#!/usr/bin/env python3
"""Build a method-assisted offline page without changing the frozen blind assets."""

from __future__ import annotations

import hashlib
import json
import math
import re
import zipfile
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path

from build_blind_standalone import (
    DIST,
    FRONTEND,
    js_for_script,
    json_for_script,
    load_json,
    replace_once,
    sanitized_translations,
    validate_inputs,
)
from build_expert_payload import extract_nodes, sanitize_sections


OUTPUT = DIST / "sa_mcgs_blind_annotation.html"
BLIND_BACKUP = DIST / "sa_mcgs_blind_annotation.original.html"
PRE_BINARY_BACKUP = DIST / "sa_mcgs_assisted_annotation.before_binary.html"
README = DIST / "ASSISTED_ANNOTATION_README_ZH.txt"
ARCHIVE = DIST / "sa_mcgs_assisted_annotation_pack.zip"
ANNOTATION_MODE = "method_assisted_review"
MODELS = {"gpt-4o", "gemini-2.5-pro"}
METHODS = {"lea", "sa-mcgs"}


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_injection_markers(manifest: dict, hints: dict) -> dict:
    """Mark actual source-text edits, never infer them from risk/affected nodes."""
    codebook = load_json(FRONTEND.parent / "internal" / "private_codebook.json")
    if codebook["manifest_hash"] != manifest["manifest_hash"]:
        raise ValueError("Injection-marker codebook does not match the frozen manifest")
    records = {record["presentation_id"]: record for record in codebook["records"]}
    if len(records) != len(codebook["records"]) or set(records) != {
        case["presentation_id"] for case in manifest["cases"]
    }:
        raise ValueError("Injection-marker presentation IDs differ from the manifest")
    originals = {}
    selected_posts = {
        case["post_case_uid"]: case
        for case in load_json(FRONTEND.parent / "candidates" / "selected_post_36.json")
    }
    for record in records.values():
        master = record["master_record"]
        if master.get("unmodified") is True:
            fingerprint = master["source_physical_fingerprint"]
            if fingerprint in originals:
                raise ValueError("Duplicate original physical SCC")
            originals[fingerprint] = master
    cases = {}
    for case in manifest["cases"]:
        pid = case["presentation_id"]
        record = records[pid]
        master = record["master_record"]
        sections, mapping = sanitize_sections(extract_nodes(master))
        if sections != case["sections"] or mapping != record["section_map"]:
            raise ValueError(f"Injection-marker source text/mapping mismatch: {pid}")
        condition = "pre" if master.get("unmodified") is True else "post"
        if condition != hints["cases"][pid]["condition"]:
            raise ValueError(f"Injection-marker condition mismatch: {pid}")
        modified = []
        if condition == "post":
            original = originals[master["source_physical_fingerprint"]]
            pre_nodes = extract_nodes(original)
            post_nodes = extract_nodes(master)
            pre_by_node = {node["id"]: node for node in pre_nodes}
            post_by_node = {node["id"]: node for node in post_nodes}
            if len(pre_by_node) != len(pre_nodes) or len(post_by_node) != len(post_nodes) or set(pre_by_node) != {
                entry["original_node_id"] for entry in mapping
            }:
                raise ValueError(f"Pre/post node identities differ: {pid}")
            modified_nodes = set()
            for section, entry in zip(sections, mapping):
                node_id = entry["original_node_id"]
                # Display titles normalize whitespace; that is not an injection.
                before = pre_by_node[node_id]["content"].strip()
                after = post_by_node[node_id]["content"].strip()
                if after != before:
                    modified.append(section["section_id"])
                    modified_nodes.add(node_id)
            selected = selected_posts[master["post_case_uid"]]
            if selected["source_physical_fingerprint"] != master["source_physical_fingerprint"] or modified_nodes != set(selected["injection_identity"]["evidence_nodes"]):
                raise ValueError(f"Text edits disagree with frozen injection identity: {pid}")
            if not modified:
                raise ValueError(f"Post sample has no injection-modified text: {pid}")
        cases[pid] = {"condition": condition, "modified_section_ids": modified}
    payload = {
        "schema_version": "assisted_injection_markers.v1",
        "source_manifest_hash": manifest["manifest_hash"],
        "derivation": "same_physical_scc_pre_post_content_diff_verified_by_injection_identity",
        "cases": cases,
    }
    return {**payload, "marker_pack_hash": canonical_hash(payload)}


def validate_hints(manifest: dict, translations: dict, hints: dict) -> dict:
    case_count, section_count = validate_inputs(manifest, translations)
    if hints.get("schema_version") != "assisted_method_hints.v1":
        raise ValueError("Unexpected method-hint schema")
    if hints.get("annotation_mode") != ANNOTATION_MODE:
        raise ValueError("Unexpected hint annotation mode")
    if hints.get("source_manifest_hash") != manifest["manifest_hash"]:
        raise ValueError("Hint pack does not match the frozen manifest")
    expected_hash = hints.get("hint_pack_hash")
    payload = {key: value for key, value in hints.items() if key != "hint_pack_hash"}
    if expected_hash != canonical_hash(payload):
        raise ValueError("Method-hint content hash mismatch")
    if set(hints.get("models", [])) != MODELS or set(hints.get("methods", [])) != METHODS:
        raise ValueError("Expected exactly two models and two methods")
    generated_at = datetime.fromisoformat(str(hints.get("generated_at", "")))
    if generated_at.tzinfo is None:
        raise ValueError("Hint generation timestamp must include a timezone")
    expected_ids = {case["presentation_id"] for case in manifest["cases"]}
    if set(hints.get("cases", {})) != expected_ids:
        raise ValueError("Hint presentation IDs do not match the manifest")
    if set(translations.get("cases", {})) != expected_ids:
        raise ValueError("Translation presentation IDs do not match the manifest")

    conditions: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    hint_count = 0
    for case in manifest["cases"]:
        presentation_id = case["presentation_id"]
        hinted_case = hints["cases"][presentation_id]
        if hinted_case.get("identity_verified") is not True:
            raise ValueError(f"Unverified hint identity: {presentation_id}")
        condition = hinted_case.get("condition")
        if condition not in {"pre", "post"}:
            raise ValueError(f"Unknown sample condition: {presentation_id}")
        conditions[condition] += 1
        section_ids = {section["section_id"] for section in case["sections"]}
        if set(hinted_case.get("sections", {})) != section_ids:
            raise ValueError(f"Hint section IDs do not match: {presentation_id}")
        translated_sections = translations["cases"][presentation_id].get("sections", {})
        if set(translated_sections) != section_ids:
            raise ValueError(f"Translation section IDs do not match: {presentation_id}")
        for section in case["sections"]:
            section_id = section["section_id"]
            translated = translated_sections[section_id]
            source = {"title": str(section.get("title") or ""), "text": str(section.get("text") or "")}
            if translated.get("source_hash") != canonical_hash(source):
                raise ValueError(f"Translation source hash mismatch: {presentation_id}/{section_id}")
            methods = hinted_case["sections"][section_id].get("methods", {})
            if set(methods) != METHODS:
                raise ValueError(f"Incomplete methods: {presentation_id}/{section_id}")
            for method_name, method in methods.items():
                models = method.get("models", {})
                if set(models) != MODELS:
                    raise ValueError(f"Incomplete models: {presentation_id}/{section_id}/{method_name}")
                for model, hint in models.items():
                    hint_count += 1
                    status = hint.get("status")
                    statuses[status] += 1
                    path = f"{presentation_id}/{section_id}/{method_name}/{model}"
                    if status not in {"available", "strict_invalid", "missing", "not_run"}:
                        raise ValueError(f"Unknown hint status: {path}")
                    if status == "available":
                        if not isinstance(hint.get("selected"), bool):
                            raise ValueError(f"Invalid selected flag: {path}")
                        rank, total = hint.get("rank"), hint.get("total_nodes")
                        if (
                            isinstance(rank, bool) or not isinstance(rank, int)
                            or isinstance(total, bool) or not isinstance(total, int)
                            or total != len(section_ids) or not 1 <= rank <= total
                        ):
                            raise ValueError(f"Invalid rank or SCC size: {path}")
                        if hint.get("top3") is not (rank <= 3):
                            raise ValueError(f"Inconsistent top-three flag: {path}")
                        score = hint.get("score")
                        if score is not None and (
                            isinstance(score, bool) or not isinstance(score, (int, float))
                            or not math.isfinite(score)
                        ):
                            raise ValueError(f"Invalid score: {path}")
                        for key in ("conflict_endpoint_mentions", "local_evidence_mentions", "repair_entry_mentions"):
                            count = hint.get(key)
                            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                                raise ValueError(f"Invalid mention count: {path}/{key}")
                    elif not isinstance(hint.get("reason_zh"), str) or not hint["reason_zh"]:
                        raise ValueError(f"Unavailable hint has no explanation: {path}")
                    elif any(key in hint for key in ("selected", "score", "rank", "total_nodes", "top3")):
                        raise ValueError(f"Unavailable hint contains stale result fields: {path}")
    if conditions != {"pre": 18, "post": 24} or hint_count != 648 * 4:
        raise ValueError("Unexpected sample-condition or hint counts")
    summary = {"presentations": case_count, "conditions": dict(conditions), "hint_statuses": dict(statuses)}
    if hints.get("summary") != summary:
        raise ValueError("Hint summary does not match its data")
    if re.search(r"\b(?:direct_mutex|condition_trigger|handoff_invariant|temporal_gate|ground[-_ ]?truth)\b", json.dumps(hints), re.I):
        raise ValueError("Method hints contain a private reference-answer field")
    return {**summary, "sections": section_count, "hint_cells": hint_count}


def assisted_app(base: str, overlay: str) -> str:
    replacements = {
        "const STORE_PREFIX = 'sa_mcgs_blind_expert_audit_v2';": "const STORE_PREFIX = 'sa_mcgs_assisted_expert_audit_v1';",
        "const STATE_SCHEMA = 'blind_annotation.state.v2';": "const STATE_SCHEMA = 'assisted_standalone_annotation.state.v1';",
        "const EXPORT_SCHEMA = 'blind_annotation.export.v2';": "const EXPORT_SCHEMA = 'assisted_standalone_annotation.export.v1';",
        "    标注模式: '独立盲法专家标注',": (
            "    标注模式: '带算法提示的辅助复核',\n"
            "    annotation_mode: 'method_assisted_review',\n"
            "    annotation_protocol: ANNOTATION_PROTOCOL,\n"
            "    injection_marker_pack_hash: state.injectionMarkers.marker_pack_hash,\n"
            "    hint_pack_hash: state.hints.hint_pack_hash,\n"
            "    hint_pack_history: state.hintPackHistory.join(';'),\n"
            "    hints_visible: state.hintsVisible,\n"
            "    progress_origin: state.progressOrigin,"
        ),
        "  if (!window.confirm(`将用备份覆盖${expertLabel(raw.expert_slot)}当前浏览器中的进度，是否继续？`)) return;": (
            "  if (!window.confirm(`将用备份覆盖${expertLabel(raw.expert_slot)}当前浏览器中的进度，是否继续？`)) return;\n"
            "  state.progressOrigin = raw.progress_origin || 'assisted_backup';\n"
            "  state.hintPackHistory = mergedHintHistory(raw.hint_pack_history || [], raw.hint_pack_hash);"
        ),
    }
    for marker, value in replacements.items():
        base = replace_once(base, marker, value)
    marker = "    annotation_mode: 'blind_human_audit',"
    if base.count(marker) != 2:
        raise ValueError("Expected two blind-mode state/export fields in the base app")
    base = base.replace(marker, (
        "    annotation_mode: 'method_assisted_review',\n"
        "    annotation_protocol: ANNOTATION_PROTOCOL,\n"
        "    injection_marker_pack_hash: state.injectionMarkers.marker_pack_hash,\n"
        "    hint_pack_hash: state.hints.hint_pack_hash,\n"
        "    hint_pack_history: state.hintPackHistory,\n"
        "    hints_visible: state.hintsVisible,\n"
        "    progress_origin: state.progressOrigin,"
    ))
    return replace_once(base, "// BOOTSTRAP_BINDINGS", overlay + "\n\n// BOOTSTRAP_BINDINGS")


def build_html(manifest: dict, translations: dict, hints: dict, markers: dict) -> str:
    html = (FRONTEND / "blind_index.template.html").read_text(encoding="utf-8")
    if hints.get("source_update"):
        snapshot_notice = hints["source_update"]["description_zh"] + "；没有可用提示不代表没有风险。"
    else:
        snapshot_notice = "算法提示使用 2026 年 8 月 29 日结果快照，未包含后续补跑；输出未通过校验或没有可用提示，不代表没有风险。"
    for marker, value in {
        'content="循环文档图结构冲突专家盲法标注工具"': 'content="循环文档图结构冲突算法辅助复核工具（非盲法）"',
        "<title>结构冲突专家盲法标注</title>": "<title>结构冲突专家辅助复核</title>",
        '<p class="eyebrow">正式专家标注</p>': '<p class="eyebrow">离线辅助复核</p>',
        "<h1>结构冲突专家盲法标注</h1>": "<h1>结构冲突专家辅助复核</h1>",
        '<p class="subtitle">请仅依据展示材料作出独立判断。页面不会显示样本生成条件或任何系统输出。</p>': (
            '<p class="subtitle">每段材料展示 LEA 与 SA-MCGS 提示；实际被注入修改的段落另标“注入段落”。标记仅说明材料来源，不代替冲突判断。</p>'
        ),
        '<span class="blind-badge">盲法模式</span>': (
            '<span class="blind-badge assisted-badge">算法辅助 · 非盲法</span>\n'
            '      <button id="toggleHintsBtn" class="button hint-toggle" type="button" aria-pressed="true">隐藏算法提示</button>'
        ),
        "  </header>\n\n  <main": (
            '  </header>\n\n'
            '  <div class="assisted-notices">\n'
            f'    <p id="hintSnapshot" class="hint-snapshot">{escape(snapshot_notice)}</p>\n'
            '    <p id="migrationNotice" class="migration-notice" role="status" hidden></p>\n'
            '  </div>\n\n  <main'
        ),
        '  <script type="application/json" id="translationData">__TRANSLATION_JSON__</script>': (
            '  <script type="application/json" id="translationData">__TRANSLATION_JSON__</script>\n'
            '  <script type="application/json" id="methodHintsData">__METHOD_HINTS_JSON__</script>\n'
            '  <script type="application/json" id="injectionMarkersData">__INJECTION_MARKERS_JSON__</script>'
        ),
    }.items():
        html = replace_once(html, marker, value)
    css = (FRONTEND / "blind_styles.css").read_text(encoding="utf-8")
    css += "\n\n" + (FRONTEND / "assisted_standalone_styles.css").read_text(encoding="utf-8")
    overlays = "\n\n".join(
        (FRONTEND / name).read_text(encoding="utf-8")
        for name in ("assisted_standalone_app.js", "binary_protocol_state.js", "binary_annotation_app.js", "injection_markers_app.js")
    )
    app = assisted_app(
        (FRONTEND / "blind_app.js").read_text(encoding="utf-8"),
        overlays,
    )
    for marker, value in {
        "__BLIND_CSS__": css,
        "__MANIFEST_JSON__": json_for_script(manifest),
        "__TRANSLATION_JSON__": json_for_script(sanitized_translations(translations)),
        "__METHOD_HINTS_JSON__": json_for_script(hints),
        "__INJECTION_MARKERS_JSON__": json_for_script(markers),
        "__XLSX_VENDOR__": js_for_script((FRONTEND / "vendor" / "xlsx.full.min.js").read_text(encoding="utf-8")),
        "__BLIND_APP__": js_for_script(app),
    }.items():
        html = replace_once(html, marker, value)
    return html


def preserve_blind_original() -> None:
    if BLIND_BACKUP.exists():
        backup = BLIND_BACKUP.read_text(encoding="utf-8")
        if "const STORE_PREFIX = 'sa_mcgs_blind_expert_audit_v2';" not in backup:
            raise ValueError("Existing original backup is not the frozen blind page")
        return
    if not OUTPUT.is_file():
        raise ValueError("Original blind HTML must exist before creating its protected backup")
    original = OUTPUT.read_bytes()
    text = original.decode("utf-8")
    if (
        "const STORE_PREFIX = 'sa_mcgs_blind_expert_audit_v2';" not in text
        or "annotation_mode: 'blind_human_audit'" not in text
        or 'id="methodHintsData"' in text
    ):
        raise ValueError("Refusing to archive a non-blind page as the original blind HTML")
    with BLIND_BACKUP.open("xb") as handle:
        handle.write(original)


def preserve_pre_binary_page() -> None:
    if PRE_BINARY_BACKUP.exists() or not OUTPUT.exists():
        return
    original = OUTPUT.read_bytes()
    if b"const ANNOTATION_PROTOCOL = 'binary_judgment_v1';" in original:
        return
    with PRE_BINARY_BACKUP.open("xb") as handle:
        handle.write(original)


def write_readme(hints: dict) -> None:
    snapshot_description = hints.get("source_update", {}).get("description_zh") or "2026 年 8 月 29 日算法结果快照，未刷新为后来补跑结果"
    README.write_text(
        f"""结构冲突专家辅助复核离线包（带算法提示，非盲法）

使用方法
1. 双击 sa_mcgs_blind_annotation.html。保留原文件名是为了方便继续使用；当前页面为带算法提示版本，不是盲法版。
2. 每段均有 LEA / SA-MCGS、GPT-4o / Gemini 2.5 Pro 的对应结果。无需联网，不需要另外载入 JSON。
3. 页面顶部可隐藏或显示算法提示。隐藏后仍属于这个辅助复核版本，不能据此当作从未接触提示的盲法标注。
4. 选择专家编号并填写匿名编号。浏览器自动保存；每次结束时请点击“保存进度备份”。
5. 可通过“恢复进度备份”导入兼容的旧盲法进度或本版进度。旧进度不会被当作纯辅助标注来源抹去；导出含有来源字段。
6. 完成后导出当前专家电子表格，并保留 JSON 进度备份。

提示与版本
- {snapshot_description}。
- 自动接续兼容的旧辅助页进度；旧记录不覆盖，新导出保留接触过的提示版本列表。
- 本页使用 binary_judgment_v1：是否存在冲突（存在/不存在）、材料是否足够支持判断（充分/不充分）、信心1到5分。逐段保留最小证据与修复材料，角色分类非必填、备注选填。
- 新的判断充分性不同于旧“冲突证据充分性”，不会自动把部分充分或不适用转换成新选项。确认并保存后才视为完成；不充分案例单独待复核，不当作确定负例。
- 18 个未注入原始样本和 24 个注入后样本，共 42 份材料、648 段；此前已标注的旧 12 份不在这次新增材料里。
- 提示中的得分、排名和选中状态是算法输出，不是专家标准答案；输出无效或未选中不等于没有风险。
- “注入段落”仅标记与同源原始材料相比确实被修改的段落；未注入材料和未修改上下文不标记，也不自动勾选任何答案。隐藏算法提示不会隐藏此标记。
- 导出顶层记录当前注入标记版本；只有实际编辑的标注才记录该版本，旧答案不追溯改写。当前页面仍为非盲辅助复核。
- 单文件同时包含中文材料、原文、提示和表格导出组件，完全离线可用。
- 本版使用独立的浏览器保存空间；导出标记为 method_assisted_review，不能冒充独立盲法结果。
- 请勿删除旧盲法进度备份。原盲法页面另存为 sa_mcgs_blind_annotation.original.html，旧盲法 ZIP 包未改。
""",
        encoding="utf-8",
    )


def write_zip() -> None:
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in (OUTPUT, README):
            info = zipfile.ZipInfo(path.name, date_time=(2026, 9, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def main() -> None:
    manifest = load_json(FRONTEND / "data" / "manifest.json")
    translations = load_json(FRONTEND / "data" / "translations_zh.json")
    hints = load_json(FRONTEND / "data" / "method_hints.json")
    summary = validate_hints(manifest, translations, hints)
    markers = build_injection_markers(manifest, hints)
    html = build_html(manifest, translations, hints, markers)
    DIST.mkdir(parents=True, exist_ok=True)
    preserve_blind_original()
    preserve_pre_binary_page()
    OUTPUT.write_text(html, encoding="utf-8")
    write_readme(hints)
    write_zip()
    print(json.dumps({
        "built": str(OUTPUT),
        "original_blind_backup": str(BLIND_BACKUP),
        **summary,
        "annotation_mode": ANNOTATION_MODE,
        "hint_pack_hash": hints["hint_pack_hash"],
        "hint_generated_at": hints["generated_at"],
        "injection_marked_sections": sum(len(case["modified_section_ids"]) for case in markers["cases"].values()),
        "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        "archive": str(ARCHIVE),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

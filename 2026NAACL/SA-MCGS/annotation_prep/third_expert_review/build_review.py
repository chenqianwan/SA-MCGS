#!/usr/bin/env python3
"""Select a targeted third-rater subset and package an isolated offline blind UI.

Read-only XLSX extraction; never modifies original labels or model results.
Selection uses expert answers only, not system performance or injection labels.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
PREP = HERE.parent
sys.path.insert(0, str(PREP / "analysis_v1"))
from annotation_analysis import validate_binary_annotation
sys.path.insert(0, str(PREP / "frontend/tools"))
from build_assisted_standalone import build_injection_markers

DEFAULT_INPUTS = (
    Path('/Users/chenlong/Downloads/arr_oct2026_expert_audit_专家_1_1_2026-09-18_辅助复核_标注结果.xlsx'),
    Path('/Users/chenlong/Downloads/arr_oct2026_expert_audit_专家_2_2_2026-09-20_辅助复核_标注结果.xlsx'),
)
POLICY = {
    "id": "targeted_third_blind_v1",
    "rule": "union_of_annotation_only_triggers",
    "target_conflict_disagreement": True,
    "any_judgment_insufficient": True,
    "any_confidence_at_most": 2,
    "positive_localization_gate": "at_least_one_present_and_sufficient",
    "minimal_evidence_jaccard_strictly_below": 0.5,
    "repair_packet_jaccard_strictly_below": 0.5,
    "empty_empty_jaccard": 1.0,
    "model_outputs_used": False,
    "selection_timing": "after_two_expert_annotations_before_third_expert_annotation",
    "order": "filter_existing_frozen_expert_3_order_without_reordering",
}
REASON_LABELS = {
    "target_disagreement": "冲突存在性判断不同",
    "insufficient": "至少一位认为材料不充分",
    "low_confidence": "至少一位信心不高于2/5",
    "minimal_low_overlap": "最小证据集重合度低于50%",
    "repair_low_overlap": "修复材料集重合度低于50%",
}


def canonical_hash(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def records(sheet):
    rows = list(sheet.values)
    header = rows[0]
    if len(header) != len(set(header)):
        raise ValueError(f"Duplicate headers: {sheet.title}")
    return [dict(zip(header, row), _xlsx_row=i) for i, row in enumerate(rows[1:], 2)]


def as_set(value):
    return set(str(value).split(";")) if value else set()


def read_expert(path, manifest, slot):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = records(workbook["样本整体标注"])
        paragraphs = records(workbook["逐段标注"])
        metadata = records(workbook["版本信息"])
    finally:
        workbook.close()
    cases = {c["presentation_id"]: c for c in manifest["cases"]}
    if len(rows) != len(cases) or {r["样本编号"] for r in rows} != set(cases):
        raise ValueError(f"Missing/duplicate/extra cases: {path}")
    if [r["样本编号"] for r in rows] != manifest["expert_orders"][slot]:
        raise ValueError(f"Unexpected expert order: {path}")
    if len(metadata) != 1 or metadata[0]["manifest_hash"] != manifest["manifest_hash"]:
        raise ValueError(f"Metadata identity mismatch: {path}")
    sections = {pid: {} for pid in cases}
    for row in paragraphs:
        pid, sid = row["样本编号"], row["段落编号"]
        if pid not in sections or sid in sections[pid]:
            raise ValueError(f"Invalid/duplicate section: {pid}/{sid}")
        if row["是否最小证据"] not in {"是", "否"} or row["是否修复材料"] not in {"是", "否"}:
            raise ValueError(f"Missing section choice: {pid}/{sid}")
        source = next((s for s in cases[pid]["sections"] if s["section_id"] == sid), None)
        if source is None or str(row["原文标题"] or "") != source["title"] or str(row["原文正文"] or "") != source["text"]:
            raise ValueError(f"Section text identity mismatch: {pid}/{sid}")
        sections[pid][sid] = {
            "minimal_evidence": row["是否最小证据"] == "是",
            "repair_packet": row["是否修复材料"] == "是",
        }
    result = {}
    for row in rows:
        pid = row["样本编号"]
        if row["manifest_hash"] != manifest["manifest_hash"] or row["完成状态"] != "已完成":
            raise ValueError(f"Unfinished/identity mismatch: {pid}")
        record = validate_binary_annotation({
            "annotation_protocol": row["annotation_protocol"],
            "target_conflict": row["目标冲突代码"],
            "judgment_sufficient": row["judgment_sufficient"],
            "sets_reviewed": row["sets_reviewed"],
            "confidence": row["判断信心_1到5"],
            "sections": sections[pid],
        }, {s["section_id"] for s in cases[pid]["sections"]})
        if as_set(row["最小证据段落"]) != set(record["minimal_evidence_section_ids"]) or as_set(row["修复材料段落"]) != set(record["repair_packet_section_ids"]):
            raise ValueError(f"Case/paragraph set mismatch: {pid}")
        result[pid] = {
            **{k: record[k] for k in ("target_conflict", "judgment_sufficient", "confidence", "minimal_evidence_section_ids", "repair_packet_section_ids")},
            "xlsx_row": row["_xlsx_row"],
        }
    return result, {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "expert_slot": slot, "export_metadata": metadata[0]}


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 1.0


def reasons_for(a, b):
    reasons = []
    if a["target_conflict"] != b["target_conflict"]:
        reasons.append("target_disagreement")
    if any(r["judgment_sufficient"] == "no" for r in (a, b)):
        reasons.append("insufficient")
    if any(r["confidence"] <= POLICY["any_confidence_at_most"] for r in (a, b)):
        reasons.append("low_confidence")
    jm = jaccard(a["minimal_evidence_section_ids"], b["minimal_evidence_section_ids"])
    jr = jaccard(a["repair_packet_section_ids"], b["repair_packet_section_ids"])
    if any(r["target_conflict"] == "present" and r["judgment_sufficient"] == "yes" for r in (a, b)):
        if jm < POLICY["minimal_evidence_jaccard_strictly_below"]:
            reasons.append("minimal_low_overlap")
        if jr < POLICY["repair_packet_jaccard_strictly_below"]:
            reasons.append("repair_low_overlap")
    return reasons, jm, jr


def prepare(paths):
    manifest = load(PREP / "frontend/data/manifest.json")
    translations = load(PREP / "frontend/data/translations_zh.json")
    if translations["source_manifest_hash"] != manifest["manifest_hash"]:
        raise ValueError("Translations and manifest differ")
    experts, inputs = [], []
    for path, slot in zip(paths, ("expert_1", "expert_2")):
        data, provenance = read_expert(path, manifest, slot)
        experts.append(data)
        inputs.append(provenance)
    # All 42 cases assessed under one rule, including nonselected cases.
    decision_rows = []
    for case in manifest["cases"]:
        pid = case["presentation_id"]
        a, b = (expert[pid] for expert in experts)
        reasons, jm, jr = reasons_for(a, b)
        decision_rows.append({"presentation_id": pid, "selected": bool(reasons), "reasons": reasons,
                              "minimal_jaccard": jm, "repair_jaccard": jr, "expert_1": a, "expert_2": b})
    selected = {row["presentation_id"] for row in decision_rows if row["selected"]}
    order = [pid for pid in manifest["expert_orders"]["expert_3"] if pid in selected]
    by_id = {c["presentation_id"]: c for c in manifest["cases"]}
    public = {
        "schema_version": "blind_annotation.v1",
        "study_id": "arr_oct2026_expert_audit_third_review_v1",
        "parent_manifest_hash": manifest["manifest_hash"],
        "review_protocol": POLICY["id"],
        "cases": [copy.deepcopy(by_id[pid]) for pid in order],
        "expert_orders": {"expert_3": order},
    }
    public["manifest_hash"] = canonical_hash(public)
    translated = {
        "schema_version": translations["schema_version"], "locale": translations.get("locale", "zh-CN"),
        "source_manifest_hash": public["manifest_hash"],
        "parent_translation_pack_hash": translations["translation_pack_hash"],
        "cases": {pid: {"sections": {sid: {"title_zh": str(value.get("title_zh", "")), "text_zh": str(value.get("text_zh", ""))}
                                            for sid, value in translations["cases"][pid]["sections"].items()}}
                  for pid in order},
    }
    translated["translation_pack_hash"] = canonical_hash(translated)
    private = {r["presentation_id"]: r for r in load(PREP / "internal/private_codebook.json")["records"]}
    for row in decision_rows:
        master = private[row["presentation_id"]]["master_record"]
        row.update(condition="pre" if master.get("unmodified") is True else "post", domain=master["domain"],
                   source_physical_fingerprint=master["source_physical_fingerprint"])
    selected_rows = [r for r in decision_rows if r["selected"]]
    audit = {
        "schema_version": "targeted_third_selection.v1", "policy": POLICY,
        "author_blinding_attestation": {"date": "2026-09-20", "scope": "experts_1_and_2", "statement": "作者明确确认标注时所有辅助信息不可见，实际为盲评；原导出元数据保留，不据其推断实际暴露。"},
        "inputs": inputs, "parent_manifest_hash": manifest["manifest_hash"], "subset_manifest_hash": public["manifest_hash"],
        "summary": {"parent_cases": len(manifest["cases"]), "selected_cases": len(selected),
                    "selected_sections": sum(len(c["sections"]) for c in public["cases"]),
                    "conditions": dict(Counter(r["condition"] for r in selected_rows)),
                    "domains": dict(Counter(r["domain"] for r in selected_rows)),
                    "reasons_overlapping": dict(Counter(reason for r in selected_rows for reason in r["reasons"]))},
        "decisions": decision_rows, "expert_3_order": order,
    }
    prior_audit_path = HERE / "internal/selection_audit.json"
    if prior_audit_path.exists():
        prior = load(prior_audit_path)
        if ([r["sha256"] for r in prior["inputs"]] != [r["sha256"] for r in inputs]
                or prior["policy"] != POLICY
                or prior["subset_manifest_hash"] != public["manifest_hash"]):
            raise ValueError("Frozen selection changed; create a separately versioned review package instead of overwriting this one")
    # Audit is researcher-only. It must never be shipped in the expert archive.
    dump(prior_audit_path, audit)
    dump(HERE / "data/manifest.json", public)
    dump(HERE / "data/translations_zh.json", translated)
    lines = ["# 第三位专家补标清单（研究者内部，不发给专家）", "",
             f"统一规则筛选 {len(selected)} / {len(manifest['cases'])} 个案例，共 {audit['summary']['selected_sections']} 段。条件和筛选理由仅在此表保留。", "",
             "| 专家展示序号 | 样本编号 | 条件 | 领域 | 入选理由 | 最小证据重合度 | 修复材料重合度 |",
             "|---:|---|---|---|---|---:|---:|"]
    decisions = {r["presentation_id"]: r for r in decision_rows}
    for index, pid in enumerate(order, 1):
        r = decisions[pid]
        lines.append(f"| {index} | {pid} | {r['condition']} | {r['domain']} | {'；'.join(REASON_LABELS[k] for k in r['reasons'])} | {r['minimal_jaccard']:.1%} | {r['repair_jaccard']:.1%} |")
    lines += ["", "此子集按双专家标签事后筛选，不是代表性随机样本。未入选不等于标签完全相同；两位原始标签全部保留。"]
    (HERE / "internal/SELECTION_ZH.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return public, translated, audit


def escaped_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def subset_hints(public):
    """Reuse exact frozen method cells, excluding generation conditions."""
    source = load(PREP / "frontend/data/method_hints.json")
    body = {k: v for k, v in source.items() if k != "hint_pack_hash"}
    if canonical_hash(body) != source["hint_pack_hash"]:
        raise ValueError("Source hint checksum mismatch")
    if source["source_manifest_hash"] != public["parent_manifest_hash"]:
        raise ValueError("Hints do not match the parent materials")
    cases = {}
    for case in public["cases"]:
        pid = case["presentation_id"]
        original = source["cases"][pid]
        if original.get("identity_verified") is not True or set(original["sections"]) != {s["section_id"] for s in case["sections"]}:
            raise ValueError(f"Hint identity mismatch: {pid}")
        for section in original["sections"].values():
            for method in ("lea", "sa-mcgs"):
                for model in ("gpt-4o", "gemini-2.5-pro"):
                    cell = section["methods"][method]["models"][model]
                    if cell["status"] not in {"available", "strict_invalid", "missing", "not_run"}:
                        raise ValueError("Unknown hint status")
        cases[pid] = {"identity_verified": True, "sections": copy.deepcopy(original["sections"])}
    hints = {"schema_version": "third_expert_method_hints.v1", "annotation_mode": "method_assisted_review",
             "source_manifest_hash": public["manifest_hash"], "parent_manifest_hash": public["parent_manifest_hash"],
             "parent_hint_pack_hash": source["hint_pack_hash"],
             "methods": ["lea", "sa-mcgs"], "models": ["gpt-4o", "gemini-2.5-pro"], "cases": cases}
    hints["hint_pack_hash"] = canonical_hash(hints)
    dump(HERE / "data/method_hints.json", hints)
    return hints


def subset_injection_markers(public):
    """Export only verified generation conditions and actual source-text edits.

    The shared parent builder compares the same physical SCC before/after
    injection and checks the changed nodes against the frozen injection identity.
    The rebuilt result must also match the marker pack already in the parent UI.
    No expert labels or selection reasons enter this payload.
    """
    parent = load(PREP / "frontend/data/manifest.json")
    source_hints = load(PREP / "frontend/data/method_hints.json")
    for value, hash_key in ((public, "manifest_hash"), (source_hints, "hint_pack_hash")):
        if canonical_hash({k: v for k, v in value.items() if k != hash_key}) != value.get(hash_key):
            raise ValueError(f"Injection-marker input checksum mismatch: {hash_key}")
    # The frozen parent manifest hashes an empty hash field without a prefix.
    if canonical_hash({**parent, "manifest_hash": ""}) != "sha256:" + parent["manifest_hash"]:
        raise ValueError("Injection-marker parent manifest checksum mismatch")
    if public.get("parent_manifest_hash") != parent["manifest_hash"]:
        raise ValueError("Injection markers do not match the parent materials")
    if source_hints.get("source_manifest_hash") != parent["manifest_hash"]:
        raise ValueError("Injection-marker hints do not match the parent materials")
    parents = {case["presentation_id"]: case for case in parent["cases"]}
    case_ids = [case["presentation_id"] for case in public["cases"]]
    if len(case_ids) != 14 or len(set(case_ids)) != 14:
        raise ValueError("Injection markers require 14 unique third-expert cases")
    if public.get("expert_orders") != {"expert_3": case_ids} or case_ids != [
        pid for pid in parent["expert_orders"]["expert_3"] if pid in set(case_ids)
    ]:
        raise ValueError("Injection-marker subset order differs from the frozen expert order")
    for case in public["cases"]:
        if case != parents.get(case["presentation_id"]):
            raise ValueError(f"Injection-marker subset identity mismatch: {case['presentation_id']}")

    source = build_injection_markers(parent, source_hints)
    embedded = re.findall(
        r'<script\b[^>]*\bid="injectionMarkersData"[^>]*>(.*?)</script>',
        (PREP / "dist/sa_mcgs_blind_annotation.html").read_text(encoding="utf-8"),
        flags=re.S,
    )
    if len(embedded) != 1 or json.loads(embedded[0]) != source:
        raise ValueError("Rebuilt injection markers differ from the frozen parent page")
    if source.get("schema_version") != "assisted_injection_markers.v1" or source.get("source_manifest_hash") != parent["manifest_hash"]:
        raise ValueError("Unexpected parent injection-marker identity")
    if canonical_hash({k: v for k, v in source.items() if k != "marker_pack_hash"}) != source.get("marker_pack_hash"):
        raise ValueError("Source injection-marker checksum mismatch")
    if set(source["cases"]) != set(parents):
        raise ValueError("Parent injection-marker cases differ from the manifest")
    cases = {}
    for case in public["cases"]:
        pid = case["presentation_id"]
        original = source["cases"][pid]
        condition, modified = original["condition"], original["modified_section_ids"]
        sections = {section["section_id"] for section in case["sections"]}
        if (condition not in {"pre", "post"} or not isinstance(modified, list)
                or len(set(modified)) != len(modified) or not set(modified) <= sections
                or (condition == "pre" and modified) or (condition == "post" and not modified)):
            raise ValueError(f"Invalid injection-marker sections: {pid}")
        cases[pid] = {"condition": condition, "modified_section_ids": list(modified)}
    markers = {
        "schema_version": "third_expert_injection_markers.v1",
        "source_manifest_hash": public["manifest_hash"],
        "parent_manifest_hash": parent["manifest_hash"],
        "parent_marker_pack_hash": source["marker_pack_hash"],
        "cases": cases,
    }
    markers["marker_pack_hash"] = canonical_hash(markers)
    dump(HERE / "data/injection_markers.json", markers)
    return markers


def build(public, translated):
    hints = subset_hints(public)
    markers = subset_injection_markers(public)
    frontend = HERE / "frontend"
    text = (frontend / "index.template.html").read_text(encoding="utf-8")
    substitutions = {
        "__BLIND_CSS__": (PREP / "frontend/blind_styles.css").read_text(encoding="utf-8") + "\n" + (PREP / "frontend/assisted_standalone_styles.css").read_text(encoding="utf-8") + "\n" + (frontend / "styles.css").read_text(encoding="utf-8"),
        "__MANIFEST_JSON__": escaped_json(public),
        "__TRANSLATION_JSON__": escaped_json(translated),
        "__METHOD_HINTS_JSON__": escaped_json(hints),
        "__INJECTION_MARKERS_JSON__": escaped_json(markers),
        "__XLSX_VENDOR__": re.sub(r"</script", r"<\\/script", (PREP / "frontend/vendor/xlsx.full.min.js").read_text(encoding="utf-8"), flags=re.I),
        "__BLIND_APP__": re.sub(r"</script", r"<\\/script", (frontend / "app.js").read_text(encoding="utf-8"), flags=re.I),
    }
    for marker, value in substitutions.items():
        if text.count(marker) != 1:
            raise ValueError(f"Template marker missing/duplicated: {marker}")
        text = text.replace(marker, value)
    out = HERE / "dist"
    out.mkdir(exist_ok=True)
    html_path = out / "第三专家_独立盲评.html"
    blind_backup = out / "第三专家_独立盲评.original.html"
    if html_path.exists() and not blind_backup.exists():
        if 'id="methodHintsData"' in html_path.read_text(encoding="utf-8"):
            raise ValueError("Cannot label an assisted page as an original blind backup")
        shutil.copyfile(html_path, blind_backup)
    archive_path = out / "第三专家_离线打标包.zip"
    archive_backup = out / "第三专家_离线打标包.original.zip"
    if archive_path.exists() and not archive_backup.exists():
        shutil.copyfile(archive_path, archive_backup)
    html_path.write_text(text, encoding="utf-8")
    readme = out / "使用说明.txt"
    readme.write_text(
        f"第三位专家标注（含可隐藏的算法提示和真实注入标记）\n\n本包含 {len(public['cases'])} 个案例。文件名沿用原名，当前页面含算法提示和真实注入标记。\n"
        "1. 双击 HTML 文件即可离线使用，填写自己的匿名编号。\n"
        "2. 阅读完整材料，回答冲突存在性、判断充分性和信心，并选择最小证据、修复材料。\n"
        "3. 每段下方提供 LEA、SA-MCGS 的 GPT-4o、Gemini 2.5 Pro 结果，仅供参考，不是标准答案；顶部可隐藏提示。\n"
        "   案例显示是否经过注入；“注入段落”仅标记与同源原始材料相比正文实际改动的段落，不代表全部冲突、风险或修复段落。\n"
        "4. 材料不足可如实选择不充分，无需强行判断。\n"
        "5. 页面自动保存于当前浏览器。每次结束请下载 JSON 备份，全部完成后导出 Excel 和 JSON 两份结果。\n"
        "6. 不查看或讨论其他专家答案；请使用独立浏览器用户目录或电脑。可恢复当前包或同一14项旧无提示版的备份。\n"
        "7. 导出分别保留历史记录来源、当前页面模式和提示显示状态；隐藏提示不会追溯改变历史记录。实际盲评操作另行记录。\n",
        encoding="utf-8",
    )
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in (html_path, readme):
            info = zipfile.ZipInfo(path.name, date_time=(2026, 9, 20, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return html_path, archive_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expert-1", type=Path, default=DEFAULT_INPUTS[0])
    parser.add_argument("--expert-2", type=Path, default=DEFAULT_INPUTS[1])
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    public, translations, audit = prepare((args.expert_1, args.expert_2))
    print(json.dumps(audit["summary"], ensure_ascii=False))
    if not args.prepare_only:
        html, archive = build(public, translations)
        print(f"html={html}\narchive={archive}")


if __name__ == "__main__":
    main()

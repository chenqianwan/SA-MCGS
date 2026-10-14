#!/usr/bin/env python3
"""Build the formal blind annotation UI as one offline HTML file."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1]
DIST = FRONTEND.parent / "dist"
OUTPUT = DIST / "sa_mcgs_blind_annotation.html"
README = DIST / "BLIND_ANNOTATION_README_ZH.txt"
ARCHIVE = DIST / "sa_mcgs_blind_annotation_pack.zip"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sanitized_translations(raw: dict) -> dict:
    cases: dict[str, dict] = {}
    for presentation_id, case in raw["cases"].items():
        sections: dict[str, dict[str, str]] = {}
        for section_id, section in case["sections"].items():
            sections[section_id] = {
                "title_zh": str(section.get("title_zh", "")),
                "text_zh": str(section.get("text_zh", "")),
            }
        cases[presentation_id] = {"sections": sections}
    return {
        "schema_version": raw["schema_version"],
        "locale": raw.get("locale", "zh-CN"),
        "source_manifest_hash": raw["source_manifest_hash"],
        "translation_pack_hash": raw.get("translation_pack_hash", ""),
        "cases": cases,
    }


def validate_inputs(manifest: dict, translations: dict) -> tuple[int, int]:
    if manifest.get("schema_version") != "blind_annotation.v1":
        raise ValueError("Unexpected manifest schema")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != 42:
        raise ValueError(f"Expected 42 cases, found {len(cases) if isinstance(cases, list) else 'invalid'}")
    case_ids = [case.get("presentation_id") for case in cases]
    if len(set(case_ids)) != 42 or any(not value for value in case_ids):
        raise ValueError("Presentation IDs are missing or duplicated")
    if translations.get("source_manifest_hash") != manifest.get("manifest_hash"):
        raise ValueError("Translation pack does not match the manifest")
    section_count = 0
    for case in cases:
        if set(case) != {"presentation_id", "domain_label", "sections"}:
            raise ValueError(f"Unsafe manifest keys for {case.get('presentation_id')}")
        if not case["sections"]:
            raise ValueError(f"Case {case['presentation_id']} has no sections")
        translated_case = translations.get("cases", {}).get(case["presentation_id"])
        if not translated_case:
            raise ValueError(f"Missing translations for {case['presentation_id']}")
        seen_sections: set[str] = set()
        for section in case["sections"]:
            if set(section) != {"section_id", "title", "text"}:
                raise ValueError(f"Unsafe section keys in {case['presentation_id']}")
            section_id = section["section_id"]
            if section_id in seen_sections:
                raise ValueError(f"Duplicate section {case['presentation_id']} / {section_id}")
            seen_sections.add(section_id)
            translated = translated_case.get("sections", {}).get(section_id)
            if translated is None or not isinstance(translated.get("text_zh"), str):
                raise ValueError(f"Missing translation {case['presentation_id']} / {section_id}")
            section_count += 1
    if section_count != 648:
        raise ValueError(f"Expected 648 sections, found {section_count}")
    expected = set(case_ids)
    for expert in ("expert_1", "expert_2", "expert_3"):
        order = manifest.get("expert_orders", {}).get(expert)
        if not isinstance(order, list) or len(order) != 42 or set(order) != expected:
            raise ValueError(f"Invalid frozen order for {expert}")
    return len(cases), section_count


def json_for_script(value: dict) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def js_for_script(text: str) -> str:
    return re.sub(r"</script", r"<\\/script", text, flags=re.IGNORECASE)


def replace_once(source: str, marker: str, value: str) -> str:
    if source.count(marker) != 1:
        raise ValueError(f"Template marker must occur exactly once: {marker}")
    return source.replace(marker, value)


def write_readme() -> None:
    README.write_text(
        """结构冲突正式专家盲法标注包

使用方法
1. 双击 sa_mcgs_blind_annotation.html；无需联网，也不需要安装软件。
2. 选择分配给你的专家编号，并填写匿名标注者编号。请勿在标注过程中切换专家编号。
3. 中文是主要阅读材料；如需核对术语，可展开原文。
4. 页面会自动保存在当前浏览器。建议每次结束前点击“保存进度备份”下载 JSON 文件。
5. 全部完成后，导出“当前专家结果”电子表格，并再保存一次进度备份。

注意事项
- 每位专家请使用独立的浏览器用户目录或独立电脑，避免覆盖他人进度。
- 不要修改 HTML 文件名或内容；恢复备份时只能选择本页面导出的 JSON 文件。
- 如果浏览器提示无法自动保存，请立即下载进度备份，并在继续工作后再次备份。
""",
        encoding="utf-8",
    )


def write_zip() -> None:
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in (OUTPUT, README):
            info = zipfile.ZipInfo(path.name, date_time=(2026, 9, 5, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def main() -> None:
    manifest = load_json(FRONTEND / "data" / "manifest.json")
    translations = sanitized_translations(load_json(FRONTEND / "data" / "translations_zh.json"))
    case_count, section_count = validate_inputs(manifest, translations)

    html = (FRONTEND / "blind_index.template.html").read_text(encoding="utf-8")
    html = replace_once(html, "__BLIND_CSS__", (FRONTEND / "blind_styles.css").read_text(encoding="utf-8"))
    html = replace_once(html, "__MANIFEST_JSON__", json_for_script(manifest))
    html = replace_once(html, "__TRANSLATION_JSON__", json_for_script(translations))
    html = replace_once(html, "__XLSX_VENDOR__", js_for_script((FRONTEND / "vendor" / "xlsx.full.min.js").read_text(encoding="utf-8")))
    html = replace_once(html, "__BLIND_APP__", js_for_script((FRONTEND / "blind_app.js").read_text(encoding="utf-8")))

    DIST.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    write_readme()
    write_zip()
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    print(f"built={OUTPUT}")
    print(f"cases={case_count} sections={section_count}")
    print(f"sha256={digest}")
    print(f"archive={ARCHIVE}")


if __name__ == "__main__":
    main()

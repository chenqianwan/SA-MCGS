#!/usr/bin/env python3
"""Validate that the distributable annotation page is complete and truly blind."""

from __future__ import annotations

import json
import re
from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1]
DIST = FRONTEND.parent / "dist"
PAGE = DIST / "sa_mcgs_blind_annotation.html"
README = DIST / "BLIND_ANNOTATION_README_ZH.txt"


def embedded_json(html: str, element_id: str) -> dict:
    match = re.search(
        rf'<script\s+type="application/json"\s+id="{re.escape(element_id)}">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError(f"Missing embedded data: {element_id}")
    return json.loads(match.group(1))


def validate_data(manifest: dict, translations: dict) -> tuple[int, int]:
    assert set(manifest) == {
        "schema_version", "study_id", "randomization_seed", "manifest_hash", "cases", "expert_orders"
    }
    assert manifest["schema_version"] == "blind_annotation.v1"
    assert isinstance(manifest["cases"], list) and len(manifest["cases"]) == 42
    case_ids: list[str] = []
    section_count = 0
    for case in manifest["cases"]:
        assert set(case) == {"presentation_id", "domain_label", "sections"}
        assert re.fullmatch(r"P-[A-Z0-9]{10}", case["presentation_id"])
        case_ids.append(case["presentation_id"])
        assert case["sections"]
        for section in case["sections"]:
            assert set(section) == {"section_id", "title", "text"}
            assert re.fullmatch(r"S\d{3}", section["section_id"])
            assert isinstance(section["title"], str) and isinstance(section["text"], str)
            section_count += 1
    assert len(case_ids) == len(set(case_ids)) == 42
    assert section_count == 648
    expected = set(case_ids)
    assert set(manifest["expert_orders"]) == {"expert_1", "expert_2", "expert_3"}
    for order in manifest["expert_orders"].values():
        assert len(order) == len(set(order)) == 42 and set(order) == expected

    assert set(translations) == {
        "schema_version", "locale", "source_manifest_hash", "translation_pack_hash", "cases"
    }
    assert translations["schema_version"] == "annotation_translation.zh-CN.v1"
    assert translations["source_manifest_hash"] == manifest["manifest_hash"]
    assert set(translations["cases"]) == expected
    translated_sections = 0
    for case in manifest["cases"]:
        translated_case = translations["cases"][case["presentation_id"]]
        assert set(translated_case) == {"sections"}
        expected_sections = {section["section_id"] for section in case["sections"]}
        assert set(translated_case["sections"]) == expected_sections
        for section in translated_case["sections"].values():
            assert set(section) == {"title_zh", "text_zh"}
            assert isinstance(section["title_zh"], str) and isinstance(section["text_zh"], str)
            translated_sections += 1
    assert translated_sections == 648
    return len(case_ids), section_count


def validate_surface() -> None:
    surface = "\n".join([
        (FRONTEND / "blind_index.template.html").read_text(encoding="utf-8"),
        (FRONTEND / "blind_app.js").read_text(encoding="utf-8"),
        README.read_text(encoding="utf-8"),
    ])
    forbidden = (
        "method_hints", "hint_pack_hash", "SA-MCGS", "GPT-4o", "Gemini",
        "未注入", "注入后", "算法提示", "injection_template", "canonical_case_id",
        "source_physical_uid", "variant_case_uid", "ground_truth", "reference_answer",
    )
    for marker in forbidden:
        assert marker.lower() not in surface.lower(), f"Forbidden visible marker: {marker}"
    assert not re.search(r"(?<![A-Za-z0-9_])LEA(?![A-Za-z0-9_])", surface, flags=re.IGNORECASE), \
        "Forbidden visible marker: LEA"


def validate_offline(html: str) -> None:
    assert "__BLIND_" not in html and "__MANIFEST_JSON__" not in html and "__TRANSLATION_JSON__" not in html
    assert not re.search(r"<(?:script|link|img)\b[^>]*(?:src|href)\s*=", html, flags=re.IGNORECASE)
    app_source = (FRONTEND / "blind_app.js").read_text(encoding="utf-8")
    assert "fetch(" not in app_source
    assert "XMLHttpRequest" not in app_source


def main() -> None:
    if not PAGE.exists() or not README.exists():
        raise SystemExit("Run build_blind_standalone.py first")
    html = PAGE.read_text(encoding="utf-8")
    manifest = embedded_json(html, "manifestData")
    translations = embedded_json(html, "translationData")
    cases, sections = validate_data(manifest, translations)
    validate_surface()
    validate_offline(html)
    print(f"validated={PAGE}")
    print(f"cases={cases} sections={sections} experts=3")
    print("blind_surface=pass offline_single_file=pass")


if __name__ == "__main__":
    main()

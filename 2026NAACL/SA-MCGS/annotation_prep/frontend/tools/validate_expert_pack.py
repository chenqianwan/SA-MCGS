#!/usr/bin/env python3
"""Fail-closed validation for the Chinese method-assisted annotation pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

from build_expert_payload import assert_allowed_schema


EXPERT_UI_FILES = ("index.html", "app.js")
FORBIDDEN_UI_PATTERNS = {
    "generator label": re.compile(r"\b(?:direct_mutex|condition_trigger|handoff_invariant|temporal_gate)\b", re.I),
    "reference-answer hint": re.compile(r"ground[-_ ]?truth|参考答案|系统建议关注|高风险重点段落|真实冲突端点", re.I),
}
FORBIDDEN_HINT_PATTERN = re.compile(
    r"\b(?:direct_mutex|condition_trigger|handoff_invariant|temporal_gate|ground[-_ ]?truth)\b",
    re.I,
)
EXPECTED_MODELS = {"gpt-4o", "gemini-2.5-pro"}
EXPECTED_METHODS = {"lea", "sa-mcgs"}


def source_hash(title: str, text: str) -> str:
    encoded = json.dumps(
        {"title": title, "text": text},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--allow-incomplete-results",
        action="store_true",
        help="validate an honest preview pack while allowing methods with no available model",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    frontend = args.frontend.resolve()
    manifest_path = (args.manifest or frontend / "data" / "manifest.json").resolve()
    translation_path = frontend / "data" / "translations_zh.json"
    hint_path = frontend / "data" / "method_hints.json"
    errors: list[str] = []
    payload = None

    if not manifest_path.is_file():
        errors.append(f"missing manifest: {manifest_path}")
    else:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert_allowed_schema(payload)
        except Exception as error:
            errors.append(f"manifest rejected: {error}")

    translations = None
    hints = None
    for label, path, schema in (
        ("translation", translation_path, "annotation_translation.zh-CN.v1"),
        ("method hint", hint_path, "assisted_method_hints.v1"),
    ):
        if not path.is_file():
            errors.append(f"missing {label} pack: {path}")
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("schema_version") != schema:
                raise ValueError(f"unexpected schema {value.get('schema_version')!r}")
            if payload and value.get("source_manifest_hash") != payload.get("manifest_hash"):
                raise ValueError("source manifest hash mismatch")
            if label == "translation":
                translations = value
            else:
                hints = value
        except Exception as error:
            errors.append(f"{label} pack rejected: {error}")

    if payload and translations and hints:
        condition_counts: dict[str, int] = {}
        hint_cells = 0
        hint_statuses: Counter[str] = Counter()
        incomplete_method_sections: Counter[str] = Counter()
        for case in payload["cases"]:
            presentation_id = case["presentation_id"]
            translated_case = translations.get("cases", {}).get(presentation_id)
            hinted_case = hints.get("cases", {}).get(presentation_id)
            if not translated_case or not hinted_case:
                errors.append(f"missing assisted data for {presentation_id}")
                continue
            condition = hinted_case.get("condition")
            if condition not in {"pre", "post"}:
                errors.append(f"invalid condition for {presentation_id}: {condition!r}")
            else:
                condition_counts[condition] = condition_counts.get(condition, 0) + 1
            for section in case["sections"]:
                section_id = section["section_id"]
                translated = translated_case.get("sections", {}).get(section_id)
                hinted = hinted_case.get("sections", {}).get(section_id)
                if not translated or not hinted:
                    errors.append(f"missing assisted data for {presentation_id}/{section_id}")
                    continue
                if not translated.get("text_zh") and section.get("text"):
                    errors.append(f"empty Chinese text for {presentation_id}/{section_id}")
                expected_source_hash = source_hash(
                    str(section.get("title") or ""), str(section.get("text") or "")
                )
                if translated.get("source_hash") != expected_source_hash:
                    errors.append(
                        f"translation source hash mismatch for {presentation_id}/{section_id}"
                    )
                source_words = f"{section.get('title') or ''} {section.get('text') or ''}"
                translated_words = (
                    f"{translated.get('title_zh') or ''} {translated.get('text_zh') or ''}"
                )
                if (
                    len(source_words.strip()) > 20
                    and re.search(r"[A-Za-zÄÖÜäöüß]", source_words)
                    and not re.search(r"[\u4e00-\u9fff]", translated_words)
                ):
                    errors.append(
                        f"translation has no Chinese text for {presentation_id}/{section_id}"
                    )
                methods = hinted.get("methods", {})
                if set(methods) != EXPECTED_METHODS:
                    errors.append(f"method hints incomplete for {presentation_id}/{section_id}")
                    continue
                for method_name, method in methods.items():
                    models = method.get("models", {})
                    if set(models) != EXPECTED_MODELS:
                        errors.append(
                            f"model hints incomplete for {presentation_id}/{section_id}/{method_name}"
                        )
                        continue
                    if not any(
                        hint.get("status") == "available" for hint in models.values()
                    ):
                        incomplete_method_sections[method_name] += 1
                        if not args.allow_incomplete_results:
                            errors.append(
                                f"no available model hint for "
                                f"{presentation_id}/{section_id}/{method_name}"
                            )
                    for model_name, hint in models.items():
                        hint_cells += 1
                        status = str(hint.get("status") or "missing_status")
                        hint_statuses[status] += 1
                        if status not in {"available", "strict_invalid"}:
                            errors.append(
                                f"unavailable hint for {presentation_id}/{section_id}/"
                                f"{method_name}/{model_name}: {status!r}"
                            )
                            continue
                        if status == "available":
                            selected = hint.get("selected")
                            score = hint.get("score")
                            rank = hint.get("rank")
                            total_nodes = hint.get("total_nodes")
                            if not isinstance(selected, bool):
                                errors.append(
                                    f"available hint lacks boolean selected for "
                                    f"{presentation_id}/{section_id}/{method_name}/{model_name}"
                                )
                            if score is not None and (
                                not isinstance(score, (int, float))
                                or isinstance(score, bool)
                                or not math.isfinite(float(score))
                            ):
                                errors.append(
                                    f"available hint has invalid score for "
                                    f"{presentation_id}/{section_id}/{method_name}/{model_name}"
                                )
                            if (
                                not isinstance(rank, int)
                                or isinstance(rank, bool)
                                or not isinstance(total_nodes, int)
                                or isinstance(total_nodes, bool)
                                or total_nodes < 1
                                or rank < 1
                                or rank > total_nodes
                            ):
                                errors.append(
                                    f"available hint has invalid rank for "
                                    f"{presentation_id}/{section_id}/{method_name}/{model_name}"
                                )
                        else:
                            stale_fields = {
                                key
                                for key in ("selected", "score", "rank", "total_nodes", "top3")
                                if key in hint
                            }
                            if stale_fields:
                                errors.append(
                                    f"unavailable hint carries stale result fields for "
                                    f"{presentation_id}/{section_id}/{method_name}/{model_name}: "
                                    f"{sorted(stale_fields)}"
                                )
        if condition_counts != {"pre": 18, "post": 24}:
            errors.append(f"unexpected condition counts: {condition_counts}")
        if hint_cells != 648 * 4:
            errors.append(f"unexpected method/model hint cells: {hint_cells}")

        public_hint_text = json.dumps(hints, ensure_ascii=False)
        match = FORBIDDEN_HINT_PATTERN.search(public_hint_text)
        if match:
            errors.append(f"method hint pack leaks private label near {match.group(0)!r}")

    for relative in EXPERT_UI_FILES:
        path = frontend / relative
        if not path.is_file():
            errors.append(f"missing UI file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN_UI_PATTERNS.items():
            match = pattern.search(text)
            if match:
                errors.append(f"{relative}: {label} leak near {match.group(0)!r}")

    if errors:
        print("EXPERT PACK VALIDATION FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 2
    print("ASSISTED EXPERT PACK VALIDATION PASSED")
    print(f"- manifest: {manifest_path}")
    print("- Chinese translation coverage: passed")
    print("- LEA/SA-MCGS hint structure: passed")
    if payload and translations and hints:
        print(f"- hint statuses: {dict(sorted(hint_statuses.items()))}")
        if incomplete_method_sections:
            print(
                "- incomplete method/section cells allowed for preview: "
                f"{dict(sorted(incomplete_method_sections.items()))}"
            )
    print("- forbidden ground-truth/template scan: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

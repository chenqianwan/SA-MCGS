#!/usr/bin/env python3
"""Build an expert-safe annotation payload from an internal master manifest.

The builder intentionally emits an allow-listed public schema. Every original
identifier and experimental field stays in the private codebook.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Any


PUBLIC_SCHEMA = "blind_annotation.v1"
ALLOWED_TOP_LEVEL = {
    "schema_version",
    "study_id",
    "randomization_seed",
    "manifest_hash",
    "cases",
    "expert_orders",
}
ALLOWED_CASE_KEYS = {"presentation_id", "domain_label", "sections"}
ALLOWED_SECTION_KEYS = {"section_id", "title", "text"}

MATERIAL_PATH_KEYS = (
    "material_path",
    "material_json",
    "source_path",
    "source_material",
    "case_path",
    "json_path",
)

FORBIDDEN_FIELD_PARTS = {
    "condition",
    "template",
    "model",
    "root",
    "witness",
    "inject",
    "risk",
    "system",
    "groundtruth",
    "ground_truth",
    "sa_core",
    "lea",
    "naive",
    "oracle",
    "affected",
    "bridge",
    "oc_nodes",
    "source_case",
    "source_scc",
    "fingerprint",
}

FORBIDDEN_HINT_PATTERNS = (
    re.compile(r"\b(?:direct_mutex|condition_trigger|handoff_invariant|temporal_gate)\b", re.I),
    re.compile(r"\b(?:pre|post)[-_ ]?injection\b", re.I),
    re.compile(r"\b(?:gpt-?4o|gemini(?:-?2\.5)?|deepseek(?:-?v3)?|qwen(?:2\.5)?)\b", re.I),
    re.compile(r"\b(?:SA-MCGS|LEA)\b", re.I),
    re.compile(r"(?:系统建议关注|高风险重点段落|可能冲突段落|真实冲突端点|参考答案|ground[-_ ]?truth)", re.I),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", required=True, type=Path, help="Internal master manifest JSON")
    parser.add_argument("--out", required=True, type=Path, help="Public expert-safe manifest JSON")
    parser.add_argument("--codebook", required=True, type=Path, help="Private blind-ID codebook JSON")
    parser.add_argument("--study-id", default="arr_oct2026_expert_audit")
    parser.add_argument("--seed", default="arr-oct-2026-blind-order-v1")
    parser.add_argument("--allow-unselected", action="store_true", help="Include records explicitly marked selected=false")
    parser.add_argument("--allow-missing-action", action="store_true", help="Treat records without annotation_action as new annotations (fixtures only)")
    parser.add_argument("--min-source-gap", type=int, default=3, help="Minimum desired positions between presentations from the same source")
    parser.add_argument("--expected-current-round", type=int, help="Fail unless the public payload contains exactly this many presentations")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8")


def normalize_records(master: Any) -> list[dict[str, Any]]:
    if isinstance(master, list):
        records = master
    elif isinstance(master, dict):
        records = None
        for key in ("cases", "selected_cases", "presentations", "records", "items"):
            if isinstance(master.get(key), list):
                records = master[key]
                break
        if records is None:
            raise ValueError("Master manifest must contain a list under cases/selected_cases/presentations/records/items.")
    else:
        raise ValueError("Master manifest must be a JSON object or list.")
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("Every master-manifest record must be an object.")
    return records


def resolve_material(record: dict[str, Any], master_path: Path) -> tuple[dict[str, Any], str]:
    if isinstance(record.get("material"), dict):
        return record["material"], "<inline:material>"
    if any(isinstance(record.get(key), list) for key in ("full_nodes", "sections", "nodes", "clauses")):
        return record, "<inline:record>"
    path_value = next((record.get(key) for key in MATERIAL_PATH_KEYS if record.get(key)), None)
    if not path_value:
        raise ValueError("Record has neither inline material nor a supported material path field.")
    candidate = Path(str(path_value)).expanduser()
    if not candidate.is_absolute():
        candidate = (master_path.parent / candidate).resolve()
    if not candidate.is_file():
        raise FileNotFoundError(f"Material file not found: {candidate}")
    material = load_json(candidate)
    if not isinstance(material, dict):
        raise ValueError(f"Material must be a JSON object: {candidate}")
    return material, str(candidate)


def first_value(*values: Any, default: str = "") -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def original_case_id(record: dict[str, Any], material: dict[str, Any], index: int) -> str:
    metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
    return first_value(
        record.get("case_id"),
        record.get("source_case_id"),
        record.get("audit_post_id"),
        record.get("pre_source_id"),
        record.get("canonical_case_id"),
        record.get("id"),
        metadata.get("case_id"),
        material.get("case_id"),
        default=f"record_{index + 1:03d}",
    )


def public_id(seed: str, case_id: str, index: int) -> str:
    digest = hashlib.sha256(f"{seed}|{index}|{case_id}".encode("utf-8")).hexdigest()[:10].upper()
    return f"P-{digest}"


def domain_label(record: dict[str, Any], material: dict[str, Any]) -> str:
    metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
    raw = first_value(record.get("domain_label"), metadata.get("domain_label"), material.get("domain_label"))
    if raw:
        return raw
    domain = first_value(record.get("domain"), metadata.get("domain"), material.get("domain"), default="text")
    return {
        "sec_ex21": "公司披露",
        "bgb": "法律条文",
        "cuad": "合同条款",
        "debian": "软件依赖说明",
    }.get(domain.lower(), "文本材料")


def extract_nodes(material: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("full_nodes", "sections", "nodes", "clauses"):
        value = material.get(key)
        if isinstance(value, list) and value:
            if not all(isinstance(node, dict) for node in value):
                raise ValueError(f"Material field {key} must contain only objects.")
            return value
    raise ValueError("Material has no full_nodes/sections/nodes/clauses list.")


def sanitize_sections(nodes: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    sections: list[dict[str, str]] = []
    node_codebook: list[dict[str, str]] = []
    for index, node in enumerate(nodes, start=1):
        original_id = first_value(node.get("node_id"), node.get("section_id"), node.get("id"), default=f"node_{index}")
        title = first_value(node.get("title"), node.get("label"), default="")
        text = first_value(node.get("text_en"), node.get("text"), node.get("body"), node.get("content"), node.get("raw_text"), default="")
        if not text and title:
            text = title
        if not text:
            raise ValueError(f"Node {original_id!r} has no displayable text.")
        if title and text.startswith(title):
            remainder = text[len(title):].lstrip(" \t\r\n:：—-")
            if remainder:
                text = remainder
            else:
                # Preserve the only visible content, but avoid rendering it twice.
                title = ""
        section_id = f"S{index:03d}"
        sections.append({"section_id": section_id, "title": title, "text": text})
        node_codebook.append({"section_id": section_id, "original_node_id": original_id})
    return sections, node_codebook


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "", value.lower())


def assert_allowed_schema(payload: dict[str, Any]) -> None:
    extra_top = set(payload) - ALLOWED_TOP_LEVEL
    if extra_top:
        raise ValueError(f"Public payload contains non-allow-listed top-level fields: {sorted(extra_top)}")
    for item in payload.get("cases", []):
        extra_case = set(item) - ALLOWED_CASE_KEYS
        if extra_case:
            raise ValueError(f"Case {item.get('presentation_id')} contains non-allow-listed fields: {sorted(extra_case)}")
        for section in item.get("sections", []):
            extra_section = set(section) - ALLOWED_SECTION_KEYS
            if extra_section:
                raise ValueError(f"Section contains non-allow-listed fields: {sorted(extra_section)}")
    known_ids = {item["presentation_id"] for item in payload.get("cases", [])}
    orders = payload.get("expert_orders")
    if not isinstance(orders, dict) or set(orders) != {"expert_1", "expert_2", "expert_3"}:
        raise ValueError("expert_orders must contain exactly expert_1/expert_2/expert_3")
    for expert_id, order in orders.items():
        if not isinstance(order, list) or len(order) != len(known_ids) or set(order) != known_ids:
            raise ValueError(f"{expert_id} order is not a permutation of public presentation IDs")
    for path, value in walk(payload):
        if path:
            key = normalized_key(path[-1])
            if any(part in key for part in FORBIDDEN_FIELD_PARTS):
                raise ValueError(f"Forbidden expert-facing field at {'.'.join(path)}")
        if isinstance(value, str) and (not path or path[-1] not in {"text", "title"}):
            for pattern in FORBIDDEN_HINT_PATTERNS:
                if pattern.search(value):
                    raise ValueError(f"Forbidden expert-facing hint at {'.'.join(path)}: {pattern.pattern}")
    for item in payload.get("cases", []):
        for section in item["sections"]:
            # Natural document text may contain words such as "condition". We only
            # reject generator/model labels and explicit UI hints inside documents.
            for field in ("title", "text"):
                value = section[field]
                for pattern in FORBIDDEN_HINT_PATTERNS:
                    if pattern.search(value):
                        raise ValueError(
                            f"Document {item['presentation_id']} {section['section_id']} contains a forbidden generated hint: {pattern.pattern}"
                        )


def walk(value: Any, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, path + (str(index),))
    else:
        yield path, value


def source_fingerprint(record: dict[str, Any], case_id: str) -> str:
    return first_value(
        record.get("source_physical_fingerprint"),
        record.get("source_scc_fingerprint"),
        record.get("source_fingerprint"),
        default=f"unique:{case_id}",
    )


def annotation_action(record: dict[str, Any], allow_missing_action: bool) -> str:
    raw = first_value(record.get("annotation_action"), default="").lower()
    aliases = {
        "new_annotation": "annotate",
        "annotate": "annotate",
        "new": "annotate",
        "reuse_legacy_label": "reuse",
        "reuse": "reuse",
        "existing": "reuse",
    }
    if raw in aliases:
        return aliases[raw]
    if raw:
        raise ValueError(f"Unsupported annotation_action {raw!r}; use new_annotation or reuse_legacy_label.")
    if allow_missing_action:
        return "annotate"
    raise ValueError("Every selected record must explicitly set annotation_action=new_annotation or reuse_legacy_label.")


def spaced_order(
    items: list[dict[str, str]],
    seed: str,
    expert_id: str,
    min_source_gap: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    randomizer = random.Random(f"{seed}|{expert_id}")
    remaining = list(items)
    randomizer.shuffle(remaining)
    order: list[str] = []
    positions: dict[str, int] = {}
    violations: list[dict[str, Any]] = []
    while remaining:
        position = len(order)
        eligible = [
            item
            for item in remaining
            if item["source"] not in positions or position - positions[item["source"]] > min_source_gap
        ]
        if not eligible:
            # The constraint can be mathematically impossible for a high-multiplicity source.
            # Choose the source with the largest existing distance, but record it privately.
            best_distance = max(position - positions[item["source"]] for item in remaining)
            eligible = [item for item in remaining if position - positions[item["source"]] == best_distance]
        chosen = randomizer.choice(eligible)
        prior = positions.get(chosen["source"])
        if prior is not None and position - prior <= min_source_gap:
            violations.append({
                "presentation_id": chosen["presentation_id"],
                "source_fingerprint": chosen["source"],
                "previous_position": prior,
                "position": position,
                "gap": position - prior - 1,
            })
        order.append(chosen["presentation_id"])
        positions[chosen["source"]] = position
        remaining.remove(chosen)
    return order, violations


def build(
    master_path: Path,
    study_id: str,
    seed: str,
    allow_unselected: bool = False,
    allow_missing_action: bool = False,
    min_source_gap: int = 3,
    expected_current_round: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    master = load_json(master_path)
    if expected_current_round is None and isinstance(master, dict) and master.get("expected_current_round_presentations") is not None:
        expected_current_round = int(master["expected_current_round_presentations"])
    records = normalize_records(master)
    public_cases: list[dict[str, Any]] = []
    codebook_rows: list[dict[str, Any]] = []
    reusable_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    order_items: list[dict[str, str]] = []
    used_public_ids: set[str] = set()

    for index, record in enumerate(records):
        if record.get("selected") is False and not allow_unselected:
            skipped_rows.append(record)
            continue
        action = annotation_action(record, allow_missing_action)
        if action == "reuse":
            reusable_rows.append(record)
            continue
        material, material_path = resolve_material(record, master_path)
        case_id = original_case_id(record, material, index)
        presentation_id = first_value(record.get("presentation_id"), record.get("blind_id")) or public_id(seed, case_id, index)
        if presentation_id in used_public_ids:
            raise ValueError(f"Duplicate presentation ID: {presentation_id}")
        used_public_ids.add(presentation_id)
        sections, node_codebook = sanitize_sections(extract_nodes(material))
        public_cases.append({
            "presentation_id": presentation_id,
            "domain_label": domain_label(record, material),
            "sections": sections,
        })
        codebook_rows.append({
            "presentation_id": presentation_id,
            "original_case_id": case_id,
            "material_path": material_path,
            "master_record": record,
            "section_map": node_codebook,
        })
        order_items.append({
            "presentation_id": presentation_id,
            "source": source_fingerprint(record, case_id),
        })

    if not public_cases:
        raise ValueError("No selected cases were available to build.")

    random.Random(seed).shuffle(public_cases)
    expert_orders: dict[str, list[str]] = {}
    spacing_violations: dict[str, list[dict[str, Any]]] = {}
    for expert_id in ("expert_1", "expert_2", "expert_3"):
        order, violations = spaced_order(order_items, seed, expert_id, min_source_gap)
        expert_orders[expert_id] = order
        spacing_violations[expert_id] = violations
    if expected_current_round is not None and len(public_cases) != expected_current_round:
        raise ValueError(
            f"Expected {expected_current_round} current-round presentations, built {len(public_cases)} "
            f"({len(reusable_rows)} records marked for label reuse)."
        )
    payload: dict[str, Any] = {
        "schema_version": PUBLIC_SCHEMA,
        "study_id": study_id,
        "randomization_seed": hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16],
        "manifest_hash": "",
        "cases": public_cases,
        "expert_orders": expert_orders,
    }
    hash_input = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["manifest_hash"] = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    assert_allowed_schema(payload)

    codebook = {
        "schema_version": "blind_annotation.codebook.v1",
        "study_id": study_id,
        "manifest_hash": payload["manifest_hash"],
        "source_master": str(master_path.resolve()),
        "summary": {
            "master_records": len(records),
            "current_round_presentations": len(public_cases),
            "reused_legacy_presentations": len(reusable_rows),
            "skipped_unselected_records": len(skipped_rows),
            "minimum_requested_source_gap": min_source_gap,
            "spacing_violation_counts": {key: len(value) for key, value in spacing_violations.items()},
        },
        "records": codebook_rows,
        "reused_records": reusable_rows,
        "skipped_records": skipped_rows,
        "spacing_violations": spacing_violations,
    }
    return payload, codebook


def main() -> int:
    args = parse_args()
    try:
        payload, codebook = build(
            args.master.resolve(),
            args.study_id,
            args.seed,
            args.allow_unselected,
            args.allow_missing_action,
            args.min_source_gap,
            args.expected_current_round,
        )
        write_json(args.out, payload)
        write_json(args.codebook, codebook)
    except Exception as error:  # fail closed with a concise operator-facing message
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(f"Built {len(payload['cases'])} blinded presentations")
    print(f"Master records: {codebook['summary']['master_records']}")
    print(f"Legacy labels reused (not re-presented): {codebook['summary']['reused_legacy_presentations']}")
    print(f"Expert payload: {args.out}")
    print(f"Private codebook: {args.codebook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Combine frozen pre and post material manifests into one internal master file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def records(value: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        result = value
    elif isinstance(value, dict):
        result = next(
            (value[key] for key in ("cases", "materials", "records", "items") if isinstance(value.get(key), list)),
            None,
        )
        if result is None:
            raise ValueError(f"{label} has no cases/materials/records/items list")
    else:
        raise ValueError(f"{label} must be a JSON list or object")
    if not all(isinstance(item, dict) for item in result):
        raise ValueError(f"{label} contains a non-object record")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--post", required=True, type=Path)
    parser.add_argument("--pre", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    post = records(json.loads(args.post.read_text(encoding="utf-8")), "post manifest")
    pre = records(json.loads(args.pre.read_text(encoding="utf-8")), "pre manifest")
    actions = [str(item.get("annotation_action") or "") for item in post]
    if len(post) != 36 or actions.count("reuse_legacy_label") != 12 or actions.count("new_annotation") != 24:
        raise SystemExit(
            "Post manifest must contain 36 records: 12 reuse_legacy_label + 24 new_annotation; "
            f"got {len(post)}, {actions.count('reuse_legacy_label')}, {actions.count('new_annotation')}."
        )
    if len(pre) != 18 or any(item.get("annotation_action") != "new_annotation" for item in pre):
        raise SystemExit("Pre manifest must contain 18 records, all annotation_action=new_annotation.")
    payload = {
        "schema_version": "annotation_master.v1",
        "expected_master_records": 54,
        "expected_current_round_presentations": 42,
        "expected_reused_legacy_presentations": 12,
        "cases": pre + post,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Master total: {len(pre) + len(post)}")
    print("Current round: 42 (18 pre + 24 new post)")
    print("Reused, not re-presented: 12 post")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

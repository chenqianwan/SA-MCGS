#!/usr/bin/env python3
"""Create a temporary master manifest referencing the immutable old 12-case pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-pack", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    materials = sorted((args.old_pack / "materials").glob("*.json"))
    if len(materials) != 12:
        raise SystemExit(f"Expected 12 legacy materials, found {len(materials)}")
    payload = {
        "schema_version": "annotation_master.v1",
        "purpose": "frontend_compatibility_fixture_only",
        "cases": [
            {
                "selected": True,
                "annotation_action": "new_annotation",
                "material_path": str(path.resolve()),
                "legacy_reuse": True,
            }
            for path in materials
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} with {len(materials)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

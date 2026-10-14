#!/usr/bin/env python3
"""Create a minimal assisted-review zip from the validated frontend."""

from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path


ALLOWED_FILES = (
    "index.html",
    "styles.css",
    "app.js",
    "data/manifest.json",
    "data/translations_zh.json",
    "data/method_hints.json",
    "vendor/xlsx.full.min.js",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--allow-incomplete-results",
        action="store_true",
        help="package an explicitly incomplete preview after structural validation",
    )
    args = parser.parse_args()
    frontend = args.frontend.resolve()
    validator = Path(__file__).with_name("validate_expert_pack.py")
    validation_command = [
        sys.executable,
        str(validator),
        "--frontend",
        str(frontend),
    ]
    if args.allow_incomplete_results:
        validation_command.append("--allow-incomplete-results")
    subprocess.run(validation_command, check=True)
    missing = [relative for relative in ALLOWED_FILES if not (frontend / relative).is_file()]
    if missing:
        raise SystemExit(f"Missing distribution files: {missing}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in ALLOWED_FILES:
            archive.write(frontend / relative, arcname=f"expert_annotation/{relative}")
    print(f"Packaged {len(ALLOWED_FILES)} allow-listed files: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

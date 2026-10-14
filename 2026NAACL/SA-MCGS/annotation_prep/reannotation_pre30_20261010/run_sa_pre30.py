#!/usr/bin/env python3
"""SA runner for the frozen 30-source reannotation batch, using the original pre protocol.

No inference is performed with --validate-only or --dry-run. Actual runs require
the explicitly selected model and use their own new output directory.
"""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent.parent
FROZEN_SHA256 = "9ed68194c04e3b6d2999bdca30c135a0304275e7a9b3cbb5034e9fec9e6b9c7a"
sys.path.insert(0, str(PAPER / "experiments/sa_update"))
import run_pre_sa as sa


def main():
    if "--models" not in sys.argv:
        raise SystemExit("Choose --models explicitly; no model or paid API is selected implicitly.")
    if "--source-json" not in sys.argv:
        sys.argv += ["--source-json", str(HERE / "sources_30.json")]
    if "--output-dir" not in sys.argv:
        raise SystemExit("Use a fresh --output-dir under this reannotation batch.")
    args = sa.parse_args()
    if hashlib.sha256(args.source_json.read_bytes()).hexdigest() != FROZEN_SHA256:
        raise SystemExit("The 30-source frozen manifest has changed; refusing to run.")
    if HERE not in args.output_dir.parents:
        raise SystemExit("Output directory must be inside this reannotation batch.")
    # This is process-local configuration; no historical runner or source is edited.
    sa.pre.EXPECTED_SOURCE_COUNT = 30
    sa.pre.EXPECTED_DOMAIN_COUNTS = {"sec_ex21": 10, "bgb": 10, "cuad": 10}
    sources, _ = sa.pre.load_and_validate_sources(args.source_json)
    old = json.loads((HERE.parent / "candidates/pre_sources_18.json").read_text())
    assert sources[:18] == old
    asyncio.run(sa.run(args))


if __name__ == "__main__":
    main()

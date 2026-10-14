#!/usr/bin/env python3
"""Run the original pre-LEA protocol on an explicit scope of frozen pre30 sources.

The full 30-source manifest is validated before selection. The historical LEA
runner is reused without edits; --validate-only and --dry-run make no API calls.
Use distinct output directories for model groups and recovery attempts.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import fcntl
import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PAPER = HERE.parent.parent
FROZEN_SHA256 = "9ed68194c04e3b6d2999bdca30c135a0304275e7a9b3cbb5034e9fec9e6b9c7a"
MODELS = {"gpt-4o", "gemini-2.5-pro"}
sys.path.insert(0, str(PAPER / "experiments/lea_update"))
import run_pre_lea as lea


def parse_args():
    supplied = {value.split("=", 1)[0] for value in sys.argv[1:] if value.startswith("--")}
    if "--models" not in supplied:
        raise SystemExit("Choose --models explicitly; no model or paid API is selected implicitly.")
    if "--output-dir" not in supplied:
        raise SystemExit("Use an explicit --output-dir under this reannotation batch.")
    scope_parser = argparse.ArgumentParser(add_help=False)
    scope_parser.add_argument("--source-ids", nargs="+", default=None)
    scope, remaining = scope_parser.parse_known_args(sys.argv[1:])
    if "--source-json" not in supplied:
        remaining += ["--source-json", str(HERE / "sources_30.json")]
    original_argv = sys.argv
    try:
        sys.argv = [original_argv[0], *remaining]
        args = lea.parse_args()
    finally:
        sys.argv = original_argv
    args.source_ids = scope.source_ids
    if not args.models or len(args.models) != len(set(args.models)) or not set(args.models) <= MODELS:
        raise SystemExit("Use distinct historical model aliases: gpt-4o and/or gemini-2.5-pro.")
    if HERE not in args.output_dir.parents:
        raise SystemExit("Output directory must be inside this reannotation batch.")
    if args.rebuild_plan:
        raise SystemExit("Do not rebuild a frozen pre30 plan; use a new output directory.")
    if args.source_ids and len(args.source_ids) != len(set(args.source_ids)):
        raise SystemExit("--source-ids must not contain duplicates.")
    return args


def main():
    args = parse_args()
    if hashlib.sha256(args.source_json.read_bytes()).hexdigest() != FROZEN_SHA256:
        raise SystemExit("The 30-source frozen manifest has changed; refusing to run.")
    # These settings and the scoped loader are process-local only.
    lea.EXPECTED_SOURCE_COUNT = 30
    lea.EXPECTED_DOMAIN_COUNTS = {"sec_ex21": 10, "bgb": 10, "cuad": 10}
    sources, reconstructed = lea.load_and_validate_sources(args.source_json)
    old_sources = json.loads((HERE.parent / "candidates/pre_sources_18.json").read_text())
    if len(old_sources) != 18 or sources[:18] != old_sources:
        raise SystemExit("The historical 18 sources differ from the frozen manifest.")
    known = {source["pre_source_id"] for source in sources}
    selected_ids = set(args.source_ids or known)
    if selected_ids - known:
        raise SystemExit(f"Unknown --source-ids: {sorted(selected_ids - known)}")
    selected = [source for source in sources if source["pre_source_id"] in selected_ids]
    selected_graphs = {source["pre_source_id"]: reconstructed[source["pre_source_id"]] for source in selected}

    def load_selected(path):
        if path.resolve() != args.source_json or hashlib.sha256(path.read_bytes()).hexdigest() != FROZEN_SHA256:
            raise lea.PreSourceValidationError("The validated source manifest changed before execution.")
        return selected, selected_graphs

    lea.load_and_validate_sources = load_selected
    audit = {
        "schema_version": "pre30_lea_scope_v1", "source_json": str(args.source_json),
        "source_json_sha256": "sha256:" + FROZEN_SHA256,
        "full_manifest_validated_sources": 30,
        "full_manifest_validated_domains": {"sec_ex21": 10, "bgb": 10, "cuad": 10},
        "all_30_sources_exactly_one_tarjan_scc": True, "historical_18_unchanged": True,
        "selected_source_ids": [source["pre_source_id"] for source in selected],
        "selected_domains": dict(Counter(source["domain"] for source in selected)),
        "models": args.models, "method": "lea", "planned_model_cases": len(selected) * len(args.models),
        "condition": "pre", "inject_mode": False, "abstention_rule_version": lea.ABSTENTION_RULE_VERSION,
        "resolved_mcgs_config": lea.cost.make_mcgs_config(args),
        "llm_timeout": args.llm_timeout, "llm_max_retries": args.llm_max_retries,
        "runner_sha256": hashlib.sha256(Path(lea.__file__).read_bytes()).hexdigest(),
        "model_calls_made_by_manifest_validation": 0,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Resume is allowed, but two processes must never own the same output tree.
    with (args.output_dir / ".pre30_lea.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another pre30 LEA process owns this output directory.")
        audit_path = args.output_dir / "source_scope_audit.json"
        if audit_path.exists() and json.loads(audit_path.read_text()) != audit:
            raise SystemExit("Existing scope/protocol differs; use a new output directory.")
        lea.atomic_write_json(audit_path, audit)
        asyncio.run(lea.run(args))


if __name__ == "__main__":
    main()

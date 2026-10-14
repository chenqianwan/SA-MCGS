#!/usr/bin/env python3
"""Freeze the 173 missing LEA cells and verify inputs without API calls.

Only the four previously audited LEA batches are eligible for reuse. The
immutable 80-case catalog supplies stable identities; the locked main-results
manifest supplies each model's own source SA-MCGS artifact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
AUDIT_PATH = REPO_ROOT / "2026NAACL/SA-MCGS/annotation_prep/baseline_audit/audit_baseline_coverage.py"
MODELS = ("gpt-4o", "gemini-2.5-pro", "qwen2.5-72b", "deepseek-v3")
EXPECTED_MISSING = {"gpt-4o": 6, "gemini-2.5-pro": 7, "qwen2.5-72b": 80, "deepseek-v3": 80}
LEA_DIRS = (
    REPO_ROOT / "emnlp2026_discussion/baseline_runs/lea_available160_gpt4o_gemini_w4_cc4_20260712_0048/results",
    REPO_ROOT / "2026NAACL/SA-MCGS/experiments/lea_runs/lea_post_gpt12_20260829/results",
    REPO_ROOT / "2026NAACL/SA-MCGS/experiments/lea_runs/lea_post_gemini_smoke_20260829/results",
    REPO_ROOT / "2026NAACL/SA-MCGS/experiments/lea_runs/lea_post_gemini_remaining10_20260829/results",
)
CSV_FIELDS = [
    "model", "domain", "scc_id", "scc_size", "template", "root", "witness", "bridge",
    "affected_count", "llm_calls", "time", "result_file", "main_case_order",
    "main_case_id", "stable_case_uid", "physical_scc_uid", "planned_scc_fingerprint",
    "source_result_sha256", "source_sa_record_sha256", "missing_reason",
]


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-preflight", action="store_true", help="Build files only; normally leave unset.")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("lea_identity_audit", AUDIT_PATH)
    audit = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(audit)
    catalog = audit.load_catalog(audit.DEFAULT_PLAN, audit.DEFAULT_REPLAY)
    assert len(catalog) == 80 and len({case["case_uid"] for case in catalog}) == 80
    indexes = audit.catalog_indexes(catalog)
    main_coverage = audit.load_main_coverage(audit.DEFAULT_MAIN_MANIFEST, indexes["key"])
    lea_coverage = audit.load_lea_coverage(LEA_DIRS, indexes["key"])
    sys.path.insert(0, str(REPO_ROOT))
    from emnlp2026_discussion import run_lea_full_baseline as runner
    cost = runner.cost
    missing, reused, coverage = [], [], []
    for model in MODELS:
        for planned in sorted(catalog, key=lambda row: row["case_order"]):
            key = (planned["domain"], int(planned["scc_size"]), planned["template"], model)
            source = main_coverage[(*key, "sa-mcgs")]
            assert source["identity_exact"], (key, source)
            source_path = Path(source["source_file"]).resolve()
            payload = audit.read_json(source_path)
            matching = [row for row in payload if row.get("method") == "sa-mcgs" and row.get("model") == model]
            assert len(matching) == 1, (source_path, model)
            source_row = matching[0]
            assert audit.validate_identity(source_row, planned)[0]
            previous = lea_coverage.get((*key, "lea"))
            identity = {
                "model": model,
                "domain": planned["domain"],
                "scc_size": planned["scc_size"],
                "template": planned["template"],
                "main_case_order": planned["case_order"],
                "main_case_id": planned["case_id"],
                "stable_case_uid": planned["case_uid"],
                "physical_scc_uid": planned["source_physical_uid"],
                "planned_scc_fingerprint": planned["planned_scc_fingerprint"],
                "planned_scc_clause_ids": planned["planned_scc_clause_ids"],
                "planned_injection_identity": planned["planned_injection_identity"],
                "source_result_file": str(source_path),
                "source_result_sha256": digest(source_path),
                "source_sa_record_sha256": cost._canonical_hash(source_row),
            }
            assert identity["physical_scc_uid"], key
            if previous and previous["identity_exact"]:
                path = Path(previous["source_file"]).resolve()
                item = {
                    **identity,
                    "status": "reused_exact",
                    "lea_result_file": str(path),
                    "lea_result_sha256": digest(path),
                    "strict_invalid_output": previous["strict_invalid_output"],
                }
                reused.append(item)
                coverage.append(item)
                continue
            reason = "identity_mismatch" if previous else "missing"
            item = {
                **identity,
                "status": "pending",
                "missing_reason": reason,
                "previous_lea_result_file": str(Path(previous["source_file"]).resolve()) if previous else None,
                "previous_identity_detail": previous["identity_detail"] if previous else None,
            }
            row = {
                **item,
                "scc_id": source_row["scc_id"],
                "root": source_row.get("injected_node") or "",
                "witness": source_row.get("injected_witness_node") or "",
                "bridge": source_row.get("injected_bridge_node") or "",
                "affected_count": len(source_row.get("injected_affected_nodes") or []),
                "llm_calls": source_row.get("llm_calls") or 0,
                "time": source_row.get("time") or 0.0,
                "result_file": str(source_path),
            }
            missing.append(row)
            coverage.append(item)
    counts = dict(Counter(row["model"] for row in missing))
    assert counts == EXPECTED_MISSING, counts
    assert len(reused) == 147 and len(coverage) == 320
    full_csv = HERE / "missing_cases.csv"
    write_csv(full_csv, missing, CSV_FIELDS)
    outputs = {full_csv.name: digest(full_csv)}
    for model in MODELS:
        path = HERE / f"missing_cases_{model}.csv"
        write_csv(path, [row for row in missing if row["model"] == model], CSV_FIELDS)
        outputs[path.name] = digest(path)
    write_csv(HERE / "coverage_before.csv", coverage, [
        "model", "domain", "scc_size", "template", "main_case_order", "main_case_id",
        "stable_case_uid", "physical_scc_uid", "status", "missing_reason",
        "lea_result_file", "previous_lea_result_file", "source_result_file",
    ])
    preflight = None
    if not args.skip_preflight:
        directory = HERE / "preflight"
        runner_args = SimpleNamespace(
            case_csv=full_csv, models=list(MODELS), limit=None, rebuild_plan=True,
        )
        plan = runner.build_or_load_case_plan(runner_args, directory)
        assert len(plan) == len(missing)
        for case, frozen in zip(plan, missing):
            cost.hydrate_case_from_source(case)
            assert case["planned_scc_clause_ids"] == frozen["planned_scc_clause_ids"]
            assert case["planned_injection_identity"] == frozen["planned_injection_identity"]
            case.update({
                "main_case_order": frozen["main_case_order"],
                "main_case_id": frozen["main_case_id"],
                "stable_case_uid": frozen["stable_case_uid"],
                "physical_scc_uid": frozen["physical_scc_uid"],
                "case_uid": frozen["stable_case_uid"],
                "planned_scc_fingerprint": frozen["planned_scc_fingerprint"],
            })
            frozen["runner_case_id"] = case["case_id"]
            frozen["runner_case_order"] = case["case_order"]
        graphs = cost.load_graphs(plan)
        preflight = cost.validate_case_plan(plan, graphs)
        # Exercise injection replay as well as source/graph identity matching.
        for case in plan:
            cost.prepare_injected_case(case, graphs)
        cost.persist_case_plan(directory, plan)
        preflight.update({"api_calls": 0, "source": str(full_csv), "csv_sha256": digest(full_csv)})
        write_json(directory / "case_identity_preflight.json", preflight)
    frozen_manifest = {
        "scope_version": "lea_full320_completion_20260923_v1",
        "budget_limit_usd": 50,
        "api_calls_by_manifest_builder": 0,
        "target_case_count": 80,
        "target_model_case_pairs": 320,
        "reused_count": len(reused),
        "missing_count": len(missing),
        "missing_by_model": counts,
        "models": list(MODELS),
        "policy": "Reuse only exact stable identities from the four vetted batches. Keep valid strict invalid outcomes. Rerun only missing or identity-mismatched cells. Numeric Tarjan IDs are diagnostic only.",
        "inputs": [{"path": str(path), "sha256": digest(path)} for path in (AUDIT_PATH, audit.DEFAULT_PLAN, audit.DEFAULT_REPLAY, audit.DEFAULT_MAIN_MANIFEST)],
        "approved_lea_result_directories": [str(path) for path in LEA_DIRS],
        "outputs_sha256": outputs,
        "preflight": {"validated_cases": preflight["validated_cases"], "api_calls": 0, "directory": str(HERE / "preflight")} if preflight else None,
        "jobs": missing,
        "reused": reused,
    }
    write_json(HERE / "frozen_manifest.json", frozen_manifest)
    lines = [
        "# LEA coverage before completion", "",
        "Frozen scope: the same 80 stable cases on all four original models (320 cells).",
        "Only the four audited legacy/repair batches are eligible for reuse. No cost-audit or exploratory runs are imported.", "",
        "| Model | Exact reuse | Missing | Identity repairs | Total to run |", "|---|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        selected = [row for row in missing if row["model"] == model]
        lines.append(f"| {model} | {80-len(selected)} | {sum(row['missing_reason']=='missing' for row in selected)} | {sum(row['missing_reason']=='identity_mismatch' for row in selected)} | {len(selected)} |")
    lines += [
        "| Total | 147 | 160 | 13 | 173 |", "",
        "The input CSVs use each model's original SA result and resolve every source path to this checkout. Stable physical SCC IDs, ordered clause IDs, injection identities, graph fingerprints, source hashes, and original case orders are frozen in `frozen_manifest.json`.", "",
        "Preflight rebuilds the runner plan from the CSV, validates every source and graph identity, and replays each injection without calling any API.",
        f"Preflight status: {'passed for 173 cases; API calls = 0' if preflight else 'not run' }.", "",
        "Rebuild: `python3 2026NAACL/SA-MCGS/experiments/lea_full320_completion_20260923/build_manifest.py`", "",
        "The paid experiment must use the separate budget-controlled runner. The user authorized a total ceiling of USD 50 for this completion batch.", "",
    ]
    (HERE / "COVERAGE_BEFORE.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"reused": len(reused), "missing": counts, "preflight_cases": preflight["validated_cases"] if preflight else None, "api_calls": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

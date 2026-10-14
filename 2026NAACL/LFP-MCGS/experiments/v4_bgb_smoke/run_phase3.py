#!/usr/bin/env python3
"""Run the Phase-3 oracle-outcome search smoke on frozen Phase-1 cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from search_core import (
    CLAIM_BOUNDARY,
    EVIDENCE_STATUS,
    OUTCOME_MODEL,
    SearchCase,
    SourcedFact,
    exact_lfp,
    load_cases,
    run_method,
)


SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parent
DEFAULT_RESULTS = ROOT / "results"
DEFAULT_METHODS = ("direct", "greedy", "beam", "tree", "graph")
DEFAULT_SIZES = (3, 5, 7, 9)
DEFAULT_SEEDS = (17,)


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl_atomic(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_csv_ints(raw: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in raw.split(",") if item.strip())


def parse_csv_strings(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def discover_cases() -> Path | None:
    candidates = (
        ROOT / "data" / "cases.jsonl",
        ROOT / "data" / "benchmark.jsonl",
        ROOT / "data" / "phase1_cases.jsonl",
        ROOT / "data" / "controlled_cases.jsonl",
        ROOT / "cases.jsonl",
    )
    return next((path for path in candidates if path.exists()), None)


def oracle_audit(case: SearchCase) -> dict[str, Any]:
    facts = []
    rules = []
    for source in case.sources:
        facts.extend(SourcedFact(atom, source.source_id) for atom in source.formal_outcome.facts)
        rules.extend(source.formal_outcome.rules)
    closure, provenance = exact_lfp(facts, rules)
    entails = case.query_atom in closure
    proof_sources: tuple[str, ...] = tuple()
    for atom, proof_sets in provenance:
        if atom == case.query_atom.text and proof_sets:
            proof_sources = min(proof_sets, key=lambda item: (len(item), item))
            break
    expected = "entailed" if entails else "unknown"

    reachable = {case.root_source_id}
    frontier = [case.root_source_id]
    while frontier:
        source_id = frontier.pop()
        for target in case.adjacency.get(source_id, tuple()):
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    reachable_facts = []
    reachable_rules = []
    for source in case.sources:
        if source.source_id not in reachable:
            continue
        reachable_facts.extend(SourcedFact(atom, source.source_id) for atom in source.formal_outcome.facts)
        reachable_rules.extend(source.formal_outcome.rules)
    reachable_closure, _ = exact_lfp(reachable_facts, reachable_rules)
    reachable_label = "entailed" if case.query_atom in reachable_closure else "unknown"
    return {
        "case_id": case.case_id,
        "oracle_entails": entails,
        "oracle_label": expected,
        "declared_gold_label": case.gold_label,
        "label_consistent": case.gold_label in (None, expected),
        "root_reachable_sources": sorted(reachable),
        "root_reachable_source_count": len(reachable),
        "root_reachable_oracle_label": reachable_label,
        "root_reachable_label_consistent": case.gold_label in (None, reachable_label),
        "execution_feasible_under_local_actions": case.gold_label in (None, reachable_label),
        "oracle_minimum_proof_sources": list(proof_sources),
        "declared_gold_proof_sources": list(case.gold_proof_sources),
        "proof_sources_consistent": (
            set(proof_sources) == set(case.gold_proof_sources)
            if entails and case.gold_proof_sources
            else None
        ),
        "full_closure": sorted(atom.text for atom in closure),
    }


def select_cases(
    cases: Sequence[SearchCase],
    sizes: Sequence[int],
    conditions: Sequence[str],
    per_size_condition: int,
) -> tuple[list[SearchCase], dict[str, Any]]:
    wanted_sizes = set(sizes)
    wanted_conditions = {value.lower() for value in conditions}
    buckets: dict[tuple[int | None, str], list[SearchCase]] = defaultdict(list)
    for case in sorted(cases, key=lambda value: value.case_id):
        if wanted_sizes and case.scc_size not in wanted_sizes:
            continue
        if wanted_conditions and case.condition.lower() not in wanted_conditions:
            continue
        buckets[(case.scc_size, case.condition)].append(case)
    selected: list[SearchCase] = []
    for key in sorted(buckets, key=lambda item: (item[0] or -1, item[1])):
        selected.extend(buckets[key][:per_size_condition])
    coverage = {
        "requested_sizes": list(sizes),
        "available_sizes": sorted({case.scc_size for case in cases if case.scc_size is not None}),
        "selected_sizes": sorted({case.scc_size for case in selected if case.scc_size is not None}),
        "missing_requested_sizes": sorted(wanted_sizes - {case.scc_size for case in selected}),
        "available_conditions": sorted({case.condition for case in cases}),
        "selected_case_count": len(selected),
        "per_size_condition_cap": per_size_condition,
    }
    return selected, coverage


def ledger_gate(trial: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    metrics = trial["metrics"]
    caps = trial["caps"]
    events = trial["ledger"]
    real_events = [event for event in events if event["phase"] == "real"]
    simulated_events = [event for event in events if event["phase"] != "real"]
    reveal_events = [event for event in events if event["oracle_reveal"]]
    if len(real_events) != metrics["real_transitions"]:
        reasons.append("real transition counter differs from ledger")
    if len(simulated_events) != metrics["simulated_transitions"]:
        reasons.append("simulated transition counter differs from ledger")
    if len(reveal_events) != metrics["total_charged_reads"]:
        reasons.append("oracle reveals differ from charged reads")
    if metrics["real_transitions"] > caps["real_action_cap"]:
        reasons.append("real action cap exceeded")
    if metrics["simulated_transitions"] > caps["simulation_transition_cap"]:
        reasons.append("simulation transition cap exceeded")
    if any(event["remaining_budget_after"] < 0 for event in events):
        reasons.append("negative branch budget")
    return not reasons, reasons


def summarise(
    trials: Sequence[Mapping[str, Any]],
    coverage: Mapping[str, Any],
    audits: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_method: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for trial in trials:
        by_method[str(trial["method"])].append(trial)
    method_rows = []
    for method, rows in sorted(by_method.items()):
        labelled = [row for row in rows if row["label_correct"] is not None]
        feasible = [row for row in labelled if row["case_execution_feasible"]]
        feasible_positive = [row for row in feasible if row["gold_label"] == "entailed"]
        method_rows.append(
            {
                "method": method,
                "trials": len(rows),
                "proof_recovery_rate": sum(bool(row["proof_recovered"]) for row in rows) / len(rows),
                "label_accuracy_all_cases": (
                    sum(bool(row["label_correct"]) for row in labelled) / len(labelled) if labelled else None
                ),
                "label_accuracy_feasible_cases": (
                    sum(bool(row["label_correct"]) for row in feasible) / len(feasible) if feasible else None
                ),
                "feasible_positive_proof_recovery_rate": (
                    sum(bool(row["proof_recovered"]) for row in feasible_positive) / len(feasible_positive)
                    if feasible_positive
                    else None
                ),
                "mean_real_reads": statistics.fmean(row["metrics"]["real_reads"] for row in rows),
                "mean_total_charged_reads": statistics.fmean(
                    row["metrics"]["total_charged_reads"] for row in rows
                ),
                "mean_total_charged_transitions": statistics.fmean(
                    row["metrics"]["total_charged_transitions"] for row in rows
                ),
                "total_nodes": sum(row["metrics"]["nodes"] for row in rows),
                "total_tt_hits": sum(row["metrics"]["tt_hits"] for row in rows),
            }
        )

    slice_rows = []
    slice_groups: dict[tuple[str, str, int | None], list[Mapping[str, Any]]] = defaultdict(list)
    for trial in trials:
        slice_groups[(str(trial["method"]), str(trial["condition"]), trial["scc_size"])].append(trial)
    for (method, condition, size), rows in sorted(
        slice_groups.items(), key=lambda item: (item[0][0], item[0][1], item[0][2] or -1)
    ):
        slice_rows.append(
            {
                "method": method,
                "condition": condition,
                "scc_size": size,
                "trials": len(rows),
                "case_execution_feasible": all(row["case_execution_feasible"] for row in rows),
                "proof_recovery_rate": sum(bool(row["proof_recovered"]) for row in rows) / len(rows),
                "label_accuracy": sum(bool(row["label_correct"]) for row in rows) / len(rows),
                "mean_total_charged_transitions": statistics.fmean(
                    row["metrics"]["total_charged_transitions"] for row in rows
                ),
                "total_nodes": sum(row["metrics"]["nodes"] for row in rows),
                "total_tt_hits": sum(row["metrics"]["tt_hits"] for row in rows),
            }
        )

    tree = next((row for row in method_rows if row["method"].startswith("TreePUCT")), None)
    graph = next((row for row in method_rows if row["method"].startswith("GraphPUCT")), None)
    graph_advantage_observed = None
    exact_merge_mechanism_observed = None
    node_reduction_fraction = None
    if tree and graph:
        graph_advantage_observed = (
            graph["feasible_positive_proof_recovery_rate"]
            > tree["feasible_positive_proof_recovery_rate"]
            or (
                graph["feasible_positive_proof_recovery_rate"]
                == tree["feasible_positive_proof_recovery_rate"]
                and graph["mean_total_charged_transitions"] < tree["mean_total_charged_transitions"]
            )
        )
        exact_merge_mechanism_observed = (
            graph["total_tt_hits"] > 0 and graph["total_nodes"] < tree["total_nodes"]
        )
        if tree["total_nodes"]:
            node_reduction_fraction = 1.0 - graph["total_nodes"] / tree["total_nodes"]
    ledger_gates_ok = all(bool(row.get("ledger_gate_pass")) for row in trials)
    case_gate_failures = [
        str(audit["case_id"])
        for audit in audits
        if not bool(audit["execution_feasible_under_local_actions"])
    ]
    case_gates_ok = not case_gate_failures
    overall_ok = bool(trials) and ledger_gates_ok and case_gates_ok
    return {
        "evidence_status": EVIDENCE_STATUS,
        "outcome_model": OUTCOME_MODEL,
        "claim_boundary": CLAIM_BOUNDARY,
        "pipeline_smoke_status": "PASS" if overall_ok else "FAIL",
        "runner_execution_status": "PASS" if trials and ledger_gates_ok else "FAIL",
        "case_execution_gate_status": "PASS" if case_gates_ok else "FAIL",
        "case_execution_gate_failures": case_gate_failures,
        "pipeline_smoke_interpretation": (
            "Runner PASS means the methods executed with auditable charges. Overall PASS also "
            "requires every declared label to be attainable from the frozen root under local actions; "
            "neither status means GraphPUCT won."
        ),
        "coverage": dict(coverage),
        "method_results": method_rows,
        "slice_results": slice_rows,
        "exact_merge_mechanism_observed": exact_merge_mechanism_observed,
        "graph_node_reduction_fraction_vs_tree": node_reduction_fraction,
        "merge_mechanism_interpretation": (
            "TT hits and fewer allocated nodes establish only that exact transposition sharing fired. "
            "They are not proof-recovery, token, latency, or algorithmic-advantage evidence."
        ),
        "graph_advantage_observed_in_this_smoke": graph_advantage_observed,
        "advantage_claim_status": (
            "NOT_ESTABLISHED_BY_SMOKE"
            if not graph_advantage_observed
            else "OBSERVED_DIAGNOSTIC_ONLY_NOT_CONFIRMATORY"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, help="Frozen Phase-1 JSON/JSONL cases")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--sizes", default=",".join(map(str, DEFAULT_SIZES)))
    parser.add_argument("--conditions", default="", help="Optional comma-separated condition filter")
    parser.add_argument("--methods", default=",".join(DEFAULT_METHODS))
    parser.add_argument("--seeds", default=",".join(map(str, DEFAULT_SEEDS)))
    parser.add_argument("--per-size-condition", type=int, default=1)
    parser.add_argument("--action-cap", type=int, default=0, help="0 uses each case's frozen cap")
    parser.add_argument("--simulation-transition-cap", type=int, default=256)
    parser.add_argument("--simulations-per-move", type=int, default=16)
    parser.add_argument("--beam-width", type=int, default=4)
    parser.add_argument("--beam-depth", type=int, default=4)
    parser.add_argument(
        "--require-all-sizes",
        action="store_true",
        help="Exit non-zero if a requested SCC size is absent",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    case_path = args.cases.resolve() if args.cases else discover_cases()
    if case_path is None or not case_path.exists():
        print(
            "Phase-1 case JSONL is not present yet. Pass --cases or create data/cases.jsonl.",
            file=sys.stderr,
        )
        return 2

    sizes = parse_csv_ints(args.sizes)
    conditions = parse_csv_strings(args.conditions)
    methods = parse_csv_strings(args.methods)
    seeds = parse_csv_ints(args.seeds)
    cases = load_cases(case_path)
    selected, coverage = select_cases(cases, sizes, conditions, args.per_size_condition)
    if not selected:
        print("No cases match the requested smoke slice.", file=sys.stderr)
        return 2
    if args.require_all_sizes and coverage["missing_requested_sizes"]:
        print(f"Missing requested sizes: {coverage['missing_requested_sizes']}", file=sys.stderr)
        return 2

    audits = [oracle_audit(case) for case in selected]
    inconsistent = [audit["case_id"] for audit in audits if not audit["label_consistent"]]
    if inconsistent:
        print(f"Gold/oracle label mismatch: {inconsistent}", file=sys.stderr)
        return 3

    trials: list[dict[str, Any]] = []
    audit_by_case = {str(audit["case_id"]): audit for audit in audits}
    for case in selected:
        for seed in seeds:
            for method in methods:
                trial = run_method(
                    case,
                    method,
                    seed,
                    action_cap=args.action_cap or None,
                    simulation_transition_cap=args.simulation_transition_cap,
                    simulations_per_move=args.simulations_per_move,
                    beam_width=args.beam_width,
                    beam_depth=args.beam_depth,
                )
                passed, reasons = ledger_gate(trial)
                trial["ledger_gate_pass"] = passed
                trial["ledger_gate_failures"] = reasons
                trial["case_execution_feasible"] = bool(
                    audit_by_case[case.case_id]["execution_feasible_under_local_actions"]
                )
                trials.append(trial)

    summary = summarise(trials, coverage, audits)
    results_dir = args.results_dir.resolve()
    trial_path = results_dir / "phase3_trials.jsonl"
    summary_path = results_dir / "phase3_summary.json"
    audit_path = results_dir / "phase3_oracle_audit.json"
    manifest_path = results_dir / "phase3_manifest.json"
    write_jsonl_atomic(trial_path, trials)
    write_json_atomic(summary_path, summary)
    write_json_atomic(audit_path, audits)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evidence_status": EVIDENCE_STATUS,
        "outcome_model": OUTCOME_MODEL,
        "claim_boundary": CLAIM_BOUNDARY,
        "input": {
            "path": str(case_path),
            "sha256": sha256_file(case_path),
            "total_cases": len(cases),
            "selected_case_ids": [case.case_id for case in selected],
        },
        "code": {
            "runner_path": str(SCRIPT_PATH),
            "runner_sha256": sha256_file(SCRIPT_PATH),
            "search_core_path": str(ROOT / "search_core.py"),
            "search_core_sha256": sha256_file(ROOT / "search_core.py"),
        },
        "configuration": {
            "sizes": list(sizes),
            "conditions": list(conditions),
            "methods": list(methods),
            "seeds": list(seeds),
            "per_size_condition": args.per_size_condition,
            "action_cap_override": args.action_cap or None,
            "simulation_transition_cap": args.simulation_transition_cap,
            "simulations_per_move": args.simulations_per_move,
            "beam_width": args.beam_width,
            "beam_depth": args.beam_depth,
        },
        "fairness_contract": {
            "physical_local_actions_only": True,
            "formal_outcome_visible_only_after_read": True,
            "discarded_branch_reads_are_charged": True,
            "real_action_cap_shared": True,
            "tree_graph_only_switch": "exact transposition sharing",
            "merge_key_fields": [
                "location",
                "committed_program",
                "closure",
                "provenance",
                "coverage",
                "action_mask",
                "remaining_budget",
            ],
        },
        "coverage": coverage,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "outputs": {
            "trials": str(trial_path),
            "summary": str(summary_path),
            "oracle_audit": str(audit_path),
        },
    }
    write_json_atomic(manifest_path, manifest)

    print(json.dumps({
        "pipeline_smoke_status": summary["pipeline_smoke_status"],
        "runner_execution_status": summary["runner_execution_status"],
        "case_execution_gate_status": summary["case_execution_gate_status"],
        "case_execution_gate_failures": summary["case_execution_gate_failures"],
        "advantage_claim_status": summary["advantage_claim_status"],
        "selected_cases": len(selected),
        "trials": len(trials),
        "sizes": coverage["selected_sizes"],
        "missing_sizes": coverage["missing_requested_sizes"],
        "summary": str(summary_path),
    }, ensure_ascii=False, indent=2))
    return 0 if summary["pipeline_smoke_status"] == "PASS" else 4


if __name__ == "__main__":
    raise SystemExit(main())

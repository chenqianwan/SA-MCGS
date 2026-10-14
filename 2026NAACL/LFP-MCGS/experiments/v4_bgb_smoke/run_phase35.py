#!/usr/bin/env python3
"""Exploratory Phase-3.5 scaling smoke over every frozen BGB carrier.

The grid below is deliberately frozen in source before inspecting its results.
Every cell is retained.  This is an oracle-outcome mechanism/cost census, not a
confirmatory comparison and not an LLM parsing result.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import platform
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from run_phase3 import ledger_gate, oracle_audit, sha256_file, write_json_atomic, write_jsonl_atomic
from search_core import CLAIM_BOUNDARY, EVIDENCE_STATUS, OUTCOME_MODEL, SearchCase, load_cases, run_method


SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parent
DEFAULT_CASES = ROOT / "data" / "cases.jsonl"
DEFAULT_RESULTS = ROOT / "results"
EXPECTED_CASES_SHA256 = "42053a8f891f21ca2499909f7760656b04aed9cef7fb36ff5e53d94f5b5a3c78"
PHASE = "exploratory_phase_3_5_scaling_smoke"
SIZES = (3, 5, 7, 9, 11, 25)
CONDITIONS = ("Productive", "Decoy", "Broken", "Clean", "Matched-DAG")
METHODS = ("greedy", "beam", "tree", "graph")
SEEDS = (17, 29, 43)


@dataclass(frozen=True)
class Intensity:
    intensity_id: str
    simulation_transition_cap: int
    simulations_per_move: int

    def as_json(self) -> dict[str, Any]:
        return {
            "intensity_id": self.intensity_id,
            "simulation_transition_cap": self.simulation_transition_cap,
            "simulations_per_move": self.simulations_per_move,
            "beam_width": 4,
            "beam_depth": 4,
        }


# Frozen before the final Phase-3.5 run.  Search intensity is varied independently
# of the real-action budget; Beam width/depth remain fixed so a positive cell
# cannot be attributed to changing both branching geometry and compute.
INTENSITIES = (
    Intensity("low", 64, 4),
    Intensity("mid", 256, 16),
    Intensity("high", 1024, 64),
)


@dataclass(frozen=True)
class RealBudget:
    budget_id: str

    def reference_cost(self, case: SearchCase) -> int:
        navigation = case.raw_metadata.get("navigation_contract", {})
        if not isinstance(navigation, Mapping):
            raise ValueError(f"{case.case_id}: missing navigation contract")
        value = navigation.get("reference_route_total_action_cost")
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"{case.case_id}: invalid reference-route cost {value!r}")
        return value

    def action_cap(self, case: SearchCase) -> int:
        if self.budget_id == "tight":
            return min(case.action_budget, max(1, math.ceil(1.25 * self.reference_cost(case))))
        if self.budget_id == "standard":
            return case.action_budget
        raise ValueError(f"unknown real budget {self.budget_id!r}")

    def as_json(self) -> dict[str, Any]:
        return {
            "budget_id": self.budget_id,
            "definition": (
                "ceil(1.25 * frozen reference-route move+read cost)"
                if self.budget_id == "tight"
                else "frozen case action budget"
            ),
        }


REAL_BUDGETS = (RealBudget("tight"), RealBudget("standard"))

SCOPE_LIMITATIONS = (
    "One lexicographically selected carrier per size; no population inference.",
    "Exactly three injected proof sources at every size and the root is the seed source.",
    "The injected Horn chain is acyclic and two-rule; this is navigation scaling, not recursive-LFP scaling.",
    "Controlled marker and symbolic notation remain visible; this is not natural-language difficulty.",
    "Seeds test tie sensitivity only and are not independent benchmark examples.",
)

CLAIM_BOUNDARY_35 = (
    f"{CLAIM_BOUNDARY} Phase 3.5 is an exhaustive exploratory grid over the frozen "
    "BGB smoke carriers. It may identify opportunities or failures, but no cell or "
    "subset is a confirmatory superiority claim."
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(*parts: Any) -> str:
    return hashlib.sha256("|".join(canonical_json(part) for part in parts).encode()).hexdigest()[:16]


def write_jsonl_gzip_atomic(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as raw_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as compressed:
            for row in rows:
                compressed.write((canonical_json(row) + "\n").encode("utf-8"))
    temporary.replace(path)


def _reachable(adjacency: Mapping[str, Sequence[str]], start: str) -> set[str]:
    reached = {start}
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for target in adjacency.get(node, tuple()):
            if target not in reached:
                reached.add(target)
                frontier.append(target)
    return reached


def is_strongly_connected(case: SearchCase) -> bool:
    nodes = set(case.source_ids)
    if _reachable(case.adjacency, case.root_source_id) != nodes:
        return False
    reverse: dict[str, list[str]] = {node: [] for node in nodes}
    for source, targets in case.adjacency.items():
        for target in targets:
            reverse[target].append(source)
    return _reachable(reverse, case.root_source_id) == nodes


def move_only_opportunity(case: SearchCase, max_depth: int | None = None) -> dict[str, Any]:
    """Count strict equal-depth, no-read state collisions before running search.

    With no reads, program/provenance/coverage stay empty.  Two distinct move
    paths ending at the same node at the same depth therefore have an identical
    strict state key (including remaining budget).  Counts are capped to avoid
    integer explosion; this remains an opportunity census, not expected TT hits.
    """

    depth_cap = min(case.action_budget, max_depth or case.action_budget)
    paths: dict[str, int] = {case.root_source_id: 1}
    rows = []
    total_collisions = 0
    for depth in range(1, depth_cap + 1):
        next_paths: dict[str, int] = defaultdict(int)
        for source, count in paths.items():
            for target in case.adjacency.get(source, tuple()):
                next_paths[target] = min(1_000_000, next_paths[target] + count)
        collision_keys = {node: count for node, count in next_paths.items() if count > 1}
        collisions = sum(count - 1 for count in collision_keys.values())
        total_collisions += collisions
        rows.append(
            {
                "depth": depth,
                "reachable_move_only_states": len(next_paths),
                "strict_collision_key_count": len(collision_keys),
                "duplicate_move_paths": collisions,
            }
        )
        paths = dict(next_paths)
        if not paths:
            break
    indegree = defaultdict(int)
    edge_count = 0
    for targets in case.adjacency.values():
        edge_count += len(targets)
        for target in targets:
            indegree[target] += 1
    return {
        "case_id": case.case_id,
        "condition": case.condition,
        "scc_size": case.scc_size,
        "node_count": len(case.sources),
        "edge_count": edge_count,
        "is_strongly_connected": is_strongly_connected(case),
        "root_reachable_source_count": len(_reachable(case.adjacency, case.root_source_id)),
        "convergent_node_count": sum(value > 1 for value in indegree.values()),
        "move_only_depth_cap": depth_cap,
        "strict_move_only_duplicate_paths": total_collisions,
        "by_depth": rows,
        "interpretation": (
            "A positive count proves that strict transposition states exist for no-read move paths. "
            "It does not predict useful committed-KB merges or an accuracy/cost win."
        ),
    }


def select_all_cases(cases: Sequence[SearchCase]) -> list[SearchCase]:
    wanted = {(size, condition) for size in SIZES for condition in CONDITIONS}
    buckets: dict[tuple[int | None, str], list[SearchCase]] = defaultdict(list)
    for case in cases:
        buckets[(case.scc_size, case.condition)].append(case)
    missing = sorted(wanted - set(buckets), key=lambda item: (item[0], item[1]))
    duplicates = {key: rows for key, rows in buckets.items() if key in wanted and len(rows) != 1}
    if missing or duplicates:
        raise ValueError(
            f"Phase-3.5 requires exactly one case per size/condition; missing={missing}, "
            f"non_singletons={{{', '.join(f'{key}:{len(rows)}' for key, rows in duplicates.items())}}}"
        )
    return [buckets[(size, condition)][0] for size in SIZES for condition in CONDITIONS]


def compact_trial(trial: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in trial.items() if key != "ledger"}


def mean(rows: Sequence[Mapping[str, Any]], path: Sequence[str]) -> float:
    values = []
    for row in rows:
        value: Any = row
        for key in path:
            value = value[key]
        values.append(float(value))
    return statistics.fmean(values)


def aggregate_cells(trials: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in trials:
        groups[
            (
                row["budget_id"],
                row["intensity_id"],
                row["condition"],
                int(row["scc_size"]),
                row["method"],
            )
        ].append(row)
    output = []
    for (budget_id, intensity_id, condition, size, method), rows in sorted(groups.items()):
        output.append(
            {
                "budget_id": budget_id,
                "intensity_id": intensity_id,
                "grid_id": f"{budget_id}__{intensity_id}",
                "condition": condition,
                "scc_size": size,
                "method": method,
                "trials": len(rows),
                "proof_recovery_rate": mean(rows, ("proof_recovered",)),
                "label_accuracy": mean(rows, ("label_correct",)),
                "mean_real_reads": mean(rows, ("metrics", "real_reads")),
                "mean_total_charged_reads": mean(rows, ("metrics", "total_charged_reads")),
                "mean_real_transitions": mean(rows, ("metrics", "real_transitions")),
                "mean_total_charged_transitions": mean(rows, ("metrics", "total_charged_transitions")),
                "mean_nodes": mean(rows, ("metrics", "nodes")),
                "total_tt_hits": int(sum(row["metrics"]["tt_hits"] for row in rows)),
                "negative_false_entailments": sum(
                    row["gold_label"] == "unknown" and bool(row["proof_recovered"]) for row in rows
                ),
            }
        )
    return output


def paired_comparisons(cell_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    indexed = {
        (
            row["budget_id"],
            row["intensity_id"],
            row["condition"],
            row["scc_size"],
            row["method"],
        ): row
        for row in cell_rows
    }
    output = []
    for budget in REAL_BUDGETS:
        for intensity in INTENSITIES:
            for condition in CONDITIONS:
                for size in SIZES:
                    key = (budget.budget_id, intensity.intensity_id, condition, size)
                    graph = indexed[(*key, "GraphPUCT (exact merge)")]
                    for baseline_name in ("TreePUCT (no merge)", "Beam", "Surface Greedy"):
                        baseline = indexed[(*key, baseline_name)]
                        node_reduction = None
                        if baseline_name == "TreePUCT (no merge)" and baseline["mean_nodes"]:
                            node_reduction = 1.0 - graph["mean_nodes"] / baseline["mean_nodes"]
                        output.append(
                            {
                                "budget_id": budget.budget_id,
                                "intensity_id": intensity.intensity_id,
                                "grid_id": f"{budget.budget_id}__{intensity.intensity_id}",
                                "condition": condition,
                                "scc_size": size,
                                "comparison": f"GraphPUCT - {baseline_name}",
                                "proof_recovery_rate_delta": (
                                    graph["proof_recovery_rate"] - baseline["proof_recovery_rate"]
                                ),
                                "label_accuracy_delta": graph["label_accuracy"] - baseline["label_accuracy"],
                                "mean_total_charged_reads_delta": (
                                    graph["mean_total_charged_reads"]
                                    - baseline["mean_total_charged_reads"]
                                ),
                                "mean_total_charged_transitions_delta": (
                                    graph["mean_total_charged_transitions"]
                                    - baseline["mean_total_charged_transitions"]
                                ),
                                "graph_tt_hits": graph["total_tt_hits"],
                                "graph_node_reduction_fraction_vs_tree": node_reduction,
                            }
                        )
    return output


def method_overall(trials: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in trials:
        groups[(row["budget_id"], row["intensity_id"], row["method"])].append(row)
    output = []
    for (budget_id, intensity_id, method), rows in sorted(groups.items()):
        positives = [row for row in rows if row["gold_label"] == "entailed"]
        negatives = [row for row in rows if row["gold_label"] == "unknown"]
        output.append(
            {
                "budget_id": budget_id,
                "intensity_id": intensity_id,
                "grid_id": f"{budget_id}__{intensity_id}",
                "method": method,
                "trials": len(rows),
                "positive_trials": len(positives),
                "negative_trials": len(negatives),
                "positive_proof_recovery_rate": mean(positives, ("proof_recovered",)),
                "negative_false_entailment_rate": mean(negatives, ("proof_recovered",)),
                "label_accuracy": mean(rows, ("label_correct",)),
                "mean_total_charged_reads": mean(rows, ("metrics", "total_charged_reads")),
                "mean_total_charged_transitions": mean(
                    rows, ("metrics", "total_charged_transitions")
                ),
                "total_nodes": int(sum(row["metrics"]["nodes"] for row in rows)),
                "total_tt_hits": int(sum(row["metrics"]["tt_hits"] for row in rows)),
            }
        )
    return output


def exploratory_candidate_windows(
    comparisons: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Retain only pre-declared repeated PUCT-vs-simple-controller signals.

    A candidate needs a positive proof-recovery delta in at least two of the
    three frozen search intensities.  This is a discovery flag, not a claim.
    Graph and Tree are interpreted together whenever their recovery is tied.
    """

    groups: dict[tuple[str, str, int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in comparisons:
        if row["condition"] not in {"Productive", "Matched-DAG"}:
            continue
        if row["comparison"] not in {
            "GraphPUCT - Beam",
            "GraphPUCT - Surface Greedy",
        }:
            continue
        groups[
            (row["budget_id"], row["condition"], int(row["scc_size"]), row["comparison"])
        ].append(row)
    output = []
    for (budget_id, condition, size, comparison), rows in sorted(groups.items()):
        positive = [row for row in rows if row["proof_recovery_rate_delta"] > 0]
        if len(positive) < 2:
            continue
        output.append(
            {
                "budget_id": budget_id,
                "condition": condition,
                "scc_size": size,
                "comparison": comparison,
                "positive_intensity_count": len(positive),
                "positive_intensities": sorted(row["intensity_id"] for row in positive),
                "all_intensity_deltas": {
                    row["intensity_id"]: row["proof_recovery_rate_delta"]
                    for row in sorted(rows, key=lambda value: value["intensity_id"])
                },
                "interpretation": (
                    "Exploratory controller window only. It must replicate on multiple carriers and "
                    "marker-free inputs; it does not establish MCGS because Graph and Tree recovery tie."
                ),
            }
        )
    return output


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument(
        "--allow-input-hash-mismatch",
        action="store_true",
        help="Diagnostic only; the mismatch is still written as a failed gate.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    case_path = args.cases.resolve()
    results_dir = args.results_dir.resolve()
    actual_hash = sha256_file(case_path)
    hash_ok = actual_hash == EXPECTED_CASES_SHA256
    if not hash_ok and not args.allow_input_hash_mismatch:
        print(
            f"Frozen case hash mismatch: expected {EXPECTED_CASES_SHA256}, got {actual_hash}",
            file=sys.stderr,
        )
        return 2

    cases = load_cases(case_path)
    selected = select_all_cases(cases)
    audits = [oracle_audit(case) for case in selected]
    case_gate_failures = [
        audit["case_id"] for audit in audits if not audit["execution_feasible_under_local_actions"]
    ]
    opportunity = [move_only_opportunity(case) for case in selected]

    trials: list[dict[str, Any]] = []
    ledgers: list[dict[str, Any]] = []
    audit_by_case = {audit["case_id"]: audit for audit in audits}
    for budget in REAL_BUDGETS:
        for intensity in INTENSITIES:
            for case in selected:
                action_cap = budget.action_cap(case)
                reference_cost = budget.reference_cost(case)
                for seed in SEEDS:
                    for method in METHODS:
                        trial = run_method(
                            case,
                            method,
                            seed,
                            action_cap=action_cap,
                            simulation_transition_cap=intensity.simulation_transition_cap,
                            simulations_per_move=intensity.simulations_per_move,
                            beam_width=4,
                            beam_depth=4,
                        )
                        passed, failures = ledger_gate(trial)
                        cell_id = stable_id(
                            PHASE,
                            budget.budget_id,
                            intensity.intensity_id,
                            case.case_id,
                            seed,
                            trial["method"],
                        )
                        trial.update(
                            {
                                "phase": PHASE,
                                "cell_id": cell_id,
                                "budget_id": budget.budget_id,
                                "intensity_id": intensity.intensity_id,
                                "grid_id": f"{budget.budget_id}__{intensity.intensity_id}",
                                "reference_route_total_action_cost": reference_cost,
                                "proof_source_ratio": 3 / len(case.sources),
                                "frozen_case_action_budget": case.action_budget,
                                "effective_real_action_cap": action_cap,
                                "case_execution_feasible": bool(
                                    audit_by_case[case.case_id]["execution_feasible_under_local_actions"]
                                ),
                                "ledger_gate_pass": passed,
                                "ledger_gate_failures": failures,
                            }
                        )
                        ledgers.append(
                            {
                                "cell_id": cell_id,
                                "budget_id": budget.budget_id,
                                "intensity_id": intensity.intensity_id,
                                "grid_id": f"{budget.budget_id}__{intensity.intensity_id}",
                                "case_id": case.case_id,
                                "condition": case.condition,
                                "scc_size": case.scc_size,
                                "method": trial["method"],
                                "seed": seed,
                                "ledger": trial["ledger"],
                            }
                        )
                        trials.append(compact_trial(trial))

    expected_cells = (
        len(REAL_BUDGETS) * len(INTENSITIES) * len(selected) * len(SEEDS) * len(METHODS)
    )
    unique_cells = len({trial["cell_id"] for trial in trials})
    ledger_failures = [trial["cell_id"] for trial in trials if not trial["ledger_gate_pass"]]
    false_entailments = [
        trial["cell_id"]
        for trial in trials
        if trial["gold_label"] == "unknown" and trial["proof_recovered"]
    ]
    cell_rows = aggregate_cells(trials)
    comparisons = paired_comparisons(cell_rows)
    overall = method_overall(trials)
    candidate_windows = exploratory_candidate_windows(comparisons)
    graph_tree = [row for row in comparisons if row["comparison"] == "GraphPUCT - TreePUCT (no merge)"]
    graph_tree_proof_wins = sum(row["proof_recovery_rate_delta"] > 0 for row in graph_tree)
    graph_tree_proof_losses = sum(row["proof_recovery_rate_delta"] < 0 for row in graph_tree)
    graph_tree_proof_ties = sum(row["proof_recovery_rate_delta"] == 0 for row in graph_tree)
    positive_tt_slices = sum(row["graph_tt_hits"] > 0 for row in graph_tree)
    all_gates_pass = (
        hash_ok
        and not case_gate_failures
        and len(trials) == expected_cells
        and unique_cells == expected_cells
        and len(ledgers) == expected_cells
        and not ledger_failures
        and not false_entailments
    )

    trials_path = results_dir / "phase35_trials.jsonl"
    ledgers_path = results_dir / "phase35_ledgers.jsonl.gz"
    summary_path = results_dir / "phase35_summary.json"
    manifest_path = results_dir / "phase35_manifest.json"
    audit_path = results_dir / "phase35_case_audit.json"
    census_path = results_dir / "phase35_opportunity_census.json"
    write_jsonl_atomic(trials_path, trials)
    write_jsonl_gzip_atomic(ledgers_path, ledgers)
    write_json_atomic(audit_path, audits)
    write_json_atomic(census_path, opportunity)

    summary = {
        "phase": PHASE,
        "evidence_status": EVIDENCE_STATUS,
        "outcome_model": OUTCOME_MODEL,
        "claim_boundary": CLAIM_BOUNDARY_35,
        "status": "PASS" if all_gates_pass else "FAIL",
        "gates": {
            "frozen_input_hash_matches": hash_ok,
            "all_case_execution_gates_pass": not case_gate_failures,
            "expected_cell_count": expected_cells,
            "actual_cell_count": len(trials),
            "unique_cell_count": unique_cells,
            "all_ledgers_present": len(ledgers) == expected_cells,
            "all_ledger_gates_pass": not ledger_failures,
            "negative_false_entailments_zero": not false_entailments,
            "case_gate_failures": case_gate_failures,
            "ledger_gate_failures": ledger_failures,
            "negative_false_entailment_cells": false_entailments,
        },
        "real_budgets": [budget.as_json() for budget in REAL_BUDGETS],
        "search_intensities": [intensity.as_json() for intensity in INTENSITIES],
        "coverage": {
            "sizes": list(SIZES),
            "conditions": list(CONDITIONS),
            "methods": list(METHODS),
            "seeds": list(SEEDS),
            "cases": len(selected),
            "cells": len(trials),
        },
        "method_overall": overall,
        "by_size_condition_grid": cell_rows,
        "paired_graph_comparisons": comparisons,
        "exploratory_candidate_windows": candidate_windows,
        "graph_tree_census": {
            "paired_slices": len(graph_tree),
            "proof_wins": graph_tree_proof_wins,
            "proof_losses": graph_tree_proof_losses,
            "proof_ties": graph_tree_proof_ties,
            "slices_with_positive_graph_tt_hits": positive_tt_slices,
            "interpretation": (
                "All slices are retained. Proof wins/losses are exploratory; TT hits/node reduction "
                "show sharing mechanics only and do not establish token or accuracy advantage."
            ),
        },
        "advantage_claim_status": "EXPLORATORY_ONLY_NOT_ESTABLISHED",
        "scope_limitations": list(SCOPE_LIMITATIONS),
    }
    write_json_atomic(summary_path, summary)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phase": PHASE,
        "status": summary["status"],
        "claim_boundary": CLAIM_BOUNDARY_35,
        "pre_registered_in_source_grid": {
            "real_budgets": [budget.as_json() for budget in REAL_BUDGETS],
            "search_intensities": [intensity.as_json() for intensity in INTENSITIES],
            "cross_product": True,
        },
        "input": {
            "path": str(case_path),
            "expected_sha256": EXPECTED_CASES_SHA256,
            "actual_sha256": actual_hash,
            "hash_matches": hash_ok,
            "selected_case_ids": [case.case_id for case in selected],
        },
        "code": {
            "runner_path": str(SCRIPT_PATH),
            "runner_sha256": sha256_file(SCRIPT_PATH),
            "search_core_path": str(ROOT / "search_core.py"),
            "search_core_sha256": sha256_file(ROOT / "search_core.py"),
        },
        "fixed_design": {
            "sizes": list(SIZES),
            "conditions": list(CONDITIONS),
            "methods": list(METHODS),
            "seeds": list(SEEDS),
            "real_budgets": [budget.budget_id for budget in REAL_BUDGETS],
            "search_intensities": [intensity.intensity_id for intensity in INTENSITIES],
            "expected_cells": expected_cells,
            "post_hoc_cell_filtering": False,
            "beam_width": 4,
            "beam_depth": 4,
            "scope_limitations": list(SCOPE_LIMITATIONS),
        },
        "fairness_contract": {
            "same_physical_local_move_read_access": True,
            "same_exact_lfp_and_terminal_proof_endpoint": True,
            "same_oracle_outcome_reveal_protocol": True,
            "all_real_and_hypothetical_reads_charged": True,
            "same_grid_caps_within_each_case_method_seed_cell": True,
            "tree_graph_only_switch": "strict exact transposition sharing",
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
        "gates": summary["gates"],
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "outputs": {
            "compact_trials": str(trials_path),
            "full_ledgers_gzip": str(ledgers_path),
            "summary": str(summary_path),
            "case_audit": str(audit_path),
            "opportunity_census": str(census_path),
        },
    }
    write_json_atomic(manifest_path, manifest)
    print(
        json.dumps(
            {
                "phase": PHASE,
                "status": summary["status"],
                "cases": len(selected),
                "cells": len(trials),
                "ledger_failures": len(ledger_failures),
                "false_entailments": len(false_entailments),
                "graph_tree_proof_wins_losses_ties": [
                    graph_tree_proof_wins,
                    graph_tree_proof_losses,
                    graph_tree_proof_ties,
                ],
                "summary": str(summary_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_gates_pass else 4


if __name__ == "__main__":
    raise SystemExit(main())

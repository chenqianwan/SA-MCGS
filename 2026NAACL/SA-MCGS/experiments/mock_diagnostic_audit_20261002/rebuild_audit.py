#!/usr/bin/env python3
"""Rebuild the historical mock diagnostic audit from frozen saved runs.

Standard library only. No model calls, network access, or simulation reruns.
The saved summaries are distinguished from metrics recomputed from trajectories.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean

BASE = Path(__file__).resolve().parent
METHODS = ("tree_mcts", "sa_mcgs")
TOPOLOGIES = ("dag", "simple_cycle", "compound_cycle")
SCALES = ("S", "M", "L")
HOP_CAP = 30


def json_text(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def csv_text(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def aggregate(runs, topology, method, scale="all"):
    tree = method == "tree_mcts"
    n = len(runs)
    steps = [v for run in runs for v in run["rollout_steps_history"]] if tree else []
    nodes = mean(run["graph_size"] for run in runs)
    state_mean = mean(run["tree_node_count"] for run in runs) if tree else None
    return {
        "topology": topology, "method": method, "scale": scale, "n_runs": n,
        "n_iterations": sum(run["actual_iterations"] for run in runs),
        "mean_physical_nodes": nodes,
        "mean_allocated_tree_nodes": state_mean,
        "mean_tree_node_ratio": mean(run["tree_node_count"] / run["graph_size"] for run in runs) if tree else None,
        "ratio_of_mean_tree_nodes_to_mean_physical_nodes": state_mean / nodes if tree else None,
        "depth_cap_reached_count": sum(v == HOP_CAP + 1 for v in steps) if tree else None,
        "n_random_walks": len(steps) if tree else None,
        "depth_cap_reached_pct": 100 * sum(v == HOP_CAP + 1 for v in steps) / len(steps) if tree else None,
        "mean_rollout_path_nodes": mean(steps) if tree else None,
        "mean_logged_cycle_revisit_pct": 100 * mean(run["rollout_hit_cycle_rate"] for run in runs) if tree else None,
        "mean_saved_positive_node_q_range": mean(run["q_spread"] for run in runs),
        "hit_at_3_count": sum(run["hit_top3"] for run in runs),
        "hit_at_3_pct": 100 * sum(run["hit_top3"] for run in runs) / n,
    }


def build():
    source = BASE / "source_frozen_runs.json"
    data = json.loads(source.read_text())
    assert len(data) == 90, "Expected 90 historical runs"
    keys = [(r["method"], r["topology"], r["scale"], r["repeat"]) for r in data]
    assert len(set(keys)) == 90
    counts = Counter((r["method"], r["topology"], r["scale"]) for r in data)
    assert len(counts) == 18 and set(counts.values()) == {5}
    data.sort(key=lambda r: (TOPOLOGIES.index(r["topology"]), METHODS.index(r["method"]), SCALES.index(r["scale"]), r["repeat"]))
    rows = []
    for i, run in enumerate(data, 1):
        tree = run["method"] == "tree_mcts"
        assert run["max_iterations"] == run["actual_iterations"] == 100
        assert len(run["tree_size_history"]) == len(run["rollout_steps_history"]) == 100
        assert all(len(v) == 100 for v in run["q_history_anomaly"].values())
        assert len(run["q_history_anomaly"]) == 1
        assert run["hit_top3"] == (run["target_rank"] is not None and run["target_rank"] <= 3)
        assert 0 <= run["q_spread"] <= 1
        assert run["tree_size_history"][-1] == run["tree_node_count"]
        assert math.isclose(mean(run["rollout_steps_history"]), run["avg_rollout_steps"], abs_tol=1e-12)
        assert all(a <= b for a, b in zip(run["tree_size_history"], run["tree_size_history"][1:]))
        if tree:
            assert all(1 <= v <= 31 for v in run["rollout_steps_history"])
        else:
            assert run["tree_node_count"] == 0
            assert set(run["rollout_steps_history"]) == {0}
        cap_n = sum(v == 31 for v in run["rollout_steps_history"]) if tree else None
        rows.append({
            "audit_run_id": f"mock_{i:03d}", "method": run["method"],
            "topology": run["topology"], "scale": run["scale"],
            "repeat_index": run["repeat"], "recorded_seed": run["seed"],
            "physical_node_count": run["graph_size"],
            "scc_sizes": ";".join(map(str, run["scc_sizes"])),
            "iterations": run["actual_iterations"],
            "allocated_tree_node_count": run["tree_node_count"] if tree else None,
            "allocated_tree_node_ratio": run["tree_node_count"] / run["graph_size"] if tree else None,
            "depth_cap_reached_count": cap_n, "n_random_walks": 100 if tree else None,
            "depth_cap_reached_rate": cap_n / 100 if tree else None,
            "mean_rollout_path_nodes": run["avg_rollout_steps"] if tree else None,
            "logged_cycle_revisit_rate": run["rollout_hit_cycle_rate"] if tree else None,
            "saved_positive_node_q_range": run["q_spread"],
            "saved_anomaly_rank": run["target_rank"], "saved_hit_at_3": int(run["hit_top3"]),
            "q_range_recomputed_from_full_node_values": False,
            "rank_recomputed_from_full_node_values": False,
        })
    summary = [aggregate([r for r in data if r["topology"] == t and r["method"] == m], t, m)
               for t in TOPOLOGIES for m in METHODS]
    by_scale = [aggregate([r for r in data if r["topology"] == t and r["method"] == m and r["scale"] == s], t, m, s)
                for t in TOPOLOGIES for m in METHODS for s in SCALES]
    pooled = [aggregate([r for r in data if r["topology"] != "dag" and r["method"] == m], "simple_plus_compound", m) for m in METHODS]
    seed_lookup = {(r["method"], r["topology"], r["scale"], r["repeat"]): r["seed"] for r in data}
    matching_seed_cells = sum(seed_lookup[("tree_mcts", t, s, k)] == seed_lookup[("sa_mcgs", t, s, k)]
                              for t in TOPOLOGIES for s in SCALES for k in range(5))
    checks = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_run_count": 90, "complete_cells": 18, "runs_per_cell": 5,
        "all_90_runs_pass_history_and_saved_hit_consistency": True,
        "cross_method_matching_recorded_seed_cells_out_of_45": matching_seed_cells,
        "no_full_final_q_vectors_in_saved_source": all("final_q_values" not in r for r in data),
        "no_rollout_terminal_flags_in_saved_source": True,
        "precise_terminal_conditioned_truncation_reconstructible": False,
        "complete_historical_mock_execution_reconstructible": False,
        "supports_reaggregation_of_saved_q_range_and_hit": True,
        "supports_recomputation_of_tree_ratio_and_depth_cap_reached": True,
        "supports_paired_identical_graph_method_comparison": False,
        "new_simulation_or_model_calls": 0,
        "notes": [
            "Q range and rank are saved metrics: aggregate arithmetic is reproduced, but final node Q vectors were not retained.",
            "A path of 31 nodes has consumed 30 transitions. An endpoint terminal flag is absent; report depth-cap reached, not exact terminal-conditioned truncation.",
            "The two methods have different seeds in all 45 topology/scale/repeat cells. They share topology families and iteration counts, not identical realized graphs or equal evaluator-call budgets.",
            "The current source uses Python hash() for configuration seeds and set iteration in selection/evaluation; the historical hash seed and code/runtime snapshot are unavailable.",
            "The saved SA method is a simplified SCC-biased window-search/TT proxy, not the full paper implementation.",
        ],
    }
    evidence = {
        "status": "reaggregated_saved_diagnostic_with_explicit_provenance_limits",
        "analysis_unit": "historical synthetic mock run, not a document SCC or model-case",
        "summary_by_topology": summary, "summary_by_scale": by_scale,
        "pooled_cycles_for_legacy_trace_only": pooled,
        "checks": checks,
    }
    names = {"dag": "DAG", "simple_cycle": "Simple cycle", "compound_cycle": "Compound cycles"}
    tex = ["% Generated by rebuild_audit.py; historical synthetic mock runs only.",
           r"\begin{table*}[t]", r"\centering\small", r"\begin{tabular}{llrrrrr}", r"\toprule",
           r"Method & Topology & $n$ & Tree-node ratio & Cap reached (\%) & Node Q range & Hit@3 (\%) \\", r"\midrule"]
    md = ["| Method | Topology | n | Tree-node ratio | Depth cap reached | Saved node Q range | Saved Hit@3 |",
          "|---|---|---:|---:|---:|---:|---:|"]
    for row in summary:
        tree = row["method"] == "tree_mcts"
        method = "TreeMCTS" if tree else "SCC-window proxy"
        ratio = f'{row["mean_tree_node_ratio"]:.2f}' if tree else "--"
        cap = f'{row["depth_cap_reached_pct"]:.2f}' if tree else "--"
        tex.append(f'{method} & {names[row["topology"]]} & 15 & {ratio} & {cap} & {row["mean_saved_positive_node_q_range"]:.3f} & {row["hit_at_3_pct"]:.2f} ' + r"\\")
        md.append(f'| {method} | {names[row["topology"]]} | 15 | {ratio} | {cap} | {row["mean_saved_positive_node_q_range"]:.3f} | {row["hit_at_3_count"]}/15 ({row["hit_at_3_pct"]:.2f}%) |')
    tex += [r"\bottomrule", r"\end{tabular}",
            r"\caption{Historical synthetic mock diagnostic, with five runs at each of three scales per row. Methods share topology families and 100 iterations, but use different seeds and evaluator budgets. Tree-node ratio is the per-run allocated tree-node count divided by physical graph size, averaged across runs. Cap reached counts random-walk paths with 30 transitions; exact terminal-conditioned truncation is unavailable. The SCC-window proxy has no search tree or random-walk rollouts (dashes). Node Q range and anomaly Hit@3 are reaggregated saved metrics; final node Q vectors were not archived. This proxy is not the full SA-MCGS implementation.}",
            r"\label{tab:mock_audit_reconstructed}", r"\end{table*}"]
    return {
        "per_run_sanitized.csv": csv_text(rows), "summary_by_topology.csv": csv_text(summary),
        "summary_by_scale.csv": csv_text(by_scale), "summary.json": json_text(evidence),
        "audit_checks.json": json_text(checks), "table_same_cohort.tex": "\n".join(tex) + "\n",
        "table_same_cohort.md": "\n".join(md) + "\n",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Compare reconstructed outputs with files on disk without rewriting")
    args = parser.parse_args()
    outputs = build()
    if args.verify:
        errors = [name for name, text in outputs.items() if not (BASE / name).exists() or (BASE / name).read_text() != text]
        if errors:
            raise SystemExit("Mismatch: " + ", ".join(errors))
        print(f"Verified {len(outputs)} deterministic outputs from 90 frozen mock runs; no model calls.")
    else:
        for name, text in outputs.items():
            (BASE / name).write_text(text)
        print(f"Wrote {len(outputs)} deterministic outputs from 90 frozen mock runs; no model calls.")


if __name__ == "__main__":
    main()

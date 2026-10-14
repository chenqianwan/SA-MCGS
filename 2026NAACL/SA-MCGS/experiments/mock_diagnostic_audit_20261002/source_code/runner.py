"""Ablation 1 Runner: True Tree-Based MCTS vs SA-MCGS.

Demonstrates three failure modes of standard MCTS on cyclic graphs:
  1. Search tree explosion (same graph node → many tree nodes)
  2. Rollout waste (trapped in cycles → depth-limit truncation)
  3. Q-value dilution & oscillation (inconsistent backprop)

Usage:
    python -m experiments.ablation1_cycle.runner [--parallel N]
"""
from __future__ import annotations

import json
import math
import time
import random
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from experiments.ablation1_cycle.graph_generator import (
    generate_compound_cycles,
    generate_dag,
    generate_simple_cycle,
)
from experiments.ablation1_cycle.mock_llm import MockEvaluator
from experiments.ablation1_cycle.search_methods import (
    SA_MCGS,
    SearchResult,
    TreeMCTS,
)


METHODS = {
    "tree_mcts": TreeMCTS,
    "sa_mcgs": SA_MCGS,
}

SCALES = {
    "S": {"dag_n": 10, "cycle_size": 5, "compound_sccs": [3, 4], "window": 3},
    "M": {"dag_n": 25, "cycle_size": 12, "compound_sccs": [5, 7, 5], "window": 4},
    "L": {"dag_n": 60, "cycle_size": 25, "compound_sccs": [10, 12, 8], "window": 5},
}

MAX_ITERATIONS = 100
REPEATS = 5


def run_single_experiment(
    method_name: str,
    topology: str,
    scale: str,
    repeat_idx: int,
    seed: int,
) -> dict:
    """Run a single experiment configuration."""
    random.seed(seed)

    scale_cfg = SCALES[scale]

    if topology == "dag":
        graph = generate_dag(n=scale_cfg["dag_n"])
    elif topology == "simple_cycle":
        graph = generate_simple_cycle(
            cycle_size=scale_cfg["cycle_size"],
            dag_prefix=3,
            dag_suffix=2,
        )
    elif topology == "compound_cycle":
        graph = generate_compound_cycles(
            scc_sizes=scale_cfg["compound_sccs"],
            bridge_size=2,
        )
    else:
        raise ValueError(f"Unknown topology: {topology}")

    evaluator = MockEvaluator(graph, noise_std=0.12, context_influence=0.25)

    method_cls = METHODS[method_name]
    searcher = method_cls(
        graph=graph,
        evaluator=evaluator,
        max_iterations=MAX_ITERATIONS,
        rollout_max_depth=30,
        window_size=scale_cfg["window"],
    )

    t0 = time.monotonic()
    result: SearchResult = searcher.run()
    elapsed = time.monotonic() - t0

    # Q-value history for anomaly node
    q_history_anomaly = {}
    if graph.anomaly_nodes:
        for anom_id in graph.anomaly_nodes:
            q_history_anomaly[anom_id] = [
                r.q_values.get(anom_id, 0.0) for r in result.history
            ]

    # Tree size history (only meaningful for tree_mcts)
    tree_size_history = [r.tree_size for r in result.history]
    rollout_steps_history = [r.rollout_steps for r in result.history]

    return {
        "method": method_name,
        "topology": topology,
        "scale": scale,
        "repeat": repeat_idx,
        "seed": seed,
        "graph_size": result.graph_size,
        "scc_sizes": result.scc_sizes,
        "max_iterations": result.max_iterations,
        "actual_iterations": result.actual_iterations,
        "target_rank": result.target_rank,
        "hit_top3": result.hit_top3,
        # Tree-MCTS specific
        "tree_node_count": result.tree_node_count,
        "avg_rollout_steps": result.avg_rollout_steps,
        "rollout_hit_cycle_rate": result.rollout_hit_cycle_rate,
        # Shared metrics
        "q_oscillation": result.q_oscillation,
        "q_spread": result.q_spread,
        "visit_entropy": result.visit_entropy,
        # Histories
        "q_history_anomaly": q_history_anomaly,
        "tree_size_history": tree_size_history,
        "rollout_steps_history": rollout_steps_history,
        "elapsed_sec": elapsed,
    }


def run_all_experiments(parallel: int = 4) -> list[dict]:
    """Run the full experiment matrix."""
    configs = []
    base_seed = 42

    for method_name in METHODS:
        for topology in ["dag", "simple_cycle", "compound_cycle"]:
            for scale in SCALES:
                for rep in range(REPEATS):
                    seed = base_seed + hash((method_name, topology, scale, rep)) % 10000
                    configs.append((method_name, topology, scale, rep, seed))

    total = len(configs)
    print(f"Ablation 1: Running {total} experiments "
          f"({len(METHODS)} methods x 3 topologies x {len(SCALES)} scales x {REPEATS} reps)")
    print(f"  Parallel workers: {parallel}")
    print()

    results = []
    t_start = time.monotonic()

    if parallel <= 1:
        for i, cfg in enumerate(configs):
            r = run_single_experiment(*cfg)
            results.append(r)
            _print_status(r, i + 1, total)
    else:
        with ProcessPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(run_single_experiment, *cfg): cfg
                for cfg in configs
            }
            for i, future in enumerate(as_completed(futures)):
                r = future.result()
                results.append(r)
                _print_status(r, i + 1, total)

    elapsed_total = time.monotonic() - t_start
    print(f"\nDone in {elapsed_total:.1f}s")
    return results


def _print_status(r: dict, idx: int, total: int):
    tree_info = ""
    if r["method"] == "tree_mcts":
        tree_info = f" | tree={r['tree_node_count']} nodes | rollout_cyc={r['rollout_hit_cycle_rate']:.0%}"
    hit = "HIT" if r["hit_top3"] else f"rank={r['target_rank']}"
    print(f"  [{idx}/{total}] {r['method']:10s} | {r['topology']:15s} | "
          f"{r['scale']} | {hit}{tree_info}")


def print_summary(results: list[dict]):
    """Print comparison summary focusing on the three failure modes."""
    print("\n" + "=" * 90)
    print("ABLATION 1: Tree-MCTS Failure Modes on Cyclic Graphs")
    print("=" * 90)

    header = (f"{'Method':<11} {'Topology':<16} {'Scale':<6} "
              f"{'Hit@3':<7} {'Rank':<6} "
              f"{'TreeSize':<10} {'AvgRollout':<11} {'CycleHit%':<10} "
              f"{'Q-Spread':<9} {'Q-Osc':<7} {'Entropy':<8}")
    print(header)
    print("-" * len(header))

    agg: dict[tuple, list[dict]] = defaultdict(list)
    for r in results:
        key = (r["method"], r["topology"], r["scale"])
        agg[key].append(r)

    for (method, topo, scale) in sorted(agg.keys()):
        runs = agg[(method, topo, scale)]
        hit3_rate = sum(1 for r in runs if r["hit_top3"]) / len(runs)
        ranks = [r["target_rank"] for r in runs if r["target_rank"] is not None]
        avg_rank = sum(ranks) / len(ranks) if ranks else None
        avg_tree = sum(r["tree_node_count"] for r in runs) / len(runs)
        avg_rollout = sum(r["avg_rollout_steps"] for r in runs) / len(runs)
        avg_cycle_hit = sum(r["rollout_hit_cycle_rate"] for r in runs) / len(runs)
        avg_spread = sum(r["q_spread"] for r in runs) / len(runs)
        avg_osc = sum(r["q_oscillation"] for r in runs) / len(runs)
        avg_entropy = sum(r["visit_entropy"] for r in runs) / len(runs)

        rank_str = f"{avg_rank:.1f}" if avg_rank else "N/A"
        tree_str = f"{avg_tree:.0f}" if avg_tree > 0 else "N/A"
        rollout_str = f"{avg_rollout:.1f}" if avg_rollout > 0 else "N/A"
        cycle_str = f"{avg_cycle_hit:.0%}" if method == "tree_mcts" else "N/A"

        print(f"{method:<11} {topo:<16} {scale:<6} "
              f"{hit3_rate:<7.0%} {rank_str:<6} "
              f"{tree_str:<10} {rollout_str:<11} {cycle_str:<10} "
              f"{avg_spread:<9.4f} {avg_osc:<7.4f} {avg_entropy:<8.2f}")

    print()
    _print_failure_mode_analysis(results)


def _print_failure_mode_analysis(results: list[dict]):
    """Quantify the three failure modes explicitly."""
    print("\n" + "-" * 60)
    print("FAILURE MODE ANALYSIS (TreeMCTS on Cycle vs DAG)")
    print("-" * 60)

    tree_dag = [r for r in results if r["method"] == "tree_mcts" and r["topology"] == "dag"]
    tree_cycle = [r for r in results if r["method"] == "tree_mcts" and r["topology"] != "dag"]
    sa_cycle = [r for r in results if r["method"] == "sa_mcgs" and r["topology"] != "dag"]

    if tree_dag and tree_cycle:
        dag_tree_avg = sum(r["tree_node_count"] for r in tree_dag) / len(tree_dag)
        cyc_tree_avg = sum(r["tree_node_count"] for r in tree_cycle) / len(tree_cycle)
        print(f"\n  F1: SEARCH TREE EXPLOSION")
        print(f"      TreeMCTS on DAG:   avg {dag_tree_avg:.0f} tree nodes")
        print(f"      TreeMCTS on Cycle: avg {cyc_tree_avg:.0f} tree nodes")
        if dag_tree_avg > 0:
            print(f"      Expansion ratio:   {cyc_tree_avg / dag_tree_avg:.1f}x")

        dag_rollout = sum(r["avg_rollout_steps"] for r in tree_dag) / len(tree_dag)
        cyc_rollout = sum(r["avg_rollout_steps"] for r in tree_cycle) / len(tree_cycle)
        cyc_hit_rate = sum(r["rollout_hit_cycle_rate"] for r in tree_cycle) / len(tree_cycle)
        print(f"\n  F2: ROLLOUT WASTE (trapped in cycles)")
        print(f"      TreeMCTS on DAG:   avg {dag_rollout:.1f} steps/rollout")
        print(f"      TreeMCTS on Cycle: avg {cyc_rollout:.1f} steps/rollout")
        print(f"      Cycle hit rate:    {cyc_hit_rate:.0%} of rollouts enter a cycle")

        dag_osc = sum(r["q_oscillation"] for r in tree_dag) / len(tree_dag)
        cyc_osc = sum(r["q_oscillation"] for r in tree_cycle) / len(tree_cycle)
        dag_spread = sum(r["q_spread"] for r in tree_dag) / len(tree_dag)
        cyc_spread = sum(r["q_spread"] for r in tree_cycle) / len(tree_cycle)
        sa_spread = sum(r["q_spread"] for r in sa_cycle) / len(sa_cycle) if sa_cycle else 0
        print(f"\n  F3: Q-VALUE DILUTION (all nodes → same average)")
        print(f"      TreeMCTS on DAG:   Q-spread = {dag_spread:.4f} (anomaly distinguishable)")
        print(f"      TreeMCTS on Cycle: Q-spread = {cyc_spread:.4f} (all nodes look same)")
        print(f"      SA-MCGS on Cycle:  Q-spread = {sa_spread:.4f} (anomaly distinguishable)")
        if dag_spread > 0:
            print(f"      Dilution ratio:    {dag_spread / max(0.0001, cyc_spread):.1f}x "
                  f"(higher = worse dilution on cycle)")
        print(f"      [Q-oscillation: DAG={dag_osc:.4f}, Cycle={cyc_osc:.4f}]")

    if tree_cycle and sa_cycle:
        tree_hit3 = sum(1 for r in tree_cycle if r["hit_top3"]) / len(tree_cycle)
        sa_hit3 = sum(1 for r in sa_cycle if r["hit_top3"]) / len(sa_cycle)
        print(f"\n  DETECTION PERFORMANCE ON CYCLIC GRAPHS")
        print(f"      TreeMCTS Hit@3: {tree_hit3:.0%}")
        print(f"      SA-MCGS  Hit@3: {sa_hit3:.0%}")
    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Ablation 1: TreeMCTS vs SA-MCGS on Cyclic Graphs")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel workers (1=sequential for reproducibility)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path")
    args = parser.parse_args()

    results = run_all_experiments(parallel=args.parallel)
    print_summary(results)

    output_path = args.output or "experiments/results/ablation1_cycle.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()

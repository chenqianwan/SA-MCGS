"""Visualization for Ablation 1 results.

Generates:
  - Figure 1: Q-value convergence comparison (3x3 grid)
  - Figure 2: Convergence iterations vs cycle size
  - Summary table
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def load_results(path: str = "experiments/results/ablation1_cycle.json") -> list[dict]:
    with open(path) as f:
        return json.load(f)


def plot_convergence_grid(results: list[dict], output_path: str = "experiments/results/ablation1_figure1.png"):
    """3x3 grid: rows=Scale(S/M/L), cols=Topology(DAG/Cycle/Compound).
    Each subplot shows Q-value of anomaly node over iterations for all 3 methods.
    """
    fig, axes = plt.subplots(3, 3, figsize=(14, 10), sharex=True)

    topologies = ["dag", "simple_cycle", "compound_cycle"]
    topo_labels = ["Pure DAG", "Simple Cycle (SCC)", "Compound Cycles"]
    scales = ["S", "M", "L"]
    methods = ["vanilla_mcts", "mcgs_dag", "sa_mcgs"]
    method_colors = {"vanilla_mcts": "#e74c3c", "mcgs_dag": "#3498db", "sa_mcgs": "#27ae60"}
    method_labels = {"vanilla_mcts": "M1: Vanilla MCTS", "mcgs_dag": "M3: MCGS-DAG", "sa_mcgs": "M4: SA-MCGS (Ours)"}
    method_styles = {"vanilla_mcts": "--", "mcgs_dag": "-.", "sa_mcgs": "-"}

    for row, scale in enumerate(scales):
        for col, topo in enumerate(topologies):
            ax = axes[row][col]

            for method in methods:
                matching = [
                    r for r in results
                    if r["method"] == method and r["topology"] == topo and r["scale"] == scale
                ]
                if not matching:
                    continue

                # Average Q-value history across repeats
                all_histories = []
                for r in matching:
                    hist = r.get("q_history_anomaly", {})
                    if hist:
                        first_key = list(hist.keys())[0]
                        all_histories.append(hist[first_key])

                if not all_histories:
                    continue

                max_len = max(len(h) for h in all_histories)
                padded = []
                for h in all_histories:
                    if len(h) < max_len:
                        h = h + [h[-1]] * (max_len - len(h))
                    padded.append(h[:max_len])

                avg_history = np.mean(padded, axis=0)

                ax.plot(
                    range(len(avg_history)),
                    avg_history,
                    color=method_colors[method],
                    linestyle=method_styles[method],
                    linewidth=2 if method == "sa_mcgs" else 1.5,
                    label=method_labels[method],
                    alpha=0.9,
                )

            # Ground truth line
            gt_risk = None
            for r in results:
                if r["topology"] == topo and r["scale"] == scale:
                    for anom in r.get("anomaly_nodes", []):
                        # Ground truth is 0.9 by default
                        gt_risk = 0.9
                        break
                    break
            if gt_risk:
                ax.axhline(y=gt_risk, color="gray", linestyle=":", alpha=0.5, linewidth=1)

            ax.set_ylim(-0.05, 1.05)
            if row == 0:
                ax.set_title(topo_labels[col], fontsize=12, fontweight="bold")
            if col == 0:
                ax.set_ylabel(f"Scale {scale}\nQ-value", fontsize=10)
            if row == 2:
                ax.set_xlabel("Iteration", fontsize=10)

            ax.grid(True, alpha=0.3)

    # Legend
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=11, bbox_to_anchor=(0.5, -0.02))

    fig.suptitle(
        "Ablation 1: MCTS Convergence Failure on Cyclic Graphs\n"
        "(Q-value of anomaly node over search iterations)",
        fontsize=13, fontweight="bold", y=0.98,
    )
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Figure 1 saved: {output_path}")


def plot_convergence_vs_size(results: list[dict], output_path: str = "experiments/results/ablation1_figure2.png"):
    """Plot: iterations to convergence vs graph complexity for each method."""
    fig, ax = plt.subplots(1, 1, figsize=(8, 5))

    methods = ["vanilla_mcts", "mcgs_dag", "sa_mcgs"]
    method_colors = {"vanilla_mcts": "#e74c3c", "mcgs_dag": "#3498db", "sa_mcgs": "#27ae60"}
    method_labels = {"vanilla_mcts": "M1: Vanilla MCTS", "mcgs_dag": "M3: MCGS-DAG", "sa_mcgs": "M4: SA-MCGS (Ours)"}
    method_markers = {"vanilla_mcts": "x", "mcgs_dag": "s", "sa_mcgs": "o"}

    # Only look at cycle/compound topologies
    cycle_results = [r for r in results if r["topology"] in ("simple_cycle", "compound_cycle")]

    for method in methods:
        method_results = [r for r in cycle_results if r["method"] == method]

        sizes = []
        iters = []
        for r in method_results:
            scc_total = sum(r.get("scc_sizes", [0]))
            if scc_total == 0:
                continue
            sizes.append(scc_total)
            if r["converged"] and r["converge_iter"] is not None:
                iters.append(r["converge_iter"])
            else:
                iters.append(r["max_iterations"])  # did not converge

        if sizes:
            ax.scatter(
                sizes, iters,
                color=method_colors[method],
                marker=method_markers[method],
                label=method_labels[method],
                s=60, alpha=0.7,
            )

    ax.axhline(y=300, color="gray", linestyle="--", alpha=0.5, label="Max iterations (no convergence)")
    ax.set_xlabel("Total SCC Size (nodes in cycles)", fontsize=11)
    ax.set_ylabel("Iterations to Convergence", fontsize=11)
    ax.set_title("Convergence Speed vs Cycle Complexity", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Figure 2 saved: {output_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="experiments/results/ablation1_cycle.json")
    parser.add_argument("--output-dir", default="experiments/results")
    args = parser.parse_args()

    results = load_results(args.input)
    plot_convergence_grid(results, f"{args.output_dir}/ablation1_figure1.png")
    plot_convergence_vs_size(results, f"{args.output_dir}/ablation1_figure2.png")


if __name__ == "__main__":
    main()

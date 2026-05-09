"""Phase 5: Publication-ready visualization for counterfactual perturbation experiment.

Generates 5 figures:
  1. DAG vs SCC Detection Rate Comparison (core figure)
  2. Risk Score Delta grouped bar chart
  3. MCGS Reward convergence curves
  4. Ablation Detection Rate
  5. SCC heatmap (optional)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np

# Publication defaults
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "legend.fontsize": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

COLORS = {
    "sa_mcgs": "#2563EB",
    "direct_llm": "#DC2626",
    "full": "#2563EB",
    "no_graph_pruning": "#7C3AED",
    "no_mcgs": "#D97706",
    "direct_llm_ablation": "#DC2626",
}


def _load_json(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# =====================================================================
# Figure 1: DAG vs SCC Detection Rate Comparison
# =====================================================================

def fig1_detection_rate_comparison(
    results: list[dict],
    output_path: str = "experiments/results/figures/fig1_detection_rates.pdf",
) -> None:
    """Bar chart: detection rate by node_type x perturbation_type, SA-MCGS vs Direct LLM."""
    from collections import defaultdict

    groups: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        if r["perturbation_type"] == "none":
            continue
        key = f"{r['node_type'].upper()}-{r['perturbation_type'].replace('type_', '').upper()}"
        groups[key].append(r)

    categories = sorted(groups.keys())
    mcgs_rates = []
    llm_rates = []
    for cat in categories:
        g = groups[cat]
        n = len(g)
        mcgs_det = sum(1 for r in g if r["mcgs_high_risk_detected"] or r["mcgs_uncertain_detected"])
        llm_det = sum(1 for r in g if r["direct_llm_detected"])
        mcgs_rates.append(mcgs_det / n * 100 if n > 0 else 0)
        llm_rates.append(llm_det / n * 100 if n > 0 else 0)

    x = np.arange(len(categories))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars1 = ax.bar(x - width / 2, mcgs_rates, width, label="SA-MCGS", color=COLORS["sa_mcgs"])
    bars2 = ax.bar(x + width / 2, llm_rates, width, label="Direct LLM", color=COLORS["direct_llm"])

    ax.set_ylabel("Detection Rate (%)")
    ax.set_xlabel("Node Type – Perturbation Type")
    ax.set_title("Detection Rate: SA-MCGS vs Direct LLM")
    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=15, ha="right")
    ax.set_ylim(0, 110)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    for bars in [bars1, bars2]:
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.annotate(f"{h:.0f}%", xy=(bar.get_x() + bar.get_width() / 2, h),
                            xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


# =====================================================================
# Figure 2: Risk Score Delta
# =====================================================================

def fig2_risk_delta(
    results: list[dict],
    output_path: str = "experiments/results/figures/fig2_risk_delta.pdf",
) -> None:
    """Grouped bar chart: risk delta by perturbation category."""
    from collections import defaultdict

    groups: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        if r["perturbation_type"] == "none":
            continue
        key = f"{r['perturbation_type'].replace('type_', '').upper()}-{r['node_type'].upper()}"
        groups[key].append(r)

    categories = sorted(groups.keys())
    mcgs_deltas = []
    llm_deltas = []
    for cat in categories:
        g = groups[cat]
        mcgs_deltas.append(np.mean([r["delta_mcgs_risk"] for r in g]))
        llm_deltas.append(np.mean([r["delta_direct_llm_risk"] for r in g]))

    x = np.arange(len(categories))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(x - width / 2, mcgs_deltas, width, label="SA-MCGS Δ", color=COLORS["sa_mcgs"])
    ax.bar(x + width / 2, llm_deltas, width, label="Direct LLM Δ", color=COLORS["direct_llm"])

    ax.set_ylabel("Risk Score Delta (perturbed − baseline)")
    ax.set_xlabel("Perturbation Type – Node Type")
    ax.set_title("Risk Score Shift After Perturbation")
    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=15, ha="right")
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


# =====================================================================
# Figure 3: MCGS Reward Convergence
# =====================================================================

def fig3_reward_convergence(
    baseline_rewards: list[float],
    perturbed_rewards: list[float],
    output_path: str = "experiments/results/figures/fig3_reward_convergence.pdf",
    title_suffix: str = "",
) -> None:
    """Line chart: cumulative average reward over rollouts."""
    fig, ax = plt.subplots(figsize=(7, 4))

    if baseline_rewards:
        cum_avg_base = np.cumsum(baseline_rewards) / np.arange(1, len(baseline_rewards) + 1)
        ax.plot(cum_avg_base, label="Baseline (original)", color="#6B7280", linewidth=1.5)

    if perturbed_rewards:
        cum_avg_pert = np.cumsum(perturbed_rewards) / np.arange(1, len(perturbed_rewards) + 1)
        ax.plot(cum_avg_pert, label="Perturbed", color=COLORS["sa_mcgs"], linewidth=1.5)

    ax.set_xlabel("Rollout Index")
    ax.set_ylabel("Cumulative Average Reward")
    ax.set_title(f"MCGS Reward Convergence{' — ' + title_suffix if title_suffix else ''}")
    ax.legend()
    ax.grid(alpha=0.3)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


# =====================================================================
# Figure 4: Ablation Detection Rate
# =====================================================================

def fig4_ablation(
    ablation_results: list[dict],
    output_path: str = "experiments/results/figures/fig4_ablation.pdf",
) -> None:
    """Grouped bar chart: detection rate by ablation config."""
    from collections import defaultdict

    groups: dict[str, list[dict]] = defaultdict(list)
    for r in ablation_results:
        groups[r["config_name"]].append(r)

    config_order = ["full", "no_graph_pruning", "no_mcgs", "direct_llm"]
    config_labels = ["Full SA-MCGS", "No Graph Pruning", "No MCGS", "Direct LLM"]

    rates = []
    for cfg in config_order:
        g = groups.get(cfg, [])
        n = len(g)
        det = sum(1 for r in g if r["high_risk_detected"] or r["uncertain_detected"])
        rates.append(det / n * 100 if n > 0 else 0)

    colors = [COLORS.get(c, "#888888") for c in config_order]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(config_labels, rates, color=colors, edgecolor="white", linewidth=0.5)

    ax.set_ylabel("Detection Rate (%)")
    ax.set_title("Ablation Study: Component Contribution")
    ax.set_ylim(0, 110)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.grid(axis="y", alpha=0.3)

    for bar in bars:
        h = bar.get_height()
        if h > 0:
            ax.annotate(f"{h:.0f}%", xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points", ha="center", fontsize=9)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


# =====================================================================
# Figure 5: SCC Risk Heatmap
# =====================================================================

def fig5_scc_heatmap(
    scc_results: list[dict],
    scc_edges: list[dict],
    output_path: str = "experiments/results/figures/fig5_scc_heatmap.pdf",
) -> None:
    """Directed graph of an SCC with nodes colored by risk delta."""
    try:
        import networkx as nx
    except ImportError:
        print("  Skipping fig5: networkx not available")
        return

    if not scc_results:
        print("  Skipping fig5: no SCC results")
        return

    G = nx.DiGraph()
    deltas = {}
    for r in scc_results:
        nid = r["target_clause_id"]
        delta = r.get("delta_mcgs_risk", 0)
        G.add_node(nid)
        deltas[nid] = delta

    for e in scc_edges:
        if e["source"] in G.nodes and e["target"] in G.nodes:
            G.add_edge(e["source"], e["target"])

    if G.number_of_nodes() == 0:
        print("  Skipping fig5: empty graph")
        return

    fig, ax = plt.subplots(figsize=(6, 5))
    pos = nx.spring_layout(G, seed=42)

    node_colors = [deltas.get(n, 0) for n in G.nodes()]
    vmax = max(abs(c) for c in node_colors) if node_colors else 1.0

    nodes = nx.draw_networkx_nodes(
        G, pos, ax=ax,
        node_color=node_colors,
        cmap=plt.cm.RdYlGn_r,
        vmin=-vmax, vmax=vmax,
        node_size=500, edgecolors="black", linewidths=0.8,
    )
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color="#999999",
                           arrows=True, arrowsize=15, width=1.2)

    labels = {n: n.split("/")[-1][:12] for n in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, ax=ax, font_size=7)

    fig.colorbar(nodes, ax=ax, label="Risk Delta (perturbed − baseline)", shrink=0.8)
    ax.set_title("SCC Risk Heatmap After Perturbation")
    ax.axis("off")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


# =====================================================================
# Main entry point
# =====================================================================

def generate_all_figures(
    experiment_results_path: str = "experiments/results/experiment_results.json",
    ablation_results_path: str = "experiments/results/ablation_results.json",
    output_dir: str = "experiments/results/figures",
) -> None:
    """Generate all publication figures from saved results."""
    print("\n=== Generating Publication Figures ===\n")

    exp_results = _load_json(experiment_results_path)
    print(f"Loaded {len(exp_results)} experiment results")

    fig1_detection_rate_comparison(exp_results, f"{output_dir}/fig1_detection_rates.pdf")
    fig2_risk_delta(exp_results, f"{output_dir}/fig2_risk_delta.pdf")

    # Fig 3: use placeholder data — real convergence data requires rollout-level logging
    fig3_reward_convergence(
        baseline_rewards=[],
        perturbed_rewards=[],
        output_path=f"{output_dir}/fig3_reward_convergence.pdf",
    )

    ablation_path = Path(ablation_results_path)
    if ablation_path.exists():
        abl_results = _load_json(ablation_results_path)
        print(f"Loaded {len(abl_results)} ablation results")
        fig4_ablation(abl_results, f"{output_dir}/fig4_ablation.pdf")
    else:
        print("  Skipping fig4: ablation results not found")

    scc_results = [r for r in exp_results if r["node_type"] == "scc"]
    fig5_scc_heatmap(scc_results, [], f"{output_dir}/fig5_scc_heatmap.pdf")

    print("\n=== Figure generation complete ===")


if __name__ == "__main__":
    generate_all_figures()

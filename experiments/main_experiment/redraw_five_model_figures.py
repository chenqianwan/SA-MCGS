#!/usr/bin/env python3
"""Refine two manuscript figures without changing accepted aggregate values.

Contract: model-dependent localization and complete evidence retention across
SCC sizes, followed by the joint evidence-retention / output-compactness relation.
The first figure is a quantitative matrix; the second is a within-model bivariate comparison.
All 90 size-stratified values and all 30 overall metric values are retained.
Means describe the fixed benchmark, not repeated seeds; no error bars or tests
are inferred. Source summaries are read-only. Python is the exclusive backend.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "experiments/main_experiment/paper_assets"
SOURCE = ASSETS / "five_model_data/aggregates.json"
FIGURES = ASSETS / "figures"
QA_DIR = ROOT / "2026NAACL/SA-MCGS/nature_data_figures_20260927"
MODELS = ["gpt-4o", "gemini-2.5-pro", "qwen2.5-72b", "llama-3.1-8b", "qwen3.5-9b"]
LABELS = ["GPT-4o", "Gemini 2.5 Pro", "Qwen2.5-72B", "Llama 3.1-8B", "Qwen3.5-9B"]
METHODS = ["one-shot", "lea", "sa-mcgs"]
METHOD_LABELS = {"one-shot": "One-shot", "lea": "LEA", "sa-mcgs": "SA-MCGS"}
SCALES = ["small", "medium", "large"]
# Preserve method semantics across the manuscript; refine contrast and saturation.
COLORS = {"one-shot": "#737373", "lea": "#D55E00", "sa-mcgs": "#0072B2"}
MARKERS = {"one-shot": "o", "lea": "s", "sa-mcgs": "^"}
INK = "#222222"
MUTED = "#444444"
GRID = "#E9E9E9"
RULE = "#333333"
WIDTH = 6.3
PLOT_VALUES: list[dict] = []


def configure_style():
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 7.5, "axes.labelsize": 7.5, "axes.titlesize": 7.5,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7.5,
        "text.color": INK, "axes.labelcolor": INK,
        "xtick.color": INK, "ytick.color": INK,
        "axes.linewidth": .55, "axes.edgecolor": RULE,
        "axes.spines.top": False, "axes.spines.right": False,
        "xtick.major.width": .55, "ytick.major.width": .55,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "xtick.direction": "out", "ytick.direction": "out",
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    })


def shared_legend(fig, y=.994, lines=True):
    handles = [Line2D([], [], color=COLORS[m], marker=MARKERS[m],
                      markerfacecolor=COLORS[m] if m == "sa-mcgs" else "white",
                      markeredgecolor=COLORS[m], markeredgewidth=.7,
                      markersize=4.2 if m == "sa-mcgs" else 3.8,
                      linewidth=1.3 if m == "sa-mcgs" else .85,
                      linestyle="-" if lines else "none", label=METHOD_LABELS[m]) for m in METHODS]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.54, y),
               ncol=3, frameon=False, borderaxespad=0, handlelength=1.8,
               handletextpad=.55, columnspacing=1.8)


def export(fig, stem):
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{stem}.svg")
    fig.savefig(FIGURES / f"{stem}.pdf")
    fig.savefig(FIGURES / f"{stem}.png", dpi=600)
    plt.close(fig)


def plot_scale(groups):
    configure_style()
    lookup = {(r["model"], r["scale"], r["method"]): r for r in groups["model_scale_method"]}
    fig = plt.figure(figsize=(WIDTH, 3.15))
    left, right, gap = .082, .985, .031
    w = (right-left-4*gap)/5
    for c, label in enumerate(LABELS):
        x = left+c*(w+gap)
        fig.text(x+w/2, .883, label, ha="center", va="center", fontsize=7.3)
        for row, (metric, bottom) in enumerate([("root_at3", .535), ("risk_all", .157)]):
            ax = fig.add_axes((x, bottom, w, .277))
            ax.set_xlim(-.18, 2.18)
            ax.set_ylim(-4, 104)
            ax.set_yticks([0, 50, 100])
            ax.set_xticks([0, 1, 2], ["≤12", "14–20", "≥24"])
            ax.tick_params(axis="both", pad=2)
            ax.tick_params(axis="y", labelleft=(c == 0), length=2.2 if c == 0 else 0)
            if c != 0:
                ax.spines["left"].set_visible(False)
            if row == 0:
                ax.tick_params(axis="x", labelbottom=False)
            ax.set_axisbelow(True)
            ax.grid(axis="y", color=GRID, linewidth=.4)
            series = {m: [lookup[(MODELS[c], scale, m)][metric]*100 for scale in SCALES]
                      for m in METHODS}
            for method in METHODS:
                values = series[method]
                for scale, value in zip(SCALES, values):
                    PLOT_VALUES.append({"figure": "scale", "model": MODELS[c], "method": method,
                                        "scale": scale, "metric": metric, "value": value})
                ax.plot([0, 1, 2], values, color=COLORS[method],
                        linewidth=1.3 if method == "sa-mcgs" else .85, zorder=3)
                for xi, value in enumerate(values):
                    tied = any(abs(value-series[m][xi]) < 1e-9 for m in METHODS if m != method)
                    size = {"one-shot": 5.0, "lea": 4.3, "sa-mcgs": 3.5}[method] if tied else (3.8 if method == "sa-mcgs" else 3.5)
                    ax.plot(xi, value, linestyle="none", marker=MARKERS[method],
                            markersize=size, markeredgecolor=COLORS[method], markeredgewidth=.65,
                            markerfacecolor=COLORS[method] if method == "sa-mcgs" else "none",
                            zorder=5+METHODS.index(method))
    fig.text(.007, .818, "a", fontsize=9, fontweight="bold")
    fig.text(.007, .440, "b", fontsize=9, fontweight="bold")
    fig.text(.018, .674, "Root@3 (%)", rotation=90, rotation_mode="anchor",
             ha="center", va="center", fontsize=7.6)
    fig.text(.018, .296, "Risk-all (%)", rotation=90, rotation_mode="anchor",
             ha="center", va="center", fontsize=7.6)
    fig.text(.53, .043, "Original SCC size (nodes)", ha="center", fontsize=7.5)
    shared_legend(fig)
    export(fig, "fig02_main_results_five_models")


def plot_coverage_compression(groups):
    configure_style()
    lookup = {(r["model"], r["method"]): r for r in groups["model_method"]}
    fig = plt.figure(figsize=(WIDTH, 2.14))
    left, right, gap = .082, .985, .031
    w = (right-left-4*gap)/5
    for i, model in enumerate(MODELS):
        x = left+i*(w+gap)
        ax = fig.add_axes((x, .270, w, .483))
        ax.set_xlim(20, 85)
        ax.set_ylim(0, 100)
        ax.set_xticks([20, 50, 80])
        ax.set_yticks([0, 50, 100])
        ax.tick_params(pad=2, labelleft=(i == 0))
        if i != 0:
            ax.spines["left"].set_visible(False)
            ax.tick_params(axis="y", length=0)
        ax.grid(False)
        ax.set_title(LABELS[i], pad=8, fontsize=7.3)
        lea, sa = lookup[(model, "lea")], lookup[(model, "sa-mcgs")]
        start = (100*lea["compression"], 100*lea["risk_all"])
        end = (100*sa["compression"], 100*sa["risk_all"])
        # A within-model method contrast, not a temporal trajectory or frontier.
        ax.annotate("", xy=end, xytext=start,
                    arrowprops={"arrowstyle": "->", "color": "#555555", "lw": .7,
                                "shrinkA": 2.0, "shrinkB": 2.4, "mutation_scale": 6.5},
                    zorder=2)
        for method in METHODS:
            record = lookup[(model, method)]
            xx, yy = record["compression"]*100, record["risk_all"]*100
            for metric in ["risk_all", "compression"]:
                PLOT_VALUES.append({"figure": "joint", "model": model, "method": method,
                                    "metric": metric, "value": record[metric]*100})
            ax.plot(xx, yy, marker=MARKERS[method], linestyle="none",
                    markersize=4.8 if method == "sa-mcgs" else 4.2,
                    color=COLORS[method], markeredgewidth=.8,
                    markerfacecolor=COLORS[method] if method == "sa-mcgs" else "white",
                    zorder=3+METHODS.index(method))
    fig.text(.018, .512, "Risk-all (%)", rotation=90, rotation_mode="anchor",
             ha="center", va="center", fontsize=7.6)
    fig.text(.535, .075, "Compression (%)", ha="center", fontsize=7.5)
    shared_legend(fig, .997, lines=False)
    export(fig, "fig03_coverage_compression_five_models")


def main():
    before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    groups = json.loads(SOURCE.read_text())
    assert len(groups["model_scale_method"]) == 45
    assert len(groups["model_method"]) == 15
    plot_scale(groups)
    plot_coverage_compression(groups)
    assert len(PLOT_VALUES) == 120
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == before
    QA_DIR.mkdir(parents=True, exist_ok=True)
    (QA_DIR / "plotted_values.json").write_text(json.dumps(PLOT_VALUES, indent=2)+"\n")
    (QA_DIR / "figure_contract.json").write_text(json.dumps({
        "backend": "python", "reuse_level": "Style-only inheritance of existing plotting workflow",
        "figure_3_question": "How do root localization and complete evidence retention vary with SCC size?",
        "figure_3_archetype": "Quantitative matrix, all five models and three methods",
        "figure_4_question": "Does complete risk retention improve at comparable or higher compression for each model?",
        "figure_4_archetype": "Five common-scale joint planes with LEA-to-SA paired method arrows",
        "data_mapping": "model / method / scale identify groups; root_at3, risk_all, compression multiplied by 100",
        "data_selection": "Exactly the previously approved groups; no exclusions or new aggregation",
        "center": "Previously accepted benchmark means", "uncertainty": "None; no repeated-seed estimate",
        "statistical_tests": "None", "transforms": "Fraction to percentage only; no interpolation",
        "source_aggregate_sha256": before, "source_unchanged": True,
        "values": {"scale": 90, "joint": 30}, "width_in": WIDTH,
        "exports": ["Editable PDF", "Editable SVG", "600 dpi PNG"],
        "coordinate_integrity": "No jitter, smoothing, axis breaks or moved points; all five joint panels share x 20-85, y 0-100",
    }, indent=2)+"\n")
    print(json.dumps({"source_unchanged": True, "plotted_values": len(PLOT_VALUES)}))


if __name__ == "__main__":
    main()

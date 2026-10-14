#!/usr/bin/env python3
"""Restyle the frozen budget and fixed-case figures without recomputing results.

The budget panels pair evidence accumulation with compactness. The fixed-case
panels preserve the common clause map and compare selected risk endpoints and
core size. Source aggregates and selections are read-only; no model is called.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.text import Text
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "experiments/main_experiment/paper_assets"
FIGURES = ASSETS / "figures"
DATA = ASSETS / "revision_20260925"
QA = ROOT / "2026NAACL/SA-MCGS/nature_data_figures_20260927"
METHODS = ("one-shot", "lea", "sa-mcgs")
LABELS = {"one-shot": "One-shot", "lea": "LEA", "sa-mcgs": "SA-MCGS"}
COLORS = {"one-shot": "#737373", "lea": "#D55E00", "sa-mcgs": "#0072B2"}
MARKERS = {"one-shot": "o", "lea": "s", "sa-mcgs": "^"}
REFERENCE = {
    "risk_all": {"one-shot": 15.00, "lea": 43.75},
    "compression": {"one-shot": 67.89, "lea": 51.26},
}
INK = "#262626"
LIGHT = "#C4C4C4"
WIDTH = 6.3

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial"],
    "font.size": 7.5, "axes.labelsize": 7.5, "axes.titlesize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
    "text.color": INK, "axes.labelcolor": INK, "axes.edgecolor": INK,
    "xtick.color": INK, "ytick.color": INK,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": .55, "xtick.major.width": .55, "ytick.major.width": .55,
    "xtick.major.size": 2.6, "ytick.major.size": 2.6,
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "savefig.dpi": 600, "figure.facecolor": "white", "axes.facecolor": "white",
})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(fig, name: str) -> dict:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    width, height = fig.canvas.get_width_height()
    text_qa = []
    outside = []
    for item in fig.findobj(Text):
        if not item.get_visible() or not item.get_text():
            continue
        box = item.get_window_extent(renderer)
        text_qa.append({"text": item.get_text(), "size_pt": item.get_fontsize()})
        if box.x0 < -0.5 or box.y0 < -0.5 or box.x1 > width + .5 or box.y1 > height + .5:
            outside.append(item.get_text())
    assert not outside, outside
    assert min(x["size_pt"] for x in text_qa) >= 6.5
    # Fixed canvas, with no tight crop, preserves the exact manuscript width.
    fig.savefig(FIGURES / f"{name}.pdf", facecolor="white")
    fig.savefig(FIGURES / f"{name}.svg", facecolor="white")
    fig.savefig(FIGURES / f"{name}.png", dpi=600, facecolor="white")
    outputs = {}
    for extension in ("pdf", "svg", "png"):
        target = FIGURES / f"{name}.{extension}"
        outputs[extension] = {"sha256": sha(target), "bytes": target.stat().st_size}
    result = {
        "width_inches": float(fig.get_figwidth()), "height_inches": float(fig.get_figheight()),
        "minimum_font_pt": min(x["size_pt"] for x in text_qa),
        "outside_canvas_text": outside, "exports": outputs,
    }
    plt.close(fig)
    return result


def budget_figure(series: list[dict]) -> dict:
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.2))
    fig.subplots_adjust(left=.074, right=.971, bottom=.197, top=.77, wspace=.32)
    budgets = np.array([int(row["budget"]) for row in series])
    assert budgets.tolist() == list(range(1, 61))
    assert {int(row["n"]) for row in series} == {80}
    for ax, metric, letter, title in zip(
        axes, ("risk_all", "compression"), ("a", "b"),
        ("Complete risk evidence", "Subgraph compression"),
    ):
        values = np.array([float(row[metric]) * 100 for row in series])
        assert np.isfinite(values).all() and (values >= 0).all() and (values <= 100).all()
        for method, dash in (("one-shot", (0, (1.4, 2.2))), ("lea", (0, (4, 2.5)))):
            ax.axhline(REFERENCE[metric][method], color=COLORS[method], ls=dash, lw=.9, zorder=1)
        # Every prefix is displayed; markers merely punctuate the saved curve.
        ax.plot(budgets, values, color=COLORS["sa-mcgs"], lw=1.25,
                marker="^", markevery=[0, 9, 19, 29, 39, 49, 59], ms=3.2,
                markeredgecolor="white", markeredgewidth=.35, zorder=3)
        label_offset = 9 if metric == "risk_all" else 5
        ax.annotate(f"{values[-1]:.2f}%", xy=(60, values[-1]), xytext=(-3, label_offset),
                    textcoords="offset points", color=COLORS["sa-mcgs"],
                    fontsize=7, ha="right", va="bottom")
        ax.set(xlim=(0, 62), ylim=(0, 100), xticks=[0, 20, 40, 60],
               yticks=[0, 25, 50, 75, 100], xlabel="Completed rollouts",
               ylabel="Risk-all (%)" if metric == "risk_all" else "Compression (%)")
        ax.tick_params(pad=2.3)
        ax.xaxis.labelpad = 4
        ax.yaxis.labelpad = 3
        ax.set_title(title, loc="left", fontsize=8, fontweight="normal", pad=8)
        ax.text(-.135, 1.075, letter, transform=ax.transAxes,
                ha="left", va="bottom", fontsize=8, weight="bold")
    handles = [
        Line2D([], [], color=COLORS[method], marker=MARKERS[method],
               ls=style, lw=1.15, ms=3.5, markeredgewidth=.55,
               markerfacecolor="white" if method != "sa-mcgs" else COLORS[method],
               markeredgecolor=COLORS[method], label=LABELS[method] + suffix)
        for method, style, suffix in zip(
            METHODS, ((0, (1.4, 2.2)), (0, (4, 2.5)), "-"),
            (" reference", " reference", ""),
        )
    ]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.53, 1.0),
               ncol=3, frameon=False, handlelength=2.5, columnspacing=2.0,
               handletextpad=.6, borderaxespad=0)
    return export(fig, "fig04_budget_prefix_three_methods")


def case_figure(case: dict) -> dict:
    positions = case["shared_node_positions"]
    assert len(positions) == 25
    assert case["case_id"] == "28_bgb25_scc_3_handoff_invariant"
    assert case["model"] == "gemini-2.5-pro"
    # Endpoint identities are the frozen identities of this unchanged case.
    endpoints = {"bgb_505", "bgb_491"}
    rows = {row["method"]: row for row in case["rows"]}
    assert set(rows) == set(METHODS)
    expected = {"one-shot": (3, 0, 1, 0, .88), "lea": (12, 1, 1, 1, .52), "sa-mcgs": (9, 1, 1, 1, .64)}
    fig = plt.figure(figsize=(6.3, 3.34))
    centers = [.225, .535, .845]
    axes = [fig.add_axes([cx-.138, .43, .276, .474]) for cx in centers]
    for letter, method, ax, center in zip("abc", METHODS, axes, centers):
        row = rows[method]
        selected = json.loads(row["selected_nodes"])
        kept = set(selected)
        assert len(selected) == len(kept) == row["retained_nodes"]
        assert kept.issubset(positions)
        assert (row["retained_nodes"], row["root_at3"], row["risk_any"], row["risk_all"], row["compression"]) == expected[method]
        ax.set(xlim=(-.48, 4.48), ylim=(-.54, 4.38), aspect="equal")
        ax.axis("off")
        fig.text(center, .96, LABELS[method], fontsize=8, ha="center", va="top")
        fig.text(center-.138, .96, letter, fontsize=8, weight="bold", ha="left", va="top")
        for node, (x, y) in positions.items():
            retained = node in kept
            endpoint = node in endpoints
            face = COLORS[method] if retained else "white"
            edge = INK if endpoint else COLORS[method] if retained else LIGHT
            ax.scatter([x], [y], s=24 if endpoint else 20,
                       marker="D" if endpoint else "o", facecolor=face,
                       edgecolor=edge, linewidth=.65 if endpoint else .55, zorder=2)
            ax.text(x, y-.235, node.replace("bgb_", "§"), fontsize=6.5,
                    ha="center", va="top", color=INK if retained or endpoint else "#909090")
    handles = [
        Line2D([], [], ls="none", marker="o", markersize=4, markerfacecolor=INK,
               markeredgecolor=INK, markeredgewidth=.6, label="Retained"),
        Line2D([], [], ls="none", marker="o", markersize=4, markerfacecolor="white",
               markeredgecolor=LIGHT, markeredgewidth=.6, label="Omitted"),
        Line2D([], [], ls="none", marker="D", markersize=4, markerfacecolor="white",
               markeredgecolor=INK, markeredgewidth=.6, label="Risk endpoint"),
    ]
    fig.legend(handles=handles, loc="center", bbox_to_anchor=(.535, .368), ncol=3,
               frameon=False, handletextpad=.45, handlelength=1, columnspacing=1.4,
               borderpad=0, fontsize=6.8)
    # One aligned summary replaces three detached prose blocks.
    fig.add_artist(Line2D([.03, .984], [.318, .318], color=INK, lw=.55,
                          transform=fig.transFigure))
    metrics = [
        ("Nodes retained", lambda row: f"{row['retained_nodes']}/25"),
        ("Root@3", lambda row: f"{row['root_at3']:.0f}"),
        ("Risk-any", lambda row: f"{row['risk_any']:.0f}"),
        ("Risk-all", lambda row: f"{row['risk_all']:.0f}"),
        ("Compression (%)", lambda row: f"{row['compression'] * 100:.0f}"),
    ]
    for y, (label, formatter) in zip([.275, .222, .169, .116, .063], metrics):
        fig.text(.03, y, label, fontsize=7, va="center", ha="left")
        for method, center in zip(METHODS, centers):
            fig.text(center, y, formatter(rows[method]), fontsize=7, va="center", ha="center")
    result = export(fig, "fig06_representative_scc_three_methods")
    result.update({"n_nodes_per_panel": 25, "n_panels": 3, "edge_count": 0,
                   "positions_unchanged": True, "metrics_unchanged": True,
                   "selection_counts": {method: rows[method]["retained_nodes"] for method in METHODS}})
    return result


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    inputs = [DATA / "gpt4o_budget_summary.csv", DATA / "fixed_case_three_methods_provenance.json"]
    before = {path.name: sha(path) for path in inputs}
    series = list(csv.DictReader(inputs[0].open()))
    case = json.loads(inputs[1].read_text())
    results = {"budget": budget_figure(series), "case": case_figure(case)}
    after = {path.name: sha(path) for path in inputs}
    assert before == after
    results.update({
        "input_sha256": before, "inputs_unchanged": True, "scientific_recomputation": False,
        "model_calls": 0, "budget_rows": len(series), "n_per_budget": 80,
        "budget_endpoint": {key: float(series[-1][key]) for key in ("risk_all", "compression")},
        "font": "Arial", "source_sha256": sha(Path(__file__)),
    })
    (QA / "budget_case_render_audit.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reproduce two complete gain maps from the frozen aggregate means."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors, font_manager
import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = ROOT / "experiments/main_experiment/paper_assets/five_model_data/aggregates.json"
MODELS = ["gpt-4o", "gemini-2.5-pro", "qwen2.5-72b", "llama-3.1-8b", "qwen3.5-9b"]
MODEL_LABELS = ["GPT-4o", "Gemini 2.5 Pro", "Qwen2.5-72B", "Llama 3.1-8B", "Qwen3.5-9B"]
METRICS = ["root_at3", "risk_any", "risk_all", "compression"]
METRIC_LABELS = ["Root@3", "Risk-any", "Risk-all", "Compression"]
DOMAIN_SPECS = [("debian", "Debian", 8), ("sec_ex21", "SEC EX-21", 20), ("bgb", "BGB", 12), ("cuad", "CUAD", 40)]
SCALE_SPECS = [("small", "≤12", 36), ("medium", "14–20", 24), ("large", "≥24", 20)]
LIMIT = 70.0
CMAP = colors.LinearSegmentedColormap.from_list(
    "signed_gain", ["#A65F4C", "#FBFBF9", "#21658A"], N=257
)
NORM = colors.TwoSlopeNorm(vmin=-LIMIT, vcenter=0.0, vmax=LIMIT)

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial"],
    "font.size": 8.0, "axes.labelsize": 8.0, "xtick.labelsize": 7.3,
    "ytick.labelsize": 8.0, "axes.linewidth": 0.6,
    "svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42,
    "savefig.facecolor": "white", "figure.facecolor": "white",
    "text.color": "#202020", "axes.labelcolor": "#202020",
    "xtick.color": "#202020", "ytick.color": "#202020",
    "axes.unicode_minus": True,
})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find(records: list[dict], **match) -> dict:
    found = [row for row in records if all(row[key] == val for key, val in match.items())]
    assert len(found) == 1, match
    return found[0]


def make_cell(candidate: str, panel: str, model: str, metric: str, sa: dict,
              comparator: dict, group_kind: str = "all", group: str = "all") -> dict:
    assert sa[metric] is not None and comparator[metric] is not None
    delta = 100.0 * (sa[metric] - comparator[metric])
    if abs(delta) < 1e-12:
        delta = 0.0
    assert -LIMIT <= delta <= LIMIT, (candidate, model, metric, delta)
    return {
        "candidate": candidate, "panel": panel, "model": model,
        "metric": metric, "group_kind": group_kind, "group": group,
        "comparator": comparator["method"], "sa_mean": sa[metric],
        "comparator_mean": comparator[metric], "delta_pp": delta,
        "display_delta_pp": fmt(delta), "sa_case_n": sa["n"],
        "comparator_case_n": comparator["n"],
        "sa_metric_n": sa[f"{metric}_n"],
        "comparator_metric_n": comparator[f"{metric}_n"],
    }


def fmt(value: float) -> str:
    return "0.00" if abs(value) < 1e-12 else f"{value:+.2f}".replace("-", "−")


def draw_map(ax, matrix, labels, *, row_labels: bool):
    nrows, ncols = matrix.shape
    ax.pcolormesh(np.arange(ncols + 1) - 0.5, np.arange(nrows + 1) - 0.5,
                  matrix, cmap=CMAP, norm=NORM, edgecolors="white", linewidth=1.25,
                  antialiased=False, rasterized=False)
    ax.set_xlim(-0.5, ncols - 0.5)
    ax.set_ylim(nrows - 0.5, -0.5)
    ax.set_xticks(range(ncols), labels)
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", length=0, pad=8)
    ax.set_yticks(range(nrows), MODEL_LABELS if row_labels else [""] * nrows)
    ax.tick_params(axis="y", length=0, pad=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for y in range(nrows):
        for x in range(ncols):
            value = float(matrix[y, x])
            rgb = np.array(CMAP(NORM(value))[:3])
            luminance = np.dot(rgb, [0.2126, 0.7152, 0.0722])
            ax.text(x, y, fmt(value), ha="center", va="center", fontsize=8.0,
                    color="white" if luminance < 0.53 else "#202020")


def panel_heading(fig, x, y, letter, title):
    fig.text(x - 0.027, y, letter, ha="left", va="center", fontsize=9.0, fontweight="bold")
    fig.text(x + 0.004, y, title, ha="left", va="center", fontsize=8.4)


def colorbar(fig, label, *, y=0.15):
    cax = fig.add_axes([0.372, y, 0.43, 0.034])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=NORM, cmap=CMAP), cax=cax,
                      orientation="horizontal", ticks=[-70, -35, 0, 35, 70])
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=2, width=0.5, pad=2.0, labelsize=7.3)
    cb.set_label(label, fontsize=7.8, labelpad=5)


def export(fig, stem):
    fig.canvas.draw()
    bounds = fig.bbox
    escaped = []
    for text in fig.findobj(matplotlib.text.Text):
        if text.get_visible() and text.get_text():
            bbox = text.get_window_extent(fig.canvas.get_renderer())
            if bbox.width > 0 and bbox.height > 0 and not (bounds.x0 <= bbox.x0 and bbox.x1 <= bounds.x1 and bounds.y0 <= bbox.y0 and bbox.y1 <= bounds.y1):
                escaped.append(text.get_text())
    assert not escaped, escaped
    fig.savefig(OUT / f"{stem}.pdf", facecolor="white")
    fig.savefig(OUT / f"{stem}.svg", facecolor="white")
    fig.savefig(OUT / f"{stem}.png", dpi=600, facecolor="white")
    plt.close(fig)
    return {"size_in": list(fig.get_size_inches()), "escaped_text": escaped,
            "files": {ext: sha(OUT / f"{stem}.{ext}") for ext in ["pdf", "svg", "png"]}}


def main():
    source_sha = sha(SOURCE)
    data = json.loads(SOURCE.read_text())
    font_path = font_manager.findfont("Arial", fallback_to_default=False)
    cells_b, matrices_b = [], []
    for comparator in ["one-shot", "lea"]:
        matrix = np.empty((5, 4))
        for i, model in enumerate(MODELS):
            sa = find(data["model_method"], model=model, method="sa-mcgs")
            base = find(data["model_method"], model=model, method=comparator)
            assert sa["n"] == base["n"] == 80
            for j, metric in enumerate(METRICS):
                cell = make_cell("B", comparator, model, metric, sa, base)
                cells_b.append(cell)
                matrix[i, j] = cell["delta_pp"]
        matrices_b.append(matrix)
    assert len(cells_b) == 40

    fig = plt.figure(figsize=(6.3, 2.83))
    for k, x in enumerate([0.196, 0.606]):
        ax = fig.add_axes([x, 0.33, 0.366, 0.50])
        draw_map(ax, matrices_b[k], METRIC_LABELS, row_labels=(k == 0))
        panel_heading(fig, x, 0.962, "ab"[k], ["SA-MCGS − One-shot", "SA-MCGS − LEA"][k])
    colorbar(fig, "Δ metric (percentage points)", y=0.165)
    output_b = export(fig, "candidate_B_gain_heatmap")

    cells_c, matrices_c = [], []
    for kind, specs, source_key in [("domain", DOMAIN_SPECS, "model_domain_method"),
                                     ("scale", SCALE_SPECS, "model_scale_method")]:
        matrix = np.empty((5, len(specs)))
        for i, model in enumerate(MODELS):
            for j, (group, _, count) in enumerate(specs):
                sa = find(data[source_key], model=model, method="sa-mcgs", **{kind: group})
                base = find(data[source_key], model=model, method="lea", **{kind: group})
                assert sa["n"] == base["n"] == count
                cell = make_cell("C", kind, model, "risk_all", sa, base, kind, group)
                cells_c.append(cell)
                matrix[i, j] = cell["delta_pp"]
        matrices_c.append(matrix)
    assert len(cells_c) == 35

    fig = plt.figure(figsize=(6.3, 2.98))
    for k, (x, width, specs) in enumerate([(0.196, 0.404, DOMAIN_SPECS), (0.662, 0.303, SCALE_SPECS)]):
        ax = fig.add_axes([x, 0.32, width, 0.48])
        labels = [f"{label}\nn = {n}" for _, label, n in specs]
        draw_map(ax, matrices_c[k], labels, row_labels=(k == 0))
        panel_heading(fig, x, 0.96, "ab"[k], ["Domain", "SCC size (nodes)"][k])
    colorbar(fig, "Δ Risk-all: SA-MCGS − LEA (percentage points)", y=0.16)
    output_c = export(fig, "candidate_C_domain_scale_heatmap")

    cell_files = {}
    for candidate, rows in [("B", cells_b), ("C", cells_c)]:
        path = OUT / f"candidate_{candidate}_cells.csv"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        # Reload the export and verify that every numeric cell is unchanged.
        with path.open() as handle:
            exported = list(csv.DictReader(handle))
        assert len(exported) == len(rows)
        for row, readback in zip(rows, exported):
            for key in ["sa_mean", "comparator_mean", "delta_pp"]:
                assert float(readback[key]) == row[key]
            assert readback["display_delta_pp"] == fmt(row["delta_pp"])
        cell_files[candidate] = {"count": len(rows), "sha256": sha(path), "csv_roundtrip_exact": True,
            "negative": sum(row["delta_pp"] < 0 for row in rows),
            "zero": sum(row["delta_pp"] == 0 for row in rows),
            "positive": sum(row["delta_pp"] > 0 for row in rows)}
    assert sha(SOURCE) == source_sha
    manifest = {
        "source_sha256_before": source_sha, "source_sha256_after": sha(SOURCE),
        "source_unchanged": True, "model_order": MODELS, "backend": "python",
        "font": "Arial", "font_found": bool(font_path), "minimum_font_pt": 7.3,
        "png_dpi": 600, "editable_text": True,
        "colorbar_limits_pp": [-LIMIT, LIMIT], "all_values_within_colorbar": True,
        "difference_rule": "100 * (unrounded SA-MCGS mean - unrounded comparator mean); round only for displayed cells",
        "rows_excluded": 0, "cells": cell_files,
        "candidate_B": output_b, "candidate_C": output_c,
        "uncertainty": "Descriptive accepted case aggregates; no inferential interval or significance assertion",
    }
    (OUT / "heatmap_candidate_validation.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"B": cell_files["B"], "C": cell_files["C"], "source_unchanged": True}, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render the complete two-metric SA-MCGS minus LEA SCC-size comparison.

The existing aggregate data and original absolute-performance figure remain
unchanged. Every plotted mean is checked against the frozen case-level table.
"""
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

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "experiments/main_experiment/paper_assets"
DATA = ASSETS / "five_model_data"
FIGURES = ASSETS / "figures"
QA_DIR = ROOT / "2026NAACL/SA-MCGS/manuscript_revision_20261001/m1_m3"
STEM = "fig02_scale_gain_heatmaps"
MODELS = ["gpt-4o", "gemini-2.5-pro", "qwen2.5-72b", "llama-3.1-8b", "qwen3.5-9b"]
MODEL_LABELS = ["GPT-4o", "Gemini 2.5 Pro", "Qwen2.5-72B", "Llama 3.1-8B", "Qwen3.5-9B"]
SCALES = ["small", "medium", "large"]
SCALE_LABELS = ["≤12\n(n = 36)", "14–20\n(n = 24)", "≥24\n(n = 20)"]
COUNTS = [36, 24, 20]
METRICS = ["root_at3", "risk_all"]
METRIC_LABELS = ["Root@3", "Risk-all"]
LIMIT = 65.0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signed(value: float) -> str:
    return "0.00" if abs(value) < 1e-12 else f"{value:+.2f}".replace("-", "−")


def load_cells() -> tuple[list[dict], dict]:
    source_paths = [DATA / "aggregates.json", DATA / "canonical_case_metrics.json"]
    before = {str(p.relative_to(ROOT)): sha256(p) for p in source_paths}
    aggregates = json.loads(source_paths[0].read_text())
    cases = json.loads(source_paths[1].read_text())
    assert len(cases) == 1200
    lookup = {(r["model"], r["method"], r["scale"]): r for r in aggregates["model_scale_method"]}
    cells = []
    for metric in METRICS:
        for model in MODELS:
            for scale, expected_n in zip(SCALES, COUNTS):
                absolute = {}
                uid_sets = []
                for method in ["lea", "sa-mcgs"]:
                    frozen = lookup[(model, method, scale)]
                    matched = [r for r in cases if r["model"] == model and r["method"] == method and r["scale"] == scale]
                    assert len(matched) == frozen["n"] == expected_n
                    uid_sets.append({r["case_uid"] for r in matched})
                    values = [r[metric] for r in matched]
                    assert all(value in (0, 1) for value in values)
                    numerator = int(sum(values))
                    denominator = len(values)
                    mean = numerator / denominator
                    assert denominator == frozen[f"{metric}_n"]
                    assert abs(mean - frozen[metric]) < 1e-12
                    absolute[method] = {"mean": frozen[metric], "numerator": numerator, "denominator": denominator}
                assert uid_sets[0] == uid_sets[1] and len(uid_sets[0]) == expected_n
                sa, lea = absolute["sa-mcgs"], absolute["lea"]
                delta = 100 * (sa["mean"] - lea["mean"])
                if abs(delta) < 1e-12:
                    delta = 0.0
                assert -LIMIT <= delta <= LIMIT
                cells.append({
                    "metric": metric, "model": model, "scale": scale,
                    "lea_numerator": lea["numerator"], "lea_denominator": lea["denominator"],
                    "lea_mean": lea["mean"], "lea_percent": 100 * lea["mean"],
                    "sa_mcgs_numerator": sa["numerator"], "sa_mcgs_denominator": sa["denominator"],
                    "sa_mcgs_mean": sa["mean"], "sa_mcgs_percent": 100 * sa["mean"],
                    "delta_pp": delta, "display_delta_pp": signed(delta),
                })
    assert len(cells) == 30
    assert len({(r["metric"], r["model"], r["scale"]) for r in cells}) == 30
    return cells, before


def plot(cells: list[dict]) -> dict:
    font_manager.findfont("Arial", fallback_to_default=False)
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Arial"],
        "font.size": 8.0, "axes.labelsize": 8.0, "xtick.labelsize": 7.5,
        "ytick.labelsize": 8.0, "axes.linewidth": 0.5,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
        "text.color": "#222222", "xtick.color": "#222222", "ytick.color": "#222222",
        "axes.unicode_minus": True,
    })
    cmap = colors.LinearSegmentedColormap.from_list("orange_white_blue", ["#C87736", "#FCFCFA", "#226C94"], N=257)
    norm = colors.TwoSlopeNorm(vmin=-LIMIT, vcenter=0.0, vmax=LIMIT)
    fig = plt.figure(figsize=(6.3, 2.05))
    text_entries = []
    for panel, (metric, label, left) in enumerate(zip(METRICS, METRIC_LABELS, [0.175, 0.535])):
        ax = fig.add_axes([left, 0.285, 0.303, 0.55])
        matrix = np.array([[next(r["delta_pp"] for r in cells if r["model"] == model and r["scale"] == scale and r["metric"] == metric)
                            for scale in SCALES] for model in MODELS])
        ax.pcolormesh(np.arange(4) - 0.5, np.arange(6) - 0.5, matrix,
                      cmap=cmap, norm=norm, edgecolors="white", linewidth=1.1,
                      antialiased=False, rasterized=False)
        ax.set_xlim(-0.5, 2.5)
        ax.set_ylim(4.5, -0.5)
        ax.set_xticks(range(3), SCALE_LABELS)
        ax.tick_params(axis="x", length=0, pad=5.0)
        ax.set_yticks(range(5), MODEL_LABELS if panel == 0 else [""] * 5)
        ax.tick_params(axis="y", length=0, pad=7.0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        for row in range(5):
            for col in range(3):
                value = float(matrix[row, col])
                rgb = np.asarray(cmap(norm(value))[:3])
                luminance = float(np.dot(rgb, [0.2126, 0.7152, 0.0722]))
                text_entries.append(ax.text(col, row, signed(value), ha="center", va="center", fontsize=8.3,
                                             color="white" if luminance < 0.53 else "#222222"))
        fig.text(left - 0.026, 0.925, f"({chr(97 + panel)})", fontsize=8.3,
                 fontweight="bold", va="center", ha="left")
        fig.text(left + 0.303 / 2, 0.925, label, fontsize=8.8, va="center", ha="center")
    cax = fig.add_axes([0.885, 0.285, 0.012, 0.55])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, ticks=[-65, 0, 65])
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=2.2, width=0.5, pad=3.0, labelsize=7.5)
    cb.set_label("SA-MCGS − LEA (pp)", fontsize=7.7, labelpad=7.0)
    fig.text(0.506, 0.045, "Original SCC size (nodes)", ha="center", va="center", fontsize=7.7)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bounds = fig.bbox
    escaped = []
    for text in fig.findobj(matplotlib.text.Text):
        if text.get_visible() and text.get_text():
            box = text.get_window_extent(renderer)
            if box.width > 0 and box.height > 0 and not (bounds.x0 <= box.x0 and box.x1 <= bounds.x1 and bounds.y0 <= box.y0 and box.y1 <= bounds.y1):
                escaped.append(text.get_text())
    assert not escaped, escaped
    assert len(text_entries) == 30
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{STEM}.pdf")
    fig.savefig(FIGURES / f"{STEM}.svg")
    fig.savefig(FIGURES / f"{STEM}.png", dpi=600)
    plt.close(fig)
    return {"width_in": 6.3, "height_in": 2.05, "font_minimum_pt": 7.5,
            "colour_limits_pp": [-LIMIT, LIMIT], "all_values_within_colour_limits": True,
            "rendered_cell_labels": len(text_entries), "escaped_text": escaped,
            "editable_text": True, "png_dpi": 600}


def main():
    QA_DIR.mkdir(parents=True, exist_ok=True)
    cells, before = load_cells()
    old_paths = [FIGURES / f"fig02_main_results_five_models.{extension}" for extension in ["pdf", "svg", "png"]]
    old_before = {str(p.relative_to(ROOT)): sha256(p) for p in old_paths}
    exported = QA_DIR / "scale_gain_cells.csv"
    with exported.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cells[0]))
        writer.writeheader()
        writer.writerows(cells)
    with exported.open() as handle:
        readback = list(csv.DictReader(handle))
    assert len(readback) == 30
    for original, copy in zip(cells, readback):
        assert copy["display_delta_pp"] == signed(original["delta_pp"])
        for field in ["lea_mean", "sa_mcgs_mean", "delta_pp"]:
            assert float(copy[field]) == original[field]
    geometry = plot(cells)
    after = {name: sha256(ROOT / name) for name in before}
    old_after = {name: sha256(ROOT / name) for name in old_before}
    assert before == after
    assert old_before == old_after
    manifest = {
        "source_hashes_before": before, "source_hashes_after": after, "source_data_unchanged": True,
        "old_figure_hashes_before": old_before, "old_figure_hashes_after": old_after,
        "old_absolute_figure_unchanged": True,
        "case_rows_read": 1200, "source_means_checked": 60, "plotted_cells": 30,
        "positive_cells": sum(r["delta_pp"] > 0 for r in cells),
        "zero_cells": sum(r["delta_pp"] == 0 for r in cells),
        "negative_cells": sum(r["delta_pp"] < 0 for r in cells),
        "scale_denominators": dict(zip(SCALES, COUNTS)), "model_order": MODELS,
        "counts_verified_from_case_rows": True, "csv_roundtrip_exact": True,
        "difference_rule": "100 * (unrounded SA-MCGS mean - unrounded LEA mean), then display two decimals",
        "geometry": geometry, "cell_csv_sha256": sha256(exported),
        "output_hashes": {extension: sha256(FIGURES / f"{STEM}.{extension}") for extension in ["pdf", "svg", "png"]},
    }
    (QA_DIR / "scale_gain_validation.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"cells": 30, "source_means_checked": 60, "positive": manifest["positive_cells"],
                      "zero": manifest["zero_cells"], "negative": manifest["negative_cells"],
                      "source_and_original_figure_unchanged": True}, indent=2))


if __name__ == "__main__":
    main()

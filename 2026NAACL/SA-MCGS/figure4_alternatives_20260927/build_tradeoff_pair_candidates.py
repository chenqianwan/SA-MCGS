#!/usr/bin/env python3
"""Two frozen-data alternatives: relative trade-offs and paired case outcomes.

Figure A asks whether complete risk retention improves with compression, using
all five model-level differences against each baseline. Figure D decomposes
that mean risk-retention gain into the four exact paired binary outcomes.
Both are descriptive benchmark views; no new inference, filtering, uncertainty
intervals, statistical tests, or recalculation of the accepted metric policy.
"""
from pathlib import Path
import csv
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DATA = ROOT / "experiments/main_experiment/paper_assets/five_model_data"
MODELS = ["gpt-4o", "gemini-2.5-pro", "qwen2.5-72b", "llama-3.1-8b", "qwen3.5-9b"]
LABELS = ["GPT-4o", "Gemini 2.5 Pro", "Qwen2.5-72B", "Llama 3.1-8B", "Qwen3.5-9B"]
BASELINES = ["one-shot", "lea"]
BASE_LABELS = {"one-shot": "One-shot", "lea": "LEA"}
INK = "#242424"
BLUE = "#0072B2"
ORANGE = "#D55E00"
WIDTH = 6.3


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def setup():
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5,
        "xtick.labelsize": 7, "ytick.labelsize": 7.5, "legend.fontsize": 7,
        "text.color": INK, "axes.labelcolor": INK, "axes.edgecolor": INK,
        "xtick.color": INK, "ytick.color": INK,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": .6, "xtick.major.width": .6, "ytick.major.width": .6,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    })


def export(fig, name):
    fig.savefig(OUT / f"{name}.svg")
    fig.savefig(OUT / f"{name}.pdf")
    fig.savefig(OUT / f"{name}.png", dpi=600)
    plt.close(fig)


def csv_write(name, rows):
    with (OUT / name).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def tradeoff(lookup):
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 3.25), sharex=True, sharey=True)
    fig.subplots_adjust(left=.104, right=.980, bottom=.185, top=.858, wspace=.21)
    label_positions = {
        "one-shot": [(-24, 67), (-24, 6), (5, 68), (8, 31), (-7, 44)],
        "lea": [(-24, 40), (3, -7), (6, 40), (-24, 20), (7, 8)],
    }
    model_markers = ["o", "D", "s", "^", "P"]
    rows = []
    for col, (ax, baseline) in enumerate(zip(axes, BASELINES)):
        ax.add_patch(Rectangle((0, 0), 29, 74, color="#F0F6F9", lw=0, zorder=0))
        ax.axvline(0, color="#6F6F6F", lw=.65, ls=(0, (3, 3)), zorder=1)
        ax.axhline(0, color="#6F6F6F", lw=.65, ls=(0, (3, 3)), zorder=1)
        ax.set(xlim=(-28, 29), ylim=(-12, 74), xticks=[-20, 0, 20], yticks=[0, 20, 40, 60])
        ax.set_title(f"{'ab'[col]}  Relative to {BASE_LABELS[baseline]}", loc="left", pad=10)
        for i, model in enumerate(MODELS):
            sa, base = lookup[(model, "sa-mcgs")], lookup[(model, baseline)]
            x, y = 100*(sa["compression"]-base["compression"]), 100*(sa["risk_all"]-base["risk_all"])
            rows.append({"baseline": baseline, "model": model, "delta_compression_pp": x, "delta_risk_all_pp": y})
            ax.plot(x, y, marker=model_markers[i], ms=5.3, ls="none", color=BLUE,
                    markeredgecolor="white", markeredgewidth=.65, zorder=4)
            ax.annotate(LABELS[i], xy=(x, y), xytext=label_positions[baseline][i],
                        textcoords="data", fontsize=7.1, ha="left", va="center",
                        arrowprops={"arrowstyle": "-", "lw": .45, "color": "#7B7B7B", "shrinkB": 3.5},
                        zorder=5)
    axes[0].set_ylabel("Change in Risk-all (percentage points)", labelpad=6)
    fig.text(.54, .055, "Change in compression (percentage points)", ha="center", fontsize=7.5)
    fig.text(.54, .966, "SA-MCGS minus baseline", ha="center", fontsize=8.5)
    export(fig, "candidate_A_relative_tradeoff")
    csv_write("candidate_A_values.csv", rows)
    return rows


def paired_outcomes(lookup, canonical):
    table = {(r["model"], r["method"], r["case_uid"]): r for r in canonical}
    assert len(table) == len(canonical) == 1200
    cohort = {r["case_uid"] for r in canonical}
    assert len(cohort) == 80
    categories = ["sa_only", "both", "baseline_only", "neither"]
    colors = [BLUE, "#AECFDF", ORANGE, "#E7E7E7"]
    labels = ["SA-MCGS only", "Both methods", "Baseline only", "Neither method"]
    rows = []
    for baseline in BASELINES:
        for model in MODELS:
            counts = dict.fromkeys(categories, 0)
            for uid in cohort:
                sa = table[(model, "sa-mcgs", uid)]["risk_all"]
                base = table[(model, baseline, uid)]["risk_all"]
                assert sa in (0, 1) and base in (0, 1)
                category = {(1, 0): "sa_only", (1, 1): "both", (0, 1): "baseline_only", (0, 0): "neither"}[(sa, base)]
                counts[category] += 1
            assert sum(counts.values()) == 80
            delta = 100*(counts["sa_only"]-counts["baseline_only"])/80
            frozen_delta = 100*(lookup[(model, "sa-mcgs")]["risk_all"]-lookup[(model, baseline)]["risk_all"])
            assert abs(delta-frozen_delta) < 1e-10
            rows.append({"baseline": baseline, "model": model, **counts, "n": 80, "delta_risk_all_pp": delta})
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 3.05), sharey=True)
    fig.subplots_adjust(left=.185, right=.990, bottom=.190, top=.710, wspace=.15)
    for col, (ax, baseline) in enumerate(zip(axes, BASELINES)):
        ax.set(xlim=(0, 100), ylim=(-.6, 4.6), xticks=[0, 20, 40, 60, 80])
        ax.set_yticks(range(5), LABELS[::-1])
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_bounds(0, 80)
        ax.tick_params(axis="y", length=0, pad=5)
        ax.set_xlabel("Paired cases (n = 80)", labelpad=6, fontsize=7)
        ax.set_title(f"{'ab'[col]}  Compared with {BASE_LABELS[baseline]}", loc="left", pad=10, fontsize=8)
        ax.text(90, 4.75, "Net Δ\n(pp)", ha="center", va="bottom", fontsize=6.5)
        for i, model in enumerate(MODELS):
            row = next(r for r in rows if r["baseline"] == baseline and r["model"] == model)
            left = 0
            for category, color in zip(categories, colors):
                count = row[category]
                ax.barh(4-i, count, left=left, height=.58, color=color, edgecolor="white", linewidth=.6)
                if count >= 5:
                    ax.text(left+count/2, 4-i, str(count), ha="center", va="center", fontsize=6.7,
                            color="white" if category in ("sa_only", "baseline_only") else INK)
                left += count
            delta = row["delta_risk_all_pp"]
            value = "0" if abs(delta) < 1e-10 else f"{delta:+.2f}"
            ax.text(90, 4-i, value, ha="center", va="center", fontsize=6.8,
                    color=BLUE if delta > 0 else ORANGE if delta < 0 else INK)
    fig.text(.55, .982, "Complete risk evidence: paired outcomes", ha="center", va="top", fontsize=8.5)
    handles = [Patch(facecolor=c, edgecolor="none", label=l) for c, l in zip(colors, labels)]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.54, .91),
               ncol=4, frameon=False, handlelength=1.3, handletextpad=.5, columnspacing=1.25, fontsize=6.8)
    export(fig, "candidate_D_paired_case_outcomes")
    csv_write("candidate_D_values.csv", rows)
    return rows


def main():
    setup()
    source_paths = [DATA / "aggregates.json", DATA / "canonical_case_metrics.json"]
    before = {p.name: sha(p) for p in source_paths}
    groups = json.loads(source_paths[0].read_text())
    canonical = json.loads(source_paths[1].read_text())
    lookup = {(r["model"], r["method"]): r for r in groups["model_method"]}
    a = tradeoff(lookup)
    d = paired_outcomes(lookup, canonical)
    assert {p.name: sha(p) for p in source_paths} == before
    (OUT / "candidate_AD_audit.json").write_text(json.dumps({
        "inputs_unchanged": True, "source_hashes": before,
        "candidate_A": {"model_baseline_pairs": len(a), "values_from": "Unrounded frozen means; SA-MCGS minus baseline, percentage points", "shade": "Both aggregate metrics nonnegative relative to baseline"},
        "candidate_D": {"rows": len(d), "paired_cases_per_row": 80, "four_exhaustive_outcomes": True, "net_delta_equals_frozen_risk_all_difference": True, "labels": "Segments below five cases retain their full width but omit text to avoid collisions"},
        "scientific_protocol_changed": False, "uncertainty": "No intervals; descriptive finite-benchmark summaries", "model_calls": 0,
        "backend": "python", "width_inches": 6.3, "font_minimum_pt": 6.5,
        "exports": ["Editable PDF", "Editable SVG", "600 dpi PNG"],
    }, indent=2)+"\n")
    print(json.dumps({"tradeoff_points": len(a), "paired_outcome_rows": len(d), "sources_unchanged": True}))


if __name__ == "__main__":
    main()

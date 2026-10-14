#!/usr/bin/env python3
"""Render the selected paired-case figure from frozen accepted metrics.

Question: how many matched benchmark cases gain complete risk evidence?
Panel a compares with One-shot; panel b decomposes the gains against LEA.
This quantitative grid retains all five models and all 80 cases per comparison.
Its two four-category stacked-bar panels reproduce the approved layout exactly:
6.3 by 3.05 inches, editable PDF/SVG, 600 dpi PNG, minimum text 6.5 pt.
No scientific producer, accepted metric, denominator, or uncertainty is changed.
"""
from pathlib import Path
import csv
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/main_experiment/paper_assets/figures"
RECORD = ROOT / "2026NAACL/SA-MCGS/figure4_selected_D_20260928"
APPROVED = ROOT / "2026NAACL/SA-MCGS/figure4_alternatives_20260927"
STEM = "fig03_paired_case_outcomes_five_models"
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
    with (RECORD / name).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


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
    export(fig, STEM)
    csv_write("paired_case_outcomes_values.csv", rows)
    return rows


def main():
    setup()
    OUT.mkdir(parents=True, exist_ok=True)
    RECORD.mkdir(parents=True, exist_ok=True)
    source_paths = [DATA / "aggregates.json", DATA / "canonical_case_metrics.json"]
    before = {p.name: sha(p) for p in source_paths}
    groups = json.loads(source_paths[0].read_text())
    canonical = json.loads(source_paths[1].read_text())
    lookup = {(r["model"], r["method"]): r for r in groups["model_method"]}
    rows = paired_outcomes(lookup, canonical)
    assert {p.name: sha(p) for p in source_paths} == before
    approved_csv = APPROVED / "candidate_D_values.csv"
    generated_csv = RECORD / "paired_case_outcomes_values.csv"
    assert generated_csv.read_bytes() == approved_csv.read_bytes(), "Approved paired counts changed"
    # Compare pixels rather than timestamp-bearing PDF/SVG metadata.
    from PIL import Image, ImageChops
    with Image.open(APPROVED / "candidate_D_paired_case_outcomes.png") as approved:
        with Image.open(OUT / f"{STEM}.png") as generated:
            assert approved.size == generated.size
            assert ImageChops.difference(approved.convert("RGB"), generated.convert("RGB")).getbbox() is None
    audit = {
        "adaptation": "Exact reuse of approved candidate D; production output paths only",
        "inputs_unchanged": True, "source_hashes": before,
        "rows": len(rows), "paired_cases_per_row": 80,
        "four_exhaustive_outcomes": True,
        "net_delta_equals_frozen_risk_all_difference": True,
        "csv_identical_to_approved": True, "png_pixels_identical_to_approved": True,
        "approved_csv_sha256": sha(approved_csv),
        "scientific_protocol_changed": False, "model_calls": 0,
        "uncertainty": "None; descriptive counts on the fixed finite benchmark",
        "labels": "Segments below five cases retain full width but omit text to avoid collisions",
        "backend": "python", "width_inches": 6.3, "height_inches": 3.05,
        "font_minimum_pt": 6.5,
        "exports": {ext: {"path": str((OUT / f"{STEM}.{ext}").relative_to(ROOT)),
                           "sha256": sha(OUT / f"{STEM}.{ext}")} for ext in ("pdf", "svg", "png")},
    }
    (RECORD / "paired_case_outcomes_audit.json").write_text(json.dumps(audit, indent=2)+"\n")
    print(json.dumps({"paired_outcome_rows": len(rows), "sources_unchanged": True,
                      "csv_identical_to_approved": True, "png_pixels_identical_to_approved": True}))


if __name__ == "__main__":
    main()

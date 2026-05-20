#!/usr/bin/env python3
"""Build paper-facing figures, tables, and a bilingual annotation pack.

This script is intentionally read-only with respect to raw experiment outputs.
It consolidates the locked main experiment assets into a stable directory that
can be referenced from the paper without mixing in diagnostic or smoke runs.
"""
from __future__ import annotations

import csv
import html
import json
import math
import re
import shutil
import sys
import textwrap
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import matplotlib.patches as patches


ROOT = Path(__file__).resolve().parents[2]
MAIN_DIR = ROOT / "experiments" / "main_experiment"
SUPP_DIR = MAIN_DIR / "supplements"
SUPP_FIG_DIR = SUPP_DIR / "figures"
SUPP_TABLE_DIR = SUPP_DIR / "tables"
CROSS_DIR = ROOT / "experiments" / "cross_domain"
RESULTS_DIR = CROSS_DIR / "results"
DEMO_HTML = ROOT / "static" / "demo.html"

ASSET_DIR = MAIN_DIR / "paper_assets"
FIG_DIR = ASSET_DIR / "figures"
TABLE_DIR = ASSET_DIR / "tables"
ANNOT_DIR = ASSET_DIR / "human_annotation_pack"
ANNOT_MATERIAL_DIR = ANNOT_DIR / "materials"

sys.path.insert(0, str(CROSS_DIR))
import final_results_dashboard as dash  # noqa: E402
from progress_dashboard import _metric_values  # noqa: E402


METHODS = ["naive", "sa-mcgs"]
METRIC_KEYS = ["root", "risk_any", "risk_all", "compression"]
METRIC_LABELS = {
    "root": "Root@3",
    "risk_any": "Risk-any",
    "risk_all": "Risk-all",
    "compression": "Compression",
    "effective_compression": "Effective compression",
}
DOMAIN_LABELS = {
    "debian": "Debian packages",
    "sec_ex21": "SEC EX-21 subsidiaries",
    "bgb": "German Civil Code (BGB)",
    "cuad": "CUAD contracts",
}
TEMPLATE_LABELS = {
    "direct_mutex": "Direct mutual exclusion",
    "handoff_invariant": "Handoff invariant",
    "temporal_gate": "Temporal gate",
    "condition_trigger": "Condition trigger",
}
PAPER_COLORS = {
    "naive": "#ff6b6b",
    "sa": "#20c997",
    "blue": "#2563eb",
    "purple": "#7c3aed",
    "orange": "#f97316",
    "gray": "#64748b",
    "dark": "#0f172a",
    "grid": "#dbe3ef",
}


def ensure_dirs() -> None:
    for directory in (ASSET_DIR, FIG_DIR, FIG_DIR / "archive", TABLE_DIR, ANNOT_DIR, ANNOT_MATERIAL_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def pct(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.{digits}f}%"


def rate_text(num: int, den: int) -> str:
    if den <= 0:
        return "-"
    return f"{num}/{den} ({num / den:.0%})"


def fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value)


def method_records(records: Iterable[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    return [record for record in records if record.get("method") == method]


def case_key(record: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(record.get("domain", "")),
        str(record.get("scc_id", "")),
        str(record.get("scc_size", "")),
        str(record.get("model", "")),
        str(record.get("_task_template") or record.get("injected_conflict_family") or ""),
        str(record.get("_task_severity") or record.get("injected_conflict_severity") or ""),
        str(record.get("_task_compression_profile") or record.get("mcgs_compression_profile") or "current"),
    )


def template_name(record: dict[str, Any]) -> str:
    return str(record.get("_task_template") or record.get("injected_conflict_family") or "")


def severity_name(record: dict[str, Any]) -> str:
    return str(record.get("_task_severity") or record.get("injected_conflict_severity") or "")


def load_current_records() -> list[dict[str, Any]]:
    return dash._load_selected(dash.CURRENT_STATUS_FILES, "current")


def summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return dash._metric_summary(records)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_md_table(path: Path, title: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text(f"# {title}\n\nNo rows.\n", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    lines = [f"# {title}", "", "| " + " | ".join(fields) + " |", "|" + "|".join(["---"] * len(fields)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(field, "")) for field in fields) + " |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def savefig(fig: plt.Figure, stem: str) -> None:
    for suffix in ("png", "pdf"):
        fig.savefig(FIG_DIR / f"{stem}.{suffix}", dpi=260, bbox_inches="tight")
    plt.close(fig)


def set_axis_style(ax: plt.Axes, *, ylim: tuple[float, float] | None = (0, 1.05), ylabel: str | None = None) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color=PAPER_COLORS["grid"], linewidth=0.8, alpha=0.75)
    ax.set_axisbelow(True)
    if ylim is not None:
        ax.set_ylim(*ylim)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10, color=PAPER_COLORS["dark"])
    ax.tick_params(labelsize=9, colors="#334155")


def pct_label(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.{digits}f}%"


def method_summary_map(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {method: summary(method_records(records, method)) for method in METHODS}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def copy_supplement_figure(source_stem: str, target_stem: str) -> None:
    for suffix in ("png", "pdf"):
        src = SUPP_FIG_DIR / f"{source_stem}.{suffix}"
        if src.exists():
            shutil.copy2(src, FIG_DIR / f"{target_stem}.{suffix}")


def copy_supplement_table(source_name: str, target_name: str) -> None:
    src = SUPP_TABLE_DIR / source_name
    if src.exists():
        shutil.copy2(src, TABLE_DIR / target_name)


def create_pipeline_figure() -> None:
    fig, ax = plt.subplots(figsize=(13.2, 4.6))
    ax.axis("off")
    boxes = [
        ("Document graph", "records + typed links"),
        ("SCC extraction", "Tarjan / SCC filter"),
        ("Local rollouts", "small windows, shared risk rubric"),
        ("Evidence memory", "relation-first ledgers"),
        ("Dynamic core", "retain critical endpoints"),
        ("Collapsed node", "risk subgraph as evaluation point"),
    ]
    x0, w, h, gap = 0.03, 0.145, 0.48, 0.025
    y = 0.28
    colors = ["#e0f2fe", "#dbeafe", "#dcfce7", "#ede9fe", "#fee2e2", "#fef3c7"]
    for i, ((title, subtitle), color) in enumerate(zip(boxes, colors)):
        x = x0 + i * (w + gap)
        rect = patches.FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.018,rounding_size=0.025",
            linewidth=1.6,
            edgecolor="#334155",
            facecolor=color,
        )
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h * 0.62, title, ha="center", va="center", fontsize=12.5, weight="bold", color="#0f172a")
        ax.text(x + w / 2, y + h * 0.35, subtitle, ha="center", va="center", fontsize=9.5, color="#334155")
        if i < len(boxes) - 1:
            ax.annotate(
                "",
                xy=(x + w + gap * 0.74, y + h / 2),
                xytext=(x + w + gap * 0.18, y + h / 2),
                arrowprops=dict(arrowstyle="->", color="#475569", lw=1.8),
            )
    ax.text(
        0.5,
        0.92,
        "SA-MCGS turns cyclic structural reasoning into a compact, inspectable risk subgraph",
        ha="center",
        va="center",
        fontsize=15.5,
        weight="bold",
        color="#0f172a",
    )
    ax.text(
        0.5,
        0.08,
        "The LLM risk semantics stay shared; the algorithm changes the unit of search from a full cyclic graph to repeated local evidence updates.",
        ha="center",
        va="center",
        fontsize=10.5,
        color="#475569",
    )
    savefig(fig, "archive/fig_old_simplified_pipeline")


def create_demo_architecture_figure() -> None:
    """Export the architecture diagram embedded in static/demo.html.

    The frontend version is the canonical Figure 1 because it captures the
    three-contribution narrative and plugin architecture more faithfully than
    the compact fallback pipeline sketch above.
    """
    if not DEMO_HTML.exists():
        return
    text = DEMO_HTML.read_text(encoding="utf-8")
    title = "SA-MCGS Framework Architecture"
    title_idx = text.find(title)
    if title_idx < 0:
        return
    svg_start = text.find("<svg", title_idx)
    svg_end = text.find("</svg>", svg_start)
    if svg_start < 0 or svg_end < 0:
        return
    raw_svg = text[svg_start : svg_end + len("</svg>")]
    raw_svg = re.sub(r"<svg\\b", '<svg xmlns="http://www.w3.org/2000/svg"', raw_svg, count=1)

    inner_svg = raw_svg[raw_svg.find(">") + 1 : raw_svg.rfind("</svg>")]

    # Keep the card shell from the demo so the figure matches the frontend view.
    # Use a transformed group rather than a nested SVG: some renderers
    # (including QuickLook) clip nested SVG content inconsistently.
    standalone = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1960" height="1220" viewBox="0 0 1960 1220">
  <rect width="1960" height="1220" fill="#0a0e1a"/>
  <rect x="44" y="44" width="1872" height="1132" rx="28" fill="#111827" stroke="#3730a3" stroke-width="2.5"/>
  <text x="980" y="118" text-anchor="middle" fill="#e2e8f0" font-family="Inter, Arial, sans-serif" font-size="44" font-weight="900">SA-MCGS Framework Architecture</text>
  <g transform="translate(90 170) scale(1.8163265 1.65)">
    {inner_svg}
  </g>
</svg>
"""
    # The demo HTML can contain HTML-only named entities. A standalone SVG is
    # parsed as XML, where those names are not guaranteed to exist.
    for entity, replacement in {
        "&rarr;": "→",
        "&middot;": "·",
        "&mdash;": "—",
    }.items():
        standalone = standalone.replace(entity, replacement)
    (FIG_DIR / "fig01_sa_mcgs_framework_architecture.svg").write_text(standalone, encoding="utf-8")
    (FIG_DIR / "fig01_sa_mcgs_framework_architecture_render.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Figure 1</title>"
        "<style>body{margin:0;background:#0a0e1a;display:grid;place-items:center;min-height:100vh}</style>"
        + standalone,
        encoding="utf-8",
    )


def create_main_metrics_figure(records: list[dict[str, Any]]) -> None:
    summaries = method_summary_map(records)
    naive = summaries["naive"]
    sa = summaries["sa-mcgs"]

    fig = plt.figure(figsize=(12.8, 7.6))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.18, 1], height_ratios=[1, 1.05], wspace=0.28, hspace=0.42)
    fig.suptitle("Main critical SCC experiment: accuracy, reliability, and compression", fontsize=17, weight="bold", y=0.99)

    # Panel A: strict hit rates.
    ax = fig.add_subplot(gs[0, 0])
    metrics = ["root", "risk_any", "risk_all"]
    labels = [METRIC_LABELS[m] for m in metrics]
    x = list(range(len(metrics)))
    width = 0.34
    naive_vals = [naive[m] for m in metrics]
    sa_vals = [sa[m] for m in metrics]
    ax.bar([i - width / 2 for i in x], naive_vals, width, color=PAPER_COLORS["naive"], label="Naive")
    ax.bar([i + width / 2 for i in x], sa_vals, width, color=PAPER_COLORS["sa"], label="SA-MCGS")
    for i, (nv, sv) in enumerate(zip(naive_vals, sa_vals)):
        ax.text(i - width / 2, nv + 0.025, pct_label(nv), ha="center", fontsize=9, weight="bold", color="#9f1239")
        ax.text(i + width / 2, sv + 0.025, pct_label(sv), ha="center", fontsize=9, weight="bold", color="#047857")
        ax.text(i, min(1.03, max(nv, sv) + 0.055), f"+{(sv - nv) * 100:.0f} pts", ha="center", fontsize=8.5, color="#334155")
    ax.set_xticks(x, labels)
    ax.set_title("A. Strict hit rates count parsing/API failures as failures", loc="left", fontsize=11, weight="bold")
    ax.legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(0.0, 1.08), ncol=2)
    set_axis_style(ax, ylabel="Strict rate")

    # Panel B: reliability and compression cost.
    ax = fig.add_subplot(gs[0, 1])
    rows = [
        ("No-error rate", 1 - naive["errors"] / naive["n"], 1 - sa["errors"] / sa["n"], "higher is better"),
        ("Compression", naive["compression"], sa["compression"], "higher is smaller subgraph"),
        ("Core fraction", naive["avg_subgraph"] / 34.0, sa["avg_subgraph"] / 34.0, "lower means smaller retained core"),
    ]
    y = list(range(len(rows)))
    ax.barh([i + 0.18 for i in y], [r[1] for r in rows], 0.32, color=PAPER_COLORS["naive"], label="Naive")
    ax.barh([i - 0.18 for i in y], [r[2] for r in rows], 0.32, color=PAPER_COLORS["sa"], label="SA-MCGS")
    for i, (_label, nv, sv, note) in enumerate(rows):
        ax.text(nv + 0.02, i + 0.18, pct_label(nv), va="center", fontsize=8.5, color="#9f1239", weight="bold")
        ax.text(sv + 0.02, i - 0.18, pct_label(sv), va="center", fontsize=8.5, color="#047857", weight="bold")
        ax.text(0.02, i + 0.46, note, fontsize=7.4, color="#64748b")
    ax.set_yticks(y, [r[0] for r in rows])
    ax.set_xlim(0, 1.05)
    ax.set_title("B. Reliability makes the strict metric conservative", loc="left", fontsize=11, weight="bold")
    set_axis_style(ax, ylim=None, ylabel=None)

    # Panel C: model-level Risk-all.
    ax = fig.add_subplot(gs[1, 0])
    model_labels: list[str] = []
    naive_model: list[float] = []
    sa_model: list[float] = []
    for model in dash.MODEL_ORDER:
        model_labels.append(dash.MODEL_LABEL.get(model, model))
        naive_model.append(summary([r for r in records if r.get("model") == model and r.get("method") == "naive"])["risk_all"])
        sa_model.append(summary([r for r in records if r.get("model") == model and r.get("method") == "sa-mcgs"])["risk_all"])
    x = list(range(len(model_labels)))
    ax.bar([i - width / 2 for i in x], naive_model, width, color=PAPER_COLORS["naive"], alpha=0.9)
    ax.bar([i + width / 2 for i in x], sa_model, width, color=PAPER_COLORS["sa"], alpha=0.95)
    for i, (nv, sv) in enumerate(zip(naive_model, sa_model)):
        ax.text(i - width / 2, nv + 0.025, pct_label(nv), ha="center", fontsize=8, color="#9f1239", weight="bold")
        ax.text(i + width / 2, sv + 0.025, pct_label(sv), ha="center", fontsize=8, color="#047857", weight="bold")
    ax.set_xticks(x, model_labels, rotation=15, ha="right")
    ax.set_title("C. Risk-all is harder but improves across models", loc="left", fontsize=11, weight="bold")
    set_axis_style(ax, ylabel="Risk-all rate")

    # Panel D: domain-level Risk-all with error overlay.
    ax = fig.add_subplot(gs[1, 1])
    domain_labels: list[str] = []
    naive_domain: list[float] = []
    sa_domain: list[float] = []
    naive_errors: list[float] = []
    for domain in dash.DOMAIN_ORDER:
        domain_labels.append(dash.DOMAIN_LABEL.get(domain, domain))
        nrs = [r for r in records if r.get("domain") == domain and r.get("method") == "naive"]
        srs = [r for r in records if r.get("domain") == domain and r.get("method") == "sa-mcgs"]
        ns, ss = summary(nrs), summary(srs)
        naive_domain.append(ns["risk_all"])
        sa_domain.append(ss["risk_all"])
        naive_errors.append(ns["errors"] / ns["n"] if ns["n"] else 0)
    x = list(range(len(domain_labels)))
    ax.bar([i - width / 2 for i in x], naive_domain, width, color=PAPER_COLORS["naive"], alpha=0.9)
    ax.bar([i + width / 2 for i in x], sa_domain, width, color=PAPER_COLORS["sa"], alpha=0.95)
    ax.plot(x, naive_errors, color=PAPER_COLORS["gray"], marker="o", linewidth=1.6, label="Naive error rate")
    for i, err in enumerate(naive_errors):
        if err > 0:
            ax.text(i, err + 0.04, f"err {err:.0%}", ha="center", fontsize=7.5, color="#475569")
    ax.set_xticks(x, domain_labels, rotation=15, ha="right")
    ax.set_title("D. Domain view separates task difficulty from output errors", loc="left", fontsize=11, weight="bold")
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    set_axis_style(ax, ylabel="Risk-all / error rate")

    fig.text(
        0.5,
        0.005,
        f"N={naive['n']} cases per method. Naive errors={naive['errors']}; SA-MCGS errors={sa['errors']}. "
        f"SA gains Root@3 +{(sa['root'] - naive['root']) * 100:.0f}, Risk-any +{(sa['risk_any'] - naive['risk_any']) * 100:.0f}, Risk-all +{(sa['risk_all'] - naive['risk_all']) * 100:.0f} points.",
        ha="center",
        fontsize=9,
        color="#334155",
    )
    savefig(fig, "fig02_main_metrics_strict")


def create_scc_size_figure(records: list[dict[str, Any]]) -> None:
    rows = dash._size_trend_rows(records)
    sizes = [row["size"] for row in rows]
    naive_all = [row["naive"]["risk_all"] for row in rows]
    sa_all = [row["sa"]["risk_all"] for row in rows]
    naive_root = [row["naive"]["root"] for row in rows]
    sa_root = [row["sa"]["root"] for row in rows]
    naive_comp = [row["naive"]["compression"] for row in rows]
    sa_comp = [row["sa"]["compression"] for row in rows]
    counts = [row["naive"]["n"] for row in rows]

    fig = plt.figure(figsize=(12.5, 7.4))
    gs = fig.add_gridspec(2, 2, wspace=0.28, hspace=0.42)
    fig.suptitle("Effect by SCC size: SA-MCGS is strongest on longer cyclic contexts", fontsize=16, weight="bold", y=0.99)

    ax = fig.add_subplot(gs[0, 0])
    ax.plot(sizes, naive_all, "-o", color=PAPER_COLORS["naive"], label="Naive Risk-all")
    ax.plot(sizes, sa_all, "-o", color=PAPER_COLORS["sa"], label="SA Risk-all")
    ax.fill_between(sizes, naive_all, sa_all, where=[s >= n for s, n in zip(sa_all, naive_all)], color=PAPER_COLORS["sa"], alpha=0.12)
    ax.set_title("A. Both endpoints retained", loc="left", fontsize=11, weight="bold")
    ax.set_xlabel("SCC size")
    ax.legend(frameon=False, fontsize=8)
    set_axis_style(ax, ylabel="Risk-all rate")

    ax = fig.add_subplot(gs[0, 1])
    deltas_all = [s - n for s, n in zip(sa_all, naive_all)]
    deltas_root = [s - n for s, n in zip(sa_root, naive_root)]
    ax.axhline(0, color="#94a3b8", linewidth=1)
    ax.bar([s - 0.18 for s in sizes], deltas_all, width=0.34, color=PAPER_COLORS["purple"], label="Δ Risk-all")
    ax.bar([s + 0.18 for s in sizes], deltas_root, width=0.34, color=PAPER_COLORS["blue"], label="Δ Root@3")
    ax.set_title("B. SA-MCGS gain by size", loc="left", fontsize=11, weight="bold")
    ax.set_xlabel("SCC size")
    ax.legend(frameon=False, fontsize=8)
    set_axis_style(ax, ylim=(-0.35, 0.85), ylabel="SA - Naive")

    ax = fig.add_subplot(gs[1, 0])
    ax.plot(sizes, naive_comp, "--o", color=PAPER_COLORS["naive"], label="Naive")
    ax.plot(sizes, sa_comp, "-o", color=PAPER_COLORS["sa"], label="SA-MCGS")
    ax.set_title("C. Compression stays meaningful as SCCs grow", loc="left", fontsize=11, weight="bold")
    ax.set_xlabel("SCC size")
    ax.legend(frameon=False, fontsize=8)
    set_axis_style(ax, ylabel="Compression ratio")

    ax = fig.add_subplot(gs[1, 1])
    bucket_rows = dash._size_bucket_rows(records)
    bucket_names = [row["bucket"] for row in bucket_rows]
    bucket_x = list(range(len(bucket_names)))
    bucket_naive = [row["naive"]["risk_all"] for row in bucket_rows]
    bucket_sa = [row["sa"]["risk_all"] for row in bucket_rows]
    bucket_n = [row["naive"]["n"] for row in bucket_rows]
    width = 0.34
    ax.bar([i - width / 2 for i in bucket_x], bucket_naive, width, color=PAPER_COLORS["naive"], label="Naive")
    ax.bar([i + width / 2 for i in bucket_x], bucket_sa, width, color=PAPER_COLORS["sa"], label="SA-MCGS")
    for i, n in enumerate(bucket_n):
        ax.text(i, 1.03, f"n={n}", ha="center", fontsize=8, color="#475569")
    ax.set_xticks(bucket_x, bucket_names)
    ax.set_title("D. Bucketed view for paper table/caption", loc="left", fontsize=11, weight="bold")
    ax.legend(frameon=False, fontsize=8)
    set_axis_style(ax, ylabel="Risk-all rate")

    savefig(fig, "fig03_main_by_scc_size")


def convergence_series_with_root(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_rollout: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("method") != "sa-mcgs":
            continue
        root = record.get("injected_node")
        trace = record.get("convergence_trace")
        if not isinstance(trace, list):
            continue
        for point in trace:
            if not isinstance(point, dict):
                continue
            try:
                rollout = int(point.get("rollout") or 0)
            except Exception:
                continue
            if rollout <= 0:
                continue
            subgraph_nodes = set(point.get("subgraph_nodes") or [])
            row = dict(point)
            row["root_retained"] = bool(root and root in subgraph_nodes)
            by_rollout[rollout].append(row)

    rows: list[dict[str, Any]] = []
    for rollout in sorted(by_rollout):
        points = by_rollout[rollout]
        rows.append(
            {
                "rollout": rollout,
                "n": len(points),
                "root": sum(1 for p in points if p.get("root_retained")) / len(points),
                "risk_any": sum(1 for p in points if dash._truthy(p.get("risk_any")) is True) / len(points),
                "risk_all": sum(1 for p in points if dash._truthy(p.get("risk_all")) is True) / len(points),
                "effective_oc": sum(1 for p in points if dash._truthy(p.get("effective_oc")) is True) / len(points),
                "compression": sum(float(p.get("compression_ratio") or 0) for p in points) / len(points),
                "risk_coverage": sum(float(p.get("risk_coverage") or 0) for p in points) / len(points),
                "valuable_coverage": sum(float(p.get("valuable_coverage") or 0) for p in points) / len(points),
            }
        )
    return rows


def value_at_budget(series: list[dict[str, Any]], key: str, budget: int) -> float | None:
    candidates = [row for row in series if int(row["rollout"]) <= budget and row.get(key) is not None]
    if not candidates:
        return None
    return float(candidates[-1][key])


def create_budget_convergence_figure(records: list[dict[str, Any]]) -> None:
    series = convergence_series_with_root(records)
    if not series:
        return
    rollouts = [row["rollout"] for row in series]
    budgets = [5, 10, 20, 30, 60]

    fig = plt.figure(figsize=(12.5, 7.4))
    gs = fig.add_gridspec(2, 2, wspace=0.28, hspace=0.42)
    fig.suptitle("SA-MCGS convergence over rollout budget", fontsize=16, weight="bold", y=0.99)

    ax = fig.add_subplot(gs[0, 0])
    line_specs = [
        ("root", "Root retained", PAPER_COLORS["blue"]),
        ("risk_any", "Risk-any", PAPER_COLORS["sa"]),
        ("risk_all", "Risk-all", PAPER_COLORS["purple"]),
        ("effective_oc", "Effective OC", PAPER_COLORS["orange"]),
    ]
    for key, label, color in line_specs:
        vals = [row[key] for row in series]
        ax.plot(rollouts, vals, linewidth=2.2, color=color, label=label)
    for b in budgets:
        ax.axvline(b, color="#cbd5e1", linewidth=0.7, linestyle=":")
    ax.set_title("A. More rollouts recover more structural evidence", loc="left", fontsize=11, weight="bold")
    ax.set_xlabel("Rollout budget")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    set_axis_style(ax, ylabel="Rate")

    ax = fig.add_subplot(gs[0, 1])
    comp = [row["compression"] for row in series]
    risk_cov = [row["risk_coverage"] for row in series]
    val_cov = [row["valuable_coverage"] for row in series]
    ax.plot(rollouts, comp, color=PAPER_COLORS["gray"], linewidth=2.0, label="Compression")
    ax.plot(rollouts, risk_cov, color=PAPER_COLORS["blue"], linewidth=2.0, label="Risk coverage")
    ax.plot(rollouts, val_cov, color=PAPER_COLORS["orange"], linewidth=2.0, label="Valuable coverage")
    ax.set_title("B. Coverage improves while compression remains bounded", loc="left", fontsize=11, weight="bold")
    ax.set_xlabel("Rollout budget")
    ax.legend(frameon=False, fontsize=8)
    set_axis_style(ax, ylabel="Rate / coverage")

    ax = fig.add_subplot(gs[1, 0])
    x = list(range(len(budgets)))
    risk_all_prefix = [value_at_budget(series, "risk_all", b) or 0 for b in budgets]
    root_prefix = [value_at_budget(series, "root", b) or 0 for b in budgets]
    width = 0.35
    ax.bar([i - width / 2 for i in x], root_prefix, width, color=PAPER_COLORS["blue"], label="Root retained")
    ax.bar([i + width / 2 for i in x], risk_all_prefix, width, color=PAPER_COLORS["purple"], label="Risk-all")
    for i, v in enumerate(risk_all_prefix):
        ax.text(i + width / 2, v + 0.025, pct_label(v), ha="center", fontsize=8, weight="bold", color=PAPER_COLORS["purple"])
    ax.set_xticks(x, [str(b) for b in budgets])
    ax.set_title("C. Prefix budgets: what the paper can cite", loc="left", fontsize=11, weight="bold")
    ax.set_xlabel("Budget prefix")
    ax.legend(frameon=False, fontsize=8)
    set_axis_style(ax, ylabel="Rate")

    ax = fig.add_subplot(gs[1, 1])
    for model in dash.MODEL_ORDER:
        subset = [r for r in records if r.get("method") == "sa-mcgs" and r.get("model") == model]
        m_series = convergence_series_with_root(subset)
        if not m_series:
            continue
        ax.plot([r["rollout"] for r in m_series], [r["risk_all"] for r in m_series], linewidth=1.8, label=dash.MODEL_LABEL.get(model, model))
    ax.set_title("D. Risk-all convergence by model", loc="left", fontsize=11, weight="bold")
    ax.set_xlabel("Rollout budget")
    ax.legend(frameon=False, fontsize=7.5, ncol=2)
    set_axis_style(ax, ylabel="Risk-all rate")

    savefig(fig, "fig04_budget_prefix_convergence")


def create_compression_tradeoff_figure(records: list[dict[str, Any]]) -> None:
    current_rows = []
    for method in METHODS:
        s = summary([r for r in records if r.get("method") == method])
        current_rows.append({"profile": "current/default", "method": method, **s})

    e3_rows = read_csv_rows(SUPP_TABLE_DIR / "E3_compression_profile_ablation.csv")
    rows: list[dict[str, Any]] = []
    for row in e3_rows:
        try:
            rows.append(
                {
                    "profile": row["profile"],
                    "method": row["method"],
                    "root": float(row["root_at_3"]),
                    "risk_any": float(row["risk_any"]),
                    "risk_all": float(row["risk_all"]),
                    "compression": float(row["compression"]),
                    "avg_subgraph": float(row["avg_subgraph"]),
                    "n": int(float(row["n"])),
                }
            )
        except Exception:
            continue
    if not rows:
        for row in current_rows:
            rows.append(
                {
                    "profile": row["profile"],
                    "method": row["method"],
                    "root": row["root"],
                    "risk_any": row["risk_any"],
                    "risk_all": row["risk_all"],
                    "compression": row["compression"],
                    "avg_subgraph": row["avg_subgraph"],
                    "n": row["n"],
                }
            )

    fig = plt.figure(figsize=(12.4, 6.8))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.1, 1], wspace=0.3)
    fig.suptitle("Compression profile trade-off: smaller subgraphs are not free", fontsize=16, weight="bold", y=1.01)

    ax = fig.add_subplot(gs[0, 0])
    marker_map = {"naive": "o", "sa-mcgs": "s"}
    color_map = {"naive": PAPER_COLORS["naive"], "sa-mcgs": PAPER_COLORS["sa"]}
    for row in rows:
        label = f"{row['method']} · {row['profile'].replace('/default', '')}"
        size = 90 + 160 * float(row["root"] or 0)
        ax.scatter(
            row["compression"],
            row["risk_all"],
            s=size,
            marker=marker_map.get(row["method"], "o"),
            color=color_map.get(row["method"], PAPER_COLORS["gray"]),
            edgecolor="white",
            linewidth=0.8,
            alpha=0.9,
            label=label,
        )
        ax.text(row["compression"] + 0.01, row["risk_all"] + 0.01, label, fontsize=8, color="#334155")
    ax.set_xlabel("Compression ratio (higher = smaller subgraph)")
    ax.set_ylabel("Risk-all retention")
    ax.set_xlim(0.45, 0.72)
    ax.set_ylim(0.42, 0.84)
    ax.set_title("A. Pareto view: retention vs subgraph size", loc="left", fontsize=11, weight="bold")
    set_axis_style(ax, ylim=(0.42, 0.84), ylabel=None)

    ax = fig.add_subplot(gs[0, 1])
    sa_rows = [r for r in rows if r["method"] == "sa-mcgs"]
    sa_rows.sort(key=lambda r: str(r["profile"]))
    labels = [r["profile"].replace("/default", "") for r in sa_rows]
    x = list(range(len(sa_rows)))
    width = 0.26
    ax.bar([i - width for i in x], [r["root"] for r in sa_rows], width, color=PAPER_COLORS["blue"], label="Root@3")
    ax.bar(x, [r["risk_all"] for r in sa_rows], width, color=PAPER_COLORS["purple"], label="Risk-all")
    ax.bar([i + width for i in x], [r["compression"] for r in sa_rows], width, color=PAPER_COLORS["orange"], label="Compression")
    for i, r in enumerate(sa_rows):
        ax.text(i, max(r["root"], r["risk_all"], r["compression"]) + 0.035, f"avg core {r['avg_subgraph']:.1f}", ha="center", fontsize=8, color="#475569")
    ax.set_xticks(x, labels)
    ax.set_title("B. SA profile choice: current/default favors risk retention", loc="left", fontsize=11, weight="bold")
    ax.legend(frameon=False, fontsize=8)
    set_axis_style(ax, ylabel="Rate")

    savefig(fig, "fig05_compression_profile_tradeoff")


def create_case_study_figure(records: list[dict[str, Any]]) -> None:
    by_case: dict[tuple[str, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        if record.get("method") in METHODS:
            by_case[case_key(record)][str(record.get("method"))] = record

    candidates: list[tuple[int, dict[str, Any], dict[str, Any] | None]] = []
    for pair in by_case.values():
        sa = pair.get("sa-mcgs")
        if not sa:
            continue
        sm = _metric_values(sa)
        naive = pair.get("naive")
        nm = _metric_values(naive) if naive else {}
        size = int(sa.get("scc_size") or 0)
        if size < 20 or sm.get("risk_all") is not True:
            continue
        score = 0
        if sa.get("domain") == "bgb":
            score += 5
        if nm.get("risk_all") is not True:
            score += 4
        if nm.get("root_top3") is not True:
            score += 2
        score += int((sm.get("compression") or 0) * 10)
        candidates.append((score, sa, naive))
    if not candidates:
        return
    candidates.sort(key=lambda item: item[0], reverse=True)
    record = candidates[0][1]
    naive_record = candidates[0][2]

    nodes = list(record.get("scc_clause_ids") or [])
    if not nodes:
        nodes = list((record.get("node_names") or {}).keys())
    nodes = nodes[: max(1, min(len(nodes), 30))]
    root = record.get("injected_node")
    witness = record.get("injected_witness_node")
    affected = set(record.get("injected_affected_nodes") or [])
    core = set(record.get("core_evidence_risk_subgraph_nodes") or record.get("risk_subgraph_nodes") or [])
    risk = {n for n in [root, witness] if n}

    fig = plt.figure(figsize=(12.4, 7.3))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.05, 1], width_ratios=[1.28, 1, 0.92], hspace=0.36, wspace=0.3)
    title = f"Case study: collapsing a {record.get('scc_size')}-node BGB SCC into an inspectable risk core"
    fig.suptitle(title, fontsize=16, weight="bold", y=0.99)

    # Panel A: SCC context as a linearized cycle.
    ax = fig.add_subplot(gs[0, :2])
    ax.set_title("A. Original SCC context: risk endpoints are far apart inside a legal-reference cycle", loc="left", fontsize=11, weight="bold")
    ax.axis("off")
    n = len(nodes)
    xs = [i / max(1, n - 1) for i in range(n)]
    y = 0.48
    ax.plot([0, 1], [y, y], color="#cbd5e1", linewidth=2.2, zorder=0)
    for i, node in enumerate(nodes):
        x = xs[i]
        if node in risk:
            face, size, label = PAPER_COLORS["naive"], 175, "risk endpoint"
        elif node in affected:
            face, size, label = PAPER_COLORS["orange"], 125, "affected"
        elif node in core:
            face, size, label = PAPER_COLORS["sa"], 120, "core"
        else:
            face, size, label = "#e2e8f0", 42, "context"
        ax.scatter([x], [y], s=size, color=face, edgecolor="#334155", linewidth=0.8, zorder=2)
        if node in risk or node in affected or node in core:
            short = node.replace("bgb_", "§")
            ax.text(x, y + (0.16 if i % 2 == 0 else -0.18), short, ha="center", va="center", fontsize=7.5, color="#0f172a")
    ax.annotate("cycle continues", xy=(1, y), xytext=(0.84, y + 0.23), arrowprops=dict(arrowstyle="->", color="#64748b"), fontsize=8, color="#475569")
    legend_items = [("root/witness", PAPER_COLORS["naive"]), ("affected", PAPER_COLORS["orange"]), ("final core", PAPER_COLORS["sa"]), ("other SCC node", "#e2e8f0")]
    for i, (label, color) in enumerate(legend_items):
        ax.scatter([0.02 + i * 0.21], [0.08], s=70, color=color, edgecolor="#334155")
        ax.text(0.045 + i * 0.21, 0.08, label, va="center", fontsize=8.5, color="#334155")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(0, 1)

    # Panel B: final core node list.
    ax = fig.add_subplot(gs[0, 2])
    ax.set_title("B. Final dynamic core", loc="left", fontsize=11, weight="bold")
    ax.axis("off")
    size = int(record.get("scc_size") or len(nodes) or 1)
    core_nodes = list(core)
    compression = _metric_values(record).get("compression")
    ax.text(0.0, 0.9, f"{len(core_nodes)}/{size} nodes retained", fontsize=18, weight="bold", color=PAPER_COLORS["dark"])
    ax.text(0.0, 0.78, f"compression = {pct_label(compression)}", fontsize=12, color="#475569")
    ax.text(0.0, 0.62, "Core contains:", fontsize=10, weight="bold", color=PAPER_COLORS["dark"])
    for i, node in enumerate(core_nodes[:10]):
        color = PAPER_COLORS["naive"] if node in risk else PAPER_COLORS["orange"] if node in affected else PAPER_COLORS["sa"]
        ax.add_patch(patches.FancyBboxPatch((0.0, 0.54 - i * 0.06), 0.82, 0.042, boxstyle="round,pad=0.008,rounding_size=0.012", facecolor=color, alpha=0.16, edgecolor=color, linewidth=0.8))
        ax.text(0.03, 0.561 - i * 0.06, node.replace("bgb_", "§"), fontsize=7.5, color="#0f172a", va="center")
    if len(core_nodes) > 10:
        ax.text(0.03, 0.54 - 10 * 0.06, f"+ {len(core_nodes) - 10} more", fontsize=7.5, color="#64748b")

    # Panel C: convergence within the case.
    ax = fig.add_subplot(gs[1, :2])
    trace = record.get("convergence_trace") or []
    rxs = [int(p.get("rollout") or 0) for p in trace if isinstance(p, dict)]
    risk_cov = [float(p.get("risk_coverage") or 0) for p in trace if isinstance(p, dict)]
    val_cov = [float(p.get("valuable_coverage") or 0) for p in trace if isinstance(p, dict)]
    comp = [float(p.get("compression_ratio") or 0) for p in trace if isinstance(p, dict)]
    if rxs:
        ax.plot(rxs, risk_cov, color=PAPER_COLORS["blue"], linewidth=2.2, label="Risk endpoint coverage")
        ax.plot(rxs, val_cov, color=PAPER_COLORS["orange"], linewidth=2.2, label="Broader valuable-node coverage")
        ax.plot(rxs, comp, color=PAPER_COLORS["gray"], linewidth=1.8, linestyle="--", label="Compression")
        first_all = record.get("first_subgraph_risk_all_rollout")
        if first_all:
            ax.axvline(int(first_all), color=PAPER_COLORS["purple"], linestyle=":", linewidth=2)
            ax.text(int(first_all) + 0.6, 0.08, f"first risk-all @ {first_all}", fontsize=8, color=PAPER_COLORS["purple"], rotation=90, va="bottom")
    ax.set_title("C. Rollout trace: evidence is retained after discovery", loc="left", fontsize=11, weight="bold")
    ax.set_xlabel("Rollout")
    ax.legend(frameon=False, fontsize=8, ncol=3)
    set_axis_style(ax, ylabel="Coverage / compression")

    # Panel D: method comparison card.
    ax = fig.add_subplot(gs[1, 2])
    ax.axis("off")
    sm = _metric_values(record)
    nm = _metric_values(naive_record) if naive_record else {}
    ax.set_title("D. Same case outcome", loc="left", fontsize=11, weight="bold")
    rows = [
        ("Root@3", nm.get("root_top3"), sm.get("root_top3")),
        ("Risk-any", nm.get("risk_any"), sm.get("risk_any")),
        ("Risk-all", nm.get("risk_all"), sm.get("risk_all")),
    ]
    x_cols = {"naive_label": 0.34, "naive_value": 0.57, "sa_label": 0.73, "sa_value": 0.97}
    for i, (label, nv, sv) in enumerate(rows):
        yy = 0.82 - i * 0.18
        ax.text(0.0, yy, label, fontsize=10.5, color=PAPER_COLORS["dark"], weight="bold")
        ax.text(x_cols["naive_label"], yy, "Naive", fontsize=9, color="#64748b")
        ax.text(x_cols["naive_value"], yy, "Yes" if nv is True else "No" if nv is False else "err", fontsize=10.5, color=PAPER_COLORS["sa"] if nv is True else PAPER_COLORS["naive"], weight="bold", ha="center")
        ax.text(x_cols["sa_label"], yy, "SA", fontsize=9, color="#64748b")
        ax.text(x_cols["sa_value"], yy, "Yes" if sv is True else "No", fontsize=10.5, color=PAPER_COLORS["sa"] if sv is True else PAPER_COLORS["naive"], weight="bold", ha="right")
    ax.text(
        0.0,
        0.16,
        f"Template: {TEMPLATE_LABELS.get(template_name(record), template_name(record))}\n"
        f"Root: {str(root).replace('bgb_', '§')}\nWitness: {str(witness).replace('bgb_', '§')}",
        fontsize=9,
        color="#475569",
        linespacing=1.45,
    )
    savefig(fig, "fig06_representative_scc_collapse")


def create_main_tables(records: list[dict[str, Any]]) -> None:
    main_rows: list[dict[str, Any]] = []
    for method in METHODS:
        recs = method_records(records, method)
        s = summary(recs)
        main_rows.append(
            {
                "method": method,
                "n": s["n"],
                "errors": s["errors"],
                "root_at_3": pct(s["root"]),
                "risk_any": pct(s["risk_any"]),
                "risk_all": pct(s["risk_all"]),
                "compression": pct(s["compression"]),
                "effective_compression": pct(s["effective_compression"]),
                "avg_subgraph": fmt(s["avg_subgraph"], 2),
            }
        )
    write_csv(TABLE_DIR / "tab03_main_results_strict.csv", main_rows)
    write_md_table(TABLE_DIR / "tab03_main_results_strict.md", "Table 3. Main Strict Results", main_rows)

    model_rows: list[dict[str, Any]] = []
    for model in dash.MODEL_ORDER:
        for method in METHODS:
            recs = [r for r in records if r.get("model") == model and r.get("method") == method]
            if not recs:
                continue
            s = summary(recs)
            model_rows.append(
                {
                    "model": model,
                    "method": method,
                    "n": s["n"],
                    "errors": s["errors"],
                    "root_at_3": pct(s["root"]),
                    "risk_any": pct(s["risk_any"]),
                    "risk_all": pct(s["risk_all"]),
                    "compression": pct(s["compression"]),
                    "effective_compression": pct(s["effective_compression"]),
                }
            )
    write_csv(TABLE_DIR / "tabA4_model_breakdown.csv", model_rows)
    write_md_table(TABLE_DIR / "tabA4_model_breakdown.md", "Table A4. Model-level Breakdown", model_rows)

    domain_rows: list[dict[str, Any]] = []
    for domain in dash.DOMAIN_ORDER:
        for method in METHODS:
            recs = [r for r in records if r.get("domain") == domain and r.get("method") == method]
            if not recs:
                continue
            s = summary(recs)
            domain_rows.append(
                {
                    "domain": domain,
                    "method": method,
                    "n": s["n"],
                    "errors": s["errors"],
                    "root_at_3": pct(s["root"]),
                    "risk_any": pct(s["risk_any"]),
                    "risk_all": pct(s["risk_all"]),
                    "compression": pct(s["compression"]),
                    "effective_compression": pct(s["effective_compression"]),
                }
            )
    write_csv(TABLE_DIR / "tabA5_domain_breakdown.csv", domain_rows)
    write_md_table(TABLE_DIR / "tabA5_domain_breakdown.md", "Table A5. Domain-level Breakdown", domain_rows)

    scc_rows: list[dict[str, Any]] = []
    for row in dash._size_trend_rows(records):
        for method in METHODS:
            s = row["naive"] if method == "naive" else row["sa"]
            scc_rows.append(
                {
                    "scc_size": row["size"],
                    "method": method,
                    "n": s["n"],
                    "root_at_3": pct(s["root"]),
                    "risk_any": pct(s["risk_any"]),
                    "risk_all": pct(s["risk_all"]),
                    "compression": pct(s["compression"]),
                }
            )
    write_csv(TABLE_DIR / "tabA6_by_scc_size.csv", scc_rows)
    write_md_table(TABLE_DIR / "tabA6_by_scc_size.md", "Table A6. Metrics by SCC Size", scc_rows)


def create_motivation_tables() -> None:
    mcts_rows = [
        {
            "method": "TreeMCTS on DAG",
            "setting": "acyclic dependencies",
            "failure_mode": "none / normal backpropagation",
            "expected_behavior": "finite expansion and stable value updates",
            "paper_role": "baseline intuition",
        },
        {
            "method": "TreeMCTS on SCC",
            "setting": "cyclic structural dependencies",
            "failure_mode": "revisits expand the same logical state repeatedly",
            "expected_behavior": "search budget is consumed by cyclic paths before evidence stabilizes",
            "paper_role": "motivates SCC-level collapse",
        },
        {
            "method": "SA-MCGS",
            "setting": "SCC isolated as a reasoning unit",
            "failure_mode": "managed by local windows + evidence memory + dynamic core",
            "expected_behavior": "compresses cyclic context into an inspectable risk subgraph",
            "paper_role": "proposed method",
        },
    ]
    write_csv(TABLE_DIR / "tab01_mcts_scc_motivation.csv", mcts_rows)
    write_md_table(TABLE_DIR / "tab01_mcts_scc_motivation.md", "Table 1. Why Standard MCTS Fails on SCCs", mcts_rows)

    domain_rows = [
        {
            "domain": "Debian",
            "source_authority": "real package dependency metadata",
            "graph_role": "software migration / ABI-like dependency constraints",
            "noise_level": "low-to-medium",
            "paper_role": "technical dependency generalization",
        },
        {
            "domain": "SEC EX-21",
            "source_authority": "public SEC subsidiary exhibit structure",
            "graph_role": "entity-control and consolidation paths",
            "noise_level": "medium",
            "paper_role": "financial/legal entity generalization",
        },
        {
            "domain": "BGB",
            "source_authority": "German Civil Code legal references",
            "graph_role": "statutory cross-reference cycles",
            "noise_level": "low",
            "paper_role": "clean legal-rule stress test",
        },
        {
            "domain": "CUAD",
            "source_authority": "contract review dataset",
            "graph_role": "long contract clause graph with native ambiguity",
            "noise_level": "high",
            "paper_role": "noisy contract-domain stress test",
        },
    ]
    write_csv(TABLE_DIR / "tab02_domain_coverage_authority.csv", domain_rows)
    write_md_table(TABLE_DIR / "tab02_domain_coverage_authority.md", "Table 2. Domain Coverage and Authority", domain_rows)


def create_figure_catalog() -> None:
    figure_rows = [
        {
            "id": "Figure 1",
            "file": "fig01_sa_mcgs_framework_architecture.svg/png",
            "paper_section": "Method",
            "what_it_shows": "Frontend architecture diagram from demo.html: validated cyclic domains, Tarjan SCC split, three SA-MCGS contributions, and pluggable pruning adapters.",
            "use_in_main_text": "Yes",
        },
        {
            "id": "Figure 2",
            "file": "fig02_main_metrics_strict.pdf/png",
            "paper_section": "Main Results",
            "what_it_shows": "Composite main result: strict Root@3/Risk-any/Risk-all, reliability/error burden, model-level Risk-all, and domain-level difficulty.",
            "use_in_main_text": "Yes",
        },
        {
            "id": "Figure 3",
            "file": "fig03_main_by_scc_size.pdf/png",
            "paper_section": "Main Results / Analysis",
            "what_it_shows": "Composite SCC-size analysis: Risk-all by exact size, SA-minus-Naive gains, compression by size, and bucketed paper view.",
            "use_in_main_text": "Yes",
        },
        {
            "id": "Figure 4",
            "file": "fig04_budget_prefix_convergence.pdf/png",
            "paper_section": "Analysis",
            "what_it_shows": "Rollout convergence: root retention, Risk-any, Risk-all, effective OC, coverage, compression, and per-model Risk-all curves.",
            "use_in_main_text": "Yes",
        },
        {
            "id": "Figure 5",
            "file": "fig05_compression_profile_tradeoff.pdf/png",
            "paper_section": "Analysis / Appendix",
            "what_it_shows": "Pareto trade-off between risk retention and compression profile; explains why current/default sacrifices some compression for endpoint retention.",
            "use_in_main_text": "Maybe",
        },
        {
            "id": "Figure 6",
            "file": "fig06_representative_scc_collapse.pdf/png",
            "paper_section": "Case Study",
            "what_it_shows": "Representative long-SCC case narrative: original cycle context, final dynamic core, rollout trace, and same-case Naive-vs-SA outcome.",
            "use_in_main_text": "Maybe",
        },
        {
            "id": "Figure A2",
            "file": "figA2_naive_output_burden.pdf/png",
            "paper_section": "Appendix",
            "what_it_shows": "Naive output-burden fairness control: full direct-subgraph output versus lite output on long CUAD cases.",
            "use_in_main_text": "No",
        },
    ]
    write_csv(TABLE_DIR / "figure_catalog.csv", figure_rows)
    write_md_table(TABLE_DIR / "figure_catalog.md", "Paper Figure Catalog", figure_rows)

    lines = [
        "# Paper Figure README",
        "",
        "这个目录是论文写作唯一推荐引用的图表入口。主文图表从这里拿，避免误用旧的 diagnostic / smoke / balanced exploratory 图。",
        "",
        "| ID | File | Section | Explanation | Main Text? |",
        "|---|---|---|---|---|",
    ]
    for row in figure_rows:
        lines.append(
            f"| {row['id']} | `{row['file']}` | {row['paper_section']} | {row['what_it_shows']} | {row['use_in_main_text']} |"
        )
    lines.extend(
        [
            "",
            "口径规则：",
            "",
            "- 主实验图只使用 `current/default + critical + structural_simple_v2 + 4 models + 80 SCC blocks/model`。",
            "- `balanced`、`conservative`、Gemini Flash、Wikipedia exploratory、旧 memory_stress diagnostic 不进入主图。",
            "- `Effective OC` 只作为 rollout 发现过程的辅助曲线，不作为主命中指标。",
            "",
        ]
    )
    (FIG_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def node_name(record: dict[str, Any], node: str | None) -> str:
    if not node:
        return ""
    return str((record.get("node_names") or {}).get(node) or node)


def compact_node_stats(record: dict[str, Any], node: str | None) -> str:
    if not node:
        return ""
    details = (record.get("clause_details") or {}).get(node)
    if isinstance(details, dict):
        keys = ["mean_score", "visit_count", "conflict_count", "is_oc_detected"]
        parts = [f"{key}={details[key]}" for key in keys if key in details]
        return "; ".join(parts)
    if details is None:
        return ""
    return textwrap.shorten(str(details), width=240, placeholder="...")


def select_annotation_pairs(records: list[dict[str, Any]], per_domain: int = 8) -> list[dict[str, Any]]:
    by_case: dict[tuple[str, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        method = str(record.get("method"))
        if method in METHODS:
            by_case[case_key(record)][method] = record

    pairs: list[dict[str, Any]] = []
    for key, pair in by_case.items():
        if "sa-mcgs" not in pair:
            continue
        sa = pair["sa-mcgs"]
        naive = pair.get("naive")
        metrics = _metric_values(sa)
        pairs.append(
            {
                "key": key,
                "domain": sa.get("domain"),
                "size": int(sa.get("scc_size") or sa.get("_task_size") or 0),
                "model": sa.get("model"),
                "template": template_name(sa),
                "risk_all": metrics.get("risk_all") is True,
                "risk_any": metrics.get("risk_any") is True,
                "sa": sa,
                "naive": naive,
            }
        )

    selected: list[dict[str, Any]] = []
    for domain in dash.DOMAIN_ORDER:
        domain_pairs = [p for p in pairs if p["domain"] == domain]
        domain_pairs.sort(key=lambda p: (p["risk_all"], p["risk_any"], -p["size"], str(p["model"]), str(p["template"])))
        # Take failures first, then long successful cases for contrast.
        chosen: list[dict[str, Any]] = []
        for p in domain_pairs:
            if len(chosen) >= per_domain:
                break
            if not p["risk_all"]:
                chosen.append(p)
        for p in sorted(domain_pairs, key=lambda item: (-item["size"], str(item["model"]), str(item["template"]))):
            if len(chosen) >= per_domain:
                break
            if p not in chosen:
                chosen.append(p)
        selected.extend(chosen[:per_domain])
    selected.sort(key=lambda p: (dash.DOMAIN_ORDER.index(str(p["domain"])) if p["domain"] in dash.DOMAIN_ORDER else 99, -p["size"], str(p["model"]), str(p["template"])))
    return selected


def create_case_material(case_id: str, pair: dict[str, Any]) -> dict[str, Any]:
    sa = pair["sa"]
    naive = pair.get("naive") or {}
    risk_nodes = [n for n in [sa.get("injected_node"), sa.get("injected_witness_node")] if n]
    affected = list(sa.get("injected_affected_nodes") or [])
    core = list(sa.get("core_evidence_risk_subgraph_nodes") or sa.get("risk_subgraph_nodes") or [])
    naive_nodes = list(naive.get("direct_risk_subgraph_nodes") or naive.get("risk_subgraph_nodes") or [])
    oc_nodes = list(sa.get("oc_detected") or [])
    context = list(sa.get("context_evidence_risk_subgraph_nodes") or [])
    metrics_sa = _metric_values(sa)
    metrics_naive = _metric_values(naive) if naive else {}

    important_nodes = []
    for role, nodes in [
        ("root", [sa.get("injected_node")]),
        ("witness", [sa.get("injected_witness_node")]),
        ("affected", affected),
        ("sa_core", core),
        ("naive_subgraph", naive_nodes),
        ("oc", oc_nodes),
    ]:
        for node in nodes:
            if not node:
                continue
            important_nodes.append(
                {
                    "role": role,
                    "node_id": node,
                    "label": node_name(sa, node),
                    "stats": compact_node_stats(sa, node),
                }
            )

    row = {
        "case_id": case_id,
        "domain": sa.get("domain"),
        "domain_label": DOMAIN_LABELS.get(str(sa.get("domain")), str(sa.get("domain"))),
        "scc_id": sa.get("scc_id"),
        "scc_size": sa.get("scc_size"),
        "model": sa.get("model"),
        "template": template_name(sa),
        "template_label": TEMPLATE_LABELS.get(template_name(sa), template_name(sa)),
        "severity": severity_name(sa),
        "root_node": sa.get("injected_node"),
        "root_label": node_name(sa, sa.get("injected_node")),
        "witness_node": sa.get("injected_witness_node"),
        "witness_label": node_name(sa, sa.get("injected_witness_node")),
        "affected_nodes": ";".join(affected),
        "sa_core_nodes": ";".join(core),
        "naive_subgraph_nodes": ";".join(naive_nodes),
        "context_nodes": ";".join(context),
        "oc_nodes": ";".join(oc_nodes),
        "sa_root_at_3": metrics_sa.get("root_top3"),
        "sa_risk_any": metrics_sa.get("risk_any"),
        "sa_risk_all": metrics_sa.get("risk_all"),
        "sa_compression": metrics_sa.get("compression"),
        "naive_error": naive.get("error", "") if naive else "missing",
        "naive_root_at_3": metrics_naive.get("root_top3"),
        "naive_risk_any": metrics_naive.get("risk_any"),
        "naive_risk_all": metrics_naive.get("risk_all"),
        "naive_compression": metrics_naive.get("compression"),
        "label_is_structural_conflict": "",
        "label_relevant_risk_nodes": "",
        "label_core_is_sufficient_for_repair": "",
        "label_comments": "",
    }

    material = {
        "metadata": row,
        "important_nodes": important_nodes,
        "risk_nodes": risk_nodes,
        "affected_nodes": affected,
        "sa_core_nodes": core,
        "naive_subgraph_nodes": naive_nodes,
        "context_nodes": context,
        "oc_nodes": oc_nodes,
        "sa_metrics": metrics_sa,
        "naive_metrics": metrics_naive,
    }
    return material


def write_case_card(case_id: str, material: dict[str, Any]) -> None:
    meta = material["metadata"]
    lines = [
        f"# {case_id}: {meta['domain_label']} / size {meta['scc_size']} / {meta['model']}",
        "",
        f"- Template: `{meta['template']}` ({meta['template_label']})",
        f"- Root: `{meta['root_node']}` — {meta['root_label']}",
        f"- Witness: `{meta['witness_node']}` — {meta['witness_label']}",
        f"- Affected nodes: `{meta['affected_nodes'] or '-'}`",
        f"- SA core nodes: `{meta['sa_core_nodes'] or '-'}`",
        f"- Naive subgraph nodes: `{meta['naive_subgraph_nodes'] or '-'}`",
        "",
        "## Annotation Task / 标注任务",
        "",
        "EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.",
        "",
        "中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。",
        "",
        "## Node Evidence",
        "",
        "| Role | Node | Label | Stats |",
        "|---|---|---|---|",
    ]
    for item in material["important_nodes"]:
        lines.append(f"| {item['role']} | `{item['node_id']}` | {item['label']} | {item['stats']} |")
    lines.append("")
    (ANNOT_MATERIAL_DIR / f"{case_id}.md").write_text("\n".join(lines), encoding="utf-8")
    (ANNOT_MATERIAL_DIR / f"{case_id}.json").write_text(json.dumps(material, indent=2, ensure_ascii=False), encoding="utf-8")


def create_annotation_html(materials: list[dict[str, Any]]) -> None:
    cards = []
    for material in materials:
        meta = material["metadata"]
        nodes_rows = []
        for item in material["important_nodes"][:32]:
            nodes_rows.append(
                "<tr>"
                f"<td>{html.escape(item['role'])}</td>"
                f"<td><code>{html.escape(str(item['node_id']))}</code></td>"
                f"<td>{html.escape(str(item['label']))}</td>"
                f"<td>{html.escape(str(item['stats']))}</td>"
                "</tr>"
            )
        cards.append(
            f"""
            <section class="case-card">
              <div class="case-head">
                <div>
                  <h2>{html.escape(meta['case_id'])} · {html.escape(meta['domain_label'])}</h2>
                  <p>{html.escape(str(meta['model']))} · SCC {html.escape(str(meta['scc_size']))} · {html.escape(meta['template_label'])}</p>
                </div>
                <div class="badges">
                  <span>SA Risk-any: {html.escape(str(meta['sa_risk_any']))}</span>
                  <span>SA Risk-all: {html.escape(str(meta['sa_risk_all']))}</span>
                  <span>Compression: {pct(meta['sa_compression'])}</span>
                </div>
              </div>
              <div class="lang zh">
                <p><strong>标注任务：</strong>判断 root/witness/affected 是否构成真实结构性风险，以及 SA core 是否足以作为修复导向的风险子图。</p>
              </div>
              <div class="lang en">
                <p><strong>Task:</strong> judge whether the root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.</p>
              </div>
              <table>
                <thead><tr><th>Role</th><th>Node</th><th>Label</th><th>Trace stats</th></tr></thead>
                <tbody>{''.join(nodes_rows)}</tbody>
              </table>
              <p><strong>SA core:</strong> <code>{html.escape(str(meta['sa_core_nodes'] or '-'))}</code></p>
              <p><strong>Naive subgraph:</strong> <code>{html.escape(str(meta['naive_subgraph_nodes'] or '-'))}</code></p>
            </section>
            """
        )
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SA-MCGS Human Annotation Pack</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #172033; background: #f8fafc; }}
header {{ position: sticky; top: 0; z-index: 10; background: #0f172a; color: #f8fafc; padding: 18px 28px; box-shadow: 0 2px 10px rgba(15,23,42,.25); }}
h1 {{ margin: 0 0 8px; font-size: 26px; }}
button {{ border: 1px solid #cbd5e1; background: #fff; color: #0f172a; padding: 8px 14px; border-radius: 8px; font-weight: 700; cursor: pointer; }}
main {{ max-width: 1180px; margin: 24px auto; padding: 0 18px 60px; }}
.case-card {{ background: #fff; border: 1px solid #dbe3ef; border-radius: 12px; padding: 20px; margin: 18px 0; box-shadow: 0 1px 4px rgba(15,23,42,.05); }}
.case-head {{ display: flex; justify-content: space-between; gap: 18px; align-items: start; }}
h2 {{ margin: 0 0 6px; font-size: 21px; }}
p {{ line-height: 1.55; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }}
.badges span {{ background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; border-radius: 999px; padding: 5px 10px; font-size: 13px; font-weight: 700; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
th, td {{ border-bottom: 1px solid #e2e8f0; text-align: left; vertical-align: top; padding: 9px; }}
th {{ background: #f1f5f9; }}
code {{ background: #f1f5f9; padding: 2px 5px; border-radius: 5px; }}
.en {{ display: none; }}
body.show-en .zh {{ display: none; }}
body.show-en .en {{ display: block; }}
</style>
</head>
<body>
<header>
  <h1 class="zh">SA-MCGS 人工标注包</h1>
  <h1 class="en">SA-MCGS Human Annotation Pack</h1>
  <button onclick="document.body.classList.toggle('show-en')">中文 / English</button>
</header>
<main>
  <p class="zh">每张卡片对应一个 critical SCC case。请结合 root、witness、affected、SA core 和 Naive 子图判断结构风险是否真实、风险子图是否足够用于修复。</p>
  <p class="en">Each card is one critical SCC case. Use root, witness, affected nodes, SA core, and Naive subgraph to judge whether the structural risk is real and whether the risk subgraph is sufficient for repair.</p>
  {''.join(cards)}
</main>
</body>
</html>"""
    (ANNOT_DIR / "annotation_interface.html").write_text(page, encoding="utf-8")


def create_annotation_pack(records: list[dict[str, Any]]) -> None:
    pairs = select_annotation_pairs(records, per_domain=8)
    materials: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []
    for idx, pair in enumerate(pairs, 1):
        case_id = f"case_{idx:03d}_{pair['domain']}_{pair['size']}_{pair['model']}_{pair['template']}".replace("/", "_")
        material = create_case_material(case_id, pair)
        material["metadata"]["case_id"] = case_id
        materials.append(material)
        csv_rows.append(material["metadata"])
        write_case_card(case_id, material)

    write_csv(ANNOT_DIR / "human_annotation_cases.csv", csv_rows)
    write_md_table(ANNOT_DIR / "human_annotation_cases.md", "Human Annotation Case Manifest", csv_rows)
    create_annotation_html(materials)
    readme = [
        "# Human Annotation Pack / 人工标注包",
        "",
        "目的：让领域专家快速审阅 critical SCC case，判断结构性风险和风险子图是否合理。",
        "",
        "包含文件：",
        "",
        "- `human_annotation_cases.csv`：可直接发给标注者或导入表格工具。",
        "- `annotation_interface.html`：双语切换的本地前端标注浏览页面。",
        "- `materials/*.md`：每个 case 的可读卡片。",
        "- `materials/*.json`：每个 case 的结构化素材。",
        "",
        "建议标注列：",
        "",
        "- `label_is_structural_conflict`：是否确实存在结构性风险。",
        "- `label_relevant_risk_nodes`：专家认为应纳入风险子图的节点。",
        "- `label_core_is_sufficient_for_repair`：SA core 是否足够作为修复入口。",
        "- `label_comments`：自由说明。",
        "",
        "注意：当前包使用主实验锁定口径生成，不包含旧 diagnostic / smoke / balanced exploratory 数据。",
        "",
    ]
    (ANNOT_DIR / "README.md").write_text("\n".join(readme), encoding="utf-8")

    zip_path = ANNOT_DIR / "human_annotation_pack.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(ANNOT_DIR.rglob("*")):
            if path == zip_path or path.is_dir():
                continue
            zf.write(path, path.relative_to(ANNOT_DIR))

    shutil.copy2(ANNOT_DIR / "human_annotation_cases.csv", TABLE_DIR / "tabE4_human_annotation_cases.csv")
    write_md_table(TABLE_DIR / "tabE4_human_annotation_cases.md", "Table E4. Human Annotation Case Manifest", csv_rows)


def create_asset_readme() -> None:
    lines = [
        "# Main Experiment Paper Assets",
        "",
        "这是最终论文写作使用的稳定图表与标注资产目录。后续写 paper 时优先从这里引用，不再直接从 `cross_domain/results/` 或临时 dashboard 拿图。",
        "",
        "## Directory",
        "",
        "- `figures/`：论文主文和 appendix 图，含 `README.md` 解释每张图。",
        "- `tables/`：论文表格 CSV/Markdown 源文件。",
        "- `human_annotation_pack/`：人工标注包，含 CSV、case 素材、双语 HTML 和 zip。",
        "",
        "## Locked Main Experiment Scope",
        "",
        "- Profile: `current/default`",
        "- Injection: `memory_stress` internally `structural_simple_v2`",
        "- Severity: `critical`",
        "- Models: `gpt-4o`, `deepseek-v3`, `qwen2.5-72b`, `gemini-2.5-pro`",
        "- Domains: Debian, SEC EX-21, BGB, CUAD",
        "- Budget: SA-MCGS `60` rollouts",
        "- Size: `80` SCC blocks per model, `320` model-case pairs, `640` method-level records",
        "",
        "## Recommended Main-paper Assets",
        "",
            "- Figure 1: `figures/fig01_sa_mcgs_framework_architecture.svg` / `.png`",
        "- Table 1: `tables/tab01_mcts_scc_motivation.md` / `.csv`",
        "- Table 2: `tables/tab02_domain_coverage_authority.md` / `.csv`",
        "- Table 3: `tables/tab03_main_results_strict.md` / `.csv`",
        "- Figure 2: `figures/fig02_main_metrics_strict.pdf`",
        "- Figure 3: `figures/fig03_main_by_scc_size.pdf`",
        "- Figure 4: `figures/fig04_budget_prefix_convergence.pdf`",
        "- Figure 5: `figures/fig05_compression_profile_tradeoff.pdf`",
        "- Figure 6: `figures/fig06_representative_scc_collapse.pdf`",
        "",
        "## Human Annotation",
        "",
        "- Zip: `human_annotation_pack/human_annotation_pack.zip`",
        "- Browser entry: `human_annotation_pack/annotation_interface.html`",
        "- CSV: `human_annotation_pack/human_annotation_cases.csv`",
        "",
    ]
    (ASSET_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def update_main_readme() -> None:
    path = MAIN_DIR / "README.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    marker = "## Paper Asset Directory"
    block = """## Paper Asset Directory

论文图表和人工标注材料统一放在 [`paper_assets/`](paper_assets/)，后续写 paper 时优先引用这里的稳定文件：

- [`paper_assets/figures/`](paper_assets/figures/)：主文和 appendix 图，目录内 `README.md` 解释每张图。
- [`paper_assets/tables/`](paper_assets/tables/)：主表和补充表的 CSV/Markdown 源。
- [`paper_assets/human_annotation_pack/human_annotation_pack.zip`](paper_assets/human_annotation_pack/human_annotation_pack.zip)：给专家标注的压缩包，含 CSV、case 素材和中英文切换 HTML。

口径提醒：主实验图表只使用 `current/default + critical + structural_simple_v2 + 4 models + 80 SCC blocks/model`。旧 diagnostic、smoke、balanced exploratory 不作为主结果。

"""
    if marker in text:
        before = text.split(marker, 1)[0].rstrip() + "\n\n"
        # Drop the old block up to the next heading if present.
        rest = text.split(marker, 1)[1]
        next_heading = rest.find("\n## ")
        after = rest[next_heading + 1 :] if next_heading >= 0 else ""
        text = before + block + after
    else:
        text = text.rstrip() + "\n\n" + block
    path.write_text(text, encoding="utf-8")


def copy_existing_assets() -> None:
    mappings = {
        "E1_naive_output_burden": "figA2_naive_output_burden",
    }
    for source, target in mappings.items():
        copy_supplement_figure(source, target)

    table_mappings = {
        "E0_matched_valid_only.csv": "tabA1_strict_valid_matched.csv",
        "E1_naive_output_burden_control.csv": "tabA2_naive_output_burden_control.csv",
        "E1_naive_output_burden_cases.csv": "tabA2_naive_output_burden_cases.csv",
        "E2_budget_prefix_convergence.csv": "tabA3_budget_prefix_convergence.csv",
        "E3_compression_profile_ablation.csv": "tabA7_compression_profile_ablation.csv",
        "E5_prompt_rubric_parity.csv": "tabA8_prompt_rubric_parity.csv",
    }
    for source, target in table_mappings.items():
        copy_supplement_table(source, target)


def main() -> int:
    ensure_dirs()
    records = load_current_records()
    if not records:
        raise RuntimeError("No current/default records loaded from main experiment manifest.")
    copy_existing_assets()
    create_pipeline_figure()
    create_demo_architecture_figure()
    create_main_metrics_figure(records)
    create_scc_size_figure(records)
    create_budget_convergence_figure(records)
    create_compression_tradeoff_figure(records)
    create_case_study_figure(records)
    create_motivation_tables()
    create_main_tables(records)
    create_figure_catalog()
    create_annotation_pack(records)
    create_asset_readme()
    update_main_readme()
    print(f"Wrote paper assets to {ASSET_DIR}")
    print(f"Wrote annotation zip to {ANNOT_DIR / 'human_annotation_pack.zip'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

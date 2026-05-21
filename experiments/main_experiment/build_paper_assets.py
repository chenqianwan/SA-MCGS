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


def role_label(role: str, lang: str = "en") -> str:
    labels = {
        "root": ("Root / injected node", "Root / 注入节点"),
        "witness": ("Witness endpoint", "Witness / 远距离证据端点"),
        "affected": ("Affected node", "受影响节点"),
        "sa_core": ("SA-MCGS core node", "SA-MCGS 风险子图节点"),
        "naive_subgraph": ("Naive subgraph node", "Naive 风险子图节点"),
        "oc": ("OC signal node", "OC 信号节点"),
    }
    en, zh = labels.get(role, (role, role))
    return zh if lang == "zh" else en


def case_explanation(meta: dict[str, Any], lang: str = "en") -> str:
    template = str(meta.get("template") or "")
    domain = str(meta.get("domain") or "")
    zh_templates = {
        "direct_mutex": "两个远距离记录分别给出互斥要求，单看都合理，但组合后不能同时满足。",
        "handoff_invariant": "上游交接条件和下游接收条件不一致，风险来自跨节点链路约束被破坏。",
        "temporal_gate": "时间或触发顺序被改写，导致后续记录依赖的条件无法按原链路成立。",
        "condition_trigger": "触发条件被改写，使同一环内的义务、权限或控制关系发生结构性冲突。",
    }
    en_templates = {
        "direct_mutex": "Two distant records impose mutually incompatible requirements. Each record may look plausible in isolation, but the pair cannot be jointly satisfied.",
        "handoff_invariant": "The upstream handoff condition and the downstream acceptance condition diverge, so the risk comes from a broken cross-node invariant.",
        "temporal_gate": "A timing or trigger order is rewritten, making a later dependency impossible under the original cycle.",
        "condition_trigger": "A trigger condition is rewritten, creating a structural conflict among obligations, permissions, or control relations in the same SCC.",
    }
    zh_domains = {
        "debian": "Debian 依赖域：关注包迁移、ABI/API 暴露、配置前置条件是否互相冲突。",
        "sec_ex21": "SEC EX-21 披露域：关注实体控制、合并口径、少数权益或控制链是否互相冲突。",
        "bgb": "BGB 法条域：关注法条之间的适用条件、期限、义务和例外是否互相冲突。",
        "cuad": "CUAD 合同域：关注合同条款之间的授权、限制、触发条件和救济路径是否互相冲突。",
    }
    en_domains = {
        "debian": "Debian dependency domain: inspect migration, ABI/API exposure, and configuration preconditions.",
        "sec_ex21": "SEC EX-21 disclosure domain: inspect entity control, consolidation, minority interest, and ownership-chain consistency.",
        "bgb": "BGB statute domain: inspect applicability conditions, deadlines, obligations, and exceptions across sections.",
        "cuad": "CUAD contract domain: inspect licenses, restrictions, triggers, and remedy paths across clauses.",
    }
    if lang == "zh":
        return f"{zh_domains.get(domain, '')} {zh_templates.get(template, '')}".strip()
    return f"{en_domains.get(domain, '')} {en_templates.get(template, '')}".strip()


def enrich_annotation_material(material: dict[str, Any]) -> dict[str, Any]:
    meta = material["metadata"]
    enriched = dict(material)
    enriched["case_summary"] = {
        "en": case_explanation(meta, "en"),
        "zh": case_explanation(meta, "zh"),
    }
    seen: set[tuple[str, str]] = set()
    nodes: list[dict[str, Any]] = []
    for item in material.get("important_nodes", []):
        key = (str(item.get("role")), str(item.get("node_id")))
        if key in seen:
            continue
        seen.add(key)
        label = str(item.get("label") or item.get("node_id") or "")
        role = str(item.get("role") or "")
        nodes.append(
            {
                **item,
                "role_label_en": role_label(role, "en"),
                "role_label_zh": role_label(role, "zh"),
                "text_en": label,
                "text_zh": f"{role_label(role, 'zh')}。原始文本/标题：{label}",
                "is_risk_endpoint": item.get("node_id") in material.get("risk_nodes", []),
                "is_affected": item.get("node_id") in material.get("affected_nodes", []),
                "in_sa_core": item.get("node_id") in material.get("sa_core_nodes", []),
                "in_naive_subgraph": item.get("node_id") in material.get("naive_subgraph_nodes", []),
                "in_oc": item.get("node_id") in material.get("oc_nodes", []),
            }
        )
    enriched["important_nodes"] = nodes
    return enriched


def ensure_sheetjs_vendor() -> None:
    vendor_dir = ANNOT_DIR / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    vendor_path = vendor_dir / "xlsx.full.min.js"
    if vendor_path.exists() and vendor_path.stat().st_size > 200_000:
        return
    import urllib.request

    url = "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"
    with urllib.request.urlopen(url, timeout=30) as response:
        vendor_path.write_bytes(response.read())


def create_annotation_html(materials: list[dict[str, Any]]) -> None:
    ensure_sheetjs_vendor()
    payload = json.dumps([enrich_annotation_material(m) for m in materials], ensure_ascii=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SA-MCGS Expert Annotation Pack</title>
<script src="vendor/xlsx.full.min.js"></script>
<style>
:root { --bg:#f6f8fb; --panel:#ffffff; --ink:#111827; --muted:#64748b; --line:#d8e0eb; --blue:#2563eb; --green:#059669; --red:#dc2626; --amber:#b45309; --soft:#eef4ff; }
* { box-sizing: border-box; }
body { margin:0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; background:var(--bg); color:var(--ink); }
header { position:sticky; top:0; z-index:20; background:#0f172a; color:#f8fafc; padding:16px 24px; box-shadow:0 6px 18px rgba(15,23,42,.22); }
h1 { margin:0 0 8px; font-size:25px; letter-spacing:0; }
.topline { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between; }
.toolbar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
button, input, textarea, select { font:inherit; }
button { border:1px solid #cbd5e1; background:#fff; color:#0f172a; padding:8px 12px; border-radius:8px; font-weight:700; cursor:pointer; }
button.primary { background:var(--blue); border-color:var(--blue); color:#fff; }
button.green { background:var(--green); border-color:var(--green); color:#fff; }
button.ghost { background:transparent; color:#e2e8f0; border-color:#475569; }
input[type="text"], textarea, select { border:1px solid var(--line); border-radius:8px; padding:9px 10px; background:#fff; width:100%; }
main { display:grid; grid-template-columns: 340px minmax(0, 1fr); gap:18px; max-width:1480px; margin:20px auto; padding:0 18px 50px; }
aside, .workspace { background:var(--panel); border:1px solid var(--line); border-radius:14px; box-shadow:0 1px 6px rgba(15,23,42,.05); }
aside { max-height:calc(100vh - 118px); overflow:auto; padding:14px; position:sticky; top:92px; }
.stats { display:grid; grid-template-columns: repeat(3, 1fr); gap:8px; margin:10px 0 14px; }
.stat { background:#f8fafc; border:1px solid var(--line); border-radius:10px; padding:10px; }
.stat b { display:block; font-size:20px; }
.case-btn { width:100%; text-align:left; margin:8px 0; padding:12px; border-radius:12px; border:1px solid var(--line); background:#fff; color:var(--ink); }
.case-btn.active { border-color:var(--blue); background:var(--soft); }
.case-btn .title { font-weight:800; display:block; margin-bottom:5px; }
.case-btn .meta { color:var(--muted); font-size:13px; line-height:1.45; }
.case-btn .done { float:right; color:var(--green); font-weight:900; }
.workspace { padding:22px; min-height:720px; }
.case-title { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; border-bottom:1px solid var(--line); padding-bottom:14px; }
.case-title h2 { margin:0 0 8px; font-size:26px; }
.pillbar { display:flex; flex-wrap:wrap; gap:7px; }
.pill { border-radius:999px; padding:5px 10px; background:#f1f5f9; color:#334155; font-size:13px; font-weight:700; }
.pill.green { background:#dcfce7; color:#166534; }
.pill.red { background:#fee2e2; color:#991b1b; }
.pill.blue { background:#dbeafe; color:#1d4ed8; }
.section { margin-top:20px; }
.section h3 { margin:0 0 10px; font-size:18px; }
.summary { background:#f8fafc; border-left:5px solid var(--blue); padding:14px 16px; border-radius:10px; line-height:1.65; }
table { width:100%; border-collapse:collapse; }
th, td { border-bottom:1px solid var(--line); padding:10px; vertical-align:top; text-align:left; }
th { background:#f8fafc; color:#334155; font-size:13px; text-transform:uppercase; letter-spacing:.02em; }
code { background:#f1f5f9; padding:2px 5px; border-radius:5px; word-break:break-all; }
.node-text { max-width:520px; color:#334155; line-height:1.45; }
.node-actions { display:flex; gap:6px; flex-wrap:wrap; }
.form-grid { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:14px; }
.question { border:1px solid var(--line); border-radius:12px; padding:14px; background:#fff; }
.question h4 { margin:0 0 10px; font-size:15px; }
.options { display:flex; flex-wrap:wrap; gap:8px; }
label.option { display:inline-flex; align-items:center; gap:6px; border:1px solid var(--line); border-radius:999px; padding:7px 10px; cursor:pointer; }
.check-list { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:6px; max-height:220px; overflow:auto; padding:6px; border:1px solid var(--line); border-radius:10px; background:#f8fafc; }
.check-list label { display:flex; gap:6px; align-items:flex-start; font-size:13px; line-height:1.35; }
.save-row { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-top:16px; }
.hint { color:var(--muted); line-height:1.55; }
.modal { display:none; position:fixed; inset:0; z-index:50; background:rgba(15,23,42,.6); padding:30px; }
.modal.open { display:flex; align-items:center; justify-content:center; }
.modal-card { width:min(960px, 96vw); max-height:88vh; overflow:auto; background:#fff; border-radius:16px; border:1px solid var(--line); box-shadow:0 20px 60px rgba(0,0,0,.28); }
.modal-head { position:sticky; top:0; background:#fff; padding:16px 18px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:12px; align-items:center; }
.modal-body { padding:18px; }
.text-panel { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.text-box { border:1px solid var(--line); border-radius:12px; padding:14px; background:#f8fafc; line-height:1.6; white-space:pre-wrap; }
.lang-en .zh-only { display:none; }
.lang-zh .en-only { display:none; }
@media (max-width: 980px) { main { grid-template-columns:1fr; } aside { position:relative; top:0; max-height:none; } .form-grid, .text-panel, .check-list { grid-template-columns:1fr; } }
</style>
</head>
<body class="lang-zh">
<header>
  <div class="topline">
    <div>
      <h1><span class="zh-only">SA-MCGS 专家标注小包</span><span class="en-only">SA-MCGS Expert Annotation Pack</span></h1>
      <div class="hint zh-only">精选 critical SCC case。点击节点查看中英文文本说明；页面内完成标注后导出 Excel。</div>
      <div class="hint en-only">Curated critical SCC cases. Click nodes for bilingual evidence text; annotate in the page and export Excel.</div>
    </div>
    <div class="toolbar">
      <button class="ghost" id="langBtn">中文 / English</button>
      <button class="green" id="exportBtn">导出 Excel</button>
    </div>
  </div>
</header>
<main>
  <aside>
    <input id="reviewer" type="text" placeholder="Reviewer / 标注者 ID">
    <div class="stats">
      <div class="stat"><b id="totalCount">0</b><span class="zh-only">样本</span><span class="en-only">Cases</span></div>
      <div class="stat"><b id="doneCount">0</b><span class="zh-only">已填</span><span class="en-only">Done</span></div>
      <div class="stat"><b id="domainCount">0</b><span class="zh-only">领域</span><span class="en-only">Domains</span></div>
    </div>
    <div class="hint zh-only">建议每位专家完成全部精选样本；每个样本约 3-6 分钟。</div>
    <div class="hint en-only">Each expert is expected to annotate all curated cases; each case takes roughly 3-6 minutes.</div>
    <div id="caseList"></div>
  </aside>
  <section class="workspace" id="workspace"></section>
</main>
<div class="modal" id="modal">
  <div class="modal-card">
    <div class="modal-head">
      <strong id="modalTitle">Evidence</strong>
      <button id="closeModal">Close</button>
    </div>
    <div class="modal-body" id="modalBody"></div>
  </div>
</div>
<script type="application/json" id="case-data">__DATA__</script>
<script>
const CASES = JSON.parse(document.getElementById('case-data').textContent);
const STORE_KEY = 'sa_mcgs_human_annotation_v2';
let activeIndex = 0;
let annotations = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;', "'":'&#39;'}[c]));
const pct = (v) => (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) ? '-' : Math.round(Number(v) * 100) + '%';
const boolPill = (label, v) => `<span class="pill ${v ? 'green' : 'red'}">${label}: ${v ? 'Yes' : 'No'}</span>`;
const currentLang = () => document.body.classList.contains('lang-en') ? 'en' : 'zh';
const textFor = (obj, key) => obj?.[`${key}_${currentLang()}`] || obj?.[`${key}_en`] || '';
const annFor = (caseId) => annotations[caseId] || {};

function saveStore() {
  localStorage.setItem(STORE_KEY, JSON.stringify(annotations));
  renderCaseList();
}

function selectedNodeOptions(c) {
  const rows = [];
  const seen = new Set();
  c.important_nodes.forEach(n => {
    if (seen.has(n.node_id)) return;
    seen.add(n.node_id);
    rows.push(n);
  });
  return rows;
}

function isDone(caseId) {
  const a = annFor(caseId);
  return !!(a.structural_conflict && a.repair_sufficient && a.confidence);
}

function renderCaseList() {
  $('totalCount').textContent = CASES.length;
  $('doneCount').textContent = CASES.filter(c => isDone(c.metadata.case_id)).length;
  $('domainCount').textContent = new Set(CASES.map(c => c.metadata.domain)).size;
  $('caseList').innerHTML = CASES.map((c, i) => {
    const m = c.metadata;
    return `<button class="case-btn ${i === activeIndex ? 'active' : ''}" data-case-index="${i}">
      <span class="done">${isDone(m.case_id) ? '✓' : ''}</span>
      <span class="title">${esc(m.domain_label)} · ${esc(m.template_label)}</span>
      <span class="meta">${esc(m.model)} · SCC ${esc(m.scc_size)} · ${esc(m.case_id)}</span>
    </button>`;
  }).join('');
  document.querySelectorAll('[data-case-index]').forEach(btn => btn.addEventListener('click', () => {
    activeIndex = Number(btn.dataset.caseIndex);
    renderAll();
  }));
}

function nodeTable(c) {
  const rows = c.important_nodes.slice(0, 48).map((n, idx) => `
    <tr>
      <td>${esc(currentLang() === 'zh' ? n.role_label_zh : n.role_label_en)}</td>
      <td><code>${esc(n.node_id)}</code></td>
      <td class="node-text">${esc(currentLang() === 'zh' ? n.text_zh : n.text_en)}</td>
      <td>
        <div class="node-actions">
          ${n.is_risk_endpoint ? '<span class="pill red">risk</span>' : ''}
          ${n.is_affected ? '<span class="pill blue">affected</span>' : ''}
          ${n.in_sa_core ? '<span class="pill green">SA core</span>' : ''}
          ${n.in_oc ? '<span class="pill blue">OC</span>' : ''}
          <button data-node-index="${idx}">${currentLang() === 'zh' ? '查看文本' : 'View text'}</button>
        </div>
      </td>
    </tr>`).join('');
  return `<table>
    <thead><tr><th>Role</th><th>Node</th><th>Text</th><th>Signals</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function annotationForm(c) {
  const m = c.metadata;
  const a = annFor(m.case_id);
  const nodes = selectedNodeOptions(c);
  const checked = new Set(a.relevant_nodes || []);
  const radio = (name, value) => a[name] === value ? 'checked' : '';
  return `<div class="section">
    <h3 class="zh-only">标注填写</h3><h3 class="en-only">Annotation Form</h3>
    <div class="form-grid">
      <div class="question">
        <h4 class="zh-only">Q1. 这个 case 是否存在真实结构性冲突？</h4>
        <h4 class="en-only">Q1. Is this a real structural conflict?</h4>
        <div class="options">
          <label class="option"><input type="radio" name="structural_conflict" value="yes" ${radio('structural_conflict','yes')}>Yes</label>
          <label class="option"><input type="radio" name="structural_conflict" value="partial" ${radio('structural_conflict','partial')}>Partial</label>
          <label class="option"><input type="radio" name="structural_conflict" value="no" ${radio('structural_conflict','no')}>No</label>
          <label class="option"><input type="radio" name="structural_conflict" value="unsure" ${radio('structural_conflict','unsure')}>Unsure</label>
        </div>
      </div>
      <div class="question">
        <h4 class="zh-only">Q2. SA core 是否足以作为修复入口？</h4>
        <h4 class="en-only">Q2. Is the SA core sufficient for repair?</h4>
        <div class="options">
          <label class="option"><input type="radio" name="repair_sufficient" value="yes" ${radio('repair_sufficient','yes')}>Yes</label>
          <label class="option"><input type="radio" name="repair_sufficient" value="partial" ${radio('repair_sufficient','partial')}>Partial</label>
          <label class="option"><input type="radio" name="repair_sufficient" value="no" ${radio('repair_sufficient','no')}>No</label>
          <label class="option"><input type="radio" name="repair_sufficient" value="unsure" ${radio('repair_sufficient','unsure')}>Unsure</label>
        </div>
      </div>
      <div class="question">
        <h4 class="zh-only">Q3. 专家认为应纳入风险子图的节点</h4>
        <h4 class="en-only">Q3. Nodes that should be in the risk subgraph</h4>
        <div class="check-list">
          ${nodes.map(n => `<label><input type="checkbox" name="relevant_nodes" value="${esc(n.node_id)}" ${checked.has(n.node_id) ? 'checked' : ''}> <span><b>${esc(currentLang() === 'zh' ? n.role_label_zh : n.role_label_en)}</b><br><code>${esc(n.node_id)}</code></span></label>`).join('')}
        </div>
      </div>
      <div class="question">
        <h4 class="zh-only">Q4. 标注信心</h4>
        <h4 class="en-only">Q4. Confidence</h4>
        <select name="confidence">
          <option value="">Select / 选择</option>
          ${[1,2,3,4,5].map(v => `<option value="${v}" ${String(a.confidence || '') === String(v) ? 'selected' : ''}>${v}</option>`).join('')}
        </select>
        <p class="hint">1 = low, 5 = high</p>
      </div>
    </div>
    <div class="section">
      <h3 class="zh-only">备注 / 缺失节点 / 理由</h3><h3 class="en-only">Comments / Missing nodes / Rationale</h3>
      <textarea name="comments" rows="5" placeholder="Write comments here...">${esc(a.comments || '')}</textarea>
    </div>
    <div class="save-row">
      <button class="primary" id="saveBtn">${currentLang() === 'zh' ? '保存当前 case' : 'Save current case'}</button>
      <span class="hint">${currentLang() === 'zh' ? '会自动保存到浏览器本地；导出 Excel 时一并带出。' : 'Saved locally in this browser and included in the Excel export.'}</span>
    </div>
  </div>`;
}

function renderWorkspace() {
  const c = CASES[activeIndex];
  const m = c.metadata;
  $('workspace').innerHTML = `
    <div class="case-title">
      <div>
        <h2>${esc(m.domain_label)} · SCC ${esc(m.scc_size)}</h2>
        <div class="hint">${esc(m.case_id)} · ${esc(m.model)} · ${esc(m.template_label)}</div>
      </div>
      <div class="pillbar">
        ${boolPill('SA any', m.sa_risk_any)}
        ${boolPill('SA all', m.sa_risk_all)}
        <span class="pill green">SA comp ${pct(m.sa_compression)}</span>
        ${m.naive_error ? `<span class="pill red">Naive error</span>` : boolPill('Naive all', m.naive_risk_all)}
      </div>
    </div>
    <div class="section">
      <h3 class="zh-only">Case 说明</h3><h3 class="en-only">Case Explanation</h3>
      <div class="summary">${esc(c.case_summary[currentLang()])}</div>
    </div>
    <div class="section">
      <h3 class="zh-only">关键文本和证据节点</h3><h3 class="en-only">Key Text and Evidence Nodes</h3>
      ${nodeTable(c)}
    </div>
    ${annotationForm(c)}
  `;
  document.querySelectorAll('[data-node-index]').forEach(btn => btn.addEventListener('click', () => openNodeModal(c, Number(btn.dataset.nodeIndex))));
  $('saveBtn').addEventListener('click', saveCurrentAnnotation);
}

function saveCurrentAnnotation() {
  const c = CASES[activeIndex];
  const id = c.metadata.case_id;
  const root = $('workspace');
  const getRadio = (name) => root.querySelector(`input[name="${name}"]:checked`)?.value || '';
  annotations[id] = {
    reviewer: $('reviewer').value || '',
    structural_conflict: getRadio('structural_conflict'),
    repair_sufficient: getRadio('repair_sufficient'),
    relevant_nodes: Array.from(root.querySelectorAll('input[name="relevant_nodes"]:checked')).map(x => x.value),
    confidence: root.querySelector('select[name="confidence"]')?.value || '',
    comments: root.querySelector('textarea[name="comments"]')?.value || '',
    saved_at: new Date().toISOString()
  };
  saveStore();
}

function openNodeModal(c, idx) {
  const n = c.important_nodes[idx];
  $('modalTitle').textContent = `${n.role_label_en} · ${n.node_id}`;
  $('modalBody').innerHTML = `
    <div class="pillbar">
      ${n.is_risk_endpoint ? '<span class="pill red">risk endpoint</span>' : ''}
      ${n.is_affected ? '<span class="pill blue">affected</span>' : ''}
      ${n.in_sa_core ? '<span class="pill green">SA core</span>' : ''}
      ${n.in_naive_subgraph ? '<span class="pill">Naive subgraph</span>' : ''}
      ${n.in_oc ? '<span class="pill blue">OC</span>' : ''}
    </div>
    <p><code>${esc(n.node_id)}</code></p>
    <div class="text-panel">
      <div class="text-box"><b>English / source text</b><br>${esc(n.text_en || '-')}</div>
      <div class="text-box"><b>中文说明</b><br>${esc(n.text_zh || '-')}</div>
    </div>
    <div class="section"><b>Trace stats</b><br><code>${esc(n.stats || '-')}</code></div>
  `;
  $('modal').classList.add('open');
}

function exportExcel() {
  saveCurrentAnnotation();
  const rows = CASES.map(c => {
    const m = c.metadata;
    const a = annFor(m.case_id);
    return {
      reviewer: $('reviewer').value || a.reviewer || '',
      case_id: m.case_id,
      domain: m.domain,
      domain_label: m.domain_label,
      scc_size: m.scc_size,
      model: m.model,
      template: m.template,
      severity: m.severity,
      root_node: m.root_node,
      witness_node: m.witness_node,
      affected_nodes: m.affected_nodes,
      sa_core_nodes: m.sa_core_nodes,
      naive_subgraph_nodes: m.naive_subgraph_nodes,
      sa_root_at_3: m.sa_root_at_3,
      sa_risk_any: m.sa_risk_any,
      sa_risk_all: m.sa_risk_all,
      sa_compression: m.sa_compression,
      naive_error: m.naive_error,
      naive_root_at_3: m.naive_root_at_3,
      naive_risk_any: m.naive_risk_any,
      naive_risk_all: m.naive_risk_all,
      naive_compression: m.naive_compression,
      label_is_structural_conflict: a.structural_conflict || '',
      label_relevant_risk_nodes: (a.relevant_nodes || []).join(';'),
      label_core_is_sufficient_for_repair: a.repair_sufficient || '',
      label_confidence_1_to_5: a.confidence || '',
      label_comments: a.comments || '',
      saved_at: a.saved_at || ''
    };
  });
  if (window.XLSX) {
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(rows), 'annotations');
    XLSX.writeFile(wb, `sa_mcgs_annotations_${new Date().toISOString().slice(0,10)}.xlsx`);
  } else {
    const csv = [Object.keys(rows[0]).join(',')].concat(rows.map(r => Object.values(r).map(v => '"' + String(v ?? '').replace(/"/g, '""') + '"').join(','))).join('\\n');
    const blob = new Blob([csv], {type:'text/csv;charset=utf-8'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'sa_mcgs_annotations.csv';
    a.click();
  }
}

function renderAll() {
  renderCaseList();
  renderWorkspace();
}

$('langBtn').addEventListener('click', () => {
  document.body.classList.toggle('lang-en');
  document.body.classList.toggle('lang-zh');
  renderAll();
});
$('closeModal').addEventListener('click', () => $('modal').classList.remove('open'));
$('modal').addEventListener('click', e => { if (e.target.id === 'modal') $('modal').classList.remove('open'); });
$('exportBtn').addEventListener('click', exportExcel);
$('reviewer').addEventListener('input', () => {
  Object.values(annotations).forEach(a => { if (!a.reviewer) a.reviewer = $('reviewer').value; });
  localStorage.setItem(STORE_KEY, JSON.stringify(annotations));
});
renderAll();
</script>
</body>
</html>"""
    (ANNOT_DIR / "annotation_interface.html").write_text(page.replace("__DATA__", payload), encoding="utf-8")


def create_annotation_pack(records: list[dict[str, Any]]) -> None:
    # The expert-facing pack is intentionally small.  The full main experiment
    # remains in tables/results, but human audit should be practical to finish.
    if ANNOT_MATERIAL_DIR.exists():
        shutil.rmtree(ANNOT_MATERIAL_DIR)
    nested_old_pack = ANNOT_DIR / "human_annotation_pack"
    if nested_old_pack.exists():
        shutil.rmtree(nested_old_pack)
    for stale in ANNOT_DIR.rglob(".DS_Store"):
        stale.unlink()
    for stale in ANNOT_DIR.glob("*.html"):
        stale.unlink()
    for stale in ANNOT_DIR.glob("*.csv"):
        stale.unlink()
    for stale in ANNOT_DIR.glob("*.md"):
        stale.unlink()
    ANNOT_MATERIAL_DIR.mkdir(parents=True, exist_ok=True)

    full_pairs = select_annotation_pairs(records, per_domain=8)
    pairs = select_annotation_pairs(records, per_domain=3)
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
    full_rows: list[dict[str, Any]] = []
    for idx, pair in enumerate(full_pairs, 1):
        material = create_case_material(f"candidate_{idx:03d}_{pair['domain']}_{pair['size']}_{pair['model']}_{pair['template']}", pair)
        full_rows.append(material["metadata"])
    write_csv(ANNOT_DIR / "full_candidate_manifest_not_for_experts.csv", full_rows)
    create_annotation_html(materials)
    readme = [
        "# Human Annotation Pack / 人工标注包",
        "",
        "目的：让领域专家快速审阅少量精选 critical SCC case，判断结构性风险和风险子图是否合理。",
        "",
        "包含文件：",
        "",
        "- `annotation_interface.html`：专家使用的主入口。可切换中英文、弹窗查看节点文本、直接填写标注并导出 Excel。",
        "- `human_annotation_cases.csv`：专家小样本 manifest。",
        "- `materials/*.md` / `materials/*.json`：每个入选 case 的备查素材。",
        "- `vendor/xlsx.full.min.js`：本地 Excel 导出依赖，已打进 zip，打开 HTML 不需要联网。",
        "- `full_candidate_manifest_not_for_experts.csv`：完整候选清单，只供内部追溯，不建议发给专家。",
        "",
        "专家需要填写：",
        "",
        "- `label_is_structural_conflict`：是否确实存在结构性风险。",
        "- `label_relevant_risk_nodes`：专家认为应纳入风险子图的节点。",
        "- `label_core_is_sufficient_for_repair`：SA core 是否足够作为修复入口。",
        "- `label_confidence_1_to_5`：标注信心。",
        "- `label_comments`：自由说明或缺失节点。",
        "",
        f"当前专家包包含 `{len(csv_rows)}` 个精选 case，每个领域约 `{3}` 个；不是全量 80-case 主实验。",
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
            if path == zip_path or path.is_dir() or path.name == ".DS_Store":
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
        "- `human_annotation_pack/`：专家标注小包，含精选 case、可填写 HTML、本地 Excel 导出依赖和 zip。",
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
        "- Selected-case CSV: `human_annotation_pack/human_annotation_cases.csv`",
        "- Internal full candidate manifest: `human_annotation_pack/full_candidate_manifest_not_for_experts.csv`",
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
- [`paper_assets/human_annotation_pack/human_annotation_pack.zip`](paper_assets/human_annotation_pack/human_annotation_pack.zip)：给专家标注的精选小包，含 12 个 case、可填写中英文 HTML、节点文本弹窗和一键 Excel 导出。

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

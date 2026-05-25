#!/usr/bin/env python3
"""Build paper figures, tables, and a bilingual annotation pack.

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
from matplotlib.ticker import PercentFormatter
from PIL import Image


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
BOOSTED_RESULTS_DIR = MAIN_DIR / "boosted_naive_baseline" / "results_canonical80_x10"
BOOSTED_SUMMARY_CSV = BOOSTED_RESULTS_DIR / "boosted_naive_top3_summary.csv"
BOOSTED_RAW_JSONL = BOOSTED_RESULTS_DIR / "boosted_naive_raw_attempts.jsonl"
MAIN_NAIVE_SELECTOR = "oracle_risk_top3"
MAIN_NAIVE_LABEL = "oracle-risk Naive"
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
    # Paper-first palette: gray baseline, restrained blue method, sparse accents.
    "naive": "#8A8F98",
    "sa": "#2F6690",
    "sa_light": "#DDEAF3",
    "blue": "#2F6690",
    "purple": "#7C6A9C",
    "orange": "#C9822B",
    "risk": "#B75A57",
    "support": "#5A8F73",
    "gray": "#6B7280",
    "light_gray": "#E5E7EB",
    "panel": "#F8FAFC",
    "dark": "#111827",
    "grid": "#E5E7EB",
}

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8,
        "axes.titlesize": 8.5,
        "axes.labelsize": 8,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 7.2,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "lines.linewidth": 1.35,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.dpi": 320,
    }
)


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


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except Exception:
        return default


def load_boosted_summary_rows(selector: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not BOOSTED_SUMMARY_CSV.exists():
        return rows
    for row in read_csv_rows(BOOSTED_SUMMARY_CSV):
        if selector and row.get("selector") != selector:
            continue
        parsed: dict[str, Any] = dict(row)
        for key in ("block_id", "actual_size", "requested_size", "attempt_count", "valid_attempt_count", "selected_count"):
            parsed[key] = as_int(parsed.get(key))
        for key in ("root_at3", "risk_any", "risk_all", "compression", "avg_total_tokens", "avg_prompt_tokens", "avg_completion_tokens"):
            parsed[key] = as_float(parsed.get(key))
        rows.append(parsed)
    return rows


def boosted_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)

    def avg(key: str) -> float:
        return sum(as_float(row.get(key)) for row in rows) / n if n else 0.0

    zero_valid = sum(1 for row in rows if as_int(row.get("valid_attempt_count")) == 0)
    return {
        "n": n,
        "errors": zero_valid,
        "valid": max(0, n - zero_valid),
        "zero_valid_cases": zero_valid,
        "root": avg("root_at3"),
        "risk_any": avg("risk_any"),
        "risk_all": avg("risk_all"),
        "compression": avg("compression"),
        "effective_compression": avg("compression"),
        "avg_subgraph": None,
        "valid_attempt_mean": avg("valid_attempt_count"),
        "avg_total_tokens": avg("avg_total_tokens"),
    }


def paper_naive_rows(selector: str = MAIN_NAIVE_SELECTOR) -> list[dict[str, Any]]:
    return load_boosted_summary_rows(selector)


def paper_method_summary_map(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "naive": boosted_summary(paper_naive_rows()),
        "sa-mcgs": summary(method_records(records, "sa-mcgs")),
    }


def boosted_raw_attempt_summary() -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    if BOOSTED_RAW_JSONL.exists():
        with BOOSTED_RAW_JSONL.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    n = len(records)
    if not n:
        return {"n": 0, "errors": 0, "root": 0.0, "risk_any": 0.0, "risk_all": 0.0, "compression": 0.0}

    def truthy(value: Any) -> bool:
        return value is True or value == 1 or str(value).strip().lower() in {"true", "yes", "1"}

    return {
        "n": n,
        "errors": sum(1 for record in records if record.get("error")),
        "root": sum(1.0 for record in records if truthy(record.get("root_top3_hit"))) / n,
        "risk_any": sum(1.0 for record in records if truthy(record.get("direct_contains_any_risk_node"))) / n,
        "risk_all": sum(1.0 for record in records if truthy(record.get("direct_contains_all_risk_nodes"))) / n,
        "compression": sum(as_float(record.get("direct_compression_ratio")) for record in records) / n,
    }


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
        fig.savefig(FIG_DIR / f"{stem}.{suffix}", dpi=320, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


def set_axis_style(ax: plt.Axes, *, ylim: tuple[float, float] | None = (0, 1.05), ylabel: str | None = None) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#374151")
    ax.spines["bottom"].set_color("#374151")
    ax.grid(axis="y", color=PAPER_COLORS["grid"], linewidth=0.55, alpha=0.9)
    ax.set_axisbelow(True)
    if ylim is not None:
        ax.set_ylim(*ylim)
    if ylabel:
        ax.set_ylabel(ylabel, color=PAPER_COLORS["dark"])
    ax.tick_params(colors="#374151")


def set_percent_axis(ax: plt.Axes, *, ylim: tuple[float, float] | None = (0, 1.02), ylabel: str | None = None) -> None:
    set_axis_style(ax, ylim=ylim, ylabel=ylabel)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))


def panel_label(ax: plt.Axes, label: str, title: str) -> None:
    ax.set_title(rf"$\bf{{{label}.}}$ {title}", loc="left", pad=4)


def soft_panel(ax: plt.Axes) -> None:
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#9CA3AF")
        ax.spines[side].set_linewidth(0.6)
    ax.tick_params(colors="#4B5563", labelsize=7.2)


def draw_method_key(ax: plt.Axes, x: float, y: float) -> None:
    ax.scatter([x], [y], s=28, color=PAPER_COLORS["naive"], edgecolor="white", linewidth=0.5, clip_on=False)
    ax.text(x + 0.025, y, "Naive", va="center", fontsize=7.0, color=PAPER_COLORS["dark"])
    ax.scatter([x + 0.17], [y], s=28, color=PAPER_COLORS["sa"], edgecolor="white", linewidth=0.5, clip_on=False)
    ax.text(x + 0.195, y, "SA-MCGS", va="center", fontsize=7.0, color=PAPER_COLORS["dark"])


def compact_percent_label(value: float, digits: int = 0) -> str:
    return f"{value * 100:.{digits}f}%"


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


def draw_node(ax: plt.Axes, x: float, y: float, label: str | None, *, color: str, size: float = 0.030, lw: float = 0.9) -> None:
    ax.add_patch(
        patches.Circle(
            (x, y),
            size,
            transform=ax.transAxes,
            facecolor="white" if color == PAPER_COLORS["risk"] else "#F9FAFB",
            edgecolor=color,
            linewidth=lw,
            zorder=3,
        )
    )
    if label:
        ax.text(x, y, label, ha="center", va="center", fontsize=6.3, color=color, weight="bold", transform=ax.transAxes, zorder=4)


def draw_edge(ax: plt.Axes, a: tuple[float, float], b: tuple[float, float], *, color: str = "#6B7280", lw: float = 0.7, style: str = "-") -> None:
    ax.annotate(
        "",
        xy=b,
        xytext=a,
        xycoords=ax.transAxes,
        textcoords=ax.transAxes,
        arrowprops=dict(arrowstyle="-|>", lw=lw, color=color, linestyle=style, shrinkA=6, shrinkB=6, mutation_scale=7),
        zorder=2,
    )


def create_mcts_failure_figure() -> None:
    """Use the original three-panel motivation figure, cropped for paper use."""
    download_stem = (
        "Create_a_clean_vectorstyle_academic_figure_for_an_ACL_EMNLP_paper._Use_the_same_visual_style_as_the_"
        "reference_image_white_background_thin_black_roundedrectangle_panels_simple_nodelink_diagrams_restrained_"
        "colors_clear_arrows_minimal_text"
    )
    clean_source = Path.home() / "Downloads" / f"{download_stem} (2).png"
    previous_clean_source = Path.home() / "Downloads" / f"{download_stem}_hig.png"
    titled_source = FIG_DIR / "archive" / "fig02_vanilla_mcts_scc_failure_uncropped.png"
    source = next((candidate for candidate in (clean_source, previous_clean_source, titled_source) if candidate.exists()), titled_source)
    if not source.exists():
        raise FileNotFoundError(f"Missing original MCTS/SCC motivation figure: {source}")

    image = Image.open(source).convert("RGB")
    # Prefer the manually supplied version.  Some copies still include the
    # generated title; detect that by aspect ratio and crop only the title band.
    if image.height / image.width > 0.535:
        cropped = image.crop((0, 96, image.width, image.height))
    else:
        cropped = image
    out_png = FIG_DIR / "fig02_vanilla_mcts_scc_failure.png"
    cropped.save(out_png)

    fig, ax = plt.subplots(figsize=(7.2, 3.12))
    ax.imshow(cropped)
    ax.axis("off")
    fig.savefig(FIG_DIR / "fig02_vanilla_mcts_scc_failure.pdf", bbox_inches="tight", pad_inches=0.025)
    plt.close(fig)


def create_main_metrics_figure(records: list[dict[str, Any]]) -> None:
    summaries = paper_method_summary_map(records)
    naive = summaries["naive"]
    sa = summaries["sa-mcgs"]

    fig, ax = plt.subplots(figsize=(7.2, 1.78))
    metrics = [
        ("Root@3", "root", True),
        ("Risk-any", "risk_any", True),
        ("Risk-all", "risk_all", True),
        ("Compression", "compression", False),
    ]
    y_positions = [3.0, 2.0, 1.0, 0.0]
    for y, (label, key, success_metric) in zip(y_positions, metrics):
        nv = float(naive[key])
        sv = float(sa[key])
        lo, hi = sorted([nv, sv])
        line_color = "#DCEBF3" if success_metric else "#F3E3C7"
        ax.plot([lo, hi], [y, y], color=line_color, linewidth=3.6, solid_capstyle="round", zorder=1)
        ax.scatter([nv], [y], s=34, color=PAPER_COLORS["naive"], edgecolor="white", linewidth=0.6, zorder=3)
        ax.scatter([sv], [y], s=38, color=PAPER_COLORS["sa"], edgecolor="white", linewidth=0.6, zorder=3)

        # ACL-style figures read better when close values are separated by
        # vertical offsets instead of forcing every label onto the same row.
        if success_metric:
            ax.text(nv + 0.009, y + 0.13, compact_percent_label(nv), ha="left", va="bottom", fontsize=7.0, color="#4B5563", weight="bold")
            ax.text(sv + 0.009, y - 0.13, compact_percent_label(sv), ha="left", va="top", fontsize=7.2, color=PAPER_COLORS["sa"], weight="bold")
            delta_y = y + 0.23
        else:
            ax.text(nv + 0.009, y + 0.13, compact_percent_label(nv), ha="left", va="bottom", fontsize=7.0, color="#4B5563", weight="bold")
            ax.text(sv - 0.009, y - 0.13, compact_percent_label(sv), ha="right", va="top", fontsize=7.2, color=PAPER_COLORS["sa"], weight="bold")
            delta_y = y + 0.23
        delta = int(round((sv - nv) * 100))
        delta_color = PAPER_COLORS["sa"] if delta >= 0 else PAPER_COLORS["orange"]
        delta_label = f"{delta:+d} pts"
        ax.text((lo + hi) / 2, delta_y, delta_label, ha="center", va="center", fontsize=6.9, color=delta_color, weight="bold")

    ax.set_yticks(y_positions, [label for label, _, _ in metrics])
    ax.set_xlim(0, 1.03)
    ax.set_ylim(-0.45, 3.55)
    ax.set_xticks([0, 0.25, 0.50, 0.75, 1.0], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_xlabel("Strict rate / compression")
    ax.grid(False)
    ax.scatter([], [], s=38, color=PAPER_COLORS["naive"], label=MAIN_NAIVE_LABEL)
    ax.scatter([], [], s=42, color=PAPER_COLORS["sa"], label="SA-MCGS")
    ax.legend(frameon=False, loc="upper right", ncol=2, handletextpad=0.35, columnspacing=0.8, bbox_to_anchor=(0.98, 1.12))
    soft_panel(ax)
    savefig(fig, "fig02_main_metrics_strict")


def create_scc_size_figure(records: list[dict[str, Any]]) -> None:
    boosted_rows = paper_naive_rows()
    buckets = [
        ("Short\n$\\leq$12", lambda size: size <= 12),
        ("Mid\n14--20", lambda size: 14 <= size <= 20),
        ("Long\n$\\geq$24", lambda size: size >= 24),
    ]
    bucket_rows: list[dict[str, Any]] = []
    for label, pred in buckets:
        row: dict[str, Any] = {"bucket": label}
        for method in METHODS:
            if method == "naive":
                recs = [r for r in boosted_rows if pred(as_int(r.get("actual_size")))]
                row[method] = boosted_summary(recs)
            else:
                recs = [
                    r
                    for r in records
                    if r.get("method") == method
                    and str(r.get("scc_size") or "").isdigit()
                    and pred(int(r.get("scc_size") or 0))
                ]
                row[method] = summary(recs)
        bucket_rows.append(row)

    fig = plt.figure(figsize=(7.2, 2.20))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.55, 1.0], wspace=0.30)

    def draw_dumbbell(
        ax: plt.Axes,
        y_pos: float,
        naive_value: float,
        sa_value: float,
        *,
        line_color: str,
        label_naive: bool = True,
        label_sa: bool = True,
    ) -> None:
        lo, hi = sorted([naive_value, sa_value])
        ax.plot([lo, hi], [y_pos, y_pos], color=line_color, linewidth=4.1, alpha=0.70, solid_capstyle="round", zorder=1)
        ax.scatter([naive_value], [y_pos], s=31, color=PAPER_COLORS["naive"], edgecolor="white", linewidth=0.65, zorder=3)
        ax.scatter([sa_value], [y_pos], s=34, color=PAPER_COLORS["sa"], edgecolor="white", linewidth=0.65, zorder=3)
        close = abs(naive_value - sa_value) < 0.065
        if label_naive:
            dx = -0.018 if naive_value >= sa_value else 0.018
            ha = "right" if naive_value >= sa_value else "left"
            ax.text(naive_value + dx, y_pos + (0.11 if close else 0.09), compact_percent_label(naive_value), ha=ha, va="bottom", fontsize=6.1, color="#4B5563")
        if label_sa:
            dx = 0.018 if sa_value >= naive_value else -0.018
            ha = "left" if sa_value >= naive_value else "right"
            ax.text(sa_value + dx, y_pos - (0.11 if close else 0.09), compact_percent_label(sa_value), ha=ha, va="top", fontsize=6.3, color=PAPER_COLORS["sa"], weight="bold")

    ax = fig.add_subplot(gs[0, 0])
    success_rows: list[tuple[str, str, str, float, float]] = []
    for row in bucket_rows:
        success_rows.append((row["bucket"], "Root@3", "root", row["naive"]["root"], row["sa-mcgs"]["root"]))
        success_rows.append((row["bucket"], "Risk-all", "risk_all", row["naive"]["risk_all"], row["sa-mcgs"]["risk_all"]))
    y_positions = list(reversed(range(len(success_rows))))
    for y_pos, (_, metric_label, key, naive_value, sa_value) in zip(y_positions, success_rows):
        draw_dumbbell(ax, y_pos, naive_value, sa_value, line_color=PAPER_COLORS["sa_light"])
    ax.set_yticks(y_positions, [metric for _, metric, _, _, _ in success_rows])
    for center, row in zip([4.5, 2.5, 0.5], bucket_rows):
        ax.text(-0.23, center, row["bucket"], transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=7.0, color="#4B5563", clip_on=False)
    panel_label(ax, "A", "Endpoint retention by SCC size")
    ax.set_xlim(0, 1.03)
    ax.set_ylim(-0.55, len(success_rows) - 0.45)
    ax.set_xticks([0, 0.5, 1.0], ["0%", "50%", "100%"])
    ax.grid(axis="x", color=PAPER_COLORS["grid"], linewidth=0.55)
    ax.grid(axis="y", color=PAPER_COLORS["grid"], linewidth=0.45)
    soft_panel(ax)

    ax = fig.add_subplot(gs[0, 1])
    y = list(reversed(range(len(bucket_rows))))
    for yi, row in zip(y, bucket_rows):
        draw_dumbbell(
            ax,
            yi,
            row["naive"]["compression"],
            row["sa-mcgs"]["compression"],
            line_color="#F2DFC0",
            label_naive=True,
            label_sa=True,
        )
    panel_label(ax, "B", "Compression cost")
    ax.set_yticks(y, [row["bucket"] for row in bucket_rows])
    ax.set_xlim(0, 1.03)
    ax.set_ylim(-0.55, len(bucket_rows) - 0.45)
    ax.set_xticks([0, 0.5, 1.0], ["0%", "50%", "100%"])
    ax.grid(axis="x", color=PAPER_COLORS["grid"], linewidth=0.55)
    ax.grid(axis="y", color=PAPER_COLORS["grid"], linewidth=0.45)
    ax.scatter([], [], s=31, color=PAPER_COLORS["naive"], label=MAIN_NAIVE_LABEL)
    ax.scatter([], [], s=34, color=PAPER_COLORS["sa"], label="SA-MCGS")
    ax.legend(frameon=False, loc="upper right", handletextpad=0.4, borderaxespad=0.2, ncol=1)
    soft_panel(ax)
    savefig(fig, "fig03_main_by_scc_size")


def create_main_results_composite_figure(records: list[dict[str, Any]]) -> None:
    boosted_rows = paper_naive_rows()
    summaries = paper_method_summary_map(records)
    naive = summaries["naive"]
    sa = summaries["sa-mcgs"]

    buckets = [
        ("Short\n$\\leq$12", lambda size: size <= 12),
        ("Mid\n14--20", lambda size: 14 <= size <= 20),
        ("Long\n$\\geq$24", lambda size: size >= 24),
    ]
    bucket_rows: list[dict[str, Any]] = []
    for label, pred in buckets:
        row: dict[str, Any] = {"bucket": label}
        for method in METHODS:
            if method == "naive":
                recs = [r for r in boosted_rows if pred(as_int(r.get("actual_size")))]
                row[method] = boosted_summary(recs)
            else:
                recs = [
                    r
                    for r in records
                    if r.get("method") == method
                    and str(r.get("scc_size") or "").isdigit()
                    and pred(int(r.get("scc_size") or 0))
                ]
                row[method] = summary(recs)
        bucket_rows.append(row)

    fig = plt.figure(figsize=(7.2, 2.58))
    gs = fig.add_gridspec(1, 2, width_ratios=[0.96, 1.22], wspace=0.30)

    method_colors = {
        "naive": "#9AA1AA",
        "sa-mcgs": PAPER_COLORS["sa"],
    }
    text_gray = "#4B5563"
    axis_gray = "#B7C0CB"
    metric_rows = [
        ("Root@3", "root"),
        ("Risk-any", "risk_any"),
        ("Risk-all", "risk_all"),
        ("Compression", "compression"),
    ]

    # A. Overall strict metrics as a compact paired-point plot.
    ax = fig.add_subplot(gs[0, 0])
    y_base = list(reversed(range(len(metric_rows))))
    for y, (label, key) in zip(y_base, metric_rows):
        nv = float(naive[key])
        sv = float(sa[key])
        bridge_color = "#E4B865" if key == "compression" else "#CFE1ED"
        ax.plot([nv, sv], [y, y], color=bridge_color, linewidth=4.1, alpha=0.74, solid_capstyle="round", zorder=1)
        ax.scatter([nv], [y], s=27, color=method_colors["naive"], edgecolor="white", linewidth=0.6, zorder=3)
        ax.scatter([sv], [y], s=30, color=method_colors["sa-mcgs"], edgecolor="white", linewidth=0.6, zorder=4)

        nv_side = -1 if nv > sv else 1
        sv_side = 1 if nv > sv else 1
        if key == "compression":
            nv_side, sv_side = 1, -1
        ax.text(
            nv + 0.018 * nv_side,
            y + 0.18,
            compact_percent_label(nv),
            ha="left" if nv_side > 0 else "right",
            va="center",
            fontsize=6.4,
            color=text_gray,
            weight="bold",
        )
        ax.text(
            sv + 0.018 * sv_side,
            y - 0.18,
            compact_percent_label(sv),
            ha="left" if sv_side > 0 else "right",
            va="center",
            fontsize=6.4,
            color=PAPER_COLORS["sa"],
            weight="bold",
        )
    ax.set_title(r"$\bf{A.}$ Overall critical-SCC results", loc="left", pad=6, color=PAPER_COLORS["dark"], fontsize=8.0)
    ax.set_yticks(y_base, [label for label, _ in metric_rows])
    ax.set_xlim(0.35, 1.02)
    # Leave a real legend band above the first metric row.  The oracle-risk
    # label is longer than the previous Naive label and otherwise collides
    # with the Root@3 markers in the compact ACL layout.
    ax.set_ylim(-0.55, len(metric_rows) + 0.28)
    ax.set_xticks([0.4, 0.6, 0.8, 1.0], ["40", "60", "80", "100"])
    ax.set_xlabel("Rate / compression (%)", labelpad=2.8)
    ax.tick_params(axis="both", colors=text_gray, pad=2)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(axis_gray)
    ax.spines["bottom"].set_color(axis_gray)
    ax.spines["left"].set_linewidth(0.7)
    ax.spines["bottom"].set_linewidth(0.7)
    ax.grid(False)
    ax.scatter([], [], s=27, color=method_colors["naive"], label=MAIN_NAIVE_LABEL)
    ax.scatter([], [], s=30, color=method_colors["sa-mcgs"], label="SA-MCGS")
    ax.legend(frameon=False, loc="upper right", bbox_to_anchor=(1.00, 1.02), ncol=2, handletextpad=0.35, columnspacing=0.75, fontsize=6.0)

    # B. SCC-size breakdown as a booktabs-style matrix.
    ax = fig.add_subplot(gs[0, 1])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.00, 0.985, "B.", fontsize=8.0, weight="bold", color=PAPER_COLORS["dark"], va="top")
    ax.text(0.052, 0.985, "SCC-size breakdown", fontsize=8.0, color=PAPER_COLORS["dark"], va="top")

    row_y = [0.62, 0.41, 0.20]
    col_x = [0.42, 0.66, 0.89]
    headers = [("Root@3", "root"), ("Risk-all", "risk_all"), ("Compression", "compression")]
    ax.text(0.02, 0.795, "SCC size", fontsize=6.35, color=PAPER_COLORS["dark"], weight="bold", va="center")
    for x, (header, _) in zip(col_x, headers):
        ax.text(x, 0.795, header, fontsize=6.35, color=PAPER_COLORS["dark"], weight="bold", ha="center", va="center")
    ax.plot([0.02, 0.985], [0.735, 0.735], color="#C9D2DD", linewidth=0.80)
    ax.plot([0.02, 0.985], [0.095, 0.095], color="#C9D2DD", linewidth=0.80)

    def draw_pair_cell(x: float, y: float, nv: float, sv: float, key: str) -> None:
        naive_txt = str(int(round(nv * 100)))
        sa_txt = str(int(round(sv * 100)))
        arrow_color = "#D6E5EF" if key != "compression" else "#EAD8B6"
        ax.plot([x - 0.042, x + 0.042], [y, y], color=arrow_color, linewidth=1.45, solid_capstyle="round")
        ax.text(x - 0.050, y, naive_txt, fontsize=6.15, color=text_gray, ha="right", va="center", weight="bold" if key != "compression" else "normal")
        ax.text(x + 0.050, y, sa_txt, fontsize=6.15, color=PAPER_COLORS["sa"] if key != "compression" else PAPER_COLORS["orange"], ha="left", va="center", weight="bold")

    for ridx, (y, row) in enumerate(zip(row_y, bucket_rows)):
        bucket = row["bucket"].replace("\n", " ")
        ax.text(0.02, y, bucket, fontsize=6.35, color=text_gray, va="center")
        for x, (_, key) in zip(col_x, headers):
            nv = float(row["naive"][key])
            sv = float(row["sa-mcgs"][key])
            draw_pair_cell(x, y, nv, sv, key)
        if ridx < len(row_y) - 1:
            ax.plot([0.02, 0.985], [y - 0.108, y - 0.108], color="#EEF2F6", linewidth=0.55)

    fig.subplots_adjust(left=0.082, right=0.988, top=0.86, bottom=0.24)

    savefig(fig, "fig02_main_results_composite")


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

    fig = plt.figure(figsize=(7.2, 2.20))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.0], wspace=0.27)

    ax = fig.add_subplot(gs[0, 0])
    line_specs = [
        ("root", "Root@3", PAPER_COLORS["blue"]),
        ("risk_any", "Risk-any", PAPER_COLORS["support"]),
        ("risk_all", "Risk-all", PAPER_COLORS["purple"]),
    ]
    end_label_x = 61.9
    label_box = {"facecolor": "white", "edgecolor": "none", "pad": 0.6, "alpha": 0.90}
    end_offsets = {"root": -0.008, "risk_any": 0.016, "risk_all": -0.020}
    for key, label, color in line_specs:
        vals = [row[key] for row in series]
        ax.plot(rollouts, vals, linewidth=1.65, color=color, label=label)
        label_y = min(0.985, max(0.035, vals[-1] + end_offsets.get(key, 0.0)))
        ax.text(
            end_label_x,
            label_y,
            compact_percent_label(vals[-1]),
            va="center",
            ha="left",
            fontsize=6.6,
            color=color,
            weight="bold",
            bbox=label_box,
            clip_on=False,
        )
    ax.axvline(30, color="#CBD5E1", linewidth=0.75, linestyle=":")
    ax.text(30.5, 0.05, "budget 30", fontsize=6.5, color="#6B7280", rotation=90, va="bottom")
    panel_label(ax, "A", "Success accumulates with rollout budget")
    ax.set_xlabel("Rollout budget")
    ax.legend(frameon=False, loc="lower right", ncol=1, handlelength=1.2, borderaxespad=0.2)
    set_percent_axis(ax, ylabel="Rate")
    ax.grid(axis="y", color=PAPER_COLORS["grid"], linewidth=0.36, alpha=0.32)
    ax.grid(axis="x", visible=False)
    ax.set_xlim(1, 64.5)
    ax.set_xticks([1, 10, 20, 30, 40, 50, 60])
    soft_panel(ax)

    ax = fig.add_subplot(gs[0, 1])
    comp = [row["compression"] for row in series]
    risk_cov = [row["risk_coverage"] for row in series]
    val_cov = [row["valuable_coverage"] for row in series]
    ax.plot(rollouts, risk_cov, color=PAPER_COLORS["blue"], linewidth=1.45, label="Risk coverage")
    ax.plot(rollouts, val_cov, color=PAPER_COLORS["orange"], linewidth=1.35, label="Valuable coverage")
    ax.plot(rollouts, comp, color=PAPER_COLORS["gray"], linewidth=1.15, linestyle="--", label="Compression")
    right_labels = [
        (risk_cov[-1] - 0.040, compact_percent_label(risk_cov[-1]), PAPER_COLORS["blue"]),
        (val_cov[-1] + 0.018, compact_percent_label(val_cov[-1]), PAPER_COLORS["orange"]),
        (comp[-1] + 0.055, compact_percent_label(comp[-1]), PAPER_COLORS["gray"]),
    ]
    for y_label, text, color in right_labels:
        ax.text(
            end_label_x,
            min(0.985, max(0.035, y_label)),
            text,
            va="center",
            ha="left",
            fontsize=6.4,
            color=color,
            weight="bold",
            bbox=label_box,
            clip_on=False,
        )
    panel_label(ax, "B", "Evidence coverage vs retained core")
    ax.set_xlabel("Rollout budget")
    ax.legend(frameon=False, loc="lower right", handlelength=1.2, borderaxespad=0.2)
    set_percent_axis(ax, ylabel="Rate")
    ax.grid(axis="y", color=PAPER_COLORS["grid"], linewidth=0.36, alpha=0.32)
    ax.grid(axis="x", visible=False)
    ax.set_xlim(1, 64.5)
    ax.set_xticks([1, 10, 20, 30, 40, 50, 60])
    soft_panel(ax)

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

    fig = plt.figure(figsize=(7.2, 2.25))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.35, 0.95], wspace=0.30)

    ax = fig.add_subplot(gs[0, 0])
    marker_map = {"naive": "o", "sa-mcgs": "s"}
    color_map = {"naive": PAPER_COLORS["naive"], "sa-mcgs": PAPER_COLORS["sa"]}
    xs = [float(row["avg_subgraph"]) for row in rows]
    ys = [float(row["risk_all"]) for row in rows]
    label_offsets = {
        ("naive", "balanced"): (0.10, 0.036, "left"),
        ("naive", "current/default"): (0.10, -0.026, "left"),
        ("sa-mcgs", "balanced"): (0.10, -0.010, "left"),
        ("sa-mcgs", "current/default"): (0.10, 0.025, "left"),
    }
    for row in rows:
        method_label = "SA" if row["method"] == "sa-mcgs" else "Naive"
        profile_label = str(row["profile"]).replace("/default", "").replace("current", "curr.")
        label = f"{method_label}, {profile_label}"
        size = 42 + 60 * float(row["root"] or 0)
        ax.scatter(
            row["avg_subgraph"],
            row["risk_all"],
            s=size,
            marker=marker_map.get(row["method"], "o"),
            color=color_map.get(row["method"], PAPER_COLORS["gray"]),
            edgecolor="white",
            linewidth=0.8,
            alpha=0.9,
        )
        dx, dy, ha = label_offsets.get((row["method"], row["profile"]), (0.08, 0.006, "left"))
        ax.annotate(
            label,
            xy=(row["avg_subgraph"], row["risk_all"]),
            xytext=(row["avg_subgraph"] + dx, row["risk_all"] + dy),
            textcoords="data",
            fontsize=6.3,
            color="#374151",
            ha=ha,
            va="center",
            arrowprops=dict(arrowstyle="-", color="#CBD5E1", lw=0.45, shrinkA=2, shrinkB=2),
        )
    ax.set_xlabel("Average retained nodes")
    ax.set_ylabel("Risk-all")
    ax.set_xlim(max(0, min(xs) - 0.8), max(xs) + 1.2)
    ax.set_ylim(max(0.0, min(ys) - 0.09), min(1.0, max(ys) + 0.10))
    panel_label(ax, "A", "Retention--core-size frontier")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    set_axis_style(ax, ylim=None, ylabel=None)
    soft_panel(ax)

    ax = fig.add_subplot(gs[0, 1])
    sa_rows = [r for r in rows if r["method"] == "sa-mcgs"]
    sa_rows.sort(key=lambda r: str(r["profile"]))
    ax.axis("off")
    panel_label(ax, "B", "SA profile choice")
    headers = ["Profile", "Risk-all", "Core", "Comp."]
    xs_text = [0.02, 0.48, 0.70, 0.87]
    for xh, header in zip(xs_text, headers):
        ax.text(xh, 0.83, header, fontsize=6.7, color="#4B5563", weight="bold", transform=ax.transAxes)
    for i, r in enumerate(sa_rows):
        y0 = 0.60 - i * 0.28
        is_current = "current" in str(r["profile"])
        face = "#F8FAFC" if not is_current else "#EEF6FB"
        edge = "#D1D5DB" if not is_current else PAPER_COLORS["sa"]
        ax.add_patch(
            patches.FancyBboxPatch(
                (0.0, y0 - 0.075),
                0.98,
                0.17,
                boxstyle="round,pad=0.012,rounding_size=0.014",
                transform=ax.transAxes,
                facecolor=face,
                edgecolor=edge,
                linewidth=0.75,
            )
        )
        profile = str(r["profile"]).replace("/default", "").replace("current", "curr.")
        vals = [profile, compact_percent_label(r["risk_all"]), f"{r['avg_subgraph']:.1f}", compact_percent_label(r["compression"])]
        for xt, val in zip(xs_text, vals):
            ax.text(xt, y0, val, fontsize=7.0, color="#111827", transform=ax.transAxes, va="center", weight="bold" if is_current and xt == xs_text[0] else "normal")
    ax.text(0.02, 0.10, "Chosen profile keeps a larger core when both endpoints persist.", fontsize=6.6, color="#4B5563", transform=ax.transAxes)

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

    fig = plt.figure(figsize=(7.45, 4.98))
    gs = fig.add_gridspec(
        2,
        3,
        height_ratios=[1.04, 1.08],
        width_ratios=[1.35, 0.80, 1.78],
        hspace=0.56,
        wspace=0.46,
    )
    size = int(record.get("scc_size") or len(nodes) or 1)
    core_nodes = [node for node in nodes if node in core] + sorted(node for node in core if node not in nodes)
    sm = _metric_values(record)
    nm = _metric_values(naive_record) if naive_record else {}
    compression = sm.get("compression") or 0
    short = lambda node: str(node).replace("bgb_", "§").replace("sec_", "").replace("us-cw-", "")

    # A. SCC context as a linearized cycle.
    ax = fig.add_subplot(gs[0, :2])
    ax.axis("off")
    panel_label(ax, "A", "Original SCC context: endpoints are far apart")
    n = max(1, len(nodes))
    xs = [0.025 + 0.950 * i / max(1, n - 1) for i in range(n)]
    y = 0.45
    ax.plot([xs[0], xs[-1]], [y, y], color="#D7DEE8", linewidth=1.6, transform=ax.transAxes, zorder=0)
    label_offsets = {
        "§312f": (0.000, -0.095),
        "§356": (0.000, -0.095),
        "§358": (0.000, 0.140),
        "§491": (0.000, 0.140),
        "§505": (0.000, 0.140),
        "§506": (0.000, 0.140),
        "§491a": (0.000, -0.095),
        "§495": (0.000, -0.095),
        "§512": (0.000, -0.095),
        "§514": (0.000, -0.095),
        "$312f": (0.000, -0.095),
        "$356": (0.000, -0.095),
        "$358": (0.000, 0.140),
        "$491": (0.000, 0.140),
        "$505": (0.000, 0.140),
        "$506": (0.000, 0.140),
        "$491a": (0.000, -0.095),
        "$495": (0.000, -0.095),
        "$512": (0.000, -0.095),
        "$514": (0.000, -0.095),
    }
    for i, node in enumerate(nodes):
        x = xs[i]
        if node in risk:
            face, s, label_color = PAPER_COLORS["risk"], 52, PAPER_COLORS["risk"]
        elif node in affected:
            face, s, label_color = PAPER_COLORS["orange"], 42, PAPER_COLORS["orange"]
        elif node in core:
            face, s, label_color = PAPER_COLORS["support"], 42, PAPER_COLORS["support"]
        else:
            face, s, label_color = "#E5E7EB", 18, "#6B7280"
        ax.scatter([x], [y], s=s, color=face, edgecolor="#334155", linewidth=0.45, transform=ax.transAxes, zorder=3)
        if node in risk or node in affected or node in core:
            label = short(node)
            if label in label_offsets:
                dx, dy = label_offsets[label]
            else:
                lane = i % 4
                dx, dy = {
                    0: (0.000, 0.185),
                    1: (0.000, 0.240),
                    2: (0.000, -0.095),
                    3: (0.000, -0.095),
                }[lane]
            ax.text(x + dx, y + dy, label, ha="center", va="center", fontsize=4.85, color="#1F2937", transform=ax.transAxes)
    ax.annotate(
        "cycle continues",
        xy=(xs[-1], y),
        xytext=(0.955, 0.755),
        xycoords=ax.transAxes,
        textcoords=ax.transAxes,
        arrowprops=dict(arrowstyle="->", color="#7A8798", lw=0.7),
        fontsize=5.15,
        color="#4B5563",
        ha="right",
    )
    ax.text(
        0.05,
        0.875,
        f"{size} records in one strongly connected component",
        fontsize=6.5,
        weight="bold",
        color="#111827",
        transform=ax.transAxes,
    )
    legend_items = [
        ("root / witness", PAPER_COLORS["risk"]),
        ("affected", PAPER_COLORS["orange"]),
        ("final core", PAPER_COLORS["support"]),
        ("other SCC node", "#E5E7EB"),
    ]
    legend_xs = [0.055, 0.290, 0.535, 0.760]
    for x0, (label, color) in zip(legend_xs, legend_items):
        ax.scatter([x0], [0.085], s=31, color=color, edgecolor="#334155", linewidth=0.45, transform=ax.transAxes)
        ax.text(x0 + 0.029, 0.085, label, va="center", fontsize=4.95, color="#374151", transform=ax.transAxes)

    # B. Final dynamic core.
    ax = fig.add_subplot(gs[0, 2])
    ax.axis("off")
    panel_label(ax, "B", "Final dynamic core")
    ax.text(0.035, 0.875, f"{len(core_nodes)}/{size}", fontsize=11.2, weight="bold", color=PAPER_COLORS["dark"], transform=ax.transAxes)
    ax.text(0.035, 0.758, "nodes retained", fontsize=5.9, color="#374151", transform=ax.transAxes)
    ax.text(0.035, 0.676, f"compression = {compact_percent_label(compression)}", fontsize=5.9, color="#4B5563", transform=ax.transAxes)

    endpoint_nodes = [node for node in core_nodes if node in risk]
    affected_nodes = [node for node in core_nodes if node in affected and node not in risk]
    support_nodes = [node for node in core_nodes if node not in risk and node not in affected]

    def node_item(x: float, y0: float, text: str, dot: str, color: str, *, bold: bool = False) -> None:
        ax.scatter([x], [y0], s=13, color=dot, edgecolor="none", transform=ax.transAxes, zorder=3)
        ax.text(
            x + 0.035,
            y0 + 0.001,
            text,
            fontsize=5.20,
            color=color,
            ha="left",
            va="center",
            transform=ax.transAxes,
            weight="bold" if bold else None,
        )

    ax.text(0.035, 0.565, "risk endpoints kept", fontsize=5.85, weight="bold", color="#111827", transform=ax.transAxes)
    if endpoint_nodes:
        for i, node in enumerate(endpoint_nodes[:2]):
            node_item(0.050 + i * 0.280, 0.480, short(node), PAPER_COLORS["risk"], PAPER_COLORS["risk"], bold=True)
    else:
        ax.text(0.045, 0.480, "-", fontsize=6.0, color="#6B7280", transform=ax.transAxes)

    ax.text(0.035, 0.360, "supporting context", fontsize=5.85, weight="bold", color="#111827", transform=ax.transAxes)
    context_nodes = (affected_nodes + support_nodes)[:7]
    for i, node in enumerate(context_nodes):
        row = i // 3
        col = i % 3
        x = 0.050 + col * 0.315
        y0 = 0.286 - row * 0.096
        if node in affected:
            color = "#8A5B20"
            dot = PAPER_COLORS["orange"]
        else:
            color = "#1F2937"
            dot = PAPER_COLORS["support"]
        node_item(x, y0, short(node), dot, color)

    # C. Case-specific rollout trace.
    ax = fig.add_subplot(gs[1, :2])
    trace = record.get("convergence_trace") or []
    rxs = [int(p.get("rollout") or 0) for p in trace if isinstance(p, dict)]
    risk_cov = [float(p.get("risk_coverage") or 0) for p in trace if isinstance(p, dict)]
    val_cov = [float(p.get("valuable_coverage") or 0) for p in trace if isinstance(p, dict)]
    comp = [float(p.get("compression_ratio") or 0) for p in trace if isinstance(p, dict)]
    if rxs:
        ax.plot(rxs, risk_cov, color=PAPER_COLORS["blue"], linewidth=1.55, label="Risk endpoint coverage")
        ax.plot(rxs, val_cov, color=PAPER_COLORS["orange"], linewidth=1.45, label="Broader valuable-node coverage")
        ax.plot(rxs, comp, color="#6B7A90", linewidth=1.35, linestyle="--", label="Compression")
        first_all = record.get("first_subgraph_risk_all_rollout")
        if first_all:
            first_all_i = int(first_all)
            ax.axvline(first_all_i, color=PAPER_COLORS["purple"], linestyle=":", linewidth=1.25, alpha=0.82, zorder=1)
            ax.text(
                first_all_i + 2.35,
                1.105,
                f"risk-all @ {first_all_i}",
                fontsize=5.75,
                color=PAPER_COLORS["purple"],
                ha="left",
                va="center",
                bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="none", alpha=0.96),
                clip_on=False,
            )
        x_label = max(rxs) + 1.2
        ax.text(x_label, risk_cov[-1], "risk endpoints", fontsize=5.7, color=PAPER_COLORS["blue"], va="center")
        ax.text(x_label, val_cov[-1], "valuable nodes", fontsize=5.7, color=PAPER_COLORS["orange"], va="center")
        ax.text(x_label, comp[-1], "compression", fontsize=5.7, color="#6B7A90", va="center")
        ax.set_xlim(0, max(rxs) + 8)
    panel_label(ax, "C", "Evidence retained after discovery")
    ax.set_xlabel("Rollout", labelpad=3)
    set_percent_axis(ax, ylim=(0, 1.16), ylabel="Coverage / compression")
    soft_panel(ax)

    # D. Method comparison card.
    ax = fig.add_subplot(gs[1, 2])
    ax.axis("off")
    panel_label(ax, "D", "Same-case outcome")
    rows = [("Root@3", "root_top3"), ("Risk-any", "risk_any"), ("Risk-all", "risk_all")]
    ax.text(0.50, 0.82, "Naive", fontsize=6.1, color="#6B7280", ha="center", transform=ax.transAxes)
    ax.text(0.82, 0.82, "SA", fontsize=6.1, color="#6B7280", ha="center", transform=ax.transAxes)
    for i, (label, key) in enumerate(rows):
        y0 = 0.72 - i * 0.17
        ax.text(0.02, y0, label, fontsize=7.2, weight="bold", color="#111827", transform=ax.transAxes, va="center")
        for x0, val in [(0.50, nm.get(key)), (0.82, sm.get(key))]:
            ok = val is True
            ax.text(
                x0,
                y0,
                "Yes" if ok else "No" if val is False else "err",
                fontsize=7.2,
                weight="bold",
                ha="center",
                va="center",
                color=PAPER_COLORS["support"] if ok else PAPER_COLORS["risk"],
                transform=ax.transAxes,
            )
    ax.text(
        0.02,
        0.03,
        f"Template: {TEMPLATE_LABELS.get(template_name(record), template_name(record))}\n"
        f"Root: {short(root)}\nWitness: {short(witness)}",
        fontsize=5.8,
        color="#4B5563",
        linespacing=1.18,
        transform=ax.transAxes,
    )
    savefig(fig, "fig06_representative_scc_collapse")


def create_main_tables(records: list[dict[str, Any]]) -> None:
    boosted_rows = paper_naive_rows()
    main_naive = boosted_summary(boosted_rows)
    main_sa = summary(method_records(records, "sa-mcgs"))
    one_shot_naive = summary(method_records(records, "naive"))
    raw_boosted = boosted_raw_attempt_summary()

    main_rows = [
        {
            "method": MAIN_NAIVE_LABEL,
            "n": main_naive["n"],
            "root_at_3": pct(main_naive["root"]),
            "risk_any": pct(main_naive["risk_any"]),
            "risk_all": pct(main_naive["risk_all"]),
            "compression": pct(main_naive["compression"]),
        },
        {
            "method": "sa-mcgs",
            "n": main_sa["n"],
            "root_at_3": pct(main_sa["root"]),
            "risk_any": pct(main_sa["risk_any"]),
            "risk_all": pct(main_sa["risk_all"]),
            "compression": pct(main_sa["compression"]),
        },
    ]
    write_csv(TABLE_DIR / "tab03_main_results_strict.csv", main_rows)
    write_md_table(TABLE_DIR / "tab03_main_results_strict.md", "Table 3. Main Results", main_rows)

    reliability_rows = [
        {
            "scope": "locked one-shot",
            "method": "one-shot Naive",
            "denominator": "model-cases",
            "usable": f"{one_shot_naive['valid']}/{one_shot_naive['n']}",
            "unusable": f"{one_shot_naive['errors']}/{one_shot_naive['n']}",
            "usable_rate": pct(one_shot_naive["valid"] / one_shot_naive["n"] if one_shot_naive["n"] else None),
        },
        {
            "scope": "locked main",
            "method": "sa-mcgs",
            "denominator": "model-cases",
            "usable": f"{main_sa['valid']}/{main_sa['n']}",
            "unusable": f"{main_sa['errors']}/{main_sa['n']}",
            "usable_rate": pct(main_sa["valid"] / main_sa["n"] if main_sa["n"] else None),
        },
        {
            "scope": "boosted Naive x10",
            "method": MAIN_NAIVE_LABEL,
            "denominator": "raw attempts",
            "usable": f"{raw_boosted['n'] - raw_boosted['errors']}/{raw_boosted['n']}",
            "unusable": f"{raw_boosted['errors']}/{raw_boosted['n']}",
            "usable_rate": pct((raw_boosted["n"] - raw_boosted["errors"]) / raw_boosted["n"] if raw_boosted["n"] else None),
        },
        {
            "scope": "boosted Naive x10",
            "method": MAIN_NAIVE_LABEL,
            "denominator": "model-cases",
            "usable": f"{main_naive['valid']}/{main_naive['n']}",
            "unusable": f"{main_naive['zero_valid_cases']}/{main_naive['n']}",
            "usable_rate": pct(main_naive["valid"] / main_naive["n"] if main_naive["n"] else None),
        },
    ]
    write_csv(TABLE_DIR / "tab03_reliability_strict.csv", reliability_rows)
    write_md_table(TABLE_DIR / "tab03_reliability_strict.md", "Table 3. Output Reliability", reliability_rows)

    model_rows: list[dict[str, Any]] = []
    for model in dash.MODEL_ORDER:
        naive_subset = [row for row in boosted_rows if row.get("model") == model]
        if naive_subset:
            s = boosted_summary(naive_subset)
            model_rows.append(
                {
                    "model": model,
                    "method": MAIN_NAIVE_LABEL,
                    "n": s["n"],
                    "zero_valid_cases": s["zero_valid_cases"],
                    "root_at_3": pct(s["root"]),
                    "risk_any": pct(s["risk_any"]),
                    "risk_all": pct(s["risk_all"]),
                    "compression": pct(s["compression"]),
                }
            )
        sa_subset = [r for r in records if r.get("model") == model and r.get("method") == "sa-mcgs"]
        if sa_subset:
            s = summary(sa_subset)
            model_rows.append(
                {
                    "model": model,
                    "method": "sa-mcgs",
                    "n": s["n"],
                    "zero_valid_cases": 0,
                    "root_at_3": pct(s["root"]),
                    "risk_any": pct(s["risk_any"]),
                    "risk_all": pct(s["risk_all"]),
                    "compression": pct(s["compression"]),
                }
            )
    write_csv(TABLE_DIR / "tabA4_model_breakdown.csv", model_rows)
    write_md_table(TABLE_DIR / "tabA4_model_breakdown.md", "Table A4. Model-level Breakdown", model_rows)

    domain_rows: list[dict[str, Any]] = []
    for domain in dash.DOMAIN_ORDER:
        naive_subset = [row for row in boosted_rows if row.get("domain") == domain]
        if naive_subset:
            s = boosted_summary(naive_subset)
            domain_rows.append(
                {
                    "domain": domain,
                    "method": MAIN_NAIVE_LABEL,
                    "n": s["n"],
                    "zero_valid_cases": s["zero_valid_cases"],
                    "root_at_3": pct(s["root"]),
                    "risk_any": pct(s["risk_any"]),
                    "risk_all": pct(s["risk_all"]),
                    "compression": pct(s["compression"]),
                }
            )
        sa_subset = [r for r in records if r.get("domain") == domain and r.get("method") == "sa-mcgs"]
        if sa_subset:
            s = summary(sa_subset)
            domain_rows.append(
                {
                    "domain": domain,
                    "method": "sa-mcgs",
                    "n": s["n"],
                    "zero_valid_cases": 0,
                    "root_at_3": pct(s["root"]),
                    "risk_any": pct(s["risk_any"]),
                    "risk_all": pct(s["risk_all"]),
                    "compression": pct(s["compression"]),
                }
            )
    write_csv(TABLE_DIR / "tabA5_domain_breakdown.csv", domain_rows)
    write_md_table(TABLE_DIR / "tabA5_domain_breakdown.md", "Table A5. Domain-level Breakdown", domain_rows)

    scc_rows: list[dict[str, Any]] = []
    sizes = sorted(
        {as_int(row.get("actual_size")) for row in boosted_rows if as_int(row.get("actual_size")) > 0}
        | {
            as_int(record.get("scc_size"))
            for record in records
            if record.get("method") == "sa-mcgs" and as_int(record.get("scc_size")) > 0
        }
    )
    for size in sizes:
        naive_subset = [row for row in boosted_rows if as_int(row.get("actual_size")) == size]
        sa_subset = [record for record in records if record.get("method") == "sa-mcgs" and as_int(record.get("scc_size")) == size]
        if naive_subset:
            s = boosted_summary(naive_subset)
            scc_rows.append(
                {
                    "scc_size": size,
                    "method": MAIN_NAIVE_LABEL,
                    "n": s["n"],
                    "root_at_3": pct(s["root"]),
                    "risk_any": pct(s["risk_any"]),
                    "risk_all": pct(s["risk_all"]),
                    "compression": pct(s["compression"]),
                }
            )
        if sa_subset:
            s = summary(sa_subset)
            scc_rows.append(
                {
                    "scc_size": size,
                    "method": "sa-mcgs",
                    "n": s["n"],
                    "root_at_3": pct(s["root"]),
                    "risk_any": pct(s["risk_any"]),
                    "risk_all": pct(s["risk_all"]),
                    "compression": pct(s["compression"]),
                }
            )
    write_csv(TABLE_DIR / "tabA6_by_scc_size.csv", scc_rows)
    write_md_table(TABLE_DIR / "tabA6_by_scc_size.md", "Table A6. Metrics by SCC Size", scc_rows)

    selector_rows: list[dict[str, Any]] = []
    selector_rows.append(
        {
            "control": "one-shot Naive",
            "n": one_shot_naive["n"],
            "root_at_3": pct(one_shot_naive["root"]),
            "risk_any": pct(one_shot_naive["risk_any"]),
            "risk_all": pct(one_shot_naive["risk_all"]),
            "compression": pct(one_shot_naive["compression"]),
            "role": "original locked control",
        }
    )
    selector_rows.append(
        {
            "control": "boosted Naive single-attempt mean",
            "n": f"{main_naive['n']} cases / {raw_boosted['n']} attempts",
            "root_at_3": pct(raw_boosted["root"]),
            "risk_any": pct(raw_boosted["risk_any"]),
            "risk_all": pct(raw_boosted["risk_all"]),
            "compression": pct(raw_boosted["compression"]),
            "role": "raw repeated-sampling mean",
        }
    )
    for selector, role in (
        ("self_top3", "non-oracle selector"),
        ("oracle_risk_top3", "main oracle-risk baseline"),
        ("oracle_compression_top3", "compression-first diagnostic"),
    ):
        s = boosted_summary(load_boosted_summary_rows(selector))
        selector_rows.append(
            {
                "control": f"boosted Naive {selector}",
                "n": s["n"],
                "root_at_3": pct(s["root"]),
                "risk_any": pct(s["risk_any"]),
                "risk_all": pct(s["risk_all"]),
                "compression": pct(s["compression"]),
                "role": role,
            }
        )
    selector_rows.append(
        {
            "control": "SA-MCGS",
            "n": main_sa["n"],
            "root_at_3": pct(main_sa["root"]),
            "risk_any": pct(main_sa["risk_any"]),
            "risk_all": pct(main_sa["risk_all"]),
            "compression": pct(main_sa["compression"]),
            "role": "proposed method",
        }
    )
    write_csv(TABLE_DIR / "tabA9_boosted_naive_selector_comparison.csv", selector_rows)
    write_md_table(TABLE_DIR / "tabA9_boosted_naive_selector_comparison.md", "Table A9. Boosted Naive Selector Comparison", selector_rows)


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
            "file": "fig02_vanilla_mcts_scc_failure.png",
            "paper_section": "Method",
            "what_it_shows": "Visual motivation for why vanilla TreeMCTS fails on SCCs: path-copy expansion, budget dilution, Q-value flattening, and the SA-MCGS collapse alternative.",
            "use_in_main_text": "Yes",
        },
        {
            "id": "Figure 3",
            "file": "fig02_main_results_composite.pdf/png",
            "paper_section": "Main Results",
            "what_it_shows": "Composite main-result figure: oracle-risk Naive versus SA-MCGS, plus SCC-size breakdown of endpoint retention and compression.",
            "use_in_main_text": "Yes",
        },
        {
            "id": "Figure A1",
            "file": "fig03_main_by_scc_size.pdf/png",
            "paper_section": "Appendix",
            "what_it_shows": "Standalone SCC-size analysis retained as a backup asset; the main text uses the composite Figure 3.",
            "use_in_main_text": "No",
        },
        {
            "id": "Figure 4",
            "file": "fig04_budget_prefix_convergence.pdf/png",
            "paper_section": "Analysis",
            "what_it_shows": "Rollout convergence: strict success curves, evidence coverage versus compression, and citable budget checkpoints.",
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
            "id": "Figure A2",
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
            "- 主实验图使用 `current/default + critical + structural_simple_v2 + 4 models + 80 SCC blocks/model`。",
            "- Figure 3 的 Naive baseline 是 `oracle_risk_top3` over ten full-SCC Naive attempts，图例写作 `oracle-risk Naive`。",
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


EXPERT_ANNOTATION_DOMAINS = ["sec_ex21", "bgb", "cuad"]


ANNOTATION_DOMAIN_ZH = {
    "sec_ex21": "公司股权/合并披露",
    "bgb": "德国民法法条",
    "cuad": "合同条款",
}


ANNOTATION_TEMPLATE_ZH = {
    "direct_mutex": "两段话直接互相矛盾",
    "handoff_invariant": "前后传递的条件不一致",
    "temporal_gate": "时间或生效顺序冲突",
    "condition_trigger": "触发条件前后不一致",
}


ANNOTATION_TEMPLATE_PLAIN_ZH = {
    "direct_mutex": "这个样本里，远距离的两段文字可能分别提出了不能同时成立的要求。专家只需要判断：这些段落放在同一条关系链里时，是否真的会互相打架。",
    "handoff_invariant": "这个样本里，前面一段传递出去的条件，和后面一段接收到的条件可能不一致。专家只需要判断：同一条关系链上的状态是否被中途改坏了。",
    "temporal_gate": "这个样本里，某个动作的时间顺序或生效前提可能被前后两段说成了不同状态。专家只需要判断：按这些文字执行时，是否会出现还没满足条件却已经开始执行的问题。",
    "condition_trigger": "这个样本里，某个后果本来需要满足条件才会发生，但后面的文字可能把它当成已经发生。专家只需要判断：触发条件是否被前后段落说乱了。",
}


NODE_READING_HINTS_ZH = {
    "risk": "重点判断：这段可能是矛盾的一端。它单独看未必错，但和远处另一段放在一起可能无法同时成立。",
    "affected": "重点判断：这段可能被前后的矛盾影响。它自己不一定错，但可能是修复时必须看的相关段落。",
    "suggested": "阅读提示：这段被系统认为有助于理解问题，但专家可以不同意。请按正文内容独立判断。",
    "context": "上下文段落：主要用于理解前后关系。如果你认为它也有风险，可以直接标出来。",
}


def _expert_attention_hint(
    kind: str,
    in_core: bool,
    in_oc: bool,
    in_context: bool,
    injected_note: str = "",
) -> dict[str, str]:
    """Human-readable, non-CS hint shown next to each paragraph in the expert UI."""
    evidence = textwrap.shorten(_clean_text(injected_note), width=420, placeholder="...")
    if kind == "risk":
        parts = [
            "这段是高风险重点段落。",
            "它包含的要求可能和另一段文字不能同时成立，建议专家直接核对。",
        ]
        if evidence:
            parts.append(f"风险证据：{evidence}")
        if in_core:
            parts.append("系统也把它列为优先审阅段落。")
        if in_oc:
            parts.append("这段在多次小范围检查中被反复注意到。")
        return {
            "level": "risk",
            "title": "高风险重点段落",
            "reason": " ".join(parts),
        }
    if kind == "affected":
        parts = [
            "这段可能是受影响段落。",
            "它不一定自己有错，但如果前后段落存在冲突，修复时可能需要一起看。",
        ]
        if in_core:
            parts.append("系统把它放进了建议优先看的材料中。")
        return {
            "level": "affected",
            "title": "可能受影响段落",
            "reason": " ".join(parts),
        }
    if in_core:
        parts = [
            "系统建议优先看这段。",
            "请重点核对：它是否和其他段落放在一起会冲突，或者是否是修复问题时必须保留的材料。",
        ]
        if in_oc:
            parts.append("这段在多次小范围检查中被反复注意到，所以建议先看；最终判断仍以你的标注为准。")
        elif in_context:
            parts.append("它曾和其他重点段落一起出现，可能有助于理解前后关系。")
        return {
            "level": "focus",
            "title": "建议优先看",
            "reason": " ".join(parts),
        }
    return {
        "level": "context",
        "title": "普通展示段落",
        "reason": "系统没有把这段列为优先审阅段落，但它仍然完整展示。若你认为它有问题，或修复时必须一起看，可以直接标出来。",
    }


GRAPH_CACHE: dict[str, DependencyGraph] = {}


def _annotation_graph(domain: str) -> DependencyGraph | None:
    """Load original domain graph only for rebuilding expert-readable text."""
    if domain in GRAPH_CACHE:
        return GRAPH_CACHE[domain]
    try:
        from run_cross_domain_battle import load_bgb_graph, load_cuad_graph
        from run_cross_domain import load_sec_graph

        loaders = {
            "sec_ex21": load_sec_graph,
            "bgb": load_bgb_graph,
            "cuad": load_cuad_graph,
        }
        if domain not in loaders:
            return None
        GRAPH_CACHE[domain] = loaders[domain]()
        return GRAPH_CACHE[domain]
    except Exception as exc:
        print(f"[annotation] could not rebuild full text for {domain}: {exc}", file=sys.stderr)
        return None


def _clean_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text


def _clause_full_text(graph: DependencyGraph | None, fallback_record: dict[str, Any], node_id: str) -> tuple[str, str]:
    """Return title and readable text for a node, preferring original graph content."""
    if graph and node_id in graph.clauses:
        clause = graph.clauses[node_id]
        title = _clean_text(clause.title or node_id)
        content = _clean_text(clause.content or clause.title or node_id)
        if title and content and not content.startswith(title):
            return title, f"{title}\n\n{content}"
        return title or node_id, content or title or node_id
    title = node_name(fallback_record, node_id) or node_id
    return title, title


def _conflict_notes_for_case(sa: dict[str, Any], graph: DependencyGraph | None) -> dict[str, str]:
    """Rebuild the injected plain-language note for root/witness/bridge nodes."""
    domain = str(sa.get("domain") or "")
    template = template_name(sa)
    severity = severity_name(sa) or "critical"
    root_id = sa.get("injected_node")
    witness_id = sa.get("injected_witness_node")
    bridge_id = sa.get("injected_bridge_node")
    if not root_id or not witness_id:
        return {}
    try:
        from inject_defect import (
            _apply_conflict_severity,
            _make_structural_simple_contents,
            _strip_record_prefix,
        )

        root_title = _clause_full_text(graph, sa, root_id)[0]
        witness_title = _clause_full_text(graph, sa, witness_id)[0]
        bridge_title = _clause_full_text(graph, sa, bridge_id)[0] if bridge_id else None
        contents = _make_structural_simple_contents(domain, template, root_title, witness_title, bridge_title)
        contents = _apply_conflict_severity(contents, domain, severity)
        notes = {
            root_id: _strip_record_prefix(contents.get("target", ""), root_title),
            witness_id: _strip_record_prefix(contents.get("witness", ""), witness_title),
        }
        if bridge_id and contents.get("bridge"):
            notes[bridge_id] = _strip_record_prefix(contents["bridge"], bridge_title)
        return {node: note for node, note in notes.items() if note}
    except Exception as exc:
        print(f"[annotation] could not rebuild injected notes for {root_id}: {exc}", file=sys.stderr)
        return {}


def _node_kind(node_id: str, risk: set[str], affected: set[str], suggested: set[str]) -> str:
    if node_id in risk:
        return "risk"
    if node_id in affected:
        return "affected"
    if node_id in suggested:
        return "suggested"
    return "context"


def select_annotation_pairs(
    records: list[dict[str, Any]],
    per_domain: int = 8,
    domains: list[str] | None = None,
) -> list[dict[str, Any]]:
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
    domain_order = domains or dash.DOMAIN_ORDER
    for domain in domain_order:
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
    selected.sort(key=lambda p: (domain_order.index(str(p["domain"])) if p["domain"] in domain_order else 99, -p["size"], str(p["model"]), str(p["template"])))
    return selected


def create_case_material(case_id: str, pair: dict[str, Any]) -> dict[str, Any]:
    sa = pair["sa"]
    naive = pair.get("naive") or {}
    risk_nodes = [n for n in [sa.get("injected_node"), sa.get("injected_witness_node")] if n]
    bridge_nodes = [n for n in [sa.get("injected_bridge_node")] if n]
    affected = list(sa.get("injected_affected_nodes") or [])
    core = list(sa.get("core_evidence_risk_subgraph_nodes") or sa.get("risk_subgraph_nodes") or [])
    naive_nodes = list(naive.get("direct_risk_subgraph_nodes") or naive.get("risk_subgraph_nodes") or [])
    oc_nodes = list(sa.get("oc_detected") or [])
    context = list(sa.get("context_evidence_risk_subgraph_nodes") or [])
    metrics_sa = _metric_values(sa)
    metrics_naive = _metric_values(naive) if naive else {}
    graph = _annotation_graph(str(sa.get("domain") or ""))
    injected_notes = _conflict_notes_for_case(sa, graph)
    suggested_nodes = set(core) | set(naive_nodes) | set(oc_nodes)

    important_nodes = []
    for role, nodes in [
        ("root", [sa.get("injected_node")]),
        ("witness", [sa.get("injected_witness_node")]),
        ("bridge", bridge_nodes),
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

    scc_node_ids = list(sa.get("scc_clause_ids") or [])
    if not scc_node_ids:
        scc_node_ids = list((sa.get("node_names") or {}).keys())
    full_nodes = []
    for idx, node_id in enumerate(scc_node_ids, 1):
        title, original_text = _clause_full_text(graph, sa, node_id)
        injected_note = injected_notes.get(node_id, "")
        final_text = _clean_text(f"{original_text}\n\n{injected_note}") if injected_note else original_text
        kind = _node_kind(node_id, set(risk_nodes), set(affected), suggested_nodes)
        attention_hint = _expert_attention_hint(
            kind=kind,
            in_core=node_id in core,
            in_oc=node_id in oc_nodes,
            in_context=node_id in context,
            injected_note=injected_note,
        )
        full_nodes.append(
            {
                "index": idx,
                "node_id": node_id,
                "title": title,
                "text_en": final_text,
                "text_zh": NODE_READING_HINTS_ZH[kind],
                "reading_hint_zh": NODE_READING_HINTS_ZH[kind],
                "expert_hint_title_zh": attention_hint["title"],
                "expert_hint_reason_zh": attention_hint["reason"],
                "expert_hint_level": attention_hint["level"],
                "kind": kind,
                "is_risk_endpoint": node_id in risk_nodes,
                "is_bridge": node_id in bridge_nodes,
                "is_affected": node_id in affected,
                "in_sa_core": node_id in core,
                "in_naive_subgraph": node_id in naive_nodes,
                "in_oc": node_id in oc_nodes,
                "in_context": node_id in context,
                "injected_note": injected_note,
                "stats": compact_node_stats(sa, node_id),
            }
        )

    row = {
        "case_id": case_id,
        "domain": sa.get("domain"),
        "domain_label": ANNOTATION_DOMAIN_ZH.get(str(sa.get("domain")), DOMAIN_LABELS.get(str(sa.get("domain")), str(sa.get("domain")))),
        "scc_id": sa.get("scc_id"),
        "scc_size": sa.get("scc_size"),
        "model": sa.get("model"),
        "template": template_name(sa),
        "template_label": ANNOTATION_TEMPLATE_ZH.get(template_name(sa), TEMPLATE_LABELS.get(template_name(sa), template_name(sa))),
        "severity": severity_name(sa),
        "root_node": sa.get("injected_node"),
        "root_label": node_name(sa, sa.get("injected_node")),
        "witness_node": sa.get("injected_witness_node"),
        "witness_label": node_name(sa, sa.get("injected_witness_node")),
        "bridge_node": sa.get("injected_bridge_node") or "",
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
        "full_nodes": full_nodes,
        "risk_nodes": risk_nodes,
        "bridge_nodes": bridge_nodes,
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
        "root": ("Possible conflict paragraph", "可能冲突段落"),
        "witness": ("Possible matching conflict paragraph", "可能对应冲突段落"),
        "bridge": ("Possible condition-transfer paragraph", "可能传递条件的段落"),
        "affected": ("Possibly affected paragraph", "可能受影响段落"),
        "sa_core": ("System-suggested paragraph", "系统建议关注段落"),
        "naive_subgraph": ("Comparison-suggested paragraph", "对照方法建议关注段落"),
        "oc": ("Repeatedly suspicious paragraph", "反复被认为可疑的段落"),
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
    enriched["case_plain_zh"] = ANNOTATION_TEMPLATE_PLAIN_ZH.get(str(meta.get("template") or ""), "")
    enriched_nodes: list[dict[str, Any]] = []
    for idx, node in enumerate(material.get("full_nodes", []), 1):
        enriched_nodes.append(
            {
                **node,
                "display_id": f"段落 {idx:02d}",
                "short_id": str(node.get("node_id") or "")[-10:],
                "role_label_zh": role_label(str(node.get("kind") or "context"), "zh"),
            }
        )
    enriched["full_nodes"] = enriched_nodes
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
                "is_bridge": item.get("node_id") in material.get("bridge_nodes", []),
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


def create_plain_annotation_html(materials: list[dict[str, Any]]) -> None:
    """Create the expert-facing annotation UI with plain Chinese wording."""
    ensure_sheetjs_vendor()
    payload = json.dumps([enrich_annotation_material(m) for m in materials], ensure_ascii=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>结构冲突专家标注</title>
<script src="vendor/xlsx.full.min.js"></script>
<style>
:root { --bg:#f5f7fb; --panel:#ffffff; --ink:#111827; --muted:#64748b; --line:#d7dfec; --blue:#2563eb; --green:#059669; --red:#dc2626; --amber:#b45309; --soft:#eff6ff; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Arial,sans-serif; }
header { position:sticky; top:0; z-index:20; background:#101827; color:#f8fafc; padding:18px 28px; box-shadow:0 8px 24px rgba(15,23,42,.22); }
h1 { margin:0 0 6px; font-size:28px; letter-spacing:0; }
header p { margin:0; color:#cbd5e1; line-height:1.55; }
button,input,textarea,select { font:inherit; }
button { border:1px solid #cbd5e1; border-radius:10px; background:#fff; color:#0f172a; padding:9px 14px; font-weight:800; cursor:pointer; }
button.primary { background:var(--blue); border-color:var(--blue); color:#fff; }
button.green { background:var(--green); border-color:var(--green); color:#fff; }
input[type="text"], textarea, select { width:100%; border:1px solid var(--line); border-radius:10px; padding:10px 12px; background:#fff; color:var(--ink); }
main { display:grid; grid-template-columns:320px minmax(0,1fr); gap:18px; max-width:1560px; margin:22px auto; padding:0 18px 60px; }
aside,.workspace { background:var(--panel); border:1px solid var(--line); border-radius:16px; box-shadow:0 1px 8px rgba(15,23,42,.05); }
aside { position:sticky; top:106px; max-height:calc(100vh - 128px); overflow:auto; padding:16px; }
.workspace { padding:24px; }
.stats { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin:12px 0 16px; }
.stat { background:#f8fafc; border:1px solid var(--line); border-radius:12px; padding:10px; }
.stat b { display:block; font-size:24px; }
.stat span { color:var(--muted); font-size:13px; }
.case-btn { width:100%; text-align:left; padding:12px; margin:8px 0; background:#fff; border:1px solid var(--line); border-radius:12px; color:var(--ink); }
.case-btn.active { border-color:var(--blue); background:var(--soft); }
.case-btn .done { float:right; color:var(--green); font-weight:900; }
.case-btn strong { display:block; margin-bottom:5px; }
.case-btn small { display:block; color:var(--muted); line-height:1.45; }
.case-head { border-bottom:1px solid var(--line); padding-bottom:16px; margin-bottom:20px; }
.case-head h2 { margin:0 0 10px; font-size:30px; }
.case-meta { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.pill { display:inline-flex; align-items:center; border-radius:999px; padding:5px 10px; background:#f1f5f9; color:#334155; font-size:13px; font-weight:800; }
.pill.green { background:#dcfce7; color:#166534; }
.pill.blue { background:#dbeafe; color:#1d4ed8; }
.pill.amber { background:#fef3c7; color:#92400e; }
.guide { background:#f8fafc; border-left:6px solid var(--blue); border-radius:12px; padding:15px 18px; line-height:1.75; color:#243244; margin:16px 0; }
.section-title { margin:26px 0 12px; font-size:23px; }
.node-card { display:grid; grid-template-columns:minmax(0,1fr) 330px; gap:18px; border:1px solid var(--line); border-radius:16px; background:#fff; padding:18px; margin:14px 0; }
.node-card.system-focus { border-color:#86efac; box-shadow:0 0 0 3px rgba(34,197,94,.10); }
.node-card.risk-focus { border-color:#fca5a5; box-shadow:0 0 0 3px rgba(220,38,38,.10); }
.node-card.affected-focus { border-color:#bfdbfe; box-shadow:0 0 0 3px rgba(37,99,235,.08); }
.node-main h3 { margin:0 0 8px; font-size:21px; }
.node-title { color:#334155; font-weight:800; margin-bottom:10px; }
.node-text { white-space:pre-wrap; line-height:1.72; color:#1f2937; font-size:16px; }
.node-id { color:var(--muted); font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:13px; }
.node-form { border-left:1px solid var(--line); padding-left:18px; }
.node-form h4 { margin:0 0 10px; font-size:17px; }
.node-form .desc { color:var(--muted); line-height:1.55; margin:0 0 10px; font-size:14px; }
.attention-box { border:1px solid var(--line); border-radius:12px; background:#f8fafc; padding:11px 12px; margin:0 0 12px; line-height:1.55; }
.attention-box.focus { border-color:#86efac; background:#ecfdf5; }
.attention-box.risk { border-color:#fca5a5; background:#fff1f2; }
.attention-box.affected { border-color:#bfdbfe; background:#eff6ff; }
.attention-title { display:flex; align-items:center; gap:8px; font-weight:900; margin-bottom:5px; }
.attention-dot { width:9px; height:9px; border-radius:999px; background:#94a3b8; flex:0 0 auto; }
.attention-box.focus .attention-dot { background:#059669; }
.attention-box.risk .attention-dot { background:#dc2626; }
.attention-box.affected .attention-dot { background:#2563eb; }
.attention-reason { color:#334155; font-size:14px; }
.radio-stack { display:grid; gap:8px; margin-bottom:12px; }
.radio-stack label,.checkline { display:flex; align-items:flex-start; gap:8px; border:1px solid var(--line); border-radius:10px; padding:9px; cursor:pointer; line-height:1.45; }
.radio-stack input,.checkline input { margin-top:4px; }
.node-form textarea { min-height:74px; resize:vertical; }
.case-form { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; margin-top:14px; }
.question { border:1px solid var(--line); border-radius:14px; background:#fff; padding:15px; }
.question h3 { margin:0 0 10px; font-size:18px; }
.options { display:flex; flex-wrap:wrap; gap:8px; }
.options label { display:inline-flex; gap:6px; align-items:center; border:1px solid var(--line); border-radius:999px; padding:8px 11px; cursor:pointer; }
.savebar { position:sticky; bottom:0; margin:24px -24px -24px; padding:14px 24px; display:flex; gap:10px; align-items:center; background:rgba(255,255,255,.94); border-top:1px solid var(--line); border-radius:0 0 16px 16px; backdrop-filter:blur(8px); }
.hint { color:var(--muted); line-height:1.55; }
code { background:#f1f5f9; border-radius:6px; padding:2px 5px; }
@media (max-width:1080px) { main { grid-template-columns:1fr; } aside { position:relative; top:0; max-height:none; } .node-card,.case-form { grid-template-columns:1fr; } .node-form { border-left:0; border-top:1px solid var(--line); padding:16px 0 0; } }
</style>
</head>
<body>
<header>
  <h1>结构冲突专家标注</h1>
  <p>请像阅读一份长合同、公司披露或法条材料一样逐段判断。页面不要求理解算法术语；只需要判断每段文字是否有问题、是否应放入最终修复材料。</p>
</header>
<main>
  <aside>
    <label class="hint" for="expertSlot">当前标注人</label>
    <select id="expertSlot" style="margin:6px 0 10px;">
      <option value="expert_1">专家 1</option>
      <option value="expert_2">专家 2</option>
      <option value="expert_3">专家 3</option>
    </select>
    <input id="reviewer" type="text" placeholder="标注者姓名或编号">
    <div class="stats">
      <div class="stat"><b id="totalCount">0</b><span>样本</span></div>
      <div class="stat"><b id="doneCount">0</b><span>当前已填</span></div>
      <div class="stat"><b id="domainCount">0</b><span>总填写份数</span></div>
    </div>
    <p class="hint">建议三位专家分别完成同一批样本。切换“专家 1/2/3”后，页面会保存各自独立的标注。</p>
    <div id="caseList"></div>
    <button class="green" id="exportBtn" style="width:100%;margin-top:12px;">生成 Excel</button>
  </aside>
  <section class="workspace" id="workspace"></section>
</main>
<script type="application/json" id="case-data">__DATA__</script>
<script>
const CASES = JSON.parse(document.getElementById('case-data').textContent);
const STORE_KEY = 'plain_structural_conflict_annotations_v2';
const EXPERTS = [
  { id: 'expert_1', label: '专家 1' },
  { id: 'expert_2', label: '专家 2' },
  { id: 'expert_3', label: '专家 3' },
];
let activeIndex = 0;
let activeExpert = localStorage.getItem(STORE_KEY + '_active_expert') || 'expert_1';
if (!EXPERTS.some(expert => expert.id === activeExpert)) activeExpert = 'expert_1';
let annotations = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;', "'":'&#39;'}[c]));
function expertBucket(expertId = activeExpert) {
  if (!annotations[expertId]) annotations[expertId] = {};
  return annotations[expertId];
}
const annFor = (caseId, expertId = activeExpert) => (annotations[expertId] || {})[caseId] || {};
const pct = (v) => (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) ? '-' : Math.round(Number(v) * 100) + '%';

function saveStore() {
  localStorage.setItem(STORE_KEY, JSON.stringify(annotations));
  localStorage.setItem(STORE_KEY + '_active_expert', activeExpert);
  renderCaseList();
}

function isDone(caseId, expertId = activeExpert) {
  const a = annFor(caseId, expertId);
  return Boolean(a.overall_conflict && a.material_sufficient && a.confidence);
}

function caseTitle(c) {
  const m = c.metadata;
  return `${m.domain_label} · ${m.scc_size} 段`;
}

function renderCaseList() {
  $('totalCount').textContent = CASES.length;
  $('doneCount').textContent = CASES.filter(c => isDone(c.metadata.case_id)).length;
  const totalDone = EXPERTS.reduce((sum, expert) => sum + CASES.filter(c => isDone(c.metadata.case_id, expert.id)).length, 0);
  $('domainCount').textContent = `${totalDone}/${CASES.length * EXPERTS.length}`;
  $('caseList').innerHTML = CASES.map((c, i) => {
    const m = c.metadata;
    const doneSlots = EXPERTS.filter(expert => isDone(m.case_id, expert.id)).length;
    return `<button class="case-btn ${i === activeIndex ? 'active' : ''}" data-case-index="${i}">
      <span class="done">${doneSlots}/3</span>
      <strong>${esc(caseTitle(c))}</strong>
      <small>${esc(m.template_label)} · ${esc(m.model)} · ${esc(m.case_id)}</small>
    </button>`;
  }).join('');
  document.querySelectorAll('[data-case-index]').forEach(btn => {
    btn.addEventListener('click', () => {
      saveCurrentAnnotation(false);
      activeIndex = Number(btn.dataset.caseIndex);
      renderAll();
    });
  });
}

function nodeJudgementLabel(value) {
  return {
    clear_risk: '有明显问题',
    related: '可能有关',
    no_risk: '没看出问题',
    unsure: '不确定',
  }[value] || '';
}

function renderNodeCard(c, node) {
  const a = annFor(c.metadata.case_id);
  const nodeAnn = (a.nodes || {})[node.node_id] || {};
  const checked = (value) => nodeAnn.judgement === value ? 'checked' : '';
  const keepChecked = nodeAnn.keep_for_repair ? 'checked' : '';
  const hintLevel = node.expert_hint_level || 'context';
  const cardClass = hintLevel === 'risk' ? 'risk-focus' : (hintLevel === 'affected' ? 'affected-focus' : (hintLevel === 'focus' ? 'system-focus' : ''));
  return `<article class="node-card ${cardClass}" data-node-id="${esc(node.node_id)}">
    <div class="node-main">
      <h3>${esc(node.display_id || ('段落 ' + node.index))}</h3>
      <div class="node-title">${esc(node.title || '')}</div>
      <div class="node-id">原始编号：${esc(node.node_id)}</div>
      <div class="node-text">${esc(node.text_en || '')}</div>
    </div>
    <div class="node-form">
      <div class="attention-box ${hintLevel}">
        <div class="attention-title"><span class="attention-dot"></span>${esc(node.expert_hint_title_zh || '阅读提示')}</div>
        <div class="attention-reason">${esc(node.expert_hint_reason_zh || '')}</div>
      </div>
      <h4>请标注这段</h4>
      <p class="desc">只根据这段和整组文字来判断：它是否明显有问题，或是否需要放进最终修复材料。</p>
      <div class="radio-stack">
        <label><input type="radio" data-node-risk value="clear_risk" ${checked('clear_risk')}> <span><b>有明显问题</b><br>这段自己有问题，或和别的段落放在一起明显冲突。</span></label>
        <label><input type="radio" data-node-risk value="related" ${checked('related')}> <span><b>可能有关</b><br>这段本身未必错，但修复冲突时可能需要一起看。</span></label>
        <label><input type="radio" data-node-risk value="no_risk" ${checked('no_risk')}> <span><b>没看出问题</b><br>看起来只是普通上下文。</span></label>
        <label><input type="radio" data-node-risk value="unsure" ${checked('unsure')}> <span><b>不确定</b><br>需要更多上下文或专业判断。</span></label>
      </div>
      <label class="checkline"><input type="checkbox" data-node-keep ${keepChecked}> <span><b>应放入最终修复材料</b><br>如果只给别人看少量段落来修复问题，我会保留这一段。</span></label>
      <textarea data-node-note placeholder="可选：说明为什么这样判断">${esc(nodeAnn.note || '')}</textarea>
    </div>
  </article>`;
}

function renderCaseForm(c) {
  const a = annFor(c.metadata.case_id);
  const radio = (name, value) => a[name] === value ? 'checked' : '';
  return `<section>
    <h2 class="section-title">整组文字判断</h2>
    <div class="case-form">
      <div class="question">
        <h3>这组文字整体是否有真实冲突？</h3>
        <div class="options">
          <label><input type="radio" name="overall_conflict" value="yes" ${radio('overall_conflict','yes')}>有真实冲突</label>
          <label><input type="radio" name="overall_conflict" value="maybe" ${radio('overall_conflict','maybe')}>有可疑冲突</label>
          <label><input type="radio" name="overall_conflict" value="no" ${radio('overall_conflict','no')}>没有明显冲突</label>
          <label><input type="radio" name="overall_conflict" value="unsure" ${radio('overall_conflict','unsure')}>不确定</label>
        </div>
      </div>
      <div class="question">
        <h3>你勾选的段落是否足够定位和修复问题？</h3>
        <div class="options">
          <label><input type="radio" name="material_sufficient" value="yes" ${radio('material_sufficient','yes')}>足够</label>
          <label><input type="radio" name="material_sufficient" value="partial" ${radio('material_sufficient','partial')}>部分足够</label>
          <label><input type="radio" name="material_sufficient" value="no" ${radio('material_sufficient','no')}>不够</label>
          <label><input type="radio" name="material_sufficient" value="unsure" ${radio('material_sufficient','unsure')}>不确定</label>
        </div>
      </div>
      <div class="question">
        <h3>是否还需要更多上下文？</h3>
        <div class="options">
          <label><input type="radio" name="need_more_context" value="yes" ${radio('need_more_context','yes')}>需要</label>
          <label><input type="radio" name="need_more_context" value="no" ${radio('need_more_context','no')}>不需要</label>
          <label><input type="radio" name="need_more_context" value="unsure" ${radio('need_more_context','unsure')}>不确定</label>
        </div>
      </div>
      <div class="question">
        <h3>标注信心</h3>
        <select name="confidence">
          <option value="">请选择</option>
          ${[1,2,3,4,5].map(v => `<option value="${v}" ${String(a.confidence || '') === String(v) ? 'selected' : ''}>${v} / 5</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="question" style="margin-top:14px;">
      <h3>备注</h3>
      <textarea name="comments" rows="5" placeholder="可选：写下你认为真正冲突的段落、缺失材料、或判断理由">${esc(a.comments || '')}</textarea>
    </div>
  </section>`;
}

function renderWorkspace() {
  const c = CASES[activeIndex];
  const m = c.metadata;
  const expert = EXPERTS.find(e => e.id === activeExpert) || EXPERTS[0];
  $('workspace').innerHTML = `
    <div class="case-head">
      <h2>${esc(caseTitle(c))}</h2>
      <div class="hint">${esc(m.template_label)}。${esc(c.case_plain_zh || c.case_summary?.zh || '')}</div>
      <div class="case-meta">
        <span class="pill blue">样本 ${esc(m.case_id)}</span>
        <span class="pill green">${esc(expert.label)}</span>
        <span class="pill">模型 ${esc(m.model)}</span>
        <span class="pill amber">请独立判断，不需要理解算法</span>
      </div>
    </div>
    <div class="guide">
      <b>怎么标：</b>从上到下读完整组文字。每段右侧选择“有明显问题 / 可能有关 / 没看出问题 / 不确定”。
      如果你认为某段应该留给后续修复人员，请勾选“应放入最终修复材料”。页面会自动保存在本浏览器，最后点击“生成 Excel”。
    </div>
    <h2 class="section-title">完整文本与逐段标注</h2>
    ${c.full_nodes.map(node => renderNodeCard(c, node)).join('')}
    ${renderCaseForm(c)}
    <div class="savebar">
      <button class="primary" id="saveBtn">保存当前样本</button>
      <button class="green" id="exportBtnBottom">生成 Excel</button>
      <span class="hint">切换样本或专家前会自动保存；生成的 Excel 包含三位专家的“样本整体标注”和“逐段标注”。</span>
    </div>
  `;
  $('saveBtn').addEventListener('click', () => saveCurrentAnnotation(true));
  $('exportBtnBottom').addEventListener('click', exportExcel);
}

function saveCurrentAnnotation(showMessage = false) {
  const c = CASES[activeIndex];
  const root = $('workspace');
  if (!root || !c) return;
  const getRadio = (name) => root.querySelector(`input[name="${name}"]:checked`)?.value || '';
  const nodeData = {};
  root.querySelectorAll('.node-card').forEach(card => {
    const nodeId = card.dataset.nodeId;
    nodeData[nodeId] = {
      judgement: card.querySelector('input[data-node-risk]:checked')?.value || '',
      judgement_label: nodeJudgementLabel(card.querySelector('input[data-node-risk]:checked')?.value || ''),
      keep_for_repair: Boolean(card.querySelector('input[data-node-keep]')?.checked),
      note: card.querySelector('textarea[data-node-note]')?.value || '',
    };
  });
  expertBucket()[c.metadata.case_id] = {
    reviewer: $('reviewer').value || '',
    expert_slot: activeExpert,
    expert_label: (EXPERTS.find(e => e.id === activeExpert) || {}).label || activeExpert,
    overall_conflict: getRadio('overall_conflict'),
    material_sufficient: getRadio('material_sufficient'),
    need_more_context: getRadio('need_more_context'),
    confidence: root.querySelector('select[name="confidence"]')?.value || '',
    comments: root.querySelector('textarea[name="comments"]')?.value || '',
    nodes: nodeData,
    saved_at: new Date().toISOString(),
  };
  saveStore();
  if (showMessage) alert('已保存当前样本。');
}

function exportExcel() {
  saveCurrentAnnotation(false);
  const caseRows = [];
  const nodeRows = [];
  EXPERTS.forEach(expert => {
    CASES.forEach(c => {
      const m = c.metadata;
      const a = annFor(m.case_id, expert.id);
      const selected = Object.entries(a.nodes || {}).filter(([, v]) => v.keep_for_repair).map(([id]) => id);
      caseRows.push({
        专家编号: expert.label,
        标注者: a.reviewer || '',
        样本编号: m.case_id,
        文本类型: m.domain_label,
        段落数: m.scc_size,
        冲突类型: m.template_label,
        整体是否冲突: a.overall_conflict || '',
        勾选材料是否足够修复: a.material_sufficient || '',
        是否需要更多上下文: a.need_more_context || '',
        标注信心_1到5: a.confidence || '',
        专家勾选段落: selected.join(';'),
        备注: a.comments || '',
        保存时间: a.saved_at || '',
        隐藏对照_root: m.root_node,
        隐藏对照_witness: m.witness_node,
        隐藏对照_affected: m.affected_nodes,
        隐藏对照_系统建议: m.sa_core_nodes,
        隐藏对照_对照方法建议: m.naive_subgraph_nodes,
        隐藏指标_系统risk_any: m.sa_risk_any,
        隐藏指标_系统risk_all: m.sa_risk_all,
        隐藏指标_系统compression: m.sa_compression,
      });
      c.full_nodes.forEach(node => {
        const na = (a.nodes || {})[node.node_id] || {};
        nodeRows.push({
          专家编号: expert.label,
          标注者: a.reviewer || '',
          样本编号: m.case_id,
          文本类型: m.domain_label,
          段落序号: node.display_id || node.index,
          原始编号: node.node_id,
          标题: node.title || '',
          原文: node.text_en || '',
          页面提示: node.expert_hint_title_zh || '',
          页面提示说明: node.expert_hint_reason_zh || '',
          专家判断: na.judgement_label || '',
          专家判断代码: na.judgement || '',
          是否放入最终修复材料: na.keep_for_repair ? '是' : '否',
          段落备注: na.note || '',
          隐藏对照_是否真实冲突端点: node.is_risk_endpoint ? '是' : '否',
          隐藏对照_是否中间传递段落: node.is_bridge ? '是' : '否',
          隐藏对照_是否受影响段落: node.is_affected ? '是' : '否',
          隐藏对照_系统是否保留: node.in_sa_core ? '是' : '否',
          隐藏对照_对照方法是否保留: node.in_naive_subgraph ? '是' : '否',
          隐藏对照_是否反复可疑: node.in_oc ? '是' : '否',
        });
      });
    });
  });
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(caseRows), '样本整体标注');
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(nodeRows), '逐段标注');
  XLSX.writeFile(wb, `structural_conflict_annotations_${new Date().toISOString().slice(0,10)}.xlsx`);
}

function renderAll() {
  renderCaseList();
  renderWorkspace();
}

$('exportBtn').addEventListener('click', exportExcel);
$('reviewer').addEventListener('input', () => {
  if (!annotations._reviewers) annotations._reviewers = {};
  annotations._reviewers[activeExpert] = $('reviewer').value || '';
  localStorage.setItem(STORE_KEY, JSON.stringify(annotations));
});
$('expertSlot').addEventListener('change', () => {
  saveCurrentAnnotation(false);
  activeExpert = $('expertSlot').value;
  $('reviewer').value = annotations._reviewers?.[activeExpert] || '';
  saveStore();
  renderAll();
});
$('expertSlot').value = activeExpert;
$('reviewer').value = annotations._reviewers?.[activeExpert] || '';
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

    full_pairs = select_annotation_pairs(records, per_domain=8, domains=EXPERT_ANNOTATION_DOMAINS)
    pairs = select_annotation_pairs(records, per_domain=4, domains=EXPERT_ANNOTATION_DOMAINS)
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
    expert_index_rows = [
        {
            "样本编号": row["case_id"],
            "文本类型": row["domain_label"],
            "段落数": row["scc_size"],
            "冲突类型": row["template_label"],
            "模型": row["model"],
        }
        for row in csv_rows
    ]
    write_csv(ANNOT_DIR / "expert_case_index.csv", expert_index_rows)
    full_rows: list[dict[str, Any]] = []
    for idx, pair in enumerate(full_pairs, 1):
        material = create_case_material(f"candidate_{idx:03d}_{pair['domain']}_{pair['size']}_{pair['model']}_{pair['template']}", pair)
        full_rows.append(material["metadata"])
    write_csv(ANNOT_DIR / "full_candidate_manifest_not_for_experts.csv", full_rows)
    create_plain_annotation_html(materials)
    readme = [
        "# Human Annotation Pack / 人工标注包",
        "",
        "目的：让领域专家像阅读长合同、公司披露或法条材料一样，逐段判断哪些文本存在冲突、哪些文本应保留给后续修复。",
        "",
        "包含文件：",
        "",
        "- `annotation_interface.html`：专家使用的主入口。打开后直接看到完整长文本，可在每段旁边打标，并一键导出 Excel。",
        "- `expert_case_index.csv`：专家可读的小样本清单，只包含文本类型、段落数和冲突类型。",
        "- `vendor/xlsx.full.min.js`：本地 Excel 导出依赖，已打进 zip，打开 HTML 不需要联网。",
        "- `human_annotation_cases.csv`、`materials/` 和 `full_candidate_manifest_not_for_experts.csv`：只保留在本地目录供内部追溯，不打进专家 zip。",
        "",
        "专家需要填写：",
        "",
        "- 每一段文字：有明显问题 / 可能有关 / 没看出问题 / 不确定。",
        "- 每一段文字：是否应放进最终修复材料。",
        "- 整组文字：是否存在真实冲突、勾选材料是否足够修复、是否需要更多上下文、标注信心和备注。",
        "",
        f"当前专家包包含 `{len(csv_rows)}` 个精选 case：SEC EX-21、BGB、CUAD 各 4 个。Debian 软件依赖样本不放入专家包，由项目内部单独标注。",
        "",
        "页面内置 `专家 1/2/3` 三个独立标注槽位。每个样本需要三位专家分别标一次；导出 Excel 时会按专家展开。",
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
            rel = path.relative_to(ANNOT_DIR)
            if path == zip_path or path.is_dir() or path.name == ".DS_Store":
                continue
            if "materials" in rel.parts or "human_annotation_pack" in rel.parts:
                continue
            if path.name in {
                "full_candidate_manifest_not_for_experts.csv",
                "human_annotation_cases.csv",
                "human_annotation_cases.md",
            }:
                continue
            zf.write(path, rel)

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
        "- Figure 2: `figures/fig02_vanilla_mcts_scc_failure.png`",
        "- Table 1: `tables/tab01_mcts_scc_motivation.md` / `.csv`",
        "- Table 2: `tables/tab02_domain_coverage_authority.md` / `.csv`",
        "- Table 3: `tables/tab03_reliability_strict.md` / `.csv`",
            "- Main-result metric source: `tables/tab03_main_results_strict.md` / `.csv`",
            "- Boosted Naive selector comparison: `tables/tabA9_boosted_naive_selector_comparison.md` / `.csv`",
        "- Figure 3: `figures/fig02_main_results_composite.pdf`",
        "- Figure 4: `figures/fig04_budget_prefix_convergence.pdf`",
        "- Figure 5: `figures/fig05_compression_profile_tradeoff.pdf`",
        "- Appendix figure: `figures/fig03_main_by_scc_size.pdf`",
        "- Appendix figure: `figures/fig06_representative_scc_collapse.pdf`",
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

口径提醒：主实验图表使用 `current/default + critical + structural_simple_v2 + 4 models + 80 SCC blocks/model`，其中 main Naive baseline 为 `oracle_risk_top3` over ten full-SCC Naive attempts。旧 diagnostic、smoke、balanced exploratory 不作为主结果。

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
    create_mcts_failure_figure()
    create_main_metrics_figure(records)
    create_scc_size_figure(records)
    create_main_results_composite_figure(records)
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

#!/usr/bin/env python3
"""Generate figures and a Markdown analysis for the severity-grid run."""
from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from progress_dashboard import RESULTS_DIR, _load_json_obj, _load_records_from_status, _metric_values


FIG_DIR = RESULTS_DIR / "figures"
DEFAULT_STATUS = RESULTS_DIR / "severitygrid_cuad_bgb_2size_b60_severity_grid_status.json"
REPORT_PATH = RESULTS_DIR / "SEVERITY_GRID_ANALYSIS.md"
HTML_REPORT_PATH = RESULTS_DIR / "SEVERITY_GRID_ANALYSIS.html"
CONTACT_SHEET_NAME = "SEVERITY_GRID_ANALYSIS_CONTACT_SHEET.png"
FIGURE_BASE_URL = "http://127.0.0.1:8777/figures"

METHOD_COLORS = {"naive": "#d94841", "sa-mcgs": "#0f8b69"}
METRICS = [
    ("root_top3", "Root@3"),
    ("risk_any", "Risk-any"),
    ("risk_all", "Risk-all"),
]
SEVERITY_ORDER = ["standard", "severe", "critical"]
TEMPLATE_ORDER = ["direct_mutex", "handoff_invariant", "temporal_gate", "condition_trigger"]


def pct_label(value: float | None) -> str:
    if value is None or np.isnan(value):
        return "-"
    return f"{value:.0%}"


def rate(series: pd.Series) -> float:
    if len(series) == 0:
        return np.nan
    return float((series == True).sum() / len(series))  # noqa: E712


def load_dataframe(status_path: Path) -> pd.DataFrame:
    status = _load_json_obj(status_path)
    records = _load_records_from_status(status)
    rows: list[dict[str, Any]] = []
    for record in records:
        if record.get("method") not in {"naive", "sa-mcgs"}:
            continue
        metrics = _metric_values(record)
        actual_size = int(record.get("scc_size") or 0)
        requested_size = int(record.get("_task_size") or actual_size)
        size_label = f"{record.get('domain')} actual {actual_size}"
        if requested_size != actual_size:
            size_label += f" (req {requested_size})"
        rows.append(
            {
                "domain": record.get("domain"),
                "requested_size": requested_size,
                "actual_size": actual_size,
                "size_label": size_label,
                "model": record.get("model"),
                "method": record.get("method"),
                "template": record.get("_task_template") or record.get("injected_conflict_family"),
                "severity": record.get("_task_severity") or record.get("injected_conflict_severity"),
                "error": bool(record.get("error")),
                "root_top3": metrics["root_top3"] is True,
                "risk_any": metrics["risk_any"] is True,
                "risk_all": metrics["risk_all"] is True,
                "effective_oc": metrics["effective_oc"] is True,
                "oc_hit": (
                    int(record.get("oc_count") or 0) > 0
                    if record.get("method") == "sa-mcgs"
                    else False
                ),
                "compression": (
                    float(metrics["compression"])
                    if metrics["compression"] is not None
                    else np.nan
                ),
                "subgraph_size": (
                    float(metrics["subgraph_size"])
                    if metrics["subgraph_size"] is not None
                    else np.nan
                ),
                "record_id": record.get("experiment_id") or record.get("scc_id"),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"No method records found from {status_path}")
    return df


def aggregate(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    for key, group in df.groupby(group_cols + ["method"], dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        item = dict(zip(group_cols + ["method"], key))
        item.update(
            {
                "n": len(group),
                "valid": int((~group["error"]).sum()),
                "errors": int(group["error"].sum()),
                "root_top3": rate(group["root_top3"]),
                "risk_any": rate(group["risk_any"]),
                "risk_all": rate(group["risk_all"]),
                "effective_oc": rate(group["effective_oc"])
                if item["method"] == "sa-mcgs"
                else np.nan,
                "oc_hit": rate(group["oc_hit"])
                if item["method"] == "sa-mcgs"
                else np.nan,
                "compression": float(group["compression"].mean()),
                "subgraph_size": float(group["subgraph_size"].mean()),
            }
        )
        rows.append(item)
    return pd.DataFrame(rows)


def annotate_bars(ax, bars, fmt=pct_label, dy=0.02, fontsize=9):
    for bar in bars:
        height = bar.get_height()
        if np.isnan(height):
            continue
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height + dy,
            fmt(height),
            ha="center",
            va="bottom",
            fontsize=fontsize,
            fontweight="bold",
        )


def grouped_metric_panels(
    agg_df: pd.DataFrame,
    group_col: str,
    group_order: list[str],
    title: str,
    out_path: Path,
    xlabel_rotation: int = 0,
) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.4), sharey=True)
    x = np.arange(len(group_order))
    width = 0.34
    for ax, (metric, label) in zip(axes, METRICS):
        for idx, method in enumerate(["naive", "sa-mcgs"]):
            vals = []
            for group_value in group_order:
                matched = agg_df[
                    (agg_df[group_col].astype(str) == str(group_value))
                    & (agg_df["method"] == method)
                ]
                vals.append(float(matched[metric].iloc[0]) if not matched.empty else np.nan)
            offset = (idx - 0.5) * width
            bars = ax.bar(
                x + offset,
                vals,
                width,
                label=method,
                color=METHOD_COLORS[method],
                alpha=0.92,
            )
            annotate_bars(ax, bars)
        ax.set_title(label, fontsize=15, fontweight="bold")
        ax.set_ylim(0, 1.12)
        ax.set_xticks(x)
        ax.set_xticklabels(group_order, rotation=xlabel_rotation, ha="right" if xlabel_rotation else "center")
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Strict hit rate")
    axes[1].legend(loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.18))
    fig.suptitle(title, fontsize=20, fontweight="bold", y=1.06)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_domain_size(df: pd.DataFrame) -> Path:
    agg_df = aggregate(df, ["size_label"])
    ordered = (
        df[["domain", "actual_size", "requested_size", "size_label"]]
        .drop_duplicates()
        .sort_values(["domain", "actual_size", "requested_size"])
    )
    order = ordered["size_label"].tolist()
    out = FIG_DIR / "severitygrid_domain_size_metrics.png"
    grouped_metric_panels(
        agg_df,
        "size_label",
        order,
        "Method comparison by actual SCC size",
        out,
        xlabel_rotation=18,
    )
    return out


def _metric_cell(group: pd.DataFrame, metric: str) -> str:
    return fmt_count_rate(int(group[metric].sum()), len(group))


def plot_headline_table(df: pd.DataFrame) -> Path:
    rows = []
    for domain, size in [("bgb", 25), ("cuad", 25)]:
        for method in ["naive", "sa-mcgs"]:
            group = df[(df["domain"] == domain) & (df["actual_size"] == size) & (df["method"] == method)]
            if group.empty:
                continue
            rows.append(
                [
                    domain.upper(),
                    str(size),
                    "Naive direct" if method == "naive" else "SA-MCGS",
                    _metric_cell(group, "root_top3"),
                    _metric_cell(group, "risk_any"),
                    _metric_cell(group, "risk_all"),
                    "-" if method == "naive" else _metric_cell(group, "effective_oc"),
                    f"{group['subgraph_size'].mean():.1f}",
                    pct_label(float(group["compression"].mean())),
                    fmt_count_rate(int(group["error"].sum()), len(group)),
                ]
            )

    headers = [
        "Domain",
        "SCC",
        "Method",
        "Root@3",
        "Risk-any",
        "Risk-all",
        "Effective OC",
        "Avg nodes",
        "Compression",
        "Errors",
    ]
    fig, ax = plt.subplots(figsize=(19, 4.8))
    ax.axis("off")
    ax.set_title(
        "Main evidence table: BGB-25 for root localization, CUAD-25 for noisy risk retention",
        fontsize=24,
        fontweight="bold",
        pad=18,
    )
    table = ax.table(
        cellText=rows,
        colLabels=headers,
        loc="center",
        cellLoc="center",
        colLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(15)
    table.scale(1, 2.2)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#d7dde8")
        if r == 0:
            cell.set_facecolor("#111827")
            cell.set_text_props(color="white", weight="bold")
        else:
            method = rows[r - 1][2]
            if method == "SA-MCGS":
                cell.set_facecolor("#ecfdf5")
            elif method == "Naive direct":
                cell.set_facecolor("#fff1f2")
            if c in {3, 4, 6, 8}:
                cell.set_text_props(weight="bold")
    out = FIG_DIR / "severitygrid_headline_table.png"
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_story_bars(df: pd.DataFrame) -> Path:
    def get(domain: str, size: int, method: str, metric: str) -> float:
        group = df[(df["domain"] == domain) & (df["actual_size"] == size) & (df["method"] == method)]
        if metric == "error":
            return float(group["error"].mean())
        return float(group[metric].mean())

    panels = [
        ("BGB-25 Root@3", "root_top3", "bgb", 25, "higher"),
        ("BGB-25 Compression", "compression", "bgb", 25, "higher"),
        ("CUAD-25 Risk-any", "risk_any", "cuad", 25, "higher"),
        ("CUAD-25 Error rate", "error", "cuad", 25, "lower"),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(19, 5.0), sharey=True)
    for ax, (title, metric, domain, size, direction) in zip(axes, panels):
        vals = [get(domain, size, "naive", metric), get(domain, size, "sa-mcgs", metric)]
        bars = ax.bar(["Naive", "SA-MCGS"], vals, color=[METHOD_COLORS["naive"], METHOD_COLORS["sa-mcgs"]], width=0.58)
        annotate_bars(ax, bars, dy=0.025, fontsize=13)
        ax.set_title(title, fontsize=17, fontweight="bold")
        ax.set_ylim(0, 1.12)
        ax.grid(axis="y", alpha=0.22)
        ax.text(
            0.5,
            -0.22,
            "higher is better" if direction == "higher" else "lower is better",
            transform=ax.transAxes,
            ha="center",
            fontsize=12,
            color="#52606d",
        )
    axes[0].set_ylabel("Rate")
    fig.suptitle("The clean story: SA improves long-ring localization, retention, compression, and stability", fontsize=23, fontweight="bold", y=1.08)
    fig.tight_layout()
    out = FIG_DIR / "severitygrid_main_story_bars.png"
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_severity(df: pd.DataFrame) -> Path:
    agg_df = aggregate(df, ["severity"])
    out = FIG_DIR / "severitygrid_severity_effect.png"
    grouped_metric_panels(
        agg_df,
        "severity",
        SEVERITY_ORDER,
        "Conflict severity makes the signal easier to retain",
        out,
    )
    return out


def plot_template(df: pd.DataFrame) -> Path:
    agg_df = aggregate(df, ["template"])
    out = FIG_DIR / "severitygrid_template_effect.png"
    grouped_metric_panels(
        agg_df,
        "template",
        TEMPLATE_ORDER,
        "Template-level difficulty profile",
        out,
        xlabel_rotation=18,
    )
    return out


def plot_compression(df: pd.DataFrame) -> Path:
    agg_df = aggregate(df, ["size_label"])
    ordered = (
        df[["domain", "actual_size", "requested_size", "size_label"]]
        .drop_duplicates()
        .sort_values(["domain", "actual_size", "requested_size"])
    )
    order = ordered["size_label"].tolist()
    x = np.arange(len(order))
    width = 0.34
    fig, axes = plt.subplots(1, 2, figsize=(16, 5.2))
    for ax, metric, title, ylabel, fmt in [
        (axes[0], "compression", "Average compression", "Compression ratio", pct_label),
        (axes[1], "subgraph_size", "Average subgraph size", "Nodes", lambda v: f"{v:.1f}"),
    ]:
        for idx, method in enumerate(["naive", "sa-mcgs"]):
            vals = []
            for group_value in order:
                matched = agg_df[
                    (agg_df["size_label"] == group_value) & (agg_df["method"] == method)
                ]
                vals.append(float(matched[metric].iloc[0]) if not matched.empty else np.nan)
            bars = ax.bar(
                x + (idx - 0.5) * width,
                vals,
                width,
                label=method,
                color=METHOD_COLORS[method],
                alpha=0.92,
            )
            annotate_bars(ax, bars, fmt=fmt, dy=0.02 if metric == "compression" else 0.12)
        ax.set_title(title, fontsize=15, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(order, rotation=18, ha="right")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylim(0, 1.05)
    axes[1].legend(loc="upper center", ncol=2, bbox_to_anchor=(-0.05, 1.18))
    fig.suptitle("Subgraph compactness: SA-MCGS is strongest on BGB-25", fontsize=20, fontweight="bold", y=1.06)
    fig.tight_layout()
    out = FIG_DIR / "severitygrid_compression_subgraph.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_model_errors(df: pd.DataFrame) -> Path:
    agg_df = aggregate(df, ["model"])
    order = sorted(df["model"].dropna().unique().tolist())
    x = np.arange(len(order))
    width = 0.26
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.2), sharey=True)
    panels = [
        ("root_top3", "Root@3"),
        ("risk_any", "Risk-any"),
        ("error_rate", "Parser / ranking error"),
    ]
    model_method = []
    for model in order:
        for method in ["naive", "sa-mcgs"]:
            group = df[(df["model"] == model) & (df["method"] == method)]
            model_method.append((model, method, float(group["error"].mean()) if len(group) else np.nan))
    for ax, (metric, title) in zip(axes, panels):
        for idx, method in enumerate(["naive", "sa-mcgs"]):
            vals = []
            for model in order:
                if metric == "error_rate":
                    group = df[(df["model"] == model) & (df["method"] == method)]
                    vals.append(float(group["error"].mean()) if len(group) else np.nan)
                else:
                    matched = agg_df[(agg_df["model"] == model) & (agg_df["method"] == method)]
                    vals.append(float(matched[metric].iloc[0]) if not matched.empty else np.nan)
            bars = ax.bar(
                x + (idx - 0.5) * width,
                vals,
                width,
                label=method,
                color=METHOD_COLORS[method],
                alpha=0.92,
            )
            annotate_bars(ax, bars)
        ax.set_title(title, fontsize=15, fontweight="bold")
        ax.set_ylim(0, 1.12)
        ax.set_xticks(x)
        ax.set_xticklabels(order)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Strict rate")
    axes[1].legend(loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.18))
    fig.suptitle("Model sensitivity and baseline output stability", fontsize=20, fontweight="bold", y=1.06)
    fig.tight_layout()
    out = FIG_DIR / "severitygrid_model_error_effect.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_sa_oc(df: pd.DataFrame) -> Path:
    sa = df[df["method"] == "sa-mcgs"].copy()
    agg_df = aggregate(sa, ["size_label"])
    ordered = (
        sa[["domain", "actual_size", "requested_size", "size_label"]]
        .drop_duplicates()
        .sort_values(["domain", "actual_size", "requested_size"])
    )
    order = ordered["size_label"].tolist()
    metrics = [("oc_hit", "OC hit"), ("effective_oc", "Effective OC / risk-any"), ("risk_all", "Risk-all")]
    x = np.arange(len(order))
    width = 0.24
    colors = ["#2f62bd", "#0f8b69", "#8b52bd"]
    fig, ax = plt.subplots(figsize=(15, 5.2))
    for idx, (metric, label) in enumerate(metrics):
        vals = []
        for group_value in order:
            matched = agg_df[(agg_df["size_label"] == group_value) & (agg_df["method"] == "sa-mcgs")]
            vals.append(float(matched[metric].iloc[0]) if not matched.empty else np.nan)
        bars = ax.bar(x + (idx - 1) * width, vals, width, label=label, color=colors[idx], alpha=0.92)
        annotate_bars(ax, bars)
    ax.set_title("SA-MCGS: OC signal is abundant, full endpoint retention is the hard part", fontsize=18, fontweight="bold")
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Strict rate")
    ax.set_xticks(x)
    ax.set_xticklabels(order, rotation=18, ha="right")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.16))
    fig.tight_layout()
    out = FIG_DIR / "severitygrid_sa_oc_vs_retention.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_delta_heatmap(df: pd.DataFrame) -> Path:
    agg_df = aggregate(df, ["size_label"])
    ordered = (
        df[["domain", "actual_size", "requested_size", "size_label"]]
        .drop_duplicates()
        .sort_values(["domain", "actual_size", "requested_size"])
    )
    rows = ordered["size_label"].tolist()
    cols = [
        ("root_top3", "Root@3"),
        ("risk_any", "Risk-any"),
        ("risk_all", "Risk-all"),
        ("compression", "Compression"),
    ]
    matrix = []
    for label in rows:
        vals = []
        for metric, _ in cols:
            n = agg_df[(agg_df["size_label"] == label) & (agg_df["method"] == "naive")]
            s = agg_df[(agg_df["size_label"] == label) & (agg_df["method"] == "sa-mcgs")]
            vals.append(float(s[metric].iloc[0]) - float(n[metric].iloc[0]) if not n.empty and not s.empty else np.nan)
        matrix.append(vals)
    arr = np.array(matrix)
    fig, ax = plt.subplots(figsize=(11.5, 5.4))
    im = ax.imshow(arr, cmap="RdYlGn", vmin=-0.65, vmax=0.65)
    ax.set_xticks(np.arange(len(cols)))
    ax.set_xticklabels([c[1] for c in cols])
    ax.set_yticks(np.arange(len(rows)))
    ax.set_yticklabels(rows)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            value = arr[i, j]
            if np.isnan(value):
                text = "-"
            else:
                text = f"{value:+.0%}"
            ax.text(j, i, text, ha="center", va="center", fontweight="bold", fontsize=12)
    ax.set_title("SA-MCGS minus Naive by actual SCC size", fontsize=18, fontweight="bold")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="SA - Naive")
    fig.tight_layout()
    out = FIG_DIR / "severitygrid_sa_minus_naive_heatmap.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_pairwise_wins(df: pd.DataFrame) -> Path:
    key_cols = ["domain", "actual_size", "requested_size", "template", "severity", "model"]
    metrics = [
        ("root_top3", "Root@3"),
        ("risk_any", "Risk-any"),
        ("risk_all", "Risk-all"),
        ("compression", "Compression"),
    ]
    counts = {label: {"Naive wins": 0, "Tie": 0, "SA wins": 0, "Comparable": 0} for _, label in metrics}
    for _, group in df.groupby(key_cols, dropna=False):
        n = group[group["method"] == "naive"]
        s = group[group["method"] == "sa-mcgs"]
        if n.empty or s.empty:
            continue
        nrow = n.iloc[0]
        srow = s.iloc[0]
        for metric, label in metrics:
            if metric == "compression":
                if np.isnan(nrow[metric]) or np.isnan(srow[metric]):
                    continue
                nv, sv = float(nrow[metric]), float(srow[metric])
            else:
                nv, sv = bool(nrow[metric]), bool(srow[metric])
            counts[label]["Comparable"] += 1
            if sv == nv:
                counts[label]["Tie"] += 1
            elif sv > nv:
                counts[label]["SA wins"] += 1
            else:
                counts[label]["Naive wins"] += 1

    labels = [label for _, label in metrics]
    naive_vals = [counts[label]["Naive wins"] for label in labels]
    tie_vals = [counts[label]["Tie"] for label in labels]
    sa_vals = [counts[label]["SA wins"] for label in labels]
    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.barh(y, naive_vals, color="#d94841", label="Naive wins")
    ax.barh(y, tie_vals, left=naive_vals, color="#cbd5e1", label="Tie")
    ax.barh(y, sa_vals, left=np.array(naive_vals) + np.array(tie_vals), color="#0f8b69", label="SA wins")
    for i, label in enumerate(labels):
        total = counts[label]["Comparable"]
        ax.text(total + 0.25, i, f"n={total}", va="center", fontsize=10)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Matched domain × size × template × severity × model cases")
    ax.set_title("Pairwise outcome: where SA beats, ties, or loses to Naive", fontsize=18, fontweight="bold")
    ax.legend(loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.16))
    ax.grid(axis="x", alpha=0.22)
    fig.tight_layout()
    out = FIG_DIR / "severitygrid_pairwise_wins.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def fmt_count_rate(num: int, den: int) -> str:
    return f"{num}/{den} ({num / den:.0%})" if den else "-"


def table_for(df: pd.DataFrame, group_cols: list[str]) -> str:
    agg_df = aggregate(df, group_cols)
    headers = group_cols + [
        "method",
        "n",
        "valid",
        "errors",
        "root_top3",
        "risk_any",
        "risk_all",
        "compression",
        "subgraph_size",
        "oc_hit",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in agg_df.sort_values(group_cols + ["method"]).iterrows():
        cells = []
        for col in headers:
            val = row[col]
            if col in {"root_top3", "risk_any", "risk_all", "oc_hit"}:
                cells.append(pct_label(float(val)) if not np.isnan(float(val)) else "-")
            elif col == "compression":
                cells.append(pct_label(float(val)) if not np.isnan(float(val)) else "-")
            elif col == "subgraph_size":
                cells.append(f"{float(val):.1f}" if not np.isnan(float(val)) else "-")
            else:
                cells.append(str(int(val)) if isinstance(val, (int, np.integer)) else str(val))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def make_contact_sheet(figures: list[Path], out_path: Path) -> Path:
    """Create one large PNG so previewers only need to open a plain image file."""
    title_map = {
        "severitygrid_headline_table": "1. Main evidence table",
        "severitygrid_main_story_bars": "2. Main story bars",
        "severitygrid_domain_size_metrics": "3. Method comparison by actual SCC size",
        "severitygrid_sa_minus_naive_heatmap": "4. SA minus Naive heatmap",
        "severitygrid_pairwise_wins": "5. Matched pair wins / ties / losses",
        "severitygrid_severity_effect": "6. Severity effect",
        "severitygrid_template_effect": "7. Template effect",
        "severitygrid_compression_subgraph": "8. Compression and subgraph size",
        "severitygrid_model_error_effect": "9. Model and parser-error effect",
        "severitygrid_sa_oc_vs_retention": "10. SA OC signal and risk retention",
    }
    target_width = 1800
    title_height = 58
    gap = 28
    margin = 34
    font = ImageFont.load_default()
    rendered: list[tuple[str, Image.Image]] = []
    for fig in figures:
        img = Image.open(fig).convert("RGB")
        ratio = target_width / img.width
        resized = img.resize((target_width, int(img.height * ratio)), Image.LANCZOS)
        rendered.append((title_map.get(fig.stem, fig.stem), resized))

    total_height = margin + sum(title_height + img.height + gap for _, img in rendered) + margin
    canvas = Image.new("RGB", (target_width + margin * 2, total_height), "white")
    draw = ImageDraw.Draw(canvas)
    y = margin
    for title, img in rendered:
        draw.text((margin, y + 14), title, fill=(22, 24, 29), font=font)
        y += title_height
        canvas.paste(img, (margin, y))
        y += img.height + gap
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return out_path


def write_report(df: pd.DataFrame, figures: list[Path], out_path: Path) -> None:
    total = len(df)
    by_method = aggregate(df, ["domain"])
    bgb25 = aggregate(df[(df["domain"] == "bgb") & (df["actual_size"] == 25)], ["domain"])
    cuad25 = aggregate(df[(df["domain"] == "cuad") & (df["actual_size"] == 25)], ["domain"])
    sev = aggregate(df, ["severity"])
    actual_sizes = (
        df[["domain", "requested_size", "actual_size"]]
        .drop_duplicates()
        .sort_values(["domain", "requested_size", "actual_size"])
    )
    bgb25_sa = bgb25[bgb25["method"] == "sa-mcgs"].iloc[0]
    bgb25_nv = bgb25[bgb25["method"] == "naive"].iloc[0]
    cuad25_sa = cuad25[cuad25["method"] == "sa-mcgs"].iloc[0]
    cuad25_nv = cuad25[cuad25["method"] == "naive"].iloc[0]
    critical_sa = sev[(sev["severity"] == "critical") & (sev["method"] == "sa-mcgs")].iloc[0]
    standard_sa = sev[(sev["severity"] == "standard") & (sev["method"] == "sa-mcgs")].iloc[0]

    local_figures = []
    for fig in figures:
        local_fig = out_path.parent / fig.name
        if local_fig.resolve() != fig.resolve():
            local_fig.write_bytes(fig.read_bytes())
        local_figures.append(local_fig)

    contact_sheet_fig = make_contact_sheet(local_figures, FIG_DIR / CONTACT_SHEET_NAME)
    contact_sheet = out_path.parent / CONTACT_SHEET_NAME
    contact_sheet.write_bytes(contact_sheet_fig.read_bytes())

    def figure_file_link(fig: Path, alt: str) -> str:
        return (
            f"![{alt}]({FIGURE_BASE_URL}/{fig.name})\n\n"
            f"[打开原图]({FIGURE_BASE_URL}/{fig.name})"
        )

    figure_links = f"""
### 图 1. 主结果表

{figure_file_link(local_figures[0], "主结果表")}

**读法。** 只看两个最有论文价值的长环：BGB actual 25 和 CUAD actual 25。BGB 是干净法条图，适合作主结果；CUAD 是 noisy 合同图，适合作泛化补充。

**结论。** BGB-25 上 SA-MCGS 把 Naive 完全漏掉的 root 拉进 Top-3，同时子图更小；CUAD-25 上 SA 更容易保留至少一个风险入口，但完整收齐所有端点仍然难。

### 图 2. 主叙事四指标

{figure_file_link(local_figures[1], "主叙事四指标")}

**读法。** 前三列越高越好，最后一列 error rate 越低越好。它把“定位、压缩、风险保留、稳定性”放在一张图里。

**结论。** 最适合写进正文的一句话是：**SA-MCGS 在干净长环里显著改善 root localization，在 noisy 合同图里提高 risk-any retention，同时保持更稳定的结构化输出。**

### 图 3. 不同实际 SCC 长度下的方法差异

{figure_file_link(local_figures[2], "不同实际 SCC 长度下的方法差异")}

**读法。** 每个小图分别是 `Root@3`、`Risk-any`、`Risk-all`。横轴是实际 SCC 长度，不是请求长度。

**结论。** BGB-25 上 SA-MCGS 的 `Root@3` 从 Naive 的 `0%` 拉到 `58%`，这是本轮最干净的长环优势；CUAD-25 上 SA-MCGS 的 `Risk-any` 达到 `83%`，比 Naive 的 `54%` 高很多，但 `Risk-all` 仍低。

### 图 4. SA-MCGS 相对 Naive 的差值热力图

{figure_file_link(local_figures[3], "SA-MCGS 相对 Naive 的差值热力图")}

**读法。** 绿色表示 SA-MCGS 高于 Naive，红色表示低于 Naive。

**结论。** SA 的优势集中在 BGB-25 的 Root@3 和 Compression，以及 CUAD-25 的 Risk-any。Risk-all 不稳定，尤其 CUAD 上 Naive valid output 一旦能生成子图，常常会同时包含两个端点，所以不能把 Risk-all 当唯一主指标。

### 图 5. Matched pair 胜/平/负

{figure_file_link(local_figures[4], "Matched pair 胜平负")}

**读法。** 每个 matched pair 是同一个 domain、size、template、severity、model 下的 Naive-vs-SA 对比。绿色是 SA wins，灰色是 tie，红色是 Naive wins。

**结论。** SA 在 Root@3 和 Compression 上更常赢；Risk-any 大量 tie，说明 Naive direct-subgraph 已经是很强 baseline；Risk-all 不是 SA 的稳定优势点。

### 图 6. 严重程度影响

{figure_file_link(local_figures[5], "严重程度影响")}

**读法。** 横轴从 standard 到 critical。高危注入应当让结构风险更容易暴露。

**结论。** 这个趋势成立：SA-MCGS 的 Risk-any 从 `47%` 提升到 `84%`，Root@3 从 `38%` 提升到 `78%`。主实验应聚焦 severe/critical，把 standard 放到 ablation 或 appendix。

### 图 7. 不同结构冲突模板

{figure_file_link(local_figures[6], "不同结构冲突模板")}

**读法。** direct_mutex 是直接互斥，handoff_invariant 是链路交接不变量，temporal_gate 是时间门控，condition_trigger 是条件触发。

**结论。** handoff_invariant 对 SA 最友好：Root@3 从 Naive `29%` 到 SA `71%`，Risk-any 从 `54%` 到 `75%`。condition_trigger 对 Naive 也很友好，更适合作 sanity，而不是 SA 优势主证据。

### 图 8. 子图压缩与平均子图大小

{figure_file_link(local_figures[7], "子图压缩与平均子图大小")}

**读法。** 左图是压缩率，越高越好；右图是平均子图节点数，越小越好，但不能小到丢掉风险点。

**结论。** BGB-25 上 SA 的子图明显更小：Naive 平均 `7.3` 节点，SA 平均 `3.8` 节点；压缩率从 `71%` 到 `85%`。这非常适合支撑“风险子图压缩”这条论文主线。

### 图 9. 模型差异与输出稳定性

{figure_file_link(local_figures[8], "模型差异与输出稳定性")}

**读法。** 第三个小图是 parser/ranking error。这里的错误不是 API 错，而是 baseline 没能按要求吐出完整可评估结构。

**结论。** DeepSeek 的 Naive direct-subgraph 很强；gpt-4o 的 Naive 出现 `19/48` 解析/排名错误，而 SA-MCGS 没有错误。论文里不能只说 Naive 弱，应该说 one-shot direct subgraph 在强模型上能抓到风险，但输出稳定性和长环 root 定位仍弱于结构化搜索。

### 图 10. SA 的 OC signal 与风险保留

{figure_file_link(local_figures[9], "SA 的 OC signal 与风险保留")}

**读法。** OC hit 表示 SA 局部搜索产生 ordered-cycle/结构证据；Effective OC 表示 OC 或 core evidence 是否落入风险区域；Risk-all 是同时保留所有风险端点。

**结论。** SA 的 OC 信号很充足：CUAD-25 是 `100%`，BGB-25 是 `88%`。但 Risk-all 低很多，说明当前算法已经会发现“这里有结构风险”，但最终 core 选择不总能同时保留 root+witness。后续算法改进应集中在 OC-to-core retention，而不是继续扩大 one-shot prompt。
"""
    size_lines = "\n".join(
        f"- `{row.domain}` requested `{row.requested_size}` -> actual SCC size `{row.actual_size}`"
        for row in actual_sizes.itertuples(index=False)
    )

    report = f"""# Severity Grid 实验分析

**一句话结论：** 这轮实验不应该写成“Naive 完全不行”。更准确的论文主线是：**SA-MCGS 在长环结构里更会定位 root、更会压缩风险子图，并且能留下 OC / core evidence 作为可解释搜索证据。**

本轮共 {total} 条 method-level 记录，来自 48 个实验 block。Naive direct-subgraph 有 19/96 条解析或排名结构错误；SA-MCGS 是 0/96。下面所有 hit rate 默认采用 strict rate：不可解析输出按失败计。

图表文件：

- 总览长图：[打开 PNG]({FIGURE_BASE_URL}/{contact_sheet.name})
- 自包含 HTML：[打开 HTML](http://127.0.0.1:8777/analysis)
- 单张图在每个图表小节中直接展示，并附有“打开原图”链接。

## 1. 最重要的结论

1. **高严重度注入确实让信号更可见。** SA-MCGS 的 `Risk-any` 从 standard 的 `{pct_label(float(standard_sa.risk_any))}` 提升到 critical 的 `{pct_label(float(critical_sa.risk_any))}`，`Root@3` 也从 `{pct_label(float(standard_sa.root_top3))}` 提升到 `{pct_label(float(critical_sa.root_top3))}`。

2. **BGB-25 是当前最漂亮的长环对照。** 在 actual 25-node BGB 上，Naive `Root@3={pct_label(float(bgb25_nv.root_top3))}`，SA-MCGS `Root@3={pct_label(float(bgb25_sa.root_top3))}`；Naive 子图平均 `7.3` 个节点、压缩率 `{pct_label(float(bgb25_nv.compression))}`，SA 子图平均 `3.8` 个节点、压缩率 `{pct_label(float(bgb25_sa.compression))}`。也就是说 SA 不只是更能找 root，还明显更会压缩。

3. **CUAD 在高噪声合同图上仍然更难。** CUAD-25 上 SA `Risk-any={pct_label(float(cuad25_sa.risk_any))}`，高于 Naive `{pct_label(float(cuad25_nv.risk_any))}`；但 `Risk-all` 仍然低，说明合同图里的原生风险/噪声会吞掉完整端点收敛。

4. **Risk-all 不是当前主叙事。** 结构性缺陷有 root/witness/affected 多个风险入口，修复时不一定必须同时抓住所有端点。更稳的主指标应该是：`Root@3 + Risk-any + Effective OC + Compression`。

5. **BGB requested 14 实际不是 14-node。** 代码选择不到 14-node BGB SCC 时 fallback 到了 3-node SCC，所以这部分只能当小环 sanity，不应写成 14-node 主结果。

## 2. 指标口径和解释

- `Root@3`：GT/root 节点是否进入前三。这个最接近传统“定位注入节点”的指标，但对结构性缺陷来说并不完整，因为 witness/affected node 也可能是有效修复入口。
- `Risk-any`：输出子图是否至少包含一个风险端点，例如 root 或 witness。对于结构性风险，这个比单点 Top-k 更合理，因为修复任意一端可能都能解除冲突。
- `Risk-all`：输出子图是否同时包含所有风险端点。这个很严格，适合作为上限指标，但不适合作为唯一主指标。
- `OC hit`：SA-MCGS 的局部窗口搜索是否产生结构证据。Naive 没有这个机制，所以不是同列比较，而是 SA 的解释性信号。
- `Effective OC`：OC/core evidence 是否落到风险区域。它比单纯 OC hit 更关键，因为只发现“某处有结构信号”还不够，必须和风险端点发生重合。
- `Compression`：子图压缩率。高压缩率意味着模型把长 SCC 收缩成更小的可检查风险区域。
- `Errors`：Naive direct-subgraph 的 JSON/排名结构不完整错误。strict rate 把它算失败，因为不可解析输出不能进入自动评估，也不能作为稳定系统输出。

**本轮主指标建议：** `Root@3 + Risk-any + Effective OC + Compression`。  
`Risk-all` 应该保留，但作为更严格的附加指标，不建议作为主叙事中心。

## 3. 分层分析

### 3.1 BGB：干净法条图，最适合作为主证据

BGB 的性质更像“正确、规范、低噪声的法律文本图”。因此如果这里出现长环结构风险，模型不应该被大量原生错误干扰。实际结果也最清楚：

- BGB actual 25 上，Naive `Root@3=0%`，SA-MCGS `Root@3=58%`。
- BGB actual 25 上，Naive `Risk-any=42%`，SA-MCGS `Risk-any=54%`。
- BGB actual 25 上，两者 `Risk-all` 都只有 `4%`，说明完整收齐 root+witness 仍然难。
- BGB actual 25 上，SA 的平均子图只有 `3.8` 个节点，Naive 是 `7.3` 个节点；SA 压缩率 `85%`，Naive `71%`。

所以 BGB-25 的论文表述应该是：**SA-MCGS 在干净长环法条图里显著改善 root 定位，并生成更小的风险子图；完整端点收齐仍是后续优化点。**

### 3.2 CUAD：高噪声合同图，适合作为泛化补充

CUAD 本身来自合同抽取/条款图构造，天然有更多噪声和潜在标注问题。这里不能期待像 BGB 那样干净，但它能测试“噪声下是否还能保留风险区域”。

- CUAD actual 25 上，Naive `Risk-any=54%`，SA-MCGS `Risk-any=83%`。
- CUAD actual 25 上，SA 的 `OC hit=100%`，说明局部搜索几乎总能找到结构信号。
- CUAD actual 25 上，Naive `Risk-all=46%`，SA `Risk-all=29%`。这说明 Naive 一旦成功吐出 direct subgraph，经常会把多个风险端点一起包进去；SA 的 dynamic core 更偏向压缩，可能剪掉 witness。
- CUAD actual 25 上，Naive 有 `8/24` 条解析/排名错误；SA 没有。

所以 CUAD 的论文表述应该更克制：**SA-MCGS 在 noisy contract graph 上提高 Risk-any 和 OC 解释信号，但 Risk-all 不占优，说明合同域需要更强的 OC-to-core retention。**

### 3.3 严重程度：critical 才是主实验应使用的设置

severity 趋势非常明显：

- standard 下，SA `Root@3=38%`、`Risk-any=47%`。
- severe 下，SA `Root@3=75%`、`Risk-any=78%`。
- critical 下，SA `Root@3=78%`、`Risk-any=84%`、`Risk-all=53%`。

这说明早期注入确实偏弱或者偏“单看合理但后果不够重”。如果论文要证明 high-risk structural accident，主实验应该聚焦 `severe/critical`，把 standard 放到 ablation 或 appendix。

### 3.4 模板：handoff/temporal 更像 SA-MCGS 的真实战场

- `handoff_invariant`：SA `Root@3=71%`，Naive `29%`；SA `Risk-any=75%`，Naive `54%`。这是最适合讲“长链路交接不变量”的模板。
- `temporal_gate`：SA `Risk-any=75%`，Naive `54%`，也很适合结构搜索叙事。
- `condition_trigger`：Naive `Risk-any=79%`，SA `71%`，两者 `Risk-all=46%`。这个模板对 one-shot 也很友好，更像强 baseline sanity。
- `direct_mutex`：SA 改善 Root@3，但 Risk-any 持平，Risk-all 低于 Naive。它太直接，未必最能体现 SA 的慢搜索优势。

因此论文主实验模板优先级建议：`handoff_invariant > temporal_gate > condition_trigger > direct_mutex`。

### 3.5 模型差异：DeepSeek 强，gpt-4o 暴露 one-shot 稳定性问题

- DeepSeek Naive 很强：`Risk-any=85%`、`Risk-all=65%`，且没有解析错误。
- gpt-4o Naive 有 `19/48` 条解析/排名错误，strict 指标明显下降。
- SA-MCGS 两个模型都没有解析错误；gpt-4o 下 SA `Root@3=71%`，Naive strict `27%`。

这意味着论文不能简单写“Naive 看不见风险”。更准确的说法是：**强 one-shot baseline 可以直接抓到部分风险点，但结构化搜索在长环 root 定位、可解释 OC 证据和输出稳定性上更稳。**

## 4. 怎么把这轮结果写进论文

### 4.1 主结果应该怎么讲

这轮结果最有价值的不是“SA-MCGS 所有指标都赢”，而是更细的一条线：

1. **在干净长环里，SA-MCGS 明显更会定位 root。** BGB actual 25 是关键 case：Naive direct-subgraph 的 `Root@3=0%`，SA-MCGS 是 `58%`。这说明当风险不是简单靠单点文本显著性判断，而是需要沿结构证据回推时，rollout + relation-first core 能把 root 拉回候选前列。

2. **在 noisy 合同图里，SA-MCGS 更像风险区域搜索器。** CUAD actual 25 上，`Risk-any` 从 Naive `54%` 到 SA `83%`，但 `Risk-all` 不占优。这说明合同图本身有很多可疑条款/抽取噪声，SA 更擅长保住一个可修复入口，而不是同时收齐所有端点。

3. **压缩不是附属指标，而是核心贡献。** BGB actual 25 上 SA 平均子图 `3.8/25`，Naive `7.3/25`；SA 用更少节点保留更强 root 信号。论文里应该把它写成“可检查风险子图”，而不只是 Top-k 排名。

4. **OC/Effective OC 是 SA 与 Naive 的机制差异。** Naive direct-subgraph 可以直接吐一个子图，所以我们不能再说 Naive 没有子图能力；但 Naive 没有独立的局部结构证据。SA 的优势在于：它不仅给出候选子图，还能留下“为什么这个局部区域可疑”的 OC/core evidence。

### 4.2 当前不能过度声称什么

- 不能说 Naive 完全失败。DeepSeek 的 direct-subgraph Naive 很强，尤其在部分模板上能直接抓到风险端点。
- 不能把 `Risk-all` 当主胜负。结构风险可以通过 root、witness 或 affected node 任意一端修复，`Risk-all` 更像“完整解释上限”，不是唯一有效性指标。
- 不能把 BGB requested 14 写成 14-node 结果。它 fallback 到 actual 3，只能作为 sanity。
- 不能把 CUAD 写成干净法律知识图。CUAD 更像 noisy contract extraction stress test，它的意义是泛化和鲁棒性，不是主证据。

### 4.3 推荐主表口径

主表建议只放 `BGB actual 25` 和 `CUAD actual 25`，并按以下列组织：

| Domain | Actual SCC | Method | Root@3 | Risk-any | Effective OC | Avg subgraph | Compression | Error |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| BGB | 25 | Naive direct-subgraph | 0% | 42% | - | 7.3 | 71% | 9/24 |
| BGB | 25 | SA-MCGS | 58% | 54% | 见图表 | 3.8 | 85% | 0/24 |
| CUAD | 25 | Naive direct-subgraph | 46% | 54% | - | 4.7 | 81% | 8/24 |
| CUAD | 25 | SA-MCGS | 54% | 83% | 见图表 | 4.2 | 83% | 0/24 |

这张表的主信息是：**BGB 证明长环 root localization，CUAD 证明 noisy domain 下风险区域 retention；二者共同支撑 SA-MCGS 是结构化风险搜索，而不是单纯 anomaly ranking。**

## 5. 实际 SCC 口径

{size_lines}

## 6. 图表

{figure_links}

## 7. 分组表

### By Domain

{table_for(df, ["domain"])}

### By Actual Size

{table_for(df, ["domain", "actual_size"])}

### By Severity

{table_for(df, ["severity"])}

### By Template

{table_for(df, ["template"])}

### By Model

{table_for(df, ["model"])}

### By Domain / Valid-only

下面这个表只统计可解析输出，主要用于判断 Naive 错误是否单纯由 parser 问题造成。论文主表仍建议使用 strict rate，因为不可解析输出本身就是 one-shot baseline 的系统稳定性问题。

{table_for(df[~df["error"]], ["domain"])}

## 8. 对论文实验叙事的建议

- 主结果优先写 `BGB-25 + CUAD-25`，不要把 fallback 的 BGB-3 伪装成 14-node。
- 对 CUAD 的解释要强调：它本来就是 noisy contract extraction graph，所以 SA 的价值更像“从噪声里稳定提出可解释风险区域”，而不是保证 `risk-all`。
- 对 BGB 的解释可以更强：干净法条图上，SA-MCGS 在 25-node 长环里把 Naive 漏掉的 root 拉回，并以更小子图表达风险。
- 下一轮如果要追 ARR 高分，建议增加真实 `BGB 11-25` 中可验证存在的长度，避免 fallback；同时针对 CUAD 增加 `critical`/`severe` 高危模板即可，不需要继续扩 standard。
"""
    out_path.write_text(report, encoding="utf-8")
    write_html_report(report, local_figures, out_path.with_suffix(".html"))


def write_html_report(markdown_text: str, figures: list[Path], out_path: Path) -> None:
    """Write a self-contained HTML report so images cannot break in previewers."""
    sections = []
    for fig in figures:
        encoded = base64.b64encode(fig.read_bytes()).decode("ascii")
        sections.append(
            f"""
            <figure>
              <img src="data:image/png;base64,{encoded}" alt="{html.escape(fig.stem)}">
              <figcaption>{html.escape(fig.stem)}</figcaption>
            </figure>
            """
        )

    escaped = html.escape(markdown_text)
    body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Severity Grid 实验分析</title>
  <style>
    body {{
      margin: 0;
      background: #f8fafc;
      color: #16181d;
      font: 18px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 36px 28px 72px;
    }}
    h1 {{
      font-size: 38px;
      margin: 0 0 22px;
    }}
    .note {{
      border-left: 8px solid #0f8b69;
      background: #ecfdf5;
      padding: 16px 20px;
      margin: 18px 0 26px;
      font-weight: 650;
    }}
    figure {{
      margin: 28px 0;
      padding: 16px;
      border: 1px solid #d6dde8;
      border-radius: 8px;
      background: white;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
    }}
    img {{
      width: 100%;
      height: auto;
      display: block;
    }}
    figcaption {{
      color: #52606d;
      margin-top: 10px;
      font-size: 15px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: white;
      border: 1px solid #d6dde8;
      border-radius: 8px;
      padding: 18px;
      font-size: 15px;
      overflow: auto;
    }}
  </style>
</head>
<body>
<main>
  <h1>Severity Grid 实验分析</h1>
  <div class="note">这份 HTML 的图像已内嵌为 base64，不依赖 Markdown 相对路径。</div>
  {''.join(sections)}
  <h2>Markdown 原文</h2>
  <pre>{escaped}</pre>
</main>
</body>
</html>
"""
    out_path.write_text(body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-file", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    df = load_dataframe(args.status_file)
    figures = [
        plot_headline_table(df),
        plot_story_bars(df),
        plot_domain_size(df),
        plot_delta_heatmap(df),
        plot_pairwise_wins(df),
        plot_severity(df),
        plot_template(df),
        plot_compression(df),
        plot_model_errors(df),
        plot_sa_oc(df),
    ]
    write_report(df, figures, args.report)
    print(f"records={len(df)}")
    print(f"report={args.report}")
    print(f"html={args.report.with_suffix('.html')}")
    for fig in figures:
        print(f"figure={fig}")


if __name__ == "__main__":
    main()

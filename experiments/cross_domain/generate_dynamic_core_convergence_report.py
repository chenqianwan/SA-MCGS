"""Generate per-case SA-MCGS convergence curves for dynamic-core runs."""
from __future__ import annotations

import argparse
import base64
import csv
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib.pyplot as plt


DEFAULT_RESULT = (
    "battle_inject_memory_stress_handoff_invariant_directsubgraphnaive_"
    "relation_first_dynamic_core_formal_8to22_20260515_1778814469.json"
)
RESULTS_DIR = Path(__file__).parent / "results"
CASE_DIR = RESULTS_DIR / "dynamic_core_convergence_cases"


def pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def yn(value: Any) -> str:
    return "Yes" if bool(value) else "No"


def png_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def embedded_png(path: Path, alt: str) -> str:
    return f"![{alt}]({png_data_uri(path)})"


def clean_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return value.strip("_") or "case"


def domain_label(domain: str) -> str:
    return {
        "debian": "Debian",
        "sec_ex21": "SEC EX-21",
        "bgb": "BGB",
        "cuad": "CUAD",
    }.get(domain, domain)


def load_sa_cases(result_path: Path) -> list[dict[str, Any]]:
    rows = json.loads(result_path.read_text())
    cases = [
        row for row in rows
        if row.get("method") == "sa-mcgs"
        and not row.get("error")
        and row.get("convergence_trace")
    ]
    cases.sort(
        key=lambda row: (
            str(row.get("domain") or ""),
            int(row.get("scc_size") or 0),
            str(row.get("scc_id") or ""),
            str(row.get("model") or ""),
        )
    )
    return cases


def case_label(case: dict[str, Any]) -> str:
    return (
        f"{domain_label(str(case.get('domain') or ''))} "
        f"{int(case.get('scc_size') or 0)}n "
        f"{case.get('model')}"
    )


def trace_series(case: dict[str, Any], key: str) -> tuple[list[int], list[float]]:
    trace = case.get("convergence_trace") or []
    return (
        [int(point.get("rollout") or 0) for point in trace],
        [float(point.get(key) or 0.0) for point in trace],
    )


def trace_bool_rollouts(case: dict[str, Any], key: str) -> list[int]:
    return [
        int(point.get("rollout") or 0)
        for point in case.get("convergence_trace") or []
        if point.get(key)
    ]


def smooth(values: list[float], window: int = 5) -> list[float]:
    if not values:
        return []
    radius = max(1, window // 2)
    smoothed: list[float] = []
    for idx in range(len(values)):
        left = max(0, idx - radius)
        right = min(len(values), idx + radius + 1)
        smoothed.append(mean(values[left:right]))
    return smoothed


def aggregate_by_rollout(cases: list[dict[str, Any]]) -> dict[str, list[float]]:
    rollouts = sorted({
        int(point.get("rollout") or 0)
        for case in cases
        for point in case.get("convergence_trace") or []
    })
    aggregate = {
        "rollout": [float(value) for value in rollouts],
        "risk_coverage": [],
        "valuable_coverage": [],
        "risk_any_rate": [],
        "risk_all_rate": [],
        "core_compression": [],
        "effective_compression": [],
        "core_size": [],
    }
    for rollout in rollouts:
        points = [
            point
            for case in cases
            for point in case.get("convergence_trace") or []
            if int(point.get("rollout") or 0) == rollout
        ]
        aggregate["risk_coverage"].append(
            mean(float(point.get("risk_coverage") or 0.0) for point in points)
        )
        aggregate["valuable_coverage"].append(
            mean(float(point.get("valuable_coverage") or 0.0) for point in points)
        )
        aggregate["risk_any_rate"].append(
            mean(1.0 if point.get("risk_any") else 0.0 for point in points)
        )
        aggregate["risk_all_rate"].append(
            mean(1.0 if point.get("risk_all") else 0.0 for point in points)
        )
        aggregate["core_compression"].append(
            mean(float(point.get("compression_ratio") or 0.0) for point in points)
        )
        aggregate["effective_compression"].append(
            mean(
                float(point.get("compression_ratio") or 0.0)
                if point.get("risk_any") else 0.0
                for point in points
            )
        )
        aggregate["core_size"].append(
            mean(float(point.get("subgraph_size") or 0.0) for point in points)
        )
    return aggregate


def draw_verticals(ax: plt.Axes, case: dict[str, Any]) -> None:
    first_any = case.get("first_subgraph_risk_any_rollout")
    first_all = case.get("first_subgraph_risk_all_rollout")
    effective_oc = case.get("first_effective_oc_rollout")
    if first_any:
        ax.axvline(
            int(first_any),
            color="#059669",
            linewidth=1.7,
            alpha=0.55,
            linestyle="-",
            label="first risk-any",
        )
    if first_all:
        ax.axvline(
            int(first_all),
            color="#7c3aed",
            linewidth=2.1,
            alpha=0.60,
            linestyle="-",
            label="first risk-all",
        )
    if effective_oc:
        ax.axvline(
            int(effective_oc),
            color="#dc2626",
            linewidth=1.5,
            alpha=0.55,
            linestyle="--",
            label="effective OC",
        )


def plot_fitted_overview(cases: list[dict[str, Any]], output: Path) -> None:
    aggregate = aggregate_by_rollout(cases)
    x = aggregate["rollout"]
    fig, ax = plt.subplots(figsize=(15.5, 8.2), dpi=190)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")

    series = [
        ("risk_any_rate", "Risk-any hit rate", "#2563eb", "-", 3.2),
        ("risk_all_rate", "Risk-all hit rate", "#7c3aed", "-", 2.8),
        ("core_compression", "Core compression", "#059669", "--", 3.0),
        ("effective_compression", "Effective compression", "#f97316", "--", 3.0),
    ]
    for key, label, color, linestyle, width in series:
        raw = aggregate[key]
        fitted = smooth(raw, window=5)
        ax.plot(x, raw, color=color, alpha=0.22, linewidth=1.2, marker="o", markersize=2.2)
        ax.plot(x, fitted, color=color, linewidth=width, linestyle=linestyle, label=label)

    first_any_values = [
        int(case["first_subgraph_risk_any_rollout"])
        for case in cases
        if case.get("first_subgraph_risk_any_rollout")
    ]
    first_all_values = [
        int(case["first_subgraph_risk_all_rollout"])
        for case in cases
        if case.get("first_subgraph_risk_all_rollout")
    ]
    effective_oc_values = [
        int(case["first_effective_oc_rollout"])
        for case in cases
        if case.get("first_effective_oc_rollout")
    ]
    marker_rows = [
        (first_any_values, "#10b981", "median first risk-any"),
        (first_all_values, "#7c3aed", "median first risk-all"),
        (effective_oc_values, "#dc2626", "median effective OC"),
    ]
    for values, color, label in marker_rows:
        if not values:
            continue
        median_value = sorted(values)[len(values) // 2]
        ax.axvline(median_value, color=color, linewidth=1.8, alpha=0.40)
        ax.text(
            median_value + 0.25,
            0.06,
            f"{label}: {median_value}",
            rotation=90,
            va="bottom",
            ha="left",
            fontsize=9.5,
            color=color,
            fontweight="bold",
        )

    final_risk_any = sum(bool(case.get("core_evidence_contains_any_risk_node")) for case in cases)
    final_risk_all = sum(bool(case.get("core_evidence_contains_all_risk_nodes")) for case in cases)
    avg_compression = mean(float(case.get("core_evidence_compression_ratio") or 0.0) for case in cases)
    avg_effective = mean(
        float(case.get("core_evidence_compression_ratio") or 0.0)
        if case.get("core_evidence_contains_any_risk_node") else 0.0
        for case in cases
    )
    ax.text(
        0.98,
        0.08,
        (
            f"Final: risk-any {final_risk_any}/{len(cases)}, "
            f"risk-all {final_risk_all}/{len(cases)}\n"
            f"avg compression {pct(avg_compression)}, "
            f"effective compression {pct(avg_effective)}"
        ),
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=11,
        color="#111827",
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#ffffff", "alpha": 0.82, "edgecolor": "#e5e7eb"},
    )

    ax.set_title(
        "Aggregate fitted convergence: dynamic-core SA-MCGS",
        fontsize=20,
        fontweight="bold",
        pad=18,
    )
    ax.set_xlabel("Rollout")
    ax.set_ylabel("Rate")
    ax.set_xlim(min(x), max(x))
    ax.set_ylim(-0.04, 1.04)
    ax.grid(alpha=0.23)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.02), ncol=4, fontsize=11)
    fig.text(
        0.5,
        0.02,
        "Faint markers are raw cross-case means at each rollout; thick lines are 5-rollout moving-average fits.",
        ha="center",
        fontsize=10.5,
        color="#4b5563",
    )
    fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.95])
    fig.savefig(output, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def plot_overview(cases: list[dict[str, Any]], output: Path) -> None:
    fig, axes = plt.subplots(4, 4, figsize=(22, 16), dpi=180, sharex=True, sharey=True)
    fig.patch.set_facecolor("#fbfbf8")
    axes = axes.ravel()
    for ax, case in zip(axes, cases):
        x, risk = trace_series(case, "risk_coverage")
        _, valuable = trace_series(case, "valuable_coverage")
        _, compression = trace_series(case, "compression_ratio")
        ax.plot(x, risk, color="#2563eb", linewidth=2.2, marker="o", markersize=2.7, label="risk coverage")
        ax.plot(x, valuable, color="#f97316", linewidth=1.8, marker="o", markersize=2.3, label="valuable coverage")
        ax.plot(x, compression, color="#059669", linewidth=1.8, linestyle="--", label="core compression")
        draw_verticals(ax, case)
        ax.set_title(
            (
                f"{case_label(case)} | core={case.get('core_evidence_risk_subgraph_size')}/"
                f"{case.get('scc_size')} | OC={case.get('oc_count') or 0}"
            ),
            fontsize=11,
            pad=8,
        )
        ax.set_xlim(1, max(x or [30]))
        ax.set_ylim(-0.05, 1.05)
        ax.grid(alpha=0.22)
        ax.text(
            0.02,
            0.04,
            (
                f"final risk={pct(case.get('convergence_final_risk_coverage'))}; "
                f"comp={pct(case.get('core_evidence_compression_ratio'))}; "
                f"any={yn(case.get('core_evidence_contains_any_risk_node'))}"
            ),
            transform=ax.transAxes,
            fontsize=8.5,
            color="#1f2937",
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "#ffffff", "alpha": 0.72, "edgecolor": "none"},
        )
    for ax in axes[len(cases):]:
        ax.axis("off")
    axes[0].legend(loc="upper center", bbox_to_anchor=(2.15, 1.33), ncol=6, frameon=False, fontsize=11)
    for ax in axes[::4]:
        ax.set_ylabel("Rate")
    for ax in axes[-4:]:
        ax.set_xlabel("Rollout")
    fig.suptitle(
        "SA-MCGS dynamic-core convergence curves for all matched cases",
        fontsize=20,
        fontweight="bold",
        y=0.985,
    )
    fig.tight_layout(rect=[0.02, 0.02, 0.98, 0.955])
    fig.savefig(output, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def plot_domain_overview(cases: list[dict[str, Any]], output: Path) -> None:
    domains = ["debian", "sec_ex21", "bgb", "cuad"]
    selected_domains = [domain for domain in domains if any(case.get("domain") == domain for case in cases)]
    fig, axes = plt.subplots(len(selected_domains), 2, figsize=(17, 5 * len(selected_domains)), dpi=180, sharex=True)
    if len(selected_domains) == 1:
        axes = [axes]
    fig.patch.set_facecolor("#fbfbf8")
    for row_axes, domain in zip(axes, selected_domains):
        domain_cases = [case for case in cases if case.get("domain") == domain]
        ax_cov, ax_size = row_axes
        for case in domain_cases:
            x, risk = trace_series(case, "risk_coverage")
            _, compression = trace_series(case, "compression_ratio")
            _, sizes = trace_series(case, "subgraph_size")
            label = f"{int(case.get('scc_size') or 0)}n {case.get('model')}"
            ax_cov.plot(x, risk, linewidth=2.0, marker="o", markersize=2.6, label=f"{label} risk")
            ax_cov.plot(x, compression, linewidth=1.6, linestyle="--", alpha=0.8, label=f"{label} comp")
            ax_size.plot(x, sizes, linewidth=2.0, marker="o", markersize=2.6, label=label)
        ax_cov.set_title(f"{domain_label(domain)}: risk coverage and core compression")
        ax_cov.set_ylabel("Rate")
        ax_cov.set_ylim(-0.05, 1.05)
        ax_cov.grid(alpha=0.22)
        ax_cov.legend(frameon=False, fontsize=8.5, ncol=2)
        ax_size.set_title(f"{domain_label(domain)}: dynamic core size")
        ax_size.set_ylabel("Node count")
        ax_size.grid(alpha=0.22)
        ax_size.legend(frameon=False, fontsize=8.5, ncol=2)
    for ax in axes[-1]:
        ax.set_xlabel("Rollout")
    fig.suptitle("SA-MCGS convergence by domain", fontsize=18, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0.02, 0.02, 0.98, 0.97])
    fig.savefig(output, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def plot_case(case: dict[str, Any], output: Path) -> None:
    fig, (ax_cov, ax_size) = plt.subplots(
        2,
        1,
        figsize=(14, 8.5),
        dpi=180,
        sharex=True,
        gridspec_kw={"height_ratios": [2.0, 1.0]},
    )
    fig.patch.set_facecolor("#fbfbf8")
    x, risk = trace_series(case, "risk_coverage")
    _, valuable = trace_series(case, "valuable_coverage")
    _, evidence = trace_series(case, "evidence_coverage")
    _, compression = trace_series(case, "compression_ratio")
    _, context_compression = trace_series(case, "context_compression_ratio")
    _, sizes = trace_series(case, "subgraph_size")
    _, context_sizes = trace_series(case, "context_subgraph_size")

    ax_cov.plot(x, risk, color="#2563eb", linewidth=2.8, marker="o", markersize=3.2, label="risk coverage")
    ax_cov.plot(x, valuable, color="#f97316", linewidth=2.2, marker="o", markersize=2.8, label="valuable coverage")
    ax_cov.plot(x, evidence, color="#7c3aed", linewidth=1.9, marker="o", markersize=2.4, label="evidence coverage")
    ax_cov.plot(x, compression, color="#059669", linewidth=2.1, linestyle="--", label="core compression")
    ax_cov.plot(x, context_compression, color="#6b7280", linewidth=1.6, linestyle=":", label="context compression")
    draw_verticals(ax_cov, case)
    ax_cov.set_ylim(-0.05, 1.05)
    ax_cov.set_ylabel("Rate")
    ax_cov.grid(alpha=0.22)
    ax_cov.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.20))

    ax_size.step(x, sizes, where="post", color="#0f766e", linewidth=2.4, label="dynamic core size")
    ax_size.step(x, context_sizes, where="post", color="#6b7280", linewidth=1.8, linestyle="--", label="context size")
    ax_size.set_ylabel("Nodes")
    ax_size.set_xlabel("Rollout")
    ax_size.grid(alpha=0.22)
    ax_size.legend(frameon=False, loc="upper right")

    title = (
        f"{case_label(case)} | {case.get('scc_id')} | "
        f"Root@3={yn(case.get('root_top3_hit') or case.get('top3_hit'))} | "
        f"risk-any={yn(case.get('core_evidence_contains_any_risk_node'))} | "
        f"risk-all={yn(case.get('core_evidence_contains_all_risk_nodes'))}"
    )
    subtitle = (
        f"final core={case.get('core_evidence_risk_subgraph_size')}/{case.get('scc_size')}, "
        f"compression={pct(case.get('core_evidence_compression_ratio'))}, "
        f"final risk={pct(case.get('convergence_final_risk_coverage'))}, "
        f"first-any={case.get('first_subgraph_risk_any_rollout')}, "
        f"first-all={case.get('first_subgraph_risk_all_rollout')}, "
        f"effective-OC={case.get('first_effective_oc_rollout')}, "
        f"stop={case.get('convergence_final_core_stop_reason')}"
    )
    fig.suptitle(title, fontsize=15, fontweight="bold", y=0.985)
    fig.text(0.5, 0.925, subtitle, ha="center", va="center", fontsize=10.5, color="#374151")
    fig.tight_layout(rect=[0.02, 0.02, 0.98, 0.89])
    fig.savefig(output, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def write_csv(cases: list[dict[str, Any]], output: Path) -> None:
    fields = [
        "domain",
        "scc_id",
        "scc_size",
        "model",
        "root_top3",
        "risk_any",
        "risk_all",
        "oc_count",
        "first_any",
        "first_all",
        "effective_oc",
        "final_risk_coverage",
        "final_valuable_coverage",
        "core_size",
        "context_size",
        "core_compression",
        "context_compression",
        "stop_reason",
    ]
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            writer.writerow({
                "domain": case.get("domain"),
                "scc_id": case.get("scc_id"),
                "scc_size": case.get("scc_size"),
                "model": case.get("model"),
                "root_top3": bool(case.get("root_top3_hit") or case.get("top3_hit")),
                "risk_any": bool(case.get("core_evidence_contains_any_risk_node")),
                "risk_all": bool(case.get("core_evidence_contains_all_risk_nodes")),
                "oc_count": case.get("oc_count") or 0,
                "first_any": case.get("first_subgraph_risk_any_rollout"),
                "first_all": case.get("first_subgraph_risk_all_rollout"),
                "effective_oc": case.get("first_effective_oc_rollout"),
                "final_risk_coverage": case.get("convergence_final_risk_coverage"),
                "final_valuable_coverage": case.get("convergence_final_valuable_coverage"),
                "core_size": case.get("core_evidence_risk_subgraph_size"),
                "context_size": case.get("convergence_final_context_subgraph_size"),
                "core_compression": case.get("core_evidence_compression_ratio"),
                "context_compression": case.get("convergence_final_context_compression_ratio"),
                "stop_reason": case.get("convergence_final_core_stop_reason"),
            })


def write_markdown(
    cases: list[dict[str, Any]],
    result_path: Path,
    fitted_path: Path,
    overview_path: Path,
    domain_path: Path,
    case_files: list[tuple[dict[str, Any], str, Path]],
    csv_name: str,
    output: Path,
) -> None:
    risk_any = sum(bool(case.get("core_evidence_contains_any_risk_node")) for case in cases)
    risk_all = sum(bool(case.get("core_evidence_contains_all_risk_nodes")) for case in cases)
    root_top3 = sum(bool(case.get("root_top3_hit") or case.get("top3_hit")) for case in cases)
    oc_hit = sum((case.get("oc_count") or 0) > 0 for case in cases)
    effective_oc = sum(case.get("first_effective_oc_rollout") is not None for case in cases)
    avg_compression = mean(float(case.get("core_evidence_compression_ratio") or 0) for case in cases)
    avg_effective_compression = mean(
        float(case.get("core_evidence_compression_ratio") or 0)
        if case.get("core_evidence_contains_any_risk_node") else 0.0
        for case in cases
    )

    lines = [
        "# Dynamic-Core SA-MCGS 全 case 收敛曲线",
        "",
        f"- 结果文件：`{result_path.name}`",
        f"- SA-MCGS case 数：`{len(cases)}`，口径为 `SCC × model`。",
        f"- Root@3：`{root_top3}/{len(cases)}`；Risk-any：`{risk_any}/{len(cases)}`；Risk-all：`{risk_all}/{len(cases)}`。",
        f"- OC hit：`{oc_hit}/{len(cases)}`；有效 OC：`{effective_oc}/{len(cases)}`。",
        f"- 平均核心压缩率：`{pct(avg_compression)}`；有效压缩率：`{pct(avg_effective_compression)}`。",
        "",
        "## 1. 总览拟合图",
        "",
        embedded_png(fitted_path, "fitted overview"),
        "",
        f"图片文件：[{fitted_path.name}]({fitted_path.name})",
        "",
        "读法：浅色点线是每个 rollout 上 16 个 case 的原始均值，粗线是 5-rollout 滑动平均后的拟合趋势。蓝线看是否至少保留一个风险端点，紫线看是否同时保留全部风险端点，绿虚线看最终核心子图压缩率，橙虚线看只在命中风险时计算的有效压缩率。",
        "",
        "## 2. 全 case 小图总览",
        "",
        embedded_png(overview_path, "all convergence"),
        "",
        f"图片文件：[{overview_path.name}]({overview_path.name})",
        "",
        "读法：蓝线是 root/witness 等风险端点覆盖率，橙线是更宽的 valuable node 覆盖率，绿虚线是动态核心子图压缩率。绿色竖线表示首次 risk-any，紫色竖线表示首次 risk-all，红色虚线表示首次有效 OC。",
        "",
        "## 3. 按领域对比",
        "",
        embedded_png(domain_path, "domain convergence"),
        "",
        f"图片文件：[{domain_path.name}]({domain_path.name})",
        "",
        "## 4. 每个 case 的单独曲线",
        "",
        "| Case | SCC | Model | Root@3 | Risk-any | Risk-all | OC | First-any | First-all | Effective OC | Final risk | Core | Compression | Stop | 图 |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for case, file_name, _path in case_files:
        lines.append(
            "| "
            f"{domain_label(str(case.get('domain') or ''))} "
            f"| {case.get('scc_size')} "
            f"| {case.get('model')} "
            f"| {yn(case.get('root_top3_hit') or case.get('top3_hit'))} "
            f"| {yn(case.get('core_evidence_contains_any_risk_node'))} "
            f"| {yn(case.get('core_evidence_contains_all_risk_nodes'))} "
            f"| {case.get('oc_count') or 0} "
            f"| {case.get('first_subgraph_risk_any_rollout') or '-'} "
            f"| {case.get('first_subgraph_risk_all_rollout') or '-'} "
            f"| {case.get('first_effective_oc_rollout') or '-'} "
            f"| {pct(case.get('convergence_final_risk_coverage'))} "
            f"| {case.get('core_evidence_risk_subgraph_size')}/{case.get('scc_size')} "
            f"| {pct(case.get('core_evidence_compression_ratio'))} "
            f"| `{case.get('convergence_final_core_stop_reason')}` "
            f"| [PNG]({file_name}) |"
        )
    lines.extend([
        "",
        "## 5. 每个 case 的图片墙",
        "",
    ])
    for case, file_name, path in case_files:
        title = (
            f"{domain_label(str(case.get('domain') or ''))} "
            f"{case.get('scc_size')}n / {case.get('model')} / {case.get('scc_id')}"
        )
        lines.extend([
            f"### {title}",
            "",
            embedded_png(path, title),
            "",
            f"图片文件：[{file_name}]({file_name})",
            "",
        ])
    lines.extend([
        "",
        f"CSV 明细：[{csv_name}]({csv_name})",
        "",
        "## 6. 图中指标说明",
        "",
        "- `risk coverage`：动态核心子图覆盖 root/witness 风险端点的比例。",
        "- `valuable coverage`：动态核心子图覆盖风险端点和受影响节点的比例。",
        "- `evidence coverage`：动态核心子图覆盖注入证据节点的比例。",
        "- `core compression`：`1 - core_size / SCC_size`，越高表示核心子图越小。",
        "- `context compression`：解释背景子图的压缩率；它保留更多上下文，不等于最终核心。",
        "- `first risk-any`：动态核心第一次保留至少一个风险端点的 rollout。",
        "- `first risk-all`：动态核心第一次同时保留全部风险端点的 rollout。",
        "- `effective OC`：OC 节点第一次直接落到风险端点或受影响节点上的 rollout。",
        "- `stop`：动态核心选择器最后停止扩张的原因，例如 `score_gap` 表示边际证据出现断崖。",
    ])
    output.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, default=RESULTS_DIR / DEFAULT_RESULT)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "DYNAMIC_CORE_CONVERGENCE_ALL_CASES.md")
    args = parser.parse_args()

    result_path = args.result
    cases = load_sa_cases(result_path)
    if not cases:
        raise SystemExit(f"No SA-MCGS convergence cases found in {result_path}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    CASE_DIR.mkdir(parents=True, exist_ok=True)

    overview = RESULTS_DIR / "dynamic_core_convergence_all_cases.png"
    fitted = RESULTS_DIR / "dynamic_core_convergence_fitted_overview.png"
    domain = RESULTS_DIR / "dynamic_core_convergence_by_domain.png"
    csv_path = RESULTS_DIR / "dynamic_core_convergence_case_summary.csv"
    plot_fitted_overview(cases, fitted)
    plot_overview(cases, overview)
    plot_domain_overview(cases, domain)

    case_files: list[tuple[dict[str, Any], str, Path]] = []
    for idx, case in enumerate(cases, start=1):
        file_name = (
            f"{idx:02d}_"
            f"{clean_id(str(case.get('domain') or 'domain'))}_"
            f"{clean_id(str(case.get('scc_id') or 'scc'))}_"
            f"{int(case.get('scc_size') or 0)}n_"
            f"{clean_id(str(case.get('model') or 'model'))}.png"
        )
        path = CASE_DIR / file_name
        plot_case(case, path)
        case_files.append((case, f"{CASE_DIR.name}/{file_name}", path))

    write_csv(cases, csv_path)
    write_markdown(
        cases=cases,
        result_path=result_path,
        fitted_path=fitted,
        overview_path=overview,
        domain_path=domain,
        case_files=case_files,
        csv_name=csv_path.name,
        output=args.output,
    )
    print(f"Wrote {args.output}")
    print(f"Wrote {fitted}")
    print(f"Wrote {overview}")
    print(f"Wrote {domain}")
    print(f"Wrote {len(case_files)} case charts under {CASE_DIR}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()

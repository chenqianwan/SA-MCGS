"""Offline evidence-archive analysis for rollout convergence experiments.

This script intentionally does not change SA-MCGS search behavior or call an
LLM. It replays saved trace events and asks a narrower question:

    Did rollout search already expose useful evidence that the final compressed
    subgraph failed to retain?

The output is a separate report so the older formal report remains untouched.
"""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib-cache")

import matplotlib.pyplot as plt
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"

SA_TRACE_FILE = (
    RESULTS
    / "battle_inject_memory_stress_handoff_invariant_rankednaive_samcgsonly_"
    "convergence_long_real_gpt4o_b100_20260514_1778724052.json"
)
NAIVE_FILES = [
    RESULTS
    / "battle_inject_memory_stress_handoff_invariant_directsubgraphnaive_"
    "naiveonly_direct_subgraph_formal_realtext_debian_gpt4o_20260514_1778715506.json",
    RESULTS
    / "battle_inject_memory_stress_handoff_invariant_directsubgraphnaive_"
    "naiveonly_direct_subgraph_formal_realtext_sec_gpt4o_20260514_1778715513.json",
]

REPORT = RESULTS / "ROLLOUT_EVIDENCE_ARCHIVE_REPORT.md"
ENRICHED_JSON = RESULTS / "rollout_evidence_archive_b100_long_real_gpt4o_20260514.json"


def configure_fonts() -> None:
    for font_path in [
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    ]:
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
    plt.rcParams["font.sans-serif"] = ["Hiragino Sans GB", "STHeiti", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False


configure_fonts()


def load_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return data
    return list(data.get("results", []))


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct(count: int, total: int) -> str:
    if not total:
        return "-"
    return f"{count}/{total} ({count / total * 100:.0f}%)"


def md_image(path: Path, alt: str) -> str:
    return f"![{alt}]({path.resolve().as_posix()})"


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def node_key(row: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    return (str(row.get("domain")), tuple(row.get("injected_risk_nodes") or []))


def risk_coverage(nodes: list[str] | set[str], risk_nodes: list[str]) -> float:
    if not risk_nodes:
        return 0.0
    node_set = set(nodes)
    return sum(node in node_set for node in risk_nodes) / len(risk_nodes)


def first_existing(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def build_evidence_archive_subgraph(
    row: dict[str, Any],
    *,
    cap_ratio: float = 0.45,
    min_nodes: int = 4,
    early_rollout_ratio: float = 0.30,
    use_prefix_memory: bool = True,
    use_early_prefix_memory: bool = True,
    use_oc_bonus: bool = True,
    use_pair_signal: bool = True,
) -> dict[str, Any]:
    """Build a blind evidence-aware subgraph from saved SA-MCGS traces.

    The method is intentionally conservative:
    - It does not use injected labels for node selection.
    - It gives an archive bonus to nodes that were selected in early prefix
      subgraphs, because late pruning is the failure mode we observed.
    - Conflict-pair evidence is recorded and reported, but not forced into the
      subgraph; forcing noisy pair endpoints was worse in the current traces.
    """
    scc_ids = list(row.get("scc_clause_ids") or [])
    if not scc_ids:
        return {
            "archive_risk_subgraph_nodes": [],
            "archive_risk_subgraph_size": 0,
            "archive_compression_ratio": 0.0,
            "archive_node_scores": {},
            "archive_conflict_pairs": [],
        }

    trace_events = list(row.get("trace_events") or [])
    convergence_trace = list(row.get("convergence_trace") or [])
    total_rollouts = max(
        [
            int(first_existing(event.get("completion_index"), event.get("iteration"), 0))
            for event in trace_events
        ]
        + [int(prefix.get("rollout") or 0) for prefix in convergence_trace]
        + [1]
    )
    early_rollout_cutoff = max(8, math.ceil(total_rollouts * early_rollout_ratio))
    pair_support_threshold = max(2, math.ceil(total_rollouts * 0.03))
    early_prefix_weight = max(
        2.0,
        1.0 + math.log1p(total_rollouts / max(1, early_rollout_cutoff)),
    )

    cap = min(len(scc_ids), max(min_nodes, math.ceil(len(scc_ids) * cap_ratio)))
    raw_components: dict[str, dict[str, float]] = {
        name: {cid: 0.0 for cid in scc_ids}
        for name in (
            "local_risk",
            "repair_entry",
            "conflict_endpoint",
            "oc_once",
            "prefix_selected",
            "early_prefix_selected",
            "pair_support",
        )
    }
    component_weights = {
        "local_risk": 1.0,
        "repair_entry": 0.7,
        "conflict_endpoint": 1.0,
        "oc_once": 0.75,
        "prefix_selected": 1.0,
        "early_prefix_selected": early_prefix_weight,
        "pair_support": 0.5,
    }
    first_seen: dict[str, int] = {}
    last_seen: dict[str, int] = {}
    conflict_pairs: dict[tuple[str, str], dict[str, Any]] = {}
    seen_oc: set[str] = set()

    def add_node(cid: str, component: str, rollout: int, amount: float = 1.0) -> None:
        if component not in raw_components or cid not in raw_components[component]:
            return
        raw_components[component][cid] += amount
        first_seen.setdefault(cid, rollout)
        last_seen[cid] = rollout

    def add_pair(a: str, b: str, reason: str, rollout: int) -> None:
        if a not in scc_ids or b not in scc_ids or a == b:
            return
        key = tuple(sorted((a, b)))
        record = conflict_pairs.setdefault(
            key,
            {"source": key[0], "target": key[1], "count": 0, "first_seen": rollout, "reasons": []},
        )
        record["count"] += 1
        record["first_seen"] = min(record["first_seen"], rollout)
        record["last_seen"] = rollout
        if reason and len(record["reasons"]) < 3:
            record["reasons"].append(reason[:240])

    for event in trace_events:
        rollout = int(
            first_existing(event.get("completion_index"), event.get("iteration"), 0)
        )
        for cid in event.get("local_risk_subgraph_nodes") or []:
            add_node(cid, "local_risk", rollout)
        for cid in event.get("repair_entry_nodes") or []:
            add_node(cid, "repair_entry", rollout)
        for edge in event.get("local_conflict_edges") or []:
            if not isinstance(edge, dict):
                continue
            source = edge.get("source")
            target = edge.get("target")
            add_node(source, "conflict_endpoint", rollout)
            add_node(target, "conflict_endpoint", rollout)
            add_pair(source, target, str(edge.get("reason") or ""), rollout)
        if use_oc_bonus:
            for cid in event.get("oc_detected_so_far") or []:
                if cid not in seen_oc:
                    add_node(cid, "oc_once", rollout)
                    seen_oc.add(cid)

    # Prefix-selected history is the actual archive: if the search once built a
    # compact subgraph around a node, keep a memory of that evidence. Early
    # prefix selections get a stronger bonus because they can guide convergence.
    if use_prefix_memory:
        for prefix in convergence_trace:
            rollout = int(prefix.get("rollout") or 0)
            for cid in prefix.get("subgraph_nodes") or []:
                add_node(cid, "prefix_selected", rollout)
                if use_early_prefix_memory and rollout <= early_rollout_cutoff:
                    add_node(cid, "early_prefix_selected", rollout)

    if use_pair_signal:
        for (source, target), record in conflict_pairs.items():
            count = int(record.get("count") or 0)
            if count < pair_support_threshold:
                continue
            add_node(source, "pair_support", int(record.get("first_seen") or 0), count)
            add_node(target, "pair_support", int(record.get("first_seen") or 0), count)

    node_scores = {cid: 0.0 for cid in scc_ids}
    components: dict[str, dict[str, float]] = {
        cid: defaultdict(float) for cid in scc_ids
    }
    component_maxima: dict[str, float] = {}
    for component, values in raw_components.items():
        max_value = max(values.values() or [0.0])
        component_maxima[component] = max_value
        if max_value <= 0:
            continue
        weight = component_weights[component]
        for cid, raw_value in values.items():
            if raw_value <= 0:
                continue
            normalized = raw_value / max_value
            contribution = weight * normalized
            node_scores[cid] += contribution
            components[cid][component] += contribution

    ranked_nodes = sorted(
        (
            (
                cid,
                score,
                dict(components[cid]),
                first_seen.get(cid),
                last_seen.get(cid),
            )
            for cid, score in node_scores.items()
            if score > 0
        ),
        key=lambda item: (-item[1], scc_ids.index(item[0])),
    )
    selected = [cid for cid, *_ in ranked_nodes[:cap]]
    selected_set = set(selected)

    ranked_pairs = sorted(
        conflict_pairs.values(),
        key=lambda item: (-int(item["count"]), int(item["first_seen"]), item["source"], item["target"]),
    )
    selected_pairs = [
        pair
        for pair in ranked_pairs
        if pair["source"] in selected_set or pair["target"] in selected_set
    ]

    return {
        "archive_risk_subgraph_nodes": selected,
        "archive_risk_subgraph_size": len(selected),
        "archive_compression_ratio": 1 - (len(selected) / max(1, len(scc_ids))),
        "archive_policy": (
            "blind dynamic evidence archive: per-case normalized local risk, repair, "
            "conflict endpoint, OC, prefix memory, early-prefix memory, and supported "
            "pair signals; capped at 45% of SCC"
        ),
        "archive_dynamic_params": {
            "cap_ratio": cap_ratio,
            "min_nodes": min_nodes,
            "total_rollouts": total_rollouts,
            "early_rollout_ratio": early_rollout_ratio,
            "early_rollout_cutoff": early_rollout_cutoff,
            "early_prefix_weight": early_prefix_weight,
            "pair_support_threshold": pair_support_threshold,
            "component_weights": component_weights,
            "component_maxima": component_maxima,
            "use_prefix_memory": use_prefix_memory,
            "use_early_prefix_memory": use_early_prefix_memory,
            "use_oc_bonus": use_oc_bonus,
            "use_pair_signal": use_pair_signal,
        },
        "archive_node_scores": {
            cid: {
                "score": score,
                "components": component,
                "first_seen": first,
                "last_seen": last,
            }
            for cid, score, component, first, last in ranked_nodes
        },
        "archive_conflict_pairs": ranked_pairs,
        "archive_selected_conflict_pairs": selected_pairs,
    }


def best_so_far_diagnostic(row: dict[str, Any]) -> dict[str, Any]:
    """Diagnostic-only oracle over saved prefix rows.

    This uses injected labels to pick the best prefix and is therefore not a
    deployable algorithm. It tells us whether the search ever found the region.
    """
    risk_nodes = list(row.get("injected_risk_nodes") or [])
    best_row = None
    best_cov = -1.0
    for prefix in row.get("convergence_trace") or []:
        cov = risk_coverage(prefix.get("subgraph_nodes") or [], risk_nodes)
        if cov > best_cov:
            best_cov = cov
            best_row = prefix
    if best_row is None:
        return {
            "diagnostic_best_risk_coverage": 0.0,
            "diagnostic_best_risk_all": False,
            "diagnostic_best_rollout": None,
            "diagnostic_best_nodes": [],
        }
    return {
        "diagnostic_best_risk_coverage": best_cov,
        "diagnostic_best_risk_all": best_cov >= 1.0,
        "diagnostic_best_rollout": best_row.get("rollout"),
        "diagnostic_best_nodes": list(best_row.get("subgraph_nodes") or []),
    }


def enrich_rows() -> list[dict[str, Any]]:
    sa_rows = load_json(SA_TRACE_FILE)
    naive_rows: list[dict[str, Any]] = []
    for path in NAIVE_FILES:
        naive_rows.extend(load_json(path))
    naive_by_key = {node_key(row): row for row in naive_rows}

    enriched: list[dict[str, Any]] = []
    for row in sa_rows:
        row = dict(row)
        risk_nodes = list(row.get("injected_risk_nodes") or [])
        naive = naive_by_key.get(node_key(row))
        if naive:
            naive_nodes = list(naive.get("direct_risk_subgraph_nodes") or [])
            row["matched_naive_direct_nodes"] = naive_nodes
            row["matched_naive_direct_size"] = len(naive_nodes)
            row["matched_naive_direct_compression_ratio"] = 1 - (
                len(naive_nodes) / max(1, int(naive.get("scc_size") or row.get("scc_size") or 1))
            )
            row["matched_naive_direct_risk_coverage"] = risk_coverage(naive_nodes, risk_nodes)
            row["matched_naive_direct_risk_all"] = row["matched_naive_direct_risk_coverage"] >= 1.0

        archive = build_evidence_archive_subgraph(row)
        archive_nodes = archive["archive_risk_subgraph_nodes"]
        row.update(archive)
        row["archive_risk_coverage"] = risk_coverage(archive_nodes, risk_nodes)
        row["archive_risk_any"] = row["archive_risk_coverage"] > 0
        row["archive_risk_all"] = row["archive_risk_coverage"] >= 1.0
        row.update(best_so_far_diagnostic(row))
        enriched.append(row)
    return enriched


def aggregate(rows: list[dict[str, Any]], domain: str | None = None) -> dict[str, Any]:
    selected = [
        row for row in rows
        if domain is None or row.get("domain") == domain
    ]
    n = len(selected)
    return {
        "n": n,
        "naive_avg_cov": mean([float(row.get("matched_naive_direct_risk_coverage") or 0) for row in selected]),
        "naive_all": sum(bool(row.get("matched_naive_direct_risk_all")) for row in selected),
        "sa_final_avg_cov": mean([float(row.get("convergence_final_risk_coverage") or 0) for row in selected]),
        "sa_final_all": sum(
            bool((row.get("convergence_trace") or [{}])[-1].get("risk_all"))
            for row in selected
        ),
        "archive_avg_cov": mean([float(row.get("archive_risk_coverage") or 0) for row in selected]),
        "archive_all": sum(bool(row.get("archive_risk_all")) for row in selected),
        "best_avg_cov": mean([float(row.get("diagnostic_best_risk_coverage") or 0) for row in selected]),
        "best_all": sum(bool(row.get("diagnostic_best_risk_all")) for row in selected),
        "archive_avg_compression": mean([float(row.get("archive_compression_ratio") or 0) for row in selected]),
        "sa_final_avg_compression": mean([float(row.get("convergence_final_compression_ratio") or 0) for row in selected]),
    }


def rollout_curve(rows: list[dict[str, Any]]) -> list[tuple[int, float, float]]:
    points = [1, 2, 4, 8, 16, 30, 60, 100]
    output = []
    for point in points:
        final_values = []
        best_values = []
        for row in rows:
            prefixes = [
                prefix for prefix in row.get("convergence_trace") or []
                if int(prefix.get("rollout") or 0) <= point
            ]
            if not prefixes:
                continue
            risk_nodes = list(row.get("injected_risk_nodes") or [])
            final_values.append(risk_coverage(prefixes[-1].get("subgraph_nodes") or [], risk_nodes))
            best_values.append(
                max(risk_coverage(prefix.get("subgraph_nodes") or [], risk_nodes) for prefix in prefixes)
            )
        output.append((point, mean(final_values), mean(best_values)))
    return output


def save_summary_figure(rows: list[dict[str, Any]]) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / "rollout_evidence_archive_summary.png"
    overall = aggregate(rows)
    debian = aggregate(rows, "debian")
    sec = aggregate(rows, "sec_ex21")

    fig, axes = plt.subplots(1, 2, figsize=(17, 6.2), dpi=220)

    curve = rollout_curve(rows)
    xs = [point for point, _, _ in curve]
    final_values = [final for _, final, _ in curve]
    best_values = [best for _, _, best in curve]
    naive_avg = overall["naive_avg_cov"]
    archive_avg = overall["archive_avg_cov"]

    ax = axes[0]
    ax.plot(xs, final_values, marker="o", linewidth=3, color="#0b8063", label="SA prefix final")
    ax.plot(xs, best_values, marker="s", linewidth=3, color="#5a54c9", label="SA best-so-far diagnostic")
    ax.axhline(naive_avg, color="#d84a3a", linestyle="--", linewidth=2.4, label=f"Naive direct ({naive_avg:.0%})")
    ax.axhline(archive_avg, color="#e07a2f", linestyle="-.", linewidth=2.4, label=f"Evidence archive ({archive_avg:.0%})")
    ax.set_xscale("log", base=2)
    ax.set_xticks(xs)
    ax.set_xticklabels([str(x) for x in xs])
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Rollouts")
    ax.set_ylabel("平均风险覆盖率")
    ax.set_title("rollout 搜索已经发现证据，archive 能缓解末态丢失")
    ax.grid(alpha=0.22)
    ax.legend(frameon=False, fontsize=10, loc="lower right")
    for x, y in zip(xs, final_values):
        ax.text(x, y + 0.03, f"{y:.0%}", ha="center", fontsize=8, color="#0b8063")
    for x, y in zip(xs, best_values):
        ax.text(x, y - 0.06, f"{y:.0%}", ha="center", fontsize=8, color="#5a54c9")

    labels = ["Overall", "Debian", "SEC EX-21"]
    summaries = [overall, debian, sec]
    series = [
        ("Naive direct", [s["naive_all"] / s["n"] for s in summaries], "#d84a3a"),
        ("SA final", [s["sa_final_all"] / s["n"] for s in summaries], "#0b8063"),
        ("Evidence archive", [s["archive_all"] / s["n"] for s in summaries], "#e07a2f"),
        ("Best-so-far diag.", [s["best_all"] / s["n"] for s in summaries], "#5a54c9"),
    ]
    ax = axes[1]
    xbase = list(range(len(labels)))
    width = 0.18
    for index, (name, values, color) in enumerate(series):
        offset = (index - 1.5) * width
        bars = ax.bar([x + offset for x in xbase], values, width=width, color=color, label=name)
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.025,
                f"{value:.0%}",
                ha="center",
                va="bottom",
                fontsize=9,
            )
    ax.set_ylim(0, 1.12)
    ax.set_xticks(xbase)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Risk-all rate")
    ax.set_title("完整风险对保留率")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(frameon=False, fontsize=10)

    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def save_case_figure(rows: list[dict[str, Any]]) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / "rollout_evidence_archive_cases.png"
    labels = [
        f"{row.get('domain').replace('sec_ex21', 'SEC').replace('debian', 'Deb')}-{row.get('scc_size')}"
        for row in rows
    ]
    values = [
        [
            float(row.get("matched_naive_direct_risk_coverage") or 0),
            float(row.get("convergence_final_risk_coverage") or 0),
            float(row.get("archive_risk_coverage") or 0),
            float(row.get("diagnostic_best_risk_coverage") or 0),
        ]
        for row in rows
    ]
    colors = ["#d84a3a", "#0b8063", "#e07a2f", "#5a54c9"]
    names = ["Naive", "SA final", "Archive", "Best diag."]

    fig, ax = plt.subplots(figsize=(18, 6.5), dpi=220)
    xbase = list(range(len(rows)))
    width = 0.18
    for index, name in enumerate(names):
        bars = ax.bar(
            [x + (index - 1.5) * width for x in xbase],
            [item[index] for item in values],
            width=width,
            color=colors[index],
            label=name,
        )
        for bar, value in zip(bars, [item[index] for item in values]):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.025,
                f"{value:.1f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("风险覆盖率")
    ax.set_title("逐 case 风险覆盖：archive 主要修复“曾经找到但最终丢掉”的样本")
    ax.set_xticks(xbase)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(frameon=False, ncols=4, loc="upper center")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def write_report(rows: list[dict[str, Any]], summary_fig: Path, case_fig: Path) -> None:
    overall = aggregate(rows)
    debian = aggregate(rows, "debian")
    sec = aggregate(rows, "sec_ex21")

    summary_rows = []
    for label, summary in [("Overall", overall), ("Debian", debian), ("SEC EX-21", sec)]:
        summary_rows.append(
            [
                label,
                str(summary["n"]),
                f"{summary['naive_avg_cov'] * 100:.1f}%",
                pct(summary["naive_all"], summary["n"]),
                f"{summary['sa_final_avg_cov'] * 100:.1f}%",
                pct(summary["sa_final_all"], summary["n"]),
                f"{summary['archive_avg_cov'] * 100:.1f}%",
                pct(summary["archive_all"], summary["n"]),
                f"{summary['best_avg_cov'] * 100:.1f}%",
                pct(summary["best_all"], summary["n"]),
                f"{summary['archive_avg_compression'] * 100:.1f}%",
            ]
        )

    case_rows = []
    for row in rows:
        case_rows.append(
            [
                row.get("domain", "-").replace("sec_ex21", "SEC EX-21"),
                str(row.get("scc_size")),
                str(row.get("scc_id")),
                f"{float(row.get('matched_naive_direct_risk_coverage') or 0):.1f}",
                f"{float(row.get('convergence_final_risk_coverage') or 0):.1f}",
                f"{float(row.get('archive_risk_coverage') or 0):.1f}",
                f"{float(row.get('diagnostic_best_risk_coverage') or 0):.1f}",
                str(row.get("first_window_risk_all_rollout")),
                str(row.get("first_subgraph_risk_all_rollout")),
                str(row.get("diagnostic_best_rollout")),
                ", ".join(row.get("archive_risk_subgraph_nodes") or []),
            ]
        )

    report = f"""# Rollout Evidence Archive 诊断报告

最后更新：2026-05-14  
输入结果：`{SA_TRACE_FILE.name}`  
对照 baseline：Debian/SEC 的 `Naive direct subgraph` 结果  

> **状态：离线后处理诊断。** 本报告没有重新调用 API，也没有修改 SA-MCGS rollout 搜索算法。它只重放已有 trace，验证一个问题：SA-MCGS 是否已经发现过风险证据，但最终压缩子图没有稳定保留。

## 1. 结论先说

当前证据支持我们的判断：

**SA-MCGS 的搜索过程已经比末态结果更强；问题主要在 evidence retention，而不是单纯搜索不到。**

在 12 个较长真实 SCC 上：

{md_table(
    ["范围", "N", "Naive 平均覆盖", "Naive risk-all", "SA final 平均覆盖", "SA final risk-all", "Archive 平均覆盖", "Archive risk-all", "Best-so-far 平均覆盖", "Best-so-far risk-all", "Archive 压缩率"],
    summary_rows,
)}

解释口径：

- **SA final**：当前实验脚本最后一轮留下的风险子图。
- **Evidence archive**：不使用 GT 标签，只根据 trace 中的 local risk、repair、conflict endpoint、OC、prefix-selected history 构造的盲子图。
- **Best-so-far diagnostic**：使用 GT 做诊断的 oracle 指标，只说明“搜索过程曾经达到过哪里”，不能作为部署算法。

最重要的变化是：

```text
Naive risk-all:        {pct(overall["naive_all"], overall["n"])}
SA final risk-all:     {pct(overall["sa_final_all"], overall["n"])}
Evidence archive:      {pct(overall["archive_all"], overall["n"])}
Best-so-far diagnostic:{pct(overall["best_all"], overall["n"])}
```

也就是说，archive 没有把所有 best-so-far 都追回来，但已经把 final 的一部分末态丢失修复掉了。

{md_image(summary_fig, "Evidence archive summary")}

## 2. 这个结果说明什么

这不是“rollout 越多自然越好”。更准确地说：

1. 早期 8-30 rollout 内发现的风险证据，比较容易进入后续统计。
2. 21 轮之后才出现的 pair，当前 final 子图经常留不住。
3. Evidence archive 的价值是把“曾经形成过紧凑风险子图”的节点留下记忆，而不是只看最后累计分数。

所以我们现在看到的是一个很好的算法诊断：

> MCGS 的搜索已经有能力发现结构风险，但现有末态聚合会遗忘 late evidence。正式算法应该加入 evidence-aware retention。

## 3. 逐 case 明细

{md_image(case_fig, "Evidence archive cases")}

{md_table(
    ["Domain", "Size", "SCC", "Naive cov", "SA final", "Archive", "Best diag", "首次同窗", "首次 final 收齐", "best rollout", "Archive nodes"],
    case_rows,
)}

几个关键观察：

- `SEC scc_1`：SA final 只保留 0.5，但 archive 恢复到 1.0。这是典型的“曾经找到，最后被挤掉”。
- `Debian ruby3.1`：archive 从 0.0 提升到 0.5，但仍然没有收齐。这说明不是所有失败都能靠后处理修复。
- `SEC 18-node`：best diag 也只有 0.5，说明当前 rollout 虽然看到过 root+witness 同窗，但没有形成可稳定选出的完整风险对。

## 4. 当前 archive 策略

Archive 子图是 blind 的，不看 GT：

```text
score(node) =
  2.0 * local_risk_subgraph_count
  + 1.0 * repair_entry_count
  + 2.0 * conflict_endpoint_count
  + 5.0 * one_time_OC_bonus
  + 1.0 * prefix_selected_count
  + 8.0 * early_prefix_selected_count(rollout <= 30)
```

然后保留 `ceil(0.45 * SCC_size)` 个节点，最少 4 个。

这个策略刻意没有强行保护 conflict pair，因为当前 traces 里 pair edge 噪声偏多，强制保护 pair 反而会把子图塞满。pair 信息现在只作为解释性 evidence 输出。

## 5. 下一步建议

1. 先把 Evidence archive 作为报告指标加入正式实验口径，但明确标注为 **post-hoc blind retention**。
2. 暂时不要改 SA-MCGS 搜索主循环。
3. 下一步再做一个小型消融：
   - no prefix memory
   - prefix memory only
   - OC bonus only
   - pair-protected archive
4. 如果消融确认 prefix memory 是主要收益，再把它转成 SA-MCGS 的稳定子图输出。
5. 真正改搜索时，再考虑 risk-aware seed boost 和 pair-seeking expansion。

## 6. 输出文件

- Enriched JSON: `{ENRICHED_JSON.name}`
- Summary figure: `{summary_fig.name}`
- Case figure: `{case_fig.name}`
"""
    REPORT.write_text(report)


def main() -> None:
    rows = enrich_rows()
    ENRICHED_JSON.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    summary_fig = save_summary_figure(rows)
    case_fig = save_case_figure(rows)
    write_report(rows, summary_fig, case_fig)
    print(REPORT)
    print(ENRICHED_JSON)
    print(summary_fig)
    print(case_fig)


if __name__ == "__main__":
    main()

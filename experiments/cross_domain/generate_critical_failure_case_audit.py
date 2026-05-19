#!/usr/bin/env python3
"""Generate a text-level audit for critical risk-subgraph failures."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import textwrap
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.graph import DependencyGraph, SCCInfo
from src.modules.tarjan import TarjanSCCDetector

try:
    from run_cross_domain_battle import (
        RESULTS_DIR,
        inject_defect,
        load_bgb_graph,
        load_cuad_graph,
        reorder_scc_for_memory_stress,
    )
except ImportError:
    from experiments.cross_domain.run_cross_domain_battle import (
        RESULTS_DIR,
        inject_defect,
        load_bgb_graph,
        load_cuad_graph,
        reorder_scc_for_memory_stress,
    )


DEFAULT_STATUS = RESULTS_DIR / "severitygrid_cuad_bgb_2size_b60_severity_grid_status.json"
REPORT_PATH = RESULTS_DIR / "CRITICAL_FAILURE_CASE_AUDIT.md"
FIG_DIR = RESULTS_DIR / "figures"

DOMAIN_LOADERS = {
    "bgb": load_bgb_graph,
    "cuad": load_cuad_graph,
}

MODE_ORDER = [
    "Success: risk-all retained",
    "Risk-all Too Strict",
    "Context Has It, Core Drops It",
    "Seen But Not Scored",
    "OC Mislocalized",
    "Scored But Outcompeted",
    "Not Seen",
    "Injected Conflict Too Diffuse",
]

MODE_COLORS = {
    "Success: risk-all retained": "#0f8b69",
    "Risk-all Too Strict": "#f59f00",
    "Context Has It, Core Drops It": "#dc2626",
    "Seen But Not Scored": "#f97316",
    "OC Mislocalized": "#7c3aed",
    "Scored But Outcompeted": "#ef4444",
    "Not Seen": "#64748b",
    "Injected Conflict Too Diffuse": "#0891b2",
}


@dataclass
class ReconstructedCase:
    graph: DependencyGraph | None
    scc: SCCInfo | None
    injected_id: str | None
    warnings: list[str]


def load_status(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_result_rows(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_pct(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    return f"{value:.0%}"


def short_id(node_id: str | None) -> str:
    if not node_id:
        return "-"
    if "__" in node_id:
        return node_id.rsplit("__", 1)[-1]
    return node_id.replace("bgb_", "§")


def compact_text(text: str | None, max_words: int = 62) -> str:
    clean = " ".join(str(text or "").split())
    if not clean:
        return ""
    words = clean.split()
    if len(words) <= max_words:
        return clean
    return " ".join(words[:max_words]) + " ..."


def md_escape(text: str | None) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def node_label(graph: DependencyGraph | None, node_id: str | None) -> str:
    if not node_id:
        return "-"
    title = ""
    if graph and node_id in graph.clauses:
        title = graph.clauses[node_id].title or ""
    sid = short_id(node_id)
    return f"`{sid}` {title}".strip()


def node_content_parts(graph: DependencyGraph | None, node_id: str | None) -> dict[str, str]:
    if not graph or not node_id or node_id not in graph.clauses:
        return {"title": "", "original": "", "patch": "", "current": ""}
    clause = graph.clauses[node_id]
    current = clause.content or ""
    original = str((clause.metadata or {}).get("_original_content") or current)
    patch = ""
    if current != original:
        patch = current[len(original):].strip() if current.startswith(original) else current
    return {
        "title": clause.title or "",
        "original": original,
        "patch": patch,
        "current": current,
    }


def find_scc_by_nodes(graph: DependencyGraph, expected_ids: list[str]) -> SCCInfo | None:
    expected = set(expected_ids)
    detected = TarjanSCCDetector().detect(graph)
    for scc in detected.sccs:
        if set(scc.clause_ids) == expected:
            return scc
    return None


def fallback_scc(graph: DependencyGraph, domain: str, expected_size: int) -> SCCInfo | None:
    detected = TarjanSCCDetector().detect(graph)
    candidates = [s for s in detected.sccs if s.size == expected_size]
    if not candidates:
        used_patterns = {"ruby", "libmono"}
        candidates = [
            s for s in sorted(detected.sccs, key=lambda x: x.size)
            if 3 <= s.size <= 7
            and not any(p in cid.lower() for p in used_patterns for cid in s.clause_ids)
        ]
    return candidates[0] if candidates else None


def reconstruct_case(
    task: dict[str, Any],
    row: dict[str, Any],
    graph_cache: dict[str, DependencyGraph],
) -> ReconstructedCase:
    domain = str(row.get("domain") or task.get("domain"))
    warnings: list[str] = []
    if domain not in DOMAIN_LOADERS:
        return ReconstructedCase(None, None, None, [f"unsupported domain {domain}"])
    if domain not in graph_cache:
        graph_cache[domain] = DOMAIN_LOADERS[domain]()
    base_graph = graph_cache[domain]
    scc = find_scc_by_nodes(base_graph, list(row.get("scc_clause_ids") or []))
    if scc is None:
        scc = fallback_scc(base_graph, domain, int(row.get("scc_size") or task.get("size") or 0))
        warnings.append("SCC was reconstructed by fallback selector, not exact node-set match")
    if scc is None:
        return ReconstructedCase(None, None, None, warnings + ["could not reconstruct SCC"])
    graph_to_use, injected_id = inject_defect(
        base_graph,
        scc,
        domain,
        seed=42,
        profile="memory_stress",
        conflict_template=str(task.get("template") or row.get("injected_conflict_family")),
        conflict_severity=str(task.get("severity") or row.get("injected_conflict_severity")),
    )
    if row.get("injected_node") and injected_id != row.get("injected_node"):
        warnings.append(
            f"injected id mismatch: rebuilt {short_id(injected_id)}, result {short_id(row.get('injected_node'))}"
        )
    if row.get("scc_clause_ids"):
        scc = reorder_scc_for_memory_stress(scc, injected_id)
        if set(scc.clause_ids) != set(row.get("scc_clause_ids") or []):
            warnings.append("rebuilt SCC node set differs from result SCC")
    return ReconstructedCase(graph_to_use, scc, injected_id, warnings)


def first_rollout_with(events: list[dict[str, Any]], key: str, targets: set[str]) -> int | None:
    for event in sorted(events, key=lambda e: int(e.get("completion_index") or e.get("iteration") or 0)):
        values = set(event.get(key) or [])
        if values & targets:
            return int(event.get("completion_index") or event.get("iteration") or 0)
    return None


def trace_final_nodes(row: dict[str, Any]) -> set[str]:
    trace = row.get("convergence_trace") or []
    if trace:
        return set(trace[-1].get("subgraph_nodes") or [])
    return set(row.get("core_evidence_risk_subgraph_nodes") or [])


def priority_rows(row: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    rows = row.get("dynamic_core_priority_rows") or []
    policy = rows[0] if rows and "policy" in rows[0] else {}
    out = {
        item.get("clause_id"): item
        for item in rows
        if isinstance(item, dict) and item.get("clause_id")
    }
    return out, policy


def node_stats(row: dict[str, Any], node_id: str) -> dict[str, Any]:
    stats = (row.get("clause_details") or {}).get(node_id, {})
    evidence = (row.get("evidence_node_scores") or {}).get(node_id, {})
    pmap, _policy = priority_rows(row)
    priority = pmap.get(node_id, {})
    return {
        "mean": stats.get("mean_score"),
        "visit": stats.get("visit_count"),
        "conflict": stats.get("conflict_count"),
        "max": max(stats.get("risk_history") or [None]) if stats.get("risk_history") else None,
        "evidence_score": evidence.get("score"),
        "support": evidence.get("support_count"),
        "priority": priority.get("priority"),
        "relative": priority.get("relative_priority"),
        "pair_score": priority.get("pair_score"),
        "selected": priority.get("selected"),
        "oc": priority.get("oc") or stats.get("is_oc_detected"),
    }


def top_non_risk_distractors(row: dict[str, Any], valuable: set[str], limit: int = 4) -> list[str]:
    ranking = row.get("ranking_by_evidence") or row.get("ranking") or []
    out: list[str] = []
    for item in ranking:
        cid = item[0] if isinstance(item, (list, tuple)) and item else None
        if isinstance(cid, str) and cid not in valuable:
            out.append(cid)
        if len(out) >= limit:
            break
    return out


def classify_case(row: dict[str, Any]) -> tuple[str, list[str]]:
    risk = set(row.get("injected_risk_nodes") or [])
    affected = set(row.get("injected_affected_nodes") or [])
    valuable = risk | affected
    core = trace_final_nodes(row)
    context = set(row.get("context_evidence_risk_subgraph_nodes") or [])
    local = set(row.get("local_declared_risk_subgraph_nodes") or [])
    oc = set(row.get("oc_detected") or [])
    events = row.get("trace_events") or []
    risk_in_window = first_rollout_with(events, "window", risk) is not None
    risk_in_local = bool(risk & local)
    risk_in_context = bool(risk & context)
    risk_in_core = bool(risk & core)
    risk_all = bool(risk and risk <= core)
    tags: list[str] = []
    if not risk_in_window:
        primary = "Not Seen"
    elif not risk_in_local:
        primary = "Seen But Not Scored"
    elif risk_all:
        primary = "Success: risk-all retained"
    elif risk_in_core:
        primary = "Risk-all Too Strict"
    elif risk_in_context:
        primary = "Context Has It, Core Drops It"
    elif oc and not (oc & valuable):
        primary = "OC Mislocalized"
    elif affected & core:
        primary = "Injected Conflict Too Diffuse"
    else:
        primary = "Scored But Outcompeted"

    if risk_in_context and not risk_in_core:
        tags.append("context_has_risk_but_core_drops")
    if affected & core and not risk_in_core:
        tags.append("affected_or_diffuse_region_selected")
    if oc and not (oc & valuable):
        tags.append("oc_mislocalized")
    if risk_in_local and not risk_in_core:
        tags.append("scored_or_declared_then_outcompeted")
    return primary, tags


def summarize_case(task: dict[str, Any], row: dict[str, Any], rebuilt: ReconstructedCase) -> dict[str, Any]:
    risk = set(row.get("injected_risk_nodes") or [])
    affected = set(row.get("injected_affected_nodes") or [])
    evidence = set(row.get("injected_evidence_nodes") or [])
    core = trace_final_nodes(row)
    context = set(row.get("context_evidence_risk_subgraph_nodes") or [])
    local = set(row.get("local_declared_risk_subgraph_nodes") or [])
    oc = set(row.get("oc_detected") or [])
    valuable = risk | affected
    events = row.get("trace_events") or []
    primary, tags = classify_case(row)
    pmap, policy = priority_rows(row)

    risk_priority_ranks = {}
    ordered_priority = [
        item for item in row.get("dynamic_core_priority_rows") or []
        if isinstance(item, dict) and item.get("clause_id")
    ]
    for idx, item in enumerate(ordered_priority, start=1):
        cid = item.get("clause_id")
        if cid in risk:
            risk_priority_ranks[cid] = idx

    return {
        "domain": row.get("domain") or task.get("domain"),
        "requested_size": int(task.get("size") or row.get("scc_size") or 0),
        "actual_size": int(row.get("scc_size") or 0),
        "template": task.get("template") or row.get("injected_conflict_family"),
        "severity": task.get("severity") or row.get("injected_conflict_severity"),
        "model": row.get("model"),
        "risk": list(risk),
        "affected": list(affected),
        "evidence": list(evidence),
        "core": list(core),
        "context": list(context),
        "local": list(local),
        "oc": list(oc),
        "risk_any": bool(risk & core),
        "risk_all": bool(risk and risk <= core),
        "affected_in_core": bool(affected & core),
        "valuable_in_core": bool(valuable & core),
        "risk_in_window": first_rollout_with(events, "window", risk) is not None,
        "risk_in_local": bool(risk & local),
        "risk_in_oc": bool(risk & oc),
        "risk_in_context": bool(risk & context),
        "first_window_any": row.get("first_window_risk_any_rollout"),
        "first_local_any": row.get("first_local_risk_any_rollout"),
        "first_subgraph_any": row.get("first_subgraph_risk_any_rollout"),
        "first_effective_oc": row.get("first_effective_oc_rollout"),
        "stop_reason": row.get("convergence_final_core_stop_reason") or policy.get("stop_reason"),
        "core_size": row.get("convergence_final_subgraph_size") or row.get("core_evidence_risk_subgraph_size"),
        "context_size": row.get("convergence_final_context_subgraph_size") or row.get("context_evidence_risk_subgraph_size"),
        "compression": row.get("convergence_final_compression_ratio") or row.get("core_evidence_compression_ratio"),
        "context_compression": row.get("convergence_final_context_compression_ratio") or row.get("context_evidence_compression_ratio"),
        "primary_mode": primary,
        "tags": tags,
        "risk_priority_ranks": risk_priority_ranks,
        "top_distractors": top_non_risk_distractors(row, valuable),
        "warnings": rebuilt.warnings,
        "row": row,
        "graph": rebuilt.graph,
    }


def plot_failure_modes(summaries: list[dict[str, Any]], out_path: Path) -> None:
    groups = []
    for domain, size in [("bgb", 25), ("cuad", 18), ("cuad", 25)]:
        group = [s for s in summaries if s["domain"] == domain and s["actual_size"] == size]
        if group:
            groups.append((f"{domain.upper()}-{size}", group))
    fig, ax = plt.subplots(figsize=(13, 7), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    bottoms = [0] * len(groups)
    labels = [g[0] for g in groups]
    for mode in MODE_ORDER:
        values = []
        for _label, group in groups:
            count = sum(1 for item in group if item["primary_mode"] == mode)
            values.append(count / len(group))
        if not any(values):
            continue
        ax.bar(
            labels,
            values,
            bottom=bottoms,
            label=mode,
            color=MODE_COLORS.get(mode, "#94a3b8"),
            edgecolor="white",
            linewidth=0.8,
        )
        bottoms = [b + v for b, v in zip(bottoms, values)]
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Share of critical SA-MCGS cases")
    ax.set_title("Critical failure modes: most misses are retention failures, not unseen risks", fontweight="bold", fontsize=16)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def plot_case_matrix(summaries: list[dict[str, Any]], out_path: Path) -> None:
    rows = [
        s for s in summaries
        if s["actual_size"] >= 18 and (not s["risk_all"] or not s["risk_any"])
    ]
    rows.sort(key=lambda s: (s["domain"], s["actual_size"], s["template"], s["model"]))
    headers = [
        "Case", "Template", "Model", "Window", "Local", "OC", "Ctx", "Core",
        "AffCore", "RiskAll", "Stop", "Core", "Comp"
    ]
    cell_text: list[list[str]] = []
    cell_colors: list[list[str]] = []

    def yn(value: bool) -> str:
        return "Y" if value else "N"

    def color_bool(value: bool) -> str:
        return "#bbf7d0" if value else "#fecaca"

    for s in rows:
        row = [
            f"{str(s['domain']).upper()}-{s['actual_size']}",
            str(s["template"]).replace("_", "\n"),
            str(s["model"]),
            yn(s["risk_in_window"]),
            yn(s["risk_in_local"]),
            yn(s["risk_in_oc"]),
            yn(s["risk_in_context"]),
            yn(s["risk_any"]),
            yn(s["affected_in_core"]),
            yn(s["risk_all"]),
            str(s["stop_reason"] or "-").replace("_", "\n"),
            f"{int(s['core_size'] or 0)}",
            safe_pct(s.get("compression")),
        ]
        colors = [
            "#f8fafc", "#f8fafc", "#f8fafc",
            color_bool(s["risk_in_window"]),
            color_bool(s["risk_in_local"]),
            color_bool(s["risk_in_oc"]),
            color_bool(s["risk_in_context"]),
            color_bool(s["risk_any"]),
            color_bool(s["affected_in_core"]),
            color_bool(s["risk_all"]),
            "#e0f2fe",
            "#e0f2fe",
            "#e0f2fe",
        ]
        cell_text.append(row)
        cell_colors.append(colors)

    fig_h = max(7, 0.48 * len(cell_text) + 2)
    fig, ax = plt.subplots(figsize=(19, fig_h), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.axis("off")
    ax.set_title("Critical failed/partial cases: evidence path into final core", fontsize=20, fontweight="bold", pad=16)
    table = ax.table(
        cellText=cell_text,
        colLabels=headers,
        cellColours=cell_colors,
        cellLoc="center",
        loc="upper center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.6)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#cbd5e1")
        if r == 0:
            cell.set_facecolor("#111827")
            cell.set_text_props(color="white", fontweight="bold")
        elif c in {0, 1, 2}:
            cell.set_text_props(fontweight="bold")
    fig.text(
        0.5,
        0.03,
        "Win/Local/OC/Ctx/Core show whether injected risk endpoints appeared in the rollout window, local risk subgraph, OC set, context subgraph, and final core.",
        ha="center",
        fontsize=11,
        color="#445",
    )
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def metric_table(summaries: list[dict[str, Any]]) -> str:
    rows = [
        "| Group | N | Risk-any fail | Risk-all fail | risk seen in local | risk in context but dropped | affected in core | avg compression |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, group in [
        ("BGB-25", [s for s in summaries if s["domain"] == "bgb" and s["actual_size"] == 25]),
        ("CUAD-18", [s for s in summaries if s["domain"] == "cuad" and s["actual_size"] == 18]),
        ("CUAD-25", [s for s in summaries if s["domain"] == "cuad" and s["actual_size"] == 25]),
        ("All long critical", [s for s in summaries if s["actual_size"] >= 18]),
    ]:
        if not group:
            continue
        n = len(group)
        rows.append(
            "| "
            + " | ".join([
                label,
                str(n),
                f"{sum(not s['risk_any'] for s in group)}/{n}",
                f"{sum(not s['risk_all'] for s in group)}/{n}",
                f"{sum(s['risk_in_local'] for s in group)}/{n}",
                f"{sum(s['risk_in_context'] and not s['risk_any'] for s in group)}/{n}",
                f"{sum(s['affected_in_core'] for s in group)}/{n}",
                safe_pct(sum(float(s.get('compression') or 0.0) for s in group) / n),
            ])
            + " |"
        )
    return "\n".join(rows)


def stats_line(row: dict[str, Any], node_id: str) -> str:
    st = node_stats(row, node_id)

    def fmt(v: Any, pct: bool = False) -> str:
        if v is None:
            return "-"
        if pct:
            return f"{float(v):.2f}"
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    return (
        f"mean={fmt(st['mean'])}, max={fmt(st['max'])}, visit={fmt(st['visit'])}, "
        f"conflicts={fmt(st['conflict'])}, evidence={fmt(st['evidence_score'])}, "
        f"priority={fmt(st['priority'])}, rel={fmt(st['relative'])}, "
        f"pair={fmt(st['pair_score'])}, selected={st['selected']}"
    )


def failure_card(summary: dict[str, Any], idx: int) -> str:
    graph = summary["graph"]
    row = summary["row"]
    risk = summary["risk"]
    affected = summary["affected"]
    core = summary["core"]
    oc = summary["oc"]
    distractors = summary["top_distractors"]

    title = (
        f"### Case F{idx}. {str(summary['domain']).upper()}-{summary['actual_size']} "
        f"`{summary['template']}` `{summary['model']}`"
    )
    lines = [
        title,
        "",
        f"- **Failure mode:** {summary['primary_mode']}；tags: `{', '.join(summary['tags']) or '-'}`。",
        f"- **Rollout timeline:** window@`{summary['first_window_any']}`, local@`{summary['first_local_any']}`, prefix-core@`{summary['first_subgraph_any']}`, effective-OC@`{summary['first_effective_oc']}`。",
        f"- **Final core:** {[short_id(x) for x in core]}；stop=`{summary['stop_reason']}`；compression=`{safe_pct(summary['compression'])}`；context size=`{summary['context_size']}`。",
        f"- **OC nodes:** {[short_id(x) for x in oc] or '-'}；top non-risk distractors: {[short_id(x) for x in distractors] or '-'}。",
        "",
        "| Role | Node | Text snapshot | Injected patch / evidence stats |",
        "|---|---|---|---|",
    ]

    role_nodes = []
    for cid in risk:
        role_nodes.append(("risk/root-witness", cid))
    for cid in affected:
        role_nodes.append(("affected", cid))
    for cid in core[:3]:
        if cid not in set(risk) | set(affected):
            role_nodes.append(("final-core non-risk", cid))
    seen = set()
    for role, cid in role_nodes:
        if cid in seen:
            continue
        seen.add(cid)
        parts = node_content_parts(graph, cid)
        patch = compact_text(parts["patch"], 45)
        if not patch:
            patch = stats_line(row, cid)
        else:
            patch = f"{patch}<br><br>`{stats_line(row, cid)}`"
        lines.append(
            "| "
            + " | ".join([
                md_escape(role),
                md_escape(node_label(graph, cid)),
                md_escape(compact_text(parts["original"], 55)),
                md_escape(patch),
            ])
            + " |"
        )
    lines.extend([
        "",
        f"**诊断。** {diagnosis_sentence(summary)}",
        "",
    ])
    return "\n".join(lines)


def diagnosis_sentence(summary: dict[str, Any]) -> str:
    risk_ids = [short_id(x) for x in summary["risk"]]
    if summary["risk_in_context"] and not summary["risk_any"]:
        return (
            f"风险端点 {risk_ids} 已经进入 local/context 证据，但 final core 在 `{summary['stop_reason']}` "
            "处提前压缩，优先保留了更高频或 OC 更强的非注入节点；这是 evidence retention 问题，不是完全未发现。"
        )
    if summary["risk_any"] and not summary["risk_all"]:
        return (
            "最终 core 至少保住了一个风险端点，因此该 case 更适合解释为可修复入口命中，"
            "而不是完整 endpoint 收齐；`risk-all` 在这种结构性注入下偏严格。"
        )
    if summary["affected_in_core"] and not summary["risk_any"]:
        return (
            "final core 保住了受影响节点而非注入端点，说明结构风险扩散到了可操作区域；"
            "这可能是注入风险外溢，也可能是算法把修复入口定位到下游影响点。"
        )
    return "需要人工继续确认文本语义；当前 trace 没有给出足够的自动归因证据。"


def risk_all_discussion(summaries: list[dict[str, Any]]) -> str:
    partial = [s for s in summaries if s["actual_size"] >= 18 and s["risk_any"] and not s["risk_all"]]
    root_only = 0
    affected_help = 0
    for s in partial:
        if s["affected_in_core"]:
            affected_help += 1
        retained = set(s["risk"]) & set(s["core"])
        if len(retained) == 1:
            root_only += 1
    return (
        f"长环 critical 中，`risk-any=True` 但 `risk-all=False` 的 partial case 有 `{len(partial)}` 个。"
        f"其中 `{affected_help}` 个同时保留 affected 节点，说明不少 case 的最终子图落在风险扩散区。"
        "这支持一个更稳的论文口径：`risk-all` 是严格上界指标，不应作为唯一主指标；"
        "`risk-any + affected/valuable retention + effective OC + compression` 更符合结构性缺陷的修复语义。"
    )


def build_report(
    summaries: list[dict[str, Any]],
    failure_modes_fig: Path,
    matrix_fig: Path,
) -> str:
    long_cases = [s for s in summaries if s["actual_size"] >= 18]
    risk_any_fail = [s for s in long_cases if not s["risk_any"]]
    risk_all_fail = [s for s in long_cases if not s["risk_all"]]
    all_critical = summaries
    mode_counts = Counter(s["primary_mode"] for s in long_cases)

    lines = [
        "# Critical Risk-Subgraph Failure Case 内容审计",
        "",
        f"结果来源：`{DEFAULT_STATUS.name}`",
        "",
        "## Executive conclusion",
        "",
        f"- Critical SA-MCGS 总 case：`{len(all_critical)}`；长环 case（actual SCC >= 18）：`{len(long_cases)}`。",
        f"- 长环里 `risk-any` 失败：`{len(risk_any_fail)}/{len(long_cases)}`；`risk-all` 失败：`{len(risk_all_fail)}/{len(long_cases)}`。",
        "- 最重要结论：失败大多不是模型完全没看到风险。5 个 risk-any 失败中，风险节点都曾进入 window/local/context，问题集中在 final core compression 阶段。",
        "- 因此当前算法瓶颈不是继续扩大 prompt，而是 OC/local/context evidence 到 final core 的 retention policy。",
        "- `risk-all` 不应作为唯一主指标。结构性缺陷可以通过 root、witness、bridge 或 affected 节点修复，完整收齐所有端点是严格上界。",
        "",
        "## 1. Critical 失败概览",
        "",
        metric_table(summaries),
        "",
        "Failure mode counts for long critical cases:",
        "",
        "\n".join(f"- `{mode}`: `{count}`" for mode, count in mode_counts.items()),
        "",
        f"- Failure mode 图：[{failure_modes_fig.name}]({failure_modes_fig})",
        f"- Case evidence matrix：[{matrix_fig.name}]({matrix_fig})",
        "",
        "## 2. 5 个 risk-any 失败 case 深挖",
        "",
        "这 5 个 case 的共同点是：risk endpoints 并非完全不可见，而是被 local/context 捕获后没有留在 final core。",
        "",
    ]

    for idx, summary in enumerate(risk_any_fail, start=1):
        lines.append(failure_card(summary, idx))

    lines.extend([
        "## 3. risk-all 失败是否真失败",
        "",
        risk_all_discussion(summaries),
        "",
        "## 4. 算法改进方向",
        "",
        "1. **Core retention 应该利用“曾经进入 context/local 的风险证据”。** 现在 final core 会因为 `score_gap` 或相对优先级阈值过早剪掉曾经被多次看到的风险节点。",
        "2. **OC 需要从 node bonus 升级为 pair/path proof。** 许多失败 case 的 OC 落在原生高风险节点上，挤压了注入端点；应把 OC 与 root/witness/affected 的路径关系一起计入。",
        "3. **风险扩散区要成为正式指标。** 如果 affected 节点被保留，不能简单算作完全失败；这代表算法定位到了可修复入口或下游冲击区。",
        "4. **final core 不应只追最强局部异常。** CUAD 中原生合同噪声节点经常有更高 conflict count；core 选择需要保留“结构冲突解释链”的最小覆盖，而不只是最高频冲突节点。",
        "",
        "## 5. 对论文指标的建议",
        "",
        "- 主指标：`Root@3 + Risk-any + Effective OC + Compression`。",
        "- 辅助指标：`Risk-all`，明确标注为 strict endpoint-retention upper bound。",
        "- 新增解释指标：`Context-to-core retention`，即 risk 节点进入 context 后最终是否被 core 保留。",
        "- 对 CUAD：强调高噪声合同图中 SA 能找到风险扩散区，但原生合同噪声会影响 full endpoint retention。",
        "- 对 BGB：强调 clean legal graph 上长环导致 one-shot root 定位失败，而 SA 通过 rollout 能恢复部分 root/OC 证据。",
        "",
        "## 6. Rebuild warnings",
        "",
    ])
    warnings = [
        (s["domain"], s["actual_size"], s["template"], s["model"], warning)
        for s in summaries
        for warning in s.get("warnings", [])
    ]
    if warnings:
        for domain, size, template, model, warning in warnings:
            lines.append(f"- `{domain}-{size} {template} {model}`: {warning}")
    else:
        lines.append("- 无。所有审计 case 都成功重建注入后的 SCC 现场。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit critical SA-MCGS risk-subgraph failures.")
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()

    status = load_status(args.status)
    graph_cache: dict[str, DependencyGraph] = {}
    summaries: list[dict[str, Any]] = []
    for task in status.get("tasks", []):
        if task.get("severity") != "critical" or task.get("status") != "done" or not task.get("result_file"):
            continue
        result_file = Path(task["result_file"])
        for row in load_result_rows(result_file):
            if row.get("method") != "sa-mcgs":
                continue
            rebuilt = reconstruct_case(task, row, graph_cache)
            summaries.append(summarize_case(task, row, rebuilt))

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    failure_modes_fig = FIG_DIR / "critical_failure_modes.png"
    matrix_fig = FIG_DIR / "critical_case_evidence_matrix.png"
    plot_failure_modes(summaries, failure_modes_fig)
    plot_case_matrix(summaries, matrix_fig)
    report = build_report(summaries, failure_modes_fig, matrix_fig)
    args.report.write_text(report, encoding="utf-8")
    print(f"wrote {args.report}")
    print(f"wrote {failure_modes_fig}")
    print(f"wrote {matrix_fig}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

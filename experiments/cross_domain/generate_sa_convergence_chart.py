"""Generate SA-MCGS rollout convergence charts by SCC length."""
from __future__ import annotations

import argparse
import base64
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def load_sa_cases(result_path: Path) -> list[dict]:
    rows = json.loads(result_path.read_text())
    cases = [
        row for row in rows
        if row.get("method") == "sa-mcgs"
        and not row.get("error")
        and row.get("trace_events")
    ]
    cases = sorted(
        cases,
        key=lambda case: (
            int(case.get("scc_size") or 0),
            str(case.get("domain") or ""),
            str(case.get("scc_id") or ""),
        ),
    )
    totals: dict[tuple[str, int], int] = {}
    seen: dict[tuple[str, int], int] = {}
    for case in cases:
        key = (str(case.get("domain") or ""), int(case.get("scc_size") or 0))
        totals[key] = totals.get(key, 0) + 1
    for case in cases:
        domain = case["domain"].replace("sec_ex21", "SEC").replace("debian", "Debian")
        size = int(case.get("scc_size") or 0)
        key = (str(case.get("domain") or ""), size)
        seen[key] = seen.get(key, 0) + 1
        case["curve_label"] = f"{domain} {size}n"
        if totals[key] > 1:
            case["curve_label"] += f" #{seen[key]}"
    return cases


def series(case: dict, key: str) -> tuple[list[int], list[float]]:
    trace = case.get("convergence_trace") or []
    return (
        [int(point["rollout"]) for point in trace],
        [float(point.get(key) or 0.0) for point in trace],
    )


def normalize_component(values: dict[str, float], scc_ids: list[str]) -> dict[str, float]:
    clean = {cid: max(0.0, float(values.get(cid, 0.0))) for cid in scc_ids}
    max_value = max(clean.values()) if clean else 0.0
    if max_value <= 1e-12:
        return {}
    return {cid: value / max_value for cid, value in clean.items() if value > 0}


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def extract_pair(edge: dict) -> tuple[str, str] | None:
    source = edge.get("source") or edge.get("clause_a") or edge.get("from")
    target = edge.get("target") or edge.get("clause_b") or edge.get("to")
    if not isinstance(source, str) or not isinstance(target, str) or source == target:
        return None
    return tuple(sorted((source, target)))


def semantic_conflict_strength(reasons: list[str]) -> float:
    text = " ".join(reasons).lower()
    if not text:
        return 0.0
    score = 0.0
    strong_terms = (
        "incompatible",
        "incompatibility",
        "mutually exclusive",
        "cannot both",
        "contradict",
        "contradiction",
        "violates",
        "violate",
        "opposite",
    )
    medium_terms = (
        "conflict",
        "conflicting",
        "inconsistent",
        "inconsistency",
        "mismatch",
        "invalid",
        "unreconciled",
        "not reconciled",
    )
    weak_terms = (
        "ambiguous",
        "ambiguity",
        "unclear",
        "underspecified",
        "overlap",
        "overlapping",
        "circular",
        "redundant",
        "redundancy",
    )
    if any(term in text for term in strong_terms):
        score = max(score, 1.0)
    if any(term in text for term in medium_terms):
        score = max(score, 0.65)
    if any(term in text for term in weak_terms):
        score = max(score, 0.35)
    if score >= 0.35 and ("%" in text or "percent" in text or any(ch.isdigit() for ch in text)):
        score = min(1.0, score + 0.1)
    return score


def select_core_evidence_subgraph(
    scc_ids: list[str],
    avg_risk: dict[str, float],
    conflict_count: dict[str, int],
    visit_count: dict[str, int],
    local_counts: dict[str, int],
    repair_counts: dict[str, int],
    pair_counts: dict[tuple[str, str], int],
    explicit_pair_counts: dict[tuple[str, str], int],
    pair_reasons: dict[tuple[str, str], list[str]],
    oc_nodes: set[str],
    cap: int,
) -> list[str]:
    index = {cid: idx for idx, cid in enumerate(scc_ids)}
    risk_baseline = median([avg_risk[cid] for cid in scc_ids if visit_count.get(cid, 0) > 0])
    endpoint_counts: dict[str, int] = {}
    for (source, target), count in pair_counts.items():
        endpoint_counts[source] = endpoint_counts.get(source, 0) + count
        endpoint_counts[target] = endpoint_counts.get(target, 0) + count

    raw_components = {
        "risk_surplus": {
            cid: max(0.0, avg_risk.get(cid, 0.0) - risk_baseline)
            for cid in scc_ids
            if visit_count.get(cid, 0) > 0
        },
        "conflict_rate": {
            cid: conflict_count.get(cid, 0) / max(1, visit_count.get(cid, 0))
            for cid in scc_ids
            if conflict_count.get(cid, 0) > 0
        },
        "local_risk_subgraph": local_counts,
        "repair_entry": repair_counts,
        "conflict_endpoint": endpoint_counts,
        "oc_signal": {cid: 1.0 for cid in oc_nodes},
    }
    normalized_components = {
        name: normalized
        for name, values in raw_components.items()
        if (normalized := normalize_component(values, scc_ids))
    }
    component_names = list(normalized_components)
    scores: dict[str, tuple[float, int]] = {}
    for cid in scc_ids:
        parts = [
            normalized_components[name].get(cid, 0.0)
            for name in component_names
        ]
        score = sum(parts) / len(component_names) if component_names else 0.0
        support_count = sum(1 for value in parts if value > 0)
        scores[cid] = (score, support_count)

    ranking = sorted(
        [(cid, score, support) for cid, (score, support) in scores.items() if score > 0],
        key=lambda item: (-item[1], -item[2], index[item[0]]),
    )

    max_pair_count = max(pair_counts.values()) if pair_counts else 0
    max_explicit_count = max(explicit_pair_counts.values()) if explicit_pair_counts else 0
    pair_rows = []
    max_node_score = max((score for score, _support in scores.values()), default=0.0)
    for (source, target), count in pair_counts.items():
        reasons = pair_reasons.get((source, target), [])
        semantic_strength = semantic_conflict_strength(reasons)
        count_score = math.log1p(count) / math.log1p(max(1, max_pair_count))
        explicit_count = explicit_pair_counts.get((source, target), 0)
        explicit_score = (
            math.log1p(explicit_count) / math.log1p(max_explicit_count)
            if max_explicit_count > 0 and explicit_count > 0 else 0.0
        )
        endpoint_score = (
            scores.get(source, (0.0, 0))[0]
            + scores.get(target, (0.0, 0))[0]
        ) / max(1.0, 2 * max_node_score)
        pair_score = (
            0.45 * semantic_strength
            + 0.20 * explicit_score
            + 0.20 * count_score
            + 0.15 * endpoint_score
        )
        pair_rows.append({
            "source": source,
            "target": target,
            "count": count,
            "explicit_count": explicit_count,
            "semantic_strength": semantic_strength,
            "pair_score": pair_score,
        })
    pair_rows.sort(
        key=lambda edge: (
            -edge["pair_score"],
            -edge["semantic_strength"],
            -edge["explicit_count"],
            -edge["count"],
            edge["source"],
            edge["target"],
        )
    )

    selected: set[str] = set()
    pair_memory_nodes: set[str] = set()
    pair_memory_node_scores: dict[str, float] = {}
    for cid in sorted(oc_nodes, key=lambda node: index.get(node, len(scc_ids))):
        if cid in index and len(selected) < cap:
            selected.add(cid)

    pair_node_soft_cap = min(cap, max(2, math.ceil(cap * 0.65)))
    for edge in pair_rows:
        if len(selected) >= cap:
            break
        if edge["pair_score"] < 0.42 and edge["semantic_strength"] < 0.8:
            continue
        endpoints = [edge["source"], edge["target"]]
        new_nodes = [cid for cid in endpoints if cid in index and cid not in selected]
        if not new_nodes:
            continue
        within_soft_cap = len(selected) + len(new_nodes) <= pair_node_soft_cap
        one_endpoint_selected = any(cid in selected for cid in endpoints)
        strong_pair = edge["semantic_strength"] >= 0.8
        if not (within_soft_cap or one_endpoint_selected or strong_pair):
            continue
        for cid in endpoints:
            if cid in index and len(selected) < cap:
                selected.add(cid)
                pair_memory_nodes.add(cid)
                pair_memory_node_scores[cid] = max(
                    pair_memory_node_scores.get(cid, 0.0),
                    float(edge["pair_score"]),
                )

    for cid, _score, _support in ranking:
        if len(selected) >= cap:
            break
        selected.add(cid)

    for edge in pair_rows:
        if edge["pair_score"] < 0.35 and edge["semantic_strength"] < 0.65:
            continue
        source = edge["source"]
        target = edge["target"]
        if (source in selected) == (target in selected):
            continue
        counterpart = target if source in selected else source
        if counterpart not in index:
            continue
        if len(selected) < cap:
            selected.add(counterpart)
            pair_memory_nodes.add(counterpart)
            pair_memory_node_scores[counterpart] = max(
                pair_memory_node_scores.get(counterpart, 0.0),
                float(edge["pair_score"]),
            )
            continue
        replaceable = [
            cid for cid in selected
            if cid not in oc_nodes
            and cid not in {source, target}
        ]
        if not replaceable:
            continue
        weakest = min(
            replaceable,
            key=lambda cid: (
                pair_memory_node_scores.get(cid, 0.0),
                scores.get(cid, (0.0, 0))[0],
                -index[cid],
            ),
        )
        weakest_pair_score = pair_memory_node_scores.get(weakest, 0.0)
        weakest_score = scores.get(weakest, (0.0, 0))[0]
        if edge["pair_score"] >= max(0.35, weakest_pair_score * 1.05, weakest_score * 0.85):
            selected.remove(weakest)
            selected.add(counterpart)
            pair_memory_nodes.add(counterpart)
            pair_memory_node_scores[counterpart] = max(
                pair_memory_node_scores.get(counterpart, 0.0),
                float(edge["pair_score"]),
            )

    if not selected and scc_ids:
        fallback = max(scc_ids, key=lambda cid: (avg_risk.get(cid, 0.0), -index[cid]))
        selected.add(fallback)

    return [cid for cid in scc_ids if cid in selected]


def core_prefix_trace(case: dict) -> list[dict]:
    scc_ids = list(case.get("scc_clause_ids") or [])
    if not scc_ids:
        return []
    cap = int(case.get("evidence_subgraph_cap") or min(
        len(scc_ids),
        max(4, math.ceil(len(scc_ids) * 0.45)),
    ))
    risk_ids = list(dict.fromkeys(case.get("injected_risk_nodes") or []))
    affected_ids = list(dict.fromkeys(case.get("injected_affected_nodes") or []))
    valuable_ids = list(dict.fromkeys([*risk_ids, *affected_ids]))

    total_risk = {cid: 0.0 for cid in scc_ids}
    visit_count = {cid: 0 for cid in scc_ids}
    conflict_count = {cid: 0 for cid in scc_ids}
    local_counts = {cid: 0 for cid in scc_ids}
    repair_counts = {cid: 0 for cid in scc_ids}
    pair_counts: dict[tuple[str, str], int] = {}
    explicit_pair_counts: dict[tuple[str, str], int] = {}
    pair_reasons: dict[tuple[str, str], list[str]] = {}
    oc_nodes: set[str] = set()
    rows = []

    def cov(nodes: list[str], ids: list[str]) -> float:
        return len(set(nodes) & set(ids)) / len(ids) if ids else 0.0

    for event in case.get("trace_events") or []:
        for cid, score in (event.get("scores") or {}).items():
            if cid in visit_count:
                visit_count[cid] += 1
                total_risk[cid] += float(score)

        counted_pairs: set[tuple[str, str]] = set()
        for conflict in event.get("conflicts") or []:
            pair = extract_pair(conflict) if isinstance(conflict, dict) else None
            if pair and pair[0] in visit_count and pair[1] in visit_count:
                conflict_count[pair[0]] += 1
                conflict_count[pair[1]] += 1
                if pair not in counted_pairs:
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
                    counted_pairs.add(pair)
                explicit_pair_counts[pair] = explicit_pair_counts.get(pair, 0) + 1
                reason = str(conflict.get("description") or "")[:300]
                if reason:
                    pair_reasons.setdefault(pair, [])
                    if len(pair_reasons[pair]) < 3:
                        pair_reasons[pair].append(reason)

        for cid in event.get("local_risk_subgraph_nodes") or []:
            if cid in local_counts:
                local_counts[cid] += 1
        for cid in event.get("repair_entry_nodes") or []:
            if cid in repair_counts:
                repair_counts[cid] += 1
        for edge in event.get("local_conflict_edges") or []:
            pair = extract_pair(edge) if isinstance(edge, dict) else None
            if pair and pair[0] in visit_count and pair[1] in visit_count and pair not in counted_pairs:
                pair_counts[pair] = pair_counts.get(pair, 0) + 1
                counted_pairs.add(pair)
            if pair and pair[0] in visit_count and pair[1] in visit_count:
                reason = str(edge.get("reason") or "")[:300]
                if reason:
                    pair_reasons.setdefault(pair, [])
                    if len(pair_reasons[pair]) < 3:
                        pair_reasons[pair].append(reason)

        oc_nodes = {cid for cid in (event.get("oc_detected_so_far") or []) if cid in visit_count}
        avg_risk = {
            cid: total_risk[cid] / visit_count[cid]
            for cid in scc_ids
            if visit_count[cid] > 0
        }
        selected = select_core_evidence_subgraph(
            scc_ids=scc_ids,
            avg_risk=avg_risk,
            conflict_count=conflict_count,
            visit_count=visit_count,
            local_counts=local_counts,
            repair_counts=repair_counts,
            pair_counts=pair_counts,
            explicit_pair_counts=explicit_pair_counts,
            pair_reasons=pair_reasons,
            oc_nodes=oc_nodes,
            cap=cap,
        )
        selected_set = set(selected)
        previous_nodes = set(rows[-1]["subgraph_nodes"]) if rows else set()
        union = previous_nodes | selected_set
        jaccard_prev = (
            len(previous_nodes & selected_set) / len(union)
            if union else 1.0
        )
        rows.append({
            "rollout": int(event.get("completion_index") or event.get("iteration") or len(rows) + 1),
            "subgraph_nodes": selected,
            "risk_coverage": cov(selected, risk_ids),
            "valuable_coverage": cov(selected, valuable_ids),
            "risk_any": bool(selected_set & set(risk_ids)),
            "risk_all": bool(risk_ids and all(cid in selected_set for cid in risk_ids)),
            "effective_oc": bool(oc_nodes & set(valuable_ids)),
            "subgraph_size": len(selected),
            "compression_ratio": 1 - len(selected) / max(1, len(scc_ids)),
            "jaccard_prev": jaccard_prev,
        })
    return rows


def first_signal(trace: list[dict], key: str) -> int | None:
    for point in trace:
        if point.get(key):
            return int(point["rollout"])
    return None


def first_or_budget(value: int | None, budget: int) -> int:
    return int(value) if value is not None else budget + 1


def generate_chart(result_path: Path, output_path: Path) -> None:
    cases = load_sa_cases(result_path)
    case_traces = [(case, core_prefix_trace(case)) for case in cases]
    case_traces = [(case, trace) for case, trace in case_traces if trace]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    budget = max(max(point["rollout"] for point in trace) for _case, trace in case_traces)

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.titlesize": 15,
        "axes.labelsize": 13,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 9,
    })

    size_values = sorted({case["scc_size"] for case, _trace in case_traces})
    cmap = plt.get_cmap("viridis")
    size_color = {
        size: cmap(0.15 + 0.75 * idx / max(1, len(size_values) - 1))
        for idx, size in enumerate(size_values)
    }

    fig = plt.figure(figsize=(18, 12), dpi=180)
    grid = fig.add_gridspec(2, 2, wspace=0.22, hspace=0.38)
    fig.patch.set_facecolor("#fbfbf8")
    fig.subplots_adjust(left=0.06, right=0.985, top=0.88, bottom=0.1)

    ax1 = fig.add_subplot(grid[0, 0])
    for case, trace in case_traces:
        x = [point["rollout"] for point in trace]
        y = [point["risk_coverage"] for point in trace]
        ax1.plot(
            x,
            y,
            marker="o",
            linewidth=2.2,
            markersize=4,
            color=size_color[case["scc_size"]],
            label=case["curve_label"],
        )
    ax1.set_title("Risk Coverage Convergence")
    ax1.set_xlabel("Rollout")
    ax1.set_ylabel("Risk coverage")
    ax1.set_ylim(-0.04, 1.04)
    ax1.set_xlim(1, budget)
    ax1.grid(alpha=0.25)
    ax1.legend(frameon=False, ncol=2, loc="lower right")

    ax2 = fig.add_subplot(grid[0, 1])
    for case, trace in case_traces:
        x = [point["rollout"] for point in trace]
        y = [point["valuable_coverage"] for point in trace]
        ax2.plot(
            x,
            y,
            marker="o",
            linewidth=2.2,
            markersize=4,
            color=size_color[case["scc_size"]],
            label=case["curve_label"],
        )
    ax2.set_title("Valuable-region Coverage Convergence")
    ax2.set_xlabel("Rollout")
    ax2.set_ylabel("Valuable coverage")
    ax2.set_ylim(-0.04, 1.04)
    ax2.set_xlim(1, budget)
    ax2.grid(alpha=0.25)

    ax3 = fig.add_subplot(grid[1, 0])
    labels = [case["curve_label"] for case, _trace in case_traces]
    xpos = np.arange(len(case_traces))
    width = 0.26
    risk_any = [
        first_or_budget(first_signal(trace, "risk_any"), budget)
        for _case, trace in case_traces
    ]
    risk_all = [
        first_or_budget(first_signal(trace, "risk_all"), budget)
        for _case, trace in case_traces
    ]
    effective_oc = [
        first_or_budget(first_signal(trace, "effective_oc"), budget)
        for _case, trace in case_traces
    ]
    ax3.bar(xpos - width, risk_any, width=width, color="#2563eb", label="first risk-any")
    ax3.bar(xpos, risk_all, width=width, color="#7b4ab8", label="first risk-all")
    ax3.bar(xpos + width, effective_oc, width=width, color="#f59f00", label="first effective OC")
    ax3.axhline(budget, color="#111827", linewidth=1, alpha=0.5)
    ax3.text(len(case_traces) - 0.1, budget + 0.6, "budget=30", ha="right", fontsize=10)
    for idx, value in enumerate(risk_all):
        label = "miss" if value > budget else str(value)
        ax3.text(idx, min(value, budget) + 0.6, label, ha="center", fontsize=9, color="#4c1d95", fontweight="bold")
    ax3.set_ylim(0, budget + 5)
    ax3.set_xticks(xpos, labels, rotation=30, ha="right")
    ax3.set_ylabel("Rollout when signal first appears")
    ax3.set_title("How Fast Does SA-MCGS Find the Risk Region?")
    ax3.grid(axis="y", alpha=0.22)
    ax3.legend(frameon=False, loc="upper left")

    ax4 = fig.add_subplot(grid[1, 1])
    final_risk = [trace[-1]["risk_coverage"] for _case, trace in case_traces]
    final_val = [trace[-1]["valuable_coverage"] for _case, trace in case_traces]
    final_comp = [trace[-1]["compression_ratio"] for _case, trace in case_traces]
    stability = [
        float(np.mean([point["jaccard_prev"] for point in trace[1:]]))
        if len(trace) > 1 else 1.0
        for _case, trace in case_traces
    ]
    sizes = [case["scc_size"] for case, _trace in case_traces]
    scatter = ax4.scatter(
        sizes,
        final_val,
        s=[120 + 360 * (c or 0) for c in final_comp],
        c=stability,
        cmap="magma",
        vmin=0,
        vmax=1,
        edgecolor="white",
        linewidth=1.3,
    )
    for (case, _trace), risk, val in zip(case_traces, final_risk, final_val):
        ax4.text(
            case["scc_size"] + 0.12,
            (val or 0) + 0.018,
            f"risk {100 * (risk or 0):.0f}%",
            fontsize=9,
            fontweight="bold",
            color="#374151",
        )
    ax4.set_title("Final State by SCC Length")
    ax4.set_xlabel("SCC size")
    ax4.set_ylabel("Final valuable coverage")
    ax4.set_ylim(-0.04, 1.08)
    ax4.set_xlim(min(sizes) - 1, max(sizes) + 2)
    ax4.grid(alpha=0.22)
    colorbar = fig.colorbar(scatter, ax=ax4, fraction=0.046, pad=0.03)
    colorbar.set_label("Mean stability (Jaccard)")
    ax4.text(
        0.02,
        0.03,
        "Bubble size = final compression",
        transform=ax4.transAxes,
        fontsize=10,
        color="#374151",
    )

    fig.suptitle(
        "SA-MCGS Rollout Convergence by SCC Length (8 cases, budget=30)",
        fontsize=21,
        fontweight="bold",
        y=0.965,
    )
    fig.text(
        0.5,
        0.925,
        "Most risk regions are found early; longer SCCs may keep improving after the first hit as rollout evidence accumulates.",
        ha="center",
        fontsize=14,
        color="#374151",
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.03,
        "Read with care: this is an 8-case smoke run, but it already shows anytime behavior: useful evidence often appears before the full budget is spent.",
        ha="center",
        fontsize=12,
        color="#374151",
        fontweight="bold",
    )
    fig.savefig(output_path, facecolor=fig.get_facecolor())
    plt.close(fig)


def generate_small_multiples(result_path: Path, output_path: Path) -> None:
    cases = load_sa_cases(result_path)
    case_traces = [(case, core_prefix_trace(case)) for case in cases]
    case_traces = [(case, trace) for case, trace in case_traces if trace]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    budget = max(max(point["rollout"] for point in trace) for _case, trace in case_traces)

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.titlesize": 13,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 10,
    })

    fig, axes = plt.subplots(2, 4, figsize=(18, 8.5), dpi=180, sharex=True, sharey=True)
    fig.patch.set_facecolor("#fbfbf8")
    axes = axes.flatten()

    for ax, (case, trace) in zip(axes, case_traces):
        x_risk = [point["rollout"] for point in trace]
        y_risk = [point["risk_coverage"] for point in trace]
        x_val = [point["rollout"] for point in trace]
        y_val = [point["valuable_coverage"] for point in trace]
        ax.plot(x_risk, y_risk, color="#2563eb", linewidth=2.4, marker="o", markersize=3, label="risk")
        ax.plot(x_val, y_val, color="#f59f00", linewidth=2.4, marker="o", markersize=3, label="valuable")
        ax.set_ylim(-0.04, 1.04)
        ax.set_xlim(1, budget)
        ax.grid(alpha=0.22)
        ax.set_title(case["curve_label"])
        first_all = first_signal(trace, "risk_all")
        first_any = first_signal(trace, "risk_any")
        first_oc = first_signal(trace, "effective_oc")
        final_risk = trace[-1]["risk_coverage"] if trace else 0
        final_val = trace[-1]["valuable_coverage"] if trace else 0
        subtitle = [
            f"final risk={final_risk:.0%}",
            f"value={final_val:.0%}",
            f"any@{first_any if first_any is not None else '-'}",
            f"all@{first_all if first_all is not None else 'miss'}",
            f"OC@{first_oc if first_oc is not None else '-'}",
        ]
        ax.text(
            0.02,
            0.04,
            " | ".join(subtitle),
            transform=ax.transAxes,
            fontsize=8.5,
            color="#374151",
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )
        if first_all is not None:
            ax.axvline(first_all, color="#7b4ab8", linewidth=1.4, alpha=0.8)

    for ax in axes[4:]:
        ax.set_xlabel("Rollout")
    for ax in axes[::4]:
        ax.set_ylabel("Coverage")
    axes[0].legend(frameon=False, loc="upper right")
    fig.suptitle(
        "SA-MCGS Convergence Curves per SCC (risk vs valuable coverage)",
        fontsize=19,
        fontweight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.93,
        "Blue = core risk endpoints; orange = broader risk region. Purple vertical line = first rollout that collected all risk endpoints.",
        ha="center",
        fontsize=12.5,
        color="#374151",
        fontweight="bold",
    )
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.9])
    fig.savefig(output_path, facecolor=fig.get_facecolor())
    plt.close(fig)


def write_markdown(output_path: Path, md_path: Path, small_output_path: Path | None = None) -> None:
    encoded = base64.b64encode(output_path.read_bytes()).decode("ascii")
    image_ref = f"data:image/png;base64,{encoded}"
    small_lines: list[str] = []
    if small_output_path and small_output_path.exists():
        small_encoded = base64.b64encode(small_output_path.read_bytes()).decode("ascii")
        small_ref = f"data:image/png;base64,{small_encoded}"
        small_lines = [
            "",
            "## 每个 SCC 的细分曲线",
            "",
            f"![SA-MCGS convergence small multiples]({small_ref})",
            "",
            "这张图把 8 个 matched SCC 拆开看。它比总览图更适合判断：某个长度的环是不是早早收齐了风险点，还是一直只抓住了一个端点。",
            "",
        ]
    md_path.write_text(
        "\n".join([
            "# SA-MCGS 收敛曲线图解",
            "",
            "> 口径说明：这版曲线按每一轮 `trace_events` 重建 `SA-MCGS core evidence` 前缀子图，和当前正式对比表中的 core evidence / risk-subgraph 口径一致；不再使用旧的 local-declared convergence trace。",
            "",
            f"![SA-MCGS convergence]({image_ref})",
            *small_lines,
            "",
            "## 每张图怎么看",
            "",
            "| 子图 | 含义 | 重点读法 |",
            "|---|---|---|",
            "| `Risk Coverage Convergence` | 随 rollout 增加，SA-MCGS 子图覆盖了多少核心 risk nodes。 | 曲线越早接近 1，说明越早收齐 root/witness 等核心风险端点。 |",
            "| `Valuable-region Coverage Convergence` | 随 rollout 增加，SA-MCGS 子图覆盖了多少 valuable nodes，即 risk nodes + affected nodes。 | 这个比 risk coverage 更贴近“风险区域是否收齐”。 |",
            "| `How Fast Does SA-MCGS Find the Risk Region?` | 记录第一次出现 risk-any、risk-all、effective OC 的 rollout。 | 柱子越低越好；`miss` 表示 30 rollout 内没有第一次收齐。 |",
            "| `Final State by SCC Length` | 横轴是 SCC size，纵轴是最终 valuable coverage，颜色是稳定性，气泡大小是压缩率。 | 用来看不同长度环在最终状态下是否稳定、是否覆盖充分。 |",
            "",
            "## 指标解释",
            "",
            "| 指标 | 含义 |",
            "|---|---|",
            "| `rollout` | SA-MCGS 完成一次局部窗口搜索和回传。 |",
            "| `risk coverage` | 当前子图覆盖 risk nodes 的比例。 |",
            "| `valuable coverage` | 当前子图覆盖 risk nodes + affected nodes 的比例。 |",
            "| `risk-any` | 当前子图至少包含一个 risk node。 |",
            "| `risk-all` | 当前子图包含所有 risk nodes。 |",
            "| `effective OC` | OC 检出的节点落在风险区域内。 |",
            "| `mean stability / Jaccard` | 相邻 rollout 子图的 Jaccard 相似度，越高表示子图越稳定。 |",
            "| `compression` | `1 - subgraph_size / SCC_size`，越高表示子图越小。 |",
            "",
        ]),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_path", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("--md-path", type=Path, default=None)
    parser.add_argument("--small-output-path", type=Path, default=None)
    args = parser.parse_args()
    generate_chart(args.result_path, args.output_path)
    if args.small_output_path:
        generate_small_multiples(args.result_path, args.small_output_path)
    md_path = args.md_path or args.output_path.with_name(f"{args.output_path.stem}_explained.md")
    write_markdown(args.output_path, md_path, args.small_output_path)
    print(args.output_path)
    print(md_path)


if __name__ == "__main__":
    main()

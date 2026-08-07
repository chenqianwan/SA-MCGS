#!/usr/bin/env python3
"""Stage 2 core-only replay ablations for the EMNLP discussion.

This script does not make LLM calls. It replays final-core construction from
locked Full SA-MCGS outputs and changes only the core-selection rule.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DISCUSSION_DIR = REPO_ROOT / "emnlp2026_discussion"
DEFAULT_SUMMARY = (
    DISCUSSION_DIR
    / "component_ablation_runs"
    / "stage1_full80_by_scc_size"
    / "summary_component_cases_full80.csv"
)
DEFAULT_RUNS_DIR = DISCUSSION_DIR / "component_ablation_runs"


VARIANT_LABELS = {
    "full-sa-mcgs-locked": "Full SA-MCGS (locked main)",
    "no-oc-core-signal": "No OC/core signal (replay)",
    "monotone-core": "Monotone core (replay)",
    "no-pair-closure-final-core": "No pair closure in final core (replay)",
}
REPLAY_VARIANTS = [
    "no-oc-core-signal",
    "monotone-core",
    "no-pair-closure-final-core",
]


PARAMS = {
    "subgraph_max_ratio": 0.45,
    "subgraph_min_nodes": 4,
    "pair_memory_min_score": 0.42,
    "pair_closure_min_score": 0.35,
    "core_min_nodes": 2,
    "core_min_relative_score": 0.52,
    "core_stop_gap": 0.14,
    "core_min_score": 0.10,
    "core_tail_relative_score": 0.28,
    "critical_pair_exit_threshold": 0.48,
    "critical_pair_lock_support": 2,
    "critical_pair_core_min_score": 0.62,
    "critical_pair_core_max_edge_ratio": None,
    "critical_pair_core_max_edges": 0,
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def mean(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return sum(nums) / len(nums) if nums else None


def mean_bool(values: list[Any]) -> float | None:
    vals = [v for v in values if isinstance(v, bool)]
    return sum(1 for v in vals if v) / len(vals) if vals else None


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def pair_key(source: str, target: str) -> tuple[str, str]:
    return tuple(sorted((source, target)))


def selected_nodes_from_priority_rows(result: dict[str, Any]) -> set[str]:
    rows = result.get("dynamic_core_priority_rows") or []
    selected = {
        row.get("clause_id")
        for row in rows
        if isinstance(row, dict) and row.get("selected") and isinstance(row.get("clause_id"), str)
    }
    if selected:
        return selected
    return set(result.get("evidence_risk_subgraph_nodes") or [])


def detected_oc_nodes(result: dict[str, Any]) -> set[str]:
    nodes = set(result.get("oc_detected") or result.get("oc_detected_clauses") or [])
    for cid, info in (result.get("evidence_node_scores") or {}).items():
        components = info.get("components") or {}
        raw = info.get("raw") or {}
        if components.get("oc_signal") or raw.get("oc_signal"):
            nodes.add(cid)
    for row in result.get("dynamic_core_priority_rows") or []:
        if isinstance(row, dict) and row.get("oc") and isinstance(row.get("clause_id"), str):
            nodes.add(row["clause_id"])
    return nodes


def adjusted_evidence_scores(result: dict[str, Any], *, remove_oc: bool) -> dict[str, dict[str, Any]]:
    evidence_scores = copy.deepcopy(result.get("evidence_node_scores") or {})
    if not remove_oc:
        return evidence_scores
    component_names = list(result.get("evidence_component_names") or [])
    if "oc_signal" not in component_names or len(component_names) <= 1:
        return evidence_scores
    old_denominator = len(component_names)
    new_denominator = old_denominator - 1
    for _cid, info in evidence_scores.items():
        components = dict(info.get("components") or {})
        oc_value = float(components.pop("oc_signal", 0.0) or 0.0)
        old_score = float(info.get("score", 0.0) or 0.0)
        new_score = max(0.0, (old_score * old_denominator - oc_value) / new_denominator)
        raw = dict(info.get("raw") or {})
        raw.pop("oc_signal", None)
        info["score"] = new_score
        info["components"] = components
        info["raw"] = raw
        info["support_count"] = len([value for value in components.values() if value > 0])
    return evidence_scores


def build_candidate_universe(
    result: dict[str, Any],
    evidence_scores: dict[str, dict[str, Any]],
    detected: set[str],
    index: dict[str, int],
) -> set[str]:
    universe = {
        cid
        for cid, info in evidence_scores.items()
        if cid in index and (float(info.get("score", 0.0) or 0.0) > 0 or int(info.get("support_count", 0) or 0) > 0)
    }
    universe.update(cid for cid in detected if cid in index)
    for edge in result.get("conflict_probability_matrix") or []:
        pair_score = float(edge.get("pair_score", 0.0) or 0.0)
        semantic_strength = float(edge.get("semantic_strength", 0.0) or 0.0)
        explicit_count = int(edge.get("explicit_count", 0) or 0)
        if (
            pair_score < PARAMS["pair_memory_min_score"]
            and semantic_strength < 0.65
            and explicit_count <= 0
        ):
            continue
        for cid in (edge.get("source"), edge.get("target")):
            if isinstance(cid, str) and cid in index:
                universe.add(cid)
    if not universe:
        universe.update(cid for cid in result.get("evidence_risk_subgraph_nodes") or [] if cid in index)
    return universe


def prepare_edges(result: dict[str, Any], index: dict[str, int]) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    set[str],
    dict[str, float],
    dict[str, int],
]:
    pair_endpoint_scores: dict[str, float] = defaultdict(float)
    pair_endpoint_counts: dict[str, int] = defaultdict(int)
    strong_edges: list[dict[str, Any]] = []
    protected_edge_candidates: list[dict[str, Any]] = []
    protected_nodes: set[str] = set()

    for edge in result.get("conflict_probability_matrix") or []:
        source = edge.get("source")
        target = edge.get("target")
        if source not in index or target not in index:
            continue
        pair_score = float(edge.get("pair_score", 0.0) or 0.0)
        semantic_strength = float(edge.get("semantic_strength", 0.0) or 0.0)
        explicit_count = int(edge.get("explicit_count", 0) or 0)
        critical_score = float(edge.get("critical_pair_score", 0.0) or 0.0)
        critical_state = str(edge.get("critical_state", ""))
        critical_support = int(edge.get("critical_support_count", 0) or 0)
        is_protected_critical = critical_state == "locked" or (
            critical_score >= PARAMS["critical_pair_core_min_score"]
            and critical_support >= PARAMS["critical_pair_lock_support"]
        )
        is_evidence_edge = (
            pair_score >= PARAMS["pair_memory_min_score"]
            or semantic_strength >= 0.65
            or explicit_count > 0
            or is_protected_critical
        )
        if not is_evidence_edge:
            continue
        strong_edges.append(edge)
        if is_protected_critical:
            protected_edge_candidates.append(edge)
        for cid in (source, target):
            pair_endpoint_scores[cid] = max(pair_endpoint_scores[cid], pair_score)
            pair_endpoint_counts[cid] += 1

    protected_edges = sorted(
        protected_edge_candidates,
        key=lambda edge: (
            -float(edge.get("critical_pair_score", 0.0) or 0.0),
            -float(edge.get("severity_strength", 0.0) or 0.0),
            -float(edge.get("same_path_strength", 0.0) or 0.0),
            -float(edge.get("no_fallback_strength", 0.0) or 0.0),
            -int(edge.get("critical_support_count", 0) or 0),
            -int(edge.get("critical_revisit_count", 0) or 0),
            str(edge.get("source")),
            str(edge.get("target")),
        ),
    )
    max_protected_edges = len(protected_edges)
    if PARAMS["critical_pair_core_max_edge_ratio"] is not None:
        max_protected_edges = min(
            max_protected_edges,
            max(1, math.ceil(max(1, len(index)) * float(PARAMS["critical_pair_core_max_edge_ratio"]))),
        )
    if PARAMS["critical_pair_core_max_edges"] > 0:
        max_protected_edges = min(max_protected_edges, int(PARAMS["critical_pair_core_max_edges"]))
    protected_edges = protected_edges[:max_protected_edges]
    for edge in protected_edges:
        protected_nodes.update({str(edge.get("source")), str(edge.get("target"))})

    strong_edges.sort(
        key=lambda edge: (
            -float(edge.get("pair_score", 0.0) or 0.0),
            -float(edge.get("semantic_strength", 0.0) or 0.0),
            -int(edge.get("explicit_count", 0) or 0),
            -int(edge.get("count", 0) or 0),
            str(edge.get("source")),
            str(edge.get("target")),
        )
    )
    return strong_edges, protected_edges, protected_nodes, pair_endpoint_scores, pair_endpoint_counts


def replay_core(result: dict[str, Any], variant: str) -> tuple[list[str], list[dict[str, Any]]]:
    scc_ids = list(result.get("scc_clause_ids") or [])
    if not scc_ids:
        scc_ids = list(dict.fromkeys(result.get("evidence_risk_subgraph_nodes") or []))
    index = {cid: i for i, cid in enumerate(scc_ids)}
    n = len(scc_ids)
    cap = int(result.get("evidence_subgraph_cap") or min(n, max(PARAMS["subgraph_min_nodes"], math.ceil(n * PARAMS["subgraph_max_ratio"]))))
    cap = min(n, max(1, cap))

    remove_oc = variant == "no-oc-core-signal"
    monotone = variant == "monotone-core"
    no_pair_closure = variant == "no-pair-closure-final-core"

    detected = set() if remove_oc else detected_oc_nodes(result)
    evidence_scores = adjusted_evidence_scores(result, remove_oc=remove_oc)
    context_selected = build_candidate_universe(result, evidence_scores, detected, index)
    if not context_selected:
        return [], []

    strong_edges, protected_edges, protected_nodes, pair_endpoint_scores, pair_endpoint_counts = prepare_edges(result, index)
    if monotone:
        protected_edges = []
        protected_nodes = set()

    priority_rows: list[dict[str, Any]] = []
    for cid in context_selected:
        info = evidence_scores.get(cid, {})
        score = float(info.get("score", 0.0) or 0.0)
        pair_score = float(pair_endpoint_scores.get(cid, 0.0) or 0.0)
        oc = cid in detected
        oc_bonus = 0.16 if oc else 0.0
        priority = score + 0.24 * pair_score + oc_bonus
        if priority <= 0:
            continue
        priority_rows.append(
            {
                "clause_id": cid,
                "priority": priority,
                "evidence_score": score,
                "pair_score": pair_score,
                "pair_endpoint_count": pair_endpoint_counts.get(cid, 0),
                "support_count": int(info.get("support_count", 0) or 0),
                "oc": oc,
            }
        )
    priority_rows.sort(
        key=lambda row: (
            -row["priority"],
            -row["support_count"],
            -row["pair_endpoint_count"],
            index.get(row["clause_id"], n),
        )
    )
    if not priority_rows:
        fallback = sorted(context_selected, key=lambda cid: index.get(cid, n))[:1]
        return fallback, []

    top_priority = max(float(priority_rows[0]["priority"]), 1e-9)
    core_min_nodes = min(cap, max(1, PARAMS["core_min_nodes"]))
    selected: set[str] = set()
    stop_reason = "exhausted_candidates"
    prev_priority = float(priority_rows[0]["priority"])

    if not monotone:
        for edge in protected_edges:
            endpoints = [
                cid for cid in (edge.get("source"), edge.get("target"))
                if isinstance(cid, str) and cid in context_selected
            ]
            if len(endpoints) < 2:
                continue
            if len(selected.union(endpoints)) > cap:
                continue
            selected.update(endpoints)

        if strong_edges:
            top_pair_score = max(float(edge.get("pair_score", 0.0) or 0.0) for edge in strong_edges)
            relation_seed_node_cap = min(cap, core_min_nodes)
            relation_seed_min_score = max(PARAMS["pair_memory_min_score"], top_pair_score * 0.90)
            for edge in strong_edges:
                if len(selected) >= relation_seed_node_cap:
                    break
                pair_score = float(edge.get("pair_score", 0.0) or 0.0)
                semantic_strength = float(edge.get("semantic_strength", 0.0) or 0.0)
                if pair_score < relation_seed_min_score and semantic_strength < 0.9:
                    continue
                endpoints = [
                    cid for cid in (edge.get("source"), edge.get("target"))
                    if isinstance(cid, str) and cid in context_selected
                ]
                if len(endpoints) < 2:
                    continue
                if len(selected.union(endpoints)) > relation_seed_node_cap:
                    continue
                selected.update(endpoints)

    for row_index, row in enumerate(priority_rows):
        if len(selected) >= cap:
            stop_reason = "hit_cap"
            break
        cid = row["clause_id"]
        priority = float(row["priority"])
        relative = priority / top_priority
        gap = max(0.0, (prev_priority - priority) / top_priority)
        if cid in selected:
            priority_rows[row_index]["selected"] = True
            priority_rows[row_index]["relative_priority"] = relative
            prev_priority = priority
            continue
        must_keep = bool(row["oc"]) or (cid in protected_nodes and not monotone)
        if len(selected) >= core_min_nodes and not must_keep:
            if priority < PARAMS["core_min_score"]:
                stop_reason = "below_absolute_score"
                break
            if gap >= PARAMS["core_stop_gap"]:
                stop_reason = "score_gap"
                break
            if relative < PARAMS["core_tail_relative_score"]:
                stop_reason = "below_tail_relative_score"
                break
            if relative < PARAMS["core_min_relative_score"]:
                stop_reason = "below_relative_score"
                break
        selected.add(cid)
        priority_rows[row_index]["selected"] = True
        priority_rows[row_index]["relative_priority"] = relative
        prev_priority = priority

    if not monotone and not no_pair_closure:
        closure_top_pair_score = max([float(edge.get("pair_score", 0.0) or 0.0) for edge in strong_edges] or [0.0])
        for edge in strong_edges:
            if len(selected) >= cap:
                break
            source = edge.get("source")
            target = edge.get("target")
            if source not in context_selected or target not in context_selected:
                continue
            if (source in selected) == (target in selected):
                continue
            counterpart = target if source in selected else source
            pair_score = float(edge.get("pair_score", 0.0) or 0.0)
            semantic_strength = float(edge.get("semantic_strength", 0.0) or 0.0)
            counterpart_priority = next(
                (float(row["priority"]) for row in priority_rows if row["clause_id"] == counterpart),
                0.0,
            )
            if (
                pair_score >= max(PARAMS["pair_closure_min_score"], closure_top_pair_score * 0.90)
                and (
                    edge.get("critical_state") == "locked"
                    or float(edge.get("critical_pair_score", 0.0) or 0.0) >= PARAMS["critical_pair_core_min_score"]
                    or semantic_strength >= 0.9
                    or counterpart_priority / top_priority >= 0.35
                )
            ):
                selected.add(counterpart)

    ordered_core = [cid for cid in scc_ids if cid in selected]
    for row in priority_rows:
        row.setdefault("selected", row["clause_id"] in selected)
        row.setdefault("relative_priority", float(row["priority"]) / top_priority)
    priority_rows.insert(
        0,
        {
            "policy": variant,
            "stop_reason": stop_reason,
            "cap": cap,
            "core_size": len(ordered_core),
            "context_size": len(context_selected),
            "hit_cap": len(ordered_core) >= cap,
            "oc_removed": remove_oc,
            "monotone": monotone,
            "pair_closure_enabled": not (monotone or no_pair_closure),
            "protected_critical_nodes": [cid for cid in scc_ids if cid in protected_nodes],
        },
    )
    return ordered_core, priority_rows


def evaluate_nodes(result: dict[str, Any], nodes: list[str], variant: str) -> dict[str, Any]:
    scc_ids = list(result.get("scc_clause_ids") or [])
    scc_set = set(scc_ids)
    nodes = [cid for cid in nodes if cid in scc_set]
    node_set = set(nodes)
    total = max(1, len(scc_ids) or int(result.get("scc_size") or 1))
    risk_ids = list(dict.fromkeys(result.get("injected_risk_nodes") or result.get("injected_evidence_nodes") or []))
    affected_ids = list(dict.fromkeys(result.get("injected_affected_nodes") or []))
    valuable_ids = list(dict.fromkeys([*risk_ids, *affected_ids]))

    def retained(ids: list[str]) -> list[str]:
        return [cid for cid in ids if cid in node_set]

    def coverage(ids: list[str]) -> float | None:
        return None if not ids else len(retained(ids)) / len(ids)

    return {
        "method": "sa-mcgs",
        "model": result.get("model"),
        "domain": result.get("domain"),
        "scc_id": result.get("scc_id"),
        "scc_size": result.get("scc_size"),
        "case_id": result.get("case_id"),
        "case_order": result.get("case_order"),
        "ablation_variant": variant,
        "ablation_label": VARIANT_LABELS[variant],
        "root_top3_hit": result.get("root_top3_hit", result.get("top3_hit")),
        "top3_hit": result.get("top3_hit", result.get("root_top3_hit")),
        "evidence_risk_subgraph_nodes": nodes,
        "core_evidence_risk_subgraph_nodes": nodes,
        "core_evidence_risk_subgraph_size": len(nodes),
        "core_evidence_compression_ratio": 1 - (len(nodes) / total),
        "core_evidence_contains_any_risk_node": bool(set(risk_ids) & node_set),
        "core_evidence_contains_all_risk_nodes": bool(risk_ids and all(cid in node_set for cid in risk_ids)),
        "core_evidence_risk_nodes_retained": retained(risk_ids),
        "core_evidence_risk_coverage": coverage(risk_ids),
        "core_evidence_contains_any_affected_node": bool(set(affected_ids) & node_set),
        "core_evidence_contains_all_affected_nodes": bool(affected_ids and all(cid in node_set for cid in affected_ids)),
        "core_evidence_contains_any_valuable_node": bool(set(valuable_ids) & node_set),
        "core_evidence_contains_all_valuable_nodes": bool(valuable_ids and all(cid in node_set for cid in valuable_ids)),
        "injected_risk_nodes": risk_ids,
        "injected_affected_nodes": affected_ids,
        "source_full_result_file": result.get("_source_result_file"),
        "stage2_replay_no_llm_calls": True,
        "replay_completed_at_iso": now_iso(),
    }


def load_selected_cases(summary_path: Path, case_orders: list[int]) -> list[dict[str, Any]]:
    wanted = set(case_orders)
    rows = list(csv.DictReader(summary_path.open(encoding="utf-8")))
    selected = []
    seen = set()
    for row in rows:
        if row.get("variant_key") != "full-sa-mcgs-locked":
            continue
        order = int(row.get("canonical_case_order") or row.get("case_order") or 0)
        if order not in wanted or order in seen:
            continue
        seen.add(order)
        selected.append(row)
    selected.sort(key=lambda row: int(row.get("canonical_case_order") or row.get("case_order") or 0))
    missing = wanted - {int(row.get("canonical_case_order") or row.get("case_order") or 0) for row in selected}
    if missing:
        raise RuntimeError(f"Missing case orders: {sorted(missing)}")
    return selected


def row_metric(result: dict[str, Any], metric: str) -> Any:
    mapping = {
        "root_at_3": ("root_top3_hit", "top3_hit"),
        "risk_any": ("core_evidence_contains_any_risk_node",),
        "risk_all": ("core_evidence_contains_all_risk_nodes",),
        "compression": ("core_evidence_compression_ratio",),
        "core_size": ("core_evidence_risk_subgraph_size",),
    }
    for key in mapping[metric]:
        if key in result:
            return result.get(key)
    return None


def write_tables(output_dir: Path, cases: list[dict[str, Any]]) -> None:
    result_files = sorted((output_dir / "results").glob("*.json"))
    case_meta = {
        row["case_id"]: row
        for row in cases
    }
    rows = []
    for path in result_files:
        result = json.loads(path.read_text(encoding="utf-8"))
        meta = case_meta.get(result.get("case_id"), {})
        rows.append(
            {
                "variant": VARIANT_LABELS.get(result.get("ablation_variant"), result.get("ablation_variant")),
                "variant_key": result.get("ablation_variant"),
                "case_id": result.get("case_id"),
                "case_order": int(meta.get("canonical_case_order") or result.get("case_order") or 0),
                "domain": meta.get("canonical_domain") or result.get("domain"),
                "scc_id": meta.get("canonical_scc_id") or result.get("scc_id"),
                "scc_size": int(meta.get("canonical_scc_size") or result.get("scc_size") or 0),
                "scc_bin": meta.get("canonical_scc_size_bin") or "",
                "template": meta.get("canonical_template") or "",
                "invalid": bool(result.get("component_ablation_error")),
                "root_at_3": row_metric(result, "root_at_3"),
                "risk_any": row_metric(result, "risk_any"),
                "risk_all": row_metric(result, "risk_all"),
                "risk_coverage": result.get("core_evidence_risk_coverage"),
                "compression": row_metric(result, "compression"),
                "core_size": row_metric(result, "core_size"),
                "result_file": str(path),
            }
        )
    rows.sort(key=lambda row: (row["case_order"], row["variant_key"]))
    if not rows:
        return

    summary_csv = output_dir / "summary_stage2_core_replay_cases.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    full = [row for row in rows if row["variant_key"] == "full-sa-mcgs-locked"]
    full_metrics = {
        "Root@3": mean_bool([row["root_at_3"] for row in full]),
        "Risk-any": mean_bool([row["risk_any"] for row in full]),
        "Risk-all": mean_bool([row["risk_all"] for row in full]),
        "Compression": mean([row["compression"] for row in full]),
        "Avg core size": mean([row["core_size"] for row in full]),
    }

    variant_order = ["full-sa-mcgs-locked", *REPLAY_VARIANTS]
    table_rows = []
    for variant in variant_order:
        items = [row for row in rows if row["variant_key"] == variant]
        if not items:
            continue
        root = mean_bool([row["root_at_3"] for row in items])
        risk_any = mean_bool([row["risk_any"] for row in items])
        risk_all = mean_bool([row["risk_all"] for row in items])
        compression = mean([row["compression"] for row in items])
        core_size = mean([row["core_size"] for row in items])
        table_rows.append(
            {
                "Variant": VARIANT_LABELS[variant],
                "N": len(items),
                "Invalid": mean_bool([row["invalid"] for row in items]),
                "Root@3": root,
                "Risk-any": risk_any,
                "Risk-all": risk_all,
                "Risk coverage": mean([row["risk_coverage"] for row in items]),
                "Compression": compression,
                "Avg core size": core_size,
                "Delta Root@3": None if root is None or full_metrics["Root@3"] is None else root - full_metrics["Root@3"],
                "Delta Risk-any": None if risk_any is None or full_metrics["Risk-any"] is None else risk_any - full_metrics["Risk-any"],
                "Delta Risk-all": None if risk_all is None or full_metrics["Risk-all"] is None else risk_all - full_metrics["Risk-all"],
                "Delta Compression": None if compression is None or full_metrics["Compression"] is None else compression - full_metrics["Compression"],
                "Delta Avg core size": None if core_size is None or full_metrics["Avg core size"] is None else core_size - full_metrics["Avg core size"],
            }
        )

    write_markdown_table(output_dir / "stage2_core_replay_table.md", "Stage 2 Core-Only Replay: 40 Cases", table_rows)
    write_csv(output_dir / "stage2_core_replay_table.csv", table_rows)

    by_bin_rows = []
    for bin_name in ["small (9-11)", "medium (12-18)", "large (20-34)"]:
        bin_full = [row for row in rows if row["scc_bin"] == bin_name and row["variant_key"] == "full-sa-mcgs-locked"]
        if not bin_full:
            continue
        bin_full_metrics = {
            "Root@3": mean_bool([row["root_at_3"] for row in bin_full]),
            "Risk-any": mean_bool([row["risk_any"] for row in bin_full]),
            "Risk-all": mean_bool([row["risk_all"] for row in bin_full]),
            "Compression": mean([row["compression"] for row in bin_full]),
        }
        for variant in variant_order:
            items = [row for row in rows if row["scc_bin"] == bin_name and row["variant_key"] == variant]
            if not items:
                continue
            root = mean_bool([row["root_at_3"] for row in items])
            risk_any = mean_bool([row["risk_any"] for row in items])
            risk_all = mean_bool([row["risk_all"] for row in items])
            compression = mean([row["compression"] for row in items])
            by_bin_rows.append(
                {
                    "SCC bin": bin_name,
                    "Variant": VARIANT_LABELS[variant],
                    "N": len(items),
                    "Root@3": root,
                    "Risk-any": risk_any,
                    "Risk-all": risk_all,
                    "Risk coverage": mean([row["risk_coverage"] for row in items]),
                    "Compression": compression,
                    "Delta Root@3": None if root is None or bin_full_metrics["Root@3"] is None else root - bin_full_metrics["Root@3"],
                    "Delta Risk-any": None if risk_any is None or bin_full_metrics["Risk-any"] is None else risk_any - bin_full_metrics["Risk-any"],
                    "Delta Risk-all": None if risk_all is None or bin_full_metrics["Risk-all"] is None else risk_all - bin_full_metrics["Risk-all"],
                    "Delta Compression": None if compression is None or bin_full_metrics["Compression"] is None else compression - bin_full_metrics["Compression"],
                }
            )
    write_markdown_table(output_dir / "stage2_core_replay_by_scc_bin.md", "Stage 2 Core-Only Replay by SCC Size Bin", by_bin_rows)
    write_csv(output_dir / "stage2_core_replay_by_scc_bin.csv", by_bin_rows)

    report = [
        "# Stage 2 Core-Only Replay Report",
        "",
        "Scope: 40 matched Full SA-MCGS cases replayed without new LLM calls.",
        "",
        "Variants:",
        "- No OC/core signal: remove the OC signal from evidence scoring and final-core priority/keep rules.",
        "- Monotone core: score-ordered accumulation without protected pair seeding or final pair closure.",
        "- No pair closure in final core: keep dynamic priority/protected seeding but disable the final counterpart-closure step.",
        "",
        "## Main Table",
        "",
        (output_dir / "stage2_core_replay_table.md").read_text(encoding="utf-8"),
        "",
        "## SCC Bin Table",
        "",
        (output_dir / "stage2_core_replay_by_scc_bin.md").read_text(encoding="utf-8"),
    ]
    (output_dir / "stage2_core_replay_report.md").write_text("\n".join(report).strip() + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_table(path: Path, title: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text(f"# {title}\n\nNo rows.\n", encoding="utf-8")
        return
    headers = list(rows[0].keys())
    lines = [
        f"# {title}",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(fmt(row.get(header)) for header in headers) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results").mkdir(exist_ok=True)
    cases = load_selected_cases(args.summary, args.case_orders)
    shutil.copy2(args.summary, output_dir / "source_summary_component_cases_full80.csv")
    with (output_dir / "case_plan.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(cases[0].keys()))
        writer.writeheader()
        writer.writerows(cases)
    atomic_write_json(
        output_dir / "run_config.json",
        {
            "created_at": now_iso(),
            "stage": "stage2_core_only_replay",
            "summary_source": str(args.summary),
            "case_orders": args.case_orders,
            "variants": ["full-sa-mcgs-locked", *REPLAY_VARIANTS],
            "no_new_llm_calls": True,
            "params": PARAMS,
        },
    )
    status = {
        "run_id": output_dir.name,
        "stage": "stage2",
        "started_at": now_iso(),
        "total_cases": len(cases),
        "variants": ["full-sa-mcgs-locked", *REPLAY_VARIANTS],
        "total_case_variants": len(cases) * (1 + len(REPLAY_VARIANTS)),
        "completed_case_variants": 0,
        "failed_case_variants": 0,
        "remaining_case_variants": len(cases) * (1 + len(REPLAY_VARIANTS)),
        "no_new_llm_calls": True,
    }
    atomic_write_json(output_dir / "status.json", status)

    completed = 0
    failed = 0
    for case in cases:
        source_path = Path(case["result_file"])
        full = json.loads(source_path.read_text(encoding="utf-8"))
        full["_source_result_file"] = str(source_path)
        full["case_order"] = int(case.get("canonical_case_order") or case.get("case_order") or full.get("case_order") or 0)
        full["case_id"] = case["case_id"]

        full_out = evaluate_nodes(full, list(full.get("evidence_risk_subgraph_nodes") or []), "full-sa-mcgs-locked")
        full_out["ablation_source"] = "locked_main_experiment"
        full_out["canonical_scc_size_bin"] = case.get("canonical_scc_size_bin")
        atomic_write_json(output_dir / "results" / f"{case['case_id']}__full-sa-mcgs-locked.json", full_out)
        completed += 1

        for variant in REPLAY_VARIANTS:
            try:
                nodes, rows = replay_core(full, variant)
                replay_out = evaluate_nodes(full, nodes, variant)
                replay_out["dynamic_core_priority_rows"] = rows
                replay_out["ablation_source"] = "stage2_core_only_replay"
                replay_out["canonical_scc_size_bin"] = case.get("canonical_scc_size_bin")
                atomic_write_json(output_dir / "results" / f"{case['case_id']}__{variant}.json", replay_out)
                completed += 1
            except Exception as exc:  # Keep one bad case from hiding all usable rows.
                failed += 1
                atomic_write_json(
                    output_dir / "results" / f"{case['case_id']}__{variant}.json",
                    {
                        "case_id": case["case_id"],
                        "case_order": int(case.get("canonical_case_order") or case.get("case_order") or 0),
                        "ablation_variant": variant,
                        "ablation_label": VARIANT_LABELS[variant],
                        "component_ablation_error": str(exc),
                        "stage2_replay_no_llm_calls": True,
                    },
                )
                completed += 1
        status.update(
            {
                "updated_at": now_iso(),
                "completed_case_variants": completed,
                "failed_case_variants": failed,
                "remaining_case_variants": status["total_case_variants"] - completed,
            }
        )
        atomic_write_json(output_dir / "status.json", status)

    write_tables(output_dir, cases)
    status.update(
        {
            "updated_at": now_iso(),
            "completed_at": now_iso(),
            "completed_case_variants": completed,
            "failed_case_variants": failed,
            "remaining_case_variants": status["total_case_variants"] - completed,
            "summary_table": str(output_dir / "stage2_core_replay_table.md"),
            "summary_cases": str(output_dir / "summary_stage2_core_replay_cases.csv"),
        }
    )
    atomic_write_json(output_dir / "status.json", status)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay Stage 2 core-only component ablations.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--case-orders", nargs="+", type=int, default=list(range(1, 41)))
    args = parser.parse_args()
    if args.output_dir is None:
        run_id = time.strftime("stage2_core_replay_40case_%Y%m%d_%H%M%S", time.localtime())
        args.output_dir = DEFAULT_RUNS_DIR / run_id
    args.summary = args.summary.resolve()
    args.output_dir = args.output_dir.resolve()
    return args


if __name__ == "__main__":
    run(parse_args())

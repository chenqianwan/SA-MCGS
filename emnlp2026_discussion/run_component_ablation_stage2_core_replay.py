#!/usr/bin/env python3
"""Paired trajectory replay for dynamic-vs-locked final-core policies.

The replay consumes one frozen Full SA-MCGS trace per case and never calls an
LLM. At every completed rollout prefix it reconstructs the cumulative search
state and runs the unchanged production core selector. The same proposal is
then interpreted under two policies:

* ``full-recompute-replacement`` uses the current prefix proposal, so nodes
  admitted at an earlier prefix may disappear later.
* ``locked-no-replacement`` admits proposed nodes until the same hard cap is
  reached; once admitted, a node can never leave the core.

OC signals, relation seeding, critical-pair protection, and pair closure are
shared. A case is emitted only when its stored identity and trace are
internally consistent and final replay reproduces the frozen Full core.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "cross_domain"))

from experiments.cross_domain import run_cross_domain_battle as battle
from src.models.graph import Clause, DependencyGraph, SCCInfo
from src.models.search_tree import TranspositionEntry
from src.modules.alphago_mcgs import AlphaGoMCGS


DISCUSSION_DIR = REPO_ROOT / "emnlp2026_discussion"
DEFAULT_DIAGNOSTIC_SUMMARY = (
    DISCUSSION_DIR
    / "component_ablation_runs"
    / "stage1_full80_by_scc_size"
    / "summary_component_cases_full80.csv"
)
DEFAULT_CASE_CSV = DISCUSSION_DIR / "case_composition.csv"
DEFAULT_CASE_PLANS = [
    DISCUSSION_DIR
    / "component_ablation_runs"
    / "stage1_gpt4o_b60_ic4_cc4_20260711_main20"
    / "case_plan.json",
    DISCUSSION_DIR
    / "component_ablation_runs"
    / "stage1_extra_long20_gpt4o_b60_ic4_cc4_20260711"
    / "case_plan.json",
]
DEFAULT_RUNS_DIR = REPO_ROOT / "2026NAACL" / "SA-MCGS" / "experiments"

FULL_RECOMPUTE = "full-recompute-replacement"
LOCKED_NO_REPLACEMENT = "locked-no-replacement"
REPLAY_VARIANTS = [FULL_RECOMPUTE, LOCKED_NO_REPLACEMENT]
VARIANT_LABELS = {
    FULL_RECOMPUTE: "Full recompute/replacement (paired replay)",
    LOCKED_NO_REPLACEMENT: "Locked no-replacement (paired replay)",
}
DEFAULT_FLOAT_TOLERANCE = 1e-12


class ReplayValidationError(RuntimeError):
    """Raised when a case cannot be certified for paired replay."""


class ReplayOnlyLLM:
    """Sentinel client: any accidental LLM request makes the replay fail."""

    def __init__(self) -> None:
        self.calls = 0

    async def call_json(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        raise AssertionError("Stage-2 core replay must not call an LLM")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def stable_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def mean(values: list[Any]) -> float | None:
    nums = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return sum(nums) / len(nums) if nums else None


def mean_bool(values: list[Any]) -> float | None:
    vals = [value for value in values if isinstance(value, bool)]
    return sum(1 for value in vals if value) / len(vals) if vals else None


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def scc_size_bin(size: int) -> str:
    if size <= 11:
        return "small (9-11)"
    if size <= 18:
        return "medium (12-18)"
    return "large (20-34)"


def _canonical(case: dict[str, Any], name: str) -> Any:
    value = case.get(f"canonical_{name}")
    return value if value not in (None, "") else case.get(name)


def resolve_source_result_path(raw_path: str | Path) -> Path:
    """Resolve a frozen result path without consulting any graph/SCC loader."""
    path = Path(raw_path)
    if path.exists() and path.resolve().is_relative_to(REPO_ROOT):
        return path.resolve()
    # Prefer the current branch's mirrored immutable artifact over a stale
    # absolute path into another worktree.
    candidate = REPO_ROOT / "experiments" / "cross_domain" / "results" / path.name
    if candidate.exists():
        return candidate.resolve()
    parts = path.parts
    if "emnlp2026_discussion" in parts:
        relative = Path(*parts[parts.index("emnlp2026_discussion") :])
        candidate = REPO_ROOT / relative
        if candidate.exists():
            return candidate.resolve()
    if path.exists():
        return path.resolve()
    raise ReplayValidationError(f"Frozen Full result does not exist: {raw_path}")


def source_injection_identity(
    payload: dict[str, Any],
    *,
    requested_family: str,
) -> dict[str, Any]:
    """Extract deterministic injection fields without importing a shared loader."""
    return {
        "seed": int(payload.get("inject_seed") or 42),
        "profile": str(payload.get("inject_profile") or "memory_stress"),
        "profile_version": payload.get("inject_profile_version"),
        "requested_conflict_family": requested_family,
        "conflict_family": payload.get("injected_conflict_family"),
        "conflict_severity": payload.get("injected_conflict_severity"),
        "conflict_template": payload.get("injected_conflict_template"),
        "root_node": payload.get("injected_node"),
        "witness_node": payload.get("injected_witness_node"),
        "witness_distance": payload.get("injected_witness_distance"),
        "bridge_node": payload.get("injected_bridge_node"),
        "bridge_distance": payload.get("injected_bridge_distance"),
        "risk_nodes": list(payload.get("injected_risk_nodes") or []),
        "evidence_nodes": list(payload.get("injected_evidence_nodes") or []),
        "affected_nodes": list(payload.get("injected_affected_nodes") or []),
    }


def _planned_scc_ids(case: dict[str, Any]) -> list[str] | None:
    direct = case.get("planned_scc_clause_ids")
    if isinstance(direct, list) and direct:
        return list(direct)
    planned = case.get("planned_case_identity")
    if isinstance(planned, dict):
        values = planned.get("ordered_clause_ids")
        if isinstance(values, list) and values:
            return list(values)
    return None


def _planned_injection(case: dict[str, Any]) -> dict[str, Any] | None:
    direct = case.get("planned_injection_identity")
    if isinstance(direct, dict) and direct:
        return direct
    planned = case.get("planned_case_identity")
    if isinstance(planned, dict) and isinstance(planned.get("injection"), dict):
        return planned["injection"]
    return None


def validate_case_identity(
    case: dict[str, Any],
    full: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed on canonical-plan/source-row identity disagreement.

    The original main-experiment row is authoritative for the physical SCC.
    Legacy numeric ``scc_id`` is retained only as diagnostics. Canonical case
    ID/order come from the plan because the original row predates those fields.
    """
    expected = {
        "case_id": str(_canonical(case, "case_id") or case.get("case_id") or ""),
        "case_order": int(_canonical(case, "case_order") or 0),
        "model": str(case.get("model") or ""),
        "domain": str(_canonical(case, "domain") or ""),
        "scc_id_diagnostic": str(_canonical(case, "scc_id") or ""),
        "scc_size": int(_canonical(case, "scc_size") or 0),
        "requested_family": str(_canonical(case, "template") or ""),
    }
    if not expected["case_id"] or expected["case_order"] <= 0:
        raise ReplayValidationError("Canonical plan is missing case_id/case_order")
    actual_model = str(full.get("model") or "")
    actual_domain = str(full.get("domain") or "")
    actual_family = str(full.get("injected_conflict_family") or "")
    mismatches: dict[str, dict[str, Any]] = {}
    for key, wanted, actual in (
        ("model", expected["model"], actual_model),
        ("domain", expected["domain"], actual_domain),
        ("requested_family", expected["requested_family"], actual_family),
    ):
        if wanted != actual:
            mismatches[key] = {"expected": wanted, "actual": actual}
    if mismatches:
        raise ReplayValidationError(
            "Original Full row does not match the canonical plan: "
            + json.dumps(mismatches, ensure_ascii=False, sort_keys=True)
        )

    scc_ids = full.get("scc_clause_ids")
    if not isinstance(scc_ids, list) or not scc_ids:
        raise ReplayValidationError("Missing non-empty scc_clause_ids")
    if any(not isinstance(cid, str) or not cid for cid in scc_ids):
        raise ReplayValidationError("scc_clause_ids contains a non-string/empty ID")
    if len(set(scc_ids)) != len(scc_ids):
        raise ReplayValidationError("scc_clause_ids contains duplicates")
    if expected["scc_size"] != len(scc_ids):
        raise ReplayValidationError(
            f"Physical SCC size disagrees with the plan: "
            f"plan={expected['scc_size']}, nodes={len(scc_ids)}"
        )
    source_size = int(full.get("scc_size") or 0)
    if source_size != len(scc_ids):
        raise ReplayValidationError(
            f"Original Full SCC size disagrees with its node set: "
            f"row={source_size}, nodes={len(scc_ids)}"
        )

    planned_ids = _planned_scc_ids(case)
    if planned_ids is not None and planned_ids != scc_ids:
        raise ReplayValidationError(
            "Original Full physical SCC does not equal planned_scc_clause_ids"
        )

    injection = source_injection_identity(
        full,
        requested_family=expected["requested_family"],
    )
    planned_injection = _planned_injection(case)
    if planned_injection is not None:
        missing = set(planned_injection) - set(injection)
        if missing:
            raise ReplayValidationError(
                f"Original Full injection identity lacks planned keys: {sorted(missing)}"
            )
        projected = {key: injection[key] for key in planned_injection}
        if projected != planned_injection:
            raise ReplayValidationError(
                "Original Full injection identity differs from the canonical plan"
            )

    composition = case.get("_composition_identity") or {}
    if composition:
        composition_checks = {
            "root_node": composition.get("root_node"),
            "witness_node": composition.get("witness_node"),
            "bridge_node": composition.get("bridge_node"),
            "affected_count": composition.get("affected_count"),
        }
        actual_checks = {
            "root_node": injection["root_node"],
            "witness_node": injection["witness_node"],
            "bridge_node": injection["bridge_node"],
            "affected_count": len(injection["affected_nodes"]),
        }
        differences = {
            key: {"expected": value, "actual": actual_checks[key]}
            for key, value in composition_checks.items()
            if value != actual_checks[key]
        }
        if differences:
            raise ReplayValidationError(
                "Original Full injection disagrees with case_composition.csv: "
                + json.dumps(differences, ensure_ascii=False, sort_keys=True)
            )

    scc_set = set(scc_ids)
    for field in (
        "injected_risk_nodes",
        "injected_evidence_nodes",
        "injected_affected_nodes",
        "ground_truth_nodes",
    ):
        values = full.get(field) or []
        if isinstance(values, str):
            values = [values]
        outside = set(values) - scc_set
        if outside:
            raise ReplayValidationError(
                f"{field} references nodes outside the physical SCC: {sorted(outside)}"
            )
    if injection["root_node"] and injection["root_node"] not in scc_set:
        raise ReplayValidationError("Injected root is outside the physical SCC")
    if injection["witness_node"] and injection["witness_node"] not in scc_set:
        raise ReplayValidationError("Injected witness is outside the physical SCC")
    if injection["bridge_node"] and injection["bridge_node"] not in scc_set:
        raise ReplayValidationError("Injected bridge is outside the physical SCC")

    identity_payload = {
        "version": "paired_core_source_identity_v1",
        "model": expected["model"],
        "domain": expected["domain"],
        "ordered_clause_ids": scc_ids,
        "injection": injection,
    }
    physical_scc_payload = {
        "version": "paired_core_physical_scc_v1",
        "domain": expected["domain"],
        "ordered_clause_ids": scc_ids,
    }
    local_uid = "pcr-v1-" + stable_sha256(identity_payload)
    return {
        "case_uid": case.get("case_uid") or local_uid,
        "paired_replay_case_uid": local_uid,
        "physical_scc_uid": "psc-v1-" + stable_sha256(physical_scc_payload),
        "identity_payload": identity_payload,
        "node_count": len(scc_ids),
        "canonical_case_id": expected["case_id"],
        "canonical_case_order": expected["case_order"],
        "canonical_scc_id_diagnostic": expected["scc_id_diagnostic"],
        "source_scc_id_diagnostic": full.get("scc_id"),
        "source_record_index": full.get("_source_record_index"),
        "source_file_sha256": full.get("_source_file_sha256"),
        "source_record_sha256": full.get("_source_record_sha256"),
    }


def validate_trace(full: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    trace = full.get("trace_events")
    if not isinstance(trace, list) or not trace:
        raise ReplayValidationError("Frozen Full result has no trace_events")
    budget = int(full.get("budget") or len(trace))
    if len(trace) != budget:
        raise ReplayValidationError(
            f"Incomplete trace: events={len(trace)}, frozen budget={budget}"
        )

    completion_indexes = [event.get("completion_index") for event in trace]
    expected_indexes = list(range(1, len(trace) + 1))
    if completion_indexes != expected_indexes:
        raise ReplayValidationError(
            "trace_events must be stored in contiguous completion order; "
            f"got={completion_indexes[:10]}..."
        )

    scc_set = set(full["scc_clause_ids"])
    previous_oc: set[str] = set()
    ignored_raw_conflict_endpoints = 0
    for position, event in enumerate(trace, 1):
        if not isinstance(event, dict):
            raise ReplayValidationError(f"Trace event {position} is not an object")
        window = event.get("window")
        if not isinstance(window, list) or not window:
            raise ReplayValidationError(f"Trace event {position} has no window")
        if len(set(window)) != len(window) or not set(window).issubset(scc_set):
            raise ReplayValidationError(
                f"Trace event {position} window is not a unique SCC subset"
            )
        scores = event.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(window):
            raise ReplayValidationError(
                f"Trace event {position} scores do not exactly match its window"
            )
        for field in (
            "local_risk_subgraph_nodes",
            "repair_entry_nodes",
            "oc_detected_so_far",
        ):
            values = event.get(field) or []
            if not isinstance(values, list) or not set(values).issubset(scc_set):
                raise ReplayValidationError(
                    f"Trace event {position} {field} is not an SCC subset"
                )
        current_oc = set(event.get("oc_detected_so_far") or [])
        if not previous_oc.issubset(current_oc):
            raise ReplayValidationError(
                f"Trace event {position} removes an already detected OC node"
            )
        previous_oc = current_oc

        local_edges = event.get("local_conflict_edges") or []
        if not isinstance(local_edges, list):
            raise ReplayValidationError(
                f"Trace event {position} local_conflict_edges is not a list"
            )
        for edge in local_edges:
            if not isinstance(edge, dict):
                raise ReplayValidationError(
                    f"Trace event {position} contains a non-object local edge"
                )
            source = edge.get("source")
            target = edge.get("target")
            if source not in scc_set or target not in scc_set or source == target:
                raise ReplayValidationError(
                    f"Trace event {position} has an invalid local edge: {edge}"
                )

        # Raw conflicts can contain hallucinated IDs. Production ignored those
        # endpoints too; count them for audit instead of using them.
        for conflict in event.get("conflicts") or []:
            if not isinstance(conflict, dict):
                continue
            for field in ("clause_a", "clause_b"):
                cid = conflict.get(field)
                if cid and cid not in scc_set:
                    ignored_raw_conflict_endpoints += 1

        selection = event.get("selection") or {}
        if not isinstance(selection, dict):
            raise ReplayValidationError(
                f"Trace event {position} selection metadata is not an object"
            )
        if selection.get("mode") in {"critical_pair_revisit", "relation_probe"}:
            endpoints = {selection.get("source"), selection.get("target")}
            if None in endpoints or not endpoints.issubset(scc_set):
                raise ReplayValidationError(
                    f"Trace event {position} selection pair is outside the SCC"
                )

    return trace, {
        "trace_sha256": stable_sha256(trace),
        "trace_events": len(trace),
        "ignored_raw_conflict_endpoints": ignored_raw_conflict_endpoints,
    }


def make_replay_mcgs(full: dict[str, Any]) -> tuple[AlphaGoMCGS, ReplayOnlyLLM]:
    scc_ids = list(full["scc_clause_ids"])
    clauses = {
        cid: Clause(id=cid, title=cid, content="frozen-trace replay placeholder")
        for cid in scc_ids
    }
    graph = DependencyGraph(clauses=clauses, edges=[])
    scc = SCCInfo(
        id=str(full.get("scc_id") or "frozen_scc"),
        clause_ids=scc_ids,
        size=len(scc_ids),
    )

    config = copy.deepcopy(battle.MCGS_DEFAULT)
    mcgs_cfg = config["alphago_mcgs"]
    trace = full["trace_events"]
    mcgs_cfg["budget"] = int(full.get("budget") or len(trace))
    mcgs_cfg["window_size"] = max(len(event.get("window") or []) for event in trace)
    mcgs_cfg["concurrency"] = int(full.get("internal_concurrency") or 1)
    mcgs_cfg["trace"] = True
    evidence = mcgs_cfg.setdefault("evidence", {})
    stored_params = full.get("mcgs_compression_params") or {}
    if isinstance(stored_params, dict):
        evidence.update(stored_params)
    if "relation_first_enabled" in full:
        evidence["relation_first"] = bool(full["relation_first_enabled"])

    llm = ReplayOnlyLLM()
    mcgs = AlphaGoMCGS(llm_client=llm, config=config)
    mcgs._init_state(graph, scc)
    return mcgs, llm


def trace_event_to_entry(event: dict[str, Any]) -> TranspositionEntry:
    return TranspositionEntry(
        clause_ids=sorted(event["window"]),
        clause_evaluations={
            cid: float(score) for cid, score in event["scores"].items()
        },
        clause_reasonings={},
        conflicts=copy.deepcopy(event.get("conflicts") or []),
        local_risk_subgraph_nodes=list(event.get("local_risk_subgraph_nodes") or []),
        local_conflict_edges=copy.deepcopy(event.get("local_conflict_edges") or []),
        repair_entry_nodes=list(event.get("repair_entry_nodes") or []),
        timestamp=int(event["completion_index"]) - 1,
    )


def apply_trace_event(mcgs: AlphaGoMCGS, event: dict[str, Any]) -> None:
    """Apply one completed rollout in the same state-update order as search()."""
    mcgs._last_selection_meta = copy.deepcopy(event.get("selection") or {})
    mcgs._backpropagate(list(event["window"]), trace_event_to_entry(event))
    # Original order is backpropagate -> update OC -> record trace. The frozen
    # event stores the post-update OC set, so assigning it here is exact.
    mcgs._detected_clauses = set(event.get("oc_detected_so_far") or [])
    mcgs._trace_events.append(copy.deepcopy(event))


def selected_proposal_order(summary: dict[str, Any]) -> list[str]:
    """Return selected proposal nodes in the selector's priority order."""
    proposal = list(summary.get("evidence_risk_subgraph_nodes") or [])
    proposal_set = set(proposal)
    ordered: list[str] = []
    for row in summary.get("dynamic_core_priority_rows") or []:
        if not isinstance(row, dict) or not row.get("selected"):
            continue
        cid = row.get("clause_id")
        if isinstance(cid, str) and cid in proposal_set and cid not in ordered:
            ordered.append(cid)
    # Protected-edge and fallback nodes can be absent from priority rows. The
    # production SCC order is the deterministic final tie-break for them.
    ordered.extend(cid for cid in proposal if cid not in ordered)
    if set(ordered) != proposal_set or len(ordered) != len(proposal_set):
        raise ReplayValidationError("Could not derive a unique proposal admission order")
    return ordered


def advance_locked_core(
    previous: list[str],
    summary: dict[str, Any],
    *,
    scc_ids: list[str],
) -> tuple[list[str], list[str]]:
    """Admit current proposal nodes without ever evicting an earlier admission."""
    cap = int(summary.get("evidence_subgraph_cap") or 0)
    if cap <= 0 or cap > len(scc_ids):
        raise ReplayValidationError(f"Invalid replay core cap: {cap}")
    if len(previous) != len(set(previous)) or not set(previous).issubset(scc_ids):
        raise ReplayValidationError("Previous locked core is invalid")
    if len(previous) > cap:
        raise ReplayValidationError("Previous locked core exceeds the shared cap")

    locked = list(previous)
    admitted: list[str] = []
    for cid in selected_proposal_order(summary):
        if len(locked) >= cap:
            break
        if cid in locked:
            continue
        locked.append(cid)
        admitted.append(cid)
    return locked, admitted


def _assert_close(
    expected: Any,
    actual: Any,
    *,
    path: str,
    tolerance: float,
) -> None:
    if isinstance(expected, bool) or isinstance(actual, bool):
        if expected is not actual:
            raise ReplayValidationError(
                f"Final Full parity failed at {path}: expected={expected}, actual={actual}"
            )
        return
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        scale = max(1.0, abs(float(expected)), abs(float(actual)))
        if abs(float(expected) - float(actual)) > tolerance * scale:
            raise ReplayValidationError(
                f"Final Full parity failed at {path}: expected={expected}, actual={actual}"
            )
        return
    if isinstance(expected, dict) and isinstance(actual, dict):
        if set(expected) != set(actual):
            raise ReplayValidationError(
                f"Final Full parity failed at {path}: dictionary keys differ"
            )
        for key in expected:
            _assert_close(
                expected[key],
                actual[key],
                path=f"{path}.{key}",
                tolerance=tolerance,
            )
        return
    if isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple)):
        if len(expected) != len(actual):
            raise ReplayValidationError(
                f"Final Full parity failed at {path}: "
                f"length {len(expected)} != {len(actual)}"
            )
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            _assert_close(
                expected_item,
                actual_item,
                path=f"{path}[{index}]",
                tolerance=tolerance,
            )
        return
    if expected != actual:
        raise ReplayValidationError(
            f"Final Full parity failed at {path}: expected={expected!r}, actual={actual!r}"
        )


def assert_final_full_parity(
    full: dict[str, Any],
    replayed: dict[str, Any],
    *,
    tolerance: float = DEFAULT_FLOAT_TOLERANCE,
) -> list[str]:
    """Certify that replay recovered the frozen Full state and final core."""
    field_pairs = [
        ("local_risk_subgraph_counts", "local_risk_subgraph_counts"),
        ("repair_entry_counts", "repair_entry_counts"),
        ("local_conflict_edges", "local_conflict_edges"),
        ("amaf_node_evidence", "amaf_node_evidence"),
        ("path_fragment_evidence", "path_fragment_evidence"),
        ("relation_node_raw_scores", "relation_node_raw_scores"),
        ("evidence_node_scores", "evidence_node_scores"),
        ("ranking_by_evidence", "ranking_by_evidence"),
        ("conflict_probability_matrix", "conflict_probability_matrix"),
        ("critical_pair_ledger_rows", "critical_pair_ledger_rows"),
        ("evidence_risk_subgraph_nodes", "evidence_risk_subgraph_nodes"),
        ("evidence_risk_subgraph_size", "evidence_risk_subgraph_size"),
        ("evidence_compression_ratio", "evidence_compression_ratio"),
        ("evidence_subgraph_cap", "evidence_subgraph_cap"),
        ("dynamic_core_priority_rows", "dynamic_core_priority_rows"),
    ]
    checked: list[str] = []
    frozen_scores = full.get("scores")
    replay_ranking = replayed.get("ranking_by_risk")
    if not isinstance(frozen_scores, dict) or not isinstance(replay_ranking, list):
        raise ReplayValidationError(
            "Final Full parity requires frozen scores and replay ranking_by_risk"
        )
    try:
        replay_scores = dict(replay_ranking)
    except (TypeError, ValueError) as exc:
        raise ReplayValidationError(
            "Replay ranking_by_risk is not a unique (node, score) sequence"
        ) from exc
    if len(replay_scores) != len(replay_ranking):
        raise ReplayValidationError("Replay ranking_by_risk contains duplicate nodes")
    _assert_close(
        frozen_scores,
        replay_scores,
        path="scores",
        tolerance=tolerance,
    )
    checked.append("scores")
    if "ranking" not in full:
        raise ReplayValidationError("Frozen Full result is missing parity field: ranking")
    _assert_close(
        full["ranking"],
        replay_ranking,
        path="ranking",
        tolerance=tolerance,
    )
    checked.append("ranking")
    for frozen_field, replay_field in field_pairs:
        if frozen_field not in full:
            raise ReplayValidationError(
                f"Frozen Full result is missing parity field: {frozen_field}"
            )
        replay_value = replayed.get(replay_field)
        if frozen_field == "dynamic_core_priority_rows":
            # The selector now emits a few additive audit keys that were not
            # present when the frozen traces were generated. Certify every
            # stored key/value while allowing only those extra replay fields.
            frozen_rows = full[frozen_field]
            if not isinstance(frozen_rows, list) or not isinstance(replay_value, list):
                raise ReplayValidationError(
                    "Final Full parity failed at dynamic_core_priority_rows: "
                    "expected two lists"
                )
            if len(frozen_rows) != len(replay_value):
                raise ReplayValidationError(
                    "Final Full parity failed at dynamic_core_priority_rows: "
                    f"length {len(frozen_rows)} != {len(replay_value)}"
                )
            projected_rows: list[dict[str, Any]] = []
            for index, (frozen_row, replay_row) in enumerate(
                zip(frozen_rows, replay_value)
            ):
                if not isinstance(frozen_row, dict) or not isinstance(replay_row, dict):
                    raise ReplayValidationError(
                        "Final Full parity failed at "
                        f"dynamic_core_priority_rows[{index}]: expected mappings"
                    )
                missing = set(frozen_row) - set(replay_row)
                if missing:
                    raise ReplayValidationError(
                        "Final Full parity failed at "
                        f"dynamic_core_priority_rows[{index}]: "
                        f"missing stored keys {sorted(missing)}"
                    )
                projected_rows.append(
                    {key: replay_row[key] for key in frozen_row}
                )
            replay_value = projected_rows
        _assert_close(
            full[frozen_field],
            replay_value,
            path=frozen_field,
            tolerance=tolerance,
        )
        checked.append(frozen_field)

    _assert_close(
        full.get("oc_detected") or full.get("oc_detected_clauses") or [],
        replayed.get("oc_detected_clauses") or [],
        path="oc_detected_clauses",
        tolerance=tolerance,
    )
    checked.append("oc_detected_clauses")
    return checked


def evaluate_nodes(result: dict[str, Any], nodes: list[str], variant: str) -> dict[str, Any]:
    scc_ids = list(result.get("scc_clause_ids") or [])
    scc_set = set(scc_ids)
    input_node_set = set(nodes)
    if not input_node_set.issubset(scc_set):
        raise ReplayValidationError("Evaluated core contains nodes outside the frozen SCC")
    nodes = [cid for cid in scc_ids if cid in input_node_set]
    node_set = set(nodes)
    total = max(1, len(scc_ids))
    risk_ids = list(
        dict.fromkeys(
            result.get("injected_risk_nodes")
            or result.get("injected_evidence_nodes")
            or []
        )
    )
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
        "scc_clause_ids": scc_ids,
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
        "core_evidence_contains_all_risk_nodes": bool(
            risk_ids and all(cid in node_set for cid in risk_ids)
        ),
        "core_evidence_risk_nodes_retained": retained(risk_ids),
        "core_evidence_risk_coverage": coverage(risk_ids),
        "core_evidence_contains_any_affected_node": bool(set(affected_ids) & node_set),
        "core_evidence_contains_all_affected_nodes": bool(
            affected_ids and all(cid in node_set for cid in affected_ids)
        ),
        "core_evidence_contains_any_valuable_node": bool(set(valuable_ids) & node_set),
        "core_evidence_contains_all_valuable_nodes": bool(
            valuable_ids and all(cid in node_set for cid in valuable_ids)
        ),
        "injected_risk_nodes": risk_ids,
        "injected_affected_nodes": affected_ids,
        "source_full_result_file": result.get("_source_result_file"),
        "stage2_replay_no_llm_calls": True,
        "replay_llm_calls": 0,
        "source_trace_llm_calls": result.get("llm_calls"),
        "replay_completed_at_iso": now_iso(),
    }


def replay_paired_core(
    case: dict[str, Any],
    full: dict[str, Any],
    *,
    float_tolerance: float = DEFAULT_FLOAT_TOLERANCE,
) -> dict[str, dict[str, Any]]:
    """Replay one frozen trace and return the two strictly paired policies."""
    identity_audit = validate_case_identity(case, full)
    trace, trace_audit = validate_trace(full)
    mcgs, llm = make_replay_mcgs(full)
    scc_ids = list(full["scc_clause_ids"])

    recompute_history: list[dict[str, Any]] = []
    locked_history: list[dict[str, Any]] = []
    previous_recompute: list[str] = []
    locked_admission_order: list[str] = []
    final_summary: dict[str, Any] | None = None

    for event in trace:
        apply_trace_event(mcgs, event)
        prefix = int(event["completion_index"])
        summary = mcgs._build_result(
            elapsed=0.0,
            llm_calls=0,
            tt_hits=sum(1 for item in trace[:prefix] if item.get("is_tt_hit")),
            total_iters=prefix,
        )
        proposal = list(summary.get("evidence_risk_subgraph_nodes") or [])
        proposal_set = set(proposal)
        previous_set = set(previous_recompute)
        priority_rows = summary.get("dynamic_core_priority_rows") or []
        selector_policy = (
            priority_rows[0].get("policy")
            if priority_rows and isinstance(priority_rows[0], dict)
            else None
        )
        recompute_history.append(
            {
                "completion_index": prefix,
                "iteration": event.get("iteration"),
                "cap": summary.get("evidence_subgraph_cap"),
                "core_nodes": proposal,
                "added_nodes": [cid for cid in proposal if cid not in previous_set],
                "removed_nodes": [
                    cid for cid in previous_recompute if cid not in proposal_set
                ],
                "selector_policy": selector_policy,
            }
        )
        previous_recompute = proposal

        locked_admission_order, admitted = advance_locked_core(
            locked_admission_order,
            summary,
            scc_ids=scc_ids,
        )
        locked_set = set(locked_admission_order)
        locked_nodes = [cid for cid in scc_ids if cid in locked_set]
        locked_history.append(
            {
                "completion_index": prefix,
                "iteration": event.get("iteration"),
                "cap": summary.get("evidence_subgraph_cap"),
                "proposal_nodes": proposal,
                "core_nodes": locked_nodes,
                "admitted_nodes": admitted,
                "removed_nodes": [],
            }
        )
        final_summary = summary

    if llm.calls != 0:
        raise ReplayValidationError(f"Replay unexpectedly made {llm.calls} LLM calls")
    if final_summary is None:
        raise ReplayValidationError("Replay produced no final evidence summary")

    parity_fields = assert_final_full_parity(
        full,
        final_summary,
        tolerance=float_tolerance,
    )
    final_recompute = list(final_summary["evidence_risk_subgraph_nodes"])
    final_locked_set = set(locked_admission_order)
    final_locked = [cid for cid in scc_ids if cid in final_locked_set]
    shared_cap = int(final_summary["evidence_subgraph_cap"])
    if len(final_recompute) > shared_cap or len(final_locked) > shared_cap:
        raise ReplayValidationError("A replayed policy exceeds the shared final cap")
    for previous, current in zip(locked_history, locked_history[1:]):
        if not set(previous["core_nodes"]).issubset(current["core_nodes"]):
            raise ReplayValidationError("Locked core history is not monotone")

    common_audit = {
        **identity_audit,
        **trace_audit,
        "paired_trace_sha256": trace_audit["trace_sha256"],
        "shared_core_cap": shared_cap,
        "final_full_parity": True,
        "final_full_parity_fields": parity_fields,
        "float_tolerance": float_tolerance,
        "replay_engine": "prefix_cumulative_state_v1",
        "shared_selector_components": [
            "OC/core signal",
            "relation seeding",
            "critical-pair protection",
            "pair closure",
        ],
    }

    recompute_out = evaluate_nodes(full, final_recompute, FULL_RECOMPUTE)
    recompute_out.update(
        {
            **common_audit,
            "core_update_policy": "recompute_each_prefix_allow_replacement",
            "core_history": recompute_history,
            "replacement_count": sum(
                len(item["removed_nodes"]) for item in recompute_history
            ),
        }
    )
    locked_out = evaluate_nodes(full, final_locked, LOCKED_NO_REPLACEMENT)
    locked_out.update(
        {
            **common_audit,
            "core_update_policy": "first_admission_locked_no_replacement",
            "core_history": locked_history,
            "admission_order": locked_admission_order,
            "replacement_count": 0,
        }
    )
    return {
        FULL_RECOMPUTE: recompute_out,
        LOCKED_NO_REPLACEMENT: locked_out,
    }


def _load_plan_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ReplayValidationError(f"Case plan does not exist: {path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("cases")
        if not isinstance(payload, list) or not all(
            isinstance(row, dict) for row in payload
        ):
            raise ReplayValidationError(f"Case plan is not a list of objects: {path}")
        return [copy.deepcopy(row) for row in payload]
    return [dict(row) for row in csv.DictReader(path.open(encoding="utf-8"))]


def _composition_identity(
    case: dict[str, Any],
    composition_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    source_name = Path(str(case.get("source_result_file") or "")).name
    model = str(case.get("model") or "")
    domain = str(_canonical(case, "domain") or "")
    family = str(_canonical(case, "template") or "")
    matches = [
        row
        for row in composition_rows
        if Path(str(row.get("result_file") or "")).name == source_name
        and str(row.get("model") or "") == model
        and str(row.get("domain") or "") == domain
        and str(row.get("template") or "") == family
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ReplayValidationError(
            f"Case composition identity is ambiguous for {case.get('case_id')}: "
            f"{len(matches)} rows"
        )
    row = matches[0]
    return {
        "root_node": row.get("root") or None,
        "witness_node": row.get("witness") or None,
        "bridge_node": row.get("bridge") or None,
        "affected_count": int(row.get("affected_count") or 0),
        "source_result_basename": source_name,
    }


def load_selected_cases(
    plan_paths: list[Path],
    case_orders: list[int],
    *,
    case_csv: Path = DEFAULT_CASE_CSV,
) -> list[dict[str, Any]]:
    """Load canonical plan rows; never source replay identity from old summaries."""
    wanted = set(case_orders)
    if len(wanted) != len(case_orders) or any(order <= 0 for order in case_orders):
        raise ReplayValidationError("Case orders must be unique positive integers")
    composition_rows = list(csv.DictReader(case_csv.open(encoding="utf-8")))
    selected: list[dict[str, Any]] = []
    seen_orders: set[int] = set()
    seen_ids: set[str] = set()
    for plan_path in plan_paths:
        for row in _load_plan_rows(plan_path):
            order = int(_canonical(row, "case_order") or 0)
            if order not in wanted:
                continue
            case_id = str(_canonical(row, "case_id") or row.get("case_id") or "")
            if order in seen_orders:
                raise ReplayValidationError(f"Duplicate case order across plans: {order}")
            if not case_id or case_id in seen_ids:
                raise ReplayValidationError(f"Missing/duplicate canonical case_id: {case_id}")
            if not row.get("source_result_file"):
                raise ReplayValidationError(
                    f"Canonical plan case {case_id} has no source_result_file"
                )
            row["case_id"] = case_id
            row["case_order"] = order
            row["canonical_case_id"] = case_id
            row["canonical_case_order"] = order
            row["canonical_domain"] = str(_canonical(row, "domain") or "")
            row["canonical_scc_id"] = str(_canonical(row, "scc_id") or "")
            row["canonical_scc_size"] = int(_canonical(row, "scc_size") or 0)
            row["canonical_template"] = str(_canonical(row, "template") or "")
            row["canonical_scc_size_bin"] = row.get(
                "canonical_scc_size_bin"
            ) or scc_size_bin(row["canonical_scc_size"])
            composition = _composition_identity(row, composition_rows)
            if composition is None and _planned_injection(row) is None:
                raise ReplayValidationError(
                    f"Case {case_id} has neither a case_composition identity nor "
                    "planned_injection_identity"
                )
            row["_composition_identity"] = composition
            row["_case_plan_source"] = str(plan_path.resolve())
            selected.append(row)
            seen_orders.add(order)
            seen_ids.add(case_id)
    missing = wanted - seen_orders
    if missing:
        raise ReplayValidationError(f"Missing case orders from canonical plans: {sorted(missing)}")
    selected.sort(key=lambda row: int(row["case_order"]))
    return selected


def load_source_full(case: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    """Select one original main-experiment SA row by model/domain, not SCC number."""
    source_path = resolve_source_result_path(case["source_result_file"])
    source_bytes = source_path.read_bytes()
    source_file_sha256 = hashlib.sha256(source_bytes).hexdigest()
    expected_file_sha256 = str(case.get("source_result_sha256") or "").removeprefix(
        "sha256:"
    )
    if expected_file_sha256 and source_file_sha256 != expected_file_sha256:
        raise ReplayValidationError(
            f"Original result-file SHA-256 mismatch for {case.get('case_id')}"
        )
    payload = json.loads(source_bytes)
    rows = payload if isinstance(payload, list) else [payload]
    model = str(case.get("model") or "")
    domain = str(_canonical(case, "domain") or "")
    candidates = [
        (index, row)
        for index, row in enumerate(rows)
        if isinstance(row, dict)
        and row.get("method") == "sa-mcgs"
        and str(row.get("model") or "") == model
        and str(row.get("domain") or "") == domain
    ]
    if len(candidates) != 1:
        raise ReplayValidationError(
            f"Expected exactly one original SA-MCGS row for "
            f"model={model}, domain={domain}; found {len(candidates)} in {source_path}"
        )
    source_index, source = candidates[0]
    source_record_sha256 = stable_sha256(source)
    expected_record_sha256 = str(
        case.get("source_sa_record_sha256") or ""
    ).removeprefix("sha256:")
    if expected_record_sha256 and source_record_sha256 != expected_record_sha256:
        raise ReplayValidationError(
            f"Original SA-record SHA-256 mismatch for {case.get('case_id')}"
        )
    full = copy.deepcopy(source)
    full["_source_result_file"] = str(source_path)
    full["_source_record_index"] = source_index
    full["_source_file_sha256"] = source_file_sha256
    full["_source_record_sha256"] = source_record_sha256
    full["_source_original_case_id"] = source.get("case_id")
    full["_source_original_case_order"] = source.get("case_order")
    # Canonical labels are plan-owned. Physical SCC and injection fields remain
    # untouched and are validated before replay.
    full["case_id"] = str(_canonical(case, "case_id") or case["case_id"])
    full["case_order"] = int(_canonical(case, "case_order") or case["case_order"])
    return source_path, full


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


def write_tables(output_dir: Path, cases: list[dict[str, Any]]) -> None:
    case_meta = {row["case_id"]: row for row in cases}
    rows: list[dict[str, Any]] = []
    for path in sorted((output_dir / "results").glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        meta = case_meta.get(result.get("case_id"), {})
        invalid = bool(result.get("component_ablation_error"))
        rows.append(
            {
                "variant": VARIANT_LABELS.get(
                    result.get("ablation_variant"), result.get("ablation_variant")
                ),
                "variant_key": result.get("ablation_variant"),
                "case_id": result.get("case_id"),
                "case_order": int(
                    meta.get("canonical_case_order")
                    or result.get("case_order")
                    or 0
                ),
                "domain": meta.get("canonical_domain") or result.get("domain"),
                "scc_id": meta.get("canonical_scc_id") or result.get("scc_id"),
                "scc_size": int(
                    meta.get("canonical_scc_size") or result.get("scc_size") or 0
                ),
                "scc_bin": meta.get("canonical_scc_size_bin") or "",
                "template": meta.get("canonical_template") or "",
                "invalid": invalid,
                "root_at_3": None if invalid else row_metric(result, "root_at_3"),
                "risk_any": None if invalid else row_metric(result, "risk_any"),
                "risk_all": None if invalid else row_metric(result, "risk_all"),
                "risk_coverage": None
                if invalid
                else result.get("core_evidence_risk_coverage"),
                "compression": None if invalid else row_metric(result, "compression"),
                "core_size": None if invalid else row_metric(result, "core_size"),
                "cumulative_evictions": None
                if invalid
                else result.get("replacement_count"),
                "case_uid": result.get("case_uid"),
                "physical_scc_uid": result.get("physical_scc_uid"),
                "trace_sha256": result.get("paired_trace_sha256"),
                "result_file": str(path),
            }
        )
    rows.sort(key=lambda row: (row["case_order"], row["variant_key"] or ""))
    if not rows:
        return

    write_csv(output_dir / "summary_stage2_paired_core_cases.csv", rows)
    baseline = [
        row
        for row in rows
        if row["variant_key"] == FULL_RECOMPUTE and not row["invalid"]
    ]
    baseline_metrics = {
        "Root@3": mean_bool([row["root_at_3"] for row in baseline]),
        "Risk-any": mean_bool([row["risk_any"] for row in baseline]),
        "Risk-all": mean_bool([row["risk_all"] for row in baseline]),
        "Compression": mean([row["compression"] for row in baseline]),
        "Avg core size": mean([row["core_size"] for row in baseline]),
    }

    table_rows: list[dict[str, Any]] = []
    for variant in REPLAY_VARIANTS:
        attempted = [row for row in rows if row["variant_key"] == variant]
        items = [row for row in attempted if not row["invalid"]]
        root = mean_bool([row["root_at_3"] for row in items])
        risk_any = mean_bool([row["risk_any"] for row in items])
        risk_all = mean_bool([row["risk_all"] for row in items])
        compression = mean([row["compression"] for row in items])
        core_size = mean([row["core_size"] for row in items])
        evictions = mean([row["cumulative_evictions"] for row in items])
        table_rows.append(
            {
                "Variant": VARIANT_LABELS[variant],
                "Attempted": len(attempted),
                "Valid": len(items),
                "Invalid": len(attempted) - len(items),
                "Root@3": root,
                "Risk-any": risk_any,
                "Risk-all": risk_all,
                "Risk coverage": mean([row["risk_coverage"] for row in items]),
                "Compression": compression,
                "Avg core size": core_size,
                "Avg cumulative evictions": evictions,
                "Delta Root@3": None
                if root is None or baseline_metrics["Root@3"] is None
                else root - baseline_metrics["Root@3"],
                "Delta Risk-any": None
                if risk_any is None or baseline_metrics["Risk-any"] is None
                else risk_any - baseline_metrics["Risk-any"],
                "Delta Risk-all": None
                if risk_all is None or baseline_metrics["Risk-all"] is None
                else risk_all - baseline_metrics["Risk-all"],
                "Delta Compression": None
                if compression is None or baseline_metrics["Compression"] is None
                else compression - baseline_metrics["Compression"],
                "Delta Avg core size": None
                if core_size is None or baseline_metrics["Avg core size"] is None
                else core_size - baseline_metrics["Avg core size"],
            }
        )

    title = "Stage 2 Paired Dynamic-vs-Locked Core Replay"
    write_markdown_table(output_dir / "stage2_paired_core_table.md", title, table_rows)
    write_csv(output_dir / "stage2_paired_core_table.csv", table_rows)

    bin_rows: list[dict[str, Any]] = []
    for bin_name in sorted({row["scc_bin"] for row in rows if row["scc_bin"]}):
        bin_baseline = [
            row
            for row in rows
            if row["scc_bin"] == bin_name
            and row["variant_key"] == FULL_RECOMPUTE
            and not row["invalid"]
        ]
        baseline_all = mean_bool([row["risk_all"] for row in bin_baseline])
        for variant in REPLAY_VARIANTS:
            items = [
                row
                for row in rows
                if row["scc_bin"] == bin_name
                and row["variant_key"] == variant
                and not row["invalid"]
            ]
            if not items:
                continue
            risk_all = mean_bool([row["risk_all"] for row in items])
            bin_rows.append(
                {
                    "SCC bin": bin_name,
                    "Variant": VARIANT_LABELS[variant],
                    "N": len(items),
                    "Root@3": mean_bool([row["root_at_3"] for row in items]),
                    "Risk-any": mean_bool([row["risk_any"] for row in items]),
                    "Risk-all": risk_all,
                    "Compression": mean([row["compression"] for row in items]),
                    "Avg core size": mean([row["core_size"] for row in items]),
                    "Avg cumulative evictions": mean(
                        [row["cumulative_evictions"] for row in items]
                    ),
                    "Delta Risk-all": None
                    if risk_all is None or baseline_all is None
                    else risk_all - baseline_all,
                }
            )
    write_markdown_table(
        output_dir / "stage2_paired_core_by_scc_bin.md",
        f"{title} by SCC Size Bin",
        bin_rows,
    )
    write_csv(output_dir / "stage2_paired_core_by_scc_bin.csv", bin_rows)

    report = [
        f"# {title} Report",
        "",
        "Both policies are derived from the same frozen Full trace. No LLM is called.",
        "Every valid case passed original-main-row identity/trace validation and final",
        "Full parity.",
        "Both policies consume the same selector proposal at every prefix. The locked policy",
        "changes only admission/eviction: OC signals, relation seeding, critical-pair",
        "protection, pair closure, scoring thresholds, and cap remain in the shared selector.",
        "Root@3 is inherited from the shared frozen search trajectory and is therefore not a",
        "core-policy effect.",
        "Cases sharing physical_scc_uid are dependent injection conditions. Aggregate means",
        "are descriptive only; this report does not apply naive i.i.d. significance tests.",
        "",
        "The legacy Stage-1 summary is diagnostic only. The deprecated rebuttal",
        "`monotone-core` result and its -25 point claim are not reused.",
        "",
        (output_dir / "stage2_paired_core_table.md").read_text(encoding="utf-8"),
        "",
        (output_dir / "stage2_paired_core_by_scc_bin.md").read_text(encoding="utf-8"),
    ]
    (output_dir / "stage2_paired_core_report.md").write_text(
        "\n".join(report).strip() + "\n",
        encoding="utf-8",
    )


def error_result(
    case: dict[str, Any],
    variant: str,
    source_path: Path | None,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "case_order": int(_canonical(case, "case_order") or 0),
        "domain": _canonical(case, "domain"),
        "scc_id": _canonical(case, "scc_id"),
        "scc_size": int(_canonical(case, "scc_size") or 0),
        "ablation_variant": variant,
        "ablation_label": VARIANT_LABELS[variant],
        "component_ablation_error": str(exc),
        "error_type": type(exc).__name__,
        "traceback": traceback.format_exc(),
        "source_full_result_file": str(source_path) if source_path else None,
        "stage2_replay_no_llm_calls": True,
        "replay_llm_calls": 0,
        "final_full_parity": False,
    }


def run(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ReplayValidationError(
            f"Refusing to overwrite a non-empty replay directory: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results").mkdir(exist_ok=True)
    cases = load_selected_cases(
        args.case_plans,
        args.case_orders,
        case_csv=args.case_csv,
    )
    atomic_write_json(output_dir / "case_plan_resolved.json", cases)
    plan_rows = [
        {
            "case_order": case["case_order"],
            "case_id": case["case_id"],
            "model": case.get("model"),
            "domain": case.get("canonical_domain"),
            "scc_id_diagnostic": case.get("canonical_scc_id"),
            "scc_size": case.get("canonical_scc_size"),
            "scc_bin": case.get("canonical_scc_size_bin"),
            "requested_family": case.get("canonical_template"),
            "source_result_file": case.get("source_result_file"),
            "case_plan_source": case.get("_case_plan_source"),
            "has_planned_scc_ids": _planned_scc_ids(case) is not None,
            "has_planned_injection": _planned_injection(case) is not None,
            "has_composition_identity": case.get("_composition_identity") is not None,
        }
        for case in cases
    ]
    write_csv(output_dir / "case_plan_resolved.csv", plan_rows)
    if args.diagnostic_summary is not None:
        shutil.copy2(
            args.diagnostic_summary,
            output_dir / "diagnostic_only_legacy_stage1_summary.csv",
        )

    atomic_write_json(
        output_dir / "run_config.json",
        {
            "created_at": now_iso(),
            "stage": "stage2_paired_dynamic_vs_locked_core_replay",
            "case_plan_sources": [str(path) for path in args.case_plans],
            "case_composition_source": str(args.case_csv),
            "diagnostic_only_legacy_summary": (
                str(args.diagnostic_summary) if args.diagnostic_summary else None
            ),
            "case_orders": args.case_orders,
            "variants": REPLAY_VARIANTS,
            "no_new_llm_calls": True,
            "float_tolerance": args.float_tolerance,
            "case_identity_policy": (
                "canonical plan ID/order + original main SA row selected by model/domain + "
                "exact physical scc_clause_ids and injection witness/family; numeric SCC ID "
                "is diagnostic only"
            ),
            "deprecated_results_reused": False,
            "legacy_stage1_summary_used_as_replay_source": False,
        },
    )
    status = {
        "run_id": output_dir.name,
        "stage": "stage2_paired_core_replay",
        "started_at": now_iso(),
        "total_cases": len(cases),
        "variants": REPLAY_VARIANTS,
        "total_case_variants": len(cases) * len(REPLAY_VARIANTS),
        "completed_case_variants": 0,
        "failed_case_variants": 0,
        "replayable_cases": 0,
        "blocked_cases": 0,
        "remaining_case_variants": len(cases) * len(REPLAY_VARIANTS),
        "no_new_llm_calls": True,
    }
    atomic_write_json(output_dir / "status.json", status)

    completed = 0
    failed = 0
    replayable_cases = 0
    blocked_cases = 0
    manifest: list[dict[str, Any]] = []
    for case in cases:
        source_path: Path | None = None
        try:
            source_path, full = load_source_full(case)
            paired = replay_paired_core(
                case,
                full,
                float_tolerance=args.float_tolerance,
            )
            for variant, replay_out in paired.items():
                replay_out["canonical_scc_size_bin"] = case.get(
                    "canonical_scc_size_bin"
                )
                atomic_write_json(
                    output_dir / "results" / f"{case['case_id']}__{variant}.json",
                    replay_out,
                )
                completed += 1
            replayable_cases += 1
            manifest.append(
                {
                    "case_id": case["case_id"],
                    "case_order": int(_canonical(case, "case_order") or 0),
                    "status": "replayed",
                    "case_uid": paired[FULL_RECOMPUTE]["case_uid"],
                    "physical_scc_uid": paired[FULL_RECOMPUTE]["physical_scc_uid"],
                    "trace_sha256": paired[FULL_RECOMPUTE]["paired_trace_sha256"],
                    "trace_events": paired[FULL_RECOMPUTE]["trace_events"],
                    "source_record_index": paired[FULL_RECOMPUTE][
                        "source_record_index"
                    ],
                    "source_record_sha256": paired[FULL_RECOMPUTE][
                        "source_record_sha256"
                    ],
                    "source_full_result_file": str(source_path),
                }
            )
        except Exception as exc:
            blocked_cases += 1
            failed += len(REPLAY_VARIANTS)
            for variant in REPLAY_VARIANTS:
                atomic_write_json(
                    output_dir / "results" / f"{case['case_id']}__{variant}.json",
                    error_result(case, variant, source_path, exc),
                )
                completed += 1
            manifest.append(
                {
                    "case_id": case.get("case_id"),
                    "case_order": int(_canonical(case, "case_order") or 0),
                    "status": "blocked",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "source_full_result_file": str(source_path) if source_path else None,
                }
            )

        status.update(
            {
                "updated_at": now_iso(),
                "completed_case_variants": completed,
                "failed_case_variants": failed,
                "replayable_cases": replayable_cases,
                "blocked_cases": blocked_cases,
                "remaining_case_variants": status["total_case_variants"] - completed,
            }
        )
        atomic_write_json(output_dir / "status.json", status)

    atomic_write_json(output_dir / "replay_manifest.json", manifest)
    write_tables(output_dir, cases)
    status.update(
        {
            "updated_at": now_iso(),
            "completed_at": now_iso(),
            "completed_case_variants": completed,
            "failed_case_variants": failed,
            "remaining_case_variants": status["total_case_variants"] - completed,
            "summary_table": str(output_dir / "stage2_paired_core_table.md"),
            "summary_cases": str(output_dir / "summary_stage2_paired_core_cases.csv"),
            "manifest": str(output_dir / "replay_manifest.json"),
        }
    )
    atomic_write_json(output_dir / "status.json", status)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay paired dynamic-vs-locked core policies from frozen Full traces."
    )
    parser.add_argument(
        "--case-plan",
        dest="case_plans",
        action="append",
        type=Path,
        default=None,
        help=(
            "Canonical JSON/CSV case plan containing source_result_file; repeat for "
            "multiple plan shards. Defaults to the original main20 + extra-long20 plans."
        ),
    )
    parser.add_argument("--case-csv", type=Path, default=DEFAULT_CASE_CSV)
    parser.add_argument(
        "--diagnostic-summary",
        type=Path,
        default=DEFAULT_DIAGNOSTIC_SUMMARY,
        help="Legacy Stage-1 summary copied for diagnosis only; never used as replay input.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--case-orders", nargs="+", type=int, default=list(range(1, 41)))
    parser.add_argument(
        "--float-tolerance",
        type=float,
        default=DEFAULT_FLOAT_TOLERANCE,
    )
    args = parser.parse_args()
    if args.float_tolerance <= 0:
        parser.error("--float-tolerance must be positive")
    if args.output_dir is None:
        run_id = time.strftime(
            "stage2_paired_core_replay_40case_%Y%m%d_%H%M%S",
            time.localtime(),
        )
        args.output_dir = DEFAULT_RUNS_DIR / run_id
    if args.case_plans is None:
        args.case_plans = list(DEFAULT_CASE_PLANS)
    args.case_plans = [path.resolve() for path in args.case_plans]
    args.case_csv = args.case_csv.resolve()
    if args.diagnostic_summary is not None:
        args.diagnostic_summary = args.diagnostic_summary.resolve()
    args.output_dir = args.output_dir.resolve()
    return args


if __name__ == "__main__":
    run(parse_args())

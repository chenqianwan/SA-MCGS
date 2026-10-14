"""Regression tests for the paired dynamic-vs-locked core replay."""
from __future__ import annotations

import argparse
import copy
import json

import pytest

from emnlp2026_discussion import run_component_ablation_stage2_core_replay as replay


def _load_frozen_case(order: int = 1):
    case = replay.load_selected_cases(
        replay.DEFAULT_CASE_PLANS,
        [order],
        case_csv=replay.DEFAULT_CASE_CSV,
    )[0]
    source_path, full = replay.load_source_full(case)
    return case, source_path, full


def test_locked_core_admission_never_replaces_and_obeys_cap() -> None:
    scc_ids = ["a", "b", "c", "d"]
    first = {
        "evidence_subgraph_cap": 3,
        "evidence_risk_subgraph_nodes": ["a", "b"],
        "dynamic_core_priority_rows": [
            {"clause_id": "a", "selected": True},
            {"clause_id": "b", "selected": True},
        ],
    }
    second = {
        "evidence_subgraph_cap": 3,
        "evidence_risk_subgraph_nodes": ["c", "d"],
        "dynamic_core_priority_rows": [
            {"clause_id": "c", "selected": True},
            {"clause_id": "d", "selected": True},
        ],
    }

    locked, admitted = replay.advance_locked_core([], first, scc_ids=scc_ids)
    assert locked == ["a", "b"]
    assert admitted == ["a", "b"]

    updated, admitted = replay.advance_locked_core(locked, second, scc_ids=scc_ids)
    assert updated == ["a", "b", "c"]
    assert admitted == ["c"]
    assert set(locked).issubset(updated)
    assert len(updated) == second["evidence_subgraph_cap"]


def test_source_loader_uses_original_main_row_and_plan_owned_labels() -> None:
    case, source_path, full = _load_frozen_case()

    assert source_path.is_relative_to(replay.REPO_ROOT)
    assert "experiments/cross_domain/results" in source_path.as_posix()
    assert full["case_id"] == case["canonical_case_id"]
    assert full["case_order"] == case["canonical_case_order"]
    assert full["_source_original_case_id"] is None
    assert full["_source_original_case_order"] is None
    audit = replay.validate_case_identity(case, full)
    assert audit["node_count"] == len(full["scc_clause_ids"])
    assert audit["canonical_scc_id_diagnostic"] == case["canonical_scc_id"]


def test_source_loader_rejects_a_pinned_record_hash_mismatch() -> None:
    case, _source_path, _full = _load_frozen_case()
    corrupted_plan = copy.deepcopy(case)
    corrupted_plan["source_sa_record_sha256"] = "sha256:" + "0" * 64

    with pytest.raises(replay.ReplayValidationError, match="SA-record SHA-256"):
        replay.load_source_full(corrupted_plan)


def test_identity_rejects_wrong_physical_scc_or_injection_witness() -> None:
    case, _source_path, full = _load_frozen_case()
    wrong_nodes = copy.deepcopy(case)
    wrong_nodes["planned_scc_clause_ids"] = list(reversed(full["scc_clause_ids"]))
    with pytest.raises(replay.ReplayValidationError, match="physical SCC"):
        replay.validate_case_identity(wrong_nodes, full)

    wrong_witness = copy.deepcopy(case)
    wrong_witness["_composition_identity"]["witness_node"] = "not-the-witness"
    with pytest.raises(replay.ReplayValidationError, match="case_composition"):
        replay.validate_case_identity(wrong_witness, full)


def test_trace_validation_rejects_noncontiguous_completion_order() -> None:
    _case, _source_path, full = _load_frozen_case()
    corrupted = copy.deepcopy(full)
    corrupted["trace_events"][0]["completion_index"] = 2

    with pytest.raises(replay.ReplayValidationError, match="contiguous completion order"):
        replay.validate_trace(corrupted)


def test_frozen_full_trace_replays_without_llm_and_with_final_parity() -> None:
    case, _source_path, full = _load_frozen_case()
    paired = replay.replay_paired_core(case, full)
    recompute = paired[replay.FULL_RECOMPUTE]
    locked = paired[replay.LOCKED_NO_REPLACEMENT]

    assert recompute["final_full_parity"] is True
    assert recompute["evidence_risk_subgraph_nodes"] == full[
        "evidence_risk_subgraph_nodes"
    ]
    assert recompute["replay_llm_calls"] == 0
    assert locked["replay_llm_calls"] == 0
    assert recompute["paired_trace_sha256"] == locked["paired_trace_sha256"]
    assert recompute["physical_scc_uid"] == locked["physical_scc_uid"]
    assert recompute["shared_core_cap"] == locked["shared_core_cap"]
    assert all(not step["removed_nodes"] for step in locked["core_history"])
    for previous, current in zip(locked["core_history"], locked["core_history"][1:]):
        assert set(previous["core_nodes"]).issubset(current["core_nodes"])
        assert len(current["core_nodes"]) <= current["cap"]


def test_final_full_parity_failure_blocks_both_policies() -> None:
    case, _source_path, full = _load_frozen_case()
    corrupted = copy.deepcopy(full)
    node = next(iter(corrupted["scores"]))
    corrupted["scores"][node] += 0.1

    with pytest.raises(replay.ReplayValidationError, match="Final Full parity failed"):
        replay.replay_paired_core(case, corrupted)


def test_runner_emits_only_invalid_artifacts_when_full_parity_fails(tmp_path) -> None:
    case, _source_path, full = _load_frozen_case()
    source_row = {
        key: copy.deepcopy(value)
        for key, value in full.items()
        if not key.startswith("_")
    }
    node = next(iter(source_row["scores"]))
    source_row["scores"][node] += 0.1
    source_path = tmp_path / "corrupted_original_main.json"
    source_path.write_text(json.dumps([source_row]), encoding="utf-8")

    plan_case = {
        key: copy.deepcopy(value)
        for key, value in case.items()
        if not key.startswith("_")
    }
    plan_case["source_result_file"] = str(source_path)
    plan_case["planned_scc_clause_ids"] = list(full["scc_clause_ids"])
    plan_case["planned_injection_identity"] = replay.source_injection_identity(
        full,
        requested_family=case["canonical_template"],
    )
    plan_path = tmp_path / "canonical_case_plan.json"
    plan_path.write_text(json.dumps([plan_case]), encoding="utf-8")
    case_csv = tmp_path / "empty_case_composition.csv"
    case_csv.write_text(
        "model,domain,scc_id,scc_size,template,root,witness,bridge,"
        "affected_count,llm_calls,time,result_file\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "paired_replay"
    replay.run(
        argparse.Namespace(
            output_dir=output_dir,
            case_plans=[plan_path],
            case_orders=[case["case_order"]],
            case_csv=case_csv,
            diagnostic_summary=None,
            float_tolerance=replay.DEFAULT_FLOAT_TOLERANCE,
        )
    )

    status = json.loads((output_dir / "status.json").read_text(encoding="utf-8"))
    results = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (output_dir / "results").glob("*.json")
    ]
    assert status["replayable_cases"] == 0
    assert status["blocked_cases"] == 1
    assert status["failed_case_variants"] == 2
    assert len(results) == 2
    assert all(result["final_full_parity"] is False for result in results)
    assert all(
        "Final Full parity failed" in result["component_ablation_error"]
        for result in results
    )

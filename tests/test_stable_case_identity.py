"""Regression tests for stable rebuttal case identity."""
from __future__ import annotations

import copy
import csv
import json
from types import SimpleNamespace

import pytest

from emnlp2026_discussion import run_component_ablation_stage0 as ablation
from emnlp2026_discussion import run_cost_audit_clean as cost
from emnlp2026_discussion import run_lea_full_baseline as lea
from src.models.clause import Clause
from src.models.graph import DependencyGraph, DependencyType, Edge
from src.modules.tarjan import TarjanSCCDetector


def _same_size_scc_graph(*, first_edge_type: DependencyType = DependencyType.REFERENCES) -> DependencyGraph:
    clauses = {
        node_id: Clause(id=node_id, title=node_id.upper(), content=f"Text for {node_id}")
        for node_id in ("a", "b", "c", "d")
    }
    edges = [
        Edge(source="a", target="b", dependency_type=first_edge_type),
        Edge(source="b", target="a", dependency_type=DependencyType.REFERENCES),
        Edge(source="c", target="d", dependency_type=DependencyType.REFERENCES),
        Edge(source="d", target="c", dependency_type=DependencyType.REFERENCES),
    ]
    return TarjanSCCDetector().detect(DependencyGraph(clauses=clauses, edges=edges))


def _injection_payload() -> dict:
    return {
        "inject_profile": "memory_stress",
        "inject_profile_version": "fixture_v1",
        "injected_node": "a",
        "injected_witness_node": "b",
        "injected_witness_distance": 1,
        "injected_bridge_node": None,
        "injected_bridge_distance": None,
        "injected_risk_nodes": ["a", "b"],
        "injected_evidence_nodes": ["a", "b"],
        "injected_affected_nodes": [],
        "injected_conflict_family": "direct_mutex",
        "injected_conflict_severity": "critical",
        "injected_conflict_template": "fixture_direct_mutex_critical",
    }


def _validated_case(graph: DependencyGraph) -> dict:
    injection = cost.injection_identity(
        _injection_payload(),
        requested_template="direct_mutex",
    )
    other_scc = next(scc for scc in graph.sccs if set(scc.clause_ids) == {"c", "d"})
    case = {
        "case_id": "canonical-case",
        "case_order": 17,
        "model": "gpt-4o",
        "domain": "fixture",
        # Deliberately point the legacy numeric label at the other same-size SCC.
        "scc_id": other_scc.id,
        "scc_size": 2,
        "template": "direct_mutex",
        "planned_scc_clause_ids": ["a", "b"],
        "planned_injection_identity": injection,
    }
    report = cost.validate_case_plan([case], {"fixture": graph})
    assert report["validated_cases"] == 1
    return case


def _result_row(clause_ids: list[str]) -> dict:
    return {
        "method": "sa-mcgs",
        "model": "gpt-4o",
        "domain": "fixture",
        "scc_id": "unstable-diagnostic-label",
        "scc_size": len(clause_ids),
        "scc_clause_ids": clause_ids,
        **_injection_payload(),
    }


def test_same_size_scc_is_selected_by_node_identity_not_numeric_id() -> None:
    graph = _same_size_scc_graph()
    case = _validated_case(graph)

    resolved = cost.find_scc(graph, case)

    assert resolved.clause_ids == ["a", "b"]
    assert set(resolved.clause_ids) != {"c", "d"}


def test_preflight_fails_when_typed_edges_change() -> None:
    original = _same_size_scc_graph()
    case = _validated_case(original)
    changed = _same_size_scc_graph(first_edge_type=DependencyType.CONSTRAINS)

    with pytest.raises(cost.StableCaseIdentityError, match="identity mismatch"):
        cost.validate_case_plan([copy.deepcopy(case)], {"fixture": changed})


def test_resume_rejects_same_size_different_node_set() -> None:
    graph = _same_size_scc_graph()
    case = _validated_case(graph)

    with pytest.raises(cost.StableCaseIdentityError, match="identity mismatch"):
        cost.validate_result_case_identity(_result_row(["c", "d"]), case, graph)


def test_locked_full_requires_one_fingerprint_match(tmp_path) -> None:
    graph = _same_size_scc_graph()
    case = _validated_case(graph)
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps([_result_row(["a", "b"]), _result_row(["c", "d"])]),
        encoding="utf-8",
    )
    case["source_result_file"] = str(source)
    args = SimpleNamespace(
        model="gpt-4o",
        case_concurrency=1,
        internal_concurrency=1,
        budget=60,
    )

    result = ablation.extract_locked_full(case, args, graph)
    assert result["actual_scc_clause_ids"] == ["a", "b"]

    source.write_text(
        json.dumps([_result_row(["a", "b"]), _result_row(["a", "b"])]),
        encoding="utf-8",
    )
    with pytest.raises(cost.StableCaseIdentityError, match="exactly one"):
        ablation.extract_locked_full(case, args, graph)


def test_model_subset_keeps_canonical_source_order(tmp_path) -> None:
    case_csv = tmp_path / "cases.csv"
    fieldnames = [
        "model", "domain", "scc_id", "scc_size", "template", "root", "witness",
        "bridge", "affected_count", "llm_calls", "time", "result_file",
    ]
    with case_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            [
                {"model": "model-a", "domain": "fixture", "scc_id": "scc_0", "scc_size": 2,
                 "template": "direct_mutex", "result_file": "a.json"},
                {"model": "model-b", "domain": "fixture", "scc_id": "scc_1", "scc_size": 2,
                 "template": "direct_mutex", "result_file": "b.json"},
            ]
        )

    lea_plan = lea.build_or_load_case_plan(
        SimpleNamespace(case_csv=case_csv, models=["model-b"], limit=None, rebuild_plan=True),
        tmp_path / "lea",
    )
    cost_plan = cost.build_or_load_case_plan(
        SimpleNamespace(
            case_csv=case_csv,
            model="model-b",
            use_all_case_rows=True,
            template_preference="direct_mutex",
            rebuild_plan=True,
        ),
        tmp_path / "cost",
    )

    assert lea_plan[0]["case_order"] == 2
    assert lea_plan[0]["case_id"].startswith("002_")
    assert cost_plan[0]["case_order"] == 2
    assert cost_plan[0]["case_id"].startswith("002_")


def test_source_artifact_hash_is_pinned_and_mutation_fails_closed(tmp_path) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps([_result_row(["a", "b"])]), encoding="utf-8")
    case = {
        "case_id": "source-hash-case",
        "model": "gpt-4o",
        "domain": "fixture",
        "scc_id": "diagnostic-only",
        "scc_size": 2,
        "template": "direct_mutex",
        "source_result_file": str(source),
    }

    cost.hydrate_case_from_source(case)
    pinned_file_hash = case["source_result_sha256"]
    pinned_row_hash = case["source_sa_record_sha256"]
    assert pinned_file_hash.startswith("sha256:")
    assert pinned_row_hash.startswith("sha256:")

    mutated = _result_row(["a", "b"])
    mutated["llm_calls"] = 999
    source.write_text(json.dumps([mutated]), encoding="utf-8")
    with pytest.raises(cost.StableCaseIdentityError, match="Source result file changed"):
        cost.hydrate_case_from_source(case)

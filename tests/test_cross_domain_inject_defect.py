from __future__ import annotations

from experiments.cross_domain.inject_defect import (
    DEFAULT_MEMORY_CONFLICT_TEMPLATE,
    STRUCTURAL_MEMORY_PROFILE_VERSION,
    SUPPORTED_MEMORY_CONFLICT_TEMPLATES,
    get_injected_node,
    inject_defect,
)
from experiments.cross_domain.run_cross_domain_battle import (
    DOMAIN_MCGS_PROMPTS,
    DOMAIN_NAIVE_PROMPTS,
)
from src.models.clause import Clause, ClauseType
from src.models.graph import DependencyGraph, DependencyType, Edge, SCCInfo


def _make_cycle_graph(size: int = 9) -> tuple[DependencyGraph, SCCInfo]:
    clauses = {
        f"n{i}": Clause(
            id=f"n{i}",
            title=f"Node {i}",
            content=f"Original neutral content for node {i}.",
            clause_type=ClauseType.OTHER,
            metadata={},
        )
        for i in range(size)
    }
    edges = [
        Edge(
            source=f"n{i}",
            target=f"n{(i + 1) % size}",
            dependency_type=DependencyType.REFERENCES,
            weight=0.8,
        )
        for i in range(size)
    ]
    scc = SCCInfo(id="cycle", clause_ids=[f"n{i}" for i in range(size)], internal_edges=edges)
    return DependencyGraph(clauses=clauses, edges=edges), scc


def test_memory_stress_is_structural_simple_not_answer_label() -> None:
    graph, scc = _make_cycle_graph()
    original_node_count = len(graph.clauses)

    injected, target_id = inject_defect(
        graph, scc, "debian", seed=42, profile="memory_stress"
    )

    target = injected.clauses[target_id]
    witness_id = target.metadata["_inject_witness_node"]
    bridge_id = target.metadata["_inject_bridge_node"]
    witness = injected.clauses[witness_id]
    bridge = injected.clauses[bridge_id]

    assert len(injected.clauses) == original_node_count
    assert get_injected_node(injected, scc) == target_id
    assert target.metadata["_perturbed"] == "type_b_cross"
    assert target.metadata["_domain"] == "debian"
    assert target.metadata["_inject_seed"] == 42
    assert target.metadata["_inject_profile"] == "memory_stress"
    assert target.metadata["_inject_profile_version"] == STRUCTURAL_MEMORY_PROFILE_VERSION
    assert target.metadata["_inject_simple_role"] == "target"
    assert target.metadata["_inject_conflict_family"] == DEFAULT_MEMORY_CONFLICT_TEMPLATE
    assert target.metadata["_inject_conflict_difficulty"] == "moderate"
    assert witness.metadata["_inject_simple_role"] == "witness"
    assert bridge.metadata["_inject_simple_role"] == "bridge"

    assert target.metadata["_inject_witness_distance"] == len(scc.clause_ids) // 2
    assert witness_id != target_id
    assert witness_id in graph.clauses
    assert target.metadata["_inject_risk_nodes"] == [target_id, witness_id]
    assert target.metadata["_inject_evidence_nodes"] == [target_id, bridge_id, witness_id]
    assert target.metadata["_inject_conflict_template"] == "debian_handoff_invariant_abi_class"
    assert target.metadata["_inject_affected_nodes"]

    full_text = "\n".join(clause.content for clause in injected.clauses.values()).lower()
    leaked_phrases = [
        "[defect",
        "cve",
        "critical lock point",
        "primary cve propagation vector",
        "security incident",
        "vulnerable object",
        "dag violation",
        "non-acyclic",
        "circular ownership anomaly",
        "most likely anomalous",
        "no evidence in this node",
    ]
    assert not any(phrase in full_text for phrase in leaked_phrases)


def test_memory_stress_marks_only_root_as_perturbed() -> None:
    graph, scc = _make_cycle_graph()

    injected, target_id = inject_defect(
        graph, scc, "sec_ex21", seed=7, profile="memory_stress"
    )

    perturbed_nodes = [
        node_id
        for node_id, clause in injected.clauses.items()
        if clause.metadata.get("_perturbed")
    ]
    assert perturbed_nodes == [target_id]

    roles = {
        node_id: clause.metadata.get("_inject_simple_role")
        for node_id, clause in injected.clauses.items()
    }
    assert roles[target_id] == "target"
    assert "witness" in roles.values()
    assert "bridge" in roles.values()
    witness_id = injected.clauses[target_id].metadata["_inject_witness_node"]
    bridge_id = injected.clauses[target_id].metadata["_inject_bridge_node"]
    assert not injected.clauses[witness_id].metadata.get("_perturbed")
    assert not injected.clauses[bridge_id].metadata.get("_perturbed")
    assert injected.clauses[target_id].metadata.get("_original_content")
    assert injected.clauses[witness_id].metadata.get("_original_content")
    assert injected.clauses[bridge_id].metadata.get("_original_content")


def test_memory_stress_generates_domain_conflict_templates() -> None:
    expected = {
        "debian": ("legacy interface class", "pass-through", "new interface class", "debian_handoff_invariant_abi_class"),
        "wikipedia": ("current-status", "forwards that label", "historical", "wikipedia_handoff_invariant_lifecycle_label"),
        "sec_ex21": ("full-control", "same control basis", "20 percent", "sec_handoff_invariant_control_basis"),
    }
    for domain, (target_signal, bridge_signal, witness_signal, template) in expected.items():
        graph, scc = _make_cycle_graph()
        injected, target_id = inject_defect(
            graph, scc, domain, seed=42, profile="memory_stress"
        )
        target = injected.clauses[target_id]
        witness = injected.clauses[target.metadata["_inject_witness_node"]]
        bridge = injected.clauses[target.metadata["_inject_bridge_node"]]
        assert target_signal.lower() in target.content.lower()
        assert bridge_signal.lower() in bridge.content.lower()
        assert witness_signal.lower() in witness.content.lower()
        assert target.metadata["_inject_conflict_template"] == template


def test_memory_stress_supports_conflict_template_suite() -> None:
    expected_difficulty = {
        "direct_mutex": "obvious",
        "handoff_invariant": "moderate",
        "temporal_gate": "subtle",
        "condition_trigger": "hard",
    }
    for template in SUPPORTED_MEMORY_CONFLICT_TEMPLATES:
        graph, scc = _make_cycle_graph(size=12)
        injected, target_id = inject_defect(
            graph,
            scc,
            "wikipedia",
            seed=42,
            profile="memory_stress",
            conflict_template=template,
        )
        target = injected.clauses[target_id]
        evidence_nodes = target.metadata["_inject_evidence_nodes"]
        assert target.metadata["_inject_conflict_family"] == template
        assert target.metadata["_inject_conflict_difficulty"] == expected_difficulty[template]
        assert target.metadata["_inject_risk_nodes"] == [
            target_id,
            target.metadata["_inject_witness_node"],
        ]
        if template == "direct_mutex":
            assert target.metadata["_inject_bridge_node"] is None
            assert len(evidence_nodes) == 2
        else:
            assert target.metadata["_inject_bridge_node"] in evidence_nodes
            assert len(evidence_nodes) == 3


def test_generic_prompts_do_not_directly_name_domain_error_types() -> None:
    graph, scc = _make_cycle_graph(size=4)
    banned = [
        "cve",
        "version-lock",
        "security-only",
        "taxonomy",
        "directed acyclic graph",
        "subcategory",
        "circular ownership",
        "tax haven",
        "shell company",
    ]

    for domain, prompt_fn in DOMAIN_NAIVE_PROMPTS.items():
        prompt = prompt_fn(graph.clauses, graph.edges, scc.clause_ids, ranked=True).lower()
        assert "directed graph of interdependent records" in prompt
        assert "global_ranking" in prompt
        assert all(term not in prompt for term in banned), domain

    class DummyMCGS:
        _clauses = graph.clauses
        _internal_edges = graph.edges
        _scc_ids = scc.clause_ids

    for domain, prompt_fn in DOMAIN_MCGS_PROMPTS.items():
        prompt = prompt_fn(DummyMCGS(), scc.clause_ids[:3]).lower()
        assert "directed graph of interdependent records" in prompt
        assert "clause_evaluations" in prompt
        assert all(term not in prompt for term in banned), domain

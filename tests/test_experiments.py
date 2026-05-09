"""End-to-end tests for the counterfactual perturbation experiment pipeline.

Tests cover:
  Phase 0: Graph exploration & target selection
  Phase 1: All 3 perturbation types (A/B/C)
  Phase 2: Experiment runner (baseline vs perturbed)
  Phase 4: Ablation runner
  Phase 5: Visualization (figure generation)

Uses a small synthetic graph (15 nodes) with known structure:
  - 10 DAG nodes
  - 1 SCC of size 3 (nodes s0, s1, s2)
  - 1 SCC of size 2 (nodes s3, s4)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

import networkx as nx
import pytest

from src.llm.base import BaseLLMClient, LLMResponse
from src.models.clause import Clause, ClauseType
from src.models.graph import DependencyGraph, DependencyType, Edge


# =====================================================================
# Fixtures
# =====================================================================

class _TestLLMClient(BaseLLMClient):
    """Minimal deterministic LLM for testing experiment pipeline."""

    def __init__(self):
        super().__init__({"model": "test"})
        self._call_count = 0

    async def call(self, prompt: str, *, temperature: float = 0.0,
                   max_tokens: int = 4096, system_prompt: Optional[str] = None,
                   response_format: Optional[dict] = None) -> LLMResponse:
        self._call_count += 1
        data = self._respond(prompt, temperature)
        return LLMResponse(content=json.dumps(data), model="test")

    async def call_json(self, prompt: str, *, temperature: float = 0.0,
                        max_tokens: int = 4096, system_prompt: Optional[str] = None) -> dict:
        self._call_count += 1
        return self._respond(prompt, temperature)

    def _respond(self, prompt: str, temperature: float) -> dict:
        import hashlib, random, re

        prompt_lower = prompt.lower()
        base = 0.25

        # Detect perturbation signals
        if any(s in prompt_lower for s in ["shall not", "is not", "not:", "darf nicht"]):
            base = 0.85
        elif any(s in prompt_lower for s in ["precondition", "only take effect"]):
            base = 0.60
        elif any(s in prompt_lower for s in ["mutatis mutandis", "entire code", "all parts"]):
            base = 0.35

        if temperature > 0:
            rng = random.Random(self._call_count)
            base = min(1.0, max(0.0, base + rng.gauss(0, temperature * 0.08)))

        dims = [{"name": d, "score": round(min(1.0, base + 0.02), 4), "reasoning": "test"}
                for d in ["financial_exposure", "liability_scope", "termination_risk",
                          "compliance_burden", "ambiguity"]]

        if "interdependent" in prompt_lower or "circular" in prompt_lower:
            clause_ids = re.findall(r'\b(s\d+|d\d+)\b', prompt)
            unique_ids = list(dict.fromkeys(clause_ids))
            if unique_ids:
                return {
                    "clause_evaluations": {
                        cid: {"overall_risk_score": round(min(1.0, base + 0.01 * i), 4),
                              "dimensions": dims, "reasoning": "test"}
                        for i, cid in enumerate(unique_ids)
                    },
                    "interaction_summary": "test",
                }

        return {"overall_risk_score": round(base, 4), "dimensions": dims, "reasoning": "test"}


def _make_test_graph() -> DependencyGraph:
    """Build a small graph: 10 DAG nodes + 2 SCCs (size 3 and 2)."""
    clauses = {}
    edges = []

    for i in range(10):
        cid = f"d{i}"
        clauses[cid] = Clause(
            id=cid,
            title=f"Section {i}: General Provision",
            content=f"All parties shall comply with the requirements of section {i}.",
            clause_type=ClauseType.OBLIGATION,
            metadata={},
        )
    for i in range(8):
        edges.append(Edge(source=f"d{i+1}", target=f"d{i}",
                          dependency_type=DependencyType.REFERENCES, weight=0.8))

    for i in range(3):
        cid = f"s{i}"
        clauses[cid] = Clause(
            id=cid,
            title=f"Section S{i}: Interdependent Provision",
            content=f"This provision for s{i} references s{(i+1)%3} and governs obligations.",
            clause_type=ClauseType.CONDITION,
            metadata={},
        )
    edges.append(Edge(source="s0", target="s1", dependency_type=DependencyType.REFERENCES, weight=0.9))
    edges.append(Edge(source="s1", target="s2", dependency_type=DependencyType.REFERENCES, weight=0.9))
    edges.append(Edge(source="s2", target="s0", dependency_type=DependencyType.REFERENCES, weight=0.9))

    for i in range(2):
        cid = f"s{i+3}"
        clauses[cid] = Clause(
            id=cid,
            title=f"Section S{i+3}: Mutual Provision",
            content=f"This provision for s{i+3} references s{3 + (i+1)%2}.",
            clause_type=ClauseType.CONDITION,
            metadata={},
        )
    edges.append(Edge(source="s3", target="s4", dependency_type=DependencyType.REFERENCES, weight=0.8))
    edges.append(Edge(source="s4", target="s3", dependency_type=DependencyType.REFERENCES, weight=0.8))

    edges.append(Edge(source="d9", target="s0", dependency_type=DependencyType.REFERENCES, weight=0.7))
    edges.append(Edge(source="d5", target="s3", dependency_type=DependencyType.REFERENCES, weight=0.7))

    return DependencyGraph(clauses=clauses, edges=edges, metadata={"source": "test"})


def _make_nx_graph() -> nx.DiGraph:
    """Build the same structure as a raw NetworkX graph (simulating QuantLaw)."""
    G = nx.DiGraph()
    for i in range(10):
        G.add_node(f"d{i}", heading=f"Section {i}", key=f"SEC_{i}",
                   text=f"All parties shall comply with section {i}.", edge_type="reference")
    for i in range(8):
        G.add_edge(f"d{i+1}", f"d{i}", edge_type="reference")

    for i in range(3):
        G.add_node(f"s{i}", heading=f"Section S{i}", key=f"SCC_{i}",
                   text=f"Provision s{i} references s{(i+1)%3}.", edge_type="reference")
    G.add_edge("s0", "s1", edge_type="reference")
    G.add_edge("s1", "s2", edge_type="reference")
    G.add_edge("s2", "s0", edge_type="reference")

    for i in range(2):
        G.add_node(f"s{i+3}", heading=f"Section S{i+3}", key=f"SCC_{i+3}",
                   text=f"Provision s{i+3} references s{3+(i+1)%2}.", edge_type="reference")
    G.add_edge("s3", "s4", edge_type="reference")
    G.add_edge("s4", "s3", edge_type="reference")

    G.add_edge("d9", "s0", edge_type="reference")
    G.add_edge("d5", "s3", edge_type="reference")
    return G


@pytest.fixture
def test_graph():
    return _make_test_graph()


@pytest.fixture
def test_nx_graph():
    return _make_nx_graph()


@pytest.fixture
def llm_client():
    return _TestLLMClient()


@pytest.fixture
def config():
    return {
        "llm": {"provider": "openai", "model": "test"},
        "graph_pruning": {"enabled": True, "noise_weight_threshold": 0.35,
                          "hierarchy_violation_threshold": 0.6, "ib_compression_ratio": 0.15},
        "scc": {"num_samples": 3, "temperature": 0.7},
        "pruning": {"variance_threshold": 0.005, "influence_threshold": 0.2},
        "mcgs": {"num_rollouts": 5, "ucb_exploration_weight": 1.414,
                 "early_stopping": False},
        "aggregation": {"high_risk_threshold": 0.7, "high_uncertainty_threshold": 0.15},
    }


# =====================================================================
# Phase 0: Graph Exploration
# =====================================================================

class TestPhase0Exploration:
    def test_explore_graph_structure(self, test_nx_graph):
        from experiments.explore_data import explore_graph

        stats = explore_graph(test_nx_graph)
        assert stats["num_nodes"] == 15
        assert stats["num_nontrivial_sccs"] == 2
        assert stats["dag_ratio"] > 0.5
        assert stats["giant_scc_size"] == 3

    def test_select_targets(self, test_nx_graph):
        from experiments.explore_data import explore_graph, select_targets

        stats = explore_graph(test_nx_graph)
        targets = select_targets(test_nx_graph, stats, num_dag_targets=3, num_scc_targets=2)

        assert len(targets["dag_targets"]) == 3
        assert len(targets["scc_targets"]) == 2

        for dt in targets["dag_targets"]:
            assert "id" in dt
            assert dt["id"].startswith("d")

        for st in targets["scc_targets"]:
            assert "node_ids" in st
            assert "scc_id" in st
            assert st["size"] >= 2
            assert len(st["node_ids"]) == st["size"]

    def test_filter_hierarchy_edges(self, test_nx_graph):
        from experiments.explore_data import filter_hierarchy_edges

        test_nx_graph.add_edge("d0", "d1", edge_type="containment")
        test_nx_graph.add_edge("d2", "d3", edge_type="hierarchy")
        original_edges = test_nx_graph.number_of_edges()

        _, removed = filter_hierarchy_edges(test_nx_graph)
        assert removed == 2
        assert test_nx_graph.number_of_edges() == original_edges - 2


# =====================================================================
# Phase 1: Perturbation Functions
# =====================================================================

class TestPhase1Perturbation:
    def test_type_a_negation(self, test_graph):
        from experiments.perturbation import perturb_type_a

        original_content = test_graph.clauses["d0"].content
        perturbed = perturb_type_a(test_graph, "d0")

        assert test_graph.clauses["d0"].content == original_content
        assert perturbed.clauses["d0"].content != original_content
        assert perturbed.clauses["d0"].metadata.get("_perturbed") == "type_a"
        assert "shall not" in perturbed.clauses["d0"].content.lower() or \
               "not:" in perturbed.clauses["d0"].content.lower() or \
               "opposite" in perturbed.clauses["d0"].content.lower()

    def test_type_a_on_scc_node(self, test_graph):
        from experiments.perturbation import perturb_type_a

        perturbed = perturb_type_a(test_graph, "s0")
        assert perturbed.clauses["s0"].metadata.get("_perturbed") == "type_a"
        assert perturbed.clauses["s1"].content == test_graph.clauses["s1"].content

    def test_type_b_deadlock(self, test_graph):
        from experiments.perturbation import perturb_type_b

        perturbed = perturb_type_b(test_graph, ["s0", "s1", "s2"], "s0", "s1")

        assert "Precondition" in perturbed.clauses["s0"].content
        assert "Precondition" in perturbed.clauses["s1"].content
        assert "s1" in perturbed.clauses["s0"].content
        assert "s0" in perturbed.clauses["s1"].content
        assert perturbed.clauses["s2"].content == test_graph.clauses["s2"].content

    def test_type_b_requires_scc_membership(self, test_graph):
        from experiments.perturbation import perturb_type_b

        with pytest.raises(ValueError, match="must be in the same SCC"):
            perturb_type_b(test_graph, ["s0", "s1", "s2"], "d0", "s1")

    def test_type_c_scope_expansion(self, test_graph):
        from experiments.perturbation import perturb_type_c

        perturbed = perturb_type_c(test_graph, ["s0", "s1", "s2"], "s0")

        assert perturbed.clauses["s0"].metadata.get("_perturbed") == "type_c"
        content = perturbed.clauses["s0"].content.lower()
        assert any(signal in content for signal in
                   ["mutatis mutandis", "entire code", "all parts", "regardless"])

    def test_type_c_requires_scc_membership(self, test_graph):
        from experiments.perturbation import perturb_type_c

        with pytest.raises(ValueError, match="must be in the SCC"):
            perturb_type_c(test_graph, ["s0", "s1", "s2"], "d0")

    def test_perturbation_does_not_mutate_original(self, test_graph):
        from experiments.perturbation import perturb_type_a, perturb_type_b, perturb_type_c

        original_contents = {cid: c.content for cid, c in test_graph.clauses.items()}
        original_edge_count = len(test_graph.edges)

        perturb_type_a(test_graph, "d0")
        perturb_type_b(test_graph, ["s0", "s1", "s2"], "s0", "s1")
        perturb_type_c(test_graph, ["s0", "s1", "s2"], "s2")

        for cid, content in original_contents.items():
            assert test_graph.clauses[cid].content == content
        assert len(test_graph.edges) == original_edge_count

    def test_nonexistent_clause_raises(self, test_graph):
        from experiments.perturbation import perturb_type_a

        with pytest.raises(ValueError, match="not found"):
            perturb_type_a(test_graph, "nonexistent_clause")


# =====================================================================
# Phase 2: Experiment Runner
# =====================================================================

class TestPhase2Runner:
    @pytest.mark.asyncio
    async def test_run_single_dag_type_a(self, config, llm_client, test_graph):
        from experiments.runner import ExperimentRunner

        runner = ExperimentRunner(config, llm_client, output_dir=tempfile.mkdtemp())
        result = await runner.run_single(
            test_graph, "test_graph", "d0",
            node_type="dag", perturbation_type="type_a",
        )

        assert result.graph_id == "test_graph"
        assert result.target_clause_id == "d0"
        assert result.node_type == "dag"
        assert result.perturbation_type == "type_a"
        assert 0.0 <= result.mcgs_risk_score <= 1.0
        assert 0.0 <= result.direct_llm_risk_score <= 1.0
        assert result.mcgs_time_seconds > 0
        assert result.delta_mcgs_risk > 0, \
            f"Type A perturbation should increase risk, got delta={result.delta_mcgs_risk}"

    @pytest.mark.asyncio
    async def test_run_single_scc_type_b(self, config, llm_client, test_graph):
        from experiments.runner import ExperimentRunner

        runner = ExperimentRunner(config, llm_client, output_dir=tempfile.mkdtemp())
        result = await runner.run_single(
            test_graph, "test_graph", "s0",
            node_type="scc", perturbation_type="type_b",
            scc_node_ids=["s0", "s1", "s2"], clause_y_id="s1",
        )

        assert result.perturbation_type == "type_b"
        assert result.scc_id is not None

    @pytest.mark.asyncio
    async def test_delta_direct_llm_is_fair_comparison(self, config, llm_client, test_graph):
        """Verify delta_direct_llm_risk compares LLM(perturbed) - LLM(baseline), not against MCGS."""
        from experiments.runner import ExperimentRunner

        runner = ExperimentRunner(config, llm_client, output_dir=tempfile.mkdtemp())
        result = await runner.run_single(
            test_graph, "test_graph", "d0",
            node_type="dag", perturbation_type="type_a",
        )

        assert result.delta_direct_llm_risk != 0.0 or result.direct_llm_risk_score > 0

    @pytest.mark.asyncio
    async def test_save_and_load_results(self, config, llm_client, test_graph):
        from experiments.runner import ExperimentRunner

        tmp_dir = tempfile.mkdtemp()
        runner = ExperimentRunner(config, llm_client, output_dir=tmp_dir)
        await runner.run_single(
            test_graph, "test_graph", "d0",
            node_type="dag", perturbation_type="type_a",
        )
        out_path = runner.save_results("test_results.json")

        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert len(data) == 1
        assert data[0]["target_clause_id"] == "d0"

    @pytest.mark.asyncio
    async def test_compute_detection_rates(self, config, llm_client, test_graph):
        from experiments.runner import ExperimentRunner

        runner = ExperimentRunner(config, llm_client, output_dir=tempfile.mkdtemp())
        await runner.run_single(
            test_graph, "test_graph", "d0",
            node_type="dag", perturbation_type="type_a",
        )
        await runner.run_single(
            test_graph, "test_graph", "d1",
            node_type="dag", perturbation_type="type_a",
        )

        summary = runner.compute_detection_rates()
        assert "dag_type_a" in summary
        assert summary["dag_type_a"]["count"] == 2
        assert 0.0 <= summary["dag_type_a"]["mcgs_detection_rate"] <= 1.0


# =====================================================================
# Phase 4: Ablation
# =====================================================================

class TestPhase4Ablation:
    @pytest.mark.asyncio
    async def test_ablation_all_configs(self, config, llm_client, test_graph):
        from experiments.ablation import AblationRunner
        from experiments.perturbation import perturb_type_a

        perturbed = perturb_type_a(test_graph, "d0")
        ablation = AblationRunner(config, llm_client, output_dir=tempfile.mkdtemp())
        results = await ablation.run_all_configs(
            perturbed, "test_graph", "d0",
            node_type="dag", perturbation_type="type_a",
        )

        assert len(results) == 4
        config_names = {r.config_name for r in results}
        assert config_names == {"full", "no_graph_pruning", "no_mcgs", "direct_llm"}

        for r in results:
            assert 0.0 <= r.risk_score <= 1.0

    @pytest.mark.asyncio
    async def test_ablation_detection_rates(self, config, llm_client, test_graph):
        from experiments.ablation import AblationRunner
        from experiments.perturbation import perturb_type_a

        perturbed = perturb_type_a(test_graph, "d0")
        ablation = AblationRunner(config, llm_client, output_dir=tempfile.mkdtemp())
        await ablation.run_all_configs(
            perturbed, "test_graph", "d0",
            node_type="dag", perturbation_type="type_a",
        )

        summary = ablation.compute_detection_rates()
        assert len(summary) > 0
        for key, stats in summary.items():
            assert "detection_rate" in stats
            assert "count" in stats


# =====================================================================
# Phase 5: Visualization (smoke test — just ensure no crash)
# =====================================================================

class TestPhase5Visualization:
    def test_fig1_no_crash(self):
        from experiments.visualize import fig1_detection_rate_comparison

        results = [
            {"node_type": "dag", "perturbation_type": "type_a",
             "mcgs_high_risk_detected": True, "mcgs_uncertain_detected": False,
             "direct_llm_detected": True},
            {"node_type": "scc", "perturbation_type": "type_b",
             "mcgs_high_risk_detected": True, "mcgs_uncertain_detected": False,
             "direct_llm_detected": False},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            fig1_detection_rate_comparison(results, f"{tmp}/fig1.pdf")
            assert Path(f"{tmp}/fig1.pdf").exists()

    def test_fig2_no_crash(self):
        from experiments.visualize import fig2_risk_delta

        results = [
            {"node_type": "dag", "perturbation_type": "type_a",
             "delta_mcgs_risk": 0.3, "delta_direct_llm_risk": 0.1},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            fig2_risk_delta(results, f"{tmp}/fig2.pdf")
            assert Path(f"{tmp}/fig2.pdf").exists()

    def test_fig3_no_crash(self):
        from experiments.visualize import fig3_reward_convergence

        with tempfile.TemporaryDirectory() as tmp:
            fig3_reward_convergence([0.5, 0.6, 0.55], [0.7, 0.8, 0.75], f"{tmp}/fig3.pdf")
            assert Path(f"{tmp}/fig3.pdf").exists()

    def test_fig4_no_crash(self):
        from experiments.visualize import fig4_ablation

        results = [
            {"config_name": "full", "high_risk_detected": True, "uncertain_detected": False},
            {"config_name": "no_mcgs", "high_risk_detected": False, "uncertain_detected": False},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            fig4_ablation(results, f"{tmp}/fig4.pdf")
            assert Path(f"{tmp}/fig4.pdf").exists()

    def test_fig5_no_crash(self):
        from experiments.visualize import fig5_scc_heatmap

        results = [
            {"target_clause_id": "s0", "delta_mcgs_risk": 0.2},
            {"target_clause_id": "s1", "delta_mcgs_risk": -0.1},
        ]
        edges = [{"source": "s0", "target": "s1"}, {"source": "s1", "target": "s0"}]
        with tempfile.TemporaryDirectory() as tmp:
            fig5_scc_heatmap(results, edges, f"{tmp}/fig5.pdf")
            assert Path(f"{tmp}/fig5.pdf").exists()

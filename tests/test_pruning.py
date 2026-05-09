"""Tests for Module 6: Three-layer pruning."""
from __future__ import annotations

import pytest

from src.models.clause import ClauseEvaluation, RiskDimension
from src.models.graph import DependencyGraph, DependencyType, Edge, SCCInfo, Clause
from src.models.search_tree import SCCBranch, SearchTree, SearchTreeNode
from src.modules.pruning import DominancePruner, InfluencePruner, VariancePruner


def _dim(name: str, score: float) -> RiskDimension:
    return RiskDimension(name=name, score=score)


def _eval(cid: str, overall: float, dims: dict[str, float]) -> ClauseEvaluation:
    return ClauseEvaluation(
        clause_id=cid,
        overall_risk_score=overall,
        dimensions=[_dim(n, s) for n, s in dims.items()],
    )


# ── Variance pruning ─────────────────────────────────────────────────

class TestVariancePruner:
    def test_collapse_low_variance(self):
        scc = SCCInfo(id="scc_0", clause_ids=["a", "b"], size=2)
        scc.variance = 0.005
        scc.samples = [
            {
                "sample_id": 0,
                "evaluations": {
                    "a": _eval("a", 0.6, {"financial_exposure": 0.5}),
                    "b": _eval("b", 0.4, {"financial_exposure": 0.3}),
                },
            },
            {
                "sample_id": 1,
                "evaluations": {
                    "a": _eval("a", 0.61, {"financial_exposure": 0.51}),
                    "b": _eval("b", 0.41, {"financial_exposure": 0.31}),
                },
            },
        ]

        graph = DependencyGraph(
            clauses={"a": Clause(id="a", title="A", content="a"), "b": Clause(id="b", title="B", content="b")},
            sccs=[scc],
        )
        pruner = VariancePruner({"pruning": {"variance_threshold": 0.01}})
        stats = pruner.prune(graph)

        assert stats["collapsed"] == 1
        assert scc.is_collapsed
        assert scc.collapsed_value is not None
        assert abs(scc.collapsed_value["a"].overall_risk_score - 0.605) < 0.01

    def test_keep_high_variance(self):
        scc = SCCInfo(id="scc_0", clause_ids=["a"], size=1)
        scc.variance = 0.1
        scc.samples = []

        graph = DependencyGraph(
            clauses={"a": Clause(id="a", title="A", content="a")},
            sccs=[scc],
        )
        pruner = VariancePruner({"pruning": {"variance_threshold": 0.01}})
        stats = pruner.prune(graph)

        assert stats["remaining"] == 1
        assert not scc.is_collapsed


# ── Dominance pruning ────────────────────────────────────────────────

class TestDominancePruner:
    def _make_branch(self, bid: str, scc_id: str, evals: dict[str, ClauseEvaluation]) -> SCCBranch:
        return SCCBranch(branch_id=bid, scc_id=scc_id, evaluation=evals)

    def test_dominated_branch_pruned(self):
        dims = {"financial_exposure": 0.0, "liability_scope": 0.0}

        branch_a = self._make_branch("b1", "scc_0", {
            "c1": _eval("c1", 0.8, {"financial_exposure": 0.9, "liability_scope": 0.7}),
        })
        branch_b = self._make_branch("b2", "scc_0", {
            "c1": _eval("c1", 0.5, {"financial_exposure": 0.4, "liability_scope": 0.3}),
        })

        node = SearchTreeNode(scc_id="scc_0", branches=[branch_a, branch_b])
        tree = SearchTree(nodes={"scc_0": node})

        pruner = DominancePruner({"pruning": {"risk_dimensions": ["financial_exposure", "liability_scope"]}})
        stats = pruner.prune(tree)

        assert stats["pruned_branches"] == 1
        assert branch_b.is_pruned
        assert branch_b.pruned_by == "dominance"
        assert not branch_a.is_pruned

    def test_no_dominance(self):
        branch_a = self._make_branch("b1", "scc_0", {
            "c1": _eval("c1", 0.8, {"financial_exposure": 0.9, "liability_scope": 0.2}),
        })
        branch_b = self._make_branch("b2", "scc_0", {
            "c1": _eval("c1", 0.5, {"financial_exposure": 0.3, "liability_scope": 0.8}),
        })

        node = SearchTreeNode(scc_id="scc_0", branches=[branch_a, branch_b])
        tree = SearchTree(nodes={"scc_0": node})

        pruner = DominancePruner({"pruning": {"risk_dimensions": ["financial_exposure", "liability_scope"]}})
        stats = pruner.prune(tree)

        assert stats["pruned_branches"] == 0


# ── Influence pruning ────────────────────────────────────────────────

class TestInfluencePruner:
    def test_low_influence_keeps_one_branch(self):
        branches = [
            SCCBranch(
                branch_id=f"scc_0_b{i}",
                scc_id="scc_0",
                evaluation={"c5": _eval("c5", score, {"financial_exposure": score})},
            )
            for i, score in enumerate([0.3, 0.5, 0.7])
        ]
        node = SearchTreeNode(scc_id="scc_0", branches=branches)
        tree = SearchTree(
            nodes={"scc_0": node},
            scc_topological_order=["scc_0"],
        )

        clauses = {f"c{i}": Clause(id=f"c{i}", title=f"C{i}", content=f"c{i}") for i in range(1, 7)}
        graph = DependencyGraph(
            clauses=clauses,
            edges=[
                Edge(source="c5", target="c6", dependency_type=DependencyType.REFERENCES),
                Edge(source="c6", target="c5", dependency_type=DependencyType.REFERENCES),
            ],
            sccs=[SCCInfo(id="scc_0", clause_ids=["c5", "c6"], size=2)],
            dag_nodes=["c1", "c2", "c3", "c4"],
        )

        pruner = InfluencePruner({"pruning": {"influence_threshold": 0.99}})
        stats = pruner.prune(tree, graph)

        active = node.active_branches
        assert len(active) == 1
        assert stats["pruned_branches"] == 2

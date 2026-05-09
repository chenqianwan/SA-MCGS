"""Tests for Module 7: MCGS search."""
from __future__ import annotations

from src.models.clause import ClauseEvaluation, RiskDimension
from src.models.graph import DependencyGraph, DependencyType, Edge, SCCInfo, Clause
from src.models.search_tree import SCCBranch, SearchTree, SearchTreeNode
from src.modules.mcgs import MCGS


def _eval(cid: str, score: float) -> ClauseEvaluation:
    return ClauseEvaluation(
        clause_id=cid,
        overall_risk_score=score,
        dimensions=[RiskDimension(name="financial_exposure", score=score)],
    )


def _make_tree_with_two_sccs() -> tuple[SearchTree, dict[str, ClauseEvaluation], DependencyGraph]:
    """Two SCCs in sequence, each with 2 branches."""
    branches_0 = [
        SCCBranch(branch_id="scc_0_b0", scc_id="scc_0", evaluation={"c1": _eval("c1", 0.3)}),
        SCCBranch(branch_id="scc_0_b1", scc_id="scc_0", evaluation={"c1": _eval("c1", 0.8)}),
    ]
    branches_1 = [
        SCCBranch(branch_id="scc_1_b0", scc_id="scc_1", evaluation={"c3": _eval("c3", 0.4)}),
        SCCBranch(branch_id="scc_1_b1", scc_id="scc_1", evaluation={"c3": _eval("c3", 0.9)}),
    ]

    tree = SearchTree(
        nodes={
            "scc_0": SearchTreeNode(scc_id="scc_0", branches=branches_0, depth=0),
            "scc_1": SearchTreeNode(scc_id="scc_1", branches=branches_1, depth=1),
        },
        scc_topological_order=["scc_0", "scc_1"],
    )

    dag_results = {"c2": _eval("c2", 0.5)}

    clauses = {f"c{i}": Clause(id=f"c{i}", title=f"C{i}", content=f"c{i}") for i in range(1, 4)}
    graph = DependencyGraph(clauses=clauses, edges=[])

    return tree, dag_results, graph


class TestMCGS:
    def test_basic_search(self):
        tree, dag_results, graph = _make_tree_with_two_sccs()
        mcgs = MCGS({"mcgs": {"num_rollouts": 20, "ucb_exploration_weight": 1.414}})
        results = mcgs.search(tree, dag_results, graph)

        assert len(results) == 20
        for r in results:
            assert "rollout_idx" in r
            assert "path" in r
            assert "evaluations" in r
            assert "reward" in r
            assert r["reward"] >= 0

    def test_all_branches_visited(self):
        tree, dag_results, graph = _make_tree_with_two_sccs()
        mcgs = MCGS({"mcgs": {"num_rollouts": 50, "ucb_exploration_weight": 1.414}})
        mcgs.search(tree, dag_results, graph)

        for node in tree.nodes.values():
            for branch in node.branches:
                assert branch.visit_count > 0, f"{branch.branch_id} was never visited"

    def test_early_stopping(self):
        tree, dag_results, graph = _make_tree_with_two_sccs()
        mcgs = MCGS({
            "mcgs": {
                "num_rollouts": 1000,
                "ucb_exploration_weight": 0.1,
                "early_stopping": True,
                "convergence_window": 5,
                "convergence_threshold": 0.5,
            }
        })
        results = mcgs.search(tree, dag_results, graph)
        assert len(results) < 1000, "Should stop early with tight convergence"

    def test_reward_computation(self):
        evals = {
            "c1": _eval("c1", 0.2),
            "c2": _eval("c2", 0.8),
        }
        reward = MCGS._compute_reward(evals)
        assert 0 < reward <= 1.0

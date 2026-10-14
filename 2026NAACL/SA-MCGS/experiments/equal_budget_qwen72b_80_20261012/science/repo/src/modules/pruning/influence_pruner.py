"""Module 6c: 影响力剪枝

影响力 = SCC 在 condensation DAG 上的下游可达节点数量。
对低影响力 SCC（下游节点数 / 总条款数 < 阈值），
只保留中位数分支，剪掉其余分支。

理论依据：低影响力 SCC 对整体风险评估的敏感度低，
精确搜索的边际收益有限。
"""
from __future__ import annotations

from collections import deque
from typing import Any

import networkx as nx
from loguru import logger

from ...models.graph import DependencyGraph
from ...models.search_tree import SCCBranch, SearchTree


class InfluencePruner:
    def __init__(self, config: dict):
        pruning_cfg = config.get("pruning", {})
        self.influence_threshold = pruning_cfg.get("influence_threshold", 0.2)

    def prune(self, search_tree: SearchTree, graph: DependencyGraph) -> dict[str, Any]:
        stats = {"pruned_branches": 0, "low_influence_sccs": 0}

        influence_scores = self._compute_influence(graph)
        total_clauses = len(graph.clauses)

        for scc_id, node in search_tree.nodes.items():
            influence = influence_scores.get(scc_id, 0)
            normalized = influence / total_clauses if total_clauses > 0 else 0.0

            if normalized >= self.influence_threshold:
                continue

            active = node.active_branches
            if len(active) <= 1:
                continue

            stats["low_influence_sccs"] += 1

            sorted_branches = sorted(active, key=lambda b: _avg_risk(b))
            median_idx = len(sorted_branches) // 2

            for i, branch in enumerate(sorted_branches):
                if i != median_idx:
                    branch.is_pruned = True
                    branch.pruned_by = "influence"
                    stats["pruned_branches"] += 1

        logger.info(
            f"Influence pruning: {stats['low_influence_sccs']} low-influence SCCs, "
            f"pruned {stats['pruned_branches']} branches"
        )
        return stats

    def _compute_influence(self, graph: DependencyGraph) -> dict[str, int]:
        """计算每个 SCC 在 condensation DAG 上的下游可达节点数"""
        cond_graph, scc_to_cond = self._build_condensation(graph)
        influence: dict[str, int] = {}

        for scc in graph.sccs:
            if scc.is_collapsed or scc.id not in scc_to_cond:
                continue
            cond_node = scc_to_cond[scc.id]
            reachable = self._bfs_reachable_count(cond_graph, cond_node, graph, scc_to_cond)
            influence[scc.id] = reachable

        return influence

    @staticmethod
    def _build_condensation(
        graph: DependencyGraph,
    ) -> tuple[nx.DiGraph, dict[str, int]]:
        G = nx.DiGraph()
        for cid in graph.clauses:
            G.add_node(cid)
        for edge in graph.edges:
            G.add_edge(edge.source, edge.target)

        condensation = nx.condensation(G)

        clause_to_cond: dict[str, int] = {}
        for cnode in condensation.nodes:
            for member in condensation.nodes[cnode]["members"]:
                clause_to_cond[member] = cnode

        scc_to_cond: dict[str, int] = {}
        for scc in graph.sccs:
            representative = scc.clause_ids[0]
            if representative in clause_to_cond:
                scc_to_cond[scc.id] = clause_to_cond[representative]

        return condensation, scc_to_cond

    @staticmethod
    def _bfs_reachable_count(
        cond_graph: nx.DiGraph,
        start_node: int,
        graph: DependencyGraph,
        scc_to_cond: dict[str, int],
    ) -> int:
        """BFS 计算下游可达节点数（不含自身）"""
        visited: set[int] = set()
        queue: deque[int] = deque()

        for neighbor in cond_graph.successors(start_node):
            if neighbor not in visited:
                queue.append(neighbor)
                visited.add(neighbor)

        total = 0
        while queue:
            current = queue.popleft()
            member_count = len(cond_graph.nodes[current]["members"])
            total += member_count
            for neighbor in cond_graph.successors(current):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return total


def _avg_risk(branch: SCCBranch) -> float:
    scores = [e.overall_risk_score for e in branch.evaluation.values()]
    return sum(scores) / len(scores) if scores else 0.0

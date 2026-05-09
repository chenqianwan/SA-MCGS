"""Graph Quality Metrics — SCC count, density, coherence.

用于评估依赖图构建和剪枝的质量。
"""
from __future__ import annotations

from typing import Any

import networkx as nx
from loguru import logger

from ..models.graph import DependencyGraph


class GraphQualityMetrics:
    """计算依赖图的结构质量指标。"""

    def compute(self, graph: DependencyGraph) -> dict[str, Any]:
        G = nx.DiGraph()
        for cid in graph.clauses:
            G.add_node(cid)
        for e in graph.edges:
            G.add_edge(e.source, e.target, weight=e.weight)

        n = G.number_of_nodes()
        m = G.number_of_edges()

        density = nx.density(G)
        sccs = list(nx.strongly_connected_components(G))
        nontrivial_sccs = [s for s in sccs if len(s) > 1 or G.has_edge(next(iter(s)), next(iter(s)))]

        dag_nodes = n - sum(len(s) for s in nontrivial_sccs)
        dag_ratio = dag_nodes / n if n > 0 else 0

        # Dependency depth: longest path in condensation DAG
        cond = nx.condensation(G)
        dep_depth = nx.dag_longest_path_length(cond) if cond.number_of_nodes() > 0 else 0

        # Coherence: average clustering coefficient (undirected projection)
        G_undir = G.to_undirected()
        coherence = nx.average_clustering(G_undir) if n > 0 else 0

        # Orphan / leaf ratios
        orphans = sum(1 for node in G if G.in_degree(node) == 0 and G.out_degree(node) == 0)
        leaves = sum(1 for node in G if G.out_degree(node) == 0 and G.in_degree(node) > 0)

        metrics = {
            "num_nodes": n,
            "num_edges": m,
            "density": round(density, 6),
            "num_sccs": len(nontrivial_sccs),
            "scc_sizes": sorted([len(s) for s in nontrivial_sccs], reverse=True),
            "dag_ratio": round(dag_ratio, 4),
            "dependency_depth": dep_depth,
            "coherence": round(coherence, 4),
            "orphan_count": orphans,
            "leaf_count": leaves,
            "orphan_ratio": round(orphans / n, 4) if n > 0 else 0,
            "leaf_ratio": round(leaves / n, 4) if n > 0 else 0,
        }

        logger.info(
            f"Graph metrics: nodes={n}, edges={m}, density={density:.4f}, "
            f"SCCs={len(nontrivial_sccs)}, DAG ratio={dag_ratio:.1%}, depth={dep_depth}"
        )
        return metrics

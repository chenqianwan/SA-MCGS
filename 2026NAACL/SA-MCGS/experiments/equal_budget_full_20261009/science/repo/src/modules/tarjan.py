"""Module 3: Tarjan SCC 检测

输入: DependencyGraph
输出: DependencyGraph (sccs / dag_nodes / topological_order 被填充)
"""
from __future__ import annotations

import networkx as nx
from loguru import logger

from ..models.graph import DependencyGraph, SCCInfo


class TarjanSCCDetector:
    def detect(self, graph: DependencyGraph) -> DependencyGraph:
        G = self._build_nx_graph(graph)

        raw_sccs = list(nx.strongly_connected_components(G))

        nontrivial_sccs: list[SCCInfo] = []
        dag_nodes: list[str] = []
        scc_idx = 0

        for scc_nodes in raw_sccs:
            if len(scc_nodes) == 1:
                node = next(iter(scc_nodes))
                if G.has_edge(node, node):
                    nontrivial_sccs.append(
                        self._create_scc_info(f"scc_{scc_idx}", scc_nodes, graph)
                    )
                    scc_idx += 1
                else:
                    dag_nodes.append(node)
            else:
                nontrivial_sccs.append(
                    self._create_scc_info(f"scc_{scc_idx}", scc_nodes, graph)
                )
                scc_idx += 1

        topological_order = self._compute_topological_order(
            G, raw_sccs, nontrivial_sccs, dag_nodes
        )

        graph.sccs = nontrivial_sccs
        graph.dag_nodes = dag_nodes
        graph.topological_order = topological_order

        graph.metadata.update({
            "num_clauses": len(graph.clauses),
            "num_edges": len(graph.edges),
            "num_nontrivial_sccs": len(nontrivial_sccs),
            "scc_sizes": [s.size for s in nontrivial_sccs],
            "dag_node_count": len(dag_nodes),
            "dag_ratio": len(dag_nodes) / len(graph.clauses) if graph.clauses else 0,
        })

        logger.info(
            f"Tarjan: {len(nontrivial_sccs)} non-trivial SCCs, "
            f"{len(dag_nodes)} DAG nodes, "
            f"DAG ratio={graph.metadata['dag_ratio']:.1%}"
        )
        return graph

    # ------------------------------------------------------------------
    @staticmethod
    def _build_nx_graph(graph: DependencyGraph) -> nx.DiGraph:
        G = nx.DiGraph()
        for clause_id in graph.clauses:
            G.add_node(clause_id)
        for edge in graph.edges:
            G.add_edge(
                edge.source,
                edge.target,
                weight=edge.weight,
                dep_type=edge.dependency_type.value,
            )
        return G

    @staticmethod
    def _create_scc_info(scc_id: str, node_set: set[str], graph: DependencyGraph) -> SCCInfo:
        clause_ids = sorted(node_set)
        internal_edges = [
            e for e in graph.edges if e.source in node_set and e.target in node_set
        ]
        return SCCInfo(
            id=scc_id,
            clause_ids=clause_ids,
            internal_edges=internal_edges,
            size=len(clause_ids),
        )

    @staticmethod
    def _compute_topological_order(
        G: nx.DiGraph,
        raw_sccs: list[set[str]],
        nontrivial_sccs: list[SCCInfo],
        dag_nodes: list[str],
    ) -> list[dict[str, str]]:
        """构建 condensation DAG 并计算拓扑序"""
        condensation = nx.condensation(G)
        topo_order = list(nx.topological_sort(condensation))

        scc_node_sets = {
            frozenset(s.clause_ids): s.id for s in nontrivial_sccs
        }
        dag_node_set = set(dag_nodes)

        result: list[dict[str, str]] = []
        for cnode in topo_order:
            members = condensation.nodes[cnode]["members"]
            frozen = frozenset(members)

            if frozen in scc_node_sets:
                result.append({"type": "scc", "id": scc_node_sets[frozen]})
            else:
                for node in sorted(members):
                    if node in dag_node_set:
                        result.append({"type": "dag_node", "id": node})

        return result

"""Tests for Module 3: Tarjan SCC detection."""
from __future__ import annotations

from src.models.clause import Clause
from src.models.graph import DependencyGraph, DependencyType, Edge
from src.modules.tarjan import TarjanSCCDetector


def test_diamond_with_scc(diamond_graph: DependencyGraph):
    detector = TarjanSCCDetector()
    graph = detector.detect(diamond_graph)

    assert len(graph.sccs) == 1, "Should detect exactly one non-trivial SCC (c5 ↔ c6)"
    scc = graph.sccs[0]
    assert set(scc.clause_ids) == {"c5", "c6"}
    assert scc.size == 2

    assert set(graph.dag_nodes) == {"c1", "c2", "c3", "c4"}

    assert graph.topological_order, "Topological order should not be empty"

    dag_ids_in_order = [
        item["id"] for item in graph.topological_order if item["type"] == "dag_node"
    ]
    assert "c1" in dag_ids_in_order
    c1_idx = dag_ids_in_order.index("c1")
    for cid in ["c2", "c3"]:
        if cid in dag_ids_in_order:
            assert dag_ids_in_order.index(cid) > c1_idx


def test_pure_dag():
    """All nodes form a DAG — no non-trivial SCCs."""
    clauses = [
        Clause(id=f"x{i}", title=f"X{i}", content=f"Content {i}")
        for i in range(1, 5)
    ]
    edges = [
        Edge(source="x1", target="x2", dependency_type=DependencyType.DEFINES),
        Edge(source="x2", target="x3", dependency_type=DependencyType.CONSTRAINS),
        Edge(source="x3", target="x4", dependency_type=DependencyType.TRIGGERS),
    ]
    graph = DependencyGraph(clauses={c.id: c for c in clauses}, edges=edges)
    detector = TarjanSCCDetector()
    graph = detector.detect(graph)

    assert len(graph.sccs) == 0
    assert set(graph.dag_nodes) == {"x1", "x2", "x3", "x4"}
    assert graph.metadata["dag_ratio"] == 1.0


def test_single_large_scc():
    """All nodes in one big SCC."""
    n = 5
    clauses = [Clause(id=f"n{i}", title=f"N{i}", content=f"c{i}") for i in range(n)]
    edges = [
        Edge(source=f"n{i}", target=f"n{(i + 1) % n}", dependency_type=DependencyType.REFERENCES)
        for i in range(n)
    ]
    graph = DependencyGraph(clauses={c.id: c for c in clauses}, edges=edges)
    detector = TarjanSCCDetector()
    graph = detector.detect(graph)

    assert len(graph.sccs) == 1
    assert graph.sccs[0].size == n
    assert len(graph.dag_nodes) == 0


def test_self_loop():
    """Single node with a self-loop counts as non-trivial SCC."""
    clauses = [Clause(id="s1", title="S1", content="self")]
    edges = [Edge(source="s1", target="s1", dependency_type=DependencyType.MODIFIES)]
    graph = DependencyGraph(clauses={c.id: c for c in clauses}, edges=edges)
    detector = TarjanSCCDetector()
    graph = detector.detect(graph)

    assert len(graph.sccs) == 1
    assert graph.sccs[0].clause_ids == ["s1"]
    assert len(graph.dag_nodes) == 0

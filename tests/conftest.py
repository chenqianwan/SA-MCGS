"""Shared fixtures for SA-MCGS test suite."""
from __future__ import annotations

import pytest

from src.models.clause import Clause, ClauseEvaluation, RiskDimension
from src.models.graph import DependencyGraph, DependencyType, Edge, SCCInfo


def _make_dim(name: str, score: float) -> RiskDimension:
    return RiskDimension(name=name, score=score, reasoning="test")


def _make_eval(clause_id: str, score: float, dim_scores: dict[str, float] | None = None) -> ClauseEvaluation:
    dims = []
    if dim_scores:
        dims = [_make_dim(n, s) for n, s in dim_scores.items()]
    return ClauseEvaluation(
        clause_id=clause_id,
        overall_risk_score=score,
        dimensions=dims,
        reasoning="test evaluation",
    )


@pytest.fixture
def sample_clauses() -> list[Clause]:
    return [
        Clause(id=f"c{i}", title=f"Clause {i}", content=f"Content of clause {i}")
        for i in range(1, 7)
    ]


@pytest.fixture
def diamond_graph(sample_clauses: list[Clause]) -> DependencyGraph:
    """
    Diamond DAG: c1 → c2, c1 → c3, c2 → c4, c3 → c4
    Plus an SCC: c5 ↔ c6
    """
    edges = [
        Edge(source="c1", target="c2", dependency_type=DependencyType.DEFINES),
        Edge(source="c1", target="c3", dependency_type=DependencyType.DEFINES),
        Edge(source="c2", target="c4", dependency_type=DependencyType.CONSTRAINS),
        Edge(source="c3", target="c4", dependency_type=DependencyType.CONSTRAINS),
        Edge(source="c5", target="c6", dependency_type=DependencyType.TRIGGERS),
        Edge(source="c6", target="c5", dependency_type=DependencyType.MODIFIES),
        Edge(source="c4", target="c5", dependency_type=DependencyType.REFERENCES),
    ]
    return DependencyGraph(
        clauses={c.id: c for c in sample_clauses},
        edges=edges,
    )

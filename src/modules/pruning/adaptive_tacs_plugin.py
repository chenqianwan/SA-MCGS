"""Adaptive TACS graph-pruning plugin (Plan B).

Falls back to topology-based pruning (betweenness centrality) when edge
types are homogeneous (>80 % same type), with a strict removal budget.

Corresponds to the ``PlanB_Adaptive`` config in ``run_pruning_v2.py``::

    "PlanB_Adaptive": {
        "enabled": True, "mode": "plan_b",
        "adaptive_tacs_enabled": True,
        "adaptive_tacs_max_removal": 0.35,
        "adaptive_tacs_homogeneity": 0.80,
    }
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from .base import GraphPruningPlugin
from ..graph_pruning import AdaptiveTACS
from ...models.graph import DependencyGraph


@GraphPruningPlugin.register("plan_b")
class AdaptiveTACSPlugin(GraphPruningPlugin):
    """Adaptive TACS: topology fallback when edge types are homogeneous."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.adaptive_tacs = AdaptiveTACS(config)

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        stats: dict[str, Any] = {"plugin": "plan_b"}
        stats["adaptive_tacs"] = self.adaptive_tacs.prune(graph)
        logger.info("AdaptiveTACSPlugin: adaptive topology pruning complete")
        return stats

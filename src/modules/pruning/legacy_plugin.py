"""Legacy graph-pruning plugin: Noise + Hierarchy + Information Bottleneck.

Corresponds to the ``Legacy`` config in ``run_pruning_v2.py``::

    "Legacy": {
        "enabled": True, "mode": "legacy",
        "noise_weight_threshold": 0.35,
        "remove_duplicate_reasoning": True,
        "hierarchy_violation_threshold": 0.6,
        "ib_compression_ratio": 0.15,
    }
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from .base import GraphPruningPlugin
from ..graph_pruning import (
    NoiseEdgeRemover,
    HierarchicalPriorEnforcer,
    InfoBottleneckPruner,
)
from ...models.graph import DependencyGraph


@GraphPruningPlugin.register("legacy")
class LegacyPruningPlugin(GraphPruningPlugin):
    """Three-stage heuristic filtering: noise → hierarchy → info bottleneck."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.noise_remover = NoiseEdgeRemover(config)
        self.hierarchy_enforcer = HierarchicalPriorEnforcer(config)
        self.ib_pruner = InfoBottleneckPruner(config)

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        stats: dict[str, Any] = {"plugin": "legacy"}
        stats["noise"] = self.noise_remover.prune(graph)
        stats["hierarchy"] = self.hierarchy_enforcer.prune(graph)
        stats["info_bottleneck"] = self.ib_pruner.prune(graph)
        logger.info("LegacyPlugin: noise → hierarchy → IB complete")
        return stats

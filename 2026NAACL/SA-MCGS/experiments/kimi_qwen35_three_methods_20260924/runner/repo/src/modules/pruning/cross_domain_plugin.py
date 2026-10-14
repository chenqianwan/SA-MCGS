"""Cross-domain pruning plugin: Noise removal + lightweight IB.

Skips the legal-specific Hierarchical Prior (Def→Obl→Cond→Rem→Lim)
since non-legal domains don't have clause type hierarchies.

Retains:
  1. Noise Edge Removal — universal (self-loops, low-weight, duplicate reasoning)
  2. Info Bottleneck (light) — universal but less aggressive for structured data

Usage in config:
    graph_pruning:
      plugins: ["cross_domain"]
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from .base import GraphPruningPlugin
from ..graph_pruning import NoiseEdgeRemover, InfoBottleneckPruner
from ...models.graph import DependencyGraph


@GraphPruningPlugin.register("cross_domain")
class CrossDomainPruningPlugin(GraphPruningPlugin):
    """Domain-agnostic pruning: noise removal + light info bottleneck."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        pruning_cfg = dict(config)
        gp = dict(pruning_cfg.get("graph_pruning", {}))
        gp.setdefault("noise_weight_threshold", 0.3)
        gp.setdefault("remove_duplicate_reasoning", True)
        gp.setdefault("ib_compression_ratio", 0.10)
        pruning_cfg["graph_pruning"] = gp

        self.noise_remover = NoiseEdgeRemover(pruning_cfg)
        self.ib_pruner = InfoBottleneckPruner(pruning_cfg)

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        stats: dict[str, Any] = {"plugin": "cross_domain"}
        stats["noise"] = self.noise_remover.prune(graph)
        stats["info_bottleneck"] = self.ib_pruner.prune(graph)
        logger.info("CrossDomainPlugin: noise → IB complete (no hierarchy enforcement)")
        return stats

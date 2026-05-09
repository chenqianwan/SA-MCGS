"""Base class and registry for graph pruning plugins.

Graph pruning strategies are loaded as plugins rather than hardcoded in
the main pipeline.  Each plugin:

  1. Subclasses ``GraphPruningPlugin``
  2. Calls ``GraphPruningPlugin.register(name)`` as a class decorator

The orchestrator (``DomainGraphPruner``) discovers strategies at runtime
via the registry and loads only the ones listed in config.
"""
from __future__ import annotations

import abc
from typing import Any

from ...models.graph import DependencyGraph


_PLUGIN_REGISTRY: dict[str, type["GraphPruningPlugin"]] = {}


class GraphPruningPlugin(abc.ABC):
    """Interface that every graph-pruning strategy must implement."""

    def __init__(self, config: dict) -> None:
        self.config = config

    @abc.abstractmethod
    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        """Mutate *graph* in-place and return a stats dict."""

    # ── decorator for self-registration ──────────────────────────
    @classmethod
    def register(cls, name: str):
        """Class decorator: ``@GraphPruningPlugin.register("legacy")``."""
        def _wrap(plugin_cls: type[GraphPruningPlugin]):
            _PLUGIN_REGISTRY[name] = plugin_cls
            return plugin_cls
        return _wrap

    @staticmethod
    def get(name: str) -> type["GraphPruningPlugin"]:
        if name not in _PLUGIN_REGISTRY:
            available = ", ".join(sorted(_PLUGIN_REGISTRY)) or "(none)"
            raise KeyError(
                f"Unknown graph-pruning plugin '{name}'. "
                f"Available: {available}"
            )
        return _PLUGIN_REGISTRY[name]

    @staticmethod
    def available() -> list[str]:
        return sorted(_PLUGIN_REGISTRY)

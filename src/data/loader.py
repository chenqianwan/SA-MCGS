"""Dataset loaders for QuantLaw cross-reference graphs.

QuantLawLoader yields (graph_id, DependencyGraph) pairs — pre-built graphs
that skip the parsing/LLM extraction steps.
"""
from __future__ import annotations

import gzip
import pickle
from pathlib import Path
import networkx as nx
from loguru import logger

from ..models.clause import Clause, ClauseType
from ..models.graph import DependencyGraph, DependencyType, Edge


class _BaseLoader:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        if not self.data_dir.exists():
            logger.warning(f"Data directory does not exist: {data_dir}")


class QuantLawLoader(_BaseLoader):
    """QuantLaw: pre-built cross-reference graphs from Zenodo.

    Source: https://doi.org/10.5281/zenodo.4660133

    Expected layout:
        data_dir/
        ├── us/4_crossreference_graph/{year}.gpickle.gz
        ├── de/4_crossreference_graph/{year}.gpickle.gz
        └── us_reg/4_crossreference_graph/{year}.gpickle.gz

    Each .gpickle.gz is a complete NetworkX DiGraph.
    Hierarchy edges are filtered out; only cross-reference edges are kept.
    """

    name = "QuantLaw"
    JURISDICTIONS = ("us", "de", "us_reg")

    def __init__(self, data_dir: str, config: dict | None = None):
        super().__init__(data_dir)
        ql_cfg = (config or {}).get("quantlaw", {})
        self.hierarchy_keywords = set(
            ql_cfg.get("hierarchy_edge_types", ["containment", "hierarchy", "part_of"])
        )
        self.edge_type_field = ql_cfg.get("edge_type_field", "edge_type")
        self.jurisdictions = ql_cfg.get("jurisdictions", list(self.JURISDICTIONS))

    def load(self) -> list[tuple[str, DependencyGraph]]:
        results: list[tuple[str, DependencyGraph]] = []
        for jur in self.jurisdictions:
            graph_dir = self.data_dir / jur / "4_crossreference_graph"
            if not graph_dir.exists():
                logger.warning(f"QuantLaw: directory not found: {graph_dir}")
                continue
            for gpickle_file in sorted(graph_dir.glob("*.gpickle.gz")):
                year = gpickle_file.stem.replace(".gpickle", "")
                graph_id = f"{jur}_{year}"
                dep_graph = self._load_single(gpickle_file, graph_id)
                if dep_graph:
                    results.append((graph_id, dep_graph))
        logger.info(f"QuantLaw: loaded {len(results)} graphs from {self.data_dir}")
        return results

    def load_single(self, filepath: str | Path) -> tuple[str, DependencyGraph] | None:
        """Load a single .gpickle.gz file."""
        fpath = Path(filepath)
        graph_id = fpath.stem.replace(".gpickle", "")
        dep_graph = self._load_single(fpath, graph_id)
        if dep_graph:
            return (graph_id, dep_graph)
        return None

    def _load_single(self, fpath: Path, graph_id: str) -> DependencyGraph | None:
        try:
            G = self._load_nx_graph(fpath)
        except Exception as e:
            logger.error(f"Failed to load {fpath}: {e}")
            return None

        G = self._filter_hierarchy_edges(G)
        self._remove_isolates(G)

        if G.number_of_nodes() == 0:
            logger.warning(f"QuantLaw: {graph_id} has 0 nodes after filtering; skipping")
            return None

        return self._nx_to_dependency_graph(G, graph_id)

    @staticmethod
    def _load_nx_graph(fpath: Path) -> nx.DiGraph:
        with gzip.open(fpath, "rb") as f:
            G = pickle.load(f)
        if not isinstance(G, nx.DiGraph):
            G = nx.DiGraph(G)
        return G

    def _filter_hierarchy_edges(self, G: nx.DiGraph) -> nx.DiGraph:
        """Remove hierarchy/containment edges, keep only cross-references."""
        to_remove = [
            (u, v) for u, v, d in G.edges(data=True)
            if str(d.get(self.edge_type_field, "")).lower() in self.hierarchy_keywords
               or str(d.get("type", "")).lower() in self.hierarchy_keywords
        ]
        G.remove_edges_from(to_remove)
        if to_remove:
            logger.debug(f"Filtered {len(to_remove)} hierarchy edges")
        return G

    @staticmethod
    def _remove_isolates(G: nx.DiGraph) -> None:
        isolates = list(nx.isolates(G))
        G.remove_nodes_from(isolates)
        if isolates:
            logger.debug(f"Removed {len(isolates)} isolated nodes")

    @staticmethod
    def _nx_to_dependency_graph(G: nx.DiGraph, graph_id: str) -> DependencyGraph:
        """Convert a filtered nx.DiGraph into our DependencyGraph model."""
        clauses: dict[str, Clause] = {}
        for node in G.nodes():
            node_data = G.nodes[node]
            nid = str(node)
            clauses[nid] = Clause(
                id=nid,
                title=node_data.get("heading", node_data.get("title", nid)),
                content=node_data.get("text", node_data.get("content", "")),
                section=node_data.get("section", node_data.get("key", None)),
                clause_type=ClauseType.OTHER,
                metadata={k: str(v) for k, v in node_data.items()
                          if k not in ("heading", "title", "text", "content", "section", "key")},
            )

        edges: list[Edge] = []
        for u, v, d in G.edges(data=True):
            weight = float(d.get("weight", 1.0))
            weight = max(0.0, min(1.0, weight))

            raw_type = str(d.get("edge_type", d.get("type", "references"))).lower()
            dep_type_map = {
                "reference": DependencyType.REFERENCES,
                "references": DependencyType.REFERENCES,
                "cross_reference": DependencyType.REFERENCES,
                "defines": DependencyType.DEFINES,
                "constrains": DependencyType.CONSTRAINS,
                "triggers": DependencyType.TRIGGERS,
                "modifies": DependencyType.MODIFIES,
            }
            dep_type = dep_type_map.get(raw_type, DependencyType.REFERENCES)

            edges.append(Edge(
                source=str(u),
                target=str(v),
                dependency_type=dep_type,
                weight=weight,
            ))

        return DependencyGraph(
            clauses=clauses,
            edges=edges,
            metadata={"source": "quantlaw", "graph_id": graph_id},
        )


def load_dataset(name: str, data_dir: str, config: dict | None = None) -> list:
    """Load a QuantLaw dataset, returns list[tuple[str, DependencyGraph]]."""
    if name.lower() != "quantlaw":
        raise ValueError(f"Unknown dataset: {name}. Available: ['quantlaw']")
    return QuantLawLoader(data_dir, config).load()

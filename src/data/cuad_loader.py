"""CUAD contract loader using graph-grpo-lex ontology.

Converts raw CUAD contract text into SA-MCGS DependencyGraph objects,
following the graph construction methodology of Dechtiar et al. (2025).

Pipeline:
    1. Load raw contract .txt from CUAD_v1
    2. Segment into clauses (rule-based + LLM)
    3. Extract minigraphs per clause (LLM with graph-grpo-lex prompt)
    4. Assemble into full contract graph
    5. Convert to SA-MCGS DependencyGraph

Can also load pre-built graph JSON files (if available).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from ..models.clause import Clause, ClauseType
from ..models.graph import DependencyGraph, DependencyType, Edge

GRPO_EDGE_TYPE_MAP = {
    "IS_PART_OF": DependencyType.REFERENCES,
    "REFERENCES": DependencyType.REFERENCES,
    "DEFINES": DependencyType.DEFINES,
    "USES": DependencyType.REFERENCES,
    "MENTION_PARTY": DependencyType.REFERENCES,
    "MENTIONS_PARTY": DependencyType.REFERENCES,
    "CONTAINS": DependencyType.REFERENCES,
    "REFERS_TO": DependencyType.REFERENCES,
}

GRPO_NODE_TYPE_TO_CLAUSE_TYPE = {
    "CLAUSE": ClauseType.OTHER,
    "DEFINED_TERM": ClauseType.DEFINITION,
    "PARTY": ClauseType.OTHER,
    "VALUE": ClauseType.OTHER,
}

CLAUSE_SECTION_PATTERN = re.compile(
    r"^(?:Section|Article|Clause|SECTION|ARTICLE|CLAUSE)?\s*"
    r"(\d+(?:\.\d+)*)\s*[.:\-–—)]\s*(.+)",
    re.MULTILINE,
)


class CUADLoader:
    """Load CUAD contracts and convert to DependencyGraph.

    Supports two modes:
    1. From pre-built graph JSON (graph-grpo-lex nupunkt_graph format)
    2. From raw contract text (rule-based clause segmentation)
    """

    name = "CUAD"

    def __init__(self, data_dir: str, config: dict | None = None):
        self.data_dir = Path(data_dir)
        cfg = (config or {}).get("cuad", {})
        self.contract_filter = cfg.get("contract_filter", None)
        self.clause_only = cfg.get("clause_only", True)

    def load(self) -> list[tuple[str, DependencyGraph]]:
        results: list[tuple[str, DependencyGraph]] = []

        graph_dir = self.data_dir / "graphs"
        if graph_dir.exists():
            results.extend(self._load_from_graphs(graph_dir))

        if not results:
            txt_dir = self.data_dir / "CUAD_v1" / "CUAD_v1" / "full_contract_txt"
            if txt_dir.exists():
                results.extend(self._load_from_text(txt_dir))

        logger.info(f"CUAD: loaded {len(results)} contract graphs from {self.data_dir}")
        return results

    def load_single_text(self, filepath: str | Path) -> tuple[str, DependencyGraph] | None:
        fpath = Path(filepath)
        if not fpath.exists():
            logger.error(f"File not found: {fpath}")
            return None
        contract_id = fpath.stem
        text = fpath.read_text(encoding="utf-8", errors="replace")
        graph = self._text_to_graph(text, contract_id)
        if graph and len(graph.clauses) > 0:
            return (contract_id, graph)
        return None

    def load_single_graph(self, filepath: str | Path) -> tuple[str, DependencyGraph] | None:
        fpath = Path(filepath)
        if not fpath.exists():
            logger.error(f"File not found: {fpath}")
            return None
        contract_id = fpath.stem.replace("_nupunkt_graph", "").replace("Copy of ", "")
        graph = self._json_to_dependency_graph(fpath, contract_id)
        if graph and len(graph.clauses) > 0:
            return (contract_id, graph)
        return None

    def _load_from_graphs(self, graph_dir: Path) -> list[tuple[str, DependencyGraph]]:
        results = []
        for json_file in sorted(graph_dir.glob("*.json")):
            contract_id = json_file.stem.replace("_nupunkt_graph", "").replace("Copy of ", "")
            if self.contract_filter and contract_id not in self.contract_filter:
                continue
            graph = self._json_to_dependency_graph(json_file, contract_id)
            if graph and len(graph.clauses) > 0:
                results.append((contract_id, graph))
        return results

    def _load_from_text(self, txt_dir: Path) -> list[tuple[str, DependencyGraph]]:
        results = []
        for txt_file in sorted(txt_dir.glob("*.txt")):
            contract_id = txt_file.stem
            if self.contract_filter and contract_id not in self.contract_filter:
                continue
            text = txt_file.read_text(encoding="utf-8", errors="replace")
            graph = self._text_to_graph(text, contract_id)
            if graph and len(graph.clauses) > 0:
                results.append((contract_id, graph))
            else:
                logger.debug(f"CUAD: skipped {contract_id} (no clauses extracted)")
        return results

    def _json_to_dependency_graph(
        self, json_path: Path, contract_id: str
    ) -> DependencyGraph | None:
        """Convert a graph-grpo-lex JSON graph to SA-MCGS DependencyGraph."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {json_path}: {e}")
            return None

        nodes_raw = data.get("nodes", [])
        edges_raw = data.get("edges", [])

        clauses: dict[str, Clause] = {}
        for node in nodes_raw:
            nid = str(node.get("id", ""))
            node_type = node.get("node_type", node.get("type", "CLAUSE"))

            if self.clause_only and node_type != "CLAUSE":
                continue

            clause_type = GRPO_NODE_TYPE_TO_CLAUSE_TYPE.get(node_type, ClauseType.OTHER)
            title = node.get("title", node.get("name", node.get("label", nid)))
            content = node.get("text", node.get("content", ""))

            clauses[nid] = Clause(
                id=nid,
                title=title or nid,
                content=content,
                clause_type=clause_type,
                metadata={
                    "node_type": node_type,
                    "source": "cuad_grpo",
                    **{k: v for k, v in node.items()
                       if k not in ("id", "node_type", "type", "title", "name",
                                    "label", "text", "content")},
                },
            )

        edges: list[Edge] = []
        for edge in edges_raw:
            src = str(edge.get("src", edge.get("source", "")))
            tgt = str(edge.get("tgt", edge.get("target", "")))
            edge_type = edge.get("type", edge.get("edge_type", "REFERENCES"))

            if self.clause_only and (src not in clauses or tgt not in clauses):
                continue

            dep_type = GRPO_EDGE_TYPE_MAP.get(edge_type, DependencyType.REFERENCES)
            weight = float(edge.get("weight", 1.0))
            weight = max(0.0, min(1.0, weight))

            edges.append(Edge(
                source=src,
                target=tgt,
                dependency_type=dep_type,
                weight=weight,
                reasoning=edge_type,
            ))

        return DependencyGraph(
            clauses=clauses,
            edges=edges,
            metadata={
                "source": "cuad",
                "graph_id": contract_id,
                "ontology": "graph-grpo-lex",
                "total_raw_nodes": len(nodes_raw),
                "total_raw_edges": len(edges_raw),
            },
        )

    def _text_to_graph(self, text: str, contract_id: str) -> DependencyGraph | None:
        """Rule-based clause segmentation and reference extraction.

        For full LLM-based extraction, use the pipeline's ClauseParser + GraphBuilder
        (Module 1-2) with graph-grpo-lex prompts.
        """
        clauses, edges = self._segment_and_link(text, contract_id)
        if not clauses:
            return None

        return DependencyGraph(
            clauses=clauses,
            edges=edges,
            metadata={
                "source": "cuad",
                "graph_id": contract_id,
                "extraction": "rule_based",
            },
        )

    def _segment_and_link(
        self, text: str, contract_id: str
    ) -> tuple[dict[str, Clause], list[Edge]]:
        """Segment contract text into clauses and detect cross-references."""
        lines = text.split("\n")
        clauses: dict[str, Clause] = {}
        current_id: str | None = None
        current_title: str = ""
        current_lines: list[str] = []

        def _flush():
            nonlocal current_id, current_title, current_lines
            if current_id and current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    clauses[current_id] = Clause(
                        id=current_id,
                        title=current_title or current_id,
                        content=content,
                        clause_type=self._infer_clause_type(current_title, content),
                        metadata={"source": "cuad_text", "contract_id": contract_id},
                    )
            current_id = None
            current_title = ""
            current_lines = []

        for line in lines:
            line_stripped = line.strip()
            match = CLAUSE_SECTION_PATTERN.match(line_stripped)
            if match:
                _flush()
                current_id = match.group(1)
                current_title = match.group(2).strip()
                current_lines = [line_stripped]
            elif current_id:
                current_lines.append(line_stripped)

        _flush()

        if not clauses and text.strip():
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            for i, para in enumerate(paragraphs[:100]):
                cid = str(i + 1)
                clauses[cid] = Clause(
                    id=cid,
                    title=para[:60].replace("\n", " "),
                    content=para,
                    clause_type=ClauseType.OTHER,
                    metadata={"source": "cuad_paragraph", "contract_id": contract_id},
                )

        edges = self._extract_references(clauses)
        return clauses, edges

    def _extract_references(self, clauses: dict[str, Clause]) -> list[Edge]:
        """Detect cross-references between clauses based on text patterns."""
        edges: list[Edge] = []
        ref_pattern = re.compile(
            r"(?:Section|Article|Clause|Paragraph|§)\s*(\d+(?:\.\d+)*)",
            re.IGNORECASE,
        )
        clause_ids = set(clauses.keys())
        seen = set()

        for cid, clause in clauses.items():
            for match in ref_pattern.finditer(clause.content):
                ref_id = match.group(1)
                if ref_id in clause_ids and ref_id != cid:
                    edge_key = (cid, ref_id)
                    if edge_key not in seen:
                        seen.add(edge_key)
                        edges.append(Edge(
                            source=cid,
                            target=ref_id,
                            dependency_type=DependencyType.REFERENCES,
                            weight=1.0,
                        ))

        for cid, clause in clauses.items():
            parts = cid.split(".")
            if len(parts) > 1:
                parent_id = ".".join(parts[:-1])
                if parent_id in clause_ids:
                    edge_key = (cid, parent_id)
                    if edge_key not in seen:
                        seen.add(edge_key)
                        edges.append(Edge(
                            source=cid,
                            target=parent_id,
                            dependency_type=DependencyType.REFERENCES,
                            weight=0.5,
                            reasoning="IS_PART_OF",
                        ))

        return edges

    @staticmethod
    def _infer_clause_type(title: str, content: str) -> ClauseType:
        title_lower = (title or "").lower()
        content_lower = content[:200].lower()
        combined = title_lower + " " + content_lower

        if any(k in combined for k in ["definition", "shall mean", "means", "\"means\""]):
            return ClauseType.DEFINITION
        if any(k in combined for k in ["shall", "obligation", "must", "agrees to"]):
            return ClauseType.OBLIGATION
        if any(k in combined for k in ["if ", "provided that", "condition", "subject to"]):
            return ClauseType.CONDITION
        if any(k in combined for k in ["remedy", "damages", "indemnif", "liable"]):
            return ClauseType.REMEDY
        if any(k in combined for k in ["limitation", "cap", "exclusion", "waiver"]):
            return ClauseType.LIMITATION
        return ClauseType.OTHER

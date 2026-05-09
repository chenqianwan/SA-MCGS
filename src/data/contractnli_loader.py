"""ContractNLI dataset loader.

Converts Stanford ContractNLI (Koreeda & Manning, EMNLP 2021) into
SA-MCGS DependencyGraph objects.

Mapping strategy:
- Each span → a Clause node (text segment with character offsets)
- Cross-references between spans → REFERENCES edges
- IS_PART_OF edges → inferred from sequential adjacency or shared sections
- Evidence chains from annotations → golden evaluation data

Source: https://stanfordnlp.github.io/contract-nli/
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from ..models.clause import Clause, ClauseType
from ..models.graph import DependencyGraph, DependencyType, Edge


_SECTION_RE = re.compile(
    r"(?:Section|Article|Clause|Paragraph|§)\s*(\d+(?:\.\d+)*(?:\([a-z]\))?)",
    re.IGNORECASE,
)
_CLAUSE_TYPE_HINTS = {
    "definition": ClauseType.DEFINITION,
    "shall mean": ClauseType.DEFINITION,
    '"means"': ClauseType.DEFINITION,
    "shall": ClauseType.OBLIGATION,
    "must": ClauseType.OBLIGATION,
    "agrees to": ClauseType.OBLIGATION,
    "if ": ClauseType.CONDITION,
    "provided that": ClauseType.CONDITION,
    "subject to": ClauseType.CONDITION,
    "indemnif": ClauseType.REMEDY,
    "damages": ClauseType.REMEDY,
    "liable": ClauseType.REMEDY,
    "limitation": ClauseType.LIMITATION,
    "exclusion": ClauseType.LIMITATION,
    "waiver": ClauseType.LIMITATION,
}


class ContractNLILoader:
    """Load ContractNLI JSON and convert to DependencyGraph."""

    name = "ContractNLI"

    def __init__(self, data_dir: str, config: dict | None = None):
        self.data_dir = Path(data_dir)
        cfg = (config or {}).get("contractnli", {})
        self.min_span_length = cfg.get("min_span_length", 20)

    def load(self, split: str = "dev") -> list[tuple[str, DependencyGraph, dict]]:
        """Load a split and return (doc_id, graph, annotations) triples."""
        json_path = self.data_dir / f"{split}.json"
        if not json_path.exists():
            logger.error(f"ContractNLI split not found: {json_path}")
            return []

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        labels = data.get("labels", {})
        results = []
        for doc in data.get("documents", []):
            doc_id = f"cnli_{doc['id']}"
            graph, annotations = self._doc_to_graph(doc, labels)
            if graph and len(graph.clauses) > 0:
                results.append((doc_id, graph, annotations))

        logger.info(
            f"ContractNLI: loaded {len(results)} documents from {split}.json "
            f"({sum(len(g.clauses) for _, g, _ in results)} total clauses)"
        )
        return results

    def load_single(self, split: str, doc_index: int = 0):
        """Load a single document by index."""
        json_path = self.data_dir / f"{split}.json"
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        labels = data.get("labels", {})
        doc = data["documents"][doc_index]
        doc_id = f"cnli_{doc['id']}"
        graph, annotations = self._doc_to_graph(doc, labels)
        return doc_id, graph, annotations

    def _doc_to_graph(
        self, doc: dict, labels: dict
    ) -> tuple[DependencyGraph | None, dict]:
        """Convert a single ContractNLI document to DependencyGraph."""
        text = doc.get("text", "")
        raw_spans = doc.get("spans", [])
        annotations_raw = {}
        if doc.get("annotation_sets"):
            annotations_raw = doc["annotation_sets"][0].get("annotations", {})

        clauses: dict[str, Clause] = {}
        span_id_map: dict[int, str] = {}

        for idx, (start, end) in enumerate(raw_spans):
            span_text = text[start:end].strip()
            if len(span_text) < self.min_span_length:
                continue

            clause_id = f"s{idx}"
            span_id_map[idx] = clause_id

            section_match = re.match(
                r"^(\d+(?:\.\d+)*(?:\([a-z]\))?)\s*[.):]\s*(.+)",
                span_text[:100],
                re.DOTALL,
            )
            if section_match:
                title = section_match.group(2).strip()[:80]
            else:
                title = span_text[:60].replace("\n", " ")

            clause_type = self._infer_type(span_text)

            clauses[clause_id] = Clause(
                id=clause_id,
                title=title,
                content=span_text,
                clause_type=clause_type,
                metadata={
                    "span_index": idx,
                    "char_start": start,
                    "char_end": end,
                    "source": "contractnli",
                },
            )

        edges = self._extract_edges(clauses, span_id_map, raw_spans, text)

        annotations = self._build_annotations(
            annotations_raw, labels, span_id_map
        )

        graph = DependencyGraph(
            clauses=clauses,
            edges=edges,
            metadata={
                "source": "contractnli",
                "doc_id": doc.get("id"),
                "file_name": doc.get("file_name", ""),
                "total_raw_spans": len(raw_spans),
                "filtered_clauses": len(clauses),
                "num_hypotheses": len(annotations),
            },
        )

        return graph, annotations

    def _extract_edges(
        self,
        clauses: dict[str, Clause],
        span_id_map: dict[int, str],
        raw_spans: list,
        text: str,
    ) -> list[Edge]:
        """Extract edges: cross-references + sequential adjacency."""
        edges: list[Edge] = []
        seen: set[tuple[str, str, str]] = set()

        section_to_clause: dict[str, str] = {}
        for cid, clause in clauses.items():
            match = re.match(r"^(\d+(?:\.\d+)*)", clause.content[:30])
            if match:
                section_to_clause[match.group(1)] = cid

        for cid, clause in clauses.items():
            for ref_match in _SECTION_RE.finditer(clause.content):
                ref_section = ref_match.group(1)
                ref_cid = section_to_clause.get(ref_section)
                if ref_cid and ref_cid != cid:
                    key = (cid, ref_cid, "ref")
                    if key not in seen:
                        seen.add(key)
                        edges.append(Edge(
                            source=cid,
                            target=ref_cid,
                            dependency_type=DependencyType.REFERENCES,
                            weight=1.0,
                        ))

        sorted_ids = sorted(
            clauses.keys(),
            key=lambda x: clauses[x].metadata.get("span_index", 0),
        )
        for i in range(len(sorted_ids) - 1):
            curr = sorted_ids[i]
            nxt = sorted_ids[i + 1]

            curr_match = re.match(r"^(\d+(?:\.\d+)*)", clauses[curr].content[:30])
            nxt_match = re.match(r"^(\d+(?:\.\d+)*)", clauses[nxt].content[:30])

            if curr_match and nxt_match:
                curr_parts = curr_match.group(1).split(".")
                nxt_parts = nxt_match.group(1).split(".")
                if len(nxt_parts) > len(curr_parts) and nxt_parts[:len(curr_parts)] == curr_parts:
                    key = (nxt, curr, "part")
                    if key not in seen:
                        seen.add(key)
                        edges.append(Edge(
                            source=nxt,
                            target=curr,
                            dependency_type=DependencyType.REFERENCES,
                            weight=0.5,
                            reasoning="IS_PART_OF",
                        ))

        return edges

    def _build_annotations(
        self,
        annotations_raw: dict,
        labels: dict,
        span_id_map: dict[int, str],
    ) -> dict[str, dict[str, Any]]:
        """Build structured annotations with evidence mapped to clause IDs."""
        result = {}
        for hid, ann in annotations_raw.items():
            evidence_clause_ids = [
                span_id_map[s] for s in ann.get("spans", [])
                if s in span_id_map
            ]
            result[hid] = {
                "hypothesis": labels.get(hid, {}).get("hypothesis", ""),
                "choice": ann.get("choice", "NotMentioned"),
                "evidence_spans": ann.get("spans", []),
                "evidence_clause_ids": evidence_clause_ids,
            }
        return result

    @staticmethod
    def _infer_type(text: str) -> ClauseType:
        lower = text[:200].lower()
        for hint, ctype in _CLAUSE_TYPE_HINTS.items():
            if hint in lower:
                return ctype
        return ClauseType.OTHER

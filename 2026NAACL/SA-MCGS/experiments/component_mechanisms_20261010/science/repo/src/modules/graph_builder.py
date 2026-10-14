"""Module 2: 依赖图构建

输入: list[Clause]
输出: DependencyGraph (无 SCC 信息)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from loguru import logger

from ..llm.base import BaseLLMClient
from ..models.clause import Clause
from ..models.graph import DependencyGraph, DependencyType, Edge


class GraphBuilder:
    def __init__(self, llm_client: BaseLLMClient, config: dict):
        self.llm = llm_client
        graph_cfg = config.get("graph", {})
        self.max_clauses_per_batch = graph_cfg.get("max_clauses_per_batch", 20)
        self.min_weight = graph_cfg.get("min_dependency_weight", 0.3)
        self._prompt_template: Optional[str] = None

    def load_prompt(self, path: str) -> None:
        self._prompt_template = Path(path).read_text(encoding="utf-8")

    async def build(self, clauses: list[Clause]) -> DependencyGraph:
        batches = self._create_batches(clauses)
        all_edges: list[Edge] = []

        for batch in batches:
            edges = await self._extract_dependencies(batch, clauses)
            all_edges.extend(edges)

        edges = self._deduplicate_and_validate(all_edges, clauses)
        logger.info(f"Dependency graph: {len(clauses)} nodes, {len(edges)} edges")

        return DependencyGraph(
            clauses={c.id: c for c in clauses},
            edges=edges,
        )

    # ------------------------------------------------------------------
    def _create_batches(self, clauses: list[Clause]) -> list[list[Clause]]:
        batches = []
        for i in range(0, len(clauses), self.max_clauses_per_batch):
            batches.append(clauses[i : i + self.max_clauses_per_batch])
        return batches

    async def _extract_dependencies(
        self, batch: list[Clause], all_clauses: list[Clause]
    ) -> list[Edge]:
        prompt = self._build_prompt(batch, all_clauses)
        try:
            result = await self.llm.call_json(prompt)
            raw_edges = result if isinstance(result, list) else result.get("dependencies", [])
        except Exception:
            logger.warning("LLM dependency extraction failed for a batch; skipping")
            return []

        edges = []
        for item in raw_edges:
            try:
                dep_type = DependencyType(item.get("type", "references"))
            except ValueError:
                dep_type = DependencyType.REFERENCES

            weight = float(item.get("weight", 1.0))
            if weight < self.min_weight:
                continue

            edges.append(Edge(
                source=item["source"],
                target=item["target"],
                dependency_type=dep_type,
                weight=weight,
                reasoning=item.get("reasoning", ""),
            ))

        return edges

    def _deduplicate_and_validate(
        self, edges: list[Edge], clauses: list[Clause]
    ) -> list[Edge]:
        valid_ids = {c.id for c in clauses}
        seen: set[tuple[str, str]] = set()
        result = []
        for e in edges:
            key = (e.source, e.target)
            if key in seen:
                continue
            if e.source not in valid_ids or e.target not in valid_ids:
                continue
            if e.source == e.target:
                continue
            seen.add(key)
            result.append(e)
        return result

    # ------------------------------------------------------------------
    def _build_prompt(self, batch: list[Clause], all_clauses: list[Clause]) -> str:
        all_summary = "\n".join(
            f"- {c.id}: {c.title}" for c in all_clauses
        )
        batch_detail = "\n\n".join(
            f"### {c.id}: {c.title}\n{c.content}" for c in batch
        )

        if self._prompt_template:
            return (
                self._prompt_template
                .replace("{all_clauses_summary}", all_summary)
                .replace("{batch_clauses_full_text}", batch_detail)
            )

        return (
            "You are analyzing a legal contract to identify dependencies between clauses.\n\n"
            "A dependency exists when understanding or evaluating the risk of one clause "
            "requires knowledge of another clause. Specifically:\n"
            "- Clause A DEPENDS ON Clause B if: to assess the risk of A, you need to first understand B.\n\n"
            "Dependency types:\n"
            '- "defines": B defines terms or concepts used in A\n'
            '- "constrains": B places constraints that affect A\'s risk level\n'
            '- "triggers": B\'s conditions can trigger A\n'
            '- "modifies": B modifies A\'s enforceability or scope\n'
            '- "references": A explicitly references B\n\n'
            f"Here are ALL clauses in the contract:\n{all_summary}\n\n"
            f"Now analyze dependencies for these specific clauses:\n{batch_detail}\n\n"
            "For each dependency found, provide:\n"
            "- source: the clause ID that is depended upon\n"
            "- target: the clause ID that depends on it\n"
            "- type: one of the dependency types above\n"
            "- weight: 0.0-1.0 how strong is this dependency\n"
            "- reasoning: one sentence explaining why\n\n"
            'Output as JSON: {"dependencies": '
            '[{"source": "...", "target": "...", "type": "...", "weight": 0.0, "reasoning": "..."}]}\n\n'
            "Be conservative: only report dependencies that would genuinely affect risk assessment."
        )

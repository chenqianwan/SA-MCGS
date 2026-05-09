"""Module 4: DAG 确定性评估

按拓扑序评估所有 DAG 节点，每个节点收集上游评估结果作为上下文，
调用 LLM 做确定性（temperature=0）评估。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import networkx as nx
from loguru import logger

from ..llm.base import BaseLLMClient
from ..models.clause import Clause, ClauseEvaluation, RiskDimension
from ..models.graph import DependencyGraph


class DAGEvaluator:
    def __init__(self, llm_client: BaseLLMClient, config: dict):
        self.llm = llm_client
        self.config = config
        self._prompt_template: Optional[str] = None

    def load_prompt(self, path: str) -> None:
        self._prompt_template = Path(path).read_text(encoding="utf-8")

    async def evaluate(self, graph: DependencyGraph, on_progress: Optional[callable] = None) -> dict[str, ClauseEvaluation]:
        results: dict[str, ClauseEvaluation] = {}
        nx_graph = _build_nx_graph(graph)

        total = len([item for item in graph.topological_order if item["type"] == "dag_node"])
        current = 0

        for item in graph.topological_order:
            if item["type"] == "dag_node":
                clause_id = item["id"]
                upstream = self._gather_upstream_context(clause_id, nx_graph, results, graph)
                evaluation = await self._evaluate_clause(graph.clauses[clause_id], upstream)
                results[clause_id] = evaluation
                current += 1
                logger.debug(f"DAG evaluated {clause_id}: risk={evaluation.overall_risk_score:.3f}")
                if on_progress:
                    await on_progress(current, total, f"Evaluating DAG: {clause_id}")

            elif item["type"] == "scc":
                scc = next((s for s in graph.sccs if s.id == item["id"]), None)
                if scc and scc.is_collapsed and scc.collapsed_value:
                    for cid, ev in scc.collapsed_value.items():
                        results[cid] = ev

        logger.info(f"DAG evaluation complete: {len(results)} clauses evaluated")
        return results

    # ------------------------------------------------------------------
    def _gather_upstream_context(
        self,
        clause_id: str,
        nx_graph: nx.DiGraph,
        existing_results: dict[str, ClauseEvaluation],
        graph: DependencyGraph,
    ) -> list[dict]:
        context = []
        for pred_id in nx_graph.predecessors(clause_id):
            if pred_id in existing_results:
                clause = graph.clauses[pred_id]
                ev = existing_results[pred_id]
                context.append({
                    "clause_id": pred_id,
                    "clause_title": clause.title,
                    "clause_content": clause.content[:500],
                    "risk_score": ev.overall_risk_score,
                    "reasoning": ev.reasoning,
                })
        return context

    async def _evaluate_clause(
        self, clause: Clause, upstream_context: list[dict]
    ) -> ClauseEvaluation:
        prompt = self._build_prompt(clause, upstream_context)
        try:
            data = await self.llm.call_json(prompt, temperature=0.0)
        except Exception:
            logger.warning(f"LLM evaluation failed for {clause.id}; returning default")
            return ClauseEvaluation(clause_id=clause.id, overall_risk_score=0.5, reasoning="LLM call failed")

        dims = []
        for d in data.get("dimensions", []):
            if isinstance(d, dict):
                dims.append(RiskDimension(
                    name=str(d.get("name", "unknown")),
                    score=float(d.get("score", 0.5)),
                    reasoning=str(d.get("reasoning", "")),
                ))
            elif isinstance(d, (int, float)):
                dims.append(RiskDimension(name="unknown", score=float(d), reasoning=""))

        return ClauseEvaluation(
            clause_id=clause.id,
            overall_risk_score=float(data.get("overall_risk_score", 0.5)),
            dimensions=dims,
            reasoning=data.get("reasoning", ""),
            context_used=[c["clause_id"] for c in upstream_context],
        )

    def _build_prompt(self, clause: Clause, upstream_context: list[dict]) -> str:
        ctx_text = ""
        if upstream_context:
            parts = []
            for c in upstream_context:
                parts.append(
                    f"- **{c['clause_id']}** ({c['clause_title']}): "
                    f"risk={c['risk_score']:.2f}. {c['reasoning']}"
                )
            ctx_text = "\n".join(parts)
        else:
            ctx_text = "No upstream dependencies."

        if self._prompt_template:
            return (
                self._prompt_template
                .replace("{clause_id}", clause.id)
                .replace("{clause_title}", clause.title)
                .replace("{clause_content}", clause.content)
                .replace("{upstream_context_formatted}", ctx_text)
            )

        return (
            "You are a legal risk assessor evaluating a specific contract clause.\n\n"
            f"## Clause to Evaluate\nID: {clause.id}\nTitle: {clause.title}\n"
            f"Content:\n{clause.content}\n\n"
            f"## Context: Upstream Clause Evaluations\n{ctx_text}\n\n"
            "## Task\n"
            "Evaluate the risk of this clause considering the upstream context. Provide:\n"
            "1. overall_risk_score: float 0.0 (no risk) to 1.0 (extreme risk)\n"
            "2. dimensions: evaluate each of these risk dimensions:\n"
            "   - financial_exposure, liability_scope, termination_risk, "
            "compliance_burden, ambiguity\n"
            "3. reasoning: explain your assessment in 2-3 sentences\n\n"
            "Output as JSON:\n"
            '{"overall_risk_score": 0.0, '
            '"dimensions": [{"name": "...", "score": 0.0, "reasoning": "..."}], '
            '"reasoning": "..."}'
        )


def _build_nx_graph(graph: DependencyGraph) -> nx.DiGraph:
    G = nx.DiGraph()
    for cid in graph.clauses:
        G.add_node(cid)
    for edge in graph.edges:
        G.add_edge(edge.source, edge.target)
    return G

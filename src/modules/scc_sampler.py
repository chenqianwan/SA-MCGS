"""Module 5: SCC 多次采样与搜索树构建

对每个非平凡 SCC，将内部所有条款整体喂给 LLM，跑 K 次（temperature > 0），
每次得到一组联合评估结果，作为搜索树的一个分支。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from statistics import variance as stat_variance
from typing import Any, Optional

import networkx as nx
from loguru import logger

from ..llm.base import BaseLLMClient
from ..models.clause import Clause, ClauseEvaluation, RiskDimension
from ..models.graph import DependencyGraph, Edge, SCCInfo
from ..models.search_tree import SCCBranch, SearchTree, SearchTreeEdge, SearchTreeNode


class SCCSampler:
    def __init__(self, llm_client: BaseLLMClient, config: dict):
        self.llm = llm_client
        scc_cfg = config.get("scc", {})
        self.num_samples = scc_cfg.get("num_samples", 5)
        self.temperature = scc_cfg.get("temperature", 0.7)
        self.max_tokens = scc_cfg.get("max_tokens", 4096)
        self.compact_threshold = scc_cfg.get("compact_threshold", 6)
        self._prompt_template: Optional[str] = None

    def load_prompt(self, path: str) -> None:
        self._prompt_template = Path(path).read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    async def sample_all_sccs(
        self,
        graph: DependencyGraph,
        dag_results: dict[str, ClauseEvaluation],
        on_progress: Optional[callable] = None,
    ) -> dict[str, list[dict[str, Any]]]:
        scc_samples: dict[str, list[dict[str, Any]]] = {}

        total_sccs = len(graph.sccs)
        for i, scc in enumerate(graph.sccs):
            if on_progress:
                await on_progress(i, total_sccs, f"Sampling SCC {scc.id} ({i+1}/{total_sccs})")
            upstream = self._gather_scc_upstream_context(scc, graph, dag_results)
            samples = await self._sample_scc(scc, graph, upstream)
            scc.samples = samples
            scc.variance = self._compute_variance(samples)
            scc_samples[scc.id] = samples

            logger.info(
                f"SCC {scc.id} (size={scc.size}): "
                f"{len(samples)} samples, variance={scc.variance:.4f}"
            )
        
        if on_progress and total_sccs > 0:
            await on_progress(total_sccs, total_sccs, "SCC Sampling complete")

        return scc_samples

    async def _sample_scc(
        self,
        scc: SCCInfo,
        graph: DependencyGraph,
        upstream_context: list[dict],
    ) -> list[dict[str, Any]]:
        clauses = [graph.clauses[cid] for cid in scc.clause_ids]
        use_compact = len(clauses) >= self.compact_threshold
        prompt = self._build_joint_prompt(
            clauses, scc.internal_edges, upstream_context, compact=use_compact
        )
        if use_compact:
            logger.info(
                f"SCC {scc.id}: using compact prompt for {len(clauses)} clauses "
                f"(max_tokens={self.max_tokens})"
            )

        tasks = [
            self.llm.call_json(
                prompt, temperature=self.temperature, max_tokens=self.max_tokens
            )
            for _ in range(self.num_samples)
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        samples: list[dict[str, Any]] = []
        for i, resp in enumerate(responses):
            if isinstance(resp, Exception):
                logger.warning(f"SCC {scc.id} sample {i} failed: {resp}")
                continue
            evaluations = self._parse_joint_evaluation(
                resp, scc.clause_ids, compact=use_compact
            )
            samples.append({"sample_id": i, "evaluations": evaluations})

        if not samples:
            logger.error(f"SCC {scc.id}: all samples failed; creating fallback")
            fallback_eval = {
                cid: ClauseEvaluation(clause_id=cid, overall_risk_score=0.5, reasoning="Fallback")
                for cid in scc.clause_ids
            }
            samples.append({"sample_id": 0, "evaluations": fallback_eval})

        return samples

    # ------------------------------------------------------------------
    def _gather_scc_upstream_context(
        self,
        scc: SCCInfo,
        graph: DependencyGraph,
        dag_results: dict[str, ClauseEvaluation],
    ) -> list[dict]:
        scc_set = set(scc.clause_ids)
        upstream_ids: set[str] = set()
        for edge in graph.edges:
            if edge.target in scc_set and edge.source not in scc_set:
                upstream_ids.add(edge.source)

        context = []
        for uid in sorted(upstream_ids):
            if uid in dag_results:
                ev = dag_results[uid]
                clause = graph.clauses[uid]
                context.append({
                    "clause_id": uid,
                    "clause_title": clause.title,
                    "risk_score": ev.overall_risk_score,
                    "reasoning": ev.reasoning,
                })
        return context

    def _parse_joint_evaluation(
        self, data: dict, clause_ids: list[str], *, compact: bool = False
    ) -> dict[str, ClauseEvaluation]:
        raw_evals = data.get("clause_evaluations", data)
        results: dict[str, ClauseEvaluation] = {}

        for cid in clause_ids:
            if cid in raw_evals:
                item = raw_evals[cid]
                if not isinstance(item, dict):
                    results[cid] = ClauseEvaluation(
                        clause_id=cid,
                        overall_risk_score=float(item) if isinstance(item, (int, float)) else 0.5,
                        reasoning="Non-dict clause evaluation",
                    )
                    continue
                dims = [] if compact else self._parse_dimensions(item.get("dimensions", []))
                results[cid] = ClauseEvaluation(
                    clause_id=cid,
                    overall_risk_score=float(item.get("overall_risk_score", 0.5)),
                    dimensions=dims,
                    reasoning=str(item.get("reasoning", "")),
                )
            else:
                results[cid] = ClauseEvaluation(
                    clause_id=cid, overall_risk_score=0.5, reasoning="Missing from LLM response"
                )

        return results

    @staticmethod
    def _parse_dimensions(raw_dims: Any) -> list[RiskDimension]:
        """Parse dimensions robustly, handling various LLM output formats."""
        if not isinstance(raw_dims, list):
            return []
        dims = []
        for d in raw_dims:
            if isinstance(d, dict):
                dims.append(RiskDimension(
                    name=str(d.get("name", "unknown")),
                    score=float(d.get("score", 0.5)),
                    reasoning=str(d.get("reasoning", "")),
                ))
            elif isinstance(d, (int, float)):
                dims.append(RiskDimension(name="unknown", score=float(d), reasoning=""))
            # Skip strings and other non-parseable formats
        return dims

    @staticmethod
    def _compute_variance(samples: list[dict[str, Any]]) -> float:
        if len(samples) < 2:
            return 0.0

        clause_ids = list(samples[0]["evaluations"].keys())
        variances: list[float] = []
        for cid in clause_ids:
            scores = [s["evaluations"][cid].overall_risk_score for s in samples]
            variances.append(stat_variance(scores) if len(scores) > 1 else 0.0)

        return sum(variances) / len(variances) if variances else 0.0

    # ------------------------------------------------------------------
    def build_search_tree(
        self,
        graph: DependencyGraph,
        scc_samples: dict[str, list[dict[str, Any]]],
    ) -> SearchTree:
        scc_topo_order = [
            item["id"] for item in graph.topological_order if item["type"] == "scc"
        ]

        nodes: dict[str, SearchTreeNode] = {}
        for scc in graph.sccs:
            if scc.is_collapsed:
                continue

            branches = []
            for sample in scc.samples:
                branches.append(SCCBranch(
                    branch_id=f"{scc.id}_branch_{sample['sample_id']}",
                    scc_id=scc.id,
                    evaluation=sample["evaluations"],
                ))

            depth = scc_topo_order.index(scc.id) if scc.id in scc_topo_order else 0
            nodes[scc.id] = SearchTreeNode(
                scc_id=scc.id,
                branches=branches,
                depth=depth,
            )

        edges = self._build_tree_edges(graph, nodes)
        root_ids = self._find_root_sccs(graph, nodes)
        active_topo = [sid for sid in scc_topo_order if sid in nodes]

        logger.info(
            f"Search tree: {len(nodes)} SCC nodes, "
            f"{sum(len(n.branches) for n in nodes.values())} total branches"
        )

        return SearchTree(
            nodes=nodes,
            edges=edges,
            root_scc_ids=root_ids,
            scc_topological_order=active_topo,
        )

    @staticmethod
    def _build_tree_edges(
        graph: DependencyGraph, nodes: dict[str, SearchTreeNode]
    ) -> list[SearchTreeEdge]:
        scc_lookup: dict[str, str] = {}
        for scc in graph.sccs:
            for cid in scc.clause_ids:
                scc_lookup[cid] = scc.id

        edge_pairs: set[tuple[str, str]] = set()
        for edge in graph.edges:
            src_scc = scc_lookup.get(edge.source)
            tgt_scc = scc_lookup.get(edge.target)
            if (
                src_scc
                and tgt_scc
                and src_scc != tgt_scc
                and src_scc in nodes
                and tgt_scc in nodes
            ):
                edge_pairs.add((src_scc, tgt_scc))

        return [
            SearchTreeEdge(parent_scc_id=p, child_scc_id=c, chosen_branch_id="")
            for p, c in edge_pairs
        ]

    @staticmethod
    def _find_root_sccs(
        graph: DependencyGraph, nodes: dict[str, SearchTreeNode]
    ) -> list[str]:
        """找到没有 SCC 上游的 SCC（即搜索树根节点）"""
        scc_lookup: dict[str, str] = {}
        for scc in graph.sccs:
            for cid in scc.clause_ids:
                scc_lookup[cid] = scc.id

        has_scc_parent: set[str] = set()
        for edge in graph.edges:
            src_scc = scc_lookup.get(edge.source)
            tgt_scc = scc_lookup.get(edge.target)
            if src_scc and tgt_scc and src_scc != tgt_scc and tgt_scc in nodes:
                has_scc_parent.add(tgt_scc)

        return [sid for sid in nodes if sid not in has_scc_parent]

    # ------------------------------------------------------------------
    def _build_joint_prompt(
        self,
        clauses: list[Clause],
        internal_edges: list[Edge],
        upstream_context: list[dict],
        *,
        compact: bool = False,
    ) -> str:
        clauses_fmt = "\n\n".join(
            f"### {c.id}: {c.title}\n{c.content}" for c in clauses
        )
        deps_fmt = "\n".join(
            f"- {e.source} → {e.target} ({e.dependency_type.value}): {e.reasoning}"
            for e in internal_edges
        ) or "None"
        ctx_fmt = "\n".join(
            f"- {c['clause_id']}: risk={c['risk_score']:.2f}. {c['reasoning']}"
            for c in upstream_context
        ) or "No upstream context."

        if self._prompt_template:
            return (
                self._prompt_template
                .replace("{clauses_formatted}", clauses_fmt)
                .replace("{dependencies_formatted}", deps_fmt)
                .replace("{upstream_context_formatted}", ctx_fmt)
            )

        clause_ids_json = ", ".join(f'"{c.id}"' for c in clauses)

        if compact:
            return (
                "You are a legal risk assessor. Evaluate a GROUP of contract clauses "
                "with CIRCULAR dependencies.\n\n"
                f"## Interdependent Clauses\n{clauses_fmt}\n\n"
                f"## Internal Dependencies\n{deps_fmt}\n\n"
                f"## Context\n{ctx_fmt}\n\n"
                "## Task\n"
                "For each clause, output ONLY its risk score (0.0-1.0). "
                "Be concise. Consider how circular dependencies amplify risk.\n\n"
                "Output STRICTLY as JSON (no extra text):\n"
                '{"clause_evaluations": {'
                f'{clause_ids_json}: '
                '{"overall_risk_score": 0.0, "reasoning": "brief reason"}'
                "}}"
            )

        return (
            "You are a legal risk assessor. You need to evaluate a GROUP of contract "
            "clauses that have CIRCULAR dependencies - they reference and affect each other.\n\n"
            f"## Interdependent Clauses\n{clauses_fmt}\n\n"
            f"## Internal Dependencies\n{deps_fmt}\n\n"
            f"## Context: Upstream Evaluations (already assessed)\n{ctx_fmt}\n\n"
            "## Task\n"
            "These clauses form a cycle of mutual dependencies. Evaluate the risk of EACH clause, "
            "considering how they interact with and affect each other.\n\n"
            "For each clause, provide:\n"
            "1. overall_risk_score: float 0.0 to 1.0\n"
            "2. dimensions: financial_exposure, liability_scope, termination_risk, "
            "compliance_burden, ambiguity\n"
            "3. reasoning: how this clause's risk is affected by the other clauses\n\n"
            "Output as JSON:\n"
            '{"clause_evaluations": {'
            f'{clause_ids_json}: '
            '{"overall_risk_score": 0.0, '
            '"dimensions": [{"name": "...", "score": 0.0, "reasoning": "..."}], '
            '"reasoning": "..."}'
            '}, "interaction_summary": "..."}'
        )

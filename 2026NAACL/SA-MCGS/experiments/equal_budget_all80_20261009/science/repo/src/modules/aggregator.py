"""Module 8: 统计聚合

汇总 DAG 确定性结果 + 坍缩 SCC 结果 + MCGS rollout 结果，
输出每个条款的最终风险评估和整体合同风险报告。
"""
from __future__ import annotations

from statistics import mean, median, stdev
from typing import Any

from loguru import logger

from ..models.clause import ClauseEvaluation
from ..models.evaluation import ClauseFinalResult, ContractFinalResult
from ..models.graph import DependencyGraph


class Aggregator:
    def __init__(self, config: dict):
        agg_cfg = config.get("aggregation", {})
        self.high_risk_threshold = agg_cfg.get("high_risk_threshold", 0.7)
        self.high_uncertainty_threshold = agg_cfg.get("high_uncertainty_threshold", 0.15)

    def aggregate(
        self,
        rollout_results: list[dict[str, Any]],
        dag_results: dict[str, ClauseEvaluation],
        collapsed_scc_results: dict[str, ClauseEvaluation],
        graph: DependencyGraph,
    ) -> ContractFinalResult:
        clause_results: dict[str, ClauseFinalResult] = {}

        # 1. DAG 节点 —— 确定性结果
        for clause_id, ev in dag_results.items():
            if any(clause_id in scc.clause_ids for scc in graph.sccs):
                continue
            clause_results[clause_id] = ClauseFinalResult(
                clause_id=clause_id,
                mean_risk_score=ev.overall_risk_score,
                median_risk_score=ev.overall_risk_score,
                max_risk_score=ev.overall_risk_score,
                std_risk_score=0.0,
                confidence=1.0,
                num_samples=1,
                dimension_scores={d.name: d.score for d in ev.dimensions},
                source="dag_deterministic",
            )

        # 2. 坍缩 SCC 结果
        for clause_id, ev in collapsed_scc_results.items():
            scc_sample_count = self._find_scc_sample_count(clause_id, graph)
            clause_results[clause_id] = ClauseFinalResult(
                clause_id=clause_id,
                mean_risk_score=ev.overall_risk_score,
                median_risk_score=ev.overall_risk_score,
                max_risk_score=ev.overall_risk_score,
                std_risk_score=0.0,
                confidence=0.95,
                num_samples=scc_sample_count,
                dimension_scores={d.name: d.score for d in ev.dimensions},
                source="scc_collapsed",
            )

        # 3. MCGS rollout 中的 SCC 条款
        scc_clause_ids: set[str] = set()
        for scc in graph.sccs:
            if not scc.is_collapsed:
                scc_clause_ids.update(scc.clause_ids)

        for clause_id in scc_clause_ids:
            scores: list[float] = []
            dim_scores_all: dict[str, list[float]] = {}

            for rollout in rollout_results:
                ev = rollout["evaluations"].get(clause_id)
                if ev is None:
                    continue
                scores.append(ev.overall_risk_score)
                for dim in ev.dimensions:
                    dim_scores_all.setdefault(dim.name, []).append(dim.score)

            if not scores:
                # Fallback: use SCC sample data when no rollouts exist
                # (happens when all branches are pruned by dominance/influence)
                for scc in graph.sccs:
                    if clause_id in scc.clause_ids and scc.samples:
                        for sample in scc.samples:
                            ev = sample["evaluations"].get(clause_id)
                            if ev is not None:
                                scores.append(ev.overall_risk_score)
                                for dim in ev.dimensions:
                                    dim_scores_all.setdefault(dim.name, []).append(dim.score)
                        break

            if not scores:
                continue

            std = stdev(scores) if len(scores) > 1 else 0.0
            source = "scc_sampled" if rollout_results else "scc_sample_fallback"
            clause_results[clause_id] = ClauseFinalResult(
                clause_id=clause_id,
                mean_risk_score=mean(scores),
                median_risk_score=median(scores),
                max_risk_score=max(scores),
                std_risk_score=std,
                confidence=max(0.0, 1.0 - std),
                num_samples=len(scores),
                dimension_scores={
                    name: mean(vals) for name, vals in dim_scores_all.items()
                },
                source=source,
            )

        # 4. 整合
        all_scores = [r.mean_risk_score for r in clause_results.values()]
        overall = mean(all_scores) if all_scores else 0.0

        high_risk = sorted(
            cid for cid, r in clause_results.items()
            if r.max_risk_score >= self.high_risk_threshold
        )
        uncertain = sorted(
            cid for cid, r in clause_results.items()
            if r.std_risk_score >= self.high_uncertainty_threshold
        )

        result = ContractFinalResult(
            contract_id="contract",
            clause_results=clause_results,
            overall_risk_score=overall,
            high_risk_clauses=high_risk,
            uncertain_clauses=uncertain,
            scc_statistics=self._collect_scc_stats(graph),
            search_statistics=self._collect_search_stats(rollout_results),
        )

        logger.info(
            f"Aggregation: overall_risk={overall:.4f}, "
            f"high_risk={len(high_risk)}, uncertain={len(uncertain)}"
        )
        return result

    # ------------------------------------------------------------------
    @staticmethod
    def _find_scc_sample_count(clause_id: str, graph: DependencyGraph) -> int:
        for scc in graph.sccs:
            if clause_id in scc.clause_ids:
                return len(scc.samples)
        return 1

    @staticmethod
    def _collect_scc_stats(graph: DependencyGraph) -> dict[str, Any]:
        return {
            "num_sccs": len(graph.sccs),
            "scc_sizes": [s.size for s in graph.sccs],
            "collapsed_count": sum(1 for s in graph.sccs if s.is_collapsed),
            "dag_ratio": (
                len(graph.dag_nodes) / len(graph.clauses) if graph.clauses else 0
            ),
        }

    @staticmethod
    def _collect_search_stats(rollout_results: list[dict[str, Any]]) -> dict[str, Any]:
        if not rollout_results:
            return {"num_rollouts": 0, "avg_reward": 0, "max_reward": 0, "converged": False}

        rewards = [r["reward"] for r in rollout_results]
        return {
            "num_rollouts": len(rollout_results),
            "avg_reward": mean(rewards),
            "max_reward": max(rewards),
            "converged": _check_convergence(rewards),
        }


def _check_convergence(rewards: list[float], window: int = 10) -> bool:
    if len(rewards) < window * 2:
        return False
    early = mean(rewards[-window * 2 : -window])
    late = mean(rewards[-window:])
    return abs(late - early) < 0.01

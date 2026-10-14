"""Module 6a: 方差剪枝

对多次采样方差低于阈值的 SCC 进行「坍缩」—— 取采样均值作为固定评估值，
该 SCC 不再进入搜索树。

理论保证：低方差意味着 LLM 对该 SCC 的评估高度一致（收敛型环），
额外搜索不会带来信息增益。
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from ...models.clause import ClauseEvaluation, RiskDimension
from ...models.graph import DependencyGraph


class VariancePruner:
    def __init__(self, config: dict):
        pruning_cfg = config.get("pruning", {})
        self.variance_threshold = pruning_cfg.get("variance_threshold", 0.01)

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        stats = {"total_sccs": len(graph.sccs), "collapsed": 0, "remaining": 0}

        for scc in graph.sccs:
            if scc.variance <= self.variance_threshold:
                scc.is_collapsed = True
                scc.collapsed_value = self._compute_mean_evaluation(scc.samples)
                stats["collapsed"] += 1
                logger.debug(
                    f"Collapsed SCC {scc.id} (variance={scc.variance:.6f} "
                    f"<= {self.variance_threshold})"
                )
            else:
                stats["remaining"] += 1

        logger.info(
            f"Variance pruning: collapsed {stats['collapsed']}/{stats['total_sccs']} SCCs"
        )
        return stats

    @staticmethod
    def _compute_mean_evaluation(
        samples: list[dict[str, Any]],
    ) -> dict[str, ClauseEvaluation]:
        if not samples:
            return {}

        clause_ids = list(samples[0]["evaluations"].keys())
        mean_evals: dict[str, ClauseEvaluation] = {}

        for cid in clause_ids:
            scores = [s["evaluations"][cid].overall_risk_score for s in samples]
            mean_score = sum(scores) / len(scores)

            dim_sums: dict[str, list[float]] = {}
            for s in samples:
                for dim in s["evaluations"][cid].dimensions:
                    dim_sums.setdefault(dim.name, []).append(dim.score)

            dims = [
                RiskDimension(
                    name=name,
                    score=sum(vals) / len(vals),
                    reasoning="Averaged from multiple samples (variance pruning)",
                )
                for name, vals in dim_sums.items()
            ]

            mean_evals[cid] = ClauseEvaluation(
                clause_id=cid,
                overall_risk_score=mean_score,
                dimensions=dims,
                reasoning="Collapsed via variance pruning (low variance across samples)",
                context_used=[],
            )

        return mean_evals

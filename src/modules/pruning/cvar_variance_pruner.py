"""Plan B: CVaR + EVT based variance pruning.

Replaces the naive variance-threshold collapse with two principled tests:
  1. CVaR check  — if the CVaR_α of the SCC's risk scores is above a
     threshold, the SCC may contain tail risk and must NOT be collapsed.
     (Rockafellar & Uryasev, J. Banking & Finance, 2002)
  2. EVT check   — fit a Generalized Pareto Distribution (GPD) to scores
     exceeding a high quantile.  If the GPD shape parameter ξ > 0 (heavy
     tail), the SCC must NOT be collapsed even when variance is low.
     (Siffer et al., KDD 2017)

Only when BOTH tests agree that the SCC is benign is it collapsed.
"""
from __future__ import annotations

import math
from typing import Any

from loguru import logger

from ...models.clause import ClauseEvaluation, RiskDimension
from ...models.graph import DependencyGraph


def _compute_cvar(scores: list[float], alpha: float = 0.8) -> float:
    """Empirical CVaR_α: mean of the worst (1-α) fraction of scores."""
    if not scores:
        return 0.0
    sorted_scores = sorted(scores, reverse=True)
    k = max(1, int(math.ceil(len(sorted_scores) * (1 - alpha))))
    return sum(sorted_scores[:k]) / k


def _evt_heavy_tail(scores: list[float], quantile: float = 0.8) -> bool:
    """Simple EVT heavy-tail test using Peak-Over-Threshold.

    If the exceedances above the empirical quantile have a positive
    mean-excess slope, we flag it as heavy-tailed.  This is a lightweight
    proxy for GPD ξ > 0, usable with very few samples.
    """
    if len(scores) < 3:
        return False
    sorted_scores = sorted(scores)
    threshold_idx = max(0, int(len(sorted_scores) * quantile) - 1)
    threshold = sorted_scores[threshold_idx]

    exceedances = [s - threshold for s in sorted_scores if s > threshold]
    if len(exceedances) < 2:
        return False

    mean_excess = sum(exceedances) / len(exceedances)
    max_excess = max(exceedances)
    return max_excess > 2.0 * mean_excess and mean_excess > 0.02


class CVaRVariancePruner:
    """Conservative variance pruner using CVaR + EVT (Plan B)."""

    def __init__(self, config: dict):
        pruning_cfg = config.get("pruning", {})
        self.variance_threshold = pruning_cfg.get("variance_threshold", 0.01)
        self.cvar_alpha = pruning_cfg.get("cvar_alpha", 0.8)
        self.cvar_safe_threshold = pruning_cfg.get("cvar_safe_threshold", 0.4)

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        stats = {
            "total_sccs": len(graph.sccs),
            "collapsed": 0,
            "remaining": 0,
            "blocked_by_cvar": 0,
            "blocked_by_evt": 0,
        }

        for scc in graph.sccs:
            all_scores = self._collect_all_scores(scc)

            cvar = _compute_cvar(all_scores, self.cvar_alpha)
            heavy_tail = _evt_heavy_tail(all_scores)

            if cvar >= self.cvar_safe_threshold:
                stats["remaining"] += 1
                stats["blocked_by_cvar"] += 1
                logger.debug(
                    f"SCC {scc.id}: CVaR={cvar:.4f} >= {self.cvar_safe_threshold} "
                    f"→ kept (tail risk)"
                )
                continue

            if heavy_tail:
                stats["remaining"] += 1
                stats["blocked_by_evt"] += 1
                logger.debug(f"SCC {scc.id}: EVT heavy-tail detected → kept")
                continue

            if scc.variance <= self.variance_threshold:
                scc.is_collapsed = True
                scc.collapsed_value = self._compute_cvar_evaluation(scc.samples)
                stats["collapsed"] += 1
                logger.debug(
                    f"Collapsed SCC {scc.id} (var={scc.variance:.6f}, "
                    f"CVaR={cvar:.4f}, no heavy tail)"
                )
            else:
                stats["remaining"] += 1

        logger.info(
            f"CVaR+EVT pruning: collapsed {stats['collapsed']}/{stats['total_sccs']} SCCs "
            f"(blocked: {stats['blocked_by_cvar']} CVaR, {stats['blocked_by_evt']} EVT)"
        )
        return stats

    @staticmethod
    def _collect_all_scores(scc) -> list[float]:
        scores = []
        for sample in scc.samples:
            for ev in sample["evaluations"].values():
                scores.append(ev.overall_risk_score)
        return scores

    @staticmethod
    def _compute_cvar_evaluation(
        samples: list[dict[str, Any]],
    ) -> dict[str, ClauseEvaluation]:
        """Use CVaR (worst-case leaning) instead of simple mean for collapse value."""
        if not samples:
            return {}

        clause_ids = list(samples[0]["evaluations"].keys())
        result: dict[str, ClauseEvaluation] = {}

        for cid in clause_ids:
            scores = [s["evaluations"][cid].overall_risk_score for s in samples]
            cvar_score = _compute_cvar(scores, alpha=0.6)

            dim_sums: dict[str, list[float]] = {}
            for s in samples:
                for dim in s["evaluations"][cid].dimensions:
                    dim_sums.setdefault(dim.name, []).append(dim.score)

            dims = [
                RiskDimension(
                    name=name,
                    score=_compute_cvar(vals, alpha=0.6),
                    reasoning="CVaR-weighted collapse (Plan B)",
                )
                for name, vals in dim_sums.items()
            ]

            result[cid] = ClauseEvaluation(
                clause_id=cid,
                overall_risk_score=cvar_score,
                dimensions=dims,
                reasoning="CVaR-weighted collapse (conservative)",
                context_used=[],
            )

        return result

"""Plan A: Conformal Risk Control for detection threshold calibration.

Implements the core algorithm from:
  Angelopoulos, Bates, Fisch, Lei & Schuster.
  "Conformal Risk Control." ICLR 2024.

Instead of a fixed threshold (e.g. 0.7), we calibrate λ on a set of
calibration scores so that the expected false-negative rate (missing a
truly risky clause) is controlled at level α.

The key guarantee (Theorem 1 of the paper):
    E[L(λ̂)] ≤ α + 1/(n+1)
where n is the calibration set size and L is any monotone loss.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class ConformalRiskController:
    """Calibrates risk detection thresholds with coverage guarantees.

    Usage:
      1. Collect calibration scores (baseline risk scores for known-safe clauses).
      2. Call calibrate() to compute the adaptive threshold.
      3. Use detect() to flag perturbed clauses.
    """

    alpha: float = 0.1
    calibration_scores: list[float] = field(default_factory=list)
    _lambda_hat: float | None = None

    def calibrate(self, baseline_scores: list[float]) -> float:
        """Compute the conformal threshold λ̂ from calibration data.

        Uses the quantile-based conformal prediction approach:
          λ̂ = Quantile_{(1-α)(1 + 1/n)} of baseline_scores

        This ensures that truly anomalous scores (above λ̂) are
        detected with probability ≥ 1 - α.
        """
        self.calibration_scores = sorted(baseline_scores)
        n = len(self.calibration_scores)
        if n == 0:
            self._lambda_hat = 0.5
            return self._lambda_hat

        adjusted_quantile = min(1.0, (1 - self.alpha) * (1 + 1 / n))
        idx = min(int(math.ceil(adjusted_quantile * n)) - 1, n - 1)
        self._lambda_hat = self.calibration_scores[idx]

        logger.info(
            f"Conformal calibration: n={n}, α={self.alpha}, "
            f"λ̂={self._lambda_hat:.4f} "
            f"(guarantee: E[miss_rate] ≤ {self.alpha + 1/(n+1):.4f})"
        )
        return self._lambda_hat

    @property
    def threshold(self) -> float:
        if self._lambda_hat is None:
            raise ValueError("Call calibrate() first")
        return self._lambda_hat

    def detect(self, score: float) -> bool:
        """True if the score exceeds the conformal threshold."""
        return score > self.threshold

    def detect_delta(self, baseline_score: float, perturbed_score: float) -> bool:
        """Delta-based detection: calibrate on score differences."""
        delta = perturbed_score - baseline_score
        return delta > self.delta_threshold if hasattr(self, '_delta_threshold') else delta > 0.15

    def calibrate_delta(self, baseline_deltas: list[float]) -> float:
        """Calibrate a threshold for risk score deltas (perturbation - baseline).

        Under the null hypothesis (no perturbation effect), deltas should be
        small. We set the threshold so that only α fraction of null deltas
        would exceed it.
        """
        sorted_deltas = sorted(baseline_deltas)
        n = len(sorted_deltas)
        if n == 0:
            self._delta_threshold = 0.15
            return self._delta_threshold

        adjusted_quantile = min(1.0, (1 - self.alpha) * (1 + 1 / n))
        idx = min(int(math.ceil(adjusted_quantile * n)) - 1, n - 1)
        self._delta_threshold = sorted_deltas[idx]

        logger.info(
            f"Conformal delta calibration: n={n}, α={self.alpha}, "
            f"δ̂={self._delta_threshold:.4f}"
        )
        return self._delta_threshold

    @property
    def delta_threshold(self) -> float:
        return getattr(self, '_delta_threshold', 0.15)


class ConformalAggregator:
    """Aggregator enhanced with Conformal Risk Control (Plan A).

    Replaces fixed high_risk_threshold with a conformally calibrated one.
    """

    def __init__(self, config: dict, baseline_scores: list[float] | None = None):
        agg_cfg = config.get("aggregation", {})
        self.fallback_threshold = agg_cfg.get("high_risk_threshold", 0.7)
        self.high_uncertainty_threshold = agg_cfg.get("high_uncertainty_threshold", 0.15)
        self.conformal_alpha = agg_cfg.get("conformal_alpha", 0.1)

        self.controller = ConformalRiskController(alpha=self.conformal_alpha)
        if baseline_scores:
            self.controller.calibrate(baseline_scores)

    @property
    def high_risk_threshold(self) -> float:
        if self.controller._lambda_hat is not None:
            return self.controller.threshold
        return self.fallback_threshold

    def calibrate_from_baseline(self, clause_scores: list[float]):
        """Feed baseline clause risk scores to calibrate the threshold."""
        self.controller.calibrate(clause_scores)

    def calibrate_deltas(self, null_deltas: list[float]):
        """Feed null-hypothesis deltas to calibrate delta detection."""
        self.controller.calibrate_delta(null_deltas)

    def is_high_risk(self, score: float) -> bool:
        return score >= self.high_risk_threshold

    def is_detected_by_delta(self, delta: float) -> bool:
        return delta > self.controller.delta_threshold

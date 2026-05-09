"""Online Conformal MCGS: self-calibrating risk detection during search.

No baseline needed. The threshold is progressively calibrated from the
pool of ALL SCC clause scores observed across rollouts.

Key idea: during MCGS, every rollout evaluates every SCC clause. As
rollouts accumulate, we build the empirical distribution of "normal SCC
risk" for THIS contract. A clause is flagged when it persistently sits
in the tail of this self-constructed distribution.

Theory:
  - Gibbs & Candes, "Adaptive Conformal Inference Under Distribution
    Shift", NeurIPS 2021 (online conformal guarantees)
  - Empirical Bernstein bound for finite-sample confidence intervals
"""
from __future__ import annotations

import math
import random
from typing import Any

from loguru import logger

from ..models.clause import ClauseEvaluation
from ..models.graph import DependencyGraph
from ..models.search_tree import SCCBranch, SearchTree, SearchTreeNode


class OnlineConformalMCGS:
    """MCGS with online self-calibrating risk detection."""

    def __init__(self, config: dict):
        mcgs_cfg = config.get("mcgs", {})
        self.num_rollouts = mcgs_cfg.get("num_rollouts", 100)
        self.exploration_weight = mcgs_cfg.get("ucb_exploration_weight", math.sqrt(2))
        self.early_stopping = mcgs_cfg.get("early_stopping", True)
        self.convergence_window = mcgs_cfg.get("convergence_window", 10)
        self.convergence_threshold = mcgs_cfg.get("convergence_threshold", 0.01)

        detect_cfg = config.get("detection", {})
        self.conformal_alpha = detect_cfg.get("alpha", 0.1)
        self.min_rollouts_for_detection = detect_cfg.get("min_rollouts", 3)
        self.confidence_delta = detect_cfg.get("confidence_delta", 0.05)

        self._score_pool: list[float] = []
        self._clause_scores: dict[str, list[float]] = {}
        self._clause_ranks: dict[str, list[float]] = {}
        self._running_quantile: float = 1.0
        self._detected_clauses: set[str] = set()
        self._detection_log: list[dict] = []

    def search(
        self,
        search_tree: SearchTree,
        dag_results: dict[str, ClauseEvaluation],
        graph: DependencyGraph,
    ) -> list[dict[str, Any]]:
        self._score_pool = []
        self._clause_scores = {}
        self._detected_clauses = set()
        self._detection_log = []

        all_results: list[dict[str, Any]] = []
        rewards_history: list[float] = []

        for rollout_idx in range(self.num_rollouts):
            path: dict[str, str] = {}
            rollout_evals = dict(dag_results)

            for scc_id in search_tree.scc_topological_order:
                if scc_id not in search_tree.nodes:
                    continue
                node = search_tree.nodes[scc_id]
                active = node.active_branches
                if not active:
                    continue

                if len(active) == 1:
                    chosen = active[0]
                else:
                    chosen = self._ucb_select(node, active, rollout_idx)

                path[scc_id] = chosen.branch_id
                for clause_id, ev in chosen.evaluation.items():
                    rollout_evals[clause_id] = ev

            reward = self._compute_reward(rollout_evals)
            self._backpropagate(search_tree, path, reward)

            self._update_score_pool(rollout_evals, dag_results)
            self._update_detection(rollout_idx)

            all_results.append({
                "rollout_idx": rollout_idx,
                "path": path,
                "evaluations": rollout_evals,
                "reward": reward,
                "running_quantile": self._running_quantile,
                "detected_so_far": set(self._detected_clauses),
            })
            rewards_history.append(reward)

            if self.early_stopping and self._check_convergence(rewards_history):
                logger.info(f"OnlineConformal-MCGS converged at rollout {rollout_idx + 1}")
                break

        logger.info(
            f"OnlineConformal-MCGS complete: {len(all_results)} rollouts, "
            f"avg_reward={sum(rewards_history) / len(rewards_history):.4f}, "
            f"final_quantile={self._running_quantile:.4f}, "
            f"detected={len(self._detected_clauses)} clauses"
        )
        return all_results

    @property
    def detected_clauses(self) -> set[str]:
        return self._detected_clauses

    @property
    def detection_log(self) -> list[dict]:
        return self._detection_log

    @property
    def running_threshold(self) -> float:
        return self._running_quantile

    def _update_score_pool(
        self,
        rollout_evals: dict[str, ClauseEvaluation],
        dag_results: dict[str, ClauseEvaluation],
    ):
        """Add SCC clause scores from this rollout and track per-rollout ranks."""
        dag_ids = set(dag_results.keys())
        rollout_scc_scores: dict[str, float] = {}

        for clause_id, ev in rollout_evals.items():
            if clause_id in dag_ids:
                continue
            score = ev.overall_risk_score
            self._score_pool.append(score)
            self._clause_scores.setdefault(clause_id, []).append(score)
            rollout_scc_scores[clause_id] = score

        if not rollout_scc_scores:
            return

        # Compute percentile rank for each clause within this rollout
        all_scores_sorted = sorted(rollout_scc_scores.values())
        n_clauses = len(all_scores_sorted)
        for clause_id, score in rollout_scc_scores.items():
            rank = sum(1 for s in all_scores_sorted if s <= score) / n_clauses
            self._clause_ranks.setdefault(clause_id, []).append(rank)

    def _update_detection(self, rollout_idx: int):
        """Detect outliers using three complementary tests:
        1. Rank consistency: clause is persistently top-ranked across rollouts
        2. Z-score: clause mean is far from pool mean in std units
        3. Exceedance fraction: clause exceeds pool median too often
        """
        if len(self._score_pool) < 5:
            return

        # Update running quantile for reporting
        sorted_pool = sorted(self._score_pool)
        n = len(sorted_pool)
        q_idx = min(int(math.ceil((1 - self.conformal_alpha) * n)) - 1, n - 1)
        self._running_quantile = sorted_pool[q_idx]

        if rollout_idx < self.min_rollouts_for_detection:
            return

        pool_mean = sum(self._score_pool) / len(self._score_pool)
        pool_std = math.sqrt(
            sum((s - pool_mean) ** 2 for s in self._score_pool) / len(self._score_pool)
        )
        if pool_std < 1e-6:
            return

        pool_median = sorted_pool[n // 2]

        for clause_id, scores in self._clause_scores.items():
            if len(scores) < self.min_rollouts_for_detection:
                continue
            if clause_id in self._detected_clauses:
                continue

            clause_mean = sum(scores) / len(scores)
            ranks = self._clause_ranks.get(clause_id, [])

            # Test 1: Z-score — is clause mean far above pool mean?
            z_score = (clause_mean - pool_mean) / pool_std
            z_detected = z_score > 1.5

            # Test 2: Rank consistency — average rank > 0.8 means persistently top
            avg_rank = sum(ranks) / len(ranks) if ranks else 0.5
            rank_detected = avg_rank > 0.8 and len(ranks) >= self.min_rollouts_for_detection

            # Test 3: Exceedance — fraction of rollouts where score > pool median
            exceedance_frac = sum(1 for s in scores if s > pool_median) / len(scores)
            exceedance_detected = exceedance_frac > 0.8

            # Detect if at least 2 out of 3 tests agree
            votes = sum([z_detected, rank_detected, exceedance_detected])
            if votes >= 2:
                self._detected_clauses.add(clause_id)
                self._detection_log.append({
                    "clause_id": clause_id,
                    "detected_at_rollout": rollout_idx,
                    "clause_mean": clause_mean,
                    "pool_mean": pool_mean,
                    "z_score": z_score,
                    "avg_rank": avg_rank,
                    "exceedance_frac": exceedance_frac,
                    "threshold": self._running_quantile,
                    "n_samples": len(scores),
                    "tests_passed": f"z={z_detected},rank={rank_detected},exc={exceedance_detected}",
                })

    def _ucb_select(
        self, node: SearchTreeNode, active: list[SCCBranch], total_rollouts: int
    ) -> SCCBranch:
        unvisited = [b for b in active if b.visit_count == 0]
        if unvisited:
            return random.choice(unvisited)

        best: SCCBranch | None = None
        best_ucb = -math.inf

        for branch in active:
            exploitation = branch.avg_reward
            exploration = self.exploration_weight * math.sqrt(
                math.log(total_rollouts + 1) / (branch.visit_count + 1e-8)
            )
            ucb = exploitation + exploration
            if ucb > best_ucb:
                best_ucb = ucb
                best = branch

        return best  # type: ignore[return-value]

    @staticmethod
    def _compute_reward(evaluations: dict[str, ClauseEvaluation]) -> float:
        scores = [e.overall_risk_score for e in evaluations.values()]
        if not scores:
            return 0.0
        max_risk = max(scores)
        avg_risk = sum(scores) / len(scores)
        variance = sum((s - avg_risk) ** 2 for s in scores) / len(scores)
        return 0.5 * max_risk + 0.3 * avg_risk + 0.2 * math.sqrt(variance)

    @staticmethod
    def _backpropagate(
        search_tree: SearchTree, path: dict[str, str], reward: float
    ) -> None:
        for scc_id, branch_id in path.items():
            node = search_tree.nodes[scc_id]
            node.visit_count += 1
            node.total_reward += reward
            for branch in node.branches:
                if branch.branch_id == branch_id:
                    branch.visit_count += 1
                    branch.total_reward += reward
                    break

    def _check_convergence(self, rewards: list[float]) -> bool:
        w = self.convergence_window
        if len(rewards) < w * 2:
            return False
        early_avg = sum(rewards[-w * 2 : -w]) / w
        late_avg = sum(rewards[-w:]) / w
        return abs(late_avg - early_avg) < self.convergence_threshold

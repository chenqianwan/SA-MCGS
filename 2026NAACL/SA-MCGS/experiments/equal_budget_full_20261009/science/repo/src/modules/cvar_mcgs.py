"""Plan B: Risk-sensitive MCGS with CVaR-aware UCB and reward.

Key changes from vanilla MCGS:
  1. Reward uses CVaR instead of mean — focuses on worst-case tail.
     (Rockafellar & Uryasev, J. Banking & Finance, 2002)
  2. UCB selection adds a risk penalty term weighted by a Lagrange
     multiplier λ that auto-adapts via online gradient ascent.
     (Ni et al., ICML 2024 — "Risk-Sensitive Reward-Free RL with CVaR")
"""
from __future__ import annotations

import math
import random
from typing import Any

from loguru import logger

from ..models.clause import ClauseEvaluation
from ..models.graph import DependencyGraph
from ..models.search_tree import SCCBranch, SearchTree, SearchTreeNode


def _empirical_cvar(scores: list[float], alpha: float = 0.8) -> float:
    """CVaR_α: mean of the top (1-α) fraction of risk scores."""
    if not scores:
        return 0.0
    sorted_desc = sorted(scores, reverse=True)
    k = max(1, int(math.ceil(len(sorted_desc) * (1 - alpha))))
    return sum(sorted_desc[:k]) / k


class CVaRMCGS:
    """Risk-sensitive Monte Carlo Graph Search using CVaR."""

    def __init__(self, config: dict):
        mcgs_cfg = config.get("mcgs", {})
        self.num_rollouts = mcgs_cfg.get("num_rollouts", 100)
        self.exploration_weight = mcgs_cfg.get("ucb_exploration_weight", math.sqrt(2))
        self.early_stopping = mcgs_cfg.get("early_stopping", True)
        self.convergence_window = mcgs_cfg.get("convergence_window", 10)
        self.convergence_threshold = mcgs_cfg.get("convergence_threshold", 0.01)

        self.cvar_alpha = mcgs_cfg.get("cvar_alpha", 0.8)
        self.risk_lambda = mcgs_cfg.get("risk_lambda", 0.3)
        self.lambda_lr = mcgs_cfg.get("lambda_lr", 0.05)
        self.risk_budget = mcgs_cfg.get("risk_budget", 0.5)

        self._branch_risk_history: dict[str, list[float]] = {}

    def search(
        self,
        search_tree: SearchTree,
        dag_results: dict[str, ClauseEvaluation],
        graph: DependencyGraph,
    ) -> list[dict[str, Any]]:
        all_results: list[dict[str, Any]] = []
        rewards_history: list[float] = []
        current_lambda = self.risk_lambda

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
                    chosen = self._cvar_ucb_select(
                        node, active, rollout_idx, current_lambda
                    )

                path[scc_id] = chosen.branch_id
                for clause_id, ev in chosen.evaluation.items():
                    rollout_evals[clause_id] = ev

            reward = self._compute_cvar_reward(rollout_evals)
            risk_cost = self._compute_risk_cost(rollout_evals)
            self._backpropagate(search_tree, path, reward)

            current_lambda = max(
                0.0,
                current_lambda + self.lambda_lr * (risk_cost - self.risk_budget),
            )

            all_results.append({
                "rollout_idx": rollout_idx,
                "path": path,
                "evaluations": rollout_evals,
                "reward": reward,
                "risk_cost": risk_cost,
                "lambda": current_lambda,
            })
            rewards_history.append(reward)

            if self.early_stopping and self._check_convergence(rewards_history):
                logger.info(f"CVaR-MCGS converged at rollout {rollout_idx + 1}")
                break

        logger.info(
            f"CVaR-MCGS complete: {len(all_results)} rollouts, "
            f"avg_reward={sum(rewards_history) / len(rewards_history):.4f}, "
            f"final_λ={current_lambda:.4f}"
        )
        return all_results

    def _cvar_ucb_select(
        self,
        node: SearchTreeNode,
        active: list[SCCBranch],
        total_rollouts: int,
        current_lambda: float,
    ) -> SCCBranch:
        unvisited = [b for b in active if b.visit_count == 0]
        if unvisited:
            return random.choice(unvisited)

        best: SCCBranch | None = None
        best_score = -math.inf

        for branch in active:
            exploitation = branch.avg_reward
            exploration = self.exploration_weight * math.sqrt(
                math.log(total_rollouts + 1) / (branch.visit_count + 1e-8)
            )

            branch_scores = [
                e.overall_risk_score for e in branch.evaluation.values()
            ]
            branch_cvar = _empirical_cvar(branch_scores, self.cvar_alpha)

            score = exploitation + exploration - current_lambda * branch_cvar

            if score > best_score:
                best_score = score
                best = branch

        return best  # type: ignore[return-value]

    def _compute_cvar_reward(
        self, evaluations: dict[str, ClauseEvaluation]
    ) -> float:
        """CVaR-weighted reward: emphasizes tail risk discovery."""
        scores = [e.overall_risk_score for e in evaluations.values()]
        if not scores:
            return 0.0

        cvar = _empirical_cvar(scores, self.cvar_alpha)
        max_risk = max(scores)
        avg_risk = sum(scores) / len(scores)

        return 0.5 * cvar + 0.3 * max_risk + 0.2 * avg_risk

    @staticmethod
    def _compute_risk_cost(
        evaluations: dict[str, ClauseEvaluation],
    ) -> float:
        scores = [e.overall_risk_score for e in evaluations.values()]
        if not scores:
            return 0.0
        return _empirical_cvar(scores, alpha=0.9)

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

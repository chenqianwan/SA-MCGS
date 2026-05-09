"""Module 7: Monte Carlo Graph Search (MCGS)

搜索树上每个节点是一个 SCC，每个 SCC 有若干活跃分支。
一次 rollout = 按拓扑序遍历所有 SCC，每个 SCC 用 UCB1 选一个分支。
rollout 结束后计算 reward 并反向传播更新统计量。
"""
from __future__ import annotations

import math
import random
from typing import Any

from loguru import logger

from ..models.clause import ClauseEvaluation
from ..models.graph import DependencyGraph
from ..models.search_tree import SCCBranch, SearchTree, SearchTreeNode


class MCGS:
    def __init__(self, config: dict):
        mcgs_cfg = config.get("mcgs", {})
        self.num_rollouts = mcgs_cfg.get("num_rollouts", 100)
        self.exploration_weight = mcgs_cfg.get("ucb_exploration_weight", math.sqrt(2))
        self.early_stopping = mcgs_cfg.get("early_stopping", True)
        self.convergence_window = mcgs_cfg.get("convergence_window", 10)
        self.convergence_threshold = mcgs_cfg.get("convergence_threshold", 0.01)

    def search(
        self,
        search_tree: SearchTree,
        dag_results: dict[str, ClauseEvaluation],
        graph: DependencyGraph,
    ) -> list[dict[str, Any]]:
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

            all_results.append({
                "rollout_idx": rollout_idx,
                "path": path,
                "evaluations": rollout_evals,
                "reward": reward,
            })
            rewards_history.append(reward)

            if self.early_stopping and self._check_convergence(rewards_history):
                logger.info(f"MCGS converged at rollout {rollout_idx + 1}")
                break

        logger.info(
            f"MCGS complete: {len(all_results)} rollouts, "
            f"avg_reward={sum(rewards_history) / len(rewards_history):.4f}"
        )
        return all_results

    # ------------------------------------------------------------------
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
        """
        Reward 设计：
        - 0.5 * max_risk  （鼓励发现极端风险）
        - 0.3 * avg_risk  （整体风险水平）
        - 0.2 * sqrt(var) （差异化风险分布的信息量）
        """
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

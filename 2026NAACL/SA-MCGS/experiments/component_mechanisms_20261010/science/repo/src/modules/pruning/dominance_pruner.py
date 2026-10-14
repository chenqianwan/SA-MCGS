"""Module 6b: 支配剪枝

分支 A 支配分支 B ⟺ A 在所有条款的所有风险维度上评分 >= B。
选 A 永远能发现至少和 B 一样多的风险，B 是冗余的。

理论保证（无损）：最终聚合关注 max risk。如果 B 被 A 支配，
则任何包含 B 的路径的 max risk <= 包含 A 的对应路径，
删除 B 不影响最坏情况风险的发现。
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from ...models.clause import ClauseEvaluation
from ...models.search_tree import SCCBranch, SearchTree


_DEFAULT_DIMENSIONS = [
    "financial_exposure",
    "liability_scope",
    "termination_risk",
    "compliance_burden",
    "ambiguity",
]


class DominancePruner:
    def __init__(self, config: dict):
        pruning_cfg = config.get("pruning", {})
        self.dimensions: list[str] = pruning_cfg.get("risk_dimensions", _DEFAULT_DIMENSIONS)

    def prune(self, search_tree: SearchTree) -> dict[str, Any]:
        stats = {"total_branches": 0, "pruned_branches": 0}

        for scc_id, node in search_tree.nodes.items():
            active = node.active_branches
            stats["total_branches"] += len(active)

            for i, branch_a in enumerate(active):
                if branch_a.is_pruned:
                    continue
                for j, branch_b in enumerate(active):
                    if i == j or branch_b.is_pruned:
                        continue
                    if self._dominates(branch_a, branch_b):
                        branch_b.is_pruned = True
                        branch_b.pruned_by = "dominance"
                        stats["pruned_branches"] += 1

        logger.info(
            f"Dominance pruning: pruned {stats['pruned_branches']}/{stats['total_branches']} branches"
        )
        return stats

    def _dominates(self, branch_a: SCCBranch, branch_b: SCCBranch) -> bool:
        """A 严格支配 B: A 在每个条款上 >= B，且至少一个条款上严格 > B。

        当 dimensions 为空（compact prompt 模式）时，退化为比较 overall_risk_score。
        """
        has_strict = False
        for clause_id in branch_a.evaluation:
            eval_a = branch_a.evaluation[clause_id]
            eval_b = branch_b.evaluation.get(clause_id)
            if eval_b is None:
                continue

            if eval_a.dimensions and eval_b.dimensions:
                for dim_name in self.dimensions:
                    score_a = _get_dim_score(eval_a, dim_name)
                    score_b = _get_dim_score(eval_b, dim_name)
                    if score_a < score_b:
                        return False
                    if score_a > score_b:
                        has_strict = True
            else:
                if eval_a.overall_risk_score < eval_b.overall_risk_score:
                    return False
                if eval_a.overall_risk_score > eval_b.overall_risk_score:
                    has_strict = True

        return has_strict


def _get_dim_score(evaluation: ClauseEvaluation, dim_name: str) -> float:
    for dim in evaluation.dimensions:
        if dim.name == dim_name:
            return dim.score
    return 0.0

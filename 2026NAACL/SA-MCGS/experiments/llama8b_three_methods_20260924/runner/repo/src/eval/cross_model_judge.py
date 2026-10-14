"""Cross-Model Judge — 使用不同 LLM 作为独立评判者.

将 SA-MCGS 的评估结果提交给一个不同的 LLM，
让它独立判断风险评分的合理性，计算一致率。
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from ..llm.base import BaseLLMClient
from ..models.evaluation import ContractFinalResult
from ..models.graph import DependencyGraph


class CrossModelJudge:
    """用不同 LLM 对 SA-MCGS 结果进行独立验证。"""

    def __init__(self, judge_client: BaseLLMClient, config: dict):
        self.judge = judge_client
        eval_cfg = config.get("evaluation", {})
        self.agreement_tolerance = eval_cfg.get("judge_agreement_tolerance", 0.15)

    async def evaluate(
        self,
        result: ContractFinalResult,
        graph: DependencyGraph,
    ) -> dict[str, Any]:
        agreements = 0
        total = 0
        per_clause: dict[str, dict] = {}

        for cid, cr in result.clause_results.items():
            clause = graph.clauses.get(cid)
            if not clause:
                continue

            judge_score = await self._get_judge_score(clause.title, clause.content)
            diff = abs(judge_score - cr.mean_risk_score)
            agreed = diff <= self.agreement_tolerance
            if agreed:
                agreements += 1
            total += 1

            per_clause[cid] = {
                "sa_mcgs_score": round(cr.mean_risk_score, 4),
                "judge_score": round(judge_score, 4),
                "diff": round(diff, 4),
                "agreed": agreed,
            }

        agreement_rate = agreements / total if total > 0 else 0.0
        metrics = {
            "agreement_rate": round(agreement_rate, 4),
            "tolerance": self.agreement_tolerance,
            "total_clauses": total,
            "agreed": agreements,
            "per_clause": per_clause,
        }

        logger.info(f"Cross-model judge: agreement={agreement_rate:.1%} ({agreements}/{total})")
        return metrics

    async def _get_judge_score(self, title: str, content: str) -> float:
        prompt = (
            "You are an independent legal risk assessor. "
            "Rate the risk of this contract clause from 0.0 (no risk) to 1.0 (extreme risk).\n\n"
            f"Clause: {title}\n{content[:800]}\n\n"
            'Output JSON: {"risk_score": 0.0}'
        )
        try:
            data = await self.judge.call_json(prompt, temperature=0.0)
            return float(data.get("risk_score", 0.5))
        except Exception:
            return 0.5

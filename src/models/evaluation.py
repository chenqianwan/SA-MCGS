from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ClauseFinalResult(BaseModel):
    """最终输出：单条款风险评估"""

    clause_id: str
    mean_risk_score: float = Field(ge=0.0, le=1.0)
    median_risk_score: float = Field(ge=0.0, le=1.0)
    max_risk_score: float = Field(ge=0.0, le=1.0)
    std_risk_score: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)
    num_samples: int = 1
    dimension_scores: dict[str, float] = {}
    source: str = "dag_deterministic"


class ContractFinalResult(BaseModel):
    """最终输出：整份合同的风险评估"""

    contract_id: str
    clause_results: dict[str, ClauseFinalResult] = {}
    overall_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    high_risk_clauses: list[str] = []
    uncertain_clauses: list[str] = []
    scc_statistics: dict[str, Any] = {}
    search_statistics: dict[str, Any] = {}

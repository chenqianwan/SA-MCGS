from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ClauseType(str, Enum):
    """条款功能类型 — 用于层级先验 (Def→Obl→Cond→Rem→Lim)"""

    DEFINITION = "definition"
    OBLIGATION = "obligation"
    CONDITION = "condition"
    REMEDY = "remedy"
    LIMITATION = "limitation"
    OTHER = "other"


CLAUSE_TYPE_HIERARCHY = [
    ClauseType.DEFINITION,
    ClauseType.OBLIGATION,
    ClauseType.CONDITION,
    ClauseType.REMEDY,
    ClauseType.LIMITATION,
]


class RiskDimension(BaseModel):
    """单个风险维度的评分"""

    name: str
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class ClauseEvaluation(BaseModel):
    """单次 LLM 对一个条款的评估结果"""

    clause_id: str
    overall_risk_score: float = Field(ge=0.0, le=1.0)
    dimensions: list[RiskDimension] = []
    reasoning: str = ""
    context_used: list[str] = []


class Clause(BaseModel):
    """一个合同条款"""

    id: str
    title: str
    content: str
    section: Optional[str] = None
    clause_type: ClauseType = ClauseType.OTHER
    metadata: dict = {}

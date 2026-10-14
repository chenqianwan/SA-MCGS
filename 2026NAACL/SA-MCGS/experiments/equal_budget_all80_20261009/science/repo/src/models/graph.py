from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .clause import Clause, ClauseEvaluation


class DependencyType(str, Enum):
    """条款间的依赖类型"""

    DEFINES = "defines"
    CONSTRAINS = "constrains"
    TRIGGERS = "triggers"
    MODIFIES = "modifies"
    REFERENCES = "references"


class Edge(BaseModel):
    """有向边：source → target 表示 target 依赖 source"""

    source: str
    target: str
    dependency_type: DependencyType = DependencyType.REFERENCES
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: str = ""


class SCCInfo(BaseModel):
    """一个强连通分量的信息"""

    id: str
    clause_ids: list[str]
    internal_edges: list[Edge] = []
    size: int = 0

    samples: list[dict[str, Any]] = []
    variance: float = 0.0
    is_collapsed: bool = False
    collapsed_value: Optional[dict[str, ClauseEvaluation]] = None

    def model_post_init(self, __context: Any) -> None:
        if self.size == 0:
            self.size = len(self.clause_ids)


class DependencyGraph(BaseModel):
    """完整的依赖图"""

    clauses: dict[str, Clause] = {}
    edges: list[Edge] = []
    sccs: list[SCCInfo] = []
    dag_nodes: list[str] = []
    topological_order: list[dict[str, str]] = []
    metadata: dict[str, Any] = {}

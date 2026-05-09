from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from .clause import ClauseEvaluation


class SCCBranch(BaseModel):
    """SCC 的一个分支（一次 LLM 采样结果）"""

    branch_id: str
    scc_id: str
    evaluation: dict[str, ClauseEvaluation] = {}
    is_pruned: bool = False
    pruned_by: Optional[str] = None

    # MCGS 运行时统计（不参与序列化比较）
    visit_count: int = 0
    total_reward: float = 0.0

    @property
    def avg_reward(self) -> float:
        return self.total_reward / self.visit_count if self.visit_count > 0 else 0.0


class SearchTreeNode(BaseModel):
    """搜索树节点，对应一个 SCC 的决策点"""

    scc_id: str
    branches: list[SCCBranch] = []
    depth: int = 0

    visit_count: int = 0
    total_reward: float = 0.0

    @property
    def active_branches(self) -> list[SCCBranch]:
        return [b for b in self.branches if not b.is_pruned]


class SearchTreeEdge(BaseModel):
    """搜索树边：选择了某个分支"""

    parent_scc_id: str
    child_scc_id: str
    chosen_branch_id: str
    visit_count: int = 0
    total_reward: float = 0.0

    @property
    def avg_reward(self) -> float:
        return self.total_reward / self.visit_count if self.visit_count > 0 else 0.0


class SearchTree(BaseModel):
    """完整的搜索树"""

    nodes: dict[str, SearchTreeNode] = {}
    edges: list[SearchTreeEdge] = []
    root_scc_ids: list[str] = []
    scc_topological_order: list[str] = []


# ── AlphaGo-style MCGS data structures ─────────────────────────────


class NodeStats(BaseModel):
    """Per-clause statistics accumulated during AlphaGo-style search."""

    clause_id: str
    visit_count: int = 0
    total_risk: float = 0.0
    risk_history: list[float] = []
    conflict_count: int = 0
    virtual_loss: int = 0

    @property
    def avg_risk(self) -> float:
        return self.total_risk / self.visit_count if self.visit_count else 0.0


class EdgeStats(BaseModel):
    """Per-edge statistics for UCB-guided window expansion."""

    source: str
    target: str
    visit_count: int = 0
    total_conflict: float = 0.0
    virtual_loss: int = 0

    @property
    def avg_conflict(self) -> float:
        return self.total_conflict / self.visit_count if self.visit_count else 0.0


class TranspositionEntry(BaseModel):
    """Cached LLM evaluation for a specific clause window."""

    clause_ids: list[str]
    clause_evaluations: dict[str, float] = {}
    clause_reasonings: dict[str, str] = {}
    conflicts: list[dict[str, Any]] = []
    timestamp: int = 0

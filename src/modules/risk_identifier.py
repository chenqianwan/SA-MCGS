"""SCC-based Risk Identification (workflow Step 6)

基于 SCC 结构进行风险模式提取、条款级风险定位与解释生成。
在聚合评分之后运行，对 ContractFinalResult 做风险增强。
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from ..models.clause import Clause
from ..models.evaluation import ClauseFinalResult, ContractFinalResult
from ..models.graph import DependencyGraph, SCCInfo


class RiskPattern:
    """一种 SCC 风险模式"""

    def __init__(self, pattern_type: str, scc_id: str, clause_ids: list[str],
                 severity: float, description: str):
        self.pattern_type = pattern_type
        self.scc_id = scc_id
        self.clause_ids = clause_ids
        self.severity = severity
        self.description = description

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_type": self.pattern_type,
            "scc_id": self.scc_id,
            "clause_ids": self.clause_ids,
            "severity": round(self.severity, 4),
            "description": self.description,
        }


class RiskIdentifier:
    """SCC-based 风险识别器"""

    def __init__(self, config: dict):
        agg_cfg = config.get("aggregation", {})
        self.high_risk_threshold = agg_cfg.get("high_risk_threshold", 0.7)

    def identify(
        self,
        result: ContractFinalResult,
        graph: DependencyGraph,
    ) -> ContractFinalResult:
        patterns = []

        # 1. Circular dependency risk
        for scc in graph.sccs:
            patterns.extend(self._analyze_scc_risk(scc, result, graph))

        # 2. Cross-SCC amplification
        patterns.extend(self._detect_cross_scc_amplification(graph, result))

        # 3. Generate localization and explanations
        risk_explanations = self._generate_explanations(patterns, graph)

        result.scc_statistics["risk_patterns"] = [p.to_dict() for p in patterns]
        result.scc_statistics["risk_explanations"] = risk_explanations
        result.scc_statistics["pattern_count"] = len(patterns)

        logger.info(f"Risk identification: found {len(patterns)} risk patterns")
        return result

    def _analyze_scc_risk(
        self, scc: SCCInfo, result: ContractFinalResult, graph: DependencyGraph
    ) -> list[RiskPattern]:
        patterns: list[RiskPattern] = []

        scc_scores = [
            result.clause_results[cid].max_risk_score
            for cid in scc.clause_ids
            if cid in result.clause_results
        ]
        if not scc_scores:
            return patterns

        avg_risk = sum(scc_scores) / len(scc_scores)
        max_risk = max(scc_scores)

        # Pattern: circular amplification — SCC 内条款互相放大风险
        if avg_risk > self.high_risk_threshold * 0.8 and scc.size >= 2:
            patterns.append(RiskPattern(
                pattern_type="circular_amplification",
                scc_id=scc.id,
                clause_ids=scc.clause_ids,
                severity=avg_risk,
                description=(
                    f"SCC {scc.id} ({scc.size} clauses) forms a circular dependency with "
                    f"elevated average risk ({avg_risk:.2f}). Mutual references may amplify risk."
                ),
            ))

        # Pattern: hidden dependency — SCC 中有条款单独看风险低，但因环而被拉高
        for cid in scc.clause_ids:
            cr = result.clause_results.get(cid)
            if not cr:
                continue
            if cr.mean_risk_score < 0.4 and cr.max_risk_score > self.high_risk_threshold:
                patterns.append(RiskPattern(
                    pattern_type="hidden_dependency_risk",
                    scc_id=scc.id,
                    clause_ids=[cid],
                    severity=cr.max_risk_score,
                    description=(
                        f"Clause {cid} appears low-risk in isolation (mean={cr.mean_risk_score:.2f}) "
                        f"but reaches {cr.max_risk_score:.2f} under certain dependency paths in {scc.id}."
                    ),
                ))

        # Pattern: large unresolved SCC
        if scc.size >= 4 and not scc.is_collapsed:
            patterns.append(RiskPattern(
                pattern_type="complex_cycle",
                scc_id=scc.id,
                clause_ids=scc.clause_ids,
                severity=max_risk,
                description=(
                    f"Large SCC {scc.id} with {scc.size} clauses and {len(scc.internal_edges)} "
                    f"internal edges represents significant structural complexity."
                ),
            ))

        return patterns

    def _detect_cross_scc_amplification(
        self, graph: DependencyGraph, result: ContractFinalResult
    ) -> list[RiskPattern]:
        """检测 SCC 之间通过 DAG 路径传播风险的模式"""
        patterns: list[RiskPattern] = []
        if len(graph.sccs) < 2:
            return patterns

        scc_lookup: dict[str, str] = {}
        for scc in graph.sccs:
            for cid in scc.clause_ids:
                scc_lookup[cid] = scc.id

        connected_pairs: set[tuple[str, str]] = set()
        for e in graph.edges:
            src_scc = scc_lookup.get(e.source)
            tgt_scc = scc_lookup.get(e.target)
            if src_scc and tgt_scc and src_scc != tgt_scc:
                connected_pairs.add((src_scc, tgt_scc))

        for src_id, tgt_id in connected_pairs:
            src_scores = [
                result.clause_results[cid].max_risk_score
                for scc in graph.sccs if scc.id == src_id
                for cid in scc.clause_ids
                if cid in result.clause_results
            ]
            tgt_scores = [
                result.clause_results[cid].max_risk_score
                for scc in graph.sccs if scc.id == tgt_id
                for cid in scc.clause_ids
                if cid in result.clause_results
            ]
            if not src_scores or not tgt_scores:
                continue

            if max(src_scores) > 0.6 and max(tgt_scores) > 0.6:
                combined_clauses = []
                for scc in graph.sccs:
                    if scc.id in (src_id, tgt_id):
                        combined_clauses.extend(scc.clause_ids)
                patterns.append(RiskPattern(
                    pattern_type="cross_scc_amplification",
                    scc_id=f"{src_id}→{tgt_id}",
                    clause_ids=combined_clauses,
                    severity=max(max(src_scores), max(tgt_scores)),
                    description=(
                        f"Connected SCCs {src_id} and {tgt_id} both contain high-risk clauses. "
                        f"Risk may propagate across the dependency chain."
                    ),
                ))

        return patterns

    @staticmethod
    def _generate_explanations(
        patterns: list[RiskPattern], graph: DependencyGraph
    ) -> list[dict[str, Any]]:
        explanations = []
        for p in patterns:
            clause_titles = [
                graph.clauses[cid].title
                for cid in p.clause_ids
                if cid in graph.clauses
            ]
            explanations.append({
                "pattern": p.pattern_type,
                "severity": round(p.severity, 4),
                "involved_clauses": [
                    {"id": cid, "title": graph.clauses[cid].title}
                    for cid in p.clause_ids
                    if cid in graph.clauses
                ],
                "explanation": p.description,
                "recommendation": _recommendation_for(p.pattern_type),
            })
        return explanations


def _recommendation_for(pattern_type: str) -> str:
    return {
        "circular_amplification": "Review all clauses in this cycle together; consider breaking circular references.",
        "hidden_dependency_risk": "This clause's risk is context-dependent; review with its SCC neighbors.",
        "complex_cycle": "Large dependency cycle; consider simplifying clause cross-references.",
        "cross_scc_amplification": "Risk propagates across connected cycles; review the entire dependency chain.",
    }.get(pattern_type, "Manual review recommended.")

"""条款类型分类器

将每个条款分类为 Definition / Obligation / Condition / Remedy / Limitation / Other，
供 Domain-Informed Graph Pruning 的层级先验使用。
"""
from __future__ import annotations

import re
from typing import Optional

from loguru import logger

from ..llm.base import BaseLLMClient
from ..models.clause import Clause, ClauseType

_HEURISTIC_PATTERNS: list[tuple[re.Pattern, ClauseType]] = [
    (re.compile(r"\b(definition|defined\s+term|means|shall\s+mean)\b", re.I), ClauseType.DEFINITION),
    (re.compile(r"\b(shall|must|obligat|covenant|undertake|agrees?\s+to)\b", re.I), ClauseType.OBLIGATION),
    (re.compile(r"\b(if|provided\s+that|condition|subject\s+to|upon|in\s+the\s+event)\b", re.I), ClauseType.CONDITION),
    (re.compile(r"\b(remedy|remedies|indemnif|damages?|cure|compensat)\b", re.I), ClauseType.REMEDY),
    (re.compile(r"\b(limit|limitation|cap|exclusion|waiver|disclaim|ceiling)\b", re.I), ClauseType.LIMITATION),
]


class ClauseClassifier:
    def __init__(self, llm_client: Optional[BaseLLMClient] = None, config: dict | None = None):
        self.llm = llm_client
        self.use_llm = (config or {}).get("parsing", {}).get("classify_with_llm", False)

    async def classify(self, clauses: list[Clause]) -> list[Clause]:
        if self.use_llm and self.llm:
            return await self._classify_llm(clauses)
        return self._classify_heuristic(clauses)

    def _classify_heuristic(self, clauses: list[Clause]) -> list[Clause]:
        for clause in clauses:
            clause.clause_type = self._match_type(clause)
        counted = _count_types(clauses)
        logger.info(f"Clause classification (heuristic): {counted}")
        return clauses

    @staticmethod
    def _match_type(clause: Clause) -> ClauseType:
        title_lower = clause.title.lower()
        if any(kw in title_lower for kw in ("definition", "interpret")):
            return ClauseType.DEFINITION
        if any(kw in title_lower for kw in ("limitation", "limit of", "cap", "exclusion")):
            return ClauseType.LIMITATION
        if any(kw in title_lower for kw in ("remedy", "indemnif", "damages")):
            return ClauseType.REMEDY

        scores: dict[ClauseType, int] = {}
        text = clause.content[:600]
        for pattern, ctype in _HEURISTIC_PATTERNS:
            hits = len(pattern.findall(text))
            if hits:
                scores[ctype] = scores.get(ctype, 0) + hits

        if not scores:
            return ClauseType.OTHER
        return max(scores, key=scores.get)  # type: ignore[arg-type]

    async def _classify_llm(self, clauses: list[Clause]) -> list[Clause]:
        prompt = self._build_prompt(clauses)
        try:
            data = await self.llm.call_json(prompt)  # type: ignore[union-attr]
            mapping = data if isinstance(data, dict) else data.get("classifications", {})
            for clause in clauses:
                raw = mapping.get(clause.id, "other")
                try:
                    clause.clause_type = ClauseType(raw)
                except ValueError:
                    clause.clause_type = ClauseType.OTHER
        except Exception:
            logger.warning("LLM clause classification failed; falling back to heuristic")
            return self._classify_heuristic(clauses)

        counted = _count_types(clauses)
        logger.info(f"Clause classification (LLM): {counted}")
        return clauses

    @staticmethod
    def _build_prompt(clauses: list[Clause]) -> str:
        items = "\n".join(f"- {c.id}: {c.title} | {c.content[:200]}" for c in clauses)
        return (
            "Classify each contract clause into exactly one type:\n"
            '- "definition": defines terms\n'
            '- "obligation": imposes duties (shall, must)\n'
            '- "condition": conditional triggers (if, subject to)\n'
            '- "remedy": remedies, indemnification, damages\n'
            '- "limitation": liability caps, exclusions, waivers\n'
            '- "other": none of the above\n\n'
            f"Clauses:\n{items}\n\n"
            'Output as JSON: {"clause_id": "type", ...}'
        )


def _count_types(clauses: list[Clause]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in clauses:
        counts[c.clause_type.value] = counts.get(c.clause_type.value, 0) + 1
    return counts

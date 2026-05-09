"""Module 1: 条款分割与解析

输入: 合同原始文本 (str / PDF 路径)
输出: list[Clause]
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from loguru import logger

from ..llm.base import BaseLLMClient
from ..models.clause import Clause

# 常见条款编号正则
_CLAUSE_PATTERNS = [
    re.compile(r"^(第[一二三四五六七八九十百千\d]+[条章节编])", re.MULTILINE),
    re.compile(r"^(Article\s+\w+)", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(Section\s+\d+[\.\d]*)", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(Clause\s+\d+[\.\d]*)", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(\d+\.\d+(?:\.\d+)?)\s", re.MULTILINE),
]


class ClauseParser:
    def __init__(self, llm_client: BaseLLMClient, config: dict):
        self.llm = llm_client
        self.max_clause_length = config.get("parsing", {}).get("max_clause_length", 2000)
        self._prompt_template: Optional[str] = None

    def load_prompt(self, path: str) -> None:
        self._prompt_template = Path(path).read_text(encoding="utf-8")

    async def parse(self, raw_text: str) -> list[Clause]:
        rough = self._regex_split(raw_text)
        if not rough:
            logger.warning("Regex split produced no clauses; falling back to LLM parsing")
            rough = [{"id": "clause_1", "title": "Full Text", "content": raw_text}]

        if any(len(c["content"]) > self.max_clause_length for c in rough):
            refined = await self._llm_refine(rough)
        else:
            refined = rough

        clauses = []
        for i, item in enumerate(refined):
            cid = item.get("id", f"clause_{i + 1}")
            clauses.append(Clause(
                id=cid,
                title=item.get("title", f"Clause {i + 1}"),
                content=item["content"],
                section=item.get("section"),
            ))

        logger.info(f"Parsed {len(clauses)} clauses from contract text")
        return clauses

    # ------------------------------------------------------------------
    def _regex_split(self, text: str) -> list[dict]:
        """用正则按条款编号粗分割"""
        best_splits: list[tuple[int, str]] = []

        for pattern in _CLAUSE_PATTERNS:
            matches = list(pattern.finditer(text))
            if len(matches) > len(best_splits):
                best_splits = [(m.start(), m.group(1)) for m in matches]

        if not best_splits:
            return []

        best_splits.sort(key=lambda x: x[0])
        clauses = []
        for idx, (start, label) in enumerate(best_splits):
            end = best_splits[idx + 1][0] if idx + 1 < len(best_splits) else len(text)
            content = text[start:end].strip()
            clauses.append({
                "id": f"clause_{idx + 1}",
                "title": label.strip(),
                "content": content,
            })

        return clauses

    # ------------------------------------------------------------------
    async def _llm_refine(self, rough_clauses: list[dict]) -> list[dict]:
        """对过长的粗分割段落，用 LLM 做进一步拆分"""
        refined = []
        sub_idx = 0

        for clause in rough_clauses:
            if len(clause["content"]) <= self.max_clause_length:
                refined.append(clause)
                continue

            prompt = self._build_refine_prompt(clause)
            try:
                result = await self.llm.call_json(prompt)
                sub_clauses = result if isinstance(result, list) else result.get("clauses", [result])
                for sc in sub_clauses:
                    sub_idx += 1
                    refined.append({
                        "id": sc.get("id", f"clause_{clause['id']}_{sub_idx}"),
                        "title": sc.get("title", clause["title"]),
                        "content": sc.get("content", clause["content"]),
                        "section": clause.get("section"),
                    })
            except Exception:
                logger.warning(f"LLM refine failed for {clause['id']}; keeping original")
                refined.append(clause)

        return refined

    def _build_refine_prompt(self, clause: dict) -> str:
        if self._prompt_template:
            return self._prompt_template.replace("{segment}", clause["content"])

        return (
            "You are a legal document parser. Given a rough segment of a contract, "
            "identify if it contains multiple distinct clauses. For each clause, provide:\n"
            "1. A unique identifier\n"
            "2. The clause title\n"
            "3. The exact text of the clause\n\n"
            f"Input segment:\n{clause['content']}\n\n"
            'Output as JSON: {"clauses": [{"id": "...", "title": "...", "content": "..."}, ...]}'
        )

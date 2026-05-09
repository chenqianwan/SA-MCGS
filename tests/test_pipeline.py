"""Integration test for the pipeline using a mock LLM client."""
from __future__ import annotations

import json
from typing import Optional

import pytest

from src.llm.base import BaseLLMClient, LLMResponse
from src.pipeline import SaMCGSPipeline


class MockLLMClient(BaseLLMClient):
    """Deterministic mock that returns pre-programmed responses."""

    def __init__(self):
        super().__init__({"model": "mock"})
        self._call_count = 0

    async def call(
        self, prompt: str, *, temperature: float = 0.0,
        max_tokens: int = 4096, system_prompt: Optional[str] = None,
        response_format: Optional[dict] = None,
    ) -> LLMResponse:
        self._call_count += 1
        data = self._generate_response(prompt, temperature)
        return LLMResponse(content=json.dumps(data), model="mock")

    async def call_json(
        self, prompt: str, *, temperature: float = 0.0,
        max_tokens: int = 4096, system_prompt: Optional[str] = None,
    ) -> dict:
        self._call_count += 1
        return self._generate_response(prompt, temperature)

    def _generate_response(self, prompt: str, temperature: float) -> dict:
        import random
        if "dependencies" in prompt.lower() or "dependency" in prompt.lower():
            return {"dependencies": [
                {"source": "clause_1", "target": "clause_2", "type": "defines", "weight": 0.8, "reasoning": "mock"},
                {"source": "clause_2", "target": "clause_3", "type": "constrains", "weight": 0.7, "reasoning": "mock"},
            ]}

        if "clause_evaluations" in prompt.lower() or "interdependent" in prompt.lower():
            clause_ids = []
            import re
            for m in re.finditer(r"clause_\d+", prompt):
                if m.group() not in clause_ids:
                    clause_ids.append(m.group())

            base = 0.5 + (0.2 * random.random() if temperature > 0 else 0)
            return {
                "clause_evaluations": {
                    cid: {
                        "overall_risk_score": round(base + 0.05 * i, 2),
                        "dimensions": [
                            {"name": "financial_exposure", "score": round(base, 2), "reasoning": "mock"},
                            {"name": "liability_scope", "score": round(base, 2), "reasoning": "mock"},
                            {"name": "termination_risk", "score": round(base, 2), "reasoning": "mock"},
                            {"name": "compliance_burden", "score": round(base, 2), "reasoning": "mock"},
                            {"name": "ambiguity", "score": round(base, 2), "reasoning": "mock"},
                        ],
                        "reasoning": "mock evaluation",
                    }
                    for i, cid in enumerate(clause_ids)
                },
                "interaction_summary": "mock",
            }

        base = 0.5 + (0.2 * random.random() if temperature > 0 else 0)
        return {
            "overall_risk_score": round(base, 2),
            "dimensions": [
                {"name": "financial_exposure", "score": round(base, 2), "reasoning": "mock"},
                {"name": "liability_scope", "score": round(base, 2), "reasoning": "mock"},
                {"name": "termination_risk", "score": round(base, 2), "reasoning": "mock"},
                {"name": "compliance_burden", "score": round(base, 2), "reasoning": "mock"},
                {"name": "ambiguity", "score": round(base, 2), "reasoning": "mock"},
            ],
            "reasoning": "mock evaluation",
        }


SAMPLE_CONTRACT = """
1.1 Definitions
For the purposes of this Agreement, the following terms shall have the meanings set forth below.

1.2 Scope of Services
The Contractor shall provide consulting services as described in Exhibit A.

1.3 Payment Terms
The Client shall pay the Contractor within 30 days of receipt of each invoice.

2.1 Confidentiality
Each party agrees to keep confidential all information received from the other party.

2.2 Intellectual Property
All work product created under this Agreement shall be owned by the Client.

3.1 Termination
Either party may terminate this Agreement with 30 days written notice.
"""


@pytest.mark.asyncio
async def test_full_pipeline():
    config = {
        "llm": {"provider": "openai", "model": "mock"},
        "parsing": {"max_clause_length": 2000},
        "graph": {"max_clauses_per_batch": 20, "min_dependency_weight": 0.3},
        "scc": {"num_samples": 3, "temperature": 0.7},
        "pruning": {"variance_threshold": 0.01, "influence_threshold": 0.2},
        "mcgs": {"num_rollouts": 10, "ucb_exploration_weight": 1.414, "early_stopping": False},
        "aggregation": {"high_risk_threshold": 0.7, "high_uncertainty_threshold": 0.15},
        "logging": {"level": "DEBUG"},
    }

    client = MockLLMClient()
    pipeline = SaMCGSPipeline(config, client)
    result = await pipeline.run(SAMPLE_CONTRACT, contract_id="test_contract")

    assert result.contract_id == "test_contract"
    assert len(result.clause_results) > 0
    assert 0.0 <= result.overall_risk_score <= 1.0

    for cid, cr in result.clause_results.items():
        assert 0.0 <= cr.mean_risk_score <= 1.0
        assert cr.num_samples >= 1
        assert cr.source in ("dag_deterministic", "scc_collapsed", "scc_sampled")

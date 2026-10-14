"""Offline request-equivalence capture; never constructs a network client.

The caller supplies its own imported cost module so original and portable
repositories can be checked without mixing module roots. Empty JSON responses
exercise the unchanged LEA/TT control flow; no synthetic scientific result is
returned or saved. These captures represent one successful JSON response per
evaluation and therefore do not simulate provider/JSON-parse retries.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from typing import Any


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class _RecordingClient:
    """Duck-typed local evaluator client with no network implementation."""

    def __init__(self, case: dict[str, Any]):
        self.case = case
        self.actual_requests: list[dict[str, Any]] = []

    async def call_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        retries: int = 2,
    ) -> dict[str, Any]:
        # Match OpenAIClient/BudgetClient message assembly and call_json format.
        # Deployment model names, URL, keys, billing, and protocol file hashes
        # are deliberately outside this provider-independent content capture.
        messages = (
            [{"role": "system", "content": system_prompt}]
            if system_prompt else []
        )
        messages.append({"role": "user", "content": prompt})
        request = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        self.actual_requests.append({
            "call_index": len(self.actual_requests) + 1,
            "case_id": self.case["case_id"],
            "case_uid": self.case["case_uid"],
            "model": self.case["model"],
            "domain": self.case["domain"],
            "prompt": prompt,
            "system_prompt": system_prompt,
            **request,
            "request_sha256": _sha256(request),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "prompt_utf8_bytes": len(prompt.encode("utf-8")),
            "json_parse_retries": retries,
        })
        return {}


async def capture_case(cost: Any, case: dict[str, Any], graphs: dict[str, Any]) -> dict[str, Any]:
    """Capture real LEA evaluation requests without API calls or result writes.

    ``actual_requests`` contains calls that reach ``call_json`` after the
    original evaluator's transposition-table reuse. Request hashes use canonical
    UTF-8 JSON of messages/temperature/max_tokens/response_format, including the
    exact prompt text. Only the requested equivalence evidence is returned.
    """
    case_copy = copy.deepcopy(case)
    if case_copy.get("model") != "qwen2.5-72b":
        raise ValueError("Portable capture is frozen to qwen2.5-72b cases")
    if not case_copy.get("case_id") or not case_copy.get("case_uid"):
        raise ValueError("Capture requires the validated frozen case identity")
    args = argparse.Namespace(
        model="qwen2.5-72b", budget=0, window_size=4,
        compression_profile="current", internal_concurrency=1,
        case_concurrency=1,
    )
    graph, scc, _injected_id, metadata = cost.prepare_injected_case(case_copy, graphs)
    recorder = _RecordingClient(case_copy)
    result = await cost.run_lea(recorder, args, case_copy, graph, scc, metadata)
    if result["llm_calls"] != len(recorder.actual_requests):
        raise RuntimeError("LEA call count differs from offline request capture")
    capture = {
        "case_id": case_copy["case_id"],
        "case_uid": case_copy["case_uid"],
        "deterministic_windows": result["deterministic_windows"],
        "actual_requests": recorder.actual_requests,
    }
    # Reject non-JSON data/non-finite values instead of obscuring differences
    # through a permissive default=str encoder. No output file is created.
    return json.loads(json.dumps(capture, ensure_ascii=False, allow_nan=False))

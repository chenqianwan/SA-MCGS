"""Durable XHub client for the 40-cell historical-token-budget baseline study.

Reuses the all80 ledger's fsync/lock, logical-request replay, virtual-prefix
accounting, and JSON-retry implementation. The only network endpoint is XHub;
authentication comes exclusively from XHUB_API_KEY. No SDK retry or dollar cap.

Input reservations use a deliberately conservative tiktoken heuristic, NOT an
exact Gemini tokenizer. Provider usage settles actual token/cost accounting.
Unknown outcomes retain their reservation and stop the arm. A provider can
exceed a requested output ceiling (e.g. reasoning); an actual arm-budget overrun
is persisted and raised after settlement, never hidden by clipping the usage.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import tiktoken
from openai import AsyncOpenAI, DefaultAsyncHttpxClient


ENDPOINT = "https://api3.xhub.chat/v1"
PRICES_USD_PER_MILLION = {
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
}
ESTIMATE_POLICY = {
    "name": "cl100k_heuristic_with_margin.v1",
    "encoding": "cl100k_base", "multiplier": 1.25,
    "fixed_margin": 256, "per_message_margin": 16,
    "exact_provider_tokenizer": False,
}
REUSED_CLIENT_PATH = Path(__file__).resolve().parent.parent / "equal_budget_all80_20261009" / "budget_client.py"
REUSED_CLIENT_SHA256 = hashlib.sha256(REUSED_CLIENT_PATH.read_bytes()).hexdigest()
_module_name = "_equal_budget_api10_durable_base"
if _module_name in sys.modules:
    _base = sys.modules[_module_name]
else:
    _spec = importlib.util.spec_from_file_location(_module_name, REUSED_CLIENT_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError("Unable to load the frozen all80 budget client")
    _base = importlib.util.module_from_spec(_spec)
    sys.modules[_module_name] = _base
    _spec.loader.exec_module(_base)

BudgetStop = _base.BudgetStop
LedgerError = _base.LedgerError
BudgetLLMResponse = _base.BudgetLLMResponse
_hash, _write_json, _plain = _base._hash, _base._write_json, _base._plain


def _safe(value: Any, secret: str = "") -> Any:
    value = _plain(value)
    if isinstance(value, dict):
        forbidden = {"authorization", "api_key", "apikey", "access_token", "headers",
                     "request_headers", "response_headers"}
        return {k: _safe(v, secret) for k, v in value.items() if k.lower() not in forbidden}
    if isinstance(value, list):
        return [_safe(v, secret) for v in value]
    if secret and isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    return value


def _valid_tokens(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class GlobalLedger(_base.GlobalLedger):
    """One cell per ledger; inherited lifetime flock prevents double payment."""

    HEADER = {
        "event": "header", "version": 1, "accounting": "actual_xhub_provider_tokens",
        "external_api_enabled": True, "endpoint": ENDPOINT,
        "unknown_outcome": "retain_full_reservation", "estimate_policy": ESTIMATE_POLICY,
        "prices_usd_per_million": PRICES_USD_PER_MILLION,
        "reused_client_sha256": REUSED_CLIENT_SHA256,
    }

    def _summary(self, rows: list[dict]) -> dict:
        summary = super()._summary(rows)
        known = [r for r in rows if r["status"] == "completed_with_usage"]
        held = [r for r in rows if r["status"] != "completed_with_usage"]
        actual_cost = sum(r.get("estimated_cost_usd", 0.0) for r in known)
        held_cost = 0.0
        for row in held:
            prices = PRICES_USD_PER_MILLION[row["owner"][1]]
            held_cost += (row["input_tokens"] * prices["input"] +
                          row["max_output_tokens"] * prices["output"]) / 1_000_000
        return {**summary, "external_api_calls": len(rows),
                "actual_usd": actual_cost, "estimated_usd": actual_cost, "estimated_cost_usd": actual_cost,
                "held_usd": held_cost, "accounted_usd": actual_cost + held_cost,
                "cost_is_estimate": True, "usd_hard_cap": None,
                "input_estimate_mismatch_calls": sum(r.get("input_estimate_error", 0) != 0 for r in known),
                "output_ceiling_exceeded_calls": sum(r.get("output_ceiling_exceeded", False) for r in known),
                "budget_overrun": any(r.get("budget_overrun", False) for r in rows),
                "budget_overrun_tokens": max((r.get("budget_overrun_tokens", 0) for r in rows), default=0)}

    async def reserve(self, **kwargs: Any) -> tuple[dict, bool]:
        await self.initialize()
        owner = tuple(kwargs["owner"])
        # Replay may traverse the successful prefix preceding an overrun; it
        # must stop at the original offending cached request, not resample it.
        if (*owner, kwargs["request_key"]) not in self._keys:
            if any(r.get("budget_overrun") for r in self.owner_records(*owner)):
                raise BudgetStop("budget_overrun", token_cap=kwargs["token_cap"])
        return await super().reserve(**kwargs)

    async def finish(self, call_id: str, *, usage: dict | None, provider_model: str = "",
                     elapsed_seconds: float = 0, error_type: str | None = None,
                     response_sha256: str | None = None, http_status: int | None = None) -> dict:
        async with self._lock:
            if not self._initialized or self._closed:
                raise LedgerError("ledger_unavailable_during_settlement")
            row = self._calls[call_id]
            if row["status"] != "reserved":
                raise LedgerError("duplicate_settlement")
            usage = usage if isinstance(usage, dict) else {}
            prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
            event = {"event": "finish", "call_id": call_id, "usage": usage,
                     "provider_model": provider_model, "elapsed_seconds": elapsed_seconds,
                     "response_sha256": response_sha256, "usage_issues": []}
            if _valid_tokens(prompt) and _valid_tokens(completion):
                subtotal = prompt + completion
                total = usage.get("total_tokens", subtotal)
                if not _valid_tokens(total) or total < subtotal:
                    event["usage_issues"].append("invalid_provider_total_tokens")
                    total = subtotal
                # Some gateways expose reasoning only in total_tokens. Retain
                # all raw details and charge the full provider total; do not add
                # reasoning_tokens again when already included in completion.
                charged_output = max(completion, total - prompt)
                prices = PRICES_USD_PER_MILLION[row["owner"][1]]
                owner = tuple(row["owner"])
                previous = sum(self.accounted_tokens(r) for r in self.owner_records(*owner)
                               if r["call_id"] != call_id)
                cap = self._owners[owner]["token_cap"]
                overrun = max(0, previous + total - cap) if cap is not None else 0
                event.update(status="completed_with_usage", prompt_tokens=prompt,
                             completion_tokens=completion, actual_total_tokens=total,
                             charged_output_tokens=charged_output,
                             provider_total_residual_tokens=total - subtotal,
                             input_estimate_error=prompt - row["input_tokens"],
                             output_ceiling_exceeded=charged_output > row["max_output_tokens"],
                             budget_overrun=overrun > 0, budget_overrun_tokens=overrun,
                             owner_actual_tokens_after_call=previous + total,
                             estimated_cost_usd=(prompt * prices["input"] + charged_output * prices["output"]) / 1_000_000,
                             prices_usd_per_million=prices)
            else:
                event["status"] = "unknown_failure" if error_type else "completed_without_usage"
            if error_type:
                event["error_type"] = error_type
            if isinstance(http_status, int) and not isinstance(http_status, bool):
                event["http_status"] = http_status
            self._append(event)
            row.update(event)
            return dict(row)


class BudgetClient(_base.BudgetClient):
    def __init__(self, config: dict | None = None, *, ledger: GlobalLedger,
                 case_id: str, method: str, model: str | None = None,
                 base_url: str | None = None, call_log_dir: str | Path | None = None,
                 token_cap: int | None = None, json_attempts: int = 3,
                 selector_json_attempts: int = 1, tokenizer: Any = None,
                 provider_client: Any = None, **unsupported: Any):
        config = dict(config or {})
        model = model or config.get("model")
        if model not in PRICES_USD_PER_MILLION:
            raise ValueError("Only gpt-4o and gemini-2.5-pro are supported")
        if method not in {"lea", "full-scc"}:
            raise ValueError("Only historical-budget LEA and Full-SCC arms are supported")
        if not isinstance(token_cap, int) or isinstance(token_cap, bool) or token_cap <= 0:
            raise ValueError("A positive historical token_cap is required; no new SA run")
        if json_attempts != 3 or selector_json_attempts != 1:
            raise ValueError("The frozen protocol requires 3 JSON attempts and 1 selector attempt")
        if unsupported or tokenizer is not None:
            raise ValueError("Provider-specific tokenizer/extra API overrides are not supported")
        for configured_endpoint in (base_url, config.get("base_url")):
            if configured_endpoint is not None and configured_endpoint.rstrip("/") != ENDPOINT:
                raise ValueError("Only the fixed XHub endpoint is permitted")
        if any(k in config for k in ("api_key", "api_key_env", "chat_template_kwargs")):
            raise ValueError("Authentication must come exclusively from XHUB_API_KEY")
        self._secret = os.environ.get("XHUB_API_KEY", "").strip()
        if provider_client is None and not self._secret:
            raise ValueError("XHUB_API_KEY is required")
        config.update(model=model, base_url=ENDPOINT, max_retries=0, timeout=600)
        _base.BaseLLMClient.__init__(self, config)
        self.ledger, self.case_id, self.method = ledger, str(case_id), method
        self.owner = (self.case_id, self.model, self.method)
        self.token_cap = token_cap
        self.json_attempts, self.selector_json_attempts = 3, 1
        self.chat_template_kwargs = {}
        # Operational context bounds, not a claim of exact tokenizer parity.
        self.max_model_len = int(config.get("max_model_len", config.get("context_window", 128_000)))
        if self.max_model_len <= 0:
            raise ValueError("max_model_len must be positive")
        self.tokenizer = tiktoken.get_encoding(ESTIMATE_POLICY["encoding"])
        self.fingerprint = _hash({"model": model, "endpoint": ENDPOINT, "method": method,
                                  "estimate_policy": ESTIMATE_POLICY, "timeout": 600,
                                  "json_attempts": 3, "selector_json_attempts": 1,
                                  "max_model_len": self.max_model_len,
                                  "output_limits": {"lea": 2048, "full-scc": 12000, "selector": 256},
                                  "reused_client_sha256": REUSED_CLIENT_SHA256})
        self.call_log_dir = Path(call_log_dir) if call_log_dir else ledger.path.parent / "calls" / _hash(self.owner)[:20]
        self.client = provider_client if provider_client is not None else AsyncOpenAI(
            api_key=self._secret, base_url=ENDPOINT, timeout=600, max_retries=0,
            http_client=DefaultAsyncHttpxClient(trust_env=False))
        self._phase, self._selector_reserve, self._logical_sequence = "candidate", 0, 0
        self._seen_calls, self._prefix_rows = set(), []
        self._cache_hits, self._closed = 0, False
        self.last_usage, self.last_response, self.last_call_record = {}, None, None

    def set_phase(self, phase: str) -> None:
        if phase not in {"candidate", "selector"}:
            raise ValueError("This experiment runs baseline candidate/selector phases only")
        super().set_phase(phase)

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, disallowed_special=()))

    def estimate_request(self, prompt: str, *, system_prompt: str | None = None,
                         max_tokens: int = 4096, response_format: dict | None = None,
                         respect_budget: bool = True) -> dict:
        if not isinstance(prompt, str) or (system_prompt is not None and not isinstance(system_prompt, str)):
            raise TypeError("Only text prompts are supported")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else [])
        messages.append({"role": "user", "content": prompt})
        encoded = sum(self.count_tokens(m["content"]) for m in messages)
        inputs = (math.ceil(encoded * ESTIMATE_POLICY["multiplier"]) + ESTIMATE_POLICY["fixed_margin"] +
                  len(messages) * ESTIMATE_POLICY["per_message_margin"])
        limit = 256 if self._phase == "selector" else {"lea": 2048, "full-scc": 12000}[self.method]
        effective = min(max_tokens, limit, self.max_model_len - inputs)
        if respect_budget:
            effective = min(effective, int(self.remaining_tokens) - inputs)
        effective = max(0, effective)
        return {"messages": messages, "input_tokens": inputs, "estimated_input_tokens": inputs,
                "estimate_policy": ESTIMATE_POLICY, "heuristic_text_tokens": encoded,
                "max_output_tokens": effective, "requested_max_output_tokens": max_tokens,
                "reserved_tokens": inputs + effective, "requested_tokens": inputs + min(max_tokens, limit),
                "response_format": response_format}

    def _check_usage(self, row: dict) -> None:
        if row["status"] != "completed_with_usage":
            raise BudgetStop("unknown_provider_usage", call_id=row["call_id"], status=row["status"])
        if row.get("budget_overrun"):
            raise BudgetStop("budget_overrun", call_id=row["call_id"], token_cap=self.token_cap,
                             accounted_tokens=row["owner_actual_tokens_after_call"],
                             overrun_tokens=row["budget_overrun_tokens"])
        if row.get("usage_issues"):
            raise BudgetStop("invalid_provider_usage", call_id=row["call_id"], issues=row["usage_issues"])

    async def _call(self, prompt: str, *, temperature: float, max_tokens: int,
                    system_prompt: str | None, response_format: dict | None,
                    logical_key: str, retry_index: int) -> BudgetLLMResponse:
        if self._closed:
            raise LedgerError("client_already_closed")
        estimate = self.estimate_request(prompt, system_prompt=system_prompt, max_tokens=max_tokens,
                                         response_format=response_format)
        effective = estimate["max_output_tokens"]
        if effective <= 0:
            # Preserve a known overrun classification on a subsequent call.
            if self.ledger.owner_summary(*self.owner).get("budget_overrun"):
                raise BudgetStop("budget_overrun", token_cap=self.token_cap)
            raise BudgetStop("no_output_budget", input_tokens=estimate["input_tokens"], remaining_tokens=self.remaining_tokens)
        body = {"model": self.model, "messages": estimate["messages"], "temperature": temperature,
                "max_tokens": effective}
        if response_format:
            body["response_format"] = response_format
        request_hash = _hash({"body": body, "phase": self._phase, "fingerprint": self.fingerprint,
                              "requested_max_tokens": max_tokens, "selector_reserve": self._selector_reserve,
                              "token_cap": self.token_cap})
        key = f"{logical_key}:attempt-{retry_index}"
        output_path = self.call_log_dir / f"{_hash(key)[:24]}.json"
        try:
            cache_path = str(output_path.resolve().relative_to(self.ledger.path.parent.resolve()))
        except ValueError:
            cache_path = str(output_path.resolve())
        row, cached = await self.ledger.reserve(
            owner=self.owner, token_cap=self.token_cap, fingerprint=self.fingerprint,
            request_key=key, request_hash=request_hash, phase=self._phase,
            input_tokens=estimate["input_tokens"], max_output=effective,
            requested_max_output=max_tokens, selector_reserve=self._selector_reserve,
            cache_file=cache_path, retry_index=retry_index)
        if cached:
            return await self._cached_response(row)
        log = {"call_id": row["call_id"], "request_key": key, "request_hash": request_hash,
               "endpoint": ENDPOINT, "request": body, "estimate_policy": ESTIMATE_POLICY,
               "reservation": row, "status": "reserved"}
        try:
            _write_json(output_path, _safe(log, self._secret))
        except Exception as exc:
            raise LedgerError(f"request_log_write_failed:{type(exc).__name__}") from None
        started = time.monotonic()
        try:
            raw = await self.client.chat.completions.create(**body)
        except BaseException as exc:
            elapsed = time.monotonic() - started
            http_status = getattr(exc, "status_code", None)
            http_status = http_status if _valid_tokens(http_status) else None
            row = await asyncio.shield(self.ledger.finish(
                row["call_id"], usage=None, elapsed_seconds=elapsed,
                error_type=type(exc).__name__, http_status=http_status))
            self._consume(row, False)
            log.update(status=row["status"], elapsed_seconds=elapsed,
                       error_type=type(exc).__name__, http_status=http_status)
            try:
                _write_json(output_path, _safe(log, self._secret))
            except Exception:
                pass
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit, BudgetStop, LedgerError)):
                raise
            raise BudgetStop("unknown_provider_outcome", call_id=row["call_id"],
                             error_type=type(exc).__name__, http_status=http_status) from None
        elapsed = time.monotonic() - started
        usage = _safe(getattr(raw, "usage", None), self._secret) or {}
        usage = usage if isinstance(usage, dict) else {}
        model = _safe(str(getattr(raw, "model", "") or ""), self._secret)
        try:
            content = raw.choices[0].message.content or ""
        except (AttributeError, IndexError, TypeError):
            content = ""
        result = _safe({"content": content, "model": model, "usage": usage, "raw": raw}, self._secret)
        result_hash = _hash(result)
        log.update(status="response_received", result=result, elapsed_seconds=elapsed)
        # This order preserves the existing recoverable response/settlement crash window.
        try:
            _write_json(output_path, _safe(log, self._secret))
        except Exception as exc:
            raise LedgerError(f"response_log_write_failed:{type(exc).__name__}") from None
        row = await self.ledger.finish(row["call_id"], usage=usage, provider_model=model,
                                       elapsed_seconds=elapsed, response_sha256=result_hash)
        self._consume(row, False)
        self._check_usage(row)
        response = BudgetLLMResponse(**result)
        self.last_response = response
        return response

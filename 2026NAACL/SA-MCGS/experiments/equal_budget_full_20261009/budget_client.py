"""Durable token accounting for local-vLLM equal-budget experiments.

SA runs first without a token cap; its measured provider usage defines B. Every
baseline request, including JSON recovery and final selection, consumes that B.
New requests reserve exact chat-template input + the effective output ceiling.
Unknown outcomes retain the whole reservation and stop rather than resample.

Recovery has two counters: durable accounting protects the real budget; virtual
prefix accounting advances as cached responses are replayed, preserving the
algorithm's original stopping decisions. Identical prompts at different logical
call indices are independent samples. Only the same index AND full request hash
can reuse a cached response. SDK retries are always disabled.
"""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import ipaddress
import json
import math
import os
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from src.llm.base import BaseLLMClient, LLMResponse
from src.llm.openai_client import OpenAIClient


class BudgetStop(BaseException):
    """Deliberately escapes search code's ``except Exception`` score fallback."""

    def __init__(self, reason: str, **details: Any):
        self.reason, self.details = reason, details
        super().__init__(f"budget_stop:{reason}")


class LedgerError(BaseException):
    """Durability or replay failure: do not continue or silently resample."""


class ProviderCallError(Exception):
    """Safe provider error classification, with no SDK request headers."""


class BudgetLLMResponse(LLMResponse):
    usage: dict[str, Any] = {}


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return {"object_type": type(value).__name__}


def _safe(value: Any) -> Any:
    value = _plain(value)
    if isinstance(value, dict):
        forbidden = {"authorization", "api_key", "access_token", "headers",
                     "request_headers", "response_headers"}
        return {k: _safe(v) for k, v in value.items() if k.lower() not in forbidden}
    if isinstance(value, list):
        return [_safe(v) for v in value]
    return value


def _serialized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_serialized(value).encode("utf-8")).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(_serialized(value) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    # Preserve the rename across a machine crash, not only a Python crash.
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _local_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("A credential-free local vLLM HTTP URL is required")
    host = parsed.hostname or ""
    allowed = host == "localhost"
    try:
        allowed = allowed or ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    if not allowed or parsed.query or parsed.fragment:
        raise ValueError("Only loopback vLLM endpoints are permitted; external APIs are disabled")
    return value


class GlobalLedger:
    """One fsynced JSONL ledger, protected against concurrent runner processes."""

    HEADER = {"event": "header", "version": 1, "accounting": "actual_local_vllm_tokens",
              "external_api_enabled": False, "unknown_outcome": "retain_full_reservation"}

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = asyncio.Lock()
        self._file_lock = None
        self._initialized = False
        self._closed = False
        self._calls: dict[str, dict] = {}
        self._keys: dict[tuple[str, str, str, str], str] = {}
        self._owners: dict[tuple[str, str, str], dict] = {}
        self._budgets: dict[tuple[str, str], dict] = {}
        self._recovered: set[str] = set()

    def _append(self, event: dict) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(_serialized({"time_unix": time.time(), **event}) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except Exception as exc:
            raise LedgerError(f"ledger_write_failed:{type(exc).__name__}") from None

    async def initialize(self) -> "GlobalLedger":
        async with self._lock:
            if self._closed:
                raise LedgerError("ledger_already_closed")
            if self._initialized:
                return self
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file_lock = self.path.with_suffix(self.path.suffix + ".lock").open("a+")
            try:
                fcntl.flock(self._file_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self._file_lock.close()
                self._file_lock = None
                raise LedgerError("ledger_in_use_by_another_runner") from None
            try:
                self._load()
            except BaseException:
                fcntl.flock(self._file_lock.fileno(), fcntl.LOCK_UN)
                self._file_lock.close()
                self._file_lock = None
                raise
            self._initialized = True
            return self

    def _load(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            self._append(self.HEADER)
            return
        try:
            data = self.path.read_bytes()
            if not data.endswith(b"\n"):
                raise LedgerError("ledger_truncated_final_record")
            events = [json.loads(line) for line in data.splitlines()]
            if any(events[0].get(k) != v for k, v in self.HEADER.items()):
                raise LedgerError("ledger_protocol_mismatch")
            for event in events[1:]:
                kind = event["event"]
                if kind == "owner":
                    owner = tuple(event["owner"])
                    if owner in self._owners:
                        raise LedgerError("duplicate_owner_record")
                    self._owners[owner] = event
                elif kind == "reserve":
                    key = (*event["owner"], event["request_key"])
                    if key in self._keys or event["call_id"] in self._calls:
                        raise LedgerError("duplicate_request_reservation")
                    self._keys[key] = event["call_id"]
                    self._calls[event["call_id"]] = {**event, "status": "reserved"}
                elif kind == "finish":
                    row = self._calls[event["call_id"]]
                    if row["status"] != "reserved":
                        raise LedgerError("duplicate_settlement")
                    row.update(event)
                elif kind == "parse":
                    self._calls[event["call_id"]].setdefault("parse_events", []).append(event)
                elif kind == "freeze_budget":
                    key = (event["case_id"], event["model"])
                    if key in self._budgets:
                        raise LedgerError("duplicate_budget_freeze")
                    self._budgets[key] = event
                else:
                    raise LedgerError("unknown_ledger_event")
            self._recovered = {call_id for call_id, row in self._calls.items()
                               if row["status"] != "completed_with_usage"}
        except LedgerError:
            raise
        except Exception as exc:
            raise LedgerError(f"ledger_replay_failed:{type(exc).__name__}") from None

    @staticmethod
    def accounted_tokens(row: dict) -> int:
        return (row["actual_total_tokens"] if row["status"] == "completed_with_usage"
                else row["reserved_tokens"])

    def owner_records(self, case_id: str, model: str, method: str) -> list[dict]:
        return [r for r in self._calls.values() if tuple(r["owner"]) == (case_id, model, method)]

    def _summary(self, rows: list[dict]) -> dict:
        known = [r for r in rows if r["status"] == "completed_with_usage"]
        held = [r for r in rows if r["status"] != "completed_with_usage"]
        return {
            "calls": len(rows), "completed_with_usage": len(known), "held_calls": len(held),
            "pending_calls": sum(r["status"] == "reserved" for r in rows),
            "unknown_failure_calls": sum(r["status"] == "unknown_failure" for r in rows),
            "missing_usage_calls": sum(r["status"] == "completed_without_usage" for r in rows),
            "recovered_unresolved_calls": sum(r["call_id"] in self._recovered for r in rows),
            "retry_calls": sum(r["retry_index"] > 0 for r in rows),
            "prompt_tokens": sum(r["prompt_tokens"] for r in known),
            "completion_tokens": sum(r["completion_tokens"] for r in known),
            "total_tokens": sum(r["actual_total_tokens"] for r in known),
            "held_tokens": sum(r["reserved_tokens"] for r in held),
            "accounted_tokens": sum(self.accounted_tokens(r) for r in rows),
            "provider_seconds": sum(r.get("elapsed_seconds", 0) for r in rows),
            "usage_mismatch_calls": sum(bool(r.get("usage_issues")) for r in rows),
            "parse_failure_calls": sum(any(p["outcome"] != "dict" for p in r.get("parse_events", [])) for r in rows),
            "external_api_calls": 0,
        }

    def owner_summary(self, case_id: str, model: str, method: str) -> dict:
        return self._summary(self.owner_records(case_id, model, method))

    async def summary(self) -> dict:
        await self.initialize()
        async with self._lock:
            return {**self._summary(list(self._calls.values())),
                    "frozen_budgets": list(self._budgets.values())}

    async def reserve(self, *, owner: tuple[str, str, str], token_cap: int | None,
                      fingerprint: str, request_key: str, request_hash: str, phase: str,
                      input_tokens: int, max_output: int, selector_reserve: int,
                      requested_max_output: int, cache_file: str, retry_index: int) -> tuple[dict, bool]:
        await self.initialize()
        async with self._lock:
            expected = {"owner": list(owner), "token_cap": token_cap, "fingerprint": fingerprint}
            if owner in self._owners:
                if any(self._owners[owner].get(k) != v for k, v in expected.items()):
                    raise LedgerError("owner_configuration_changed_on_resume")
            else:
                event = {"event": "owner", **expected}
                self._append(event)
                self._owners[owner] = event
            key = (*owner, request_key)
            if key in self._keys:
                row = self._calls[self._keys[key]]
                if row["request_hash"] != request_hash:
                    raise LedgerError("cached_request_hash_mismatch")
                return dict(row), True
            records = self.owner_records(*owner)
            if any(r.get("usage_issues") for r in records):
                raise BudgetStop("tokenizer_or_provider_usage_mismatch")
            if any(r["status"] != "completed_with_usage" for r in records):
                raise BudgetStop("unresolved_prior_request")
            used = sum(self.accounted_tokens(r) for r in records)
            reserve = input_tokens + max_output
            selector = 0 if phase == "selector" else selector_reserve
            if token_cap is not None and used + reserve + selector > token_cap:
                raise BudgetStop("tokens", accounted_tokens=used, request_tokens=reserve,
                                 selector_reserve=selector, token_cap=token_cap)
            if max_output <= 0:
                raise BudgetStop("no_output_budget")
            row = {
                "event": "reserve", "call_id": uuid.uuid4().hex, "owner": list(owner),
                "request_key": request_key, "request_hash": request_hash, "phase": phase,
                "input_tokens": input_tokens, "max_output_tokens": max_output,
                "requested_max_output_tokens": requested_max_output,
                "reserved_tokens": reserve, "selector_reserve": selector,
                "retry_index": retry_index, "cache_file": cache_file,
            }
            self._append(row)
            self._calls[row["call_id"]] = {**row, "status": "reserved"}
            self._keys[key] = row["call_id"]
            return dict(self._calls[row["call_id"]]), False

    async def finish(self, call_id: str, *, usage: dict | None, provider_model: str = "",
                     elapsed_seconds: float = 0, error_type: str | None = None,
                     response_sha256: str | None = None) -> dict:
        async with self._lock:
            if not self._initialized or self._closed:
                raise LedgerError("ledger_unavailable_during_settlement")
            row = self._calls[call_id]
            if row["status"] != "reserved":
                raise LedgerError("duplicate_settlement")
            prompt = usage.get("prompt_tokens") if usage else None
            completion = usage.get("completion_tokens") if usage else None
            valid = all(isinstance(n, int) and not isinstance(n, bool) and n >= 0
                        for n in (prompt, completion))
            event = {"event": "finish", "call_id": call_id, "usage": usage or {},
                     "provider_model": provider_model, "elapsed_seconds": elapsed_seconds,
                     "response_sha256": response_sha256, "usage_issues": []}
            if valid:
                total = usage.get("total_tokens", prompt + completion)
                if not isinstance(total, int) or isinstance(total, bool) or total != prompt + completion:
                    event["usage_issues"].append("provider_total_not_input_plus_output")
                    total = max(prompt + completion, total if isinstance(total, int) else 0)
                if prompt != row["input_tokens"]:
                    event["usage_issues"].append("tokenizer_prompt_count_mismatch")
                if completion > row["max_output_tokens"]:
                    event["usage_issues"].append("provider_output_exceeded_request")
                event.update(status="completed_with_usage", prompt_tokens=prompt,
                             completion_tokens=completion, actual_total_tokens=total)
            else:
                event["status"] = "unknown_failure" if error_type else "completed_without_usage"
            if error_type:
                event["error_type"] = error_type
            self._append(event)
            row.update(event)
            return dict(row)

    async def record_parse(self, call_id: str, outcome: str) -> None:
        async with self._lock:
            row = self._calls[call_id]
            # Replaying the same cached content must not multiply failure counts.
            if any(p["outcome"] == outcome for p in row.get("parse_events", [])):
                return
            event = {"event": "parse", "call_id": call_id, "outcome": outcome}
            self._append(event)
            row.setdefault("parse_events", []).append(event)

    async def freeze_budget(self, case_id: str, model: str, sa_method: str = "sa") -> int:
        """Caller must invoke only after its complete 60-slot SA run succeeds."""
        await self.initialize()
        async with self._lock:
            rows = self.owner_records(case_id, model, sa_method)
            if not rows or any(r["status"] != "completed_with_usage" or r.get("usage_issues") for r in rows):
                raise BudgetStop("cannot_freeze_unknown_or_mismatched_sa_usage")
            budget = sum(r["actual_total_tokens"] for r in rows)
            if budget <= 0:
                raise BudgetStop("cannot_freeze_empty_sa_budget")
            key = (case_id, model)
            ids = [r["call_id"] for r in rows]
            if key in self._budgets:
                frozen = self._budgets[key]
                if frozen["token_budget"] != budget or frozen["source_call_ids"] != ids:
                    raise LedgerError("frozen_sa_budget_changed")
                return budget
            event = {"event": "freeze_budget", "case_id": case_id, "model": model,
                     "sa_method": sa_method, "token_budget": budget, "source_call_ids": ids}
            self._append(event)
            self._budgets[key] = event
            return budget

    async def close(self) -> None:
        async with self._lock:
            if self._file_lock is not None:
                fcntl.flock(self._file_lock.fileno(), fcntl.LOCK_UN)
                self._file_lock.close()
                self._file_lock = None
            self._closed = True


class BudgetClient(BaseLLMClient):
    budget_stop_type = BudgetStop

    def __init__(self, config: dict | None = None, *, ledger: GlobalLedger,
                 case_id: str, method: str, tokenizer: Any, model: str | None = None,
                 base_url: str | None = None, call_log_dir: str | Path | None = None,
                 token_cap: int | None = None, json_attempts: int = 3,
                 selector_json_attempts: int = 1, chat_template_kwargs: dict | None = None,
                 provider_client: Any = None):
        config = dict(config or {})
        model = model or config.get("model")
        if not isinstance(model, str) or not model:
            raise ValueError("A local served-model name is required")
        if token_cap is not None and (not isinstance(token_cap, int) or isinstance(token_cap, bool) or token_cap <= 0):
            raise ValueError("token_cap must be a positive integer or None for the initial SA run")
        if json_attempts < 1 or selector_json_attempts < 1:
            raise ValueError("JSON attempts must be positive")
        endpoint = _local_url(base_url or config.get("base_url") or "http://127.0.0.1:8000/v1")
        # Never use config/env API keys; this client can only reach local vLLM.
        config = {k: v for k, v in config.items() if k not in {"api_key", "api_key_env"}}
        config.update(model=model, base_url=endpoint, max_retries=0)
        super().__init__(config)
        self.ledger, self.tokenizer = ledger, tokenizer
        self.case_id, self.method = str(case_id), str(method)
        self.owner = (self.case_id, self.model, self.method)
        self.token_cap = token_cap
        self.json_attempts, self.selector_json_attempts = int(json_attempts), int(selector_json_attempts)
        self.chat_template_kwargs = dict(chat_template_kwargs or config.get("chat_template_kwargs") or {})
        if any(k in self.chat_template_kwargs for k in ("tokenize", "return_tensors", "add_generation_prompt", "return_dict")):
            raise ValueError("Tokenization/generation flags cannot be overridden")
        self.max_model_len = config.get("max_model_len", config.get("context_window"))
        if self.max_model_len is not None:
            self.max_model_len = int(self.max_model_len)
        tokenizer_description = {
            "class": type(tokenizer).__name__, "name_or_path": getattr(tokenizer, "name_or_path", None),
            "chat_template": getattr(tokenizer, "chat_template", None),
            "special_tokens_map": _plain(getattr(tokenizer, "special_tokens_map", {})),
            "declared_fingerprint": config.get("tokenizer_fingerprint"),
        }
        self.fingerprint = _hash({"model": self.model, "tokenizer": tokenizer_description,
                                 "chat_template_kwargs": self.chat_template_kwargs,
                                 "json_attempts": self.json_attempts,
                                 "selector_json_attempts": self.selector_json_attempts,
                                 "max_model_len": self.max_model_len})
        self.call_log_dir = Path(call_log_dir) if call_log_dir else ledger.path.parent/"calls"/_hash(self.owner)[:20]
        self.client = provider_client if provider_client is not None else AsyncOpenAI(
            api_key="local-vllm", base_url=endpoint, timeout=self.timeout,
            max_retries=0, http_client=DefaultAsyncHttpxClient(trust_env=False),
        )
        self._phase = "candidate"
        self._selector_reserve = 0
        self._logical_sequence = 0
        self._seen_calls: set[str] = set()
        self._prefix_rows: list[dict] = []
        self._cache_hits = 0
        self._closed = False
        self.last_usage: dict[str, Any] = {}
        self.last_response: BudgetLLMResponse | None = None
        self.last_call_record: dict | None = None

    @property
    def token_usage(self) -> dict:
        summary = self.ledger._summary(self._prefix_rows)
        return {k: summary[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens",
                                       "held_tokens", "accounted_tokens")}

    @property
    def remaining_tokens(self) -> int | float:
        if self.token_cap is None:
            return math.inf
        reserve = 0 if self._phase == "selector" else self._selector_reserve
        return max(0, self.token_cap - self.token_usage["accounted_tokens"] - reserve)

    def set_phase(self, phase: str) -> None:
        if phase not in {"sa", "candidate", "selector"}:
            raise ValueError("phase must be sa, candidate or selector")
        self._phase = phase

    def set_selector_reserve(self, tokens: int) -> None:
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
            raise ValueError("selector reserve must be a nonnegative integer")
        self._selector_reserve = tokens

    def summary(self) -> dict:
        return {"case_id": self.case_id, "model": self.model, "method": self.method,
                "phase": self._phase, "token_cap": self.token_cap,
                "remaining_tokens": None if self.token_cap is None else self.remaining_tokens,
                "selector_reserve": self._selector_reserve, "cache_replays": self._cache_hits,
                "virtual_prefix": self.ledger._summary(self._prefix_rows),
                **self.ledger.owner_summary(*self.owner)}

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))

    def estimate_request(self, prompt: str, *, system_prompt: str | None = None,
                         max_tokens: int = 4096, response_format: dict | None = None,
                         respect_budget: bool = True) -> dict:
        if not isinstance(prompt, str) or (system_prompt is not None and not isinstance(system_prompt, str)):
            raise TypeError("Only text chat prompts are supported")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        ids = self.tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, **self.chat_template_kwargs)
        if isinstance(ids, Mapping):
            ids = ids["input_ids"]
        if hasattr(ids, "tolist"):
            ids = ids.tolist()
        if not isinstance(ids, list) or (ids and isinstance(ids[0], list)):
            raise LedgerError("tokenizer_did_not_return_single_token_sequence")
        inputs = len(ids)
        effective = max_tokens
        if self.max_model_len is not None:
            effective = min(effective, self.max_model_len-inputs)
        if respect_budget and self.token_cap is not None:
            effective = min(effective, int(self.remaining_tokens)-inputs)
        effective = max(0, effective)
        return {"messages": messages, "input_tokens": inputs,
                "estimated_input_tokens": inputs, "max_output_tokens": effective,
                "requested_max_output_tokens": max_tokens, "reserved_tokens": inputs+effective,
                "requested_tokens": inputs+max_tokens, "response_format": response_format}

    def _logical_key(self, request_key: str | None) -> str:
        key = request_key if request_key is not None else f"call-{self._logical_sequence:08d}"
        self._logical_sequence += 1
        return str(key)

    def _consume(self, row: dict, cached: bool) -> None:
        if row["call_id"] not in self._seen_calls:
            self._seen_calls.add(row["call_id"])
            self._prefix_rows.append(dict(row))
        if cached:
            self._cache_hits += 1
        self.last_call_record = dict(row)
        self.last_usage = row.get("usage", {})

    def _check_usage(self, row: dict) -> None:
        if row["status"] != "completed_with_usage":
            raise BudgetStop("unknown_provider_usage", call_id=row["call_id"], status=row["status"])
        if row.get("usage_issues"):
            raise BudgetStop("tokenizer_or_provider_usage_mismatch", call_id=row["call_id"],
                             issues=row["usage_issues"], estimated_input=row["input_tokens"],
                             actual_input=row.get("prompt_tokens"))

    async def call(self, prompt: str, *, temperature: float = 0.0, max_tokens: int = 4096,
                   system_prompt: Optional[str] = None, response_format: Optional[dict] = None,
                   request_key: str | None = None) -> BudgetLLMResponse:
        return await self._call(prompt, temperature=temperature, max_tokens=max_tokens,
                                system_prompt=system_prompt, response_format=response_format,
                                logical_key=self._logical_key(request_key), retry_index=0)

    async def _cached_response(self, row: dict) -> BudgetLLMResponse:
        path = Path(row["cache_file"])
        if not path.is_absolute():
            path = self.ledger.path.parent/path
        try:
            cached = json.loads(path.read_text())
        except (OSError, ValueError):
            self._consume(row, True)
            raise BudgetStop("unresolved_cached_request", call_id=row["call_id"]) from None
        if cached.get("call_id") != row["call_id"] or cached.get("request_hash") != row["request_hash"]:
            raise LedgerError("cached_response_identity_mismatch")
        result = cached.get("result")
        if not isinstance(result, dict):
            self._consume(row, True)
            raise BudgetStop("unresolved_cached_request", call_id=row["call_id"])
        result_hash = _hash(result)
        if row["status"] == "reserved":
            # A crash after the response was fsynced but before ledger settlement.
            row = await self.ledger.finish(row["call_id"], usage=result.get("usage"),
                                           provider_model=result.get("model", ""),
                                           elapsed_seconds=cached.get("elapsed_seconds", 0),
                                           response_sha256=result_hash)
        elif row.get("response_sha256") != result_hash:
            raise LedgerError("cached_response_hash_mismatch")
        self._consume(row, True)
        self._check_usage(row)
        response = BudgetLLMResponse(**result)
        self.last_response = response
        return response

    async def _call(self, prompt: str, *, temperature: float, max_tokens: int,
                    system_prompt: str | None, response_format: dict | None,
                    logical_key: str, retry_index: int) -> BudgetLLMResponse:
        if self._closed:
            raise LedgerError("client_already_closed")
        estimate = self.estimate_request(prompt, system_prompt=system_prompt, max_tokens=max_tokens,
                                         response_format=response_format)
        effective = estimate["max_output_tokens"]
        if effective <= 0:
            raise BudgetStop("no_output_budget", input_tokens=estimate["input_tokens"],
                             remaining_tokens=None if self.token_cap is None else self.remaining_tokens)
        body = {"model": self.model, "messages": estimate["messages"],
                "temperature": temperature, "max_tokens": effective}
        if response_format:
            body["response_format"] = response_format
        if self.chat_template_kwargs:
            body["extra_body"] = {"chat_template_kwargs": self.chat_template_kwargs}
        request_hash = _hash({"body": body, "phase": self._phase, "fingerprint": self.fingerprint,
                              "requested_max_tokens": max_tokens,
                              "selector_reserve": self._selector_reserve,
                              "token_cap": self.token_cap})
        key = f"{logical_key}:attempt-{retry_index}"
        output_path = self.call_log_dir/f"{_hash(key)[:24]}.json"
        try:
            cache_path = str(output_path.resolve().relative_to(self.ledger.path.parent.resolve()))
        except ValueError:
            cache_path = str(output_path.resolve())
        row, cached = await self.ledger.reserve(
            owner=self.owner, token_cap=self.token_cap, fingerprint=self.fingerprint,
            request_key=key, request_hash=request_hash, phase=self._phase,
            input_tokens=estimate["input_tokens"], max_output=effective,
            requested_max_output=max_tokens, selector_reserve=self._selector_reserve,
            cache_file=cache_path, retry_index=retry_index,
        )
        if cached:
            return await self._cached_response(row)
        log = {"call_id": row["call_id"], "request_key": key, "request_hash": request_hash,
               "request": body, "reservation": row, "status": "reserved"}
        try:
            _write_json(output_path, _safe(log))
        except Exception as exc:
            raise LedgerError(f"request_log_write_failed:{type(exc).__name__}") from None
        started = time.monotonic()
        try:
            raw = await self.client.chat.completions.create(**body)
        except BaseException as exc:
            elapsed = time.monotonic()-started
            row = await asyncio.shield(self.ledger.finish(row["call_id"], usage=None,
                                                       elapsed_seconds=elapsed, error_type=type(exc).__name__))
            self._consume(row, False)
            log.update(status=row["status"], elapsed_seconds=elapsed, error_type=type(exc).__name__)
            try:
                _write_json(output_path, _safe(log))
            except Exception:
                pass
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit, BudgetStop, LedgerError)):
                raise
            raise BudgetStop("unknown_provider_outcome", call_id=row["call_id"],
                             error_type=type(exc).__name__) from None
        elapsed = time.monotonic()-started
        usage = _plain(getattr(raw, "usage", None)) or {}
        if not isinstance(usage, dict):
            usage = {}
        model = str(getattr(raw, "model", "") or "")
        try:
            content = raw.choices[0].message.content or ""
        except (AttributeError, IndexError, TypeError):
            content = ""
        result = {"content": content, "model": model, "usage": usage, "raw": _safe(raw)}
        result_hash = _hash(result)
        log.update(status="response_received", result=result, elapsed_seconds=elapsed)
        # Response cache before settlement makes the tiny crash window recoverable.
        try:
            _write_json(output_path, _safe(log))
        except Exception as exc:
            raise LedgerError(f"response_log_write_failed:{type(exc).__name__}") from None
        row = await self.ledger.finish(row["call_id"], usage=usage, provider_model=model,
                                       elapsed_seconds=elapsed, response_sha256=result_hash)
        self._consume(row, False)
        self._check_usage(row)
        response = BudgetLLMResponse(content=content, model=model, usage=usage, raw=raw)
        self.last_response = response
        return response

    async def call_json(self, prompt: str, *, temperature: float = 0.0,
                        max_tokens: int = 4096, system_prompt: Optional[str] = None,
                        retries: int = 2, request_key: str | None = None) -> dict:
        logical = self._logical_key(request_key)
        configured = self.selector_json_attempts if self._phase == "selector" else self.json_attempts
        attempts = min(configured, max(1, int(retries)+1))
        for attempt in range(attempts):
            response = await self._call(prompt, temperature=temperature, max_tokens=max_tokens,
                                        system_prompt=system_prompt, response_format={"type": "json_object"},
                                        logical_key=logical, retry_index=attempt)
            parsed = OpenAIClient._extract_json(response.content)
            outcome = "dict" if isinstance(parsed, dict) else ("invalid_json" if parsed is None else "schema_not_object")
            await self.ledger.record_parse(self.last_call_record["call_id"], outcome)
            if isinstance(parsed, dict):
                return parsed
        # Preserve the repository client's exhausted-parse fallback. All attempts
        # remain in the budget and parse audit; selectors can reject {} explicitly.
        return {}

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self.client.close()

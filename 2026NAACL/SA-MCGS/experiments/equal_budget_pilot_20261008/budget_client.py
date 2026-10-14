"""GPT-4o client with a durable, shared, fail-closed pilot budget.

Only the SDK call in ``BudgetClient._call`` can send a request. A fsynced
reservation always precedes it. Missing usage, failed requests and interrupted
requests retain their full reservations, including after restarting the runner.
Prices are deliberately uncached list prices: $2.50/M input and $10.00/M output.
The UTF-8 reservation assumes text-only Chat Completions and includes 1,024
framing tokens plus 64 per message; provider usage is audited against that bound.
"""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import math
import os
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import tiktoken
from openai import AsyncOpenAI

from src.llm.base import BaseLLMClient, LLMResponse
from src.llm.openai_client import OpenAIClient


NANODOLLARS = 1_000_000_000
INPUT_NANODOLLARS_PER_TOKEN = 2_500
OUTPUT_NANODOLLARS_PER_TOKEN = 10_000
MAX_OUTPUT_TOKENS = 12000
MAX_PILOT_USD = Decimal("15")


class BudgetStop(BaseException):
    """Stop the search; intentionally bypasses its ``except Exception`` fallback."""

    def __init__(self, reason: str, **details: Any):
        self.reason = reason
        self.details = details
        super().__init__(f"budget_stop:{reason}")


class LedgerError(BaseException):
    """Durability/configuration errors must also stop rather than become scores."""


class ProviderCallError(Exception):
    """Safe provider failure without SDK error text, headers, URLs or secrets."""


class BudgetLLMResponse(LLMResponse):
    # The repository base annotates usage as dict[str, int]. Provider usage also
    # contains cached-token and reasoning-token nested details, so preserve them.
    usage: dict[str, Any] = {}


def _dollars(nanos: int) -> float:
    return nanos / NANODOLLARS


def _cost(prompt_tokens: int, completion_tokens: int) -> int:
    return (prompt_tokens * INPUT_NANODOLLARS_PER_TOKEN
            + completion_tokens * OUTPUT_NANODOLLARS_PER_TOKEN)


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # Do not use repr: SDK objects can contain request headers and credentials.
    return {"object_type": type(value).__name__}


def _safe(value: Any, api_key: str | None = None) -> Any:
    value = _plain(value)
    if isinstance(value, dict):
        forbidden = {"authorization", "api_key", "apikey", "access_token",
                     "headers", "request_headers", "response_headers"}
        return {k: _safe(v, api_key) for k, v in value.items()
                if k.lower() not in forbidden}
    if isinstance(value, list):
        return [_safe(v, api_key) for v in value]
    if isinstance(value, str) and api_key:
        return value.replace(api_key, "[REDACTED]")
    return value


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class GlobalLedger:
    """One shared ledger per paid pilot; ``summary`` and lifecycle are async.

    A lifetime OS lock excludes a second runner from using the same ledger.
    Every API attempt has its own reservation; recovery never erases an attempt.
    """

    def __init__(self, path: str | Path, cap_usd: float = 15.0):
        amount = Decimal(str(cap_usd))
        if not amount.is_finite() or amount <= 0 or amount > MAX_PILOT_USD:
            raise ValueError("Pilot cap must be positive and no greater than $15")
        self.path = Path(path)
        self.cap_nanos = int(amount * NANODOLLARS)
        self._lock = asyncio.Lock()
        self._file_lock = None
        self._initialized = False
        self._closed = False
        self._calls: dict[str, dict] = {}
        self._owner_caps: dict[tuple[str, str], int] = {}
        self._recovered_unresolved: set[str] = set()

    def _append(self, event: dict) -> None:
        event = {"time_unix": time.time(), **event}
        encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"),
                             allow_nan=False) + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(encoded)
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
        expected_header = {
            "event": "header", "version": 1, "cap_nanos": self.cap_nanos,
            "input_nanos_per_token": INPUT_NANODOLLARS_PER_TOKEN,
            "output_nanos_per_token": OUTPUT_NANODOLLARS_PER_TOKEN,
            "model": "gpt-4o",
        }
        if not self.path.exists() or self.path.stat().st_size == 0:
            self._append(expected_header)
            return
        try:
            data = self.path.read_bytes()
            # Fail closed even for a truncated final line. Never silently discard
            # a reservation that might already have reached the provider.
            if not data.endswith(b"\n"):
                raise LedgerError("ledger_truncated_final_record")
            events = [json.loads(line) for line in data.splitlines()]
            header = events[0]
            if any(header.get(k) != v for k, v in expected_header.items()):
                raise LedgerError("ledger_header_price_or_cap_mismatch")
            for event in events[1:]:
                call_id = event["call_id"]
                if event["event"] == "reserve":
                    if call_id in self._calls:
                        raise LedgerError("duplicate_reservation")
                    owner = (event["case_id"], event["method"])
                    prior_cap = self._owner_caps.get(owner, event["token_cap"])
                    if prior_cap != event["token_cap"]:
                        raise LedgerError("owner_token_cap_changed")
                    self._owner_caps[owner] = prior_cap
                    self._calls[call_id] = {**event, "status": "reserved"}
                elif event["event"] == "finish":
                    record = self._calls[call_id]
                    if record["status"] != "reserved":
                        raise LedgerError("duplicate_completion")
                    record.update(event)
                else:
                    raise LedgerError("unknown_ledger_event")
            self._recovered_unresolved = {
                key for key, row in self._calls.items()
                if row["status"] != "completed_with_usage"
            }
        except LedgerError:
            raise
        except Exception as exc:
            raise LedgerError(f"ledger_replay_failed:{type(exc).__name__}") from None

    @staticmethod
    def _accounted_nanos(row: dict) -> int:
        return (row["actual_nanos"] if row["status"] == "completed_with_usage"
                else row["reserved_nanos"])

    @staticmethod
    def _accounted_tokens(row: dict) -> int:
        return (row["actual_total_tokens"] if row["status"] == "completed_with_usage"
                else row["reserved_tokens"])

    def owner_records(self, case_id: str, method: str) -> list[dict]:
        return [r for r in self._calls.values()
                if r["case_id"] == case_id and r["method"] == method]

    def owner_summary(self, case_id: str, method: str) -> dict:
        return self._summary(self.owner_records(case_id, method))

    def _summary(self, records: list[dict]) -> dict:
        complete = [r for r in records if r["status"] == "completed_with_usage"]
        held = [r for r in records if r["status"] != "completed_with_usage"]
        actual_nanos = sum(r["actual_nanos"] for r in complete)
        held_nanos = sum(r["reserved_nanos"] for r in held)
        return {
            "calls": len(records), "completed_with_usage": len(complete),
            "held_calls": len(held),
            "unknown_failure_calls": sum(r["status"] == "unknown_failure" for r in records),
            "missing_usage_calls": sum(r["status"] == "completed_without_usage" for r in records),
            "pending_calls": sum(r["status"] == "reserved" for r in records),
            "recovered_unresolved_calls": sum(r["call_id"] in self._recovered_unresolved for r in records),
            "retry_calls": sum(r.get("retry_index", 0) > 0 for r in records),
            "prompt_tokens": sum(r["prompt_tokens"] for r in complete),
            "completion_tokens": sum(r["completion_tokens"] for r in complete),
            "total_tokens": sum(r["actual_total_tokens"] for r in complete),
            "held_tokens": sum(r["reserved_tokens"] for r in held),
            "accounted_tokens": sum(self._accounted_tokens(r) for r in records),
            "actual_usd": _dollars(actual_nanos), "held_usd": _dollars(held_nanos),
            "accounted_usd": _dollars(actual_nanos + held_nanos),
            "reservation_bound_violations": sum(bool(r.get("reservation_bound_exceeded")) for r in records),
            "price_usd_per_million": {"input": 2.5, "output": 10.0},
        }

    async def summary(self) -> dict:
        await self.initialize()
        async with self._lock:
            result = self._summary(list(self._calls.values()))
            accounted = sum(self._accounted_nanos(r) for r in self._calls.values())
            return {**result, "cap_usd": _dollars(self.cap_nanos),
                    "remaining_usd": _dollars(max(0, self.cap_nanos - accounted))}

    async def reserve(self, *, case_id: str, method: str, token_cap: int,
                      selector_reserve: int, phase: str, input_upper: int,
                      estimated_input: int, max_output: int, prompt_hash: str,
                      retry_index: int = 0) -> dict:
        await self.initialize()
        async with self._lock:
            if any(r.get("reservation_bound_exceeded") for r in self._calls.values()):
                raise BudgetStop("provider_exceeded_reservation_bound")
            owner = (case_id, method)
            if self._owner_caps.get(owner, token_cap) != token_cap:
                raise LedgerError("owner_token_cap_changed")
            records = self.owner_records(case_id, method)
            used_tokens = sum(self._accounted_tokens(r) for r in records)
            reserved_tokens = estimated_input + max_output
            held_for_selector = 0 if phase == "selector" else selector_reserve
            if used_tokens + reserved_tokens + held_for_selector > token_cap:
                raise BudgetStop("tokens", case_id=case_id, method=method,
                                 accounted_tokens=used_tokens,
                                 requested_tokens=reserved_tokens,
                                 selector_reserve=held_for_selector, token_cap=token_cap)
            reserved_nanos = _cost(input_upper, max_output)
            committed = sum(self._accounted_nanos(r) for r in self._calls.values())
            if committed + reserved_nanos > self.cap_nanos:
                raise BudgetStop("global_dollars", remaining_usd=_dollars(max(0, self.cap_nanos-committed)),
                                 requested_reserve_usd=_dollars(reserved_nanos))
            event = {
                "event": "reserve", "call_id": uuid.uuid4().hex,
                "case_id": case_id, "method": method, "phase": phase,
                "token_cap": token_cap, "selector_reserve": held_for_selector,
                "input_upper_tokens": input_upper,
                "estimated_input_tokens": estimated_input,
                "max_output_tokens": max_output, "reserved_tokens": reserved_tokens,
                "reserved_nanos": reserved_nanos, "prompt_sha256": prompt_hash,
                "retry_index": retry_index,
            }
            self._append(event)
            self._owner_caps[owner] = token_cap
            self._calls[event["call_id"]] = {**event, "status": "reserved"}
            return dict(event)

    async def finish(self, call_id: str, *, usage: dict | None,
                     error_type: str | None = None, provider_model: str = "") -> dict:
        async with self._lock:
            if not self._initialized or self._closed:
                raise LedgerError("ledger_unavailable_during_settlement")
            row = self._calls[call_id]
            if row["status"] != "reserved":
                raise LedgerError("attempt_already_settled")
            prompt = usage.get("prompt_tokens") if usage else None
            completion = usage.get("completion_tokens") if usage else None
            valid_usage = all(isinstance(n, int) and not isinstance(n, bool) and n >= 0
                              for n in (prompt, completion))
            event = {"event": "finish", "call_id": call_id,
                     "provider_model": provider_model, "usage": usage or {}}
            if valid_usage:
                total = usage.get("total_tokens")
                total = max(prompt + completion, total if isinstance(total, int) else 0)
                event.update(status="completed_with_usage", prompt_tokens=prompt,
                             completion_tokens=completion, actual_total_tokens=total,
                             actual_nanos=_cost(prompt, completion),
                             reservation_bound_exceeded=(prompt > row["input_upper_tokens"]
                                                         or completion > row["max_output_tokens"]))
            else:
                event.update(status="unknown_failure" if error_type else "completed_without_usage")
            if error_type:
                event["error_type"] = error_type
            self._append(event)
            row.update(event)
            return dict(row)

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
                 case_id: str, method: str, call_log_dir: str | Path,
                 token_cap: int = 160_000, provider_client: Any = None,
                 api_key: str | None = None, base_url: str | None = None,
                 model: str = "gpt-4o"):
        config = dict(config or {})
        model = config.get("model", model)
        if model != "gpt-4o":
            raise ValueError("This pilot client permits only gpt-4o")
        if not isinstance(token_cap, int) or token_cap <= 0:
            raise ValueError("token_cap must be a positive integer")
        config.update(model=model, max_retries=0)
        super().__init__(config)
        self.ledger = ledger
        self.case_id, self.method = str(case_id), str(method)
        self.call_log_dir = Path(call_log_dir)
        self.token_cap = token_cap
        self._phase = "candidate"
        self._selector_reserve = 0
        self._closed = False
        self._encoding = tiktoken.get_encoding("o200k_base")
        self._api_key = api_key if api_key is not None else os.environ.get(
            config.get("api_key_env", "OPENAI_API_KEY"), "")
        self.client = provider_client if provider_client is not None else AsyncOpenAI(
            api_key=self._api_key,
            base_url=base_url if base_url is not None else config.get("base_url"),
            timeout=self.timeout, max_retries=0,
        )
        self.last_usage: dict[str, Any] = {}
        self.last_response: BudgetLLMResponse | None = None
        self.last_call_record: dict | None = None

    @property
    def token_usage(self) -> dict:
        summary = self.ledger.owner_summary(self.case_id, self.method)
        return {k: summary[k] for k in ("prompt_tokens", "completion_tokens",
                                       "total_tokens", "held_tokens", "accounted_tokens")}

    @property
    def remaining_tokens(self) -> int:
        held = 0 if self._phase == "selector" else self._selector_reserve
        return max(0, self.token_cap - self.token_usage["accounted_tokens"] - held)

    def set_phase(self, phase: str) -> None:
        if phase not in {"candidate", "selector", "sa"}:
            raise ValueError("phase must be candidate, selector or sa")
        self._phase = phase

    def set_selector_reserve(self, tokens: int) -> None:
        if not isinstance(tokens, int) or tokens < 0 or tokens > self.token_cap:
            raise ValueError("selector reserve must be an integer within the token cap")
        self._selector_reserve = tokens

    def summary(self) -> dict:
        return {"case_id": self.case_id, "method": self.method, "model": self.model,
                "phase": self._phase, "token_cap": self.token_cap,
                "selector_reserve": self._selector_reserve,
                "remaining_tokens": self.remaining_tokens,
                **self.ledger.owner_summary(self.case_id, self.method)}

    def estimate_request(self, prompt: str, *, system_prompt: str | None = None,
                         max_tokens: int = 4096, response_format: dict | None = None) -> dict:
        if not isinstance(prompt, str) or (system_prompt is not None and not isinstance(system_prompt, str)):
            raise TypeError("Only text prompts are supported")
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        serialized = json.dumps({"messages": messages, "response_format": response_format},
                                ensure_ascii=False, separators=(",", ":"))
        tokenized = len(self._encoding.encode(serialized, disallowed_special=()))
        estimated_input = math.ceil(tokenized * 1.2) + 64
        input_upper = max(estimated_input, len(serialized.encode("utf-8")) + 1024 + 64 * len(messages))
        output = min(max_tokens, MAX_OUTPUT_TOKENS)
        return {"messages": messages, "estimated_input_tokens": estimated_input,
                "input_upper_tokens": input_upper, "max_output_tokens": output,
                "reserved_tokens": estimated_input + output,
                "reserve_usd": _dollars(_cost(input_upper, output)),
                "prompt_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest()}

    async def call(self, prompt: str, *, temperature: float = 0.0,
                   max_tokens: int = 4096, system_prompt: Optional[str] = None,
                   response_format: Optional[dict] = None) -> BudgetLLMResponse:
        return await self._call(prompt, temperature=temperature, max_tokens=max_tokens,
                                system_prompt=system_prompt, response_format=response_format,
                                retry_index=0)

    async def _call(self, prompt: str, *, temperature: float, max_tokens: int,
                    system_prompt: str | None, response_format: dict | None,
                    retry_index: int) -> BudgetLLMResponse:
        if self._closed:
            raise LedgerError("client_already_closed")
        request = self.estimate_request(prompt, system_prompt=system_prompt,
                                        max_tokens=max_tokens, response_format=response_format)
        reservation = await self.ledger.reserve(
            case_id=self.case_id, method=self.method, token_cap=self.token_cap,
            selector_reserve=self._selector_reserve, phase=self._phase,
            input_upper=request["input_upper_tokens"],
            estimated_input=request["estimated_input_tokens"],
            max_output=request["max_output_tokens"], prompt_hash=request["prompt_sha256"],
            retry_index=retry_index,
        )
        call_id = reservation["call_id"]
        output_path = self.call_log_dir / f"{call_id}.json"
        log = {"reservation": reservation, "request": {
            "model": self.model, "messages": request["messages"],
            "temperature": temperature, "requested_max_tokens": max_tokens,
            "max_tokens": request["max_output_tokens"], "response_format": response_format,
        }, "status": "reserved"}
        # If saving this record fails, no request is sent and the durable global
        # reservation remains held. Conservatism takes precedence over throughput.
        try:
            _write_json(output_path, _safe(log, self._api_key))
        except Exception as exc:
            raise LedgerError(f"call_log_write_failed:{type(exc).__name__}") from None
        kwargs = {"model": self.model, "messages": request["messages"],
                  "temperature": temperature, "max_tokens": request["max_output_tokens"]}
        if response_format:
            kwargs["response_format"] = response_format
        started = time.monotonic()
        try:
            response = await self.client.chat.completions.create(**kwargs)
        except BaseException as exc:
            # Never infer "free" from a timeout/transport/SDK error. The provider
            # may have generated tokens even when its usage never reached us.
            record = await asyncio.shield(self.ledger.finish(call_id, usage=None,
                                                           error_type=type(exc).__name__))
            self.last_call_record = record
            log.update(status=record["status"], error_type=type(exc).__name__,
                       elapsed_seconds=time.monotonic()-started, settlement=record)
            try:
                _write_json(output_path, _safe(log, self._api_key))
            except Exception:
                pass  # The fsynced ledger already preserves the financial hold.
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit, BudgetStop, LedgerError)):
                raise
            raise ProviderCallError(f"provider_error:{type(exc).__name__}") from None

        usage_object = getattr(response, "usage", None)
        usage = _plain(usage_object) if usage_object is not None else {}
        if not isinstance(usage, dict):
            usage = {}
        provider_model = str(getattr(response, "model", "") or "")
        record = await self.ledger.finish(call_id, usage=usage, provider_model=provider_model)
        self.last_usage = usage
        self.last_call_record = record
        raw = _safe(response, self._api_key)
        log.update(status=record["status"], usage=_safe(usage, self._api_key), raw_response=raw,
                   elapsed_seconds=time.monotonic()-started, settlement=record)
        try:
            _write_json(output_path, _safe(log, self._api_key))
        except Exception as exc:
            raise LedgerError(f"call_log_write_failed:{type(exc).__name__}") from None
        if record.get("reservation_bound_exceeded"):
            raise BudgetStop("provider_exceeded_reservation_bound", call_id=call_id)
        try:
            content = response.choices[0].message.content or ""
        except Exception:
            raise ProviderCallError("provider_response_schema_error") from None
        result = BudgetLLMResponse(content=content, model=provider_model, usage=usage, raw=response)
        self.last_response = result
        return result

    async def call_json(self, prompt: str, *, temperature: float = 0.0,
                        max_tokens: int = 4096, system_prompt: Optional[str] = None,
                        retries: int = 2) -> dict:
        # Legacy callers pass retries=2, which meant three requests. This pilot
        # permits at most one explicit recovery request, each independently gated.
        attempts = 1 + min(1, max(0, int(retries)))
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = await self._call(
                    prompt, temperature=temperature, max_tokens=max_tokens,
                    system_prompt=system_prompt, response_format={"type": "json_object"},
                    retry_index=attempt,
                )
                parsed = OpenAIClient._extract_json(response.content)
                if isinstance(parsed, dict):
                    return parsed
                last_error = ProviderCallError("provider_json_parse_error")
            except ProviderCallError as exc:
                last_error = exc
        raise last_error or ProviderCallError("provider_json_parse_error")

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self.client.close()

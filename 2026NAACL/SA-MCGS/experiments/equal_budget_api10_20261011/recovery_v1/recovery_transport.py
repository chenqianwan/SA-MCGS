"""Explicit HTTP-503 recovery without modifying the frozen API experiment.

Use a snapshot ledger/calls directory, never the original run directory. Original
request keys and client fingerprints are unchanged. A JSON attempt has at most
three transport attempts: its original request, then :transport1 and :transport2.
Every 503 reservation remains charged against the token ceiling. Unknown network
outcomes, missing usage, and other HTTP errors are never retried here.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ORIGINAL_CLIENT_PATH = Path(__file__).resolve().parent.parent / "api_budget_client.py"
ORIGINAL_CLIENT_SHA256 = hashlib.sha256(ORIGINAL_CLIENT_PATH.read_bytes()).hexdigest()
_name = "_api10_original_paid_client_for_recovery"
if _name in sys.modules:
    original = sys.modules[_name]
else:
    _spec = importlib.util.spec_from_file_location(_name, ORIGINAL_CLIENT_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError("Cannot load frozen API client")
    original = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = original
    _spec.loader.exec_module(original)

BudgetStop = original.BudgetStop
LedgerError = original.LedgerError
BudgetLLMResponse = original.BudgetLLMResponse
ENDPOINT = original.ENDPOINT
TRANSPORT_SPEC = {
    "schema_version": "api10_transport_recovery.v1",
    "original_client_sha256": ORIGINAL_CLIENT_SHA256,
    "retryable_status": "unknown_failure",
    "retryable_http_status": 503,
    "maximum_transport_attempts_per_json_attempt": 3,
    "original_request_counts_as_attempt": True,
    "backoff_seconds": [30, 90],
    "extra_key_components": ["transport1", "transport2"],
    "original_fingerprint_unchanged": True,
    "reservation_policy": "retain_every_503_reservation_in_token_ceiling",
    "timeout_connection_missing_usage_or_other_http": "stop_without_retry",
    "sdk_retries": 0,
}


def is_explicit_503(row: dict | None) -> bool:
    return bool(row and row.get("status") == "unknown_failure" and row.get("http_status") == 503)


class GlobalLedger(original.GlobalLedger):
    """Original accounting/header plus an immutable recovery-policy sidecar."""

    def __init__(self, path: str | Path):
        super().__init__(path)
        self.transport_spec_path = self.path.with_suffix(self.path.suffix + ".transport_spec.json")
        self.transport_events_path = self.path.with_suffix(self.path.suffix + ".transport_events.jsonl")
        self._transport_sidecar_ready = False
        self._transport_event_keys: set[tuple] = set()

    async def initialize(self) -> "GlobalLedger":
        await super().initialize()
        async with self._lock:
            if self._transport_sidecar_ready:
                return self
            try:
                if self.transport_spec_path.exists():
                    if json.loads(self.transport_spec_path.read_text()) != TRANSPORT_SPEC:
                        raise LedgerError("transport_recovery_policy_changed")
                else:
                    original._write_json(self.transport_spec_path, TRANSPORT_SPEC)
                if self.transport_events_path.exists():
                    data = self.transport_events_path.read_bytes()
                    if data and not data.endswith(b"\n"):
                        raise LedgerError("transport_audit_truncated")
                    for line in data.splitlines():
                        event = json.loads(line)
                        self._transport_event_keys.add((event["failed_call_id"], event["next_request_key"]))
            except LedgerError:
                raise
            except Exception as exc:
                raise LedgerError(f"transport_sidecar_failed:{type(exc).__name__}") from None
            self._transport_sidecar_ready = True
            return self

    async def audit_transport_retry(self, row: dict, next_key: str, delay: int) -> None:
        await self.initialize()
        async with self._lock:
            event_key = (row["call_id"], next_key)
            if event_key in self._transport_event_keys:
                return
            event = {"event": "explicit_503_transport_successor", "time_unix": time.time(),
                     "failed_call_id": row["call_id"], "failed_request_key": row["request_key"],
                     "next_request_key": next_key, "retained_tokens": row["reserved_tokens"],
                     "http_status": 503, "backoff_seconds": delay,
                     "policy_sha256": original._hash(TRANSPORT_SPEC)}
            try:
                with self.transport_events_path.open("a", encoding="utf-8") as handle:
                    handle.write(original._base._serialized(event) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception as exc:
                raise LedgerError(f"transport_audit_write_failed:{type(exc).__name__}") from None
            self._transport_event_keys.add(event_key)

    async def reserve(self, *, owner: tuple[str, str, str], token_cap: int | None,
                      fingerprint: str, request_key: str, request_hash: str, phase: str,
                      input_tokens: int, max_output: int, selector_reserve: int,
                      requested_max_output: int, cache_file: str, retry_index: int) -> tuple[dict, bool]:
        # Same frozen reserve protocol, except explicit returned 503s may precede
        # a new transport attempt. Their held reservations are still summed.
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
            if any(r.get("budget_overrun") for r in records):
                raise BudgetStop("budget_overrun", token_cap=token_cap)
            if any(r.get("usage_issues") for r in records):
                raise BudgetStop("invalid_provider_usage")
            if any(r["status"] != "completed_with_usage" and not is_explicit_503(r) for r in records):
                raise BudgetStop("unresolved_prior_request")
            used = sum(self.accounted_tokens(r) for r in records)
            reserve = input_tokens + max_output
            selector = 0 if phase == "selector" else selector_reserve
            if token_cap is not None and used + reserve + selector > token_cap:
                raise BudgetStop("tokens", accounted_tokens=used, request_tokens=reserve,
                                 selector_reserve=selector, token_cap=token_cap)
            if max_output <= 0:
                raise BudgetStop("no_output_budget")
            row = {"event": "reserve", "call_id": uuid.uuid4().hex, "owner": list(owner),
                   "request_key": request_key, "request_hash": request_hash, "phase": phase,
                   "input_tokens": input_tokens, "max_output_tokens": max_output,
                   "requested_max_output_tokens": requested_max_output,
                   "reserved_tokens": reserve, "selector_reserve": selector,
                   "retry_index": retry_index, "cache_file": cache_file}
            self._append(row)
            self._calls[row["call_id"]] = {**row, "status": "reserved"}
            self._keys[key] = row["call_id"]
            return dict(self._calls[row["call_id"]]), False

    def _summary(self, rows: list[dict]) -> dict:
        summary = super()._summary(rows)
        http503 = [r for r in rows if is_explicit_503(r)]
        return {**summary, "explicit_503_calls": len(http503),
                "retained_503_tokens": sum(r["reserved_tokens"] for r in http503),
                "transport_successor_calls": sum(":transport" in r["request_key"] for r in rows),
                "transport_recovery_policy": TRANSPORT_SPEC}


class BudgetClient(original.BudgetClient):
    async def _transport_sleep(self, seconds: int) -> None:
        """Separate method permits offline tests to replace waiting, never the policy."""
        await asyncio.sleep(seconds)

    async def _call(self, prompt: str, *, temperature: float, max_tokens: int,
                    system_prompt: str | None, response_format: dict | None,
                    logical_key: str, retry_index: int) -> BudgetLLMResponse:
        for transport in range(3):
            actual_logical_key = logical_key if transport == 0 else f"{logical_key}:transport{transport}"
            expected_key = f"{actual_logical_key}:attempt-{retry_index}"
            try:
                return await super()._call(
                    prompt, temperature=temperature, max_tokens=max_tokens,
                    system_prompt=system_prompt, response_format=response_format,
                    logical_key=actual_logical_key, retry_index=retry_index)
            except BudgetStop as exc:
                if transport > 0 and exc.reason in {"tokens", "no_output_budget", "token_cap_exhausted"}:
                    raise BudgetStop("transport_budget_exhausted", token_cap=self.token_cap,
                                     accounted_tokens=self.token_usage["accounted_tokens"]) from None
                row = self.last_call_record
                if not is_explicit_503(row) or row.get("request_key") != expected_key:
                    raise
                if transport == 2:
                    raise BudgetStop("http503_transport_attempts_exhausted", attempts=3,
                                     call_id=row["call_id"], http_status=503) from None
                delay = TRANSPORT_SPEC["backoff_seconds"][transport]
                next_key = f"{logical_key}:transport{transport+1}:attempt-{retry_index}"
                await self.ledger.audit_transport_retry(row, next_key, delay)
                # Already completed successors are replayed immediately. A new
                # paid request waits even when recovering an old 503 reservation.
                if (*self.owner, next_key) not in self.ledger._keys:
                    await self._transport_sleep(delay)

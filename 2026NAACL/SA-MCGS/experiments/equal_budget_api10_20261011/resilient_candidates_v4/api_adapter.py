"""Candidate-level service isolation using the frozen baseline's error branch.

Do not raise ValueError inside LEA: its window evaluator swallows Exception and
substitutes scores. Service BudgetStop crosses that evaluator, and a wrapper
around the complete candidate converts it to CandidateServiceFailure. The
unchanged baseline then records and discards the entire candidate. Selector,
budget, missing-usage and durability failures are never converted.
"""
from __future__ import annotations
import functools
import importlib.util
import json
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

GUARD_PATH = Path(__file__).resolve().parent.parent / "pending_v2/budget_guard.py"
_name = "_api10_pending_guard_for_candidate_isolation"
if _name in sys.modules:
    guard = sys.modules[_name]
else:
    _spec = importlib.util.spec_from_file_location(_name, GUARD_PATH)
    guard = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = guard
    _spec.loader.exec_module(guard)
original = guard.original
BudgetStop, LedgerError = guard.BudgetStop, guard.LedgerError
selector_extra_reserve = guard.selector_extra_reserve


class CandidateServiceFailure(ValueError):
    """Raised only outside a complete candidate, caught by frozen baseline()."""


class GlobalLedger(guard.GlobalLedger):
    def __init__(self, path):
        super().__init__(path)
        self._safe_error_details = {}

    def _append(self, event):
        if event.get("event") == "finish" and event.get("call_id") in self._safe_error_details:
            event.update(self._safe_error_details.pop(event["call_id"]))
        super()._append(event)

    async def reserve(self, *, owner, token_cap, fingerprint, request_key, request_hash, phase,
                      input_tokens, max_output, selector_reserve, requested_max_output,
                      cache_file, retry_index):
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
            # An ended failure is retained at its full reservation but does not
            # prevent sampling the next independent candidate. In-flight and
            # completed-without-usage records still block new paid requests.
            if any(r["status"] not in {"completed_with_usage", "unknown_failure"} for r in records):
                raise BudgetStop("unresolved_prior_request")
            used = sum(self.accounted_tokens(r) for r in records)
            thinking = guard._allowance(owner[1], phase)
            reserve = input_tokens + max_output + thinking
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
                   "thinking_token_reserve": thinking, "reserved_tokens": reserve,
                   "selector_reserve": selector_reserve, "retry_index": retry_index,
                   "cache_file": cache_file}
            self._append(row)
            self._calls[row["call_id"]] = {**row, "status": "reserved"}
            self._keys[key] = row["call_id"]
            return dict(self._calls[row["call_id"]]), False


class BudgetClient(guard.BudgetClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        path = self.ledger.path.parent / "migration_cancelled_call_ids.json"
        self.migration_cancelled_call_ids = set(json.loads(path.read_text())) if path.exists() else set()
        provider = self.client
        async def safe_create(**body):
            try:
                return await provider.chat.completions.create(**body)
            except BaseException as error:
                def clean(value, limit):
                    value = original._safe(value, self._secret)
                    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", text)
                    text = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", text)
                    return text[:limit]
                pending = [r for r in self.ledger.owner_records(*self.owner) if r["status"] == "reserved"]
                if len(pending) == 1:
                    self.ledger._safe_error_details[pending[0]["call_id"]] = {
                        "error_message_safe": clean(str(error), 1000),
                        "error_body_safe": clean(getattr(error, "body", None), 2000)}
                raise
        self.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=safe_create)),
                                      close=provider.close)

    async def _call(self, prompt, *, temperature, max_tokens, system_prompt,
                    response_format, logical_key, retry_index):
        # Historical transport successors must replay exactly. New failures do
        # not create transport retries: discard that candidate and move on.
        historical = [logical_key]
        for n in (1, 2):
            candidate = f"{logical_key}:transport{n}"
            if (*self.owner, f"{candidate}:attempt-{retry_index}") in self.ledger._keys:
                historical.append(candidate)
        for position, actual_key in enumerate(historical):
            request_key = f"{actual_key}:attempt-{retry_index}"
            call_id = self.ledger._keys.get((*self.owner, request_key))
            if call_id and self.ledger._calls[call_id]["status"] == "unknown_failure":
                row = self.ledger._calls[call_id]
                path = Path(row["cache_file"])
                if not path.is_absolute():
                    path = self.ledger.path.parent / path
                try:
                    cached = json.loads(path.read_text())
                    if cached.get("call_id") != call_id or cached.get("request_hash") != row["request_hash"]:
                        raise ValueError("identity")
                except Exception:
                    raise LedgerError("failed_request_cache_missing_or_corrupt") from None
            try:
                return await original.BudgetClient._call(
                    self, prompt, temperature=temperature, max_tokens=max_tokens,
                    system_prompt=system_prompt, response_format=response_format,
                    logical_key=actual_key, retry_index=retry_index)
            except BudgetStop:
                row = self.last_call_record
                if (position + 1 < len(historical) and row
                        and row.get("request_key") == f"{actual_key}:attempt-{retry_index}"
                        and row.get("status") == "unknown_failure"):
                    continue
                raise


def _skippable_service_failure(client, error):
    row = client.last_call_record
    service_types = {"APIConnectionError", "APITimeoutError", "APIStatusError", "InternalServerError",
                     "BadRequestError", "RateLimitError", "AuthenticationError", "PermissionDeniedError",
                     "NotFoundError", "UnprocessableEntityError", "TimeoutError", "ConnectionError"}
    return (client._phase == "candidate" and row and row.get("status") == "unknown_failure"
            and error.reason in {"unknown_provider_outcome", "unresolved_cached_request", "unknown_provider_usage"}
            and (row.get("error_type") in service_types or
                 (row.get("error_type") == "CancelledError" and
                  row["call_id"] in client.migration_cancelled_call_ids)))


def wrap_candidate_functions(methods):
    """Call once after loading frozen methods_full.py; files remain unchanged."""
    def wrap(function):
        if getattr(function, "_candidate_service_boundary", False):
            return function
        @functools.wraps(function)
        async def invoke(client, *args, **kwargs):
            try:
                return await function(client, *args, **kwargs)
            except BudgetStop as error:
                if not _skippable_service_failure(client, error):
                    raise
                row = client.last_call_record
                raise CandidateServiceFailure(
                    f"candidate_service_failure:{row.get('error_type', 'unknown')}; "
                    f"http={row.get('http_status')}; request={row['request_key']}; "
                    f"retained_tokens={row['reserved_tokens']}") from None
        invoke._candidate_service_boundary = True
        return invoke
    methods.cost.run_lea = wrap(methods.cost.run_lea)
    methods.cost.battle.run_naive = wrap(methods.cost.battle.run_naive)

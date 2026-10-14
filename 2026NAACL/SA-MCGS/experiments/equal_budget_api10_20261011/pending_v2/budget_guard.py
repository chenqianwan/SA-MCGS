"""Gemini thinking reservations after exact replay of a frozen legacy prefix.

legacy_call_ids.json in each cell directory is immutable and explicitly lists
the snapshot's old call IDs. New requests reserve extra tokens without changing
the SDK output limits. These are heuristics, not provider-enforced thinking caps.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import sys
import uuid
from pathlib import Path

RECOVERY_PATH = Path(__file__).resolve().parent.parent / "recovery_v1/recovery_transport.py"
_name = "_api10_recovery_transport_for_guard"
if _name in sys.modules:
    transport = sys.modules[_name]
else:
    _spec = importlib.util.spec_from_file_location(_name, RECOVERY_PATH)
    transport = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = transport
    _spec.loader.exec_module(transport)
original = transport.original
BudgetStop, LedgerError = transport.BudgetStop, transport.LedgerError
GUARD_SPEC = {
    "schema_version": "api10_pending_thinking_guard.v1",
    "model": "gemini-2.5-pro", "candidate_extra_tokens": 8192,
    "selector_extra_tokens": 16384, "provider_output_caps_unchanged": True,
    "exact_provider_bound": False, "actual_provider_usage_settles_reservation": True,
    "activation": "after_all_explicit_legacy_call_ids_replayed",
    "recovery_source_sha256": hashlib.sha256(RECOVERY_PATH.read_bytes()).hexdigest(),
}


def _allowance(model, phase):
    if model != "gemini-2.5-pro":
        return 0
    return 16384 if phase == "selector" else 8192


def selector_extra_reserve(client) -> int:
    """Add to methods.judge_cost; never change candidate_lower_bound estimates."""
    return 16384 if client.model == "gemini-2.5-pro" and client.guard_active else 0


class GlobalLedger(transport.GlobalLedger):
    def __init__(self, path):
        super().__init__(path)
        self.legacy_path = self.path.parent / "legacy_call_ids.json"
        try:
            document = json.loads(self.legacy_path.read_text())
            values = document if isinstance(document, list) else document["legacy_call_ids"]
            if not isinstance(values, list) or any(not isinstance(x, str) for x in values) or len(values) != len(set(values)):
                raise ValueError("Invalid legacy IDs")
            self.legacy_call_ids = frozenset(values)
            self.legacy_file_sha256 = hashlib.sha256(self.legacy_path.read_bytes()).hexdigest()
        except Exception as exc:
            raise LedgerError(f"legacy_prefix_manifest_invalid:{type(exc).__name__}") from None
        self._guard_ready = False
        self.guard_spec_path = self.path.with_suffix(self.path.suffix + ".thinking_guard.json")

    async def initialize(self):
        await super().initialize()
        async with self._lock:
            if self._guard_ready:
                return self
            if not self.legacy_call_ids <= self._calls.keys():
                raise LedgerError("legacy_prefix_call_missing_from_snapshot")
            spec = {**GUARD_SPEC, "legacy_call_ids_sha256": self.legacy_file_sha256,
                    "legacy_call_count": len(self.legacy_call_ids)}
            if self.guard_spec_path.exists():
                if json.loads(self.guard_spec_path.read_text()) != spec:
                    raise LedgerError("thinking_guard_policy_changed")
            else:
                original._write_json(self.guard_spec_path, spec)
            self._guard_ready = True
            return self

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
            if any(r["status"] != "completed_with_usage" and not transport.is_explicit_503(r) for r in records):
                raise BudgetStop("unresolved_prior_request")
            used = sum(self.accounted_tokens(r) for r in records)
            thinking = _allowance(owner[1], phase)
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


class BudgetClient(transport.BudgetClient):
    @property
    def guard_active(self):
        return self.ledger.legacy_call_ids <= self._seen_calls

    def _consume(self, row, cached):
        was_active = self.guard_active
        super()._consume(row, cached)
        # An old 503 can be the last legacy request. Its new transport successor
        # occurs before baseline() recomputes the selector reserve. Add the one
        # missing future-selector margin at that exact boundary, once only.
        if (not was_active and self.guard_active and self.model == "gemini-2.5-pro"
                and self._phase != "selector" and self._selector_reserve > 0):
            self._selector_reserve += 16384

    def estimate_request(self, prompt, *, system_prompt=None, max_tokens=4096,
                         response_format=None, respect_budget=True):
        if not self.guard_active or not respect_budget or self.model != "gemini-2.5-pro":
            return super().estimate_request(prompt, system_prompt=system_prompt, max_tokens=max_tokens,
                                             response_format=response_format, respect_budget=respect_budget)
        estimate = super().estimate_request(prompt, system_prompt=system_prompt, max_tokens=max_tokens,
                                             response_format=response_format, respect_budget=False)
        thinking = _allowance(self.model, self._phase)
        estimate["max_output_tokens"] = max(0, min(estimate["max_output_tokens"],
            int(self.remaining_tokens) - estimate["input_tokens"] - thinking))
        estimate["thinking_token_reserve"] = thinking
        estimate["reserved_tokens"] = estimate["input_tokens"] + estimate["max_output_tokens"] + thinking
        estimate["requested_tokens"] += thinking
        return estimate

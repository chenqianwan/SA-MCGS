#!/usr/bin/env python3
"""Frozen LEA completion with a shared USD cap and exact per-call resume.

No paid calls in --mode preflight. --mode smoke runs the fixed first case for
each selected model; those same results count in --mode run. Parallel processes
use --shard-count N --shard-index I; every case and budget operation has a file
lock. Existing successful responses are replayed verbatim after interruption.
Successful or strict-failure cases are never repeated. A provider failure can
only continue with --resume-provider-failures, which resumes its missing call.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
from contextlib import contextmanager
from decimal import Decimal, ROUND_CEILING
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from emnlp2026_discussion import run_lea_full_baseline as lea
from emnlp2026_discussion import run_cost_audit_clean as cost
from src.llm.base import LLMResponse

NANODOLLARS = Decimal("1000000000")


class RunStop(BaseException):
    """Must bypass existing catch-and-fallback handling in the LEA evaluator."""


class BudgetStop(RunStop):
    pass


class ProviderFailure(RunStop):
    pass


class ProviderSnapshotMismatch(RunStop):
    pass


class StrictFailure(RunStop):
    pass


class IntegrityStop(RunStop):
    pass


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nd(value: Any) -> int:
    return int((Decimal(str(value)) * NANODOLLARS).to_integral_value(rounding=ROUND_CEILING))


def dollars(value: int) -> float:
    return float(Decimal(value) / NANODOLLARS)


def append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    # Refuse incomplete/corrupt records; never silently discard a charge.
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@contextmanager
def locked(path: Path, nonblocking: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class BudgetLedger:
    """Integer-dollar accounting; unresolved reservations always stay charged."""

    def __init__(self, output_dir: Path, pricing_path: Path):
        self.output_dir = output_dir
        self.pricing_path = pricing_path
        self.pricing_bytes_hash = file_digest(pricing_path)
        self.pricing = json.loads(pricing_path.read_text())
        self.cap = nd(self.pricing["budget_usd"])
        if self.cap <= 0 or self.cap > nd(50):
            raise ValueError("This run is authorized for at most USD 50")
        self.path = output_dir / "budget_ledger.jsonl"
        self.lock_path = output_dir / "locks" / "budget.lock"
        self.halt_path = output_dir / "budget_halt.json"

    def assert_frozen(self):
        if file_digest(self.pricing_path) != self.pricing_bytes_hash:
            raise IntegrityStop("Frozen pricing changed; stop before further paid calls")

    def _state(self) -> dict:
        events = read_jsonl(self.path)
        reserved, settled = {}, {}
        for event in events:
            if event["pricing_sha256"] != self.pricing_bytes_hash:
                raise IntegrityStop("Ledger pricing differs from frozen pricing")
            rid = event["reservation_id"]
            if event["event"] == "reserve":
                if rid in reserved:
                    raise IntegrityStop("Duplicate budget reservation")
                reserved[rid] = event
            elif event["event"] == "settle":
                if rid in settled or rid not in reserved:
                    raise IntegrityStop("Unmatched or duplicate budget settlement")
                settled[rid] = event
        actual = sum(v["charged_nd"] for v in settled.values())
        pending = sum(v["reserved_nd"] for key, v in reserved.items() if key not in settled)
        return {"actual_nd": actual, "pending_nd": pending, "committed_nd": actual + pending,
                "reservations": reserved, "settlements": settled}

    def _write_status(self, state):
        cost.atomic_write_json(self.output_dir / "budget_status.json", {
            "updated_at": cost.now_iso(), "budget_usd": dollars(self.cap),
            "charged_or_conservatively_assumed_usd": dollars(state["actual_nd"]),
            "unresolved_reservations_usd": dollars(state["pending_nd"]),
            "committed_upper_bound_usd": dollars(state["committed_nd"]),
            "remaining_usd": dollars(max(0, self.cap - state["committed_nd"])),
            "api_reservations": len(state["reservations"]),
            "settled_calls": len(state["settlements"]),
            "pricing_sha256": self.pricing_bytes_hash,
            "note": "Uncertain failures retain their full reserved cost; this is not a provider invoice.",
        })

    def snapshot(self) -> dict:
        with locked(self.lock_path):
            state = self._state()
            self._write_status(state)
            return {key: value for key, value in state.items() if key.endswith("_nd")}

    def reserve(self, amount_nd: int, context: dict) -> str:
        with locked(self.lock_path):
            if self.halt_path.exists():
                raise IntegrityStop("Shared accounting/provider halt requires review before further paid calls")
            self.assert_frozen()
            state = self._state()
            if state["committed_nd"] + amount_nd > self.cap:
                self._write_status(state)
                raise BudgetStop("USD 50 shared cap: next call cannot be fully reserved")
            rid = uuid.uuid4().hex
            append(self.path, {"event": "reserve", "at": cost.now_iso(),
                "reservation_id": rid, "reserved_nd": amount_nd,
                "reserved_usd": dollars(amount_nd), "pricing_sha256": self.pricing_bytes_hash,
                **context})
            self._write_status(self._state())
            return rid

    def settle(self, rid: str, charged_nd: int, reason: str, **extra):
        with locked(self.lock_path):
            state = self._state()
            if rid in state["settlements"]:
                raise IntegrityStop("Budget reservation already settled")
            reserve = state["reservations"][rid]
            append(self.path, {"event": "settle", "at": cost.now_iso(),
                "reservation_id": rid, "charged_nd": charged_nd,
                "charged_usd": dollars(charged_nd), "reason": reason,
                "pricing_sha256": self.pricing_bytes_hash, **extra})
            state = self._state()
            self._write_status(state)
            if charged_nd > reserve["reserved_nd"]:
                self._halt("Provider usage exceeded conservative reservation")
                raise IntegrityStop("Provider usage exceeded conservative reservation; stop and reconcile pricing")

    def _halt(self, reason: str):
        if not self.halt_path.exists():
            cost.atomic_write_json(self.halt_path, {"at": cost.now_iso(), "reason": reason})

    def halt(self, reason: str):
        with locked(self.lock_path):
            self._halt(reason)


def token_cost(route: dict, input_tokens: int, output_tokens: int) -> int:
    amount = (Decimal(input_tokens) * Decimal(str(route["input_usd_per_million"]))
              + Decimal(output_tokens) * Decimal(str(route["output_usd_per_million"]))) / Decimal(1000000)
    return nd(amount)


def completion_reserve_bound(route: dict, max_tokens: int) -> int:
    # XHub's Gemini usage includes thinking tokens beyond the visible-output
    # max_tokens. Reserve the documented separate thinking ceiling without
    # changing any actual request field or the experimental protocol.
    return max_tokens + (32768 if route["model_id"] == "gemini-2.5-pro" else 0)


def compatible_protocol_hashes(output_dir: Path, current_hash: str, *, for_terminal_results: bool = False) -> set[str]:
    allowed = {current_hash}
    path = output_dir / "protocol_amendments.json"
    if path.exists():
        for change in json.loads(path.read_text()):
            if (change.get("to_protocol_sha256") == current_hash
                and change.get("type") in ("budget_only", "adapter_compatibility")
                and not (for_terminal_results and change.get("type") == "adapter_compatibility")
                and change.get("api_request_and_scientific_protocol_unchanged") is True):
                allowed.add(change["from_protocol_sha256"])
    return allowed


def response_usage(raw_usage: dict) -> dict[str, int]:
    """Match the historical OpenAIClient's LLMResponse usage type.

    Provider metadata remains intact in the audit log, ledger and raw cache.
    Only the three integer token counts belong in LLMResponse.usage.
    """
    prompt = int(raw_usage["prompt_tokens"])
    completion = int(raw_usage["completion_tokens"])
    return {"prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": prompt + completion}


def validate_returned_model(requested: str, returned: str) -> None:
    lower, requested_lower = str(returned).lower(), requested.lower()
    if "deepseek-v3" in requested_lower:
        allowed = re.fullmatch(r"(?:deepseek/)?(?:deepseek-chat|deepseek-v3)", lower)
    elif "qwen" in requested_lower:
        allowed = re.fullmatch(r"(?:qwen/)?qwen-?2\.5-72b-instruct", lower)
    elif requested_lower == "gpt-4o":
        allowed = re.fullmatch(r"gpt-4o(?:-2024-(?:05-13|08-06|11-20))?", lower)
    elif requested_lower == "gemini-2.5-pro":
        allowed = re.fullmatch(r"(?:google/)?gemini-2\.5-pro", lower)
    else:
        allowed = lower == requested_lower
    if not allowed:
        raise ProviderSnapshotMismatch("Returned provider model is outside the frozen model's allowed aliases/snapshots; inspect logged returned_model")


class BudgetClient(cost.LoggingOpenAIClient):
    def __init__(self, *, route, ledger, output_dir, case, phase, protocol_hash, timeout):
        super().__init__({"provider": "openai", "model": route["model_id"],
            "base_url": route["base_url"], "api_key_env": route["api_key_env"],
            "timeout": timeout, "max_retries": 0},
            call_log_path=output_dir / "call_logs" / "llm_calls.jsonl",
            context={"run_id": output_dir.name, "case_id": case["case_id"],
                "case_order": case["case_order"], "model": case["model"],
                "domain": case["domain"], "scc_id": case["scc_id"],
                "scc_size": case["scc_size"], "template": case["template"],
                "method": "lea", "phase": phase, "case_concurrency": 1,
                "internal_concurrency": 1, "requested_model_id": route["model_id"],
                "base_url": route["base_url"], "protocol_sha256": protocol_hash})
        self.route, self.ledger = route, ledger
        self.compatible_protocols = compatible_protocol_hashes(output_dir, protocol_hash)
        self.cache_path = output_dir / "call_cache" / case["model"] / case["case_id"] / "responses.jsonl"
        self.cache = read_jsonl(self.cache_path)
        self._next = 0
        self.parse_exhausted_windows = 0

    async def call(self, prompt, *, temperature=0.0, max_tokens=4096,
                   system_prompt=None, response_format=None):
        request = {"prompt": prompt, "temperature": temperature, "max_tokens": max_tokens,
                   "system_prompt": system_prompt, "response_format": response_format,
                   "route": self.route, "protocol_sha256": self.context["protocol_sha256"]}
        signature = digest(request)
        index = self._next
        self._next += 1
        if index < len(self.cache):
            saved = self.cache[index]
            saved_protocol = saved["record"].get("protocol_sha256")
            saved_request = {**request, "protocol_sha256": saved_protocol}
            if (saved_protocol not in self.compatible_protocols
                or saved["request_sha256"] != digest(saved_request)
                or saved["call_index"] != index + 1):
                raise IntegrityStop("Resume call sequence does not match frozen successful response")
            validate_returned_model(self.model, saved["returned_model"])
            if not isinstance(saved["usage"].get("prompt_tokens"), int) or not isinstance(saved["usage"].get("completion_tokens"), int):
                raise IntegrityStop("Cached provider response has no auditable token usage")
            self.call_records.append({**saved["record"], "replayed_from_checkpoint": True})
            return LLMResponse(content=saved["content"], model=saved["returned_model"], usage=response_usage(saved["usage"]))

        # Byte-level bound is deliberately loose (one input token per UTF-8 byte,
        # plus 512 protocol tokens); reserve separate provider thinking tokens.
        input_bound = len(prompt.encode()) + len((system_prompt or "").encode()) + 512
        output_bound = completion_reserve_bound(self.route, max_tokens)
        reserve_nd = token_cost(self.route, input_bound, output_bound)
        context = {**self.context, "call_index": index + 1, "request_sha256": signature,
                   "input_token_upper_bound": input_bound, "max_tokens": max_tokens,
                   "completion_token_upper_bound": output_bound,
                   "additional_thinking_token_reserve": output_bound - max_tokens}
        rid = self.ledger.reserve(reserve_nd, context)
        t0 = time.time()
        record = {**context, "reservation_id": rid, "started_at": cost.now_iso(),
                  "prompt_chars": len(prompt), "system_prompt_chars": len(system_prompt or ""),
                  "temperature": temperature, "response_format": response_format, "ok": False}
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else [])
        messages.append({"role": "user", "content": prompt})
        kwargs = {"model": self.model, "messages": messages,
                  "temperature": temperature, "max_tokens": max_tokens}
        if response_format:
            kwargs["response_format"] = response_format
        try:
            raw = await self.client.chat.completions.create(**kwargs)
        except BaseException as exc:
            # Never serialize SDK exceptions: they may contain headers or keys.
            record.update({"ended_at": cost.now_iso(), "runtime_sec": time.time() - t0,
                "error_type": type(exc).__name__, "http_status": getattr(exc, "status_code", None),
                "charged_upper_bound_usd": dollars(reserve_nd), "charge_is_uncertain": True})
            append(self.call_log_path, record)
            self.call_records.append(record)
            self.ledger.settle(rid, reserve_nd, "provider_failure_or_interrupt_charge_unknown")
            if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
                raise
            raise ProviderFailure(f"Provider failure ({type(exc).__name__}, HTTP {getattr(exc, 'status_code', None)})") from None

        usage = raw.usage.model_dump() if raw.usage is not None else {}
        content = raw.choices[0].message.content if raw.choices else None
        valid_usage = isinstance(usage.get("prompt_tokens"), int) and isinstance(usage.get("completion_tokens"), int)
        charged = token_cost(self.route, usage["prompt_tokens"], usage["completion_tokens"]) if valid_usage else reserve_nd
        # Where a provider supplies an explicit USD amount, never undercount it.
        if isinstance(usage.get("cost"), (float, int)):
            charged = max(charged, nd(usage["cost"]))
        record.update({"ok": True, "ended_at": cost.now_iso(), "runtime_sec": time.time() - t0,
            "returned_model": raw.model, "usage": usage, "charged_usd": dollars(charged),
            "finish_reason": raw.choices[0].finish_reason if raw.choices else None,
            "charge_is_uncertain": not valid_usage})
        append(self.call_log_path, record)
        self.call_records.append(record)
        saved = {"call_index": index + 1, "request_sha256": signature,
                 "content": content or "", "returned_model": raw.model,
                 "usage": usage, "record": record}
        # Persist paid output before settling: a process crash can over-reserve,
        # but cannot cause an already received response to be paid for again.
        append(self.cache_path, saved)
        self.cache.append(saved)
        self.ledger.settle(rid, charged, "reported_usage" if valid_usage else "usage_missing_reserved_upper_bound",
                           usage=usage, returned_model=raw.model)
        validate_returned_model(self.model, raw.model)
        if not valid_usage:
            raise IntegrityStop("Provider omitted token usage; charge reserved and stop for reconciliation")
        return LLMResponse(content=content or "", model=raw.model, usage=response_usage(usage))

    async def call_json(self, prompt, *, temperature=0.0, max_tokens=4096,
                        system_prompt=None, retries=2):
        # Match the historical JSON-parse retry limit, accounting for every call.
        for attempt in range(retries + 1):
            response = await self.call(prompt, temperature=temperature, max_tokens=max_tokens,
                system_prompt=system_prompt, response_format={"type": "json_object"})
            parsed = self._extract_json(response.content)
            if parsed is not None:
                return parsed
            if attempt < retries:
                await asyncio.sleep(min(2 ** attempt, 8))
        # Historical OpenAIClient returns {} after three successful but
        # unparsable outputs, allowing the existing LEA missing-value fallback.
        self.parse_exhausted_windows += 1
        return {}


def load_plan(args, output_dir):
    plan_path = output_dir / "case_plan.json"
    with locked(output_dir / "locks" / "plan.lock"):
        if plan_path.exists():
            plan = json.loads(plan_path.read_text())
            if args.case_plan.exists():
                original = json.loads(args.case_plan.read_text())
                fields = ("case_id", "model", "case_uid", "planned_scc_fingerprint", "source_result_sha256", "source_sa_record_sha256")
                if [{k: c.get(k) for k in fields} for c in plan] != [{k: c.get(k) for k in fields} for c in original]:
                    raise IntegrityStop("Runtime plan differs from independently frozen preflight plan")
            return plan
        if args.case_plan.exists():
            plan = json.loads(args.case_plan.read_text())
        else:
            plan = []
            for order, row in enumerate(csv.DictReader(args.case_csv.open()), 1):
                canonical_order = int(row.get("main_case_order") or row.get("canonical_case_order") or order)
                case_id = lea.safe_token(f"{canonical_order:03d}_{row['model']}_{row['domain']}{row['scc_size']}_{row['scc_id']}_{row['template']}")
                plan.append({"case_order": canonical_order, "case_id": case_id,
                    "canonical_case_order": canonical_order, "canonical_case_id": case_id,
                    "model": row["model"], "domain": row["domain"], "scc_id": row["scc_id"],
                    "scc_size": int(row["scc_size"]), "template": row["template"],
                    "root": row.get("root"), "witness": row.get("witness"), "bridge": row.get("bridge"),
                    "affected_count": int(float(row.get("affected_count") or 0)),
                    "source_result_file": row["result_file"]})
        graphs = cost.load_graphs(plan)
        validation = cost.validate_case_plan(plan, graphs)
        cost.persist_case_plan(output_dir, plan)
        cost.atomic_write_json(output_dir / "case_identity_preflight.json", {**validation, "validated_at": cost.now_iso()})
        return plan


def save_protocol(args, output_dir):
    protocol = {"window_size": 4, "compression_profile": "current", "internal_concurrency": 1,
        "sdk_max_retries": 0, "json_parse_attempts": 3, "json_parse_exhaustion_fallback": {},
        "strict_failures_are_terminal": True,
        "accounting_only_reservation": {"gemini-2.5-pro_additional_thinking_tokens": 32768},
        "response_adapter": "LLMResponse usage contains only integer prompt/completion/total tokens; full provider usage remains in audit records",
        "code_sha256": {str(p.relative_to(ROOT)): file_digest(p) for p in (
            Path(__file__), ROOT / "emnlp2026_discussion/run_lea_full_baseline.py",
            ROOT / "emnlp2026_discussion/run_cost_audit_clean.py", ROOT / "src/modules/alphago_mcgs.py",
            ROOT / "experiments/cross_domain/run_cross_domain_battle.py")}}
    path = output_dir / "frozen_runner_protocol.json"
    with locked(output_dir / "locks" / "protocol.lock"):
        if path.exists() and json.loads(path.read_text()) != protocol:
            raise IntegrityStop("Runner/protocol changed since first use; review before further paid calls")
        if not path.exists():
            cost.atomic_write_json(path, protocol)
    return digest(protocol)


async def run_case(args, output_dir, case, graphs, route, ledger, protocol_hash):
    llm = BudgetClient(route=route, ledger=ledger, output_dir=output_dir, case=case,
        phase=args.mode, protocol_hash=protocol_hash, timeout=args.llm_timeout)
    started = time.time()
    case_args = argparse.Namespace(model=case["model"], budget=0, window_size=4,
        compression_profile="current", internal_concurrency=1, case_concurrency=1)
    failure_fields = {**cost.case_identity_audit_fields(case), "domain": case["domain"],
        "scc_id": case["scc_id"], "scc_size": case["scc_size"], "case_template": case["template"],
        "scc_clause_ids": case.get("planned_scc_clause_ids", []),
        "provider_route": route, "pricing_sha256": ledger.pricing_bytes_hash, "protocol_sha256": protocol_hash}
    try:
        graph, scc, injected_id, metadata = cost.prepare_injected_case(case, graphs)
        result = await cost.run_lea(llm, case_args, case, graph, scc, metadata)
        lea.override_injected_root_metrics(result, injected_id)
        result.update({"inject_mode": True, "injected_node": injected_id,
            "inject_type": cost.battle.DOMAIN_INJECT_TYPE.get(case["domain"]),
            "inject_profile": "memory_stress", "cycle_source": "real_long", "case_template": case["template"], **metadata})
        cost.battle.add_rank_metrics(result, injected_id)
        cost.battle.add_structural_rank_metrics(result, metadata)
        result = cost.attach_common_audit(result, args=case_args, case=case,
            method="lea", llm=llm, started_at=started)
        result.update({"completion_status": "complete", "provider_route": route,
            "pricing_sha256": ledger.pricing_bytes_hash, "protocol_sha256": protocol_hash,
            "json_parse_exhausted_windows": llm.parse_exhausted_windows,
            "smoke_case_reused_as_experiment": args.mode == "smoke"})
        return result
    except (BudgetStop, ProviderFailure, ProviderSnapshotMismatch, StrictFailure, IntegrityStop) as exc:
        if isinstance(exc, (IntegrityStop, ProviderSnapshotMismatch)):
            ledger.halt(str(exc))
        status = {BudgetStop: "budget_paused", ProviderFailure: "provider_smoke_failure" if args.mode == "smoke" else "provider_failure",
            ProviderSnapshotMismatch: "provider_snapshot_mismatch",
            StrictFailure: "strict_experiment_failure", IntegrityStop: "integrity_paused"}[type(exc)]
        return {**failure_fields, "case_id": case["case_id"], "case_order": case["case_order"],
            "model": case["model"], "method": "lea", "completion_status": status,
            "cost_audit_error": str(exc), "llm_usage_summary": cost.usage_summary(llm.call_records),
            "provider_route": route, "pricing_sha256": ledger.pricing_bytes_hash,
            "protocol_sha256": protocol_hash, "updated_at": cost.now_iso()}
    except Exception as exc:
        # Keep an unexpected strict failure as a terminal record without logging
        # arbitrary exception strings (some dependencies embed credentials).
        return {**failure_fields, "case_id": case["case_id"], "case_order": case["case_order"],
            "model": case["model"], "method": "lea", "completion_status": "strict_experiment_failure",
            "cost_audit_error": f"Strict evaluation failed: {type(exc).__name__}",
            "llm_usage_summary": cost.usage_summary(llm.call_records), "updated_at": cost.now_iso()}
    finally:
        await llm.close()


async def run(args):
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger = BudgetLedger(output_dir, args.pricing)
    protocol_hash = save_protocol(args, output_dir)
    plan = load_plan(args, output_dir)
    allowed = set(args.models or ledger.pricing["models"])
    selected = [case for case in plan if case["model"] in allowed]
    graphs = cost.load_graphs(selected)
    cost.validate_case_plan(selected, graphs)
    if args.mode == "smoke":
        selected = [c for c in selected if int(c.get("main_case_order", c["case_order"])) == args.smoke_case_order]
        if set(c["model"] for c in selected) != allowed or len(selected) != len(allowed):
            raise IntegrityStop("Smoke must select one fixed common case per requested model")
    else:
        indexes = {}
        sharded = []
        for case in selected:
            index = indexes.get(case["model"], 0)
            indexes[case["model"]] = index + 1
            if index % args.shard_count == args.shard_index:
                sharded.append(case)
        selected = sharded
    run_key = lea.safe_token("-".join(sorted(allowed))) + f"_shard{args.shard_index}of{args.shard_count}"
    status_path = output_dir / "worker_status" / f"{run_key}.json"
    status = {"models": sorted(allowed), "mode": args.mode, "shard_index": args.shard_index,
        "shard_count": args.shard_count, "selected_cases": len(selected), "completed_this_invocation": 0,
        "skipped_terminal_cases": 0, "pid": os.getpid(), "state": "preflight"}

    def update(**kwargs):
        status.update({"updated_at": cost.now_iso(), **kwargs})
        cost.atomic_write_json(status_path, status)

    ledger.snapshot()
    update()
    if args.mode == "preflight":
        print(json.dumps({"preflight": "ok", "selected_cases": len(selected), "status_file": str(status_path)}), flush=True)
        return
    blocked_models = set()
    for case in selected:
        model = case["model"]
        if model in blocked_models:
            continue
        route = ledger.pricing["models"][model]
        if not os.environ.get(route["api_key_env"]):
            update(state="missing_credential", model=model, required_env=route["api_key_env"])
            print(json.dumps({"model": model, "status": "missing_credential", "api_key_env": route["api_key_env"]}), flush=True)
            blocked_models.add(model)
            continue
        with locked(output_dir / "locks" / "cases" / f"{case['case_id']}.lock", nonblocking=True) as acquired:
            if not acquired:
                continue
            result_path = lea.result_path(output_dir, case)
            if result_path.exists():
                existing = json.loads(result_path.read_text())
                if (existing.get("model") != model
                    or existing.get("protocol_sha256") not in compatible_protocol_hashes(output_dir, protocol_hash, for_terminal_results=True)
                    or existing.get("pricing_sha256") != ledger.pricing_bytes_hash
                    or existing.get("provider_route") != route):
                    raise IntegrityStop("Existing result model, route or frozen protocol does not match")
                if existing.get("completion_status") == "complete":
                    cost.validate_result_case_identity(existing, case, graphs[case["domain"]])
                status["skipped_terminal_cases"] += 1
                continue
            case_status_path = output_dir / "case_status" / f"{case['case_id']}.json"
            if case_status_path.exists():
                previous = json.loads(case_status_path.read_text())
                previous_status = previous.get("completion_status", "")
                if "provider" in previous_status and not args.resume_provider_failures:
                    blocked_models.add(model)
                    continue
                if previous_status in ("integrity_paused", "provider_snapshot_mismatch"):
                    raise IntegrityStop("Case paused for integrity reconciliation; explicit review required")
            append(output_dir / "case_attempts.jsonl", {"event": "case_started", "at": cost.now_iso(),
                "case_id": case["case_id"], "model": model, "phase": args.mode, "worker": run_key})
            update(state="running", active_case=case["case_id"], model=model)
            result = await run_case(args, output_dir, case, graphs, route, ledger, protocol_hash)
            state = result["completion_status"]
            cost.atomic_write_json(case_status_path, result)
            if state in ("complete", "strict_experiment_failure"):
                cost.atomic_write_json(result_path, result)
            append(output_dir / "case_attempts.jsonl", {"event": "case_ended", "at": cost.now_iso(),
                "case_id": case["case_id"], "model": model, "phase": args.mode, "status": state, "worker": run_key})
            print(json.dumps({"case_id": case["case_id"], "status": state,
                "budget": {key: dollars(value) for key, value in ledger.snapshot().items()}}), flush=True)
            if state == "complete":
                status["completed_this_invocation"] += 1
            if state in ("budget_paused", "integrity_paused"):
                update(state=state, active_case=None)
                return
            if "provider" in state:
                blocked_models.add(model)
    with locked(output_dir / "locks" / "summary.lock"):
        lea.summarize(output_dir)
    update(state="stopped_with_blocked_models" if blocked_models else "finished", active_case=None,
           blocked_models=sorted(blocked_models))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--case-csv", type=Path, default=HERE / "missing_cases.csv")
    parser.add_argument("--case-plan", type=Path, default=HERE / "preflight/case_plan.json")
    parser.add_argument("--pricing", type=Path, default=HERE / "frozen_pricing.json")
    parser.add_argument("--models", nargs="+")
    parser.add_argument("--mode", choices=("preflight", "smoke", "run"), default="preflight")
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--llm-timeout", type=float, default=180)
    parser.add_argument("--smoke-case-order", type=int, default=20)
    parser.add_argument("--resume-provider-failures", action="store_true")
    args = parser.parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error("Require 0 <= shard-index < shard-count")
    if args.mode == "smoke" and (args.shard_count != 1 or args.shard_index != 0):
        parser.error("Smoke uses the fixed first case per model and cannot be sharded")
    for field in ("output_dir", "case_csv", "case_plan", "pricing"):
        setattr(args, field, getattr(args, field).resolve())
    return args


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except RunStop as exc:
        print(json.dumps({"stopped": type(exc).__name__, "reason": str(exc)}), flush=True)
        sys.exit(2)

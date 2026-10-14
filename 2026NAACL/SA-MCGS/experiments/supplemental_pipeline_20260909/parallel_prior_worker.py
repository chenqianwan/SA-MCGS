#!/usr/bin/env python3
"""Isolated, single-attempt worker for the scheduling-only prior amendment.

Only the coordinator may publish results or append the official ledger.  This
worker imports (and hashes) the frozen serial runner unchanged, preserves its
scientific configuration, and writes exclusively to its immutable-ticket
directory.  The budget guard uses frozen list prices; it is not an assertion of
exact provider billing for hidden SDK retries.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any


PIPELINE_DIR = Path(__file__).resolve().parent
SOURCE_RUNNER = PIPELINE_DIR.parent / "prior_fallback_slots_01_03_08_10" / "run_prior_fallback.py"
TICKET_SCHEMA = "prior_parallel_worker_ticket.v1"


class WorkerError(RuntimeError):
    pass


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("isolated_frozen_prior_runner", SOURCE_RUNNER)
    if spec is None or spec.loader is None:
        raise WorkerError("Cannot import frozen prior runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finite_nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise WorkerError(f"Invalid {label}")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise WorkerError(f"Invalid {label}") from exc
    if not math.isfinite(result) or result < 0:
        raise WorkerError(f"Invalid {label}")
    return result


def read_ticket(path: Path, expected_hash: str) -> tuple[dict[str, Any], Path]:
    path = path.resolve()
    if file_hash(path) != expected_hash:
        raise WorkerError("Ticket hash mismatch")
    ticket = json.loads(path.read_text(encoding="utf-8"))
    if ticket.get("schema") != TICKET_SCHEMA:
        raise WorkerError("Unexpected worker ticket schema")
    raw_dir = Path(ticket["worker_dir"])
    if not raw_dir.is_absolute():
        raise WorkerError("Worker directory must be absolute")
    worker_dir = raw_dir.resolve()
    try:
        relative = worker_dir.relative_to(PIPELINE_DIR.resolve())
    except ValueError as exc:
        raise WorkerError("Worker directory must be isolated under the pipeline") from exc
    if not relative.parts or path != worker_dir / "ticket.json":
        raise WorkerError("Ticket must be worker_dir/ticket.json")
    if ticket.get("outer_process_concurrency") != 4:
        raise WorkerError("Unexpected scheduling concurrency")
    cap = finite_nonnegative(ticket.get("worker_spend_cap_usd"), "worker cap")
    if cap <= 0 or cap > 200:
        raise WorkerError("Worker cap must be within the authorized ceiling")
    return ticket, worker_dir


def validate_ticket(ticket: dict[str, Any], runner: Any) -> dict[str, Any]:
    """Rebuild science identity from the frozen source, not from ticket assertions."""
    if ticket.get("source_runner_sha256") != file_hash(SOURCE_RUNNER):
        raise WorkerError("Frozen runner source hash mismatch")
    frozen = runner.protocol()
    if ticket.get("protocol_sha256") != runner.file_hash(runner.PROTOCOL_PATH):
        raise WorkerError("Protocol hash mismatch")
    amendment = Path(ticket.get("amendment_path", ""))
    if not amendment.is_absolute() or file_hash(amendment) != ticket.get("amendment_sha256"):
        raise WorkerError("Scheduling amendment hash mismatch")
    runner.validate_source_hashes(frozen)
    manifest = runner.validate_manifest(frozen)
    plans, graphs, _ = runner.validate_selected_plans(frozen, manifest)
    expected = runner.expected_execution_rows(manifest, plans)
    cell = ticket["cell"]
    matching = [row for row in expected if row["order"] == cell.get("order")]
    if len(matching) != 1 or matching[0] != cell:
        raise WorkerError("Ticket cell differs from the frozen execution plan")
    case = next(row for row in plans[cell["model"]] if row["case_order"] == cell["slot"])
    if case != ticket["case"]:
        raise WorkerError("Ticket case differs from validated source case")
    if Path(cell["result_path"]).exists():
        raise WorkerError("Official result is already terminal; no rerun permitted")
    snapshot = ticket.get("budget_snapshot") or {}
    payload = snapshot.get("payload") or {}
    if snapshot.get("authoritative") is not True or payload.get("context_kind") != "authoritative":
        raise WorkerError("Synthetic or non-authoritative budget snapshot is forbidden")
    audited_snapshot = runner.validate_balance_snapshot(
        frozen,
        context_kind="authoritative",
        snapshot_path=snapshot.get("path"),
        snapshot_sha256=snapshot.get("sha256"),
        asserted_balance_usd=payload.get("total_available_usd"),
        asserted_captured_at=payload.get("captured_at"),
    )
    if not audited_snapshot.get("passed") or audited_snapshot.get("age_seconds", math.inf) > 1800:
        raise WorkerError("Worker launch requires a fresh authoritative balance snapshot")
    if audited_snapshot.get("payload") != payload:
        raise WorkerError("Snapshot summary differs from hashed source artifact")
    if finite_nonnegative(payload.get("total_available_usd"), "account balance") < float(ticket["worker_spend_cap_usd"]):
        raise WorkerError("Account snapshot cannot cover this worker reservation")
    runtime = frozen["locked_runtime"]
    if runtime["internal_concurrency"] != 1 or runtime["case_concurrency"] != 1 or runtime["llm_max_retries"] != 2:
        raise WorkerError("Frozen per-cell runtime changed")
    return {"frozen": frozen, "cell": cell, "case": case, "graphs": graphs[cell["model"]]}


class SpendGuard:
    """Observed usage plus conservative reservations for unobserved failed calls.

Each next wrapper call reserves three SDK attempts. A successful response releases
that reservation in favor of observed usage; failed/zero-usage responses retain
it. Hidden retries inside successful wrappers are not separately observable and
must also be checked against fresh account balances by the coordinator.
"""

    def __init__(self, *, cap: float, rates: dict[str, float], retries: int = 2):
        self.cap = finite_nonnegative(cap, "worker cap")
        self.rates = {key: finite_nonnegative(rates[key], key) for key in ("input", "output")}
        self.attempts = int(retries) + 1
        self.observed_usd = 0.0
        self.unobserved_failure_reserve_usd = 0.0
        self.blocked = False
        self.lock = asyncio.Lock()

    def maximum_next_cost(self, prompt: str, system_prompt: str | None, max_tokens: int, response_format: dict | None) -> float:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
            raise WorkerError("A bounded positive output token limit is required")
        # UTF-8 bytes conservatively bound text tokens. Allow 512 additional
        # tokens for message framing, JSON response format, and protocol overhead.
        prompt_bound = len((prompt or "").encode("utf-8")) + len((system_prompt or "").encode("utf-8")) + 512
        if response_format:
            prompt_bound += len(json.dumps(response_format, ensure_ascii=False).encode("utf-8"))
        return self.attempts * (prompt_bound * self.rates["input"] + max_tokens * self.rates["output"]) / 1_000_000

    @property
    def spend_upper_bound(self) -> float:
        return self.observed_usd + self.unobserved_failure_reserve_usd

    def admit(self, reserve: float, exception_type: type[Exception]) -> None:
        if self.blocked or self.spend_upper_bound + reserve > self.cap + 1e-12:
            self.blocked = True
            raise exception_type("Worker budget cap reached before the next API call; terminal, no automatic retry")

    def settle(self, reserve: float, usage: dict[str, Any] | None) -> None:
        usage = usage or {}
        prompt = finite_nonnegative(usage.get("prompt_tokens", 0), "observed prompt usage")
        output = finite_nonnegative(usage.get("completion_tokens", 0), "observed completion usage")
        if prompt + output > 0:
            self.observed_usd += (prompt * self.rates["input"] + output * self.rates["output"]) / 1_000_000
        else:
            self.unobserved_failure_reserve_usd += reserve
        if self.spend_upper_bound > self.cap + 1e-12:
            self.blocked = True

    def summary(self) -> dict[str, Any]:
        return {
            "worker_spend_cap_usd": self.cap,
            "provider_observed_estimated_usd": self.observed_usd,
            "budget_spend_upper_bound_usd": self.spend_upper_bound,
            "unobserved_failure_reserve_usd": self.unobserved_failure_reserve_usd,
            "budget_stop_triggered": self.blocked,
            "sdk_maximum_attempts_per_wrapper_call": self.attempts,
            "basis": "frozen_list_prices_observed_usage_plus_unobserved_failure_reserves",
            "successful_wrapper_hidden_retry_billing_not_observable": True,
            "exact_provider_billing_upper_bound_claimed": False,
        }


def guarded_client_class(runner: Any, guard: SpendGuard, metadata: dict[str, Any], worker_dir: Path) -> type:
    original = runner.cost.LoggingOpenAIClient

    class GuardedLoggingClient(original):
        def __init__(self, *args: Any, **kwargs: Any):
            kwargs["context"] = {**kwargs.get("context", {}), **metadata}
            super().__init__(*args, **kwargs)

        async def call(self, prompt: str, *, temperature: float = 0.0, max_tokens: int = 4096,
                       system_prompt: str | None = None, response_format: dict | None = None) -> Any:
            async with guard.lock:
                reserve = guard.maximum_next_cost(prompt, system_prompt, max_tokens, response_format)
                guard.admit(reserve, runner.BudgetStop)
                runner.cost.append_jsonl(worker_dir / "budget_guard.jsonl", {
                    "event": "call_reserved", "recorded_at": runner.now_iso(),
                    "maximum_next_call_usd": reserve, **guard.summary(),
                })
                response = None
                try:
                    response = await super().call(prompt, temperature=temperature, max_tokens=max_tokens,
                                                  system_prompt=system_prompt, response_format=response_format)
                    return response
                finally:
                    guard.settle(reserve, getattr(response, "usage", None))
                    runner.cost.append_jsonl(worker_dir / "budget_guard.jsonl", {
                        "event": "call_settled", "recorded_at": runner.now_iso(), **guard.summary(),
                    })

    return GuardedLoggingClient


async def execute(ticket: dict[str, Any], worker_dir: Path, runner: Any, validated: dict[str, Any], ticket_hash: str) -> dict[str, Any]:
    frozen, cell, case, graphs = (validated[key] for key in ("frozen", "cell", "case", "graphs"))
    graph, scc, injected_id, injection_metadata = runner.cost.prepare_injected_case(case, graphs)
    # Recheck after graph preparation, immediately before establishing paid state.
    snapshot = ticket["budget_snapshot"]
    runner.validate_balance_snapshot(frozen, context_kind="authoritative", snapshot_path=snapshot["path"],
                                    snapshot_sha256=snapshot["sha256"],
                                    asserted_balance_usd=snapshot["payload"]["total_available_usd"],
                                    asserted_captured_at=snapshot["payload"]["captured_at"])
    if Path(cell["result_path"]).exists():
        raise WorkerError("Official result appeared before worker start")
    actual_started_at = runner.now_iso()
    actual_started_epoch = time.time()
    scheduling = {
        "schema": "prior_parallel_scheduling.v1", "outer_process_concurrency": 4,
        "per_worker_case_concurrency": 1, "per_worker_internal_concurrency": 1,
        "amendment_path": ticket["amendment_path"], "amendment_sha256": ticket["amendment_sha256"],
        "ticket_path": str(worker_dir / "ticket.json"), "ticket_sha256": ticket_hash,
        "worker_source_sha256": file_hash(Path(__file__)), "worker_dir": str(worker_dir),
        "actual_started_at": actual_started_at, "actual_started_epoch": actual_started_epoch,
        "frozen_case_concurrency_field_scope": "per_isolated_worker_not_whole_batch",
        "wall_clock_comparable_to_serial_nominal": False,
    }
    runner.cost.atomic_write_json(worker_dir / "started.json", {
        "schema": "prior_parallel_worker_started.v1", "order": cell["order"],
        "pid": os.getpid(), "actual_started_at": actual_started_at,
        "actual_started_epoch": actual_started_epoch, "ticket_sha256": ticket_hash,
        "outer_scheduling": scheduling,
    })
    guard = SpendGuard(cap=float(ticket["worker_spend_cap_usd"]),
                       rates=frozen["pricing"]["rates_usd_per_million_tokens"][cell["model"]],
                       retries=frozen["locked_runtime"]["llm_max_retries"])
    original_client = runner.cost.LoggingOpenAIClient
    runner.cost.LoggingOpenAIClient = guarded_client_class(runner, guard, {
        "outer_process_concurrency": 4, "outer_scheduling_amendment_sha256": ticket["amendment_sha256"],
        "worker_ticket_sha256": ticket_hash,
    }, worker_dir)
    try:
        with runner.cost.InjectedGroundTruth(case["domain"], injected_id):
            result = await runner.run_prior_sa_cell(cell=cell, case=case, graph=graph, scc=scc,
                                                   injected_id=injected_id, injection_metadata=injection_metadata,
                                                   output_dir=worker_dir)
    finally:
        runner.cost.LoggingOpenAIClient = original_client
    # Some search-layer error handlers can absorb a client exception; a budget
    # cutoff must nevertheless be a terminal invalid, never a partial success.
    if guard.blocked:
        result["cost_audit_error"] = "Worker budget guard stopped further paid calls"
        result["error_type"] = "BudgetStop"
    result["outer_scheduling"] = scheduling
    result["budget_guard"] = guard.summary()
    runner.validate_local_result(result, cell=cell, case=case, graph=graphs[case["domain"]])
    completed_at = runner.now_iso()
    scheduling["actual_completed_at"] = completed_at
    scheduling["actual_completed_epoch"] = time.time()
    scheduling["budget_spend_upper_bound_usd"] = guard.spend_upper_bound
    scheduling["unobserved_failure_reserve_usd"] = guard.unobserved_failure_reserve_usd
    pending = worker_dir / "pending_result.json"
    runner.cost.atomic_write_json(pending, result)
    usage = result.get("llm_usage_summary") or {}
    completion = {
        "schema": "prior_parallel_worker_completion.v1", "order": cell["order"],
        "result_path": str(pending), "result_sha256": file_hash(pending), "usage": usage,
        "estimated_usd": runner.estimate_usd(cell["model"], usage, frozen),
        "valid": not bool(result.get("cost_audit_error")), "error_type": result.get("error_type"),
        "actual_started_at": actual_started_at, "actual_completed_at": completed_at,
        "actual_started_epoch": actual_started_epoch, "actual_completed_epoch": scheduling["actual_completed_epoch"],
        "ticket_sha256": ticket_hash, "amendment_sha256": ticket["amendment_sha256"],
        "budget_spend_upper_bound_usd": guard.spend_upper_bound,
        "unobserved_failure_reserve_usd": guard.unobserved_failure_reserve_usd,
        "budget_guard": guard.summary(), "invalid_is_terminal": True, "automatic_retry_permitted": False,
    }
    runner.cost.atomic_write_json(worker_dir / "completion.json", completion)
    return completion


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket", type=Path, required=True)
    parser.add_argument("--ticket-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    ticket, worker_dir = read_ticket(args.ticket, args.ticket_sha256)
    runner = load_runner()
    validated = validate_ticket(ticket, runner)
    if not args.execute:
        print(json.dumps({"status": "dry_inspect_passed", "order": ticket["cell"]["order"],
                          "paid_execution": False, "worker_dir": str(worker_dir)}))
        return 0
    with (worker_dir / "worker.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkerError("This worker ticket is already executing") from exc
        if any((worker_dir / name).exists() for name in ("started.json", "pending_result.json", "completion.json")):
            raise WorkerError("Ticket already started or terminal; automatic rerun forbidden")
        completion = asyncio.run(execute(ticket, worker_dir, runner, validated, args.ticket_sha256))
        print(json.dumps({"status": "worker_terminal", "order": completion["order"],
                          "valid": completion["valid"], "estimated_usd": completion["estimated_usd"]}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Do not print request bodies, configuration, credentials, or SDK errors.
        print(json.dumps({"status": "worker_refused_or_failed", "error_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)

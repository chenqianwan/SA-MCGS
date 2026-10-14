#!/usr/bin/env python3
"""Four isolated prior workers, unchanged per-search science, one ordered writer.

The authoritative parallel journal records actual execution order/times. The
legacy serial-prefix result view is materialized only in canonical order; its
ledger timestamps are commit times, with actual times attached explicitly.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
REPO = PROJECT.parents[1]
PRIOR = PROJECT / "experiments/prior_fallback_slots_01_03_08_10"
WORK = HERE / "parallel_prior_v1"
AMENDMENT = WORK / "amendment.json"
WORKER = HERE / "parallel_prior_worker.py"
PYTHON = "/opt/homebrew/anaconda3/bin/python"
MAX_WORKERS = 4
RESERVE = 10.0


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def journal(event, **fields):
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / "events.jsonl").open("a") as out:
        out.write(json.dumps({"recorded_at": now(), "event": event, **fields}, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())


def status(state, **fields):
    payload = {"updated_at": now(), "state": state, "pid": os.getpid(),
               "outer_process_concurrency": MAX_WORKERS,
               "per_worker_case_concurrency": 1, "internal_concurrency": 1,
               "budget_ceiling_usd": 200, "expert_results": "awaiting_author_labels", **fields}
    save(HERE / "execution_status.json", payload)
    save(WORK / "execution_status.json", payload)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def process_command(pid):
    response = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat=,command="],
                              capture_output=True, text=True)
    if response.returncode:
        return ""
    value = response.stdout.strip()
    return "" if not value or value.split()[0].startswith("Z") else value


def budget_needed(execution, committed, jobs, caps):
    """Include every active/queued reservation, not only canonical ledger spend."""
    pending = 0.0
    for cell in execution:
        order = int(cell["order"])
        if order <= committed:
            continue
        job = jobs.get(order)
        if job and job.get("completion"):
            item = job["completion"]
            pending += max(float(item["estimated_usd"]),
                           float(item.get("budget_spend_upper_bound_usd", item["estimated_usd"])))
        elif job:
            pending += float(job["cap"])
        else:
            pending += float(caps[str(cell["model"])])
    return pending + RESERVE


def require_budget(needed, remaining, shared_room):
    values = [needed, remaining, shared_room]
    if not all(math.isfinite(v) and v >= 0 for v in values):
        raise RuntimeError("Non-finite/negative parallel budget input")
    if needed > remaining or needed > shared_room:
        raise RuntimeError(f"Parallel reserved tail ${needed:.6f} exceeds available budget")


def validate_reserved_amount(upper, observed, cap):
    values = (upper, observed, cap)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise RuntimeError("Invalid completion budget amount")
    if observed < 0 or upper < observed - 1e-8 or upper > cap + 1e-8:
        raise RuntimeError("Completion reservation is inconsistent with observed spend/cap")


def receipt_for(p, pre, cell, accounting, needed, snapshot, ticket_path):
    order = int(cell["order"])
    invocation = f"parallel-prior-{os.getpid()}-{order:02d}"
    receipt = {
        "receipt_version": "prior_fallback_launch_receipt_v1", "created_at": now(),
        "invocation_id": invocation, "protocol_version": p.EXPECTED_PROTOCOL_VERSION,
        "protocol_sha256": digest(p.PROTOCOL_PATH), "runner_sha256": digest(Path(p.__file__)),
        "fallback_manifest_sha256": pre["frozen"]["selection"]["source_manifest_sha256"],
        "parent_protocol_sha256": pre["frozen"]["parent"]["frozen_protocol_sha256"],
        "global_authorization_usd": 200.0,
        "global_authorization_remaining_usd_derived_at_invocation": accounting["derived_authorization_remaining_usd"],
        "closeout_reserve_usd": RESERVE, "fresh_balance_snapshot": snapshot,
        "accounting_provenance": accounting, "required_including_closeout_usd": needed,
        "next_execution_order": order, "max_new_cells": 1,
        "paid_execution_explicitly_authorized": True,
        "outer_process_concurrency": MAX_WORKERS, "per_worker_case_concurrency": 1,
        "dispatcher_sha256": digest(__file__), "worker_sha256": digest(WORKER),
        "ticket_path": str(ticket_path), "amendment_path": str(AMENDMENT),
        "amendment_sha256": digest(AMENDMENT),
        "ledger_note": "Receipt created before execution; canonical ledger entries are materialized later in prefix order with actual timestamps attached",
    }
    return invocation, receipt


def validate_completion(p, pre, job):
    payload = read(job["directory"] / "completion.json")
    result_path = (job["directory"] / "pending_result.json").resolve()
    if Path(payload["result_path"]).resolve() != result_path or digest(result_path) != payload["result_sha256"]:
        raise RuntimeError("Parallel worker result hash/path mismatch")
    cell = job["cell"]
    if payload["order"] != cell["order"]:
        raise RuntimeError("Worker returned the wrong execution order")
    result = read(result_path)
    model = str(cell["model"])
    case = job["case"]
    p.validate_local_result(result, cell=cell, case=case, graph=pre["graphs"][model][case["domain"]])
    usage = result.get("llm_usage_summary") or {}
    amount = p.estimate_usd(model, usage)
    if usage != payload["usage"] or not math.isclose(amount, payload["estimated_usd"], abs_tol=1e-8):
        raise RuntimeError("Parallel completion usage/cost binding failed")
    if payload["valid"] is not (not bool(result.get("cost_audit_error"))):
        raise RuntimeError("Parallel completion validity mismatch")
    if amount > float(job["cap"]) + 1e-8:
        raise RuntimeError("Worker observed spend exceeded its reserved cap")
    upper = payload.get("budget_spend_upper_bound_usd")
    validate_reserved_amount(upper, amount, float(job["cap"]))
    guard = result.get("budget_guard") or {}
    if guard != payload.get("budget_guard") or guard.get("budget_spend_upper_bound_usd") != upper:
        raise RuntimeError("Result/completion budget guard mismatch")
    unknown = payload.get("unobserved_failure_reserve_usd")
    if unknown != guard.get("unobserved_failure_reserve_usd") or not math.isclose(upper, amount + unknown, abs_tol=1e-8):
        raise RuntimeError("Unobserved billing reservation mismatch")
    ticket_path = job["directory"] / "ticket.json"
    if payload.get("ticket_sha256") != digest(ticket_path) or payload.get("amendment_sha256") != digest(AMENDMENT):
        raise RuntimeError("Completion ticket/amendment binding failed")
    scheduling = result.get("outer_scheduling") or {}
    if (scheduling.get("outer_process_concurrency") != MAX_WORKERS or
        scheduling.get("ticket_sha256") != digest(ticket_path) or
        scheduling.get("amendment_sha256") != digest(AMENDMENT)):
        raise RuntimeError("Worker did not disclose the outer parallel schedule")
    return payload


def commit_job(p, job):
    """Only coordinator writes official artifacts; no API, no result changes."""
    cell, completion = job["cell"], job["completion"]
    destination = Path(cell["result_path"])
    if destination.exists():
        raise RuntimeError("Refusing to overwrite an official terminal result")
    receipt_path = job["receipt"]
    receipt = read(receipt_path)
    invocation = receipt["invocation_id"]
    recorded_at = now()
    p.append_ledger({"event": "run_invocation_start", "recorded_at": recorded_at,
        "actual_invocation_started_at": receipt["created_at"], "invocation_id": invocation,
        "protocol_sha256": receipt["protocol_sha256"], "runner_sha256": receipt["runner_sha256"],
        "launch_receipt": str(receipt_path), "launch_receipt_sha256": digest(receipt_path),
        "paid_execution_explicitly_authorized": True, "outer_process_concurrency": MAX_WORKERS,
        "global_authorization_usd": 200.0, "closeout_reserve_usd": RESERVE})
    identity = {"invocation_id": invocation, "order": int(cell["order"]),
                "model": cell["model"], "profile": cell["profile"], "slot": cell["slot"],
                "case_id": cell["case_id"], "case_uid": cell["case_uid"],
                "result_path": str(destination.resolve())}
    p.append_ledger({**identity, "event": "cell_start", "recorded_at": recorded_at,
        "actual_started_at": completion["actual_started_at"],
        "parallel_journal": str(WORK / "events.jsonl"),
        "materialized_after_worker_completion": True})
    # Copy bytes exactly so the worker's own result hash remains authoritative.
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".parallel.tmp")
    temporary.write_bytes(Path(completion["result_path"]).read_bytes())
    temporary.replace(destination)
    p.append_ledger({**identity, "event": "cell_complete", "recorded_at": now(),
        "actual_completed_at": completion["actual_completed_at"],
        "valid": completion["valid"], "error_type": completion.get("error_type"),
        "usage": completion["usage"], "estimated_usd": completion["estimated_usd"],
        "result_sha256": digest(destination), "invalid_is_terminal": True,
        "automatic_retry_permitted": False, "outer_process_concurrency": MAX_WORKERS})
    journal("canonical_prefix_committed", order=cell["order"], result_sha256=digest(destination),
            actual_completed_at=completion["actual_completed_at"])


def _run_pool(p, coordinator, context):
    if list((WORK / "workers").glob("*/ticket.json")):
        raise RuntimeError("Existing parallel tickets require recovery audit; never duplicate paid workers")
    pre = p.perform_preflight(command="parallel_initial_preflight")
    if not pre["gate"]["intrinsic_ready"]:
        raise RuntimeError("Frozen source/identity/nominal gate failed")
    committed = int(pre["state"]["attempted"])
    if committed == 16:
        return
    execution = pre["execution"]
    caps = dict(pre["projection"]["reserve_per_missing_cell_usd"])
    jobs = {}
    context.update(jobs=jobs, pre=pre, committed=committed)
    save(WORK / "initial_state.json", {"created_at": now(), "prior_committed": committed,
        "preflight_gate": pre["gate"], "caps": caps,
        "preserved_result_hashes": {str(path): digest(path) for path in p.RESULTS_DIR.glob("*/*/results/*.json")}})
    while committed < 16:
        # Collect finished workers; never free reservations solely on process exit.
        for order, job in jobs.items():
            if job.get("completion"):
                continue
            result = job["process"].poll()
            if result is None:
                continue
            if result != 0 or not (job["directory"] / "completion.json").is_file():
                raise RuntimeError(f"Worker {order} exited without a verified terminal result; no automatic retry")
            job["completion"] = validate_completion(p, pre, job)
            journal("worker_complete", order=order, completion=job["completion"])
        while committed + 1 in jobs and jobs[committed + 1].get("completion"):
            commit_job(p, jobs[committed + 1])
            committed += 1
            context["committed"] = committed
        if committed == 16:
            break
        active = [order for order, job in jobs.items() if not job.get("completion")]
        next_cell = next((cell for cell in execution
                          if cell["order"] > committed and cell["order"] not in jobs), None)
        if len(active) < MAX_WORKERS and next_cell:
            # Fresh account artifact and complete reserved tail on every dispatch.
            snapshot_path, snapshot = coordinator.capture_balance()
            accounting = p.accounting_provenance(pre["frozen"], context_kind="authoritative",
                fresh_xhub_balance_usd=snapshot["total_available_usd"],
                fresh_balance_captured_at=snapshot["captured_at"], upstream_ledgers=None,
                balance_snapshot_path=str(snapshot_path), balance_snapshot_sha256=digest(snapshot_path))
            if not accounting["authoritative_for_paid_launch"]:
                raise RuntimeError("Parallel account/ledger provenance failed")
            needed = budget_needed(execution, committed, jobs, caps)
            # Failed calls without usage retain a separate reservation even after
            # canonical commit; they must not become free budget.
            unknown_committed = sum(max(0, float(j["completion"].get("budget_spend_upper_bound_usd", j["completion"]["estimated_usd"])) - float(j["completion"]["estimated_usd"]))
                for order, j in jobs.items() if order <= committed and j.get("completion"))
            remaining = float(accounting["derived_authorization_remaining_usd"]) - unknown_committed
            require_budget(needed, remaining, snapshot["total_available_usd"] - coordinator.BALANCE_FLOOR)
            p.validate_source_hashes(pre["frozen"])
            cell = next_cell
            model, order = str(cell["model"]), int(cell["order"])
            case = next(row for row in pre["plans"][model] if row["case_order"] == cell["slot"])
            directory = (WORK / "workers" / f"{order:02d}").resolve()
            ticket_path = directory / "ticket.json"
            invocation, receipt = receipt_for(p, pre, cell, accounting, needed,
                                              accounting["balance_snapshot"], ticket_path)
            receipt_path = (PRIOR / "launch_receipts" / f"{invocation}.json").resolve()
            if receipt_path.exists() or ticket_path.exists():
                raise RuntimeError("Duplicate worker launch artifacts")
            ticket = {"schema": "prior_parallel_worker_ticket.v1", "created_at": now(),
                "cell": cell, "case": case, "worker_dir": str(directory),
                "protocol_sha256": digest(p.PROTOCOL_PATH), "source_runner_sha256": digest(Path(p.__file__)),
                "worker_spend_cap_usd": caps[model], "outer_process_concurrency": MAX_WORKERS,
                "budget_snapshot": accounting["balance_snapshot"],
                "amendment_path": str(AMENDMENT), "amendment_sha256": digest(AMENDMENT)}
            save(ticket_path, ticket)
            save(receipt_path, receipt)
            journal("worker_dispatch_authorized", order=order, ticket=str(ticket_path),
                    ticket_sha256=digest(ticket_path), cap=caps[model],
                    reserved_tail_including_closeout_usd=needed,
                    remaining_authorized_usd=remaining, snapshot=str(snapshot_path))
            with (directory / "worker.log").open("ab") as log:
                child = subprocess.Popen([PYTHON, str(WORKER), "--ticket", str(ticket_path),
                    "--ticket-sha256", digest(ticket_path), "--execute"], cwd=REPO,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, close_fds=True)
            jobs[order] = {"process": child, "cell": cell, "case": case, "directory": directory,
                           "receipt": receipt_path, "cap": caps[model]}
            journal("worker_spawned", order=order, pid=child.pid)
            active.append(order)
            status("running_prior_parallel", committed=committed, planned=16, active_orders=active,
                   completed_pending_commit=[o for o,j in jobs.items() if o > committed and j.get("completion")],
                   remaining_authorized_usd=remaining, reserved_tail_usd=needed)
            continue
        status("running_prior_parallel", committed=committed, planned=16, active_orders=active,
               completed_pending_commit=[o for o,j in jobs.items() if o > committed and j.get("completion")])
        time.sleep(15)
    final = p.perform_preflight(command="parallel_final_preflight")
    if not final["gate"]["already_complete"] or final["state"]["attempted"] != 16:
        raise RuntimeError("Legacy 16-cell final gate failed")
    observed = float(final["accounting"]["validated_cumulative_spend_usd"])
    unknown = sum(float(j["completion"].get("unobserved_failure_reserve_usd", 0)) for j in jobs.values())
    if observed + unknown + RESERVE > 200 + 1e-8:
        raise RuntimeError("Final observed spend plus unknown reservations exceeds authorization")
    budget_stopped = [o for o, j in jobs.items() if j["completion"].get("budget_guard", {}).get("budget_stop_triggered")]
    save(WORK / "final_accounting.json", {"observed_estimated_usd": observed,
        "unobserved_failure_reserve_usd": unknown, "closeout_reserve_usd": RESERVE,
        "budget_stopped_orders": budget_stopped, "global_authorization_usd": 200})
    p.make_report()
    p.write_status("complete", {"outer_process_concurrency": MAX_WORKERS,
                               "parallel_amendment": str(AMENDMENT)})
    closeout = coordinator.run_closeout()
    note = ("# Prior 外层并行执行说明\n\n"
            "本批从 serial 已完成前缀之后切换至最多4个独立worker；每worker case/internal concurrency仍为1，科学配置不变。"
            "实际dispatch、开始/完成及canonical提交时间分别保留，账本前缀提交顺序不是实际串行执行顺序。"
            "prior 的runtime/限流率不可与串行nominal直接作公平比较。"
            "Cost中断恢复费用与首次有效性另见上级README，不把恢复成功当首次成功。\n\n"
            f"本轮已观测列表价估算 ${observed:.6f}，另保留未观察失败调用预留 ${unknown:.6f}。"
            f"预算门禁提前截断的任务：{budget_stopped}；如非空，按strict invalid保留，不将该下降归因于prior权重。\n")
    (Path(closeout) / "EXECUTION_CAVEATS_ZH.md").write_text(note)
    status("paid_experiments_complete_labels_pending", prior_cells=final["gate"]["local_result_state"],
           attributable_spend_usd=final["accounting"]["validated_cumulative_spend_usd"],
           paired_clustered_statistics=closeout, parallel_amendment=str(AMENDMENT))


def run_pool(p, coordinator):
    context = {}
    try:
        return _run_pool(p, coordinator, context)
    except Exception:
        # A launch/worker fault stops further dispatch, not other already-paid
        # work. Keep the host awake and drain independent artifacts for recovery.
        jobs = context.get("jobs", {})
        while any(job["process"].poll() is None for job in jobs.values()):
            status("parallel_draining_after_error", committed=context.get("committed"),
                   active_orders=[o for o,j in jobs.items() if j["process"].poll() is None])
            time.sleep(15)
        recovery = []
        for order, job in jobs.items():
            item = {"order": order, "pid": job["process"].pid,
                    "exit_code": job["process"].returncode, "worker_dir": str(job["directory"]),
                    "reserved_cap_usd": job["cap"]}
            try:
                item["verified_completion"] = validate_completion(p, context["pre"], job)
            except Exception as exc:
                item["verification_error"] = f"{type(exc).__name__}: {exc}"
            recovery.append(item)
        save(WORK / "recovery_required.json", {"created_at": now(),
            "committed": context.get("committed"), "automatic_retry_permitted": False,
            "workers": recovery})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--legacy-coordinator-pid", type=int, default=20150)
    parser.add_argument("--legacy-child-pid", type=int, default=27166)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"mode": "offline_inspection_only", "current": read(HERE / "execution_status.json")}, ensure_ascii=False))
        return
    coordinator = load_module("serial_coordinator", HERE / "continue_pipeline.py")
    old = process_command(args.legacy_coordinator_pid)
    if old:
        if str(HERE / "continue_pipeline.py") not in old or not old.split()[0].startswith("T"):
            raise RuntimeError("Legacy coordinator is not the inspected paused process")
        os.kill(args.legacy_coordinator_pid, signal.SIGTERM)
        os.kill(args.legacy_coordinator_pid, signal.SIGCONT)
        for _ in range(20):
            if not process_command(args.legacy_coordinator_pid):
                break
            time.sleep(.1)
    with (HERE / "pipeline.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        awake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())])
        try:
            while process_command(args.legacy_child_pid):
                if str(PRIOR / "run_prior_fallback.py") not in process_command(args.legacy_child_pid):
                    raise RuntimeError("Legacy child PID identity changed")
                status("waiting_for_serial_cell_to_finish", legacy_child_pid=args.legacy_child_pid)
                time.sleep(15)
            p = load_module("frozen_parallel_prior", PRIOR / "run_prior_fallback.py")
            amendment = read(AMENDMENT)
            if amendment["outer_process_concurrency"] != MAX_WORKERS or digest(WORKER) != amendment["worker_sha256"]:
                raise RuntimeError("Parallel amendment/worker hash mismatch")
            journal("parallel_coordinator_start", pid=os.getpid(), amendment_sha256=digest(AMENDMENT))
            run_pool(p, coordinator)
        except Exception as exc:
            # Other paid workers are not killed: their raw evidence remains in
            # independent directories. No more launches or automatic retries.
            status("parallel_stopped_requires_review", error_type=type(exc).__name__, error=str(exc))
            journal("coordinator_error", error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            awake.terminate()


if __name__ == "__main__":
    main()

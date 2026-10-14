#!/usr/bin/env python3
"""Resume missing cost cells, preserving orphaned paid usage and frozen science.

Operational amendment only: do not modify the frozen runner, replace cases, or
retry terminal invalid results. No API request is made without --execute.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import importlib.util
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
COST = PROJECT / "experiments/cost_prior_12case_gpt4o_gemini25pro_b60_v1"
PRIOR = PROJECT / "experiments/prior_fallback_slots_01_03_08_10"
MODEL = "gemini-2.5-pro"
CASE_ID = "08_gemini-2.5-pro_bgb25_condition_trigger"
METHOD = "sa-mcgs"
BALANCE_FLOOR = 707.078988


def load_runner():
    spec = importlib.util.spec_from_file_location("cost_recovery_parent", COST / "run_cost_prior.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    frozen = module.load_json(PRIOR / "frozen_fallback_protocol.json")
    for path, expected in (
        (COST / "run_cost_prior.py", frozen["parent"]["parent_runner_sha256"]),
        (Path(module.cost.__file__), frozen["parent"]["cost_runner_module_sha256"]),
    ):
        if module.file_hash(path) != expected:
            raise RuntimeError(f"Frozen source changed: {path}")
    return module


def combine_usage(current, interrupted):
    if set(current) != set(interrupted):
        raise RuntimeError("Usage schema changed; do not silently drop counters")
    return {key: current[key] + interrupted[key] for key in current}


def validate_no_unhandled_partials(records, terminal_keys):
    for row in records:
        key = (row.get("model"), row.get("case_id"), row.get("method"))
        if key not in terminal_keys and key != (MODEL, CASE_ID, METHOD):
            raise RuntimeError(f"Another interrupted cell requires its own recovery audit: {key}")


def pending_interruption(parent):
    plans = parent.load_validated_plans()
    case = next(row for row in plans[MODEL] if row["case_id"] == CASE_ID)
    target = parent.result_path(parent.COST_DIR, MODEL, case, METHOD)
    all_ledger = list(parent.iter_ledger())
    terminal_keys = {(r.get("model"), r.get("case_id"), r.get("method"))
                     for r in all_ledger if r.get("stage") == "cost"}
    all_records = []
    for source in parent.COST_DIR.glob("*/call_logs/llm_calls.jsonl"):
        all_records.extend(json.loads(line) for line in source.read_text().splitlines() if line.strip())
    validate_no_unhandled_partials(all_records, terminal_keys)
    ledger = [r for r in all_ledger
              if (r.get("model"), r.get("case_id"), r.get("method")) == (MODEL, CASE_ID, METHOD)]
    if target.exists():
        if len(ledger) != 1 or ledger[0]["result_sha256_before_write"] != parent.canonical_hash(parent.load_json(target)):
            raise RuntimeError("Recovered result/ledger binding is inconsistent")
        return case, [], {key: 0 for key in parent.cost.usage_summary([])}
    if ledger:
        raise RuntimeError("Ledger exists without terminal result; manual recovery required")
    partial = [r for r in all_records
               if (r.get("model"), r.get("case_id"), r.get("method")) == (MODEL, CASE_ID, METHOD)]
    if not partial:
        raise RuntimeError("Expected interrupted call records are missing")
    # Repeated call_index values across attempts are legitimate, not duplicates.
    return case, partial, parent.cost.usage_summary(partial)


def append_recovery_note(parent, manifest_path):
    report = COST / "REPORT_ZH.md"
    if not report.exists():
        return
    note = (
        "\n\n## 执行中断与恢复（必须保留的口径）\n\n"
        "Gemini slot 8 SA 首次执行在产生部分调用后被中断，原因未由日志确证；"
        "恢复时没有算法状态 checkpoint，因此同一冻结 cell 从头执行。"
        "这不是首次尝试成功。主表 valid 表示最终输出可用性，不等于首次成功率；"
        "首次尝试分析需将该 cell 记为 interrupted/未获得完整输出。"
        "其 token 与 recorded-call 成本包含中断前全部可观测用量及恢复用量；"
        "无 usage 返回的潜在在途请求无法精确归账，账户余额另作交叉检查。"
        "audit wall-clock 保留恢复执行区间，中断前 API 耗时单列，不能当成一次连续运行。"
        f"详细记录：`{manifest_path}`。\n"
    )
    with report.open("a") as handle:
        handle.write(note)


async def execute(parent, case, partial, usage, manifest_path):
    original_run_method = parent.cost.run_method
    original_guard = parent.assert_budget_for_next_cell
    extra_pending = parent.estimate_usd(MODEL, usage) / 2.0

    def guarded(model, method):
        original_guard(model, method)
        committed = parent.local_xhub_list_estimated_spend() + extra_pending
        reserve = parent.reserve_for_next_cell(model, method)
        if committed + reserve > float(parent.protocol()["budget"]["hard_cap_usd"]):
            raise RuntimeError("Pending interruption usage would exceed the cost budget")

    async def recovered_run_method(args, output_dir, row, method, *other):
        nonlocal extra_pending
        result = await original_run_method(args, output_dir, row, method, *other)
        if partial and (args.model, row["case_id"], method) == (MODEL, CASE_ID, METHOD):
            resumed_usage = dict(result["llm_usage_summary"])
            result["llm_usage_summary"] = combine_usage(resumed_usage, usage)
            result["execution_recovery"] = {
                "schema": "cost_interruption_recovery.v1",
                "first_attempt_status": "interrupted_without_terminal_output",
                "scientific_configuration_changed": False,
                "restored_algorithm_checkpoint": False,
                "final_result_is_first_attempt": False,
                "interrupted_usage": usage,
                "resumed_execution_usage": resumed_usage,
                "manifest": str(manifest_path),
                "manifest_sha256": parent.file_hash(manifest_path),
                "runtime_note": "audit timestamps and logical llm_calls describe the resumed scientific attempt; recorded usage includes all interrupted attempts",
                "unobserved_inflight_request_cost": "unknown; not assumed zero",
            }
            # The parent's original append-only ledger now charges both parts.
            # No paid call occurs between this return and that append.
            extra_pending = 0.0
        return result

    parent.assert_budget_for_next_cell = guarded
    parent.cost.run_method = recovered_run_method
    try:
        await parent.run_cost(smoke_only=False, retry_errors=False, max_new_cells=None)
        parent.make_report()
        append_recovery_note(parent, manifest_path)
    finally:
        parent.assert_budget_for_next_cell = original_guard
        parent.cost.run_method = original_run_method


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    parent = load_runner()
    case, partial, usage = pending_interruption(parent)
    summary = {
        "mode": "execute" if args.execute else "offline_inspection_only",
        "cells": parent.completed_counts()["cost"],
        "pending_case": CASE_ID,
        "interrupted_usage": usage,
        "unledgered_observed_usd": parent.estimate_usd(MODEL, usage) / 2.0,
        "ledger_usd": parent.local_xhub_list_estimated_spend(),
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not args.execute:
        return
    with (HERE / "cost_resume.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        processes = subprocess.run(["/bin/ps", "-axo", "pid=,command="], capture_output=True, text=True, check=True)
        for line in processes.stdout.splitlines():
            pid, command = line.strip().split(None, 1)
            if int(pid) != os.getpid() and Path(command.split()[0]).name.startswith("python") and (
                "run_cost_prior.py cost" in command or
                ("resume_cost_after_interruption.py" in command and "--execute" in command)
            ):
                raise RuntimeError(f"Another cost execution is present (PID {pid})")
        balance = parent.query_xhub_balance()
        # Keeping the parent's full $85 sub-cap also leaves room under $200
        # for the previously audited pre/Stage-1 spending and later prior gate.
        unspent_cost_cap = float(parent.protocol()["budget"]["hard_cap_usd"]) - summary["ledger_usd"]
        if balance["total_available_usd"] - BALANCE_FLOOR < unspent_cost_cap:
            raise RuntimeError("Fresh shared-account budget cross-check failed")
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
        manifest_path = HERE / "recovery" / f"interruption_{stamp}.json"
        manifest = {
            **summary,
            "schema": "cost_interruption_manifest.v1",
            "created_at": datetime.now().astimezone().isoformat(),
            "pid": os.getpid(),
            "balance_snapshot": balance,
            "source_log": str(parent.COST_DIR / MODEL / "call_logs/llm_calls.jsonl"),
            "source_log_sha256_before_resume": parent.file_hash(parent.COST_DIR / MODEL / "call_logs/llm_calls.jsonl"),
            "partial_records": partial,
            "case_uid": case["case_uid"],
            "physical_scc_fingerprint": case["physical_scc_fingerprint"],
            "terminal_result_hashes_before_resume": {str(p): parent.file_hash(p) for p in parent.COST_DIR.glob("*/results/*.json")},
            "policy": "retain terminal valid/invalid cells; restart only missing cells; charge all observed interruption usage; no selection by outcomes",
        }
        parent.cost.atomic_write_json(manifest_path, manifest)
        awake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())])
        try:
            asyncio.run(execute(parent, case, partial, usage, manifest_path))
        finally:
            awake.terminate()


if __name__ == "__main__":
    main()

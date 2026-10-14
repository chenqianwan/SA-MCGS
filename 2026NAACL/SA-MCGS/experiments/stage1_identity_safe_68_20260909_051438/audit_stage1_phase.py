#!/usr/bin/env python3
"""Create an identity/parity/retry/budget gate for one Stage-1 phase."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


RUN_ROOT = Path(__file__).resolve().parent
REPO_ROOT = RUN_ROOT.parents[3]
sys.path.insert(0, str(REPO_ROOT))

from emnlp2026_discussion import run_cost_audit_clean as cost


VARIANTS = [
    "full-sa-mcgs-rerun",
    "no-relation-first-memory",
    "no-critical-pair-ledger-revisit",
    "random-local-window-selection",
]
FORMAL_ORDERS = [8, 14, 17, 18, 20, 39, 40, 44, 60, 69, 70, 71, 72, 73, 74, 79, 80]
INPUT_USD_PER_TOKEN = 2.5 / 1_000_000
OUTPUT_USD_PER_TOKEN = 10.0 / 1_000_000
HARD_BUDGET_USD = 60.0
RANDOM_SEED_BASE = 8229


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [row for row in rows if row.get("ok")]
    prompt = sum(int((row.get("usage") or {}).get("prompt_tokens") or 0) for row in ok)
    completion = sum(int((row.get("usage") or {}).get("completion_tokens") or 0) for row in ok)
    return {
        "recorded_api_calls": len(rows),
        "successful_api_calls": len(ok),
        "failed_api_calls": len(rows) - len(ok),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "estimated_usd": prompt * INPUT_USD_PER_TOKEN + completion * OUTPUT_USD_PER_TOKEN,
    }


def parse_audit(rows: list[dict[str, Any]]) -> dict[str, int]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["logical_request_id"]].append(row)
    out = Counter()
    for attempts in grouped.values():
        attempts.sort(key=lambda row: int(row.get("json_attempt") or 0))
        first_failed = not bool(attempts[0].get("json_parse_ok"))
        succeeded = any(bool(row.get("json_parse_ok")) for row in attempts)
        out["logical_rollouts"] += 1
        out["first_parse_or_transport_failures"] += int(first_failed)
        out["recovered_after_first_failure"] += int(first_failed and succeeded)
        out["exhausted_without_parse"] += int(not succeeded)
        out["explicit_retry_attempts"] += sum(
            int(row.get("json_attempt") or 1) > 1 for row in attempts
        )
    return dict(out)


def marker_check(result: dict[str, Any], variant: str, budget: int) -> tuple[bool, str]:
    if variant == "no-relation-first-memory":
        passed = result.get("relation_first_enabled") is False and int(
            result.get("relation_probe_count") or 0
        ) == 0
        return passed, "relation_first=false and relation_probe_count=0"
    if variant == "no-critical-pair-ledger-revisit":
        fields = [
            "critical_pair_ledger_rows",
            "critical_pair_locked_edges",
            "critical_pair_candidate_edges",
            "critical_pair_revisit_history",
        ]
        passed = all(not (result.get(field) or []) for field in fields)
        return passed, "critical-pair ledger/locked/candidate/revisit are all empty"
    events = result.get("selection_events") or []
    if variant == "random-local-window-selection":
        expected_seed = RANDOM_SEED_BASE + int(result["case_order"]) * 1009
        passed = (
            len(events) == budget
            and {event.get("mode") for event in events} == {"random_local_window"}
            and {event.get("random_seed") for event in events} == {expected_seed}
        )
        return passed, f"{budget}/{budget} random_local_window events with seed={expected_seed}"
    passed = result.get("relation_first_enabled") is True and all(
        event.get("mode") != "random_local_window" for event in events
    )
    return passed, "relation_first=true and selection is not random_local_window"


def historical_costs() -> dict[tuple[int, str], float]:
    wanted = set(VARIANTS[1:])
    totals: dict[tuple[int, str], float] = defaultdict(float)
    roots = REPO_ROOT / "emnlp2026_discussion" / "component_ablation_runs"
    for path in roots.glob("stage1*/call_logs/llm_calls.jsonl"):
        for row in load_jsonl(path):
            order = int(row.get("case_order") or -1)
            variant = row.get("ablation_variant")
            if order not in FORMAL_ORDERS or variant not in wanted or not row.get("ok"):
                continue
            call_usage = row.get("usage") or {}
            totals[(order, variant)] += (
                int(call_usage.get("prompt_tokens") or 0) * INPUT_USD_PER_TOKEN
                + int(call_usage.get("completion_tokens") or 0) * OUTPUT_USD_PER_TOKEN
            )
    expected = {(order, variant) for order in FORMAL_ORDERS for variant in wanted}
    if set(totals) != expected:
        raise RuntimeError(f"Historical projection matrix mismatch: missing={sorted(expected-set(totals))}")
    return totals


def smoke_budget_projection(cell_rows: list[dict[str, Any]], smoke_cost: float) -> dict[str, Any]:
    old = historical_costs()
    case8 = {
        row["variant"]: float(row["estimated_usd"])
        for row in cell_rows
        if int(row["case_order"]) == 8
    }
    if set(case8) != set(VARIANTS):
        raise RuntimeError("Need all four order-8 smoke cells for projection")
    ratios = {
        variant: case8[variant] / old[(8, variant)]
        for variant in VARIANTS[1:]
    }
    projected_three_point = sum(
        sum(old[(order, variant)] for order in FORMAL_ORDERS) * ratios[variant]
        for variant in VARIANTS[1:]
    )
    relative_mean = {
        order: sum(old[(order, variant)] / old[(8, variant)] for variant in VARIANTS[1:]) / 3
        for order in FORMAL_ORDERS
    }
    full_point = case8[VARIANTS[0]] * sum(relative_mean.values())
    formal68_point = projected_three_point + full_point

    # Conservative empirical envelope: apply the largest observed current/old
    # order-8 arm multiplier to all three historical arms, and use the largest
    # per-case historical relative factor across arms to proxy fresh Full.
    max_multiplier = max(ratios.values())
    projected_three_upper = sum(old.values()) * max_multiplier
    relative_max = {
        order: max(old[(order, variant)] / old[(8, variant)] for variant in VARIANTS[1:])
        for order in FORMAL_ORDERS
    }
    full_upper = case8[VARIANTS[0]] * sum(relative_max.values())
    formal68_upper = projected_three_upper + full_upper
    reused_cost = sum(case8.values())
    paid64_point = formal68_point - reused_cost
    paid64_upper = formal68_upper - reused_cost
    total_point = smoke_cost + paid64_point
    total_upper = smoke_cost + paid64_upper
    return {
        "method": (
            "Exact historical 17x3 token costs scaled by each arm's fresh/old order-8 ratio; "
            "fresh Full uses historical per-case relative factors. The conservative envelope uses "
            "the maximum observed arm multiplier and maximum per-case relative factor."
        ),
        "fresh_to_historical_order8_ratios": ratios,
        "historical_17x3_usd": sum(old.values()),
        "formal_68_point_usd": formal68_point,
        "formal_68_conservative_envelope_usd": formal68_upper,
        "nonselectively_reused_order8_quartet_usd": reused_cost,
        "new_paid_64_point_usd": paid64_point,
        "new_paid_64_conservative_envelope_usd": paid64_upper,
        "smoke_actual_usd": smoke_cost,
        "smoke_plus_new64_point_usd": total_point,
        "smoke_plus_new64_conservative_envelope_usd": total_upper,
        "hard_budget_usd": HARD_BUDGET_USD,
        "conservative_headroom_usd": HARD_BUDGET_USD - total_upper,
        "budget_gate_pass": total_upper <= HARD_BUDGET_USD,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["smoke", "formal"], required=True)
    args = parser.parse_args()
    phase_dir = RUN_ROOT / args.phase
    plan = json.loads((phase_dir / "case_plan.json").read_text(encoding="utf-8"))
    protocol = json.loads((phase_dir / "protocol.json").read_text(encoding="utf-8"))
    preflight = json.loads((phase_dir / "case_identity_preflight.json").read_text(encoding="utf-8"))
    graphs = cost.load_graphs(plan)

    local_network = load_jsonl(phase_dir / "call_logs" / "llm_calls.jsonl")
    local_parse = load_jsonl(phase_dir / "call_logs" / "json_parse_attempts.jsonl")
    smoke_network = load_jsonl(RUN_ROOT / "smoke" / "call_logs" / "llm_calls.jsonl")
    smoke_parse = load_jsonl(RUN_ROOT / "smoke" / "call_logs" / "json_parse_attempts.jsonl")
    results: dict[tuple[int, str], tuple[Path, dict[str, Any]]] = {}
    for path in sorted((phase_dir / "results").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        key = (int(payload["case_order"]), payload["ablation_variant"])
        if key in results:
            raise RuntimeError(f"Duplicate result cell: {key}")
        results[key] = (path, payload)

    expected = {(int(case["case_order"]), variant) for case in plan for variant in VARIANTS}
    by_order = {int(case["case_order"]): case for case in plan}
    cell_rows: list[dict[str, Any]] = []
    identity_errors = []
    for order, variant in sorted(expected, key=lambda key: (key[0], VARIANTS.index(key[1]))):
        entry = results.get((order, variant))
        if entry is None:
            cell_rows.append(
                {
                    "case_order": order,
                    "case_id": by_order[order]["case_id"],
                    "variant": variant,
                    "provenance": "missing",
                    "result_present": False,
                    "case_valid": False,
                }
            )
            continue
        path, result = entry
        provenance = "reused_from_smoke" if result.get("formal_cell_provenance") else "phase_local"
        source_network = smoke_network if provenance == "reused_from_smoke" else local_network
        source_parse = smoke_parse if provenance == "reused_from_smoke" else local_parse
        network_rows = [
            row
            for row in source_network
            if int(row.get("case_order") or -1) == order
            and row.get("ablation_variant") == variant
        ]
        parse_rows = [
            row
            for row in source_parse
            if int(row.get("case_order") or -1) == order
            and row.get("ablation_variant") == variant
        ]
        network_usage_all = usage(network_rows)
        attempts = sorted({int(row.get("job_attempt") or 1) for row in network_rows}) or [1]
        final_attempt = max(attempts)
        network_usage_final = usage(
            [row for row in network_rows if int(row.get("job_attempt") or 1) == final_attempt]
        )
        result_usage = result.get("llm_usage_summary") or {}
        usage_fields = [
            "recorded_api_calls",
            "successful_api_calls",
            "failed_api_calls",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        ]
        usage_consistent = all(
            int(result_usage.get(field) or 0) == int(network_usage_final.get(field) or 0)
            for field in usage_fields
        )
        identity_ok = True
        identity_error = None
        try:
            cost.validate_result_case_identity(result, by_order[order], graphs[result["domain"]])
        except Exception as exc:
            identity_ok = False
            identity_error = f"{type(exc).__name__}: {exc}"
            identity_errors.append({"case_order": order, "variant": variant, "error": identity_error})
        marker_ok, marker_detail = marker_check(
            result, variant, int(protocol["budget_rollouts"])
        )
        protocol_fields_ok = (
            result.get("model") == protocol["model"]
            and int(result.get("budget") or -1) == int(protocol["budget_rollouts"])
            and result.get("mcgs_compression_profile") == protocol["compression_profile"]
            and result.get("case_uid") == by_order[order]["case_uid"]
        )
        parse_stats = parse_audit(parse_rows)
        case_error = result.get("component_ablation_error")
        case_valid = bool(
            identity_ok
            and marker_ok
            and protocol_fields_ok
            and usage_consistent
            and not case_error
        )
        cell_rows.append(
            {
                "case_order": order,
                "case_id": result["case_id"],
                "variant": variant,
                "provenance": provenance,
                "result_present": True,
                "identity_ok": identity_ok,
                "identity_error": identity_error,
                "protocol_fields_ok": protocol_fields_ok,
                "toggle_marker_ok": marker_ok,
                "toggle_marker_detail": marker_detail,
                "usage_consistent": usage_consistent,
                "case_level_error": case_error,
                "case_valid": case_valid,
                "network_calls": network_usage_all["recorded_api_calls"],
                "network_successes": network_usage_all["successful_api_calls"],
                "network_failures": network_usage_all["failed_api_calls"],
                **parse_stats,
                "prompt_tokens": network_usage_all["prompt_tokens"],
                "completion_tokens": network_usage_all["completion_tokens"],
                "total_tokens": network_usage_all["total_tokens"],
                "estimated_usd": network_usage_all["estimated_usd"],
                "result_file": str(path),
            }
        )

    case_parity = []
    for order, case in by_order.items():
        rows = [results[key][1] for key in expected if key[0] == order and key in results]
        actual_hashes = {
            json.dumps(row.get("actual_case_identity"), ensure_ascii=False, sort_keys=True)
            for row in rows
        }
        injection_hashes = {
            json.dumps(row.get("planned_injection_identity"), ensure_ascii=False, sort_keys=True)
            for row in rows
        }
        case_parity.append(
            {
                "case_order": order,
                "case_id": case["case_id"],
                "arms_present": len(rows),
                "four_arm_identity_exact": len(rows) == 4 and len(actual_hashes) == 1,
                "four_arm_injection_exact": len(rows) == 4 and len(injection_hashes) == 1,
            }
        )

    by_arm = []
    for variant in VARIANTS:
        rows = [row for row in cell_rows if row["variant"] == variant]
        by_arm.append(
            {
                "variant": variant,
                "cells": len(rows),
                "case_valid": sum(bool(row.get("case_valid")) for row in rows),
                "network_calls": sum(int(row.get("network_calls") or 0) for row in rows),
                "network_failures": sum(int(row.get("network_failures") or 0) for row in rows),
                "logical_rollouts": sum(int(row.get("logical_rollouts") or 0) for row in rows),
                "first_parse_or_transport_failures": sum(
                    int(row.get("first_parse_or_transport_failures") or 0) for row in rows
                ),
                "recovered_after_first_failure": sum(
                    int(row.get("recovered_after_first_failure") or 0) for row in rows
                ),
                "exhausted_without_parse": sum(
                    int(row.get("exhausted_without_parse") or 0) for row in rows
                ),
                "estimated_usd": sum(float(row.get("estimated_usd") or 0) for row in rows),
            }
        )

    balance_rows = load_jsonl(phase_dir / "balance_checkpoints.jsonl")
    balances = [
        row for row in balance_rows if (row.get("account_balance") or {}).get("ok")
    ]
    account_debit = None
    if len(balances) >= 2:
        account_debit = (
            float(balances[0]["account_balance"]["total_available_usd"])
            - float(balances[-1]["account_balance"]["total_available_usd"])
        )

    matrix_complete = set(results) == expected
    protocol_gate = {
        "preflight_case_count_exact": int(preflight.get("validated_cases") or -1) == len(plan),
        "preflight_orders_exact": preflight.get("orders") == [int(case["case_order"]) for case in plan],
        "protocol_variants_exact": protocol.get("variants") == VARIANTS,
        "protocol_model_exact": protocol.get("model") == "gpt-4o",
        "protocol_budget_window_exact": protocol.get("budget_rollouts") == 60
        and protocol.get("window_size") == 4,
        "max_concurrency_at_most_three": int(protocol.get("effective_max_api_concurrency") or 99)
        <= 3,
        "historical_full_rejected_for_strict_pairing": (
            protocol.get("historical_full_parity_audit") or {}
        ).get("strict_contemporaneous_pairing_eligible")
        is False,
        "fresh_full_included": VARIANTS[0] in protocol.get("variants", []),
    }
    smoke_usage = usage(smoke_network)
    projection = smoke_budget_projection(cell_rows, smoke_usage["estimated_usd"]) if args.phase == "smoke" else None
    reuse_manifest = None
    reuse_path = RUN_ROOT / "formal" / "reuse_from_smoke_order8.json"
    if reuse_path.exists():
        reuse_manifest = json.loads(reuse_path.read_text(encoding="utf-8"))

    passed = bool(
        matrix_complete
        and all(row.get("case_valid") for row in cell_rows)
        and all(row["four_arm_identity_exact"] and row["four_arm_injection_exact"] for row in case_parity)
        and all(protocol_gate.values())
        and (projection is None or projection["budget_gate_pass"])
        and (args.phase != "formal" or (reuse_manifest or {}).get("passed") is True)
    )
    gate = {
        "gate_version": "stage1_identity_parity_retry_budget_gate_v1",
        "created_at": now_iso(),
        "phase": args.phase,
        "passed": passed,
        "matrix_complete": matrix_complete,
        "expected_cells": len(expected),
        "observed_cells": len(results),
        "valid_cells": sum(bool(row.get("case_valid")) for row in cell_rows),
        "identity_errors": identity_errors,
        "protocol_gate": protocol_gate,
        "case_parity": case_parity,
        "by_arm": by_arm,
        "cells": cell_rows,
        "phase_local_usage": usage(local_network),
        "smoke_self_usage": smoke_usage,
        "account_balance_cross_check": {
            "available_usd_at_first_checkpoint": (
                balances[0]["account_balance"]["total_available_usd"] if balances else None
            ),
            "available_usd_at_last_checkpoint": (
                balances[-1]["account_balance"]["total_available_usd"] if balances else None
            ),
            "account_wide_debit_usd": account_debit,
            "interpretation": (
                "Auxiliary only: other experiment lines used the same XHub account concurrently. "
                "This phase's token ledger is the attributable cost source of truth."
            ),
        },
        "budget_projection": projection,
        "reuse_manifest": str(reuse_path) if reuse_manifest else None,
        "reuse_manifest_passed": (reuse_manifest or {}).get("passed"),
        "exhausted_policy": (
            "Retain the cell and count it in the strict denominator; do not selectively rerun."
        ),
    }
    write_json(phase_dir / "gate.json", gate)

    with (phase_dir / "cell_gate.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cell_rows[0]))
        writer.writeheader()
        writer.writerows(cell_rows)

    md = [
        f"# Stage-1 {args.phase} 硬门禁",
        "",
        f"结论：**{'PASS' if passed else 'FAIL'}**；matrix {len(results)}/{len(expected)}，valid cells "
        f"{sum(bool(row.get('case_valid')) for row in cell_rows)}/{len(expected)}。",
        "",
        "| Arm | Cells valid | Network fail/calls | Logical first-fail | Recovered | Exhausted | Est. USD |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in by_arm:
        md.append(
            f"| {row['variant']} | {row['case_valid']}/{row['cells']} | "
            f"{row['network_failures']}/{row['network_calls']} | "
            f"{row['first_parse_or_transport_failures']} | "
            f"{row['recovered_after_first_failure']} | {row['exhausted_without_parse']} | "
            f"${row['estimated_usd']:.4f} |"
        )
    md.extend(
        [
            "",
            "- Exhausted rollout 保留在原 arm 的 strict denominator，不整 cell 重跑。",
            f"- 本 phase 本地调用账本：${usage(local_network)['estimated_usd']:.6f}。",
            f"- XHub 账户同期总扣减：${account_debit:.6f}（并行任务污染，仅交叉核验）。"
            if account_debit is not None
            else "- XHub 账户同期总扣减：不可用。",
        ]
    )
    if projection:
        md.extend(
            [
                f"- formal 68 cells 保守经验包络：${projection['formal_68_conservative_envelope_usd']:.6f}。",
                f"- 非选择性复用 order-8 四格后，新付费 64 cells 包络：${projection['new_paid_64_conservative_envelope_usd']:.6f}。",
                f"- smoke + 新付费64总包络：${projection['smoke_plus_new64_conservative_envelope_usd']:.6f} / ${HARD_BUDGET_USD:.2f}，余量 ${projection['conservative_headroom_usd']:.6f}。",
            ]
        )
    (phase_dir / "GATE_ZH.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"phase": args.phase, "passed": passed, "valid": gate["valid_cells"], "expected": len(expected), "projection": projection}, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

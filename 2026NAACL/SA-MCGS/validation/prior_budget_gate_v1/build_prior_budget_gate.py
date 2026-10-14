#!/usr/bin/env python3
"""Offline budget gate builder. It performs no network or paid API calls."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
COST_ROOT = REPO / "experiments" / "cost_prior_12case_gpt4o_gemini25pro_b60_v1"
PROTOCOL = COST_ROOT / "frozen_protocol.json"
AMENDMENT = COST_ROOT / "protocol_amendment_budget_gate.json"
COST_STATUS = COST_ROOT / "execution_status.json"
COST_LEDGER = COST_ROOT / "budget_ledger.jsonl"
PREFLIGHT = COST_ROOT / "preflight" / "case_identity_preflight.json"
PRE_SUMMARY = (
    REPO / "experiments" / "pre_baseline_runs"
    / "pre_baseline_v1_20260909" / "summary.json"
)
MODELS = ("gpt-4o", "gemini-2.5-pro")
PROFILES = ("minus20", "plus20")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_hash(value: Any) -> str:
    data = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def choose_fallback(selectors: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[list[int]]]:
    domains = {"debian", "sec_ex21", "bgb", "cuad"}
    templates = {
        "direct_mutex", "handoff_invariant", "temporal_gate", "condition_trigger"
    }
    scales = Counter({"small": 2, "medium": 1, "large": 1})
    feasible = []
    for combo in itertools.combinations(selectors, 4):
        if {row["domain"] for row in combo} != domains:
            continue
        if {row["template"] for row in combo} != templates:
            continue
        if Counter(row["scale"] for row in combo) != scales:
            continue
        feasible.append((tuple(int(row["slot"]) for row in combo), combo))
    feasible.sort(key=lambda row: row[0])
    if not feasible:
        raise RuntimeError("No exact-balanced four-case fallback exists")
    return [dict(row) for row in feasible[0][1]], [list(row[0]) for row in feasible]


def list_usd(row: dict[str, Any], rates: dict[str, Any]) -> float:
    usage = row.get("usage") or {}
    rate = rates[row["model"]]
    return (
        float(usage.get("prompt_tokens") or 0) * float(rate["input"])
        + float(usage.get("completion_tokens") or 0) * float(rate["output"])
    ) / 1_000_000


def latest_stage1() -> tuple[Path | None, dict[str, Any]]:
    paths = list((REPO / "experiments").glob(
        "stage1_identity_safe_68_*/formal/status.json"
    ))
    if not paths:
        return None, {}
    path = max(paths, key=lambda item: item.stat().st_mtime_ns)
    return path, read_json(path)


def nominal_parity(protocol_sha: str) -> dict[str, Any]:
    checked = 0
    missing = 0
    errors: list[str] = []
    by_model = {}
    for model in MODELS:
        plan_path = COST_ROOT / "preflight" / "plans" / model / "case_plan.json"
        config_path = COST_ROOT / "cost" / model / "run_config.json"
        if not plan_path.exists() or not config_path.exists():
            missing += 12
            by_model[model] = {"checked": 0, "missing": 12, "errors": 0}
            continue
        plan = read_json(plan_path)
        config = read_json(config_path)["method_configs"]["sa-mcgs"]
        expected_config_hash = canonical_hash(config)
        model_checked = model_missing = model_errors = 0
        for case in plan:
            result_path = (
                COST_ROOT / "cost" / model / "results"
                / f"{case['case_id']}__sa-mcgs.json"
            )
            if not result_path.exists():
                missing += 1
                model_missing += 1
                continue
            result = read_json(result_path)
            tests = {
                "protocol": result.get("protocol_sha256") == protocol_sha,
                "model": result.get("model") == model,
                "method": result.get("method") == "sa-mcgs",
                "case_uid": result.get("case_uid") == case.get("case_uid"),
                "physical": result.get("physical_scc_fingerprint")
                == case.get("physical_scc_fingerprint"),
                "injection": result.get("actual_scc_fingerprint")
                == case.get("planned_scc_fingerprint"),
                "budget": result.get("cost_audit_budget") == 60,
                "concurrency": result.get("internal_concurrency") == 1,
                "profile": result.get("relation_prior_profile") == "nominal",
                "config": result.get("experiment_config_sha256")
                == expected_config_hash,
            }
            checked += 1
            model_checked += 1
            failed = [key for key, value in tests.items() if not value]
            if failed:
                model_errors += 1
                errors.append(
                    f"{model}/slot-{case['case_order']}:{','.join(failed)}"
                )
        by_model[model] = {
            "checked": model_checked,
            "missing": model_missing,
            "errors": model_errors,
        }
    return {
        "checked": checked,
        "missing": missing,
        "errors": errors,
        "by_model": by_model,
        "ready": checked == 24 and missing == 0 and not errors,
    }


def make_execution_order(chosen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    sequence = 0
    for case_index, case in enumerate(chosen):
        models = MODELS if case_index % 2 == 0 else tuple(reversed(MODELS))
        for model in models:
            for profile in PROFILES:
                sequence += 1
                result.append({
                    "order": sequence,
                    "slot": int(case["slot"]),
                    "model": model,
                    "profile": profile,
                    "relation_prior_weight": (
                        0.68 if profile == "minus20" else 1.02
                    ),
                })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization-usd", type=float, default=200.0)
    parser.add_argument("--other-spend-usd", type=float, default=0.0)
    parser.add_argument("--closeout-reserve-usd", type=float, default=10.0)
    parser.add_argument("--account-available-usd", type=float)
    args = parser.parse_args()

    protocol = read_json(PROTOCOL)
    amendment = read_json(AMENDMENT)
    selectors = sorted(
        [dict(row) for row in protocol["selection_policy"]["case_selectors"]],
        key=lambda row: int(row["slot"]),
    )

    # Selection is completed using frozen structure before any ledger is read.
    chosen, feasible = choose_fallback(selectors)
    slots = [int(row["slot"]) for row in chosen]
    preflight = read_json(PREFLIGHT)
    identities = {int(row["slot"]): row for row in preflight["cases"]}
    cases = []
    for row in chosen:
        identity = identities[int(row["slot"])]
        cases.append({
            **row,
            "case_uid": identity["case_uid"],
            "physical_scc_fingerprint": identity["physical_scc_fingerprint"],
            "injected_case_fingerprint": identity["injected_case_fingerprint"],
        })

    ledger = read_jsonl(COST_LEDGER)
    rates = amendment["list_rates_usd_per_million_tokens"]
    nominal = [
        row for row in ledger
        if row.get("stage") == "cost" and row.get("method") == "sa-mcgs"
    ]
    observed = defaultdict(list)
    for row in nominal:
        observed[row["model"]].append(row)

    reserves = {}
    for model in MODELS:
        values = [list_usd(row, rates) for row in observed[model]]
        observed_slots = {int(row["case_slot"]) for row in observed[model]}
        maximum = max(values) if values else None
        reserve = max(1.25, 1.5 * maximum if maximum is not None else 0.0)
        reserves[model] = {
            "nominal_observed_cells": len(observed_slots),
            "observed_max_list_price_usd": maximum,
            "next_cell_reserve_usd": reserve,
            "complete_12_case_basis": len(observed_slots) == 12,
        }

    reserve_sum = sum(reserves[model]["next_cell_reserve_usd"] for model in MODELS)
    full_guard = 24 * reserve_sum
    fallback_guard = 8 * reserve_sum
    full_threshold = full_guard + args.closeout_reserve_usd
    fallback_threshold = fallback_guard + args.closeout_reserve_usd

    pre = read_json(PRE_SUMMARY)
    pre_spend = float(pre["usage"]["total_including_paid_smoke"]["estimated_usd"])
    stage1_path, stage1 = latest_stage1()
    stage1_spend = float(
        (stage1.get("self_ledger_all_phases") or {}).get("estimated_usd") or 0
    )
    cost_spend = sum(list_usd(row, rates) for row in ledger)
    known_spend = pre_spend + stage1_spend + cost_spend + args.other_spend_usd
    remaining = args.authorization_usd - known_spend

    cost_status = read_json(COST_STATUS)
    cost_cells = (cost_status.get("cells") or {}).get("cost") or {}
    prior_cells = (cost_status.get("cells") or {}).get("prior_new") or {}
    prior_files = list((COST_ROOT / "prior" / "results").glob("**/*.json"))
    protocol_sha = file_hash(PROTOCOL)
    parity = nominal_parity(protocol_sha)
    conditions = {
        "cost_72_terminal": int(cost_cells.get("missing", 72)) == 0,
        "stage1_terminal": int(stage1.get("remaining_jobs", 68)) == 0,
        "nominal_24_identity_parity": parity["ready"],
        "prior_new_cells_untouched": (
            int(prior_cells.get("attempted", 0)) == 0 and not prior_files
        ),
        "pricing_version_matches": (
            amendment.get("pricing_version")
            == "a42d372ccf0b5dd13ecf71203521f9d2"
        ),
        "fresh_account_balance_supplied": args.account_available_usd is not None,
    }
    all_ready = all(conditions.values())
    account = args.account_available_usd
    if not all_ready:
        decision = "WAIT_FOR_ALL_GATES"
    elif remaining >= full_threshold and account is not None and account >= full_threshold:
        decision = "RUN_FULL_48"
    elif (
        remaining >= fallback_threshold
        and account is not None
        and account >= fallback_threshold
    ):
        decision = "RUN_FALLBACK_16_SLOTS_01_03_08_10"
    else:
        decision = "NO_GO_BUDGET"

    created = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
    fallback = {
        "selection_blind_to_results": True,
        "selection_rule": (
            "Enumerate 4-case subsets with one case per domain, one per "
            "template, scales small/medium/large=2/1/1; choose the "
            "lexicographically smallest slot tuple."
        ),
        "feasible_slot_sets": feasible,
        "selected_slots": slots,
        "cases": cases,
        "new_paid_cells": 16,
        "nominal_reuse_cells": 8,
        "strict_denominator_per_model_profile": 4,
        "execution_order": make_execution_order(chosen),
        "no_outcome_directed_replacement": True,
        "no_adaptive_promotion_after_first_prior_call": True,
        "required_output_isolation": (
            "Use a new prior_fallback_slots_01_03_08_10 directory; "
            "do not mix with full-12 prior outputs."
        ),
    }
    payload = {
        "schema_version": "prior_budget_gate_v1",
        "generated_at": created,
        "network_calls": 0,
        "paid_calls_started": 0,
        "decision": decision,
        "decision_is_provisional": not all_ready,
        "projection": {
            "policy": (
                "For each model use max(USD 1.25, 1.5 times maximum observed "
                "nominal SA-MCGS XHub-list cell), multiplied by new-cell count."
            ),
            "provisional": not all(
                reserves[model]["complete_12_case_basis"] for model in MODELS
            ),
            "reserves_by_model": reserves,
            "full_48": {
                "cases": 12,
                "new_cells": 48,
                "new_cells_per_model": 24,
                "guard_usd": full_guard,
                "closeout_reserve_usd": args.closeout_reserve_usd,
                "launch_threshold_usd": full_threshold,
            },
            "fallback_16": {
                "cases": 4,
                "new_cells": 16,
                "new_cells_per_model": 8,
                "guard_usd": fallback_guard,
                "closeout_reserve_usd": args.closeout_reserve_usd,
                "launch_threshold_usd": fallback_threshold,
            },
        },
        "global_budget": {
            "authorization_usd": args.authorization_usd,
            "formula": (
                "authorization - pre_final - stage1_final - cost_final "
                "- other_paid"
            ),
            "pre_attributed_usd": pre_spend,
            "stage1_attributed_snapshot_usd": stage1_spend,
            "cost_attributed_snapshot_usd": cost_spend,
            "other_paid_declared_usd": args.other_spend_usd,
            "known_attributed_spend_usd": known_spend,
            "authorization_remaining_snapshot_usd": remaining,
            "account_available_usd": account,
            "shared_account_delta_is_not_attribution": True,
        },
        "readiness": {
            "all_pass": all_ready,
            "conditions": conditions,
            "cost_status": {
                "state": cost_status.get("state"),
                "attempted": cost_cells.get("attempted", 0),
                "missing": cost_cells.get("missing", 72),
                "updated_at": cost_status.get("updated_at"),
            },
            "stage1_status": {
                "path": str(stage1_path) if stage1_path else None,
                "state": stage1.get("state"),
                "completed_jobs": stage1.get("completed_jobs", 0),
                "remaining_jobs": stage1.get("remaining_jobs", 68),
                "updated_at": stage1.get("updated_at"),
            },
            "nominal_parity": parity,
        },
        "fallback": fallback,
        "protocol_audit": {
            "frozen_protocol_path": str(PROTOCOL),
            "frozen_protocol_sha256": protocol_sha,
            "budget_amendment_path": str(AMENDMENT),
            "budget_amendment_sha256": file_hash(AMENDMENT),
            "pricing_version": amendment["pricing_version"],
            "old_local_hard_cap_usd": protocol["budget"]["hard_cap_usd"],
            "old_runner_prior_command_is_not_authorized": True,
            "reason": (
                "It gates against the old USD 85 line cap and has no frozen "
                "fallback slot scope."
            ),
        },
        "snapshot_inputs": {
            "cost_ledger_sha256": file_hash(COST_LEDGER),
            "cost_status_sha256": file_hash(COST_STATUS),
            "pre_summary_sha256": file_hash(PRE_SUMMARY),
            "stage1_status_sha256": (
                file_hash(stage1_path) if stage1_path else None
            ),
        },
    }
    subset_payload = {
        "schema_version": "prior_fallback_subset_v1",
        "frozen_at": created,
        "selection_input": {
            "protocol_sha256": protocol_sha,
            "preflight_sha256": file_hash(PREFLIGHT),
        },
        **fallback,
    }
    write_json(HERE / "prior_budget_gate.json", payload)
    write_json(HERE / "fallback_subset.json", subset_payload)
    print(json.dumps({"decision": decision, "output": str(HERE)}))


if __name__ == "__main__":
    main()

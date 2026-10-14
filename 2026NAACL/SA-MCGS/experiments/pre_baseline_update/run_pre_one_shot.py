#!/usr/bin/env python3
"""Run the frozen two-model one-shot baseline on the 18 pre SCCs.

The runner is deliberately separate from every injected/post runner.  It
reconstructs the frozen unmodified SCCs, validates their content-derived
identities before any paid call, records every API call, and treats terminal
API/JSON/schema failures as strict-invalid outcomes.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import re
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from emnlp2026_discussion import run_cost_audit_clean as cost

LEA_UPDATE_DIR = REPO_ROOT / "2026NAACL/SA-MCGS/experiments/lea_update"
sys.path.insert(0, str(LEA_UPDATE_DIR))
import run_pre_lea as pre


DEFAULT_RUNS_DIR = (
    REPO_ROOT / "2026NAACL/SA-MCGS/experiments/pre_baseline_runs"
)
DEFAULT_MODELS = ["gpt-4o", "gemini-2.5-pro"]
ONE_SHOT_IDENTITY_VERSION = "pre_one_shot_case_identity_v1"
ONE_SHOT_PROTOCOL_VERSION = "pre_one_shot_protocol_v1"
NAIVE_PROFILE = "direct_subgraph"
PRICING_VERSION = "a42d372ccf0b5dd13ecf71203521f9d2"
QUOTA_PER_USD = 500_000
MODEL_PRICING = {
    "gpt-4o": {"model_ratio": 1.25, "completion_ratio": 4.0},
    "gemini-2.5-pro": {"model_ratio": 0.625, "completion_ratio": 8.0},
}


class PreOneShotRunError(RuntimeError):
    pass


class StrictOneShotLoggingClient(pre.StrictPreLoggingClient):
    """Apply the frozen strict schema to whole-SCC bullet-form prompts."""

    async def call_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        retries: int = 2,
    ) -> dict[str, Any]:
        if self._terminal_failure_latched:
            raise pre.StrictJSONError(self._terminal_failure_latched)
        expected_ids = re.findall(
            r"^-\s*ID:\s*(.+?)\s*$", prompt, flags=re.MULTILINE
        )
        if not expected_ids:
            message = "runner could not recover exact SCC IDs from the one-shot prompt"
            self._record_terminal_json_failure([], 0, message)
            raise pre.StrictJSONError(message)
        for attempt in range(1, retries + 2):
            try:
                response = await self.call(
                    prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt,
                    response_format={"type": "json_object"},
                )
            except Exception as exc:
                message = f"API failure: {type(exc).__name__}: {exc}"
                self._record_terminal_json_failure(expected_ids, attempt, message)
                raise pre.StrictJSONError(message) from exc

            parsed = self._extract_json(response.content)
            error = pre.schema_error(parsed, expected_ids)
            if error is None:
                return parsed
            diagnostic = {
                **self.context,
                "event": "json_schema_attempt_failure",
                "recorded_at": pre.now_iso(),
                "attempt": attempt,
                "expected_window_ids": expected_ids,
                "error": error,
            }
            self.json_validation_attempt_failures.append(diagnostic)
            cost.append_jsonl(self.call_log_path, diagnostic)
            if attempt <= retries:
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
                continue
            self._record_terminal_json_failure(expected_ids, attempt, error)
            raise pre.StrictJSONError(error)
        raise AssertionError("unreachable")


def estimate_usd(model: str, usage: dict[str, Any]) -> float | None:
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return None
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    weighted = pricing["model_ratio"] * (
        prompt + pricing["completion_ratio"] * completion
    )
    return weighted / QUOTA_PER_USD


def protocol(args: argparse.Namespace) -> dict[str, Any]:
    value = {
        "version": ONE_SHOT_PROTOCOL_VERSION,
        "method": "one-shot",
        "implementation": "battle.run_naive",
        "naive_profile": NAIVE_PROFILE,
        "input_scope": "full_frozen_pre_scc",
        "temperature": args.temperature,
        "response_format": {"type": "json_object"},
        "strict_schema": "pre.StrictPreLoggingClient/schema_error",
        "abstention_rule_version": pre.ABSTENTION_RULE_VERSION,
    }
    value["fingerprint"] = pre.sha256_json(value)
    return value


def build_plan(
    sources: list[dict[str, Any]], models: list[str], args: argparse.Namespace
) -> list[dict[str, Any]]:
    if not models or len(models) != len(set(models)):
        raise ValueError("--models must contain distinct aliases")
    selected = set(args.source_ids or [])
    known = {str(source["pre_source_id"]) for source in sources}
    unknown = sorted(selected - known)
    if unknown:
        raise PreOneShotRunError(f"unknown --source-ids: {unknown}")

    frozen_protocol = protocol(args)
    plan: list[dict[str, Any]] = []
    for model in models:
        for source in sources:
            source_id = str(source["pre_source_id"])
            if selected and source_id not in selected:
                continue
            identity = {
                "version": ONE_SHOT_IDENTITY_VERSION,
                "model": model,
                "method": "one-shot",
                "pre_content_fingerprint": source["pre_content_fingerprint"],
                "one_shot_protocol_fingerprint": frozen_protocol["fingerprint"],
            }
            plan.append(
                {
                    "case_order": len(plan) + 1,
                    "case_id": pre.safe_token(f"{source_id}__{model}__one-shot"),
                    "case_uid": pre.sha256_json(identity),
                    "case_identity": identity,
                    "condition": "pre",
                    "inject_mode": False,
                    "method": "one-shot",
                    "model": model,
                    "domain": source["domain"],
                    "scc_id": source_id,
                    "scc_size": int(source["source_scc_size"]),
                    "pre_source_id": source_id,
                    "source_physical_fingerprint": source[
                        "source_physical_fingerprint"
                    ],
                    "pre_content_fingerprint": source["pre_content_fingerprint"],
                    "dataset_revision": source["dataset_revision"],
                    "ordered_clause_ids": list(source["ordered_clause_ids"]),
                    "one_shot_protocol": copy.deepcopy(frozen_protocol),
                }
            )
    return plan


def plan_fingerprint(plan: list[dict[str, Any]]) -> str:
    return pre.sha256_json(
        [
            {
                "case_uid": case["case_uid"],
                "case_order": case["case_order"],
                "model": case["model"],
                "pre_content_fingerprint": case["pre_content_fingerprint"],
                "one_shot_protocol_fingerprint": case["one_shot_protocol"][
                    "fingerprint"
                ],
            }
            for case in plan
        ]
    )


def persist_or_check_plan(
    output_dir: Path, plan: list[dict[str, Any]], rebuild: bool
) -> None:
    path = output_dir / "case_plan.json"
    if path.exists() and not rebuild:
        old = json.loads(path.read_text(encoding="utf-8"))
        if plan_fingerprint(old) != plan_fingerprint(plan):
            raise PreOneShotRunError(
                f"existing plan differs in {output_dir}; use a new directory"
            )
    pre.atomic_write_json(path, plan)
    pre.atomic_write_csv(output_dir / "case_plan.csv", plan)


def result_path(output_dir: Path, case: dict[str, Any]) -> Path:
    return output_dir / "results" / f"{case['case_id']}__one-shot.json"


def validate_result_identity(result: dict[str, Any], case: dict[str, Any]) -> None:
    checks = (
        "case_uid",
        "model",
        "domain",
        "pre_source_id",
        "source_physical_fingerprint",
        "pre_content_fingerprint",
        "dataset_revision",
    )
    differences = [key for key in checks if result.get(key) != case.get(key)]
    if result.get("condition") != "pre" or result.get("inject_mode") is not False:
        differences.append("condition/inject_mode")
    if result.get("unmodified") is not True:
        differences.append("unmodified")
    if result.get("method") != "one-shot":
        differences.append("method")
    expected_protocol = case["one_shot_protocol"]
    protocol_body = {
        key: value for key, value in expected_protocol.items() if key != "fingerprint"
    }
    if pre.sha256_json(protocol_body) != expected_protocol.get("fingerprint"):
        differences.append("planned_one_shot_protocol_fingerprint")
    if result.get("one_shot_protocol") != expected_protocol:
        differences.append("one_shot_protocol")
    if result.get("one_shot_protocol_fingerprint") != expected_protocol["fingerprint"]:
        differences.append("one_shot_protocol_fingerprint")
    if result.get("case_identity") != case["case_identity"]:
        differences.append("case_identity")
    if list(result.get("scc_clause_ids") or []) != list(case["ordered_clause_ids"]):
        differences.append("scc_clause_ids")
    if differences:
        raise PreOneShotRunError(
            f"existing result identity mismatch for {case['case_id']}: {differences}"
        )


def make_llm(
    args: argparse.Namespace, output_dir: Path, case: dict[str, Any]
) -> StrictOneShotLoggingClient:
    model_id = cost.MODEL_IDS.get(case["model"], case["model"])
    return StrictOneShotLoggingClient(
        {
            "provider": "openai",
            "model": model_id,
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
            "timeout": args.llm_timeout,
            "max_retries": args.llm_max_retries,
        },
        call_log_path=output_dir / "call_logs" / "llm_calls.jsonl",
        context={
            "run_id": output_dir.name,
            "case_id": case["case_id"],
            "case_order": case["case_order"],
            "condition": "pre",
            "domain": case["domain"],
            "scc_id": case["scc_id"],
            "scc_size": case["scc_size"],
            "method": "one-shot",
            "model": case["model"],
            "case_concurrency": args.case_concurrency,
            "internal_concurrency": 1,
        },
    )


def null_ground_truth_metrics(result: dict[str, Any]) -> None:
    result.update(
        {
            "ground_truth_nodes": None,
            "gt_evidence": None,
            "top1_hit": None,
            "top3_hit": None,
            "root_at_3": None,
            "risk_any": None,
            "risk_all": None,
            "injected_node": None,
            "inject_type": None,
            "inject_profile": None,
            "injected_risk_nodes": None,
            "injected_evidence_nodes": None,
            "injected_affected_nodes": None,
            "injected_ground_truth_available": False,
        }
    )
    for key in list(result):
        lower = key.lower()
        if (
            lower.startswith(("root_", "risk_", "affected_", "valuable_"))
            and lower.endswith(("_hit", "_rank", "_coverage", "_retained"))
        ) or (
            (
                "contains_" in lower
                or lower.endswith("_coverage")
                or lower.endswith("_retained")
            )
            and any(
                token in lower
                for token in ("risk", "evidence", "affected", "valuable")
            )
        ):
            result[key] = None


async def run_case(
    args: argparse.Namespace,
    output_dir: Path,
    case: dict[str, Any],
    reconstructed: dict[str, Any],
) -> dict[str, Any]:
    original_graph, original_scc = reconstructed[case["pre_source_id"]]
    graph = copy.deepcopy(original_graph)
    scc = copy.deepcopy(original_scc)
    llm = make_llm(args, output_dir, case)
    started_at = time.time()
    caught_error: str | None = None
    try:
        result = await cost.battle.run_naive(
            llm,
            case["model"],
            case["domain"],
            graph,
            scc,
            naive_profile=NAIVE_PROFILE,
            injected_id=None,
            temperature=args.temperature,
        )
    except Exception as exc:
        caught_error = f"{type(exc).__name__}: {exc}"
        result = {
            "method": "one-shot",
            "model": case["model"],
            "domain": case["domain"],
            "scc_id": case["scc_id"],
            "scc_size": case["scc_size"],
            "scc_clause_ids": list(scc.clause_ids),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    finally:
        await llm.close()

    usage = cost.usage_summary(llm.call_records)
    invalid_reasons: list[str] = []
    if caught_error:
        invalid_reasons.append(caught_error)
    if int(usage.get("failed_api_calls") or 0):
        invalid_reasons.append(f"{usage['failed_api_calls']} failed API call(s)")
    if llm.terminal_json_failures:
        invalid_reasons.append(
            f"{len(llm.terminal_json_failures)} terminal JSON/API failure(s)"
        )

    pairs, rejected = pre.filter_explicit_pairs(
        result.get("conflicts", []), list(scc.clause_ids)
    )
    invalid = bool(invalid_reasons)
    decision = (
        "invalid"
        if invalid
        else "assert_target_conflict"
        if pairs
        else "abstain_from_target_conflict"
    )
    null_ground_truth_metrics(result)
    result.update(
        {
            "method": "one-shot",
            "case_id": case["case_id"],
            "case_order": case["case_order"],
            "case_uid": case["case_uid"],
            "case_identity": copy.deepcopy(case["case_identity"]),
            "condition": "pre",
            "inject_mode": False,
            "unmodified": True,
            "cycle_source": "naturally_occurring_structural_scc",
            "natural_risk_label_pending_expert": True,
            "pre_source_id": case["pre_source_id"],
            "source_physical_fingerprint": case["source_physical_fingerprint"],
            "pre_content_fingerprint": case["pre_content_fingerprint"],
            "dataset_revision": case["dataset_revision"],
            "one_shot_protocol": copy.deepcopy(case["one_shot_protocol"]),
            "one_shot_protocol_fingerprint": case["one_shot_protocol"][
                "fingerprint"
            ],
            "abstention_rule_version": pre.ABSTENTION_RULE_VERSION,
            "abstention_rule": (
                "Accept a target-conflict assertion only when a raw conflicts item "
                "contains two distinct exact SCC IDs and a nonempty reason."
            ),
            "target_conflict_decision": decision,
            "explicit_conflict_pairs": pairs,
            "explicit_conflict_pair_count": len(pairs),
            "rejected_raw_conflict_count": rejected,
            "abstention_eligible": not invalid,
            "json_validation_attempt_failure_count": len(
                llm.json_validation_attempt_failures
            ),
            "terminal_json_failure_count": len(llm.terminal_json_failures),
            "llm_usage_summary": usage,
            "estimated_usd": estimate_usd(case["model"], usage),
            "pricing_version": PRICING_VERSION,
            "cost_audit_method": "one-shot",
            "cost_audit_error": "; ".join(invalid_reasons) if invalid else None,
            "audit_started_at": started_at,
            "audit_completed_at": time.time(),
            "audit_started_at_iso": time.strftime(
                "%Y-%m-%dT%H:%M:%S%z", time.localtime(started_at)
            ),
            "audit_completed_at_iso": pre.now_iso(),
            "case_concurrency": args.case_concurrency,
            "internal_concurrency": 1,
        }
    )
    return result


def mean(values: list[Any]) -> float | None:
    numeric = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return sum(numeric) / len(numeric) if numeric else None


def load_result_rows(output_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((output_dir / "results").glob("*__one-shot.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        usage = result.get("llm_usage_summary") or {}
        rows.append(
            {
                "case_order": result.get("case_order"),
                "case_id": result.get("case_id"),
                "case_uid": result.get("case_uid"),
                "model": result.get("model"),
                "domain": result.get("domain"),
                "pre_source_id": result.get("pre_source_id"),
                "scc_size": result.get("scc_size"),
                "condition": result.get("condition"),
                "invalid_output": bool(result.get("cost_audit_error")),
                "target_conflict_decision": result.get("target_conflict_decision"),
                "explicit_conflict_pair_count": result.get(
                    "explicit_conflict_pair_count"
                ),
                "direct_compression": result.get("direct_compression_ratio"),
                "llm_calls": result.get("llm_calls"),
                "recorded_api_calls": usage.get("recorded_api_calls"),
                "successful_api_calls": usage.get("successful_api_calls"),
                "failed_api_calls": usage.get("failed_api_calls"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "estimated_usd": result.get("estimated_usd"),
                "runtime_sec": result.get("time"),
                "source_physical_fingerprint": result.get(
                    "source_physical_fingerprint"
                ),
                "pre_content_fingerprint": result.get("pre_content_fingerprint"),
                "result_file": str(path),
            }
        )
    return rows


def summarize(output_dir: Path) -> None:
    rows = load_result_rows(output_dir)
    if not rows:
        return
    pre.atomic_write_csv(output_dir / "summary_pre_one_shot_cases.csv", rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped["overall"].append(row)
        grouped[f"model={row['model']}"].append(row)
        grouped[f"domain={row['domain']}"].append(row)
        grouped[f"model={row['model']}|domain={row['domain']}"].append(row)
    breakdown: list[dict[str, Any]] = []
    for group, items in sorted(grouped.items()):
        valid = [item for item in items if not item["invalid_output"]]
        assertions = sum(
            item["target_conflict_decision"] == "assert_target_conflict"
            for item in valid
        )
        breakdown.append(
            {
                "group": group,
                "attempted_N": len(items),
                "invalid_N": len(items) - len(valid),
                "valid_N": len(valid),
                "assert_target_conflict_N": assertions,
                "abstain_from_target_conflict_N": sum(
                    item["target_conflict_decision"]
                    == "abstain_from_target_conflict"
                    for item in valid
                ),
                "strict_assert_rate_all": assertions / len(items),
                "invalid_rate_all": (len(items) - len(valid)) / len(items),
                "direct_compression_valid_mean": mean(
                    [item["direct_compression"] for item in valid]
                ),
                "calls_total": sum(int(item["recorded_api_calls"] or 0) for item in items),
                "prompt_tokens_total": sum(
                    int(item["prompt_tokens"] or 0) for item in items
                ),
                "completion_tokens_total": sum(
                    int(item["completion_tokens"] or 0) for item in items
                ),
                "total_tokens": sum(int(item["total_tokens"] or 0) for item in items),
                "estimated_usd": sum(float(item["estimated_usd"] or 0) for item in items),
            }
        )
    pre.atomic_write_csv(
        output_dir / "summary_pre_one_shot_breakdown.csv", breakdown
    )


def current_estimated_usd(output_dir: Path) -> float:
    return sum(float(row["estimated_usd"] or 0) for row in load_result_rows(output_dir))


def write_status(
    output_dir: Path,
    plan: list[dict[str, Any]],
    args: argparse.Namespace,
    *,
    phase: str,
    active: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    completed = 0
    failed = 0
    for case in plan:
        path = result_path(output_dir, case)
        if not path.exists():
            continue
        completed += 1
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            validate_result_identity(result, case)
            if result.get("cost_audit_error"):
                failed += 1
        except Exception:
            failed += 1
    spent = current_estimated_usd(output_dir)
    status = {
        "run_id": output_dir.name,
        "updated_at": pre.now_iso(),
        "phase": phase,
        "condition": "pre",
        "inject_mode": False,
        "method": "one-shot",
        "models": args.models,
        "total_cases": len(plan),
        "completed_cases": completed,
        "failed_cases": failed,
        "remaining_cases": len(plan) - completed,
        "case_concurrency": args.case_concurrency,
        "active": active or [],
        "budget_usd": args.budget_usd,
        "estimated_spent_usd": spent,
        "estimated_budget_remaining_usd": args.budget_usd - spent,
        "pricing_version": PRICING_VERSION,
        "result_dir": str(output_dir / "results"),
        "call_log": str(output_dir / "call_logs" / "llm_calls.jsonl"),
    }
    pre.atomic_write_json(output_dir / "status.json", status)
    return status


def build_preflight(
    args: argparse.Namespace,
    sources: list[dict[str, Any]],
    plan: list[dict[str, Any]],
) -> dict[str, Any]:
    domains = Counter(str(source["domain"]) for source in sources)
    return {
        "validated_at": pre.now_iso(),
        "validation_only": bool(args.validate_only or args.dry_run),
        "api_calls_made_by_preflight": 0,
        "identity_version": ONE_SHOT_IDENTITY_VERSION,
        "source_identity_version": pre.PRE_IDENTITY_VERSION,
        "abstention_rule_version": pre.ABSTENTION_RULE_VERSION,
        "source_json": str(args.source_json),
        "source_json_sha256": pre.file_sha256(args.source_json),
        "validated_sources": len(sources),
        "validated_domains": dict(sorted(domains.items())),
        "all_sources_exactly_one_tarjan_scc": True,
        "models": list(args.models),
        "planned_model_cases": len(plan),
        "planned_source_ids": [case["pre_source_id"] for case in plan],
        "plan_fingerprint": plan_fingerprint(plan),
        "one_shot_protocol": protocol(args),
        "strict_denominator": "all attempted model-case cells",
        "pricing_version": PRICING_VERSION,
        "budget_usd": args.budget_usd,
    }


async def run(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    call_log = output_dir / "call_logs" / "llm_calls.jsonl"
    call_log.parent.mkdir(parents=True, exist_ok=True)
    call_log.touch(exist_ok=True)

    sources, reconstructed = pre.load_and_validate_sources(args.source_json)
    plan = build_plan(sources, args.models, args)
    persist_or_check_plan(output_dir, plan, args.rebuild_plan)
    for case in plan:
        path = result_path(output_dir, case)
        if path.exists():
            validate_result_identity(json.loads(path.read_text(encoding="utf-8")), case)

    preflight = build_preflight(args, sources, plan)
    pre.atomic_write_json(output_dir / "case_identity_preflight.json", preflight)
    pre.atomic_write_json(
        output_dir / "run_config.json",
        {
            "created_or_updated_at": pre.now_iso(),
            "source_json": str(args.source_json),
            "source_json_sha256": preflight["source_json_sha256"],
            "models": args.models,
            "resolved_model_ids": {
                model: cost.MODEL_IDS.get(model, model) for model in args.models
            },
            "condition": "pre",
            "inject_mode": False,
            "method": "one-shot",
            "one_shot_protocol": protocol(args),
            "case_concurrency": args.case_concurrency,
            "llm_timeout": args.llm_timeout,
            "llm_max_retries": args.llm_max_retries,
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
            "plan_fingerprint": preflight["plan_fingerprint"],
            "budget_usd": args.budget_usd,
            "pricing_version": PRICING_VERSION,
            "model_pricing": MODEL_PRICING,
            "quota_per_usd": QUOTA_PER_USD,
        },
    )
    phase = "validated" if args.validate_only or args.dry_run else "ready"
    write_status(output_dir, plan, args, phase=phase)
    summarize(output_dir)
    if args.validate_only or args.dry_run:
        return
    if not os.environ.get(args.api_key_env):
        raise RuntimeError(f"{args.api_key_env} is not set")

    active: dict[str, dict[str, Any]] = {}
    active_lock = asyncio.Lock()
    summarize_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(args.case_concurrency)
    budget_exhausted = False

    async def worker(case: dict[str, Any]) -> None:
        nonlocal budget_exhausted
        path = result_path(output_dir, case)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            validate_result_identity(existing, case)
            if not args.retry_errors or not existing.get("cost_audit_error"):
                return
        async with semaphore:
            async with active_lock:
                if current_estimated_usd(output_dir) >= args.budget_usd:
                    budget_exhausted = True
                    return
                entry = {
                    "case_id": case["case_id"],
                    "case_order": case["case_order"],
                    "model": case["model"],
                    "domain": case["domain"],
                    "pre_source_id": case["pre_source_id"],
                    "scc_size": case["scc_size"],
                    "started_at": pre.now_iso(),
                }
                active[case["case_id"]] = entry
                write_status(
                    output_dir, plan, args, phase="running", active=list(active.values())
                )
            result = await run_case(args, output_dir, case, reconstructed)
            pre.atomic_write_json(path, result)
            async with summarize_lock:
                summarize(output_dir)
            async with active_lock:
                active.pop(case["case_id"], None)
                write_status(
                    output_dir, plan, args, phase="running", active=list(active.values())
                )

    await asyncio.gather(*(worker(case) for case in plan))
    summarize(output_dir)
    final_status = write_status(output_dir, plan, args, phase="complete")
    if budget_exhausted or final_status["remaining_cases"]:
        write_status(output_dir, plan, args, phase="stopped_budget_guard")
        raise PreOneShotRunError(
            "run stopped at the configured one-shot budget guard; resume only after review"
        )
    if final_status["estimated_spent_usd"] > args.budget_usd:
        write_status(output_dir, plan, args, phase="complete_over_budget")
        raise PreOneShotRunError("recorded usage exceeded --budget-usd")
    if final_status["failed_cases"]:
        write_status(output_dir, plan, args, phase="complete_with_errors")
        raise PreOneShotRunError(
            f"{final_status['failed_cases']} result(s) failed strict validation; "
            "retain them as first-attempt reliability outcomes"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one-shot on frozen, unmodified pre-injection SCCs."
    )
    parser.add_argument("--source-json", type=Path, default=pre.DEFAULT_SOURCE_JSON)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--source-ids", nargs="*", default=None)
    parser.add_argument("--case-concurrency", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--base-url", default=cost.battle.XHUB_BASE_URL)
    parser.add_argument("--api-key-env", default="XHUB_API_KEY")
    parser.add_argument("--llm-timeout", type=float, default=900)
    parser.add_argument("--llm-max-retries", type=int, default=5)
    parser.add_argument("--budget-usd", type=float, default=10.0)
    parser.add_argument("--rebuild-plan", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.output_dir is None:
        run_id = time.strftime("one_shot_pre18_%Y%m%d_%H%M%S", time.localtime())
        args.output_dir = DEFAULT_RUNS_DIR / run_id
    args.source_json = args.source_json.resolve()
    args.output_dir = args.output_dir.resolve()
    if not 1 <= args.case_concurrency <= 3:
        parser.error("--case-concurrency must be between 1 and 3")
    if args.budget_usd <= 0:
        parser.error("--budget-usd must be positive")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))

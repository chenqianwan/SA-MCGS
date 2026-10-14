#!/usr/bin/env python3
"""Identity-safe, auditable Stage-1 four-arm runner.

This wrapper deliberately keeps all new artifacts under its own run directory.
It reuses the tested component-ablation implementation, but runs a fresh Full
arm because the historical Full rows did not record prompt/config hashes.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import csv
import hashlib
import inspect
import json
import math
import os
import random
import shutil
import sys
import time
import traceback
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any


RUN_ROOT = Path(__file__).resolve().parent
REPO_ROOT = RUN_ROOT.parents[3]
sys.path.insert(0, str(REPO_ROOT))

from emnlp2026_discussion import run_component_ablation_stage0 as ablation
from emnlp2026_discussion import run_cost_audit_clean as cost
from experiments.cross_domain import run_cross_domain_battle as battle
from src.modules.alphago_mcgs import AlphaGoMCGS


FULL = "full-sa-mcgs-rerun"
VARIANTS = [
    FULL,
    "no-relation-first-memory",
    "no-critical-pair-ledger-revisit",
    "random-local-window-selection",
]
LABELS = {
    FULL: "Full SA-MCGS (contemporaneous rerun)",
    "no-relation-first-memory": "No relation-first memory",
    "no-critical-pair-ledger-revisit": "No critical-pair ledger/revisit",
    "random-local-window-selection": "Random local-window selection",
}
SMOKE_ORDERS = [1, 8, 19]
FORMAL_ORDERS = [8, 14, 17, 18, 20, 39, 40, 44, 60, 69, 70, 71, 72, 73, 74, 79, 80]
CANONICAL_PLAN = (
    REPO_ROOT
    / "2026NAACL"
    / "SA-MCGS"
    / "validation"
    / "identity_stage2_80"
    / "case_plan.json"
)
RERUN_SCOPE = REPO_ROOT / "2026NAACL" / "SA-MCGS" / "manifests" / "rerun_scope.json"
MAIN_MANIFEST = REPO_ROOT / "experiments" / "main_experiment" / "MANIFEST.json"

# XHub's public price registry reports model_ratio=1.25 and completion_ratio=4
# for gpt-4o. With quota_per_unit=500000 these are $2.50/M input and
# $10.00/M output tokens. Values are re-fetched and frozen in protocol.json.
QUOTA_PER_USD = 500_000
DEFAULT_INPUT_USD_PER_TOKEN = 2.5 / 1_000_000
DEFAULT_OUTPUT_USD_PER_TOKEN = 10.0 / 1_000_000
HARD_BUDGET_USD = 60.0
PER_CALL_RESERVATION_USD = 0.06


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def usage_cost(records: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [row for row in records if row.get("ok")]
    prompt = sum(int((row.get("usage") or {}).get("prompt_tokens") or 0) for row in ok)
    completion = sum(int((row.get("usage") or {}).get("completion_tokens") or 0) for row in ok)
    estimated = prompt * DEFAULT_INPUT_USD_PER_TOKEN + completion * DEFAULT_OUTPUT_USD_PER_TOKEN
    return {
        "recorded_api_calls": len(records),
        "successful_api_calls": len(ok),
        "failed_api_calls": len(records) - len(ok),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "estimated_usd": estimated,
    }


def all_run_usage() -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for path in sorted(RUN_ROOT.glob("*/call_logs/llm_calls.jsonl")):
        records.extend(read_jsonl(path))
    return usage_cost(records)


def query_balance() -> dict[str, Any]:
    key = os.environ.get("XHUB_API_KEY")
    if not key:
        return {"ok": False, "error": "XHUB_API_KEY is not set", "checked_at": now_iso()}
    request = urllib.request.Request(
        "https://api3.xhub.chat/api/usage/token/",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        data = payload.get("data") or {}
        return {
            "ok": True,
            "checked_at": now_iso(),
            "total_granted_usd": float(data["total_granted"]) / QUOTA_PER_USD,
            "total_used_usd": float(data["total_used"]) / QUOTA_PER_USD,
            "total_available_usd": float(data["total_available"]) / QUOTA_PER_USD,
        }
    except Exception as exc:
        return {
            "ok": False,
            "checked_at": now_iso(),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def query_pricing() -> dict[str, Any]:
    try:
        with urllib.request.urlopen("https://api3.xhub.chat/api/pricing/", timeout=30) as response:
            payload = json.load(response)
        rows = payload.get("data") or []
        row = next(item for item in rows if item.get("model_name") == "gpt-4o")
        model_ratio = float(row["model_ratio"])
        completion_ratio = float(row["completion_ratio"])
        return {
            "ok": True,
            "checked_at": now_iso(),
            "model_name": "gpt-4o",
            "quota_type": row.get("quota_type"),
            "model_ratio": model_ratio,
            "completion_ratio": completion_ratio,
            "cache_ratio": row.get("cache_ratio"),
            "quota_per_usd": QUOTA_PER_USD,
            "input_usd_per_million_tokens": model_ratio / QUOTA_PER_USD * 1_000_000,
            "output_usd_per_million_tokens": (
                model_ratio * completion_ratio / QUOTA_PER_USD * 1_000_000
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "checked_at": now_iso(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "fallback_input_usd_per_million_tokens": 2.5,
            "fallback_output_usd_per_million_tokens": 10.0,
        }


def full_config(args: argparse.Namespace) -> dict[str, Any]:
    cfg = copy.deepcopy(battle.MCGS_DEFAULT)
    mcgs = cfg["alphago_mcgs"]
    mcgs["budget"] = args.budget
    mcgs["window_size"] = args.window_size
    mcgs["concurrency"] = args.internal_concurrency
    mcgs["trace"] = True
    evidence = mcgs.setdefault("evidence", {})
    evidence["compression_profile"] = args.compression_profile
    evidence.update(battle.MCGS_COMPRESSION_PROFILES.get(args.compression_profile, {}))
    return cfg


ORIGINAL_MAKE_CONFIG = ablation.make_mcgs_config


def make_config(args: argparse.Namespace, variant: str) -> dict[str, Any]:
    if variant == FULL:
        return full_config(args)
    return ORIGINAL_MAKE_CONFIG(args, variant)


class BudgetExceeded(RuntimeError):
    pass


class AuditedOpenAIClient(cost.OpenAIClient):
    """One visible ledger row per network call, including JSON retries."""

    spent_usd = 0.0
    reserved_usd = 0.0
    budget_lock: asyncio.Lock | None = None

    def __init__(self, config: dict[str, Any], *, call_log_path: Path, context: dict[str, Any]):
        super().__init__(config)
        self.call_log_path = call_log_path
        self.parse_log_path = call_log_path.parent / "json_parse_attempts.jsonl"
        self.context = dict(context)
        self.call_records: list[dict[str, Any]] = []
        self._call_index = 0

    @classmethod
    def _lock(cls) -> asyncio.Lock:
        if cls.budget_lock is None:
            cls.budget_lock = asyncio.Lock()
        return cls.budget_lock

    async def call(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        response_format: dict | None = None,
    ):
        async with self._lock():
            if self.spent_usd + self.reserved_usd + PER_CALL_RESERVATION_USD > HARD_BUDGET_USD:
                raise BudgetExceeded(
                    f"Stage-1 self-ledger hard stop: spent=${self.spent_usd:.6f}, "
                    f"reserved=${self.reserved_usd:.6f}, cap=${HARD_BUDGET_USD:.2f}"
                )
            type(self).reserved_usd += PER_CALL_RESERVATION_USD

        self._call_index += 1
        call_index = self._call_index
        record = {
            **self.context,
            "call_index": call_index,
            "started_at": now_iso(),
            "prompt_chars": len(prompt or ""),
            "prompt_sha256": canonical_sha256(prompt or ""),
            "system_prompt_chars": len(system_prompt or ""),
            "system_prompt_sha256": canonical_sha256(system_prompt or ""),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format,
            "ok": False,
        }
        t0 = time.time()
        actual_cost = 0.0
        try:
            response = await cost.OpenAIClient.call(
                self,
                prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
                response_format=response_format,
            )
            usage = dict(response.usage or {})
            actual_cost = (
                int(usage.get("prompt_tokens") or 0) * DEFAULT_INPUT_USD_PER_TOKEN
                + int(usage.get("completion_tokens") or 0) * DEFAULT_OUTPUT_USD_PER_TOKEN
            )
            record.update(
                {
                    "ok": True,
                    "ended_at": now_iso(),
                    "runtime_sec": time.time() - t0,
                    "returned_model": response.model,
                    "usage": usage,
                    "estimated_usd": actual_cost,
                }
            )
            return response
        except Exception as exc:
            record.update(
                {
                    "ok": False,
                    "ended_at": now_iso(),
                    "runtime_sec": time.time() - t0,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            raise
        finally:
            async with self._lock():
                type(self).reserved_usd -= PER_CALL_RESERVATION_USD
                type(self).spent_usd += actual_cost
            self.call_records.append(record)
            append_jsonl(self.call_log_path, record)

    async def call_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        retries: int = 2,
    ) -> dict[str, Any]:
        logical_id = canonical_sha256(
            {
                "context": self.context,
                "prompt": prompt,
                "logical_started_at_ns": time.time_ns(),
            }
        )
        last_error: Exception | None = None
        for attempt in range(1, retries + 2):
            parse_row = {
                **self.context,
                "logical_request_id": logical_id,
                "prompt_sha256": canonical_sha256(prompt),
                "json_attempt": attempt,
                "started_at": now_iso(),
                "transport_ok": False,
                "json_parse_ok": False,
            }
            try:
                response = await self.call(
                    prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt,
                    response_format={"type": "json_object"},
                )
                parse_row["transport_ok"] = True
                parsed = self._extract_json(response.content)
                if parsed is not None:
                    parse_row["json_parse_ok"] = True
                    parse_row["ended_at"] = now_iso()
                    append_jsonl(self.parse_log_path, parse_row)
                    return parsed
                parse_row["error_type"] = "JSONParseEmpty"
                parse_row["error"] = "response contained no parseable JSON object"
            except Exception as exc:
                last_error = exc
                parse_row["error_type"] = type(exc).__name__
                parse_row["error"] = str(exc)
            parse_row["ended_at"] = now_iso()
            append_jsonl(self.parse_log_path, parse_row)
            if attempt <= retries:
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
        if last_error is not None:
            raise last_error
        return {}


def load_scope(orders: list[int]) -> list[dict[str, Any]]:
    all_cases = json.loads(CANONICAL_PLAN.read_text(encoding="utf-8"))
    by_order = {int(case["case_order"]): case for case in all_cases}
    missing = sorted(set(orders) - set(by_order))
    if missing:
        raise RuntimeError(f"Canonical plan is missing case orders: {missing}")
    return [copy.deepcopy(by_order[order]) for order in orders]


def source_scc_uid(case: dict[str, Any]) -> str:
    identity = case["planned_case_identity"]
    payload = {
        key: identity[key]
        for key in (
            "version",
            "domain",
            "dataset_revision",
            "ordered_clause_ids",
            "typed_internal_edges",
            "normalized_clause_text_hashes",
        )
    }
    return "source-scc-v1-" + canonical_sha256(payload).removeprefix("sha256:")


def validate_frozen_scope() -> dict[str, Any]:
    scope = json.loads(RERUN_SCOPE.read_text(encoding="utf-8"))
    configured = scope["stage1"]
    if configured["affected_case_orders"] != FORMAL_ORDERS:
        raise RuntimeError("FORMAL_ORDERS differs from manifests/rerun_scope.json")
    if int(configured["paid_jobs"]) != 51 or int(configured["variants_per_case"]) != 3:
        raise RuntimeError("Unexpected frozen Stage-1 scope dimensions")
    if scope["stage0_smoke"]["case_orders"] != SMOKE_ORDERS:
        raise RuntimeError("SMOKE_ORDERS differs from manifests/rerun_scope.json")
    return scope


def current_prompt_schema_provenance() -> dict[str, Any]:
    prompt_sources = {
        "generic": inspect.getsource(battle._mcgs_generic_prompt),
        "debian": inspect.getsource(battle._mcgs_debian_prompt),
        "sec_ex21": inspect.getsource(battle._mcgs_sec_prompt),
        "bgb": inspect.getsource(battle._mcgs_generic_prompt),
        "cuad": inspect.getsource(battle._mcgs_generic_prompt),
    }
    parser_source = inspect.getsource(AlphaGoMCGS._evaluate)
    return {
        "prompt_builder_source_sha256": canonical_sha256(prompt_sources),
        "json_parser_source_sha256": canonical_sha256(parser_source),
        "response_format": {"type": "json_object"},
        "required_top_level_schema": [
            "clause_evaluations",
            "local_risk_subgraph_nodes",
            "local_conflict_edges",
            "critical_pairs",
            "repair_entry_nodes",
            "conflicts",
        ],
    }


def audit_historical_full(plan: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    rows = []
    for case in plan:
        source_path = cost.source_result_path(case["source_result_file"])
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else [payload]
        candidates = [
            row
            for row in records
            if row.get("method") == "sa-mcgs"
            and row.get("model") == "gpt-4o"
            and row.get("domain") == case["domain"]
        ]
        matches = []
        for row in candidates:
            try:
                actual = cost.validate_result_case_identity(row, case, args.graphs[case["domain"]])
            except cost.StableCaseIdentityError:
                continue
            matches.append((row, actual))
        if len(matches) != 1:
            raise RuntimeError(f"Historical Full match count for {case['case_id']}: {len(matches)}")
        row, actual = matches[0]
        marker_keys = {
            "relation_first_enabled": row.get("relation_first_enabled"),
            "relation_evidence_policy": row.get("relation_evidence_policy"),
            "evidence_component_policy": row.get("evidence_component_policy"),
            "critical_pair_policy": row.get("critical_pair_policy"),
            "evidence_subgraph_policy": row.get("evidence_subgraph_policy"),
        }
        rows.append(
            {
                "case_order": case["case_order"],
                "case_id": case["case_id"],
                "source_scc_uid": source_scc_uid(case),
                "source_file": str(source_path),
                "source_file_sha256": file_sha256(source_path),
                "source_sa_record_sha256": canonical_sha256(row),
                "identity_match": actual["fingerprint"] == case["planned_scc_fingerprint"],
                "model": row.get("model"),
                "budget": row.get("budget"),
                "inject_profile": row.get("inject_profile"),
                "inject_profile_version": row.get("inject_profile_version"),
                "conflict_family": row.get("injected_conflict_family"),
                "conflict_severity": row.get("injected_conflict_severity"),
                "schema_policy_markers": marker_keys,
                "raw_prompt_hash_recorded": False,
                "full_config_hash_recorded": False,
            }
        )
    return {
        "cases_checked": len(rows),
        "identity_matches": sum(bool(row["identity_match"]) for row in rows),
        "model_matches": sum(row["model"] == "gpt-4o" for row in rows),
        "budget_matches": sum(int(row["budget"] or -1) == 60 for row in rows),
        "protocol_marker_matches": sum(
            row["inject_profile"] == "memory_stress"
            and row["inject_profile_version"] == "structural_simple_v2"
            and row["conflict_severity"] == "critical"
            and row["schema_policy_markers"]["relation_first_enabled"] is True
            for row in rows
        ),
        "strict_contemporaneous_pairing_eligible": False,
        "decision": (
            "Do not use historical Full as the paired control: its case identity/model/budget/protocol "
            "match, but raw prompt and full config hashes were not recorded. Rerun Full in the same "
            "contemporaneous four-arm batch."
        ),
        "rows": rows,
    }


def prepare_phase(phase: str, args: argparse.Namespace) -> tuple[Path, list[dict[str, Any]]]:
    validate_frozen_scope()
    orders = SMOKE_ORDERS if phase == "smoke" else FORMAL_ORDERS
    phase_dir = RUN_ROOT / phase
    phase_dir.mkdir(parents=True, exist_ok=True)
    plan = load_scope(orders)
    graphs = cost.load_graphs(plan)
    args.graphs = graphs
    preflight = cost.validate_case_plan(plan, graphs)
    for case in plan:
        case["source_scc_uid"] = source_scc_uid(case)
    cost.persist_case_plan(phase_dir, plan)
    cost.atomic_write_json(
        phase_dir / "case_identity_preflight.json",
        {**preflight, "validated_at": now_iso(), "orders": orders},
    )

    provenance = current_prompt_schema_provenance()
    configs = {variant: make_config(args, variant) for variant in VARIANTS}
    config_hashes = {variant: canonical_sha256(configs[variant]) for variant in VARIANTS}
    full_cfg = configs[FULL]
    config_diffs = {}
    for variant in VARIANTS:
        if variant == FULL:
            config_diffs[variant] = "reference"
        elif variant == "random-local-window-selection":
            config_diffs[variant] = "runtime selection patch only; base config equals Full"
        else:
            config_diffs[variant] = {
                "full_evidence": full_cfg["alphago_mcgs"]["evidence"],
                "variant_evidence": configs[variant]["alphago_mcgs"]["evidence"],
            }

    prompt_examples = []
    for case in plan:
        graph, scc, _injected, _metadata = cost.prepare_injected_case(case, graphs)
        mcgs = AlphaGoMCGS(llm_client=None, config=full_cfg)
        prompt_fn = battle.DOMAIN_MCGS_PROMPTS[case["domain"]]
        mcgs._build_focused_prompt = lambda window, _self=mcgs, _fn=prompt_fn: _fn(_self, window)
        mcgs._init_state(graph, scc)
        window = mcgs._select_and_expand(0)
        prompt = mcgs._build_focused_prompt(window)
        prompt_examples.append(
            {
                "case_order": case["case_order"],
                "case_id": case["case_id"],
                "source_scc_uid": case["source_scc_uid"],
                "first_full_window": window,
                "first_full_prompt_chars": len(prompt),
                "first_full_prompt_sha256": canonical_sha256(prompt),
            }
        )

    historical = audit_historical_full(plan, args)
    protocol = {
        "manifest_version": "stage1_identity_safe_four_arm_v1",
        "created_at": now_iso(),
        "phase": phase,
        "publication_use": "diagnostic_only" if phase == "smoke" else "formal",
        "orders": orders,
        "cases": len(plan),
        "variants": VARIANTS,
        "paid_jobs": len(plan) * len(VARIANTS),
        "model": "gpt-4o",
        "model_id": "gpt-4o",
        "budget_rollouts": args.budget,
        "window_size": args.window_size,
        "internal_concurrency": args.internal_concurrency,
        "case_concurrency": 1,
        "effective_max_api_concurrency": args.internal_concurrency,
        "compression_profile": args.compression_profile,
        "injection": {
            "profile": "memory_stress",
            "profile_version": "structural_simple_v2",
            "severity": "critical",
            "seed": 42,
        },
        "identity_policy": cost.STABLE_CASE_IDENTITY_VERSION,
        "invalid_policy": "retain every attempted case; invalid/missing metrics count as misses in strict denominator",
        "retry_policy": {
            "sdk_hidden_retries": 0,
            "explicit_json_or_transport_attempts_per_rollout": 3,
            "case_level_retry_after_exception": 1,
            "first_case_attempt_preserved_under": "attempts/attempt_1",
            "every_network_and_json_parse_attempt_logged": True,
        },
        "hard_budget_usd_including_smoke_and_formal": HARD_BUDGET_USD,
        "pricing": query_pricing(),
        "prompt_schema_provenance": provenance,
        "prompt_examples": prompt_examples,
        "config_sha256": config_hashes,
        "config_diffs_vs_full": config_diffs,
        "code_sha256": {
            str(path.relative_to(REPO_ROOT)): file_sha256(path)
            for path in [
                REPO_ROOT / "emnlp2026_discussion" / "run_component_ablation_stage0.py",
                REPO_ROOT / "emnlp2026_discussion" / "run_cost_audit_clean.py",
                REPO_ROOT / "experiments" / "cross_domain" / "run_cross_domain_battle.py",
                REPO_ROOT / "src" / "modules" / "alphago_mcgs.py",
                Path(__file__).resolve(),
                RERUN_SCOPE,
                CANONICAL_PLAN,
                MAIN_MANIFEST,
            ]
        },
        "historical_full_parity_audit": historical,
        "paired_control_decision": "fresh contemporaneous Full required and included",
    }
    cost.atomic_write_json(phase_dir / "protocol.json", protocol)
    return phase_dir, plan


ORIGINAL_MAKE_LLM = ablation.make_llm


def make_llm(args: argparse.Namespace, output_dir: Path, case: dict[str, Any], variant: str):
    model_id = cost.MODEL_IDS.get(args.model, args.model)
    config = {
        "provider": "openai",
        "model": model_id,
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "timeout": args.llm_timeout,
        # No hidden SDK retry: every retry must appear in our ledger.
        "max_retries": 0,
    }
    return AuditedOpenAIClient(
        config,
        call_log_path=output_dir / "call_logs" / "llm_calls.jsonl",
        context={
            "run_id": RUN_ROOT.name,
            "phase": output_dir.name,
            "case_id": case["case_id"],
            "case_order": case["case_order"],
            "case_uid": case["case_uid"],
            "source_scc_uid": case["source_scc_uid"],
            "domain": case["domain"],
            "scc_id_diagnostic": case["scc_id"],
            "scc_size": case["scc_size"],
            "template": case["template"],
            "method": "sa-mcgs",
            "ablation_variant": variant,
            "model": args.model,
            "job_attempt": getattr(args, "current_job_attempt", 1),
            "internal_concurrency": args.internal_concurrency,
        },
    )


def result_files(phase_dir: Path) -> list[Path]:
    return sorted((phase_dir / "results").glob("*.json"))


def phase_status(phase_dir: Path, plan: list[dict[str, Any]], state: str, current: Any = None) -> None:
    results = []
    for path in result_files(phase_dir):
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    expected = len(plan) * len(VARIANTS)
    invalid = sum(bool(row.get("component_ablation_error")) for row in results)
    payload = {
        "run_id": RUN_ROOT.name,
        "phase": phase_dir.name,
        "state": state,
        "updated_at": now_iso(),
        "total_cases": len(plan),
        "variants": VARIANTS,
        "total_jobs": expected,
        "completed_jobs": len(results),
        "remaining_jobs": expected - len(results),
        "invalid_jobs": invalid,
        "current": current,
        "self_ledger_all_phases": all_run_usage(),
        "hard_budget_usd": HARD_BUDGET_USD,
    }
    cost.atomic_write_json(phase_dir / "status.json", payload)


def write_balance_checkpoint(phase_dir: Path, event: str, case_order: int | None = None) -> None:
    append_jsonl(
        phase_dir / "balance_checkpoints.jsonl",
        {
            "event": event,
            "case_order": case_order,
            "self_ledger_all_phases": all_run_usage(),
            "account_balance": query_balance(),
        },
    )


async def run_phase(phase: str, args: argparse.Namespace) -> None:
    phase_dir, plan = prepare_phase(phase, args)
    ablation.make_mcgs_config = make_config
    ablation.make_llm = make_llm
    ablation.VARIANT_LABELS.update(LABELS)
    cost.LoggingOpenAIClient = AuditedOpenAIClient

    existing_cost = all_run_usage()["estimated_usd"]
    AuditedOpenAIClient.spent_usd = existing_cost
    AuditedOpenAIClient.reserved_usd = 0.0
    AuditedOpenAIClient.budget_lock = None

    write_balance_checkpoint(phase_dir, "phase_start")
    phase_status(phase_dir, plan, "running")
    for case in plan:
        for variant in VARIANTS:
            path = ablation.result_path(phase_dir, case, variant)
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if not existing.get("component_ablation_error"):
                    cost.validate_result_case_identity(existing, case, args.graphs[case["domain"]])
                    continue
                attempt_dir = phase_dir / "attempts" / "attempt_1" / "results"
                attempt_dir.mkdir(parents=True, exist_ok=True)
                preserved = attempt_dir / path.name
                if not preserved.exists():
                    path.replace(preserved)

            ledger = all_run_usage()
            if ledger["estimated_usd"] + PER_CALL_RESERVATION_USD > HARD_BUDGET_USD:
                phase_status(phase_dir, plan, "budget_stopped", {"case": case["case_id"], "variant": variant})
                raise BudgetExceeded(
                    f"Refusing next job: self ledger ${ledger['estimated_usd']:.6f} near cap ${HARD_BUDGET_USD:.2f}"
                )

            current = {
                "case_order": case["case_order"],
                "case_id": case["case_id"],
                "variant": variant,
                "started_at": now_iso(),
            }
            print(
                f"[{phase}] case {case['case_order']} {variant} start; "
                f"self_cost=${ledger['estimated_usd']:.4f}",
                flush=True,
            )
            phase_status(phase_dir, plan, "running", current)
            args.current_job_attempt = 1
            result = await ablation.run_one_variant(
                args, phase_dir, case, variant, args.graphs
            )
            if result.get("component_ablation_error"):
                attempt_dir = phase_dir / "attempts" / "attempt_1" / "results"
                attempt_dir.mkdir(parents=True, exist_ok=True)
                preserved = attempt_dir / path.name
                if preserved.exists():
                    raise RuntimeError(f"Refusing to overwrite preserved first attempt: {preserved}")
                path.replace(preserved)
                append_jsonl(
                    phase_dir / "case_retry_ledger.jsonl",
                    {
                        "case_order": case["case_order"],
                        "case_id": case["case_id"],
                        "variant": variant,
                        "first_attempt_result": str(preserved),
                        "error": result.get("component_ablation_error"),
                        "retry_started_at": now_iso(),
                    },
                )
                args.current_job_attempt = 2
                result = await ablation.run_one_variant(
                    args, phase_dir, case, variant, args.graphs
                )

            phase_status(phase_dir, plan, "running")
            print(
                f"[{phase}] case {case['case_order']} {variant} done; "
                f"error={bool(result.get('component_ablation_error'))}; "
                f"self_cost=${all_run_usage()['estimated_usd']:.4f}",
                flush=True,
            )
        write_balance_checkpoint(phase_dir, "case_complete", int(case["case_order"]))

    aggregate_formal(phase_dir, plan, phase)
    phase_status(phase_dir, plan, "complete")
    write_balance_checkpoint(phase_dir, "phase_complete")


def metric(result: dict[str, Any], key: str) -> bool:
    if result.get("component_ablation_error"):
        return False
    aliases = {
        "root_at_3": ("root_top3_hit", "top3_hit"),
        "risk_any": ("core_evidence_contains_any_risk_node",),
        "risk_all": ("core_evidence_contains_all_risk_nodes",),
    }
    for alias in aliases[key]:
        if isinstance(result.get(alias), bool):
            return bool(result[alias])
    return False


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    index = (len(ordered) - 1) * p
    left = int(math.floor(index))
    right = int(math.ceil(index))
    if left == right:
        return ordered[left]
    return ordered[left] * (right - index) + ordered[right] * (index - left)


def clustered_ci(
    rows: list[dict[str, Any]],
    value_fn,
    *,
    seed: int = 20260909,
    samples: int = 20_000,
) -> tuple[float, float]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[row["source_scc_uid"]].append(row)
    keys = sorted(clusters)
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        sampled_rows = []
        for key in rng.choices(keys, k=len(keys)):
            sampled_rows.extend(clusters[key])
        estimates.append(sum(value_fn(row) for row in sampled_rows) / len(sampled_rows))
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def aggregate_formal(phase_dir: Path, plan: list[dict[str, Any]], phase: str) -> None:
    by_case = {case["case_id"]: case for case in plan}
    result_rows = []
    for path in result_files(phase_dir):
        result = json.loads(path.read_text(encoding="utf-8"))
        case = by_case[result["case_id"]]
        cost.validate_result_case_identity(result, case, phase_dir and args_global.graphs[case["domain"]])
        usage = result.get("llm_usage_summary") or {}
        estimated = (
            int(usage.get("prompt_tokens") or 0) * DEFAULT_INPUT_USD_PER_TOKEN
            + int(usage.get("completion_tokens") or 0) * DEFAULT_OUTPUT_USD_PER_TOKEN
        )
        result_rows.append(
            {
                "case_order": int(case["case_order"]),
                "case_id": case["case_id"],
                "case_uid": case["case_uid"],
                "source_scc_uid": case["source_scc_uid"],
                "domain": case["domain"],
                "scc_size": int(case["scc_size"]),
                "template": case["template"],
                "variant": result["ablation_variant"],
                "invalid": bool(result.get("component_ablation_error")),
                "error": result.get("component_ablation_error"),
                "root_at_3_strict": metric(result, "root_at_3"),
                "risk_any_strict": metric(result, "risk_any"),
                "risk_all_strict": metric(result, "risk_all"),
                "core_size": result.get("core_evidence_risk_subgraph_size"),
                "compression": result.get("core_evidence_compression_ratio"),
                "algorithm_llm_calls": int(result.get("llm_calls") or 0),
                "recorded_api_calls": int(usage.get("recorded_api_calls") or 0),
                "successful_api_calls": int(usage.get("successful_api_calls") or 0),
                "failed_api_calls": int(usage.get("failed_api_calls") or 0),
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
                "estimated_usd": estimated,
                "result_file": str(path),
                "result_sha256": file_sha256(path),
            }
        )
    result_rows.sort(key=lambda row: (row["case_order"], VARIANTS.index(row["variant"])))
    expected_pairs = {(case["case_id"], variant) for case in plan for variant in VARIANTS}
    actual_pairs = {(row["case_id"], row["variant"]) for row in result_rows}
    missing = sorted(expected_pairs - actual_pairs)
    extras = sorted(actual_pairs - expected_pairs)
    if missing or extras:
        raise RuntimeError(f"Result matrix mismatch: missing={missing}, extras={extras}")

    detail_csv = phase_dir / "stage1_case_results_strict.csv"
    with detail_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result_rows[0]))
        writer.writeheader()
        writer.writerows(result_rows)

    table = []
    for variant in VARIANTS:
        rows = [row for row in result_rows if row["variant"] == variant]
        n = len(rows)
        table.append(
            {
                "Variant": LABELS[variant],
                "Attempted": n,
                "Valid": sum(not row["invalid"] for row in rows),
                "Invalid": sum(row["invalid"] for row in rows),
                "Invalid rate": sum(row["invalid"] for row in rows) / n,
                "Root@3 strict": sum(row["root_at_3_strict"] for row in rows) / n,
                "Risk-any strict": sum(row["risk_any_strict"] for row in rows) / n,
                "Risk-all strict": sum(row["risk_all_strict"] for row in rows) / n,
                "Algorithm calls": sum(row["algorithm_llm_calls"] for row in rows),
                "API calls": sum(row["recorded_api_calls"] for row in rows),
                "Input tokens": sum(row["prompt_tokens"] for row in rows),
                "Output tokens": sum(row["completion_tokens"] for row in rows),
                "Total tokens": sum(row["total_tokens"] for row in rows),
                "Estimated USD": sum(row["estimated_usd"] for row in rows),
            }
        )

    table_csv = phase_dir / "stage1_publication_table.csv"
    with table_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)

    full_by_case = {
        row["case_id"]: row for row in result_rows if row["variant"] == FULL
    }
    uncertainty = []
    for variant in VARIANTS:
        rows = [row for row in result_rows if row["variant"] == variant]
        for key, label in [
            ("root_at_3_strict", "Root@3"),
            ("risk_any_strict", "Risk-any"),
            ("risk_all_strict", "Risk-all"),
        ]:
            low, high = clustered_ci(rows, lambda row, _key=key: float(row[_key]))
            point = sum(float(row[key]) for row in rows) / len(rows)
            item = {
                "variant": variant,
                "metric": label,
                "estimate": point,
                "clustered_ci_95_low": low,
                "clustered_ci_95_high": high,
                "source_scc_clusters": len({row["source_scc_uid"] for row in rows}),
                "bootstrap_samples": 20_000,
            }
            if variant != FULL:
                low_d, high_d = clustered_ci(
                    rows,
                    lambda row, _key=key: float(row[_key])
                    - float(full_by_case[row["case_id"]][_key]),
                    seed=20260909 + VARIANTS.index(variant) * 101,
                )
                deltas = [
                    float(row[key]) - float(full_by_case[row["case_id"]][key])
                    for row in rows
                ]
                item.update(
                    {
                        "paired_delta_vs_full": sum(deltas) / len(deltas),
                        "paired_delta_clustered_ci_95_low": low_d,
                        "paired_delta_clustered_ci_95_high": high_d,
                    }
                )
            uncertainty.append(item)
    cost.atomic_write_json(phase_dir / "stage1_clustered_uncertainty.json", uncertainty)

    retry_rows = read_jsonl(phase_dir / "case_retry_ledger.jsonl")
    parse_rows = read_jsonl(phase_dir / "call_logs" / "json_parse_attempts.jsonl")
    first_parse_failures = sum(
        row.get("json_attempt") == 1 and not row.get("json_parse_ok") for row in parse_rows
    )
    retry_parse_attempts = sum(int(row.get("json_attempt") or 1) > 1 for row in parse_rows)
    manifest = {
        "manifest_version": "stage1_identity_safe_results_v1",
        "completed_at": now_iso(),
        "phase": phase,
        "publication_use": "formal" if phase == "formal" else "diagnostic_only",
        "matrix_complete": len(result_rows) == len(plan) * len(VARIANTS),
        "cases": len(plan),
        "source_scc_clusters": len({row["source_scc_uid"] for row in result_rows}),
        "variants": VARIANTS,
        "jobs": len(result_rows),
        "case_level_first_attempt_failures": len(retry_rows),
        "case_level_retries": len(retry_rows),
        "logical_rollout_first_parse_or_transport_failures": first_parse_failures,
        "explicit_json_or_transport_retry_attempts": retry_parse_attempts,
        "self_usage_this_phase": usage_cost(
            read_jsonl(phase_dir / "call_logs" / "llm_calls.jsonl")
        ),
        "self_usage_all_phases": all_run_usage(),
        "hard_budget_usd": HARD_BUDGET_USD,
        "strict_denominator": len(plan),
        "invalids_count_as_metric_misses": True,
        "files": {
            str(path.relative_to(phase_dir)): file_sha256(path)
            for path in [
                phase_dir / "protocol.json",
                phase_dir / "case_plan.json",
                phase_dir / "case_identity_preflight.json",
                detail_csv,
                table_csv,
                phase_dir / "stage1_clustered_uncertainty.json",
            ]
        },
        "result_index": [
            {
                "case_id": row["case_id"],
                "variant": row["variant"],
                "case_uid": row["case_uid"],
                "source_scc_uid": row["source_scc_uid"],
                "result_file": row["result_file"],
                "result_sha256": row["result_sha256"],
            }
            for row in result_rows
        ],
    }
    cost.atomic_write_json(phase_dir / "results_manifest.json", manifest)

    def pct(value: float) -> str:
        return f"{value * 100:.1f}%"

    md = [
        "# Stage-1 identity-safe 四臂配对消融",
        "",
        f"状态：{'正式批次完成' if phase == 'formal' else 'smoke 诊断完成'}。",
        "",
        "历史 frozen Full 缺少原始 prompt/config hash，因此本批次将 Full 与三个消融全部 contemporaneous 重跑。",
        "所有指标使用 strict all-case denominator；invalid 保留并按未命中计。置信区间以 physical source SCC 聚类 bootstrap。",
        "",
        "| Variant | Attempted | Valid | Invalid | Root@3 | Risk-any | Risk-all | API calls | Tokens | Est. USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in table:
        md.append(
            "| {Variant} | {Attempted} | {Valid} | {Invalid} | {root} | {any} | {all} | {calls} | {tokens} | ${usd:.4f} |".format(
                **row,
                root=pct(row["Root@3 strict"]),
                any=pct(row["Risk-any strict"]),
                all=pct(row["Risk-all strict"]),
                calls=row["API calls"],
                tokens=row["Total tokens"],
                usd=row["Estimated USD"],
            )
        )
    md.extend(
        [
            "",
            f"- physical source SCC clusters：{manifest['source_scc_clusters']}",
            f"- case-level 首轮失败/重试：{len(retry_rows)}/{len(retry_rows)}",
            f"- rollout 首次 JSON/transport 失败：{first_parse_failures}",
            f"- 显式 JSON/transport retry attempts：{retry_parse_attempts}",
            f"- 本 phase 估算成本：${manifest['self_usage_this_phase']['estimated_usd']:.6f}",
            f"- smoke + formal 累计估算成本：${manifest['self_usage_all_phases']['estimated_usd']:.6f} / ${HARD_BUDGET_USD:.2f}",
            "",
            "详细逐 case 结果、聚类区间与哈希索引分别见 `stage1_case_results_strict.csv`、",
            "`stage1_clustered_uncertainty.json` 与 `results_manifest.json`。",
        ]
    )
    (phase_dir / "RESULTS_ZH.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["smoke", "formal"], required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--budget", type=int, default=60)
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--internal-concurrency", type=int, default=3)
    parser.add_argument("--compression-profile", default="current")
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--base-url", default=battle.XHUB_BASE_URL)
    parser.add_argument("--api-key-env", default="XHUB_API_KEY")
    parser.add_argument("--llm-timeout", type=float, default=600)
    parser.add_argument("--llm-max-retries", type=int, default=0)
    parser.add_argument("--case-concurrency", type=int, default=1)
    parser.add_argument("--random-seed", type=int, default=8229)
    parser.add_argument("--retry-errors", action="store_false", default=False)
    return parser.parse_args()


args_global: argparse.Namespace


async def main() -> None:
    global args_global
    args_global = parse_args()
    if args_global.model != "gpt-4o":
        raise RuntimeError("Frozen Stage-1 protocol requires model=gpt-4o")
    if args_global.budget != 60 or args_global.window_size != 4:
        raise RuntimeError("Frozen Stage-1 protocol requires budget=60 and window_size=4")
    if args_global.internal_concurrency > 3 or args_global.case_concurrency != 1:
        raise RuntimeError("Operational API concurrency must remain <=3")
    phase_dir, _plan = prepare_phase(args_global.phase, args_global)
    if args_global.prepare_only:
        print(f"Prepared and validated {phase_dir}")
        return
    if not os.environ.get(args_global.api_key_env):
        raise RuntimeError(f"{args_global.api_key_env} is not set")
    await run_phase(args_global.phase, args_global)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
        raise

#!/usr/bin/env python3
"""Frozen, fail-closed runner for the four-slot relation-prior fallback.

Offline commands (``preflight`` and ``dry-run``) never construct an LLM client
and never make a network request.  The ``run`` command is the sole paid path;
it additionally requires ``--execute-paid-cells`` and fresh global-budget
arguments.  Results are attempted once in the exact manifest order.  A saved
valid *or invalid* result is terminal and is never retried or replaced.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import csv
import hashlib
import json
import math
import os
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable


EXPECTED_DIRECTORY = "prior_fallback_slots_01_03_08_10"
EXPECTED_PROTOCOL_VERSION = "prior_fallback_slots_01_03_08_10_v1"
EXPECTED_PROTOCOL_SHA256 = "sha256:56466e4e26fee490e698922eb80f4fdddfc6970965c0a40d513607c6623a7e37"
RUN_DIR = Path(__file__).resolve().parent
REPO_ROOT = RUN_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT))

from emnlp2026_discussion import run_cost_audit_clean as cost  # noqa: E402


PROTOCOL_PATH = RUN_DIR / "frozen_fallback_protocol.json"
PREFLIGHT_DIR = RUN_DIR / "preflight"
RESULTS_DIR = RUN_DIR / "results"
LEDGER_PATH = RUN_DIR / "budget_ledger.jsonl"
STATUS_PATH = RUN_DIR / "execution_status.json"
REPORT_PATH = RUN_DIR / "REPORT_ZH.md"
MODELS = ("gpt-4o", "gemini-2.5-pro")
PROFILES = ("minus20", "plus20")
ALL_PROFILES = ("minus20", "nominal", "plus20")
PARENT_METHODS = ("naive-single", "lea", "sa-mcgs")
EXPECTED_SELECTED_SLOTS = (1, 3, 8, 10)
PROMPT_FIELDS = (
    "prompt_semantic_audit_version",
    "prompt_semantic_audit_hash",
    "prompt_adapter_type",
    "prompt_compatibility",
    "prompt_input_scope",
)


class ProtocolError(RuntimeError):
    """A frozen identity, parity, ordering, or provenance assertion failed."""


class BudgetStop(RuntimeError):
    """The supplied global authorization cannot safely cover the frozen tail."""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def repo_path(relative_path: str) -> Path:
    path = (REPO_ROOT / relative_path).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise ProtocolError(f"Frozen source escapes repository: {relative_path}") from exc
    return path


def protocol() -> dict[str, Any]:
    if RUN_DIR.name != EXPECTED_DIRECTORY:
        raise ProtocolError(
            f"Output isolation failed: {RUN_DIR.name!r} != {EXPECTED_DIRECTORY!r}"
        )
    actual_protocol_hash = file_hash(PROTOCOL_PATH)
    if actual_protocol_hash != EXPECTED_PROTOCOL_SHA256:
        raise ProtocolError(
            f"Frozen fallback protocol hash drift: {actual_protocol_hash} != "
            f"{EXPECTED_PROTOCOL_SHA256}"
        )
    payload = load_json(PROTOCOL_PATH)
    if payload.get("protocol_version") != EXPECTED_PROTOCOL_VERSION:
        raise ProtocolError("Unexpected fallback protocol version")
    if payload.get("output_directory_name") != EXPECTED_DIRECTORY:
        raise ProtocolError("Frozen protocol permits a different output directory")
    if payload.get("scope", {}).get("new_paid_cells") != 16:
        raise ProtocolError("Frozen paid-cell count is not 16")
    if payload.get("scope", {}).get("nominal_reuse_cells") != 8:
        raise ProtocolError("Frozen nominal reuse count is not 8")
    upstream = payload.get("upstream_accounting") or {}
    sources = upstream.get("sources") or []
    if [row.get("role") for row in sources] != ["pre", "stage1", "parent"]:
        raise ProtocolError("Frozen accounting does not name exactly pre/Stage-1/parent")
    if upstream.get("additional_cli_ledgers_permitted") is not False:
        raise ProtocolError("Frozen accounting unexpectedly permits extra CLI ledgers")
    return payload


def assert_file_hash(path: Path, expected: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ProtocolError(f"Frozen {label} is missing: {path}")
    actual = file_hash(path)
    if actual != expected:
        raise ProtocolError(f"Frozen {label} hash drift: {actual} != {expected}")
    return {"label": label, "path": str(path), "expected": expected, "actual": actual, "passed": True}


def validate_source_hashes(frozen: dict[str, Any]) -> list[dict[str, Any]]:
    selection = frozen["selection"]
    parent = frozen["parent"]
    implementation = frozen["implementation_lock"]
    upstream_by_role = {
        str(row["role"]): row for row in frozen["upstream_accounting"]["sources"]
    }
    specs = [
        (repo_path(selection["source_manifest"]), selection["source_manifest_sha256"], "fallback_subset"),
        (repo_path(selection["source_preflight"]), selection["source_preflight_sha256"], "parent_preflight"),
        (repo_path(parent["frozen_protocol"]), parent["frozen_protocol_sha256"], "parent_protocol"),
        (repo_path(parent["budget_amendment"]), parent["budget_amendment_sha256"], "budget_amendment"),
        (repo_path(parent["pricing_snapshot"]), parent["pricing_snapshot_sha256"], "pricing_snapshot"),
        (repo_path(parent["gpt_plan"]), parent["gpt_plan_sha256"], "gpt_plan"),
        (repo_path(parent["gemini_plan"]), parent["gemini_plan_sha256"], "gemini_plan"),
        (repo_path(parent["cost_runner_module"]), parent["cost_runner_module_sha256"], "cost_runner_module"),
        (repo_path(parent["parent_runner"]), parent["parent_runner_sha256"], "parent_runner"),
        (repo_path(implementation["battle_module"]), implementation["battle_module_sha256"], "battle_module"),
        (repo_path(implementation["alphago_mcgs_module"]), implementation["alphago_mcgs_module_sha256"], "alphago_mcgs_module"),
        (repo_path(implementation["openai_client_module"]), implementation["openai_client_module_sha256"], "openai_client_module"),
        (repo_path(implementation["llm_base_module"]), implementation["llm_base_module_sha256"], "llm_base_module"),
        (
            repo_path(upstream_by_role["pre"]["path"]),
            upstream_by_role["pre"]["sha256"],
            "pre_accounting_ledger",
        ),
        (
            repo_path(upstream_by_role["stage1"]["path"]),
            upstream_by_role["stage1"]["sha256"],
            "stage1_accounting_summary",
        ),
        (
            repo_path(upstream_by_role["stage1"]["status_path"]),
            upstream_by_role["stage1"]["status_sha256"],
            "stage1_terminal_status",
        ),
    ]
    return [assert_file_hash(path, expected, label) for path, expected, label in specs]


def physical_scc_identity(case: dict[str, Any]) -> dict[str, Any]:
    identity = case["planned_case_identity"]
    return {
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


def physical_scc_fingerprint(case: dict[str, Any]) -> str:
    return canonical_hash(physical_scc_identity(case))


def make_args(model: str, output_dir: Path, runtime: dict[str, Any] | None = None) -> SimpleNamespace:
    runtime = runtime or protocol()["locked_runtime"]
    return SimpleNamespace(
        model=model,
        output_dir=output_dir,
        budget=int(runtime["sa_mcgs_budget"]),
        window_size=int(runtime["window_size"]),
        internal_concurrency=int(runtime["internal_concurrency"]),
        compression_profile=str(runtime["compression_profile"]),
        base_url=str(runtime["base_url"]),
        api_key_env=str(runtime["api_key_env"]),
        llm_timeout=float(runtime["llm_timeout_seconds"]),
        llm_max_retries=int(runtime["llm_max_retries"]),
    )


def effective_mcgs_config(model: str, relation_prior_weight: float, *, runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cost.make_mcgs_config(make_args(model, RUN_DIR, runtime))
    cfg["alphago_mcgs"].setdefault("evidence", {})["relation_prior_weight"] = float(
        relation_prior_weight
    )
    return cfg


def experiment_config_payload(model: str, profile: str) -> dict[str, Any]:
    frozen = protocol()
    profile_cfg = frozen["scope"]["profiles"][profile]
    runtime = frozen["locked_runtime"]
    return {
        "protocol_version": frozen["protocol_version"],
        "model": model,
        "model_id": cost.MODEL_IDS.get(model, model),
        "method": "sa-mcgs",
        "inject_profile": runtime["inject_profile"],
        "inject_profile_version": runtime["inject_profile_version"],
        "severity": runtime["severity"],
        "compression_profile": runtime["compression_profile"],
        "sa_mcgs_budget": runtime["sa_mcgs_budget"],
        "window_size": runtime["window_size"],
        "case_concurrency": runtime["case_concurrency"],
        "internal_concurrency": runtime["internal_concurrency"],
        "relation_profile": profile,
        "relation_prior_multiplier": profile_cfg["multiplier"],
        "effective_mcgs_config": effective_mcgs_config(
            model, profile_cfg["relation_prior_weight"], runtime=runtime
        ),
    }


def parent_experiment_config_payload(
    frozen: dict[str, Any], model: str, method: str
) -> dict[str, Any]:
    parent = load_json(repo_path(frozen["parent"]["frozen_protocol"]))
    runtime = parent["locked_runtime"]
    profile_cfg = parent["prior_scope"]["profiles"]["nominal"]
    return {
        "protocol_version": parent["protocol_version"],
        "model": model,
        "model_id": cost.MODEL_IDS.get(model, model),
        "method": method,
        "inject_profile": runtime["inject_profile"],
        "inject_profile_version": runtime["inject_profile_version"],
        "severity": runtime["severity"],
        "compression_profile": runtime["compression_profile"],
        "sa_mcgs_budget": runtime["sa_mcgs_budget"] if method == "sa-mcgs" else None,
        "window_size": runtime["window_size"],
        "case_concurrency": runtime["case_concurrency"],
        "internal_concurrency": runtime["internal_concurrency"],
        "relation_profile": "nominal" if method == "sa-mcgs" else None,
        "relation_prior_multiplier": (
            profile_cfg["multiplier"] if method == "sa-mcgs" else None
        ),
        "effective_mcgs_config": (
            effective_mcgs_config(model, profile_cfg["value"], runtime=runtime)
            if method == "sa-mcgs"
            else None
        ),
    }


def parent_nominal_config_payload(model: str) -> dict[str, Any]:
    return parent_experiment_config_payload(protocol(), model, "sa-mcgs")


def recursive_diff(left: Any, right: Any, prefix: str = "") -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        paths: list[str] = []
        for key in sorted(set(left) | set(right)):
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in left or key not in right:
                paths.append(child)
            else:
                paths.extend(recursive_diff(left[key], right[key], child))
        return paths
    if left != right:
        return [prefix]
    return []


def scientific_config(config: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(config)
    payload.pop("protocol_version", None)
    return payload


def paired_config_audit() -> dict[str, Any]:
    frozen = protocol()
    locked = frozen.get("configuration_lock")
    if not isinstance(locked, dict):
        raise ProtocolError("Frozen protocol has no exact configuration_lock")
    locked_experiment = locked.get("experiment_config_sha256")
    locked_scientific = locked.get("scientific_config_sha256")
    if not isinstance(locked_experiment, dict) or not isinstance(locked_scientific, dict):
        raise ProtocolError("Frozen exact configuration hashes are incomplete")
    allowed = {
        "relation_profile",
        "relation_prior_multiplier",
        "effective_mcgs_config.alphago_mcgs.evidence.relation_prior_weight",
    }
    rows = []
    for model in MODELS:
        nominal_config = parent_nominal_config_payload(model)
        nominal = scientific_config(nominal_config)
        if canonical_hash(nominal_config) != locked_experiment.get(model, {}).get("nominal"):
            raise ProtocolError(f"Frozen nominal experiment config drift for {model}")
        if canonical_hash(nominal) != locked_scientific.get(model, {}).get("nominal"):
            raise ProtocolError(f"Frozen nominal scientific config drift for {model}")
        for profile_name in PROFILES:
            varied_config = experiment_config_payload(model, profile_name)
            varied = scientific_config(varied_config)
            if canonical_hash(varied_config) != locked_experiment.get(model, {}).get(profile_name):
                raise ProtocolError(
                    f"Frozen experiment config drift for {model}/{profile_name}"
                )
            if canonical_hash(varied) != locked_scientific.get(model, {}).get(profile_name):
                raise ProtocolError(
                    f"Frozen scientific config drift for {model}/{profile_name}"
                )
            differences = recursive_diff(nominal, varied)
            if set(differences) != allowed:
                raise ProtocolError(
                    f"Uncontrolled config delta for {model}/{profile_name}: {differences}"
                )
            rows.append(
                {
                    "model": model,
                    "profile": profile_name,
                    "nominal_scientific_config_sha256": canonical_hash(nominal),
                    "varied_scientific_config_sha256": canonical_hash(varied),
                    "changed_paths": differences,
                    "only_relation_prior_changed": True,
                }
            )
    return {
        "allowed_changed_paths": sorted(allowed),
        "all_only_relation_prior_changed": True,
        "rows": rows,
    }


def validate_manifest(frozen: dict[str, Any]) -> dict[str, Any]:
    fallback = load_json(repo_path(frozen["selection"]["source_manifest"]))
    if fallback.get("schema_version") != "prior_fallback_subset_v1":
        raise ProtocolError("Unexpected fallback manifest schema")
    if tuple(fallback.get("selected_slots") or ()) != EXPECTED_SELECTED_SLOTS:
        raise ProtocolError("Fallback slots changed")
    if tuple(frozen["selection"]["selected_slots"]) != EXPECTED_SELECTED_SLOTS:
        raise ProtocolError("Protocol slots changed")
    canonical_checks = {
        "selected_slots": canonical_hash(fallback["selected_slots"]),
        "cases": canonical_hash(fallback["cases"]),
        "execution_order": canonical_hash(fallback["execution_order"]),
    }
    expected_checks = {
        "selected_slots": frozen["selection"]["selected_slots_canonical_sha256"],
        "cases": frozen["selection"]["selected_cases_canonical_sha256"],
        "execution_order": frozen["selection"]["execution_order_canonical_sha256"],
    }
    if canonical_checks != expected_checks:
        raise ProtocolError(f"Fallback canonical hash drift: {canonical_checks} != {expected_checks}")
    if fallback.get("selection_blind_to_results") is not True:
        raise ProtocolError("Fallback selection is not outcome-blind")
    if fallback.get("no_outcome_directed_replacement") is not True:
        raise ProtocolError("Fallback permits outcome-directed replacement")
    if fallback.get("new_paid_cells") != 16 or fallback.get("nominal_reuse_cells") != 8:
        raise ProtocolError("Fallback cell counts changed")
    cases = fallback["cases"]
    if len(cases) != 4 or [int(row["slot"]) for row in cases] != list(EXPECTED_SELECTED_SLOTS):
        raise ProtocolError("Fallback case list is not the exact frozen four-slot list")
    execution = fallback["execution_order"]
    if len(execution) != 16 or [int(row["order"]) for row in execution] != list(range(1, 17)):
        raise ProtocolError("Execution order is not exactly 1..16")
    expected_pairs = {
        (model, slot, profile)
        for model in MODELS
        for slot in EXPECTED_SELECTED_SLOTS
        for profile in PROFILES
    }
    actual_pairs = {
        (str(row["model"]), int(row["slot"]), str(row["profile"])) for row in execution
    }
    if actual_pairs != expected_pairs:
        raise ProtocolError("Execution order does not cover the exact frozen 16 cells")
    profile_values = frozen["scope"]["profiles"]
    for row in execution:
        profile_name = str(row["profile"])
        if row["model"] not in MODELS or profile_name not in PROFILES:
            raise ProtocolError(f"Forbidden execution cell: {row}")
        expected_weight = float(profile_values[profile_name]["relation_prior_weight"])
        if float(row["relation_prior_weight"]) != expected_weight:
            raise ProtocolError(f"Relation-prior value drift at order {row['order']}")
    return fallback


def load_parent_plans(frozen: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "gpt-4o": load_json(repo_path(frozen["parent"]["gpt_plan"])),
        "gemini-2.5-pro": load_json(repo_path(frozen["parent"]["gemini_plan"])),
    }


def validate_selected_plans(
    frozen: dict[str, Any], fallback: dict[str, Any]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    full_plans = load_parent_plans(frozen)
    selected: dict[str, list[dict[str, Any]]] = {}
    graphs_by_model: dict[str, dict[str, Any]] = {}
    fallback_by_slot = {int(row["slot"]): row for row in fallback["cases"]}
    for model in MODELS:
        full = full_plans[model]
        if len(full) != 12 or [int(row["case_order"]) for row in full] != list(range(1, 13)):
            raise ProtocolError(f"Parent plan is not the frozen 12-slot plan: {model}")
        subset = [copy.deepcopy(row) for row in full if int(row["case_order"]) in EXPECTED_SELECTED_SLOTS]
        if [int(row["case_order"]) for row in subset] != list(EXPECTED_SELECTED_SLOTS):
            raise ProtocolError(f"Selected plan slots changed for {model}")
        graphs = cost.load_graphs(subset)
        cost.validate_case_plan(subset, graphs)
        for case in subset:
            physical = physical_scc_fingerprint(case)
            if case.get("physical_scc_fingerprint") != physical:
                raise ProtocolError(f"Physical-SCC hash drift: {case['case_id']}")
            manifest_case = fallback_by_slot[int(case["case_order"])]
            checks = {
                "domain": case["domain"] == manifest_case["domain"],
                "scc_size": int(case["scc_size"]) == int(manifest_case["scc_size"]),
                "template": case["template"] == manifest_case["template"],
                "scale": case["scale"] == manifest_case["scale"],
                "case_uid": case["case_uid"] == manifest_case["case_uid"],
                "physical_scc_fingerprint": physical == manifest_case["physical_scc_fingerprint"],
                "injected_case_fingerprint": case["planned_scc_fingerprint"]
                == manifest_case["injected_case_fingerprint"],
                "seed": case["planned_injection_identity"].get("seed") == 42,
                "profile": case["planned_injection_identity"].get("profile")
                == frozen["locked_runtime"]["inject_profile"],
                "profile_version": case["planned_injection_identity"].get("profile_version")
                == frozen["locked_runtime"]["inject_profile_version"],
                "severity": case["planned_injection_identity"].get("conflict_severity")
                == frozen["locked_runtime"]["severity"],
            }
            if not all(checks.values()):
                raise ProtocolError(f"Manifest/plan parity failed for {model}/{case['case_id']}: {checks}")
        selected[model] = subset
        graphs_by_model[model] = graphs

    parity_rows = []
    for slot in EXPECTED_SELECTED_SLOTS:
        left = next(row for row in selected[MODELS[0]] if int(row["case_order"]) == slot)
        right = next(row for row in selected[MODELS[1]] if int(row["case_order"]) == slot)
        checks = {
            "case_uid": left["case_uid"] == right["case_uid"],
            "physical_scc_fingerprint": left["physical_scc_fingerprint"]
            == right["physical_scc_fingerprint"],
            "injected_case_fingerprint": left["planned_scc_fingerprint"]
            == right["planned_scc_fingerprint"],
            "planned_case_identity": left["planned_case_identity"] == right["planned_case_identity"],
            "planned_injection_identity": left["planned_injection_identity"]
            == right["planned_injection_identity"],
        }
        if not all(checks.values()):
            raise ProtocolError(f"Cross-model case parity failed at slot {slot}: {checks}")
        parity_rows.append(
            {
                "slot": slot,
                "case_uid": left["case_uid"],
                "physical_scc_fingerprint": left["physical_scc_fingerprint"],
                "injected_case_fingerprint": left["planned_scc_fingerprint"],
                "injection_seed": left["planned_injection_identity"]["seed"],
                "checks": checks,
                "passed": True,
            }
        )
    if len({row["physical_scc_fingerprint"] for row in parity_rows}) != 4:
        raise ProtocolError("Fallback is not four unique physical source SCCs")
    return selected, graphs_by_model, parity_rows


def expected_cell_path(cell: dict[str, Any], plans: dict[str, list[dict[str, Any]]]) -> Path:
    model = str(cell["model"])
    slot = int(cell["slot"])
    case = next(row for row in plans[model] if int(row["case_order"]) == slot)
    return (
        RESULTS_DIR
        / str(cell["profile"])
        / cost.safe_token(model)
        / "results"
        / f"{case['case_id']}__sa-mcgs.json"
    )


def parent_nominal_path(model: str, case: dict[str, Any], frozen: dict[str, Any]) -> Path:
    parent_dir = repo_path(frozen["parent"]["run_directory"])
    return (
        parent_dir
        / "cost"
        / cost.safe_token(model)
        / "results"
        / f"{case['case_id']}__sa-mcgs.json"
    )


def estimate_usd(model: str, usage: dict[str, Any], frozen: dict[str, Any] | None = None) -> float:
    frozen = frozen or protocol()
    rates = frozen["pricing"]["rates_usd_per_million_tokens"][model]
    prompt = float(usage.get("prompt_tokens") or 0)
    completion = float(usage.get("completion_tokens") or 0)
    return prompt / 1_000_000 * float(rates["input"]) + completion / 1_000_000 * float(
        rates["output"]
    )


def validate_pricing(frozen: dict[str, Any]) -> dict[str, Any]:
    pricing = load_json(repo_path(frozen["parent"]["pricing_snapshot"]))
    amendment = load_json(repo_path(frozen["parent"]["budget_amendment"]))
    checks = {
        "pricing_version_snapshot": pricing.get("pricing_version") == frozen["pricing"]["pricing_version"],
        "pricing_version_amendment": amendment.get("pricing_version")
        == frozen["pricing"]["pricing_version"],
        "quota_per_unit": float(pricing.get("quota_per_unit") or 0) == 500000.0,
        "gpt_input": float(pricing["models"]["gpt-4o"]["derived_input_usd_per_million"])
        == float(frozen["pricing"]["rates_usd_per_million_tokens"]["gpt-4o"]["input"]),
        "gpt_output": float(pricing["models"]["gpt-4o"]["derived_output_usd_per_million"])
        == float(frozen["pricing"]["rates_usd_per_million_tokens"]["gpt-4o"]["output"]),
        "gemini_input": float(
            pricing["models"]["gemini-2.5-pro"]["derived_input_usd_per_million"]
        )
        == float(
            frozen["pricing"]["rates_usd_per_million_tokens"]["gemini-2.5-pro"]["input"]
        ),
        "gemini_output": float(
            pricing["models"]["gemini-2.5-pro"]["derived_output_usd_per_million"]
        )
        == float(
            frozen["pricing"]["rates_usd_per_million_tokens"]["gemini-2.5-pro"]["output"]
        ),
    }
    if not all(checks.values()):
        raise ProtocolError(f"Frozen pricing parity failed: {checks}")
    return {"checks": checks, "passed": True, "pricing": pricing}


def read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProtocolError(f"Malformed {label} line {lineno}") from exc
            if not isinstance(row, dict):
                raise ProtocolError(f"Non-object {label} line {lineno}")
            rows.append(row)
    return rows


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"Cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise ProtocolError(f"{label} is not a JSON object: {path}")
    return payload


def exact_int(value: Any, expected: int) -> bool:
    return type(value) is int and value == int(expected)


def same_number(value: Any, expected: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    actual = float(value)
    target = float(expected)
    return abs(actual - target) <= max(1e-12, abs(target) * 1e-12)


def parent_expected_cells(
    full_plans: dict[str, list[dict[str, Any]]],
) -> dict[tuple[str, str, int], dict[str, Any]]:
    expected: dict[tuple[str, str, int], dict[str, Any]] = {}
    for model in MODELS:
        for case in full_plans[model]:
            for method in PARENT_METHODS:
                key = (model, method, int(case["case_order"]))
                if key in expected:
                    raise ProtocolError(f"Duplicate frozen parent cell: {key}")
                expected[key] = case
    if len(expected) != 72:
        raise ProtocolError(f"Frozen parent cell count is {len(expected)}, expected 72")
    return expected


def parent_cost_ledger_index(
    frozen: dict[str, Any], full_plans: dict[str, list[dict[str, Any]]]
) -> tuple[Path, list[dict[str, Any]], dict[tuple[str, str, int], dict[str, Any]]]:
    parent_dir = repo_path(frozen["parent"]["run_directory"])
    ledger_path = parent_dir / "budget_ledger.jsonl"
    all_rows = read_jsonl(ledger_path, "parent budget ledger")
    expected = parent_expected_cells(full_plans)
    indexed: dict[tuple[str, str, int], dict[str, Any]] = {}
    for lineno, row in enumerate(all_rows, 1):
        stage = row.get("stage")
        if stage == "prior":
            continue
        if stage != "cost":
            raise ProtocolError(
                f"Unexpected parent ledger stage at line {lineno}: {stage!r}"
            )
        slot = row.get("case_slot")
        if type(slot) is not int:
            raise ProtocolError(f"Invalid parent ledger case_slot at line {lineno}")
        key = (str(row.get("model")), str(row.get("method")), slot)
        if key not in expected:
            raise ProtocolError(f"Unexpected parent cost ledger cell at line {lineno}: {key}")
        if key in indexed:
            raise ProtocolError(f"Duplicate parent cost ledger cell: {key}")
        indexed[key] = row
    return ledger_path, all_rows, indexed


def parent_estimate_usd(
    frozen: dict[str, Any], model: str, usage: dict[str, Any]
) -> float:
    parent = load_json(repo_path(frozen["parent"]["frozen_protocol"]))
    rates = parent["budget"]["conservative_estimation_rates_usd_per_million_tokens"][model]
    prompt = float(usage.get("prompt_tokens") or 0)
    completion = float(usage.get("completion_tokens") or 0)
    return prompt / 1_000_000 * float(rates["input"]) + completion / 1_000_000 * float(
        rates["output"]
    )


def validate_parent_result_binding(
    *,
    frozen: dict[str, Any],
    model: str,
    method: str,
    case: dict[str, Any],
    graph: Any,
    path: Path,
    result: dict[str, Any],
    ledger_row: dict[str, Any],
) -> dict[str, Any]:
    try:
        cost.validate_result_case_identity(result, case, graph)
    except Exception as exc:
        raise ProtocolError(f"Parent result identity failure for {path}: {exc}") from exc

    parent = load_json(repo_path(frozen["parent"]["frozen_protocol"]))
    expected_config = parent_experiment_config_payload(frozen, model, method)
    expected_config_hash = canonical_hash(expected_config)
    usage = result.get("llm_usage_summary") or {}
    if not isinstance(usage, dict):
        raise ProtocolError(f"Parent result has non-object usage: {path}")
    result_valid = not bool(result.get("cost_audit_error"))
    result_method_names = {
        "naive-single": {"naive-single", "full-scc-naive-single"},
        "lea": {"lea"},
        "sa-mcgs": {"sa-mcgs"},
    }
    result_checks = {
        "model": result.get("model") == model,
        "method": result.get("method") in result_method_names[method],
        "case_id": result.get("case_id") == case["case_id"],
        "case_order": exact_int(result.get("case_order"), int(case["case_order"])),
        "case_uid": result.get("case_uid") == case["case_uid"],
        "physical_scc": result.get("physical_scc_fingerprint")
        == case["physical_scc_fingerprint"],
        "planned_injection": result.get("planned_scc_fingerprint")
        == case["planned_scc_fingerprint"],
        "actual_injection": result.get("actual_scc_fingerprint")
        == case["planned_scc_fingerprint"],
        "injection_identity": result.get("actual_injection_identity")
        == case["planned_injection_identity"],
        "protocol_version": result.get("protocol_version") == parent["protocol_version"],
        "protocol_sha256": result.get("protocol_sha256")
        == frozen["parent"]["frozen_protocol_sha256"],
        "config_payload": result.get("experiment_config") == expected_config,
        "config_hash_internal": result.get("experiment_config_sha256")
        == canonical_hash(result.get("experiment_config")),
        "config_hash_expected": result.get("experiment_config_sha256")
        == expected_config_hash,
        "relation_profile": result.get("relation_prior_profile")
        == ("nominal" if method == "sa-mcgs" else None),
        "strict_denominator": result.get("strict_denominator_member") is True,
    }
    if not all(result_checks.values()):
        raise ProtocolError(f"Parent result parity failure for {path}: {result_checks}")

    expected_cost = parent_estimate_usd(frozen, model, usage)
    canonical_result_sha256 = canonical_hash(result)
    ledger_checks = {
        "stage": ledger_row.get("stage") == "cost",
        "relation_profile": ledger_row.get("relation_profile") is None,
        "model": ledger_row.get("model") == model,
        "method": ledger_row.get("method") == method,
        "case_id": ledger_row.get("case_id") == case["case_id"],
        "case_slot": exact_int(ledger_row.get("case_slot"), int(case["case_order"])),
        "case_uid": ledger_row.get("case_uid") == case["case_uid"],
        "physical_scc": ledger_row.get("physical_scc_fingerprint")
        == case["physical_scc_fingerprint"],
        "valid": ledger_row.get("valid") is result_valid,
        "error_type": ledger_row.get("error_type") == result.get("error_type"),
        "usage": ledger_row.get("usage") == usage,
        "estimated_usd": same_number(ledger_row.get("estimated_usd"), expected_cost),
        "canonical_result_sha256": ledger_row.get("result_sha256_before_write")
        == canonical_result_sha256,
    }
    if not all(ledger_checks.values()):
        raise ProtocolError(f"Parent result/ledger binding failure for {path}: {ledger_checks}")
    return {
        "canonical_result_sha256": canonical_result_sha256,
        "ledger_result_sha256": ledger_row["result_sha256_before_write"],
        "usage": usage,
        "estimated_usd": expected_cost,
        "result_checks": result_checks,
        "ledger_checks": ledger_checks,
    }


def parent_cost_terminal(
    frozen: dict[str, Any], full_plans: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    parent_dir = repo_path(frozen["parent"]["run_directory"])
    ledger_path, ledger_rows, ledger_index = parent_cost_ledger_index(frozen, full_plans)
    expected = parent_expected_cells(full_plans)
    graphs = {model: cost.load_graphs(full_plans[model]) for model in MODELS}
    disk = Counter()
    ledger_counts = Counter()
    integrity_rows = []
    for (model, method, slot), case in expected.items():
        path = (
            parent_dir
            / "cost"
            / cost.safe_token(model)
            / "results"
            / f"{case['case_id']}__{cost.safe_token(method)}.json"
        )
        result_exists = path.is_file()
        ledger_row = ledger_index.get((model, method, slot))
        if result_exists != (ledger_row is not None):
            raise ProtocolError(
                f"Parent result/ledger presence mismatch for {model}/{method}/slot-{slot:02d}"
            )
        if not result_exists:
            disk["missing"] += 1
            ledger_counts["missing"] += 1
            continue
        result = load_json_object(path, "parent result")
        binding = validate_parent_result_binding(
            frozen=frozen,
            model=model,
            method=method,
            case=case,
            graph=graphs[model][case["domain"]],
            path=path,
            result=result,
            ledger_row=ledger_row,
        )
        disk["attempted"] += 1
        disk["invalid" if result.get("cost_audit_error") else "valid"] += 1
        ledger_counts["attempted"] += 1
        ledger_counts["invalid" if not ledger_row["valid"] else "valid"] += 1
        integrity_rows.append(
            {
                "model": model,
                "method": method,
                "slot": slot,
                "case_id": case["case_id"],
                "case_uid": case["case_uid"],
                "result_path": str(path),
                "result_file_sha256": file_hash(path),
                "result_canonical_sha256": binding["canonical_result_sha256"],
                "ledger_result_sha256": binding["ledger_result_sha256"],
                "valid": ledger_row["valid"],
                "passed": True,
            }
        )
    status_path = parent_dir / "execution_status.json"
    status = load_json(status_path) if status_path.exists() else {}
    status_counts = (status.get("cells") or {}).get("cost") or {}
    accepted_states = {"cost_complete", "prior_running", "prior_complete"}
    disk_terminal = (
        disk["attempted"] == 72
        and disk["missing"] == 0
        and disk["valid"] + disk["invalid"] == 72
    )
    ledger_terminal = (
        len(ledger_index) == 72
        and ledger_counts["attempted"] == 72
        and ledger_counts["missing"] == 0
        and ledger_counts["valid"] + ledger_counts["invalid"] == 72
    )
    status_terminal = (
        status.get("state") in accepted_states
        and int(status_counts.get("attempted") or 0) == 72
        and int(status_counts.get("missing") or 0) == 0
        and int(status_counts.get("valid") or 0) + int(status_counts.get("invalid") or 0) == 72
    )
    return {
        "status_path": str(status_path),
        "status_state": status.get("state"),
        "status_counts": status_counts,
        "parent_ledger_path": str(ledger_path),
        "parent_ledger_sha256": file_hash(ledger_path) if ledger_path.is_file() else None,
        "parent_ledger_total_rows": len(ledger_rows),
        "disk_counts": {key: disk[key] for key in ("attempted", "valid", "invalid", "missing")},
        "ledger_counts": {
            key: ledger_counts[key] for key in ("attempted", "valid", "invalid", "missing")
        },
        "integrity_checked_cells": len(integrity_rows),
        "integrity_rows": integrity_rows,
        "disk_terminal_72_of_72": disk_terminal,
        "ledger_integrity_72_of_72": ledger_terminal,
        "status_terminal_72_of_72": status_terminal,
        "terminal_72_of_72": disk_terminal and ledger_terminal and status_terminal,
    }


def verify_nominal_reuse(
    frozen: dict[str, Any],
    plans: dict[str, list[dict[str, Any]]],
    graphs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    full_plans = load_parent_plans(frozen)
    parent_ledger_path, _, parent_ledger = parent_cost_ledger_index(frozen, full_plans)
    for model in MODELS:
        expected_config = parent_nominal_config_payload(model)
        expected_config_hash = canonical_hash(expected_config)
        for case in plans[model]:
            path = parent_nominal_path(model, case, frozen)
            ledger_key = (model, "sa-mcgs", int(case["case_order"]))
            ledger_row = parent_ledger.get(ledger_key)
            if path.is_file() != (ledger_row is not None):
                raise ProtocolError(
                    "Nominal parent result/ledger presence mismatch for "
                    f"{model}/slot-{int(case['case_order']):02d}"
                )
            if not path.is_file():
                missing.append(
                    {
                        "model": model,
                        "slot": case["case_order"],
                        "case_id": case["case_id"],
                        "source_result": str(path),
                    }
                )
                continue
            result = load_json_object(path, "nominal parent result")
            binding = validate_parent_result_binding(
                frozen=frozen,
                model=model,
                method="sa-mcgs",
                case=case,
                graph=graphs[model][case["domain"]],
                path=path,
                result=result,
                ledger_row=ledger_row,
            )
            implementation = frozen["implementation_lock"]
            terminal_error = bool(result.get("cost_audit_error"))
            prompt_checks = {
                field: result.get(field) == implementation[field] for field in PROMPT_FIELDS
            }
            if terminal_error:
                # An invalid nominal cell remains a terminal strict-denominator member.
                # It may have failed before prompt metadata was constructed; code/config
                # locks, rather than outcome fields, establish prompt parity in that case.
                prompt_checks = {
                    field: result.get(field) in (None, implementation[field]) for field in PROMPT_FIELDS
                }
            checks = {
                "model": result.get("model") == model,
                "case_id": result.get("case_id") == case["case_id"],
                "case_order": int(result.get("case_order") or -1) == int(case["case_order"]),
                "case_uid": result.get("case_uid") == case["case_uid"],
                "physical_scc": result.get("physical_scc_fingerprint")
                == case["physical_scc_fingerprint"],
                "planned_injection": result.get("planned_scc_fingerprint")
                == case["planned_scc_fingerprint"],
                "actual_injection": result.get("actual_scc_fingerprint")
                == case["planned_scc_fingerprint"],
                "injection_identity": result.get("actual_injection_identity")
                == case["planned_injection_identity"],
                "budget_60": int(result.get("cost_audit_budget") or -1) == 60,
                "algorithm_budget_60": (
                    result.get("budget") in (None, 60)
                    if terminal_error
                    else int(result.get("budget") or -1) == 60
                ),
                "case_concurrency_1": int(result.get("case_concurrency") or -1) == 1,
                "internal_concurrency_1": int(result.get("internal_concurrency") or -1) == 1,
                "compression_current": (
                    result.get("mcgs_compression_profile") in (None, "current")
                    if terminal_error
                    else result.get("mcgs_compression_profile") == "current"
                ),
                "relation_first": (
                    result.get("relation_first_enabled") in (None, True)
                    if terminal_error
                    else result.get("relation_first_enabled") is True
                ),
                "config_payload": result.get("experiment_config") == expected_config,
                "config_hash_internal": result.get("experiment_config_sha256")
                == canonical_hash(result.get("experiment_config")),
                "config_hash_expected": result.get("experiment_config_sha256")
                == expected_config_hash,
                "nominal_profile": result.get("relation_prior_profile") == "nominal",
                "parent_protocol": result.get("protocol_version")
                == load_json(repo_path(frozen["parent"]["frozen_protocol"]))["protocol_version"],
                "parent_protocol_hash": result.get("protocol_sha256")
                == frozen["parent"]["frozen_protocol_sha256"],
                "strict_denominator": result.get("strict_denominator_member") is True,
                "prompt_semantics": all(prompt_checks.values()),
            }
            if not all(checks.values()):
                raise ProtocolError(f"Nominal reuse parity failure for {path}: {checks}")
            rows.append(
                {
                    "model": model,
                    "slot": case["case_order"],
                    "case_id": case["case_id"],
                    "case_uid": case["case_uid"],
                    "physical_scc_fingerprint": case["physical_scc_fingerprint"],
                    "injected_case_fingerprint": case["planned_scc_fingerprint"],
                    "source_result": str(path),
                    "source_result_sha256": file_hash(path),
                    "source_result_canonical_sha256": binding[
                        "canonical_result_sha256"
                    ],
                    "parent_ledger": str(parent_ledger_path),
                    "parent_ledger_result_sha256": binding["ledger_result_sha256"],
                    "source_valid": not bool(result.get("cost_audit_error")),
                    "source_error_type": result.get("error_type"),
                    "source_usage": result.get("llm_usage_summary") or {},
                    "source_list_estimated_usd": estimate_usd(
                        model, result.get("llm_usage_summary") or {}, frozen
                    ),
                    "expected_config_sha256": expected_config_hash,
                    "prompt_checks": prompt_checks,
                    "parity_checks": checks,
                    "passed": True,
                }
            )
    return {
        "expected_cells": 8,
        "ready_cells": len(rows),
        "missing_cells": len(missing),
        "all_eight_ready": len(rows) == 8 and not missing,
        "invalid_nominal_cells_retained": sum(not row["source_valid"] for row in rows),
        "missing": missing,
        "cells": rows,
    }


def iter_ledger() -> list[dict[str, Any]]:
    return read_jsonl(LEDGER_PATH, "fallback budget ledger")


def append_ledger(payload: dict[str, Any]) -> None:
    cost.append_jsonl(LEDGER_PATH, payload)


def expected_execution_rows(
    fallback: dict[str, Any], plans: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    rows = []
    for raw in fallback["execution_order"]:
        row = copy.deepcopy(raw)
        model = str(row["model"])
        slot = int(row["slot"])
        case = next(item for item in plans[model] if int(item["case_order"]) == slot)
        path = expected_cell_path(row, plans)
        config = experiment_config_payload(model, str(row["profile"]))
        row.update(
            {
                "case_id": case["case_id"],
                "case_uid": case["case_uid"],
                "physical_scc_fingerprint": case["physical_scc_fingerprint"],
                "injected_case_fingerprint": case["planned_scc_fingerprint"],
                "result_path": str(path),
                "experiment_config_sha256": canonical_hash(config),
                "scientific_config_sha256": canonical_hash(scientific_config(config)),
            }
        )
        rows.append(row)
    return rows


def attach_protocol_fields(
    result: dict[str, Any], *, cell: dict[str, Any], case: dict[str, Any]
) -> None:
    frozen = protocol()
    config = experiment_config_payload(str(cell["model"]), str(cell["profile"]))
    result.update(
        {
            "protocol_version": frozen["protocol_version"],
            "protocol_sha256": file_hash(PROTOCOL_PATH),
            "runner_sha256": file_hash(Path(__file__).resolve()),
            "output_directory_name": EXPECTED_DIRECTORY,
            "fallback_manifest_sha256": frozen["selection"]["source_manifest_sha256"],
            "parent_protocol_sha256": frozen["parent"]["frozen_protocol_sha256"],
            "execution_order": int(cell["order"]),
            "case_slot": int(cell["slot"]),
            "physical_scc_fingerprint": case["physical_scc_fingerprint"],
            "experiment_config": config,
            "experiment_config_sha256": canonical_hash(config),
            "scientific_config_sha256": canonical_hash(scientific_config(config)),
            "relation_prior_profile": str(cell["profile"]),
            "relation_prior_weight": float(cell["relation_prior_weight"]),
            "strict_denominator_member": True,
            "invalid_is_terminal": True,
            "automatic_retry_permitted": False,
            "adaptive_case_replacement_permitted": False,
        }
    )


def validate_local_result(
    result: dict[str, Any],
    *,
    cell: dict[str, Any],
    case: dict[str, Any],
    graph: Any,
) -> None:
    frozen = protocol()
    cost.validate_result_case_identity(result, case, graph)
    expected_config = experiment_config_payload(str(cell["model"]), str(cell["profile"]))
    checks = {
        "protocol_version": result.get("protocol_version") == frozen["protocol_version"],
        "protocol_sha256": result.get("protocol_sha256") == file_hash(PROTOCOL_PATH),
        "runner_sha256": result.get("runner_sha256") == file_hash(Path(__file__).resolve()),
        "output_directory": result.get("output_directory_name") == EXPECTED_DIRECTORY,
        "manifest": result.get("fallback_manifest_sha256")
        == frozen["selection"]["source_manifest_sha256"],
        "parent_protocol": result.get("parent_protocol_sha256")
        == frozen["parent"]["frozen_protocol_sha256"],
        "execution_order": int(result.get("execution_order") or -1) == int(cell["order"]),
        "model": result.get("model") == cell["model"],
        "case_id": result.get("case_id") == case["case_id"],
        "case_uid": result.get("case_uid") == case["case_uid"],
        "case_slot": int(result.get("case_slot") or -1) == int(cell["slot"]),
        "physical_scc": result.get("physical_scc_fingerprint")
        == case["physical_scc_fingerprint"],
        "injected_scc": result.get("actual_scc_fingerprint")
        == case["planned_scc_fingerprint"],
        "profile": result.get("relation_prior_profile") == cell["profile"],
        "weight": float(result.get("relation_prior_weight") or -999)
        == float(cell["relation_prior_weight"]),
        "budget": int(result.get("cost_audit_budget") or -1) == 60,
        "case_concurrency": int(result.get("case_concurrency") or -1) == 1,
        "internal_concurrency": int(result.get("internal_concurrency") or -1) == 1,
        "config_payload": result.get("experiment_config") == expected_config,
        "config_hash": result.get("experiment_config_sha256") == canonical_hash(expected_config),
        "strict_denominator": result.get("strict_denominator_member") is True,
        "terminal_invalid_policy": result.get("invalid_is_terminal") is True
        and result.get("automatic_retry_permitted") is False,
    }
    if not result.get("cost_audit_error"):
        implementation = frozen["implementation_lock"]
        checks["prompt_semantics"] = all(
            result.get(field) == implementation[field] for field in PROMPT_FIELDS
        )
        checks["compression_current"] = result.get("mcgs_compression_profile") == "current"
        checks["relation_first"] = result.get("relation_first_enabled") is True
    if not all(checks.values()):
        raise ProtocolError(f"Saved fallback result failed parity: {checks}")


def assert_contiguous_orders(completed_orders: Iterable[int]) -> None:
    observed = sorted(set(int(value) for value in completed_orders))
    expected = list(range(1, len(observed) + 1))
    if observed != expected:
        raise ProtocolError(f"Out-of-order fallback results: {observed}; expected prefix {expected}")


def validate_launch_receipt(
    invocation_row: dict[str, Any], *, invocation_id: str
) -> tuple[dict[str, Any], Path, str]:
    raw_path = invocation_row.get("launch_receipt")
    if not isinstance(raw_path, str) or not raw_path or not Path(raw_path).is_absolute():
        raise ProtocolError(f"Invocation {invocation_id} has no absolute launch receipt path")
    receipt_path = Path(raw_path)
    if not receipt_path.is_file():
        raise ProtocolError(f"Invocation {invocation_id} launch receipt is missing: {receipt_path}")
    receipt_sha256 = file_hash(receipt_path)
    receipt = load_json_object(receipt_path, "fallback launch receipt")
    frozen = protocol()
    runner_sha256 = file_hash(Path(__file__).resolve())
    checks = {
        "receipt_hash": invocation_row.get("launch_receipt_sha256") == receipt_sha256,
        "receipt_version": receipt.get("receipt_version")
        == "prior_fallback_launch_receipt_v1",
        "invocation_id": receipt.get("invocation_id") == invocation_id,
        "protocol_version": receipt.get("protocol_version") == frozen["protocol_version"],
        "protocol_sha256": receipt.get("protocol_sha256") == file_hash(PROTOCOL_PATH)
        == invocation_row.get("protocol_sha256"),
        "runner_sha256": receipt.get("runner_sha256") == runner_sha256
        == invocation_row.get("runner_sha256"),
        "fallback_manifest": receipt.get("fallback_manifest_sha256")
        == frozen["selection"]["source_manifest_sha256"],
        "parent_protocol": receipt.get("parent_protocol_sha256")
        == frozen["parent"]["frozen_protocol_sha256"],
        "receipt_paid_authorization": receipt.get("paid_execution_explicitly_authorized")
        is True,
        "invocation_paid_authorization": invocation_row.get(
            "paid_execution_explicitly_authorized"
        )
        is True,
    }
    if not all(checks.values()):
        raise ProtocolError(
            f"Invocation {invocation_id} launch receipt binding failure: {checks}"
        )
    return receipt, receipt_path, receipt_sha256


def local_ledger_identity_checks(
    row: dict[str, Any], cell: dict[str, Any]
) -> dict[str, bool]:
    raw_path = row.get("result_path")
    expected_path = Path(cell["result_path"]).resolve()
    return {
        "order": exact_int(row.get("order"), int(cell["order"])),
        "model": row.get("model") == cell["model"],
        "profile": row.get("profile") == cell["profile"],
        "slot": exact_int(row.get("slot"), int(cell["slot"])),
        "case_id": row.get("case_id") == cell["case_id"],
        "case_uid": row.get("case_uid") == cell["case_uid"],
        "absolute_result_path": isinstance(raw_path, str)
        and bool(raw_path)
        and Path(raw_path).is_absolute(),
        "result_path": isinstance(raw_path, str)
        and bool(raw_path)
        and Path(raw_path).resolve() == expected_path,
    }


def scan_execution_state(
    execution: list[dict[str, Any]],
    plans: dict[str, list[dict[str, Any]]],
    graphs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    expected_paths = {Path(row["result_path"]).resolve() for row in execution}
    actual_paths = {path.resolve() for path in RESULTS_DIR.glob("*/*/results/*.json")}
    unexpected = sorted(str(path) for path in actual_paths - expected_paths)
    if unexpected:
        raise ProtocolError(f"Unexpected result files would mix protocols: {unexpected}")
    completed = []
    rows = []
    results_by_order: dict[int, dict[str, Any]] = {}
    for cell in execution:
        path = Path(cell["result_path"])
        if path.exists():
            model = str(cell["model"])
            case = next(
                row for row in plans[model] if int(row["case_order"]) == int(cell["slot"])
            )
            result = load_json(path)
            validate_local_result(
                result,
                cell=cell,
                case=case,
                graph=graphs[model][case["domain"]],
            )
            order = int(cell["order"])
            completed.append(order)
            results_by_order[order] = result
            state = "terminal_invalid" if result.get("cost_audit_error") else "terminal_valid"
        else:
            result = None
            state = "missing"
        rows.append(
            {
                "order": cell["order"],
                "model": cell["model"],
                "slot": cell["slot"],
                "profile": cell["profile"],
                "case_id": cell["case_id"],
                "result_path": str(path),
                "state": state,
                "result_sha256": file_hash(path) if path.exists() else None,
                "error_type": (result or {}).get("error_type"),
            }
        )
    assert_contiguous_orders(completed)

    events = iter_ledger()
    expected_by_order = {int(cell["order"]): cell for cell in execution}
    invocations: dict[str, dict[str, Any]] = {}
    starts: dict[int, tuple[int, dict[str, Any]]] = {}
    finishes: dict[int, tuple[int, dict[str, Any]]] = {}
    for event_index, event in enumerate(events):
        event_type = event.get("event")
        if event_type == "run_invocation_start":
            invocation_id = event.get("invocation_id")
            if not isinstance(invocation_id, str) or not invocation_id:
                raise ProtocolError("Fallback invocation ledger row has no invocation_id")
            if invocation_id in invocations:
                raise ProtocolError(f"Duplicate fallback invocation ledger row: {invocation_id}")
            receipt, receipt_path, receipt_sha256 = validate_launch_receipt(
                event, invocation_id=invocation_id
            )
            invocations[invocation_id] = {
                "event_index": event_index,
                "row": event,
                "receipt": receipt,
                "receipt_path": receipt_path,
                "receipt_sha256": receipt_sha256,
            }
            continue
        if event_type not in {"cell_start", "cell_complete"}:
            raise ProtocolError(f"Unexpected fallback ledger event: {event_type!r}")
        order = event.get("order")
        if type(order) is not int or order not in expected_by_order:
            raise ProtocolError(f"Unexpected fallback ledger cell order: {order!r}")
        identity_checks = local_ledger_identity_checks(event, expected_by_order[order])
        if not all(identity_checks.values()):
            raise ProtocolError(
                f"Fallback {event_type} identity failure for cell {order}: {identity_checks}"
            )
        target = starts if event_type == "cell_start" else finishes
        if order in target:
            raise ProtocolError(f"Cell {order} has duplicate {event_type} ledger events")
        target[order] = (event_index, event)

    invocation_orders: dict[str, list[int]] = defaultdict(list)
    for order in range(1, 17):
        has_result = order in completed
        start_event = starts.get(order)
        finish_event = finishes.get(order)
        if finish_event and not has_result:
            raise ProtocolError(f"Ledger marks cell {order} complete but result is missing")
        if start_event and not finish_event:
            raise ProtocolError(
                f"Cell {order} has an unresolved started attempt; fail closed, do not rerun"
            )
        if finish_event and not start_event:
            raise ProtocolError(f"Cell {order} complete event lacks a start event")
        if has_result and (not start_event or not finish_event):
            raise ProtocolError(f"Cell {order} result lacks one start/complete ledger pair")
        if not start_event or not finish_event:
            continue

        start_index, start_row = start_event
        finish_index, finish_row = finish_event
        start_invocation = start_row.get("invocation_id")
        finish_invocation = finish_row.get("invocation_id")
        if (
            not isinstance(start_invocation, str)
            or not start_invocation
            or start_invocation != finish_invocation
            or start_invocation not in invocations
        ):
            raise ProtocolError(f"Cell {order} start/complete invocation binding failure")
        invocation = invocations[start_invocation]
        if not invocation["event_index"] < start_index < finish_index:
            raise ProtocolError(f"Cell {order} ledger event sequence is not invocation/start/complete")
        invocation_orders[start_invocation].append(order)

        result = results_by_order[order]
        result_path = Path(expected_by_order[order]["result_path"])
        usage = result.get("llm_usage_summary") or {}
        if not isinstance(usage, dict):
            raise ProtocolError(f"Fallback result has non-object usage for cell {order}")
        expected_cost = estimate_usd(str(expected_by_order[order]["model"]), usage)
        result_valid = not bool(result.get("cost_audit_error"))
        completion_checks = {
            "result_sha256": finish_row.get("result_sha256") == file_hash(result_path),
            "valid": finish_row.get("valid") is result_valid,
            "error_type": finish_row.get("error_type") == result.get("error_type"),
            "usage": finish_row.get("usage") == usage,
            "estimated_usd": same_number(finish_row.get("estimated_usd"), expected_cost),
            "invalid_is_terminal": finish_row.get("invalid_is_terminal") is True,
            "automatic_retry_forbidden": finish_row.get("automatic_retry_permitted") is False,
        }
        if not all(completion_checks.values()):
            raise ProtocolError(
                f"Fallback result/complete-ledger binding failure for cell {order}: "
                f"{completion_checks}"
            )

    for invocation_id, orders in invocation_orders.items():
        receipt = invocations[invocation_id]["receipt"]
        if not exact_int(receipt.get("next_execution_order"), min(orders)):
            raise ProtocolError(
                f"Invocation {invocation_id} receipt does not bind its first cell order"
            )
    return {
        "planned": 16,
        "attempted": len(completed),
        "valid": sum(row["state"] == "terminal_valid" for row in rows),
        "invalid": sum(row["state"] == "terminal_invalid" for row in rows),
        "missing": sum(row["state"] == "missing" for row in rows),
        "next_order": len(completed) + 1 if len(completed) < 16 else None,
        "contiguous_prefix": True,
        "no_unexpected_results": True,
        "ledger_integrity_passed": True,
        "ledger_events": len(events),
        "launch_receipts_verified": len(invocations),
        "rows": rows,
    }


def reserve_projection(
    frozen: dict[str, Any],
    full_plans: dict[str, list[dict[str, Any]]],
    execution: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    parent_dir = repo_path(frozen["parent"]["run_directory"])
    observations: dict[str, list[float]] = defaultdict(list)
    observation_rows = []
    for model in MODELS:
        for case in full_plans[model]:
            path = (
                parent_dir
                / "cost"
                / cost.safe_token(model)
                / "results"
                / f"{case['case_id']}__sa-mcgs.json"
            )
            if not path.exists():
                continue
            result = load_json(path)
            usage = result.get("llm_usage_summary") or {}
            amount = estimate_usd(model, usage, frozen)
            observations[model].append(amount)
            observation_rows.append(
                {
                    "source": "parent_nominal",
                    "model": model,
                    "slot": case["case_order"],
                    "result_path": str(path),
                    "estimated_usd": amount,
                }
            )
    for row in state["rows"]:
        if not row["state"].startswith("terminal_"):
            continue
        result = load_json(Path(row["result_path"]))
        amount = estimate_usd(str(row["model"]), result.get("llm_usage_summary") or {}, frozen)
        observations[str(row["model"])].append(amount)
        observation_rows.append(
            {
                "source": "fallback_completed",
                "model": row["model"],
                "order": row["order"],
                "result_path": row["result_path"],
                "estimated_usd": amount,
            }
        )
    reserves = {
        model: max(1.25, 1.5 * max(observations[model])) if observations[model] else 1.25
        for model in MODELS
    }
    missing_orders = {row["order"] for row in state["rows"] if row["state"] == "missing"}
    raw = sum(reserves[str(row["model"])] for row in execution if row["order"] in missing_orders)
    floor = float(frozen["pricing"]["fallback_projection_floor_usd"])
    floor_applied = state["attempted"] == 0
    projected = max(raw, floor) if floor_applied else raw
    return {
        "created_at": now_iso(),
        "reserve_policy": frozen["pricing"]["next_cell_reserve_policy"],
        "observed_parent_nominal_cells": {
            model: sum(row["source"] == "parent_nominal" and row["model"] == model for row in observation_rows)
            for model in MODELS
        },
        "observed_fallback_cells": {
            model: sum(row["source"] == "fallback_completed" and row["model"] == model for row in observation_rows)
            for model in MODELS
        },
        "reserve_per_missing_cell_usd": reserves,
        "missing_cells_by_model": dict(
            Counter(str(row["model"]) for row in execution if row["order"] in missing_orders)
        ),
        "raw_projected_missing_usd": raw,
        "initial_projection_floor_usd": floor,
        "initial_projection_floor_applied": floor_applied,
        "projected_missing_usd": projected,
        "observations": observation_rows,
    }


def validate_budget_arguments(
    frozen: dict[str, Any],
    projection: dict[str, Any],
    *,
    authorization_usd: float | None,
    authorization_remaining_usd: float | None,
    closeout_reserve_usd: float | None,
    derived_authorization_remaining_usd: float | None = None,
    require_remaining_assertion: bool = True,
) -> dict[str, Any]:
    supplied = (
        authorization_usd is not None
        and closeout_reserve_usd is not None
        and derived_authorization_remaining_usd is not None
        and (authorization_remaining_usd is not None or not require_remaining_assertion)
    )
    result: dict[str, Any] = {
        "arguments_supplied": supplied,
        "global_authorization_usd": authorization_usd,
        "asserted_global_authorization_remaining_usd": authorization_remaining_usd,
        "derived_global_authorization_remaining_usd": derived_authorization_remaining_usd,
        "closeout_reserve_usd": closeout_reserve_usd,
        "passed": False,
    }
    if not supplied:
        result["reason"] = "launch budget arguments were not supplied"
        return result
    assert authorization_usd is not None
    assert closeout_reserve_usd is not None
    assert derived_authorization_remaining_usd is not None
    derived = float(derived_authorization_remaining_usd)
    asserted_matches = (
        not require_remaining_assertion
        or (
            authorization_remaining_usd is not None
            and math.isclose(float(authorization_remaining_usd), derived, abs_tol=1e-6)
        )
    )
    checks = {
        "authorization_exactly_frozen_200": float(authorization_usd)
        == float(frozen["budget"]["global_authorization_usd"]),
        "derived_remaining_finite": math.isfinite(derived),
        "derived_remaining_nonnegative": derived >= 0,
        "derived_remaining_not_above_authorization": derived
        <= float(authorization_usd),
        "cli_remaining_equals_ledger_derived_remaining": asserted_matches,
        "closeout_at_least_frozen_minimum": float(closeout_reserve_usd)
        >= float(frozen["budget"]["minimum_closeout_reserve_usd"]),
    }
    required = float(projection["projected_missing_usd"]) + float(closeout_reserve_usd)
    checks["projected_tail_plus_closeout_within_remaining"] = required <= derived
    result.update(
        {
            "checks": checks,
            "projected_missing_usd": projection["projected_missing_usd"],
            "required_including_closeout_usd": required,
            "headroom_after_projection_and_closeout_usd": derived - required,
            "passed": all(checks.values()),
        }
    )
    if not result["passed"]:
        result["reason"] = "one or more frozen budget checks failed"
    return result


def resolve_cli_path(raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    cwd_candidate = (Path.cwd() / candidate).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return (REPO_ROOT / candidate).resolve()


def _parse_timestamp(value: Any, label: str) -> float:
    text = str(value or "").strip()
    if not text:
        raise ProtocolError(f"{label} timestamp is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolError(f"{label} timestamp is not ISO-8601: {text!r}") from exc
    if parsed.tzinfo is None:
        raise ProtocolError(f"{label} timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).timestamp()


def _nonnegative_amount(value: Any, label: str) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"{label} is not numeric") from exc
    if not math.isfinite(amount) or amount < 0:
        raise ProtocolError(f"{label} must be finite and nonnegative")
    return amount


def accounting_source(frozen: dict[str, Any], role: str) -> dict[str, Any]:
    matches = [
        row
        for row in frozen["upstream_accounting"]["sources"]
        if row.get("role") == role
    ]
    if len(matches) != 1:
        raise ProtocolError(f"Frozen accounting role {role!r} is not unique")
    return matches[0]


def audit_pre_accounting(frozen: dict[str, Any]) -> dict[str, Any]:
    source = accounting_source(frozen, "pre")
    path = repo_path(source["path"])
    assert_file_hash(path, source["sha256"], "pre accounting ledger")
    payload = load_json_object(path, "pre accounting ledger")
    entries = payload.get("entries")
    total = payload.get("all_new_calls_including_paid_smoke")
    cross_check = payload.get("account_balance_cross_check")
    if not isinstance(entries, list) or not isinstance(total, dict) or not isinstance(
        cross_check, dict
    ):
        raise ProtocolError("Pre accounting ledger has an incomplete aggregate schema")
    entry_spend = sum(
        _nonnegative_amount(row.get("estimated_usd"), "pre entry estimated_usd")
        for row in entries
        if isinstance(row, dict)
    )
    if len(entries) != sum(isinstance(row, dict) for row in entries):
        raise ProtocolError("Pre accounting ledger has a non-object entry")
    spend = _nonnegative_amount(total.get("estimated_usd"), "pre total estimated_usd")
    expected = _nonnegative_amount(source["expected_spend_usd"], "frozen pre spend")
    checks = {
        "scope": payload.get("scope") == "pre fairness baselines only",
        "currency": payload.get("currency") == "USD",
        "pricing_version": (payload.get("pricing") or {}).get("pricing_version")
        == frozen["pricing"]["pricing_version"],
        "entry_sum": math.isclose(entry_spend, spend, rel_tol=1e-12, abs_tol=1e-12),
        "frozen_total": math.isclose(spend, expected, rel_tol=1e-12, abs_tol=1e-12),
        "self_ledger_cross_check": same_number(cross_check.get("self_ledger_usd"), spend),
        "within_line_budget": total.get("within_line_budget") is True,
    }
    if not all(checks.values()):
        raise ProtocolError(f"Pre accounting ledger validation failed: {checks}")
    return {
        "role": "pre",
        "path": str(path),
        "sha256": file_hash(path),
        "schema": source["schema"],
        "validated_spend_usd": spend,
        "checks": checks,
    }


def audit_stage1_accounting(frozen: dict[str, Any]) -> dict[str, Any]:
    source = accounting_source(frozen, "stage1")
    summary_path = repo_path(source["path"])
    status_path = repo_path(source["status_path"])
    assert_file_hash(summary_path, source["sha256"], "Stage-1 accounting summary")
    assert_file_hash(status_path, source["status_sha256"], "Stage-1 terminal status")
    summary = load_json_object(summary_path, "Stage-1 accounting summary")
    status = load_json_object(status_path, "Stage-1 terminal status")
    cost_summary = summary.get("cost") or {}
    unique_paid = cost_summary.get("unique_paid_smoke_plus_new_formal") or {}
    spend = _nonnegative_amount(
        unique_paid.get("estimated_usd"), "Stage-1 unique paid estimated_usd"
    )
    expected = _nonnegative_amount(source["expected_spend_usd"], "frozen Stage-1 spend")
    status_ledger = status.get("self_ledger_all_phases") or {}
    gates = summary.get("gates") or {}
    matrix = summary.get("formal_matrix") or {}
    checks = {
        "summary_schema": summary.get("summary_version") == source["schema"],
        "summary_complete": summary.get("status") == "complete" and summary.get("passed") is True,
        "formal_matrix_complete": exact_int(matrix.get("cells"), 68)
        and exact_int(matrix.get("valid"), 68)
        and exact_int(matrix.get("invalid"), 0),
        "all_gates_passed": bool(gates) and all(value is True for value in gates.values()),
        "status_complete": status.get("state") == "complete"
        and exact_int(status.get("completed_jobs"), 68)
        and exact_int(status.get("remaining_jobs"), 0),
        "status_ledger_matches": same_number(status_ledger.get("estimated_usd"), spend),
        "frozen_total": math.isclose(spend, expected, rel_tol=1e-12, abs_tol=1e-12),
    }
    if not all(checks.values()):
        raise ProtocolError(f"Stage-1 accounting validation failed: {checks}")
    return {
        "role": "stage1",
        "path": str(summary_path),
        "sha256": file_hash(summary_path),
        "status_path": str(status_path),
        "status_sha256": file_hash(status_path),
        "schema": source["schema"],
        "validated_spend_usd": spend,
        "checks": checks,
    }


def audit_accounting_ledger(path: Path, *, role: str) -> dict[str, Any]:
    if role not in {"parent", "fallback"}:
        raise ProtocolError(f"Unsupported dynamic accounting ledger role: {role!r}")
    if not path.is_file():
        raise ProtocolError(f"Required {role} accounting ledger is missing: {path}")
    snapshot = path.read_bytes()
    rows: list[dict[str, Any]] = []
    spend_keys: set[tuple[Any, ...]] = set()
    spend = 0.0
    for lineno, raw in enumerate(snapshot.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"Malformed {role} ledger line {lineno}") from exc
        if not isinstance(row, dict):
            raise ProtocolError(f"{role} ledger line {lineno} is not an object")
        event = row.get("event")
        stage = row.get("stage")
        if role == "fallback" and event == "cell_complete":
            model = row.get("model")
            usage = row.get("usage")
            if model not in MODELS or not isinstance(usage, dict):
                raise ProtocolError(
                    f"Cannot reprice fallback ledger line {lineno}: invalid model or usage"
                )
            amount = _nonnegative_amount(
                row.get("estimated_usd"), f"{role} ledger line {lineno} estimated_usd"
            )
            expected_amount = estimate_usd(str(model), usage, protocol())
            if not math.isclose(amount, expected_amount, rel_tol=1e-12, abs_tol=1e-12):
                raise ProtocolError(
                    f"Fallback ledger line {lineno} amount does not match frozen pricing"
                )
            key = (
                "cell_complete",
                row.get("order"),
                row.get("model"),
                row.get("profile"),
                row.get("case_uid"),
            )
        elif role == "parent" and stage in {"cost", "prior"}:
            model = row.get("model")
            usage = row.get("usage")
            if model not in MODELS or not isinstance(usage, dict):
                raise ProtocolError(
                    f"Cannot reprice {role} ledger line {lineno}: invalid model or usage"
                )
            expected_list_amount = estimate_usd(str(model), usage, protocol())
            if row.get("xhub_list_estimated_usd") is not None:
                amount = _nonnegative_amount(
                    row.get("xhub_list_estimated_usd"),
                    f"{role} ledger line {lineno} xhub_list_estimated_usd",
                )
                if not math.isclose(
                    amount, expected_list_amount, rel_tol=1e-12, abs_tol=1e-12
                ):
                    raise ProtocolError(
                        f"{role} ledger line {lineno} list-rate amount does not match usage"
                    )
            elif role == "parent" and stage == "cost":
                # The first six frozen parent cost rows predate the explicit
                # list-price field.  Their conservative estimate was exactly
                # 2x the frozen XHub list rates, so accept only that
                # independently reproducible legacy representation.
                legacy_stress_amount = _nonnegative_amount(
                    row.get("estimated_usd"),
                    f"{role} ledger line {lineno} legacy estimated_usd",
                )
                if not math.isclose(
                    legacy_stress_amount,
                    expected_list_amount * 2.0,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    raise ProtocolError(
                        f"{role} ledger line {lineno} legacy 2x amount does not match usage"
                    )
                amount = legacy_stress_amount / 2.0
            else:
                raise ProtocolError(
                    f"{role} ledger line {lineno} lacks xhub_list_estimated_usd"
                )
            key = (
                str(stage),
                row.get("relation_profile") if stage == "prior" else "parent-cost",
                row.get("model"),
                row.get("method"),
                row.get("case_uid"),
            )
        elif role == "fallback" and event in {"run_invocation_start", "cell_start"}:
            amount = 0.0
            key = ()
        else:
            raise ProtocolError(
                f"Unrecognized {role} accounting ledger line {lineno}; cannot derive spend"
            )
        if key:
            if any(value in (None, "") for value in key[1:]):
                raise ProtocolError(f"Incomplete spend identity in {role} ledger line {lineno}")
            if key in spend_keys:
                raise ProtocolError(f"Duplicate spend cell in {role} ledger: {key}")
            spend_keys.add(key)
            spend += amount
        rows.append(row)
    return {
        "role": role,
        "path": str(path),
        "sha256": "sha256:" + hashlib.sha256(snapshot).hexdigest(),
        "nonempty_line_count": len(rows),
        "spend_cell_count": len(spend_keys),
        "validated_spend_usd": spend,
    }


def validate_balance_snapshot(
    frozen: dict[str, Any],
    *,
    context_kind: str | None,
    snapshot_path: str | None,
    snapshot_sha256: str | None,
    asserted_balance_usd: float | None,
    asserted_captured_at: str | None,
    validation_mode: str = "invocation_start",
    expected_launch_snapshot_sha256: str | None = None,
) -> dict[str, Any]:
    if validation_mode not in {"invocation_start", "same_invocation_per_cell"}:
        raise ProtocolError(f"Unknown balance snapshot validation mode: {validation_mode!r}")
    supplied = all(
        value not in (None, "")
        for value in (
            context_kind,
            snapshot_path,
            snapshot_sha256,
            asserted_balance_usd,
            asserted_captured_at,
        )
    )
    if not supplied:
        return {
            "arguments_supplied": False,
            "passed": False,
            "authoritative": False,
            "reason": "hashed balance snapshot and consistency assertions were not supplied",
        }
    assert snapshot_path is not None and snapshot_sha256 is not None
    path = resolve_cli_path(snapshot_path)
    if not path.is_file():
        raise ProtocolError(f"Fresh balance snapshot does not exist: {path}")
    actual_hash = file_hash(path)
    if actual_hash != snapshot_sha256:
        raise ProtocolError(
            f"Fresh balance snapshot hash mismatch: {actual_hash} != {snapshot_sha256}"
        )
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ProtocolError("Fresh balance snapshot must be an object")
    budget = frozen["budget"]
    captured_at = str(payload.get("captured_at") or "")
    captured_epoch = _parse_timestamp(captured_at, "balance snapshot")
    age_seconds = time.time() - captured_epoch
    total_available = _nonnegative_amount(
        payload.get("total_available_usd"), "balance snapshot total_available_usd"
    )
    within_ttl = age_seconds <= float(budget["balance_snapshot_ttl_seconds"])
    artifact_checks = {
        "schema": payload.get("schema_version") == budget["balance_snapshot_schema"],
        "context_kind": payload.get("context_kind") == context_kind,
        "provider": payload.get("provider") == "XHub",
        "source": payload.get("source") == "coordinator_captured_account_balance",
        "captured_by": payload.get("captured_by")
        == budget["balance_snapshot_captured_by"],
        "authorization_scope": payload.get("authorization_scope_id")
        == budget["authorization_scope_id"],
        "timestamp_matches_cli_assertion": captured_at == asserted_captured_at,
        "balance_matches_cli_assertion": asserted_balance_usd is not None
        and math.isclose(total_available, float(asserted_balance_usd), abs_tol=1e-6),
        "not_from_future": age_seconds >= -60,
        "same_invocation_launch_hash": validation_mode == "invocation_start"
        or (
            expected_launch_snapshot_sha256 is not None
            and actual_hash == expected_launch_snapshot_sha256
        ),
    }
    freshness_required = validation_mode == "invocation_start"
    freshness_passed = within_ttl if freshness_required else True
    required_checks = {
        **artifact_checks,
        "freshness_requirement_satisfied": freshness_passed,
    }
    if not all(required_checks.values()):
        raise ProtocolError(
            f"Balance snapshot validation failed in {validation_mode}: {required_checks}"
        )
    return {
        "arguments_supplied": True,
        "path": str(path),
        "sha256": actual_hash,
        "payload": payload,
        "age_seconds": age_seconds,
        "ttl_seconds": budget["balance_snapshot_ttl_seconds"],
        "within_ttl_at_validation": within_ttl,
        "freshness_enforced": freshness_required,
        "validation_mode": validation_mode,
        "expected_launch_snapshot_sha256": expected_launch_snapshot_sha256,
        "total_available_usd": total_available,
        "checks": required_checks,
        "passed": True,
        "authoritative": context_kind == "authoritative",
    }


def accounting_provenance(
    frozen: dict[str, Any],
    *,
    context_kind: str | None,
    fresh_xhub_balance_usd: float | None,
    fresh_balance_captured_at: str | None,
    upstream_ledgers: list[str] | None,
    balance_snapshot_path: str | None = None,
    balance_snapshot_sha256: str | None = None,
    snapshot_validation_mode: str = "invocation_start",
    expected_launch_snapshot_sha256: str | None = None,
) -> dict[str, Any]:
    if upstream_ledgers:
        raise ProtocolError(
            "Additional --upstream-ledger inputs are forbidden; the exact pre, Stage-1, "
            "and parent sources are frozen and loaded automatically"
        )
    parent_source = accounting_source(frozen, "parent")
    parent_ledger = repo_path(frozen["parent"]["run_directory"]) / "budget_ledger.jsonl"
    expected_parent_relative = (
        str(frozen["parent"]["run_directory"]).rstrip("/") + "/budget_ledger.jsonl"
    )
    if parent_source.get("path") != expected_parent_relative:
        raise ProtocolError("Frozen parent accounting path disagrees with parent run directory")
    frozen_upstream_rows = [
        audit_pre_accounting(frozen),
        audit_stage1_accounting(frozen),
        audit_accounting_ledger(parent_ledger, role="parent"),
    ]
    ledger_rows = list(frozen_upstream_rows)
    if LEDGER_PATH.exists():
        ledger_rows.append(audit_accounting_ledger(LEDGER_PATH.resolve(), role="fallback"))
    total_spend = sum(float(row["validated_spend_usd"]) for row in ledger_rows)
    authorization = float(frozen["budget"]["global_authorization_usd"])
    derived_remaining = authorization - total_spend
    snapshot = validate_balance_snapshot(
        frozen,
        context_kind=context_kind,
        snapshot_path=balance_snapshot_path,
        snapshot_sha256=balance_snapshot_sha256,
        asserted_balance_usd=fresh_xhub_balance_usd,
        asserted_captured_at=fresh_balance_captured_at,
        validation_mode=snapshot_validation_mode,
        expected_launch_snapshot_sha256=expected_launch_snapshot_sha256,
    )
    checks = {
        "context_kind_declared": context_kind in {"synthetic", "authoritative"},
        "hashed_balance_snapshot_valid": snapshot.get("passed") is True,
        "exact_frozen_upstream_roles": [row["role"] for row in frozen_upstream_rows]
        == frozen["upstream_accounting"]["required_roles"],
        "pre_ledger_hash_valid": frozen_upstream_rows[0]["sha256"]
        == accounting_source(frozen, "pre")["sha256"],
        "stage1_ledger_hash_valid": frozen_upstream_rows[1]["sha256"]
        == accounting_source(frozen, "stage1")["sha256"],
        "parent_cost_ledger_hashed": frozen_upstream_rows[2]["path"]
        == str(parent_ledger),
        "additional_cli_ledgers_absent": not upstream_ledgers,
        "fallback_ledger_automatically_included": not LEDGER_PATH.exists()
        or any(row["path"] == str(LEDGER_PATH.resolve()) for row in ledger_rows),
        "derived_remaining_finite": math.isfinite(derived_remaining),
        "derived_remaining_nonnegative": derived_remaining >= 0,
    }
    return {
        "arguments_supplied": snapshot.get("arguments_supplied") is True,
        "accounting_context_kind": context_kind,
        "balance_snapshot": snapshot,
        "upstream_ledgers": frozen_upstream_rows,
        "fallback_ledger": next(
            (row for row in ledger_rows if row["role"] == "fallback"), None
        ),
        "all_accounting_ledgers": ledger_rows,
        "validated_cumulative_spend_usd": total_spend,
        "derived_authorization_remaining_usd": derived_remaining,
        "checks": checks,
        "passed": all(checks.values()),
        "authoritative_for_paid_launch": all(checks.values())
        and snapshot.get("authoritative") is True,
        "note": "Authorization remaining is derived from validated ledgers; CLI values are consistency assertions only.",
    }


def write_status(state: str, extra: dict[str, Any] | None = None) -> None:
    payload = {
        "protocol_version": EXPECTED_PROTOCOL_VERSION,
        "protocol_sha256": file_hash(PROTOCOL_PATH),
        "runner_sha256": file_hash(Path(__file__).resolve()),
        "output_directory_name": RUN_DIR.name,
        "updated_at": now_iso(),
        "state": state,
    }
    if state.startswith("offline_"):
        payload["model_or_xhub_calls_made_by_offline_command"] = 0
    if extra:
        payload.update(extra)
    cost.atomic_write_json(STATUS_PATH, payload)


def perform_preflight(
    *,
    authorization_usd: float | None = None,
    authorization_remaining_usd: float | None = None,
    closeout_reserve_usd: float | None = None,
    accounting_context_kind: str | None = None,
    fresh_xhub_balance_usd: float | None = None,
    fresh_balance_captured_at: str | None = None,
    fresh_balance_snapshot: str | None = None,
    fresh_balance_snapshot_sha256: str | None = None,
    upstream_ledgers: list[str] | None = None,
    require_remaining_assertion: bool = True,
    snapshot_validation_mode: str = "invocation_start",
    expected_launch_snapshot_sha256: str | None = None,
    command: str = "preflight",
) -> dict[str, Any]:
    frozen = protocol()
    source_hashes = validate_source_hashes(frozen)
    fallback = validate_manifest(frozen)
    pricing = validate_pricing(frozen)
    plans, graphs, parity_rows = validate_selected_plans(frozen, fallback)
    full_plans = load_parent_plans(frozen)
    terminal = parent_cost_terminal(frozen, full_plans)
    nominal = verify_nominal_reuse(frozen, plans, graphs)
    config_audit = paired_config_audit()
    execution = expected_execution_rows(fallback, plans)
    state = scan_execution_state(execution, plans, graphs)
    projection = reserve_projection(frozen, full_plans, execution, state)
    accounting = accounting_provenance(
        frozen,
        context_kind=accounting_context_kind,
        fresh_xhub_balance_usd=fresh_xhub_balance_usd,
        fresh_balance_captured_at=fresh_balance_captured_at,
        upstream_ledgers=upstream_ledgers,
        balance_snapshot_path=fresh_balance_snapshot,
        balance_snapshot_sha256=fresh_balance_snapshot_sha256,
        snapshot_validation_mode=snapshot_validation_mode,
        expected_launch_snapshot_sha256=expected_launch_snapshot_sha256,
    )
    budget = validate_budget_arguments(
        frozen,
        projection,
        authorization_usd=authorization_usd,
        authorization_remaining_usd=authorization_remaining_usd,
        closeout_reserve_usd=closeout_reserve_usd,
        derived_authorization_remaining_usd=accounting[
            "derived_authorization_remaining_usd"
        ],
        require_remaining_assertion=require_remaining_assertion,
    )
    if budget["arguments_supplied"] and accounting["arguments_supplied"]:
        snapshot_balance = float(accounting["balance_snapshot"]["total_available_usd"])
        remaining_within_fresh_balance = float(
            accounting["derived_authorization_remaining_usd"]
        ) <= snapshot_balance
        budget.setdefault("checks", {})[
            "ledger_derived_remaining_not_above_fresh_xhub_balance"
        ] = remaining_within_fresh_balance
        budget["passed"] = bool(budget["passed"] and remaining_within_fresh_balance)
        if not budget["passed"]:
            budget["reason"] = "one or more frozen budget checks failed"
    intrinsic_ready = (
        terminal["terminal_72_of_72"]
        and nominal["all_eight_ready"]
        and config_audit["all_only_relation_prior_changed"]
        and state["contiguous_prefix"]
        and state["no_unexpected_results"]
    )
    ready_for_paid_run = (
        intrinsic_ready
        and budget["passed"]
        and accounting["authoritative_for_paid_launch"]
        and state["missing"] > 0
    )
    already_complete = intrinsic_ready and state["missing"] == 0

    for model in MODELS:
        plan_dir = PREFLIGHT_DIR / "plans" / cost.safe_token(model)
        cost.persist_case_plan(plan_dir, plans[model])
    cost.atomic_write_json(
        PREFLIGHT_DIR / "source_hash_audit.json",
        {
            "created_at": now_iso(),
            "protocol_sha256": file_hash(PROTOCOL_PATH),
            "sources": source_hashes,
            "all_passed": True,
        },
    )
    cost.atomic_write_json(
        PREFLIGHT_DIR / "case_and_config_parity.json",
        {
            "created_at": now_iso(),
            "cross_model_case_parity": parity_rows,
            "controlled_config_delta": config_audit,
            "prompt_and_schema_lock": frozen["implementation_lock"],
            "case_model_prompt_schema_parity_passed": True,
        },
    )
    cost.atomic_write_json(
        PREFLIGHT_DIR / "execution_plan.json",
        {
            "created_at": now_iso(),
            "protocol_version": frozen["protocol_version"],
            "fallback_manifest_sha256": frozen["selection"]["source_manifest_sha256"],
            "selection_rule": fallback["selection_rule"],
            "selection_blind_to_results": True,
            "selected_slots": list(EXPECTED_SELECTED_SLOTS),
            "execution_order_sha256": canonical_hash(fallback["execution_order"]),
            "planned_new_paid_cells": 16,
            "cells": execution,
        },
    )
    cost.atomic_write_json(PREFLIGHT_DIR / "nominal_reuse_readiness.json", nominal)
    cost.atomic_write_json(PREFLIGHT_DIR / "parent_cost_terminal.json", terminal)
    cost.atomic_write_json(
        PREFLIGHT_DIR / "pricing_and_budget_projection.json",
        {
            "pricing": pricing,
            "projection": projection,
            "launch_budget": budget,
            "accounting_provenance": accounting,
        },
    )
    cost.atomic_write_json(PREFLIGHT_DIR / "execution_state.json", state)
    gate = {
        "created_at": now_iso(),
        "command": command,
        "protocol_version": frozen["protocol_version"],
        "protocol_sha256": file_hash(PROTOCOL_PATH),
        "runner_sha256": file_hash(Path(__file__).resolve()),
        "output_directory_name": RUN_DIR.name,
        "source_hashes_passed": True,
        "manifest_and_execution_order_passed": True,
        "pricing_passed": True,
        "case_identity_and_cross_model_parity_passed": True,
        "controlled_config_delta_passed": True,
        "prompt_schema_implementation_lock_passed": True,
        "parent_cost_terminal_72_of_72": terminal["terminal_72_of_72"],
        "nominal_reuse_ready_cells": nominal["ready_cells"],
        "nominal_reuse_all_eight_ready": nominal["all_eight_ready"],
        "local_result_state": {key: state[key] for key in ("planned", "attempted", "valid", "invalid", "missing", "next_order")},
        "budget_gate": budget,
        "accounting_provenance": accounting,
        "intrinsic_ready": intrinsic_ready,
        "ready_for_paid_run": ready_for_paid_run,
        "already_complete": already_complete,
        "offline_command_made_model_or_xhub_calls": False,
        "blocking_reasons": [
            reason
            for condition, reason in (
                (terminal["terminal_72_of_72"], "parent cost run is not terminal 72/72"),
                (nominal["all_eight_ready"], "not all eight frozen nominal cells are ready"),
                (budget["passed"], "fresh launch budget arguments are absent or insufficient"),
                (
                    accounting["authoritative_for_paid_launch"],
                    "accounting context is absent, synthetic, or not authoritative for paid launch",
                ),
                (state["missing"] > 0 or already_complete, "local execution state is inconsistent"),
            )
            if not condition
        ],
    }
    cost.atomic_write_json(PREFLIGHT_DIR / "gate.json", gate)
    if command == "dry-run":
        cost.atomic_write_json(RUN_DIR / "dry_run.json", gate)
    if command in {"preflight", "preflight_test", "dry-run", "report"}:
        state_name = "offline_dry_run_complete" if command == "dry-run" else "offline_preflight_complete"
        write_status(state_name, {"gate": gate})
    return {
        "frozen": frozen,
        "fallback": fallback,
        "plans": plans,
        "graphs": graphs,
        "execution": execution,
        "state": state,
        "projection": projection,
        "budget": budget,
        "accounting": accounting,
        "nominal": nominal,
        "terminal": terminal,
        "gate": gate,
    }


async def run_prior_sa_cell(
    *,
    cell: dict[str, Any],
    case: dict[str, Any],
    graph: Any,
    scc: Any,
    injected_id: str,
    injection_metadata: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    model = str(cell["model"])
    args = make_args(model, output_dir)
    llm = None
    started_at = time.time()
    try:
        llm = cost.make_llm(args, output_dir, case, "sa-mcgs")
        result = await cost.battle.run_sa_mcgs(
            llm,
            model,
            case["domain"],
            graph,
            scc,
            effective_mcgs_config(model, float(cell["relation_prior_weight"])),
        )
        result.update(
            {
                "inject_mode": True,
                "injected_node": injected_id,
                "inject_type": cost.battle.DOMAIN_INJECT_TYPE.get(case["domain"]),
                "inject_profile": "memory_stress",
                "cycle_source": "real_long",
            }
        )
        result.update(injection_metadata)
        cost.battle.add_rank_metrics(result, injected_id)
        cost.battle.add_structural_rank_metrics(result, injection_metadata)
        evidence_nodes = injection_metadata.get("injected_evidence_nodes", [injected_id])
        risk_nodes = injection_metadata.get("injected_risk_nodes")
        affected_nodes = injection_metadata.get("injected_affected_nodes")
        result.update(
            cost.battle.build_risk_subgraph_summary(
                graph, scc, result, injected_id, evidence_nodes, risk_nodes, affected_nodes
            )
        )
        result.update(
            cost.battle.build_local_declared_subgraph_summary(
                scc, result, evidence_nodes, risk_nodes, affected_nodes
            )
        )
        result.update(
            cost.battle.build_core_evidence_subgraph_summary(
                scc, result, evidence_nodes, risk_nodes, affected_nodes
            )
        )
        result.update(
            cost.battle.build_trace_convergence_summary(
                scc, result, evidence_nodes, risk_nodes, affected_nodes
            )
        )
        result = cost.attach_common_audit(
            result,
            args=args,
            case=case,
            method="sa-mcgs",
            llm=llm,
            started_at=started_at,
        )
    except Exception as exc:  # A first attempt is terminal even when invalid.
        payload = {
            "method": "sa-mcgs",
            "model": model,
            "domain": case["domain"],
            "scc_id": case["scc_id"],
            "scc_size": case["scc_size"],
            "scc_clause_ids": list(scc.clause_ids),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        payload.update(injection_metadata)
        if llm is not None:
            result = cost.attach_common_audit(
                payload,
                args=args,
                case=case,
                method="sa-mcgs",
                llm=llm,
                started_at=started_at,
                error=str(exc),
            )
        else:
            result = {
                **payload,
                **cost.case_identity_audit_fields(case),
                "case_id": case["case_id"],
                "case_order": case["case_order"],
                "audit_started_at": started_at,
                "audit_completed_at": time.time(),
                "audit_started_at_iso": time.strftime(
                    "%Y-%m-%dT%H:%M:%S%z", time.localtime(started_at)
                ),
                "audit_completed_at_iso": now_iso(),
                "case_concurrency": 1,
                "internal_concurrency": 1,
                "cost_audit_budget": 60,
                "cost_audit_method": "sa-mcgs",
                "cost_audit_error": str(exc),
                "llm_usage_summary": {
                    "recorded_api_calls": 0,
                    "successful_api_calls": 0,
                    "failed_api_calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "api_runtime_sec_sum": 0.0,
                },
            }
    finally:
        if llm is not None:
            await llm.close()
    attach_protocol_fields(result, cell=cell, case=case)
    return result


async def execute_paid_run(args: argparse.Namespace) -> None:
    if not args.execute_paid_cells:
        raise ProtocolError("Paid execution requires the explicit --execute-paid-cells flag")
    if args.max_new_cells is not None and args.max_new_cells < 0:
        raise ProtocolError("--max-new-cells must be nonnegative")
    preflight = perform_preflight(
        authorization_usd=args.global_authorization_usd,
        authorization_remaining_usd=args.global_authorization_remaining_usd,
        closeout_reserve_usd=args.closeout_reserve_usd,
        accounting_context_kind=args.accounting_context_kind,
        fresh_xhub_balance_usd=args.fresh_xhub_balance_usd,
        fresh_balance_captured_at=args.fresh_balance_captured_at,
        fresh_balance_snapshot=args.fresh_balance_snapshot,
        fresh_balance_snapshot_sha256=args.fresh_balance_snapshot_sha256,
        upstream_ledgers=args.upstream_ledger,
        command="run_gate",
    )
    if preflight["gate"]["already_complete"]:
        make_report()
        write_status("complete", {"gate": preflight["gate"]})
        return
    if not preflight["gate"]["ready_for_paid_run"]:
        raise ProtocolError(
            "Paid launch gate is closed: " + "; ".join(preflight["gate"]["blocking_reasons"])
        )
    key_env = preflight["frozen"]["locked_runtime"]["api_key_env"]
    if not os.environ.get(key_env):
        raise ProtocolError(f"Required API key environment variable is absent: {key_env}")

    invocation_id = f"fallback-{time.strftime('%Y%m%dT%H%M%S', time.localtime())}-{os.getpid()}"
    protocol_sha = file_hash(PROTOCOL_PATH)
    invocation_spend = 0.0
    receipt = {
        "receipt_version": "prior_fallback_launch_receipt_v1",
        "created_at": now_iso(),
        "invocation_id": invocation_id,
        "protocol_version": EXPECTED_PROTOCOL_VERSION,
        "protocol_sha256": protocol_sha,
        "runner_sha256": file_hash(Path(__file__).resolve()),
        "fallback_manifest_sha256": preflight["frozen"]["selection"]["source_manifest_sha256"],
        "parent_protocol_sha256": preflight["frozen"]["parent"]["frozen_protocol_sha256"],
        "global_authorization_usd": args.global_authorization_usd,
        "global_authorization_remaining_usd_asserted_at_invocation": args.global_authorization_remaining_usd,
        "global_authorization_remaining_usd_derived_at_invocation": preflight["accounting"][
            "derived_authorization_remaining_usd"
        ],
        "closeout_reserve_usd": args.closeout_reserve_usd,
        "fresh_balance_snapshot": preflight["accounting"]["balance_snapshot"],
        "accounting_provenance": preflight["accounting"],
        "projected_missing_usd": preflight["projection"]["projected_missing_usd"],
        "required_including_closeout_usd": preflight["budget"][
            "required_including_closeout_usd"
        ],
        "headroom_after_projection_and_closeout_usd": preflight["budget"][
            "headroom_after_projection_and_closeout_usd"
        ],
        "parent_cost_terminal_72_of_72": preflight["terminal"]["terminal_72_of_72"],
        "nominal_reuse_ready_cells": preflight["nominal"]["ready_cells"],
        "nominal_reuse_index": str(PREFLIGHT_DIR / "nominal_reuse_readiness.json"),
        "nominal_reuse_index_sha256": file_hash(
            PREFLIGHT_DIR / "nominal_reuse_readiness.json"
        ),
        "next_execution_order": preflight["state"]["next_order"],
        "max_new_cells": args.max_new_cells,
        "paid_execution_explicitly_authorized": True,
    }
    receipt_path = RUN_DIR / "launch_receipts" / f"{invocation_id}.json"
    if receipt_path.exists():
        raise ProtocolError(f"Launch receipt collision: {receipt_path}")
    cost.atomic_write_json(receipt_path, receipt)
    append_ledger(
        {
            "event": "run_invocation_start",
            "recorded_at": now_iso(),
            "invocation_id": invocation_id,
            "protocol_sha256": protocol_sha,
            "runner_sha256": file_hash(Path(__file__).resolve()),
            "global_authorization_usd": args.global_authorization_usd,
            "global_authorization_remaining_usd_asserted_at_invocation": args.global_authorization_remaining_usd,
            "global_authorization_remaining_usd_derived_at_invocation": preflight["accounting"][
                "derived_authorization_remaining_usd"
            ],
            "closeout_reserve_usd": args.closeout_reserve_usd,
            "accounting_provenance": preflight["accounting"],
            "launch_receipt": str(receipt_path),
            "launch_receipt_sha256": file_hash(receipt_path),
            "max_new_cells": args.max_new_cells,
            "paid_execution_explicitly_authorized": True,
        }
    )
    new_cells = 0
    for cell in preflight["execution"]:
        path = Path(cell["result_path"])
        if path.exists():
            continue
        if args.max_new_cells is not None and new_cells >= args.max_new_cells:
            write_status(
                "paused_by_max_new_cells",
                {"invocation_id": invocation_id, "new_cells_this_invocation": new_cells},
            )
            make_report()
            return

        # Revalidate every frozen input and the complete remaining-tail reserve
        # before constructing the next LLM client.
        fresh = perform_preflight(
            authorization_usd=args.global_authorization_usd,
            authorization_remaining_usd=None,
            closeout_reserve_usd=args.closeout_reserve_usd,
            accounting_context_kind=args.accounting_context_kind,
            fresh_xhub_balance_usd=args.fresh_xhub_balance_usd,
            fresh_balance_captured_at=args.fresh_balance_captured_at,
            fresh_balance_snapshot=args.fresh_balance_snapshot,
            fresh_balance_snapshot_sha256=args.fresh_balance_snapshot_sha256,
            upstream_ledgers=args.upstream_ledger,
            require_remaining_assertion=False,
            snapshot_validation_mode="same_invocation_per_cell",
            expected_launch_snapshot_sha256=receipt["fresh_balance_snapshot"]["sha256"],
            command="per_cell_gate",
        )
        if not fresh["gate"]["ready_for_paid_run"]:
            raise BudgetStop(
                f"Per-cell gate closed before order {cell['order']}: "
                + "; ".join(fresh["gate"]["blocking_reasons"])
            )
        if file_hash(PROTOCOL_PATH) != protocol_sha:
            raise ProtocolError("Fallback protocol changed during paid execution")
        expected_next = fresh["state"]["next_order"]
        if int(cell["order"]) != int(expected_next):
            raise ProtocolError(
                f"Execution-order drift: about to run {cell['order']}, expected {expected_next}"
            )
        effective_remaining = float(
            fresh["budget"]["derived_global_authorization_remaining_usd"]
        )

        model = str(cell["model"])
        case = next(
            row for row in fresh["plans"][model] if int(row["case_order"]) == int(cell["slot"])
        )
        graphs = fresh["graphs"][model]
        graph, scc, injected_id, injection_metadata = cost.prepare_injected_case(case, graphs)
        output_dir = RESULTS_DIR / str(cell["profile"]) / cost.safe_token(model)
        append_ledger(
            {
                "event": "cell_start",
                "recorded_at": now_iso(),
                "invocation_id": invocation_id,
                "order": int(cell["order"]),
                "model": model,
                "profile": cell["profile"],
                "slot": int(cell["slot"]),
                "case_id": case["case_id"],
                "case_uid": case["case_uid"],
                "result_path": str(path),
                "effective_global_authorization_remaining_usd": effective_remaining,
                "tail_projection_before_cell_usd": fresh["projection"]["projected_missing_usd"],
                "closeout_reserve_usd": args.closeout_reserve_usd,
            }
        )
        with cost.InjectedGroundTruth(case["domain"], injected_id):
            result = await run_prior_sa_cell(
                cell=cell,
                case=case,
                graph=graph,
                scc=scc,
                injected_id=injected_id,
                injection_metadata=injection_metadata,
                output_dir=output_dir,
            )
        validate_local_result(
            result,
            cell=cell,
            case=case,
            graph=graphs[case["domain"]],
        )
        cost.atomic_write_json(path, result)
        usage = result.get("llm_usage_summary") or {}
        amount = estimate_usd(model, usage, fresh["frozen"])
        invocation_spend += amount
        append_ledger(
            {
                "event": "cell_complete",
                "recorded_at": now_iso(),
                "invocation_id": invocation_id,
                "order": int(cell["order"]),
                "model": model,
                "profile": cell["profile"],
                "slot": int(cell["slot"]),
                "case_id": case["case_id"],
                "case_uid": case["case_uid"],
                "valid": not bool(result.get("cost_audit_error")),
                "error_type": result.get("error_type"),
                "usage": usage,
                "estimated_usd": amount,
                "result_path": str(path),
                "result_sha256": file_hash(path),
                "invalid_is_terminal": True,
                "automatic_retry_permitted": False,
            }
        )
        new_cells += 1
        write_status(
            "running",
            {
                "invocation_id": invocation_id,
                "last_completed_order": cell["order"],
                "new_cells_this_invocation": new_cells,
                "estimated_usd_this_invocation": invocation_spend,
            },
        )

    make_report()
    write_status(
        "complete",
        {
            "invocation_id": invocation_id,
            "new_cells_this_invocation": new_cells,
            "estimated_usd_this_invocation": invocation_spend,
        },
    )


def metric_value(result: dict[str, Any] | None, metric: str) -> Any:
    if result is None or result.get("cost_audit_error"):
        return None
    return cost.metric_value(result, "SA-MCGS", metric)


def result_for_profile(
    model: str,
    profile_name: str,
    case: dict[str, Any],
    frozen: dict[str, Any],
    execution_by_key: dict[tuple[str, int, str], dict[str, Any]],
) -> tuple[dict[str, Any] | None, Path]:
    if profile_name == "nominal":
        path = parent_nominal_path(model, case, frozen)
    else:
        cell = execution_by_key[(model, int(case["case_order"]), profile_name)]
        path = Path(cell["result_path"])
    return (load_json(path), path) if path.exists() else (None, path)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    headers = list(rows[0])
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        cells = []
        for header in headers:
            value = row.get(header)
            if isinstance(value, float):
                cells.append(f"{value:.4f}")
            elif value is None:
                cells.append("NA")
            else:
                cells.append(str(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def make_report() -> None:
    preflight = perform_preflight(command="report")
    frozen = preflight["frozen"]
    execution_by_key = {
        (str(row["model"]), int(row["slot"]), str(row["profile"])): row
        for row in preflight["execution"]
    }
    cell_rows = []
    aggregate_rows = []
    paired_rows = []
    for model in MODELS:
        for profile_name in ALL_PROFILES:
            profile_cells = []
            for case in preflight["plans"][model]:
                result, path = result_for_profile(
                    model, profile_name, case, frozen, execution_by_key
                )
                usage = (result or {}).get("llm_usage_summary") or {}
                valid = result is not None and not result.get("cost_audit_error")
                row = {
                    "model": model,
                    "profile": profile_name,
                    "slot": case["case_order"],
                    "case_id": case["case_id"],
                    "case_uid": case["case_uid"],
                    "attempted": result is not None,
                    "valid": valid,
                    "invalid": result is not None and not valid,
                    "missing": result is None,
                    "root_at_3_strict": metric_value(result, "root@3") is True,
                    "risk_any_strict": metric_value(result, "risk_any") is True,
                    "risk_all_strict": metric_value(result, "risk_all") is True,
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "recorded_api_calls": usage.get("recorded_api_calls"),
                    "estimated_usd": estimate_usd(model, usage, frozen) if result else None,
                    "nominal_reused": profile_name == "nominal",
                    "result_path": str(path),
                    "result_sha256": file_hash(path) if path.exists() else None,
                }
                profile_cells.append(row)
                cell_rows.append(row)
            n = len(profile_cells)
            aggregate_rows.append(
                {
                    "Model": model,
                    "Profile": profile_name,
                    "Planned": n,
                    "Attempted": sum(row["attempted"] for row in profile_cells),
                    "Valid": sum(row["valid"] for row in profile_cells),
                    "Invalid": sum(row["invalid"] for row in profile_cells),
                    "Missing": sum(row["missing"] for row in profile_cells),
                    "Root@3 strict": sum(row["root_at_3_strict"] for row in profile_cells) / n,
                    "Risk-any strict": sum(row["risk_any_strict"] for row in profile_cells) / n,
                    "Risk-all strict": sum(row["risk_all_strict"] for row in profile_cells) / n,
                }
            )
        for profile_name in PROFILES:
            for metric in ("root@3", "risk_any", "risk_all"):
                improved = tied = worsened = comparable = strict_nominal = strict_varied = 0
                for case in preflight["plans"][model]:
                    nominal, _ = result_for_profile(
                        model, "nominal", case, frozen, execution_by_key
                    )
                    varied, _ = result_for_profile(
                        model, profile_name, case, frozen, execution_by_key
                    )
                    left = metric_value(nominal, metric)
                    right = metric_value(varied, metric)
                    strict_nominal += left is True
                    strict_varied += right is True
                    if isinstance(left, bool) and isinstance(right, bool):
                        comparable += 1
                        delta = int(right) - int(left)
                        improved += delta > 0
                        tied += delta == 0
                        worsened += delta < 0
                paired_rows.append(
                    {
                        "model": model,
                        "profile_vs_nominal": profile_name,
                        "metric": metric,
                        "planned_pairs": 4,
                        "valid_comparable_pairs": comparable,
                        "improved": improved,
                        "tied": tied,
                        "worsened": worsened,
                        "strict_nominal_rate": strict_nominal / 4,
                        "strict_profile_rate": strict_varied / 4,
                        "strict_rate_delta": (strict_varied - strict_nominal) / 4,
                    }
                )
    write_csv(RUN_DIR / "strict_prior_cells.csv", cell_rows)
    write_csv(RUN_DIR / "strict_prior_table.csv", aggregate_rows)
    write_csv(RUN_DIR / "paired_direction_table.csv", paired_rows)
    cost.atomic_write_json(
        RUN_DIR / "summary.json",
        {
            "created_at": now_iso(),
            "gate": preflight["gate"],
            "strict_table": aggregate_rows,
            "paired_directions": paired_rows,
            "new_paid_execution_state": preflight["state"],
        },
    )
    paid_costs = [
        float(row["estimated_usd"])
        for row in cell_rows
        if not row["nominal_reused"] and isinstance(row["estimated_usd"], (int, float))
    ]
    lines = [
        "# Relation-prior 冻结 fallback 报告",
        "",
        f"生成时间：{now_iso()}。输出隔离目录：`{EXPECTED_DIRECTORY}`。",
        "",
        "该 fallback 只使用结果盲选并预冻结的 slots 01/03/08/10。执行顺序严格来自 fallback manifest 的 16 cells；8 个 nominal cells 仅引用 parent cost 结果，不复制、不重跑。invalid 保留在每个 model/profile 的固定 4-case strict denominator 内，且不换 case、不自动重试。",
        "",
        "## 当前门禁",
        "",
        f"Parent cost 72/72：{preflight['terminal']['terminal_72_of_72']}；nominal parity：{preflight['nominal']['ready_cells']}/8；fallback 新 cells：attempted={preflight['state']['attempted']}、valid={preflight['state']['valid']}、invalid={preflight['state']['invalid']}、missing={preflight['state']['missing']}。",
        "",
        "## Strict table",
        "",
        markdown_table(aggregate_rows),
        "",
        "## 成本与审计",
        "",
        f"Fallback 新 cells 的 provider-token × 冻结 XHub list-rate 累计为 ${sum(paid_costs):.6f}。当前缺失尾部保守投影为 ${preflight['projection']['projected_missing_usd']:.6f}，另需启动参数传入且不少于 $10 的 closeout reserve。共享账户余额不用于本线归因。",
        "",
        "完整身份、配置、prompt/schema、价格、预算、nominal 引用与执行状态审计位于 `preflight/`；逐 cell append-only 账本为 `budget_ledger.jsonl`。",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def add_budget_args(parser: argparse.ArgumentParser, *, required: bool) -> None:
    parser.add_argument("--global-authorization-usd", type=float, required=required)
    parser.add_argument("--global-authorization-remaining-usd", type=float, required=required)
    parser.add_argument("--closeout-reserve-usd", type=float, required=required)
    parser.add_argument(
        "--accounting-context-kind",
        choices=("synthetic", "authoritative"),
        required=required,
        help="synthetic is dry-run only; paid launch requires authoritative",
    )
    parser.add_argument("--fresh-xhub-balance-usd", type=float, required=required)
    parser.add_argument(
        "--fresh-balance-captured-at",
        required=required,
        help="timestamp or immutable reference supplied by the coordinator",
    )
    parser.add_argument(
        "--fresh-balance-snapshot",
        required=required,
        help="coordinator-attested XHub balance snapshot JSON",
    )
    parser.add_argument(
        "--fresh-balance-snapshot-sha256",
        required=required,
        help="exact sha256:... digest of --fresh-balance-snapshot",
    )
    parser.add_argument(
        "--upstream-ledger",
        action="append",
        default=[],
        help="legacy compatibility only; every non-empty value is rejected because the exact three upstream sources are frozen",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight", help="offline frozen-input and parity audit")
    dry = subparsers.add_parser("dry-run", help="offline launch simulation; never calls XHub")
    add_budget_args(dry, required=True)
    run = subparsers.add_parser("run", help="execute the exact frozen paid sequence")
    add_budget_args(run, required=True)
    run.add_argument("--execute-paid-cells", action="store_true")
    run.add_argument("--max-new-cells", type=int, default=None)
    subparsers.add_parser("report", help="offline strict summary of existing artifacts")
    return parser.parse_args(argv)


async def async_main(args: argparse.Namespace) -> None:
    if args.command == "preflight":
        result = perform_preflight(command="preflight")
        print(json.dumps(result["gate"], ensure_ascii=False, indent=2))
    elif args.command == "dry-run":
        result = perform_preflight(
            authorization_usd=args.global_authorization_usd,
            authorization_remaining_usd=args.global_authorization_remaining_usd,
            closeout_reserve_usd=args.closeout_reserve_usd,
            accounting_context_kind=args.accounting_context_kind,
            fresh_xhub_balance_usd=args.fresh_xhub_balance_usd,
            fresh_balance_captured_at=args.fresh_balance_captured_at,
            fresh_balance_snapshot=args.fresh_balance_snapshot,
            fresh_balance_snapshot_sha256=args.fresh_balance_snapshot_sha256,
            upstream_ledgers=args.upstream_ledger,
            command="dry-run",
        )
        print(json.dumps(result["gate"], ensure_ascii=False, indent=2))
    elif args.command == "run":
        await execute_paid_run(args)
    elif args.command == "report":
        make_report()
        print(str(REPORT_PATH))
    else:
        raise AssertionError(args.command)


if __name__ == "__main__":
    asyncio.run(async_main(parse_args()))

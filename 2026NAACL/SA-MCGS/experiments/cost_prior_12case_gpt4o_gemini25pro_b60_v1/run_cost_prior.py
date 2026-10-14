#!/usr/bin/env python3
"""Frozen cost/reliability and relation-prior sensitivity runner.

The implementation deliberately reuses the stable-identity and method adapters
from ``emnlp2026_discussion.run_cost_audit_clean`` while replacing its legacy
sampling, budget-50 default, and valid-only aggregation.

Every paid cell is serial, resumable, and followed by an append-only accounting
record.  The account-balance snapshots are global diagnostics because the XHub
key can be used by other workers at the same time; local provider-observed token
usage is the attribution ledger for this experiment.
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
import shutil
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable


RUN_DIR = Path(__file__).resolve().parent
REPO_ROOT = RUN_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT))

from emnlp2026_discussion import run_cost_audit_clean as cost  # noqa: E402


PROTOCOL_PATH = RUN_DIR / "frozen_protocol.json"
MASTER_CASE_CSV = REPO_ROOT / "emnlp2026_discussion" / "case_composition.csv"
PREFLIGHT_DIR = RUN_DIR / "preflight"
COST_DIR = RUN_DIR / "cost"
PRIOR_DIR = RUN_DIR / "prior"
LEDGER_PATH = RUN_DIR / "budget_ledger.jsonl"
STATUS_PATH = RUN_DIR / "execution_status.json"
REPORT_PATH = RUN_DIR / "REPORT_ZH.md"
PRICING_SNAPSHOT_PATH = RUN_DIR / "xhub_pricing_snapshot.json"
MODELS = ("gpt-4o", "gemini-2.5-pro")
COST_METHODS = ("naive-single", "lea", "sa-mcgs")
PRIOR_PROFILES = ("minus20", "plus20")
XHUB_USAGE_URL = "https://api3.xhub.chat/api/usage/token/"
XHUB_STATUS_URL = "https://api3.xhub.chat/api/status"


class ProtocolError(RuntimeError):
    """Raised before paid calls when a frozen-protocol assertion fails."""


class BudgetStop(RuntimeError):
    """Raised when the next paid cell would cross the local USD guardrail."""


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


def protocol() -> dict[str, Any]:
    payload = load_json(PROTOCOL_PATH)
    if payload.get("protocol_version") != RUN_DIR.name:
        raise ProtocolError(
            f"Protocol version/directory mismatch: {payload.get('protocol_version')} != {RUN_DIR.name}"
        )
    return payload


def physical_scc_identity(case: dict[str, Any]) -> dict[str, Any]:
    identity = case["planned_case_identity"]
    return {
        "version": identity["version"],
        "domain": identity["domain"],
        "dataset_revision": identity["dataset_revision"],
        "ordered_clause_ids": identity["ordered_clause_ids"],
        "typed_internal_edges": identity["typed_internal_edges"],
        "normalized_clause_text_hashes": identity["normalized_clause_text_hashes"],
    }


def physical_scc_fingerprint(case: dict[str, Any]) -> str:
    return canonical_hash(physical_scc_identity(case))


def scale_bin(size: int) -> str:
    if size <= 12:
        return "small"
    if size <= 20:
        return "medium"
    return "large"


def load_master_rows() -> list[tuple[int, dict[str, str]]]:
    with MASTER_CASE_CSV.open(encoding="utf-8", newline="") as handle:
        return list(enumerate(csv.DictReader(handle), 1))


def build_model_plan(
    model: str,
    frozen: dict[str, Any],
    rows: list[tuple[int, dict[str, str]]],
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for selector in frozen["selection_policy"]["case_selectors"]:
        matches = [
            (order, row)
            for order, row in rows
            if row.get("model") == model
            and row.get("domain") == selector["domain"]
            and int(row.get("scc_size") or -1) == int(selector["scc_size"])
            and row.get("template") == selector["template"]
        ]
        if len(matches) != 1:
            raise ProtocolError(
                f"Expected one master row for {model}/{selector}; found {len(matches)}"
            )
        canonical_order, row = matches[0]
        slot = int(selector["slot"])
        case_id = cost.safe_token(
            f"{slot:02d}_{model}_{row['domain']}{row['scc_size']}_{row['template']}"
        )
        plan.append(
            {
                "case_order": slot,
                "case_slot": slot,
                "case_id": case_id,
                "canonical_case_order": canonical_order,
                "canonical_case_id": cost.safe_token(
                    f"{canonical_order:03d}_{model}_{row['domain']}{row['scc_size']}_"
                    f"{row['scc_id']}_{row['template']}"
                ),
                "model": model,
                "domain": row["domain"],
                "scc_id": row["scc_id"],
                "scc_size": int(row["scc_size"]),
                "template": row["template"],
                "scale": selector["scale"],
                "source_result_file": row.get("result_file"),
                "old_llm_calls": int(float(row.get("llm_calls") or 0)),
                "old_time_sec": float(row.get("time") or 0.0),
                "selection_basis": "frozen domain/size/template selector; outcome-blind",
            }
        )
    if [case["case_order"] for case in plan] != list(range(1, 13)):
        raise ProtocolError("Frozen case slots must be exactly 1..12")
    return plan


def persist_plan(model: str, plan: list[dict[str, Any]]) -> None:
    model_dir = PREFLIGHT_DIR / "plans" / cost.safe_token(model)
    cost.persist_case_plan(model_dir, plan)


def validate_protocol_counts(frozen: dict[str, Any]) -> None:
    selectors = frozen["selection_policy"]["case_selectors"]
    if len(selectors) != 12:
        raise ProtocolError(f"Expected 12 selectors; found {len(selectors)}")
    for key, expected in (
        ("domain", frozen["selection_policy"]["domain_counts"]),
        ("template", frozen["selection_policy"]["template_counts"]),
        ("scale", frozen["selection_policy"]["scale_counts"]),
    ):
        actual = Counter(str(row[key]) for row in selectors)
        if dict(actual) != expected:
            raise ProtocolError(f"Frozen {key} counts changed: {dict(actual)} != {expected}")


def run_preflight() -> dict[str, Any]:
    frozen = protocol()
    validate_protocol_counts(frozen)
    rows = load_master_rows()
    plans: dict[str, list[dict[str, Any]]] = {}
    graph_cache: dict[str, dict[str, Any]] = {}

    for model in MODELS:
        plan = build_model_plan(model, frozen, rows)
        graphs = cost.load_graphs(plan)
        cost.validate_case_plan(plan, graphs)
        for case in plan:
            injection = case["planned_injection_identity"]
            if injection.get("profile_version") != frozen["locked_runtime"]["inject_profile_version"]:
                raise ProtocolError(
                    f"Wrong injection profile for {case['case_id']}: {injection.get('profile_version')}"
                )
            if injection.get("profile") != frozen["locked_runtime"]["inject_profile"]:
                raise ProtocolError(f"Wrong injection mode for {case['case_id']}")
            if injection.get("conflict_severity") != frozen["locked_runtime"]["severity"]:
                raise ProtocolError(f"Wrong severity for {case['case_id']}")
            if scale_bin(int(case["scc_size"])) != case["scale"]:
                raise ProtocolError(f"Scale mismatch for {case['case_id']}")
            case["physical_scc_fingerprint"] = physical_scc_fingerprint(case)
        persist_plan(model, plan)
        plans[model] = plan
        graph_cache[model] = graphs

    parity_rows: list[dict[str, Any]] = []
    physical_ids: list[str] = []
    for slot in range(1, 13):
        left = plans[MODELS[0]][slot - 1]
        right = plans[MODELS[1]][slot - 1]
        fields = ("domain", "scc_size", "template", "scale")
        if any(left[field] != right[field] for field in fields):
            raise ProtocolError(f"Cross-model selector mismatch at slot {slot}")
        if left["physical_scc_fingerprint"] != right["physical_scc_fingerprint"]:
            raise ProtocolError(f"Cross-model physical-SCC mismatch at slot {slot}")
        if left["planned_scc_fingerprint"] != right["planned_scc_fingerprint"]:
            raise ProtocolError(f"Cross-model injection identity mismatch at slot {slot}")
        physical_ids.append(left["physical_scc_fingerprint"])
        parity_rows.append(
            {
                "slot": slot,
                "domain": left["domain"],
                "scc_size": left["scc_size"],
                "scale": left["scale"],
                "template": left["template"],
                "physical_scc_fingerprint": left["physical_scc_fingerprint"],
                "injected_case_fingerprint": left["planned_scc_fingerprint"],
                "case_uid": left["case_uid"],
                "gpt_source_result_sha256": left["source_result_sha256"],
                "gemini_source_result_sha256": right["source_result_sha256"],
            }
        )
    if len(set(physical_ids)) != 12:
        duplicates = [item for item, count in Counter(physical_ids).items() if count > 1]
        raise ProtocolError(f"Frozen subset is not 12 unique physical SCCs: {duplicates}")

    preflight = {
        "protocol_version": frozen["protocol_version"],
        "protocol_sha256": file_hash(PROTOCOL_PATH),
        "validated_at": now_iso(),
        "master_case_csv": str(MASTER_CASE_CSV),
        "master_case_csv_sha256": file_hash(MASTER_CASE_CSV),
        "models": list(MODELS),
        "cases_per_model": 12,
        "unique_physical_sccs": len(set(physical_ids)),
        "cross_model_physical_parity": True,
        "cross_model_injection_parity": True,
        "profile_version": frozen["locked_runtime"]["inject_profile_version"],
        "domain_counts": dict(Counter(row["domain"] for row in parity_rows)),
        "scale_counts": dict(Counter(row["scale"] for row in parity_rows)),
        "template_counts": dict(Counter(row["template"] for row in parity_rows)),
        "cases": parity_rows,
    }
    PREFLIGHT_DIR.mkdir(parents=True, exist_ok=True)
    cost.atomic_write_json(PREFLIGHT_DIR / "case_identity_preflight.json", preflight)
    write_status("preflight_complete", extra={"preflight": preflight})
    return preflight


def load_validated_plans() -> dict[str, list[dict[str, Any]]]:
    preflight_path = PREFLIGHT_DIR / "case_identity_preflight.json"
    if not preflight_path.exists():
        run_preflight()
    preflight = load_json(preflight_path)
    if preflight.get("protocol_sha256") != file_hash(PROTOCOL_PATH):
        raise ProtocolError("Frozen protocol changed after preflight")
    plans = {}
    for model in MODELS:
        path = PREFLIGHT_DIR / "plans" / cost.safe_token(model) / "case_plan.json"
        plan = load_json(path)
        graphs = cost.load_graphs(plan)
        cost.validate_case_plan(plan, graphs)
        for case in plan:
            if physical_scc_fingerprint(case) != case.get("physical_scc_fingerprint"):
                raise ProtocolError(f"Physical fingerprint drift: {case['case_id']}")
        plans[model] = plan
    return plans


def make_args(model: str, output_dir: Path) -> SimpleNamespace:
    runtime = protocol()["locked_runtime"]
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


def effective_mcgs_config(args: SimpleNamespace, relation_multiplier: float = 1.0) -> dict[str, Any]:
    cfg = cost.make_mcgs_config(args)
    evidence = cfg["alphago_mcgs"].setdefault("evidence", {})
    nominal = float(protocol()["prior_scope"]["nominal_value"])
    evidence["relation_prior_weight"] = nominal * relation_multiplier
    return cfg


def experiment_config_payload(
    model: str,
    method: str,
    *,
    relation_profile: str = "nominal",
) -> dict[str, Any]:
    frozen = protocol()
    multiplier = float(frozen["prior_scope"]["profiles"][relation_profile]["multiplier"])
    args = make_args(model, RUN_DIR)
    return {
        "protocol_version": frozen["protocol_version"],
        "model": model,
        "model_id": cost.MODEL_IDS.get(model, model),
        "method": method,
        "inject_profile": frozen["locked_runtime"]["inject_profile"],
        "inject_profile_version": frozen["locked_runtime"]["inject_profile_version"],
        "severity": frozen["locked_runtime"]["severity"],
        "compression_profile": frozen["locked_runtime"]["compression_profile"],
        "sa_mcgs_budget": frozen["locked_runtime"]["sa_mcgs_budget"] if method == "sa-mcgs" else None,
        "window_size": frozen["locked_runtime"]["window_size"],
        "case_concurrency": frozen["locked_runtime"]["case_concurrency"],
        "internal_concurrency": frozen["locked_runtime"]["internal_concurrency"],
        "relation_profile": relation_profile if method == "sa-mcgs" else None,
        "relation_prior_multiplier": multiplier if method == "sa-mcgs" else None,
        "effective_mcgs_config": effective_mcgs_config(args, multiplier) if method == "sa-mcgs" else None,
    }


def query_xhub_balance() -> dict[str, Any]:
    key = os.environ.get("XHUB_API_KEY", "")
    if not key:
        raise ProtocolError("XHUB_API_KEY is not available")
    usage_request = urllib.request.Request(
        XHUB_USAGE_URL,
        headers={"Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(usage_request, timeout=30) as response:
        usage = json.loads(response.read().decode("utf-8"))
    with urllib.request.urlopen(XHUB_STATUS_URL, timeout=30) as response:
        status = json.loads(response.read().decode("utf-8"))
    quota_per_unit = float(status["data"]["quota_per_unit"])
    available_units = float(usage["data"]["total_available"])
    return {
        "captured_at": now_iso(),
        "total_available_usd": available_units / quota_per_unit,
        "quota_per_unit": quota_per_unit,
    }


def safe_balance_snapshot() -> dict[str, Any]:
    try:
        return query_xhub_balance()
    except Exception as exc:
        return {
            "captured_at": now_iso(),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def iter_ledger() -> Iterable[dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return []
    records: list[dict[str, Any]] = []
    with LEDGER_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def append_ledger(record: dict[str, Any]) -> None:
    cost.append_jsonl(LEDGER_PATH, record)


def estimate_usd(model: str, usage: dict[str, Any]) -> float:
    rates = protocol()["budget"]["conservative_estimation_rates_usd_per_million_tokens"][model]
    prompt = float(usage.get("prompt_tokens") or 0)
    completion = float(usage.get("completion_tokens") or 0)
    return prompt / 1_000_000 * float(rates["input"]) + completion / 1_000_000 * float(rates["output"])


def local_estimated_spend() -> float:
    return sum(float(row.get("estimated_usd") or 0.0) for row in iter_ledger())


def xhub_list_estimate_from_record(row: dict[str, Any]) -> float:
    if isinstance(row.get("xhub_list_estimated_usd"), (int, float)):
        return float(row["xhub_list_estimated_usd"])
    # The frozen stress rates are exactly twice the captured XHub public ratios.
    return float(row.get("estimated_usd") or 0.0) / 2.0


def local_xhub_list_estimated_spend() -> float:
    return sum(xhub_list_estimate_from_record(row) for row in iter_ledger())


def reserve_for_next_cell(model: str, method: str) -> float:
    matching = [
        xhub_list_estimate_from_record(row)
        for row in iter_ledger()
        if row.get("model") == model and row.get("method") == method
    ]
    # XHub-list-price fallback reserves.  The frozen protocol's original
    # 0.5/1.5/2.5 values were 2x stress reserves and are display-only after the
    # budget-gate amendment recorded next to this runner.
    defaults = {"naive-single": 0.25, "lea": 0.75, "sa-mcgs": 1.25}
    if not matching:
        return defaults[method]
    return max(defaults[method], max(matching) * 1.5)


def assert_budget_for_next_cell(model: str, method: str) -> None:
    cap = float(protocol()["budget"]["hard_cap_usd"])
    spent = local_xhub_list_estimated_spend()
    reserve = reserve_for_next_cell(model, method)
    if spent + reserve > cap:
        raise BudgetStop(
            f"Budget guard: estimated spend ${spent:.6f} + next-cell reserve "
            f"${reserve:.6f} exceeds hard cap ${cap:.2f}"
        )


def result_path(base_dir: Path, model: str, case: dict[str, Any], method: str) -> Path:
    return (
        base_dir
        / cost.safe_token(model)
        / "results"
        / f"{case['case_id']}__{cost.safe_token(method)}.json"
    )


def archive_failed_result(path: Path) -> Path:
    history_dir = path.parents[1] / "attempt_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    archived = history_dir / f"{path.stem}__before_retry_{stamp}.json"
    if archived.exists():
        raise ProtocolError(f"Attempt-history collision: {archived}")
    shutil.copy2(path, archived)
    return archived


def completed_counts() -> dict[str, Any]:
    plans: dict[str, list[dict[str, Any]]] = {}
    for model in MODELS:
        plan_path = PREFLIGHT_DIR / "plans" / cost.safe_token(model) / "case_plan.json"
        if not plan_path.exists():
            return {
                "cost": {"attempted": 0, "valid": 0, "invalid": 0, "missing": 72},
                "prior_new": {"attempted": 0, "valid": 0, "invalid": 0, "missing": 48},
            }
        plans[model] = load_json(plan_path)
    cost_counts = Counter()
    prior_counts = Counter()
    for model, plan in plans.items():
        for case in plan:
            for method in COST_METHODS:
                path = result_path(COST_DIR, model, case, method)
                if path.exists():
                    payload = load_json(path)
                    cost_counts["attempted"] += 1
                    cost_counts["invalid" if payload.get("cost_audit_error") else "valid"] += 1
                else:
                    cost_counts["missing"] += 1
            for profile_name in PRIOR_PROFILES:
                path = result_path(PRIOR_DIR / "results" / profile_name, model, case, "sa-mcgs")
                if path.exists():
                    payload = load_json(path)
                    prior_counts["attempted"] += 1
                    prior_counts["invalid" if payload.get("cost_audit_error") else "valid"] += 1
                else:
                    prior_counts["missing"] += 1
    return {"cost": dict(cost_counts), "prior_new": dict(prior_counts)}


def write_status(state: str, *, extra: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {
        "protocol_version": RUN_DIR.name,
        "updated_at": now_iso(),
        "state": state,
        "local_xhub_list_estimated_spend_usd": local_xhub_list_estimated_spend(),
        "local_2x_stress_estimated_spend_usd": local_estimated_spend(),
        "hard_cap_usd": protocol()["budget"]["hard_cap_usd"],
    }
    try:
        payload["cells"] = completed_counts()
    except Exception as exc:
        payload["cells_error"] = f"{type(exc).__name__}: {exc}"
    if extra:
        payload.update(extra)
    cost.atomic_write_json(STATUS_PATH, payload)


def attach_protocol_fields(
    result: dict[str, Any],
    *,
    model: str,
    method: str,
    relation_profile: str = "nominal",
) -> None:
    config_payload = experiment_config_payload(
        model,
        method,
        relation_profile=relation_profile,
    )
    result.update(
        {
            "protocol_version": RUN_DIR.name,
            "protocol_sha256": file_hash(PROTOCOL_PATH),
            "physical_scc_fingerprint": canonical_hash(
                {
                    key: result["planned_case_identity"][key]
                    for key in (
                        "version",
                        "domain",
                        "dataset_revision",
                        "ordered_clause_ids",
                        "typed_internal_edges",
                        "normalized_clause_text_hashes",
                    )
                }
            ),
            "experiment_config": config_payload,
            "experiment_config_sha256": canonical_hash(config_payload),
            "strict_denominator_member": True,
            "relation_prior_profile": relation_profile if method == "sa-mcgs" else None,
        }
    )


def write_model_run_config(base_dir: Path, model: str, methods: Iterable[str]) -> None:
    payload = {
        "protocol_version": RUN_DIR.name,
        "protocol_sha256": file_hash(PROTOCOL_PATH),
        "created_or_updated_at": now_iso(),
        "model": model,
        "model_id": cost.MODEL_IDS.get(model, model),
        "methods": list(methods),
        "method_configs": {
            method: experiment_config_payload(model, method) for method in methods
        },
    }
    path = base_dir / cost.safe_token(model) / "run_config.json"
    cost.atomic_write_json(path, payload)


async def run_prior_sa_cell(
    args: SimpleNamespace,
    output_dir: Path,
    case: dict[str, Any],
    graph: Any,
    scc: Any,
    injected_id: str,
    injection_metadata: dict[str, Any],
    profile_name: str,
) -> dict[str, Any]:
    multiplier = float(protocol()["prior_scope"]["profiles"][profile_name]["multiplier"])
    llm = cost.make_llm(args, output_dir, case, "sa-mcgs")
    started_at = time.time()
    try:
        result = await cost.battle.run_sa_mcgs(
            llm,
            args.model,
            case["domain"],
            graph,
            scc,
            effective_mcgs_config(args, multiplier),
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
        result.update(
            cost.battle.build_risk_subgraph_summary(
                graph,
                scc,
                result,
                injected_id,
                evidence_nodes,
                injection_metadata.get("injected_risk_nodes"),
                injection_metadata.get("injected_affected_nodes"),
            )
        )
        result.update(
            cost.battle.build_local_declared_subgraph_summary(
                scc,
                result,
                evidence_nodes,
                injection_metadata.get("injected_risk_nodes"),
                injection_metadata.get("injected_affected_nodes"),
            )
        )
        result.update(
            cost.battle.build_core_evidence_subgraph_summary(
                scc,
                result,
                evidence_nodes,
                injection_metadata.get("injected_risk_nodes"),
                injection_metadata.get("injected_affected_nodes"),
            )
        )
        result.update(
            cost.battle.build_trace_convergence_summary(
                scc,
                result,
                evidence_nodes,
                injection_metadata.get("injected_risk_nodes"),
                injection_metadata.get("injected_affected_nodes"),
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
    except Exception as exc:
        import traceback

        payload = {
            "method": "sa-mcgs",
            "model": args.model,
            "domain": case["domain"],
            "scc_id": case["scc_id"],
            "scc_size": case["scc_size"],
            "scc_clause_ids": list(scc.clause_ids),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        payload.update(injection_metadata)
        result = cost.attach_common_audit(
            payload,
            args=args,
            case=case,
            method="sa-mcgs",
            llm=llm,
            started_at=started_at,
            error=str(exc),
        )
    finally:
        await llm.close()
    attach_protocol_fields(
        result,
        model=args.model,
        method="sa-mcgs",
        relation_profile=profile_name,
    )
    return result


async def execute_paid_cell(
    *,
    stage: str,
    model: str,
    method: str,
    case: dict[str, Any],
    output_dir: Path,
    graph: Any,
    scc: Any,
    injected_id: str,
    injection_metadata: dict[str, Any],
    relation_profile: str = "nominal",
) -> dict[str, Any]:
    assert_budget_for_next_cell(model, method)
    balance_before = safe_balance_snapshot()
    started = now_iso()
    args = make_args(model, output_dir)
    if stage == "cost":
        result = await cost.run_method(
            args,
            output_dir,
            case,
            method,
            graph,
            scc,
            injected_id,
            injection_metadata,
        )
        attach_protocol_fields(result, model=model, method=method)
    elif stage == "prior":
        result = await run_prior_sa_cell(
            args,
            output_dir,
            case,
            graph,
            scc,
            injected_id,
            injection_metadata,
            relation_profile,
        )
    else:
        raise ValueError(stage)
    balance_after = safe_balance_snapshot()
    usage = result.get("llm_usage_summary") or {}
    estimated = estimate_usd(model, usage)
    xhub_list_estimated = estimated / 2.0
    global_delta = None
    if "total_available_usd" in balance_before and "total_available_usd" in balance_after:
        global_delta = balance_before["total_available_usd"] - balance_after["total_available_usd"]
    append_ledger(
        {
            "recorded_at": now_iso(),
            "stage": stage,
            "relation_profile": relation_profile if stage == "prior" else None,
            "model": model,
            "method": method,
            "case_id": case["case_id"],
            "case_slot": case["case_order"],
            "case_uid": case["case_uid"],
            "physical_scc_fingerprint": case["physical_scc_fingerprint"],
            "started_at": started,
            "completed_at": now_iso(),
            "valid": not bool(result.get("cost_audit_error")),
            "error_type": result.get("error_type"),
            "usage": usage,
            "estimated_usd": estimated,
            "xhub_list_estimated_usd": xhub_list_estimated,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "global_balance_delta_usd_unattributed": global_delta,
            "result_sha256_before_write": canonical_hash(result),
            "accounting_note": "Global balance delta may include parallel workers; local usage is primary.",
        }
    )
    return result


async def run_cost(*, smoke_only: bool, retry_errors: bool, max_new_cells: int | None) -> None:
    if not (PREFLIGHT_DIR / "case_identity_preflight.json").exists():
        run_preflight()
    plans = load_validated_plans()
    smoke_slot = int(protocol()["cost_scope"]["smoke_case_slot"])
    new_cells = 0
    account_start_path = COST_DIR / "account_start.json"
    if not account_start_path.exists():
        cost.atomic_write_json(account_start_path, safe_balance_snapshot())

    for model in MODELS:
        plan = plans[model]
        graphs = cost.load_graphs(plan)
        write_model_run_config(COST_DIR, model, COST_METHODS)
        selected_plan = [case for case in plan if case["case_order"] == smoke_slot] if smoke_only else plan
        for case in selected_plan:
            graph, scc, injected_id, injection_metadata = cost.prepare_injected_case(case, graphs)
            with cost.InjectedGroundTruth(case["domain"], injected_id):
                for method in COST_METHODS:
                    path = result_path(COST_DIR, model, case, method)
                    if path.exists():
                        existing = load_json(path)
                        cost.validate_result_case_identity(existing, case, graphs[case["domain"]])
                        if not (retry_errors and existing.get("cost_audit_error")):
                            continue
                        archive_failed_result(path)
                    if max_new_cells is not None and new_cells >= max_new_cells:
                        summarize_cost(plans)
                        write_status("cost_paused_by_max_new_cells")
                        return
                    write_status(
                        "cost_running",
                        extra={
                            "current": {
                                "model": model,
                                "case_slot": case["case_order"],
                                "case_id": case["case_id"],
                                "method": method,
                            }
                        },
                    )
                    result = await execute_paid_cell(
                        stage="cost",
                        model=model,
                        method=method,
                        case=case,
                        output_dir=COST_DIR / cost.safe_token(model),
                        graph=graph,
                        scc=scc,
                        injected_id=injected_id,
                        injection_metadata=injection_metadata,
                    )
                    cost.atomic_write_json(path, result)
                    new_cells += 1
                    summarize_cost(plans)
                    write_status("cost_running")

    summarize_cost(plans)
    projection = project_remaining_spend(plans)
    cost.atomic_write_json(RUN_DIR / "spend_projection.json", projection)
    state = "cost_smoke_complete" if smoke_only else "cost_complete"
    write_status(state, extra={"spend_projection": projection})


def metric_for(result: dict[str, Any] | None, method: str, metric: str) -> Any:
    if not result or result.get("cost_audit_error"):
        return None
    label = cost.method_label(result)
    return cost.metric_value(result, label, metric)


def num(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def strict_rate(results: list[dict[str, Any] | None], method: str, metric: str) -> float:
    return sum(1 for result in results if metric_for(result, method, metric) is True) / len(results)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * p
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def cell_row(model: str, method: str, case: dict[str, Any], path: Path) -> dict[str, Any]:
    result = load_json(path) if path.exists() else None
    valid = bool(result is not None and not result.get("cost_audit_error"))
    usage = (result or {}).get("llm_usage_summary") or {}
    runtime = None
    if result:
        start = result.get("audit_started_at")
        end = result.get("audit_completed_at")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            runtime = max(0.0, float(end) - float(start))
    return {
        "model": model,
        "method": method,
        "case_slot": case["case_order"],
        "case_id": case["case_id"],
        "case_uid": case["case_uid"],
        "physical_scc_fingerprint": case["physical_scc_fingerprint"],
        "domain": case["domain"],
        "scc_size": case["scc_size"],
        "scale": case["scale"],
        "template": case["template"],
        "attempted": result is not None,
        "valid": valid,
        "invalid": bool(result is not None and not valid),
        "missing": result is None,
        "error_type": (result or {}).get("error_type"),
        "logical_llm_calls": (result or {}).get("llm_calls"),
        "recorded_api_calls": usage.get("recorded_api_calls"),
        "successful_api_calls": usage.get("successful_api_calls"),
        "failed_api_calls": usage.get("failed_api_calls"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "runtime_sec": runtime,
        "root_at_3_strict": metric_for(result, method, "root@3") is True,
        "risk_any_strict": metric_for(result, method, "risk_any") is True,
        "risk_all_strict": metric_for(result, method, "risk_all") is True,
        "compression_valid_only": metric_for(result, method, "compression"),
        "result_file": str(path),
        "result_sha256": file_hash(path) if path.exists() else None,
    }


def aggregate_rows(rows: list[dict[str, Any]], model: str, method: str) -> dict[str, Any]:
    planned = len(rows)
    valid_compression = [
        float(row["compression_valid_only"])
        for row in rows
        if isinstance(row.get("compression_valid_only"), (int, float))
    ]
    runtimes = [float(row["runtime_sec"]) for row in rows if isinstance(row.get("runtime_sec"), (int, float))]
    tokens = [float(row["total_tokens"]) for row in rows if isinstance(row.get("total_tokens"), (int, float))]
    return {
        "Model": model,
        "Method": protocol()["selection_policy"]["method_display_names"].get(method, method),
        "Planned": planned,
        "Attempted": sum(bool(row["attempted"]) for row in rows),
        "Valid": sum(bool(row["valid"]) for row in rows),
        "Invalid": sum(bool(row["invalid"]) for row in rows),
        "Missing": sum(bool(row["missing"]) for row in rows),
        "Invalid rate / planned": sum(bool(row["invalid"]) for row in rows) / planned,
        "Logical calls / planned": sum(num(row.get("logical_llm_calls")) for row in rows) / planned,
        "Recorded calls / planned": sum(num(row.get("recorded_api_calls")) for row in rows) / planned,
        "Input tok. / planned": sum(num(row.get("prompt_tokens")) for row in rows) / planned,
        "Output tok. / planned": sum(num(row.get("completion_tokens")) for row in rows) / planned,
        "Total tok. / planned": sum(num(row.get("total_tokens")) for row in rows) / planned,
        "Total tok. median attempted": statistics.median(tokens) if tokens else None,
        "Runtime / planned": sum(num(row.get("runtime_sec")) for row in rows) / planned,
        "Runtime median attempted": statistics.median(runtimes) if runtimes else None,
        "Root@3 strict": sum(bool(row["root_at_3_strict"]) for row in rows) / planned,
        "Risk-any strict": sum(bool(row["risk_any_strict"]) for row in rows) / planned,
        "Risk-all strict": sum(bool(row["risk_all_strict"]) for row in rows) / planned,
        "Compression mean valid-only": statistics.mean(valid_compression) if valid_compression else None,
        "Compression n": len(valid_compression),
    }


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
    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        cells = []
        for header in headers:
            value = row.get(header)
            if isinstance(value, float):
                if "rate" in header.lower() or "strict" in header.lower():
                    cells.append(f"{value:.3f}")
                elif "tok" in header.lower() or "calls" in header.lower():
                    cells.append(f"{value:.1f}")
                else:
                    cells.append(f"{value:.3f}")
            elif value is None:
                cells.append("NA")
            else:
                cells.append(str(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def summarize_cost(plans: dict[str, list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    plans = plans or load_validated_plans()
    cells: list[dict[str, Any]] = []
    table: list[dict[str, Any]] = []
    for model, plan in plans.items():
        for method in COST_METHODS:
            subset = [
                cell_row(model, method, case, result_path(COST_DIR, model, case, method))
                for case in plan
            ]
            cells.extend(subset)
            table.append(aggregate_rows(subset, model, method))
    for method in COST_METHODS:
        subset = [row for row in cells if row["method"] == method]
        table.append(aggregate_rows(subset, "Both models", method))
    write_csv(COST_DIR / "strict_method_cells.csv", cells)
    write_csv(COST_DIR / "strict_cost_table.csv", table)
    (COST_DIR / "strict_cost_table.md").write_text(markdown_table(table), encoding="utf-8")
    return table


def project_remaining_spend(plans: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    plans = plans or load_validated_plans()
    observed: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in iter_ledger():
        observed[(str(row.get("model")), str(row.get("method")))].append(xhub_list_estimate_from_record(row))
    projections = []
    cost_remaining_total = 0.0
    prior_remaining_total = 0.0
    for model in MODELS:
        for method in COST_METHODS:
            vals = observed.get((model, method), [])
            per_cell = max(vals) * 1.5 if vals else reserve_for_next_cell(model, method)
            remaining = sum(
                not result_path(COST_DIR, model, case, method).exists()
                for case in plans[model]
            )
            amount = per_cell * remaining
            cost_remaining_total += amount
            projections.append(
                {
                    "stage": "cost",
                    "model": model,
                    "method": method,
                    "remaining_cells": remaining,
                    "projected_usd_per_cell": per_cell,
                    "projected_remaining_usd": amount,
                }
            )
        sa_vals = observed.get((model, "sa-mcgs"), [])
        per_prior_cell = max(sa_vals) * 1.5 if sa_vals else reserve_for_next_cell(model, "sa-mcgs")
        prior_remaining = 0
        for profile_name in PRIOR_PROFILES:
            prior_remaining += sum(
                not result_path(PRIOR_DIR / "results" / profile_name, model, case, "sa-mcgs").exists()
                for case in plans[model]
            )
        amount = per_prior_cell * prior_remaining
        prior_remaining_total += amount
        projections.append(
            {
                "stage": "prior",
                "model": model,
                "method": "sa-mcgs",
                "remaining_cells": prior_remaining,
                "projected_usd_per_cell": per_prior_cell,
                "projected_remaining_usd": amount,
            }
        )
    spent = local_xhub_list_estimated_spend()
    projected_total = spent + cost_remaining_total + prior_remaining_total
    return {
        "created_at": now_iso(),
        "local_xhub_list_estimated_spend_usd": spent,
        "local_2x_stress_estimated_spend_usd": local_estimated_spend(),
        "projected_cost_remaining_usd": cost_remaining_total,
        "projected_cost_completion_usd": spent + cost_remaining_total,
        "projected_prior_remaining_usd": prior_remaining_total,
        "projected_full_protocol_usd": projected_total,
        "hard_cap_usd": protocol()["budget"]["hard_cap_usd"],
        "cost_within_hard_cap": spent + cost_remaining_total <= float(protocol()["budget"]["hard_cap_usd"]),
        "within_hard_cap": projected_total <= float(protocol()["budget"]["hard_cap_usd"]),
        "projection_policy": "1.5x maximum locally observed XHub-list estimate for each model/method; fallback uses conservative next-cell reserve",
        "components": projections,
    }


def verify_nominal_reuse(plans: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = []
    for model, plan in plans.items():
        expected_config = experiment_config_payload(model, "sa-mcgs", relation_profile="nominal")
        expected_hash = canonical_hash(expected_config)
        for case in plan:
            path = result_path(COST_DIR, model, case, "sa-mcgs")
            if not path.exists():
                raise ProtocolError(f"Nominal reuse source missing: {path}")
            result = load_json(path)
            cost.validate_result_case_identity(result, case, cost.load_graphs(plan)[case["domain"]])
            checks = {
                "model": result.get("model") == model,
                "case_uid": result.get("case_uid") == case["case_uid"],
                "physical_scc": result.get("physical_scc_fingerprint") == case["physical_scc_fingerprint"],
                "injection": result.get("actual_scc_fingerprint") == case["planned_scc_fingerprint"],
                "budget": result.get("cost_audit_budget") == protocol()["locked_runtime"]["sa_mcgs_budget"],
                "internal_concurrency": result.get("internal_concurrency") == 1,
                "config_hash": result.get("experiment_config_sha256") == expected_hash,
                "relation_profile": result.get("relation_prior_profile") == "nominal",
            }
            if not all(checks.values()):
                raise ProtocolError(f"Nominal parity failure for {path}: {checks}")
            index.append(
                {
                    "model": model,
                    "case_slot": case["case_order"],
                    "case_id": case["case_id"],
                    "case_uid": case["case_uid"],
                    "physical_scc_fingerprint": case["physical_scc_fingerprint"],
                    "source_result": str(path),
                    "source_result_sha256": file_hash(path),
                    "source_valid": not bool(result.get("cost_audit_error")),
                    "parity_checks": checks,
                }
            )
    if len(index) != 24:
        raise ProtocolError(f"Expected 24 nominal reuse cells; found {len(index)}")
    cost.atomic_write_json(
        PRIOR_DIR / "nominal_reuse_index.json",
        {
            "created_at": now_iso(),
            "policy": protocol()["prior_scope"]["nominal_reuse_policy"],
            "cells": index,
        },
    )
    return index


async def run_prior(*, retry_errors: bool, max_new_cells: int | None) -> None:
    if not (PREFLIGHT_DIR / "case_identity_preflight.json").exists():
        run_preflight()
    plans = load_validated_plans()
    cost_table = summarize_cost(plans)
    if any(int(row["Missing"]) for row in cost_table if row["Model"] != "Both models"):
        raise ProtocolError("Cost main table is incomplete; prior sensitivity must not start")
    verify_nominal_reuse(plans)
    projection = project_remaining_spend(plans)
    cost.atomic_write_json(RUN_DIR / "spend_projection.json", projection)
    if not projection["within_hard_cap"]:
        raise BudgetStop(
            f"Projected full protocol ${projection['projected_full_protocol_usd']:.3f} exceeds $85 cap"
        )

    new_cells = 0
    if not (PRIOR_DIR / "account_start.json").exists():
        cost.atomic_write_json(PRIOR_DIR / "account_start.json", safe_balance_snapshot())
    for profile_name in PRIOR_PROFILES:
        for model in MODELS:
            plan = plans[model]
            graphs = cost.load_graphs(plan)
            profile_base = PRIOR_DIR / "results" / profile_name
            write_model_run_config(profile_base, model, ("sa-mcgs",))
            profile_config = experiment_config_payload(
                model,
                "sa-mcgs",
                relation_profile=profile_name,
            )
            config_path = profile_base / cost.safe_token(model) / "prior_run_config.json"
            cost.atomic_write_json(config_path, profile_config)
            for case in plan:
                path = result_path(profile_base, model, case, "sa-mcgs")
                if path.exists():
                    existing = load_json(path)
                    cost.validate_result_case_identity(existing, case, graphs[case["domain"]])
                    if not (retry_errors and existing.get("cost_audit_error")):
                        continue
                    archive_failed_result(path)
                if max_new_cells is not None and new_cells >= max_new_cells:
                    summarize_prior(plans)
                    write_status("prior_paused_by_max_new_cells")
                    return
                graph, scc, injected_id, injection_metadata = cost.prepare_injected_case(case, graphs)
                with cost.InjectedGroundTruth(case["domain"], injected_id):
                    write_status(
                        "prior_running",
                        extra={
                            "current": {
                                "profile": profile_name,
                                "model": model,
                                "case_slot": case["case_order"],
                                "case_id": case["case_id"],
                            }
                        },
                    )
                    result = await execute_paid_cell(
                        stage="prior",
                        model=model,
                        method="sa-mcgs",
                        case=case,
                        output_dir=profile_base / cost.safe_token(model),
                        graph=graph,
                        scc=scc,
                        injected_id=injected_id,
                        injection_metadata=injection_metadata,
                        relation_profile=profile_name,
                    )
                    cost.atomic_write_json(path, result)
                    new_cells += 1
                    summarize_prior(plans)
                    write_status("prior_running")
    summarize_prior(plans)
    write_status("prior_complete")


def prior_result(
    profile_name: str,
    model: str,
    case: dict[str, Any],
) -> tuple[dict[str, Any] | None, Path]:
    if profile_name == "nominal":
        path = result_path(COST_DIR, model, case, "sa-mcgs")
    else:
        path = result_path(PRIOR_DIR / "results" / profile_name, model, case, "sa-mcgs")
    return (load_json(path), path) if path.exists() else (None, path)


def summarize_prior(plans: dict[str, list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    plans = plans or load_validated_plans()
    profiles = ("minus20", "nominal", "plus20")
    cell_rows: list[dict[str, Any]] = []
    table_rows: list[dict[str, Any]] = []
    for model, plan in plans.items():
        for profile_name in profiles:
            rows = []
            for case in plan:
                result, path = prior_result(profile_name, model, case)
                row = cell_row(model, "sa-mcgs", case, path)
                row["profile"] = profile_name
                row["relation_prior_value"] = protocol()["prior_scope"]["profiles"][profile_name]["value"]
                row["nominal_reused"] = profile_name == "nominal"
                rows.append(row)
            cell_rows.extend(rows)
            aggregated = aggregate_rows(rows, model, "sa-mcgs")
            aggregated.pop("Method", None)
            aggregated["Profile"] = profile_name
            aggregated["Relation prior"] = protocol()["prior_scope"]["profiles"][profile_name]["value"]
            table_rows.append(aggregated)

    paired_rows: list[dict[str, Any]] = []
    for model, plan in plans.items():
        nominal_by_slot = {
            case["case_order"]: prior_result("nominal", model, case)[0]
            for case in plan
        }
        for profile_name in ("minus20", "plus20"):
            for metric in ("root@3", "risk_any", "risk_all"):
                improved = tied = worsened = comparable = 0
                strict_nominal = strict_profile = 0
                for case in plan:
                    nominal = nominal_by_slot[case["case_order"]]
                    varied = prior_result(profile_name, model, case)[0]
                    nominal_value = metric_for(nominal, "sa-mcgs", metric)
                    varied_value = metric_for(varied, "sa-mcgs", metric)
                    strict_nominal += nominal_value is True
                    strict_profile += varied_value is True
                    if isinstance(nominal_value, bool) and isinstance(varied_value, bool):
                        comparable += 1
                        delta = int(varied_value) - int(nominal_value)
                        improved += delta > 0
                        tied += delta == 0
                        worsened += delta < 0
                paired_rows.append(
                    {
                        "model": model,
                        "profile_vs_nominal": profile_name,
                        "metric": metric,
                        "planned_pairs": len(plan),
                        "valid_comparable_pairs": comparable,
                        "improved": improved,
                        "tied": tied,
                        "worsened": worsened,
                        "nominal_strict_rate": strict_nominal / len(plan),
                        "profile_strict_rate": strict_profile / len(plan),
                        "strict_rate_delta": (strict_profile - strict_nominal) / len(plan),
                    }
                )

    write_csv(PRIOR_DIR / "strict_prior_cells.csv", cell_rows)
    write_csv(PRIOR_DIR / "strict_prior_table.csv", table_rows)
    write_csv(PRIOR_DIR / "paired_direction_table.csv", paired_rows)
    (PRIOR_DIR / "strict_prior_table.md").write_text(markdown_table(table_rows), encoding="utf-8")
    (PRIOR_DIR / "paired_direction_table.md").write_text(markdown_table(paired_rows), encoding="utf-8")
    return table_rows


def make_report() -> None:
    frozen = protocol()
    preflight = load_json(PREFLIGHT_DIR / "case_identity_preflight.json") if (PREFLIGHT_DIR / "case_identity_preflight.json").exists() else run_preflight()
    plans = load_validated_plans()
    cost_table = summarize_cost(plans)
    prior_table = summarize_prior(plans)
    projection = project_remaining_spend(plans)
    cost.atomic_write_json(RUN_DIR / "spend_projection.json", projection)
    snapshots = [
        row
        for row in iter_ledger()
        if isinstance((row.get("balance_after") or {}).get("total_available_usd"), (int, float))
    ]
    latest_balance = snapshots[-1]["balance_after"]["total_available_usd"] if snapshots else None
    account_start = None
    if (COST_DIR / "account_start.json").exists():
        account_start = load_json(COST_DIR / "account_start.json").get("total_available_usd")
    global_delta = account_start - latest_balance if account_start is not None and latest_balance is not None else None
    counts = completed_counts()

    lines = [
        "# Cost / reliability 与 relation-prior sensitivity 报告",
        "",
        f"生成时间：{now_iso()}。协议：`{frozen['protocol_version']}`。",
        "",
        "## 冻结设计与身份验收",
        "",
        f"已冻结并验证 {preflight['unique_physical_sccs']} 个不同 physical SCC；GPT-4o 与 Gemini 2.5 Pro 在每个 slot 的 source-SCC 与注入 fingerprint 完全一致。领域分布为 Debian/SEC/BGB/CUAD = 2/3/3/4，模板四类各 3 个，scale 为 small/medium/large = 6/3/3。Debian 在 locked benchmark 中只有 size 11 与 12 两个 eligible SCC，因此未通过重复注入伪造第三个独立 Debian SCC。",
        "",
        "主成本表固定使用 `memory_stress / structural_simple_v2 / critical / current(default)`，SA-MCGS rollout budget=60，window=4，case concurrency=1、internal concurrency=1。One-shot 指一次 full-SCC direct-subgraph prompt。所有二元性能指标均按每个模型/方法 12 个冻结 cases 的严格分母汇总；invalid 与 missing 计为失败，不插补、不静默删除。",
        "",
        "## Cost / reliability 主表",
        "",
        markdown_table(cost_table).rstrip(),
        "",
        "`Compression mean valid-only` 只在有定义的有效输出上计算，并同时给出 `Compression n`；它没有被伪装成 strict all-case 指标。Calls/tokens 的 `/ planned` 分母包含所有冻结 cells，已发生的 invalid 调用仍计入成本。Runtime 是串行低并发实测，不能直接当作高并发 wall-clock 预测。",
        "",
        "## Relation-prior sensitivity",
        "",
        "仅扰动 `alphago_mcgs.evidence.relation_prior_weight`：0.68 / 0.85 / 1.02，其他参数、case identity、模型与预算不变。Nominal 0.85 必须通过配置与身份 parity 后逐字节引用 cost 主表的 SA-MCGS 结果，不重复付费运行。",
        "",
        markdown_table(prior_table).rstrip(),
        "",
    ]
    paired_path = PRIOR_DIR / "paired_direction_table.md"
    if paired_path.exists():
        lines.extend(
            [
                "逐 case 方向统计见 `prior/paired_direction_table.csv`。只有两边均为有效布尔值的 cell 才进入 improved/tied/worsened；同时保留 strict 12-case rate delta，避免 invalid 被有效样本分母掩盖。",
                "",
            ]
        )
    lines.extend(
        [
            "## 预算与可审计性",
            "",
            f"本线 XHub 公共 ratio 列表价估算累计为 **${local_xhub_list_estimated_spend():.4f}**，2×压力估算为 **${local_estimated_spend():.4f}**，硬上限 **${frozen['budget']['hard_cap_usd']:.2f}**。价格快照与 pricing version 保存在 `xhub_pricing_snapshot.json`；账户余额差仍只作共享环境交叉核验。",
            f"本线开始后的账户全局余额变化为 **{f'${global_delta:.4f}' if global_delta is not None else 'NA'}**，最新过滤后余额快照为 **{f'${latest_balance:.4f}' if latest_balance is not None else 'NA'}**。由于同一 key 有并行实验，这一全局差值不能单独归因给本线。",
            "",
            f"Cost cells：{counts['cost']}。Prior 新付费 cells：{counts['prior_new']}；nominal 计划复用 24 cells。当前全协议投影：${projection['projected_full_protocol_usd']:.4f}（门禁内：{projection['within_hard_cap']}）。",
            "",
            "原始结果、call-level usage、append-only budget ledger、冻结 case plans、配置 hash、结果 hash 与 nominal reuse index 均保留在本目录。未运行 Flash/Qwen 附录，也未对结果不利的 case 做替换。",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("preflight", "cost-smoke", "cost", "prior", "report", "balance"),
    )
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--max-new-cells", type=int, default=None)
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    if args.command == "preflight":
        result = run_preflight()
        print(json.dumps({k: result[k] for k in ("unique_physical_sccs", "domain_counts", "scale_counts", "template_counts")}, ensure_ascii=False, indent=2))
    elif args.command == "balance":
        print(json.dumps(safe_balance_snapshot(), ensure_ascii=False, indent=2))
    elif args.command == "cost-smoke":
        await run_cost(smoke_only=True, retry_errors=args.retry_errors, max_new_cells=args.max_new_cells)
        make_report()
    elif args.command == "cost":
        await run_cost(smoke_only=False, retry_errors=args.retry_errors, max_new_cells=args.max_new_cells)
        make_report()
    elif args.command == "prior":
        await run_prior(retry_errors=args.retry_errors, max_new_cells=args.max_new_cells)
        make_report()
    elif args.command == "report":
        make_report()
    else:
        raise AssertionError(args.command)


if __name__ == "__main__":
    asyncio.run(async_main(parse_args()))

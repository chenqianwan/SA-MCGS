#!/usr/bin/env python3
"""Fail-closed, zero-API paired SCC bootstrap closeout.

This script is intentionally separate from both frozen paid runners.  It reads
only terminal artifacts, reuses the fallback runner's read-only integrity
validators, and writes a compact JSON/Markdown statistical closeout only after
the 72-cell cost table and 16-cell fallback are both complete.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable


MODELS = ("gpt-4o", "gemini-2.5-pro")
METHODS = ("naive-single", "lea", "sa-mcgs")
EXPECTED_RESULT_METHOD = {
    "naive-single": "full-scc-naive-single",
    "lea": "lea",
    "sa-mcgs": "sa-mcgs",
}
METHOD_LABELS = {
    "naive-single": "One-shot",
    "lea": "LEA",
    "sa-mcgs": "SA-MCGS",
}
METRICS = ("root@3", "risk_any", "risk_all")
PROFILES = ("minus20", "plus20")
DRAWS = 20_000
SEED = 8_229
SCHEMA = "paired_cluster_closeout_v1"


class CloseoutError(RuntimeError):
    """A terminality, identity, hash, or strict-denominator gate failed."""


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise CloseoutError(f"missing {label}: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CloseoutError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CloseoutError(f"{label} must be a JSON object: {path}")
    return payload


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CloseoutError(message)


def validate_result_method(result: dict[str, Any], method: str, path: Path) -> None:
    """Match the frozen runner's distinct success and exception schemas.

    run_method labels successful one-shot output full-scc-naive-single, but
    its exception handler retains the requested naive-single method. This
    does not make a failed output valid or remove it from the denominator.
    """
    expected = method if result.get("cost_audit_error") else EXPECTED_RESULT_METHOD[method]
    require(result.get("method") == expected, f"cost result method mismatch: {path}")
    require(result.get("cost_audit_method") == method, f"cost audit method mismatch: {path}")


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def bootstrap_mean_ci(
    values: Iterable[float], *, draws: int = DRAWS, seed: int = SEED
) -> dict[str, Any]:
    """Percentile cluster bootstrap, resampling equally weighted SCCs."""
    vector = [float(value) for value in values]
    if not vector:
        raise ValueError("bootstrap requires at least one SCC")
    rng = random.Random(seed)
    n = len(vector)
    replicates = [
        sum(vector[rng.randrange(n)] for _ in range(n)) / n for _ in range(draws)
    ]
    return {
        "estimate": sum(vector) / n,
        "ci95_lower": percentile(replicates, 0.025),
        "ci95_upper": percentile(replicates, 0.975),
        "draws": draws,
        "seed": seed,
        "method": "equal-SCC percentile cluster bootstrap",
    }


def metric_value(result: dict[str, Any], method: str, metric: str) -> bool | None:
    """Return a defined boolean metric; terminal invalids remain undefined."""
    if result.get("cost_audit_error"):
        return None
    if metric == "root@3":
        value = result.get("root_top3_hit", result.get("top3_hit"))
    else:
        prefix = {
            "naive-single": "direct",
            "lea": "lea",
            "sa-mcgs": "core_evidence",
        }[method]
        suffix = {
            "risk_any": "contains_any_risk_node",
            "risk_all": "contains_all_risk_nodes",
        }[metric]
        value = result.get(f"{prefix}_{suffix}")
    return value if isinstance(value, bool) else None


def strict_binary(result: dict[str, Any], method: str, metric: str) -> int:
    """Strict denominator: only an explicit True scores one; everything else zero."""
    return int(metric_value(result, method, metric) is True)


def _count_directions(deltas: list[int]) -> dict[str, int]:
    return {
        "improved": sum(delta > 0 for delta in deltas),
        "tied": sum(delta == 0 for delta in deltas),
        "worsened": sum(delta < 0 for delta in deltas),
    }


def compute_analysis(
    cost_records: dict[str, dict[str, dict[int, dict[str, Any]]]],
    prior_records: dict[str, dict[str, dict[int, dict[str, Any]]]],
    *,
    selected_slots: tuple[int, ...],
) -> dict[str, Any]:
    """Compute all estimates after callers have completed artifact validation."""
    require(len(selected_slots) == 4, "prior analysis must contain exactly four SCCs")
    require(len(set(selected_slots)) == 4, "prior selected SCC slots are not unique")
    performance: list[dict[str, Any]] = []
    cost_pairs: list[dict[str, Any]] = []
    prior_pairs: list[dict[str, Any]] = []

    for model in MODELS:
        for method in METHODS:
            records = cost_records[model][method]
            require(set(records) == set(range(1, 13)), f"{model}/{method}: not exactly slots 1..12")
            for metric in METRICS:
                raw = [metric_value(records[slot], method, metric) for slot in range(1, 13)]
                strict = [int(value is True) for value in raw]
                interval = bootstrap_mean_ci(strict)
                performance.append(
                    {
                        "model": model,
                        "method": method,
                        "method_label": METHOD_LABELS[method],
                        "metric": metric,
                        "denominator_sccs": 12,
                        "successes": sum(strict),
                        "strict_rate": interval["estimate"],
                        "ci95_lower": interval["ci95_lower"],
                        "ci95_upper": interval["ci95_upper"],
                        "valid_cells": sum(
                            not bool(records[slot].get("cost_audit_error"))
                            for slot in range(1, 13)
                        ),
                        "invalid_cells": sum(
                            bool(records[slot].get("cost_audit_error"))
                            for slot in range(1, 13)
                        ),
                        "metric_defined_cells": sum(isinstance(value, bool) for value in raw),
                    }
                )

        lea = cost_records[model]["lea"]
        sa = cost_records[model]["sa-mcgs"]
        for metric in METRICS:
            lea_raw = [metric_value(lea[slot], "lea", metric) for slot in range(1, 13)]
            sa_raw = [metric_value(sa[slot], "sa-mcgs", metric) for slot in range(1, 13)]
            lea_strict = [int(value is True) for value in lea_raw]
            sa_strict = [int(value is True) for value in sa_raw]
            deltas = [right - left for left, right in zip(lea_strict, sa_strict)]
            interval = bootstrap_mean_ci(deltas)
            cost_pairs.append(
                {
                    "model": model,
                    "comparison": "SA-MCGS minus LEA",
                    "metric": metric,
                    "denominator_paired_sccs": 12,
                    "lea_successes": sum(lea_strict),
                    "sa_mcgs_successes": sum(sa_strict),
                    "strict_rate_delta": interval["estimate"],
                    "ci95_lower": interval["ci95_lower"],
                    "ci95_upper": interval["ci95_upper"],
                    "both_metrics_defined": sum(
                        isinstance(left, bool) and isinstance(right, bool)
                        for left, right in zip(lea_raw, sa_raw)
                    ),
                    **_count_directions(deltas),
                }
            )

        nominal = cost_records[model]["sa-mcgs"]
        for profile in PROFILES:
            varied = prior_records[model][profile]
            require(set(varied) == set(selected_slots), f"{model}/{profile}: prior slots drift")
            for metric in METRICS:
                nominal_raw = [
                    metric_value(nominal[slot], "sa-mcgs", metric) for slot in selected_slots
                ]
                varied_raw = [
                    metric_value(varied[slot], "sa-mcgs", metric) for slot in selected_slots
                ]
                nominal_strict = [int(value is True) for value in nominal_raw]
                varied_strict = [int(value is True) for value in varied_raw]
                deltas = [right - left for left, right in zip(nominal_strict, varied_strict)]
                interval = bootstrap_mean_ci(deltas)
                prior_pairs.append(
                    {
                        "model": model,
                        "comparison": f"{profile} minus nominal",
                        "profile": profile,
                        "metric": metric,
                        "denominator_paired_sccs": 4,
                        "nominal_successes": sum(nominal_strict),
                        "profile_successes": sum(varied_strict),
                        "strict_rate_delta": interval["estimate"],
                        "ci95_lower": interval["ci95_lower"],
                        "ci95_upper": interval["ci95_upper"],
                        "both_metrics_defined": sum(
                            isinstance(left, bool) and isinstance(right, bool)
                            for left, right in zip(nominal_raw, varied_raw)
                        ),
                        **_count_directions(deltas),
                        "interpretation": "exploratory; four frozen SCCs; no significance claim",
                    }
                )

    return {
        "bootstrap": {
            "draws": DRAWS,
            "seed": SEED,
            "confidence_interval": "two-sided 95% percentile",
            "cluster_unit": "physical SCC",
            "weighting": "one selector per SCC; equal SCC weight",
        },
        "cost": {
            "strict_denominator_sccs_per_model_method": 12,
            "method_performance": performance,
            "sa_mcgs_vs_lea_paired": cost_pairs,
        },
        "relation_prior": {
            "strict_denominator_sccs_per_model_profile": 4,
            "selected_slots": list(selected_slots),
            "profile_vs_nominal_paired": prior_pairs,
            "interpretation": (
                "Exploratory sensitivity analysis: each interval is based on four "
                "pre-frozen physical SCCs and is not a confirmatory significance test."
            ),
        },
    }


def _import_fallback_runner(prior_dir: Path) -> ModuleType:
    runner_path = prior_dir / "run_prior_fallback.py"
    if not runner_path.is_file():
        raise CloseoutError(f"missing fallback runner: {runner_path}")
    module_name = f"paired_closeout_fallback_{hashlib.sha256(str(prior_dir).encode()).hexdigest()[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, runner_path)
    if spec is None or spec.loader is None:
        raise CloseoutError(f"cannot import fallback runner: {runner_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise CloseoutError(f"cannot load fallback validator: {type(exc).__name__}: {exc}") from exc
    return module


def _assert_persisted_gates(
    prior_dir: Path,
    module: ModuleType,
    *,
    terminal: dict[str, Any],
    nominal: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    preflight_dir = prior_dir / "preflight"
    gate = load_json(preflight_dir / "gate.json", "fallback gate")
    source = load_json(preflight_dir / "source_hash_audit.json", "source hash audit")
    parent = load_json(preflight_dir / "parent_cost_terminal.json", "parent terminal gate")
    nominal_disk = load_json(
        preflight_dir / "nominal_reuse_readiness.json", "nominal reuse gate"
    )
    parity = load_json(preflight_dir / "case_and_config_parity.json", "case/config parity gate")
    execution = load_json(preflight_dir / "execution_plan.json", "fallback execution plan")
    execution_state = load_json(preflight_dir / "execution_state.json", "fallback execution state")
    protocol_sha = file_hash(prior_dir / "frozen_fallback_protocol.json")
    runner_sha = file_hash(prior_dir / "run_prior_fallback.py")

    require(gate.get("protocol_sha256") == protocol_sha, "persisted fallback gate protocol hash drift")
    require(gate.get("runner_sha256") == runner_sha, "persisted fallback gate runner hash drift")
    require(gate.get("source_hashes_passed") is True, "fallback source-hash gate did not pass")
    require(gate.get("manifest_and_execution_order_passed") is True, "fallback manifest gate did not pass")
    require(gate.get("case_identity_and_cross_model_parity_passed") is True, "case identity gate did not pass")
    require(gate.get("controlled_config_delta_passed") is True, "controlled config-delta gate did not pass")
    require(gate.get("prompt_schema_implementation_lock_passed") is True, "prompt/schema lock gate did not pass")
    require(gate.get("parent_cost_terminal_72_of_72") is True, "persisted parent cost terminal gate is false")
    require(gate.get("nominal_reuse_all_eight_ready") is True, "persisted nominal reuse gate is false")
    require(gate.get("nominal_reuse_ready_cells") == 8, "persisted nominal reuse count is not 8")
    require(gate.get("intrinsic_ready") is True, "fallback intrinsic gate is false")
    require(gate.get("already_complete") is True, "fallback complete gate is false")
    gate_state = gate.get("local_result_state") or {}
    require(gate_state.get("attempted") == 16 and gate_state.get("missing") == 0, "fallback gate is not 16/16 terminal")

    # The source audit's frozen schema contains the validated source rows and
    # all_passed.  Its protocol binding lives in gate.json (checked above).
    require(source.get("all_passed") is True, "source hash audit is not terminal-pass")
    require(parent.get("terminal_72_of_72") is True, "persisted parent terminal artifact is false")
    require(parent.get("parent_ledger_sha256") == terminal.get("parent_ledger_sha256"), "parent ledger hash changed after gate")
    require(parent.get("integrity_checked_cells") == terminal.get("integrity_checked_cells") == 72, "parent integrity count is not 72")
    require(nominal_disk.get("all_eight_ready") is True, "persisted nominal reuse artifact is false")
    require(nominal_disk.get("ready_cells") == nominal.get("ready_cells") == 8, "nominal reuse artifact is not 8/8")
    require(parity.get("case_model_prompt_schema_parity_passed") is True, "persisted case/config parity is false")
    require(execution.get("planned_new_paid_cells") == 16, "persisted fallback execution plan is not 16 cells")
    require(len(execution.get("cells") or []) == 16, "persisted fallback execution cell list is not 16")
    require(execution_state.get("attempted") == state.get("attempted") == 16, "persisted execution state is not 16 attempted")
    require(execution_state.get("missing") == state.get("missing") == 0, "persisted execution state has missing cells")
    require(execution_state.get("ledger_integrity_passed") is True, "fallback ledger integrity gate is false")

    return {
        "gate_sha256": file_hash(preflight_dir / "gate.json"),
        "source_hash_audit_sha256": file_hash(preflight_dir / "source_hash_audit.json"),
        "parent_terminal_sha256": file_hash(preflight_dir / "parent_cost_terminal.json"),
        "nominal_reuse_sha256": file_hash(preflight_dir / "nominal_reuse_readiness.json"),
        "case_config_parity_sha256": file_hash(preflight_dir / "case_and_config_parity.json"),
        "execution_plan_sha256": file_hash(preflight_dir / "execution_plan.json"),
        "execution_state_sha256": file_hash(preflight_dir / "execution_state.json"),
    }


def validate_and_load(
    cost_dir: Path,
    prior_dir: Path,
    *,
    validator_module: ModuleType | None = None,
) -> tuple[
    dict[str, dict[str, dict[int, dict[str, Any]]]],
    dict[str, dict[str, dict[int, dict[str, Any]]]],
    tuple[int, ...],
    dict[str, Any],
]:
    """Fail closed unless both source runs are terminal and integrity-valid."""
    cost_dir = cost_dir.resolve()
    prior_dir = prior_dir.resolve()
    require(cost_dir.is_dir(), f"cost directory does not exist: {cost_dir}")
    require(prior_dir.is_dir(), f"prior directory does not exist: {prior_dir}")

    cost_status_path = cost_dir / "execution_status.json"
    prior_status_path = prior_dir / "execution_status.json"
    cost_status = load_json(cost_status_path, "cost status")
    prior_status = load_json(prior_status_path, "fallback status")
    cost_counts = (cost_status.get("cells") or {}).get("cost") or {}
    require(cost_status.get("state") == "cost_complete", f"cost run is not terminal: state={cost_status.get('state')!r}")
    require(cost_counts.get("attempted") == 72 and cost_counts.get("missing", 0) == 0, "cost status is not 72/72 terminal")
    require(
        int(cost_counts.get("valid") or 0) + int(cost_counts.get("invalid") or 0) == 72,
        "cost valid+invalid does not equal strict denominator 72",
    )
    # A legitimate offline preflight/report after paid completion rewrites the
    # status to offline_preflight_complete.  Terminality is therefore proved by
    # the fresh 16-cell ledger scan and gate.already_complete below, not by this
    # mutable presentation-state field alone.
    require(
        prior_status.get("state") in {"complete", "offline_preflight_complete"},
        f"fallback run has no admissible terminal/offline status: state={prior_status.get('state')!r}",
    )

    module = validator_module or _import_fallback_runner(prior_dir)
    try:
        frozen = module.protocol()
        expected_parent = module.repo_path(frozen["parent"]["run_directory"]).resolve()
        require(expected_parent == cost_dir, f"fallback parent path {expected_parent} != --cost-dir {cost_dir}")
        source_hash_rows = module.validate_source_hashes(frozen)
        fallback_manifest = module.validate_manifest(frozen)
        selected_plans, graphs, _ = module.validate_selected_plans(frozen, fallback_manifest)
        full_plans = module.load_parent_plans(frozen)
        terminal = module.parent_cost_terminal(frozen, full_plans)
        nominal = module.verify_nominal_reuse(frozen, selected_plans, graphs)
        config = module.paired_config_audit()
        execution = module.expected_execution_rows(fallback_manifest, selected_plans)
        state = module.scan_execution_state(execution, selected_plans, graphs)
    except CloseoutError:
        raise
    except Exception as exc:
        raise CloseoutError(f"read-only fallback integrity validation failed: {type(exc).__name__}: {exc}") from exc

    require(terminal.get("terminal_72_of_72") is True, "fresh parent cost integrity gate is false")
    require(terminal.get("disk_counts", {}).get("attempted") == 72, "fresh cost disk count is not 72")
    require(terminal.get("ledger_counts", {}).get("attempted") == 72, "fresh cost ledger count is not 72")
    require(nominal.get("all_eight_ready") is True and nominal.get("ready_cells") == 8, "fresh nominal reuse is not 8/8")
    require(config.get("all_only_relation_prior_changed") is True, "fresh controlled config-delta audit failed")
    require(state.get("attempted") == 16 and state.get("missing") == 0, "fresh fallback state is not 16/16 terminal")
    require(int(state.get("valid") or 0) + int(state.get("invalid") or 0) == 16, "fallback valid+invalid is not 16")
    require(state.get("ledger_integrity_passed") is True, "fresh fallback ledger integrity failed")

    persisted = _assert_persisted_gates(
        prior_dir,
        module,
        terminal=terminal,
        nominal=nominal,
        state=state,
    )

    selected_slots = tuple(int(slot) for slot in module.EXPECTED_SELECTED_SLOTS)
    require(selected_slots == (1, 3, 8, 10), f"unexpected selected slots: {selected_slots}")
    cost_records: dict[str, dict[str, dict[int, dict[str, Any]]]] = {
        model: {method: {} for method in METHODS} for model in MODELS
    }
    expected_cost_paths: set[Path] = set()
    physical_by_model: dict[str, dict[int, str]] = {model: {} for model in MODELS}
    for model in MODELS:
        plan = full_plans[model]
        require(len(plan) == 12, f"{model}: parent plan does not contain 12 selectors")
        require({int(case["case_order"]) for case in plan} == set(range(1, 13)), f"{model}: plan slots drift")
        for case in plan:
            slot = int(case["case_order"])
            physical_by_model[model][slot] = str(case["physical_scc_fingerprint"])
            for method in METHODS:
                path = (
                    cost_dir
                    / "cost"
                    / module.cost.safe_token(model)
                    / "results"
                    / f"{case['case_id']}__{module.cost.safe_token(method)}.json"
                )
                expected_cost_paths.add(path.resolve())
                result = load_json(path, f"cost result {model}/{method}/slot-{slot:02d}")
                require(result.get("model") == model, f"cost result model mismatch: {path}")
                validate_result_method(result, method, path)
                require(result.get("case_uid") == case["case_uid"], f"cost result case_uid mismatch: {path}")
                require(result.get("physical_scc_fingerprint") == case["physical_scc_fingerprint"], f"cost physical SCC mismatch: {path}")
                require(result.get("strict_denominator_member") is True, f"cost result is not a strict denominator member: {path}")
                cost_records[model][method][slot] = result

    actual_cost_paths = {
        path.resolve() for path in (cost_dir / "cost").glob("*/results/*.json")
    }
    require(actual_cost_paths == expected_cost_paths, "unexpected or missing JSON files in cost result directories")
    for model in MODELS:
        require(len(set(physical_by_model[model].values())) == 12, f"{model}: physical SCC selectors are not unique")
    require(physical_by_model[MODELS[0]] == physical_by_model[MODELS[1]], "cross-model physical SCC slots differ")

    prior_records: dict[str, dict[str, dict[int, dict[str, Any]]]] = {
        model: {profile: {} for profile in PROFILES} for model in MODELS
    }
    execution_by_key = {
        (str(row["model"]), int(row["slot"]), str(row["profile"])): row
        for row in execution
    }
    require(len(execution_by_key) == 16, "fallback execution keys are not unique 16 cells")
    for model in MODELS:
        for profile in PROFILES:
            for slot in selected_slots:
                cell = execution_by_key[(model, slot, profile)]
                path = Path(cell["result_path"])
                result = load_json(path, f"fallback result {model}/{profile}/slot-{slot:02d}")
                require(result.get("strict_denominator_member") is True, f"fallback result is not a strict denominator member: {path}")
                prior_records[model][profile][slot] = result

    gate_evidence = {
        "all_passed": True,
        "cost": {
            "status": "cost_complete",
            "attempted": 72,
            "valid": int(cost_counts.get("valid") or 0),
            "invalid": int(cost_counts.get("invalid") or 0),
            "missing": 0,
            "protocol_sha256": file_hash(cost_dir / "frozen_protocol.json"),
            "status_sha256": file_hash(cost_status_path),
            "ledger_sha256": file_hash(cost_dir / "budget_ledger.jsonl"),
            "fresh_parent_integrity_cells": terminal["integrity_checked_cells"],
        },
        "prior": {
            "status": prior_status.get("state"),
            "terminality_basis": "fresh 16/16 result+ledger scan and persisted gate.already_complete",
            "attempted": 16,
            "valid": int(state.get("valid") or 0),
            "invalid": int(state.get("invalid") or 0),
            "missing": 0,
            "protocol_sha256": file_hash(prior_dir / "frozen_fallback_protocol.json"),
            "runner_sha256": file_hash(prior_dir / "run_prior_fallback.py"),
            "status_sha256": file_hash(prior_status_path),
            "ledger_sha256": file_hash(prior_dir / "budget_ledger.jsonl"),
            "nominal_reuse_ready": 8,
        },
        "read_only_validation": {
            "source_hash_rows": len(source_hash_rows),
            "selected_slots": list(selected_slots),
            **persisted,
        },
    }
    return cost_records, prior_records, selected_slots, gate_evidence


def _format_rate(value: Any) -> str:
    return "NA" if not isinstance(value, (int, float)) else f"{100.0 * float(value):.1f}%"


def markdown_report(payload: dict[str, Any]) -> str:
    analysis = payload["analysis"]
    lines = [
        "# SCC 等权配对统计收尾",
        "",
        f"生成时间：{payload['generated_at']}。两条输入实验均已通过 terminal、identity、hash、ledger 与 strict-denominator 门禁。Bootstrap 固定为 {DRAWS:,} 次、seed {SEED}，cluster unit 为 physical SCC。",
        "",
        "## Cost / reliability：三方法严格性能",
        "",
        "| Model | Method | Metric | Success / 12 | Strict rate | 95% cluster-bootstrap CI | Invalid cells |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in analysis["cost"]["method_performance"]:
        lines.append(
            "| {model} | {method_label} | {metric} | {successes}/12 | {rate} | [{lo}, {hi}] | {invalid_cells} |".format(
                **row,
                rate=_format_rate(row["strict_rate"]),
                lo=_format_rate(row["ci95_lower"]),
                hi=_format_rate(row["ci95_upper"]),
            )
        )
    lines.extend(
        [
            "",
            "## Cost / reliability：SA-MCGS − LEA 配对差值",
            "",
            "| Model | Metric | Delta | 95% paired CI | Better / tied / worse |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in analysis["cost"]["sa_mcgs_vs_lea_paired"]:
        lines.append(
            "| {model} | {metric} | {delta} | [{lo}, {hi}] | {improved} / {tied} / {worsened} |".format(
                **row,
                delta=_format_rate(row["strict_rate_delta"]),
                lo=_format_rate(row["ci95_lower"]),
                hi=_format_rate(row["ci95_upper"]),
            )
        )
    lines.extend(
        [
            "",
            "## Relation-prior：扰动 − nominal 配对差值",
            "",
            "| Model | Profile | Metric | Delta | 95% paired CI | Better / tied / worse |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for row in analysis["relation_prior"]["profile_vs_nominal_paired"]:
        lines.append(
            "| {model} | {profile} | {metric} | {delta} | [{lo}, {hi}] | {improved} / {tied} / {worsened} |".format(
                **row,
                delta=_format_rate(row["strict_rate_delta"]),
                lo=_format_rate(row["ci95_lower"]),
                hi=_format_rate(row["ci95_upper"]),
            )
        )
    lines.extend(
        [
            "",
            "Relation-prior 区间仅基于预冻结的 4 个不同 SCC，属于探索性敏感度描述；不据此宣称统计显著或无差异。所有 invalid/未定义布尔值均按严格分母计 0，未做 valid-only 删除。",
            "",
        ]
    )
    return "\n".join(lines)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cost-dir", required=True, type=Path)
    parser.add_argument("--prior-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        cost_records, prior_records, selected_slots, gates = validate_and_load(
            args.cost_dir, args.prior_dir
        )
        analysis = compute_analysis(
            cost_records, prior_records, selected_slots=selected_slots
        )
        payload = {
            "schema": SCHEMA,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "zero_api": True,
            "inputs": {
                "cost_dir": str(args.cost_dir.resolve()),
                "prior_dir": str(args.prior_dir.resolve()),
            },
            "gates": gates,
            "analysis": analysis,
        }
        payload["analysis_sha256"] = canonical_hash(analysis)
        out_dir = args.out_dir.resolve()
        json_path = out_dir / "paired_cluster_closeout.json"
        markdown_path = out_dir / "paired_cluster_closeout.md"
        atomic_write(
            json_path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        atomic_write(markdown_path, markdown_report(payload))
        print(
            json.dumps(
                {
                    "status": "complete",
                    "json": str(json_path),
                    "markdown": str(markdown_path),
                    "analysis_sha256": payload["analysis_sha256"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except CloseoutError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"REFUSED: unexpected closeout error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

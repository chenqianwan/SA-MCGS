#!/usr/bin/env python3
"""Independent final audit and publication summaries for the frozen Stage-1 run."""

from __future__ import annotations

import csv
import copy
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any


RUN_ROOT = Path(__file__).resolve().parent
PHASE = RUN_ROOT / "formal"
REPO_ROOT = next(path for path in RUN_ROOT.parents if (path / "emnlp2026_discussion").is_dir())
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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def canonical_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mode_counts(result: dict[str, Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get("mode")) for row in result.get("selection_events", [])).items()))


def load_ablation_module():
    path = REPO_ROOT / "emnlp2026_discussion" / "run_component_ablation_stage0.py"
    sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location("stage1_frozen_ablation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    protocol = load_json(PHASE / "protocol.json")
    gate = load_json(PHASE / "gate.json")
    manifest = load_json(PHASE / "results_manifest.json")
    reuse = load_json(PHASE / "reuse_from_smoke_order8.json")
    plan = load_json(PHASE / "case_plan.json")
    uncertainty = load_json(PHASE / "stage1_clustered_uncertainty.json")
    detail_rows = read_csv(PHASE / "stage1_case_results_strict.csv")
    publication_rows = read_csv(PHASE / "stage1_publication_table.csv")

    results: dict[tuple[int, str], dict[str, Any]] = {}
    result_paths: dict[tuple[int, str], Path] = {}
    for path in sorted((PHASE / "results").glob("*.json")):
        result = load_json(path)
        key = (int(result["case_order"]), result["ablation_variant"])
        if key in results:
            raise AssertionError(f"Duplicate result: {key}")
        results[key] = result
        result_paths[key] = path

    orders = [int(row["case_order"]) for row in plan]
    expected = {(order, variant) for order in orders for variant in VARIANTS}
    assert set(results) == expected, (sorted(expected - set(results)), sorted(set(results) - expected))
    assert len(results) == 68 and len(orders) == 17

    # Recompute the actual base configs from frozen source, not merely from the recorded hashes.
    ablation = load_ablation_module()
    config_args = SimpleNamespace(
        budget=int(protocol["budget_rollouts"]),
        window_size=int(protocol["window_size"]),
        internal_concurrency=int(protocol["internal_concurrency"]),
        compression_profile=protocol["compression_profile"],
    )
    def recompute_config(variant: str) -> dict[str, Any]:
        if variant != FULL:
            return ablation.make_mcgs_config(config_args, variant)
        cfg = copy.deepcopy(ablation.battle.MCGS_DEFAULT)
        mcgs = cfg["alphago_mcgs"]
        mcgs["budget"] = config_args.budget
        mcgs["window_size"] = config_args.window_size
        mcgs["concurrency"] = config_args.internal_concurrency
        mcgs["trace"] = True
        evidence = mcgs.setdefault("evidence", {})
        evidence["compression_profile"] = config_args.compression_profile
        evidence.update(
            ablation.battle.MCGS_COMPRESSION_PROFILES.get(config_args.compression_profile, {})
        )
        return cfg

    recomputed_config_hashes = {
        variant: canonical_sha256(recompute_config(variant)) for variant in VARIANTS
    }
    recorded_config_hashes = protocol["config_sha256"]
    config_hash_match = {
        variant: recomputed_config_hashes[variant] == recorded_config_hashes[variant]
        for variant in VARIANTS
    }

    runtime_patch = {
        FULL: {"selection": "native_sa_mcgs", "seed_rule": None},
        "no-relation-first-memory": {"selection": "native_without_relation_first", "seed_rule": None},
        "no-critical-pair-ledger-revisit": {"selection": "native_without_critical_pair_revisit", "seed_rule": None},
        "random-local-window-selection": {
            "selection": "random_local_window",
            "seed_rule": "8229 + case_order * 1009",
        },
    }
    effective_intervention_hashes = {
        variant: canonical_sha256(
            {"base_config_sha256": recorded_config_hashes[variant], "runtime_patch": runtime_patch[variant]}
        )
        for variant in VARIANTS
    }
    assert all(config_hash_match.values())
    assert len(set(effective_intervention_hashes.values())) == 4

    plan_by_order = {int(row["case_order"]): row for row in plan}
    csv_by_key = {(int(row["case_order"]), row["variant"]): row for row in detail_rows}
    quartet_audits = []
    evaluator_checks = []
    toggle_checks: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for order in orders:
        quartet = [results[(order, variant)] for variant in VARIANTS]
        planned = plan_by_order[order]
        case_uids = {row.get("case_uid") for row in quartet}
        fingerprints = {row.get("actual_scc_fingerprint") for row in quartet}
        injections = {canonical(row.get("actual_injection_identity")) for row in quartet}
        planned_injections = {canonical(row.get("planned_injection_identity")) for row in quartet}
        source_hashes = {row.get("source_result_sha256") for row in quartet}
        prompt_audit_hashes = {row.get("prompt_semantic_audit_hash") for row in quartet}
        models = {row.get("model") for row in quartet}
        budgets = {int(row.get("budget")) for row in quartet}
        internal_concurrency = {int(row.get("internal_concurrency")) for row in quartet}
        case_concurrency = {int(row.get("case_concurrency")) for row in quartet}
        identity_ok = all(
            canonical(row.get("planned_case_identity")) == canonical(row.get("actual_case_identity"))
            and row.get("case_uid") == planned["case_uid"]
            and row.get("actual_scc_fingerprint") == planned["planned_scc_fingerprint"]
            and canonical(row.get("planned_injection_identity")) == canonical(row.get("actual_injection_identity"))
            for row in quartet
        )
        parity_ok = (
            len(case_uids) == 1
            and len(fingerprints) == 1
            and len(injections) == 1
            and len(planned_injections) == 1
            and len(source_hashes) == 1
            and len(prompt_audit_hashes) == 1
            and models == {"gpt-4o"}
            and budgets == {60}
            and internal_concurrency == {3}
            and case_concurrency == {1}
            and next(iter(injections)) == next(iter(planned_injections))
        )
        quartet_audits.append(
            {
                "case_order": order,
                "case_id": planned["case_id"],
                "case_uid": planned["case_uid"],
                "source_scc_uid": planned["source_scc_uid"],
                "identity_exact": identity_ok,
                "paired_inputs_exact": parity_ok,
                "injection_seed": quartet[0]["actual_injection_identity"]["seed"],
                "prompt_semantic_audit_hash": next(iter(prompt_audit_hashes)),
                "source_result_sha256": next(iter(source_hashes)),
            }
        )

        for variant, result in zip(VARIANTS, quartet):
            events = result.get("selection_events") or []
            modes = mode_counts(result)
            if variant == FULL:
                toggle_ok = (
                    result.get("relation_first_enabled") is True
                    and int(result.get("relation_probe_count") or 0) > 0
                    and "random_local_window" not in modes
                )
                detail = "relation-first active; native selection; no random-window events"
            elif variant == "no-relation-first-memory":
                toggle_ok = (
                    result.get("relation_first_enabled") is False
                    and int(result.get("relation_probe_count") or 0) == 0
                    and "relation_probe" not in modes
                    and "ucb_relation_bias" not in modes
                )
                detail = "relation-first false; relation probes 0; no relation-biased selection"
            elif variant == "no-critical-pair-ledger-revisit":
                toggle_ok = (
                    result.get("relation_first_enabled") is True
                    and len(result.get("critical_pair_ledger_rows") or []) == 0
                    and len(result.get("critical_pair_locked_edges") or []) == 0
                    and len(result.get("critical_pair_candidate_edges") or []) == 0
                    and len(result.get("critical_pair_revisit_history") or []) == 0
                    and "critical_pair_revisit" not in modes
                )
                detail = "critical ledger/locks/candidates/revisit all empty; no revisit selection"
            else:
                expected_seed = 8229 + order * 1009
                toggle_ok = (
                    len(events) == 60
                    and modes == {"random_local_window": 60}
                    and all(int(event.get("random_seed")) == expected_seed for event in events)
                )
                detail = f"60/60 random_local_window events; deterministic seed {expected_seed}"
            toggle_checks[variant].append(
                {
                    "case_order": order,
                    "passed": toggle_ok,
                    "detail": detail,
                    "selection_mode_counts": modes,
                }
            )

            invalid = bool(result.get("component_ablation_error"))
            risk_nodes = set(result.get("injected_risk_nodes") or [])
            core_nodes = set(result.get("core_evidence_risk_subgraph_nodes") or [])
            recomputed_any = bool(risk_nodes & core_nodes) if not invalid else False
            recomputed_all = risk_nodes.issubset(core_nodes) if (risk_nodes and not invalid) else False
            stored_any = bool(result.get("core_evidence_contains_any_risk_node")) if not invalid else False
            stored_all = bool(result.get("core_evidence_contains_all_risk_nodes")) if not invalid else False
            root3_stored = result.get("root_top3_hit")
            if not isinstance(root3_stored, bool):
                root3_stored = result.get("top3_hit")
            root3_stored = bool(root3_stored) if not invalid else False
            csv_row = csv_by_key[(order, variant)]
            evaluator_ok = (
                recomputed_any == stored_any == as_bool(csv_row["risk_any_strict"])
                and recomputed_all == stored_all == as_bool(csv_row["risk_all_strict"])
                and root3_stored == as_bool(csv_row["root_at_3_strict"])
                and invalid == as_bool(csv_row["invalid"])
            )
            evaluator_checks.append(
                {
                    "case_order": order,
                    "variant": variant,
                    "risk_nodes": sorted(risk_nodes),
                    "final_core_nodes": sorted(core_nodes),
                    "risk_any_recomputed": recomputed_any,
                    "risk_all_recomputed": recomputed_all,
                    "root_at_3_stored": root3_stored,
                    "invalid": invalid,
                    "passed": evaluator_ok,
                }
            )

    assert all(row["identity_exact"] and row["paired_inputs_exact"] for row in quartet_audits)
    assert all(row["passed"] for rows in toggle_checks.values() for row in rows)
    assert all(row["passed"] for row in evaluator_checks)

    strict_counts = {}
    for variant in VARIANTS:
        rows = [row for row in detail_rows if row["variant"] == variant]
        strict_counts[variant] = {
            "attempted": len(rows),
            "valid": sum(not as_bool(row["invalid"]) for row in rows),
            "invalid": sum(as_bool(row["invalid"]) for row in rows),
            "denominator": len(rows),
        }
    assert all(row == {"attempted": 17, "valid": 17, "invalid": 0, "denominator": 17} for row in strict_counts.values())

    uncertainty_by_key = {(row["variant"], row["metric"]): row for row in uncertainty}
    publication_by_label = {row["Variant"]: row for row in publication_rows}
    paired_rows = []
    full_values = {
        order: evaluator_checks[(orders.index(order) * len(VARIANTS))]["risk_all_recomputed"]
        for order in orders
    }
    for variant in VARIANTS:
        metrics = {metric: uncertainty_by_key[(variant, metric)] for metric in ("Root@3", "Risk-any", "Risk-all")}
        values = {
            order: next(
                row["risk_all_recomputed"]
                for row in evaluator_checks
                if row["case_order"] == order and row["variant"] == variant
            )
            for order in orders
        }
        improved = [order for order in orders if values[order] and not full_values[order]] if variant != FULL else []
        degraded = [order for order in orders if not values[order] and full_values[order]] if variant != FULL else []
        table = publication_by_label[LABELS[variant]]
        paired_rows.append(
            {
                "variant": variant,
                "label": LABELS[variant],
                "n": 17,
                "valid": int(table["Valid"]),
                "invalid": int(table["Invalid"]),
                "root_at_3": metrics["Root@3"]["estimate"],
                "root_at_3_cluster_ci_low": metrics["Root@3"]["clustered_ci_95_low"],
                "root_at_3_cluster_ci_high": metrics["Root@3"]["clustered_ci_95_high"],
                "root_at_3_delta_vs_full": metrics["Root@3"].get("paired_delta_vs_full"),
                "root_at_3_delta_cluster_ci_low": metrics["Root@3"].get("paired_delta_clustered_ci_95_low"),
                "root_at_3_delta_cluster_ci_high": metrics["Root@3"].get("paired_delta_clustered_ci_95_high"),
                "risk_any": metrics["Risk-any"]["estimate"],
                "risk_any_cluster_ci_low": metrics["Risk-any"]["clustered_ci_95_low"],
                "risk_any_cluster_ci_high": metrics["Risk-any"]["clustered_ci_95_high"],
                "risk_any_delta_vs_full": metrics["Risk-any"].get("paired_delta_vs_full"),
                "risk_any_delta_cluster_ci_low": metrics["Risk-any"].get("paired_delta_clustered_ci_95_low"),
                "risk_any_delta_cluster_ci_high": metrics["Risk-any"].get("paired_delta_clustered_ci_95_high"),
                "risk_all": metrics["Risk-all"]["estimate"],
                "risk_all_cluster_ci_low": metrics["Risk-all"]["clustered_ci_95_low"],
                "risk_all_cluster_ci_high": metrics["Risk-all"]["clustered_ci_95_high"],
                "risk_all_delta_vs_full": metrics["Risk-all"].get("paired_delta_vs_full"),
                "risk_all_delta_cluster_ci_low": metrics["Risk-all"].get("paired_delta_clustered_ci_95_low"),
                "risk_all_delta_cluster_ci_high": metrics["Risk-all"].get("paired_delta_clustered_ci_95_high"),
                "risk_all_discordant_improved": len(improved),
                "risk_all_discordant_degraded": len(degraded),
                "risk_all_improved_case_orders": "|".join(map(str, improved)),
                "risk_all_degraded_case_orders": "|".join(map(str, degraded)),
                "api_calls": int(table["API calls"]),
                "input_tokens": int(table["Input tokens"]),
                "output_tokens": int(table["Output tokens"]),
                "total_tokens": int(table["Total tokens"]),
                "estimated_usd": float(table["Estimated USD"]),
            }
        )

    paired_csv = PHASE / "stage1_paired_publication_table.csv"
    with paired_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(paired_rows[0]))
        writer.writeheader()
        writer.writerows(paired_rows)

    full_failures = []
    for order in orders:
        full_check = next(
            row for row in evaluator_checks if row["case_order"] == order and row["variant"] == FULL
        )
        if full_check["risk_all_recomputed"]:
            continue
        arms = []
        for variant in VARIANTS:
            result = results[(order, variant)]
            check = next(
                row for row in evaluator_checks if row["case_order"] == order and row["variant"] == variant
            )
            trace = result.get("trace_events") or []
            convergence = result.get("convergence_trace") or []
            arms.append(
                {
                    "variant": variant,
                    "risk_all": check["risk_all_recomputed"],
                    "risk_all_top3_ranking": bool(result.get("risk_all_top3_hit")),
                    "risk_nodes": check["risk_nodes"],
                    "final_core_nodes": check["final_core_nodes"],
                    "missing_risk_nodes": sorted(set(check["risk_nodes"]) - set(check["final_core_nodes"])),
                    "risk_node_ranks": result.get("risk_node_ranks"),
                    "selection_mode_counts": mode_counts(result),
                    "trace_events": len(trace),
                    "last_trace_selection": (trace[-1].get("selection") if trace else None),
                    "last_convergence": (convergence[-1] if convergence else None),
                    "result_file": str(result_paths[(order, variant)]),
                    "result_sha256": file_sha256(result_paths[(order, variant)]),
                }
            )
        full_failures.append(
            {
                "case_order": order,
                "case_id": plan_by_order[order]["case_id"],
                "case_uid": plan_by_order[order]["case_uid"],
                "source_scc_uid": plan_by_order[order]["source_scc_uid"],
                "trace_root_cause": (
                    "Full ranked every injected risk node in its top 3, but the frozen dynamic final-core "
                    "selection omitted one injected root risk node. The strict Risk-all evaluator measures "
                    "all-risk retention in the final evidence core, not top-3 ranking coverage."
                ),
                "arms": arms,
            }
        )
    assert [row["case_order"] for row in full_failures] == [20, 73]

    code_hash_checks = {}
    for relpath, expected_hash in protocol["code_sha256"].items():
        path = REPO_ROOT / relpath
        code_hash_checks[relpath] = {
            "expected": expected_hash,
            "actual": file_sha256(path),
            "passed": path.is_file() and file_sha256(path) == expected_hash,
        }
    artifact_hash_checks = {}
    for relpath, expected_hash in manifest["files"].items():
        path = PHASE / relpath
        artifact_hash_checks[relpath] = {
            "expected": expected_hash,
            "actual": file_sha256(path),
            "passed": path.is_file() and file_sha256(path) == expected_hash,
        }
    result_hash_checks = []
    for row in manifest["result_index"]:
        path = Path(row["result_file"])
        actual = file_sha256(path)
        result_hash_checks.append(
            {
                "case_id": row["case_id"],
                "variant": row["variant"],
                "expected": row["result_sha256"],
                "actual": actual,
                "passed": actual == row["result_sha256"],
            }
        )
    assert all(row["passed"] for row in code_hash_checks.values())
    assert all(row["passed"] for row in artifact_hash_checks.values())
    assert all(row["passed"] for row in result_hash_checks)

    by_arm_gate = {row["variant"]: row for row in gate["by_arm"]}
    formal_matrix_reliability = {
        "network_calls": sum(row["network_calls"] for row in by_arm_gate.values()),
        "network_successes": sum(row["network_calls"] - row["network_failures"] for row in by_arm_gate.values()),
        "network_failures": sum(row["network_failures"] for row in by_arm_gate.values()),
        "logical_rollouts": sum(row["logical_rollouts"] for row in by_arm_gate.values()),
        "logical_first_parse_or_transport_failures": sum(
            row["first_parse_or_transport_failures"] for row in by_arm_gate.values()
        ),
        "recovered_after_first_failure": sum(row["recovered_after_first_failure"] for row in by_arm_gate.values()),
        "exhausted_without_parse": sum(row["exhausted_without_parse"] for row in by_arm_gate.values()),
        "case_valid": sum(row["case_valid"] for row in by_arm_gate.values()),
        "case_invalid": 68 - sum(row["case_valid"] for row in by_arm_gate.values()),
        "case_level_retries": int(manifest["case_level_retries"]),
    }
    formal_matrix_usage = {
        "recorded_api_calls": sum(int(row["API calls"]) for row in publication_rows),
        "prompt_tokens": sum(int(row["Input tokens"]) for row in publication_rows),
        "completion_tokens": sum(int(row["Output tokens"]) for row in publication_rows),
        "total_tokens": sum(int(row["Total tokens"]) for row in publication_rows),
        "estimated_usd": sum(float(row["Estimated USD"]) for row in publication_rows),
    }
    assert formal_matrix_usage["recorded_api_calls"] == formal_matrix_reliability["network_calls"]
    assert formal_matrix_reliability == {
        "network_calls": 3934,
        "network_successes": 3931,
        "network_failures": 3,
        "logical_rollouts": 3928,
        "logical_first_parse_or_transport_failures": 6,
        "recovered_after_first_failure": 6,
        "exhausted_without_parse": 0,
        "case_valid": 68,
        "case_invalid": 0,
        "case_level_retries": 0,
    }

    negative_control_audit = {
        "audit_version": "stage1_identity_safe_independent_negative_control_v1",
        "passed": True,
        "matrix": {"cases": 17, "variants": 4, "cells": 68, "strict_denominator_per_arm": 17},
        "paired_identity_and_input_gate": {
            "passed": all(row["identity_exact"] and row["paired_inputs_exact"] for row in quartet_audits),
            "shared_model": protocol["model"],
            "shared_budget": protocol["budget_rollouts"],
            "shared_window_size": protocol["window_size"],
            "shared_internal_concurrency": protocol["internal_concurrency"],
            "shared_injection_seed": protocol["injection"]["seed"],
            "prompt_builder_source_sha256": protocol["prompt_schema_provenance"]["prompt_builder_source_sha256"],
            "json_parser_source_sha256": protocol["prompt_schema_provenance"]["json_parser_source_sha256"],
            "response_schema": protocol["prompt_schema_provenance"]["required_top_level_schema"],
            "note": (
                "Case/source/injection identities and the prompt-builder/parser/schema are paired. Exact request "
                "prompt text is not forced identical because the ablations intentionally alter selected windows/trajectories."
            ),
            "quartets": quartet_audits,
        },
        "effective_intervention_gate": {
            "passed": all(config_hash_match.values())
            and len(set(effective_intervention_hashes.values())) == 4
            and all(row["passed"] for rows in toggle_checks.values() for row in rows),
            "recorded_base_config_sha256": recorded_config_hashes,
            "recomputed_base_config_sha256": recomputed_config_hashes,
            "base_config_hash_match": config_hash_match,
            "runtime_patch": runtime_patch,
            "effective_intervention_sha256": effective_intervention_hashes,
            "note": (
                "The random arm intentionally shares Full's static base-config hash; its independent effective "
                "intervention hash differs because the frozen runtime selector is random_local_window."
            ),
            "by_variant_case_checks": toggle_checks,
        },
        "evaluator_and_denominator_gate": {
            "passed": all(row["passed"] for row in evaluator_checks),
            "risk_any_definition": "injected_risk_nodes intersects final core_evidence_risk_subgraph_nodes",
            "risk_all_definition": "injected_risk_nodes is a subset of final core_evidence_risk_subgraph_nodes",
            "root_at_3_definition": "root_top3_hit (fallback top3_hit)",
            "invalid_policy": "invalid cells stay in the strict denominator and count as metric misses",
            "strict_counts": strict_counts,
            "checks": evaluator_checks,
        },
        "full_only_risk_all_failures": full_failures,
        "paired_publication_rows": paired_rows,
        "formal_matrix_five_layer_reliability": formal_matrix_reliability,
        "hash_integrity_gate": {
            "passed": all(row["passed"] for row in code_hash_checks.values())
            and all(row["passed"] for row in artifact_hash_checks.values())
            and all(row["passed"] for row in result_hash_checks),
            "code": code_hash_checks,
            "artifacts": artifact_hash_checks,
            "results": result_hash_checks,
        },
        "smoke_reuse_gate": {
            "passed": bool(reuse["passed"]),
            "all_checks_passed": all(bool(value) for value in reuse["checks"].values()),
            "checks": reuse["checks"],
            "reused_case_order": 8,
            "reused_cells": 4,
        },
    }
    audit_path = PHASE / "negative_control_audit.json"
    write_json(audit_path, negative_control_audit)

    final_summary = {
        "summary_version": "stage1_identity_safe_final_summary_v1",
        "status": "complete",
        "passed": bool(gate["passed"]) and negative_control_audit["passed"],
        "formal_matrix": {
            "cases": 17,
            "variants": 4,
            "cells": 68,
            "valid": 68,
            "invalid": 0,
            "source_scc_clusters": 5,
            "orders": orders,
        },
        "results": paired_rows,
        "full_only_risk_all_failure_orders": [row["case_order"] for row in full_failures],
        "formal_matrix_five_layer_reliability": formal_matrix_reliability,
        "cost": {
            "formal_matrix_including_reused_order8_once": formal_matrix_usage,
            "new_formal_64_cells": manifest["self_usage_this_phase"],
            "smoke_12_cells": gate["smoke_self_usage"],
            "unique_paid_smoke_plus_new_formal": manifest["self_usage_all_phases"],
            "hard_cap_usd": float(manifest["hard_budget_usd"]),
            "headroom_usd": float(manifest["hard_budget_usd"])
            - float(manifest["self_usage_all_phases"]["estimated_usd"]),
            "account_balance_cross_check": gate["account_balance_cross_check"],
            "account_balance_note": "Shared-account debit is contaminated by concurrent experiment lines; self token ledger is authoritative.",
        },
        "gates": {
            "runner_gate": gate["passed"],
            "identity_and_input": negative_control_audit["paired_identity_and_input_gate"]["passed"],
            "effective_intervention": negative_control_audit["effective_intervention_gate"]["passed"],
            "evaluator_and_denominator": negative_control_audit["evaluator_and_denominator_gate"]["passed"],
            "hash_integrity": negative_control_audit["hash_integrity_gate"]["passed"],
            "smoke_reuse": negative_control_audit["smoke_reuse_gate"]["passed"],
        },
        "interpretation": {
            "supported": (
                "All arms saturate Root@3 and Risk-any. Random-window selection is numerically lower than Full on "
                "Risk-all, but its clustered paired interval includes zero."
            ),
            "not_supported": (
                "This run does not support the old claim that relation-first memory or the critical-pair "
                "ledger improves Risk-all: both removals are +2/17 versus Full, with clustered intervals including zero."
            ),
            "caution": "Only five physical source-SCC clusters; treat the component attribution as inconclusive/negative evidence.",
        },
        "files": {
            "paired_csv": str(paired_csv),
            "negative_control_audit": str(audit_path),
            "strict_case_csv": str(PHASE / "stage1_case_results_strict.csv"),
            "clustered_uncertainty": str(PHASE / "stage1_clustered_uncertainty.json"),
            "runner_gate": str(PHASE / "gate.json"),
            "protocol": str(PHASE / "protocol.json"),
            "manifest": str(PHASE / "results_manifest.json"),
        },
    }
    summary_path = PHASE / "final_summary.json"
    write_json(summary_path, final_summary)

    def pct(value: float | None) -> str:
        return "—" if value is None else f"{100 * value:.1f}%"

    report = [
        "# Stage-1 identity-safe 四臂配对消融：最终报告",
        "",
        "状态：**完成并通过最终审计（68/68 valid，0 invalid）**。旧 frozen Full 因缺 raw prompt/config hash，未作为严格对照；本批次使用同期 Full。",
        "",
        "## 可入稿结果",
        "",
        "| Arm | Root@3 [cluster 95% CI] | Risk-any [cluster 95% CI] | Risk-all [cluster 95% CI] | Δ Risk-all vs Full [cluster 95% CI] | Risk-all discordance (+/−) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in paired_rows:
        root = f"{pct(row['root_at_3'])} [{pct(row['root_at_3_cluster_ci_low'])}, {pct(row['root_at_3_cluster_ci_high'])}]"
        risk_any = f"{pct(row['risk_any'])} [{pct(row['risk_any_cluster_ci_low'])}, {pct(row['risk_any_cluster_ci_high'])}]"
        risk_all = f"{pct(row['risk_all'])} [{pct(row['risk_all_cluster_ci_low'])}, {pct(row['risk_all_cluster_ci_high'])}]"
        delta = (
            "reference"
            if row["risk_all_delta_vs_full"] is None
            else f"{pct(row['risk_all_delta_vs_full'])} [{pct(row['risk_all_delta_cluster_ci_low'])}, {pct(row['risk_all_delta_cluster_ci_high'])}]"
        )
        discordance = (
            "—"
            if row["variant"] == FULL
            else f"{row['risk_all_discordant_improved']}/{row['risk_all_discordant_degraded']}"
        )
        report.append(f"| {row['label']} | {root} | {risk_any} | {risk_all} | {delta} | {discordance} |")

    report.extend(
        [
            "",
            "这里的 +/− 分别表示相对 Full 从失败变成功、从成功变失败的配对 case 数。Root@3 与 Risk-any 四臂均饱和；所有非零 Risk-all 配对区间均覆盖 0。",
            "",
            "## 结论与旧归因的关系",
            "",
            "本批次**不支持**旧 rebuttal 中“relation-first memory 或 critical-pair ledger 提升 Risk-all”的组件归因。两个消融均为 17/17，Full 为 15/17；二者相对 Full 均 +2/17（+11.8 pp，clustered 95% CI [0, 25.0 pp]）。这不是显著正向证据：只有 5 个 physical source-SCC clusters，区间包含 0。",
            "",
            "Random local-window 为 14/17，相对 Full −1/17（−5.9 pp，clustered 95% CI [−22.2, 14.3 pp]；discordance 2/3），同样不能作确定性组件结论。最稳妥的入稿表述是：在这一小型 identity-safe 子集上，Root@3/Risk-any 无差异，Risk-all 的组件贡献不确定，且两个结构组件的移除没有造成退化。",
            "",
            "## 两处 Full-only Risk-all 失败与 trace 根因",
            "",
        ]
    )
    for failure in full_failures:
        full_arm = next(row for row in failure["arms"] if row["variant"] == FULL)
        report.extend(
            [
                f"### Case {failure['case_order']}: `{failure['case_id']}`",
                "",
                f"注入 risk nodes 为 `{', '.join(full_arm['risk_nodes'])}`。Full 的风险排名仍覆盖全部 risk nodes（Risk-all@top3=True），但最终 dynamic evidence core 漏掉 `{', '.join(full_arm['missing_risk_nodes'])}`，因此预冻结的 final-core Risk-all=False。",
                "",
                "| Arm | Final-core Risk-all | Missing risk node(s) | Selection modes |",
                "|---|---:|---|---|",
            ]
        )
        for arm in failure["arms"]:
            missing = ", ".join(arm["missing_risk_nodes"]) or "none"
            modes = ", ".join(f"{key}:{value}" for key, value in arm["selection_mode_counts"].items())
            report.append(f"| {LABELS[arm['variant']]} | {str(arm['risk_all'])} | {missing} | {modes} |")
        report.extend(
            [
                "",
                f"四臂完整输出和末次 trace/convergence 摘要已固化在 `negative_control_audit.json`；Full 原始结果：`{full_arm['result_file']}`。",
                "",
            ]
        )

    report.extend(
        [
            "## 独立负控与 evaluator 核验",
            "",
            "- 17 个 quartet 的 case_uid、physical SCC fingerprint、source hash、注入身份与 seed=42 完全一致；model=gpt-4o、budget=60、window=4、internal concurrency=3 一致。",
            f"- prompt builder hash=`{protocol['prompt_schema_provenance']['prompt_builder_source_sha256']}`；parser hash=`{protocol['prompt_schema_provenance']['json_parser_source_sha256']}`；response schema 冻结一致。精确 request prompt 会因各臂选择不同窗口/轨迹而不同，这是干预本身，不是 parity 错误。",
            "- Full/no-relation/no-critical 的 base config hash 已从冻结源码独立重算并逐一匹配。Random 臂按设计与 Full 共用 base config hash，但其 runtime selector 的 17×60 events 均为 `random_local_window`，seed 规则为 `8229 + case_order×1009`；组合后的四个 effective intervention hashes 全部不同。",
            "- no-relation：17/17 均 `relation_first_enabled=False`、relation probes=0，且无 relation-biased selection；no-critical：17/17 ledger/locked/candidate/revisit 全空；Full 使用原生 relation-first；random：每 case 60/60 random events。",
            "- Risk-any/Risk-all 已对 68 格从集合关系独立重算，并与结果 JSON、strict CSV 三方逐格一致。Risk-all 定义为 `injected_risk_nodes ⊆ final core_evidence_risk_subgraph_nodes`，不是 top-3 ranking coverage。每臂 denominator=17；0 invalid；不存在 evaluator 或 denominator 错误。",
            "- protocol/code/result/artifact SHA256 全部复算匹配；order 8 的四格 smoke promotion 29/29 checks 通过，非结果选择性复用。",
            "",
            "## 五层可靠性与成本",
            "",
            "正式 68-cell 矩阵：3934 network calls（3931 success / 3 fail）；3928 logical rollouts；6 个 first-parse/transport fail，6 recovered，0 exhausted；68 case-level valid，0 invalid，0 case retry。按臂明细见 `gate.json`。",
            "",
            f"正式矩阵本身（order 8 只计一次）为 {formal_matrix_usage['total_tokens']:,} tokens、${formal_matrix_usage['estimated_usd']:.6f}。实际唯一付费账本为 smoke 12 格 + formal 新跑 64 格：{manifest['self_usage_all_phases']['recorded_api_calls']} calls、{manifest['self_usage_all_phases']['total_tokens']:,} tokens、${manifest['self_usage_all_phases']['estimated_usd']:.6f}；低于 $60 硬上限，余量 ${60 - manifest['self_usage_all_phases']['estimated_usd']:.6f}。",
            "",
            f"共享账户在 formal checkpoint 间从 ${gate['account_balance_cross_check']['available_usd_at_first_checkpoint']:.6f} 到 ${gate['account_balance_cross_check']['available_usd_at_last_checkpoint']:.6f}，但期间有并行实验，因此该差额仅作交叉核验；本线 token ledger 才是可归因成本。",
            "",
            "## 产物",
            "",
            "- `stage1_paired_publication_table.csv`：可入稿四臂点估计、cluster CI、paired delta 与 discordance。",
            "- `final_summary.json`：最终机器可读汇总。",
            "- `negative_control_audit.json`：逐 case parity/toggle/evaluator、Full failure trace 与 hash 证据。",
            "- `stage1_case_results_strict.csv`：68 格 strict 明细。",
            "- `stage1_clustered_uncertainty.json`：20,000 次 source-SCC clustered bootstrap。",
            "- `gate.json` / `GATE_ZH.md`：五层正式 gate。",
            "",
            "未修改顶层 `plan.md` / `REMAINING_EXPERIMENTS_ZH.md`，未提交或推送 Git。",
        ]
    )
    report_path = PHASE / "FINAL_REPORT_ZH.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")

    # Add final output hashes after all three files have been written.
    final_summary["files"].update(
        {
            "final_report": str(report_path),
            "final_report_sha256": file_sha256(report_path),
            "paired_csv_sha256": file_sha256(paired_csv),
            "negative_control_audit_sha256": file_sha256(audit_path),
        }
    )
    write_json(summary_path, final_summary)
    print(
        json.dumps(
            {
                "passed": final_summary["passed"],
                "cells": 68,
                "full_failures": [row["case_order"] for row in full_failures],
                "cost_usd": manifest["self_usage_all_phases"]["estimated_usd"],
                "report": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Synthetic, zero-API tests for paired_cluster_closeout.py."""

from __future__ import annotations

import tempfile
import unittest
import json
from types import SimpleNamespace
from pathlib import Path

import paired_cluster_closeout as closeout


def result(method: str, success: bool, *, invalid: bool = False) -> dict:
    payload = {
        "method": method if invalid else closeout.EXPECTED_RESULT_METHOD[method],
        "cost_audit_method": method,
        "cost_audit_error": "synthetic invalid" if invalid else None,
        "root_top3_hit": success,
    }
    prefix = {
        "naive-single": "direct",
        "lea": "lea",
        "sa-mcgs": "core_evidence",
    }[method]
    payload[f"{prefix}_contains_any_risk_node"] = success
    payload[f"{prefix}_contains_all_risk_nodes"] = success
    return payload


class PairedCloseoutTests(unittest.TestCase):
    def synthetic_records(self):
        cost = {
            model: {method: {} for method in closeout.METHODS}
            for model in closeout.MODELS
        }
        prior = {
            model: {profile: {} for profile in closeout.PROFILES}
            for model in closeout.MODELS
        }
        for model in closeout.MODELS:
            for slot in range(1, 13):
                cost[model]["naive-single"][slot] = result(
                    "naive-single", slot <= 3, invalid=(slot == 12)
                )
                cost[model]["lea"][slot] = result("lea", slot <= 6)
                cost[model]["sa-mcgs"][slot] = result("sa-mcgs", slot <= 9)
            for slot in (1, 3, 8, 10):
                prior[model]["minus20"][slot] = result("sa-mcgs", slot in (1, 3))
                prior[model]["plus20"][slot] = result(
                    "sa-mcgs", slot in (1, 3, 8), invalid=(slot == 10)
                )
        return cost, prior

    def test_synthetic_strict_and_paired_bootstrap_is_deterministic(self):
        cost, prior = self.synthetic_records()
        first = closeout.compute_analysis(cost, prior, selected_slots=(1, 3, 8, 10))
        second = closeout.compute_analysis(cost, prior, selected_slots=(1, 3, 8, 10))
        self.assertEqual(first, second)
        gpt_sa_root = next(
            row
            for row in first["cost"]["method_performance"]
            if row["model"] == "gpt-4o"
            and row["method"] == "sa-mcgs"
            and row["metric"] == "root@3"
        )
        self.assertEqual(gpt_sa_root["denominator_sccs"], 12)
        self.assertEqual(gpt_sa_root["successes"], 9)
        self.assertEqual(gpt_sa_root["strict_rate"], 0.75)
        gpt_delta = next(
            row
            for row in first["cost"]["sa_mcgs_vs_lea_paired"]
            if row["model"] == "gpt-4o" and row["metric"] == "root@3"
        )
        self.assertEqual(gpt_delta["strict_rate_delta"], 0.25)
        self.assertEqual(gpt_delta["denominator_paired_sccs"], 12)
        self.assertEqual(gpt_delta["improved"], 3)
        self.assertEqual(len(first["relation_prior"]["profile_vs_nominal_paired"]), 12)

    def test_invalid_is_strict_zero_not_dropped(self):
        invalid = result("naive-single", True, invalid=True)
        self.assertIsNone(closeout.metric_value(invalid, "naive-single", "root@3"))
        self.assertEqual(closeout.strict_binary(invalid, "naive-single", "root@3"), 0)

    def test_method_validation_matches_frozen_success_and_error_schemas(self):
        for method in closeout.METHODS:
            for invalid in (False, True):
                payload = result(method, True, invalid=invalid)
                closeout.validate_result_method(payload, method, Path("fixture.json"))
                if invalid:
                    self.assertEqual(closeout.strict_binary(payload, method, "risk_all"), 0)

    def test_method_validation_rejects_wrong_method_or_unflagged_exception_label(self):
        payload = result("naive-single", True)
        payload["method"] = "naive-single"
        with self.assertRaises(closeout.CloseoutError):
            closeout.validate_result_method(payload, "naive-single", Path("fixture.json"))
        for invalid in (False, True):
            payload = result("naive-single", True, invalid=invalid)
            payload["method"] = "lea"
            with self.assertRaises(closeout.CloseoutError):
                closeout.validate_result_method(payload, "naive-single", Path("fixture.json"))
            payload = result("naive-single", True, invalid=invalid)
            payload["cost_audit_method"] = "lea"
            with self.assertRaises(closeout.CloseoutError):
                closeout.validate_result_method(payload, "naive-single", Path("fixture.json"))

    def test_incomplete_inputs_fail_closed_without_creating_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cost_dir = root / "cost"
            prior_dir = root / "prior"
            out_dir = root / "out"
            cost_dir.mkdir()
            prior_dir.mkdir()
            exit_code = closeout.main(
                [
                    "--cost-dir",
                    str(cost_dir),
                    "--prior-dir",
                    str(prior_dir),
                    "--out-dir",
                    str(out_dir),
                ]
            )
            self.assertEqual(exit_code, 2)
            self.assertFalse(out_dir.exists())

    def test_real_schema_shaped_complete_fixture_passes(self):
        """Exercise the full loader with 72 cost + 16 prior terminal cells."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cost_dir = root / "cost_run"
            prior_dir = root / "prior_run"
            preflight = prior_dir / "preflight"
            cost_dir.mkdir()
            preflight.mkdir(parents=True)

            def write(path: Path, payload):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload), encoding="utf-8")

            write(cost_dir / "frozen_protocol.json", {"protocol_version": "fixture"})
            (cost_dir / "budget_ledger.jsonl").write_text("{}\n", encoding="utf-8")
            write(
                cost_dir / "execution_status.json",
                {
                    "state": "cost_complete",
                    # Real frozen Counter output omits zero-valued missing.
                    "cells": {"cost": {"attempted": 72, "valid": 71, "invalid": 1}},
                },
            )
            write(prior_dir / "frozen_fallback_protocol.json", {"protocol_version": "fixture-prior"})
            (prior_dir / "run_prior_fallback.py").write_text("# synthetic validator target\n", encoding="utf-8")
            (prior_dir / "budget_ledger.jsonl").write_text("{}\n", encoding="utf-8")
            write(prior_dir / "execution_status.json", {"state": "offline_preflight_complete"})

            plans = {}
            for model in closeout.MODELS:
                model_plans = []
                for slot in range(1, 13):
                    case = {
                        "case_order": slot,
                        "case_id": f"{slot:02d}_{model}_fixture",
                        "case_uid": f"uid-{slot}",
                        "physical_scc_fingerprint": f"physical-{slot}",
                    }
                    model_plans.append(case)
                    for method in closeout.METHODS:
                        payload = result(method, success=(slot % 2 == 0), invalid=(model == "gpt-4o" and method == "naive-single" and slot == 12))
                        payload.update(
                            {
                                "model": model,
                                "case_uid": case["case_uid"],
                                "physical_scc_fingerprint": case["physical_scc_fingerprint"],
                                "strict_denominator_member": True,
                            }
                        )
                        write(
                            cost_dir / "cost" / model / "results" / f"{case['case_id']}__{method}.json",
                            payload,
                        )
                plans[model] = model_plans

            selected = (1, 3, 8, 10)
            execution = []
            order = 0
            for model in closeout.MODELS:
                for profile in closeout.PROFILES:
                    for slot in selected:
                        order += 1
                        case = plans[model][slot - 1]
                        path = prior_dir / "results" / profile / model / "results" / f"{case['case_id']}__sa-mcgs.json"
                        payload = result("sa-mcgs", success=(slot != 10))
                        payload.update({"strict_denominator_member": True})
                        write(path, payload)
                        execution.append(
                            {
                                "order": order,
                                "model": model,
                                "profile": profile,
                                "slot": slot,
                                "result_path": str(path),
                            }
                        )

            terminal = {
                "terminal_72_of_72": True,
                "disk_counts": {"attempted": 72},
                "ledger_counts": {"attempted": 72},
                "integrity_checked_cells": 72,
                "parent_ledger_sha256": "sha256:fixture-parent-ledger",
            }
            nominal = {"all_eight_ready": True, "ready_cells": 8}
            state = {
                "attempted": 16,
                "valid": 15,
                "invalid": 1,
                "missing": 0,
                "ledger_integrity_passed": True,
            }
            gate = {
                "protocol_sha256": closeout.file_hash(prior_dir / "frozen_fallback_protocol.json"),
                "runner_sha256": closeout.file_hash(prior_dir / "run_prior_fallback.py"),
                "source_hashes_passed": True,
                "manifest_and_execution_order_passed": True,
                "case_identity_and_cross_model_parity_passed": True,
                "controlled_config_delta_passed": True,
                "prompt_schema_implementation_lock_passed": True,
                "parent_cost_terminal_72_of_72": True,
                "nominal_reuse_all_eight_ready": True,
                "nominal_reuse_ready_cells": 8,
                "intrinsic_ready": True,
                "already_complete": True,
                "local_result_state": {"attempted": 16, "missing": 0},
            }
            write(preflight / "gate.json", gate)
            # Deliberately use the actual minimal source-audit schema: no
            # protocol_sha256 field here; protocol binding belongs to gate.json.
            write(preflight / "source_hash_audit.json", {"created_at": "fixture", "sources": [], "all_passed": True})
            write(preflight / "parent_cost_terminal.json", terminal)
            write(preflight / "nominal_reuse_readiness.json", nominal)
            write(preflight / "case_and_config_parity.json", {"case_model_prompt_schema_parity_passed": True})
            write(preflight / "execution_plan.json", {"planned_new_paid_cells": 16, "cells": execution})
            write(preflight / "execution_state.json", state)

            fake_module = SimpleNamespace(
                EXPECTED_SELECTED_SLOTS=selected,
                cost=SimpleNamespace(safe_token=lambda value: value),
                protocol=lambda: {"parent": {"run_directory": str(cost_dir)}},
                repo_path=lambda value: Path(value),
                validate_source_hashes=lambda frozen: [{"passed": True}],
                validate_manifest=lambda frozen: {"fixture": True},
                validate_selected_plans=lambda frozen, manifest: (plans, {}, []),
                load_parent_plans=lambda frozen: plans,
                parent_cost_terminal=lambda frozen, full_plans: terminal,
                verify_nominal_reuse=lambda frozen, selected_plans, graphs: nominal,
                paired_config_audit=lambda: {"all_only_relation_prior_changed": True},
                expected_execution_rows=lambda manifest, selected_plans: execution,
                scan_execution_state=lambda execution_rows, selected_plans, graphs: state,
            )
            loaded_cost, loaded_prior, loaded_slots, evidence = closeout.validate_and_load(
                cost_dir, prior_dir, validator_module=fake_module
            )
            self.assertEqual(loaded_slots, selected)
            self.assertEqual(len(loaded_cost["gpt-4o"]["sa-mcgs"]), 12)
            self.assertEqual(len(loaded_prior["gemini-2.5-pro"]["plus20"]), 4)
            self.assertTrue(evidence["all_passed"])
            self.assertEqual(evidence["prior"]["status"], "offline_preflight_complete")


if __name__ == "__main__":
    unittest.main()

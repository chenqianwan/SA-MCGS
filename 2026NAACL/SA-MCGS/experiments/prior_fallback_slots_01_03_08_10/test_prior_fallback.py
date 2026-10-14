from __future__ import annotations

import argparse
import asyncio
import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "prior_fallback_runner", HERE / "run_prior_fallback.py"
)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class FrozenFallbackTests(unittest.TestCase):
    def test_output_directory_and_protocol_are_exact(self) -> None:
        frozen = runner.protocol()
        self.assertEqual(runner.RUN_DIR.name, "prior_fallback_slots_01_03_08_10")
        self.assertEqual(frozen["protocol_version"], "prior_fallback_slots_01_03_08_10_v1")
        self.assertEqual(frozen["scope"]["new_paid_cells"], 16)
        self.assertEqual(frozen["scope"]["nominal_reuse_cells"], 8)

    def test_manifest_is_exact_and_outcome_blind(self) -> None:
        frozen = runner.protocol()
        fallback = runner.validate_manifest(frozen)
        self.assertEqual(fallback["selected_slots"], [1, 3, 8, 10])
        self.assertEqual([row["order"] for row in fallback["execution_order"]], list(range(1, 17)))
        self.assertTrue(fallback["selection_blind_to_results"])
        self.assertTrue(fallback["no_outcome_directed_replacement"])

    def test_only_relation_prior_changes(self) -> None:
        audit = runner.paired_config_audit()
        self.assertTrue(audit["all_only_relation_prior_changed"])
        self.assertEqual(len(audit["rows"]), 4)
        allowed = set(audit["allowed_changed_paths"])
        for row in audit["rows"]:
            self.assertEqual(set(row["changed_paths"]), allowed)

    def test_common_scientific_config_drift_is_rejected(self) -> None:
        original = runner.effective_mcgs_config

        def drifted(model: str, weight: float, **kwargs: object) -> dict[str, object]:
            config = original(model, weight, **kwargs)
            config["alphago_mcgs"]["max_depth"] = 999999
            return config

        with mock.patch.object(runner, "effective_mcgs_config", side_effect=drifted):
            with self.assertRaises(runner.ProtocolError):
                runner.paired_config_audit()

    def test_parent_nominal_config_hashes_match_completed_results(self) -> None:
        expected = {
            "gpt-4o": "sha256:a6def50c76a600b80a933e75e90b8449acdc9f991968ab735279657a866b8b13",
            "gemini-2.5-pro": "sha256:e7944bc85c8ec20454e3297e4b9d3833274085bd8a679b2b7daffb5c1b32b965",
        }
        for model, digest in expected.items():
            self.assertEqual(runner.canonical_hash(runner.parent_nominal_config_payload(model)), digest)

    def test_budget_gate_accepts_synthetic_arithmetic_but_not_paid_authority(self) -> None:
        frozen = runner.protocol()
        projection = {"projected_missing_usd": 40.447019999999995}
        budget = runner.validate_budget_arguments(
            frozen,
            projection,
            authorization_usd=200.0,
            authorization_remaining_usd=100.0,
            closeout_reserve_usd=10.0,
            derived_authorization_remaining_usd=100.0,
        )
        self.assertTrue(budget["passed"])
        too_small = runner.validate_budget_arguments(
            frozen,
            projection,
            authorization_usd=200.0,
            authorization_remaining_usd=50.0,
            closeout_reserve_usd=10.0,
            derived_authorization_remaining_usd=50.0,
        )
        self.assertFalse(too_small["passed"])
        parent_relative = frozen["parent"]["run_directory"]
        real_repo_path = runner.repo_path
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            parent_dir = tmp / "parent"
            parent_dir.mkdir()
            (parent_dir / "budget_ledger.jsonl").write_text(
                json.dumps(
                    {
                        "stage": "cost",
                        "model": "gpt-4o",
                        "method": "naive-single",
                        "case_uid": "synthetic-accounting-fixture",
                        "usage": {
                            "prompt_tokens": 2_000_000,
                            "completion_tokens": 2_000_000,
                        },
                        "xhub_list_estimated_usd": 25.0,
                        "estimated_usd": 50.0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            def temp_repo_path(relative: str) -> Path:
                if relative == parent_relative:
                    return parent_dir
                return real_repo_path(relative)

            with mock.patch.object(runner, "repo_path", side_effect=temp_repo_path), mock.patch.object(
                runner, "LEDGER_PATH", tmp / "absent-fallback-ledger.jsonl"
            ):
                accounting = runner.accounting_provenance(
                    frozen,
                    context_kind="synthetic",
                    fresh_xhub_balance_usd=100.0,
                    fresh_balance_captured_at="synthetic-unit-test",
                    balance_snapshot_path=None,
                    balance_snapshot_sha256=None,
                    upstream_ledgers=[],
                )
        self.assertFalse(accounting["passed"])
        self.assertFalse(accounting["authoritative_for_paid_launch"])
        self.assertEqual(
            {row["role"] for row in accounting["upstream_ledgers"]},
            {"pre", "stage1", "parent"},
        )

    def test_authoritative_accounting_rejects_spoofed_balance_and_remaining(self) -> None:
        frozen = runner.protocol()
        made_up_rejected = False
        try:
            accounting = runner.accounting_provenance(
                frozen,
                context_kind="authoritative",
                fresh_xhub_balance_usd=200.0,
                fresh_balance_captured_at=runner.now_iso(),
                balance_snapshot_path="MADE-UP-REFERENCE",
                balance_snapshot_sha256="sha256:" + "0" * 64,
                upstream_ledgers=[],
            )
        except runner.ProtocolError:
            made_up_rejected = True
        else:
            made_up_rejected = not accounting["authoritative_for_paid_launch"]
        self.assertTrue(made_up_rejected)

        parent_relative = frozen["parent"]["run_directory"]
        real_repo_path = runner.repo_path
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            parent_dir = tmp / "parent"
            parent_dir.mkdir()
            parent_ledger = parent_dir / "budget_ledger.jsonl"
            parent_ledger.write_text(
                json.dumps(
                    {
                        "stage": "cost",
                        "model": "gpt-4o",
                        "method": "naive-single",
                        "case_uid": "parent-accounting-fixture",
                        "usage": {
                            "prompt_tokens": 2_000_000,
                            "completion_tokens": 2_000_000,
                        },
                        "xhub_list_estimated_usd": 25.0,
                        "estimated_usd": 50.0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            own_ledger = tmp / "fallback_ledger.jsonl"
            own_ledger.write_text(
                json.dumps(
                    {
                        "event": "cell_complete",
                        "order": 1,
                        "model": "gpt-4o",
                        "profile": "minus20",
                        "case_uid": "fallback-accounting-fixture",
                        "usage": {
                            "prompt_tokens": 0,
                            "completion_tokens": 500_000,
                        },
                        "estimated_usd": 5.0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            captured_at = datetime.now().astimezone().isoformat()
            snapshot_path = tmp / "balance_snapshot.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "schema_version": "xhub_balance_snapshot.v1",
                        "context_kind": "authoritative",
                        "provider": "XHub",
                        "source": "coordinator_captured_account_balance",
                        "captured_at": captured_at,
                        "total_available_usd": 500.0,
                        "captured_by": frozen["budget"]["balance_snapshot_captured_by"],
                        "authorization_scope_id": frozen["budget"]["authorization_scope_id"],
                    }
                ),
                encoding="utf-8",
            )
            arbitrary_ledger = tmp / "caller-selected-upstream.jsonl"
            arbitrary_ledger.write_text("{}\n", encoding="utf-8")

            def temp_repo_path(relative: str) -> Path:
                if relative == parent_relative:
                    return parent_dir
                return real_repo_path(relative)

            with mock.patch.object(runner, "repo_path", side_effect=temp_repo_path), mock.patch.object(
                runner, "LEDGER_PATH", own_ledger
            ):
                with self.assertRaises(runner.ProtocolError):
                    runner.accounting_provenance(
                        frozen,
                        context_kind="authoritative",
                        fresh_xhub_balance_usd=500.0,
                        fresh_balance_captured_at=captured_at,
                        balance_snapshot_path=str(snapshot_path),
                        balance_snapshot_sha256=runner.file_hash(snapshot_path),
                        upstream_ledgers=[str(arbitrary_ledger)],
                    )
                accounting = runner.accounting_provenance(
                    frozen,
                    context_kind="authoritative",
                    fresh_xhub_balance_usd=500.0,
                    fresh_balance_captured_at=captured_at,
                    balance_snapshot_path=str(snapshot_path),
                    balance_snapshot_sha256=runner.file_hash(snapshot_path),
                    upstream_ledgers=[],
                )
        self.assertTrue(accounting["authoritative_for_paid_launch"])
        self.assertEqual(
            {row["role"] for row in accounting["upstream_ledgers"]},
            {"pre", "stage1", "parent"},
        )
        self.assertEqual(accounting["fallback_ledger"]["role"], "fallback")
        self.assertEqual(
            {row["role"] for row in accounting["all_accounting_ledgers"]},
            {"pre", "stage1", "parent", "fallback"},
        )
        self.assertAlmostEqual(
            accounting["derived_authorization_remaining_usd"],
            200.0 - 34.63448 - 47.381175 - 25.0 - 5.0,
        )

        spoofed_remaining = runner.validate_budget_arguments(
            frozen,
            {"projected_missing_usd": 70.0},
            authorization_usd=200.0,
            authorization_remaining_usd=200.0,
            closeout_reserve_usd=10.0,
            derived_authorization_remaining_usd=accounting[
                "derived_authorization_remaining_usd"
            ],
        )
        self.assertFalse(spoofed_remaining["passed"])

    def test_snapshot_ttl_expires_only_at_new_invocation_boundary(self) -> None:
        frozen = runner.protocol()
        ttl_seconds = float(frozen["budget"]["balance_snapshot_ttl_seconds"])
        captured_at = (
            datetime.now().astimezone() - timedelta(seconds=ttl_seconds + 120)
        ).isoformat()

        with tempfile.TemporaryDirectory() as raw_tmp:
            snapshot_path = Path(raw_tmp) / "aged_balance_snapshot.json"
            payload = {
                "schema_version": "xhub_balance_snapshot.v1",
                "context_kind": "authoritative",
                "provider": "XHub",
                "source": "coordinator_captured_account_balance",
                "captured_at": captured_at,
                "total_available_usd": 500.0,
                "captured_by": frozen["budget"]["balance_snapshot_captured_by"],
                "authorization_scope_id": frozen["budget"]["authorization_scope_id"],
            }
            snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
            snapshot_sha256 = runner.file_hash(snapshot_path)
            common = {
                "context_kind": "authoritative",
                "snapshot_path": str(snapshot_path),
                "snapshot_sha256": snapshot_sha256,
                "asserted_balance_usd": 500.0,
                "asserted_captured_at": captured_at,
            }

            with self.assertRaises(runner.ProtocolError):
                runner.validate_balance_snapshot(
                    frozen,
                    validation_mode="invocation_start",
                    expected_launch_snapshot_sha256=None,
                    **common,
                )

            same_invocation = runner.validate_balance_snapshot(
                frozen,
                validation_mode="same_invocation_per_cell",
                expected_launch_snapshot_sha256=snapshot_sha256,
                **common,
            )
            self.assertTrue(same_invocation["passed"])
            self.assertGreater(same_invocation["age_seconds"], ttl_seconds)

            with self.assertRaises(runner.ProtocolError):
                runner.validate_balance_snapshot(
                    frozen,
                    validation_mode="same_invocation_per_cell",
                    expected_launch_snapshot_sha256="sha256:" + "0" * 64,
                    **common,
                )

            payload["provider"] = "not-XHub"
            snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
            tampered_hash = runner.file_hash(snapshot_path)
            with self.assertRaises(runner.ProtocolError):
                runner.validate_balance_snapshot(
                    frozen,
                    validation_mode="same_invocation_per_cell",
                    expected_launch_snapshot_sha256=tampered_hash,
                    **{
                        **common,
                        "snapshot_sha256": tampered_hash,
                    },
                )

    def test_parent_terminal_rejects_arbitrary_json_with_spoofed_status_and_ledger(self) -> None:
        frozen = runner.protocol()
        full_plans = runner.load_parent_plans(frozen)
        parent_relative = frozen["parent"]["run_directory"]
        real_repo_path = runner.repo_path
        arbitrary_payload: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as raw_tmp:
            parent_dir = Path(raw_tmp)
            ledger_rows = []
            for model in runner.MODELS:
                result_dir = parent_dir / "cost" / runner.cost.safe_token(model) / "results"
                result_dir.mkdir(parents=True, exist_ok=True)
                for case in full_plans[model]:
                    for method in runner.PARENT_METHODS:
                        result_path = (
                            result_dir
                            / f"{case['case_id']}__{runner.cost.safe_token(method)}.json"
                        )
                        result_path.write_text("{}", encoding="utf-8")
                        ledger_rows.append(
                            {
                                "stage": "cost",
                                "model": model,
                                "method": method,
                                "case_id": case["case_id"],
                                "case_slot": case["case_order"],
                                "case_uid": case["case_uid"],
                                "physical_scc_fingerprint": case[
                                    "physical_scc_fingerprint"
                                ],
                                "valid": True,
                                "error_type": None,
                                "usage": {},
                                "estimated_usd": 0.0,
                                "xhub_list_estimated_usd": 0.0,
                                "result_sha256_before_write": runner.canonical_hash(
                                    arbitrary_payload
                                ),
                            }
                        )
            (parent_dir / "budget_ledger.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in ledger_rows),
                encoding="utf-8",
            )
            (parent_dir / "execution_status.json").write_text(
                json.dumps(
                    {
                        "state": "cost_complete",
                        "cells": {
                            "cost": {
                                "attempted": 72,
                                "missing": 0,
                                "valid": 72,
                                "invalid": 0,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            def temp_repo_path(relative: str) -> Path:
                if relative == parent_relative:
                    return parent_dir
                return real_repo_path(relative)

            dummy_graphs = {
                model: {case["domain"]: object() for case in full_plans[model]}
                for model in runner.MODELS
            }
            with mock.patch.object(
                runner, "repo_path", side_effect=temp_repo_path
            ), mock.patch.object(
                runner.cost,
                "load_graphs",
                side_effect=lambda cases: dummy_graphs[str(cases[0]["model"])],
            ):
                with self.assertRaises(runner.ProtocolError):
                    runner.parent_cost_terminal(frozen, full_plans)

    def test_nominal_outcome_tamper_is_rejected_by_parent_ledger_hash(self) -> None:
        frozen = runner.protocol()
        full_plans = runner.load_parent_plans(frozen)
        plans = {
            model: [
                row
                for row in full_plans[model]
                if int(row["case_order"]) in runner.EXPECTED_SELECTED_SLOTS
            ]
            for model in runner.MODELS
        }
        graphs = {
            model: {case["domain"]: object() for case in plans[model]}
            for model in runner.MODELS
        }
        model = "gpt-4o"
        case = next(row for row in plans[model] if int(row["case_order"]) == 1)
        original_path = runner.parent_nominal_path(model, case, frozen)
        original_lookup = runner.parent_nominal_path

        with tempfile.TemporaryDirectory() as raw_tmp:
            tampered_path = Path(raw_tmp) / original_path.name
            payload = runner.load_json(original_path)
            payload["root_top3_hit"] = not bool(payload.get("root_top3_hit"))
            tampered_path.write_text(json.dumps(payload), encoding="utf-8")

            def nominal_lookup(
                candidate_model: str, candidate_case: dict[str, object], protocol: dict[str, object]
            ) -> Path:
                if candidate_model == model and int(candidate_case["case_order"]) == 1:
                    return tampered_path
                return original_lookup(candidate_model, candidate_case, protocol)

            with mock.patch.object(
                runner, "parent_nominal_path", side_effect=nominal_lookup
            ), mock.patch.object(runner.cost, "validate_result_case_identity", return_value={}):
                with self.assertRaises(runner.ProtocolError):
                    runner.verify_nominal_reuse(frozen, plans, graphs)

    def test_local_result_tamper_is_rejected_by_complete_ledger_hash(self) -> None:
        frozen = runner.protocol()
        fallback = runner.validate_manifest(frozen)
        full_plans = runner.load_parent_plans(frozen)
        plans = {
            model: [
                row
                for row in full_plans[model]
                if int(row["case_order"]) in runner.EXPECTED_SELECTED_SLOTS
            ]
            for model in runner.MODELS
        }
        graphs = {
            model: {case["domain"]: object() for case in plans[model]}
            for model in runner.MODELS
        }
        execution = runner.expected_execution_rows(fallback, plans)
        first = execution[0]
        model = str(first["model"])
        case = next(
            row for row in plans[model] if int(row["case_order"]) == int(first["slot"])
        )
        result = runner.load_json(runner.parent_nominal_path(model, case, frozen))
        runner.attach_protocol_fields(result, cell=first, case=case)

        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            results_dir = tmp / "results"
            ledger_path = tmp / "budget_ledger.jsonl"
            execution_fixture = copy.deepcopy(execution)
            for row in execution_fixture:
                selected_case = next(
                    item
                    for item in plans[str(row["model"])]
                    if int(item["case_order"]) == int(row["slot"])
                )
                row["result_path"] = str(
                    results_dir
                    / str(row["profile"])
                    / runner.cost.safe_token(str(row["model"]))
                    / "results"
                    / f"{selected_case['case_id']}__sa-mcgs.json"
                )
            first_fixture = execution_fixture[0]
            result_path = Path(first_fixture["result_path"])
            result_path.parent.mkdir(parents=True)
            result_path.write_text(json.dumps(result), encoding="utf-8")

            invocation_id = "fallback-unit-test-invocation"
            protocol_sha = runner.file_hash(runner.PROTOCOL_PATH)
            runner_sha = runner.file_hash(Path(runner.__file__).resolve())
            receipt_path = (tmp / "launch_receipt.json").resolve()
            receipt_path.write_text(
                json.dumps(
                    {
                        "receipt_version": "prior_fallback_launch_receipt_v1",
                        "invocation_id": invocation_id,
                        "protocol_version": frozen["protocol_version"],
                        "protocol_sha256": protocol_sha,
                        "runner_sha256": runner_sha,
                        "fallback_manifest_sha256": frozen["selection"][
                            "source_manifest_sha256"
                        ],
                        "parent_protocol_sha256": frozen["parent"][
                            "frozen_protocol_sha256"
                        ],
                        "next_execution_order": int(first_fixture["order"]),
                        "paid_execution_explicitly_authorized": True,
                    }
                ),
                encoding="utf-8",
            )
            usage = result.get("llm_usage_summary") or {}
            ledger_rows = [
                {
                    "event": "run_invocation_start",
                    "invocation_id": invocation_id,
                    "protocol_sha256": protocol_sha,
                    "runner_sha256": runner_sha,
                    "launch_receipt": str(receipt_path),
                    "launch_receipt_sha256": runner.file_hash(receipt_path),
                    "paid_execution_explicitly_authorized": True,
                },
                {
                    "event": "cell_start",
                    "invocation_id": invocation_id,
                    "order": int(first_fixture["order"]),
                    "model": model,
                    "profile": first_fixture["profile"],
                    "slot": int(first_fixture["slot"]),
                    "case_id": case["case_id"],
                    "case_uid": case["case_uid"],
                    "result_path": str(result_path),
                },
                {
                    "event": "cell_complete",
                    "invocation_id": invocation_id,
                    "order": int(first_fixture["order"]),
                    "model": model,
                    "profile": first_fixture["profile"],
                    "slot": int(first_fixture["slot"]),
                    "case_id": case["case_id"],
                    "case_uid": case["case_uid"],
                    "valid": not bool(result.get("cost_audit_error")),
                    "error_type": result.get("error_type"),
                    "usage": usage,
                    "estimated_usd": runner.estimate_usd(model, usage, frozen),
                    "result_path": str(result_path),
                    "result_sha256": runner.file_hash(result_path),
                    "invalid_is_terminal": True,
                    "automatic_retry_permitted": False,
                },
            ]
            ledger_path.write_text(
                "".join(json.dumps(row) + "\n" for row in ledger_rows),
                encoding="utf-8",
            )
            with mock.patch.object(runner, "RESULTS_DIR", results_dir), mock.patch.object(
                runner, "LEDGER_PATH", ledger_path
            ), mock.patch.object(runner.cost, "validate_result_case_identity", return_value={}):
                baseline = runner.scan_execution_state(execution_fixture, plans, graphs)
                self.assertEqual(baseline["attempted"], 1)
                tampered = runner.load_json(result_path)
                tampered["root_top3_hit"] = not bool(tampered.get("root_top3_hit"))
                result_path.write_text(json.dumps(tampered), encoding="utf-8")
                with self.assertRaises(runner.ProtocolError):
                    runner.scan_execution_state(execution_fixture, plans, graphs)

    def test_out_of_order_resume_is_rejected(self) -> None:
        runner.assert_contiguous_orders([1, 2, 3])
        with self.assertRaises(runner.ProtocolError):
            runner.assert_contiguous_orders([1, 3])
        with self.assertRaises(runner.ProtocolError):
            runner.assert_contiguous_orders([2])

    def test_paid_path_requires_explicit_flag_before_preflight_or_llm(self) -> None:
        args = argparse.Namespace(
            execute_paid_cells=False,
            max_new_cells=None,
            global_authorization_usd=200.0,
            global_authorization_remaining_usd=100.0,
            closeout_reserve_usd=10.0,
            accounting_context_kind="authoritative",
            fresh_xhub_balance_usd=100.0,
            fresh_balance_captured_at="test",
            upstream_ledger=[],
        )
        with mock.patch.object(runner, "perform_preflight") as preflight, mock.patch.object(
            runner.cost, "make_llm"
        ) as make_llm:
            with self.assertRaises(runner.ProtocolError):
                asyncio.run(runner.execute_paid_run(args))
        preflight.assert_not_called()
        make_llm.assert_not_called()

    def test_full_offline_preflight_never_constructs_llm(self) -> None:
        with mock.patch.object(
            runner.cost, "make_llm", side_effect=AssertionError("offline path touched LLM")
        ) as make_llm:
            result = runner.perform_preflight(command="preflight_test")
        make_llm.assert_not_called()
        self.assertTrue(result["gate"]["source_hashes_passed"])
        self.assertFalse(result["gate"]["offline_command_made_model_or_xhub_calls"])


if __name__ == "__main__":
    unittest.main()

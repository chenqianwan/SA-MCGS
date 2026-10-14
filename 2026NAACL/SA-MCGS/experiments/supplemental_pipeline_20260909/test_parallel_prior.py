"""Synthetic, zero-network tests for the outer prior scheduler.

Only temporary artifacts are written. No real worker/coordinator is launched.
"""
import ast
import copy
import importlib.util
import json
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PATH = Path(__file__).with_name("parallel_prior.py")
spec = importlib.util.spec_from_file_location("parallel_prior_under_test", PATH)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.execution = [{"order": i, "model": "m1" if i < 4 else "m2"}
                          for i in range(1, 7)]
        self.caps = {"m1": 7.0, "m2": 5.0}

    def test_includes_active_pending_and_entire_undispatched_tail(self):
        jobs = {
            1: {"completion": {"estimated_usd": 99.0}},  # Already in ledger.
            2: {"cap": 7.0},  # Active reservation.
            3: {"cap": 7.0, "completion": {"estimated_usd": 2.0,
                                            "budget_spend_upper_bound_usd": 4.0}},
            4: {"cap": 5.0},
        }
        # Orders 2+3+4+5+6, plus the fixed closeout reserve.
        self.assertEqual(p.budget_needed(self.execution, 1, jobs, self.caps),
                         7.0 + 4.0 + 5.0 + 5.0 + 5.0 + 10.0)

    def test_no_worker_does_not_mean_zero_tail(self):
        self.assertEqual(p.budget_needed(self.execution, 1, {}, self.caps),
                         7.0 + 7.0 + 5.0 + 5.0 + 5.0 + 10.0)

    def test_unknown_failure_cost_is_reserved_until_canonical_commit(self):
        jobs = {2: {"completion": {"estimated_usd": 0.0,
                                   "budget_spend_upper_bound_usd": 6.5}}}
        self.assertEqual(p.budget_needed(self.execution[:2], 1, jobs, self.caps), 16.5)

    def test_legacy_completion_without_upper_bound_retains_observed_cost(self):
        jobs = {2: {"completion": {"estimated_usd": 2.5}}}
        self.assertEqual(p.budget_needed(self.execution[:2], 1, jobs, self.caps), 12.5)

    def test_upper_bound_cannot_reduce_observed_cost(self):
        jobs = {2: {"completion": {"estimated_usd": 3.0,
                                   "budget_spend_upper_bound_usd": 1.0}}}
        self.assertEqual(p.budget_needed(self.execution[:2], 1, jobs, self.caps), 13.0)

    def test_completed_grid_keeps_closeout_reserve(self):
        self.assertEqual(p.budget_needed(self.execution, 6, {}, self.caps), 10.0)

    def test_exact_available_budget_is_accepted(self):
        p.require_budget(25.0, 25.0, 25.0)

    def test_insufficient_authorization_is_rejected(self):
        with self.assertRaises(RuntimeError):
            p.require_budget(25.0, 24.99, 200.0)

    def test_insufficient_shared_balance_is_rejected(self):
        with self.assertRaises(RuntimeError):
            p.require_budget(25.0, 200.0, 24.99)

    def test_nonfinite_and_negative_each_input_are_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), -0.01):
            for index in range(3):
                with self.subTest(value=value, index=index):
                    inputs = [25.0, 100.0, 100.0]
                    inputs[index] = value
                    with self.assertRaises(RuntimeError):
                        p.require_budget(*inputs)

    def test_reserved_amount_rejects_nonfinite_negative_low_and_over_cap(self):
        for upper in (float("nan"), float("inf"), -1.0, 1.0, 8.0, True, None, "2.0"):
            with self.subTest(upper=upper):
                with self.assertRaises(RuntimeError):
                    p.validate_reserved_amount(upper, 1.25, 7.0)
        p.validate_reserved_amount(1.25, 1.25, 7.0)
        p.validate_reserved_amount(7.0, 1.25, 7.0)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.worker_dir = self.root / "worker"
        self.worker_dir.mkdir()
        self.official = self.root / "official/m1/low/results/case.json"
        self.protocol = self.root / "protocol.json"
        self.protocol.write_text('{"protocol": "synthetic"}')
        self.runner = self.root / "frozen_runner.py"
        self.runner.write_text("# Synthetic frozen source, never executed.\n")
        self.worker_source = self.root / "worker.py"
        self.worker_source.write_text("# Synthetic isolated worker, never executed.\n")
        self.amendment = self.root / "amendment.json"
        self.amendment.write_text('{"outer_process_concurrency": 4}')
        self.events = []
        self.mock_runner = SimpleNamespace(
            EXPECTED_PROTOCOL_VERSION="synthetic.v1", PROTOCOL_PATH=self.protocol,
            __file__=str(self.runner), append_ledger=lambda row: self.events.append(copy.deepcopy(row)),
            validate_local_result=Mock(), estimate_usd=Mock(return_value=1.25),
        )
        self.cell = {"order": 1, "model": "m1", "profile": "low", "slot": 1,
                     "case_id": "case-1", "case_uid": "sha256:case-1",
                     "result_path": str(self.official)}
        self.case = {"domain": "SEC", "case_id": "case-1", "case_uid": "sha256:case-1"}
        self.pre = {"frozen": {"selection": {"source_manifest_sha256": "sha256:manifest"},
                               "parent": {"frozen_protocol_sha256": "sha256:parent"}},
                    "graphs": {"m1": {"SEC": "synthetic-graph"}}}
        self.accounting = {"derived_authorization_remaining_usd": 80.0,
                           "validated_cumulative_spend_usd": 120.0}
        self.snapshot = {"synthetic": True}
        self.patchers = [patch.object(p, "WORK", self.root / "parallel"),
                         patch.object(p, "WORKER", self.worker_source),
                         patch.object(p, "AMENDMENT", self.amendment)]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_job(self, invalid=False):
        pending = self.worker_dir / "pending_result.json"
        ticket = self.worker_dir / "ticket.json"
        p.save(ticket, {"cell": self.cell, "worker_spend_cap_usd": 7.0})
        guard = {"budget_spend_upper_bound_usd": 2.0,
                 "unobserved_failure_reserve_usd": 0.75}
        result = {"llm_usage_summary": {"prompt_tokens": 10, "completion_tokens": 5},
                  "outer_scheduling": {"outer_process_concurrency": 4,
                      "ticket_sha256": p.digest(ticket), "amendment_sha256": p.digest(self.amendment)},
                  "budget_guard": guard}
        if invalid:
            result.update(cost_audit_error="Synthetic terminal failure", error_type="BudgetStop")
        # Non-default formatting ensures commit copies exact bytes, not JSON content only.
        pending.write_text(json.dumps(result, separators=(",", ":")) + "\n")
        with patch.object(p, "now", return_value="2026-09-09T20:00:00+08:00"):
            invocation, receipt = p.receipt_for(
                self.mock_runner, self.pre, self.cell, self.accounting, 50.0,
                self.snapshot, self.worker_dir / "ticket.json")
        receipt_path = self.worker_dir / "receipt.json"
        p.save(receipt_path, receipt)
        completion = {"order": 1, "result_path": str(pending),
                      "result_sha256": p.digest(pending), "usage": result["llm_usage_summary"],
                      "estimated_usd": 1.25, "valid": not invalid,
                      "error_type": result.get("error_type"),
                      "actual_started_at": "2026-09-09T20:01:00+08:00",
                      "actual_completed_at": "2026-09-09T20:05:00+08:00",
                      "budget_guard": guard, "budget_spend_upper_bound_usd": 2.0,
                      "unobserved_failure_reserve_usd": 0.75,
                      "ticket_sha256": p.digest(ticket),
                      "amendment_sha256": p.digest(self.amendment)}
        p.save(self.worker_dir / "completion.json", completion)
        return {"cell": self.cell, "case": self.case, "directory": self.worker_dir,
                "receipt": receipt_path, "completion": completion, "cap": 7.0}

    def test_receipt_binds_frozen_identity_and_actual_authorization(self):
        job = self.make_job()
        receipt = p.read(job["receipt"])
        self.assertEqual(receipt["receipt_version"], "prior_fallback_launch_receipt_v1")
        self.assertEqual(receipt["protocol_version"], "synthetic.v1")
        self.assertEqual(receipt["protocol_sha256"], p.digest(self.protocol))
        self.assertEqual(receipt["runner_sha256"], p.digest(self.runner))
        self.assertEqual(receipt["worker_sha256"], p.digest(self.worker_source))
        self.assertEqual(receipt["dispatcher_sha256"], p.digest(PATH))
        self.assertEqual(receipt["amendment_sha256"], p.digest(self.amendment))
        self.assertEqual(receipt["fallback_manifest_sha256"], "sha256:manifest")
        self.assertEqual(receipt["parent_protocol_sha256"], "sha256:parent")
        self.assertEqual(receipt["accounting_provenance"], self.accounting)
        self.assertEqual(receipt["fresh_balance_snapshot"], self.snapshot)
        self.assertEqual(receipt["global_authorization_remaining_usd_derived_at_invocation"], 80.0)
        self.assertEqual(receipt["required_including_closeout_usd"], 50.0)
        self.assertEqual(receipt["closeout_reserve_usd"], 10.0)
        self.assertEqual(receipt["next_execution_order"], 1)
        self.assertEqual(receipt["max_new_cells"], 1)
        self.assertIs(receipt["paid_execution_explicitly_authorized"], True)

    def test_commit_exact_bytes_identity_receipt_hash_and_distinct_actual_times(self):
        job = self.make_job()
        raw_before = Path(job["completion"]["result_path"]).read_bytes()
        with patch.object(p, "now", return_value="2026-09-09T20:10:00+08:00"):
            p.commit_job(self.mock_runner, job)
        self.assertEqual(self.official.read_bytes(), raw_before)
        self.assertEqual([row["event"] for row in self.events],
                         ["run_invocation_start", "cell_start", "cell_complete"])
        invocation, start, finish = self.events
        receipt = p.read(job["receipt"])
        self.assertEqual(invocation["launch_receipt_sha256"], p.digest(job["receipt"]))
        self.assertEqual(invocation["protocol_sha256"], receipt["protocol_sha256"])
        self.assertEqual(invocation["runner_sha256"], receipt["runner_sha256"])
        for row in self.events:
            self.assertEqual(row["invocation_id"], receipt["invocation_id"])
            self.assertEqual(row["recorded_at"], "2026-09-09T20:10:00+08:00")
        for row in (start, finish):
            for key in ("order", "model", "profile", "slot", "case_id", "case_uid"):
                self.assertEqual(row[key], self.cell[key])
            self.assertEqual(row["result_path"], str(self.official.resolve()))
        self.assertEqual(invocation["actual_invocation_started_at"], receipt["created_at"])
        self.assertEqual(start["actual_started_at"], job["completion"]["actual_started_at"])
        self.assertEqual(finish["actual_completed_at"], job["completion"]["actual_completed_at"])
        self.assertIs(start["materialized_after_worker_completion"], True)
        self.assertEqual(finish["result_sha256"], p.digest(self.official))
        self.assertEqual(finish["usage"], job["completion"]["usage"])
        self.assertEqual(finish["estimated_usd"], 1.25)
        self.assertIs(finish["valid"], True)
        self.assertIs(finish["automatic_retry_permitted"], False)
        journal = p.read(self.root / "parallel/events.jsonl")
        self.assertEqual(journal["event"], "canonical_prefix_committed")
        self.assertEqual(journal["result_sha256"], p.digest(self.official))

    def test_invalid_completion_is_committed_once_not_retried_or_dropped(self):
        job = self.make_job(invalid=True)
        p.commit_job(self.mock_runner, job)
        self.assertIs(self.events[-1]["valid"], False)
        self.assertEqual(self.events[-1]["error_type"], "BudgetStop")
        self.assertIs(self.events[-1]["invalid_is_terminal"], True)
        self.assertIs(self.events[-1]["automatic_retry_permitted"], False)
        self.assertEqual(p.read(self.official)["cost_audit_error"], "Synthetic terminal failure")

    def test_existing_official_result_refuses_overwrite_before_any_ledger_write(self):
        job = self.make_job()
        self.official.parent.mkdir(parents=True)
        self.official.write_bytes(b"existing authoritative result\n")
        with self.assertRaisesRegex(RuntimeError, "overwrite"):
            p.commit_job(self.mock_runner, job)
        self.assertEqual(self.events, [])
        self.assertEqual(self.official.read_bytes(), b"existing authoritative result\n")

    def test_completion_validates_result_and_usage_cost_before_commit(self):
        job = self.make_job()
        verified = p.validate_completion(self.mock_runner, self.pre, job)
        self.assertEqual(verified, job["completion"])
        self.mock_runner.validate_local_result.assert_called_once_with(
            p.read(self.worker_dir / "pending_result.json"), cell=self.cell,
            case=self.case, graph="synthetic-graph")
        self.assertFalse(self.official.exists())

    def test_completion_rejects_modified_result_bytes(self):
        job = self.make_job()
        (self.worker_dir / "pending_result.json").write_text('{}\n')
        with self.assertRaisesRegex(RuntimeError, "hash/path"):
            p.validate_completion(self.mock_runner, self.pre, job)

    def test_completion_rejects_wrong_path_order_usage_validity_or_observed_cap(self):
        changes = [({"result_path": str(self.root / "elsewhere.json")}, "hash/path"),
                   ({"order": 2}, "wrong execution order"),
                   ({"usage": {}}, "usage/cost"),
                   ({"estimated_usd": 3.0}, "usage/cost"),
                   ({"valid": False}, "validity")]
        for update, message in changes:
            with self.subTest(update=update):
                job = self.make_job()
                malformed = {**job["completion"], **update}
                p.save(self.worker_dir / "completion.json", malformed)
                with self.assertRaisesRegex(RuntimeError, message):
                    p.validate_completion(self.mock_runner, self.pre, job)
        job = self.make_job()
        job["cap"] = 1.0
        with self.assertRaisesRegex(RuntimeError, "reserved cap"):
            p.validate_completion(self.mock_runner, self.pre, job)

    def test_completion_cannot_hide_outer_parallel_schedule(self):
        job = self.make_job()
        pending = self.worker_dir / "pending_result.json"
        result = p.read(pending)
        result["outer_scheduling"] = {}
        p.save(pending, result)
        job["completion"]["result_sha256"] = p.digest(pending)
        p.save(self.worker_dir / "completion.json", job["completion"])
        with self.assertRaisesRegex(RuntimeError, "outer parallel schedule"):
            p.validate_completion(self.mock_runner, self.pre, job)

    def test_completion_rejects_invalid_reservations_before_commit(self):
        for upper in (float("nan"), float("inf"), -1.0, 1.0, 8.0, True, None):
            with self.subTest(upper=upper):
                job = self.make_job()
                job["completion"]["budget_spend_upper_bound_usd"] = upper
                p.save(self.worker_dir / "completion.json", job["completion"])
                with self.assertRaises(RuntimeError):
                    p.validate_completion(self.mock_runner, self.pre, job)
                self.assertFalse(self.official.exists())

    def test_completion_rejects_guard_unknown_and_ticket_amendment_binding_drift(self):
        changes = [({"budget_guard": {}}, "budget guard"),
                   ({"unobserved_failure_reserve_usd": 0.5}, "billing reservation"),
                   ({"ticket_sha256": "sha256:wrong"}, "ticket/amendment"),
                   ({"amendment_sha256": "sha256:wrong"}, "ticket/amendment")]
        for update, message in changes:
            with self.subTest(update=update):
                job = self.make_job()
                p.save(self.worker_dir / "completion.json", {**job["completion"], **update})
                with self.assertRaisesRegex(RuntimeError, message):
                    p.validate_completion(self.mock_runner, self.pre, job)

    def legacy_validators(self):
        """Execute unchanged validator function ASTs without importing API clients."""
        source = PATH.parent.parent / "prior_fallback_slots_01_03_08_10/run_prior_fallback.py"
        names = {"load_json_object", "exact_int", "same_number", "assert_contiguous_orders",
                 "validate_launch_receipt", "local_ledger_identity_checks", "scan_execution_state"}
        tree = ast.parse(source.read_text())
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual({node.name for node in selected}, names)
        subset = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                                  *selected], type_ignores=[])
        ast.fix_missing_locations(subset)
        frozen = {"protocol_version": "synthetic.v1", **self.pre["frozen"]}
        scope = {"Path": Path, "json": json, "defaultdict": defaultdict, "ProtocolError": RuntimeError,
                 "protocol": lambda: frozen, "file_hash": p.digest, "load_json": p.read,
                 "__file__": str(self.runner), "PROTOCOL_PATH": self.protocol,
                 "RESULTS_DIR": self.root / "official", "iter_ledger": lambda: self.events,
                 "validate_local_result": self.mock_runner.validate_local_result,
                 "estimate_usd": self.mock_runner.estimate_usd}
        exec(compile(subset, str(source), "exec"), scope)
        return scope

    def test_canonical_commit_passes_unchanged_legacy_receipt_and_ledger_validators(self):
        job = self.make_job(invalid=True)
        p.commit_job(self.mock_runner, job)
        validators = self.legacy_validators()
        state = validators["scan_execution_state"](
            [self.cell], {"m1": [{**self.case, "case_order": 1}]}, self.pre["graphs"])
        self.assertEqual(state["attempted"], 1)
        self.assertEqual(state["invalid"], 1)
        self.assertEqual(state["launch_receipts_verified"], 1)
        self.assertIs(state["ledger_integrity_passed"], True)
        self.assertEqual(state["ledger_events"], 3)

    def test_legacy_validator_rejects_altered_receipt_and_finish_identity(self):
        job = self.make_job()
        p.commit_job(self.mock_runner, job)
        validators = self.legacy_validators()
        self.events[-1]["case_uid"] = "sha256:wrong"
        with self.assertRaisesRegex(RuntimeError, "identity failure"):
            validators["scan_execution_state"](
                [self.cell], {"m1": [{**self.case, "case_order": 1}]}, self.pre["graphs"])
        self.events[-1]["case_uid"] = self.cell["case_uid"]
        receipt = p.read(job["receipt"])
        receipt["next_execution_order"] = 2
        p.save(job["receipt"], receipt)
        with self.assertRaisesRegex(RuntimeError, "receipt binding failure"):
            validators["scan_execution_state"](
                [self.cell], {"m1": [{**self.case, "case_order": 1}]}, self.pre["graphs"])


if __name__ == "__main__":
    unittest.main()

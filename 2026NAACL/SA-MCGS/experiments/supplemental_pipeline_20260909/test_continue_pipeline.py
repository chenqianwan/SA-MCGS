"""No-network orchestration tests; paid runner is mocked in every case."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).with_name("continue_pipeline.py")
spec = importlib.util.spec_from_file_location("supplemental_pipeline", PATH)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PipelineTests(unittest.TestCase):
    def test_counter_omits_zero_missing_at_completion(self):
        payload = {"state": "cost_complete", "cells": {"cost": {
            "attempted": 72, "valid": 69, "invalid": 3}}}
        self.assertTrue(p.cost_ready(payload))
        payload["cells"]["cost"]["missing"] = 1
        self.assertFalse(p.cost_ready(payload))

    def test_absent_missing_cannot_hide_incomplete_results(self):
        payload = {"state": "cost_complete", "cells": {"cost": {
            "attempted": 71, "valid": 68, "invalid": 3}}}
        self.assertFalse(p.cost_ready(payload))
        payload["cells"]["cost"]["attempted"] = 72
        self.assertFalse(p.cost_ready(payload))

    def test_stopped_complete_cost_can_continue_with_counter_shape(self):
        payload = {"state": "cost_complete", "cells": {"cost": {
            "attempted": 72, "valid": 69, "invalid": 3}}}
        with patch.object(p, "load", return_value=payload), \
             patch.object(p, "matching_cost_process", return_value=False), \
             patch.object(p, "state") as state:
            p.wait_for_cost(123)
        self.assertEqual(state.call_args.args[0], "cost_complete_verified_by_status")

    def test_terminal_requires_complete_state_and_strict_counts(self):
        payload = {"state": "cost_complete", "cells": {"cost": {
            "attempted": 72, "missing": 0, "valid": 69, "invalid": 3}}}
        self.assertTrue(p.cost_ready(payload))
        payload["state"] = "cost_running"
        self.assertFalse(p.cost_ready(payload))
        payload["state"] = "cost_complete"
        payload["cells"]["cost"]["invalid"] = 0
        self.assertFalse(p.cost_ready(payload))

    def test_identity_gate_stops_before_balance_or_paid_launch(self):
        with patch.object(p, "load", return_value={"intrinsic_ready": False}), \
             patch.object(p, "run_cli") as cli, patch.object(p, "capture_balance") as balance:
            with self.assertRaises(RuntimeError):
                p.continue_prior()
            cli.assert_called_once_with("preflight")
            balance.assert_not_called()

    def drive(self, *, ready=True, balance=800, already=False):
        initial = {"intrinsic_ready": True, "already_complete": False,
                   "accounting_provenance": {"derived_authorization_remaining_usd": 80}}
        complete = {"intrinsic_ready": True, "already_complete": True,
                    "local_result_state": {"attempted": 16, "valid": 15, "invalid": 1, "missing": 0},
                    "accounting_provenance": {"validated_cumulative_spend_usd": 140}}
        launch = {"ready_for_paid_run": ready,
                  "budget_gate": {"required_including_closeout_usd": 50},
                  "local_result_state": {"next_order": 16}}
        sequence = [complete] if already else [initial, launch, complete]
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text("{}")
            with patch.object(p, "load", side_effect=sequence), \
                 patch.object(p, "run_cli") as cli, patch.object(p, "state") as status, \
                 patch.object(p, "run_closeout", return_value="synthetic_closeout"), \
                 patch.object(p, "capture_balance", return_value=(snapshot, {
                     "captured_at": "2026-09-09T12:00:00+08:00", "total_available_usd": balance})) as capture:
                if ready and (balance >= p.BALANCE_FLOOR + 50 or already):
                    p.continue_prior()
                    self.assertEqual(status.call_args.args[0], "paid_experiments_complete_labels_pending")
                    self.assertEqual(status.call_args.kwargs["prior_cells"]["invalid"], 1)
                else:
                    with self.assertRaises(RuntimeError):
                        p.continue_prior()
                return cli.call_args_list, capture.call_count

    def test_budget_failure_cannot_launch_paid_cell(self):
        calls, _ = self.drive(ready=False)
        self.assertFalse(any(call.args[0] == "run" for call in calls))

    def test_shared_balance_floor_stops_paid_cell(self):
        calls, _ = self.drive(balance=720)
        self.assertFalse(any(call.args[0] == "run" for call in calls))

    def test_one_terminal_cell_then_final_report_preserves_invalid(self):
        calls, _ = self.drive()
        paid = [call for call in calls if call.args[0] == "run"]
        self.assertEqual(len(paid), 1)
        self.assertEqual(paid[0].args[-3:], ("--execute-paid-cells", "--max-new-cells", "1"))

    def test_complete_resume_does_not_call_balance_or_model(self):
        calls, captures = self.drive(already=True)
        self.assertEqual(captures, 0)
        self.assertEqual([call.args[0] for call in calls], ["preflight", "report"])


if __name__ == "__main__":
    unittest.main()

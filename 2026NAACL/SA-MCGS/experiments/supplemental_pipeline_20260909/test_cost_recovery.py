"""Synthetic recovery tests. Never imports a provider or spends API credit."""
import asyncio
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("recovery_under_test", Path(__file__).with_name("resume_cost_after_interruption.py"))
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def usage(calls=1):
    return dict(recorded_api_calls=calls, successful_api_calls=calls, failed_api_calls=0,
                prompt_tokens=100 * calls, completion_tokens=10 * calls,
                total_tokens=110 * calls, api_runtime_sec_sum=2.5 * calls)


class RecoveryTests(unittest.TestCase):
    def test_refuses_a_new_interruption_in_another_cell(self):
        row = dict(model=recovery.MODEL, case_id="slot-9", method=recovery.METHOD)
        with self.assertRaises(RuntimeError):
            recovery.validate_no_unhandled_partials([row], set())

    def test_accepts_terminal_calls_and_the_audited_interruption(self):
        done = (recovery.MODEL, "slot-9", recovery.METHOD)
        rows = [dict(zip(("model", "case_id", "method"), key))
                for key in (done, (recovery.MODEL, recovery.CASE_ID, recovery.METHOD))]
        recovery.validate_no_unhandled_partials(rows, {done})

    def test_combines_every_usage_counter(self):
        self.assertEqual(recovery.combine_usage(usage(3), usage(17)), usage(20))

    def test_rejects_changed_usage_schema(self):
        with self.assertRaises(RuntimeError):
            recovery.combine_usage(usage(), {"prompt_tokens": 100})

    def make_parent(self, spent=20):
        self.results = []
        self.paid_calls = 0
        async def adapter(*args):
            self.paid_calls += 1
            return dict(llm_usage_summary=usage(3), llm_calls=3, audit_started_at=100,
                        audit_completed_at=110, marker="scientific-result-unchanged")
        parent = SimpleNamespace(cost=SimpleNamespace(run_method=adapter),
            assert_budget_for_next_cell=Mock(), estimate_usd=lambda *args: .44,
            local_xhub_list_estimated_spend=lambda: spent,
            reserve_for_next_cell=lambda *args: .1,
            protocol=lambda: {"budget": {"hard_cap_usd": 85}},
            file_hash=lambda path: "sha256:synthetic", make_report=Mock())
        async def run_cost(**kwargs):
            self.assertEqual(kwargs, dict(smoke_only=False, retry_errors=False, max_new_cells=None))
            for case_id in (recovery.CASE_ID, "different-case"):
                parent.assert_budget_for_next_cell(recovery.MODEL, recovery.METHOD)
                result = await parent.cost.run_method(SimpleNamespace(model=recovery.MODEL),
                    Path("unused"), {"case_id": case_id}, recovery.METHOD)
                self.results.append(copy.deepcopy(result))
        parent.run_cost = run_cost
        return parent

    def test_only_interrupted_cell_is_augmented(self):
        parent = self.make_parent()
        original = parent.cost.run_method
        with patch.object(recovery, "append_recovery_note") as note:
            asyncio.run(recovery.execute(parent, {}, [{}], usage(17), Path("manifest.json")))
        self.assertEqual(self.results[0]["llm_usage_summary"], usage(20))
        self.assertEqual(self.results[1]["llm_usage_summary"], usage(3))
        self.assertNotIn("execution_recovery", self.results[1])
        meta = self.results[0]["execution_recovery"]
        self.assertFalse(meta["final_result_is_first_attempt"])
        self.assertFalse(meta["scientific_configuration_changed"])
        self.assertEqual(meta["resumed_execution_usage"], usage(3))
        self.assertEqual(self.results[0]["audit_started_at"], 100)
        self.assertEqual(self.results[0]["llm_calls"], 3)
        self.assertIs(parent.cost.run_method, original)
        note.assert_called_once()

    def test_unledgered_usage_is_guarded_before_any_call(self):
        parent = self.make_parent(spent=84.8)
        original = parent.cost.run_method
        with self.assertRaises(RuntimeError):
            asyncio.run(recovery.execute(parent, {}, [{}], usage(17), Path("manifest.json")))
        self.assertEqual(self.paid_calls, 0)
        self.assertIs(parent.cost.run_method, original)
        parent.make_report.assert_not_called()

    def test_no_double_charge_once_recovered(self):
        parent = self.make_parent()
        parent.estimate_usd = lambda *args: 0
        with patch.object(recovery, "append_recovery_note"):
            asyncio.run(recovery.execute(parent, {}, [], usage(0), Path("manifest.json")))
        self.assertTrue(all(r["llm_usage_summary"] == usage(3) for r in self.results))
        self.assertTrue(all("execution_recovery" not in r for r in self.results))


if __name__ == "__main__":
    unittest.main()

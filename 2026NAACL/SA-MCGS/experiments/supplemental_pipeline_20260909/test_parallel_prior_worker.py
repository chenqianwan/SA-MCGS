"""Synthetic-only tests: no LLM client or network request is constructed."""
from __future__ import annotations

import asyncio
import contextlib
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("parallel_prior_worker_under_test", HERE / "parallel_prior_worker.py")
assert SPEC and SPEC.loader
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class TestGuard(unittest.TestCase):
    def make_guard(self, cap: float = 2.5):
        return worker.SpendGuard(cap=cap, rates={"input": 2.5, "output": 10}, retries=2)

    def test_reserves_utf8_bytes_overhead_and_all_three_sdk_attempts(self):
        guard = self.make_guard()
        expected = 3 * ((len("法律".encode()) + len("system".encode()) + 512) * 2.5 + 4096 * 10) / 1e6
        self.assertAlmostEqual(guard.maximum_next_cost("法律", "system", 4096, None), expected)

    def test_cap_rejects_before_network(self):
        guard = self.make_guard(0.1)
        with self.assertRaises(RuntimeError):
            guard.admit(0.100001, RuntimeError)
        self.assertTrue(guard.blocked)
        with self.assertRaises(RuntimeError):
            guard.admit(0, RuntimeError)

    def test_success_uses_observed_usage_and_failure_keeps_unknown_reserve(self):
        guard = self.make_guard()
        guard.settle(0.2, {"prompt_tokens": 1000, "completion_tokens": 100})
        self.assertAlmostEqual(guard.observed_usd, 0.0035)
        guard.settle(0.2, None)
        self.assertAlmostEqual(guard.spend_upper_bound, 0.2035)
        self.assertEqual(guard.unobserved_failure_reserve_usd, 0.2)
        self.assertFalse(guard.summary()["exact_provider_billing_upper_bound_claimed"])

    def test_zero_usage_is_not_mistaken_for_free_call(self):
        guard = self.make_guard()
        guard.settle(0.1, {"prompt_tokens": 0, "completion_tokens": 0})
        self.assertEqual(guard.spend_upper_bound, 0.1)

    def test_unbounded_or_nonfinite_inputs_fail(self):
        for cap in (float("nan"), float("inf"), -1, True):
            with self.assertRaises(worker.WorkerError):
                self.make_guard(cap)
        for limit in (0, -1, None, True, 1.5):
            with self.assertRaises(worker.WorkerError):
                self.make_guard().maximum_next_cost("x", None, limit, None)

    def test_adapter_preserves_call_arguments_and_logging(self):
        calls = []
        logs = []

        class SyntheticLoggingClient:
            def __init__(self, config, *, call_log_path, context):
                self.config, self.context = config, context

            async def call(self, prompt, **kwargs):
                calls.append((prompt, kwargs))
                return SimpleNamespace(usage={"prompt_tokens": 100, "completion_tokens": 20})

        runner = SimpleNamespace(cost=SimpleNamespace(LoggingOpenAIClient=SyntheticLoggingClient,
                                                      append_jsonl=lambda p, row: logs.append(row)),
                                 now_iso=lambda: "2026-09-09T21:00:00+0800", BudgetStop=RuntimeError)
        guard = self.make_guard()
        guarded = worker.guarded_client_class(runner, guard, {"outer_process_concurrency": 4}, Path("/unused"))
        client = guarded({"max_retries": 2, "timeout": 600}, call_log_path=Path("/unused/log"), context={"case_concurrency": 1})
        asyncio.run(client.call("hello", temperature=0.4, max_tokens=2048, system_prompt="system", response_format={"type": "json_object"}))
        self.assertEqual(calls, [("hello", {"temperature": 0.4, "max_tokens": 2048, "system_prompt": "system", "response_format": {"type": "json_object"}})])
        self.assertEqual(client.config, {"max_retries": 2, "timeout": 600})
        self.assertEqual(client.context, {"case_concurrency": 1, "outer_process_concurrency": 4})
        self.assertEqual([row["event"] for row in logs], ["call_reserved", "call_settled"])
        guard.cap = guard.spend_upper_bound
        with self.assertRaises(RuntimeError):
            asyncio.run(client.call("blocked"))
        self.assertEqual(len(calls), 1)


class TestWorker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.directory = self.root / "workers" / "cell_7"
        self.directory.mkdir(parents=True)
        self.ticket_path = self.directory / "ticket.json"
        self.amendment = self.root / "amendment.json"
        write_json(self.amendment, {"scheduling_only": True})
        self.cell = {"order": 7, "slot": 3, "model": "gpt-4o", "profile": "minus20",
                     "result_path": str(self.root / "official" / "result.json")}
        self.case = {"case_order": 3, "domain": "synthetic", "case_id": "fake"}
        payload = {"context_kind": "authoritative", "total_available_usd": 100,
                   "captured_at": "2026-09-09T21:00:00+0800"}
        self.ticket = {"schema": worker.TICKET_SCHEMA, "worker_dir": str(self.directory),
                       "cell": self.cell, "case": self.case, "outer_process_concurrency": 4,
                       "worker_spend_cap_usd": 2.5,
                       "source_runner_sha256": worker.file_hash(worker.SOURCE_RUNNER),
                       "protocol_sha256": "sha256:synthetic_protocol",
                       "amendment_path": str(self.amendment), "amendment_sha256": worker.file_hash(self.amendment),
                       "budget_snapshot": {"path": "/synthetic/balance.json", "sha256": "sha256:synthetic_balance",
                                           "payload": payload, "authoritative": True}}
        self.frozen = {"locked_runtime": {"internal_concurrency": 1, "case_concurrency": 1, "llm_max_retries": 2},
                       "pricing": {"rates_usd_per_million_tokens": {"gpt-4o": {"input": 2.5, "output": 10}}}}
        self.runner = SimpleNamespace(
            protocol=lambda: self.frozen, PROTOCOL_PATH=Path("/synthetic/protocol"),
            file_hash=lambda p: "sha256:synthetic_protocol", validate_source_hashes=mock.Mock(),
            validate_manifest=mock.Mock(return_value={}),
            validate_selected_plans=mock.Mock(return_value=({"gpt-4o": [self.case]}, {"gpt-4o": {"synthetic": "graph"}}, [])),
            expected_execution_rows=mock.Mock(return_value=[self.cell]),
            validate_balance_snapshot=mock.Mock(return_value={"passed": True, "age_seconds": 1, "payload": payload}),
        )
        self.patch = mock.patch.object(worker, "PIPELINE_DIR", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def save_ticket(self):
        write_json(self.ticket_path, self.ticket)
        return worker.file_hash(self.ticket_path)

    def test_read_ticket_rejects_hash_tampering_and_directory_escape(self):
        digest = self.save_ticket()
        self.assertEqual(worker.read_ticket(self.ticket_path, digest)[1], self.directory)
        with self.assertRaises(worker.WorkerError):
            worker.read_ticket(self.ticket_path, "sha256:wrong")
        self.ticket["worker_dir"] = "/tmp/outside_the_pipeline"
        with self.assertRaises(worker.WorkerError):
            worker.read_ticket(self.ticket_path, self.save_ticket())

    def test_reconstructed_case_and_protocol_identity_are_required(self):
        checked = worker.validate_ticket(self.ticket, self.runner)
        self.assertEqual(checked["case"], self.case)
        self.runner.validate_source_hashes.assert_called_once()
        modified = copy.deepcopy(self.ticket)
        modified["case"]["domain"] = "wrong_scc"
        with self.assertRaises(worker.WorkerError):
            worker.validate_ticket(modified, self.runner)
        modified = copy.deepcopy(self.ticket)
        modified["protocol_sha256"] = "sha256:wrong"
        with self.assertRaises(worker.WorkerError):
            worker.validate_ticket(modified, self.runner)

    def test_synthetic_stale_and_changed_snapshots_are_rejected(self):
        self.ticket["budget_snapshot"]["authoritative"] = False
        with self.assertRaises(worker.WorkerError):
            worker.validate_ticket(self.ticket, self.runner)
        self.ticket["budget_snapshot"]["authoritative"] = True
        self.runner.validate_balance_snapshot.return_value["age_seconds"] = 1801
        with self.assertRaises(worker.WorkerError):
            worker.validate_ticket(self.ticket, self.runner)
        self.runner.validate_balance_snapshot.return_value["age_seconds"] = 1
        self.runner.validate_balance_snapshot.return_value["payload"] = {"changed": True}
        with self.assertRaises(worker.WorkerError):
            worker.validate_ticket(self.ticket, self.runner)

    def test_existing_official_result_is_never_reexecuted(self):
        write_json(Path(self.cell["result_path"]), {"valid": False})
        with self.assertRaises(worker.WorkerError):
            worker.validate_ticket(self.ticket, self.runner)

    def test_dry_inspect_never_enters_execution_or_writes_started(self):
        digest = self.save_ticket()
        with mock.patch.object(worker, "load_runner", return_value=self.runner), mock.patch.object(worker, "execute") as execute:
            self.assertEqual(worker.main(["--ticket", str(self.ticket_path), "--ticket-sha256", digest]), 0)
            execute.assert_not_called()
        self.assertFalse((self.directory / "started.json").exists())
        self.assertFalse((self.directory / "worker.lock").exists())

    def test_preexisting_started_ticket_refuses_automatic_rerun(self):
        digest = self.save_ticket()
        write_json(self.directory / "started.json", {"pid": 999})
        with mock.patch.object(worker, "load_runner", return_value=self.runner), mock.patch.object(worker, "execute") as execute:
            with self.assertRaises(worker.WorkerError):
                worker.main(["--ticket", str(self.ticket_path), "--ticket-sha256", digest, "--execute"])
            execute.assert_not_called()

    def test_worker_fl_lock_prevents_duplicate_execution(self):
        digest = self.save_ticket()
        with (self.directory / "worker.lock").open("a+") as held:
            worker.fcntl.flock(held, worker.fcntl.LOCK_EX | worker.fcntl.LOCK_NB)
            with mock.patch.object(worker, "load_runner", return_value=self.runner):
                with self.assertRaises(worker.WorkerError):
                    worker.main(["--ticket", str(self.ticket_path), "--ticket-sha256", digest, "--execute"])

    def test_isolated_execution_preserves_config_and_never_publishes_official(self):
        digest = self.save_ticket()
        frozen_config = {"case_concurrency": 1, "internal_concurrency": 1, "relation_weight": 0.68}
        result = {"experiment_config": frozen_config, "llm_usage_summary": {"prompt_tokens": 1000, "completion_tokens": 100}}
        expected_result = copy.deepcopy(result)

        async def fake_run(**kwargs):
            self.assertTrue((self.directory / "started.json").is_file())
            self.assertEqual(kwargs["output_dir"], self.directory)
            return result

        original_class = type("SyntheticBaseClient", (), {})
        self.runner.cost = SimpleNamespace(
            prepare_injected_case=mock.Mock(return_value=("injected_graph", "scc", "node", {})),
            atomic_write_json=write_json, LoggingOpenAIClient=original_class,
            InjectedGroundTruth=lambda *args: contextlib.nullcontext(),
        )
        self.runner.now_iso = lambda: "2026-09-09T21:00:00+0800"
        self.runner.run_prior_sa_cell = fake_run
        self.runner.validate_local_result = mock.Mock()
        self.runner.estimate_usd = lambda model, usage, frozen: 0.0035
        self.runner.BudgetStop = RuntimeError
        validated = worker.validate_ticket(self.ticket, self.runner)
        completed = asyncio.run(worker.execute(self.ticket, self.directory, self.runner, validated, digest))
        self.assertEqual(result["experiment_config"], expected_result["experiment_config"])
        self.assertTrue(completed["valid"])
        self.assertEqual(completed["result_path"], str(self.directory / "pending_result.json"))
        self.assertEqual(completed["result_sha256"], worker.file_hash(self.directory / "pending_result.json"))
        self.assertFalse(Path(self.cell["result_path"]).exists())
        self.assertFalse((self.directory / "budget_ledger.jsonl").exists())
        self.assertIs(self.runner.cost.LoggingOpenAIClient, original_class)
        self.assertEqual(result["outer_scheduling"]["outer_process_concurrency"], 4)
        self.assertFalse(result["outer_scheduling"]["wall_clock_comparable_to_serial_nominal"])
        self.runner.validate_local_result.assert_called_once()


if __name__ == "__main__":
    unittest.main()

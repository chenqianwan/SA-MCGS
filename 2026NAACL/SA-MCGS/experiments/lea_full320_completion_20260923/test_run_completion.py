"""Offline safety checks. No network access or paid calls."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

SPEC = importlib.util.spec_from_file_location("completion", Path(__file__).with_name("run_completion.py"))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.route = {"base_url": "https://example.invalid/v1", "model_id": "deepseek-v3",
            "api_key_env": "LEA_OFFLINE_TEST_KEY", "input_usd_per_million": 1,
            "output_usd_per_million": 2}
        self.price = self.root / "pricing.json"
        self.price.write_text(json.dumps({"budget_usd": 50, "models": {"deepseek-v3": self.route}}))
        self.ledger = runner.BudgetLedger(self.root, self.price)

    def tearDown(self):
        self.tmp.cleanup()

    def test_shared_reservations_cannot_overspend(self):
        def reserve(_):
            ledger = runner.BudgetLedger(self.root, self.price)
            try:
                return ledger.reserve(runner.nd(6), {"case_id": "test"})
            except runner.BudgetStop:
                return None
        with ThreadPoolExecutor(max_workers=12) as pool:
            reservations = list(pool.map(reserve, range(12)))
        accepted = [r for r in reservations if r]
        self.assertEqual(len(accepted), 8)
        self.assertEqual(self.ledger.snapshot()["committed_nd"], runner.nd(48))
        self.ledger.settle(accepted[0], runner.nd(1), "test_usage")
        self.assertEqual(self.ledger.snapshot()["committed_nd"], runner.nd(43))
        self.ledger.reserve(runner.nd(6), {})
        self.assertEqual(self.ledger.snapshot()["committed_nd"], runner.nd(49))

    def test_frozen_price_change_stops_before_reserve(self):
        self.price.write_text(self.price.read_text() + "\n")
        with self.assertRaises(runner.IntegrityStop):
            self.ledger.reserve(runner.nd(1), {})
        self.assertFalse(self.ledger.path.exists())

    def test_unresolved_reservation_survives_restart(self):
        self.ledger.reserve(runner.nd(49), {})
        another = runner.BudgetLedger(self.root, self.price)
        with self.assertRaises(runner.BudgetStop):
            another.reserve(runner.nd(2), {})

    def test_shared_halt_blocks_other_worker(self):
        self.ledger.halt("provider version mismatch")
        another = runner.BudgetLedger(self.root, self.price)
        with self.assertRaises(runner.IntegrityStop):
            another.reserve(runner.nd(1), {})

    def test_successful_paid_response_replayed_without_new_call(self):
        async def check():
            os.environ["LEA_OFFLINE_TEST_KEY"] = "offline-placeholder"
            case = {"case_id": "test", "case_order": 1, "model": "deepseek-v3",
                "domain": "cuad", "scc_id": "1", "scc_size": 9, "template": "direct_mutex"}
            calls = []
            async def create(**kwargs):
                calls.append(kwargs)
                return SimpleNamespace(model="deepseek-v3", usage=SimpleNamespace(model_dump=lambda: {
                    "prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125,
                    "prompt_tokens_details": {"cached_tokens": 8},
                    "completion_tokens_details": {"reasoning_tokens": 6}, "cost": 0.00015,
                    "cache_read_input_tokens": None}),
                    choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'), finish_reason="stop")])
            def make(protocol="test"):
                return runner.BudgetClient(route=self.route, ledger=self.ledger, output_dir=self.root,
                    case=case, phase="smoke", protocol_hash=protocol, timeout=1)
            first = make()
            first.client.chat.completions.create = create
            self.assertEqual(await first.call_json("test"), {"ok": True})
            self.assertEqual(first.cache[0]["usage"]["completion_tokens_details"], {"reasoning_tokens": 6})
            await first.close()
            charged_before = self.ledger.snapshot()["committed_nd"]
            self.root.joinpath("protocol_amendments.json").write_text(json.dumps([{
                "from_protocol_sha256": "test", "to_protocol_sha256": "budget_v2",
                "type": "adapter_compatibility", "api_request_and_scientific_protocol_unchanged": True}]))
            ledger_before = self.ledger.path.read_bytes()
            cache_before = first.cache_path.read_bytes()
            second = make("budget_v2")
            second.client.chat.completions.create = create
            self.assertEqual(await second.call_json("test"), {"ok": True})
            await second.close()
            self.assertEqual(len(calls), 1)
            self.assertEqual(self.ledger.snapshot()["committed_nd"], charged_before)
            self.assertEqual(self.ledger.path.read_bytes(), ledger_before)
            self.assertEqual(first.cache_path.read_bytes(), cache_before)
        asyncio.run(check())

    def test_gemini_reasoning_beyond_max_tokens_fits_reservation(self):
        route = {**self.route, "model_id": "gemini-2.5-pro",
                 "input_usd_per_million": 1.25, "output_usd_per_million": 10}
        output_bound = runner.completion_reserve_bound(route, 2048)
        self.assertEqual(output_bound, 2048 + 32768)
        reservation = runner.token_cost(route, 3807, output_bound)
        # Real failing smoke response: 749 visible + 1934 reasoning tokens.
        charge = runner.token_cost(route, 952, 2683)
        self.assertLess(charge, reservation)
        rid = self.ledger.reserve(reservation, {"max_tokens": 2048})
        self.ledger.settle(rid, charge, "test_gemini_reasoning_usage")
        self.assertEqual(self.ledger.snapshot()["pending_nd"], 0)
        self.assertFalse(self.ledger.halt_path.exists())
        self.assertEqual(runner.completion_reserve_bound(self.route, 2048), 2048)

    def test_new_deepseek_snapshot_rejected(self):
        runner.validate_returned_model("deepseek-v3", "deepseek-chat")
        for model in ("deepseek-v3-0324", "deepseek-v3.1", "DeepSeek-V3.2", "deepseek-v4", "deepseek-reasoner"):
            with self.assertRaises(runner.ProviderSnapshotMismatch):
                runner.validate_returned_model("deepseek-v3", model)

    def test_other_models_cannot_silently_replace_requested_model(self):
        for requested, returned in (("gpt-4o", "gemini-2.5-flash"),
            ("gemini-2.5-pro", "gemini-2.5-flash"),
            ("qwen/qwen-2.5-72b-instruct", "Qwen/Qwen2.5-7B-Instruct")):
            with self.assertRaises(runner.ProviderSnapshotMismatch):
                runner.validate_returned_model(requested, returned)

    def test_parse_exhaustion_preserves_historical_empty_dict_fallback(self):
        async def check():
            client = object.__new__(runner.BudgetClient)
            client.parse_exhausted_windows = 0
            client.call = AsyncMock(return_value=SimpleNamespace(content="unparseable"))
            with patch.object(runner.asyncio, "sleep", new=AsyncMock()):
                result = await client.call_json("test")
            self.assertEqual(result, {})
            self.assertEqual(client.call.await_count, 3)
            self.assertEqual(client.parse_exhausted_windows, 1)
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()

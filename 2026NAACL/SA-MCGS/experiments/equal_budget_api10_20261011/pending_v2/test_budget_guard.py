"""Offline guard and legacy-prefix restart tests; no real API requests."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from test_api_budget_client import FakeProvider, FakeResponse
from budget_guard import BudgetClient, GlobalLedger, BudgetStop, original, selector_extra_reserve


class Http503(Exception):
    status_code = 503


class FastClient(BudgetClient):
    async def _transport_sleep(self, seconds):
        pass


class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.clients, self.ledgers = [], []

    async def asyncTearDown(self):
        for c in self.clients:
            await c.close()
        for ledger in self.ledgers:
            await ledger.close()
        self.temp.cleanup()

    async def client(self, name="cell", cap=100000, model="gemini-2.5-pro", provider=None, old=False):
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        if not old and not (folder / "legacy_call_ids.json").exists():
            (folder / "legacy_call_ids.json").write_text("[]\n")
        ledger = (original.GlobalLedger if old else GlobalLedger)(folder / "ledger.jsonl")
        self.ledgers.append(ledger)
        await ledger.initialize()
        provider = provider or FakeProvider()
        c = (original.BudgetClient if old else FastClient)(ledger=ledger, case_id="c", method="lea",
            model=model, token_cap=cap, provider_client=provider)
        self.clients.append(c)
        return c, ledger, provider

    async def test_legacy_success_503_boundary_and_restart_exact_hash(self):
        old, oldledger, _ = await self.client(old=True,
            provider=FakeProvider([FakeResponse(), Http503("offline")]))
        old.set_selector_reserve(2000)
        await old.call_json("first", max_tokens=2048)
        with self.assertRaises(BudgetStop):
            await old.call_json("second", max_tokens=2048)
        oldhold = old.token_usage["held_tokens"]
        legacy = list(oldledger._calls)
        (self.root / "cell/legacy_call_ids.json").write_text(json.dumps(legacy))
        await oldledger.close()
        c, ledger, p = await self.client()
        self.assertEqual(c.fingerprint, old.fingerprint)
        self.assertFalse(c.guard_active)
        self.assertEqual(selector_extra_reserve(c), 0)
        c.set_selector_reserve(2000)
        await c.call_json("first", max_tokens=2048)
        self.assertFalse(p.requests)
        self.assertFalse(c.guard_active)
        await c.call_json("second", max_tokens=2048)
        self.assertTrue(c.guard_active)
        self.assertEqual(selector_extra_reserve(c), 16384)
        self.assertEqual(c._selector_reserve, 18384)
        self.assertEqual(len(p.requests), 1)
        row = c.last_call_record
        self.assertEqual(row["thinking_token_reserve"], 8192)
        self.assertEqual(row["max_output_tokens"], p.requests[0]["max_tokens"])
        self.assertEqual(row["reserved_tokens"], row["input_tokens"] + 2048 + 8192)
        self.assertEqual(c.token_usage["accounted_tokens"], 60 + oldhold)
        # Recompute the next selector reservation exactly as the wrapped method.
        c.set_selector_reserve(2000 + selector_extra_reserve(c))
        await c.call_json("third", max_tokens=2048)
        await ledger.close()
        replay, _, network = await self.client()
        replay.set_selector_reserve(2000)
        await replay.call_json("first", max_tokens=2048)
        await replay.call_json("second", max_tokens=2048)
        replay.set_selector_reserve(2000 + selector_extra_reserve(replay))
        await replay.call_json("third", max_tokens=2048)
        self.assertFalse(network.requests)
        self.assertEqual(replay.token_usage, c.token_usage)

    async def test_new_cell_lower_bound_uninflated_and_provider_cap_unchanged(self):
        c, _, p = await self.client(cap=12000)
        lower = c.estimate_request("hello", max_tokens=256, respect_budget=False)
        self.assertNotIn("thinking_token_reserve", lower)
        self.assertEqual(lower["reserved_tokens"], lower["input_tokens"] + 256)
        est = c.estimate_request("hello", max_tokens=2048)
        self.assertEqual(est["thinking_token_reserve"], 8192)
        await c.call_json("hello", max_tokens=2048)
        self.assertEqual(p.requests[0]["max_tokens"], 2048)
        self.assertEqual(c.token_usage["accounted_tokens"], 30)
        self.assertEqual(c.last_call_record["reserved_tokens"], est["reserved_tokens"])

    async def test_selector_visible_cap_256_with_extra_thinking_reservation(self):
        c, _, p = await self.client(cap=30000)
        c.set_phase("selector")
        c.set_selector_reserve(20000)
        est = c.estimate_request("judge", max_tokens=256)
        self.assertEqual(est["thinking_token_reserve"], 16384)
        await c.call_json("judge", max_tokens=256)
        self.assertEqual(p.requests[0]["max_tokens"], 256)
        self.assertEqual(c.last_call_record["reserved_tokens"], est["input_tokens"] + 256 + 16384)

    async def test_budget_true_caps_output_but_false_not_inflated(self):
        c, _, p = await self.client(cap=9000)
        est = c.estimate_request("hello", max_tokens=2048)
        self.assertEqual(est["max_output_tokens"], 9000 - est["input_tokens"] - 8192)
        self.assertEqual(c.estimate_request("hello", max_tokens=2048, respect_budget=False)["max_output_tokens"], 2048)
        await c.call_json("hello", max_tokens=2048)
        self.assertEqual(p.requests[0]["max_tokens"], est["max_output_tokens"])

    async def test_gpt_unchanged_and_guard_is_not_a_claimed_usage_cap(self):
        c, _, p = await self.client(model="gpt-4o")
        self.assertEqual(selector_extra_reserve(c), 0)
        await c.call_json("hello", max_tokens=2048)
        self.assertEqual(c.last_call_record["thinking_token_reserve"], 0)
        self.assertEqual(p.requests[0]["max_tokens"], 2048)
        huge = FakeResponse(usage={"prompt_tokens": 100, "completion_tokens": 40000, "total_tokens": 40100})
        gem, _, _ = await self.client(name="overrun", cap=30000, provider=FakeProvider([huge]))
        with self.assertRaises(BudgetStop) as error:
            await gem.call_json("hello", max_tokens=2048)
        self.assertEqual(error.exception.reason, "budget_overrun")
        self.assertEqual(gem.token_usage["accounted_tokens"], 40100)


if __name__ == "__main__":
    unittest.main()

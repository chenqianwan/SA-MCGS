"""Targeted offline transport-recovery tests; never sends an API request."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from test_api_budget_client import FakeProvider, FakeResponse
from recovery_transport import BudgetClient, BudgetStop, GlobalLedger, LedgerError, TRANSPORT_SPEC, original


class HttpError(Exception):
    def __init__(self, status):
        self.status_code = status
        super().__init__("offline fake")


class FastClient(BudgetClient):
    async def _transport_sleep(self, seconds):
        self.delays.append(seconds)


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.clients, self.ledgers = [], []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        for ledger in self.ledgers:
            await ledger.close()
        self.temp.cleanup()

    async def make_client(self, *, recovered=True, name="snapshot", provider=None, cap=20000):
        module = sys.modules[BudgetClient.__module__] if recovered else original
        ledger = module.GlobalLedger(self.root / name / "ledger.jsonl")
        self.ledgers.append(ledger)
        await ledger.initialize()
        provider = provider or FakeProvider()
        cls = FastClient if recovered else original.BudgetClient
        client = cls(ledger=ledger, case_id="case1", method="lea", model="gpt-4o",
                     token_cap=cap, provider_client=provider)
        client.delays = []
        self.clients.append(client)
        return client, ledger, provider

    async def test_old_prefix_and_503_resume_without_changing_original_or_fingerprint(self):
        old, ledger, _ = await self.make_client(recovered=False, name="original",
            provider=FakeProvider([FakeResponse(), HttpError(503)]))
        await old.call_json("first", max_tokens=500)
        with self.assertRaises(BudgetStop):
            await old.call_json("second", max_tokens=500)
        held = old.token_usage["held_tokens"]
        await ledger.close()
        old_bytes = {p.relative_to(self.root / "original"): p.read_bytes()
                     for p in (self.root / "original").rglob("*") if p.is_file()}
        shutil.copytree(self.root / "original", self.root / "snapshot")
        resumed, rledger, provider = await self.make_client()
        self.assertEqual(old.fingerprint, resumed.fingerprint)
        await resumed.call_json("first", max_tokens=500)
        self.assertFalse(provider.requests)
        self.assertEqual(resumed.token_usage["accounted_tokens"], 30)
        await resumed.call_json("second", max_tokens=500)
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(resumed.delays, [30])
        self.assertEqual(resumed.token_usage["accounted_tokens"], 60 + held)
        self.assertEqual(resumed.summary()["retained_503_tokens"], held)
        self.assertEqual(resumed.summary()["transport_successor_calls"], 1)
        self.assertEqual(json.loads(rledger.transport_spec_path.read_text()), TRANSPORT_SPEC)
        for rel, data in old_bytes.items():
            self.assertEqual((self.root / "original" / rel).read_bytes(), data)
        await rledger.close()
        replay, _, no_network = await self.make_client()
        await replay.call_json("first", max_tokens=500)
        await replay.call_json("second", max_tokens=500)
        self.assertFalse(no_network.requests)
        self.assertFalse(replay.delays)
        self.assertEqual(replay.token_usage["accounted_tokens"], 60 + held)

    async def test_repeated_503_at_most_three_and_replay_does_not_retry_again(self):
        c, ledger, p = await self.make_client(provider=FakeProvider([HttpError(503)] * 3))
        with self.assertRaises(BudgetStop) as caught:
            await c.call_json("hello", max_tokens=400)
        self.assertEqual(caught.exception.reason, "http503_transport_attempts_exhausted")
        self.assertEqual(len(p.requests), 3)
        self.assertEqual(c.delays, [30, 90])
        self.assertEqual(c.summary()["explicit_503_calls"], 3)
        self.assertEqual(c.summary()["retained_503_tokens"], c.token_usage["accounted_tokens"])
        await ledger.close()
        replay, _, no_network = await self.make_client()
        with self.assertRaises(BudgetStop) as caught:
            await replay.call_json("hello", max_tokens=400)
        self.assertEqual(caught.exception.reason, "http503_transport_attempts_exhausted")
        self.assertFalse(no_network.requests)
        self.assertFalse(replay.delays)

    async def test_timeout_other_status_missing_usage_never_retry(self):
        errors = [TimeoutError("offline"), ConnectionError("offline"), HttpError(429), HttpError(500),
                  FakeResponse(missing=True)]
        for i, response in enumerate(errors):
            c, _, p = await self.make_client(name=f"no_retry_{i}", provider=FakeProvider([response]))
            with self.assertRaises(BudgetStop):
                await c.call_json("hello", max_tokens=400)
            self.assertEqual(len(p.requests), 1)
            self.assertFalse(c.delays)
            with self.assertRaises(BudgetStop):
                await c.call_json("another", max_tokens=400)
            self.assertEqual(len(p.requests), 1)

    async def test_503_hold_reduces_next_output_and_all_actual_tokens_count(self):
        c, _, p = await self.make_client(cap=1600,
            provider=FakeProvider([HttpError(503), FakeResponse()]))
        estimate = c.estimate_request("hello", max_tokens=600)
        await c.call_json("hello", max_tokens=600)
        self.assertEqual(p.requests[0]["max_tokens"], 600)
        self.assertEqual(p.requests[1]["max_tokens"], 1600 - estimate["reserved_tokens"] - estimate["input_tokens"])
        self.assertEqual(c.token_usage["accounted_tokens"], estimate["reserved_tokens"] + 30)
        self.assertLessEqual(c.token_usage["accounted_tokens"], 1600)

    async def test_budget_exhausted_by_503_is_infrastructure_not_silent_scientific_zero(self):
        c, _, p = await self.make_client(cap=600, provider=FakeProvider([HttpError(503)]))
        with self.assertRaises(BudgetStop) as caught:
            await c.call_json("hello", max_tokens=600)
        self.assertEqual(caught.exception.reason, "transport_budget_exhausted")
        self.assertEqual(len(p.requests), 1)
        self.assertEqual(c.token_usage["accounted_tokens"], 600)
        self.assertFalse(issubclass(BudgetStop, Exception))

    async def test_json_attempts_and_selector_attempt_remain_frozen(self):
        outputs = [HttpError(503), FakeResponse("bad"), HttpError(503), FakeResponse("bad"), FakeResponse()]
        c, _, p = await self.make_client(provider=FakeProvider(outputs))
        self.assertEqual(await c.call_json("hello", max_tokens=300), {"ok": True})
        self.assertEqual(len(p.requests), 5)
        self.assertEqual(c.summary()["parse_failure_calls"], 2)
        self.assertEqual(c.summary()["explicit_503_calls"], 2)
        selector, _, sp = await self.make_client(name="selector",
            provider=FakeProvider([HttpError(503), FakeResponse("bad"), FakeResponse()]))
        selector.set_phase("selector")
        self.assertEqual(await selector.call_json("judge", max_tokens=256), {})
        self.assertEqual(len(sp.requests), 2)
        self.assertEqual(selector.summary()["parse_failure_calls"], 1)

    async def test_policy_sidecar_change_rejected(self):
        _, ledger, _ = await self.make_client()
        spec = dict(TRANSPORT_SPEC, maximum_transport_attempts_per_json_attempt=10)
        ledger.transport_spec_path.write_text(json.dumps(spec))
        await ledger.close()
        with self.assertRaises(LedgerError):
            await self.make_client()


if __name__ == "__main__":
    unittest.main()

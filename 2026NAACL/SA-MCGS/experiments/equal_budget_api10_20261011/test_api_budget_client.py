"""Offline tests only: all completion requests use an injected fake provider."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "equal_budget_all80_20261009" / "science" / "repo"))
sys.path.insert(0, str(HERE))
from api_budget_client import BudgetClient, BudgetStop, GlobalLedger, LedgerError, ENDPOINT


class FakeResponse:
    def __init__(self, content='{"ok": true}', usage=None, missing=False):
        self.model = "mock-provider"
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]
        self.usage = None if missing else (usage if usage is not None else {
            "prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30,
            "completion_tokens_details": {"reasoning_tokens": 5}})

    def model_dump(self, mode="json"):
        return {"model": self.model, "usage": self.usage,
                "choices": [{"message": {"content": self.choices[0].message.content}}]}


class FakeProvider:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.closed = False

    async def create(self, **body):
        self.requests.append(body)
        response = self.responses.pop(0) if self.responses else FakeResponse()
        if isinstance(response, BaseException):
            raise response
        return response

    async def close(self):
        self.closed = True


class ApiBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ledger.jsonl"
        self.ledgers, self.clients = [], []
        self.ledger = await self.open_ledger()

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        for ledger in self.ledgers:
            await ledger.close()
        self.temp.cleanup()

    async def open_ledger(self):
        ledger = GlobalLedger(self.path)
        self.ledgers.append(ledger)
        await ledger.initialize()
        return ledger

    def client(self, *, ledger=None, provider=None, cap=100_000, method="lea", model="gpt-4o", **kwargs):
        provider = provider or FakeProvider()
        client = BudgetClient(ledger=ledger or self.ledger, case_id="case1", method=method,
                              model=model, token_cap=cap, provider_client=provider, **kwargs)
        self.clients.append(client)
        return client, provider

    async def test_actual_usage_not_estimate_and_prices_reasoning_preserved(self):
        c, p = self.client(model="gemini-2.5-pro")
        response = await c.call("hello", max_tokens=2048)
        self.assertGreater(c.estimate_request("hello")["input_tokens"], 21)
        self.assertEqual(c.token_usage["accounted_tokens"], 30)
        self.assertEqual(response.usage["completion_tokens_details"]["reasoning_tokens"], 5)
        self.assertEqual(c.summary()["usage_mismatch_calls"], 0)
        self.assertEqual(c.summary()["input_estimate_mismatch_calls"], 1)
        self.assertAlmostEqual(c.summary()["estimated_usd"], (21 * 1.25 + 9 * 10) / 1e6)
        self.assertEqual(c.timeout, 600)
        self.assertEqual(c.config["base_url"], ENDPOINT)
        self.assertEqual(c.config["max_retries"], 0)
        self.assertEqual(p.requests[0]["max_tokens"], 2048)

    async def test_limits_selector_reserve_and_full_output(self):
        c, p = self.client(method="full-scc", cap=20_000)
        c.set_selector_reserve(500)
        self.assertEqual(c.remaining_tokens, 19_500)
        await c.call("hello", max_tokens=12000)
        self.assertEqual(p.requests[-1]["max_tokens"], 12000)
        c.set_phase("selector")
        self.assertEqual(c.remaining_tokens, 19_970)
        await c.call_json("judge", max_tokens=12000)
        self.assertEqual(p.requests[-1]["max_tokens"], 256)
        lea, lp = self.client(cap=10_000)
        await lea.call("hello", max_tokens=12000)
        self.assertEqual(lp.requests[-1]["max_tokens"], 2048)

    async def test_replay_prefix_no_duplicate_charge_or_provider_calls(self):
        c, _ = self.client(cap=1800)
        await c.call("one", max_tokens=600)
        await c.call("two", max_tokens=600)
        await self.ledger.close()
        replay, network = self.client(ledger=await self.open_ledger(), cap=1800)
        self.assertEqual(replay.remaining_tokens, 1800)
        await replay.call("one", max_tokens=600)
        self.assertEqual(replay.remaining_tokens, 1770)
        await replay.call("two", max_tokens=600)
        self.assertFalse(network.requests)
        self.assertEqual(replay.summary()["calls"], 2)
        self.assertEqual(replay.summary()["accounted_tokens"], 60)
        await replay.call("three", max_tokens=600)
        self.assertEqual(len(network.requests), 1)

    async def test_changed_replay_request_rejected(self):
        c, _ = self.client()
        await c.call("one", max_tokens=500)
        replay, p = self.client()
        with self.assertRaises(LedgerError):
            await replay.call("changed", max_tokens=500)
        self.assertFalse(p.requests)

    async def test_transport_unknown_no_retry_and_secret_never_logged(self):
        secret = "offline-secret-not-real"
        error = TimeoutError("sensitive message " + secret)
        with patch.dict(os.environ, {"XHUB_API_KEY": secret}):
            c, p = self.client(provider=FakeProvider([error]))
        estimate = c.estimate_request("hello", max_tokens=500)["reserved_tokens"]
        with self.assertRaises(BudgetStop) as caught:
            await c.call_json("hello", max_tokens=500)
        self.assertEqual(caught.exception.reason, "unknown_provider_outcome")
        self.assertEqual(len(p.requests), 1)
        self.assertEqual(c.token_usage["held_tokens"], estimate)
        await self.ledger.close()
        replay, network = self.client(ledger=await self.open_ledger())
        with self.assertRaises(BudgetStop):
            await replay.call_json("hello", max_tokens=500)
        self.assertFalse(network.requests)
        for file in Path(self.temp.name).rglob("*"):
            if file.is_file():
                self.assertNotIn(secret, file.read_text())
                self.assertNotIn("sensitive message", file.read_text())

    async def test_response_redaction_and_cache_hash_match(self):
        secret = "offline-secret-not-real"
        with patch.dict(os.environ, {"XHUB_API_KEY": secret}):
            c, _ = self.client(provider=FakeProvider([FakeResponse('{"note":"' + secret + '"}')]))
        result = await c.call_json("hello")
        self.assertEqual(result["note"], "[REDACTED]")
        replay, p = self.client()
        self.assertEqual(await replay.call_json("hello"), result)
        self.assertFalse(p.requests)
        for file in Path(self.temp.name).rglob("*.json*"):
            self.assertNotIn(secret, file.read_text())

    async def test_reasoning_budget_overrun_records_full_usage_and_stops(self):
        usage = {"prompt_tokens": 30, "completion_tokens": 900, "total_tokens": 1230,
                 "completion_tokens_details": {"reasoning_tokens": 800}}
        c, p = self.client(model="gemini-2.5-pro", cap=1000,
                           provider=FakeProvider([FakeResponse(usage=usage)]))
        with self.assertRaises(BudgetStop) as caught:
            await c.call_json("hello", max_tokens=2048)
        self.assertEqual(caught.exception.reason, "budget_overrun")
        self.assertEqual(c.token_usage["accounted_tokens"], 1230)
        self.assertEqual(c.summary()["budget_overrun_tokens"], 230)
        self.assertEqual(c.summary()["output_ceiling_exceeded_calls"], 1)
        self.assertEqual(c.last_call_record["provider_total_residual_tokens"], 300)
        self.assertAlmostEqual(c.summary()["estimated_usd"], (30 * 1.25 + 1200 * 10) / 1e6)
        with self.assertRaises(BudgetStop):
            await c.call("next")
        self.assertEqual(len(p.requests), 1)
        await self.ledger.close()
        replay, network = self.client(ledger=await self.open_ledger(), model="gemini-2.5-pro", cap=1000)
        with self.assertRaises(BudgetStop) as replay_error:
            await replay.call_json("hello", max_tokens=2048)
        self.assertEqual(replay_error.exception.reason, "budget_overrun")
        self.assertFalse(network.requests)

    async def test_missing_usage_stops_no_default_scores(self):
        c, p = self.client(provider=FakeProvider([FakeResponse(missing=True)]))
        with self.assertRaises(BudgetStop) as caught:
            await c.call_json("hello")
        self.assertEqual(caught.exception.reason, "unknown_provider_usage")
        self.assertGreater(c.token_usage["held_tokens"], 0)
        with self.assertRaises(BudgetStop):
            await c.call_json("next")
        self.assertEqual(len(p.requests), 1)
        self.assertFalse(issubclass(BudgetStop, Exception))

    async def test_json_retries_three_and_selector_one_all_charged(self):
        c, p = self.client(provider=FakeProvider([FakeResponse("bad") for _ in range(3)]))
        self.assertEqual(await c.call_json("hello", retries=10), {})
        self.assertEqual(len(p.requests), 3)
        self.assertEqual(c.token_usage["accounted_tokens"], 90)
        self.assertEqual(c.summary()["parse_failure_calls"], 3)
        self.assertEqual(c.summary()["retry_calls"], 2)
        judge, jp = self.client(method="full-scc", provider=FakeProvider([FakeResponse("bad")]))
        judge.set_phase("selector")
        self.assertEqual(await judge.call_json("judge", retries=10), {})
        self.assertEqual(len(jp.requests), 1)

    async def test_response_fsync_crash_recovery_no_second_charge(self):
        c, p = self.client()
        original = self.ledger.finish
        async def crash(*args, **kwargs):
            raise LedgerError("simulated")
        self.ledger.finish = crash
        with self.assertRaises(LedgerError):
            await c.call("hello")
        self.ledger.finish = original
        await self.ledger.close()
        replay, network = self.client(ledger=await self.open_ledger())
        await replay.call("hello")
        self.assertFalse(network.requests)
        self.assertEqual(replay.summary()["accounted_tokens"], 30)

    async def test_fixed_endpoint_auth_policy_and_ledger_lock(self):
        with self.assertRaises(ValueError):
            self.client(base_url="https://elsewhere.example/v1")
        with self.assertRaises(ValueError):
            self.client(config={"api_key": "disallowed"})
        with self.assertRaises(ValueError):
            self.client(model="other")
        with self.assertRaises(ValueError):
            self.client(json_attempts=4)
        with self.assertRaises(LedgerError):
            await self.open_ledger()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                BudgetClient(ledger=self.ledger, model="gpt-4o", case_id="x", method="lea", token_cap=1000)


if __name__ == "__main__":
    unittest.main()

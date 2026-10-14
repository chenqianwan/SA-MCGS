"""Offline financial-gate tests. Fake SDK only; never contact a provider."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from budget_client import (BudgetClient, BudgetStop, GlobalLedger, LedgerError,
                           ProviderCallError)


class FakeResponse:
    def __init__(self, content='{"ok": true}', usage=None, missing_usage=False):
        self.model = "gpt-4o-2024-08-06"
        self.usage = None if missing_usage else (usage or {
            "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
            "prompt_tokens_details": {"cached_tokens": 80},
            "completion_tokens_details": {"reasoning_tokens": 3},
        })
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]

    def model_dump(self, mode="json"):
        return {"model": self.model, "usage": self.usage,
                "choices": [{"message": {"content": self.choices[0].message.content}}]}


class FakeProvider:
    def __init__(self, responses=None, release=None):
        self.responses = list(responses or [FakeResponse()])
        self.release = release
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.closed = False

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.release is not None:
            await self.release.wait()
        response = self.responses.pop(0) if self.responses else FakeResponse()
        if isinstance(response, BaseException):
            raise response
        return response

    async def close(self):
        self.closed = True


class BudgetClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.ledgers = []
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        for ledger in self.ledgers:
            await ledger.close()
        self.temporary.cleanup()

    async def ledger(self, cap=15.0, name="ledger.jsonl"):
        ledger = GlobalLedger(self.directory/name, cap_usd=cap)
        self.ledgers.append(ledger)
        await ledger.initialize()
        return ledger

    def client(self, ledger, provider=None, method="sa", **kwargs):
        provider = provider or FakeProvider()
        client = BudgetClient(ledger=ledger, case_id="case-1", method=method,
                              call_log_dir=self.directory/method,
                              provider_client=provider, **kwargs)
        self.clients.append(client)
        return client, provider

    async def test_full_usage_and_output_caps_and_uncached_prices(self):
        ledger = await self.ledger()
        client, provider = self.client(ledger)
        response = await client.call("hello", max_tokens=16000)
        self.assertEqual(provider.requests[0]["max_tokens"], 12000)
        self.assertEqual(response.usage["prompt_tokens_details"]["cached_tokens"], 80)
        self.assertEqual(response.usage["completion_tokens_details"]["reasoning_tokens"], 3)
        self.assertIsInstance(response.raw, FakeResponse)
        self.assertEqual(response.model, "gpt-4o-2024-08-06")
        await client.call("hello", max_tokens=2048)
        self.assertEqual(provider.requests[1]["max_tokens"], 2048)
        report = await ledger.summary()
        self.assertEqual(report["calls"], 2)
        self.assertEqual(report["held_usd"], 0)
        self.assertAlmostEqual(report["actual_usd"], 2*(100*2.5+20*10)/1e6)
        saved = [json.loads(p.read_text()) for p in (self.directory/"sa").glob("*.json")]
        self.assertEqual(len(saved), 2)
        self.assertIn("completion_tokens_details", saved[0]["usage"])
        self.assertIn("choices", saved[0]["raw_response"])

    async def test_three_parallel_jobs_cannot_overreserve_global_cap(self):
        ledger = await self.ledger(cap=0.09)
        release = asyncio.Event()
        pairs = [self.client(ledger, FakeProvider(release=release), method=f"arm-{i}") for i in range(3)]

        async def attempt(client):
            try:
                await client.call("hello", max_tokens=4096)
                return "complete"
            except BudgetStop:
                return "stopped"

        tasks = [asyncio.create_task(attempt(client)) for client, _ in pairs]
        for _ in range(5):
            await asyncio.sleep(0)
        pending = await ledger.summary()
        self.assertEqual(sum(len(p.requests) for _, p in pairs), 2)
        self.assertEqual(pending["pending_calls"], 2)
        self.assertLessEqual(pending["accounted_usd"], 0.09)
        release.set()
        outcomes = await asyncio.gather(*tasks)
        self.assertEqual(outcomes.count("stopped"), 1)
        self.assertEqual(outcomes.count("complete"), 2)

    async def test_exact_15_dollar_cap_and_no_raising_cap_on_restart(self):
        ledger = await self.ledger()
        reserve = dict(case_id="large", token_cap=20_000_000, selector_reserve=0,
                       phase="sa", input_upper=2_000_000, estimated_input=100,
                       max_output=4096, prompt_hash="a")
        await ledger.reserve(method="a", **reserve)
        await ledger.reserve(method="b", **reserve)
        with self.assertRaises(BudgetStop) as caught:
            await ledger.reserve(method="c", **reserve)
        self.assertEqual(caught.exception.reason, "global_dollars")
        self.assertLessEqual((await ledger.summary())["accounted_usd"], 15)
        with self.assertRaises(ValueError):
            GlobalLedger(self.directory/"other.jsonl", cap_usd=15.01)

    async def test_unknown_failure_keeps_full_hold_and_hides_error_secret(self):
        secret = "sk-test-sensitive-credential"
        ledger = await self.ledger()
        client, _ = self.client(ledger, FakeProvider([RuntimeError(secret)]), api_key=secret)
        reserve = client.estimate_request("hello", max_tokens=100)["reserve_usd"]
        with self.assertRaises(ProviderCallError) as caught:
            await client.call("hello", max_tokens=100)
        self.assertNotIn(secret, str(caught.exception))
        report = await ledger.summary()
        self.assertEqual(report["actual_usd"], 0)
        self.assertEqual(report["held_usd"], reserve)
        self.assertEqual(report["unknown_failure_calls"], 1)
        self.assertGreater(client.token_usage["held_tokens"], 0)
        for file in self.directory.rglob("*.json*"):
            self.assertNotIn(secret, file.read_text())

    async def test_missing_usage_is_a_full_hold_even_with_usable_answer(self):
        ledger = await self.ledger()
        client, _ = self.client(ledger, FakeProvider([FakeResponse(missing_usage=True)]))
        answer = await client.call_json("hello", max_tokens=100)
        self.assertTrue(answer["ok"])
        report = await ledger.summary()
        self.assertEqual(report["missing_usage_calls"], 1)
        self.assertEqual(report["actual_usd"], 0)
        self.assertGreater(report["held_usd"], 0)

    async def test_restart_retains_unfinished_call_dollar_and_token_holds(self):
        ledger = await self.ledger(cap=0.05)
        client, _ = self.client(ledger, token_cap=4500)
        estimate = client.estimate_request("hello")
        await ledger.reserve(case_id="case-1", method="sa", token_cap=4500,
                             selector_reserve=0, phase="sa", input_upper=estimate["input_upper_tokens"],
                             estimated_input=estimate["estimated_input_tokens"],
                             max_output=4096, prompt_hash=estimate["prompt_sha256"])
        original = await ledger.summary()
        await ledger.close()
        reopened = await self.ledger(cap=0.05)
        again, provider = self.client(reopened, token_cap=4500)
        recovered = await reopened.summary()
        self.assertEqual(recovered["accounted_usd"], original["accounted_usd"])
        self.assertEqual(recovered["recovered_unresolved_calls"], 1)
        self.assertLess(again.remaining_tokens, 4500)
        with self.assertRaises(BudgetStop):
            await again.call("hello")
        self.assertFalse(provider.requests)

    async def test_selector_reserve_and_stop_bypass_exception_fallback(self):
        ledger = await self.ledger()
        client, provider = self.client(ledger, token_cap=2000)
        client.set_selector_reserve(1500)
        self.assertEqual(client.remaining_tokens, 500)
        swallowed = False
        try:
            try:
                await client.call("hello", max_tokens=500)
            except Exception:
                swallowed = True
        except BudgetStop as stop:
            self.assertEqual(stop.reason, "tokens")
        else:
            self.fail("BudgetStop should escape an ordinary search exception fallback")
        self.assertFalse(swallowed)
        self.assertFalse(provider.requests)
        client.set_phase("selector")
        self.assertEqual(client.remaining_tokens, 2000)
        await client.call("hello", max_tokens=500)
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(client.remaining_tokens, 1880)

    async def test_json_retry_is_at_most_one_and_each_attempt_is_charged(self):
        ledger = await self.ledger()
        client, provider = self.client(ledger, FakeProvider([FakeResponse("invalid"), FakeResponse("still invalid")]))
        with self.assertRaises(ProviderCallError):
            await client.call_json("hello", max_tokens=100, retries=20)
        self.assertEqual(len(provider.requests), 2)
        report = await ledger.summary()
        self.assertEqual(report["calls"], 2)
        self.assertEqual(report["retry_calls"], 1)
        self.assertEqual(report["total_tokens"], 240)

    async def test_budget_stop_on_json_retry_is_not_swallowed(self):
        ledger = await self.ledger()
        # Unknown failed first attempt conservatively consumes the input estimate
        # and the requested output cap, leaving no room for the single retry.
        client, provider = self.client(ledger, FakeProvider([TimeoutError("safe")]), token_cap=250)
        with self.assertRaises(BudgetStop):
            await client.call_json("hello", max_tokens=100)
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual((await ledger.summary())["unknown_failure_calls"], 1)

    async def test_cancellation_keeps_attempt_held(self):
        ledger = await self.ledger()
        release = asyncio.Event()
        client, provider = self.client(ledger, FakeProvider(release=release))
        task = asyncio.create_task(client.call("hello"))
        while not provider.requests:
            await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        report = await ledger.summary()
        self.assertEqual(report["unknown_failure_calls"], 1)
        self.assertGreater(report["held_usd"], 0)

    async def test_truncated_ledger_fails_closed_and_second_runner_excluded(self):
        ledger = await self.ledger()
        competing = GlobalLedger(ledger.path)
        self.ledgers.append(competing)
        with self.assertRaises(LedgerError):
            await competing.initialize()
        await ledger.close()
        with ledger.path.open("ab") as handle:
            handle.write(b'{"event":"reserve"')
        broken = GlobalLedger(ledger.path)
        self.ledgers.append(broken)
        with self.assertRaises(LedgerError):
            await broken.initialize()

    async def test_sdk_retries_forced_zero_and_non_gpt4o_rejected(self):
        ledger = await self.ledger()
        provider = FakeProvider()
        with patch("budget_client.AsyncOpenAI", return_value=provider) as sdk:
            client = BudgetClient({"max_retries": 5}, ledger=ledger, case_id="x", method="x",
                                  call_log_dir=self.directory/"x", api_key="safe-fake")
            self.clients.append(client)
            self.assertEqual(sdk.call_args.kwargs["max_retries"], 0)
        with self.assertRaises(ValueError):
            BudgetClient({"model": "gpt-4.1"}, ledger=ledger, case_id="x", method="x",
                         call_log_dir=self.directory/"x", provider_client=provider)


if __name__ == "__main__":
    unittest.main()

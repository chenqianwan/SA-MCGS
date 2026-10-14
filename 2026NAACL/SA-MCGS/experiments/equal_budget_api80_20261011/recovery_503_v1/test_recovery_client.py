"""Offline regression tests for durable, request-preserving HTTP-503 recovery.

Run with ``python -m unittest discover -s <this directory> -p test_recovery_client.py``.
Every provider is fake, and constructing the real SDK client is forbidden.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import recovery_client as recovery


MODEL = "gpt-4o"
PROMPT = "Return the evidence as JSON."
USAGE = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


class HTTPFailure(Exception):
    def __init__(self, status):
        super().__init__(f"fake HTTP {status}")
        self.status_code = status


class FakeProvider:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.closed = False
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **body):
        self.requests.append(copy.deepcopy(body))
        if not self.outcomes:
            raise AssertionError("Unexpected provider request")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def close(self):
        self.closed = True


def response(content='{"answer": 42}', usage=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        model=MODEL,
        usage=copy.deepcopy(USAGE if usage is None else usage),
    )


def historical(*, index=0, content='{"answer": 42}', status="response_received",
               http_status=None, retry_index=0, max_tokens=17, as_json=True):
    call_id, request_hash = f"original-call-{index}", f"original-hash-{index}"
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if as_json:
        body["response_format"] = {"type": "json_object"}
    row = {
        "call_id": call_id,
        "request_hash": request_hash,
        "status": status,
        "request": body,
        "reservation": {
            "call_id": call_id,
            "request_hash": request_hash,
            "request_key": f"call-{index}:attempt-{retry_index}",
            "retry_index": retry_index,
            "requested_max_output_tokens": 64,
        },
    }
    if http_status is not None:
        row["http_status"] = http_status
    if status == "response_received":
        row["result"] = {"content": content, "model": MODEL,
                         "usage": copy.deepcopy(USAGE), "raw": {"id": call_id}}
    return row


class RecoveryClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.clients = []
        self.sdk_guard = patch.object(
            recovery.original, "AsyncOpenAI",
            side_effect=AssertionError("Real provider construction is forbidden in tests"),
        )
        self.sdk_guard.start()

    async def asyncTearDown(self):
        for client in reversed(self.clients):
            await client.close()
        self.sdk_guard.stop()
        self.temp.cleanup()

    def client(self, history=(), *, provider=None, paid=False, phase="candidate"):
        client = recovery.RecoveryClient(
            MODEL, "lea", self.folder, list(history), phase=phase,
            paid_allowed=paid, provider_client=provider,
        )
        async def no_sleep(seconds):
            pass
        client._transport_sleep = no_sleep
        self.clients.append(client)
        return client

    async def ask(self, client, **kwargs):
        return await client.call_json(PROMPT, temperature=0, max_tokens=64, **kwargs)

    async def test_historical_success_replays_without_payment(self):
        old = historical()
        snapshot = copy.deepcopy(old)
        provider = FakeProvider()
        client = self.client([old], provider=provider)
        self.assertEqual(await self.ask(client), {"answer": 42})
        self.assertEqual(provider.requests, [])
        self.assertEqual(old, snapshot)
        client.assert_history_consumed()
        self.assertEqual(client.summary()["external_api_calls"], 0)
        self.assertEqual(client.summary()["historical_cache_replays"], 1)

    async def test_historical_503_retries_exact_body_twice_then_restarts_free(self):
        old = historical(status="unknown_failure", http_status=503)
        provider = FakeProvider(HTTPFailure(503), response())
        client = self.client([old], provider=provider, paid=True)
        self.assertEqual(await self.ask(client), {"answer": 42})
        self.assertEqual(provider.requests, [old["request"], old["request"]])
        self.assertEqual(client.summary()["external_api_calls"], 2)
        self.assertEqual(client.summary()["explicit_503_calls"], 1)
        self.assertEqual(client.summary()["total_tokens"], 18)
        await client.close()
        restarted_provider = FakeProvider()
        restarted = self.client([old], provider=restarted_provider)
        self.assertEqual(await self.ask(restarted), {"answer": 42})
        self.assertEqual(restarted_provider.requests, [])
        self.assertEqual(restarted.summary()["external_api_calls"], 2)
        self.assertEqual(restarted.summary()["cache_replays"], 2)

    async def test_historical_503_cap_remains_exhausted_after_restart(self):
        old = historical(status="unknown_failure", http_status=503)
        provider = FakeProvider(HTTPFailure(503), HTTPFailure(503), response())
        client = self.client([old], provider=provider, paid=True)
        with self.assertRaisesRegex(recovery.BudgetStop, "http503_transport_attempts_exhausted"):
            await self.ask(client)
        self.assertEqual(len(provider.requests), 2)
        await client.close()
        restarted_provider = FakeProvider(response())
        restarted = self.client([old], provider=restarted_provider, paid=True)
        with self.assertRaisesRegex(recovery.BudgetStop, "http503_transport_attempts_exhausted"):
            await self.ask(restarted)
        self.assertEqual(restarted_provider.requests, [])

    async def test_new_window_has_one_initial_and_two_503_retries(self):
        provider = FakeProvider(HTTPFailure(503), HTTPFailure(503), response())
        client = self.client(provider=provider, paid=True)
        self.assertEqual(await self.ask(client), {"answer": 42})
        self.assertEqual(len(provider.requests), 3)
        self.assertTrue(all(body == provider.requests[0] for body in provider.requests))
        self.assertEqual(client.summary()["retry_calls"], 2)
        await client.close()
        restarted_provider = FakeProvider()
        restarted = self.client(provider=restarted_provider)
        self.assertEqual(await self.ask(restarted), {"answer": 42})
        self.assertEqual(restarted_provider.requests, [])

    async def test_new_window_503_cap_is_three_total_attempts(self):
        provider = FakeProvider(*(HTTPFailure(503) for _ in range(4)))
        client = self.client(provider=provider, paid=True)
        with self.assertRaisesRegex(recovery.BudgetStop, "http503_transport_attempts_exhausted"):
            await self.ask(client)
        self.assertEqual(len(provider.requests), 3)

    async def test_non503_historical_errors_are_ineligible(self):
        for status in (400, 429, 500, 502, 504, None):
            with self.subTest(status=status):
                self.folder = Path(self.temp.name) / f"status-{status}"
                old = historical(status="unknown_failure", http_status=status)
                provider = FakeProvider(response())
                client = self.client([old], provider=provider, paid=True)
                with self.assertRaisesRegex(recovery.BudgetStop, "historical_non503_failure"):
                    await self.ask(client)
                self.assertEqual(provider.requests, [])

    async def test_new_non503_error_is_not_retried_on_restart(self):
        provider = FakeProvider(HTTPFailure(429), response())
        client = self.client(provider=provider, paid=True)
        with self.assertRaisesRegex(recovery.BudgetStop, "recovery_non503_failure"):
            await self.ask(client)
        self.assertEqual(len(provider.requests), 1)
        await client.close()
        restarted_provider = FakeProvider(response())
        restarted = self.client(provider=restarted_provider, paid=True)
        with self.assertRaisesRegex(recovery.BudgetStop, "recovery_non503_failure"):
            await self.ask(restarted)
        self.assertEqual(restarted_provider.requests, [])

    async def test_inflight_record_blocks_resending_after_restart(self):
        client = self.client(provider=FakeProvider(response()), paid=True)
        await self.ask(client)
        await client.close()
        path, = (self.folder / "calls").glob("*.json")
        record = json.loads(path.read_text())
        record["status"] = "reserved"
        record.pop("result")
        record.pop("result_sha256")
        path.write_text(json.dumps(record))
        provider = FakeProvider(response())
        restarted = self.client(provider=provider, paid=True)
        with self.assertRaisesRegex(recovery.BudgetStop, "unresolved_recovery_request"):
            await self.ask(restarted)
        self.assertEqual(provider.requests, [])
        self.assertEqual(restarted.summary()["pending_calls"], 1)

    async def test_historical_invalid_json_follows_existing_next_attempt(self):
        history = [historical(content="invalid JSON"),
                   historical(index=1, retry_index=1)]
        provider = FakeProvider()
        client = self.client(history, provider=provider)
        self.assertEqual(await self.ask(client), {"answer": 42})
        self.assertEqual(client.history_consumed, 2)
        self.assertEqual(provider.requests, [])

    async def test_historical_invalid_json_does_not_create_missing_json_attempt(self):
        provider = FakeProvider(response())
        client = self.client([historical(content="invalid JSON")], provider=provider, paid=True)
        with self.assertRaisesRegex(recovery.BudgetStop, "new_parse_resampling_disabled"):
            await self.ask(client)
        self.assertEqual(provider.requests, [])

    async def test_new_malformed_json_stops_without_resampling(self):
        provider = FakeProvider(response("invalid JSON"), response())
        client = self.client(provider=provider, paid=True)
        with self.assertRaisesRegex(recovery.BudgetStop, "recovered_response_invalid_json_no_resampling"):
            await self.ask(client)
        self.assertEqual(len(provider.requests), 1)

    async def test_recovered_malformed_json_stops_without_resampling(self):
        old = historical(status="unknown_failure", http_status=503)
        provider = FakeProvider(response("invalid JSON"), response())
        client = self.client([old], provider=provider, paid=True)
        with self.assertRaisesRegex(recovery.BudgetStop, "recovered_response_invalid_json_no_resampling"):
            await self.ask(client)
        self.assertEqual(len(provider.requests), 1)

    async def test_historical_body_mismatch_stops_before_network(self):
        provider = FakeProvider(response())
        client = self.client([historical()], provider=provider, paid=True)
        with self.assertRaisesRegex(recovery.LedgerError, "historical_request_body_mismatch"):
            await client.call_json("A different prompt", max_tokens=64)
        self.assertEqual(provider.requests, [])
        self.assertEqual(client.history_consumed, 0)

    async def test_changed_history_is_rejected_on_restart(self):
        old = historical()
        client = self.client([old])
        await client.close()
        old["result"]["content"] = '{"changed": true}'
        with self.assertRaisesRegex(recovery.LedgerError, "recovery_identity_changed"):
            self.client([old])

    async def test_missing_usage_blocks_retry_and_resume(self):
        provider = FakeProvider(response(usage={}), response())
        client = self.client(provider=provider, paid=True)
        with self.assertRaisesRegex(recovery.BudgetStop, "recovery_provider_usage_missing_or_invalid"):
            await self.ask(client)
        self.assertEqual(len(provider.requests), 1)
        await client.close()
        restarted_provider = FakeProvider(response())
        restarted = self.client(provider=restarted_provider, paid=True)
        with self.assertRaisesRegex(recovery.BudgetStop, "recovery_provider_usage_missing_or_invalid"):
            await self.ask(restarted)
        self.assertEqual(restarted_provider.requests, [])

    async def test_paid_disabled_refuses_new_provider_request(self):
        provider = FakeProvider(response())
        client = self.client(provider=provider)
        with self.assertRaisesRegex(recovery.BudgetStop, "paid_recovery_disabled"):
            await self.ask(client)
        self.assertEqual(provider.requests, [])

    async def test_plain_call_preserves_historical_content(self):
        provider = FakeProvider()
        old = historical(content="plain response", as_json=False)
        client = self.client([old], provider=provider)
        actual = await client.call(PROMPT, max_tokens=64)
        self.assertEqual(actual.content, "plain response")
        self.assertEqual(actual.usage, USAGE)
        self.assertEqual(provider.requests, [])

    async def test_simultaneous_client_is_rejected_until_close(self):
        client = self.client()
        with self.assertRaisesRegex(recovery.LedgerError, "recovery_client_already_running"):
            self.client()
        await client.close()
        restarted = self.client()
        self.assertEqual(restarted.summary()["external_api_calls"], 0)


if __name__ == "__main__":
    unittest.main()

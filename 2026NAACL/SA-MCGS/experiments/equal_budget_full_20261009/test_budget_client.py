"""Offline regression tests: no model downloads or real inference requests."""
import asyncio
import json
import sys
import tempfile
import unittest
from collections import UserDict
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from budget_client import BudgetClient, BudgetStop, GlobalLedger, LedgerError


class FakeTokenizer:
    name_or_path = "offline-fake"
    chat_template = "test-v1"
    special_tokens_map = {}

    def encode(self, text, add_special_tokens=False):
        return list(range(len(text.split())))

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, **kwargs):
        return list(range(3 + sum(3 + len(m['content'].split()) for m in messages)))


class FakeResponse:
    def __init__(self, content, prompt, output, missing=False):
        self.model = 'local-model'
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]
        self.usage = None if missing else {
            'prompt_tokens': prompt, 'completion_tokens': output, 'total_tokens': prompt+output,
            'prompt_tokens_details': {'cached_tokens': 2},
            'completion_tokens_details': {'reasoning_tokens': 1}}

    def model_dump(self, mode='json'):
        return {'model': self.model, 'usage': self.usage,
                'choices': [{'message': {'content': self.choices[0].message.content}}]}


class FakeProvider:
    def __init__(self, outputs=None, missing=False, mismatch=0):
        self.outputs = list(outputs or [])
        self.requests = []
        self.missing, self.mismatch = missing, mismatch
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        output = self.outputs.pop(0) if self.outputs else '{"ok": true}'
        if isinstance(output, BaseException):
            raise output
        prompt = len(FakeTokenizer().apply_chat_template(kwargs['messages'], True, True))
        return FakeResponse(output, prompt+self.mismatch, min(4, kwargs['max_tokens']), self.missing)

    async def close(self):
        pass


class LocalBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'ledger.jsonl'
        self.ledgers = []
        self.clients = []
        self.ledger = await self.open_ledger()

    async def open_ledger(self):
        ledger = GlobalLedger(self.path)
        self.ledgers.append(ledger)
        await ledger.initialize()
        return ledger

    async def asyncTearDown(self):
        for c in self.clients:
            await c.close()
        for ledger in self.ledgers:
            await ledger.close()
        self.temp.cleanup()

    def client(self, ledger=None, provider=None, cap=None, method='sa', model='local-model', **kw):
        provider = provider or FakeProvider()
        c = BudgetClient(ledger=ledger or self.ledger, case_id='c1', model=model,
                         method=method, tokenizer=FakeTokenizer(), token_cap=cap,
                         provider_client=provider, **kw)
        self.clients.append(c)
        return c, provider

    async def test_exact_count_full_usage_output_request_and_sa_budget(self):
        c, provider = self.client(chat_template_kwargs={'enable_thinking': False})
        c.set_phase('sa')
        result = await c.call('hello world', max_tokens=2048)
        self.assertEqual(c.token_usage['total_tokens'], 12)
        self.assertEqual(result.usage['completion_tokens_details']['reasoning_tokens'], 1)
        self.assertEqual(provider.requests[0]['max_tokens'], 2048)
        self.assertEqual(provider.requests[0]['extra_body']['chat_template_kwargs'], {'enable_thinking': False})
        self.assertEqual(await self.ledger.freeze_budget('c1', 'local-model'), 12)
        self.assertEqual(await self.ledger.freeze_budget('c1', 'local-model'), 12)

    async def test_dynamic_output_and_actual_selector_reserve(self):
        c, provider = self.client(cap=50, method='full-scc')
        c.set_selector_reserve(20)
        self.assertEqual(c.remaining_tokens, 30)
        await c.call('hello', max_tokens=12000)
        self.assertEqual(provider.requests[0]['max_tokens'], 23)
        self.assertEqual(c.remaining_tokens, 19)
        c.set_phase('selector')
        self.assertEqual(c.remaining_tokens, 39)
        await c.call('judge', max_tokens=256)
        self.assertEqual(provider.requests[1]['max_tokens'], 32)
        self.assertEqual(c.token_usage['total_tokens'], 22)

    async def test_transformers_batch_encoding_mapping(self):
        c, provider = self.client()
        original = c.tokenizer.apply_chat_template
        c.tokenizer.apply_chat_template = lambda *a, **kw: UserDict(input_ids=original(*a, **kw))
        await c.call('hello', max_tokens=20)
        self.assertEqual(c.token_usage['prompt_tokens'], 7)

    async def test_no_artificial_candidate_count_cap(self):
        c, p = self.client(cap=200, method='lea')
        while True:
            try:
                await c.call('hello', max_tokens=20)
            except BudgetStop as e:
                self.assertEqual(e.reason, 'no_output_budget')
                break
        self.assertGreater(len(p.requests), 12)
        self.assertLessEqual(c.token_usage['accounted_tokens'], 200)

    async def test_resume_advances_virtual_prefix_instead_of_precharging_all_calls(self):
        c, p = self.client(cap=100, method='lea')
        for text in ['one', 'two', 'three']:
            await c.call(text, max_tokens=30)
        self.assertEqual(c.token_usage['total_tokens'], 33)
        await self.ledger.close()
        reopened = await self.open_ledger()
        replay, no_network = self.client(ledger=reopened, cap=100, method='lea')
        self.assertEqual(replay.token_usage['total_tokens'], 0)
        self.assertEqual(replay.remaining_tokens, 100)
        for i, text in enumerate(['one', 'two', 'three'], 1):
            await replay.call(text, max_tokens=30)
            self.assertEqual(replay.token_usage['total_tokens'], i*11)
            self.assertEqual(replay.remaining_tokens, 100-i*11)
        self.assertFalse(no_network.requests)
        await replay.call('four', max_tokens=30)
        self.assertEqual(len(no_network.requests), 1)
        self.assertEqual((await reopened.summary())['calls'], 4)

    async def test_changed_resume_request_fails_closed_without_resampling(self):
        c, _ = self.client(cap=100, method='lea')
        await c.call('original', max_tokens=20)
        replay, p = self.client(cap=100, method='lea')
        with self.assertRaises(LedgerError):
            await replay.call('changed', max_tokens=20)
        self.assertFalse(p.requests)

    async def test_unknown_transport_retains_hold_and_never_retries_or_freezes(self):
        c, p = self.client(provider=FakeProvider([TimeoutError('do not print this')]))
        with self.assertRaises(BudgetStop):
            await c.call_json('hello', max_tokens=30)
        self.assertEqual(len(p.requests), 1)
        self.assertEqual(c.token_usage['held_tokens'], 37)
        with self.assertRaises(BudgetStop):
            await self.ledger.freeze_budget('c1', 'local-model')
        await self.ledger.close()
        replay, no_network = self.client(ledger=await self.open_ledger())
        with self.assertRaises(BudgetStop):
            await replay.call_json('hello', max_tokens=30)
        self.assertFalse(no_network.requests)
        self.assertEqual(replay.token_usage['held_tokens'], 37)

    async def test_missing_usage_is_held_and_cannot_define_sa_budget(self):
        c, p = self.client(provider=FakeProvider(missing=True))
        with self.assertRaises(BudgetStop):
            await c.call('hello', max_tokens=30)
        self.assertEqual(c.token_usage['held_tokens'], 37)
        with self.assertRaises(BudgetStop):
            await self.ledger.freeze_budget('c1', 'local-model')

    async def test_tokenizer_mismatch_recorded_and_blocks_new_calls(self):
        c, p = self.client(provider=FakeProvider(mismatch=1))
        with self.assertRaises(BudgetStop) as e:
            await c.call('hello', max_tokens=30)
        self.assertEqual(e.exception.reason, 'tokenizer_or_provider_usage_mismatch')
        self.assertEqual((await self.ledger.summary())['usage_mismatch_calls'], 1)
        with self.assertRaises(BudgetStop):
            await c.call('another', max_tokens=30)
        self.assertEqual(len(p.requests), 1)
        with self.assertRaises(BudgetStop):
            await self.ledger.freeze_budget('c1', 'local-model')

    async def test_three_json_attempts_failure_fallback_usage_still_freezes(self):
        c, p = self.client(provider=FakeProvider(['bad', 'bad', 'bad']))
        self.assertEqual(await c.call_json('hello', max_tokens=30), {})
        self.assertEqual(len(p.requests), 3)
        report = await self.ledger.summary()
        self.assertEqual(report['retry_calls'], 2)
        self.assertEqual(report['parse_failure_calls'], 3)
        self.assertEqual(await self.ledger.freeze_budget('c1', 'local-model'), 33)
        # Selector always has one attempt, regardless of legacy retries=2.
        judge, jp = self.client(method='full-scc', cap=200, provider=FakeProvider(['bad', 'bad']))
        judge.set_phase('selector')
        self.assertEqual(await judge.call_json('judge', max_tokens=30), {})
        self.assertEqual(len(jp.requests), 1)

    async def test_response_cache_recovers_crash_before_settlement(self):
        c, p = self.client()
        original = self.ledger.finish

        async def crash(*args, **kwargs):
            raise LedgerError('simulated_crash')

        self.ledger.finish = crash
        with self.assertRaises(LedgerError):
            await c.call('hello', max_tokens=30)
        self.ledger.finish = original
        await self.ledger.close()
        reopened = await self.open_ledger()
        replay, no_network = self.client(ledger=reopened)
        await replay.call('hello', max_tokens=30)
        self.assertFalse(no_network.requests)
        self.assertEqual(replay.token_usage['total_tokens'], 11)
        self.assertEqual(await reopened.freeze_budget('c1', 'local-model'), 11)

    async def test_budget_stop_bypasses_search_exception_fallback(self):
        c, p = self.client(cap=5, method='lea')
        swallowed = False
        try:
            try:
                await c.call('hello', max_tokens=30)
            except Exception:
                swallowed = True
        except BudgetStop:
            pass
        else:
            self.fail('Expected BudgetStop')
        self.assertFalse(swallowed)
        self.assertFalse(p.requests)

    async def test_external_endpoint_rejected_and_model_accounting_isolated(self):
        with self.assertRaises(ValueError):
            self.client(base_url='https://api.openai.com/v1')
        a, _ = self.client(model='model-A')
        b, _ = self.client(model='model-B')
        await asyncio.gather(a.call('one', max_tokens=20), b.call('two words', max_tokens=20))
        self.assertEqual(await self.ledger.freeze_budget('c1', 'model-A'), 11)
        self.assertEqual(await self.ledger.freeze_budget('c1', 'model-B'), 12)


if __name__ == '__main__':
    unittest.main()

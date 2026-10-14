"""Offline candidate boundary, cache, and accounting tests."""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent));sys.path.insert(0, str(HERE))
from test_api_budget_client import FakeProvider, FakeResponse
from api_adapter import BudgetClient, GlobalLedger, BudgetStop, LedgerError, CandidateServiceFailure, wrap_candidate_functions, guard


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory();self.root = Path(self.temp.name)
        (self.root/'legacy_call_ids.json').write_text('[]')
        self.clients=[];self.ledgers=[]

    async def asyncTearDown(self):
        for c in self.clients:await c.close()
        for l in self.ledgers:await l.close()
        self.temp.cleanup()

    async def client(self, responses=None):
        ledger=GlobalLedger(self.root/'ledger.jsonl');self.ledgers.append(ledger);await ledger.initialize()
        p=FakeProvider(responses)
        c=BudgetClient(ledger=ledger,case_id='c',method='lea',model='gemini-2.5-pro',token_cap=100000,provider_client=p)
        self.clients.append(c);return c,ledger,p

    def methods(self):
        async def lea(client,*args,**kwargs):
            windows=[]
            for prompt in ('window1','window2'):
                try:result=await client.call_json(prompt,max_tokens=2048)
                except Exception:result={'default_score':0.5}
                windows.append(result)
            return {'windows':windows}
        async def naive(client,*args,**kwargs):return await client.call_json('full',max_tokens=12000)
        m=SimpleNamespace(cost=SimpleNamespace(run_lea=lea,battle=SimpleNamespace(run_naive=naive)))
        wrap_candidate_functions(m);return m

    async def test_failed_second_window_rejects_whole_candidate_next_candidate_succeeds(self):
        c,l,p=await self.client([FakeResponse(),TimeoutError('transient'),FakeResponse(),FakeResponse(),TimeoutError('later')])
        methods=self.methods();pool=[]
        with self.assertRaises(CandidateServiceFailure):pool.append(await methods.cost.run_lea(c))
        self.assertEqual(pool,[])
        held=c.token_usage['held_tokens'];self.assertGreater(held,8192)
        pool.append(await methods.cost.run_lea(c))
        self.assertEqual(pool,[{'windows':[{'ok':True},{'ok':True}]}])
        with self.assertRaises(CandidateServiceFailure):pool.append(await methods.cost.run_lea(c))
        self.assertEqual(len(pool),1)
        self.assertGreater(c.token_usage['held_tokens'],held)
        # Existing successful candidates survive; selector uses the same client
        # and can be called after ended failures without releasing reservations.
        c.set_phase('selector')
        self.assertEqual(await c.call_json('judge',max_tokens=256),{'ok':True})
        self.assertEqual(len(p.requests),6)
        self.assertEqual(c.summary()['unknown_failure_calls'],2)
        await l.close()
        replay,_,no_network=await self.client()
        m=self.methods()
        with self.assertRaises(CandidateServiceFailure):await m.cost.run_lea(replay)
        await m.cost.run_lea(replay)
        with self.assertRaises(CandidateServiceFailure):await m.cost.run_lea(replay)
        replay.set_phase('selector');await replay.call_json('judge',max_tokens=256)
        self.assertFalse(no_network.requests)
        self.assertEqual(replay.token_usage,c.token_usage)

    async def test_selector_error_is_not_converted_and_new_cancellation_not_swallowed(self):
        c,_,p=await self.client([TimeoutError('selector'),asyncio.CancelledError()])
        c.set_phase('selector')
        with self.assertRaises(BudgetStop):await c.call_json('judge',max_tokens=256)
        c.set_phase('candidate')
        with self.assertRaises(asyncio.CancelledError):await self.methods().cost.run_lea(c)
        self.assertEqual(len(p.requests),2)

    async def test_missing_usage_still_blocks_and_failure_cache_corruption_not_hidden(self):
        c,l,p=await self.client([FakeResponse(missing=True)])
        with self.assertRaises(BudgetStop):await self.methods().cost.run_lea(c)
        with self.assertRaises(BudgetStop):await self.methods().cost.run_lea(c)
        self.assertEqual(len(p.requests),1)

    async def test_failed_cache_missing_is_ledger_error(self):
        c,l,_=await self.client([TimeoutError('offline')])
        with self.assertRaises(CandidateServiceFailure):await self.methods().cost.run_lea(c)
        (self.root/c.last_call_record['cache_file']).unlink()
        await l.close()
        replay,_,p=await self.client()
        with self.assertRaises(LedgerError):await self.methods().cost.run_lea(replay)
        self.assertFalse(p.requests)

    async def test_reserved_still_blocks_new_request(self):
        c,l,p=await self.client()
        await l.reserve(owner=c.owner,token_cap=c.token_cap,fingerprint=c.fingerprint,
            request_key='inflight',request_hash='hash',phase='candidate',input_tokens=100,
            max_output=100,selector_reserve=0,requested_max_output=100,cache_file='unused',retry_index=0)
        with self.assertRaises(BudgetStop) as error:await self.methods().cost.run_lea(c)
        self.assertEqual(error.exception.reason,'unresolved_prior_request')
        self.assertFalse(p.requests)

    async def test_safe_provider_error_details_in_durable_ledger(self):
        c,l,_=await self.client([TimeoutError('Bearer secret-value and sk-secretvalue')])
        with self.assertRaises(CandidateServiceFailure):await self.methods().cost.run_lea(c)
        row=c.last_call_record
        self.assertIn('[REDACTED]',row['error_message_safe'])
        self.assertNotIn('secret-value',l.path.read_text())
        self.assertNotIn('sk-secretvalue',l.path.read_text())

    async def test_historical_transport_successor_replays_without_new_payment(self):
        class InternalServerError(Exception):status_code=503
        oldledger=guard.transport.GlobalLedger(self.root/'ledger.jsonl');self.ledgers.append(oldledger)
        await oldledger.initialize()
        old=guard.transport.BudgetClient(ledger=oldledger,case_id='c',method='lea',model='gemini-2.5-pro',
            token_cap=100000,provider_client=FakeProvider([InternalServerError(),FakeResponse()]))
        self.clients.append(old)
        async def no_wait(seconds):pass
        old._transport_sleep=no_wait
        await old.call_json('hello',max_tokens=2048)
        ids=list(oldledger._calls)
        self.assertEqual(len(ids),2)
        await oldledger.close()
        (self.root/'legacy_call_ids.json').write_text(json.dumps(ids))
        replay,_,network=await self.client()
        self.assertEqual(await replay.call_json('hello',max_tokens=2048),{'ok':True})
        self.assertFalse(network.requests)
        self.assertEqual(replay.token_usage,old.token_usage)


if __name__=='__main__':unittest.main()

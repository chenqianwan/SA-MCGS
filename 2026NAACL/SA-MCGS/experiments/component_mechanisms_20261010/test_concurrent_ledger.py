"""Four simultaneous mock provider calls and durable failure handling; no network."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'science/repo'))
UPSTREAM=ROOT.parent/'equal_budget_full_20261009'
sys.path.insert(0,str(UPSTREAM))
from budget_client import BudgetClient, BudgetStop
from concurrent_ledger import ConcurrentLedger


class Tokenizer:
    name_or_path='offline-tokenizer';chat_template='test';special_tokens_map={}
    def apply_chat_template(self,messages,**kwargs):
        return list(range(3+sum(3+len(m['content'].split()) for m in messages)))
    def encode(self,text,**kwargs):return list(range(len(text.split())))


class Response:
    def __init__(self,body):
        self.model=body['model']
        self.content=json.dumps({'id':body['messages'][-1]['content']})
        self.choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        n=len(Tokenizer().apply_chat_template(body['messages']))
        self.usage={'prompt_tokens':n,'completion_tokens':4,'total_tokens':n+4}
    def model_dump(self,mode='json'):
        return {'model':self.model,'usage':self.usage,'choices':[{'message':{'content':self.content}}]}


class Provider:
    def __init__(self,target=4,fail_index=None):
        self.target=target;self.fail_index=fail_index;self.started=0;self.active=0;self.peak=0
        self.ready=asyncio.Event();self.requests=[]
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    async def create(self,**body):
        i=self.started;self.started+=1;self.active+=1;self.peak=max(self.active,self.peak)
        self.requests.append(body)
        if self.started>=self.target:self.ready.set()
        await asyncio.wait_for(self.ready.wait(),1)
        await asyncio.sleep((self.target-i)*.003)
        self.active-=1
        if i==self.fail_index:raise TimeoutError('synthetic unknown provider outcome')
        return Response(body)
    async def close(self):pass


class ConcurrentLedgerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'ledger.jsonl'
        self.ledger=ConcurrentLedger(self.path);await self.ledger.initialize();self.clients=[]
    async def asyncTearDown(self):
        for c in self.clients:await c.close()
        await self.ledger.close();self.temp.cleanup()
    def client(self,provider):
        c=BudgetClient(ledger=self.ledger,case_id='case',method='full',model='model',
                       tokenizer=Tokenizer(),provider_client=provider,token_cap=None,
                       base_url='http://127.0.0.1:19081/v1')
        c.set_phase('sa');self.clients.append(c);return c
    async def test_four_calls_inflight_exact_accounting_and_parse_provenance(self):
        provider=Provider();client=self.client(provider)
        results=await asyncio.gather(*(client.call_json(f'node {i}',max_tokens=20) for i in range(4)))
        self.assertEqual(provider.peak,4);self.assertEqual([r['id'] for r in results],[f'node {i}' for i in range(4)])
        summary=await self.ledger.summary()
        self.assertEqual(summary['calls'],4);self.assertEqual(summary['total_tokens'],48)
        self.assertEqual(summary['held_calls'],0);self.assertEqual(summary['usage_mismatch_calls'],0)
        records=self.ledger.owner_records('case','model','full')
        self.assertEqual(len({r['call_id'] for r in records}),4)
        self.assertTrue(all(r['parse_events']==[{'event':'parse','call_id':r['call_id'],'outcome':'dict'}] for r in records))
    async def test_reopened_reserved_call_cannot_admit_new_request(self):
        await self.ledger.reserve(owner=('case','model','full'),token_cap=None,fingerprint='fp',
             request_key='old',request_hash='oldhash',phase='sa',input_tokens=8,max_output=20,
             selector_reserve=0,requested_max_output=20,cache_file='old.json',retry_index=0)
        await self.ledger.close();self.ledger=ConcurrentLedger(self.path);await self.ledger.initialize()
        with self.assertRaises(BudgetStop):
            await self.ledger.reserve(owner=('case','model','full'),token_cap=None,fingerprint='fp',
                 request_key='new',request_hash='newhash',phase='sa',input_tokens=8,max_output=20,
                 selector_reserve=0,requested_max_output=20,cache_file='new.json',retry_index=0)
        self.assertEqual((await self.ledger.summary())['calls'],1)
    async def test_unknown_outcome_retained_and_later_requests_blocked(self):
        provider=Provider(fail_index=0);client=self.client(provider)
        rows=await asyncio.gather(*(client.call_json(f'node {i}',max_tokens=20) for i in range(4)),return_exceptions=True)
        self.assertEqual(sum(isinstance(r,BudgetStop) for r in rows),1)
        summary=await self.ledger.summary()
        self.assertEqual(summary['calls'],4);self.assertEqual(summary['held_calls'],1)
        self.assertEqual(summary['total_tokens'],36);self.assertEqual(summary['held_tokens'],28)
        with self.assertRaises(BudgetStop):await client.call_json('new request',max_tokens=20)
        self.assertEqual(provider.started,4)
    async def test_native_gather_failure_drains_other_three_calls_before_usage(self):
        from cluster_runner import drain_rollouts
        provider=Provider(fail_index=3);client=self.client(provider)
        class Native:
            async def search(self):
                async def run_one(i):return await client.call_json(f'node {i}',max_tokens=20)
                return await asyncio.gather(*(run_one(i) for i in range(4)))
        before=set(asyncio.all_tasks())
        with self.assertRaises(BudgetStop):await Native().search()
        self.assertGreater(provider.active,0)
        await drain_rollouts(before)
        self.assertEqual(provider.active,0)
        summary=await self.ledger.summary()
        self.assertEqual(summary['completed_with_usage'],3)
        self.assertEqual(summary['pending_calls'],0)
        self.assertEqual(summary['unknown_failure_calls'],1)
        self.assertEqual(summary['total_tokens'],36)
        self.assertEqual(summary['held_tokens'],28)


if __name__=='__main__':unittest.main()

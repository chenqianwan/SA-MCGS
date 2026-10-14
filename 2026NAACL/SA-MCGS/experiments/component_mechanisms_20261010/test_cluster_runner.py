"""Offline tests for identity, exclusivity, failure retention and isolation; no HTTP."""
import asyncio
import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import cluster_runner as runner


class FakeLedger:
    def __init__(self,path):self.path=Path(path);self.calls=0
    async def initialize(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if not self.path.exists():self.path.write_text('{"event":"header"}\n')
        return self
    def owner_summary(self,*args):
        return {'calls':self.calls,'prompt_tokens':self.calls*10,'completion_tokens':self.calls*5,
                'total_tokens':self.calls*15,'held_calls':0,'usage_mismatch_calls':0}
    async def close(self):pass


class FakeClient:
    created=0
    def __init__(self,**kwargs):self.ledger=kwargs['ledger'];FakeClient.created+=1
    def set_phase(self,phase):pass
    async def close(self):pass


class FakeMachine:
    fail=False
    def __init__(self,*,llm_client,config,arm,seed,trace_callback):
        self.client=llm_client;self.arm=arm;self.callback=trace_callback;self.config=config
    async def search(self,graph,scc):
        self.client.ledger.calls+=1
        with self.client.ledger.path.open('a') as f:f.write('{"event":"reserve"}\n')
        if FakeMachine.fail:raise RuntimeError('synthetic infrastructure failure')
        self.callback({'iteration':1,'window':['a','b'],'selection':{'mode':self.arm}})
        return {'ranking_by_risk':[['a',.9],['b',.5]],'evidence_risk_subgraph_nodes':['a'],
                'total_iterations':60,'trace_events':[{'iteration':i+1} for i in range(60)],
                'mechanism_audit':{'arm':self.arm}}


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.patch=patch.object(runner,'ROOT',self.root);self.patch.start()
        self.case={'case_uid':'uid','case_id':'case','case_order':1,'domain':'test',
                   'planned_scc_clause_ids':['a','b'],'planned_scc_fingerprint':'fp'}
        self.replica={'id':'llama-0','model_key':'llama','base_url':'http://127.0.0.1:19081/v1'}
        self.cfg={'alias':'llama-3.1-8b-instruct'}
        graph=types.SimpleNamespace(clauses={x:types.SimpleNamespace(title=x,content=x) for x in ['a','b']},edges=[])
        scc=types.SimpleNamespace(id='test-scc',clause_ids=['a','b'],size=2)
        self.cost=types.SimpleNamespace(prepare_injected_case=lambda *_:(graph,scc,'a',{'injected_risk_nodes':['a']}),
             make_mcgs_config=lambda args:{'alphago_mcgs':{'budget':60,'concurrency':4}},
             battle=types.SimpleNamespace(DOMAIN_MCGS_PROMPTS={'test':lambda *_:'synthetic'}))
        self.support=types.SimpleNamespace(metrics=lambda result,*args:{'valid':bool(result)})
        self.loaded=(None,self.cost,None,{},[self.case])
        self.module=patch.dict(sys.modules,{'budget_client':types.SimpleNamespace(GlobalLedger=FakeLedger,BudgetClient=FakeClient),
                               'concurrent_ledger':types.SimpleNamespace(ConcurrentLedger=FakeLedger)})
        self.module.start();FakeClient.created=0;FakeMachine.fail=False
    def tearDown(self):
        self.module.stop();self.patch.stop();self.temp.cleanup()
    async def run_one(self,arm='full',recover=False):
        folder=self.root/'results/llama/uid'/arm;folder.mkdir(parents=True,exist_ok=True)
        return await runner.run_task(self.case,arm,self.replica,self.cfg,None,{},self.support,self.loaded,
                                    FakeMachine,'protocol','runtime',recover)
    async def test_complete_result_is_retained_without_resampling(self):
        first=await self.run_one();second=await self.run_one(recover=True)
        self.assertEqual(first,second);self.assertEqual(FakeClient.created,1)
        self.assertEqual(first['usage']['total_tokens'],15)
        self.assertEqual(first['status'],'complete');self.assertEqual(first['result']['ranking'][0][0],'a')
        self.assertEqual(len((self.root/'results/llama/uid/full/trace.jsonl').read_text().splitlines()),1)
    async def test_partial_infrastructure_failure_cannot_be_quality_rerun(self):
        FakeMachine.fail=True
        first=await self.run_one();FakeMachine.fail=False
        second=await self.run_one(recover=True)
        self.assertEqual(first,second);self.assertEqual(first['status'],'infrastructure_failure')
        self.assertEqual(FakeClient.created,1)
    async def test_each_arm_has_independent_client_and_ledger(self):
        a=await self.run_one('full');b=await self.run_one('random_windows')
        self.assertEqual(FakeClient.created,2);self.assertEqual(a['usage'],b['usage'])
        self.assertNotEqual(a['arm'],b['arm'])
    async def test_invalid_native_output_preserved_separately_and_never_rerun(self):
        self.support.metrics=lambda result,*args:{'valid':False}
        first=await self.run_one();second=await self.run_one(recover=True)
        self.assertEqual(first['status'],'strict_experiment_failure');self.assertIsNone(first['result'])
        self.assertEqual(first,second);self.assertEqual(FakeClient.created,1)
        raw=json.loads((self.root/'results/llama/uid/full/raw_result.json').read_text())
        self.assertEqual(raw['model'],'llama-3.1-8b-instruct')
        self.assertEqual(raw['scc_clause_ids'],['a','b'])
        self.assertEqual(raw['injected_risk_nodes'],['a'])
    def test_loopback_whitelist(self):
        runner.local_endpoint('http://127.0.0.1:19081/v1')
        for url in ['https://api.openai.com/v1','http://localhost:19081/v1',
                    'http://127.0.0.1:1234/v1','http://user:secret@127.0.0.1:19081/v1',
                    'http://127.0.0.1:19081/v1?api_key=secret']:
            with self.assertRaises(ValueError):runner.local_endpoint(url)
    def test_task_lock_is_exclusive(self):
        a=runner.acquire_task(self.root/'lock');self.assertIsNotNone(a)
        self.assertIsNone(runner.acquire_task(self.root/'lock'))
        a.close();b=runner.acquire_task(self.root/'lock');self.assertIsNotNone(b);b.close()
    def test_queue_has_exactly_400_tasks_per_model(self):
        plan=[dict(self.case,case_uid=f'uid-{i}') for i in range(80)]
        queue=runner.queue_plan(plan)
        self.assertEqual(len(queue),400)
        self.assertEqual(len({(c['case_uid'],a) for c,a in queue}),400)
    def test_wrong_frozen_identity_rejected(self):
        row={'case_uid':'uid','model':'llama','arm':'full','repeat_index':1,
             'protocol_sha256':'protocol','runtime_manifest_sha256':'runtime','status':'complete'}
        runner.terminal_matches(row,self.case,'llama','full','protocol','runtime')
        with self.assertRaises(ValueError):runner.terminal_matches(row,self.case,'llama','full','changed','runtime')


if __name__=='__main__':unittest.main()

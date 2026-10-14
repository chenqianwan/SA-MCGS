"""Offline tests of actual scientific entry points and concurrent cache replay."""
import argparse, asyncio, copy, os, random, tempfile, unittest, re, hashlib, json
from pathlib import Path
from types import SimpleNamespace
import llama_launcher as L

class Tokenizer:
    def apply_chat_template(self,*args,**kwargs):return [1,2,3]
class Usage:
    def model_dump(self):return {'prompt_tokens':3,'completion_tokens':1,'total_tokens':4}
class FakeServer:
    def __init__(self,fail=False):self.started=0;self.fail=fail
    async def create(self,**request):
        if self.fail:raise ConnectionError('deliberate offline transport failure')
        self.started+=1;i=self.started
        await asyncio.sleep((8-((i-1)%8))*0.003)
        ids=re.findall(r'^### ID: (.+)$',request['messages'][-1]['content'],re.M)
        payload={'clause_evaluations':{node:{'risk_score':(int(hashlib.sha256(node.encode()).hexdigest()[:4],16)%80+20)/100,'reasoning':'offline fixture'} for node in ids},'local_risk_subgraph_nodes':ids[:2],'repair_entry_nodes':ids[:1],
            'local_conflict_edges':[{'source':ids[0],'target':ids[1],'reason':'offline fixture'}] if len(ids)>=2 else [],
            'critical_pairs':[{'source':ids[0],'target':ids[1],'same_path_score':0.9,'mutual_incompatibility_score':0.9,'severity_score':0.9,'no_fallback':True}] if len(ids)>=2 else []}
        content='bad JSON' if i==3 else ('{}' if request['max_tokens']==12000 else json.dumps(payload))
        return SimpleNamespace(usage=Usage(),model=L.ALIAS,choices=[SimpleNamespace(message=SimpleNamespace(content=content),finish_reason='stop')])

class ReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupted_batch_replays_prefix_and_guards_changed_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);j=L.ReplayJournal(p,'protocol')
            for i in range(8):j.begin({'prompt':str(i)})
            for i in [5,2,8]:await j.finish(i,j.starts[i-1]['request_sha256'],str(i),'model',{}, {})
            replay=L.ReplayJournal(p,'protocol');observed=[];new=[]
            async def worker(i):
                idx,sig=replay.begin({'prompt':str(i)});saved=await replay.replay(idx)
                if saved is None:new.append(idx);saved=await replay.finish(idx,sig,str(idx),'model',{}, {})
                observed.append(saved['call_index'])
            await asyncio.gather(*(worker(i) for i in range(8)))
            self.assertEqual(observed[:3],[5,2,8]);self.assertEqual(set(new),{1,3,4,6,7})
            self.assertEqual(len(L.rows(p/'responses.jsonl')),8)
            with self.assertRaises(L.IntegrityStop):L.ReplayJournal(p,'protocol').begin({'prompt':'changed'})

class ScientificTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.cost=L.import_science();cls.manifest=L.verify_bundle();cls.graphs=L.restore_graphs(cls.cost,cls.manifest)
        plan=L.read(L.ROOT/'portable_data/llama80_case_plan.json')
        for c in plan:c['source_result_file']=str(L.ROOT/c['source_result_repo_relpath'])
        cls.cost.validate_case_plan(plan,cls.graphs);cls.case=next(c for c in plan if c['main_case_order']==20)
    def args(self,path):return argparse.Namespace(output_dir=path,base_url='http://127.0.0.1:18081/v1',llm_timeout=10,shard_count=2,case_concurrency=2,mode='run',max_model_len=32768,checkpoint_revision='0'*40)
    async def science(self,path,server,method='sa-mcgs'):
        os.environ['LOCAL_VLLM_API_KEY']='offline-test';args=self.args(path);frozen=L.protocol(args,self.cost,self.manifest)
        client=L.make_client_class(self.cost)(args,self.case,method,frozen,Tokenizer());actual=client.client
        server.current_client=client
        client.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=server.create)),close=actual.close)
        graph,scc,root,metadata=self.cost.prepare_injected_case(copy.deepcopy(self.case),self.graphs)
        old=self.cost.make_llm;self.cost.make_llm=lambda *_a,**_k:client;random.seed(42)
        try:r=await self.cost.run_method(L.scientific_args(args),path,self.case,method,graph,scc,root,metadata)
        finally:self.cost.make_llm=old
        return r,client
    async def test_one_shot_empty_json_is_scientific_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            r,_=await self.science(Path(tmp),FakeServer(),'naive-single')
            self.assertEqual(r['error_type'],'ValueError');self.assertIn('no parseable JSON',r['cost_audit_error'])
    async def test_transport_failure_bypasses_scientific_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(L.ProviderFailure):await self.science(Path(tmp),FakeServer(fail=True),'lea')
    async def test_real_concurrent_sa_replay_with_parse_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);original,client=await self.science(p,FakeServer())
            cached=L.rows(p/'call_cache'/self.case['case_id']/'sa-mcgs'/'responses.jsonl')
            self.assertNotEqual([r['call_index'] for r in cached],sorted(r['call_index'] for r in cached))
            self.assertTrue(any(r['content']=='bad JSON' for r in cached))
            blocked=FakeServer(fail=True);resumed,replayed=await self.science(p,blocked)
            self.assertEqual(blocked.started,0)
            self.assertEqual(original['ranking'],resumed['ranking'])
            self.assertEqual(original['core_evidence_risk_subgraph_nodes'],resumed['core_evidence_risk_subgraph_nodes'])
            self.assertEqual([r['request_sha256'] for r in client.call_records],[r['request_sha256'] for r in replayed.call_records])
    async def test_actual_sa_resumes_partially_completed_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);baseline,_=await self.science(p/'original',FakeServer())
            source=p/'original'/'call_cache'/self.case['case_id']/'sa-mcgs'
            requests=L.rows(source/'requests.jsonl');responses=L.rows(source/'responses.jsonl')
            target=p/'resumed'/'call_cache'/self.case['case_id']/'sa-mcgs'
            # The first batch has one parse retry (9 calls). Capture a real prefix
            # part way through the next concurrent batch, with its starts journal.
            prefix=responses[:12];cut=max(r['call_index'] for r in prefix)
            for row in requests[:cut]:L.append(target/'requests.jsonl',row)
            for row in prefix:L.append(target/'responses.jsonl',row)
            by_index={r['call_index']:r for r in responses}
            completion_pos={r['call_index']:i for i,r in enumerate(responses)}
            class RemainingServer:
                def __init__(inner):inner.started=0
                async def create(inner,**request):
                    idx=inner.current_client.journal.next_index
                    inner.started+=1
                    self.assertEqual(request,requests[idx-1]['request'])
                    # Gate on durable completion, not elapsed milliseconds: new server
                    # replies otherwise legitimately choose a different search trajectory.
                    async def wait_turn():
                        while len(L.rows(target/'responses.jsonl')) < completion_pos[idx]:
                            await asyncio.sleep(0.001)
                    await asyncio.wait_for(wait_turn(),10)
                    saved=by_index[idx]
                    return SimpleNamespace(usage=Usage(),model=L.ALIAS,choices=[SimpleNamespace(message=SimpleNamespace(content=saved['content']),finish_reason='stop')])
            resumed,_=await self.science(p/'resumed',RemainingServer())
            self.assertEqual(baseline['ranking'],resumed['ranking'])
            self.assertEqual(baseline['core_evidence_risk_subgraph_nodes'],resumed['core_evidence_risk_subgraph_nodes'])
            self.assertEqual([r['request_sha256'] for r in requests],[r['request_sha256'] for r in L.rows(target/'requests.jsonl')])
if __name__=='__main__':unittest.main()

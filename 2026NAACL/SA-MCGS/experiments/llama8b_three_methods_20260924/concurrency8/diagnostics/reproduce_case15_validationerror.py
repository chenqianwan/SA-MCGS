#!/usr/bin/env python3
"""Replay only cached replies through unchanged scientific SA code; zero API."""
from __future__ import annotations
import argparse,asyncio,copy,importlib.util,json,os,random,shutil,tempfile,traceback
from pathlib import Path
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent;RUN=HERE.parents[1]
launcher=RUN/'runner/llama_launcher.py'
spec=importlib.util.spec_from_file_location('original_frozen_launcher',launcher)
L=importlib.util.module_from_spec(spec);spec.loader.exec_module(L)
SOURCE=RUN/'diagnostics/case15_sa_validationerror_20260924/remote/results/llama80_three_methods'
class Tokenizer:
    def apply_chat_template(self,*_a,**_kw):return [1]
class NeverNetwork:
    def __init__(self):self.pending=[]
    async def create(self,**request):
        self.pending.append(asyncio.current_task())
        await asyncio.Future()
        raise AssertionError('Uncached requests must never receive fabricated responses')
    async def cancel(self):
        for task in self.pending:
            if not task.done():task.cancel()
        if self.pending:await asyncio.gather(*self.pending,return_exceptions=True)
async def main():
    assert os.environ.get('PYTHONHASHSEED')=='42'
    cost=L.import_science();manifest=L.verify_bundle();graphs=L.restore_graphs(cost,manifest)
    plan=L.read(L.ROOT/'portable_data/llama80_case_plan.json')
    for c in plan:c['source_result_file']=str(L.ROOT/c['source_result_repo_relpath'])
    cost.validate_case_plan(plan,graphs);case=next(c for c in plan if c['main_case_order']==15)
    frozen=L.read(SOURCE/'frozen_protocol.json');original_sha=L.sha(launcher)
    assert frozen['launcher_sha256']==original_sha
    cache=SOURCE/'call_cache'/case['case_id']/'sa-mcgs'
    source_hashes={p.name:L.sha(p) for p in cache.glob('*.jsonl')}
    with tempfile.TemporaryDirectory(prefix='case15-cache-replay-') as temporary:
        output=Path(temporary);target=output/'call_cache'/case['case_id']/'sa-mcgs'
        shutil.copytree(cache,target)
        args=argparse.Namespace(output_dir=output,base_url='http://127.0.0.1:18081/v1',llm_timeout=600,
            case_concurrency=4,shard_count=4,shard_index=2,mode='run',max_model_len=131072,
            checkpoint_revision=frozen['checkpoint_revision'])
        assert L.protocol(args,cost,manifest)==frozen
        os.environ['LOCAL_VLLM_API_KEY']='offline-only-no-network'
        client=L.make_client_class(cost)(args,case,'sa-mcgs',frozen,Tokenizer())
        real_sdk=client.client;transport=NeverNetwork()
        async def close():await transport.cancel();await real_sdk.close()
        client.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=transport.create)),close=close)
        old_factory=cost.make_llm;cost.make_llm=lambda *_a,**_kw:client
        graph,scc,root,metadata=cost.prepare_injected_case(copy.deepcopy(case),graphs)
        random.seed(42)
        try:
            result=await asyncio.wait_for(cost.run_method(L.scientific_args(args),output,case,'sa-mcgs',graph,scc,root,metadata),15)
        finally:cost.make_llm=old_factory
        client.journal.assert_consumed()
        assert result['error_type']=='ValidationError'
        assert 'conflicts.2' in result['error'] and 'critical_pairs' in result['error']
        assert source_hashes=={p.name:L.sha(p) for p in cache.glob('*.jsonl')}
        assert source_hashes=={p.name:L.sha(p) for p in target.glob('*.jsonl')}
        saved=L.rows(cache/'responses.jsonl');bad=next(r for r in saved if r['call_index']==6)
        import pydantic
        report={'passed':True,'case_id':case['case_id'],'source_job_id':'395047','api_calls':0,
            'scientific_source_unchanged':True,'launcher_sha256':original_sha,'protocol_sha256':L.digest(frozen),
            'cache_files_sha256':source_hashes,'cache_files_unchanged':True,
            'original_request_start_count':client.journal.original_start_count,
            'replayed_request_start_count':client.journal.next_index,
            'cached_completion_order':client.journal.order,'consumed_cached_response_count':client.journal.cursor,
            'uncached_requests_held_without_network':len(transport.pending),
            'validationerror_is_valueerror_subclass':issubclass(pydantic.ValidationError,ValueError),
            'error_type':result['error_type'],'error':result['error'],'traceback':result['traceback'],
            'bad_response':{'call_index':6,'finish_reason':bad['record']['finish_reason'],'usage':bad['usage'],
                'parsed_conflicts':json.loads(bad['content'])['conflicts'],'content':bad['content']},
            'root_cause':'Model returned a string in conflicts[2]; TranspositionEntry requires a dictionary. The output adapter classified ValidationError by exact class name and omitted this ValueError subclass from terminal scientific failures.',
            'minimal_correction':'Versioned execution adapter should classify this existing model-output ValidationError as strict_experiment_failure. Keep original scientific code, protocol, raw cached response, and error subtype; do not repair JSON or retry for a better response.'}
        L.write(HERE/'case15_validationerror_reproduction.json',report)
        L.write(HERE/'case15_original_cost_result_OFFLINE_DIAGNOSTIC_ONLY.json',result)
        print(json.dumps({k:v for k,v in report.items() if k not in {'traceback','bad_response'}},ensure_ascii=False,indent=2))
if __name__=='__main__':asyncio.run(main())

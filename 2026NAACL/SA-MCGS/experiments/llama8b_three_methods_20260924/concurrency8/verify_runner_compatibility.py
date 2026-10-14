#!/usr/bin/env python3
"""Zero-network verification of scheduling-only 2-to-8 concurrency migration."""
from __future__ import annotations
import argparse
import asyncio
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
RUN=HERE.parent
LAUNCHER=RUN/'runner/llama_launcher.py'
spec=importlib.util.spec_from_file_location('unchanged_llama_launcher',LAUNCHER)
L=importlib.util.module_from_spec(spec);spec.loader.exec_module(L)
REVISION='0e9e39f249a16976918f6564b8830bc894c89659'

def args(path,concurrency):
    return argparse.Namespace(output_dir=path,base_url='http://127.0.0.1:18081/v1',llm_timeout=30,
        case_concurrency=concurrency,shard_count=concurrency,shard_index=0,mode='run',
        max_model_len=131072,checkpoint_revision=REVISION)

class Tokenizer:
    def apply_chat_template(self,*_a,**_kw):return [1,2,3]
class Usage:
    def model_dump(self):return {'prompt_tokens':3,'completion_tokens':5,'total_tokens':8}
class FakeServer:
    def __init__(self,forbid=False):self.calls=0;self.forbid=forbid
    async def create(self,**request):
        self.calls+=1
        if self.forbid:raise AssertionError('Cached prefix should not issue any new request')
        return SimpleNamespace(model=L.ALIAS,usage=Usage(),choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"offline_audit":true}'),finish_reason='stop')])

def attach_fake(client,server):
    real=client.client
    client.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=server.create)),close=real.close)

async def main():
    if os.environ.get('PYTHONHASHSEED')!='42':raise RuntimeError('Start with PYTHONHASHSEED=42')
    launcher_sha=L.sha(LAUNCHER)
    assert launcher_sha==L.read(RUN/'runner_ready.json')['launcher_sha256']
    manifest=L.verify_bundle();cost=L.import_science()
    old=L.protocol(args(Path('/unused-output'),2),cost,manifest)
    new=L.protocol(args(Path('/unused-output'),8),cost,manifest)
    assert old==new
    assert old['sa_mcgs_config']['alphago_mcgs']['concurrency']==8
    original_plan=L.read(L.ROOT/'portable_data/llama80_case_plan.json')
    assignments={str(n):[[c['case_uid'] for index,c in enumerate(original_plan) if index%n==shard] for shard in range(n)] for n in (2,8)}
    expected=[c['case_uid'] for c in original_plan]
    for n in (2,8):
        flat=[uid for group in assignments[str(n)] for uid in group]
        assert len(flat)==80 and len(set(flat))==80 and set(flat)==set(expected)
    graphs=L.restore_graphs(cost,manifest);plan=copy.deepcopy(original_plan)
    for case in plan:case['source_result_file']=str(L.ROOT/case['source_result_repo_relpath'])
    cost.validate_case_plan(plan,graphs);case=next(c for c in plan if c['main_case_order']==20)
    graph,scc,injected,metadata=cost.prepare_injected_case(copy.deepcopy(case),graphs)
    terminal_checks=[]
    with tempfile.TemporaryDirectory(prefix='llama-scheduling-audit-') as temporary:
        path=Path(temporary);a4=args(path,8)
        before_factory=L.make_client_class
        def forbid_factory(*_a,**_kw):raise AssertionError('Terminal result tried to construct a model client')
        L.make_client_class=forbid_factory
        try:
            for method,status in [('lea','complete'),('naive-single','strict_experiment_failure')]:
                result={**metadata,'model':L.MODEL,'case_id':case['case_id'],'cost_audit_method':method,
                    'protocol_sha256':L.digest(old),'completion_status':status,'case_concurrency':2,
                    'scc_clause_ids':list(scc.clause_ids),'scc_size':scc.size,
                    'ranking':[[scc.clause_ids[0],0.5]],'lea_risk_subgraph_nodes':list(scc.clause_ids[:4]),
                    'cost_audit_error':'offline strict-failure fixture' if status!='complete' else None}
                file=L.result_path(a4,case,method);L.write(file,result);before=L.sha(file)
                await L.run_one(cost,a4,case,method,graphs,new,Tokenizer())
                assert L.sha(file)==before
                assert not (path/'call_cache').exists() and not (path/'case_status').exists()
                terminal_checks.append({'method':method,'completion_status':status,'unchanged_bytes':True,
                    'stored_case_concurrency':2,'new_requested_case_concurrency':8,'model_client_constructed':False})
        finally:L.make_client_class=before_factory
    with tempfile.TemporaryDirectory(prefix='llama-cache-migration-audit-') as temporary:
        path=Path(temporary);os.environ['LOCAL_VLLM_API_KEY']='offline-audit-no-real-api'
        cls=L.make_client_class(cost);a2=args(path,2);a4=args(path,8)
        first=cls(a2,case,'sa-mcgs',old,Tokenizer());fake=FakeServer();attach_fake(first,fake)
        parsed=await first.call_json('Offline partial-cache compatibility fixture',temperature=0.4,max_tokens=2048)
        assert parsed=={'offline_audit':True} and fake.calls==1
        await first.close()
        response_file=path/'call_cache'/case['case_id']/'sa-mcgs/responses.jsonl'
        request_file=response_file.parent/'requests.jsonl';before=(L.sha(request_file),L.sha(response_file))
        resumed=cls(a4,case,'sa-mcgs',new,Tokenizer());blocked=FakeServer(forbid=True);attach_fake(resumed,blocked)
        parsed=await resumed.call_json('Offline partial-cache compatibility fixture',temperature=0.4,max_tokens=2048)
        resumed.journal.assert_consumed();await resumed.close()
        assert parsed=={'offline_audit':True} and blocked.calls==0
        assert before==(L.sha(request_file),L.sha(response_file))
        assert resumed.call_records[0]['replayed_from_checkpoint'] is True
        cache_check={'original_localclient_used':True,'initial_fixture_server_calls':1,'resume_fixture_server_calls':0,
            'external_api_calls':0,'request_response_bytes_unchanged':True,'exact_cached_content_replayed':True,
            'all_original_checkpoint_calls_consumed':True}
    report={'passed':True,'read_only_original_runner':True,'external_api_calls':0,'launcher_sha256':launcher_sha,
        'original_runner_ready_sha256':L.sha(RUN/'runner_ready.json'),'protocol_equal':True,
        'protocol_canonical_sha256':L.digest(old),'case_concurrency_part_of_frozen_protocol':False,
        'sa_internal_concurrency_unchanged':8,'model_context_unchanged':131072,
        'old_shard_sizes':[len(x) for x in assignments['2']],
        'new_shard_sizes':[len(x) for x in assignments['8']],
        'coverage_cases':80,'unique_case_uids':80,'both_assignments_cover_all_cases_exactly_once':True,
        'terminal_result_reuse':terminal_checks,'partial_cache_reuse':cache_check,
        'execution_boundary':'Old workers must exit before launching new eight-shard workers; old stride2/4 and new stride8 overlap.',
        'server_max_num_seqs_note':'Server scheduler capacity16-to32 is recorded separately in the new deployment manifest; this test does not assume hardware throughput or memory capacity.'}
    L.write(HERE/'runner_compatibility_verification.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':asyncio.run(main())

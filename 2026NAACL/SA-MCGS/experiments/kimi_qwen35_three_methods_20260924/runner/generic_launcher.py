#!/usr/bin/env python3
"""Two-model execution adapter around unchanged scientific runners.

Every configuration has its own frozen protocol and output/cache root. Scientific
failures remain observations; infrastructure failures are recorded separately.
"""
from __future__ import annotations
import argparse
import asyncio
import collections
import copy
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import sys
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('portable_base',HERE/'base_launcher.py')
L=importlib.util.module_from_spec(spec);spec.loader.exec_module(L)
BASE_PROTOCOL=L.protocol
BASE_VALIDATE=L.validate_result
BASE_CLIENT_FACTORY=L.make_client_class
BASE_REQUEST=L.request_payload
CFG=None
MODEL_REGISTRY={
 'kimi-vl-a3b-instruct':{'repository':'moonshotai/Kimi-VL-A3B-Instruct','port':18082},
 'qwen3.5-9b':{'repository':'Qwen/Qwen3.5-9B','port':18083},
}
class EndpointRecoveryRequired(L.RunStop):pass


def configure(config):
    global CFG
    config=copy.deepcopy(config)
    required={'version','model_key','checkpoint_repository','checkpoint_revision','served_model_name','base_url',
        'dtype','quantization','tensor_parallel_size','max_model_len','trust_remote_code','chat_template_kwargs'}
    if required-set(config):raise L.IntegrityStop('Missing model configuration fields: '+str(sorted(required-set(config))))
    key=config['model_key']
    if config['version']!=1 or key not in MODEL_REGISTRY:raise L.IntegrityStop('Unknown model/configuration version')
    entry=MODEL_REGISTRY[key]
    if config['checkpoint_repository']!=entry['repository'] or config['base_url']!=f"http://127.0.0.1:{entry['port']}/v1":
        raise L.IntegrityStop('Only the configured same-node official model route is allowed')
    if not re.fullmatch('[0-9a-f]{40}',config['checkpoint_revision']):raise L.IntegrityStop('Pinned model revision required')
    if not re.fullmatch('[A-Za-z0-9_.-]+',config['served_model_name']):raise L.IntegrityStop('Invalid served model alias')
    if config['dtype']!='bfloat16' or config['quantization'] is not None or config['tensor_parallel_size']!=1:
        raise L.IntegrityStop('This experiment requires unquantized BF16 on one GPU')
    if not isinstance(config['trust_remote_code'],bool) or not isinstance(config['max_model_len'],int) or config['max_model_len']<12001:
        raise L.IntegrityStop('Invalid tokenizer/context configuration')
    expected_kwargs={'enable_thinking':False} if key=='qwen3.5-9b' else {}
    if config['chat_template_kwargs']!=expected_kwargs:raise L.IntegrityStop('Unexpected reasoning/chat-template mode')
    CFG=config;L.MODEL=key;L.ALIAS=config['served_model_name'];L.CHECKPOINT=config['checkpoint_repository']
    cost=L.import_science()
    # The original branch capped every model whose name contained "qwen" for a
    # historical hosted endpoint. This new local Qwen supports the common12000.
    original=getattr(cost.battle,'_two_model_original_json_cap',cost.battle._model_json_max_tokens)
    cost.battle._two_model_original_json_cap=original
    cost.battle._model_json_max_tokens=lambda model,requested:requested if model==key else original(model,requested)
    return cost


def protocol(args,cost,manifest):
    if CFG is None:raise L.IntegrityStop('Model configuration not loaded')
    return {'version':1,'experiment':'kimi_qwen35_three_methods_20260924','model':L.MODEL,
        'model_config':CFG,'served_model':L.ALIAS,'checkpoint_repository':L.CHECKPOINT,
        'checkpoint_revision':args.checkpoint_revision,'base_url':args.base_url,
        'external_api_cost_usd':0.0,'gpu_resource_cost_not_included':True,
        'base_launcher_sha256':L.sha(HERE/'base_launcher.py'),'producer_sha256':L.sha(Path(__file__)),
        'original_scientific_code_sha256':manifest['unchanged_code_sha256'],
        'bundle_manifest_sha256':L.sha(L.ROOT/'bundle_manifest.json'),
        'canonical_case_plan_sha256':L.sha(L.ROOT/'portable_data/qwen80_case_plan.json'),
        'cases':80,'methods':list(L.METHODS),'expected_results':240,
        'sa_mcgs_config':cost.make_mcgs_config(L.scientific_args(args)),
        'lea':{'window_size':4,'temperature':0.4,'max_tokens':2048,'internal_concurrency':1},
        'one_shot':{'naive_profile':'direct_subgraph','temperature':0.0,'max_tokens':12000,'internal_concurrency':1},
        'legacy_qwen_hosted_output_cap_override':{'enabled':L.MODEL=='qwen3.5-9b',
            'scope':'Only this new local model; original scientific source bytes unchanged',
            'reason':'The historical name-based8192 hosted-provider cap does not apply; both new models use12000'},
        'sdk_max_retries':0,'json_parse_attempts':3,'json_parse_exhaustion_fallback':{},
        'strict_failures_are_terminal':True,
        'schema_failure_policy':'Original ValueError/TypeError/KeyError/AttributeError and output-origin TranspositionEntry ValidationError are scientific strict failures; preserve raw error and traceback',
        'infrastructure_policy':{'max_case_attempts':args.max_case_attempts,'scientific_scores_not_assigned':True,
            'endpoint_recovery_exit_code':75,'per_case_other_errors_continue':True,
            'health_probe_timeout_sec':3,'healthy_endpoint_request_failure':'Record only this cell as infrastructure failure and continue',
            'endpoint_restart_requires':'Transport/timeout/408/429/5xx failure plus failed authenticated models/alias health check'},
        'max_model_len':args.max_model_len,'context_policy':'No truncation; tokenize every real request before transmission',
        'python_rng_seed':42,'python_hash_seed':42,'case_concurrency_is_execution_metadata':True,
        'cache_policy':'Exact request/config plus original completion ordering; old checkpoints never silently discarded',
        'metric_node_fields':{'naive-single':'direct_risk_subgraph_nodes','lea':'lea_risk_subgraph_nodes','sa-mcgs':'core_evidence_risk_subgraph_nodes'}}


def prepare(args,cost,manifest,graphs):
    plan=L.read(L.ROOT/'portable_data/qwen80_case_plan.json')
    for case in plan:
        case['source_model']=case['model'];case['source_case_id']=case['case_id'];case['model']=L.MODEL
        case['case_id']=f"{case['main_case_order']:03d}_{L.MODEL}_{case['domain']}{case['scc_size']}_{case['scc_id']}_{case['template']}"
        case['source_result_file']=str(L.ROOT/case['source_result_repo_relpath'])
    if len(plan)!=80 or len({c['case_uid'] for c in plan})!=80:raise L.IntegrityStop('Expected80 immutable case identities')
    report=cost.validate_case_plan(plan,graphs);frozen=protocol(args,cost,manifest)
    with L.locked(args.output_dir/'locks/init.lock'):
        for name,payload in [('frozen_protocol.json',frozen),('case_plan.json',plan)]:
            file=args.output_dir/name
            if file.exists() and L.read(file)!=payload:raise L.IntegrityStop('Frozen configuration changed: '+name)
            if not file.exists():L.write(file,payload)
    return plan,frozen,report


def request_payload(prompt,temperature,max_tokens,system_prompt,response_format):
    payload=BASE_REQUEST(prompt,temperature,max_tokens,system_prompt,response_format)
    if CFG['chat_template_kwargs']:
        payload['extra_body']={'chat_template_kwargs':copy.deepcopy(CFG['chat_template_kwargs'])}
    return payload

def token_count(tokenizer,request):
    kwargs=(request.get('extra_body') or {}).get('chat_template_kwargs',{})
    ids=tokenizer.apply_chat_template(request['messages'],tokenize=True,add_generation_prompt=True,**kwargs)
    if isinstance(ids,dict) or hasattr(ids,'keys'):ids=ids['input_ids']
    if len(ids) and isinstance(ids[0],(list,tuple)):ids=ids[0]
    return len(ids)

def tokenizer_hashes(args):
    if not args.tokenizer_path:raise L.IntegrityStop('--tokenizer-path is required')
    names={'tokenizer.json','tokenizer_config.json','config.json','special_tokens_map.json','chat_template.jinja',
        'tokenizer.model','vocab.json','merges.txt','tiktoken.model'}
    names.update(p.name for p in args.tokenizer_path.glob('*.py'))
    return {name:L.sha(args.tokenizer_path/name) for name in sorted(names) if (args.tokenizer_path/name).is_file()}

def load_tokenizer(args):
    if not args.tokenizer_path:raise L.IntegrityStop('--tokenizer-path is required')
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(str(args.tokenizer_path),local_files_only=True,trust_remote_code=CFG['trust_remote_code'])


def make_client_class(cost):
    class ScopedClient(BASE_CLIENT_FACTORY(cost)):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);self.active_tasks=set();self.closed=False
        async def call(self,*args,**kwargs):
            task=asyncio.current_task();self.active_tasks.add(task)
            try:return await super().call(*args,**kwargs)
            finally:self.active_tasks.discard(task)
        async def close(self):
            if self.closed:return
            self.closed=True;current=asyncio.current_task()
            pending=[task for task in self.active_tasks if task is not current and not task.done()]
            for task in pending:task.cancel()
            if pending:await asyncio.gather(*pending,return_exceptions=True)
            await super().close()
    return ScopedClient


def is_model_validation_error(result):
    return (result.get('error_type')=='ValidationError'
        and 'for TranspositionEntry' in str(result.get('cost_audit_error') or result.get('error') or '')
        and 'alphago_mcgs.py' in str(result.get('traceback') or '')
        and 'TranspositionEntry(' in str(result.get('traceback') or ''))

def classification(result):
    if not result.get('cost_audit_error'):return 'complete'
    if result.get('error_type') in {'ValueError','TypeError','KeyError','AttributeError'} or is_model_validation_error(result):
        return 'strict_experiment_failure'
    return 'infrastructure_failure'


async def endpoint_health(args):
    """A read-only localhost probe; never spends a model generation request."""
    import httpx
    started=time.time()
    headers={'Authorization':'Bearer '+os.environ.get('LOCAL_VLLM_API_KEY','local-no-external-billing')}
    try:
        async with httpx.AsyncClient(timeout=3.0,trust_env=False) as client:
            response=await client.get(args.base_url+'/models',headers=headers)
            aliases=[item.get('id') for item in response.json().get('data',[])] if response.status_code==200 else []
            return {'healthy':response.status_code==200 and L.ALIAS in aliases,'http_status':response.status_code,
                'returned_models':aliases,'expected_model':L.ALIAS,'elapsed_sec':time.time()-started}
    except Exception as exc:
        return {'healthy':False,'error_type':type(exc).__name__,'error':str(exc)[:1000],
            'expected_model':L.ALIAS,'elapsed_sec':time.time()-started}


def infra_path(args,case,method):return args.output_dir/'infrastructure_failures'/f"{case['case_id']}__{method}.json"
def validate_infra(args,case,method,frozen,payload):
    for key,expected in {'case_id':case['case_id'],'case_uid':case['case_uid'],'model':L.MODEL,
        'cost_audit_method':method,'protocol_sha256':L.digest(frozen),'completion_status':'infrastructure_failure'}.items():
        if payload.get(key)!=expected:raise L.IntegrityStop('Infrastructure terminal identity mismatch: '+key)
    if not payload.get('error_type') or not payload.get('error'):raise L.IntegrityStop('Infrastructure terminal lacks cause')


def record_infra(args,case,method,frozen,error_type,error,attempts,category,details=None):
    scientific=L.result_path(args,case,method);path=infra_path(args,case,method)
    if scientific.exists():raise L.IntegrityStop('Cannot replace a scientific terminal with infrastructure failure')
    if path.exists():
        validate_infra(args,case,method,frozen,L.read(path));return
    payload={'case_id':case['case_id'],'case_uid':case['case_uid'],'model':L.MODEL,'domain':case['domain'],
        'scc_id':case['scc_id'],'scc_size':case['scc_size'],'planned_scc_clause_ids':case['planned_scc_clause_ids'],
        'planned_scc_fingerprint':case['planned_scc_fingerprint'],'main_case_id':case['main_case_id'],
        'main_case_order':case['main_case_order'],'method':method,'cost_audit_method':method,
        'protocol_sha256':L.digest(frozen),'producer_sha256':L.sha(Path(__file__)),
        'completion_status':'infrastructure_failure','infrastructure_category':category,
        'error_type':str(error_type),'error':str(error)[:6000],'attempts':attempts,
        'max_case_attempts':args.max_case_attempts,'scientific_prediction_available':False,
        'external_api_cost_usd':0.0,'recorded_at':time.time(),'details':details or {}}
    validate_infra(args,case,method,frozen,payload);L.write(path,payload)
    L.write(args.output_dir/'case_status'/path.name,{'case_id':case['case_id'],'method':method,
        'state':'infrastructure_failure','error_type':str(error_type),'message':str(error)[:1000],'time':time.time()})


def validate_result(cost,args,case,method,graphs,frozen,result):
    BASE_VALIDATE(cost,args,case,method,graphs,frozen,result)
    if result.get('producer_sha256')!=L.sha(Path(__file__)):raise L.IntegrityStop('Result producer differs from frozen adapter')
    if result['completion_status']=='strict_experiment_failure' and classification(result)!='strict_experiment_failure':
        raise L.IntegrityStop('Recorded scientific failure has an unexpected error category')
    if result.get('error_type')=='ValidationError' and not is_model_validation_error(result):
        raise L.IntegrityStop('Unqualified ValidationError marked as scientific failure')


async def run_one(cost,args,case,method,graphs,frozen,tokenizer):
    with L.locked(args.output_dir/'locks/cases'/f"{case['case_id']}__{method}.lock"):
        path=L.result_path(args,case,method);infra=infra_path(args,case,method)
        if path.exists() and infra.exists():raise L.IntegrityStop('Two conflicting terminal records')
        if path.exists():validate_result(cost,args,case,method,graphs,frozen,L.read(path));return
        if infra.exists():validate_infra(args,case,method,frozen,L.read(infra));return
        attempt_path=args.output_dir/'attempts'/f"{case['case_id']}__{method}.json"
        previous=L.read(attempt_path) if attempt_path.exists() else {'attempts':0}
        if previous.get('protocol_sha256',L.digest(frozen))!=L.digest(frozen):raise L.IntegrityStop('Attempt counter protocol mismatch')
        attempt=int(previous['attempts'])
        if attempt>=args.max_case_attempts:
            record_infra(args,case,method,frozen,'AttemptLimitExceeded','Persistent case attempt limit reached',attempt,'attempt_limit');return
        attempt+=1;L.write(attempt_path,{'attempts':attempt,'protocol_sha256':L.digest(frozen),'started_at':time.time(),'last_state':'running'})
        status=args.output_dir/'case_status'/f"{case['case_id']}__{method}.json"
        L.write(status,{'case_id':case['case_id'],'method':method,'state':'running','attempt':attempt,'time':time.time()})
        client=None;old_factory=cost.make_llm
        try:
            graph,scc,injected,metadata=cost.prepare_injected_case(case,graphs)
            client=make_client_class(cost)(args,case,method,frozen,tokenizer)
            cost.make_llm=lambda *_a,**_kw:client;random.seed(42)
            result=await cost.run_method(L.scientific_args(args),args.output_dir,case,method,graph,scc,injected,metadata)
            client.journal.assert_consumed()
            state=classification(result)
            if state=='infrastructure_failure':
                record_infra(args,case,method,frozen,result.get('error_type','UnknownImplementationError'),
                    result.get('cost_audit_error','Unexpected method exception'),attempt,'implementation_error',
                    {'original_traceback':result.get('traceback'),'usage':result.get('llm_usage_summary')});return
            if method=='lea' and state=='complete':
                ranking=result.get('ranking') or [];result['top1_hit']=bool(ranking and ranking[0][0]==injected)
                result['top3_hit']=injected in [row[0] for row in ranking[:3]]
            result.update({'completion_status':state,'protocol_sha256':L.digest(frozen),'producer_sha256':L.sha(Path(__file__)),
                'checkpoint_repository':L.CHECKPOINT,'checkpoint_revision':args.checkpoint_revision,'base_url':args.base_url,
                'requested_model_id':L.ALIAS,'model_config_sha256':L.digest(CFG),'case_concurrency':args.case_concurrency,
                'internal_concurrency':8 if method=='sa-mcgs' else 1,'python_rng_seed':42,
                'json_parse_exhausted_windows':client.parse_exhausted_windows,'external_api_cost_usd':0.0,
                'main_case_order':case['main_case_order'],'main_case_id':case['main_case_id'],'execution_attempt':attempt,
                'chat_template_kwargs':CFG['chat_template_kwargs'],'original_scientific_source_unchanged':True})
            validate_result(cost,args,case,method,graphs,frozen,result);L.write(path,result)
            L.write(status,{'case_id':case['case_id'],'method':method,'state':state,'attempt':attempt,'result_sha256':L.sha(path),'time':time.time()})
            print(json.dumps({'case':case['main_case_order'],'model':L.MODEL,'method':method,'state':state,'attempt':attempt}),flush=True)
        except L.ProviderFailure as exc:
            # Stop sibling SA calls before deciding whether the endpoint failed.
            # Their cancellations are consequences, not evidence of an outage.
            if client is not None:await client.close()
            failed=[r for r in (client.call_records if client else []) if not r.get('ok') and r.get('error_type')!='CancelledError']
            statuses=[r.get('http_status') for r in failed]
            outage_candidate=not statuses or any(code is None or code in (408,429) or code>=500 for code in statuses)
            health=await endpoint_health(args) if outage_candidate else {'performed':False,'reason':'Request-specific HTTP error'}
            recoverable=outage_candidate and not health['healthy']
            details={'http_statuses':statuses,'failed_calls':[{key:r.get(key) for key in
                ('call_index','request_sha256','error_type','http_status','runtime_sec')} for r in failed],'endpoint_health':health}
            L.write(attempt_path,{'attempts':attempt,'protocol_sha256':L.digest(frozen),'last_state':'provider_failure','error':str(exc),'time':time.time()})
            if not recoverable or attempt>=args.max_case_attempts:
                record_infra(args,case,method,frozen,type(exc).__name__,str(exc),attempt,
                    'provider_request_error' if not recoverable else 'endpoint_attempt_limit',details)
            else:
                L.write(status,{'case_id':case['case_id'],'method':method,'state':'endpoint_recovery_required','attempt':attempt,'error':str(exc),'details':details,'time':time.time()})
            if recoverable:raise EndpointRecoveryRequired(f'{case["case_id"]}/{method}: {exc}') from None
        except (asyncio.CancelledError,KeyboardInterrupt,SystemExit):raise
        except EndpointRecoveryRequired:raise
        except BaseException as exc:
            record_infra(args,case,method,frozen,type(exc).__name__,str(exc),attempt,
                'checkpoint_or_case_integrity_error' if isinstance(exc,L.IntegrityStop) else 'case_execution_error')
        finally:
            cost.make_llm=old_factory
            if client is not None:await client.close()


def summarize(args,plan,cost=None,graphs=None,frozen=None):
    expected={L.result_path(args,case,method).name for case in plan for method in L.METHODS}
    for folder in ('results','infrastructure_failures'):
        extra={p.name for p in (args.output_dir/folder).glob('*.json')}-expected
        if extra:raise L.IntegrityStop('Unexpected terminal files: '+str(sorted(extra)))
    counts={m:collections.Counter() for m in L.METHODS};unresolved=[]
    for case in plan:
        for method in L.METHODS:
            result=L.result_path(args,case,method);infra=infra_path(args,case,method)
            if result.exists() and infra.exists():raise L.IntegrityStop('Conflicting scientific/infrastructure terminals')
            if result.exists():
                payload=L.read(result);validate_result(cost,args,case,method,graphs,frozen,payload)
                counts[method][payload['completion_status']]+=1
            elif infra.exists():
                validate_infra(args,case,method,frozen,L.read(infra));counts[method]['infrastructure_failure']+=1
            else:counts[method]['unresolved']+=1;unresolved.append({'case_id':case['case_id'],'method':method})
    science=sum(v['complete']+v['strict_experiment_failure'] for v in counts.values())
    infrastructure=sum(v['infrastructure_failure'] for v in counts.values());terminal=science+infrastructure
    report={'model':L.MODEL,'expected_results':240,'terminal_results':terminal,'scientific_terminal_results':science,
        'infrastructure_failure_results':infrastructure,'unresolved_results':len(unresolved),
        'verification_passed':terminal==240,'scientific_complete':science==240,
        'counts':{m:dict(v) for m,v in counts.items()},'unresolved':unresolved,
        'protocol_sha256':L.digest(frozen),'external_api_cost_usd':0.0,'gpu_resource_cost_not_included':True}
    L.write(args.output_dir/'summary.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='unresolved'},ensure_ascii=False,indent=2),flush=True)
    return report


L.protocol=protocol;L.prepare=prepare;L.request_payload=request_payload;L.token_count=token_count
L.tokenizer_hashes=tokenizer_hashes;L.load_tokenizer=load_tokenizer
L.make_client_class=make_client_class;L.validate_result=validate_result;L.run_one=run_one;L.summarize=summarize

async def main(args):
    configure(L.read(args.model_config))
    args.base_url=CFG['base_url'];args.checkpoint_revision=CFG['checkpoint_revision'];args.max_model_len=CFG['max_model_len']
    if args.mode=='finalize-infrastructure':
        if os.environ.get('PYTHONHASHSEED')!='42':raise L.IntegrityStop('PYTHONHASHSEED=42 is required')
        manifest=L.verify_bundle();cost=L.import_science();graphs=L.restore_graphs(cost,manifest)
        plan,frozen,_=prepare(args,cost,manifest,graphs)
        for case in plan:
            for method in L.METHODS:
                with L.locked(args.output_dir/'locks/cases'/f"{case['case_id']}__{method}.lock"):
                    science=L.result_path(args,case,method);infra=infra_path(args,case,method)
                    if science.exists():validate_result(cost,args,case,method,graphs,frozen,L.read(science));continue
                    if infra.exists():validate_infra(args,case,method,frozen,L.read(infra));continue
                    counter=args.output_dir/'attempts'/f"{case['case_id']}__{method}.json"
                    attempts=L.read(counter)['attempts'] if counter.exists() else 0
                    record_infra(args,case,method,frozen,'SupervisorRecoveryLimit',args.infrastructure_reason,attempts,'supervisor_skip')
        summarize(args,plan,cost,graphs,frozen);return 0
    return await L.main(args)

def parse_args():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-config',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--mode',choices=('preflight','tokenize','smoke','run','summarize','finalize-infrastructure'),default='preflight')
    parser.add_argument('--tokenizer-path',type=Path);parser.add_argument('--case-concurrency',type=int,default=8)
    parser.add_argument('--shard-count',type=int,default=1);parser.add_argument('--shard-index',type=int,default=0)
    parser.add_argument('--llm-timeout',type=float,default=600);parser.add_argument('--max-case-attempts',type=int,default=4)
    parser.add_argument('--infrastructure-reason',default='Supervisor stopped unresolved cells after bounded infrastructure recovery')
    args=parser.parse_args();args.model_config=args.model_config.resolve();args.output_dir=args.output_dir.resolve()
    if args.tokenizer_path:args.tokenizer_path=args.tokenizer_path.resolve()
    if not 0<=args.shard_index<args.shard_count or args.case_concurrency<1 or args.max_case_attempts<1:
        parser.error('Invalid scheduling/attempt arguments')
    return args
if __name__=='__main__':
    try:raise SystemExit(asyncio.run(main(parse_args())))
    except EndpointRecoveryRequired as exc:print(f'ENDPOINT_RECOVERY_REQUIRED: {exc}',file=sys.stderr);raise SystemExit(75)
    except L.RunStop as exc:print(f'{type(exc).__name__}: {exc}',file=sys.stderr);raise SystemExit(78)

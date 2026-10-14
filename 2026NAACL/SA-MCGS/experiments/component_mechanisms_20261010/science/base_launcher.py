#!/usr/bin/env python3
"""Portable Llama experiment adapter; unchanged original scientific entry points.

Preflight/tokenize never construct an API client. Only explicit smoke/run use
127.0.0.1:18081. Each process handles one case at a time; independent shards
provide case concurrency. Strict scientific failures are terminal observations.
"""
from __future__ import annotations
import argparse
import asyncio
import collections
import copy
import csv
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sys
import time
from contextlib import contextmanager

HERE = Path(__file__).resolve().parent
ROOT = HERE / 'repo'
sys.path.insert(0, str(ROOT))
MODEL = 'llama-3.1-8b'
ALIAS = 'llama-3.1-8b-instruct'
CHECKPOINT = 'meta-llama/Llama-3.1-8B-Instruct'
METHODS = ('naive-single', 'lea', 'sa-mcgs')
TERMINAL = {'complete', 'strict_experiment_failure'}

class RunStop(BaseException):
    pass
class IntegrityStop(RunStop):
    pass
class ProviderFailure(RunStop):
    pass


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(path)
def append(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')
        stream.flush();os.fsync(stream.fileno())
def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
@contextmanager
def locked(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(stream,fcntl.LOCK_UN)

def import_science():
    from emnlp2026_discussion import run_cost_audit_clean as cost
    return cost

def verify_bundle():
    manifest=read(ROOT/'bundle_manifest.json')
    checks=dict(manifest['unchanged_code_sha256'])
    checks.update({name:info['sha256'] for name,info in manifest['source_results'].items()})
    checks.update({info['path']:info['sha256'] for info in manifest['graphs'].values()})
    checks['portable_data/qwen80_case_plan.json']=manifest['case_plan_sha256']
    for relative,expected in checks.items():
        if sha(ROOT/relative)!=expected: raise IntegrityStop(f'Bundle hash mismatch: {relative}')
    return manifest

def restore_graphs(cost,manifest):
    from src.models.graph import DependencyGraph
    graphs={}
    for domain,info in manifest['graphs'].items():
        graph=DependencyGraph.model_validate_json(gzip.decompress((ROOT/info['path']).read_bytes()))
        graph.metadata.pop(cost._DATASET_REVISION_CACHE_KEY,None)
        if cost.graph_dataset_revision(graph,domain)!=info['dataset_revision']:
            raise IntegrityStop(f'Graph content revision mismatch: {domain}')
        graphs[domain]=graph
    return graphs

def scientific_args(args):
    return argparse.Namespace(model=MODEL,budget=60,window_size=4,internal_concurrency=8,
        compression_profile='current',case_concurrency=args.case_concurrency,
        llm_timeout=args.llm_timeout,llm_max_retries=0,base_url=args.base_url,
        api_key_env='LOCAL_VLLM_API_KEY')

def protocol(args,cost,manifest):
    if args.base_url!='http://127.0.0.1:18081/v1': raise IntegrityStop('Only fixed same-node endpoint is allowed')
    if not re.fullmatch('[0-9a-f]{40}',args.checkpoint_revision): raise IntegrityStop('Pinned 40-hex checkpoint revision required')
    return {'version':1,'model':MODEL,'served_model':ALIAS,'checkpoint_repository':CHECKPOINT,
        'checkpoint_revision':args.checkpoint_revision,'base_url':args.base_url,
        'dtype':'bfloat16','quantization':None,'tensor_parallel_size':1,
        'external_api_cost_usd':0.0,'gpu_resource_cost_not_included':True,
        'bundle_manifest_sha256':sha(ROOT/'bundle_manifest.json'),
        'case_plan_sha256':sha(ROOT/'portable_data/llama80_case_plan.json'),
        'launcher_sha256':sha(Path(__file__)),
        'original_scientific_code_sha256':manifest['unchanged_code_sha256'],
        'cases':80,'methods':list(METHODS),'expected_terminal_results':240,
        'sa_mcgs_config':cost.make_mcgs_config(scientific_args(args)),
        'lea':{'window_size':4,'temperature':0.4,'max_tokens':2048,'internal_concurrency':1},
        'one_shot':{'naive_profile':'direct_subgraph','temperature':0.0,'max_tokens':12000,'internal_concurrency':1},
        'sdk_max_retries':0,'json_parse_attempts':3,'json_parse_exhaustion_fallback':{},
        'strict_failures_are_terminal':True,'max_model_len':args.max_model_len,
        'context_policy':'No truncation; exact tokenizer guard before every request including dynamic SA prompts',
        'python_rng_seed':42,'python_hash_seed':42,'rng_note':'New model reproducibility setting, not asserted for historical runs; concurrent completion order also affects SA search',
        'historical_sa_concurrency':{'gpt-4o':8,'deepseek-v3':8,'qwen2.5-72b':12,'gemini-2.5-pro':{'10':76,'12':4}},
        'sa_concurrency_reason':'8 matches historical GPT and DeepSeek main experiments',
        'cache_policy':'Exact invocation index/config hash plus original response completion order; mismatch stops without resampling',
        'metric_node_fields':{'naive-single':'direct_risk_subgraph_nodes','lea':'lea_risk_subgraph_nodes','sa-mcgs':'core_evidence_risk_subgraph_nodes'}}

def prepare(args,cost,manifest,graphs):
    plan=read(ROOT/'portable_data/llama80_case_plan.json')
    original=read(ROOT/'portable_data/qwen80_case_plan.json')
    if len(plan)!=80 or len({c['case_uid'] for c in plan})!=80: raise IntegrityStop('Expected 80 unique case identities')
    for case,source in zip(plan,original):
        for field in ('case_uid','planned_case_identity','planned_scc_clause_ids','planned_injection_identity','source_result_sha256','source_sa_record_sha256','main_case_order'):
            if case[field]!=source[field]: raise IntegrityStop(f'Changed identity {field}')
        if case['model']!=MODEL: raise IntegrityStop('Unexpected model in plan')
        case['source_result_file']=str(ROOT/case['source_result_repo_relpath'])
    report=cost.validate_case_plan(plan,graphs)
    frozen=protocol(args,cost,manifest)
    with locked(args.output_dir/'locks/init.lock'):
        for name,value in [('frozen_protocol.json',frozen),('case_plan.json',plan)]:
            path=args.output_dir/name
            if path.exists() and read(path)!=value: raise IntegrityStop(f'Frozen configuration changed: {name}')
            if not path.exists(): write(path,value)
    return plan,frozen,report


def request_payload(prompt,temperature,max_tokens,system_prompt,response_format):
    messages=([{'role':'system','content':system_prompt}] if system_prompt else [])
    messages.append({'role':'user','content':prompt})
    return {'model':ALIAS,'messages':messages,'temperature':temperature,'max_tokens':max_tokens,
            **({'response_format':response_format} if response_format else {})}

def token_count(tokenizer,request):
    ids=tokenizer.apply_chat_template(request['messages'],tokenize=True,add_generation_prompt=True)
    if isinstance(ids,dict) or hasattr(ids,'keys'): ids=ids['input_ids']
    if len(ids) and isinstance(ids[0],(list,tuple)): ids=ids[0]
    return len(ids)

class ReplayJournal:
    """Transport-only checkpoint; all scientific state is rebuilt by original code."""
    def __init__(self,path,protocol_sha256,timeout=90):
        self.path=path;self.protocol_sha256=protocol_sha256;self.timeout=timeout
        self.starts=rows(path/'requests.jsonl');saved=rows(path/'responses.jsonl')
        self.saved={r['call_index']:r for r in saved}
        self.order=[r['call_index'] for r in saved];self.cursor=0;self.next_index=0
        self.original_start_count=len(self.starts)
        self.changed=asyncio.Condition();self.return_counter=len(saved)
        if len(self.saved)!=len(saved): raise IntegrityStop('Duplicate saved response index')
        if [r['call_index'] for r in self.starts]!=list(range(1,len(self.starts)+1)):
            raise IntegrityStop('Broken request journal sequence')
        for response in saved:
            idx=response['call_index']
            if idx>len(self.starts) or response['request_sha256']!=self.starts[idx-1]['request_sha256']:
                raise IntegrityStop('Response/request journal mismatch')
    def assert_consumed(self):
        if self.next_index < self.original_start_count or self.cursor != len(self.order):
            raise IntegrityStop('Scientific trajectory ended before consuming the original checkpoint')
    def begin(self,request):
        self.next_index+=1;idx=self.next_index
        signature=digest({'request':request,'protocol_sha256':self.protocol_sha256})
        if idx<=len(self.starts):
            expected=self.starts[idx-1]
            if expected['request_sha256']!=signature or expected['request']!=request:
                raise IntegrityStop(f'Resume trajectory/config mismatch at call {idx}; no new request sent')
        else:
            row={'call_index':idx,'request':request,'request_sha256':signature,'protocol_sha256':self.protocol_sha256}
            append(self.path/'requests.jsonl',row);self.starts.append(row)
        return idx,signature
    async def replay(self,index):
        if index not in self.saved:return None
        # Yield to all initial gather tasks, preserving initial request starts.
        await asyncio.sleep(0)
        try:
            async with self.changed:
                await asyncio.wait_for(self.changed.wait_for(lambda:self.cursor<len(self.order) and self.order[self.cursor]==index),self.timeout)
                result=self.saved[index];self.cursor+=1;self.changed.notify_all()
                return result
        except asyncio.TimeoutError:raise IntegrityStop('Cached response completion-order replay stalled') from None
    async def finish(self,index,signature,content,returned_model,usage,record):
        # New/missing replies cannot overtake the recorded pre-interruption prefix.
        try:
            async with self.changed:
                await asyncio.wait_for(self.changed.wait_for(lambda:self.cursor>=len(self.order)),self.timeout)
                saved={'call_index':index,'request_sha256':signature,'content':content,'returned_model':returned_model,'usage':usage,'record':record}
                append(self.path/'responses.jsonl',saved)
                return saved
        except asyncio.TimeoutError:raise IntegrityStop('New response overtook an unreplayed checkpoint prefix') from None


def make_client_class(cost):
    from src.llm.base import LLMResponse
    class LocalClient(cost.LoggingOpenAIClient):
        def __init__(self,args,case,method,frozen,tokenizer):
            super().__init__({'provider':'openai','model':ALIAS,'base_url':args.base_url,'api_key_env':'LOCAL_VLLM_API_KEY','timeout':args.llm_timeout,'max_retries':0},
                call_log_path=args.output_dir/'call_logs'/f"{case['case_id']}__{method}.jsonl",
                context={'case_id':case['case_id'],'case_uid':case['case_uid'],'method':method,'model':MODEL,
                    'protocol_sha256':digest(frozen),'phase':args.mode})
            self.journal=ReplayJournal(args.output_dir/'call_cache'/case['case_id']/method,digest(frozen))
            self.tokenizer=tokenizer;self.max_model_len=args.max_model_len
            self.parse_exhausted_windows=0
        async def call(self,prompt,*,temperature=0.0,max_tokens=4096,system_prompt=None,response_format=None):
            req=request_payload(prompt,temperature,max_tokens,system_prompt,response_format)
            count=token_count(self.tokenizer,req)
            if count+max_tokens>self.max_model_len: raise IntegrityStop(f'Context overflow: {count}+{max_tokens}>{self.max_model_len}; no truncation/request')
            idx,signature=self.journal.begin(req)
            saved=await self.journal.replay(idx)
            if saved is not None:
                if saved['returned_model']!=ALIAS:raise IntegrityStop('Cached model mismatch')
                self.call_records.append({**saved['record'],'replayed_from_checkpoint':True})
                self.last_usage=saved['usage']
                return LLMResponse(content=saved['content'],model=ALIAS,usage={k:int(saved['usage'].get(k,0)) for k in ('prompt_tokens','completion_tokens','total_tokens')})
            started=time.time()
            record={**self.context,'call_index':idx,'request_sha256':signature,'request':req,
                'prompt_tokens_preflight':count,'max_tokens':max_tokens,'started_at':started,'ok':False,'external_api_cost_usd':0.0}
            try:raw=await self.client.chat.completions.create(**req)
            except BaseException as exc:
                record.update({'runtime_sec':time.time()-started,'error_type':type(exc).__name__,'http_status':getattr(exc,'status_code',None)})
                append(self.call_log_path,record);self.call_records.append(record)
                if isinstance(exc,(KeyboardInterrupt,asyncio.CancelledError)):raise
                raise ProviderFailure(f'Local provider failure: {type(exc).__name__}, HTTP {getattr(exc,"status_code",None)}') from None
            usage=raw.usage.model_dump() if raw.usage else {}
            if not raw.choices or raw.model!=ALIAS:raise IntegrityStop('Server model/choice mismatch')
            if any(not isinstance(usage.get(k),int) for k in ('prompt_tokens','completion_tokens','total_tokens')):raise IntegrityStop('Server omitted auditable token usage')
            content=raw.choices[0].message.content or ''
            record.update({'ok':True,'runtime_sec':time.time()-started,'returned_model':raw.model,'usage':usage,'finish_reason':raw.choices[0].finish_reason})
            await self.journal.finish(idx,signature,content,raw.model,usage,record)
            append(self.call_log_path,record);self.call_records.append(record);self.last_usage=usage
            return LLMResponse(content=content,model=raw.model,usage={k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens')})
        async def call_json(self,prompt,*,temperature=0.0,max_tokens=4096,system_prompt=None,retries=2):
            if retries!=2:raise IntegrityStop('Unexpected JSON retry policy')
            for attempt in range(retries+1):
                response=await self.call(prompt,temperature=temperature,max_tokens=max_tokens,system_prompt=system_prompt,response_format={'type':'json_object'})
                parsed=self._extract_json(response.content)
                if parsed is not None:return parsed
                if attempt<retries:await asyncio.sleep(min(2**attempt,8))
            self.parse_exhausted_windows+=1;return {}
    return LocalClient


class CaptureClient:
    def __init__(self):self.requests=[];self.call_records=[];self.last_usage={}
    async def call_json(self,prompt,*,temperature=0.0,max_tokens=4096,system_prompt=None,retries=2):
        self.requests.append(request_payload(prompt,temperature,max_tokens,system_prompt,{'type':'json_object'}));return {}
    async def close(self):pass

async def capture_requests(cost,args,plan,graphs):
    captures=[]
    for case in plan:
        graph,scc,root,metadata=cost.prepare_injected_case(case,graphs)
        # Direct prompts follow the original function even though {} causes its intentional strict error.
        direct=CaptureClient()
        try:await cost.battle.run_naive(direct,MODEL,case['domain'],graph,scc,naive_profile='direct_subgraph',injected_id=root)
        except ValueError as exc:
            if str(exc)!='LLM returned no parseable JSON':raise
        captures.extend({'case_id':case['case_id'],'case_uid':case['case_uid'],'method':'naive-single','request':r} for r in direct.requests)
        # Include every deterministic LEA window (also those a response-dependent TT may reuse).
        mcgs=cost.AlphaGoMCGS(llm_client=CaptureClient(),config=cost.make_mcgs_config(scientific_args(args)))
        mcgs._init_state(graph,scc)
        for window in cost.deterministic_windows(mcgs,list(scc.clause_ids),4):
            prompt=cost.battle.DOMAIN_MCGS_PROMPTS[case['domain']](mcgs,window)
            captures.append({'case_id':case['case_id'],'case_uid':case['case_uid'],'method':'lea',
                'window':window,'request':request_payload(prompt,0.4,2048,None,{'type':'json_object'})})
        # SA selections and memory-dependent prompts cannot be enumerated in advance.
        random.seed(42)
        recorder=CaptureClient()
        await cost.battle.run_sa_mcgs(recorder,MODEL,case['domain'],graph,scc,cost.make_mcgs_config(scientific_args(args)))
        captures.extend({'case_id':case['case_id'],'case_uid':case['case_uid'],'method':'sa-mcgs_stub_path_only','request':r} for r in recorder.requests)
    return captures


def result_path(args,case,method):return args.output_dir/'results'/f"{case['case_id']}__{method}.json"

def validate_result(cost,args,case,method,graphs,frozen,result):
    if result.get('completion_status') not in TERMINAL:raise IntegrityStop('Nonterminal result cannot be silently reused')
    if result.get('model')!=MODEL or result.get('case_id')!=case['case_id'] or result.get('cost_audit_method')!=method or result.get('protocol_sha256')!=digest(frozen):
        raise IntegrityStop('Existing result metadata mismatch')
    cost.validate_result_case_identity(result,case,graphs[case['domain']])
    if result['completion_status']=='strict_experiment_failure' and not (result.get('cost_audit_error') or result.get('error')):
        raise IntegrityStop('Strict-failure result has no recorded scientific error')
    if result['completion_status']=='complete':
        allowed=set(case['planned_scc_clause_ids']);ranking=result.get('ranking') or []
        field={'naive-single':'direct_risk_subgraph_nodes','lea':'lea_risk_subgraph_nodes','sa-mcgs':'core_evidence_risk_subgraph_nodes'}[method]
        nodes=result.get(field)
        if not ranking or any(not isinstance(row,(list,tuple)) or len(row)!=2 or row[0] not in allowed for row in ranking):
            raise IntegrityStop('Result has invalid or empty ranking')
        if not isinstance(nodes,list) or not set(nodes)<=allowed:
            raise IntegrityStop('Result has invalid prediction nodes')

async def run_one(cost,args,case,method,graphs,frozen,tokenizer):
    path=result_path(args,case,method)
    if path.exists():
        validate_result(cost,args,case,method,graphs,frozen,read(path));return
    status_path=args.output_dir/'case_status'/f"{case['case_id']}__{method}.json"
    write(status_path,{'case_id':case['case_id'],'method':method,'state':'running','time':time.time()})
    graph,scc,root,metadata=cost.prepare_injected_case(case,graphs)
    client=make_client_class(cost)(args,case,method,frozen,tokenizer)
    old=cost.make_llm
    cost.make_llm=lambda *_a,**_k:client
    random.seed(42)
    try:
        result=await cost.run_method(scientific_args(args),args.output_dir,case,method,graph,scc,root,metadata)
        client.journal.assert_consumed()
        # Original run_method retains format/schema ValueError as scientific failure.
        if result.get('cost_audit_error'):
            if result.get('error_type') not in {'ValueError','TypeError','KeyError','AttributeError'}:
                raise IntegrityStop(f'Unexpected scientific implementation error: {result.get("error_type")}')
            completion='strict_experiment_failure'
        else:completion='complete'
        if method=='lea' and completion=='complete':
            # Same injected-root override used by the frozen full LEA runner.
            ranking=result.get('ranking') or []
            result['top1_hit']=bool(ranking and ranking[0][0]==root)
            result['top3_hit']=root in [item[0] for item in ranking[:3]]
        result.update({'completion_status':completion,'protocol_sha256':digest(frozen),
            'checkpoint_repository':CHECKPOINT,'checkpoint_revision':args.checkpoint_revision,
            'base_url':args.base_url,'requested_model_id':ALIAS,'case_concurrency':args.case_concurrency,
            'internal_concurrency':8 if method=='sa-mcgs' else 1,'python_rng_seed':42,
            'json_parse_exhausted_windows':client.parse_exhausted_windows,'external_api_cost_usd':0.0,
            'main_case_order':case['main_case_order'],'main_case_id':case['main_case_id']})
        validate_result(cost,args,case,method,graphs,frozen,result)
        write(path,result)
        write(status_path,{'case_id':case['case_id'],'method':method,'state':completion,'result_sha256':sha(path),'time':time.time()})
        print(json.dumps({'case':case['main_case_order'],'method':method,'state':completion,'calls':len(client.call_records)},ensure_ascii=False),flush=True)
    except BaseException as exc:
        write(status_path,{'case_id':case['case_id'],'method':method,'state':'provider_failure' if isinstance(exc,ProviderFailure) else 'interrupted_or_integrity_stop','error_type':type(exc).__name__,'message':str(exc)[:1000],'time':time.time()})
        raise
    finally:cost.make_llm=old


def summarize(args,plan,cost=None,graphs=None,frozen=None):
    results=[];counts=collections.Counter();metric_rows=[]
    expected_names={result_path(args,c,m).name for c in plan for m in METHODS}
    extras={p.name for p in (args.output_dir/'results').glob('*.json')}-expected_names
    if extras:raise IntegrityStop(f'Unexpected result files: {sorted(extras)}')
    for case in plan:
        for method in METHODS:
            path=result_path(args,case,method)
            if not path.exists():continue
            result=read(path)
            if cost is not None:validate_result(cost,args,case,method,graphs,frozen,result)
            state=result.get('completion_status');counts[method+':'+str(state)]+=1
            if state not in TERMINAL:continue
            results.append(result)
            valid=state=='complete';nodes=set(result.get({'naive-single':'direct_risk_subgraph_nodes','lea':'lea_risk_subgraph_nodes','sa-mcgs':'core_evidence_risk_subgraph_nodes'}[method]) or [])
            truth=case['planned_injection_identity'];risk=set(truth['risk_nodes']);ranking=result.get('ranking') or []
            metric_rows.append({'case_id':case['case_id'],'case_uid':case['case_uid'],'method':method,'domain':case['domain'],
                'scc_size':case['scc_size'],'completion_status':state,'root_at3':int(valid and truth['root_node'] in [r[0] for r in ranking[:3]]),
                'risk_any':int(valid and bool(nodes&risk)),'risk_all':int(valid and bool(risk) and risk<=nodes),
                'compression':1-len(nodes)/case['scc_size'] if valid else None,'json_parse_exhausted_windows':result.get('json_parse_exhausted_windows',0)})
    summary={'expected':240,'terminal':len(results),'expected_results':240,'terminal_results':len(results),'verification_passed':len(results)==240,'counts':dict(counts),'external_api_cost_usd':0.0,'gpu_resource_cost_not_included':True,'methods':{}}
    for method in METHODS:
        subset=[r for r in metric_rows if r['method']==method]
        summary['methods'][method]={'terminal':len(subset),'strict_failures':sum(r['completion_status']!='complete' for r in subset),
            **{m:sum(r[m] for r in subset)/len(subset) if subset else None for m in ('root_at3','risk_any','risk_all')},
            'compression_valid_only':(sum(r['compression'] for r in subset if r['compression'] is not None)/sum(r['compression'] is not None for r in subset) if any(r['compression'] is not None for r in subset) else None)}
    write(args.output_dir/'summary.json',summary)
    if metric_rows:
        with (args.output_dir/'case_metrics.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(metric_rows[0]));writer.writeheader();writer.writerows(metric_rows)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    return summary


async def main(args):
    if os.environ.get('PYTHONHASHSEED')!='42':raise IntegrityStop('Set PYTHONHASHSEED=42 before starting every worker process')
    manifest=verify_bundle();cost=import_science();graphs=restore_graphs(cost,manifest)
    plan,frozen,report=prepare(args,cost,manifest,graphs)
    if args.mode in {'preflight','tokenize'}:
        captures=await capture_requests(cost,args,plan,graphs)
        write(args.output_dir/'offline_prompt_capture.json',captures)
        report.update({'passed':True,'api_calls':0,'scientific_code_unchanged':True,'protocol_sha256':digest(frozen),
            'captured_request_counts':dict(collections.Counter(c['method'] for c in captures)),
            'sa_capture_scope':'One empty-JSON stub trajectory, not all possible dynamic SA prompts; exact runtime guard required'})
        write(args.output_dir/'portable_preflight.json',report)
        if args.mode=='preflight':print(json.dumps({k:v for k,v in report.items() if k!='case_uids'},indent=2));return 0
        tokenizer=load_tokenizer(args)
        checks=[{'case_id':c['case_id'],'method':c['method'],'prompt_tokens':token_count(tokenizer,c['request']),'max_tokens':c['request']['max_tokens']} for c in captures]
        overflow=[r for r in checks if r['prompt_tokens']+r['max_tokens']>args.max_model_len]
        token_report={'passed':not overflow,'api_calls':0,'protocol_sha256':digest(frozen),'max_model_len':args.max_model_len,
            'max_prompt_tokens':max(r['prompt_tokens'] for r in checks),'max_prompt_plus_output_tokens':max(r['prompt_tokens']+r['max_tokens'] for r in checks),
            'overflow':overflow,'rows':checks,'tokenizer_files_sha256':tokenizer_hashes(args),
            'coverage':'80 full-SCC One-shot prompts, every deterministic LEA window, SA stub trajectory plus mandatory actual-request runtime guard'}
        write(args.output_dir/'tokenization_report.json',token_report)
        print(json.dumps({k:v for k,v in token_report.items() if k!='rows'},indent=2))
        return 2 if overflow else 0
    if args.mode=='summarize':summarize(args,plan,cost,graphs,frozen);return 0
    for name in ('portable_preflight.json','tokenization_report.json'):
        proof=read(args.output_dir/name)
        if not proof.get('passed') or proof['protocol_sha256']!=digest(frozen):raise IntegrityStop(f'Missing/current-bundle check failed: {name}')
    if read(args.output_dir/'tokenization_report.json')['tokenizer_files_sha256']!=tokenizer_hashes(args):raise IntegrityStop('Tokenizer files changed')
    tokenizer=load_tokenizer(args);os.environ['LOCAL_VLLM_API_KEY']='local-no-external-billing'
    selected=[c for c in plan if c['main_case_order']==20] if args.mode=='smoke' else [c for i,c in enumerate(plan) if i%args.shard_count==args.shard_index]
    with locked(args.output_dir/'locks'/f'shard_{args.shard_index}.lock'):
        for case in selected:
            for method in METHODS:await run_one(cost,args,case,method,graphs,frozen,tokenizer)
    with locked(args.output_dir/'locks/summary.lock'):summarize(args,plan,cost,graphs,frozen)
    return 0

def tokenizer_hashes(args):
    if not args.tokenizer_path:raise IntegrityStop('--tokenizer-path is required')
    return {name:sha(args.tokenizer_path/name) for name in ('tokenizer.json','tokenizer_config.json','config.json','special_tokens_map.json','chat_template.jinja') if (args.tokenizer_path/name).is_file()}
def load_tokenizer(args):
    if not args.tokenizer_path:raise IntegrityStop('--tokenizer-path is required')
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(str(args.tokenizer_path),local_files_only=True,trust_remote_code=False)

def parse_args():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('preflight','tokenize','smoke','run','summarize'),default='preflight')
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--base-url',default='http://127.0.0.1:18081/v1')
    p.add_argument('--tokenizer-path',type=Path);p.add_argument('--checkpoint-revision',required=True)
    p.add_argument('--max-model-len',type=int,default=131072);p.add_argument('--shard-count',type=int,default=1);p.add_argument('--shard-index',type=int,default=0)
    p.add_argument('--case-concurrency',type=int,default=2)
    p.add_argument('--llm-timeout',type=float,default=600)
    args=p.parse_args();args.output_dir=args.output_dir.resolve()
    if args.tokenizer_path:args.tokenizer_path=args.tokenizer_path.resolve()
    if not 0<=args.shard_index<args.shard_count:p.error('Invalid shard')
    if args.case_concurrency < 1:p.error('Invalid case concurrency')
    if args.max_model_len not in (32768,65536,131072):p.error('Unexpected context length')
    return args
if __name__=='__main__':
    try:raise SystemExit(asyncio.run(main(parse_args())))
    except RunStop as exc:print(f'{type(exc).__name__}: {exc}',file=sys.stderr);raise SystemExit(3)

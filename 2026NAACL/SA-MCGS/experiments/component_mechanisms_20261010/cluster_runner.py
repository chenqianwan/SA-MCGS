#!/usr/bin/env python3
"""One frozen sample per model/case/arm, using only existing node-local services."""
from __future__ import annotations
import argparse
import asyncio
import collections
import copy
import fcntl
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import random
import sys
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT.parent / 'equal_budget_full_20261009'
SERVICE_ROOT = ROOT.parent / 'equal_budget_all80_20261009'
MODELS = ('llama', 'kimi', 'qwen35')
ARMS = ('full', 'no_relation_guidance', 'no_critical_revisit', 'no_both', 'random_windows')
TERMINAL = {'complete', 'strict_experiment_failure', 'infrastructure_failure'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), default=str).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def append(path, value):
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)+'\n')
        stream.flush(); os.fsync(stream.fileno())


def scoped_protocol(plan):
    protocol, scope = read(ROOT/'protocol.json'), read(ROOT/'run_scope.json')
    expected = {'cases_per_model': 80, 'repeats': 1, 'seed': 42, 'rollouts': 60,
                'window_size': 4, 'internal_concurrency': 4, 'expected_results': 1200,
                'external_api_enabled': False}
    for key, value in expected.items():
        if protocol.get(key) != value:
            raise ValueError(f'Protocol mismatch: {key}')
    if set(protocol.get('models', [])) != set(MODELS) or tuple(protocol.get('arms', [])) != ARMS:
        raise ValueError('Protocol must contain exactly the three models and five ordered arms')
    ids = [case['case_uid'] for case in plan]
    if len(ids) != 80 or len(set(ids)) != 80 or set(scope.get('case_uids', [])) != set(ids):
        raise ValueError('Scope must be the verified complete 80-case plan')
    if len(scope['case_uids']) != 80 or any(scope.get(k) != v for k,v in
          {'expected_results': 1200, 'repeats': 1, 'stop_after_scope': True}.items()):
        raise ValueError('Scope must authorize exactly one repeat and 1200 terminal observations')
    return protocol, scope


def local_endpoint(url):
    p = urllib.parse.urlsplit(url)
    if (p.scheme != 'http' or p.hostname != '127.0.0.1' or p.port not in range(19081,19089)
            or p.path != '/v1' or p.username or p.password or p.query or p.fragment):
        raise ValueError('Only the eight existing credential-free loopback endpoints are allowed')
    return url


def endpoints():
    obj = read(SERVICE_ROOT/'endpoints.json')
    if str(obj.get('job_id')) != '415747' or set(obj.get('models', {})) != set(MODELS):
        raise ValueError('Unexpected endpoint deployment')
    reps = obj['replicas']
    if collections.Counter(r['model_key'] for r in reps) != {'llama':2,'kimi':4,'qwen35':2}:
        raise ValueError('Require the existing 2/4/2 deployment')
    if len({r['id'] for r in reps}) != 8 or len({r['base_url'] for r in reps}) != 8:
        raise ValueError('Replica IDs and endpoints must be unique')
    for r in reps:
        local_endpoint(r['base_url'])
        cfg = obj['models'][r['model_key']]
        if cfg['alias'] != r['alias'] or cfg['max_model_len'] != 131072:
            raise ValueError('Model alias/context mismatch')
        if cfg.get('chat_template_kwargs', {}) != ({'enable_thinking':False} if r['model_key']=='qwen35' else {}):
            raise ValueError('Unexpected thinking configuration')
    return obj


def health(replica):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(local_endpoint(replica['base_url'])+'/models', timeout=10) as r:
        body = json.load(r)
    if replica['alias'] not in {r.get('id') for r in body.get('data', [])}:
        raise RuntimeError('Existing endpoint is not serving the frozen model')


def load_science():
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    # Dependencies and immutable source material are reused; no prior output is modified.
    sys.path.insert(0, str(UPSTREAM))
    spec = importlib.util.spec_from_file_location('mechanism_science_support', UPSTREAM/'runner.py')
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    support.ROOT = ROOT  # New study owns an unchanged copy of the verified science bundle.
    loaded = support.load_science()
    from mechanism_patches import MechanismMCGS, ARMS as PATCH_ARMS
    if set(PATCH_ARMS) != set(ARMS) or not issubclass(MechanismMCGS, loaded[1].AlphaGoMCGS):
        raise ValueError('Patch class must derive from the verified frozen bundle class')
    expected_source=(ROOT/'science/repo/src/modules/alphago_mcgs.py').resolve()
    if Path(inspect.getfile(loaded[1].AlphaGoMCGS)).resolve()!=expected_source:
        raise ValueError('Imported scientific class is outside the new frozen science copy')
    return support, loaded, MechanismMCGS


def args_for(model):
    return argparse.Namespace(model=model, budget=60, window_size=4, internal_concurrency=4,
                              compression_profile='current', seed=42, case_concurrency=1,
                              llm_timeout=1800, llm_max_retries=0)


def runtime_manifest(support, loaded):
    launcher, cost, manifest, graphs, plan = loaded
    scoped_protocol(plan)
    files = ['cluster_runner.py', 'cluster_supervisor.py', 'mechanism_patches.py', 'concurrent_ledger.py',
             'launch_cluster_workers.sh']
    sources = {f: sha(ROOT/f) for f in files}
    upstream = {f: sha(UPSTREAM/f) for f in ('runner.py','budget_client.py','science/base_launcher.py',
                                          'science/repo/bundle_manifest.json')}
    cfg = cost.make_mcgs_config(args_for('offline'))
    cfg['alphago_mcgs']['temperature'] = .4
    settings = cfg['alphago_mcgs']
    if any(settings.get(k, default) != expected for k,default,expected in
           [('max_tokens',2048,2048),('tt_max_reuse',3,3),('concurrency',1,4),('budget',60,60)]):
        raise ValueError('Frozen native config differs from the declared mechanism protocol')
    return {'schema_version':'component_mechanisms.runtime.v1', 'protocol_sha256':sha(ROOT/'protocol.json'),
            'scope_sha256':sha(ROOT/'run_scope.json'), 'source_hashes':sources,
            'upstream_source_hashes':upstream, 'science_source_hashes':manifest['unchanged_code_sha256'],
            'local_science_files':{f:sha(ROOT/f) for f in
                                  ('science/base_launcher.py','science/repo/bundle_manifest.json')},
            'case_plan_sha256':sha(launcher.ROOT/'portable_data/qwen80_case_plan.json'),
            'sa_config':cfg, 'seed':42, 'sampling_repeats':1, 'external_api_enabled':False,
            'json_attempts':3, 'sdk_retries':0,
            'recovery_policy':'No quality reruns; only a zero-request infrastructure attempt may restart. '
                              'Partial/unknown requests remain recorded as failures, never resampled.'}


def verify_runtime(support, loaded):
    current = runtime_manifest(support, loaded)
    if read(ROOT/'runtime_manifest.json') != current:
        raise ValueError('Runtime source/protocol changed after offline preparation')
    return current


def terminal_matches(record, case, model, arm, protocol_hash, runtime_hash):
    expected = {'case_uid':case['case_uid'], 'model':model, 'arm':arm, 'repeat_index':1,
                'protocol_sha256':protocol_hash, 'runtime_manifest_sha256':runtime_hash}
    if any(record.get(k) != v for k,v in expected.items()) or record.get('status') not in TERMINAL:
        raise ValueError('Existing result identity, protocol, or status mismatch')


def zero_request_attempt(folder):
    ledger = folder/'ledger.jsonl'
    if not ledger.exists():
        return not any((folder/'calls').glob('*.json'))
    events = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    return not any(row.get('event') == 'reserve' for row in events) and not any((folder/'calls').glob('*.json'))


def queue_plan(plan):
    # Large graphs first, interleaved arms. Selection never uses observed quality.
    cases = sorted(plan, key=lambda c:(-len(c['planned_scc_clause_ids']),c['case_uid']))
    return [(case, arm) for case in cases for arm in ARMS]


def acquire_task(folder):
    folder.mkdir(parents=True, exist_ok=True)
    stream = (folder/'task.lock').open('a+')
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        stream.close(); return None
    return stream


def is_rollout_task(task):
    return getattr(task.get_coro(),'__qualname__','').endswith('.search.<locals>.run_one')


async def drain_rollouts(before):
    # Native gather can raise while sibling calls are in flight. Finish only this
    # case's rollout coroutines, never unrelated SDK background tasks or new work.
    pending=[t for t in asyncio.all_tasks() if t not in before and not t.done() and is_rollout_task(t)]
    if pending:
        return await asyncio.gather(*pending,return_exceptions=True)
    return []


def pause_model(model,reason):
    path=ROOT/'execution/paused_models.json'
    path.parent.mkdir(exist_ok=True)
    with path.with_suffix('.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        data=read(path) if path.exists() else {}
        data[model]={'reason':reason,'paused_at':now()}
        save(path,data)


def enrich_result(result,case,model_alias,scc,config,injected_id,injection_metadata):
    """Attach provenance only after search; labels never enter the search client."""
    result.update(copy.deepcopy(injection_metadata))
    ranking=result.get('ranking_by_risk',result.get('ranking',[]))
    result.update(model=model_alias,domain=case['domain'],case_uid=case['case_uid'],
          case_id=case['case_id'],case_order=case['case_order'],method='sa-mcgs',
          scc_id=scc.id,scc_size=scc.size,scc_clause_ids=list(scc.clause_ids),
          budget=60,window_size=4,internal_concurrency=4,ranking=ranking,scores=dict(ranking),
          mcgs_compression_profile='current',
          mcgs_compression_params=copy.deepcopy(config['alphago_mcgs'].get('evidence',{})),
          inject_mode=True,injected_node=injected_id,inject_profile='memory_stress',cycle_source='real_long')
    return result


async def run_task(case, arm, replica, model_cfg, tokenizer, token_hashes, support, loaded,
                   machine_class, protocol_hash, runtime_hash, recover=False):
    launcher, cost, manifest, graphs, plan = loaded
    model = replica['model_key']
    folder = ROOT/'results'/model/case['case_uid']/arm
    final_path = folder/'final.json'
    if final_path.exists():
        prior = read(final_path)
        terminal_matches(prior,case,model,arm,protocol_hash,runtime_hash)
        if not (recover and prior['status']=='infrastructure_failure' and zero_request_attempt(folder)):
            return prior
        append(folder/'recovery_history.jsonl', {'recovered_at':now(),'prior_final':prior,
                                               'reason':'Explicit recovery; no request was reserved or sent'})
        final_path.unlink()
    elif (folder/'attempt.json').exists() and not zero_request_attempt(folder):
        # Concurrent search cannot safely replay a new trajectory after an uncheckpointed interruption.
        record = read(folder/'attempt.json')
        record.update(status='infrastructure_failure',completion_status='infrastructure_failure',
                      error_type='InterruptedPartialSearch',error='Prior requests preserved; no resampling',
                      result=None,metrics=support.metrics(None,'sa-mcgs',case,False),ended_at=now())
        from concurrent_ledger import ConcurrentLedger
        ledger = ConcurrentLedger(folder/'ledger.jsonl')
        try:
            await ledger.initialize()
            record['usage']=ledger.owner_summary(case['case_uid'],model_cfg['alias'],arm)
        finally:
            await ledger.close()
        save(final_path,record)
        return record
    import budget_client as budget
    from concurrent_ledger import ConcurrentLedger
    ledger = ConcurrentLedger(folder/'ledger.jsonl')
    client = None
    record = {'schema_version':'component_mechanisms.result.v1','case_uid':case['case_uid'],
              'case_id':case['case_id'],'domain':case['domain'],'model':model,'model_key':model,
              'model_alias':model_cfg['alias'],'arm':arm,'method':'sa-mcgs','repeat_index':1,'seed':42,
              'protocol_sha256':protocol_hash,'runtime_manifest_sha256':runtime_hash,
              'replica_id':replica['id'],'source_n':len(case['planned_scc_clause_ids']),
              'status':'running','completion_status':'running','started_at':now(),'started_unix':time.time(),
              'result':None,'external_api_enabled':False}
    save(folder/'attempt.json', record)
    start = time.monotonic()
    before_tasks=set(asyncio.all_tasks())
    try:
        await ledger.initialize()
        graph,scc,injected_id,injection_metadata = cost.prepare_injected_case(case,graphs)
        allowed = set(scc.clause_ids)
        visible={'nodes':[{'id':c,'title':graph.clauses[c].title,'text':graph.clauses[c].content}
                          for c in scc.clause_ids],
                 'edges':[{'source':e.source,'target':e.target,
                           'type':str(getattr(e.dependency_type,'value',e.dependency_type)),
                           'weight':float(e.weight)} for e in graph.edges
                          if e.source in allowed and e.target in allowed]}
        record['visible_input_sha256']=digest(visible)
        save(folder/'input_identity.json',{'case_uid':case['case_uid'],
              'visible_input_sha256':record['visible_input_sha256'],
              'planned_fingerprint':case['planned_scc_fingerprint'],
              'protocol_sha256':protocol_hash})
        client=budget.BudgetClient(config={'timeout':1800,'max_model_len':131072,
                'tokenizer_fingerprint':digest(token_hashes)},ledger=ledger,case_id=case['case_uid'],
                method=arm,tokenizer=tokenizer,model=model_cfg['alias'],base_url=local_endpoint(replica['base_url']),
                call_log_dir=folder/'calls',token_cap=None,json_attempts=3,selector_json_attempts=1,
                chat_template_kwargs=model_cfg.get('chat_template_kwargs',{}))
        cfg=cost.make_mcgs_config(args_for(model_cfg['alias']))
        cfg['alphago_mcgs']['temperature']=.4
        random.seed(42)  # Every process runs a single independent case at a time.
        completed = [0]
        def durable_trace(event):
            append(folder/'trace.jsonl',event)
            completed[0] += 1
            save(folder/'progress.json',{'completed_rollouts':completed[0],
                 'usage':ledger.owner_summary(case['case_uid'],model_cfg['alias'],arm),
                 'elapsed_sec':time.monotonic()-start,'updated_at':now()})
        machine=machine_class(llm_client=client,config=copy.deepcopy(cfg),arm=arm,seed=42,
                              trace_callback=durable_trace)
        formatter=cost.battle.DOMAIN_MCGS_PROMPTS[case['domain']]
        machine._build_focused_prompt=lambda window:formatter(machine,window)
        client.set_phase('sa')
        result=await machine.search(graph,scc)
        result=enrich_result(result,case,model_cfg['alias'],scc,cfg,injected_id,injection_metadata)
        if result.get('total_iterations')!=60 or len(result.get('trace_events',[]))!=60:
            raise RuntimeError('Search did not produce the declared 60 rollout records')
        record['metrics']=support.metrics(result,'sa-mcgs',case)
        record['result']=result
        record['status']='complete' if record['metrics']['valid'] else 'strict_experiment_failure'
    except asyncio.CancelledError:
        record.update(status='infrastructure_failure',error_type='CancelledError',error='Search interrupted')
        raise
    except BaseException as exc:
        if isinstance(exc,(KeyboardInterrupt,SystemExit)):
            raise
        record.update(status='infrastructure_failure',error_type=type(exc).__name__,error=str(exc)[:2000],
                      traceback=traceback.format_exc()[-10000:])
    finally:
        await drain_rollouts(before_tasks)
        record['usage']=ledger.owner_summary(case['case_uid'],model_cfg['alias'],arm)
        if record['usage'].get('held_calls') or record['usage'].get('usage_mismatch_calls'):
            record.update(status='infrastructure_failure',error_type='UnsettledOrMismatchedUsage')
        if record['status']!='complete':
            if record.get('result') is not None:
                save(folder/'raw_result.json',record['result'])
            record['result']=None
            record['metrics']=support.metrics(None,'sa-mcgs',case,False)
        record.update(completion_status=record['status'],ended_at=now(),elapsed_sec=time.monotonic()-start)
        if client is not None:
            await client.close()
        await ledger.close()
        save(final_path,record)
    print(json.dumps({'model':model,'case_uid':case['case_uid'],'arm':arm,'status':record['status'],
                      'tokens':record['usage'].get('total_tokens',0),'elapsed_sec':record['elapsed_sec']}),flush=True)
    return record


async def execute(cli,support,loaded,machine_class):
    if os.environ.get('PYTHONHASHSEED')!='42':
        raise ValueError('Workers require PYTHONHASHSEED=42 at interpreter startup')
    runtime=verify_runtime(support,loaded)
    ep=endpoints()
    replica=next(r for r in ep['replicas'] if r['id']==cli.replica_id)
    cfg=ep['models'][replica['model_key']]
    health(replica)  # GET metadata only; no generation or fallback.
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(cfg['tokenizer_path'],local_files_only=True,
                                           trust_remote_code=cfg.get('trust_remote_code',False))
    hashes=support.tokenizer_hashes(cfg['tokenizer_path'])
    token_path=ROOT/'tokenizer_hashes'/f"{replica['model_key']}.json"
    support.freeze(token_path,hashes)
    status_path=ROOT/'execution'/f'{cli.replica_id}_worker{cli.worker_index}_status.json'
    status={'status':'running','replica_id':cli.replica_id,'worker_index':cli.worker_index,
            'pid':os.getpid(),'started_at':now(),'completed_by_worker':0}
    save(status_path,status)
    protocol_hash,runtime_hash=sha(ROOT/'protocol.json'),digest(runtime)
    for case,arm in queue_plan(loaded[4]):
        pauses=ROOT/'execution/paused_models.json'
        if pauses.exists() and replica['model_key'] in read(pauses):
            status.update(status='model_paused_after_infrastructure_failure',ended_at=now())
            save(status_path,status)
            return
        folder=ROOT/'results'/replica['model_key']/case['case_uid']/arm
        lock=acquire_task(folder)
        if lock is None:
            continue
        try:
            if (folder/'final.json').exists():
                prior=read(folder/'final.json')
                terminal_matches(prior,case,replica['model_key'],arm,protocol_hash,runtime_hash)
                if not (cli.recover_infrastructure and prior['status']=='infrastructure_failure'
                        and zero_request_attempt(folder)):
                    continue
            status.update(current_case_uid=case['case_uid'],current_arm=arm,updated_at=now())
            save(status_path,status)
            record=await run_task(case,arm,replica,cfg,tokenizer,hashes,support,loaded,machine_class,
                                  protocol_hash,runtime_hash,cli.recover_infrastructure)
            status['completed_by_worker']+=1
            save(status_path,status)
            if record['status']=='infrastructure_failure':
                pause_model(replica['model_key'],record.get('error_type','infrastructure_failure'))
                status.update(status='model_paused_after_infrastructure_failure',ended_at=now())
                save(status_path,status)
                return
        finally:
            lock.close()
    status.update(status='complete',ended_at=now())
    save(status_path,status)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--replica-id')
    parser.add_argument('--worker-index',type=int,default=0)
    parser.add_argument('--recover-infrastructure',action='store_true')
    cli=parser.parse_args()
    support,loaded,machine_class=load_science()
    scoped_protocol(loaded[4])
    if cli.prepare:
        if any((ROOT/'results').glob('*/*/*/attempt.json')):
            verify_runtime(support,loaded)
        validation=loaded[1].validate_case_plan(loaded[4],loaded[3])
        frozen_plan=read(loaded[0].ROOT/'portable_data/qwen80_case_plan.json')
        save(ROOT/'frozen_case_plan.json',frozen_plan)
        manifest=runtime_manifest(support,loaded)
        save(ROOT/'runtime_manifest.json',manifest)
        save(ROOT/'preflight/runner_prepare.json',{'status':'passed','cases':80,'arms':list(ARMS),
             'expected_results':1200,'model_calls':0,'validation':validation,
             'runtime_manifest_sha256':digest(manifest),'checked_at':now()})
        print(json.dumps({'status':'passed','cases':80,'expected_results':1200,'model_calls':0}))
        return 0
    if not cli.replica_id or not 0 <= cli.worker_index < 16:
        parser.error('A valid --replica-id and worker-index 0..15 are required')
    asyncio.run(execute(cli,support,loaded,machine_class))
    return 0


if __name__=='__main__':
    raise SystemExit(main())

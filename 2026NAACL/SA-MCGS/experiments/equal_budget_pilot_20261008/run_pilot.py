#!/usr/bin/env python3
"""Four-domain GPT-4o pilot. All paid calls use the shared $15 ledger."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

RUN_DIR = Path(__file__).resolve().parent
ROOT = RUN_DIR.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(RUN_DIR))
from emnlp2026_discussion import run_cost_audit_clean as cost
from src.modules.alphago_mcgs import AlphaGoMCGS

SLOTS = [1, 3, 6, 9]
ARMS = ['sa-mcgs', 'lea', 'full-scc']
TOKEN_CAP = 160000
SEED = 20261008
PLAN_PATH = ROOT / '2026NAACL/SA-MCGS/experiments/cost_prior_12case_gpt4o_gemini25pro_b60_v1/preflight/plans/gpt-4o/case_plan.json'

def now():
    return datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat(timespec='seconds')

def save(path, obj):
    cost.atomic_write_json(Path(path), obj)

def sha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def visible_input(graph, scc):
    ids = set(scc.clause_ids)
    return {'nodes': [{'id': i, 'title': graph.clauses[i].title, 'text': graph.clauses[i].content} for i in scc.clause_ids],
            'edges': [{'source': e.source, 'target': e.target, 'type': str(e.dependency_type)} for e in graph.edges if e.source in ids and e.target in ids]}

def online_account_and_price():
    key = os.environ.get('XHUB_API_KEY')
    if not key:
        raise RuntimeError('XHUB_API_KEY missing')
    def get(url, auth=False):
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer '+key} if auth else {})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    price = get('https://api3.xhub.chat/api/pricing')
    row = next(r for r in price['data'] if r['model_name'] == 'gpt-4o')
    if float(row['model_ratio']) != 1.25 or float(row['completion_ratio']) != 4 or float(price['group_ratio']['default']) != 1:
        raise RuntimeError('Pricing changed; do not run against stale budget rates')
    status = get('https://api3.xhub.chat/api/status')
    usage = get('https://api3.xhub.chat/api/usage/token/', True)
    return {'checked_at': now(), 'available_usd': float(usage['data']['total_available'])/float(status['data']['quota_per_unit']),
            'input_usd_per_million': 2.5, 'output_usd_per_million': 10,
            'pricing_version': price.get('pricing_version'),
            'account_note': 'Shared key balance is diagnostic, not experiment-attributable spend.'}

def prepare():
    all_cases = json.loads(PLAN_PATH.read_text())
    cases = [r for r in all_cases if r['case_slot'] in SLOTS]
    assert len(cases) == 4
    graphs = cost.load_graphs(cases)
    prepared = []
    for case in cases:
        graph, scc, root, labels = cost.prepare_injected_case(case, graphs)
        visible = visible_input(graph, scc)
        save(RUN_DIR/'inputs'/f"{case['case_slot']:02d}_visible.json", visible)
        prepared.append((case, graph, scc, root, labels, sha(visible)))
    protocol = {
        'version': RUN_DIR.name, 'model': 'gpt-4o', 'scope': 'exploratory development pilot, not confirmatory test',
        'selection': 'First smallest source per domain from previously frozen 12-source plan; no outcome-based selection.',
        'slots': SLOTS, 'arms': ARMS, 'cap_usd': 15, 'per_arm_token_cap': TOKEN_CAP,
        'temperature': .4, 'sa_rollout_horizon': 60, 'window_size': 4,
        'full_scc_output_token_cap': 12000, 'local_output_token_cap': 2048,
        'sdk_retries': 0, 'explicit_json_retries_max': 1,
        'parallelism': 'Three arms concurrently; one request per arm; cases sequential.',
        'output_policy': 'Primary comparison preserves native H, reports actual node count and compression. Common .45*n cap is a separate offline diagnostic only.',
        'failure_policy': 'After bounded JSON recovery fails, no default-0.5 answer is accepted: SA case or baseline candidate invalid; selector failure invalidates final output.',
        'selector': 'One same-model blinded selection over anonymous shuffled complete candidates; no ground truth; cost included.',
        'budget_interpretation': 'Equal token ceilings, actual tokens reported; no padding and no claim of identical realized tokens.',
        'repeat_limits': {'lea': 6, 'full-scc': 12}, 'seed': SEED,
        'sa_stopping': 'Original sequential search operations, stop cleanly before next request exceeds token/dollar budget; retain completed rollout state.',
        'source_hashes': {str(p.relative_to(ROOT)): file_sha(p) for p in [PLAN_PATH, ROOT/'src/modules/alphago_mcgs.py', ROOT/'emnlp2026_discussion/run_cost_audit_clean.py', ROOT/'experiments/cross_domain/run_cross_domain_battle.py', RUN_DIR/'run_pilot.py', RUN_DIR/'methods.py', RUN_DIR/'budget_client.py']},
        'cases': [{'case_id': c['case_id'], 'slot': c['case_slot'], 'domain': c['domain'], 'n': s.size, 'case_uid': c['case_uid'], 'visible_input_sha256': h} for c,g,s,r,l,h in prepared],
    }
    pp = RUN_DIR/'protocol.json'
    if pp.exists() and json.loads(pp.read_text()) != protocol:
        raise RuntimeError('Frozen protocol/code changed; cannot silently resume')
    save(pp, protocol)
    save(RUN_DIR/'case_plan.json', cases)
    print(json.dumps({'event': 'preflight_ok', 'cases': protocol['cases'], 'token_cap': TOKEN_CAP, 'hard_usd_cap': 15}, ensure_ascii=False), flush=True)
    return prepared, protocol

class InferenceFailure(BaseException):
    pass

class StrictProxy:
    """Do not allow SA's generic exception fallback to masquerade as valid output."""
    def __init__(self, client): self.client = client
    def __getattr__(self, name): return getattr(self.client, name)
    async def call_json(self, *args, **kwargs):
        try:
            value = await self.client.call_json(*args, **kwargs)
            if not value: raise ValueError('Empty parsed JSON')
            return value
        except Exception as e:
            raise InferenceFailure(type(e).__name__) from e

async def run_sa(client, args, case, graph, scc):
    cfg = cost.make_mcgs_config(args)
    cfg['alphago_mcgs']['temperature'] = .4
    mcgs = AlphaGoMCGS(llm_client=StrictProxy(client), config=cfg)
    fn = cost.battle.DOMAIN_MCGS_PROMPTS[case['domain']]
    mcgs._build_focused_prompt = lambda w: fn(mcgs, w)
    mcgs._init_state(graph, scc)
    start = time.monotonic()
    done = calls = hits = 0
    stop_reason = 'rollout_horizon'
    client.set_phase('sa')
    for iteration in range(60):
        window = mcgs._select_and_expand(iteration)
        mcgs._apply_virtual_loss(window)
        try:
            entry, hit = await mcgs._evaluate(window)
            mcgs._backpropagate(window, entry)
            mcgs._update_oc(iteration)
            mcgs._record_trace(iteration, window, entry, hit)
            hits += int(hit)
            calls += int(not hit)
            done += 1
        except client.budget_stop_type:
            stop_reason = 'budget_limit'
            break
        finally:
            mcgs._remove_virtual_loss(window)
    if done == 0: raise InferenceFailure('No completed rollout')
    result = mcgs._build_result(time.monotonic()-start, calls, hits, done)
    result['ranking'] = result['ranking_by_risk']
    result['stop_reason'] = stop_reason
    return {'selected_result': result, 'selection': {'method': 'native_sa_core'}, 'completed_rollouts': done}

def output_nodes(result, method):
    fields = {'sa-mcgs': 'evidence_risk_subgraph_nodes', 'lea': 'lea_risk_subgraph_nodes', 'full-scc': 'direct_risk_subgraph_nodes'}
    return list(dict.fromkeys(result.get(fields[method]) or []))

def apply_cap(result, method, scc):
    field = {'sa-mcgs': 'evidence_risk_subgraph_nodes', 'lea': 'lea_risk_subgraph_nodes', 'full-scc': 'direct_risk_subgraph_nodes'}[method]
    result = dict(result)
    ids = list(scc.clause_ids)
    nodes = output_nodes(result, method)
    result.setdefault('pilot_raw_output_nodes', nodes)
    k = min(len(ids), max(4, math.ceil(.45*len(ids))))
    ranking = [r[0] for r in result.get('ranking', [])]
    if len(nodes) > k:
        order = {v: i for i,v in enumerate(ranking)}
        nodes = sorted(nodes, key=lambda v: (order.get(v,len(ids)),ids.index(v) if v in ids else len(ids)))[:k]
    result[field] = nodes
    result['pilot_output_cap'] = k
    return result

def score(result, method, scc, root, labels):
    ids = set(scc.clause_ids)
    ranking = [r[0] for r in result.get('ranking', [])]
    nodes = output_nodes(result, method)
    valid = bool(nodes) and set(nodes) <= ids and len(ranking)==len(ids) and set(ranking)==ids
    risks = set(labels.get('injected_risk_nodes') or [])
    return {'valid': valid, 'root_at_3': int(valid and root in ranking[:3]),
            'risk_any': int(valid and bool(risks & set(nodes))),
            'risk_all': int(valid and bool(risks) and risks <= set(nodes)),
            'compression': 1-len(nodes)/len(ids) if valid else None, 'output_n': len(nodes) if valid else None}

async def run_arm(ledger, args, item, method):
    from budget_client import BudgetClient, BudgetStop
    from methods import baseline
    case, graph, scc, root, labels, input_hash = item
    folder = RUN_DIR/'results'/case['case_id']/method
    folder.mkdir(parents=True, exist_ok=True)
    final_path = folder/'final.json'
    if final_path.exists(): return json.loads(final_path.read_text())
    client = BudgetClient({'model': 'gpt-4o', 'api_key_env': 'XHUB_API_KEY', 'base_url': 'https://api3.xhub.chat/v1', 'timeout': 180, 'max_retries': 0}, ledger=ledger, case_id=case['case_id'], method=method, call_log_dir=folder/'calls', token_cap=TOKEN_CAP)
    t0 = time.monotonic()
    record = {'case_id':case['case_id'],'domain':case['domain'],'method':method,'n':scc.size,'visible_input_sha256':input_hash,'started_at':now()}
    try:
        if method == 'sa-mcgs':
            raw = await run_sa(client,args,case,graph,scc)
        else:
            arm_args = SimpleNamespace(**vars(args))
            arm_args.repeat_count = 6 if method == 'lea' else 12
            arm_args.output_cap = scc.size
            raw = await baseline(client,arm_args,case,graph,scc,{},method,folder)
        save(folder/'inference_frozen.json',raw)
        result = raw.get('selected_result') or {}
        capped = apply_cap(result,method,scc)
        record.update({'inference':raw,'selected_result':result,'metrics':score(result,method,scc,root,labels),
                       'common_cap_diagnostic':score(capped,method,scc,root,labels)})
    except (BudgetStop,InferenceFailure,Exception) as e:
        record.update({'error_type':type(e).__name__,'error':str(e)[:500],'metrics':{'valid':False,'root_at_3':0,'risk_any':0,'risk_all':0,'compression':None,'output_n':None}})
    finally:
        record.update({'usage':client.summary(),'ended_at':now(),'elapsed_sec':time.monotonic()-t0})
        await client.close()
    save(final_path,record)
    print(json.dumps({'event':'arm_complete','case':case['case_id'],'method':method,'metrics':record['metrics'],'usage':record['usage']},ensure_ascii=False),flush=True)
    return record

async def main(run=False):
    prepared, protocol = prepare()
    if not run: return
    from budget_client import GlobalLedger
    ledger = GlobalLedger(RUN_DIR/'ledger.jsonl',cap_usd=15)
    await ledger.initialize()
    start = online_account_and_price()
    if start['available_usd'] < 15: raise RuntimeError('Available account balance below authorized cap')
    if not (RUN_DIR/'account_start.json').exists(): save(RUN_DIR/'account_start.json',start)
    args = SimpleNamespace(model='gpt-4o',budget=60,window_size=4,internal_concurrency=1,compression_profile='current',candidate_temperature=.4,full_scc_temperature=.4,judge_max_tokens=256,max_output_cap=12000,seed=SEED)
    results=[]
    try:
        for item in prepared:
            random.seed(SEED+item[0]['case_slot'])
            save(RUN_DIR/'status.json',{'status':'running','case':item[0]['case_id'],'updated_at':now(),'ledger':await ledger.summary()})
            results.extend(await asyncio.gather(*(run_arm(ledger,args,item,m) for m in ARMS)))
            save(RUN_DIR/'results.json',results)
            save(RUN_DIR/'spend.json',await ledger.summary())
        end = online_account_and_price()
        save(RUN_DIR/'account_end.json',end)
        save(RUN_DIR/'status.json',{'status':'complete','updated_at':now(),'completed_cells':len(results),'ledger':await ledger.summary()})
        print(json.dumps({'event':'complete','ledger':await ledger.summary(),'account_available_usd':end['available_usd']},ensure_ascii=False),flush=True)
    finally:
        await ledger.close()

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',action='store_true',help='Use paid API; capped globally at USD 15')
    cli=parser.parse_args()
    asyncio.run(main(cli.run))

#!/usr/bin/env python3
"""Ten-case paid pilot; no manuscript writes or new SA inference."""
from __future__ import annotations
import argparse,asyncio,collections,csv,fcntl,hashlib,importlib.util,itertools,json,os,sys,time
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]
PREVIOUS=ROOT.parent/'equal_budget_all80_20261009'
COST=ROOT.parent/'cost_prior_12case_gpt4o_gemini25pro_b60_v1'
MODELS=('gpt-4o','gemini-2.5-pro')
METHODS=('lea','full-scc')
sys.path.insert(0,str(REPO));sys.path.insert(0,str(ROOT))
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n');tmp.replace(p)
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def prepare():
 # Import verified frozen algorithm and graph bundle, then bind the API transport.
 support=module('api_science_support',PREVIOUS/'science_support.py')
 launcher,cost,manifest,graphs,mainplan=support.load_science()
 plans={m:read(COST/'preflight/plans'/m/'case_plan.json') for m in MODELS}
 rows=plans['gpt-4o'];quota={'cuad':4,'sec_ex21':2,'bgb':2,'debian':2}
 eligible=[]
 for group in itertools.combinations(rows,10):
  if dict(collections.Counter(c['domain'] for c in group))!=quota:continue
  if min(collections.Counter(c['template'] for c in group).values())<2:continue
  if len({c['template'] for c in group})!=4:continue
  key=hashlib.sha256(('api10-v1|'+','.join(sorted(c['case_uid'] for c in group))).encode()).hexdigest()
  eligible.append((key,group))
 chosen=sorted(min(eligible,key=lambda x:x[0])[1],key=lambda x:x['case_slot'])
 selected_uids={c['case_uid'] for c in chosen}
 assert len(selected_uids)==10 and selected_uids<={c['case_uid'] for c in mainplan}
 with (COST/'cost/strict_method_cells.csv').open() as f:costrows=list(csv.DictReader(f))
 with (ROOT.parent/'unified_scoring_20261002/canonical_case_metrics.csv').open() as f:canonical=list(csv.DictReader(f))
 refs=[];prepared={};budgets=[];selected_plans={}
 for model in MODELS:
  selected_plans[model]=[c for c in plans[model] if c['case_uid'] in selected_uids]
  assert len(selected_plans[model])==10
  for case in selected_plans[model]:
   graph,scc,_,_=cost.prepare_injected_case(case,graphs)
   prepared[(model,case['case_uid'])]=(case,graph,scc)
   cr=next(r for r in costrows if r['model']==model and r['method']=='sa-mcgs' and r['case_uid']==case['case_uid'])
   mr=next(r for r in canonical if r['model']==model and r['method']=='sa-mcgs' and r['case_uid']==case['case_uid'])
   assert cr['total_tokens'] and int(cr['total_tokens'])>0
   b={'model':model,'case_uid':case['case_uid'],'case_slot':case['case_slot'],'domain':case['domain'],'scc_size':scc.size,'token_cap':int(cr['total_tokens']),'budget_source':'20260909 cost audit SA recorded provider usage; separate from original main SA outputs','source_result_file':cr['result_file'],'source_result_sha256':cr['result_sha256'],'historical_failed_calls_without_usage':int(cr['failed_api_calls']), 'historical_restart_cost_note':('Includes 67936 reported tokens from an interrupted earlier attempt, consistent with cumulative cost-audit accounting.' if model=='gemini-2.5-pro' and case['case_slot']==8 else None)}
   budgets.append(b)
   refs.append({'model':model,'method':'sa-mcgs','case_uid':case['case_uid'],'case_slot':case['case_slot'],'domain':case['domain'],'source':'fixed main experiment; no new SA run','source_sha256':mr['source_sha256'],'main_case_id':mr['main_case_id'],'scoring_policy':mr['scoring_policy'],'metrics':{'valid':mr['valid']=='True','root_at_3':int(float(mr['root_at3'])),'risk_any':int(float(mr['risk_any'])),'risk_all':int(float(mr['risk_all'])),'compression':float(mr['compression']) if mr['compression'] else None,'output_n':int(mr['retained_nodes']) if mr['retained_nodes'] else None}})
 protocol={
  'experiment':ROOT.name,'models':list(MODELS),'methods':list(METHODS),'main_benchmark_cases':80,'cases_per_model':10,'expected_baseline_cells':40,'whole_experiment_runs':1,'stop_after_pilot':True,
  'selection_rule':'Among the existing 12 cost-audit cases inside the main 80, enumerate subsets with CUAD/SEC/BGB/Debian=4/2/2/2 and >=2 of each injection template; select lexicographically smallest SHA256(api10-v1|sorted case UIDs). No performance values enter selection.',
  'eligible_subset_count':len(eligible),'case_uids':[c['case_uid'] for c in chosen],'case_slots':[c['case_slot'] for c in chosen],
  'budget_rule':'For each model-case, each baseline receives the historical cost-audit SA sum of reported input+completion tokens. All baseline candidates, JSON retries and selector are charged within this ceiling. Cumulative provider-recorded costs include interrupted attempts where present. Unrecorded failed-call usage is not imputed; recorded usage is a lower bound in flagged historical cells. Main SA predictions remain a separate historical reference.',
  'temperature':.4,'selector_temperature':0,'window_size':4,'local_max_tokens':2048,'full_scc_max_tokens':12000,'judge_max_tokens':256,'json_attempts':3,'selector_attempts':1,'sdk_retries':0,'seed':42,'per_model_cell_concurrency':8,
  'comparison_label':'Pilot under cost-audit SA token ceilings, with fixed original-main SA results','output_policy':'Preserve native H; no ground-truth selection; retain all planned cases, failed metrics zero, compression valid-only.',
  'endpoint':'https://api3.xhub.chat/v1','sa_rerun':False,'scope_expands_automatically':False,
  'source_hashes':{str(p.relative_to(REPO)):sha(p) for p in [ROOT/'runner.py',ROOT/'methods_full.py',ROOT/'api_budget_client.py',PREVIOUS/'budget_client.py',PREVIOUS/'science_support.py',COST/'preflight/plans/gpt-4o/case_plan.json',COST/'preflight/plans/gemini-2.5-pro/case_plan.json',COST/'cost/strict_method_cells.csv',ROOT.parent/'unified_scoring_20261002/canonical_case_metrics.csv']},
  'science_source_hashes':manifest['unchanged_code_sha256']}
 pp=ROOT/'protocol.json'
 if pp.exists() and read(pp)!=protocol:raise RuntimeError('Frozen protocol mismatch')
 save(pp,protocol);save(ROOT/'selection_candidates.json',[{'hash':key,'case_slots':sorted(c['case_slot'] for c in group),'case_uids':sorted(c['case_uid'] for c in group)} for key,group in sorted(eligible)]);save(ROOT/'case_plans.json',selected_plans);save(ROOT/'budgets.json',budgets);save(ROOT/'main_sa_references.json',refs)
 save(ROOT/'sample_manifest.json',[{k:c[k] for k in ('case_slot','case_uid','domain','scc_size','template','scale')} for c in chosen])
 api=module('budget_client',ROOT/'api_budget_client.py')
 methods=module('api_pilot_methods',ROOT/'methods_full.py')
 return support,api,methods,prepared,budgets,protocol

def report(status='running'):
 results=[read(p) for p in sorted((ROOT/'results').glob('*/*/*/final.json'))]
 refs=read(ROOT/'main_sa_references.json');summary=[]
 for model in MODELS:
  for method in ('sa-mcgs',*METHODS):
   group=[r for r in (refs if method=='sa-mcgs' else results) if r['model']==model and r['method']==method]
   valid=[r for r in group if r['metrics']['valid']]
   row={'model':model,'method':method,'completed':len(group),'planned':10,'valid':len(valid)}
   for key in ('root_at_3','risk_any','risk_all'):row[key+'_count']=sum(r['metrics'][key] for r in group)
   row['compression_pct']=100*sum(r['metrics']['compression'] for r in valid)/len(valid) if valid else None
   row['estimated_usd']=sum(r.get('usage',{}).get('estimated_usd',0) for r in group)
   row['tokens']=sum(r.get('usage',{}).get('total_tokens',0) for r in group)
   summary.append(row)
 save(ROOT/'summary.json',summary)
 state={'status':status,'updated_at':now(),'completed_cells':len(results),'planned_cells':40,'failed_cells':sum(not r['metrics']['valid'] for r in results),'estimated_usd_finished_cells':sum(r.get('usage',{}).get('estimated_usd',0) for r in results),'summary':summary}
 save(ROOT/'status.json',state);return state

async def execute(loaded):
 support,api,methods,prepared,budgets,protocol=loaded
 sems={m:asyncio.Semaphore(8) for m in MODELS}
 paused={m:False for m in MODELS}
 async def one(b,method):
  model=b['model'];case,graph,scc=prepared[(model,b['case_uid'])]
  folder=ROOT/'results'/model/f"{case['case_slot']:02d}"/method;folder.mkdir(parents=True,exist_ok=True)
  if (folder/'final.json').exists():
   old=read(folder/'final.json')
   expected={'model':model,'method':method,'case_uid':case['case_uid'],'B':b['token_cap'],'protocol_sha256':sha(ROOT/'protocol.json')}
   if any(old.get(k)!=v for k,v in expected.items()):raise RuntimeError('Existing final record identity mismatch')
   return
  async with sems[model]:
   if paused[model]:return
   ledger=api.GlobalLedger(folder/'ledger.jsonl')
   await ledger.initialize()
   try:
    client=api.BudgetClient({'model':model,'base_url':protocol['endpoint'],'timeout':600,'max_retries':0,'max_model_len':131072},ledger=ledger,case_id=case['case_uid'],method=method,call_log_dir=folder/'calls',token_cap=b['token_cap'])
   except BaseException:
    await ledger.close()
    raise
   start=time.monotonic();record={'model':model,'method':method,'case_uid':case['case_uid'],'case_slot':case['case_slot'],'domain':case['domain'],'B':b['token_cap'],'started_at':now(),'protocol_sha256':sha(ROOT/'protocol.json')}
   try:
    args=support.science_args(model)
    raw=await methods.baseline(client,args,case,graph,scc,method,folder)
    save(folder/'inference.json',raw)
    record['selected_result']=raw.get('selected_result');record['selection']=raw.get('selection')
    record['metrics']=support.metrics(record['selected_result'],method,case)
    record['status']='complete' if record['metrics']['valid'] else 'scientific_failure'
   except BaseException as e:
    if isinstance(e,(KeyboardInterrupt,SystemExit,asyncio.CancelledError)):raise
    reason=getattr(e,'reason','')
    infra=not isinstance(e,(ValueError,TypeError,KeyError,AttributeError)) and reason not in ('no_output_budget','token_cap_exhausted','tokens','budget_overrun')
    if infra:paused[model]=True
    record.update(status='infrastructure_failure' if infra else 'stopped',error_type=type(e).__name__,error=str(e)[:350],metrics=support.metrics(None,method,case,False))
   finally:
    record['usage']=client.summary();record['ended_at']=now();record['elapsed_seconds']=time.monotonic()-start
    try:await client.close()
    finally:await ledger.close()
   save(folder/'final.json',record);state=report()
   print(json.dumps({'event':'cell_finished','model':model,'slot':case['case_slot'],'method':method,'status':record['status'],'metrics':record['metrics'],'progress':state['completed_cells']},ensure_ascii=False),flush=True)
 await asyncio.gather(*(one(b,method) for b in budgets for method in METHODS))
 state=report('needs_review' if any(paused.values()) else 'complete');print(json.dumps({'event':'pilot_finished','status':state['status'],'completed':state['completed_cells']},ensure_ascii=False),flush=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--report',action='store_true');args=p.parse_args()
 if args.report:print(json.dumps(report(),ensure_ascii=False));return
 from dotenv import load_dotenv
 load_dotenv(REPO/'.env')
 lock=(ROOT/'runner.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 loaded=prepare()
 print(json.dumps({'event':'preflight_complete','slots':loaded[-1]['case_slots'],'paid':args.run},ensure_ascii=False),flush=True)
 if args.run:
  save(ROOT/'launch.json',{'pid':os.getpid(),'started_at':now(),'scope':40,'concurrency_per_model':8})
  report();asyncio.run(execute(loaded))
if __name__=='__main__':main()

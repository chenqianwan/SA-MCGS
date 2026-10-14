#!/usr/bin/env python3
"""Finish the 31 previously unfinalized cells; keep existing finals immutable."""
from __future__ import annotations
import asyncio,fcntl,hashlib,importlib.util,json,os,shutil,sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent;ORIGINAL=ROOT.parent;PREV=ORIGINAL/'recovery_v1';REPO=ORIGINAL.parents[3]
MODELS=('gpt-4o','gemini-2.5-pro');METHODS=('lea','full-scc')
sys.path.insert(0,str(REPO));sys.path.insert(0,str(ORIGINAL));sys.path.insert(0,str(ROOT))
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n');t.replace(p)
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def prepare():
 if read(PREV/'status.json')['status']!='needs_review':raise RuntimeError('Previous run must be stopped')
 scope=[]
 for b in read(ORIGINAL/'budgets.json'):
  for method in METHODS:
   relative=Path('results')/b['model']/f"{b['case_slot']:02d}"/method;source=PREV/relative;dest=ROOT/relative
   if (source/'final.json').exists():continue
   scope.append({**b,'method':method,'relative':str(relative)})
   if not dest.exists():
    if source.exists():shutil.copytree(source,dest)
    else:dest.mkdir(parents=True)
    old=[]
    p=dest/'ledger.jsonl'
    if p.exists():
     state={}
     for line in p.read_text().splitlines():
      x=json.loads(line)
      if x['event']=='reserve':old.append(x['call_id']);state[x['call_id']]={**x,'status':'reserved'}
      elif x['event']=='finish':state[x['call_id']].update(x)
     if any(x['status']=='reserved' for x in state.values()):raise RuntimeError('Cannot copy an in-flight request')
    save(dest/'legacy_call_ids.json',old)
 assert len(scope)==31
 spec={'parent_protocol_sha256':sha(ORIGINAL/'protocol.json'),'previous_amendment_sha256':sha(PREV/'protocol_amendment.json'),'scope':[{'model':x['model'],'case_slot':x['case_slot'],'method':x['method'],'case_uid':x['case_uid'],'token_cap':x['token_cap']} for x in scope],'existing_final_records_unchanged':True,'new_sa_calls':0,'per_model_concurrency':1,'gemini_extra_reserve':{'candidate':8192,'selector':16384},'guard_interpretation':'Empirical reasoning-token safety allowances; not guaranteed provider upper bounds. Actual provider usage still settles accounting. Only newly issued requests use the updated guard.','failure_policy':'A cell error terminates only that cell. Budget violations never pause the model. Three consecutive service/infrastructure cell failures pause that model; otherwise wait 30 seconds and continue. Unknown requests are never resampled.','source_hashes':{str(p.relative_to(ORIGINAL)):sha(p) for p in [Path(__file__),ROOT/'budget_guard.py',ORIGINAL/'budgets.json',ORIGINAL/'case_plans.json',ORIGINAL/'methods_full.py']}}
 if (ROOT/'protocol_amendment.json').exists() and read(ROOT/'protocol_amendment.json')!=spec:raise RuntimeError('Changed continuation protocol')
 save(ROOT/'protocol_amendment.json',spec);save(ROOT/'scope.json',scope);return scope

def report(status):
 finals=[read(p) for p in (ROOT/'results').glob('*/*/*/final.json')]
 rows=[]
 for model in MODELS:
  for method in METHODS:
   a=[x for x in finals if x['model']==model and x['method']==method]
   rows.append({'model':model,'method':method,'finished':len(a),'complete':sum(x['status']=='complete' for x in a),'failures':sum(x['status']!='complete' for x in a)})
 save(ROOT/'status.json',{'status':status,'updated_at':now(),'finished_cells':len(finals),'planned_pending_cells':31,'previous_complete_cells':7,'previous_flagged_cells':2,'summary':rows})

async def run(scope):
 support=module('pending_science_support',ORIGINAL.parent/'equal_budget_all80_20261009/science_support.py')
 launcher,cost,manifest,graphs,_=support.load_science()
 api=module('budget_client',ROOT/'budget_guard.py');methods=module('pending_methods',ORIGINAL/'methods_full.py')
 old_judge_cost=methods.judge_cost
 methods.judge_cost=lambda client,source,pool:old_judge_cost(client,source,pool)+api.selector_extra_reserve(client)
 plans=read(ORIGINAL/'case_plans.json');prepared={}
 for model in MODELS:
  for case in plans[model]:
   graph,scc,_,_=cost.prepare_injected_case(case,graphs);prepared[(model,case['case_uid'])]=(case,graph,scc)
 paused=[]
 async def queue(model):
  consecutive=0
  for b in [x for x in scope if x['model']==model]:
   folder=ROOT/b['relative'];method=b['method'];case,graph,scc=prepared[(model,b['case_uid'])]
   if (folder/'final.json').exists():
    old=read(folder/'final.json')
    if any(old.get(k)!=v for k,v in {'case_uid':b['case_uid'],'model':model,'method':method,'B':b['token_cap'],'protocol_sha256':sha(ROOT/'protocol_amendment.json')}.items()):raise RuntimeError('Existing final identity mismatch')
    consecutive=consecutive+1 if old['status']=='infrastructure_failure' else 0
    if consecutive>=3:paused.append(model);return
    continue
   ledger=api.GlobalLedger(folder/'ledger.jsonl');await ledger.initialize()
   client=api.BudgetClient({'model':model,'base_url':'https://api3.xhub.chat/v1','max_model_len':131072,'timeout':600,'max_retries':0},ledger=ledger,case_id=b['case_uid'],method=method,call_log_dir=folder/'calls',token_cap=b['token_cap'])
   record={'model':model,'method':method,'case_uid':b['case_uid'],'case_slot':b['case_slot'],'domain':case['domain'],'B':b['token_cap'],'started_at':now(),'protocol_sha256':sha(ROOT/'protocol_amendment.json')};start=time.monotonic();infra=False
   try:
    raw=await methods.baseline(client,support.science_args(model),case,graph,scc,method,folder)
    save(folder/'inference.json',raw);record['selection']=raw.get('selection');record['selected_result']=raw.get('selected_result');record['metrics']=support.metrics(record['selected_result'],method,case)
    record['status']='complete' if record['metrics']['valid'] else 'scientific_failure';consecutive=0
   except BaseException as e:
    if isinstance(e,(KeyboardInterrupt,SystemExit,asyncio.CancelledError)):raise
    reason=getattr(e,'reason','');budget=reason in {'budget_overrun','transport_budget_exhausted','no_output_budget','tokens','token_cap_exhausted'}
    scientific=isinstance(e,(ValueError,TypeError,KeyError,AttributeError));infra=not budget and not scientific
    record.update(status='budget_violation' if budget else ('scientific_failure' if scientific else 'infrastructure_failure'),error_type=type(e).__name__,error=str(e)[:400],metrics=support.metrics(None,method,case,False))
    consecutive=consecutive+1 if infra else 0
   finally:
    record['usage']=client.summary();record['ended_at']=now();record['elapsed_seconds']=time.monotonic()-start
    try:await client.close()
    finally:await ledger.close()
   save(folder/'final.json',record);report('running');print(json.dumps({'event':'cell_finished','model':model,'method':method,'slot':b['case_slot'],'status':record['status']},ensure_ascii=False),flush=True)
   if consecutive>=3:paused.append(model);return
   if infra:await asyncio.sleep(30)
 await asyncio.gather(*(queue(m) for m in MODELS));report('needs_review' if paused else 'finished_pending_scope')

def main():
 from dotenv import load_dotenv
 load_dotenv(REPO/'.env');lock=(ROOT/'runner.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 scope=prepare();save(ROOT/'launch.json',{'pid':os.getpid(),'started_at':now(),'scope':31});report('running');asyncio.run(run(scope))
if __name__=='__main__':main()

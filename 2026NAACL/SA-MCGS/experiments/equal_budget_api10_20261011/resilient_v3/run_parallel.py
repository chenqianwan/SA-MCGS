#!/usr/bin/env python3
"""Parallel batch scheduling only; leave science and existing final records unchanged."""
from __future__ import annotations
import asyncio,fcntl,hashlib,importlib.util,json,os,shutil,sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent;ORIGINAL=ROOT.parent;PREV=ORIGINAL/'pending_v2';FIRST=ORIGINAL/'recovery_v1';REPO=ORIGINAL.parents[3]
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
 scope=[];previous=[]
 # The former runner was gracefully stopped before snapshots are taken.
 import subprocess
 oldpid=read(PREV/'process.json')['pid']
 try:os.kill(oldpid,0)
 except ProcessLookupError:pass
 else:raise RuntimeError('Previous process is still alive')
 for b in read(ORIGINAL/'budgets.json'):
  for method in METHODS:
   relative=Path('results')/b['model']/f"{b['case_slot']:02d}"/method
   sources=[PREV/relative,FIRST/relative]
   final=next((s/'final.json' for s in sources if (s/'final.json').exists()),None)
   if final is not None:
    previous.append({'source':str(final),'sha256':sha(final),'record':read(final)});continue
   source=next((s for s in sources if s.exists()),None);dest=ROOT/relative
   scope.append({**b,'method':method,'relative':str(relative),'snapshot_source':str(source) if source else None})
   if not dest.exists():
    if source is not None:shutil.copytree(source,dest)
    else:dest.mkdir(parents=True)
    old=[];state={};ledger=dest/'ledger.jsonl'
    if ledger.exists():
     for line in ledger.read_text().splitlines():
      x=json.loads(line)
      if x['event']=='reserve':old.append(x['call_id']);state[x['call_id']]={**x,'status':'reserved'}
      elif x['event']=='finish':state[x['call_id']].update(x)
     if any(x['status']=='reserved' for x in state.values()):raise RuntimeError('In-flight request in snapshot')
    if not (dest/'legacy_call_ids.json').exists():save(dest/'legacy_call_ids.json',old)
 assert len(scope)+len(previous)==40
 paths=[Path(__file__),PREV/'budget_guard.py',FIRST/'recovery_transport.py',ORIGINAL/'api_budget_client.py',ORIGINAL/'methods_full.py',ORIGINAL/'budgets.json',ORIGINAL/'case_plans.json']
 spec={'parent_protocol_sha256':sha(ORIGINAL/'protocol.json'),'scope':[{'model':x['model'],'case_slot':x['case_slot'],'method':x['method'],'case_uid':x['case_uid'],'token_cap':x['token_cap']} for x in scope],'previous_final_count':len(previous),'per_model_concurrency':8,'total_concurrency':16,'new_sa_calls':0,'algorithm':'Unmodified methods_full.py and existing pending_v2 client; only batch scheduling changes.','failure_policy':'Record a failed cell and move on; do not pause other cells or rerun existing final records. Existing transport/cache behavior is unchanged.','source_hashes':{str(p.relative_to(ORIGINAL)):sha(p) for p in paths}}
 if (ROOT/'protocol_amendment.json').exists() and read(ROOT/'protocol_amendment.json')!=spec:raise RuntimeError('Changed parallel protocol')
 save(ROOT/'protocol_amendment.json',spec);save(ROOT/'scope.json',scope);save(ROOT/'previous_finals.json',previous);return scope

def report(status):
 previous=[x['record'] for x in read(ROOT/'previous_finals.json')]
 finals=[read(p) for p in (ROOT/'results').glob('*/*/*/final.json')]
 allrows=previous+finals
 rows=[]
 for model in MODELS:
  for method in METHODS:
   a=[x for x in allrows if x['model']==model and x['method']==method]
   rows.append({'model':model,'method':method,'finished':len(a),'complete':sum(x['status']=='complete' for x in a),'failed':sum(x['status']!='complete' for x in a)})
 save(ROOT/'status.json',{'status':status,'updated_at':now(),'total_cells':40,'finished_cells':len(allrows),'complete_cells':sum(x['status']=='complete' for x in allrows),'failed_cells':sum(x['status']!='complete' for x in allrows),'remaining_cells':40-len(allrows),'per_model_concurrency':8,'active':ACTIVE,'summary':rows})

ACTIVE={}

async def run(scope):
 support=module('pending_science_support',ORIGINAL.parent/'equal_budget_all80_20261009/science_support.py')
 launcher,cost,manifest,graphs,_=support.load_science()
 api=module('budget_client',PREV/'budget_guard.py');methods=module('pending_methods',ORIGINAL/'methods_full.py')
 old_judge_cost=methods.judge_cost
 methods.judge_cost=lambda client,source,pool:old_judge_cost(client,source,pool)+api.selector_extra_reserve(client)
 plans=read(ORIGINAL/'case_plans.json');prepared={}
 for model in MODELS:
  for case in plans[model]:
   graph,scc,_,_=cost.prepare_injected_case(case,graphs);prepared[(model,case['case_uid'])]=(case,graph,scc)
 semaphores={model:asyncio.Semaphore(8) for model in MODELS}
 async def cell(b):
  model=b['model'];method=b['method'];folder=ROOT/b['relative'];key=f"{model}/{b['case_slot']:02d}/{method}"
  async with semaphores[model]:
   if (folder/'final.json').exists():
    old=read(folder/'final.json')
    if any(old.get(k)!=v for k,v in {'case_uid':b['case_uid'],'model':model,'method':method,'B':b['token_cap'],'protocol_sha256':sha(ROOT/'protocol_amendment.json')}.items()):raise RuntimeError('Existing final identity mismatch')
    return
   case,graph,scc=prepared[(model,b['case_uid'])]
   record={'model':model,'method':method,'case_uid':b['case_uid'],'case_slot':b['case_slot'],'domain':case['domain'],'B':b['token_cap'],'started_at':now(),'protocol_sha256':sha(ROOT/'protocol_amendment.json')}
   start=time.monotonic();ledger=None;client=None;ACTIVE[key]={'started_at':now()};report('running')
   print(json.dumps({'event':'cell_started','cell':key}),flush=True)
   try:
    ledger=api.GlobalLedger(folder/'ledger.jsonl');await ledger.initialize()
    client=api.BudgetClient({'model':model,'base_url':'https://api3.xhub.chat/v1','max_model_len':131072,'timeout':600,'max_retries':0},ledger=ledger,case_id=b['case_uid'],method=method,call_log_dir=folder/'calls',token_cap=b['token_cap'])
    raw=await methods.baseline(client,support.science_args(model),case,graph,scc,method,folder)
    save(folder/'inference.json',raw);record['selection']=raw.get('selection');record['selected_result']=raw.get('selected_result');record['metrics']=support.metrics(record['selected_result'],method,case)
    record['status']='complete' if record['metrics']['valid'] else 'scientific_failure'
   except BaseException as e:
    if isinstance(e,(KeyboardInterrupt,SystemExit,asyncio.CancelledError)):raise
    reason=getattr(e,'reason','');budget=reason in {'budget_overrun','transport_budget_exhausted','no_output_budget','tokens','token_cap_exhausted'}
    scientific=isinstance(e,(ValueError,TypeError,KeyError,AttributeError))
    record.update(status='budget_violation' if budget else ('scientific_failure' if scientific else 'infrastructure_failure'),error_type=type(e).__name__,error=str(e)[:400],metrics=support.metrics(None,method,case,False))
   finally:
    if client is not None:record['usage']=client.summary()
    record['ended_at']=now();record['elapsed_seconds']=time.monotonic()-start
    try:
     if client is not None:await client.close()
    finally:
     if ledger is not None:await ledger.close()
    ACTIVE.pop(key,None)
   save(folder/'final.json',record);report('running');print(json.dumps({'event':'cell_finished','cell':key,'status':record['status']},ensure_ascii=False),flush=True)
 await asyncio.gather(*(cell(b) for b in scope));report('finished')

def main():
 from dotenv import load_dotenv
 load_dotenv(REPO/'.env');lock=(ROOT/'runner.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 scope=prepare();save(ROOT/'launch.json',{'pid':os.getpid(),'started_at':now(),'scope':len(scope),'per_model_concurrency':8});report('running');asyncio.run(run(scope))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Resume failed cells with candidate-level service isolation in the batch layer."""
from __future__ import annotations
import asyncio, fcntl, hashlib, importlib.util, json, os, shutil, sys, time
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
REPO=BASE.parents[3]
V3=BASE/'resilient_v3'
PARENTS=[V3,BASE/'pending_v2',BASE/'recovery_v1']
MODELS=('gpt-4o','gemini-2.5-pro')
ACTIVE={}
sys.path[:0]=[str(ROOT),str(BASE),str(REPO)]
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n');tmp.replace(p)
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def scope():
 return [{**b,'method':method,'relative':str(Path('results')/b['model']/f"{b['case_slot']:02d}"/method)} for b in read(BASE/'budgets.json') for method in ('lea','full-scc')]
def latest(b,include_self=True):
 for parent in ([ROOT] if include_self else [])+PARENTS:
  f=parent/b['relative']/'final.json'
  if f.exists():return f,read(f)
 return None,None
def actual_overrun(record):
 u=record.get('usage') or {}
 return bool(u.get('budget_overrun') or (u.get('virtual_prefix') or {}).get('budget_overrun'))
def report(status,rows):
 records=[]
 for b in rows:
  f,r=latest(b)
  if r is not None:records.append({'model':b['model'],'method':b['method'],'case_slot':b['case_slot'],'source':str(f),'status':r['status'],'strict_budget_eligible':not actual_overrun(r)})
 save(ROOT/'status.json',{'status':status,'updated_at':now(),'total_cells':40,'complete_cells':sum(x['status']=='complete' for x in records),'currently_failed_cells':sum(x['status']!='complete' for x in records),'final_records':len(records),'active_recovery':ACTIVE,'maximum_combined_concurrency_per_model':8,'results':records})
def prepare(b,source):
 dest=ROOT/b['relative']
 if not dest.exists():
  shutil.copytree(source.parent,dest)
  (dest/'final.json').rename(dest/'parent_final.json')
  state={};ledger=dest/'ledger.jsonl'
  for line in ledger.read_text().splitlines():
   r=json.loads(line)
   if r['event']=='reserve':state[r['call_id']]={**r,'status':'reserved'}
   elif r['event']=='finish':state[r['call_id']].update(r)
  if any(r['status']=='reserved' for r in state.values()):raise RuntimeError('Snapshot has an in-flight request')
  if not (dest/'legacy_call_ids.json').exists():save(dest/'legacy_call_ids.json',list(state))
  save(dest/'migration_cancelled_call_ids.json',[k for k,r in state.items() if r.get('error_type')=='CancelledError'])
  save(dest/'snapshot.json',{'parent_final':str(source),'parent_final_sha256':sha(source),'source_ledger_sha256':sha(ledger),'copied_at':now()})
 return dest

async def run(rows):
 support=module('candidate_science_support',BASE.parent/'equal_budget_all80_20261009/science_support.py')
 launcher,cost,manifest,graphs,_=support.load_science()
 api=module('budget_client',ROOT/'api_adapter.py')
 methods=module('candidate_methods',BASE/'methods_full.py')
 api.wrap_candidate_functions(methods)
 old_judge_cost=methods.judge_cost
 methods.judge_cost=lambda c,s,p:old_judge_cost(c,s,p)+api.selector_extra_reserve(c)
 prepared={}
 for model,cases in read(BASE/'case_plans.json').items():
  for case in cases:
   graph,scc,_,_=cost.prepare_injected_case(case,graphs)
   prepared[(model,case['case_uid'])]=(case,graph,scc)
 async def cell(b,source):
  key=b['relative'];folder=prepare(b,source);model=b['model'];method=b['method'];case,graph,scc=prepared[(model,b['case_uid'])]
  record={'model':model,'method':method,'case_uid':b['case_uid'],'case_slot':b['case_slot'],'domain':case['domain'],'B':b['token_cap'],'started_at':now(),'protocol_sha256':sha(ROOT/'protocol.json'),'parent_final':str(source)}
  client=None;ledger=None;started=time.monotonic()
  try:
   ledger=api.GlobalLedger(folder/'ledger.jsonl');await ledger.initialize()
   client=api.BudgetClient({'model':model,'base_url':'https://api3.xhub.chat/v1','max_model_len':131072,'timeout':600,'max_retries':0},ledger=ledger,case_id=b['case_uid'],method=method,call_log_dir=folder/'calls',token_cap=b['token_cap'])
   raw=await methods.baseline(client,support.science_args(model),case,graph,scc,method,folder)
   save(folder/'inference.json',raw);record['selection']=raw.get('selection');record['selected_result']=raw.get('selected_result');record['metrics']=support.metrics(record['selected_result'],method,case)
   record['status']='complete' if record['metrics']['valid'] else 'scientific_failure'
  except BaseException as e:
   if isinstance(e,(KeyboardInterrupt,SystemExit,asyncio.CancelledError)):raise
   record.update(status='failed',error_type=type(e).__name__,error=str(e)[:400],metrics=support.metrics(None,method,case,False))
  finally:
   if client is not None:record['usage']=client.summary()
   record.update(ended_at=now(),elapsed_seconds=time.monotonic()-started)
   try:
    if client is not None:await client.close()
   finally:
    if ledger is not None:await ledger.close()
  save(folder/'final.json',record)
  print(json.dumps({'event':'recovery_finished','cell':key,'status':record['status']}),flush=True)

 jobs={};done=set()
 while True:
  for key,(b,t) in list(jobs.items()):
   if t.done():
    try:await t
    except BaseException:
     for _,other in jobs.values():other.cancel()
     raise
    del jobs[key];ACTIVE.pop(key,None);done.add(key)
  external={m:0 for m in MODELS}
  for b in read(V3/'scope.json'):
   if not (V3/b['relative']/'final.json').exists():external[b['model']]+=1
  counts={m:sum(b['model']==m for b,_ in jobs.values()) for m in MODELS}
  waiting=False
  for b in rows:
   key=b['relative']
   if key in jobs or key in done:continue
   f,r=latest(b)
   if r is None:waiting=True;continue
   if f.parent.parent.parent.parent==ROOT/'results':done.add(key);continue
   if (ROOT/key/'final.json').exists() or r['status']=='complete' or actual_overrun(r):done.add(key);continue
   waiting=True
   capacity=8-min(8,external[b['model']])
   if counts[b['model']]>=capacity:continue
   ACTIVE[key]={'started_at':now(),'parent_final':str(f)}
   print(json.dumps({'event':'recovery_started','cell':key}),flush=True)
   jobs[key]=(b,asyncio.create_task(cell(b,f)));counts[b['model']]+=1
  report('running',rows)
  if not jobs and not waiting and not any(external.values()):break
  await asyncio.sleep(5)
 report('finished',rows)

def main():
 from dotenv import load_dotenv
 load_dotenv(REPO/'.env')
 lock=(ROOT/'runner.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 paths=[Path(__file__),ROOT/'api_adapter.py',BASE/'methods_full.py',BASE/'pending_v2/budget_guard.py',BASE/'budgets.json',BASE/'case_plans.json']
 spec={'original_algorithm_sha256':sha(BASE/'methods_full.py'),'source_hashes':{str(p.relative_to(BASE)):sha(p) for p in paths},'concurrency_per_model_including_v3':8,'policy':'Skip a failed complete-candidate attempt at the batch boundary, keep successful candidates, and use the unchanged original selector. Preserve actual/held failed-call costs in original token ceilings. Do not rerun a complete cell or a true budget-overrun cell.','new_sa_calls':0}
 if (ROOT/'protocol.json').exists() and read(ROOT/'protocol.json')!=spec:raise RuntimeError('Protocol changed')
 save(ROOT/'protocol.json',spec);save(ROOT/'launch.json',{'pid':os.getpid(),'started_at':now()})
 asyncio.run(run(scope()))
if __name__=='__main__':main()

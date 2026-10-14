#!/usr/bin/env python3
"""One bounded transport recovery of the original 40 cells; no new SA calls."""
from __future__ import annotations
import asyncio,fcntl,hashlib,importlib.util,json,os,shutil,sys,time,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
ORIGINAL=ROOT.parent
REPO=ORIGINAL.parents[3]
MODELS=('gpt-4o','gemini-2.5-pro');METHODS=('lea','full-scc')
sys.path.insert(0,str(REPO));sys.path.insert(0,str(ORIGINAL));sys.path.insert(0,str(ROOT))
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n');tmp.replace(p)
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def snapshot():
 original_status=read(ORIGINAL/'status.json')
 if original_status['status']!='needs_review':raise RuntimeError('Original runner must have ended before copying ledgers')
 for p in (ORIGINAL/'results').glob('*/*/*/ledger.jsonl'):
  calls={}
  for line in p.read_text().splitlines():
   x=json.loads(line)
   if x['event']=='reserve':calls[x['call_id']]={**x,'status':'reserved'}
   elif x['event']=='finish':calls[x['call_id']].update(x)
  if any(x['status']=='reserved' for x in calls.values()):raise RuntimeError('Outstanding original request; no snapshot permitted')
  dest=ROOT/p.parent.relative_to(ORIGINAL)
  if not dest.exists():
   shutil.copytree(p.parent,dest)
   old=dest/'final.json'
   if old.exists():
    if read(old)['status']!='infrastructure_failure':raise RuntimeError('Never overwrite a scientific final')
    old.rename(dest/'initial_infrastructure_failure.json')
 for name in ['budgets.json','case_plans.json','main_sa_references.json','sample_manifest.json']:
  if not (ROOT/name).exists():shutil.copy2(ORIGINAL/name,ROOT/name)
 source={str(p.relative_to(ORIGINAL)):sha(p) for p in sorted((ORIGINAL/'results').rglob('*')) if p.is_file() and p.name!='ledger.jsonl.lock'}
 frozen={'parent_protocol_sha256':sha(ORIGINAL/'protocol.json'),'reason':'XHub HTTP 503 interrupted initial transport; preserve successful cache and all original reservations','cases_unchanged':True,'budget_unchanged':True,'science_methods_unchanged':True,'new_sa_calls':0,'per_model_concurrency':1,'transport_total_attempts_per_logical_call':3,'transport_backoff_seconds':[30,90],'recoverable_status':'unknown_failure with explicit http_status=503 only','unknown_timeout_or_inflight_retried':False,'old_503_accounting':'full original reservation remains accounted, not reported as observed token usage','original_files_sha256':source,'recovery_source_sha256':{p.name:sha(p) for p in [Path(__file__),ROOT/'recovery_transport.py']}}
 if (ROOT/'protocol_amendment.json').exists() and read(ROOT/'protocol_amendment.json')!=frozen:raise RuntimeError('Recovery protocol changed')
 save(ROOT/'protocol_amendment.json',frozen)

def report(status='running'):
 finished=[read(p) for p in sorted((ROOT/'results').glob('*/*/*/final.json'))]
 rows=[]
 for model in MODELS:
  for method in METHODS:
   group=[x for x in finished if x['model']==model and x['method']==method]
   scientific=[x for x in group if x['status'] in ('complete','scientific_failure')]
   valid=[x for x in scientific if x['metrics']['valid']]
   rows.append({'model':model,'method':method,'planned':10,'finished_cells':len(group),'evaluable_cells':len(scientific),'infrastructure_failures':sum(x['status']=='infrastructure_failure' for x in group),'valid':len(valid),'root_at_3_count':sum(x['metrics']['root_at_3'] for x in scientific),'risk_any_count':sum(x['metrics']['risk_any'] for x in scientific),'risk_all_count':sum(x['metrics']['risk_all'] for x in scientific),'compression_pct':100*sum(x['metrics']['compression'] for x in valid)/len(valid) if valid else None})
 # Include active paid calls in the cost/progress view, not just completed cells.
 accounting={'requests':0,'provider_successes':0,'http503':0,'pending':0,'known_tokens':0,'estimated_usd':0.0}
 for p in (ROOT/'results').glob('*/*/*/ledger.jsonl'):
  calls={}
  for line in p.read_text().splitlines():
   x=json.loads(line)
   if x['event']=='reserve':calls[x['call_id']]={**x,'status':'reserved'}
   elif x['event']=='finish':calls[x['call_id']].update(x)
  for x in calls.values():
   accounting['requests']+=1
   if x['status']=='completed_with_usage':accounting['provider_successes']+=1;accounting['known_tokens']+=x.get('actual_total_tokens',0);accounting['estimated_usd']+=x.get('estimated_cost_usd',0)
   elif x['status']=='reserved':accounting['pending']+=1
   elif x.get('http_status')==503:accounting['http503']+=1
 state={'status':status,'updated_at':now(),'finished_cells':len(finished),'planned_cells':40,'accounting':accounting,'summary':rows}
 save(ROOT/'status.json',state);save(ROOT/'summary.json',rows);return state

async def health_gate():
 def check():
  req=urllib.request.Request('https://api3.xhub.chat/v1/models',headers={'Authorization':'Bearer '+os.environ['XHUB_API_KEY']})
  try:
   with urllib.request.urlopen(req,timeout=20) as r:data=json.load(r)
   present={x['id'] for x in data.get('data',[])}
   return {'ready':set(MODELS)<=present,'http':200}
  except urllib.error.HTTPError as e:return {'ready':False,'http':e.code}
  except Exception as e:return {'ready':False,'error':type(e).__name__}
 consecutive=0
 for i in range(60):
  result=await asyncio.to_thread(check);save(ROOT/'health.json',{'checked_at':now(),'check':i+1,**result})
  consecutive=consecutive+1 if result['ready'] else 0
  if consecutive>=2:return True
  report('waiting_for_xhub');await asyncio.sleep(30)
 return False

async def run():
 support=module('recovery_science_support',ORIGINAL.parent/'equal_budget_all80_20261009/science_support.py')
 launcher,cost,manifest,graphs,plan=support.load_science()
 api=module('budget_client',ROOT/'recovery_transport.py')
 methods=module('recovery_methods',ORIGINAL/'methods_full.py')
 budgets=read(ROOT/'budgets.json');plans=read(ROOT/'case_plans.json');paused={m:False for m in MODELS}
 prepared={}
 for model in MODELS:
  for case in plans[model]:
   graph,scc,_,_=cost.prepare_injected_case(case,graphs);prepared[(model,case['case_uid'])]=(case,graph,scc)
 if not await health_gate():report('xhub_unavailable');return
 async def model_queue(model):
  for b in [b for b in budgets if b['model']==model]:
   for method in METHODS:
    if paused[model]:return
    case,graph,scc=prepared[(model,b['case_uid'])];folder=ROOT/'results'/model/f"{case['case_slot']:02d}"/method;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'final.json').exists():continue
    ledger=api.GlobalLedger(folder/'ledger.jsonl');await ledger.initialize()
    client=api.BudgetClient({'model':model,'base_url':'https://api3.xhub.chat/v1','timeout':600,'max_retries':0,'max_model_len':131072},ledger=ledger,case_id=case['case_uid'],method=method,call_log_dir=folder/'calls',token_cap=b['token_cap'])
    record={'model':model,'method':method,'case_uid':case['case_uid'],'case_slot':case['case_slot'],'domain':case['domain'],'B':b['token_cap'],'started_at':now(),'protocol_amendment_sha256':sha(ROOT/'protocol_amendment.json')};start=time.monotonic()
    try:
     raw=await methods.baseline(client,support.science_args(model),case,graph,scc,method,folder)
     save(folder/'inference.json',raw);record['selected_result']=raw.get('selected_result');record['selection']=raw.get('selection');record['metrics']=support.metrics(record['selected_result'],method,case);record['status']='complete' if record['metrics']['valid'] else 'scientific_failure'
    except BaseException as e:
     if isinstance(e,(KeyboardInterrupt,SystemExit,asyncio.CancelledError)):raise
     scientific=isinstance(e,(ValueError,TypeError,KeyError,AttributeError))
     record.update(status='scientific_failure' if scientific else 'infrastructure_failure',error_type=type(e).__name__,error=str(e)[:400],metrics=support.metrics(None,method,case,False))
     if not scientific:paused[model]=True
    finally:
     record['usage']=client.summary();record['ended_at']=now();record['elapsed_seconds']=time.monotonic()-start
     try:await client.close()
     finally:await ledger.close()
    save(folder/'final.json',record);state=report();print(json.dumps({'event':'cell_finished','model':model,'method':method,'slot':case['case_slot'],'status':record['status'],'finished':state['finished_cells']},ensure_ascii=False),flush=True)
 await asyncio.gather(*(model_queue(m) for m in MODELS))
 report('needs_review' if any(paused.values()) else 'complete')

def main():
 from dotenv import load_dotenv
 load_dotenv(REPO/'.env')
 lock=(ROOT/'runner.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 snapshot();save(ROOT/'launch.json',{'pid':os.getpid(),'started_at':now(),'per_model_concurrency':1});report('prepared')
 asyncio.run(run())
if __name__=='__main__':main()

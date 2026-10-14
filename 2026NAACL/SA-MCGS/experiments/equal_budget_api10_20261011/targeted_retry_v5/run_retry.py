#!/usr/bin/env python3
"""Bounded, explicitly requested recovery of failed GPT cells; original science.

One original candidate per failed cell is resumed, selected by successful prefix
length before seeing any new output. Old successes are reused ONLY within that
candidate. New paid requests have separate durable identities. Old spending is
retained in cumulative reporting; recovery exceeding B is never called matched.
"""
import asyncio, fcntl, hashlib, importlib.util, json, os, sys, time
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
REPO=BASE.parents[3]
OLD=BASE/'resilient_candidates_v4'
sys.path[:0]=[str(BASE),str(REPO)]
TARGETS=[(8,'lea'),(10,'lea'),(11,'lea'),(12,'lea'),(11,'full-scc'),(12,'full-scc')]
def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 t=p.with_suffix(p.suffix+'.tmp')
 with t.open('w') as f:
  json.dump(x,f,ensure_ascii=False,indent=2,default=str);f.write('\n');f.flush();os.fsync(f.fileno())
 t.replace(p)
def mod(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
api=mod('budget_client',OLD/'api_adapter.py')
original=api.original

def historical(folder):
 rows={}
 for line in (folder/'ledger.jsonl').read_text().splitlines():
  e=json.loads(line)
  if e['event']=='reserve': rows[e['call_id']]={**e,'status':'reserved'}
  elif e['event']=='finish': rows[e['call_id']].update(e)
 assert all(r['status']!='reserved' for r in rows.values())
 out=[];total=0
 for r in rows.values():
  start=total;total+=api.GlobalLedger.accounted_tokens(r)
  out.append({**r,'prefix_start':start,'prefix_end':total})
 return out

def plan_cell(slot,method):
 folder=OLD/'results/gpt-4o'/f'{slot:02}'/method
 final=read(folder/'final.json');rows=historical(folder)
 assert final['status']!='complete'
 candidates=[]
 for f in sorted(folder.glob('candidate_*.json')):
  c=read(f);lo=c['usage_before']['accounted_tokens'];hi=c['usage_after']['accounted_tokens']
  cr=[r for r in rows if r['prefix_start']>=lo and r['prefix_end']<=hi]
  assert sum(api.GlobalLedger.accounted_tokens(r) for r in cr)==hi-lo
  successful_windows={r['request_key'].split(':')[0] for r in cr if r['status']=='completed_with_usage'}
  candidates.append((len(successful_windows),-c['candidate_index'],c,cr,f))
 if not any(r['status']=='unknown_failure' for r in rows):
  return {'slot':slot,'method':method,'skip_reason':'No failed API requests; native ranking validation failed.', 'source':str(folder/'final.json')}
 eligible=[x for x in candidates if any(r['status']=='unknown_failure' for r in x[3]) or x[2]['status']=='incomplete_budget_stop']
 _,_,c,cr,f=max(eligible,key=lambda x:(x[0],x[1]))
 logicals=list(dict.fromkeys(r['request_key'].split(':')[0] for r in cr))
 mapping={}
 for r in cr:
  p=folder/r['cache_file'];cache=read(p)
  assert cache['call_id']==r['call_id'] and cache['request_hash']==r['request_hash']
  if r['status']=='completed_with_usage':assert original._hash(cache['result'])==r['response_sha256']
  key=r['request_key'];ordinal=logicals.index(key.split(':')[0]);attempt=int(key.rsplit(':attempt-',1)[1])
  mapping.setdefault((ordinal,attempt),[]).append((r,cache,str(p)))
 return {'slot':slot,'method':method,'source':str(folder/'final.json'),'source_sha256':sha(folder/'final.json'),
         'candidate_index':c['candidate_index'],'candidate_source':str(f),'candidate_sha256':sha(f),
         'successful_prefix_requests':sum(r['status']=='completed_with_usage' for r in cr),'old_usage':final['usage'],
         'B':final['B'],'case_uid':final['case_uid'],'mapping':mapping}

class RetryClient(api.BudgetClient):
 def __init__(self,*args,plan,**kwargs):
  super().__init__(*args,**kwargs);self.plan=plan;self.reused=[];self.recovery_log=[]
 async def _call(self,prompt,*,temperature,max_tokens,system_prompt,response_format,logical_key,retry_index):
  ordinal=int(logical_key.split('-')[-1]);old=self.plan['mapping'].get((ordinal,retry_index),[])
  messages=([{'role':'system','content':system_prompt}] if system_prompt else [])+[{'role':'user','content':prompt}]
  for row,cache,path in old:
   b=cache['request']
   if (b['model']!=self.model or b['messages']!=messages or b['temperature']!=temperature or b.get('response_format')!=response_format):
    raise api.LedgerError('Historical candidate/window request mismatch')
   if row['status']=='completed_with_usage':
    self.last_call_record=row;self.last_response=original.BudgetLLMResponse(**cache['result']);self.last_usage=cache['result']['usage']
    self.reused.append({'call_id':row['call_id'],'source':path,'source_sha256':sha(path),'ordinal':ordinal,'json_attempt':retry_index})
    save(self.ledger.path.parent/'reused_calls.json',self.reused)
    return self.last_response
  # A failed old request gets at most TWO new transport attempts. Unattempted
  # tail requests receive an initial attempt plus at most two transport retries.
  attempts=(1,2) if old else (0,1,2)
  for number in attempts:
   try:
    return await original.BudgetClient._call(self,prompt,temperature=temperature,max_tokens=max_tokens,
      system_prompt=system_prompt,response_format=response_format,
      logical_key=f'recovered-candidate-{self.plan["candidate_index"]}-window-{ordinal:04d}-transport-{number}',retry_index=retry_index)
   except api.BudgetStop as e:
    row=self.last_call_record
    if not (row and row['status']=='unknown_failure' and e.reason in {'unknown_provider_outcome','unresolved_cached_request'}):raise
    self.recovery_log.append({'time':now(),'window':ordinal,'attempt':number,'error':str(e),'call_id':row['call_id']})
    save(self.ledger.path.parent/'retry_events.json',self.recovery_log)
    if number==attempts[-1]:raise
    await asyncio.sleep(3)
 async def call_json(self,prompt,*,temperature=0.0,max_tokens=4096,system_prompt=None,retries=2,request_key=None):
  # Same JSON extraction and exhaustion semantics as the frozen base client.
  logical=self._logical_key(request_key)
  configured=self.selector_json_attempts if self._phase=='selector' else self.json_attempts
  for attempt in range(min(configured,max(1,int(retries)+1))):
   response=await self._call(prompt,temperature=temperature,max_tokens=max_tokens,system_prompt=system_prompt,
      response_format={'type':'json_object'},logical_key=logical,retry_index=attempt)
   parsed=original._base.OpenAIClient._extract_json(response.content)
   outcome='dict' if isinstance(parsed,dict) else ('invalid_json' if parsed is None else 'schema_not_object')
   if self.last_call_record['call_id'] in self.ledger._calls:
    await self.ledger.record_parse(self.last_call_record['call_id'],outcome)
   if isinstance(parsed,dict):return parsed
  return {}

async def run(plans):
 support=mod('retry_science_support',BASE.parent/'equal_budget_all80_20261009/science_support.py')
 launcher,cost,manifest,graphs,_=support.load_science()
 methods=mod('retry_methods',BASE/'methods_full.py')
 cases={c['case_uid']:c for c in read(BASE/'case_plans.json')['gpt-4o']}
 sem=asyncio.Semaphore(8)
 async def cell(p):
  folder=ROOT/'results/gpt-4o'/f'{p["slot"]:02}'/p['method'];folder.mkdir(parents=True,exist_ok=True)
  if (folder/'final.json').exists():return read(folder/'final.json')
  if p.get('skip_reason'):
   r={k:v for k,v in p.items() if k!='mapping'};r.update(status='not_retried_no_api_error',ended_at=now());save(folder/'final.json',r);return r
  async with sem:
   r={k:v for k,v in p.items() if k not in ('mapping','old_usage')};r.update(started_at=now(),model='gpt-4o',case_slot=p['slot'])
   if not (folder/'legacy_call_ids.json').exists():save(folder/'legacy_call_ids.json',[])
   ledger=api.GlobalLedger(folder/'ledger.jsonl');await ledger.initialize();client=None
   print(json.dumps({'event':'started','slot':p['slot'],'method':p['method'],'candidate':p['candidate_index'],'reused_prefix':p['successful_prefix_requests']}),flush=True)
   try:
    # Operational bound only: the finite one-candidate scope controls requests.
    # Scientific eligibility below ALWAYS uses original B and all prior costs.
    client=RetryClient({'model':'gpt-4o','base_url':original.ENDPOINT,'max_model_len':131072,'timeout':600,'max_retries':0},
      ledger=ledger,case_id=p['case_uid'],method=p['method'],call_log_dir=folder/'calls',token_cap=2000000,plan=p)
    case=cases[p['case_uid']];graph,scc,_,_=cost.prepare_injected_case(case,graphs);args=support.science_args('gpt-4o')
    if p['method']=='lea':result=await cost.run_lea(client,args,case,graph,scc,{})
    else:result=await cost.battle.run_naive(client,args.model,case['domain'],graph,scc,naive_profile='direct_subgraph',injected_id=None,temperature=.4)
    if not methods.valid(result,scc,p['method']):raise ValueError('Invalid native baseline candidate')
    r.update(status='complete',selected_result=result,metrics=support.metrics(result,p['method'],case),
      selection={'status':'single_complete_candidate_no_judge','selected_candidate_index':p['candidate_index'],'complete_candidates':1})
   except BaseException as e:
    if isinstance(e,(KeyboardInterrupt,SystemExit,asyncio.CancelledError)):raise
    r.update(status='failed',error_type=type(e).__name__,error=str(e)[:1000])
   finally:
    if client:
     new=client.summary();old=p['old_usage'];r['new_usage']=new
     r['cumulative_usage']={k:old.get(k,0)+new.get(k,0) for k in ('total_tokens','held_tokens','accounted_tokens','estimated_cost_usd')}
     r['strict_budget_eligible']=r['cumulative_usage']['accounted_tokens']<=p['B']
     r['actual_token_excess']=max(0,r['cumulative_usage']['total_tokens']-p['B'])
     r['reused_requests']=len(client.reused);await client.close()
    await ledger.close()
   r['ended_at']=now();save(folder/'final.json',r)
   print(json.dumps({'event':'finished','slot':p['slot'],'method':p['method'],'status':r['status'],'strict_budget_eligible':r.get('strict_budget_eligible'),'new_tokens':r.get('new_usage',{}).get('total_tokens')}),flush=True)
   return r
 results=await asyncio.gather(*(cell(p) for p in plans))
 save(ROOT/'summary.json',{'finished_at':now(),'results':results,'original_reporting_unchanged':True})

def main():
 from dotenv import load_dotenv
 load_dotenv(REPO/'.env')
 lock=(ROOT/'runner.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 plans=[plan_cell(s,m) for s,m in TARGETS]
 public=[{k:v for k,v in p.items() if k not in ('mapping','old_usage')} for p in plans]
 protocol={'created_at':now(),'scope':public,'maximum_new_retries_per_failed_request':2,'concurrency':8,
   'selection_rule':'Resume original candidate with longest successful prefix; tie lowest index; no metrics used.',
   'budget_reporting':'All original and additional tokens retained; over-B recovery is marked ineligible for strict matched-budget reporting.',
   'full11_policy':'No failed API request, so do not resample invalid ranking without authorization.',
   'new_SA_calls':0,'methods_sha256':sha(BASE/'methods_full.py'),'script_sha256':sha(__file__)}
 if '--plan' in sys.argv:
  print(json.dumps(public,ensure_ascii=False,indent=2));return
 save(ROOT/'protocol.json',protocol);save(ROOT/'launch.json',{'pid':os.getpid(),'started_at':now()})
 asyncio.run(run(plans))
if __name__=='__main__':main()

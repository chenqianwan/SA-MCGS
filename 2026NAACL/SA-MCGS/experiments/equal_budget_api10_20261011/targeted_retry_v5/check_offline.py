"""Zero-network validation of frozen prefixes and transport retry bounds."""
import asyncio, tempfile
from pathlib import Path
from types import SimpleNamespace
import run_retry as m
class Stop(BaseException):pass
class Probe(m.RetryClient):
 async def _call(self,prompt,**kw):
  ordinal=int(kw['logical_key'].split('-')[-1]);old=self.plan['mapping'].get((ordinal,kw['retry_index']),[])
  if not old or not any(r['status']=='completed_with_usage' for r,_,_ in old):
   if old:assert old[0][1]['request']['messages']==[{'role':'user','content':prompt}]
   raise Stop(f'window={ordinal}; original_failed={bool(old)}')
  return await super()._call(prompt,**kw)
class Fake:
 def __init__(self,fail=999):
  self.count=0;self.fail=fail
  self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
 async def create(self,**body):
  self.count+=1
  if self.count<=self.fail:raise ConnectionError('offline transport mock')
  return SimpleNamespace(usage={'prompt_tokens':10,'completion_tokens':5,'total_tokens':15},model='gpt-4o',choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))])
 async def close(self):pass
async def main():
 support=m.mod('offline_support',m.BASE.parent/'equal_budget_all80_20261009/science_support.py')
 _,cost,_,graphs,_=support.load_science()
 cases={c['case_uid']:c for c in m.read(m.BASE/'case_plans.json')['gpt-4o']}
 for slot,method in m.TARGETS:
  p=m.plan_cell(slot,method)
  if 'skip_reason' in p:continue
  with tempfile.TemporaryDirectory() as tmp:
   t=Path(tmp);m.save(t/'legacy_call_ids.json',[]);l=m.api.GlobalLedger(t/'ledger.jsonl');await l.initialize();fake=Fake()
   c=Probe({'model':'gpt-4o','base_url':m.original.ENDPOINT,'max_model_len':131072},ledger=l,case_id=p['case_uid'],method=method,call_log_dir=t/'calls',token_cap=2000000,plan=p,provider_client=fake)
   case=cases[p['case_uid']];graph,scc,_,_=cost.prepare_injected_case(case,graphs);args=support.science_args('gpt-4o')
   try:
    if method=='lea':await cost.run_lea(c,args,case,graph,scc,{})
    else:await cost.battle.run_naive(c,args.model,case['domain'],graph,scc,naive_profile='direct_subgraph',injected_id=None,temperature=.4)
   except Stop as e:print('prefix OK',slot,method,len(c.reused),str(e),flush=True)
   else:raise AssertionError('Expected partial candidate')
   assert fake.count==0 and len(l._calls)==0
   await c.close();await l.close()
 for old,fail,expected in [(True,5,2),(True,1,2),(False,5,3),(False,2,3)]:
  with tempfile.TemporaryDirectory() as tmp:
   t=Path(tmp);m.save(t/'legacy_call_ids.json',[]);l=m.api.GlobalLedger(t/'ledger.jsonl');await l.initialize();fake=Fake(fail)
   mapping={}
   if old:mapping[(0,0)]=[({'status':'unknown_failure'},{'request':{'model':'gpt-4o','messages':[{'role':'user','content':'test'}],'temperature':.4,'response_format':{'type':'json_object'}}},'unused')]
   c=m.RetryClient({'model':'gpt-4o','base_url':m.original.ENDPOINT,'max_model_len':131072},ledger=l,case_id='mock',method='lea',call_log_dir=t/'calls',token_cap=2000000,plan={'candidate_index':1,'mapping':mapping},provider_client=fake)
   try:await c.call_json('test',temperature=.4,max_tokens=2048)
   except m.api.BudgetStop:assert fail>=expected
   else:assert fail<expected
   assert fake.count==expected and len(l._calls)==expected
   await c.close();await l.close()
   print('retry bound OK',old,fail,expected,flush=True)
 print('ALL OFFLINE CHECKS PASSED',flush=True)
if __name__=='__main__':asyncio.run(main())

"""Zero-network tests for the new model routes, lifecycle, and exact old science."""
import argparse,asyncio,copy,json,os,re,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import generic_launcher as G
L=G.L

def config(key='qwen3.5-9b'):
 return {'version':1,'model_key':key,'checkpoint_repository':G.MODEL_REGISTRY[key]['repository'],
  'checkpoint_revision':'a'*40,'served_model_name':key,'base_url':f"http://127.0.0.1:{G.MODEL_REGISTRY[key]['port']}/v1",
  'dtype':'bfloat16','quantization':None,'tensor_parallel_size':1,'max_model_len':131072,
  'trust_remote_code':key.startswith('kimi'),'chat_template_kwargs':{'enable_thinking':False} if key.startswith('qwen') else {}}
def args(path,attempts=4):
 return argparse.Namespace(output_dir=path,base_url=G.CFG['base_url'],checkpoint_revision=G.CFG['checkpoint_revision'],
  llm_timeout=10,case_concurrency=8,shard_count=8,shard_index=0,mode='run',max_model_len=131072,max_case_attempts=attempts)
class Tokenizer:
 def __init__(self):self.kwargs=[]
 def apply_chat_template(self,*a,**kw):self.kwargs.append(kw);return [1,2,3]
class Usage:
 def model_dump(self):return {'prompt_tokens':3,'completion_tokens':3,'total_tokens':6}
class Server:
 def __init__(self,mode='ok'):self.mode=mode;self.calls=0;self.requests=[]
 async def create(self,**request):
  self.calls+=1;self.requests.append(request)
  if self.mode=='connection':raise ConnectionError('offline fixture')
  if self.mode=='timeout':raise TimeoutError('offline timeout fixture')
  if self.mode=='503':
   exc=RuntimeError('offline busy fixture');exc.status_code=503;raise exc
  if self.mode=='400':
   exc=RuntimeError('offline bad request');exc.status_code=400;raise exc
  if self.mode=='forbid':raise AssertionError('Unexpected new request')
  ids=re.findall(r'^### ID: (.+)$',request['messages'][-1]['content'],re.M)
  payload={'clause_evaluations':{i:{'risk_score':0.4} for i in ids},'conflicts':['critical_pairs']} if self.mode=='schema' else {}
  return SimpleNamespace(model=L.ALIAS,usage=Usage(),choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)),finish_reason='stop')])

class ConfigurationTests(unittest.TestCase):
 def test_qwen_no_thinking_and_only_new_model_cap_override(self):
  cost=G.configure(config());request=G.request_payload('test',0.4,2048,None,{'type':'json_object'})
  self.assertEqual(request['extra_body'],{'chat_template_kwargs':{'enable_thinking':False}})
  tokenizer=Tokenizer();G.token_count(tokenizer,request)
  self.assertIs(tokenizer.kwargs[0]['enable_thinking'],False)
  self.assertEqual(cost.battle._model_json_max_tokens('qwen3.5-9b',12000),12000)
  self.assertEqual(cost.battle._model_json_max_tokens('qwen2.5-72b',12000),8192)
  bad=config();bad['chat_template_kwargs']['enable_thinking']=True
  with self.assertRaises(L.IntegrityStop):G.configure(bad)
  bad=config();bad['base_url']='https://external.invalid/v1'
  with self.assertRaises(L.IntegrityStop):G.configure(bad)

class LifecycleTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):
  cls.cost=G.configure(config());cls.manifest=L.verify_bundle();cls.graphs=L.restore_graphs(cls.cost,cls.manifest)
 def setUp(self):
  G.configure(config());os.environ['LOCAL_VLLM_API_KEY']='offline-no-network'
  self.temporary=tempfile.TemporaryDirectory();self.path=Path(self.temporary.name);self.args=args(self.path)
  self.plan,self.frozen,_=G.prepare(self.args,self.cost,self.manifest,self.graphs)
  self.case=next(c for c in self.plan if c['main_case_order']==20)
  self.original_factory=G.make_client_class
  self.original_health=G.endpoint_health;self.health_calls=0;self.health_status=False
  async def health(_args):
   self.health_calls+=1
   return {'healthy':self.health_status,'fixture':True,'expected_model':L.ALIAS}
  G.endpoint_health=health
 def tearDown(self):G.make_client_class=self.original_factory;G.endpoint_health=self.original_health;self.temporary.cleanup()
 def install(self,server):
  original=self.original_factory
  class Factory(original(self.cost)):
   def __init__(inner,*a,**kw):
    super().__init__(*a,**kw);real=inner.client
    inner.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=server.create)),close=real.close)
  G.make_client_class=lambda cost:Factory
 async def run_method(self,method='naive-single'):
  return await G.run_one(self.cost,self.args,self.case,method,self.graphs,self.frozen,Tokenizer())
 async def test_scientific_schema_failure_terminal_and_not_retried(self):
  server=Server('schema');self.install(server)
  await self.run_method('sa-mcgs')
  file=L.result_path(self.args,self.case,'sa-mcgs');r=L.read(file)
  self.assertEqual(r['completion_status'],'strict_experiment_failure');self.assertEqual(r['error_type'],'ValidationError')
  self.assertFalse(G.infra_path(self.args,self.case,'sa-mcgs').exists());before=L.sha(file);n=server.calls
  await self.run_method('sa-mcgs');self.assertEqual(server.calls,n);self.assertEqual(before,L.sha(file))
 async def test_endpoint_retry_counter_survives_attempts_and_stops(self):
  self.args.max_case_attempts=2;self.frozen=G.protocol(self.args,self.cost,self.manifest)
  server=Server('connection');self.install(server)
  for _ in range(2):
   with self.assertRaises(G.EndpointRecoveryRequired):await self.run_method()
  r=L.read(G.infra_path(self.args,self.case,'naive-single'))
  self.assertEqual(r['attempts'],2);self.assertEqual(r['completion_status'],'infrastructure_failure')
  self.assertFalse(L.result_path(self.args,self.case,'naive-single').exists())
  n=server.calls;await self.run_method();self.assertEqual(server.calls,n)
 async def test_request_specific_http400_skips_without_endpoint_restart(self):
  server=Server('400');self.install(server);await self.run_method()
  r=L.read(G.infra_path(self.args,self.case,'naive-single'))
  self.assertEqual(r['infrastructure_category'],'provider_request_error')
  # Next method can still complete under the same process; failure did not end batch.
  good=Server();self.install(good);await self.run_method('lea')
  self.assertEqual(L.read(L.result_path(self.args,self.case,'lea'))['completion_status'],'complete')
 async def test_healthy_endpoint_timeout_and503_skip_only_failed_cell(self):
  self.health_status=True
  for mode,method in [('timeout','naive-single'),('503','lea')]:
   self.install(Server(mode));await self.run_method(method)
   record=L.read(G.infra_path(self.args,self.case,method))
   self.assertTrue(record['details']['endpoint_health']['healthy'])
   self.assertEqual(record['infrastructure_category'],'provider_request_error')
  self.assertEqual(self.health_calls,2)
 async def test_sa400_cancels_siblings_without_misclassifying_outage(self):
  class ConcurrentServer(Server):
   async def create(inner,**request):
    inner.calls+=1;index=inner.calls
    if index==1:
     await asyncio.sleep(.01)
     exc=RuntimeError('offline rejected first request');exc.status_code=400;raise exc
    await asyncio.Event().wait()
  server=ConcurrentServer();self.install(server)
  await asyncio.wait_for(self.run_method('sa-mcgs'),timeout=3)
  record=L.read(G.infra_path(self.args,self.case,'sa-mcgs'))
  self.assertEqual(record['details']['http_statuses'],[400]);self.assertEqual(self.health_calls,0)
  self.assertEqual(server.calls,8)
  logs=[json.loads(line) for line in (self.path/'call_logs'/f"{self.case['case_id']}__sa-mcgs.jsonl").read_text().splitlines()]
  self.assertEqual(sum(r.get('error_type')=='CancelledError' for r in logs),7)
 async def test_one_shot_uses_full12000_and_strict_empty_json(self):
  server=Server();self.install(server);await self.run_method()
  self.assertEqual(server.requests[0]['max_tokens'],12000)
  result=L.read(L.result_path(self.args,self.case,'naive-single'))
  self.assertEqual(result['completion_status'],'strict_experiment_failure')
  result['error_type']='RuntimeError'
  with self.assertRaises(L.IntegrityStop):G.validate_result(self.cost,self.args,self.case,'naive-single',self.graphs,self.frozen,result)
 async def test_partial_cache_replays_without_new_request_and_binds_config(self):
  server=Server();self.install(server)
  client=G.make_client_class(self.cost)(self.args,self.case,'lea',self.frozen,Tokenizer())
  await client.call_json('cached fixture',temperature=0.4,max_tokens=2048);await client.close()
  blocked=Server('forbid');self.install(blocked)
  resumed=G.make_client_class(self.cost)(self.args,self.case,'lea',self.frozen,Tokenizer())
  self.assertEqual(await resumed.call_json('cached fixture',temperature=0.4,max_tokens=2048),{})
  resumed.journal.assert_consumed();await resumed.close();self.assertEqual(blocked.calls,0)
  G.configure(config('kimi-vl-a3b-instruct'))
  with self.assertRaises(L.IntegrityStop):G.prepare(args(self.path),self.cost,self.manifest,self.graphs)
 async def test_summary_keeps_infrastructure_distinct_and_detects_double_terminal(self):
  bad=Server('400');self.install(bad);await self.run_method()
  report=G.summarize(self.args,self.plan,self.cost,self.graphs,self.frozen)
  self.assertEqual(report['infrastructure_failure_results'],1);self.assertEqual(report['scientific_terminal_results'],0)
  self.assertFalse(report['scientific_complete']);self.assertEqual(report['unresolved_results'],239)
  L.write(L.result_path(self.args,self.case,'naive-single'),{})
  with self.assertRaises(L.IntegrityStop):G.summarize(self.args,self.plan,self.cost,self.graphs,self.frozen)
if __name__=='__main__':unittest.main()

import json,time,hashlib,collections
from pathlib import Path
root=Path('/aifs4su/hansirui_3rd/chenlong/kq35_20260924');output=root/'results/qwen35'
def read(p):return json.loads(p.read_text())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):
 result=[]
 for line in p.read_text().splitlines():
  try:result.append(json.loads(line))
  except json.JSONDecodeError:pass
 return result
report={'at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'api_calls':0,'read_only':True,'violations':[]}
report['status']=read(root/'status/qwen35.json') if (root/'status/qwen35.json').exists() else None
frozen=read(output/'frozen_protocol.json');protocol=digest(frozen);report['protocol_sha256']=protocol;report['frozen_fields']={k:frozen.get(k) for k in ['model','served_model','checkpoint_repository','checkpoint_revision','base_url','producer_sha256','one_shot','lea','max_model_len']}
producer=sha(root/'runner/generic_launcher.py');report['producer_actual_sha256']=producer
if producer!=frozen['producer_sha256']:report['violations'].append('producer hash changed')
plan={c['case_id']:c for c in read(output/'case_plan.json')}
methods=collections.defaultdict(lambda:{'started_requests':0,'recorded_responses':0,'completed_results':0,'samples':[],'usage_delta_counts':collections.Counter()})
for p in sorted((output/'call_cache').glob('*/*/requests.jsonl')):
 case,method=p.parent.parent.name,p.parent.name
 for item in rows(p):
  req=item['request'];mm=methods[method];mm['started_requests']+=1
  if req.get('model')!='qwen3.5-9b':report['violations'].append('request alias '+case+'/'+method)
  if req.get('extra_body')!={'chat_template_kwargs':{'enable_thinking':False}}:report['violations'].append('thinking flag '+case+'/'+method)
  cap=12000 if method=='naive-single' else 2048
  if req.get('max_tokens')!=cap:report['violations'].append('output cap '+case+'/'+method)
  if item['request_sha256']!=digest({'request':req,'protocol_sha256':protocol}):report['violations'].append('request hash '+case+'/'+method)
  if item.get('protocol_sha256')!=protocol:report['violations'].append('request protocol '+case+'/'+method)
  if len(mm['samples'])<2:mm['samples'].append({'case_id':case,'call_index':item['call_index'],'model':req['model'],'max_tokens':req['max_tokens'],'temperature':req.get('temperature'),'response_format':req.get('response_format'),'extra_body':req.get('extra_body'),'request_sha256':item['request_sha256']})
 rp=p.parent/'responses.jsonl'
 if rp.exists():
  for item in rows(rp):
   mm=methods[method];mm['recorded_responses']+=1;r=item['record'];usage=item['usage'];count=r.get('prompt_tokens_preflight');actual=usage.get('prompt_tokens');mm['usage_delta_counts'][str(actual-count) if actual is not None and count is not None else 'unknown']+=1
   if item['returned_model']!='qwen3.5-9b':report['violations'].append('response alias '+case+'/'+method)
   if len(mm.get('usage_samples',[]))<2:mm.setdefault('usage_samples',[]).append({'case_id':case,'call_index':item['call_index'],'tokenizer_prompt_tokens':count,'server_usage':usage,'finish_reason':r.get('finish_reason')})
fields={'naive-single':'direct_risk_subgraph_nodes','lea':'lea_risk_subgraph_nodes','sa-mcgs':'core_evidence_risk_subgraph_nodes'}
for p in sorted((output/'results').glob('*.json')):
 r=read(p);case=r['case_id'];method=r['cost_audit_method'];c=plan[case];mm=methods[method];mm['completed_results']+=1
 for k,expected in {'model':'qwen3.5-9b','case_uid':c['case_uid'],'protocol_sha256':protocol,'producer_sha256':producer,'checkpoint_repository':frozen['checkpoint_repository'],'checkpoint_revision':frozen['checkpoint_revision'],'requested_model_id':'qwen3.5-9b','base_url':'http://127.0.0.1:18083/v1','chat_template_kwargs':{'enable_thinking':False}}.items():
  if r.get(k)!=expected:report['violations'].append('result '+k+' '+case+'/'+method)
 for k in ['planned_case_identity','planned_scc_clause_ids','planned_injection_identity']:
  if r.get(k)!=c[k]:report['violations'].append('result identity '+k+' '+case+'/'+method)
 for a,b in [('actual_case_identity','planned_case_identity'),('actual_scc_clause_ids','planned_scc_clause_ids'),('actual_injection_identity','planned_injection_identity')]:
  if r.get(a)!=c[b]:report['violations'].append('actual identity '+a+' '+case+'/'+method)
 if len(mm.get('result_samples',[]))<2:mm.setdefault('result_samples',[]).append({'case_id':case,'state':r['completion_status'],'protocol_sha256':r['protocol_sha256'],'producer_sha256':r['producer_sha256'],'case_uid':r['case_uid'],'scientific_node_field':fields[method],'node_field_present':fields[method] in r,'internal_concurrency':r['internal_concurrency'],'error_type':r.get('error_type')})
report['methods']=dict(methods)
report['tokenization_report']={k:v for k,v in read(output/'tokenization_report.json').items() if k not in ['rows','overflow']}
if frozen.get('base_url')!='http://127.0.0.1:18083/v1':report['violations'].append('nonlocal endpoint')
report['scientific_source_hash_match']=all(sha(root/'runner/repo'/name)==value for name,value in frozen['original_scientific_code_sha256'].items())
report['server_commands']=[read(p) for p in sorted((root/'runs/qwen35-395518').glob('server_command_*.json'))]
report['infra_records']=len(list((output/'infrastructure_failures').glob('*.json')))
print(json.dumps(report))


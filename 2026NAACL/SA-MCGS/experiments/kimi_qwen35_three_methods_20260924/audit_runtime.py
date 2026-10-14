#!/usr/bin/env python3
"""Read one real request/response per method without sending model requests."""
import json
from cluster_io import HERE,REMOTE,remote
CODE=r'''import pathlib,json,time,hashlib
root=pathlib.Path(ROOT)
out={'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'api_calls':0,'read_only':True,'models':{}}
for key in ['kimi','qwen35']:
 cfg=json.loads((root/'configs'/f'{key}.json').read_text())
 model_out=root/'results'/key
 evidence={'methods':{},'all_three_methods_observed':False,'passed':False};out['models'][key]=evidence
 for method in ['naive-single','lea','sa-mcgs']:
  candidates=sorted((model_out/'call_cache').glob(f'*/{method}/responses.jsonl'))
  for path in candidates:
   if not path.stat().st_size:continue
   with path.open() as stream:response=json.loads(next(stream))
   record=response['record'];request=record['request']
   usage=response['usage'];expected_max=12000 if method=='naive-single' else 2048
   checks={'model_alias':request['model']==cfg['served_model_name']==response['returned_model'],
           'token_budget':request['max_tokens']==expected_max,
           'temperature':request['temperature']==(0.0 if method=='naive-single' else 0.4),
           'non_thinking':((request.get('extra_body') or {}).get('chat_template_kwargs',{})==cfg['chat_template_kwargs']),
           'json_response':request.get('response_format')=={'type':'json_object'},
           'tokenizer_matches_server':record['prompt_tokens_preflight']==usage['prompt_tokens'],
           'local_endpoint':cfg['base_url'].startswith('http://127.0.0.1:')}
   evidence['methods'][method]={'response_file':str(path.relative_to(root)),
       'case_id':record['case_id'],'request_sha256':response['request_sha256'],
       'checks':checks,'passed':all(checks.values()),'prompt_tokens_preflight':record['prompt_tokens_preflight'],
       'server_prompt_tokens':usage['prompt_tokens'],'max_tokens':request['max_tokens'],
       'finish_reason':record.get('finish_reason'),'chat_template_kwargs':cfg['chat_template_kwargs']}
   break
 evidence['all_three_methods_observed']=len(evidence['methods'])==3
 evidence['passed']=evidence['all_three_methods_observed'] and all(r['passed'] for r in evidence['methods'].values())
print(json.dumps(out))
'''.replace('pathlib.Path(ROOT)','pathlib.Path('+repr(REMOTE)+')')
if __name__=='__main__':
    report=json.loads(remote(CODE))
    (HERE/'actual_request_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))

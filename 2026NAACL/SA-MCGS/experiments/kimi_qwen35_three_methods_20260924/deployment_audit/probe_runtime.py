#!/usr/bin/env python3
"""Read-only CPU compatibility probe; no model weights or remote disk writes.

Fetches only the 2.8 MB official Kimi vocabulary into this local audit directory.
The remote tokenizer reads a Linux anonymous memory file. No HF dynamic-module
cache is used, and tiktoken's persistent cache is explicitly disabled.
"""
import argparse
import base64
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parent

REMOTE = r'''
import base64,datetime,hashlib,importlib,importlib.metadata,json,os,pathlib,sys,types
os.environ['TIKTOKEN_CACHE_DIR']=''
report={'checked_at':datetime.datetime.now().astimezone().isoformat(),
        'remote_persistent_writes':False,'gpu_used':False,'model_calls':0,
        'versions':{n:importlib.metadata.version(n) for n in ['vllm','transformers','tokenizers','tiktoken','jinja2','torch']},'checks':[]}
for module,names in [
 ('transformers.tokenization_utils',['PreTrainedTokenizer']),
 ('transformers.utils',['to_py_obj']),
 ('transformers.convert_slow_tokenizer',['bytes_to_unicode']),
 ('transformers.processing_utils',['ProcessingKwargs','ProcessorMixin','Unpack']),
 ('vllm.transformers_utils.configs.kimi_vl',['KimiVLConfig']),
 ('transformers.models.qwen3_5.configuration_qwen3_5',['Qwen3_5Config'])]:
 try:
  m=importlib.import_module(module)
  report['checks'].append({'name':'import '+module,'symbols':names,'passed':all(hasattr(m,n) for n in names)})
 except Exception as e:
  report['checks'].append({'name':'import '+module,'passed':False,'error':type(e).__name__+': '+str(e)})
base=pathlib.Path(importlib.metadata.distribution('vllm').locate_file('vllm'))
registry=(base/'model_executor/models/registry.py').read_text()
for name in ['KimiVLForConditionalGeneration','Qwen3_5ForConditionalGeneration']:
 report['checks'].append({'name':'vllm registry '+name,'passed':name in registry})
report['default_kwargs_sources']=[]
for p in (base/'entrypoints').rglob('*.py'):
 if p.stat().st_size>500000:continue
 t=p.read_text()
 if 'default_chat_template_kwargs' in t:
  report['default_kwargs_sources'].append(str(p.relative_to(base)))
report['checks'].append({'name':'vllm default chat template kwargs available','passed':bool(report['default_kwargs_sources'])})
try:
 source=base64.b64decode(PAYLOAD['tokenizer_source_b64'])
 assert hashlib.sha256(source).hexdigest()==PAYLOAD['tokenizer_source_sha256']
 vocab=base64.b64decode(PAYLOAD['vocab_b64'])
 assert hashlib.sha256(vocab).hexdigest()==PAYLOAD['vocab_sha256']
 module=types.ModuleType('audited_official_kimi_tokenizer')
 module.__file__='<official-pinned-tokenization_moonshot.py>'
 sys.modules[module.__name__]=module
 exec(compile(source,module.__file__,'exec'),module.__dict__)
 from tokenizers import AddedToken
 cfg=dict(PAYLOAD['tokenizer_config'])
 cfg['added_tokens_decoder']={int(k):AddedToken(**v) for k,v in cfg['added_tokens_decoder'].items()}
 for key in ('auto_map','tokenizer_class'):cfg.pop(key,None)
 fd=os.memfd_create('audited-kimi-tiktoken',flags=os.MFD_CLOEXEC)
 try:
  os.write(fd,vocab)
  tok=module.TikTokenTokenizer(vocab_file='/proc/self/fd/'+str(fd),**cfg)
  examples=['Hello world.','中华人民共和国民法典。','Return {"status":"ok"}.']
  rows=[]
  for text in examples:
   ids=tok.encode(text,add_special_tokens=False)
   rows.append({'text':text,'token_count':len(ids),'roundtrip':tok.decode(ids)==text})
  messages=[{'role':'system','content':'You are a helpful assistant.'},{'role':'user','content':'Return only OK.'}]
  rendered=tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
  ids=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=False)
  direct=tok.encode(rendered,add_special_tokens=False)
  report['kimi_tokenizer']={'loaded':True,'class':type(tok).__name__,'vocab_size':tok.vocab_size,
   'roundtrips':rows,'chat_template_tail':rendered[-80:],
   'chat_template_token_count':len(ids),'chat_template_matches_direct_encoding':ids==direct,
   'source_sha256':PAYLOAD['tokenizer_source_sha256'],'vocab_sha256':PAYLOAD['vocab_sha256'],
   'loader_scope':'Exact official tokenizer class constructor, with anonymous-memory vocabulary; HF AutoTokenizer cache/download path not exercised.'}
  report['checks'].append({'name':'Kimi tokenizer constructor and chat template','passed':all(x['roundtrip'] for x in rows) and ids==direct})
 finally:os.close(fd)
except Exception as e:
 report['kimi_tokenizer']={'loaded':False,'error':type(e).__name__+': '+str(e)}
 report['checks'].append({'name':'Kimi tokenizer constructor and chat template','passed':False,'error':type(e).__name__+': '+str(e)})
try:
 from transformers.utils.chat_template_utils import _compile_jinja_template
 template=_compile_jinja_template(PAYLOAD['qwen_chat_template'])
 text=template.render(messages=[{'role':'user','content':'Return only OK.'}],add_generation_prompt=True,enable_thinking=False)
 report['qwen_non_thinking']={'rendered_tail':text[-90:],'empty_think_suffix':text.endswith('<think>\n\n</think>\n\n')}
 report['checks'].append({'name':'Qwen official non-thinking template','passed':report['qwen_non_thinking']['empty_think_suffix']})
except Exception as e:
 report['checks'].append({'name':'Qwen official non-thinking template','passed':False,'error':type(e).__name__+': '+str(e)})
report['passed']=all(x['passed'] for x in report['checks'])
print(json.dumps(report))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh-alias',default='Group3_dgx-127',choices=['Group3_slogin','Group3_dgx-127'])
    args=parser.parse_args()
    metadata=json.loads((ROOT/'kimi_official.json').read_text())
    entry=next(x for x in metadata['siblings'] if x['rfilename']=='tiktoken.model')
    path=ROOT/'kimi/tiktoken.model'
    if not path.is_file():
        url='https://huggingface.co/'+metadata['id']+'/resolve/'+metadata['sha']+'/tiktoken.model'
        with urllib.request.urlopen(url,timeout=30) as response:data=response.read()
        path.write_bytes(data)
    data=path.read_bytes()
    digest=hashlib.sha256(data).hexdigest()
    blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    expected=entry.get('lfs',{}).get('sha256')
    if len(data)!=entry['size'] or (digest!=expected if expected else blob!=entry['blobId']):
        raise RuntimeError('Official vocabulary checksum mismatch')
    source=(ROOT/'kimi/tokenization_moonshot.py').read_bytes()
    proof=json.loads((ROOT/'kimi_small_file_verification.json').read_text())
    expected_source=next(x['sha256'] for x in proof if x['path']=='tokenization_moonshot.py')
    if hashlib.sha256(source).hexdigest()!=expected_source:raise RuntimeError('Tokenizer source changed')
    payload={'tokenizer_source_b64':base64.b64encode(source).decode(),'tokenizer_source_sha256':expected_source,
             'vocab_b64':base64.b64encode(data).decode(),'vocab_sha256':digest,
             'tokenizer_config':json.loads((ROOT/'kimi/tokenizer_config.json').read_text()),
             'qwen_chat_template':(ROOT/'qwen/chat_template.jinja').read_text()}
    script='PAYLOAD='+repr(payload)+'\n'+REMOTE
    command=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15',args.ssh_alias,
             '/aifs4su/hansirui/vllm-dsv4-venv/bin/python3 -I -B -']
    result=subprocess.run(command,input=script,capture_output=True,text=True,timeout=150)
    if result.returncode:
        report={'probe_completed':False,'exit_code':result.returncode,'stderr':result.stderr[-3000:],
                'checked_at':datetime.datetime.now().astimezone().isoformat()}
    else:
        report=json.loads(result.stdout);report['warnings']=result.stderr[-3000:]
    output=ROOT/('runtime_compatibility.json' if result.returncode==0 else 'latest_probe_connection_failure.json')
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report.get('passed') else 1


if __name__=='__main__':raise SystemExit(main())

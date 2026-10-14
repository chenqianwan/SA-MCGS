#!/usr/bin/env python3
"""Run one model and all experiment workers inside its one-GPU Slurm job.

Recover only this job's endpoint, using persistent bounded attempts; finished
observations are immutable. Operational skips remain distinct from outputs.
"""
import argparse
import atexit
import collections
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

STOP=False
METHODS=('naive-single','lea','sa-mcgs')
class OperationalStop(Exception): pass
def now(): return time.strftime('%Y-%m-%dT%H:%M:%S%z')
def read(p): return json.loads(p.read_text())
def write(p, obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(f'.{p.name}.{os.getpid()}.tmp');tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n');tmp.replace(p)
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def counts(output):
    c=collections.Counter()
    for folder in ('results','infrastructure_failures'):
        for p in (output/folder).glob('*.json'):
            obj=read(p);c[obj.get('cost_audit_method',obj.get('method','unknown'))+':'+obj.get('completion_status','unknown')]+=1
    return dict(c)

class Children:
    def __init__(self,run):self.run=run;self.children=[]
    def spawn(self,name,cmd,cwd):
        with (self.run/(name+'.log')).open('ab',buffering=0) as log:
            p=subprocess.Popen(cmd,cwd=cwd,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        self.children.append((name,p))
        write(self.run/'children.json',{'at':now(),'children':[{'name':n,'pid':p.pid,'exit_code':p.poll()} for n,p in self.children]})
        return p
    def cleanup(self):
        # A crashed server leader may leave its own model workers alive.
        # Every recorded group was created here with start_new_session=True.
        def alive(p):
            try:os.killpg(p.pid,0);return True
            except ProcessLookupError:return False
        active=[p for _,p in reversed(self.children) if alive(p)]
        for p in active:
            try:os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        deadline=time.monotonic()+20
        while any(alive(p) for p in active) and time.monotonic()<deadline:
            for p in active:p.poll()
            time.sleep(.2)
        for p in active:
            if alive(p):
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:pass
        # Never target retired PGIDs again on a later recovery cycle.
        self.children=[]

def verify_model(root,key,cfg):
    marker=read(root/'prep'/f'{key}_complete.json');meta=read(root/'deployment_audit'/f'{key}_official.json')
    if not marker.get('verified') or marker['state']!='complete' or meta['sha']!=cfg['checkpoint_revision'] or marker['revision']!=meta['sha'] or meta['id']!=cfg['checkpoint_repository']:
        raise RuntimeError('Model preparation identity/verification failure')
    expected={x['rfilename']:x for x in meta['siblings'] if '/' not in x['rfilename'] and x['rfilename']!='.gitattributes'}
    if {x['path'] for x in marker['files']}!=set(expected):raise RuntimeError('Incomplete checkpoint file coverage')
    for row in marker['files']:
        p=root/'models'/key/row['path'];official=expected[row['path']]
        if p.resolve()!=p or p.stat().st_size!=official['size'] or sha(p)!=row['sha256']:
            raise RuntimeError('Checkpoint changed: '+row['path'])
        if official.get('lfs') and row['sha256']!=official['lfs']['sha256']:raise RuntimeError('Official weight hash mismatch')
        if not official.get('lfs') and row['git_blob_sha1']!=official['blobId']:raise RuntimeError('Official config hash mismatch')
    return {'verified':True,'repository':meta['id'],'revision':meta['sha'],'files':len(expected),'at':now()}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--model',choices=['kimi','qwen35'],required=True)
    a=parser.parse_args();root=a.root.resolve();key=a.model;job=os.environ.get('SLURM_JOB_ID','')
    if not job.isdigit() or os.getuid()!=1083 or str(root)!='/aifs4su/hansirui_3rd/chenlong/kq35_20260924':raise RuntimeError('Allocated Slurm job/personal root required')
    cfg=read(root/'configs'/f'{key}.json');run=root/'runs'/f'{key}-{job}';run.mkdir(parents=True,exist_ok=True)
    output=root/'results'/key;output.mkdir(parents=True,exist_ok=True)
    lock=(root/'locks'/f'{key}_coordinator.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    children=Children(run);atexit.register(children.cleanup)
    def stop(sig,frame):
        global STOP
        STOP=True
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGUSR1):signal.signal(sig,stop)
    deadline=time.monotonic()+432000-600
    state={'model':key,'job_id':job,'started_at':now(),'hostname':socket.gethostname(),'expected_results':240,'external_api_cost_usd':0,'same_node_model_and_workers':True}
    def status(**changes):
        state.update(changes);state.update(updated_at=now(),counts=counts(output));write(run/'status.json',state);write(root/'status'/f'{key}.json',state)
        print(json.dumps(state,ensure_ascii=False),flush=True)
    runner=root/'runner/generic_launcher.py'
    common=[sys.executable,'-B',str(runner),'--model-config',str(root/'configs'/f'{key}.json'),'--output-dir',str(output),
            '--tokenizer-path',str(root/'models'/key),'--case-concurrency','8','--max-case-attempts','4','--llm-timeout','600']
    def bounded(name,args,timeout=1800):
        p=children.spawn(name,[*common,*args],runner.parent);end=time.monotonic()+timeout
        while p.poll() is None:
            if STOP or time.monotonic()>deadline:raise InterruptedError('Allocation stopping; preserve checkpoints')
            if time.monotonic()>end:
                children.cleanup()
                return 124
            time.sleep(1)
        return p.returncode
    base=cfg['base_url'];port=int(base.split(':')[2].split('/')[0]);alias=cfg['served_model_name']
    def healthy():
        try:
            with urlopen(base+'/models',timeout=5) as res:body=json.load(res)
            return [x.get('id') for x in body.get('data',[])]==[alias]
        except (OSError,ValueError):return False
    try:
        status(status='verifying')
        manifest=read(root/'gpu_staging_manifest.json')
        for n,e in manifest['files'].items():
            p=root/n
            if p.resolve()!=p or p.stat().st_size!=e['bytes'] or sha(p)!=e['sha256']:raise RuntimeError('Staged input changed: '+n)
        write(run/'checkpoint_verified.json',verify_model(root,key,cfg))
        import torch
        if torch.cuda.device_count()!=1:raise OperationalStop('Exactly one Slurm-visible GPU required')
        total=torch.cuda.get_device_properties(0).total_memory;free,_=torch.cuda.mem_get_info(0);gpu=torch.cuda.get_device_name(0)
        if 'H800' not in gpu or total<75*1024**3 or free<.9*total:raise OperationalStop('Unexpected allocated GPU or existing memory use')
        write(run/'runtime.json',{'hostname':socket.gethostname(),'gpu':gpu,'total_bytes':total,'free_before_bytes':free,
              'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'),'versions':{x:importlib.metadata.version(x) for x in ['torch','vllm','transformers','tiktoken']}})
        status(status='tokenizing_all_cases')
        token_code=bounded('tokenize',['--mode','tokenize'],3600)
        if token_code==78:raise RuntimeError('Frozen protocol integrity check failed')
        if token_code!=0:raise OperationalStop('Prompt/tokenizer preflight failed with code '+str(token_code))
        history_path=root/'recovery'/f'{key}.json'
        history=read(history_path) if history_path.exists() else {'model':key,'max_server_attempts':4,'server_attempts':[]}
        complete=False;last_reason='endpoint recovery exhausted'
        while len(history['server_attempts'])<4:
            if STOP or time.monotonic()>deadline:raise InterruptedError('Preserve checkpoints at allocation end')
            children.cleanup()
            attempt=len(history['server_attempts'])+1
            event={'attempt':attempt,'job_id':job,'started_at':now()};history['server_attempts'].append(event);write(history_path,history)
            # Binding is non-destructive: if another process owns the port we never kill it.
            try:
                with socket.socket() as sock:
                    sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);sock.bind(('127.0.0.1',port))
            except OSError as exc:
                last_reason='Local endpoint port unavailable: '+type(exc).__name__
                event.update(ended_at=now(),reason=last_reason);write(history_path,history);continue
            cmd=[sys.executable,'-B','-m','vllm.entrypoints.openai.api_server','--model',str(root/'models'/key),
                 '--served-model-name',alias,'--host','127.0.0.1','--port',str(port),'--dtype','bfloat16','--tensor-parallel-size','1',
                 '--max-model-len',str(cfg['max_model_len']),'--max-num-seqs','32','--gpu-memory-utilization','0.85',
                 '--enable-chunked-prefill','--max-num-batched-tokens','8192','--generation-config','vllm',
                 '--override-generation-config','{"top_k":-1,"top_p":1.0,"repetition_penalty":1.0}',
                 '--language-model-only','--enforce-eager','--no-async-scheduling']
            if cfg['trust_remote_code']:cmd.append('--trust-remote-code')
            if cfg['chat_template_kwargs']:cmd += ['--default-chat-template-kwargs',json.dumps(cfg['chat_template_kwargs'])]
            write(run/f'server_command_{attempt}.json',{'argv':cmd,'base_url':base,'attempt':attempt})
            server=children.spawn(f'server_{attempt}',cmd,root);status(status='server_starting',server_attempt=attempt)
            end=time.monotonic()+1800
            while server.poll() is None and time.monotonic()<end and not healthy():
                if STOP or time.monotonic()>deadline:raise InterruptedError('Stop during startup')
                time.sleep(3)
            if server.poll() is not None or not healthy():
                last_reason='Model server failed startup';event.update(ended_at=now(),reason=last_reason,exit_code=server.poll());write(history_path,history);continue
            status(status='fixed_case20_smoke')
            code=bounded(f'smoke_{attempt}',['--mode','smoke'],5400)
            if code!=0:
                last_reason=f'Smoke worker exited {code}';event.update(ended_at=now(),reason=last_reason);write(history_path,history)
                if code==78:break
                continue
            workers=[children.spawn(f'worker_{attempt}_{i}',[*common,'--mode','run','--shard-count','8','--shard-index',str(i)],runner.parent) for i in range(8)]
            status(status='running',server_attempt=attempt)
            last_status=time.monotonic();failed_health=0
            while True:
                if STOP or time.monotonic()>deadline:raise InterruptedError('Stop during experiment')
                codes=[p.poll() for p in workers]
                if all(c==0 for c in codes):complete=True;break
                if server.poll() is not None or any(c not in (None,0) for c in codes):
                    last_reason=f'Endpoint/worker failure; server={server.poll()}, workers={codes}';break
                if time.monotonic()-last_status>=30:
                    last_status=time.monotonic();failed_health=0 if healthy() else failed_health+1
                    status(status='running',server_attempt=attempt,failed_health_checks=failed_health)
                    if failed_health>=3:last_reason='Endpoint failed three consecutive health checks';break
                time.sleep(1)
            event.update(ended_at=now(),reason='workers_finished' if complete else last_reason);write(history_path,history)
            children.cleanup()
            if complete:break
            if any(p.returncode==78 for p in workers):break
            status(status='recovering_endpoint',reason=last_reason)
        children.cleanup()
        if not complete:
            status(status='settling_operational_skips',reason=last_reason)
            if bounded('finalize_infrastructure',['--mode','finalize-infrastructure','--infrastructure-reason',last_reason],1200)!=0:
                raise RuntimeError('Could not settle unresolved cases; inspect integrity report')
        if bounded('summary',['--mode','summarize'],1200)!=0:raise RuntimeError('Summary verification failed')
        summary=read(output/'summary.json')
        if summary.get('terminal_results')!=240 or not summary.get('verification_passed'):raise RuntimeError('Incomplete terminal identity validation')
        analysis=children.spawn('independent_analysis',[sys.executable,'-B',str(root/'analyze_results.py'),'--input-dir',str(output),'--output-dir',str(root/'analysis'/key),'--allow-incomplete'],root)
        analysis.wait(timeout=300)
        if analysis.returncode:raise RuntimeError('Independent result verification failed')
        status(status='complete' if summary.get('scientific_complete') else 'complete_with_operational_skips',summary=summary,finished_at=now())
        return 0
    except OperationalStop as exc:
        children.cleanup()
        status(status='settling_operational_skips',reason=str(exc))
        try:
            code=bounded('setup_failure_finalize',['--mode','finalize-infrastructure','--infrastructure-reason',str(exc)],1200)
            if code!=0:raise RuntimeError('Operational finalization returned '+str(code))
            summary=read(output/'summary.json')
            if summary.get('terminal_results')!=240 or not summary.get('verification_passed'):
                raise RuntimeError('Operational terminal identity validation failed')
            analysis=children.spawn('setup_failure_analysis',[sys.executable,'-B',str(root/'analyze_results.py'),'--input-dir',str(output),'--output-dir',str(root/'analysis'/key),'--allow-incomplete'],root)
            analysis.wait(timeout=300)
            if analysis.returncode:raise RuntimeError('Independent operational result verification failed')
            status(status='complete_with_operational_skips',summary=summary,finished_at=now())
            return 0
        except BaseException as final_exc:
            status(status='failed',reason='Operational finalization failed: '+str(final_exc),original_error=str(exc))
            return 1
    except InterruptedError as exc:
        status(status='interrupted_checkpoints_preserved',reason=str(exc));return 75
    except BaseException as exc:
        status(status='failed',error_type=type(exc).__name__,reason=str(exc));return 1
    finally:
        children.cleanup();atexit.unregister(children.cleanup);lock.close()
if __name__=='__main__':raise SystemExit(main())

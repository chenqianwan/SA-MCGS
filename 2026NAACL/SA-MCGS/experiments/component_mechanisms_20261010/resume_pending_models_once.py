#!/usr/bin/env python3
"""One recovery of untouched Kimi/Qwen tasks; retain all prior final observations.

Dispatch adds a CPU-only step to the existing allocation. It leaves the live
Llama supervisor and all model servers alone. The original frozen runner is
used without its infrastructure-retry option. No paused model is auto-restarted.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from cluster_runner import ROOT, read, save, sha, digest, endpoints, health
from cluster_supervisor import collect_results

REMOTE=Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/component_mechanisms_20261010')
RUNTIME='/aifs4su/hansirui/vllm-dsv4-venv/bin/python3'
SLURM='/cm/shared/apps/slurm/current/bin/'
MODELS={'kimi':16,'qwen35':16}
RECOVERY=ROOT/'execution/pending_recovery'


def frozen_sources():
    manifest=read(ROOT/'runtime_manifest.json')
    expected={**manifest['source_hashes'],**manifest['local_science_files'],
              'protocol.json':manifest['protocol_sha256'],'run_scope.json':manifest['scope_sha256']}
    for name,value in expected.items():
        if sha(ROOT/name)!=value:raise RuntimeError('Frozen source changed: '+name)
    return manifest


def original_supervisor_stopped():
    with (ROOT/'execution/supervisor.lock').open('a+') as probe:
        try:fcntl.flock(probe.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return False
    return True


def dispatch():
    if ROOT!=REMOTE or os.getuid()!=1083:
        raise RuntimeError('Run only from the staged study on the cluster login node')
    manifest=frozen_sources();RECOVERY.mkdir(exist_ok=True)
    with (RECOVERY/'dispatch.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipt=RECOVERY/'launch_receipt.json'
        if receipt.exists():print(receipt.read_text());return 0
        state=read(ROOT/'execution/status.json')
        for model,wanted in [('kimi',64),('qwen35',32)]:
            rows=[w for w in state['workers'] if w['model']==model]
            if len(rows)!=wanted or any(w.get('exit_code')!=0 for w in rows):
                raise RuntimeError('Prior model workers have not all cleanly exited: '+model)
        pauses=read(ROOT/'execution/paused_models.json')
        if not set(MODELS)<=set(pauses):raise RuntimeError('Both expected model pauses must still exist')
        env={**os.environ,'SLURM_CONF':'/cm/shared/apps/slurm/var/etc/slurm/slurm.conf'}
        output=subprocess.run([SLURM+'scontrol','show','job','415747','--oneliner'],env=env,
                              capture_output=True,text=True,check=True,timeout=30).stdout
        fields=dict(w.split('=',1) for w in output.split() if '=' in w)
        if fields.get('JobState')!='RUNNING' or fields.get('NodeList')!='dgx-061':
            raise RuntimeError('Original allocation no longer available')
        command=['/usr/bin/nohup',SLURM+'srun','--jobid=415747','--overlap','--exact',
                 '--nodes=1','--ntasks=1','--cpus-per-task=64','--gres=none',
                 '--chdir='+str(ROOT),'--export=ALL',RUNTIME,'-B',str(Path(__file__).resolve()),'--supervise']
        data={'status':'starting','created_unix':time.time(),'job_id':'415747',
              'models':list(MODELS),'workers':{'kimi':64,'qwen35':32},'command':command,
              'script_sha256':sha(__file__),'runtime_manifest_sha256':digest(manifest),
              'retry_existing_final':False,'automatic_restarts':False}
        save(receipt,data)
        with (RECOVERY/'step.log').open('ab',buffering=0) as log:
            child=subprocess.Popen(command,env=env,cwd=ROOT,stdin=subprocess.DEVNULL,
                  stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        data.update(status='step_process_started',launch_pid=child.pid)
        save(receipt,data);print(json.dumps(data));return 0


def supervise():
    if os.environ.get('SLURM_JOB_ID')!='415747':raise RuntimeError('Wrong allocation')
    for key in ['PYTHONPATH','OPENAI_API_KEY','OPENAI_BASE_URL','OPENAI_API_BASE','ANTHROPIC_API_KEY']:
        os.environ.pop(key,None)
    os.environ.update(PYTHONHASHSEED='42',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',
          PYTHON_DOTENV_DISABLED='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='1',
          OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    lock=(RECOVERY/'supervisor.lock').open('a+')
    fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    frozen_sources()
    replicas=[r for r in endpoints()['replicas'] if r['model_key'] in MODELS]
    if len(replicas)!=6:raise RuntimeError('Expected the existing six Kimi/Qwen services')
    for replica in replicas:health(replica)  # Metadata GET only, no inference.
    prior={str(f.relative_to(ROOT)):sha(f) for model in MODELS
           for f in (ROOT/'results'/model).glob('*/*/final.json')}
    save(RECOVERY/'preserved_finals_sha256.json',prior)
    pause_path=ROOT/'execution/paused_models.json'
    with pause_path.with_suffix('.lock').open('a+') as pause_lock:
        fcntl.flock(pause_lock.fileno(),fcntl.LOCK_EX)
        pauses=read(pause_path)
        if not set(MODELS)<=set(pauses):raise RuntimeError('Pause state changed before recovery')
        save(RECOVERY/'paused_models_before.json',pauses)
        save(pause_path,{k:v for k,v in pauses.items() if k not in MODELS})
    state={'status':'starting_workers','started_unix':time.time(),'pid':os.getpid(),
           'job_id':os.environ.get('SLURM_JOB_ID'),'step_id':os.environ.get('SLURM_STEP_ID'),
           'models':list(MODELS),'preserved_finals':len(prior),'workers':[],
           'retry_existing_final':False,'automatic_restarts':False}
    def update(**values):
        state.update(values,updated_unix=time.time());save(RECOVERY/'status.json',state)
    interrupted=False
    def stop(*_):
        nonlocal interrupted
        interrupted=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    children=[];cache={};update()
    try:
        for replica in replicas:
            for index in range(MODELS[replica['model_key']]):
                if interrupted:break
                name=f"{replica['id']}_worker{index}"
                log=(RECOVERY/(name+'.log')).open('ab',buffering=0)
                # Deliberately omit --recover-infrastructure: both unknown finals are immutable.
                command=[RUNTIME,'-B',str(ROOT/'cluster_runner.py'),'--replica-id',replica['id'],
                         '--worker-index',str(index)]
                child=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,
                                       stderr=subprocess.STDOUT,start_new_session=True)
                children.append((child,log))
                state['workers'].append({'name':name,'model':replica['model_key'],'pid':child.pid,'exit_code':None})
                update(started_workers=len(children));time.sleep(.25)
        while not interrupted:
            for item,(child,_) in zip(state['workers'],children):item['exit_code']=child.poll()
            result=collect_results(cache)
            active=sum(w['exit_code'] is None for w in state['workers'])
            update(status='running_pending_models',running_workers=active,**result)
            if not active:break
            time.sleep(15)
        if interrupted:update(status='interrupted',ended_unix=time.time());return 130
        for name,expected in prior.items():
            if sha(ROOT/name)!=expected:raise RuntimeError('A pre-recovery final changed: '+name)
        model_counts={model:sum(r['count'] for r in result['result_groups'] if r['model']==model) for model in MODELS}
        update(recovered_model_terminal_counts=model_counts,preserved_finals_unchanged=True)
        if any(n!=400 for n in model_counts.values()) or any(w['exit_code']!=0 for w in state['workers']):
            update(status='needs_attention',reason='Pending queue paused or a recovery worker exited abnormally',
                   ended_unix=time.time());return 1
        # The original supervisor may still finish Llama. Never race its report writer.
        update(status='models_finished_waiting_for_original_supervisor')
        while not interrupted and not original_supervisor_stopped():time.sleep(15)
        if interrupted:update(status='interrupted',ended_unix=time.time());return 130
        result=collect_results(cache);update(**result)
        if result['final_results']!=1200:
            update(status='models_finished_other_work_pending',ended_unix=time.time());return 1
        summary=ROOT/'reports/summary.json'
        existing=read(summary) if summary.exists() else {}
        if (existing.get('counts',{}).get('terminal')==1200 and existing.get('quick') is False
                and existing.get('protocol_sha256')==sha(ROOT/'protocol.json')):
            update(status='complete_original_reports_preserved',ended_unix=time.time());return 0
        with (ROOT/'execution/offline_report_recovery.lock').open('a+') as report_lock:
            fcntl.flock(report_lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            update(status='generating_offline_reports')
            with (RECOVERY/'offline_analysis.log').open('ab',buffering=0) as log:
                report=subprocess.run([RUNTIME,'-B',str(ROOT/'offline_analysis.py'),'--run-root',str(ROOT),
                      '--output-dir',str(ROOT/'reports')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        update(status='complete' if report.returncode==0 else 'offline_report_failed',
               offline_report_exit_code=report.returncode,ended_unix=time.time())
        return int(report.returncode!=0)
    except BaseException as exc:
        update(status='needs_attention',error_type=type(exc).__name__,error=str(exc)[:1500],ended_unix=time.time())
        raise
    finally:
        for child,log in children:
            if child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
            log.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--supervise',action='store_true')
    cli=parser.parse_args()
    raise SystemExit(supervise() if cli.supervise else dispatch())

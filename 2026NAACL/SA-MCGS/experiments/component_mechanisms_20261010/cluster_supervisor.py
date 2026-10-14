#!/usr/bin/env python3
"""Run the 1200-task frozen queue on existing services, then produce offline reports."""
import collections
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import argparse
from cluster_runner import ROOT, ARMS, MODELS, TERMINAL, read, save, endpoints, sha


def collect_results(cache=None):
    cache={} if cache is None else cache
    groups=collections.Counter()
    usage=collections.Counter()
    rows=[]
    scope=read(ROOT/'run_scope.json')
    known=set(scope['case_uids'])
    for path in (ROOT/'results').glob('*/*/*/final.json'):
        stamp=path.stat().st_mtime_ns
        if path not in cache or cache[path][0]!=stamp:
            record=read(path)
            cache[path]=(stamp,{k:record.get(k) for k in
                  ('model','case_uid','arm','status','repeat_index','protocol_sha256','usage','elapsed_sec')})
        row=cache[path][1]
        if (row['model'] not in MODELS or row['case_uid'] not in known or row['arm'] not in ARMS
                or row['repeat_index']!=1 or row['status'] not in TERMINAL
                or row['protocol_sha256']!=sha(ROOT/'protocol.json')):
            raise ValueError('Unexpected identity or protocol in final result')
        groups[(row['model'],row['arm'],row['status'])]+=1
        for k in ('calls','prompt_tokens','completion_tokens','total_tokens','held_tokens'):
            usage[k]+=int((row['usage'] or {}).get(k,0))
        rows.append(row)
    return {'final_results':len(rows),'expected_results':1200,'remaining_results':1200-len(rows),
            'result_groups':[{'model':k[0],'arm':k[1],'status':k[2],'count':v} for k,v in sorted(groups.items())],
            'final_usage':dict(usage),'infrastructure_failures':sum(v for k,v in groups.items()
                                                                  if k[2]=='infrastructure_failure')}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--recover-infrastructure',action='store_true')
    cli=parser.parse_args()
    if os.environ.get('SLURM_JOB_ID')!='415747':
        raise ValueError('Supervisor must run inside the existing authorized allocation')
    run=ROOT/'execution';run.mkdir(exist_ok=True)
    lock=(run/'supervisor.lock').open('a+')
    fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    config=read(ROOT/'protocol.json')
    limits=config['workers_per_replica']
    if limits!={'llama':10,'kimi':16,'qwen35':16}:
        raise ValueError('Expected the authorized prior worker counts')
    replicas=endpoints()['replicas']
    state={'status':'starting','started_unix':time.time(),'pid':os.getpid(),
           'job_id':os.environ.get('SLURM_JOB_ID'),'step_id':os.environ.get('SLURM_STEP_ID'),
           'workers_per_replica':limits,'expected_results':1200,'repeats':1,
           'internal_concurrency':4,'external_api_enabled':False,'workers':[]}
    def update(**items):
        state.update(items,updated_unix=time.time());save(run/'status.json',state)
    update()
    interrupted=False
    def stop(signum,frame):
        nonlocal interrupted
        interrupted=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    children=[];cache={}
    try:
        for replica in replicas:
            for index in range(limits[replica['model_key']]):
                if interrupted:break
                name=f"{replica['id']}_worker{index}"
                log=(run/f'{name}.log').open('ab',buffering=0)
                command=[sys.executable,'-B',str(ROOT/'cluster_runner.py'),'--replica-id',replica['id'],
                         '--worker-index',str(index)]
                if cli.recover_infrastructure:command.append('--recover-infrastructure')
                child=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL,start_new_session=True)
                children.append((child,log))
                state['workers'].append({'name':name,'model':replica['model_key'],'pid':child.pid,'exit_code':None})
                update(started_workers=len(children));time.sleep(.25)
        while not interrupted:
            for entry,(child,_) in zip(state['workers'],children):entry['exit_code']=child.poll()
            result=collect_results(cache)
            running=sum(e['exit_code'] is None for e in state['workers'])
            update(status='running',running_workers=running,**result)
            if not running:
                if result['final_results']!=1200:
                    update(status='needs_attention',ended_unix=time.time(),
                           reason='Workers stopped before the frozen queue reached 1200 terminal records')
                    return 1
                update(status='generating_offline_reports')
                with (run/'offline_analysis.log').open('ab',buffering=0) as log:
                    analysis=subprocess.run([sys.executable,'-B',str(ROOT/'offline_analysis.py'),
                        '--run-root',str(ROOT),'--output-dir',str(ROOT/'reports')],
                        cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
                status=('complete' if not result['infrastructure_failures'] else 'complete_with_failures')
                if analysis.returncode:status='offline_report_failed'
                update(status=status,offline_report_exit_code=analysis.returncode,ended_unix=time.time())
                return int(analysis.returncode!=0)
            time.sleep(15)
        update(status='interrupted',ended_unix=time.time())
        return 130
    finally:
        for child,log in children:
            if child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
            log.close()


if __name__=='__main__':
    raise SystemExit(main())

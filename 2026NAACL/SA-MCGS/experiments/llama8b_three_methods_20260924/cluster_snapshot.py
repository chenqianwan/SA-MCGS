#!/usr/bin/env python3
"""Read only this experiment's receipts, Slurm state, progress and bounded logs."""
from pathlib import Path
import json
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
CODE = r'''
import collections,json,os,pathlib,subprocess,time
root=pathlib.Path('/aifs4su/hansirui_3rd/chenlong/llama8b_20260924')
env=dict(os.environ,SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf')
slurm=pathlib.Path('/cm/shared/apps/slurm/current/bin')
report={'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'read_only':True,'api_calls':0,'files':{},'logs':{}}
receipt=root/'concurrency8/resume_submission.json'
if not receipt.exists():receipt=root/'concurrency4/retry_submission.json'
if not receipt.exists():receipt=root/'concurrency4/resume_submission.json'
if not receipt.exists():receipt=root/'gpu_submission.json'
record=json.loads(receipt.read_text()) if receipt.exists() else {}
job=str(record.get('job_id',''))
if job and not job.isdigit():raise RuntimeError('Invalid receipt job ID')
report['active_job_id']=job or None
names=['gpu_submission.json','model_download_complete.json','concurrency4/resume_submission.json','concurrency4/retry_submission.json','concurrency4/release_receipt.json','concurrency4/cache_verification.json','concurrency8/resume_submission.json','concurrency8/release_receipt.json','concurrency8/cache_verification.json']
if job:
    names.extend(f'runs/{job}/{leaf}' for leaf in ('status.json','runtime.json','healthy_models.json','child_processes.json','execution_change.json','reused_preflight.json','port_preflight.json','schema_execution_amendment.json'))
for name in names:
    path=root/name
    if path.is_file():report['files'][name]=json.loads(path.read_text())
for jid in dict.fromkeys(('394900',job)):
    if not jid:continue
    r=subprocess.run([str(slurm/'scontrol'),'show','job',jid],env=env,text=True,capture_output=True)
    report[jid]={'scontrol':r.stdout or r.stderr}
    if r.returncode:
        r=subprocess.run([str(slurm/'sacct'),'-n','-P','-j',jid,'--format=JobID,State,ExitCode,NodeList,Elapsed,AllocTRES'],env=env,text=True,capture_output=True)
        report[jid]['sacct']=r.stdout or r.stderr
if job:
    for path in list((root/f'runs/{job}').glob('*.log'))+[root/f'logs/experiment-{job}.err']:
        if path.is_file():
            with path.open('rb') as stream:
                stream.seek(max(0,path.stat().st_size-4000))
                report['logs'][str(path.relative_to(root))]=stream.read().decode('utf-8',errors='replace')
counts=collections.Counter()
for path in (root/'results/llama80_three_methods/results').glob('*.json'):
    result=json.loads(path.read_text())
    counts[result.get('cost_audit_method','unknown')+':'+result.get('completion_status','unknown')]+=1
report['result_counts']=dict(counts)
out=root/'results/llama80_three_methods'
for name in ('summary.json','portable_preflight.json','tokenization_report.json'):
    path=out/name
    if path.is_file():report['files'][str(path.relative_to(root))]={k:v for k,v in json.loads(path.read_text()).items() if k not in ('rows','case_uids')}
print(json.dumps(report,ensure_ascii=False))
'''

if __name__ == '__main__':
    command=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','Group3_slogin','/usr/bin/python3 -B -c '+shlex.quote(CODE)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=90)
    if result.returncode:
        (HERE/'cluster_snapshot_last_error.txt').write_text(result.stderr)
        raise SystemExit(result.stderr.strip() or f'SSH exited {result.returncode}; snapshot not refreshed')
    report=json.loads(result.stdout)
    (HERE/'cluster_live_status.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    job=report['active_job_id']
    print(json.dumps({'checked_at':report['checked_at'],'active_job_id':job,'slurm':report.get(job),'download_slurm':report.get('394900'),'state':report['files'].get(f'runs/{job}/status.json'),'runtime':report['files'].get(f'runs/{job}/runtime.json'),'result_counts':report['result_counts'],'logs':report['logs']},ensure_ascii=False,indent=2))

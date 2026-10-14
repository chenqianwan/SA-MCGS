#!/usr/bin/env python3
"""Read our existing Slurm jobs and bounded logs; never submit or infer."""
from pathlib import Path
import json
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
CODE = r'''
import collections,json,os,pathlib,subprocess,time
root=pathlib.Path('/aifs4su/hansirui_3rd/chenlong/q72awq_20260924')
env=dict(os.environ,SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf')
report={'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'read_only':True,'api_calls':0,'files':{},'logs':{}}
resume_receipt=root/'resume_submission_20260924.json'
active_job=str(json.loads(resume_receipt.read_text())['job_id']) if resume_receipt.exists() else '394281'
if not active_job.isdigit():raise RuntimeError('Invalid job ID in continuation receipt')
report['active_job_id']=active_job
names=['gpu_submission.json','resume_submission_20260924.json','cpu_preflight_submission.json','results/lea_qwen80/portable_preflight.json','results/lea_qwen80/tokenization_report.json','results/lea_qwen80/budget_status.json','validation/tokenizer_cpu/results/tokenization_report.json']
for job in dict.fromkeys(('394281',active_job)):
    names.extend(f'runs/{job}/{leaf}' for leaf in ('status.json','runtime.json','healthy_models.json','resume_audit.json','child_processes.json'))
for name in names:
    path=root/name
    if path.is_file():report['files'][name]=json.loads(path.read_text())
for job in dict.fromkeys(('394281','394282',active_job)):
    r=subprocess.run(['/cm/shared/apps/slurm/current/bin/scontrol','show','job',job],env=env,text=True,capture_output=True)
    report[job]={'scontrol':r.stdout or r.stderr}
    if r.returncode:
        r=subprocess.run(['/cm/shared/apps/slurm/current/bin/sacct','-n','-P','-j',job,'--format=JobID,State,ExitCode,NodeList,Elapsed,AllocTRES'],env=env,text=True,capture_output=True)
        report[job]['sacct']=r.stdout or r.stderr
for path in list((root/f'runs/{active_job}').glob('*.log'))+[root/f'logs/lea-{active_job}.err']:
    if path.is_file():
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-5000))
            report['logs'][str(path.relative_to(root))]=stream.read().decode('utf-8',errors='replace')
counts=collections.Counter()
for path in (root/'results/lea_qwen80/results').glob('*__lea.json'):
    counts[json.loads(path.read_text()).get('completion_status','unknown')]+=1
report['result_counts']=dict(counts)
report['workers']=[json.loads(path.read_text()) for path in (root/'results/lea_qwen80/worker_status').glob('*.json')]
print(json.dumps(report,ensure_ascii=False))
'''

if __name__ == "__main__":
    command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15", "Group3_slogin", "/usr/bin/python3 -B -c " + shlex.quote(CODE)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if result.returncode:
        (HERE / "cluster_snapshot_last_error.txt").write_text(result.stderr)
        raise SystemExit(result.stderr.strip() or f"SSH exited with code {result.returncode}; previous snapshot was not refreshed")
    report = json.loads(result.stdout)
    (HERE / "cluster_live_status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    tokenization = report["files"].get("results/lea_qwen80/tokenization_report.json", {})
    job = report["active_job_id"]
    print(json.dumps({"checked_at": report["checked_at"], "active_job_id": job, "slurm": report[job], "state": report["files"].get(f"runs/{job}/status.json"), "runtime": report["files"].get(f"runs/{job}/runtime.json"), "tokenizer_passed": tokenization.get("passed"), "max_reserved_context": tokenization.get("max_prompt_plus_output_tokens"), "result_counts": report["result_counts"], "logs": report["logs"]}, ensure_ascii=False, indent=2))

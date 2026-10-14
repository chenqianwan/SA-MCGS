#!/usr/bin/env python3
"""Stage only continuation orchestration, then submit once with an audit receipt."""
from pathlib import Path
import ast
import base64
import hashlib
import json
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
CODE = r'''
import base64,collections,fcntl,hashlib,json,os,pathlib,subprocess,sys,time
root=pathlib.Path('/aifs4su/hansirui_3rd/chenlong/q72awq_20260924')
if os.getuid()!=1083 or root.resolve()!=root or root.stat().st_uid!=os.getuid():
    raise SystemExit('Unexpected account or deployment path')
os.umask(0o077)
env=dict(os.environ,SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf')
slurm=pathlib.Path('/cm/shared/apps/slurm/current/bin')
payload=json.load(sys.stdin)
allowed={'run_awq_lea_resume.py','run_awq_lea_resume.sbatch'}
if set(payload)!=allowed:
    raise SystemExit('Unexpected continuation files')
with (root/'gpu_submission.lock').open('a+') as submission_lock:
    fcntl.flock(submission_lock,fcntl.LOCK_EX)
    receipt=root/'resume_submission_20260924.json'
    if receipt.exists():
        record=json.loads(receipt.read_text())
    else:
        if (root/'resume_submission_intent_20260924.json').exists():
            raise SystemExit('Unresolved prior continuation submission; inspect our queue before retrying')
        queue=subprocess.run([str(slurm/'squeue'),'-h','-u','hansirui_3rd','-n','chenlong_qwen72_lea80,chenlong_qwen72_resume,chenlong_qwen72_lea80_resume','-o','%i %j %T'],env=env,text=True,capture_output=True,check=True)
        if queue.stdout.strip():
            raise SystemExit('An existing Qwen job must be reconciled before submitting: '+queue.stdout)
        with (root/'service_and_experiment.lock').open('a+') as service_lock:
            fcntl.flock(service_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            original=json.loads((root/'gpu_staging_manifest.json').read_text())
            for name,expected in original['files'].items():
                path=root/name
                if path.stat().st_size!=expected['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=expected['sha256']:
                    raise SystemExit('Original deployment changed: '+name)
            output=root/'results/lea_qwen80'
            if (output/'budget_halt.json').exists():
                raise SystemExit('Accounting or provider halt requires reconciliation')
            guards={
                'frozen_runner_protocol.json':'2ddf5a71d7a6fb2b3ef7d2b8b4b82433c1d207287c86c3f0358ca724682a2be7',
                'frozen_pricing.json':'dafa7da74b2bfe88903e850bc995503628f0bf2bc5d8d3c55205f0bae538aa08',
                'deployment_provenance.json':'f5be09a9d1e9d248be5f66a1830b878934def4788a083f39d559bdb3a4fbd753'}
            for name,expected in guards.items():
                if hashlib.sha256((output/name).read_bytes()).hexdigest()!=expected:
                    raise SystemExit('Frozen runtime configuration changed: '+name)
            counts=dict(collections.Counter(json.loads(path.read_text()).get('completion_status') for path in (output/'results').glob('*__lea.json')))
            if counts!={'complete':26}:
                raise SystemExit('Checkpoint count differs from reviewed continuation: '+str(counts))
            caches=[]
            for path in sorted((output/'call_cache/qwen2.5-72b').glob('*/responses.jsonl')):
                data=path.read_bytes()
                rows=[json.loads(line) for line in data.splitlines()]
                if any(row.get('call_index')!=i+1 or not isinstance(row.get('usage',{}).get('completion_tokens'),int) or not isinstance(row.get('usage',{}).get('prompt_tokens'),int) for i,row in enumerate(rows)):
                    raise SystemExit('Non-contiguous or unauditable cache: '+path.parent.name)
                caches.append({'case_id':path.parent.name,'records':len(rows),'sha256':hashlib.sha256(data).hexdigest()})
            if sum(item['records'] for item in caches)!=721:
                raise SystemExit('Checkpoint response count differs from reviewed continuation')
            staged={}
            for name,item in payload.items():
                data=base64.b64decode(item['content'],validate=True)
                if hashlib.sha256(data).hexdigest()!=item['sha256']:
                    raise SystemExit('Continuation upload checksum mismatch')
                path=root/name
                if path.resolve()!=path:
                    raise SystemExit('Unexpected symbolic link in continuation path')
                if path.exists():
                    if path.read_bytes()!=data:
                        raise SystemExit('Different continuation file is already staged: '+name)
                else:
                    with path.open('xb') as stream:stream.write(data)
                staged[name]={'sha256':item['sha256'],'bytes':len(data)}
            audit={'verified_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'source_job_id':'394281','result_counts':counts,'cached_responses':721,'cache_files':caches,'frozen_configuration_sha256':guards,'staged_files':staged,'original_deployment_unchanged':True,'old_zero_cost_unsettled_reservations_preserved':4}
            (root/'resume_staging_audit_20260924.json').write_text(json.dumps(audit,indent=2)+'\n')
        # Release the service lock before sbatch; the new coordinator may start immediately.
        (root/'resume_submission_intent_20260924.json').write_text(json.dumps({'created_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'job_name':'chenlong_qwen72_lea80_resume'})+'\n')
        result=subprocess.run([str(slurm/'sbatch'),'--parsable','--comment=chenlong_q72awq_resume_20260924',str(root/'run_awq_lea_resume.sbatch')],env=env,text=True,capture_output=True)
        if result.returncode:
            (root/'resume_submission_failure_20260924.json').write_text(json.dumps({'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})+'\n')
            raise SystemExit(result.stderr)
        jobid=result.stdout.strip().split(';')[0]
        if not jobid.isdigit():
            raise SystemExit('Ambiguous sbatch response; inspect queue before retrying: '+result.stdout)
        record={'job_id':jobid,'submitted_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'source_job_id':'394281','time_limit':'12:00:00','gpu_count':1,'cpus':16,'memory':'128G','completed_at_submission':26,'remaining_at_submission':54,'cached_responses_reused':721,'scientific_protocol_unchanged':True,'external_api_spend_usd':0,'staged_files':staged,'sbatch_stdout':result.stdout,'sbatch_stderr':result.stderr}
        receipt.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)
    subprocess.run([str(slurm/'scontrol'),'show','job',record['job_id']],env=env,check=True)
'''


if __name__ == "__main__":
    ast.parse((HERE / "run_awq_lea_resume.py").read_text())
    subprocess.run(["bash", "-n", str(HERE / "run_awq_lea_resume.sbatch")], check=True)
    payload = {}
    for name in ("run_awq_lea_resume.py", "run_awq_lea_resume.sbatch"):
        data = (HERE / name).read_bytes()
        payload[name] = {"sha256": hashlib.sha256(data).hexdigest(), "content": base64.b64encode(data).decode()}
    command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15", "Group3_slogin", "/usr/bin/python3 -B -c " + shlex.quote(CODE)]
    result = subprocess.run(command, input=json.dumps(payload), text=True, capture_output=True, timeout=120)
    output = result.stdout + result.stderr
    (HERE / "resume_submission_receipt_20260924.txt").write_text(output)
    print(output, end="")
    if result.returncode == 0:
        record = json.loads(result.stdout.splitlines()[0])
        (HERE / "resume_submission_20260924.json").write_text(json.dumps(record, indent=2) + "\n")
    raise SystemExit(result.returncode)

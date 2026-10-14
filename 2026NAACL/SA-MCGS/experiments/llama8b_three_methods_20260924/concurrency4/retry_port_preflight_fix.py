#!/usr/bin/env python3
"""Stage the reviewed execution change and submit a held, dependent successor.

Both previous allocations must be stopped; preserved result and cache hashes are checked.
"""
from pathlib import Path
import hashlib
import io
import json
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent / 'port_reuse'
ROOT = '/aifs4su/hansirui_3rd/chenlong/llama8b_20260924'
names = ['run_llama_experiment.py', 'run_llama_experiment.sbatch']
manifest = {'files': {'concurrency4/port_reuse/' + n: {'bytes': (HERE/n).stat().st_size,
    'sha256': hashlib.sha256((HERE/n).read_bytes()).hexdigest()} for n in names}}
payload = io.BytesIO()
with tarfile.open(fileobj=payload, mode='w:gz') as archive:
    for n in names:
        archive.add(HERE/n, arcname='concurrency4/port_reuse/' + n, recursive=False)
    content=(json.dumps(manifest,indent=2)+'\n').encode()
    info=tarfile.TarInfo('concurrency4/port_reuse/staging_manifest.json');info.size=len(content);info.mode=0o600
    archive.addfile(info,io.BytesIO(content))

CODE = r'''
import fcntl,hashlib,io,json,os,pathlib,subprocess,sys,tarfile,time
root=pathlib.Path('/aifs4su/hansirui_3rd/chenlong/llama8b_20260924');v=root/'concurrency4'; fixed=v/'port_reuse'
if os.getuid()!=1083 or root.resolve()!=root or root.stat().st_uid!=os.getuid():raise SystemExit('Unexpected root/account')
os.umask(0o077)
archive=tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()),mode='r:gz')
for member in archive.getmembers():
    rel=pathlib.PurePosixPath(member.name)
    if not member.isfile() or rel.is_absolute() or '..' in rel.parts or rel.parts[0]!='concurrency4':raise SystemExit('Unsafe archive')
    path=root.joinpath(*rel.parts)
    if path.resolve()!=path:raise SystemExit('Symlink in deployment path')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    data=archive.extractfile(member).read()
    if path.exists():
        if path.read_bytes()!=data:raise SystemExit('Different version already staged: '+member.name)
    else:path.write_bytes(data)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for manifest_path in (root/'gpu_staging_manifest.json',v/'staging_manifest.json',fixed/'staging_manifest.json'):
    for name,expected in json.loads(manifest_path.read_text())['files'].items():
        p=root/name
        if p.stat().st_size!=expected['bytes'] or sha(p)!=expected['sha256']:raise SystemExit('Staged hash mismatch: '+name)
proof=json.loads((v/'runner_compatibility_verification.json').read_text())
if not proof.get('passed') or not proof.get('protocol_equal'):raise SystemExit('Migration validation failed')
env=dict(os.environ,SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf');slurm=pathlib.Path('/cm/shared/apps/slurm/current/bin')
with (v/'submission.lock').open('a+') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    receipt=v/'retry_submission.json'
    if receipt.exists():record=json.loads(receipt.read_text())
    else:
        stopped=read_status=json.loads((root/'runs/395039/status.json').read_text())
        if stopped.get('error')!='[Errno 98] Address already in use' or (root/'runs/395039/server_command.json').exists():raise SystemExit('Unexpected original restart state')
        for previous in ('394926','395039'):
            result=subprocess.run([str(slurm/'sacct'),'-n','-P','-j',previous,'--format=JobIDRaw,State'],env=env,text=True,capture_output=True,check=True)
            rows=[line.split('|') for line in result.stdout.splitlines() if line.split('|')[0]==previous]
            if len(rows)!=1 or rows[0][1].split()[0] not in {'FAILED','CANCELLED','COMPLETED'}:raise SystemExit('Previous allocation has not stopped')
        handoff=json.loads((v/'handoff_snapshot.json').read_text())
        for name,expected in handoff['completed_result_sha256'].items():
            if sha(root/name)!=expected:raise SystemExit('Completed result changed')
        for name,expected in handoff['cache_files'].items():
            if sha(root/name)!=expected['sha256']:raise SystemExit('Cache changed during preflight-only restart')
        command=[str(slurm/'sbatch'),'--parsable','--comment=chenlong_llama8b_c4_portreuse',str(fixed/'run_llama_experiment.sbatch')]
        check=subprocess.run([*command[:-1],'--test-only',command[-1]],env=env,text=True,capture_output=True)
        if check.returncode:raise SystemExit('Slurm rejected preparation: '+check.stderr)
        intent=v/'retry_submission_intent.json'
        if intent.exists():raise SystemExit('Unresolved prior intent; inspect queue before any retry')
        intent.write_text(json.dumps({'at':time.time(),'argv':command})+'\n')
        result=subprocess.run(command,env=env,text=True,capture_output=True)
        if result.returncode:
            (v/'retry_submission_failure.json').write_text(json.dumps({'code':result.returncode,'out':result.stdout,'err':result.stderr})+'\n')
            raise SystemExit(result.stderr)
        job=result.stdout.strip().split(';')[0]
        if not job.isdigit():raise SystemExit('Unrecognized sbatch response; inspect queue')
        record={'job_id':job,'previous_job_id':'395039','original_job_id':'394926','submitted_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'reason':'Resume preflight binds with SO_REUSEADDR to match Uvicorn and tolerate drained TCP connections; real listeners still reject binding. No scientific or concurrency change.','node':'dgx-100','nodes':1,'gpu_count':1,'time_limit':'5-00:00:00','case_concurrency':4,'vllm_max_num_seqs':16,'base_protocol_sha256':proof['protocol_canonical_sha256'],'preserved_terminal_results':len(handoff['completed_result_sha256']),'staging_manifest_sha256':sha(fixed/'staging_manifest.json'),'sbatch_argv':command}
        receipt.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)
    subprocess.run([str(slurm/'scontrol'),'show','job',record['job_id']],env=env,check=True)
'''
command=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','Group3_slogin','/usr/bin/python3 -B -c '+shlex.quote(CODE)]
result=subprocess.run(command,input=payload.getvalue(),capture_output=True,timeout=120)
output=result.stdout.decode()+result.stderr.decode()
(HERE/'retry_submission_output.txt').write_text(output)
print(output,end='')
if not result.returncode:(HERE/'staging_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
raise SystemExit(result.returncode)

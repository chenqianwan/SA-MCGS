#!/usr/bin/env python3
"""Idempotently stage two pinned checkpoints and submit CPU-only preparation."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
from cluster_io import HERE, REMOTE, remote

def main():
    named=[(HERE/'download_models.py','download_models.py')]
    for key,src in [('kimi','kimi'),('qwen35','qwen')]:
        named += [(HERE/'configs'/f'{key}.json',f'configs/{key}.json'),
                  (HERE/'deployment_audit'/f'{key}_official.json',f'deployment_audit/{key}_official.json')]
        named += [(p,f'models/{key}/{p.name}') for p in (HERE/'deployment_audit'/src).iterdir() if p.is_file()]
        batch=f'''#!/bin/bash
#SBATCH --job-name=chenlong_{key}_prepare
#SBATCH --partition=debug
#SBATCH --qos=llm
#SBATCH --account=hansirui
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=08:00:00
#SBATCH --chdir={REMOTE}
#SBATCH --output={REMOTE}/logs/{key}-prepare-%j.out
#SBATCH --error={REMOTE}/logs/{key}-prepare-%j.err
#SBATCH --export=NONE
set -euo pipefail
umask 077
export PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHON_DOTENV_DISABLED=1
export TMPDIR={REMOTE}/prep/tmp
exec /usr/bin/python3 -B {REMOTE}/download_models.py --root {REMOTE} --model {key}
'''
        p=HERE/f'{key}_prepare.sbatch';p.write_text(batch);named.append((p,p.name))
    manifest={n:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p,n in named}
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
        for p,n in named: archive.add(p,arcname=n,recursive=False)
        data=(json.dumps(manifest,indent=2)+'\n').encode();info=tarfile.TarInfo('prep_staging_manifest.json');info.size=len(data);archive.addfile(info,io.BytesIO(data))
    code=r'''import os, pathlib, io, tarfile, sys, json, hashlib, subprocess, fcntl, time
root=pathlib.Path('''+repr(REMOTE)+r''')
if os.getuid()!=1083 or root.resolve()!=root: raise RuntimeError('Wrong account/root')
os.umask(0o077)
root.mkdir(exist_ok=True)
for n in ['logs','prep/tmp','runs','locks','t','receipts']:
 p=root/n;p.mkdir(parents=True,exist_ok=True)
 if p.resolve()!=p or p.stat().st_uid!=os.getuid(): raise RuntimeError('Unsafe directory')
archive=tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()),mode='r:gz')
for member in archive.getmembers():
 rel=pathlib.PurePosixPath(member.name)
 if not member.isfile() or rel.is_absolute() or '..' in rel.parts: raise RuntimeError('Unsafe member')
 p=root.joinpath(*rel.parts);p.parent.mkdir(parents=True,exist_ok=True)
 if p.resolve()!=p: raise RuntimeError('Symlink target')
 data=archive.extractfile(member).read()
 if p.exists():
  if p.read_bytes()!=data: raise RuntimeError('Different staged file '+member.name)
 else:
  with p.open('xb') as f: f.write(data)
manifest=json.loads((root/'prep_staging_manifest.json').read_text())
for name,expected in manifest.items():
 p=root/name
 if p.stat().st_size!=expected['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=expected['sha256']: raise RuntimeError('Staged mismatch')
env=dict(os.environ,SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf')
reports={}
with (root/'locks/prep_submit.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 for key in ['kimi','qwen35']:
  receipt=root/'receipts'/f'{key}_prep.json';intent=root/'receipts'/f'{key}_prep_intent.json'
  if receipt.exists(): reports[key]=json.loads(receipt.read_text());continue
  if intent.exists(): raise RuntimeError('Unresolved submission intent; inspect queue, do not duplicate')
  cmd=['/cm/shared/apps/slurm/current/bin/sbatch','--parsable','--comment=chenlong_kq35_20260924',str(root/f'{key}_prepare.sbatch')]
  check=subprocess.run([*cmd[:-1],'--test-only',cmd[-1]],env=env,text=True,capture_output=True)
  if check.returncode: raise RuntimeError(check.stderr)
  intent.write_text(json.dumps({'at':time.time(),'argv':cmd})+'\n')
  r=subprocess.run(cmd,env=env,text=True,capture_output=True)
  if r.returncode: raise RuntimeError('sbatch rejected '+r.stderr)
  jid=r.stdout.strip().split(';')[0]
  if not jid.isdigit(): raise RuntimeError('Ambiguous submission '+r.stdout)
  result={'job_id':jid,'model':key,'phase':'prepare','gpu_count':0,'submitted_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'sbatch_stdout':r.stdout,'sbatch_stderr':r.stderr}
  receipt.write_text(json.dumps(result,indent=2)+'\n');reports[key]=result
print(json.dumps(reports))
'''
    result=json.loads(remote(code,buffer.getvalue(),timeout=180))
    (HERE/'prep_submission_receipts.json').write_text(json.dumps(result,indent=2)+'\n')
    (HERE/'prep_staging_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()

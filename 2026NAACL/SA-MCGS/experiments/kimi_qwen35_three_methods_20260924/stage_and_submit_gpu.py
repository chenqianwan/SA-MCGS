#!/usr/bin/env python3
"""Freeze, stage, and optionally submit the two personal single-GPU experiments.

Default: local plan only. --stage-only stages without sbatch; --submit stages and
submits. Run either mutating mode only after supervisor/runner/analyzer freeze.
An unresolved durable submission intent requires inspection, never blind retry.
"""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile

from cluster_io import HERE, REMOTE, remote

PREP_JOBS = {'kimi': '395439', 'qwen35': '395441'}
EXPECTED_REMOTE = '/aifs4su/hansirui_3rd/chenlong/kq35_20260924'

REMOTE_CODE = r'''
import fcntl,hashlib,io,json,os,pathlib,re,subprocess,sys,tarfile,time
root=pathlib.Path(REMOTE_ROOT)
allowed=pathlib.Path('/aifs4su/hansirui_3rd/chenlong')
if os.getuid()!=1083 or root.resolve()!=root or allowed not in root.parents:
 raise RuntimeError('Wrong account or unsafe experiment root')
os.umask(0o077)
def validate_path(path,kind=None):
 if path.resolve()!=path or (path!=root and root not in path.parents):
  raise RuntimeError('Unsafe path '+str(path))
 for parent in (path,*path.parents):
  if parent==allowed or allowed in parent.parents:
   if parent.exists() and parent.stat().st_uid!=os.getuid():
    raise RuntimeError('Unexpected owner '+str(parent))
   if parent!=path and parent.exists() and not parent.is_dir():
    raise RuntimeError('Non-directory ancestor '+str(parent))
 if path.exists() and kind=='file' and not path.is_file():raise RuntimeError('Not a regular file '+str(path))
 if path.exists() and kind=='dir' and not path.is_dir():raise RuntimeError('Not a directory '+str(path))
def mkdir(path):
 validate_path(path,'dir');path.mkdir(mode=0o700,parents=True,exist_ok=True);validate_path(path,'dir')
def sync_dir(path):
 fd=os.open(str(path),os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def create_durable(path,data):
 validate_path(path,'file');mkdir(path.parent)
 fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as output:
  output.write(data);output.flush();os.fsync(output.fileno())
 sync_dir(path.parent)
def json_bytes(data):return (json.dumps(data,sort_keys=True,indent=2)+'\n').encode()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
validate_path(root,'dir')
if not root.is_dir():raise RuntimeError('Preparation root does not exist')
mkdir(root/'locks');mkdir(root/'receipts')
lock_path=root/'locks/gpu_stage_submit.lock'
validate_path(lock_path,'file')
lock_fd=os.open(str(lock_path),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
with os.fdopen(lock_fd,'a+b') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 archive=tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()),mode='r:gz')
 payload={}
 for member in archive.getmembers():
  rel=pathlib.PurePosixPath(member.name)
  if not member.isfile() or rel.is_absolute() or '..' in rel.parts or member.name in payload:
   raise RuntimeError('Unsafe or duplicate archive member')
  payload[member.name]=archive.extractfile(member).read()
 manifest_name='gpu_staging_manifest.json'
 manifest_data=payload.pop(manifest_name)
 manifest=json.loads(manifest_data)
 manifest_sha=hashlib.sha256(manifest_data).hexdigest()
 if manifest_sha!=MANIFEST_SHA256 or manifest.get('remote_root')!=str(root) or manifest.get('prep_jobs')!=PREP_JOBS:
  raise RuntimeError('Manifest identity mismatch')
 files=manifest['files']
 if set(files)!=set(payload):raise RuntimeError('Archive does not exactly match manifest')
 # Complete prevalidation occurs before any staged executable/config is written.
 for name,expected in files.items():
  data=payload[name]
  if len(data)!=expected['bytes'] or hashlib.sha256(data).hexdigest()!=expected['sha256']:
   raise RuntimeError('Corrupt payload '+name)
  target=root/name;validate_path(target,'file')
  if target.exists() and target.read_bytes()!=data:raise RuntimeError('Different immutable staged file '+name)
 target_manifest=root/manifest_name;validate_path(target_manifest,'file')
 if target_manifest.exists() and target_manifest.read_bytes()!=manifest_data:
  raise RuntimeError('Different immutable GPU staging manifest')
 for key in PREP_JOBS:
  prep_path=root/'receipts'/f'{key}_prep.json';validate_path(prep_path,'file')
  prep=json.loads(prep_path.read_text())
  if str(prep.get('job_id'))!=PREP_JOBS[key] or prep.get('model')!=key or prep.get('phase')!='prepare':
   raise RuntimeError('Preparation receipt does not match dependency '+key)
 for name,data in payload.items():
  target=root/name
  if not target.exists():create_durable(target,data)
 if not target_manifest.exists():create_durable(target_manifest,manifest_data)
 for name,expected in files.items():
  target=root/name
  if target.stat().st_size!=expected['bytes'] or digest(target)!=expected['sha256']:
   raise RuntimeError('Post-stage checksum mismatch '+name)
 for name in ['logs','runs','runtime','t']:mkdir(root/name)
 reports={}
 if SUBMIT:
  env=dict(os.environ,SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf')
  for key in MODELS:
   receipt=root/'receipts'/f'{key}_gpu.json';intent=root/'receipts'/f'{key}_gpu_intent.json'
   validate_path(receipt,'file');validate_path(intent,'file')
   batch=root/f'{key}_gpu.sbatch'
   if receipt.exists():
    previous=json.loads(receipt.read_text())
    if (previous.get('gpu_staging_manifest_sha256')!=manifest_sha
        or previous.get('model')!=key or previous.get('prep_job_id')!=PREP_JOBS[key]
        or not str(previous.get('job_id','')).isdigit()):
     raise RuntimeError('Existing GPU receipt identity mismatch '+key)
    reports[key]=previous;continue
   if intent.exists():
    raise RuntimeError('Unresolved '+key+' GPU submission intent: inspect Slurm and reconcile the exact job; do not resubmit.')
   command=['/cm/shared/apps/slurm/current/bin/sbatch','--parsable',
            '--comment=chenlong_kq35_20260924_'+key,str(batch)]
   test=subprocess.run([*command[:-1],'--test-only',command[-1]],env=env,text=True,capture_output=True,timeout=60)
   if test.returncode:raise RuntimeError('sbatch test rejected '+key+': '+test.stderr)
   intent_data={'model':key,'prep_job_id':PREP_JOBS[key],'argv':command,
                'gpu_staging_manifest_sha256':manifest_sha,'batch_sha256':digest(batch),
                'created_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'created_epoch':time.time(),
                'state':'submission_intent','test_stdout':test.stdout,'test_stderr':test.stderr}
   create_durable(intent,json_bytes(intent_data))
   try:
    submitted=subprocess.run(command,env=env,text=True,capture_output=True,timeout=60)
   except subprocess.TimeoutExpired:
    raise RuntimeError('Submission timed out after durable intent for '+key+'; job may exist. Do not retry sbatch.')
   match=re.fullmatch(r'([0-9]+)(?:;[^\s;]+)?',submitted.stdout.strip())
   if submitted.returncode or not match:
    failure={'model':key,'exit_code':submitted.returncode,'stdout':submitted.stdout,
             'stderr':submitted.stderr,'recorded_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    create_durable(root/'receipts'/f'{key}_gpu_submission_failure.json',json_bytes(failure))
    raise RuntimeError('GPU submission rejected/ambiguous for '+key+'; durable intent preserved for inspection.')
   result={'job_id':match.group(1),'model':key,'phase':'experiment','prep_job_id':PREP_JOBS[key],
           'dependency':'afterok:'+PREP_JOBS[key],'nodes':1,'gpu_count':1,'cpus':16,'memory':'128G',
           'time_limit':'5-00:00:00','excluded_nodes':['dgx-127'],'pinned_node':None,
           'same_node_model_and_workers':True,'gpu_staging_manifest_sha256':manifest_sha,
           'batch_sha256':digest(batch),'submitted_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
           'sbatch_stdout':submitted.stdout,'sbatch_stderr':submitted.stderr}
   create_durable(receipt,json_bytes(result));reports[key]=result
 print(json.dumps({'remote_root':str(root),'staged':True,'submitted':SUBMIT,
                   'gpu_staging_manifest_sha256':manifest_sha,'file_count':len(files),'receipts':reports}))
'''


def canonical(data):
    return (json.dumps(data,sort_keys=True,indent=2)+'\n').encode()


def freeze_local(path,data):
    if path.is_symlink():raise RuntimeError('Refuse symlinked local receipt/manifest')
    if path.exists():
        if path.read_bytes()!=data:raise RuntimeError('Different immutable local file: '+str(path))
        return
    with path.open('xb') as output:
        output.write(data);output.flush();os.fsync(output.fileno())
    fd=os.open(str(path.parent),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def collect_files():
    named={}
    for directory in ('runner','configs'):
        base=HERE/directory
        if not base.is_dir():raise RuntimeError('Missing frozen directory '+directory)
        for path in sorted(base.rglob('*')):
            if '__pycache__' in path.parts or path.suffix in ('.pyc','.pyo'):continue
            if path.is_symlink():raise RuntimeError('Refuse symlinked staged source '+str(path))
            if path.is_file():named[path.relative_to(HERE).as_posix()]=path
    for name in ('supervisor.py','analyze_results.py','kimi_gpu.sbatch','qwen35_gpu.sbatch',
                 'deployment_audit/kimi_official.json','deployment_audit/qwen35_official.json'):
        path=HERE/name
        if not path.is_file() or path.is_symlink():raise RuntimeError('Missing/unsafe frozen file '+name)
        named[name]=path
    if 'runner/generic_launcher.py' not in named:raise RuntimeError('Missing frozen generic runner')
    content={name:path.read_bytes() for name,path in sorted(named.items())}
    for name,path in named.items():
        if path.read_bytes()!=content[name]:raise RuntimeError('Source changed while collecting '+name)
    for key in PREP_JOBS:
        config=json.loads(content[f'configs/{key}.json'])
        metadata=json.loads(content[f'deployment_audit/{key}_official.json'])
        if (config['checkpoint_repository']!=metadata['id'] or config['checkpoint_revision']!=metadata['sha']):
            raise RuntimeError('Checkpoint identity mismatch '+key)
        batch=content[f'{key}_gpu.sbatch'].decode()
        requirements=['#SBATCH --nodes=1','#SBATCH --gres=gpu:1','#SBATCH --cpus-per-task=16',
                      '#SBATCH --mem=128G','#SBATCH --time=5-00:00:00','#SBATCH --exclude=dgx-127',
                      '#SBATCH --dependency=afterok:'+PREP_JOBS[key]]
        if not all(x in batch.splitlines() for x in requirements) or '#SBATCH --nodelist' in batch:
            raise RuntimeError('Unexpected GPU allocation contract '+key)
    return content


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--stage-only',action='store_true')
    mode.add_argument('--submit',action='store_true')
    parser.add_argument('--models',nargs='+',choices=tuple(PREP_JOBS),default=list(PREP_JOBS))
    parser.add_argument('--syntax-only',action='store_true')
    args=parser.parse_args()
    ast.parse(REMOTE_CODE)
    if args.syntax_only:
        print(json.dumps({'remote_python_syntax_valid':True,'network_calls':0}));return
    if REMOTE!=EXPECTED_REMOTE:raise RuntimeError('Unexpected cluster_io root')
    models=list(dict.fromkeys(args.models))
    content=collect_files()
    manifest={'schema_version':1,'remote_root':REMOTE,'prep_jobs':PREP_JOBS,
              'files':{name:{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)} for name,data in content.items()}}
    manifest_data=canonical(manifest);manifest_sha=hashlib.sha256(manifest_data).hexdigest()
    if not args.stage_only and not args.submit:
        print(json.dumps({'action':'local_plan_only','network_calls':0,'models':models,
                          'file_count':len(content),'payload_bytes':sum(map(len,content.values())),
                          'manifest_sha256':manifest_sha,'prep_jobs':PREP_JOBS},indent=2));return
    freeze_local(HERE/'gpu_staging_manifest.json',manifest_data)
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
        for name,data in [*content.items(),('gpu_staging_manifest.json',manifest_data)]:
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600;info.mtime=0
            archive.addfile(info,io.BytesIO(data))
    prefix=('REMOTE_ROOT='+repr(REMOTE)+'\nPREP_JOBS='+repr(PREP_JOBS)+'\nMODELS='+repr(models)+
            '\nMANIFEST_SHA256='+repr(manifest_sha)+'\nSUBMIT='+repr(args.submit)+'\n')
    result=json.loads(remote(prefix+REMOTE_CODE,buffer.getvalue(),timeout=300))
    for key,receipt in result['receipts'].items():
        freeze_local(HERE/f'{key}_gpu_submission_receipt.json',canonical(receipt))
    output=HERE/('gpu_submission_receipts.json' if args.submit else 'gpu_stage_receipt.json')
    output.write_bytes(canonical(result))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

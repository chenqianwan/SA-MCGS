#!/usr/bin/env python3
"""Gracefully stop our original job, snapshot checkpoints, release successor."""
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
CODE = r'''
import collections,fcntl,hashlib,json,os,pathlib,subprocess,time
root=pathlib.Path('/aifs4su/hansirui_3rd/chenlong/llama8b_20260924');v=root/'concurrency8'
if os.getuid()!=1083 or root.resolve()!=root or root.stat().st_uid!=os.getuid():raise SystemExit('Unexpected root/account')
os.umask(0o077)
env=dict(os.environ,SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf');slurm=pathlib.Path('/cm/shared/apps/slurm/current/bin')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,a):
    tmp=p.with_name('.'+p.name+'.tmp');tmp.write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def info(job):
    r=subprocess.run([str(slurm/'scontrol'),'show','job',job,'-o'],env=env,text=True,capture_output=True)
    if r.returncode:
        a=subprocess.run([str(slurm/'sacct'),'-n','-P','-j',job,'--format=JobIDRaw,State,ExitCode,NodeList'],env=env,text=True,capture_output=True,check=True)
        for line in a.stdout.splitlines():
            f=line.split('|')
            if f[0]==job:return {'JobId':job,'JobState':f[1].split()[0],'ExitCode':f[2],'NodeList':f[3]}
        raise RuntimeError('Cannot determine existing job state')
    return dict(p.split('=',1) for p in r.stdout.split() if '=' in p)
record=read(v/'resume_submission.json');new=record['job_id'];old=record['previous_job_id']
if not new.isdigit() or old!='395047':raise SystemExit('Unexpected handoff job IDs')
with (v/'handoff.lock').open('a+') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    released=v/'release_receipt.json'
    if released.exists():
        print(json.dumps({'already_released':read(released),'current':info(new)}),flush=True)
        raise SystemExit(0)
    newer=info(new)
    if newer.get('JobState')!='PENDING' or newer.get('Reason') not in {'JobHeldUser','JobHeldAdmin','Dependency'} or newer.get('Priority')!='0':raise SystemExit('Successor must still be held before handoff')
    older=info(old)
    if older.get('JobState') in {'RUNNING','COMPLETING'}:
        if older.get('JobName')!='chenlong_llama8b_c4_resume' or older.get('UserId')!='hansirui_3rd(1083)' or older.get('NodeList')!='dgx-100':raise SystemExit('Original allocation identity changed')
        write(v/'stop_requested.json',{'at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'job_id':old,'successor_job_id':new,'signal':'USR1 to batch coordinator only','old_job_state':older})
        if older['JobState']=='RUNNING':
            subprocess.run([str(slurm/'scancel'),'--signal=USR1','--batch',old],env=env,check=True)
        print(json.dumps({'phase':'stop_requested','old_job_id':old,'held_successor':new}),flush=True)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            older=info(old)
            if older.get('JobState') not in {'RUNNING','COMPLETING','PENDING','SUSPENDED','CONFIGURING'}:break
            time.sleep(2)
        else:raise SystemExit('Original allocation has not exited; successor remains held')
    if older.get('JobState') not in {'CANCELLED','FAILED','COMPLETED','TIMEOUT','NODE_FAIL','OUT_OF_MEMORY'}:raise SystemExit('Unexpected original terminal state; successor stays held')
    with (root/'locks/coordinator.lock').open('a+') as coordinator_lock:
        fcntl.flock(coordinator_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        snapshot_path=v/'handoff_snapshot.json'
        if not snapshot_path.exists():
            out=root/'results/llama80_three_methods';frozen=read(out/'frozen_protocol.json')
            protocol=hashlib.sha256(json.dumps(frozen,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
            if protocol!=record['base_protocol_sha256']:raise SystemExit('Frozen science changed')
            completed={};counts=collections.Counter();cache={};journal_count=0
            for p in (out/'results').glob('*.json'):
                result=read(p)
                if result.get('completion_status') not in {'complete','strict_experiment_failure'} or result.get('protocol_sha256')!=protocol:raise SystemExit('Invalid existing terminal result')
                completed[str(p.relative_to(root))]=sha(p)
                counts[result['cost_audit_method']+':'+result['completion_status']]+=1
            for p in (out/'call_cache').rglob('*.jsonl'):
                # A interrupted partial append must not be silently discarded.
                rows=[json.loads(line) for line in p.read_text().splitlines() if line.strip()]
                journal_count+=len(rows)
                cache[str(p.relative_to(root))]={'bytes':p.stat().st_size,'sha256':sha(p),'records':len(rows)}
            write(snapshot_path,{'created_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'previous_job_id':old,'successor_job_id':new,'old_terminal_state':older,'base_protocol_sha256':protocol,'launcher_sha256':sha(root/'runner/llama_launcher.py'),'completed_result_sha256':completed,'terminal_counts':dict(counts),'cache_files':cache,'journal_records':journal_count,'previous_server_command':read(root/'runs/395047/server_command.json'),'previous_runtime':read(root/'runs/395047/runtime.json')})
        else:
            snapshot=read(snapshot_path)
            for name,expected in snapshot['completed_result_sha256'].items():
                if sha(root/name)!=expected:raise SystemExit('Completed result changed before release')
        snapshot=read(snapshot_path)
        for name, expected in snapshot['cache_files'].items():
            if (root/name).stat().st_size != expected['bytes'] or sha(root/name) != expected['sha256']:
                raise SystemExit('Checkpoint cache changed before release')
        journals=0;responses_verified=0
        for requests_path in (root/'results/llama80_three_methods/call_cache').rglob('requests.jsonl'):
            starts=[json.loads(line) for line in requests_path.read_text().splitlines() if line.strip()]
            if [row['call_index'] for row in starts]!=list(range(1,len(starts)+1)):
                raise SystemExit('Checkpoint request sequence is invalid')
            for row in starts:
                signature=hashlib.sha256(json.dumps({'request':row['request'],'protocol_sha256':snapshot['base_protocol_sha256']},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
                if row['request_sha256']!=signature:raise SystemExit('Checkpoint request/config mismatch')
            rp=requests_path.with_name('responses.jsonl')
            saved=[json.loads(line) for line in rp.read_text().splitlines() if line.strip()] if rp.exists() else []
            indices=set()
            for row in saved:
                idx=row['call_index']
                if idx in indices or not 1<=idx<=len(starts) or row['request_sha256']!=starts[idx-1]['request_sha256'] or row['returned_model']!='llama-3.1-8b-instruct':
                    raise SystemExit('Checkpoint response/request mismatch')
                indices.add(idx)
            journals+=1;responses_verified+=len(saved)
        write(v/'cache_verification.json',{'verified_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'passed':True,'cache_files_verified':len(snapshot['cache_files']),'journals_verified':journals,'responses_verified':responses_verified,'handoff_snapshot_sha256':sha(snapshot_path)})
    print(json.dumps({'phase':'original_stopped_and_checkpointed','terminal_results':len(snapshot['completed_result_sha256']),'cache_files':len(snapshot['cache_files']),'old_state':older.get('JobState')}),flush=True)
    # Both the parent allocation and its shared coordinator lock are now released.
    subprocess.run([str(slurm/'scontrol'),'release',new],env=env,check=True)
    final={'released_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'previous_job_id':old,'job_id':new,'handoff_snapshot_sha256':sha(v/'handoff_snapshot.json'),'cache_verification_sha256':sha(v/'cache_verification.json'),'preserved_terminal_results':len(snapshot['completed_result_sha256']),'current_job':info(new)}
    write(released,final)
    print(json.dumps(final),flush=True)
'''
command=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','Group3_slogin','/usr/bin/python3 -B -c '+shlex.quote(CODE)]
result=subprocess.run(command,capture_output=True,text=True,timeout=180)
output=result.stdout+result.stderr
(HERE/'handoff_release_output.txt').write_text(output)
print(output,end='')
raise SystemExit(result.returncode)

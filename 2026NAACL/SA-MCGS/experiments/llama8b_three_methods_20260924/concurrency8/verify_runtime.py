#!/usr/bin/env python3
"""Read-only, one-shot audit of the eight-worker Llama allocation.

Only SSH read operations and Slurm queries run remotely. No inference, signal,
submission, process creation on a GPU node, or remote file write is performed.
The resulting audit is saved locally beside this script.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent

REMOTE_CODE = r'''
import collections,datetime,hashlib,json,os,pathlib,re,statistics,subprocess,time
root=pathlib.Path('/aifs4su/hansirui_3rd/chenlong/llama8b_20260924')
variant=root/'concurrency8'
assert os.getuid()==1083 and root.resolve(strict=True)==root
now=datetime.datetime.now().astimezone()
cutoff=now-datetime.timedelta(minutes=5)
slurm=pathlib.Path('/cm/shared/apps/slurm/current/bin')
env=dict(os.environ,SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf')
checks=[]
def check(name,condition,**details):
    checks.append(dict(name=name,passed=bool(condition),**details))
def path_for(relative):
    rel=pathlib.Path(relative)
    if rel.is_absolute() or '..' in rel.parts:raise RuntimeError('Unsafe audit input path')
    p=root/rel
    if p.resolve()!=p:raise RuntimeError('Symlink in audited path')
    return p
def read(path):return json.loads(path.read_text())
def maybe(path):return read(path) if path.is_file() else None
def sha(path,limit=None):
    h=hashlib.sha256();remaining=limit
    with path.open('rb') as f:
        while remaining is None or remaining>0:
            data=f.read(1024*1024 if remaining is None else min(1024*1024,remaining))
            if not data:break
            h.update(data)
            if remaining is not None:remaining-=len(data)
    if remaining not in (None,0):raise RuntimeError('Audited prefix was truncated')
    return h.hexdigest()
def query(args):
    p=subprocess.run([str(slurm/args[0]),*args[1:]],env=env,capture_output=True,text=True,timeout=20)
    return dict(exit_code=p.returncode,stdout=p.stdout.strip(),stderr=p.stderr.strip())
receipt=read(variant/'resume_submission.json')
job=str(receipt['job_id'])
if not job.isdigit():raise RuntimeError('Unexpected job identifier')
run=root/'runs'/job
status=maybe(run/'status.json')
server=maybe(run/'server_command.json')
children=maybe(run/'child_processes.json')
runtime=maybe(run/'runtime.json')
checkpoint=maybe(run/'checkpoint_verified.json')
release=maybe(variant/'release_receipt.json')
cache_proof=maybe(variant/'cache_verification.json')
handoff=read(variant/'handoff_snapshot.json')
handoff_sha=sha(variant/'handoff_snapshot.json')
execution=maybe(run/'execution_change.json')
amendment=maybe(run/'schema_execution_amendment.json')
job_query=query(['scontrol','show','job',job,'-o'])
accounting=query(['sacct','-n','-P','-j',job,'--format=JobIDRaw,State,ExitCode,Elapsed,NodeList'])
job_fields=dict(x.split('=',1) for x in job_query['stdout'].split() if '=' in x)
record_state=job_fields.get('JobState')
if record_state is None:
    for line in accounting['stdout'].splitlines():
        fields=line.split('|')
        if fields[0]==job:record_state=fields[1].split()[0]
check('receipt_eight_cases_and_thirty_two_sequences',receipt.get('case_concurrency')==8 and receipt.get('vllm_max_num_seqs')==32)
check('same_single_node_single_gpu_request',receipt.get('node')=='dgx-100' and receipt.get('nodes')==1 and receipt.get('gpu_count')==1)
check('slurm_running_or_completed',record_state in ('RUNNING','COMPLETED'),state=record_state)
check('runtime_status_running_or_complete',bool(status) and status.get('status') in ('running','complete'),status=status)
check('handoff_bound_to_released_successor',bool(release) and str(release.get('job_id'))==job and release.get('handoff_snapshot_sha256')==handoff_sha)
check('cache_proof_bound_to_handoff',bool(cache_proof) and cache_proof.get('passed') is True and cache_proof.get('handoff_snapshot_sha256')==handoff_sha)
check('execution_bound_to_handoff',bool(execution) and execution.get('handoff_snapshot_sha256')==handoff_sha)
check('exactly_fifty_six_preserved_results',len(handoff['completed_result_sha256'])==56,actual=len(handoff['completed_result_sha256']))
result_errors=[]
for name,expected in handoff['completed_result_sha256'].items():
    p=path_for(name)
    if not p.is_file() or sha(p)!=expected:result_errors.append(name)
check('all_preserved_results_sha256_match',not result_errors,changed_or_missing=result_errors)
prefix_errors=[]
for name,expected in handoff['cache_files'].items():
    p=path_for(name)
    if not p.is_file() or p.stat().st_size<expected['bytes'] or sha(p,expected['bytes'])!=expected['sha256']:
        prefix_errors.append(name)
check('all_cache_prefixes_preserved',not prefix_errors,prefixes=len(handoff['cache_files']),changed_or_missing=prefix_errors)
result_dir=root/'results/llama80_three_methods/results'
counts=collections.Counter();schema_failures=[];result_errors_current=[]
for p in result_dir.glob('*.json'):
    try:
        data=read(p);state=data.get('completion_status');method=data.get('cost_audit_method')
        counts[str(method)+':'+str(state)]+=1
        if state=='strict_experiment_failure' and data.get('error_type')=='ValidationError':
            schema_failures.append({'file':p.name,'case_id':data.get('case_id'),'method':method,
                'terminalization_protocol_sha256':data.get('terminalization_protocol_sha256'),
                'schema_compat_adapter_sha256':data.get('schema_compat_adapter_sha256'),
                'cached_only_schema_recovery':data.get('cached_only_schema_recovery'),
                'schema_recovery_audit':data.get('schema_recovery_audit')})
        if state not in ('complete','strict_experiment_failure'):result_errors_current.append(p.name)
    except Exception as exc:result_errors_current.append(p.name+':'+type(exc).__name__)
check('current_results_are_terminal',not result_errors_current,errors=result_errors_current)
schema_rule=read(variant/'schema_amendment.json');known=schema_rule['known_cached_failure']
known_result=maybe(result_dir/(known['case_id']+'__'+known['method']+'.json'))
known_cache=root/'results/llama80_three_methods/call_cache'/known['case_id']/known['method']
known_cache_ok=all((known_cache/name).is_file() and sha(known_cache/name)==expected for name,expected in known['cache_files_sha256'].items())
check('known_schema_failure_recovers_without_new_api_call',bool(known_result)
    and known_result.get('completion_status')=='strict_experiment_failure'
    and known_result.get('error_type')=='ValidationError'
    and known_result.get('cached_only_schema_recovery') is True
    and known_result.get('schema_recovery_audit',{}).get('new_api_calls')==0
    and known_result.get('schema_compat_adapter_sha256')==sha(variant/'schema_compat_launcher.py')
    and known_cache_ok,known_result_present=bool(known_result),original_cache_exactly_unchanged=known_cache_ok)
argv=(server or {}).get('argv',[])
def option(name):
    try:return argv[argv.index(name)+1]
    except (ValueError,IndexError):return None
check('server_max_num_seqs_32',option('--max-num-seqs')=='32')
check('server_batch_tokens_8192',option('--max-num-batched-tokens')=='8192')
check('server_memory_budget_085',option('--gpu-memory-utilization')=='0.85')
check('server_same_local_endpoint',option('--host')=='127.0.0.1' and option('--port')=='18081')
check('server_one_tensor_parallel_gpu',option('--tensor-parallel-size')=='1')
check('same_h800_and_cuda_device',bool(runtime) and runtime.get('hostname')=='dgx-100' and 'H800' in runtime.get('gpu','') and runtime.get('cuda_visible_devices')=='0',runtime=runtime)
official=read(root/'official_model_metadata.json')
official_files={x['rfilename']:x for x in official['siblings']}
marker_path=root/'model_download_complete.json';marker=read(marker_path)
checkpoint_errors=[]
if checkpoint:
    if checkpoint.get('repository')!='meta-llama/Llama-3.1-8B-Instruct' or checkpoint.get('revision')!='0e9e39f249a16976918f6564b8830bc894c89659' or checkpoint.get('dtype')!='bfloat16':checkpoint_errors.append('checkpoint_identity')
    if checkpoint.get('marker_sha256')!=sha(marker_path):checkpoint_errors.append('download_marker_hash')
    shards=[x for x in checkpoint.get('files',[]) if x['path'].endswith('.safetensors')]
    if len(shards)!=4:checkpoint_errors.append('shard_count')
    for row in shards:
        expected=official_files.get(row['path'],{})
        if row.get('sha256')!=expected.get('lfs',{}).get('sha256') or row.get('size')!=expected.get('size'):checkpoint_errors.append(row['path'])
else:checkpoint_errors.append('checkpoint_verification_not_yet_written')
check('gpu_startup_checkpoint_verification_matches_official',not checkpoint_errors,errors=checkpoint_errors,
      note='Uses the GPU coordinator\'s completed full-weight hash check; this read-only audit does not reread 16GB of weights on the login node.')
worker_rows=[x for x in (children or {}).get('children',[]) if x.get('name','').startswith('shard_')]
worker_names={x.get('name') for x in worker_rows}
heartbeat_age=None
if status and status.get('updated_at'):
    heartbeat_text=re.sub(r'([+-]\d{2})(\d{2})$',r'\1:\2',status['updated_at'])
    heartbeat_age=(now-datetime.datetime.fromisoformat(heartbeat_text)).total_seconds()
check('all_eight_workers_launched',worker_names=={'shard_'+str(i) for i in range(8)})
check('coordinator_recent_or_complete',bool(status) and (status.get('status')=='complete' or heartbeat_age is not None and -5<=heartbeat_age<=90),heartbeat_age_seconds=heartbeat_age)
# This is a Slurm read RPC, not srun and not a new allocation.
pid_query=query(['scontrol','listpids',job,'dgx-100']) if record_state=='RUNNING' else None
pid_set=set()
if pid_query and pid_query['exit_code']==0:
    for line in pid_query['stdout'].splitlines():
        fields=line.split()
        if fields and fields[0].isdigit():pid_set.add(int(fields[0]))
worker_process_evidence=[]
for item in worker_rows:
    log=run/(item['name']+'.log')
    worker_process_evidence.append({**item,'pid_visible_to_slurm':item['pid'] in pid_set if pid_set else None,
        'log_exists':log.is_file(),'log_bytes':log.stat().st_size if log.is_file() else None,
        'log_modified_at':datetime.datetime.fromtimestamp(log.stat().st_mtime).astimezone().isoformat() if log.is_file() else None})
log_tails={};hard_errors=[];preemption_lines=[];allowed_schema_tracebacks=[]
metric_rows=[];kv_info={};server_path=run/'vllm_server.log'
for p in [server_path,*[run/('shard_'+str(i)+'.log') for i in range(8)]]:
    if not p.is_file():continue
    text=p.read_text(errors='replace');lines=text.splitlines();log_tails[p.name]=lines[-16:]
    if p==server_path:
        for line in lines:
            memory=re.search(r'Available KV cache memory: ([\d.]+) GiB',line)
            tokens=re.search(r'GPU KV cache size: ([\d,]+) tokens',line)
            if memory:kv_info['memory_gib']=float(memory.group(1))
            if tokens:kv_info['capacity_tokens']=int(tokens.group(1).replace(',',''))
            hit=re.search(r'(\d\d-\d\d) (\d\d:\d\d:\d\d).*Avg prompt throughput: ([\d.]+) tokens/s, Avg generation throughput: ([\d.]+) tokens/s, Running: (\d+) reqs, Waiting: (\d+) reqs,.*GPU KV cache usage: ([\d.]+)%',line)
            if hit:
                moment=datetime.datetime.strptime(str(now.year)+'-'+hit.group(1)+' '+hit.group(2),'%Y-%m-%d %H:%M:%S').replace(tzinfo=now.tzinfo)
                if moment>=cutoff:
                    metric_rows.append({'at':moment.isoformat(),'prompt_tokens_per_second':float(hit.group(3)),
                        'generation_tokens_per_second':float(hit.group(4)),'running':int(hit.group(5)),
                        'waiting':int(hit.group(6)),'kv_usage_percent':float(hit.group(7))})
    for i,line in enumerate(lines):
        if re.search(r'preempt',line,re.I):preemption_lines.append({'file':p.name,'line':i+1,'text':line})
        if not re.search(r'out of memory|CUDA error|IntegrityStop|Traceback \(most recent call last\)',line,re.I):continue
        # A model schema failure is allowed only if it becomes an explicitly
        # recorded terminal observation, rather than stopping its worker.
        block='\n'.join(lines[i:min(len(lines),i+70)])
        allowed=(p!=server_path and 'Traceback (most recent call last)' in line and 'ValidationError' in block
                 and 'strict_experiment_failure' in block and bool(schema_failures)
                 and 'IntegrityStop' not in block)
        record={'file':p.name,'line':i+1,'text':line}
        (allowed_schema_tracebacks if allowed else hard_errors).append(record)
check('no_worker_integrity_error_or_unhandled_traceback_or_oom',not hard_errors,errors=hard_errors)
check('real_kv_capacity_recorded',bool(kv_info.get('capacity_tokens')))
check('recent_server_throughput_observed',bool(metric_rows))
metric_summary={}
if metric_rows:
    metric_summary={'samples':len(metric_rows),'from':metric_rows[0]['at'],'to':metric_rows[-1]['at'],
        'running_max':max(x['running'] for x in metric_rows),'waiting_max':max(x['waiting'] for x in metric_rows),
        'kv_usage_percent_max':max(x['kv_usage_percent'] for x in metric_rows),
        'generation_mean':statistics.mean(x['generation_tokens_per_second'] for x in metric_rows),
        'generation_max':max(x['generation_tokens_per_second'] for x in metric_rows),
        'observed_above_old_sequence_limit':any(x['running']>16 for x in metric_rows)}
result={'checked_at':now.isoformat(),'read_only':True,'api_calls':0,'job_id':job,
    'receipt':receipt,'slurm_job':job_query,'slurm_accounting':accounting,
    'status':status,'runtime':runtime,'server_command':server,'checkpoint_verification':checkpoint,
    'handoff_snapshot_sha256':handoff_sha,'preserved_result_count':len(handoff['completed_result_sha256']),
    'changed_results':result_errors,'verified_cache_prefixes':len(handoff['cache_files']),
    'changed_cache_prefixes':prefix_errors,'current_terminal_result_count':sum(counts.values()),
    'current_result_counts':dict(counts),'schema_failures_allowed_as_terminal_observations':schema_failures,
    'schema_execution_amendment':amendment,'worker_process_evidence':worker_process_evidence,
    'worker_liveness_scope':'OS PIDs use Slurm listpids if available. Otherwise eight launched workers plus the fresh coordinator heartbeat provide indirect liveness evidence; stored returncode=null alone is not treated as a live-process probe.',
    'slurm_pid_query':pid_query,'recent_server_metrics':metric_rows,'recent_metrics_summary':metric_summary,
    'kv_cache':kv_info,'preemption_log_lines':preemption_lines,'preemption_counter_queried':False,
    'allowed_schema_tracebacks':allowed_schema_tracebacks,'log_tails':log_tails,
    'checks':checks,'checks_passed':sum(x['passed'] for x in checks),'checks_total':len(checks),
    'passed':all(x['passed'] for x in checks)}
print(json.dumps(result,ensure_ascii=False))
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh-alias', default='Group3_slogin', choices=('Group3_slogin','Group3_dgx-127'))
    parser.add_argument('--output', type=Path, default=HERE/'runtime_verification.json')
    parser.add_argument('--syntax-only', action='store_true')
    args = parser.parse_args()
    ast.parse(REMOTE_CODE)
    if args.syntax_only:
        print(json.dumps({'syntax_valid': True, 'network_calls': 0}))
        return 0
    command = ['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15',
               args.ssh_alias,'python3 -I -B -']
    response = subprocess.run(command,input=REMOTE_CODE,capture_output=True,text=True,timeout=180)
    if response.returncode:
        print(json.dumps({'audit_executed':False,'ssh_exit_code':response.returncode,
                          'stderr':response.stderr[-2500:]},ensure_ascii=False))
        return 2
    result = json.loads(response.stdout)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.is_symlink():
        raise RuntimeError('Refuse a symlinked local audit output')
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(args.output),'job_id':result['job_id'],'passed':result['passed'],
        'checks_passed':result['checks_passed'],'checks_total':result['checks_total'],
        'status':(result['status'] or {}).get('status'),'preserved_results':result['preserved_result_count'],
        'cache_prefixes':result['verified_cache_prefixes'],'terminal_results':result['current_terminal_result_count'],
        'metrics':result['recent_metrics_summary'],'kv_cache':result['kv_cache'],
        'failed_checks':[x for x in result['checks'] if not x['passed']]},ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())

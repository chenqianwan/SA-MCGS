#!/usr/bin/env python3
"""One-shot CPU orchestration: restore -> verified retirement -> services -> workers.

Only existing allocation 415747 is used. Durable launch receipts prohibit retries.
This process never calls a scientific model, rewrites budgets, or repeats arms.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

DEPLOY = Path(__file__).resolve().parent
ROOT = DEPLOY.parent
AUTHORIZED_ROOT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')
PYTHON = '/aifs4su/hansirui/vllm-dsv4-venv/bin/python3'
JOB, NODE, UID = '415747', 'dgx-061', 1083
REPOSITORY = 'Qwen/Qwen2.5-72B-Instruct-AWQ'
REVISION = '698703eae6604af048a3d2f509995dc302088217'
ALIAS = 'qwen2.5-72b-instruct'
MODEL_PATH = Path('/aifs4su/hansirui_3rd/chenlong/q72awq_20261012/model')
STATUS = DEPLOY/'pipeline_status.json'
STOP = False


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path = Path(path)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with temporary.open('w') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def interrupted():
    if STOP:
        raise InterruptedError('Pipeline received a termination signal; persistent launches are retained for review')


def pause(seconds=5):
    for _ in range(seconds):
        interrupted()
        time.sleep(1)


def environment_identity():
    require(ROOT == AUTHORIZED_ROOT and ROOT.resolve() == ROOT, 'Unexpected pipeline root')
    require(os.getuid() == UID and socket.gethostname().split('.')[0] == NODE,
            'Pipeline requires the exact deployment account and node')
    require(os.environ.get('SLURM_JOB_ID') == JOB, 'Pipeline requires existing allocation 415747')
    require(os.environ.get('SLURM_STEP_ID', '').isdigit(), 'Pipeline requires a numbered Slurm CPU step')
    require(os.environ.get('CUDA_VISIBLE_DEVICES', '') in ('', '-1', 'NoDevFiles')
            and os.environ.get('SLURM_STEP_GPUS', '') in ('', '-1', 'NoDevFiles'),
            'Pipeline must run in a CPU-only step')


def verify_source_receipt():
    receipt = read(DEPLOY/'pipeline_launch_receipt.json')
    require(receipt.get('job_id') == JOB and receipt.get('node') == NODE
            and receipt.get('auto_retry') is False and receipt.get('gpu_requested') is False,
            'Pipeline launch identity mismatch')
    files = receipt.get('verified_files', {})
    require('deployment/pipeline_supervisor.py' in files and 'start_workers_once.py' in files,
            'Pipeline launch source proof is missing')
    for name, expected in files.items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe pipeline manifest entry')
        path = ROOT/relative
        require(path.resolve() == path and sha(path) == expected, 'Pipeline source changed: '+name)
    return receipt


def child_environment(gpu_step=False):
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env.update(PYTHONHASHSEED='42', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               PYTHON_DOTENV_DISABLED='1', SLURM_EXPORT_ENV='ALL',
               SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf')
    if gpu_step:
        # The caller is a CPU-only step. New srun --gres=gpu:8 must determine its
        # own GPU visibility, rather than inherit the caller's empty assignment.
        for key in ('CUDA_VISIBLE_DEVICES', 'SLURM_STEP_GPUS', 'SLURM_GPUS_ON_NODE',
                    'SLURM_GPUS_PER_TASK', 'SLURM_GPUS_PER_NODE', 'SLURM_GPUS',
                    'SLURM_GRES', 'SLURM_TRES_PER_TASK', 'SLURM_TRES_BIND',
                    'SLURM_GPU_BIND', 'SLURM_MEM_PER_GPU'):
            env.pop(key, None)
    return env


def run_once(label, script, arguments=(), gpu_step=False, timeout=300):
    interrupted()
    command = [PYTHON, '-B', str(script), *arguments]
    with (DEPLOY/f'pipeline_{label}.log').open('ab', buffering=0) as log:
        result = subprocess.run(command, cwd=ROOT, env=child_environment(gpu_step),
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            timeout=timeout, check=False)
    require(result.returncode == 0, f'{label} failed with exit code {result.returncode}; no retry')
    interrupted()
    return {'command': command, 'exit_code': result.returncode, 'completed_at': now(),
            'log': str(DEPLOY/f'pipeline_{label}.log')}


def restored_model():
    if (DEPLOY/'model_restore_failure.json').exists():
        raise RuntimeError('Model restore failure marker exists; pipeline stopped without retry')
    status_path = DEPLOY/'model_restore_status.json'
    if status_path.exists() and read(status_path).get('state') == 'failed':
        raise RuntimeError('Model restore reported failure; pipeline stopped without retry')
    path = DEPLOY/'model_download_complete.json'
    if not path.exists():
        return None
    value = read(path)
    require(value.get('state') == 'complete' and value.get('verified') is True
            and value.get('repository') == REPOSITORY and value.get('revision') == REVISION
            and Path(value.get('model_path', '')).resolve() == MODEL_PATH,
            'Completed restore marker has the wrong checkpoint identity')
    return {'path': str(path), 'sha256': sha(path), 'repository': REPOSITORY,
            'revision': REVISION, 'verified_files': len(value.get('files', []))}


def retirement_verified():
    path = DEPLOY/'previous_service_retirement.json'
    if not path.exists():
        return None
    receipt = read(path)
    if receipt.get('status') != 'retired':
        raise RuntimeError('Prior retirement receipt is not confirmed retired; no retry or repeat signal permitted')
    spec = importlib.util.spec_from_file_location('qwen_pipeline_retirement', DEPLOY/'retire_previous_services.py')
    retirement = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(retirement)
    require(receipt.get('job_id') == JOB and receipt.get('target_pid') == retirement.OLD_PID
            and receipt.get('target_step_id') == retirement.OLD_STEP
            and receipt.get('target_root') == str(retirement.OLD)
            and receipt.get('signal_sent') is True and receipt.get('service_ports_closed') is True,
            'Existing retirement receipt does not identify the authorized prior services')
    retirement.environment_identity()
    retirement.complete_science()
    started = receipt.get('process_identity', {}).get('starttime_ticks')
    require(type(started) is int, 'Retirement PID start-time proof is missing')
    exit_state = retirement.process_exit_state(started)
    require(exit_state in ('absent', 'zombie') and not retirement.open_ports(),
            'Recorded old services are no longer confirmed retired')
    return {'status': 'retired_verified', 'receipt_sha256': sha(path), 'process_exit_state': exit_state,
            'service_ports_closed': True, 'repeat_signal_sent': False, 'verified_at': now()}


def ready_services():
    path = DEPLOY/'service_state.json'
    if not path.exists():
        return None
    state = read(path)
    if state.get('status') in ('failed', 'stopped', 'stopping', 'needs_attention'):
        raise RuntimeError('New model services reported '+str(state.get('status'))+'; no retry')
    if state.get('status') != 'ready':
        return None
    endpoint_path = ROOT/'endpoints.json'
    require(endpoint_path.exists(), 'Ready services have no endpoint publication')
    endpoints = read(endpoint_path)
    require(state.get('job_id') == JOB and str(endpoints.get('job_id')) == JOB
            and state.get('hostname', '').split('.')[0] == NODE
            and endpoints.get('hostname', '').split('.')[0] == NODE,
            'New model service allocation identity mismatch')
    require(state.get('pid') == endpoints.get('service_supervisor_pid')
            and str(state.get('step_id')) == str(endpoints.get('service_step_id')),
            'Endpoint publication does not belong to the ready service supervisor')
    models = endpoints.get('models', {})
    require(set(models) == {'qwen25'}, 'Unexpected endpoint model keys')
    model = models['qwen25']
    require(model.get('alias') == ALIAS and model.get('checkpoint') == REPOSITORY
            and model.get('model_revision') == REVISION and model.get('tensor_parallel_size') == 2
            and model.get('max_model_len') == 131072,
            'Ready service model, revision, TP or context configuration mismatch')
    replicas = endpoints.get('replicas', [])
    require(len(replicas) == 4 and {r.get('id') for r in replicas} == {f'qwen25-{i}' for i in range(4)}
            and {r.get('port') for r in replicas} == set(range(19271, 19275)),
            'Expected four independently verified TP2 replicas')
    state_replicas = {r['id']: r for r in state.get('replicas', [])}
    require(len(state_replicas) == 4 and state.get('synthetic_smoke_calls') == 4,
            'Ready services must have exactly four completed synthetic smoke calls')
    proofs = []
    for replica in replicas:
        require(replica.get('model_key') == 'qwen25' and replica.get('alias') == ALIAS
                and replica.get('status') == 'healthy'
                and state_replicas.get(replica['id'], {}).get('status') == 'healthy'
                and replica.get('base_url') == f'http://127.0.0.1:{replica["port"]}/v1',
                'Ready replica identity or health proof mismatch')
        smoke_path = DEPLOY/'runtime'/JOB/(replica['id']+'_smoke.json')
        smoke = read(smoke_path)
        usage = smoke.get('response', {}).get('usage', {})
        prompt = smoke.get('expected_prompt_tokens')
        require(smoke.get('scientific_experiment') is False and smoke.get('prompt_token_match') is True
                and smoke.get('request', {}).get('model') == ALIAS
                and smoke.get('response', {}).get('model') == ALIAS
                and type(prompt) is int and prompt > 0 and usage.get('prompt_tokens') == prompt
                and type(usage.get('completion_tokens')) is int and 0 < usage['completion_tokens'] <= 8
                and usage.get('total_tokens') == prompt + usage['completion_tokens'],
                'Synthetic smoke token accounting is not verified')
        proofs.append({'replica_id': replica['id'], 'sha256': sha(smoke_path)})
    return {'endpoints_sha256': sha(endpoint_path), 'service_state_sha256': sha(path),
            'service_pid': state['pid'], 'service_step_id': state['step_id'], 'replicas': 4,
            'smoke_proofs': proofs, 'verified_at': now()}


def workers_running():
    path = ROOT/'execution/status.json'
    if not path.exists():
        return None
    state = read(path)
    if state.get('status') in ('needs_attention', 'failed', 'interrupted', 'service_wait_timeout'):
        raise RuntimeError('Scientific worker supervisor reported '+str(state.get('status'))+'; no retry')
    if state.get('status') != 'running' or state.get('running_workers', 0) <= 0:
        return None
    require(str(state.get('job_id')) == JOB and state.get('expected_results') == 160
            and state.get('sa_execution_enabled') is False and state.get('external_api_enabled') is False,
            'Running workers do not match the authorized 160-arm baseline scope')
    return {'status_sha256': sha(path), 'running_workers': state['running_workers'],
            'expected_results': 160, 'verified_at': now()}


def worker_terminal_state():
    path = ROOT/'execution/status.json'
    value = read(path)
    require(str(value.get('job_id')) == JOB and value.get('expected_results') == 160
            and value.get('sa_execution_enabled') is False,
            'Scientific supervisor scope changed while pipeline monitored it')
    if value.get('status') not in ('complete', 'needs_attention', 'interrupted', 'failed'):
        return None
    if value['status'] == 'complete':
        require(value.get('final_results') == 160 and value.get('running_workers') == 0,
                'Completed supervisor does not contain all 160 terminal arms')
    return value


def scientific_processes_alive(terminal):
    # Only check identities from this experiment; never signal scientific workers.
    pids = [terminal.get('pid'), *[worker.get('pid') for worker in terminal.get('workers', [])]]
    alive = []
    allowed = {str(ROOT/'runner.py').encode(), str(ROOT/'worker_supervisor.py').encode()}
    for pid in pids:
        if type(pid) is not int or pid <= 1:
            continue
        process = Path('/proc')/str(pid)
        try:
            args = (process/'cmdline').read_bytes().split(b'\0')
            stat = (process/'stat').read_text().rsplit(')', 1)[1].strip().split()
            if stat[0] != 'Z' and allowed.intersection(args) and process.stat().st_uid == UID:
                alive.append(pid)
        except FileNotFoundError:
            pass
    return alive


def stop_own_services():
    result = run_once('stop_own_services', DEPLOY/'stop_services.py', timeout=60)
    deadline = time.monotonic()+180
    while True:
        interrupted()
        service = read(DEPLOY/'service_state.json')
        require(service.get('job_id') == JOB and service.get('hostname', '').split('.')[0] == NODE,
                'Own service identity changed during shutdown')
        if service.get('status') == 'stopped':
            require(not (ROOT/'endpoints.json').exists(), 'Stopped services still publish endpoints')
            return {**result, 'status': 'stopped', 'verified_at': now()}
        require(service.get('status') != 'failed', 'Own service supervisor failed during shutdown')
        require(time.monotonic() < deadline, 'Own service cleanup exceeded three minutes; no repeat signal')
        pause()


def main():
    global STOP
    environment_identity()
    os.umask(0o077)
    with (DEPLOY/'pipeline_supervisor.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not STATUS.exists(), 'Prior pipeline state exists; no automatic resume or retry')
        state = {'status': 'initializing', 'job_id': JOB, 'node': NODE,
                 'step_id': os.environ['SLURM_STEP_ID'], 'pid': os.getpid(), 'started_at': now(),
                 'launch_receipt_sha256': sha(DEPLOY/'pipeline_launch_receipt.json'),
                 'auto_retry': False, 'gpu_requested': False, 'scientific_model_calls': 0,
                 'sa_execution_enabled': False, 'stages': {}}
        def update(status, **fields):
            state.update(status=status, updated_at=now(), **fields)
            save(STATUS, state)
            print(json.dumps({'status': status, 'at': now(), **fields}), flush=True)
        def stop(signum, frame):
            global STOP
            STOP = True
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            verify_source_receipt()
            update('waiting_for_model_restore', restore_wait_deadline_unix=time.time()+7200)
            deadline = time.monotonic()+7200
            while True:
                interrupted()
                proof = restored_model()
                if proof:
                    state['stages']['restore'] = proof
                    break
                require(time.monotonic() < deadline, 'Model restore wait exceeded two hours; no retry')
                pause()
            verify_source_receipt()
            update('retiring_previous_services')
            proof = retirement_verified()
            if proof is None:
                state['stages']['retirement_command'] = run_once('retire_previous',
                    DEPLOY/'retire_previous_services.py', ('--retire',), timeout=300)
                proof = retirement_verified()
                require(proof is not None, 'Retirement finished without a verified retired receipt')
            state['stages']['retirement'] = proof
            verify_source_receipt()
            update('starting_services')
            state['stages']['service_launch'] = run_once('start_services', DEPLOY/'start_services_once.py',
                                                        gpu_step=True, timeout=180)
            update('waiting_for_services', service_wait_deadline_unix=time.time()+7200)
            deadline = time.monotonic()+7200
            while True:
                interrupted()
                proof = ready_services()
                if proof:
                    state['stages']['services'] = proof
                    break
                require(time.monotonic() < deadline, 'New model service startup exceeded two hours; no retry')
                pause()
            verify_source_receipt()
            update('starting_workers')
            state['stages']['worker_launch'] = run_once('start_workers', ROOT/'start_workers_once.py', timeout=180)
            update('waiting_for_workers', worker_wait_deadline_unix=time.time()+1200)
            deadline = time.monotonic()+1200
            while True:
                interrupted()
                ready_services()  # A failed service blocks accepting the worker startup.
                proof = workers_running()
                if proof:
                    state['stages']['workers'] = proof
                    break
                require(time.monotonic() < deadline, 'Worker startup exceeded twenty minutes; no retry')
                pause()
            update('workers_running', workers_started_at=now(), running_workers=proof['running_workers'],
                   lifetime='Remain in this CPU step so nested srun controllers survive until the experiment ends')
            # start_new_session does not escape the pipeline Slurm cgroup. Keep
            # this step alive for all nested service/worker srun controllers.
            while True:
                interrupted()
                terminal = worker_terminal_state()
                if terminal is not None:
                    break
                pause(15)
            update('waiting_for_worker_exit', worker_terminal_status=terminal['status'],
                   final_results=terminal.get('final_results'))
            deadline = time.monotonic()+300
            while scientific_processes_alive(terminal):
                require(time.monotonic() < deadline, 'Terminal worker supervisor left active workers; no force kill or retry')
                pause()
            update('stopping_own_services', worker_terminal_status=terminal['status'])
            state['stages']['service_shutdown'] = stop_own_services()
            successful = terminal['status'] == 'complete'
            update('complete' if successful else 'needs_attention', completed_at=now(),
                   worker_terminal_status=terminal['status'], final_results=terminal.get('final_results'),
                   own_services_stopped=True, scientific_retries=0)
            return 0 if successful else 1
        except BaseException as error:
            update('interrupted' if isinstance(error, InterruptedError) else 'failed',
                   failed_at=now(), error_type=type(error).__name__, error=str(error),
                   launched_services_and_workers_retained=True)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())

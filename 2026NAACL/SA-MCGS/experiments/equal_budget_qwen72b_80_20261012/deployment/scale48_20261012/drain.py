#!/usr/bin/env python3
"""Drain existing Qwen arms through their unchanged claim locks; never signal a process.

Run in a separate CPU-only step of job 415747. Existing arms finish normally;
unclaimed arms stay locked until the old pipeline has cleaned up and exited.
An incomplete final count intentionally makes the old pipeline needs_attention.
No inference, retries, result edits, or service/worker launches are performed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUTHORIZED_ROOT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')
UID, NODE, JOB = 1083, 'dgx-061', '415747'
PIPELINE_STEP, SERVICE_STEP, WORKER_STEP = '41', '42', '43'
PYTHON = '/aifs4su/hansirui/vllm-dsv4-venv/bin/python3'
MODEL = 'qwen2.5-72b-instruct'
METHODS = ('lea', 'full-scc')
PORTS = tuple(range(19271, 19275))
DEADLINE_SECONDS = 3 * 3600
POLL_SECONDS = 15
STOP_SIGNAL = None


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                   separators=(',', ':'), default=str).encode()).hexdigest()


def save(path, value):
    path = Path(path)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def environment_identity():
    step = os.environ.get('SLURM_STEP_ID', '')
    require(ROOT == AUTHORIZED_ROOT and ROOT.resolve() == ROOT, 'Unexpected drain root')
    require(os.getuid() == UID and socket.gethostname().split('.')[0] == NODE,
            'Drain requires the authorized account on dgx-061')
    require(os.environ.get('SLURM_JOB_ID') == JOB and step.isdigit()
            and step not in (PIPELINE_STEP, SERVICE_STEP, WORKER_STEP),
            'Drain requires its own independent numbered step in allocation 415747')
    require(os.environ.get('CUDA_VISIBLE_DEVICES', '') in ('', '-1', 'NoDevFiles')
            and os.environ.get('SLURM_STEP_GPUS', '') in ('', '-1', 'NoDevFiles'),
            'Drain must be CPU-only')
    return {'uid': UID, 'hostname': socket.gethostname(), 'job_id': JOB,
            'step_id': step, 'pid': os.getpid(), 'gpu_requested': False}


def load_tasks(root):
    queue = read(root/'execution/task_queue.json')
    scope = read(root/'run_scope.json')
    refs = read(root/'historical_sa_reference.json')['rows']
    require(queue.get('model_key') == 'qwen25' and queue.get('expected_results') == 160
            and queue.get('sa_execution_enabled') is False, 'Unexpected queue scope')
    require(scope.get('expected_results') == 160 and scope.get('cases_per_model') == 80
            and scope.get('models') == ['qwen25'] and scope.get('execution_methods') == list(METHODS)
            and scope.get('sa_execution_enabled') is False, 'Unexpected frozen run scope')
    protocol_hash = digest(read(root/'protocol.json'))
    require(queue.get('protocol_sha256') == protocol_hash, 'Queue/protocol identity mismatch')
    budgets = {(r['case_uid'], r['model_key']): r['usage']['total_tokens'] for r in refs}
    expected = {(uid, method) for uid in scope['case_uids'] for method in METHODS}
    tasks = queue.get('tasks', [])
    require(len(tasks) == 160 and len(expected) == 160 and len(budgets) == 80,
            'Expected 80 unique cases and 160 unique arm identities')
    seen = set()
    for task in tasks:
        uid, method = task['case_uid'], task['method']
        require(re.fullmatch(r'scid-v1-[a-f0-9]{64}', uid) is not None
                and method in METHODS, 'Unsafe or unknown task identity')
        key = (uid, method)
        require(key not in seen and key in expected, 'Duplicate or out-of-scope task')
        require(type(task.get('token_budget')) is int and task['token_budget'] > 0
                and task['token_budget'] == budgets[(uid, 'qwen25')], 'Task budget changed')
        seen.add(key)
    require(seen == expected, 'Queue coverage mismatch')
    proofs = {name: sha(root/name) for name in ('execution/task_queue.json', 'run_scope.json',
              'historical_sa_reference.json', 'protocol.json', 'runner.py', 'worker_supervisor.py',
              'science_support.py', 'methods_full.py', 'budget_client.py')}
    return tasks, protocol_hash, proofs


def task_key(task):
    return task['case_uid']+'__'+task['method']


class ClaimLocks:
    def __init__(self, root, tasks):
        self.directory = root/'execution/claims/qwen25'
        require(self.directory.is_dir() and self.directory.resolve() == self.directory,
                'Original claim directory is missing or redirected')
        self.tasks = tasks
        self.handles = {}

    def acquire_available(self):
        for task in self.tasks:
            key = task_key(task)
            if key in self.handles:
                continue
            path = self.directory/(key+'.lock')
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            try:
                require(os.fstat(fd).st_uid == UID, 'Claim lock is not owned by the authorized account')
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
            except BaseException:
                os.close(fd)
                raise
            else:
                self.handles[key] = fd
        return len(self.handles)

    def close(self):
        for fd in self.handles.values():
            os.close(fd)
        self.handles.clear()


def process_snapshot(pid):
    require(type(pid) is int and pid > 1, 'Invalid watched PID')
    path = Path('/proc')/str(pid)
    try:
        fields = (path/'stat').read_text().rsplit(')', 1)[1].strip().split()
        if fields[0] == 'Z':
            return None
        argv = [v.decode() for v in (path/'cmdline').read_bytes().split(b'\0') if v]
        environ = dict(v.split(b'=', 1) for v in (path/'environ').read_bytes().split(b'\0') if b'=' in v)
        return {'pid': pid, 'start_ticks': int(fields[19]), 'uid': path.stat().st_uid,
                'argv': argv, 'job_id': environ.get(b'SLURM_JOB_ID', b'').decode(),
                'step_id': environ.get(b'SLURM_STEP_ID', b'').decode()}
    except FileNotFoundError:
        return None


def states(root):
    return {'pipeline': read(root/'deployment/pipeline_status.json'),
            'services': read(root/'deployment/service_state.json'),
            'workers': read(root/'execution/status.json')}


def watch_processes(root, state):
    watched = {}
    definitions = [('pipeline', state['pipeline']['pid'], PIPELINE_STEP,
                    [PYTHON, '-B', str(root/'deployment/pipeline_supervisor.py')]),
                   ('services', state['services']['pid'], SERVICE_STEP,
                    [PYTHON, '-B', str(root/'deployment/service_supervisor.py')]),
                   ('worker_supervisor', state['workers']['pid'], WORKER_STEP,
                    [PYTHON, '-B', str(root/'worker_supervisor.py')])]
    expected_names = {f'qwen25-{replica}_worker{worker}' for replica in range(4) for worker in range(8)}
    workers = state['workers'].get('workers', [])
    require(len(workers) == 32 and {w['name'] for w in workers} == expected_names,
            'Expected exactly the existing 32 worker identities')
    for worker in workers:
        replica, index = worker['name'].split('_worker')
        command = [PYTHON, '-B', str(root/'runner.py'), '--replica-id', replica, '--worker-index', index]
        require(worker.get('model') == 'qwen25' and worker.get('command') == command,
                'Unexpected scientific worker command')
        definitions.append((worker['name'], worker['pid'], WORKER_STEP, command))
    require(len({pid for _, pid, _, _ in definitions}) == len(definitions), 'Duplicate watched PID')
    for name, pid, step, command in definitions:
        snapshot = process_snapshot(pid)
        if snapshot is not None:
            require(snapshot['uid'] == UID and snapshot['argv'] == command
                    and snapshot['job_id'] == JOB and snapshot['step_id'] == step,
                    'Watched process identity mismatch: '+name)
        watched[name] = {'pid': pid, 'step_id': step, 'command': command, 'initial_identity': snapshot}
    return watched


def alive_processes(watched):
    alive = []
    for name, proof in watched.items():
        current = process_snapshot(proof['pid'])
        if current is None:
            continue
        require(proof['initial_identity'] is not None and current == proof['initial_identity'],
                'Watched PID identity changed: '+name)
        alive.append(name)
    return alive


def validate_states(value, watched=None):
    for name, step in [('pipeline', PIPELINE_STEP), ('services', SERVICE_STEP), ('workers', WORKER_STEP)]:
        state = value[name]
        require(str(state.get('job_id')) == JOB and str(state.get('step_id')) == step,
                'Original '+name+' step identity changed')
    require(value['pipeline'].get('status') not in ('failed', 'interrupted'), 'Original pipeline failed or interrupted')
    require(value['services'].get('status') not in ('failed', 'needs_attention'), 'Original services failed')
    require(value['workers'].get('status') in ('running', 'complete', 'needs_attention')
            and value['workers'].get('expected_results') == 160
            and value['workers'].get('sa_execution_enabled') is False
            and value['workers'].get('external_api_enabled') is False
            and not value['workers'].get('error'), 'Original workers have an unexpected scope/state/error')
    require(all(w.get('exit_code') in (None, 0) for w in value['workers'].get('workers', [])),
            'A scientific worker exited with an error')
    if watched is not None:
        require(value['pipeline']['pid'] == watched['pipeline']['pid']
                and value['services']['pid'] == watched['services']['pid']
                and value['workers']['pid'] == watched['worker_supervisor']['pid'],
                'A supervisor was replaced while draining')
        rows = value['workers']['workers']
        require(len(rows) == 32 and {w['name'] for w in rows} == set(watched)-{
                'pipeline', 'services', 'worker_supervisor'}, 'Worker membership changed while draining')
        require(all(w['pid'] == watched[w['name']]['pid'] and w['command'] == watched[w['name']]['command']
                    for w in rows), 'A scientific worker was replaced while draining')


def ledger_summary(path, task):
    data = path.read_bytes()
    require(data.endswith(b'\n'), 'Truncated ledger: '+str(path))
    events = [json.loads(line) for line in data.splitlines()]
    require(events and all(events[0].get(k) == v for k, v in {
        'event': 'header', 'version': 1, 'accounting': 'actual_local_vllm_tokens',
        'external_api_enabled': False, 'unknown_outcome': 'retain_full_reservation'}.items()),
        'Ledger protocol mismatch')
    owner = [task['case_uid'], MODEL, task['method']]
    owners, calls, request_keys = [], {}, set()
    for event in events[1:]:
        kind = event.get('event')
        if kind == 'owner':
            require(event.get('owner') == owner and event.get('token_cap') == task['token_budget']
                    and not owners, 'Ledger owner/budget mismatch or duplicate')
            owners.append(event)
        elif kind == 'reserve':
            cid = event['call_id']
            require(owners and event.get('owner') == owner and cid not in calls
                    and event['request_key'] not in request_keys, 'Duplicate or foreign reservation')
            calls[cid] = {**event, 'status': 'reserved'}
            request_keys.add(event['request_key'])
        elif kind == 'finish':
            cid = event['call_id']
            require(cid in calls and calls[cid]['status'] == 'reserved', 'Unknown or duplicate settlement')
            calls[cid].update(event)
        elif kind == 'parse':
            require(event.get('call_id') in calls, 'Parse without reservation')
        else:
            raise RuntimeError('Unexpected baseline ledger event: '+str(kind))
    prompt = completion = 0
    for row in calls.values():
        require(row.get('status') == 'completed_with_usage' and not row.get('usage_issues')
                and not row.get('error_type'), 'Unsettled, unknown or mismatched ledger call')
        p, c, total = row.get('prompt_tokens'), row.get('completion_tokens'), row.get('actual_total_tokens')
        require(all(type(x) is int and x >= 0 for x in (p, c, total)) and p+c == total
                and p == row['input_tokens'] and c <= row['max_output_tokens'], 'Invalid settled token usage')
        prompt += p
        completion += c
    total = prompt+completion
    require(total <= task['token_budget'], 'Ledger exceeded the frozen arm budget')
    return {'calls': len(calls), 'completed_with_usage': len(calls), 'held_calls': 0,
            'usage_mismatch_calls': 0, 'prompt_tokens': prompt, 'completion_tokens': completion,
            'total_tokens': total, 'accounted_tokens': total}


def audit_results(root, tasks, protocol_hash, all_settled=False):
    by_key = {task_key(t): t for t in tasks}
    failure_files = list((root/'results').glob('*/*/*/failure.json'))
    require(not failure_files, 'Scientific failure.json exists; drain will not mask it')
    proofs = []
    keys = set()
    for path in sorted((root/'results').glob('*/*/*/final.json')):
        uid, method, model_key = path.parents[1].name, path.parent.name, path.parents[2].name
        key = uid+'__'+method
        require(model_key == 'qwen25' and key in by_key, 'Out-of-scope result')
        task, final = by_key[key], read(path)
        require(final.get('model_key') == 'qwen25' and final.get('model') == MODEL
                and final.get('case_uid') == uid and final.get('method') == method
                and final.get('protocol_sha256') == protocol_hash
                and final.get('token_budget') == task['token_budget']
                and final.get('completion_status') in ('complete', 'strict_experiment_failure'),
                'Final identity, protocol or completion status is invalid')
        actual = ledger_summary(path.parent/'ledger.jsonl', task)
        require(all(final.get('usage', {}).get(k) == v for k, v in actual.items()),
                'Final usage differs from its settled ledger')
        keys.add(key)
        proofs.append({'task': key, 'final_sha256': sha(path), 'ledger_sha256': sha(path.parent/'ledger.jsonl'),
                       'completion_status': final['completion_status'], 'usage': actual})
    if all_settled:
        for ledger in (root/'results').glob('*/*/*/ledger.jsonl'):
            key = ledger.parents[1].name+'__'+ledger.parent.name
            require(ledger.parents[2].name == 'qwen25' and key in keys,
                    'An unfinished arm has a ledger after every worker exited')
        for path in (root/'results').glob('*/*/*/attempt.json'):
            key = path.parents[1].name+'__'+path.parent.name
            require(path.parents[2].name == 'qwen25' and key in keys,
                    'An unfinished arm has an attempt after every worker exited')
    return {'final_results': len(proofs), 'remaining_arms': len(tasks)-len(proofs),
            'completed_tasks': sorted(keys), 'results': proofs,
            'held_calls': 0, 'usage_mismatch_calls': 0, 'infrastructure_failures': 0}


def open_ports():
    result = []
    for port in PORTS:
        with socket.socket() as connection:
            connection.settimeout(.25)
            if connection.connect_ex(('127.0.0.1', port)) == 0:
                result.append(port)
    return result


def terminal_ready(root, state, alive, held_count, final_count):
    if held_count != 160 or alive:
        return False
    workers, pipeline, services = state['workers'], state['pipeline'], state['services']
    if workers.get('status') not in ('complete', 'needs_attention'):
        return False
    if pipeline.get('status') not in ('complete', 'needs_attention') or services.get('status') != 'stopped':
        return False
    require(workers.get('running_workers') == 0 and all(w.get('exit_code') == 0 for w in workers['workers']),
            'Terminal workers are not all confirmed normal exits')
    require(workers.get('final_results') == final_count and pipeline.get('final_results') == final_count
            and pipeline.get('worker_terminal_status') == workers['status']
            and pipeline.get('own_services_stopped') is True, 'Terminal supervisor proof mismatch')
    require(not (root/'endpoints.json').exists() and not open_ports(), 'Old service endpoints/ports remain live')
    require(final_count == 160 or (workers['status'] == 'needs_attention'
            and pipeline['status'] == 'needs_attention'), 'Partial scope was incorrectly marked complete')
    return True


def run(root, output, context, locks):
    global STOP_SIGNAL
    tasks, protocol_hash, source_proofs = load_tasks(root)
    initial = states(root)
    validate_states(initial)
    watched = watch_processes(root, initial)
    started, deadline = now(), time.monotonic()+DEADLINE_SECONDS
    base = {'schema': 'qwen48_arm_drain_v1', 'started_at': started, 'context': context,
            'deadline_seconds': DEADLINE_SECONDS, 'poll_seconds': POLL_SECONDS,
            'source_sha256': source_proofs, 'protocol_sha256': protocol_hash,
            'watched_processes': watched, 'expected_results': 160, 'original_worker_count': 32,
            'scientific_model_calls': 0, 'signals_sent': 0, 'scientific_retries': 0,
            'sa_execution_enabled': False, 'existing_results_modified': False}
    save(output/'drain_initial.json', {**base, 'original_states': initial})
    while True:
        if STOP_SIGNAL is not None:
            raise InterruptedError('Drain interrupted; releasing claim locks permits surviving workers to continue. '
                                   'No worker is restarted and no scientific request is retried.')
        require(time.monotonic() < deadline, 'Three-hour drain deadline exceeded; no process will be signalled')
        held = locks.acquire_available()
        state = states(root)
        validate_states(state, watched)
        alive = alive_processes(watched)
        audit = audit_results(root, tasks, protocol_hash)
        progress = {**base, 'status': 'draining', 'updated_at': now(),
                    'claim_locks_held': held, 'held_tasks': sorted(locks.handles),
                    'unheld_tasks': [task_key(t) for t in tasks if task_key(t) not in locks.handles],
                    'current_alive_processes': alive,
                    'current_worker_count': sum(name.startswith('qwen25-') for name in alive),
                    'worker_supervisor_reported_running': state['workers'].get('running_workers'),
                    'final_results': audit['final_results'], 'remaining_arms': audit['remaining_arms'],
                    'pipeline_status': state['pipeline']['status'], 'service_status': state['services']['status'],
                    'worker_status': state['workers']['status']}
        save(output/'drain_status.json', progress)
        print(json.dumps({k: progress[k] for k in ('status', 'updated_at', 'claim_locks_held',
              'current_worker_count', 'final_results', 'remaining_arms', 'pipeline_status', 'service_status')}), flush=True)
        if terminal_ready(root, state, alive, held, audit['final_results']):
            require(all(sha(root/name) == expected for name, expected in source_proofs.items()),
                    'Scientific source, queue, budget or protocol changed during drain')
            audit = audit_results(root, tasks, protocol_hash, all_settled=True)
            receipt = {**base, 'status': 'drained', 'completed_at': now(),
                       'final_states': state, 'audit': audit, 'claim_locks_held_at_validation': held,
                       'all_original_processes_exited': True, 'old_service_ports_closed': True,
                       'endpoints_absent': True, 'claim_locks_release': 'on_normal_process_exit',
                       'partial_needs_attention_is_expected': audit['final_results'] < 160}
            save(output/'drained_receipt.json', receipt)
            save(output/'drain_status.json', {**progress, 'status': 'drained', 'completed_at': receipt['completed_at']})
            return receipt
        for _ in range(POLL_SECONDS):
            if STOP_SIGNAL is not None:
                break
            time.sleep(1)


def main():
    global STOP_SIGNAL
    context = environment_identity()
    os.umask(0o077)
    with (HERE/'drain_controller.lock').open('a') as controller:
        fcntl.flock(controller, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not (HERE/'drain_status.json').exists() and not (HERE/'drained_receipt.json').exists(),
                'Existing drain state requires explicit review; no automatic repeat')
        def interrupted(signum, frame):
            global STOP_SIGNAL
            STOP_SIGNAL = signum
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        locks = None
        receipt = None
        result = 1
        try:
            tasks, _, _ = load_tasks(ROOT)
            locks = ClaimLocks(ROOT, tasks)
            receipt = run(ROOT, HERE, context, locks)
            result = 0
        except BaseException as error:
            status = read(HERE/'drain_status.json') if (HERE/'drain_status.json').exists() else {'context': context}
            status.update(status='interrupted' if isinstance(error, InterruptedError) else 'failed',
                          failed_at=now(), error_type=type(error).__name__, error=str(error),
                          signals_sent=0, scientific_model_calls=0, scientific_retries=0,
                          signal_received=STOP_SIGNAL,
                          release_effect='Only drain-owned claim locks are released. Surviving workers may continue; '
                                         'no workers or scientific requests are restarted or retried.')
            save(HERE/'drain_status.json', status)
            print(json.dumps({'status': status['status'], 'error': str(error)}), flush=True)
            result = 130 if isinstance(error, InterruptedError) else 1
        finally:
            if locks is not None:
                locks.close()
        status = read(HERE/'drain_status.json')
        status.update(claim_locks_held=0, claim_locks_released_at=now())
        save(HERE/'drain_status.json', status)
        if receipt is not None:
            receipt.update(claim_locks_released_at=status['claim_locks_released_at'], claim_locks_release='confirmed')
            save(HERE/'drained_receipt.json', receipt)
        return result


if __name__ == '__main__':
    raise SystemExit(main())

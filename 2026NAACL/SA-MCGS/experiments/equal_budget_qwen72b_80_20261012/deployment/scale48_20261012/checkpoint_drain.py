#!/usr/bin/env python3
"""Checkpoint only fully settled request prefixes, prove replay, then retire workers.

No scientific source, ledger, response, result, budget, or prompt is changed.
Only identity-verified original workers receive STOP/CONT and, after a frozen
offline replay proof, TERM/CONT. On failure every surviving stopped worker is
continued. The original pipeline owns service cleanup.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
from urllib.request import ProxyHandler, build_opener

import drain as d

ROOT, HERE = d.ROOT, d.HERE
STOP = None
REPLAY_TIMEOUT = 20*60
METRIC = re.compile(r'^(vllm:num_requests_(?:running|waiting))(?:\{.*\})?\s+([^\s]+)')


def stop_handler(signum, frame):
    global STOP
    STOP = signum


def check_stop(deadline):
    if STOP is not None:
        raise InterruptedError('Checkpoint interrupted; all surviving paused workers will be continued without retries')
    d.require(time.monotonic() < deadline, 'Three-hour checkpoint deadline exceeded')


def proc(pid):
    identity = d.process_snapshot(pid)
    if identity is None:
        return None
    try:
        status = (Path('/proc')/str(pid)/'status').read_text()
        fields = dict(line.split(':', 1) for line in status.splitlines() if ':' in line)
        state = fields['State'].strip().split()[0]
        default_term = not ((int(fields['SigIgn'].strip(), 16) | int(fields['SigCgt'].strip(), 16))
                            & (1 << (signal.SIGTERM-1)))
        return {'identity': identity, 'state': state, 'default_sigterm': default_term}
    except FileNotFoundError:
        return None


def capture_watched(state):
    watched = {}
    definitions = [('pipeline', state['pipeline']['pid'], d.PIPELINE_STEP, ROOT/'deployment/pipeline_supervisor.py'),
                   ('services', state['services']['pid'], d.SERVICE_STEP, ROOT/'deployment/service_supervisor.py'),
                   ('worker_supervisor', state['workers']['pid'], d.WORKER_STEP, ROOT/'worker_supervisor.py')]
    names = {f'qwen25-{r}_worker{i}' for r in range(4) for i in range(8)}
    workers = state['workers'].get('workers', [])
    d.require(len(workers) == 32 and {w['name'] for w in workers} == names, 'Expected original 32 worker identities')
    for name, pid, step, source in definitions:
        current = proc(pid)
        d.require(current is not None, 'Original supervisor is not alive: '+name)
        identity = current['identity']
        command = identity['argv']
        d.require(command in ([d.PYTHON, '-B', str(source)], [d.PYTHON, '-B', source.name])
                  and identity['uid'] == d.UID and identity['job_id'] == d.JOB
                  and identity['step_id'] == step, 'Original supervisor identity mismatch: '+name)
        watched[name] = {'pid': pid, 'step_id': step, 'command': command, 'initial_identity': identity}
    for row in workers:
        name, pid = row['name'], row['pid']
        replica, index = name.split('_worker')
        command = [d.PYTHON, '-B', str(ROOT/'runner.py'), '--replica-id', replica, '--worker-index', index]
        d.require(row.get('command') == command and row.get('model') == 'qwen25', 'Worker command changed')
        current = proc(pid)
        if current is not None:
            identity = current['identity']
            d.require(identity['uid'] == d.UID and identity['argv'] == command
                      and identity['job_id'] == d.JOB and identity['step_id'] == d.WORKER_STEP
                      and current['default_sigterm'] and current['state'] not in ('T', 't'),
                      'Worker identity/signal disposition is unsuitable: '+name)
        else:
            d.require(row.get('exit_code') == 0, 'A disappeared worker lacks a normal-exit proof')
            identity = None
        watched[name] = {'pid': pid, 'step_id': d.WORKER_STEP, 'command': command, 'initial_identity': identity}
    d.require(len({v['pid'] for v in watched.values()}) == len(watched), 'Duplicate watched PID')
    return watched


def verify_worker(proof, allow_absent=False):
    current = proc(proof['pid'])
    if current is None and allow_absent:
        return None
    d.require(current is not None and current['identity'] == proof['initial_identity']
              and current['default_sigterm'], 'Worker identity/default SIGTERM disposition changed')
    return current


def send_verified(proof, signum, require_stopped=False):
    current = verify_worker(proof, allow_absent=signum == signal.SIGCONT)
    if current is None:
        return False
    if require_stopped:
        d.require(current['state'] == 'T', 'Worker is not stopped at the validated checkpoint')
    os.kill(proof['pid'], signum)
    return True


def ledger_cache_proof(path, task):
    summary = d.ledger_summary(path, task)
    events = [json.loads(line) for line in path.read_bytes().splitlines()]
    calls = {}
    for event in events[1:]:
        if event['event'] == 'reserve':
            calls[event['call_id']] = dict(event)
        elif event['event'] == 'finish':
            calls[event['call_id']].update(event)
    caches = {}
    for cid, row in calls.items():
        cache = Path(row['cache_file'])
        cache = cache if cache.is_absolute() else path.parent/cache
        d.require(cache.resolve() == cache and cache.is_relative_to(path.parent/'calls'), 'Unexpected response cache path')
        value = d.read(cache)
        d.require(value.get('call_id') == cid and value.get('request_hash') == row['request_hash']
                  and isinstance(value.get('result'), dict)
                  and d.digest(value['result']) == row.get('response_sha256'), 'Response cache identity/hash mismatch')
        usage = value['result'].get('usage', {})
        d.require(value['result'].get('model') == d.MODEL
                  and usage.get('prompt_tokens') == row['prompt_tokens']
                  and usage.get('completion_tokens') == row['completion_tokens']
                  and usage.get('total_tokens') == row['actual_total_tokens'], 'Cached usage differs from ledger')
        caches[str(cache.relative_to(ROOT))] = d.sha(cache)
    return {'task': d.task_key(task), 'case_uid': task['case_uid'], 'method': task['method'],
            'ledger_sha256': d.sha(path), 'cache_sha256': caches,
            'settled_calls': summary['calls'], 'held_calls': 0, 'usage_mismatch_calls': 0, 'usage': summary}


def all_result_hashes():
    return {str(p.relative_to(ROOT)): d.sha(p) for p in sorted((ROOT/'results').rglob('*')) if p.is_file()}


def frozen_audit(tasks, protocol_hash):
    completed = d.audit_results(ROOT, tasks, protocol_hash)
    by_key = {d.task_key(t): t for t in tasks}
    partial, ledgers = [], []
    for path in sorted((ROOT/'results').glob('*/*/*/ledger.jsonl')):
        key = path.parents[1].name+'__'+path.parent.name
        d.require(path.parents[2].name == 'qwen25' and key in by_key, 'Out-of-scope ledger')
        proof = ledger_cache_proof(path, by_key[key])
        ledgers.append(proof)
        if not (path.parent/'final.json').exists():
            partial.append(proof)
    return {**completed, 'partial_arms': partial, 'all_ledger_proofs': ledgers,
            'all_result_files_sha256': all_result_hashes()}


def worker_task(name, by_key):
    path = ROOT/'execution'/(name+'_status.json')
    if not path.exists():
        return None
    state = d.read(path)
    uid, method = state.get('current_case_uid'), state.get('current_method')
    key = str(uid)+'__'+str(method)
    return by_key.get(key)


def idle_metrics():
    opener = build_opener(ProxyHandler({}))
    readings = []
    for port in d.PORTS:
        with opener.open(f'http://127.0.0.1:{port}/metrics', timeout=5) as response:
            body = response.read()
        values = {'vllm:num_requests_running': [], 'vllm:num_requests_waiting': []}
        for line in body.decode().splitlines():
            match = METRIC.match(line)
            if match:
                values[match[1]].append(float(match[2]))
        d.require(all(values.values()), 'Service request metrics are missing')
        if any(x != 0 for group in values.values() for x in group):
            return None
        readings.append({'port': port, 'readings': values, 'metrics_sha256': __import__('hashlib').sha256(body).hexdigest()})
    return readings


def run_replay(deadline):
    script = HERE/'replay_preflight.py'
    output = HERE/'replay_preflight_frozen.json'
    snapshot = HERE/'replay_snapshots_frozen'
    d.require(script.exists() and not output.exists() and not snapshot.exists(), 'Missing replay program or prior frozen replay state')
    command = [d.PYTHON, '-B', str(script), '--output', str(output), '--snapshot-dir', str(snapshot)]
    child = None
    with (HERE/'replay_preflight_frozen.log').open('ab', buffering=0) as log:
        try:
            child = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, start_new_session=True)
            expires = min(deadline, time.monotonic()+REPLAY_TIMEOUT)
            while child.poll() is None:
                check_stop(expires)
                time.sleep(.25)
            d.require(child.returncode == 0, 'Frozen offline replay failed; no scientific worker will be terminated')
        finally:
            if child is not None and child.poll() is None:
                child.terminate()  # Only our own offline replay subprocess, never a scientific worker.
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=10)
    return d.read(output), output


def validate_replay(proof, audit, protocol_hash):
    d.require(proof.get('status') == 'passed' and proof.get('all_active_arms_verified') is True
              and proof.get('provider_calls') == 0 and proof.get('protocol_sha256') == protocol_hash,
              'Frozen replay did not prove zero-call replay under the existing protocol')
    expected = {(r['case_uid'], r['method']): r for r in audit['partial_arms']}
    actual = proof.get('active_arm_identities', [])
    d.require(len(actual) == len(expected) and {(r['case_uid'], r['method']) for r in actual} == set(expected),
              'Replay proof does not cover every partial arm')
    for row in actual:
        old = expected[(row['case_uid'], row['method'])]
        d.require(row.get('source_ledger_sha256') == old['ledger_sha256']
                  and row.get('omitted_reservations') == [] and row.get('omitted_reservations_count') == 0
                  and row.get('ignored_partial_bytes') == 0
                  and row.get('source_cache_sha256') == old['cache_sha256']
                  and row.get('prefix_calls') == old['settled_calls'],
                  'Replay proof omitted calls or belongs to an older ledger snapshot')


def terminal_states(watched, signals, audit):
    state = d.states(ROOT)
    for name, step in [('pipeline', d.PIPELINE_STEP), ('services', d.SERVICE_STEP), ('workers', d.WORKER_STEP)]:
        d.require(str(state[name].get('job_id')) == d.JOB and str(state[name].get('step_id')) == step,
                  'Original supervisor step changed')
    rows = state['workers']['workers']
    sent = {r['worker'] for r in signals if r.get('sigterm_sent_at')}
    d.require(len(rows) == 32 and {r['name'] for r in rows} == set(watched)-{
        'pipeline', 'services', 'worker_supervisor'}, 'Original worker set changed')
    for row in rows:
        d.require(row['pid'] == watched[row['name']]['pid'] and row.get('exit_code') in (None, 0, -15),
                  'Unexpected worker identity or exit code')
        d.require(row.get('exit_code') != -15 or row['name'] in sent, 'Unplanned SIGTERM exit')
    d.require(state['pipeline']['status'] not in ('failed', 'interrupted')
              and state['services']['status'] not in ('failed', 'needs_attention'), 'Original cleanup failed')
    alive = d.alive_processes(watched)
    if alive or state['pipeline']['status'] not in ('complete', 'needs_attention'):
        return None
    d.require(state['services']['status'] == 'stopped' and state['workers']['running_workers'] == 0
              and state['workers']['status'] in ('complete', 'needs_attention')
              and state['pipeline'].get('own_services_stopped') is True
              and state['pipeline'].get('worker_terminal_status') == state['workers']['status']
              and state['pipeline'].get('final_results') == audit['final_results']
              and state['workers'].get('final_results') == audit['final_results']
              and not state['workers'].get('error')
              and not (ROOT/'endpoints.json').exists() and not d.open_ports(), 'Cleanup is not fully confirmed')
    return state


def execute(context, locks, paused, signals, status):
    tasks, protocol_hash, source_hashes = d.load_tasks(ROOT)
    by_key = {d.task_key(t): t for t in tasks}
    initial = d.states(ROOT)
    d.validate_states(initial)
    watched = capture_watched(initial)
    deadline = time.monotonic()+d.DEADLINE_SECONDS
    status.update(schema='qwen48_request_checkpoint_v1', context=context, started_at=d.now(),
                  source_sha256=source_hashes, protocol_sha256=protocol_hash, watched_processes=watched,
                  planned_signal_termination=True, scientific_model_calls=0, scientific_retries=0,
                  existing_results_modified=False, expected_results=160, original_worker_count=32,
                  original_states=initial, deadline_seconds=d.DEADLINE_SECONDS)
    d.save(HERE/'checkpoint_initial.json', status)
    last_saved = 0
    workers = {name: item for name, item in watched.items() if name.startswith('qwen25-')}
    while len(paused) < 32:
        check_stop(deadline)
        locks.acquire_available()
        d.validate_states(d.states(ROOT), watched)
        for name, item in workers.items():
            check_stop(deadline)
            if name in paused:
                continue
            current = verify_worker(item, allow_absent=True)
            if current is None:
                row = next(r for r in d.read(ROOT/'execution/status.json')['workers'] if r['name'] == name)
                d.require(row.get('exit_code') == 0, 'Worker exited without normal completion')
                paused[name] = {**item, 'already_exited': True}
                continue
            task = worker_task(name, by_key)
            if task is None:
                continue
            ledger = ROOT/'results/qwen25'/task['case_uid']/task['method']/'ledger.jsonl'
            # A running read is only a cheap hint. The authoritative audit occurs after T.
            try:
                data = ledger.read_bytes()
                last = json.loads(data.splitlines()[-1])
                if not data.endswith(b'\n') or last.get('event') not in ('finish', 'parse'):
                    continue
                d.ledger_summary(ledger, task)  # Cheap pre-read: never routinely STOP an in-flight call.
            except (RuntimeError, FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
                continue
            send_verified(item, signal.SIGSTOP)
            paused[name] = {**item, 'already_exited': False, 'stop_sent_at': d.now(), 'boundary_verified': False}
            expires = time.monotonic()+2
            while True:
                current = verify_worker(item)
                if current['state'] == 'T':
                    break
                d.require(time.monotonic() < expires, 'SIGSTOP did not reach T state')
                time.sleep(.002)
            try:
                fresh_task = worker_task(name, by_key)
                d.require(fresh_task is not None, 'Worker has no current arm')
                fresh_ledger = ROOT/'results/qwen25'/fresh_task['case_uid']/fresh_task['method']/'ledger.jsonl'
                proof = ledger_cache_proof(fresh_ledger, fresh_task)
            except (RuntimeError, FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
                send_verified(item, signal.SIGCONT, require_stopped=True)
                del paused[name]
                continue
            paused[name].update(boundary_verified=True, boundary_task=proof['task'], boundary_ledger_sha256=proof['ledger_sha256'])
        if time.monotonic()-last_saved >= 15 or len(paused) == 32:
            status.update(status='finding_request_boundaries', updated_at=d.now(),
                          paused_worker_count=sum(not r['already_exited'] for r in paused.values()),
                          naturally_exited_worker_count=sum(r['already_exited'] for r in paused.values()),
                          accounted_worker_count=len(paused), claim_locks_held=len(locks.handles), frozen_workers=paused)
            d.save(HERE/'checkpoint_status.json', status)
            print(json.dumps({k: status[k] for k in ('status', 'updated_at', 'paused_worker_count', 'accounted_worker_count')}), flush=True)
            last_saved = time.monotonic()
        time.sleep(.02)
    for item in paused.values():
        if not item['already_exited']:
            d.require(verify_worker(item)['state'] == 'T', 'Paused worker resumed unexpectedly')
    audit = frozen_audit(tasks, protocol_hash)
    idle_deadline = time.monotonic()+60
    while True:
        check_stop(deadline)
        metrics = idle_metrics()
        if metrics is not None:
            break
        d.require(time.monotonic() < idle_deadline, 'Services still have requests after all workers were checkpointed')
        time.sleep(1)
    status.update(status='frozen_replay_check', frozen_audit=audit, zero_active_requests=metrics, updated_at=d.now())
    d.save(HERE/'checkpoint_ready.json', status)
    d.save(HERE/'checkpoint_status.json', status)
    replay, replay_path = run_replay(deadline)
    validate_replay(replay, audit, protocol_hash)
    for item in paused.values():
        if not item['already_exited']:
            d.require(verify_worker(item)['state'] == 'T', 'Worker changed during frozen replay')
    d.require(frozen_audit(tasks, protocol_hash) == audit, 'Scientific state changed during frozen replay')
    d.require(idle_metrics() is not None, 'Requests appeared during frozen replay')
    d.require(all(d.sha(ROOT/name) == value for name, value in source_hashes.items()), 'Frozen science or queue source changed')
    check_stop(deadline)
    replay_proof = {'path': str(replay_path.relative_to(ROOT)), 'sha256': d.sha(replay_path),
                    'status': 'passed', 'provider_calls': 0}
    status.update(status='termination_intent', replay_proof=replay_proof, audit=audit,
                  frozen_workers=paused, signals=signals, updated_at=d.now())
    d.save(HERE/'checkpoint_termination_intent.json', status)
    for name, item in paused.items():
        if item['already_exited']:
            continue
        check_stop(deadline)
        d.require(verify_worker(item)['state'] == 'T', 'Worker left its checkpoint before TERM')
        event = {'worker': name, 'pid': item['pid'], 'identity': item['initial_identity'], 'sigterm_intent_at': d.now()}
        signals.append(event)
        d.save(HERE/'checkpoint_signals.json', {'signals': signals, 'replay_proof': replay_proof})
        send_verified(item, signal.SIGTERM, require_stopped=True)
        event['sigterm_sent_at'] = d.now()
        d.save(HERE/'checkpoint_signals.json', {'signals': signals, 'replay_proof': replay_proof})
        send_verified(item, signal.SIGCONT)
        event['sigcont_sent_at'] = d.now()
        d.save(HERE/'checkpoint_signals.json', {'signals': signals, 'replay_proof': replay_proof})
    status.update(status='waiting_for_original_cleanup', updated_at=d.now(), signals=signals)
    d.save(HERE/'checkpoint_status.json', status)
    while True:
        check_stop(deadline)
        locks.acquire_available()
        final_states = terminal_states(watched, signals, audit)
        if final_states is not None:
            break
        time.sleep(1)
    d.require(len(locks.handles) == 160, 'Not all original claims were released')
    d.require(frozen_audit(tasks, protocol_hash) == audit, 'Scientific results changed during planned worker termination')
    receipt = {**status, 'status': 'drained', 'completed_at': d.now(), 'audit': audit,
               'final_states': final_states, 'replay_proof': replay_proof, 'signals': signals,
               'all_original_processes_exited': True, 'old_service_ports_closed': True,
               'endpoints_absent': True, 'old_services_stopped': True, 'zero_live_scientific_processes': True,
               'claim_locks_held_at_validation': 160, 'claim_locks_release': 'on_normal_process_exit',
               'state_files_sha256': {name: d.sha(ROOT/name) for name in (
                   'deployment/pipeline_status.json', 'deployment/service_state.json', 'execution/status.json')}}
    d.save(HERE/'drained_receipt.json', receipt)
    return receipt


def main():
    context = d.environment_identity()
    os.umask(0o077)
    with (HERE/'checkpoint_controller.lock').open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        d.require(not (HERE/'checkpoint_status.json').exists() and not (HERE/'drained_receipt.json').exists(),
                  'Prior checkpoint state needs explicit reconciliation; no automatic retry')
        signal.signal(signal.SIGTERM, stop_handler)
        signal.signal(signal.SIGINT, stop_handler)
        locks, paused, signals, status, receipt = None, {}, [], {'context': context}, None
        code = 1
        try:
            tasks, _, _ = d.load_tasks(ROOT)
            locks = d.ClaimLocks(ROOT, tasks)
            receipt = execute(context, locks, paused, signals, status)
            code = 0
        except BaseException as error:
            status.update(status='interrupted' if isinstance(error, InterruptedError) else 'failed', failed_at=d.now(),
                          error_type=type(error).__name__, error=str(error), signal_received=STOP,
                          partial_termination=bool(signals), scientific_model_calls=0, scientific_retries=0)
            code = 130 if isinstance(error, InterruptedError) else 1
        finally:
            continuations = []
            for name, item in paused.items():
                if item['already_exited']:
                    continue
                try:
                    current = verify_worker(item, allow_absent=True)
                    if current is not None and current['state'] == 'T':
                        send_verified(item, signal.SIGCONT, require_stopped=True)
                        continuations.append({'worker': name, 'pid': item['pid'], 'continued_at': d.now()})
                except BaseException as error:
                    continuations.append({'worker': name, 'pid': item['pid'], 'error': str(error)})
                    code = 1
            status.update(cleanup_continuations=continuations, claim_locks_held=0, claim_locks_released_at=d.now())
            if locks is not None:
                locks.close()
            if receipt is not None and code == 0:
                receipt.update(claim_locks_release='confirmed', claim_locks_released_at=status['claim_locks_released_at'])
                d.save(HERE/'drained_receipt.json', receipt)
                status.update(status='drained', completed_at=receipt['completed_at'])
            elif receipt is not None:
                receipt.update(status='failed_cleanup', error='A surviving worker could not be safely continued')
                d.save(HERE/'drained_receipt.json', receipt)
            d.save(HERE/'checkpoint_status.json', status)
        print(json.dumps({'status': status['status'], 'exit_code': code, 'error': status.get('error')}), flush=True)
        return code


if __name__ == '__main__':
    raise SystemExit(main())

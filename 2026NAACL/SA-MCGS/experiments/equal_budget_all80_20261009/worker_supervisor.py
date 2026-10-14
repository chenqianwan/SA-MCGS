#!/usr/bin/env python3
"""Persistent, adjustable arm-worker pool over the authorized 480-task queue."""
import collections
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def save(path, value):
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def read(path):
    return json.loads(path.read_text())


def configured_workers():
    config = read(ROOT/'execution_config.json')
    limits = config['workers_per_replica']
    if set(limits) != {'llama', 'kimi', 'qwen35'} or any(type(v) is not int or not 1 <= v <= 16 for v in limits.values()):
        raise ValueError('Expected per-model worker limits in 1..16')
    return limits


def main():
    scope = read(ROOT/'run_scope.json')
    if (scope.get('scope_schema') != 'historical_sa_baselines_v1' or scope.get('cases_per_model') != 80
            or len(set(scope['case_uids'])) != 80 or scope.get('expected_results') != 480
            or scope.get('execution_methods') != ['lea', 'full-scc'] or scope.get('stop_after_scope') is not True):
        raise ValueError('User-authorized full scope must be exactly 480 baseline arms')
    run = ROOT/'execution'
    run.mkdir(exist_ok=True)
    lock = (run/'supervisor.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = {'status': 'waiting_for_model_services', 'started_unix': time.time(),
             'job_id': os.environ.get('SLURM_JOB_ID'), 'step_id': os.environ.get('SLURM_STEP_ID'),
             'pid': os.getpid(), 'expected_results': 480, 'sa_execution_enabled': False,
             'external_api_enabled': False, 'workers': []}
    children = {}
    def update(**items):
        state.update(items, updated_unix=time.time())
        save(run/'status.json', state)
    update()
    interrupted = False
    def stop(signum, frame):
        nonlocal interrupted
        interrupted = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    deadline = time.time()+2*3600
    while not (ROOT/'endpoints.json').exists():
        if interrupted or time.time() > deadline:
            update(status='interrupted' if interrupted else 'service_wait_timeout')
            return 1
        time.sleep(5)
    endpoints = read(ROOT/'endpoints.json')
    replicas = endpoints['replicas']
    counts = collections.Counter(r['model_key'] for r in replicas)
    if counts != {'kimi': 4, 'llama': 2, 'qwen35': 2} or len({r['id'] for r in replicas}) != 8:
        raise ValueError('Expected four Kimi, two Llama and two Qwen GPU replicas')
    update(status='starting_workers', replica_counts=dict(counts))
    try:
        while not interrupted:
            limits = configured_workers()
            # Add slots without restarting any existing arm. Completed slots never auto-retry.
            for replica in replicas:
                for index in range(limits[replica['model_key']]):
                    name = f"{replica['id']}_worker{index}"
                    if name in children:
                        continue
                    log = (run/f'{name}.log').open('ab', buffering=0)
                    command = [sys.executable, '-B', str(ROOT/'runner.py'),
                               '--replica-id', replica['id'], '--worker-index', str(index)]
                    child = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                             start_new_session=True, stdin=subprocess.DEVNULL)
                    children[name] = (child, log)
                    state['workers'].append({'name': name, 'model': replica['model_key'],
                                             'pid': child.pid, 'exit_code': None, 'command': command})
                    time.sleep(.25)
            for entry in state['workers']:
                entry['exit_code'] = children[entry['name']][0].poll()
            groups = collections.Counter()
            for p in (ROOT/'results').glob('*/*/*/final.json'):
                row = read(p)
                if row['method'] not in scope['execution_methods'] or row['case_uid'] not in scope['case_uids']:
                    raise ValueError('Out-of-scope result')
                groups[(row['model_key'], row['method'], row['completion_status'])] += 1
            final_count = sum(groups.values())
            update(status='running', workers_per_replica=limits, final_results=final_count,
                   running_workers=sum(e['exit_code'] is None for e in state['workers']),
                   result_groups=[{'model':k[0], 'method':k[1], 'status':k[2], 'count':v} for k,v in sorted(groups.items())])
            if all(child.poll() is not None for child, _ in children.values()):
                failed = any(child.returncode != 0 for child, _ in children.values())
                report = subprocess.run([sys.executable, '-B', str(ROOT/'report_results.py')], cwd=ROOT)
                failed = failed or report.returncode != 0 or final_count != 480
                failed = failed or any(k[2] not in ('complete', 'strict_experiment_failure') for k in groups)
                update(status='needs_attention' if failed else 'complete', ended_unix=time.time())
                return 1 if failed else 0
            time.sleep(15)
        update(status='interrupted')
        return 130
    finally:
        for child, log in children.values():
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
            log.close()


if __name__ == '__main__':
    raise SystemExit(main())

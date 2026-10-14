#!/usr/bin/env python3
"""Persistent node-local case workers; GPU servers have a separate supervisor."""
from __future__ import annotations
import argparse
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
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers-per-replica', type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.workers_per_replica <= 16:
        raise ValueError('workers-per-replica must be 1..16')
    scope = json.loads((ROOT/'run_scope.json').read_text())
    if (scope.get('cases_per_model') != 10 or len(set(scope.get('case_uids', []))) != 10
            or scope.get('expected_results') != 90 or scope.get('stop_after_scope') is not True):
        raise ValueError('User authorized this stage for exactly ten cases per model')
    expected = scope['expected_results']
    run = ROOT/'execution'
    run.mkdir(exist_ok=True)
    lock = (run/'supervisor.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = {'status': 'waiting_for_model_services', 'started_unix': time.time(),
             'job_id': os.environ.get('SLURM_JOB_ID'), 'pid': os.getpid(),
             'workers_per_replica': args.workers_per_replica, 'expected_results': expected,
             'scope': scope,
             'external_api_enabled': False, 'workers': []}
    def update(**values):
        state.update(values, updated_unix=time.time())
        save(run/'status.json', state)
    update()
    deadline = time.time() + 24*3600
    while not (ROOT/'endpoints.json').exists():
        if time.time() > deadline:
            update(status='services_wait_timeout')
            return 1
        time.sleep(10)
    endpoints = json.loads((ROOT/'endpoints.json').read_text())
    replicas = endpoints['replicas']
    if len(replicas) != 8:
        raise ValueError('Expected all eight replica endpoints')
    children = []
    interrupted = False
    def stop(signum, frame):
        nonlocal interrupted
        interrupted = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for replica in replicas:
            same_model = sorted([r for r in replicas if r['model_key'] == replica['model_key']], key=lambda r: r['id'])
            ordinal = next(i for i, r in enumerate(same_model) if r['id'] == replica['id'])
            assigned = sum(i % len(same_model) == ordinal for i in range(scope['cases_per_model']))
            for index in range(min(args.workers_per_replica, assigned)):
                name = f"{replica['id']}_worker{index}"
                log = (run/f'{name}.log').open('a')
                cmd = [sys.executable, '-B', str(ROOT/'runner.py'), '--replica-id', str(replica['id']),
                       '--worker-index', str(index), '--workers-per-replica', str(args.workers_per_replica)]
                child = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=True)
                children.append((child, log))
                state['workers'].append({'name': name, 'pid': child.pid, 'command': cmd, 'exit_code': None})
                # Stagger imports to reduce shared-filesystem bursts.
                time.sleep(.25)
        update(status='running')
        while True:
            for entry, (child, _) in zip(state['workers'], children):
                entry['exit_code'] = child.poll()
            final_count = len(list((ROOT/'results').glob('*/*/*/final.json')))
            update(final_results=final_count)
            if interrupted:
                update(status='interrupted')
                return 130
            if all(child.poll() is not None for child, _ in children):
                failed = any(child.returncode != 0 for child, _ in children)
                report = subprocess.run([sys.executable, '-B', str(ROOT/'report_results.py')], cwd=ROOT)
                failed = failed or report.returncode != 0
                update(status='needs_attention' if failed or final_count != expected else 'complete',
                       ended_unix=time.time())
                return 1 if failed or final_count != expected else 0
            time.sleep(15)
    finally:
        for child, log in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
            log.close()


if __name__ == '__main__':
    raise SystemExit(main())

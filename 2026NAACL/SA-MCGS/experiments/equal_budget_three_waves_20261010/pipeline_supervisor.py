#!/usr/bin/env python3
"""Run exactly two further full waves, with independent per-model advancement."""
from __future__ import annotations
import collections
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from wave_audit import audit_model

ROOT = Path(__file__).resolve().parent
MODELS = ('llama', 'kimi', 'qwen35')


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.tmp')
    with tmp.open('w') as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def lock_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        handle.close()
        raise
    return handle


def workers_finished(entries, expected):
    return (len(entries) == expected and all(type(x.get('exit_code')) is int
                                            and x['exit_code'] == 0 for x in entries))


def gate(audit, entries, expected):
    return audit.get('complete') is True and workers_finished(entries, expected)


def validate(manifest):
    if (manifest['total_waves'] != 3 or manifest['stop_after_wave'] != 3
            or manifest['expected_baseline_arms_total'] != 1440
            or manifest['sa_rerun_enabled'] is not False):
        raise ValueError('Expected exactly three full waves and fixed historical SA')
    waves = [(ROOT.parent/name).resolve() for name in manifest['wave_dirs']]
    if len(waves) != 3 or len(set(waves)) != 3:
        raise ValueError('Wave directories must be distinct')
    endpoints = read(waves[0]/'endpoints.json')
    if endpoints['job_id'] != '415747' or endpoints['hostname'] != 'dgx-061':
        raise ValueError('Unexpected model service allocation')
    replicas = endpoints['replicas']
    if (collections.Counter(r['model_key'] for r in replicas) != {'llama': 2, 'kimi': 4, 'qwen35': 2}
            or len(set(r['id'] for r in replicas)) != 8):
        raise ValueError('Expected eight distinct model replicas')
    if manifest['workers_per_replica'] != {'llama': 10, 'kimi': 16, 'qwen35': 16}:
        raise ValueError('Unexpected worker limits')
    scope0 = read(waves[0]/'run_scope.json')
    source_names = ('runner.py', 'science_support.py', 'budget_client.py', 'methods_full.py',
                    'report_results.py', 'science/base_launcher.py', 'science/repo/bundle_manifest.json')
    for i, wave in enumerate(waves):
        scope = read(wave/'run_scope.json')
        if scope['case_uids'] != scope0['case_uids'] or scope['expected_results'] != 480:
            raise ValueError('Wave cases differ')
        refhash = hashlib.sha256((wave/'historical_sa_reference.json').read_bytes()).hexdigest()
        if refhash != manifest['historical_sa_reference_sha256']:
            raise ValueError('Historical SA reference changed')
        if read(wave/'endpoints.json') != endpoints:
            raise ValueError('Wave model services differ')
        if i:
            if scope.get('wave_id') != i+1 or scope.get('repeat_group') != manifest['group_id']:
                raise ValueError('Missing unique wave identity')
            for name in source_names:
                if (wave/name).read_bytes() != (waves[0]/name).read_bytes():
                    raise ValueError('Scientific source differs: '+name)
            prep = read(wave/'preflight/runner_prepare.json')
            if prep.get('status') != 'passed' or prep.get('model_calls') != 0:
                raise ValueError('Missing offline preparation')
            # This launcher never silently resumes an ambiguous interrupted wave.
            if any((wave/'results').glob('*/*/*/final.json')) or any((wave/'execution').glob('*worker*.log')):
                raise ValueError('New wave already has runtime artifacts; inspect before relaunch')
    return waves, replicas


def main():
    os.umask(0o077)
    if os.environ.get('SLURM_JOB_ID') != '415747':
        raise RuntimeError('Run only inside the existing authorized allocation')
    run = ROOT/'execution'
    run.mkdir(exist_ok=True)
    locks = []
    try:
        locks.append(lock_file(run/'supervisor.lock'))
        if any(run.glob('launch_wave*.json')):
            raise RuntimeError('Prior launch receipt exists; refusing automatic relaunch')
        manifest = read(ROOT/'manifest.json')
        waves, replicas = validate(manifest)
        # Excludes a whole-wave supervisor from sharing either new wave.
        for wave in waves[1:]:
            locks.append(lock_file(wave/'execution/supervisor.lock'))
    except BaseException:
        for handle in locks:
            handle.close()
        raise
    state = {'status': 'running', 'started_unix': time.time(), 'pid': os.getpid(),
             'job_id': os.environ['SLURM_JOB_ID'], 'step_id': os.environ.get('SLURM_STEP_ID'),
             'expected_results': 1440, 'sa_execution_enabled': False, 'external_api_enabled': False,
             'models': {m: {'wave': 1, 'state': 'waiting_for_previous_workers'} for m in MODELS}}
    children = {}  # (wave index, model) -> [(entry, Popen, log)]
    audits, reported = {}, set()
    interrupted = False
    def stop(signum, frame):
        nonlocal interrupted
        interrupted = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def entries_for(i, model):
        if i == 0:
            return [e for e in read(waves[0]/'execution/status.json')['workers'] if e['model'] == model]
        return [e for e, _, _ in children.get((i, model), [])]

    def launch(i, model):
        receipt_path = run/f'launch_wave{i+1}_{model}.json'
        if receipt_path.exists():
            raise RuntimeError('Duplicate or ambiguous launch: '+receipt_path.name)
        if (waves[i]/'results'/model).exists():
            raise RuntimeError('New model-wave contains prior runtime data')
        receipt = {'wave': i+1, 'model': model, 'state': 'intent', 'created_unix': time.time(), 'workers': []}
        save(receipt_path, receipt)  # Persist authorization boundary before spawning.
        group = children[(i, model)] = []
        for replica in replicas:
            if replica['model_key'] != model:
                continue
            for index in range(manifest['workers_per_replica'][model]):
                name = f"{replica['id']}_worker{index}"
                command = [sys.executable, '-B', str(waves[i]/'runner.py'),
                           '--replica-id', replica['id'], '--worker-index', str(index)]
                log = (waves[i]/'execution'/f'{name}.log').open('ab', buffering=0)
                child = subprocess.Popen(command, cwd=waves[i], stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                entry = {'name': name, 'model': model, 'pid': child.pid, 'exit_code': None,
                         'command': command, 'started_unix': time.time()}
                group.append((entry, child, log))
                receipt['workers'].append(entry.copy())
                save(receipt_path, receipt)
                time.sleep(.15)
        receipt['state'] = 'started'
        save(receipt_path, receipt)
        state['models'][model] = {'wave': i+1, 'state': 'running', 'started_unix': time.time()}

    def snapshot():
        totals = []
        for i, wave in enumerate(waves):
            counts = {m: len(list((wave/'results'/m).glob('*/*/final.json'))) for m in MODELS}
            totals.append(sum(counts.values()))
            if i:
                entries = [e.copy() for (j, _), group in children.items() if i == j for e, _, _ in group]
                models_done = all((i, m) in audits and audits[(i, m)]['complete'] for m in MODELS)
                status = 'complete' if models_done else ('running' if entries else 'pending')
                if any(state['models'][m]['wave'] == i+1 and state['models'][m]['state'] == 'needs_attention' for m in MODELS):
                    status = 'needs_attention'
                save(wave/'execution/status.json', {'status': status, 'managed_by': str(ROOT),
                    'job_id': os.environ['SLURM_JOB_ID'], 'updated_unix': time.time(),
                    'expected_results': 480, 'final_results': sum(counts.values()), 'per_model': counts,
                    'running_workers': sum(e['exit_code'] is None for e in entries), 'workers': entries,
                    'sa_execution_enabled': False, 'external_api_enabled': False})
        state.update(updated_unix=time.time(), wave_final_results=totals, final_results=sum(totals),
                     running_workers=sum(c.poll() is None for group in children.values() for _, c, _ in group))
        save(run/'status.json', state)

    def aggregate():
        return subprocess.run([sys.executable, '-B', str(ROOT/'aggregate_three_waves.py')], cwd=ROOT).returncode

    try:
        while not interrupted:
            for group in children.values():
                for entry, child, _ in group:
                    entry['exit_code'] = child.poll()
            changed = False
            for model in MODELS:
                stage = state['models'][model]
                if stage['state'] in ('complete', 'needs_attention'):
                    continue
                i = stage['wave']-1
                entries = entries_for(i, model)
                expected = manifest['workers_per_replica'][model]*sum(r['model_key'] == model for r in replicas)
                if len(entries) != expected or any(e.get('exit_code') is None for e in entries):
                    continue
                audit = audit_model(waves[i], model)
                audits[(i, model)] = audit
                save(run/f'audit_wave{i+1}_{model}.json', audit)
                changed = True
                if not gate(audit, entries, expected):
                    stage.update(state='needs_attention', audit_file=f'audit_wave{i+1}_{model}.json',
                                 errors=audit['errors'][:5], missing_count=len(audit['missing']),
                                 failed_worker_count=sum(e.get('exit_code') != 0 for e in entries))
                    continue
                if i == 2:
                    stage.update(state='complete', ended_unix=time.time())
                else:
                    launch(i+1, model)
            for i in (1, 2):
                if i not in reported and all((i, m) in audits and audits[(i, m)]['complete'] for m in MODELS):
                    report = subprocess.run([sys.executable, '-B', str(waves[i]/'report_results.py')], cwd=waves[i])
                    if report.returncode:
                        state.setdefault('report_errors', []).append({'wave': i+1, 'exit_code': report.returncode})
                    reported.add(i)
            snapshot()
            if changed:
                aggregate()
            if all(s['state'] in ('complete', 'needs_attention') for s in state['models'].values()):
                rc = aggregate()
                ready = rc == 0 and read(ROOT/'aggregate_summary.json')['formal_three_wave_ready']
                okay = ready and not state.get('report_errors') and all(s['state'] == 'complete' for s in state['models'].values())
                state.update(status='complete' if okay else 'needs_attention', ended_unix=time.time())
                snapshot()
                return 0 if okay else 1
            time.sleep(15)
        state['status'] = 'interrupted'
        snapshot()
        return 130
    except Exception as exc:
        state.update(status='needs_attention', supervisor_error=repr(exc))
        snapshot()
        raise
    finally:
        for group in children.values():
            for _, child, log in group:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                log.close()
        for handle in locks:
            handle.close()


if __name__ == '__main__':
    raise SystemExit(main())

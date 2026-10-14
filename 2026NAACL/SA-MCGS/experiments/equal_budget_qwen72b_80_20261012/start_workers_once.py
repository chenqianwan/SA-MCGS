#!/usr/bin/env python3
"""Start the verified 160-arm queue once in the existing allocation."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')
SLURM = Path('/cm/shared/apps/slurm/current/bin')


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    os.umask(0o077)
    if os.getuid() != 1083 or Path(__file__).resolve().parent != ROOT or ROOT.resolve() != ROOT:
        raise RuntimeError('Unexpected account or experiment directory')
    folder = ROOT / 'execution'
    folder.mkdir(exist_ok=True)
    with (folder / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = folder / 'step_launch_receipt.json'
        if receipt_path.exists():
            print(json.dumps({'status': 'existing_receipt_no_duplicate_launch', 'receipt': read(receipt_path)}))
            return
        preflight = read(ROOT / 'preflight/runner_prepare.json')
        if (preflight.get('status') != 'passed' or preflight.get('expected_results') != 160
                or preflight.get('model_calls') != 0 or preflight.get('sa_model_calls') != 0):
            raise RuntimeError('Offline scope/identity preflight has not passed')
        protocol = preflight['protocol']
        hashes = {**protocol['source_hashes'], 'run_scope.json': protocol['run_scope_sha256'],
                  'historical_sa_reference.json': protocol['historical_sa_reference_sha256']}
        for name, expected in hashes.items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise RuntimeError('Source changed after preflight: ' + name)
        endpoints = read(ROOT / 'endpoints.json')
        from runner import validate_endpoints
        validate_endpoints(endpoints)
        if len(endpoints['replicas']) != 4:
            raise RuntimeError('Expected four verified Qwen TP2 replicas')
        env = os.environ.copy()
        env.update(SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf', PATH='/usr/bin:/bin')
        checked = subprocess.run([str(SLURM / 'scontrol'), 'show', 'job', '415747', '--oneliner'],
                                 env=env, text=True, capture_output=True, check=True, timeout=30)
        fields = dict(x.split('=', 1) for x in checked.stdout.split() if '=' in x)
        if (fields.get('JobState') != 'RUNNING' or fields.get('NodeList') != 'dgx-061'
                or fields.get('UserId') != 'hansirui_3rd(1083)'):
            raise RuntimeError('Authorized allocation changed')
        command = [str(SLURM / 'srun'), '--jobid=415747', '--overlap', '--exact',
                   '--nodes=1', '--ntasks=1', '--cpus-per-task=64', '--gres=none',
                   '--chdir=' + str(ROOT), '--export=ALL', '/bin/bash', str(ROOT / 'launch_workers.sh')]
        receipt = {'status': 'starting', 'created_unix': time.time(), 'job_id': '415747',
                   'node': 'dgx-061', 'expected_results': 160, 'sa_execution_enabled': False,
                   'command': command, 'verified_source_hashes': hashes,
                   'endpoints_sha256': hashlib.sha256((ROOT / 'endpoints.json').read_bytes()).hexdigest()}
        save(receipt_path, receipt)
        with (folder / 'step.log').open('ab', buffering=0) as log:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                     stderr=subprocess.STDOUT, cwd=ROOT, env=env,
                                     start_new_session=True, close_fds=True)
        receipt.update(status='step_process_started', launch_pid=child.pid)
        save(receipt_path, receipt)
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()

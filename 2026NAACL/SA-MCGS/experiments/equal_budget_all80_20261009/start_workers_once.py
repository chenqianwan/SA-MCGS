#!/usr/bin/env python3
"""Dispatch durable workers into the existing allocation, once."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_all80_20261009')
SLURM = Path('/cm/shared/apps/slurm/current/bin')


def write(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2)+'\n')
    tmp.replace(path)


def main():
    os.umask(0o077)
    folder = ROOT/'execution'
    folder.mkdir(exist_ok=True)
    if os.getuid() != 1083 or ROOT.resolve() != ROOT:
        raise RuntimeError('Unexpected user or path')
    preflight = json.loads((ROOT/'preflight/runner_prepare.json').read_text())
    if preflight.get('status') != 'passed' or preflight.get('expected_results') != 480 or preflight.get('model_calls') != 0:
        raise RuntimeError('Cluster offline preflight must pass before dispatch')
    protocol = preflight['protocol']
    expected_hashes = {**protocol['source_hashes'],
        'run_scope.json': protocol['run_scope_sha256'],
        'historical_sa_reference.json': protocol['historical_sa_reference_sha256']}
    for name, expected_hash in expected_hashes.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected_hash:
            raise RuntimeError('Scientific source changed after offline preflight: '+name)
    with (folder/'start.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = folder/'step_launch_receipt.json'
        if receipt_path.exists():
            print(receipt_path.read_text())
            return
        env = os.environ.copy()
        env.update(SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf', PATH='/usr/bin:/bin')
        check = subprocess.run([str(SLURM/'scontrol'), 'show', 'job', '415747', '--oneliner'],
                               env=env, text=True, capture_output=True, check=True, timeout=30)
        fields = dict(item.split('=', 1) for item in check.stdout.split() if '=' in item)
        if fields.get('JobState') != 'RUNNING' or fields.get('NodeList') != 'dgx-061':
            raise RuntimeError('Allocated job no longer running on dgx-061')
        command = ['/usr/bin/nohup', str(SLURM/'srun'), '--jobid=415747', '--overlap', '--exact',
                   '--nodes=1', '--ntasks=1', '--cpus-per-task=64', '--gres=none',
                   '--chdir='+str(ROOT), '--export=ALL', '/bin/bash', str(ROOT/'launch_workers.sh')]
        receipt = {'status': 'starting', 'command': command, 'created_unix': time.time()}
        write(receipt_path, receipt)
        with (folder/'step.log').open('ab', buffering=0) as log:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, cwd=ROOT, env=env, start_new_session=True, close_fds=True)
        receipt.update(status='step_process_started', launch_pid=child.pid)
        write(receipt_path, receipt)
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Start one persistent service step in existing job 415747; never submit a job."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_full_20261009')
DEPLOY = ROOT/'deployment'
SLURM = Path('/cm/shared/apps/slurm/current/bin')
JOB = '415747'


def write(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2)+'\n')
    temporary.replace(path)


def main():
    os.umask(0o077)
    if os.getuid() != 1083 or DEPLOY.resolve() != DEPLOY:
        raise RuntimeError('Unexpected account or deployment directory')
    with (DEPLOY/'start.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = DEPLOY/'step_launch_receipt.json'
        if receipt_path.exists():
            print(json.dumps({'status': 'existing_receipt_no_duplicate_launch',
                              'receipt': json.loads(receipt_path.read_text())}))
            return
        env = os.environ.copy()
        env.update(SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf',
                   PATH='/usr/bin:/bin')
        check = subprocess.run([str(SLURM/'scontrol'), 'show', 'job', JOB, '--oneliner'],
            env=env, text=True, capture_output=True, check=True, timeout=30)
        fields = dict(item.split('=', 1) for item in check.stdout.split() if '=' in item)
        if (fields.get('JobId') != JOB or fields.get('JobState') != 'RUNNING'
                or fields.get('UserId') != 'hansirui_3rd(1083)'
                or fields.get('NodeList') != 'dgx-061' or fields.get('NumNodes') != '1'):
            raise RuntimeError('The authorized allocation identity/state has changed')
        manifest = json.loads((DEPLOY/'staging_manifest.json').read_text())
        for name, expected in manifest['files'].items():
            path = DEPLOY/name
            if path.resolve() != path or hashlib.sha256(path.read_bytes()).hexdigest() != expected['sha256']:
                raise RuntimeError('Staged deployment file mismatch: '+name)
        command = ['/usr/bin/nohup', str(SLURM/'srun'), '--jobid='+JOB, '--overlap', '--exact',
            '--nodes=1', '--ntasks=1', '--cpus-per-task=80', '--gres=gpu:8',
            '--chdir='+str(ROOT), '--export=ALL', '/bin/bash', str(DEPLOY/'launch.sh')]
        receipt = dict(status='starting', job_id=JOB, node='dgx-061', command=command,
            created_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            staging_manifest_sha256=hashlib.sha256((DEPLOY/'staging_manifest.json').read_bytes()).hexdigest())
        # Durable intent precedes Popen: an ambiguous disconnect must be reconciled.
        write(receipt_path, receipt)
        with (DEPLOY/'step.log').open('ab', buffering=0) as log:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, env=env, cwd=ROOT, start_new_session=True, close_fds=True)
        receipt.update(status='step_process_started', launch_pid=child.pid)
        write(receipt_path, receipt)
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()

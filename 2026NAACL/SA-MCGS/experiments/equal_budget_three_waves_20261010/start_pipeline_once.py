#!/usr/bin/env python3
"""Dispatch one persistent three-wave supervisor into existing job 415747.

A receipt is written before dispatch. An ambiguous or failed launch is preserved
for reconciliation and is never automatically retried. No job is allocated or
cancelled, and this launcher does not alter model services or prior wave data.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_three_waves_20261010')
SLURM = Path('/cm/shared/apps/slurm/current/bin')
JOB = '415747'
NODE = 'dgx-061'
UID = 1083


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write(path, data):
    """Persist the intent before a child can start, including directory metadata."""
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with temporary.open('w') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def verify_preflight(path):
    preflight = json.loads(path.read_text())
    if (preflight.get('status') != 'passed'
            or type(preflight.get('model_calls')) is not int
            or preflight['model_calls'] != 0
            or preflight.get('expected_results_total') != 1440):
        raise RuntimeError('A passed, zero-call, 1440-result pipeline preflight is required')
    hashes = preflight.get('file_hashes')
    if not isinstance(hashes, dict) or not hashes:
        raise RuntimeError('Pipeline preflight must contain nonempty absolute file_hashes')
    for name, expected in hashes.items():
        if (not isinstance(name, str) or not Path(name).is_absolute()
                or not isinstance(expected, str)
                or re.fullmatch(r'[0-9a-f]{64}', expected) is None):
            raise RuntimeError('Malformed pipeline preflight file hash')
        if not Path(name).is_file() or sha(name) != expected:
            raise RuntimeError('File changed since pipeline preflight: '+name)
    return preflight


def main():
    os.umask(0o077)
    if os.getuid() != UID or ROOT.resolve() != ROOT or not ROOT.is_dir():
        raise RuntimeError('Unexpected account or pipeline directory')
    folder = ROOT/'execution'
    folder.mkdir(exist_ok=True)
    if folder.resolve() != folder:
        raise RuntimeError('Pipeline execution directory must not be redirected')
    with (folder/'start.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = folder/'step_launch_receipt.json'
        if receipt_path.exists():
            print(json.dumps({'status': 'existing_receipt_no_duplicate_launch',
                              'receipt': json.loads(receipt_path.read_text())}))
            return 0
        preflight_path = ROOT/'preflight/pipeline_prepare.json'
        preflight = verify_preflight(preflight_path)
        env = os.environ.copy()
        env.update(SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf',
                   PATH='/usr/bin:/bin')
        check = subprocess.run([str(SLURM/'scontrol'), 'show', 'job', JOB, '--oneliner'],
            env=env, text=True, capture_output=True, check=True, timeout=30)
        fields = dict(item.split('=', 1) for item in check.stdout.split() if '=' in item)
        if (fields.get('JobId') != JOB or fields.get('JobState') != 'RUNNING'
                or fields.get('UserId') != 'hansirui_3rd(1083)'
                or fields.get('NodeList') != NODE or fields.get('NumNodes') != '1'):
            raise RuntimeError('The authorized allocation identity or state has changed')
        command = ['/usr/bin/nohup', str(SLURM/'srun'), '--jobid='+JOB,
            '--overlap', '--exact', '--nodes=1', '--ntasks=1', '--cpus-per-task=64',
            '--gres=none', '--input=none', '--chdir='+str(ROOT), '--export=ALL',
            '/bin/bash', str(ROOT/'launch_pipeline.sh')]
        receipt = dict(status='starting', job_id=JOB, node=NODE, command=command,
            expected_results_total=1440, created_unix=time.time(),
            preflight_sha256=sha(preflight_path),
            verified_file_count=len(preflight['file_hashes']))
        write(receipt_path, receipt)
        with (folder/'step.log').open('ab', buffering=0) as log:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, env=env, cwd=ROOT,
                start_new_session=True, close_fds=True)
        receipt.update(status='step_process_started', launch_pid=child.pid)
        write(receipt_path, receipt)
        print(json.dumps(receipt))
        return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Start one persistent Qwen service step in existing job 415747; never sbatch."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

DEPLOY = Path(__file__).resolve().parent
ROOT = DEPLOY.parent
AUTHORIZED_ROOT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')
SLURM = Path('/cm/shared/apps/slurm/current/bin')
PYTHON = '/aifs4su/hansirui/vllm-dsv4-venv/bin/python3'
JOB = '415747'
NODE = 'dgx-061'


def write(path, value):
    temporary = path.with_name(path.name+'.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    os.umask(0o077)
    if os.getuid() != 1083 or ROOT != AUTHORIZED_ROOT:
        raise RuntimeError('Unexpected account or deployment root')
    with (DEPLOY/'start_services.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = DEPLOY/'services_launch_receipt.json'
        if receipt_path.exists():
            print(json.dumps({'status': 'existing_receipt_no_duplicate_launch',
                              'receipt': json.loads(receipt_path.read_text())}))
            return
        if (DEPLOY/'service_state.json').exists() or (ROOT/'endpoints.json').exists():
            raise RuntimeError('Prior services state exists without matching launch receipt; reconcile first')
        complete = json.loads((DEPLOY/'model_download_complete.json').read_text())
        if complete.get('state') != 'complete' or complete.get('verified') is not True:
            raise RuntimeError('Pinned checkpoint restore has not completed verification')
        env = os.environ.copy()
        env.update(SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf',
                   PATH='/usr/bin:/bin', PYTHONHASHSEED='42', PYTHONNOUSERSITE='1',
                   PYTHONDONTWRITEBYTECODE='1', PYTHON_DOTENV_DISABLED='1',
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', CUDA_DEVICE_ORDER='PCI_BUS_ID',
                   SLURM_EXPORT_ENV='ALL')
        env.pop('PYTHONPATH', None)
        check = subprocess.run([str(SLURM/'scontrol'), 'show', 'job', JOB, '--oneliner'],
            env=env, text=True, capture_output=True, check=True, timeout=30)
        fields = dict(item.split('=', 1) for item in check.stdout.split() if '=' in item)
        if (fields.get('JobId') != JOB or fields.get('JobState') != 'RUNNING'
                or fields.get('UserId') != 'hansirui_3rd(1083)'
                or fields.get('NodeList') != NODE or fields.get('NumNodes') != '1'):
            raise RuntimeError('Authorized allocation identity/state changed')
        manifest_path = DEPLOY/'services_staging_manifest.json'
        manifest = json.loads(manifest_path.read_text())
        for name, expected in manifest['files'].items():
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise RuntimeError('Unsafe staging manifest entry')
            path = ROOT/name
            if path.resolve() != path or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise RuntimeError('Staged service source mismatch: '+name)
        command = ['/usr/bin/nohup', str(SLURM/'srun'), '--jobid='+JOB, '--overlap', '--exact',
            '--nodes=1', '--ntasks=1', '--cpus-per-task=80', '--gres=gpu:8', '--nodelist='+NODE,
            '--chdir='+str(ROOT), '--export=ALL', PYTHON, '-B', str(DEPLOY/'service_supervisor.py')]
        receipt = {'status': 'starting', 'job_id': JOB, 'node': NODE, 'command': command,
                   'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                   'staging_manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                   'manages_preexisting_services': False, 'submits_new_job': False}
        # Persist intent before Popen so uncertain disconnects never trigger duplicate launch.
        write(receipt_path, receipt)
        with (DEPLOY/'services_step.log').open('ab', buffering=0) as log:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, env=env, cwd=ROOT, start_new_session=True, close_fds=True)
        receipt.update(status='step_process_started', launch_pid=child.pid)
        write(receipt_path, receipt)
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()

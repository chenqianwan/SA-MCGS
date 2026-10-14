#!/usr/bin/env python3
"""Launch a single persistent CPU-only restore step in allocation 415747."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

DEPLOY = Path(__file__).resolve().parent
EXPECTED = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012/deployment')
SLURM = Path('/cm/shared/apps/slurm/current/bin')
MODEL_ROOT = Path('/aifs4su/hansirui_3rd/chenlong/q72awq_20261012')


def save(path, data):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    os.umask(0o077)
    if DEPLOY != EXPECTED or os.getuid() != 1083:
        raise RuntimeError('Unexpected deployment or account')
    with (DEPLOY / 'model_restore_launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt = DEPLOY / 'model_restore_launch_receipt.json'
        if receipt.exists():
            print(json.dumps({'status': 'existing_receipt_no_duplicate_launch',
                              'receipt': json.loads(receipt.read_text())}))
            return
        if MODEL_ROOT.exists():
            raise RuntimeError('Destination already exists; reconcile before launch')
        if shutil.disk_usage(MODEL_ROOT.parent).free < 64 * 1024**3:
            raise RuntimeError('Less than 64 GiB free storage')
        manifest = json.loads((DEPLOY / 'restore_staging_manifest.json').read_text())
        for name, expected in manifest['files'].items():
            path = DEPLOY / name
            if Path(name).name != name or path.resolve() != path:
                raise RuntimeError('Unsafe staged file')
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected['sha256']:
                raise RuntimeError('Staged file differs')
        env = os.environ.copy()
        env.update(SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf',
                   PYTHONDONTWRITEBYTECODE='1', PYTHON_DOTENV_DISABLED='1',
                   PYTHONNOUSERSITE='1')
        env.pop('PYTHONPATH', None)
        checked = subprocess.run([str(SLURM / 'scontrol'), 'show', 'job', '415747', '--oneliner'],
                                 env=env, text=True, capture_output=True, check=True, timeout=30)
        fields = dict(x.split('=', 1) for x in checked.stdout.split() if '=' in x)
        if (fields.get('JobId') != '415747' or fields.get('JobState') != 'RUNNING'
                or fields.get('UserId') != 'hansirui_3rd(1083)' or fields.get('NodeList') != 'dgx-061'):
            raise RuntimeError('Authorized allocation differs')
        command = [str(SLURM / 'srun'), '--jobid=415747', '--overlap', '--exact',
                   '--nodes=1', '--ntasks=1', '--cpus-per-task=4', '--gres=none',
                   '--time=02:00:00', '--chdir=' + str(DEPLOY), '--export=ALL',
                   '/aifs4su/hansirui/vllm-dsv4-venv/bin/python3', '-B', str(DEPLOY / 'restore_model.py')]
        state = dict(status='starting', job_id='415747', node='dgx-061',
                     command=command, created_unix=time.time(), gpu_requested=False,
                     inference_calls=0, model_path=str(MODEL_ROOT / 'model'),
                     staging_manifest_sha256=hashlib.sha256((DEPLOY / 'restore_staging_manifest.json').read_bytes()).hexdigest())
        save(receipt, state)
        with (DEPLOY / 'model_restore_step.log').open('ab', buffering=0) as log:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                     stderr=subprocess.STDOUT, cwd=DEPLOY, env=env,
                                     start_new_session=True, close_fds=True)
        state.update(status='step_process_started', launch_pid=child.pid)
        save(receipt, state)
        print(json.dumps(state))


if __name__ == '__main__':
    main()

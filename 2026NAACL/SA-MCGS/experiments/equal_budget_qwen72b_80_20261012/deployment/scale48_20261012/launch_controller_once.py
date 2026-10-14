#!/usr/bin/env python3
"""Submit one CPU-only transition step to the already authorized allocation."""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EXPECTED = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')


def save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def main():
    if ROOT != EXPECTED or os.getuid() != 1083:
        raise RuntimeError('Unexpected account or experiment root')
    os.umask(0o077)
    with (HERE / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = HERE / 'controller_launch_receipt.json'
        if receipt_path.exists():
            print(json.dumps({'status': 'existing_receipt_no_duplicate_launch',
                              'receipt': json.loads(receipt_path.read_text())}))
            return
        if (HERE / 'controller_status.json').exists():
            raise RuntimeError('Existing controller status without receipt')
        state = json.loads((ROOT / 'execution/status.json').read_text())
        service = json.loads((ROOT / 'deployment/service_state.json').read_text())
        if (state['status'] != 'running' or state['running_workers'] != 32
                or state['step_id'] != '43' or service['step_id'] != '42'
                or service['status'] != 'ready' or any(service['health_failures'].values())
                or time.time() - state['updated_unix'] > 90):
            raise RuntimeError('Expected healthy current 32-worker run')
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env.update(SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf',
                   SLURM_EXPORT_ENV='ALL', PYTHONHASHSEED='42', PYTHONNOUSERSITE='1',
                   PYTHONDONTWRITEBYTECODE='1', PYTHON_DOTENV_DISABLED='1',
                   TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='1',
                   OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        slurm = '/cm/shared/apps/slurm/current/bin/'
        checked = subprocess.run([slurm + 'scontrol', 'show', 'job', '415747', '--oneliner'],
                                 env=env, capture_output=True, text=True, check=True, timeout=20)
        fields = dict(x.split('=', 1) for x in checked.stdout.split() if '=' in x)
        if fields.get('JobState') != 'RUNNING' or fields.get('NodeList') != 'dgx-061' or fields.get('UserId') != 'hansirui_3rd(1083)':
            raise RuntimeError('Allocation identity changed')
        files = ['controller.py', 'launch_controller_once.py', 'drain.py', 'checkpoint_drain.py',
                 'replay_preflight.py', 'restart_after_drain.py', 'observe48.py']
        hashes = {str((HERE / name).relative_to(ROOT)): hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                  for name in files}
        command = ['/usr/bin/nohup', slurm + 'srun', '--jobid=415747', '--overlap', '--exact',
                   '--nodes=1', '--ntasks=1', '--cpus-per-task=4', '--gres=none', '--nodelist=dgx-061',
                   '--chdir=' + str(ROOT), '--export=ALL', '/usr/bin/env', 'CUDA_VISIBLE_DEVICES=',
                   '/aifs4su/hansirui/vllm-dsv4-venv/bin/python3', '-B', str(HERE / 'controller.py')]
        receipt = {'status': 'launch_intent', 'created_unix': time.time(), 'job_id': '415747',
                   'target_workers': 48, 'target_service_max_num_seqs': 12, 'gpu_requested': False,
                   'auto_retry': False, 'command': command, 'source_sha256': hashes,
                   'authorization': 'User explicitly requested directly testing 48 concurrency.'}
        save(receipt_path, receipt)
        with (HERE / 'controller_step.log').open('ab', buffering=0) as log:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        receipt.update(status='step_process_started', launch_pid=child.pid)
        save(receipt_path, receipt)
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()

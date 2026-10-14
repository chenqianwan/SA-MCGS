#!/usr/bin/env python3
"""Resume the verified 48-request transition after a completed-exit audit race."""
from pathlib import Path
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import fcntl

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EXPECTED = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')


def save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def main():
    if (ROOT != EXPECTED or os.getuid() != 1083 or socket.gethostname().split('.')[0] != 'dgx-061'
            or os.environ.get('SLURM_JOB_ID') != '415747'
            or os.environ.get('CUDA_VISIBLE_DEVICES', '') not in ('', '-1', 'NoDevFiles')):
        raise RuntimeError('Controller requires the exact CPU-only allocation context')
    with (HERE / 'recovery_controller.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (HERE / 'recovery_controller_status.json').exists():
            raise RuntimeError('Prior controller state exists; inspect without duplicate execution')
        receipt = json.loads((HERE / 'recovery_launch_receipt.json').read_text())
        for relative, expected in receipt['source_sha256'].items():
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
                raise RuntimeError('Controller source differs from launch receipt: ' + relative)
        state = {'status': 'starting', 'pid': os.getpid(), 'job_id': '415747',
                 'step_id': os.environ['SLURM_STEP_ID'], 'started_unix': time.time(),
                 'target_workers': 48, 'target_service_max_num_seqs': 12,
                 'scientific_model_calls': 0, 'sa_execution_enabled': False, 'source': 'explicit_recovery_after_completed_exit_race'}
        def update(status, **fields):
            state.update(status=status, updated_unix=time.time(), **fields)
            save(HERE / 'recovery_controller_status.json', state)
            print(json.dumps(state), flush=True)
        try:
            update('reconciling_completed_checkpoint')
            with (HERE / 'reconciliation_step.log').open('ab', buffering=0) as log:
                drained = subprocess.run([sys.executable, '-B', str(HERE / 'reconcile_completed_checkpoint.py')],
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            if drained.returncode != 0:
                raise RuntimeError('Completed-checkpoint reconciliation failed; no service restart requested')
            update('reconciled_starting_48')
            # The observer never calls the model, changes configuration or signals a process.
            with (HERE / 'observe48.log').open('ab', buffering=0) as log:
                observer = subprocess.Popen([sys.executable, '-B', str(HERE / 'observe48.py')],
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            update('running_restart_helper', observer_pid=observer.pid)
            # Stay alive for the complete replacement pipeline. Its nested Slurm
            # controllers belong to this step's cgroup, including its services.
            with (HERE / 'restart_step.log').open('ab', buffering=0) as log:
                restarted = subprocess.run([sys.executable, '-B', str(HERE / 'restart_after_drain.py')],
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            update('complete' if restarted.returncode == 0 else 'needs_attention',
                   restart_exit_code=restarted.returncode, ended_unix=time.time())
            return restarted.returncode
        except BaseException as exc:
            update('needs_attention', error_type=type(exc).__name__, error=str(exc), ended_unix=time.time())
            raise


if __name__ == '__main__':
    raise SystemExit(main())

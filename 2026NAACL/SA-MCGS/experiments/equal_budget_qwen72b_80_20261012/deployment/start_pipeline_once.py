#!/usr/bin/env python3
"""Launch one durable CPU-only pipeline step inside existing allocation 415747."""
from __future__ import annotations
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
JOB, NODE = '415747', 'dgx-061'
FILES = ('deployment/pipeline_supervisor.py', 'deployment/start_pipeline_once.py',
         'deployment/retire_previous_services.py', 'deployment/start_services_once.py',
         'deployment/service_supervisor.py', 'deployment/context_preflight.py', 'deployment/stop_services.py',
         'deployment/services_staging_manifest.json', 'start_workers_once.py', 'launch_workers.sh',
         'worker_supervisor.py', 'runner.py', 'science_support.py', 'methods_full.py', 'budget_client.py',
         'historical_sa_reference.json', 'run_scope.json', 'preflight/runner_prepare.json')


def save(path, value):
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
    if ROOT != AUTHORIZED_ROOT or ROOT.resolve() != ROOT or os.getuid() != 1083:
        raise RuntimeError('Unexpected pipeline deployment directory or account')
    with (DEPLOY/'start_pipeline.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = DEPLOY/'pipeline_launch_receipt.json'
        if path.exists():
            print(json.dumps({'status': 'existing_receipt_no_duplicate_launch',
                              'receipt': json.loads(path.read_text())}))
            return
        if (DEPLOY/'pipeline_status.json').exists():
            raise RuntimeError('Prior pipeline state exists without launch receipt; reconcile without retry')
        if (DEPLOY/'model_restore_failure.json').exists():
            raise RuntimeError('Model restore has failed; pipeline will not launch')
        preflight = json.loads((ROOT/'preflight/runner_prepare.json').read_text())
        if (preflight.get('status') != 'passed' or preflight.get('expected_results') != 160
                or preflight.get('model_calls') != 0 or preflight.get('sa_model_calls') != 0):
            raise RuntimeError('Offline scope and identity preflight has not passed')
        proofs = {}
        for name in FILES:
            source = ROOT/name
            if source.resolve() != source:
                raise RuntimeError('Redirected pipeline source: '+name)
            proofs[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env.update(SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf',
                   PATH='/usr/bin:/bin', PYTHONHASHSEED='42', PYTHONNOUSERSITE='1',
                   PYTHONDONTWRITEBYTECODE='1', PYTHON_DOTENV_DISABLED='1', SLURM_EXPORT_ENV='ALL')
        for key in ('CUDA_VISIBLE_DEVICES', 'SLURM_STEP_GPUS', 'SLURM_GPUS_ON_NODE',
                    'SLURM_GPUS_PER_TASK', 'SLURM_GPUS_PER_NODE', 'SLURM_GPUS',
                    'SLURM_GRES', 'SLURM_TRES_PER_TASK', 'SLURM_TRES_BIND', 'SLURM_GPU_BIND'):
            env.pop(key, None)
        checked = subprocess.run([str(SLURM/'scontrol'), 'show', 'job', JOB, '--oneliner'],
            env=env, text=True, capture_output=True, check=True, timeout=30)
        fields = dict(item.split('=', 1) for item in checked.stdout.split() if '=' in item)
        if (fields.get('JobId') != JOB or fields.get('JobState') != 'RUNNING'
                or fields.get('UserId') != 'hansirui_3rd(1083)' or fields.get('NodeList') != NODE):
            raise RuntimeError('Authorized allocation identity/state changed')
        command = ['/usr/bin/nohup', str(SLURM/'srun'), '--jobid='+JOB, '--overlap', '--exact',
                   '--nodes=1', '--ntasks=1', '--cpus-per-task=2', '--gres=none', '--nodelist='+NODE,
                   '--chdir='+str(ROOT), '--export=ALL',
                   '/usr/bin/env', 'CUDA_VISIBLE_DEVICES=', PYTHON, '-B', str(DEPLOY/'pipeline_supervisor.py')]
        receipt = {'status': 'starting', 'job_id': JOB, 'node': NODE, 'command': command,
                   'created_unix': time.time(), 'gpu_requested': False, 'auto_retry': False,
                   'expected_results': 160, 'sa_execution_enabled': False,
                   'restore_wait_timeout_sec': 7200, 'service_wait_timeout_sec': 7200,
                   'worker_wait_timeout_sec': 1200, 'pipeline_lifetime': 'full_experiment_in_allocation',
                   'verified_files': proofs}
        save(path, receipt)
        with (DEPLOY/'pipeline_step.log').open('ab', buffering=0) as log:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
        receipt.update(status='step_process_started', launch_pid=child.pid)
        save(path, receipt)
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Gracefully retire only the identified prior task service supervisor.

Runs within job 415747. Never cancels a Slurm job, kills arbitrary GPU processes,
changes shared software, or touches prior experiment results.
"""
import json
import os
from pathlib import Path
import subprocess
import socket
import time
from service_supervisor import BASE_ROOT, OLD_ROOT, ROOT, TOPOLOGY, JOB, now, read, write


def main():
    if (os.environ.get('SLURM_JOB_ID') != JOB or os.getuid() != 1083
            or socket.gethostname().split('.')[0] != 'dgx-061'):
        raise RuntimeError('Require the authorized existing allocation on dgx-061')
    target = OLD_ROOT if TOPOLOGY == 'balanced' else BASE_ROOT
    source = target/'deployment/service_supervisor.py'
    prior = read(target/'deployment/service_state.json')
    if prior.get('job_id') != JOB or prior.get('hostname', '').split('.')[0] != 'dgx-061':
        raise RuntimeError('Prior service identity mismatch')
    pid = int(prior['pid'])
    if TOPOLOGY == 'balanced':
        if pid != 633843 or str(prior.get('step_id')) != '13':
            raise RuntimeError('Old supervisor differs from the authorized completed trial')
        finals = list((OLD_ROOT/'results').glob('*/*/*/final.json'))
        if len(finals) != 90 or any(read(p).get('completion_status') not in ('complete', 'strict_experiment_failure') for p in finals):
            raise RuntimeError('The prior 90-result experiment is not fully terminal')
        workers = read(OLD_ROOT/'execution/status.json')
        if (workers.get('status') not in ('complete', 'needs_attention')
                or workers.get('final_results') != 90
                or any(w.get('exit_code') is None for w in workers.get('workers', []))):
            raise RuntimeError('Prior scientific workers are still active')
    receipt_path = ROOT/'deployment/retirement_receipt.json'
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = dict(at=now(), topology=TOPOLOGY, target_root=str(target), pid=pid,
                   job_id=JOB, step_id=prior.get('step_id'), signal='SIGTERM', status='verifying')
    proc = Path('/proc')/str(pid)
    command = [s.decode() for s in (proc/'cmdline').read_bytes().split(b'\0') if s] if proc.exists() else []
    if command:
        if proc.stat().st_uid != 1083 or str(source) not in command:
            raise RuntimeError('Refusing to retire an unrecognized prior service process')
        step = str(prior.get('step_id'))
        if not step.isdigit() or step == os.environ.get('SLURM_STEP_ID'):
            raise RuntimeError('Refusing an invalid or current Slurm step identity')
        target_step = JOB+'.'+step
        receipt.update(command=command, status='termination_intent', target_step=target_step)
        write(receipt_path, receipt)
        # Signal exactly job.step, never the parent job; Slurm step IDs are not reused.
        action = ['/cm/shared/apps/slurm/current/bin/scancel', '--signal=TERM', target_step]
        result = subprocess.run(action, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError('Slurm service-step SIGTERM failed: '+result.stderr[:500])
        receipt.update(status='termination_sent', signal_sent_at=now(), action=action)
        write(receipt_path, receipt)
        deadline = time.monotonic()+120
        while proc.exists():
            current = (proc/'cmdline').read_bytes().split(b'\0')
            if str(source).encode() not in current:
                break
            if time.monotonic()>deadline:
                raise RuntimeError('Prior supervisor did not exit in 120 seconds; no force kill attempted')
            time.sleep(1)
        receipt.update(status='prior_supervisor_exited', exited_at=now())
    else:
        if prior.get('status') not in ('stopped', 'failed') and not receipt_path.exists():
            raise RuntimeError('Prior process vanished without a terminal service state')
        receipt.update(status='prior_process_already_exited')
    # Its child cleanup may finish just after the main process exits.
    deadline = time.monotonic()+120
    while True:
        occupied=[]
        for port in range(19081,19089):
            with socket.socket() as sock:
                sock.settimeout(.25)
                if sock.connect_ex(('127.0.0.1',port)) == 0:
                    occupied.append(port)
        if not occupied:
            break
        if time.monotonic()>deadline:
            raise RuntimeError('Prior owned service ports remain occupied; refusing overlap')
        time.sleep(2)
    receipt.update(status='retired', completed_at=now(), service_ports_free=True)
    write(receipt_path, receipt)
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()

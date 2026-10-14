#!/usr/bin/env python3
"""Gracefully stop only this deployment's identity-verified supervisor on its node."""
import json
import os
from pathlib import Path
import signal
import socket

from service_supervisor import DEPLOY, ROOT, AUTHORIZED_ROOT, JOB, NODE, process_identity, write, now


def main():
    if os.getuid() != 1083 or socket.gethostname() != NODE or ROOT != AUTHORIZED_ROOT:
        raise RuntimeError('Stop wrapper must run as deployment owner on its exact authorized node')
    state = json.loads((DEPLOY/'service_state.json').read_text())
    if state.get('job_id') != JOB or state.get('hostname') != NODE:
        raise RuntimeError('Service state identity mismatch')
    if state.get('status') == 'stopped':
        print(json.dumps({'status': 'already_stopped', 'pid': state['pid']}))
        return
    pid = state['pid']
    if type(pid) is not int or pid <= 1:
        raise RuntimeError('Invalid service PID')
    process = Path('/proc')/str(pid)
    if not process.exists():
        raise RuntimeError('Recorded supervisor no longer exists; no process signalled')
    if process_identity(pid) != state.get('process_identity'):
        raise RuntimeError('Recorded PID has changed identity; no process signalled')
    argv = (process/'cmdline').read_bytes().split(b'\0')
    if str(DEPLOY/'service_supervisor.py').encode() not in argv:
        raise RuntimeError('Recorded process is not this exact service supervisor')
    env = dict(item.split(b'=', 1) for item in (process/'environ').read_bytes().split(b'\0') if b'=' in item)
    if env.get(b'SLURM_JOB_ID') != JOB.encode():
        raise RuntimeError('Supervisor allocation identity mismatch')
    # Signal one verified supervisor. It cleans up only groups it created itself.
    os.kill(pid, signal.SIGTERM)
    write(DEPLOY/'services_stop_receipt.json', {'status': 'termination_requested',
          'pid': pid, 'job_id': JOB, 'at': now(), 'other_processes_signalled': False})
    print(json.dumps({'status': 'termination_requested', 'pid': pid}))


if __name__ == '__main__':
    main()

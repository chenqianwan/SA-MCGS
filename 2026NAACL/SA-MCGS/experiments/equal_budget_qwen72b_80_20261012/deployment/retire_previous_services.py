#!/usr/bin/env python3
"""Check, or explicitly retire, the completed job-415747 prior model services.

Default and --check-only only validate. --retire sends SIGTERM to the exact
verified old supervisor PID; that supervisor cleans up its own child groups.
Never cancels a job/step, sends SIGKILL, or changes historical result files.
Run in a CPU-only overlapping Slurm step on dgx-061 with CUDA_VISIBLE_DEVICES=''.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import time
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
REMOTE_PARENT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law')
OLD = REMOTE_PARENT / 'equal_budget_all80_20261009'
OLD_SOURCE = OLD / 'deployment/service_supervisor.py'
RUNTIME_PYTHON = '/aifs4su/hansirui/vllm-dsv4-venv/bin/python3'
JOB, OLD_STEP, OLD_PID, UID = '415747', '19', 979130, 1083
PORTS = tuple(range(19081, 19089))
RECEIPT = ROOT / 'deployment/previous_service_retirement.json'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def read_with_proof(path):
    content = path.read_bytes()
    return json.loads(content), {'path': str(path), 'sha256': hashlib.sha256(content).hexdigest()}


def write_receipt(data):
    temporary = RECEIPT.with_name(f'.{RECEIPT.name}.{os.getpid()}.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, RECEIPT)
    directory = os.open(RECEIPT.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def environment_identity():
    step = os.environ.get('SLURM_STEP_ID', '')
    visible = os.environ.get('CUDA_VISIBLE_DEVICES', '')
    step_gpus = os.environ.get('SLURM_STEP_GPUS', '')
    require(os.getuid() == UID, 'Require the authorized uid 1083')
    require(socket.gethostname().split('.')[0] == 'dgx-061', 'Require node dgx-061')
    require(os.environ.get('SLURM_JOB_ID') == JOB, 'Require existing allocation 415747')
    require(step.isdigit() and step != OLD_STEP, 'Require a separate numbered CPU-only Slurm step')
    require(step_gpus in ('', '-1', 'NoDevFiles') and visible in ('', '-1', 'NoDevFiles'),
            'Require CPU-only step: no SLURM_STEP_GPUS and empty CUDA_VISIBLE_DEVICES')
    require(ROOT == REMOTE_PARENT / 'equal_budget_qwen72b_80_20261012', 'Unexpected new-run root')
    return {'uid': UID, 'hostname': socket.gethostname(), 'job_id': JOB, 'step_id': step,
            'slurm_step_gpus': step_gpus, 'cuda_visible_devices': visible}


def complete_science():
    expected = [
        ('equal_budget_three_waves_20261010', 'complete', 1440),
        ('equal_budget_all80_20261009', 'complete', 480),
        ('equal_budget_all80_wave2_20261010', 'complete', 480),
        ('equal_budget_all80_wave3_20261010', 'complete', 480),
        ('component_mechanisms_20261010', 'complete_with_failures', 1200),
    ]
    evidence = []
    for name, status, count in expected:
        value, proof = read_with_proof(REMOTE_PARENT / name / 'execution/status.json')
        require(value.get('status') == status and value.get('final_results') == count
                and value.get('expected_results') == count,
                f'{name}: expected {status} with {count} terminal results')
        require(str(value.get('job_id')) == JOB, f'{name}: allocation mismatch')
        require(value.get('running_workers') == 0, f'{name}: workers are still running or count absent')
        workers = value.get('workers', [])
        require(all(type(worker.get('exit_code')) is int for worker in workers),
                f'{name}: an unfinished scientific worker remains')
        proof.update(status=value['status'], final_results=value['final_results'],
                     expected_results=value['expected_results'], running_workers=0,
                     recorded_workers=len(workers))
        evidence.append(proof)
    return evidence


def process_identity():
    proc = Path('/proc') / str(OLD_PID)
    require(proc.is_dir(), 'Prior supervisor PID is absent; inspect separately, no signal sent')
    require(proc.stat().st_uid == UID, 'Prior supervisor is not owned by uid 1083')
    command = [part.decode() for part in (proc / 'cmdline').read_bytes().split(b'\0') if part]
    allowed = ([RUNTIME_PYTHON, '-B', str(OLD_SOURCE)],
               [RUNTIME_PYTHON, '-B', str(OLD_SOURCE), '--root', str(OLD)])
    require(command in allowed, 'Prior PID command is not the exact known service supervisor')
    fields = (proc / 'stat').read_text().rsplit(')', 1)[1].strip().split()
    require(fields[0] != 'Z', 'Prior supervisor is already a zombie; no signal sent')
    # /proc/stat field 22, with the post-comm slice starting at field 3.
    started_ticks = int(fields[19])
    environ = dict(part.split(b'=', 1) for part in (proc / 'environ').read_bytes().split(b'\0')
                   if b'=' in part)
    require(environ.get(b'SLURM_JOB_ID') == JOB.encode()
            and environ.get(b'SLURM_STEP_ID') == OLD_STEP.encode(),
            'Prior process environment does not belong to job 415747 step 19')
    return {'pid': OLD_PID, 'uid': UID, 'command': command, 'starttime_ticks': started_ticks,
            'job_id': JOB, 'step_id': OLD_STEP, 'process_state': fields[0]}


def service_identity():
    value, proof = read_with_proof(OLD / 'deployment/service_state.json')
    require(str(value.get('job_id')) == JOB and str(value.get('step_id')) == OLD_STEP
            and value.get('pid') == OLD_PID
            and value.get('hostname', '').split('.')[0] == 'dgx-061'
            and value.get('status') == 'ready', 'Prior service state identity/status mismatch')
    replicas = value.get('replicas', [])
    require(len(replicas) == 8 and sorted(item.get('port', -1) for item in replicas) == list(PORTS),
            'Prior service ports are not exactly 19081..19088')
    proof.update(job_id=JOB, step_id=OLD_STEP, pid=OLD_PID, status=value['status'],
                 ports=list(PORTS), supervisor_source_sha256=hashlib.sha256(OLD_SOURCE.read_bytes()).hexdigest())
    return proof


METRIC = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})?\s+([^\s]+)(?:\s+.*)?$')
METRIC_GROUPS = {
    'running': ('vllm:num_requests_running',),
    'waiting': ('vllm:num_requests_waiting',),
    'kv_cache_usage': ('vllm:kv_cache_usage_perc', 'vllm:gpu_cache_usage_perc'),
}


def check_port_metrics(port):
    opener = build_opener(ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{port}/metrics', timeout=5) as response:
        content = response.read()
    readings = {key: [] for key in METRIC_GROUPS}
    for line in content.decode().splitlines():
        if not line or line.startswith('#'):
            continue
        match = METRIC.fullmatch(line)
        if not match:
            continue
        name, labels, raw = match.groups()
        for group, names in METRIC_GROUPS.items():
            if name in names:
                value = float(raw)
                require(math.isfinite(value) and value == 0,
                        f'Port {port}: {name} is not idle ({raw})')
                readings[group].append({'name': name, 'labels': labels or '', 'value': value})
    require(all(readings.values()), f'Port {port}: required running/waiting/KV metrics missing')
    return {'port': port, 'checked_at': now(), 'readings': readings,
            'metrics_sha256': hashlib.sha256(content).hexdigest()}


def idle_samples():
    evidence = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for index in range(3):
            sample = list(pool.map(check_port_metrics, PORTS))
            evidence.append({'sample': index + 1, 'at': now(), 'ports': sample})
            if index < 2:
                time.sleep(2)
    return evidence


def open_ports():
    result = []
    for port in PORTS:
        with socket.socket() as sock:
            sock.settimeout(.25)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                result.append(port)
    return result


def process_exit_state(started_ticks):
    proc = Path('/proc') / str(OLD_PID)
    try:
        fields = (proc / 'stat').read_text().rsplit(')', 1)[1].strip().split()
    except FileNotFoundError:
        return 'absent'
    require(int(fields[19]) == started_ticks, 'PID was reused after termination; no additional signal sent')
    return 'zombie' if fields[0] == 'Z' else 'running'


def pidfd_available():
    return callable(getattr(os, 'pidfd_open', None)) and callable(getattr(signal, 'pidfd_send_signal', None))


def signal_previous_supervisor(expected_identity, pidfd):
    # Recheck every stable identity field immediately before the one permitted
    # signal. Some shared Python runtimes do not expose the Linux pidfd API.
    fresh = process_identity()
    identity_fields = ('pid', 'uid', 'command', 'starttime_ticks', 'job_id', 'step_id')
    require(all(fresh.get(key) == expected_identity.get(key) for key in identity_fields),
            'Prior supervisor identity changed before termination; no signal sent')
    if pidfd is not None:
        signal.pidfd_send_signal(pidfd, signal.SIGTERM, None, 0)
    else:
        os.kill(OLD_PID, signal.SIGTERM)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check-only', action='store_true', help='Validate only; this is the default.')
    mode.add_argument('--retire', action='store_true', help='Explicitly allow one SIGTERM to verified PID 979130.')
    args = parser.parse_args()
    context = environment_identity()
    evidence = {'version': 1, 'mode': 'retire' if args.retire else 'check_only',
                'started_at': now(), 'context': context, 'target_root': str(OLD),
                'target_pid': OLD_PID, 'job_id': JOB, 'target_step_id': OLD_STEP,
                'signal': 'SIGTERM', 'signal_sent': False,
                'historical_result_changes': False, 'allocation_cancelled': False}
    # A lock only in the new run prevents duplicate retirement invocations.
    with (ROOT / 'deployment/previous_service_retirement.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if RECEIPT.exists():
            old_receipt, _ = read_with_proof(RECEIPT)
            require(old_receipt.get('signal_sent') is not True
                    and old_receipt.get('signal_requested') is not True,
                    'A retirement intent or signal was already recorded; inspect that receipt before another attempt')
        pidfd = None
        try:
            evidence['science_completion'] = complete_science()
            evidence['service_identity'] = service_identity()
            evidence['process_identity'] = process_identity()
            if args.retire and pidfd_available():
                pidfd = os.pidfd_open(OLD_PID, 0)
            evidence['idle_metric_samples'] = idle_samples()
            fresh = process_identity()
            require(fresh['starttime_ticks'] == evidence['process_identity']['starttime_ticks'],
                    'Prior PID changed during validation')
            evidence['science_completion_recheck'] = complete_science()
            evidence['service_identity_recheck'] = service_identity()
            evidence.update(status='checks_passed', checks_passed_at=now())
            if not args.retire:
                print(json.dumps(evidence, ensure_ascii=False), flush=True)
                return 0
            evidence.update(status='termination_intent', signal_requested=True, termination_intent_at=now(),
                            signal_backend='pidfd' if pidfd is not None else 'verified_pid')
            write_receipt(evidence)
            signal_previous_supervisor(evidence['process_identity'], pidfd)
            evidence.update(status='termination_sent', signal_sent=True, signal_sent_at=now())
            write_receipt(evidence)
            deadline = time.monotonic() + 180
            while True:
                exit_state = process_exit_state(fresh['starttime_ticks'])
                occupied = open_ports()
                if exit_state in ('absent', 'zombie') and not occupied:
                    break
                require(time.monotonic() < deadline,
                        'Graceful retirement not confirmed within 180 seconds; no force kill attempted')
                time.sleep(2)
            final_state, final_proof = read_with_proof(OLD / 'deployment/service_state.json')
            evidence.update(status='retired', completed_at=now(), process_exit_state=exit_state,
                            service_ports_closed=True, final_service_state=final_state.get('status'),
                            final_service_state_file=final_proof)
            write_receipt(evidence)
            print(json.dumps({'status': 'retired', 'pid': OLD_PID, 'service_ports_closed': True,
                              'receipt': str(RECEIPT)}, ensure_ascii=False), flush=True)
            return 0
        except BaseException as error:
            evidence.update(status='failed', failed_at=now(), error_type=type(error).__name__, error=str(error))
            if args.retire:
                write_receipt(evidence)
            raise
        finally:
            if pidfd is not None:
                os.close(pidfd)


if __name__ == '__main__':
    raise SystemExit(main())

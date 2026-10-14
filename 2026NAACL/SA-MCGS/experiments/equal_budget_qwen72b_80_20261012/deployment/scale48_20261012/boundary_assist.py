#!/usr/bin/env python3
"""Bounded helper: catch remaining settled request boundaries and hand them off.

No TERM, inference, source/result edits, or restart. The existing checkpoint
controller remains authoritative. Only this helper's unadopted pauses can be
continued by its cleanup. Linux inotify close-write events avoid expensive
whole-ledger polling; the existing frozen audit remains mandatory after STOP.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import ctypes
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import threading
import time

import drain as d
import checkpoint_drain as c

ROOT, HERE = d.ROOT, d.HERE
STOP = threading.Event()
TIMEOUT_SECONDS = 300
RECEIPTS = HERE/'boundary_assist_receipts'


class IncrementalLedger:
    """Append-only hints; authoritative accounting is checked only while stopped."""
    def __init__(self, path):
        self.path = path
        self.inode = None
        self.offset = 0
        self.partial = b''
        self.calls = {}
        self.header = False

    def settled_hint(self):
        with self.path.open('rb') as stream:
            stat = os.fstat(stream.fileno())
            identity = (stat.st_dev, stat.st_ino)
            d.require(self.inode in (None, identity) and stat.st_size >= self.offset,
                      'Ledger was replaced or truncated')
            self.inode = identity
            stream.seek(self.offset)
            content = stream.read()
        self.offset += len(content)
        pieces = (self.partial+content).split(b'\n')
        self.partial = pieces.pop()
        for line in pieces:
            event = json.loads(line)
            kind = event.get('event')
            if not self.header:
                d.require(kind == 'header', 'Ledger header missing')
                self.header = True
            elif kind == 'reserve':
                d.require(event['call_id'] not in self.calls, 'Duplicate reservation')
                self.calls[event['call_id']] = 'reserved'
            elif kind == 'finish':
                d.require(self.calls.get(event['call_id']) == 'reserved', 'Unknown or duplicate finish')
                d.require(event.get('status') == 'completed_with_usage' and not event.get('usage_issues')
                          and not event.get('error_type'), 'Unknown/failed settlement')
                self.calls[event['call_id']] = 'completed_with_usage'
            elif kind == 'parse':
                d.require(event.get('call_id') in self.calls, 'Unknown parse call')
            else:
                d.require(kind == 'owner', 'Unexpected ledger event')
        return bool(self.calls) and not self.partial and all(v == 'completed_with_usage' for v in self.calls.values())


class CloseWriteWatch:
    def __init__(self, path):
        self.fd = None
        self.backend = 'bounded_poll'
        libc = ctypes.CDLL(None, use_errno=True)
        if hasattr(libc, 'inotify_init1') and hasattr(libc, 'inotify_add_watch'):
            libc.inotify_init1.argtypes = [ctypes.c_int]
            libc.inotify_init1.restype = ctypes.c_int
            libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
            libc.inotify_add_watch.restype = ctypes.c_int
            fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
            if fd >= 0:
                if libc.inotify_add_watch(fd, os.fsencode(path), 0x8 | 0x400 | 0x800) >= 0:
                    self.fd, self.backend = fd, 'inotify_close_write'
                else:
                    os.close(fd)

    def wait(self):
        if self.fd is None:
            STOP.wait(.005)
            return
        ready, _, _ = select.select([self.fd], [], [], .25)
        if ready:
            try:
                os.read(self.fd, 65536)
            except BlockingIOError:
                pass

    def close(self):
        if self.fd is not None:
            os.close(self.fd)


def adoption(name, proof):
    for path in (HERE/'checkpoint_status.json', HERE/'checkpoint_ready.json', HERE/'checkpoint_termination_intent.json'):
        if not path.exists():
            continue
        value = d.read(path)
        row = value.get('frozen_workers', {}).get(name, {})
        if (row.get('pid') == proof['pid'] and row.get('initial_identity') == proof['initial_identity']
                and row.get('boundary_verified') is True):
            return {'path': str(path.relative_to(ROOT)), 'observed_at': d.now(), 'sha256': d.sha(path)}
    return None


def controller_alive(identity):
    current = d.process_snapshot(identity['pid'])
    d.require(current is None or current == identity, 'Checkpoint controller PID identity changed')
    return current is not None


def stable_unsettled(path):
    """Only stable, definite held/partial evidence permits an immediate CONT."""
    try:
        data = path.read_bytes()
        if data != path.read_bytes():
            return None
        if not data.endswith(b'\n'):
            return {'reason': 'stable_incomplete_ledger_line', 'ledger_sha256': __import__('hashlib').sha256(data).hexdigest()}
        calls = {}
        for line in data.splitlines():
            row = json.loads(line)
            if row.get('event') == 'reserve':
                calls[row['call_id']] = 'reserved'
            elif row.get('event') == 'finish':
                calls[row['call_id']] = row.get('status')
        if any(status != 'completed_with_usage' for status in calls.values()):
            return {'reason': 'stable_unsettled_reservation', 'ledger_sha256': __import__('hashlib').sha256(data).hexdigest()}
    except (OSError, ValueError, KeyError):
        pass
    return None


def resolve_pause(name, proof, controller, save):
    """After STOP, unknown ownership cannot be resolved by an automatic timeout.

    The original controller may already have adopted a pause in memory. Keep
    waiting for its durable acknowledgment or confirmed process exit. A prior
    TERM intent forbids autonomous continuation even after that process exits.
    """
    started = time.monotonic()
    while True:
        transfer = adoption(name, proof)
        if transfer:
            save(status='adopted_by_controller', adoption=transfer)
            return True
        current = c.verify_worker(proof, allow_absent=True)
        if current is None:
            save(status='worker_exited_without_helper_signal')
            return True
        if current['state'] != 'T':
            save(status='controller_released_pause', observed_at=d.now())
            return True
        if not controller_alive(controller):
            if (HERE/'checkpoint_termination_intent.json').exists() or (HERE/'checkpoint_signals.json').exists():
                save(status='needs_attention', error='Controller exited after termination intent; no autonomous CONT')
                return False
            c.send_verified(proof, signal.SIGCONT, require_stopped=True)
            save(status='continued_after_controller_exit', cleanup_continued_at=d.now(), own_pause_released=True)
            return False
        if time.monotonic()-started > 30:
            save(status='waiting_for_safe_ownership_resolution', controller_still_alive=True,
                 capture_timeout_does_not_authorize_cont=True)
            started = time.monotonic()
        time.sleep(.1)


def watch_one(name, proof, controller, tasks, deadline):
    by_key = {d.task_key(t): t for t in tasks}
    receipt = {'worker': name, 'pid': proof['pid'], 'identity': proof['initial_identity'],
               'started_at': d.now(), 'status': 'watching', 'stop_count': 0, 'continue_count': 0,
               'signals_permitted': ['SIGSTOP', 'SIGCONT'], 'scientific_model_calls': 0}
    output = RECEIPTS/(name+'.json')
    own_pause, handed_off, observer = False, False, None
    def save(**fields):
        receipt.update(fields, updated_at=d.now())
        d.save(output, receipt)
    save()
    try:
        task = c.worker_task(name, by_key)
        d.require(task is not None, 'No current arm for helper target')
        ledger = ROOT/'results/qwen25'/task['case_uid']/task['method']/'ledger.jsonl'
        hint = IncrementalLedger(ledger)
        observer = CloseWriteWatch(ledger)
        save(watch_backend=observer.backend, task=d.task_key(task))
        while True:
            d.require(not STOP.is_set(), 'Boundary helper was interrupted')
            d.require(time.monotonic() < deadline, 'Boundary helper reached its five-minute deadline')
            transfer = adoption(name, proof)
            if transfer:
                handed_off = True
                save(status='adopted_by_controller', adoption=transfer)
                return receipt
            d.require(controller_alive(controller), 'Checkpoint controller exited before handoff')
            state = d.read(HERE/'checkpoint_status.json')
            d.require(state.get('status') == 'finding_request_boundaries',
                      'Checkpoint controller left boundary discovery before handoff')
            current = c.verify_worker(proof, allow_absent=True)
            if current is None:
                save(status='worker_exited_without_helper_signal')
                return receipt
            if own_pause:
                d.require(current['state'] == 'T', 'Helper-owned worker resumed unexpectedly')
                STOP.wait(.05)
                continue
            if current['state'] == 'T':  # Another controller owns this pause; never adopt it as ours.
                STOP.wait(.05)
                continue
            current_task = c.worker_task(name, by_key)
            d.require(current_task is not None, 'Current arm unavailable')
            if d.task_key(current_task) != d.task_key(task):
                observer.close()
                task = current_task
                ledger = ROOT/'results/qwen25'/task['case_uid']/task['method']/'ledger.jsonl'
                hint, observer = IncrementalLedger(ledger), CloseWriteWatch(ledger)
                save(task=d.task_key(task), watch_backend=observer.backend)
            if not hint.settled_hint():
                observer.wait()
                continue
            c.send_verified(proof, signal.SIGSTOP)
            own_pause = True
            receipt['stop_count'] += 1
            expires = time.monotonic()+2
            while c.verify_worker(proof)['state'] != 'T':
                d.require(time.monotonic() < expires, 'SIGSTOP failed to reach T')
                time.sleep(.001)
            try:
                current_task = c.worker_task(name, by_key)
                d.require(current_task is not None, 'Current arm disappeared')
                current_ledger = ROOT/'results/qwen25'/current_task['case_uid']/current_task['method']/'ledger.jsonl'
                boundary = c.ledger_cache_proof(current_ledger, current_task)
            except (RuntimeError, FileNotFoundError, ValueError, KeyError, IndexError) as error:
                # A transient cache/IO error does not prove that the main
                # controller has not already adopted this T-state worker.
                definite = stable_unsettled(current_ledger) if 'current_ledger' in locals() else None
                if definite is not None:
                    c.send_verified(proof, signal.SIGCONT, require_stopped=True)
                    own_pause = False
                    receipt['continue_count'] += 1
                    save(status='watching', last_raced_boundary_at=d.now(), continue_proof=definite)
                    observer.wait()
                    continue
                save(status='waiting_for_safe_ownership_resolution', audit_error=str(error))
                handed_off = resolve_pause(name, proof, controller, save)
                own_pause = False
                return receipt
            save(status='awaiting_controller_adoption', boundary=boundary, verified_stopped_at=d.now())
    except BaseException as error:
        save(status='failed', error_type=type(error).__name__, error=str(error))
        return receipt
    finally:
        if own_pause and not handed_off:
            handed_off = resolve_pause(name, proof, controller, save)
        if observer is not None:
            observer.close()


def main():
    context = d.environment_identity()
    os.umask(0o077)
    with (HERE/'boundary_assist.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        d.require(not (HERE/'boundary_assist.json').exists() and not RECEIPTS.exists(),
                  'Preserve earlier helper evidence; no automatic repeated launch')
        initial = d.read(HERE/'checkpoint_initial.json')
        status = d.read(HERE/'checkpoint_status.json')
        d.require(status.get('status') == 'finding_request_boundaries', 'Checkpoint no longer needs a helper')
        controller = d.process_snapshot(initial['context']['pid'])
        d.require(controller is not None and controller['uid'] == d.UID and controller['job_id'] == d.JOB
                  and controller['step_id'] == initial['context']['step_id']
                  and context['step_id'] != controller['step_id']
                  and controller['argv'] == [d.PYTHON, '-B', str(HERE/'checkpoint_drain.py')],
                  'Helper requires an independent step and the exact existing checkpoint controller')
        tasks, _, _ = d.load_tasks(ROOT)
        pending = {n: p for n, p in initial['watched_processes'].items()
                   if n.startswith('qwen25-') and n not in status.get('frozen_workers', {})}
        d.require(0 < len(pending) <= 8, 'Helper only covers at most eight remaining original workers')
        RECEIPTS.mkdir(mode=0o700)
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda signum, frame: STOP.set())
        receipt = {'context': context, 'controller_identity': controller, 'started_at': d.now(),
                   'status': 'watching', 'targets': sorted(pending), 'timeout_seconds': TIMEOUT_SECONDS,
                   'scientific_model_calls': 0, 'sigterm_signals': 0, 'workers': []}
        d.save(HERE/'boundary_assist.json', receipt)
        deadline = time.monotonic()+TIMEOUT_SECONDS
        with ThreadPoolExecutor(max_workers=len(pending)) as pool:
            jobs = {pool.submit(watch_one, n, p, controller, tasks, deadline) for n, p in pending.items()}
            while jobs:
                finished, jobs = wait(jobs, timeout=1, return_when=FIRST_COMPLETED)
                for future in finished:
                    receipt['workers'].append(future.result())
                receipt['updated_at'] = d.now()
                d.save(HERE/'boundary_assist.json', receipt)
        receipt.update(status='complete' if all(w['status'] in ('adopted_by_controller', 'controller_released_pause',
                       'worker_exited_without_helper_signal') for w in receipt['workers']) else 'failed', ended_at=d.now())
        d.save(HERE/'boundary_assist.json', receipt)
        return 0 if receipt['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())

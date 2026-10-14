#!/usr/bin/env python3
"""Reconcile the completed 32-worker retirement after an exit-observation error.

Additive evidence only: no signals, model calls, retries, or edits to prior
receipts/scientific files. The failed checkpoint remains failed in its original
record. A new receipt independently proves that its intended cleanup completed.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import re

import drain as d
import checkpoint_drain as c
import restart_after_drain as r

ROOT, HERE = d.ROOT, d.HERE
OLD_CONTROLLER_PID, OLD_CHECKPOINT_PID, OLD_STEP = 1676546, 1676547, '48'
STATE_FILES = ('deployment/pipeline_status.json', 'deployment/service_state.json', 'execution/status.json')
EVIDENCE_FILES = ('controller_launch_receipt.json', 'controller_status.json',
                  'checkpoint_initial.json', 'checkpoint_status.json', 'checkpoint_ready.json',
                  'checkpoint_termination_intent.json', 'checkpoint_signals.json',
                  'replay_preflight_frozen.json')


def absent_or_zombie(pid):
    """Read only stat: never read environ for a process already terminating."""
    d.require(type(pid) is int and pid > 1, 'Invalid prior PID')
    try:
        fields = (Path('/proc')/str(pid)/'stat').read_text().rsplit(')', 1)[1].strip().split()
        d.require(fields[0] in ('Z', 'X'), 'A prior process is still live: '+str(pid))
        return {'pid': pid, 'state': fields[0], 'start_ticks': int(fields[19])}
    except FileNotFoundError:
        return {'pid': pid, 'state': 'absent'}


def validate_signal_events(events, watched, frozen):
    workers = {name: proof for name, proof in watched.items() if name.startswith('qwen25-')}
    expected = {f'qwen25-{replica}_worker{index}' for replica in range(4) for index in range(8)}
    d.require(set(workers) == expected and len(events) == 32
              and {event.get('worker') for event in events} == expected,
              'The completed signal receipt must cover exactly 32 original workers')
    d.require(set(frozen) == expected, 'Frozen worker coverage changed')
    for event in events:
        proof = workers[event['worker']]
        pause = frozen[event['worker']]
        d.require(event.get('pid') == proof['pid'] and event.get('identity') == proof['initial_identity']
                  and pause.get('pid') == proof['pid'] and pause.get('initial_identity') == proof['initial_identity']
                  and pause.get('boundary_verified') is True and pause.get('already_exited') is False,
                  'Worker identity or verified boundary changed')
        times = [event.get(name) for name in ('sigterm_intent_at', 'sigterm_sent_at', 'sigcont_sent_at')]
        d.require(all(isinstance(value, str) and value for value in times) and times == sorted(times),
                  'A worker lacks the complete ordered TERM/CONT evidence')
        identity = proof['initial_identity']
        replica, index = event['worker'].split('_worker')
        d.require(identity.get('uid') == d.UID and identity.get('job_id') == d.JOB
                  and identity.get('step_id') == d.WORKER_STEP and identity.get('pid') == proof['pid']
                  and identity.get('argv') == [d.PYTHON, '-B', str(ROOT/'runner.py'),
                                             '--replica-id', replica, '--worker-index', index],
                  'Signal proof is outside the original experiment')


def validate_failure(failed, controller):
    d.require(failed.get('status') == 'failed' and failed.get('error_type') == 'PermissionError'
              and re.fullmatch(r"\[Errno 13\] Permission denied: '/proc/[0-9]+/environ'", failed.get('error', ''))
              and failed.get('partial_termination') is True,
              'This reconciliation is restricted to the observed post-termination proc permission error')
    d.require(failed.get('context', {}).get('pid') == OLD_CHECKPOINT_PID
              and str(failed['context'].get('step_id')) == OLD_STEP,
              'Unexpected original checkpoint identity')
    d.require(controller.get('pid') == OLD_CONTROLLER_PID and str(controller.get('job_id')) == d.JOB
              and str(controller.get('step_id')) == OLD_STEP and controller.get('status') == 'needs_attention'
              and controller.get('error') == 'Checkpoint drain failed; no service restart requested',
              'Unexpected outer controller terminal state')
    for item in failed.get('cleanup_continuations', []):
        d.require(not item.get('continued_at') and item.get('error')
                  and re.fullmatch(r"\[Errno 13\] Permission denied: '/proc/[0-9]+/environ'", item['error']),
                  'A worker was resumed, or cleanup encountered a different failure')


def audit_completed(context):
    evidence = {name: d.read(HERE/name) for name in EVIDENCE_FILES}
    evidence_hashes = {str((HERE/name).relative_to(ROOT)): d.sha(HERE/name) for name in EVIDENCE_FILES}
    initial, failed, ready, intent, sent = (evidence[name] for name in (
        'checkpoint_initial.json', 'checkpoint_status.json', 'checkpoint_ready.json',
        'checkpoint_termination_intent.json', 'checkpoint_signals.json'))
    validate_failure(failed, evidence['controller_status.json'])
    d.require(str(context['step_id']) != OLD_STEP, 'Reconciliation requires a new independent CPU step')
    d.require(ready.get('status') == 'frozen_replay_check' and intent.get('status') == 'termination_intent'
              and ready.get('schema') == intent.get('schema') == initial.get('schema') == 'qwen48_request_checkpoint_v1',
              'Original checkpoint phases are incomplete')
    for name, expected in evidence['controller_launch_receipt.json']['source_sha256'].items():
        d.require(r.sha(r.local_path(name)) == expected, 'Original checkpoint implementation changed: '+name)
    tasks, protocol_hash, sources = d.load_tasks(ROOT)
    for old in (initial, failed, ready, intent):
        d.require(old.get('source_sha256') == sources and old.get('protocol_sha256') == protocol_hash
                  and old.get('context') == initial['context']
                  and old.get('watched_processes') == initial['watched_processes'],
                  'Original scientific or process identity differs across checkpoint phases')
    audit = c.frozen_audit(tasks, protocol_hash)
    d.require(audit == ready.get('frozen_audit') == intent.get('audit'),
              'Scientific files changed after the frozen checkpoint; reconciliation refused')
    signals = sent.get('signals', [])
    validate_signal_events(signals, initial['watched_processes'], intent['frozen_workers'])
    d.require(signals == failed.get('signals') and sent.get('replay_proof') == intent.get('replay_proof'),
              'Final signal/replay evidence is inconsistent')
    c.validate_replay(evidence['replay_preflight_frozen.json'], audit, protocol_hash)
    pids = {OLD_CONTROLLER_PID, OLD_CHECKPOINT_PID}
    pids.update(item['pid'] for item in initial['watched_processes'].values())
    observed_exits = [absent_or_zombie(pid) for pid in sorted(pids)]
    states = d.states(ROOT)
    d.require(all(row.get('exit_code') == -15 for row in states['workers']['workers']),
              'The original 32 workers did not all exit by the recorded TERM')
    drained = {**intent, 'status': 'drained', 'completed_at': d.now(), 'audit': audit, 'signals': signals,
               'final_states': states, 'replay_proof': intent['replay_proof'],
               'all_original_processes_exited': True, 'old_service_ports_closed': True,
               'endpoints_absent': True, 'old_services_stopped': True, 'zero_live_scientific_processes': True,
               'claim_locks_held_at_validation': 160, 'claim_locks_release': 'confirmed',
               'state_files_sha256': {name: d.sha(ROOT/name) for name in STATE_FILES}}
    r.verify_drain_receipt(drained)
    r.verify_old_stopped(drained)
    r.verify_scientific_files(drained)
    d.require(states['workers'].get('final_results') == states['pipeline'].get('final_results') == audit['final_results'],
              'Terminal result count differs from the frozen audit')
    # Existing claim files only: do not create or replace any original task lock.
    for task in tasks:
        claim = ROOT/'execution/claims/qwen25'/(d.task_key(task)+'.lock')
        d.require(claim.is_file() and not claim.is_symlink(), 'An original claim lock is missing or redirected')
    claims = d.ClaimLocks(ROOT, tasks)
    try:
        d.require(claims.acquire_available() == 160, 'At least one original arm remains claimed')
        d.require(c.frozen_audit(tasks, protocol_hash) == audit, 'Scientific files changed during reconciliation')
        d.require(d.states(ROOT) == states, 'Original terminal states changed during reconciliation')
        d.require(all(d.sha(ROOT/name) == value for name, value in evidence_hashes.items()),
                  'Original checkpoint evidence changed during reconciliation')
    finally:
        claims.close()
    drained['claim_locks_released_at'] = d.now()
    reconciliation = {'schema': 'qwen48_completed_checkpoint_reconciliation_v1', 'status': 'passed',
                      'context': context, 'completed_at': d.now(), 'original_failure_preserved': True,
                      'reason': 'All 32 planned TERM/CONT actions completed; prior observer failed reading terminating proc environ.',
                      'prior_evidence_sha256': evidence_hashes, 'original_checkpoint_context': initial['context'],
                      'source_sha256': sources, 'state_files_sha256': drained['state_files_sha256'],
                      'replay_proof': drained['replay_proof'], 'frozen_audit_sha256': d.digest(audit),
                      'scientific_result_tree_unchanged': True, 'signal_events_validated': 32,
                      'process_exit_observations': observed_exits, 'claim_locks_acquired': 160,
                      'claim_locks_release': 'confirmed', 'scientific_model_calls': 0, 'scientific_retries': 0,
                      'signals_sent': 0, 'script_sha256': d.sha(Path(__file__).resolve())}
    return reconciliation, drained


def main():
    context = d.environment_identity()
    os.umask(0o077)
    output = HERE/'checkpoint_reconciliation.json'
    with (HERE/'checkpoint_reconciliation.lock').open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        d.require(not output.exists() and not (HERE/'drained_receipt.json').exists(),
                  'Prior reconciliation/drain evidence exists; do not repeat an uncertain write')
        try:
            reconciliation, drained = audit_completed(context)
            d.save(output, reconciliation)
            drained['reconciliation'] = {'path': str(output.relative_to(ROOT)), 'sha256': d.sha(output),
                                         'status': 'passed', 'context': context,
                                         'original_failed_checkpoint_preserved': True}
            r.verify_drain_receipt(drained)
            d.save(HERE/'drained_receipt.json', drained)
        except BaseException as error:
            if not output.exists():
                d.save(output, {'status': 'failed', 'context': context, 'failed_at': d.now(),
                               'error_type': type(error).__name__, 'error': str(error),
                               'scientific_model_calls': 0, 'signals_sent': 0})
            raise
    print('Completed-checkpoint reconciliation passed; no signals or scientific calls were made.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

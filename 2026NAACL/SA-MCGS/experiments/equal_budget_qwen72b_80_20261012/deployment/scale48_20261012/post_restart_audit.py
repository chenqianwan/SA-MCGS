#!/usr/bin/env python3
"""Read-only shared-files audit of the 48-worker run and resumed cache prefixes.

Does not import or call a model client, contact a server, signal processes, change
configuration, lock a live ledger, or modify scientific artifacts.  --output may
save this audit's receipt only inside its recovery directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EXPECTED = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')
MODEL = 'qwen2.5-72b-instruct'
METHODS = ('lea', 'full-scc')
JOB, NODE = '415747', 'dgx-061'


class AuditError(Exception):
    pass


class SnapshotRetry(Exception):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return sha_bytes(Path(path).read_bytes())


def digest(value):
    return sha_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False,
                               separators=(',', ':'), allow_nan=False).encode())


def local_path(relative):
    name = Path(relative)
    require(not name.is_absolute() and '..' not in name.parts, 'Unsafe proof path: ' + str(relative))
    path = ROOT / name
    require(path.resolve() == path, 'Redirected proof path: ' + str(relative))
    return path


def stamp(path):
    stat = path.stat()
    return stat.st_ino, stat.st_size, stat.st_mtime_ns


def stable_arm_snapshot(folder):
    """A ledger/final pair must stand still for the short file-read interval."""
    ledger = folder / 'ledger.jsonl'
    last_reason = 'files changed while reading'
    for _ in range(3):
        try:
            before = stamp(ledger)
            raw = ledger.read_bytes()
            final_path = folder / 'final.json'
            final_raw = final_path.read_bytes() if final_path.exists() else None
            after = stamp(ledger)
            if before != after or len(raw) != after[1]:
                time.sleep(.02)
                continue
            complete_end = raw.rfind(b'\n') + 1
            if complete_end != len(raw) or not complete_end:
                last_reason = 'ledger has an unfinished trailing record'
                time.sleep(.02)
                continue
            final = json.loads(final_raw) if final_raw is not None else None
            return raw, final
        except FileNotFoundError:
            last_reason = 'arm was being initialized'
            time.sleep(.02)
    raise SnapshotRetry(str(folder.relative_to(ROOT)) + ': ' + last_reason)


def parse_ledger(raw, owner, cap):
    require(raw.endswith(b'\n'), 'Incomplete ledger cannot be audited')
    events = [json.loads(line) for line in raw.splitlines()]
    require(bool(events) and all(events[0].get(k) == v for k, v in {
        'event': 'header', 'version': 1, 'accounting': 'actual_local_vllm_tokens',
        'external_api_enabled': False, 'unknown_outcome': 'retain_full_reservation'}.items()),
        'Unexpected ledger header')
    calls, requests, owners, freezes = {}, set(), set(), set()
    for event in events[1:]:
        kind = event.get('event')
        if kind == 'owner':
            identity = tuple(event['owner'])
            require(identity == owner and identity not in owners and event.get('token_cap') == cap,
                    'Duplicate owner or changed owner/cap')
            owners.add(identity)
        elif kind == 'reserve':
            cid = event['call_id']
            identity = tuple(event['owner'])
            key = (*identity, event['request_key'])
            require(identity == owner and identity in owners, 'Unregistered or changed reservation owner')
            require(cid not in calls and key not in requests, 'Duplicate call or owner/request_key reservation')
            require(type(event.get('input_tokens')) is int and event['input_tokens'] >= 0
                    and type(event.get('max_output_tokens')) is int and event['max_output_tokens'] > 0
                    and event.get('reserved_tokens') == event['input_tokens'] + event['max_output_tokens'],
                    'Invalid token reservation')
            calls[cid] = {**event, 'status': 'reserved'}
            requests.add(key)
        elif kind == 'finish':
            cid = event['call_id']
            require(cid in calls and calls[cid]['status'] == 'reserved', 'Duplicate or unknown settlement')
            row = calls[cid]
            require(event.get('status') == 'completed_with_usage' and not event.get('usage_issues')
                    and not event.get('error_type'), 'Unknown/missing/mismatched provider usage or provider error')
            prompt, completion, total = (event.get(key) for key in
                                         ('prompt_tokens', 'completion_tokens', 'actual_total_tokens'))
            require(all(type(value) is int and value >= 0 for value in (prompt, completion, total))
                    and prompt == row['input_tokens'] and completion <= row['max_output_tokens']
                    and total == prompt + completion and event.get('provider_model') == MODEL,
                    'Settled provider token count/model mismatch')
            usage = event.get('usage', {})
            require(usage.get('prompt_tokens') == prompt and usage.get('completion_tokens') == completion
                    and usage.get('total_tokens', total) == total, 'Provider usage differs from ledger settlement')
            row.update(event)
        elif kind == 'parse':
            require(event['call_id'] in calls, 'Parse record refers to an unknown call')
        elif kind == 'freeze_budget':
            identity = (event['case_id'], event['model'])
            require(identity not in freezes, 'Duplicate budget freeze')
            freezes.add(identity)
        else:
            raise AuditError('Unknown ledger event: ' + str(kind))
    settled = [row for row in calls.values() if row['status'] == 'completed_with_usage']
    pending = [row for row in calls.values() if row['status'] == 'reserved']
    require(len(pending) <= 1, 'Multiple pending requests in one sequential arm')
    prompt = sum(row['prompt_tokens'] for row in settled)
    completion = sum(row['completion_tokens'] for row in settled)
    used = sum(row['actual_total_tokens'] for row in settled)
    held = sum(row['reserved_tokens'] for row in pending)
    require(used + held <= cap, 'Accounted tokens including pending reservation exceed frozen cap')
    return calls, {'calls': len(calls), 'completed_with_usage': len(settled), 'pending_calls': len(pending),
                   'held_calls': len(pending), 'prompt_tokens': prompt, 'completion_tokens': completion,
                   'total_tokens': used, 'held_tokens': held, 'accounted_tokens': used + held,
                   'usage_mismatch_calls': 0}


def check_cache(folder, row):
    path = Path(row['cache_file'])
    path = path if path.is_absolute() else folder / path
    require(path.resolve() == path and path.is_relative_to(folder / 'calls'), 'Response cache escapes its arm')
    cached = read(path)
    result = cached.get('result')
    require(cached.get('call_id') == row['call_id'] and cached.get('request_hash') == row['request_hash']
            and isinstance(result, dict) and digest(result) == row.get('response_sha256'),
            'Cached response identity/content changed')
    usage = result.get('usage', {})
    require(result.get('model') == MODEL and usage.get('prompt_tokens') == row['prompt_tokens']
            and usage.get('completion_tokens') == row['completion_tokens']
            and usage.get('total_tokens') == row['actual_total_tokens'], 'Cached response token usage changed')


def audit_configuration():
    scope = read(ROOT / 'run_scope.json')
    require(scope.get('models') == ['qwen25'] and scope.get('execution_methods') == list(METHODS)
            and scope.get('expected_results') == 160 and scope.get('cases_per_model') == 80
            and scope.get('sa_execution_enabled') is False, 'Scientific scope changed')
    require(read(ROOT / 'execution_config.json') == {'workers_per_replica': {'qwen25': 12}},
            'Worker configuration is not twelve per replica')
    worker = read(ROOT / 'execution/status.json')
    service = read(ROOT / 'deployment/service_state.json')
    pipeline = read(ROOT / 'deployment/pipeline_status.json')
    controller_path = HERE / 'recovery_controller_status.json'
    if not controller_path.exists():
        controller_path = HERE / 'controller_status.json'
    controller = read(controller_path)
    require(str(pipeline.get('step_id')) == str(controller.get('step_id'))
            and pipeline.get('status') == 'workers_running', 'Replacement pipeline is not active in its independent controller step')
    require(all(str(state.get('job_id')) == JOB for state in (worker, service, pipeline, controller)),
            'Unexpected allocation identity')
    require(worker.get('status') == 'running' and worker.get('running_workers') == 48
            and worker.get('expected_results') == 160 and worker.get('sa_execution_enabled') is False
            and worker.get('external_api_enabled') is False, 'Expected 48 active authorized scientific workers')
    require(time.time() - worker.get('updated_unix', 0) < 90, 'Worker status is stale')
    names = {f'qwen25-{replica}_worker{index}' for replica in range(4) for index in range(12)}
    workers = worker.get('workers', [])
    require(len(workers) == 48 and {item['name'] for item in workers} == names
            and len({item['pid'] for item in workers}) == 48
            and all(item.get('exit_code') is None and str(ROOT / 'runner.py') in item.get('command', []) for item in workers),
            'Worker identities/commands/exit codes do not prove 48 active slots')
    process_check = 'fresh_supervisor_receipt_only_on_noncompute_host'
    if socket.gethostname().split('.')[0] == NODE:
        for item in workers:
            process = Path('/proc') / str(item['pid'])
            try:
                process_state = (process / 'stat').read_text().rsplit(')', 1)[1].strip().split()[0]
                argv = (process / 'cmdline').read_bytes().split(b'\0')
                environment = dict(field.split(b'=', 1) for field in (process / 'environ').read_bytes().split(b'\0') if b'=' in field)
                require(process.stat().st_uid == 1083 and process_state not in ('Z', 'T', 't')
                        and str(ROOT / 'runner.py').encode() in argv
                        and environment.get(b'SLURM_JOB_ID') == JOB.encode()
                        and environment.get(b'SLURM_STEP_ID') == str(worker['step_id']).encode(),
                        'Worker PID identity/state does not match its active supervisor receipt')
            except FileNotFoundError:
                raise AuditError('Worker PID exited after the supervisor status snapshot: ' + item['name'])
        process_check = 'all_48_compute_node_pids_verified'
    require(service.get('status') == 'ready' and service.get('hostname', '').split('.')[0] == NODE
            and len(service.get('replicas', [])) == 4
            and all(item.get('status') == 'healthy' for item in service['replicas'])
            and not any(service.get('health_failures', {}).values()), 'Four healthy services are not verified')
    endpoints = read(ROOT / 'endpoints.json')
    require(endpoints.get('service_supervisor_pid') == service['pid']
            and str(endpoints.get('service_step_id')) == str(service['step_id'])
            and set(endpoints.get('models', {})) == {'qwen25'}
            and len(endpoints.get('replicas', [])) == 4, 'Published endpoints do not belong to the replacement service')
    for index in range(4):
        command = read(ROOT / 'deployment/runtime' / JOB / f'qwen25-{index}_command.json')['argv']
        require(command.count('--max-num-seqs') == 1 and command[command.index('--max-num-seqs') + 1] == '12'
                and command[command.index('--tensor-parallel-size') + 1] == '2', 'Service is not TP2 with twelve execution slots')
    receipt = read(ROOT / 'deployment/pipeline_launch_receipt.json')
    require(receipt.get('source') == 'planned_scale48', 'Replacement pipeline receipt has unexpected provenance')
    for name, expected in receipt['verified_files'].items():
        require(sha(local_path(name)) == expected, 'Replacement pipeline source changed: ' + name)
    manifest = read(ROOT / 'deployment/services_staging_manifest.json')['files']
    for name, expected in manifest.items():
        if name not in ('summary.json', 'RESULTS_ZH.md'):
            require(sha(local_path(name)) == expected, 'Frozen staged source changed: ' + name)
    protocol = read(ROOT / 'protocol.json')
    require(digest(protocol) == read(ROOT / 'execution/task_queue.json')['protocol_sha256'],
            'Frozen protocol and task queue differ')
    return scope, {'controller_step': controller['step_id'], 'pipeline_step': pipeline['step_id'],
                   'controller_status_source': str(controller_path.relative_to(ROOT)),
                   'service_step': service['step_id'], 'worker_step': worker['step_id'],
                   'active_workers': 48, 'service_max_num_seqs': 12, 'replicas': 4,
                   'worker_process_check': process_check,
                   'worker_status_updated_unix': worker['updated_unix'], 'protocol_sha256': digest(protocol)}


def audit():
    receipt = {'schema': 'qwen_scale48_post_restart_audit_v1', 'status': 'running',
               'started_unix': time.time(), 'root': str(ROOT), 'scientific_model_calls': 0,
               'signals_sent': 0, 'scientific_files_modified': False, 'errors': [], 'retry_reasons': [], 'arms': []}
    scope, configuration = audit_configuration()
    receipt['configuration'] = configuration
    drained = read(HERE / 'drained_receipt.json')
    frozen = read(HERE / 'replay_preflight_frozen.json')
    require(drained.get('schema') == 'qwen48_request_checkpoint_v1' and drained.get('status') == 'drained'
            and drained.get('claim_locks_release') == 'confirmed', 'No successful released request checkpoint')
    require(sha(HERE / 'replay_preflight_frozen.json') == drained['replay_proof']['sha256']
            and frozen.get('status') == 'passed' and frozen.get('provider_calls') == 0
            and frozen.get('all_active_arms_verified') is True, 'Frozen zero-provider-call replay proof changed')
    for name, expected in drained['source_sha256'].items():
        require(sha(local_path(name)) == expected, 'Original scientific protocol/source changed: ' + name)
    before = {(row['case_uid'], row['method']): row for row in frozen['active_arm_identities']}
    require(len(before) == len(frozen['active_arm_identities']) == len(drained['audit']['partial_arms']),
            'Frozen replay identity count changed')
    for name, expected in frozen['source_cache_sha256'].items():
        require(sha(local_path(name)) == expected, 'Pre-restart response cache was overwritten: ' + name)
    for old in drained['audit']['results']:
        uid, method = old['task'].rsplit('__', 1)
        folder = ROOT / 'results/qwen25' / uid / method
        require(sha(folder / 'final.json') == old['final_sha256']
                and sha(folder / 'ledger.jsonl') == old['ledger_sha256'], 'Already-complete arm was rerun or modified')
    failure_paths = list((ROOT / 'results').glob('*/*/*/failure.json'))
    require(not failure_paths, 'Scientific failure marker exists: ' + ','.join(str(p.relative_to(ROOT)) for p in failure_paths))
    references = read(ROOT / 'historical_sa_reference.json')['rows']
    refs = {(row['case_uid'], row['model_key']): row for row in references}
    require(len(refs) == len(references) == 80, 'Historical SA reference does not contain exactly eighty unique cases')
    totals = {key: 0 for key in ('calls', 'completed_with_usage', 'pending_calls', 'total_tokens', 'held_tokens', 'accounted_tokens')}
    seen_prefixes, final_count, old_settled_calls = set(), 0, 0
    ledgers = sorted((ROOT / 'results').glob('*/*/*/ledger.jsonl'))
    for ledger in ledgers:
        folder = ledger.parent
        model_key, uid, method = folder.parents[1].name, folder.parent.name, folder.name
        name = str(folder.relative_to(ROOT))
        try:
            require(model_key == 'qwen25' and uid in scope['case_uids'] and method in METHODS, 'Out-of-scope scientific arm')
            raw, final = stable_arm_snapshot(folder)
            reference = refs[(uid, model_key)]
            cap = reference['usage']['total_tokens']
            calls, summary = parse_ledger(raw, (uid, MODEL, method), cap)
            old = before.get((uid, method))
            if old is not None:
                count = old['source_ledger_bytes']
                require(len(raw) >= count and sha_bytes(raw[:count]) == old['source_ledger_sha256'],
                        'Pre-restart ledger byte prefix was rewritten or lost')
                previous, prior_summary = parse_ledger(raw[:count], (uid, MODEL, method), cap)
                require(prior_summary['pending_calls'] == 0 and prior_summary['completed_with_usage'] == old['prefix_calls'],
                        'Frozen ledger prefix is not fully settled')
                for cid, old_call in previous.items():
                    require(cid in calls and calls[cid] == old_call, 'A pre-restart provider call was charged or settled again')
                old_settled_calls += len(previous)
                seen_prefixes.add((uid, method))
            for row in calls.values():
                if row['status'] == 'completed_with_usage':
                    check_cache(folder, row)
            if final is not None:
                require(final.get('model_key') == model_key and final.get('model') == MODEL
                        and final.get('case_uid') == uid and final.get('method') == method
                        and final.get('protocol_sha256') == configuration['protocol_sha256']
                        and final.get('token_budget') == cap
                        and final.get('historical_sa_source_sha256') == reference['source_sha256']
                        and final.get('completion_status') in ('complete', 'strict_experiment_failure'),
                        'Final scientific identity/protocol/state is invalid')
                require(summary['held_calls'] == 0
                        and all(final.get('usage', {}).get(key) == value for key, value in summary.items()),
                        'Final accounting differs from unique settled ledger calls')
                final_count += 1
            for key in totals:
                totals[key] += summary[key]
            receipt['arms'].append({'case_uid': uid, 'method': method, 'final': final is not None,
                                    'resumed_prefix': old is not None, 'token_cap': cap, **summary})
        except SnapshotRetry as exc:
            receipt['retry_reasons'].append(str(exc))
        except (AuditError, KeyError, ValueError, TypeError, OSError) as exc:
            receipt['errors'].append({'arm': name, 'error_type': type(exc).__name__, 'error': str(exc)})
    missing = set(before) - seen_prefixes
    if missing and not receipt['retry_reasons']:
        receipt['errors'].append({'error': 'Pre-restart partial arms missing from audit', 'arms': sorted(missing)})
    receipt.update(ended_unix=time.time(), observed_arms=len(ledgers), audited_arms=len(receipt['arms']),
                   final_arms=final_count, frozen_partial_arms=len(before), verified_resumed_prefixes=len(seen_prefixes),
                   old_settled_calls_preserved_once=old_settled_calls,
                   historical_sa_reused=True,
                   duplicate_reservations=0 if not receipt['errors'] and not receipt['retry_reasons'] else None,
                   duplicate_settlements=0 if not receipt['errors'] and not receipt['retry_reasons'] else None, usage=totals,
                   active_pending_calls_are_expected=True, atomic_global_snapshot=False)
    receipt['status'] = 'failed' if receipt['errors'] else 'retry_required' if receipt['retry_reasons'] else 'passed'
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional audit JSON receipt in this scale48 directory')
    args = parser.parse_args()
    require(ROOT == EXPECTED and ROOT.resolve() == ROOT and os.getuid() == 1083,
            'Requires the exact experiment shared directory and authorized account')
    try:
        receipt = audit()
    except (AuditError, KeyError, ValueError, TypeError, OSError) as exc:
        receipt = {'schema': 'qwen_scale48_post_restart_audit_v1', 'status': 'failed',
                   'ended_unix': time.time(), 'scientific_model_calls': 0, 'scientific_files_modified': False,
                   'errors': [{'error_type': type(exc).__name__, 'error': str(exc)}]}
    if args.output:
        path = args.output if args.output.is_absolute() else HERE / args.output
        require(path.resolve() == path and path.parent == HERE and path.name.startswith('post_restart_audit')
                and path.suffix == '.json', 'Output must be a named audit JSON inside this recovery directory')
        temporary = path.with_name('.' + path.name + '.' + str(os.getpid()) + '.tmp')
        with temporary.open('x') as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    print(json.dumps({key: value for key, value in receipt.items() if key != 'arms'}, ensure_ascii=False))
    return 0 if receipt['status'] == 'passed' else 2 if receipt['status'] == 'retry_required' else 1


if __name__ == '__main__':
    raise SystemExit(main())

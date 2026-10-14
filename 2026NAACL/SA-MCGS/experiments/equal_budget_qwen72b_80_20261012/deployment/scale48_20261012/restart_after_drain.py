#!/usr/bin/env python3
"""One authorized 32 -> 48 execution-concurrency restart after a verified drain.

No scientific source, protocol, result, ledger, case or budget is changed.  This
helper stays alive with its pipeline child so nested srun controllers retain the
independent CPU step's lifetime.  A durable intent prevents ambiguous retries.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, redirect_stdout
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
DEPLOY = HERE.parent
ROOT = DEPLOY.parent
AUTHORIZED_ROOT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')
PYTHON = '/aifs4su/hansirui/vllm-dsv4-venv/bin/python3'
JOB, NODE, UID = '415747', 'dgx-061', 1083
DERIVED = ('summary.json', 'RESULTS_ZH.md')
CHANGED = ('deployment/service_supervisor.py', 'execution_config.json')
OLD_SEQUENCE = b"'--max-num-seqs', '8'"
NEW_SEQUENCE = b"'--max-num-seqs', '12'"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_bytes(path, data):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '.' + str(os.getpid()) + '.tmp')
    with temporary.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def local_path(name):
    relative = Path(name)
    require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe relative path: ' + name)
    path = ROOT / relative
    require(path.resolve() == path, 'Redirected path: ' + name)
    return path


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def environment_identity():
    require(ROOT == AUTHORIZED_ROOT and ROOT.resolve() == ROOT, 'Wrong experiment root')
    require(os.getuid() == UID and socket.gethostname().split('.')[0] == NODE, 'Wrong owner/node')
    require(os.environ.get('SLURM_JOB_ID') == JOB, 'Wrong existing allocation')
    step = os.environ.get('SLURM_STEP_ID', '')
    require(step.isdigit() and step not in ('41', '42', '43'), 'An independent numbered CPU step is required')
    require(os.environ.get('CUDA_VISIBLE_DEVICES', '') in ('', '-1', 'NoDevFiles')
            and os.environ.get('SLURM_STEP_GPUS', '') in ('', '-1', 'NoDevFiles'), 'CPU-only step required')


def process_absent_or_zombie(pid):
    require(type(pid) is int and pid > 1, 'Missing prior process identity')
    try:
        tail = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].strip().split()
        return tail[0] == 'Z'
    except FileNotFoundError:
        return True


def verify_old_stopped(drained):
    states = {
        'pipeline': read(DEPLOY / 'pipeline_status.json'),
        'service': read(DEPLOY / 'service_state.json'),
        'workers': read(ROOT / 'execution/status.json'),
    }
    pipeline, service, workers = (states[key] for key in ('pipeline', 'service', 'workers'))
    require(pipeline.get('status') == 'needs_attention' and pipeline.get('own_services_stopped') is True
            and pipeline.get('worker_terminal_status') == 'needs_attention', 'Old pipeline did not finish the planned partial drain')
    require(service.get('status') == 'stopped', 'Old services are not stopped')
    checkpoint = drained.get('schema') == 'qwen48_request_checkpoint_v1'
    allowed_exits = (0, -15) if checkpoint else (0,)
    require(workers.get('status') == 'needs_attention' and workers.get('running_workers') == 0
            and len(workers.get('workers', [])) == 32
            and all(worker.get('exit_code') in allowed_exits for worker in workers['workers']),
            'Prior workers did not exit in the reviewed drain mode')
    if checkpoint:
        signals = {item['pid']: item for item in drained.get('signals', [])}
        for worker in workers['workers']:
            if worker['exit_code'] == -15:
                sent = signals.get(worker['pid'], {})
                require(sent.get('worker') == worker['name'] and sent.get('identity')
                        and sent.get('sigterm_intent_at') and sent.get('sigterm_sent_at')
                        and sent.get('sigcont_sent_at'), 'Worker -15 exit lacks planned checkpoint signal proof')
    require(0 <= workers.get('final_results', -1) < 160 and workers.get('expected_results') == 160
            and workers.get('sa_execution_enabled') is False and workers.get('external_api_enabled') is False,
            'Unexpected scientific completion or scope')
    require(not workers.get('error') and not workers.get('error_type'), 'Prior worker supervisor has an infrastructure error')
    for key, step in (('pipeline', '41'), ('service', '42'), ('workers', '43')):
        state = states[key]
        require(str(state.get('job_id')) == JOB and str(state.get('step_id')) == step,
                'Previous ' + key + ' allocation/step changed')
        require(process_absent_or_zombie(state.get('pid')), 'Previous ' + key + ' process is still alive')
    for worker in workers['workers']:
        require(process_absent_or_zombie(worker.get('pid')), 'Prior scientific worker is still alive')
    require(not (ROOT / 'endpoints.json').exists(), 'Old endpoint publication still exists')
    for port in range(19271, 19275):
        with socket.socket() as sock:
            sock.settimeout(.5)
            require(sock.connect_ex(('127.0.0.1', port)) != 0, 'Old service port remains open: ' + str(port))
    # Reject live processes from this experiment even if absent from a stale status.
    arguments = {str(ROOT / 'runner.py').encode(), str(ROOT / 'worker_supervisor.py').encode(),
                 str(DEPLOY / 'pipeline_supervisor.py').encode(), str(DEPLOY / 'service_supervisor.py').encode()}
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid == UID and not process_absent_or_zombie(int(process.name)):
                require(not arguments.intersection((process / 'cmdline').read_bytes().split(b'\0')),
                        'Unrecorded live process from this experiment: ' + process.name)
        except FileNotFoundError:
            continue
    return states


def verify_scientific_files(drained):
    preparation = read(ROOT / 'preflight/runner_prepare.json')
    require(preparation.get('status') == 'passed' and preparation.get('expected_results') == 160
            and preparation.get('sa_model_calls') == 0 and preparation.get('model_calls') == 0,
            'Frozen offline preflight changed')
    protocol = preparation['protocol']
    hashes = {**protocol['source_hashes'], 'run_scope.json': protocol['run_scope_sha256'],
              'historical_sa_reference.json': protocol['historical_sa_reference_sha256']}
    for name, expected in hashes.items():
        require(sha(local_path(name)) == expected, 'Scientific source/reference changed: ' + name)
    require(read(ROOT / 'execution/step_launch_receipt.json')['verified_source_hashes'] == hashes,
            'Old worker source proof differs from frozen preflight')
    preserved = {}
    for path in sorted((ROOT / 'results').rglob('*')):
        if path.is_file():
            require(not path.is_symlink(), 'Result symlink is not permitted')
            preserved[str(path.relative_to(ROOT))] = sha(path)
    for name in ('protocol.json', 'execution/task_queue.json', 'historical_sa_raw_reference.json'):
        preserved[name] = sha(local_path(name))
    for path in sorted((ROOT / 'tokenizer_hashes').glob('*.json')):
        preserved[str(path.relative_to(ROOT))] = sha(path)
    require(not list((ROOT / 'results').glob('*/*/*/failure.json')), 'A scientific failure marker exists')
    # Frozen runner validates terminal results and their actual budget accounting.
    sys.path.insert(0, str(ROOT))
    import runner
    plan = read(ROOT / 'science/repo/portable_data/qwen80_case_plan.json')
    scope = runner.load_scope(plan)
    refs = runner.historical_reference(plan)
    phash = runner.digest(read(ROOT / 'protocol.json'))
    finals = runner.validate_existing_results(scope, refs, phash)
    require(len(finals) == read(ROOT / 'execution/status.json')['final_results'], 'Partial final count mismatch')
    final_folders = {path.parent for path in (ROOT / 'results').glob('*/*/*/final.json')}
    partial_ledgers = set()
    if drained.get('schema') == 'qwen48_request_checkpoint_v1':
        audit = drained['audit']
        actual_results = {name: value for name, value in preserved.items() if name.startswith('results/')}
        require(actual_results == audit['all_result_files_sha256'], 'Result tree changed since checkpoint')
        for arm in audit['partial_arms']:
            require(arm.get('method') in ('lea', 'full-scc') and arm.get('case_uid') in scope['case_uids']
                    and arm.get('held_calls') == 0 and arm.get('usage_mismatch_calls') == 0
                    and type(arm.get('settled_calls')) is int and arm['settled_calls'] >= 0,
                    'Partial arm is not a settled authorized baseline')
            folder = ROOT / 'results/qwen25' / arm['case_uid'] / arm['method']
            ledger = folder / 'ledger.jsonl'
            require(ledger not in partial_ledgers and folder not in final_folders,
                    'Duplicate or already-terminal checkpoint arm')
            require(sha(ledger) == arm['ledger_sha256'], 'Partial ledger changed since checkpoint')
            cache_hashes = arm.get('cache_sha256', {})
            require(arm['settled_calls'] == len(cache_hashes), 'Checkpoint cache count differs from settled requests')
            for name, expected in cache_hashes.items():
                cached = local_path(name)
                require(cached.is_relative_to(folder) and sha(cached) == expected,
                        'Partial response cache changed or escaped its arm')
            partial_ledgers.add(ledger)
    for ledger in (ROOT / 'results').glob('*/*/*/ledger.jsonl'):
        require(ledger.parent in final_folders or ledger in partial_ledgers,
                'Nonterminal ledger has no audited deterministic replay proof: ' + str(ledger))
    return {'frozen_source_hashes': hashes, 'preserved_files': preserved, 'terminal_results': len(finals),
            'settled_partial_arms': len(partial_ledgers)}


def verify_derived_reports():
    # The original report code is independently manifest-verified by the caller.
    # Recreate its two outputs in isolation, without touching the published report.
    class RedirectWrites:
        def __init__(self, temporary):
            self.temporary = temporary

        def __truediv__(self, name):
            return (self.temporary if str(name) in DERIVED else ROOT) / name

    with tempfile.TemporaryDirectory(prefix='derived_check_', dir=HERE) as temporary:
        report = module('scale48_report_validation', ROOT / 'report_results.py')
        report.ROOT = RedirectWrites(Path(temporary))
        with redirect_stdout(io.StringIO()):
            report.main()
        result = {}
        for name in DERIVED:
            expected = (Path(temporary) / name).read_bytes()
            require(local_path(name).read_bytes() == expected,
                    'Published partial report is not reproduced by the frozen reporter: ' + name)
            result[name] = digest(expected)
        return result


def verify_manifests():
    launch = read(DEPLOY / 'pipeline_launch_receipt.json')
    require(launch.get('job_id') == JOB and launch.get('node') == NODE
            and launch.get('auto_retry') is False and launch.get('gpu_requested') is False,
            'Previous pipeline receipt identity changed')
    for name, expected in launch['verified_files'].items():
        require(sha(local_path(name)) == expected, 'Old pipeline source proof mismatch: ' + name)
    manifest = read(DEPLOY / 'services_staging_manifest.json')
    config_receipt = read(DEPLOY / 'concurrency_20261012/scale_24_to_32.json')
    require(config_receipt.get('status') == 'applied'
            and config_receipt.get('before') == {'workers_per_replica': {'qwen25': 6}}
            and config_receipt.get('after') == {'workers_per_replica': {'qwen25': 8}}
            and config_receipt.get('service_restart') is False
            and config_receipt.get('scientific_source_or_budget_changes') is False
            and str(config_receipt.get('worker_step_id')) == '43'
            and str(config_receipt.get('service_step_id')) == '42', 'Missing authorized 24 -> 32 change proof')
    config_name = 'execution_config.json'
    require(manifest['files'][config_name] == config_receipt['before_sha256']
            and sha(local_path(config_name)) == config_receipt['after_sha256']
            and read(local_path(config_name)) == config_receipt['after'], 'Live configuration differs from its change proof')
    for name, expected in manifest['files'].items():
        if name not in (*DERIVED, config_name):
            require(sha(local_path(name)) == expected, 'Immutable staged file changed: ' + name)
    reports = verify_derived_reports()
    return manifest, reports


def archive_plan():
    moves = set()
    exact = ('pipeline_launch_receipt.json', 'pipeline_status.json', 'pipeline_step.log',
             'services_launch_receipt.json', 'service_state.json', 'services_step.log',
             'services_stop_receipt.json', 'endpoints_retired.json', 'model_provenance.json', 'gpu_preflight.json')
    moves.update('deployment/' + name for name in exact if (DEPLOY / name).exists())
    moves.update(str(path.relative_to(ROOT)) for path in DEPLOY.glob('pipeline_*.log'))
    for pattern in ('qwen25-*.log', 'qwen25-*_command.json', 'qwen25-*_smoke.json'):
        moves.update(str(path.relative_to(ROOT)) for path in (DEPLOY / 'runtime' / JOB).glob(pattern))
    for name in ('step_launch_receipt.json', 'status.json', 'step.log'):
        if (ROOT / 'execution' / name).exists():
            moves.add('execution/' + name)
    for pattern in ('qwen25-*_worker*.log', 'qwen25-*_worker*_status.json'):
        moves.update(str(path.relative_to(ROOT)) for path in (ROOT / 'execution').glob(pattern))
    start = module('scale48_pipeline_start', DEPLOY / 'start_pipeline_once.py')
    copies = set(start.FILES) | set(CHANGED) | set(DERIVED) | {
        'report_results.py', 'protocol.json', 'execution/task_queue.json',
        'deployment/previous_service_retirement.json',
        'deployment/concurrency_20261012/scale_24_to_32.json',
        'preflight/context_validation_deployed.json',
    }
    copies.difference_update(moves)
    return sorted(moves), sorted(copies)


def verify_replay_proof(drained, proof_path):
    proof = read(proof_path)
    require(proof.get('schema') == 'qwen_scale48_cache_replay_v1' and proof.get('status') == 'passed'
            and proof.get('all_active_arms_verified') is True and proof.get('provider_calls') == 0
            and not proof.get('errors') and proof.get('root') == str(ROOT),
            'Frozen cache replay did not pass for this exact run without provider calls')
    require(proof.get('script_sha256') == sha(HERE / 'replay_preflight.py'), 'Frozen replay implementation changed')
    require({'runner.py', 'science_support.py', 'methods_full.py', 'budget_client.py', 'protocol.json',
             'historical_sa_reference.json', 'run_scope.json', 'endpoints.json'} <= set(proof.get('source_hashes', {})),
            'Frozen replay source coverage is incomplete')
    for name, expected in proof.get('source_hashes', {}).items():
        path = DEPLOY / 'endpoints_retired.json' if name == 'endpoints.json' else local_path(name)
        require(sha(path) == expected, 'Replay source or retired endpoints changed: ' + name)
    require(proof.get('tokenizer_hashes') == read(ROOT / 'tokenizer_hashes/qwen25.json'),
            'Frozen replay tokenizer proof changed')
    partial = {(arm['case_uid'], arm['method']): arm for arm in drained['audit']['partial_arms']}
    verified = {(arm['case_uid'], arm['method']): arm for arm in proof['active_arm_identities']}
    require(len(partial) == len(drained['audit']['partial_arms'])
            and len(verified) == len(proof['active_arm_identities'])
            and set(partial) == set(verified) and proof.get('arm_count') == len(partial),
            'Frozen replay does not cover exactly the partial scientific arms')
    all_caches = {}
    for key, arm in partial.items():
        verified_arm = verified[key]
        require(verified_arm.get('status') == 'passed' and verified_arm.get('ignored_partial_bytes') == 0
                and verified_arm.get('omitted_reservations') == []
                and verified_arm.get('omitted_reservations_count') == 0
                and verified_arm.get('source_ledger_sha256') == arm['ledger_sha256']
                and verified_arm.get('source_complete_sha256') == arm['ledger_sha256']
                and verified_arm.get('source_ledger_bytes') == verified_arm.get('source_complete_bytes')
                and verified_arm.get('prefix_calls') == arm['settled_calls']
                and verified_arm.get('source_cache_sha256') == arm['cache_sha256'],
                'Partial arm differs from its complete frozen replay proof: ' + '/'.join(key))
        evidence_path = Path(verified_arm.get('evidence_path', ''))
        require(evidence_path.is_absolute() and evidence_path.resolve() == evidence_path
                and evidence_path.is_relative_to(HERE) and sha(evidence_path) == verified_arm['evidence_sha256'],
                'Frozen replay evidence changed or escaped this recovery directory')
        evidence = read(evidence_path)
        require(evidence.get('status') == 'passed' and evidence.get('parse_idempotent') is True
                and evidence.get('first_replay') == evidence.get('second_replay')
                and evidence.get('first_replay', {}).get('provider_calls') == 0,
                'Two deterministic zero-provider-call cached replays are not confirmed')
        all_caches.update(arm['cache_sha256'])
    require(all_caches == proof.get('source_cache_sha256'), 'Replay global response cache proof mismatch')


def verify_drain_receipt(drained):
    require(drained.get('status') == 'drained', 'A successful explicit drain receipt is required')
    checkpoint = drained.get('schema') == 'qwen48_request_checkpoint_v1'
    require(checkpoint or drained.get('kind', 'arm_boundary') == 'arm_boundary',
            'Unknown or unreviewed draining mode')
    if checkpoint:
        require(drained.get('planned_signal_termination') is True,
                'Request checkpoint does not authorize planned worker termination')
        replay = drained.get('replay_proof', {})
        require(replay.get('status') == 'passed' and replay.get('provider_calls') == 0,
                'Request checkpoint lacks a successful zero-provider-call replay proof')
        proof_path = local_path(replay.get('path', ''))
        require(proof_path == HERE / 'replay_preflight_frozen.json'
                and sha(proof_path) == replay.get('sha256'), 'Frozen replay proof changed or uses an unexpected path')
        verify_replay_proof(drained, proof_path)
    context = drained.get('context', {})
    require(str(context.get('job_id')) == JOB and context.get('hostname', '').split('.')[0] == NODE
            and context.get('uid') == UID and context.get('gpu_requested') is False,
            'Drain receipt allocation mismatch')
    require(drained.get('all_original_processes_exited') is True
            and drained.get('old_service_ports_closed') is True
            and drained.get('endpoints_absent') is True
            and drained.get('claim_locks_release') == 'confirmed', 'Drain cleanup is not explicitly confirmed')
    audit = drained.get('audit', {})
    require(audit.get('held_calls') == 0 and audit.get('usage_mismatch_calls') == 0
            and audit.get('infrastructure_failures') == 0 and 0 <= audit.get('final_results', -1) < 160,
            'Drain did not settle all started scientific arms')
    if checkpoint:
        require(isinstance(audit.get('partial_arms'), list) and len(audit['partial_arms']) <= 32
                and isinstance(audit.get('all_result_files_sha256'), dict), 'Partial checkpoint audit is missing')
    hashes = drained.get('source_sha256', {})
    require({'runner.py', 'methods_full.py', 'budget_client.py', 'protocol.json',
             'run_scope.json', 'historical_sa_reference.json'} <= set(hashes),
            'Drain scientific source proof is incomplete')
    for name, expected in hashes.items():
        require(sha(local_path(name)) == expected, 'File changed since drain: ' + name)
    state_hashes = drained.get('state_files_sha256', {})
    require(set(state_hashes) == {'deployment/pipeline_status.json', 'deployment/service_state.json',
                                  'execution/status.json'}, 'Drain terminal-state fingerprints are incomplete')
    for name, expected in state_hashes.items():
        require(sha(local_path(name)) == expected, 'Terminal state changed since drain: ' + name)
    return audit


def prepare():
    drain_path = HERE / 'drained_receipt.json'
    drained = read(drain_path)
    audit = verify_drain_receipt(drained)
    states = verify_old_stopped(drained)
    require(states['workers']['final_results'] == audit['final_results'], 'Final count changed since drain')
    scientific = verify_scientific_files(drained)
    manifest, report_hashes = verify_manifests()
    old_source = local_path(CHANGED[0]).read_bytes()
    require(old_source.count(OLD_SEQUENCE) == 1 and NEW_SEQUENCE not in old_source,
            'Expected exactly one unchanged service max-num-seqs=8 option')
    new_source = old_source.replace(OLD_SEQUENCE, NEW_SEQUENCE)
    compile(new_source, str(local_path(CHANGED[0])), 'exec')
    config = {'workers_per_replica': {'qwen25': 12}}
    new_config = (json.dumps(config, indent=2) + '\n').encode()
    moves, copies = archive_plan()
    archive = HERE / 'archive_before_48'
    require(not archive.exists(), 'Archive already exists; do not repeat an uncertain restart')
    files = {name: {'sha256': sha(local_path(name)), 'mode': 'move' if name in moves else 'copy'}
             for name in sorted(set(moves) | set(copies))}
    intent = {'status': 'preparing', 'created_unix': time.time(), 'job_id': JOB, 'node': NODE,
              'independent_step_id': os.environ['SLURM_STEP_ID'], 'pid': os.getpid(),
              'authorization': 'User explicitly requested a 48-active-request test.',
              'drain_receipt_sha256': sha(drain_path), 'old_states': states,
              'archive': str(archive), 'archive_files': files, 'scientific': scientific,
              'new_workers_per_replica': 12, 'new_service_max_num_seqs': 12,
              'scientific_retries': 0, 'sa_execution_enabled': False}
    save(HERE / 'restart_receipt.json', intent)
    archive.mkdir(mode=0o700)
    # Copy first, then move only finished orchestration artifacts.  Claims,
    # results, ledger files and frozen scientific state remain at original paths.
    for name in copies:
        target = archive / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path(name), target)
        require(sha(target) == files[name]['sha256'], 'Archive copy mismatch: ' + name)
    for name in moves:
        target = archive / name
        target.parent.mkdir(parents=True, exist_ok=True)
        local_path(name).replace(target)
        require(sha(target) == files[name]['sha256'], 'Archive move mismatch: ' + name)
    save(archive / 'archive_manifest.json', files)
    atomic_bytes(local_path(CHANGED[0]), new_source)
    atomic_bytes(local_path(CHANGED[1]), new_config)
    new_hashes = {CHANGED[0]: digest(new_source), CHANGED[1]: digest(new_config), **report_hashes}
    original_manifest = json.loads(json.dumps(manifest))
    manifest['files'].update(new_hashes)
    require(set(manifest['files']) == set(original_manifest['files']), 'Staging manifest file coverage changed')
    changed_hashes = {name: {'before': original_manifest['files'][name], 'after': value}
                      for name, value in manifest['files'].items()
                      if value != original_manifest['files'][name]}
    require(set(changed_hashes) <= set(CHANGED + DERIVED), 'Unexpected manifest hash change')
    save(DEPLOY / 'services_staging_manifest.json', manifest)
    for name, expected in scientific['preserved_files'].items():
        require(sha(local_path(name)) == expected, 'Preserved scientific artifact changed: ' + name)
    for name, expected in manifest['files'].items():
        require(sha(local_path(name)) == expected, 'Prepared staging proof mismatch: ' + name)
    starter = module('scale48_pipeline_start_final', DEPLOY / 'start_pipeline_once.py')
    proofs = {name: sha(local_path(name)) for name in starter.FILES}
    command = [PYTHON, '-B', str(DEPLOY / 'pipeline_supervisor.py')]
    require(not (DEPLOY / 'pipeline_launch_receipt.json').exists(), 'Pipeline launch receipt was not archived')
    require((archive / 'deployment/pipeline_launch_receipt.json').exists(), 'Prior launch receipt is not recoverable')
    receipt = {'status': 'planned_scale48_starting', 'job_id': JOB, 'node': NODE,
               'command': command, 'created_unix': time.time(), 'gpu_requested': False,
               'auto_retry': False, 'expected_results': 160, 'sa_execution_enabled': False,
               'restore_wait_timeout_sec': 7200, 'service_wait_timeout_sec': 7200,
               'worker_wait_timeout_sec': 1200, 'pipeline_lifetime': 'full_experiment_in_independent_cpu_step',
               'verified_files': proofs, 'source': 'planned_scale48',
               'parent_pid': os.getpid(), 'independent_step_id': os.environ['SLURM_STEP_ID'],
               'drain_receipt_sha256': sha(drain_path), 'restart_receipt': str(HERE / 'restart_receipt.json')}
    save(DEPLOY / 'pipeline_launch_receipt.json', receipt)
    intent.update(status='prepared', prepared_unix=time.time(), changed_manifest_hashes=changed_hashes,
                  pipeline_launch_receipt_sha256=sha(DEPLOY / 'pipeline_launch_receipt.json'),
                  scientific_files_unchanged=True)
    save(HERE / 'restart_receipt.json', intent)
    return intent, command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true', help='Prepare once without launching; production should omit this flag.')
    args = parser.parse_args()
    environment_identity()
    os.umask(0o077)
    with (HERE / 'restart.lock').open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not (HERE / 'restart_receipt.json').exists(), 'Restart intent already exists; no duplicate or automatic retry')
        with ExitStack() as locks:
            for name in ('deployment/start_pipeline.lock', 'deployment/pipeline_supervisor.lock',
                         'deployment/start_services.lock', 'deployment/service_supervisor.lock',
                         'execution/launch.lock', 'execution/supervisor.lock'):
                lock = locks.enter_context(local_path(name).open('a'))
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            intent, command = prepare()
        if args.prepare_only:
            print(json.dumps({'status': 'prepared_without_launch', 'receipt': str(HERE / 'restart_receipt.json')}), flush=True)
            return 0
        intent.update(status='pipeline_launch_intent', launched_unix=time.time(), command=command)
        save(HERE / 'restart_receipt.json', intent)
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env.update(PYTHONHASHSEED='42', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
                   PYTHON_DOTENV_DISABLED='1', SLURM_EXPORT_ENV='ALL',
                   SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf')
        with (DEPLOY / 'pipeline_step.log').open('ab', buffering=0) as log:
            result = subprocess.run(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, check=False)
        intent.update(status='pipeline_exited', ended_unix=time.time(), pipeline_exit_code=result.returncode)
        save(HERE / 'restart_receipt.json', intent)
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())

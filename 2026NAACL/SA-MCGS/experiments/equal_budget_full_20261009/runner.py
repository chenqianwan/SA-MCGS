#!/usr/bin/env python3
"""Fresh per-case SA budget followed by two independently sampled baselines."""
from __future__ import annotations
import argparse
import asyncio
import copy
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import sys
import time
import traceback
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
METHODS = ('sa-mcgs', 'lea', 'full-scc')
FIELDS = {'sa-mcgs': 'evidence_risk_subgraph_nodes', 'lea': 'lea_risk_subgraph_nodes',
          'full-scc': 'direct_risk_subgraph_nodes'}
MODEL_KEYS = ('llama', 'kimi', 'qwen35')


class WorkerStop(BaseException):
    pass


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), default=str).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def freeze(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + '.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if path.exists():
            if read(path) != value:
                raise WorkerStop(f'Frozen protocol changed: {path.name}')
        else:
            save(path, value)


def load_science():
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    try:
        import dotenv
        dotenv.load_dotenv = lambda *args, **kwargs: False
    except ImportError:
        pass
    spec = importlib.util.spec_from_file_location('equal_budget_science', ROOT/'science/base_launcher.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    manifest = launcher.verify_bundle()
    cost = launcher.import_science()
    graphs = launcher.restore_graphs(cost, manifest)
    plan = read(launcher.ROOT/'portable_data/qwen80_case_plan.json')
    if len(plan) != 80 or len({c['case_uid'] for c in plan}) != 80:
        raise WorkerStop('Expected exactly 80 frozen case identities')
    for case in plan:
        case['source_result_file'] = str(launcher.ROOT/case['source_result_repo_relpath'])
    # New local Qwen3.5 has the same 12000 one-shot allowance as the other models.
    original = cost.battle._model_json_max_tokens
    cost.battle._model_json_max_tokens = lambda model, requested: (
        requested if model == 'qwen3.5-9b' else original(model, requested))
    return launcher, cost, manifest, graphs, plan


def science_args(model='offline'):
    return argparse.Namespace(model=model, budget=60, window_size=4, internal_concurrency=1,
                              compression_profile='current', seed=42, case_concurrency=1,
                              llm_timeout=1800, llm_max_retries=0)


def load_scope(plan):
    path = ROOT/'run_scope.json'
    if not path.is_file():
        raise WorkerStop('run_scope.json is required; refusing unscoped execution')
    scope = read(path)
    selected = scope.get('case_uids') if isinstance(scope, dict) else None
    if (not isinstance(selected, list) or len(selected) != 10
            or not all(isinstance(uid, str) for uid in selected)
            or len(set(selected)) != 10):
        raise WorkerStop('run_scope.json must fix exactly 10 unique case_uids')
    if (scope.get('version') != 1 or scope.get('cases_per_model') != 10
            or scope.get('expected_results') != 90 or scope.get('stop_after_scope') is not True
            or not isinstance(scope.get('selection_rule'), str) or not scope['selection_rule'].strip()):
        raise WorkerStop('Run scope must explicitly authorize version1, 10 cases/model, 90 results and stop_after_scope')
    known = {case['case_uid'] for case in plan}
    if not set(selected) <= known:
        raise WorkerStop('Run scope contains a case outside the verified 80-source plan')
    return scope


def science_protocol(launcher, cost, manifest, scope):
    return {
        'version': 1, 'experiment': 'equal_budget_full_20261009', 'seed': 42,
        'source_cases': 80, 'cases_per_model': len(scope['case_uids']),
        'run_scope': scope, 'run_scope_sha256': sha(ROOT/'run_scope.json'),
        'expected_results': len(scope['case_uids'])*len(MODEL_KEYS)*len(METHODS),
        'models': list(MODEL_KEYS), 'methods': list(METHODS),
        'source_hashes': {name: sha(ROOT/name) for name in
                          ('runner.py', 'methods_full.py', 'budget_client.py',
                           'science/base_launcher.py', 'science/repo/bundle_manifest.json')},
        'science_source_hashes': manifest['unchanged_code_sha256'],
        'case_plan_sha256': sha(launcher.ROOT/'portable_data/qwen80_case_plan.json'),
        'sa_config': cost.make_mcgs_config(science_args()),
        'local_temperature': .4, 'baseline_temperature': .4, 'judge_temperature': 0,
        'local_max_output': 2048, 'full_max_output': 12000, 'judge_max_output': 256,
        'json_attempts': 3, 'selector_json_attempts': 1, 'parse_exhaustion': {}, 'sdk_retries': 0,
        'native_h_fields': FIELDS, 'gt_use': 'injection identity and offline metrics only',
        'budget_rule': 'Fresh SA60 measured input+output tokens; each baseline including candidates, retries and judge <= B; actual usage reported',
        'sa_scientific_failure_budget': 'Freeze known consumed SA usage; preserve failed score; no quality-based rerun',
        'unknown_usage': 'Keep reservation and stop worker; no resampling',
        'baseline_selector': 'Independent original candidates, compact anonymous same-model judge; no ground-truth selection',
        'qwen35_hosted_8192_cap_override': True,
        'protocol_changes_from_historical': ['SA internal concurrency 8 -> 1', 'Full repeated sampling temperature 0 -> 0.4'],
        'external_api_enabled': False,
    }


def metrics(result, method, case, eligible=True):
    ids = case['planned_scc_clause_ids']; allowed = set(ids)
    labels = case['planned_injection_identity']
    result = result or {}; rows = result.get('ranking') or []
    h = set(result.get(FIELDS[method]) or [])
    try:
        ranking = [r[0] for r in rows]
        valid = bool(eligible and h and h <= allowed and len(rows) == len(ids)
                     and set(ranking) == allowed
                     and all(len(r) >= 2 and math.isfinite(float(r[1])) for r in rows))
    except (ValueError, TypeError, IndexError, KeyError):
        valid = False; ranking = []
    risks = set(labels['risk_nodes']); evidence = set(labels['evidence_nodes'])
    rank = ranking.index(labels['root_node'])+1 if valid else None
    return {'valid': valid, 'root_at_1': int(rank == 1),
            'root_at_3': int(rank is not None and rank <= 3), 'root_rank': rank,
            'mrr': 1/rank if rank else 0,
            'risk_any': int(valid and bool(h & risks)), 'risk_all': int(valid and risks <= h),
            'endpoint_recall': len(h & risks)/len(risks) if valid else 0,
            'evidence_all': int(valid and evidence <= h),
            'evidence_recall': len(h & evidence)/len(evidence) if valid else 0,
            'output_n': len(h) if valid else None,
            'compression': 1-len(h)/len(ids) if valid else None}


def select_worker_cases(plan, endpoints, replica_id, worker_index, workers):
    replica = next((r for r in endpoints['replicas'] if r['id'] == replica_id), None)
    if replica is None:
        raise WorkerStop('Replica absent from endpoint configuration')
    model_key = replica['model_key']
    replicas = sorted([r for r in endpoints['replicas'] if r['model_key'] == model_key], key=lambda r: r['id'])
    ordinal = next(i for i, r in enumerate(replicas) if r['id'] == replica_id)
    shard, shards = ordinal*workers+worker_index, len(replicas)*workers
    assigned = [case for index, case in enumerate(plan)
                if index % len(replicas) == ordinal
                and (index // len(replicas)) % workers == worker_index]
    return replica, model_key, assigned, shard, shards


def tokenizer_hashes(path):
    path = Path(path)
    names = {'tokenizer.json', 'tokenizer_config.json', 'config.json', 'special_tokens_map.json',
             'chat_template.jinja', 'tokenizer.model', 'vocab.json', 'merges.txt', 'tiktoken.model'}
    names.update(item.name for item in path.glob('*.py'))
    return {name: sha(path/name) for name in sorted(names) if (path/name).is_file()}


async def run_case(case, replica, model_key, model_cfg, tokenizer, token_hashes,
                   args, cost, graphs, protocol_hash, methods, budget):
    case_root = ROOT/'results'/model_key/case['case_uid']
    case_root.mkdir(parents=True, exist_ok=True)
    ledger = budget.GlobalLedger(case_root/'ledger.jsonl')
    await ledger.initialize()
    try:
        graph, scc, _root, _labels = cost.prepare_injected_case(case, graphs)
        visible = {'nodes': [{'id': c, 'title': graph.clauses[c].title, 'text': graph.clauses[c].content}
                             for c in scc.clause_ids],
                   'edges': [{'source': e.source, 'target': e.target,
                              'type': str(getattr(e.dependency_type, 'value', e.dependency_type)),
                              'weight': float(e.weight)} for e in graph.edges
                             if e.source in set(scc.clause_ids) and e.target in set(scc.clause_ids)]}
        input_hash = digest(visible)
        freeze(case_root/'input_identity.json', {'case_uid': case['case_uid'], 'case_id': case['case_id'],
               'protocol_sha256': protocol_hash, 'visible_input_sha256': input_hash,
               'planned_fingerprint': case['planned_scc_fingerprint']})
        B = None
        for method in METHODS:
            folder = case_root/method; folder.mkdir(exist_ok=True)
            path = folder/'final.json'
            if path.exists():
                record = read(path)
                if any(record.get(k) != v for k, v in {'protocol_sha256': protocol_hash,
                       'case_uid': case['case_uid'], 'model_key': model_key, 'method': method}.items()):
                    raise WorkerStop('Existing final identity/protocol mismatch')
                if record['completion_status'] not in ('complete', 'strict_experiment_failure'):
                    raise WorkerStop('Preserving prior infrastructure failure; worker requires review')
                current = ledger.owner_summary(case['case_uid'], model_cfg['alias'], method)
                for key in ('calls', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'held_tokens'):
                    if current[key] != record['usage'][key]:
                        raise WorkerStop('Existing final and durable ledger disagree')
            else:
                state_path = folder/'attempt.json'
                state = read(state_path) if state_path.exists() else {'started_at': now(), 'started_unix': time.time()}
                save(state_path, state)
                client = budget.BudgetClient(config={'timeout': 1800, 'max_model_len': 131072,
                    'tokenizer_fingerprint': digest(token_hashes)}, ledger=ledger,
                    case_id=case['case_uid'], method=method, tokenizer=tokenizer,
                    model=model_cfg['alias'], base_url=replica['base_url'], call_log_dir=folder/'calls',
                    token_cap=None if method == 'sa-mcgs' else B,
                    json_attempts=3, selector_json_attempts=1,
                    chat_template_kwargs=model_cfg.get('chat_template_kwargs', {}))
                record = {'model_key': model_key, 'model': model_cfg['alias'],
                          'case_uid': case['case_uid'], 'case_id': case['case_id'], 'domain': case['domain'],
                          'method': method, 'protocol_sha256': protocol_hash, 'replica_id': replica['id'],
                          'visible_input_sha256': input_hash, 'source_n': scc.size,
                          'started_at': state['started_at'], 'token_budget': B,
                          'selected_result': None, 'completion_status': 'started'}
                start = time.monotonic(); fatal = False
                try:
                    random.seed(42)
                    inference = (await methods.run_sa(client, args, case, graph, scc, folder)
                                 if method == 'sa-mcgs' else
                                 await methods.baseline(client, args, case, graph, scc, method, folder))
                    record['inference'] = inference
                    record['selected_result'] = inference.get('selected_result')
                    record['metrics'] = metrics(record['selected_result'], method, case)
                    record['completion_status'] = ('complete' if record['metrics']['valid']
                                                   else 'strict_experiment_failure')
                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                    record.update(completion_status='strict_experiment_failure', error_type=type(exc).__name__,
                                  error=str(exc)[:3000], traceback=traceback.format_exc()[-12000:])
                except BaseException as exc:
                    if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                        raise
                    fatal = True
                    record.update(completion_status='infrastructure_failure', error_type=type(exc).__name__,
                                  error=str(exc)[:3000], traceback=traceback.format_exc()[-12000:])
                finally:
                    record['usage'] = ledger.owner_summary(case['case_uid'], model_cfg['alias'], method)
                    record['ended_at'] = now(); record['elapsed_sec'] = time.time()-state['started_unix']
                    record['attempt_elapsed_sec'] = time.monotonic()-start
                    await client.close()
                if record['usage']['held_calls'] or record['usage']['usage_mismatch_calls']:
                    fatal = True
                    record.update(completion_status='infrastructure_failure', error_type='UnsettledOrMismatchedUsage')
                if record['completion_status'] != 'complete':
                    record['selected_result'] = None
                    record['metrics'] = metrics(None, method, case, False)
                if B is not None and record['usage']['accounted_tokens'] > B:
                    fatal = True
                    record.update(completion_status='infrastructure_failure', error_type='BudgetExceeded',
                                  selected_result=None, metrics=metrics(None, method, case, False))
                save(path, record)
                print(json.dumps({'case_uid': case['case_uid'], 'model_key': model_key, 'method': method,
                                  'status': record['completion_status'], 'tokens': record['usage']['total_tokens'],
                                  'B': B}, ensure_ascii=False), flush=True)
                if fatal:
                    raise WorkerStop(f"Stop worker after {method}: {record.get('error_type')}")
            if method == 'sa-mcgs':
                B = await ledger.freeze_budget(case['case_uid'], model_cfg['alias'], sa_method='sa-mcgs')
                freeze(case_root/'budget.json', {'case_uid': case['case_uid'], 'model_key': model_key,
                       'model': model_cfg['alias'], 'token_budget': B, 'protocol_sha256': protocol_hash,
                       'sa_completion_status': record['completion_status']})
        save(case_root/'complete.json', {'case_uid': case['case_uid'], 'model_key': model_key,
                                        'methods': list(METHODS), 'token_budget': B, 'completed_at': now()})
    except BaseException as exc:
        save(case_root/'failure.json', {'case_uid': case['case_uid'], 'model_key': model_key,
             'error_type': type(exc).__name__, 'error': str(exc)[:3000], 'recorded_at': now(),
             'protocol_sha256': protocol_hash, 'ledger_summary': await ledger.summary()})
        raise
    finally:
        await ledger.close()


async def execute(cli, loaded):
    launcher, cost, manifest, graphs, plan = loaded
    scope = load_scope(plan)
    scope_uids = set(scope['case_uids'])
    scoped_plan = [case for case in plan if case['case_uid'] in scope_uids]
    endpoints = read(ROOT/'endpoints.json')
    replica, key, assigned, shard, shards = select_worker_cases(
        scoped_plan, endpoints, cli.replica_id, cli.worker_index, cli.workers_per_replica)
    if key not in MODEL_KEYS or set(endpoints['models']) != set(MODEL_KEYS):
        raise WorkerStop('Unexpected endpoint model keys')
    cfg = endpoints['models'][key]
    if cfg['alias'] != replica['alias'] or cfg['max_model_len'] != 131072:
        raise WorkerStop('Replica model/context configuration mismatch')
    if cfg.get('chat_template_kwargs', {}) != ({'enable_thinking': False} if key == 'qwen35' else {}):
        raise WorkerStop('Unexpected thinking configuration')
    if os.environ.get('PYTHONHASHSEED') != '42':
        raise WorkerStop('Set PYTHONHASHSEED=42 before starting workers')
    if not assigned:
        save(ROOT/'execution'/f'{cli.replica_id}_worker{cli.worker_index}_status.json',
             {'replica_id': cli.replica_id, 'model_key': key, 'worker_index': cli.worker_index,
              'workers_per_replica': cli.workers_per_replica, 'shard': shard, 'shards': shards,
              'assigned_case_uids': [], 'completed_cases': 0, 'status': 'complete', 'ended_at': now()})
        return
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(cfg['tokenizer_path'], local_files_only=True,
                                             trust_remote_code=cfg.get('trust_remote_code', False))
    hashes = tokenizer_hashes(cfg['tokenizer_path'])
    protocol = science_protocol(launcher, cost, manifest, scope)
    protocol['models_configuration'] = endpoints['models']
    protocol['replicas'] = [{name: r[name] for name in ('id', 'model_key', 'alias', 'base_url')}
                            for r in endpoints['replicas']]
    freeze(ROOT/'protocol.json', protocol)
    freeze(ROOT/'tokenizer_hashes'/f'{key}.json', hashes)
    protocol_hash = digest(protocol)
    cost.validate_case_plan(assigned, graphs)
    import budget_client as budget
    import methods_full as methods
    status_path = ROOT/'execution'/f'{cli.replica_id}_worker{cli.worker_index}_status.json'
    status = {'replica_id': cli.replica_id, 'model_key': key, 'worker_index': cli.worker_index,
              'workers_per_replica': cli.workers_per_replica,
              'shard': shard, 'shards': shards, 'assigned_case_uids': [c['case_uid'] for c in assigned],
              'completed_cases': 0, 'started_at': now(), 'status': 'running'}
    save(status_path, status)
    try:
        for case in assigned:
            status.update(current_case_uid=case['case_uid'], updated_at=now()); save(status_path, status)
            await run_case(case, replica, key, cfg, tokenizer, hashes, science_args(cfg['alias']),
                           cost, graphs, protocol_hash, methods, budget)
            status['completed_cases'] += 1; save(status_path, status)
    except BaseException as exc:
        status.update(status='needs_attention', error_type=type(exc).__name__, error=str(exc)[:3000], ended_at=now())
        save(status_path, status)
        raise
    status.update(status='complete', ended_at=now()); save(status_path, status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true', help='Offline 80-source and required 10-case scope validation; no model calls')
    parser.add_argument('--replica-id')
    parser.add_argument('--worker-index', type=int, default=0)
    parser.add_argument('--workers-per-replica', type=int, default=8)
    cli = parser.parse_args()
    if not 1 <= cli.workers_per_replica <= 16 or not 0 <= cli.worker_index < cli.workers_per_replica:
        parser.error('Invalid worker index/count')
    loaded = load_science()
    scope = load_scope(loaded[4])
    if cli.prepare:
        launcher, cost, manifest, graphs, plan = loaded
        validation = cost.validate_case_plan(plan, graphs)
        report = {'status': 'passed', 'cases': len(plan), 'scoped_cases': len(scope['case_uids']),
                  'expected_results': 90, 'model_calls': 0,
                  'science_protocol': science_protocol(launcher, cost, manifest, scope), 'validation': validation}
        save(ROOT/'preflight/runner_prepare.json', report)
        print(json.dumps({'status': 'passed', 'source_cases': len(plan), 'scoped_cases': len(scope['case_uids']),
                          'expected_results': 90, 'model_calls': 0}), flush=True)
        return 0
    if not cli.replica_id:
        parser.error('--replica-id is required unless --prepare is used')
    asyncio.run(execute(cli, loaded))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except WorkerStop as error:
        print(json.dumps({'status': 'needs_attention', 'error': str(error)}, ensure_ascii=False), flush=True)
        raise SystemExit(2)

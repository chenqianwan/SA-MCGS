#!/usr/bin/env python3
"""Run independent baseline arms against frozen historical SA token budgets."""
from __future__ import annotations
import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
import random
import time
import traceback

from science_support import (ROOT, MODEL_KEYS, FIELDS, WorkerStop, read, sha,
    digest, now, save, freeze, load_science, science_args, metrics, tokenizer_hashes)

METHODS = ('lea', 'full-scc')


MODEL_ALIAS = 'qwen2.5-72b-instruct'
MODEL_CHECKPOINT = 'Qwen/Qwen2.5-72B-Instruct-AWQ'
EXPECTED_RESULTS = 160
TERMINAL_STATES = ('complete', 'strict_experiment_failure')


def load_scope(plan):
    scope = read(ROOT/'run_scope.json')
    if (scope.get('scope_schema') != 'historical_sa_baselines_v1'
            or scope.get('models') != list(MODEL_KEYS)
            or scope.get('cases_per_model') != 80 or scope.get('expected_results') != EXPECTED_RESULTS
            or scope.get('comparison_expected_results') != 240
            or scope.get('execution_methods') != list(METHODS)
            or scope.get('sa_execution_enabled') is not False
            or scope.get('stop_after_scope') is not True
            or len(plan) != 80 or len({c['case_uid'] for c in plan}) != 80
            or scope.get('case_uids') != [c['case_uid'] for c in plan]):
        raise WorkerStop('Expected qwen25, all 80 original cases, two baselines, 160 new arms, and no SA execution')
    return scope


def budget_provenance(document, row):
    provenance = row.get('budget_provenance', document.get('budget_provenance'))
    if not isinstance(provenance, dict) or provenance.get('kind') not in ('actual', 'calibrated'):
        raise WorkerStop('Historical budget must explicitly identify actual or calibrated provenance')
    return provenance


def historical_reference(plan):
    document = read(ROOT/'historical_sa_reference.json')
    rows = document['rows']
    refs = {(r['model_key'], r['case_uid']): r for r in rows}
    expected = {(m, c['case_uid']) for m in MODEL_KEYS for c in plan}
    if len(rows) != 80 or set(refs) != expected:
        raise WorkerStop('Historical Qwen SA must cover exactly 80 unique model/case pairs')
    for model in MODEL_KEYS:
        for case in plan:
            row = refs[(model, case['case_uid'])]
            tokens = row['usage']['total_tokens']
            if (row['method'] != 'sa-mcgs'
                    or row.get('model') not in ('qwen2.5-72b', MODEL_ALIAS)
                    or row.get('target_execution_alias', MODEL_ALIAS) != MODEL_ALIAS
                    or row['domain'] != case['domain']
                    or row['source_n'] != len(case['planned_scc_clause_ids'])
                    or not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0
                    or row['completion_status'] not in TERMINAL_STATES
                    or not isinstance(row['source_sha256'], str)
                    or len(row['source_sha256']) != 64
                    or any(c not in '0123456789abcdef' for c in row['source_sha256'])):
                raise WorkerStop('Historical SA identity/usage is unsuitable for Qwen reuse')
            budget_provenance(document, row)
    return refs


def validate_endpoints(endpoints):
    if set(endpoints.get('models', {})) != set(MODEL_KEYS):
        raise WorkerStop('Only qwen25 endpoints are authorized')
    cfg = endpoints['models']['qwen25']
    if (cfg.get('alias') != MODEL_ALIAS or cfg.get('checkpoint') != MODEL_CHECKPOINT
            or cfg.get('max_model_len') not in (16384, 32768, 131072)
            or cfg.get('chat_template_kwargs', {}) != {}):
        raise WorkerStop('Unexpected Qwen checkpoint, alias, context or thinking configuration')
    replicas = endpoints.get('replicas', [])
    if not replicas or len({r['id'] for r in replicas}) != len(replicas):
        raise WorkerStop('Expected unique Qwen replica IDs')
    for replica in replicas:
        if replica.get('model_key') != 'qwen25' or replica.get('alias') != MODEL_ALIAS:
            raise WorkerStop('Replica model does not match the authorized Qwen model')
    return replicas


def validate_final(path, model, case_uid, method, ref=None, phash=None):
    row = read(path)
    expected = {'model_key': model, 'model': MODEL_ALIAS, 'case_uid': case_uid, 'method': method}
    if phash is not None:
        expected['protocol_sha256'] = phash
    if any(row.get(k) != v for k, v in expected.items()):
        raise WorkerStop('Existing final identity/protocol mismatch')
    if row.get('completion_status') not in TERMINAL_STATES:
        raise WorkerStop('Preserving existing infrastructure failure; review required before resuming')
    usage = row.get('usage', {})
    cap = row.get('token_budget')
    if (type(cap) is not int or cap < 0 or type(usage.get('total_tokens')) is not int
            or usage['total_tokens'] < 0 or usage['total_tokens'] > cap
            or type(usage.get('accounted_tokens')) is not int
            or usage['accounted_tokens'] < usage['total_tokens'] or usage['accounted_tokens'] > cap
            or usage.get('held_calls') != 0 or usage.get('usage_mismatch_calls') != 0):
        raise WorkerStop('Existing final has unresolved or over-budget token accounting')
    if ref is not None and (cap != ref['usage']['total_tokens']
            or row.get('historical_sa_source_sha256') != ref['source_sha256']):
        raise WorkerStop('Existing final has changed historical SA budget or source')
    return row


def validate_existing_results(scope, refs, phash=None):
    allowed = set(scope['case_uids'])
    rows = []
    for path in sorted((ROOT/'results').glob('*/*/*/final.json')):
        model, uid, method = path.parents[2].name, path.parents[1].name, path.parent.name
        if model not in MODEL_KEYS or uid not in allowed or method not in METHODS:
            raise WorkerStop('Out-of-scope result: refusing extra model, case or fresh SA')
        rows.append(validate_final(path, model, uid, method, refs[(model, uid)], phash))
    return rows


def protocol(launcher, manifest, scope, models=None):
    reference_document = read(ROOT/'historical_sa_reference.json')
    result = {
        'version': 1, 'experiment': 'equal_budget_qwen72b_80_20261012', 'seed': 42,
        'run_scope': scope, 'run_scope_sha256': sha(ROOT/'run_scope.json'),
        'historical_sa_reference_sha256': sha(ROOT/'historical_sa_reference.json'),
        'models': list(MODEL_KEYS), 'execution_methods': list(METHODS), 'expected_results': EXPECTED_RESULTS,
        'sa_execution_enabled': False,
        'source_hashes': {name: sha(ROOT/name) for name in
            ('runner.py', 'science_support.py', 'methods_full.py', 'budget_client.py',
             'science/base_launcher.py', 'science/repo/bundle_manifest.json')},
        'science_source_hashes': manifest['unchanged_code_sha256'],
        'case_plan_sha256': sha(launcher.ROOT/'portable_data/qwen80_case_plan.json'),
        'budget_rule': 'Each baseline has its own cap B from historical_sa_reference usage.total_tokens for this exact Qwen/case. The provenance below states whether B is measured actual usage or a calibrated estimate. All candidate, retry and selector usage counts.',
        'historical_budget_provenance': reference_document.get('budget_provenance'),
        'historical_budget_row_provenance': {r['case_uid']: budget_provenance(reference_document, r) for r in reference_document['rows']},
        'historical_sa_failures': 'Retain strict failure scores and the frozen reference budget with its explicit provenance.',
        'local_temperature': .4, 'baseline_temperature': .4, 'judge_temperature': 0,
        'local_max_output': 2048, 'full_max_output': 12000, 'judge_max_output': 256,
        'json_attempts': 3, 'selector_json_attempts': 1, 'parse_exhaustion': {}, 'sdk_retries': 0,
        'native_h_fields': {m: FIELDS[m] for m in METHODS},
        'gt_use': 'Injection identity verification and offline metrics only; never candidate selection.',
        'baseline_selector': 'Unchanged independent original candidates and compact anonymous same-model judge.',
        'scheduling': 'Independent arm processes; dynamic largest-budget-first queue. Each arm keeps isolated RNG, call log and durable ledger.',
        'unknown_usage': 'Preserve reservation and stop that worker; no automatic resampling.',
        'qwen25_hosted_8192_cap_override': True,
        'qwen25_full_output_allowance': 'Local Qwen uses the same 12000 full-SCC output allowance as the comparison models; the historical hosted-Qwen 8192 clamp is bypassed explicitly.', 'external_api_enabled': False,
        'baseline_reuse': 'None: all 80 baseline cases execute under the frozen Qwen historical-SA budget protocol.'}
    if models is not None:
        # GPU placement and number of workers are execution details, not scientific settings.
        result['models_configuration'] = {key: {k: v for k, v in cfg.items() if k != 'base_urls'}
                                           for key, cfg in models.items()}
    return result


def ordered_tasks(plan, refs, model):
    if model not in MODEL_KEYS:
        raise WorkerStop('Task model outside authorized Qwen scope')
    return sorted([(c, m) for c in plan for m in METHODS],
                  key=lambda t: (-refs[(model, t[0]['case_uid'])]['usage']['total_tokens'],
                                 t[0]['main_case_order'], METHODS.index(t[1])))


def claim_next(tasks, model, refs=None, phash=None):
    if model not in MODEL_KEYS or any(method not in METHODS for _, method in tasks):
        raise WorkerStop('Only Qwen LEA/Full-SCC arms may be claimed')
    claim_root = ROOT/'execution/claims'/model
    claim_root.mkdir(parents=True, exist_ok=True)
    for case, method in tasks:
        final = ROOT/'results'/model/case['case_uid']/method/'final.json'
        if final.exists():
            validate_final(final, model, case['case_uid'], method,
                           refs[(model, case['case_uid'])] if refs is not None else None, phash)
            continue
        lock = (claim_root/f"{case['case_uid']}__{method}.lock").open('a+')
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            continue
        if final.exists():
            try:
                validate_final(final, model, case['case_uid'], method,
                               refs[(model, case['case_uid'])] if refs is not None else None, phash)
            finally:
                lock.close()
            continue
        return case, method, lock
    return None


async def run_arm(case, method, replica, cfg, tokenizer, hashes, cost, graphs, phash, ref):
    if method not in METHODS or replica.get('model_key') != 'qwen25':
        raise WorkerStop('Fresh SA and other models are forbidden')
    import budget_client as budget
    import methods_full as methods
    model = replica['model_key']
    B = ref['usage']['total_tokens']
    folder = ROOT/'results'/model/case['case_uid']/method
    folder.mkdir(parents=True, exist_ok=True)
    ledger = budget.GlobalLedger(folder/'ledger.jsonl')
    await ledger.initialize()
    client = None
    try:
        cost.validate_case_plan([case], graphs)
        graph, scc, _, _ = cost.prepare_injected_case(case, graphs)
        ids = set(scc.clause_ids)
        visible = {'nodes': [{'id': c, 'title': graph.clauses[c].title, 'text': graph.clauses[c].content}
                             for c in scc.clause_ids],
                   'edges': [{'source': e.source, 'target': e.target,
                              'type': str(getattr(e.dependency_type, 'value', e.dependency_type)),
                              'weight': float(e.weight)} for e in graph.edges if e.source in ids and e.target in ids]}
        input_hash = digest(visible)
        freeze(folder/'input_identity.json', {'case_uid': case['case_uid'], 'method': method,
            'protocol_sha256': phash, 'visible_input_sha256': input_hash,
            'planned_fingerprint': case['planned_scc_fingerprint'], 'token_budget': B,
            'historical_sa_source_sha256': ref['source_sha256']})
        state_path = folder/'attempt.json'
        state = read(state_path) if state_path.exists() else {'started_at': now(), 'started_unix': time.time()}
        save(state_path, state)
        client = budget.BudgetClient(config={'timeout': 1800, 'max_model_len': cfg['max_model_len'],
            'tokenizer_fingerprint': digest(hashes)}, ledger=ledger,
            case_id=case['case_uid'], method=method, tokenizer=tokenizer, model=cfg['alias'],
            base_url=replica['base_url'], call_log_dir=folder/'calls', token_cap=B,
            json_attempts=3, selector_json_attempts=1,
            chat_template_kwargs=cfg.get('chat_template_kwargs', {}))
        record = {'model_key': model, 'model': cfg['alias'], 'case_uid': case['case_uid'],
            'case_id': case['case_id'], 'main_case_order': case['main_case_order'], 'domain': case['domain'],
            'method': method, 'protocol_sha256': phash, 'replica_id': replica['id'],
            'visible_input_sha256': input_hash, 'source_n': scc.size,
            'historical_sa_source_sha256': ref['source_sha256'], 'historical_sa_completion_status': ref['completion_status'],
            'started_at': state['started_at'], 'token_budget': B,
            'selected_result': None, 'completion_status': 'started'}
        start = time.monotonic()
        fatal = False
        try:
            random.seed(42)
            inference = await methods.baseline(client, science_args(cfg['alias']), case, graph, scc, method, folder)
            record['inference'] = inference
            record['selected_result'] = inference.get('selected_result')
            record['metrics'] = metrics(record['selected_result'], method, case)
            record['completion_status'] = 'complete' if record['metrics']['valid'] else 'strict_experiment_failure'
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
            record['usage'] = ledger.owner_summary(case['case_uid'], cfg['alias'], method)
            record['ended_at'] = now()
            record['elapsed_sec'] = time.time()-state['started_unix']
            record['attempt_elapsed_sec'] = time.monotonic()-start
            await client.close()
            client = None
        if record['usage']['held_calls'] or record['usage']['usage_mismatch_calls']:
            fatal = True
            record.update(completion_status='infrastructure_failure', error_type='UnsettledOrMismatchedUsage')
        if record['usage']['accounted_tokens'] > B:
            fatal = True
            record.update(completion_status='infrastructure_failure', error_type='BudgetExceeded')
        if record['completion_status'] != 'complete':
            record.update(selected_result=None, metrics=metrics(None, method, case, False))
        save(folder/'final.json', record)
        print(json.dumps({'model': model, 'case_uid': case['case_uid'], 'method': method,
                          'status': record['completion_status'], 'tokens': record['usage']['total_tokens'], 'B': B}), flush=True)
        if fatal:
            raise WorkerStop(f"Infrastructure failure: {record.get('error_type')}")
    except BaseException as exc:
        save(folder/'failure.json', {'case_uid': case['case_uid'], 'method': method, 'model': model,
             'error_type': type(exc).__name__, 'error': str(exc)[:3000], 'recorded_at': now(),
             'protocol_sha256': phash, 'ledger_summary': await ledger.summary()})
        raise
    finally:
        if client is not None:
            await client.close()
        await ledger.close()


async def execute(cli, loaded, scope, refs):
    launcher, cost, manifest, graphs, plan = loaded
    endpoints = read(ROOT/'endpoints.json')
    replicas = validate_endpoints(endpoints)
    replica = next((r for r in replicas if r['id'] == cli.replica_id), None)
    if replica is None:
        raise WorkerStop('Replica absent from endpoint configuration')
    model = replica['model_key']
    cfg = endpoints['models'][model]
    if os.environ.get('PYTHONHASHSEED') != '42':
        raise WorkerStop('Set PYTHONHASHSEED=42 before execution')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(cfg['tokenizer_path'], local_files_only=True,
                                             trust_remote_code=cfg.get('trust_remote_code', False))
    hashes = tokenizer_hashes(cfg['tokenizer_path'])
    if not {'tokenizer_config.json', 'tokenizer.json'} <= set(hashes):
        raise WorkerStop('Qwen tokenizer files missing; cannot verify token accounting')
    frozen = protocol(launcher, manifest, scope, endpoints['models'])
    freeze(ROOT/'protocol.json', frozen)
    freeze(ROOT/'tokenizer_hashes'/f'{model}.json', hashes)
    phash = digest(frozen)
    validate_existing_results(scope, refs, phash)
    tasks = ordered_tasks(plan, refs, model)
    freeze(ROOT/'execution/task_queue.json', {'model_key': model, 'protocol_sha256': phash,
        'sa_execution_enabled': False, 'expected_results': EXPECTED_RESULTS,
        'tasks': [{'case_uid': c['case_uid'], 'method': m,
                   'token_budget': refs[(model, c['case_uid'])]['usage']['total_tokens']}
                  for c, m in tasks]})
    status_path = ROOT/'execution'/f'{cli.replica_id}_worker{cli.worker_index}_status.json'
    state = {'replica_id': cli.replica_id, 'model_key': model, 'worker_index': cli.worker_index,
             'completed_arms': 0, 'started_at': now(), 'status': 'running'}
    save(status_path, state)
    try:
        while True:
            claimed = claim_next(tasks, model, refs, phash)
            if claimed is None:
                break
            case, method, lock = claimed
            try:
                state.update(current_case_uid=case['case_uid'], current_method=method, updated_at=now())
                save(status_path, state)
                await run_arm(case, method, replica, cfg, tokenizer, hashes, cost, graphs, phash,
                              refs[(model, case['case_uid'])])
                state['completed_arms'] += 1
                save(status_path, state)
            finally:
                lock.close()
    except BaseException as exc:
        state.update(status='needs_attention', error_type=type(exc).__name__, error=str(exc)[:3000], ended_at=now())
        save(status_path, state)
        raise
    state.update(status='complete', ended_at=now())
    save(status_path, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--replica-id')
    parser.add_argument('--worker-index', type=int, default=0)
    cli = parser.parse_args()
    if not 0 <= cli.worker_index < 32:
        parser.error('Worker index must be in 0..31')
    loaded = load_science()
    scope = load_scope(loaded[4])
    refs = historical_reference(loaded[4])
    validate_existing_results(scope, refs)
    if cli.prepare:
        launcher, cost, manifest, graphs, plan = loaded
        validation = cost.validate_case_plan(plan, graphs)
        result = {'status': 'passed', 'source_cases': len(plan), 'historical_sa_rows': len(refs),
                  'expected_results': EXPECTED_RESULTS, 'sa_model_calls': 0, 'model_calls': 0,
                  'protocol': protocol(launcher, manifest, scope), 'validation': validation}
        save(ROOT/'preflight/runner_prepare.json', result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('protocol', 'validation')}), flush=True)
        return 0
    if not cli.replica_id:
        parser.error('--replica-id is required unless --prepare')
    asyncio.run(execute(cli, loaded, scope, refs))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except WorkerStop as exc:
        print(json.dumps({'status': 'needs_attention', 'error': str(exc)}), flush=True)
        raise SystemExit(2)

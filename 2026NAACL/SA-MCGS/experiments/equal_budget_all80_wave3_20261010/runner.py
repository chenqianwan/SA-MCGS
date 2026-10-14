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


def load_scope(plan):
    scope = read(ROOT/'run_scope.json')
    if (scope.get('scope_schema') != 'historical_sa_baselines_v1'
            or scope.get('cases_per_model') != 80 or scope.get('expected_results') != 480
            or scope.get('comparison_expected_results') != 720
            or scope.get('execution_methods') != list(METHODS)
            or scope.get('stop_after_scope') is not True
            or scope.get('case_uids') != [c['case_uid'] for c in plan]):
        raise WorkerStop('Expected all 80 original cases, exactly two baseline methods, and 480 new arms')
    return scope


def historical_reference(plan):
    rows = read(ROOT/'historical_sa_reference.json')['rows']
    refs = {(r['model_key'], r['case_uid']): r for r in rows}
    expected = {(m, c['case_uid']) for m in MODEL_KEYS for c in plan}
    if len(rows) != 240 or set(refs) != expected:
        raise WorkerStop('Historical SA must cover exactly all 240 model/case pairs')
    for model in MODEL_KEYS:
        for case in plan:
            row = refs[(model, case['case_uid'])]
            tokens = row['usage']['total_tokens']
            if (row['method'] != 'sa-mcgs' or row['domain'] != case['domain']
                    or row['source_n'] != len(case['planned_scc_clause_ids'])
                    or not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0
                    or row['completion_status'] not in ('complete', 'strict_experiment_failure')
                    or len(row['source_sha256']) != 64):
                raise WorkerStop('Historical SA identity/usage is unsuitable for reuse')
    return refs


def protocol(launcher, manifest, scope, models=None):
    result = {
        'version': 1, 'experiment': 'equal_budget_all80_20261009', 'seed': 42,
        'run_scope': scope, 'run_scope_sha256': sha(ROOT/'run_scope.json'),
        'historical_sa_reference_sha256': sha(ROOT/'historical_sa_reference.json'),
        'models': list(MODEL_KEYS), 'execution_methods': list(METHODS), 'expected_results': 480,
        'sa_execution_enabled': False,
        'source_hashes': {name: sha(ROOT/name) for name in
            ('runner.py', 'science_support.py', 'methods_full.py', 'budget_client.py',
             'science/base_launcher.py', 'science/repo/bundle_manifest.json')},
        'science_source_hashes': manifest['unchanged_code_sha256'],
        'case_plan_sha256': sha(launcher.ROOT/'portable_data/qwen80_case_plan.json'),
        'budget_rule': 'Each baseline has its own cap B, equal to historical SA actual input+output tokens for this exact model/case; all candidate, retry and selector usage counts.',
        'historical_sa_failures': 'Retain strict failure score and its actual consumed token budget.',
        'local_temperature': .4, 'baseline_temperature': .4, 'judge_temperature': 0,
        'local_max_output': 2048, 'full_max_output': 12000, 'judge_max_output': 256,
        'json_attempts': 3, 'selector_json_attempts': 1, 'parse_exhaustion': {}, 'sdk_retries': 0,
        'native_h_fields': {m: FIELDS[m] for m in METHODS},
        'gt_use': 'Injection identity verification and offline metrics only; never candidate selection.',
        'baseline_selector': 'Unchanged independent original candidates and compact anonymous same-model judge.',
        'scheduling': 'Independent arm processes; dynamic largest-budget-first queue. Each arm keeps isolated RNG, call log and durable ledger.',
        'unknown_usage': 'Preserve reservation and stop that worker; no automatic resampling.',
        'qwen35_hosted_8192_cap_override': True, 'external_api_enabled': False,
        'pilot_reuse': 'None: all 80 baseline cases use the same historical-SA budget protocol; prior 10-case pilot retained separately.'}
    if models is not None:
        # GPU placement and number of workers are execution details, not scientific settings.
        result['models_configuration'] = {key: {k: v for k, v in cfg.items() if k != 'base_urls'}
                                           for key, cfg in models.items()}
    return result


def ordered_tasks(plan, refs, model):
    return sorted([(c, m) for c in plan for m in METHODS],
                  key=lambda t: (-refs[(model, t[0]['case_uid'])]['usage']['total_tokens'],
                                 t[0]['main_case_order'], METHODS.index(t[1])))


def claim_next(tasks, model):
    claim_root = ROOT/'execution/claims'/model
    claim_root.mkdir(parents=True, exist_ok=True)
    for case, method in tasks:
        final = ROOT/'results'/model/case['case_uid']/method/'final.json'
        if final.exists():
            continue
        lock = (claim_root/f"{case['case_uid']}__{method}.lock").open('a+')
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            continue
        if final.exists():
            lock.close()
            continue
        return case, method, lock
    return None


async def run_arm(case, method, replica, cfg, tokenizer, hashes, cost, graphs, phash, ref):
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
        client = budget.BudgetClient(config={'timeout': 1800, 'max_model_len': 131072,
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
    replica = next(r for r in endpoints['replicas'] if r['id'] == cli.replica_id)
    model = replica['model_key']
    cfg = endpoints['models'][model]
    if set(endpoints['models']) != set(MODEL_KEYS) or cfg['alias'] != replica['alias'] or cfg['max_model_len'] != 131072:
        raise WorkerStop('Unexpected model endpoint configuration')
    if cfg.get('chat_template_kwargs', {}) != ({'enable_thinking': False} if model == 'qwen35' else {}):
        raise WorkerStop('Unexpected thinking configuration')
    if os.environ.get('PYTHONHASHSEED') != '42':
        raise WorkerStop('Set PYTHONHASHSEED=42 before execution')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(cfg['tokenizer_path'], local_files_only=True,
                                             trust_remote_code=cfg.get('trust_remote_code', False))
    hashes = tokenizer_hashes(cfg['tokenizer_path'])
    frozen = protocol(launcher, manifest, scope, endpoints['models'])
    freeze(ROOT/'protocol.json', frozen)
    freeze(ROOT/'tokenizer_hashes'/f'{model}.json', hashes)
    phash = digest(frozen)
    tasks = ordered_tasks(plan, refs, model)
    status_path = ROOT/'execution'/f'{cli.replica_id}_worker{cli.worker_index}_status.json'
    state = {'replica_id': cli.replica_id, 'model_key': model, 'worker_index': cli.worker_index,
             'completed_arms': 0, 'started_at': now(), 'status': 'running'}
    save(status_path, state)
    try:
        while True:
            claimed = claim_next(tasks, model)
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
    if cli.prepare:
        launcher, cost, manifest, graphs, plan = loaded
        validation = cost.validate_case_plan(plan, graphs)
        result = {'status': 'passed', 'source_cases': len(plan), 'historical_sa_rows': len(refs),
                  'expected_results': 480, 'sa_model_calls': 0, 'model_calls': 0,
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

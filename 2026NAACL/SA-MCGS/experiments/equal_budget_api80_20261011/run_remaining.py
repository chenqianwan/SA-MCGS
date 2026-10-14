#!/usr/bin/env python3
"""Run only the frozen 70-case complement; scientific functions stay unchanged."""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
PILOT = ROOT.parent / 'equal_budget_api10_20261011'
SCIENCE = ROOT.parent / 'equal_budget_all80_20261009'
MODELS = ('gpt-4o', 'gemini-2.5-pro')
METHODS = ('lea', 'full-scc')
CONCURRENCY = 8
EXPECTED = 280
ENDPOINT = 'https://api3.xhub.chat/v1'
TERMINAL = {'complete', 'scientific_failure', 'infrastructure_failure', 'budget_violation'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def safe_error(error):
    text = str(error)
    for name in ('XHUB_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY'):
        secret = os.environ.get(name, '').strip()
        if secret:
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)bearer\s+\S+', 'Bearer [REDACTED]', text)
    text = re.sub(r'sk-[A-Za-z0-9_-]+', '[REDACTED]', text)
    return text[:800]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def source_path(name):
    path = Path(name)
    choices = [path] if path.is_absolute() else [ROOT/path, REPO/path]
    found = {p.resolve() for p in choices if p.is_file()}
    if len(found) != 1:
        raise ValueError('Frozen source path is missing or ambiguous: ' + name)
    return found.pop()


def verify_sources(protocol):
    hashes = protocol.get('source_hashes')
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('protocol.source_hashes is required')
    checked = {}
    for name, expected in hashes.items():
        path = source_path(name)
        if not isinstance(expected, str) or sha(path) != expected.removeprefix('sha256:'):
            raise ValueError('Frozen source hash mismatch: ' + name)
        checked[path] = expected
    required = {Path(__file__).resolve(), ROOT/'case_plans.json', ROOT/'budgets.json',
                PILOT/'case_plans.json', PILOT/'methods_full.py',
                PILOT/'resilient_candidates_v4/api_adapter.py',
                PILOT/'pending_v2/budget_guard.py',
                PILOT/'recovery_v1/recovery_transport.py', PILOT/'api_budget_client.py',
                SCIENCE/'science_support.py', SCIENCE/'budget_client.py', ROOT/'report_results.py'}
    if not required <= checked.keys():
        raise ValueError('Protocol does not freeze every required runner/science/transport input: ' +
                         ', '.join(sorted(str(p) for p in required-checked.keys())))


def identity(budget, method, protocol_hash):
    return {'model': budget['model'], 'method': method, 'case_uid': budget['case_uid'],
            'case_slot': budget['case_slot'], 'B': budget['token_cap'],
            'protocol_sha256': protocol_hash}


def validate_record(record, expected, terminal=True):
    if any(record.get(k) != value for k, value in expected.items()):
        raise ValueError('Existing result/attempt identity or protocol mismatch')
    if terminal and record.get('status') not in TERMINAL:
        raise ValueError('Existing final has an unrecognized terminal status')


def write_report():
    """Reporting cannot abort model work; inference records remain authoritative."""
    try:
        report_module = sys.modules.get('api80_results_report')
        if report_module is None:
            report_module = module('api80_results_report', ROOT/'report_results.py')
        report_module.report(root=ROOT)
    except Exception as error:
        save(ROOT/'report_error.json', {'at': now(), 'error_type': type(error).__name__,
                                       'error': safe_error(error)})


def prepare():
    protocol = read(ROOT/'protocol.json')
    verify_sources(protocol)
    if protocol.get('endpoint', ENDPOINT) != ENDPOINT:
        raise ValueError('Only the frozen XHub endpoint is allowed')
    if protocol.get('per_model_cell_concurrency', CONCURRENCY) != CONCURRENCY:
        raise ValueError('This runner permits exactly 8 active cells per model')
    plans, budgets = read(ROOT/'case_plans.json'), read(ROOT/'budgets.json')
    pilot_plans = read(PILOT/'case_plans.json')
    if set(plans) != set(MODELS) or len(budgets) != 140:
        raise ValueError('Expected two models, 70 cases/model, 140 model-case budgets')
    budget_map = {(b['model'], b['case_uid']): b for b in budgets}
    if len(budget_map) != 140:
        raise ValueError('Duplicate budget identity')
    for model in MODELS:
        cases = plans[model]
        uids = {c['case_uid'] for c in cases}
        pilot_uids = {c['case_uid'] for c in pilot_plans[model]}
        if len(cases) != 70 or len(uids) != 70 or len(pilot_uids) != 10 or uids & pilot_uids:
            raise ValueError('The new scope must be 70 unique cases disjoint from the original 10')
        if len({c['case_slot'] for c in cases}) != 70:
            raise ValueError('New case slots must be unique within each model')
        for case in cases:
            b = budget_map.get((model, case['case_uid']))
            if b is None or b['domain'] != case['domain'] or b['case_slot'] != case['case_slot']:
                raise ValueError('Budget and case plan identity differ')
            if type(b['token_cap']) is not int or b['token_cap'] <= 0:
                raise ValueError('Every case needs an explicit positive integer token ceiling')
            if type(b['case_slot']) is not int or b['case_slot'] <= 0:
                raise ValueError('Case slots must be positive integers')
    if {c['case_uid'] for c in plans[MODELS[0]]} != {c['case_uid'] for c in plans[MODELS[1]]}:
        raise ValueError('Both models must evaluate the same 70 cases')
    # The science loader deliberately disables further dotenv loads.
    from dotenv import load_dotenv
    load_dotenv(REPO/'.env')
    sys.path[:0] = [str(PILOT), str(REPO)]
    support = module('api80_science_support', SCIENCE/'science_support.py')
    launcher, cost, manifest, graphs, mainplan = support.load_science()
    known = {c['case_uid'] for c in mainplan}
    for model in MODELS:
        if {c['case_uid'] for c in plans[model]} | {c['case_uid'] for c in pilot_plans[model]} != known:
            raise ValueError('Original 10 plus new 70 do not exactly cover the verified main 80')
    declared_science = protocol.get('science_source_hashes')
    if declared_science is not None and declared_science != manifest['unchanged_code_sha256']:
        raise ValueError('Verified science bundle differs from protocol')
    api = module('budget_client', PILOT/'resilient_candidates_v4/api_adapter.py')
    methods = module('api80_frozen_methods', PILOT/'methods_full.py')
    api.wrap_candidate_functions(methods)
    original_judge_cost = methods.judge_cost
    methods.judge_cost = lambda client, source, pool: (
        original_judge_cost(client, source, pool) + api.selector_extra_reserve(client))
    prepared = {}
    for model in MODELS:
        cost.validate_case_plan(plans[model], graphs)
        for case in plans[model]:
            graph, scc, _, _ = cost.prepare_injected_case(case, graphs)
            prepared[(model, case['case_uid'])] = (case, graph, scc)
    protocol_hash = sha(ROOT/'protocol.json')
    jobs, existing = [], {}
    for b in sorted(budgets, key=lambda b: (b['model'], b['case_slot'])):
        for method in METHODS:
            folder = ROOT/'results'/b['model']/f"{b['case_slot']:02d}"/method
            expected = identity(b, method, protocol_hash)
            key = f"{b['model']}/{b['case_slot']:02d}/{method}"
            if (folder/'final.json').exists():
                record = read(folder/'final.json')
                validate_record(record, expected)
                existing[key] = record
            elif (folder/'attempt.json').exists():
                validate_record(read(folder/'attempt.json'), expected, terminal=False)
            elif (folder/'ledger.jsonl').exists() or any((folder/'calls').glob('*.json')):
                raise ValueError('Refusing an unbound existing request ledger without attempt identity')
            jobs.append((key, b, method, folder, expected))
    allowed = {folder/'final.json' for _, _, _, folder, _ in jobs}
    if set((ROOT/'results').glob('*/*/*/final.json')) - allowed:
        raise ValueError('Results directory contains a final outside the frozen 280-cell scope')
    verify_sources(protocol)
    if sha(ROOT/'protocol.json') != protocol_hash:
        raise ValueError('Protocol changed during preflight')
    return support, api, methods, prepared, jobs, existing, protocol_hash


async def execute(loaded):
    support, api, methods, prepared, jobs, finished, protocol_hash = loaded
    active = {}
    semaphores = {model: asyncio.Semaphore(CONCURRENCY) for model in MODELS}
    started = time.monotonic()

    def status(state):
        per_model = {}
        for model in MODELS:
            rows = [r for r in finished.values() if r['model'] == model]
            per_model[model] = {'planned': 140, 'completed': len(rows),
                'complete': sum(r['status'] == 'complete' for r in rows),
                'failed': sum(r['status'] != 'complete' for r in rows),
                'active': sum(x['model'] == model for x in active.values())}
        snapshot = {key: {k: v for k, v in row.items() if k != 'client'}
                    for key, row in active.items()}
        for key, row in active.items():
            if row.get('client') is not None:
                snapshot[key]['usage'] = row['client'].summary()
        save(ROOT/'status.json', {'status': state, 'updated_at': now(),
            'protocol_sha256': protocol_hash, 'planned_cells': EXPECTED,
            'completed_cells': len(finished), 'remaining_cells': EXPECTED-len(finished),
            'complete_cells': sum(r['status'] == 'complete' for r in finished.values()),
            'failed_cells': sum(r['status'] != 'complete' for r in finished.values()),
            'per_model_cell_concurrency': CONCURRENCY, 'per_model': per_model,
            'active': snapshot, 'elapsed_seconds': time.monotonic()-started})

    async def heartbeat():
        while True:
            await asyncio.sleep(15)
            status('running')

    async def cell(key, b, method, folder, expected):
        if key in finished:
            return
        async with semaphores[b['model']]:
            folder.mkdir(parents=True, exist_ok=True)
            # A same-directory second process is excluded by runner.lock;
            # the original ledger also holds a per-cell filesystem lock.
            if (folder/'final.json').exists():
                record = read(folder/'final.json')
                validate_record(record, expected)
                finished[key] = record
                return
            record = {**expected, 'domain': b['domain'], 'started_at': now(),
                      'selected_result': None, 'selection': None,
                      'status': 'running', 'budget_source': b.get('budget_source')}
            if (folder/'attempt.json').exists():
                prior = read(folder/'attempt.json')
                validate_record(prior, expected, terminal=False)
                record['first_started_at'] = prior.get('first_started_at', prior['started_at'])
            save(folder/'attempt.json', record)
            legacy = folder/'legacy_call_ids.json'
            if legacy.exists():
                if read(legacy) != []:
                    raise ValueError('Fresh 70-case cells must retain an empty legacy prefix')
            else:
                save(legacy, [])
            case, graph, scc = prepared[(b['model'], b['case_uid'])]
            client = ledger = None
            begun = time.monotonic()
            active[key] = {'model': b['model'], 'method': method, 'case_uid': b['case_uid'],
                           'case_slot': b['case_slot'], 'started_at': record['started_at'], 'B': b['token_cap']}
            status('running')
            print(json.dumps({'event': 'cell_started', 'cell': key}), flush=True)
            try:
                ledger = api.GlobalLedger(folder/'ledger.jsonl')
                await ledger.initialize()
                client = api.BudgetClient({'model': b['model'], 'base_url': ENDPOINT,
                    'max_model_len': 131072, 'timeout': 600, 'max_retries': 0},
                    ledger=ledger, case_id=b['case_uid'], method=method,
                    call_log_dir=folder/'calls', token_cap=b['token_cap'])
                active[key]['client'] = client
                raw = await methods.baseline(client, support.science_args(b['model']),
                                             case, graph, scc, method, folder)
                save(folder/'inference.json', raw)
                record.update(selected_result=raw.get('selected_result'), selection=raw.get('selection'))
                record['metrics'] = support.metrics(record['selected_result'], method, case)
                record['status'] = 'complete' if record['metrics']['valid'] else 'scientific_failure'
            except BaseException as error:
                if isinstance(error, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                    raise
                reason = getattr(error, 'reason', '')
                budget_failure = reason in {'budget_overrun', 'transport_budget_exhausted',
                    'no_output_budget', 'tokens', 'token_cap_exhausted'}
                scientific = isinstance(error, (ValueError, TypeError, KeyError, AttributeError))
                record.update(status='budget_violation' if budget_failure else
                    ('scientific_failure' if scientific else 'infrastructure_failure'),
                    error_type=type(error).__name__, error=safe_error(error),
                    metrics=support.metrics(None, method, case, False))
            finally:
                if client is not None:
                    record['usage'] = client.summary()
                elif ledger is not None and getattr(ledger, '_initialized', False):
                    record['usage'] = ledger.owner_summary(b['case_uid'], b['model'], method)
                record.update(ended_at=now(), elapsed_seconds=time.monotonic()-begun)
                cleanup_errors = []
                for resource in (client, ledger):
                    if resource is not None:
                        try:
                            await resource.close()
                        except Exception as error:
                            cleanup_errors.append({'type': type(error).__name__, 'error': safe_error(error)})
                if cleanup_errors:
                    record['cleanup_errors'] = cleanup_errors
                active.pop(key, None)
            save(folder/'final.json', record)
            finished[key] = record
            status('running')
            write_report()
            print(json.dumps({'event': 'cell_finished', 'cell': key, 'status': record['status'],
                              'completed_cells': len(finished)}), flush=True)

    status('running')
    ticker = asyncio.create_task(heartbeat())
    try:
        await asyncio.gather(*(cell(*job) for job in jobs))
    finally:
        ticker.cancel()
        await asyncio.gather(ticker, return_exceptions=True)
        status('finished' if len(finished) == EXPECTED else 'interrupted')
        write_report()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Explicitly allow the frozen paid batch')
    cli = parser.parse_args()
    os.umask(0o077)
    with (ROOT/'runner.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        loaded = prepare()
        preflight = {'status': 'passed', 'checked_at': now(), 'model_calls': 0,
            'planned_cells': EXPECTED, 'cases_per_model': 70, 'models': list(MODELS),
            'methods': list(METHODS), 'preserved_existing_finals': len(loaded[5]),
            'protocol_sha256': loaded[6], 'per_model_cell_concurrency': CONCURRENCY}
        save(ROOT/'preflight.json', preflight)
        print(json.dumps({'event': 'preflight_complete', **preflight, 'paid_run': cli.run}), flush=True)
        if cli.run:
            if not os.environ.get('XHUB_API_KEY', '').strip():
                raise ValueError('XHUB_API_KEY is required for --run')
            save(ROOT/'launch.json', {'pid': os.getpid(), 'started_at': now(),
                 'protocol_sha256': loaded[6], 'planned_cells': EXPECTED,
                 'per_model_cell_concurrency': CONCURRENCY})
            asyncio.run(execute(loaded))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'event': 'runner_stopped', 'error_type': type(error).__name__,
                          'error': safe_error(error)}), file=sys.stderr, flush=True)
        raise SystemExit(1) from None

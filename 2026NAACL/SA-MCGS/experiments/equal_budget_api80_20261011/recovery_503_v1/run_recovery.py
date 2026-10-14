#!/usr/bin/env python3
"""Recover only scoped HTTP-503 interruptions; preserve original inference files."""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time
import tiktoken
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT.parent
MODELS = ('gpt-4o', 'gemini-2.5-pro')
CONCURRENCY = 8
ENCODING = tiktoken.get_encoding('cl100k_base')

def read(path):
    return json.loads(Path(path).read_text())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.tmp')
    with tmp.open('w') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result

def key(entry):
    return f"{entry['model']}/{entry['case_slot']:02d}/{entry['method']}"

def identity(entry):
    return {k: entry[k] for k in ('model', 'method', 'case_uid', 'case_slot', 'mode')}

def check_identity(record, entry):
    if record.get('identity') != identity(entry):
        raise ValueError('Recovery result identity mismatch')

def verify_sources(scope):
    for path, expected in scope['source_hashes'].items():
        if sha(path) != expected:
            raise ValueError('Frozen recovery source changed: ' + path)

def metrics(support, selected, method, case):
    m = support.metrics(selected, method, case)
    if not m['valid']:
        m['compression'] = 1.0
    return m

def usage_sum(rows):
    result = {}
    for name in ('calls', 'prompt_tokens', 'completion_tokens', 'total_tokens',
                 'estimated_cost_usd', 'http503_calls', 'retry_calls', 'cache_replays'):
        result[name] = sum(x.get(name, 0) for x in rows)
    return result

def selector_context_cost(methods, source, pool, model):
    view, _ = methods.presentation(pool)
    prompt = methods.judge_prompt(source, view)
    inputs = math.ceil(len(ENCODING.encode(prompt, disallowed_special=()))*1.25) + 256 + 16
    return inputs + methods.JUDGE_OUTPUT + (16384 if model == 'gemini-2.5-pro' else 0)

def merged_report(scope, finished):
    merged = read(scope['original_merged_results'])
    replacements = {(x['identity']['model'], x['identity']['method'], x['identity']['case_uid']): x
                    for x in finished.values()}
    for row in merged:
        rec = replacements.get((row['model'], row['method'], row['case_uid']))
        if rec is None:
            continue
        row['before_recovery_metrics'] = row['reporting_metrics']
        for field in ('status', 'reporting_state', 'reporting_mapping'):
            row['before_recovery_' + field] = row.get(field)
        row['recovery_source'] = str(ROOT/'results'/key(rec['identity'])/'final.json')
        row['recovery_status'] = rec['status']
        row['status'] = rec['status']
        row['reporting_state'] = 'valid_output' if rec['metrics']['valid'] else 'empty_output'
        row['reporting_mapping'] = 'HTTP503 recovery; invalid output maps to hits0/compression1'
        row['valid_output'] = rec['metrics']['valid']
        row['metrics'] = row['reporting_metrics'] = rec['metrics']
        row['recovery_selected_result'] = rec.get('selected_result')
    groups = []
    for model in MODELS:
        for method in ('sa-mcgs', 'lea', 'full-scc'):
            rs = [r for r in merged if r['model'] == model and r['method'] == method]
            if len(rs) != 80:
                raise ValueError('Merged row must retain exactly 80 cases')
            groups.append({'model': model, 'method': method, 'n': 80,
                           'valid': sum(r['valid_output'] for r in rs),
                           **{n: sum(r['reporting_metrics'][n] for r in rs)/80
                              for n in ('risk_all', 'root_at_3', 'risk_any', 'compression')}})
    summary = {'updated_at': now(), 'recovery_complete': len(finished) == len(scope['entries']),
               'recovery_finished': len(finished), 'recovery_planned': len(scope['entries']),
               'recovered_valid_cells': sum(r['metrics']['valid'] for r in finished.values()),
               'excluded_non503_cells': len(scope['excluded']), 'groups': groups,
               'recovery_usage': usage_sum([r['recovery_usage'] for r in finished.values()]),
               'budget_policy': 'Historical usage unchanged; bounded service-recovery costs recorded separately.'}
    save(ROOT/'reports/summary.json', summary)
    save(ROOT/'reports/case_results.json', merged)
    lines = ['# HTTP 503 补跑结果', '',
             f"已处理 {len(finished)}/{len(scope['entries'])} 项；恢复有效输出 {summary['recovered_valid_cells']} 项。9 项非 503 错误仍按错误计分。",
             '', '| 模型 | 方法 | Risk-all | Root@3 | Risk-any | 压缩率 | 有效输出 |',
             '|---|---|---:|---:|---:|---:|---:|']
    for g in groups:
        lines.append(f"| {g['model']} | {g['method']} | {g['risk_all']*100:.2f}% | {g['root_at_3']*100:.2f}% | {g['risk_any']*100:.2f}% | {g['compression']*100:.2f}% | {g['valid']}/80 |")
    lines += ['', '补跑只恢复指定 503 请求及完成其中断候选所需的后续窗口；已有成功请求复用。42 项选择器失败只补最后选择。',
              '恢复开销单独记录，原始结果和原始消耗保留。无最终有效结果的三个命中指标为 0，压缩率为 100%。']
    (ROOT/'reports/RESULTS_ZH.md').write_text('\n'.join(lines)+'\n')

async def execute(scope, support, methods, prepared, client_module, *, paid, only_mode=None):
    Client = client_module.RecoveryClient
    active, finished = {}, {}
    semaphores = {m: asyncio.Semaphore(CONCURRENCY) for m in MODELS}
    start = time.monotonic()
    for entry in scope['entries']:
        path = ROOT/'results'/key(entry)/'final.json'
        if path.exists():
            record = read(path); check_identity(record, entry); finished[key(entry)] = record

    def status(state):
        live = {}
        for k, x in active.items():
            live[k] = {n: v for n, v in x.items() if n != 'client'}
            if x.get('client') is not None:
                live[k]['current_usage'] = x['client'].summary()
        save(ROOT/'status.json', {'state': state, 'updated_at': now(),
             'planned': len(scope['entries']), 'finished': len(finished),
             'valid_recovered': sum(r['metrics']['valid'] for r in finished.values()),
             'active': live, 'per_model_concurrency': CONCURRENCY,
             'elapsed_seconds': round(time.monotonic()-start, 2),
             'completed_recovery_usage': usage_sum([r['recovery_usage'] for r in finished.values()])})

    async def ticker():
        while True:
            await asyncio.sleep(15)
            status('running')

    async def cell(entry):
        k = key(entry)
        if k in finished:
            return
        async with semaphores[entry['model']]:
            folder = ROOT/'results'/k
            folder.mkdir(parents=True, exist_ok=True)
            case, graph, scc = prepared[(entry['model'], entry['case_uid'])]
            source, aliases = methods.source_view(graph, scc)
            args = support.science_args(entry['model'])
            record = {'identity': identity(entry), 'started_at': now(), 'source_final': entry['source_final'],
                      'source_final_sha256': entry['source_final_sha256'],
                      'original_usage': entry['original_usage'], 'original_B': entry['original_B'],
                      'selected_result': None, 'selection': {}, 'recovery_usage': {}}
            usages = []
            active[k] = {'mode': entry['mode'], 'started_at': now(), 'candidate_done': 0,
                         'candidate_planned': len(entry['candidates']), 'client': None}
            pool = [read(p) for p in entry['complete_candidate_paths']]
            print(json.dumps({'event': 'recovery_started', 'cell': k, 'mode': entry['mode']}), flush=True)

            async def run_client(call_folder, histories, phase, operation):
                client = Client(model=entry['model'], method=entry['method'], folder=call_folder,
                                historical_calls=[read(p) for p in histories], phase=phase, paid_allowed=paid)
                active[k]['client'] = client
                try:
                    result = await operation(client)
                    client.assert_history_consumed()
                    return result
                finally:
                    usages.append(client.summary())
                    await client.close()
                    active[k]['client'] = None

            try:
                if entry['mode'] == 'candidate_recovery':
                    for target in entry['candidates']:
                        index = target['candidate_index']
                        target_folder = folder/f'candidate_{index:04d}'
                        final_path = target_folder/'candidate_result.json'
                        if final_path.exists():
                            item = read(final_path)
                            if item['source_candidate_sha256'] != sha(target['path']):
                                raise ValueError('Candidate changed on recovery resume')
                            usages.append(item['recovery_usage'])
                        else:
                            item = {'candidate_index': index, 'source_candidate': target['path'],
                                    'source_candidate_sha256': sha(target['path']), 'status': 'failed'}
                            before_usage_count = len(usages)
                            async def generate(client):
                                if entry['method'] == 'lea':
                                    return await methods.cost.run_lea(client, args, case, graph, scc, {})
                                return await methods.cost.battle.run_naive(client, args.model, case['domain'], graph, scc,
                                           naive_profile='direct_subgraph', injected_id=None, temperature=.4)
                            try:
                                result = await run_client(target_folder/'requests', target['historical_call_files'],
                                                          'candidate', generate)
                                if not methods.valid(result, scc, entry['method']):
                                    raise ValueError('Recovered candidate has invalid native output')
                                item.update(status='complete', result=result,
                                            judge_view=methods.judge_view(result, entry['method'], aliases))
                                if selector_context_cost(methods, source, [*pool, item], entry['model']) > 131072:
                                    item['status'] = 'complete_excluded_selector_capacity'
                            except BaseException as error:
                                if isinstance(error, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                                    raise
                                item.update(error_type=type(error).__name__, error=str(error)[:800])
                            item['recovery_usage'] = usage_sum(usages[before_usage_count:])
                            save(final_path, item)
                        if item['status'] == 'complete':
                            pool.append(item)
                        active[k]['candidate_done'] += 1
                        active[k]['complete_candidates'] = len(pool)
                        status('running')
                        if item['status'] == 'complete_excluded_selector_capacity':
                            record['candidate_stop_reason'] = 'selector_capacity_for_new_candidate'
                            break

                chosen = None
                selection = {'complete_candidates': len(pool)}
                if not pool:
                    selection['status'] = 'no_complete_candidate'
                elif len(pool) == 1:
                    chosen = pool[0]
                    selection['status'] = 'single_complete_candidate_no_judge'
                else:
                    if entry['mode'] == 'selector_only':
                        mapping_ids = read(entry['judge_candidate_mapping_path'])
                        by_index = {p['candidate_index']: p for p in pool}
                        mapping = {cid: by_index[index] for cid, index in mapping_ids.items()}
                        prompt = Path(entry['judge_prompt_path']).read_text()
                        history = entry['selector_calls']
                    else:
                        view, mapping = methods.presentation(pool)
                        prompt = methods.judge_prompt(source, view)
                        history = []
                    (folder/'judge_prompt.txt').write_text(prompt)
                    save(folder/'judge_candidate_mapping.json', {c: p['candidate_index'] for c,p in mapping.items()})
                    async def judge(client):
                        estimate = client.estimate_request(prompt, max_tokens=methods.JUDGE_OUTPUT, respect_budget=False)
                        if estimate['input_tokens']+methods.JUDGE_OUTPUT > client.max_model_len:
                            raise ValueError('Recovered selector exceeds frozen context limit')
                        return await client.call_json(prompt, temperature=0, max_tokens=methods.JUDGE_OUTPUT)
                    answer = await run_client(folder/'selector_requests', history, 'selector', judge)
                    save(folder/'judge_response.json', answer)
                    if isinstance(answer, dict) and set(answer) == {'candidate_id'} and answer['candidate_id'] in mapping:
                        chosen = mapping[answer['candidate_id']]
                        selection['status'] = 'judged'
                    else:
                        selection['status'] = 'selector_invalid_response'
                record['selected_result'] = chosen['result'] if chosen else None
                selection['selected_candidate_index'] = chosen['candidate_index'] if chosen else None
                record['selection'] = selection
                record['metrics'] = metrics(support, record['selected_result'], entry['method'], case)
                record['status'] = 'complete' if record['metrics']['valid'] else 'failed'
            except BaseException as error:
                if isinstance(error, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                    raise
                record.update(status='failed', error_type=type(error).__name__, error=str(error)[:800],
                              metrics=metrics(support, None, entry['method'], case))
            record.update(ended_at=now(), recovery_usage=usage_sum(usages))
            save(folder/'final.json', record)
            finished[k] = record
            active.pop(k, None)
            status('running'); merged_report(scope, finished)
            print(json.dumps({'event': 'recovery_finished', 'cell': k, 'status': record['status'],
                              'finished': len(finished), 'usage': record['recovery_usage']}), flush=True)

    beat = asyncio.create_task(ticker())
    status('running')
    try:
        # Finish already-complete candidate pools before recovering local windows.
        for mode in ('selector_only', 'candidate_recovery'):
            if only_mode is not None and only_mode != mode:
                continue
            await asyncio.gather(*(cell(e) for e in scope['entries'] if e['mode'] == mode))
    finally:
        beat.cancel(); await asyncio.gather(beat, return_exceptions=True)
        status('finished' if len(finished) == len(scope['entries']) else 'stage_finished')
        merged_report(scope, finished)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--only-mode', choices=['selector_only', 'candidate_recovery'])
    cli = parser.parse_args()
    os.umask(0o077)
    with (ROOT/'runner.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)
        scope = read(ROOT/'scope.json')
        verify_sources(scope)
        old = module('api80_recovery_original_runner', ORIGINAL/'run_remaining.py')
        support, _, methods, prepared, *_ = old.prepare()
        client_module = module('api80_explicit503_recovery_client', ROOT/'recovery_client.py')
        protocol = {'schema': 'api80_explicit503_recovery.v1', 'scope_sha256': sha(ROOT/'scope.json'),
                    'source_hashes': {p: sha(ROOT/p) for p in ('run_recovery.py', 'recovery_client.py')},
                    'per_model_concurrency': CONCURRENCY, 'historical_503_max_new_attempts': 2,
                    'new_window_503_max_retries': 2, 'selector_only_cells': 42,
                    'candidate_recovery_cells': 119, 'new_independent_candidates': 0,
                    'budget_policy': 'Recovery overhead separately accounted; original ceilings and usage preserved.',
                    'algorithm': 'Frozen native generators, validation, anonymous seeded candidate presentation and same-model judge.'}
        protocol_file = ROOT/'protocol.json'
        if protocol_file.exists() and read(protocol_file) != protocol:
            raise ValueError('Recovery protocol changed after preflight')
        save(protocol_file, protocol)
        save(ROOT/'preflight.json', {'status': 'passed', 'at': now(), 'paid_calls': 0,
                                    'eligible_cells': len(scope['entries'])})
        print(json.dumps({'event': 'preflight_passed', 'paid_run': cli.run}), flush=True)
        if cli.run:
            save(ROOT/'launch.json', {'pid': os.getpid(), 'started_at': now(), 'only_mode': cli.only_mode})
            asyncio.run(execute(scope, support, methods, prepared, client_module, paid=True, only_mode=cli.only_mode))

if __name__ == '__main__':
    main()

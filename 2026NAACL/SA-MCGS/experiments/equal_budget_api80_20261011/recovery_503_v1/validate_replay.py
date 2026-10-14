#!/usr/bin/env python3
"""Offline integration check: frozen generation must replay up to its original503."""
import asyncio
from collections import Counter
from pathlib import Path
import tempfile
import time
import run_recovery as runner

async def check(scope, support, methods, prepared, module):
    count = Counter()
    issues = []
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='xhub503_offline_') as temp:
        for entry in scope['entries']:
            case, graph, scc = prepared[(entry['model'], entry['case_uid'])]
            jobs = entry['candidates'] if entry['mode'] == 'candidate_recovery' else [None]
            for item in jobs:
                historical = entry['selector_calls'] if item is None else item['historical_call_files']
                name = runner.key(entry) + ('/selector' if item is None else f"/candidate_{item['candidate_index']:04d}")
                client = module.RecoveryClient(model=entry['model'], method=entry['method'],
                         folder=Path(temp)/name, historical_calls=[runner.read(p) for p in historical],
                         phase='selector' if item is None else 'candidate', paid_allowed=False)
                try:
                    if item is None:
                        await client.call_json(Path(entry['judge_prompt_path']).read_text(), temperature=0,
                                               max_tokens=methods.JUDGE_OUTPUT)
                    elif entry['method'] == 'lea':
                        await methods.cost.run_lea(client, support.science_args(entry['model']), case, graph, scc, {})
                    else:
                        await methods.cost.battle.run_naive(client, entry['model'], case['domain'], graph, scc,
                                  naive_profile='direct_subgraph', injected_id=None, temperature=.4)
                    issues.append({'name': name, 'error': 'Unexpected complete output before retrying original503'})
                except BaseException as error:
                    if isinstance(error, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                        raise
                    reason = str(error)
                    if ('paid' in reason.lower() and ('disabled' in reason.lower() or 'not' in reason.lower())):
                        count['matched_original_failed_request'] += 1
                    else:
                        issues.append({'name': name, 'error_type': type(error).__name__, 'error': reason[:500]})
                finally:
                    summary = client.summary()
                    if summary.get('calls', 0) != 0:
                        issues.append({'name': name, 'error': 'Unexpected paid call count'})
                    count['cache_replays'] += summary.get('cache_replays', 0)
                    await client.close()
                count['checked'] += 1
                if count['checked'] % 100 == 0:
                    print(dict(count), 'issues', len(issues), flush=True)
    report = {'status': 'passed' if not issues else 'failed', 'paid_calls': 0,
              'counts': dict(count), 'issues': issues, 'elapsed_seconds': time.monotonic()-start}
    runner.save(runner.ROOT/'offline_replay_validation.json', report)
    print(report, flush=True)
    if issues:
        raise SystemExit(1)

if __name__ == '__main__':
    scope = runner.read(runner.ROOT/'scope.json')
    runner.verify_sources(scope)
    old = runner.module('api80_offline_recovery_original', runner.ORIGINAL/'run_remaining.py')
    support, _, methods, prepared, *_ = old.prepare()
    module = runner.module('api80_offline_recovery_client', runner.ROOT/'recovery_client.py')
    asyncio.run(check(scope, support, methods, prepared, module))

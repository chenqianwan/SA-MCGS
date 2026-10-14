#!/usr/bin/env python3
"""Verify every active arm's durable cached prefix without issuing inference.

Only isolated snapshots and receipts are written. A missing cached request raises
a BaseException before the original ledger can reserve it. Run with the original
shared Python, PYTHONHASHSEED=42, and the original tokenizer path.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import socket
import sys
import time
import traceback
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class ReplayViolation(BaseException):
    pass


class ReplayPrefixEnd(BaseException):
    def __init__(self, request):
        self.request = request


def require(condition, message):
    if not condition:
        raise ReplayViolation(message)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return sha_bytes(Path(path).read_bytes())


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.' + str(os.getpid()) + '.tmp')
    with tmp.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def complete_events(raw):
    """A writer may be appending; never parse or promote an incomplete line."""
    end = raw.rfind(b'\n') + 1
    require(end > 0, 'No complete source ledger header')
    events = [json.loads(line) for line in raw[:end].splitlines()]
    require(events[0].get('event') == 'header', 'Missing source ledger header')
    return events, end


def reconstruct(events):
    rows = {}
    for event in events[1:]:
        kind = event.get('event')
        if kind == 'reserve':
            require(event['call_id'] not in rows, 'Duplicate source reservation')
            rows[event['call_id']] = {**event, 'status': 'reserved'}
        elif kind == 'finish':
            row = rows[event['call_id']]
            require(row['status'] == 'reserved', 'Duplicate source settlement')
            row.update(event)
        elif kind == 'parse':
            rows[event['call_id']].setdefault('parse_events', []).append(event)
        else:
            require(kind in ('owner', 'freeze_budget'), 'Unknown source ledger event')
    return list(rows.values())


def snapshot_arm(source, destination):
    """Copy a point-in-time durable completed prefix; never lock the live ledger."""
    source, destination = Path(source), Path(destination)
    require(not destination.exists(), 'Snapshot destination already exists: ' + str(destination))
    require(source.resolve() == source and not source.is_symlink(), 'Redirected source arm')
    destination.mkdir(parents=True)
    raw = (source/'ledger.jsonl').read_bytes()
    events, complete_end = complete_events(raw)
    rows = reconstruct(events)
    known, omitted = [], []
    for row in rows:
        if not omitted and row['status'] == 'completed_with_usage':
            require(not row.get('usage_issues'), 'Source usage mismatch')
            known.append(row)
        else:
            omitted.append(row)
    require(all(row['status'] == 'reserved' for row in omitted),
            'Source has unresolved failure or a noncontinuous completed prefix')
    require(len(omitted) <= 1, 'More than one outstanding sequential request')
    known_ids = {row['call_id'] for row in known}
    cache_map, cache_hashes = {}, {}
    for row in known:
        path = Path(row['cache_file'])
        path = path if path.is_absolute() else source/path
        require(path.resolve().is_relative_to(source.resolve()), 'Cache escapes source arm')
        data = path.read_bytes()
        cache = json.loads(data)
        require(cache.get('call_id') == row['call_id']
                and cache.get('request_hash') == row['request_hash']
                and isinstance(cache.get('result'), dict), 'Source cache identity mismatch')
        relative = Path('calls')/(row['call_id'] + '.json')
        target = destination/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        cache_map[row['call_id']] = str(relative)
        cache_hashes[str(path)] = sha_bytes(data)
    filtered = []
    for original in events:
        event = dict(original)
        if event.get('event') in ('reserve', 'finish', 'parse'):
            if event['call_id'] not in known_ids:
                continue
            if event['event'] == 'reserve':
                event['cache_file'] = cache_map[event['call_id']]
        filtered.append(event)
    copied = ''.join(json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n'
                     for event in filtered).encode()
    (destination/'source_ledger_bytes.jsonl').write_bytes(raw)
    (destination/'ledger.jsonl').write_bytes(copied)
    evidence = {
        'source_path': str(source), 'snapshot_path': str(destination),
        'source_ledger_sha256': sha_bytes(raw), 'source_ledger_bytes': len(raw),
        'source_complete_bytes': complete_end, 'ignored_partial_bytes': len(raw)-complete_end,
        'source_complete_sha256': sha_bytes(raw[:complete_end]),
        'snapshot_initial_ledger_sha256': sha_bytes(copied),
        'source_cache_hashes': cache_hashes, 'prefix_calls': len(known),
        'prefix_call_ids': [row['call_id'] for row in known],
        'prefix_request_keys': [row['request_key'] for row in known],
        'prefix_request_hashes': [row['request_hash'] for row in known],
        'omitted_reservations': omitted,
        'source_parse_events': {row['call_id']: [p['outcome'] for p in row.get('parse_events', [])]
                                for row in known},
    }
    save(destination/'snapshot.json', evidence)
    return evidence


class DisabledProvider:
    def __init__(self):
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.calls += 1
        raise ReplayViolation('Replay attempted a provider request')

    async def close(self):
        return None


async def replay_once(snapshot, evidence, case, method, ref, cfg, tokenizer, hashes,
                      cost, graphs, budget, methods, support):
    ledger = budget.GlobalLedger(snapshot/'ledger.jsonl')
    await ledger.initialize()
    provider, client = DisabledProvider(), None
    expected_keys = evidence['prefix_request_keys']
    consumed = []
    next_request = None
    baseline_returned = False
    before = ledger.owner_summary(case['case_uid'], cfg['alias'], method)
    require(before['held_calls'] == 0 and before['usage_mismatch_calls'] == 0,
            'Snapshot retains an unsettled or mismatched call')
    original_reserve = ledger.reserve

    async def cached_only_reserve(**kwargs):
        key = (*kwargs['owner'], kwargs['request_key'])
        if key not in ledger._keys:
            raise ReplayPrefixEnd(kwargs)
        require(len(consumed) < len(expected_keys)
                and kwargs['request_key'] == expected_keys[len(consumed)],
                'Replay changed the cached call order')
        row, cached = await original_reserve(**kwargs)
        require(cached, 'Original ledger tried to reserve during replay')
        consumed.append(kwargs['request_key'])
        return row, cached

    ledger.reserve = cached_only_reserve
    try:
        cost.validate_case_plan([case], graphs)
        graph, scc, _, _ = cost.prepare_injected_case(case, graphs)
        client = budget.BudgetClient(
            config={'timeout': 1800, 'max_model_len': cfg['max_model_len'],
                    'tokenizer_fingerprint': support.digest(hashes)},
            ledger=ledger, case_id=case['case_uid'], method=method,
            tokenizer=tokenizer, model=cfg['alias'], base_url='http://127.0.0.1:1/v1',
            call_log_dir=snapshot/'calls', token_cap=ref['usage']['total_tokens'],
            json_attempts=3, selector_json_attempts=1,
            chat_template_kwargs=cfg.get('chat_template_kwargs', {}), provider_client=provider)
        for owner in ledger._owners.values():
            require(owner.get('owner') == list(client.owner)
                    and owner.get('token_cap') == client.token_cap
                    and owner.get('fingerprint') == client.fingerprint,
                    'Original owner/fingerprint differs from replay configuration')
        random.seed(42)
        try:
            await methods.baseline(client, support.science_args(cfg['alias']), case,
                                   graph, scc, method, snapshot/'replayed_outputs')
            baseline_returned = True
        except ReplayPrefixEnd as boundary:
            next_request = boundary.request
        require(consumed == expected_keys, 'Replay did not consume the entire cached prefix')
        require(provider.calls == 0, 'Provider was called')
        after = ledger.owner_summary(*client.owner)
        for name in ('calls', 'completed_with_usage', 'held_calls', 'prompt_tokens',
                     'completion_tokens', 'total_tokens', 'accounted_tokens'):
            require(before[name] == after[name], 'Durable token accounting changed: '+name)
        for name in ('prompt_tokens', 'completion_tokens', 'total_tokens', 'held_tokens', 'accounted_tokens'):
            require(client.token_usage[name] == before[name], 'Virtual prefix usage differs: '+name)
        omitted = evidence['omitted_reservations']
        next_matches = None
        if omitted:
            require(next_request is not None, 'Source is in flight but replay stopped earlier')
            pending = omitted[0]
            mapping = {'request_key': 'request_key', 'request_hash': 'request_hash',
                       'phase': 'phase', 'input_tokens': 'input_tokens',
                       'max_output': 'max_output_tokens', 'selector_reserve': 'selector_reserve',
                       'requested_max_output': 'requested_max_output_tokens', 'retry_index': 'retry_index'}
            for incoming, stored in mapping.items():
                require(next_request[incoming] == pending[stored],
                        'Next in-flight request changed: ' + incoming)
            next_matches = True
        return {'cached_calls_consumed': len(consumed), 'provider_calls': provider.calls,
                'owner_fingerprint': client.fingerprint, 'usage': client.token_usage,
                'ledger_usage': after, 'baseline_returned': baseline_returned,
                'next_request': next_request, 'next_request_matches_source_reserved': next_matches,
                'parse_outcomes': {row['call_id']: [p['outcome'] for p in row.get('parse_events', [])]
                                   for row in ledger.owner_records(*client.owner)}}
    finally:
        if client is not None:
            await client.close()
        await ledger.close()


async def audit(args):
    require(os.environ.get('PYTHONHASHSEED') == '42', 'Run with PYTHONHASHSEED=42')
    sys.path.insert(0, str(ROOT))
    import runner
    import science_support as support
    loaded = runner.load_science()
    launcher, cost, manifest, graphs, plan = loaded
    import budget_client as budget
    import methods_full as methods
    from transformers import AutoTokenizer
    endpoints = read(ROOT/'endpoints.json')
    runner.validate_endpoints(endpoints)
    scope = runner.load_scope(plan)
    refs = runner.historical_reference(plan)
    cfg = endpoints['models']['qwen25']
    tokenizer = AutoTokenizer.from_pretrained(cfg['tokenizer_path'], local_files_only=True,
                                              trust_remote_code=cfg.get('trust_remote_code', False))
    hashes = support.tokenizer_hashes(cfg['tokenizer_path'])
    require(hashes == read(ROOT/'tokenizer_hashes/qwen25.json'), 'Frozen tokenizer hashes changed')
    protocol = read(ROOT/'protocol.json')
    require(runner.protocol(launcher, manifest, scope, endpoints['models']) == protocol,
            'Frozen scientific protocol differs from current source/configuration')
    source_hashes = {name: sha(ROOT/name) for name in
                    ('runner.py', 'science_support.py', 'methods_full.py', 'budget_client.py',
                     'protocol.json', 'historical_sa_reference.json', 'run_scope.json', 'endpoints.json')}
    plan_by_uid = {case['case_uid']: case for case in plan}
    active = sorted(path.parent for path in (ROOT/'results/qwen25').glob('*/*/ledger.jsonl')
                    if not (path.parent/'final.json').exists())
    require(bool(active), 'No active arms to verify')
    receipt = {'schema': 'qwen_scale48_cache_replay_v1', 'status': 'running',
               'started_at': now(), 'root': str(ROOT), 'pid': os.getpid(),
               'snapshot_dir': str(args.snapshot_dir), 'source_hashes': source_hashes,
               'script_sha256': sha(__file__), 'tokenizer_hashes': hashes,
               'protocol_sha256': support.digest(protocol), 'arm_count': len(active),
               'all_active_arms_verified': False, 'provider_calls': 0, 'source_cache_sha256': {},
               'active_arm_identities': [], 'errors': []}
    save(args.output, receipt)
    # Defense in depth: scientific replay cannot issue network connections even
    # if future repository code bypasses the supplied DisabledProvider.
    old_connect, old_connect_ex, old_getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
    def network_disabled(*_args, **_kwargs):
        raise ReplayViolation('Network disabled during cached-prefix verification')
    socket.socket.connect = socket.socket.connect_ex = socket.getaddrinfo = network_disabled
    try:
        for source in active:
            uid, method = source.parent.name, source.name
            snapshot = args.snapshot_dir/uid/method
            evidence = {'case_uid': uid, 'method': method, 'status': 'running'}
            try:
                require(uid in plan_by_uid and method in runner.METHODS, 'Out-of-scope active arm')
                evidence.update(snapshot_arm(source, snapshot))
                for cache_path, cache_sha in evidence['source_cache_hashes'].items():
                    receipt['source_cache_sha256'][str(Path(cache_path).relative_to(ROOT))] = cache_sha
                before = (snapshot/'ledger.jsonl').read_bytes()
                first = await replay_once(snapshot, evidence, plan_by_uid[uid], method,
                                          refs[('qwen25', uid)], cfg, tokenizer, hashes,
                                          cost, graphs, budget, methods, support)
                after_first = (snapshot/'ledger.jsonl').read_bytes()
                require(after_first.startswith(before), 'Replay rewrote its snapshot ledger')
                added = [json.loads(line) for line in after_first[len(before):].splitlines()]
                require(all(event.get('event') == 'parse' for event in added),
                        'Replay added a non-parse ledger event')
                for call_id, old_outcomes in evidence['source_parse_events'].items():
                    new_outcomes = first['parse_outcomes'][call_id]
                    require(all(outcome in new_outcomes for outcome in old_outcomes)
                            and len(set(new_outcomes)) == 1,
                            'Cached JSON produced a different parse outcome')
                second = await replay_once(snapshot, evidence, plan_by_uid[uid], method,
                                           refs[('qwen25', uid)], cfg, tokenizer, hashes,
                                           cost, graphs, budget, methods, support)
                require((snapshot/'ledger.jsonl').read_bytes() == after_first,
                        'Second replay was not parse-idempotent')
                require(first == second, 'Two cached replays disagree')
                evidence.update(status='passed', first_replay=first, second_replay=second,
                                parse_events_completed_from_snapshot_race=added,
                                parse_idempotent=True, snapshot_final_ledger_sha256=sha_bytes(after_first))
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                evidence.update(status='failed', error_type=type(exc).__name__, error=str(exc),
                                traceback=traceback.format_exc()[-12000:])
                receipt['errors'].append({'case_uid': uid, 'method': method,
                                          'error_type': type(exc).__name__, 'error': str(exc)})
            evidence_path = snapshot/'evidence.json'
            save(evidence_path, evidence)
            row = {key: evidence.get(key) for key in ('case_uid', 'method', 'status',
                   'source_ledger_sha256', 'source_complete_sha256', 'source_ledger_bytes',
                   'source_complete_bytes', 'ignored_partial_bytes', 'prefix_calls', 'omitted_reservations')}
            row.update(evidence_path=str(evidence_path), evidence_sha256=sha(evidence_path),
                       omitted_reservations_count=len(evidence.get('omitted_reservations', [])),
                       source_cache_sha256={str(Path(p).relative_to(ROOT)): h for p, h in
                                            evidence.get('source_cache_hashes', {}).items()},
                       next_request_matches_source_reserved=evidence.get('first_replay', {}).get(
                           'next_request_matches_source_reserved'))
            receipt['active_arm_identities'].append(row)
            save(args.output, receipt)
            print(json.dumps({'arm': uid+'/'+method, 'status': evidence['status'],
                              'prefix_calls': evidence.get('prefix_calls'),
                              'error': evidence.get('error')}, ensure_ascii=False), flush=True)
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = old_connect, old_connect_ex, old_getaddrinfo
    # Original ledgers may advance during an initial live audit; their hashes
    # above bind each verified prefix, not a claim that the live files stood still.
    require(all(sha(ROOT/name) == expected for name, expected in source_hashes.items()),
            'Scientific source/configuration changed while replaying')
    receipt.update(status='failed' if receipt['errors'] else 'passed', ended_at=now(),
                   all_active_arms_verified=not receipt['errors'])
    save(args.output, receipt)
    return 0 if receipt['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE/'replay_preflight.json')
    parser.add_argument('--snapshot-dir', type=Path, default=HERE/'replay_snapshots')
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.snapshot_dir = args.snapshot_dir.resolve()
    require(args.output.is_relative_to(HERE) and args.snapshot_dir.is_relative_to(HERE),
            'Replay outputs must stay under the scale48 deployment directory')
    require(not args.output.exists() and not args.snapshot_dir.exists(),
            'Use fresh receipt and snapshot paths; preserve prior audit evidence')
    return asyncio.run(audit(args))


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""One selector-only continuation of GPT-4o slot04 Full-SCC. Default: offline."""
from __future__ import annotations
import argparse
import asyncio
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT.parent
SOURCE = ORIGINAL / 'recovery_v1/results/gpt-4o/04/full-scc'
SUPPORT = ORIGINAL.parent / 'equal_budget_all80_20261009/science_support.py'
MODEL, METHOD, SLOT, CAP = 'gpt-4o', 'full-scc', 4, 99876
UID = 'scid-v1-91d0e015759b48338c9e97e3cf11a43bf743074d83664fcd277d9908f7b48e60'
REQUEST_KEY = 'selector-only-recovery-v2'
sys.path.insert(0, str(ORIGINAL.parents[3]))


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.tmp')
    with temporary.open('w') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def ledger_records(path):
    records, owners = {}, []
    raw = Path(path).read_bytes()
    if not raw.endswith(b'\n'):
        raise RuntimeError('Truncated source ledger')
    for line in raw.splitlines():
        event = json.loads(line)
        if event['event'] == 'owner':
            owners.append(event)
        elif event['event'] == 'reserve':
            if event['call_id'] in records:
                raise RuntimeError('Duplicate source request')
            records[event['call_id']] = {**event, 'status': 'reserved'}
        elif event['event'] == 'finish':
            if records[event['call_id']]['status'] != 'reserved':
                raise RuntimeError('Duplicate source settlement')
            records[event['call_id']].update(event)
    return records, owners


class NoNetwork:
    """Construction permits token/fingerprint checks without loading credentials."""
    async def close(self):
        pass


def load_science():
    support = module('selector_recovery_science', SUPPORT)
    launcher, cost, manifest, graphs, _ = support.load_science()
    api = module('budget_client', ORIGINAL / 'api_budget_client.py')
    methods = module('selector_recovery_methods', ORIGINAL / 'methods_full.py')
    return support, cost, manifest, graphs, api, methods


def prepare():
    support, cost, manifest, graphs, api, methods = load_science()
    original_final = read(SOURCE / 'final.json')
    identity = {'model': MODEL, 'method': METHOD, 'case_slot': SLOT,
                'case_uid': UID, 'B': CAP, 'status': 'infrastructure_failure'}
    if any(original_final.get(k) != v for k, v in identity.items()):
        raise RuntimeError('Unexpected source final')
    records, owners = ledger_records(SOURCE / 'ledger.jsonl')
    if len(records) != 13 or len(owners) != 1 or owners[0]['owner'] != [UID, MODEL, METHOD]:
        raise RuntimeError('Unexpected original request set')
    unknown = [r for r in records.values() if r['status'] != 'completed_with_usage']
    if (len(unknown) != 2 or any(r['status'] != 'unknown_failure' for r in unknown)
            or sorted(r.get('error_type', '') for r in unknown) != ['APIConnectionError', 'InternalServerError']
            or sum(r.get('http_status') == 503 for r in unknown) != 1):
        raise RuntimeError('Source unknown outcomes changed')
    if any(r.get('budget_overrun') or r.get('usage_issues') for r in records.values()):
        raise RuntimeError('Invalid source accounting')
    if any(tuple(r['owner']) != (UID, MODEL, METHOD) for r in records.values()):
        raise RuntimeError('Mixed source owners')
    known = sum(r['actual_total_tokens'] for r in records.values() if r['status'] == 'completed_with_usage')
    held = sum(r['reserved_tokens'] for r in unknown)
    if (known, held) != (49275, 30934) or owners[0]['token_cap'] != CAP:
        raise RuntimeError('Source budget changed')
    plans = read(ORIGINAL / 'case_plans.json')[MODEL]
    matches = [c for c in plans if c['case_uid'] == UID and c['case_slot'] == SLOT]
    if len(matches) != 1:
        raise RuntimeError('Ambiguous case identity')
    case = matches[0]
    graph, scc, _, _ = cost.prepare_injected_case(case, graphs)
    source_view, aliases = methods.source_view(graph, scc)
    candidates = [read(p) for p in sorted(SOURCE.glob('candidate_*.json'))]
    if [c['candidate_index'] for c in candidates] != list(range(1, 12)):
        raise RuntimeError('Candidate pool changed')
    for candidate in candidates:
        if candidate['status'] != 'complete' or not methods.valid(candidate['result'], scc, METHOD):
            raise RuntimeError('Incomplete candidate in frozen pool')
        if candidate['judge_view'] != methods.judge_view(candidate['result'], METHOD, aliases):
            raise RuntimeError('Saved candidate projection differs from original selector')
    presentation, mapping = methods.presentation(candidates)
    prompt = methods.judge_prompt(source_view, presentation)
    # No ledger initialization, SDK creation, .env read, or model call in prepare.
    dummy = api.BudgetClient({'model': MODEL, 'max_model_len': 131072},
                            ledger=api.GlobalLedger(ROOT/'unused_offline_ledger.jsonl'),
                            case_id=UID, method=METHOD, token_cap=CAP,
                            provider_client=NoNetwork())
    dummy.set_phase('selector')
    estimate = dummy.estimate_request(prompt, max_tokens=256, response_format={'type': 'json_object'},
                                      respect_budget=False)
    if dummy.fingerprint != owners[0]['fingerprint']:
        raise RuntimeError('Client configuration differs from historical owner')
    if estimate['input_tokens'] + 256 > CAP-known-held or estimate['max_output_tokens'] != 256:
        raise RuntimeError('Selector does not fit remaining budget')
    body = {'model': MODEL, 'messages': estimate['messages'], 'temperature': 0,
            'max_tokens': 256, 'response_format': {'type': 'json_object'}}
    request_hash = api._hash({'body': body, 'phase': 'selector', 'fingerprint': dummy.fingerprint,
                             'requested_max_tokens': 256, 'selector_reserve': 0, 'token_cap': CAP})
    source_files = {str(p.relative_to(SOURCE)): sha(p) for p in sorted(SOURCE.rglob('*'))
                    if p.is_file() and not p.name.endswith('.lock')}
    code_files = [Path(__file__), ORIGINAL/'api_budget_client.py', ORIGINAL/'methods_full.py',
                  ORIGINAL/'protocol.json', ORIGINAL/'case_plans.json', ORIGINAL/'budgets.json',
                  ORIGINAL/'recovery_v1/protocol_amendment.json', SUPPORT, api.REUSED_CLIENT_PATH]
    protocol = {'schema_version': 'api10_selector_only_recovery.v1', **identity,
                'status': 'frozen', 'source_directory': str(SOURCE),
                'old_request_count': 13, 'old_successful_requests': 11,
                'old_call_ids': list(records), 'allowed_held_call_ids': [r['call_id'] for r in unknown],
                'known_tokens_before': known, 'held_tokens_before': held,
                'accounted_tokens_before': known+held, 'remaining_tokens_before': CAP-known-held,
                'candidate_indices': list(range(1, 12)), 'selector_seed': methods.SEED,
                'new_request_key': REQUEST_KEY+':attempt-0', 'new_request_hash': request_hash,
                'selector_input_reservation': estimate['input_tokens'], 'selector_output_limit': 256,
                'selector_total_reservation': estimate['input_tokens']+256,
                'temperature': 0, 'json_attempts': 1, 'sdk_retries': 0, 'transport_retries': 0,
                'policy': 'Stop candidate sampling after the unknown candidate outcome. Select once from every '
                          'complete pre-existing candidate using the unchanged label-blind selector. Retain all '
                          'old reservations, including both unknown outcomes. Never retry unknown requests, '
                          'generate candidates, edit a candidate, or fall back after selector failure.',
                'source_files_sha256': source_files,
                'source_code_sha256': {str(p): sha(p) for p in code_files},
                'science_source_sha256': manifest['unchanged_code_sha256'],
                'judge_prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                'candidate_mapping': {k: v['candidate_index'] for k, v in mapping.items()}}
    frozen_path = ROOT/'protocol.json'
    if frozen_path.exists() and read(frozen_path) != protocol:
        raise RuntimeError('Frozen selector-only protocol changed')
    snapshot = ROOT/'source_snapshot'
    snapshot.mkdir(parents=True, exist_ok=True)
    for name, expected in source_files.items():
        target = snapshot/name
        if target.exists():
            if sha(target) != expected:
                raise RuntimeError('Source snapshot hash mismatch: '+name)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE/name, target)
            if sha(target) != expected:
                raise RuntimeError('Source changed during copy: '+name)
    (ROOT/'judge_prompt.txt').write_text(prompt)
    save(ROOT/'candidate_mapping.json', protocol['candidate_mapping'])
    save(ROOT/'candidate_presentation.json', presentation)
    save(frozen_path, protocol)
    save(ROOT/'preflight.json', {'status': 'passed', 'model_calls': 0,
         'case_uid': UID, 'complete_candidates': 11, 'protocol_sha256': sha(frozen_path),
         'accounted_tokens_before': known+held, 'held_tokens_preserved': held,
         'remaining_tokens_before': CAP-known-held,
         'selector_total_reservation': estimate['input_tokens']+256})
    return protocol, support, api, methods, case, candidates, mapping, prompt


def ledger_class(api, protocol):
    class SelectorOnlyLedger(api.GlobalLedger):
        async def reserve(self, **kwargs):
            await self.initialize()
            async with self._lock:
                owner = tuple(kwargs['owner'])
                if (owner != (UID, MODEL, METHOD) or kwargs['token_cap'] != CAP
                        or kwargs['phase'] != 'selector' or kwargs['request_key'] != protocol['new_request_key']
                        or kwargs['request_hash'] != protocol['new_request_hash'] or kwargs['retry_index'] != 0
                        or kwargs['input_tokens'] != protocol['selector_input_reservation']
                        or kwargs['max_output'] != 256 or kwargs['requested_max_output'] != 256
                        or kwargs['selector_reserve'] != 0):
                    raise api.LedgerError('Only the frozen selector request is authorized')
                if set(self._calls) != set(protocol['old_call_ids']):
                    raise api.LedgerError('Selector already reserved or unexpected request exists; no retry')
                expected_owner = self._owners.get(owner, {})
                if expected_owner.get('fingerprint') != kwargs['fingerprint'] or expected_owner.get('token_cap') != CAP:
                    raise api.LedgerError('Owner identity changed')
                rows = self.owner_records(*owner)
                held = {r['call_id'] for r in rows if r['status'] != 'completed_with_usage'}
                if held != set(protocol['allowed_held_call_ids']):
                    raise api.LedgerError('Unapproved unknown request')
                if any(r.get('budget_overrun') or r.get('usage_issues') for r in rows):
                    raise api.LedgerError('Invalid prior accounting')
                used = sum(self.accounted_tokens(r) for r in rows)
                reserve = kwargs['input_tokens'] + kwargs['max_output']
                if used != protocol['accounted_tokens_before'] or used+reserve > CAP:
                    raise api.BudgetStop('tokens', accounted_tokens=used, request_tokens=reserve, token_cap=CAP)
                row = {'event': 'reserve', 'call_id': uuid.uuid4().hex, 'owner': list(owner),
                       'request_key': kwargs['request_key'], 'request_hash': kwargs['request_hash'],
                       'phase': 'selector', 'input_tokens': kwargs['input_tokens'],
                       'max_output_tokens': 256, 'requested_max_output_tokens': 256,
                       'reserved_tokens': reserve, 'selector_reserve': 0, 'retry_index': 0,
                       'cache_file': kwargs['cache_file']}
                self._append(row)
                self._calls[row['call_id']] = {**row, 'status': 'reserved'}
                self._keys[(*owner, kwargs['request_key'])] = row['call_id']
                return dict(self._calls[row['call_id']]), False
    return SelectorOnlyLedger


async def execute(loaded):
    protocol, support, api, methods, case, candidates, mapping, prompt = loaded
    out = ROOT/'result'
    out.mkdir(exist_ok=True)
    final_path = out/'final.json'
    if final_path.exists():
        final = read(final_path)
        if final.get('protocol_sha256') != sha(ROOT/'protocol.json'):
            raise RuntimeError('Existing final protocol differs')
        print(json.dumps({'status': 'already_finalized', 'final': str(final_path)})); return
    intent = ROOT/'launch_intent.json'
    if intent.exists():
        raise RuntimeError('A selector launch was already intended; no automatic retry after an unknown outcome')
    destination = out/'ledger.jsonl'
    if destination.exists():
        if destination.read_bytes() != (ROOT/'source_snapshot/ledger.jsonl').read_bytes():
            raise RuntimeError('Existing working ledger changed; no automatic retry')
    else:
        shutil.copy2(ROOT/'source_snapshot/ledger.jsonl', destination)
    shutil.copytree(ROOT/'source_snapshot/calls', out/'calls', dirs_exist_ok=True)
    Ledger = ledger_class(api, protocol)
    ledger = Ledger(destination)
    await ledger.initialize()
    client = None
    record = {'model': MODEL, 'method': METHOD, 'case_uid': UID, 'case_slot': SLOT,
              'domain': case['domain'], 'B': CAP, 'protocol_sha256': sha(ROOT/'protocol.json'),
              'started_at': now(), 'recovery': 'selector_only_after_infrastructure_failure',
              'source_final_sha256': protocol['source_files_sha256']['final.json'],
              'source_ledger_sha256': protocol['source_files_sha256']['ledger.jsonl'],
              'candidate_indices': protocol['candidate_indices'], 'selected_result': None,
              'selection': {'status': 'selector_failed', 'complete_candidates': 11,
                            'selected_candidate_index': None},
              'metrics': support.metrics(None, METHOD, case, False)}
    try:
        client = api.BudgetClient({'model': MODEL, 'max_model_len': 131072}, ledger=ledger,
                                 case_id=UID, method=METHOD, token_cap=CAP, call_log_dir=out/'calls')
        client.set_phase('selector'); client.set_selector_reserve(0)
        for row in ledger.owner_records(UID, MODEL, METHOD):
            client._consume(row, False)
        if client.remaining_tokens != protocol['remaining_tokens_before']:
            raise RuntimeError('Client did not retain complete prior usage')
        with intent.open('x') as handle:
            json.dump({'created_at': now(), 'pid': os.getpid(), 'protocol_sha256': sha(ROOT/'protocol.json'),
                       'physical_requests_allowed': 1, 'request_key': protocol['new_request_key']}, handle)
            handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
        answer = await client.call_json(prompt, temperature=0, max_tokens=256, request_key=REQUEST_KEY)
        save(out/'judge_response.json', answer)
        if isinstance(answer, dict) and set(answer) == {'candidate_id'} and answer['candidate_id'] in mapping:
            selected = mapping[answer['candidate_id']]
            record['selected_result'] = selected['result']
            record['selection'].update(status='judged', selected_candidate_index=selected['candidate_index'])
            record['metrics'] = support.metrics(selected['result'], METHOD, case)
            record['status'] = 'complete' if record['metrics']['valid'] else 'scientific_failure'
        else:
            record['status'] = 'scientific_failure'
    except BaseException as exc:
        record.update(status='selector_failure', error_type=type(exc).__name__, error=str(exc)[:400])
        if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
            record['status'] = 'interrupted'
    finally:
        record['ended_at'] = now()
        record['usage'] = ledger.owner_summary(UID, MODEL, METHOD)
        old_ids = set(protocol['old_call_ids'])
        new_rows = [r for r in ledger.owner_records(UID, MODEL, METHOD) if r['call_id'] not in old_ids]
        record['new_selector_usage'] = ledger._summary(new_rows)
        record['unknown_source_reservations_preserved'] = all(
            ledger._calls[c]['reserved_tokens'] == 15467 and ledger._calls[c]['status'] == 'unknown_failure'
            for c in protocol['allowed_held_call_ids'])
        save(final_path, record)
        if client is not None:
            await client.close()
        await ledger.close()
    print(json.dumps({'status': record['status'], 'metrics': record['metrics'],
                      'new_selector_usage': record['new_selector_usage'], 'final': str(final_path)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true', help='Offline snapshot and preflight (default)')
    parser.add_argument('--run', action='store_true', help='Send exactly one new selector request')
    args = parser.parse_args()
    if args.prepare and args.run:
        parser.error('Choose --prepare or --run')
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT/'runner.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.run:
            from dotenv import load_dotenv
            load_dotenv(ORIGINAL.parents[3]/'.env')
        loaded = prepare()
        if args.run:
            asyncio.run(execute(loaded))
        else:
            print(json.dumps(read(ROOT/'preflight.json'), ensure_ascii=False))


if __name__ == '__main__':
    main()

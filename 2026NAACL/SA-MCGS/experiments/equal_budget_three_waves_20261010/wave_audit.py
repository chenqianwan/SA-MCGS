"""Read-only completion audit for one model in a 480-arm experiment wave.

Uses only the standard library. It neither imports the inference client nor
locks, settles, rewrites or recovers its ledger. Missing finals are pending.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

MODELS = ('llama', 'kimi', 'qwen35')
METHODS = ('lea', 'full-scc')
TERMINAL = ('complete', 'strict_experiment_failure')
HEADER = {'event': 'header', 'version': 1, 'accounting': 'actual_local_vllm_tokens',
          'external_api_enabled': False, 'unknown_outcome': 'retain_full_reservation'}


class AuditError(ValueError):
    pass


def digest(value):
    """Exactly the canonical JSON encoding used by runner/science_support."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), default=str).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, reason):
    if not condition:
        raise AuditError(reason)


def integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, f'invalid_integer:{name}')
    return value


def hash_string(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def read(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(value, dict), 'expected_json_object')
    return value


def local_file(path, root):
    require(path.is_file(), f'missing_file:{path.name}')
    require(path.resolve().is_relative_to(root), 'file_outside_wave')
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current/part
        require(not current.is_symlink(), 'symlinked_runtime_file')


def ledger_summary(path, owner, budget):
    """Strictly reduce reserve/finish/parse events without recovering anything."""
    require(path.stat().st_nlink == 1, 'shared_or_hardlinked_ledger')
    data = path.read_bytes()
    require(bool(data) and data.endswith(b'\n'), 'empty_or_truncated_ledger')
    events = [json.loads(line) for line in data.splitlines()]
    require(all(isinstance(e, dict) for e in events), 'invalid_ledger_event')
    require(all(events[0].get(k) == v for k, v in HEADER.items()), 'ledger_header_mismatch')
    calls, keys, cache_paths = {}, set(), set()
    owner_seen = False
    spent = 0
    for event in events[1:]:
        kind = event.get('event')
        if kind == 'owner':
            require(not owner_seen, 'duplicate_ledger_owner')
            require(event.get('owner') == list(owner), 'ledger_owner_mismatch')
            require(type(event.get('token_cap')) is int and event['token_cap'] == budget, 'ledger_budget_mismatch')
            require(hash_string(event.get('fingerprint')), 'invalid_owner_fingerprint')
            owner_seen = True
        elif kind == 'reserve':
            require(owner_seen and event.get('owner') == list(owner), 'reservation_owner_mismatch')
            call_id, key = event.get('call_id'), event.get('request_key')
            require(isinstance(call_id, str) and bool(call_id) and call_id not in calls, 'duplicate_or_invalid_call_id')
            require(isinstance(key, str) and bool(key) and key not in keys, 'duplicate_or_invalid_request_key')
            require(all(r.get('finish') is not None for r in calls.values()), 'overlapping_or_unresolved_reservation')
            require(hash_string(event.get('request_hash')), 'invalid_request_hash')
            inputs = integer(event.get('input_tokens'), 'input_tokens')
            output = integer(event.get('max_output_tokens'), 'max_output_tokens', 1)
            requested = integer(event.get('requested_max_output_tokens'), 'requested_max_output_tokens', 1)
            reserved = integer(event.get('reserved_tokens'), 'reserved_tokens', 1)
            selector = integer(event.get('selector_reserve'), 'selector_reserve')
            integer(event.get('retry_index'), 'retry_index')
            require(event.get('phase') in ('candidate', 'selector'), 'non_baseline_phase')
            require(event['phase'] != 'selector' or selector == 0, 'selector_reservation_double_counted')
            require(reserved == inputs+output and output <= requested, 'reservation_token_mismatch')
            require(spent+reserved+selector <= budget, 'reservation_exceeds_budget')
            raw_cache = event.get('cache_file')
            require(isinstance(raw_cache, str) and bool(raw_cache), 'invalid_cache_path')
            cache_root = path.parent/'calls'
            require(not cache_root.is_symlink() and cache_root.resolve() == path.parent.resolve()/'calls',
                    'shared_or_outside_arm_cache')
            cache = Path(raw_cache)
            cache = (cache if cache.is_absolute() else path.parent/cache).resolve()
            require(cache.is_relative_to(cache_root.resolve()) and cache not in cache_paths,
                    'shared_or_outside_arm_cache')
            cache_paths.add(cache)
            calls[call_id] = {'reserve': event, 'finish': None, 'parse': set()}
            keys.add(key)
        elif kind == 'finish':
            call_id = event.get('call_id')
            require(call_id in calls and calls[call_id]['finish'] is None, 'unknown_or_duplicate_settlement')
            require(event.get('status') == 'completed_with_usage', 'unknown_or_held_provider_usage')
            require(event.get('usage_issues') == [] and not event.get('error_type'), 'provider_usage_mismatch_or_error')
            usage = event.get('usage')
            require(isinstance(usage, dict), 'missing_provider_usage')
            prompt = integer(usage.get('prompt_tokens'), 'provider_prompt_tokens')
            output = integer(usage.get('completion_tokens'), 'provider_completion_tokens')
            total = integer(usage.get('total_tokens', prompt+output), 'provider_total_tokens')
            require(total == prompt+output, 'provider_total_mismatch')
            reserve = calls[call_id]['reserve']
            require(prompt == reserve['input_tokens'] and output <= reserve['max_output_tokens'], 'provider_reservation_mismatch')
            require(event.get('prompt_tokens') == prompt and event.get('completion_tokens') == output
                    and event.get('actual_total_tokens') == total, 'settlement_usage_mismatch')
            elapsed = event.get('elapsed_seconds')
            require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, 'invalid_provider_elapsed')
            require(hash_string(event.get('response_sha256')), 'invalid_response_hash')
            calls[call_id]['finish'] = event
            spent += total
        elif kind == 'parse':
            call_id, outcome = event.get('call_id'), event.get('outcome')
            require(call_id in calls and calls[call_id]['finish'] is not None, 'parse_without_settlement')
            require(outcome in ('dict', 'invalid_json', 'schema_not_object'), 'invalid_parse_outcome')
            require(outcome not in calls[call_id]['parse'], 'duplicate_parse_event')
            calls[call_id]['parse'].add(outcome)
        else:
            raise AuditError('unexpected_ledger_event')
    require(all(r['finish'] is not None for r in calls.values()), 'unresolved_reservation')
    require(spent <= budget, 'actual_usage_exceeds_budget')
    rows = list(calls.values())
    return {
        'calls': len(rows), 'completed_with_usage': len(rows), 'held_calls': 0,
        'pending_calls': 0, 'unknown_failure_calls': 0, 'missing_usage_calls': 0,
        'retry_calls': sum(r['reserve']['retry_index'] > 0 for r in rows),
        'prompt_tokens': sum(r['finish']['prompt_tokens'] for r in rows),
        'completion_tokens': sum(r['finish']['completion_tokens'] for r in rows),
        'total_tokens': spent, 'held_tokens': 0, 'accounted_tokens': spent,
        'provider_seconds': sum(r['finish']['elapsed_seconds'] for r in rows),
        'usage_mismatch_calls': 0,
        'parse_failure_calls': sum(bool(r['parse']-{'dict'}) for r in rows),
        'external_api_calls': 0,
    }


def audit_model(wave_root: Path, model: str) -> dict:
    """Return completion, missing keys and audit errors; never mutate the wave."""
    root = Path(wave_root).absolute()
    result = {'complete': False, 'model': model, 'wave_root': str(root), 'expected_count': 160,
              'final_count': 0, 'terminal_count': 0, 'strict_failures': 0,
              'verified_count': 0, 'actual_tokens': 0, 'missing': [], 'errors': []}

    def error(path, exc):
        result['errors'].append({'path': str(path), 'error_type': type(exc).__name__, 'reason': str(exc)})

    try:
        require(model in MODELS, 'unknown_model')
        require(not root.is_symlink(), 'symlinked_wave_root')
        root = root.resolve()
        scope = read(root/'run_scope.json')
        uids = scope.get('case_uids')
        require(scope.get('cases_per_model') == 80 and isinstance(uids, list)
                and len(uids) == 80 and all(isinstance(u, str) and u and Path(u).name == u for u in uids)
                and len(set(uids)) == 80, 'expected_exactly_80_unique_cases')
        require(scope.get('expected_results') == 480 and scope.get('execution_methods') == list(METHODS), 'scope_methods_or_count_mismatch')
        expected = {(uid, method) for uid in uids for method in METHODS}
        paths = sorted((root/'results'/model).rglob('final.json'))
        result['final_count'] = len(paths)
        result['missing'] = [{'case_uid': uid, 'method': method} for uid, method in sorted(expected)
                             if not (root/'results'/model/uid/method/'final.json').is_file()]
        if not paths:
            return result
        protocol = read(root/'protocol.json')
        require(protocol.get('run_scope') == scope and protocol.get('run_scope_sha256') == sha(root/'run_scope.json'), 'protocol_scope_mismatch')
        planpath = root/'science/repo/portable_data/qwen80_case_plan.json'
        require(protocol.get('case_plan_sha256') == sha(planpath), 'case_plan_hash_mismatch')
        plan_rows = json.loads(planpath.read_text(encoding='utf-8'))
        require(isinstance(plan_rows, list) and len(plan_rows) == 80, 'case_plan_count_mismatch')
        plan = {r['case_uid']: r for r in plan_rows}
        require(len(plan) == 80 and set(plan) == set(uids), 'case_plan_key_set_mismatch')
        refpath = root/'historical_sa_reference.json'
        require(protocol.get('historical_sa_reference_sha256') == sha(refpath), 'historical_reference_hash_mismatch')
        phash = digest(protocol)
        alias = protocol['models_configuration'][model]['alias']
        require(isinstance(alias, str) and bool(alias), 'missing_served_model_alias')
        refs = {}
        for row in read(refpath)['rows']:
            key = (row['model_key'], row['case_uid'])
            require(key not in refs, 'duplicate_historical_reference')
            require(row.get('method') == 'sa-mcgs' and row.get('completion_status') in TERMINAL,
                    'invalid_historical_reference')
            integer(row['usage']['total_tokens'], 'historical_budget', 1)
            require(hash_string(row.get('source_sha256')), 'invalid_historical_source_hash')
            refs[key] = row
        require(set(refs) == {(m, uid) for m in MODELS for uid in uids}, 'historical_reference_key_set_mismatch')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        error(root, exc)
        return result

    seen = set()
    for path in paths:
        try:
            local_file(path, root)
            relative = path.relative_to(root/'results'/model)
            require(len(relative.parts) == 3, 'unexpected_result_path')
            uid, method, _ = relative.parts
            require((uid, method) in expected and (uid, method) not in seen, 'extra_or_duplicate_arm')
            seen.add((uid, method))
            row = read(path)
            require(row.get('completion_status') in TERMINAL, 'nonterminal_or_infrastructure_failure')
            result['terminal_count'] += 1
            result['strict_failures'] += int(row['completion_status'] == 'strict_experiment_failure')
            reference = refs[(model, uid)]
            budget = reference['usage']['total_tokens']
            identity = {'model_key': model, 'model': alias, 'case_uid': uid, 'method': method,
                        # Historical per-model display IDs differ from the
                        # unified Qwen-derived execution plan; UID is stable.
                        'case_id': plan[uid]['case_id'], 'domain': reference['domain'],
                        'main_case_order': reference['main_case_order'], 'source_n': reference['source_n'],
                        'protocol_sha256': phash, 'historical_sa_source_sha256': reference['source_sha256'],
                        'historical_sa_completion_status': reference['completion_status']}
            mismatches = [k for k, v in identity.items() if row.get(k) != v]
            require(not mismatches, 'final_identity_or_protocol_mismatch:'+','.join(mismatches))
            require(integer(row.get('token_budget'), 'final_budget', 1) == budget, 'final_historical_budget_mismatch')
            input_path = path.parent/'input_identity.json'
            local_file(input_path, root)
            inputs = read(input_path)
            require(hash_string(row.get('visible_input_sha256')), 'invalid_visible_input_hash')
            input_identity = {'case_uid': uid, 'method': method, 'protocol_sha256': phash,
                              'token_budget': budget, 'historical_sa_source_sha256': reference['source_sha256'],
                              'visible_input_sha256': row['visible_input_sha256']}
            require(all(inputs.get(k) == v for k, v in input_identity.items()), 'frozen_input_identity_mismatch')
            ledger_path = path.parent/'ledger.jsonl'
            local_file(ledger_path, root)
            summary = ledger_summary(ledger_path, (uid, alias, method), budget)
            usage = row.get('usage')
            require(isinstance(usage, dict), 'missing_final_usage')
            for key, expected_value in summary.items():
                actual = usage.get(key)
                if key == 'provider_seconds':
                    require(type(actual) in (int, float) and math.isfinite(actual)
                            and math.isclose(actual, expected_value, rel_tol=1e-9, abs_tol=1e-6),
                            'final_ledger_counter_mismatch:'+key)
                else:
                    require(type(actual) is int and actual == expected_value, 'final_ledger_counter_mismatch:'+key)
            # This is a process-recovery diagnostic, not an outstanding charge:
            # a successfully settled response-cache recovery can leave it > 0.
            integer(usage.get('recovered_unresolved_calls', 0), 'recovered_unresolved_calls')
            require(summary['accounted_tokens'] <= budget, 'final_usage_exceeds_budget')
            result['verified_count'] += 1
            result['actual_tokens'] += summary['total_tokens']
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            error(path, exc)
    result['complete'] = (not result['errors'] and not result['missing']
                          and seen == expected and result['verified_count'] == 160)
    return result

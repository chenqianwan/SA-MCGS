#!/usr/bin/env python3
"""Freeze authorized Qwen budgets from same-case historical LEA usage, offline.

B_i = ceil(SA_llm_calls_i * LEA_total_tokens_i / LEA_llm_calls_i).
SA outputs and metrics remain fixed. No inference is performed. Observed LEA
usage includes every recorded JSON attempt; its denominator is algorithm calls.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'historical_sa_raw_reference.json'
PLAN = ROOT / 'science/repo/portable_data/qwen80_case_plan.json'
FORMULA = 'ceil(SA_llm_calls_i * LEA_total_tokens_i / LEA_llm_calls_i)'
AUTHORIZATION = {
    'date': '2026-10-12',
    'user_instruction': '估算，但是不用明确标识作为区分',
    'interpretation': 'User authorized estimated budgets with the existing model name and table format. Scientific protocol and source records retain the calibrated provenance.',
    'scope': 'Qwen2.5-72B, original 80 cases, one run of LEA and Full-SCC; reuse SA and do not run SA.',
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def freeze(path, value):
    if path.exists():
        require(read(path) == value, f'Frozen artifact differs: {path}')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def capture_sources(raw):
    """Capture original bytes once; subsequent/remote runs verify the snapshot."""
    manifest_path = ROOT / 'sources/manifest.json'
    if not manifest_path.exists():
        original_csv = Path(raw['historical_lea_cost_information_only']['source_file'])
        require(sha(original_csv) == raw['historical_lea_cost_information_only']['source_sha256'],
                'Original LEA CSV changed after identity preparation')
        base = original_csv.parent
        paths = [(original_csv, 'sources/lea_summary_method_cases.csv'),
                 (base / 'call_logs/llm_calls.jsonl', 'sources/lea_llm_calls.jsonl')]
        paths += [(base / 'results' / f"{row['case_id']}__lea.json",
                   f"sources/lea_results/{row['case_id']}__lea.json") for row in raw['rows']]
        science = base.parents[1] / 'repo/emnlp2026_discussion'
        paths += [(science / name, 'sources/science/' + name)
                  for name in ('run_cost_audit_clean.py', 'run_lea_full_baseline.py')]
        entries = []
        for original, relative in paths:
            content = original.read_bytes()
            expected = hashlib.sha256(content).hexdigest()
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                require(sha(target) == expected, f'Existing source differs: {relative}')
            else:
                with target.open('xb') as stream:
                    stream.write(content)
            entries.append({'source_file': str(original), 'snapshot_file': relative,
                            'source_sha256': expected, 'bytes': len(content)})
        freeze(manifest_path, {'version': 1, 'purpose': 'Original LEA evidence for offline budget audit',
                               'entries': entries})
    manifest = read(manifest_path)
    for entry in manifest['entries']:
        require(sha(ROOT / entry['snapshot_file']) == entry['source_sha256'],
                f"Source snapshot SHA mismatch: {entry['snapshot_file']}")
    return {entry['snapshot_file']: entry for entry in manifest['entries']}


def verified_lea_rows(raw, plan, manifest):
    with (ROOT / 'sources/lea_summary_method_cases.csv').open(newline='', encoding='utf-8') as stream:
        csv_rows = list(csv.DictReader(stream))
    by_case = {row['case_id']: row for row in csv_rows}
    require(len(csv_rows) == len(by_case) == 80, 'Expected 80 unique cost rows')
    require(set(by_case) == {row['case_id'] for row in raw['rows']}, 'LEA and SA case ID sets differ')
    logs = defaultdict(list)
    with (ROOT / 'sources/lea_llm_calls.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            require(row['model'] == 'qwen2.5-72b' and row['method'] == 'lea', 'Unexpected API log model/method')
            require(row.get('ok') is True and row.get('charge_is_uncertain') is False,
                    'Historical API usage contains failed/uncertain attempts')
            logs[row['case_id']].append(row)
    require(set(logs) == set(by_case), 'Call logs do not cover exactly the 80 cases')
    plans = {case['case_uid']: case for case in plan}
    verified = {}
    for sa in raw['rows']:
        uid, case_id = sa['case_uid'], sa['case_id']
        case, csv_row = plans[uid], by_case[case_id]
        relative = f'sources/lea_results/{case_id}__lea.json'
        result = read(ROOT / relative)
        require(result['model'] == sa['model'] == csv_row['model'] == 'qwen2.5-72b'
                and result['method'] == 'lea' and result['case_uid'] == uid
                and result['case_id'] == case_id, f'Model/case UID: {uid}')
        require(result['domain'] == sa['domain'] == case['domain'] == csv_row['domain']
                and result['scc_size'] == sa['source_n'] == int(csv_row['scc_size']), f'Domain/size: {uid}')
        require(result['source_result_sha256'].removeprefix('sha256:') == sa['source_sha256']
                and result['source_sa_record_sha256'].removeprefix('sha256:')
                    == sa['source_sa_record_sha256']
                and result['source_result_repo_relpath'] == sa['source_repo_relpath'],
                f'LEA and SA original source differ: {uid}')
        require(result['actual_case_identity'] == result['planned_case_identity']
                == case['planned_case_identity'], f'Exact frozen graph/case identity: {uid}')
        require(result['actual_scc_clause_ids'] == result['planned_scc_clause_ids']
                == result['scc_clause_ids'] == sa['planned_scc_clause_ids'], f'Ordered clause IDs: {uid}')
        require(result['actual_injection_identity'] == result['planned_injection_identity']
                == sa['planned_injection_identity'], f'Injection identity: {uid}')
        require(result['completion_status'] == 'complete' and not result.get('cost_audit_error'),
                f'Historical LEA not complete: {uid}')
        calls = result['llm_calls']
        require(type(calls) is int and calls > 0 and calls == int(csv_row['llm_calls']),
                f'Invalid algorithm call count: {uid}')
        # The frozen source defines this field as the non-TT-window counter.
        unique_windows = {frozenset(item['window']) for item in result['deterministic_windows']}
        # A repeated window may be evaluated again after the TT reuse limit;
        # the recorded non-TT count need not equal the unique-window count.
        require(len(unique_windows) <= calls <= len(result['deterministic_windows'])
                and calls + result['tt_hits'] == len(result['deterministic_windows']),
                f'Algorithm window-call counter mismatch: {uid}')
        usage = result['llm_usage_summary']
        records = logs[case_id]
        require(usage['recorded_api_calls'] == len(records) == int(csv_row['recorded_api_calls'])
                and len(records) >= calls, f'Provider/algorithm call count mismatch: {uid}')
        require(usage['failed_api_calls'] == 0 and usage['successful_api_calls'] == len(records),
                f'Failed historical API attempts: {uid}')
        for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
            total = sum(int(record['usage'][key]) for record in records)
            require(total == usage[key] == int(csv_row[key]), f'Logged {key} differs: {uid}')
        require(usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens'] > 0,
                f'Invalid token sum: {uid}')
        verified[uid] = {
            'model': result['model'], 'case_uid': uid, 'case_id': case_id,
            'domain': result['domain'], 'source_n': result['scc_size'],
            'algorithm_llm_calls': calls, 'recorded_api_calls': len(records),
            'prompt_tokens': usage['prompt_tokens'], 'completion_tokens': usage['completion_tokens'],
            'total_tokens': usage['total_tokens'],
            'result_source_file': manifest[relative]['source_file'],
            'result_snapshot_file': relative, 'result_source_sha256': manifest[relative]['source_sha256'],
            'original_sa_source_sha256': sa['source_sha256'],
            'original_sa_record_sha256': sa['source_sa_record_sha256'],
            'original_sa_case_uid_exact_match': True,
            'csv_and_result_and_all_api_logs_exact_match': True,
        }
    require(len(verified) == 80, 'Expected 80 verified same-case costs')
    return verified


def main():
    raw_sha = sha(RAW)
    raw, plan = read(RAW), read(PLAN)
    require(len(raw['rows']) == len(plan) == 80, 'Expected all 80 cases')
    require([row['case_uid'] for row in raw['rows']] == [case['case_uid'] for case in plan],
            'Original case order differs')
    require(all(row['usage']['total_tokens'] is None for row in raw['rows']),
            'Raw SA token usage must remain unavailable')
    manifest = capture_sources(raw)
    verified = verified_lea_rows(raw, plan, manifest)
    provenance = {
        'kind': 'calibrated', 'formula': FORMULA,
        'rounding': 'Integer ceiling via (numerator + denominator - 1) // denominator.',
        'calibration_source': 'Same-model, same-case historical LEA local-window usage.',
        'denominator': 'Historical LEA algorithm llm_calls (non-TT local windows), not recorded_api_calls.',
        'retry_accounting': 'LEA total_tokens includes all recorded API/JSON attempts; dividing by algorithm calls retains the observed retry overhead in each per-call estimate.',
        'historical_main_actual_token_match': False,
        'historical_sa_token_usage': None,
        'raw_historical_sa_reference': 'historical_sa_raw_reference.json',
        'raw_historical_sa_reference_sha256': raw_sha,
        'authorization': AUTHORIZATION,
    }
    rows, budget_rows = [], []
    for source in raw['rows']:
        lea = verified[source['case_uid']]
        sa_calls = source['llm_calls']
        require(type(sa_calls) is int and sa_calls > 0, 'Invalid historical SA algorithm calls')
        numerator = sa_calls * lea['total_tokens']
        denominator = lea['algorithm_llm_calls']
        cap = (numerator + denominator - 1) // denominator
        require((cap - 1) * denominator < numerator <= cap * denominator,
                'Ceiling arithmetic check failed')
        budget_source = {
            'case_uid': source['case_uid'], 'case_id': source['case_id'],
            'main_case_order': source['main_case_order'], 'model': source['model'],
            'domain': source['domain'], 'source_n': source['source_n'],
            'kind': 'calibrated', 'formula': FORMULA, 'sa_llm_calls': sa_calls,
            'lea': lea, 'numerator': numerator, 'denominator': denominator,
            'token_cap': cap, 'baseline_methods': ['lea', 'full-scc'],
            'each_baseline_has_its_own_identical_cap': True,
            'historical_main_actual_token_match': False,
        }
        budget_rows.append(budget_source)
        row = copy.deepcopy(source)
        row['historical_usage'] = copy.deepcopy(source['usage'])
        row['usage']['total_tokens'] = cap
        row['usage_status'] = 'calibrated_total_token_ceiling_not_observed_sa_usage'
        row['usage_field_semantics'] = 'Runner compatibility: usage.total_tokens stores calibrated cap B_i, not observed SA usage; historical_usage remains null.'
        row['token_budget'] = cap
        row['budget_rule'] = FORMULA
        row['budget_selection_status'] = 'frozen'
        row['budget_provenance'] = {
            'kind': 'calibrated', 'formula': FORMULA, 'sa_llm_calls': sa_calls,
            'lea_llm_calls': denominator, 'lea_recorded_api_calls': lea['recorded_api_calls'],
            'lea_total_tokens': lea['total_tokens'], 'token_cap': cap,
            'lea_source_file': lea['result_snapshot_file'],
            'lea_source_sha256': lea['result_source_sha256'],
            'historical_main_actual_token_match': False,
        }
        require(row['selected_result'] == source['selected_result'] and row['metrics'] == source['metrics'],
                'Historical SA output or metrics changed')
        rows.append(row)
    budget_document = {
        'schema': 'same_case_lea_calibrated_sa_token_budgets_v1',
        'budget_provenance': provenance, 'rows': budget_rows,
        'source_manifest': 'sources/manifest.json',
        'source_manifest_sha256': sha(ROOT / 'sources/manifest.json'),
    }
    reference_document = {
        'schema': 'historical_sa_with_calibrated_budget_v1',
        'budget_provenance': provenance, 'rows': rows,
        'display_model': 'Qwen2.5-72B',
        'provenance': {'historical_outputs_unchanged': True, 'historical_metrics_unchanged': True,
                       'sa_execution_enabled': False, 'model_calls': 0,
                       'budget_source_file': 'budget_sources.json'},
    }
    scope = {
        'version': 1, 'scope_schema': 'historical_sa_baselines_v1',
        'experiment': ROOT.name, 'models': ['qwen25'], 'display_model': 'Qwen2.5-72B',
        'execution_alias': 'qwen2.5-72b-instruct',
        'cases_per_model': 80, 'source_scc_count': 20, 'whole_experiment_runs': 1,
        'expected_results': 160, 'comparison_expected_results': 240,
        'execution_methods': ['lea', 'full-scc'], 'reused_sa_rows': 80,
        'sa_execution_enabled': False, 'stop_after_scope': True,
        'case_uids': [case['case_uid'] for case in plan],
        'selection_rule': 'All 80 original cases in frozen main-case order; no pilot or previous baseline reuse.',
        'budget_rule': FORMULA, 'budget_source': 'budget_sources.json',
        'each_baseline_has_its_own_identical_cap': True,
        'seed': 42, 'provider_request_seed': None,
        'authorization': AUTHORIZATION,
    }
    freeze(ROOT / 'budget_sources.json', budget_document)
    freeze(ROOT / 'historical_sa_reference.json', reference_document)
    freeze(ROOT / 'run_scope.json', scope)
    require(sha(RAW) == raw_sha, 'Raw historical reference changed')
    totals = {key: sum(row['lea'][key] for row in budget_rows)
              for key in ('algorithm_llm_calls', 'recorded_api_calls', 'prompt_tokens',
                          'completion_tokens', 'total_tokens')}
    caps = [row['token_cap'] for row in budget_rows]
    preflight = {
        'schema': 'qwen_same_case_budget_preflight_v1', 'status': 'passed',
        'model_calls': 0, 'sa_execution_enabled': False, 'case_count': 80,
        'expected_baseline_arms': 160, 'comparison_rows': 240,
        'budget_kind': 'calibrated', 'formula': FORMULA,
        'actual_historical_sa_token_usage_available': False,
        'historical_sa_raw_reference_unchanged': True,
        'historical_sa_algorithm_calls': sum(row['sa_llm_calls'] for row in budget_rows),
        'lea_source_totals': totals,
        'token_caps': {'per_baseline_sum': sum(caps), 'both_baselines_sum': 2 * sum(caps),
                       'min': min(caps), 'max': max(caps)},
        'checks': {'same_model_and_exact_case_uid': True, 'same_original_sa_source_hashes': True,
                   'ordered_nodes_and_injection_identity': True,
                   'lea_llm_calls_is_non_tt_algorithm_window_count': True,
                   'all_recorded_api_calls_at_least_algorithm_calls': True,
                   'csv_result_and_all_call_logs_token_sums': True,
                   'json_retry_overhead_included': True, 'ceiling_integer_arithmetic': True,
                   'historical_sa_outputs_and_metrics_unchanged': True,
                   'one_wave_80_cases_two_methods_only': True},
        'inputs_sha256': {'historical_sa_raw_reference.json': raw_sha,
                         'science/repo/portable_data/qwen80_case_plan.json': sha(PLAN),
                         'sources/manifest.json': sha(ROOT / 'sources/manifest.json'),
                         'prepare_budget.py': sha(Path(__file__))},
        'outputs_sha256': {name: sha(ROOT / name) for name in
                           ('historical_sa_reference.json', 'run_scope.json', 'budget_sources.json')},
    }
    freeze(ROOT / 'budget_preflight.json', preflight)
    print(json.dumps({key: preflight[key] for key in
                      ('status', 'case_count', 'expected_baseline_arms', 'budget_kind',
                       'token_caps', 'model_calls')}, ensure_ascii=False))


if __name__ == '__main__':
    main()

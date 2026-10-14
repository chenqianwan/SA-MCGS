#!/usr/bin/env python3
"""Freeze verified historical SA identities and outputs without choosing a budget.

Only writes historical_sa_raw_reference.json and identity_preflight.json.
Uses the standard library, performs no inference, and never writes run_scope.json
or historical_sa_reference.json. Historical SA token usage is unavailable.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXP = ROOT.parent
REPO = ROOT.parents[3]
MODEL = 'qwen2.5-72b'
ALIAS = 'qwen2.5-72b-instruct'
PLAN = EXP / 'equal_budget_all80_20261009/science/repo/portable_data/qwen80_case_plan.json'
SOURCES = EXP / 'unified_scoring_20261002/source_record_audit.csv'
METRICS = EXP / 'unified_scoring_20261002/canonical_case_metrics.csv'
LEA_COSTS = EXP / ('lea_full320_completion_20260923/cluster_qwen72b/'
                  'retrieved_final_20260924/results/lea_qwen80/summary_method_cases.csv')
NATIVE_FIELDS = ('ranking', 'scores', 'evidence_risk_subgraph_nodes')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def require(condition, explanation):
    if not condition:
        raise ValueError(explanation)


def freeze(path, value):
    if path.exists():
        require(read(path) == value, f'Frozen artifact differs: {path.name}')
        return
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def csv_rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def reference_map(path):
    rows = [row for row in csv_rows(path)
            if row['model'] == MODEL and row['method'] == 'sa-mcgs']
    result = {row['case_uid']: row for row in rows}
    require(len(rows) == len(result) == 80, f'Expected 80 unique SA rows: {path}')
    return result


def injection_identity(record, template):
    # Exact deterministic field extraction used by run_cost_audit_clean.py.
    return {
        'seed': int(record.get('inject_seed') or 42),
        'profile': str(record.get('inject_profile') or 'memory_stress'),
        'profile_version': record.get('inject_profile_version'),
        'requested_conflict_family': str(template),
        'conflict_family': record.get('injected_conflict_family'),
        'conflict_severity': record.get('injected_conflict_severity'),
        'conflict_template': record.get('injected_conflict_template'),
        'root_node': record.get('injected_node'),
        'witness_node': record.get('injected_witness_node'),
        'witness_distance': record.get('injected_witness_distance'),
        'bridge_node': record.get('injected_bridge_node'),
        'bridge_distance': record.get('injected_bridge_distance'),
        'risk_nodes': list(record.get('injected_risk_nodes') or []),
        'evidence_nodes': list(record.get('injected_evidence_nodes') or []),
        'affected_nodes': list(record.get('injected_affected_nodes') or []),
    }


def native_metrics(record, case):
    ids = case['planned_scc_clause_ids']
    allowed = set(ids)
    rows = record.get('ranking') or []
    ranking = [row[0] for row in rows]
    selected = set(record.get('evidence_risk_subgraph_nodes') or [])
    valid = bool(selected and selected <= allowed and len(rows) == len(ids)
                 and set(ranking) == allowed
                 and all(len(row) >= 2 and math.isfinite(float(row[1])) for row in rows))
    labels = case['planned_injection_identity']
    risks, evidence = set(labels['risk_nodes']), set(labels['evidence_nodes'])
    rank = ranking.index(labels['root_node']) + 1 if valid else None
    return {
        'valid': valid, 'root_at_1': int(rank == 1),
        'root_at_3': int(rank is not None and rank <= 3), 'root_rank': rank,
        'mrr': 1 / rank if rank else 0,
        'risk_any': int(valid and bool(selected & risks)),
        'risk_all': int(valid and risks <= selected),
        'endpoint_recall': len(selected & risks) / len(risks) if valid else 0,
        'evidence_all': int(valid and evidence <= selected),
        'evidence_recall': len(selected & evidence) / len(evidence) if valid else 0,
        'output_n': len(selected) if valid else None,
        'compression': 1 - len(selected) / len(ids) if valid else None,
    }


def lea_cost_summary(plan):
    rows = csv_rows(LEA_COSTS)
    by_id = {row['case_id']: row for row in rows}
    require(len(rows) == len(by_id) == 80, 'Expected 80 unique historical LEA costs')
    require(set(by_id) == {case['case_id'] for case in plan}, 'LEA case IDs differ')
    for case in plan:
        row = by_id[case['case_id']]
        require(row['model'] == MODEL and row['domain'] == case['domain']
                and int(row['scc_size']) == case['scc_size'], 'LEA identity mismatch')
        require(int(row['total_tokens']) == int(row['prompt_tokens'])
                + int(row['completion_tokens']), 'LEA token sum differs')
    fields = ('llm_calls', 'recorded_api_calls', 'prompt_tokens',
              'completion_tokens', 'total_tokens')
    return {
        'source_file': str(LEA_COSTS), 'source_sha256': sha(LEA_COSTS),
        'model': MODEL, 'method': 'lea', 'cases': 80,
        'interpretation': 'Observed costs of historical LEA, not SA costs. Informational only; no budget rule selected.',
        'used_to_set_budget': False,
        'totals': {field: sum(int(row[field]) for row in rows) for field in fields},
        'by_domain': {domain: {
            'cases': sum(row['domain'] == domain for row in rows),
            **{field: sum(int(row[field]) for row in rows if row['domain'] == domain)
               for field in fields}}
            for domain in sorted({case['domain'] for case in plan})},
    }


def main():
    plan = read(PLAN)
    require(len(plan) == len({case['case_uid'] for case in plan}) == 80,
            'Expected 80 frozen case identities')
    require([case['main_case_order'] for case in plan] == list(range(1, 81)),
            'Main case order differs')
    sources, metrics = reference_map(SOURCES), reference_map(METRICS)
    require(set(sources) == set(metrics) == {case['case_uid'] for case in plan},
            'Plan and unified scoring case sets differ')
    output_rows = []
    for case in plan:
        uid = case['case_uid']
        source, official = sources[uid], metrics[uid]
        source_path = REPO / case['source_result_repo_relpath']
        require(source['source'] == case['source_result_repo_relpath'], f'Source path: {uid}')
        source_sha = sha(source_path)
        require(source_sha == source['sha256'] == official['source_sha256']
                == case['source_result_sha256'].removeprefix('sha256:'), f'Source SHA: {uid}')
        document = read(source_path)
        records = document if isinstance(document, list) else [document]
        matches = [(index, record) for index, record in enumerate(records)
                   if record.get('method') == 'sa-mcgs' and record.get('model') == MODEL
                   and record.get('domain') == case['domain']]
        require(len(matches) == 1, f'Nonunique historical SA row: {uid}')
        source_index, record = matches[0]
        record_sha = canonical_sha(record)
        require(record_sha == case['source_sa_record_sha256'].removeprefix('sha256:'),
                f'SA record SHA: {uid}')
        require(record['scc_clause_ids'] == case['planned_scc_clause_ids'], f'Ordered nodes: {uid}')
        require(record['scc_size'] == case['scc_size'] == len(case['planned_scc_clause_ids']),
                f'Source size: {uid}')
        require(record['budget'] == 60, f'Unexpected historical rollout setting: {uid}')
        injection = injection_identity(record, case['template'])
        require(injection == case['planned_injection_identity'], f'Injection fields: {uid}')
        planned_identity = case['planned_case_identity']
        require(planned_identity['injection'] == injection
                and planned_identity['ordered_clause_ids'] == record['scc_clause_ids']
                and planned_identity['domain'] == record['domain'], f'Planned identity: {uid}')
        identity_payload = {key: value for key, value in planned_identity.items()
                            if key not in ('fingerprint', 'case_uid')}
        fingerprint = canonical_sha(identity_payload)
        require(planned_identity['fingerprint'] == case['planned_scc_fingerprint']
                == 'sha256:' + fingerprint and uid == planned_identity['case_uid']
                == 'scid-v1-' + fingerprint, f'Case UID fingerprint: {uid}')
        require(official['physical_scc_uid'] == case['physical_scc_uid']
                and official['domain'] == case['domain']
                and int(official['main_case_order']) == case['main_case_order']
                and official['main_case_id'] == case['main_case_id'], f'Unified identity: {uid}')
        measured = native_metrics(record, case)
        require(measured['valid'] == (official['valid'] == 'True')
                == (source['valid'] == 'True'), f'Valid status: {uid}')
        require(source['identity_verified'] == 'True'
                and source['metrics_recomputed_match_archive'] == 'True', f'Source audit: {uid}')
        for derived, original in (('root_at_3', 'root_at3'), ('risk_all', 'risk_all'),
                                  ('risk_any', 'risk_any'), ('output_n', 'retained_nodes')):
            require(measured[derived] == int(float(official[original])), f'{derived}: {uid}')
        require(math.isclose(measured['compression'], float(official['compression']),
                             rel_tol=0, abs_tol=1e-12), f'Compression: {uid}')
        token_keys = [key for key in record if any(term in key.lower()
                      for term in ('token', 'usage', 'cost'))]
        require(not token_keys, f'Unexpected token/cost metadata requires review: {uid}: {token_keys}')
        calls = record['llm_calls']
        require(isinstance(calls, int) and not isinstance(calls, bool) and calls >= 0,
                f'Invalid historical call count: {uid}')
        trace = record['trace_events']
        trace_calls = sum(not event.get('is_tt_hit') for event in trace)
        require(calls == trace_calls, f'Historical calls and non-TT traces differ: {uid}')
        selected = {field: record[field] for field in NATIVE_FIELDS}
        output_rows.append({
            'model_key': 'qwen25', 'model': record['model'], 'target_execution_alias': ALIAS,
            'method': 'sa-mcgs', 'case_uid': uid, 'case_id': case['case_id'],
            'main_case_order': case['main_case_order'], 'main_case_id': case['main_case_id'],
            'physical_scc_uid': case['physical_scc_uid'], 'domain': record['domain'],
            'source_n': record['scc_size'], 'source_scc_id': record['scc_id'],
            'template': case['template'], 'historical_rollout_budget': record['budget'],
            'completion_status': 'complete' if measured['valid'] else 'strict_experiment_failure',
            'selected_result': selected, 'selected_result_sha256': canonical_sha(selected),
            'selected_result_fields': list(NATIVE_FIELDS), 'metrics': measured,
            'llm_calls': calls, 'historical_runtime_sec': record.get('time'),
            'historical_trace_events': len(trace), 'historical_non_tt_trace_events': trace_calls,
            'usage': {'prompt_tokens': None, 'completion_tokens': None, 'total_tokens': None,
                      'calls': None, 'failed_api_calls': None},
            'usage_status': 'historical_provider_token_usage_not_recorded',
            'llm_calls_semantics': 'Historical algorithm call counter; not provider attempts including retries.',
            'token_budget': None, 'budget_rule': None, 'budget_selection_status': 'unresolved',
            'source_file': str(source_path), 'source_repo_relpath': source['source'],
            'source_sha256': source_sha, 'source_sa_record_sha256': record_sha,
            'source_record_index': source_index, 'planned_scc_fingerprint': case['planned_scc_fingerprint'],
            'planned_scc_clause_ids': case['planned_scc_clause_ids'],
            'planned_injection_identity': injection,
            'identity_and_unified_metrics_verified': True,
        })
    require(len({row['physical_scc_uid'] for row in output_rows}) == 20, 'Expected 20 source SCCs')
    lea_summary = lea_cost_summary(plan)
    reference = {
        'schema': 'historical_sa_raw_reference_without_budget_v1',
        'provenance': {
            'reference_kind': 'historical_main_sa_strict_no_token_usage',
            'source_model': MODEL, 'target_execution_alias': ALIAS,
            'model_calls': 0, 'sa_execution_enabled': False,
            'budget_rule': None, 'budget_selection_status': 'unresolved',
            'not_an_executable_budget_reference': True,
            'token_usage_statement': 'Historical SA provider prompt/completion/total tokens were not recorded; all are null. No actual-token-match claim is supported.',
            'matching': '80 case UIDs recomputed from frozen identity payloads; exact ordered source nodes, injection fields, original file bytes SHA256 and SA record SHA256; native metrics match unified scoring.',
            'graph_reconstruction': 'This check verifies the frozen identity payload and original source record. Runner preflight separately rebuilds graphs and rechecks injected input identity.',
            'selected_result_policy': 'Exact projection of original native ranking, scores and evidence_risk_subgraph_nodes. Full original record remains at source_file and is fixed by source_sha256 and source_sa_record_sha256.',
            'inputs': {str(path): sha(path) for path in (PLAN, SOURCES, METRICS, LEA_COSTS)},
            'script_sha256': sha(Path(__file__)),
        },
        'rows': output_rows,
        'historical_lea_cost_information_only': lea_summary,
    }
    reference_path = ROOT / 'historical_sa_raw_reference.json'
    freeze(reference_path, reference)
    preflight = {
        'schema': 'historical_sa_identity_preflight_v1',
        'status': 'passed_identity_and_metrics_only',
        'run_ready': False, 'budget_selection_status': 'unresolved',
        'model_calls': 0, 'sa_execution_enabled': False,
        'source_model': MODEL, 'target_execution_alias': ALIAS,
        'source_cases': len(plan), 'historical_sa_rows': len(output_rows),
        'source_scc_count': len({row['physical_scc_uid'] for row in output_rows}),
        'case_uids': [case['case_uid'] for case in plan],
        'valid_rows': sum(row['metrics']['valid'] for row in output_rows),
        'missing_historical_token_usage_rows': sum(row['usage']['total_tokens'] is None for row in output_rows),
        'historical_llm_calls': {'total': sum(row['llm_calls'] for row in output_rows),
                                 'min': min(row['llm_calls'] for row in output_rows),
                                 'max': max(row['llm_calls'] for row in output_rows)},
        'domain_counts': dict(sorted(Counter(case['domain'] for case in plan).items())),
        'template_counts': dict(sorted(Counter(case['template'] for case in plan).items())),
        'fixed_sa_metrics': {key: sum(row['metrics'][key] for row in output_rows) / 80
                             for key in ('risk_all', 'root_at_3', 'risk_any', 'compression')},
        'checks': {'unique_80_cases': True, 'frozen_case_uid_fingerprint': True,
                   'original_source_bytes_sha256': True, 'source_sa_record_sha256': True,
                   'ordered_scc_nodes': True, 'injection_identity': True,
                   'unified_scoring_identity_and_metrics': True,
                   'historical_llm_calls_equal_non_tt_trace_count': True,
                   'lea_cost_table_80_case_ids': True},
        'artifacts': {str(reference_path): sha(reference_path), str(Path(__file__)): sha(Path(__file__))},
        'notice': 'Identity preparation is complete. No token or call budget rule is selected or frozen; this artifact does not authorize execution.',
    }
    freeze(ROOT / 'identity_preflight.json', preflight)
    print(json.dumps({key: preflight[key] for key in
                      ('status', 'source_cases', 'valid_rows', 'missing_historical_token_usage_rows',
                       'run_ready', 'budget_selection_status', 'model_calls')}, ensure_ascii=False))


if __name__ == '__main__':
    main()

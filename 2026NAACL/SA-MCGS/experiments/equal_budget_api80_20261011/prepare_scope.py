#!/usr/bin/env python3
"""Prepare the remaining benchmark cases offline; never issue API requests."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXP = ROOT.parent
REPO = ROOT.parents[3]
PILOT = EXP / 'equal_budget_api10_20261011'
MODELS = ('gpt-4o', 'gemini-2.5-pro')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(name, value):
    path = ROOT / name
    if path.exists():
        if read(path) != value:
            raise RuntimeError(f'Existing prepared input differs: {name}')
        return
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    plan_path = EXP / 'equal_budget_all80_20261009/science/repo/portable_data/qwen80_case_plan.json'
    main_plan = read(plan_path)
    pilot_manifest_path = PILOT / 'sample_manifest.json'
    pilot_uids = {c['case_uid'] for c in read(pilot_manifest_path)}
    main_uids = {c['case_uid'] for c in main_plan}
    assert len(main_plan) == len(main_uids) == 80
    assert len(pilot_uids) == 10 and pilot_uids <= main_uids
    remaining = [c for c in main_plan if c['case_uid'] not in pilot_uids]
    assert len(remaining) == 70

    metric_path = EXP / 'unified_scoring_20261002/canonical_case_metrics.csv'
    source_path = EXP / 'unified_scoring_20261002/source_record_audit.csv'
    cost_path = EXP / 'cost_prior_12case_gpt4o_gemini25pro_b60_v1/cost/strict_method_cells.csv'
    metrics = list(csv.DictReader(metric_path.open()))
    sources = list(csv.DictReader(source_path.open()))
    costs = [r for r in csv.DictReader(cost_path.open()) if r['method'] == 'sa-mcgs']
    references, plans, budgets = [], {}, []
    for model in MODELS:
        metric_map = {r['case_uid']: r for r in metrics if r['model'] == model and r['method'] == 'sa-mcgs'}
        source_map = {r['case_uid']: r for r in sources if r['model'] == model and r['method'] == 'sa-mcgs'}
        assert set(metric_map) == set(source_map) == main_uids
        plans[model] = []
        for original in main_plan:
            uid = original['case_uid']
            metric, source = metric_map[uid], source_map[uid]
            actual_source = REPO / source['source']
            assert sha(actual_source) == source['sha256'] == metric['source_sha256']
            references.append({
                'model': model, 'method': 'sa-mcgs', 'case_uid': uid,
                'main_case_order': int(metric['main_case_order']), 'main_case_id': metric['main_case_id'],
                'domain': metric['domain'], 'source_file': str(actual_source),
                'source_sha256': source['sha256'], 'source': 'fixed original main experiment; no new SA predictions',
                'metrics': {'valid': metric['valid'] == 'True',
                            'root_at_3': int(float(metric['root_at3'])),
                            'risk_all': int(float(metric['risk_all'])),
                            'risk_any': int(float(metric['risk_any'])),
                            'compression': float(metric['compression']) if metric['compression'] else None,
                            'output_n': int(metric['retained_nodes']) if metric['retained_nodes'] else None}})
            if uid in pilot_uids:
                continue
            case = copy.deepcopy(original)
            source_document = read(actual_source)
            source_rows = source_document if isinstance(source_document, list) else [source_document]
            matching_source = [r for r in source_rows if r.get('model') == model and r.get('method') == 'sa-mcgs' and r.get('domain') == metric['domain']]
            assert len(matching_source) == 1
            record_hash = hashlib.sha256(json.dumps(matching_source[0], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            case.update(model=model, case_slot=int(metric['main_case_order']),
                        source_result_file=str(actual_source), source_result_sha256='sha256:' + source['sha256'],
                        source_sa_record_sha256='sha256:' + record_hash,
                        source_result_repo_relpath=source['source'], source_result_file_original=str(actual_source))
            plans[model].append(case)
            measured = next((r for r in costs if r['model'] == model and r['case_uid'] == uid), None)
            domain_costs = [r for r in costs if r['model'] == model and r['domain'] == case['domain']]
            estimate = math.ceil(sum(int(r['total_tokens']) for r in domain_costs) / len(domain_costs))
            budgets.append({'model': model, 'case_uid': uid, 'case_slot': case['case_slot'],
                            'domain': case['domain'], 'scc_size': case['scc_size'],
                            'measured_cost_audit_token_cap': int(measured['total_tokens']) if measured else None,
                            'estimated_domain_mean_token_cap': estimate,
                            'estimate_source_count': len(domain_costs),
                            'cost_audit_source_result': measured['result_file'] if measured else None})

    freeze('case_plans.json', plans)
    freeze('main_sa_references.json', references)
    freeze('budget_sources.json', budgets)
    freeze('pilot_results.json', read(PILOT / 'reporting_retry_20261011/case_results.json'))
    freeze('scope_manifest.json', {
        'models': list(MODELS), 'methods': ['lea', 'full-scc'], 'benchmark_case_count': 80,
        'new_case_count_per_model': 70, 'new_baseline_cells': 280,
        'pilot_case_uids': sorted(pilot_uids), 'remaining_case_uids': [c['case_uid'] for c in remaining],
        'sa_rerun': False, 'budget_policy_config': 'protocol.json',
        'input_sha256': {str(p): sha(p) for p in [plan_path, pilot_manifest_path, metric_path, source_path, cost_path,
                                                 PILOT / 'reporting_retry_20261011/case_results.json']}})
    print(json.dumps({'prepared_cases_per_model': 70, 'new_baseline_cells': 280,
                      'measured_budget_model_cases': sum(r['measured_cost_audit_token_cap'] is not None for r in budgets),
                      'missing_measured_budget_model_cases': sum(r['measured_cost_audit_token_cap'] is None for r in budgets),
                      'paid_requests': 0}))


if __name__ == '__main__':
    main()

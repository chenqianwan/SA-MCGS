#!/usr/bin/env python3
"""Freeze the user-approved calibrated budgets before any new inference."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXP = ROOT.parent
PILOT = EXP / 'equal_budget_api10_20261011'


def read(p):
    return json.loads(p.read_text())


def freeze(p, value):
    if p.exists() and read(p) != value:
        raise RuntimeError(f'Frozen input differs: {p.name}')
    if not p.exists():
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    rows = read(ROOT / 'budget_sources.json')
    budgets = []
    for row in rows:
        measured = row['measured_cost_audit_token_cap']
        budgets.append({**row, 'token_cap': measured if measured is not None else row['estimated_domain_mean_token_cap'],
                        'budget_source': 'same-case recorded cost audit' if measured is not None else 'ceil of same-model same-domain recorded SA cost-audit mean',
                        'historical_main_actual_token_match': False})
    assert len(budgets) == len({(r['model'], r['case_uid']) for r in budgets}) == 140
    assert all(isinstance(r['token_cap'], int) and r['token_cap'] > 0 for r in budgets)
    freeze(ROOT / 'budgets.json', budgets)
    dependencies = [
        ROOT / 'run_remaining.py', ROOT / 'report_results.py', Path(__file__), ROOT / 'prepare_scope.py',
        ROOT / 'case_plans.json', ROOT / 'budgets.json', ROOT / 'budget_sources.json',
        ROOT / 'scope_manifest.json', ROOT / 'main_sa_references.json', ROOT / 'pilot_results.json',
        PILOT / 'case_plans.json', PILOT / 'methods_full.py', PILOT / 'api_budget_client.py',
        PILOT / 'resilient_candidates_v4/api_adapter.py', PILOT / 'pending_v2/budget_guard.py',
        PILOT / 'recovery_v1/recovery_transport.py',
        EXP / 'equal_budget_all80_20261009/science_support.py',
        EXP / 'equal_budget_all80_20261009/budget_client.py',
    ]
    protocol = {
        'experiment': ROOT.name, 'models': ['gpt-4o', 'gemini-2.5-pro'], 'methods': ['lea', 'full-scc'],
        'benchmark_cases_per_model': 80, 'new_cases_per_model': 70, 'expected_baseline_cells': 280,
        'pilot_baseline_cells_reused': 40, 'whole_experiment_runs': 1, 'sa_rerun': False,
        'endpoint': 'https://api3.xhub.chat/v1', 'per_model_cell_concurrency': 8,
        'timeout_seconds': 600, 'sdk_retries': 0, 'seed': 42,
        'window_size': 4, 'temperature': 0.4, 'selector_temperature': 0,
        'local_max_tokens': 2048, 'full_scc_max_tokens': 12000, 'judge_max_tokens': 256,
        'json_attempts': 3, 'selector_attempts': 1,
        'authorization': '2026-10-11 user requested all remaining 70 cases, then explicitly approved fixing missing budgets from existing same-model, same-domain cost data.',
        'budget_rule': 'Use same-case historical cost-audit total tokens where available (2 remaining cases/model). For the other 68 cases/model, freeze ceil(mean SA total_tokens) over the existing same-model, same-domain 12-case cost-audit subset. Give each baseline its own identical cap; charge all candidates, JSON attempts and selection. Estimates are not historical-main per-case actual token matches.',
        'cost_calibration_data': str(EXP / 'cost_prior_12case_gpt4o_gemini25pro_b60_v1/cost/strict_method_cells.csv'),
        'comparison_label': 'SA cost-audit-calibrated token ceilings with fixed original-main SA outputs',
        'failure_policy': 'Keep each failed candidate and accounted usage; continue independent candidates using the existing v4 batch adapter. A failed cell does not stop other cells. Existing final records are never rerun. Preserve raw output, failure status and actual costs.',
        'output_policy': 'All terminal cases remain in reported denominators. Empty selected output scores compression 1 and all task metrics 0. Pending cases remain pending, not failures.',
        'algorithm_policy': 'Use the unchanged pilot methods_full.py and its same-model anonymous selector. No labels or SA scores enter candidate generation or selection.',
        'source_hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies},
    }
    freeze(ROOT / 'protocol.json', protocol)
    print(json.dumps({'new_cells': 280, 'concurrency_per_model': 8,
                      'token_caps_across_two_baselines': {m: 2 * sum(r['token_cap'] for r in budgets if r['model'] == m) for m in protocol['models']},
                      'paid_requests': 0}))


if __name__ == '__main__':
    main()

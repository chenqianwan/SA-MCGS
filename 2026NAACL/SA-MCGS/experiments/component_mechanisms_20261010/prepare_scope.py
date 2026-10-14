#!/usr/bin/env python3
"""Freeze the author-authorized, single-run ablation scope; never calls models."""
import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'equal_budget_all80_20261009/science/repo/portable_data/qwen80_case_plan.json'


def freeze(name, value):
    path = ROOT / name
    if path.exists():
        assert json.loads(path.read_text()) == value, f'Refusing to change frozen {name}'
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    cases = json.loads(SOURCE.read_text())
    uids = [c['case_uid'] for c in cases]
    sources = {c['physical_scc_uid'] for c in cases}
    assert len(cases) == len(set(uids)) == 80
    assert len(sources) == 20
    assert set(collections.Counter(c['template'] for c in cases).values()) == {20}
    freeze('protocol.json', {
        'schema_version': 1,
        'experiment_id': ROOT.name,
        'models': ['llama', 'kimi', 'qwen35'],
        'arms': ['full', 'no_relation_guidance', 'no_critical_revisit', 'no_both', 'random_windows'],
        'cases_per_model': 80,
        'independent_source_sccs': 20,
        'repeats': 1,
        'seed': 42,
        'rollouts': 60,
        'window_size': 4,
        'internal_concurrency': 4,
        'expected_results': 1200,
        'temperature': 0.4,
        'max_output_tokens': 2048,
        'tt_max_reuse': 3,
        'external_api_enabled': False,
        'workers_per_replica': {'llama': 10, 'kimi': 16, 'qwen35': 16},
        'workers_per_model': {'llama': 20, 'kimi': 64, 'qwen35': 32},
        'provider_seed': None,
        'rng_policy': 'Independent instance RNG, same seed 42; one run per task. No claim of server determinism.',
        'concurrency_policy': 'Task-local selection metadata fixes concurrent window provenance; frozen batch concurrency 4 in every arm.',
        'budget_policy': '60 rollout iterations per arm; actual calls/input/output tokens reported, not claimed equal-token.',
        'search_interventions': {
            'full': {'relation_guidance': True, 'critical_revisit': True},
            'no_relation_guidance': {'relation_guidance': False, 'critical_revisit': True},
            'no_critical_revisit': {'relation_guidance': True, 'critical_revisit': False},
            'no_both': {'relation_guidance': False, 'critical_revisit': False},
            'random_windows': {'selection': 'random adjacency expansion', 'adaptive_probes': False},
        },
        'critical_ledger': 'Retained in all arms; only its revisit scheduling is ablated online.',
        'probe_schedule': 'Retain original Full outer probe gate and critical-revisit inner gate in all applicable arms.',
        'analyses': {
            'common_selector': 'mean-risk top-k, k=min(n,max(4,ceil(0.45*n))); native output reported separately',
            'full_trace_selectors': ['full', 'mean-risk', 'lea-score', 'locked-no-replacement'],
            'selector_size_matching': 'Match each Full trace endpoint actual k; locked admission capacity frozen to that endpoint k before replay.',
            'core_cap_ratios': [0.25, 0.35, 0.45, 0.60],
            'core_min_nodes': 4,
            'trace_prefixes': [15, 30, 45, 60],
            'prefix_interpretation': 'Observed-evidence completion prefixes, not independent shorter-budget reruns.',
            'metrics': ['risk_all', 'risk_any', 'root_at_3', 'compression', 'calls', 'input_tokens', 'output_tokens'],
            'selector_root_at_3': 'Shared mean-risk ranking within a trace; not selector-specific improvement.',
            'subgroups': ['domain', 'template', 'scc_size_le13_14to20_ge21'],
            'failure_denominator': 'All 80 cases per model/arm for hit metrics; scientific failure scores zero. Pending or infrastructure failure keeps formal rates incomplete; report observed-hit lower bounds and failure type. Compression on valid outputs.',
            'independence_unit': '20 source SCCs; injected variants, prefixes and selector outputs are not independent new samples.',
            'reporting': 'All completed arms and predetermined settings retained; no quality-based rerun or result exclusion.',
        },
        'historical_main_results': 'Preserved; new Full belongs only to this contemporaneous ablation.',
        'recovery_policy': 'Resume completed tasks without rerunning. Do not resample scientific failures or unknown outcomes.',
        'authorization': 'User requested all proposed experiments, one run only, previous concurrency, existing cluster allocation.',
    })
    freeze('run_scope.json', {
        'version': 1,
        'case_uids': uids,
        'cases_per_model': 80,
        'expected_results': 1200,
        'repeats': 1,
        'stop_after_scope': True,
        'selection_rule': 'All 80 frozen main-experiment variants, no outcome-based selection.',
        'case_plan_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    })
    freeze('preflight/scope_verification.json', {
        'cases': len(cases), 'source_sccs': len(sources),
        'domain_counts': dict(collections.Counter(c['domain'] for c in cases)),
        'template_counts': dict(collections.Counter(c['template'] for c in cases)),
        'rollout_tasks': 1200, 'max_rollout_iterations': 72000,
        'new_model_calls_during_scope_preparation': 0,
    })
    print(json.dumps({'status': 'scope_frozen', 'cases': 80, 'source_sccs': 20, 'search_tasks': 1200}))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Assemble the confirmed five-model values without changing their estimators."""
from pathlib import Path
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / 'internal_sources'
MODELS = ('gpt4o', 'qwen25', 'llama', 'qwen35', 'kimi')
LABELS = {'gpt4o': 'GPT-4o', 'qwen25': 'Qwen2.5-72B',
          'llama': 'Llama 3.1-8B-Instruct', 'qwen35': 'Qwen3.5-9B', 'kimi': 'Kimi-VL-A3B'}
METHODS = ('sa-mcgs', 'lea', 'full-scc')
METRICS = ('root_at_3', 'risk_any', 'risk_all', 'compression')


def read(name):
    return json.loads((SOURCES / name).read_text())


def build():
    table = read('three_model_table_source.json')['rows']
    old = read('three_model_summary.json')['aggregate']
    assert old['formal_three_wave_ready'] and old['terminal_new_results'] == 1440
    assert all(w['complete'] and w['budget_audit_passed'] for w in old['wave_audits'])
    api = read('gpt4o_recovery_summary.json')
    assert api['recovery_complete']
    qwen = read('qwen72b_summary.json')
    status = read('qwen72b_execution_status.json')
    assert qwen['execution_terminal_results'] == qwen['execution_expected_results'] == 160
    assert status['status'] == 'complete' and status['running_workers'] == 0
    assert len(status['workers']) == 48 and all(w['exit_code'] == 0 for w in status['workers'])
    assert len(qwen['budget_audit']) == 160
    assert all(r['cap_matches_reference_budget'] and r['actual_tokens'] <= r['configured_token_cap']
               for r in qwen['budget_audit'])
    rows, internal = [], []
    for model in MODELS:
        for method in METHODS:
            provenance = {'model': model, 'method': method, 'planned_cases': 80}
            if model == 'gpt4o':
                raw = next(r for r in api['groups'] if r['model'] == 'gpt-4o' and r['method'] == method)
                metrics = {key: raw[key] for key in METRICS}
                provenance.update(source='gpt4o_recovery_summary.json', runs=1,
                    aggregation='reported 80-case aggregate, unchanged', valid=raw['valid'],
                    compression_policy='all 80 cases; invalid outputs contribute 100% compression',
                    budget_policy='cost-audit-calibrated ceiling; recovery overhead separately recorded')
            elif model == 'qwen25':
                raw = next(r for r in qwen['rows'] if r['method'] == method)
                metrics = {key: raw['metrics_over_planned'][key] for key in METRICS if key != 'compression'}
                metrics['compression'] = raw['mean_compression_valid']
                provenance.update(source='qwen72b_summary.json', runs=1,
                    aggregation='reported 80-case aggregate, unchanged', valid=raw['valid_cases'],
                    compression_policy='mean across valid outputs', budget_policy=qwen['budget_provenance'])
            else:
                raw = next(r for r in table if r['model'] == model and r['method'] == method)
                metrics = {key: raw['metrics'][key]['mean'] for key in METRICS}
                check = next(r for r in old['historical_sa' if method == 'sa-mcgs' else 'comparisons']
                             if r['model'] == model and (method == 'sa-mcgs' or r['method'] == method))
                for key, value in metrics.items():
                    expected = (check['mean_compression_valid'] if key == 'compression' else check['metrics_over_planned'][key]) if method == 'sa-mcgs' else check['metrics'][key]['mean']
                    assert math.isclose(value, expected, abs_tol=1e-12)
                provenance.update(source='three_model_table_source.json',
                    runs=1 if method == 'sa-mcgs' else 3,
                    aggregation='fixed historical aggregate' if method == 'sa-mcgs' else 'equal-weight mean of three run-level values; unchanged',
                    compression_policy='valid-output mean within each run',
                    budget_policy='historical SA token consumption matched per case')
            assert all(math.isfinite(v) and 0 <= v <= 1 for v in metrics.values())
            rows.append({'model': model, 'model_label': LABELS[model], 'method': method,
                         **{key + '_percent': 100 * value for key, value in metrics.items()}})
            internal.append(provenance)
    assert len(rows) == 15 and len({(r['model'], r['method']) for r in rows}) == 15
    (ROOT/'figure_source_data.json').write_text(json.dumps(rows, indent=2)+'\n')
    with (ROOT/'figure_source_data.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    cases = read('gpt4o_internal_case_audit.json')
    caveats = {
        'rows': internal,
        'public_display': 'User requested preserved point estimates, no repeated-run or SD exposition, and no failure explanation in figure/table.',
        'source_specific_compression': 'GPT-4o uses the requested original all-case compression; the other four models use valid-only compression. Do not infer a common compression estimator.',
        'gpt4o_actual_plus_recovery_exceeds_original_B': {
            method: sum(r['combined_exceeds_B'] for r in cases if r['method'] == method)
            for method in ('lea', 'full-scc')},
        'strict_actual_spend_equality_claim': False,
        'uncertainty_removed_from_display_only': True,
        'all_requested_model_method_metric_values_preserved': True,
    }
    (SOURCES/'aggregation_and_budget_audit.json').write_text(json.dumps(caveats, indent=2)+'\n')
    manifest = {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
                for p in SOURCES.iterdir() if p.is_file() and p.name != 'manifest.json'}
    (SOURCES/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Validated {len(rows)} rows and {len(rows)*len(METRICS)} metrics.')
    for row in rows:
        print(row['model_label'], row['method'], *(f"{row[k+'_percent']:.2f}" for k in METRICS))


if __name__ == '__main__':
    build()

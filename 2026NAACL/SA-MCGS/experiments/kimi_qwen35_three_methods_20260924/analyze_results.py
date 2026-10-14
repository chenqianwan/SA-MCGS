#!/usr/bin/env python3
"""Offline, read-only input audit for each frozen 80-case / three-method run.

Usage: python analyze_results.py --input-dir MODEL_OUTPUT [--input-dir OTHER]
       [--output-dir SEPARATE_ANALYSIS_DIRECTORY] [--allow-incomplete]

Only the Python standard library is used. No runner import, model call, or raw
result mutation occurs. Exit 2 means an audited but scientifically incomplete
run; --allow-incomplete permits that state for overnight progress reporting.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / 'runner/repo/portable_data/qwen80_case_plan.json'
FIELDS = {'naive-single': 'direct_risk_subgraph_nodes', 'lea': 'lea_risk_subgraph_nodes',
          'sa-mcgs': 'core_evidence_risk_subgraph_nodes'}
METRICS = ('root_at3', 'risk_any', 'risk_all')
IDENTITY_FIELDS = ('case_uid', 'domain', 'scc_size', 'planned_case_identity',
                   'planned_scc_clause_ids', 'planned_injection_identity',
                   'source_result_sha256', 'source_sa_record_sha256', 'main_case_order')


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def aggregate(rows):
    n = len(rows)
    evaluable = sum(r['state'] in ('complete', 'strict_experiment_failure') for r in rows)
    return {'planned': n, 'scientific_terminal': evaluable,
            'scientifically_complete': evaluable == n,
            'valid': sum(r['state'] == 'complete' for r in rows),
            'strict_failures': sum(r['state'] == 'strict_experiment_failure' for r in rows),
            'infrastructure_failures': sum(r['state'] == 'infrastructure_failure' for r in rows),
            'missing': sum(r['state'] == 'missing' for r in rows),
            **{m: {'hits': sum(r[m] for r in rows), 'planned_denominator': n,
                   'planned_conservative_rate': sum(r[m] for r in rows) / n if n else None,
                   'evaluable_denominator': evaluable,
                   'evaluable_rate': sum(r[m] for r in rows) / evaluable if evaluable else None}
               for m in METRICS},
            'compression_n': sum(r['valid'] for r in rows),
            'compression_valid_only': mean([r['compression'] for r in rows]),
            'json_exhaustion_cases': sum((r['json_parse_exhausted_windows'] or 0) > 0 for r in rows),
            'json_exhausted_windows': sum(r['json_parse_exhausted_windows'] or 0 for r in rows),
            'json_exhaustion_unknown_cases': sum(r['json_parse_exhausted_windows'] is None for r in rows
                                                 if r['state'] != 'missing'),
            'error_types': dict(collections.Counter(r['error_type'] for r in rows if r['error_type']))}


def audit(input_dir, reference_path=REFERENCE):
    root = Path(input_dir).resolve()
    input_hashes = {}

    def read(path):
        path = Path(path).resolve()
        raw = path.read_bytes()
        input_hashes[path] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    plan = read(root / 'case_plan.json')
    reference = read(reference_path)
    frozen = read(root / 'frozen_protocol.json')
    require(isinstance(plan, list) and len(plan) == 80, 'Plan must contain exactly 80 cases')
    require(len(reference) == 80, 'Reference plan must contain exactly 80 cases')
    require(len({c['case_id'] for c in plan}) == 80 and len({c['case_uid'] for c in plan}) == 80,
            'Duplicate case ID or UID')
    original = {c['case_uid']: c for c in reference}
    require({c['case_uid'] for c in plan} == set(original), 'Plan differs from frozen reference 80')
    require(frozen.get('cases') == 80 and set(frozen.get('methods', [])) == set(FIELDS),
            'Protocol does not declare 80 cases and all three methods')
    require(frozen.get('metric_node_fields') == FIELDS, 'Protocol metric node fields changed')
    model = frozen['model']
    for c in plan:
        for key in IDENTITY_FIELDS:
            require(c.get(key) == original[c['case_uid']].get(key), f'Changed reference {key}: {c["case_id"]}')
        require(c.get('model') == model, f'Wrong plan model: {c["case_id"]}')
        ids = c['planned_scc_clause_ids']
        truth = c['planned_injection_identity']
        require(len(ids) == len(set(ids)) == c['scc_size'], 'SCC size/IDs inconsistent')
        require(bool(truth['risk_nodes']) and set(truth['risk_nodes']) <= set(ids)
                and truth['root_node'] in ids, 'Invalid frozen truth identity')

    files = {p.name: p for p in (root / 'results').glob('*.json')}
    infra = {p.name: p for p in (root / 'infrastructure_failures').glob('*.json')}
    expected = {f'{c["case_id"]}__{m}.json' for c in plan for m in FIELDS}
    require(set(files) <= expected and set(infra) <= expected, 'Unexpected result/infra filenames')
    require(not set(files) & set(infra), 'Cell has both scientific and infrastructure terminal records')

    manifest_path = root / 'download_manifest.json'
    manifest_verified = False
    if manifest_path.exists():
        manifest = read(manifest_path)
        for name, metadata in manifest['files'].items():
            path = (root / name).resolve()
            require(path.is_relative_to(root) and path != root, 'Unsafe download manifest path')
            raw = path.read_bytes()
            require(len(raw) == metadata['bytes'] and hashlib.sha256(raw).hexdigest() == metadata['sha256'],
                    f'Download manifest mismatch: {name}')
            input_hashes[path] = hashlib.sha256(raw).hexdigest()
        require({str(p.relative_to(root)) for p in [root/'case_plan.json', root/'frozen_protocol.json',
                 *files.values(), *infra.values()]} <= set(manifest['files']), 'Manifest omits an analyzed input')
        manifest_verified = True

    rows = []
    protocol_sha = digest(frozen)
    if frozen.get('canonical_case_plan_sha256') is not None:
        require(frozen['canonical_case_plan_sha256'] == input_hashes[Path(reference_path).resolve()],
                'Frozen canonical plan SHA differs from the supplied reference')
    for c in plan:
        allowed = set(c['planned_scc_clause_ids'])
        truth = c['planned_injection_identity']
        physical = digest({'domain': c['domain'], 'clause_ids': sorted(allowed)})
        for method, field in FIELDS.items():
            name = f'{c["case_id"]}__{method}.json'
            result = read(files[name]) if name in files else read(infra[name]) if name in infra else None
            row = {'case_id': c['case_id'], 'case_uid': c['case_uid'], 'method': method,
                   'domain': c['domain'], 'physical_scc': physical, 'scc_size': c['scc_size'],
                   'scale': 'small' if c['scc_size'] <= 12 else 'medium' if c['scc_size'] <= 20 else 'large',
                   'state': 'missing', 'valid': False, **{m: 0 for m in METRICS},
                   'retained_nodes': None, 'compression': None, 'json_parse_exhausted_windows': None,
                   'error_type': None}
            if result is None:
                rows.append(row)
                continue
            for key, expected_value in {'case_id': c['case_id'], 'case_uid': c['case_uid'],
                                        'model': model, 'protocol_sha256': protocol_sha}.items():
                require(result.get(key) == expected_value, f'{name}: mismatched {key}')
            require(result.get('cost_audit_method', result.get('method')) == method, f'{name}: wrong method')
            if frozen.get('producer_sha256') is not None:
                require(result.get('producer_sha256') == frozen['producer_sha256'], f'{name}: wrong producer')
            state = result.get('completion_status')
            error = result.get('cost_audit_error') or result.get('error') or result.get('message')
            if name in infra:
                require(state == 'infrastructure_failure' and bool(error), f'{name}: invalid infra record')
            else:
                require(state in ('complete', 'strict_experiment_failure'), f'{name}: nonterminal science result')
                require(bool(result.get('error') or result.get('cost_audit_error')) ==
                        (state == 'strict_experiment_failure'), f'{name}: state and scientific error disagree')
                for key, expected_value in {'checkpoint_repository': frozen['checkpoint_repository'],
                                            'checkpoint_revision': frozen['checkpoint_revision'],
                                            'requested_model_id': frozen['served_model'],
                                            'domain': c['domain'], 'scc_size': c['scc_size']}.items():
                    require(result.get(key) == expected_value, f'{name}: mismatched {key}')
                for key in ('planned_case_identity', 'planned_scc_clause_ids', 'planned_injection_identity'):
                    require(result.get(key) == c[key], f'{name}: mismatched {key}')
                for actual, planned in [('actual_case_identity', 'planned_case_identity'),
                                        ('actual_scc_clause_ids', 'planned_scc_clause_ids'),
                                        ('actual_injection_identity', 'planned_injection_identity')]:
                    require(result.get(actual) == c[planned], f'{name}: mismatched {actual}')
            exhaustion = result.get('json_parse_exhausted_windows')
            require(exhaustion is None or (type(exhaustion) is int and exhaustion >= 0),
                    f'{name}: invalid JSON exhaustion counter')
            row.update(state=state, valid=state == 'complete', error_type=result.get('error_type'),
                       json_parse_exhausted_windows=exhaustion)
            if row['valid']:
                nodes, ranking = result.get(field), result.get('ranking')
                require(isinstance(nodes, list) and all(isinstance(x, str) for x in nodes)
                        and set(nodes) <= allowed, f'{name}: missing/invalid {field}')
                require(isinstance(ranking, list) and bool(ranking), f'{name}: missing ranking')
                require(all(isinstance(x, list) and len(x) == 2 and x[0] in allowed
                            and type(x[1]) in (int, float) and math.isfinite(x[1]) for x in ranking),
                        f'{name}: invalid ranking')
                ids = [x[0] for x in ranking]
                require(len(ids) == len(set(ids)), f'{name}: duplicate ranked nodes')
                if method == 'naive-single':
                    require(set(ids) == allowed, f'{name}: One-shot ranking is incomplete')
                selected = set(nodes)
                risk = set(truth['risk_nodes'])
                row.update(root_at3=int(truth['root_node'] in ids[:3]), risk_any=int(bool(selected & risk)),
                           risk_all=int(risk <= selected), retained_nodes=len(selected),
                           compression=1 - len(selected) / c['scc_size'])
            rows.append(row)

    overall = {m: aggregate([r for r in rows if r['method'] == m]) for m in FIELDS}
    groups = {dim: {key: {m: aggregate([r for r in rows if r['method'] == m and r[dim] == key])
                         for m in FIELDS} for key in sorted({r[dim] for r in rows})}
              for dim in ('domain', 'scale')}
    indexed = {(r['case_uid'], r['method']): r for r in rows}
    pairs = [(indexed[c['case_uid'], 'sa-mcgs'], indexed[c['case_uid'], 'lea']) for c in plan]
    observed_pairs = [(a, b) for a, b in pairs if a['state'] in ('complete', 'strict_experiment_failure')
                      and b['state'] in ('complete', 'strict_experiment_failure')]
    paired = {m: {'n': len(observed_pairs), 'sa_only': sum(a[m] > b[m] for a, b in observed_pairs),
                  'lea_only': sum(a[m] < b[m] for a, b in observed_pairs),
                  'both': sum(a[m] and b[m] for a, b in observed_pairs),
                  'neither': sum(not a[m] and not b[m] for a, b in observed_pairs)} for m in METRICS}
    common = [(a, b) for a, b in pairs if a['valid'] and b['valid']]
    summary_match = None
    summary_counts_match = None
    if (root / 'summary.json').exists():
        summary = read(root / 'summary.json')
        if 'scientific_terminal_results' in summary:
            science = sum(x['scientific_terminal'] for x in overall.values())
            infra_n = sum(x['infrastructure_failures'] for x in overall.values())
            require(summary.get('scientific_terminal_results') == science
                    and summary.get('infrastructure_failure_results') == infra_n
                    and summary.get('unresolved_results') == 240 - science - infra_n
                    and summary.get('terminal_results') == science + infra_n
                    and summary.get('scientific_complete') == (science == 240)
                    and summary.get('verification_passed') == (science + infra_n == 240),
                    'Cluster summary scientific/infrastructure coverage mismatch')
            for method, item in overall.items():
                actual = summary['counts'][method]
                expected_counts = {'complete': item['valid'], 'strict_experiment_failure': item['strict_failures'],
                                   'infrastructure_failure': item['infrastructure_failures'], 'unresolved': item['missing']}
                require(all(actual.get(k, 0) == v for k, v in expected_counts.items()),
                        f'{method}: summary outcome counts mismatch')
            summary_counts_match = True
        if 'methods' in summary and all(x['scientifically_complete'] for x in overall.values()):
            for method, item in overall.items():
                old = summary['methods'][method]
                require(old['terminal'] == 80 and old['strict_failures'] == item['strict_failures'],
                        f'{method}: summary count mismatch')
                for metric in METRICS:
                    require(math.isclose(old[metric], item[metric]['planned_conservative_rate'], abs_tol=1e-12),
                            f'{method}: summary {metric} mismatch')
                a, b = old['compression_valid_only'], item['compression_valid_only']
                require(a == b or a is not None and b is not None and math.isclose(a, b, abs_tol=1e-12),
                        f'{method}: summary compression mismatch')
            summary_match = True

    # Avoid reporting a snapshot assembled while producers replaced its files.
    require(set(files) == {p.name for p in (root / 'results').glob('*.json')}
            and set(infra) == {p.name for p in (root / 'infrastructure_failures').glob('*.json')},
            'Inputs changed during analysis; retry after snapshotting the outputs')
    for path, expected_sha in input_hashes.items():
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha, f'Input changed: {path}')
    report = {'audit_passed': True, 'scientifically_complete': all(x['scientifically_complete'] for x in overall.values()),
              'model': model, 'input_dir': str(root), 'cases': 80, 'planned_cells': 240,
              'physical_sccs': len({r['physical_scc'] for r in rows}),
              'api_calls': 0, 'protocol_sha256': protocol_sha, 'download_manifest_verified': manifest_verified,
              'metrics_match_complete_cluster_summary': summary_match,
              'coverage_counts_match_cluster_summary': summary_counts_match,
              'identity_check_scope': 'Result fields match the original frozen 80-case plan; this standalone audit does not reload graphs or replay inference.',
              'policy': 'Strict model-output failures score zero. Planned conservative detection divides by 80 and also assigns zero contribution to separately reported infrastructure failures and missing cells. Evaluable detection divides only by complete plus strict scientific failures. Compression averages valid outputs only. Operational skips are not scientific failures.',
              'statistical_scope': 'Descriptive only: 80 injection variants share 20 physical SCCs; no significance or universal improvement claim.',
              'overall': overall, 'groups': groups, 'sa_vs_lea_scientifically_evaluable_pairs': paired,
              'sa_vs_lea_common_valid_compression': {'n': len(common),
                  'sa_mean': mean([a['compression'] for a, b in common]),
                  'lea_mean': mean([b['compression'] for a, b in common]),
                  'identical_retained_node_count_pairs': sum(a['retained_nodes'] == b['retained_nodes'] for a, b in common)},
              'input_sha256': {str(p): h for p, h in sorted(input_hashes.items())}}
    require(report['physical_sccs'] == 20, 'Expected 20 physical SCCs')
    return report, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, action='append', required=True)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--reference-plan', type=Path, default=REFERENCE)
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    if args.output_dir:
        output = args.output_dir.resolve()
        require(not any(output == p.resolve() or output.is_relative_to(p.resolve()) for p in args.input_dir),
                'Analysis output must be outside all input directories')
    reports, model_names = [], set()
    for source in args.input_dir:
        report, rows = audit(source, args.reference_plan)
        require(report['model'] not in model_names, 'Repeated model input')
        model_names.add(report['model'])
        reports.append(report)
        if args.output_dir:
            output.mkdir(parents=True, exist_ok=True)
            label = ''.join(x if x.isalnum() or x in '-_' else '_' for x in report['model'])
            for name, value in [(f'{label}_analysis.json', report), (f'{label}_case_metrics.json', rows)]:
                path = output / name
                require(path.resolve() not in {Path(p) for p in report['input_sha256']}, 'Refusing to overwrite input')
                path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0 if args.allow_incomplete or all(r['scientifically_complete'] for r in reports) else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AuditError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'Analysis audit failed: {exc}', file=sys.stderr)
        raise SystemExit(1)

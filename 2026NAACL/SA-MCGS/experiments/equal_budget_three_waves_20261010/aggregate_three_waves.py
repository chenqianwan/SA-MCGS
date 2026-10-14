#!/usr/bin/env python3
"""Offline, strict aggregation of three 80-case baseline waves; stdlib only."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
MODELS = ('llama', 'kimi', 'qwen35')
METHODS = ('lea', 'full-scc')
METRICS = ('risk_all', 'root_at_3', 'risk_any')
TERMINAL = ('complete', 'strict_experiment_failure', 'infrastructure_failure')
N = 80


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def resolve(value, experiments):
    path = Path(value)
    return (path if path.is_absolute() else experiments / path).resolve()


def wave_specs(manifest, experiments):
    values = manifest['wave_dirs']
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError('manifest.wave_dirs must contain exactly three waves')
    waves = []
    for i, value in enumerate(values, 1):
        if isinstance(value, str):
            wave_id, path = f'wave{i}', value
        else:
            wave_id = value.get('wave_id', value.get('id', f'wave{i}'))
            path = value.get('path', value.get('wave_dir'))
        waves.append((str(wave_id), resolve(path, experiments)))
    if len({w[0] for w in waves}) != 3 or len({w[1] for w in waves}) != 3:
        raise ValueError('Three distinct wave IDs and directories are required')
    return waves


def metric_snapshot(row, ref=None):
    m = row['metrics']
    state = row['completion_status']
    if state not in TERMINAL or not isinstance(m.get('valid'), bool):
        raise ValueError('Unrecognized terminal status or missing boolean validity')
    valid = m['valid']
    if valid != (state == 'complete'):
        raise ValueError('Completion status and strict validity disagree')
    hits = {}
    for key in METRICS:
        value = m[key]
        if value not in (0, 1) or (not valid and value != 0):
            raise ValueError('Strict hit metrics must be binary; failures must be zero')
        hits[key] = int(value)
    source_n = row['source_n']
    if not isinstance(source_n, int) or source_n <= 0:
        raise ValueError('Invalid source node count')
    compression, output_n = m.get('compression'), m.get('output_n')
    if valid:
        if (not isinstance(output_n, int) or not 0 <= output_n <= source_n
                or not isinstance(compression, (int, float))
                or not math.isfinite(compression)
                or not math.isclose(compression, 1-output_n/source_n, abs_tol=1e-12)):
            raise ValueError('Compression must equal the per-case retained-node fraction')
    elif compression is not None or output_n is not None:
        raise ValueError('Failed output size/compression must be null, never 100%')
    if ref and (source_n != ref['source_n'] or row['domain'] != ref['domain']
                or row.get('historical_sa_source_sha256') != ref['source_sha256']):
        raise ValueError('Baseline source identity differs from historical SA reference')
    return {'valid': valid, **hits, 'output_n': output_n, 'compression': compression}


def group_stats(rows):
    valid = [r for r in rows if r['metrics']['valid']]
    sums = {k: sum(r['metrics'][k] for r in rows) for k in METRICS}
    return {
        'planned_cases': N, 'terminal_cases': len(rows), 'missing_cases': N-len(rows),
        'valid_cases': len(valid),
        'states': dict(collections.Counter(r['completion_status'] for r in rows)),
        'hits': sums, 'metrics_over_planned': {k: v/N for k, v in sums.items()},
        'mean_compression_valid': statistics.mean(r['metrics']['compression'] for r in valid) if valid else None,
        'compression_valid_cases': len(valid),
        'known_actual_tokens': sum(r['usage'].get('total_tokens', 0) or 0 for r in rows),
        'usage_complete': all(isinstance(r['usage'].get('total_tokens'), int)
                              and not r['usage'].get('held_calls', 0) for r in rows),
    }


def aggregate(manifest_path, experiments):
    manifest = read(manifest_path)
    specs = wave_specs(manifest, experiments)
    ref_path = resolve(manifest['historical_sa_reference'], experiments) if manifest.get('historical_sa_reference') else specs[0][1]/'historical_sa_reference.json'
    historical = read(ref_path)['rows']
    reference = {(r['model_key'], r['case_uid']): r for r in historical}
    scope_path = specs[0][1]/'run_scope.json'
    scope = read(scope_path)
    uids = scope['case_uids']
    if len(uids) != N or len(set(uids)) != N or scope['cases_per_model'] != N:
        raise ValueError('Exactly 80 frozen case UIDs are required')
    expected_ref = {(m, u) for m in MODELS for u in uids}
    if len(historical) != 240 or set(reference) != expected_ref:
        raise ValueError('Historical SA must contain exactly 240 unique model/case rows')
    historical_groups = []
    for model in MODELS:
        rs = []
        for uid in uids:
            r = reference[(model, uid)]
            if r['method'] != 'sa-mcgs':
                raise ValueError('Historical reference must contain SA only')
            metric_snapshot(r)
            token = r['usage']['total_tokens']
            if not isinstance(token, int) or token <= 0:
                raise ValueError('Historical SA budget must be recorded positive actual tokens')
            rs.append(r)
        historical_groups.append({'model': model, 'method': 'sa-mcgs',
                                  'reference_runs': 1, **group_stats(rs)})
    waves, records, visible_hashes = [], [], {}
    expected_cells = {(m, u, method) for m in MODELS for u in uids for method in METHODS}
    for wave_id, directory in specs:
        wave_scope = directory/'run_scope.json'
        if wave_scope.exists():
            ws = read(wave_scope)
            if ws['case_uids'] != uids or ws['cases_per_model'] != N or ws['expected_results'] != 480:
                raise ValueError(f'{wave_id}: frozen scope/order mismatch')
        local_ref = directory/'historical_sa_reference.json'
        if local_ref.exists():
            local_rows = read(local_ref)['rows']
            local_index = {(r['model_key'], r['case_uid']): r for r in local_rows}
            if len(local_rows) != 240 or set(local_index) != expected_ref:
                raise ValueError(f'{wave_id}: historical reference membership mismatch')
            for key, r in reference.items():
                for field in ('metrics', 'usage', 'source_sha256', 'source_n', 'domain', 'completion_status'):
                    if local_index[key][field] != r[field]:
                        raise ValueError(f'{wave_id}: fixed historical SA changed: {field}')
        seen, grouped, issues = set(), collections.defaultdict(list), []
        for path in sorted((directory/'results').glob('*/*/*/final.json')):
            if not wave_scope.exists():
                raise ValueError(f'{wave_id}: results exist without frozen scope')
            r = read(path)
            key = (r['model_key'], r['case_uid'], r['method'])
            path_key = (path.parents[2].name, path.parents[1].name, path.parent.name)
            if key != path_key or key not in expected_cells or key in seen:
                raise ValueError(f'{wave_id}: duplicate, unexpected, or misfiled result')
            seen.add(key)
            ref = reference[key[:2]]
            snapshot = metric_snapshot(r, ref)
            usage = r.get('usage', {})
            actual, cap = usage.get('total_tokens'), r.get('token_budget')
            known = isinstance(actual, int) and not isinstance(actual, bool) and actual >= 0
            if (cap != ref['usage']['total_tokens'] or not known or (known and actual > cap)
                    or usage.get('held_calls', 0) or usage.get('usage_mismatch_calls', 0)
                    or usage.get('accounted_tokens', actual or 0) > cap):
                issues.append({'model': key[0], 'case_uid': key[1], 'method': key[2],
                               'reason': 'budget_or_usage_audit_failed'})
            vh = r.get('visible_input_sha256')
            if vh:
                if key in visible_hashes and visible_hashes[key] != vh:
                    raise ValueError(f'{wave_id}: visible input changed between waves')
                visible_hashes[key] = vh
            item = {'wave_id': wave_id, 'model_key': key[0], 'case_uid': key[1], 'method': key[2],
                    'domain': r['domain'], 'source_n': r['source_n'],
                    'completion_status': r['completion_status'], 'metrics': snapshot,
                    'usage': usage, 'token_budget': cap, 'visible_input_sha256': vh,
                    'source_file': str(path), 'source_sha256': sha(path)}
            grouped[(key[0], key[2])].append(item)
            records.append(item)
        complete = seen == expected_cells
        waves.append({'wave_id': wave_id, 'directory': str(directory),
                      'scope_sha256': sha(wave_scope) if wave_scope.exists() else None,
                      'expected_results': 480, 'terminal_results': len(seen),
                      'missing_results': 480-len(seen), 'complete': complete,
                      'budget_audit_passed': not issues, 'audit_issues': issues,
                      'groups': [{'model': m, 'method': method, **group_stats(grouped[(m, method)])}
                                 for m in MODELS for method in METHODS]})
    ready = all(w['complete'] and w['budget_audit_passed'] for w in waves)
    comparisons = []
    for model in MODELS:
        for method in METHODS:
            gs = [next(g for g in w['groups'] if (g['model'], g['method']) == (model, method)) for w in waves]
            aggregate_metrics = {}
            for metric in (*METRICS, 'compression'):
                values = [g['mean_compression_valid'] if metric == 'compression' else g['metrics_over_planned'][metric] for g in gs]
                defined = ready and all(v is not None for v in values)
                aggregate_metrics[metric] = {'wave_values': values,
                    'mean': statistics.mean(values) if defined else None,
                    'sample_std_ddof1': statistics.stdev(values) if defined else None}
            comparisons.append({'model': model, 'method': method, 'formal_three_wave_ready': ready,
                                'wave_valid_n': [g['valid_cases'] for g in gs],
                                'wave_terminal_n': [g['terminal_cases'] for g in gs],
                                'metrics': aggregate_metrics})
    return {'schema': 'three_wave_strict_aggregate_v1',
            'formal_three_wave_ready': ready, 'planned_waves': 3, 'cases_per_model_per_wave': N,
            'expected_new_results': 1440, 'terminal_new_results': len(records),
            'historical_sa': historical_groups, 'waves': waves, 'comparisons': comparisons,
            'case_results': records,
            'provenance': {'manifest_file': str(manifest_path), 'manifest_sha256': sha(manifest_path),
                           'historical_reference_file': str(ref_path), 'historical_reference_sha256': sha(ref_path),
                           'script_sha256': sha(Path(__file__))},
            'definition_notes': [
                'Each wave hit metric has fixed denominator 80; strict failures contribute zero.',
                'Compression: mean per-case compression among valid cases in each wave, then equal-weight mean and sample std (ddof=1) across exactly three waves.',
                'Compression remains undefined if any wave has zero valid cases; never skip that wave or treat failures as 100% compression.',
                'No formal three-wave mean/std until every wave has 480 final cells and budget/usage audits pass; incomplete-wave rates are progress only.',
                'Historical SA is one fixed main-experiment reference, not three repeats; no SA repeat std is estimated.',
                'Wave1 is the full all80 run, excluding the earlier 10-case pilot. Waves use identical settings (Python/selector seed 42, no explicit server seed): three new samplings, not distinct-seed experiments.',
                'Across-wave std describes run variation on the same fixed cases, not uncertainty from 240 independent cases or a confidence interval.',
                'Raw wave directories are read only. case_results retains every discovered final, including strict/infrastructure failures and its source hash.'
            ]}


def percent(value):
    return '未定义' if value is None else f'{value:.2%}'


def render(report):
    ready = report['formal_three_wave_ready']
    columns = (*METRICS, 'compression')
    historical = {r['model']: r for r in report['historical_sa']}
    baselines = {(r['model'], r['method']): r for r in report['comparisons']}

    def cell(value, std, best, fixed=False):
        if value is None:
            return '未定义'
        number = percent(value)
        if ready and best is not None and math.isclose(value, best, rel_tol=0, abs_tol=1e-12):
            number = f'**{number}**'
        return f"{number} ± {'—' if fixed else percent(std)}"

    lines = ['# 三波全量实验汇总', '',
             f"新基线结果：{report['terminal_new_results']}/1440。正式三波统计：{'已就绪' if report['formal_three_wave_ready'] else '尚未就绪'}。", '',
             '只有三波各480组终态全部到齐且预算审计通过后，才报告正式均值和样本标准差（ddof=1）。', '',
             '| 模型 | 方法 | Risk-all ↑ 均值 ± SD | Root@3 ↑ 均值 ± SD | Risk-any ↑ 均值 ± SD | 压缩率 ↑ 均值 ± SD | 有效 n（SA单次／基线三波） |',
             '|---|---|---:|---:|---:|---:|---|']
    for model in MODELS:
        sa = historical[model]
        sa_values = {**sa['metrics_over_planned'], 'compression': sa['mean_compression_valid']}
        best = {}
        for key in columns:
            values = [sa_values[key]]
            if ready:
                values.extend(baselines[(model, method)]['metrics'][key]['mean'] for method in METHODS)
            best[key] = max((v for v in values if v is not None), default=None)
        cells = [cell(sa_values[key], None, best[key], fixed=True) for key in columns]
        lines.append(f"| {model} | SA（固定主实验） | {' | '.join(cells)} | {sa['valid_cases']}（单次） |")
        for method, label in (('lea', 'LEA（三波）'), ('full-scc', 'Full-SCC（三波）')):
            row = baselines[(model, method)]
            cells = []
            for key in columns:
                m = row['metrics'][key]
                cells.append('待三波完整' if not ready or not row['formal_three_wave_ready'] else
                             cell(m['mean'], m['sample_std_ddof1'], best[key]))
            lines.append(f"| {model} | {label} | {' | '.join(cells)} | {' / '.join(map(str, row['wave_valid_n']))} |")
    lines.extend(['', 'SA为固定的单次主实验结果，SD显示“—”；两个基线显示三波均值±样本SD。',
                  '三波完整后，同一模型内每列最高数值加粗，并列均加粗；比较依据未舍入值。未完整时不标最优。压缩率越高仅表示输出节点越少。'])
    for wave in report['waves']:
        lines.extend(['', f"{wave['wave_id']}：{wave['terminal_results']}/480；预算审计{'通过' if wave['budget_audit_passed'] else '未通过'}。未完整波次的命中率仅为进度。", '',
                      '| 模型 | 方法 | 终态/80 | 有效/80 | Risk-all | Root@3 | Risk-any | 压缩率（仅有效） |',
                      '|---|---|---:|---:|---:|---:|---:|---:|'])
        for row in wave['groups']:
            cells = [percent(row['metrics_over_planned'][k]) for k in METRICS]
            lines.append(f"| {row['model']} | {row['method']} | {row['terminal_cases']} | {row['valid_cases']} | {' | '.join(cells)} | {percent(row['mean_compression_valid'])} |")
    lines.extend(['', '命中率每波固定除以80，严格失败计0。压缩率先逐例计算1−|H|/|SCC|，再每波仅对有效输出求均值；失败不算100%压缩。三波等权汇总，不按有效例数加权。',
                  '均值和SD均显示为百分数（SD的数值单位为百分点）。三波为相同设置下三次新采样，不称不同随机种子的实验；早先10例pilot不计入。这是固定80例上的重复运行波动，不是240个独立样本的置信区间。',
                  '逐波状态、失败、预算审计与逐例来源哈希完整保存在aggregate_summary.json；各波原始文件保持不变。'])
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT/'manifest.json')
    parser.add_argument('--experiments-root', type=Path, default=ROOT.parent)
    parser.add_argument('--output-dir', type=Path, default=ROOT)
    args = parser.parse_args()
    report = aggregate(args.manifest.resolve(), args.experiments_root.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    save(args.output_dir/'aggregate_summary.json', report)
    (args.output_dir/'AGGREGATE_ZH.md').write_text(render(report))
    print(json.dumps({'formal_three_wave_ready': report['formal_three_wave_ready'],
                      'terminal_new_results': report['terminal_new_results'],
                      'summary': str(args.output_dir/'aggregate_summary.json')}))


if __name__ == '__main__':
    main()

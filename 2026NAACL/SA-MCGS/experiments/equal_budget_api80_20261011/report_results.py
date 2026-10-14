#!/usr/bin/env python3
"""Offline merged reporting; never imports clients or alters source results."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent
MODELS = ('gpt-4o', 'gemini-2.5-pro')
METHODS = ('sa-mcgs', 'lea', 'full-scc')
METRICS = ('risk_all', 'root_at_3', 'risk_any', 'compression')
NONTERMINAL = {'pending', 'running', 'in_progress', 'queued', 'not_started', 'interrupted'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def atomic_write(path, text):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.' + path.name + '.', delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def keyed(rows, fields, label):
    result = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in result:
            raise ValueError(f'Duplicate identity in {label}: {key}')
        result[key] = row
    return result


def checked_metrics(metrics):
    result = {}
    for key in METRICS:
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f'Invalid reported metric {key}: {value!r}')
        result[key] = value
    return result


def make_row(reference, method, raw, origin, source, budget):
    """Keep the source record intact; apply empty-output scoring separately."""
    model, uid = reference['model'], reference['case_uid']
    is_reference = method == 'sa-mcgs'
    raw_status = raw.get('status') if raw is not None else None
    if raw is not None and not is_reference and not isinstance(raw_status, str):
        raise ValueError(f'Missing status in final: {model}/{uid}/{method}')
    terminal = is_reference or (raw is not None and raw_status not in NONTERMINAL)
    original_metrics = raw.get('metrics') or {} if raw is not None else {}
    selected = raw.get('selected_result') if raw is not None else None
    valid = bool(terminal and original_metrics.get('valid') is True and
                 (is_reference or isinstance(selected, dict) and bool(selected)))
    if valid:
        reporting_metrics = checked_metrics(original_metrics)
        mapping = 'original_metrics'
    elif terminal:
        reporting_metrics = dict(risk_all=0, root_at_3=0, risk_any=0, compression=1)
        mapping = 'terminal_without_valid_selected_output: compression=1; hit_metrics=0'
    else:
        reporting_metrics = {metric: None for metric in METRICS}
        mapping = 'pending_excluded_from_terminal_denominator'
    return {
        'model': model, 'method': method, 'case_uid': uid,
        'main_case_order': reference['main_case_order'], 'domain': reference['domain'],
        'origin': origin, 'status': raw_status if raw is not None else 'pending',
        'reporting_state': 'valid_output' if valid else ('empty_output' if terminal else 'pending'),
        'terminal': terminal, 'valid_output': valid,
        'metrics': original_metrics, 'reporting_metrics': reporting_metrics,
        'reporting_mapping': mapping,
        'B': raw.get('B') if raw is not None and raw.get('B') is not None else (budget or {}).get('token_cap'),
        'budget_source': budget, 'source': source,
        'historical_sa_reference': {key: reference[key] for key in
                                    ('source_file', 'source_sha256', 'source') if key in reference},
        'usage': raw.get('usage') if raw is not None else None,
        'raw': raw,
    }


def sum_usage(rows):
    """Read cumulative cell usage once, never add virtual_prefix/recovery twice."""
    usages = [row['usage'] for row in rows if row['terminal'] and isinstance(row['usage'], dict)]
    fields = ('prompt_tokens', 'completion_tokens', 'total_tokens', 'held_tokens',
              'accounted_tokens', 'calls', 'unknown_failure_calls', 'missing_usage_calls')
    result = {'cells_with_usage': len(usages), 'scope': 'terminal baseline cells only; pending usage excluded',
              'cost_is_estimate': True, 'source': 'top-level cumulative cell usage; nested prefixes not added'}
    for field in fields:
        values = [u[field] for u in usages if isinstance(u.get(field), (int, float))]
        result[field] = sum(values) if values else None
        result[field + '_cells'] = len(values)
    costs = []
    for usage in usages:
        value = next((usage[key] for key in ('estimated_cost_usd', 'estimated_usd', 'actual_usd')
                      if isinstance(usage.get(key), (int, float))), None)
        if value is not None:
            costs.append(value)
    result['estimated_cost_usd'] = sum(costs) if costs else None
    result['cost_cells'] = len(costs)
    return result


def _report(root, output_dir):
    references = read(root / 'main_sa_references.json')
    plans = read(root / 'case_plans.json')
    pilot = read(root / 'pilot_results.json')
    budget_file = root / 'budgets.json'
    budgets = read(budget_file if budget_file.exists() else root / 'budget_sources.json')
    refs = keyed(references, ('model', 'case_uid'), 'historical SA references')
    pilot_map = keyed(pilot, ('model', 'case_uid', 'method'), 'pilot')
    budget_map = keyed(budgets, ('model', 'case_uid'), 'budgets')
    plan_map = keyed([row for model in MODELS for row in plans[model]],
                     ('model', 'case_uid'), 'new case plans')
    if len(references) != 160 or len(pilot) != 40 or len(plan_map) != 140:
        raise ValueError('Expected 160 SA references, 40 pilot cells and 140 new model/case plans')
    for model in MODELS:
        all_uids = {uid for m, uid in refs if m == model}
        new_uids = {uid for m, uid in plan_map if m == model}
        if len(all_uids) != 80 or len(new_uids) != 70:
            raise ValueError(f'Invalid planned scope for {model}')
        for method in METHODS[1:]:
            old_uids = {uid for m, uid, k in pilot_map if m == model and k == method}
            if len(old_uids) != 10 or old_uids & new_uids or old_uids | new_uids != all_uids:
                raise ValueError(f'Pilot/new UID partition mismatch for {model}/{method}')
    if set(budget_map) != set(plan_map):
        raise ValueError('Budget identities do not match the new case plans')

    new_map, source_map = {}, {}
    for path in sorted((root / 'results').glob('*/*/*/final.json')):
        raw = read(path)
        key = (raw['model'], raw['case_uid'], raw['method'])
        model, uid, method = key
        if (model, uid) not in plan_map or method not in METHODS[1:]:
            raise ValueError(f'Unexpected new final identity: {key}')
        planned = plan_map[model, uid]
        expected = root / 'results' / model / f"{planned['case_slot']:02d}" / method / 'final.json'
        if path != expected or raw.get('domain', planned['domain']) != planned['domain']:
            raise ValueError(f'Final path/domain does not match planned identity: {path}')
        if key in new_map or key in pilot_map:
            raise ValueError(f'Duplicate result identity: {key}')
        new_map[key] = raw
        source_map[key] = {'path': str(path), 'sha256': sha(path)}

    pilot_source = {'path': str(root / 'pilot_results.json'), 'sha256': sha(root / 'pilot_results.json')}
    ref_source = {'path': str(root / 'main_sa_references.json'), 'sha256': sha(root / 'main_sa_references.json')}
    rows = []
    for model in MODELS:
        ordered = sorted((row for row in references if row['model'] == model),
                         key=lambda row: row['main_case_order'])
        for reference in ordered:
            uid = reference['case_uid']
            rows.append(make_row(reference, 'sa-mcgs', reference, 'fixed_historical_sa', ref_source, None))
            for method in METHODS[1:]:
                key = model, uid, method
                if key in pilot_map:
                    raw, origin, source = pilot_map[key], 'retained_pilot10', pilot_source
                    budget = {'budget_source': 'retained_pilot_budget_and_reporting_adjustments',
                              'token_cap': raw.get('B'),
                              'historical_main_actual_token_match': False}
                else:
                    raw, origin = new_map.get(key), 'remaining70'
                    source = source_map.get(key)
                    budget = budget_map[model, uid]
                rows.append(make_row(reference, method, raw, origin, source, budget))
    keyed(rows, ('model', 'case_uid', 'method'), 'merged output')

    groups = []
    for model in MODELS:
        for method in METHODS:
            cells = [row for row in rows if row['model'] == model and row['method'] == method]
            terminal = [row for row in cells if row['terminal']]
            complete = len(terminal) == 80
            averages = {metric: (sum(row['reporting_metrics'][metric] for row in terminal) / len(terminal)
                                 if terminal else None) for metric in METRICS}
            groups.append({'model': model, 'method': method, 'planned': 80,
                           'terminal': len(terminal), 'pending': 80 - len(terminal),
                           'valid_outputs': sum(row['valid_output'] for row in terminal),
                           'empty_outputs': sum(not row['valid_output'] for row in terminal),
                           'complete': complete, 'status_counts': dict(Counter(row['status'] for row in cells)),
                           'metric_denominator': len(terminal), 'terminal_metrics': averages,
                           'full80_metrics': averages if complete else {metric: None for metric in METRICS},
                           'usage': sum_usage(cells) if method != 'sa-mcgs' else None})
    baselines = [row for row in rows if row['method'] != 'sa-mcgs']
    new_rows = [row for row in baselines if row['origin'] == 'remaining70']
    summary = {
        'schema_version': 'equal_budget_api80.reporting.v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'complete': all(row['terminal'] for row in baselines),
        'baseline_cells': {'planned': 320, 'terminal': sum(row['terminal'] for row in baselines),
                           'pending': sum(not row['terminal'] for row in baselines),
                           'valid_outputs': sum(row['valid_output'] for row in baselines),
                           'empty_outputs': sum(row['terminal'] and not row['valid_output'] for row in baselines)},
        'new_baseline_cells': {'planned': 280, 'terminal': sum(row['terminal'] for row in new_rows),
                               'pending': sum(not row['terminal'] for row in new_rows)},
        'historical_sa_cells': 160, 'retained_pilot_cells': 40, 'groups': groups,
        'scoring_policy': 'All terminal cells enter every metric denominator. No valid selected output: '
                          'compression=1 and risk/root hits=0. Pending cells are not failures; '
                          'full80_metrics remain null until all 80 terminal cells exist.',
        'budget_policy': 'Audited token ceilings where recorded; otherwise frozen same-model, same-domain '
                         'mean ceilings. Not historical-main-SA actual-token matching. '
                         'Pilot reporting adjustments remain in raw records.',
        'usage': sum_usage(baselines), 'budget_allocations': budgets,
        'inputs': {name: {'path': str(root / name), 'sha256': sha(root / name)} for name in
                   ('main_sa_references.json', 'case_plans.json', 'pilot_results.json',
                    budget_file.name if budget_file.exists() else 'budget_sources.json')},
    }
    text = encode(rows)
    summary['case_results_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    summary['case_results_file'] = str(output_dir / 'case_results.json')
    counts = summary['baseline_cells']
    state = '全量已终态' if summary['complete'] else '阶段结果，尚未全量完成'
    lines = [f"{state}：基线 {counts['terminal']}/320 项已终态（有效输出 {counts['valid_outputs']}，"
             f"空输出 {counts['empty_outputs']}），待完成 {counts['pending']}；历史 SA 固定 160 项。",
             '下表以各行已终态案例为分母，包含全部失败；待完成不计失败。不同完成数量的行暂不能直接当作全量对比。', '',
             '| 模型 | 方法 | 已终态/计划 | Risk-all | Root@3 | Risk-any | 压缩率 |',
             '|---|---|---:|---:|---:|---:|---:|']
    labels = {'sa-mcgs': 'SA-MCGS（历史）', 'lea': 'LEA', 'full-scc': 'Full-SCC'}
    for group in groups:
        values = ['—' if group['terminal_metrics'][metric] is None else
                  f"{group['terminal_metrics'][metric] * 100:.2f}%" for metric in METRICS]
        lines.append(f"| {group['model']} | {labels[group['method']]} | {group['terminal']}/80 | "
                     + ' | '.join(values) + ' |')
    lines += ['', '空输出按压缩率 100%、三个命中指标 0 计分；原始状态、结果和历史调整保留在 case_results.json。',
              '新增预算使用已有审计值或同模型同领域均值估计，并保留逐例来源；不是主实验 SA 逐例实际 token 对齐。']
    cost = summary['usage']['estimated_cost_usd']
    if cost is not None:
        lines.append(f"已终态基线的已知用量费用估计 ${cost:.2f}；不含在途用量及失败请求未知账单。")
    atomic_write(output_dir / 'case_results.json', text)
    atomic_write(output_dir / 'RESULTS_ZH.md', '\n'.join(lines) + '\n')
    atomic_write(output_dir / 'summary.json', encode(summary))
    return summary


def report(root=ROOT, output_dir=None):
    root = Path(root).resolve()
    output_dir = Path(output_dir).resolve() if output_dir is not None else root / 'reports'
    output_dir.mkdir(parents=True, exist_ok=True)
    # Serialize callers before reading finals, so an older snapshot cannot win a race.
    with (output_dir / '.report.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _report(root, output_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    summary = report(args.root, args.output_dir)
    print(json.dumps({'complete': summary['complete'], 'baseline_cells': summary['baseline_cells'],
                      'new_baseline_cells': summary['new_baseline_cells']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

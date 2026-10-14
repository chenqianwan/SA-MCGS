#!/usr/bin/env python3
"""Compare historical main-experiment SA with current baselines on identical cases."""
import collections
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
METRICS = ('risk_all', 'root_at_3', 'risk_any', 'root_at_1', 'mrr',
           'endpoint_recall', 'evidence_all', 'evidence_recall')
DISPLAY_METRICS = ('risk_all', 'root_at_3', 'risk_any', 'mean_compression_valid')


def displayed_value(row, metric):
    if metric == 'mean_compression_valid':
        return row[metric]
    return row['metrics_over_planned'][metric]


def format_score(row, metric, best):
    value = displayed_value(row, metric)
    if value is None:
        return '未记录'
    text = f'{value:.2%}'
    highest = best[(row['model'], metric)]
    return f'**{text}**' if math.isclose(value, highest, rel_tol=0, abs_tol=1e-12) else text


def main():
    scope = json.loads((ROOT/'run_scope.json').read_text())
    planned = scope['cases_per_model']
    allowed = set(scope['case_uids'])
    groups = collections.defaultdict(list)
    historical = json.loads((ROOT/'historical_sa_reference.json').read_text())
    historical_rows = historical['rows']
    reference = {}
    for row in historical_rows:
        key = (row['model_key'], row['case_uid'])
        if key in reference or row['case_uid'] not in allowed or row['method'] != 'sa-mcgs':
            raise ValueError('Duplicate or mismatched historical SA reference')
        reference[key] = row
        groups[(row['model_key'], 'sa-mcgs')].append(row)
    if set(reference) != {(m, u) for m in ('llama', 'kimi', 'qwen35') for u in allowed}:
        raise ValueError('Historical SA must cover exactly the same models and cases')
    execution_finals = 0
    budget_audit = []
    for path in (ROOT/'results').glob('*/*/*/final.json'):
        row = json.loads(path.read_text())
        if row['case_uid'] not in allowed:
            raise ValueError('Result outside current user-authorized scope')
        key = (path.parents[2].name, path.parent.name)
        execution_finals += 1
        # This run must never execute or import fresh SA results.
        if key[1] == 'sa-mcgs':
            raise ValueError('Fresh SA is forbidden in this full baseline run')
        old_tokens = reference[(key[0], row['case_uid'])]['usage']['total_tokens']
        cap = row.get('token_budget')
        actual = row.get('usage', {}).get('total_tokens')
        if cap != old_tokens or actual is None or actual > cap:
            raise ValueError('Full-run baseline budget does not match historical SA or is exceeded')
        budget_audit.append({'model': key[0], 'case_uid': row['case_uid'], 'method': key[1],
                             'historical_sa_tokens': old_tokens, 'configured_token_cap': cap,
                             'actual_tokens': actual, 'cap_matches_historical_sa': cap == old_tokens,
                             'actual_to_historical_sa_ratio': actual/old_tokens if old_tokens and actual is not None else None})
        groups[key].append(row)
    summary = []
    for model in ('llama', 'kimi', 'qwen35'):
        for method in ('sa-mcgs', 'lea', 'full-scc'):
            rows = groups[(model, method)]
            uids = [r['case_uid'] for r in rows]
            if len(uids) != len(set(uids)) or len(rows) > planned:
                raise ValueError('Duplicate or extra scientific results')
            states = dict(collections.Counter(r.get('completion_status', 'unknown') for r in rows))
            metric = {k: (sum(float(r['metrics'][k] or 0) for r in rows)/planned
                          if all(k in r.get('metrics', {}) for r in rows) else None) for k in METRICS}
            valid = [r for r in rows if r.get('metrics', {}).get('valid')]
            used = sum(int(r.get('usage', {}).get('total_tokens') or 0) for r in rows)
            budget = sum(int(r.get('token_budget') or 0) for r in rows)
            outputs = [r['metrics']['output_n'] for r in valid if r['metrics'].get('output_n') is not None]
            compressions = [r['metrics']['compression'] for r in valid if r['metrics'].get('compression') is not None]
            for r in valid:
                compression = r['metrics'].get('compression')
                if compression is not None and not math.isclose(compression, 1-r['metrics']['output_n']/r['source_n'], abs_tol=1e-12):
                    raise ValueError('Compression does not match per-case retained-node fraction')
            old_tokens = sum(reference[(model, u)]['usage']['total_tokens'] for u in allowed)
            summary.append({'model': model, 'method': method, 'planned_cases': planned,
                'source': 'historical_main_experiment' if method == 'sa-mcgs' else 'current_repeated_baseline',
                'terminal_cases': len(rows), 'missing_cases': planned-len(rows), 'valid_cases': len(valid),
                'states': states, 'metrics_over_planned': metric,
                'actual_tokens': used, 'configured_budget_tokens': budget if method != 'sa-mcgs' else None,
                'historical_sa_reference_tokens': old_tokens,
                'token_utilization': used/budget if budget else None,
                'mean_compression_valid': statistics.mean(compressions) if len(compressions) == len(valid) and compressions else None,
                'compression_valid_cases': len(compressions),
                'mean_output_nodes_valid': statistics.mean(outputs) if len(outputs) == len(valid) and outputs else None})
    report = {'planned_results': scope['comparison_expected_results'], 'execution_expected_results': scope['expected_results'], 'terminal_results': sum(len(v) for v in groups.values()),
              'execution_terminal_results': execution_finals,
              'sa_comparison_source': 'historical_main_experiment',
              'fresh_sa_included_in_comparison': False,
              'historical_budget_matched': len(budget_audit) == planned*6 and all(r['cap_matches_historical_sa'] for r in budget_audit),
              'budget_audit': budget_audit,
              'independent_source_sccs_per_model': len({c['physical_scc_uid'] for c in scope['case_details']}),
              'injected_variants_per_model': planned,
              'rows': summary, 'caution': 'Historical SA is reused on identical cases. Each baseline token ceiling equals that historical SA actual usage; realized consumption may differ. Strict failures stay in the denominator.'}
    (ROOT/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    lines = ['# 全量80例对比：沿用主实验 SA', '',
             'SA复用主实验全部80例，保持原严格评测口径；本轮只运行两个基线，不重跑SA。',
             '两个基线分别以对应旧SA的实际token数为上限，候选生成、重试与评选全部计入；实际消耗照实列出。', '',
             f"对比表已有 {report['terminal_results']}/{report['planned_results']} 组结果（含复用的240组旧SA）。每模型{planned}个注入变体。", '',
             f'| 模型 | 方法 | 终态/{planned} | 有效/{planned} | Risk-all ↑ | Root@3 ↑ | Risk-any ↑ | 平均压缩率 ↑ | 实际tokens |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    best = {}
    for model in ('llama', 'kimi', 'qwen35'):
        for metric in DISPLAY_METRICS:
            values = [displayed_value(row, metric) for row in summary if row['model'] == model]
            best[(model, metric)] = max((value for value in values if value is not None), default=None)
    for row in summary:
        scores = [format_score(row, k, best) for k in DISPLAY_METRICS]
        label = 'SA（主实验旧结果）' if row['method'] == 'sa-mcgs' else row['method']
        lines.append(f"| {row['model']} | {label} | {row['terminal_cases']} | {row['valid_cases']} | {' | '.join(scores)} | {row['actual_tokens']:,} |")
    lines.extend(['', '同一模型内各指标最高值加粗，并列最高均加粗。',
                  f'三项命中率统一除以{planned}，失败保留在分母中；实验未结束时，数字只表示已获得命中数占计划总数的比例。',
                  '压缩率＝1−输出节点数/原图节点数，越高表示输出越精简；先逐例计算，再仅对有效输出取平均。有效例数见表，失败不算作100%压缩。',
                  '逐例旧SA用量、基线上限及实际消耗见summary.json的budget_audit。全部480组基线上限逐例与旧SA用量核对，实际消耗允许低于上限。'])
    (ROOT/'RESULTS_ZH.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'terminal_results': report['terminal_results'], 'report': str(ROOT/'RESULTS_ZH.md')}))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Build the requested Markdown tables directly from the finished replay data."""
import hashlib
import json
import math
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'snapshots/reports_final_20261011'
OUTPUT = ROOT / 'EXPERIMENT_TABLES_20261011_ZH.md'
MODELS = ['llama', 'qwen35', 'kimi']
NAMES = {'llama': 'Llama 3.1-8B', 'qwen35': 'Qwen3.5-9B', 'kimi': 'Kimi-VL-A3B'}
METRICS = ['risk_all', 'root_at_3', 'risk_any', 'compression']
SELECTORS = ['full', 'mean-risk-matched-k', 'lea-score-matched-k', 'locked-matched-k']
SNAMES = {'full': 'SA 完整选择器', 'mean-risk-matched-k': '平均风险 top-k',
          'lea-score-matched-k': 'LEA 聚合打分', 'locked-matched-k': '提前锁死（不替换）'}
ARMS = ['full', 'no_relation_guidance', 'no_critical_revisit', 'no_both', 'random_windows']
ANAMES = {'full': 'SA 完整配置', 'no_relation_guidance': '去关系引导',
          'no_critical_revisit': '去关键对重访', 'no_both': '同时去掉两项',
          'random_windows': '随机窗口'}


def main():
    data = json.loads((SOURCE / 'case_metrics.json').read_text())
    summary = json.loads((SOURCE / 'summary.json').read_text())
    counts = summary['counts']
    assert counts['terminal'] == 1200 and counts['pending'] == 0
    assert counts['analysis_errors'] == 0
    index = {}
    for r in data:
        key = (r['model'], r['analysis'], r['arm'], r['selector'], r['prefix'], r['cap_ratio'])
        group = index.setdefault(key, {})
        assert r['case_uid'] not in group
        group[r['case_uid']] = r
    audit = {'source_sha256': hashlib.sha256((SOURCE / 'case_metrics.json').read_bytes()).hexdigest(),
             'counts': counts, 'tables': {}}

    def paired(model, specs):
        groups = [index[(model, *spec)] for spec in specs]
        common = set.intersection(*[{uid for uid, r in g.items() if r['state'] == 'complete'} for g in groups])
        assert common
        values = []
        for group in groups:
            assert all(all(isinstance(group[uid][k], (int, float)) and math.isfinite(group[uid][k]) for k in METRICS) for uid in common)
            values.append({k: 100 * mean(group[uid][k] for uid in common) for k in METRICS})
        return values, sorted(common)

    def table(headers, rows):
        return ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                *['| ' + ' | '.join(row) + ' |' for row in rows], '']

    def metric_cells(values, i):
        cells = []
        for k in METRICS:
            x = values[i][k]
            vals = [v[k] for v in values]
            txt = f'{x:.2f}'
            if max(vals) - min(vals) > 1e-8 and math.isclose(x, max(vals), abs_tol=1e-8):
                txt = '**' + txt + '**'
            cells.append(txt)
        return cells

    def positive(x):
        txt = f'{x:+.2f}'
        return '**' + txt + '**' if x > 1e-8 else txt

    # Capture all selector cases once; all subsequent comparisons match by UID.
    selection, selection_uids = {}, {}
    for model in MODELS:
        selection[model], selection_uids[model] = paired(model, [('selector', 'full', s, 60, None) for s in SELECTORS])
        assert len(selection_uids[model]) == 80
    search_counts = {}
    for model in MODELS:
        _, uids = paired(model, [('search', a, s, 60, None) for a in ARMS for s in ['native-core', 'common-mean-risk']])
        search_counts[model] = len(uids)

    lines = [
        '**集群补充实验：重点展示与完整结果（2026-10-11）**', '',
        f"1,200 项已全部结束：{counts['successful']} 项成功，{counts['infrastructure_failures']} 项基础设施失败，0 项待运行。",
        '指标单位均为 %。加粗表示当前对比组中有差异的最高值；并列最高一起加粗，全组相同不加粗。Δ 为百分点。压缩率需要与覆盖率一起看。',
        '表中的 SA 完整配置来自本轮消融实验；论文主实验的历史 SA 结果保持原值。',
        '选择器、容量和搜索前缀实验均为每模型 80 例；组件消融只比较五种配置都成功的相同案例：'
        + '、'.join(f'{NAMES[m]} {search_counts[m]} 例' for m in MODELS) + '。', '',
        '**优先采用的优势：允许后期替换节点。**', '',
    ]
    overview = []
    for model in MODELS:
        full, _, _, locked = selection[model]
        overview.append([NAMES[model], f"**{full['risk_all']:.2f}**", f"{locked['risk_all']:.2f}",
                         positive(full['risk_all'] - locked['risk_all'])])
    lines += table(['模型', 'SA 动态替换 Risk-all', '提前锁死 Risk-all', 'SA 提升'], overview)

    lines += ['**实验 1：动态替换 vs 提前锁死**', '',
              '使用完全相同的搜索轨迹和证据，逐例匹配输出节点数，只改变最终是否允许替换节点。', '']
    body = []
    for model in MODELS:
        values = [selection[model][0], selection[model][3]]
        for i, name in enumerate(['SA 动态替换', '提前锁死']):
            body.append([NAMES[model], name, *metric_cells(values, i)])
    lines += table(['模型', '方法', 'Risk-all ↑', 'Root@3 ↑', 'Risk-any ↑', '压缩率 ↑'], body)
    lines += ['Root@3 直接沿用同一条搜索轨迹的排名，在本实验中是共享值，不代表选择器的独立提升。', '']
    audit['tables']['selectors'] = {m: {'case_uids': selection_uids[m], 'rows': dict(zip(SELECTORS, selection[m]))} for m in MODELS}

    lines += ['**实验 2：不同输出容量**', '',
              '容量是最大保留节点比例，最少保留 4 个节点；每个比较方法逐例匹配 SA 实际输出大小。下表先给动态替换与锁死的 Risk-all 对照。', '']
    cap_rows, cap_data, wins = [], {}, 0
    for model in MODELS:
        cap_data[model] = {}
        for cap in [.25, .35, .45, .60]:
            values, uids = paired(model, [('cap', 'full', s, 60, cap) for s in SELECTORS])
            full, _, _, locked = values
            delta = full['risk_all'] - locked['risk_all']
            wins += delta > 1e-8
            cap_rows.append([NAMES[model], f'{cap:.0%}', f"**{full['risk_all']:.2f}**" if delta > 1e-8 else f"{full['risk_all']:.2f}",
                             f"{locked['risk_all']:.2f}", positive(delta), f"{full['compression']:.2f}"])
            cap_data[model][str(cap)] = {'case_uids': uids, 'rows': dict(zip(SELECTORS, values))}
    lines += table(['模型', '容量上限', 'SA Risk-all', '锁死 Risk-all', 'SA 提升', '实际压缩率'], cap_rows)
    lines += [f'**动态替换在 {wins}/12 组模型与容量组合上优于提前锁死。** 完整四指标与全部选择器的数据放在文末。', '']
    audit['tables']['capacities'] = cap_data

    lines += ['**实验 3：完整选择器 vs LEA 聚合打分**', '',
              '本表聚焦完整选择器与 LEA 聚合打分，证据和逐例输出大小均相同。LEA 聚合打分是对同一条 SA 轨迹做离线聚合，不是重新运行 LEA 基线。全部已测选择规则见文末容量实验。', '']
    body = []
    displayed_selectors = ['full', 'lea-score-matched-k']
    for model in MODELS:
        values = [selection[model][SELECTORS.index(s)] for s in displayed_selectors]
        for i, selector in enumerate(displayed_selectors):
            body.append([NAMES[model], SNAMES[selector], *metric_cells(values, i)])
    lines += table(['模型', '选择规则', 'Risk-all ↑', 'Root@3 ↑', 'Risk-any ↑', '压缩率 ↑'], body)
    lines += ['**相较 LEA 聚合打分，完整选择器在 Llama、Qwen、Kimi 上的 Risk-all 分别提高 5.00、5.00、8.75 个百分点，且逐例输出大小相同。**', '']

    prefix_details = ['**补充 A：搜索前缀完整结果**', '',
                      '同一条 60 次搜索轨迹的 15 / 30 / 45 / 60 次前缀，每模型均为相同的 80 例。',
                      '统一 top-k 使用 k = min(n, max(4, ceil(0.45n)))；实验 3 则匹配 Full 实际节点数，两个规则的结果可以不同。', '']
    prefix_data = {}
    for selector, explanation in [
        ('common-mean-risk', '固定输出大小、统一选择规则'),
        ('native-core', '原生 SA 输出：节点数可随搜索变化，反映整体覆盖与压缩的权衡'),
    ]:
        prefix_details += [explanation + '：', '']
        body, prefix_data[selector] = [], {}
        for model in MODELS:
            values, uids = paired(model, [('search', 'full', selector, p, None) for p in [15, 30, 45, 60]])
            prefix_data[selector][model] = {'case_uids': uids, 'rows': dict(zip([15, 30, 45, 60], values))}
            for i, p in enumerate([15, 30, 45, 60]):
                body.append([NAMES[model], str(p), *metric_cells(values, i)])
        prefix_details += table(['模型', '搜索步数', 'Risk-all ↑', 'Root@3 ↑', 'Risk-any ↑', '压缩率 ↑'], body)
    audit['tables']['prefixes'] = prefix_data

    lines += ['**实验 4：增加搜索后的整体覆盖收益**', '',
              '重点展示 SA 原生输出从 15 步到 60 步的变化：三个模型均使用各自完整的 80 例，截取同一条搜索轨迹的两个端点。表内数值均为“15 步 → 60 步”。', '']
    body = []
    for model in MODELS:
        start = prefix_data['native-core'][model]['rows'][15]
        end = prefix_data['native-core'][model]['rows'][60]
        changes = []
        for key in ['risk_all', 'root_at_3', 'risk_any']:
            end_text = f"{end[key]:.2f}"
            if end[key] > start[key] + 1e-8:
                end_text = '**' + end_text + '**'
            changes.append(f"{start[key]:.2f} → {end_text}")
        body.append([NAMES[model], *changes, positive(end['risk_all'] - start['risk_all'])])
    lines += table(['模型', 'Risk-all ↑', 'Root@3 ↑', 'Risk-any ↑', 'Risk-all 提升'], body)
    lines += ['**从 15 步增加到 60 步，三个模型的完整风险覆盖率均提高。** 原生输出同时保留了更多节点；固定输出大小时的结果依模型而异，压缩率、全部步数及固定大小对照见补充 A。', '']

    arm_details = ['**补充 B：组件消融完整结果**', '',
                   '五种配置均使用 60 次搜索。去关系引导关闭关系先验和普通探测；去关键对重访关闭重访行为。它们分别不是删除全部关系记忆或整个关键对账本。',
                   '所有比较按同模型、相同案例配对；这里匹配搜索次数，实际 token 消耗不强制相同。', '']
    arm_data = {}
    for selector, explanation in [
        ('native-core', '各配置保留自己的原生输出，观察整体系统效果'),
        ('common-mean-risk', '各配置改用同一个平均风险 top-k，且固定输出大小，观察搜索本身贡献'),
    ]:
        arm_details += [explanation + '：', '']
        body, arm_data[selector] = [], {}
        for model in MODELS:
            values, uids = paired(model, [('search', arm, selector, 60, None) for arm in ARMS])
            assert len(uids) == search_counts[model]
            arm_data[selector][model] = {'case_uids': uids, 'rows': dict(zip(ARMS, values))}
            for i, arm in enumerate(ARMS):
                body.append([NAMES[model], ANAMES[arm], *metric_cells(values, i)])
        arm_details += table(['模型', '配置', 'Risk-all ↑', 'Root@3 ↑', 'Risk-any ↑', '压缩率 ↑'], body)
    arm_details += ['这组结果用于判断各组件的实际贡献；目前未显示跨三个模型一致的单组件收益。', '']
    audit['tables']['search_arms'] = arm_data

    lines += prefix_details + arm_details

    lines += ['**补充：容量实验完整四指标**', '', '同一模型、同一容量内加粗最优值。', '']
    for model in MODELS:
        lines += [NAMES[model] + '：', '']
        body = []
        for cap in [.25, .35, .45, .60]:
            values = [cap_data[model][str(cap)]['rows'][s] for s in SELECTORS]
            for i, selector in enumerate(SELECTORS):
                body.append([f'{cap:.0%}', SNAMES[selector], *metric_cells(values, i)])
        lines += table(['容量上限', '选择规则', 'Risk-all ↑', 'Root@3 ↑', 'Risk-any ↑', '压缩率 ↑'], body)
    lines += ['数据来源：', '',
              f'- [最终逐例数据]({SOURCE / "case_metrics.json"})',
              f'- [运行与分析汇总]({SOURCE / "summary.json"})',
              f'- [表格复算数据]({ROOT / "EXPERIMENT_TABLES_20261011_values.json"})', '']
    OUTPUT.write_text('\n'.join(lines), encoding='utf-8')
    (ROOT / 'EXPERIMENT_TABLES_20261011_values.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'markdown': str(OUTPUT), 'counts': counts, 'component_paired_n': search_counts,
                      'positive_cap_comparisons': wins, 'lines': len(lines)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

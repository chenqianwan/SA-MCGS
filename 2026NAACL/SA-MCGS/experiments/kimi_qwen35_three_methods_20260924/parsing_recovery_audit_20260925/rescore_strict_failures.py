#!/usr/bin/env python3
"""User-requested metricwise rescore of strict failures only; no model calls.

Successful case metrics are copied verbatim from the prior audited analysis.
Each group always has denominator 80, including compression. Missing values
are zero. Original results, cached responses, and scientific code are read only.
"""
from __future__ import annotations

import ast
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace

from prefix_json import audit_json_prefix

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
MODELS = {'kimi': 'kimi-vl-a3b-instruct', 'qwen35': 'qwen3_5-9b'}
METRICS = ('root_at3', 'risk_any', 'risk_all', 'compression')
SCHEMA_KEYS = {'global_ranking', 'risk_subgraph_nodes', 'risk_subgraph',
               'risk_factor_distribution', 'risk_subgraph_rationale',
               'risk_subgraph_edges', 'clause_evaluations', 'conflicts'}
INPUT_HASHES = {}


def read_bytes(path):
    data = path.read_bytes()
    INPUT_HASHES[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def read_json(path):
    return json.loads(read_bytes(path))


def original_id_helpers():
    """Reuse only the frozen pure ID/alias helpers without importing the runner."""
    source = read_bytes(EXPERIMENT / 'runner/repo/experiments/cross_domain/run_cross_domain_battle.py').decode()
    names = {'_extract_ranked_node_id', '_normalize_node_alias', '_build_node_alias_map'}
    selected = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(selected) == len(names)
    tree = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *selected], type_ignores=[])
    scope = {'re': re}
    exec(compile(ast.fix_missing_locations(tree), '<frozen-id-helpers>', 'exec'), scope)
    return scope


def walk(node, path='$'):
    yield path, node
    if node.get('kind') == 'object':
        for key, child in node.get('fields', {}).items():
            yield from walk(child, path + '.' + key)
    elif node.get('kind') == 'array':
        for i, child in enumerate(node.get('items', [])):
            yield from walk(child, path + f'[{i}]')


def marker_field(root, name):
    """Accept a unique literal schema label misplaced inside a JSON array.

    No prose/string parsing: subsequent fully closed JSON values form the
    segment, ending at another schema label or the containing array's end.
    """
    found = []
    for path, node in walk(root):
        if node.get('kind') != 'array':
            continue
        items = node.get('items', [])
        for i, item in enumerate(items):
            if item.get('complete') and item.get('usable') and item.get('value') == name:
                end = len(items)
                delimited = False
                for j in range(i + 1, len(items)):
                    value = items[j].get('value')
                    if isinstance(value, str) and value in SCHEMA_KEYS:
                        end, delimited = j, True
                        break
                segment = items[i + 1:end]
                complete = bool(delimited or node.get('complete')) and all(x.get('complete') and x.get('usable') for x in segment)
                if len(segment) == 1 and segment[0].get('kind') == 'array':
                    found.append((path + f'[{i}]::marker[0]', segment[0]))
                    continue
                for offset, child in enumerate(segment):
                    value = child.get('value')
                    shaped = isinstance(value, str) or (
                        isinstance(value, dict) and any(isinstance(value.get(k), str)
                        for k in ('clause_id', 'node_id', 'id', 'package_id', 'category_id', 'company_id')))
                    if not (child.get('complete') and child.get('usable') and shaped):
                        segment = segment[:offset]
                        complete = False
                        break
                found.append((path + f'[{i}]::marker', {'kind': 'array', 'items': segment,
                              'complete': complete, 'usable': complete,
                              'marker_repair': True,
                              'start': segment[0].get('start') if segment else None,
                              'end': segment[-1].get('end') if segment else None}))
    return found[0] if len(found) == 1 else (None, None)


def locate(root, name):
    fields = root.get('fields', {}) if root.get('kind') == 'object' else {}
    if name in fields:
        return '$.' + name, fields[name]
    if name == 'risk_subgraph_nodes' and 'risk_subgraph' in fields:
        sub = fields['risk_subgraph']
        if sub.get('kind') == 'array':
            return '$.risk_subgraph', sub
        if sub.get('kind') == 'object':
            for key in ('nodes', 'node_ids', 'clause_ids'):
                candidate = sub.get('fields', {}).get(key)
                if candidate is not None and candidate.get('value') not in (None, []):
                    return '$.risk_subgraph.' + key, candidate
                if candidate is not None and not candidate.get('complete'):
                    return '$.risk_subgraph.' + key, candidate
    found = [(path + '.' + name, node['fields'][name]) for path, node in walk(root)
             if node.get('kind') == 'object' and name in node.get('fields', {})]
    if len(found) == 1:
        return found[0]
    if found:
        return None, None
    return marker_field(root, name)


def values(node, allow_string=False):
    if not node:
        return [], False
    if node.get('kind') == 'array':
        entries = [(i, item['value']) for i, item in enumerate(node.get('items', []))
                   if item.get('complete') and item.get('usable') and 'value' in item]
        return entries, bool(node.get('complete') and node.get('usable'))
    if allow_string and node.get('kind') == 'string' and node.get('complete') and node.get('usable'):
        return list(enumerate(x.strip() for x in re.split(r'[,;\n]+', node['value']) if x.strip())), True
    return [], False


def evaluate(content, case, clauses, helpers):
    parsed = audit_json_prefix(content)
    root = parsed.get('root') or {}
    rank_path, rank_node = locate(root, 'global_ranking')
    risk_path, risk_node = locate(root, 'risk_subgraph_nodes')
    rank_values, rank_closed = values(rank_node)
    risk_values, risk_closed = values(risk_node, allow_string=True)
    ids = case['planned_scc_clause_ids']
    allowed = set(ids)
    aliases = helpers['_build_node_alias_map'](clauses, ids)

    def resolve(item):
        raw = helpers['_extract_ranked_node_id'](item)
        cid = raw if raw in allowed else aliases.get(helpers['_normalize_node_alias'](raw)) if raw else None
        return raw, cid

    ranking, seen, rank_invalid, rank_duplicates, rank_defaults = [], set(), [], [], []
    for position, item in rank_values:
        raw, cid = resolve(item)
        if cid not in allowed:
            rank_invalid.append(raw)
            continue
        if cid in seen:
            rank_duplicates.append(cid)
            continue
        seen.add(cid)
        try:
            rank_float = float(item.get('rank')) if isinstance(item, dict) else position + 1
            if not math.isfinite(rank_float):
                raise ValueError('nonfinite rank')
            rank = int(rank_float)
        except (TypeError, ValueError, OverflowError):
            rank = position + 1
            rank_defaults.append(position)
        ranking.append((rank, position, cid))
    ranking.sort()
    ranked_ids = [x[2] for x in ranking]
    risk_ids, risk_invalid, risk_duplicates = [], [], []
    for _, item in risk_values:
        raw, cid = resolve(item)
        if cid not in allowed:
            risk_invalid.append(raw)
        elif cid in risk_ids:
            risk_duplicates.append(cid)
        else:
            risk_ids.append(cid)

    # Ground truth is consulted only here, after predictions are fixed.
    truth = case['planned_injection_identity']
    truth_nodes = set(truth['risk_nodes'])
    observed = set(risk_ids)
    compression_available = bool(risk_closed and risk_ids)
    metrics = {'root_at3': int(truth['root_node'] in ranked_ids[:3]),
               'risk_any': int(bool(truth_nodes & observed)),
               'risk_all': int(truth_nodes <= observed),
               'compression': 1 - len(risk_ids) / len(ids) if compression_available else 0.0}
    available = {'root_at3': bool(ranked_ids), 'risk_any': bool(risk_ids),
                 'risk_all': bool(risk_ids), 'compression': compression_available}
    return {'metrics': metrics, 'available': available, 'parser_status': parsed.get('status'),
            'ranking_path': rank_path, 'risk_path': risk_path,
            'ranking_recovery_method': 'marker_array' if rank_path and '::marker' in rank_path else 'named_field',
            'risk_recovery_method': 'marker_array' if risk_path and '::marker' in risk_path else 'named_field',
            'ranking_span': [rank_node.get('start'), rank_node.get('end')] if rank_node else None,
            'risk_span': [risk_node.get('start'), risk_node.get('end')] if risk_node else None,
            'ranking_array_closed': rank_closed, 'risk_array_closed': risk_closed,
            'observed_ranking': ranked_ids, 'observed_risk_nodes': risk_ids,
            'ranking_missing': [cid for cid in ids if cid not in seen],
            'ranking_invalid': rank_invalid, 'ranking_duplicates': rank_duplicates,
            'rank_default_positions': rank_defaults,
            'risk_invalid': risk_invalid, 'risk_duplicates': risk_duplicates,
            'parser_issues': parsed.get('issues', [])}


def aggregate(rows):
    out = {}
    for method in ('naive-single', 'lea', 'sa-mcgs'):
        group = [r for r in rows if r['method'] == method]
        assert len(group) == 80
        out[method] = {'denominator': 80,
                       **{m: sum(r[m] for r in group) / 80 for m in METRICS},
                       'hits': {m: sum(r[m] for r in group) for m in METRICS[:3]},
                       'rescored_strict_cases': sum(r.get('rescored_strict_failure', False) for r in group)}
    return out


def write_report(output):
    lines = [
        '# Kimi / Qwen3.5：严格失败案例按指标补入后的结果',
        '',
        '按用户于 2026-09-25 指定的新口径：只重新解析 58 个原严格失败案例；'
        '其余 422 个成功案例直接沿用已有指标，数值未变。全部案例均纳入统计，'
        '能计算的指标照常计入，缺失或不能确定的指标记 0。'
        '每个模型、每种方法、每项指标（包括压缩率）的分母统一为 80。',
        '',
        '本次仅离线处理现有缓存，新增模型调用 0 次、API 支出 $0。'
        '原始响应和原始运行诊断保留；原“严格失败”标记不再屏蔽整例指标。',
        '',
        '| 模型 | 方法 | Root@3 | Risk-any | Risk-all | 平均压缩率 | 分母 |',
        '|---|---|---:|---:|---:|---:|---:|',
    ]
    names = {'kimi': 'Kimi-VL-A3B-Instruct', 'qwen35': 'Qwen3.5-9B'}
    methods = {'naive-single': 'One-shot', 'lea': 'LEA', 'sa-mcgs': 'SA-MCGS'}
    for key, model in output['models'].items():
        for method, s in model['summary'].items():
            metrics = [f"{s[m]:.2%} ({s['hits'][m]}/80)" for m in METRICS[:3]]
            lines.append(f"| {names[key]} | {methods[method]} | " + ' | '.join(metrics) + f" | {s['compression']:.2%} | 80 |")
    lines += ['', '## 仅对原严格失败案例的补入情况', '',
              '| 模型 | 处理案例 | 有可用排名 | 有可用风险节点 | 可计算压缩率 | 新增 Root@3 / Risk-any / Risk-all 命中 |',
              '|---|---:|---:|---:|---:|---|']
    for key, model in output['models'].items():
        n = model['availability_among_rescored']
        evidence = model['strict_case_evidence']
        added = ' / '.join(str(sum(e['metrics'][m] for e in evidence)) for m in METRICS[:3])
        lines.append(f"| {names[key]} | {len(evidence)} | {n['root_at3']} | {n['risk_any']} | {n['compression']} | {added} |")
    lines += [
        '', '## 固定的取值规则', '',
        '- 每例固定使用原流程最后一次缓存响应；不从多次响应中挑选分数较好的结果。',
        '- 排名只取完整输出的条目，沿用原唯一节点别名映射，非法 ID 排除，重复 ID 保留首次；按显式 rank、原始位置排序，取实际可用的前 3 项。缺失节点不补入，缺失排名不通过 risk_score 猜测。',
        '- 风险指标使用已完整输出的节点 ID，规范化后去重。已输出节点能够证明命中则记 1，否则记 0；整个字段缺失同样记 0。',
        '- 压缩率仅在风险列表完整闭合且有有效节点时计算为 1 − 保留节点数 / SCC 节点数；列表截断、缺失或无法解析时记 0。所有案例都参与平均。',
        '- 使用字符串和转义感知的 JSON 前缀解析。唯一的错层字段、唯一且明确的数组内字段标签可以确定性提取；重复键或有歧义的字段不猜测。',
        '- 本次改变了失败处理口径和压缩率分母，属于用户指定的新版评估；原严格版报告保留作对照，不将两种口径混用。LEA / SA-MCGS 因没有整例严格失败，指标不变。',
        '', '## 复核与文件', '',
        f"- [逐例指标、58 例解析证据及汇总]({HERE / 'metricwise_results.json'})",
        f"- [可复现的离线重算脚本]({HERE / 'rescore_strict_failures.py'})",
        f"- [原始严格口径报告]({EXPERIMENT / 'final_analysis/FINAL_RESULTS_ZH.md'})",
        '', '读取的原始文件均记录 SHA-256，并在结束时确认未变；422 个原成功案例逐行相等检查通过。',
    ]
    (HERE / 'METRICWISE_RESULTS_ZH.md').write_text('\n'.join(lines) + '\n')


def main():
    analysis_code_sha256 = {name: hashlib.sha256(read_bytes(HERE / name)).hexdigest()
                           for name in ('rescore_strict_failures.py', 'prefix_json.py')}
    helpers = original_id_helpers()
    graphs = {}
    for domain in ('bgb', 'cuad', 'debian', 'sec_ex21'):
        graph = json.loads(gzip.decompress(read_bytes(EXPERIMENT / f'runner/repo/portable_data/{domain}.graph.json.gz')))
        graphs[domain] = {cid: SimpleNamespace(title=c['title']) for cid, c in graph['clauses'].items()}
    manifest = read_json(HERE / 'raw_cache/source_manifest.json')
    all_out = {}
    for key, label in MODELS.items():
        original = read_json(EXPERIMENT / f'final_analysis/{label}_case_metrics.json')
        plan = {c['case_id']: c for c in read_json(EXPERIMENT / f'downloaded_final/{key}/case_plan.json')}
        rows = copy.deepcopy(original)
        evidence = []
        for row in rows:
            if row['state'] != 'strict_experiment_failure':
                assert row['state'] == 'complete' and all(row[m] is not None for m in METRICS)
                continue
            assert row['method'] == 'naive-single'
            cid = row['case_id']
            relative = f'{key}/{cid}/responses.jsonl'
            data = read_bytes(HERE / 'raw_cache' / relative)
            assert len(data) == manifest[relative]['bytes']
            assert hashlib.sha256(data).hexdigest() == manifest[relative]['sha256']
            calls = [json.loads(line) for line in data.splitlines() if line.strip()]
            # Original terminal response; no selection among retries.
            response = calls[-1]
            record = response['record']
            assert record['case_id'] == cid and record['method'] == 'naive-single'
            result = evaluate(response['content'], plan[cid], graphs[row['domain']], helpers)
            row.update(result['metrics'])
            row.update(state='included_metricwise', valid=True, source_completion_status='strict_experiment_failure',
                       rescored_strict_failure=True, retained_nodes=len(result['observed_risk_nodes']) if result['available']['compression'] else None)
            original_result = read_json(EXPERIMENT / f'downloaded_final/{key}/results/{cid}__naive-single.json')
            evidence.append({'case_id': cid, 'original_error': original_result.get('error'),
                             'response_call_index': response['call_index'], 'response_count': len(calls),
                             'finish_reason': record.get('finish_reason'),
                             'cache_sha256': manifest[relative]['sha256'],
                             'content_sha256': hashlib.sha256(response['content'].encode()).hexdigest(), **result})
        unchanged = [a == b for a, b in zip(original, rows) if a['state'] == 'complete']
        assert all(unchanged)
        assert len(evidence) == (45 if key == 'kimi' else 13)
        all_out[key] = {'model': label, 'original_success_rows_unchanged': len(unchanged),
                        'strict_cases_rescored': len(evidence), 'summary': aggregate(rows),
                        'original_summary_same_denominator': aggregate([{**r, 'compression': r['compression'] or 0} for r in original]),
                        'availability_among_rescored': {m: sum(e['available'][m] for e in evidence) for m in METRICS},
                        'case_metrics': rows, 'strict_case_evidence': evidence}
    for filename, digest in INPUT_HASHES.items():
        assert hashlib.sha256(Path(filename).read_bytes()).hexdigest() == digest, filename
    output = {'policy': 'metricwise_observed_output_zero_missing_v1',
              'scope': 'Only the 58 original strict failures are re-parsed. All 422 successful rows are reused unchanged.',
              'response_selection': 'Final cached response per strict case; never select by score.',
              'ranking': 'Closed entries only; canonical aliases; first occurrence per ID; explicit rank then original position. No missing-node backfill.',
              'risk': 'Closed node values only; canonical aliases; deduplicate. Prefix hit absent = 0.',
              'compression': 'Compute only for a closed, nonempty normalized risk list; otherwise zero. All 80 cases in denominator.',
              'schema_recovery': 'Unique nested named fields and unique literal array schema markers are accepted; ambiguous or duplicated keys are not.',
              'analysis_code_sha256': analysis_code_sha256,
              'additional_api_calls': 0, 'input_hashes_verified_unchanged': INPUT_HASHES,
              'models': all_out}
    (HERE / 'metricwise_results.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    write_report(output)
    print(json.dumps({k: {n: v for n, v in value.items() if n not in ('case_metrics', 'strict_case_evidence')} for k, value in all_out.items()}, indent=2))


if __name__ == '__main__':
    main()

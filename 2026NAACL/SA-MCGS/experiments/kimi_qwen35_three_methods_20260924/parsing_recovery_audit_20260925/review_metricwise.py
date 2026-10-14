#!/usr/bin/env python3
"""Independent read-only checks of the generated metricwise audit."""
import collections
import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
METRICS = ('root_at3', 'risk_any', 'risk_all', 'compression')
LABELS = {'kimi': 'kimi-vl-a3b-instruct', 'qwen35': 'qwen3_5-9b'}


class AmbiguousObject:
    """A complete object with duplicate keys is not usable evidence."""


def unambiguous_pairs(pairs):
    if len({key for key, _ in pairs}) != len(pairs):
        return AmbiguousObject()
    return dict(pairs)


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = HERE / 'metricwise_results.json'
    data = load(output)
    report = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'read_only_inputs': True, 'output_sha256': sha(output),
              'checks': [], 'models': {}}

    def check(name, passed, detail=None):
        item = {'check': name, 'passed': bool(passed)}
        if detail is not None:
            item['detail'] = detail
        report['checks'].append(item)

    hashes = data['input_hashes_verified_unchanged']
    check('all_declared_input_hashes_still_match',
          all(sha(Path(path)) == value for path, value in hashes.items()), len(hashes))
    check('declares_no_additional_api_calls', data['additional_api_calls'] == 0)
    total_success = total_rescored = 0
    graphs = {domain: json.loads(gzip.decompress((ROOT / f'runner/repo/portable_data/{domain}.graph.json.gz').read_bytes()))
              for domain in ('bgb', 'cuad', 'debian', 'sec_ex21')}

    for model, label in LABELS.items():
        source = load(ROOT / f'final_analysis/{label}_case_metrics.json')
        result = data['models'][model]
        rows = result['case_metrics']
        plan = {c['case_id']: c for c in load(ROOT / f'downloaded_final/{model}/case_plan.json')}
        original = {(r['case_id'], r['method']): r for r in source}
        updated = {(r['case_id'], r['method']): r for r in rows}
        strict_ids = {r['case_id'] for r in source if r['state'] == 'strict_experiment_failure'}
        evidence = {e['case_id']: e for e in result['strict_case_evidence']}
        check(f'{model}.unique_row_identity_and_coverage',
              len(original) == len(updated) == len(rows) == 240 and original.keys() == updated.keys())
        successful = [key for key, row in original.items() if row['state'] == 'complete']
        check(f'{model}.all_original_success_rows_identical',
              all(original[key] == updated[key] for key in successful), len(successful))
        total_success += len(successful)
        total_rescored += len(evidence)
        check(f'{model}.exact_strict_failure_scope',
              set(evidence) == strict_ids and len(evidence) == (45 if model == 'kimi' else 13))
        check(f'{model}.reported_scope_counts',
              result['original_success_rows_unchanged'] == len(successful)
              and result['strict_cases_rescored'] == len(evidence))

        direct_raw_checks = []
        for cid, e in evidence.items():
            row = updated[(cid, 'naive-single')]
            c = plan[cid]
            allowed = set(c['planned_scc_clause_ids'])
            selected = e['observed_risk_nodes']
            ranked = e['observed_ranking']
            truth = c['planned_injection_identity']
            check(f'{model}.{cid}.observations_are_unique_allowed_ids',
                  len(selected) == len(set(selected)) and set(selected) <= allowed
                  and len(ranked) == len(set(ranked)) and set(ranked) <= allowed)
            check(f'{model}.{cid}.nonempty_truth_and_consistent_scc_size',
                  bool(truth['risk_nodes']) and c['scc_size'] == len(allowed) == row['scc_size'])
            independently_scored = {
                'root_at3': int(truth['root_node'] in ranked[:3]),
                'risk_any': int(bool(set(truth['risk_nodes']) & set(selected))),
                'risk_all': int(set(truth['risk_nodes']) <= set(selected)),
                'compression': 1 - len(selected) / len(allowed) if e['available']['compression'] else 0.0}
            check(f'{model}.{cid}.metrics_match_fixed_observations',
                  all(row[m] == e['metrics'][m] == independently_scored[m] for m in METRICS))
            check(f'{model}.{cid}.unavailable_metrics_are_zero',
                  all(row[m] == 0 for m in METRICS if not e['available'][m]))
            check(f'{model}.{cid}.compression_uses_complete_risk_list',
                  not e['available']['compression'] or (e['risk_array_closed'] and bool(selected)))
            cache = HERE / 'raw_cache' / model / cid / 'responses.jsonl'
            calls = [json.loads(line) for line in cache.read_text().splitlines() if line.strip()]
            final = calls[-1]
            check(f'{model}.{cid}.final_cached_response_selected',
                  e['response_count'] == len(calls) and e['response_call_index'] == final['call_index']
                  and e['cache_sha256'] == sha(cache)
                  and e['content_sha256'] == hashlib.sha256(final['content'].encode()).hexdigest())
            try:
                raw = json.loads(final['content'], object_pairs_hook=unambiguous_pairs)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue

            # Independent normalization for valid JSON with ordinary top-level fields.
            # Do not import or execute either production parser or scorer.
            normalize = lambda text: re.sub(r'\s+', ' ', text.strip()).casefold()
            candidates = collections.defaultdict(set)
            for node in allowed:
                title = graphs[c['domain']]['clauses'][node]['title']
                for value in (node, node.replace('_', ' '), title):
                    if value:
                        candidates[normalize(value)].add(node)
            aliases = {k: next(iter(v)) for k, v in candidates.items() if len(v) == 1}

            def resolve(item):
                if isinstance(item, str):
                    value = item
                elif isinstance(item, dict):
                    value = next((item[k] for k in ('clause_id', 'node_id', 'id', 'package_id', 'category_id', 'company_id')
                                  if isinstance(item.get(k), str) and item[k]), None)
                else:
                    value = None
                return value if value in allowed else aliases.get(normalize(value)) if value else None

            if isinstance(raw.get('risk_subgraph_nodes'), list):
                independent_risk = list(dict.fromkeys(node for item in raw['risk_subgraph_nodes']
                                                     if (node := resolve(item)) is not None))
                passed = selected == independent_risk
                check(f'{model}.{cid}.direct_raw_json_risk_reproduced', passed)
                direct_raw_checks.append('risk')
            if isinstance(raw.get('global_ranking'), list):
                independent_rank = []
                seen = set()
                for pos, item in enumerate(raw['global_ranking']):
                    node = resolve(item)
                    if node is None or node in seen:
                        continue
                    seen.add(node)
                    try:
                        rank = float(item.get('rank')) if isinstance(item, dict) else pos + 1
                        if not math.isfinite(rank):
                            raise ValueError()
                        rank = int(rank)
                    except (ValueError, TypeError, OverflowError):
                        rank = pos + 1
                    independent_rank.append((rank, pos, node))
                check(f'{model}.{cid}.direct_raw_json_ranking_reproduced',
                      ranked == [r[2] for r in sorted(independent_rank)])
                direct_raw_checks.append('ranking')

        recomputed = {}
        for method in ('naive-single', 'lea', 'sa-mcgs'):
            group = [r for r in rows if r['method'] == method]
            summary = result['summary'][method]
            values = {metric: math.fsum(r[metric] for r in group) / 80 for metric in METRICS}
            hits = {metric: sum(r[metric] for r in group) for metric in METRICS[:3]}
            check(f'{model}.{method}.all_denominators_80', len(group) == summary['denominator'] == 80)
            check(f'{model}.{method}.aggregate_reproduced',
                  all(math.isclose(values[m], summary[m], rel_tol=0, abs_tol=1e-12) for m in METRICS)
                  and hits == summary['hits'])
            recomputed[method] = {'denominator': len(group), **values, 'hits': hits}
        check(f'{model}.availability_counts_reproduced', result['availability_among_rescored'] ==
              {m: sum(bool(e['available'][m]) for e in evidence.values()) for m in METRICS})
        report['models'][model] = {'success_rows_unchanged': len(successful), 'strict_rows': len(evidence),
                                   'independent_valid_json_checks': dict(collections.Counter(direct_raw_checks)),
                                   'recomputed_summary': recomputed}

    check('422_success_rows_unchanged_and_58_strict_rows_rescored', total_success == 422 and total_rescored == 58)
    check('result_artifact_stable_during_review', sha(output) == report['output_sha256'])
    report['all_checks_passed'] = all(c['passed'] for c in report['checks'])
    report['failed_checks'] = [c for c in report['checks'] if not c['passed']]
    (HERE / 'metricwise_independent_review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['all_checks_passed'] else 1)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Read-only trace analysis; writes only derived artifacts in --output-dir.

Search is compared with a common mean-risk output rule, independently of the
native evidence selector. Full trajectories additionally support size-matched
selector, cap, and prefix diagnostics. No inference or response resampling.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import copy
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import socket
import statistics
import sys

ARMS = ('full', 'no_relation_guidance', 'no_critical_revisit', 'no_both', 'random_windows')
SELECTORS = ('full', 'mean-risk-matched-k', 'lea-score-matched-k', 'locked-matched-k')
PREFIXES = (15, 30, 45, 60)
CAP_RATIOS = (.25, .35, .45, .60)
MODEL_NAMES = {'llama': 'llama-3.1-8b', 'kimi': 'kimi-vl-a3b-instruct', 'qwen35': 'qwen3.5-9b'}
HIT_METRICS = ('risk_all', 'risk_any', 'root_at_3', 'endpoint_recall', 'bridge_retained', 'triple_retained')
SCHEMA = 'component_mechanisms.offline.v1'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def no_network():
    def reject(*args, **kwargs):
        raise AssertionError('Offline analysis cannot make network connections')
    old = socket.socket.connect, socket.socket.connect_ex, socket.create_connection
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = reject
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection = old


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Backend:
    """Reuse the original validators, selector aggregation, and replay order."""
    def __init__(self, root, helper_dir=None):
        self.root = Path(root)
        manifest_path = self.root / 'bundle_manifest.json'
        if manifest_path.is_file():
            for relative, expected in read(manifest_path)['unchanged_code_sha256'].items():
                if file_sha(self.root / relative) != expected:
                    raise ValueError(f'Frozen scientific source hash mismatch: {relative}')
        sys.path.insert(0, str(self.root))
        folder = Path(helper_dir) if helper_dir else self.root / 'emnlp2026_discussion'
        self.replay = _module(folder / 'run_component_ablation_stage2_core_replay.py', 'mechanism_original_replay')
        self.replay.REPO_ROOT = self.root
        implementation = Path(sys.modules[self.replay.AlphaGoMCGS.__module__].__file__).resolve()
        if not implementation.is_relative_to(self.root.resolve()):
            raise ValueError('An unrelated scientific module is already imported; use a fresh analysis process')
        self.selector = _module(folder / 'run_offline_selector_control_20261002.py', 'mechanism_original_selector')
        self.hashes = {name: file_sha(folder / name) for name in
                       ('run_component_ablation_stage2_core_replay.py', 'run_offline_selector_control_20261002.py')}

    def identity(self, case, full):
        # The new search run is authoritative for model; the fixed injection
        # plan remains authoritative for node order and injection identity.
        adapted = dict(case, model=full['model'])
        adapted['case_order'] = case.get('main_case_order', case.get('case_order'))
        adapted['case_id'] = case.get('case_id') or full.get('case_id')
        return self.replay.validate_case_identity(adapted, full)

    def histories(self, full, ratio=None, capture_prefixes=None):
        trace, audit = self.replay.validate_trace(full)
        if len(trace) != 60:
            raise ValueError('Expected exactly 60 completed rollout events')
        mcgs, sentinel = self.replay.make_replay_mcgs(full)
        if ratio is not None:
            mcgs.evidence_subgraph_max_ratio = float(ratio)
            mcgs.evidence_subgraph_min_nodes = 4
        summaries = []
        hits = 0
        for event in trace:
            self.replay.apply_trace_event(mcgs, event)
            hits += bool(event.get('is_tt_hit'))
            prefix = len(summaries) + 1
            summaries.append(mcgs._build_result(elapsed=0.0, llm_calls=0,
                                               tt_hits=hits, total_iters=prefix)
                             if capture_prefixes is None or prefix in capture_prefixes or prefix == 60 else None)
        if sentinel.calls:
            raise AssertionError('Replay attempted model inference')
        if ratio is None:
            self.replay.assert_final_full_parity(full, summaries[-1])
        return summaries, audit

    def aggregate(self, ids, events):
        return self.selector.aggregate(ids, events)

    def select(self, ids, stats, k, selector):
        return self.selector.select(ids, stats, k, selector)

    def locked(self, histories, ids, k):
        if k == 0:
            return []
        admitted = []
        for summary in histories:
            # Only the admission capacity changes, after proposals are frozen.
            # This preserves the no-eviction rule without truncating Full.
            matched = dict(summary, evidence_subgraph_cap=k)
            admitted, _ = self.replay.advance_locked_core(admitted, matched, scc_ids=ids)
        selected = set(admitted)
        result = [node for node in ids if node in selected]
        if len(result) != k:
            raise AssertionError('Locked selector could not attain matched output size')
        return result


def load_backend(input_dir, science_root=None):
    helpers = Path(__file__).parent / 'replay_helpers'
    frozen = Path(science_root) if science_root else Path(__file__).parent / 'science/repo'
    if (helpers / 'run_component_ablation_stage2_core_replay.py').is_file() and (frozen / 'src/modules/alphago_mcgs.py').is_file():
        return Backend(frozen, helpers)
    candidates = [Path(science_root)] if science_root else []
    candidates += [Path(input_dir) / 'science/repo', Path(__file__).parent / 'science/repo']
    candidates += list(Path(__file__).resolve().parents)
    for root in candidates:
        if (root / 'emnlp2026_discussion/run_component_ablation_stage2_core_replay.py').is_file():
            return Backend(root)
    raise FileNotFoundError('Frozen replay helpers unavailable; pass --science-root')


def ranking_nodes(ranking):
    if not isinstance(ranking, list):
        raise ValueError('Missing risk ranking')
    result = []
    for row in ranking:
        if isinstance(row, str):
            node = row
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            node = row[0]
        elif isinstance(row, dict):
            node = row.get('clause_id', row.get('node'))
        else:
            raise ValueError('Unrecognized risk ranking row')
        if not isinstance(node, str) or node in result:
            raise ValueError('Invalid or duplicate risk ranking node')
        result.append(node)
    return result


def score_nodes(ids, nodes, ranking, injection):
    if len(nodes) != len(set(nodes)) or not set(nodes) <= set(ids):
        raise ValueError('Output must be a unique subset of the planned SCC')
    risk = set(injection.get('risk_nodes') or injection.get('evidence_nodes') or [])
    root, witness, bridge = (injection.get(key) for key in ('root_node', 'witness_node', 'bridge_node'))
    if not risk or not risk <= set(ids) or root not in ids:
        raise ValueError('Missing/outside-SCC evaluation labels')
    selected = set(nodes)
    rank = ranking_nodes(ranking)
    if not set(rank) <= set(ids):
        raise ValueError('Risk ranking contains outside-SCC nodes')
    triple = {root, witness, bridge} if bridge is not None else None
    if triple is not None and (None in triple or not triple <= set(ids)):
        raise ValueError('Invalid injected context triple')
    return {'risk_all': int(risk <= selected), 'risk_any': int(bool(risk & selected)),
            'root_at_3': int(root in rank[:3]), 'endpoint_recall': len(risk & selected) / len(risk),
            'compression': 1 - len(nodes) / len(ids), 'output_k': len(nodes),
            'bridge_retained': None if bridge is None else int(bridge in selected),
            'triple_retained': None if triple is None else int(triple <= selected),
            'selected_nodes': list(nodes)}


def view_specs(arm, quick=False):
    prefixes = (60,) if quick else PREFIXES
    for prefix in prefixes:
        for selector in ('common-mean-risk', 'native-core'):
            yield {'analysis': 'search', 'selector': selector, 'prefix': prefix, 'cap_ratio': None}
    if quick or arm != 'full':
        return
    for prefix in PREFIXES:
        for selector in SELECTORS:
            yield {'analysis': 'selector', 'selector': selector, 'prefix': prefix, 'cap_ratio': None}
    for ratio in CAP_RATIOS:
        for selector in SELECTORS:
            yield {'analysis': 'cap', 'selector': selector, 'prefix': 60, 'cap_ratio': ratio}


def base_row(case, model, arm, status):
    ids = case.get('planned_scc_clause_ids') or case.get('planned_case_identity', {}).get('ordered_clause_ids')
    if not ids:
        raise ValueError('Plan must preserve ordered SCC node IDs')
    injection = case.get('planned_injection_identity') or case.get('planned_case_identity', {}).get('injection')
    if not injection:
        raise ValueError('Plan must preserve injection identity')
    source = case.get('physical_scc_uid') or 'psc-' + digest({'domain': case['domain'], 'nodes': sorted(ids)})
    return {'model': model, 'arm': arm, 'case_uid': case['case_uid'], 'case_id': case.get('case_id'),
            'case_order': case.get('main_case_order', case.get('case_order')), 'source_id': source,
            'domain': case['domain'], 'template': case.get('template'), 'scc_n': len(ids),
            'has_bridge': injection.get('bridge_node') is not None, 'state': status}


def unavailable_rows(case, model, arm, state, quick=False, error=None):
    base = base_row(case, model, arm, state)
    result = []
    for spec in view_specs(arm, quick):
        row = {**base, **spec, **{m: None for m in HIT_METRICS}, 'compression': None,
               'output_k': None, 'selected_nodes': [], 'error': error}
        if state == 'scientific_failure':
            row.update({m: 0 for m in HIT_METRICS if m not in ('bridge_retained', 'triple_retained')})
            if base['has_bridge']:
                row.update(bridge_retained=0, triple_retained=0)
        result.append(row)
    return result


def analyze_case(full, case, model, arm, backend, quick=False):
    identity = backend.identity(case, full)
    ids = full['scc_clause_ids']
    injection = case.get('planned_injection_identity') or case['planned_case_identity']['injection']
    trace = full['trace_events']
    base = base_row(case, model, arm, 'complete')
    base['identity_verified'] = True
    base['trace_sha256'] = digest(trace)
    # Every successful run is replayed once at its original parameters. This
    # certifies native parity and gives search prefixes for every arm.
    captures = (60,) if quick else (None if arm == 'full' else PREFIXES)
    histories, audit = backend.histories(full, capture_prefixes=captures)
    output = []
    stats_by_prefix = {}
    for prefix in ((60,) if quick else PREFIXES):
        summary = histories[prefix - 1]
        stats = backend.aggregate(ids, trace[:prefix])
        stats_by_prefix[prefix] = stats
        common_k = min(len(ids), max(4, math.ceil(.45 * len(ids))))
        common = backend.select(ids, stats, common_k, 'mean-risk-matched-k')
        native = summary['evidence_risk_subgraph_nodes']
        ranking = summary['ranking_by_risk']
        for selector, nodes in (('common-mean-risk', common), ('native-core', native)):
            output.append({**base, 'analysis': 'search', 'selector': selector, 'prefix': prefix,
                           'cap_ratio': None, **score_nodes(ids, nodes, ranking, injection), 'error': None})
    if quick or arm != 'full':
        return output

    def append_selectors(hist, prefix, ratio, analysis):
        summary = hist[prefix - 1]
        native = summary['evidence_risk_subgraph_nodes']
        k = len(native)
        stats = stats_by_prefix[prefix]
        selections = {'full': native, 'locked-matched-k': backend.locked(hist[:prefix], ids, k)}
        for selector in ('mean-risk-matched-k', 'lea-score-matched-k'):
            selections[selector] = backend.select(ids, stats, k, selector)
        for selector in SELECTORS:
            if len(selections[selector]) != k:
                raise AssertionError('Per-case matched-k violation')
            output.append({**base, 'analysis': analysis, 'selector': selector, 'prefix': prefix,
                           'cap_ratio': ratio, **score_nodes(ids, selections[selector],
                            summary['ranking_by_risk'], injection), 'error': None})
    for prefix in PREFIXES:
        append_selectors(histories, prefix, None, 'selector')
    for ratio in CAP_RATIOS:
        # Recompute the production selector from each recorded evidence prefix;
        # no truncation of the previously selected core or injected-label input.
        cap_histories, _ = backend.histories(full, ratio=ratio)
        append_selectors(cap_histories, 60, ratio, 'cap')
    expected = list(view_specs(arm, quick))
    if len(output) != len(expected):
        raise AssertionError('Incomplete offline views')
    return output


GROUP_FIELDS = ('model', 'arm', 'analysis', 'selector', 'prefix', 'cap_ratio')


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        key = tuple(row[k] for k in GROUP_FIELDS)
        size_group = 'le13' if row['scc_n'] <= 13 else '14to20' if row['scc_n'] <= 20 else 'ge21'
        for grouping, group in (('all', 'all'), ('domain', row['domain']), ('source', row['source_id']),
                                ('template', row['template']), ('scc_size', size_group)):
            groups[(key, grouping, group)].append(row)
    summaries = []
    for (key, grouping, group), values in groups.items():
        states = Counter(x['state'] for x in values)
        done = [x for x in values if x['state'] in ('complete', 'scientific_failure')]
        resolved = len(done) == len(values)
        item = {**dict(zip(GROUP_FIELDS, key)), 'grouping': grouping, 'group': group,
                'planned': len(values), 'terminal': len(done) + states['infrastructure_failure'],
                'evaluable_terminal': len(done), 'successful': states['complete'],
                'scientific_failures': states['scientific_failure'], 'pending': states['pending'],
                'infrastructure_failures': states['infrastructure_failure'],
                'analysis_errors': states['analysis_error'], 'complete': resolved,
                'source_count': len({x['source_id'] for x in values})}
        for metric in HIT_METRICS:
            eligible = [x for x in values if metric not in ('bridge_retained', 'triple_retained') or x['has_bridge']]
            known = [x for x in eligible if x[metric] is not None]
            item[metric + '_n'] = len(eligible)
            item[metric + '_terminal_n'] = len(known)
            item[metric] = (sum(x[metric] for x in eligible) / len(eligible)
                            if eligible and all(x[metric] is not None for x in eligible) else None)
            item[metric + '_terminal_rate'] = statistics.mean(x[metric] for x in known) if known else None
            # Explicit bound only; missing cases never become model failures.
            item[metric + '_planned_lower_bound'] = sum(x[metric] for x in known) / len(eligible) if eligible else None
            if eligible and all(x[metric] is not None for x in eligible):
                sources = defaultdict(list)
                for x in eligible:
                    sources[x['source_id']].append(x[metric])
                item[metric + '_source_equal'] = statistics.mean(statistics.mean(v) for v in sources.values())
            else:
                item[metric + '_source_equal'] = None
        valid = [x for x in values if x['state'] == 'complete']
        item['compression_valid_n'] = len(valid)
        item['compression_valid_mean'] = statistics.mean(x['compression'] for x in valid) if valid else None
        item['output_k_valid_mean'] = statistics.mean(x['output_k'] for x in valid) if valid else None
        summaries.append(item)
    return summaries


def _write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})


def _save(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def report_text(summary):
    c = summary['counts']
    lines = ['# Component mechanisms: offline analysis', '',
             f"Planned {c['planned']} search runs; terminal {c['terminal']}; pending {c['pending']}; "
             f"scientific failures {c['scientific_failures']}; infrastructure failures {c['infrastructure_failures']}; "
             f"analysis errors {c['analysis_errors']}.", '',
             'One run per model/case/arm; no across-seed or across-run standard deviation.', '',
             'All search arms use the same mean-risk rule with k = min(n, max(4, ceil(0.45n))); native cores are reported separately. '
             'Full-only selector comparisons freeze both evidence and actual output size. Root@3 is shared within those comparisons and is not a selector benefit.', '',
             'Cap sweeps rerun the production selector with min_nodes=4 and ratios 0.25/0.35/0.45/0.60; every comparator matches the resulting Full k. '
             'Locked admission uses the same ordered proposals, cannot evict nodes, and fixes its capacity retrospectively to the endpoint Full k. '
             'This size control does not define an online rule for selecting k.', '',
             'Strict rates include terminal scientific failures as zero and use all planned cases (80 per model/arm at completion). '
             'Pending, infrastructure-failed, or unvalidated cases leave strict rates unset; interim evaluable-terminal rates and explicitly named planned-denominator lower bounds are separate. '
             'Compression is averaged only over valid outputs; failure counts remain visible.', '',
             'Bridge and injected-triple diagnostics use all cases with a recorded bridge. They do not replace Risk-all and do not certify all semantic context or edge correctness. '
             'Source rows and source-equal descriptive means account for the four dependent variants of each physical source SCC.', '',
             '| Model | Arm | Output rule | Complete | Risk-all | Risk-any | Root@3 | Compression (valid) |',
             '|---|---|---|---:|---:|---:|---:|---:|']
    def pct(x): return 'pending' if x is None else f'{100*x:.2f}%'
    for row in summary['summaries']:
        if row['grouping'] == 'all' and row['analysis'] == 'search' and row['prefix'] == 60:
            lines.append(f"| {row['model']} | {row['arm']} | {row['selector']} | {row['terminal']}/{row['planned']} | "
                         f"{pct(row['risk_all'])} | {pct(row['risk_any'])} | {pct(row['root_at_3'])} | {pct(row['compression_valid_mean'])} |")
    return '\n'.join(lines) + '\n'


def analyze_run(input_dir, output_dir, *, plan_path=None, science_root=None, quick=False,
                backend=None, models=None, arms=ARMS, expected_cases=80):
    """Analyze runner finals; missing files are pending, never failed cases.

    ``models`` and ``expected_cases`` permit small offline fixtures. The CLI
    retains the three-model, 80-case, five-arm experiment specification.
    """
    root, out = Path(input_dir).resolve(), Path(output_dir).resolve()
    if out == root or out == root / 'results' or (root / 'results') in out.parents:
        raise ValueError('Derived output must not overwrite the run or results tree')
    plan_path = Path(plan_path) if plan_path else root / 'frozen_case_plan.json'
    payload = read(plan_path)
    plan = payload if isinstance(payload, list) else payload.get('cases', payload.get('rows'))
    if not isinstance(plan, list) or len(plan) != expected_cases:
        raise ValueError(f'Expected {expected_cases} frozen cases')
    if len({c['case_uid'] for c in plan}) != len(plan):
        raise ValueError('Duplicate planned case UID')
    models = tuple(models or MODEL_NAMES)
    if len(set(models)) != len(models) or len(set(arms)) != len(arms) or not set(arms) <= set(ARMS):
        raise ValueError('Invalid model/arm scope')
    protocol_path = next((root / name for name in ('frozen_protocol.json', 'protocol.json')
                          if (root / name).is_file()), None)
    protocol = read(protocol_path) if protocol_path else None
    expected_protocol = file_sha(protocol_path) if protocol_path is not None else None
    runtime_path = root / 'runtime_manifest.json'
    expected_runtime = digest(read(runtime_path)) if runtime_path.is_file() else None
    rows, audits, run_errors = [], [], []
    counts = Counter(planned=len(plan) * len(models) * len(arms))
    seen_protocols = set()
    visible_hashes = defaultdict(set)
    expected_paths = {root / 'results' / model / case['case_uid'] / arm / 'final.json'
                      for model in models for case in plan for arm in arms}
    observed = set((root / 'results').rglob('final.json')) if (root / 'results').exists() else set()
    for path in sorted(observed - expected_paths):
        run_errors.append({'kind': 'unexpected_final', 'path': str(path.relative_to(root))})
    with no_network():
        for model in models:
            for case in plan:
                for arm in arms:
                    path = root / 'results' / model / case['case_uid'] / arm / 'final.json'
                    state, error, case_rows = 'pending', None, None
                    record = {}
                    record_hash = None
                    if path.exists():
                        try:
                            record_hash = file_sha(path)
                            record = read(path)
                            if record.get('case_uid') != case['case_uid'] or record.get('arm') != arm:
                                raise ValueError('Final path/result identity mismatch')
                            if record.get('model_key', record.get('model')) != model or record.get('domain') != case['domain']:
                                raise ValueError('Final model/domain identity mismatch')
                            if record.get('case_id') != case.get('case_id'):
                                raise ValueError('Final canonical case ID mismatch')
                            if record.get('seed') != 42 or record.get('repeat_index') != 1:
                                raise ValueError('Expected seed 42 and exactly one repeat')
                            ph = record.get('protocol_sha256')
                            if not isinstance(ph, str) or len(ph) != 64:
                                raise ValueError('Missing protocol SHA-256')
                            if expected_protocol is not None and ph != expected_protocol:
                                raise ValueError('Final protocol SHA-256 mismatch')
                            if expected_runtime is not None and record.get('runtime_manifest_sha256') != expected_runtime:
                                raise ValueError('Final runtime manifest SHA-256 mismatch')
                            seen_protocols.add(ph)
                            if record.get('visible_input_sha256'):
                                visible_hashes[case['case_uid']].add(record['visible_input_sha256'])
                            status = record.get('status', record.get('completion_status'))
                            if record.get('completion_status', status) != status:
                                raise ValueError('Conflicting final completion status')
                            if status in ('complete', 'completed', 'success'):
                                full = record.get('result')
                                if not isinstance(full, dict):
                                    raise ValueError('Successful final has no native result')
                                if record.get('metrics', {}).get('valid') is False:
                                    raise ValueError('Successful final has invalid metrics')
                                expected_model = record.get('model_alias', MODEL_NAMES.get(model, model))
                                if full.get('model') != expected_model:
                                    raise ValueError('Nested result model identity mismatch')
                                if full.get('case_uid', case['case_uid']) != case['case_uid']:
                                    raise ValueError('Nested result case UID mismatch')
                                if backend is None:
                                    backend = load_backend(root, science_root)
                                case_rows = analyze_case(full, case, model, arm, backend, quick)
                                state = 'complete'
                            elif status in ('strict_experiment_failure', 'scientific_failure', 'schema_failure', 'parse_failure'):
                                if record.get('result') is not None or record.get('metrics', {}).get('valid') is not False:
                                    raise ValueError('Scientific failure record lacks explicit invalid/null result')
                                state = 'scientific_failure'
                            elif status in ('pending', 'running', 'in_progress', 'infrastructure_blocked'):
                                state = 'pending'
                            elif status == 'infrastructure_failure':
                                state = 'infrastructure_failure'
                            else:
                                raise ValueError(f'Unrecognized terminal status: {status}')
                        except Exception as exc:
                            state = 'analysis_error'
                            error = f'{type(exc).__name__}: {exc}'
                    if case_rows is None:
                        case_rows = unavailable_rows(case, model, arm, state, quick, error)
                    rows.extend(case_rows)
                    counts[state] += 1
                    audits.append({'model': model, 'case_uid': case['case_uid'], 'arm': arm,
                                   'state': state, 'final_sha256': record_hash, 'error': error,
                                   'usage': record.get('usage'), 'elapsed_sec': record.get('elapsed_sec')})
    if len(seen_protocols) > 1:
        run_errors.append({'kind': 'mixed_protocol_sha256', 'values': sorted(seen_protocols)})
    for uid, hashes in visible_hashes.items():
        if len(hashes) > 1:
            run_errors.append({'kind': 'different_visible_inputs', 'case_uid': uid, 'hashes': sorted(hashes)})
    counts['scientific_failures'] = counts.pop('scientific_failure', 0)
    counts['analysis_errors'] = counts.pop('analysis_error', 0) + len(run_errors)
    counts['successful'] = counts.pop('complete', 0)
    counts['infrastructure_failures'] = counts.pop('infrastructure_failure', 0)
    counts['terminal'] = counts['successful'] + counts['scientific_failures'] + counts['infrastructure_failures']
    counts.setdefault('pending', 0)
    execution_complete = counts['terminal'] == counts['planned'] and counts['analysis_errors'] == 0
    complete = execution_complete and counts['infrastructure_failures'] == 0
    usage_groups = defaultdict(list)
    for audit in audits:
        usage_groups[(audit['model'], audit['arm'])].append(audit)
    usage_summary = []
    for (model, arm), group in usage_groups.items():
        known = [x for x in group if isinstance(x['usage'], dict)]
        cost = {'model': model, 'arm': arm, 'planned': len(group), 'usage_records': len(known),
                'scope': 'whole search run including retries; not prefix costs or additional selector calls'}
        for key in ('calls', 'retry_calls', 'prompt_tokens', 'completion_tokens', 'total_tokens',
                    'held_tokens', 'accounted_tokens', 'held_calls', 'usage_mismatch_calls'):
            values = [x['usage'][key] for x in known if isinstance(x['usage'].get(key), (int, float))]
            cost[key + '_known_n'] = len(values)
            cost[key + '_sum'] = sum(values) if values else None
            cost[key + '_mean'] = statistics.mean(values) if values else None
        elapsed = [x['elapsed_sec'] for x in group if isinstance(x['elapsed_sec'], (int, float))]
        cost['elapsed_sec_known_n'] = len(elapsed)
        cost['elapsed_sec_mean'] = statistics.mean(elapsed) if elapsed else None
        usage_summary.append(cost)
    summary = {'schema_version': SCHEMA, 'quick': quick, 'complete': complete,
               'execution_complete': execution_complete,
               'all_finals_present': len(observed & expected_paths) == counts['planned'],
               'one_run_per_case_arm': True, 'counts': dict(counts),
               'plan_sha256': file_sha(plan_path), 'protocol_sha256': expected_protocol,
               'backend_sha256': backend.hashes if backend is not None else {},
               'source_hashes': {'offline_analysis.py': file_sha(Path(__file__))},
               'scope': {'models': list(models), 'arms': list(arms), 'cases_per_model': expected_cases,
                         'prefixes': [60] if quick else list(PREFIXES),
                         'cap_ratios': [] if quick else list(CAP_RATIOS)},
               'summaries': summarize(rows), 'search_usage': usage_summary, 'run_errors': run_errors}
    out.mkdir(parents=True, exist_ok=True)
    _save(out / 'summary.json', summary)
    _save(out / 'case_metrics.json', rows)
    _save(out / 'identity_and_replay_audit.json', audits)
    _write_csv(out / 'case_metrics.csv', rows)
    _write_csv(out / 'summary.csv', summary['summaries'])
    _write_csv(out / 'search_usage.csv', usage_summary)
    (out / 'REPORT.md').write_text(report_text(summary), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', '--run-root', dest='input_dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--science-root', type=Path)
    parser.add_argument('--quick', action='store_true', help='Only final search views; skip selector/cap/prefix scans')
    args = parser.parse_args()
    summary = analyze_run(args.input_dir, args.output_dir, plan_path=args.plan,
                          science_root=args.science_root, quick=args.quick)
    print(json.dumps({'counts': summary['counts'], 'complete': summary['complete'],
                      'output_dir': str(args.output_dir)}, ensure_ascii=False))
    if summary['counts']['analysis_errors']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()

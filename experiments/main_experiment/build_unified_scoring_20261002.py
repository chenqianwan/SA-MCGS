#!/usr/bin/env python3
"""Strict, offline five-model reanalysis; standard library only, no model imports.

The raw-input mode checks archived identities, hashes and terminal status, then
recomputes metrics.  --from-canonical reproduces aggregates and confidence
intervals from the anonymous canonical CSV without private workspace paths.
Only the explicitly selected output directory is written.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / '2026NAACL/SA-MCGS/experiments/unified_scoring_20261002'
MODELS = ['gpt-4o', 'gemini-2.5-pro', 'qwen2.5-72b', 'llama-3.1-8b', 'qwen3.5-9b']
METHODS = ['one-shot', 'lea', 'sa-mcgs']
DOMAINS = ['debian', 'sec_ex21', 'bgb', 'cuad']
SCALES = ['small', 'medium', 'large']
METRICS = ['root_at3', 'risk_any', 'risk_all']
FIELDS = {'one-shot': 'direct_risk_subgraph_nodes', 'lea': 'lea_risk_subgraph_nodes',
          'sa-mcgs': 'core_evidence_risk_subgraph_nodes'}
LABELS = dict(zip(MODELS, ['GPT-4o', 'Gemini 2.5 Pro', 'Qwen2.5-72B',
                          'Llama 3.1-8B-Instruct', 'Qwen3.5-9B']))
MLABELS = {'one-shot': 'One-shot', 'lea': 'LEA', 'sa-mcgs': r'\samcgs{}'}
SAFE_CONFIG_KEYS = {'model', 'model_id', 'requested_model_id', 'served_model',
    'served_model_name', 'checkpoint_repository', 'checkpoint_revision',
    'temperature', 'max_tokens', 'top_p', 'top_k', 'enable_thinking',
    'dtype', 'quantization', 'max_model_len', 'tensor_parallel_size',
    'budget', 'window_size', 'concurrency', 'internal_concurrency',
    'case_concurrency', 'python_rng_seed', 'python_hash_seed', 'seed',
    'sdk_max_retries', 'json_parse_attempts', 'json_parse_exhaustion_fallback',
    'tt_max_reuse', 'sa_mcgs_budget', 'naive_profile', 'compression_profile',
    'strict_failures_are_terminal'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def write_csv(path, rows):
    require(bool(rows), f'Empty output {path}')
    with Path(path).open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def relpath(path):
    path = Path(path)
    if not path.is_absolute():
        return str(path)
    return str(path.resolve().relative_to(ROOT))


def config_items(obj, prefix=''):
    if not isinstance(obj, dict):
        return
    for key, value in obj.items():
        name = f'{prefix}.{key}' if prefix else key
        if key in SAFE_CONFIG_KEYS and (value is None or isinstance(value, (bool, int, float, str))):
            yield name, value
        elif isinstance(value, dict) and key in {
                'sa_mcgs_config', 'alphago_mcgs', 'lea', 'one_shot', 'model_config',
                'chat_template_kwargs', 'experiment_config', 'effective_mcgs_config',
                'mcgs_config', 'inference_config', 'llm_config', 'run_config', 'provider_route'}:
            yield from config_items(value, name)


class SourceAudit:
    def __init__(self, protocol):
        self.protocol = protocol
        self.hashes = {}
        self.raw_cache = {}
        self.configs = []
        self.records = []

    def read(self, path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        actual = sha(path)
        if expected:
            require(actual == expected.removeprefix('sha256:'), f'Hash mismatch {relpath(path)}')
        self.hashes[path] = actual
        if path not in self.raw_cache:
            self.raw_cache[path] = read_json(path)
        return self.raw_cache[path]

    def input(self, name):
        item = self.protocol['inputs'][name]
        return self.read(item['path'], item['sha256'])

    def observe_config(self, model, method, source, raw, case_uid='protocol'):
        for key, value in config_items(raw):
            self.configs.append({'model': model, 'method': method,
                'case_uid': case_uid, 'source': relpath(source),
                'field': key, 'value_json': json.dumps(value, ensure_ascii=False)})

    def finish(self, out):
        require(all(sha(p) == h for p, h in self.hashes.items()), 'Input changed during audit')
        write_json(out / 'input_manifest.json', {
            'read_only_inputs_verified_unchanged': True,
            'inputs': [{'path': relpath(p), 'sha256': h} for p, h in sorted(self.hashes.items())]})
        write_csv(out / 'source_record_audit.csv', self.records)
        grouped = defaultdict(set)
        for r in self.configs:
            grouped[(r['model'], r['method'], r['source'], r['field'], r['value_json'])].add(r['case_uid'])
        config = [dict(zip(['model', 'method', 'source', 'field', 'value_json'], key),
                       observation_count=len(cases)) for key, cases in sorted(grouped.items())]
        write_csv(out / 'verified_config_observations.csv', config)
        # Summarize only directly recorded values. Current code defaults are not
        # historical run evidence, and a route alias is not a pinned snapshot.
        summary = []
        for model in MODELS:
            for method in METHODS:
                observed = [r for r in self.configs if r['model'] == model and
                            r['method'] == method]
                prows = [r for r in self.configs if r['model'] == model and
                         r['method'] == 'all (protocol)']
                prefix = {'one-shot':'one_shot.', 'lea':'lea.',
                          'sa-mcgs':'sa_mcgs_config.alphago_mcgs.'}[method]
                def direct_values(field):
                    vals = {r['value_json'] for r in observed
                            if r['field'] == field or r['field'] == 'provider_route.'+field}
                    vals.update(r['value_json'] for r in prows
                                if r['field'] in (field,prefix+field))
                    return ' | '.join(sorted(vals)) or 'not recorded in audited artifacts'
                summary.append({'model':model,'method':method,
                    'checkpoint_repository':direct_values('checkpoint_repository'),
                    'checkpoint_revision':direct_values('checkpoint_revision'),
                    'requested_alias':direct_values('model_id'),
                    'served_model':direct_values('served_model'),
                    'temperature':direct_values('temperature'),
                    'max_tokens':direct_values('max_tokens'),
                    'python_rng_seed':direct_values('python_rng_seed'),
                    'python_hash_seed':direct_values('python_hash_seed'),
                    'api_sampling_seed':'not recorded in audited artifacts',
                    'internal_concurrency':direct_values('internal_concurrency')
                        if method != 'sa-mcgs' else direct_values('concurrency'),
                    'exactness_note':'Values are archived observations/protocol fields; missing historical settings are not inferred.'})
        write_csv(out / 'verified_model_method_configuration.csv', summary)


def metric_record(raw, plan, model, method, archived_valid, source, audit, expected):
    status = raw.get('completion_status')
    invalid = bool(raw.get('error') or raw.get('cost_audit_error') or status == 'strict_experiment_failure')
    require(status not in ('missing', 'infrastructure_failure', 'pending'), f'Nonterminal: {source}')
    if model in MODELS[3:]:
        require(status in ('complete', 'strict_experiment_failure'), f'No terminal status: {source}')
    require(archived_valid == (not invalid), f'Invalid flag mismatch: {source}')
    allowed = set(plan['planned_scc_clause_ids'])
    truth = plan['planned_injection_identity']
    risks = set(truth['risk_nodes'])
    require(len(allowed) == int(plan['scc_size']) and risks and risks <= allowed, 'Invalid plan')
    for key in ('planned_scc_clause_ids', 'actual_scc_clause_ids', 'scc_clause_ids'):
        if key in raw:
            require(set(raw[key]) == allowed, f'Input membership mismatch {source}: {key}')
    for key in ('case_uid',):
        if key in raw:
            require(raw[key] == plan['case_uid'], f'Input identity mismatch {source}')
    if 'injected_node' in raw:
        require(raw['injected_node'] == truth['root_node'], f'Root mismatch: {source}')
    if 'injected_risk_nodes' in raw:
        require(set(raw['injected_risk_nodes']) == risks, f'Risk identity mismatch: {source}')
    if 'planned_injection_identity' in raw:
        require(raw['planned_injection_identity'] == truth, f'Injection mismatch: {source}')
    require(raw.get('model') == model, f'Model mismatch: {source}')
    raw_method = raw.get('cost_audit_method', raw.get('method'))
    require(raw_method in ({'naive', 'naive-single', 'one-shot'} if method == 'one-shot' else {method}),
            f'Method mismatch: {source}')
    nodes, rank = [], []
    if not invalid:
        nodes = raw.get(FIELDS[method])
        ranking = raw.get('ranking')
        require(isinstance(nodes, list) and set(nodes) <= allowed, f'Invalid selected nodes: {source}')
        nodes = list(dict.fromkeys(nodes))
        require(isinstance(ranking, list) and ranking, f'Invalid ranking: {source}')
        require(all(isinstance(x, (tuple, list)) and len(x) >= 2 and x[0] in allowed for x in ranking),
                f'Invalid ranking shape: {source}')
        rank = [x[0] for x in ranking]
        require(len(rank) == len(set(rank)), f'Duplicate ranking: {source}')
        if method == 'one-shot':
            require(set(rank) == allowed, f'Incomplete valid One-shot ranking: {source}')
    values = dict(root_at3=int(not invalid and truth['root_node'] in rank[:3]),
                  risk_any=int(not invalid and bool(risks & set(nodes))),
                  risk_all=int(not invalid and risks <= set(nodes)),
                  compression=None if invalid else 1 - len(nodes) / len(allowed))
    for key, value in values.items():
        old = expected.get(key)
        if old in ('', None):
            old = None
        else:
            old = float(old)
        require(old == value or old is not None and value is not None and abs(old-value) < 1e-12,
                f'Archived metric mismatch {source}: {key}')
    audit.observe_config(model, method, source, raw, plan['case_uid'])
    source_digest = audit.hashes[Path(source).resolve()]
    audit.records.append({'model': model, 'method': method, 'case_uid': plan['case_uid'],
        'source': relpath(source), 'sha256': source_digest, 'valid': not invalid,
        'status_rule': 'archived terminal status/error verified',
        'identity_verified': True, 'metrics_recomputed_match_archive': True,
        'json_parse_exhausted_windows': raw.get('json_parse_exhausted_windows', '')})
    return dict(model=model, method=method, case_uid=plan['case_uid'],
        main_case_id=plan['main_case_id'], main_case_order=int(plan['main_case_order']),
        physical_scc_uid=plan['physical_scc_uid'], domain=plan['domain'],
        scc_size=len(allowed), scale='small' if len(allowed) <= 12 else 'medium' if len(allowed) <= 20 else 'large',
        template=plan['template'], valid=not invalid, strict_invalid=invalid,
        compression_defined=not invalid, retained_nodes=None if invalid else len(nodes),
        source_sha256=source_digest, scoring_policy='unified-strict-v1', **values)


def raw_reanalysis(protocol, out):
    audit = SourceAudit(protocol)
    # The portable frozen 80-case plan carries stable source identities and IDs.
    plans = audit.input('llama_plan')
    by_uid = {p['case_uid']: p for p in plans}
    require(len(by_uid) == 80, 'Expected 80 canonical identities')
    require(len({p['physical_scc_uid'] for p in plans}) == 20, 'Expected 20 physical sources')
    require(set(Counter(p['physical_scc_uid'] for p in plans).values()) == {4}, 'Unequal variant count')
    rows = []
    old_item = protocol['inputs']['legacy_metrics']
    old_path = ROOT / old_item['path']
    require(sha(old_path) == old_item['sha256'], 'Legacy CSV hash changed')
    audit.hashes[old_path] = sha(old_path)
    with old_path.open() as handle:
        old_rows = [r for r in csv.DictReader(handle) if r['model'] in MODELS[:3]]
    require(len(old_rows) == 720, 'Legacy three-model coverage')
    for r in old_rows:
        require(r['available'] == r['identity_exact'] == 'True', 'Legacy unavailable/unmatched row')
        plan = by_uid[r['stable_case_uid']]
        require(r['physical_scc_uid'] == plan['physical_scc_uid'] and
                r['domain'] == plan['domain'] and int(r['scc_size']) == plan['scc_size'], 'Metadata mismatch')
        require(r['root_node'] == plan['planned_injection_identity']['root_node'] and
                set(json.loads(r['risk_nodes_json'])) == set(plan['planned_injection_identity']['risk_nodes']),
                'Frozen endpoint identity mismatch')
        source = ROOT / relpath(r['source_file'])
        raw = audit.read(source, r['source_sha256'])
        if isinstance(raw, list):
            candidates = [x for x in raw if x.get('model') == r['model'] and
                          x.get('method') == ('naive' if r['method'] == 'one-shot' else r['method'])]
            require(len(candidates) == 1, 'Ambiguous legacy result selection')
            raw = candidates[0]
        expected = {**r, 'root_at3': r['root_at_3']}
        rows.append(metric_record(raw, plan, r['model'], r['method'], r['strict_invalid'] == 'False',
                                  source, audit, expected))
    for key, model in [('llama', MODELS[3]), ('qwen', MODELS[4])]:
        incoming = audit.input(key + '_strict')
        plan2 = audit.input(key + '_plan')
        frozen = audit.input(key + '_protocol')
        downloaded = audit.input(key + '_download')
        directory = (ROOT / protocol['inputs'][key + '_protocol']['path']).parent
        plans2 = {p['case_uid']: p for p in plan2}
        require(set(plans2) == set(by_uid), 'New model differs from canonical cohort')
        audit.observe_config(model, 'all (protocol)', directory/'frozen_protocol.json', frozen)
        for r in incoming:
            plan = by_uid[r['case_uid']]
            secondary = plans2[r['case_uid']]
            for field in ('planned_scc_clause_ids', 'planned_injection_identity', 'physical_scc_uid'):
                require(plan[field] == secondary[field], f'Cross-model {field} mismatch')
            source = directory / 'results' / (r['case_id'] + '__' + r['method'] + '.json')
            raw = audit.read(source, downloaded['files']['results/' + source.name]['sha256'])
            require(raw.get('checkpoint_revision') == frozen['checkpoint_revision'], 'Checkpoint mismatch')
            method = 'one-shot' if r['method'] == 'naive-single' else r['method']
            rows.append(metric_record(raw, plan, model, method, r['valid'], source, audit, r))
    require(len(rows) == 1200 and len({(r['model'],r['method'],r['case_uid']) for r in rows}) == 1200,
            'Canonical output coverage mismatch')
    rows.sort(key=lambda r: (MODELS.index(r['model']),r['main_case_order'],METHODS.index(r['method'])))
    metricwise = audit.input('qwen_metricwise')['models']['qwen35']['case_metrics']
    lookup = {(r['case_uid'], r['method']): r for r in rows if r['model'] == MODELS[4]}
    sensitivity = []
    for r in metricwise:
        method = 'one-shot' if r['method'] == 'naive-single' else r['method']
        item = dict(lookup[r['case_uid'], method])
        item.update({m: r[m] for m in METRICS + ['compression', 'retained_nodes']})
        item['scoring_policy'] = 'archived-qwen-metricwise-sensitivity'
        item['compression_defined'] = True  # archived sensitivity denominator is always 80
        sensitivity.append(item)
    write_csv(out/'canonical_case_metrics.csv', rows)
    write_csv(out/'qwen_metricwise_sensitivity_cases.csv', sensitivity)
    audit.finish(out)
    return rows, sensitivity


def load_canonical(path):
    with Path(path).open() as handle:
        rows = list(csv.DictReader(handle))
    for r in rows:
        for field in ['main_case_order','scc_size','retained_nodes']:
            r[field] = None if r[field] == '' else int(r[field])
        for field in ['valid','strict_invalid','compression_defined']:
            r[field] = r[field] == 'True'
        for field in METRICS + ['compression']:
            r[field] = None if r[field] == '' else float(r[field])
    return rows


def summarize(rows):
    comp = [r['compression'] for r in rows if r['compression'] is not None]
    return {'n':len(rows),'source_scc_n':len({r['physical_scc_uid'] for r in rows}),
            'valid_n':sum(r['valid'] for r in rows),'strict_invalid_n':sum(r['strict_invalid'] for r in rows),
            **{m:mean(r[m] for r in rows) for m in METRICS},
            'compression':mean(comp) if comp else None,'compression_n':len(comp)}


def quantile(values, q):
    ordered = sorted(values)
    pos = (len(ordered)-1)*q
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi]-ordered[lo])*(pos-lo)


def paired_inference(rows, protocol):
    sources = sorted({r['physical_scc_uid'] for r in rows})
    require(len(sources) == 20, 'Wrong cluster count')
    rng = random.Random(protocol['bootstrap']['seed'])
    samples = [[rng.randrange(20) for _ in range(20)] for _ in range(protocol['bootstrap']['replicates'])]
    indexed = {(r['physical_scc_uid'],r['model'],r['case_uid'],r['method']): r for r in rows}
    keys = sorted({(r['physical_scc_uid'],r['model'],r['case_uid']) for r in rows})
    output, conditional, source_rows = [], [], []
    for model in ['all-five-fixed'] + MODELS:
        for baseline in ['lea', 'one-shot']:
            pairs = [(indexed[*k,'sa-mcgs'], indexed[*k,baseline]) for k in keys
                     if model == 'all-five-fixed' or k[1] == model]
            for metric in METRICS + ['compression']:
                selected = pairs if metric != 'compression' else [(a,b) for a,b in pairs
                    if a['compression'] is not None and b['compression'] is not None]
                by_source = defaultdict(list)
                for a,b in selected:
                    by_source[a['physical_scc_uid']].append(a[metric]-b[metric])
                available = sorted(by_source)
                means = [mean(by_source[s]) for s in available]
                require(means, 'Empty comparison')
                if available == sources:
                    draws = samples
                else:
                    local_rng = random.Random(protocol['bootstrap']['seed'])
                    draws = [[local_rng.randrange(len(available)) for _ in available]
                             for _ in range(protocol['bootstrap']['replicates'])]
                boots = [sum(means[i] for i in draw)/len(draw)*100 for draw in draws]
                result = {'scope':model,'comparison':'sa-mcgs minus '+baseline,'metric':metric,
                    'n_model_variant_pairs':len(selected),'source_scc_n':len(available),
                    'delta_pp':mean(means)*100,'ci95_low_pp':quantile(boots,.025),
                    'ci95_high_pp':quantile(boots,.975),
                    'estimand':'source-equal strict paired binary difference' if metric != 'compression'
                               else 'source-equal compression difference conditional on jointly defined outputs'}
                if metric != 'compression':
                    result.update(sa_only=sum(a[metric] > b[metric] for a,b in selected),
                        baseline_only=sum(a[metric] < b[metric] for a,b in selected),
                        both=sum(bool(a[metric]) and bool(b[metric]) for a,b in selected),
                        neither=sum(not a[metric] and not b[metric] for a,b in selected))
                    output.append(result)
                else:
                    conditional.append(result)
                for source, value in zip(available, means):
                    source_rows.append({'scope':model,'comparison':result['comparison'],'metric':metric,
                        'physical_scc_uid':source,'n_pairs':len(by_source[source]),'delta_pp':value*100})
    return output, conditional, source_rows


def pct(x):
    return '--' if x is None else f'{100*x:.2f}'


def table_rows(groups, group_field, labels, include_n=False):
    lines = []
    values = list(dict.fromkeys(r[group_field] for r in groups))
    for group in values:
        subset = [r for r in groups if r[group_field] == group]
        best = {m:max(r[m] for r in subset if r[m] is not None) for m in METRICS+['compression']}
        for i,r in enumerate(subset):
            cells = [labels.get(group,group) if i == 0 else '', MLABELS[r['method']]]
            if include_n:
                cells.append(str(r['n']))
            for metric in METRICS+['compression']:
                v = pct(r[metric])
                if r[metric] == best[metric]:
                    v = r'\textbf{' + v + '}'
                cells.append(v)
            lines.append(' & '.join(cells) + r' \\')
        if group != values[-1]:
            lines.append(r'\midrule')
    return '\n'.join(lines)+'\n'


def aggregate_outputs(rows, sensitivity, protocol, out):
    groups = {}
    for fields in [('model',),('domain',),('scale',),('model','domain'),('model','scale')]:
        ordering={'model':MODELS,'domain':DOMAINS,'scale':SCALES}
        keys = sorted({tuple(r[k] for k in fields) for r in rows},
                      key=lambda values:tuple(ordering[k].index(v) for k,v in zip(fields,values)))
        records=[]
        for key in keys:
            for method in METHODS:
                subset=[r for r in rows if tuple(r[k] for k in fields)==key and r['method']==method]
                records.append(dict(zip(fields,key),method=method,**summarize(subset)))
        name='_'.join(fields)+'_method'
        groups[name]=records
        write_csv(out/(name+'.csv'),records)
    compatible_dir = out/'compatible_assets'
    compatible_dir.mkdir(exist_ok=True)
    compatible_groups = {}
    for name, records in groups.items():
        compatible_groups[name] = [dict(r, **{m+'_n':r['n'] for m in METRICS}) for r in records]
    write_json(compatible_dir/'aggregates.json', compatible_groups)
    # A plotting consumer only needs numeric rows and cohort metadata. The raw
    # audit fills optional public node/source fields from the existing asset
    # metadata separately; anonymous statistical rebuilds need no raw outputs.
    compatible_rows=[]
    for r in rows:
        compatible_rows.append(dict(r, root_node=None, risk_nodes=None,
            case_id=r['main_case_id'], source_file=None,
            summary_source='canonical_case_metrics.csv', selected_nodes=None))
    metadata_path=out/'compatible_metadata.json'
    if metadata_path.exists():
        metadata={(r['model'],r['method'],r['case_uid']):r for r in read_json(metadata_path)}
        for r in compatible_rows:
            item=metadata[r['model'],r['method'],r['case_uid']]
            for key in ['root_node','risk_nodes','case_id','source_file','selected_nodes']:
                r[key]=item[key]
            if not r['valid']:
                r['selected_nodes']=[]
    write_json(compatible_dir/'canonical_case_metrics.json',compatible_rows)
    overall=[]
    for method in METHODS:
        pooled=summarize([r for r in rows if r['method']==method])
        model_rows=[r for r in groups['model_method'] if r['method']==method]
        overall.append(dict(method=method,aggregation='pooled defined outputs',**pooled))
        equal=dict(pooled,**{m:mean(r[m] for r in model_rows) for m in METRICS+['compression']})
        overall.append(dict(method=method,aggregation='equal model means; compression conditional within model',**equal))
    write_csv(out/'overall_method.csv',overall)
    cis,compression_cis,source_means=paired_inference(rows,protocol)
    write_csv(out/'paired_source_cluster_ci.csv',cis)
    write_csv(out/'paired_compression_conditional_ci.csv',compression_cis)
    write_csv(out/'paired_source_differences.csv',source_means)
    qrows=[]
    for policy,cohort in [('unified strict',[r for r in rows if r['model']==MODELS[4]]),
                           ('Qwen metricwise sensitivity',sensitivity)]:
        for method in METHODS:
            qrows.append(dict(policy=policy,method=method,**summarize([r for r in cohort if r['method']==method])))
    write_csv(out/'qwen_scoring_sensitivity.csv',qrows)
    # Row-only snippets fit the current manuscript table; separate table exposes all denominators.
    (out/'five_model_main_rows.tex').write_text(table_rows(groups['model_method'],'model',LABELS))
    (out/'five_model_model_rows.tex').write_text(table_rows(groups['model_method'],'model',LABELS,True))
    group_labels={'domain':dict(zip(DOMAINS,['Debian','SEC EX-21','BGB','CUAD'])),
                  'scale':dict(zip(SCALES,[r'Short ($\leq$12)','Mid (14--20)',r'Long ($\geq$24)']))}
    for field in ['domain','scale']:
        (out/f'five_model_{field}_rows.tex').write_text(table_rows(groups[field+'_method'],field,group_labels[field],True))
    denom=[r'\begin{table*}[t]',r'\centering\small',
        r'\begin{tabular}{llrrrr}',r'\toprule',
        r'Model & Method & Planned & Valid & Invalid & Comp. $n$ \\',r'\midrule']
    for r in groups['model_method']:
        denom.append(f"{LABELS[r['model']]} & {MLABELS[r['method']]} & {r['n']} & {r['valid_n']} & {r['strict_invalid_n']} & {r['compression_n']} \\\\")
    denom += [r'\bottomrule\end{tabular}',
        r'\caption{Validity and metric denominators for the unified strict main comparison. All three binary metrics use all planned outputs; compression uses only defined valid outputs. Local parsing fallbacks preserve the original terminal-output policy.}',
        r'\label{tab:unified_scoring_denominators}',r'\end{table*}']
    (out/'validity_denominators.tex').write_text('\n'.join(denom)+'\n')
    ctex=[r'\begin{table*}[t]',r'\centering\small',r'\begin{tabular}{llrrr}',r'\toprule',
          r'Model / scope & Comparator & Root@3 & Risk-any & Risk-all \\',r'\midrule']
    for scope in ['all-five-fixed']+MODELS:
        for base in ['lea','one-shot']:
            sel=[r for r in cis if r['scope']==scope and r['comparison']=='sa-mcgs minus '+base]
            cells=['All five (fixed)' if scope=='all-five-fixed' else LABELS[scope],MLABELS[base]]
            for m in METRICS:
                r=next(r for r in sel if r['metric']==m)
                cells.append(f"{r['delta_pp']:+.2f} [{r['ci95_low_pp']:.2f}, {r['ci95_high_pp']:.2f}]")
            ctex.append(' & '.join(cells)+r' \\')
    ctex += [r'\bottomrule\end{tabular}',
        r'\caption{SA-MCGS minus each comparator, in percentage points, with paired source-SCC bootstrap 95\% intervals. Each of 20 sources is resampled jointly across its four variants and five fixed models (20,000 draws; seed 8229). These descriptive intervals do not measure repeated-run variability or adjust for multiple comparisons.}',
        r'\label{tab:unified_paired_intervals}',r'\end{table*}']
    (out/'paired_source_cluster_ci.tex').write_text('\n'.join(ctex)+'\n')
    sensitivity_tex=[r'\begin{table}[t]',r'\centering\small',r'\begin{tabular}{lrrrr}',r'\toprule',
        r'Qwen3.5 One-shot & Root@3 & Any & All & Comp. ($n$) \\',r'\midrule']
    for r in qrows:
        if r['method']=='one-shot':
            label='Strict' if r['policy']=='unified strict' else 'Metricwise recovery'
            sensitivity_tex.append(label+' & '+' & '.join(pct(r[m]) for m in METRICS)+f" & {pct(r['compression'])} ({r['compression_n']}) \\\\")
    sensitivity_tex += [r'\bottomrule\end{tabular}',r'\caption{Qwen3.5-9B scoring sensitivity on the same 80 One-shot outputs. Metricwise recovery deterministically reparses archived strict failures; no new calls are made. LEA and SA-MCGS are unchanged because all their terminal outputs are valid.}',r'\label{tab:qwen_scoring_sensitivity}',r'\end{table}']
    (out/'qwen_scoring_sensitivity.tex').write_text('\n'.join(sensitivity_tex)+'\n')
    paragraph = r'''All five models use a unified strict terminal-output policy. A strict-invalid output receives zero for Root@3, Risk-any, and Risk-all; each binary denominator remains 80. Compression is averaged only over defined valid outputs, with denominators reported separately. The archived local parsing fallback is retained within otherwise valid system outputs. Qwen3.5-9B metricwise reparsing is reported separately as a scoring sensitivity, without new model calls.

The 80 variants comprise four variants from each of 20 physical source SCCs. Paired intervals use 20,000 percentile-bootstrap draws (seed 8229), resampling source SCCs jointly across methods, variants, and the five fixed models. For pooled differences, we first average the 20 model--variant differences within each source, then average sources. Model-specific differences average four variants per source. The comparison uses one frozen terminal outcome per model--method--variant from historical execution batches. Its intervals reflect variation across the selected sources; they do not measure repeated-run seed variation, unseen-model variation, or natural-risk prevalence. Intervals are descriptive and unadjusted for multiple comparisons.
'''
    (out/'scoring_protocol_paragraph.tex').write_text(paragraph)
    all_lea={r['metric']:r for r in cis if r['scope']=='all-five-fixed' and r['comparison']=='sa-mcgs minus lea'}
    all_one={r['metric']:r for r in cis if r['scope']=='all-five-fixed' and r['comparison']=='sa-mcgs minus one-shot'}
    write_json(out/'impact_summary.json',{'primary_changes':{'model':'qwen3.5-9b','method':'one-shot',
        'old_metricwise':[15.0,60.0,13.75,64.73],'new_strict':[100*next(r for r in qrows if r['policy']=='unified strict' and r['method']=='one-shot')[m] for m in METRICS+['compression']],
        'compression_denominator_old':80,'compression_denominator_new':67},
        'sa_minus_lea_overall':all_lea,'sa_minus_one_shot_overall':all_one,
        'unchanged':'All SA-MCGS and LEA main estimates; all four other models; GPT-4o budget curve; expert and component experiments.',
        'affected_assets':['Five-model main table Qwen One-shot row','Pooled One-shot mean in abstract/results','Domain and size tables containing Qwen One-shot','Five-model absolute size plot Qwen One-shot panel','SA versus One-shot paired-outcome plot Qwen row','Any all-method main-summary figures'],'new_model_calls':0})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=DEFAULT_OUT)
    parser.add_argument('--from-canonical',type=Path)
    parser.add_argument('--sensitivity-cases',type=Path)
    parser.add_argument('--protocol',type=Path)
    args=parser.parse_args()
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    protocol_path=args.protocol or out/'protocol.json'
    protocol=read_json(protocol_path)
    checksum_path=protocol_path.parent/'PROTOCOL_SHA256'
    require(checksum_path.exists() and sha(protocol_path)==checksum_path.read_text().split()[0],
            'Frozen protocol checksum missing or changed')
    if args.from_canonical:
        require(args.sensitivity_cases is not None,'--sensitivity-cases required')
        rows=load_canonical(args.from_canonical)
        sensitivity=load_canonical(args.sensitivity_cases)
    else:
        rows,sensitivity=raw_reanalysis(protocol,out)
        asset=ROOT/'experiments/main_experiment/paper_assets/five_model_data/canonical_case_metrics.json'
        old_metadata=read_json(asset)
        indexed={(r['model'],r['method'],r['case_uid']):r for r in rows}
        metadata=[]
        for old in old_metadata:
            current=indexed[old['model'],old['method'],old['case_uid']]
            for key in ['physical_scc_uid','main_case_id','scc_size','domain']:
                require(current[key]==old[key],'Compatible-asset metadata mismatch')
            metadata.append({k:(relpath(old[k]) if k=='source_file' else old[k])
                             for k in ['model','method','case_uid','root_node','risk_nodes',
                                       'case_id','source_file','selected_nodes']})
        write_json(out/'compatible_metadata.json',metadata)
        write_json(out/'compatible_metadata_provenance.json',{
            'input':relpath(asset),'sha256':sha(asset),
            'use':'Public node/source metadata only; every metric overwritten with independently recomputed strict scores.',
            'absolute_paths_removed':True})
    aggregate_outputs(rows,sensitivity,protocol,out)
    if Path(__file__).resolve() != (out/'rebuild_statistics.py').resolve():
        shutil.copyfile(__file__,out/'rebuild_statistics.py')
    write_json(out/'validation.json',{'all_raw_metrics_recomputed':not bool(args.from_canonical),
        'canonical_rows':len(rows),'unique_cells':len({(r['model'],r['method'],r['case_uid'])for r in rows}),
        'source_scc_n':len({r['physical_scc_uid']for r in rows}),'new_model_calls':0,
        'protocol_sha256':sha(protocol_path),'script_sha256':sha(__file__),
        'full_1200_cell_coverage':len(rows)==1200,'source_cluster_definition':'frozen physical_scc_uid; traversal indices ignored'})
    print(json.dumps({'output':str(out),'rows':len(rows),'new_model_calls':0,'validation':'passed'}))


if __name__=='__main__':
    main()

#!/usr/bin/env python3
"""Recompute final metrics from verified raw results and frozen case identities."""
import collections
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
HERE = Path(__file__).resolve().parent
DATA = HERE / 'downloaded_final'
spec = importlib.util.spec_from_file_location('schema_compat', HERE/'concurrency8/schema_compat_launcher.py')
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)
L = A.L
FIELDS = {'naive-single':'direct_risk_subgraph_nodes', 'lea':'lea_risk_subgraph_nodes',
          'sa-mcgs':'core_evidence_risk_subgraph_nodes'}
METRICS = ('root_at3', 'risk_any', 'risk_all')

def mean(values):
    values = [x for x in values if x is not None]
    return sum(values)/len(values) if values else None

def aggregate(rows):
    return {'n':len(rows), 'strict_failures':sum(not r['valid'] for r in rows),
            'compression_n':sum(r['valid'] for r in rows),
            **{m:{'hits':sum(r[m] for r in rows), 'rate':mean([r[m] for r in rows])} for m in METRICS},
            'compression_valid_only':mean([r['compression'] for r in rows])}

def main():
    download = L.read(DATA/'download_manifest.json')
    for name, expected in download['files'].items():
        path = DATA/name
        assert path.stat().st_size == expected['bytes'] and L.sha(path) == expected['sha256']
    bundle = L.verify_bundle()
    cost = L.import_science()
    graphs = L.restore_graphs(cost, bundle)
    plan = L.read(DATA/'case_plan.json')
    original = L.read(L.ROOT/'portable_data/llama80_case_plan.json')
    assert len(plan) == 80 and len({c['case_uid'] for c in plan}) == 80
    for current, source in zip(plan, original):
        for key in ('case_id','case_uid','main_case_order','planned_case_identity',
                    'planned_scc_clause_ids','planned_injection_identity','source_result_sha256'):
            assert current[key] == source[key], key
    validation_plan = copy.deepcopy(plan)
    for case in validation_plan:
        case['source_result_file'] = str(L.ROOT/case['source_result_repo_relpath'])
    cost.validate_case_plan(validation_plan, graphs)
    frozen = L.read(DATA/'frozen_protocol.json')
    args = SimpleNamespace(output_dir=DATA, checkpoint_revision=frozen['checkpoint_revision'])
    expected_names = {f"{c['case_id']}__{m}.json" for c in plan for m in FIELDS}
    assert {p.name for p in (DATA/'results').glob('*.json')} == expected_names
    rows = []
    for case in plan:
        truth = case['planned_injection_identity']
        risk = set(truth['risk_nodes'])
        for method, field in FIELDS.items():
            result = L.read(DATA/'results'/f"{case['case_id']}__{method}.json")
            A.validate_result(cost,args,case,method,graphs,frozen,result)
            assert result['checkpoint_revision'] == frozen['checkpoint_revision']
            valid = result['completion_status'] == 'complete'
            nodes = set(result.get(field) or [])
            assert not valid or nodes <= set(case['planned_scc_clause_ids'])
            ranking = result.get('ranking') or []
            rows.append({'case_id':case['case_id'],'case_uid':case['case_uid'],'method':method,
                'domain':case['domain'],'physical_scc':case['domain']+':'+str(case['scc_id']),
                'scc_size':case['scc_size'],'scale':cost.scale_bin(case['scc_size']),
                'valid':valid,'root_at3':int(valid and truth['root_node'] in [x[0] for x in ranking[:3]]),
                'risk_any':int(valid and bool(nodes & risk)),
                'risk_all':int(valid and bool(risk) and risk <= nodes),
                'retained_nodes':len(nodes) if valid else None,
                'compression':1-len(nodes)/case['scc_size'] if valid else None})
    overall = {m:aggregate([r for r in rows if r['method']==m]) for m in FIELDS}
    previous = L.read(DATA/'summary.json')
    for method, values in overall.items():
        old = previous['methods'][method]
        assert values['n'] == old['terminal'] == 80
        assert values['strict_failures'] == old['strict_failures']
        for metric in METRICS:
            assert abs(values[metric]['rate'] - old[metric]) < 1e-12
        assert abs(values['compression_valid_only'] - old['compression_valid_only']) < 1e-12
    groups = {}
    for dimension in ('domain','scale'):
        groups[dimension] = {key:{m:aggregate([r for r in rows if r['method']==m and r[dimension]==key])
            for m in FIELDS} for key in sorted({r[dimension] for r in rows})}
    indexed = {(r['case_uid'],r['method']):r for r in rows}
    pairs = [(indexed[(c['case_uid'],'sa-mcgs')],indexed[(c['case_uid'],'lea')]) for c in plan]
    paired = {m:{'sa_only':sum(a[m]>b[m] for a,b in pairs),'lea_only':sum(a[m]<b[m] for a,b in pairs),
                  'both':sum(a[m] and b[m] for a,b in pairs),'neither':sum(not a[m] and not b[m] for a,b in pairs)} for m in METRICS}
    shared = [(a,b) for a,b in pairs if a['valid'] and b['valid']]
    matched_compression = {'n':len(shared),'sa_mean':mean([a['compression'] for a,b in shared]),
        'lea_mean':mean([b['compression'] for a,b in shared]),
        'identical_retained_node_count_pairs':sum(a['retained_nodes']==b['retained_nodes'] for a,b in shared)}
    report = {'verified':True,'api_calls':0,'model':'meta-llama/Llama-3.1-8B-Instruct',
        'cases':80,'physical_sccs':len({r['physical_scc'] for r in rows}),'records':len(rows),
        'source_manifest_sha256':L.sha(DATA/'download_manifest.json'),
        'policy':'Strict failures score zero in detection denominators of 80; compression is null for failures and averaged only across valid results.',
        'all_case_identity_checks_passed':True,'all_metrics_match_cluster_summary':True,
        'overall':overall,'groups':groups,'sa_vs_lea_paired':paired,
        'sa_vs_lea_common_valid_compression':matched_compression,
        'statistical_scope':'Descriptive paired counts; no significance claim. Four variants share each physical SCC.'}
    L.write(HERE/'final_analysis.json',report)
    L.write(HERE/'final_analysis_case_metrics.json',rows)
    labels = {'naive-single':'One-shot','lea':'LEA','sa-mcgs':'SA-MCGS'}
    text = ['# Llama 3.1 8B 最终指标','',
        '240 条结果逐 SHA、案例身份及实际执行器来源验证通过。严格失败检测计 0，三项检测分母均为 80；失败压缩率为空，仅在有效输出上取均值。','',
        '| 方法 | Root@3 | Risk-any | Risk-all | 压缩率（有效输出） | 严格失败 |',
        '|---|---:|---:|---:|---:|---:|']
    for method in FIELDS:
        item = overall[method]
        cells = [f"{100*item[m]['rate']:.2f}% ({item[m]['hits']}/80)" for m in METRICS]
        text.append('| '+labels[method]+' | '+' | '.join(cells)+f" | {100*item['compression_valid_only']:.2f}% (n={item['compression_n']}) | {item['strict_failures']}/80 |")
    text += ['',f"SA-MCGS 对 LEA 的共有效案例数为 {matched_compression['n']}，其中 {matched_compression['identical_retained_node_count_pairs']} 对保留节点数相同。",
        '', '原始来源见 downloaded_final/；逐例重算见 final_analysis_case_metrics.json；领域与规模分组、配对计数见 final_analysis.json。80 个变体来自 20 个物理 SCC，此处未进行独立样本显著性推断。','']
    (HERE/'FINAL_METRICS_ZH.md').write_text('\n'.join(text))
    print(json.dumps({'verified':True,'overall':overall,'paired':paired,'common_valid_compression':matched_compression},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()

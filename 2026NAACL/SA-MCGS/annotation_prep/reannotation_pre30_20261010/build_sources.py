#!/usr/bin/env python3
"""Build 30 unmodified source SCCs offline, preserving the original 18 records.

No annotations or model outputs are read. The SEC source loader is reused with
only its eight-SCC display cap removed in memory; original source files stay
unchanged. Select five new SEC and seven new BGB SCCs by size and stable hash.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import inspect
import io
import json
from pathlib import Path
import socket
import sys
from collections import Counter


HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
REPO = PAPER.parents[1]
OLD_SOURCE = HERE.parent/'candidates/pre_sources_18.json'
TIE_SEED = 'reannotation-pre30-unmodified-20261010-v1'
ADDITIONS = {'sec_ex21': 5, 'bgb': 7, 'cuad': 0}
SEC_CAP_BLOCK = '    if len(target_sccs) > 8:\n        target_sccs = target_sccs[:8]\n'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return 'sha256:'+hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    hasher = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def offline_guard():
    """Disable dotenv loading and fail closed if any network/client is attempted."""
    import dotenv
    import openai
    dotenv.load_dotenv = lambda *a, **kw: False
    def denied(*a, **kw):
        raise RuntimeError('Source construction is offline: model/network calls are forbidden')
    openai.OpenAI = denied
    openai.AsyncOpenAI = denied
    socket.create_connection = denied
    socket.socket.connect = denied
    socket.socket.connect_ex = denied


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def load_original_graphs_for_reannotation():
    """Return original SEC/BGB/CUAD graphs; SEC includes all 5–24-node SCCs.

    Callers needing the new SEC cases must use this loader or the frozen source
    records, because the historical SEC loader caps its material pool at eight.
    """
    offline_guard()
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from experiments.cross_domain import run_cross_domain as sec_module
    from experiments.cross_domain import run_cross_domain_battle as battle
    from src.modules.tarjan import TarjanSCCDetector
    original = inspect.getsource(sec_module.load_sec_graph)
    if original.count(SEC_CAP_BLOCK) != 1:
        raise ValueError('SEC loader changed: review the exact cap removal before rebuilding')
    uncapped = original.replace(SEC_CAP_BLOCK, '')
    namespace = dict(sec_module.__dict__)
    exec(compile(uncapped, '<original-sec-loader-without-eight-scc-cap>', 'exec'), namespace)
    with contextlib.redirect_stdout(io.StringIO()):
        graphs = {'sec_ex21': namespace['load_sec_graph'](),
                  'bgb': battle.load_bgb_graph(), 'cuad': battle.load_cuad_graph()}
        for graph in graphs.values():
            TarjanSCCDetector().detect(graph)
    return graphs, battle, sec_module, original, uncapped


def material(graph, ids, domain, revision, helper):
    ids = sorted(ids)
    edges = helper.graph_internal_edges(graph, set(ids))
    source_payload = {'version': 'source_physical_scc_identity_v1', 'domain': domain,
                      'dataset_revision': revision, 'ordered_clause_ids': ids,
                      'typed_internal_edges': edges}
    source_fp = digest(source_payload)
    clauses = []
    text_hashes = []
    for node_id in ids:
        clause = graph.clauses[node_id]
        content = str(clause.content or '')
        if not content.strip():
            raise ValueError(f'Empty original node content: {domain}/{node_id}')
        clauses.append({'id': node_id, 'title': str(clause.title or ''),
                        'content': content, 'clause_type': helper.enum_value(clause.clause_type)})
        text_hashes.append({'id': node_id, 'normalized_text_sha256': 'sha256:'+
                            hashlib.sha256(helper.normalize_text(content).encode()).hexdigest()})
    content_payload = {'version': 'unmodified_pre_source_content_v1',
                       'source_physical_fingerprint': source_fp, 'domain': domain,
                       'dataset_revision': revision, 'ordered_clause_ids': ids,
                       'normalized_clause_text_hashes': text_hashes, 'typed_internal_edges': edges}
    return {'pre_source_id': f"pre_{domain}_{len(ids):02d}_{source_fp.removeprefix('sha256:')[:12]}",
            'source_physical_fingerprint': source_fp, 'pre_content_fingerprint': digest(content_payload),
            'domain': domain, 'source_scc_size': len(ids), 'dataset_revision': revision,
            'unmodified': True, 'annotation_action': 'new_annotation',
            'ordered_clause_ids': ids, 'typed_internal_edges': edges, 'clauses': clauses}


def main():
    old_bytes = OLD_SOURCE.read_bytes()
    old = json.loads(old_bytes)
    if len(old) != 18 or Counter(r['domain'] for r in old) != {'sec_ex21': 5, 'bgb': 3, 'cuad': 10}:
        raise ValueError('Original 18-source manifest changed')
    graphs, battle, sec_module, original_sec, uncapped_sec = load_original_graphs_for_reannotation()
    helper = module('pre30_original_material_helpers', HERE.parent/'candidates/select_candidates.py')
    cost = module('pre30_identity_helpers', REPO/'emnlp2026_discussion/run_cost_audit_clean.py')
    old_nodes = {(r['domain'], tuple(sorted(r['ordered_clause_ids']))) for r in old}
    assert len(old_nodes) == 18
    old_checks = []
    for record in old:
        graph = graphs[record['domain']]
        ids = record['ordered_clause_ids']
        if not any(set(s.clause_ids) == set(ids) for s in graph.sccs):
            raise ValueError('Old source is not present as a complete original SCC')
        rebuilt = material(graph, ids, record['domain'], record['dataset_revision'], helper)
        if rebuilt != record:
            raise ValueError(f"Original material differs: {record['pre_source_id']}")
        old_checks.append({'pre_source_id': record['pre_source_id'],
                           'record_sha256': digest(record), 'pre_content_fingerprint': record['pre_content_fingerprint'],
                           'unchanged': True})
    additions = []
    pool_audit = {}
    selected_audit = []
    revisions = {domain: cost.graph_dataset_revision(graph, domain) for domain, graph in graphs.items()}
    for domain in ('sec_ex21', 'bgb', 'cuad'):
        graph = graphs[domain]
        all_sccs = [s for s in graph.sccs if s.size >= 2]
        candidates = []
        for scc in all_sccs:
            ids = tuple(sorted(scc.clause_ids))
            if (domain, ids) in old_nodes or scc.size > 34:
                continue
            if not all(str(graph.clauses[n].content or '').strip() for n in ids):
                continue
            row = material(graph, ids, domain, revisions[domain], helper)
            tie = hashlib.sha256(f"{TIE_SEED}|{domain}|{row['source_physical_fingerprint']}".encode()).hexdigest()
            candidates.append((row, tie))
        candidates.sort(key=lambda item: (-item[0]['source_scc_size'], item[1]))
        if len(candidates) < ADDITIONS[domain]:
            raise ValueError(f'{domain}: insufficient distinct original SCCs')
        chosen = candidates[:ADDITIONS[domain]]
        additions.extend(row for row, tie in chosen)
        selected_audit.extend({'pre_source_id': row['pre_source_id'], 'domain': domain,
                               'size': row['source_scc_size'], 'tie_sha256': tie,
                               'source_physical_fingerprint': row['source_physical_fingerprint'],
                               'pre_content_fingerprint': row['pre_content_fingerprint']} for row, tie in chosen)
        pool_audit[domain] = {'graph_nodes': len(graph.clauses), 'graph_edges': len(graph.edges),
                             'all_nontrivial_scc_ge2': len(all_sccs),
                             'old_sources': sum(r['domain'] == domain for r in old),
                             'eligible_new_scc_2_to_34': len(candidates),
                             'eligible_new_size_counts': dict(sorted(Counter(r['source_scc_size'] for r, tie in candidates).items())),
                             'selected_new': len(chosen),
                             'selected_new_sizes': [r['source_scc_size'] for r, tie in chosen],
                             'dataset_revision_for_new': revisions[domain],
                             'eligible_new_sources': [{'pre_source_id': r['pre_source_id'], 'size': r['source_scc_size'],
                                                       'source_physical_fingerprint': r['source_physical_fingerprint'],
                                                       'tie_sha256': tie} for r, tie in candidates]}
    sources = copy.deepcopy(old)+additions
    assert len(sources) == 30 and Counter(r['domain'] for r in sources) == {'sec_ex21': 10, 'bgb': 10, 'cuad': 10}
    assert sources[:18] == old
    assert len({(r['domain'], tuple(r['ordered_clause_ids'])) for r in sources}) == 30
    assert len({r['pre_source_id'] for r in sources}) == 30
    sec_raw = Path(sec_module.__file__).parent/'finance_blockchain/corpwatch/entities.ftm.json.gz'
    if not sec_raw.exists():
        sec_raw = sec_raw.with_suffix('')
    raw_paths = [sec_raw, battle.BGB_QUANTLAW_PATH if battle.BGB_QUANTLAW_PATH.exists() else battle.BGB_XML_PATH]
    raw_paths.extend(sorted(battle.CUAD_FULLGRAPH_DIR.glob('*_fullgraph.json')))
    source_paths = [OLD_SOURCE, Path(battle.__file__), Path(sec_module.__file__),
                    HERE.parent/'candidates/select_candidates.py', REPO/'emnlp2026_discussion/run_cost_audit_clean.py', *raw_paths]
    audit = {'schema_version': 'unmodified_pre30_selection_v1', 'model_calls': 0,
             'sources_total': 30, 'old_sources_reused_unchanged': 18, 'new_sources': 12,
             'domain_counts': dict(Counter(r['domain'] for r in sources)),
             'source_manifest_shape': 'list; first 18 records exactly equal original pre_sources_18.json; 12 new records follow',
             'selection_rule': 'Keep all original 18. Add SEC5 and BGB7, using complete unmodified SCCs with 2–34 nodes and nonempty original text; rank descending size, then SHA256 tie-break. No model outputs, annotations, or outcomes are read.',
             'tie_seed': TIE_SEED, 'old_record_checks': old_checks, 'pool_inventory': pool_audit,
             'selected_new_sources': selected_audit,
             'sec_loader_extension': {'change': 'Only remove the target_sccs[:8] cap in a private in-memory function copy; preserve original 5–24-node filter and all original text/edge construction.',
                                      'original_function_sha256': hashlib.sha256(original_sec.encode()).hexdigest(),
                                      'uncapped_function_sha256': hashlib.sha256(uncapped_sec.encode()).hexdigest(),
                                      'original_source_file_modified': False,
                                      'old_dataset_revision_preserved_for_old_records': True},
             'limitations': [
                 'New BGB SCCs have 3–7 nodes; the original pool has no additional 9–34-node BGB SCC. Domain balancing changes the BGB size distribution.',
                 'SEC material comprises original company properties and ownership edges, not contract clauses.',
                 'Unmodified/pre means no synthetic injection; it is not a verified negative label.',
                 'No historical annotations or SA decisions are copied into this source manifest; they belong in a separately versioned annotation/prediction layer.',
                 'The new SEC pool has a different graph-level dataset revision; old 18 record identities and content hashes remain unchanged.'
             ],
             'source_files': [{'path': str(p), 'sha256': file_hash(p)} for p in source_paths],
             'script_sha256': file_hash(Path(__file__))}
    HERE.mkdir(parents=True, exist_ok=True)
    source_output = HERE/'sources_30.json'
    source_output.write_text(json.dumps(sources, ensure_ascii=False, indent=2)+'\n')
    audit['sources_30_file_sha256'] = file_hash(source_output)
    (HERE/'selection_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n')
    assert OLD_SOURCE.read_bytes() == old_bytes
    print(json.dumps({'sources': 30, 'old_preserved': 18, 'new': 12,
                      'domain_counts': audit['domain_counts'],
                      'new_sizes': {d: x['selected_new_sizes'] for d, x in pool_audit.items()},
                      'model_calls': 0, 'source_sha256': audit['sources_30_file_sha256']}))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Offline integration for review; preserve raw votes and existing paper outputs.

Applies the existing designated-third-expert policy to the newly selected five
pre cases. Unresolved sufficiency remains explicit. No manuscript/model changes.
"""
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
PREP = PAPER / 'annotation_prep'
PARENT = PREP / 'reannotation_pre30_20261010'
THIRD = PARENT / 'third_review_20261010'
OLD = PAPER / 'manuscript_revision_20260922/expert_analysis'
SOURCES = {}


def read(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    SOURCES[str(path)] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def write(name, value):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def normalize(record):
    return dict(target_conflict=record['target_conflict'],
                judgment_sufficient={'sufficient': 'yes', 'insufficient': 'no'}[record['judgment_sufficient']],
                confidence=record['confidence'],
                minimal_evidence_section_ids=[k for k, v in record['sections'].items() if v['minimal_evidence']],
                repair_packet_section_ids=[k for k, v in record['sections'].items() if v['repair_material']],
                notes=record['notes'], confirmed_at=record['confirmed_at'], updated_at=record['updated_at'])


def validate_record(record, case):
    assert record['case_id'] == case['id'] and record['content_hash'] == case['content_hash']
    assert record['confirmed'] is True and record['sets_reviewed'] is True
    assert record['target_conflict'] in ('present', 'absent')
    assert record['judgment_sufficient'] in ('sufficient', 'insufficient')
    assert type(record['confidence']) is int and 1 <= record['confidence'] <= 5
    assert set(record['sections']) == {s['id'] for s in case['sections']}
    for v in record['sections'].values():
        assert set(v) == {'minimal_evidence', 'repair_material'}
        assert all(type(x) is bool for x in v.values())
        assert not v['minimal_evidence'] or v['repair_material']
    # Risk-existence decisions do not imply that a paragraph-level evidence set
    # is available. Evidence scoring separately requires nonempty references.


def agreement(records):
    out = []
    for slots in [('expert_1', 'expert_2'), ('expert_1', 'expert_3'), ('expert_2', 'expert_3')]:
        for condition in ['pre', 'post', 'all']:
            cases = [r for r in records if all(s in r['original_ratings'] for s in slots)
                     and (condition == 'all' or r['condition'] == condition)]
            if not cases:
                continue
            row = dict(raters=list(slots), condition=condition, n=len(cases),
                       selected_subset='expert_3' in slots)
            for field in ['target_conflict', 'judgment_sufficient']:
                a, b = [[r['original_ratings'][slot][field] for r in cases] for slot in slots]
                count = sum(x == y for x, y in zip(a, b)); n = len(a)
                ca, cb = Counter(a), Counter(b)
                pe = sum(ca[k] * cb[k] for k in set(a) | set(b)) / n**2
                row[field] = dict(agreement_count=count, raw_agreement=count/n,
                                  cohen_kappa=(count/n-pe)/(1-pe) if pe < 1 else None)
            row['joint_agreement_count'] = sum(all(r['original_ratings'][slots[0]][f] == r['original_ratings'][slots[1]][f]
                                                  for f in ['target_conflict', 'judgment_sufficient']) for r in cases)
            for field in ['minimal_evidence_section_ids', 'repair_packet_section_ids']:
                sets = [(set(r['original_ratings'][slots[0]][field]), set(r['original_ratings'][slots[1]][field])) for r in cases]
                scores = [len(a & b)/len(a | b) if a | b else 1.0 for a, b in sets]
                nonempty = [v for v, (a, b) in zip(scores, sets) if a | b]
                row[field] = dict(mean_jaccard=mean(scores), nonempty_union_n=len(nonempty),
                                  mean_jaccard_excluding_both_empty=mean(nonempty) if nonempty else None)
            out.append(row)
    return out


def main():
    parent = read(PARENT / 'payload.json')
    blind = read(THIRD / 'payload.json')
    audit = read(THIRD / 'internal/selection_audit.json')
    hintpack = read(THIRD / 'method_hints_with_predictions.json')
    files = {
        'expert_1': HERE / 'source_exports/pre18_main_reannotation_20261010_expert_1_2026-10-10T12-32-49-792Z.json',
        'expert_2': HERE / 'source_exports/pre18_main_reannotation_20261010_expert_2_2026-10-10T12-32-59-272Z.json',
        'expert_3': HERE / 'source_exports/expert3_annotations_2026-10-10T13-08-34-739Z.json',
    }
    exports = {slot: read(path) for slot, path in files.items()}
    for slot, path in files.items():
        target = HERE / 'source_exports' / path.name
        target.parent.mkdir(exist_ok=True)
        if target.exists():
            assert target.read_bytes() == path.read_bytes()
        else:
            target.write_bytes(path.read_bytes())
        expected = blind if slot == 'expert_3' else parent
        assert exports[slot]['expert_id'] == slot
        assert exports[slot]['study_id'] == expected['study_id']
        assert exports[slot]['manifest_hash'] == expected['manifest_hash']
        assert set(exports[slot]['annotations']) == {c['id'] for c in expected['cases']}
        for case in expected['cases']:
            validate_record(exports[slot]['annotations'][case['id']], case)
            catalog = exports[slot]['case_catalog'][case['id']]
            assert catalog['content_hash'] == case['content_hash']
            assert catalog['sections'] == ([s['id'] for s in case['sections']] if slot == 'expert_3' else
                [{'id': s['id'], 'source_node_id': s['source_node_id']} for s in case['sections']])
    for original in audit['inputs']:
        assert SOURCES[str(files[original['expert_id']])] == original['sha256']
    old = read(PREP / 'third_expert_review/internal/adjudication_20260920/adjudicated_records.json')
    old_final = read(OLD / 'final_labels_with_separate_references.json')
    codebook = read(PREP / 'internal/private_codebook.json')
    identities = {x['master_record']['pre_source_id']: x for x in codebook['records'] if x['master_record'].get('unmodified')}
    reviewed = {m['case_id']: bid for bid, m in audit['blind_mapping'].items()}
    decisions = {r['case_id']: r for r in audit['decisions']}
    records, exposures = [], []
    for case in parent['cases']:
        cid = case['id']; ident = identities[case['pre_source_id']]
        assert ident['master_record']['source_physical_fingerprint'] == case['source_physical_fingerprint']
        assert {s['section_id']: s['original_node_id'] for s in ident['section_map']} == {s['id']: s['source_node_id'] for s in case['sections']}
        raw = {s: copy.deepcopy(exports[s]['annotations'][cid]) for s in ['expert_1', 'expert_2']}
        assert all(raw[s] == decisions[cid][s] for s in raw)
        eligible = raw['expert_1']['target_conflict'] != raw['expert_2']['target_conflict'] or min(r['confidence'] for r in raw.values()) < 3
        assert eligible == (cid in reviewed)
        if cid in reviewed:
            bid = reviewed[cid]; raw['expert_3'] = copy.deepcopy(exports['expert_3']['annotations'][bid])
            authoritative = [normalize(raw['expert_3'])]
            refs = [{'rater': 'expert_3', **authoritative[0]}]
            resolution = 'designated_expert_3_complete_answer'
            events = [e for e in exports['expert_3']['hint_visibility']['events'] if e['case_id'] == bid]
            before = [e for e in events if e['at'] <= raw['expert_3']['confirmed_at']]
            exposures.append(dict(case_id=cid, blind_id=bid, ever_shown=any(e['visible'] for e in events),
                                  visible_at_confirmation=before[-1]['visible'] if before else False,
                                  confirmed_at=raw['expert_3']['confirmed_at'], events=events))
        else:
            authoritative = [normalize(raw[s]) for s in ['expert_1', 'expert_2']]
            refs = [{'rater': s, **normalize(raw[s])} for s in ['expert_1', 'expert_2']]
            resolution = 'two_original_answers_retained'
        target = authoritative[0]['target_conflict']
        assert all(r['target_conflict'] == target for r in authoritative)
        suffs = {r['judgment_sufficient'] for r in authoritative}
        status = ('sufficiency_disagreement' if len(suffs) > 1 else 'insufficient' if suffs == {'no'} else
                  'positive' if target == 'present' else 'negative')
        records.append(dict(case_id=cid, presentation_id=ident['presentation_id'], condition='pre', domain=case['domain'],
            source_scc_uid=case['source_physical_fingerprint'], pre_source_id=case['pre_source_id'],
            section_count=len(case['sections']), content_hash=case['content_hash'],
            reviewed_by_expert_3=cid in reviewed, resolution=resolution, target_conflict=target,
            scoring_status=status, references=refs, original_ratings={s: normalize(r) for s, r in raw.items()},
            raw_annotations=raw))
    posts = copy.deepcopy([r for r in old['records'] if r['condition'] == 'post'])
    assert len(records) == 18 and len(posts) == 24
    combined = records + posts
    counts = Counter(r['scoring_status'] for r in records)
    coverage = Counter(s for r in combined for s in r['original_ratings'])
    summary = dict(unique_current_cases=42, pre_cases=18, retained_post_cases=24,
        pre_section_count=sum(r['section_count'] for r in records),
        positive_cases_without_minimal_evidence=[r['case_id'] for r in records
            if r['target_conflict'] == 'present' and not all(ref['minimal_evidence_section_ids'] for ref in r['references'])],
        pre_status_counts=dict(counts), pre_target_only_counts=dict(Counter(r['target_conflict'] for r in records)),
        actual_current_ratings=dict(coverage), total_current_ratings=sum(coverage.values()),
        pre_current_ratings=41, retained_post_current_ratings=sum(len(r['original_ratings']) for r in posts),
        legacy12_separate=True, pre_is_reannotation_not_new_independent_sources=True,
        source_export_metadata={s: {k: v for k, v in x.items() if k in ['schema_version','annotation_mode','sa_visible','hints_visible','exported_at']} for s, x in exports.items()},
        expert3_exposure=exposures,
        labeling_policy='Designated E3 complete answer for selected cases; otherwise retain both E1/E2 references. Sufficiency disagreements remain unresolved, never auto-positive or negative.',
        old_post_records_unchanged=(posts == [r for r in old['records'] if r['condition'] == 'post']),
        manuscript_changed=False, new_model_calls=0)
    write('integrated_annotations.json', dict(schema_version='pre18_reannotation_integration.v1',
          status='integrated_for_manuscript_scope_review', summary=summary, records=combined))
    write('summary.json', summary)
    write('agreement.json', dict(note='Latest pre votes plus unchanged historical post; mixed rounds and targeted E3 are explicitly stratified.', rows=agreement(combined)))
    by_pid = {r['presentation_id']: r for r in records}
    frozen_rows = read(OLD / 'pre_case_metrics.json')
    read(OLD / 'post_summary.json')
    source_manifest = read(OLD / 'source_manifest.json')
    frozen_hashes = {x['path']: x['sha256'] for x in source_manifest['source_files']}
    classified, evidence = [], []
    selected_fields = {'one-shot': 'direct_risk_subgraph_nodes', 'lea': 'lea_risk_subgraph_nodes', 'sa-mcgs': 'core_evidence_risk_subgraph_nodes'}
    by_case = {c['id']: c for c in parent['cases']}
    for old_row in frozen_rows:
        r = by_pid[old_row['presentation_id']]
        row = {k: copy.deepcopy(v) for k, v in old_row.items() if k not in ['false_positive', 'abstain', 'valid', 'invalid']}
        row.update(case_id=r['case_id'], expert_status=r['scoring_status'], expert_target=r['target_conflict'])
        status, decision = row['expert_status'], row['decision']
        row['outcome'] = ('invalid' if decision == 'invalid' else 'unresolved_reference' if status not in ['positive','negative'] else
                          'TP' if status == 'positive' and decision == 'assert_target_conflict' else
                          'FN_operational_abstention' if status == 'positive' else
                          'FP' if decision == 'assert_target_conflict' else 'TN_operational_abstention')
        classified.append(row)
        if status != 'positive' or not all(ref['minimal_evidence_section_ids'] for ref in r['references']):
            continue
        returned = set(); valid = decision != 'invalid'
        if valid:
            raw_result = read(row['source_path'])
            assert SOURCES[row['source_path']] == frozen_hashes[row['source_path']]
            assert raw_result['source_physical_fingerprint'] == r['source_scc_uid']
            assert raw_result['target_conflict_decision'] == decision
            sectionmap = {s['source_node_id']: s['id'] for s in by_case[r['case_id']]['sections']}
            nodes = set(raw_result[selected_fields[row['method']]])
            assert nodes <= set(sectionmap)
            returned = {sectionmap[n] for n in nodes}
        values = []
        for ref in r['references']:
            minimal = set(ref['minimal_evidence_section_ids']); repair = set(ref['repair_packet_section_ids'])
            assert minimal and minimal <= repair
            values.append(dict(rater=ref['rater'], minimal_evidence_recall=len(returned & minimal)/len(minimal),
                repair_coverage=len(returned & repair)/len(repair),
                repair_precision=len(returned & repair)/len(returned) if returned else 0,
                outside_reference_fraction=len(returned - repair)/len(returned) if returned else 0))
        evidence.append({**{k: row[k] for k in ['case_id','presentation_id','source_scc_uid','model','method','protocol','source_path']},
            'valid':valid, 'returned_sections':sorted(returned), 'references_scored':values,
            **{key:mean(v[key] for v in values) for key in values[0] if key != 'rater'}})
    groups = defaultdict(list)
    for row in classified:
        groups[row['model'],row['method'],row['protocol']].append(row)
    results = []
    for key, group in groups.items():
        g = dict(zip(['model','method','protocol'],key)); g['n_all']=len(group)
        g['all_predictions']=dict(Counter(r['decision'] for r in group))
        for status in ['positive','negative','insufficient','sufficiency_disagreement']:
            subset=[r for r in group if r['expert_status']==status]
            g[status]=dict(n=len(subset), outcomes=dict(Counter(r['outcome'] for r in subset)),
                           predictions=dict(Counter(r['decision'] for r in subset)))
        pos=g['positive']; neg=g['negative']
        g['tp_over_all_confirmed_positives']=pos['outcomes'].get('TP',0)/pos['n']
        g['fp_over_all_confirmed_negatives']=neg['outcomes'].get('FP',0)/neg['n']
        vneg=neg['n']-neg['outcomes'].get('invalid',0)
        g['fpr_among_valid_confirmed_negatives']=neg['outcomes'].get('FP',0)/vneg if vneg else None
        g['invalid_is_not_a_true_negative']=True
        rows=[r for r in evidence if (r['model'],r['method'],r['protocol'])==key]
        g['natural_positive_evidence']=dict(n=len(rows),valid=sum(r['valid'] for r in rows),
             **{metric:mean(r[metric] for r in rows) for metric in ['minimal_evidence_recall','repair_coverage','repair_precision','outside_reference_fraction']})
        results.append(g)
    write('pre_case_outcomes.json', classified)
    write('natural_positive_evidence.json', evidence)
    write('model_summary.json', results)
    old_by_id = {r['presentation_id']: r for r in old['records']}
    changes = {}
    for slot in ['expert_1', 'expert_2']:
        changes[slot] = {}
        for field in ['target_conflict', 'judgment_sufficient', 'confidence',
                      'minimal_evidence_section_ids', 'repair_packet_section_ids']:
            changed = []
            for record in records:
                before = old_by_id[record['presentation_id']]['original_ratings'][slot][field]
                after = record['original_ratings'][slot][field]
                if (set(before) != set(after)) if isinstance(before, list) else (before != after):
                    changed.append(record['case_id'])
            changes[slot][field] = dict(count=len(changed), cases=changed)
    write('revision_diff.json', changes)
    two_rater_cases = {r['case_id'] for r in records if r['scoring_status'] == 'positive' and not r['reviewed_by_expert_3']}
    sensitivity = []
    for key in groups:
        rows = [r for r in evidence if (r['model'], r['method'], r['protocol']) == key and r['case_id'] in two_rater_cases]
        sensitivity.append({**dict(zip(['model','method','protocol'], key)), 'n':len(rows), 'valid_n':sum(r['valid'] for r in rows),
            **{metric:mean(r[metric] for r in rows) for metric in ['minimal_evidence_recall','repair_coverage','repair_precision']}})
    write('two_rater_supported_sensitivity.json', {
        'description':'Seven supported natural positives based on the two current first-rater references; excludes the E3-adjudicated positive. Does not independently certify blinding. Same frozen model outputs.',
        'case_ids':sorted(two_rater_cases), 'rows':sensitivity})
    write('source_manifest.json', dict(source_files=[dict(path=k,sha256=v) for k,v in SOURCES.items()],
          script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          inherited_resolution_policy='third_expert_review/internal/adjudication_20260920/adjudicated_records.json',
          model_protocol='Frozen paper first/recovery results only. No page-completion reruns substituted.',
          primary_scope='Reviewable integration; no existing manuscript or historical outputs overwritten.',
          new_model_calls=0))
    print(json.dumps({k:v for k,v in summary.items() if k not in ['expert3_exposure','source_export_metadata']},ensure_ascii=False,indent=2))
    for row in results:
        print(row['model'],row['method'],row['protocol'],'positive',row['positive']['outcomes'],'negative',row['negative']['outcomes'],row['natural_positive_evidence'])


if __name__ == '__main__':
    main()

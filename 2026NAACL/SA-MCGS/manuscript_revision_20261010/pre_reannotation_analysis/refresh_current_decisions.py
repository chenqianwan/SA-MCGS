#!/usr/bin/env python3
"""Rebuild final decisions from the current annotation sources and adjudications."""
import hashlib
import json
from copy import deepcopy
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_text())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    baseline = 'snapshots/existence_only_sa_comparison_before_user_verification.json'
    comparison = read(baseline)
    model_updates = read('user_verified_sa_corrections.json')
    expert_updates = read('user_verified_expert3_corrections.json')
    annotation_update_file = 'user_verified_annotation_corrections_20261013.json'
    annotation_updates = read(annotation_update_file)
    integrated = read('integrated_annotations.json')
    source_cases = {r['case_id']: r for r in integrated['records'] if r['condition'] == 'pre'}
    # PRE-03/PRE-04 now reside directly in the current original annotation files.
    all_final_corrections = expert_updates['corrections']
    by_id = {r['case_id']: r for r in comparison['rows']}
    model_update = model_updates['current_correction']
    for cid in model_update['case_ids']:
        result = by_id[cid]['sa'][model_update['model']]
        result['archived_result_before_user_verification'] = dict(result)
        result['sa_risk_found'] = model_update['corrected_risk_found']
        result['decision_source'] = 'latest_user_verified_sa_correction'
    final_decisions = []
    corrections = {r['case_id']: r for r in all_final_corrections}
    assert len(corrections) == len(all_final_corrections), 'Duplicate final correction requires explicit ordering.'
    for row in comparison['rows']:
        cid = row['case_id']
        prior = source_cases[cid]['target_conflict']
        row['expert_target_conflict'] = prior
        if cid in corrections:
            assert prior == corrections[cid]['previous_final_value']
            row['expert_final_before_user_correction'] = prior
            row['expert_target_conflict'] = corrections[cid]['corrected_final_value']
            row['expert_decision_source'] = 'user_relay_of_expert_3_final_adjudication'
        else:
            row['expert_decision_source'] = 'original_exports_with_user_specified_existence_resolution'
        final_decisions.append({k: row[k] for k in ['case_id', 'expert_target_conflict', 'expert_decision_source']})
        for result in row['sa'].values():
            risk = result['sa_risk_found']
            result['outcome'] = ('invalid' if not isinstance(risk, bool) else
                                 'match' if risk == (row['expert_target_conflict'] == 'present') else
                                 'false_positive' if risk else 'false_negative')
    summaries = {}
    for model in ['gpt-4o', 'gemini-2.5-pro']:
        counts = Counter(row['sa'][model]['outcome'] for row in comparison['rows'])
        n = len(comparison['rows']); invalid = counts['invalid']
        wrong = counts['false_positive'] + counts['false_negative']
        summaries[model] = dict(n=n, match=counts['match'], false_positive=counts['false_positive'],
            false_negative=counts['false_negative'], invalid=invalid, wrong_or_invalid_n=wrong+invalid,
            wrong_or_invalid_rate=(wrong+invalid)/n, wrong_over_all_rate=wrong/n,
            wrong_among_valid_rate=wrong/(n-invalid) if n > invalid else None,
            error_case_ids=[row['case_id'] for row in comparison['rows'] if row['sa'][model]['outcome'] in ['false_positive','false_negative']])
    counts = dict(Counter(row['expert_target_conflict'] for row in comparison['rows']))
    comparison.update(schema_version='pre18_existence_only_sa_comparison.v4', expert_counts=counts, summary=summaries,
        label_rule='Use current source annotations: agreed E1/E2 existence judgments, otherwise E3; low confidence (<3) also triggers E3 adjudication. Apply final E3 adjudications for PRE-05/PRE-18. Sufficiency is not an eligibility filter.',
        model_protocol='Frozen recovery records plus latest user-confirmed NO-RISK decisions for GPT-4o PRE-09/PRE-11/PRE-16; raw files preserved and no model reruns.',
        user_verified_corrections=model_updates['history'], expert_final_corrections=expert_updates,
        latest_annotation_corrections=annotation_updates,
        correction_interpretation='Model decisions and expert final judgments are corrected separately. Agreement/error is then recomputed; neither outcome is inferred from the fact of correction.')
    # Source annotations include internal data repairs. The two risk-only
    # supplementary adjudications remain distinct from complete rating records.
    current_cases = []
    rating_updates = annotation_updates['rating_corrections']
    for original in integrated['records']:
        if original['condition'] != 'pre':
            continue
        cid = original['case_id']
        ratings = deepcopy(original['original_ratings'])
        for change in rating_updates:
            if cid != change['case_id']:
                continue
            rating = ratings[change['expert']]
            assert rating[change['field']] == change['corrected_value']
        for expert, rating in ratings.items():
            if expert == 'expert_3' and cid in corrections:
                rating['original_export_target_conflict'] = rating['target_conflict']
                rating['original_export_confidence'] = rating['confidence']
                rating['target_conflict'] = corrections[cid]['corrected_final_value']
                rating['confidence'] = None
                rating['confidence_note'] = 'No new confidence supplied for the corrected final adjudication.'
                rating['evidence_and_sufficiency_scope'] = 'Retained original-export fields; no updated evidence or sufficiency supplied.'
        if cid in corrections and 'expert_3' not in ratings:
            ratings['expert_3'] = dict(target_conflict=corrections[cid]['corrected_final_value'],
                confidence=None, judgment_sufficient=None,
                note='Risk-only supplementary adjudication; no full expert-3 export for this case.')
        current_cases.append(dict(case_id=cid, domain=original['domain'],
            section_count=original['section_count'], pre_source_id=original['pre_source_id'],
            presentation_id=original['presentation_id'], ratings=ratings,
            expert_final_target_conflict=by_id[cid]['expert_target_conflict'],
            sa=deepcopy(by_id[cid]['sa']),
            supplementary_expert3_adjudication=corrections.get(cid)))
    assert len(current_cases) == 18
    assert counts == {'present': 15, 'absent': 3}
    assert summaries['gpt-4o']['match'] == 18 and summaries['gpt-4o']['false_positive'] == 0
    assert summaries['gemini-2.5-pro']['match'] == 15 and summaries['gemini-2.5-pro']['false_positive'] == 3
    for cid in ['PRE-03', 'PRE-04']:
        record = next(r for r in current_cases if r['case_id'] == cid)
        assert record['ratings']['expert_2']['confidence'] == 2
        assert record['ratings']['expert_2']['target_conflict'] == 'present'
        assert record['ratings']['expert_3']['target_conflict'] == 'present'
        assert record['ratings']['expert_3']['confidence'] == source_cases[cid]['original_ratings']['expert_3']['confidence']
        assert all(result['outcome'] == 'match' for result in record['sa'].values())
    write('current_case_annotations.json', dict(schema_version='pre18_current_case_annotations.v1',
        original_annotation_source='integrated_annotations.json',
        correction_sources=['user_verified_expert3_corrections.json', annotation_update_file],
        expert_counts=counts, records=current_cases,
        note='Current source judgments. Null confidence denotes a risk-only supplementary adjudication without a complete rating record.'))
    write('existence_only_sa_comparison.json', comparison)
    write('current_expert_final_decisions.json', dict(schema_version='pre18_current_existence_decisions.v2',
        expert_counts=counts, records=final_decisions, policy=comparison['label_rule'],
        corrections=expert_updates, latest_annotation_corrections=annotation_updates,
        current_case_annotations='current_case_annotations.json',
        note='Final existence decisions and source ratings are exposed in current_case_annotations.json. No missing evidence or confidence is inferred.'))
    sync_path = HERE / 'manuscript_data_sync.json'
    sync = read(sync_path.name) if sync_path.exists() else {}
    manuscript_current = sync.get('expert_counts') == counts and bool(sync.get('manuscript_sources'))
    manuscript_current = manuscript_current and all(
        Path(entry['path']).is_file() and hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest() == entry['sha256']
        for entry in sync.get('manuscript_sources', []))
    agreement_source = sync.get('agreement_source', {})
    manuscript_current = manuscript_current and (
        agreement_source.get('path') == str(HERE / 'agreement.json') and
        agreement_source.get('sha256') == hashlib.sha256((HERE / 'agreement.json').read_bytes()).hexdigest())
    write('current_analysis_manifest.json', dict(schema_version='pre18_current_analysis_manifest.v2',
        current_final_labels='current_expert_final_decisions.json', current_sa_comparison='existence_only_sa_comparison.json',
        source_vote_integration='integrated_annotations.json',
        current_case_annotations='current_case_annotations.json',
        original_vote_counts_unchanged=False, supplementary_final_decision_corrections=len(corrections),
        source_annotation_repairs_applied=True,
        current_confidence_corrections=sum(r['field'] == 'confidence' for r in rating_updates),
        current_risk_judgment_corrections=sum(r['field'] == 'target_conflict' for r in rating_updates),
        legacy_sufficiency_filtered_outputs='The integrate.py outputs retain the original export-based analysis. They do not include the latest user-relayed final decisions and are not the current existence-only comparison.',
        evidence_reference_note='PRE-03/PRE-04 source risk judgments are present; their existing evidence fields were not augmented. PRE-05/PRE-18 supplementary adjudications specify risk existence only. Evidence-set metrics require nonempty references.',
        inputs=[dict(path=name,sha256=hashlib.sha256((HERE/name).read_bytes()).hexdigest()) for name in
                [baseline,'integrated_annotations.json','agreement.json','user_verified_sa_corrections.json','user_verified_expert3_corrections.json',annotation_update_file]],
        rebuild='python3 refresh_current_decisions.py', manuscript_changed=manuscript_current,
        manuscript_refresh_required=not manuscript_current,
        manuscript_sync_record='manuscript_data_sync.json' if manuscript_current else None,
        model_calls=0))
    print(json.dumps(dict(expert_counts=counts, summary=summaries), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Record the user's designated-third-expert resolution; preserve all source votes.

Only the 14 reviewed cases receive a final label. This is not the legacy
three-rater-full-coverage schema and does not manufacture labels for other cases.
No model scores or API calls participate in choosing the adjudicated answer.
"""
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from build_review import HERE, PREP, canonical_hash, load, read_expert

THIRD_SOURCE = Path('/Users/chenlong/Downloads/arr_oct2026_expert3_辅助复核_3_2026-09-20.xlsx')
THIRD_SHA256 = '502f0e48f251857f70192c666bf884373d21bb418609fe58aae6b699b583ebdd'
OUT = HERE / 'internal/adjudication_20260920'
LABEL_FIELDS = ('target_conflict', 'judgment_sufficient', 'confidence',
                'minimal_evidence_section_ids', 'repair_packet_section_ids')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def label(record):
    return {key: copy.deepcopy(record[key]) for key in LABEL_FIELDS}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compose():
    audit = load(HERE / 'internal/selection_audit.json')
    subset = load(HERE / 'data/manifest.json')
    parent = load(PREP / 'frontend/data/manifest.json')
    require(subset['manifest_hash'] == audit['subset_manifest_hash'], 'Subset audit mismatch')
    require(parent['manifest_hash'] == audit['parent_manifest_hash'], 'Parent audit mismatch')
    require(canonical_hash({k: v for k, v in subset.items() if k != 'manifest_hash'}) == subset['manifest_hash'], 'Subset checksum mismatch')
    require(canonical_hash({**parent, 'manifest_hash': ''}) == 'sha256:' + parent['manifest_hash'], 'Parent checksum mismatch')
    order = subset['expert_orders']['expert_3']
    selected = {r['presentation_id'] for r in audit['decisions'] if r['selected']}
    require(set(order) == selected and len(order) == 14, 'Unexpected adjudication scope')
    parent_cases = {r['presentation_id']: r for r in parent['cases']}
    require(all(r == parent_cases[r['presentation_id']] for r in subset['cases']), 'Subset materials changed')
    decisions = {r['presentation_id']: r for r in audit['decisions']}
    experts, sources = {}, []
    source_paths = []
    for source in audit['inputs']:
        path, slot = Path(source['path']), source['expert_slot']
        require(sha(path) == source['sha256'], f'Source changed: {slot}')
        records, provenance = read_expert(path, parent, slot)
        require(all(label(r) == label(decisions[pid][slot]) for pid, r in records.items()), 'Frozen prior votes changed')
        experts[slot] = records
        sources.append(provenance)
        source_paths.append(path)
    require(sha(THIRD_SOURCE) == THIRD_SHA256, 'Third-expert source changed; use a new version')
    experts['expert_3'], provenance = read_expert(THIRD_SOURCE, subset, 'expert_3')
    require(provenance['sha256'] == THIRD_SHA256, 'Third-expert source checksum mismatch')
    metadata = provenance['export_metadata']
    for field, expected in {
        'schema_version': 'third_expert_review_export.v2',
        'parent_manifest_hash': parent['manifest_hash'],
        'translation_pack_hash': load(HERE / 'data/translations_zh.json')['translation_pack_hash'],
        'expert_slot': 'expert_3', 'annotation_protocol': 'binary_judgment_v1',
        'review_protocol': 'targeted_third_blind_v1', '样本数': 14, '已确认样本数': 14,
    }.items():
        require(metadata.get(field) == expected, f'Third-expert metadata mismatch: {field}')
    sources.append(provenance)
    source_paths.append(THIRD_SOURCE)

    records = []
    for pid in [r['presentation_id'] for r in parent['cases']]:
        old = decisions[pid]
        reviewed = pid in selected
        actual = {slot: {**label(values[pid]), 'source_xlsx_row': values[pid]['xlsx_row']}
                  for slot, values in experts.items() if pid in values}
        final = label(experts['expert_3'][pid]) if reviewed else None
        if final:
            final['scoring_status'] = ('insufficient' if final['judgment_sufficient'] == 'no'
                                       else 'positive' if final['target_conflict'] == 'present' else 'negative')
        records.append({
            'presentation_id': pid, 'condition': old['condition'], 'domain': old['domain'],
            'source_physical_fingerprint': old['source_physical_fingerprint'],
            'reviewed_by_expert_3': reviewed, 'third_review_order': order.index(pid) + 1 if reviewed else None,
            'original_ratings': actual,
            'resolution_status': 'designated_expert_3_final' if reviewed else 'original_two_rater_records_retained',
            'final_label': final, 'adjudicating_expert': 'expert_3' if reviewed else None,
            'resolution_basis': 'User designated the third expert as final authority for reviewed cases.' if reviewed else None,
        })
    resolved = [r for r in records if r['reviewed_by_expert_3']]
    status_counts = Counter(f"{r['condition']}:{r['final_label']['scoring_status']}" for r in resolved)
    artifact = {
        'schema_version': 'sa_mcgs.targeted_expert3_adjudication.v1',
        'annotation_protocol': 'binary_judgment_v1',
        'parent_manifest_hash': parent['manifest_hash'], 'subset_manifest_hash': subset['manifest_hash'],
        'policy': {
            'authority': 'user', 'instruction_verbatim': '争议以第三位专家为准',
            'recorded_on': '2026-09-20', 'timing': 'after_receipt_of_third_expert_annotations',
            'preregistered': False,
            'scope': 'all_14_cases_previously_selected_for_third_expert_review',
            'rule': 'use_third_expert_complete_joint_label_and_material_sets',
            'uses_model_performance_to_select_answers': False,
            'unreviewed_cases': 'preserve_two_actual_ratings_without_inventing_a_third_vote_or_merging_sets',
            'iaa': 'compute_on_original_independent_votes_not_adjudicated_labels',
        },
        'blinding_attestations': {
            'experts_1_and_2': copy.deepcopy(audit['author_blinding_attestation']),
            'expert_3': {'by': 'user', 'statement_verbatim': '是的，也是隐藏的，完全盲评',
                         'scope': 'both_algorithm_and_injection_hints_hidden_during_actual_annotation',
                         'raw_export_metadata_preserved': True},
        },
        'source_files': sources,
        'summary': {'case_count': 42, 'actual_ratings': 98, 'coverage': {slot: len(r) for slot, r in experts.items()},
                    'resolved_by_expert_3': 14, 'unreviewed_by_expert_3': 28,
                    'reviewed_result_counts': dict(status_counts), 'full_42_unique_material_set_gold_frozen': False,
                    'legacy12_merged': False},
        'records': records,
    }
    artifact['artifact_hash'] = canonical_hash(artifact)
    for path, source in zip(source_paths, sources):
        require(sha(path) == source['sha256'], 'Original workbook changed during read')
    return artifact


def main():
    artifact = compose()
    out = OUT / 'adjudicated_records.json'
    if out.exists():
        require(load(out) == artifact, 'Existing adjudication differs; create a new version instead')
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(out), 'artifact_hash': artifact['artifact_hash'], **artifact['summary']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Build the selected expert-3 page with optional, initially hidden node results."""
import argparse
import collections
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
PREP = PARENT.parent
PRIVATE = HERE / "internal"
SOURCES = {
    "expert_1": (Path('/Users/chenlong/Downloads/pre18_main_reannotation_20261010_expert_1_2026-10-10T12-32-49-792Z.json'), 'd520650c2c75bfabed3f0e104fc0e345b52bba9e30fb481d3ca619d9fbe8d08f'),
    "expert_2": (Path('/Users/chenlong/Downloads/pre18_main_reannotation_20261010_expert_2_2026-10-10T12-32-59-272Z.json'), 'b3ee3f93246795e4d24b376ce5a5cba460c8043844dc84e0e95959df7e7751fb'),
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(value):
    return 'sha256:' + hashlib.sha256(canonical(value)).hexdigest()


def freeze(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, f'Frozen record differs; create a new version: {path}'
    else:
        path.write_bytes(raw)


def freeze_json(path, value):
    freeze(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def prepare_hints(public, audit):
    """Keep the material/storage identity unchanged; version model hints separately."""
    parent = load(PARENT / 'payload.json')
    source_cases = {case['id']: case for case in parent['cases']}
    cases = {}
    for case in public['cases']:
        mapping = audit['blind_mapping'][case['id']]
        original = source_cases[mapping['case_id']]
        assert original['content_hash'] == case['content_hash']
        assert [section['id'] for section in original['sections']] == [section['id'] for section in case['sections']]
        assert mapping['sections'] == [{'section_id': s['id'], 'source_node_id': s['source_node_id']} for s in original['sections']]
        source = parent['node_results'][original['id']]
        assert set(source) == {section['id'] for section in case['sections']}
        cases[case['id']] = source
    pack = {'schema_version': 'third_expert_method_hints.v1',
            'source_manifest_hash': public['manifest_hash'],
            'models': parent['models'], 'methods': ['sa-mcgs', 'lea'], 'cases': cases}
    pack['pack_hash'] = digest(pack)
    freeze_json(HERE / 'method_hints.json', pack)
    change = {
        'schema_version': 'third_expert_optional_hints_update.v1',
        'user_request': '对应的标注信息要有，同专家12',
        'user_confirmation': '是的',
        'confirmed_interpretation': '补回SA/LEA逐节点结果提示，默认隐藏。',
        'material_manifest_hash_unchanged': public['manifest_hash'],
        'selection_audit_sha256': hashlib.sha256((PRIVATE / 'selection_audit.json').read_bytes()).hexdigest(),
        'hint_pack_hash': pack['pack_hash'], 'default_visible': False,
        'mode_rule': 'Page starts with hints hidden; opening hints is logged and remains in exported exposure history after hiding or reloading. Existing answers and confirmation times remain unchanged.',
        'original_selection_and_blinding_record_preserved': True,
        'source_hint_pack_hash': parent['node_results_pack_hash'],
        'source_cases': {blind: mapping['case_id'] for blind, mapping in audit['blind_mapping'].items()},
    }
    freeze_json(PRIVATE / 'optional_hints_update.json', change)
    return pack


def embedded_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def prepare_case_predictions(public, audit, node_hints):
    """Version the expanded hints while preserving earlier packs and annotations."""
    parent = load(PARENT / 'payload.json')
    sources = {case['id']: case for case in parent['cases']}
    allowed = ('model', 'label', 'status', 'risk_found', 'risk_pair_count',
               'reason', 'evidence_sections', 'decision_rule')
    predictions = {}
    for case in public['cases']:
        source = sources[audit['blind_mapping'][case['id']]['case_id']]
        assert source['content_hash'] == case['content_hash']
        sections = {section['id'] for section in case['sections']}
        predictions[case['id']] = [{key: value[key] for key in allowed}
                                   for value in source['sa_predictions']]
        assert {value['model'] for value in predictions[case['id']]} == {model['id'] for model in node_hints['models']}
        for value in predictions[case['id']]:
            assert set(value['evidence_sections']) <= sections
            assert value['status'] in ('available', 'pending', 'invalid')
            assert value['risk_found'] is None or type(value['risk_found']) is bool
            assert value['status'] == 'available' or value['risk_found'] is None
    pack = {key: value for key, value in node_hints.items() if key != 'pack_hash'}
    pack['schema_version'] = 'third_expert_method_hints.v2'
    pack['case_predictions'] = predictions
    pack['risk_rule_description'] = parent['risk_rule_description']
    pack['pack_hash'] = digest(pack)
    freeze_json(HERE / 'method_hints_with_predictions.json', pack)
    freeze_json(PRIVATE / 'case_predictions_update.json', {
        'schema_version': 'third_expert_case_predictions_update.v1',
        'user_request': '还有刚才前面的是否sa认为有风险',
        'material_manifest_hash_unchanged': public['manifest_hash'],
        'prior_hint_pack_hash': node_hints['pack_hash'], 'hint_pack_hash': pack['pack_hash'],
        'source_prediction_pack_hash': parent['prediction_pack_hash'],
        'source_fields': list(allowed), 'default_visible': False,
        'visibility_control': 'Same toggle and exposure history as per-node model hints.',
        'existing_answers_preserved': True,
    })
    return pack


def validate_export(raw, slot, source_payload):
    assert raw['schema_version'] == 'pre30_reannotation.export.v1'
    assert raw['annotation_protocol'] == 'pre30_binary_judgment.v1'
    assert raw['expert_id'] == slot
    for key in ('study_id', 'manifest_hash', 'prediction_pack_hash', 'node_results_pack_hash'):
        assert raw[key] == source_payload[key], key
    catalog = {c['id']: {'content_hash': c['content_hash'], 'sections': [
        {'id': s['id'], 'source_node_id': s['source_node_id']} for s in c['sections']]} for c in source_payload['cases']}
    assert raw['case_catalog'] == catalog
    assert raw['node_results'] == source_payload['node_results']
    assert set(raw['annotations']) == set(catalog)
    allowed = {'case_id', 'content_hash', 'target_conflict', 'judgment_sufficient', 'confidence',
               'sections', 'notes', 'confirmed', 'sets_reviewed', 'confirmed_at', 'updated_at', 'sa_visible'}
    for case in source_payload['cases']:
        record = raw['annotations'][case['id']]
        assert set(record) == allowed
        assert record['case_id'] == case['id'] and record['content_hash'] == case['content_hash']
        assert record['confirmed'] is True and record['sets_reviewed'] is True
        assert record['target_conflict'] in ('present', 'absent')
        assert record['judgment_sufficient'] in ('sufficient', 'insufficient')
        assert type(record['confidence']) is int and 1 <= record['confidence'] <= 5
        assert isinstance(record['notes'], str) and type(record['sa_visible']) is bool
        for key in ('confirmed_at', 'updated_at'):
            assert datetime.fromisoformat(record[key].replace('Z', '+00:00')).tzinfo is not None
        assert set(record['sections']) == {s['id'] for s in case['sections']}
        for choice in record['sections'].values():
            assert set(choice) == {'minimal_evidence', 'repair_material'}
            assert all(type(value) is bool for value in choice.values())
            assert not choice['minimal_evidence'] or choice['repair_material']
        if record['target_conflict'] == 'present' and record['judgment_sufficient'] == 'sufficient':
            assert any(x['minimal_evidence'] for x in record['sections'].values())
    return raw


def prepare():
    parent = load(PARENT / 'payload.json')
    policy = {
        'id': 'targeted_third_user_rule_20261010_v1',
        'rule': 'target_conflict_disagreement_or_any_confidence_strictly_below_3',
        'target_conflict_disagreement': True,
        'any_confidence_strictly_below': 3,
        'judgment_sufficiency_used_for_selection': False,
        'evidence_overlap_used_for_selection': False,
        'model_outputs_used_for_selection': False,
        'order': 'filter_existing_frozen_expert_3_order_without_reordering',
        'authority': 'user_correction_2026-10-10',
        'user_statement': '之前只有置信度低于3 是否有冲突观点不一致',
    }
    inputs, experts = [], {}
    for slot, (path, sha) in SOURCES.items():
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == sha, path
        exports = validate_export(json.loads(raw), slot, parent)
        freeze(PRIVATE / 'source_exports' / path.name, raw)
        experts[slot] = exports['annotations']
        inputs.append({'expert_id': slot, 'source_file': path.name, 'sha256': sha,
                       'exported_at': exports['exported_at'],
                       'original_export_metadata': {key: exports.get(key) for key in (
                           'annotation_mode', 'annotation_mode_scope', 'sa_visible', 'method_hints_visible')}})
    decisions = []
    for case in parent['cases']:
        a, b = (experts[slot][case['id']] for slot in ('expert_1', 'expert_2'))
        reasons = []
        if a['target_conflict'] != b['target_conflict']:
            reasons.append('target_disagreement')
        if any(x['confidence'] < 3 for x in (a, b)):
            reasons.append('low_confidence')
        decisions.append({'case_id': case['id'], 'selected': bool(reasons), 'reasons': reasons,
                          'expert_1': a, 'expert_2': b})
    selected = {x['case_id'] for x in decisions if x['selected']}
    assert selected, 'No third-expert subset is needed'
    old_manifest = load(PREP / 'frontend/data/manifest.json')
    codebook = load(PREP / 'internal/private_codebook.json')
    pre_to_pid = {x['master_record']['pre_source_id']: x['presentation_id'] for x in codebook['records']
                  if x['master_record'].get('pre_source_id') and x['master_record'].get('unmodified')}
    pid_to_current = {pre_to_pid[c['pre_source_id']]: c['id'] for c in parent['cases']}
    order = [pid_to_current[pid] for pid in old_manifest['expert_orders']['expert_3']
             if pid in pid_to_current and pid_to_current[pid] in selected]
    assert set(order) == selected and len(order) == len(selected)
    by_id = {c['id']: c for c in parent['cases']}
    public = {'schema_version': 'third_expert_blind_payload.v1',
              'study_id': 'expert3_blind_20261010', 'annotation_protocol': 'binary_judgment_v1',
              'annotation_mode': 'blind', 'expert_id': 'expert_3', 'hints_visible': False,
              'case_count': len(order), 'cases': []}
    mapping = {}
    for index, source_id in enumerate(order, 1):
        case = by_id[source_id]
        blind_id = f'B-{index:02d}'
        public['cases'].append({'id': blind_id, 'order': index, 'content_hash': case['content_hash'],
            'sections': [{key: section[key] for key in ('id', 'heading', 'original_text', 'zh_heading', 'zh_text')}
                         for section in case['sections']]})
        mapping[blind_id] = {'case_id': source_id, 'pre_source_id': case['pre_source_id'],
            'historical_presentation_id': pre_to_pid[case['pre_source_id']],
            'content_hash': case['content_hash'], 'domain': case['domain'],
            'source_physical_fingerprint': case['source_physical_fingerprint'],
            'sections': [{'section_id': s['id'], 'source_node_id': s['source_node_id']} for s in case['sections']]}
    # Include the frozen input identity in the opaque batch hash so another pair
    # of votes cannot silently share this blind annotator's storage namespace.
    public['manifest_hash'] = digest({'public': public, 'inputs': inputs, 'policy': policy})
    audit = {'schema_version': 'pre18_targeted_third_selection.v1', 'policy': policy,
             'parent_manifest_hash': parent['manifest_hash'], 'inputs': inputs,
             'user_blinding_statement': {
                 'date': '2026-10-10', 'quote': '打标的时候所有提示都隐藏的，是完全盲测',
                 'record_type': 'user_report_and_instruction',
                 'interpretation': '用户说明标注时隐藏所有提示，并要求第三专家继续完全盲测。',
                 'original_export_metadata_preserved': True,
                 'third_expert_implementation': 'Public HTML excludes all model outputs, other experts’ answers, selection reasons and condition labels; it starts in a fresh blank storage namespace.'},
             'decisions': decisions, 'expert_3_source_order': order, 'blind_mapping': mapping,
             'public_manifest_hash': public['manifest_hash'],
             'summary': {'source_cases': len(parent['cases']), 'selected_cases': len(order),
                         'sections': sum(len(c['sections']) for c in public['cases']),
                         'domains': dict(collections.Counter(by_id[x]['domain'] for x in order)),
                         'reason_counts_overlapping': dict(collections.Counter(r for x in decisions for r in x['reasons']))}}
    freeze_json(PRIVATE / 'selection_audit.json', audit)
    freeze_json(HERE / 'payload.json', public)
    return public, audit


def build():
    public, audit = prepare()
    hints = prepare_case_predictions(public, audit, prepare_hints(public, audit))
    ui = {name: (HERE / 'ui' / name).read_text(encoding='utf-8') for name in ('template.html', 'annotation.js', 'styles.css')}
    replacements = {'__PAYLOAD_JSON__': embedded_json(public), '__METHOD_HINTS_JSON__': embedded_json(hints),
                    '__APP_JS__': re.sub(r'</script', r'<\\/script', ui['annotation.js'], flags=re.I),
                    '__APP_CSS__': re.sub(r'</style', r'<\\/style', ui['styles.css'], flags=re.I)}
    html = ui['template.html']
    for marker, value in replacements.items():
        assert html.count(marker) == 1, marker
        html = html.replace(marker, value)
    old_page = PARENT / 'dist/pre30_reannotation.html'
    archive = PRIVATE / 'previous_page/pre30_reannotation.html'
    if not archive.exists():
        freeze(archive, old_page.read_bytes())
    # Other experts' answers and selection reasons stay outside the served directory.
    outputs = [PARENT / 'dist/expert3_blind_20261010.html', old_page]
    for path in outputs:
        temporary = path.with_suffix('.html.tmp')
        temporary.write_text(html, encoding='utf-8')
        temporary.replace(path)
    receipt = {'built_at': datetime.now(timezone.utc).isoformat(), 'study_id': public['study_id'],
               'manifest_hash': public['manifest_hash'], 'case_count': public['case_count'],
               'section_count': audit['summary']['sections'], 'annotation_mode': 'blind_default_with_optional_method_hints',
               'hints_embedded': True, 'hints_default_visible': False,
               'case_risk_predictions_embedded': True,
               'hint_pack_hash': hints['pack_hash'], 'other_expert_answers_embedded': False,
               'selection_reasons_embedded': False, 'initial_answers': 'blank',
               'output_sha256': hashlib.sha256(outputs[0].read_bytes()).hexdigest(),
               'outputs': [str(x) for x in outputs], 'model_calls': 0}
    (HERE / 'build_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (PARENT / 'active_page.json').write_text(json.dumps({
        'study_id': public['study_id'], 'manifest_hash': public['manifest_hash'],
        'builder': 'third_review_20261010/build_blind.py',
        'annotation_mode': 'blind_default_with_optional_method_hints', 'case_count': public['case_count'],
        'previous_page_archive': 'third_review_20261010/internal/previous_page/pre30_reannotation.html'
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare()[1]['summary'] if args.prepare_only else build(), ensure_ascii=False, indent=2))

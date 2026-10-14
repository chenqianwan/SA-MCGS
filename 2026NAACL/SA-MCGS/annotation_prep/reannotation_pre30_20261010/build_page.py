#!/usr/bin/env python3
"""Build the 18 original legal-source reannotation page at its existing URL."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT/'dist/pre30_reannotation.html'
HASH = re.compile(r'^(sha256:)?[0-9a-f]{64}$')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_id(value):
    return isinstance(value, str) and bool(value) and value not in ('__proto__', 'constructor', 'prototype')


def validate_payload(data):
    require(isinstance(data, dict) and data.get('study_id') == 'pre18_main_reannotation_20261010', 'Unexpected study_id')
    require(isinstance(data.get('schema_version'), str) and data['schema_version'], 'Missing payload schema')
    for key in ('manifest_hash', 'prediction_pack_hash'):
        require(isinstance(data.get(key), str) and HASH.fullmatch(data[key]), f'Invalid {key}')
    models = data.get('models')
    require(isinstance(models, list) and models, 'Expected at least one model')
    model_ids = set()
    for model in models:
        require(isinstance(model, dict) and safe_id(model.get('id')) and model['id'] not in model_ids, 'Duplicate or invalid model')
        require(isinstance(model.get('label'), str) and model['label'], 'Missing model label')
        model_ids.add(model['id'])
    cases = data.get('cases')
    require(isinstance(cases, list) and len(cases) == 18 and data.get('case_count') == 18, 'Exactly 18 main-experiment legal sources are required')
    case_ids, orders = set(), set()
    for case in cases:
        require(isinstance(case, dict) and safe_id(case.get('id')) and case['id'] not in case_ids, 'Duplicate or invalid case ID')
        case_ids.add(case['id'])
        require(type(case.get('order')) is int and 1 <= case['order'] <= 18 and case['order'] not in orders, 'Invalid or duplicate display order')
        orders.add(case['order'])
        require(isinstance(case.get('content_hash'), str) and HASH.fullmatch(case['content_hash']), 'Invalid case content hash')
        require(type(case.get('previous_batch')) is bool, 'Missing previous-batch provenance')
        for key in ('domain', 'source_label'):
            require(isinstance(case.get(key), str) and case[key], f'Missing {key}')
        sections = case.get('sections')
        require(isinstance(sections, list) and sections, 'Missing original source sections')
        section_ids, node_ids = set(), set()
        for section in sections:
            require(isinstance(section, dict) and safe_id(section.get('id')) and section['id'] not in section_ids, 'Invalid section ID')
            require(isinstance(section.get('source_node_id'), str) and section['source_node_id']
                    and section['source_node_id'] not in node_ids, 'Source-node mapping is not one-to-one')
            section_ids.add(section['id'])
            node_ids.add(section['source_node_id'])
            require(isinstance(section.get('heading'), str), 'Section heading must be text')
            require(isinstance(section.get('original_text'), str) and section['original_text'].strip(), 'Original source text is empty')
            require(section.get('zh_text') is None or isinstance(section['zh_text'], str), 'Translation must be text or null')
            require(section.get('zh_heading') is None or isinstance(section['zh_heading'], str), 'Translated heading must be text or null')
        predictions = case.get('sa_predictions')
        require(isinstance(predictions, list), 'Expected sa_predictions list')
        seen_models = set()
        for prediction in predictions:
            require(isinstance(prediction, dict) and prediction.get('model') in model_ids
                    and prediction['model'] not in seen_models, 'Duplicate or unknown prediction model')
            seen_models.add(prediction['model'])
            require(prediction.get('status') in ('available', 'pending', 'invalid'), 'Unknown prediction status')
            risk = prediction.get('risk_found')
            require(risk is None or type(risk) is bool, 'risk_found must be true, false or null')
            require(prediction['status'] == 'available' or risk is None, 'Pending/invalid results cannot assert a risk decision')
            count = prediction.get('risk_pair_count')
            require(count is None or (type(count) is int and count >= 0), 'Invalid risk pair count')
            require(isinstance(prediction.get('reason'), str), 'Missing prediction reason')
            evidence = prediction.get('evidence_sections')
            require(isinstance(evidence, list) and all(isinstance(item, str) and item in section_ids for item in evidence),
                    'Prediction evidence does not map to the displayed sections')
    require(isinstance(data.get('node_results_pack_hash'), str) and HASH.fullmatch(data['node_results_pack_hash']),
            'Missing node-result identity')
    nodes = data.get('node_results')
    require(isinstance(nodes, dict) and set(nodes) == case_ids, 'Node hints must cover exactly this batch')
    for case in cases:
        require(set(nodes[case['id']]) == {s['id'] for s in case['sections']}, 'Node hints do not match displayed sections')
        for section in case['sections']:
            methods = nodes[case['id']][section['id']].get('methods')
            require(isinstance(methods, dict) and set(methods) == {'sa-mcgs', 'lea'}, 'Missing method hints')
            for method in methods.values():
                models = method.get('models')
                require(isinstance(models, dict) and set(models) == model_ids, 'Missing model node hints')
                for hint in models.values():
                    require(hint.get('status') in ('available', 'not_run', 'strict_invalid', 'missing'), 'Invalid node-hint status')
                    if hint['status'] != 'available':
                        require(isinstance(hint.get('reason_zh'), str) and hint['reason_zh'], 'Unavailable hint needs a reason')
                        require(not any(k in hint for k in ('score', 'rank', 'selected')), 'Unavailable results cannot imply a score/selection')
                        continue
                    require(type(hint.get('selected')) is bool and type(hint.get('top3')) is bool, 'Invalid selection fields')
                    require(hint.get('total_nodes') == len(case['sections']), 'Wrong node count')
                    score, rank = hint.get('score'), hint.get('rank')
                    require(score is None or type(score) in (int, float) and math.isfinite(score), 'Invalid node score')
                    require(rank is None or type(rank) is int and 1 <= rank <= len(case['sections']), 'Invalid node rank')
                    require(hint['top3'] == (rank is not None and rank <= 3), 'Top-three flag disagrees with ranking')
                    for key in ('conflict_endpoint_mentions', 'local_evidence_mentions', 'repair_entry_mentions'):
                        require(type(hint.get(key)) is int and hint[key] >= 0, 'Invalid mention count')
    history = data.get('historical_annotations')
    require(isinstance(history, dict) and history.get('schema_version') == 'pre18_historical_annotations.v1', 'Missing historical annotation pack')
    canonical = json.dumps({k: v for k, v in history.items() if k != 'pack_hash'}, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    require(history.get('pack_hash') == 'sha256:' + hashlib.sha256(canonical).hexdigest(), 'Historical pack identity mismatch')
    require(set(history.get('experts', {})) == {'expert_1', 'expert_2'}, 'Only original experts 1 and 2 may be prefilled')
    for slot, source in history['experts'].items():
        require(set(source.get('annotations', {})) == case_ids, f'Incomplete original votes for {slot}')
        require(set(source.get('case_provenance', {})) == case_ids, f'Incomplete original provenance for {slot}')
        require(HASH.fullmatch(source['provenance'].get('source_sha256', '')), 'Missing original file hash')
        for case in cases:
            record = source['annotations'][case['id']]
            provenance = source['case_provenance'][case['id']]
            require(record['case_id'] == case['id'] and record['content_hash'] == case['content_hash'], 'Original case mismatch')
            require(record['target_conflict'] in ('present', 'absent') and record['judgment_sufficient'] in ('sufficient', 'insufficient'), 'Invalid original judgment')
            require(type(record['confidence']) is int and 1 <= record['confidence'] <= 5, 'Invalid original confidence')
            require(record['confirmed'] is True and record['sets_reviewed'] is True, 'Original vote was not complete')
            require(record['confirmed_at'] == record['updated_at'] == provenance['source_saved_at'], 'Historical timestamp changed')
            require(datetime.fromisoformat(record['updated_at'].replace('Z', '+00:00')).tzinfo is not None, 'Invalid original save time')
            require(set(record['sections']) == {s['id'] for s in case['sections']}, 'Original section mismatch')
            for answer in record['sections'].values():
                require(type(answer.get('minimal_evidence')) is bool and type(answer.get('repair_material')) is bool
                        and (not answer['minimal_evidence'] or answer['repair_material']), 'Invalid original evidence selection')
    return data


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(payload_path):
    raw = payload_path.read_bytes()
    data = validate_payload(json.loads(raw))
    source_paths = {name: ROOT/'ui'/name for name in ('template.html', 'styles.css', 'annotation.js')}
    source = {name: path.read_text(encoding='utf-8') for name, path in source_paths.items()}
    # JSON cannot terminate its inert <script> element; model/source text is never HTML.
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    payload = payload.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    js = re.sub(r'</script', r'<\\/script', source['annotation.js'], flags=re.I)
    css = re.sub(r'</style', r'<\\/style', source['styles.css'], flags=re.I)
    html = source['template.html']
    for marker, value in {'__APP_CSS__': css, '__PAYLOAD_JSON__': payload, '__APP_JS__': js}.items():
        require(html.count(marker) == 1, f'Expected exactly one {marker} template marker')
        html = html.replace(marker, value)
    require(not re.search(r'__(?:APP_CSS|APP_JS|PAYLOAD_JSON)__', html), 'Unreplaced template marker')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix('.html.tmp')
    temporary.write_text(html, encoding='utf-8')
    temporary.replace(OUTPUT)
    sections = [section for case in data['cases'] for section in case['sections']]
    receipt = {'built_at': datetime.now(timezone.utc).isoformat(), 'study_id': data['study_id'],
        'annotation_mode': 'method_assisted_reannotation', 'annotation_protocol': 'pre30_binary_judgment.v1',
        'sa_visible': True, 'case_count': len(data['cases']), 'section_count': len(sections),
        'translated_sections': sum(isinstance(section.get('zh_text'), str) and bool(section['zh_text'].strip()) for section in sections),
        'prediction_statuses': dict(Counter(prediction['status'] for case in data['cases'] for prediction in case['sa_predictions'])),
        'manifest_hash': data['manifest_hash'], 'prediction_pack_hash': data['prediction_pack_hash'],
        'node_results_pack_hash': data['node_results_pack_hash'], 'method_hints_visible': data['method_hints_visible'],
        'payload_path': str(payload_path.resolve()), 'payload_sha256': sha(raw),
        'source_sha256': {name: sha(path.read_bytes()) for name, path in source_paths.items()},
        'output': str(OUTPUT), 'output_sha256': sha(OUTPUT.read_bytes()), 'model_calls': 0,
        'legacy_annotations_read': True,
        'historical_annotations_pack_hash': data['historical_annotations']['pack_hash'],
        'historical_annotations_per_expert': {slot: len(value['annotations']) for slot, value in data['historical_annotations']['experts'].items()},
        'third_expert_prefilled': False, 'standalone': True}
    (OUTPUT.parent/'build_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, default=ROOT/'payload.json')
    args = parser.parse_args()
    active_path = ROOT/'active_page.json'
    if active_path.exists():
        active = json.loads(active_path.read_text(encoding='utf-8'))
        if active.get('builder') == 'third_review_20261010/build_blind.py':
            if args.payload != ROOT/'payload.json':
                parser.error('The active page is the dedicated blind batch; use third_review_20261010/build_blind.py.')
            import importlib.util
            spec = importlib.util.spec_from_file_location('active_blind_builder', ROOT/active['builder'])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            print(json.dumps(module.build(), ensure_ascii=False, indent=2))
            return
    print(json.dumps(build(args.payload), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

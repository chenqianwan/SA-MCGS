"""Verify pre-only node mapping against the prior reviewed annotation pack."""
from pathlib import Path
import collections, json

ROOT = Path(__file__).resolve().parent
PREP = ROOT.parent
data = json.loads((ROOT/'payload.json').read_text())
original = json.loads((ROOT/'qa/node_hints_before/payload.json').read_text())
assert data['cases'] == original['cases'][:18]
assert data['models'] == original['models']
for key in ('study_id', 'manifest_hash', 'prediction_pack_hash'):
    assert data['predecessor'][key] == original[key], key
old = json.loads((PREP/'frontend/data/method_hints.json').read_text())
code = json.loads((PREP/'internal/private_codebook.json').read_text())
by_source = {r['master_record']['pre_source_id']: r for r in code['records'] if r['master_record'].get('unmodified')}
checked = 0
statuses = collections.Counter()
for case in data['cases']:
    record = by_source.get(case['pre_source_id'])
    if not record:
        for node in data['node_results'][case['id']].values():
            for method in node['methods'].values():
                for hint in method['models'].values():
                    assert hint['status'] == 'not_run'
        continue
    old_case = old['cases'][record['presentation_id']]
    assert old_case['condition'] == 'pre'
    mapping = {r['original_node_id']: r['section_id'] for r in record['section_map']}
    for section in case['sections']:
        hints = data['node_results'][case['id']][section['id']]['methods']
        previous = old_case['sections'][mapping[section['source_node_id']]]['methods']
        for method in ('sa-mcgs', 'lea'):
            for model in (m['id'] for m in data['models']):
                now, before = hints[method]['models'][model], previous[method]['models'][model]
                assert now == before, (case['id'], section['id'], method, model, now, before)
                checked += 1
                statuses[now['status']] += 1
report = {'old_node_method_model_hints_equal': checked, 'old_status_counts': dict(statuses),
          'extra_12_cases_excluded': len(data['cases']) == 18, 'no_post_data': True,
          'section_count': sum(len(c['sections']) for c in data['cases']),
          'retained_case_content_and_results_unchanged': True, 'exact_predecessor_identity_saved': True}
(ROOT/'qa/node_hints_data_check.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))

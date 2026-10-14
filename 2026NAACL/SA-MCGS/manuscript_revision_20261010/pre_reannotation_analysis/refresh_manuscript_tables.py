#!/usr/bin/env python3
"""Refresh current source-vote IAA and provenance, preserving all model results.

Run after integrate.py, refresh_current_decisions.py, and manuscript sync.
Repeated runs with unchanged inputs produce byte-identical outputs.
"""
import copy
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
JSON_PATH = HERE / 'manuscript_tables_20261010.json'
MD_PATH = HERE / 'manuscript_tables_20261010.md'


def read(name):
    return json.loads((HERE / name).read_text())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    data = read(JSON_PATH.name)
    original = copy.deepcopy(data)
    records = read('integrated_annotations.json')['records']
    reference = {(tuple(row['raters']), row['condition']): row
                 for row in read('agreement.json')['rows']}
    final = read('current_expert_final_decisions.json')
    comparison = read('existence_only_sa_comparison.json')
    targets = {row['case_id']: row['expert_target_conflict'] for row in final['records']}
    assert data['final_existence_labels']['records'] == final['records']
    assert Counter(targets.values()) == final['expert_counts']

    # This refresh is for votes/IAA, not new model decisions or final labels.
    predictions = {(row['case_id'], model): value['sa_risk_found']
                   for row in comparison['rows'] for model, value in row['sa'].items()}
    for row in data['table10']['final_verified_case_outcomes']:
        assert row['prediction'] is predictions[row['case_id'], row['model']]
        assert row['expert_target_conflict'] == targets[row['case_id']]

    for row in data['agreement']['rows']:
        first, second = row['raters']
        selected = [item for item in records
                    if first in item['original_ratings'] and second in item['original_ratings']
                    and (row['condition'] == 'all' or item['condition'] == row['condition'])]
        n = len(selected)
        assert n == row['n']
        row['case_ids'] = [item.get('case_id', item['presentation_id']) for item in selected]
        for field in ['target_conflict', 'judgment_sufficient']:
            a = [item['original_ratings'][first][field] for item in selected]
            b = [item['original_ratings'][second][field] for item in selected]
            ca, cb = Counter(a), Counter(b)
            count = sum(x == y for x, y in zip(a, b))
            expected = sum(ca[key] * cb[key] for key in ca.keys() | cb.keys()) / n ** 2
            row[field] = dict(
                agreement_count=count, n=n, observed_agreement=count / n,
                cohen_kappa=(count / n - expected) / (1 - expected) if expected < 1 else None,
                label_counts={first: dict(ca), second: dict(cb)})
        row['joint_agreement_count'] = sum(
            all(item['original_ratings'][first][field] == item['original_ratings'][second][field]
                for field in ['target_conflict', 'judgment_sufficient']) for item in selected)
        for field in ['minimal_evidence_section_ids', 'repair_packet_section_ids']:
            pairs = [(set(item['original_ratings'][first][field]),
                      set(item['original_ratings'][second][field])) for item in selected]
            scores = [len(a & b) / len(a | b) if a | b else 1.0 for a, b in pairs]
            nonempty = [score for score, (a, b) in zip(scores, pairs) if a | b]
            row[field] = dict(mean_jaccard=mean(scores),
                              exact_agreement_count=sum(a == b for a, b in pairs),
                              nonempty_union_n=len(nonempty),
                              mean_jaccard_excluding_both_empty=mean(nonempty) if nonempty else None)
        expected_row = reference[tuple(row['raters']), row['condition']]
        for field in ['target_conflict', 'judgment_sufficient']:
            assert row[field]['agreement_count'] == expected_row[field]['agreement_count']
            assert row[field]['cohen_kappa'] == expected_row[field]['cohen_kappa']
        assert row['joint_agreement_count'] == expected_row['joint_agreement_count']

    agreement = data['agreement']
    agreement['current_full_vote_counts'] = dict(Counter(
        expert for item in records for expert in item['original_ratings']))
    agreement['total_full_votes'] = sum(len(item['original_ratings']) for item in records)
    agreement['pre_full_votes'] = sum(len(item['original_ratings']) for item in records
                                      if item['condition'] == 'pre')
    agreement['retained_post_full_votes'] = sum(len(item['original_ratings']) for item in records
                                                if item['condition'] == 'post')
    assert data['table10'] == original['table10']
    assert data['unchanged_post_table9'] == original['unchanged_post_table9']
    for old, new in zip(original['agreement']['rows'], agreement['rows']):
        if old['condition'] == 'post':
            assert old == new
        for field in ['judgment_sufficient', 'minimal_evidence_section_ids', 'repair_packet_section_ids']:
            assert old[field] == new[field]

    paths = {item['path'] for item in data['provenance']['source_files']}
    paths.add(str(Path(__file__).resolve()))
    for name in ['integrated_annotations.json', 'agreement.json', 'current_case_annotations.json',
                 'current_analysis_manifest.json', 'current_expert_final_decisions.json',
                 'existence_only_sa_comparison.json', 'source_manifest.json', 'manuscript_data_sync.json']:
        path = HERE / name
        if path.is_file():
            paths.add(str(path))
    hashes = {path: sha(path) for path in sorted(paths)}
    for source in original['provenance']['source_files']:
        if '/experiments/' in source['path']:
            assert hashes[source['path']] == source['sha256'], source['path']
    data['provenance']['source_files'] = [dict(path=path, sha256=value) for path, value in hashes.items()]
    data['provenance']['source_inputs_verified_for_current_build'] = True
    data['provenance']['frozen_prediction_or_log_files_unchanged'] = True

    markdown = MD_PATH.read_text()
    for row in agreement['rows']:
        n = row['n']
        first = row['target_conflict']
        second = row['judgment_sufficient']
        def format_kappa(value):
            return 'undefined' if value is None else f'{value:.3f}'
        prefix = f"| {'/'.join(row['raters'])} | {row['condition']} |"
        replacement = (f"{prefix} {n} | {first['agreement_count']}/{n} | "
                       f"{format_kappa(first['cohen_kappa'])} | {second['agreement_count']}/{n} | "
                       f"{format_kappa(second['cohen_kappa'])} | {row['joint_agreement_count']}/{n} |")
        matches = [line for line in markdown.splitlines() if line.startswith(prefix)]
        assert len(matches) == 1, prefix
        markdown = markdown.replace(matches[0], replacement)
    if data != original:
        data['generated_at'] = datetime.now(timezone.utc).isoformat()
        JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    if markdown != MD_PATH.read_text():
        MD_PATH.write_text(markdown)
    print(json.dumps(dict(
        rows=len(agreement['rows']), final_labels=final['expert_counts'],
        model_rows_unchanged=True, post_table9_unchanged=True,
        source_hashes=len(hashes), json_sha256=sha(JSON_PATH), md_sha256=sha(MD_PATH)), indent=2))


if __name__ == '__main__':
    main()

"""Offline unit/integrity checks. Never changes real expert annotations."""
import copy
import hashlib
import importlib.util
import json
import re
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('review_builder', ROOT / 'build_review.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def rating(target='present', sufficient='yes', confidence=4, m=('S1', 'S2'), r=('S1', 'S2', 'S3')):
    return dict(target_conflict=target, judgment_sufficient=sufficient, confidence=confidence,
                minimal_evidence_section_ids=list(m), repair_packet_section_ids=list(r))


class SelectionTests(unittest.TestCase):
    def test_identical_no_trigger(self):
        self.assertEqual(builder.reasons_for(rating(), rating())[0], [])

    def test_half_overlap_not_triggered(self):
        a, b = rating(m=('S1',)), rating(m=('S1', 'S2'))
        reasons, jm, _ = builder.reasons_for(a, b)
        self.assertEqual(jm, .5)
        self.assertEqual(reasons, [])

    def test_less_than_half_triggered(self):
        a, b = rating(m=('S1',)), rating(m=('S1', 'S2', 'S3'))
        self.assertIn('minimal_low_overlap', builder.reasons_for(a, b)[0])

    def test_empty_empty_is_one(self):
        self.assertEqual(builder.jaccard([], []), 1)

    def test_negative_repair_disagreement_not_triggered(self):
        a = rating('absent', m=(), r=('S1',))
        b = rating('absent', m=(), r=('S2',))
        self.assertEqual(builder.reasons_for(a, b)[0], [])

    def test_low_confidence_threshold(self):
        self.assertIn('low_confidence', builder.reasons_for(rating(confidence=2), rating())[0])
        self.assertNotIn('low_confidence', builder.reasons_for(rating(confidence=3), rating())[0])

    def test_any_insufficient_even_if_both_same(self):
        self.assertIn('insufficient', builder.reasons_for(rating(sufficient='no'), rating(sufficient='no'))[0])

    def test_conflict_disagreement(self):
        self.assertIn('target_disagreement', builder.reasons_for(rating(), rating('absent', m=()))[0])

    def test_frozen_package(self):
        public = builder.load(ROOT / 'data/manifest.json')
        translated = builder.load(ROOT / 'data/translations_zh.json')
        audit = builder.load(ROOT / 'internal/selection_audit.json')
        parent = builder.load(ROOT.parent / 'frontend/data/manifest.json')
        parents = {c['presentation_id']: c for c in parent['cases']}
        self.assertEqual(len(public['cases']), 14)
        self.assertEqual(sum(len(c['sections']) for c in public['cases']), 264)
        self.assertEqual(audit['summary']['conditions'], {'pre': 9, 'post': 5})
        self.assertEqual(len(audit['decisions']), 42)
        self.assertEqual({c['presentation_id'] for c in public['cases']}, {r['presentation_id'] for r in audit['decisions'] if r['selected']})
        self.assertEqual(list(public['expert_orders']), ['expert_3'])
        self.assertEqual(public['expert_orders']['expert_3'], [p for p in parent['expert_orders']['expert_3'] if p in public['expert_orders']['expert_3']])
        self.assertEqual(set(translated['cases']), {c['presentation_id'] for c in public['cases']})
        for case in public['cases']:
            self.assertEqual(case, parents[case['presentation_id']])
            self.assertEqual(set(case), {'presentation_id', 'domain_label', 'sections'})
            self.assertEqual(set(translated['cases'][case['presentation_id']]['sections']), {s['section_id'] for s in case['sections']})
        body = copy.deepcopy(public)
        digest = body.pop('manifest_hash')
        self.assertEqual(builder.canonical_hash(body), digest)
        body = copy.deepcopy(translated)
        digest = body.pop('translation_pack_hash')
        self.assertEqual(builder.canonical_hash(body), digest)
        self.assertEqual(translated['source_manifest_hash'], public['manifest_hash'])
        for item in audit['inputs']:
            self.assertEqual(hashlib.sha256(Path(item['path']).read_bytes()).hexdigest(), item['sha256'])
        for row in audit['decisions']:
            self.assertEqual(row['reasons'], builder.reasons_for(row['expert_1'], row['expert_2'])[0])

    def test_hint_subset_matches_original(self):
        public = builder.load(ROOT / 'data/manifest.json')
        hints = builder.load(ROOT / 'data/method_hints.json')
        original = builder.load(ROOT.parent / 'frontend/data/method_hints.json')
        self.assertEqual(hints['source_manifest_hash'], public['manifest_hash'])
        self.assertEqual(hints['parent_hint_pack_hash'], original['hint_pack_hash'])
        self.assertEqual(set(hints['cases']), {c['presentation_id'] for c in public['cases']})
        statuses = []
        for pid, case in hints['cases'].items():
            self.assertEqual(set(case), {'identity_verified', 'sections'})
            self.assertTrue(case['identity_verified'])
            self.assertEqual(case['sections'], original['cases'][pid]['sections'])
            for section in case['sections'].values():
                for method in section['methods'].values():
                    for cell in method['models'].values():
                        statuses.append(cell['status'])
        self.assertEqual(len(statuses), 1056)
        self.assertEqual(statuses.count('available'), 947)
        self.assertEqual(statuses.count('strict_invalid'), 109)
        body = copy.deepcopy(hints)
        digest = body.pop('hint_pack_hash')
        self.assertEqual(builder.canonical_hash(body), digest)


class InjectionMarkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.public = builder.load(ROOT / 'data/manifest.json')
        cls.markers = builder.load(ROOT / 'data/injection_markers.json')
        parent_html = (ROOT.parent / 'dist/sa_mcgs_blind_annotation.html').read_text(encoding='utf-8')
        cls.parent_markers = json.loads(re.findall(
            r'<script\b[^>]*\bid="injectionMarkersData"[^>]*>(.*?)</script>', parent_html, re.S,
        )[0])

    def test_frozen_marker_subset_matches_parent_and_contains_only_public_fields(self):
        markers = self.markers
        self.assertEqual(set(markers), {'schema_version', 'source_manifest_hash', 'parent_manifest_hash',
                                        'parent_marker_pack_hash', 'cases', 'marker_pack_hash'})
        self.assertEqual(markers['schema_version'], 'third_expert_injection_markers.v1')
        self.assertEqual(markers['source_manifest_hash'], self.public['manifest_hash'])
        self.assertEqual(markers['parent_manifest_hash'], self.public['parent_manifest_hash'])
        self.assertEqual(markers['parent_marker_pack_hash'], self.parent_markers['marker_pack_hash'])
        self.assertEqual(list(markers['cases']), self.public['expert_orders']['expert_3'])
        self.assertEqual(Counter(c['condition'] for c in markers['cases'].values()), {'pre': 9, 'post': 5})
        self.assertEqual(sum(len(c['modified_section_ids']) for c in markers['cases'].values()), 13)
        section_counts = Counter()
        for case in self.public['cases']:
            pid = case['presentation_id']
            marker = markers['cases'][pid]
            self.assertEqual(set(marker), {'condition', 'modified_section_ids'})
            self.assertEqual(marker, self.parent_markers['cases'][pid])
            self.assertEqual(len(marker['modified_section_ids']), len(set(marker['modified_section_ids'])))
            self.assertLessEqual(set(marker['modified_section_ids']), {s['section_id'] for s in case['sections']})
            self.assertEqual(bool(marker['modified_section_ids']), marker['condition'] == 'post')
            section_counts[marker['condition']] += len(case['sections'])
        self.assertEqual(section_counts, {'pre': 178, 'post': 86})
        self.assertEqual({pid: m['modified_section_ids'] for pid, m in markers['cases'].items() if m['condition'] == 'post'}, {
            'P-6E178B900A': ['S009', 'S014'],
            'P-69C4BFE2A4': ['S013', 'S017'],
            'P-4BAF2F94CC': ['S006', 'S009', 'S014'],
            'P-C30711E2A7': ['S003', 'S006', 'S009'],
            'P-1E0D6A4D66': ['S002', 'S003', 'S007'],
        })
        body = {k: v for k, v in markers.items() if k != 'marker_pack_hash'}
        self.assertEqual(builder.canonical_hash(body), markers['marker_pack_hash'])

    def test_rebuild_is_deterministic_and_preserves_existing_materials(self):
        public = copy.deepcopy(self.public)
        paths = [ROOT / 'data' / name for name in ('manifest.json', 'translations_zh.json', 'method_hints.json')]
        paths += [ROOT.parent / 'dist/sa_mcgs_blind_annotation.html',
                  ROOT / 'dist/第三专家_独立盲评.original.html', ROOT / 'dist/第三专家_离线打标包.original.zip']
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        with patch.object(builder, 'dump') as write:
            result = builder.subset_injection_markers(public)
        self.assertEqual(result, self.markers)
        write.assert_called_once_with(ROOT / 'data/injection_markers.json', result)
        self.assertEqual(public, self.public)
        self.assertEqual({path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}, before)

    def test_modified_subset_material_is_rejected_even_with_recomputed_hash(self):
        public = copy.deepcopy(self.public)
        public['cases'][0]['sections'][0]['text'] += ' changed'
        public['manifest_hash'] = builder.canonical_hash({k: v for k, v in public.items() if k != 'manifest_hash'})
        with patch.object(builder, 'dump') as write:
            with self.assertRaisesRegex(ValueError, 'subset identity mismatch'):
                builder.subset_injection_markers(public)
        write.assert_not_called()

    def test_duplicate_subset_identity_is_rejected(self):
        public = copy.deepcopy(self.public)
        public['cases'][1] = copy.deepcopy(public['cases'][0])
        public['manifest_hash'] = builder.canonical_hash({k: v for k, v in public.items() if k != 'manifest_hash'})
        with self.assertRaisesRegex(ValueError, '14 unique'):
            builder.subset_injection_markers(public)

    def test_changed_parent_marker_pack_is_rejected_even_with_recomputed_hash(self):
        changed = copy.deepcopy(self.parent_markers)
        changed['cases']['P-6E178B900A']['modified_section_ids'] = ['S001']
        changed['marker_pack_hash'] = builder.canonical_hash({k: v for k, v in changed.items() if k != 'marker_pack_hash'})
        with patch.object(builder, 'build_injection_markers', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'frozen parent page'):
                builder.subset_injection_markers(self.public)

    def test_changed_frozen_injection_identity_is_rejected_by_source_diff(self):
        source_globals = builder.build_injection_markers.__globals__
        read_source = source_globals['load_json']

        def altered_source(path):
            value = read_source(path)
            if path.name == 'selected_post_36.json':
                # All selected post identities become inconsistent with their
                # actual pre/post text differences; a hash-only check misses this.
                for case in value:
                    case['injection_identity']['evidence_nodes'] = []
            return value

        with patch.dict(source_globals, {'load_json': altered_source}):
            with self.assertRaisesRegex(ValueError, 'Text edits disagree with frozen injection identity'):
                builder.subset_injection_markers(self.public)


if __name__ == '__main__':
    unittest.main()

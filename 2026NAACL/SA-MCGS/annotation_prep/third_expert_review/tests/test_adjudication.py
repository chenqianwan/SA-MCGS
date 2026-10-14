"""Source-preserving checks for designated-third-expert resolution."""
import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


class AdjudicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load(ROOT / 'internal/adjudication_20260920/adjudicated_records.json')
        cls.audit = load(ROOT / 'internal/selection_audit.json')
        cls.records = {r['presentation_id']: r for r in cls.bundle['records']}

    def test_scope_and_real_rating_count(self):
        self.assertEqual(len(self.records), 42)
        self.assertEqual(sum(len(r['original_ratings']) for r in self.records.values()), 98)
        selected = {r['presentation_id'] for r in self.audit['decisions'] if r['selected']}
        self.assertEqual({pid for pid, r in self.records.items() if r['reviewed_by_expert_3']}, selected)
        self.assertEqual(len(selected), 14)

    def test_third_complete_answer_is_the_only_resolution_source(self):
        for r in self.records.values():
            if not r['reviewed_by_expert_3']:
                self.assertNotIn('expert_3', r['original_ratings'])
                self.assertIsNone(r['final_label'])
                continue
            original = dict(r['original_ratings']['expert_3'])
            original.pop('source_xlsx_row')
            final = dict(r['final_label'])
            scoring = final.pop('scoring_status')
            self.assertEqual(final, original)
            self.assertEqual(scoring, 'negative' if final['target_conflict'] == 'absent' else 'positive')
            self.assertLessEqual(set(final['minimal_evidence_section_ids']), set(final['repair_packet_section_ids']))

    def test_previous_votes_preserved_even_when_overruled(self):
        for old in self.audit['decisions']:
            for slot in ('expert_1', 'expert_2'):
                actual = dict(self.records[old['presentation_id']]['original_ratings'][slot])
                self.assertEqual(actual.pop('source_xlsx_row'), old[slot]['xlsx_row'])
                self.assertEqual(actual, {k: v for k, v in old[slot].items() if k != 'xlsx_row'})
        for pid in ('P-86752D8428', 'P-124E4D04CF', 'P-44C73A652D'):
            self.assertEqual(self.records[pid]['final_label']['target_conflict'], 'absent')
            self.assertEqual(self.records[pid]['final_label']['judgment_sufficient'], 'yes')

    def test_counts_and_non_preregistered_policy(self):
        counts = Counter(f"{r['condition']}:{r['final_label']['scoring_status']}" for r in self.records.values() if r['final_label'])
        self.assertEqual(counts, {'pre:negative': 9, 'post:positive': 5})
        self.assertFalse(self.bundle['policy']['preregistered'])
        self.assertFalse(self.bundle['summary']['full_42_unique_material_set_gold_frozen'])
        self.assertEqual(self.bundle['policy']['instruction_verbatim'], '争议以第三位专家为准')

    def test_checksums_and_source_workbooks_unchanged(self):
        body = {k: v for k, v in self.bundle.items() if k != 'artifact_hash'}
        digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(self.bundle['artifact_hash'], 'sha256:' + digest)
        for source in self.bundle['source_files']:
            self.assertEqual(hashlib.sha256(Path(source['path']).read_bytes()).hexdigest(), source['sha256'])


if __name__ == '__main__':
    unittest.main()

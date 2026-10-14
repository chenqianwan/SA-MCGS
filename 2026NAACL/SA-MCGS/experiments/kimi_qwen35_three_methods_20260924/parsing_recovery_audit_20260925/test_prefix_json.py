import json
import unittest
from prefix_json import audit_json_prefix


class PrefixTests(unittest.TestCase):
    def test_complete_nested_values_and_escaped_strings(self):
        value = {'ranking': [['a', 0.8]], 'explanation': 'quote " slash \\ braces } ]',
                 'nested': {'unicode': '\u4e2d', 'items': [True, False, None, -1.5e2]}}
        report = audit_json_prefix(json.dumps(value))
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['root']['value'], value)
        self.assertEqual(report['complete_fields'], value)

    def test_partial_nested_risk_retains_closed_nodes_field(self):
        report = audit_json_prefix('{"ranking":[["a",0.8]],"risk_subgraph":{"nodes":["a","b"],"edges":[')
        risk = report['root']['fields']['risk_subgraph']
        self.assertEqual(report['complete_fields'], {'ranking': [['a', 0.8]]})
        self.assertFalse(risk['complete'])
        self.assertEqual(risk['fields']['nodes']['value'], ['a', 'b'])
        self.assertTrue(risk['fields']['nodes']['usable'])
        self.assertFalse(risk['fields']['edges']['complete'])

    def test_partial_ranking_retains_only_closed_rows(self):
        ranking = audit_json_prefix('{"ranking":[["a",0.8],["b",0.')['root']['fields']['ranking']
        self.assertFalse(ranking['complete'])
        self.assertEqual(ranking['complete_elements'], [{'index': 0, 'value': ['a', 0.8]}])
        self.assertFalse(ranking['items'][1]['usable'])
        self.assertNotIn('value', ranking['items'][1])

    def test_partial_array_closed_strings_are_exact_elements(self):
        nodes = audit_json_prefix('{"nodes":["a","b"')['root']['fields']['nodes']
        self.assertEqual(nodes['complete_elements'], [{'index': 0, 'value': 'a'}, {'index': 1, 'value': 'b'}])
        self.assertFalse(nodes['complete'])

    def test_duplicate_keys_never_choose_an_occurrence(self):
        report = audit_json_prefix('{"nodes":["a"],"nodes":["b"],"safe":3}')
        duplicate = report['root']['fields']['nodes']
        self.assertEqual(duplicate['kind'], 'duplicate_key')
        self.assertFalse(duplicate['usable'])
        self.assertNotIn('value', duplicate)
        self.assertEqual(len(duplicate['occurrences']), 2)
        self.assertEqual(report['complete_fields'], {'safe': 3})
        self.assertEqual(report['status'], 'invalid')

    def test_second_duplicate_partial_value_invalidates_first(self):
        report = audit_json_prefix('{"nodes":["a"],"nodes":[')
        self.assertFalse(report['root']['fields']['nodes']['usable'])
        self.assertNotIn('nodes', report['complete_fields'])

    def test_incomplete_escape_never_becomes_value(self):
        for tail in ['\\', '\\u12', '\\"']:
            node = audit_json_prefix('{"text":"unfinished' + tail)['root']['fields']['text']
            self.assertFalse(node['complete'])
            self.assertNotIn('value', node)

    def test_number_at_truncation_boundary_is_not_guessed(self):
        report = audit_json_prefix('{"values":[1,23')
        items = report['root']['fields']['values']['items']
        self.assertEqual(items[0]['value'], 1)
        self.assertFalse(items[1]['complete'])
        self.assertNotIn('value', items[1])
        self.assertEqual(audit_json_prefix('23')['root']['value'], 23)

    def test_no_nested_regex_matching_or_prose_search(self):
        report = audit_json_prefix('{"explanation":"fake \\"nodes\\": [1]"}')
        self.assertNotIn('nodes', report['complete_fields'])
        report = audit_json_prefix('Here is the JSON: {"nodes":["a"]}')
        self.assertEqual(report['status'], 'invalid')
        self.assertEqual(report['complete_fields'], {})

    def test_only_explicit_fence_wrapper(self):
        report = audit_json_prefix('```json\n{"nodes":["a"]}\n```\n')
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['complete_fields'], {'nodes': ['a']})
        self.assertEqual(report['root']['start'], 8)

    def test_malformed_and_trailing_content_remains_flagged(self):
        for text in ['{"a":1,}', '{"a":1} trailing', '{"a":"bad\\q"}']:
            self.assertEqual(audit_json_prefix(text)['status'], 'invalid')


if __name__ == '__main__':
    unittest.main()

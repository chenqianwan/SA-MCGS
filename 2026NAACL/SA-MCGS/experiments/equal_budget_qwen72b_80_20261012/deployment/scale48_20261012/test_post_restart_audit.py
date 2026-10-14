"""Isolated tests for live-ledger audit semantics; no cluster or model access."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('audit_under_test', Path(__file__).with_name('post_restart_audit.py'))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class LedgerAuditTests(unittest.TestCase):
    OWNER = ('case', audit.MODEL, 'lea')

    def events(self):
        return [
            {'event': 'header', 'version': 1, 'accounting': 'actual_local_vllm_tokens',
             'external_api_enabled': False, 'unknown_outcome': 'retain_full_reservation'},
            {'event': 'owner', 'owner': list(self.OWNER), 'token_cap': 100, 'fingerprint': 'fp'},
            {'event': 'reserve', 'call_id': 'one', 'owner': list(self.OWNER), 'request_key': 'call-0',
             'input_tokens': 10, 'max_output_tokens': 20, 'reserved_tokens': 30, 'cache_file': 'calls/one.json'},
            {'event': 'finish', 'call_id': 'one', 'status': 'completed_with_usage', 'usage_issues': [],
             'prompt_tokens': 10, 'completion_tokens': 5, 'actual_total_tokens': 15,
             'provider_model': audit.MODEL, 'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}},
        ]

    def raw(self, events):
        return ''.join(json.dumps(event) + '\n' for event in events).encode()

    def test_live_pending_request_is_expected_and_counted_once(self):
        events = self.events()
        pending = copy.deepcopy(events[2])
        pending.update(call_id='two', request_key='call-1')
        events.append(pending)
        _, value = audit.parse_ledger(self.raw(events), self.OWNER, 100)
        self.assertEqual(value['total_tokens'], 15)
        self.assertEqual(value['held_tokens'], 30)
        self.assertEqual(value['accounted_tokens'], 45)
        self.assertEqual(value['pending_calls'], 1)

    def test_duplicate_request_key_with_new_call_id_is_rejected(self):
        events = self.events()
        duplicate = copy.deepcopy(events[2])
        duplicate['call_id'] = 'duplicate'
        events.append(duplicate)
        with self.assertRaisesRegex(audit.AuditError, 'Duplicate call or owner/request_key'):
            audit.parse_ledger(self.raw(events), self.OWNER, 100)

    def test_duplicate_settlement_is_rejected(self):
        events = self.events()
        events.append(copy.deepcopy(events[-1]))
        with self.assertRaisesRegex(audit.AuditError, 'Duplicate or unknown settlement'):
            audit.parse_ledger(self.raw(events), self.OWNER, 100)

    def test_additional_parse_events_do_not_charge_again(self):
        events = self.events()
        events.extend([{'event': 'parse', 'call_id': 'one', 'outcome': 'dict'}] * 2)
        calls, value = audit.parse_ledger(self.raw(events), self.OWNER, 100)
        self.assertEqual(len(calls), 1)
        self.assertEqual(value['total_tokens'], 15)

    def test_unknown_usage_is_failure(self):
        events = self.events()
        events[-1]['status'] = 'unknown_failure'
        with self.assertRaisesRegex(audit.AuditError, 'Unknown/missing/mismatched'):
            audit.parse_ledger(self.raw(events), self.OWNER, 100)

    def test_pending_reservation_over_cap_is_failure(self):
        events = self.events()
        pending = copy.deepcopy(events[2])
        pending.update(call_id='two', request_key='call-1', max_output_tokens=100, reserved_tokens=110)
        events.append(pending)
        with self.assertRaisesRegex(audit.AuditError, 'exceed frozen cap'):
            audit.parse_ledger(self.raw(events), self.OWNER, 100)

    def test_unfinished_tail_requests_retry_instead_of_parsing_partial_event(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            folder = root / 'results/qwen25/case/lea'
            folder.mkdir(parents=True)
            (folder / 'ledger.jsonl').write_bytes(self.raw(self.events()) + b'{"event":')
            with patch.object(audit, 'ROOT', root):
                with self.assertRaisesRegex(audit.SnapshotRetry, 'unfinished trailing record'):
                    audit.stable_arm_snapshot(folder)


if __name__ == '__main__':
    unittest.main()

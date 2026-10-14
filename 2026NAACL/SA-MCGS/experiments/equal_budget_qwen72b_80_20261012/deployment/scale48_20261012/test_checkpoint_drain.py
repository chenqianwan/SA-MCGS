"""Isolated tests only: temporary files, fake identities, zero scientific calls."""
import copy
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import drain as d
import checkpoint_drain as c


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.task = {'case_uid': 'scid-v1-'+'a'*64, 'method': 'lea', 'token_budget': 100}
        self.patch = mock.patch.object(c, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(setattr, c, 'STOP', None)

    def fixture(self, finish=True):
        folder = self.root/'results/qwen25'/self.task['case_uid']/'lea'
        (folder/'calls').mkdir(parents=True)
        result = {'model': d.MODEL, 'content': '{}', 'usage': {'prompt_tokens': 7,
                  'completion_tokens': 4, 'total_tokens': 11}, 'raw': {}}
        cache = folder/'calls/a.json'
        cache.write_text(json.dumps({'call_id': 'call1', 'request_hash': 'request1', 'result': result}))
        owner = [self.task['case_uid'], d.MODEL, 'lea']
        events = [
            {'event': 'header', 'version': 1, 'accounting': 'actual_local_vllm_tokens',
             'external_api_enabled': False, 'unknown_outcome': 'retain_full_reservation'},
            {'event': 'owner', 'owner': owner, 'token_cap': 100, 'fingerprint': 'test'},
            {'event': 'reserve', 'call_id': 'call1', 'owner': owner, 'request_key': 'call-00000000:attempt-0',
             'request_hash': 'request1', 'input_tokens': 7, 'max_output_tokens': 20,
             'reserved_tokens': 27, 'cache_file': 'calls/a.json', 'retry_index': 0},
        ]
        if finish:
            events.append({'event': 'finish', 'call_id': 'call1', 'status': 'completed_with_usage',
                           'prompt_tokens': 7, 'completion_tokens': 4, 'actual_total_tokens': 11,
                           'usage_issues': [], 'response_sha256': d.digest(result)})
        path = folder/'ledger.jsonl'
        path.write_text(''.join(json.dumps(x)+'\n' for x in events))
        return path, cache

    def test_real_fcntl_excludes_worker_and_acquires_after_exit(self):
        claim = self.root/'execution/claims/qwen25'
        claim.mkdir(parents=True)
        path = claim/(d.task_key(self.task)+'.lock')
        child = subprocess.Popen([sys.executable, '-B', '-c',
            'import fcntl,sys; f=open(sys.argv[1],"a+"); fcntl.flock(f,fcntl.LOCK_EX); '
            'print("ready",flush=True); sys.stdin.readline()', str(path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            with mock.patch.object(d, 'UID', os.getuid()):
                locks = d.ClaimLocks(self.root, [self.task])
                try:
                    self.assertEqual(locks.acquire_available(), 0)
                    child.stdin.write('\n'); child.stdin.flush(); child.wait(timeout=5)
                    self.assertEqual(locks.acquire_available(), 1)
                    self.assertEqual(locks.acquire_available(), 1)
                    with path.open('a+') as other:
                        with self.assertRaises(BlockingIOError):
                            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    locks.close()
                with path.open('a+') as other:
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            if child.poll() is None:
                child.stdin.write('\n'); child.stdin.flush(); child.wait(timeout=5)
            child.stdin.close(); child.stdout.close()

    def test_settled_ledger_and_response_hash_pass(self):
        path, cache = self.fixture()
        proof = c.ledger_cache_proof(path, self.task)
        self.assertEqual(proof['held_calls'], 0)
        self.assertEqual(proof['settled_calls'], 1)
        self.assertEqual(proof['cache_sha256'], {str(cache.relative_to(self.root)): d.sha(cache)})

    def test_unsettled_reservation_rejected(self):
        path, _ = self.fixture(False)
        with self.assertRaisesRegex(RuntimeError, 'Unsettled'):
            c.ledger_cache_proof(path, self.task)

    def test_partial_line_rejected(self):
        path, _ = self.fixture()
        with path.open('a') as stream:
            stream.write('{')
        with self.assertRaisesRegex(RuntimeError, 'Truncated'):
            c.ledger_cache_proof(path, self.task)

    def test_corrupt_cached_response_rejected(self):
        path, cache = self.fixture()
        value = json.loads(cache.read_text()); value['result']['content'] = 'changed'
        cache.write_text(json.dumps(value))
        with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
            c.ledger_cache_proof(path, self.task)

    def test_out_of_scope_cache_rejected(self):
        path, _ = self.fixture()
        events = [json.loads(line) for line in path.read_text().splitlines()]
        events[2]['cache_file'] = '../escape.json'
        path.write_text(''.join(json.dumps(x)+'\n' for x in events))
        with self.assertRaisesRegex(RuntimeError, 'cache path'):
            c.ledger_cache_proof(path, self.task)

    def test_signal_requires_same_process_identity(self):
        proof = {'pid': 99, 'initial_identity': {'pid': 99, 'start_ticks': 1}}
        fake = {'identity': {'pid': 99, 'start_ticks': 2}, 'state': 'T', 'default_sigterm': True}
        with mock.patch.object(c, 'proc', return_value=fake), mock.patch.object(c.os, 'kill') as kill:
            with self.assertRaises(RuntimeError):
                c.send_verified(proof, signal.SIGTERM, require_stopped=True)
            kill.assert_not_called()

    def test_signal_requires_stopped_state_and_default_term(self):
        proof = {'pid': 99, 'initial_identity': {'pid': 99}}
        for state, default in [('S', True), ('T', False)]:
            fake = {'identity': {'pid': 99}, 'state': state, 'default_sigterm': default}
            with mock.patch.object(c, 'proc', return_value=fake), mock.patch.object(c.os, 'kill') as kill:
                with self.assertRaises(RuntimeError):
                    c.send_verified(proof, signal.SIGTERM, require_stopped=True)
                kill.assert_not_called()

    def test_signal_uses_verified_exact_pid(self):
        proof = {'pid': 99, 'initial_identity': {'pid': 99}}
        fake = {'identity': {'pid': 99}, 'state': 'T', 'default_sigterm': True}
        with mock.patch.object(c, 'proc', return_value=fake), mock.patch.object(c.os, 'kill') as kill:
            c.send_verified(proof, signal.SIGTERM, require_stopped=True)
            kill.assert_called_once_with(99, signal.SIGTERM)

    def test_replay_requires_exact_complete_frozen_prefix(self):
        path, _ = self.fixture()
        arm = c.ledger_cache_proof(path, self.task)
        proof = {'status': 'passed', 'all_active_arms_verified': True, 'provider_calls': 0,
                 'protocol_sha256': 'protocol', 'active_arm_identities': [{
                     'case_uid': arm['case_uid'], 'method': arm['method'], 'source_ledger_sha256': arm['ledger_sha256'],
                     'omitted_reservations': [], 'omitted_reservations_count': 0, 'ignored_partial_bytes': 0,
                     'source_cache_sha256': arm['cache_sha256'], 'prefix_calls': 1}]}
        c.validate_replay(proof, {'partial_arms': [arm]}, 'protocol')
        for key, value in [('omitted_reservations', [{}]), ('omitted_reservations_count', 1),
                           ('ignored_partial_bytes', 1), ('prefix_calls', 0),
                           ('source_cache_sha256', {}), ('source_ledger_sha256', 'old')]:
            changed = copy.deepcopy(proof); changed['active_arm_identities'][0][key] = value
            with self.assertRaises(RuntimeError):
                c.validate_replay(changed, {'partial_arms': [arm]}, 'protocol')

    def test_failure_continues_owned_stopped_workers_and_releases_locks(self):
        fake_locks = mock.Mock()
        def fail(context, locks, paused, signals, status):
            paused['qwen25-0_worker0'] = {'pid': 99, 'already_exited': False, 'initial_identity': {'pid': 99}}
            raise RuntimeError('offline replay failed')
        with mock.patch.object(c, 'HERE', self.root), \
             mock.patch.object(c.d, 'environment_identity', return_value={}), \
             mock.patch.object(c.d, 'load_tasks', return_value=([], '', {})), \
             mock.patch.object(c.d, 'ClaimLocks', return_value=fake_locks), \
             mock.patch.object(c, 'execute', side_effect=fail), \
             mock.patch.object(c, 'verify_worker', return_value={'state': 'T'}), \
             mock.patch.object(c, 'send_verified') as send:
            self.assertEqual(c.main(), 1)
        fake_locks.close.assert_called_once()
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1], signal.SIGCONT)
        self.assertEqual(json.loads((self.root/'checkpoint_status.json').read_text())['status'], 'failed')

    def test_stop_signal_raises_interrupted_not_scientific_retry(self):
        c.stop_handler(signal.SIGTERM, None)
        with self.assertRaises(InterruptedError):
            c.check_stop(time.monotonic()+100)


if __name__ == '__main__':
    unittest.main()

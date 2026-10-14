"""Offline temporary-file tests; no model clients, remote operations or signals."""
import copy
import fcntl
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import drain as d
import reconcile_completed_checkpoint as m


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.here = self.root/'deployment/scale48_20261012'
        self.here.mkdir(parents=True)
        for owner, attribute, value in ((m, 'ROOT', self.root), (m, 'HERE', self.here),
                                        (m.r, 'ROOT', self.root), (d, 'UID', os.getuid())):
            patch = mock.patch.object(owner, attribute, value)
            patch.start(); self.addCleanup(patch.stop)
        self.no_signals = mock.patch.object(os, 'kill', side_effect=AssertionError('No signals permitted'))
        self.no_signals.start(); self.addCleanup(self.no_signals.stop)
        self.watched, self.frozen, self.events = {}, {}, []
        for replica in range(4):
            for index in range(8):
                name = f'qwen25-{replica}_worker{index}'
                pid = 10000+replica*8+index
                identity = {'pid': pid, 'uid': d.UID, 'job_id': d.JOB, 'step_id': '43',
                            'argv': [d.PYTHON, '-B', str(self.root/'runner.py'),
                                     '--replica-id', f'qwen25-{replica}', '--worker-index', str(index)]}
                proof = {'pid': pid, 'initial_identity': identity}
                self.watched[name] = proof
                self.frozen[name] = {**proof, 'boundary_verified': True, 'already_exited': False}
                self.events.append({'worker': name, 'pid': pid, 'identity': identity,
                                    'sigterm_intent_at': '2026-10-12T04:25:00+00:00',
                                    'sigterm_sent_at': '2026-10-12T04:25:01+00:00',
                                    'sigcont_sent_at': '2026-10-12T04:25:02+00:00'})
        self.failed = {'status': 'failed', 'error_type': 'PermissionError',
                       'error': "[Errno 13] Permission denied: '/proc/1626673/environ'",
                       'partial_termination': True, 'context': {'pid': 1676547, 'step_id': '48'},
                       'cleanup_continuations': [{'error': "[Errno 13] Permission denied: '/proc/1626673/environ'"}]}
        self.controller = {'pid': 1676546, 'job_id': d.JOB, 'step_id': '48', 'status': 'needs_attention',
                           'error': 'Checkpoint drain failed; no service restart requested'}

    def test_exact_complete_signal_proof_passes(self):
        m.validate_signal_events(self.events, self.watched, self.frozen)

    def test_missing_cont_is_rejected(self):
        del self.events[-1]['sigcont_sent_at']
        with self.assertRaisesRegex(RuntimeError, 'ordered TERM/CONT'):
            m.validate_signal_events(self.events, self.watched, self.frozen)

    def test_duplicate_or_missing_worker_is_rejected(self):
        self.events[-1] = copy.deepcopy(self.events[0])
        with self.assertRaisesRegex(RuntimeError, 'exactly 32'):
            m.validate_signal_events(self.events, self.watched, self.frozen)

    def test_changed_worker_identity_is_rejected(self):
        self.events[0] = copy.deepcopy(self.events[0])
        self.events[0]['identity']['pid'] += 100
        with self.assertRaisesRegex(RuntimeError, 'identity'):
            m.validate_signal_events(self.events, self.watched, self.frozen)

    def test_only_observed_failure_is_allowed(self):
        m.validate_failure(self.failed, self.controller)
        self.failed['error_type'] = 'RuntimeError'
        with self.assertRaisesRegex(RuntimeError, 'restricted'):
            m.validate_failure(self.failed, self.controller)

    def test_cleanup_resume_is_rejected(self):
        self.failed['cleanup_continuations'][0]['continued_at'] = 'now'
        with self.assertRaisesRegex(RuntimeError, 'resumed'):
            m.validate_failure(self.failed, self.controller)

    def test_proc_zombie_needs_no_environ_read(self):
        stat = '123 (python) Z '+' '.join(['0']*18+['1234'])
        with mock.patch.object(Path, 'read_text', return_value=stat) as read:
            result = m.absent_or_zombie(123)
        self.assertEqual(result['state'], 'Z')
        self.assertEqual(read.call_count, 1)

    def test_live_or_permission_denied_proc_is_not_treated_as_gone(self):
        with mock.patch.object(Path, 'read_text', return_value='123 (python) S '+' '.join(['0']*19)):
            with self.assertRaisesRegex(RuntimeError, 'still live'):
                m.absent_or_zombie(123)
        with mock.patch.object(Path, 'read_text', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                m.absent_or_zombie(123)

    def fixture(self):
        context = {'pid': 1676547, 'step_id': '48'}
        audit = {'final_results': 0, 'partial_arms': [], 'all_result_files_sha256': {}}
        sources = {'runner.py': 'science-source'}
        base = {'schema': 'qwen48_request_checkpoint_v1', 'source_sha256': sources,
                'protocol_sha256': 'protocol', 'context': context, 'watched_processes': self.watched}
        replay = {'path': 'deployment/scale48_20261012/replay_preflight_frozen.json', 'sha256': 'replay'}
        launch_hashes = {}
        for name in ('controller.py', 'launch_controller_once.py', 'drain.py', 'checkpoint_drain.py',
                     'replay_preflight.py', 'restart_after_drain.py', 'observe48.py'):
            path = self.here/name
            path.write_text('# isolated fixture\n')
            launch_hashes[str(path.relative_to(self.root))] = d.sha(path)
        evidence = {
            'controller_launch_receipt.json': {'source_sha256': launch_hashes},
            'controller_status.json': self.controller, 'checkpoint_initial.json': base,
            'checkpoint_status.json': {**base, **self.failed, 'signals': self.events},
            'checkpoint_ready.json': {**base, 'status': 'frozen_replay_check', 'frozen_audit': audit},
            'checkpoint_termination_intent.json': {**base, 'status': 'termination_intent', 'audit': audit,
                                                  'frozen_workers': self.frozen, 'replay_proof': replay},
            'checkpoint_signals.json': {'signals': self.events, 'replay_proof': replay},
            'replay_preflight_frozen.json': {},
        }
        for name, value in evidence.items():
            d.save(self.here/name, value)
        for name in m.STATE_FILES:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            d.save(path, {})
        tasks = [{'case_uid': f'case{i}', 'method': 'lea'} for i in range(160)]
        claim_dir = self.root/'execution/claims/qwen25'
        claim_dir.mkdir(parents=True)
        for task in tasks:
            (claim_dir/(d.task_key(task)+'.lock')).touch()
        states = {'workers': {'workers': [{'exit_code': -15} for i in range(32)], 'final_results': 0},
                  'pipeline': {'final_results': 0}, 'services': {}}
        for owner, function, value in ((d, 'load_tasks', (tasks, 'protocol', sources)),
                                       (d, 'states', states), (m.c, 'frozen_audit', audit),
                                       (m.c, 'validate_replay', None), (m, 'absent_or_zombie', {'state': 'absent'}),
                                       (m.r, 'verify_drain_receipt', None), (m.r, 'verify_old_stopped', None),
                                       (m.r, 'verify_scientific_files', None)):
            patch = mock.patch.object(owner, function, return_value=value)
            patch.start(); self.addCleanup(patch.stop)
        return audit, tasks

    def test_complete_audit_preserves_evidence_and_releases_real_160_locks(self):
        self.fixture()
        before = {name: d.sha(self.here/name) for name in m.EVIDENCE_FILES}
        reconciliation, drained = m.audit_completed({'step_id': '49'})
        self.assertEqual(reconciliation['status'], 'passed')
        self.assertEqual(drained['claim_locks_release'], 'confirmed')
        self.assertEqual(before, {name: d.sha(self.here/name) for name in m.EVIDENCE_FILES})
        for claim in (self.root/'execution/claims/qwen25').glob('*.lock'):
            with claim.open('a') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertFalse((self.here/'drained_receipt.json').exists())

    def test_claim_still_owned_refuses_receipt_and_releases_other_locks(self):
        self.fixture()
        claim = self.root/'execution/claims/qwen25/case0__lea.lock'
        with claim.open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, 'remains claimed'):
                m.audit_completed({'step_id': '49'})
        self.assertFalse((self.here/'drained_receipt.json').exists())

    def test_result_change_refuses_reconciliation(self):
        self.fixture()
        m.c.frozen_audit.return_value = {'final_results': 1}
        with self.assertRaisesRegex(RuntimeError, 'Scientific files changed'):
            m.audit_completed({'step_id': '49'})


if __name__ == '__main__':
    unittest.main()

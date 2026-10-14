"""Isolated recovery tests: never contact the cluster or change scientific files."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('restart_after_drain.py')
spec = importlib.util.spec_from_file_location('restart_under_test', SCRIPT)
restart = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restart)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.deploy = self.root / 'deployment'
        self.here = self.deploy / 'scale48_20261012'
        self.here.mkdir(parents=True)
        self.patches = patch.multiple(restart, ROOT=self.root, DEPLOY=self.deploy, HERE=self.here)
        self.patches.start()
        self.addCleanup(self.patches.stop)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, dict):
            data = (json.dumps(data, indent=2) + '\n').encode()
        if isinstance(data, str):
            data = data.encode()
        path.write_bytes(data)
        return restart.sha(path)

    def manifest_fixture(self):
        old_config = {'workers_per_replica': {'qwen25': 6}}
        new_config = {'workers_per_replica': {'qwen25': 8}}
        old_hash = restart.digest((json.dumps(old_config, indent=2) + '\n').encode())
        new_hash = self.write('execution_config.json', new_config)
        source_hash = self.write('runner.py', '# unchanged science\n')
        service_hash = self.write('deployment/service_supervisor.py', "OPTIONS = ['--max-num-seqs', '8']\n")
        self.write('report_results.py', '# frozen reporter\n')
        report_hashes = {name: self.write(name, 'derived current ' + name) for name in restart.DERIVED}
        files = {'execution_config.json': old_hash, 'runner.py': source_hash,
                 'report_results.py': restart.sha(self.root / 'report_results.py'),
                 'deployment/service_supervisor.py': service_hash,
                 **{name: '0' * 64 for name in restart.DERIVED}}
        manifest = {'files': files}
        mh = self.write('deployment/services_staging_manifest.json', manifest)
        self.write('deployment/pipeline_launch_receipt.json', {
            'job_id': restart.JOB, 'node': restart.NODE, 'auto_retry': False, 'gpu_requested': False,
            'verified_files': {'runner.py': source_hash, 'deployment/services_staging_manifest.json': mh}})
        self.write('deployment/concurrency_20261012/scale_24_to_32.json', {
            'status': 'applied', 'before': old_config, 'after': new_config,
            'before_sha256': old_hash, 'after_sha256': new_hash,
            'worker_step_id': '43', 'service_step_id': '42', 'service_restart': False,
            'scientific_source_or_budget_changes': False})
        return manifest, report_hashes

    def test_manifest_accepts_only_receipted_live_config_and_reproduced_reports(self):
        expected, reports = self.manifest_fixture()
        with patch.object(restart, 'verify_derived_reports', return_value=reports):
            actual, hashes = restart.verify_manifests()
        self.assertEqual(actual, expected)
        self.assertEqual(hashes, reports)

    def test_manifest_rejects_scientific_source_change(self):
        self.manifest_fixture()
        self.write('runner.py', '# changed science\n')
        with self.assertRaisesRegex(RuntimeError, 'source proof mismatch'):
            restart.verify_manifests()

    def test_manifest_rejects_unreceipted_concurrency(self):
        self.manifest_fixture()
        self.write('execution_config.json', {'workers_per_replica': {'qwen25': 12}})
        with self.assertRaisesRegex(RuntimeError, 'configuration differs'):
            restart.verify_manifests()

    def test_manifest_rejects_derived_report_mismatch(self):
        self.manifest_fixture()
        with patch.object(restart, 'verify_derived_reports', side_effect=RuntimeError('report mismatch')):
            with self.assertRaisesRegex(RuntimeError, 'report mismatch'):
                restart.verify_manifests()

    def test_unreviewed_request_checkpoint_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'unreviewed draining mode'):
            restart.verify_drain_receipt({'status': 'drained', 'kind': 'request_boundary_checkpoint'})

    def test_unsafe_manifest_paths_are_rejected(self):
        for name in ('../runner.py', '/tmp/runner.py'):
            with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
                restart.local_path(name)

    def replay_fixture(self):
        hashes = {name: self.write(name, '# frozen ' + name) for name in
                  ('runner.py', 'science_support.py', 'methods_full.py', 'budget_client.py',
                   'protocol.json', 'historical_sa_reference.json', 'run_scope.json')}
        hashes['endpoints.json'] = self.write('deployment/endpoints_retired.json', {'old': 'endpoints'})
        script_hash = self.write('deployment/scale48_20261012/replay_preflight.py', '# replay verifier')
        self.write('tokenizer_hashes/qwen25.json', {'tokenizer.json': 'abc'})
        ledger_hash = self.write('results/qwen25/case/lea/ledger.jsonl', 'settled ledger\n')
        cache_name = 'results/qwen25/case/lea/calls/1.json'
        cache_hash = self.write(cache_name, {'response': 'cached'})
        cache_hashes = {cache_name: cache_hash}
        replay = {'provider_calls': 0, 'cached_calls_consumed': 1}
        evidence_name = 'deployment/scale48_20261012/snapshot/case/lea/evidence.json'
        evidence_hash = self.write(evidence_name, {'status': 'passed', 'parse_idempotent': True,
                                                 'first_replay': replay, 'second_replay': replay})
        arm = {'case_uid': 'case', 'method': 'lea', 'ledger_sha256': ledger_hash,
               'settled_calls': 1, 'cache_sha256': cache_hashes}
        row = {'case_uid': 'case', 'method': 'lea', 'status': 'passed', 'ignored_partial_bytes': 0,
               'omitted_reservations': [], 'omitted_reservations_count': 0, 'source_ledger_sha256': ledger_hash,
               'source_complete_sha256': ledger_hash, 'source_ledger_bytes': 15, 'source_complete_bytes': 15,
               'prefix_calls': 1, 'source_cache_sha256': cache_hashes,
               'evidence_path': str(self.root / evidence_name), 'evidence_sha256': evidence_hash}
        proof = {'schema': 'qwen_scale48_cache_replay_v1', 'status': 'passed',
                 'all_active_arms_verified': True, 'provider_calls': 0, 'errors': [], 'root': str(self.root),
                 'script_sha256': script_hash, 'source_hashes': hashes,
                 'tokenizer_hashes': {'tokenizer.json': 'abc'}, 'active_arm_identities': [row],
                 'arm_count': 1, 'source_cache_sha256': cache_hashes}
        proof_path = self.here / 'replay_preflight_frozen.json'
        self.write(str(proof_path.relative_to(self.root)), proof)
        return {'audit': {'partial_arms': [arm]}}, proof_path, proof

    def test_checkpoint_proof_covers_exact_frozen_prefix_and_two_equal_replays(self):
        drained, proof_path, _ = self.replay_fixture()
        restart.verify_replay_proof(drained, proof_path)

    def test_checkpoint_proof_rejects_omitted_reservation(self):
        drained, proof_path, proof = self.replay_fixture()
        proof['active_arm_identities'][0]['omitted_reservations_count'] = 1
        self.write(str(proof_path.relative_to(self.root)), proof)
        with self.assertRaisesRegex(RuntimeError, 'complete frozen replay proof'):
            restart.verify_replay_proof(drained, proof_path)

    def test_checkpoint_proof_rejects_missing_partial_arm(self):
        drained, proof_path, proof = self.replay_fixture()
        proof['active_arm_identities'] = []
        self.write(str(proof_path.relative_to(self.root)), proof)
        with self.assertRaisesRegex(RuntimeError, 'exactly the partial'):
            restart.verify_replay_proof(drained, proof_path)

    def test_checkpoint_proof_rejects_provider_calls(self):
        drained, proof_path, proof = self.replay_fixture()
        proof['provider_calls'] = 1
        self.write(str(proof_path.relative_to(self.root)), proof)
        with self.assertRaisesRegex(RuntimeError, 'without provider calls'):
            restart.verify_replay_proof(drained, proof_path)

    def test_prepare_archives_old_state_changes_only_limits_and_preserves_results(self):
        manifest, reports = self.manifest_fixture()
        self.write('deployment/scale48_20261012/drained_receipt.json', {'status': 'drained'})
        preserved_hash = self.write('results/qwen25/case/lea/final.json', {'usage': 123})
        self.write('execution/status.json', {'status': 'needs_attention', 'final_results': 32})
        source_before = (self.deploy / 'service_supervisor.py').read_bytes()
        scientific = {'preserved_files': {'results/qwen25/case/lea/final.json': preserved_hash},
                      'frozen_source_hashes': {'runner.py': restart.sha(self.root / 'runner.py')},
                      'terminal_results': 32}
        moves = ['deployment/pipeline_launch_receipt.json', 'execution/status.json']
        copies = ['deployment/service_supervisor.py', 'deployment/services_staging_manifest.json',
                  'execution_config.json', 'runner.py', 'summary.json', 'RESULTS_ZH.md']
        starter = types.SimpleNamespace(FILES=['runner.py', 'deployment/service_supervisor.py',
                                               'deployment/services_staging_manifest.json'])
        with patch.dict(os.environ, {'SLURM_STEP_ID': '50'}), \
             patch.object(restart, 'verify_drain_receipt', return_value={'final_results': 32}), \
             patch.object(restart, 'verify_old_stopped', return_value={'workers': {'final_results': 32}}), \
             patch.object(restart, 'verify_scientific_files', return_value=scientific), \
             patch.object(restart, 'verify_manifests', return_value=(copy.deepcopy(manifest), reports)), \
             patch.object(restart, 'archive_plan', return_value=(moves, copies)), \
             patch.object(restart, 'module', return_value=starter):
            intent, command = restart.prepare()
        self.assertEqual(intent['status'], 'prepared')
        self.assertTrue(intent['scientific_files_unchanged'])
        self.assertEqual((self.deploy / 'service_supervisor.py').read_bytes(),
                         source_before.replace(restart.OLD_SEQUENCE, restart.NEW_SEQUENCE))
        self.assertEqual(restart.read(self.root / 'execution_config.json'), {'workers_per_replica': {'qwen25': 12}})
        self.assertEqual(restart.sha(self.root / 'results/qwen25/case/lea/final.json'), preserved_hash)
        archive = self.here / 'archive_before_48'
        self.assertTrue((archive / 'execution/status.json').exists())
        self.assertFalse((self.root / 'execution/status.json').exists())
        self.assertEqual((archive / 'deployment/service_supervisor.py').read_bytes(), source_before)
        self.assertEqual(restart.read(self.deploy / 'pipeline_launch_receipt.json')['source'], 'planned_scale48')
        self.assertEqual(command, [restart.PYTHON, '-B', str(self.deploy / 'pipeline_supervisor.py')])
        after = restart.read(self.deploy / 'services_staging_manifest.json')['files']
        self.assertEqual(after['runner.py'], manifest['files']['runner.py'])
        self.assertEqual(set(after), set(manifest['files']))


if __name__ == '__main__':
    unittest.main()

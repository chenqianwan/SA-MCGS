"""Offline safety tests: no Slurm dispatch, model calls, or real worker processes."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pipeline_supervisor as pipeline
import start_pipeline_once as launcher


class LauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root/'pipeline_supervisor.py'
        self.source.write_text('# frozen test fixture\n')
        (self.root/'preflight').mkdir()
        self.preflight = self.root/'preflight/pipeline_prepare.json'
        self.data = {'status': 'passed', 'model_calls': 0, 'expected_results_total': 1440,
                     'file_hashes': {str(self.source): launcher.sha(self.source)}}
        self.save()
        self.job = subprocess.CompletedProcess([], 0,
            'JobId=415747 JobState=RUNNING UserId=hansirui_3rd(1083) NodeList=dgx-061 NumNodes=1', '')

    def save(self):
        self.preflight.write_text(json.dumps(self.data))

    def run_main(self, spawn):
        with patch.object(launcher, 'ROOT', self.root), \
             patch.object(launcher.os, 'getuid', return_value=1083), \
             patch.object(launcher.subprocess, 'run', return_value=self.job), \
             patch.object(launcher.subprocess, 'Popen', side_effect=spawn), \
             contextlib.redirect_stdout(io.StringIO()):
            return launcher.main()

    def test_changed_file_blocks_dispatch(self):
        launcher.verify_preflight(self.preflight)
        self.source.write_text('changed')
        with self.assertRaises(RuntimeError):
            self.run_main(lambda *a, **k: self.fail('Changed file was dispatched'))

    def test_relative_or_empty_hash_mapping_rejected(self):
        for value in ({}, {'pipeline_supervisor.py': launcher.sha(self.source)}):
            self.data['file_hashes'] = value
            self.save()
            with self.assertRaises(RuntimeError):
                launcher.verify_preflight(self.preflight)

    def test_nonzero_calls_or_wrong_scope_rejected(self):
        for key, value in (('model_calls', 1), ('model_calls', False),
                           ('expected_results_total', 960), ('status', 'failed')):
            original = self.data[key]
            self.data[key] = value
            self.save()
            with self.assertRaises(RuntimeError):
                launcher.verify_preflight(self.preflight)
            self.data[key] = original

    def test_intent_precedes_dispatch_and_second_launch_is_noop(self):
        commands = []
        def spawn(command, **kwargs):
            receipt = json.loads((self.root/'execution/step_launch_receipt.json').read_text())
            self.assertEqual(receipt['status'], 'starting')
            for argument in ('--jobid=415747', '--cpus-per-task=64', '--gres=none',
                             '--input=none', '--overlap'):
                self.assertIn(argument, command)
            self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
            commands.append(command)
            return type('Child', (), {'pid': 123})()
        self.assertEqual(self.run_main(spawn), 0)
        self.assertEqual(self.run_main(spawn), 0)
        self.assertEqual(len(commands), 1)

    def test_failed_dispatch_preserves_intent_without_automatic_retry(self):
        def fail(*args, **kwargs):
            raise OSError('Simulated dispatch failure')
        with self.assertRaises(OSError):
            self.run_main(fail)
        receipt = json.loads((self.root/'execution/step_launch_receipt.json').read_text())
        self.assertEqual(receipt['status'], 'starting')
        self.assertEqual(self.run_main(lambda *a, **k: self.fail('Duplicate dispatch')), 0)

    def test_wrong_allocation_is_never_dispatched(self):
        self.job.stdout = self.job.stdout.replace('NodeList=dgx-061', 'NodeList=dgx-999')
        with self.assertRaises(RuntimeError):
            self.run_main(lambda *a, **k: self.fail('Wrong allocation dispatched'))


class GateTests(unittest.TestCase):
    def test_complete_audit_and_all_workers_exited_are_both_required(self):
        self.assertTrue(pipeline.gate({'complete': True}, [{'exit_code': 0}], 1))
        for code in (None, 1, False, '0'):
            self.assertFalse(pipeline.gate({'complete': True}, [{'exit_code': code}], 1))
        self.assertFalse(pipeline.gate({'complete': False}, [{'exit_code': 0}], 1))
        self.assertFalse(pipeline.gate({'complete': True}, [], 1))

    def test_scientific_failures_do_not_trigger_quality_based_repeat_filtering(self):
        audit = {'complete': True, 'strict_failures': 160, 'errors': [], 'missing': []}
        self.assertTrue(pipeline.gate(audit, [{'exit_code': 0}], 1))


class PipelineStateTests(unittest.TestCase):
    def simulate(self, bad_kimi_audit=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        parent = Path(temporary.name).resolve()
        root = parent/'controller'
        root.mkdir()
        waves = [parent/f'wave{i}' for i in (1, 2, 3)]
        for wave in waves:
            (wave/'execution').mkdir(parents=True)
        limits = {'llama': 10, 'kimi': 16, 'qwen35': 16}
        manifest = {'workers_per_replica': limits}
        (root/'manifest.json').write_text(json.dumps(manifest))
        replicas = [{'id': f'{model}-{n}', 'model_key': model}
                    for model, count in [('llama', 2), ('kimi', 4), ('qwen35', 2)]
                    for n in range(count)]
        wave1_entries = [{'name': f'{r["id"]}_{i}', 'model': r['model_key'],
                          'exit_code': 0 if r['model_key'] == 'qwen35' else None}
                         for r in replicas for i in range(limits[r['model_key']])]
        def old_status():
            (waves[0]/'execution/status.json').write_text(json.dumps({'workers': wave1_entries}))
        old_status()
        launched, children, waits = [], [], []

        class Child:
            def __init__(self, wave, model, pid):
                self.wave, self.model, self.pid = wave, model, pid
                self.returncode = None
            def poll(self):
                self.returncode = 0
                return 0

        def spawn(command, **kwargs):
            wave = Path(command[2]).parent
            model = command[command.index('--replica-id')+1].rsplit('-', 1)[0]
            if wave == waves[1]:
                self.assertTrue(all(e['exit_code'] == 0 for e in wave1_entries if e['model'] == model))
            if wave == waves[2]:
                self.assertTrue(all(c.returncode == 0 for c in children
                                    if c.wave == waves[1] and c.model == model))
            receipt = root/'execution'/f'launch_wave{waves.index(wave)+1}_{model}.json'
            self.assertEqual(json.loads(receipt.read_text())['state'], 'intent')
            child = Child(wave, model, 10000+len(children))
            children.append(child)
            launched.append((waves.index(wave)+1, model))
            return child

        def audit(wave, model):
            failed = bad_kimi_audit and wave == waves[1] and model == 'kimi'
            return {'complete': not failed, 'errors': ['unsettled_usage'] if failed else [], 'missing': []}

        def sleep(seconds):
            if seconds == 15:
                waits.append(seconds)
                self.assertLess(len(waits), 8, 'Pipeline did not terminate')
                for entry in wave1_entries:
                    entry['exit_code'] = 0
                old_status()

        def report(command, **kwargs):
            if Path(command[2]).name == 'aggregate_three_waves.py':
                (root/'aggregate_summary.json').write_text(json.dumps({'formal_three_wave_ready': True}))
            return subprocess.CompletedProcess(command, 0)

        with patch.object(pipeline, 'ROOT', root), \
             patch.dict(pipeline.os.environ, {'SLURM_JOB_ID': '415747'}), \
             patch.object(pipeline, 'validate', return_value=(waves, replicas)), \
             patch.object(pipeline, 'audit_model', side_effect=audit), \
             patch.object(pipeline.subprocess, 'Popen', side_effect=spawn), \
             patch.object(pipeline.subprocess, 'run', side_effect=report), \
             patch.object(pipeline.time, 'sleep', side_effect=sleep), \
             patch.object(pipeline.signal, 'signal'):
            result = pipeline.main()
            # Prior per-model launch receipts block every subsequent automatic start.
            with self.assertRaisesRegex(RuntimeError, 'Prior launch receipt'):
                pipeline.main()
        return result, launched, json.loads((root/'execution/status.json').read_text())

    def test_models_advance_independently_and_stop_after_wave_three(self):
        result, launched, state = self.simulate()
        self.assertEqual(result, 0)
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(launched[0], (2, 'qwen35'))
        self.assertLess(launched.index((2, 'qwen35')), launched.index((2, 'llama')))
        self.assertEqual(len(launched), 232)
        self.assertEqual({wave for wave, _ in launched}, {2, 3})

    def test_failed_audit_blocks_only_that_model_next_wave(self):
        result, launched, state = self.simulate(bad_kimi_audit=True)
        self.assertEqual(result, 1)
        self.assertEqual(state['status'], 'needs_attention')
        self.assertNotIn((3, 'kimi'), launched)
        self.assertIn((3, 'llama'), launched)
        self.assertIn((3, 'qwen35'), launched)


if __name__ == '__main__':
    unittest.main()

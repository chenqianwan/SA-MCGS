"""Offline deployment identity and smoke guards; no service starts or network calls."""
import importlib.util
import io
import json
from pathlib import Path
import signal
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('qwen_service_test', HERE/'deployment/service_supervisor.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class Tokenizer:
    def apply_chat_template(self, *args, **kwargs):
        return list(range(13))


class DeploymentTests(unittest.TestCase):
    def test_tp2_yarn_configuration_preserves_checkpoint_and_fp16_kv(self):
        argv = service.command({'port': 19271})
        for key, expected in [('--model', str(service.MODEL_PATH)), ('--dtype', 'float16'),
                              ('--quantization', 'awq'), ('--tensor-parallel-size', '2'),
                              ('--max-model-len', '131072'), ('--max-num-seqs', '8'),
                              ('--gpu-memory-utilization', '0.90'), ('--generation-config', 'vllm')]:
            self.assertEqual(argv[argv.index(key)+1], expected)
        overrides = json.loads(argv[argv.index('--hf-overrides')+1])
        self.assertEqual(overrides['rope_parameters']['rope_type'], 'yarn')
        self.assertEqual(overrides['rope_parameters']['factor'], 4.0)
        self.assertEqual(overrides['rope_parameters']['original_max_position_embeddings'], 32768)
        self.assertNotIn('--rope-scaling', argv)
        self.assertEqual(service.REPLICA_COUNT * service.TP_SIZE, 8)

    def test_smoke_accepts_exact_token_count_and_rejects_mismatch(self):
        replica = {'id': 'qwen25-0', 'base_url': 'http://127.0.0.1:19271/v1'}
        result = {'model': service.MODEL_ALIAS, 'choices': [{'message': {'content': 'OK'}}],
                  'usage': {'prompt_tokens': 13, 'completion_tokens': 2, 'total_tokens': 15}}
        with patch.object(service, 'urlopen', return_value=io.BytesIO(json.dumps(result).encode())):
            self.assertTrue(service.smoke(replica, Tokenizer())['prompt_token_match'])
        result['usage']['prompt_tokens'] = 12
        with patch.object(service, 'urlopen', return_value=io.BytesIO(json.dumps(result).encode())):
            with self.assertRaises(RuntimeError):
                service.smoke(replica, Tokenizer())

    def test_cleanup_only_signals_token_verified_groups_it_created(self):
        owned, unrelated = Mock(pid=91001), Mock(pid=91002)
        seen = set()
        def alive(group):
            if group == owned.pid and group not in seen:
                seen.add(group)
                return True
            return False
        with patch.object(service, 'owned_group_alive', side_effect=alive), \
                patch.object(service.os, 'killpg') as kill:
            service.cleanup({'own_child': owned, 'no_owner_token': unrelated})
        kill.assert_called_once_with(owned.pid, signal.SIGTERM)


if __name__ == '__main__':
    unittest.main()

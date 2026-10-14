#!/usr/bin/env python3
"""Local, zero-inference check with the verified official tokenizer files."""
from pathlib import Path
import collections
import hashlib
import importlib.util
import json
from transformers import AutoTokenizer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location('llama_launcher', ROOT / 'runner/llama_launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
tokenizer = AutoTokenizer.from_pretrained(str(HERE / 'model'), local_files_only=True, trust_remote_code=False)
capture = ROOT / 'offline_validation_128k_final/offline_prompt_capture.json'
requests = json.loads(capture.read_text())
counts = collections.Counter()
maxima = {}
overflow = []
cache = {}
for item in requests:
    request = item['request']
    key = launcher.digest(request)
    if key not in cache:
        cache[key] = launcher.token_count(tokenizer, request)
    prompt_tokens = cache[key]
    total = prompt_tokens + request['max_tokens']
    counts[item['method']] += 1
    if total > maxima.get(item['method'], {}).get('prompt_plus_output_tokens', 0):
        maxima[item['method']] = {'case_id': item['case_id'], 'prompt_tokens': prompt_tokens,
            'output_tokens': request['max_tokens'], 'prompt_plus_output_tokens': total}
    if total > 131072:
        overflow.append({'case_id': item['case_id'], 'method': item['method'], 'tokens': total})
report = {'passed': not overflow, 'api_calls': 0, 'max_model_len': 131072,
    'request_counts': dict(counts), 'maxima_by_method': maxima, 'overflow': overflow,
    'prompt_capture_sha256': launcher.sha(capture),
    'tokenizer_files_sha256': {p.name: launcher.sha(p) for p in (HERE / 'model').iterdir() if p.is_file()},
    'note': 'Local independent preview; production repeats with the cluster runtime and guards every actual dynamic request.'}
(HERE / 'tokenization_preview.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report['passed'] else 2)

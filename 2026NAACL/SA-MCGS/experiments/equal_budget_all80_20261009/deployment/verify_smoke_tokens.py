#!/usr/bin/env python3
"""Offline comparison of the eight deployment smoke prompt token counts."""
from collections.abc import Mapping
import os
from pathlib import Path
from service_supervisor import JOB, MODELS, ORDER, ROOT, now, read, write


def main():
    if os.environ.get('SLURM_JOB_ID') != JOB or os.getuid() != 1083:
        raise RuntimeError('Run tokenizer verification on the authorized model node')
    from transformers import AutoTokenizer
    tokenizers = {}
    rows = []
    run = ROOT/'deployment/runtime'/JOB
    for key, number in ORDER:
        cfg = MODELS[key]
        if key not in tokenizers:
            tokenizers[key] = AutoTokenizer.from_pretrained(cfg['path'], local_files_only=True,
                trust_remote_code=cfg['trust_remote_code'])
        tokenizer = tokenizers[key]
        record = read(run/f'{key}-{number}_smoke.json')
        request = record['request']
        kwargs = request.get('chat_template_kwargs', cfg['chat_template_kwargs'])
        ids = tokenizer.apply_chat_template(request['messages'], tokenize=True,
            add_generation_prompt=True, return_dict=False, **kwargs)
        if isinstance(ids, Mapping):
            ids = ids['input_ids']
        if hasattr(ids, 'tolist'):
            ids = ids.tolist()
        if ids and isinstance(ids[0], list):
            if len(ids) != 1:
                raise RuntimeError('Unexpected batched tokenizer output')
            ids = ids[0]
        actual = record['response']['usage']['prompt_tokens']
        row = dict(replica_id=f'{key}-{number}', model_key=key, tokenizer_tokens=len(ids),
            response_prompt_tokens=actual, matched=len(ids)==actual, add_generation_prompt=True,
            chat_template_kwargs=kwargs, tokenizer_path=cfg['path'], model_revision=cfg['revision'],
            model_calls=0)
        rows.append(row)
        write(ROOT/'deployment/smoke_token_verification.json',
            dict(at=now(), passed=False, state='verifying', scientific_calls=0, rows=rows))
    passed = len(rows)==8 and all(row['matched'] for row in rows)
    write(ROOT/'deployment/smoke_token_verification.json',
        dict(at=now(), passed=passed, state='complete', scientific_calls=0, model_calls=0, rows=rows))
    if not passed:
        raise RuntimeError('Offline smoke tokenizer count differs from actual vLLM prompt usage')
    print('All 8 deployment smoke prompt-token counts match the pinned local tokenizers.', flush=True)


if __name__ == '__main__':
    main()

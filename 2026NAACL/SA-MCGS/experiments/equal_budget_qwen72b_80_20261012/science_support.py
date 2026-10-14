#!/usr/bin/env python3
"""Shared verified science helpers; no execution entry point or SA runner."""

from __future__ import annotations

import argparse

import asyncio

import copy

import fcntl

import hashlib

import importlib.util

import json

import math

import os

from pathlib import Path

import random

import sys

import time

import traceback

from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent

METHODS = ('lea', 'full-scc')

FIELDS = {'sa-mcgs': 'evidence_risk_subgraph_nodes', 'lea': 'lea_risk_subgraph_nodes',
          'full-scc': 'direct_risk_subgraph_nodes'}

MODEL_KEYS = ('qwen25',)

class WorkerStop(BaseException):
    pass

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), default=str).encode()).hexdigest()

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def freeze(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + '.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if path.exists():
            if read(path) != value:
                raise WorkerStop(f'Frozen protocol changed: {path.name}')
        else:
            save(path, value)

def load_science():
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    try:
        import dotenv
        dotenv.load_dotenv = lambda *args, **kwargs: False
    except ImportError:
        pass
    spec = importlib.util.spec_from_file_location('equal_budget_science', ROOT/'science/base_launcher.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    manifest = launcher.verify_bundle()
    cost = launcher.import_science()
    graphs = launcher.restore_graphs(cost, manifest)
    plan = read(launcher.ROOT/'portable_data/qwen80_case_plan.json')
    if len(plan) != 80 or len({c['case_uid'] for c in plan}) != 80:
        raise WorkerStop('Expected exactly 80 frozen case identities')
    for case in plan:
        case['source_result_file'] = str(launcher.ROOT/case['source_result_repo_relpath'])
    # Match the comparator baselines' full-SCC 12000 output allowance on local Qwen.
    original = cost.battle._model_json_max_tokens
    cost.battle._model_json_max_tokens = lambda model, requested: (
        requested if model in ('qwen2.5-72b', 'qwen2.5-72b-instruct') else original(model, requested))
    return launcher, cost, manifest, graphs, plan

def science_args(model='offline'):
    return argparse.Namespace(model=model, budget=60, window_size=4, internal_concurrency=1,
                              compression_profile='current', seed=42, case_concurrency=1,
                              llm_timeout=1800, llm_max_retries=0)

def metrics(result, method, case, eligible=True):
    ids = case['planned_scc_clause_ids']; allowed = set(ids)
    labels = case['planned_injection_identity']
    result = result or {}; rows = result.get('ranking') or []
    h = set(result.get(FIELDS[method]) or [])
    try:
        ranking = [r[0] for r in rows]
        valid = bool(eligible and h and h <= allowed and len(rows) == len(ids)
                     and set(ranking) == allowed
                     and all(len(r) >= 2 and math.isfinite(float(r[1])) for r in rows))
    except (ValueError, TypeError, IndexError, KeyError):
        valid = False; ranking = []
    risks = set(labels['risk_nodes']); evidence = set(labels['evidence_nodes'])
    rank = ranking.index(labels['root_node'])+1 if valid else None
    return {'valid': valid, 'root_at_1': int(rank == 1),
            'root_at_3': int(rank is not None and rank <= 3), 'root_rank': rank,
            'mrr': 1/rank if rank else 0,
            'risk_any': int(valid and bool(h & risks)), 'risk_all': int(valid and risks <= h),
            'endpoint_recall': len(h & risks)/len(risks) if valid else 0,
            'evidence_all': int(valid and evidence <= h),
            'evidence_recall': len(h & evidence)/len(evidence) if valid else 0,
            'output_n': len(h) if valid else None,
            'compression': 1-len(h)/len(ids) if valid else None}

def tokenizer_hashes(path):
    path = Path(path)
    names = {'tokenizer.json', 'tokenizer_config.json', 'config.json', 'special_tokens_map.json',
             'chat_template.jinja', 'tokenizer.model', 'vocab.json', 'merges.txt', 'tiktoken.model'}
    names.update(item.name for item in path.glob('*.py'))
    return {name: sha(path/name) for name in sorted(names) if (path/name).is_file()}

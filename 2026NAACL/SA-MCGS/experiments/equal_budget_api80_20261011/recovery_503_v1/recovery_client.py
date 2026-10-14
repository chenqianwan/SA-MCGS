"""Isolated, durable HTTP-503 recovery; historical paid responses are replayed.

Each instance belongs to one original candidate or selector. Recovery spending
is reported separately; this client does not reset or edit historical budgets.
"""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
_name = '_api10_original_paid_client_for_recovery'
if _name in sys.modules:
    original = sys.modules[_name]
else:
    _path = HERE.parent.parent / 'equal_budget_api10_20261011/api_budget_client.py'
    _spec = importlib.util.spec_from_file_location(_name, _path)
    original = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = original
    _spec.loader.exec_module(original)

BudgetStop = original.BudgetStop
LedgerError = original.LedgerError
BudgetLLMResponse = original.BudgetLLMResponse
ENDPOINT = original.ENDPOINT
POLICY = {'version': 1, 'endpoint': ENDPOINT, 'sdk_retries': 0,
          'timeout_seconds': 120, 'maximum_503_retries': 2,
          'backoff_seconds': [5, 15], 'invalid_new_json': 'stop_without_resampling',
          'unknown_outcome': 'stop_without_resending', 'separate_recovery_accounting': True}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    with temporary.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class RecoveryClient:
    def __init__(self, model, method, folder, historical_calls, phase='candidate',
                 paid_allowed=False, provider_client=None):
        if model not in original.PRICES_USD_PER_MILLION or method not in {'lea', 'full-scc'}:
            raise ValueError('Unsupported recovery model or method')
        if phase not in {'candidate', 'selector'}:
            raise ValueError('Unsupported phase')
        self.model, self.method, self._phase = model, method, phase
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock = (self.folder/'client.lock').open('a+')
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock.close()
            raise LedgerError('recovery_client_already_running') from None
        self.historical_calls = json.loads(json.dumps(historical_calls))
        self.history_consumed = 0
        self.paid_allowed = bool(paid_allowed)
        self._client = provider_client
        self._closed = False
        self._sequence = 0
        self._cache_hits = 0
        self._historical_cache_hits = 0
        self._last_historical = False
        self.last_call_record = self.last_response = None
        self.last_usage = {}
        self.max_model_len = 131072
        self.token_cap = None
        self.guard_active = True
        self._selector_reserve = 0
        self._secret = os.environ.get('XHUB_API_KEY', '').strip()
        self.tokenizer = original.tiktoken.get_encoding(original.ESTIMATE_POLICY['encoding'])
        self._records = {}
        manifest = {'policy': POLICY, 'model': model, 'method': method, 'phase': phase,
                    'historical_calls_sha256': _digest(self.historical_calls),
                    'historical_call_count': len(self.historical_calls)}
        try:
            path = self.folder/'client_manifest.json'
            if path.exists():
                if json.loads(path.read_text()) != manifest:
                    raise LedgerError('recovery_identity_changed')
            else:
                _write(path, manifest)
            for path in (self.folder/'calls').glob('*.json'):
                record = json.loads(path.read_text())
                if record.get('request_sha256') != _digest(record.get('request')):
                    raise LedgerError('recovery_request_corrupt')
                if record.get('result') is not None and record.get('result_sha256') != _digest(record['result']):
                    raise LedgerError('recovery_response_corrupt')
                self._records[path.name] = record
        except BaseException:
            self._lock.close()
            raise

    @property
    def remaining_tokens(self):
        return math.inf

    @property
    def token_usage(self):
        summary = self.summary()
        return {key: summary[key] for key in ('prompt_tokens', 'completion_tokens',
                    'total_tokens', 'held_tokens', 'accounted_tokens')}

    def set_phase(self, phase):
        if phase != self._phase:
            raise LedgerError('recovery_phase_changed')

    def set_selector_reserve(self, tokens):
        self._selector_reserve = tokens

    def count_tokens(self, text):
        return len(self.tokenizer.encode(text, disallowed_special=()))

    def estimate_request(self, prompt, *, system_prompt=None, max_tokens=4096,
                         response_format=None, respect_budget=True):
        return original.BudgetClient.estimate_request(self, prompt, system_prompt=system_prompt,
            max_tokens=max_tokens, response_format=response_format, respect_budget=False)

    def assert_history_consumed(self):
        if self.history_consumed != len(self.historical_calls):
            raise LedgerError('historical_candidate_prefix_not_fully_consumed')

    async def _transport_sleep(self, seconds):
        await asyncio.sleep(seconds)

    def _body(self, prompt, temperature, max_tokens, system_prompt, response_format):
        estimate = self.estimate_request(prompt, system_prompt=system_prompt,
                                        max_tokens=max_tokens, response_format=response_format)
        if estimate['max_output_tokens'] <= 0:
            raise BudgetStop('recovery_context_limit')
        body = {'model': self.model, 'messages': estimate['messages'],
                'temperature': temperature, 'max_tokens': estimate['max_output_tokens']}
        if response_format:
            body['response_format'] = response_format
        return body

    def _history(self, body, max_tokens, retry_index):
        index = self.history_consumed
        if index >= len(self.historical_calls):
            return None
        old = self.historical_calls[index]
        reservation = old.get('reservation', {})
        if (old.get('call_id') != reservation.get('call_id') or
                old.get('request_hash') != reservation.get('request_hash')):
            raise LedgerError('historical_request_identity_mismatch')
        if reservation.get('retry_index', retry_index) != retry_index:
            raise LedgerError('historical_json_attempt_mismatch')
        if reservation.get('requested_max_output_tokens', max_tokens) != max_tokens:
            raise LedgerError('historical_requested_output_limit_mismatch')
        stored = old.get('request', {})
        keys = ('model', 'messages', 'temperature', 'response_format')
        if any(stored.get(key) != body.get(key) for key in keys):
            raise LedgerError('historical_request_body_mismatch')
        if not isinstance(stored.get('max_tokens'), int) or stored['max_tokens'] <= 0:
            raise LedgerError('historical_output_limit_invalid')
        self.history_consumed += 1
        return index, old

    def _response(self, record, *, historical=False):
        result = record.get('result')
        if not isinstance(result, dict):
            raise BudgetStop('recovery_response_missing')
        usage = result.get('usage') or {}
        prompt, completion = usage.get('prompt_tokens'), usage.get('completion_tokens')
        total = usage.get('total_tokens', (prompt + completion) if
                          original._valid_tokens(prompt) and original._valid_tokens(completion) else None)
        if not all(original._valid_tokens(x) for x in (prompt, completion, total)) or total < prompt + completion:
            raise BudgetStop('recovery_provider_usage_missing_or_invalid')
        expected = record.get('response_sha256') or record.get('reservation', {}).get('response_sha256')
        if expected and original._hash(result) != expected:
            raise LedgerError('historical_response_hash_mismatch')
        self._last_historical = historical
        self.last_call_record, self.last_usage = record, usage
        response = BudgetLLMResponse(content=result.get('content', ''), model=result.get('model', self.model),
                                     usage=usage, raw=result.get('raw'))
        self.last_response = response
        return response

    async def _paid(self, body, *, logical, first_attempt, source=None):
        for attempt in range(first_attempt, 3):
            name = f'{logical}.transport{attempt}.json'
            path = self.folder/'calls'/name
            if name in self._records:
                record = self._records[name]
                if record['request'] != body or record.get('source_call_id') != source:
                    raise LedgerError('recovery_cached_request_mismatch')
                self._cache_hits += 1
            else:
                if not self.paid_allowed:
                    raise BudgetStop('paid_recovery_disabled')
                if any(r['status'] in {'reserved', 'completed_without_usage'} for r in self._records.values()):
                    raise BudgetStop('unresolved_recovery_request')
                if self._client is None:
                    if not self._secret:
                        raise BudgetStop('XHUB_API_KEY_missing')
                    self._client = original.AsyncOpenAI(api_key=self._secret, base_url=ENDPOINT,
                        timeout=120, max_retries=0,
                        http_client=original.DefaultAsyncHttpxClient(trust_env=False))
                if attempt > 0:
                    await self._transport_sleep(POLICY['backoff_seconds'][attempt - 1])
                record = {'call_id': uuid.uuid4().hex, 'source_call_id': source,
                          'logical_key': logical, 'transport_attempt': attempt,
                          'model': self.model, 'phase': self._phase, 'request': body,
                          'request_sha256': _digest(body), 'status': 'reserved',
                          'started_at_unix': time.time()}
                _write(path, record)
                self._records[name] = record
                start = time.monotonic()
                try:
                    raw = await self._client.chat.completions.create(**body)
                except BaseException as error:
                    status = getattr(error, 'status_code', None)
                    record.update(status='unknown_failure', error_type=type(error).__name__,
                                  http_status=status if type(status) is int else None,
                                  elapsed_seconds=time.monotonic()-start)
                    _write(path, record)
                    if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                        raise
                else:
                    usage = original._safe(getattr(raw, 'usage', None), self._secret) or {}
                    try:
                        content = raw.choices[0].message.content or ''
                    except (IndexError, AttributeError, TypeError):
                        content = ''
                    result = original._safe({'content': content, 'model': getattr(raw, 'model', self.model),
                                              'usage': usage, 'raw': raw}, self._secret)
                    record.update(status='completed_with_usage', result=result,
                                  result_sha256=_digest(result), elapsed_seconds=time.monotonic()-start)
                    try:
                        self._response(record)
                    except BudgetStop:
                        record['status'] = 'completed_without_usage'
                    _write(path, record)
            self.last_call_record = record
            if record['status'] == 'completed_with_usage':
                return self._response(record)
            if record['status'] == 'reserved':
                raise BudgetStop('unresolved_recovery_request')
            if record['status'] == 'completed_without_usage':
                raise BudgetStop('recovery_provider_usage_missing_or_invalid')
            if record.get('http_status') != 503:
                raise BudgetStop('recovery_non503_failure', http_status=record.get('http_status'))
        raise BudgetStop('http503_transport_attempts_exhausted', attempts=3)

    async def _call(self, prompt, *, temperature, max_tokens, system_prompt,
                    response_format, logical, retry_index):
        if self._closed:
            raise LedgerError('recovery_client_closed')
        body = self._body(prompt, temperature, max_tokens, system_prompt, response_format)
        historical = self._history(body, max_tokens, retry_index)
        if historical is not None:
            index, old = historical
            self.last_call_record = old
            if isinstance(old.get('result'), dict):
                self._cache_hits += 1
                self._historical_cache_hits += 1
                return self._response(old, historical=True)
            if old.get('status') != 'unknown_failure' or old.get('http_status') != 503:
                raise BudgetStop('historical_non503_failure', http_status=old.get('http_status'))
            return await self._paid(old['request'], logical=f'history-{index:06d}',
                                    first_attempt=1, source=old['call_id'])
        if retry_index > 0:
            raise BudgetStop('new_parse_resampling_disabled')
        return await self._paid(body, logical=f'new-{logical:06d}', first_attempt=0)

    async def call(self, prompt, *, temperature=0, max_tokens=4096,
                   system_prompt=None, response_format=None, request_key=None):
        logical = self._sequence
        self._sequence += 1
        return await self._call(prompt, temperature=temperature, max_tokens=max_tokens,
            system_prompt=system_prompt, response_format=response_format, logical=logical, retry_index=0)

    async def call_json(self, prompt, *, temperature=0, max_tokens=4096,
                        system_prompt=None, retries=2, request_key=None):
        logical = self._sequence
        self._sequence += 1
        attempts = min(1 if self._phase == 'selector' else 3, max(1, int(retries)+1))
        for attempt in range(attempts):
            response = await self._call(prompt, temperature=temperature, max_tokens=max_tokens,
                system_prompt=system_prompt, response_format={'type': 'json_object'},
                logical=logical, retry_index=attempt)
            parsed = original._base.OpenAIClient._extract_json(response.content)
            if isinstance(parsed, dict):
                return parsed
            if not self._last_historical:
                raise BudgetStop('recovered_response_invalid_json_no_resampling')
        return {}

    def summary(self):
        rows = list(self._records.values())
        prompt = completion = total = 0
        cost = 0.0
        prices = original.PRICES_USD_PER_MILLION[self.model]
        for row in rows:
            if row['status'] != 'completed_with_usage':
                continue
            usage = row['result']['usage']
            p, c = usage['prompt_tokens'], usage['completion_tokens']
            t = usage.get('total_tokens', p+c)
            prompt += p; completion += c; total += t
            cost += (p * prices['input'] + max(c, t-p) * prices['output']) / 1_000_000
        return {'calls': len(rows), 'external_api_calls': len(rows),
                'completed_with_usage': sum(r['status'] == 'completed_with_usage' for r in rows),
                'unknown_failure_calls': sum(r['status'] == 'unknown_failure' for r in rows),
                'pending_calls': sum(r['status'] == 'reserved' for r in rows),
                'missing_usage_calls': sum(r['status'] == 'completed_without_usage' for r in rows),
                'explicit_503_calls': sum(r.get('http_status') == 503 for r in rows),
                'http503_calls': sum(r.get('http_status') == 503 for r in rows),
                'retry_calls': sum(r['transport_attempt'] > 0 for r in rows),
                'cache_replays': self._cache_hits, 'historical_cache_replays': self._historical_cache_hits,
                'history_consumed': self.history_consumed, 'history_count': len(self.historical_calls),
                'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': total,
                'accounted_tokens': total, 'held_tokens': 0,
                'estimated_cost_usd': cost, 'cost_is_estimate': True,
                'unresolved_cost_calls': sum(r['status'] != 'completed_with_usage' for r in rows),
                'accounting_scope': 'recovery_requests_only; unknown costs are not zero-cost claims'}

    async def close(self):
        if not self._closed:
            self._closed = True
            try:
                if self._client is not None:
                    await self._client.close()
            finally:
                self._lock.close()

"""Query-independent, fail-closed parser for controlled notes in one window."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from openai import OpenAI

from lfp_core import Atom, Fragment, Rule, canonical_json, parse_atom, sha256_text


ROOT = Path(__file__).resolve().parent
PROMPT_PATH = ROOT / "prompts" / "source_parser_system_v1.txt"
SCHEMA_PATH = ROOT / "prompts" / "source_parser_schema_v1.json"
VALIDATOR_VERSION = "controlled-note-positive-horn-v1"
DEFAULT_MODEL = "qwen2.5:14b"
EXPECTED_MODEL_DIGEST = "7cdf5a0187d5c58cc5d369b255592f7841d1c4696d45a8c8a9489440385b22f6"


NOTE_PATTERNS = (
    re.compile(
        r"\[CONTROLLED-LFP-NOTE\]\s*(.*?)\s*\[/CONTROLLED-LFP-NOTE\]",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\[LFP-INJECTION\]\s*(.*?)\s*\[/LFP-INJECTION\]",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\[CONTROLLED NOTE:\s*LFP-MCGS\]\s*(.*)$",
        re.IGNORECASE | re.DOTALL,
    ),
)


def extract_controlled_note(rendered_text: str) -> str | None:
    """Return only the explicit Paper-2 note; never send original BGB text."""
    matches: list[str] = []
    for pattern in NOTE_PATTERNS:
        matches.extend(match.strip() for match in pattern.findall(rendered_text) if match.strip())
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("fail-closed: expected exactly one controlled note")
    return matches[0]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _post_json(url: str, payload: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"local Ollama request failed: {exc}") from exc


@dataclass(frozen=True)
class CallStats:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_seconds: float = 0.0

    def __add__(self, other: "CallStats") -> "CallStats":
        return CallStats(
            self.calls + other.calls,
            self.prompt_tokens + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
            self.latency_seconds + other.latency_seconds,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "latency_seconds": round(self.latency_seconds, 6),
        }


class ProviderCallError(RuntimeError):
    """Sanitized provider failure with explicit paid-call accounting."""

    def __init__(self, message: str, stats: CallStats) -> None:
        super().__init__(message)
        self.stats = stats


class OllamaClient:
    provider = "ollama"

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = "http://localhost:11434",
        temperature: float = 0.0,
        timeout_seconds: float = 180.0,
        num_ctx: int = 16_384,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.base_url_host = urlparse(self.base_url).netloc
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.num_ctx = num_ctx
        self.model_digest = self._resolve_digest()

    def _resolve_digest(self) -> str:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5) as response:
                rows = json.loads(response.read().decode("utf-8")).get("models", [])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"cannot inspect local Ollama: {exc}") from exc
        for row in rows:
            if row.get("name") == self.model or row.get("model") == self.model:
                return str(row.get("digest") or "")
        raise RuntimeError(f"local Ollama model is missing: {self.model}")

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
    ) -> tuple[dict[str, Any], str, CallStats]:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        started = time.perf_counter()
        raw = _post_json(f"{self.base_url}/api/chat", payload, self.timeout_seconds)
        wall = time.perf_counter() - started
        content = str(raw.get("message", {}).get("content", ""))
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"model returned non-JSON: {content[:120]!r}") from exc
        stats = CallStats(
            calls=1,
            prompt_tokens=int(raw.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(raw.get("eval_count", 0) or 0),
            latency_seconds=wall,
        )
        return parsed, content, stats


def _extract_json_object(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise ValueError("model returned empty content")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced is None:
            raise ValueError(f"model returned non-JSON: {text[:120]!r}")
        try:
            parsed = json.loads(fenced.group(1))
        except json.JSONDecodeError as exc:
            raise ValueError(f"model returned non-JSON: {text[:120]!r}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("model JSON response is not an object")
    return parsed


class OpenAICompatibleClient:
    """Synchronous OpenAI-compatible client used for the xhub experiment arm."""

    provider = "xhub"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key_env: str = "XHUB_API_KEY",
        temperature: float = 0.0,
        timeout_seconds: float = 300.0,
        num_ctx: int = 32_768,
        max_tokens: int = 4_096,
    ) -> None:
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            raise RuntimeError(f"{api_key_env} is not set")
        parsed_url = urlparse(base_url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("xhub base URL must be a plain HTTPS endpoint")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.base_url_host = parsed_url.hostname
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.num_ctx = num_ctx
        self.max_tokens = max_tokens
        # xhub does not expose an immutable model digest.  This identifier is
        # intentionally named and recorded as a cache namespace, not a digest
        # claim about upstream weights.
        self.cache_namespace = sha256_text(
            canonical_json({
                "provider": self.provider,
                "base_url_host": self.base_url_host,
                "model": self.model,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "protocol": "openai-chat-json-object-v1",
            })
        )
        self.model_revision = None
        self.last_response_model_id: str | None = None
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            # Hidden SDK retries make paid-call accounting ambiguous.  The
            # runner records every explicit logical request instead.
            max_retries=0,
        )

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
    ) -> tuple[dict[str, Any], str, CallStats]:
        schema_instruction = (
            "\n\nReturn one JSON object that matches this JSON Schema exactly:\n"
            + json.dumps(schema, ensure_ascii=False, sort_keys=True)
        )
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system + schema_instruction},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # SDK exception classes vary by gateway/version.
            wall = time.perf_counter() - started
            status = getattr(exc, "status_code", None)
            suffix = f", status={status}" if status is not None else ""
            # Do not serialize the SDK exception body: a gateway error may
            # echo request metadata.  The class and status are sufficient for
            # the audit trail without risking credential disclosure.
            raise ProviderCallError(
                f"xhub request failed ({type(exc).__name__}{suffix})",
                CallStats(calls=1, latency_seconds=wall),
            ) from None
        wall = time.perf_counter() - started
        content = response.choices[0].message.content or ""
        parsed = _extract_json_object(content)
        self.last_response_model_id = str(getattr(response, "model", "") or self.model)
        usage = response.usage
        stats = CallStats(
            calls=1,
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            latency_seconds=wall,
        )
        return parsed, content, stats


@dataclass(frozen=True)
class ParseResult:
    source_id: str
    note_found: bool
    valid: bool
    decision: str
    fragment: Fragment | None
    error: str | None
    cache_hit: bool
    cache_key: str
    stats: CallStats
    recorded_stats: CallStats
    raw_response: str | None

    def as_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        row: dict[str, Any] = {
            "source_id": self.source_id,
            "note_found": self.note_found,
            "valid": self.valid,
            "decision": self.decision,
            "error": self.error,
            "cache_hit": self.cache_hit,
            "cache_key": self.cache_key,
            "stats": self.stats.as_dict(),
            "recorded_inference_stats": self.recorded_stats.as_dict(),
            "fragment": self.fragment.as_dict() if self.fragment else None,
        }
        if include_raw:
            row["raw_response"] = self.raw_response
        return row


def _strict_keys(raw: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != expected:
        found = sorted(raw) if isinstance(raw, Mapping) else type(raw).__name__
        raise ValueError(f"{label} fields must be exactly {sorted(expected)}; got {found}")
    return raw


def _literal_pattern(atom: Atom) -> re.Pattern[str]:
    arguments = r"\s*,\s*".join(re.escape(item) for item in atom.arguments)
    return re.compile(
        rf"(?<![\w]){re.escape(atom.predicate)}\s*\(\s*{arguments}\s*\)",
        re.IGNORECASE | re.UNICODE,
    )


def _evidence_atom(raw: Any, note: str, *, fact: bool) -> tuple[Atom, str]:
    fields = {"predicate", "arguments", "evidence"}
    row = _strict_keys(raw, fields, "fact")
    evidence = row["evidence"]
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("evidence must be non-empty")
    atom = parse_atom({"predicate": row["predicate"], "arguments": row["arguments"]})
    if fact and not atom.ground:
        raise ValueError("fact is not ground")
    # The hard source anchor is the exact symbolic literal in the extracted
    # note.  This tolerates a model adding/removing surrounding punctuation in
    # its evidence quote without weakening semantic validation.
    if _literal_pattern(atom).search(note) is None:
        raise ValueError(f"atom {atom} is not explicitly present in the note")
    return atom, evidence


def validate_model_output(
    raw: Any,
    *,
    source_id: str,
    rendered_text: str,
    note: str,
) -> tuple[str, Fragment]:
    row = _strict_keys(raw, {"decision", "facts", "rules"}, "top-level output")
    decision = row["decision"]
    if decision not in {"commit", "abstain"}:
        raise ValueError("decision must be commit or abstain")
    if not isinstance(row["facts"], list) or not isinstance(row["rules"], list):
        raise ValueError("facts/rules must be arrays")
    if decision == "abstain" and (row["facts"] or row["rules"]):
        raise ValueError("abstain must contain no facts or rules")
    if decision == "commit" and not (row["facts"] or row["rules"]):
        raise ValueError("commit must contain at least one fact or rule")

    facts = tuple(_evidence_atom(item, note, fact=True)[0] for item in row["facts"])
    rules: list[Rule] = []
    for index, item in enumerate(row["rules"]):
        rule_row = _strict_keys(item, {"head", "body", "evidence"}, "rule")
        evidence = rule_row["evidence"]
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("rule evidence must be non-empty")
        head = parse_atom(rule_row["head"])
        if not isinstance(rule_row["body"], list):
            raise ValueError("rule body must be an array")
        body = tuple(parse_atom(atom) for atom in rule_row["body"])
        for atom in (head, *body):
            if _literal_pattern(atom).search(note) is None:
                raise ValueError(f"rule atom {atom} is not explicitly present in the note")
        # The generator writes head <- body.  Check the direction, not merely
        # the bag of mentioned literals, before accepting a rule.
        compact_note = re.sub(r"\s+", "", note.lower())
        compact_head = re.sub(r"\s+", "", str(head).lower())
        compact_bodies = [re.sub(r"\s+", "", str(atom).lower()) for atom in body]
        arrow = compact_note.find(f"{compact_head}<-")
        if arrow < 0 or any(item not in compact_note[arrow:] for item in compact_bodies):
            raise ValueError("rule direction/body is not explicitly anchored by head <- body")
        rules.append(
            Rule(
                sha256_text(f"{source_id}|{index}|{evidence}")[:16],
                head,
                body,
                source_id,
            )
        )
    fragment = Fragment(
        source_id=source_id,
        source_text_sha256=sha256_text(rendered_text),
        facts=facts,
        rules=tuple(rules),
        validated=True,
        validation_note=VALIDATOR_VERSION,
    )
    return str(decision), fragment


class LocalNoteParser:
    def __init__(
        self,
        *,
        cache_path: Path,
        client: OllamaClient,
        refresh_cache: bool = False,
    ) -> None:
        self.client = client
        self.cache_path = cache_path
        self.system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
        self.schema = _load_json(SCHEMA_PATH)
        self.prompt_hash = sha256_text(self.system_prompt)
        self.schema_hash = sha256_text(canonical_json(self.schema))
        self.rows: dict[str, dict[str, Any]] = {}
        if cache_path.exists() and not refresh_cache:
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[str(row["cache_key"])] = row

    def _key(self, source_id: str, rendered_text: str, note: str | None) -> str:
        return sha256_text(canonical_json({
            "source_id": source_id,
            "model": self.client.model,
            "model_digest": self.client.model_digest,
            "temperature": self.client.temperature,
            "num_ctx": self.client.num_ctx,
            "prompt_hash": self.prompt_hash,
            "schema_hash": self.schema_hash,
            "validator_version": VALIDATOR_VERSION,
            "rendered_text_sha256": sha256_text(rendered_text),
            "note_sha256": sha256_text(note) if note is not None else None,
        }))

    def _persist(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in sorted(self.rows.values(), key=lambda item: item["cache_key"])
        )
        temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.cache_path)

    def parse(self, *, source_id: str, rendered_text: str) -> ParseResult:
        try:
            note = extract_controlled_note(rendered_text)
        except ValueError as exc:
            note = None
            extraction_error = str(exc)
        else:
            extraction_error = None
        key = self._key(source_id, rendered_text, note)
        cached = self.rows.get(key)
        if cached is not None:
            fragment = None
            if cached.get("valid") and cached.get("fragment") is not None:
                fragment_raw = cached["fragment"]
                fragment = Fragment(
                    source_id=source_id,
                    source_text_sha256=sha256_text(rendered_text),
                    facts=tuple(parse_atom(atom) for atom in fragment_raw.get("facts", [])),
                    rules=tuple(
                        Rule(
                            str(rule.get("rule_id") or ""),
                            parse_atom(rule["head"]),
                            tuple(parse_atom(atom) for atom in rule["body"]),
                            source_id,
                        )
                        for rule in fragment_raw.get("rules", [])
                    ),
                    validated=True,
                    validation_note=VALIDATOR_VERSION,
                )
            recorded_raw = cached.get("stats") or {}
            recorded_stats = CallStats(
                int(recorded_raw.get("calls", 0)),
                int(recorded_raw.get("prompt_tokens", 0)),
                int(recorded_raw.get("completion_tokens", 0)),
                float(recorded_raw.get("latency_seconds", 0.0)),
            )
            return ParseResult(
                source_id, bool(cached.get("note_found")), bool(cached.get("valid")),
                str(cached.get("decision", "invalid")), fragment, cached.get("error"),
                True, key, CallStats(), recorded_stats, cached.get("raw_response"),
            )

        raw_response: str | None = None
        stats = CallStats()
        if extraction_error:
            valid, decision, fragment, error = False, "invalid", None, extraction_error
        elif note is None:
            # No Paper-2 marker means original BGB text only.  Abstention is
            # deterministic and costs no model call.
            fragment = Fragment(
                source_id, sha256_text(rendered_text), (), (), True,
                "no_controlled_note_abstention",
            )
            valid, decision, error = True, "abstain", None
        else:
            try:
                raw, raw_response, stats = self.client.chat_json(
                    system=self.system_prompt,
                    user=f"Controlled note:\n{note}",
                    schema=self.schema,
                )
                decision, fragment = validate_model_output(
                    raw,
                    source_id=source_id,
                    rendered_text=rendered_text,
                    note=note,
                )
                valid, error = True, None
            except (RuntimeError, ValueError, KeyError, TypeError) as exc:
                valid, decision, fragment, error = False, "invalid", None, str(exc)

        row = {
            "cache_key": key,
            "source_id": source_id,
            "model": self.client.model,
            "model_digest": self.client.model_digest,
            "temperature": self.client.temperature,
            "prompt_hash": self.prompt_hash,
            "schema_hash": self.schema_hash,
            "validator_version": VALIDATOR_VERSION,
            "rendered_text_sha256": sha256_text(rendered_text),
            "note_found": note is not None,
            "note_sha256": sha256_text(note) if note is not None else None,
            "valid": valid,
            "decision": decision,
            "error": error,
            "fragment": fragment.as_dict() if fragment else None,
            "stats": stats.as_dict(),
            "raw_response": raw_response,
        }
        self.rows[key] = row
        self._persist()
        return ParseResult(
            source_id, note is not None, valid, decision, fragment, error,
            False, key, stats, stats, raw_response,
        )

#!/usr/bin/env python3
"""Run the two SA-MCGS-lineage baselines on every frozen BGB carrier size.

The experiment has two deliberately different access patterns:

1. ``full-direct`` / ``full-cot``: one model call receives every source in the
   SCC.  This is the full-context baseline used to test whether a general LLM
   can solve the case in one pass.
2. ``lea``: deterministic graph windows use the same source-local symbolic
   evidence schema, then transparently union validated fragments and run exact
   LFP once at the end.  LEA has no PUCT, online closure feedback, critical-pair
   revisit, relation memory, or dynamic window selection.

Gold programs and labels are evaluator-only.  They are used after prediction
for exact parsing/proof checks and never enter either model prompt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from dotenv import load_dotenv

from lfp_core import (
    CommittedKB,
    ExecutionReceipt,
    Fragment,
    Rule,
    canonical_json,
    least_fixed_point,
    sha256_text,
    source_set_sufficient,
    verify_proof,
)
from local_parser import (
    VALIDATOR_VERSION,
    CallStats,
    OpenAICompatibleClient,
    ProviderCallError,
    validate_model_output,
)
from run_phase2 import (
    CACHE,
    DEFAULT_COMBINED,
    DEFAULT_GOLD,
    DEFAULT_PUBLIC,
    ROOT,
    BaselineCache,
    EvaluatorSidecar,
    PublicCase,
    PublicSource,
    _aggregate_baselines,
    _baseline_gold_kb,
    gold_fragment,
    load_cases,
    read_jsonl,
    sha256_file,
    sum_stats,
    write_json,
    write_jsonl,
)


RESULTS_DIR = ROOT / "results" / "phase4_xhub_baselines"
LEA_SYSTEM = ROOT / "prompts" / "lea_window_system_v1.txt"
LEA_SCHEMA = ROOT / "prompts" / "lea_window_schema_v1.json"
LEA_VALIDATOR_VERSION = f"lea-raw-window-v1+{VALIDATOR_VERSION}"
DEFAULT_XHUB_BASE_URL = "https://api3.xhub.chat/v1"
DEFAULT_XHUB_MODEL = "qwen-turbo"
JSON_REQUEST_PROTOCOL = "xhub-openai-chat-json-object-v1"


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or "model"


def run_full_graph_context_baseline(
    public: PublicCase,
    sidecar: EvaluatorSidecar,
    raw_public: Mapping[str, Any],
    *,
    policy: str,
    client: OpenAICompatibleClient,
    cache: BaselineCache,
    max_chars: int,
) -> dict[str, Any]:
    """One call sees every source and the complete directed SCC topology."""
    system_path = ROOT / "prompts" / f"{policy}_system_v1.txt"
    schema_path = ROOT / "prompts" / "baseline_schema_v1.json"
    system = system_path.read_text(encoding="utf-8")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    sources = [
        {"source_id": source.source_id, "heading": source.heading, "text": source.rendered_text}
        for source in public.sources
    ]
    user = json.dumps({
        "query_text": public.query_text,
        "query_atom": public.query.as_dict(),
        "directed_reference_edges": raw_public.get("topology", {}).get("edges", []),
        "sources": sources,
    }, ensure_ascii=False, sort_keys=True)
    common = {
        "case_id": public.case_id,
        "carrier_size": public.carrier_size,
        "condition": public.condition,
        "policy": policy,
        "method": f"Full-SCC {'CoT' if policy == 'cot' else 'Direct'}",
        "expected_label": sidecar.expected_label,
        "public_input_sha256": public.raw_public_sha256,
        "visible_chars": len(user),
        "source_count": len(public.sources),
        "edge_count": len(raw_public.get("topology", {}).get("edges", [])),
        "provider": client.provider,
        "base_url_host": client.base_url_host,
        "model": client.model,
        "num_ctx": client.num_ctx,
        "num_ctx_semantics": "diagnostic_assumed_context_limit_not_sent_to_xhub",
    }
    if len(user) > max_chars:
        return {
            **common,
            "skipped": True,
            "skip_reason": f"visible context {len(user)} > cap {max_chars}",
            "new_model_usage": CallStats().as_dict(),
            "recorded_inference_usage": CallStats().as_dict(),
        }
    key = sha256_text(canonical_json({
        "provider": client.provider,
        "base_url_host": client.base_url_host,
        "model": client.model,
        "cache_namespace": client.cache_namespace,
        "temperature": client.temperature,
        "num_ctx": client.num_ctx,
        "max_tokens": client.max_tokens,
        "policy": policy,
        "system_hash": sha256_text(system),
        "schema_hash": sha256_text(canonical_json(schema)),
        "user_hash": sha256_text(user),
        "protocol": f"full-directed-scc-v1+{JSON_REQUEST_PROTOCOL}",
    }))
    cached = cache.get(key)
    stats = CallStats()
    if cached is None:
        try:
            raw, raw_response, stats = client.chat_json(system=system, user=user, schema=schema)
            response_model_id = client.last_response_model_id or client.model
            error = None
        except (RuntimeError, ValueError) as exc:
            if isinstance(exc, ProviderCallError):
                stats = exc.stats
            raw, raw_response, response_model_id, error = None, None, None, str(exc)
        cache.put(key, {
            "raw": raw,
            "raw_response": raw_response,
            "error": error,
            "response_model_id": response_model_id,
            "original_usage": stats.as_dict(),
        })
        cache_hit = False
        recorded_stats = stats
    else:
        raw, error = cached.get("raw"), cached.get("error")
        response_model_id = cached.get("response_model_id")
        cache_hit = True
        usage = cached.get("original_usage") or {}
        recorded_stats = CallStats(
            int(usage.get("calls", 0)),
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
            float(usage.get("latency_seconds", 0.0)),
        )

    answer_schema_valid = citation_contract_valid = valid = False
    label = "INVALID"
    claimed_sources: list[str] = []
    rationale = ""
    if error is None:
        try:
            if not isinstance(raw, Mapping) or set(raw) != {"label", "proof_source_ids", "rationale"}:
                raise ValueError("baseline output has wrong fields")
            label = str(raw["label"])
            if label not in {"Entailed", "PR-Unknown"}:
                raise ValueError("invalid label")
            if not isinstance(raw["proof_source_ids"], list):
                raise ValueError("proof_source_ids is not a list")
            claimed_sources = [str(item) for item in raw["proof_source_ids"]]
            rationale = str(raw["rationale"])
            answer_schema_valid = True
        except (TypeError, ValueError) as exc:
            error = str(exc)
    if answer_schema_valid:
        if len(claimed_sources) != len(set(claimed_sources)):
            error = "duplicate proof source"
        elif not set(claimed_sources) <= set(public.source_map):
            error = "proof cites a hidden/nonexistent source"
        elif label == "PR-Unknown" and claimed_sources:
            error = "PR-Unknown must not claim a proof"
        else:
            citation_contract_valid = valid = True
    if valid and label == "Entailed":
        proof_kb = _baseline_gold_kb(public, sidecar, claimed_sources)
        proof_source_valid = least_fixed_point(proof_kb).entails(public.query)
    elif valid and label == "PR-Unknown":
        proof_source_valid = not claimed_sources
    else:
        proof_source_valid = False
    near_context_cap = recorded_stats.prompt_tokens >= int(client.num_ctx * 0.95)
    strict_answer_and_proof = (
        valid
        and label == sidecar.expected_label
        and (
            (label == "Entailed" and proof_source_valid)
            or (label == "PR-Unknown" and not claimed_sources)
        )
    )
    oracle_minimum_cover = set(
        sidecar.raw.get("oracle", {}).get("minimum_source_cover", []) or []
    )
    exact_minimum_source_cover = (
        label == "Entailed"
        and label == sidecar.expected_label
        and set(claimed_sources) == oracle_minimum_cover
    )
    return {
        **common,
        "skipped": False,
        "cache_hit": cache_hit,
        "cache_key": key,
        "response_model_id": response_model_id,
        "valid": valid,
        "answer_schema_valid": answer_schema_valid,
        "citation_contract_valid": citation_contract_valid,
        "error": error,
        "predicted_label": label,
        "answer_label_exact": answer_schema_valid and label == sidecar.expected_label,
        "label_exact": valid and label == sidecar.expected_label,
        "strict_answer_and_proof": strict_answer_and_proof,
        "exact_minimum_source_cover": exact_minimum_source_cover,
        "unknown_false_entailment": sidecar.expected_label == "PR-Unknown" and label == "Entailed",
        "proof_source_ids": claimed_sources,
        "proof_source_valid": proof_source_valid,
        "rationale": rationale,
        "near_context_cap": near_context_cap,
        "context_utilization": (
            recorded_stats.prompt_tokens / client.num_ctx if client.num_ctx else None
        ),
        "new_model_usage": stats.as_dict(),
        "recorded_inference_usage": recorded_stats.as_dict(),
    }


def _raw_public_cases(combined: Path, public: Path) -> dict[str, Mapping[str, Any]]:
    rows = read_jsonl(combined) if combined.exists() else read_jsonl(public)
    output: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        raw = row.get("public_case", row.get("public", row))
        output[str(raw["case_id"])] = raw
    return output


def deterministic_windows(raw_public: Mapping[str, Any], window_size: int) -> list[tuple[str, ...]]:
    """Faithful LEA policy: center + directed neighbors + SCC-order fill."""
    order = [str(item) for item in raw_public["source_order"]]
    positions = {source_id: index for index, source_id in enumerate(order)}
    adjacency: dict[str, set[str]] = {source_id: set() for source_id in order}
    for edge in raw_public.get("topology", {}).get("edges", []):
        source = str(edge["source"])
        target = str(edge["target"])
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
            adjacency[target].add(source)

    windows: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    target_size = min(window_size, len(order))
    for index, center in enumerate(order):
        window = [center]
        for neighbor in sorted(adjacency[center], key=positions.__getitem__):
            if neighbor not in window:
                window.append(neighbor)
            if len(window) >= target_size:
                break
        offset = 1
        while len(window) < target_size:
            for candidate in (order[(index + offset) % len(order)], order[(index - offset) % len(order)]):
                if candidate not in window:
                    window.append(candidate)
                if len(window) >= target_size:
                    break
            offset += 1
        key = tuple(window)
        if key not in seen:
            seen.add(key)
            windows.append(key)
    return windows


def deduplicate_window_sets(windows: Sequence[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """Reuse the first ordering for duplicate unordered LEA node sets.

    The rebuttal implementation keyed its local-evaluation cache by
    ``frozenset(window)``.  Explicit de-duplication is the deterministic,
    stronger equivalent for Paper 2 because Horn union is order invariant.
    """
    output: list[tuple[str, ...]] = []
    seen: set[frozenset[str]] = set()
    for window in windows:
        key = frozenset(window)
        if key not in seen:
            seen.add(key)
            output.append(window)
    return output


@dataclass(frozen=True)
class LEAWindowResult:
    window: tuple[str, ...]
    fragments: Mapping[str, Fragment]
    valid_sources: frozenset[str]
    errors: Mapping[str, str]
    cache_hit: bool
    cache_key: str
    response_model_id: str | None
    new_stats: CallStats
    recorded_stats: CallStats


class LEAWindowParser:
    def __init__(
        self,
        client: OpenAICompatibleClient,
        cache_path: Path,
        refresh: bool = False,
    ) -> None:
        self.client = client
        self.system = LEA_SYSTEM.read_text(encoding="utf-8")
        self.schema = json.loads(LEA_SCHEMA.read_text(encoding="utf-8"))
        self.cache = BaselineCache(cache_path, refresh)

    def _key(self, user: str, window_size: int) -> str:
        return sha256_text(canonical_json({
            "provider": self.client.provider,
            "base_url_host": self.client.base_url_host,
            "model": self.client.model,
            "cache_namespace": self.client.cache_namespace,
            "temperature": self.client.temperature,
            "num_ctx": self.client.num_ctx,
            "max_tokens": self.client.max_tokens,
            "window_size": window_size,
            "prompt_hash": sha256_text(self.system),
            "schema_hash": sha256_text(canonical_json(self.schema)),
            "validator_version": LEA_VALIDATOR_VERSION,
            "request_protocol": JSON_REQUEST_PROTOCOL,
            "user_hash": sha256_text(user),
        }))

    def parse(
        self,
        *,
        sources: Sequence[PublicSource],
        window_size: int,
    ) -> LEAWindowResult:
        window = tuple(source.source_id for source in sources)
        source_map = {source.source_id: source for source in sources}
        user = json.dumps({
            "sources": [
                {"source_id": source.source_id, "heading": source.heading, "text": source.rendered_text}
                for source in sources
            ]
        }, ensure_ascii=False, sort_keys=True)
        key = self._key(user, window_size)
        cached = self.cache.get(key)
        new_stats = CallStats()
        if cached is None:
            try:
                raw, raw_response, new_stats = self.client.chat_json(
                    system=self.system,
                    user=user,
                    schema=self.schema,
                )
                response_model_id = self.client.last_response_model_id or self.client.model
                error = None
            except (RuntimeError, ValueError) as exc:
                if isinstance(exc, ProviderCallError):
                    new_stats = exc.stats
                raw, raw_response, response_model_id, error = None, None, None, str(exc)
            self.cache.put(key, {
                "raw": raw,
                "raw_response": raw_response,
                "error": error,
                "response_model_id": response_model_id,
                "original_usage": new_stats.as_dict(),
            })
            cache_hit = False
            recorded_stats = new_stats
        else:
            raw = cached.get("raw")
            error = cached.get("error")
            response_model_id = cached.get("response_model_id")
            cache_hit = True
            usage = cached.get("original_usage") or {}
            recorded_stats = CallStats(
                int(usage.get("calls", 0)),
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
                float(usage.get("latency_seconds", 0.0)),
            )

        fragments: dict[str, Fragment] = {}
        valid_sources: set[str] = set()
        errors: dict[str, str] = {}
        if error is not None:
            errors["__window__"] = str(error)
        else:
            try:
                if not isinstance(raw, Mapping) or set(raw) != {"sources"}:
                    raise ValueError("top-level output must contain only sources")
                rows = raw["sources"]
                if not isinstance(rows, list):
                    raise ValueError("sources output is not an array")
                ids = [str(item.get("source_id")) for item in rows if isinstance(item, Mapping)]
                if len(rows) != len(window) or len(set(ids)) != len(ids) or set(ids) != set(window):
                    raise ValueError("output must contain every window source exactly once")
                for item in rows:
                    source_id = str(item["source_id"])
                    nested = {key: value for key, value in item.items() if key != "source_id"}
                    source = source_map[source_id]
                    try:
                        _, fragment = validate_model_output(
                            nested,
                            source_id=source_id,
                            rendered_text=source.rendered_text,
                            note=source.rendered_text,
                        )
                    except (TypeError, ValueError) as exc:
                        errors[source_id] = str(exc)
                    else:
                        fragments[source_id] = fragment
                        valid_sources.add(source_id)
            except (TypeError, ValueError) as exc:
                errors["__window__"] = str(exc)
        return LEAWindowResult(
            window=window,
            fragments=fragments,
            valid_sources=frozenset(valid_sources),
            errors=errors,
            cache_hit=cache_hit,
            cache_key=key,
            response_model_id=response_model_id,
            new_stats=new_stats,
            recorded_stats=recorded_stats,
        )


def _merge_source_fragments(source: PublicSource, fragments: Iterable[Fragment]) -> Fragment:
    facts = set()
    rules_by_signature: dict[str, Rule] = {}
    for fragment in fragments:
        facts.update(fragment.facts)
        for rule in fragment.rules:
            rules_by_signature.setdefault(rule.signature, rule)
    rules = tuple(
        Rule(
            sha256_text(f"lea|{source.source_id}|{signature}")[:16],
            rule.head,
            rule.body,
            source.source_id,
        )
        for signature, rule in sorted(rules_by_signature.items())
    )
    return Fragment(
        source_id=source.source_id,
        source_text_sha256=sha256_text(source.rendered_text),
        facts=tuple(facts),
        rules=rules,
        validated=True,
        validation_note=LEA_VALIDATOR_VERSION,
    )


def run_lea_case(
    public: PublicCase,
    sidecar: EvaluatorSidecar,
    raw_public: Mapping[str, Any],
    *,
    parser: LEAWindowParser,
    window_size: int,
) -> dict[str, Any]:
    candidate_windows = deterministic_windows(raw_public, window_size)
    windows = deduplicate_window_sets(candidate_windows)
    observations: dict[str, list[Fragment]] = defaultdict(list)
    source_valid_observations: dict[str, int] = defaultdict(int)
    source_exact_observations: dict[str, int] = defaultdict(int)
    nonempty_observations = 0
    nonempty_valid_observations = 0
    nonempty_exact_observations = 0
    empty_observations = 0
    empty_exact_observations = 0
    new_stats = CallStats()
    recorded_stats = CallStats()
    observed_model_ids: set[str] = set()
    events: list[dict[str, Any]] = []
    for index, window in enumerate(windows, 1):
        result = parser.parse(
            sources=[public.source_map[source_id] for source_id in window],
            window_size=window_size,
        )
        new_stats += result.new_stats
        recorded_stats += result.recorded_stats
        if result.response_model_id:
            observed_model_ids.add(result.response_model_id)
        exact_ids: list[str] = []
        for source_id in window:
            gold = gold_fragment(public.source_map[source_id], sidecar)
            gold_nonempty = bool(gold.facts or gold.rules)
            nonempty_observations += int(gold_nonempty)
            empty_observations += int(not gold_nonempty)
            fragment = result.fragments.get(source_id)
            if fragment is None:
                continue
            observations[source_id].append(fragment)
            source_valid_observations[source_id] += 1
            nonempty_valid_observations += int(gold_nonempty)
            if fragment.semantic_signature == gold.semantic_signature:
                source_exact_observations[source_id] += 1
                exact_ids.append(source_id)
                nonempty_exact_observations += int(gold_nonempty)
                empty_exact_observations += int(not gold_nonempty)
        events.append({
            "window_index": index,
            "source_ids": list(window),
            "cache_hit": result.cache_hit,
            "cache_key": result.cache_key,
            "response_model_id": result.response_model_id,
            "valid_source_ids": sorted(result.valid_sources),
            "exact_source_ids": sorted(exact_ids),
            "errors": dict(result.errors),
            "recorded_inference_usage": result.recorded_stats.as_dict(),
        })

    kb = CommittedKB()
    merged_exact = 0
    merged_valid = 0
    merged_nonempty = 0
    merged_nonempty_exact = 0
    for sequence, source_id in enumerate(public.source_order, 1):
        source = public.source_map[source_id]
        if source_id not in observations:
            continue
        fragment = _merge_source_fragments(source, observations[source_id])
        gold = gold_fragment(source, sidecar)
        gold_nonempty = bool(gold.facts or gold.rules)
        merged_valid += 1
        merged_nonempty += int(gold_nonempty)
        exact = fragment.semantic_signature == gold.semantic_signature
        merged_exact += int(exact)
        merged_nonempty_exact += int(gold_nonempty and exact)
        kb = kb.commit(
            ExecutionReceipt(source_id, sha256_text(source.rendered_text), sequence),
            fragment,
        )

    lfp = least_fixed_point(kb)
    proof = lfp.proof(public.query)
    predicted = "Entailed" if lfp.entails(public.query) else "PR-Unknown"
    proof_valid = (
        verify_proof(kb, proof)
        and source_set_sufficient(kb, public.query, proof.source_ids)
        if proof is not None
        else predicted == "PR-Unknown"
    )
    oracle_minimum_cover = set(
        sidecar.raw.get("oracle", {}).get("minimum_source_cover", []) or []
    )
    exact_minimum_source_cover = (
        sidecar.expected_label == "Entailed"
        and proof is not None
        and set(proof.source_ids) == oracle_minimum_cover
    )
    observation_count = sum(len(window) for window in windows)
    valid_observations = sum(source_valid_observations.values())
    exact_observations = sum(source_exact_observations.values())
    return {
        "case_id": public.case_id,
        "carrier_size": public.carrier_size,
        "condition": public.condition,
        "policy": "lea",
        "method": "GraphRAG-style Local Evidence Aggregation",
        "method_boundary": (
            "Deterministic local graph windows + raw-window symbolic extraction + transparent "
            "validated union + end-only exact LFP; no PUCT or online closure feedback."
        ),
        "expected_label": sidecar.expected_label,
        "provider": parser.client.provider,
        "base_url_host": parser.client.base_url_host,
        "model": parser.client.model,
        "observed_model_ids": sorted(observed_model_ids),
        "num_ctx": parser.client.num_ctx,
        "num_ctx_semantics": "diagnostic_assumed_context_limit_not_sent_to_xhub",
        "predicted_label": predicted,
        "label_exact": predicted == sidecar.expected_label,
        "strict_answer_and_proof": predicted == sidecar.expected_label and proof_valid,
        "unknown_false_entailment": sidecar.expected_label == "PR-Unknown" and predicted == "Entailed",
        "proof_valid": proof_valid,
        "exact_minimum_source_cover": exact_minimum_source_cover,
        "proof": proof.as_dict() if proof else None,
        "window_size": window_size,
        "window_candidates": len(candidate_windows),
        "windows": len(windows),
        "source_window_observations": observation_count,
        "valid_source_window_observations": valid_observations,
        "exact_source_window_observations": exact_observations,
        "source_window_valid_rate": valid_observations / observation_count if observation_count else None,
        "source_window_exact_rate": exact_observations / observation_count if observation_count else None,
        "nonempty_source_window_observations": nonempty_observations,
        "nonempty_valid_source_window_observations": nonempty_valid_observations,
        "nonempty_exact_source_window_observations": nonempty_exact_observations,
        "empty_source_window_observations": empty_observations,
        "empty_exact_source_window_observations": empty_exact_observations,
        "merged_sources": merged_valid,
        "merged_exact_sources": merged_exact,
        "merged_nonempty_sources": merged_nonempty,
        "merged_nonempty_exact_sources": merged_nonempty_exact,
        "committed_source_ids": list(kb.source_ids),
        "closure_size": len(lfp.closure),
        "lfp_iterations": lfp.iterations,
        "new_model_usage": new_stats.as_dict(),
        "recorded_inference_usage": recorded_stats.as_dict(),
        "events": events,
    }


def aggregate_lea(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed_model_ids = sorted({
        str(model_id)
        for row in rows
        for model_id in row.get("observed_model_ids", [])
        if model_id
    })
    output: dict[str, Any] = {
        "cases": len(rows),
        "label_exact": sum(bool(row["label_exact"]) for row in rows),
        "proof_valid": sum(bool(row["proof_valid"]) for row in rows),
        "strict_answer_and_proof": sum(bool(row["strict_answer_and_proof"]) for row in rows),
        "exact_minimum_source_cover": sum(bool(row["exact_minimum_source_cover"]) for row in rows),
        "unknown_false_entailments": sum(bool(row["unknown_false_entailment"]) for row in rows),
        "window_candidates": sum(int(row["window_candidates"]) for row in rows),
        "windows": sum(int(row["windows"]) for row in rows),
        "source_window_observations": sum(int(row["source_window_observations"]) for row in rows),
        "valid_source_window_observations": sum(int(row["valid_source_window_observations"]) for row in rows),
        "exact_source_window_observations": sum(int(row["exact_source_window_observations"]) for row in rows),
        "nonempty_source_window_observations": sum(int(row["nonempty_source_window_observations"]) for row in rows),
        "nonempty_valid_source_window_observations": sum(int(row["nonempty_valid_source_window_observations"]) for row in rows),
        "nonempty_exact_source_window_observations": sum(int(row["nonempty_exact_source_window_observations"]) for row in rows),
        "empty_source_window_observations": sum(int(row["empty_source_window_observations"]) for row in rows),
        "empty_exact_source_window_observations": sum(int(row["empty_exact_source_window_observations"]) for row in rows),
        "merged_sources": sum(int(row["merged_sources"]) for row in rows),
        "merged_exact_sources": sum(int(row["merged_exact_sources"]) for row in rows),
        "merged_nonempty_sources": sum(int(row["merged_nonempty_sources"]) for row in rows),
        "merged_nonempty_exact_sources": sum(int(row["merged_nonempty_exact_sources"]) for row in rows),
        "observed_model_ids": observed_model_ids,
    }
    denominator = output["source_window_observations"]
    output["source_window_valid_rate"] = output["valid_source_window_observations"] / denominator
    output["source_window_exact_rate"] = output["exact_source_window_observations"] / denominator
    nonempty_denominator = output["nonempty_source_window_observations"]
    output["nonempty_source_window_valid_rate"] = (
        output["nonempty_valid_source_window_observations"] / nonempty_denominator
        if nonempty_denominator else None
    )
    output["nonempty_source_window_exact_rate"] = (
        output["nonempty_exact_source_window_observations"] / nonempty_denominator
        if nonempty_denominator else None
    )
    output["logical_uncached_model_usage"] = sum_stats(
        CallStats(
            int(row["recorded_inference_usage"]["calls"]),
            int(row["recorded_inference_usage"]["prompt_tokens"]),
            int(row["recorded_inference_usage"]["completion_tokens"]),
            float(row["recorded_inference_usage"]["latency_seconds"]),
        )
        for row in rows
    ).as_dict()
    output["new_model_usage"] = sum_stats(
        CallStats(
            int(row["new_model_usage"]["calls"]),
            int(row["new_model_usage"]["prompt_tokens"]),
            int(row["new_model_usage"]["completion_tokens"]),
            float(row["new_model_usage"]["latency_seconds"]),
        )
        for row in rows
    ).as_dict()
    return output


def breakdown(rows: Sequence[Mapping[str, Any]], policy: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for size in sorted({int(row["carrier_size"]) for row in rows}):
        for condition in sorted({str(row["condition"]) for row in rows}):
            subset = [
                row for row in rows
                if int(row["carrier_size"]) == size and str(row["condition"]) == condition
            ]
            if not subset:
                continue
            output.append({
                "policy": policy,
                "carrier_size": size,
                "condition": condition,
                "n": len(subset),
                "evaluated": sum(not bool(row.get("skipped")) for row in subset),
                "label_exact": sum(bool(row.get("label_exact")) for row in subset),
                "strict_answer_and_proof": sum(bool(row.get("strict_answer_and_proof")) for row in subset),
                "proof_or_citation_set_valid": sum(
                    bool(row.get("proof_valid") or row.get("proof_source_valid")) for row in subset
                ),
                "unknown_false_entailments": sum(bool(row.get("unknown_false_entailment")) for row in subset),
                "visible_chars": sum(int(row.get("visible_chars", 0)) for row in subset),
                "recorded_calls": sum(int((row.get("recorded_inference_usage") or {}).get("calls", 0)) for row in subset),
                "recorded_tokens": sum(int((row.get("recorded_inference_usage") or {}).get("total_tokens", 0)) for row in subset),
                "recorded_latency_seconds": round(sum(float((row.get("recorded_inference_usage") or {}).get("latency_seconds", 0.0)) for row in subset), 6),
            })
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--combined", type=Path, default=DEFAULT_COMBINED)
    parser.add_argument("--public", type=Path, default=DEFAULT_PUBLIC)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--sizes", default="3,5,7,9,11,25")
    parser.add_argument("--conditions", default="Productive,Decoy,Broken,Clean,Matched-DAG")
    parser.add_argument("--methods", default="direct,cot,lea")
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--provider", choices=("xhub",), default="xhub")
    parser.add_argument("--model", default=DEFAULT_XHUB_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_XHUB_BASE_URL)
    parser.add_argument("--api-key-env", default="XHUB_API_KEY")
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--num-ctx", type=int, default=32_768)
    parser.add_argument("--max-tokens", type=int, default=4_096)
    parser.add_argument("--full-max-chars", type=int, default=100_000)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Repository credentials remain local and ignored.  Only the variable name
    # is recorded; its value never enters a cache, trial, summary, or manifest.
    load_dotenv(ROOT.parents[3] / ".env")
    sizes = {int(item) for item in args.sizes.split(",") if item.strip()}
    conditions = {item.strip().lower() for item in args.conditions.split(",") if item.strip()}
    methods = {item.strip().lower() for item in args.methods.split(",") if item.strip()}
    unknown = methods - {"direct", "cot", "lea"}
    if unknown:
        raise ValueError(f"unknown methods: {sorted(unknown)}")
    pairs = [
        pair for pair in load_cases(
            combined_path=args.combined,
            public_path=args.public,
            gold_path=args.gold,
        )
        if pair[0].carrier_size in sizes and pair[0].condition.lower() in conditions
    ]
    raw_public = _raw_public_cases(args.combined, args.public)
    if not pairs:
        raise RuntimeError("no cases survived filters")
    client = OpenAICompatibleClient(
        model=args.model,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        timeout_seconds=args.timeout_seconds,
        num_ctx=args.num_ctx,
        max_tokens=args.max_tokens,
    )
    cache_slug = _safe_slug(f"{client.provider}-{client.base_url_host}-{client.model}")

    full_rows: list[dict[str, Any]] = []
    full_cache = BaselineCache(
        CACHE / f"full_graph_context_baselines_{cache_slug}.jsonl",
        args.refresh_cache,
    )
    for public, sidecar in pairs:
        for policy in ("direct", "cot"):
            if policy in methods:
                full_rows.append(run_full_graph_context_baseline(
                    public,
                    sidecar,
                    raw_public[public.case_id],
                    policy=policy,
                    client=client,
                    cache=full_cache,
                    max_chars=args.full_max_chars,
                ))

    lea_rows: list[dict[str, Any]] = []
    if "lea" in methods:
        lea_parser = LEAWindowParser(
            client,
            CACHE / f"lea_raw_windows_{cache_slug}.jsonl",
            args.refresh_cache,
        )
        for public, sidecar in pairs:
            lea_rows.append(run_lea_case(
                public,
                sidecar,
                raw_public[public.case_id],
                parser=lea_parser,
                window_size=args.window_size,
            ))

    full_summary = _aggregate_baselines(full_rows)
    for policy, policy_summary in full_summary.items():
        policy_summary["strict_answer_and_proof"] = sum(
            bool(row["strict_answer_and_proof"])
            for row in full_rows
            if row["policy"] == policy
        )
        policy_summary["exact_minimum_source_cover"] = sum(
            bool(row["exact_minimum_source_cover"])
            for row in full_rows
            if row["policy"] == policy
        )
        policy_summary["near_context_cap"] = sum(
            bool(row.get("near_context_cap"))
            for row in full_rows
            if row["policy"] == policy
        )
        policy_summary["observed_model_ids"] = sorted({
            str(row["response_model_id"])
            for row in full_rows
            if row["policy"] == policy and row.get("response_model_id")
        })
    lea_summary = aggregate_lea(lea_rows) if lea_rows else {"cases": 0}
    all_breakdowns: list[dict[str, Any]] = []
    for policy in ("direct", "cot"):
        all_breakdowns.extend(breakdown([row for row in full_rows if row["policy"] == policy], policy))
    all_breakdowns.extend(breakdown(lea_rows, "lea"))
    gates = {
        "input_count_expected": len(pairs) == len(sizes) * len(conditions),
        "provider_is_xhub": client.provider == "xhub",
        "backend_metadata_complete": bool(
            client.base_url_host and client.model and client.cache_namespace
        ),
        "lea_unknown_false_entailment_zero": lea_summary.get("unknown_false_entailments", 0) == 0,
        "lea_source_window_valid_rate_ge_0_95": float(lea_summary.get("source_window_valid_rate", 1.0)) >= 0.95,
        "lea_source_window_exact_rate_ge_0_95": float(lea_summary.get("source_window_exact_rate", 1.0)) >= 0.95,
    }
    status = "PASS" if all(gates.values()) else "FAIL"
    summary = {
        "schema_version": "bgb-phase4-xhub-baselines-v3",
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "status_interpretation": (
            "PASS means the input, accounting, parser-validity, and negative-safety gates passed. "
            "It does not mean one baseline is superior or that LFP-PUCT is established."
        ),
        "claim_boundary": (
            "Exploratory controlled-intervention baseline smoke. Full-context tests one-pass "
            "general-LLM behavior; LEA controls local decomposition and schema burden. This does "
            "not establish natural-data generalization or an LFP-PUCT advantage."
        ),
        "filters": {"sizes": sorted(sizes), "conditions": sorted(conditions), "methods": sorted(methods)},
        "case_count": len(pairs),
        "model": {
            "provider": client.provider,
            "base_url_host": client.base_url_host,
            "requested_model": client.model,
            "observed_model_ids": sorted({
                str(model_id)
                for row in [*full_rows, *lea_rows]
                for model_id in (
                    row.get("observed_model_ids", [])
                    if isinstance(row.get("observed_model_ids"), list)
                    else [row.get("response_model_id")]
                )
                if model_id
            }),
            "model_revision": client.model_revision,
            "cache_namespace": client.cache_namespace,
            "temperature": client.temperature,
            "diagnostic_assumed_context_limit": client.num_ctx,
            "max_tokens": client.max_tokens,
            "timeout_seconds": client.timeout_seconds,
            "request_protocol": JSON_REQUEST_PROTOCOL,
            "api_key_env": client.api_key_env,
        },
        "protocol": {
            "full_context": "all SCC source windows plus every directed internal edge in one call; Direct and CoT prompts",
            "lea": (
                "deterministic center+neighbors+order-fill windows; raw-window positive-Horn "
                "extraction; transparent validated union; exact LFP only after all windows"
            ),
            "lea_window_size": args.window_size,
            "lea_window_set_deduplication": (
                "unordered node-set cache equivalence; first deterministic ordering retained"
            ),
            "lea_excludes": [
                "PUCT", "online closure feedback", "critical-pair revisit",
                "relation memory", "dynamic window selection", "dynamic core replacement",
            ],
        },
        "whole_context": full_summary,
        "lea": lea_summary,
        "breakdown": all_breakdowns,
        "gates": gates,
        "inputs": {
            "cases": {"path": str(args.combined), "sha256": sha256_file(args.combined)},
            "runner": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
            "local_parser": {"path": str(ROOT / "local_parser.py"), "sha256": sha256_file(ROOT / "local_parser.py")},
            "direct_system": {"path": str(ROOT / "prompts" / "direct_system_v1.txt"), "sha256": sha256_file(ROOT / "prompts" / "direct_system_v1.txt")},
            "cot_system": {"path": str(ROOT / "prompts" / "cot_system_v1.txt"), "sha256": sha256_file(ROOT / "prompts" / "cot_system_v1.txt")},
            "baseline_schema": {"path": str(ROOT / "prompts" / "baseline_schema_v1.json"), "sha256": sha256_file(ROOT / "prompts" / "baseline_schema_v1.json")},
            "lea_system": {"path": str(LEA_SYSTEM), "sha256": sha256_file(LEA_SYSTEM)},
            "lea_schema": {"path": str(LEA_SCHEMA), "sha256": sha256_file(LEA_SCHEMA)},
        },
    }
    args.results_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.results_dir / "full_context_trials.jsonl", full_rows)
    write_jsonl(args.results_dir / "lea_trials.jsonl", lea_rows)
    write_json(args.results_dir / "summary.json", summary)
    manifest = {
        "schema_version": "bgb-phase4-xhub-baselines-manifest-v2",
        "status": status,
        "inputs": summary["inputs"],
        "outputs": {
            name: {
                "path": str(args.results_dir / name),
                "sha256": sha256_file(args.results_dir / name),
            }
            for name in ("full_context_trials.jsonl", "lea_trials.jsonl", "summary.json")
        },
        "gates": gates,
    }
    write_json(args.results_dir / "manifest.json", manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Run the oracle replay, local parser, and tiny whole-context LLM baselines.

This runner deliberately stops before PUCT/MCGS.  It tests the first three
engineering smokes: frozen cases can be replayed, executed windows can become a
validated immutable KB, and exact LFP/proof reconstruction can close the query.
Direct/CoT are reported separately as whole-visible-context baselines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from lfp_core import (
    Atom,
    CommittedKB,
    ExecutionReceipt,
    Fragment,
    canonical_json,
    fragment_from_formal,
    least_fixed_point,
    parse_atom,
    sha256_text,
    source_set_sufficient,
    verify_proof,
)
from local_parser import (
    DEFAULT_MODEL,
    EXPECTED_MODEL_DIGEST,
    CallStats,
    LocalNoteParser,
    OllamaClient,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_COMBINED = ROOT / "data" / "cases.jsonl"
DEFAULT_PUBLIC = ROOT / "data" / "public_cases.jsonl"
DEFAULT_GOLD = ROOT / "data" / "gold_sidecar.jsonl"
RESULTS = ROOT / "results"
CACHE = ROOT / "cache"


def sum_stats(values: Iterable[CallStats]) -> CallStats:
    total = CallStats()
    for value in values:
        total += value
    return total


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"{path}:{number}: expected object")
                rows.append(row)
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


@dataclass(frozen=True)
class PublicSource:
    source_id: str
    rendered_text: str
    heading: str


@dataclass(frozen=True)
class PublicCase:
    case_id: str
    carrier_size: int
    condition: str
    query: Atom
    query_text: str
    sources: tuple[PublicSource, ...]
    source_order: tuple[str, ...]
    raw_public_sha256: str

    @property
    def source_map(self) -> dict[str, PublicSource]:
        return {source.source_id: source for source in self.sources}


@dataclass(frozen=True)
class EvaluatorSidecar:
    case_id: str
    expected_label: str
    query: Atom
    formal_by_source: Mapping[str, Mapping[str, Any]]
    recommended_order: tuple[str, ...]
    raw: Mapping[str, Any]


def _public_case(raw: Mapping[str, Any]) -> PublicCase:
    case_id = str(raw["case_id"])
    query_raw = raw.get("query", {})
    if isinstance(query_raw, Mapping) and "atom" in query_raw:
        query_atom = parse_atom(query_raw["atom"])
        query_text = str(query_raw.get("text", query_atom))
    else:
        query_atom = parse_atom(query_raw)
        query_text = str(raw.get("query_text", query_atom))
    sources: list[PublicSource] = []
    for source_raw in raw.get("sources", []):
        source_id = str(source_raw.get("source_id") or source_raw.get("id"))
        if not source_id or source_id == "None":
            raise ValueError(f"{case_id}: source without id")
        rendered = str(source_raw.get("rendered_text", source_raw.get("text", "")))
        sources.append(PublicSource(source_id, rendered, str(source_raw.get("heading", ""))))
    if not sources:
        raise ValueError(f"{case_id}: no sources")
    source_ids = {source.source_id for source in sources}
    order = tuple(str(item) for item in raw.get("source_order", []) if str(item) in source_ids)
    order += tuple(source.source_id for source in sources if source.source_id not in order)
    return PublicCase(
        case_id=case_id,
        carrier_size=int(raw.get("carrier_size", raw.get("size", len(sources)))),
        condition=str(raw.get("condition", "Unknown")),
        query=query_atom,
        query_text=query_text,
        sources=tuple(sources),
        source_order=order,
        raw_public_sha256=sha256_text(canonical_json(raw)),
    )


def _sidecar(raw: Mapping[str, Any]) -> EvaluatorSidecar:
    case_id = str(raw["case_id"])
    formal_by_source: dict[str, dict[str, list[Any]]] = {}
    for patch in raw.get("injected_patches", []) or []:
        source_id = str(patch.get("source_id"))
        if not source_id or source_id == "None":
            continue
        merged = formal_by_source.setdefault(source_id, {"facts": [], "rules": []})
        formal = patch.get("formal_injection") or patch.get("formal_outcome") or {}
        if formal.get("kind") == "fact":
            merged["facts"].append(formal["head"])
        elif formal.get("kind") == "rule":
            merged["rules"].append(formal)
        else:
            merged["facts"].extend(formal.get("facts", []) or [])
            merged["rules"].extend(formal.get("rules", []) or [])
    query_raw = raw.get("query_atom") or raw.get("query")
    return EvaluatorSidecar(
        case_id=case_id,
        expected_label=str(raw.get("expected_label", raw.get("label", "PR-Unknown"))),
        query=parse_atom(query_raw),
        formal_by_source=formal_by_source,
        recommended_order=tuple(str(item) for item in raw.get("recommended_smoke_execution_order", [])),
        raw=raw,
    )


def load_cases(
    *,
    combined_path: Path,
    public_path: Path,
    gold_path: Path,
) -> list[tuple[PublicCase, EvaluatorSidecar]]:
    if combined_path.exists():
        pairs = []
        for row in read_jsonl(combined_path):
            public_raw = row.get("public_case", row.get("public", row))
            sidecar_raw = row.get("evaluator_sidecar", row.get("gold_sidecar", row.get("gold")))
            if sidecar_raw is None:
                raise ValueError(f"{combined_path}: combined row lacks evaluator_sidecar")
            pairs.append((_public_case(public_raw), _sidecar(sidecar_raw)))
    else:
        if not public_path.exists() or not gold_path.exists():
            raise FileNotFoundError(
                f"need {combined_path} or both {public_path} and {gold_path}"
            )
        sidecars = {str(row["case_id"]): _sidecar(row) for row in read_jsonl(gold_path)}
        pairs = []
        for row in read_jsonl(public_path):
            public = _public_case(row)
            if public.case_id not in sidecars:
                raise KeyError(f"missing sidecar for {public.case_id}")
            pairs.append((public, sidecars[public.case_id]))
    for public, sidecar in pairs:
        if public.case_id != sidecar.case_id or public.query != sidecar.query:
            raise ValueError(f"public/sidecar mismatch: {public.case_id}")
    return pairs


def gold_fragment(source: PublicSource, sidecar: EvaluatorSidecar) -> Fragment:
    return fragment_from_formal(
        sidecar.formal_by_source.get(source.source_id, {}),
        source_id=source.source_id,
        source_text=source.rendered_text,
        validated=True,
        validation_note="hidden_oracle_after_execution",
    )


def execution_order(public: PublicCase, sidecar: EvaluatorSidecar) -> tuple[str, ...]:
    source_ids = set(public.source_map)
    result: list[str] = []
    for source_id in (*sidecar.recommended_order, *public.source_order):
        if source_id in source_ids and source_id not in result:
            result.append(source_id)
    result.extend(sorted(source_ids - set(result)))
    return tuple(result)


def replay_case(
    public: PublicCase,
    sidecar: EvaluatorSidecar,
    *,
    mode: str,
    parser: LocalNoteParser | None,
) -> dict[str, Any]:
    if mode not in {"oracle", "local"}:
        raise ValueError(mode)
    kb = CommittedKB()
    previous_closure: frozenset[Atom] = frozenset()
    events: list[dict[str, Any]] = []
    stats = CallStats()
    logical_stats = CallStats()
    unique_recorded: dict[str, CallStats] = {}
    exact_count = valid_count = note_count = note_exact_count = 0
    for sequence, source_id in enumerate(execution_order(public, sidecar), 1):
        source = public.source_map[source_id]
        receipt = ExecutionReceipt(source_id, sha256_text(source.rendered_text), sequence)
        gold = gold_fragment(source, sidecar)
        if mode == "oracle":
            fragment = gold
            parse_valid = True
            parse_exact = True
            parse_event: dict[str, Any] = {
                "decision": "commit" if not fragment.empty else "abstain",
                "valid": True,
                "cache_hit": False,
                "stats": CallStats().as_dict(),
            }
        else:
            assert parser is not None
            parsed = parser.parse(source_id=source_id, rendered_text=source.rendered_text)
            stats = stats + parsed.stats
            logical_stats = logical_stats + parsed.recorded_stats
            unique_recorded.setdefault(parsed.cache_key, parsed.recorded_stats)
            parse_valid = parsed.valid
            fragment = parsed.fragment
            parse_exact = bool(
                parse_valid
                and fragment is not None
                and fragment.semantic_signature == gold.semantic_signature
            )
            parse_event = parsed.as_dict(include_raw=False)
            valid_count += int(parse_valid)
            exact_count += int(parse_exact)
            note_count += int(parsed.note_found)
            note_exact_count += int(parsed.note_found and parse_exact)

        committed = False
        commit_error = None
        if fragment is not None and parse_valid:
            try:
                kb = kb.commit(receipt, fragment)
                committed = True
            except ValueError as exc:
                commit_error = str(exc)
        lfp = least_fixed_point(kb)
        delta = sorted(lfp.closure - previous_closure)
        previous_closure = lfp.closure
        events.append({
            "sequence": sequence,
            "source_id": source_id,
            "executed": True,
            "committed": committed,
            "commit_error": commit_error,
            "gold_nonempty": not gold.empty,
            "parse_valid": parse_valid,
            "parse_exact": parse_exact,
            "parse": parse_event,
            "delta_closure": [atom.as_dict() for atom in delta],
            "query_entailed_after_step": lfp.entails(public.query),
        })

    final_lfp = least_fixed_point(kb)
    proof = final_lfp.proof(public.query)
    predicted = "Entailed" if final_lfp.entails(public.query) else "PR-Unknown"
    proof_valid = (
        verify_proof(kb, proof)
        and source_set_sufficient(kb, public.query, proof.source_ids)
        if proof is not None
        else predicted == "PR-Unknown"
    )
    return {
        "case_id": public.case_id,
        "carrier_size": public.carrier_size,
        "condition": public.condition,
        "mode": mode,
        "public_input_sha256": public.raw_public_sha256,
        "query": public.query.as_dict(),
        "expected_label": sidecar.expected_label,
        "predicted_label": predicted,
        "label_exact": predicted == sidecar.expected_label,
        "unknown_false_entailment": sidecar.expected_label == "PR-Unknown" and predicted == "Entailed",
        "proof_valid": proof_valid,
        "proof": proof.as_dict() if proof else None,
        "committed_source_ids": list(kb.source_ids),
        "closure_size": len(final_lfp.closure),
        "lfp_iterations": final_lfp.iterations,
        "source_count": len(public.sources),
        "parse_valid_count": valid_count if mode == "local" else len(public.sources),
        "parse_exact_count": exact_count if mode == "local" else len(public.sources),
        "controlled_note_count": note_count if mode == "local" else None,
        "controlled_note_exact_count": note_exact_count if mode == "local" else None,
        "new_model_usage": stats.as_dict(),
        "logical_uncached_model_usage": logical_stats.as_dict(),
        "unique_cached_inference_usage": sum_stats(unique_recorded.values()).as_dict(),
        "events": events,
    }


class BaselineCache:
    def __init__(self, path: Path, refresh: bool) -> None:
        self.path = path
        self.rows: dict[str, dict[str, Any]] = {}
        if path.exists() and not refresh:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row["cache_key"]] = row

    def get(self, key: str) -> dict[str, Any] | None:
        return self.rows.get(key)

    def put(self, key: str, row: dict[str, Any]) -> None:
        self.rows[key] = {"cache_key": key, **row}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            "".join(
                json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                for item in sorted(self.rows.values(), key=lambda value: value["cache_key"])
            ),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def _baseline_gold_kb(
    public: PublicCase,
    sidecar: EvaluatorSidecar,
    source_ids: Iterable[str],
) -> CommittedKB:
    kb = CommittedKB()
    for sequence, source_id in enumerate(sorted(set(source_ids)), 1):
        source = public.source_map[source_id]
        fragment = gold_fragment(source, sidecar)
        kb = kb.commit(
            ExecutionReceipt(source_id, sha256_text(source.rendered_text), sequence),
            fragment,
        )
    return kb


def run_whole_context_baseline(
    public: PublicCase,
    sidecar: EvaluatorSidecar,
    *,
    policy: str,
    client: OllamaClient,
    cache: BaselineCache,
    max_chars: int,
) -> dict[str, Any]:
    system_path = ROOT / "prompts" / f"{policy}_system_v1.txt"
    schema_path = ROOT / "prompts" / "baseline_schema_v1.json"
    system = system_path.read_text(encoding="utf-8")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    sources = [
        {"source_id": source.source_id, "heading": source.heading, "text": source.rendered_text}
        for source in public.sources
    ]
    user_payload = {
        "query_text": public.query_text,
        "query_atom": public.query.as_dict(),
        "sources": sources,
    }
    user = json.dumps(user_payload, ensure_ascii=False, sort_keys=True)
    common = {
        "case_id": public.case_id,
        "carrier_size": public.carrier_size,
        "condition": public.condition,
        "policy": policy,
        "expected_label": sidecar.expected_label,
        "public_input_sha256": public.raw_public_sha256,
        "visible_chars": len(user),
    }
    if len(user) > max_chars:
        return {
            **common,
            "skipped": True,
            "skip_reason": f"visible context {len(user)} > cap {max_chars}",
            "new_model_usage": CallStats().as_dict(),
        }
    key = sha256_text(canonical_json({
        "model": client.model,
        "model_digest": client.model_digest,
        "temperature": client.temperature,
        "num_ctx": client.num_ctx,
        "policy": policy,
        "system_hash": sha256_text(system),
        "schema_hash": sha256_text(canonical_json(schema)),
        "user_hash": sha256_text(user),
    }))
    cached = cache.get(key)
    stats = CallStats()
    if cached is None:
        try:
            raw, raw_response, stats = client.chat_json(system=system, user=user, schema=schema)
            error = None
        except (RuntimeError, ValueError) as exc:
            raw, raw_response, error = None, None, str(exc)
        cache.put(key, {
            "raw": raw,
            "raw_response": raw_response,
            "error": error,
            "original_usage": stats.as_dict(),
        })
        cache_hit = False
        recorded_stats = stats
    else:
        raw, error = cached.get("raw"), cached.get("error")
        cache_hit = True
        recorded_raw = cached.get("original_usage") or {}
        recorded_stats = CallStats(
            int(recorded_raw.get("calls", 0)),
            int(recorded_raw.get("prompt_tokens", 0)),
            int(recorded_raw.get("completion_tokens", 0)),
            float(recorded_raw.get("latency_seconds", 0.0)),
        )

    answer_schema_valid = False
    citation_contract_valid = False
    valid = False
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
        except (ValueError, TypeError) as exc:
            error = str(exc)

    if answer_schema_valid:
        if len(claimed_sources) != len(set(claimed_sources)):
            error = "duplicate proof source"
        elif not set(claimed_sources) <= set(public.source_map):
            error = "proof cites a hidden/nonexistent source"
        elif label == "PR-Unknown" and claimed_sources:
            error = "PR-Unknown must not claim a proof"
        else:
            citation_contract_valid = True
            valid = True

    if valid and label == "Entailed":
        proof_kb = _baseline_gold_kb(public, sidecar, claimed_sources)
        proof_source_valid = least_fixed_point(proof_kb).entails(public.query)
    elif valid and label == "PR-Unknown":
        proof_source_valid = not claimed_sources
    else:
        proof_source_valid = False
    return {
        **common,
        "skipped": False,
        "cache_hit": cache_hit,
        "cache_key": key,
        "valid": valid,
        "answer_schema_valid": answer_schema_valid,
        "citation_contract_valid": citation_contract_valid,
        "error": error,
        "predicted_label": label,
        "answer_label_exact": answer_schema_valid and label == sidecar.expected_label,
        "label_exact": valid and label == sidecar.expected_label,
        "unknown_false_entailment": sidecar.expected_label == "PR-Unknown" and label == "Entailed",
        "proof_source_ids": claimed_sources,
        "proof_source_valid": proof_source_valid,
        "rationale": rationale,
        "new_model_usage": stats.as_dict(),
        "recorded_inference_usage": recorded_stats.as_dict(),
    }


def _aggregate_replays(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"cases": 0}
    sources = sum(int(row["source_count"]) for row in rows)
    valid = sum(int(row["parse_valid_count"]) for row in rows)
    exact = sum(int(row["parse_exact_count"]) for row in rows)
    notes = sum(int(row.get("controlled_note_count") or 0) for row in rows)
    note_exact = sum(int(row.get("controlled_note_exact_count") or 0) for row in rows)
    usage = CallStats()
    logical_usage = CallStats()
    unique_rows: dict[str, CallStats] = {}
    for row in rows:
        raw = row["new_model_usage"]
        usage += CallStats(
            int(raw["calls"]), int(raw["prompt_tokens"]), int(raw["completion_tokens"]),
            float(raw["latency_seconds"]),
        )
        for event in row.get("events", []):
            parse = event.get("parse", {})
            recorded = parse.get("recorded_inference_stats", {})
            recorded_stats = CallStats(
                int(recorded.get("calls", 0)), int(recorded.get("prompt_tokens", 0)),
                int(recorded.get("completion_tokens", 0)), float(recorded.get("latency_seconds", 0.0)),
            )
            logical_usage += recorded_stats
            key = parse.get("cache_key")
            if key:
                unique_rows.setdefault(str(key), recorded_stats)
    return {
        "cases": len(rows),
        "label_exact": sum(bool(row["label_exact"]) for row in rows),
        "proof_valid": sum(bool(row["proof_valid"]) for row in rows),
        "unknown_false_entailments": sum(bool(row["unknown_false_entailment"]) for row in rows),
        "sources": sources,
        "parse_valid": valid,
        "parse_valid_rate": valid / sources if sources else None,
        "parse_exact": exact,
        "parse_exact_rate": exact / sources if sources else None,
        "controlled_notes": notes,
        "controlled_note_exact": note_exact,
        "controlled_note_exact_rate": note_exact / notes if notes else None,
        "new_model_usage": usage.as_dict(),
        "logical_uncached_model_usage": logical_usage.as_dict(),
        "unique_cached_inference_usage": sum_stats(unique_rows.values()).as_dict(),
    }


def _aggregate_baselines(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for policy in sorted({str(row["policy"]) for row in rows}):
        subset = [row for row in rows if row["policy"] == policy]
        evaluated = [row for row in subset if not row.get("skipped")]
        usage = CallStats()
        logical_usage = CallStats()
        unique_usage: dict[str, CallStats] = {}
        for row in evaluated:
            raw = row["new_model_usage"]
            usage += CallStats(
                int(raw["calls"]), int(raw["prompt_tokens"]), int(raw["completion_tokens"]),
                float(raw["latency_seconds"]),
            )
            recorded = row.get("recorded_inference_usage", {})
            recorded_stats = CallStats(
                int(recorded.get("calls", 0)), int(recorded.get("prompt_tokens", 0)),
                int(recorded.get("completion_tokens", 0)), float(recorded.get("latency_seconds", 0.0)),
            )
            logical_usage += recorded_stats
            if row.get("cache_key"):
                unique_usage.setdefault(str(row["cache_key"]), recorded_stats)
        output[policy] = {
            "cases": len(subset),
            "evaluated": len(evaluated),
            "skipped": len(subset) - len(evaluated),
            "valid": sum(bool(row.get("valid")) for row in evaluated),
            "answer_schema_valid": sum(bool(row.get("answer_schema_valid")) for row in evaluated),
            "citation_contract_valid": sum(bool(row.get("citation_contract_valid")) for row in evaluated),
            "answer_label_exact": sum(bool(row.get("answer_label_exact")) for row in evaluated),
            "label_exact": sum(bool(row.get("label_exact")) for row in evaluated),
            "proof_source_valid": sum(bool(row.get("proof_source_valid")) for row in evaluated),
            "unknown_false_entailments": sum(bool(row.get("unknown_false_entailment")) for row in evaluated),
            "new_model_usage": usage.as_dict(),
            "logical_uncached_model_usage": logical_usage.as_dict(),
            "unique_cached_inference_usage": sum_stats(unique_usage.values()).as_dict(),
        }
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--combined", type=Path, default=DEFAULT_COMBINED)
    parser.add_argument("--public", type=Path, default=DEFAULT_PUBLIC)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--mode", choices=("oracle", "local", "both"), default="both")
    parser.add_argument("--baselines", choices=("none", "direct", "cot", "both"), default="both")
    parser.add_argument("--sizes", default="3,5,7,9")
    parser.add_argument("--conditions", default="Productive,Decoy,Broken,Clean,Matched-DAG")
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--num-ctx", type=int, default=16_384)
    parser.add_argument("--baseline-max-chars", type=int, default=100_000)
    parser.add_argument("--refresh-cache", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sizes = {int(item) for item in args.sizes.split(",") if item.strip()}
    conditions = {item.strip().lower() for item in args.conditions.split(",") if item.strip()}
    pairs = [
        pair for pair in load_cases(
            combined_path=args.combined,
            public_path=args.public,
            gold_path=args.gold,
        )
        if pair[0].carrier_size in sizes and pair[0].condition.lower() in conditions
    ]
    if args.max_cases is not None:
        pairs = pairs[: args.max_cases]
    if not pairs:
        raise RuntimeError("no cases survived size/condition filters")

    need_model = args.mode in {"local", "both"} or args.baselines != "none"
    client = OllamaClient(
        model=args.model,
        base_url=args.ollama_url,
        timeout_seconds=args.timeout_seconds,
        num_ctx=args.num_ctx,
    ) if need_model else None
    local_parser = LocalNoteParser(
        cache_path=CACHE / "source_parser.jsonl",
        client=client,
        refresh_cache=args.refresh_cache,
    ) if args.mode in {"local", "both"} and client else None

    oracle_rows: list[dict[str, Any]] = []
    local_rows: list[dict[str, Any]] = []
    if args.mode in {"oracle", "both"}:
        for public, sidecar in pairs:
            oracle_rows.append(replay_case(public, sidecar, mode="oracle", parser=None))
    if args.mode in {"local", "both"}:
        for public, sidecar in pairs:
            local_rows.append(replay_case(public, sidecar, mode="local", parser=local_parser))

    baseline_rows: list[dict[str, Any]] = []
    baseline_cache: BaselineCache | None = None
    if args.baselines != "none":
        assert client is not None
        policies = ("direct", "cot") if args.baselines == "both" else (args.baselines,)
        cache = BaselineCache(CACHE / "whole_context_baselines.jsonl", args.refresh_cache)
        baseline_cache = cache
        for public, sidecar in pairs:
            for policy in policies:
                baseline_rows.append(run_whole_context_baseline(
                    public,
                    sidecar,
                    policy=policy,
                    client=client,
                    cache=cache,
                    max_chars=args.baseline_max_chars,
                ))

    oracle_summary = _aggregate_replays(oracle_rows)
    local_summary = _aggregate_replays(local_rows)
    baseline_summary = _aggregate_baselines(baseline_rows)
    selected_baseline_keys = {
        str(row["cache_key"]) for row in baseline_rows if row.get("cache_key")
    }
    excluded_baseline_rows = (
        [row for key, row in baseline_cache.rows.items() if key not in selected_baseline_keys]
        if baseline_cache is not None else []
    )
    excluded_baseline_usage = sum_stats(
        CallStats(
            int((row.get("original_usage") or {}).get("calls", 0)),
            int((row.get("original_usage") or {}).get("prompt_tokens", 0)),
            int((row.get("original_usage") or {}).get("completion_tokens", 0)),
            float((row.get("original_usage") or {}).get("latency_seconds", 0.0)),
        )
        for row in excluded_baseline_rows
    )
    selected_parser_keys = {
        str(event["parse"]["cache_key"])
        for row in local_rows for event in row.get("events", [])
        if event.get("parse", {}).get("cache_key")
    }
    excluded_parser_rows = (
        [row for key, row in local_parser.rows.items() if key not in selected_parser_keys]
        if local_parser is not None else []
    )
    excluded_parser_usage = sum_stats(
        CallStats(
            int((row.get("stats") or {}).get("calls", 0)),
            int((row.get("stats") or {}).get("prompt_tokens", 0)),
            int((row.get("stats") or {}).get("completion_tokens", 0)),
            float((row.get("stats") or {}).get("latency_seconds", 0.0)),
        )
        for row in excluded_parser_rows
    )
    gates = {
        "oracle_labels_all_exact": not oracle_rows or oracle_summary["label_exact"] == len(oracle_rows),
        "oracle_proofs_all_valid": not oracle_rows or oracle_summary["proof_valid"] == len(oracle_rows),
        "oracle_unknown_false_entailment_zero": oracle_summary.get("unknown_false_entailments", 0) == 0,
        "local_parse_valid_rate_ge_0_95": (
            not local_rows or float(local_summary.get("parse_valid_rate") or 0) >= 0.95
        ),
        "local_parse_exact_rate_ge_0_95": (
            not local_rows or float(local_summary.get("parse_exact_rate") or 0) >= 0.95
        ),
        "local_unknown_false_entailment_zero": local_summary.get("unknown_false_entailments", 0) == 0,
        "model_digest_matches_frozen_qwen": (
            client is None or client.model != DEFAULT_MODEL or client.model_digest == EXPECTED_MODEL_DIGEST
        ),
    }
    summary = {
        "schema_version": 1,
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(gates.values()) else "FAIL",
        "claim_boundary": (
            "Engineering/oracle/local-parser/whole-context smoke only. No PUCT/MCGS "
            "advantage, SCC causality, natural-distribution, or paper-level result is established."
        ),
        "public_gold_separation": (
            "Policies receive only PublicCase rendered text and formal query. evaluator_sidecar "
            "is consulted only after an executed source (oracle/parser scoring) or after a "
            "baseline answer (proof-source verification)."
        ),
        "local_parser_access": (
            "Marker-isolated parser smoke: code extracts exactly one CONTROLLED-LFP-NOTE and "
            "sends only that note to Qwen; clean/original German windows abstain without a call. "
            "This is not raw-window note discovery. Direct/CoT receive the full rendered windows."
        ),
        "filters": {"sizes": sorted(sizes), "conditions": sorted(conditions)},
        "case_count": len(pairs),
        "input_cases": {
            "path": str(args.combined if args.combined.exists() else args.public),
            "sha256": sha256_file(args.combined if args.combined.exists() else args.public),
        },
        "model": ({
            "name": client.model,
            "digest": client.model_digest,
            "temperature": client.temperature,
            "num_ctx": client.num_ctx,
            "expected_digest": EXPECTED_MODEL_DIGEST if client.model == DEFAULT_MODEL else None,
        } if client else None),
        "oracle": oracle_summary,
        "local_parser": local_summary,
        "whole_context_baselines": baseline_summary,
        "cache_audit": {
            "source_parser": {
                "selected_rows": len(selected_parser_keys),
                "excluded_preserved_rows": len(excluded_parser_rows),
                "excluded_preserved_usage": excluded_parser_usage.as_dict(),
            },
            "whole_context_baselines": {
                "selected_rows": len(selected_baseline_keys),
                "excluded_preserved_rows": len(excluded_baseline_rows),
                "excluded_preserved_usage": excluded_baseline_usage.as_dict(),
                "note": (
                    "Excluded rows are preserved audit records from incompatible/earlier cache keys; "
                    "they do not contribute to current metrics."
                ),
            },
        },
        "gates": gates,
        "artifacts": {
            "oracle_trials": "phase2_oracle_trials.jsonl" if oracle_rows else None,
            "local_trials": "phase2_local_parser_trials.jsonl" if local_rows else None,
            "baseline_trials": "phase3_llm_baselines.jsonl" if baseline_rows else None,
        },
    }
    if oracle_rows:
        write_jsonl(RESULTS / "phase2_oracle_trials.jsonl", oracle_rows)
    if local_rows:
        write_jsonl(RESULTS / "phase2_local_parser_trials.jsonl", local_rows)
    if baseline_rows:
        write_jsonl(RESULTS / "phase3_llm_baselines.jsonl", baseline_rows)
    write_json(RESULTS / "phase2_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())

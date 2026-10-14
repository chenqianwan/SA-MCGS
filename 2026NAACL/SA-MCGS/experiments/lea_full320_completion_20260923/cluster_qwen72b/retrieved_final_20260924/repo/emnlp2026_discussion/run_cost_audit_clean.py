#!/usr/bin/env python3
"""Low-concurrency cost audit runner for the EMNLP discussion.

The runner is intentionally conservative:
- case-level concurrency is always 1;
- SA-MCGS internal rollout concurrency defaults to 1;
- every method/case writes an independent JSON result;
- every LLM call writes a JSONL usage record immediately.

Re-running the same command with the same output directory resumes from the
completed method/case JSON files.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import csv
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
import traceback
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "cross_domain"))

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from src.llm.openai_client import OpenAIClient
from src.models.graph import SCCInfo
from src.modules.alphago_mcgs import AlphaGoMCGS
from src.modules.tarjan import TarjanSCCDetector

from experiments.cross_domain import run_cross_domain_battle as battle


DISCUSSION_DIR = REPO_ROOT / "emnlp2026_discussion"
SA_WORK_DIR = REPO_ROOT / "2026NAACL" / "SA-MCGS"
DEFAULT_CASE_CSV = DISCUSSION_DIR / "case_composition.csv"
DEFAULT_RUNS_DIR = SA_WORK_DIR / "experiments" / "cost_audit_runs"
MODEL_IDS = {
    "gpt-4o": "gpt-4o",
    "deepseek-v3": "deepseek-chat",
    "qwen2.5-72b": "qwen2.5-72b-instruct",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-2.5-flash": "gemini-2.5-flash",
}
STABLE_CASE_IDENTITY_VERSION = "stable_case_identity_v1"
DATASET_REVISION_VERSION = "graph_content_revision_v1"
_DATASET_REVISION_CACHE_KEY = "_stable_dataset_revision_v1"


class StableCaseIdentityError(RuntimeError):
    """Raised when a planned case cannot be reproduced exactly."""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def safe_token(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("_")


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=json_default,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _edge_identity(edge: Any) -> dict[str, Any]:
    return {
        "source": str(edge.source),
        "target": str(edge.target),
        "dependency_type": _enum_value(edge.dependency_type),
        "weight": format(float(getattr(edge, "weight", 1.0)), ".17g"),
    }


def _sorted_edge_identities(edges: list[Any]) -> list[dict[str, Any]]:
    return sorted(
        (_edge_identity(edge) for edge in edges),
        key=lambda item: (
            item["source"],
            item["target"],
            item["dependency_type"],
            item["weight"],
        ),
    )


def graph_dataset_revision(graph: Any, domain: str) -> str:
    """Return a content-derived dataset revision, cached on the loaded graph."""
    metadata = graph.metadata if isinstance(getattr(graph, "metadata", None), dict) else {}
    cached = metadata.get(_DATASET_REVISION_CACHE_KEY)
    if cached:
        return str(cached)

    clauses = []
    for clause_id in sorted(graph.clauses):
        clause = graph.clauses[clause_id]
        clauses.append(
            {
                "id": str(clause_id),
                "title": _normalize_text(getattr(clause, "title", "")),
                "content": _normalize_text(getattr(clause, "content", "")),
                "section": _normalize_text(getattr(clause, "section", "")),
                "clause_type": _enum_value(getattr(clause, "clause_type", "")),
            }
        )
    payload = {
        "version": DATASET_REVISION_VERSION,
        "domain": str(domain),
        "clauses": clauses,
        "typed_edges": _sorted_edge_identities(list(graph.edges)),
    }
    revision = _canonical_hash(payload)
    metadata[_DATASET_REVISION_CACHE_KEY] = revision
    graph.metadata = metadata
    return revision


def _source_result_path(raw_path: Any) -> Path:
    raw = str(raw_path or "").strip()
    if not raw:
        raise StableCaseIdentityError("Case is missing source_result_file")
    direct = Path(raw)
    repo_mirror = REPO_ROOT / "experiments" / "cross_domain" / "results" / direct.name
    candidates: list[Path] = []
    if direct.exists() and direct.resolve().is_relative_to(REPO_ROOT.resolve()):
        candidates.append(direct)
    candidates.extend([repo_mirror, direct])
    candidates = list(dict.fromkeys(candidates))
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise StableCaseIdentityError(
        "Source result file is unavailable; cannot recover the stable SCC identity: "
        + ", ".join(str(path) for path in candidates)
    )


def source_result_path(raw_path: Any) -> Path:
    return _source_result_path(raw_path)


def _source_sa_result(
    case: dict[str, Any],
    source_path: Path | None = None,
) -> dict[str, Any]:
    source_path = source_path or _source_result_path(case.get("source_result_file"))
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else [payload]
    candidates = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("method") == "sa-mcgs"
        and row.get("domain") == case.get("domain")
    ]
    model_matches = [row for row in candidates if row.get("model") == case.get("model")]
    if len(model_matches) == 1:
        return model_matches[0]
    if len(model_matches) > 1:
        raise StableCaseIdentityError(
            f"Expected exactly one source SA-MCGS record for {case.get('case_id')}; "
            f"found {len(model_matches)} model-matched rows in {source_path}"
        )

    # Cost-audit models such as Flash/Qwen may intentionally reuse the canonical
    # graph case selected by another model. Accept this only when every source
    # SA row agrees on the complete node/injection identity.
    signatures: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        signature = _canonical_hash(
            {
                "ordered_clause_ids": list(row.get("scc_clause_ids") or []),
                "injection": injection_identity(
                    row,
                    requested_template=str(case.get("template") or ""),
                ),
            }
        )
        signatures[signature].append(row)
    if len(signatures) != 1 or not candidates:
        raise StableCaseIdentityError(
            f"No model-matched source row and source identities are not unique for "
            f"{case.get('case_id')}: {len(candidates)} rows, {len(signatures)} identities "
            f"in {source_path}"
        )
    return sorted(candidates, key=lambda row: str(row.get("model") or ""))[0]


def injection_identity(
    payload: dict[str, Any],
    *,
    requested_template: str,
    injected_id: str | None = None,
) -> dict[str, Any]:
    """Extract only deterministic injection fields used by stable case identity."""
    root = payload.get("injected_node") or injected_id
    return {
        "seed": int(payload.get("inject_seed") or 42),
        "profile": str(payload.get("inject_profile") or "memory_stress"),
        "profile_version": payload.get("inject_profile_version"),
        "requested_conflict_family": str(requested_template),
        "conflict_family": payload.get("injected_conflict_family"),
        "conflict_severity": payload.get("injected_conflict_severity"),
        "conflict_template": payload.get("injected_conflict_template"),
        "root_node": root,
        "witness_node": payload.get("injected_witness_node"),
        "witness_distance": payload.get("injected_witness_distance"),
        "bridge_node": payload.get("injected_bridge_node"),
        "bridge_distance": payload.get("injected_bridge_distance"),
        "risk_nodes": list(payload.get("injected_risk_nodes") or []),
        "evidence_nodes": list(payload.get("injected_evidence_nodes") or []),
        "affected_nodes": list(payload.get("injected_affected_nodes") or []),
    }


def _validate_injection_identity(identity: dict[str, Any], case_id: str) -> None:
    required = ("profile_version", "conflict_family", "conflict_severity", "conflict_template", "root_node")
    missing = [key for key in required if identity.get(key) in (None, "")]
    if not identity.get("risk_nodes"):
        missing.append("risk_nodes")
    if missing:
        raise StableCaseIdentityError(
            f"Stable injection identity for {case_id} is incomplete: {sorted(set(missing))}"
        )


def hydrate_case_from_source(case: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a legacy numeric-ID case row with its immutable source identity."""
    original_source = str(case.get("source_result_file") or "")
    already_hydrated = bool(
        case.get("planned_scc_clause_ids")
        and case.get("planned_injection_identity")
    )
    if already_hydrated and not original_source:
        return case
    source_path = _source_result_path(original_source)
    source_file_sha256 = _file_sha256(source_path)
    stored_file_sha256 = case.get("source_result_sha256")
    if stored_file_sha256 and stored_file_sha256 != source_file_sha256:
        raise StableCaseIdentityError(
            f"Source result file changed for {case.get('case_id')}: "
            f"{stored_file_sha256} != {source_file_sha256}"
        )

    source = _source_sa_result(case, source_path)
    source_record_sha256 = _canonical_hash(source)
    stored_record_sha256 = case.get("source_sa_record_sha256")
    if stored_record_sha256 and stored_record_sha256 != source_record_sha256:
        raise StableCaseIdentityError(
            f"Source SA-MCGS row changed for {case.get('case_id')}: "
            f"{stored_record_sha256} != {source_record_sha256}"
        )

    if original_source and original_source != str(source_path):
        case.setdefault("source_result_file_original", original_source)
    case["source_result_file"] = str(source_path)
    case["source_result_sha256"] = source_file_sha256
    case["source_sa_record_sha256"] = source_record_sha256
    if source_path.is_relative_to(REPO_ROOT.resolve()):
        case["source_result_repo_relpath"] = str(
            source_path.relative_to(REPO_ROOT.resolve())
        )

    if already_hydrated:
        return case
    clause_ids = list(source.get("scc_clause_ids") or [])
    if not clause_ids or len(clause_ids) != len(set(clause_ids)):
        raise StableCaseIdentityError(
            f"Source result for {case.get('case_id')} has missing or duplicate scc_clause_ids"
        )
    expected_injection = injection_identity(
        source,
        requested_template=str(case.get("template") or ""),
    )
    _validate_injection_identity(expected_injection, str(case.get("case_id")))
    case["planned_scc_clause_ids"] = clause_ids
    case["planned_injection_identity"] = expected_injection
    case["source_scc_id"] = source.get("scc_id")
    case["source_scc_size"] = source.get("scc_size")
    return case


def build_case_identity(
    graph: Any,
    *,
    domain: str,
    ordered_clause_ids: list[str],
    injection: dict[str, Any],
) -> dict[str, Any]:
    """Build the stable identity from graph content, structure, and injection."""
    clause_ids = [str(clause_id) for clause_id in ordered_clause_ids]
    if not clause_ids or len(clause_ids) != len(set(clause_ids)):
        raise StableCaseIdentityError("ordered_clause_ids must be non-empty and unique")
    missing = [clause_id for clause_id in clause_ids if clause_id not in graph.clauses]
    if missing:
        raise StableCaseIdentityError(f"Stable SCC contains missing graph nodes: {missing[:5]}")

    clause_set = set(clause_ids)
    internal_edges = [
        edge
        for edge in graph.edges
        if edge.source in clause_set and edge.target in clause_set
    ]
    text_hashes = []
    for clause_id in clause_ids:
        clause = graph.clauses[clause_id]
        normalized_text = {
            "title": _normalize_text(getattr(clause, "title", "")),
            "content": _normalize_text(getattr(clause, "content", "")),
            "section": _normalize_text(getattr(clause, "section", "")),
            "clause_type": _enum_value(getattr(clause, "clause_type", "")),
        }
        text_hashes.append({"id": clause_id, "text_sha256": _canonical_hash(normalized_text)})

    identity_payload = {
        "version": STABLE_CASE_IDENTITY_VERSION,
        "domain": str(domain),
        "dataset_revision": graph_dataset_revision(graph, domain),
        "ordered_clause_ids": clause_ids,
        "typed_internal_edges": _sorted_edge_identities(internal_edges),
        "normalized_clause_text_hashes": text_hashes,
        "injection": copy.deepcopy(injection),
    }
    fingerprint = _canonical_hash(identity_payload)
    return {
        **identity_payload,
        "fingerprint": fingerprint,
        "case_uid": f"scid-v1-{fingerprint.removeprefix('sha256:')}",
    }


def _identity_mismatch_message(
    case: dict[str, Any],
    planned: dict[str, Any],
    actual: dict[str, Any],
) -> str:
    differences = []
    for key in (
        "dataset_revision",
        "ordered_clause_ids",
        "typed_internal_edges",
        "normalized_clause_text_hashes",
        "injection",
    ):
        if planned.get(key) != actual.get(key):
            differences.append(key)
    return (
        f"Stable case identity mismatch for {case.get('case_id')}: "
        f"planned={planned.get('fingerprint')} actual={actual.get('fingerprint')}; "
        f"different fields={differences or ['fingerprint']}"
    )


def validate_case_plan(plan: list[dict[str, Any]], graphs: dict[str, Any]) -> dict[str, Any]:
    """Hydrate and validate every case before any API call is allowed."""
    for case in plan:
        hydrate_case_from_source(case)
        domain = str(case.get("domain"))
        if domain not in graphs:
            raise StableCaseIdentityError(f"No loaded graph for domain={domain}")
        clause_ids = list(case["planned_scc_clause_ids"])
        if int(case.get("scc_size") or -1) != len(clause_ids):
            raise StableCaseIdentityError(
                f"Legacy scc_size disagrees with stable node list for {case.get('case_id')}: "
                f"{case.get('scc_size')} != {len(clause_ids)}"
            )
        planned_injection = case["planned_injection_identity"]
        if planned_injection.get("requested_conflict_family") != case.get("template"):
            raise StableCaseIdentityError(
                f"Injection template mismatch for {case.get('case_id')}: "
                f"{planned_injection.get('requested_conflict_family')} != {case.get('template')}"
            )
        if (
            planned_injection.get("seed") != 42
            or planned_injection.get("profile") != "memory_stress"
            or planned_injection.get("conflict_severity") != "critical"
        ):
            raise StableCaseIdentityError(
                f"Unexpected injection protocol for {case.get('case_id')}: {planned_injection}"
            )
        identity_nodes = {
            planned_injection.get("root_node"),
            planned_injection.get("witness_node"),
            planned_injection.get("bridge_node"),
            *planned_injection.get("risk_nodes", []),
            *planned_injection.get("evidence_nodes", []),
            *planned_injection.get("affected_nodes", []),
        }
        unknown_identity_nodes = sorted(
            node_id for node_id in identity_nodes if node_id and node_id not in set(clause_ids)
        )
        if unknown_identity_nodes:
            raise StableCaseIdentityError(
                f"Injection identity references nodes outside the planned SCC for "
                f"{case.get('case_id')}: {unknown_identity_nodes}"
            )
        current = build_case_identity(
            graphs[domain],
            domain=domain,
            ordered_clause_ids=clause_ids,
            injection=planned_injection,
        )
        stored = case.get("planned_case_identity")
        if stored and stored.get("fingerprint") != current["fingerprint"]:
            raise StableCaseIdentityError(_identity_mismatch_message(case, stored, current))
        stored_uid = case.get("case_uid")
        if stored_uid and stored_uid != current["case_uid"]:
            raise StableCaseIdentityError(
                f"Stored case_uid mismatch for {case.get('case_id')}: "
                f"{stored_uid} != {current['case_uid']}"
            )
        case["planned_case_identity"] = current
        case["case_uid"] = current["case_uid"]
        case["planned_scc_fingerprint"] = current["fingerprint"]

    return {
        "identity_version": STABLE_CASE_IDENTITY_VERSION,
        "validated_cases": len(plan),
        "case_uids": [case["case_uid"] for case in plan],
    }


def persist_case_plan(output_dir: Path, plan: list[dict[str, Any]]) -> None:
    """Persist the upgraded manifest without flattening its identity records."""
    atomic_write_json(output_dir / "case_plan.json", plan)
    if not plan:
        return
    fieldnames = list(dict.fromkeys(key for case in plan for key in case))
    with (output_dir / "case_plan.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for case in plan:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in case.items()
                }
            )


def json_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    tmp.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=json_default) + "\n")


def usage_summary(call_records: list[dict[str, Any]]) -> dict[str, Any]:
    ok_records = [r for r in call_records if r.get("ok")]
    prompt = sum(int((r.get("usage") or {}).get("prompt_tokens", 0)) for r in ok_records)
    completion = sum(int((r.get("usage") or {}).get("completion_tokens", 0)) for r in ok_records)
    total = sum(int((r.get("usage") or {}).get("total_tokens", 0)) for r in ok_records)
    runtime = sum(float(r.get("runtime_sec") or 0.0) for r in call_records)
    return {
        "recorded_api_calls": len(call_records),
        "successful_api_calls": len(ok_records),
        "failed_api_calls": len(call_records) - len(ok_records),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "api_runtime_sec_sum": runtime,
    }


class LoggingOpenAIClient(OpenAIClient):
    """OpenAI client that records every actual API call before returning."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        call_log_path: Path,
        context: dict[str, Any],
    ):
        super().__init__(config)
        self.call_log_path = call_log_path
        self.context = dict(context)
        self.call_records: list[dict[str, Any]] = []
        self._call_index = 0

    async def call(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        response_format: dict | None = None,
    ):
        self._call_index += 1
        record = {
            **self.context,
            "call_index": self._call_index,
            "started_at": now_iso(),
            "prompt_chars": len(prompt or ""),
            "system_prompt_chars": len(system_prompt or ""),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format,
            "ok": False,
        }
        t0 = time.time()
        try:
            response = await super().call(
                prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
                response_format=response_format,
            )
            record.update(
                {
                    "ok": True,
                    "ended_at": now_iso(),
                    "runtime_sec": time.time() - t0,
                    "returned_model": response.model,
                    "usage": dict(response.usage or {}),
                }
            )
            return response
        except Exception as exc:
            record.update(
                {
                    "ok": False,
                    "ended_at": now_iso(),
                    "runtime_sec": time.time() - t0,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            raise
        finally:
            self.call_records.append(record)
            append_jsonl(self.call_log_path, record)


def build_or_load_case_plan(args: argparse.Namespace, output_dir: Path) -> list[dict[str, Any]]:
    plan_path = output_dir / "case_plan.json"
    if plan_path.exists() and not args.rebuild_plan:
        return json.loads(plan_path.read_text(encoding="utf-8"))

    indexed_rows = list(enumerate(csv.DictReader(args.case_csv.open(encoding="utf-8")), 1))
    rows = [(order, row) for order, row in indexed_rows if row.get("model") == args.model]
    if not rows:
        raise RuntimeError(f"No rows found for model={args.model} in {args.case_csv}")

    if args.use_all_case_rows:
        ordered = rows
    else:
        chosen: dict[tuple[str, int], tuple[int, dict[str, Any]]] = {}
        for canonical_order, row in rows:
            key = (row["domain"], int(row["scc_size"]))
            current = chosen.get(key)
            if current is None:
                chosen[key] = (canonical_order, row)
                continue
            if row.get("template") == args.template_preference:
                chosen[key] = (canonical_order, row)

        ordered = sorted(
            chosen.values(),
            key=lambda item: (
                -int(item[1]["scc_size"]),
                item[1]["domain"],
                item[1]["scc_id"],
                item[1]["template"],
            ),
        )
    plan: list[dict[str, Any]] = []
    for canonical_order, row in ordered:
        case_id = safe_token(
            f"{canonical_order:03d}_{row['model']}_{row['domain']}{row['scc_size']}_"
            f"{row['scc_id']}_{row['template']}"
        )
        plan.append(
            {
                "case_order": canonical_order,
                "case_id": case_id,
                "canonical_case_order": canonical_order,
                "canonical_case_id": case_id,
                "model": row["model"],
                "domain": row["domain"],
                "scc_id": row["scc_id"],
                "scc_size": int(row["scc_size"]),
                "template": row["template"],
                "source_result_file": row.get("result_file"),
                "old_llm_calls": int(float(row.get("llm_calls") or 0)),
                "old_time_sec": float(row.get("time") or 0.0),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(plan_path, plan)
    with (output_dir / "case_plan.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(plan[0].keys()))
        writer.writeheader()
        writer.writerows(plan)
    return plan


def load_graphs(plan: list[dict[str, Any]]) -> dict[str, Any]:
    loaders = {
        "debian": battle.load_debian_graph,
        "sec_ex21": battle.load_sec_graph,
        "bgb": battle.load_bgb_graph,
        "cuad": battle.load_cuad_graph,
    }
    graphs = {}
    for domain in sorted({case["domain"] for case in plan}):
        graph = loaders[domain]()
        graphs[domain] = TarjanSCCDetector().detect(graph)
    validate_case_plan(plan, graphs)
    return graphs


def _detected_scc_for_ids(graph: Any, clause_ids: list[str], case_id: str) -> Any:
    wanted = set(clause_ids)
    matches = [scc for scc in graph.sccs if set(scc.clause_ids) == wanted]
    if len(matches) != 1:
        raise StableCaseIdentityError(
            f"Expected exactly one detected SCC matching the stable node set for {case_id}; "
            f"found {len(matches)}. Numeric Tarjan IDs are diagnostic only."
        )
    return matches[0]


def find_scc(graph: Any, case: dict[str, Any]) -> SCCInfo:
    """Resolve by the immutable ordered node list; never by a numeric Tarjan ID."""
    clause_ids = list(case.get("planned_scc_clause_ids") or [])
    if not clause_ids:
        raise StableCaseIdentityError(
            f"Case {case.get('case_id')} has no planned_scc_clause_ids; run case-plan validation first"
        )
    if len(clause_ids) != int(case.get("scc_size") or -1):
        raise StableCaseIdentityError(
            f"Stable node count mismatch for {case.get('case_id')}: "
            f"{len(clause_ids)} != legacy size {case.get('scc_size')}"
        )
    detected = _detected_scc_for_ids(graph, clause_ids, str(case.get("case_id")))
    clause_set = set(clause_ids)
    internal_edges = [
        edge
        for edge in graph.edges
        if edge.source in clause_set and edge.target in clause_set
    ]
    case["actual_tarjan_scc_id"] = str(detected.id)
    return SCCInfo(
        id=str(case.get("scc_id") or detected.id),
        clause_ids=clause_ids,
        internal_edges=internal_edges,
        size=len(clause_ids),
    )


def _identity_audit_fields(
    case: dict[str, Any],
    actual: dict[str, Any] | None = None,
) -> dict[str, Any]:
    planned = case.get("planned_case_identity")
    fields = {
        "case_identity_version": STABLE_CASE_IDENTITY_VERSION,
        "case_uid": case.get("case_uid"),
        "source_result_file": case.get("source_result_file"),
        "source_result_repo_relpath": case.get("source_result_repo_relpath"),
        "source_result_sha256": case.get("source_result_sha256"),
        "source_sa_record_sha256": case.get("source_sa_record_sha256"),
        "planned_case_identity": copy.deepcopy(planned),
        "planned_scc_clause_ids": list(case.get("planned_scc_clause_ids") or []),
        "planned_scc_fingerprint": case.get("planned_scc_fingerprint"),
        "planned_injection_identity": copy.deepcopy(case.get("planned_injection_identity")),
        "planned_scc_id_diagnostic": case.get("scc_id"),
        "actual_tarjan_scc_id_diagnostic": case.get("actual_tarjan_scc_id"),
    }
    if actual is not None:
        fields.update(
            {
                "actual_case_identity": copy.deepcopy(actual),
                "actual_scc_clause_ids": list(actual.get("ordered_clause_ids") or []),
                "actual_scc_fingerprint": actual.get("fingerprint"),
                "actual_injection_identity": copy.deepcopy(actual.get("injection")),
            }
        )
    return fields


def case_identity_audit_fields(
    case: dict[str, Any],
    actual: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _identity_audit_fields(case, actual)


def validate_result_case_identity(
    result: dict[str, Any],
    case: dict[str, Any],
    graph: Any,
) -> dict[str, Any]:
    """Reject stale/mislabelled result files before resume can reuse them."""
    planned = case.get("planned_case_identity")
    if not planned:
        raise StableCaseIdentityError(
            f"Case {case.get('case_id')} has not passed stable-identity preflight"
        )
    result_ids = list(
        result.get("actual_scc_clause_ids")
        or result.get("scc_clause_ids")
        or []
    )
    if not result_ids:
        raise StableCaseIdentityError(
            f"Existing result for {case.get('case_id')} has no actual SCC identity; "
            "rerun it instead of resuming"
        )
    actual_injection = result.get("actual_injection_identity") or injection_identity(
        result,
        requested_template=str(case.get("template") or ""),
    )
    _validate_injection_identity(actual_injection, str(case.get("case_id")))
    actual = build_case_identity(
        graph,
        domain=str(case["domain"]),
        ordered_clause_ids=result_ids,
        injection=actual_injection,
    )
    recorded_fingerprint = result.get("actual_scc_fingerprint")
    if recorded_fingerprint and recorded_fingerprint != actual["fingerprint"]:
        raise StableCaseIdentityError(
            f"Existing result fingerprint is internally inconsistent for {case.get('case_id')}: "
            f"recorded={recorded_fingerprint} reconstructed={actual['fingerprint']}"
        )
    if actual["fingerprint"] != planned["fingerprint"]:
        raise StableCaseIdentityError(_identity_mismatch_message(case, planned, actual))
    return actual


def prepare_injected_case(case: dict[str, Any], graphs: dict[str, Any]):
    domain = case["domain"]
    graph = graphs[domain]
    if not case.get("planned_case_identity"):
        raise StableCaseIdentityError(
            f"Case {case.get('case_id')} has not passed stable-identity preflight"
        )
    scc = find_scc(graph, case)
    battle.assert_original_scc_content(graph, scc, domain)
    graph_to_use, injected_id = battle.inject_defect(
        graph,
        scc,
        domain,
        seed=42,
        profile="memory_stress",
        conflict_template=case["template"],
        conflict_severity="critical",
    )
    scc = battle.reorder_scc_for_memory_stress(scc, injected_id)
    injected_scan = battle.get_injected_node(graph_to_use, scc)
    if injected_scan != injected_id:
        raise RuntimeError(f"Injected node scan mismatch: {injected_id} vs {injected_scan}")
    metadata = battle.get_injection_metadata(graph_to_use, injected_id)
    actual_injection = injection_identity(
        metadata,
        requested_template=str(case.get("template") or ""),
        injected_id=injected_id,
    )
    _validate_injection_identity(actual_injection, str(case.get("case_id")))
    actual = build_case_identity(
        graph,
        domain=str(domain),
        ordered_clause_ids=list(scc.clause_ids),
        injection=actual_injection,
    )
    planned = case["planned_case_identity"]
    if actual["fingerprint"] != planned["fingerprint"]:
        raise StableCaseIdentityError(_identity_mismatch_message(case, planned, actual))
    metadata.update(_identity_audit_fields(case, actual))
    return graph_to_use, scc, injected_id, metadata


class InjectedGroundTruth:
    def __init__(self, domain: str, injected_id: str):
        self.domain = domain
        self.injected_id = injected_id
        self.orig_gt = None
        self.orig_exact = None

    def __enter__(self):
        self.orig_gt = battle.GROUND_TRUTH.get(self.domain, {}).copy()
        self.orig_exact = set(battle._GT_EXACT_MATCH)
        battle.GROUND_TRUTH[self.domain] = {
            self.injected_id: "injected memory_stress defect (seed=42)"
        }
        battle._GT_EXACT_MATCH.add(self.injected_id.lower())

    def __exit__(self, exc_type, exc, tb):
        if self.orig_gt is not None:
            battle.GROUND_TRUTH[self.domain] = self.orig_gt
        if self.orig_exact is not None:
            battle._GT_EXACT_MATCH.clear()
            battle._GT_EXACT_MATCH.update(self.orig_exact)


def make_mcgs_config(args: argparse.Namespace) -> dict[str, Any]:
    cfg = copy.deepcopy(battle.MCGS_DEFAULT)
    mcgs = cfg["alphago_mcgs"]
    mcgs["budget"] = args.budget
    mcgs["window_size"] = args.window_size
    mcgs["concurrency"] = args.internal_concurrency
    mcgs["trace"] = True
    evidence = mcgs.setdefault("evidence", {})
    evidence["relation_first"] = True
    evidence["compression_profile"] = args.compression_profile
    evidence.update(battle.MCGS_COMPRESSION_PROFILES.get(args.compression_profile, {}))
    return cfg


def make_llm(args: argparse.Namespace, output_dir: Path, case: dict[str, Any], method: str):
    model_id = MODEL_IDS.get(args.model, args.model)
    config = {
        "provider": "openai",
        "model": model_id,
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "timeout": args.llm_timeout,
        "max_retries": args.llm_max_retries,
    }
    return LoggingOpenAIClient(
        config,
        call_log_path=output_dir / "call_logs" / "llm_calls.jsonl",
        context={
            "run_id": output_dir.name,
            "case_id": case["case_id"],
            "case_order": case["case_order"],
            "domain": case["domain"],
            "scc_id": case["scc_id"],
            "scc_size": case["scc_size"],
            "template": case["template"],
            "method": method,
            "model": args.model,
            "case_concurrency": 1,
            "internal_concurrency": args.internal_concurrency if method == "sa-mcgs" else 1,
        },
    )


def deterministic_windows(mcgs: AlphaGoMCGS, scc_ids: list[str], window_size: int) -> list[list[str]]:
    pos = {cid: i for i, cid in enumerate(scc_ids)}

    def ordered(nodes: set[str]) -> list[str]:
        return sorted(nodes, key=lambda cid: pos.get(cid, 10**9))

    windows = []
    seen: set[tuple[str, ...]] = set()
    n = len(scc_ids)
    for idx, center in enumerate(scc_ids):
        window = [center]
        neighbors = set(mcgs._adjacency.get(center, [])) | set(mcgs._reverse_adj.get(center, []))
        for cid in ordered(neighbors):
            if cid not in window:
                window.append(cid)
            if len(window) >= window_size:
                break
        offset = 1
        while len(window) < min(window_size, n):
            for candidate in (
                scc_ids[(idx + offset) % n],
                scc_ids[(idx - offset) % n],
            ):
                if candidate not in window:
                    window.append(candidate)
                if len(window) >= min(window_size, n):
                    break
            offset += 1
        key = tuple(window)
        if key not in seen:
            seen.add(key)
            windows.append(window)
    return windows


def median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def coverage_metrics(prefix: str, nodes: list[str], risk_ids: list[str], evidence_ids: list[str], affected_ids: list[str]) -> dict[str, Any]:
    node_set = set(nodes)
    valuable_ids = list(dict.fromkeys([*risk_ids, *affected_ids]))

    def retained(ids: list[str]) -> list[str]:
        return [cid for cid in ids if cid in node_set]

    def all_hit(ids: list[str]) -> bool:
        return bool(ids and all(cid in node_set for cid in ids))

    def any_hit(ids: list[str]) -> bool:
        return bool(set(ids) & node_set)

    return {
        f"{prefix}_contains_any_risk_node": any_hit(risk_ids),
        f"{prefix}_contains_all_risk_nodes": all_hit(risk_ids),
        f"{prefix}_risk_nodes_retained": retained(risk_ids),
        f"{prefix}_contains_any_evidence_node": any_hit(evidence_ids),
        f"{prefix}_contains_all_evidence_nodes": all_hit(evidence_ids),
        f"{prefix}_evidence_nodes_retained": retained(evidence_ids),
        f"{prefix}_contains_any_affected_node": any_hit(affected_ids),
        f"{prefix}_contains_all_affected_nodes": all_hit(affected_ids),
        f"{prefix}_affected_nodes_retained": retained(affected_ids),
        f"{prefix}_contains_any_valuable_node": any_hit(valuable_ids),
        f"{prefix}_contains_all_valuable_nodes": all_hit(valuable_ids),
        f"{prefix}_valuable_nodes_retained": retained(valuable_ids),
    }


async def run_lea(
    llm: LoggingOpenAIClient,
    args: argparse.Namespace,
    case: dict[str, Any],
    graph: Any,
    scc: Any,
    injection_metadata: dict[str, Any],
) -> dict[str, Any]:
    t0 = time.time()
    cfg = make_mcgs_config(args)
    cfg["alphago_mcgs"]["budget"] = 0
    mcgs = AlphaGoMCGS(llm_client=llm, config=cfg)
    mcgs._init_state(graph, scc)
    prompt_fn = battle.DOMAIN_MCGS_PROMPTS[case["domain"]]
    mcgs._build_focused_prompt = lambda window, _self=mcgs: prompt_fn(_self, window)

    windows = deterministic_windows(mcgs, list(scc.clause_ids), args.window_size)
    entries = []
    for window_index, window in enumerate(windows, 1):
        entry, is_hit = await mcgs._evaluate(window)
        entries.append({"window_index": window_index, "window": window, "entry": entry, "is_tt_hit": is_hit})

    scc_ids = list(scc.clause_ids)
    scc_set = set(scc_ids)
    total_scores: dict[str, float] = defaultdict(float)
    visit_counts: dict[str, int] = defaultdict(int)
    local_counts: dict[str, int] = defaultdict(int)
    repair_counts: dict[str, int] = defaultdict(int)
    endpoint_counts: dict[str, int] = defaultdict(int)
    conflicts = []

    for item in entries:
        entry = item["entry"]
        for cid, score in entry.clause_evaluations.items():
            if cid in scc_set:
                total_scores[cid] += float(score)
                visit_counts[cid] += 1
        for cid in entry.local_risk_subgraph_nodes:
            if cid in scc_set:
                local_counts[cid] += 1
        for cid in entry.repair_entry_nodes:
            if cid in scc_set:
                repair_counts[cid] += 1
        for edge in entry.local_conflict_edges:
            source = edge.get("source")
            target = edge.get("target")
            if source in scc_set and target in scc_set and source != target:
                endpoint_counts[source] += 1
                endpoint_counts[target] += 1
        conflicts.extend(entry.conflicts)

    avg_scores = {
        cid: total_scores[cid] / max(1, visit_counts[cid])
        for cid in scc_ids
        if visit_counts.get(cid, 0) > 0
    }
    score_floor = median(list(avg_scores.values()))
    ranking = sorted(
        [(cid, avg_scores.get(cid, 0.0)) for cid in scc_ids],
        key=lambda item: (-item[1], scc_ids.index(item[0])),
    )
    signal = {
        cid: (
            local_counts.get(cid, 0)
            + repair_counts.get(cid, 0)
            + endpoint_counts.get(cid, 0)
            + max(0.0, avg_scores.get(cid, 0.0) - score_floor)
        )
        for cid in scc_ids
    }
    cap = min(len(scc_ids), max(4, math.ceil(len(scc_ids) * 0.45)))
    ranked_signal = sorted(signal.items(), key=lambda item: (-item[1], scc_ids.index(item[0])))
    selected = {cid for cid, value in ranked_signal if value > 0.0}
    if not selected:
        selected = {cid for cid, _ in ranking[:cap]}
    else:
        selected = {cid for cid, _ in ranked_signal[:cap]}
    subgraph_nodes = [cid for cid in scc_ids if cid in selected]

    gt_nodes = [cid for cid in scc_ids if battle.is_ground_truth_node(cid, case["domain"])]
    top3_ids = {cid for cid, _ in ranking[:3]}
    risk_ids = list(dict.fromkeys(injection_metadata.get("injected_risk_nodes") or []))
    evidence_ids = list(dict.fromkeys(injection_metadata.get("injected_evidence_nodes") or []))
    affected_ids = list(dict.fromkeys(injection_metadata.get("injected_affected_nodes") or []))

    return {
        "method": "lea",
        "method_source": (
            "GraphRAG-style Local Evidence Aggregation: deterministic graph-window "
            "retrieval with the SA-MCGS local evidence schema, without relation-first "
            "memory, critical-pair revisiting, OC/core signals, or dynamic-core replacement."
        ),
        **battle.build_risk_rubric_audit(
            adapter_type="deterministic_local_window_evidence_aggregation",
            input_scope="local_scc_window",
        ),
        "model": args.model,
        "domain": case["domain"],
        "scc_id": scc.id,
        "scc_size": scc.size,
        "scc_clause_ids": scc_ids,
        "window_size": args.window_size,
        "deterministic_window_policy": "one center node plus deterministic graph neighbors; fill by SCC order",
        "deterministic_windows": [{"window_index": item["window_index"], "window": item["window"]} for item in entries],
        "llm_calls": sum(1 for item in entries if not item["is_tt_hit"]),
        "tt_hits": sum(1 for item in entries if item["is_tt_hit"]),
        "time": time.time() - t0,
        "scores": avg_scores,
        "visit_counts": dict(visit_counts),
        "ranking": ranking,
        "local_risk_subgraph_counts": dict(local_counts),
        "repair_entry_counts": dict(repair_counts),
        "local_conflict_endpoint_counts": dict(endpoint_counts),
        "lea_risk_subgraph_nodes": subgraph_nodes,
        "lea_risk_subgraph_size": len(subgraph_nodes),
        "lea_compression_ratio": 1 - (len(subgraph_nodes) / max(1, len(scc_ids))),
        "conflicts": conflicts,
        "ground_truth_nodes": gt_nodes,
        "top1_hit": ranking[0][0] in gt_nodes if (ranking and gt_nodes) else None,
        "top3_hit": bool(top3_ids & set(gt_nodes)) if gt_nodes else None,
        **coverage_metrics("lea", subgraph_nodes, risk_ids, evidence_ids, affected_ids),
    }


def attach_common_audit(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    case: dict[str, Any],
    method: str,
    llm: LoggingOpenAIClient,
    started_at: float,
    error: str | None = None,
) -> dict[str, Any]:
    result.update(
        {
            **_identity_audit_fields(case),
            "case_id": case["case_id"],
            "case_order": case["case_order"],
            "audit_started_at": started_at,
            "audit_completed_at": time.time(),
            "audit_started_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started_at)),
            "audit_completed_at_iso": now_iso(),
            "case_concurrency": 1,
            "internal_concurrency": args.internal_concurrency if method == "sa-mcgs" else 1,
            "cost_audit_budget": args.budget if method == "sa-mcgs" else None,
            "cost_audit_method": method,
            "cost_audit_error": error,
            "llm_usage_summary": usage_summary(llm.call_records),
        }
    )
    return result


async def run_method(
    args: argparse.Namespace,
    output_dir: Path,
    case: dict[str, Any],
    method: str,
    graph: Any,
    scc: Any,
    injected_id: str,
    injection_metadata: dict[str, Any],
) -> dict[str, Any]:
    llm = make_llm(args, output_dir, case, method)
    started_at = time.time()
    try:
        if method == "sa-mcgs":
            result = await battle.run_sa_mcgs(
                llm,
                args.model,
                case["domain"],
                graph,
                scc,
                make_mcgs_config(args),
            )
            result.update(
                {
                    "inject_mode": True,
                    "injected_node": injected_id,
                    "inject_type": battle.DOMAIN_INJECT_TYPE.get(case["domain"]),
                    "inject_profile": "memory_stress",
                    "cycle_source": "real_long",
                }
            )
            result.update(injection_metadata)
            battle.add_rank_metrics(result, injected_id)
            battle.add_structural_rank_metrics(result, injection_metadata)
            evidence_nodes = injection_metadata.get("injected_evidence_nodes", [injected_id])
            result.update(
                battle.build_risk_subgraph_summary(
                    graph,
                    scc,
                    result,
                    injected_id,
                    evidence_nodes,
                    injection_metadata.get("injected_risk_nodes"),
                    injection_metadata.get("injected_affected_nodes"),
                )
            )
            result.update(
                battle.build_local_declared_subgraph_summary(
                    scc,
                    result,
                    evidence_nodes,
                    injection_metadata.get("injected_risk_nodes"),
                    injection_metadata.get("injected_affected_nodes"),
                )
            )
            result.update(
                battle.build_core_evidence_subgraph_summary(
                    scc,
                    result,
                    evidence_nodes,
                    injection_metadata.get("injected_risk_nodes"),
                    injection_metadata.get("injected_affected_nodes"),
                )
            )
            result.update(
                battle.build_trace_convergence_summary(
                    scc,
                    result,
                    evidence_nodes,
                    injection_metadata.get("injected_risk_nodes"),
                    injection_metadata.get("injected_affected_nodes"),
                )
            )
        elif method == "lea":
            result = await run_lea(llm, args, case, graph, scc, injection_metadata)
            result.update(
                {
                    "inject_mode": True,
                    "injected_node": injected_id,
                    "inject_type": battle.DOMAIN_INJECT_TYPE.get(case["domain"]),
                    "inject_profile": "memory_stress",
                    "cycle_source": "real_long",
                }
            )
            result.update(injection_metadata)
            battle.add_rank_metrics(result, injected_id)
            battle.add_structural_rank_metrics(result, injection_metadata)
        elif method == "naive-single":
            result = await battle.run_naive(
                llm,
                args.model,
                case["domain"],
                graph,
                scc,
                naive_profile="direct_subgraph",
                injected_id=injected_id,
            )
            result["method"] = "full-scc-naive-single"
            result.update(
                {
                    "inject_mode": True,
                    "injected_node": injected_id,
                    "inject_type": battle.DOMAIN_INJECT_TYPE.get(case["domain"]),
                    "inject_profile": "memory_stress",
                    "cycle_source": "real_long",
                }
            )
            result.update(injection_metadata)
            battle.add_rank_metrics(result, injected_id)
            battle.add_structural_rank_metrics(result, injection_metadata)
            battle.add_direct_subgraph_retention_metrics(result, injection_metadata)
        else:
            raise ValueError(f"Unknown method: {method}")
        return attach_common_audit(
            result,
            args=args,
            case=case,
            method=method,
            llm=llm,
            started_at=started_at,
        )
    except Exception as exc:
        payload = {
            "method": method,
            "model": args.model,
            "domain": case["domain"],
            "scc_id": case["scc_id"],
            "scc_size": case["scc_size"],
            "scc_clause_ids": list(scc.clause_ids),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        payload.update(injection_metadata)
        return attach_common_audit(
            payload,
            args=args,
            case=case,
            method=method,
            llm=llm,
            started_at=started_at,
            error=str(exc),
        )
    finally:
        await llm.close()


def result_path(output_dir: Path, case: dict[str, Any], method: str) -> Path:
    return output_dir / "results" / f"{case['case_id']}__{safe_token(method)}.json"


def scale_bin(size: int) -> str:
    if size <= 12:
        return "small"
    if size <= 20:
        return "medium"
    return "large"


def metric_value(result: dict[str, Any], method_label: str, metric: str) -> Any:
    if result.get("cost_audit_error"):
        return None
    if metric == "root@3":
        return result.get("root_top3_hit", result.get("top3_hit"))
    if method_label == "SA-MCGS":
        mapping = {
            "risk_any": "core_evidence_contains_any_risk_node",
            "risk_all": "core_evidence_contains_all_risk_nodes",
            "compression": "core_evidence_compression_ratio",
        }
    elif method_label == "GraphRAG-style LEA":
        mapping = {
            "risk_any": "lea_contains_any_risk_node",
            "risk_all": "lea_contains_all_risk_nodes",
            "compression": "lea_compression_ratio",
        }
    else:
        mapping = {
            "risk_any": "direct_contains_any_risk_node",
            "risk_all": "direct_contains_all_risk_nodes",
            "compression": "direct_compression_ratio",
        }
    return result.get(mapping[metric])


def method_label(result: dict[str, Any]) -> str:
    method = result.get("method")
    if method == "sa-mcgs":
        return "SA-MCGS"
    if method == "lea":
        return "GraphRAG-style LEA"
    if method == "full-scc-naive-single":
        return "Full-SCC Naive, single attempt"
    return str(method)


def mean_numeric(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return sum(nums) / len(nums) if nums else None


def mean_bool(values: list[Any]) -> float | None:
    vals = [v for v in values if isinstance(v, bool)]
    return sum(1 for v in vals if v) / len(vals) if vals else None


def summarize(output_dir: Path) -> None:
    result_files = sorted((output_dir / "results").glob("*.json"))
    rows = []
    for path in result_files:
        result = json.loads(path.read_text(encoding="utf-8"))
        label = method_label(result)
        usage = result.get("llm_usage_summary") or {}
        rows.append(
            {
                "method": label,
                "scale": scale_bin(int(result.get("scc_size") or 0)),
                "case_id": result.get("case_id"),
                "domain": result.get("domain"),
                "scc_size": result.get("scc_size"),
                "case_concurrency": result.get("case_concurrency", 1),
                "internal_concurrency": result.get("internal_concurrency", 1),
                "llm_calls": result.get("llm_calls"),
                "recorded_api_calls": usage.get("recorded_api_calls"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "runtime_sec": result.get("time"),
                "invalid_output": bool(result.get("cost_audit_error")),
                "root_at_3": metric_value(result, label, "root@3"),
                "risk_any": metric_value(result, label, "risk_any"),
                "risk_all": metric_value(result, label, "risk_all"),
                "compression": metric_value(result, label, "compression"),
                "result_file": str(path),
            }
        )

    if not rows:
        return

    flat_path = output_dir / "summary_method_cases.csv"
    with flat_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["method"], "Overall")].append(row)
        groups[(row["method"], row["scale"])].append(row)

    table_rows = []
    for (method, scale), items in sorted(groups.items()):
        table_rows.append(
            {
                "Method": method,
                "Scale": scale,
                "Cases": len({item["case_id"] for item in items}),
                "Case conc.": 1,
                "Internal conc.": int(mean_numeric([item["internal_concurrency"] for item in items]) or 1),
                "Calls / case": mean_numeric([item["llm_calls"] for item in items]),
                "Input tok. / case": mean_numeric([item["prompt_tokens"] for item in items]),
                "Output tok. / case": mean_numeric([item["completion_tokens"] for item in items]),
                "Total tok. / case": mean_numeric([item["total_tokens"] for item in items]),
                "Runtime / case": mean_numeric([item["runtime_sec"] for item in items]),
                "Invalid output": mean_bool([item["invalid_output"] for item in items]),
                "Root@3": mean_bool([item["root_at_3"] for item in items]),
                "Risk-any": mean_bool([item["risk_any"] for item in items]),
                "Risk-all": mean_bool([item["risk_all"] for item in items]),
                "Compression": mean_numeric([item["compression"] for item in items]),
            }
        )

    table_csv = output_dir / "summary_cost_table.csv"
    with table_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(table_rows[0].keys()))
        writer.writeheader()
        writer.writerows(table_rows)

    headers = list(table_rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in table_rows:
        cells = []
        for header in headers:
            value = row[header]
            if isinstance(value, float):
                if "tok" in header:
                    cells.append(f"{value:.0f}")
                elif "Runtime" in header:
                    cells.append(f"{value:.1f}s")
                else:
                    cells.append(f"{value:.3f}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    (output_dir / "summary_cost_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_status(output_dir: Path, plan: list[dict[str, Any]], methods: list[str], current: dict[str, Any] | None = None) -> None:
    result_dir = output_dir / "results"
    completed = 0
    failed = 0
    for case in plan:
        for method in methods:
            path = result_path(output_dir, case, method)
            if not path.exists():
                continue
            completed += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                failed += 1
                continue
            if payload.get("cost_audit_error"):
                failed += 1
    status = {
        "run_id": output_dir.name,
        "updated_at": now_iso(),
        "total_cases": len(plan),
        "methods": methods,
        "total_method_cases": len(plan) * len(methods),
        "completed_method_cases": completed,
        "failed_method_cases": failed,
        "remaining_method_cases": len(plan) * len(methods) - completed,
        "current": current,
        "result_dir": str(result_dir),
        "call_log": str(output_dir / "call_logs" / "llm_calls.jsonl"),
    }
    atomic_write_json(output_dir / "status.json", status)


async def run(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = build_or_load_case_plan(args, output_dir)
    graphs = load_graphs(plan)
    persist_case_plan(output_dir, plan)
    atomic_write_json(
        output_dir / "case_identity_preflight.json",
        {
            **validate_case_plan(plan, graphs),
            "validated_at": now_iso(),
        },
    )
    methods = args.methods
    for case in plan:
        for method in methods:
            existing_path = result_path(output_dir, case, method)
            if existing_path.exists():
                existing = json.loads(existing_path.read_text(encoding="utf-8"))
                validate_result_case_identity(existing, case, graphs[case["domain"]])
    atomic_write_json(
        output_dir / "run_config.json",
        {
            "created_or_updated_at": now_iso(),
            "model": args.model,
            "model_id": MODEL_IDS.get(args.model, args.model),
            "budget": args.budget,
            "window_size": args.window_size,
            "case_concurrency": 1,
            "internal_concurrency": args.internal_concurrency,
            "methods": methods,
            "case_csv": str(args.case_csv),
            "use_all_case_rows": args.use_all_case_rows,
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
            "case_identity_version": STABLE_CASE_IDENTITY_VERSION,
        },
    )
    if args.dry_run or args.validate_only:
        write_status(output_dir, plan, methods)
        summarize(output_dir)
        return

    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        raise RuntimeError(f"{args.api_key_env} is not set")

    write_status(output_dir, plan, methods)

    for case in plan:
        graph, scc, injected_id, injection_metadata = prepare_injected_case(case, graphs)
        with InjectedGroundTruth(case["domain"], injected_id):
            for method in methods:
                path = result_path(output_dir, case, method)
                if path.exists():
                    existing = json.loads(path.read_text(encoding="utf-8"))
                    validate_result_case_identity(existing, case, graphs[case["domain"]])
                    if not (args.retry_errors and existing.get("cost_audit_error")):
                        continue
                current = {
                    "case_id": case["case_id"],
                    "case_order": case["case_order"],
                    "domain": case["domain"],
                    "scc_size": case["scc_size"],
                    "template": case["template"],
                    "method": method,
                    "started_at": now_iso(),
                }
                write_status(output_dir, plan, methods, current=current)
                result = await run_method(
                    args,
                    output_dir,
                    case,
                    method,
                    graph,
                    scc,
                    injected_id,
                    injection_metadata,
                )
                atomic_write_json(path, result)
                summarize(output_dir)
                write_status(output_dir, plan, methods, current={**current, "completed_at": now_iso()})

    summarize(output_dir)
    write_status(output_dir, plan, methods)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run clean low-concurrency cost audit.")
    parser.add_argument("--case-csv", type=Path, default=DEFAULT_CASE_CSV)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--template-preference", default="direct_mutex")
    parser.add_argument("--budget", type=int, default=50)
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--internal-concurrency", type=int, default=1)
    parser.add_argument("--compression-profile", default="current")
    parser.add_argument(
        "--methods",
        nargs="+",
        default=["sa-mcgs", "lea", "naive-single"],
        choices=["sa-mcgs", "lea", "naive-single"],
    )
    parser.add_argument("--base-url", default=battle.XHUB_BASE_URL)
    parser.add_argument("--api-key-env", default="XHUB_API_KEY")
    parser.add_argument("--llm-timeout", type=float, default=600)
    parser.add_argument("--llm-max-retries", type=int, default=2)
    parser.add_argument("--rebuild-plan", action="store_true")
    parser.add_argument("--use-all-case-rows", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate and persist stable case identities without making API calls.",
    )
    args = parser.parse_args()
    if args.output_dir is None:
        run_id = time.strftime("clean_gpt4o_b50_%Y%m%d_%H%M%S", time.localtime())
        args.output_dir = DEFAULT_RUNS_DIR / run_id
    args.output_dir = args.output_dir.resolve()
    args.case_csv = args.case_csv.resolve()
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))

#!/usr/bin/env python3
"""Run LEA on the 18 frozen, unmodified pre-injection SCCs.

This runner is intentionally separate from the injected-case runners.  It
reconstructs each graph directly from ``pre_sources_18.json`` and never calls
the injection pipeline.  A validation-only pass performs all identity and SCC
checks without constructing an API client or making a model call.
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
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "cross_domain"))

from emnlp2026_discussion import run_cost_audit_clean as cost
from src.models.clause import Clause
from src.models.graph import DependencyGraph, Edge, SCCInfo
from src.modules.alphago_mcgs import AlphaGoMCGS
from src.modules.tarjan import TarjanSCCDetector


DEFAULT_SOURCE_JSON = (
    REPO_ROOT
    / "2026NAACL/SA-MCGS/annotation_prep/candidates/pre_sources_18.json"
)
DEFAULT_RUNS_DIR = REPO_ROOT / "2026NAACL/SA-MCGS/experiments/lea_runs"
DEFAULT_MODELS = ["gpt-4o", "gemini-2.5-pro"]
PRE_IDENTITY_VERSION = "unmodified_pre_source_content_v1"
ABSTENTION_RULE_VERSION = "explicit_pair_v1"
EXPECTED_SOURCE_COUNT = 18
EXPECTED_DOMAIN_COUNTS = {"sec_ex21": 5, "bgb": 3, "cuad": 10}


class PreSourceValidationError(RuntimeError):
    """The frozen pre-source manifest cannot be reproduced exactly."""


class StrictJSONError(RuntimeError):
    """A model response remained invalid after JSON/schema retries."""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def safe_token(text: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("_")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical_weight(value: Any) -> str:
    return format(float(value), ".17g")


def canonical_edges(edges: Iterable[Any]) -> list[dict[str, str]]:
    normalized = []
    for edge in edges:
        if isinstance(edge, dict):
            source = str(edge["source"])
            target = str(edge["target"])
            dependency_type = str(edge.get("dependency_type", "references"))
            weight = canonical_weight(edge.get("weight", 1.0))
        else:
            source = str(edge.source)
            target = str(edge.target)
            dependency_type = str(getattr(edge.dependency_type, "value", edge.dependency_type))
            weight = canonical_weight(edge.weight)
        normalized.append(
            {
                "source": source,
                "target": target,
                "dependency_type": dependency_type,
                "weight": weight,
            }
        )
    return sorted(
        normalized,
        key=lambda item: (
            item["source"],
            item["target"],
            item["dependency_type"],
            item["weight"],
        ),
    )


def atomic_write_json(path: Path, payload: Any) -> None:
    cost.atomic_write_json(path, payload)


def atomic_write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )
    tmp.replace(path)


def expected_source_fingerprint(source: dict[str, Any]) -> str:
    return sha256_json(
        {
            "version": "source_physical_scc_identity_v1",
            "domain": source["domain"],
            "dataset_revision": source["dataset_revision"],
            "ordered_clause_ids": sorted(source["ordered_clause_ids"]),
            "typed_internal_edges": canonical_edges(source["typed_internal_edges"]),
        }
    )


def expected_content_fingerprint(source: dict[str, Any]) -> str:
    text_hashes = [
        {
            "id": str(clause["id"]),
            "normalized_text_sha256": "sha256:"
            + hashlib.sha256(normalize_text(clause.get("content")).encode("utf-8")).hexdigest(),
        }
        for clause in source["clauses"]
    ]
    return sha256_json(
        {
            "version": PRE_IDENTITY_VERSION,
            "source_physical_fingerprint": source["source_physical_fingerprint"],
            "domain": source["domain"],
            "dataset_revision": source["dataset_revision"],
            "ordered_clause_ids": sorted(source["ordered_clause_ids"]),
            "normalized_clause_text_hashes": text_hashes,
            "typed_internal_edges": canonical_edges(source["typed_internal_edges"]),
        }
    )


def reconstruct_source(source: dict[str, Any]) -> tuple[DependencyGraph, SCCInfo]:
    required = {
        "pre_source_id",
        "source_physical_fingerprint",
        "pre_content_fingerprint",
        "domain",
        "source_scc_size",
        "dataset_revision",
        "unmodified",
        "ordered_clause_ids",
        "typed_internal_edges",
        "clauses",
    }
    missing = sorted(required - set(source))
    if missing:
        raise PreSourceValidationError(f"pre source missing fields {missing}")
    source_id = str(source["pre_source_id"])
    if source.get("unmodified") is not True:
        raise PreSourceValidationError(f"{source_id}: unmodified must be true")

    ordered_ids = [str(value) for value in source["ordered_clause_ids"]]
    if not ordered_ids or len(ordered_ids) != len(set(ordered_ids)):
        raise PreSourceValidationError(f"{source_id}: clause IDs are empty or duplicated")
    if int(source["source_scc_size"]) != len(ordered_ids):
        raise PreSourceValidationError(
            f"{source_id}: source_scc_size={source['source_scc_size']} != {len(ordered_ids)}"
        )

    clause_rows = source["clauses"]
    clause_ids = [str(row.get("id")) for row in clause_rows]
    if clause_ids != ordered_ids:
        raise PreSourceValidationError(
            f"{source_id}: clauses must occur once and in ordered_clause_ids order"
        )
    clauses = {
        str(row["id"]): Clause(
            id=str(row["id"]),
            title=str(row.get("title") or ""),
            content=str(row.get("content") or ""),
            clause_type=str(row.get("clause_type") or "other"),
            metadata={
                "condition": "pre",
                "pre_source_id": source_id,
                "unmodified": True,
            },
        )
        for row in clause_rows
    }

    clause_set = set(ordered_ids)
    edges = []
    for row in source["typed_internal_edges"]:
        edge = Edge(
            source=str(row["source"]),
            target=str(row["target"]),
            dependency_type=str(row.get("dependency_type") or "references"),
            weight=float(row.get("weight", 1.0)),
            reasoning="frozen_original_internal_edge",
        )
        if edge.source not in clause_set or edge.target not in clause_set:
            raise PreSourceValidationError(
                f"{source_id}: edge {edge.source}->{edge.target} leaves the frozen SCC"
            )
        edges.append(edge)

    actual_source_fp = expected_source_fingerprint(source)
    if actual_source_fp != source["source_physical_fingerprint"]:
        raise PreSourceValidationError(
            f"{source_id}: source fingerprint mismatch "
            f"{actual_source_fp} != {source['source_physical_fingerprint']}"
        )
    actual_content_fp = expected_content_fingerprint(source)
    if actual_content_fp != source["pre_content_fingerprint"]:
        raise PreSourceValidationError(
            f"{source_id}: content fingerprint mismatch "
            f"{actual_content_fp} != {source['pre_content_fingerprint']}"
        )

    graph = DependencyGraph(
        clauses=clauses,
        edges=edges,
        metadata={
            "condition": "pre",
            "inject_mode": False,
            "pre_source_id": source_id,
            "source_physical_fingerprint": source["source_physical_fingerprint"],
            "pre_content_fingerprint": source["pre_content_fingerprint"],
            "dataset_revision": source["dataset_revision"],
        },
    )
    detected_graph = TarjanSCCDetector().detect(graph)
    exact = [
        item
        for item in detected_graph.sccs
        if set(item.clause_ids) == clause_set and len(item.clause_ids) == len(clause_set)
    ]
    if len(exact) != 1 or len(detected_graph.sccs) != 1 or detected_graph.dag_nodes:
        raise PreSourceValidationError(
            f"{source_id}: frozen graph is not exactly one SCC "
            f"(exact={len(exact)}, nontrivial={len(detected_graph.sccs)}, "
            f"dag={len(detected_graph.dag_nodes)})"
        )
    scc = SCCInfo(
        id=source_id,
        clause_ids=ordered_ids,
        internal_edges=edges,
        size=len(ordered_ids),
    )
    return graph, scc


def load_and_validate_sources(path: Path) -> tuple[list[dict[str, Any]], dict[str, tuple[DependencyGraph, SCCInfo]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise PreSourceValidationError(f"{path}: expected a non-empty JSON list")
    if len(payload) != EXPECTED_SOURCE_COUNT:
        raise PreSourceValidationError(
            f"{path}: expected the frozen {EXPECTED_SOURCE_COUNT} pre sources, found {len(payload)}"
        )
    domain_counts = Counter(str(row.get("domain")) for row in payload)
    if dict(domain_counts) != EXPECTED_DOMAIN_COUNTS:
        raise PreSourceValidationError(
            f"{path}: domain counts {dict(domain_counts)} != {EXPECTED_DOMAIN_COUNTS}"
        )
    ids = [str(row.get("pre_source_id")) for row in payload]
    source_fps = [str(row.get("source_physical_fingerprint")) for row in payload]
    content_fps = [str(row.get("pre_content_fingerprint")) for row in payload]
    for label, values in (
        ("pre_source_id", ids),
        ("source_physical_fingerprint", source_fps),
        ("pre_content_fingerprint", content_fps),
    ):
        if len(values) != len(set(values)):
            raise PreSourceValidationError(f"duplicate {label} in {path}")
    reconstructed = {
        str(source["pre_source_id"]): reconstruct_source(source)
        for source in payload
    }
    return payload, reconstructed


def build_plan(sources: list[dict[str, Any]], models: list[str]) -> list[dict[str, Any]]:
    if not models or len(models) != len(set(models)):
        raise ValueError("--models must contain one or more distinct model aliases")
    plan = []
    for model in models:
        for source in sources:
            identity = {
                "version": "pre_lea_case_identity_v1",
                "model": model,
                "pre_content_fingerprint": source["pre_content_fingerprint"],
                "method": "lea",
            }
            plan.append(
                {
                    "case_order": len(plan) + 1,
                    "case_id": safe_token(f"{source['pre_source_id']}__{model}"),
                    "case_uid": sha256_json(identity),
                    "case_identity": identity,
                    "condition": "pre",
                    "inject_mode": False,
                    "method": "lea",
                    "model": model,
                    "domain": source["domain"],
                    "scc_id": source["pre_source_id"],
                    "scc_size": int(source["source_scc_size"]),
                    "pre_source_id": source["pre_source_id"],
                    "source_physical_fingerprint": source["source_physical_fingerprint"],
                    "pre_content_fingerprint": source["pre_content_fingerprint"],
                    "dataset_revision": source["dataset_revision"],
                    "ordered_clause_ids": list(source["ordered_clause_ids"]),
                }
            )
    return plan


def plan_fingerprint(plan: list[dict[str, Any]]) -> str:
    return sha256_json(
        [
            {
                "case_uid": case["case_uid"],
                "case_order": case["case_order"],
                "model": case["model"],
                "pre_content_fingerprint": case["pre_content_fingerprint"],
            }
            for case in plan
        ]
    )


def persist_or_check_plan(output_dir: Path, plan: list[dict[str, Any]], rebuild: bool) -> None:
    path = output_dir / "case_plan.json"
    if path.exists() and not rebuild:
        old = json.loads(path.read_text(encoding="utf-8"))
        if plan_fingerprint(old) != plan_fingerprint(plan):
            raise PreSourceValidationError(
                f"existing plan differs in {output_dir}; use a new directory or --rebuild-plan"
            )
    atomic_write_json(path, plan)
    atomic_write_csv(output_dir / "case_plan.csv", plan)


def result_path(output_dir: Path, case: dict[str, Any]) -> Path:
    return output_dir / "results" / f"{case['case_id']}__lea.json"


def validate_result_identity(result: dict[str, Any], case: dict[str, Any]) -> None:
    checks = (
        "case_uid",
        "model",
        "domain",
        "pre_source_id",
        "source_physical_fingerprint",
        "pre_content_fingerprint",
    )
    differences = [key for key in checks if result.get(key) != case.get(key)]
    if result.get("condition") != "pre" or result.get("inject_mode") is not False:
        differences.append("condition/inject_mode")
    if differences:
        raise PreSourceValidationError(
            f"existing result identity mismatch for {case['case_id']}: {differences}"
        )


def schema_error(payload: Any, expected_ids: list[str]) -> str | None:
    if not isinstance(payload, dict):
        return "response is not a JSON object"
    evaluations = payload.get("clause_evaluations")
    if not isinstance(evaluations, dict):
        return "clause_evaluations is not an object"
    for clause_id in expected_ids:
        value = evaluations.get(clause_id)
        if not isinstance(value, dict):
            return f"missing clause evaluation for exact ID {clause_id}"
        score = value.get("risk_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return f"risk_score is not numeric for {clause_id}"
        if not math.isfinite(float(score)) or not 0.0 <= float(score) <= 1.0:
            return f"risk_score is outside [0,1] for {clause_id}"
    for field in (
        "conflicts",
        "local_risk_subgraph_nodes",
        "local_conflict_edges",
        "critical_pairs",
        "repair_entry_nodes",
    ):
        value = payload.get(field, [])
        if not isinstance(value, list):
            return f"{field} is not a list"
        if field in {"conflicts", "local_conflict_edges", "critical_pairs"} and any(
            not isinstance(item, dict) for item in value
        ):
            return f"{field} contains a non-object item"
    return None


class StrictPreLoggingClient(cost.LoggingOpenAIClient):
    """Add terminal JSON/schema diagnostics to the existing call logger."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.json_validation_attempt_failures: list[dict[str, Any]] = []
        self.terminal_json_failures: list[dict[str, Any]] = []
        self._terminal_failure_latched: str | None = None

    async def call_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        retries: int = 2,
    ) -> dict[str, Any]:
        if self._terminal_failure_latched:
            raise StrictJSONError(self._terminal_failure_latched)
        expected_ids = re.findall(r"^### ID:\s*(.+?)\s*$", prompt, flags=re.MULTILINE)
        if not expected_ids:
            expected_ids = re.findall(r"^### ([^:]+):", prompt, flags=re.MULTILINE)
        if not expected_ids:
            message = "runner could not recover exact window IDs from the prompt"
            self._record_terminal_json_failure([], 0, message)
            raise StrictJSONError(message)
        for attempt in range(1, retries + 2):
            try:
                response = await self.call(
                    prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt,
                    response_format={"type": "json_object"},
                )
            except Exception as exc:
                message = f"API failure: {type(exc).__name__}: {exc}"
                self._record_terminal_json_failure(expected_ids, attempt, message)
                raise StrictJSONError(message) from exc

            parsed = self._extract_json(response.content)
            error = schema_error(parsed, expected_ids)
            if error is None:
                return parsed
            diagnostic = {
                **self.context,
                "event": "json_schema_attempt_failure",
                "recorded_at": now_iso(),
                "attempt": attempt,
                "expected_window_ids": expected_ids,
                "error": error,
            }
            self.json_validation_attempt_failures.append(diagnostic)
            cost.append_jsonl(self.call_log_path, diagnostic)
            if attempt <= retries:
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
                continue
            self._record_terminal_json_failure(expected_ids, attempt, error)
            raise StrictJSONError(error)
        raise AssertionError("unreachable")

    def _record_terminal_json_failure(
        self,
        expected_ids: list[str],
        attempt: int,
        error: str,
    ) -> None:
        diagnostic = {
            **self.context,
            "event": "terminal_json_or_api_failure",
            "recorded_at": now_iso(),
            "attempt": attempt,
            "expected_window_ids": expected_ids,
            "error": error,
        }
        self.terminal_json_failures.append(diagnostic)
        self._terminal_failure_latched = error
        cost.append_jsonl(self.call_log_path, diagnostic)


def make_llm(
    args: argparse.Namespace,
    output_dir: Path,
    case: dict[str, Any],
) -> StrictPreLoggingClient:
    model_id = cost.MODEL_IDS.get(case["model"], case["model"])
    return StrictPreLoggingClient(
        {
            "provider": "openai",
            "model": model_id,
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
            "timeout": args.llm_timeout,
            "max_retries": args.llm_max_retries,
        },
        call_log_path=output_dir / "call_logs" / "llm_calls.jsonl",
        context={
            "run_id": output_dir.name,
            "case_id": case["case_id"],
            "case_order": case["case_order"],
            "condition": "pre",
            "domain": case["domain"],
            "scc_id": case["scc_id"],
            "scc_size": case["scc_size"],
            "method": "lea",
            "model": case["model"],
            "case_concurrency": args.case_concurrency,
            "internal_concurrency": 1,
        },
    )


def filter_explicit_pairs(
    conflicts: Any,
    exact_scc_ids: list[str],
) -> tuple[list[dict[str, Any]], int]:
    allowed = set(exact_scc_ids)
    accepted: dict[tuple[str, str], dict[str, Any]] = {}
    rejected = 0
    if not isinstance(conflicts, list):
        return [], 1
    for item in conflicts:
        if not isinstance(item, dict):
            rejected += 1
            continue
        source = item.get("clause_a") or item.get("source") or item.get("from")
        target = item.get("clause_b") or item.get("target") or item.get("to")
        reason = item.get("description") or item.get("reason") or item.get("rationale")
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or source not in allowed
            or target not in allowed
            or source == target
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            rejected += 1
            continue
        key = tuple(sorted((source, target)))
        if key not in accepted:
            accepted[key] = {
                "source": key[0],
                "target": key[1],
                "reason": reason.strip(),
                "support_count": 1,
            }
        else:
            accepted[key]["support_count"] += 1
    return [accepted[key] for key in sorted(accepted)], rejected


def null_injected_metrics(result: dict[str, Any]) -> None:
    result.update(
        {
            "ground_truth_nodes": None,
            "top1_hit": None,
            "top3_hit": None,
            "root_at_3": None,
            "risk_any": None,
            "risk_all": None,
            "injected_node": None,
            "inject_type": None,
            "inject_profile": None,
            "injected_risk_nodes": None,
            "injected_evidence_nodes": None,
            "injected_affected_nodes": None,
            "injected_ground_truth_available": False,
        }
    )
    for key in list(result):
        if key.startswith("lea_contains_") or key.startswith("lea_") and key.endswith("_retained"):
            result[key] = None


async def run_case(
    args: argparse.Namespace,
    output_dir: Path,
    case: dict[str, Any],
    reconstructed: dict[str, tuple[DependencyGraph, SCCInfo]],
) -> dict[str, Any]:
    graph, scc = reconstructed[case["pre_source_id"]]
    llm = make_llm(args, output_dir, case)
    started_at = time.time()
    result: dict[str, Any]
    caught_error: str | None = None
    try:
        case_args = copy.copy(args)
        case_args.model = case["model"]
        result = await cost.run_lea(llm, case_args, case, graph, scc, {})
    except Exception as exc:
        caught_error = f"{type(exc).__name__}: {exc}"
        result = {
            "method": "lea",
            "model": case["model"],
            "domain": case["domain"],
            "scc_id": case["scc_id"],
            "scc_size": case["scc_size"],
            "scc_clause_ids": list(scc.clause_ids),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    finally:
        await llm.close()

    usage = cost.usage_summary(llm.call_records)
    invalid_reasons = []
    if caught_error:
        invalid_reasons.append(caught_error)
    if int(usage.get("failed_api_calls") or 0):
        invalid_reasons.append(f"{usage['failed_api_calls']} failed API call(s)")
    if llm.terminal_json_failures:
        invalid_reasons.append(
            f"{len(llm.terminal_json_failures)} terminal JSON/API failure(s)"
        )

    pairs, rejected_conflicts = filter_explicit_pairs(
        result.get("conflicts", []), list(scc.clause_ids)
    )
    invalid = bool(invalid_reasons)
    decision = (
        "invalid"
        if invalid
        else "assert_target_conflict"
        if pairs
        else "abstain_from_target_conflict"
    )
    null_injected_metrics(result)
    result.update(
        {
            "case_id": case["case_id"],
            "case_order": case["case_order"],
            "case_uid": case["case_uid"],
            "case_identity": copy.deepcopy(case["case_identity"]),
            "condition": "pre",
            "inject_mode": False,
            "unmodified": True,
            "cycle_source": "naturally_occurring_structural_scc",
            "natural_risk_label_pending_expert": True,
            "pre_source_id": case["pre_source_id"],
            "source_physical_fingerprint": case["source_physical_fingerprint"],
            "pre_content_fingerprint": case["pre_content_fingerprint"],
            "dataset_revision": case["dataset_revision"],
            "abstention_rule_version": ABSTENTION_RULE_VERSION,
            "abstention_rule": (
                "Accept a target-conflict assertion only when a raw conflicts item "
                "contains two distinct exact SCC IDs and a nonempty reason."
            ),
            "target_conflict_decision": decision,
            "explicit_conflict_pairs": pairs,
            "explicit_conflict_pair_count": len(pairs),
            "rejected_raw_conflict_count": rejected_conflicts,
            "abstention_eligible": not invalid,
            "json_validation_attempt_failure_count": len(
                llm.json_validation_attempt_failures
            ),
            "terminal_json_failure_count": len(llm.terminal_json_failures),
            "llm_usage_summary": usage,
            "cost_audit_method": "lea",
            "cost_audit_error": "; ".join(invalid_reasons) if invalid else None,
            "audit_started_at": started_at,
            "audit_completed_at": time.time(),
            "audit_started_at_iso": time.strftime(
                "%Y-%m-%dT%H:%M:%S%z", time.localtime(started_at)
            ),
            "audit_completed_at_iso": now_iso(),
            "case_concurrency": args.case_concurrency,
            "internal_concurrency": 1,
        }
    )
    return result


def mean(values: list[Any]) -> float | None:
    numeric = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return sum(numeric) / len(numeric) if numeric else None


def summarize(output_dir: Path) -> None:
    rows = []
    for path in sorted((output_dir / "results").glob("*__lea.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        usage = result.get("llm_usage_summary") or {}
        rows.append(
            {
                "case_order": result.get("case_order"),
                "case_id": result.get("case_id"),
                "model": result.get("model"),
                "domain": result.get("domain"),
                "pre_source_id": result.get("pre_source_id"),
                "scc_size": result.get("scc_size"),
                "condition": result.get("condition"),
                "invalid_output": bool(result.get("cost_audit_error")),
                "target_conflict_decision": result.get("target_conflict_decision"),
                "explicit_conflict_pair_count": result.get("explicit_conflict_pair_count"),
                "rejected_raw_conflict_count": result.get("rejected_raw_conflict_count"),
                "root_at_3": None,
                "risk_any": None,
                "risk_all": None,
                "compression": result.get("lea_compression_ratio"),
                "llm_calls": result.get("llm_calls"),
                "recorded_api_calls": usage.get("recorded_api_calls"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "runtime_sec": result.get("time"),
                "source_physical_fingerprint": result.get("source_physical_fingerprint"),
                "pre_content_fingerprint": result.get("pre_content_fingerprint"),
                "result_file": str(path),
            }
        )
    if not rows:
        return
    atomic_write_csv(output_dir / "summary_pre_lea_cases.csv", rows)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped["overall"].append(row)
        grouped[f"model={row['model']}"].append(row)
        grouped[f"domain={row['domain']}"].append(row)
        grouped[f"model={row['model']}|domain={row['domain']}"].append(row)
    group_rows = []
    for name, items in sorted(grouped.items()):
        valid = [item for item in items if not item["invalid_output"]]
        group_rows.append(
            {
                "group": name,
                "N": len(items),
                "invalid": sum(bool(item["invalid_output"]) for item in items),
                "valid_N": len(valid),
                "assert_target_conflict": sum(
                    item["target_conflict_decision"] == "assert_target_conflict"
                    for item in valid
                ),
                "abstain_from_target_conflict": sum(
                    item["target_conflict_decision"] == "abstain_from_target_conflict"
                    for item in valid
                ),
                "compression": mean([item["compression"] for item in valid]),
                "calls_per_case": mean([item["llm_calls"] for item in valid]),
                "tokens_per_case": mean([item["total_tokens"] for item in valid]),
                "runtime_sec_per_case": mean([item["runtime_sec"] for item in valid]),
            }
        )
    atomic_write_csv(output_dir / "summary_pre_lea_breakdown.csv", group_rows)


def write_status(
    output_dir: Path,
    plan: list[dict[str, Any]],
    args: argparse.Namespace,
    *,
    phase: str,
    active: list[dict[str, Any]] | None = None,
) -> None:
    completed = 0
    failed = 0
    for case in plan:
        path = result_path(output_dir, case)
        if not path.exists():
            continue
        completed += 1
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            validate_result_identity(result, case)
            if result.get("cost_audit_error"):
                failed += 1
        except Exception:
            failed += 1
    atomic_write_json(
        output_dir / "status.json",
        {
            "run_id": output_dir.name,
            "updated_at": now_iso(),
            "phase": phase,
            "condition": "pre",
            "inject_mode": False,
            "method": "lea",
            "models": args.models,
            "total_cases": len(plan),
            "completed_cases": completed,
            "failed_cases": failed,
            "remaining_cases": len(plan) - completed,
            "case_concurrency": args.case_concurrency,
            "active": active or [],
            "result_dir": str(output_dir / "results"),
            "call_log": str(output_dir / "call_logs" / "llm_calls.jsonl"),
        },
    )


def build_preflight(
    args: argparse.Namespace,
    sources: list[dict[str, Any]],
    reconstructed: dict[str, tuple[DependencyGraph, SCCInfo]],
    plan: list[dict[str, Any]],
) -> dict[str, Any]:
    windows_by_source = {}
    for source in sources:
        graph, scc = reconstructed[source["pre_source_id"]]
        preview_args = copy.copy(args)
        preview_args.model = args.models[0]
        mcgs = AlphaGoMCGS(llm_client=None, config=cost.make_mcgs_config(preview_args))
        mcgs._init_state(graph, scc)
        windows = cost.deterministic_windows(
            mcgs, list(scc.clause_ids), args.window_size
        )
        windows_by_source[source["pre_source_id"]] = len(windows)
    windows_per_model = sum(windows_by_source.values())
    domains = Counter(source["domain"] for source in sources)
    return {
        "validated_at": now_iso(),
        "validation_only": bool(args.validate_only or args.dry_run),
        "api_calls_made_by_preflight": 0,
        "identity_version": PRE_IDENTITY_VERSION,
        "abstention_rule_version": ABSTENTION_RULE_VERSION,
        "source_json": str(args.source_json),
        "source_json_sha256": file_sha256(args.source_json),
        "validated_sources": len(sources),
        "validated_source_ids": [source["pre_source_id"] for source in sources],
        "validated_domains": dict(sorted(domains.items())),
        "validated_nodes": sum(int(source["source_scc_size"]) for source in sources),
        "all_sources_exactly_one_tarjan_scc": True,
        "models": list(args.models),
        "planned_model_cases": len(plan),
        "plan_fingerprint": plan_fingerprint(plan),
        "window_size": args.window_size,
        "deterministic_windows_by_source": windows_by_source,
        "deterministic_windows_per_model": windows_per_model,
        "planned_window_evaluations": windows_per_model * len(args.models),
        "model_call_count_note": (
            "Actual model calls can be lower than planned window evaluations because "
            "bounded transposition-table reuse is stateful; use result llm_calls and the "
            "call log as the authoritative post-run counts."
        ),
    }


async def run(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    call_log = output_dir / "call_logs" / "llm_calls.jsonl"
    call_log.parent.mkdir(parents=True, exist_ok=True)
    call_log.touch(exist_ok=True)

    sources, reconstructed = load_and_validate_sources(args.source_json)
    plan = build_plan(sources, args.models)
    persist_or_check_plan(output_dir, plan, args.rebuild_plan)
    for case in plan:
        path = result_path(output_dir, case)
        if path.exists():
            validate_result_identity(json.loads(path.read_text(encoding="utf-8")), case)

    preflight = build_preflight(args, sources, reconstructed, plan)
    atomic_write_json(output_dir / "case_identity_preflight.json", preflight)
    atomic_write_json(
        output_dir / "run_config.json",
        {
            "created_or_updated_at": now_iso(),
            "source_json": str(args.source_json),
            "source_json_sha256": preflight["source_json_sha256"],
            "models": args.models,
            "resolved_model_ids": {
                model: cost.MODEL_IDS.get(model, model) for model in args.models
            },
            "condition": "pre",
            "inject_mode": False,
            "method": "lea",
            "window_size": args.window_size,
            "case_concurrency": args.case_concurrency,
            "compression_profile": args.compression_profile,
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
            "identity_version": PRE_IDENTITY_VERSION,
            "abstention_rule_version": ABSTENTION_RULE_VERSION,
            "plan_fingerprint": preflight["plan_fingerprint"],
        },
    )
    phase = "validated" if args.validate_only or args.dry_run else "ready"
    write_status(output_dir, plan, args, phase=phase)
    summarize(output_dir)
    if args.validate_only or args.dry_run:
        return
    if not os.environ.get(args.api_key_env, ""):
        raise RuntimeError(f"{args.api_key_env} is not set")

    active: dict[str, dict[str, Any]] = {}
    active_lock = asyncio.Lock()
    summarize_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(args.case_concurrency)

    async def worker(case: dict[str, Any]) -> None:
        path = result_path(output_dir, case)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            validate_result_identity(existing, case)
            if not args.retry_errors or not existing.get("cost_audit_error"):
                return
        async with semaphore:
            entry = {
                "case_id": case["case_id"],
                "case_order": case["case_order"],
                "model": case["model"],
                "domain": case["domain"],
                "pre_source_id": case["pre_source_id"],
                "scc_size": case["scc_size"],
                "started_at": now_iso(),
            }
            async with active_lock:
                active[case["case_id"]] = entry
                write_status(
                    output_dir, plan, args, phase="running", active=list(active.values())
                )
            result = await run_case(args, output_dir, case, reconstructed)
            atomic_write_json(path, result)
            async with summarize_lock:
                summarize(output_dir)
            async with active_lock:
                active.pop(case["case_id"], None)
                write_status(
                    output_dir, plan, args, phase="running", active=list(active.values())
                )

    await asyncio.gather(*(worker(case) for case in plan))
    summarize(output_dir)
    write_status(output_dir, plan, args, phase="complete")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run GraphRAG-style LEA on frozen unmodified pre-injection SCCs."
    )
    parser.add_argument("--source-json", type=Path, default=DEFAULT_SOURCE_JSON)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--case-concurrency", type=int, default=4)
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--budget", type=int, default=0)
    parser.add_argument("--internal-concurrency", type=int, default=1)
    parser.add_argument("--compression-profile", default="current")
    parser.add_argument("--base-url", default=cost.battle.XHUB_BASE_URL)
    parser.add_argument("--api-key-env", default="XHUB_API_KEY")
    parser.add_argument("--llm-timeout", type=float, default=600)
    parser.add_argument("--llm-max-retries", type=int, default=2)
    parser.add_argument("--rebuild-plan", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate/persist identities and status without constructing an API client.",
    )
    args = parser.parse_args()
    if args.output_dir is None:
        run_id = time.strftime("lea_pre18_%Y%m%d_%H%M%S", time.localtime())
        args.output_dir = DEFAULT_RUNS_DIR / run_id
    args.source_json = args.source_json.resolve()
    args.output_dir = args.output_dir.resolve()
    if args.case_concurrency < 1:
        parser.error("--case-concurrency must be >= 1")
    if args.window_size < 1:
        parser.error("--window-size must be >= 1")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))

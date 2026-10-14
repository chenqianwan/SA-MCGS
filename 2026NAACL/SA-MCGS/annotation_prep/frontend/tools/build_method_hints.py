#!/usr/bin/env python3
"""Build the expert-facing LEA/SA-MCGS hint pack with stable identities."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[5]
FRONTEND = Path(__file__).resolve().parents[1]
DEFAULT_CODEBOOK = FRONTEND.parent / "internal" / "private_codebook.json"
DEFAULT_COVERAGE = FRONTEND.parent / "baseline_audit" / "baseline_coverage.csv"
DEFAULT_GPT_PRE = (
    FRONTEND.parents[1]
    / "experiments"
    / "lea_runs"
    / "lea_pre_gpt18_20260829"
    / "results"
)
DEFAULT_GEMINI_PRE = (
    FRONTEND.parents[1]
    / "experiments"
    / "lea_runs"
    / "lea_pre_gemini18_20260829"
    / "results"
)
DEFAULT_GPT_PRE_SA = (
    FRONTEND.parents[1]
    / "experiments"
    / "sa_runs"
    / "sa_pre_gpt18_20260829"
    / "results"
)
DEFAULT_GEMINI_PRE_SA = (
    FRONTEND.parents[1]
    / "experiments"
    / "sa_runs"
    / "sa_pre_gemini18_20260829"
    / "results"
)
DEFAULT_OUTPUT = FRONTEND / "data" / "method_hints.json"
MODELS = ("gpt-4o", "gemini-2.5-pro")
METHODS = ("lea", "sa-mcgs")
RETRY_ROOT = FRONTEND.parents[1] / "experiments" / "pre_baseline_runs" / "pre_baseline_v1_20260909"
RETRY_PROTOCOL = "sha256:873882b0f28e64bd6abef9fc99d122b8334e45144c75dfdc90fa516862674bd9"
RETRY_RUNS = {
    "gpt-4o": (
        RETRY_ROOT / "sa_retry_gpt10",
        "444f37799327520acd8d841df583423204ddad8a279e2758792e499b541709a4",
        10, 7,
    ),
    "gemini-2.5-pro": (
        RETRY_ROOT / "sa_retry_gemini14",
        "44b8f4dbdfc37dea914058e3cd635a48d6be8357acfd969d04b9a1a7df806f23",
        14, 14,
    ),
}


class HintBuildError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def resolve_source_file(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def coverage_rows(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    indexed: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["canonical_case_id"], row["model"], row["method"])
        if key in indexed:
            raise HintBuildError(f"duplicate coverage row: {key}")
        indexed[key] = row
    return indexed


def pre_results(
    expected_method: str, *directories: Path
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for directory in directories:
        for path in sorted(directory.glob("*.json")):
            result = load_json(path)
            if (
                result.get("method") != expected_method
                or result.get("condition") != "pre"
                or result.get("inject_mode") is not False
                or result.get("unmodified") is not True
            ):
                raise HintBuildError(f"invalid pre {expected_method} result: {path}")
            key = (str(result.get("pre_source_id")), str(result.get("model")))
            if key in indexed:
                raise HintBuildError(f"duplicate pre result: {key}")
            indexed[key] = result
    return indexed


def select_sa_record(payload: Any, model: str) -> dict[str, Any]:
    records = payload if isinstance(payload, list) else payload.get("results", [])
    matches = [
        row
        for row in records
        if row.get("method") == "sa-mcgs" and row.get("model") == model
    ]
    if len(matches) != 1:
        raise HintBuildError(
            f"expected one SA-MCGS record for {model}, found {len(matches)}"
        )
    return matches[0]


def ranking_map(result: dict[str, Any]) -> dict[str, int]:
    ranking = result.get("ranking") or []
    return {
        str(item[0]): index + 1
        for index, item in enumerate(ranking)
        if isinstance(item, (list, tuple)) and item
    }


def endpoint_counts(result: dict[str, Any]) -> Counter[str]:
    direct = result.get("local_conflict_endpoint_counts")
    if isinstance(direct, dict):
        return Counter({str(key): int(value) for key, value in direct.items()})
    counts: Counter[str] = Counter()
    for conflict in result.get("conflicts") or []:
        if not isinstance(conflict, dict):
            continue
        for key in ("clause_a", "clause_b", "source", "target"):
            if conflict.get(key):
                counts[str(conflict[key])] += 1
    for edge in result.get("local_conflict_edges") or []:
        if not isinstance(edge, dict):
            continue
        for key in ("source", "target", "clause_a", "clause_b"):
            if edge.get(key):
                counts[str(edge[key])] += 1
    return counts


def method_nodes(result: dict[str, Any], method: str) -> set[str]:
    if method == "lea":
        nodes = result.get("lea_risk_subgraph_nodes") or []
    else:
        # Use the deployable core/evidence packet. `risk_subgraph_nodes` in the
        # historical injected runner may be GT-anchored and must not be exposed
        # as an algorithm-only hint.
        nodes = result.get("core_evidence_risk_subgraph_nodes") or []
    return {str(node) for node in nodes}


def compact_hint(
    result: dict[str, Any], method: str, node_id: str, expected_nodes: set[str]
) -> dict[str, Any]:
    actual_nodes = {str(node) for node in result.get("scc_clause_ids") or []}
    if actual_nodes != expected_nodes:
        raise HintBuildError(
            f"node identity mismatch for {result.get('case_id') or result.get('scc_id')}: "
            f"expected={len(expected_nodes)} actual={len(actual_nodes)}"
        )
    ranks = ranking_map(result)
    scores = result.get("scores") or {}
    selected_nodes = method_nodes(result, method)
    endpoints = endpoint_counts(result)
    evidence = result.get("local_risk_subgraph_counts") or {}
    repair = result.get("repair_entry_counts") or {}
    score = scores.get(node_id)
    return {
        "status": "available",
        "selected": node_id in selected_nodes,
        "score": round(float(score), 4) if score is not None else None,
        "rank": ranks.get(node_id),
        "total_nodes": len(expected_nodes),
        "top3": bool(ranks.get(node_id) and ranks[node_id] <= 3),
        "conflict_endpoint_mentions": int(endpoints.get(node_id, 0)),
        "local_evidence_mentions": int(evidence.get(node_id, 0)),
        "repair_entry_mentions": int(repair.get(node_id, 0)),
    }


def unavailable_hint(status: str, reason: str) -> dict[str, Any]:
    return {"status": status, "reason_zh": reason}


def strict_invalid_hint(result: dict[str, Any] | None = None) -> dict[str, Any]:
    result = result or {}
    error = str(result.get("cost_audit_error") or "")
    usage = result.get("llm_usage_summary") or {}
    recorded = usage.get("recorded_api_calls", 0)
    if (
        recorded > 0
        and usage.get("successful_api_calls") == recorded
        and usage.get("failed_api_calls") == 0
        and result.get("terminal_json_failure_count", 0) > 0
    ):
        reason = "API 已成功返回，但输出未通过严格格式校验，暂无可靠提示"
    elif "API call" in error or "JSON/API" in error:
        reason = "本模型运行失败或输出未通过严格校验，暂无可靠提示"
    else:
        reason = "该模型输出未通过严格校验"
    return unavailable_hint("strict_invalid", reason)


def checked_sa_identity(result: dict[str, Any], master: dict[str, Any], model: str) -> None:
    """Check all source/config identities even for a failed run with no usable score."""
    source_id = master["pre_source_id"]
    expected_nodes = [str(node) for node in master["ordered_clause_ids"]]
    if (
        result.get("method") != "sa-mcgs" or result.get("model") != model
        or result.get("condition") != "pre" or result.get("inject_mode") is not False
        or result.get("unmodified") is not True
        or result.get("pre_source_id") != source_id
        or result.get("scc_size") != len(expected_nodes)
        or result.get("scc_clause_ids") != expected_nodes
    ):
        raise HintBuildError(f"retry source/model/node mismatch: {source_id}/{model}")
    for key in ("source_physical_fingerprint", "pre_content_fingerprint", "dataset_revision", "domain"):
        if not master.get(key) or result.get(key) != master[key]:
            raise HintBuildError(f"retry source identity mismatch: {source_id}/{model}/{key}")
    identity = result.get("case_identity") or {}
    expected_identity = {
        "version": "pre_sa_case_identity_v1", "model": model, "method": "sa-mcgs",
        "pre_content_fingerprint": master["pre_content_fingerprint"],
        "sa_protocol_fingerprint": RETRY_PROTOCOL,
    }
    if identity != expected_identity or result.get("case_uid") != canonical_hash(identity):
        raise HintBuildError(f"retry nested identity or UID mismatch: {source_id}/{model}")
    protocol = result.get("sa_protocol") or {}
    protocol_body = {key: value for key, value in protocol.items() if key != "fingerprint"}
    if (
        result.get("sa_protocol_fingerprint") != RETRY_PROTOCOL
        or protocol.get("fingerprint") != RETRY_PROTOCOL
        or canonical_hash(protocol_body) != RETRY_PROTOCOL
    ):
        raise HintBuildError(f"retry protocol fingerprint mismatch: {source_id}/{model}")


def merge_frozen_sa_retries(
    originals: dict[tuple[str, str], dict[str, Any]],
    codebook: dict[str, Any],
    retry_runs: dict[str, tuple[Path, str, int, int]] | None = None,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    """Use only the frozen September exact retries; never search for a winning attempt."""
    retry_runs = RETRY_RUNS if retry_runs is None else retry_runs
    if set(retry_runs) != set(MODELS):
        raise HintBuildError("retry model set changed")
    masters: dict[str, dict[str, Any]] = {}
    for record in codebook["records"]:
        master = record["master_record"]
        if master.get("unmodified") is True:
            source_id = str(master["pre_source_id"])
            if source_id in masters:
                raise HintBuildError(f"duplicate pre source in codebook: {source_id}")
            masters[source_id] = master
    expected_keys = {(source, model) for source in masters for model in MODELS}
    if len(masters) != 18 or set(originals) != expected_keys:
        raise HintBuildError("expected exactly 18 frozen pre sources by two models")
    for (source, model), result in originals.items():
        checked_sa_identity(result, masters[source], model)
    merged = dict(originals)
    attempted = recovered = remaining = 0
    for model, (run_dir, plan_digest, expected_count, expected_valid) in retry_runs.items():
        plan_path = run_dir / "case_plan.json"
        if hashlib.sha256(plan_path.read_bytes()).hexdigest() != plan_digest:
            raise HintBuildError(f"frozen retry plan changed: {model}")
        plan = load_json(plan_path)
        if not isinstance(plan, list) or len(plan) != expected_count:
            raise HintBuildError(f"unexpected retry plan count: {model}")
        planned: dict[tuple[str, str], dict[str, Any]] = {}
        for row in plan:
            key = (str(row.get("pre_source_id")), str(row.get("model")))
            if key in planned or key not in originals or key[1] != model:
                raise HintBuildError(f"unexpected or duplicate frozen retry cell: {key}")
            planned[key] = row
        invalid_keys = {key for key, row in originals.items() if key[1] == model and row.get("cost_audit_error")}
        if set(planned) != invalid_keys:
            raise HintBuildError(f"retry plan must equal the original invalid-cell set: {model}")
        retry_files = sorted((run_dir / "results").glob("*.json"))
        if len(retry_files) != expected_count:
            raise HintBuildError(f"retry result count changed: {model}")
        observed: set[tuple[str, str]] = set()
        valid_count = 0
        for path in retry_files:
            result = load_json(path)
            key = (str(result.get("pre_source_id")), str(result.get("model")))
            if key in observed or key not in planned:
                raise HintBuildError(f"unexpected or duplicate retry result: {path}")
            observed.add(key)
            checked_sa_identity(result, masters[key[0]], model)
            original, planned_row = originals[key], planned[key]
            for field in (
                "case_uid", "case_identity", "pre_content_fingerprint", "source_physical_fingerprint",
                "dataset_revision", "sa_protocol", "sa_protocol_fingerprint", "method", "model", "domain", "scc_size",
            ):
                planned_value = planned_row.get(field)
                if field == "sa_protocol_fingerprint":
                    planned_value = planned_row.get("sa_protocol", {}).get("fingerprint")
                if result.get(field) != original.get(field) or result.get(field) != planned_value:
                    raise HintBuildError(f"retry identity/config parity mismatch: {key}/{field}")
            if planned_row.get("ordered_clause_ids") != result["scc_clause_ids"]:
                raise HintBuildError(f"retry planned node order changed: {key}")
            if result.get("prompt_semantic_audit_hash") != original.get("prompt_semantic_audit_hash"):
                raise HintBuildError(f"retry prompt semantics changed: {key}")
            if not str(result.get("audit_completed_at_iso") or "").startswith("2026-09-09"):
                raise HintBuildError(f"retry completion date changed: {key}")
            usage = result.get("llm_usage_summary") or {}
            if (
                usage.get("recorded_api_calls", 0) <= 0
                or usage.get("successful_api_calls") != usage.get("recorded_api_calls")
                or usage.get("failed_api_calls") != 0
            ):
                raise HintBuildError(f"frozen retry transport audit changed: {key}")
            if result.get("cost_audit_error"):
                if result.get("terminal_json_failure_count", 0) < 1:
                    raise HintBuildError(f"retry invalid has no terminal validation failure: {key}")
                remaining += 1
            else:
                if result.get("terminal_json_failure_count") != 0:
                    raise HintBuildError(f"retry valid has a terminal validation failure: {key}")
                valid_count += 1
                recovered += 1
            replacement = copy.deepcopy(result)
            replacement["_hint_source_attempt"] = "retry_20260909"
            merged[key] = replacement
            attempted += 1
        if observed != set(planned) or valid_count != expected_valid:
            raise HintBuildError(f"frozen retry outcomes changed: {model}")
    if (attempted, recovered, remaining) != (24, 21, 3):
        raise HintBuildError("unexpected frozen retry totals")
    return merged, {
        "schema_version": "method_hint_retry_update.v1",
        "retry_completed_date": "2026-09-09",
        "original_snapshot_date": "2026-08-29",
        "retry_cells": attempted,
        "recovered_cells": recovered,
        "remaining_sa_invalid_cells": remaining,
        "first_attempt_reliability_preserved": True,
        "description_zh": "已纳入2026年9月9日未注入样本SA-MCGS补跑结果；其余结果保持原记录",
    }


def add_retry_provenance(hint: dict[str, Any], result: dict[str, Any] | None) -> dict[str, Any]:
    if result and result.get("_hint_source_attempt") == "retry_20260909":
        hint["source_attempt"] = "retry_20260909"
        hint["original_status"] = "strict_invalid"
        if hint.get("status") == "strict_invalid":
            hint["reason_zh"] = "9 月 9 日补跑的 " + hint["reason_zh"]
    return hint


def verify_pack_hash(payload: dict[str, Any]) -> str:
    digest = payload.get("hint_pack_hash")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise HintBuildError("invalid existing hint-pack hash")
    if canonical_hash({key: value for key, value in payload.items() if key != "hint_pack_hash"}) != digest:
        raise HintBuildError("existing hint-pack content hash mismatch")
    return digest


def save_hint_pack(payload: dict[str, Any], output: Path) -> tuple[dict[str, Any], bool]:
    """Preserve complete predecessors and leave timestamp/hash unchanged for a no-op."""
    existing = load_json(output) if output.exists() else None
    skip = {"generated_at", "hint_pack_hash", "previous_hint_pack_hashes"}
    previous: list[str] = []
    if existing is not None:
        old_hash = verify_pack_hash(existing)
        if existing.get("source_manifest_hash") != payload.get("source_manifest_hash"):
            raise HintBuildError("refusing to mix hint history from another manifest")
        if {k: v for k, v in existing.items() if k not in skip} == {k: v for k, v in payload.items() if k not in skip}:
            return existing, False
        history_dir = output.parent / "history"
        for ancestor in existing.get("previous_hint_pack_hashes", []):
            if not isinstance(ancestor, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", ancestor):
                raise HintBuildError("invalid predecessor hash")
            ancestor_path = history_dir / f"method_hints.{ancestor.split(':')[1]}.json"
            ancestor_pack = load_json(ancestor_path)
            if verify_pack_hash(ancestor_pack) != ancestor or ancestor_pack.get("source_manifest_hash") != payload["source_manifest_hash"]:
                raise HintBuildError("unverified hint-pack predecessor")
            if ancestor not in previous:
                previous.append(ancestor)
        history_dir.mkdir(parents=True, exist_ok=True)
        archive = history_dir / f"method_hints.{old_hash.split(':')[1]}.json"
        original_bytes = output.read_bytes()
        if archive.exists():
            if archive.read_bytes() != original_bytes:
                raise HintBuildError("existing hint history cannot be overwritten")
        else:
            with archive.open("xb") as handle:
                handle.write(original_bytes)
        previous = [old_hash] + [ancestor for ancestor in previous if ancestor != old_hash]
    final = copy.deepcopy(payload)
    final["previous_hint_pack_hashes"] = previous
    final["generated_at"] = datetime.now(timezone.utc).isoformat()
    final["hint_pack_hash"] = canonical_hash(final)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return final, True


def build_post_case(
    record: dict[str, Any], coverage: dict[tuple[str, str, str], dict[str, str]]
) -> dict[str, Any]:
    master = record["master_record"]
    canonical_id = str(master["canonical_case_id"])
    section_map = record["section_map"]
    expected_nodes = {str(row["original_node_id"]) for row in section_map}
    method_results: dict[tuple[str, str], dict[str, Any]] = {}
    unavailable: dict[tuple[str, str], dict[str, Any]] = {}
    for method in METHODS:
        for model in MODELS:
            key = (method, model)
            row = coverage.get((canonical_id, model, method))
            if not row or not row.get("source_file"):
                unavailable[key] = unavailable_hint("missing", "没有可核验的对应结果")
                continue
            coverage_status = str(row.get("coverage_status") or "")
            if coverage_status != "available_exact":
                if coverage_status == "strict_invalid":
                    unavailable[key] = strict_invalid_hint()
                elif coverage_status == "identity_mismatch":
                    unavailable[key] = unavailable_hint(
                        "identity_mismatch", "结果身份与当前样本不一致"
                    )
                else:
                    unavailable[key] = unavailable_hint("missing", "没有可核验的对应结果")
                continue
            source = resolve_source_file(row["source_file"])
            payload = load_json(source)
            result = select_sa_record(payload, model) if method == "sa-mcgs" else payload
            if result.get("cost_audit_error"):
                unavailable[key] = strict_invalid_hint(result)
            else:
                method_results[key] = result
    sections: dict[str, Any] = {}
    for mapped in section_map:
        section_id = str(mapped["section_id"])
        node_id = str(mapped["original_node_id"])
        methods: dict[str, Any] = {}
        for method in METHODS:
            models: dict[str, Any] = {}
            for model in MODELS:
                result = method_results.get((method, model))
                models[model] = (
                    compact_hint(result, method, node_id, expected_nodes)
                    if result
                    else unavailable.get(
                        (method, model),
                        unavailable_hint("missing", "没有可核验的对应结果"),
                    )
                )
            methods[method] = {"models": models}
        sections[section_id] = {"methods": methods}
    return {
        "condition": "post",
        "sections": sections,
        "identity_verified": True,
    }


def build_pre_case(
    record: dict[str, Any],
    indexed_pre_lea: dict[tuple[str, str], dict[str, Any]],
    indexed_pre_sa: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    master = record["master_record"]
    pre_source_id = str(master["pre_source_id"])
    section_map = record["section_map"]
    expected_nodes = {str(row["original_node_id"]) for row in section_map}
    sections: dict[str, Any] = {}
    for mapped in section_map:
        section_id = str(mapped["section_id"])
        node_id = str(mapped["original_node_id"])
        lea_models: dict[str, Any] = {}
        sa_models: dict[str, Any] = {}
        for model in MODELS:
            lea_result = indexed_pre_lea.get((pre_source_id, model))
            if not lea_result:
                lea_models[model] = unavailable_hint("missing", "没有可核验的对应结果")
            elif lea_result.get("cost_audit_error"):
                lea_models[model] = strict_invalid_hint(lea_result)
            else:
                lea_models[model] = compact_hint(
                    lea_result, "lea", node_id, expected_nodes
                )

            sa_result = indexed_pre_sa.get((pre_source_id, model))
            if not sa_result:
                sa_models[model] = unavailable_hint(
                    "not_run", "未注入原始样本的 SA-MCGS 尚未运行"
                )
            elif sa_result.get("cost_audit_error"):
                sa_models[model] = strict_invalid_hint(sa_result)
            else:
                sa_models[model] = compact_hint(
                    sa_result, "sa-mcgs", node_id, expected_nodes
                )
            sa_models[model] = add_retry_provenance(sa_models[model], sa_result)
        sections[section_id] = {
            "methods": {
                "lea": {"models": lea_models},
                "sa-mcgs": {"models": sa_models},
            }
        }
    return {
        "condition": "pre",
        "sections": sections,
        "identity_verified": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--gpt-pre", type=Path, default=DEFAULT_GPT_PRE)
    parser.add_argument("--gemini-pre", type=Path, default=DEFAULT_GEMINI_PRE)
    parser.add_argument("--gpt-pre-sa", type=Path, default=DEFAULT_GPT_PRE_SA)
    parser.add_argument("--gemini-pre-sa", type=Path, default=DEFAULT_GEMINI_PRE_SA)
    parser.add_argument("--historical-only", action="store_true", help="Use only the original August runs, without September exact retries")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    codebook = load_json(args.codebook)
    coverage = coverage_rows(args.coverage)
    indexed_pre_lea = pre_results("lea", args.gpt_pre, args.gemini_pre)
    indexed_pre_sa = pre_results("sa-mcgs", args.gpt_pre_sa, args.gemini_pre_sa)
    source_update = None
    if not args.historical_only:
        indexed_pre_sa, source_update = merge_frozen_sa_retries(indexed_pre_sa, codebook)
    cases: dict[str, Any] = {}
    condition_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for record in codebook["records"]:
        master = record["master_record"]
        built = (
            build_pre_case(record, indexed_pre_lea, indexed_pre_sa)
            if master.get("unmodified") is True
            else build_post_case(record, coverage)
        )
        cases[str(record["presentation_id"])] = built
        condition_counts[built["condition"]] += 1
        for section in built["sections"].values():
            for method in section["methods"].values():
                for hint in method["models"].values():
                    status_counts[hint["status"]] += 1

    payload = {
        "schema_version": "assisted_method_hints.v1",
        "annotation_mode": "method_assisted_review",
        "source_manifest_hash": codebook["manifest_hash"],
        "models": list(MODELS),
        "methods": list(METHODS),
        "cases": cases,
        "summary": {
            "presentations": len(cases),
            "conditions": dict(sorted(condition_counts.items())),
            "hint_statuses": dict(sorted(status_counts.items())),
        },
    }
    if source_update is not None:
        payload["source_update"] = source_update
    payload, changed = save_hint_pack(payload, args.output)
    print(json.dumps({**payload["summary"], "changed": changed, "hint_pack_hash": payload["hint_pack_hash"], "source_update": payload.get("source_update")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

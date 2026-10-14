#!/usr/bin/env python3
"""Audit locked post-case baseline coverage without calling any model API.

The script joins a frozen post-candidate manifest to the stable 80-case catalog,
then verifies the stored one-shot, SA-MCGS, and rebuttal LEA artifacts by exact
SCC clause IDs and injection identity.  Numeric Tarjan ``scc_id`` is diagnostic
only and is never used as a join key.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
DEFAULT_PLAN = REPO_ROOT / "2026NAACL/SA-MCGS/validation/identity_stage2_80/case_plan.json"
DEFAULT_REPLAY = (
    REPO_ROOT
    / "2026NAACL/SA-MCGS/experiments/stage2_paired_replay_80case_identity_v1_final/replay_manifest.json"
)
DEFAULT_MAIN_MANIFEST = REPO_ROOT / "experiments/main_experiment/MANIFEST.json"
DEFAULT_LEA_DIR = (
    REPO_ROOT
    / "emnlp2026_discussion/baseline_runs/lea_available160_gpt4o_gemini_w4_cc4_20260712_0048/results"
)
DEFAULT_MODELS = ("gpt-4o", "gemini-2.5-pro")
METHODS = ("one-shot", "sa-mcgs", "lea")
TEMPLATES = (
    "direct_mutex",
    "handoff_invariant",
    "temporal_gate",
    "condition_trigger",
)
DOMAINS = ("debian", "sec_ex21", "bgb", "cuad")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def first(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def list_value(value: Any) -> list[str] | None:
    if value in (None, ""):
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    text = str(value).strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
    separator = ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    payload = read_json(path)
    if isinstance(payload, dict):
        for key in ("post_cases", "selected_cases", "candidates", "cases", "rows"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ValueError(f"Manifest is not a list of objects: {path}")
    return [dict(row) for row in payload]


CASE_PATTERN = re.compile(
    r"(?P<domain>debian|sec_ex21|bgb|cuad)[_-]?(?P<size>\d+).*?"
    r"(?P<template>direct_mutex|handoff_invariant|temporal_gate|condition_trigger)"
)


def normalized_candidate(row: dict[str, Any], position: int) -> dict[str, Any]:
    candidate_id = str(
        first(
            row,
            "audit_post_id",
            "candidate_id",
            "post_case_id",
            "presentation_id",
            "canonical_case_id",
            "main_case_id",
            "case_id",
            "id",
        )
        or f"candidate_{position:03d}"
    )
    domain = first(row, "domain", "canonical_domain", "source_domain")
    size = integer(first(row, "scc_size", "canonical_scc_size", "source_scc_size", "size"))
    template = first(
        row,
        "template",
        "canonical_template",
        "injection_template",
        "conflict_family",
        "requested_conflict_family",
    )
    parsed = CASE_PATTERN.search(candidate_id)
    if parsed:
        domain = domain or parsed.group("domain")
        size = size or int(parsed.group("size"))
        template = template or parsed.group("template")
    return {
        "candidate_id": candidate_id,
        "domain": str(domain or ""),
        "scc_size": size,
        "template": str(template or ""),
        # Source physical identity is for clustering.  It must not be replaced
        # by planned_scc_fingerprint, which includes injected text/template.
        "source_physical_fingerprint": first(
            row,
            "source_physical_fingerprint",
            "source_physical_uid",
            "physical_scc_uid",
        ),
        "source_clause_ids": list_value(
            first(
                row,
                "source_clause_ids",
                "original_clause_ids",
                "ordered_clause_ids",
                "planned_scc_clause_ids",
            )
        ),
        "variant_case_uid": first(
            row,
            "variant_case_uid",
            "post_case_uid",
            "stable_case_uid",
            "case_uid",
        ),
        "variant_fingerprint": first(
            row,
            "variant_fingerprint",
            "post_variant_fingerprint",
            "planned_scc_fingerprint",
        ),
        "canonical_case_id": first(
            row,
            "canonical_case_id",
            "main_case_id",
            "source_case_id",
        ),
        "main_case_order": integer(first(row, "main_case_order", "canonical_case_order")),
        "raw": row,
    }


def load_catalog(plan_path: Path, replay_path: Path) -> list[dict[str, Any]]:
    plan = read_json(plan_path)
    if not isinstance(plan, list):
        raise ValueError(f"Stable case plan is not a list: {plan_path}")
    replay_by_id: dict[str, dict[str, Any]] = {}
    if replay_path.exists():
        replay = read_json(replay_path)
        replay_by_id = {str(row.get("case_id")): row for row in replay if isinstance(row, dict)}
    result: list[dict[str, Any]] = []
    for source in plan:
        row = dict(source)
        replay_row = replay_by_id.get(str(row.get("case_id")), {})
        row["source_physical_uid"] = replay_row.get("physical_scc_uid")
        result.append(row)
    return result


def catalog_indexes(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    indexes: dict[str, Any] = {
        "case_id": {},
        "case_uid": {},
        "fingerprint": {},
        "case_order": {},
        "key": defaultdict(list),
    }
    for row in catalog:
        indexes["case_id"][str(row.get("case_id"))] = row
        indexes["case_uid"][str(row.get("case_uid"))] = row
        indexes["fingerprint"][str(row.get("planned_scc_fingerprint"))] = row
        indexes["case_order"][integer(row.get("case_order"))] = row
        key = (str(row.get("domain")), integer(row.get("scc_size")), str(row.get("template")))
        indexes["key"][key].append(row)
    return indexes


def match_candidate(candidate: dict[str, Any], indexes: dict[str, Any]) -> tuple[dict[str, Any], str]:
    lookups = (
        ("case_order", candidate.get("main_case_order"), "explicit_main_case_order"),
        ("case_uid", candidate.get("variant_case_uid"), "variant_case_uid"),
        ("case_id", candidate.get("canonical_case_id"), "canonical_case_id"),
        ("fingerprint", candidate.get("variant_fingerprint"), "variant_fingerprint"),
    )
    for index_name, value, reason in lookups:
        if value not in (None, "") and value in indexes[index_name]:
            return indexes[index_name][value], reason
    key = (candidate["domain"], candidate["scc_size"], candidate["template"])
    matches = indexes["key"].get(key, [])
    if len(matches) != 1:
        raise ValueError(
            f"Candidate {candidate['candidate_id']} has {len(matches)} stable-plan matches for {key}"
        )
    return matches[0], "unique_domain_size_template"


def result_injection(row: dict[str, Any], requested_family: str) -> dict[str, Any]:
    return {
        "seed": int(row.get("inject_seed") or 42),
        "profile": row.get("inject_profile") or "memory_stress",
        "profile_version": row.get("inject_profile_version"),
        "requested_conflict_family": requested_family,
        "conflict_family": row.get("injected_conflict_family"),
        "conflict_severity": row.get("injected_conflict_severity"),
        "conflict_template": row.get("injected_conflict_template"),
        "root_node": row.get("injected_node"),
        "witness_node": row.get("injected_witness_node"),
        "witness_distance": row.get("injected_witness_distance"),
        "bridge_node": row.get("injected_bridge_node"),
        "bridge_distance": row.get("injected_bridge_distance"),
        "risk_nodes": list(row.get("injected_risk_nodes") or []),
        "evidence_nodes": list(row.get("injected_evidence_nodes") or []),
        "affected_nodes": list(row.get("injected_affected_nodes") or []),
    }


def validate_identity(row: dict[str, Any], planned: dict[str, Any]) -> tuple[bool, str]:
    problems: list[str] = []
    expected_ids = list(planned.get("planned_scc_clause_ids") or [])
    actual_ids = list(row.get("scc_clause_ids") or [])
    if actual_ids != expected_ids:
        problems.append("scc_clause_ids")
    for field, expected in (
        ("domain", planned.get("domain")),
        ("model", row.get("model")),
        ("conflict_family", planned.get("template")),
    ):
        if field == "conflict_family":
            actual = row.get("injected_conflict_family")
        else:
            actual = row.get(field)
        if actual != expected:
            problems.append(field)
    expected_injection = planned.get("planned_injection_identity") or {}
    actual_injection = result_injection(row, str(planned.get("template") or ""))
    for key, expected in expected_injection.items():
        if actual_injection.get(key) != expected:
            problems.append(f"injection.{key}")
    return not problems, ";".join(sorted(set(problems))) or "exact"


def resolve_result_file(raw_path: str) -> Path:
    path = Path(raw_path)
    local = REPO_ROOT / "experiments/cross_domain/results" / path.name
    if local.exists():
        return local
    if path.exists():
        return path.resolve()
    return local


def target_key(row: dict[str, Any]) -> tuple[str, int | None, str]:
    return (str(row.get("domain")), integer(row.get("scc_size")), str(row.get("template")))


def load_main_coverage(
    manifest_path: Path,
    catalog_by_key: dict[tuple[str, int | None, str], list[dict[str, Any]]],
) -> dict[tuple[str, int, str, str, str], dict[str, Any]]:
    manifest = read_json(manifest_path)
    output: dict[tuple[str, int, str, str, str], dict[str, Any]] = {}
    for spec in manifest.get("canonical_status_files", []):
        status_path = (manifest_path.parent / spec["path"]).resolve()
        status = read_json(status_path)
        profile_filter = spec.get("profile_filter")
        for task in status.get("tasks", []):
            if task.get("status") != "done":
                continue
            basename = Path(str(task.get("result_file") or "")).name
            task_profile = task.get("compression_profile")
            if profile_filter and task_profile and task_profile != profile_filter:
                continue
            # Old locked runs have no explicit profile and are the canonical
            # current profile. Gemini paired jobs encode current/balanced here.
            if profile_filter and not task_profile and "_b60_balanced_" in basename:
                continue
            key3 = (str(task.get("domain")), integer(task.get("size")), str(task.get("template")))
            plans = catalog_by_key.get(key3, [])
            if len(plans) != 1:
                continue
            planned = plans[0]
            result_path = resolve_result_file(str(task.get("result_file") or ""))
            if not result_path.exists():
                continue
            payload = read_json(result_path)
            if not isinstance(payload, list):
                continue
            exact_sa_by_model: dict[str, bool] = {}
            for row in payload:
                if row.get("method") == "sa-mcgs":
                    exact_sa_by_model[str(row.get("model"))] = validate_identity(row, planned)[0]
            for row in payload:
                raw_method = str(row.get("method"))
                if raw_method not in ("naive", "sa-mcgs"):
                    continue
                model = str(row.get("model"))
                method = "one-shot" if raw_method == "naive" else "sa-mcgs"
                exact, detail = validate_identity(row, planned)
                inherited = False
                if raw_method == "naive" and row.get("error") and not row.get("scc_clause_ids"):
                    other_problems = [
                        problem
                        for problem in detail.split(";")
                        if problem and problem != "scc_clause_ids"
                    ]
                    exact = exact_sa_by_model.get(model, False) and not other_problems
                    inherited = exact
                    detail = "paired_sa_clause_identity" if exact else ";".join(other_problems) or detail
                output[(key3[0], int(key3[1]), key3[2], model, method)] = {
                    "identity_exact": exact,
                    "identity_detail": detail,
                    "strict_invalid_output": bool(row.get("error")),
                    "identity_inherited_from_paired_sa": inherited,
                    "source_file": str(result_path),
                    "actual_scc_id_diagnostic": row.get("scc_id"),
                    "actual_scc_size": row.get("scc_size"),
                }
    return output


LEA_FILE_PATTERN = re.compile(
    r"^\d+_(?P<model>.+?)_(?P<domain>debian|sec_ex21|bgb|cuad)"
    r"(?P<size>\d+)_scc_\d+_(?P<template>direct_mutex|handoff_invariant|temporal_gate|condition_trigger)"
    r"__lea\.json$"
)


def load_lea_coverage(
    lea_dirs: Iterable[Path],
    catalog_by_key: dict[tuple[str, int | None, str], list[dict[str, Any]]],
) -> dict[tuple[str, int, str, str, str], dict[str, Any]]:
    output: dict[tuple[str, int, str, str, str], dict[str, Any]] = {}
    for lea_dir in lea_dirs:
        for path in sorted(lea_dir.glob("*__lea.json")):
            match = LEA_FILE_PATTERN.match(path.name)
            if not match:
                continue
            domain = match.group("domain")
            size = int(match.group("size"))
            template = match.group("template")
            model = match.group("model")
            key3 = (domain, size, template)
            plans = catalog_by_key.get(key3, [])
            if len(plans) != 1:
                continue
            row = read_json(path)
            exact, detail = validate_identity(row, plans[0])
            artifact_key = (domain, size, template, model, "lea")
            artifact = {
                "identity_exact": exact,
                "identity_detail": detail,
                "strict_invalid_output": bool(row.get("cost_audit_error")),
                "identity_inherited_from_paired_sa": False,
                "source_file": str(path),
                "actual_scc_id_diagnostic": row.get("scc_id"),
                "actual_scc_size": row.get("scc_size"),
            }
            previous = output.get(artifact_key)
            if previous is None:
                output[artifact_key] = artifact
                continue
            if Path(str(previous["source_file"])).resolve() == path.resolve():
                continue
            if exact and not previous["identity_exact"]:
                output[artifact_key] = artifact
                continue
            if previous["identity_exact"] and not exact:
                continue
            status = "exact" if exact else "identity-mismatched"
            raise ValueError(
                f"Multiple {status} LEA artifacts for {artifact_key}: "
                f"{previous['source_file']} and {path}"
            )
    return output


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_summary(summary: dict[str, Any], manifest_path: Path) -> str:
    lines = [
        "# Baseline coverage audit",
        "",
        f"- Candidate manifest: `{manifest_path}`",
        f"- Post variants: **{summary['candidate_count']}**",
        f"- Models: `{', '.join(summary['models'])}`",
        f"- Coverage cells: **{summary['cell_count']}**",
        f"- Cells requiring rerun: **{summary['rerun_cell_count']}**",
        "",
        "| model | method | available exact | strict invalid (kept) | identity mismatch | missing | rerun |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for model in summary["models"]:
        for method in METHODS:
            counts = summary["by_model_method"].get(f"{model}|{method}", {})
            lines.append(
                f"| {model} | {method} | {counts.get('available_exact', 0)} | "
                f"{counts.get('available_strict_invalid', 0)} | "
                f"{counts.get('identity_mismatch', 0)} | {counts.get('missing', 0)} | "
                f"{counts.get('rerun', 0)} |"
            )
    lines.extend(
        [
            "",
            "Interpretation: a locked one-shot invalid output remains a valid strict outcome and is not rerun. "
            "Only missing or identity-mismatched cells enter `rerun_scope.csv`. Numeric Tarjan `scc_id` is diagnostic only.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="Frozen 36-post CSV or JSON manifest")
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS), help="Comma-separated model names")
    parser.add_argument("--case-plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--replay-manifest", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--main-manifest", type=Path, default=DEFAULT_MAIN_MANIFEST)
    parser.add_argument(
        "--lea-dir",
        type=Path,
        action="append",
        default=None,
        help="LEA result directory; repeat to merge vetted legacy and new runs",
    )
    parser.add_argument("--output-dir", type=Path, default=SCRIPT_DIR)
    args = parser.parse_args()
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    lea_dirs = args.lea_dir or [DEFAULT_LEA_DIR]
    rows = load_rows(args.manifest)
    candidates = [normalized_candidate(row, index) for index, row in enumerate(rows, 1)]
    catalog = load_catalog(args.case_plan, args.replay_manifest)
    indexes = catalog_indexes(catalog)
    catalog_by_key = indexes["key"]
    resolved: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for candidate in candidates:
        planned, match_rule = match_candidate(candidate, indexes)
        source_ids = candidate.get("source_clause_ids")
        if source_ids and set(source_ids) != set(planned.get("planned_scc_clause_ids") or []):
            raise ValueError(f"Source clause IDs disagree for {candidate['candidate_id']}")
        source_uid = candidate.get("source_physical_fingerprint")
        planned_uid = planned.get("source_physical_uid")
        if source_uid and str(source_uid).startswith("psc-v1-") and source_uid != planned_uid:
            raise ValueError(f"Source physical UID disagrees for {candidate['candidate_id']}")
        resolved.append((candidate, planned, match_rule))

    duplicate_keys = Counter(
        (str(plan.get("source_physical_uid")), str(plan.get("template"))) for _, plan, _ in resolved
    )
    duplicates = [key for key, count in duplicate_keys.items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate post variants in candidate manifest: {duplicates}")

    main_coverage = load_main_coverage(args.main_manifest, catalog_by_key)
    lea_coverage = load_lea_coverage(lea_dirs, catalog_by_key)
    coverage = {**main_coverage, **lea_coverage}
    output_rows: list[dict[str, Any]] = []
    for candidate, planned, match_rule in resolved:
        key3 = target_key(planned)
        for model in models:
            for method in METHODS:
                artifact = coverage.get((key3[0], int(key3[1]), key3[2], model, method))
                if artifact is None:
                    status = "missing"
                    rerun = True
                    reason = "no_stored_artifact"
                    artifact = {}
                elif not artifact["identity_exact"]:
                    status = "identity_mismatch"
                    rerun = True
                    reason = artifact.get("identity_detail") or "identity_mismatch"
                elif artifact.get("strict_invalid_output") and method == "one-shot":
                    status = "available_strict_invalid"
                    rerun = False
                    reason = "locked_strict_outcome_keep"
                else:
                    status = "available_exact"
                    rerun = False
                    reason = ""
                output_rows.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "canonical_case_id": planned.get("case_id"),
                        "main_case_order": planned.get("case_order"),
                        "source_physical_uid": candidate.get("source_physical_fingerprint")
                        or planned.get("source_physical_uid"),
                        "variant_case_uid": planned.get("case_uid"),
                        "variant_fingerprint": planned.get("planned_scc_fingerprint"),
                        "domain": key3[0],
                        "scc_size": key3[1],
                        "template": key3[2],
                        "model": model,
                        "method": method,
                        "coverage_status": status,
                        "needs_rerun": str(rerun).lower(),
                        "rerun_reason": reason,
                        "identity_match_rule": match_rule,
                        "identity_detail": artifact.get("identity_detail", ""),
                        "actual_scc_id_diagnostic": artifact.get("actual_scc_id_diagnostic", ""),
                        "actual_scc_size": artifact.get("actual_scc_size", ""),
                        "source_file": artifact.get("source_file", ""),
                    }
                )

    fields = list(output_rows[0]) if output_rows else []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "baseline_coverage.csv", output_rows, fields)
    rerun_rows = [row for row in output_rows if row["needs_rerun"] == "true"]
    write_csv(args.output_dir / "rerun_scope.csv", rerun_rows, fields)
    by_model_method: dict[str, dict[str, int]] = {}
    for model in models:
        for method in METHODS:
            selected = [row for row in output_rows if row["model"] == model and row["method"] == method]
            counts = Counter(row["coverage_status"] for row in selected)
            counts["rerun"] = sum(row["needs_rerun"] == "true" for row in selected)
            by_model_method[f"{model}|{method}"] = dict(counts)
    summary = {
        "candidate_manifest": str(args.manifest.resolve()),
        "candidate_count": len(candidates),
        "models": models,
        "methods": list(METHODS),
        "lea_dirs": [str(path.resolve()) for path in lea_dirs],
        "cell_count": len(output_rows),
        "rerun_cell_count": len(rerun_rows),
        "by_model_method": by_model_method,
        "identity_policy": {
            "source_cluster": "source_physical_fingerprint/physical_scc_uid (injection-text-independent)",
            "variant_match": "explicit stable case identity; unique domain+size+template only as audited fallback",
            "tarjan_scc_id": "diagnostic_only",
        },
    }
    write_json(args.output_dir / "baseline_coverage_summary.json", summary)
    (args.output_dir / "baseline_coverage_summary.md").write_text(
        render_summary(summary, args.manifest), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

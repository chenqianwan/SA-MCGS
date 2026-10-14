#!/usr/bin/env python3
"""Build the frozen GPT-4o/Gemini LEA post-update scope.

The scope is derived from the structural candidate manifest, not the mutable
rerun report.  This keeps the original 48-job plan reproducible after completed
jobs disappear from ``rerun_scope.csv``.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
RERUN_SCOPE = (
    REPO_ROOT
    / "2026NAACL/SA-MCGS/annotation_prep/baseline_audit/rerun_scope.csv"
)
CANDIDATES = (
    REPO_ROOT
    / "2026NAACL/SA-MCGS/annotation_prep/candidates/selected_post_36.json"
)
CASE_COMPOSITION = REPO_ROOT / "emnlp2026_discussion/case_composition.csv"
TARGET_MODELS = ("gpt-4o", "gemini-2.5-pro")
GEMINI_REPAIR_CANDIDATE_IDS = {
    "post_001",
    "post_002",
    "post_003",
    "post_004",
    "post_005",
    "post_007",
    "post_008",
    "post_009",
    "post_010",
    "post_011",
    "post_012",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def key(row: dict[str, str]) -> tuple[str, str, int, str]:
    return (
        row["model"],
        row["domain"],
        int(row["scc_size"]),
        row["template"],
    )


def main() -> int:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    if not isinstance(candidates, list) or len(candidates) != 36:
        raise RuntimeError(f"Expected 36 frozen post candidates, found {len(candidates)}")

    # Frozen stable-identity audit:
    # - GPT requires identity-safe replay on all 12 SEC variants.
    # - Gemini requires identity-safe replay on 11 of those 12 SEC variants;
    #   post_006 already has an exact legacy artifact.
    targets: list[dict[str, object]] = []
    for candidate in candidates:
        if candidate["domain"] == "sec_ex21":
            targets.append(
                {
                    "candidate": candidate,
                    "model": "gpt-4o",
                    "reason": "legacy_lea_identity_mismatch_repair",
                }
            )
        if candidate["audit_post_id"] in GEMINI_REPAIR_CANDIDATE_IDS:
            targets.append(
                {
                    "candidate": candidate,
                    "model": "gemini-2.5-pro",
                    "reason": "legacy_lea_identity_mismatch_repair",
                }
            )
    if len(targets) != 23:
        raise RuntimeError(f"Expected 23 frozen LEA post jobs, found {len(targets)}")

    composition = read_csv(CASE_COMPOSITION)
    fields = list(composition[0])
    by_key: dict[tuple[str, str, int, str], list[dict[str, str]]] = {}
    for row in composition:
        by_key.setdefault(key(row), []).append(row)

    rows: list[dict[str, str]] = []
    manifest_rows = []
    seen: set[tuple[str, str, int, str]] = set()
    for target in targets:
        candidate = target["candidate"]
        target_row = {
            "model": str(target["model"]),
            "domain": str(candidate["domain"]),
            "scc_size": str(candidate["source_scc_size"]),
            "template": str(candidate["template"]),
        }
        audit_key = key(target_row)
        matches = by_key.get(audit_key, [])
        if len(matches) != 1:
            raise RuntimeError(f"Expected one case-composition row for {audit_key}, found {len(matches)}")
        if audit_key in seen:
            raise RuntimeError(f"Duplicate LEA target: {audit_key}")
        seen.add(audit_key)
        rows.append(matches[0])
        manifest_rows.append(
            {
                "candidate_id": candidate["audit_post_id"],
                "canonical_case_id": candidate["canonical_case_id"],
                "variant_case_uid": candidate["post_case_uid"],
                "model": target_row["model"],
                "domain": target_row["domain"],
                "scc_size": int(target_row["scc_size"]),
                "template": target_row["template"],
                "reason": target["reason"],
            }
        )

    paired = sorted(
        zip(rows, manifest_rows),
        key=lambda pair: (
            TARGET_MODELS.index(pair[1]["model"]),
            pair[1]["domain"],
            pair[1]["scc_size"],
            pair[1]["template"],
            pair[1]["candidate_id"],
        ),
    )
    rows = [pair[0] for pair in paired]
    manifest_rows = [pair[1] for pair in paired]

    gemini_positions = [
        index for index, row in enumerate(manifest_rows) if row["model"] == "gemini-2.5-pro"
    ]
    smoke_index = min(
        gemini_positions,
        key=lambda index: (
            manifest_rows[index]["scc_size"],
            manifest_rows[index]["domain"],
            manifest_rows[index]["template"],
            manifest_rows[index]["candidate_id"],
        ),
    )
    smoke_rows = [rows[smoke_index]]
    remaining_rows = [
        row
        for index, (row, item) in enumerate(zip(rows, manifest_rows))
        if item["model"] == "gemini-2.5-pro" and index != smoke_index
    ]
    gpt_rows = [
        row for row, item in zip(rows, manifest_rows) if item["model"] == "gpt-4o"
    ]
    gemini_rows = [
        row for row, item in zip(rows, manifest_rows) if item["model"] == "gemini-2.5-pro"
    ]

    full_path = HERE / "post_lea_23_cases.csv"
    smoke_path = HERE / "post_lea_gemini_smoke_1_case.csv"
    remaining_path = HERE / "post_lea_gemini_remaining10_cases.csv"
    gpt_path = HERE / "post_lea_gpt12_cases.csv"
    gemini_path = HERE / "post_lea_gemini11_cases.csv"
    write_csv(full_path, rows, fields)
    write_csv(smoke_path, smoke_rows, fields)
    write_csv(remaining_path, remaining_rows, fields)
    write_csv(gpt_path, gpt_rows, fields)
    write_csv(gemini_path, gemini_rows, fields)

    manifest = {
        "scope_version": "arr_oct2026_lea_post_gpt_gemini_v2",
        "models": list(TARGET_MODELS),
        "job_count": len(rows),
        "by_model": {
            model: sum(item["model"] == model for item in manifest_rows)
            for model in TARGET_MODELS
        },
        "smoke": manifest_rows[smoke_index],
        "jobs": manifest_rows,
        "inputs": {
            "candidate_manifest": str(CANDIDATES.relative_to(REPO_ROOT)),
            "latest_rerun_scope": str(RERUN_SCOPE.relative_to(REPO_ROOT)),
            "case_composition": str(CASE_COMPOSITION.relative_to(REPO_ROOT)),
        },
        "outputs": {
            full_path.name: sha256(full_path),
            smoke_path.name: sha256(smoke_path),
            remaining_path.name: sha256(remaining_path),
            gpt_path.name: sha256(gpt_path),
            gemini_path.name: sha256(gemini_path),
        },
    }
    (HERE / "post_lea_gpt_gemini_scope.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"jobs": len(rows), "by_model": manifest["by_model"], "smoke": manifest["smoke"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

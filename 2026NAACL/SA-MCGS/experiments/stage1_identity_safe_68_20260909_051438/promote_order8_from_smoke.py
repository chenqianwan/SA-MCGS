#!/usr/bin/env python3
"""Non-selectively promote the pre-frozen order-8 smoke quartet into formal.

The promotion is allowed only when every execution-relevant protocol field and
the order-8 case/prompt hashes are identical.  It records source hashes before
adding provenance to the formal copies; it never edits the smoke artifacts.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


RUN_ROOT = Path(__file__).resolve().parent
SMOKE = RUN_ROOT / "smoke"
FORMAL = RUN_ROOT / "formal"
ORDER = 8
VARIANTS = [
    "full-sa-mcgs-rerun",
    "no-relation-first-memory",
    "no-critical-pair-ledger-revisit",
    "random-local-window-selection",
]
RANDOM_SEED_BASE = 8229
RANDOM_SEED = RANDOM_SEED_BASE + ORDER * 1009
EQUIVALENT_PROTOCOL_FIELDS = [
    "model",
    "model_id",
    "budget_rollouts",
    "window_size",
    "internal_concurrency",
    "case_concurrency",
    "effective_max_api_concurrency",
    "compression_profile",
    "injection",
    "identity_policy",
    "invalid_policy",
    "retry_policy",
    "hard_budget_usd_including_smoke_and_formal",
    "prompt_schema_provenance",
    "config_sha256",
    "config_diffs_vs_full",
    "code_sha256",
    "paired_control_decision",
]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def by_order(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [row for row in rows if int(row["case_order"]) == ORDER]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one order-{ORDER} record, found {len(matches)}")
    return matches[0]


def result_by_variant(directory: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted((directory / "results").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("case_order", -1)) == ORDER:
            variant = payload.get("ablation_variant")
            if variant in found:
                raise RuntimeError(f"Duplicate order-{ORDER} variant: {variant}")
            found[variant] = path
    return found


def main() -> None:
    smoke_protocol = json.loads((SMOKE / "protocol.json").read_text(encoding="utf-8"))
    formal_protocol = json.loads((FORMAL / "protocol.json").read_text(encoding="utf-8"))
    smoke_case = by_order(json.loads((SMOKE / "case_plan.json").read_text(encoding="utf-8")))
    formal_case = by_order(json.loads((FORMAL / "case_plan.json").read_text(encoding="utf-8")))
    smoke_prompt = by_order(smoke_protocol["prompt_examples"])
    formal_prompt = by_order(formal_protocol["prompt_examples"])

    checks: dict[str, bool] = {
        f"protocol.{field}": smoke_protocol.get(field) == formal_protocol.get(field)
        for field in EQUIVALENT_PROTOCOL_FIELDS
    }
    checks.update(
        {
            "case_plan.order8_exact": smoke_case == formal_case,
            "prompt_example.order8_exact": smoke_prompt == formal_prompt,
            "smoke_publication_use_is_diagnostic": smoke_protocol.get("publication_use")
            == "diagnostic_only",
            "formal_publication_use_is_formal": formal_protocol.get("publication_use") == "formal",
            "order8_is_prefrozen_smoke": ORDER in smoke_protocol.get("orders", []),
            "order8_is_prefrozen_formal": ORDER in formal_protocol.get("orders", []),
        }
    )

    sources = result_by_variant(SMOKE)
    checks["all_four_smoke_results_present"] = set(sources) == set(VARIANTS)
    result_audit = []
    expected_uid = formal_case["case_uid"]
    expected_fingerprint = formal_case["planned_scc_fingerprint"]
    for variant in VARIANTS:
        path = sources.get(variant)
        if path is None:
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        item_checks = {
            "case_order": int(result.get("case_order", -1)) == ORDER,
            "case_id": result.get("case_id") == formal_case["case_id"],
            "case_uid": result.get("case_uid") == expected_uid,
            "planned_fingerprint": result.get("planned_scc_fingerprint") == expected_fingerprint,
            "actual_fingerprint": (result.get("actual_case_identity") or {}).get("fingerprint")
            == expected_fingerprint,
            "variant": result.get("ablation_variant") == variant,
            "model": result.get("model") == formal_protocol["model"],
            "budget": int(result.get("budget", -1)) == int(formal_protocol["budget_rollouts"]),
            "compression_profile": result.get("mcgs_compression_profile")
            == formal_protocol["compression_profile"],
            "case_level_valid": not bool(result.get("component_ablation_error")),
        }
        if variant == "random-local-window-selection":
            events = result.get("selection_events") or []
            item_checks.update(
                {
                    "random_events_cover_budget": len(events)
                    == int(formal_protocol["budget_rollouts"]),
                    "random_mode_exact": bool(events)
                    and {event.get("mode") for event in events} == {"random_local_window"},
                    "random_seed_exact": bool(events)
                    and {event.get("random_seed") for event in events} == {RANDOM_SEED},
                }
            )
        checks[f"result.{variant}"] = all(item_checks.values())
        result_audit.append(
            {
                "variant": variant,
                "source_file": str(path),
                "source_sha256": sha256(path),
                "checks": item_checks,
            }
        )

    passed = bool(checks) and all(checks.values())
    manifest_path = FORMAL / "reuse_from_smoke_order8.json"
    manifest = {
        "manifest_version": "stage1_order8_nonselective_reuse_v1",
        "created_at": now_iso(),
        "passed": passed,
        "selection_policy": (
            "Order 8 was pre-frozen in both smoke and formal scopes. All four arms are reused as a "
            "quartet regardless of their outcomes; no result-dependent selection is permitted."
        ),
        "source_phase": "smoke",
        "target_phase": "formal",
        "case_order": ORDER,
        "random_seed_base": RANDOM_SEED_BASE,
        "derived_random_seed": RANDOM_SEED,
        "equivalent_protocol_fields": EQUIVALENT_PROTOCOL_FIELDS,
        "checks": checks,
        "results": result_audit,
    }
    write_json(manifest_path, manifest)
    if not passed:
        raise RuntimeError(f"Order-8 reuse equivalence failed; see {manifest_path}")

    target_dir = FORMAL / "results"
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in result_audit:
        source = Path(item["source_file"])
        target = target_dir / source.name
        if target.exists():
            raise RuntimeError(f"Refusing to overwrite existing formal result: {target}")
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["formal_cell_provenance"] = {
            "mode": "reused_from_smoke_nonselective_prefrozen_overlap",
            "source_phase": "smoke",
            "source_result_file": str(source),
            "source_result_sha256": item["source_sha256"],
            "reuse_manifest": str(manifest_path),
            "reused_at": now_iso(),
        }
        write_json(target, payload)

    manifest["promoted_at"] = now_iso()
    manifest["target_results"] = [
        {
            "variant": item["variant"],
            "target_file": str(target_dir / Path(item["source_file"]).name),
            "target_sha256": sha256(target_dir / Path(item["source_file"]).name),
        }
        for item in result_audit
    ]
    write_json(manifest_path, manifest)
    print(f"Promoted order-{ORDER} quartet after {len(checks)} equivalence checks: {manifest_path}")


if __name__ == "__main__":
    main()

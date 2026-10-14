#!/usr/bin/env python3
"""Recompute the bounded legacy-63 Stage-1 diagnostic from raw JSON only.

This script is deliberately offline.  The frozen legacy CSV is used only to
locate the four raw result files for each case; none of its aggregate metric
columns is consumed for estimation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
WORKSPACE_ROOT = REPO_ROOT.parents[1]
DEFAULT_PROTOCOL = SCRIPT_DIR / "frozen_protocol.json"

FULL_ARM = "full-sa-mcgs-locked"
ABLATION_ARMS = (
    "no-relation-first-memory",
    "no-critical-pair-ledger-revisit",
    "random-local-window-selection",
)


class AuditError(RuntimeError):
    """Raised when a frozen input, identity, or configuration check fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_rooted(root: str, relpath: str) -> Path:
    base = {"repo": REPO_ROOT, "workspace": WORKSPACE_ROOT}.get(root)
    if base is None:
        raise AuditError(f"Unsupported frozen input root: {root}")
    path = (base / relpath).resolve()
    require(path.is_file(), f"Missing frozen input: {path}")
    return path


def verify_lock(entry: dict[str, Any]) -> Path:
    path = resolve_rooted(str(entry["root"]), str(entry["path"]))
    actual = sha256_file(path)
    require(actual == entry["sha256"], f"Hash mismatch for {path}: {actual}")
    return path


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def physical_scc_uid(domain: str, ordered_clause_ids: list[str]) -> str:
    payload = {
        "version": "paired_core_physical_scc_v1",
        "domain": domain,
        "ordered_clause_ids": ordered_clause_ids,
    }
    return "psc-v1-" + canonical_sha256(payload).removeprefix("sha256:")


def workspace_relpath(path: Path) -> str:
    try:
        return path.resolve().relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError as exc:
        raise AuditError(f"Raw path escapes the workspace: {path}") from exc


def raw_path_from_index(value: str) -> Path:
    """Re-anchor the legacy absolute locator below the current workspace."""

    marker = "emnlp2026_discussion/component_ablation_runs/"
    normalized = value.replace("\\", "/")
    require(marker in normalized, f"Unexpected raw locator: {value}")
    suffix = marker + normalized.split(marker, 1)[1]
    path = (WORKSPACE_ROOT / suffix).resolve()
    allowed = (WORKSPACE_ROOT / "emnlp2026_discussion/component_ablation_runs").resolve()
    try:
        path.relative_to(allowed)
    except ValueError as exc:
        raise AuditError(f"Raw locator escapes frozen result root: {path}") from exc
    require(path.is_file(), f"Missing raw result: {path}")
    return path


def exact_bool(raw: dict[str, Any], field: str, cell: str) -> bool:
    require(field in raw, f"Missing raw metric {field}: {cell}")
    value = raw[field]
    require(type(value) is bool, f"Raw metric {field} is not boolean: {cell}")
    return value


def exact_list(raw: dict[str, Any], field: str, cell: str) -> list[Any]:
    value = raw.get(field)
    require(isinstance(value, list), f"Expected list {field}: {cell}")
    return value


def source_shard_for_order(
    protocol: dict[str, Any], order: int
) -> dict[str, Any]:
    matches = [
        shard
        for shard in protocol["source_shards"]
        if int(shard["orders"][0]) <= order <= int(shard["orders"][1])
    ]
    require(len(matches) == 1, f"Expected one source shard for order {order}")
    return matches[0]


def verify_source_shards(
    protocol: dict[str, Any], canonical_by_order: dict[int, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    runtime = protocol["locked_runtime"]
    expected_variants = list(ABLATION_ARMS)
    audit: dict[str, dict[str, Any]] = {}
    for shard in protocol["source_shards"]:
        root = (WORKSPACE_ROOT / shard["workspace_path"]).resolve()
        require(root.is_dir(), f"Missing source shard: {root}")
        config_path = root / "run_config.json"
        case_plan_path = root / "case_plan.json"
        require(
            sha256_file(config_path) == shard["run_config_sha256"],
            f"run_config hash mismatch: {config_path}",
        )
        require(
            sha256_file(case_plan_path) == shard["case_plan_sha256"],
            f"case_plan hash mismatch: {case_plan_path}",
        )
        config = load_json(config_path)
        start, end = map(int, shard["orders"])
        expected_orders = list(range(start, end + 1))
        checks = {
            "stage": config.get("stage") == "stage1",
            "model": config.get("model") == runtime["model"],
            "model_id": config.get("model_id") == runtime["model"],
            "budget": config.get("budget") == runtime["budget"],
            "window_size": config.get("window_size")
            == runtime["window_size_from_run_config"],
            "internal_concurrency": config.get("internal_concurrency")
            == runtime["internal_concurrency"],
            "case_concurrency": config.get("case_concurrency")
            == runtime["case_concurrency"],
            "ablation_variants_exact": config.get("variants") == expected_variants,
            "historical_full_not_in_contemporaneous_variants": FULL_ARM
            not in (config.get("variants") or []),
            "orders_exact": config.get("case_orders") == expected_orders,
        }
        require(all(checks.values()), f"Source shard config mismatch: {shard['name']}")

        shard_cases = load_json(case_plan_path)
        require(isinstance(shard_cases, list), f"Bad shard case plan: {case_plan_path}")
        require(
            [int(row["case_order"]) for row in shard_cases] == expected_orders,
            f"Shard case order mismatch: {shard['name']}",
        )
        for row in shard_cases:
            order = int(row["case_order"])
            canonical = canonical_by_order[order]
            for field in ("case_id", "domain", "scc_id", "scc_size", "model"):
                require(
                    row.get(field) == canonical.get(field),
                    f"Shard case-plan {field} mismatch: order {order}",
                )
        audit[shard["name"]] = {
            "workspace_path": shard["workspace_path"],
            "orders": expected_orders,
            "run_config_sha256": sha256_file(config_path),
            "case_plan_sha256": sha256_file(case_plan_path),
            "checks": checks,
        }
    return audit


def verify_identity_catalogs(
    case_plan: list[dict[str, Any]], replay_manifest: list[dict[str, Any]]
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    expected_orders = set(range(1, 81))
    require(len(case_plan) == 80, "Canonical identity plan must contain 80 cases")
    require(len(replay_manifest) == 80, "Physical-SCC manifest must contain 80 cases")
    canonical_by_order = {int(row["case_order"]): row for row in case_plan}
    replay_by_order = {int(row["case_order"]): row for row in replay_manifest}
    require(set(canonical_by_order) == expected_orders, "Canonical plan orders are not 1..80")
    require(set(replay_by_order) == expected_orders, "Replay manifest orders are not 1..80")
    require(len(canonical_by_order) == 80, "Duplicate canonical case order")
    require(len(replay_by_order) == 80, "Duplicate replay case order")

    for order in range(1, 81):
        case = canonical_by_order[order]
        replay = replay_by_order[order]
        require(case["case_id"] == replay["case_id"], f"Replay case mismatch: {order}")
        require(case["case_uid"] == replay["case_uid"], f"Replay UID mismatch: {order}")
        clause_ids = case.get("planned_scc_clause_ids")
        require(isinstance(clause_ids, list) and clause_ids, f"Missing SCC nodes: {order}")
        expected_physical = physical_scc_uid(str(case["domain"]), clause_ids)
        require(
            replay.get("physical_scc_uid") == expected_physical,
            f"Physical-SCC UID mismatch: {order}",
        )
    return canonical_by_order, replay_by_order


def verify_raw_identity(
    raw: dict[str, Any], case: dict[str, Any], arm: str, cell: str
) -> None:
    exact_fields = {
        "case_order": case["case_order"],
        "case_id": case["case_id"],
        "domain": case["domain"],
        "scc_id": case["scc_id"],
        "scc_size": case["scc_size"],
        "model": case["model"],
        "ablation_variant": arm,
    }
    for field, expected in exact_fields.items():
        require(raw.get(field) == expected, f"Raw {field} mismatch: {cell}")
    require(
        raw.get("scc_clause_ids") == case["planned_scc_clause_ids"],
        f"Raw ordered SCC nodes mismatch: {cell}",
    )
    injection = case["planned_injection_identity"]
    injection_map = {
        "inject_profile": "profile",
        "inject_profile_version": "profile_version",
        "injected_conflict_family": "conflict_family",
        "injected_conflict_template": "conflict_template",
        "injected_conflict_severity": "conflict_severity",
        "injected_node": "root_node",
        "injected_witness_node": "witness_node",
        "injected_bridge_node": "bridge_node",
        "injected_risk_nodes": "risk_nodes",
        "injected_evidence_nodes": "evidence_nodes",
        "injected_affected_nodes": "affected_nodes",
    }
    for raw_field, identity_field in injection_map.items():
        require(
            raw.get(raw_field) == injection.get(identity_field),
            f"Raw injection identity mismatch for {raw_field}: {cell}",
        )


def verify_raw_runtime(
    raw: dict[str, Any], arm: str, protocol: dict[str, Any], cell: str
) -> dict[str, Any]:
    runtime = protocol["locked_runtime"]
    shared = {
        "model": raw.get("model") == runtime["model"],
        "budget": raw.get("budget") == runtime["budget"],
        "internal_concurrency": raw.get("internal_concurrency")
        == runtime["internal_concurrency"],
        "case_concurrency": raw.get("case_concurrency")
        == runtime["case_concurrency"],
        "inject_profile": raw.get("inject_profile") == runtime["inject_profile"],
        "inject_profile_version": raw.get("inject_profile_version")
        == runtime["inject_profile_version"],
        "injected_conflict_severity": raw.get("injected_conflict_severity")
        == runtime["injected_conflict_severity"],
        "method": raw.get("method") == "sa-mcgs",
        "first_attempt_valid": raw.get("component_ablation_error") is None,
    }
    require(all(shared.values()), f"Shared runtime mismatch: {cell}")

    prompt = protocol["ablation_prompt_metadata"]
    prompt_fields = tuple(prompt)
    config_hash_keys = tuple(
        key for key in raw if "hash" in key.lower() or "config" in key.lower()
    )
    if arm == FULL_ARM:
        arm_checks = {
            "relation_first_enabled": raw.get("relation_first_enabled") is True,
            "historical_source_marker": raw.get("ablation_source")
            == "locked_main_experiment",
            "historical_component_ablation_budget_absent": raw.get(
                "component_ablation_budget"
            )
            is None,
            "prompt_metadata_absent": all(field not in raw for field in prompt_fields),
            "prompt_or_config_hash_absent": not config_hash_keys,
        }
        prompt_status = "historical_full_missing_prompt_and_config_hash"
    else:
        arm_checks = {
            "component_ablation_budget": raw.get("component_ablation_budget")
            == runtime["budget"],
            "prompt_metadata_exact": all(raw.get(field) == value for field, value in prompt.items())
        }
        prompt_status = "prompt_semantic_audit_hash_present_no_general_config_sha"
        if arm == "no-relation-first-memory":
            events = exact_list(raw, "selection_events", cell)
            history = exact_list(raw, "relation_probe_history", cell)
            arm_checks.update(
                {
                    "relation_first_disabled": raw.get("relation_first_enabled") is False,
                    "relation_probe_count_zero": raw.get("relation_probe_count") == 0,
                    "relation_history_empty": history == [],
                    "selection_mode_ucb_only": bool(events)
                    and {event.get("mode") for event in events} == {"ucb"},
                }
            )
        elif arm == "no-critical-pair-ledger-revisit":
            history = exact_list(raw, "relation_probe_history", cell)
            arm_checks.update(
                {
                    "relation_first_enabled": raw.get("relation_first_enabled") is True,
                    "critical_pair_ledger_empty": exact_list(
                        raw, "critical_pair_ledger_rows", cell
                    )
                    == [],
                    "critical_pair_revisit_empty": exact_list(
                        raw, "critical_pair_revisit_history", cell
                    )
                    == [],
                    "critical_pair_locked_empty": exact_list(
                        raw, "critical_pair_locked_edges", cell
                    )
                    == [],
                    "critical_pair_candidates_empty": exact_list(
                        raw, "critical_pair_candidate_edges", cell
                    )
                    == [],
                    "no_revisit_event": all(
                        event.get("mode") != "critical_pair_revisit" for event in history
                    ),
                }
            )
        elif arm == "random-local-window-selection":
            events = exact_list(raw, "selection_events", cell)
            history = exact_list(raw, "relation_probe_history", cell)
            arm_checks.update(
                {
                    "relation_first_flag_retained": raw.get("relation_first_enabled") is True,
                    "relation_probe_count_zero": raw.get("relation_probe_count") == 0,
                    "relation_history_empty": history == [],
                    "selection_mode_random_only": bool(events)
                    and {event.get("mode") for event in events}
                    == {"random_local_window"},
                    "random_seed_recorded": all(
                        isinstance(event.get("random_seed"), int) for event in events
                    ),
                }
            )
        else:
            raise AuditError(f"Unexpected arm: {arm}")
    require(all(arm_checks.values()), f"Effective arm config mismatch: {cell}")
    return {
        "shared_checks": shared,
        "arm_checks": arm_checks,
        "prompt_config_status": prompt_status,
        "prompt_semantic_audit_hash": raw.get("prompt_semantic_audit_hash"),
    }


def mean(values: Iterable[float]) -> float:
    materialized = list(values)
    require(bool(materialized), "Cannot average an empty sequence")
    return sum(materialized) / len(materialized)


def summarize(
    case_rows: list[dict[str, Any]], arms: list[str]
) -> list[dict[str, Any]]:
    metrics = ("root_at_3", "risk_any", "risk_all")
    absolute: dict[str, dict[str, tuple[float, float]]] = defaultdict(dict)
    for arm in arms:
        rows = [row for row in case_rows if row["variant_key"] == arm]
        require(len(rows) == 63, f"Expected 63 raw rows for {arm}")
        sccs = sorted({str(row["physical_scc_uid"]) for row in rows})
        require(len(sccs) == 17, f"Expected 17 source SCCs for {arm}")
        for metric in metrics:
            case_mean = mean(float(row[metric]) for row in rows)
            within_scc = [
                mean(
                    float(row[metric])
                    for row in rows
                    if row["physical_scc_uid"] == source_uid
                )
                for source_uid in sccs
            ]
            absolute[arm][metric] = (case_mean, mean(within_scc))

    output: list[dict[str, Any]] = []
    for arm in arms:
        rows = [row for row in case_rows if row["variant_key"] == arm]
        result: dict[str, Any] = {
            "variant_key": arm,
            "comparison_scope": (
                "historical_full_absolute_diagnostic"
                if arm == FULL_ARM
                else "vs_historical_full_diagnostic_only"
            ),
            "prompt_config_identity_status": rows[0]["prompt_config_identity_status"],
            "n_cases": len(rows),
            "n_valid_cases": sum(int(row["valid"]) for row in rows),
            "n_source_scc": len({row["physical_scc_uid"] for row in rows}),
        }
        for metric in metrics:
            case_value, scc_value = absolute[arm][metric]
            full_case, full_scc = absolute[FULL_ARM][metric]
            result[f"{metric}_case_weighted_mean"] = case_value
            result[f"{metric}_source_scc_equal_mean"] = scc_value
            result[f"{metric}_delta_vs_historical_full_case_diagnostic"] = (
                None if arm == FULL_ARM else case_value - full_case
            )
            result[f"{metric}_delta_vs_historical_full_scc_diagnostic"] = (
                None if arm == FULL_ARM else scc_value - full_scc
            )
        output.append(result)
    return output


def markdown_report(
    table: list[dict[str, Any]], excluded: list[int], cluster_sizes: Counter[int]
) -> str:
    def pct(value: float | None) -> str:
        return "—" if value is None else f"{100.0 * value:.1f}%"

    lines = [
        "# Stage-1 legacy 63-case 零 API 诊断附录",
        "",
        "## 边界",
        "",
        "本附录固定排除 identity-safe 重跑覆盖的 17 个 order：",
        f"`{','.join(map(str, excluded))}`。剩余 63 个历史 case 仅作为独立 legacy 证据保存；",
        "不能与本次同期修复的 17 个 SEC case 拼接成新的 80-case headline。全程只读历史 raw JSON，",
        "没有调用模型或任何付费 API。",
        "",
        "历史 Full raw 没有 prompt/config hash，且三个 shard 的 `run_config.json` 只列出三条",
        "同期 ablation arm、未列出 Full。因此，即便四臂 raw case/injection/source-SCC 身份逐格一致，",
        "任何 `vs Full` 差值仍只属于 diagnostic，不是严格同期 paired control 结论。",
        "",
        "## 描述结果",
        "",
        "每臂均为 63/63 有效 case、17 个 physical/source SCC。`case` 为 63-case 普通均值；",
        "`SCC-eq` 为先在 SCC 内平均、再对 17 个 source SCC 等权平均。",
        "",
        "| arm | Root@3 case / SCC-eq | Risk-any case / SCC-eq | Risk-all case / SCC-eq |",
        "|---|---:|---:|---:|",
    ]
    for row in table:
        lines.append(
            "| {arm} | {r_case} / {r_scc} | {a_case} / {a_scc} | {l_case} / {l_scc} |".format(
                arm=row["variant_key"],
                r_case=pct(row["root_at_3_case_weighted_mean"]),
                r_scc=pct(row["root_at_3_source_scc_equal_mean"]),
                a_case=pct(row["risk_any_case_weighted_mean"]),
                a_scc=pct(row["risk_any_source_scc_equal_mean"]),
                l_case=pct(row["risk_all_case_weighted_mean"]),
                l_scc=pct(row["risk_all_source_scc_equal_mean"]),
            )
        )
    lines.extend(
        [
            "",
            "source-SCC case 数分布："
            + "，".join(f"{count} 个 SCC×{size} cases" for size, count in sorted(cluster_sizes.items()))
            + "。这里不计算 CI 或显著性检验。",
            "",
            "## 可复跑与审计",
            "",
            "```bash",
            "cd /Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS",
            "python3 experiments/stage1_legacy63_diagnostic/build_legacy63_diagnostic.py",
            "```",
            "",
            "`legacy63_case_metrics.csv` 的每一行都携带 raw 文件路径和 SHA-256；三项数值分别直接读取",
            "raw 的 `root_top3_hit`、`core_evidence_contains_any_risk_node` 和",
            "`core_evidence_contains_all_risk_nodes`。旧 summary 只消费 case/order/arm/result path/subset",
            "五个 locator 字段，旧 summary 的 metric/aggregate 列没有参与估计。输入锁、identity 检查、",
            "配置检查与限制见 `legacy63_summary.json` 和 `frozen_protocol.json`。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-dir", type=Path, default=SCRIPT_DIR)
    args = parser.parse_args()

    protocol_path = args.protocol.resolve()
    output_dir = args.output_dir.resolve()
    protocol = load_json(protocol_path)
    require(
        protocol.get("protocol_version") == "stage1_legacy63_diagnostic_v1",
        "Unexpected protocol version",
    )
    require(protocol.get("network_or_paid_calls_permitted") is False, "Protocol is not offline")
    protocol_sha = sha256_file(protocol_path)

    locks = protocol["input_locks"]
    locked_paths = {name: verify_lock(entry) for name, entry in locks.items()}
    require(
        locked_paths["legacy_locator_index"].read_bytes()
        == locked_paths["original_legacy_summary"].read_bytes(),
        "Repository locator index is not byte-identical to the original legacy summary",
    )

    excluded = [int(value) for value in protocol["scope"]["excluded_identity_repair_orders"]]
    require(len(excluded) == 17 and len(set(excluded)) == 17, "Excluded orders are not 17 unique values")
    repair_protocol = load_json(locked_paths["identity_repair_protocol"])
    require(repair_protocol.get("orders") == excluded, "Excluded orders drifted from repair protocol")
    included_orders = [order for order in range(1, 81) if order not in set(excluded)]
    require(len(included_orders) == protocol["scope"]["included_case_count"] == 63, "Scope mismatch")

    case_plan = load_json(locked_paths["canonical_identity_plan"])
    replay_manifest = load_json(locked_paths["physical_scc_manifest"])
    canonical_by_order, replay_by_order = verify_identity_catalogs(case_plan, replay_manifest)
    shard_audit = verify_source_shards(protocol, canonical_by_order)

    index_path = locked_paths["legacy_locator_index"]
    with index_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None, "Legacy locator index has no header")
        permitted = locks["legacy_locator_index"]["permitted_fields"]
        require(set(permitted).issubset(reader.fieldnames), "Locator fields missing from legacy index")
        index_rows = [
            {field: source_row[field] for field in permitted}
            for source_row in reader
        ]
    arms = list(protocol["scope"]["arms"])
    require(arms == [FULL_ARM, *ABLATION_ARMS], "Arm order drifted")
    require(len(index_rows) == 320, "Legacy index must contain 320 cells")
    cells = {(int(row["case_order"]), row["variant_key"]) for row in index_rows}
    require(len(cells) == 320, "Duplicate legacy index cell")
    require(
        cells == {(order, arm) for order in range(1, 81) for arm in arms},
        "Legacy index is not the complete 80x4 matrix",
    )

    selected_index = [
        row for row in index_rows if int(row["case_order"]) in set(included_orders)
    ]
    selected_index.sort(key=lambda row: (int(row["case_order"]), arms.index(row["variant_key"])))
    require(len(selected_index) == protocol["scope"]["expected_cells"] == 252, "Cell scope mismatch")

    case_rows: list[dict[str, Any]] = []
    raw_manifest_items: list[dict[str, Any]] = []
    effective_check_counts: Counter[str] = Counter()
    full_missing_prompt_hash = 0
    ablation_prompt_hash_present = 0
    for locator in selected_index:
        order = int(locator["case_order"])
        arm = locator["variant_key"]
        case = canonical_by_order[order]
        replay = replay_by_order[order]
        require(locator["case_id"] == case["case_id"], f"Index case mismatch: order {order}")
        raw_path = raw_path_from_index(locator["result_file"])
        expected_name = f"{case['case_id']}__{arm}.json"
        require(raw_path.name == expected_name, f"Unexpected raw filename: {raw_path}")
        shard = source_shard_for_order(protocol, order)
        shard_root = (WORKSPACE_ROOT / shard["workspace_path"]).resolve()
        require(raw_path.parent.parent == shard_root, f"Raw result is in wrong shard: {raw_path}")
        raw = load_json(raw_path)
        cell = f"order={order}, arm={arm}"
        require(isinstance(raw, dict), f"Raw result is not an object: {cell}")
        verify_raw_identity(raw, case, arm, cell)
        runtime_audit = verify_raw_runtime(raw, arm, protocol, cell)
        effective_check_counts[arm] += 1
        if arm == FULL_ARM:
            full_missing_prompt_hash += 1
        else:
            ablation_prompt_hash_present += int(
                raw.get("prompt_semantic_audit_hash")
                == protocol["ablation_prompt_metadata"]["prompt_semantic_audit_hash"]
            )

        raw_sha = sha256_file(raw_path)
        metrics = protocol["metrics"]
        root_at_3 = exact_bool(raw, metrics["Root@3"], cell)
        risk_any = exact_bool(raw, metrics["Risk-any"], cell)
        risk_all = exact_bool(raw, metrics["Risk-all"], cell)
        computed_physical = physical_scc_uid(str(raw["domain"]), raw["scc_clause_ids"])
        require(computed_physical == replay["physical_scc_uid"], f"Raw physical SCC mismatch: {cell}")

        relpath = workspace_relpath(raw_path)
        raw_manifest_items.append(
            {
                "case_order": order,
                "case_id": case["case_id"],
                "variant_key": arm,
                "raw_result_workspace_relpath": relpath,
                "raw_result_sha256": raw_sha,
                "raw_result_size_bytes": raw_path.stat().st_size,
            }
        )
        case_rows.append(
            {
                "case_order": order,
                "case_id": case["case_id"],
                "case_uid": case["case_uid"],
                "physical_scc_uid": computed_physical,
                "domain": case["domain"],
                "source_scc_id_diagnostic": case["source_scc_id"],
                "scc_size": case["scc_size"],
                "injected_conflict_template": raw["injected_conflict_template"],
                "variant_key": arm,
                "valid": True,
                "root_at_3": root_at_3,
                "risk_any": risk_any,
                "risk_all": risk_all,
                "root_at_3_raw_field": metrics["Root@3"],
                "risk_any_raw_field": metrics["Risk-any"],
                "risk_all_raw_field": metrics["Risk-all"],
                "identity_checks_passed": True,
                "effective_config_checks_passed": True,
                "prompt_config_identity_status": runtime_audit["prompt_config_status"],
                "prompt_semantic_audit_hash": runtime_audit["prompt_semantic_audit_hash"],
                "source_shard": shard["name"],
                "raw_result_workspace_relpath": relpath,
                "raw_result_sha256": raw_sha,
            }
        )

    raw_manifest = {
        "schema_version": "stage1_legacy63_raw_input_manifest_v1",
        "protocol_sha256": protocol_sha,
        "row_count": len(raw_manifest_items),
        "items": raw_manifest_items,
    }
    raw_manifest_path = output_dir / "raw_input_manifest.json"
    if raw_manifest_path.exists():
        require(
            load_json(raw_manifest_path) == raw_manifest,
            "Raw input manifest drifted; refusing to overwrite the frozen audit",
        )
    else:
        write_json(raw_manifest_path, raw_manifest)

    table = summarize(case_rows, arms)
    case_fields = [
        "case_order",
        "case_id",
        "case_uid",
        "physical_scc_uid",
        "domain",
        "source_scc_id_diagnostic",
        "scc_size",
        "injected_conflict_template",
        "variant_key",
        "valid",
        "root_at_3",
        "risk_any",
        "risk_all",
        "root_at_3_raw_field",
        "risk_any_raw_field",
        "risk_all_raw_field",
        "identity_checks_passed",
        "effective_config_checks_passed",
        "prompt_config_identity_status",
        "prompt_semantic_audit_hash",
        "source_shard",
        "raw_result_workspace_relpath",
        "raw_result_sha256",
    ]
    table_fields = list(table[0])
    write_csv(output_dir / "legacy63_case_metrics.csv", case_rows, case_fields)
    write_csv(output_dir / "legacy63_descriptive_table.csv", table, table_fields)

    cluster_counts = Counter(
        replay_by_order[order]["physical_scc_uid"] for order in included_orders
    )
    cluster_size_distribution = Counter(cluster_counts.values())
    summary = {
        "schema_version": "stage1_legacy63_diagnostic_summary_v1",
        "protocol_version": protocol["protocol_version"],
        "protocol_sha256": protocol_sha,
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "offline": {
            "model_calls": 0,
            "paid_api_calls": 0,
            "network_access_used": False,
        },
        "scope": {
            "included_orders": included_orders,
            "excluded_identity_repair_orders": excluded,
            "n_cases": len(included_orders),
            "n_arms": len(arms),
            "n_raw_cells": len(case_rows),
            "n_valid_raw_cells": sum(int(row["valid"]) for row in case_rows),
            "n_source_scc": len(cluster_counts),
            "source_scc_case_count_distribution": {
                str(size): count for size, count in sorted(cluster_size_distribution.items())
            },
            "domain_case_counts": dict(
                sorted(Counter(canonical_by_order[o]["domain"] for o in included_orders).items())
            ),
        },
        "provenance": {
            "input_locks": {
                name: {"path": entry["path"], "sha256": entry["sha256"]}
                for name, entry in locks.items()
            },
            "raw_input_manifest": "raw_input_manifest.json",
            "raw_input_manifest_sha256": sha256_file(raw_manifest_path),
            "legacy_locator_index_fields_consumed": locks["legacy_locator_index"][
                "permitted_fields"
            ],
            "legacy_summary_metric_fields_used_for_estimation": [],
            "metric_source": "252 locked raw JSON files",
            "metric_raw_fields": protocol["metrics"],
        },
        "identity_audit": {
            "canonical_case_uid_bound_cells": len(case_rows),
            "ordered_raw_scc_nodes_match_canonical_cells": len(case_rows),
            "raw_injection_identity_match_canonical_cells": len(case_rows),
            "recomputed_physical_scc_uid_match_manifest_cells": len(case_rows),
            "quartets_complete_and_identity_matched_cases": len(included_orders),
            "passed": True,
        },
        "configuration_audit": {
            "source_shards": shard_audit,
            "effective_arm_check_cells": dict(effective_check_counts),
            "historical_full_cells_missing_prompt_and_config_hash": full_missing_prompt_hash,
            "ablation_cells_with_expected_prompt_semantic_audit_hash": ablation_prompt_hash_present,
            "historical_full_is_contemporaneous_paired_control": False,
            "all_vs_historical_full_deltas_are_diagnostic_only": True,
            "passed_with_publication_limitation": True,
        },
        "descriptive_results": table,
        "publication_limitations": protocol["strict_publication_limitations"],
    }
    write_json(output_dir / "legacy63_summary.json", summary)
    (output_dir / "REPORT_ZH.md").write_text(
        markdown_report(table, excluded, cluster_size_distribution), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "status": "complete",
                "output_dir": str(output_dir),
                "cases": 63,
                "source_sccs": 17,
                "cells": 252,
                "raw_identity_checks_passed": True,
                "historical_full_strict_parity": False,
                "paid_or_network_calls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

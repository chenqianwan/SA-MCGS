#!/usr/bin/env python3
"""Read-only identity audit and strict summaries for the frozen LEA completion.

Missing cases never become zeros or disappear from the 320-cell coverage table.
Full-scope rates are emitted only after every cell in that group is available.
The three-method table explicitly uses the available matched subset and keeps
strict invalid outcomes as zero detection scores, with undefined compression.
This script does not import the paid runner and cannot start API calls.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
METHODS = ("one-shot", "lea", "sa-mcgs")
FIELDS = {
    "one-shot": "direct_risk_subgraph_nodes",
    "lea": "lea_risk_subgraph_nodes",
    "sa-mcgs": "core_evidence_risk_subgraph_nodes",
}
PREFIXES = {"one-shot": "direct", "lea": "lea", "sa-mcgs": "core_evidence"}
BASE_COLUMNS = [
    "model", "main_case_order", "main_case_id", "stable_case_uid", "physical_scc_uid",
    "domain", "scc_size", "scale", "template", "method", "coverage_status", "available",
    "identity_exact", "identity_basis", "source_kind", "source_file", "source_sha256",
    "prediction_field", "strict_invalid", "invalid_reason", "root_at_3", "risk_any", "risk_all",
    "compression", "selected_nodes_n", "root_node", "risk_nodes_json", "selected_nodes_json",
    "llm_calls", "prompt_tokens", "completion_tokens", "total_tokens", "runtime_sec",
    "cost_usd_at_frozen_prices", "completion_charged_or_assumed_usd", "completion_unresolved_reserved_usd",
]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_json(path: Path, value) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    fields = columns or list(dict.fromkeys(k for row in rows for k in row))
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def scale(size: int) -> str:
    return "small" if size <= 12 else "medium" if size <= 20 else "large"


def read_ledger(directory: Path) -> tuple[dict, dict]:
    """Snapshot complete JSONL records; an in-progress last append is deferred."""
    path = directory / "budget_ledger.jsonl"
    reservations, settlements = {}, {}
    if path.exists():
        raw = path.read_bytes()
        lines = raw.splitlines(keepends=True)
        for line in lines:
            if not line.endswith(b"\n"):
                continue
            item = json.loads(line)
            rid = item["reservation_id"]
            if item["event"] == "reserve":
                if rid in reservations:
                    raise ValueError("Duplicate ledger reservation")
                reservations[rid] = item
            elif item["event"] == "settle":
                if rid in settlements or rid not in reservations:
                    raise ValueError("Duplicate or unmatched ledger settlement")
                settlements[rid] = item
    by_case = defaultdict(lambda: {"charged_nd": 0, "reserved_nd": 0})
    for rid, reservation in reservations.items():
        target = by_case[reservation["case_id"]]
        if rid in settlements:
            target["charged_nd"] += settlements[rid]["charged_nd"]
        else:
            target["reserved_nd"] += reservation["reserved_nd"]
    total = {
        "settled_calls": len(settlements), "reservations": len(reservations),
        "charged_or_assumed_usd": sum(x["charged_nd"] for x in by_case.values()) / 1e9,
        "unresolved_reserved_usd": sum(x["reserved_nd"] for x in by_case.values()) / 1e9,
    }
    total["committed_upper_bound_usd"] = total["charged_or_assumed_usd"] + total["unresolved_reserved_usd"]
    return dict(by_case), total


def base_row(frozen: dict, method: str) -> dict:
    row = {name: frozen[name] for name in (
        "model", "main_case_order", "main_case_id", "stable_case_uid", "physical_scc_uid",
        "domain", "scc_size", "template",
    )}
    row.update({"method": method, "scale": scale(int(row["scc_size"])),
                "prediction_field": FIELDS[method], "available": False,
                "identity_exact": False, "coverage_status": "missing"})
    return row


def result_metrics(raw: dict, frozen: dict, method: str, pricing: dict, warnings: list) -> dict:
    invalid = bool(raw.get("error") or raw.get("cost_audit_error") or raw.get("completion_status") == "strict_experiment_failure")
    ids = set(frozen["planned_scc_clause_ids"])
    truth = frozen["planned_injection_identity"]
    risks = set(truth["risk_nodes"])
    if not risks:
        raise ValueError("Frozen risk endpoint set is empty")
    selected = [] if invalid else raw[FIELDS[method]]
    if not isinstance(selected, list) or not set(selected) <= ids:
        raise ValueError("Prediction contains unknown clause IDs or is not a list")
    selected = list(dict.fromkeys(selected))
    ranking = [] if invalid else raw.get("ranking")
    if not invalid and (not isinstance(ranking, list) or not ranking):
        raise ValueError("Valid result has no ranking")
    ranked_ids = [item[0] for item in ranking if isinstance(item, (list, tuple)) and item]
    if not set(ranked_ids) <= ids:
        raise ValueError("Ranking contains unknown clause IDs")
    root_at_3 = False if invalid else truth["root_node"] in ranked_ids[:3]
    risk_any = False if invalid else bool(set(selected) & risks)
    risk_all = False if invalid else risks <= set(selected)
    compression = None if invalid else 1 - len(selected) / len(ids)
    prefix = PREFIXES[method]
    checks = {
        "root_top3_hit": root_at_3,
        f"{prefix}_contains_any_risk_node": risk_any,
        f"{prefix}_contains_all_risk_nodes": risk_all,
        f"{prefix}_compression_ratio": compression,
    }
    if not invalid:
        for key, value in checks.items():
            if key in raw and (abs(raw[key]-value) > 1e-10 if isinstance(value, float) else raw[key] != value):
                warnings.append({"model": frozen["model"], "case": frozen["main_case_id"], "method": method,
                                 "field": key, "stored": raw[key], "recomputed": value})
    usage = raw.get("llm_usage_summary") or {}
    prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
    rates = raw.get("provider_route") or pricing["models"].get(frozen["model"], {})
    repriced = None
    if isinstance(prompt, int) and isinstance(completion, int) and rates:
        repriced = (prompt*rates["input_usd_per_million"] + completion*rates["output_usd_per_million"]) / 1e6
    return {
        "available": True, "strict_invalid": invalid,
        "invalid_reason": raw.get("error") or raw.get("cost_audit_error") or "",
        "root_at_3": int(root_at_3), "risk_any": int(risk_any), "risk_all": int(risk_all),
        "compression": compression, "selected_nodes_n": len(selected), "root_node": truth["root_node"],
        "risk_nodes_json": json.dumps(sorted(risks), ensure_ascii=False),
        "selected_nodes_json": json.dumps(selected, ensure_ascii=False),
        "llm_calls": usage.get("recorded_api_calls", raw.get("llm_calls")),
        "prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": usage.get("total_tokens"),
        "runtime_sec": raw.get("time"), "cost_usd_at_frozen_prices": repriced,
    }


def summary_group(group: str, rows: list[dict], *, matched: bool = False) -> dict:
    available = [r for r in rows if r["available"]]
    valid = [r for r in available if not r["strict_invalid"]]
    complete = len(available) == len(rows)
    row = {"group": group, "scope": "matched_available_subset" if matched else "frozen_target_scope",
           "status": "complete" if complete and not matched else "matched_subset" if matched else "partial",
           "expected_n": len(rows), "available_n": len(available), "missing_n": len(rows)-len(available),
           "strict_invalid_n": len(available)-len(valid), "valid_n": len(valid)}
    for metric in ("root_at_3", "risk_any", "risk_all"):
        row[f"{metric}_success_n"] = sum(x[metric] for x in available)
        row[metric] = sum(x[metric] for x in available)/len(rows) if complete and rows else None
    row["compression_valid_n"] = len(valid)
    row["compression"] = sum(x["compression"] for x in valid)/len(valid) if complete and valid else None
    for field in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_usd_at_frozen_prices",
                  "completion_charged_or_assumed_usd", "completion_unresolved_reserved_usd"):
        values = [x[field] for x in rows if isinstance(x.get(field), (int, float))]
        row[f"{field}_known_n"] = len(values)
        row[f"{field}_sum"] = sum(values) if values else None
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=HERE)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--cluster-registry", type=Path,
                        help="Explicit verified cluster import; defaults to the local registry when present")
    args = parser.parse_args()
    run_dir, out = args.run_dir.resolve(), args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = read_json(HERE / "frozen_manifest.json")
    pricing_path = run_dir / "frozen_pricing.json"
    pricing = read_json(pricing_path)
    pricing_hash = sha(pricing_path).removeprefix("sha256:")
    protocol_path = run_dir / "frozen_runner_protocol.json"
    protocol = read_json(protocol_path) if protocol_path.exists() else None
    protocol_hash = canonical_hash(protocol) if protocol is not None else None
    verification = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                    "api_calls": 0, "scope": "80 stable cases x four original models",
                    "errors": [], "stored_metric_discrepancies": [], "inherited_invalid_identities": 0}
    for item in manifest["inputs"]:
        if sha(Path(item["path"])) != item["sha256"]:
            verification["errors"].append(f"Frozen input hash mismatch: {item['path']}")
    for name, expected in manifest["outputs_sha256"].items():
        if sha(HERE / name) != expected:
            verification["errors"].append(f"Frozen CSV hash mismatch: {name}")
    if verification["errors"]:
        verification["verification_passed"] = False
        write_json(out / "verification.json", verification)
        return 1
    cluster = None
    registry_path = args.cluster_registry or HERE / "cluster_import_registry.json"
    if registry_path.exists() or args.cluster_registry is not None:
        from cluster_import import load_cluster_import
        try:
            cluster = load_cluster_import(registry_path.resolve(), protocol, manifest)
            verification["cluster_import"] = cluster["verification"]
        except (ValueError, KeyError, TypeError, OSError) as exc:
            verification["errors"].append({"cluster_import_rejected": str(exc)})
            verification["verification_passed"] = False
            write_json(out / "verification.json", verification)
            return 1
    audit_path = Path(manifest["inputs"][0]["path"])
    spec = importlib.util.spec_from_file_location("completion_audit", audit_path)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    catalog = audit.load_catalog(audit.DEFAULT_PLAN, audit.DEFAULT_REPLAY)
    plans = {case["case_uid"]: case for case in catalog}
    main_coverage = audit.load_main_coverage(audit.DEFAULT_MAIN_MANIFEST, audit.catalog_indexes(catalog)["key"])
    costs_by_case, ledger_summary = read_ledger(run_dir)
    cluster_costs = {}
    if cluster:
        cluster_costs, cluster_ledger = read_ledger(cluster["run_dir"])
        expected_cluster_ids = {job["runner_case_id"] for job in manifest["jobs"] if job["model"] == cluster["model"]}
        if set(cluster_costs) - expected_cluster_ids or cluster_ledger["committed_upper_bound_usd"] != 0:
            verification["errors"].append("Cluster ledger has unexpected cases or nonzero API charges")
        verification["cluster_budget_ledger_snapshot"] = cluster_ledger
    all_cells = manifest["reused"] + manifest["jobs"]
    all_cells.sort(key=lambda x: (manifest["models"].index(x["model"]), x["main_case_order"]))
    assert len(all_cells) == 320
    lea_rows, matched_rows = [], []
    expected_result_paths = {
        (run_dir / "results" / f"{job['runner_case_id']}__lea.json").resolve()
        for job in manifest["jobs"]
    }
    unknown_ledger_cases = sorted(set(costs_by_case) - {job["runner_case_id"] for job in manifest["jobs"]})
    if unknown_ledger_cases:
        verification["errors"].append({"unexpected_ledger_case_ids": unknown_ledger_cases})
    if ledger_summary["committed_upper_bound_usd"] > float(manifest["budget_limit_usd"]) + 1e-9:
        verification["errors"].append("Committed budget exceeds the authorized USD 50 ceiling")
    hashes, payloads = {}, {}

    def load(path: Path, expected: str | None = None):
        key = str(path)
        if key not in payloads:
            hashes[key], payloads[key] = sha(path), read_json(path)
        if expected and hashes[key] != expected:
            raise ValueError(f"Frozen artifact hash mismatch: {path}")
        return payloads[key]

    for frozen in all_cells:
        planned = plans[frozen["stable_case_uid"]]
        lea_row = base_row(frozen, "lea")
        source_path = Path(frozen["source_result_file"])
        runner_id = frozen.get("runner_case_id")
        is_cluster = cluster is not None and frozen["model"] == cluster["model"]
        tracked = (cluster_costs if is_cluster else costs_by_case).get(runner_id)
        if tracked:
            lea_row.update({"completion_charged_or_assumed_usd": tracked["charged_nd"]/1e9,
                            "completion_unresolved_reserved_usd": tracked["reserved_nd"]/1e9})
        try:
            original = load(source_path, frozen["source_result_sha256"])
            by_method = {}
            for method, raw_method in (("one-shot", "naive"), ("sa-mcgs", "sa-mcgs")):
                found = [x for x in original if x.get("model") == frozen["model"] and x.get("method") == raw_method]
                if len(found) != 1:
                    raise ValueError(f"Expected one original {method} model record")
                raw = found[0]
                key = (frozen["domain"], frozen["scc_size"], frozen["template"], frozen["model"], method)
                cov = main_coverage[key]
                if not cov["identity_exact"]:
                    raise ValueError(f"Original {method} identity mismatch")
                inherited = cov["identity_inherited_from_paired_sa"]
                if not inherited and not audit.validate_identity(raw, planned)[0]:
                    raise ValueError(f"Original {method} clause/injection identity mismatch")
                row = base_row(frozen, method)
                row.update(result_metrics(raw, frozen, method, pricing, verification["stored_metric_discrepancies"]))
                row.update({"coverage_status": "strict_invalid" if row["strict_invalid"] else "available_exact",
                            "identity_exact": True, "identity_basis": "paired_original_sa" if inherited else "ordered_clauses_and_injection",
                            "source_kind": "locked_main", "source_file": str(source_path), "source_sha256": hashes[str(source_path)]})
                verification["inherited_invalid_identities"] += int(inherited)
                by_method[method] = row
            if "lea_result_file" in frozen:
                lea_path = Path(frozen["lea_result_file"])
                raw = load(lea_path, frozen["lea_result_sha256"])
                kind = "vetted_reuse"
            else:
                result_run_dir = cluster["run_dir"] if is_cluster else run_dir
                result_pricing = cluster["pricing"] if is_cluster else pricing
                result_pricing_hash = cluster["pricing_hash"] if is_cluster else pricing_hash
                result_protocol_hash = cluster["protocol_hash"] if is_cluster else protocol_hash
                lea_path = result_run_dir / "results" / f"{runner_id}__lea.json"
                kind = "cluster_completion_batch" if is_cluster else "completion_batch"
                if not lea_path.exists():
                    status_path = result_run_dir / "case_status" / f"{runner_id}.json"
                    lea_row["coverage_status"] = read_json(status_path).get("completion_status", "missing") if status_path.exists() else "missing"
                    lea_row["source_kind"] = kind
                    lea_rows.append(lea_row)
                    continue
                raw = load(lea_path)
                if raw.get("case_id") != runner_id or raw.get("completion_status") not in ("complete", "strict_experiment_failure"):
                    raise ValueError("Completion case ID/status mismatch")
                if (raw.get("provider_route") != result_pricing["models"][frozen["model"]]
                        or raw.get("pricing_sha256") != result_pricing_hash
                        or raw.get("protocol_sha256") != result_protocol_hash):
                    raise ValueError("Completion model route/pricing/protocol mismatch")
                if raw.get("case_uid") != frozen["stable_case_uid"]:
                    raise ValueError("Completion stable case UID mismatch")
            if raw.get("model") != frozen["model"] or raw.get("method") != "lea":
                raise ValueError("LEA model/method mismatch")
            inherited_failure = raw.get("completion_status") == "strict_experiment_failure"
            if inherited_failure:
                if (raw.get("planned_scc_clause_ids") != frozen["planned_scc_clause_ids"]
                        or raw.get("planned_injection_identity") != frozen["planned_injection_identity"]
                        or raw.get("source_result_sha256") != frozen["source_result_sha256"]):
                    raise ValueError("Strict failure frozen plan identity mismatch")
                verification["inherited_invalid_identities"] += 1
            elif not audit.validate_identity(raw, planned)[0]:
                raise ValueError("LEA ordered clause/injection identity mismatch")
            lea_row.update(result_metrics(raw, frozen, "lea", pricing, verification["stored_metric_discrepancies"]))
            lea_row.update({"coverage_status": "strict_invalid" if lea_row["strict_invalid"] else "available_exact",
                            "identity_exact": True, "identity_basis": "validated_plan_strict_failure" if inherited_failure else "ordered_clauses_and_injection",
                            "source_kind": kind, "source_file": str(lea_path), "source_sha256": hashes[str(lea_path)]})
            by_method["lea"] = lea_row
            matched_rows.extend(by_method[method] for method in METHODS)
        except (ValueError, KeyError, AssertionError, TypeError) as exc:
            lea_row.update({"coverage_status": "rejected_integrity", "available": False, "identity_exact": False})
            verification["errors"].append({"model": frozen["model"], "case": frozen["main_case_id"], "reason": str(exc)})
        lea_rows.append(lea_row)
    # Compare with all frozen jobs: another process may finish a legitimate
    # case after its row was visited during this read-only snapshot.
    unexpected = sorted(str(path.resolve()) for path in (run_dir / "results").glob("*__lea.json") if path.resolve() not in expected_result_paths)
    if unexpected:
        verification["errors"].append({"unexpected_result_paths": unexpected})
    groups = defaultdict(list)
    for row in lea_rows:
        for key in ("overall", f"model={row['model']}", f"domain={row['domain']}", f"scale={row['scale']}",
                    f"scc_size={row['scc_size']}", f"template={row['template']}",
                    f"model={row['model']}|domain={row['domain']}", f"model={row['model']}|scale={row['scale']}"):
            groups[key].append(row)
    breakdown = [summary_group(key, rows) for key, rows in sorted(groups.items())]
    matched_groups = defaultdict(list)
    for row in matched_rows:
        matched_groups[f"model={row['model']}|method={row['method']}"].append(row)
    matched_summary = [summary_group(key, rows, matched=True) for key, rows in sorted(matched_groups.items())]
    available_n = sum(row["available"] for row in lea_rows)
    verification.update({
        "verification_passed": not verification["errors"], "completion_status": "complete" if available_n == 320 else "partial",
        "expected_lea_cells": 320, "available_lea_cells": available_n, "missing_lea_cells": 320-available_n,
        "new_available_cells": sum(row["available"] and row.get("source_kind") in ("completion_batch", "cluster_completion_batch") for row in lea_rows),
        "cluster_available_cells": sum(row["available"] and row.get("source_kind") == "cluster_completion_batch" for row in lea_rows),
        "reused_available_cells": sum(row["available"] and row.get("source_kind") == "vetted_reuse" for row in lea_rows),
        "matched_model_case_pairs": len(matched_rows)//3, "matched_method_records": len(matched_rows),
        "budget_ledger_snapshot": ledger_summary,
        "metric_policy": "Detection scores recomputed from final ranking and declared selected nodes. Invalid detection scores=0; invalid compression=null. Pending/provider-paused outputs are unavailable, never strict zero. Full-scope rates suppressed for incomplete groups. SA uses only core_evidence_risk_subgraph_nodes.",
        "cost_policy": "cost_usd_at_frozen_prices reprices available recorded token usage and is not historical billed cost. Completion ledger includes every reserved or settled call, including failures/retries/unfinished cases. Unknown historical token usage/cost stays null.",
        "by_model": {model: summary_group(f"model={model}", [x for x in lea_rows if x["model"] == model]) for model in manifest["models"]},
        "status_counts": dict(Counter(row["coverage_status"] for row in lea_rows)),
    })
    write_csv(out / "full320_case_metrics.csv", lea_rows, BASE_COLUMNS)
    write_csv(out / "full320_breakdown.csv", breakdown)
    write_csv(out / "matched_3method_case_metrics.csv", matched_rows, BASE_COLUMNS)
    write_csv(out / "matched_3method_summary.csv", matched_summary)
    write_json(out / "verification.json", verification)
    lines = ["# LEA 补跑汇总", "", f"数据状态：**{'完整' if available_n == 320 else 'PARTIAL（未完成）'}**；稳定身份核验通过的 LEA 结果 **{available_n}/320**。",
             f"历史复用 {verification['reused_available_cells']}/147，新增完成 {verification['new_available_cells']}/173。", "",
             "| 模型 | 已有/目标 | 严格无效 | 待完成 | 全80指标可用 |", "|---|---:|---:|---:|---|" ]
    for model, row in verification["by_model"].items():
        lines.append(f"| {model} | {row['available_n']}/80 | {row['strict_invalid_n']} | {row['missing_n']} | {'是' if row['status']=='complete' else '否'} |")
    complete_models = [(model, row) for model, row in verification["by_model"].items() if row["status"] == "complete"]
    if complete_models:
        lines += ["", "以下指标仅包含已完成全部80案例的模型；严格无效结果保留在检测指标分母中。", "",
                  "| 模型 | Root@3 | Risk-any | Risk-all | Compression（有效输出） |", "|---|---:|---:|---:|---:|"]
        for model, row in complete_models:
            vals = [f"{row[k]:.1%}" if row[k] is not None else "—" for k in ("root_at_3", "risk_any", "risk_all", "compression")]
            lines.append(f"| {model} | " + " | ".join(vals) + " |")
    if available_n == 320 and not verification["errors"]:
        lines += ["", "## 三方法完整配对结果", "", "每个模型均为同一批80例。Full-SCC 对应 sa-mcgs 的最终 core_evidence 输出；Compression 为删除节点比例。", "",
                  "| 模型 | 方法 | Root@3 | Risk-any | Risk-all | Compression | 严格无效 |", "|---|---|---:|---:|---:|---:|---:|"]
        for row in matched_summary:
            parts = dict(part.split("=", 1) for part in row["group"].split("|"))
            vals = [f"{row[k]:.2%}" if row[k] is not None else "—" for k in ("root_at_3", "risk_any", "risk_all", "compression")]
            method_label = {"one-shot": "One-shot", "lea": "LEA", "sa-mcgs": "Full-SCC"}[parts["method"]]
            lines.append(f"| {parts['model']} | {method_label} | " + " | ".join(vals) + f" | {row['strict_invalid_n']} |")
    lines += ["", "未完成分组的完整范围均值留空；不能把当前已完成子集的均值当作80案例结果。",
              f"已生成三方法共同集合：**{len(matched_rows)//3} 个模型×案例对，{len(matched_rows)} 条方法记录**；{'已覆盖完整冻结目标集合' if available_n == 320 else '这是当前可用共同子集'}。",
              "三方法输出分别使用 One-shot 的 direct_risk_subgraph_nodes、LEA 的 lea_risk_subgraph_nodes、SA 的 core_evidence_risk_subgraph_nodes。严格无效的 Root@3/Risk-any/Risk-all 记0，Compression 留空，仅对有效输出平均。", "",
              f"补跑账本：已结算或保守记账 **${ledger_summary['charged_or_assumed_usd']:.4f}**，未结算预留 **${ledger_summary['unresolved_reserved_usd']:.4f}**，合计承诺上界 **${ledger_summary['committed_upper_bound_usd']:.4f} / $50**。",
              "历史 LEA token 用量按冻结单价换算的成本单独列出，不代表历史账单，也不计入本次50美元增量额度。原始 One-shot/SA 无 token 记录时保留空值。", "",
              f"身份/配置异常：{len(verification['errors'])}；缓存指标与按最终输出重算差异：{len(verification['stored_metric_discrepancies'])}。",
              "明细见 full320_case_metrics.csv、full320_breakdown.csv、matched_3method_case_metrics.csv、matched_3method_summary.csv 和 verification.json。", ""]
    if cluster:
        lines += ["Qwen 的80例来自单独核验的集群结果快照。科学代码与参数和原补跑协议一致，案例身份、原始输出和来源哈希逐项核验；本地服务路由与零 API 费率单独记录，未覆盖原 API 配置。集群 GPU 资源成本未折算为美元。", ""]
    (out / "SUMMARY_ZH.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: verification[k] for k in ("verification_passed", "completion_status", "available_lea_cells", "new_available_cells", "matched_model_case_pairs", "budget_ledger_snapshot")}, ensure_ascii=False, indent=2))
    return 0 if verification["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

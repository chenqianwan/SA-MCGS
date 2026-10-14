#!/usr/bin/env python3
"""Offline reporting only; never imports inference code, clients, or credentials.

Inputs: frozen protocol/plan, final and candidate JSON, append-only ledger.
Outputs: REPORT_ZH.md, summary.json, case_metrics.csv in the same directory.
Incomplete runs are refused by default. --allow-partial marks pending cells as
pending (not observed failures), while retaining the planned denominator.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo


RUN_DIR = Path(__file__).resolve().parent
FIELDS = {"sa-mcgs": "evidence_risk_subgraph_nodes",
          "lea": "lea_risk_subgraph_nodes", "full-scc": "direct_risk_subgraph_nodes"}
GROUPS = [("sa-mcgs", "final", "SA-MCGS"),
          ("lea", "first", "LEA 第 1 次（诊断）"),
          ("lea", "final", "LEA Best-of-N"),
          ("full-scc", "first", "Full-SCC 第 1 次（诊断）"),
          ("full-scc", "final", "Full-SCC Best-of-N")]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_text(path, text):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def money(prompt, completion):
    return (2.5 * prompt + 10.0 * completion) / 1_000_000


def evaluate(result, method, ids, root, risks, eligible=True, common_cap=False):
    result = result or {}
    allowed = set(ids)
    ranking_rows = result.get("ranking", [])
    ranking = [row[0] for row in ranking_rows
               if isinstance(row, (list, tuple)) and len(row) >= 2]
    raw_nodes = result.get(FIELDS[method]) or []
    nodes = list(dict.fromkeys(raw_nodes))
    if common_cap:
        cap = min(len(ids), max(4, math.ceil(.45 * len(ids))))
        if len(nodes) > cap:
            order = {node: i for i, node in enumerate(ranking)}
            input_order = {node: i for i, node in enumerate(ids)}
            nodes = sorted(nodes, key=lambda node: (order.get(node, len(ids)),
                                                    input_order.get(node, len(ids))))[:cap]
    valid = bool(eligible and nodes and set(nodes) <= allowed
                 and len(ranking_rows) == len(ranking) == len(ids)
                 and set(ranking) == allowed)
    return {"valid": valid, "root_at_3": int(valid and root in ranking[:3]),
            "risk_any": int(valid and bool(set(risks) & set(nodes))),
            "risk_all": int(valid and bool(risks) and set(risks) <= set(nodes)),
            "output_n": len(nodes) if valid else None,
            "compression": 1 - len(nodes) / len(ids) if valid else None}


def replay_ledger(events):
    if not events or events[0].get("event") != "header":
        raise ValueError("Ledger header missing")
    header = events[0]
    if (header.get("input_nanos_per_token"), header.get("output_nanos_per_token")) != (2500, 10000):
        raise ValueError("Unexpected ledger prices; reporting formula needs review")
    calls = {}
    for event in events[1:]:
        call_id = event["call_id"]
        if event["event"] == "reserve":
            if call_id in calls:
                raise ValueError("Duplicate ledger reservation")
            calls[call_id] = {**event, "status": "reserved"}
        elif event["event"] == "finish":
            if call_id not in calls or calls[call_id]["status"] != "reserved":
                raise ValueError("Unmatched or duplicate ledger finish")
            calls[call_id].update(event)
        else:
            raise ValueError("Unexpected ledger event")
    return header, list(calls.values())


def call_summary(calls):
    completed = [call for call in calls if call["status"] == "completed_with_usage"]
    held = [call for call in calls if call["status"] != "completed_with_usage"]
    actual_nanos = sum(call["actual_nanos"] for call in completed)
    held_nanos = sum(call["reserved_nanos"] for call in held)
    return {"calls": len(calls), "completed_with_usage": len(completed),
            "held_calls": len(held), "statuses": dict(Counter(call["status"] for call in calls)),
            "returned_model_labels": dict(Counter(call.get("provider_model") or "not_returned"
                                                   for call in calls)),
            "prompt_tokens": sum(call["prompt_tokens"] for call in completed),
            "completion_tokens": sum(call["completion_tokens"] for call in completed),
            "total_tokens": sum(call["actual_total_tokens"] for call in completed),
            "held_tokens": sum(call["reserved_tokens"] for call in held),
            "accounted_tokens": sum(call["actual_total_tokens"] for call in completed)
                                + sum(call["reserved_tokens"] for call in held),
            "known_usage_usd": actual_nanos / 1_000_000_000,
            "held_usd": held_nanos / 1_000_000_000,
            "accounted_usd": (actual_nanos + held_nanos) / 1_000_000_000,
            "reservation_bound_violations": sum(bool(call.get("reservation_bound_exceeded")) for call in calls)}


def candidate_usage(candidate, owner_calls):
    """Known cost comes from candidate usage_delta; locate held calls by offsets."""
    delta = candidate.get("usage_delta") or {}
    prompt = int(delta.get("prompt_tokens", 0))
    completion = int(delta.get("completion_tokens", 0))
    before = candidate.get("usage_before") or {}
    after = candidate.get("usage_after") or {}
    start = int(before.get("accounted_tokens", before.get("total_tokens", 0)))
    stop = int(after.get("accounted_tokens", after.get("total_tokens", start)))
    cumulative = 0
    selected = []
    for call in owner_calls:
        amount = (call["actual_total_tokens"] if call["status"] == "completed_with_usage"
                  else call["reserved_tokens"])
        left, right = cumulative, cumulative + amount
        if right > start and left < stop:
            if left < start or right > stop:
                raise ValueError("Candidate usage boundaries split a ledger request")
            selected.append(call)
        cumulative = right
    summary = call_summary(selected)
    if (summary["prompt_tokens"], summary["completion_tokens"]) != (prompt, completion):
        raise ValueError("Candidate usage_delta does not match ledger token totals")
    # Explicitly use the specified input/output calculation for this diagnostic.
    summary["known_usage_usd"] = money(prompt, completion)
    summary["accounted_usd"] = summary["known_usage_usd"] + summary["held_usd"]
    return summary


def verify_metrics(recomputed, stored, context):
    for key in ("valid", "root_at_3", "risk_any", "risk_all", "output_n", "compression"):
        expected, actual = recomputed[key], stored.get(key)
        equal = (math.isclose(expected, actual, abs_tol=1e-10)
                 if isinstance(expected, float) and isinstance(actual, (int, float))
                 else expected == actual)
        if not equal:
            raise ValueError(f"Stored metric mismatch: {context}, {key}: {actual} != {expected}")


def aggregate(rows, planned):
    eligible = [row for row in rows if row["valid"]]
    return {"planned": planned, "observed": sum(row["observed"] for row in rows),
            "pending": sum(not row["observed"] for row in rows), "valid": len(eligible),
            "invalid_observed": sum(row["observed"] and not row["valid"] for row in rows),
            "root_at_3_count": sum(row["root_at_3"] for row in rows),
            "risk_any_count": sum(row["risk_any"] for row in rows),
            "risk_all_count": sum(row["risk_all"] for row in rows),
            "root_at_3": sum(row["root_at_3"] for row in rows) / planned,
            "risk_any": sum(row["risk_any"] for row in rows) / planned,
            "risk_all": sum(row["risk_all"] for row in rows) / planned,
            "mean_output_n_valid_only": mean(row["output_n"] for row in eligible) if eligible else None,
            "mean_compression_valid_only": mean(row["compression"] for row in eligible) if eligible else None,
            "compression_n": len(eligible),
            **{key: sum(row[key] for row in rows) for key in
               ("calls", "prompt_tokens", "completion_tokens", "total_tokens", "held_tokens",
                "accounted_tokens", "known_usage_usd", "held_usd", "accounted_usd")}}


def fmt(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def rate(count, total):
    return f"{count}/{total} ({100*count/total:.1f}%)"


def report_markdown(summary, rows):
    n = summary["planned_cases"]
    finance = summary["finance"]
    lines = ["# 四域 GPT-4o 小规模试跑报告", "", f"生成时间：{summary['generated_at']}。状态：{summary['status']}。", "",
             f"本报告覆盖 {n} 个源 SCC、每源一个注入变体、一个模型 GPT-4o；按各域最小来源选取，属于开发 pilot，不是 80 变体主实验，也不能据此作显著性或跨域泛化结论。",
             "所有 Ground Truth 仅用于本离线报告；候选生成与选择已经冻结。", "",
             "## 原生输出主表", "",
             f"二元指标固定以全部 {n} 例为分母；失败不删除。H 大小与压缩率仅对有效输出取均值，并保留原方法的输出节点集合。第 1 次诊断只取 candidate_index=1，失败记 0，绝不换成第一个成功候选。", "",
             "| 方法 | 有效 | Root@3 | Risk-all | 平均实际 H | 压缩率（有效 n） | 调用 | 已知 tokens | usage 估值 USD | 未知预留 USD |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for method, scope, label in GROUPS:
        item = summary["groups"][f"{method}:{scope}"]
        comp = item["mean_compression_valid_only"]
        lines.append(f"| {label} | {item['valid']}/{n} | {rate(item['root_at_3_count'], n)} | {rate(item['risk_all_count'], n)} | {fmt(item['mean_output_n_valid_only'])} | {fmt(None if comp is None else 100*comp)}% ({item['compression_n']}) | {item['calls']} | {item['total_tokens']:,} | {item['known_usage_usd']:.4f} | {item['held_usd']:.4f} |")
    lines += ["", "第 1 次行仅是完整 Best-of-N 流程的费用子集，不能把五行相加。Best-of-N 行包含所有候选、失败请求和 judge；judge 失败时最终输出记失败，不回退挑选其他答案。",
              "", "## 逐例结果与重复选择", "",
              "| 来源 | 方法 | 首次有效 / Root / All | 最终有效 / Root / All | 选中候选 | 完整/尝试候选 | 选择状态 | H 首次→最终 |",
              "|---|---|---|---|---:|---:|---|---:|"]
    for transition in summary["first_to_final"]:
        first, final = transition["first"], transition["final"]
        def compact(row):
            return f"{int(row['valid'])}/{row['root_at_3']}/{row['risk_all']}" if row["observed"] else "待完成"
        lines.append(f"| {transition['domain']} / {transition['case_slot']} | {transition['method']} | {compact(first)} | {compact(final)} | {transition['selected_candidate_index']} | {transition['complete_candidates']}/{transition['attempted_candidates']} | {transition['selection_status']} | {first['output_n']}→{final['output_n']} |")
    lines += ["", "完整逐例五方法数据见 case_metrics.csv；没有按结果挑选候选，也没有用真实 Risk-all 最大值替代 blind judge。", "",
              "## SA 完成的工作与预算停止", "",
              "| 来源 | 完成 rollout | 停止原因 | 有效 | 实际 H | 已知 tokens |",
              "|---|---:|---|---:|---:|---:|"]
    for row in rows:
        if row["method"] == "sa-mcgs":
            lines.append(f"| {row['domain']} / {row['case_slot']} | {row['completed_rollouts']} | {row['stop_reason']} | {int(row['valid'])} | {row['output_n']} | {row['total_tokens']:,} |")
    cap = summary["per_arm_token_cap"]
    lines += ["", f"每个来源、每种方法的 token 上限均为 {cap:,}，实际使用量可以不同；不填充无意义调用，也不把共同上限表述成实际 token 完全相等。候选次数还有预设上限（LEA 6 次、Full-SCC 12 次），SA 至多 60 个 rollout；达到次数上限时可以远未耗满 token 上限。因此本试跑不是严格匹配实际 tokens 的实验。SA 的 budget_limit 表示返回预算停止前已完成的前缀，未必完成 60 个 rollout；API/JSON 失败触发的可靠性 guard 与预算正常停止分开记录。"]
    stopped = []
    for item in summary["first_to_final"]:
        if not item.get("sampling_stop"):
            continue
        reason = {"insufficient_tokens_for_estimated_complete_run": "未通过下一整轮的保守启动门槛",
                  "strict_budget_gate": "触发请求预算门槛"}.get(item["sampling_stop"], item["sampling_stop"])
        selector = ("未调用 judge" if item["selection_status"] == "single_complete_candidate_no_judge"
                    else f"judge 实际用 {item['judge_tokens_used']:,} tokens")
        stopped.append(f"{item['domain'].upper()} {item['method']}：{reason}，完成 {item['complete_candidates']} 个候选，评选预留 {item['selector_reserve_tokens']:,} tokens，{selector}，全臂实际用 {item['actual_tokens']:,} tokens")
    if stopped:
        lines += ["", "另有基线提前停止：" + "；".join(stopped) + "。保守评选预留会减少可启动候选的额度，并可能导致上限明显未用满；它不是实际消耗，也未计入实花或未知请求费用。仅有一个候选的案例不能用于证明重复选择的增益。"]
    lines += ["", "## 共同输出上限：仅离线诊断", "",
              "按 min(n, max(4, ceil(0.45n))) 对原 H 做排名顺序截断，不重新生成或重新评选。它用于检查更大输出集合是否解释保留率差异，不替代原生输出主表。", "",
              "| 方法 | 有效 | Root@3 | Risk-all | 平均 H | 压缩率（有效 n） |",
              "|---|---:|---:|---:|---:|---:|"]
    for method, scope, label in GROUPS:
        item = summary["common_cap_groups"][f"{method}:{scope}"]
        comp = item["mean_compression_valid_only"]
        lines.append(f"| {label} | {item['valid']}/{n} | {rate(item['root_at_3_count'], n)} | {rate(item['risk_all_count'], n)} | {fmt(item['mean_output_n_valid_only'])} | {fmt(None if comp is None else 100*comp)}% ({item['compression_n']}) |")
    lines += ["", "## 全部支出与完整性", "",
              f"全流程共记录 {finance['calls']} 次 API 尝试；有 usage 的费用估值 ${finance['known_usage_usd']:.4f}，未知/尚未结算请求保守预留 ${finance['held_usd']:.4f}，预算记账合计 ${finance['accounted_usd']:.4f}，上限 ${finance['cap_usd']:.2f}。",
              f"已知输入 {finance['prompt_tokens']:,}、输出 {finance['completion_tokens']:,}、总计 {finance['total_tokens']:,} tokens；另保留 {finance['held_tokens']:,} 个未知 token 预留。请求状态计数：{json.dumps(finance['statuses'], ensure_ascii=False)}。",
              "费用按冻结 GPT-4o 输入 $2.50/M、输出 $10.00/M tokens 估算，属于可归属到本实验的 usage 估值，不等同于独立账单。预留是风险占用，不宣称已实际收费；本报告不读取账户余额。共享账户余额变化只能作为诊断，不能替代本实验 ledger。",
              f"全部请求使用 gpt-4o、同一渠道。供应商返回的模型标签计数为 {json.dumps(finance['returned_model_labels'], ensure_ascii=False)}；这仅报告返回字段，不据此断言同一或不同模型快照。各实际方法标签分布为 {json.dumps(summary['returned_model_labels_by_arm'], ensure_ascii=False)}。",
              f"独立核验：{summary['validation']['stored_metric_checks']} 组已存指标重算一致；{summary['validation']['owner_usage_checks']} 个最终 usage 与 ledger 一致；预算预留边界异常 {finance['reservation_bound_violations']} 次。",
              "", "数据入口：protocol.json、case_plan.json、各来源/方法的 final.json 与 candidate_001.json、ledger.jsonl。该脚本只生成离线报告，不导入推理代码、不调用 API、不修改冻结协议或实验结果。", ""]
    if summary["pending_cells"]:
        lines.insert(4, "**运行尚未完成；pending 不是观测失败，当前比例是以计划分母显示的进度下界，不能作最终比较。**\n")
    return "\n".join(lines)


def build_report(directory, allow_partial=False):
    directory = Path(directory)
    protocol = read_json(directory / "protocol.json")
    cases = read_json(directory / "case_plan.json")
    case_ids = [case["case_id"] for case in cases]
    if len(case_ids) != len(set(case_ids)) or set(case_ids) != {case["case_id"] for case in protocol["cases"]}:
        raise ValueError("Case plan and protocol do not identify the same unique cases")
    pending = [(case["case_id"], method) for case in cases for method in FIELDS
               if not (directory / "results" / case["case_id"] / method / "final.json").exists()]
    if pending and not allow_partial:
        raise RuntimeError(f"Experiment still running: {len(pending)} of {len(cases)*3} final.json files missing; no report written")
    data = (directory / "ledger.jsonl").read_bytes()
    if not data.endswith(b"\n"):
        raise RuntimeError("Ledger snapshot ends in a partial line; retry after the current write")
    header, calls = replay_ledger([json.loads(line) for line in data.splitlines()])
    owners = defaultdict(list)
    for call in calls:
        owners[(call["case_id"], call["method"])].append(call)
    expected_owners = {(case_id, method) for case_id in case_ids for method in FIELDS}
    if set(owners) - expected_owners:
        raise ValueError("Ledger contains a case/method outside the frozen plan")
    rows, capped_rows, transitions = [], [], []
    metric_checks = usage_checks = 0
    for case in cases:
        identity = case.get("planned_injection_identity") or {}
        ids = case.get("planned_scc_clause_ids") or []
        root, risks = identity.get("root_node"), identity.get("risk_nodes")
        if not ids or root not in ids or not risks or not set(risks) <= set(ids):
            raise ValueError(f"Missing or invalid frozen scoring labels: {case['case_id']}")
        slot = case.get("case_slot", case.get("case_order"))
        for method in FIELDS:
            folder = directory / "results" / case["case_id"] / method
            final_file = folder / "final.json"
            final = read_json(final_file) if final_file.exists() else None
            owner_calls = owners[(case["case_id"], method)]
            usage = call_summary(owner_calls)
            if final:
                if final.get("case_id") != case["case_id"] or final.get("method") != method:
                    raise ValueError("Final output identity mismatch")
                for key in ("prompt_tokens", "completion_tokens", "total_tokens", "accounted_tokens", "calls"):
                    if final["usage"].get(key) != usage[key]:
                        raise ValueError(f"Final usage differs from ledger: {case['case_id']} {method} {key}")
                usage_checks += 1
            inference = (final or {}).get("inference") or {}
            selection = inference.get("selection") or {}
            result = (final or {}).get("selected_result") or {}
            eligible = bool(final and not final.get("error_type"))
            scores = evaluate(result, method, ids, root, risks, eligible)
            capped = evaluate(result, method, ids, root, risks, eligible, common_cap=True)
            if final:
                verify_metrics(scores, final["metrics"], f"{case['case_id']} {method} native")
                metric_checks += 1
                if final.get("common_cap_diagnostic"):
                    verify_metrics(capped, final["common_cap_diagnostic"], f"{case['case_id']} {method} common cap")
                    metric_checks += 1
            row = {"case_id": case["case_id"], "case_slot": slot, "domain": case["domain"],
                   "source_scc_size": len(ids), "case_uid": case.get("case_uid"),
                   "method": method, "scope": "final", "observed": final is not None,
                   "status": (final or {}).get("error_type") or selection.get("status") or ("native_sa_core" if final else "pending"),
                   "selected_candidate_index": selection.get("selected_candidate_index"),
                   "attempted_candidates": selection.get("attempted_candidates"),
                   "complete_candidates": selection.get("complete_candidates"),
                   "completed_rollouts": inference.get("completed_rollouts"),
                   "stop_reason": result.get("stop_reason") or (final or {}).get("error_type") or ("not_applicable" if final else "pending"),
                   **scores, **{k: v for k, v in usage.items() if k not in {"statuses", "returned_model_labels"}},
                   **{f"common_cap_{key}": value for key, value in capped.items()}}
            rows.append(row)
            capped_rows.append({**row, **capped})
            if method == "sa-mcgs":
                continue
            first_path = folder / "candidate_001.json"
            first = read_json(first_path) if first_path.exists() else None
            if first and first.get("candidate_index") != 1:
                raise ValueError("candidate_001.json does not contain candidate_index=1")
            first_result = ((first or {}).get("raw_result") or (first or {}).get("result") or {})
            first_eligible = bool(first and first.get("status") == "complete")
            first_metrics = evaluate(first_result, method, ids, root, risks, first_eligible)
            first_capped = evaluate(first_result, method, ids, root, risks, first_eligible, common_cap=True)
            first_usage = candidate_usage(first, owner_calls) if first else call_summary([])
            first_row = {**row, "scope": "first", "observed": bool(first or final),
                         "status": (first or {}).get("status") or ("not_generated" if final else "pending"),
                         "selected_candidate_index": 1 if first else None,
                         "attempted_candidates": int(bool(first)), "complete_candidates": int(first_eligible),
                         "stop_reason": "first_attempt_diagnostic", **first_metrics,
                         **{k: v for k, v in first_usage.items() if k not in {"statuses", "returned_model_labels"}},
                         **{f"common_cap_{key}": value for key, value in first_capped.items()}}
            rows.append(first_row)
            capped_rows.append({**first_row, **first_capped})
            keys = ("observed", "valid", "root_at_3", "risk_all", "output_n", "status")
            transitions.append({"case_id": case["case_id"], "case_slot": slot,
                                "domain": case["domain"], "method": method,
                                "first": {key: first_row[key] for key in keys},
                                "final": {key: row[key] for key in keys},
                                "selected_candidate_index": row["selected_candidate_index"],
                                "complete_candidates": row["complete_candidates"],
                                "attempted_candidates": row["attempted_candidates"],
                                "sampling_stop": selection.get("sampling_stop"),
                                "selector_reserve_tokens": selection.get("selector_reserve_tokens", 0),
                                "judge_tokens_used": selection.get("judge_tokens_used", 0),
                                "actual_tokens": usage["total_tokens"],
                                "selection_status": row["status"]})
    finance = call_summary(calls)
    finance["cap_usd"] = header["cap_nanos"] / 1_000_000_000
    finance["remaining_budget_usd"] = max(0., finance["cap_usd"] - finance["accounted_usd"])
    summary = {"generated_at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(timespec="seconds"),
               "status": "partial" if pending else "complete", "model": protocol["model"],
               "planned_cases": len(cases), "planned_method_jobs": len(cases)*3,
               "pending_cells": pending, "per_arm_token_cap": protocol["per_arm_token_cap"],
               "finance": finance, "first_to_final": transitions,
               "returned_model_labels_by_arm": {
                   method: dict(Counter(call.get("provider_model") or "not_returned"
                                        for call in calls if call["method"] == method))
                   for method in FIELDS},
               "groups": {}, "common_cap_groups": {},
               "validation": {"stored_metric_checks": metric_checks, "owner_usage_checks": usage_checks,
                              "scoring_source": "frozen case_plan.planned_injection_identity; offline only",
                              "first_candidate_policy": "candidate_index=1, invalid remains zero; never first valid"},
               "source_sha256": {name: file_hash(directory/name) for name in ["protocol.json", "case_plan.json"]},
               "ledger_snapshot_sha256": hashlib.sha256(data).hexdigest(),
               "report_script_sha256": file_hash(__file__)}
    for method, scope, _label in GROUPS:
        key = f"{method}:{scope}"
        summary["groups"][key] = aggregate([row for row in rows if (row["method"], row["scope"]) == (method, scope)], len(cases))
        summary["common_cap_groups"][key] = aggregate([row for row in capped_rows if (row["method"], row["scope"]) == (method, scope)], len(cases))
    summary["case_metrics"] = rows
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    atomic_text(directory/"case_metrics.csv", buffer.getvalue())
    atomic_text(directory/"summary.json", json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    atomic_text(directory/"REPORT_ZH.md", report_markdown(summary, rows))
    return summary


def self_test():
    ids = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
    result = {"ranking": [(node, 1-i/20) for i, node in enumerate(ids)],
              "direct_risk_subgraph_nodes": ["a", "b", "c", "d", "e", "j"]}
    native = evaluate(result, "full-scc", ids, "a", ["a", "j"])
    capped = evaluate(result, "full-scc", ids, "a", ["a", "j"], common_cap=True)
    failed_first = evaluate(result, "full-scc", ids, "a", ["a", "j"], eligible=False)
    assert native["risk_all"] == 1 and native["output_n"] == 6
    assert capped["risk_all"] == 0 and capped["output_n"] == 5
    assert not failed_first["valid"] and failed_first["risk_all"] == 0 and failed_first["compression"] is None
    events = [{"event": "header", "input_nanos_per_token": 2500, "output_nanos_per_token": 10000},
              {"event": "reserve", "call_id": "1", "reserved_tokens": 1000, "reserved_nanos": 10000000},
              {"event": "finish", "call_id": "1", "status": "completed_with_usage", "prompt_tokens": 100,
               "completion_tokens": 20, "actual_total_tokens": 120, "actual_nanos": 450000},
              {"event": "reserve", "call_id": "2", "reserved_tokens": 1000, "reserved_nanos": 10000000},
              {"event": "finish", "call_id": "2", "status": "unknown_failure"}]
    _, calls = replay_ledger(events)
    financial = call_summary(calls)
    assert financial["calls"] == 2 and financial["held_calls"] == 1
    assert math.isclose(financial["known_usage_usd"], .00045)
    assert math.isclose(financial["held_usd"], .01) and financial["accounted_tokens"] == 1120
    candidate = {"usage_before": {"accounted_tokens": 0}, "usage_after": {"accounted_tokens": 1120},
                 "usage_delta": {"prompt_tokens": 100, "completion_tokens": 20}}
    assert candidate_usage(candidate, calls)["held_usd"] == .01
    print("report self-test: PASS (native/cap distinction, strict invalid first, known/held accounting)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=RUN_DIR)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    if arguments.self_test:
        self_test()
    else:
        try:
            output = build_report(arguments.run_dir, arguments.allow_partial)
        except (ValueError, RuntimeError, KeyError) as error:
            parser.exit(2, f"Report not generated: {error}\n")
        print(json.dumps({"status": output["status"], "planned_cases": output["planned_cases"],
                          "known_usage_usd": output["finance"]["known_usage_usd"],
                          "held_usd": output["finance"]["held_usd"],
                          "report": str(arguments.run_dir/"REPORT_ZH.md")}, ensure_ascii=False))

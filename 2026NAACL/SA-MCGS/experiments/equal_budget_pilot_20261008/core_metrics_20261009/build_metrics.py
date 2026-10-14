#!/usr/bin/env python3
"""Rebuild additional pilot diagnostics offline using only the Python standard library.

Reads the frozen plan, completed outputs, original summary, and request ledger.
Writes only metrics.json, metrics_by_case.csv, and metrics_summary.csv beside this
script. Does not import inference code, read credentials, or make network calls.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
from statistics import mean


OUTPUT_DIR = Path(__file__).resolve().parent
RUN_DIR = OUTPUT_DIR.parent
DOMAINS = ["debian", "sec_ex21", "bgb", "cuad"]
GROUPS = [
    ("sa-mcgs:final", "SA-MCGS", "sa-mcgs", "final"),
    ("lea:first", "LEA 首次", "lea", "first"),
    ("lea:final", "LEA Best-of-N", "lea", "final"),
    ("full-scc:first", "Full-SCC 首次", "full-scc", "first"),
    ("full-scc:final", "Full-SCC Best-of-N", "full-scc", "final"),
]
H_FIELDS = {
    "sa-mcgs": "evidence_risk_subgraph_nodes",
    "lea": "lea_risk_subgraph_nodes",
    "full-scc": "direct_risk_subgraph_nodes",
}
INPUT_HASHES = {}


def read_bytes(path):
    data = path.read_bytes()
    INPUT_HASHES[str(path.relative_to(RUN_DIR))] = hashlib.sha256(data).hexdigest()
    return data


def read_json(path):
    return json.loads(read_bytes(path))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(left, right, context):
    require(math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-10),
            f"Mismatch at {context}: {left!r} != {right!r}")


def load_ledger():
    data = read_bytes(RUN_DIR / "ledger.jsonl")
    require(data.endswith(b"\n"), "Ledger has an incomplete trailing line")
    events = [json.loads(line) for line in data.splitlines()]
    header = events[0]
    require(header.get("event") == "header", "Missing ledger header")
    require((header["input_nanos_per_token"], header["output_nanos_per_token"])
            == (2500, 10000), "Unexpected frozen pricing")
    calls = {}
    for event in events[1:]:
        call_id = event["call_id"]
        if event["event"] == "reserve":
            require(call_id not in calls, "Duplicate reserve event")
            # Preserve reserve time before the finish event replaces time_unix.
            calls[call_id] = {**event, "reserve_time": event["time_unix"]}
        elif event["event"] == "finish":
            require(call_id in calls and "finish_time" not in calls[call_id],
                    "Unmatched or repeated finish event")
            calls[call_id].update(event)
            calls[call_id]["finish_time"] = event["time_unix"]
        else:
            raise ValueError(f"Unexpected ledger event: {event['event']}")
    for call in calls.values():
        require(call.get("status") == "completed_with_usage" and "finish_time" in call,
                "This completed-pilot export requires settled usage for every request")
        require(call["finish_time"] >= call["reserve_time"], "Negative request duration")
        require(call["actual_total_tokens"] == call["prompt_tokens"] + call["completion_tokens"],
                "Token total differs from input + output")
        require(call["actual_nanos"] == 2500 * call["prompt_tokens"] + 10000 * call["completion_tokens"],
                "Request cost differs from frozen usage prices")
    return list(calls.values())


def usage(calls):
    return {
        "total_tokens": sum(call["actual_total_tokens"] for call in calls),
        "prompt_tokens": sum(call["prompt_tokens"] for call in calls),
        "completion_tokens": sum(call["completion_tokens"] for call in calls),
        "calls": len(calls),
        "cost_usd": sum(call["actual_nanos"] for call in calls) / 1_000_000_000,
        "elapsed_sec": (max(call["finish_time"] for call in calls)
                        - min(call["reserve_time"] for call in calls)) if calls else None,
    }


def first_candidate_calls(candidate, owner_calls):
    before, after = candidate["usage_before"], candidate["usage_after"]
    start, stop = before["accounted_tokens"], after["accounted_tokens"]
    require(stop >= start, "Reversed candidate usage offsets")
    selected, cumulative = [], 0
    for call in owner_calls:
        left, right = cumulative, cumulative + call["actual_total_tokens"]
        if right > start and left < stop:
            require(left >= start and right <= stop, "Candidate boundary splits a request")
            selected.append(call)
        cumulative = right
    measured = usage(selected)
    require(measured["total_tokens"] == stop - start, "Candidate interval is not fully matched")
    for key in ("total_tokens", "prompt_tokens", "completion_tokens"):
        require(measured[key] == candidate["usage_delta"][key],
                f"Candidate usage mismatch: {key}")
    return selected


def score(result, method, case, eligible):
    ids = case["planned_scc_clause_ids"]
    identity = case["planned_injection_identity"]
    root = identity["root_node"]
    risks, evidence = set(identity["risk_nodes"]), set(identity["evidence_nodes"])
    require(root in ids and risks and evidence and risks <= evidence <= set(ids),
            "Invalid frozen injection labels")
    result = result or {}
    ranking_rows = result.get("ranking") or []
    ranking = [row[0] for row in ranking_rows
               if isinstance(row, (list, tuple)) and len(row) >= 2]
    nodes = set(result.get(H_FIELDS[method]) or [])
    valid = bool(eligible and nodes and nodes <= set(ids)
                 and len(ranking_rows) == len(ranking) == len(ids)
                 and set(ranking) == set(ids))
    root_rank = ranking.index(root) + 1 if valid else None
    risk_kept, evidence_kept = (len(risks & nodes), len(evidence & nodes)) if valid else (0, 0)
    return {
        "root_rank": root_rank,
        "root_at_1": int(root_rank == 1),
        "root_at_3": int(root_rank is not None and root_rank <= 3),
        "risk_any": int(valid and risk_kept > 0),
        "risk_all": int(valid and risk_kept == len(risks)),
        "endpoint_recall": risk_kept / len(risks),
        "evidence_all": int(valid and evidence_kept == len(evidence)),
        "evidence_recall": evidence_kept / len(evidence),
        "evidence_kept": evidence_kept,
        "evidence_total": len(evidence),
        "risk_kept": risk_kept,
        "risk_total": len(risks),
        "output_n": len(nodes) if valid else None,
        "source_n": len(ids),
        "compression": 1 - len(nodes) / len(ids) if valid else None,
    }


def check_final(final, method, case, owner_calls):
    require(final["case_id"] == case["case_id"] and final["method"] == method,
            "Final output identity mismatch")
    measured = usage(owner_calls)
    for key in ("total_tokens", "prompt_tokens", "completion_tokens", "calls"):
        require(measured[key] == final["usage"][key], f"Final usage mismatch: {key}")
    close(measured["cost_usd"], final["usage"]["actual_usd"], "final cost")
    scored = score(final.get("selected_result"), method, case, not final.get("error_type"))
    for key in ("root_at_3", "risk_any", "risk_all", "output_n", "compression"):
        if scored[key] is None:
            require(final["metrics"][key] is None, f"Final metric mismatch: {key}")
        else:
            close(scored[key], final["metrics"][key], f"final {key}")
    return scored, measured


def aggregate(group_id, label, rows, n_cases):
    selected = [row for row in rows if row["group_id"] == group_id]
    require(len(selected) == n_cases, "A group does not cover the planned denominator")
    valid = [row for row in selected if row["output_n"] is not None]
    timed = [row["elapsed_sec"] for row in selected if row["elapsed_sec"] is not None]
    return {
        "id": group_id,
        "label": label,
        **{key: sum(row[key] for row in selected) / n_cases for key in
           ("root_at_1", "root_at_3", "risk_any", "risk_all", "endpoint_recall",
            "evidence_all", "evidence_recall")},
        "mrr": sum(1 / row["root_rank"] if row["root_rank"] else 0 for row in selected) / n_cases,
        "mean_output_n": mean(row["output_n"] for row in valid) if valid else None,
        "compression": mean(row["compression"] for row in valid) if valid else None,
        **{key: sum(row[key] for row in selected) for key in
           ("prompt_tokens", "completion_tokens", "total_tokens", "calls")},
        "cost_usd": sum(round(row["cost_usd"] * 1_000_000_000) for row in selected) / 1_000_000_000,
        "mean_elapsed_sec": mean(timed) if timed else None,
    }


def atomic_write(path, text):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def csv_text(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def main():
    plan = read_json(RUN_DIR / "case_plan.json")
    protocol = read_json(RUN_DIR / "protocol.json")
    original = read_json(RUN_DIR / "summary.json")
    require(original["status"] == "complete" and not original["pending_cells"],
            "The original pilot report is incomplete")
    require(len(plan) == 4 and {case["domain"] for case in plan} == set(DOMAINS),
            "Expected exactly one source per frozen domain")
    plan = sorted(plan, key=lambda case: DOMAINS.index(case["domain"]))
    require({case["case_id"] for case in plan} == {case["case_id"] for case in protocol["cases"]},
            "Protocol and plan case IDs differ")
    calls = load_ledger()
    expected_owners = {(case["case_id"], method) for case in plan for method in H_FIELDS}
    require({(call["case_id"], call["method"]) for call in calls} == expected_owners,
            "Unexpected or missing ledger owner")
    finals, owners = {}, {}
    for case in plan:
        for method in H_FIELDS:
            owner = (case["case_id"], method)
            owners[owner] = [call for call in calls
                             if (call["case_id"], call["method"]) == owner]
            final = read_json(RUN_DIR / "results" / case["case_id"] / method / "final.json")
            check_final(final, method, case, owners[owner])
            finals[owner] = final
    rows = []
    for group_id, _label, method, scope in GROUPS:
        for case in plan:
            owner = (case["case_id"], method)
            final, owner_calls = finals[owner], owners[owner]
            selection = final.get("inference", {}).get("selection", {})
            if scope == "first":
                candidate = read_json(RUN_DIR / "results" / case["case_id"] / method / "candidate_001.json")
                require(candidate["candidate_index"] == 1, "First candidate is not index 1")
                result = candidate.get("raw_result") or candidate.get("result") or {}
                scored = score(result, method, case, candidate["status"] == "complete")
                measured = usage(first_candidate_calls(candidate, owner_calls))
                candidate_count = int(candidate["status"] == "complete")
            else:
                scored, measured = check_final(final, method, case, owner_calls)
                candidate_count = selection.get("complete_candidates") if method != "sa-mcgs" else None
            rows.append({"group_id": group_id, "domain": case["domain"], "case_id": case["case_id"],
                         **scored, **measured, "candidate_count": candidate_count,
                         "rollouts": final.get("inference", {}).get("completed_rollouts")
                         if method == "sa-mcgs" else None})
    groups = [aggregate(group_id, label, rows, len(plan)) for group_id, label, _, _ in GROUPS]
    for group in groups:
        stored = original["groups"][group["id"]]
        for key in ("root_at_3", "risk_any", "risk_all", "prompt_tokens", "completion_tokens",
                    "total_tokens", "calls"):
            close(group[key], stored[key], f"original summary {group['id']} {key}")
        close(group["cost_usd"], stored["known_usage_usd"], f"original summary {group['id']} cost")
        close(group["mean_output_n"], stored["mean_output_n_valid_only"], "original output size")
        close(group["compression"], stored["mean_compression_valid_only"], "original compression")
    finance_usage = usage(calls)
    for key in ("total_tokens", "calls"):
        require(finance_usage[key] == original["finance"][key], f"Global {key} differs")
    close(finance_usage["cost_usd"], original["finance"]["known_usage_usd"], "global cost")
    actual_groups = [group for group in groups if group["id"].endswith(":final")]
    for key in ("total_tokens", "calls", "cost_usd"):
        close(sum(group[key] for group in actual_groups), finance_usage[key], f"actual-arm total {key}")
    notes = {
        "scope": "4个小源SCC、各1个注入变体、GPT-4o单模型开发pilot；所有新指标仅离线计算。",
        "ordering": "groups按SA final、LEA first/final、Full first/final；每组rows按debian、sec_ex21、bgb、cuad。",
        "root": "root_rank是注入root_node在原始完整ranking中的1起始位置；Root@k为rank<=k；MRR是4例1/rank均值。",
        "risk": "risk_nodes是每例2个标记风险端点（含root）。Risk-any/All分别表示H保留至少一个/全部端点；endpoint_recall=|H∩risk_nodes|/|risk_nodes|。",
        "evidence": "新增离线诊断：evidence_nodes在SEC/BGB额外包含1个bridge；Evidence-all表示这些标记节点全部在H中，evidence_recall=|H∩evidence_nodes|/|evidence_nodes|。不等于关系、方向或论证正确。",
        "averaging": "所有rate和MRR固定以4例为分母，失败计0；两类recall按例宏平均。H与compression只对有效输出平均。本次20行均有效。",
        "native_output": "使用原生H；SA=evidence_risk_subgraph_nodes，LEA=lea_risk_subgraph_nodes，Full=direct_risk_subgraph_nodes。未施加共同cap，未使用GT锚定旧risk_subgraph_nodes。",
        "compression": "1-|H|/|SCC|；宏平均不是汇总所有节点后再求比率。",
        "first": "只取candidate_index=1，失败不换为首个成功；first费用与耗时是final流程子集，不能与final重复相加。",
        "time": "elapsed_sec是该行所属请求首次reserve到最后finish的ledger墙钟跨度，包含间隔与重试；first依usage_before/after.accounted_tokens定位。不是独立服务延迟基准。",
        "finance": "按冻结输入$2.50/M、输出$10.00/M使用量估值；finance只累计三个实际arm，first诊断不重复计入。wall_minutes为全部请求最早reserve到最晚finish，各arm并发不可将臂耗时求和。",
        "budget": "每臂每例上限160K tokens，实际用量不等；候选次数上限与保守评选预留均可导致提前停止，预留不是实耗。CUAD LEA仅1候选、无judge。",
        "counts": "candidate_count为已完成有效候选数（本次等于尝试数）；SA为null。rollouts仅SA记录已完成轮数，其余为null。",
        "label_limit": "非gold节点未全面标负且可能是必要上下文，不能把额外H节点当误报；不能据此估计自然precision/F1/FPR。",
        "interpretation": "四例不能支持显著性或泛化结论。SA端点All=4/4而Evidence-all=2/4；新指标不能混称完整真实证据。",
    }
    output = {
        "n_cases": len(plan), "domains": DOMAINS,
        "groups": groups, "rows": rows,
        "finance": {"total_tokens": finance_usage["total_tokens"], "calls": finance_usage["calls"],
                    "cost_usd": finance_usage["cost_usd"], "wall_minutes": finance_usage["elapsed_sec"] / 60},
        "provenance": {
            "source_root": str(RUN_DIR),
            "input_sha256": dict(sorted(INPUT_HASHES.items())),
            "build_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_summary_checked": True,
            "settled_ledger_calls": len(calls),
            "provider_model_labels": original["finance"]["returned_model_labels"],
        },
        "definition_notes": notes,
    }
    atomic_write(OUTPUT_DIR / "metrics.json", json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    atomic_write(OUTPUT_DIR / "metrics_by_case.csv", csv_text(rows))
    atomic_write(OUTPUT_DIR / "metrics_summary.csv", csv_text(groups))
    print(json.dumps({"groups": len(groups), "rows": len(rows), "finance": output["finance"],
                      "input_files_hashed": len(INPUT_HASHES), "output_dir": str(OUTPUT_DIR)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

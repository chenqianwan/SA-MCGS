#!/usr/bin/env python3
"""Freeze a read-only, request-bound recovery scope; never issue API requests."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HTTP503 = re.compile(r"(?:^|[;\s])http=503(?:;|\s|$)")
ERROR_REQUEST = re.compile(r"(?:^|[;\s])request=([^;\s]+)")


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(root=ROOT):
    root = Path(root).resolve()
    output = root / "recovery_503_v1"
    pilot = root.parent / "equal_budget_api10_20261011"
    allowed_roots = (root, pilot)
    source_hashes = {}

    def bind(path, expected_sha=None):
        path = Path(path).resolve()
        if not any(path.is_relative_to(base) for base in allowed_roots):
            raise ValueError(f"Source outside approved experiment roots: {path}")
        if not path.is_file():
            raise ValueError(f"Missing source: {path}")
        sha = digest(path)
        if expected_sha is not None and sha != expected_sha:
            raise ValueError(f"Source hash does not match merged record: {path}")
        if str(path) in source_hashes and source_hashes[str(path)] != sha:
            raise ValueError(f"Source changed during preparation: {path}")
        source_hashes[str(path)] = sha
        return path

    def read(path, expected_sha=None):
        return json.loads(bind(path, expected_sha).read_text(encoding="utf-8"))

    merge_path = root / "reports/case_results.json"
    merged = read(merge_path)
    summary = read(root / "reports/summary.json")
    if summary.get("case_results_sha256") != source_hashes[str(merge_path)]:
        raise ValueError("Summary is not bound to the current merged case file")
    if not summary.get("complete"):
        raise ValueError("Original experiment is not complete")
    for name in ("pilot_results.json", "main_sa_references.json", "case_plans.json",
                 "budgets.json", "protocol.json", "scope_manifest.json"):
        bind(root / name)
    bind(pilot / "methods_full.py")
    bind(Path(__file__).resolve())
    identities = [(r["model"], r["case_uid"], r["method"]) for r in merged]
    if len(merged) != 480 or len(set(identities)) != 480:
        raise ValueError("Expected 480 unique merged method-case records")
    invalid = [r for r in merged if r["method"] != "sa-mcgs"
               and r["reporting_state"] == "empty_output"]
    valid = [r for r in merged if r["method"] != "sa-mcgs"
             and r["reporting_state"] == "valid_output"]
    if len(invalid) != 170 or len(valid) != 150:
        raise ValueError("Expected the frozen 170 invalid and 150 valid baseline cells")

    def source_final(row):
        # Pilot slots are local pilot slots: never infer an api80 path from one.
        bind(row["source"]["path"], row["source"]["sha256"])
        if row["origin"] == "remaining70":
            path = Path(row["source"]["path"]).resolve()
            if not path.is_relative_to(root / "results") or path.name != "final.json":
                raise ValueError("Remaining70 row does not point to its actual final.json")
        elif row["origin"] == "retained_pilot10":
            source = row["raw"]["reporting_source"]
            path = bind(source["path"], source["sha256"])
            if not path.is_relative_to(pilot) or path.name != "final.json":
                raise ValueError("Pilot row does not point to its actual pilot final.json")
        else:
            raise ValueError(f"Unexpected baseline origin: {row['origin']}")
        raw = read(path)
        for key in ("model", "method", "case_uid"):
            if raw.get(key) != row[key]:
                raise ValueError(f"Source identity mismatch ({key}): {path}")
        if raw.get("case_slot") != row["raw"].get("case_slot"):
            raise ValueError(f"Source slot mismatch: {path}")
        return path

    protected_valid = []
    for row in valid:
        final = source_final(row)
        protected_valid.append({k: row[k] for k in ("model", "method", "case_uid", "origin")}
                               | {"source_final": str(final), "sha256": digest(final)})

    def ledger_calls(folder):
        path = bind(folder / "ledger.jsonl")
        states, order = {}, []
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            call_id = event.get("call_id")
            if event.get("event") == "reserve":
                if call_id in states:
                    raise ValueError(f"Duplicate reservation: {path}/{call_id}")
                order.append(call_id)
            if call_id and event.get("event") in {"reserve", "finish"}:
                states.setdefault(call_id, {}).update(event)
        calls, total, last_finish = [], 0, 0
        for call_id in order:
            state = states[call_id]
            if state.get("event") != "finish":
                raise ValueError(f"Unsettled source call: {path}/{call_id}")
            if state.get("time_unix", 0) < last_finish:
                raise ValueError(f"Nonsequential source ledger: {path}")
            last_finish = state.get("time_unix", 0)
            cache_path = Path(state["cache_file"])
            if not cache_path.is_absolute():
                cache_path = folder / cache_path
            cache_path = bind(cache_path)
            raw = read(cache_path)
            for key in ("call_id", "request_key", "request_hash"):
                if raw.get(key) != state.get(key):
                    raise ValueError(f"Call/cache identity mismatch ({key}): {cache_path}")
            if state["status"] == "completed_with_usage":
                if raw.get("status") != "response_received":
                    raise ValueError(f"Missing reusable successful response: {cache_path}")
                cost = state["actual_total_tokens"]
            else:
                cost = state["reserved_tokens"]
            if not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
                raise ValueError(f"Invalid accounted token cost: {cache_path}")
            if state.get("http_status") == 503:
                if state["status"] != "unknown_failure" or raw.get("http_status") != 503:
                    raise ValueError(f"503 status mismatch: {cache_path}")
            calls.append({"path": str(cache_path), "state": state,
                          "accounted_before": total, "accounted_after": total + cost})
            total += cost
        if len(states) != len(order):
            raise ValueError(f"Ledger contains call without reservation: {path}")
        return calls, total

    entries, excluded, triage = [], [], []
    for row in sorted(invalid, key=lambda r: (r["model"], r["main_case_order"], r["method"])):
        final = source_final(row)
        folder = final.parent
        calls, accounted = ledger_calls(folder)
        candidates = []
        for path in sorted(folder.glob("candidate_[0-9]*.json")):
            candidate = read(path)
            if path.name != f"candidate_{candidate['candidate_index']:04d}.json":
                raise ValueError(f"Candidate index/path mismatch: {path}")
            candidates.append((path, candidate))
        for name in ("inference.json", "judge_candidate_mapping.json", "judge_prompt.txt", "judge_response.json"):
            if (folder / name).is_file():
                bind(folder / name)
        selectors = [c for c in calls if c["state"]["phase"] == "selector"]
        complete = [{"candidate_index": c["candidate_index"], "path": str(p)}
                    for p, c in candidates if c["status"] == "complete"]
        identity = {k: row[k] for k in ("model", "method", "case_uid", "origin", "main_case_order")}
        identity |= {"case_slot": row["raw"]["case_slot"], "source_dir": str(folder),
                     "source_final": str(final), "source_final_sha256": digest(final)}
        common = identity | {"original_B": row["raw"]["B"],
                             "original_status": row["status"],
                             "original_usage": row["raw"].get("usage"),
                             "complete_pool_candidates": complete,
                             "complete_candidate_paths": [c["path"] for c in complete],
                             "candidates": [], "selector_calls": []}
        if selectors and selectors[-1]["state"].get("http_status") == 503:
            # A failed final selection never authorizes further candidate work.
            if calls[-1] is not selectors[-1] or len(complete) < 2:
                raise ValueError(f"Invalid selector-only source: {folder}")
            for call in selectors[:-1]:
                if call["state"]["status"] != "completed_with_usage":
                    raise ValueError(f"Unresolved selector prefix: {folder}")
            mapping_path = folder / "judge_candidate_mapping.json"
            mapping = read(mapping_path)
            if set(mapping.values()) != {c["candidate_index"] for c in complete}:
                raise ValueError(f"Judge pool does not match complete candidates: {folder}")
            entry = common | {"mode": "selector_only",
                              "selector_calls": [c["path"] for c in selectors],
                              "judge_candidate_mapping_path": str(mapping_path),
                              "judge_prompt_path": str(folder / "judge_prompt.txt")}
            entries.append(entry)
        else:
            targets = []
            for path, candidate in candidates:
                error = candidate.get("error", "")
                if candidate["status"] != "scientific_failure" or not HTTP503.search(error):
                    continue
                start = candidate["usage_before"]["accounted_tokens"]
                stop = candidate["usage_after"]["accounted_tokens"]
                segment = [c for c in calls if c["accounted_before"] >= start
                           and c["accounted_after"] <= stop]
                if not segment or segment[0]["accounted_before"] != start or segment[-1]["accounted_after"] != stop:
                    raise ValueError(f"Candidate accounting boundaries do not bind calls: {path}")
                failed = segment[-1]["state"]
                request = ERROR_REQUEST.search(error)
                if (failed.get("http_status") != 503 or failed["status"] != "unknown_failure"
                        or not request or failed["request_key"] != request.group(1)
                        or any(c["state"]["phase"] != "candidate" for c in segment)
                        or any(c["state"]["status"] != "completed_with_usage" for c in segment[:-1])):
                    raise ValueError(f"Candidate is not a successful prefix ending in its explicit 503: {path}")
                if candidate.get("tokens_used") != stop - start:
                    raise ValueError(f"Candidate token delta mismatch: {path}")
                targets.append({"candidate_index": candidate["candidate_index"], "path": str(path),
                                "historical_call_files": [c["path"] for c in segment],
                                "accounted_before": start, "accounted_after": stop,
                                "failed_call_id": failed["call_id"],
                                "failed_request_key": failed["request_key"],
                                "failed_request_hash": failed["request_hash"],
                                "failed_call_file": segment[-1]["path"],
                                "historical_successful_calls": len(segment) - 1,
                                "retained_503_reservation": failed["reserved_tokens"]})
            if targets:
                if selectors:
                    raise ValueError(f"Candidate recovery would alter a completed selector: {folder}")
                entry = common | {"mode": "candidate_recovery", "candidates": targets}
                entries.append(entry)
            else:
                reason = ("non503_pilot_failure_preserved" if row["origin"] == "retained_pilot10"
                          else "non503_connection_or_schema_failure_preserved")
                entry = identity | {"mode": "excluded", "reason": reason,
                                    "original_status": row["status"]}
                excluded.append(entry)
        triage.append(identity | {"mode": entry["mode"]})

    counts = {"original_invalid_cells": len(invalid), "protected_valid_baseline_cells": len(valid),
              "fixed_historical_sa_cells": 160, "eligible_cells": len(entries),
              "selector_only_cells": sum(e["mode"] == "selector_only" for e in entries),
              "candidate_recovery_cells": sum(e["mode"] == "candidate_recovery" for e in entries),
              "excluded_non503_cells": len(excluded),
              "eligible_candidates": sum(len(e["candidates"]) for e in entries),
              "selector_call_files": sum(len(e["selector_calls"]) for e in entries),
              "existing_complete_pool_candidates": sum(len(e["complete_pool_candidates"]) for e in entries)}
    expected = dict(eligible_cells=161, selector_only_cells=42, candidate_recovery_cells=119,
                    excluded_non503_cells=9, eligible_candidates=1284, selector_call_files=42,
                    existing_complete_pool_candidates=201)
    if any(counts[k] != v for k, v in expected.items()):
        raise ValueError(f"Unexpected recovery scope: {counts}")
    scope = {"schema_version": "equal_budget_api80.recovery_503.scope.v1",
             "original_merged_results": str(merge_path),
             "max_new_transport_retries_per_503_request": 2,
             "scoring_policy": "Non503 failures remain unchanged; empty outputs score compression=1 and all hit metrics=0.",
             "selection_policy": "Selector-only cells reuse the original complete pool and issue no new candidate evaluations.",
             "budget_policy": "Preparation preserves all historical usage and 503 reservations; it does not authorize or implement a budget reset.",
             "counts": counts, "entries": entries, "excluded": excluded,
             "invalid_cells": triage, "protected_valid_cells": protected_valid,
             "source_hashes": dict(sorted(source_hashes.items()))}
    # Recheck every bound file before freezing; this also catches concurrent edits.
    for name, sha in source_hashes.items():
        if digest(name) != sha:
            raise ValueError(f"Source changed during preparation: {name}")
    lines = ["# HTTP 503 恢复范围核验", "", "本步骤只读取已有结果并冻结恢复范围，不发起 API 请求。", "",
             "- 原始无效基线：170 项；历史有效基线 150 项保持不变；历史 SA 参考 160 项保持不变。",
             "- 42 项只重试选择器，复用原有 201 个完整候选，不补跑或新建候选。",
             "- 119 项恢复候选阶段；严格选取 scientific_failure 且错误明确为 HTTP 503 的 1,284 个候选。",
             "- 其余 9 项按原结果保留，不恢复。其中包含试跑阶段的 GPT-4o Full-SCC 第 11、12 项。",
             "- 每个恢复候选的调用范围由 usage_before/usage_after.accounted_tokens 与原始账本累计计费对齐；末次调用必须与错误中的 request key 一致并明确返回 503。",
             "- 已成功的调用从原始缓存复用；解析失败、HTTP 400、连接错误等不作为新增重试依据。",
             "- 每个已确认的 503 请求最多新增两次传输重试。此准备步骤不清空历史用量或 503 预留额度。",
             "- 所有读取的原始最终结果、候选、调用缓存、账本和合并结果均记录 SHA-256。试跑路径来自其 reporting_source，绝不按试跑序号映射到新增 70 项目录。", "",
             "## 按模型和方法汇总", "", "| 模型 | 方法 | 候选恢复 | 仅选择器 | 不恢复 |",
             "|---|---|---:|---:|---:|"]
    grouped = Counter((r["model"], r["method"], r["mode"]) for r in triage)
    for model in ("gpt-4o", "gemini-2.5-pro"):
        for method in ("lea", "full-scc"):
            lines.append(f"| {model} | {method} | {grouped[model, method, 'candidate_recovery']} | {grouped[model, method, 'selector_only']} | {grouped[model, method, 'excluded']} |")
    lines += ["", "## 保留原结果的 9 项", "", "| 来源 | 模型 | 方法 | 原目录序号 | 主实验顺序 |", "|---|---|---|---:|---:|"]
    for entry in excluded:
        lines.append(f"| {entry['origin']} | {entry['model']} | {entry['method']} | {entry['case_slot']} | {entry['main_case_order']} |")
    lines += ["", f"已冻结 {len(source_hashes)} 个源文件的校验值。", ""]
    output.mkdir(parents=True, exist_ok=True)
    for name, text in (("scope.json", encode(scope)), ("TRIAGE_ZH.md", "\n".join(lines))):
        path = output / name
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise ValueError(f"Refusing to replace a different frozen recovery artifact: {path}")
        else:
            path.write_text(text, encoding="utf-8")
    return scope


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = prepare(args.root)
    print(encode(result["counts"]), end="")

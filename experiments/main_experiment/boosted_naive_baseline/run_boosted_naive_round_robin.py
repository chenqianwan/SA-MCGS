#!/usr/bin/env python3
"""Budget-matched boosted Naive baseline.

This script deliberately writes into experiments/main_experiment only. It does
not touch paper/, paper figures, or the locked main-result files.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "cross_domain"))

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from src.models.graph import DependencyGraph, SCCInfo
from src.llm.openai_client import OpenAIClient

from experiments.cross_domain.run_cross_domain import (
    load_debian_graph,
    load_sec_graph,
    load_wikipedia_graph,
)
from experiments.cross_domain.run_cross_domain_battle import (
    BATTLE_MODELS,
    XHUB_BASE_URL,
    add_direct_subgraph_retention_metrics,
    add_rank_metrics,
    add_structural_rank_metrics,
    assert_original_scc_content,
    get_injection_metadata,
    load_bgb_graph,
    load_cuad_graph,
    reorder_scc_for_memory_stress,
    run_naive,
)
from experiments.cross_domain.inject_defect import inject_defect


THIS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = THIS_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_STATUS = (
    REPO_ROOT
    / "experiments"
    / "cross_domain"
    / "results"
    / "critical_qwen_current_full80_b60_severity_grid_status.json"
)
RAW_JSONL = RESULTS_DIR / "boosted_naive_raw_attempts.jsonl"
STATUS_JSON = RESULTS_DIR / "boosted_naive_round_robin_status.json"
SUMMARY_CSV = RESULTS_DIR / "boosted_naive_top3_summary.csv"
REPORT_MD = RESULTS_DIR / "BOOSTED_NAIVE_BASELINE_REPORT.md"


QUOTA_PATTERNS = (
    "quota",
    "insufficient",
    "balance",
    "billing",
    "credit",
    "402",
    "429",
    "rate limit",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def jsonl_append(path: Path, obj: Any) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def safe_bool(x: Any) -> bool:
    return bool(x) if x is not None else False


def quota_like(message: str) -> bool:
    lower = (message or "").lower()
    return any(p in lower for p in QUOTA_PATTERNS)


def result_file_for_task(task: dict) -> Path | None:
    raw = task.get("result_file")
    if not raw:
        return None
    p = Path(raw)
    if p.exists():
        return p
    alt = REPO_ROOT / raw
    return alt if alt.exists() else None


def build_blocks(status_path: Path, max_blocks: int | None = None) -> list[dict]:
    status = load_json(status_path)
    blocks: list[dict] = []
    for task in status.get("tasks", []):
        if task.get("status") != "done":
            continue
        result_path = result_file_for_task(task)
        if result_path is None:
            continue
        records = load_json(result_path)
        naive = next((r for r in records if r.get("method") == "naive"), None)
        if not naive:
            continue
        block = {
            "block_id": len(blocks) + 1,
            "source_task_id": task.get("task_id"),
            "domain": task.get("domain"),
            "requested_size": task.get("size"),
            "actual_size": naive.get("scc_size"),
            "template": task.get("template") or naive.get("injected_conflict_template") or "handoff_invariant",
            "severity": task.get("severity") or "critical",
            "compression_profile": task.get("compression_profile") or "current",
            "scc_id": naive.get("scc_id"),
            "scc_clause_ids": naive.get("scc_clause_ids") or [],
            "source_result_file": str(result_path),
        }
        if block["domain"] and block["scc_id"] and block["scc_clause_ids"]:
            blocks.append(block)
        if max_blocks and len(blocks) >= max_blocks:
            break
    return blocks


def load_domain_graphs(domains: set[str]) -> dict[str, DependencyGraph]:
    loaders = {
        "debian": load_debian_graph,
        "sec_ex21": load_sec_graph,
        "wikipedia": load_wikipedia_graph,
        "bgb": load_bgb_graph,
        "cuad": load_cuad_graph,
    }
    graphs: dict[str, DependencyGraph] = {}
    for domain in sorted(domains):
        if domain not in loaders:
            raise ValueError(f"Unsupported domain: {domain}")
        graphs[domain] = loaders[domain]()
    return graphs


def make_scc(graph: DependencyGraph, block: dict) -> SCCInfo:
    ids = list(block["scc_clause_ids"])
    scc_set = set(ids)
    edges = [e for e in graph.edges if e.source in scc_set and e.target in scc_set]
    return SCCInfo(
        id=str(block["scc_id"]),
        clause_ids=ids,
        internal_edges=edges,
        size=len(ids),
    )


def make_llm(model_name: str) -> OpenAIClient:
    model_lookup = {m["name"]: m["model_id"] for m in BATTLE_MODELS}
    if model_name not in model_lookup:
        raise ValueError(f"Unknown model name: {model_name}")
    return OpenAIClient(
        {
            "provider": "openai",
            "api_key_env": "XHUB_API_KEY",
            "base_url": XHUB_BASE_URL,
            "model": model_lookup[model_name],
            "timeout": 300,
        }
    )


def attempt_key(block_id: int, model: str, attempt_index: int) -> str:
    return f"{block_id}::{model}::{attempt_index}"


def read_completed_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.exists():
        return keys
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            keys.add(attempt_key(rec["block_id"], rec["model"], rec["attempt_index"]))
    return keys


def trial_temperature(attempt_index: int, schedule: list[float]) -> float:
    return schedule[(attempt_index - 1) % len(schedule)]


def attach_metrics(result: dict, injected_id: str, injection_metadata: dict) -> dict:
    add_rank_metrics(result, injected_id)
    ranking_ids = [cid for cid, _ in result.get("ranking", [])]
    result["top1_hit"] = bool(ranking_ids and ranking_ids[0] == injected_id)
    result["top3_hit"] = injected_id in ranking_ids[:3]
    result["root_rank"] = result.get("injected_rank")
    result["root_top1_hit"] = result["top1_hit"]
    result["root_top3_hit"] = result["top3_hit"]
    add_structural_rank_metrics(result, injection_metadata)
    add_direct_subgraph_retention_metrics(result, injection_metadata)
    return result


def self_selection_score(result: dict) -> float:
    """Select good samples without peeking at injected ground truth."""
    if result.get("error"):
        return -1e9
    score = 0.0
    score += 2.0 if result.get("ranking_complete") else 0.0
    score += 2.0 if result.get("direct_subgraph_complete_parse") else 0.0
    score += min(1.5, float(result.get("ranking_score_spread") or 0.0))
    score += min(1.5, float(result.get("risk_factor_weight_sum") or 0.0))
    subgraph_size = float(result.get("direct_risk_subgraph_size") or 0.0)
    scc_size = float(result.get("scc_size") or 1.0)
    if 0 < subgraph_size <= scc_size:
        ratio = subgraph_size / scc_size
        score += 1.0 if 0.10 <= ratio <= 0.65 else 0.25
    rationale = result.get("direct_risk_subgraph_rationale") or ""
    score += min(0.5, len(str(rationale)) / 800.0)
    return score


def oracle_score(result: dict) -> float:
    if result.get("error"):
        return -1e9
    return (
        3.0 * float(safe_bool(result.get("root_top3_hit")))
        + 2.0 * float(safe_bool(result.get("direct_contains_all_risk_nodes")))
        + 1.0 * float(safe_bool(result.get("direct_contains_any_risk_node")))
        + 0.25 * float(result.get("direct_compression_ratio") or 0.0)
    )


def metric_row_for_selected(block: dict, model: str, selector: str, selected: list[dict], all_attempts: list[dict]) -> dict:
    valid_count = sum(1 for r in all_attempts if not r.get("error"))
    target = {
        "block_id": block["block_id"],
        "domain": block["domain"],
        "actual_size": block["actual_size"],
        "requested_size": block["requested_size"],
        "template": block["template"],
        "model": model,
        "selector": selector,
        "attempt_count": len(all_attempts),
        "valid_attempt_count": valid_count,
        "selected_count": len(selected),
    }
    if not selected:
        target.update(
            {
                "root_at3": 0.0,
                "risk_any": 0.0,
                "risk_all": 0.0,
                "compression": 0.0,
                "avg_total_tokens": 0.0,
                "avg_prompt_tokens": 0.0,
                "avg_completion_tokens": 0.0,
            }
        )
        return target
    target.update(
        {
            "root_at3": sum(float(safe_bool(r.get("root_top3_hit"))) for r in selected) / len(selected),
            "risk_any": sum(float(safe_bool(r.get("direct_contains_any_risk_node"))) for r in selected) / len(selected),
            "risk_all": sum(float(safe_bool(r.get("direct_contains_all_risk_nodes"))) for r in selected) / len(selected),
            "compression": sum(float(r.get("direct_compression_ratio") or 0.0) for r in selected) / len(selected),
            "avg_total_tokens": sum(float((r.get("llm_usage") or {}).get("total_tokens") or 0.0) for r in selected) / len(selected),
            "avg_prompt_tokens": sum(float((r.get("llm_usage") or {}).get("prompt_tokens") or 0.0) for r in selected) / len(selected),
            "avg_completion_tokens": sum(float((r.get("llm_usage") or {}).get("completion_tokens") or 0.0) for r in selected) / len(selected),
        }
    )
    return target


def load_attempt_records(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def summarize(blocks: list[dict], models: list[str], top_k: int) -> dict:
    records = load_attempt_records(RAW_JSONL)
    by_key: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for rec in records:
        by_key[(rec["block_id"], rec["model"])].append(rec)

    rows: list[dict] = []
    block_lookup = {b["block_id"]: b for b in blocks}
    for block in blocks:
        for model in models:
            attempts = sorted(
                by_key.get((block["block_id"], model), []),
                key=lambda r: r.get("attempt_index", 0),
            )
            valid = [r for r in attempts if not r.get("error")]
            self_selected = sorted(valid, key=self_selection_score, reverse=True)[:top_k]
            oracle_selected = sorted(valid, key=oracle_score, reverse=True)[:top_k]
            rows.append(metric_row_for_selected(block, model, "self_top3", self_selected, attempts))
            rows.append(metric_row_for_selected(block, model, "oracle_top3", oracle_selected, attempts))

    if rows:
        with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    aggregate: dict[str, dict[str, float]] = {}
    for selector in ("self_top3", "oracle_top3"):
        subset = [r for r in rows if r["selector"] == selector]
        denom = len(subset) or 1
        aggregate[selector] = {
            "n": len(subset),
            "root_at3": sum(r["root_at3"] for r in subset) / denom,
            "risk_any": sum(r["risk_any"] for r in subset) / denom,
            "risk_all": sum(r["risk_all"] for r in subset) / denom,
            "compression": sum(r["compression"] for r in subset) / denom,
            "valid_attempt_mean": sum(r["valid_attempt_count"] for r in subset) / denom,
            "avg_total_tokens": sum(r["avg_total_tokens"] for r in subset) / denom,
        }

    write_report(records, rows, aggregate, top_k)
    return {"records": len(records), "rows": len(rows), "aggregate": aggregate}


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def write_report(records: list[dict], rows: list[dict], aggregate: dict, top_k: int) -> None:
    errors = [r for r in records if r.get("error")]
    total_tokens = sum(float((r.get("llm_usage") or {}).get("total_tokens") or 0) for r in records)
    prompt_tokens = sum(float((r.get("llm_usage") or {}).get("prompt_tokens") or 0) for r in records)
    completion_tokens = sum(float((r.get("llm_usage") or {}).get("completion_tokens") or 0) for r in records)

    lines = [
        "# Boosted Naive Baseline Report",
        "",
        "状态：独立补充实验报告；不更新 paper / LaTeX / paper figures。",
        "",
        f"- Raw attempts: `{len(records)}`",
        f"- Top-k aggregation: `Top-{top_k}`",
        f"- Errors recorded in denominator: `{len(errors)}`",
        f"- Observed tokens: prompt `{prompt_tokens:,.0f}`, completion `{completion_tokens:,.0f}`, total `{total_tokens:,.0f}`",
        "",
        "## Aggregate",
        "",
        "| Selector | N | Root@3 | Risk-any | Risk-all | Compression | Mean valid attempts | Avg selected tokens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for selector, vals in aggregate.items():
        lines.append(
            f"| {selector} | {int(vals['n'])} | {pct(vals['root_at3'])} | {pct(vals['risk_any'])} | "
            f"{pct(vals['risk_all'])} | {pct(vals['compression'])} | {vals['valid_attempt_mean']:.2f} | "
            f"{vals['avg_total_tokens']:,.0f} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `self_top3` 不看 GT，只按 JSON 完整性、模型自报风险强度、证据一致性和子图合理性选择样本。",
            "- `oracle_top3` 看真实指标，只作为 boosted Naive 的上界，不应作为默认论文主结果。",
            "- 如果某个 model-case 没有任何有效输出，则该 case 记为失败。",
        ]
    )
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run_one_attempt(
    block: dict,
    model_name: str,
    attempt_index: int,
    temperature: float,
    graphs: dict[str, DependencyGraph],
) -> dict:
    domain = block["domain"]
    graph = copy.deepcopy(graphs[domain])
    scc = make_scc(graph, block)
    assert_original_scc_content(graph, scc, domain)
    graph, injected_id = inject_defect(
        graph,
        scc,
        domain,
        seed=42,
        profile="memory_stress",
        conflict_template=block["template"],
        conflict_severity=block["severity"],
    )
    scc = reorder_scc_for_memory_stress(scc, injected_id)
    injection_metadata = get_injection_metadata(graph, injected_id)
    llm = make_llm(model_name)
    try:
        result = await run_naive(
            llm=llm,
            model_name=model_name,
            domain=domain,
            graph=graph,
            scc=scc,
            naive_profile="direct_subgraph",
            injected_id=injected_id,
            temperature=temperature,
        )
        result.update(
            {
                "boosted_naive": True,
                "boosted_attempt_index": attempt_index,
                "boosted_temperature": temperature,
                "aggregation_policy": "top3_mean",
                "inject_mode": True,
                "injected_node": injected_id,
                "inject_profile": "memory_stress",
                "cycle_source": "real_long",
                **injection_metadata,
            }
        )
        attach_metrics(result, injected_id, injection_metadata)
        return result
    finally:
        await llm.close()


async def run_round_robin(args: argparse.Namespace) -> None:
    models = args.models
    schedule = [float(x) for x in args.temperatures.split(",")]
    blocks = build_blocks(args.status_path, max_blocks=args.max_blocks)
    if not blocks:
        raise RuntimeError(f"No blocks found in {args.status_path}")
    graphs = load_domain_graphs({b["domain"] for b in blocks})

    planned_keys = [
        attempt_key(block["block_id"], model, attempt_index)
        for attempt_index in range(1, args.attempts_per_model_case + 1)
        for block in blocks
        for model in models
    ]
    completed = read_completed_keys(RAW_JSONL)
    remaining = [k for k in planned_keys if k not in completed]

    plan = {
        "status": "dry_run" if args.dry_run else "running",
        "updated_at": time.time(),
        "blocks": len(blocks),
        "models": models,
        "attempts_per_model_case": args.attempts_per_model_case,
        "top_k": args.top_k,
        "temperature_schedule": schedule,
        "planned_attempts": len(planned_keys),
        "completed_attempts": len(completed),
        "remaining_attempts": len(remaining),
        "raw_jsonl": str(RAW_JSONL),
        "summary_csv": str(SUMMARY_CSV),
        "report_md": str(REPORT_MD),
    }
    dump_json(STATUS_JSON, plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2), flush=True)
    if args.dry_run:
        return

    sem = asyncio.Semaphore(args.concurrency)
    write_lock = asyncio.Lock()
    stop_event = asyncio.Event()
    done_counter = len(completed)

    block_lookup = {b["block_id"]: b for b in blocks}
    model_lookup = {m: m for m in models}

    async def worker(key: str) -> None:
        nonlocal done_counter
        block_id_raw, model, attempt_raw = key.split("::")
        block = block_lookup[int(block_id_raw)]
        attempt_index = int(attempt_raw)
        temperature = trial_temperature(attempt_index, schedule)
        if stop_event.is_set():
            return
        async with sem:
            if stop_event.is_set():
                return
            started_at = time.time()
            record: dict[str, Any] = {
                "block_id": block["block_id"],
                "source_task_id": block.get("source_task_id"),
                "domain": block["domain"],
                "requested_size": block["requested_size"],
                "actual_size": block["actual_size"],
                "scc_id": block["scc_id"],
                "scc_clause_ids": block["scc_clause_ids"],
                "template": block["template"],
                "severity": block["severity"],
                "compression_profile": block["compression_profile"],
                "model": model_lookup[model],
                "attempt_index": attempt_index,
                "temperature": temperature,
                "started_at": started_at,
            }
            try:
                result = await run_one_attempt(block, model, attempt_index, temperature, graphs)
                record.update(result)
                record["error"] = None
            except Exception as exc:
                message = str(exc)
                record.update(
                    {
                        "error": message,
                        "error_type": type(exc).__name__,
                        "quota_like_error": quota_like(message),
                    }
                )
                if quota_like(message):
                    stop_event.set()
            record["ended_at"] = time.time()
            record["wall_time"] = record["ended_at"] - started_at
            async with write_lock:
                jsonl_append(RAW_JSONL, record)
                done_counter += 1
                if done_counter % args.status_every == 0 or record.get("error"):
                    status = {
                        **plan,
                        "status": "quota_stopped" if stop_event.is_set() else "running",
                        "updated_at": time.time(),
                        "completed_attempts": done_counter,
                        "remaining_attempts": max(0, len(planned_keys) - done_counter),
                        "last_error": record.get("error"),
                    }
                    dump_json(STATUS_JSON, status)
                    summarize(blocks, models, args.top_k)
                    print(
                        f"[{done_counter}/{len(planned_keys)}] "
                        f"{record['domain']} size={record['actual_size']} "
                        f"{record['model']} attempt={attempt_index} "
                        f"temp={temperature} error={bool(record.get('error'))}",
                        flush=True,
                    )

    for attempt_index in range(1, args.attempts_per_model_case + 1):
        round_keys = [
            attempt_key(block["block_id"], model, attempt_index)
            for block in blocks
            for model in models
            if attempt_key(block["block_id"], model, attempt_index) not in completed
        ]
        if not round_keys:
            continue
        print(f"Starting round {attempt_index}: {len(round_keys)} attempts", flush=True)
        for i in range(0, len(round_keys), max(1, args.batch_size)):
            if stop_event.is_set():
                break
            await asyncio.gather(*(worker(k) for k in round_keys[i : i + args.batch_size]))
        summarize(blocks, models, args.top_k)
        completed = read_completed_keys(RAW_JSONL)
        if stop_event.is_set():
            break

    final_status = {
        **plan,
        "status": "quota_stopped" if stop_event.is_set() else "done",
        "updated_at": time.time(),
        "completed_attempts": len(read_completed_keys(RAW_JSONL)),
        "remaining_attempts": max(0, len(planned_keys) - len(read_completed_keys(RAW_JSONL))),
    }
    dump_json(STATUS_JSON, final_status)
    summary = summarize(blocks, models, args.top_k)
    print(json.dumps({"final_status": final_status, "summary": summary}, ensure_ascii=False, indent=2), flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["gpt-4o", "deepseek-v3", "qwen2.5-72b", "gemini-2.5-pro"],
    )
    parser.add_argument("--attempts-per-model-case", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--temperatures", default="0.0,0.2,0.4,0.7,1.0")
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--status-every", type=int, default=20)
    parser.add_argument("--max-blocks", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.top_k != 3:
        print(f"Warning: this boosted run is designed for Top-3, got --top-k={args.top_k}", flush=True)
    asyncio.run(run_round_robin(args))


if __name__ == "__main__":
    main()

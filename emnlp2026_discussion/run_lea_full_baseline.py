#!/usr/bin/env python3
"""Run the GraphRAG-style Local Evidence Aggregation baseline on all cases.

This runner is discussion-oriented:
- reads every selected row from case_composition.csv, without domain/size de-dup;
- runs only the decomposed graph-aware LEA baseline;
- writes one JSON per case and resumes from completed files;
- avoids mutating global ground-truth state, so case-level concurrency is safe.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import csv
import json
import os
import re
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "cross_domain"))

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from emnlp2026_discussion import run_cost_audit_clean as cost


DISCUSSION_DIR = REPO_ROOT / "emnlp2026_discussion"
DEFAULT_CASE_CSV = DISCUSSION_DIR / "case_composition.csv"
DEFAULT_RUNS_DIR = DISCUSSION_DIR / "baseline_runs"
DEFAULT_MODELS = ["gpt-4o", "deepseek-v3", "qwen2.5-72b", "gemini-2.5-pro"]


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LEA Full Baseline Progress</title>
  <style>
    :root { color-scheme: light; --ink: #12201a; --muted: #69766d; --line: #d8ded6; --fill: #2f7d73; --bg: #fbfcfa; }
    body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { width: min(1220px, calc(100vw - 32px)); margin: 28px auto 48px; }
    h1 { margin: 0; font-size: clamp(30px, 4vw, 44px); letter-spacing: 0; }
    .sub { color: var(--muted); font-size: 22px; font-weight: 700; margin-top: 2px; }
    .top { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 28px; }
    .refresh { text-align: right; color: var(--muted); font-weight: 700; font-size: 24px; }
    .panel { background: white; border: 1px solid var(--line); border-radius: 8px; padding: 20px; box-shadow: 0 1px 2px rgba(18,32,26,.04); }
    .progress-row { display: flex; justify-content: space-between; gap: 18px; align-items: center; }
    .badge { border-radius: 999px; background: #dcefed; color: #1e625d; padding: 8px 14px; font-weight: 800; }
    .bar { height: 18px; border-radius: 999px; background: #e8ece5; border: 1px solid #d7ddd2; overflow: hidden; margin-top: 22px; }
    .bar span { display: block; height: 100%; background: linear-gradient(90deg, #18796f, #5e9b79); }
    .cards { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 16px; margin: 22px 0 28px; }
    .card { background: white; border: 1px solid var(--line); border-radius: 8px; padding: 18px; }
    .card .label { color: var(--muted); font-weight: 650; }
    .card .value { font-size: 40px; font-weight: 850; margin-top: 8px; }
    h2 { font-size: 28px; margin: 28px 0 12px; }
    .active { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
    .task { background: white; border: 1px solid var(--line); border-radius: 8px; padding: 16px; min-height: 108px; }
    .task b { display: block; font-size: 18px; overflow-wrap: anywhere; }
    .muted { color: var(--muted); }
    .table-scroll { overflow-x: auto; border-radius: 8px; background: white; }
    table { width: 100%; border-collapse: collapse; min-width: 900px; background: white; }
    th, td { padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
    th { color: var(--muted); font-weight: 800; }
    @media (max-width: 900px) { .cards, .active { grid-template-columns: repeat(2, minmax(0, 1fr)); } .top { display: block; } .refresh { text-align: left; margin-top: 12px; } }
  </style>
</head>
<body>
<main>
  <div class="top">
    <div>
      <h1>LEA Full Baseline Progress</h1>
      <div class="sub" id="runMeta">loading</div>
    </div>
    <div class="refresh">Last refresh<br><span id="clock">--:--:--</span></div>
  </div>
  <section class="panel">
    <div class="progress-row">
      <div>
        <div style="font-size:26px;font-weight:850" id="progressText">loading</div>
        <div class="muted" style="font-size:22px" id="statusText">loading</div>
      </div>
      <div class="badge" id="stateBadge">loading</div>
    </div>
    <div class="bar"><span id="progressBar" style="width:0%"></span></div>
  </section>
  <section class="cards">
    <div class="card"><div class="label">Completed</div><div class="value" id="completed">0</div></div>
    <div class="card"><div class="label">Remaining</div><div class="value" id="remaining">0</div></div>
    <div class="card"><div class="label">Failed</div><div class="value" id="failed">0</div></div>
    <div class="card"><div class="label">Cases</div><div class="value" id="cases">0</div></div>
    <div class="card"><div class="label">Concurrency</div><div class="value" id="conc">0</div></div>
  </section>
  <h2>Active Tasks</h2>
  <div class="active" id="active"><div class="muted">No active task reported.</div></div>
  <h2>Breakdown Table</h2>
  <div class="table-scroll" id="breakdown"><div class="panel muted">Waiting for summary_lea_full_breakdown.csv</div></div>
  <h2>Recent Completed Cases</h2>
  <div class="table-scroll" id="casesTable"><div class="panel muted">Waiting for summary_method_cases.csv</div></div>
</main>
<script>
async function fetchJSON(path) {
  const r = await fetch(path + '?t=' + Date.now(), {cache:'no-store'});
  if (!r.ok) throw new Error(path + ' ' + r.status);
  return await r.json();
}
async function fetchText(path) {
  const r = await fetch(path + '?t=' + Date.now(), {cache:'no-store'});
  if (!r.ok) return '';
  return await r.text();
}
function csvRows(text) {
  const lines = text.trim().split(/\\r?\\n/).filter(Boolean);
  return lines.map(line => {
    const out = []; let cur = '', q = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"' && line[i+1] === '"') { cur += '"'; i++; }
      else if (ch === '"') q = !q;
      else if (ch === ',' && !q) { out.push(cur); cur = ''; }
      else cur += ch;
    }
    out.push(cur); return out;
  });
}
function renderTable(id, text, keepCols, maxRows) {
  const root = document.getElementById(id);
  if (!text.trim()) return;
  const rows = csvRows(text);
  const header = rows[0];
  const idx = keepCols.map(c => header.indexOf(c)).filter(i => i >= 0);
  let html = '<table><thead><tr>' + idx.map(i => '<th>' + header[i] + '</th>').join('') + '</tr></thead><tbody>';
  const body = rows.slice(1).slice(-maxRows).reverse();
  for (const row of body) html += '<tr>' + idx.map(i => '<td>' + (row[i] || '') + '</td>').join('') + '</tr>';
  html += '</tbody></table>';
  root.innerHTML = html;
}
async function refresh() {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString();
  const s = await fetchJSON('status.json');
  const total = s.total_cases || 0, done = s.completed_cases || 0, failed = s.failed_cases || 0, rem = s.remaining_cases || 0;
  const pct = total ? (done / total * 100) : 0;
  document.getElementById('runMeta').textContent = s.run_id || '';
  document.getElementById('progressText').textContent = `${done} / ${total} completed (${pct.toFixed(1)}%)`;
  document.getElementById('statusText').textContent = `updated ${s.updated_at || 'unknown'} - ${rem} remaining`;
  document.getElementById('stateBadge').textContent = rem === 0 ? 'complete' : 'running';
  document.getElementById('progressBar').style.width = pct + '%';
  document.getElementById('completed').textContent = done;
  document.getElementById('remaining').textContent = rem;
  document.getElementById('failed').textContent = failed;
  document.getElementById('cases').textContent = total;
  document.getElementById('conc').textContent = s.case_concurrency || 1;
  const active = s.active || [];
  document.getElementById('active').innerHTML = active.length ? active.map(a => (
    `<div class="task"><b>${a.case_order}. ${a.case_id}</b><div>${a.model} · ${a.domain} · SCC ${a.scc_size}</div><div class="muted">${a.template} · started ${a.started_at}</div></div>`
  )).join('') : '<div class="muted">No active task reported.</div>';
  renderTable('breakdown', await fetchText('summary_lea_full_breakdown.csv'), ['group','N','invalid','root_at_3','risk_any','risk_all','compression','calls_per_case','total_tokens_per_case','runtime_sec_per_case'], 80);
  renderTable('casesTable', await fetchText('summary_method_cases.csv'), ['case_order','model','domain','scc_size','template','invalid_output','root_at_3','risk_any','risk_all','compression','llm_calls','total_tokens','runtime_sec'], 24);
}
refresh().catch(console.error);
setInterval(() => refresh().catch(console.error), 5000);
</script>
</body>
</html>
"""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def safe_token(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("_")


def atomic_write_json(path: Path, payload: Any) -> None:
    cost.atomic_write_json(path, payload)


def result_path(output_dir: Path, case: dict[str, Any]) -> Path:
    return output_dir / "results" / f"{case['case_id']}__lea.json"


def build_or_load_case_plan(args: argparse.Namespace, output_dir: Path) -> list[dict[str, Any]]:
    plan_path = output_dir / "case_plan.json"
    if plan_path.exists() and not args.rebuild_plan:
        return json.loads(plan_path.read_text(encoding="utf-8"))

    rows = list(csv.DictReader(args.case_csv.open(encoding="utf-8")))
    allowed = set(args.models)
    rows = [row for row in rows if row.get("model") in allowed]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        raise RuntimeError(f"No rows found in {args.case_csv} for models={sorted(allowed)}")

    plan = []
    for idx, row in enumerate(rows, 1):
        case_id = safe_token(
            f"{idx:03d}_{row['model']}_{row['domain']}{row['scc_size']}_{row['scc_id']}_{row['template']}"
        )
        plan.append(
            {
                "case_order": idx,
                "case_id": case_id,
                "model": row["model"],
                "domain": row["domain"],
                "scc_id": row["scc_id"],
                "scc_size": int(row["scc_size"]),
                "template": row["template"],
                "root": row.get("root"),
                "witness": row.get("witness"),
                "bridge": row.get("bridge"),
                "affected_count": int(float(row.get("affected_count") or 0)),
                "source_result_file": row.get("result_file"),
                "old_llm_calls": int(float(row.get("llm_calls") or 0)),
                "old_time_sec": float(row.get("time") or 0.0),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(plan_path, plan)
    with (output_dir / "case_plan.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(plan[0].keys()))
        writer.writeheader()
        writer.writerows(plan)
    return plan


def make_case_args(args: argparse.Namespace, case: dict[str, Any]) -> argparse.Namespace:
    case_args = copy.copy(args)
    case_args.model = case["model"]
    return case_args


def make_llm(args: argparse.Namespace, output_dir: Path, case: dict[str, Any]) -> cost.LoggingOpenAIClient:
    model_id = cost.MODEL_IDS.get(case["model"], case["model"])
    config = {
        "provider": "openai",
        "model": model_id,
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "timeout": args.llm_timeout,
        "max_retries": args.llm_max_retries,
    }
    return cost.LoggingOpenAIClient(
        config,
        call_log_path=output_dir / "call_logs" / "llm_calls.jsonl",
        context={
            "run_id": output_dir.name,
            "case_id": case["case_id"],
            "case_order": case["case_order"],
            "domain": case["domain"],
            "scc_id": case["scc_id"],
            "scc_size": case["scc_size"],
            "template": case["template"],
            "method": "lea",
            "model": case["model"],
            "case_concurrency": args.case_concurrency,
            "internal_concurrency": 1,
        },
    )


def override_injected_root_metrics(result: dict[str, Any], injected_id: str | None) -> None:
    ranking = result.get("ranking") or []
    ranked_ids = [item[0] for item in ranking if isinstance(item, (list, tuple)) and item]
    result["ground_truth_nodes"] = [injected_id] if injected_id else []
    result["top1_hit"] = bool(injected_id and ranked_ids[:1] == [injected_id])
    result["top3_hit"] = bool(injected_id and injected_id in ranked_ids[:3])


async def run_lea_case(
    args: argparse.Namespace,
    output_dir: Path,
    case: dict[str, Any],
    graphs: dict[str, Any],
) -> dict[str, Any]:
    case_args = make_case_args(args, case)
    llm = make_llm(args, output_dir, case)
    started_at = time.time()
    try:
        graph, scc, injected_id, injection_metadata = cost.prepare_injected_case(case, graphs)
        result = await cost.run_lea(llm, case_args, case, graph, scc, injection_metadata)
        override_injected_root_metrics(result, injected_id)
        result.update(
            {
                "inject_mode": True,
                "injected_node": injected_id,
                "inject_type": cost.battle.DOMAIN_INJECT_TYPE.get(case["domain"]),
                "inject_profile": "memory_stress",
                "cycle_source": "real_long",
                "case_template": case["template"],
            }
        )
        result.update(injection_metadata)
        cost.battle.add_rank_metrics(result, injected_id)
        cost.battle.add_structural_rank_metrics(result, injection_metadata)
        result = cost.attach_common_audit(
            result,
            args=case_args,
            case=case,
            method="lea",
            llm=llm,
            started_at=started_at,
        )
        result["case_concurrency"] = args.case_concurrency
        usage = result.get("llm_usage_summary") or {}
        if int(usage.get("failed_api_calls") or 0) > 0:
            result["cost_audit_error"] = (
                "One or more LLM API calls failed during LEA evaluation; "
                "discard this case result and retry after provider availability is restored."
            )
        return result
    except Exception as exc:
        payload = {
            "method": "lea",
            "model": case["model"],
            "domain": case["domain"],
            "scc_id": case["scc_id"],
            "scc_size": case["scc_size"],
            "case_template": case["template"],
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        result = cost.attach_common_audit(
            payload,
            args=case_args,
            case=case,
            method="lea",
            llm=llm,
            started_at=started_at,
            error=str(exc),
        )
        result["case_concurrency"] = args.case_concurrency
        return result
    finally:
        await llm.close()


def mean(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return sum(nums) / len(nums) if nums else None


def mean_bool(values: list[Any]) -> float | None:
    vals = [v for v in values if isinstance(v, bool)]
    return sum(1 for v in vals if v) / len(vals) if vals else None


def summarize(output_dir: Path) -> None:
    cost.summarize(output_dir)
    rows = []
    for path in sorted((output_dir / "results").glob("*__lea.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        usage = result.get("llm_usage_summary") or {}
        label = cost.method_label(result)
        rows.append(
            {
                "case_order": result.get("case_order"),
                "case_id": result.get("case_id"),
                "model": result.get("model"),
                "domain": result.get("domain"),
                "scc_size": int(result.get("scc_size") or 0),
                "scale": cost.scale_bin(int(result.get("scc_size") or 0)),
                "template": result.get("case_template") or result.get("injected_conflict_template"),
                "invalid_output": bool(result.get("cost_audit_error")),
                "root_at_3": cost.metric_value(result, label, "root@3"),
                "risk_any": cost.metric_value(result, label, "risk_any"),
                "risk_all": cost.metric_value(result, label, "risk_all"),
                "compression": cost.metric_value(result, label, "compression"),
                "llm_calls": result.get("llm_calls"),
                "recorded_api_calls": usage.get("recorded_api_calls"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "runtime_sec": result.get("time"),
            }
        )

    if not rows:
        return

    full_csv = output_dir / "summary_method_cases.csv"
    with full_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups["overall"].append(row)
        groups[f"model={row['model']}"].append(row)
        groups[f"domain={row['domain']}"].append(row)
        groups[f"scale={row['scale']}"].append(row)
        groups[f"template={row['template']}"].append(row)
        groups[f"model={row['model']}|domain={row['domain']}"].append(row)

    breakdown = []
    for group, items in sorted(groups.items()):
        breakdown.append(
            {
                "group": group,
                "N": len(items),
                "invalid": mean_bool([r["invalid_output"] for r in items]),
                "root_at_3": mean_bool([r["root_at_3"] for r in items]),
                "risk_any": mean_bool([r["risk_any"] for r in items]),
                "risk_all": mean_bool([r["risk_all"] for r in items]),
                "compression": mean([r["compression"] for r in items]),
                "calls_per_case": mean([r["llm_calls"] for r in items]),
                "total_tokens_per_case": mean([r["total_tokens"] for r in items]),
                "runtime_sec_per_case": mean([r["runtime_sec"] for r in items]),
            }
        )

    fields = list(breakdown[0].keys())
    with (output_dir / "summary_lea_full_breakdown.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(breakdown)

    lines = ["| " + " | ".join(fields) + " |", "|" + "|".join("---" for _ in fields) + "|"]
    for row in breakdown:
        cells = []
        for field in fields:
            value = row[field]
            if isinstance(value, float):
                if field.endswith("tokens_per_case"):
                    cells.append(f"{value:.0f}")
                elif field.endswith("runtime_sec_per_case"):
                    cells.append(f"{value:.1f}s")
                else:
                    cells.append(f"{value:.3f}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    (output_dir / "summary_lea_full_breakdown.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_status(
    output_dir: Path,
    plan: list[dict[str, Any]],
    args: argparse.Namespace,
    active: list[dict[str, Any]] | None = None,
) -> None:
    completed = 0
    failed = 0
    for case in plan:
        path = result_path(output_dir, case)
        if not path.exists():
            continue
        completed += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            failed += 1
            continue
        if payload.get("cost_audit_error"):
            failed += 1

    status = {
        "run_id": output_dir.name,
        "updated_at": now_iso(),
        "total_cases": len(plan),
        "method": "lea",
        "case_concurrency": args.case_concurrency,
        "completed_cases": completed,
        "failed_cases": failed,
        "remaining_cases": len(plan) - completed,
        "active": active or [],
        "result_dir": str(output_dir / "results"),
        "call_log": str(output_dir / "call_logs" / "llm_calls.jsonl"),
    }
    atomic_write_json(output_dir / "status.json", status)


async def run(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    plan = build_or_load_case_plan(args, output_dir)
    atomic_write_json(
        output_dir / "run_config.json",
        {
            "created_or_updated_at": now_iso(),
            "case_csv": str(args.case_csv),
            "models": args.models,
            "method": "lea",
            "total_cases": len(plan),
            "case_concurrency": args.case_concurrency,
            "window_size": args.window_size,
            "compression_profile": args.compression_profile,
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
        },
    )
    write_status(output_dir, plan, args)
    summarize(output_dir)
    if args.dry_run:
        return

    if not os.environ.get(args.api_key_env, ""):
        raise RuntimeError(f"{args.api_key_env} is not set")

    graphs = cost.load_graphs(plan)
    active: dict[str, dict[str, Any]] = {}
    active_lock = asyncio.Lock()
    summarize_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(args.case_concurrency)

    async def worker(case: dict[str, Any]) -> None:
        path = result_path(output_dir, case)
        if path.exists():
            if not args.retry_errors:
                return
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
                if not old.get("cost_audit_error"):
                    return
            except Exception:
                pass

        async with semaphore:
            active_entry = {
                "case_id": case["case_id"],
                "case_order": case["case_order"],
                "model": case["model"],
                "domain": case["domain"],
                "scc_size": case["scc_size"],
                "template": case["template"],
                "started_at": now_iso(),
            }
            async with active_lock:
                active[case["case_id"]] = active_entry
                write_status(output_dir, plan, args, list(active.values()))
            result = await run_lea_case(args, output_dir, case, graphs)
            atomic_write_json(path, result)
            async with summarize_lock:
                summarize(output_dir)
            async with active_lock:
                active.pop(case["case_id"], None)
                write_status(output_dir, plan, args, list(active.values()))

    await asyncio.gather(*(worker(case) for case in plan))
    summarize(output_dir)
    write_status(output_dir, plan, args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full GraphRAG-style LEA baseline.")
    parser.add_argument("--case-csv", type=Path, default=DEFAULT_CASE_CSV)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case-concurrency", type=int, default=4)
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--budget", type=int, default=50)
    parser.add_argument("--internal-concurrency", type=int, default=1)
    parser.add_argument("--compression-profile", default="current")
    parser.add_argument("--base-url", default=cost.battle.XHUB_BASE_URL)
    parser.add_argument("--api-key-env", default="XHUB_API_KEY")
    parser.add_argument("--llm-timeout", type=float, default=600)
    parser.add_argument("--llm-max-retries", type=int, default=2)
    parser.add_argument("--rebuild-plan", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.output_dir is None:
        run_id = time.strftime("lea_full320_%Y%m%d_%H%M%S", time.localtime())
        args.output_dir = DEFAULT_RUNS_DIR / run_id
    args.output_dir = args.output_dir.resolve()
    args.case_csv = args.case_csv.resolve()
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))

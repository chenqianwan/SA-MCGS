"""Focused live dashboard for the supplementary-model critical run."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from progress_dashboard import _build_metric_rows, _load_records_from_status, _pair_key, _summarize


RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_STATUS = RESULTS_DIR / "critical_balanced_b60_supp_qwen_gemini_severity_grid_status.json"
QUOTA_PATTERNS = (
    "余额",
    "额度",
    "quota",
    "insufficient",
    "billing",
    "无可用渠道",
    "Error code: 429",
    "Error code: 502",
    "Error code: 503",
    "Bad Gateway",
)
QUOTA_EXHAUSTED_PATTERNS = (
    "额度",
    "quota",
    "billing",
    "insufficient",
    "无可用渠道",
    "Error code: 401",
    "RemainQuota",
)


def _read_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"tasks": [], "summary": {}, "error": f"status file not found: {path}"}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {"tasks": [], "summary": {}, "error": "status is not a JSON object"}
    except Exception as exc:
        return {"tasks": [], "summary": {}, "error": f"failed to read status: {exc}"}


def _read_combined_status(paths: list[Path]) -> dict[str, Any]:
    combined: dict[str, Any] = {
        "tasks": [],
        "summary": {},
        "sources": [str(path) for path in paths],
    }
    errors: list[str] = []
    for source_idx, path in enumerate(paths, 1):
        status = _read_status(path)
        if status.get("error"):
            errors.append(f"{path.name}: {status['error']}")
        source_tasks = status.get("tasks", [])
        if not isinstance(source_tasks, list):
            continue
        for task in source_tasks:
            enriched = dict(task)
            enriched["_source_status"] = path.name
            enriched["_source_task_id"] = task.get("task_id")
            enriched["task_id"] = f"{source_idx}.{task.get('task_id')}"
            combined["tasks"].append(enriched)
    summary: dict[str, int] = {}
    for task in combined["tasks"]:
        state = str(task.get("status", "?"))
        summary[state] = summary.get(state, 0) + 1
    combined["summary"] = summary
    if errors:
        combined["error"] = "; ".join(errors)
    return combined


def _duration(start: Any, end: Any | None = None) -> float | None:
    try:
        return max(0.0, float(end or time.time()) - float(start))
    except Exception:
        return None


def _line_has_quota_exhausted(line: str) -> bool:
    lowered = line.lower()
    return any(pattern.lower() in lowered for pattern in QUOTA_EXHAUSTED_PATTERNS)


def _task_quota_exhausted(task: dict[str, Any]) -> bool:
    path = Path(task.get("log_path") or "")
    if not path.exists():
        return False
    try:
        for line in path.read_text(errors="replace").splitlines():
            if _line_has_quota_exhausted(line):
                return True
    except Exception:
        return False
    return False


def _scan_logs(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    quota_hits: list[dict[str, str]] = []
    recent_errors: list[dict[str, str]] = []
    sa_internal_warnings: list[dict[str, str]] = []
    sa_warning_categories: Counter[str] = Counter()
    for task in tasks:
        path = Path(task.get("log_path") or "")
        if not path.exists():
            continue
        try:
            lines = path.read_text(errors="replace").splitlines()
        except Exception:
            continue
        for line in lines:
            lowered = line.lower()
            if any(p.lower() in lowered for p in QUOTA_PATTERNS):
                quota_hits.append({
                    "task": str(task.get("task_id")),
                    "domain": str(task.get("domain")),
                    "size": str(task.get("size")),
                    "line": line.strip()[:240],
                })
            if "AlphaGoMCGS LLM call failed" in line:
                if "401" in lowered or "quota" in lowered or "额度" in lowered:
                    category = "quota_401"
                elif "502" in lowered or "bad gateway" in lowered or "<html>" in lowered:
                    category = "bad_gateway_502"
                elif "connection error" in lowered:
                    category = "connection_error"
                else:
                    category = "other"
                sa_warning_categories[category] += 1
                sa_internal_warnings.append({
                    "task": str(task.get("task_id")),
                    "domain": str(task.get("domain")),
                    "size": str(task.get("size")),
                    "category": category,
                    "line": line.strip()[:240],
                })
            if "ERROR:" in line or "Connection error" in line or "no parseable JSON" in line:
                recent_errors.append({
                    "task": str(task.get("task_id")),
                    "domain": str(task.get("domain")),
                    "size": str(task.get("size")),
                    "line": line.strip()[:240],
                })
    return {
        "quota_hits": quota_hits[-12:],
        "quota_count": len(quota_hits),
        "recent_errors": recent_errors[-18:],
        "error_count": len(recent_errors),
        "sa_internal_warning_count": len(sa_internal_warnings),
        "sa_internal_warning_categories": dict(sa_warning_categories),
        "recent_sa_internal_warnings": sa_internal_warnings[-18:],
    }


def _matched_valid_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return paired records where both methods exist and neither method errored."""
    by_case: dict[tuple[str, str, str, str, str, str], dict[str, dict[str, Any]]] = {}
    for record in records:
        method = record.get("method")
        if method not in {"naive", "sa-mcgs"}:
            continue
        by_case.setdefault(_pair_key(record), {})[str(method)] = record

    kept: list[dict[str, Any]] = []
    stats = {
        "matched_pairs_total": 0,
        "matched_pairs_kept": 0,
        "removed_missing_method_pairs": 0,
        "removed_naive_error_pairs": 0,
        "removed_sa_error_pairs": 0,
    }
    for methods in by_case.values():
        naive = methods.get("naive")
        sa = methods.get("sa-mcgs")
        if not naive or not sa:
            stats["removed_missing_method_pairs"] += 1
            continue
        stats["matched_pairs_total"] += 1
        if naive.get("error"):
            stats["removed_naive_error_pairs"] += 1
            continue
        if sa.get("error"):
            stats["removed_sa_error_pairs"] += 1
            continue
        stats["matched_pairs_kept"] += 1
        kept.extend([naive, sa])
    return kept, stats


def _payload(status_paths: list[Path]) -> dict[str, Any]:
    status = _read_combined_status(status_paths) if len(status_paths) > 1 else _read_status(status_paths[0])
    tasks = status.get("tasks", []) if isinstance(status.get("tasks"), list) else []
    done_tasks = [t for t in tasks if t.get("status") == "done"]
    quota_excluded_tasks = [t for t in done_tasks if _task_quota_exhausted(t)]
    quota_excluded_ids = {t.get("task_id") for t in quota_excluded_tasks}
    valid_done_tasks = [t for t in done_tasks if t.get("task_id") not in quota_excluded_ids]
    done_status = dict(status)
    done_status["tasks"] = valid_done_tasks
    records = _load_records_from_status(done_status)
    live_records = _load_records_from_status(status)
    summary = _summarize(records, expected_total=len(valid_done_tasks) * 4)
    paired_valid_records, paired_valid_stats = _matched_valid_records(records)
    summary["paired_valid_groups"] = _build_metric_rows(
        paired_valid_records,
        lambda _r: "Naive-valid matched pairs",
        sort_fn=lambda r: (r["label"], r["method"]),
    )
    summary["paired_valid_stats"] = paired_valid_stats
    summary["model_groups"] = _build_metric_rows(
        [r for r in records if r.get("method") in {"naive", "sa-mcgs"}],
        lambda r: r.get("model"),
        sort_fn=lambda r: (r["label"], r["method"]),
    )
    summary["domain_model_groups"] = _build_metric_rows(
        [r for r in records if r.get("method") in {"naive", "sa-mcgs"}],
        lambda r: f"{r.get('domain')} / {r.get('model')}",
        sort_fn=lambda r: (r["label"], r["method"]),
    )

    task_counter = Counter(str(t.get("status", "?")) for t in tasks)
    by_domain_status: dict[str, dict[str, int]] = {}
    for task in tasks:
        domain = str(task.get("domain", "?"))
        by_domain_status.setdefault(domain, {})
        state = str(task.get("status", "?"))
        by_domain_status[domain][state] = by_domain_status[domain].get(state, 0) + 1

    running = []
    for task in tasks:
        if task.get("status") != "running":
            continue
        elapsed = _duration(task.get("started_at"))
        running.append({
            "task_id": task.get("task_id"),
            "domain": task.get("domain"),
            "size": task.get("size"),
            "template": task.get("template"),
            "severity": task.get("severity"),
            "elapsed_min": round((elapsed or 0) / 60, 1),
            "log": Path(task.get("log_path") or "").name,
        })
    running.sort(key=lambda r: r["elapsed_min"], reverse=True)

    recent_done = []
    for task in sorted(
        [t for t in tasks if t.get("status") == "done"],
        key=lambda t: float(t.get("ended_at") or 0),
        reverse=True,
    )[:24]:
        elapsed = _duration(task.get("started_at"), task.get("ended_at"))
        recent_done.append({
            "task_id": task.get("task_id"),
            "domain": task.get("domain"),
            "size": task.get("size"),
            "template": task.get("template"),
            "elapsed_min": round((elapsed or 0) / 60, 1),
            "result": Path(task.get("result_file") or "").name,
            "quota_excluded": task.get("task_id") in quota_excluded_ids,
        })

    existing_status_paths = [path for path in status_paths if path.exists()]
    checkpoint_mtime = (
        max(path.stat().st_mtime for path in existing_status_paths)
        if existing_status_paths else None
    )

    return {
        "now": time.strftime("%Y-%m-%d %H:%M:%S"),
        "checkpoint": " | ".join(str(path) for path in status_paths),
        "checkpoint_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(checkpoint_mtime))
        if checkpoint_mtime is not None
        else "-",
        "status_error": status.get("error"),
        "task_total": len(tasks),
        "task_counts": dict(task_counter),
        "valid_done_task_count": len(valid_done_tasks),
        "excluded_quota_task_count": len(quota_excluded_tasks),
        "excluded_quota_tasks": [
            {
                "task_id": task.get("task_id"),
                "domain": task.get("domain"),
                "size": task.get("size"),
                "template": task.get("template"),
                "log": Path(task.get("log_path") or "").name,
            }
            for task in quota_excluded_tasks
        ],
        "done_method_records": len(records),
        "live_method_records": len(live_records),
        "by_domain_status": by_domain_status,
        "running": running,
        "recent_done": recent_done,
        "summary": summary,
        "logs": _scan_logs(tasks),
    }


def _html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Supplement Model Run Progress</title>
  <style>
    :root {
      color-scheme: dark;
      --bg:#0d1117; --panel:#151a22; --panel2:#1c2430; --line:#303846;
      --text:#f3f7ff; --muted:#9aa7ba; --green:#16c98d; --red:#ff555f;
      --blue:#67a0ff; --amber:#f3a43b; --purple:#b084ff;
    }
    * { box-sizing: border-box; }
    body { margin:0; background:linear-gradient(135deg,#0d1117,#0e1a1d 48%,#10131a); color:var(--text);
      font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    main { max-width:1500px; margin:0 auto; padding:28px; }
    header { display:flex; justify-content:space-between; gap:18px; align-items:flex-start; margin-bottom:18px; }
    h1 { margin:0; font-size:34px; letter-spacing:0; }
    h2 { margin:0 0 12px; font-size:23px; }
    h3 { margin:12px 0 8px; font-size:16px; color:#dbeafe; }
    .sub { color:var(--muted); margin-top:6px; }
    .pill { border:1px solid var(--line); background:var(--panel2); border-radius:999px; padding:8px 12px; white-space:nowrap; }
    .dot { display:inline-block; width:10px; height:10px; border-radius:50%; background:var(--muted); margin-right:8px; }
    .dot.on { background:var(--green); box-shadow:0 0 16px rgba(22,201,141,.6); }
    .dot.warn { background:var(--amber); }
    .grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }
    .grid.two { grid-template-columns:1.1fr .9fr; }
    .card { background:rgba(21,26,34,.94); border:1px solid var(--line); border-radius:12px; padding:18px; box-shadow:0 18px 50px rgba(0,0,0,.18); }
    .metric-label { color:var(--muted); font-size:14px; margin-bottom:6px; }
    .metric-value { font-size:38px; font-weight:900; line-height:1.05; }
    .ok { color:var(--green); font-weight:850; } .bad { color:var(--red); font-weight:850; }
    .warn { color:var(--amber); font-weight:850; } .blue { color:var(--blue); font-weight:850; }
    .mono { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
    .progress { height:16px; background:#0a0e14; border:1px solid var(--line); border-radius:999px; overflow:hidden; margin-top:12px; }
    .bar { height:100%; background:linear-gradient(90deg,var(--blue),var(--green)); width:0%; transition:width .25s ease; }
    .mini { display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
    .tag { display:inline-flex; border:1px solid var(--line); background:var(--panel2); border-radius:999px; padding:5px 9px; color:#dbeafe; }
    table { width:100%; border-collapse:collapse; }
    th,td { padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
    th { position:sticky; top:0; background:#111722; color:#dbeafe; z-index:1; }
    .scroll { overflow:auto; max-height:470px; border:1px solid var(--line); border-radius:10px; background:#111722; }
    .scroll table { min-width:1050px; }
    .chart { height:260px; border:1px solid var(--line); border-radius:10px; background:#101720; padding:12px; overflow:hidden; }
    .chart.tall { height:360px; }
    .chart.wide { min-height:330px; height:auto; overflow:auto; }
    svg { width:100%; height:100%; display:block; }
    .legend { display:flex; gap:16px; flex-wrap:wrap; color:var(--muted); margin-top:10px; }
    .legend i { display:inline-block; width:20px; height:4px; border-radius:99px; margin-right:6px; vertical-align:middle; }
    .method-naive { color:#ff766f; } .method-sa { color:#16c98d; }
    .small { font-size:13px; color:var(--muted); }
    @media (max-width:1000px) { main{padding:18px} header,.grid.two{display:block}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.card{margin-bottom:14px} }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Supplement Model Critical Run</h1>
      <div class="sub">qwen2.5-72b + gemini-2.5-flash · critical-only · balanced compression · rollout=60 · auto refresh 15s</div>
    </div>
    <div class="pill"><span id="dot" class="dot"></span><span id="runState">loading</span></div>
  </header>

  <section class="card">
    <h2>Run Progress</h2>
    <div class="grid" style="grid-template-columns:repeat(5,minmax(0,1fr))">
      <div><div class="metric-label">Blocks done</div><div class="metric-value"><span id="done">-</span><span class="sub">/<span id="taskTotal">-</span></span></div></div>
      <div><div class="metric-label">Valid blocks in charts</div><div class="metric-value ok" id="validBlocks">-</div></div>
      <div><div class="metric-label">Quota-excluded</div><div class="metric-value warn" id="quotaExcluded">-</div></div>
      <div><div class="metric-label">Running</div><div class="metric-value blue" id="running">-</div></div>
      <div><div class="metric-label">Valid method records</div><div class="metric-value"><span id="records">-</span><span class="sub">/<span id="expectedRecords">-</span></span></div></div>
    </div>
    <div class="progress"><div id="progressBar" class="bar"></div></div>
    <div class="mini" id="domainTags"></div>
    <div class="sub" id="checkpoint"></div>
  </section>

  <section class="grid two" style="margin-top:14px">
    <div class="card">
      <h2>Naive vs SA-MCGS So Far</h2>
      <h3>Strict accounting: errors count as misses</h3>
      <div class="chart" id="metricChartStrict"></div>
      <h3>Comparable pairs: remove Naive-error pairs</h3>
      <div class="chart" id="metricChartComparable"></div>
      <div class="legend">
        <span><i style="background:#ff766f"></i>Naive</span>
        <span><i style="background:#16c98d"></i>SA-MCGS</span>
      </div>
    </div>
    <div class="card">
      <h2>Key Numbers</h2>
      <div id="headline" class="grid" style="grid-template-columns:repeat(2,minmax(0,1fr))"></div>
      <div class="sub" id="readout"></div>
    </div>
  </section>

  <section class="grid two" style="margin-top:14px">
    <div class="card">
      <h2>Model-level Results</h2>
      <div class="sub">同一个指标按模型拆开看。这里能直接看出 Qwen 和 Gemini 的差异，不再被混合总览掩盖。</div>
      <div class="chart tall" id="modelChart"></div>
      <div class="legend">
        <span><i style="background:#ff766f"></i>Naive</span>
        <span><i style="background:#16c98d"></i>SA-MCGS</span>
      </div>
    </div>
    <div class="card">
      <h2>Failure Accounting</h2>
      <div class="sub">红色是 done block 里的 method-level error。strict rate 会把这些 error 计入分母并视为 miss。</div>
      <div class="chart tall" id="failureChart"></div>
      <div id="accountingNote" class="sub"></div>
    </div>
  </section>

  <section class="card" style="margin-top:14px">
    <h2>Domain × Model Heatmap</h2>
    <div class="sub">颜色越绿代表命中率越高；偏红说明这个模型/领域组合不稳定或没有抓住风险端点。</div>
    <div class="chart wide" id="heatmap"></div>
  </section>

  <section class="grid two" style="margin-top:14px">
    <div class="card">
      <h2>Running CUAD Blocks</h2>
      <div class="scroll"><table><thead><tr><th>ID</th><th>Domain</th><th>Size</th><th>Template</th><th>Elapsed</th><th>Log</th></tr></thead><tbody id="runningRows"></tbody></table></div>
    </div>
    <div class="card">
      <h2>Recent Completed Blocks</h2>
      <div class="scroll"><table><thead><tr><th>ID</th><th>Domain</th><th>Size</th><th>Template</th><th>Minutes</th><th>Result</th></tr></thead><tbody id="recentRows"></tbody></table></div>
    </div>
  </section>

  <section class="card" style="margin-top:14px">
    <h2>Domain × Method Metrics</h2>
    <div class="scroll"><table><thead><tr><th>Domain</th><th>Method</th><th>N</th><th>Errors</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Avg subgraph</th><th>Compression</th><th>OC</th><th>Effective OC</th></tr></thead><tbody id="metricRows"></tbody></table></div>
  </section>

  <section class="grid two" style="margin-top:14px">
    <div class="card">
      <h2>Model × Method Breakdown</h2>
      <div class="sub">总 risk-all 目前主要被 Gemini SA-MCGS 的 uniform/empty signal 拉低；看这个表比看总览更可靠。</div>
      <div class="scroll"><table><thead><tr><th>Model</th><th>Method</th><th>N</th><th>Errors</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Compression</th><th>Eff. comp</th></tr></thead><tbody id="modelRows"></tbody></table></div>
    </div>
    <div class="card">
      <h2>Domain × Model Detail</h2>
      <div class="sub">这里用来区分“模型问题”和“领域难度问题”。</div>
      <div class="scroll"><table><thead><tr><th>Domain / Model</th><th>Method</th><th>N</th><th>Errors</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Compression</th><th>Eff. comp</th></tr></thead><tbody id="domainModelRows"></tbody></table></div>
    </div>
  </section>

  <section class="card" style="margin-top:14px">
    <h2>All Blocks</h2>
    <div class="sub">按任务编号展示。done/running/pending 都在这里，方便确认没有漏掉。</div>
    <div class="scroll" style="max-height:620px"><table><thead><tr><th>ID</th><th>Status</th><th>Quota excluded</th><th>Domain</th><th>Size</th><th>Template</th><th>Attempt</th><th>Return</th><th>Started/Ended</th></tr></thead><tbody id="taskRows"></tbody></table></div>
  </section>

  <section class="card" style="margin-top:14px">
    <h2>Warnings</h2>
    <div id="quotaBox"></div>
    <div id="saInternalBox" style="margin-top:10px"></div>
    <details style="margin-top:10px"><summary>Recent SA internal window warnings</summary><div class="scroll" style="max-height:260px"><table><tbody id="saWarningRows"></tbody></table></div></details>
    <details style="margin-top:10px"><summary>Recent local method errors</summary><div class="scroll" style="max-height:260px"><table><tbody id="errorRows"></tbody></table></div></details>
  </section>
</main>
<script>
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '-').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = v => Number.isFinite(v) ? Math.round(v * 100) + '%' : '-';
function parseRate(s) {
  const m = String(s || '').match(/(\\d+)\\/(\\d+)/);
  return m ? {hit:+m[1], total:+m[2], rate:+m[1]/Math.max(1,+m[2])} : {hit:0,total:0,rate:0};
}
function metricRow(rows, method) {
  const filtered = rows.filter(r => r.method === method);
  const out = {n:0, root:0, any:0, all:0, comp:[], errors:0};
  for (const r of filtered) {
    const root = parseRate(r.root_top3), any = parseRate(r.risk_any), all = parseRate(r.risk_all);
    out.n += root.total; out.root += root.hit; out.any += any.hit; out.all += all.hit; out.errors += Number(r.errors || 0);
    const c = String(r.avg_compression || '').match(/(\\d+)/); if (c) out.comp.push(+c[1]/100);
  }
  out.rootRate = out.n ? out.root/out.n : 0; out.anyRate = out.n ? out.any/out.n : 0; out.allRate = out.n ? out.all/out.n : 0;
  out.compRate = out.comp.length ? out.comp.reduce((a,b)=>a+b,0)/out.comp.length : 0;
  return out;
}
function renderChart(targetId, naive, sa) {
  const metrics = [
    ['Root@3', naive.rootRate, sa.rootRate],
    ['Risk-any', naive.anyRate, sa.anyRate],
    ['Risk-all', naive.allRate, sa.allRate],
    ['Compression', naive.compRate, sa.compRate],
  ];
  const W=760,H=220, left=48, base=188, top=18, groupW=165, barW=30;
  let svg = `<svg viewBox="0 0 ${W} ${H}">`;
  for (let i=0;i<=4;i++) {
    const y=base-(base-top)*i/4;
    svg += `<line x1="${left}" y1="${y}" x2="${W-12}" y2="${y}" stroke="#263242"/><text x="8" y="${y+4}" fill="#9aa7ba" font-size="12">${i*25}%</text>`;
  }
  metrics.forEach((m,idx)=>{
    const x=left+35+idx*groupW;
    const hn=(base-top)*m[1], hs=(base-top)*m[2];
    svg += `<rect x="${x}" y="${base-hn}" width="${barW}" height="${hn}" rx="5" fill="#ff766f"/>`;
    svg += `<rect x="${x+42}" y="${base-hs}" width="${barW}" height="${hs}" rx="5" fill="#16c98d"/>`;
    svg += `<text x="${x-14}" y="${H-10}" fill="#dbeafe" font-size="13">${m[0]}</text>`;
    svg += `<text x="${x-2}" y="${base-hn-6}" fill="#ffb0aa" font-size="12">${pct(m[1])}</text>`;
    svg += `<text x="${x+40}" y="${base-hs-6}" fill="#9af5ce" font-size="12">${pct(m[2])}</text>`;
  });
  svg += `</svg>`;
  $(targetId).innerHTML = svg;
}
function renderModelChart(rows) {
  const models = [...new Set(rows.map(r => r.label))].sort();
  const metrics = [
    ['Root@3','root_top3'],
    ['Risk-any','risk_any'],
    ['Risk-all','risk_all'],
    ['Compression','avg_compression'],
    ['Eff. comp','effective_compression'],
  ];
  const W = 1450, H = Math.max(330, 160 * models.length + 48), left = 150, top = 28, rowH = 152, barW = 24;
  const segment = (W - left - 40) / metrics.length;
  const metricRate = (row, field) => {
    const raw = String((row || {})[field] || '');
    if (field === 'avg_compression' || field === 'effective_compression') {
      const m = raw.match(/([0-9]+(?:[.][0-9]+)?)%/);
      return m ? Number(m[1]) / 100 : 0;
    }
    return parseRate(raw).rate;
  };
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">`;
  for (let i=0;i<=4;i++) {
    const x = left + (W-left-28) * i / 4;
    svg += `<line x1="${x}" y1="${top-12}" x2="${x}" y2="${H-24}" stroke="#263242"/><text x="${x-13}" y="${H-5}" fill="#9aa7ba" font-size="12">${i*25}%</text>`;
  }
  models.forEach((model, mi) => {
    const y0 = top + mi * rowH;
    svg += `<text x="8" y="${y0+48}" fill="#e8f1ff" font-size="16" font-weight="800">${esc(model)}</text>`;
    metrics.forEach((m, idx) => {
      const n = rows.find(r => r.label === model && r.method === 'naive') || {};
      const s = rows.find(r => r.label === model && r.method === 'sa-mcgs') || {};
      const nr = metricRate(n, m[1]), sr = metricRate(s, m[1]);
      const x0 = left + idx * segment;
      const wN = (segment - 78) * nr;
      const wS = (segment - 78) * sr;
      const y = y0 + 12 + idx * 28;
      svg += `<text x="${x0}" y="${y+15}" fill="#9aa7ba" font-size="12">${m[0]}</text>`;
      svg += `<rect x="${x0+72}" y="${y}" width="${wN}" height="${barW/2}" rx="5" fill="#ff766f"/>`;
      svg += `<rect x="${x0+72}" y="${y+14}" width="${wS}" height="${barW/2}" rx="5" fill="#16c98d"/>`;
      svg += `<text x="${x0+78+wN}" y="${y+10}" fill="#ffb0aa" font-size="11">${pct(nr)}</text>`;
      svg += `<text x="${x0+78+wS}" y="${y+24}" fill="#9af5ce" font-size="11">${pct(sr)}</text>`;
    });
  });
  svg += `</svg>`;
  $('modelChart').innerHTML = svg;
}
function renderFailureChart(rows, taskCounts) {
  const items = rows.map(r => ({
    label: `${r.label}\\n${r.method}`,
    count: Number(r.count || 0),
    errors: Number(r.errors || 0),
  }));
  const W=840, H=Math.max(250, 42*items.length+70), left=190, top=24, barH=18;
  const maxN = Math.max(1, ...items.map(i => i.count));
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">`;
  items.forEach((it, idx) => {
    const y = top + idx * 38;
    const valid = Math.max(0, it.count - it.errors);
    const validW = (W-left-42) * valid / maxN;
    const errW = (W-left-42) * it.errors / maxN;
    const [a,b] = it.label.split('\\n');
    svg += `<text x="8" y="${y+11}" fill="#e8f1ff" font-size="12">${esc(a)}</text>`;
    svg += `<text x="8" y="${y+26}" fill="#9aa7ba" font-size="11">${esc(b)}</text>`;
    svg += `<rect x="${left}" y="${y}" width="${validW}" height="${barH}" rx="5" fill="#334155"/>`;
    svg += `<rect x="${left+validW}" y="${y}" width="${errW}" height="${barH}" rx="5" fill="#ff555f"/>`;
    svg += `<text x="${left+validW+errW+8}" y="${y+14}" fill="#dbeafe" font-size="12">${it.errors}/${it.count} errors</text>`;
  });
  svg += `<text x="8" y="${H-16}" fill="#9aa7ba" font-size="12">Block status: done ${taskCounts.done||0}, running ${taskCounts.running||0}, pending ${taskCounts.pending||0}, failed ${taskCounts.failed||0}</text>`;
  svg += `</svg>`;
  $('failureChart').innerHTML = svg;
}
function heatColor(rate) {
  const r = Math.max(0, Math.min(1, rate));
  const red = Math.round(230 - 190*r);
  const green = Math.round(70 + 130*r);
  const blue = Math.round(76 + 35*r);
  return `rgb(${red},${green},${blue})`;
}
function renderHeatmap(rows) {
  const metrics = [['Root@3','root_top3'], ['Risk-any','risk_any'], ['Risk-all','risk_all'], ['Compression','avg_compression']];
  const W=1040, rowH=34, top=46, left=270, H=Math.max(260, top + rows.length * rowH + 28);
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMinYMin meet" style="min-width:1040px;height:${H}px">`;
  metrics.forEach((m, i) => svg += `<text x="${left+i*175+12}" y="26" fill="#dbeafe" font-size="13" font-weight="800">${m[0]}</text>`);
  rows.forEach((r, ri) => {
    const y = top + ri*rowH;
    svg += `<text x="8" y="${y+21}" fill="#e8f1ff" font-size="12">${esc(r.label)}</text>`;
    svg += `<text x="178" y="${y+21}" fill="${r.method==='sa-mcgs'?'#16c98d':'#ff766f'}" font-size="12" font-weight="800">${esc(r.method)}</text>`;
    metrics.forEach((m, i) => {
      const raw = m[1] === 'avg_compression' ? String(r.avg_compression || '0/1') : String(r[m[1]] || '0/1');
      const rate = m[1] === 'avg_compression' ? ((raw.match(/(\\d+)/)||[0,0])[1] / 100) : parseRate(raw).rate;
      const x = left + i*175;
      svg += `<rect x="${x}" y="${y}" width="150" height="25" rx="5" fill="${heatColor(rate)}" opacity=".95"/>`;
      svg += `<text x="${x+12}" y="${y+17}" fill="#fff" font-size="12" font-weight="800">${esc(raw)}</text>`;
    });
  });
  svg += `</svg>`;
  $('heatmap').innerHTML = svg;
}
function statusClass(v) {
  if (v === 'done') return 'ok';
  if (v === 'running') return 'blue';
  if (v === 'pending') return 'warn';
  return 'bad';
}
async function refresh() {
  const data = await fetch('/api/status', {cache:'no-store'}).then(r => r.json());
  const counts = data.task_counts || {};
  const done = counts.done || 0, running = counts.running || 0, pending = counts.pending || 0, total = data.task_total || 0;
  $('done').textContent = done; $('running').textContent = running; $('taskTotal').textContent = total;
  $('validBlocks').textContent = data.valid_done_task_count || 0;
  $('quotaExcluded').textContent = data.excluded_quota_task_count || 0;
  $('progressBar').style.width = total ? `${Math.round(done/total*100)}%` : '0%';
  $('checkpoint').innerHTML = `checkpoint: <span class="mono">${esc(data.checkpoint_mtime)}</span> · ${esc(data.checkpoint)}<br><span class="warn">主图已排除 quota-exhausted block；这些 block 仍保留在 All Blocks 和 Warnings 中供审计。</span>`;
  $('dot').className = 'dot ' + (running ? 'on' : 'warn');
  $('runState').textContent = running ? 'running' : (pending ? 'paused / waiting' : 'complete');

  const s = data.summary || {};
  $('records').textContent = data.done_method_records || s.completed_total || 0;
  $('expectedRecords').textContent = s.expected_total || 0;
  const groups = s.groups || [];
  const naive = metricRow(groups, 'naive'), sa = metricRow(groups, 'sa-mcgs');
  const comparableGroups = s.paired_valid_groups || [];
  const comparableNaive = metricRow(comparableGroups, 'naive'), comparableSa = metricRow(comparableGroups, 'sa-mcgs');
  renderChart('metricChartStrict', naive, sa);
  renderChart('metricChartComparable', comparableNaive, comparableSa);
  renderModelChart(s.model_groups || []);
  renderFailureChart(s.model_groups || [], counts);
  renderHeatmap(s.domain_model_groups || []);

  $('headline').innerHTML = [
    ['Root@3', `${naive.root}/${naive.n} → ${sa.root}/${sa.n}`, sa.rootRate >= naive.rootRate ? 'ok' : 'bad'],
    ['Risk-any', `${naive.any}/${naive.n} → ${sa.any}/${sa.n}`, sa.anyRate >= naive.anyRate ? 'ok' : 'bad'],
    ['Risk-all', `${naive.all}/${naive.n} → ${sa.all}/${sa.n}`, sa.allRate >= naive.allRate ? 'ok' : 'bad'],
    ['Compression', `${pct(naive.compRate)} → ${pct(sa.compRate)}`, sa.compRate >= naive.compRate ? 'ok' : 'warn'],
  ].map(([k,v,c]) => `<div><div class="metric-label">${k}</div><div class="metric-value ${c}" style="font-size:28px">${v}</div></div>`).join('');
  const pairStats = s.paired_valid_stats || {};
  $('readout').innerHTML = `现在给两份口径：<b>Strict</b> 保留 method-level error 并按 miss 计入分母；<b>Comparable</b> 只看 Naive 和 SA-MCGS 都有效返回的 matched pairs。Comparable 当前保留 <b>${esc(pairStats.matched_pairs_kept ?? 0)}</b> 组，移除 Naive error <b>${esc(pairStats.removed_naive_error_pairs ?? 0)}</b> 组、SA error <b>${esc(pairStats.removed_sa_error_pairs ?? 0)}</b> 组。`;
  $('accountingNote').innerHTML = `统计口径：quota-exhausted block 整块排除；其余 done block 中每条 method record 都计入。如果 record 带 <span class="mono">error</span>，它仍进入分母，并按未命中处理。running/pending 只显示进度，不进入主图命中率。当前已落盘 live/partial records: ${esc(data.live_method_records || 0)}。`;

  $('domainTags').innerHTML = Object.entries(data.by_domain_status || {}).map(([d,c]) =>
    `<span class="tag">${esc(d)}: done ${c.done||0}, running ${c.running||0}, pending ${c.pending||0}</span>`).join('');

  $('runningRows').innerHTML = (data.running || []).map(r => `<tr><td>${r.task_id}</td><td>${esc(r.domain)}</td><td>${r.size}</td><td><span class="tag">${esc(r.template)}</span></td><td class="warn">${r.elapsed_min} min</td><td class="mono small">${esc(r.log)}</td></tr>`).join('') || '<tr><td colspan="6" class="sub">No running tasks.</td></tr>';
  $('recentRows').innerHTML = (data.recent_done || []).map(r => `<tr><td>${r.task_id}</td><td>${esc(r.domain)} ${r.quota_excluded ? '<span class="tag warn">quota excluded</span>' : ''}</td><td>${r.size}</td><td><span class="tag">${esc(r.template)}</span></td><td>${r.elapsed_min}</td><td class="mono small">${esc(r.result)}</td></tr>`).join('');
  $('metricRows').innerHTML = groups.map(r => `<tr><td>${esc(r.domain)}</td><td class="${r.method==='sa-mcgs'?'method-sa':'method-naive'}">${esc(r.method)}</td><td>${r.count}</td><td class="${r.errors?'warn':'ok'}">${r.errors}</td><td>${esc(r.root_top3)}</td><td>${esc(r.risk_any)}</td><td>${esc(r.risk_all)}</td><td>${esc(r.avg_subgraph)}</td><td>${esc(r.avg_compression)}</td><td>${esc(r.oc_hit)}</td><td>${esc(r.effective_oc_hit)}</td></tr>`).join('');
  $('modelRows').innerHTML = (s.model_groups || []).map(r => `<tr><td>${esc(r.label)}</td><td class="${r.method==='sa-mcgs'?'method-sa':'method-naive'}">${esc(r.method)}</td><td>${r.count}</td><td class="${r.errors?'warn':'ok'}">${r.errors}</td><td>${esc(r.root_top3)}</td><td>${esc(r.risk_any)}</td><td>${esc(r.risk_all)}</td><td>${esc(r.avg_compression)}</td><td>${esc(r.effective_compression)}</td></tr>`).join('');
  $('domainModelRows').innerHTML = (s.domain_model_groups || []).map(r => `<tr><td>${esc(r.label)}</td><td class="${r.method==='sa-mcgs'?'method-sa':'method-naive'}">${esc(r.method)}</td><td>${r.count}</td><td class="${r.errors?'warn':'ok'}">${r.errors}</td><td>${esc(r.root_top3)}</td><td>${esc(r.risk_any)}</td><td>${esc(r.risk_all)}</td><td>${esc(r.avg_compression)}</td><td>${esc(r.effective_compression)}</td></tr>`).join('');

  const tasks = Object.values(data.by_domain_status || {}).length ? [] : [];
  const taskRows = [];
  for (const r of [...(data.running || [])]) {}
  const allStatus = await fetch('/api/tasks', {cache:'no-store'}).then(r => r.json());
  $('taskRows').innerHTML = allStatus.tasks.map(t => `<tr><td>${t.task_id}</td><td class="${statusClass(t.status)}">${esc(t.status)}</td><td>${t.quota_excluded ? '<span class="tag warn">excluded</span>' : '-'}</td><td>${esc(t.domain)}</td><td>${esc(t.size)}</td><td><span class="tag">${esc(t.template)}</span></td><td>${esc(t.attempt)}</td><td>${esc(t.returncode)}</td><td class="small">${esc(t.started)}<br>${esc(t.ended)}</td></tr>`).join('');

  const logs = data.logs || {};
  const excluded = data.excluded_quota_tasks || [];
  const excludedText = excluded.slice(-16).map(t => `<span class="tag">#${esc(t.task_id)} ${esc(t.domain)}-${esc(t.size)} ${esc(t.template)}</span>`).join(' ');
  $('quotaBox').innerHTML = logs.quota_count
    ? `<div class="bad">发现 ${logs.quota_count} 条额度/网关相关告警；${excluded.length} 个 block 已整块排除主统计。</div><div class="mini">${excludedText}</div>`
    : `<div class="ok">未发现额度不足/余额不足/429/502/503 告警。</div>`;
  const cats = logs.sa_internal_warning_categories || {};
  const catText = Object.entries(cats).map(([k,v]) => `<span class="tag">${esc(k)}: ${esc(v)}</span>`).join(' ');
  $('saInternalBox').innerHTML = logs.sa_internal_warning_count
    ? `<div class="warn">SA-MCGS 内部窗口调用 warning: ${logs.sa_internal_warning_count} 条。注意：这些 warning 被算法兜底，不会显示为 method-level error。</div><div class="mini">${catText}</div>`
    : `<div class="ok">未发现 SA-MCGS 内部窗口调用 warning。</div>`;
  $('saWarningRows').innerHTML = (logs.recent_sa_internal_warnings || []).map(e => `<tr><td class="mono">${esc(e.task)}</td><td>${esc(e.domain)} ${esc(e.size)}</td><td><span class="tag">${esc(e.category)}</span></td><td class="small">${esc(e.line)}</td></tr>`).join('') || '<tr><td class="sub">No SA internal warnings.</td></tr>';
  $('errorRows').innerHTML = (logs.recent_errors || []).map(e => `<tr><td class="mono">${esc(e.task)}</td><td>${esc(e.domain)} ${esc(e.size)}</td><td class="small">${esc(e.line)}</td></tr>`).join('') || '<tr><td class="sub">No method-level errors yet.</td></tr>';
}
refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    status_files: list[Path]

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/status"):
            self._send(200, json.dumps(_payload(self.status_files), ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if self.path.startswith("/api/tasks"):
            status = _read_combined_status(self.status_files) if len(self.status_files) > 1 else _read_status(self.status_files[0])
            quota_excluded_ids = {
                task.get("task_id")
                for task in status.get("tasks", [])
                if task.get("status") == "done" and _task_quota_exhausted(task)
            }
            tasks = []
            for task in status.get("tasks", []):
                tasks.append({
                    "task_id": task.get("task_id"),
                    "status": task.get("status"),
                    "domain": task.get("domain"),
                    "size": task.get("size"),
                    "template": task.get("template"),
                    "attempt": task.get("attempt"),
                    "returncode": task.get("returncode"),
                    "quota_excluded": task.get("task_id") in quota_excluded_ids,
                    "started": time.strftime("%H:%M:%S", time.localtime(task.get("started_at"))) if task.get("started_at") else "-",
                    "ended": time.strftime("%H:%M:%S", time.localtime(task.get("ended_at"))) if task.get("ended_at") else "-",
                })
            self._send(200, json.dumps({"tasks": tasks}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        self._send(200, _html().encode(), "text/html; charset=utf-8")

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--status-file", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--status-files", nargs="*", type=Path)
    args = parser.parse_args()
    Handler.status_files = args.status_files or [args.status_file]
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Supplement progress dashboard: http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

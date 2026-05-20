"""Final critical-run dashboard for the ARR/EMNLP result review."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from progress_dashboard import _load_records_from_status, _metric_values


RESULTS_DIR = Path(__file__).resolve().parent / "results"
MAIN_EXPERIMENT_MANIFEST = Path(__file__).resolve().parent.parent / "main_experiment" / "MANIFEST.json"

MODEL_ORDER = ["gpt-4o", "deepseek-v3", "qwen2.5-72b", "gemini-2.5-pro"]
MODEL_LABEL = {
    "gpt-4o": "GPT-4o",
    "deepseek-v3": "DeepSeek-V3",
    "qwen2.5-72b": "Qwen2.5-72B",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
}
DOMAIN_ORDER = ["debian", "sec_ex21", "bgb", "cuad"]
DOMAIN_LABEL = {
    "debian": "Debian",
    "sec_ex21": "SEC EX-21",
    "bgb": "BGB",
    "cuad": "CUAD",
}

DEFAULT_CURRENT_STATUS_FILES = [
    "critical_paper_v3_b60_severity_grid_status.json",
    "critical_qwen_current_full80_b60_severity_grid_status.json",
    "gemini25pro_health_current_balanced_b60_severity_grid_status.json",
    "critical_gemini25pro_current_balanced_partA_b60_severity_grid_status.json",
    "critical_gemini25pro_current_balanced_partB_b60_severity_grid_status.json",
]


def _current_status_files_from_manifest() -> list[str]:
    if not MAIN_EXPERIMENT_MANIFEST.exists():
        return list(DEFAULT_CURRENT_STATUS_FILES)
    try:
        manifest = json.loads(MAIN_EXPERIMENT_MANIFEST.read_text())
    except Exception:
        return list(DEFAULT_CURRENT_STATUS_FILES)
    files: list[str] = []
    for item in manifest.get("canonical_status_files") or []:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or "").strip()
        if not raw_path:
            continue
        files.append(Path(raw_path).name)
    return files or list(DEFAULT_CURRENT_STATUS_FILES)


CURRENT_STATUS_FILES = _current_status_files_from_manifest()

BALANCED_STATUS_FILES = [
    "compression_profile_sweep_b60_net_severity_grid_status.json",
    "critical_dsgpt_balanced_fill80_partA_b60_severity_grid_status.json",
    "critical_dsgpt_balanced_fill80_partB_b60_severity_grid_status.json",
    "critical_balanced_b60_supp_qwen_gemini_severity_grid_status.json",
    "gemini25pro_health_current_balanced_b60_severity_grid_status.json",
    "critical_gemini25pro_current_balanced_partA_b60_severity_grid_status.json",
    "critical_gemini25pro_current_balanced_partB_b60_severity_grid_status.json",
]

CACHED_PAYLOAD: dict[str, Any] | None = None
CACHED_HTML: bytes | None = None
CACHED_API: bytes | None = None


def _read_status(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {"tasks": []}
    except Exception:
        return {"tasks": []}


def _profile(record: dict[str, Any]) -> str:
    return str(
        record.get("_task_compression_profile")
        or record.get("mcgs_compression_profile")
        or "current"
    )


def _severity(record: dict[str, Any]) -> str:
    return str(record.get("_task_severity") or record.get("injected_conflict_severity") or "")


def _template(record: dict[str, Any]) -> str:
    return str(record.get("_task_template") or record.get("injected_conflict_family") or "")


def _case_key(record: dict[str, Any], profile: str | None = None) -> tuple[str, ...]:
    return (
        str(record.get("domain", "")),
        str(record.get("scc_id", "")),
        str(record.get("scc_size", "")),
        str(record.get("model", "")),
        str(record.get("method", "")),
        _template(record),
        _severity(record),
        profile or _profile(record),
    )


def _load_selected(status_files: list[str], wanted_profile: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for filename in status_files:
        path = RESULTS_DIR / filename
        status = _read_status(path)
        for record in _load_records_from_status(status):
            if record.get("model") not in MODEL_ORDER:
                continue
            if record.get("method") not in {"naive", "sa-mcgs"}:
                continue
            if _severity(record) != "critical":
                continue
            if _profile(record) != wanted_profile:
                continue
            key = _case_key(record, wanted_profile)
            if key in seen:
                continue
            seen.add(key)
            enriched = dict(record)
            enriched["_source_status"] = filename
            enriched["_norm_profile"] = wanted_profile
            records.append(enriched)
    return records


def _rate(num: int, den: int) -> float:
    return num / den if den else 0.0


def _round_pct(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 100)


def _metric_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    errors = sum(1 for record in records if record.get("error"))
    metric_rows = [_metric_values(record) for record in records]

    def bool_rate(name: str) -> float:
        return _rate(sum(1 for metrics in metric_rows if metrics.get(name) is True), n)

    compressions: list[float] = []
    effective_compressions: list[float] = []
    subgraphs: list[float] = []
    for record, metrics in zip(records, metric_rows):
        if metrics.get("compression") is not None:
            try:
                comp = float(metrics["compression"])
            except Exception:
                continue
            compressions.append(comp)
            if metrics.get("risk_any") is True:
                effective_compressions.append(comp)
        if metrics.get("subgraph_size") is not None:
            try:
                subgraphs.append(float(metrics["subgraph_size"]))
            except Exception:
                pass

    oc_den = n
    oc_hit = sum(1 for record in records if record.get("method") == "sa-mcgs" and int(record.get("oc_count") or 0) > 0)
    effective_oc = sum(
        1
        for record, metrics in zip(records, metric_rows)
        if record.get("method") == "sa-mcgs" and metrics.get("effective_oc") is True
    )

    return {
        "n": n,
        "errors": errors,
        "valid": max(0, n - errors),
        "root": bool_rate("root_top3"),
        "risk_any": bool_rate("risk_any"),
        "risk_all": bool_rate("risk_all"),
        "compression": sum(compressions) / len(compressions) if compressions else None,
        "effective_compression": (
            sum(effective_compressions) / len(effective_compressions)
            if effective_compressions
            else None
        ),
        "avg_subgraph": sum(subgraphs) / len(subgraphs) if subgraphs else None,
        "oc": _rate(oc_hit, oc_den),
        "effective_oc": _rate(effective_oc, oc_den),
    }


def _group(records: list[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(key_fn(record))].append(record)
    rows = []
    for key, subset in groups.items():
        row = _metric_summary(subset)
        row["key"] = key
        rows.append(row)
    return rows


def _sort_model_method(row: dict[str, Any]) -> tuple[int, int]:
    model, _, method = row["key"].partition("|")
    return (
        MODEL_ORDER.index(model) if model in MODEL_ORDER else 999,
        0 if method == "naive" else 1,
    )


def _sort_domain_method(row: dict[str, Any]) -> tuple[int, int]:
    domain, _, method = row["key"].partition("|")
    return (
        DOMAIN_ORDER.index(domain) if domain in DOMAIN_ORDER else 999,
        0 if method == "naive" else 1,
    )


def _error_breakdown(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str, str]] = Counter()
    for record in records:
        if not record.get("error"):
            continue
        counter[(str(record.get("model")), str(record.get("method")), str(record.get("domain")))] += 1
    rows = [
        {"model": model, "method": method, "domain": domain, "count": count}
        for (model, method, domain), count in counter.items()
    ]
    rows.sort(key=lambda r: (-r["count"], r["model"], r["method"], r["domain"]))
    return rows


def _truthy(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1"}:
            return True
        if lowered in {"false", "no", "n", "0"}:
            return False
    return None


def _avg(values: list[Any]) -> float | None:
    nums: list[float] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            nums.append(1.0 if value else 0.0)
            continue
        try:
            nums.append(float(value))
        except Exception:
            continue
    if not nums:
        return None
    return sum(nums) / len(nums)


def _bool_rate(points: list[dict[str, Any]], key: str) -> float | None:
    values = [_truthy(point.get(key)) for point in points]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return sum(1 for value in values if value) / len(values)


def _convergence_series(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_rollout: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("method") != "sa-mcgs":
            continue
        trace = record.get("convergence_trace")
        if not isinstance(trace, list):
            continue
        for point in trace:
            if not isinstance(point, dict):
                continue
            try:
                rollout = int(point.get("rollout") or 0)
            except Exception:
                continue
            if rollout <= 0:
                continue
            by_rollout[rollout].append(point)
    series: list[dict[str, Any]] = []
    for rollout in sorted(by_rollout):
        points = by_rollout[rollout]
        series.append({
            "rollout": rollout,
            "n": len(points),
            "risk_any": _bool_rate(points, "risk_any"),
            "risk_all": _bool_rate(points, "risk_all"),
            "effective_oc": _bool_rate(points, "effective_oc"),
            "compression": _avg([point.get("compression_ratio") for point in points]),
            "risk_coverage": _avg([point.get("risk_coverage") for point in points]),
            "valuable_coverage": _avg([point.get("valuable_coverage") for point in points]),
        })
    return series


def _convergence_by_model(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for model in MODEL_ORDER:
        subset = [record for record in records if record.get("model") == model and record.get("method") == "sa-mcgs"]
        if not subset:
            continue
        series = _convergence_series(subset)
        final = series[-1] if series else {}
        rows.append({
            "model": model,
            "n": len(subset),
            "series": series,
            "final": final,
        })
    return rows


def _record_size(record: dict[str, Any]) -> int:
    for key in ("scc_size", "_task_size"):
        try:
            value = int(record.get(key) or 0)
        except Exception:
            continue
        if value > 0:
            return value
    return 0


def _size_trend_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_size_method: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        method = str(record.get("method"))
        if method not in {"naive", "sa-mcgs"}:
            continue
        size = _record_size(record)
        if size <= 0:
            continue
        by_size_method[(size, method)].append(record)
    sizes = sorted({size for size, _method in by_size_method})
    rows = []
    for size in sizes:
        naive = _metric_summary(by_size_method.get((size, "naive"), []))
        sa = _metric_summary(by_size_method.get((size, "sa-mcgs"), []))
        if not naive["n"] or not sa["n"]:
            continue
        rows.append({
            "size": size,
            "naive": naive,
            "sa": sa,
        })
    return rows


def _size_bucket(size: int) -> str:
    if size <= 12:
        return "short <=12"
    if size <= 20:
        return "mid 14-20"
    return "long >=24"


def _size_bucket_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_bucket_method: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        method = str(record.get("method"))
        if method not in {"naive", "sa-mcgs"}:
            continue
        size = _record_size(record)
        if size <= 0:
            continue
        by_bucket_method[(_size_bucket(size), method)].append(record)
    order = ["short <=12", "mid 14-20", "long >=24"]
    rows = []
    for bucket in order:
        naive = _metric_summary(by_bucket_method.get((bucket, "naive"), []))
        sa = _metric_summary(by_bucket_method.get((bucket, "sa-mcgs"), []))
        if not naive["n"] or not sa["n"]:
            continue
        rows.append({
            "bucket": bucket,
            "naive": naive,
            "sa": sa,
        })
    return rows


def _best_delta_rows(current_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for model in MODEL_ORDER:
        naive = [r for r in current_records if r.get("model") == model and r.get("method") == "naive"]
        sa = [r for r in current_records if r.get("model") == model and r.get("method") == "sa-mcgs"]
        if not naive or not sa:
            continue
        ns = _metric_summary(naive)
        ss = _metric_summary(sa)
        rows.append({
            "model": model,
            "root_delta": ss["root"] - ns["root"],
            "any_delta": ss["risk_any"] - ns["risk_any"],
            "all_delta": ss["risk_all"] - ns["risk_all"],
            "error_delta": ns["errors"] - ss["errors"],
            "naive": ns,
            "sa": ss,
        })
    rows.sort(key=lambda r: (r["all_delta"], r["root_delta"]), reverse=True)
    return rows


def _payload() -> dict[str, Any]:
    current = _load_selected(CURRENT_STATUS_FILES, "current")
    balanced_all = _load_selected(BALANCED_STATUS_FILES, "balanced")
    balanced_sa = [r for r in balanced_all if r.get("method") == "sa-mcgs"]

    current_model_rows = _group(current, lambda r: f"{r.get('model')}|{r.get('method')}")
    current_model_rows.sort(key=_sort_model_method)
    current_domain_rows = _group(current, lambda r: f"{r.get('domain')}|{r.get('method')}")
    current_domain_rows.sort(key=_sort_domain_method)

    balanced_sa_rows = _group(balanced_sa, lambda r: str(r.get("model")))
    balanced_sa_rows.sort(key=lambda r: MODEL_ORDER.index(r["key"]) if r["key"] in MODEL_ORDER else 999)

    current_sa_rows = _group([r for r in current if r.get("method") == "sa-mcgs"], lambda r: str(r.get("model")))
    current_sa_by_model = {row["key"]: row for row in current_sa_rows}
    profile_tradeoff = []
    for row in balanced_sa_rows:
        model = row["key"]
        cur = current_sa_by_model.get(model)
        if not cur:
            continue
        profile_tradeoff.append({
            "model": model,
            "current": cur,
            "balanced": row,
            "compression_gain": (row["compression"] or 0) - (cur["compression"] or 0),
            "risk_all_delta": row["risk_all"] - cur["risk_all"],
        })

    current_by_method = _group(current, lambda r: str(r.get("method")))
    current_by_method.sort(key=lambda r: 0 if r["key"] == "naive" else 1)

    return {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sources": {
            "current": CURRENT_STATUS_FILES,
            "balanced": BALANCED_STATUS_FILES,
        },
        "records": {
            "current": len(current),
            "balanced_sa": len(balanced_sa),
        },
        "current_overall": current_by_method,
        "current_by_model": current_model_rows,
        "current_by_domain": current_domain_rows,
        "balanced_sa_by_model": balanced_sa_rows,
        "profile_tradeoff": profile_tradeoff,
        "size_trend": _size_trend_rows(current),
        "size_buckets": _size_bucket_rows(current),
        "convergence": {
            "overall": _convergence_series(current),
            "by_model": _convergence_by_model(current),
        },
        "deltas": _best_delta_rows(current),
        "errors": _error_breakdown(current),
    }


def _html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SA-MCGS Final Results</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0d1117;
      --panel: #151b23;
      --panel2: #1f2630;
      --line: #313a49;
      --text: #f3f7ff;
      --muted: #9aa8bd;
      --naive: #ff6b6b;
      --sa: #20c997;
      --blue: #68a3ff;
      --purple: #b084ff;
      --yellow: #f6bd60;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(32, 201, 151, 0.14), transparent 34rem),
        radial-gradient(circle at 80% 0%, rgba(104, 163, 255, 0.12), transparent 34rem),
        var(--bg);
      color: var(--text);
    }
    main { max-width: 1680px; margin: 0 auto; padding: 34px 36px 60px; }
    h1 { font-size: 52px; line-height: 1.02; margin: 0 0 14px; letter-spacing: 0; }
    h2 { font-size: 32px; margin: 0 0 22px; letter-spacing: 0; }
    h3 { font-size: 22px; margin: 0 0 12px; }
    p { color: var(--muted); font-size: 18px; line-height: 1.55; margin: 0; }
    .hero {
      border: 1px solid var(--line);
      background: rgba(21, 27, 35, 0.88);
      padding: 30px;
      border-radius: 8px;
      margin-bottom: 24px;
    }
    .claim {
      font-size: 24px;
      line-height: 1.45;
      color: #dce8ff;
      max-width: 1180px;
    }
    .claim b { color: #ffffff; }
    .grid { display: grid; gap: 18px; }
    .grid.cols4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .grid.cols2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .card {
      background: rgba(21, 27, 35, 0.94);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
    }
    .kpi-label { color: var(--muted); font-size: 15px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }
    .kpi-main { font-size: 42px; font-weight: 900; margin-top: 8px; }
    .kpi-main .naive { color: var(--naive); }
    .kpi-main .sa { color: var(--sa); }
    .kpi-sub { margin-top: 8px; color: var(--muted); font-size: 15px; line-height: 1.4; }
    section { margin-top: 26px; }
    .chart {
      background: #101720;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px 24px;
      overflow: hidden;
    }
    .bars { display: grid; gap: 15px; }
    .bar-row {
      display: grid;
      grid-template-columns: 190px 1fr 70px;
      align-items: center;
      gap: 14px;
      min-height: 28px;
    }
    .bar-label { color: #d7e2f4; font-size: 16px; font-weight: 750; }
    .bar-track { height: 18px; background: #222b38; border-radius: 99px; position: relative; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 99px; min-width: 3px; }
    .bar-value { color: #eaf2ff; font-weight: 850; font-size: 16px; text-align: right; }
    .naive-fill { background: var(--naive); }
    .sa-fill { background: var(--sa); }
    .blue-fill { background: var(--blue); }
    .purple-fill { background: var(--purple); }
    .yellow-fill { background: var(--yellow); }
    .small { font-size: 14px; color: var(--muted); }
    .pill {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 6px 10px; border: 1px solid var(--line); border-radius: 999px;
      background: var(--panel2); color: #dce8ff; font-weight: 750; font-size: 14px;
    }
    .legend { display: flex; gap: 14px; flex-wrap: wrap; margin: 14px 0 18px; }
    .legend span::before {
      content: ""; display: inline-block; width: 18px; height: 5px; border-radius: 99px; margin-right: 8px; vertical-align: middle;
    }
    .legend .naive::before { background: var(--naive); }
    .legend .sa::before { background: var(--sa); }
    .legend .balanced::before { background: var(--purple); }
    .table-wrap { overflow: auto; border: 1px solid var(--line); border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; min-width: 900px; }
    th, td { padding: 13px 15px; border-bottom: 1px solid var(--line); text-align: left; font-size: 15px; }
    th { color: #d7e2f4; background: #121923; position: sticky; top: 0; z-index: 1; }
    td { color: #ecf3ff; }
    tr:last-child td { border-bottom: 0; }
    .good { color: var(--sa); font-weight: 900; }
    .bad { color: var(--naive); font-weight: 900; }
    .warn { color: var(--yellow); font-weight: 900; }
    .matrix { display: grid; gap: 16px; }
    .model-card {
      display: grid;
      grid-template-columns: 170px 1fr;
      gap: 18px;
      align-items: start;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      background: #111820;
    }
    .model-name { font-size: 22px; font-weight: 900; }
    .metric-group { display: grid; gap: 9px; }
    .split-row {
      display: grid;
      grid-template-columns: 90px 1fr 58px 1fr 58px;
      gap: 9px;
      align-items: center;
    }
    .split-row .metric { color: var(--muted); font-weight: 750; }
    .note {
      border-left: 5px solid var(--sa);
      padding: 16px 18px;
      background: rgba(32, 201, 151, 0.08);
      color: #dce8ff;
      font-size: 17px;
      line-height: 1.55;
    }
    .scatter { width: 100%; height: 390px; display: block; background: #101720; border-radius: 8px; }
    .footer-space { height: 30px; }
    @media (max-width: 1100px) {
      .grid.cols4, .grid.cols2 { grid-template-columns: 1fr; }
      .bar-row { grid-template-columns: 140px 1fr 56px; }
      .model-card { grid-template-columns: 1fr; }
      main { padding: 22px 16px 42px; }
      h1 { font-size: 38px; }
    }
  </style>
</head>
<body>
<main>
  <div class="hero">
    <div class="pill">Critical structural-conflict · 4 domains · 4 models · 80 SCC blocks</div>
    <h1>SA-MCGS Final Results</h1>
    <p class="claim" id="claim">Loading...</p>
  </div>

  <div class="grid cols4" id="kpis"></div>

  <section class="grid cols2">
    <div class="card">
      <h2>主结果：Current / Default</h2>
      <p>strict rate：模型报错或 JSON 解析失败都计入分母。</p>
      <div class="legend"><span class="naive">Naive</span><span class="sa">SA-MCGS</span></div>
      <div class="chart"><div class="bars" id="overallBars"></div></div>
    </div>
    <div class="card">
      <h2>错误分布</h2>
      <p>主要看 one-shot 是否在长 SCC / 长合同文本下失稳。</p>
      <div class="chart"><div class="bars" id="errorBars"></div></div>
    </div>
  </section>

  <section class="card">
    <h2>按模型展开</h2>
    <p>每个模型内部比较 Naive 和 SA-MCGS；这是最适合放进论文主表的视角。</p>
    <div class="matrix" id="modelMatrix"></div>
  </section>

  <section class="grid cols2">
    <div class="card">
      <h2>压缩强度消融</h2>
      <p>Balanced 会提高压缩率，但部分模型会牺牲 Risk-all。Current 更适合作为主结果。</p>
      <div class="chart"><div class="bars" id="profileBars"></div></div>
    </div>
    <div class="card">
      <h2>压缩率 vs Risk-all</h2>
      <p>横轴是压缩率，纵轴是 Risk-all。右上角最好；紫点是 balanced，绿点是 current。</p>
      <svg class="scatter" id="scatter" viewBox="0 0 760 390" role="img"></svg>
    </div>
  </section>

  <section class="card">
    <h2>按领域展开</h2>
    <p>CUAD 是 Naive 最容易崩的领域；BGB/SEC/Debian 更能看结构定位与压缩的稳定性。</p>
    <div class="chart"><div class="bars" id="domainBars"></div></div>
  </section>

  <section class="card">
    <h2>核心数据表</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Model</th><th>Profile</th><th>Method</th><th>N</th><th>Err</th>
            <th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Compression</th><th>Eff. Comp.</th><th>Eff. OC</th>
          </tr>
        </thead>
        <tbody id="mainTable"></tbody>
      </table>
    </div>
  </section>
  <div class="footer-space"></div>
</main>

<script>
const MODEL_LABEL = {
  "gpt-4o": "GPT-4o",
  "deepseek-v3": "DeepSeek-V3",
  "qwen2.5-72b": "Qwen2.5-72B",
  "gemini-2.5-pro": "Gemini 2.5 Pro"
};
const DOMAIN_LABEL = {
  "debian": "Debian",
  "sec_ex21": "SEC EX-21",
  "bgb": "BGB",
  "cuad": "CUAD"
};
const metrics = [
  ["root", "Root@3"],
  ["risk_any", "Risk-any"],
  ["risk_all", "Risk-all"],
  ["compression", "Compression"]
];
function pct(v) { return v === null || v === undefined ? "-" : `${Math.round(v * 100)}%`; }
function num(v, d=1) { return v === null || v === undefined ? "-" : Number(v).toFixed(d); }
function rateCell(row, key) { return `${Math.round((row[key] || 0) * row.n)}/${row.n} (${pct(row[key])})`; }
function fill(value, cls) {
  const width = Math.max(0, Math.min(100, Math.round((value || 0) * 100)));
  return `<div class="bar-track"><div class="bar-fill ${cls}" style="width:${width}%"></div></div>`;
}
function bar(label, value, cls="sa-fill") {
  return `<div class="bar-row"><div class="bar-label">${label}</div>${fill(value, cls)}<div class="bar-value">${pct(value)}</div></div>`;
}
function splitBar(metric, nVal, sVal) {
  return `<div class="split-row">
    <div class="metric">${metric}</div>
    ${fill(nVal, "naive-fill")}<div class="bar-value">${pct(nVal)}</div>
    ${fill(sVal, "sa-fill")}<div class="bar-value">${pct(sVal)}</div>
  </div>`;
}
function loadJson(url) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.onreadystatechange = () => {
      if (xhr.readyState !== 4) return;
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText)); }
        catch (err) { reject(err); }
      } else {
        reject(new Error(`HTTP ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("request failed"));
    xhr.send();
  });
}
function rowsByKey(rows) {
  const m = {};
  for (const r of rows) m[r.key] = r;
  return m;
}
function modelMethodMap(rows) {
  const out = {};
  for (const r of rows) {
    const [model, method] = r.key.split("|");
    out[`${model}|${method}`] = r;
  }
  return out;
}
async function main() {
  const data = await loadJson("/api");
  const overall = rowsByKey(data.current_overall);
  const naive = overall.naive;
  const sa = overall["sa-mcgs"];
  document.getElementById("claim").innerHTML =
    `合并当前主实验和补充实验后，<b>Current/default</b> 口径下 SA-MCGS 相比 Naive：` +
    `<b>Root@3 ${pct(naive.root)} → ${pct(sa.root)}</b>，` +
    `<b>Risk-any ${pct(naive.risk_any)} → ${pct(sa.risk_any)}</b>，` +
    `<b>Risk-all ${pct(naive.risk_all)} → ${pct(sa.risk_all)}</b>。` +
    `代价是子图更大，平均压缩率从 <b>${pct(naive.compression)}</b> 到 <b>${pct(sa.compression)}</b>；` +
    `但 SA-MCGS 额外给出 <b>Effective OC ${pct(sa.effective_oc)}</b> 的结构证据。`;

  document.getElementById("kpis").innerHTML = [
    ["Root@3", naive.root, sa.root, "注入 root 是否进 Top-3"],
    ["Risk-any", naive.risk_any, sa.risk_any, "至少保留一个可修复风险点"],
    ["Risk-all", naive.risk_all, sa.risk_all, "root/witness 等关键端点全部保留"],
    ["Method errors", naive.errors / naive.n, sa.errors / sa.n, "返回错误或解析失败比例"]
  ].map(([name, n, s, sub]) => `
    <div class="card">
      <div class="kpi-label">${name}</div>
      <div class="kpi-main"><span class="naive">${pct(n)}</span> → <span class="sa">${pct(s)}</span></div>
      <div class="kpi-sub">${sub}</div>
    </div>`).join("");

  document.getElementById("overallBars").innerHTML = metrics.map(([k, label]) =>
    bar(`${label} · Naive`, naive[k], "naive-fill") + bar(`${label} · SA`, sa[k], "sa-fill")
  ).join("");

  const errors = data.errors.slice(0, 8);
  const maxErr = Math.max(1, ...errors.map(e => e.count));
  document.getElementById("errorBars").innerHTML = errors.map(e => {
    const label = `${MODEL_LABEL[e.model] || e.model} / ${e.method} / ${DOMAIN_LABEL[e.domain] || e.domain}`;
    return `<div class="bar-row"><div class="bar-label">${label}</div>
      <div class="bar-track"><div class="bar-fill naive-fill" style="width:${Math.round(e.count / maxErr * 100)}%"></div></div>
      <div class="bar-value">${e.count}</div></div>`;
  }).join("") || `<p>没有错误。</p>`;

  const mm = modelMethodMap(data.current_by_model);
  document.getElementById("modelMatrix").innerHTML = Object.keys(MODEL_LABEL).map(model => {
    const n = mm[`${model}|naive`];
    const s = mm[`${model}|sa-mcgs`];
    if (!n || !s) return "";
    return `<div class="model-card">
      <div>
        <div class="model-name">${MODEL_LABEL[model]}</div>
        <div class="small">N=${n.n} per method · Naive err=${n.errors}, SA err=${s.errors}</div>
      </div>
      <div class="metric-group">
        ${splitBar("Root@3", n.root, s.root)}
        ${splitBar("Risk-any", n.risk_any, s.risk_any)}
        ${splitBar("Risk-all", n.risk_all, s.risk_all)}
        ${splitBar("Compression", n.compression, s.compression)}
      </div>
    </div>`;
  }).join("");

  const trade = data.profile_tradeoff;
  document.getElementById("profileBars").innerHTML = trade.map(t => {
    const label = MODEL_LABEL[t.model] || t.model;
    return `<h3>${label}</h3>` +
      bar("Current Risk-all", t.current.risk_all, "sa-fill") +
      bar("Balanced Risk-all", t.balanced.risk_all, "purple-fill") +
      bar("Current Compression", t.current.compression, "blue-fill") +
      bar("Balanced Compression", t.balanced.compression, "yellow-fill");
  }).join("");

  drawScatter(trade);

  const domainMap = {};
  for (const r of data.current_by_domain) domainMap[r.key] = r;
  document.getElementById("domainBars").innerHTML = Object.keys(DOMAIN_LABEL).map(domain => {
    const n = domainMap[`${domain}|naive`];
    const s = domainMap[`${domain}|sa-mcgs`];
    if (!n || !s) return "";
    return `<h3>${DOMAIN_LABEL[domain]}</h3>` +
      bar("Naive Risk-all", n.risk_all, "naive-fill") +
      bar("SA Risk-all", s.risk_all, "sa-fill") +
      bar("SA Effective OC", s.effective_oc, "blue-fill");
  }).join("");

  const tableRows = [];
  for (const r of data.current_by_model) {
    const [model, method] = r.key.split("|");
    tableRows.push({model, profile:"current", method, row:r});
  }
  for (const r of data.balanced_sa_by_model) {
    tableRows.push({model:r.key, profile:"balanced", method:"sa-mcgs", row:r});
  }
  document.getElementById("mainTable").innerHTML = tableRows.map(x => {
    const r = x.row;
    return `<tr>
      <td>${MODEL_LABEL[x.model] || x.model}</td>
      <td>${x.profile}</td>
      <td>${x.method}</td>
      <td>${r.n}</td>
      <td class="${r.errors ? "bad" : "good"}">${r.errors}</td>
      <td>${rateCell(r, "root")}</td>
      <td>${rateCell(r, "risk_any")}</td>
      <td>${rateCell(r, "risk_all")}</td>
      <td>${pct(r.compression)}</td>
      <td>${pct(r.effective_compression)}</td>
      <td>${x.method === "sa-mcgs" ? pct(r.effective_oc) : "-"}</td>
    </tr>`;
  }).join("");
}
function drawScatter(trade) {
  const svg = document.getElementById("scatter");
  const pad = {l: 60, r: 22, t: 28, b: 58};
  const w = 760, h = 390;
  const x = v => pad.l + (v - 0.45) / 0.35 * (w - pad.l - pad.r);
  const y = v => h - pad.b - (v - 0.55) / 0.45 * (h - pad.t - pad.b);
  let html = "";
  for (let i = 0; i <= 5; i++) {
    const yy = pad.t + i * (h - pad.t - pad.b) / 5;
    html += `<line x1="${pad.l}" y1="${yy}" x2="${w-pad.r}" y2="${yy}" stroke="#263241"/>`;
  }
  for (let i = 0; i <= 5; i++) {
    const xx = pad.l + i * (w - pad.l - pad.r) / 5;
    html += `<line x1="${xx}" y1="${pad.t}" x2="${xx}" y2="${h-pad.b}" stroke="#263241"/>`;
  }
  html += `<text x="${pad.l}" y="${h-18}" fill="#9aa8bd" font-size="14">Compression</text>`;
  html += `<text x="16" y="26" fill="#9aa8bd" font-size="14">Risk-all</text>`;
  for (const t of trade) {
    const label = MODEL_LABEL[t.model] || t.model;
    const points = [
      [t.current.compression, t.current.risk_all, "#20c997", "current"],
      [t.balanced.compression, t.balanced.risk_all, "#b084ff", "balanced"],
    ];
    for (const [cx, cy, color, profile] of points) {
      html += `<circle cx="${x(cx)}" cy="${y(cy)}" r="8" fill="${color}"/>`;
      html += `<text x="${x(cx)+12}" y="${y(cy)+5}" fill="#dce8ff" font-size="13">${label} ${profile}</text>`;
    }
    html += `<line x1="${x(t.current.compression)}" y1="${y(t.current.risk_all)}" x2="${x(t.balanced.compression)}" y2="${y(t.balanced.risk_all)}" stroke="#5f6c7b" stroke-width="2" stroke-dasharray="5 5"/>`;
  }
  svg.innerHTML = html;
}
main();
</script>
</body>
</html>"""


def _pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.0%}"
    except Exception:
        return "-"


def _safe_width(value: Any) -> int:
    try:
        return max(0, min(100, round(float(value) * 100)))
    except Exception:
        return 0


def _bar(label: str, value: Any, cls: str = "sa-fill") -> str:
    return (
        '<div class="bar-row">'
        f'<div class="bar-label">{label}</div>'
        f'<div class="bar-track"><div class="bar-fill {cls}" style="width:{_safe_width(value)}%"></div></div>'
        f'<div class="bar-value">{_pct(value)}</div>'
        '</div>'
    )


def _rate_cell(row: dict[str, Any], key: str) -> str:
    n = int(row.get("n") or 0)
    value = float(row.get(key) or 0)
    return f"{round(value * n)}/{n} ({_pct(value)})"


def _rows_by_key(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["key"]): row for row in rows}


def _split_bar(metric: str, naive_value: Any, sa_value: Any) -> str:
    return (
        '<div class="split-row">'
        f'<div class="metric">{metric}</div>'
        f'<div class="bar-track"><div class="bar-fill naive-fill" style="width:{_safe_width(naive_value)}%"></div></div>'
        f'<div class="bar-value">{_pct(naive_value)}</div>'
        f'<div class="bar-track"><div class="bar-fill sa-fill" style="width:{_safe_width(sa_value)}%"></div></div>'
        f'<div class="bar-value">{_pct(sa_value)}</div>'
        '</div>'
    )


def _render_scatter(tradeoff: list[dict[str, Any]]) -> str:
    width, height = 760, 390
    pad_l, pad_r, pad_t, pad_b = 60, 22, 28, 58

    def x_pos(value: float) -> float:
        return pad_l + (value - 0.45) / 0.35 * (width - pad_l - pad_r)

    def y_pos(value: float) -> float:
        return height - pad_b - (value - 0.55) / 0.45 * (height - pad_t - pad_b)

    parts = [
        f'<svg class="scatter" viewBox="0 0 {width} {height}" role="img">'
    ]
    for i in range(6):
        y = pad_t + i * (height - pad_t - pad_b) / 5
        x = pad_l + i * (width - pad_l - pad_r) / 5
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#263241"/>')
        parts.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{height-pad_b}" stroke="#263241"/>')
    parts.append(f'<text x="{pad_l}" y="{height-18}" fill="#9aa8bd" font-size="14">Compression</text>')
    parts.append('<text x="16" y="26" fill="#9aa8bd" font-size="14">Risk-all</text>')
    for item in tradeoff:
        label = MODEL_LABEL.get(str(item["model"]), str(item["model"]))
        current = item["current"]
        balanced = item["balanced"]
        points = [
            (current.get("compression") or 0, current.get("risk_all") or 0, "#20c997", "current"),
            (balanced.get("compression") or 0, balanced.get("risk_all") or 0, "#b084ff", "balanced"),
        ]
        x1, y1 = x_pos(float(points[0][0])), y_pos(float(points[0][1]))
        x2, y2 = x_pos(float(points[1][0])), y_pos(float(points[1][1]))
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#5f6c7b" stroke-width="2" stroke-dasharray="5 5"/>')
        for comp, risk_all, color, profile in points:
            cx, cy = x_pos(float(comp)), y_pos(float(risk_all))
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8" fill="{color}"/>')
            parts.append(f'<text x="{cx+12:.1f}" y="{cy+5:.1f}" fill="#dce8ff" font-size="13">{label} {profile}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _polyline(points: list[tuple[float, float]], color: str, width: int = 4, dashed: bool = False) -> str:
    if len(points) < 2:
        return ""
    coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    dash = ' stroke-dasharray="8 7"' if dashed else ""
    return f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{dash}/>'


def _render_convergence_chart(
    series: list[dict[str, Any]],
    title: str,
    width: int = 1120,
    height: int = 420,
    compact: bool = False,
) -> str:
    if not series:
        return '<div class="note">没有 convergence trace。</div>'
    pad_l, pad_r, pad_t, pad_b = 62, 28, 46, 54
    max_rollout = max(int(point.get("rollout") or 0) for point in series) or 1

    def x_pos(rollout: int) -> float:
        if max_rollout <= 1:
            return pad_l
        return pad_l + (rollout - 1) / (max_rollout - 1) * (width - pad_l - pad_r)

    def y_pos(value: Any) -> float:
        try:
            v = max(0.0, min(1.0, float(value)))
        except Exception:
            v = 0.0
        return height - pad_b - v * (height - pad_t - pad_b)

    curves = [
        ("risk_any", "Risk-any", "#20c997", False),
        ("risk_all", "Risk-all", "#b084ff", False),
        ("effective_oc", "Effective OC", "#ff6b6b", False),
        ("compression", "Compression", "#f6bd60", True),
    ]
    parts = [f'<svg class="scatter" viewBox="0 0 {width} {height}" role="img">']
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" rx="8" fill="#101720"/>')
    for i in range(6):
        y = pad_t + i * (height - pad_t - pad_b) / 5
        value = 1 - i / 5
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#263241"/>')
        parts.append(f'<text x="18" y="{y+5:.1f}" fill="#9aa8bd" font-size="13">{value:.0%}</text>')
    for rollout in [1, 10, 20, 30, 40, 50, max_rollout]:
        if rollout > max_rollout:
            continue
        x = x_pos(rollout)
        parts.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{height-pad_b}" stroke="#1e2937"/>')
        parts.append(f'<text x="{x-10:.1f}" y="{height-20}" fill="#9aa8bd" font-size="13">{rollout}</text>')
    parts.append(f'<text x="{pad_l}" y="26" fill="#eaf2ff" font-size="{18 if compact else 22}" font-weight="800">{title}</text>')
    parts.append(f'<text x="{width - 150}" y="{height - 20}" fill="#9aa8bd" font-size="13">Rollout</text>')
    legend_x = pad_l + 300 if not compact else pad_l + 190
    for idx, (_key, label, color, dashed) in enumerate(curves):
        lx = legend_x + idx * (150 if not compact else 118)
        dash_attr = ' stroke-dasharray="8 7"' if dashed else ""
        parts.append(f'<line x1="{lx}" y1="22" x2="{lx+28}" y2="22" stroke="{color}" stroke-width="4" stroke-linecap="round"{dash_attr}/>')
        parts.append(f'<text x="{lx+36}" y="27" fill="#dce8ff" font-size="13">{label}</text>')
    for key, _label, color, dashed in curves:
        pts: list[tuple[float, float]] = []
        for point in series:
            value = point.get(key)
            if value is None:
                continue
            pts.append((x_pos(int(point.get("rollout") or 0)), y_pos(value)))
        parts.append(_polyline(pts, color, 4 if not compact else 3, dashed=dashed))
        if pts:
            final_value = series[-1].get(key)
            parts.append(
                f'<text x="{pts[-1][0]-46:.1f}" y="{pts[-1][1]-8:.1f}" fill="{color}" '
                f'font-size="13" font-weight="800">{_pct(final_value)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _render_size_metric_chart(
    rows: list[dict[str, Any]],
    metric: str,
    title: str,
    width: int = 1120,
    height: int = 320,
) -> str:
    if not rows:
        return '<div class="note">没有按 SCC size 聚合的数据。</div>'
    pad_l, pad_r, pad_t, pad_b = 64, 28, 44, 58

    def x_pos(index: int) -> float:
        if len(rows) <= 1:
            return pad_l
        return pad_l + index / (len(rows) - 1) * (width - pad_l - pad_r)

    def y_pos(value: Any) -> float:
        try:
            v = max(0.0, min(1.0, float(value)))
        except Exception:
            v = 0.0
        return height - pad_b - v * (height - pad_t - pad_b)

    parts = [f'<svg class="scatter" viewBox="0 0 {width} {height}" role="img">']
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" rx="8" fill="#101720"/>')
    for i in range(6):
        y = pad_t + i * (height - pad_t - pad_b) / 5
        value = 1 - i / 5
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#263241"/>')
        parts.append(f'<text x="18" y="{y+5:.1f}" fill="#9aa8bd" font-size="13">{value:.0%}</text>')
    for idx, row in enumerate(rows):
        x = x_pos(idx)
        size = row["size"]
        parts.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{height-pad_b}" stroke="#1e2937"/>')
        parts.append(f'<text x="{x-10:.1f}" y="{height-22}" fill="#9aa8bd" font-size="12">{size}</text>')
    parts.append(f'<text x="{pad_l}" y="26" fill="#eaf2ff" font-size="22" font-weight="800">{title}</text>')
    parts.append(f'<text x="{width - 132}" y="{height - 22}" fill="#9aa8bd" font-size="13">SCC size</text>')
    legend_x = pad_l + 330
    parts.append(f'<line x1="{legend_x}" y1="22" x2="{legend_x+28}" y2="22" stroke="#ff6b6b" stroke-width="4" stroke-linecap="round"/>')
    parts.append(f'<text x="{legend_x+36}" y="27" fill="#dce8ff" font-size="13">Naive</text>')
    parts.append(f'<line x1="{legend_x+118}" y1="22" x2="{legend_x+146}" y2="22" stroke="#20c997" stroke-width="4" stroke-linecap="round"/>')
    parts.append(f'<text x="{legend_x+154}" y="27" fill="#dce8ff" font-size="13">SA-MCGS</text>')

    for method, color in [("naive", "#ff6b6b"), ("sa", "#20c997")]:
        pts = []
        for idx, row in enumerate(rows):
            value = row[method].get(metric)
            pts.append((x_pos(idx), y_pos(value)))
        parts.append(_polyline(pts, color, 4))
        for idx, (x, y) in enumerate(pts):
            row = rows[idx]
            value = row[method].get(metric)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}"/>')
            if idx in {0, len(pts) - 1}:
                parts.append(
                    f'<text x="{x-20:.1f}" y="{y-10:.1f}" fill="{color}" font-size="12" '
                    f'font-weight="800">{_pct(value)}</text>'
                )
    parts.append("</svg>")
    return "".join(parts)


def _render_html(data: dict[str, Any]) -> str:
    overall = _rows_by_key(data["current_overall"])
    naive = overall["naive"]
    sa = overall["sa-mcgs"]
    claim = (
        "合并当前主实验和补充实验后，<b>Current/default</b> 口径下 SA-MCGS 相比 Naive："
        f"<b>Root@3 {_pct(naive['root'])} → {_pct(sa['root'])}</b>，"
        f"<b>Risk-any {_pct(naive['risk_any'])} → {_pct(sa['risk_any'])}</b>，"
        f"<b>Risk-all {_pct(naive['risk_all'])} → {_pct(sa['risk_all'])}</b>。"
        f"代价是子图更大，平均压缩率从 <b>{_pct(naive['compression'])}</b> 到 "
        f"<b>{_pct(sa['compression'])}</b>；但 SA-MCGS 额外给出 "
        f"<b>Effective OC {_pct(sa['effective_oc'])}</b> 的结构证据。"
    )
    kpis = "".join(
        [
            (
                '<div class="card">'
                f'<div class="kpi-label">{name}</div>'
                f'<div class="kpi-main"><span class="naive">{_pct(n_val)}</span> → <span class="sa">{_pct(s_val)}</span></div>'
                f'<div class="kpi-sub">{sub}</div>'
                '</div>'
            )
            for name, n_val, s_val, sub in [
                ("Root@3", naive["root"], sa["root"], "注入 root 是否进 Top-3"),
                ("Risk-any", naive["risk_any"], sa["risk_any"], "至少保留一个可修复风险点"),
                ("Risk-all", naive["risk_all"], sa["risk_all"], "root/witness 等关键端点全部保留"),
                ("Method errors", naive["errors"] / naive["n"], sa["errors"] / sa["n"], "返回错误或解析失败比例"),
            ]
        ]
    )
    overall_bars = "".join(
        _bar(f"{label} · Naive", naive[key], "naive-fill") + _bar(f"{label} · SA", sa[key], "sa-fill")
        for key, label in [
            ("root", "Root@3"),
            ("risk_any", "Risk-any"),
            ("risk_all", "Risk-all"),
            ("compression", "Compression"),
        ]
    )
    errors = data["errors"][:8]
    max_err = max([1] + [int(row["count"]) for row in errors])
    error_bars = "".join(
        (
            '<div class="bar-row">'
            f'<div class="bar-label">{MODEL_LABEL.get(row["model"], row["model"])} / {row["method"]} / {DOMAIN_LABEL.get(row["domain"], row["domain"])}</div>'
            f'<div class="bar-track"><div class="bar-fill naive-fill" style="width:{round(row["count"] / max_err * 100)}%"></div></div>'
            f'<div class="bar-value">{row["count"]}</div>'
            '</div>'
        )
        for row in errors
    ) or "<p>没有错误。</p>"
    size_charts = "".join(
        '<div class="chart">'
        + _render_size_metric_chart(data["size_trend"], metric, title, width=760, height=300)
        + "</div>"
        for metric, title in [
            ("root", "Root@3 by SCC size"),
            ("risk_any", "Risk-any by SCC size"),
            ("risk_all", "Risk-all by SCC size"),
            ("compression", "Compression by SCC size"),
        ]
    )
    bucket_rows = "".join(
        (
            "<tr>"
            f"<td>{row['bucket']}</td>"
            f"<td>{row['naive']['n']}</td>"
            f"<td>{_pct(row['naive']['root'])} → <b class=\"good\">{_pct(row['sa']['root'])}</b></td>"
            f"<td>{_pct(row['naive']['risk_any'])} → <b class=\"good\">{_pct(row['sa']['risk_any'])}</b></td>"
            f"<td>{_pct(row['naive']['risk_all'])} → <b class=\"good\">{_pct(row['sa']['risk_all'])}</b></td>"
            f"<td>{_pct(row['naive']['compression'])} → <b>{_pct(row['sa']['compression'])}</b></td>"
            "</tr>"
        )
        for row in data["size_buckets"]
    )
    convergence_overall = _render_convergence_chart(
        data["convergence"]["overall"],
        "Aggregate convergence over 60 rollouts · current/default",
    )
    convergence_models = "".join(
        '<div class="chart">'
        + _render_convergence_chart(
            item["series"],
            f'{MODEL_LABEL.get(str(item["model"]), str(item["model"]))} · N={item["n"]}',
            width=760,
            height=300,
            compact=True,
        )
        + "</div>"
        for item in data["convergence"]["by_model"]
    )
    model_map = _rows_by_key(data["current_by_model"])
    model_cards = []
    for model in MODEL_ORDER:
        n_row = model_map.get(f"{model}|naive")
        s_row = model_map.get(f"{model}|sa-mcgs")
        if not n_row or not s_row:
            continue
        model_cards.append(
            '<div class="model-card">'
            '<div>'
            f'<div class="model-name">{MODEL_LABEL[model]}</div>'
            f'<div class="small">N={n_row["n"]} per method · Naive err={n_row["errors"]}, SA err={s_row["errors"]}</div>'
            '</div>'
            '<div class="metric-group">'
            f'{_split_bar("Root@3", n_row["root"], s_row["root"])}'
            f'{_split_bar("Risk-any", n_row["risk_any"], s_row["risk_any"])}'
            f'{_split_bar("Risk-all", n_row["risk_all"], s_row["risk_all"])}'
            f'{_split_bar("Compression", n_row["compression"], s_row["compression"])}'
            '</div></div>'
        )
    profile_bars = []
    for item in data["profile_tradeoff"]:
        label = MODEL_LABEL.get(str(item["model"]), str(item["model"]))
        current = item["current"]
        balanced = item["balanced"]
        profile_bars.append(
            f"<h3>{label}</h3>"
            f'{_bar("Current Risk-all", current["risk_all"], "sa-fill")}'
            f'{_bar("Balanced Risk-all", balanced["risk_all"], "purple-fill")}'
            f'{_bar("Current Compression", current["compression"], "blue-fill")}'
            f'{_bar("Balanced Compression", balanced["compression"], "yellow-fill")}'
        )
    domain_map = _rows_by_key(data["current_by_domain"])
    domain_bars = []
    for domain in DOMAIN_ORDER:
        n_row = domain_map.get(f"{domain}|naive")
        s_row = domain_map.get(f"{domain}|sa-mcgs")
        if not n_row or not s_row:
            continue
        domain_bars.append(
            f"<h3>{DOMAIN_LABEL[domain]}</h3>"
            f'{_bar("Naive Risk-all", n_row["risk_all"], "naive-fill")}'
            f'{_bar("SA Risk-all", s_row["risk_all"], "sa-fill")}'
            f'{_bar("SA Effective OC", s_row["effective_oc"], "blue-fill")}'
        )
    table_rows = []
    for row in data["current_by_model"]:
        model, _, method = str(row["key"]).partition("|")
        table_rows.append((model, "current", method, row))
    for row in data["balanced_sa_by_model"]:
        table_rows.append((str(row["key"]), "balanced", "sa-mcgs", row))
    table_html = "".join(
        (
            "<tr>"
            f"<td>{MODEL_LABEL.get(model, model)}</td>"
            f"<td>{profile}</td>"
            f"<td>{method}</td>"
            f"<td>{row['n']}</td>"
            f"<td class=\"{'bad' if row['errors'] else 'good'}\">{row['errors']}</td>"
            f"<td>{_rate_cell(row, 'root')}</td>"
            f"<td>{_rate_cell(row, 'risk_any')}</td>"
            f"<td>{_rate_cell(row, 'risk_all')}</td>"
            f"<td>{_pct(row['compression'])}</td>"
            f"<td>{_pct(row['effective_compression'])}</td>"
            f"<td>{_pct(row['effective_oc']) if method == 'sa-mcgs' else '-'}</td>"
            "</tr>"
        )
        for model, profile, method, row in table_rows
    )
    css = _html().split("<body>", 1)[0]
    return f"""{css}<body>
<main>
  <div class="hero">
    <div class="pill">Critical structural-conflict · 4 domains · 4 models · 80 SCC blocks</div>
    <h1>SA-MCGS Final Results</h1>
    <p class="claim">{claim}</p>
  </div>
  <div class="grid cols4">{kpis}</div>
  <section class="grid cols2">
    <div class="card">
      <h2>主结果：Current / Default</h2>
      <p>strict rate：模型报错或 JSON 解析失败都计入分母。</p>
      <div class="legend"><span class="naive">Naive</span><span class="sa">SA-MCGS</span></div>
      <div class="chart"><div class="bars">{overall_bars}</div></div>
    </div>
    <div class="card">
      <h2>错误分布</h2>
      <p>主要看 one-shot 是否在长 SCC / 长合同文本下失稳。</p>
      <div class="chart"><div class="bars">{error_bars}</div></div>
    </div>
  </section>
  <section class="card">
    <h2>主指标随 SCC 规模变化</h2>
    <p>按实际 SCC size 聚合 current/default 结果。折线展示 exact size，表格给短/中/长环分桶，避免单个长度样本量波动。</p>
    <div class="grid cols2">{size_charts}</div>
    <div class="table-wrap" style="margin-top:18px;">
      <table>
        <thead>
          <tr><th>SCC bucket</th><th>N / method</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Compression</th></tr>
        </thead>
        <tbody>{bucket_rows}</tbody>
      </table>
    </div>
  </section>
  <section class="card">
    <h2>SA-MCGS 收敛曲线</h2>
    <p>主图使用 current/default 口径。上升后平台期说明 rollout 逐步把风险端点和 OC 证据收进核心子图；Compression 下降表示子图为保留证据变大。</p>
    <div class="chart">{convergence_overall}</div>
    <div class="grid cols2" style="margin-top:18px;">{convergence_models}</div>
  </section>
  <section class="card">
    <h2>按模型展开</h2>
    <p>每个模型内部比较 Naive 和 SA-MCGS；这是最适合放进论文主表的视角。</p>
    <div class="matrix">{"".join(model_cards)}</div>
  </section>
  <section class="grid cols2">
    <div class="card">
      <h2>压缩强度消融</h2>
      <p>Balanced 会提高压缩率，但部分模型会牺牲 Risk-all。Current 更适合作为主结果。</p>
      <div class="chart"><div class="bars">{"".join(profile_bars)}</div></div>
    </div>
    <div class="card">
      <h2>压缩率 vs Risk-all</h2>
      <p>横轴是压缩率，纵轴是 Risk-all。右上角最好；紫点是 balanced，绿点是 current。</p>
      {_render_scatter(data["profile_tradeoff"])}
    </div>
  </section>
  <section class="card">
    <h2>按领域展开</h2>
    <p>CUAD 是 Naive 最容易崩的领域；BGB/SEC/Debian 更能看结构定位与压缩的稳定性。</p>
    <div class="chart"><div class="bars">{"".join(domain_bars)}</div></div>
  </section>
  <section class="card">
    <h2>核心数据表</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Model</th><th>Profile</th><th>Method</th><th>N</th><th>Err</th>
            <th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Compression</th><th>Eff. Comp.</th><th>Eff. OC</th>
          </tr>
        </thead>
        <tbody>{table_html}</tbody>
      </table>
    </div>
  </section>
  <div class="footer-space"></div>
</main>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global CACHED_PAYLOAD, CACHED_HTML, CACHED_API
        if CACHED_PAYLOAD is None:
            CACHED_PAYLOAD = _payload()
            CACHED_HTML = _render_html(CACHED_PAYLOAD).encode("utf-8")
            CACHED_API = json.dumps(CACHED_PAYLOAD, ensure_ascii=False).encode("utf-8")
        if self.path.startswith("/api"):
            payload = CACHED_API or b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        body = CACHED_HTML or b""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> None:
    global CACHED_PAYLOAD, CACHED_HTML, CACHED_API
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print("Preparing final result payload...", flush=True)
    CACHED_PAYLOAD = _payload()
    CACHED_HTML = _render_html(CACHED_PAYLOAD).encode("utf-8")
    CACHED_API = json.dumps(CACHED_PAYLOAD, ensure_ascii=False).encode("utf-8")
    server = ReusableThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Final results dashboard: http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

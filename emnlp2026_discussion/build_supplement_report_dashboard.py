#!/usr/bin/env python3
"""Build a static dashboard for EMNLP 2026 discussion supplemental experiments."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DISCUSSION = ROOT / "emnlp2026_discussion"
OUT_DIR = DISCUSSION / "supplement_report_dashboard"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fnum(value: Any) -> float | None:
    try:
        if value is None or value == "" or str(value).lower() == "nan":
            return None
        return float(value)
    except Exception:
        return None


def pct(value: Any, digits: int = 1) -> str:
    number = fnum(value)
    return "NA" if number is None else f"{number * 100:.{digits}f}%"


def num(value: Any, digits: int = 1) -> str:
    number = fnum(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def intish(value: Any) -> str:
    number = fnum(value)
    if number is None:
        return "NA"
    return f"{number:,.0f}"


def table(headers: list[str], rows: list[list[Any]], class_name: str = "") -> str:
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    cls = f' class="{class_name}"' if class_name else ""
    return f"<div class=\"table-wrap\"><table{cls}><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def load_data() -> dict[str, Any]:
    cost_rows = read_csv(
        DISCUSSION / "experiment_records/20260711_cost_and_stage1/summary_cost_table_merged.csv"
    )
    stage1_rows = read_csv(
        DISCUSSION / "experiment_records/20260711_cost_and_stage1/component_ablation_table_full80.csv"
    )
    stage1_bins = read_csv(
        DISCUSSION / "experiment_records/20260711_cost_and_stage1/component_ablation_by_scc_bin_compact.csv"
    )
    stage2_rows = read_csv(
        DISCUSSION / "experiment_records/20260711_stage2_dynamic_40case/component_ablation_table.csv"
    )
    lea_rows = read_csv(
        DISCUSSION / "experiment_records/20260712_lea_available160/matched_lea_vs_full_sa_mcgs_summary.csv"
    )
    lea_only = read_csv(
        DISCUSSION / "experiment_records/20260712_lea_available160/summary_lea_full_breakdown.csv"
    )

    cost_overall = [r for r in cost_rows if r["Scale"] == "Overall"]
    lea_summary_groups = [
        r
        for r in lea_rows
        if r["group"] in {"overall", "model=gpt-4o", "model=gemini-2.5-pro"}
    ]
    return {
        "cost_rows": cost_rows,
        "cost_overall": cost_overall,
        "stage1_rows": stage1_rows,
        "stage1_bins": stage1_bins,
        "stage2_rows": stage2_rows,
        "lea_rows": lea_rows,
        "lea_summary_groups": lea_summary_groups,
        "lea_only": lea_only,
    }


def build_tables(data: dict[str, Any]) -> dict[str, str]:
    cost_table = table(
        [
            "Method",
            "Cases",
            "Invalid",
            "Calls/case",
            "Input tok.",
            "Output tok.",
            "Total tok.",
            "Runtime",
            "Root@3",
            "Risk-any",
            "Risk-all",
            "Compression",
        ],
        [
            [
                html.escape(r["Method"]),
                r["Cases"],
                pct(r["Invalid rate"]),
                num(r["API calls / case"], 1),
                intish(r["Input tok. / case"]),
                intish(r["Output tok. / case"]),
                intish(r["Total tok. / case"]),
                f"{num(r['Runtime / case'], 1)}s",
                pct(r["Root@3"]),
                pct(r["Risk-any"]),
                pct(r["Risk-all"]),
                pct(r["Compression"]),
            ]
            for r in data["cost_overall"]
        ],
    )

    stage1_table = table(
        [
            "Variant",
            "N",
            "Root@3",
            "Risk-any",
            "Risk-all",
            "Compression",
            "Delta Risk-all",
            "Avg core",
        ],
        [
            [
                html.escape(r["Variant"]),
                r["N"],
                pct(r["Root@3"]),
                pct(r["Risk-any"]),
                pct(r["Risk-all"]),
                pct(r["Compression"]),
                pct(r["Delta Risk-all"]),
                num(r["Avg core size"], 1),
            ]
            for r in data["stage1_rows"]
        ],
    )

    stage2_table = table(
        [
            "Variant",
            "N",
            "Root@3",
            "Risk-any",
            "Risk-all",
            "Compression",
            "Delta Risk-all",
            "Avg core",
        ],
        [
            [
                html.escape(r["Variant"]),
                r["N"],
                pct(r["Root@3"]),
                pct(r["Risk-any"]),
                pct(r["Risk-all"]),
                pct(r["Compression"]),
                pct(r["Delta Risk-all"]),
                num(r["Avg core size"], 1),
            ]
            for r in data["stage2_rows"]
        ],
    )

    lea_overall = [r for r in data["lea_rows"] if r["group"] == "overall"][0]
    lea_table = table(
        [
            "Group",
            "N",
            "LEA Root@3",
            "SA Root@3",
            "Delta",
            "LEA Risk-all",
            "SA Risk-all",
            "Delta",
            "LEA calls",
            "SA calls",
        ],
        [
            [
                html.escape(r["group"]),
                r["N"],
                pct(r["LEA Root@3"]),
                pct(r["SA Root@3"]),
                pct(r["Delta Root@3"]),
                pct(r["LEA Risk-all"]),
                pct(r["SA Risk-all"]),
                pct(r["Delta Risk-all"]),
                num(r["LEA Calls"], 1),
                num(r["SA Calls"], 1),
            ]
            for r in data["lea_rows"]
            if r["group"]
            in {
                "overall",
                "model=gpt-4o",
                "model=gemini-2.5-pro",
                "scale=large>=21",
                "scale=medium13-20",
                "scale=small<=12",
            }
        ],
    )

    claim_table = table(
        ["Reviewer concern", "New evidence", "Careful claim"],
        [
            [
                "Cost accounting",
                "20-case low-concurrency audit with calls/tokens/runtime; LEA included in the same accounting.",
                "Report cost-performance tradeoff by case scale; SA-MCGS uses more calls, while LEA reduces calls substantially.",
            ],
            [
                "Component-level ablations",
                "Stage 1: 80 cases for search/memory modules. Stage 2: 40 dynamic cases for OC/core and final-core policies.",
                "Critical-pair ledger/revisit and dynamic core construction are the strongest supported modules; relation memory and pair closure should be framed cautiously.",
            ],
            [
                "Baseline fairness",
                "160 clean cases for GraphRAG-style LEA on gpt-4o and Gemini 2.5 Pro, matched against locked Full SA-MCGS.",
                "LEA is competitive, especially on Gemini; SA-MCGS still improves endpoint completeness overall, with non-uniform model-level behavior.",
            ],
        ],
    )

    return {
        "claim_table": claim_table,
        "cost_table": cost_table,
        "stage1_table": stage1_table,
        "stage2_table": stage2_table,
        "lea_table": lea_table,
        "lea_overall_note": (
            f"Matched 160-case overall: LEA Risk-all {pct(lea_overall['LEA Risk-all'])}, "
            f"SA-MCGS Risk-all {pct(lea_overall['SA Risk-all'])}, "
            f"delta {pct(lea_overall['Delta Risk-all'])}."
        ),
    }


def build_html(data: dict[str, Any], tables: dict[str, str]) -> str:
    payload = {
        "costOverall": [
            {
                "method": r["Method"].replace("Full-SCC Naive (single attempt)", "Naive")
                .replace("GraphRAG-style LEA", "LEA")
                .replace("SA-MCGS", "SA-MCGS"),
                "calls": fnum(r["API calls / case"]),
                "tokens": fnum(r["Total tok. / case"]),
                "runtime": fnum(r["Runtime / case"]),
                "root": fnum(r["Root@3"]),
                "any": fnum(r["Risk-any"]),
                "all": fnum(r["Risk-all"]),
                "invalid": fnum(r["Invalid rate"]),
            }
            for r in data["cost_overall"]
        ],
        "stage1": [
            {
                "variant": r["Variant"].replace("Full SA-MCGS (locked main)", "Full")
                .replace("No relation-first memory", "No relation memory")
                .replace("No critical-pair ledger/revisit", "No critical-pair")
                .replace("Random local-window selection", "Random window"),
                "riskAll": fnum(r["Risk-all"]),
                "deltaRiskAll": fnum(r["Delta Risk-all"]),
                "compression": fnum(r["Compression"]),
            }
            for r in data["stage1_rows"]
        ],
        "stage1Large": [
            {
                "variant": r["Variant"].replace("Full SA-MCGS (locked main)", "Full")
                .replace("No relation-first memory", "No relation memory")
                .replace("No critical-pair ledger/revisit", "No critical-pair")
                .replace("Random local-window selection", "Random window"),
                "bin": r["SCC bin"],
                "riskAll": fnum(r["Risk-all"]),
                "deltaRiskAll": fnum(r["Delta Risk-all"]),
            }
            for r in data["stage1_bins"]
            if r["SCC bin"] == "large (20-34)"
        ],
        "stage2": [
            {
                "variant": r["Variant"].replace("Full SA-MCGS (locked main)", "Full")
                .replace("No OC/core signal", "No OC/core")
                .replace("Monotone core", "Monotone")
                .replace("No pair closure in final core", "No pair closure"),
                "riskAll": fnum(r["Risk-all"]),
                "deltaRiskAll": fnum(r["Delta Risk-all"]),
                "compression": fnum(r["Compression"]),
                "core": fnum(r["Avg core size"]),
            }
            for r in data["stage2_rows"]
        ],
        "leaOverall": [
            {
                "metric": "Root@3",
                "lea": fnum(data["lea_rows"][0]["LEA Root@3"]),
                "sa": fnum(data["lea_rows"][0]["SA Root@3"]),
            },
            {
                "metric": "Risk-any",
                "lea": fnum(data["lea_rows"][0]["LEA Risk-any"]),
                "sa": fnum(data["lea_rows"][0]["SA Risk-any"]),
            },
            {
                "metric": "Risk-all",
                "lea": fnum(data["lea_rows"][0]["LEA Risk-all"]),
                "sa": fnum(data["lea_rows"][0]["SA Risk-all"]),
            },
        ],
        "leaModels": [
            {
                "model": r["group"].replace("model=", ""),
                "lea": fnum(r["LEA Risk-all"]),
                "sa": fnum(r["SA Risk-all"]),
            }
            for r in data["lea_rows"]
            if r["group"].startswith("model=")
        ],
        "leaCost": [
            {
                "method": "LEA",
                "calls": fnum(data["lea_rows"][0]["LEA Calls"]),
                "runtime": fnum(data["lea_rows"][0]["LEA Runtime"]),
            },
            {
                "method": "SA-MCGS",
                "calls": fnum(data["lea_rows"][0]["SA Calls"]),
                "runtime": fnum(data["lea_rows"][0]["SA Runtime"]),
            },
        ],
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="zh-Hans">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EMNLP 2026 Discussion Supplemental Report</title>
  <style>
    :root {{
      --bg: #f7f8f5;
      --paper: #ffffff;
      --ink: #17211b;
      --muted: #657267;
      --line: #d9dfd6;
      --teal: #23756d;
      --green: #5f8f56;
      --amber: #bf7f2f;
      --rose: #b25a5a;
      --blue: #506f9f;
      --soft-teal: rgba(35,117,109,.12);
      --soft-amber: rgba(191,127,47,.15);
      --soft-rose: rgba(178,90,90,.16);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 32px 24px 64px; }}
    header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 24px;
      align-items: end;
      padding: 8px 0 24px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0; font-size: 34px; line-height: 1.15; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 24px; line-height: 1.2; letter-spacing: 0; }}
    h3 {{ margin: 0 0 10px; font-size: 17px; letter-spacing: 0; }}
    p {{ margin: 0; }}
    .subhead {{ color: var(--muted); margin-top: 10px; max-width: 920px; }}
    .stamp {{ text-align: right; color: var(--muted); font-size: 14px; white-space: nowrap; }}
    section {{ padding: 28px 0; border-bottom: 1px solid var(--line); }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-top: 18px;
    }}
    .metric {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-height: 118px;
    }}
    .metric b {{ display: block; font-size: 28px; margin-top: 6px; }}
    .metric span {{ color: var(--muted); font-size: 14px; }}
    .two-col {{
      display: grid;
      grid-template-columns: minmax(0, .92fr) minmax(420px, 1.08fr);
      gap: 20px;
      align-items: start;
    }}
    .panel {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .table-wrap {{
      overflow-x: auto;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{ width: 100%; border-collapse: collapse; min-width: 820px; }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
      white-space: nowrap;
    }}
    th {{ color: var(--muted); font-weight: 700; background: rgba(0,0,0,.025); }}
    tr:last-child td {{ border-bottom: 0; }}
    .claim table {{ min-width: 940px; }}
    .claim td {{ white-space: normal; }}
    .note {{ color: var(--muted); font-size: 14px; margin: 10px 0 0; }}
    .chart-grid {{ display: grid; grid-template-columns: 1fr; gap: 14px; }}
    .chart {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-height: 280px;
    }}
    .chart.short {{ min-height: 230px; }}
    .chart-title {{ font-weight: 700; margin-bottom: 8px; }}
    svg {{ width: 100%; height: auto; display: block; }}
    .axis {{ stroke: var(--line); stroke-width: 1; }}
    .tick {{ fill: var(--muted); font-size: 12px; }}
    .label {{ fill: var(--ink); font-size: 12px; }}
    .value {{ fill: var(--ink); font-size: 12px; font-weight: 700; }}
    .legend {{ display: flex; gap: 14px; flex-wrap: wrap; color: var(--muted); font-size: 13px; margin-top: 8px; }}
    .swatch {{ width: 11px; height: 11px; border-radius: 2px; display: inline-block; margin-right: 6px; vertical-align: -1px; }}
    .callout {{
      border-left: 4px solid var(--teal);
      background: var(--soft-teal);
      padding: 12px 14px;
      border-radius: 6px;
      margin-top: 12px;
      color: var(--ink);
    }}
    .risk {{ color: var(--rose); font-weight: 700; }}
    .good {{ color: var(--teal); font-weight: 700; }}
    @media (max-width: 980px) {{
      main {{ padding: 24px 14px 48px; }}
      header, .two-col, .summary-grid {{ grid-template-columns: 1fr; }}
      .stamp {{ text-align: left; }}
      h1 {{ font-size: 28px; }}
      .chart {{ min-height: 240px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>EMNLP 2026 Discussion 补充实验报告</h1>
        <p class="subhead">三个补充方向已经形成可展示证据：推理成本核算、组件级消融、以及 GraphRAG-style Local Evidence Aggregation baseline。页面只使用冻结记录中的数据。</p>
      </div>
      <div class="stamp">Updated<br>2026-07-12</div>
    </header>

    <section>
      <h2>Reviewer-facing Summary</h2>
      <div class="summary-grid">
        <div class="metric"><span>Cost audit</span><b>20 cases</b><span>Naive / LEA / SA-MCGS with tokens, calls, runtime</span></div>
        <div class="metric"><span>Component ablation</span><b>80 + 40</b><span>Stage 1 search modules + Stage 2 dynamic core modules</span></div>
        <div class="metric"><span>Graph-aware baseline</span><b>160 cases</b><span>Clean LEA run on gpt-4o and Gemini, matched to locked SA-MCGS</span></div>
      </div>
      <div class="claim" style="margin-top:16px">{tables["claim_table"]}</div>
    </section>

    <section>
      <div class="two-col">
        <div>
          <h2>1. 推理成本与可靠性</h2>
          {tables["cost_table"]}
          <p class="note">Scope: low-concurrency 20-case audit. LEA is included in the same accounting table to support the baseline-fairness response.</p>
          <div class="callout">可以对 reviewer 说：我们会同时报告 performance 和 cost，包含 input/output tokens、API calls、runtime，并按 SCC scale 拆分。</div>
        </div>
        <div class="chart-grid">
          <div class="chart"><div class="chart-title">Performance by method</div><div id="costPerf"></div></div>
          <div class="chart short"><div class="chart-title">Cost profile by method</div><div id="costProfile"></div></div>
        </div>
      </div>
    </section>

    <section>
      <div class="two-col">
        <div>
          <h2>2. 组件级消融</h2>
          <h3>Stage 1: search / memory modules, 80 cases</h3>
          {tables["stage1_table"]}
          <h3 style="margin-top:18px">Stage 2: dynamic core modules, 40 cases</h3>
          {tables["stage2_table"]}
          <div class="callout">最强证据：critical-pair ledger/revisit 和 dynamic/replacement core。relation-first memory 接近 Full，pair closure 影响较小，应谨慎表述。</div>
        </div>
        <div class="chart-grid">
          <div class="chart"><div class="chart-title">Risk-all delta vs Full SA-MCGS</div><div id="ablationDelta"></div></div>
          <div class="chart"><div class="chart-title">Stage 2: compression and endpoint retention</div><div id="stage2Core"></div></div>
          <div class="chart short"><div class="chart-title">Large SCC: Stage 1 Risk-all</div><div id="stage1Large"></div></div>
        </div>
      </div>
    </section>

    <section>
      <div class="two-col">
        <div>
          <h2>3. Graph-aware Decomposed Baseline</h2>
          {tables["lea_table"]}
          <p class="note">{html.escape(tables["lea_overall_note"])}</p>
          <div class="callout">这张表非常适合回应 baseline fairness：LEA 很强，尤其 Gemini 上更强；SA-MCGS 的优势主要体现在 overall endpoint completeness / Risk-all，且 model-level non-uniformity 需要如实说明。</div>
        </div>
        <div class="chart-grid">
          <div class="chart"><div class="chart-title">Matched LEA vs Full SA-MCGS</div><div id="leaMatched"></div></div>
          <div class="chart short"><div class="chart-title">Risk-all by model</div><div id="leaModel"></div></div>
          <div class="chart short"><div class="chart-title">Calls/runtime tradeoff</div><div id="leaCost"></div></div>
        </div>
      </div>
    </section>
  </main>

  <script>
    const DATA = {payload_json};
    const colors = {{
      teal: getComputedStyle(document.documentElement).getPropertyValue('--teal').trim(),
      amber: getComputedStyle(document.documentElement).getPropertyValue('--amber').trim(),
      rose: getComputedStyle(document.documentElement).getPropertyValue('--rose').trim(),
      green: getComputedStyle(document.documentElement).getPropertyValue('--green').trim(),
      blue: getComputedStyle(document.documentElement).getPropertyValue('--blue').trim(),
      line: getComputedStyle(document.documentElement).getPropertyValue('--line').trim(),
      ink: getComputedStyle(document.documentElement).getPropertyValue('--ink').trim(),
      muted: getComputedStyle(document.documentElement).getPropertyValue('--muted').trim()
    }};

    function fmtPct(v) {{ return (v * 100).toFixed(1) + '%'; }}
    function fmtNum(v) {{ return v >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(1); }}

    function groupedBars(rootId, data, keys, labels, opts = {{}}) {{
      const root = document.getElementById(rootId);
      const width = 720, height = opts.height || 260;
      const margin = {{top: 18, right: 20, bottom: 52, left: 84}};
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const max = opts.max ?? Math.max(...data.flatMap(d => keys.map(k => d[k] || 0)), 1);
      const groupW = plotW / data.length;
      const barW = Math.min(28, groupW / (keys.length + 1.4));
      const seriesColors = opts.colors || [colors.teal, colors.amber, colors.blue];
      let svg = `<svg viewBox="0 0 ${{width}} ${{height}}" role="img" aria-label="${{opts.label || 'bar chart'}}">`;
      for (let i = 0; i <= 4; i++) {{
        const y = margin.top + plotH - (plotH * i / 4);
        svg += `<line class="axis" x1="${{margin.left}}" y1="${{y}}" x2="${{width - margin.right}}" y2="${{y}}"></line>`;
        svg += `<text class="tick" x="${{margin.left - 10}}" y="${{y + 4}}" text-anchor="end">${{opts.percent ? fmtPct(max * i / 4) : fmtNum(max * i / 4)}}</text>`;
      }}
      data.forEach((d, i) => {{
        const gx = margin.left + i * groupW + groupW / 2;
        keys.forEach((k, j) => {{
          const val = d[k] || 0;
          const h = plotH * val / max;
          const x = gx - (keys.length * barW + (keys.length - 1) * 6) / 2 + j * (barW + 6);
          const y = margin.top + plotH - h;
          svg += `<rect x="${{x}}" y="${{y}}" width="${{barW}}" height="${{h}}" rx="3" fill="${{seriesColors[j]}}"></rect>`;
          svg += `<text class="value" x="${{x + barW / 2}}" y="${{Math.max(12, y - 5)}}" text-anchor="middle">${{opts.percent ? Math.round(val * 100) : Math.round(val)}}</text>`;
        }});
        svg += `<text class="tick" x="${{gx}}" y="${{height - 22}}" text-anchor="middle">${{d.method || d.metric || d.model || d.variant}}</text>`;
      }});
      svg += `</svg><div class="legend">`;
      labels.forEach((label, i) => {{
        svg += `<span><i class="swatch" style="background:${{seriesColors[i]}}"></i>${{label}}</span>`;
      }});
      svg += `</div>`;
      root.innerHTML = svg;
    }}

    function horizontalDelta(rootId, rows, opts = {{}}) {{
      const root = document.getElementById(rootId);
      const width = 720, rowH = 34, height = 60 + rows.length * rowH;
      const margin = {{top: 20, right: 86, bottom: 28, left: 210}};
      const plotW = width - margin.left - margin.right;
      const vals = rows.map(r => r.deltaRiskAll || 0);
      const min = Math.min(-0.45, ...vals), max = Math.max(0.12, ...vals);
      const zeroX = margin.left + ((0 - min) / (max - min)) * plotW;
      let svg = `<svg viewBox="0 0 ${{width}} ${{height}}" role="img" aria-label="Risk-all delta chart">`;
      svg += `<line class="axis" x1="${{zeroX}}" y1="${{margin.top}}" x2="${{zeroX}}" y2="${{height - margin.bottom}}"></line>`;
      rows.forEach((r, i) => {{
        const y = margin.top + i * rowH + 8;
        const val = r.deltaRiskAll || 0;
        const x = margin.left + ((Math.min(0, val) - min) / (max - min)) * plotW;
        const w = Math.abs(val) / (max - min) * plotW;
        const fill = val < -0.08 ? colors.rose : val < 0 ? colors.amber : colors.teal;
        svg += `<text class="label" x="${{margin.left - 10}}" y="${{y + 13}}" text-anchor="end">${{r.group ? r.group + ': ' : ''}}${{r.variant}}</text>`;
        svg += `<rect x="${{val < 0 ? x : zeroX}}" y="${{y}}" width="${{Math.max(2, w)}}" height="18" rx="3" fill="${{fill}}"></rect>`;
        svg += `<text class="value" x="${{val < 0 ? x - 8 : zeroX + w + 8}}" y="${{y + 13}}" text-anchor="${{val < 0 ? 'end' : 'start'}}">${{fmtPct(val)}}</text>`;
      }});
      svg += `</svg>`;
      root.innerHTML = svg;
    }}

    function singleBars(rootId, rows, key, opts = {{}}) {{
      const root = document.getElementById(rootId);
      const width = 720, rowH = 38, height = 54 + rows.length * rowH;
      const margin = {{top: 16, right: 84, bottom: 24, left: opts.left || 190}};
      const plotW = width - margin.left - margin.right;
      const max = opts.max ?? Math.max(...rows.map(r => r[key] || 0), 1);
      let svg = `<svg viewBox="0 0 ${{width}} ${{height}}" role="img" aria-label="${{opts.label || 'bar chart'}}">`;
      rows.forEach((r, i) => {{
        const y = margin.top + i * rowH + 8;
        const val = r[key] || 0;
        const w = plotW * val / max;
        svg += `<text class="label" x="${{margin.left - 10}}" y="${{y + 13}}" text-anchor="end">${{r.variant || r.method || r.model}}</text>`;
        svg += `<rect x="${{margin.left}}" y="${{y}}" width="${{w}}" height="18" rx="3" fill="${{opts.color || colors.teal}}"></rect>`;
        svg += `<text class="value" x="${{margin.left + w + 8}}" y="${{y + 13}}">${{opts.percent ? fmtPct(val) : fmtNum(val)}}</text>`;
      }});
      svg += `</svg>`;
      root.innerHTML = svg;
    }}

    function dualBars(rootId, rows, keys, opts = {{}}) {{
      const expanded = rows.map(r => ({{...r, method: r.metric || r.model || r.method}}));
      groupedBars(rootId, expanded, keys, opts.labels, {{...opts, colors: opts.colors || [colors.amber, colors.teal]}});
    }}

    groupedBars('costPerf', DATA.costOverall, ['root', 'any', 'all'], ['Root@3', 'Risk-any', 'Risk-all'], {{percent: true, max: 1, height: 260, colors: [colors.blue, colors.green, colors.teal]}});
    groupedBars('costProfile', DATA.costOverall, ['calls'], ['API calls / case'], {{height: 210, colors: [colors.amber]}});
    singleBars('stage1Large', DATA.stage1Large, 'riskAll', {{percent: true, max: 1, color: colors.teal, left: 180}});
    horizontalDelta('ablationDelta', [
      ...DATA.stage1.filter(r => r.variant !== 'Full').map(r => ({{...r, group: 'S1'}})),
      ...DATA.stage2.filter(r => r.variant !== 'Full').map(r => ({{...r, group: 'S2'}}))
    ]);
    dualBars('stage2Core', DATA.stage2, ['riskAll', 'compression'], {{labels: ['Risk-all', 'Compression'], percent: true, max: 1, height: 260, colors: [colors.teal, colors.rose]}});
    dualBars('leaMatched', DATA.leaOverall, ['lea', 'sa'], {{labels: ['LEA', 'SA-MCGS'], percent: true, max: 1, height: 250}});
    dualBars('leaModel', DATA.leaModels, ['lea', 'sa'], {{labels: ['LEA', 'SA-MCGS'], percent: true, max: 1, height: 220}});
    groupedBars('leaCost', DATA.leaCost, ['calls'], ['Calls / case'], {{height: 210, colors: [colors.amber]}});
  </script>
</body>
</html>
"""


def main() -> None:
    data = load_data()
    tables = build_tables(data)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(build_html(data, tables), encoding="utf-8")
    (OUT_DIR / "data_snapshot.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()

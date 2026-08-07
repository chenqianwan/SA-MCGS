#!/usr/bin/env python3
"""Component ablation runner for the EMNLP discussion.

This runner is intentionally scoped:
- Full SA-MCGS rows are copied from the locked main experiment files.
- Only LLM-dependent ablations are re-run here.
- Each case/variant writes an independent JSON file, so interrupted runs resume.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import csv
import json
import math
import os
import random
import sys
import time
import traceback
import types
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "cross_domain"))

from emnlp2026_discussion import run_cost_audit_clean as cost
from experiments.cross_domain import run_cross_domain_battle as battle
from src.modules.alphago_mcgs import AlphaGoMCGS


DISCUSSION_DIR = REPO_ROOT / "emnlp2026_discussion"
DEFAULT_CASE_PLAN = (
    DISCUSSION_DIR
    / "cost_audit_runs"
    / "clean_gpt4o_b50_20260711_013007"
    / "case_plan.csv"
)
DEFAULT_RUNS_DIR = DISCUSSION_DIR / "component_ablation_runs"

VARIANT_LABELS = {
    "full-sa-mcgs-locked": "Full SA-MCGS (locked main)",
    "no-relation-first-memory": "No relation-first memory",
    "no-critical-pair-ledger-revisit": "No critical-pair ledger/revisit",
    "random-local-window-selection": "Random local-window selection",
    "no-oc-core-signal": "No OC/core signal",
    "monotone-core": "Monotone core",
    "no-pair-closure-final-core": "No pair closure in final core",
}

LLM_VARIANTS = [
    "no-relation-first-memory",
    "no-critical-pair-ledger-revisit",
    "random-local-window-selection",
]

STAGE2_LLM_VARIANTS = [
    "no-oc-core-signal",
    "monotone-core",
    "no-pair-closure-final-core",
]

ALL_LLM_VARIANTS = [*LLM_VARIANTS, *STAGE2_LLM_VARIANTS]


def mean_numeric(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return sum(nums) / len(nums) if nums else None


def mean_bool(values: list[Any]) -> float | None:
    vals = [v for v in values if isinstance(v, bool)]
    return sum(1 for v in vals if v) / len(vals) if vals else None


def fmt_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def write_dashboard(output_dir: Path) -> None:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Component Ablation Progress</title>
  <style>
    :root {
      --bg: #f7f8f5;
      --panel: #ffffff;
      --ink: #17201a;
      --muted: #667064;
      --line: #d9ded5;
      --accent: #216869;
      --accent-soft: #dcebea;
      --warn: #a15c14;
      --bad: #a43832;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main { width: min(1180px, calc(100vw - 32px)); margin: 28px auto 48px; }
    header {
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-end;
      margin-bottom: 22px;
    }
    h1 { margin: 0 0 4px; font-size: 24px; line-height: 1.2; letter-spacing: 0; }
    h2 { font-size: 16px; margin: 0 0 10px; letter-spacing: 0; }
    section { margin-top: 22px; }
    .subtle { color: var(--muted); }
    .stamp { text-align: right; min-width: 220px; }
    .progress-wrap {
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 16px;
      border-radius: 8px;
      margin-bottom: 18px;
    }
    .progress-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: center;
      margin-bottom: 12px;
    }
    .bar {
      height: 14px;
      border-radius: 999px;
      background: #e6e9e2;
      overflow: hidden;
      border: 1px solid var(--line);
    }
    .bar > div {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent), #4d8f6d);
      transition: width 240ms ease;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 10px;
      margin: 18px 0;
    }
    .stat {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 12px 14px;
      min-height: 76px;
    }
    .stat .label { color: var(--muted); font-size: 12px; margin-bottom: 6px; }
    .stat .value { font-size: 24px; font-weight: 700; letter-spacing: 0; }
    table {
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    th, td {
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }
    th { font-size: 12px; color: var(--muted); background: #fbfcf8; position: sticky; top: 0; }
    tr:last-child td { border-bottom: 0; }
    .table-scroll { overflow: auto; border-radius: 8px; max-height: 560px; }
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 650;
      font-size: 12px;
    }
    .badge.warn { background: #f3e6d6; color: var(--warn); }
    .badge.bad { background: #f1dddc; color: var(--bad); }
    .active-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 10px;
    }
    .active-item {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 11px 12px;
    }
    .active-item strong { display: block; margin-bottom: 4px; }
    @media (max-width: 760px) {
      header { display: block; }
      .stamp { text-align: left; margin-top: 10px; }
      .stats { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      th, td { white-space: normal; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Component Ablation Progress</h1>
        <div class="subtle" id="runMeta">Loading run metadata...</div>
      </div>
      <div class="stamp">
        <div class="subtle">Last refresh</div>
        <div id="lastRefresh">-</div>
      </div>
    </header>
    <div class="progress-wrap">
      <div class="progress-row">
        <div>
          <strong id="progressText">0 / 0 completed</strong>
          <div class="subtle" id="statusText">Waiting for status.json</div>
        </div>
        <span class="badge" id="stateBadge">starting</span>
      </div>
      <div class="bar"><div id="progressBar"></div></div>
    </div>
    <div class="stats">
      <div class="stat"><div class="label">Completed</div><div class="value" id="completed">0</div></div>
      <div class="stat"><div class="label">Remaining</div><div class="value" id="remaining">0</div></div>
      <div class="stat"><div class="label">Failed</div><div class="value" id="failed">0</div></div>
      <div class="stat"><div class="label">Cases</div><div class="value" id="cases">0</div></div>
      <div class="stat"><div class="label">Variants</div><div class="value" id="variants">0</div></div>
    </div>
    <section>
      <h2>Active Tasks</h2>
      <div class="active-list" id="activeList"><div class="subtle">No active task reported yet.</div></div>
    </section>
    <section>
      <h2>Aggregate Table</h2>
      <div class="table-scroll" id="aggregateTable"><div class="subtle">Waiting for component_ablation_table.csv</div></div>
    </section>
    <section>
      <h2>Completed Case Details</h2>
      <div class="table-scroll" id="caseTable"><div class="subtle">Waiting for summary_component_cases.csv</div></div>
    </section>
  </main>
  <script>
    const refreshMs = 10000;
    const fmt = value => value === undefined || value === null || value === '' ? '-' : value;
    function parseCsv(text) {
      const rows = [];
      let row = [], cell = '', quoted = false;
      for (let i = 0; i < text.length; i++) {
        const ch = text[i], next = text[i + 1];
        if (quoted && ch === '"' && next === '"') { cell += '"'; i++; continue; }
        if (ch === '"') { quoted = !quoted; continue; }
        if (!quoted && ch === ',') { row.push(cell); cell = ''; continue; }
        if (!quoted && (ch === '\\n' || ch === '\\r')) {
          if (ch === '\\r' && next === '\\n') i++;
          row.push(cell); cell = '';
          if (row.some(x => x.length)) rows.push(row);
          row = [];
          continue;
        }
        cell += ch;
      }
      if (cell.length || row.length) { row.push(cell); rows.push(row); }
      return rows;
    }
    async function fetchJson(path) {
      const res = await fetch(path + '?t=' + Date.now());
      if (!res.ok) throw new Error(path + ' missing');
      return await res.json();
    }
    async function fetchText(path) {
      const res = await fetch(path + '?t=' + Date.now());
      if (!res.ok) throw new Error(path + ' missing');
      return await res.text();
    }
    function renderTable(targetId, csvText, columns = null) {
      const parsed = parseCsv(csvText).filter(row => row.length);
      const target = document.getElementById(targetId);
      if (parsed.length < 2) {
        target.innerHTML = '<div class="subtle">No rows yet.</div>';
        return;
      }
      const headers = parsed[0];
      const indices = columns ? columns.map(name => headers.indexOf(name)).filter(i => i >= 0) : headers.map((_, i) => i);
      const shownHeaders = indices.map(i => headers[i]);
      const body = parsed.slice(1);
      target.innerHTML = '<table><thead><tr>' +
        shownHeaders.map(h => '<th>' + h + '</th>').join('') +
        '</tr></thead><tbody>' +
        body.map(row => '<tr>' + indices.map(i => '<td>' + fmt(row[i]) + '</td>').join('') + '</tr>').join('') +
        '</tbody></table>';
    }
    function renderActive(active) {
      const target = document.getElementById('activeList');
      if (!active || !active.length) {
        target.innerHTML = '<div class="subtle">No active task reported.</div>';
        return;
      }
      target.innerHTML = active.map(item => `
        <div class="active-item">
          <strong>${fmt(item.case_order)}. ${fmt(item.case_id)}</strong>
          <div>${fmt(item.variant)}</div>
          <div class="subtle">${fmt(item.domain)} &middot; SCC ${fmt(item.scc_size)} &middot; started ${fmt(item.started_at)}</div>
        </div>
      `).join('');
    }
    async function refresh() {
      try {
        const status = await fetchJson('status.json');
        const total = Number(status.total_case_variants || 0);
        const completed = Number(status.completed_case_variants || 0);
        const failed = Number(status.failed_case_variants || 0);
        const remaining = Number(status.remaining_case_variants || 0);
        const pct = total ? Math.round(completed * 1000 / total) / 10 : 0;
        document.getElementById('runMeta').textContent = `${status.stage || 'stage'} - ${status.run_id || ''}`;
        document.getElementById('lastRefresh').textContent = new Date().toLocaleTimeString();
        document.getElementById('progressText').textContent = `${completed} / ${total} completed (${pct}%)`;
        document.getElementById('statusText').textContent = `updated ${status.updated_at || '-'} - ${remaining} remaining`;
        document.getElementById('progressBar').style.width = pct + '%';
        document.getElementById('completed').textContent = completed;
        document.getElementById('remaining').textContent = remaining;
        document.getElementById('failed').textContent = failed;
        document.getElementById('cases').textContent = status.total_cases || 0;
        document.getElementById('variants').textContent = (status.variants || []).length;
        const badge = document.getElementById('stateBadge');
        badge.textContent = failed ? 'check failures' : (remaining ? 'running' : 'complete');
        badge.className = 'badge' + (failed ? ' bad' : '');
        renderActive(status.active || (status.current ? [status.current] : []));
      } catch (err) {
        document.getElementById('statusText').textContent = err.message;
        document.getElementById('stateBadge').textContent = 'waiting';
        document.getElementById('stateBadge').className = 'badge warn';
      }
      try { renderTable('aggregateTable', await fetchText('component_ablation_table.csv')); } catch (err) {}
      try {
        renderTable('caseTable', await fetchText('summary_component_cases.csv'), [
          'case_order', 'variant', 'domain', 'scc_size', 'invalid', 'root_at_3',
          'risk_any', 'risk_all', 'compression', 'core_size', 'llm_calls', 'runtime_sec'
        ]);
      } catch (err) {}
    }
    refresh();
    setInterval(refresh, refreshMs);
  </script>
</body>
</html>
"""
    (output_dir / "index.html").write_text(html, encoding="utf-8")


def build_case_plan(args: argparse.Namespace, output_dir: Path) -> list[dict[str, Any]]:
    plan_path = output_dir / "case_plan.json"
    if plan_path.exists() and not args.rebuild_plan:
        return json.loads(plan_path.read_text(encoding="utf-8"))

    rows = list(csv.DictReader(args.case_plan.open(encoding="utf-8")))
    wanted = set(args.case_orders)
    selected = [
        {
            "case_order": int(row["case_order"]),
            "case_id": row["case_id"],
            "model": row["model"],
            "domain": row["domain"],
            "scc_id": row["scc_id"],
            "scc_size": int(row["scc_size"]),
            "template": row["template"],
            "source_result_file": row.get("source_result_file"),
            "old_llm_calls": int(float(row.get("old_llm_calls") or 0)),
            "old_time_sec": float(row.get("old_time_sec") or 0.0),
        }
        for row in rows
        if int(row["case_order"]) in wanted and row.get("model") == args.model
    ]
    selected.sort(key=lambda row: row["case_order"])
    if len(selected) != len(wanted):
        found = {row["case_order"] for row in selected}
        raise RuntimeError(f"Missing case orders from plan: {sorted(wanted - found)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    cost.atomic_write_json(plan_path, selected)
    with (output_dir / "case_plan.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(selected[0].keys()))
        writer.writeheader()
        writer.writerows(selected)
    return selected


def make_mcgs_config(args: argparse.Namespace, variant: str) -> dict[str, Any]:
    cfg = copy.deepcopy(battle.MCGS_DEFAULT)
    mcgs = cfg["alphago_mcgs"]
    mcgs["budget"] = args.budget
    mcgs["window_size"] = args.window_size
    mcgs["concurrency"] = args.internal_concurrency
    mcgs["trace"] = True
    evidence = mcgs.setdefault("evidence", {})
    evidence["compression_profile"] = args.compression_profile
    evidence.update(battle.MCGS_COMPRESSION_PROFILES.get(args.compression_profile, {}))

    if variant == "no-relation-first-memory":
        evidence["relation_first"] = False
        evidence["relation_prior_weight"] = 0.0
        evidence["probe_fraction"] = 0.0
        mcgs["relation_first_evidence"] = False
        mcgs["relation_prior_weight"] = 0.0
        mcgs["relation_probe_fraction"] = 0.0
    elif variant == "no-critical-pair-ledger-revisit":
        evidence["critical_pair_ledger"] = False
        evidence["critical_pair_revisit_fraction"] = 0.0
        mcgs["critical_pair_ledger"] = False
        mcgs["critical_pair_revisit_fraction"] = 0.0
    elif variant == "random-local-window-selection":
        evidence["relation_first"] = True
    elif variant in STAGE2_LLM_VARIANTS:
        pass
    else:
        raise ValueError(f"Unknown LLM variant: {variant}")
    return cfg


def make_llm(
    args: argparse.Namespace,
    output_dir: Path,
    case: dict[str, Any],
    variant: str,
) -> cost.LoggingOpenAIClient:
    model_id = cost.MODEL_IDS.get(args.model, args.model)
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
            "method": "sa-mcgs",
            "ablation_variant": variant,
            "model": args.model,
            "case_concurrency": args.case_concurrency,
            "internal_concurrency": args.internal_concurrency,
        },
    )


def patch_random_window_selection(mcgs: AlphaGoMCGS, seed: int) -> None:
    rng = random.Random(seed)

    def random_select_and_expand(self: AlphaGoMCGS, iteration: int) -> list[str]:
        scc_ids = list(self._scc_ids)
        if not scc_ids:
            return []
        target_size = min(self.window_size, len(scc_ids))
        seed_node = rng.choice(scc_ids)
        window = [seed_node]
        seen = {seed_node}

        while len(window) < target_size:
            frontier = []
            for node in window:
                for neighbor in self._adjacency.get(node, []):
                    if neighbor not in seen:
                        frontier.append(neighbor)
                for neighbor in self._reverse_adj.get(node, []):
                    if neighbor not in seen:
                        frontier.append(neighbor)
            candidates = list(dict.fromkeys(frontier))
            if not candidates:
                candidates = [cid for cid in scc_ids if cid not in seen]
            if not candidates:
                break
            new_node = rng.choice(candidates)
            window.append(new_node)
            seen.add(new_node)

        meta = {
            "mode": "random_local_window",
            "seed": seed_node,
            "random_seed": seed,
        }
        self._last_selection_meta = meta
        self._selection_events.append(
            {"iteration": iteration + 1, "window": list(window), **meta}
        )
        return window

    mcgs._select_and_expand = types.MethodType(random_select_and_expand, mcgs)


def patch_no_oc_signal(mcgs: AlphaGoMCGS) -> None:
    def no_update_oc(self: AlphaGoMCGS, iteration: int) -> None:
        return None

    mcgs._update_oc = types.MethodType(no_update_oc, mcgs)


def patch_dynamic_core_selection(mcgs: AlphaGoMCGS, variant: str) -> None:
    monotone = variant == "monotone-core"
    no_pair_closure = variant == "no-pair-closure-final-core"

    def select_core(
        self: AlphaGoMCGS,
        context_selected: set[str],
        evidence_scores: dict[str, dict[str, Any]],
        conflict_probability_matrix: list[dict[str, Any]],
        cap: int,
        index: dict[str, int],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        if not context_selected:
            return [], []

        pair_endpoint_scores: dict[str, float] = defaultdict(float)
        pair_endpoint_counts: dict[str, int] = defaultdict(int)
        strong_edges: list[dict[str, Any]] = []
        protected_edge_candidates: list[dict[str, Any]] = []
        protected_edges: list[dict[str, Any]] = []
        protected_nodes: set[str] = set()

        for edge in conflict_probability_matrix:
            source = edge.get("source")
            target = edge.get("target")
            if source not in index or target not in index:
                continue
            pair_score = float(edge.get("pair_score", 0.0))
            semantic_strength = float(edge.get("semantic_strength", 0.0))
            explicit_count = int(edge.get("explicit_count", 0))
            critical_score = float(edge.get("critical_pair_score", 0.0))
            critical_state = str(edge.get("critical_state", ""))
            critical_support = int(edge.get("critical_support_count", 0))
            is_protected_critical = (
                critical_state == "locked"
                or (
                    critical_score >= self.critical_pair_core_min_score
                    and critical_support >= self.critical_pair_lock_support
                )
            )
            is_evidence_edge = (
                pair_score >= self.evidence_pair_memory_min_score
                or semantic_strength >= 0.65
                or explicit_count > 0
                or is_protected_critical
            )
            if not is_evidence_edge:
                continue
            strong_edges.append(edge)
            if is_protected_critical:
                protected_edge_candidates.append(edge)
            for cid in (source, target):
                pair_endpoint_scores[cid] = max(pair_endpoint_scores[cid], pair_score)
                pair_endpoint_counts[cid] += 1

        if protected_edge_candidates and not monotone:
            protected_edge_candidates.sort(
                key=lambda edge: (
                    -float(edge.get("critical_pair_score", 0.0)),
                    -float(edge.get("severity_strength", 0.0)),
                    -float(edge.get("same_path_strength", 0.0)),
                    -float(edge.get("no_fallback_strength", 0.0)),
                    -int(edge.get("critical_support_count", 0)),
                    -int(edge.get("critical_revisit_count", 0)),
                    str(edge.get("source")),
                    str(edge.get("target")),
                )
            )
            max_protected_edges = len(protected_edge_candidates)
            if self.critical_pair_core_max_edge_ratio is not None:
                max_protected_edges = min(
                    max_protected_edges,
                    max(1, math.ceil(cap * self.critical_pair_core_max_edge_ratio)),
                )
            if self.critical_pair_core_max_edges > 0:
                max_protected_edges = min(
                    max_protected_edges,
                    self.critical_pair_core_max_edges,
                )
            protected_edges = protected_edge_candidates[:max_protected_edges]
            for edge in protected_edges:
                protected_nodes.update({str(edge.get("source")), str(edge.get("target"))})

        priority_rows: list[dict[str, Any]] = []
        for cid in context_selected:
            info = evidence_scores.get(cid, {})
            score = float(info.get("score", 0.0))
            pair_score = float(pair_endpoint_scores.get(cid, 0.0))
            oc_bonus = 0.16 if cid in self._detected_clauses else 0.0
            priority = score + 0.24 * pair_score + oc_bonus
            if priority <= 0:
                continue
            priority_rows.append({
                "clause_id": cid,
                "priority": priority,
                "evidence_score": score,
                "pair_score": pair_score,
                "pair_endpoint_count": pair_endpoint_counts.get(cid, 0),
                "support_count": int(info.get("support_count", 0)),
                "oc": cid in self._detected_clauses,
            })

        priority_rows.sort(
            key=lambda row: (
                -row["priority"],
                -row["support_count"],
                -row["pair_endpoint_count"],
                index[row["clause_id"]],
            )
        )
        if not priority_rows:
            fallback = sorted(context_selected, key=lambda cid: index.get(cid, len(index)))[:1]
            return fallback, []

        top_priority = max(priority_rows[0]["priority"], 1e-9)
        core_min_nodes = min(cap, max(1, self.evidence_core_min_nodes))
        selected: set[str] = set()
        stop_reason = "exhausted_candidates"
        prev_priority = priority_rows[0]["priority"]

        if not monotone:
            if protected_edges:
                protected_edges.sort(
                    key=lambda edge: (
                        -float(edge.get("critical_pair_score", 0.0)),
                        -float(edge.get("semantic_strength", 0.0)),
                        -int(edge.get("critical_support_count", 0)),
                        str(edge.get("source")),
                        str(edge.get("target")),
                    )
                )
                for edge in protected_edges:
                    endpoints = [
                        cid for cid in (edge.get("source"), edge.get("target"))
                        if isinstance(cid, str) and cid in context_selected
                    ]
                    if len(endpoints) < 2:
                        continue
                    if len(selected.union(endpoints)) > cap:
                        continue
                    selected.update(endpoints)

            if strong_edges:
                top_pair_score = max(float(edge.get("pair_score", 0.0)) for edge in strong_edges)
                relation_seed_node_cap = min(cap, core_min_nodes)
                relation_seed_min_score = max(
                    self.evidence_pair_memory_min_score,
                    top_pair_score * 0.90,
                )
                for edge in strong_edges:
                    if len(selected) >= relation_seed_node_cap:
                        break
                    pair_score = float(edge.get("pair_score", 0.0))
                    semantic_strength = float(edge.get("semantic_strength", 0.0))
                    if pair_score < relation_seed_min_score and semantic_strength < 0.9:
                        continue
                    endpoints = [
                        cid for cid in (edge.get("source"), edge.get("target"))
                        if isinstance(cid, str) and cid in context_selected
                    ]
                    if len(endpoints) < 2:
                        continue
                    if len(selected.union(endpoints)) > relation_seed_node_cap:
                        continue
                    selected.update(endpoints)

        for row_index, row in enumerate(priority_rows):
            if len(selected) >= cap:
                stop_reason = "hit_cap"
                break

            cid = row["clause_id"]
            priority = float(row["priority"])
            relative = priority / top_priority
            gap = max(0.0, (prev_priority - priority) / top_priority)
            if cid in selected:
                priority_rows[row_index]["selected"] = True
                priority_rows[row_index]["relative_priority"] = relative
                prev_priority = priority
                continue

            must_keep = bool(row["oc"])
            if not monotone and cid in protected_nodes:
                must_keep = True

            if len(selected) >= core_min_nodes and not must_keep:
                if priority < self.evidence_core_min_score:
                    stop_reason = "below_absolute_score"
                    break
                if gap >= self.evidence_core_stop_gap:
                    stop_reason = "score_gap"
                    break
                if relative < self.evidence_core_tail_relative_score:
                    stop_reason = "below_tail_relative_score"
                    break
                if relative < self.evidence_core_min_relative_score:
                    stop_reason = "below_relative_score"
                    break

            selected.add(cid)
            priority_rows[row_index]["selected"] = True
            priority_rows[row_index]["relative_priority"] = relative
            prev_priority = priority

        if not monotone and not no_pair_closure:
            closure_top_pair_score = max(
                [float(edge.get("pair_score", 0.0)) for edge in strong_edges] or [0.0]
            )
            for edge in strong_edges:
                if len(selected) >= cap:
                    break
                source = edge["source"]
                target = edge["target"]
                if source not in context_selected or target not in context_selected:
                    continue
                if (source in selected) == (target in selected):
                    continue
                counterpart = target if source in selected else source
                pair_score = float(edge.get("pair_score", 0.0))
                semantic_strength = float(edge.get("semantic_strength", 0.0))
                counterpart_priority = next(
                    (
                        float(row["priority"])
                        for row in priority_rows
                        if row["clause_id"] == counterpart
                    ),
                    0.0,
                )
                if (
                    pair_score >= max(
                        self.evidence_pair_closure_min_score,
                        closure_top_pair_score * 0.90,
                    )
                    and (
                        edge.get("critical_state") == "locked"
                        or float(edge.get("critical_pair_score", 0.0)) >= self.critical_pair_core_min_score
                        or semantic_strength >= 0.9
                        or counterpart_priority / top_priority >= 0.35
                    )
                ):
                    selected.add(counterpart)

        ordered_core = [cid for cid in self._scc_ids if cid in selected]
        for row in priority_rows:
            row.setdefault("selected", row["clause_id"] in selected)
            row.setdefault("relative_priority", row["priority"] / top_priority)
        priority_rows.insert(0, {
            "policy": f"dynamic_{variant}",
            "stop_reason": stop_reason,
            "cap": cap,
            "core_size": len(ordered_core),
            "context_size": len(context_selected),
            "hit_cap": len(ordered_core) >= cap,
            "min_relative_score": self.evidence_core_min_relative_score,
            "tail_relative_score": self.evidence_core_tail_relative_score,
            "stop_gap": self.evidence_core_stop_gap,
            "monotone": monotone,
            "pair_closure_enabled": not no_pair_closure and not monotone,
            "protected_critical_nodes": [
                cid for cid in self._scc_ids if cid in protected_nodes
            ],
        })
        return ordered_core, priority_rows

    mcgs._select_dynamic_core_subgraph = types.MethodType(select_core, mcgs)


async def run_sa_mcgs_variant(
    llm: cost.LoggingOpenAIClient,
    args: argparse.Namespace,
    case: dict[str, Any],
    graph: Any,
    scc: Any,
    injected_id: str,
    injection_metadata: dict[str, Any],
    variant: str,
) -> dict[str, Any]:
    started = time.time()
    cfg = make_mcgs_config(args, variant)
    prompt_fn = battle.DOMAIN_MCGS_PROMPTS[case["domain"]]
    mcgs = AlphaGoMCGS(llm_client=llm, config=cfg)
    mcgs._build_focused_prompt = lambda window, _self=mcgs: prompt_fn(_self, window)
    if variant == "random-local-window-selection":
        patch_random_window_selection(mcgs, args.random_seed + case["case_order"] * 1009)
    elif variant == "no-oc-core-signal":
        patch_no_oc_signal(mcgs)
    elif variant in {"monotone-core", "no-pair-closure-final-core"}:
        patch_dynamic_core_selection(mcgs, variant)

    scc_result = await mcgs.search(graph, scc)

    scores = {cid: score for cid, score in scc_result.get("ranking_by_risk", [])}
    ranking = scc_result.get("ranking_by_risk", [])
    score_vals = list(scores.values())
    score_spread = max(score_vals) - min(score_vals) if score_vals else 0.0
    root_nodes = [injected_id] if injected_id else []
    top1_hit = ranking[0][0] in root_nodes if (ranking and root_nodes) else None
    top3_ids = {cid for cid, _score in ranking[:3]}
    top3_hit = bool(top3_ids & set(root_nodes)) if root_nodes else None
    node_names = {
        cid: graph.clauses[cid].title
        for cid in scc.clause_ids
        if cid in graph.clauses
    }

    result = {
        "method": "sa-mcgs",
        **battle.build_risk_rubric_audit(
            adapter_type="local_window_evidence_for_search",
            input_scope="local_scc_window",
        ),
        "model": args.model,
        "domain": case["domain"],
        "scc_size": scc.size,
        "scc_id": scc.id,
        "scc_clause_ids": scc.clause_ids,
        "budget": cfg["alphago_mcgs"]["budget"],
        "llm_calls": scc_result.get("llm_calls", 0),
        "tt_hits": scc_result.get("tt_hits", 0),
        "tt_hit_rate": scc_result.get("tt_hit_rate", 0),
        "time": time.time() - started,
        "scores": scores,
        "ranking": ranking,
        "oc_detected": scc_result.get("oc_detected_clauses", []),
        "oc_count": scc_result.get("oc_count", 0),
        "score_spread": score_spread,
        "score_mean": sum(score_vals) / max(1, len(score_vals)),
        "score_max": max(score_vals) if score_vals else 0,
        "node_names": node_names,
        "clause_details": scc_result.get("clause_details", {}),
        "local_risk_subgraph_counts": scc_result.get("local_risk_subgraph_counts", {}),
        "repair_entry_counts": scc_result.get("repair_entry_counts", {}),
        "local_conflict_edges": scc_result.get("local_conflict_edges", []),
        "local_subgraph_signal": scc_result.get("local_subgraph_signal", {}),
        "local_subgraph_candidate_nodes": scc_result.get("local_subgraph_candidate_nodes", []),
        "ranking_by_local_subgraph": scc_result.get("ranking_by_local_subgraph", []),
        "amaf_node_evidence": scc_result.get("amaf_node_evidence", {}),
        "amaf_edge_evidence": scc_result.get("amaf_edge_evidence", {}),
        "path_fragment_evidence": scc_result.get("path_fragment_evidence", {}),
        "relation_node_raw_scores": scc_result.get("relation_node_raw_scores", {}),
        "relation_probe_history": scc_result.get("relation_probe_history", []),
        "relation_probe_count": scc_result.get("relation_probe_count", 0),
        "selection_events": scc_result.get("selection_events", []),
        "relation_first_enabled": scc_result.get("relation_first_enabled", False),
        "relation_evidence_policy": scc_result.get("relation_evidence_policy"),
        "evidence_node_scores": scc_result.get("evidence_node_scores", {}),
        "evidence_component_names": scc_result.get("evidence_component_names", []),
        "evidence_component_policy": scc_result.get("evidence_component_policy"),
        "ranking_by_evidence": scc_result.get("ranking_by_evidence", []),
        "conflict_probability_matrix": scc_result.get("conflict_probability_matrix", []),
        "evidence_pair_memory_nodes": scc_result.get("evidence_pair_memory_nodes", []),
        "evidence_pair_memory_edges": scc_result.get("evidence_pair_memory_edges", []),
        "critical_pair_ledger_rows": scc_result.get("critical_pair_ledger_rows", []),
        "critical_pair_locked_edges": scc_result.get("critical_pair_locked_edges", []),
        "critical_pair_candidate_edges": scc_result.get("critical_pair_candidate_edges", []),
        "critical_pair_revisit_history": scc_result.get("critical_pair_revisit_history", []),
        "critical_pair_policy": scc_result.get("critical_pair_policy"),
        "mcgs_compression_profile": (
            cfg.get("alphago_mcgs", {})
            .get("evidence", {})
            .get("compression_profile", "current")
        ),
        "mcgs_compression_params": {
            key: value
            for key, value in cfg.get("alphago_mcgs", {}).get("evidence", {}).items()
            if key.startswith("core_")
            or key.startswith("subgraph_")
            or key.startswith("critical_pair_core_")
        },
        "evidence_risk_subgraph_nodes": scc_result.get("evidence_risk_subgraph_nodes", []),
        "evidence_risk_subgraph_size": scc_result.get("evidence_risk_subgraph_size", 0),
        "evidence_compression_ratio": scc_result.get("evidence_compression_ratio", 0),
        "context_evidence_risk_subgraph_nodes": scc_result.get("context_evidence_risk_subgraph_nodes", []),
        "context_evidence_risk_subgraph_size": scc_result.get("context_evidence_risk_subgraph_size", 0),
        "context_evidence_compression_ratio": scc_result.get("context_evidence_compression_ratio", 0),
        "dynamic_core_priority_rows": scc_result.get("dynamic_core_priority_rows", []),
        "dynamic_core_hit_cap": scc_result.get("dynamic_core_hit_cap", False),
        "evidence_subgraph_policy": scc_result.get("evidence_subgraph_policy"),
        "evidence_subgraph_cap": scc_result.get("evidence_subgraph_cap"),
        "trace_events": scc_result.get("trace_events", []),
        "ground_truth_nodes": root_nodes,
        "gt_evidence": {node: "injected memory_stress defect (seed=42)" for node in root_nodes},
        "top1_hit": top1_hit,
        "top3_hit": top3_hit,
    }

    result.update(
        {
            "inject_mode": True,
            "injected_node": injected_id,
            "inject_type": battle.DOMAIN_INJECT_TYPE.get(case["domain"]),
            "inject_profile": "memory_stress",
            "cycle_source": "real_long",
        }
    )
    result.update(injection_metadata)
    battle.add_rank_metrics(result, injected_id)
    battle.add_structural_rank_metrics(result, injection_metadata)
    evidence_nodes = injection_metadata.get("injected_evidence_nodes", [injected_id])
    result.update(
        battle.build_risk_subgraph_summary(
            graph,
            scc,
            result,
            injected_id,
            evidence_nodes,
            injection_metadata.get("injected_risk_nodes"),
            injection_metadata.get("injected_affected_nodes"),
        )
    )
    result.update(
        battle.build_local_declared_subgraph_summary(
            scc,
            result,
            evidence_nodes,
            injection_metadata.get("injected_risk_nodes"),
            injection_metadata.get("injected_affected_nodes"),
        )
    )
    result.update(
        battle.build_core_evidence_subgraph_summary(
            scc,
            result,
            evidence_nodes,
            injection_metadata.get("injected_risk_nodes"),
            injection_metadata.get("injected_affected_nodes"),
        )
    )
    result.update(
        battle.build_trace_convergence_summary(
            scc,
            result,
            evidence_nodes,
            injection_metadata.get("injected_risk_nodes"),
            injection_metadata.get("injected_affected_nodes"),
        )
    )
    return result


def attach_ablation_audit(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    case: dict[str, Any],
    variant: str,
    llm: cost.LoggingOpenAIClient | None,
    started_at: float,
    error: str | None = None,
) -> dict[str, Any]:
    result.update(
        {
            "case_id": case["case_id"],
            "case_order": case["case_order"],
            "ablation_variant": variant,
            "ablation_label": VARIANT_LABELS.get(variant, variant),
            "component_ablation_error": error,
            "ablation_started_at": started_at,
            "ablation_completed_at": time.time(),
            "ablation_started_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started_at)),
            "ablation_completed_at_iso": cost.now_iso(),
            "case_concurrency": args.case_concurrency,
            "internal_concurrency": args.internal_concurrency,
            "component_ablation_budget": args.budget if variant != "full-sa-mcgs-locked" else None,
            "llm_usage_summary": cost.usage_summary(llm.call_records) if llm is not None else {},
        }
    )
    return result


def result_path(output_dir: Path, case: dict[str, Any], variant: str) -> Path:
    return output_dir / "results" / f"{case['case_id']}__{cost.safe_token(variant)}.json"


def extract_locked_full(case: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    src = Path(str(case.get("source_result_file") or ""))
    if not src.exists():
        raise FileNotFoundError(f"Locked main result file not found: {src}")
    payload = json.loads(src.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else [payload]
    for row in rows:
        if (
            row.get("method") == "sa-mcgs"
            and row.get("model") == args.model
            and row.get("domain") == case["domain"]
            and row.get("scc_id") == case["scc_id"]
            and int(row.get("scc_size") or -1) == int(case["scc_size"])
        ):
            result = copy.deepcopy(row)
            result["ablation_source"] = "locked_main_experiment"
            return attach_ablation_audit(
                result,
                args=args,
                case=case,
                variant="full-sa-mcgs-locked",
                llm=None,
                started_at=time.time(),
            )
    raise RuntimeError(f"No locked gpt-4o SA-MCGS row found in {src}")


async def run_one_variant(
    args: argparse.Namespace,
    output_dir: Path,
    case: dict[str, Any],
    variant: str,
    graphs: dict[str, Any],
) -> dict[str, Any]:
    path = result_path(output_dir, case, variant)
    if path.exists() and not args.retry_errors:
        return json.loads(path.read_text(encoding="utf-8"))
    if path.exists() and args.retry_errors:
        old = json.loads(path.read_text(encoding="utf-8"))
        if not old.get("component_ablation_error"):
            return old

    llm = make_llm(args, output_dir, case, variant)
    started = time.time()
    try:
        graph, scc, injected_id, injection_metadata = cost.prepare_injected_case(case, graphs)
        result = await run_sa_mcgs_variant(
            llm,
            args,
            case,
            graph,
            scc,
            injected_id,
            injection_metadata,
            variant,
        )
        result = attach_ablation_audit(
            result,
            args=args,
            case=case,
            variant=variant,
            llm=llm,
            started_at=started,
        )
    except Exception as exc:
        result = attach_ablation_audit(
            {
                "method": "sa-mcgs",
                "model": args.model,
                "domain": case["domain"],
                "scc_id": case["scc_id"],
                "scc_size": case["scc_size"],
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
            args=args,
            case=case,
            variant=variant,
            llm=llm,
            started_at=started,
            error=str(exc),
        )
    finally:
        await llm.close()

    cost.atomic_write_json(path, result)
    return result


def metric_value(result: dict[str, Any], metric: str) -> Any:
    if result.get("component_ablation_error"):
        return None
    mapping = {
        "root_at_3": ("root_top3_hit", "top3_hit"),
        "risk_any": ("core_evidence_contains_any_risk_node",),
        "risk_all": ("core_evidence_contains_all_risk_nodes",),
        "compression": ("core_evidence_compression_ratio",),
        "core_size": ("core_evidence_risk_subgraph_size",),
    }
    for key in mapping[metric]:
        if key in result:
            return result.get(key)
    return None


def summarize(output_dir: Path) -> None:
    files = sorted((output_dir / "results").glob("*.json"))
    rows: list[dict[str, Any]] = []
    for path in files:
        result = json.loads(path.read_text(encoding="utf-8"))
        usage = result.get("llm_usage_summary") or {}
        locked_source = result.get("ablation_variant") == "full-sa-mcgs-locked"
        rows.append(
            {
                "variant": VARIANT_LABELS.get(result.get("ablation_variant"), result.get("ablation_variant")),
                "variant_key": result.get("ablation_variant"),
                "case_id": result.get("case_id"),
                "case_order": result.get("case_order"),
                "domain": result.get("domain"),
                "scc_id": result.get("scc_id"),
                "scc_size": result.get("scc_size"),
                "template": result.get("injected_conflict_template") or result.get("template"),
                "invalid": bool(result.get("component_ablation_error")),
                "root_at_3": metric_value(result, "root_at_3"),
                "risk_any": metric_value(result, "risk_any"),
                "risk_all": metric_value(result, "risk_all"),
                "compression": metric_value(result, "compression"),
                "core_size": metric_value(result, "core_size"),
                "llm_calls": None if locked_source else result.get("llm_calls"),
                "recorded_api_calls": usage.get("recorded_api_calls"),
                "total_tokens": usage.get("total_tokens"),
                "runtime_sec": result.get("time"),
                "relation_probe_count": result.get("relation_probe_count"),
                "critical_pair_locked_count": len(result.get("critical_pair_locked_edges") or []),
                "critical_pair_candidate_count": len(result.get("critical_pair_candidate_edges") or []),
                "first_risk_any_rollout": result.get("first_subgraph_risk_any_rollout"),
                "first_risk_all_rollout": result.get("first_subgraph_risk_all_rollout"),
                "result_file": str(path),
            }
        )
    if not rows:
        return

    flat_path = output_dir / "summary_component_cases.csv"
    with flat_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["variant_key"]].append(row)
    full_items = groups.get("full-sa-mcgs-locked", [])
    full_metrics = {
        "Root@3": mean_bool([row["root_at_3"] for row in full_items]),
        "Risk-any": mean_bool([row["risk_any"] for row in full_items]),
        "Risk-all": mean_bool([row["risk_all"] for row in full_items]),
    }

    variant_order = [
        "full-sa-mcgs-locked",
        *[variant for variant in ALL_LLM_VARIANTS if variant in groups],
    ]
    table_rows = []
    for variant in variant_order:
        items = groups.get(variant, [])
        if not items:
            continue
        root = mean_bool([row["root_at_3"] for row in items])
        risk_any = mean_bool([row["risk_any"] for row in items])
        risk_all = mean_bool([row["risk_all"] for row in items])
        table_rows.append(
            {
                "Variant": VARIANT_LABELS.get(variant, variant),
                "N": len({row["case_id"] for row in items}),
                "Invalid": mean_bool([row["invalid"] for row in items]),
                "Root@3": root,
                "Risk-any": risk_any,
                "Risk-all": risk_all,
                "Compression": mean_numeric([row["compression"] for row in items]),
                "Avg core size": mean_numeric([row["core_size"] for row in items]),
                "Delta Root@3": None if root is None or full_metrics["Root@3"] is None else root - full_metrics["Root@3"],
                "Delta Risk-any": None if risk_any is None or full_metrics["Risk-any"] is None else risk_any - full_metrics["Risk-any"],
                "Delta Risk-all": None if risk_all is None or full_metrics["Risk-all"] is None else risk_all - full_metrics["Risk-all"],
            }
        )

    if not table_rows:
        return

    table_csv = output_dir / "component_ablation_table.csv"
    with table_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(table_rows[0].keys()))
        writer.writeheader()
        writer.writerows(table_rows)

    headers = list(table_rows[0].keys())
    if "stage2" in output_dir.name:
        stage_title = "Stage 2 Dynamic Component Ablation Table"
        stage_note = (
            "Dynamic run: matched cases with full rollout trajectories re-run. "
            "Full SA-MCGS rows are copied from locked main results; Stage 2 variants "
            "disable OC/core signals or alter final-core construction while preserving "
            "the main local evidence schema and rollout budget."
        )
    elif "stage1" in output_dir.name:
        stage_title = "Stage 1 Component Ablation Main Table"
        stage_note = (
            "Main run: matched cases. Full SA-MCGS rows are copied from locked main results; "
            "LLM-dependent ablations are re-run under the main setting."
        )
    else:
        stage_title = "Stage 0 Component Ablation Smoke Table"
        stage_note = (
            "Smoke run only: 3 matched cases. Full SA-MCGS rows are copied from locked main results; "
            "LLM-dependent ablations are re-run under the main setting."
        )
    lines = [
        f"# {stage_title}",
        "",
        stage_note,
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in table_rows:
        lines.append("| " + " | ".join(fmt_cell(row[header]) for header in headers) + " |")
    (output_dir / "component_ablation_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_status(
    output_dir: Path,
    plan: list[dict[str, Any]],
    variants: list[str],
    current: dict[str, Any] | None = None,
    active: list[dict[str, Any]] | None = None,
) -> None:
    completed = 0
    failed = 0
    all_variants = ["full-sa-mcgs-locked", *variants]
    for case in plan:
        for variant in all_variants:
            path = result_path(output_dir, case, variant)
            if not path.exists():
                continue
            completed += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                failed += 1
                continue
            if payload.get("component_ablation_error"):
                failed += 1
    status = {
        "run_id": output_dir.name,
        "updated_at": cost.now_iso(),
        "stage": "stage2" if "stage2" in output_dir.name else ("stage1" if "stage1" in output_dir.name else "stage0"),
        "total_cases": len(plan),
        "variants": all_variants,
        "total_case_variants": len(plan) * len(all_variants),
        "completed_case_variants": completed,
        "failed_case_variants": failed,
        "remaining_case_variants": len(plan) * len(all_variants) - completed,
        "current": current,
        "active": active or ([] if current is None else [current]),
        "result_dir": str(output_dir / "results"),
        "call_log": str(output_dir / "call_logs" / "llm_calls.jsonl"),
    }
    cost.atomic_write_json(output_dir / "status.json", status)


async def run(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    write_dashboard(output_dir)
    plan = build_case_plan(args, output_dir)
    variants = args.variants
    cost.atomic_write_json(
        output_dir / "run_config.json",
        {
            "created_or_updated_at": cost.now_iso(),
            "stage": args.stage,
            "model": args.model,
            "model_id": cost.MODEL_IDS.get(args.model, args.model),
            "budget": args.budget,
            "window_size": args.window_size,
            "case_concurrency": args.case_concurrency,
            "internal_concurrency": args.internal_concurrency,
            "variants": variants,
            "case_orders": args.case_orders,
            "case_plan": str(args.case_plan),
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
        },
    )

    for case in plan:
        path = result_path(output_dir, case, "full-sa-mcgs-locked")
        if path.exists() and not args.rebuild_full:
            continue
        try:
            full_result = extract_locked_full(case, args)
        except Exception as exc:
            full_result = attach_ablation_audit(
                {
                    "method": "sa-mcgs",
                    "model": args.model,
                    "domain": case["domain"],
                    "scc_id": case["scc_id"],
                    "scc_size": case["scc_size"],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
                args=args,
                case=case,
                variant="full-sa-mcgs-locked",
                llm=None,
                started_at=time.time(),
                error=str(exc),
            )
        cost.atomic_write_json(path, full_result)

    summarize(output_dir)
    write_status(output_dir, plan, variants)
    if args.dry_run:
        return

    if not os.environ.get(args.api_key_env):
        raise RuntimeError(f"{args.api_key_env} is not set")

    graphs = cost.load_graphs(plan)
    semaphore = asyncio.Semaphore(args.case_concurrency)
    write_lock = asyncio.Lock()
    active_tasks: dict[str, dict[str, Any]] = {}

    async def guarded(case: dict[str, Any], variant: str) -> None:
        async with semaphore:
            key = f"{case['case_id']}::{variant}"
            current = {
                "case_id": case["case_id"],
                "case_order": case["case_order"],
                "domain": case["domain"],
                "scc_size": case["scc_size"],
                "variant": variant,
                "started_at": cost.now_iso(),
            }
            async with write_lock:
                active_tasks[key] = current
                write_status(output_dir, plan, variants, current=current, active=list(active_tasks.values()))
            try:
                await run_one_variant(args, output_dir, case, variant, graphs)
            finally:
                async with write_lock:
                    active_tasks.pop(key, None)
                    summarize(output_dir)
                    write_status(
                        output_dir,
                        plan,
                        variants,
                        current={**current, "completed_at": cost.now_iso()},
                        active=list(active_tasks.values()),
                    )

    tasks = [
        asyncio.create_task(guarded(case, variant))
        for case in plan
        for variant in variants
    ]
    await asyncio.gather(*tasks)
    summarize(output_dir)
    write_status(output_dir, plan, variants)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run component ablations for the EMNLP discussion.")
    parser.add_argument("--stage", choices=["stage0", "stage1", "stage2"], default="stage0")
    parser.add_argument("--case-plan", type=Path, default=DEFAULT_CASE_PLAN)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--case-orders", nargs="+", type=int, default=None)
    parser.add_argument("--budget", type=int, default=60)
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--case-concurrency", type=int, default=None)
    parser.add_argument("--internal-concurrency", type=int, default=4)
    parser.add_argument("--compression-profile", default="current")
    parser.add_argument("--variants", nargs="+", default=None, choices=ALL_LLM_VARIANTS)
    parser.add_argument("--base-url", default=battle.XHUB_BASE_URL)
    parser.add_argument("--api-key-env", default="XHUB_API_KEY")
    parser.add_argument("--llm-timeout", type=float, default=600)
    parser.add_argument("--llm-max-retries", type=int, default=2)
    parser.add_argument("--random-seed", type=int, default=8229)
    parser.add_argument("--rebuild-plan", action="store_true")
    parser.add_argument("--rebuild-full", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.variants is None:
        args.variants = STAGE2_LLM_VARIANTS if args.stage == "stage2" else LLM_VARIANTS
    if args.case_orders is None:
        if args.stage == "stage0":
            args.case_orders = [1, 10, 19]
        elif args.stage == "stage2":
            args.case_orders = list(range(1, 41))
        else:
            args.case_orders = list(range(1, 21))
    if args.case_concurrency is None:
        args.case_concurrency = 3 if args.stage == "stage0" else 4
    if args.output_dir is None:
        run_id = time.strftime(
            f"{args.stage}_gpt4o_b{args.budget}_ic{args.internal_concurrency}_cc{args.case_concurrency}_%Y%m%d_%H%M%S",
            time.localtime(),
        )
        args.output_dir = DEFAULT_RUNS_DIR / run_id
    args.output_dir = args.output_dir.resolve()
    args.case_plan = args.case_plan.resolve()
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))

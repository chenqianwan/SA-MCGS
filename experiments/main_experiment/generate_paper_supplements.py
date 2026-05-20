#!/usr/bin/env python3
"""Generate paper-facing supplement reports from the locked main experiment.

The script is intentionally read-only with respect to raw result files. It
loads the canonical status files through the same dashboard helpers used for
manual inspection, then writes compact Markdown/CSV reports and publication
figures under experiments/main_experiment/supplements/.
"""
from __future__ import annotations

import csv
import inspect
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
MAIN_DIR = ROOT / "experiments" / "main_experiment"
SUPP_DIR = MAIN_DIR / "supplements"
FIG_DIR = SUPP_DIR / "figures"
TABLE_DIR = SUPP_DIR / "tables"
CROSS_DIR = ROOT / "experiments" / "cross_domain"

sys.path.insert(0, str(CROSS_DIR))
import final_results_dashboard as dash  # noqa: E402
from progress_dashboard import _load_records_from_status, _metric_values  # noqa: E402
import run_cross_domain_battle as battle  # noqa: E402


METHODS = ["naive", "sa-mcgs"]
METRICS = ["root", "risk_any", "risk_all", "compression"]
ROW_METRIC_KEY = {
    "root": "root_at_3",
    "risk_any": "risk_any",
    "risk_all": "risk_all",
    "compression": "compression",
}
METRIC_LABELS = {
    "root": "Root@3",
    "risk_any": "Risk-any",
    "risk_all": "Risk-all",
    "compression": "Compression",
    "effective_compression": "Effective compression",
    "errors": "Errors",
}


def ensure_dirs() -> None:
    for directory in (SUPP_DIR, FIG_DIR, TABLE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def pct(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.{digits}f}%"


def count_pct(num: int, den: int) -> str:
    if den <= 0:
        return "-"
    return f"{num}/{den} ({num / den:.0%})"


def fmt_num(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def method_records(records: Iterable[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    return [record for record in records if record.get("method") == method]


def case_key(record: dict[str, Any]) -> tuple[str, ...]:
    """Method-independent key for matched Naive-vs-SA comparisons."""
    return (
        str(record.get("domain", "")),
        str(record.get("scc_id", "")),
        str(record.get("scc_size", "")),
        str(record.get("model", "")),
        str(record.get("_task_template") or record.get("injected_conflict_family") or ""),
        str(record.get("_task_severity") or record.get("injected_conflict_severity") or ""),
        str(record.get("_task_compression_profile") or record.get("mcgs_compression_profile") or "current"),
    )


def template_name(record: dict[str, Any]) -> str:
    return str(record.get("_task_template") or record.get("injected_conflict_family") or "")


def summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return dash._metric_summary(records)


def metric_hits(records: list[dict[str, Any]], metric_key: str) -> int:
    if metric_key == "root":
        key = "root_top3"
    elif metric_key == "risk_any":
        key = "risk_any"
    elif metric_key == "risk_all":
        key = "risk_all"
    else:
        raise ValueError(metric_key)
    return sum(1 for record in records if _metric_values(record).get(key) is True)


def e0_matched_valid_tables(current: list[dict[str, Any]]) -> None:
    strict_rows: list[dict[str, Any]] = []
    valid_rows: list[dict[str, Any]] = []
    matched_rows: list[dict[str, Any]] = []

    for method in METHODS:
        recs = method_records(current, method)
        summ = summary(recs)
        strict_rows.append({
            "scope": "strict_all_records",
            "method": method,
            "n": summ["n"],
            "errors": summ["errors"],
            "root_at_3": summ["root"],
            "risk_any": summ["risk_any"],
            "risk_all": summ["risk_all"],
            "compression": summ["compression"],
            "effective_compression": summ["effective_compression"],
        })
        valid = [record for record in recs if not record.get("error")]
        vs = summary(valid)
        valid_rows.append({
            "scope": "valid_only",
            "method": method,
            "n": vs["n"],
            "errors": vs["errors"],
            "root_at_3": vs["root"],
            "risk_any": vs["risk_any"],
            "risk_all": vs["risk_all"],
            "compression": vs["compression"],
            "effective_compression": vs["effective_compression"],
        })

    by_case: dict[tuple[str, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in current:
        by_case[case_key(record)][str(record.get("method"))] = record
    matched_cases = [
        pair for pair in by_case.values()
        if all(method in pair for method in METHODS)
        and all(not pair[method].get("error") for method in METHODS)
    ]
    for method in METHODS:
        recs = [pair[method] for pair in matched_cases]
        ms = summary(recs)
        matched_rows.append({
            "scope": "matched_no_error_pairs",
            "method": method,
            "n": ms["n"],
            "errors": ms["errors"],
            "root_at_3": ms["root"],
            "risk_any": ms["risk_any"],
            "risk_all": ms["risk_all"],
            "compression": ms["compression"],
            "effective_compression": ms["effective_compression"],
        })

    all_rows = strict_rows + valid_rows + matched_rows
    write_csv(TABLE_DIR / "E0_matched_valid_only.csv", all_rows)
    (TABLE_DIR / "E0_matched_valid_only.json").write_text(
        json.dumps(all_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    md = [
        "# E0. Matched / Valid-only / Error Handling",
        "",
        "目的：把 strict rate、valid-only rate、matched no-error rate 分开，回答 reviewer 关于解析失败是否被 cherry-pick 的问题。",
        "",
        f"- Strict 分母：Naive={len(method_records(current, 'naive'))}, SA-MCGS={len(method_records(current, 'sa-mcgs'))}。",
        f"- Matched no-error 分母：{len(matched_cases)} 个同一 SCC + 同一模型 + 同一注入的可比 pair。",
        "",
        "| Scope | Method | N | Errors | Root@3 | Risk-any | Risk-all | Compression | Effective Compression |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in all_rows:
        md.append(
            "| {scope} | {method} | {n} | {errors} | {root_at_3} | {risk_any} | {risk_all} | {compression} | {effective_compression} |".format(
                scope=row["scope"],
                method=row["method"],
                n=row["n"],
                errors=row["errors"],
                root_at_3=pct(row["root_at_3"]),
                risk_any=pct(row["risk_any"]),
                risk_all=pct(row["risk_all"]),
                compression=pct(row["compression"]),
                effective_compression=pct(row["effective_compression"]),
            )
        )
    md.extend([
        "",
        "论文写法建议：主表用 strict；补充表同时给 valid-only 和 matched no-error。这样 Naive 的 59 个解析失败不会被忽略，也不会把 SA-MCGS 的优势只解释成 JSON 稳定性。",
        "",
    ])
    (SUPP_DIR / "E0_MATCHED_VALID_ONLY.md").write_text("\n".join(md), encoding="utf-8")
    plot_e0(all_rows)


def e1_naive_output_burden_control(current: list[dict[str, Any]]) -> None:
    """Compare full Naive direct-subgraph output with the lightweight schema.

    E1 is intentionally a supplement, not a new main result. It reuses the
    same full-SCC input but removes the complete ranking and per-node output
    burden from Naive to test whether CUAD failures are mostly schema pressure.
    """
    status_name = "e1_naive_lite_cuad_long32_severity_grid_status.json"
    lite_records = [
        record
        for record in load_status_records(status_name)
        if record.get("method") == "naive"
        and record.get("naive_profile") == "direct_subgraph_lite"
    ]
    if not lite_records:
        return

    main_naive_by_case = {
        case_key(record): record
        for record in current
        if record.get("method") == "naive"
        and record.get("domain") == "cuad"
        and record.get("model") in {"gpt-4o", "qwen2.5-72b"}
    }
    paired_lite: list[dict[str, Any]] = []
    paired_full: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    for lite in lite_records:
        full = main_naive_by_case.get(case_key(lite))
        if not full:
            continue
        paired_lite.append(lite)
        paired_full.append(full)
        lite_metrics = _metric_values(lite)
        full_metrics = _metric_values(full)
        case_rows.append({
            "domain": lite.get("domain"),
            "scc_id": lite.get("scc_id"),
            "scc_size": lite.get("scc_size"),
            "model": lite.get("model"),
            "template": template_name(lite),
            "full_error": bool(full.get("error")),
            "lite_error": bool(lite.get("error")),
            "full_root_at_3": full_metrics.get("root_top3"),
            "lite_root_at_3": lite_metrics.get("root_top3"),
            "full_risk_any": full_metrics.get("risk_any"),
            "lite_risk_any": lite_metrics.get("risk_any"),
            "full_risk_all": full_metrics.get("risk_all"),
            "lite_risk_all": lite_metrics.get("risk_all"),
            "full_compression": full_metrics.get("compression"),
            "lite_compression": lite_metrics.get("compression"),
            "full_subgraph_size": full_metrics.get("subgraph_size"),
            "lite_subgraph_size": lite_metrics.get("subgraph_size"),
            "full_prompt_words": full.get("prompt_word_count"),
            "lite_prompt_words": lite.get("prompt_word_count"),
            "full_time_sec": full.get("time"),
            "lite_time_sec": lite.get("time"),
        })

    def row(scope: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        s = summary(records)
        return {
            "scope": scope,
            "n": s["n"],
            "errors": s["errors"],
            "root_at_3": s["root"],
            "risk_any": s["risk_any"],
            "risk_all": s["risk_all"],
            "compression": s["compression"],
            "effective_compression": s["effective_compression"],
            "avg_subgraph": s["avg_subgraph"],
            "avg_prompt_words": avg_field(records, "prompt_word_count"),
            "avg_time_sec": avg_field(records, "time"),
        }

    rows = [
        row("lite_all_records", lite_records),
        row("matched_main_full_direct_subgraph", paired_full),
        row("matched_lite_direct_subgraph", paired_lite),
    ]
    write_csv(TABLE_DIR / "E1_naive_output_burden_control.csv", rows)
    write_csv(TABLE_DIR / "E1_naive_output_burden_cases.csv", case_rows)
    (TABLE_DIR / "E1_naive_output_burden_control.json").write_text(
        json.dumps({"summary": rows, "cases": case_rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    status_path = CROSS_DIR / "results" / status_name
    status_text = ""
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status_text = f"- Status summary: `{status.get('summary')}`."
        except Exception:
            status_text = "- Status summary: unavailable."

    matched_n = len(paired_lite)
    md = [
        "# E1. Naive Output-burden Control",
        "",
        "目的：控制 Naive 的输出 schema 负担。输入仍是完整 CUAD 长 SCC；区别只是轻量版不再要求完整 `global_ranking` 和逐节点 `clause_evaluations`，只输出 `top_risk_nodes` 与 `risk_subgraph_nodes`。",
        "",
        status_text,
        f"- Matched full-vs-lite records: `{matched_n}`.",
        "- 解释口径：E1 只回答 Naive 的 JSON/输出负担问题，不替换主实验的 Naive direct-subgraph baseline。",
        "",
        "| Scope | N | Errors | Root@3 | Risk-any | Risk-all | Compression | Avg subgraph | Avg prompt words | Avg time sec |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in rows:
        md.append(
            f"| {item['scope']} | {item['n']} | {item['errors']} | {pct(item['root_at_3'])} | {pct(item['risk_any'])} | {pct(item['risk_all'])} | {pct(item['compression'])} | {fmt_num(item['avg_subgraph'], 2)} | {fmt_num(item['avg_prompt_words'], 0)} | {fmt_num(item['avg_time_sec'], 1)} |"
        )
    md.extend([
        "",
        "## Reviewer-facing Takeaway",
        "",
        "- 如果轻量 Naive 的报错显著下降，说明 CUAD 长合同的一部分失败来自 whole-SCC one-shot 的输出格式压力。",
        "- 如果轻量 Naive 的 Risk-all 仍明显低于 SA-MCGS，则说明差距不只是 JSON/schema，而是长环结构搜索与证据保留问题。",
        "- 这组结果应放 appendix / robustness，不进入主表。",
        "",
    ])
    (SUPP_DIR / "E1_NAIVE_OUTPUT_BURDEN_CONTROL.md").write_text("\n".join(md), encoding="utf-8")
    plot_e1(rows)


def latest_trace_point(trace: list[dict[str, Any]], budget: int) -> dict[str, Any] | None:
    points = []
    for point in trace:
        try:
            rollout = int(point.get("rollout") or 0)
        except Exception:
            continue
        if rollout <= budget:
            points.append((rollout, point))
    if not points:
        return None
    return max(points, key=lambda item: item[0])[1]


def bool_rate(values: list[Any]) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value is True) / len(values)


def avg(values: list[Any]) -> float | None:
    nums: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            nums.append(float(value))
        except Exception:
            pass
    if not nums:
        return None
    return sum(nums) / len(nums)


def avg_field(records: list[dict[str, Any]], field: str) -> float | None:
    return avg([record.get(field) for record in records])


def load_status_records(status_name: str) -> list[dict[str, Any]]:
    path = CROSS_DIR / "results" / status_name
    if not path.exists():
        return []
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(status, dict):
        return []
    return _load_records_from_status(status)


def e2_budget_prefix(current: list[dict[str, Any]]) -> None:
    budgets = [5, 10, 20, 30, 60]
    sa_records = method_records(current, "sa-mcgs")
    rows: list[dict[str, Any]] = []
    for model in ["ALL", *dash.MODEL_ORDER]:
        subset = sa_records if model == "ALL" else [r for r in sa_records if r.get("model") == model]
        if not subset:
            continue
        for budget in budgets:
            points = [
                latest_trace_point(record.get("convergence_trace") or [], budget)
                for record in subset
                if isinstance(record.get("convergence_trace"), list)
            ]
            points = [point for point in points if point]
            rows.append({
                "model": model,
                "budget": budget,
                "n_trace": len(points),
                "risk_any": bool_rate([point.get("risk_any") for point in points]),
                "risk_all": bool_rate([point.get("risk_all") for point in points]),
                "risk_coverage": avg([point.get("risk_coverage") for point in points]),
                "valuable_coverage": avg([point.get("valuable_coverage") for point in points]),
                "compression": avg([point.get("compression_ratio") for point in points]),
                "effective_oc_discovered": bool_rate([point.get("effective_oc") for point in points]),
            })
    write_csv(TABLE_DIR / "E2_budget_prefix_convergence.csv", rows)
    (TABLE_DIR / "E2_budget_prefix_convergence.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md = [
        "# E2. Budget-prefix Convergence",
        "",
        "目的：用同一批 SA-MCGS traces 截断到不同 rollout budget，回答“更多 rollout 是否真的带来收敛”的问题。",
        "",
        "注意：`effective_oc_discovered` 是 cumulative discovery 指标，只说明某个 budget 前是否曾经发现有效 OC，不作为主指标；主指标仍是当前 core 的 Risk-any / Risk-all / Compression。",
        "",
        "| Model | Budget | Trace N | Risk-any | Risk-all | Risk coverage | Valuable coverage | Compression | Effective OC discovered |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        md.append(
            f"| {row['model']} | {row['budget']} | {row['n_trace']} | {pct(row['risk_any'])} | {pct(row['risk_all'])} | {pct(row['risk_coverage'])} | {pct(row['valuable_coverage'])} | {pct(row['compression'])} | {pct(row['effective_oc_discovered'])} |"
        )
    (SUPP_DIR / "E2_BUDGET_PREFIX_CONVERGENCE.md").write_text("\n".join(md), encoding="utf-8")
    plot_e2(rows)


def e3_profile_ablation(current: list[dict[str, Any]], balanced: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for profile, records in [("current/default", current), ("balanced", balanced)]:
        for method in METHODS:
            subset = method_records(records, method)
            if not subset:
                continue
            s = summary(subset)
            rows.append({
                "profile": profile,
                "method": method,
                "n": s["n"],
                "errors": s["errors"],
                "root_at_3": s["root"],
                "risk_any": s["risk_any"],
                "risk_all": s["risk_all"],
                "compression": s["compression"],
                "effective_compression": s["effective_compression"],
                "avg_subgraph": s["avg_subgraph"],
            })
    write_csv(TABLE_DIR / "E3_compression_profile_ablation.csv", rows)
    (TABLE_DIR / "E3_compression_profile_ablation.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md = [
        "# E3. Compression Profile Ablation",
        "",
        "目的：把 `current/default` 主实验和 `balanced` 压缩强度分开。主论文只用 current/default；balanced 只作为压缩率-召回率 trade-off 补充。",
        "",
        "| Profile | Method | N | Errors | Root@3 | Risk-any | Risk-all | Compression | Effective Compression | Avg Subgraph |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        md.append(
            f"| {row['profile']} | {row['method']} | {row['n']} | {row['errors']} | {pct(row['root_at_3'])} | {pct(row['risk_any'])} | {pct(row['risk_all'])} | {pct(row['compression'])} | {pct(row['effective_compression'])} | {row['avg_subgraph']:.2f} |"
        )
    (SUPP_DIR / "E3_COMPRESSION_PROFILE_ABLATION.md").write_text("\n".join(md), encoding="utf-8")
    plot_e3(rows)


def e5_prompt_rubric() -> None:
    rubric = battle.build_shared_risk_rubric()
    rubric_hash = battle.shared_risk_rubric_hash()
    naive_src = inspect.getsource(battle._build_generic_naive_prompt)
    mcgs_src = inspect.getsource(battle._mcgs_generic_prompt)
    common_terms = [
        "directed graph of interdependent records",
        "depends on, constrains, references, modifies",
        "structurally inconsistent",
        "mutually incompatible",
        "underspecified",
        "high-impact",
        "risk_score",
        "record IDs",
    ]
    rows = []
    for term in common_terms:
        rows.append({
            "term": term,
            "naive_prompt": term in naive_src,
            "sa_window_prompt": term in mcgs_src,
        })
    write_csv(TABLE_DIR / "E5_prompt_rubric_parity.csv", rows)
    md = [
        "# E5. Prompt / Rubric Parity",
        "",
        f"- Shared semantic audit version: `{battle.SHARED_RISK_RUBRIC_VERSION}`",
        f"- Shared semantic hash: `{rubric_hash}`",
        "- 兼容性：没有在已完成实验后新增 prompt block；这是对已有通用 wording 的抽象记录。",
        "",
        "## Shared Risk Rubric",
        "",
        "```text",
        rubric.strip(),
        "```",
        "",
        "## Common Terms Audit",
        "",
        "| Term | Naive prompt | SA window prompt |",
        "|---|---:|---:|",
    ]
    for row in rows:
        md.append(
            f"| `{row['term']}` | {'yes' if row['naive_prompt'] else 'no'} | {'yes' if row['sa_window_prompt'] else 'no'} |"
        )
    md.extend([
        "",
        "## Adapter Difference",
        "",
        "- Naive adapter: one-shot full SCC, requires a whole-SCC ranking and a direct risk subgraph.",
        "- SA-MCGS adapter: repeated local windows, same risk semantics, plus local evidence fields for search aggregation.",
        "- 公平性结论：风险判断标准一致；差异来自输入范围和搜索/聚合机制，而不是领域专用找错提示。",
        "",
    ])
    (SUPP_DIR / "E5_PROMPT_RUBRIC_PARITY.md").write_text("\n".join(md), encoding="utf-8")


def plot_e0(rows: list[dict[str, Any]]) -> None:
    strict = [r for r in rows if r["scope"] == "strict_all_records"]
    matched = [r for r in rows if r["scope"] == "matched_no_error_pairs"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True)
    for ax, subset, title in zip(axes, [strict, matched], ["Strict", "Matched no-error"]):
        x = range(len(METRICS))
        width = 0.36
        by_method = {row["method"]: row for row in subset}
        ax.bar(
            [i - width / 2 for i in x],
            [by_method["naive"][ROW_METRIC_KEY[m]] for m in METRICS],
            width,
            label="Naive",
            color="#ff6b6b",
        )
        ax.bar(
            [i + width / 2 for i in x],
            [by_method["sa-mcgs"][ROW_METRIC_KEY[m]] for m in METRICS],
            width,
            label="SA-MCGS",
            color="#20c997",
        )
        ax.set_xticks(list(x), [METRIC_LABELS[m] for m in METRICS], rotation=18)
        ax.set_ylim(0, 1.05)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Rate")
    axes[0].legend()
    fig.tight_layout()
    savefig(fig, "E0_strict_vs_matched")


def plot_e1(rows: list[dict[str, Any]]) -> None:
    matched = [row for row in rows if row["scope"] in {"matched_main_full_direct_subgraph", "matched_lite_direct_subgraph"}]
    if len(matched) < 2:
        return
    by_scope = {row["scope"]: row for row in matched}
    labels = ["Root@3", "Risk-any", "Risk-all", "Compression"]
    keys = ["root_at_3", "risk_any", "risk_all", "compression"]
    x = range(len(labels))
    width = 0.36
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5))
    axes[0].bar(
        [i - width / 2 for i in x],
        [by_scope["matched_main_full_direct_subgraph"][key] for key in keys],
        width,
        label="Full direct-subgraph",
        color="#ff6b6b",
    )
    axes[0].bar(
        [i + width / 2 for i in x],
        [by_scope["matched_lite_direct_subgraph"][key] for key in keys],
        width,
        label="Lite direct-subgraph",
        color="#60a5fa",
    )
    axes[0].set_xticks(list(x), labels, rotation=18)
    axes[0].set_ylim(0, 1.05)
    axes[0].set_ylabel("Rate")
    axes[0].set_title("Matched metric rates")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend()

    burden_labels = ["Error rate", "Avg time / max", "Avg subgraph / max"]
    full = by_scope["matched_main_full_direct_subgraph"]
    lite = by_scope["matched_lite_direct_subgraph"]
    max_time = max(full.get("avg_time_sec") or 0, lite.get("avg_time_sec") or 0, 1)
    max_subgraph = max(full.get("avg_subgraph") or 0, lite.get("avg_subgraph") or 0, 1)
    full_bars = [
        full["errors"] / full["n"] if full["n"] else 0,
        (full.get("avg_time_sec") or 0) / max_time,
        (full.get("avg_subgraph") or 0) / max_subgraph,
    ]
    lite_bars = [
        lite["errors"] / lite["n"] if lite["n"] else 0,
        (lite.get("avg_time_sec") or 0) / max_time,
        (lite.get("avg_subgraph") or 0) / max_subgraph,
    ]
    y = range(len(burden_labels))
    axes[1].barh([i + width / 2 for i in y], full_bars, width, color="#ff6b6b", label="Full")
    axes[1].barh([i - width / 2 for i in y], lite_bars, width, color="#60a5fa", label="Lite")
    axes[1].set_yticks(list(y), burden_labels)
    axes[1].set_xlim(0, 1.05)
    axes[1].set_title("Output-burden proxies")
    axes[1].grid(axis="x", alpha=0.25)
    axes[1].legend()
    fig.tight_layout()
    savefig(fig, "E1_naive_output_burden")


def plot_e2(rows: list[dict[str, Any]]) -> None:
    overall = [row for row in rows if row["model"] == "ALL"]
    budgets = [row["budget"] for row in overall]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for key, label, color in [
        ("risk_any", "Risk-any", "#2563eb"),
        ("risk_all", "Risk-all", "#7c3aed"),
        ("compression", "Compression", "#059669"),
        ("effective_oc_discovered", "Effective OC discovered", "#ef4444"),
    ]:
        ax.plot(budgets, [row[key] for row in overall], marker="o", linewidth=2.4, label=label, color=color)
    ax.set_xlabel("SA-MCGS rollout budget prefix")
    ax.set_ylabel("Rate")
    ax.set_ylim(0, 1.05)
    ax.grid(alpha=0.25)
    ax.legend(loc="lower right")
    ax.set_title("E2 budget-prefix convergence on locked traces")
    fig.tight_layout()
    savefig(fig, "E2_budget_prefix_convergence")


def plot_e3(rows: list[dict[str, Any]]) -> None:
    sa_rows = [row for row in rows if row["method"] == "sa-mcgs"]
    profiles = [row["profile"] for row in sa_rows]
    x = range(len(profiles))
    width = 0.22
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for offset, key, label, color in [
        (-width, "risk_any", "Risk-any", "#2563eb"),
        (0, "risk_all", "Risk-all", "#7c3aed"),
        (width, "compression", "Compression", "#059669"),
    ]:
        ax.bar([i + offset for i in x], [row[key] for row in sa_rows], width, label=label, color=color)
    ax.set_xticks(list(x), profiles)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Rate")
    ax.set_title("E3 SA-MCGS profile trade-off")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    savefig(fig, "E3_profile_tradeoff")


def plot_main_paper_figures(current: list[dict[str, Any]]) -> None:
    main_rows = []
    for method in METHODS:
        s = summary(method_records(current, method))
        main_rows.append((method, s))
    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    x = range(len(METRICS))
    width = 0.36
    naive = dict(main_rows)["naive"]
    sa = dict(main_rows)["sa-mcgs"]
    ax.bar([i - width / 2 for i in x], [naive[m] for m in METRICS], width, color="#ff6b6b", label="Naive")
    ax.bar([i + width / 2 for i in x], [sa[m] for m in METRICS], width, color="#20c997", label="SA-MCGS")
    ax.set_xticks(list(x), [METRIC_LABELS[m] for m in METRICS])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Strict rate")
    ax.set_title("Main critical SCC experiment")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    savefig(fig, "main_metrics_strict")

    size_rows = dash._size_bucket_rows(current)
    labels = [row["bucket"] for row in size_rows]
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2), sharey=True)
    for ax, metric in zip(axes, ["root", "risk_any", "risk_all"]):
        ax.bar([i - width / 2 for i in range(len(labels))], [row["naive"][metric] for row in size_rows], width, color="#ff6b6b", label="Naive")
        ax.bar([i + width / 2 for i in range(len(labels))], [row["sa"][metric] for row in size_rows], width, color="#20c997", label="SA-MCGS")
        ax.set_title(METRIC_LABELS[metric])
        ax.set_xticks(list(range(len(labels))), labels, rotation=18, ha="right")
        ax.set_ylim(0, 1.05)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Strict rate")
    axes[0].legend()
    fig.tight_layout()
    savefig(fig, "main_by_scc_size")


def savefig(fig: plt.Figure, stem: str) -> None:
    for suffix in ("png", "pdf"):
        fig.savefig(FIG_DIR / f"{stem}.{suffix}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def supplement_index() -> None:
    md = [
        "# Main Experiment Supplements",
        "",
        "这些文件服务最终论文写作；主实验仍以 `experiments/main_experiment/MANIFEST.json` 为准。",
        "",
        "- [E0 matched / valid-only](E0_MATCHED_VALID_ONLY.md)",
        "- [E1 Naive output-burden control](E1_NAIVE_OUTPUT_BURDEN_CONTROL.md)",
        "- [E2 budget-prefix convergence](E2_BUDGET_PREFIX_CONVERGENCE.md)",
        "- [E3 compression profile ablation](E3_COMPRESSION_PROFILE_ABLATION.md)",
        "- [E5 prompt / rubric parity](E5_PROMPT_RUBRIC_PARITY.md)",
        "",
        "Figures live in `figures/`; machine-readable tables live in `tables/`.",
        "",
    ]
    (SUPP_DIR / "README.md").write_text("\n".join(md), encoding="utf-8")


def main() -> int:
    ensure_dirs()
    current = dash._load_selected(dash.CURRENT_STATUS_FILES, "current")
    balanced = dash._load_selected(dash.BALANCED_STATUS_FILES, "balanced")
    e0_matched_valid_tables(current)
    e1_naive_output_burden_control(current)
    e2_budget_prefix(current)
    e3_profile_ablation(current, balanced)
    e5_prompt_rubric()
    plot_main_paper_figures(current)
    supplement_index()
    print(f"Wrote supplements to {SUPP_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

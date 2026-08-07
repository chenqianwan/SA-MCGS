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
COST_AUDIT_RUNS = [
    {
        "model": "gpt-4o",
        "chart_prefix": "4o",
        "run_dir": DISCUSSION / "cost_audit_runs/clean_40case_gpt4o_b50_20260712",
    },
    {
        "model": "gemini-2.5-flash",
        "chart_prefix": "Flash",
        "run_dir": DISCUSSION / "cost_audit_runs/clean_40case_gemini25flash_b50_20260712",
    },
]
ADDITIONAL_MODEL_COST_RUNS = [
    {
        "group": "model=gemini-2.5-flash (cost audit)",
        "chart_label": "gemini-2.5-flash",
        "run_dir": DISCUSSION / "cost_audit_runs/clean_40case_gemini25flash_b50_20260712",
    }
]
DISPLAY_COST_METHODS = [
    "Full-SCC Naive, single attempt",
    "GraphRAG-style LEA",
    "SA-MCGS",
]


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


def pp(value: Any) -> str:
    number = fnum(value)
    return "NA" if number is None else f"{number * 100:+.1f} pp"


def table(headers: list[str], rows: list[list[Any]], class_name: str = "") -> str:
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    cls = f' class="{class_name}"' if class_name else ""
    return f"<div class=\"table-wrap\"><table{cls}><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def bilingual(en: str, zh: str) -> str:
    return f"{html.escape(en)}<span class=\"zh\">{html.escape(zh)}</span>"


def method_label(value: str) -> str:
    labels = {
        "Full-SCC Naive (single attempt)": "完整 SCC Naive（单次生成）",
        "Full-SCC Naive, single attempt": "完整 SCC Naive（单次生成）",
        "GraphRAG-style LEA": "图感知局部证据聚合（LEA）",
        "SA-MCGS": "SA-MCGS 主方法",
    }
    return bilingual(value, labels.get(value, value))


def short_method_label(value: str) -> str:
    labels = {
        "Full-SCC Naive (single attempt)": "Naive",
        "Full-SCC Naive, single attempt": "Naive",
        "GraphRAG-style LEA": "LEA",
        "SA-MCGS": "SA-MCGS",
    }
    return labels.get(value, value)


def variant_label(value: str) -> str:
    labels = {
        "Full SA-MCGS (locked main)": "完整 SA-MCGS（冻结主设置）",
        "No relation-first memory": "移除 relation-first memory",
        "No critical-pair ledger/revisit": "移除 critical-pair 记录与重访",
        "Random local-window selection": "随机选择局部窗口",
        "No OC/core signal": "移除 OC/core 信号",
        "Monotone core": "单调累积 core",
        "No pair closure in final core": "最终 core 不做 pair closure",
    }
    return bilingual(value, labels.get(value, value))


def group_label(value: str) -> str:
    labels = {
        "overall": "总体",
        "model=gpt-4o": "模型：gpt-4o",
        "model=gemini-2.5-pro": "模型：Gemini 2.5 Pro",
        "model=gemini-2.5-flash (cost audit)": "模型：Gemini 2.5 Flash（40-case 成本审计）",
        "model=deepseek-v3 (cost audit)": "模型：DeepSeek-V3（40-case 成本审计）",
        "model=qwen-turbo (cost audit)": "模型：Qwen Turbo（40-case 成本审计）",
        "scale=large>=21": "大 SCC（>=21）",
        "scale=medium13-20": "中等 SCC（13-20）",
        "scale=small<=12": "小 SCC（<=12）",
    }
    return bilingual(value, labels.get(value, value))


def cost_metric_blocks(rows: list[dict[str, str]]) -> str:
    method_names = {
        "Full-SCC Naive (single attempt)": "Naive",
        "Full-SCC Naive, single attempt": "Naive",
        "GraphRAG-style LEA": "LEA",
        "SA-MCGS": "SA-MCGS",
    }
    method_colors = {
        "Naive": "var(--blue)",
        "LEA": "var(--green)",
        "SA-MCGS": "var(--amber)",
    }
    metrics = [
        ("API calls / case", "每例 API 调用", "API calls / case", lambda v: num(v, 1)),
        ("Total tokens / case", "每例总 token", "Total tok. / case", intish),
        (
            "Runtime / case (low rollout)",
            "每例运行时间（低 rollout / 低并发）",
            "Runtime / case",
            lambda v: f"{num(v, 1)}s",
        ),
    ]

    blocks = []
    for en_label, zh_label, key, formatter in metrics:
        max_value = max((fnum(r[key]) or 0 for r in rows), default=1) or 1
        metric_rows = []
        for row in rows:
            method = method_names.get(row["Method"], row["Method"])
            value = fnum(row[key]) or 0
            width = max(2.0, min(100.0, value / max_value * 100.0)) if value else 0
            color = method_colors.get(method, "var(--teal)")
            metric_rows.append(
                "<div class=\"cost-row\">"
                f"<span class=\"cost-method\">{html.escape(method)}</span>"
                "<span class=\"cost-track\">"
                f"<span class=\"cost-fill\" style=\"width:{width:.1f}%; background:{color}\"></span>"
                "</span>"
                f"<span class=\"cost-value\">{formatter(row[key])}</span>"
                "</div>"
            )
        blocks.append(
            "<div class=\"cost-metric-block\">"
            f"<div class=\"cost-metric-title\">{html.escape(en_label)}<span class=\"zh\">{html.escape(zh_label)}</span></div>"
            + "".join(metric_rows)
            + "</div>"
        )

    return "".join(blocks)


def cost_parallel_formula() -> str:
    return """
      <div class="parallel-formula">
        <div class="formula-title">Parallelizable wall-clock model<span class="zh">可并行优化的 wall-clock 时间模型</span></div>
        <code>T_wall(c_parallel) ≈ T_serial + T_LLM / c_parallel<br>c_parallel = min(C_rollout, C_worker, C_api)</code>
        <p>Reported runtime uses a low-rollout / low-concurrency audit, so it is a conservative wall-clock measurement. Increasing the effective rollout concurrency c_parallel can shorten the parallel LLM-call portion by multiples, subject to worker and API-rate limits; token and call counts remain the accounting cost.</p>
        <p class="zh">这里报告的 runtime 来自低 rollout / 低并发审计，因此是偏保守的 wall-clock 时间。增大有效 rollout 并发参数 c_parallel，可以在 worker 和 API 速率限制内近似按倍数压缩可并行的 LLM 调用时间；token 与调用数仍然是实际成本核算口径。</p>
      </div>
    """


def cost_profile_panel(rows: list[dict[str, str]]) -> str:
    return "<div class=\"cost-profile-panel\">" + cost_metric_blocks(rows) + cost_parallel_formula() + "</div>"


def cost_audit_profile_panel(runs: list[dict[str, Any]]) -> str:
    blocks = []
    for run in runs:
        blocks.append(
            "<div class=\"cost-model-block\">"
            f"<div class=\"cost-model-title\">{html.escape(run['model'])}<span class=\"zh\">40-case 成本审计</span></div>"
            + cost_metric_blocks(run["overall_rows"])
            + "</div>"
        )
    return "<div class=\"cost-profile-panel\">" + "".join(blocks) + cost_parallel_formula() + "</div>"


def stage2_compare_panel(rows: list[dict[str, str]]) -> str:
    full = next(r for r in rows if r["Variant"] == "Full SA-MCGS (locked main)")
    variant_names = {
        "No OC/core signal": "No OC/core",
        "Monotone core": "Monotone",
        "No pair closure in final core": "No pair closure",
    }
    variant_zh = {
        "No OC/core signal": "移除 OC/core 信号",
        "Monotone core": "单调累积 core",
        "No pair closure in final core": "最终 core 不做 pair closure",
    }
    full_risk = fnum(full["Risk-all"]) or 0
    full_compression = fnum(full["Compression"]) or 0
    items = []
    for row in rows:
        if row is full:
            continue
        risk_delta = (fnum(row["Risk-all"]) or 0) - full_risk
        compression_delta = (fnum(row["Compression"]) or 0) - full_compression
        risk_class = "delta-bad" if risk_delta < -0.05 else "delta-warn" if risk_delta < 0 else "delta-good"
        compression_class = "delta-good" if compression_delta > 0.03 else "delta-neutral"
        items.append(
            "<div class=\"stage2-compare-row\">"
            "<div class=\"compare-name\">"
            f"<strong>{html.escape(variant_names.get(row['Variant'], row['Variant']))}</strong>"
            f"<span class=\"zh\">{html.escape(variant_zh.get(row['Variant'], row['Variant']))}</span>"
            "</div>"
            "<div class=\"compare-metric\">"
            f"<span>Risk-all</span><b>{pct(row['Risk-all'])}</b>"
            f"<em class=\"{risk_class}\">{pp(risk_delta)}</em>"
            "</div>"
            "<div class=\"compare-metric\">"
            f"<span>Compression</span><b>{pct(row['Compression'])}</b>"
            f"<em class=\"{compression_class}\">{pp(compression_delta)}</em>"
            "</div>"
            "</div>"
        )
    return (
        "<div class=\"stage2-compare-panel\">"
        "<div class=\"stage2-reference\">"
        "<strong>Full reference</strong><span class=\"zh\">完整 SA-MCGS 作为对照</span>"
        f"<span>Risk-all {pct(full['Risk-all'])}</span>"
        f"<span>Compression {pct(full['Compression'])}</span>"
        "</div>"
        + "".join(items)
        + "<p class=\"compare-note\">Each row reports the ablated variant and its point-change against Full SA-MCGS.<span class=\"zh\">每一行都是消融变体，并显式给出相对 Full SA-MCGS 的百分点变化。</span></p>"
        + "</div>"
    )


def load_completed_cost_model_row(config: dict[str, Any]) -> dict[str, Any] | None:
    run_dir = Path(config["run_dir"])
    status_path = run_dir / "status.json"
    summary_path = run_dir / "summary_cost_table.csv"
    if not status_path.exists() or not summary_path.exists():
        return None

    status = json.loads(status_path.read_text(encoding="utf-8"))
    if (
        status.get("completed_method_cases") != status.get("total_method_cases")
        or status.get("remaining_method_cases") != 0
    ):
        return None

    rows = read_csv(summary_path)
    overall = {r["Method"]: r for r in rows if r.get("Scale") == "Overall"}
    lea = overall.get("GraphRAG-style LEA")
    sa = overall.get("SA-MCGS")
    if lea is None or sa is None:
        return None

    lea_n = int(fnum(lea["Cases"]) or 0)
    sa_n = int(fnum(sa["Cases"]) or 0)
    return {
        "group": config["group"],
        "chart_label": config["chart_label"],
        "N": min(lea_n, sa_n),
        "LEA Root@3": fnum(lea["Root@3"]),
        "SA Root@3": fnum(sa["Root@3"]),
        "Delta Root@3": (fnum(sa["Root@3"]) or 0) - (fnum(lea["Root@3"]) or 0),
        "LEA Risk-all": fnum(lea["Risk-all"]),
        "SA Risk-all": fnum(sa["Risk-all"]),
        "Delta Risk-all": (fnum(sa["Risk-all"]) or 0) - (fnum(lea["Risk-all"]) or 0),
        "LEA Calls": fnum(lea["Calls / case"]),
        "SA Calls": fnum(sa["Calls / case"]),
    }


def load_completed_cost_model_rows() -> list[dict[str, Any]]:
    rows = []
    for config in ADDITIONAL_MODEL_COST_RUNS:
        row = load_completed_cost_model_row(config)
        if row:
            rows.append(row)
    return rows


def is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def method_case_stats(run_dir: Path) -> dict[str, dict[str, int]]:
    path = run_dir / "summary_method_cases.csv"
    if not path.exists():
        return {}
    stats: dict[str, dict[str, int]] = {}
    for row in read_csv(path):
        method = row.get("method", "")
        item = stats.setdefault(method, {"attempted": 0, "invalid": 0})
        item["attempted"] += 1
        if is_true(row.get("invalid_output")):
            item["invalid"] += 1
    if "naive-single" in stats:
        item = stats.setdefault("Full-SCC Naive, single attempt", {"attempted": 0, "invalid": 0})
        item["attempted"] += stats["naive-single"]["attempted"]
        item["invalid"] += stats["naive-single"]["invalid"]
    return stats


def load_completed_cost_audit_run(config: dict[str, Any]) -> dict[str, Any] | None:
    run_dir = Path(config["run_dir"])
    status_path = run_dir / "status.json"
    summary_path = run_dir / "summary_cost_table.csv"
    if not status_path.exists() or not summary_path.exists():
        return None

    status = json.loads(status_path.read_text(encoding="utf-8"))
    if (
        status.get("completed_method_cases") != status.get("total_method_cases")
        or status.get("remaining_method_cases") != 0
    ):
        return None

    stats = method_case_stats(run_dir)
    rows = []
    for row in read_csv(summary_path):
        if row.get("Scale") != "Overall" or row.get("Method") not in DISPLAY_COST_METHODS:
            continue
        method = row["Method"]
        row = dict(row)
        row["API calls / case"] = row.get("API calls / case") or row.get("Calls / case", "")
        row["Attempted cases"] = stats.get(method, {}).get("attempted", int(fnum(row.get("Cases")) or 0))
        row["Invalid cases"] = stats.get(method, {}).get("invalid", 0)
        row["Invalid rate"] = (
            row["Invalid cases"] / row["Attempted cases"] if row["Attempted cases"] else 0
        )
        rows.append(row)
    if len(rows) != len(DISPLAY_COST_METHODS):
        return None

    return {
        "model": config["model"],
        "chart_prefix": config["chart_prefix"],
        "run_dir": str(run_dir),
        "status": status,
        "overall_rows": rows,
    }


def load_completed_cost_audit_runs() -> list[dict[str, Any]]:
    rows = []
    for config in COST_AUDIT_RUNS:
        row = load_completed_cost_audit_run(config)
        if row:
            rows.append(row)
    return rows


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
    completed_cost_audit_runs = load_completed_cost_audit_runs()
    lea_summary_groups = [
        r
        for r in lea_rows
        if r["group"] in {"overall", "model=gpt-4o", "model=gemini-2.5-pro"}
    ]
    extra_cost_model_rows = load_completed_cost_model_rows()
    return {
        "cost_rows": cost_rows,
        "cost_overall": cost_overall,
        "completed_cost_audit_runs": completed_cost_audit_runs,
        "stage1_rows": stage1_rows,
        "stage1_bins": stage1_bins,
        "stage2_rows": stage2_rows,
        "lea_rows": lea_rows,
        "lea_summary_groups": lea_summary_groups,
        "lea_only": lea_only,
        "extra_cost_model_rows": extra_cost_model_rows,
    }


def build_tables(data: dict[str, Any]) -> dict[str, str]:
    completed_cost_runs = data.get("completed_cost_audit_runs") or []
    if completed_cost_runs:
        cost_table_rows = []
        for run in completed_cost_runs:
            for r in run["overall_rows"]:
                valid = int(fnum(r["Cases"]) or 0)
                attempted = int(r.get("Attempted cases") or valid)
                cost_table_rows.append(
                    [
                        html.escape(run["model"]),
                        method_label(r["Method"]),
                        f"{valid}/{attempted}",
                        pct(r["Invalid rate"]),
                        num(r["Calls / case"], 1),
                        intish(r["Input tok. / case"]),
                        intish(r["Output tok. / case"]),
                        intish(r["Total tok. / case"]),
                        f"{num(r['Runtime / case'], 1)}s",
                        pct(r["Root@3"]),
                        pct(r["Risk-any"]),
                        pct(r["Risk-all"]),
                        pct(r["Compression"]),
                    ]
                )
        cost_table = table(
            [
                "Model / 模型",
                "Method / 方法",
                "Valid/Total / 有效/总数",
                "Invalid / 无效",
                "Calls/case / 每例调用",
                "Input tok. / 输入 token",
                "Output tok. / 输出 token",
                "Total tok. / 总 token",
                "Runtime / 运行时间",
                "Root@3",
                "Risk-any",
                "Risk-all",
                "Compression / 压缩率",
            ],
            cost_table_rows,
        )
    else:
        cost_table = table(
            [
                "Method / 方法",
                "Cases / 案例数",
                "Invalid / 无效",
                "Calls/case / 每例调用",
                "Input tok. / 输入 token",
                "Output tok. / 输出 token",
                "Total tok. / 总 token",
                "Runtime / 运行时间",
                "Root@3",
                "Risk-any",
                "Risk-all",
                "Compression / 压缩率",
            ],
            [
                [
                    method_label(r["Method"]),
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
            "Variant / 变体",
            "N",
            "Root@3",
            "Risk-any",
            "Risk-all",
            "Compression / 压缩率",
            "Delta Risk-all / Risk-all 变化",
            "Avg core / 平均 core 大小",
        ],
        [
            [
                variant_label(r["Variant"]),
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
            "Variant / 变体",
            "N",
            "Root@3",
            "Risk-any",
            "Risk-all",
            "Compression / 压缩率",
            "Delta Risk-all / Risk-all 变化",
            "Avg core / 平均 core 大小",
        ],
        [
            [
                variant_label(r["Variant"]),
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
    lea_table_groups = [
        "overall",
        "model=gemini-2.5-pro",
        "model=gpt-4o",
        "scale=large>=21",
        "scale=medium13-20",
        "scale=small<=12",
    ]
    lea_table_rows = [r for r in data["lea_rows"] if r["group"] in lea_table_groups]
    if data.get("extra_cost_model_rows"):
        insert_at = next(
            (i + 1 for i, r in enumerate(lea_table_rows) if r["group"] == "model=gpt-4o"),
            min(3, len(lea_table_rows)),
        )
        for row in data["extra_cost_model_rows"]:
            lea_table_rows.insert(insert_at, row)
            insert_at += 1
    lea_table = table(
        [
            "Group / 分组",
            "N",
            "LEA Root@3",
            "SA Root@3",
            "Delta / 差值",
            "LEA Risk-all",
            "SA Risk-all",
            "Delta / 差值",
            "LEA calls / LEA 调用",
            "SA calls / SA 调用",
        ],
        [
            [
                group_label(r["group"]),
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
            for r in lea_table_rows
        ],
    )
    extra_model_note = ""
    if data.get("extra_cost_model_rows"):
        labels = ", ".join(
            html.escape(str(row["group"]).removeprefix("model=").replace(" (cost audit)", ""))
            for row in data["extra_cost_model_rows"]
        )
        extra_model_note = (
            f'<p class="note">{labels} are additional 40-case cost-audit slices and are not included in the matched 160-case overall.'
            f'<span class="zh">{labels} 是额外的 40 案例成本审计切片，不计入 matched 160-case overall。</span></p>'
        )

    claim_table = table(
        [
            "Reviewer concern / 审稿人关切",
            "New evidence / 新增证据",
            "Careful claim / 谨慎结论",
        ],
        [
            [
                bilingual("Cost accounting", "成本核算"),
                bilingual(
                    "Two completed 40-case low-rollout audits on gpt-4o and Gemini 2.5 Flash, with calls/tokens/runtime for Naive, LEA, and SA-MCGS.",
                    "已完成 gpt-4o 与 Gemini 2.5 Flash 两组 40 案例低 rollout 审计，记录 Naive、LEA 与 SA-MCGS 的调用数、token 和运行时间。",
                ),
                bilingual(
                    "Report cost-performance tradeoff by model and method; runtime is measured under low concurrency and can be reduced by parallel rollout.",
                    "按模型和方法报告成本-性能权衡；runtime 采用低并发测量，可通过并行 rollout 进一步缩短。",
                ),
            ],
            [
                bilingual("Component-level ablations", "组件级消融"),
                bilingual(
                    "Stage 1: 80 cases for search/memory modules. Stage 2: 40 dynamic cases for OC/core and final-core policies.",
                    "Stage 1 用 80 个案例分析搜索/记忆模块；Stage 2 用 40 个动态案例分析 OC/core 与最终 core 策略。",
                ),
                bilingual(
                    "Critical-pair ledger/revisit and dynamic core construction are the strongest supported modules; relation memory and pair closure should be framed cautiously.",
                    "证据最强的是 critical-pair 记录/重访和 dynamic core 构造；relation memory 与 pair closure 需要谨慎表述。",
                ),
            ],
            [
                bilingual("Baseline fairness", "Baseline 公平性"),
                bilingual(
                    "160 clean cases for GraphRAG-style LEA on gpt-4o and Gemini 2.5 Pro, matched against locked Full SA-MCGS.",
                    "在 gpt-4o 和 Gemini 2.5 Pro 上完成 160 个干净 LEA 案例，并与冻结的 Full SA-MCGS 匹配比较。",
                ),
                bilingual(
                    "LEA is competitive, especially on Gemini; SA-MCGS still improves endpoint completeness overall, with non-uniform model-level behavior.",
                    "LEA 很有竞争力，尤其在 Gemini 上；SA-MCGS 仍提升总体 endpoint completeness，但模型层面的表现并不均匀。",
                ),
            ],
        ],
    )

    return {
        "claim_table": claim_table,
        "cost_table": cost_table,
        "cost_profile_panel": (
            cost_audit_profile_panel(data["completed_cost_audit_runs"])
            if data.get("completed_cost_audit_runs")
            else cost_profile_panel(data["cost_overall"])
        ),
        "stage1_table": stage1_table,
        "stage2_table": stage2_table,
        "stage2_compare_panel": stage2_compare_panel(data["stage2_rows"]),
        "lea_table": lea_table,
        "lea_overall_note": (
            f"Matched 160-case overall: LEA Risk-all {pct(lea_overall['LEA Risk-all'])}, "
            f"SA-MCGS Risk-all {pct(lea_overall['SA Risk-all'])}, "
            f"delta {pct(lea_overall['Delta Risk-all'])}."
        ),
        "lea_extra_model_note": extra_model_note,
    }


def build_html(data: dict[str, Any], tables: dict[str, str]) -> str:
    model_rows = [
        {
            "model": r["group"].replace("model=", ""),
            "lea": fnum(r["LEA Risk-all"]),
            "sa": fnum(r["SA Risk-all"]),
        }
        for r in data["lea_rows"]
        if r["group"].startswith("model=")
    ]
    for row in data.get("extra_cost_model_rows", []):
        model_rows.append(
            {
                "model": row.get("chart_label") or str(row["group"]).replace("model=", ""),
                "lea": fnum(row["LEA Risk-all"]),
                "sa": fnum(row["SA Risk-all"]),
            }
        )
    if data.get("completed_cost_audit_runs"):
        cost_chart_rows = [
            {
                "method": f"{run['chart_prefix']}/{short_method_label(r['Method'])}",
                "calls": fnum(r["Calls / case"]),
                "tokens": fnum(r["Total tok. / case"]),
                "runtime": fnum(r["Runtime / case"]),
                "root": fnum(r["Root@3"]),
                "any": fnum(r["Risk-any"]),
                "all": fnum(r["Risk-all"]),
                "invalid": fnum(r["Invalid rate"]),
            }
            for run in data["completed_cost_audit_runs"]
            for r in run["overall_rows"]
        ]
    else:
        cost_chart_rows = [
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
        ]
    payload = {
        "costOverall": cost_chart_rows,
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
        "leaModels": model_rows,
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
    .cost-chart {{ min-height: 430px; }}
    .cost-profile-panel {{ display: grid; gap: 12px; }}
    .cost-model-block {{
      display: grid;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: rgba(35,117,109,.045);
    }}
    .cost-model-title {{
      font-size: 15px;
      font-weight: 800;
      color: var(--ink);
    }}
    .cost-metric-block {{
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 10px 12px;
      background: rgba(0,0,0,.012);
    }}
    .cost-metric-title {{
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 7px;
    }}
    .cost-row {{
      display: grid;
      grid-template-columns: 74px minmax(80px, 1fr) 92px;
      align-items: center;
      gap: 10px;
      margin: 6px 0;
    }}
    .cost-method {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .cost-track {{
      height: 14px;
      border-radius: 999px;
      background: #eef2ea;
      overflow: hidden;
      border: 1px solid var(--line);
    }}
    .cost-fill {{
      display: block;
      height: 100%;
      border-radius: 999px;
    }}
    .cost-value {{
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
      text-align: right;
      white-space: nowrap;
    }}
    .parallel-formula {{
      border-left: 4px solid var(--amber);
      background: #fbf4e7;
      border-radius: 7px;
      padding: 11px 12px;
      color: var(--ink);
    }}
    .formula-title {{ font-weight: 800; margin-bottom: 7px; }}
    .parallel-formula code {{
      display: block;
      padding: 8px 10px;
      border-radius: 6px;
      background: rgba(255,255,255,.74);
      border: 1px solid rgba(191,127,47,.28);
      color: var(--ink);
      font-size: 13px;
      line-height: 1.45;
      white-space: normal;
    }}
    .parallel-formula p {{
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }}
    .stage2-compare-panel {{ display: grid; gap: 10px; }}
    .stage2-reference {{
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      padding: 10px 12px;
      border-radius: 7px;
      background: var(--soft-teal);
      border: 1px solid rgba(35,117,109,.22);
      color: var(--ink);
    }}
    .stage2-reference strong {{ font-size: 14px; }}
    .stage2-reference span:not(.zh) {{
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }}
    .stage2-compare-row {{
      display: grid;
      grid-template-columns: minmax(130px, 1.2fr) minmax(120px, 1fr) minmax(120px, 1fr);
      gap: 10px;
      align-items: stretch;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: rgba(0,0,0,.012);
    }}
    .compare-name strong {{ display: block; font-size: 14px; }}
    .compare-metric {{
      display: grid;
      gap: 3px;
      padding-left: 10px;
      border-left: 1px solid var(--line);
    }}
    .compare-metric span {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .compare-metric b {{
      color: var(--ink);
      font-size: 20px;
      line-height: 1;
    }}
    .compare-metric em {{
      width: max-content;
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 12px;
      font-style: normal;
      font-weight: 800;
    }}
    .delta-bad {{ color: #8f2f2f; background: #f7e4e4; }}
    .delta-warn {{ color: #8a5a1e; background: #fbefd8; }}
    .delta-good {{ color: #17695f; background: #dff0ea; }}
    .delta-neutral {{ color: var(--muted); background: #edf1ea; }}
    .compare-note {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }}
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
    .zh {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.35;
      margin-top: 3px;
      font-weight: 500;
      white-space: normal;
    }}
    h2 .zh, h3 .zh, .chart-title .zh {{
      font-size: .72em;
      font-weight: 600;
    }}
    .metric b .zh {{
      display: inline;
      font-size: .54em;
      margin-left: 6px;
    }}
    @media (max-width: 980px) {{
      main {{ padding: 24px 14px 48px; }}
      header, .two-col, .summary-grid {{ grid-template-columns: 1fr; }}
      .stamp {{ text-align: left; }}
      h1 {{ font-size: 28px; }}
      .chart {{ min-height: 240px; }}
      .stage2-compare-row {{ grid-template-columns: 1fr; }}
      .compare-metric {{ border-left: 0; padding-left: 0; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>EMNLP 2026 Discussion 补充实验报告</h1>
        <p class="subhead">三个补充方向已经形成可展示证据：推理成本核算、组件级消融、以及 GraphRAG-style Local Evidence Aggregation baseline（图感知局部证据聚合基线）。页面只使用冻结记录中的数据。</p>
      </div>
      <div class="stamp">Updated / 更新<br>2026-07-13</div>
    </header>

    <section>
      <h2>Reviewer-facing Summary<span class="zh">面向审稿人的证据总览</span></h2>
      <div class="summary-grid">
        <div class="metric"><span>Cost audit<span class="zh">成本核算</span></span><b>2 × 40 cases <span class="zh">两组 40 案例</span></b><span>gpt-4o + Gemini Flash; Naive / LEA / SA-MCGS with tokens, calls, low-rollout runtime<span class="zh">gpt-4o 与 Gemini Flash；同时记录 token、调用数和低 rollout 运行时间</span></span></div>
        <div class="metric"><span>Component ablation<span class="zh">组件级消融</span></span><b>80 + 40</b><span>Stage 1 search modules + Stage 2 dynamic core modules<span class="zh">Stage 1 分析搜索/记忆模块，Stage 2 分析 dynamic core 模块</span></span></div>
        <div class="metric"><span>Graph-aware baseline<span class="zh">图感知 baseline</span></span><b>160 cases <span class="zh">160 个案例</span></b><span>Clean LEA run on gpt-4o and Gemini, matched to locked SA-MCGS<span class="zh">在 gpt-4o 和 Gemini 上运行 LEA，并与冻结的 SA-MCGS 匹配比较</span></span></div>
      </div>
      <div class="claim" style="margin-top:16px">{tables["claim_table"]}</div>
    </section>

    <section>
      <div class="two-col">
        <div>
          <h2>1. 推理成本与可靠性</h2>
          {tables["cost_table"]}
          <p class="note">Scope: completed low-rollout / low-concurrency 40-case audits on gpt-4o and Gemini 2.5 Flash. Qwen is still running and is not included in this version. Runtime is conservative wall-clock, not a fixed lower bound.<span class="zh">范围：已完成的 gpt-4o 与 Gemini 2.5 Flash 两组低 rollout / 低并发 40 案例审计。Qwen 仍在运行，本版本不纳入。runtime 是偏保守的 wall-clock，而不是固定下界。</span></p>
          <div class="callout">可以对 reviewer 说：我们会同时报告 performance 和 cost，包含 input/output tokens、API calls、runtime；其中 runtime 采用低 rollout 测得，可通过有效并发参数 c_parallel 进一步并行优化。当前表格只纳入已经完成的 gpt-4o 与 Gemini Flash。</div>
        </div>
        <div class="chart-grid">
          <div class="chart"><div class="chart-title">Performance by model and method<span class="zh">不同模型与方法的性能</span></div><div id="costPerf"></div></div>
          <div class="chart cost-chart"><div class="chart-title">Cost profile by model and method<span class="zh">不同模型与方法的调用、token 与低 rollout 时间</span></div>{tables["cost_profile_panel"]}</div>
        </div>
      </div>
    </section>

    <section>
      <div class="two-col">
        <div>
          <h2>2. 组件级消融</h2>
          <h3>Stage 1: search / memory modules, 80 cases<span class="zh">Stage 1：搜索/记忆模块，80 个案例</span></h3>
          {tables["stage1_table"]}
          <h3 style="margin-top:18px">Stage 2: dynamic core modules, 40 cases<span class="zh">Stage 2：dynamic core 模块，40 个案例</span></h3>
          {tables["stage2_table"]}
          <div class="callout">最强证据：critical-pair ledger/revisit 和 dynamic/replacement core。relation-first memory 接近 Full，pair closure 影响较小，应谨慎表述。</div>
        </div>
        <div class="chart-grid">
          <div class="chart"><div class="chart-title">Risk-all delta vs Full SA-MCGS<span class="zh">相对完整 SA-MCGS 的 Risk-all 变化</span></div><div id="ablationDelta"></div></div>
          <div class="chart"><div class="chart-title">Stage 2: ablations vs Full<span class="zh">Stage 2：相对 Full 的消融对比</span></div>{tables["stage2_compare_panel"]}</div>
          <div class="chart short"><div class="chart-title">Large SCC: Stage 1 Risk-all<span class="zh">大 SCC：Stage 1 的 Risk-all</span></div><div id="stage1Large"></div></div>
        </div>
      </div>
    </section>

    <section>
      <div class="two-col">
        <div>
          <h2>3. Graph-aware Decomposed Baseline<span class="zh">图感知分解式 Baseline</span></h2>
          {tables["lea_table"]}
          <p class="note">{html.escape(tables["lea_overall_note"])}<span class="zh">匹配的 160 个案例总体结果：LEA Risk-all 为 66.2%，SA-MCGS Risk-all 为 79.4%，差值为 13.1%。</span></p>
          {tables["lea_extra_model_note"]}
          <div class="callout">这张表非常适合回应 baseline fairness：LEA 很强，尤其 Gemini 上更强；SA-MCGS 的优势主要体现在 overall endpoint completeness / Risk-all，且 model-level non-uniformity 需要如实说明。</div>
        </div>
        <div class="chart-grid">
          <div class="chart"><div class="chart-title">Matched LEA vs Full SA-MCGS<span class="zh">匹配案例上的 LEA 与完整 SA-MCGS 对比</span></div><div id="leaMatched"></div></div>
          <div class="chart short"><div class="chart-title">Risk-all by model<span class="zh">不同模型上的 Risk-all</span></div><div id="leaModel"></div></div>
          <div class="chart short"><div class="chart-title">Calls/runtime tradeoff<span class="zh">调用数/运行时间权衡</span></div><div id="leaCost"></div></div>
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
    singleBars('stage1Large', DATA.stage1Large, 'riskAll', {{percent: true, max: 1, color: colors.teal, left: 180}});
    horizontalDelta('ablationDelta', [
      ...DATA.stage1.filter(r => r.variant !== 'Full').map(r => ({{...r, group: 'S1'}})),
      ...DATA.stage2.filter(r => r.variant !== 'Full').map(r => ({{...r, group: 'S2'}}))
    ]);
    dualBars('leaMatched', DATA.leaOverall, ['lea', 'sa'], {{labels: ['LEA', 'SA-MCGS'], percent: true, max: 1, height: 250}});
    dualBars('leaModel', DATA.leaModels, ['lea', 'sa'], {{labels: ['LEA', 'SA-MCGS'], percent: true, max: 1, height: 220}});
    groupedBars('leaCost', DATA.leaCost, ['calls'], ['Calls / case / 每例调用'], {{height: 210, colors: [colors.amber]}});
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

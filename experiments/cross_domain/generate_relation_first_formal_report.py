"""Generate the Chinese report for the relation-first SA-MCGS formal run."""
from __future__ import annotations

import argparse
import base64
import json
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np


RESULTS_DIR = Path(__file__).resolve().parent / "results"
FIGURE_DIR = RESULTS_DIR / "figures"
DEFAULT_PATTERN = (
    "battle_inject_memory_stress_handoff_invariant_directsubgraphnaive_"
    "relation_first_formal_relation_8to22_*.json"
)


def pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.0f}%"


def yn(value: bool | None) -> str:
    return "是" if value else "否"


def yn_en(value: bool | None) -> str:
    return "Y" if value else "N"


def avg(values: Iterable[float | int | None]) -> float:
    clean = [float(v) for v in values if v is not None]
    return mean(clean) if clean else 0.0


def hit_rate(rows: list[dict], key: str) -> float:
    return sum(bool(row.get(key)) for row in rows) / len(rows) if rows else 0.0


def coverage(nodes: Iterable[str], target_ids: Iterable[str]) -> float:
    target = set(target_ids or [])
    if not target:
        return 0.0
    return len(set(nodes or []) & target) / len(target)


def label_domain(domain: str) -> str:
    return {
        "debian": "Debian",
        "sec_ex21": "SEC EX-21",
        "bgb": "BGB",
        "cuad": "CUAD",
    }.get(domain, domain)


def latest_result() -> Path:
    candidates = [
        path for path in RESULTS_DIR.glob(DEFAULT_PATTERN)
        if not path.name.endswith(".partial.json")
    ]
    if not candidates:
        raise FileNotFoundError(f"No relation-first result found under {RESULTS_DIR}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


@dataclass
class Pair:
    key: tuple[str, str, int, str, str]
    domain: str
    model: str
    scc_id: str
    scc_size: int
    injected_node: str
    naive: dict
    sa: dict

    @property
    def risk_nodes(self) -> list[str]:
        return list(self.naive.get("injected_risk_nodes") or [])

    @property
    def valuable_nodes(self) -> list[str]:
        return list(dict.fromkeys(
            (self.naive.get("injected_risk_nodes") or [])
            + (self.naive.get("injected_affected_nodes") or [])
        ))

    @property
    def label(self) -> str:
        model = "4o" if self.model == "gpt-4o" else "DS"
        return f"{label_domain(self.domain)} {self.scc_size}n {model}"

    @property
    def naive_root_rank(self) -> int | None:
        return self.naive.get("root_rank")

    @property
    def sa_root_rank(self) -> int | None:
        return self.sa.get("root_rank")

    @property
    def root_rank_delta(self) -> int | None:
        if self.naive_root_rank is None or self.sa_root_rank is None:
            return None
        return int(self.naive_root_rank) - int(self.sa_root_rank)

    @property
    def naive_direct_nodes(self) -> list[str]:
        return list(self.naive.get("direct_risk_subgraph_nodes") or [])

    @property
    def sa_core_nodes(self) -> list[str]:
        return list(self.sa.get("core_evidence_risk_subgraph_nodes") or [])

    @property
    def naive_risk_coverage(self) -> float:
        return coverage(self.naive_direct_nodes, self.risk_nodes)

    @property
    def sa_risk_coverage(self) -> float:
        return float(self.sa.get("core_evidence_risk_coverage") or 0.0)

    @property
    def naive_valuable_coverage(self) -> float:
        return coverage(self.naive_direct_nodes, self.valuable_nodes)

    @property
    def sa_valuable_coverage(self) -> float:
        return float(self.sa.get("core_evidence_valuable_coverage") or 0.0)

    @property
    def effective_oc(self) -> bool:
        oc_nodes = set(self.sa.get("oc_detected") or [])
        return bool(oc_nodes & set(self.risk_nodes or []))


def load_rows(result_path: Path) -> list[dict]:
    return list(json.loads(result_path.read_text()))


def build_pairs(rows: list[dict]) -> list[Pair]:
    grouped: dict[tuple[str, str, int, str, str], dict[str, dict]] = defaultdict(dict)
    for row in rows:
        if row.get("error") or row.get("method") not in {"naive", "sa-mcgs"}:
            continue
        key = (
            row.get("domain"),
            row.get("scc_id"),
            int(row.get("scc_size") or 0),
            row.get("model"),
            row.get("injected_node"),
        )
        grouped[key][row["method"]] = row

    pairs = []
    for key, by_method in grouped.items():
        if "naive" not in by_method or "sa-mcgs" not in by_method:
            continue
        domain, scc_id, scc_size, model, injected_node = key
        pairs.append(Pair(
            key=key,
            domain=domain,
            model=model,
            scc_id=scc_id,
            scc_size=scc_size,
            injected_node=injected_node,
            naive=by_method["naive"],
            sa=by_method["sa-mcgs"],
        ))
    return sorted(pairs, key=lambda p: (p.domain, p.scc_size, p.scc_id, p.model))


def setup_matplotlib() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.titlesize": 18,
        "axes.labelsize": 15,
        "xtick.labelsize": 13,
        "ytick.labelsize": 13,
        "legend.fontsize": 13,
        "figure.titlesize": 22,
    })


def save_overall_chart(pairs: list[Pair], output: Path) -> None:
    setup_matplotlib()
    output.parent.mkdir(parents=True, exist_ok=True)

    naive_root3 = sum(bool(p.naive.get("root_top3_hit")) for p in pairs) / len(pairs)
    sa_root3 = sum(bool(p.sa.get("top3_hit")) for p in pairs) / len(pairs)
    naive_any = sum(bool(p.naive.get("direct_contains_any_risk_node")) for p in pairs) / len(pairs)
    sa_any = sum(bool(p.sa.get("core_evidence_contains_any_risk_node")) for p in pairs) / len(pairs)
    naive_all = sum(bool(p.naive.get("direct_contains_all_risk_nodes")) for p in pairs) / len(pairs)
    sa_all = sum(bool(p.sa.get("core_evidence_contains_all_risk_nodes")) for p in pairs) / len(pairs)
    naive_comp = avg(p.naive.get("direct_compression_ratio") for p in pairs)
    sa_comp = avg(p.sa.get("core_evidence_compression_ratio") for p in pairs)
    naive_effective_comp = avg(
        (p.naive.get("direct_compression_ratio") or 0.0) * p.naive_risk_coverage
        for p in pairs
    )
    sa_effective_comp = avg(
        (p.sa.get("core_evidence_compression_ratio") or 0.0) * p.sa_risk_coverage
        for p in pairs
    )
    naive_val = avg(p.naive_valuable_coverage for p in pairs)
    sa_val = avg(p.sa_valuable_coverage for p in pairs)
    effective_oc = sum(p.effective_oc for p in pairs) / len(pairs)

    fig = plt.figure(figsize=(17.5, 9.8), dpi=180)
    ax = fig.add_subplot(111)
    fig.patch.set_facecolor("#fbfbf8")
    metrics = [
        "Root@3",
        "Risk-any",
        "Risk-all",
        "Compression",
        "Effective\ncompression",
        "Valuable\ncoverage",
        "Effective OC",
    ]
    naive_values = [
        naive_root3,
        naive_any,
        naive_all,
        naive_comp,
        naive_effective_comp,
        naive_val,
        0.0,
    ]
    sa_values = [
        sa_root3,
        sa_any,
        sa_all,
        sa_comp,
        sa_effective_comp,
        sa_val,
        effective_oc,
    ]
    x = np.arange(len(metrics))
    width = 0.34
    red = "#d84a3a"
    green = "#087f5b"
    gray = "#9ca3af"
    ax.bar(x - width / 2, naive_values, width, color=[red, red, red, red, gray], label="Naive direct subgraph")
    ax.bar(x + width / 2, sa_values, width, color=green, label="SA-MCGS relation-first")
    for xpos, value in zip(x - width / 2, naive_values):
        label = "-" if xpos == x[-1] - width / 2 else pct(value)
        ax.text(xpos, min(value + 0.035, 1.05), label, ha="center", va="bottom", fontweight="bold")
    for xpos, value in zip(x + width / 2, sa_values):
        ax.text(xpos, min(value + 0.035, 1.05), pct(value), ha="center", va="bottom", fontweight="bold", color=green)
    ax.set_ylim(0, 1.12)
    ax.set_xticks(x, metrics)
    ax.set_ylabel("Rate / Coverage")
    ax.set_title("Overall matched comparison, 24 SCC-model pairs")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, loc="upper left")
    fig.text(
        0.5,
        0.04,
        "Effective compression = compression ratio x risk-node coverage. Effective OC = OC/conflict signal intersects the injected risk region.",
        ha="center",
        fontsize=14,
        color="#374151",
        fontweight="bold",
    )
    fig.tight_layout(rect=[0.03, 0.08, 0.98, 0.98])
    fig.savefig(output, facecolor=fig.get_facecolor())
    plt.close(fig)


def save_domain_chart(pairs: list[Pair], output: Path) -> None:
    setup_matplotlib()
    domains = ["debian", "sec_ex21", "bgb"]
    colors = {
        "naive": "#d84a3a",
        "sa": "#087f5b",
        "oc": "#2563eb",
    }
    fig, axes = plt.subplots(1, 3, figsize=(20, 7.5), dpi=180, sharey=True)
    fig.patch.set_facecolor("#fbfbf8")
    for ax, domain in zip(axes, domains):
        domain_pairs = [p for p in pairs if p.domain == domain]
        metrics = {
            "Root@3": (
                sum(bool(p.naive.get("root_top3_hit")) for p in domain_pairs) / len(domain_pairs),
                sum(bool(p.sa.get("top3_hit")) for p in domain_pairs) / len(domain_pairs),
            ),
            "Risk-any": (
                sum(bool(p.naive.get("direct_contains_any_risk_node")) for p in domain_pairs) / len(domain_pairs),
                sum(bool(p.sa.get("core_evidence_contains_any_risk_node")) for p in domain_pairs) / len(domain_pairs),
            ),
            "Risk-all": (
                sum(bool(p.naive.get("direct_contains_all_risk_nodes")) for p in domain_pairs) / len(domain_pairs),
                sum(bool(p.sa.get("core_evidence_contains_all_risk_nodes")) for p in domain_pairs) / len(domain_pairs),
            ),
            "Effective OC": (
                0.0,
                sum(p.effective_oc for p in domain_pairs) / len(domain_pairs),
            ),
        }
        x = np.arange(len(metrics))
        naive = [value[0] for value in metrics.values()]
        sa = [value[1] for value in metrics.values()]
        ax.bar(x - 0.18, naive, 0.36, color=colors["naive"], label="Naive")
        ax.bar(x + 0.18, sa, 0.36, color=[colors["sa"], colors["sa"], colors["sa"], colors["oc"]], label="SA-MCGS")
        for idx, value in enumerate(naive):
            label = "-" if idx == len(naive) - 1 else pct(value)
            ax.text(idx - 0.18, min(value + 0.035, 1.05), label, ha="center", fontweight="bold", fontsize=12)
        for idx, value in enumerate(sa):
            ax.text(idx + 0.18, min(value + 0.035, 1.05), pct(value), ha="center", fontweight="bold", fontsize=12)
        ax.set_title(f"{label_domain(domain)} (n={len(domain_pairs)})")
        ax.set_ylim(0, 1.12)
        ax.set_xticks(x, list(metrics.keys()), rotation=18, ha="right")
        ax.grid(axis="y", alpha=0.24)
    axes[0].set_ylabel("Rate")
    axes[0].legend(frameon=False, loc="upper left")
    fig.suptitle("By-domain signal: SA-MCGS gains are strongest on SEC and BGB root localization")
    fig.tight_layout(rect=[0.02, 0.02, 0.98, 0.93])
    fig.savefig(output, facecolor=fig.get_facecolor())
    plt.close(fig)


def save_rank_delta_chart(pairs: list[Pair], output: Path) -> None:
    setup_matplotlib()
    clean = [p for p in pairs if p.root_rank_delta is not None]
    clean.sort(key=lambda p: p.root_rank_delta or 0)
    fig, ax = plt.subplots(figsize=(17, 12), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    y = np.arange(len(clean))
    deltas = np.array([p.root_rank_delta or 0 for p in clean])
    colors = ["#087f5b" if d > 0 else "#d84a3a" if d < 0 else "#6b7280" for d in deltas]
    ax.barh(y, deltas, color=colors)
    labels = [p.label for p in clean]
    ax.set_yticks(y, labels)
    ax.axvline(0, color="#111827", linewidth=1)
    ax.set_xlabel("Naive root rank - SA root rank (positive = SA ranks root higher)")
    ax.set_title("Root localization shift by case")
    ax.grid(axis="x", alpha=0.25)
    for idx, pair in enumerate(clean):
        delta = pair.root_rank_delta or 0
        text = f"N:{pair.naive_root_rank}  SA:{pair.sa_root_rank}"
        ha = "left" if delta >= 0 else "right"
        x = delta + (0.2 if delta >= 0 else -0.2)
        ax.text(x, idx, text, va="center", ha=ha, fontsize=10, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output, facecolor=fig.get_facecolor())
    plt.close(fig)


def select_convergence_cases(pairs: list[Pair]) -> list[Pair]:
    wins = [
        p for p in pairs
        if bool(p.sa.get("top3_hit")) and not bool(p.naive.get("root_top3_hit"))
    ]
    wins.sort(key=lambda p: (
        p.domain != "sec_ex21",
        p.scc_size,
        p.model != "gpt-4o",
    ))
    failures = [
        p for p in pairs
        if p.domain == "bgb" and p.scc_size == 14
    ]
    selected = wins[:5] + failures[:1]
    dedup = []
    seen = set()
    for pair in selected:
        if pair.key not in seen and pair.sa.get("convergence_trace"):
            dedup.append(pair)
            seen.add(pair.key)
    return dedup[:6]


def save_convergence_chart(pairs: list[Pair], output: Path) -> None:
    setup_matplotlib()
    selected = select_convergence_cases(pairs)
    fig, axes = plt.subplots(2, 3, figsize=(20, 11.5), dpi=180, sharex=True, sharey=True)
    fig.patch.set_facecolor("#fbfbf8")
    axes = axes.ravel()
    for ax, pair in zip(axes, selected):
        trace = pair.sa.get("convergence_trace") or []
        rollouts = [int(row["rollout"]) for row in trace]
        risk_cov = [float(row.get("risk_coverage") or 0) for row in trace]
        val_cov = [float(row.get("valuable_coverage") or 0) for row in trace]
        ax.plot(rollouts, risk_cov, color="#2563eb", linewidth=2.6, marker="o", markersize=3, label="Risk coverage")
        ax.plot(rollouts, val_cov, color="#f59f00", linewidth=2.6, marker="o", markersize=3, label="Valuable coverage")
        first_all = pair.sa.get("first_subgraph_risk_all_rollout")
        first_any = pair.sa.get("first_subgraph_risk_any_rollout")
        if first_any:
            ax.axvline(first_any, color="#10b981", alpha=0.45, linewidth=1.8)
        if first_all:
            ax.axvline(first_all, color="#7c3aed", alpha=0.65, linewidth=2.2)
        title = (
            f"{pair.label}: N@3={yn_en(bool(pair.naive.get('root_top3_hit')))}, "
            f"SA@3={yn_en(bool(pair.sa.get('top3_hit')))}"
        )
        ax.set_title(title, fontsize=14)
        ax.set_ylim(-0.04, 1.06)
        ax.set_xlim(1, 30)
        ax.grid(alpha=0.22)
        ax.text(
            0.03,
            0.04,
            f"OC={pair.sa.get('oc_count') or 0}; final risk={pct(pair.sa.get('convergence_final_risk_coverage'))}",
            transform=ax.transAxes,
            fontsize=11,
            fontweight="bold",
            color="#374151",
        )
    for ax in axes[len(selected):]:
        ax.axis("off")
    axes[0].legend(frameon=False, loc="lower right")
    for ax in axes[::3]:
        ax.set_ylabel("Coverage")
    for ax in axes[-3:]:
        ax.set_xlabel("Rollout")
    fig.suptitle("Selected SA-MCGS convergence curves: rollout evidence accumulates the risk region")
    fig.tight_layout(rect=[0.02, 0.02, 0.98, 0.94])
    fig.savefig(output, facecolor=fig.get_facecolor())
    plt.close(fig)


def save_case_table(pairs: list[Pair], output: Path) -> None:
    setup_matplotlib()
    rows = []
    candidates = sorted(
        pairs,
        key=lambda p: (
            not (bool(p.sa.get("top3_hit")) and not bool(p.naive.get("root_top3_hit"))),
            -(p.root_rank_delta or 0),
            p.domain,
            p.scc_size,
        ),
    )[:12]
    for p in candidates:
        rows.append([
            label_domain(p.domain),
            f"{p.scc_size}",
            "4o" if p.model == "gpt-4o" else "DeepSeek",
            f"{p.naive_root_rank}",
            f"{p.sa_root_rank}",
            f"{yn_en(bool(p.naive.get('root_top3_hit')))} / {yn_en(bool(p.sa.get('top3_hit')))}",
            f"{yn_en(bool(p.naive.get('direct_contains_all_risk_nodes')))} / {yn_en(bool(p.sa.get('core_evidence_contains_all_risk_nodes')))}",
            f"{p.sa.get('oc_count') or 0}",
            pct(p.sa.get("core_evidence_compression_ratio")),
        ])

    fig, ax = plt.subplots(figsize=(20, 7.5), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.axis("off")
    table = ax.table(
        cellText=rows,
        colLabels=[
            "Domain",
            "Size",
            "Model",
            "Naive rank",
            "SA rank",
            "Root@3 N/SA",
            "Risk-all N/SA",
            "OC",
            "SA comp.",
        ],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1, 1.75)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#d1d5db")
        if row == 0:
            cell.set_facecolor("#111827")
            cell.set_text_props(color="white", weight="bold")
        elif col in {4, 5, 6, 7}:
            cell.set_facecolor("#ecfdf5")
    ax.set_title("Representative cases where rollout evidence changes the result", fontsize=20, fontweight="bold", pad=20)
    fig.tight_layout()
    fig.savefig(output, facecolor=fig.get_facecolor())
    plt.close(fig)


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def summary_rows_for_domain(pairs: list[Pair]) -> list[list[str]]:
    rows = []
    for domain in ["debian", "sec_ex21", "bgb"]:
        subset = [p for p in pairs if p.domain == domain]
        if not subset:
            continue
        rows.append([
            label_domain(domain),
            str(len(subset)),
            f"{sum(bool(p.naive.get('root_top3_hit')) for p in subset)}/{len(subset)}",
            f"{sum(bool(p.sa.get('top3_hit')) for p in subset)}/{len(subset)}",
            f"{sum(bool(p.naive.get('direct_contains_any_risk_node')) for p in subset)}/{len(subset)}",
            f"{sum(bool(p.sa.get('core_evidence_contains_any_risk_node')) for p in subset)}/{len(subset)}",
            f"{sum(bool(p.naive.get('direct_contains_all_risk_nodes')) for p in subset)}/{len(subset)}",
            f"{sum(bool(p.sa.get('core_evidence_contains_all_risk_nodes')) for p in subset)}/{len(subset)}",
            f"{sum((p.sa.get('oc_count') or 0) > 0 for p in subset)}/{len(subset)}",
            f"{sum(p.effective_oc for p in subset)}/{len(subset)}",
            pct(avg(p.sa.get("core_evidence_compression_ratio") for p in subset)),
        ])
    return rows


def top_case_rows(pairs: list[Pair]) -> list[list[str]]:
    selected = sorted(
        pairs,
        key=lambda p: (
            not (bool(p.sa.get("top3_hit")) and not bool(p.naive.get("root_top3_hit"))),
            -(p.root_rank_delta or 0),
        ),
    )[:10]
    rows = []
    for p in selected:
        rows.append([
            label_domain(p.domain),
            str(p.scc_size),
            p.model,
            str(p.naive_root_rank),
            str(p.sa_root_rank),
            "是" if bool(p.naive.get("root_top3_hit")) else "否",
            "是" if bool(p.sa.get("top3_hit")) else "否",
            f"{yn(bool(p.naive.get('direct_contains_all_risk_nodes')))} / {yn(bool(p.sa.get('core_evidence_contains_all_risk_nodes')))}",
            str(p.sa.get("oc_count") or 0),
            pct(p.sa.get("core_evidence_compression_ratio")),
        ])
    return rows


def write_report(result_path: Path, rows: list[dict], pairs: list[Pair], output: Path) -> None:
    figures = {
        "overall": FIGURE_DIR / "relation_first_main_metrics.png",
        "domain": FIGURE_DIR / "relation_first_domain_metrics.png",
        "delta": FIGURE_DIR / "relation_first_root_rank_delta.png",
        "convergence": FIGURE_DIR / "relation_first_convergence_selected.png",
        "cases": FIGURE_DIR / "relation_first_case_table.png",
    }
    md_figure_refs = {}
    for name, figure_path in figures.items():
        local_path = output.with_name(figure_path.name)
        if figure_path.resolve() != local_path.resolve():
            shutil.copyfile(figure_path, local_path)
        encoded = base64.b64encode(figure_path.read_bytes()).decode("ascii")
        md_figure_refs[name] = f"data:image/png;base64,{encoded}"

    valid_rows = [row for row in rows if not row.get("error")]
    skipped = [row for row in rows if row.get("error")]
    naive_rows = [p.naive for p in pairs]
    sa_rows = [p.sa for p in pairs]

    total = len(pairs)
    naive_root3 = sum(bool(row.get("root_top3_hit")) for row in naive_rows)
    sa_root3 = sum(bool(row.get("top3_hit")) for row in sa_rows)
    naive_any = sum(bool(row.get("direct_contains_any_risk_node")) for row in naive_rows)
    sa_any = sum(bool(row.get("core_evidence_contains_any_risk_node")) for row in sa_rows)
    naive_all = sum(bool(row.get("direct_contains_all_risk_nodes")) for row in naive_rows)
    sa_all = sum(bool(row.get("core_evidence_contains_all_risk_nodes")) for row in sa_rows)
    naive_comp = avg(row.get("direct_compression_ratio") for row in naive_rows)
    sa_comp = avg(row.get("core_evidence_compression_ratio") for row in sa_rows)
    naive_effective_comp = avg(
        (p.naive.get("direct_compression_ratio") or 0.0) * p.naive_risk_coverage
        for p in pairs
    )
    sa_effective_comp = avg(
        (p.sa.get("core_evidence_compression_ratio") or 0.0) * p.sa_risk_coverage
        for p in pairs
    )
    sa_oc = sum((row.get("oc_count") or 0) > 0 for row in sa_rows)
    sa_eff_oc = sum(p.effective_oc for p in pairs)
    sa_root_wins = sum(
        bool(p.sa.get("top3_hit")) and not bool(p.naive.get("root_top3_hit"))
        for p in pairs
    )
    naive_root_wins = sum(
        bool(p.naive.get("root_top3_hit")) and not bool(p.sa.get("top3_hit"))
        for p in pairs
    )

    md = []
    md.extend([
        "# Relation-First SA-MCGS 正式实验报告",
        "",
        f"- 结果文件：`{result_path.name}`",
        f"- 有效 matched case：`{total}` 组；原始有效实验记录：`{len(valid_rows)}` 条",
        "- 设置：`memory_stress` profile 内部版本为 `structural_simple_v1`；冲突模板 `handoff_invariant`；真实 SCC；SCC size 8-22；SA-MCGS budget=30；模型 `gpt-4o` 和 `deepseek-v3`。",
        "- Baseline：Naive 不是单点 rank，而是 `direct_subgraph`，即 one-shot LLM 直接输出完整风险子图。",
        "",
        "> **一句话结论：** Naive direct subgraph 已经很强，经常能找到一个可疑风险点；但 relation-first SA-MCGS 在 root Top-3、risk-all、OC/有效 OC 和 rollout 收敛证据上明显更像一个可解释搜索系统。尤其在 SEC 和 BGB 8-node case，SA-MCGS 能把 one-shot 漏掉的 root 拉回 Top-3，并输出可检查的风险子图。",
        "",
        "## 1. 总览",
        "",
        f"![Overall metrics]({md_figure_refs['overall']})",
        "",
        markdown_table(
            ["指标", "Naive direct subgraph", "SA-MCGS relation-first", "解读"],
            [
                ["Root@3", f"{naive_root3}/{total} ({pct(naive_root3 / total)})", f"{sa_root3}/{total} ({pct(sa_root3 / total)})", "SA 明显更容易把 GT/root 排进前三。"],
                ["Risk-any", f"{naive_any}/{total} ({pct(naive_any / total)})", f"{sa_any}/{total} ({pct(sa_any / total)})", "两者都能抓到风险气味，Naive 并不弱。"],
                ["Risk-all", f"{naive_all}/{total} ({pct(naive_all / total)})", f"{sa_all}/{total} ({pct(sa_all / total)})", "SA 更容易收齐 root+witness 这类风险端点。"],
                ["平均压缩率", pct(naive_comp), pct(sa_comp), "Naive 子图更小，但单看压缩率会奖励漏风险。"],
                ["有效压缩率", pct(naive_effective_comp), pct(sa_effective_comp), "`compression × risk coverage`；同时奖励压缩和风险覆盖，SA 更高。"],
                ["OC hit", "-", f"{sa_oc}/{total} ({pct(sa_oc / total)})", "Naive 没有 OC 机制；这是 SA 的结构化搜索信号。"],
                ["有效 OC", "-", f"{sa_eff_oc}/{total} ({pct(sa_eff_oc / total)})", "OC 节点与真实风险区相交，不只是噪声环。"],
                ["SA 新增胜场", "-", f"{sa_root_wins} 组", "Naive root@3 失败、SA root@3 成功。"],
                ["SA 丢失胜场", f"{naive_root_wins} 组", "-", "Naive root@3 成功、SA root@3 失败。"],
            ],
        ),
        "",
        "## 2. 分领域结果",
        "",
        f"![Domain metrics]({md_figure_refs['domain']})",
        "",
        markdown_table(
            [
                "领域",
                "matched case",
                "Naive Root@3",
                "SA Root@3",
                "Naive risk-any",
                "SA risk-any",
                "Naive risk-all",
                "SA risk-all",
                "SA OC",
                "SA 有效 OC",
                "SA 平均压缩率",
            ],
            summary_rows_for_domain(pairs),
        ),
        "",
        "解释：Debian 样本少但 SA 有稳定增益；SEC 是当前最重要的泛化补充，Naive 常能抓到一个风险点，但 SA 在 root 定位、risk-all 和 OC 上更强；BGB 只有 8/14 两个真实 SCC，8-node 很漂亮，14-node 是困难 case，需要后续扩大法律数据集来确认。",
        "",
        "## 3. Root 排名变化",
        "",
        f"![Root rank delta]({md_figure_refs['delta']})",
        "",
        "这张图读法：横轴是 `Naive root rank - SA root rank`，越往右说明 SA 把 root 排得越靠前。左侧负值表示 SA 排名更差。报告中不能只看 Top-k，还要看 rank delta，因为它体现 rollout 证据是否真的把注意力往正确节点收敛。",
        "",
        "## 4. 代表性 case",
        "",
        f"![Representative cases]({md_figure_refs['cases']})",
        "",
        markdown_table(
            ["领域", "SCC size", "模型", "Naive root rank", "SA root rank", "Naive Root@3", "SA Root@3", "Risk-all N/SA", "SA OC", "SA 压缩率"],
            top_case_rows(pairs),
        ),
        "",
        "## 5. Rollout 收敛曲线",
        "",
        f"![Convergence curves]({md_figure_refs['convergence']})",
        "",
        "蓝线是 risk-node coverage，橙线是 valuable-region coverage。绿色竖线表示第一次至少保住一个风险端点，紫色竖线表示第一次收齐全部风险端点。这里可以看到 SA-MCGS 的主要优势不是一次性猜中，而是在 rollout 中把局部证据、冲突边、repair entry 和 OC signal 累积到风险子图里。",
        "",
        "## 6. 需要诚实写进论文的边界",
        "",
        "- **Naive direct subgraph 很强。** 这次 baseline 已经不是弱 baseline，它直接输出风险子图；因此论文主张不能写成“Naive 完全看不见风险”。更准确的说法是：Naive 能发现可疑点，但缺少 OC 与 rollout evidence 的可解释收敛机制。",
        "- **BGB 14-node 是困难 case。** 两个模型下 SA root@3 都失败，core evidence risk-any 也没有稳定覆盖到风险端点；但 deepseek-v3 有 OC=2，说明有结构信号，只是最终 evidence aggregation 没有收好。",
        "- **CUAD 本地数据缺失。** 当前 run 只验证了 Debian、SEC EX-21、BGB；CUAD 需要补数据后再跑，不能在当前报告中声称 CUAD 泛化。",
        "- **SEC 的风险扩散现象值得保留。** 很多 SEC case 中，Naive 和 SA 都会抓到受影响节点而不是 root，这不一定是失败；它支持“风险子图/修复入口”比单点 GT 更合理。",
        "",
        "## 7. 下一步实验 Todo",
        "",
        "1. 补齐 CUAD 数据，优先跑 8-22 SCC，同样用 direct-subgraph Naive 做强 baseline。",
        "2. 对 BGB 增加更多真实 SCC 或构造不新增节点的真实条文子环，重点补 10-24 节点范围。",
        "3. 对 relation-first 做 ablation：`relation_first` vs `pair_memory` vs `off`，固定同一批 SCC，验证新增的 AMAF/RAVE-style relation memory 不是偶然收益。",
        "4. 针对 BGB 14-node 失败 case 做现场分析：检查注入 root/witness/bridge 的文本位置、LLM 局部窗口是否看到关键链路、final core evidence 为什么丢掉风险端点。",
        "5. 论文主结果优先汇报：Root@3、Risk-any、Risk-all、有效 OC、风险子图压缩率、rollout 收敛曲线。Top-1 只作为辅助指标。",
        "",
    ])

    if skipped:
        md.extend([
            "## 附：跳过记录",
            "",
            markdown_table(
                ["domain", "reason"],
                [[row.get("domain") or "-", str(row.get("error") or "-")] for row in skipped],
            ),
            "",
        ])

    output.write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "RELATION_FIRST_FORMAL_REPORT.md")
    args = parser.parse_args()

    result_path = args.input or latest_result()
    rows = load_rows(result_path)
    pairs = build_pairs(rows)
    if not pairs:
        raise RuntimeError("No matched naive/SA-MCGS pairs found")

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    save_overall_chart(pairs, FIGURE_DIR / "relation_first_main_metrics.png")
    save_domain_chart(pairs, FIGURE_DIR / "relation_first_domain_metrics.png")
    save_rank_delta_chart(pairs, FIGURE_DIR / "relation_first_root_rank_delta.png")
    save_convergence_chart(pairs, FIGURE_DIR / "relation_first_convergence_selected.png")
    save_case_table(pairs, FIGURE_DIR / "relation_first_case_table.png")
    write_report(result_path, rows, pairs, args.output)
    print(args.output)


if __name__ == "__main__":
    main()

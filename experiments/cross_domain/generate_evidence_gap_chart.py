"""Generate an intuitive comparison chart for SA-MCGS evidence subgraphs."""
from __future__ import annotations

import argparse
import base64
import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def intersect_count(left: list[str], right: list[str]) -> int:
    return len(set(left or []) & set(right or []))


def coverage(nodes: list[str], ids: list[str]) -> float:
    return intersect_count(nodes, ids) / len(ids) if ids else np.nan


def pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def build_pairs(rows: list[dict]) -> list[dict]:
    rows = [row for row in rows if not row.get("error")]
    pairs = []
    for idx in range(0, len(rows), 2):
        naive = rows[idx]
        sa = rows[idx + 1]
        risk_ids = naive.get("injected_risk_nodes") or []
        valuable_ids = list(dict.fromkeys(
            (naive.get("injected_risk_nodes") or [])
            + (naive.get("injected_affected_nodes") or [])
        ))
        domain = naive["domain"].replace("sec_ex21", "SEC").replace("debian", "Debian")
        pairs.append({
            "label": f"{domain}\n{naive['scc_size']}n",
            "domain": naive["domain"],
            "size": naive["scc_size"],
            "naive_risk_cov": coverage(
                naive.get("direct_risk_subgraph_nodes") or [],
                risk_ids,
            ),
            "naive_val_cov": coverage(
                naive.get("direct_risk_subgraph_nodes") or [],
                valuable_ids,
            ),
            "sa_risk_cov": sa.get("core_evidence_risk_coverage"),
            "sa_val_cov": sa.get("core_evidence_valuable_coverage"),
            "naive_all": bool(naive.get("direct_contains_all_risk_nodes")),
            "sa_all": bool(sa.get("core_evidence_contains_all_risk_nodes")),
            "naive_any": bool(naive.get("direct_contains_any_risk_node")),
            "sa_any": bool(sa.get("core_evidence_contains_any_risk_node")),
            "naive_comp": naive.get("direct_compression_ratio", np.nan),
            "sa_comp": sa.get("core_evidence_compression_ratio", np.nan),
            "sa_oc": sa.get("oc_count", 0),
        })
    return pairs


def generate_chart(result_path: Path, output_path: Path) -> None:
    pairs = build_pairs(json.loads(result_path.read_text()))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    naive_risk = np.array([p["naive_risk_cov"] for p in pairs])
    sa_risk = np.array([p["sa_risk_cov"] for p in pairs])
    naive_val = np.array([p["naive_val_cov"] for p in pairs])
    sa_val = np.array([p["sa_val_cov"] for p in pairs])
    naive_comp = np.array([p["naive_comp"] for p in pairs])
    sa_comp = np.array([p["sa_comp"] for p in pairs])

    summary = {
        "Risk coverage": [np.nanmean(naive_risk), np.nanmean(sa_risk)],
        "Valuable coverage": [np.nanmean(naive_val), np.nanmean(sa_val)],
        "Risk-all hit": [
            np.mean([p["naive_all"] for p in pairs]),
            np.mean([p["sa_all"] for p in pairs]),
        ],
        "Compression": [np.nanmean(naive_comp), np.nanmean(sa_comp)],
    }

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.titlesize": 15,
        "axes.labelsize": 13,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 12,
    })

    fig = plt.figure(figsize=(18, 12), dpi=180)
    grid = fig.add_gridspec(
        2,
        2,
        width_ratios=[1, 1.45],
        height_ratios=[1, 1],
        wspace=0.22,
        hspace=0.48,
    )
    fig.patch.set_facecolor("#fbfbf8")
    fig.subplots_adjust(left=0.06, right=0.985, top=0.86, bottom=0.1)

    red = "#d84a3a"
    green = "#087f5b"
    orange = "#f59f00"
    blue = "#2563eb"

    ax1 = fig.add_subplot(grid[0, 0])
    metrics = list(summary.keys())
    x = np.arange(len(metrics))
    width = 0.36
    naive_values = [summary[metric][0] for metric in metrics]
    sa_values = [summary[metric][1] for metric in metrics]
    ax1.bar(x - width / 2, naive_values, width=width, color=red, label="Naive direct subgraph")
    ax1.bar(x + width / 2, sa_values, width=width, color=green, label="SA-MCGS core evidence")
    for xpos, value in zip(x - width / 2, naive_values):
        ax1.text(xpos, value + 0.025, pct(value), ha="center", fontweight="bold", color=red)
    for xpos, value in zip(x + width / 2, sa_values):
        ax1.text(xpos, value + 0.025, pct(value), ha="center", fontweight="bold", color=green)
    ax1.set_ylim(0, 1.12)
    ax1.set_xticks(x, metrics, rotation=15, ha="right")
    ax1.set_ylabel("Rate")
    ax1.set_title("Average Metrics")
    ax1.grid(axis="y", alpha=0.22)
    ax1.legend(frameon=False, loc="upper right")

    ax2 = fig.add_subplot(grid[0, 1])
    labels = [p["label"] for p in pairs]
    case_x = np.arange(len(pairs))
    risk_delta = sa_risk - naive_risk
    val_delta = sa_val - naive_val
    ax2.axhline(0, color="#111827", linewidth=1)
    ax2.bar(case_x - 0.18, risk_delta, width=0.35, color=blue, label="Risk coverage gain")
    ax2.bar(case_x + 0.18, val_delta, width=0.35, color=orange, label="Valuable coverage gain")
    for idx, (risk_gain, val_gain) in enumerate(zip(risk_delta, val_delta)):
        ax2.text(idx - 0.18, risk_gain + 0.025, f"{risk_gain * 100:+.0f}%", ha="center", fontweight="bold", color=blue)
        ax2.text(idx + 0.18, val_gain + 0.025, f"{val_gain * 100:+.0f}%", ha="center", fontweight="bold", color=orange)
    ax2.set_ylim(-0.12, 0.82)
    ax2.set_xticks(case_x, labels)
    ax2.set_ylabel("SA-MCGS minus Naive")
    ax2.set_title("Case-by-case Gain (SA-MCGS minus Naive)")
    ax2.grid(axis="y", alpha=0.22)
    ax2.legend(frameon=False, loc="upper right")

    ax3 = fig.add_subplot(grid[1, 0])
    values = [
        sum(p["naive_any"] for p in pairs) / len(pairs),
        sum(p["sa_any"] for p in pairs) / len(pairs),
        sum(p["naive_all"] for p in pairs) / len(pairs),
        sum(p["sa_all"] for p in pairs) / len(pairs),
    ]
    names = ["Naive\nrisk-any", "SA\nrisk-any", "Naive\nrisk-all", "SA\nrisk-all"]
    colors = [red, green, "#e58b84", "#7b4ab8"]
    ax3.bar(np.arange(4), values, color=colors, width=0.62)
    for idx, value in enumerate(values):
        ax3.text(idx, value + 0.03, f"{round(value * len(pairs))}/{len(pairs)}", ha="center", fontweight="bold")
    ax3.set_ylim(0, 1.12)
    ax3.set_xticks(np.arange(4), names)
    ax3.set_ylabel("Hit rate")
    ax3.set_title("Risk Endpoint Completeness")
    ax3.grid(axis="y", alpha=0.22)

    ax4 = fig.add_subplot(grid[1, 1])
    ax4.scatter(naive_comp, naive_val, s=180, color=red, alpha=0.78, label="Naive direct", edgecolor="white", linewidth=1.4)
    ax4.scatter(sa_comp, sa_val, s=180, color=green, alpha=0.85, label="SA-MCGS core", edgecolor="white", linewidth=1.4)
    for idx, pair in enumerate(pairs):
        ax4.plot([naive_comp[idx], sa_comp[idx]], [naive_val[idx], sa_val[idx]], color="#9ca3af", alpha=0.55, linewidth=1.2)
        ax4.text(sa_comp[idx] + 0.012, sa_val[idx] + 0.012, f"{pair['size']}n", fontsize=9, color=green, fontweight="bold")
    ax4.set_xlim(0.36, 0.86)
    ax4.set_ylim(0.18, 1.08)
    ax4.set_xlabel("Compression ratio (higher = smaller subgraph)")
    ax4.set_ylabel("Valuable-region coverage")
    ax4.set_title("Coverage vs. Compression")
    ax4.grid(alpha=0.22)
    ax4.legend(frameon=False, loc="lower left")

    fig.suptitle(
        "Naive Direct Subgraph vs SA-MCGS Evidence Subgraph (8 matched SCC cases, budget=30)",
        fontsize=20,
        fontweight="bold",
        y=0.965,
    )
    fig.text(
        0.5,
        0.925,
        "SA-MCGS keeps a slightly larger subgraph, but it preserves far more of the actual risk region.",
        ha="center",
        fontsize=14,
        color="#374151",
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.03,
        "Takeaway: Naive often finds one suspicious endpoint; SA-MCGS accumulates rollout evidence into a more complete risk region.",
        ha="center",
        fontsize=13,
        color="#374151",
        fontweight="bold",
    )
    fig.savefig(output_path, facecolor=fig.get_facecolor())
    plt.close(fig)


def write_explained_markdown(output_path: Path, md_path: Path, embed_image: bool = True) -> None:
    md_image_path = md_path.with_name(output_path.name)
    if output_path.resolve() != md_image_path.resolve():
        shutil.copyfile(output_path, md_image_path)
    if embed_image:
        encoded = base64.b64encode(output_path.read_bytes()).decode("ascii")
        image_ref = f"data:image/png;base64,{encoded}"
    else:
        image_ref = f"./{md_image_path.name}"
    md_path.write_text(
        "\n".join([
            "# Evidence Subgraph Gap 图解",
            "",
            f"![Evidence subgraph gap]({image_ref})",
            "",
            f"图片文件：[{md_image_path.name}]({image_ref})",
            "",
            "## 参数名解释",
            "",
            "| 图中参数 | 含义 | 读法 |",
            "|---|---|---|",
            "| `Naive direct subgraph` | one-shot LLM 直接读取整个 SCC 后输出的 `risk_subgraph_nodes`。 | 这是最强 Naive baseline，不只是单点 rank，而是让 LLM 直接给风险子图。 |",
            "| `SA-MCGS core evidence` | SA-MCGS 在多轮 rollout 中累积局部风险、冲突边、repair entry、OC signal 后生成的盲风险子图。 | 不使用 GT，不手动加入 root/witness，是算法自己的 evidence aggregation 输出。 |",
            "| `SCC case` / `matched SCC case` | 同一个强连通分量、同一次注入、同一个模型下，比较 Naive 和 SA-MCGS。 | 图里共有 8 个 matched cases。 |",
            "| `budget=30` | 每个 SCC 的 SA-MCGS rollout 预算。 | 不是实际 LLM call 数；TT 命中会减少真实 API 调用。 |",
            "| `7n` / `11n` / `18n` | SCC 的节点数量。 | `18n` 表示这个环里有 18 个节点。 |",
            "| `Risk node` | 注入结构性冲突中最核心的风险端点。 | 当前实验里通常包括 root/GT 节点和 witness 节点。 |",
            "| `Affected node` | 被结构性冲突影响、也可能成为有效修复入口的节点。 | SEC 这类风险扩散场景里尤其重要。 |",
            "| `Valuable node` | `Risk node + Affected node` 的合集。 | 表示“值得被风险子图保留下来”的节点，不只限于 GT/root。 |",
            "| `Risk coverage` | 输出子图覆盖了多少比例的 risk nodes。 | 公式：`covered risk nodes / all risk nodes`，越高越好。 |",
            "| `Valuable coverage` | 输出子图覆盖了多少比例的 valuable nodes。 | 公式：`covered valuable nodes / all valuable nodes`，越高说明风险区域收得更完整。 |",
            "| `Risk-any` | 输出子图至少包含一个 risk node。 | 这是宽松指标，说明模型至少抓到一个风险入口。 |",
            "| `Risk-all` / `Risk-all hit` | 输出子图包含所有 risk nodes。 | 这是严格指标，说明模型把冲突两端都收齐了。 |",
            "| `Compression` / `Compression ratio` | 子图相对原 SCC 的压缩率。 | 公式：`1 - subgraph_size / SCC_size`；越高表示子图越小，但过高可能漏风险。 |",
            "| `Risk coverage gain` | SA-MCGS 的 risk coverage 减去 Naive 的 risk coverage。 | 大于 0 表示 SA-MCGS 在该 case 覆盖了更多核心风险节点。 |",
            "| `Valuable coverage gain` | SA-MCGS 的 valuable coverage 减去 Naive 的 valuable coverage。 | 大于 0 表示 SA-MCGS 把更多受影响/可修复风险区域收进来了。 |",
            "| `SA-MCGS minus Naive` | 逐 case 的差值。 | 右上图里蓝色/橙色柱子越高，说明 SA-MCGS 相对 Naive 的增益越大。 |",
            "| `Coverage vs. Compression` | 同时看覆盖率和压缩率的 tradeoff。 | 右下图里点越靠上表示覆盖越好，越靠右表示子图越小。 |",
            "",
            "## 一句话读图",
            "",
            "Naive direct subgraph 往往能找到一个可疑端点，但经常没有收齐完整风险区域；SA-MCGS core evidence 子图通常稍大一点，因此压缩率低一些，但能显著提升 `risk coverage`、`valuable coverage` 和 `risk-all`。",
            "",
        ]),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_path", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("--md-path", type=Path, default=None)
    parser.add_argument(
        "--link-image",
        action="store_true",
        help="Use a local image link instead of embedding the PNG as a data URI.",
    )
    args = parser.parse_args()
    generate_chart(args.result_path, args.output_path)
    md_path = args.md_path or args.output_path.with_name(f"{args.output_path.stem}_explained.md")
    write_explained_markdown(args.output_path, md_path, embed_image=not args.link_image)
    print(args.output_path)
    print(md_path)


if __name__ == "__main__":
    main()

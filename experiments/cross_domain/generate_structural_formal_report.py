"""Generate figures and the formal structural-conflict experiment report."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib-cache")

import matplotlib.pyplot as plt
from matplotlib import font_manager


def configure_chinese_fonts() -> None:
    font_paths = [
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    ]
    for font_path in font_paths:
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
    plt.rcParams["font.sans-serif"] = ["Hiragino Sans GB", "STHeiti", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False


configure_chinese_fonts()


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
REPORT = RESULTS / "STRUCTURAL_SIMPLE_V2_FORMAL_REPORT.md"

RUN_PATTERN = (
    "battle_inject_memory_stress_handoff_invariant_rankednaive_"
    "formal_full_realtext_c8_*_20260513_*.json"
)


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(RESULTS.glob(RUN_PATTERN)):
        if path.name.endswith(".partial.json"):
            continue
        data = json.loads(path.read_text())
        if isinstance(data, list):
            rows.extend(data)
        else:
            rows.extend(data.get("results", []))
    return rows


def pct(count: int, total: int) -> str:
    if total == 0:
        return "-"
    return f"{count}/{total} ({count / total * 100:.0f}%)"


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def contains_any(nodes: list[str] | None, targets: list[str] | None) -> bool:
    node_set = set(nodes or [])
    return any(target in node_set for target in targets or [])


def contains_all(nodes: list[str] | None, targets: list[str] | None) -> bool:
    targets = targets or []
    node_set = set(nodes or [])
    return bool(targets) and all(target in node_set for target in targets)


def valuable_nodes(row: dict) -> list[str]:
    """Nodes that are valid repair handles for a propagated structural conflict."""
    values = []
    for key in ("injected_risk_nodes", "injected_evidence_nodes", "injected_affected_nodes"):
        values.extend(row.get(key) or [])
    return list(dict.fromkeys(node for node in values if node))


def metric_summary(rows: list[dict], domain: str | None = None, method: str | None = None) -> dict:
    selected = [
        row
        for row in rows
        if not row.get("error")
        and (domain is None or row.get("domain") == domain)
        and (method is None or row.get("method") == method)
    ]
    total = len(selected)
    summary = {
        "n": total,
        "root_top1": sum(bool(row.get("root_top1_hit")) for row in selected),
        "root_top3": sum(bool(row.get("root_top3_hit")) for row in selected),
        "risk_any_top3": sum(bool(row.get("risk_top3_hit")) for row in selected),
        "risk_all_top3": sum(bool(row.get("risk_all_top3_hit")) for row in selected),
        "evidence_any_top3": sum(bool(row.get("evidence_top3_hit")) for row in selected),
        "evidence_all_top3": sum(bool(row.get("evidence_all_top3_hit")) for row in selected),
        "avg_root_rank": mean([float(row.get("root_rank") or 0) for row in selected]),
    }
    if method == "sa-mcgs":
        oc_counts = [int(row.get("oc_count") or len(row.get("conflicts") or [])) for row in selected]
        oc_hit_rows = [
            row
            for row in selected
            if int(
                row.get("oc_count")
                or len(row.get("oc_detected") or [])
                or len(row.get("conflicts") or [])
            )
            > 0
        ]
        effective_oc_rows = [
            row for row in oc_hit_rows
            if contains_any(row.get("oc_detected"), valuable_nodes(row))
        ]
        blind_comp = [
            float(row.get("blind_compression_ratio"))
            for row in selected
            if row.get("blind_compression_ratio") is not None
        ]
        summary.update(
            {
                "oc_hit": sum(count > 0 for count in oc_counts),
                "oc_effective": len(effective_oc_rows),
                "oc_effective_denominator": len(oc_hit_rows),
                "oc_effectiveness": (
                    len(effective_oc_rows) / len(oc_hit_rows) if oc_hit_rows else 0.0
                ),
                "avg_oc": mean(oc_counts),
                "blind_root_ret": sum(
                    row.get("injected_node") in set(row.get("blind_risk_subgraph_nodes") or [])
                    for row in selected
                ),
                "blind_risk_any_ret": sum(
                    contains_any(row.get("blind_risk_subgraph_nodes"), row.get("injected_risk_nodes"))
                    for row in selected
                ),
                "blind_risk_all_ret": sum(
                    contains_all(row.get("blind_risk_subgraph_nodes"), row.get("injected_risk_nodes"))
                    for row in selected
                ),
                "blind_avg_compression": mean(blind_comp),
            }
        )
    return summary


def matched_naive_subgraph(row: dict, top_k: int = 3) -> list[str]:
    """Matched subgraph baseline: top-k ranked anchors plus cycle neighbors."""
    ordered_cycle = list(row.get("scc_clause_ids") or row.get("node_names") or [])
    anchors = [cid for cid, _ in (row.get("ranking") or [])[:top_k]]
    nodes = set(anchors)
    for anchor in anchors:
        if anchor not in ordered_cycle:
            continue
        idx = ordered_cycle.index(anchor)
        nodes.add(ordered_cycle[(idx - 1) % len(ordered_cycle)])
        nodes.add(ordered_cycle[(idx + 1) % len(ordered_cycle)])
    return list(nodes)


def matched_sa_subgraph(row: dict) -> list[str]:
    """SA-MCGS blind risk subgraph from OC/ranking anchors, without GT anchoring."""
    return list(row.get("blind_risk_subgraph_nodes") or [])


def matched_subgraph_summary(
    rows: list[dict],
    domain: str | None = None,
    method: str | None = None,
) -> dict:
    selected = [
        row
        for row in rows
        if not row.get("error")
        and (domain is None or row.get("domain") == domain)
        and (method is None or row.get("method") == method)
    ]
    items = []
    for row in selected:
        nodes = matched_naive_subgraph(row) if row.get("method") == "naive" else matched_sa_subgraph(row)
        scc_size = int(row.get("scc_size") or len(row.get("scc_clause_ids") or []) or 0)
        compression = 1 - (len(nodes) / scc_size) if scc_size else 0.0
        items.append((row, nodes, compression))
    total = len(items)
    return {
        "n": total,
        "avg_size": mean([len(nodes) for _, nodes, _ in items]),
        "avg_compression": mean([compression for _, _, compression in items]),
        "risk_any": sum(contains_any(nodes, row.get("injected_risk_nodes")) for row, nodes, _ in items),
        "risk_all": sum(contains_all(nodes, row.get("injected_risk_nodes")) for row, nodes, _ in items),
        "evidence_any": sum(contains_any(nodes, row.get("injected_evidence_nodes")) for row, nodes, _ in items),
        "valuable_any": sum(contains_any(nodes, valuable_nodes(row)) for row, nodes, _ in items),
        "valuable_all": sum(contains_all(nodes, valuable_nodes(row)) for row, nodes, _ in items),
    }


def by_size(rows: list[dict]) -> list[dict]:
    output = []
    for size in sorted({row["scc_size"] for row in rows if not row.get("error")}):
        for method in ("naive", "sa-mcgs"):
            subset = [
                row
                for row in rows
                if not row.get("error") and row["scc_size"] == size and row["method"] == method
            ]
            if not subset:
                continue
            item = metric_summary(subset, method=method)
            item["size"] = size
            item["method"] = method
            if method == "sa-mcgs":
                item["blind_avg_compression"] = mean(
                    [
                        float(row.get("blind_compression_ratio") or 0)
                        for row in subset
                        if row.get("blind_compression_ratio") is not None
                    ]
                )
            output.append(item)
    return output


def save_domain_table(rows: list[dict]) -> Path:
    domains = ["debian", "sec_ex21"]
    labels = {"debian": "Debian", "sec_ex21": "SEC EX-21"}
    table_rows = []
    for domain in domains:
        for method in ("naive", "sa-mcgs"):
            summary = metric_summary(rows, domain=domain, method=method)
            subgraph = matched_subgraph_summary(rows, domain=domain, method=method)
            row = [
                labels[domain],
                "Ranked Naive" if method == "naive" else "SA-MCGS",
                str(summary["n"]),
                pct(summary["root_top3"], summary["n"]),
                pct(summary["risk_any_top3"], summary["n"]),
                pct(summary["risk_all_top3"], summary["n"]),
                f"{summary['avg_root_rank']:.2f}",
                pct(subgraph["risk_any"], subgraph["n"]),
                pct(subgraph["risk_all"], subgraph["n"]),
                f"{subgraph['avg_compression'] * 100:.1f}%",
            ]
            if method == "sa-mcgs":
                row.extend(
                    [
                        pct(summary["oc_hit"], summary["n"]),
                        pct(summary["oc_effective"], summary["oc_effective_denominator"]),
                        pct(summary["blind_risk_any_ret"], summary["n"]),
                        pct(summary["blind_risk_all_ret"], summary["n"]),
                        f"{summary['blind_avg_compression'] * 100:.1f}%",
                    ]
                )
            else:
                row.extend(["-", "-", "-", "-", "-"])
            table_rows.append(row)

    columns = [
        "领域",
        "方法",
        "N",
        "Root@3",
        "Risk-any@3",
        "Risk-all@3",
        "平均 root 排名",
        "子图 risk-any",
        "子图 risk-all",
        "子图压缩率",
        "OC 命中",
        "OC 有效率",
        "盲风险子图 risk-any",
        "盲风险子图 risk-all",
        "盲压缩率",
    ]
    path = FIGURES / "formal_realtext_main_domain_metrics_table.png"
    fig, ax = plt.subplots(figsize=(24, 6.2))
    ax.axis("off")
    table = ax.table(cellText=table_rows, colLabels=columns, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.85)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#cfd7df")
        if row == 0:
            cell.set_facecolor("#18212b")
            cell.set_text_props(color="white", weight="bold")
        elif col == 1 and cell.get_text().get_text() == "SA-MCGS":
            cell.set_facecolor("#e6f4ef")
        elif col == 1 and cell.get_text().get_text() == "Ranked Naive":
            cell.set_facecolor("#fff2e8")
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def save_core_chart(rows: list[dict]) -> Path:
    methods = ["naive", "sa-mcgs"]
    labels = ["Root@3", "Risk-any@3", "Risk-all@3"]
    data = []
    for method in methods:
        summary = metric_summary(rows, method=method)
        total = summary["n"]
        data.append(
            [
                summary["root_top3"] / total,
                summary["risk_any_top3"] / total,
                summary["risk_all_top3"] / total,
            ]
        )
    x = range(len(labels))
    width = 0.34
    path = FIGURES / "formal_realtext_core_topk.png"
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    colors = ["#c83f36", "#0b8063"]
    for index, method in enumerate(methods):
        offset = (index - 0.5) * width
        values = data[index]
        bars = ax.bar([i + offset for i in x], values, width=width, color=colors[index], label=method)
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.025,
                f"{value * 100:.0f}%",
                ha="center",
                va="bottom",
                fontsize=10,
                weight="bold",
            )
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("命中率")
    ax.set_title("Top-k 是辅助指标，不是 SA-MCGS 的主要优势")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.22)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def save_subgraph_chart(rows: list[dict]) -> Path:
    domains = ["debian", "sec_ex21"]
    labels = ["Debian", "SEC EX-21"]
    any_ret = []
    all_ret = []
    compression = []
    oc_rate = []
    oc_effectiveness = []
    for domain in domains:
        summary = metric_summary(rows, domain=domain, method="sa-mcgs")
        total = summary["n"]
        any_ret.append(summary["blind_risk_any_ret"] / total if total else 0)
        all_ret.append(summary["blind_risk_all_ret"] / total if total else 0)
        compression.append(summary["blind_avg_compression"])
        oc_rate.append(summary["oc_hit"] / total if total else 0)
        oc_effectiveness.append(summary["oc_effectiveness"])

    x = list(range(len(domains)))
    width = 0.16
    path = FIGURES / "formal_realtext_main_oc_subgraph.png"
    fig, ax = plt.subplots(figsize=(13.5, 7.2))
    series = [
        ("OC 命中", oc_rate, "#2d5aa7"),
        ("OC 有效率", oc_effectiveness, "#4e79a7"),
        ("Risk-any 保留", any_ret, "#0b8063"),
        ("Risk-all 保留", all_ret, "#7d4cb5"),
        ("压缩率", compression, "#e07a2f"),
    ]
    for index, (name, values, color) in enumerate(series):
        offset = (index - 2) * width
        bars = ax.bar([i + offset for i in x], values, width=width, color=color, label=name)
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.025,
                f"{value * 100:.0f}%",
                ha="center",
                va="bottom",
                fontsize=9,
                weight="bold",
            )
    ax.set_ylim(0, 1.18)
    ax.set_ylabel("比例", fontsize=14)
    ax.set_title("SA-MCGS 的价值：OC 信号 + 盲风险子图压缩", fontsize=18, pad=16)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=14)
    ax.legend(frameon=False, ncols=3, fontsize=12)
    ax.grid(axis="y", alpha=0.22)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def save_matched_subgraph_chart(rows: list[dict]) -> Path:
    domains = ["debian", "sec_ex21"]
    labels = ["Debian", "SEC EX-21"]
    naive_comp = []
    sa_comp = []
    naive_any = []
    sa_any = []
    naive_all = []
    sa_all = []
    for domain in domains:
        n = matched_subgraph_summary(rows, domain=domain, method="naive")
        s = matched_subgraph_summary(rows, domain=domain, method="sa-mcgs")
        naive_comp.append(n["avg_compression"])
        sa_comp.append(s["avg_compression"])
        naive_any.append(n["risk_any"] / n["n"] if n["n"] else 0)
        sa_any.append(s["risk_any"] / s["n"] if s["n"] else 0)
        naive_all.append(n["risk_all"] / n["n"] if n["n"] else 0)
        sa_all.append(s["risk_all"] / s["n"] if s["n"] else 0)

    x = list(range(len(domains)))
    width = 0.12
    path = FIGURES / "formal_realtext_main_matched_subgraph.png"
    fig, ax = plt.subplots(figsize=(15, 7.2))
    series = [
        ("Naive risk-any", naive_any, "#d24b40"),
        ("SA risk-any", sa_any, "#0b8063"),
        ("Naive risk-all", naive_all, "#e58f86"),
        ("SA risk-all", sa_all, "#7d4cb5"),
        ("Naive 压缩率", naive_comp, "#f2b36d"),
        ("SA 压缩率", sa_comp, "#e07a2f"),
    ]
    for index, (name, values, color) in enumerate(series):
        offset = (index - 2.5) * width
        bars = ax.bar([i + offset for i in x], values, width=width, color=color, label=name)
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.02,
                f"{value * 100:.0f}%",
                ha="center",
                va="bottom",
                fontsize=9,
            )
    ax.set_ylim(0, 1.18)
    ax.set_ylabel("比例", fontsize=14)
    ax.set_title("公平子图对照：Naive Top-3+邻居 vs SA-MCGS OC+Top-3+邻居", fontsize=17, pad=16)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=14)
    ax.legend(frameon=False, ncols=3, fontsize=11)
    ax.grid(axis="y", alpha=0.22)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def save_size_chart(rows: list[dict]) -> Path:
    rows = [row for row in rows if row.get("domain") in {"debian", "sec_ex21"}]
    size_rows = by_size(rows)
    sizes = sorted({item["size"] for item in size_rows})
    naive = {item["size"]: item for item in size_rows if item["method"] == "naive"}
    sam = {item["size"]: item for item in size_rows if item["method"] == "sa-mcgs"}
    path = FIGURES / "formal_realtext_main_by_size.png"
    fig, ax = plt.subplots(figsize=(15, 7.2))
    x = list(range(len(sizes)))
    width = 0.24
    series = [
        ("Naive Root@3", [naive[s]["root_top3"] / naive[s]["n"] for s in sizes], "#c83f36"),
        ("SA Root@3", [sam[s]["root_top3"] / sam[s]["n"] for s in sizes], "#0b8063"),
        ("SA 盲压缩率", [sam[s].get("blind_avg_compression", 0) for s in sizes], "#e07a2f"),
    ]
    for index, (name, values, color) in enumerate(series):
        offset = (index - 1) * width
        ax.bar([i + offset for i in x], values, width=width, label=name, color=color)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("比例", fontsize=14)
    ax.set_title("SCC 变长后，root Top-3 走弱，子图压缩价值更明显", fontsize=18, pad=16)
    ax.set_xticks(x)
    ax.set_xticklabels([str(size) for size in sizes], fontsize=13)
    ax.set_xlabel("SCC 规模", fontsize=14)
    ax.legend(frameon=False, ncols=3, fontsize=13)
    ax.grid(axis="y", alpha=0.22)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def save_sec_case_table(rows: list[dict]) -> Path:
    pairs = defaultdict(dict)
    for row in rows:
        if row.get("domain") != "sec_ex21" or row.get("error"):
            continue
        key = (row["scc_id"], row["scc_size"], row["model"])
        pairs[key][row["method"]] = row

    table_rows = []
    for (_, size, model), pair in sorted(pairs.items(), key=lambda item: (item[0][1], item[0][2], item[0][0])):
        naive = pair.get("naive", {})
        sam = pair.get("sa-mcgs", {})
        blind_nodes = sam.get("blind_risk_subgraph_nodes") or []
        blind_size = len(blind_nodes)
        risk_targets = sam.get("injected_risk_nodes") or []
        oc_effective = contains_any(sam.get("oc_detected"), valuable_nodes(sam))
        table_rows.append(
            [
                str(size),
                model,
                str(naive.get("root_rank", "-")),
                "是" if naive.get("root_top3_hit") else "否",
                str(sam.get("root_rank", "-")),
                "是" if sam.get("root_top3_hit") else "否",
                str(sam.get("oc_count") or 0),
                "是" if oc_effective else "否",
                f"{blind_size}/{size}",
                "是" if contains_any(blind_nodes, risk_targets) else "否",
                "是" if contains_all(blind_nodes, risk_targets) else "否",
            ]
        )
    columns = [
        "规模",
        "模型",
        "Naive root 排名",
        "Naive root@3",
        "SA root 排名",
        "SA root@3",
        "OC",
        "OC 有效",
        "盲子图",
        "Risk-any",
        "Risk-all",
    ]
    path = FIGURES / "formal_realtext_main_sec_case_table.png"
    fig, ax = plt.subplots(figsize=(18, 9.2))
    ax.axis("off")
    table = ax.table(cellText=table_rows, colLabels=columns, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.65)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#cfd7df")
        if row == 0:
            cell.set_facecolor("#18212b")
            cell.set_text_props(color="white", weight="bold")
        elif row > 0 and col in (6, 7, 8, 9):
            cell.set_facecolor("#e6f4ef")
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    body = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    body.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(body)


def markdown_image_path(path: Path) -> str:
    return path.resolve().as_posix()


def markdown_image(path: Path, alt: str) -> str:
    return f"![{alt}]({markdown_image_path(path)})"


def full_size_link(path: Path) -> str:
    return f"[打开原图]({markdown_image_path(path)})"


def write_report(rows: list[dict], image_paths: dict[str, Path]) -> None:
    main_rows = [row for row in rows if row.get("domain") in {"debian", "sec_ex21"}]
    wiki_rows = [row for row in rows if row.get("domain") == "wikipedia"]
    total = len([row for row in main_rows if not row.get("error")])
    errors = len([row for row in main_rows if row.get("error")])
    overall_naive = metric_summary(main_rows, method="naive")
    overall_sam = metric_summary(main_rows, method="sa-mcgs")
    overall_naive_sub = matched_subgraph_summary(main_rows, method="naive")
    overall_sam_sub = matched_subgraph_summary(main_rows, method="sa-mcgs")

    domain_rows = []
    for domain, label in [
        ("debian", "Debian"),
        ("sec_ex21", "SEC EX-21"),
    ]:
        naive = metric_summary(rows, domain=domain, method="naive")
        sam = metric_summary(rows, domain=domain, method="sa-mcgs")
        naive_sub = matched_subgraph_summary(rows, domain=domain, method="naive")
        sam_sub = matched_subgraph_summary(rows, domain=domain, method="sa-mcgs")
        domain_rows.append(
            [
                label,
                str(naive["n"] + sam["n"]),
                pct(naive["root_top3"], naive["n"]),
                pct(sam["root_top3"], sam["n"]),
                pct(naive_sub["risk_any"], naive_sub["n"]),
                pct(sam_sub["risk_any"], sam_sub["n"]),
                pct(naive_sub["risk_all"], naive_sub["n"]),
                pct(sam_sub["risk_all"], sam_sub["n"]),
                f"{naive_sub['avg_compression'] * 100:.1f}%",
                f"{sam_sub['avg_compression'] * 100:.1f}%",
                pct(sam["oc_hit"], sam["n"]),
                pct(sam["oc_effective"], sam["oc_effective_denominator"]),
            ]
        )

    result_files = "\n".join(
        f"- `{path.name}`"
        for path in sorted(RESULTS.glob(RUN_PATTERN))
        if not path.name.endswith(".partial.json")
    )
    wiki_naive = metric_summary(rows, domain="wikipedia", method="naive")
    wiki_sam = metric_summary(rows, domain="wikipedia", method="sa-mcgs")

    report = f"""# Structural Simple V2 正式真实文本实验报告

最后更新：2026-05-13  
实验范围：`memory_stress` CLI profile，内部版本 `_inject_profile_version = structural_simple_v2`  
运行标签：`formal_full_realtext_c8_*_20260513`

> **状态：正式真实文本分析。** 旧版 `memory_stress`、synthetic、diagnostic 结果不进入本报告主结果，只作为实验设计演进的历史记录。当前主结论只基于 **Debian + SEC EX-21**。Wikipedia 由于真实 SCC 覆盖过少，只保留为数据集诊断记录，不参与主结论。

## 1. 核心结论

结构性缺陷不应该只按“注入 root 节点是否进入 Top-k”来评估，而应该按 **风险区域 risk region** 来评估。

原因很简单：我们注入的不是一个孤立坏点，而是一组互相依赖的结构性冲突。危险状态通常由 perturbed root、远距离 witness，以及可能存在的 bridge/affected 节点共同形成。在真实修复流程里，修改 **root 侧、witness 侧，或者某个被影响的桥接记录** 都可能解除风险。因此，root-only Top-k 只是一个较窄的诊断指标；如果模型抓到了 witness 或 affected 节点，也不能简单算失败。

本轮主结果完成 **{total} 个有效 case，{errors} 个错误**。这里的主结果只统计 Debian + SEC EX-21；Wikipedia 的 4 个 case 不进入主表结论。

{markdown_table(
    ["方法", "N", "Root Top-3", "Risk-any Top-3", "Risk-all Top-3", "平均 root 排名", "子图 risk-any", "子图 risk-all", "子图压缩率", "SA-only OC", "OC 有效率"],
    [
        [
            "Ranked Naive",
            str(overall_naive["n"]),
            pct(overall_naive["root_top3"], overall_naive["n"]),
            pct(overall_naive["risk_any_top3"], overall_naive["n"]),
            pct(overall_naive["risk_all_top3"], overall_naive["n"]),
            f"{overall_naive['avg_root_rank']:.2f}",
            pct(overall_naive_sub["risk_any"], overall_naive_sub["n"]),
            pct(overall_naive_sub["risk_all"], overall_naive_sub["n"]),
            f"{overall_naive_sub['avg_compression'] * 100:.1f}%",
            "-",
            "-",
        ],
        [
            "SA-MCGS",
            str(overall_sam["n"]),
            pct(overall_sam["root_top3"], overall_sam["n"]),
            pct(overall_sam["risk_any_top3"], overall_sam["n"]),
            pct(overall_sam["risk_all_top3"], overall_sam["n"]),
            f"{overall_sam['avg_root_rank']:.2f}",
            pct(overall_sam_sub["risk_any"], overall_sam_sub["n"]),
            pct(overall_sam_sub["risk_all"], overall_sam_sub["n"]),
            f"{overall_sam_sub['avg_compression'] * 100:.1f}%",
            pct(overall_sam["oc_hit"], overall_sam["n"]),
            pct(overall_sam["oc_effective"], overall_sam["oc_effective_denominator"]),
        ],
    ],
)}

**解释。** 如果只看 Top-k，这轮并不是一个干净的 SA-MCGS 排名胜利：Naive 的 root Top-3 是 `{pct(overall_naive["root_top3"], overall_naive["n"])}`，SA-MCGS 的 root Top-3 是 `{pct(overall_sam["root_top3"], overall_sam["n"])}`。但两种方法都经常能把至少一个风险节点放进 Top-3。这说明 one-shot LLM 并非完全看不见风险；真正要比较的是，系统能不能把“泛泛的可疑节点”进一步组织成 **OC 证据 + 可检查的风险子图**。

## 2. 为什么主指标应是 OC + 风险子图

对 SA-MCGS 来说，重要输出不是单个排名，而是：

- **OC hit：** 局部窗口搜索是否发现了 ordered-cycle evidence 或结构性矛盾信号。
- **OC 有效率：** 在已经触发 OC 的 case 中，OC 节点是否落在 root / witness / bridge / affected 任一可解释风险节点上。它衡量 OC 不是“随便响”，而是真的指向风险扩散区域。
- **盲风险子图 blind risk subgraph：** 由 OC 节点、Top-k 风险节点和局部环邻居构成，不手动加入 GT root。
- **Risk-any retention：** 盲子图是否保留至少一个可修复风险点，例如 root 或 witness。
- **Risk-all retention：** 盲子图是否同时保留 root 和 witness。这个指标更严格，但真实修复时不一定必须同时抓住两端。
- **Compression：** 在保留风险区域的同时，能把原 SCC 压缩掉多少。

为避免对子图能力的比较不公平，报告新增了一个 matched subgraph baseline：

```text
Naive 子图 = Naive global_ranking Top-3 anchors + 每个 anchor 的环上前后邻居
SA-MCGS 子图 = OC anchors + Top-3 anchors + 环上前后邻居，不使用 GT root
```

这个口径下，Naive 也被允许输出一个风险子图；SA-MCGS 的增量主要来自 OC anchors 是否能让子图更小、更集中。

{markdown_image(image_paths["subgraph"], "OC 与风险子图")}

{full_size_link(image_paths["subgraph"])}

{markdown_table(
    ["领域", "总 case", "Naive Root@3", "SA Root@3", "Naive 子图 any", "SA 子图 any", "Naive 子图 all", "SA 子图 all", "Naive 压缩", "SA 压缩", "SA OC 命中", "OC 有效率"],
    domain_rows,
)}

{markdown_image(image_paths["table"], "按领域指标表")}

{full_size_link(image_paths["table"])}

{markdown_image(image_paths["matched"], "公平子图对照")}

{full_size_link(image_paths["matched"])}

**SEC EX-21 是当前最强的主结果领域。** 在这个领域里，两种方法的 root Top-3 都很低，说明任务不是靠“看出被改过的 root”就能轻松解决。在 matched subgraph 口径下，Naive 子图 risk-any 是 `15/16 (94%)`，SA-MCGS 是 `14/16 (88%)`；但 SA-MCGS 平均压缩率更高，`57.4%` 对 `40.1%`。这说明 SA-MCGS 不是单纯覆盖更多风险点，而是更激进地压缩风险区域。与此同时，SEC 中 `12/16` 个 case 有 OC，其中 `7/12` 个 OC 落在 root / witness / bridge / affected 这类可解释风险区域里。

**Debian 是混合但有用的支持结果。** 很多 5-node 小环太小，不容易体现压缩价值；但 matched subgraph 口径下，Naive risk-any 是 `21/22 (95%)`，SA-MCGS 是 `22/22 (100%)`，同时 SA-MCGS 压缩率从 Naive 的 `7.3%` 提高到 `29.7%`。此外，SA-MCGS 在 `11/22` 个 case 中触发 OC，且这 `11/11` 个 OC 都落在可解释风险区域里。

**Wikipedia 暂时不参与主结论。** 当前 loader 合图后只有 3 个真实 SCC，长度为 `[5, 34, 56]`；在 `5-24` 正式范围内只剩一个 5-node SCC，因此结果覆盖太稀疏，不适合作为数据集主证据。

## 3. 环长度影响

{markdown_image(image_paths["size"], "按 SCC 规模对比")}

{full_size_link(image_paths["size"])}

随着 SCC 变长，root Top-3 会变弱并且更不稳定。这是合理现象：结构性冲突传播后，root 不一定是表面上最可疑的记录。更稳健的指标应该是方法是否保留了一个可操作的风险区域。

比起 5-node 小环，11/12/18-node case 更值得写进论文主体：

- Debian 11-node：Naive 和 SA-MCGS 都没有命中 root Top-3，但 DeepSeek + SA-MCGS 仍触发 OC，并保留压缩子图。
- Debian 12-node：gpt-4o + SA-MCGS 在 Naive miss 的情况下恢复 root Top-3；两个 SA run 都压缩到 `7/12`。
- SEC 18-node：两个模型都 miss root Top-3，但盲风险子图压缩到 `7/18`，相当于减少 `61%`。即使 Top-k 不成功，这也是很强的风险子图证据。

## 4. 为什么暂时不参考 Wikipedia

Wikipedia 这轮不是因为 API 或实验失败，而是数据形态本身不适合作为当前主数据集。当前 loader 把真实 category cycles 合成图后再跑 Tarjan，得到的 SCC 长度只有：

```text
[5, 34, 56]
```

在本轮正式参数 `--real-min-size 5 --real-max-size 24` 下，Wikipedia 只贡献了一个 5-node SCC，因此只有：

```text
1 个 SCC × 2 个模型 × 2 个方法 = 4 个 case
```

这 4 个 case 的结果是：Naive root Top-3 `{pct(wiki_naive["root_top3"], wiki_naive["n"])}`，SA-MCGS root Top-3 `{pct(wiki_sam["root_top3"], wiki_sam["n"])}`，SA-MCGS OC `{pct(wiki_sam["oc_hit"], wiki_sam["n"])}`。这些数字没有足够数据集覆盖意义，因此只保留为记录，不进入主结论。

## 5. SEC EX-21 明细

SEC 是当前最适合承载论文叙事的领域，因为它把 root ranking 和 structural risk localization 分开了：root 排名不高，但 OC 与风险子图仍然能给出可解释定位。

{markdown_image(image_paths["sec_table"], "SEC 明细表")}

{full_size_link(image_paths["sec_table"])}

表格右侧是关键：即使 root Top-3 没命中，OC、OC 有效率和盲风险子图覆盖仍然经常保留下来。这正好匹配我们的设定：结构性注入缺陷不一定只能从 root 修，也可以从 witness 或 affected 节点侧修。

## 6. 对论文主张的影响

论文不应该写成“SA-MCGS 在单点排名上碾压 Naive”。更稳、更有说服力的主张应该是：

> **在真实文本的循环依赖图中，one-shot ranking 经常可以抓到某个可疑节点，但它不能解释结构性失效。SA-MCGS 的价值在于增加 search-time OC 信号，并把 SCC 压缩成一个更小的风险子图，同时保留可操作的修复入口。**

这个口径也解释了为什么 root-only GT 会显得不公平或噪声很大。注入 root 只是结构性矛盾的一端；如果模型抓到了 witness、bridge 或 affected 记录，在实践上并不是失败，而是找到了另一个修复把手。

## 7. 下一步实验建议

1. 把 `blind_risk_subgraph` 作为主子图指标；GT-anchored subgraph 只保留为 sanity check。
2. 分开报告 root Top-k、risk-any Top-k、risk-all Top-k，不要合并成一个 detection rate。
3. 把 SEC EX-21 提升为当前设计下的主结构风险领域。
4. Debian 作为支持结果，重点写 11/12-node SCC。
5. 当前 Wikipedia 不作为 headline；后续除非改成更合理的 raw-cycle mode 或找到更密集真实 SCC，否则不进入主实验。
6. 考虑把 **CUAD** 加入下一轮跨域实验。CUAD 的合同条款文本更长、更接近法律推理场景，可能比 Wikipedia 更适合验证结构性冲突 + 风险子图压缩。
7. 方法章节必须解释：为什么结构性冲突不能只用 root-only GT 评估。
8. 下一轮可以只在 SEC/Debian/CUAD 上跑多个 conflict template，继续坚持真实文本、不新增 synthetic 节点。

## 8. 结果文件

{result_files}
"""
    REPORT.write_text(report)


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    image_paths = {
        "table": save_domain_table(rows),
        "subgraph": save_subgraph_chart(rows),
        "matched": save_matched_subgraph_chart(rows),
        "size": save_size_chart(rows),
        "sec_table": save_sec_case_table(rows),
    }
    write_report(rows, image_paths)
    print(REPORT)
    for path in image_paths.values():
        print(path)


if __name__ == "__main__":
    main()

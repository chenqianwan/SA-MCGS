#!/usr/bin/env python3
"""Build the budget and fixed-case three-method revision figures, offline.

Figure contract: the budget panels test whether complete risk evidence is
accumulated while the emitted core stays compact. The case panels compare
which evidence is retained under identical node coordinates. Both figures
use the full specified cohort, immutable result rows, editable vector text,
and a Python quantitative-grid workflow; no model client may be called.

Only style is inherited from the earlier plotting script. Prefix cores are
reconstructed with the production selector from saved completed rollouts;
every final state and every final core must reproduce its frozen source.
The baseline lines are final reference values, not baseline trajectories.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "experiments/main_experiment/paper_assets"
FIGURES = ASSETS / "figures"
DATA = ASSETS / "revision_20260925"
SOURCE_CSV = ROOT / "2026NAACL/SA-MCGS/experiments/lea_full320_completion_20260923/matched_3method_case_metrics.csv"
REPLAY_SCRIPT = ROOT / "emnlp2026_discussion/run_component_ablation_stage2_core_replay.py"
METHODS = ("one-shot", "lea", "sa-mcgs")
LABELS = {"one-shot": "One-shot", "lea": "LEA", "sa-mcgs": "SA-MCGS"}
COLORS = {"one-shot": "#8A8F98", "lea": "#C9822B", "sa-mcgs": "#2F6690"}
MARKERS = {"one-shot": "o", "lea": "s", "sa-mcgs": "^"}
FIXED_CASE = "28_bgb25_scc_3_handoff_invariant"
REFERENCES = {
    "risk_all": {"one-shot": .15, "lea": .4375, "sa-mcgs": .75},
    "compression": {"one-shot": .6789, "lea": .5126, "sa-mcgs": .5126},
}
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"],
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 9,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7.2,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": .6, "pdf.fonttype": 42, "ps.fonttype": 42,
    "svg.fonttype": "none", "savefig.dpi": 600,
})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(name: str, payload) -> None:
    (DATA / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_csv(name: str, rows: list[dict]) -> None:
    with (DATA / name).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def source_record(row: dict) -> dict:
    path = Path(row["source_file"])
    assert "sha256:" + sha(path) == row["source_sha256"], path
    payload = json.loads(path.read_text())
    method = "naive" if row["method"] == "one-shot" else row["method"]
    if isinstance(payload, list):
        matches = [r for r in payload if r.get("model") == row["model"] and r.get("method") == method]
        assert len(matches) == 1
        return matches[0]
    return payload


def replay_budget(rows: list[dict]) -> tuple[list[dict], dict]:
    spec = importlib.util.spec_from_file_location("frozen_core_replay", REPLAY_SCRIPT)
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    cohort = [r for r in rows if r["model"] == "gpt-4o" and r["method"] == "sa-mcgs"]
    assert len(cohort) == len({r["stable_case_uid"] for r in cohort}) == 80
    detailed, audits = [], []
    for row in cohort:
        full = source_record(row)
        events, trace_audit = replay.validate_trace(full)
        assert len(events) == 60
        assert [int(e["completion_index"]) for e in events] == list(range(1, 61))
        assert len(full["scc_clause_ids"]) == int(row["scc_size"])
        assert full["injected_node"] == row["root_node"]
        assert set(full["injected_risk_nodes"]) == set(json.loads(row["risk_nodes_json"]))
        machine, sentinel = replay.make_replay_mcgs(full)
        risks = set(full["injected_risk_nodes"])
        legacy_final = set(full["convergence_trace"][-1]["subgraph_nodes"])
        for event in events:
            replay.apply_trace_event(machine, event)
            budget = int(event["completion_index"])
            summary = machine._build_result(elapsed=0, llm_calls=0, tt_hits=0, total_iters=budget)
            nodes = list(summary["evidence_risk_subgraph_nodes"])
            detailed.append({
                "model": "gpt-4o", "case_id": row["main_case_id"],
                "case_uid": row["stable_case_uid"], "budget": budget,
                "risk_all": int(bool(risks) and risks.issubset(nodes)),
                "compression": 1 - len(nodes) / len(full["scc_clause_ids"]),
                "core_nodes": json.dumps(nodes), "core_size": len(nodes),
            })
        parity_fields = replay.assert_final_full_parity(full, summary)
        frozen = json.loads(row["selected_nodes_json"])
        assert nodes == frozen == full["core_evidence_risk_subgraph_nodes"]
        assert abs(detailed[-1]["compression"] - float(row["compression"])) < 1e-12
        assert detailed[-1]["risk_all"] == int(row["risk_all"])
        assert sentinel.calls == 0
        audits.append({
            "case_id": row["main_case_id"], "case_uid": row["stable_case_uid"],
            "source_file": str(Path(row["source_file"]).relative_to(ROOT)),
            "source_sha256": row["source_sha256"], "n_completed_rollouts": 60,
            "source_and_main_table_core_equal": True, "final_replay_core_equal": True,
            "full_state_parity_fields": parity_fields, "llm_calls": sentinel.calls,
            "legacy_trace_final_core_equal": legacy_final == set(frozen),
        })
    aggregated = []
    for budget in range(1, 61):
        subset = [r for r in detailed if r["budget"] == budget]
        assert len(subset) == 80
        aggregated.append({
            "budget": budget, "n": 80,
            "risk_all": np.mean([r["risk_all"] for r in subset]).item(),
            "compression": np.mean([r["compression"] for r in subset]).item(),
        })
    assert round(aggregated[-1]["risk_all"] * 100, 2) == 75
    assert round(aggregated[-1]["compression"] * 100, 2) == 51.26
    audit = {
        "verification_passed": True, "cohort_n": 80, "prefixes_per_case": 60,
        "case_prefix_rows": len(detailed), "budget_endpoint": aggregated[-1],
        "case_audits": audits, "source_csv_sha256": sha(SOURCE_CSV),
        "selector_sha256": sha(ROOT / "src/modules/alphago_mcgs.py"),
        "replay_sha256": sha(REPLAY_SCRIPT),
        "legacy_final_core_mismatches": sum(not x["legacy_trace_final_core_equal"] for x in audits),
        "reference_lines": REFERENCES,
        "center": "Unweighted mean over the same 80 model-cases at each completed rollout prefix",
        "interval": "None; descriptive finite benchmark means, with no repeated-run uncertainty inferred",
    }
    write_csv("gpt4o_budget_case_prefixes.csv", detailed)
    write_csv("gpt4o_budget_summary.csv", aggregated)
    write_json("gpt4o_budget_verification.json", audit)
    return aggregated, audit


def export(fig, basename: str) -> None:
    fig.savefig(FIGURES / f"{basename}.pdf", facecolor="white")
    fig.savefig(FIGURES / f"{basename}.svg", facecolor="white")
    fig.savefig(FIGURES / f"{basename}.png", dpi=600, facecolor="white")
    plt.close(fig)


def plot_budget(series: list[dict]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.15, 2.48))
    fig.subplots_adjust(left=.080, right=.974, bottom=.215, top=.76, wspace=.28)
    budgets = np.asarray([r["budget"] for r in series])
    for ax, metric, title, letter in zip(axes, ("risk_all", "compression"), ("Complete risk evidence", "Subgraph compression"), ("a", "b")):
        values = np.asarray([r[metric] * 100 for r in series])
        for method, style in (("one-shot", ":"), ("lea", "--")):
            level = REFERENCES[metric][method] * 100
            ax.axhline(level, color=COLORS[method], ls=style, lw=1.2, zorder=1)
            ax.plot([60], [level], color=COLORS[method], marker=MARKERS[method], ms=4, zorder=2)
        ax.plot(budgets, values, color=COLORS["sa-mcgs"], lw=1.8, marker="^", markevery=[0,9,19,29,39,49,59], ms=3.5, zorder=3)
        ax.annotate(f"{values[-1]:.2f}%", (60, values[-1]), xytext=(-3, 8), textcoords="offset points", ha="right", color=COLORS["sa-mcgs"], fontsize=7, weight="bold")
        ax.set(xlim=(1, 62), ylim=(0, 100), xticks=[1,10,20,30,40,50,60], yticks=[0,25,50,75,100], xlabel="Completed rollouts", ylabel="Risk-all (%)" if metric == "risk_all" else "Compression (%)")
        ax.set_title(f"{letter}  {title}", loc="left", fontweight="bold", pad=7)
        ax.grid(axis="y", color="#E5E7EB", lw=.45, zorder=0)
    handles = [Line2D([], [], color=COLORS[m], marker=MARKERS[m], linestyle=style, lw=1.5, ms=4, label=LABELS[m] + (" reference" if m != "sa-mcgs" else " prefix core")) for m, style in zip(METHODS, (":", "--", "-"))]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.52, .995), ncol=3, frameon=False, handlelength=2.5, columnspacing=2)
    export(fig, "fig04_budget_prefix_three_methods")


def plot_case(rows: list[dict]) -> dict:
    selected = [r for r in rows if r["model"] == "gemini-2.5-pro" and r["main_case_id"] == FIXED_CASE]
    assert len(selected) == 3 and {r["method"] for r in selected} == set(METHODS)
    assert len({r["stable_case_uid"] for r in selected}) == 1
    method_rows = {r["method"]: r for r in selected}
    full = source_record(method_rows["sa-mcgs"])
    nodes = full["scc_clause_ids"]
    assert len(nodes) == 25
    risks, affected = set(full["injected_risk_nodes"]), set(full["injected_affected_nodes"])
    assert full["injected_node"] == "bgb_505" and full["injected_witness_node"] == "bgb_491"
    assert json.loads(method_rows["sa-mcgs"]["selected_nodes_json"]) == ["bgb_312f", "bgb_356", "bgb_358", "bgb_491", "bgb_491a", "bgb_495", "bgb_505", "bgb_512", "bgb_514"]
    positions = {n: (i % 5, 4 - i // 5) for i, n in enumerate(nodes)}
    fig, axes = plt.subplots(1, 3, figsize=(7.15, 3.78))
    fig.subplots_adjust(left=.028, right=.982, bottom=.28, top=.82, wspace=.15)
    evidence_colors = {"Risk endpoint": "#B75A57", "Affected context": "#C9822B", "Other retained": "#5A8F73", "Omitted": "#DFE3E8"}
    summary = []
    for letter, method, ax in zip(("a", "b", "c"), METHODS, axes):
        row = method_rows[method]
        kept = set(json.loads(row["selected_nodes_json"]))
        assert kept.issubset(nodes)
        ax.set(xlim=(-.45,4.45), ylim=(-.53,4.40), aspect="equal")
        ax.axis("off")
        ax.set_title(f"{letter}  {LABELS[method]}", fontsize=9, color=COLORS[method], fontweight="bold", pad=9)
        for n, (x,y) in positions.items():
            category = "Omitted" if n not in kept else "Risk endpoint" if n in risks else "Affected context" if n in affected else "Other retained"
            marker = "D" if n in risks else "o"
            ax.scatter(x, y, s=36 if n in risks else 26, marker=marker, c=evidence_colors[category], edgecolors="#6B7280" if n in risks else "none", linewidths=.5, zorder=2)
            ax.text(x, y-.22, n.replace("bgb_", "§"), ha="center", va="top", fontsize=6.4, color="#303842" if n in kept else "#7D8590")
        metrics = {
            "method": method, "case_id": FIXED_CASE, "case_uid": row["stable_case_uid"],
            "model": row["model"], "retained_nodes": len(kept), "scc_size": len(nodes),
            "root_at3": float(row["root_at_3"]), "risk_any": float(row["risk_any"]),
            "risk_all": float(row["risk_all"]), "compression": float(row["compression"]),
            "selected_nodes": json.dumps(list(json.loads(row["selected_nodes_json"]))),
        }
        summary.append(metrics)
        metric_text = (f"Nodes retained  {len(kept)}/25\n"
                       f"Root@3 / Risk-any / Risk-all\n"
                       f"{int(metrics['root_at3'])} / {int(metrics['risk_any'])} / {int(metrics['risk_all'])}\n"
                       f"Compression  {metrics['compression']:.0%}")
        ax.text(.5, -.13, metric_text, transform=ax.transAxes, ha="center", va="top", fontsize=7, linespacing=1.45)
    handles = [Line2D([], [], color="none", marker="D" if label == "Risk endpoint" else "o", markerfacecolor=color, markeredgecolor="#6B7280" if label == "Risk endpoint" else "none", markersize=5, label=label) for label, color in evidence_colors.items()]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.50, 1.01), ncol=4, frameon=False, columnspacing=1.3, handletextpad=.4)
    fig.text(.5, .024, "Gemini 2.5 Pro · BGB · Handoff invariant · Root §505 / witness §491", ha="center", fontsize=7, color="#4B5563")
    export(fig, "fig06_representative_scc_three_methods")
    write_csv("fixed_case_three_methods.csv", summary)
    result = {
        "case_id": FIXED_CASE, "model": "gemini-2.5-pro", "source_case_unchanged": True,
        "shared_node_positions": positions,
        "layout": "Canonical clause order mapped to a shared 5 by 5 node map; no unobserved topology edges are drawn",
        "rows": summary, "source_sha256": {r["method"]: r["source_sha256"] for r in selected},
    }
    write_json("fixed_case_three_methods_provenance.json", result)
    return result


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(SOURCE_CSV.open()))
    series, audit = replay_budget(rows)
    plot_budget(series)
    case = plot_case(rows)
    print(json.dumps({"budget_endpoint": audit["budget_endpoint"], "legacy_final_core_mismatches": audit["legacy_final_core_mismatches"], "case_rows": case["rows"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

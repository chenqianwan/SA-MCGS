#!/usr/bin/env python3
"""Build the five-model manuscript assets from accepted, immutable summaries.

This entry point only writes its own five-model assets. It never runs inference,
re-parses failed outputs, or changes experiment files. Missing measurements and
the accepted aggregation semantics are preserved from each source.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = ROOT / "2026NAACL/SA-MCGS/experiments"
ASSETS = ROOT / "experiments/main_experiment/paper_assets"
DATA = ASSETS / "five_model_data"
FIGURES = ASSETS / "figures"
TABLES = ASSETS / "tables"
MODELS = ["gpt-4o", "gemini-2.5-pro", "qwen2.5-72b", "llama-3.1-8b", "qwen3.5-9b"]
MODEL_LABELS = {
    "gpt-4o": "GPT-4o", "gemini-2.5-pro": "Gemini 2.5 Pro",
    "qwen2.5-72b": "Qwen2.5-72B", "llama-3.1-8b": "Llama 3.1-8B-Instruct",
    "qwen3.5-9b": "Qwen3.5-9B",
}
PANEL_LABELS = dict(MODEL_LABELS, **{"llama-3.1-8b": "Llama 3.1-8B"})
METHODS = ["one-shot", "lea", "sa-mcgs"]
METHOD_LABELS = {"one-shot": "One-shot", "lea": "LEA", "sa-mcgs": "SA-MCGS"}
COLORS = {"one-shot": "#8A8F98", "lea": "#C9822B", "sa-mcgs": "#2F6690"}
MARKERS = {"one-shot": "o", "lea": "s", "sa-mcgs": "^"}
METRICS = ["root_at3", "risk_any", "risk_all", "compression"]
DOMAINS = ["debian", "sec_ex21", "bgb", "cuad"]
DOMAIN_LABELS = {"debian": "Debian", "sec_ex21": "SEC EX-21", "bgb": "BGB", "cuad": "CUAD"}
SCALES = ["small", "medium", "large"]
SCALE_LABELS = {"small": "Short (≤12)", "medium": "Mid (14–20)", "large": "Long (≥24)"}
SCALE_TEX_LABELS = {"small": r"Short ($\leq$12)", "medium": "Mid (14--20)", "large": r"Long ($\geq$24)"}
OLD_SOURCE = EXPERIMENTS / "lea_full320_completion_20260923/matched_3method_case_metrics.csv"
LLAMA_SOURCE = EXPERIMENTS / "llama8b_three_methods_20260924/final_analysis_case_metrics.json"
QWEN_SOURCE = EXPERIMENTS / "kimi_qwen35_three_methods_20260924/parsing_recovery_audit_20260925/metricwise_results.json"
ACCEPTED = {
    "gpt-4o": [[26.25, 55., 15., 67.89], [78.75, 96.25, 43.75, 51.26], [86.25, 100., 75., 51.26]],
    "gemini-2.5-pro": [[90., 97.5, 85., 74.98], [87.5, 100., 83.75, 51.26], [87.5, 97.5, 83.75, 55.86]],
    "qwen2.5-72b": [[2.5, 46.25, 13.75, 42.69], [67.5, 97.5, 43.75, 51.26], [70., 97.5, 75., 52.82]],
    "llama-3.1-8b": [[3.75, 47.5, 25., 30.27], [43.75, 92.5, 35., 51.26], [61.25, 95., 48.75, 51.30]],
    "qwen3.5-9b": [[15., 60., 13.75, 64.73], [56.25, 91.25, 63.75, 51.26], [62.5, 86.25, 63.75, 67.25]],
}


def read_json(path: Path):
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value):
    return None if value in (None, "") else float(value)


def load_rows() -> list[dict]:
    """Canonical 1,200 rows; metrics in [0,1], unavailable compression is None.

    Stable case_uid is shared by all models and methods. The original three
    models also carry selected_nodes and ground-truth nodes from the accepted
    per-case CSV, for same-case illustration and stored-trajectory alignment.
    """
    with OLD_SOURCE.open() as handle:
        old = [r for r in csv.DictReader(handle) if r["model"] in MODELS]
    metadata = {}
    rows = []
    for r in old:
        uid = r["stable_case_uid"]
        base = {
            "case_uid": uid, "main_case_id": r["main_case_id"],
            "main_case_order": int(r["main_case_order"]),
            "physical_scc_uid": r["physical_scc_uid"], "domain": r["domain"],
            "scc_size": int(r["scc_size"]), "scale": r["scale"], "template": r["template"],
            "root_node": r["root_node"], "risk_nodes": json.loads(r["risk_nodes_json"]),
        }
        if uid in metadata:
            assert metadata[uid] == base, (uid, "case metadata mismatch")
        metadata[uid] = base
        rows.append(dict(base, model=r["model"], method=r["method"],
                         case_id=r["main_case_id"], source_file=r["source_file"],
                         source_sha256=r["source_sha256"].removeprefix("sha256:"),
                         summary_source=str(OLD_SOURCE.relative_to(ROOT)),
                         selected_nodes=json.loads(r["selected_nodes_json"]),
                         retained_nodes=int(r["selected_nodes_n"]),
                         root_at3=number(r["root_at_3"]), risk_any=number(r["risk_any"]),
                         risk_all=number(r["risk_all"]), compression=number(r["compression"])))
    assert len(metadata) == 80
    additions = [
        ("llama-3.1-8b", LLAMA_SOURCE, read_json(LLAMA_SOURCE), LLAMA_SOURCE.parent / "downloaded_final/results"),
        ("qwen3.5-9b", QWEN_SOURCE, read_json(QWEN_SOURCE)["models"]["qwen35"]["case_metrics"],
         QWEN_SOURCE.parent.parent / "downloaded_final/qwen35/results"),
    ]
    for model, source, incoming, result_dir in additions:
        assert len(incoming) == 240
        for r in incoming:
            base = metadata[r["case_uid"]]
            for key in ("domain", "scc_size", "scale"):
                assert base[key] == r[key], (model, r["case_uid"], key)
            result_file = result_dir / (r["case_id"] + "__" + r["method"] + ".json")
            assert result_file.exists(), result_file
            method = "one-shot" if r["method"] == "naive-single" else r["method"]
            rows.append(dict(base, model=model, method=method, case_id=r["case_id"],
                             source_file=str(result_file), source_sha256=sha256(result_file),
                             summary_source=str(source.relative_to(ROOT)),
                             selected_nodes=None, retained_nodes=r["retained_nodes"],
                             **{k: number(r[k]) for k in METRICS}))
    rows.sort(key=lambda r: (MODELS.index(r["model"]), r["main_case_order"], METHODS.index(r["method"])))
    assert len(rows) == 1200
    assert len({(r["model"], r["method"], r["case_uid"]) for r in rows}) == 1200
    for model in MODELS:
        for method in METHODS:
            selected = [r for r in rows if r["model"] == model and r["method"] == method]
            assert {r["case_uid"] for r in selected} == set(metadata)
    for r in rows:
        assert all(r[k] is None or 0 <= r[k] <= 1 for k in METRICS)
        assert r["scale"] == ("small" if r["scc_size"] <= 12 else "medium" if 14 <= r["scc_size"] <= 20 else "large")
    return rows


def summarize(rows: list[dict]) -> dict:
    out = {"n": len(rows), "source_scc_n": len({r["physical_scc_uid"] for r in rows})}
    for metric in METRICS:
        values = [r[metric] for r in rows if r[metric] is not None]
        out[metric] = mean(values) if values else None
        out[metric + "_n"] = len(values)
    return out


def grouped(rows, fields, ordered_values):
    import itertools
    output = []
    for values in itertools.product(*ordered_values):
        selected = [r for r in rows if all(r[k] == v for k, v in zip(fields, values))]
        assert selected, (fields, values)
        output.append(dict(zip(fields, values), **summarize(selected)))
    return output


def write_csv(path, rows):
    assert rows
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def tex_rows(groups, field, labels, include_n=False):
    lines = []
    categories = list(dict.fromkeys(g[field] for g in groups))
    for category in categories:
        selected = [r for r in groups if r[field] == category]
        best = {k: max(r[k] for r in selected if r[k] is not None) for k in METRICS}
        for index, row in enumerate(selected):
            cells = [labels[category] if index == 0 else "", r"\textbf{SA-MCGS}" if row["method"] == "sa-mcgs" else METHOD_LABELS[row["method"]]]
            if include_n:
                cells.append(str(row["n"]))
            for key in METRICS:
                value = row[key]
                text = "--" if value is None else f"{value * 100:.2f}"
                if value is not None and abs(value - best[key]) < 1e-10:
                    text = r"\textbf{" + text + "}"
                cells.append(text)
            lines.append(" & ".join(cells) + r" \\")
        if category != categories[-1]:
            lines.append(r"\midrule")
    return "\n".join(lines) + "\n"


def write_tables(groups):
    (TABLES / "five_model_main_rows.tex").write_text(tex_rows(groups["model_method"], "model", MODEL_LABELS))
    for kind, field, labels in [("model", "model", MODEL_LABELS), ("domain", "domain", DOMAIN_LABELS), ("scale", "scale", SCALE_TEX_LABELS)]:
        (TABLES / f"five_model_{kind}_rows.tex").write_text(tex_rows(groups[f"{field}_method"], field, labels, True))
    blocks = []
    for title, kind in [("A. Models", "model"), ("B. Domains", "domain"), ("C. SCC sizes", "scale")]:
        blocks.append(r"\textbf{" + title + r"}\\[0.5mm]" + "\n" +
                      r"\begin{tabular}{@{}llrrrrr@{}}" + "\n" + r"\toprule" + "\n" +
                      "Group & Method & N & Root@3 & Risk-any & Risk-all & Comp. " + r"\\" + "\n" + r"\midrule" + "\n" +
                      (TABLES / f"five_model_{kind}_rows.tex").read_text() + r"\bottomrule" + "\n" + r"\end{tabular}" + "\n")
    wrapper = (
        r"\begin{table*}[t]" + "\n" + r"\centering" + "\n" +
        r"\fontsize{7.5}{9}\selectfont" + "\n" + r"\setlength{\tabcolsep}{2pt}" + "\n" +
        r"\renewcommand{\arraystretch}{1.08}" + "\n" + blocks[0] +
        "\n" + r"\par\medskip" + "\n" +
        r"\begin{minipage}[t]{.49\textwidth}" + "\n" + r"\centering" + "\n" + blocks[1] +
        r"\end{minipage}\hfill" + "\n" +
        r"\begin{minipage}[t]{.49\textwidth}" + "\n" + r"\centering" + "\n" + blocks[2] +
        r"\end{minipage}" + "\n" +
        r"\caption{Five-model results by model, domain, and original SCC size. All metrics are percentages. "
        r"Domain and size summaries pool the same five models. Bold values mark the best method within each group, including ties.}" + "\n" +
        r"\label{tab:appendix_breakdowns}" + "\n" + r"\end{table*}" + "\n"
    )
    (TABLES / "five_model_appendix_breakdowns.tex").write_text(wrapper)


def style():
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
        "font.size": 7, "axes.titlesize": 7.1,
        "axes.labelsize": 7, "xtick.labelsize": 6, "ytick.labelsize": 6,
        "legend.fontsize": 7, "axes.linewidth": 0.6, "lines.linewidth": 1.3,
        "xtick.major.width": 0.5, "ytick.major.width": 0.5,
        "xtick.major.size": 2, "ytick.major.size": 2,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    })


def soft_axes(ax):
    ax.spines[["top", "right"]].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color("#B7C0CB")
    ax.tick_params(colors="#4B5563", pad=2)
    ax.grid(axis="y", color="#E5E7EB", linewidth=.5, zorder=0)


def legend(fig, y):
    handles = [Line2D([0], [0], color=COLORS[m], marker=MARKERS[m], markersize=4.4,
                      linewidth=1.4 if m == "sa-mcgs" else 1.0, label=METHOD_LABELS[m]) for m in METHODS]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.54, y), frameon=False,
               ncol=3, handletextpad=.5, columnspacing=1.5)


def export(fig, filename):
    # Fixed physical dimensions: a 183 mm double-column figure with editable text.
    fig.savefig(FIGURES / f"{filename}.pdf")
    fig.savefig(FIGURES / f"{filename}.svg")
    fig.savefig(FIGURES / f"{filename}.png", dpi=320)
    plt.close(fig)


def plot_scale(groups):
    from redraw_five_model_figures import plot_scale as draw_scale
    draw_scale(groups)


def plot_coverage_compression(groups):
    from redraw_five_model_figures import plot_coverage_compression as draw_profiles
    draw_profiles(groups)


def main():
    for path in [DATA, FIGURES, TABLES]:
        path.mkdir(parents=True, exist_ok=True)
    hashes_before = {str(p.relative_to(ROOT)): sha256(p) for p in [OLD_SOURCE, LLAMA_SOURCE, QWEN_SOURCE]}
    rows = load_rows()
    source_hashes = {}
    for row in rows:
        path = row["source_file"]
        if path in source_hashes:
            assert source_hashes[path] == row["source_sha256"]
        else:
            source_hashes[path] = sha256(Path(path))
        assert source_hashes[path] == row["source_sha256"], path
    groups = {
        "model_method": grouped(rows, ["model", "method"], [MODELS, METHODS]),
        "domain_method": grouped(rows, ["domain", "method"], [DOMAINS, METHODS]),
        "scale_method": grouped(rows, ["scale", "method"], [SCALES, METHODS]),
        "model_domain_method": grouped(rows, ["model", "domain", "method"], [MODELS, DOMAINS, METHODS]),
        "model_scale_method": grouped(rows, ["model", "scale", "method"], [MODELS, SCALES, METHODS]),
    }
    for row in groups["model_method"]:
        actual = [round(row[k] * 100, 2) for k in METRICS]
        expected = ACCEPTED[row["model"]][METHODS.index(row["method"])]
        assert actual == expected, (row["model"], row["method"], actual, expected)
    (DATA / "canonical_case_metrics.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    write_csv(DATA / "canonical_case_metrics.csv", rows)
    for name, values in groups.items():
        write_csv(DATA / (name + ".csv"), values)
    (DATA / "aggregates.json").write_text(json.dumps(groups, ensure_ascii=False, indent=2) + "\n")
    write_tables(groups)
    style()
    plot_scale(groups)
    plot_coverage_compression(groups)
    hashes_after = {str(p.relative_to(ROOT)): sha256(p) for p in [OLD_SOURCE, LLAMA_SOURCE, QWEN_SOURCE]}
    assert hashes_before == hashes_after
    unique_cases = [r for r in rows if r["model"] == MODELS[0] and r["method"] == METHODS[0]]
    audit = {
        "source_summary_hashes": hashes_before, "source_summaries_unchanged": True,
        "raw_source_files_verified": len(source_hashes),
        "rows": len(rows), "models": MODELS, "methods": METHODS,
        "unique_variants": len(unique_cases), "physical_sccs": len({r["physical_scc_uid"] for r in unique_cases}),
        "main_table_values_verified": 60,
        "variant_counts_by_scale": dict(Counter(r["scale"] for r in unique_cases)),
        "variant_counts_by_domain": dict(Counter(r["domain"] for r in unique_cases)),
        "input_mapping": {"root_at_3/root_at3": "root_at3", "stable_case_uid/case_uid": "case_uid", "naive-single/one-shot": "one-shot"},
        "aggregation": "Accepted per-case metrics, arithmetic mean of available measurements; per-metric counts preserved in CSV/JSON. No output re-parsing.",
        "inclusion": "Exactly the five requested models and all 80 matched variants per model/method.",
        "plot_contract": {
            "backend": "python", "archetype": "quantitative grid", "width_mm": 160.02,
            "scale_question": "How do localization and complete risk retention compare across original SCC sizes for each model?",
            "scale_evidence": "Top row localization; bottom row complete endpoint retention. Columns preserve every selected model, bins preserve original scale groups.",
            "coverage_question": "How do complete risk retention and compression jointly change from LEA to SA-MCGS for each model?",
            "summary": "Descriptive means over frozen benchmark variants, not repeated-seed estimates; no inferential error bars or significance tests.",
            "case_unit": "80 variants from 20 source SCCs per model; domain and size aggregates pool the same five models.",
            "reuse": "Style-only inheritance from existing manuscript Python figure palette and physical dimensions.",
            "exports": ["pdf", "svg", "png"],
        },
    }
    (DATA / "asset_validation.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"rows": len(rows), "main_table_values_verified": 60, "case_counts": audit["variant_counts_by_scale"], "data_dir": str(DATA)}, indent=2))


if __name__ == "__main__":
    main()

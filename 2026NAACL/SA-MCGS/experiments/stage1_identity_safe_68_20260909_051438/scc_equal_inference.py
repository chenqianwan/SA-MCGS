#!/usr/bin/env python3
"""Offline SCC-equal addendum; never changes frozen runs or their case estimand."""
from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
FORMAL = HERE / "formal"
FULL = "full-sa-mcgs-rerun"
ARMS = (FULL, "no-relation-first-memory", "no-critical-pair-ledger-revisit",
        "random-local-window-selection")
SEED, REPLICATES = 8229, 20_000


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values, p):
    values = sorted(values)
    position = (len(values) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def interval(values):
    rng = random.Random(SEED)
    draws = [mean(rng.choices(values, k=len(values))) for _ in range(REPLICATES)]
    return [percentile(draws, 0.025), percentile(draws, 0.975)]


def load_results():
    manifest = json.loads((FORMAL / "results_manifest.json").read_text())
    clusters = defaultdict(lambda: defaultdict(dict))
    seen = set()
    for item in manifest["result_index"]:
        path = Path(item["result_file"])
        if digest(path) != item["result_sha256"]:
            raise ValueError(f"Result hash mismatch: {path}")
        result = json.loads(path.read_text())
        case, arm = item["case_uid"], item["variant"]
        if (case, arm) in seen or arm not in ARMS:
            raise ValueError("Duplicate/unknown arm")
        seen.add((case, arm))
        if result["case_uid"] != case or result["ablation_variant"] != arm:
            raise ValueError("Result identity mismatch")
        if result.get("component_ablation_error") or result["domain"] != "sec_ex21":
            raise ValueError("This frozen addendum expects 68 valid SEC cells")
        risks = set(result["injected_risk_nodes"])
        core = set(result["core_evidence_risk_subgraph_nodes"])
        if not risks:
            raise ValueError("Missing risk endpoints")
        values = {"Root@3": float(result["root_top3_hit"]),
                  "Risk-any": float(bool(risks & core)),
                  "Risk-all": float(risks <= core)}
        clusters[item["source_scc_uid"]][case][arm] = values
    if len(seen) != 68 or len(clusters) != 5:
        raise ValueError("Expected 17 cases x 4 arms, 5 source SCCs")
    for cases in clusters.values():
        for arms in cases.values():
            if set(arms) != set(ARMS):
                raise ValueError("Incomplete paired quartet")
    return clusters


def analyse(clusters):
    rows = []
    for metric in ("Root@3", "Risk-any", "Risk-all"):
        for arm in ARMS:
            source_means, paired_deltas, case_values = [], [], []
            for uid in sorted(clusters):
                cases = clusters[uid]
                values = [cases[c][arm][metric] for c in sorted(cases)]
                full = [cases[c][FULL][metric] for c in sorted(cases)]
                source_means.append(mean(values))
                paired_deltas.append(mean(values) - mean(full))
                case_values.extend(values)
            rows.append({"arm": arm, "metric": metric,
                         "case_weighted_descriptive": mean(case_values),
                         "scc_equal_estimate": mean(source_means),
                         "scc_equal_percentile_ci95": interval(source_means),
                         "paired_delta_vs_full": mean(paired_deltas),
                         "paired_delta_ci95": interval(paired_deltas)})
    return rows


def main():
    clusters = load_results()
    rows = analyse(clusters)
    report = {
        "scope": "17 identity-mismatch repair cases; SEC only; 5 source SCCs",
        "estimand": "Mean of within-source-SCC variant means; equal source weights",
        "limitations": "Small, repair-selected subset; not a replacement for an 80-case ablation",
        "frozen_manifest_sha256": digest(FORMAL / "results_manifest.json"),
        "analysis_script_sha256": digest(Path(__file__)),
        "bootstrap_seed": SEED, "bootstrap_replicates": REPLICATES,
        "source_case_counts": {uid: len(clusters[uid]) for uid in sorted(clusters)},
        "results": rows,
    }
    (FORMAL / "scc_equal_inference.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Stage-1：SCC 等权统计补充", "",
             "范围为身份错配修复的 17 个 SEC cases，来自 5 个 source SCC；不是全部 80-case 消融。",
             "先在 SCC 内平均 variants，再对 5 个 SCC 等权；按 SCC 配对 bootstrap 20,000 次。",
             "原报告的 case-weighted 点估计和 cluster-bootstrap 保留；二者统计目标不同，不替换原始结果。", "",
             "| 方法 | Case-level Risk-all | SCC 等权 Risk-all | 相对 Full 差值（95% CI），pp |",
             "|---|---:|---:|---:|"]
    for row in rows:
        if row["metric"] != "Risk-all":
            continue
        lo, hi = row["paired_delta_ci95"]
        lines.append(f"| {row['arm']} | {row['case_weighted_descriptive']:.1%} | "
                     f"{row['scc_equal_estimate']:.1%} | {100*row['paired_delta_vs_full']:+.1f} "
                     f"[{100*lo:+.1f}, {100*hi:+.1f}] |")
    lines += ["", "所有臂 Root@3、Risk-any 均为 100%。只有 5 个簇，区间仅作探索性描述。",
              "这批结果不支持 relation-first/critical-pair 的正向独立贡献，也不能据此断言其他域没有贡献。",
              "本补充为零 API 离线计算，未改冻结 runner、case 选择或任何结果。", ""]
    (FORMAL / "SCC_EQUAL_INFERENCE_ZH.md").write_text("\n".join(lines))
    print(json.dumps({"source_case_counts": report["source_case_counts"],
                      "risk_all": [row for row in rows if row["metric"] == "Risk-all"]}, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Source-SCC-clustered inference for the frozen Stage-2 paired replay.

This script is deliberately offline.  It validates the existing 80 paired
cases, gives every physical source SCC equal weight, and bootstraps source SCCs
rather than treating four injected variants of one SCC as independent cases.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
INPUT = HERE / "summary_stage2_paired_core_cases.csv"
OUTPUT_JSON = HERE / "stage2_clustered_paired_inference.json"
OUTPUT_CSV = HERE / "stage2_clustered_paired_inference.csv"
OUTPUT_MD = HERE / "stage2_clustered_paired_inference.md"

FULL = "full-recompute-replacement"
LOCKED = "locked-no-replacement"
VARIANTS = {FULL, LOCKED}
BOOTSTRAP_REPLICATES = 20_000
BOOTSTRAP_SEED = 8_229


class AuditError(RuntimeError):
    """The frozen Stage-2 input is incomplete or inconsistent."""


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def parse_bool(value: str, *, field: str, case_id: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise AuditError(f"Invalid {field} for {case_id}: {value!r}")


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def mean(values: list[float]) -> float:
    if not values:
        raise AuditError("Cannot average an empty list")
    return sum(values) / len(values)


def load_and_validate() -> dict[str, dict[str, dict[str, str]]]:
    with INPUT.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 160:
        raise AuditError(f"Expected 160 rows (80 cases x 2 policies); found {len(rows)}")

    by_case: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        case_id = row.get("case_id", "")
        variant = row.get("variant_key", "")
        if not case_id or variant not in VARIANTS:
            raise AuditError(f"Bad case/variant row: {case_id!r}/{variant!r}")
        if variant in by_case[case_id]:
            raise AuditError(f"Duplicate {case_id}/{variant}")
        if parse_bool(row.get("invalid", ""), field="invalid", case_id=case_id):
            raise AuditError(f"Invalid Stage-2 cell cannot enter inference: {case_id}/{variant}")
        by_case[case_id][variant] = row

    if len(by_case) != 80:
        raise AuditError(f"Expected 80 paired cases; found {len(by_case)}")

    observed_orders: set[int] = set()
    clusters: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    parity_fields = (
        "case_id",
        "case_order",
        "domain",
        "scc_id",
        "scc_size",
        "template",
        "case_uid",
        "physical_scc_uid",
        "trace_sha256",
    )
    for case_id, arms in by_case.items():
        if set(arms) != VARIANTS:
            raise AuditError(f"Incomplete pair for {case_id}: {sorted(arms)}")
        full, locked = arms[FULL], arms[LOCKED]
        mismatches = [field for field in parity_fields if full[field] != locked[field]]
        if mismatches:
            raise AuditError(f"Pair parity failure for {case_id}: {mismatches}")
        order = int(full["case_order"])
        if order in observed_orders:
            raise AuditError(f"Duplicate case_order: {order}")
        observed_orders.add(order)
        source_uid = full["physical_scc_uid"]
        if not source_uid:
            raise AuditError(f"Missing physical_scc_uid for {case_id}")
        clusters[source_uid][case_id] = arms

    if observed_orders != set(range(1, 81)):
        raise AuditError("case_order must be exactly 1..80")
    if len(clusters) != 20:
        raise AuditError(f"Expected 20 physical source SCCs; found {len(clusters)}")
    bad_sizes = {uid: len(cases) for uid, cases in clusters.items() if len(cases) != 4}
    if bad_sizes:
        raise AuditError(f"Each source SCC must have exactly four variants: {bad_sizes}")
    return clusters


def analyse_metric(
    clusters: dict[str, dict[str, dict[str, str]]],
    metric: str,
    parser: Callable[[str, str], float],
) -> dict[str, Any]:
    cluster_values: list[dict[str, float]] = []
    improved = tied = worsened = 0
    for source_uid in sorted(clusters):
        full_values: list[float] = []
        locked_values: list[float] = []
        for case_id in sorted(clusters[source_uid]):
            arms = clusters[source_uid][case_id]
            full_value = parser(arms[FULL][metric], case_id)
            locked_value = parser(arms[LOCKED][metric], case_id)
            full_values.append(full_value)
            locked_values.append(locked_value)
            delta = full_value - locked_value
            improved += delta > 0
            tied += delta == 0
            worsened += delta < 0
        full_mean = mean(full_values)
        locked_mean = mean(locked_values)
        cluster_values.append(
            {
                "full": full_mean,
                "locked": locked_mean,
                "delta": full_mean - locked_mean,
            }
        )

    point = {
        key: mean([row[key] for row in cluster_values])
        for key in ("full", "locked", "delta")
    }
    rng = random.Random(BOOTSTRAP_SEED)
    replicates = {key: [] for key in point}
    n_clusters = len(cluster_values)
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = [cluster_values[rng.randrange(n_clusters)] for _ in range(n_clusters)]
        for key in replicates:
            replicates[key].append(mean([row[key] for row in sample]))
    intervals = {
        key: [quantile(values, 0.025), quantile(values, 0.975)]
        for key, values in replicates.items()
    }
    return {
        "metric": metric,
        "point": point,
        "clustered_percentile_95_ci": intervals,
        "case_discordance_full_minus_locked": {
            "improved": improved,
            "tied": tied,
            "worsened": worsened,
        },
        "source_scc_cluster_values": cluster_values,
    }


def bool_parser(field: str) -> Callable[[str, str], float]:
    def parse(value: str, case_id: str) -> float:
        return float(parse_bool(value, field=field, case_id=case_id))

    return parse


def float_parser(value: str, case_id: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise AuditError(f"Invalid numeric metric for {case_id}: {value!r}") from exc


def pct(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def main() -> None:
    clusters = load_and_validate()
    analyses = [
        analyse_metric(clusters, "risk_any", bool_parser("risk_any")),
        analyse_metric(clusters, "risk_all", bool_parser("risk_all")),
        analyse_metric(clusters, "risk_coverage", float_parser),
    ]
    payload = {
        "schema_version": "stage2_source_scc_clustered_inference_v1",
        "input": str(INPUT),
        "input_sha256": file_sha256(INPUT),
        "paired_cases": 80,
        "source_scc_clusters": len(clusters),
        "variants_per_source_scc": 4,
        "bootstrap": {
            "unit": "physical_scc_uid",
            "within_cluster_aggregation": "equal mean over the four injected variants",
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "interval": "percentile 95%",
        },
        "analyses": analyses,
        "claim_boundary": (
            "Intervals quantify uncertainty across the 20 frozen physical source SCCs. "
            "They do not establish population prevalence or deployment validity."
        ),
    }
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    csv_rows: list[dict[str, Any]] = []
    for result in analyses:
        metric = result["metric"]
        point = result["point"]
        ci = result["clustered_percentile_95_ci"]
        discordance = result["case_discordance_full_minus_locked"]
        csv_rows.append(
            {
                "metric": metric,
                "full": point["full"],
                "full_ci_low": ci["full"][0],
                "full_ci_high": ci["full"][1],
                "locked": point["locked"],
                "locked_ci_low": ci["locked"][0],
                "locked_ci_high": ci["locked"][1],
                "delta_full_minus_locked": point["delta"],
                "delta_ci_low": ci["delta"][0],
                "delta_ci_high": ci["delta"][1],
                "improved_cases": discordance["improved"],
                "tied_cases": discordance["tied"],
                "worsened_cases": discordance["worsened"],
            }
        )
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)

    lines = [
        "# Stage-2 source-SCC 聚类配对区间",
        "",
        "状态：80/80 配对 case、20 个 physical source SCC 均通过离线身份与 trace parity 门禁；0 API。",
        "",
        "| Metric | Full replacement | Locked no-replacement | Δ Full−Locked | case discordance (+/=/-) |",
        "|---|---:|---:|---:|---:|",
    ]
    labels = {"risk_any": "Risk-any", "risk_all": "Risk-all", "risk_coverage": "Risk coverage"}
    for row in csv_rows:
        lines.append(
            f"| {labels[row['metric']]} "
            f"| {pct(row['full'])} [{pct(row['full_ci_low'])}, {pct(row['full_ci_high'])}] "
            f"| {pct(row['locked'])} [{pct(row['locked_ci_low'])}, {pct(row['locked_ci_high'])}] "
            f"| {pct(row['delta_full_minus_locked'])} "
            f"[{pct(row['delta_ci_low'])}, {pct(row['delta_ci_high'])}] "
            f"| {row['improved_cases']}/{row['tied_cases']}/{row['worsened_cases']} |"
        )
    lines.extend(
        [
            "",
            f"区间为 `{BOOTSTRAP_REPLICATES:,}` 次 physical-SCC clustered percentile bootstrap（seed={BOOTSTRAP_SEED}）。",
            "同一 SCC 的四个注入 variants 先等权汇总，三位专家或四个 variants 均不作为独立 source SCC。",
            "该区间只描述冻结的 20 个 source SCC，不用于声称真实总体风险率或部署有效性。",
            "",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"passed": True, "json": str(OUTPUT_JSON), "markdown": str(OUTPUT_MD)}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check real outputs against original records and older metric code; save a report."""
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean

import analyze

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_text())


def verify():
    labels = {r["presentation_id"]: r for r in read("final_labels_with_separate_references.json")}
    rows = read("post_case_metrics.json")
    manifest = json.loads((analyze.PREP / "frontend/data/manifest.json").read_text())
    sections = {r["presentation_id"]: {s["section_id"] for s in r["sections"]} for r in manifest["cases"]}
    assert len(labels) == 42 and len(rows) == 144
    assert sum(len(r["references"]) == 1 for r in labels.values()) == 14
    assert sum(len(r["references"]) == 2 for r in labels.values()) == 28
    metric_map = {"minimal_evidence_recall": "expert_evidence_recall", "repair_coverage": "repair_packet_coverage",
                  "outside_repair_rate": "excess_node_rate", "bridge_aware_precision": "bridge_aware_precision",
                  "bridge_aware_excess_rate": "bridge_aware_excess_node_rate", "minimal_evidence_density": "expert_evidence_density"}
    references_checked = 0
    for row in rows:
        pid = row["presentation_id"]
        assert len(row["references_scored"]) == len(labels[pid]["references"])
        for ref, scored in zip(labels[pid]["references"], row["references_scored"]):
            # Adapter only to call the previously existing, separately implemented
            # single-reference mathematics; not a new label or consensus artifact.
            diagnostic = {"annotation_protocol": "binary_judgment_v1", "sets_reviewed": True,
                          "target_conflict": ref["target_conflict"], "judgment_sufficient": ref["judgment_sufficient"],
                          "confidence": ref["confidence"], "sections": {s: {
                              "minimal_evidence": s in ref["minimal_evidence_section_ids"],
                              "repair_packet": s in ref["repair_packet_section_ids"]} for s in sections[pid]}}
            expected = analyze.aa.binary_case_metrics(diagnostic, sections[pid], row["returned_sections"],
                prediction="present" if row["valid"] else "invalid", output_valid=row["valid"],
                bridge_section_ids=row["bridge_sections"])
            for actual_key, old_key in metric_map.items():
                assert math.isclose(scored[actual_key], expected[old_key], abs_tol=1e-12)
            references_checked += 1
        for metric in metric_map:
            assert math.isclose(row[metric], mean(x[metric] for x in row["references_scored"]), abs_tol=1e-12)
    # Concrete hand-check: predicted S001,S005,S007,S008; minimal S002,S008,S010.
    # Repair references contain 8 and 7 nodes with 3 retrieved in each. Average
    # coverage is (3/8+3/7)/2 = 45/112, not coverage against a merged reference.
    spot = next(r for r in rows if (r["presentation_id"], r["method"], r["model"]) == ("P-22E78DB472", "one-shot", "gpt-4o"))
    assert spot["returned_sections"] == ["S001", "S005", "S007", "S008"]
    assert math.isclose(spot["minimal_evidence_recall"], 1/3)
    assert math.isclose(spot["repair_coverage"], 45/112)
    assert spot["repair_precision"] == 3/4 and spot["outside_repair_rate"] == 1/4
    for summary in read("post_summary.json")["rows"]:
        group = [r for r in rows if (r["model"], r["method"]) == (summary["model"], summary["method"])]
        by_cluster = defaultdict(list)
        for r in group:
            by_cluster[r["source_scc_uid"]].append(r)
        assert len(by_cluster) == 14
        for metric, stats in summary["metrics"].items():
            point = mean(mean(r[metric] for r in group) for group in by_cluster.values())
            assert math.isclose(point, stats["source_equal_mean"], abs_tol=1e-12)
            assert math.isclose(mean(r[metric] for r in group), stats["variant_mean"], abs_tol=1e-12)
    pre = read("pre_case_metrics.json")
    assert len(pre) == 162
    reconstructed = [r for r in pre if r["reconstructed_first_status"]]
    assert len(reconstructed) == 2 and all(r["invalid"] == 1 for r in reconstructed)
    for row in pre:
        assert row["false_positive"] + row["abstain"] + row["invalid"] == 1
        assert row["valid"] == row["false_positive"] + row["abstain"]
        assert labels[row["presentation_id"]]["target_conflict"] == "absent"
    for item in read("source_manifest.json")["source_files"]:
        assert hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"], item["path"]
    retry_calls = [call for runs in read("lea_attempt_history.json")["gpt"]["cases"].values() for run in runs[1:] for call in run["calls"]]
    assert len(retry_calls) == 63
    assert sum(c["usage"]["prompt_tokens"] for c in retry_calls) == 153448
    assert sum(c["usage"]["completion_tokens"] for c in retry_calls) == 107941
    result = {"status": "PASS", "post_method_cases": len(rows), "separate_reference_checks": references_checked,
                      "pre_protocol_cases": len(pre), "labels": len(labels), "source_hashes": "all_match",
                      "source_file_count": len(read("source_manifest.json")["source_files"]),
                      "checks": ["all separate post references match existing single-reference scoring code",
                                 "dual-reference metrics averaged before source aggregation",
                                 "all source-equal point estimates independently recomputed",
                                 "pre decision partition and expert-negative eligibility",
                                 "two GPT LEA first-run failures reconstructed only from append-only log",
                                 "all source hashes unchanged", "LEA retry call/token totals independently summed"],
                      "hand_calculation": {"presentation_id": "P-22E78DB472", "repair_coverage": "45/112"}}
    (HERE / "VALIDATION.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    verify()

#!/usr/bin/env python3
"""Offline, source-preserving analysis of the actual 42/42/14 expert audit.

No spreadsheet parsing, network clients, model calls, or original-file changes.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
ROOT = PAPER.parents[1]
PREP = PAPER / "annotation_prep"
SEED = 20260922
BOOTSTRAPS = 20000
SOURCES = {}
MODELS = ("gpt-4o", "gemini-2.5-pro")
METHODS = ("one-shot", "lea", "sa-mcgs")


def source(path):
    path = Path(path).resolve()
    if path not in SOURCES:
        SOURCES[path] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return path


def read(path):
    return json.loads(source(path).read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, source(path))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


aa = module("existing_annotation_analysis", PREP / "analysis_v1/annotation_analysis.py")
audit = module("existing_identity_audit", PREP / "baseline_audit/audit_baseline_coverage.py")


def output(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def output_csv(name, rows):
    with (HERE / name).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summary(rows, metric):
    point, lower, upper, n, clusters = aa.cluster_bootstrap_ci(
        rows, metric, samples=BOOTSTRAPS, seed=SEED)
    return {"variant_mean": mean(r[metric] for r in rows if r.get(metric) is not None),
            "source_equal_mean": point, "source_equal_ci95": [lower, upper],
            "n_cases": n, "n_source_scc": clusters}


def iaa(records):
    result = []
    for pair in (("expert_1", "expert_2"), ("expert_1", "expert_3"), ("expert_2", "expert_3")):
        for condition in ("all", "pre", "post"):
            eligible = [r for r in records if all(p in r["original_ratings"] for p in pair)
                        and (condition == "all" or r["condition"] == condition)]
            row = {"raters": list(pair), "condition": condition, "n": len(eligible),
                   "targeted_subset": "expert_3" in pair}
            for field in ("target_conflict", "judgment_sufficient"):
                a, b = ([r["original_ratings"][p][field] for r in eligible] for p in pair)
                row[field] = aa._pairwise_agreement(a, b)
                row[field]["agreement_count"] = sum(x == y for x, y in zip(a, b))
                row[field]["rater_label_counts"] = {pair[0]: dict(Counter(a)), pair[1]: dict(Counter(b))}
            row["joint_agreement_count"] = sum(all(r["original_ratings"][pair[0]][f] == r["original_ratings"][pair[1]][f]
                                                     for f in ("target_conflict", "judgment_sufficient")) for r in eligible)
            for field in ("minimal_evidence_section_ids", "repair_packet_section_ids"):
                values = []
                nonempty_values = []
                exact = 0
                for r in eligible:
                    a, b = (set(r["original_ratings"][p][field]) for p in pair)
                    value = aa.jaccard(a, b)
                    values.append(value)
                    if a or b:
                        nonempty_values.append(value)
                    exact += a == b
                row[field] = {"mean_jaccard": mean(values), "exact_agreement_count": exact,
                              "nonempty_union_n": len(nonempty_values),
                              "mean_jaccard_excluding_both_empty": mean(nonempty_values) if nonempty_values else None}
            result.append(row)
    return result


def main():
    source(HERE / "analyze.py")
    source(HERE / "verify.py")
    for relative in ("experiments/lea_update/run_pre_lea.py", "experiments/sa_update/run_pre_sa.py",
                     "experiments/pre_baseline_update/run_pre_one_shot.py",
                     "experiments/lea_runs/lea_pre_gpt18_20260829/summary_pre_lea_breakdown.csv",
                     "experiments/lea_update/LEA_UPDATE_STATUS_ZH.md",
                     "experiments/pre_baseline_runs/pre_baseline_v1_20260909/PRE_BASELINE_FINAL_REPORT_ZH.md"):
        source(PAPER / relative)
    adj = read(PREP / "third_expert_review/internal/adjudication_20260920/adjudicated_records.json")
    unsigned = copy.deepcopy(adj)
    unsigned.pop("artifact_hash")
    assert aa.canonical_sha256(unsigned) == adj["artifact_hash"]
    codebook = read(PREP / "internal/private_codebook.json")
    public = read(PREP / "frontend/data/manifest.json")
    hints = read(PREP / "frontend/data/method_hints.json")
    assert aa.canonical_sha256({k: v for k, v in hints.items() if k != "hint_pack_hash"}) == hints["hint_pack_hash"]
    assert aa.recompute_manifest_hash(public) == public["manifest_hash"] == adj["parent_manifest_hash"]
    assert codebook["manifest_hash"] == public["manifest_hash"] == hints["source_manifest_hash"]
    records = adj["records"]
    identities = {r["presentation_id"]: r for r in codebook["records"]}
    public_cases = {r["presentation_id"]: r for r in public["cases"]}
    assert len(records) == len(identities) == len(public_cases) == 42
    catalog = {r["post_case_uid"]: r for r in read(PREP / "candidates/master_manifest.json")["post_presentations"]}
    plans = {r["case_id"]: r for r in read(PAPER / "validation/identity_stage2_80/case_plan.json")}
    with source(PREP / "baseline_audit/baseline_coverage.csv").open(newline="") as f:
        coverage = {(r["canonical_case_id"], r["model"], r["method"]): r for r in csv.DictReader(f)}
    finalized = []
    for r in records:
        pid = r["presentation_id"]
        master = identities[pid]["master_record"]
        assert r["source_physical_fingerprint"] == master["source_physical_fingerprint"]
        section_ids = {s["section_id"] for s in public_cases[pid]["sections"]}
        assert section_ids == {s["section_id"] for s in identities[pid]["section_map"]}
        for vote in r["original_ratings"].values():
            assert set(vote["minimal_evidence_section_ids"]) <= set(vote["repair_packet_section_ids"]) <= section_ids
        if r["reviewed_by_expert_3"]:
            label = r["final_label"]
            references = [{"rater": "expert_3", **r["original_ratings"]["expert_3"]}]
            for key, value in r["original_ratings"]["expert_3"].items():
                if key != "source_xlsx_row":
                    assert value == label[key]
        else:
            for field in ("target_conflict", "judgment_sufficient"):
                assert r["original_ratings"]["expert_1"][field] == r["original_ratings"]["expert_2"][field]
            label = r["original_ratings"]["expert_1"]
            references = [{"rater": e, **r["original_ratings"][e]} for e in ("expert_1", "expert_2")]
        assert label["judgment_sufficient"] == "yes"
        assert label["target_conflict"] == ("absent" if r["condition"] == "pre" else "present")
        finalized.append({"presentation_id": pid, "condition": r["condition"], "domain": r["domain"],
                          "source_scc_uid": r["source_physical_fingerprint"],
                          "resolution": r["resolution_status"], "target_conflict": label["target_conflict"],
                          "judgment_sufficient": label["judgment_sufficient"], "references": references})
    output("final_labels_with_separate_references.json", finalized)
    iaa_results = iaa(records)
    output("iaa.json", {"empty_empty_jaccard": 1, "rows": iaa_results})
    post_rows = []
    for r in finalized:
        if r["condition"] != "post":
            continue
        pid = r["presentation_id"]
        identity = identities[pid]
        master = identity["master_record"]
        mapping = {s["original_node_id"]: s["section_id"] for s in identity["section_map"]}
        cat = catalog[master["post_case_uid"]]
        assert cat["source_physical_fingerprint"] == r["source_scc_uid"]
        bridge = cat["injection_identity"].get("bridge_node")
        bridges = {mapping[bridge]} if bridge else set()
        for model in MODELS:
            for method in METHODS:
                cov = coverage[master["canonical_case_id"], model, method]
                assert cov["source_physical_uid"] == r["source_scc_uid"]
                assert cov["variant_case_uid"] == master["post_case_uid"]
                assert cov["coverage_status"] in ("available_exact", "available_strict_invalid", "strict_invalid")
                raw_path = Path(cov["source_file"])
                if not raw_path.is_absolute():
                    raw_path = ROOT / raw_path
                payload = read(raw_path)
                if method == "lea":
                    result = payload
                else:
                    raw_records = payload if isinstance(payload, list) else payload["results"]
                    matches = [x for x in raw_records if x["model"] == model and x["method"] == ("naive" if method == "one-shot" else method)]
                    assert len(matches) == 1
                    result = matches[0]
                valid = cov["coverage_status"] == "available_exact" and not (result.get("cost_audit_error") or result.get("error"))
                if valid:
                    ok, detail = audit.validate_identity(result, plans[master["canonical_case_id"]])
                    assert ok, (pid, method, model, detail)
                selected_field = {"one-shot": "direct_risk_subgraph_nodes", "lea": "lea_risk_subgraph_nodes", "sa-mcgs": "core_evidence_risk_subgraph_nodes"}[method]
                assert not valid or selected_field in result
                nodes = set(result[selected_field]) if valid else set()
                assert nodes <= mapping.keys()
                returned = {mapping[n] for n in nodes}
                if method != "one-shot":
                    hint_sections = hints["cases"][pid]["sections"]
                    recovered = {s for s, v in hint_sections.items() if v["methods"][method]["models"][model].get("selected")}
                    assert returned == recovered
                values = []
                for ref in r["references"]:
                    minimal = set(ref["minimal_evidence_section_ids"])
                    repair = set(ref["repair_packet_section_ids"])
                    assert minimal and repair
                    allowed = repair | bridges
                    values.append({"rater": ref["rater"],
                        "minimal_evidence_recall": len(returned & minimal) / len(minimal),
                        "repair_coverage": len(returned & repair) / len(repair),
                        "repair_precision": len(returned & repair) / len(returned) if returned else 0.0,
                        "outside_repair_rate": len(returned - repair) / len(returned) if returned else 0.0,
                        "bridge_aware_precision": len(returned & allowed) / len(returned) if returned else 0.0,
                        "bridge_aware_excess_rate": len(returned - allowed) / len(returned) if returned else 0.0,
                        "minimal_evidence_density": len(returned & minimal) / len(returned) if returned else 0.0})
                row = {k: r[k] for k in ("presentation_id", "source_scc_uid", "domain")}
                row.update({"method": method, "model": model, "valid": valid, "source_path": str(raw_path),
                            "prediction_field": selected_field, "returned_sections": sorted(returned),
                            "bridge_sections": sorted(bridges), "references_scored": values,
                            "returned_nodes": len(returned), "compression": 1-len(returned)/len(mapping)})
                row.update({metric: mean(v[metric] for v in values) for metric in values[0] if metric != "rater"})
                post_rows.append(row)
    assert len(post_rows) == 24 * 2 * 3
    metrics = [k for k in post_rows[0]["references_scored"][0] if k != "rater"]
    post_summary = []
    paired = []
    for model in MODELS:
        for method in METHODS:
            rows = [r for r in post_rows if r["model"] == model and r["method"] == method]
            post_summary.append({"model": model, "method": method, "valid_n": sum(r["valid"] for r in rows),
                                 "metrics": {m: summary(rows, m) for m in metrics}})
        for comparator in ("one-shot", "lea"):
            sa = {r["presentation_id"]: r for r in post_rows if r["model"] == model and r["method"] == "sa-mcgs"}
            comp = {r["presentation_id"]: r for r in post_rows if r["model"] == model and r["method"] == comparator}
            diffs = [{"source_scc_uid": row["source_scc_uid"], **{m: row[m]-comp[pid][m] for m in metrics}} for pid, row in sa.items()]
            paired.append({"model": model, "contrast": "sa-mcgs minus " + comparator,
                           "metrics": {m: summary(diffs, m) for m in metrics}})
    output("post_case_metrics.json", post_rows)
    output_csv("post_case_metrics.csv", [{k: v for k, v in r.items() if k not in ("returned_sections", "bridge_sections", "references_scored")} for r in post_rows])
    output("post_summary.json", {"rows": post_summary, "paired_contrasts": paired})

    pre_rows = []
    retry_root = PAPER / "experiments/pre_baseline_runs/pre_baseline_v1_20260909"
    lea_history = {}
    for alias in ("gpt", "gemini"):
        log_path = source(PAPER / f"experiments/lea_runs/lea_pre_{alias}18_20260829/call_logs/llm_calls.jsonl")
        attempts = defaultdict(list)
        for number, line in enumerate(log_path.read_text().splitlines(), 1):
            event = json.loads(line)
            case = event["case_id"]
            if event.get("call_index") == 1:
                attempts[case].append({"start_line": number, "started_at": event["started_at"],
                    "source_identity": {k: event[k] for k in ("case_id", "scc_id", "model", "method", "condition", "domain")},
                    "calls": [], "terminal_failures": []})
            if "call_index" in event:
                attempts[case][-1]["calls"].append({"line": number, "usage": event.get("usage", {}), "ok": event["ok"]})
            if event.get("event") == "terminal_json_or_api_failure":
                attempts[case][-1]["terminal_failures"].append({"line": number, "recorded_at": event["recorded_at"], "error": event["error"]})
        lea_history[alias] = {"source_path": str(log_path), "cases": dict(attempts)}
    assert {case for case, runs in lea_history["gpt"]["cases"].items() if len(runs) > 1} == {
        "pre_cuad_25_e97c2968e072__gpt-4o", "pre_cuad_34_0e1882106beb__gpt-4o"}
    assert all(len(runs) == 1 for runs in lea_history["gemini"]["cases"].values())
    output("lea_attempt_history.json", lea_history)
    for model in MODELS:
        alias = "gpt" if model == "gpt-4o" else "gemini"
        first_dirs = {"one-shot": retry_root / "one_shot_full/results",
                      "lea": PAPER / f"experiments/lea_runs/lea_pre_{alias}18_20260829/results",
                      "sa-mcgs": PAPER / f"experiments/sa_runs/sa_pre_{alias}18_20260829/results"}
        retry_dir = retry_root / ("sa_retry_gpt10/results" if alias == "gpt" else "sa_retry_gemini14/results")
        retry_by_source = {}
        for path in sorted(retry_dir.glob("*.json")):
            result = read(path)
            retry_by_source[result["pre_source_id"]] = (path, result)
        for method, directory in first_dirs.items():
            by_source = {}
            for path in sorted(directory.glob("*.json")):
                result = read(path)
                if result["model"] == model:
                    by_source[result["pre_source_id"]] = (path, result)
            assert len(by_source) == 18
            for r in finalized:
                if r["condition"] != "pre":
                    continue
                master = identities[r["presentation_id"]]["master_record"]
                source_id = master["pre_source_id"]
                first_path, first = by_source[source_id]
                latest_path, latest = first_path, first
                lea_runs = lea_history[alias]["cases"].get(first["case_id"], []) if method == "lea" else []
                if method == "lea":
                    assert lea_runs
                    for run in lea_runs:
                        identity = run["source_identity"]
                        assert identity == {"case_id": first["case_id"], "scc_id": source_id, "model": model,
                                            "method": method, "condition": "pre", "domain": r["domain"]}
                if method == "lea" and len(lea_runs) > 1:
                    assert len(lea_runs) == 2 and lea_runs[0]["terminal_failures"]
                    # The runner overwrote these two result JSONs. Preserve the
                    # final JSON and reconstruct only first-run invalid status,
                    # not any unavailable original output text or selected set.
                    first = {k: latest[k] for k in ("case_id", "case_uid", "source_physical_fingerprint", "pre_content_fingerprint", "condition", "inject_mode", "abstention_rule")}
                    first.update({"target_conflict_decision": "invalid", "cost_audit_error": lea_runs[0]["terminal_failures"][0]["error"],
                                  "reconstructed_first_status": True, "original_result_json_available": False,
                                  "log_terminal_failure_lines": [v["line"] for v in lea_runs[0]["terminal_failures"]]})
                    first_path = Path(lea_history[alias]["source_path"])
                attempts = [("first", first_path, first, [first_path])]
                if method == "lea" and model == "gpt-4o":
                    attempts.append(("recovery", latest_path, latest, [first_path] + ([latest_path] if latest_path != first_path else [])))
                if method == "sa-mcgs":
                    recovered_path, recovered = retry_by_source.get(source_id, (first_path, first))
                    if source_id in retry_by_source:
                        assert first["target_conflict_decision"] == "invalid"
                        assert first["case_uid"] == recovered["case_uid"]
                    attempts.append(("recovery", recovered_path, recovered, [first_path] + ([recovered_path] if recovered_path != first_path else [])))
                for protocol, path, result, attempt_paths in attempts:
                    assert result["source_physical_fingerprint"] == r["source_scc_uid"]
                    assert result["pre_content_fingerprint"] == master["pre_content_fingerprint"]
                    assert result["condition"] == "pre" and result["inject_mode"] is False
                    decision = result["target_conflict_decision"]
                    assert decision in ("invalid", "assert_target_conflict", "abstain_from_target_conflict")
                    assert (decision == "invalid") == bool(result["cost_audit_error"])
                    if decision != "invalid":
                        assert (decision == "assert_target_conflict") == bool(result["explicit_conflict_pairs"])
                        assert set(result["scc_clause_ids"]) == set(master["ordered_clause_ids"])
                        for pair in result["explicit_conflict_pairs"]:
                            assert pair["source"] != pair["target"]
                            assert {pair["source"], pair["target"]} <= set(master["ordered_clause_ids"])
                            assert isinstance(pair["reason"], str) and pair["reason"].strip()
                    if method == "lea" and not result.get("reconstructed_first_status"):
                        node_hints = hints["cases"][r["presentation_id"]]["sections"].values()
                        statuses = {v["methods"][method]["models"][model]["status"] for v in node_hints}
                        assert statuses == ({"available"} if decision != "invalid" else {"strict_invalid"})
                    pre_rows.append({"presentation_id": r["presentation_id"], "source_scc_uid": r["source_scc_uid"],
                                     "domain": r["domain"], "model": model, "method": method, "protocol": protocol,
                                     "source_path": str(path), "attempt_paths": [str(p) for p in attempt_paths],
                                     "reconstructed_first_status": result.get("reconstructed_first_status", False),
                                     "log_terminal_failure_lines": result.get("log_terminal_failure_lines", []),
                                     "decision": decision, "rule": result["abstention_rule"],
                                     "valid": float(decision != "invalid"), "false_positive": float(decision == "assert_target_conflict"),
                                     "abstain": float(decision == "abstain_from_target_conflict"), "invalid": float(decision == "invalid")})
    pre_summary = []
    for model in MODELS:
        for method in METHODS:
            has_recovery = method == "sa-mcgs" or (method == "lea" and model == "gpt-4o")
            for protocol in (("first", "recovery") if has_recovery else ("first",)):
                rows = [r for r in pre_rows if (r["model"], r["method"], r["protocol"]) == (model, method, protocol)]
                assert len(rows) == 18
                pre_summary.append({"model": model, "method": method, "protocol": protocol,
                    "counts": {m: int(sum(r[m] for r in rows)) for m in ("valid", "false_positive", "abstain", "invalid")},
                    "metrics": {m: summary(rows, m) for m in ("valid", "false_positive", "abstain", "invalid")},
                    "false_positive_given_valid": sum(r["false_positive"] for r in rows) / sum(r["valid"] for r in rows)})
    output("pre_case_metrics.json", pre_rows)
    output("pre_summary.json", pre_summary)
    output_csv("pre_summary.csv", [{"model": r["model"], "method": r["method"], "protocol": r["protocol"], "N": 18, **r["counts"],
        "false_positive_given_valid": r["false_positive_given_valid"]} for r in pre_summary])
    output("source_manifest.json", {"analysis_script": str(HERE / "analyze.py"), "bootstrap_samples": BOOTSTRAPS,
        "seed": SEED, "source_files": list(SOURCES.values()), "original_xlsx_provenance_from_frozen_adjudication": adj["source_files"],
        "original_xlsx_reopened": False, "new_api_calls": 0})
    write_report(finalized, iaa_results, post_summary, paired, pre_summary)


def percent(value):
    return f"{100*value:.1f}"


def ci(value):
    return f"{percent(value['source_equal_mean'])} [{percent(value['source_equal_ci95'][0])}, {percent(value['source_equal_ci95'][1])}]"


def write_report(labels, iaa_rows, posts, contrasts, pres):
    post_labels = [r for r in labels if r["condition"] == "post"]
    lines = ["# Expert audit: offline analysis, 22 September 2026", "",
        "The current audit contains 18 unmodified originals and 24 newly annotated injected variants; two experts rated all 42 presentations and a third independently reviewed 14 selected presentations (9 pre, 5 post). There are 98 actual judgments. All 18 originals are finally absent/sufficient and all 24 injected variants present/sufficient. These are expert labels, not model accuracies.", "",
        f"New post: 24 variants from {len({r['source_scc_uid'] for r in post_labels})} source SCCs. Pre: 18 originals from 18 source SCCs. The historical 12-case audit remains a separate stratum; its worksheets were not reopened or merged in this analysis.", "",
        "## Original inter-annotator agreement", "",
        "Agreement is computed before adjudication. The third expert's targeted subset is reported separately and is not a random three-rater sample. Cohen's kappa is undefined when both marginal distributions contain only one category. Empty/empty set Jaccard is 1; post-only set agreement avoids the empty negative-evidence inflation.", "",
        "| Pair | Scope | N | Target agreement | Target kappa | Sufficiency agreement | Sufficiency kappa | Joint agreement | Minimal Jaccard | Repair Jaccard |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in iaa_rows:
        def k(field):
            v = row[field]["cohen_kappa"]
            return "undefined" if v is None else f"{v:.3f}"
        lines.append(f"| {'/'.join(row['raters'])} | {row['condition']} | {row['n']} | {row['target_conflict']['agreement_count']}/{row['n']} | {k('target_conflict')} | {row['judgment_sufficient']['agreement_count']}/{row['n']} | {k('judgment_sufficient')} | {row['joint_agreement_count']}/{row['n']} | {row['minimal_evidence_section_ids']['mean_jaccard']:.3f} | {row['repair_packet_section_ids']['mean_jaccard']:.3f} |")
    lines += ["", "## Post evidence quality", "",
        "For the five adjudicated post cases, all reference fields come from the third expert's complete answer. For the other 19 post cases, each prediction is scored separately against the two original references and the two metric values are averaged within the case; no union or intersection of expert gold sets is used. Minimal recall = |returned intersect minimal|/|minimal|; repair coverage = |returned intersect repair|/|repair|; repair precision = |returned intersect repair|/|returned|. Repair packets already permit explanation and supporting material. The bridge-aware sensitivity allows the independently frozen injection bridge in addition to each individual repair reference. Outside-reference nodes are not established to be irrelevant.", "",
        "SA uses the deployable core_evidence_risk_subgraph_nodes field, LEA uses lea_risk_subgraph_nodes, and One-shot uses direct_risk_subgraph_nodes. LEA/SA selections were checked against the frozen hint export. The historical SA risk_subgraph_nodes field can be anchored on injected ground truth and is excluded from this expert comparison. This output-field distinction must also be stated if historical benchmark metrics using a different field appear nearby. Valid outputs were checked against exact clause/injection identities; invalid One-shot outcomes retain the identity established in the frozen coverage audit. Failed or empty outputs retain their cases: recall, coverage, precision, density, and excess are zero by the existing analysis convention; therefore precision plus excess need not equal 100% in an aggregate containing such cases. Report validity beside these measures.", "",
        "The main estimates average variants within each source SCC, then weight source SCCs equally. Brackets are percentile 95% intervals from 20,000 source-SCC bootstrap draws (seed 20260922). Descriptive variant means are reported separately. These small selected-sample intervals do not support population prevalence claims.", "",
        "| Model | Method | Valid / 24 | Minimal recall % [CI] | Repair coverage % [CI] | Repair precision % [CI] | Outside repair % [CI] | Bridge-aware precision % [CI] |",
        "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in posts:
        m = r["metrics"]
        lines.append(f"| {r['model']} | {r['method']} | {r['valid_n']}/24 | " + " | ".join(ci(m[k]) for k in ("minimal_evidence_recall", "repair_coverage", "repair_precision", "outside_repair_rate", "bridge_aware_precision")) + " |")
    lines += ["", "Variant-weighted descriptive means (same 24-case denominator):", "", "| Model | Method | Minimal recall % | Repair coverage % | Repair precision % | Outside repair % |", "|---|---|---:|---:|---:|---:|"]
    for r in posts:
        lines.append(f"| {r['model']} | {r['method']} | " + " | ".join(percent(r['metrics'][k]['variant_mean']) for k in ("minimal_evidence_recall", "repair_coverage", "repair_precision", "outside_repair_rate")) + " |")
    lines += ["", "Paired source-SCC contrasts (percentage points; positive means higher for SA):", "", "| Model | Contrast | Minimal recall difference [CI] | Repair coverage difference [CI] | Repair precision difference [CI] |", "|---|---|---:|---:|---:|"]
    for r in contrasts:
        lines.append(f"| {r['model']} | {r['contrast']} | " + " | ".join(ci(r['metrics'][k]) for k in ("minimal_evidence_recall", "repair_coverage", "repair_precision")) + " |")
    lines += ["", "## Pre negative-case audit", "",
        "The stored decision rule asserts a target conflict only when a raw conflict record (a rollout conflict for SA) has two distinct exact SCC IDs and a nonempty reason. A valid output with no accepted pair is operational abstention; it is not a separately elicited negative judgment. Nonempty selected subgraphs are not used to infer assertions. An invalid output is never treated as a correct abstention. Since all 18 expert labels are negative, each stored valid assertion is a false positive under this operational rule. Natural-positive recall is not estimable (N = 0).", "",
        "First means the original complete run, including its within-run schema retries. SA recovery permits exactly one additional complete run on each original strict failure (10 GPT and 14 Gemini); the original SA result files remain preserved. GPT LEA also reran its two original failures on 29 August: CUAD25 recovered and CUAD34 remained invalid. That runner overwrote the two original result JSONs, so their first-run invalid status is reconstructed only from the append-only call log, with exact line provenance; unavailable original output text and selections are not reconstructed. Gemini LEA and One-shot have no additional complete-run recovery here. Recovery is a reliability/cost sensitivity, not an equal-opportunity single-run comparison. The SA retry report accounts for 1,140 additional retry calls, 5,011,988 tokens and estimated $26.766918; GPT LEA recovery adds 63 calls and 261,389 tokens (153,448 input + 107,941 output). First-run costs are additional.", "",
        "| Model | Method | Protocol | Valid / 18 | False positive / 18 | Abstain / 18 | Invalid / 18 | False positive % [CI] | FP among valid % |", "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in pres:
        c = r["counts"]
        lines.append(f"| {r['model']} | {r['method']} | {r['protocol']} | {c['valid']}/18 | {c['false_positive']}/18 | {c['abstain']}/18 | {c['invalid']}/18 | {ci(r['metrics']['false_positive'])} | {percent(r['false_positive_given_valid'])} |")
    lines += ["", "Provenance reconciliation: the historical 16/18 GPT LEA figure is the original pass; the current result JSONs, batch summary CSV, and frozen hint packs reflect 17/18 after recovery. The append-only log records initial CUAD25 and CUAD34 failures at lines 144 and 162, second-run starts at lines 305 and 306, and the repeated CUAD34 failure at line 381. These are different protocols, not a numerical error in the original first-run count. A 100% bootstrap interval degenerates when every observed source is positive and should not be interpreted as certainty about unseen sources."]
    lines += ["", "## Provenance and limits", "",
        "The frozen adjudication hash, public manifest hash, case/source identity, section mappings, positive-reference denominators, raw method output identity and hint-selection agreement were checked. Machine-readable outputs preserve every separate expert reference and every first/recovery system record; source_manifest.json lists SHA-256 digests for all read artifacts and preserved original workbook provenance. No new model calls were made. Reproduce with `python3 analyze.py` from this directory.", "",
        "The 14-case adjudication rule was author-designated after receiving the third expert's results, not preregistered. No full 42-case unique evidence gold is claimed. Expert qualifications, consent, compensation, and ethics statements must be supplied from real author records. The original historical 12-case summary may be cited separately; no missing old-case labels were reconstructed. The analysis measures output-set agreement and an explicit assertion protocol, not legal advice quality or natural-positive detection."]
    (HERE / "REPORT_EN.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

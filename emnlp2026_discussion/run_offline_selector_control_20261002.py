#!/usr/bin/env python3
"""Offline, size-matched output-selector control. Never queries an LLM.

Extraction uses the original Stage-2 identity/replay/parity validators. The
exported text-free inputs and this file also support standalone reproduction:
    python run_offline_selector_control_20261002.py --reproduce BUNDLE
The reproduction path requires only the Python standard library.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import socket
import statistics
import sys
from types import SimpleNamespace
from typing import Any

ARMS = ("full", "lea-score-matched-k", "mean-risk-matched-k")
METRICS = ("risk_all", "risk_any", "risk_coverage", "compression", "k", "root_at_3")
DEFAULT_REL = Path("2026NAACL/SA-MCGS/experiments/offline_selector_control_20261002")
PLAN_REL = Path("2026NAACL/SA-MCGS/validation/identity_stage2_80/case_plan.json")
LEA_REL = Path("emnlp2026_discussion/run_cost_audit_clean.py")
REPLAY_REL = Path("emnlp2026_discussion/run_component_ablation_stage2_core_replay.py")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_obj(value: Any) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode())


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text("".join(json.dumps(v, sort_keys=True, allow_nan=False) + "\n" for v in values))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def find_repo() -> Path:
    for root in Path(__file__).resolve().parents:
        if (root / "src/modules/alphago_mcgs.py").exists():
            return root
    raise RuntimeError("Extraction needs the repository; use --reproduce for an exported bundle")


@contextmanager
def forbid_network():
    attempts = []
    def blocked(*_args, **_kwargs):
        attempts.append(True)
        raise AssertionError("Offline analysis forbids all network connections")
    original = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection)
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.create_connection = blocked
    try:
        yield attempts
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection = original


def aggregate(scc_ids: list[str], events: list[dict]) -> dict:
    """Only primitive LEA fields; no labels, OC or Full evidence scores."""
    if not scc_ids or len(scc_ids) != len(set(scc_ids)):
        raise ValueError("SCC IDs must be unique and nonempty")
    universe = set(scc_ids)
    totals, visits, local, repair, endpoint = (defaultdict(float), Counter(), Counter(), Counter(), Counter())
    for event in events:
        for cid, value in event["scores"].items():
            value = float(value)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Nonfinite or out-of-range node score")
            if cid in universe:
                totals[cid] += value
                visits[cid] += 1
        for cid in event.get("local_risk_subgraph_nodes", []):
            if cid in universe:
                local[cid] += 1
        for cid in event.get("repair_entry_nodes", []):
            if cid in universe:
                repair[cid] += 1
        for edge in event.get("local_conflict_edges", []):
            source, target = edge.get("source"), edge.get("target")
            if source in universe and target in universe and source != target:
                endpoint[source] += 1
                endpoint[target] += 1
    means = {cid: totals[cid] / visits[cid] for cid in scc_ids if visits[cid]}
    floor = statistics.median(means.values()) if means else 0.0
    rows = []
    for cid in scc_ids:
        q = means.get(cid, 0.0)
        rows.append({"node": cid, "score_sum": totals[cid], "score_count": visits[cid],
                     "qbar": q, "L": local[cid], "R": repair[cid], "E": endpoint[cid],
                     "membership_score": local[cid] + repair[cid] + endpoint[cid] + max(0.0, q - floor)})
    return {"median_observed_qbar": floor, "nodes": rows}


def select(scc_ids: list[str], stats: dict, k: int, arm: str) -> list[str]:
    if not 0 <= k <= len(scc_ids):
        raise ValueError("Invalid matched size")
    if [r["node"] for r in stats["nodes"]] != scc_ids:
        raise ValueError("Statistics must retain the frozen SCC order")
    by_node = {r["node"]: r for r in stats["nodes"]}
    fallback = all(r["membership_score"] == 0 for r in stats["nodes"])
    if arm == "mean-risk-matched-k" or (arm == "lea-score-matched-k" and fallback):
        field = "qbar"
    elif arm == "lea-score-matched-k":
        field = "membership_score"
    else:
        raise ValueError(f"Unknown selector: {arm}")
    order = {cid: i for i, cid in enumerate(scc_ids)}
    ranked = sorted(scc_ids, key=lambda cid: (-by_node[cid][field], order[cid]))
    chosen = set(ranked[:k])
    return [cid for cid in scc_ids if cid in chosen]


def lea_source_oracle(source_path: Path):
    """Execute only the unmodified aggregation AST, never the LLM loop."""
    source = source_path.read_text()
    tree = ast.parse(source)
    func = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_lea")
    selected, active = [], False
    for statement in func.body:
        targets = {t.id for t in statement.targets if isinstance(t, ast.Name)} if isinstance(statement, ast.Assign) else set()
        if "scc_ids" in targets:
            active = True
        if active:
            selected.append(statement)
        if "subgraph_nodes" in targets:
            break
    if not selected or not any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "subgraph_nodes" for t in n.targets) for n in selected):
        raise AssertionError("Could not isolate real LEA aggregation block")
    block = ast.Module(body=selected, type_ignores=[])
    if any(isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith)) for n in ast.walk(block)):
        raise AssertionError("LEA oracle must contain no asynchronous/model evaluation")
    code = compile(ast.fix_missing_locations(block), str(source_path.name), "exec")
    def oracle(scc_ids, events):
        entries = [{"entry": SimpleNamespace(clause_evaluations=e["scores"],
                   local_risk_subgraph_nodes=e.get("local_risk_subgraph_nodes", []),
                   repair_entry_nodes=e.get("repair_entry_nodes", []),
                   local_conflict_edges=e.get("local_conflict_edges", []), conflicts=[])} for e in events]
        env = {"scc": SimpleNamespace(clause_ids=scc_ids), "entries": entries,
               "defaultdict": defaultdict, "median": lambda x: statistics.median(x) if x else 0.0,
               "math": math}
        exec(code, env)
        return env
    return oracle, {"first_line": selected[0].lineno, "last_line": selected[-1].end_lineno,
                    "source_sha256": sha_bytes(source_path.read_bytes()),
                    "aggregation_ast_sha256": sha_obj(ast.dump(block, include_attributes=False))}


def compare_oracle(scc_ids, events, stats, oracle):
    reference = oracle(scc_ids, events)
    for row in stats["nodes"]:
        cid = row["node"]
        for field, key in [("L", "local_counts"), ("R", "repair_counts"), ("E", "endpoint_counts"),
                           ("score_count", "visit_counts"), ("score_sum", "total_scores"),
                           ("qbar", "avg_scores"), ("membership_score", "signal")]:
            if not math.isclose(row[field], reference[key].get(cid, 0), abs_tol=1e-12, rel_tol=0):
                raise AssertionError(f"Real LEA source mismatch: {field}, node {cid}")
    if not math.isclose(stats["median_observed_qbar"], reference["score_floor"], abs_tol=1e-12, rel_tol=0):
        raise AssertionError("Observed-only median differs from real LEA")
    selected = select(scc_ids, stats, reference["cap"], "lea-score-matched-k")
    if selected != reference["subgraph_nodes"]:
        raise AssertionError("Tie break/fallback differs from the real LEA source")


def correctness_checks(oracle=None):
    ids = ["a", "b", "c", "unseen"]
    events = [
        {"scores": {"a": .9, "b": .1}, "local_risk_subgraph_nodes": ["a"],
         "repair_entry_nodes": ["b"], "local_conflict_edges": [{"source": "a", "target": "b"}]*2},
        {"scores": {"a": .3, "c": .6}, "local_risk_subgraph_nodes": ["c"],
         "repair_entry_nodes": [], "local_conflict_edges": [{"source": "a", "target": "a"}, {"source": "a", "target": "outside"}], "is_tt_hit": True},
    ]
    stats = aggregate(ids, events)
    values = {r["node"]: r for r in stats["nodes"]}
    assert values["a"]["E"] == values["b"]["E"] == 2
    assert values["a"]["score_count"] == 2 and abs(values["a"]["qbar"]-.6) < 1e-12
    assert abs(stats["median_observed_qbar"]-.6) < 1e-12
    assert values["unseen"]["membership_score"] == 0
    assert select(ids, stats, 2, "lea-score-matched-k") == ["a", "b"]
    assert select(ids, stats, 0, "lea-score-matched-k") == []
    tied = aggregate(ids, [{"scores": {cid:.4 for cid in ids}}])
    assert select(ids, tied, 2, "lea-score-matched-k") == ["a", "b"]
    if oracle:
        compare_oracle(ids, events, stats, oracle)
        compare_oracle(ids, [{"scores": {cid:.4 for cid in ids}}], tied, oracle)
    return {"hand_calculated_counts_and_mean": True, "cached_entries_included": True,
            "duplicate_edge_records_counted_and_invalid_edges_ignored": True,
            "observed_only_median": True, "tie_break_and_zero_fallback": True,
            "zero_size_supported": True, "source_oracle_fixture_parity": bool(oracle)}


def sanitize_event(event: dict, aliases: dict[str, str]) -> dict:
    return {"completion_index": int(event["completion_index"]),
            "is_tt_hit": bool(event.get("is_tt_hit")),
            "scores": {aliases[cid]: value for cid, value in event["scores"].items()},
            "local_risk_subgraph_nodes": [aliases[cid] for cid in event.get("local_risk_subgraph_nodes", [])],
            "repair_entry_nodes": [aliases[cid] for cid in event.get("repair_entry_nodes", [])],
            "local_conflict_edges": [{"source": aliases[e["source"]], "target": aliases[e["target"]]} for e in event.get("local_conflict_edges", [])]}


def extract(root: Path, out: Path, protocol: dict) -> dict:
    sys.path.insert(0, str(root))
    from emnlp2026_discussion import run_component_ablation_stage2_core_replay as replay
    oracle, oracle_audit = lea_source_oracle(root / LEA_REL)
    fixture_checks = correctness_checks(oracle)
    # Exercise the existing sentinel once in isolation; this is not a model call.
    sentinel = replay.ReplayOnlyLLM()
    try:
        asyncio.run(sentinel.call_json("offline self-check"))
    except AssertionError:
        pass
    else:
        raise AssertionError("LLM sentinel failed to reject a call")
    assert sentinel.calls == 1
    cases = replay.load_selected_cases([root / PLAN_REL], list(range(1,81)))
    input_rows, trace_rows, labels, full_outputs, audits = [], [], [], [], []
    physical_sources = {}
    for case in cases:
        source_path, full = replay.load_source_full(case)
        identity = replay.validate_case_identity(case, full)
        trace, trace_audit = replay.validate_trace(full)
        mcgs, sentinel = replay.make_replay_mcgs(full)
        for event in trace:
            replay.apply_trace_event(mcgs, event)
        summary = mcgs._build_result(elapsed=0.0, llm_calls=0,
                    tt_hits=sum(bool(e.get("is_tt_hit")) for e in trace), total_iters=len(trace))
        parity_fields = replay.assert_final_full_parity(full, summary)
        if sentinel.calls:
            raise AssertionError("Replay attempted an LLM call")
        # All simple aggregation starts from raw primitive fields, not Full scores.
        stats = aggregate(full["scc_clause_ids"], trace)
        compare_oracle(full["scc_clause_ids"], trace, stats, oracle)
        for row in stats["nodes"]:
            if not math.isclose(row["qbar"], dict(summary["ranking_by_risk"])[row["node"]], abs_tol=1e-12, rel_tol=0):
                raise AssertionError("Frozen mean node score was not reconstructed")
        source_uid = identity["physical_scc_uid"]
        source_id = physical_sources.setdefault(source_uid, f"source-{len(physical_sources)+1:02d}")
        case_id = f"case-{int(case['case_order']):03d}"
        aliases = {cid: f"n{i+1:03d}" for i,cid in enumerate(full["scc_clause_ids"])}
        anon_events = [sanitize_event(e, aliases) for e in trace]
        ids = list(aliases.values())
        anon_stats = aggregate(ids, anon_events)
        full_nodes = [aliases[cid] for cid in full["evidence_risk_subgraph_nodes"]]
        k = len(full_nodes)
        if k != len(set(full_nodes)) or k != int(full["evidence_risk_subgraph_size"]):
            raise AssertionError("Invalid frozen Full core size")
        common = {"case_id": case_id, "source_id": source_id, "model": str(full["model"]),
                  "domain": str(full["domain"]), "template": str(case["canonical_template"])}
        selection_input = {**common, "scc_order": ids, "matched_k": k, "statistics": anon_stats}
        input_rows.append(selection_input)
        trace_rows.append({"case_id": case_id, "events": anon_events})
        # Labels are not read by aggregate() or select(); export them separately.
        risk_ids = full.get("injected_risk_nodes") or full.get("injected_evidence_nodes") or []
        root_node = full.get("injected_node")
        if not risk_ids or root_node not in aliases:
            raise AssertionError("Missing metric-only endpoint/root labels")
        labels.append({"case_id": case_id, "root": aliases[root_node],
                       "risk_endpoints": list(dict.fromkeys(aliases[cid] for cid in risk_ids))})
        full_outputs.append({"case_id": case_id, "core": full_nodes,
                             "frozen_root_ranking": [aliases[cid] for cid,_ in full["ranking"]]})
        audits.append({**common, "source_record_index": identity["source_record_index"],
                       "source_file_sha256": identity["source_file_sha256"],
                       "source_record_sha256": identity["source_record_sha256"],
                       "source_file_relative": source_path.relative_to(root).as_posix(),
                       "physical_source_hash": source_uid, "trace_sha256": trace_audit["trace_sha256"],
                       "anonymous_trace_sha256": sha_obj(anon_events),
                       "selection_input_sha256": sha_obj(selection_input),
                       "trace_entries": len(trace), "cached_entries": sum(bool(e.get("is_tt_hit")) for e in trace),
                       "identity_valid": True, "final_full_parity": True, "parity_fields": parity_fields,
                       "lea_source_aggregation_parity": True, "llm_calls": sentinel.calls})
        print(f"Validated {case_id}: identity, final Full parity, real LEA aggregation", flush=True)
    source_counts = Counter(r["source_id"] for r in input_rows)
    if len(input_rows) != 80 or len(source_counts) != 20 or set(source_counts.values()) != {4}:
        raise AssertionError("Expected exactly 80 variants / 20 sources / four variants per source")
    write_jsonl(out / "selection_inputs.jsonl", input_rows)
    write_jsonl(out / "minimal_traces.jsonl", trace_rows)
    write_jsonl(out / "metric_labels.jsonl", labels)
    write_jsonl(out / "full_reference_outputs.jsonl", full_outputs)
    write_jsonl(out / "identity_and_parity_audit.jsonl", audits)
    sources = [PLAN_REL, LEA_REL, REPLAY_REL, Path("src/modules/alphago_mcgs.py"),
               Path("src/models/search_tree.py"), Path("experiments/cross_domain/run_cross_domain_battle.py")]
    write_json(out / "source_provenance.json", {"source_sha256": {str(p):sha_bytes((root/p).read_bytes()) for p in sources},
                                              "lea_source_oracle": oracle_audit})
    return {"planned_cases":80, "valid_cases":80, "invalid_cases":0, "source_sccs":20,
            "variants_per_source":4, "identity_passes":80, "trace_passes":80,
            "final_full_parity_passes":80, "real_lea_aggregation_passes":80,
            "replay_llm_calls":0, "new_model_tokens":0, "sentinel_rejection_test":True,
            "correctness_tests":fixture_checks}


def quantile(values: list[float], p: float) -> float:
    values = sorted(values)
    position = (len(values)-1)*p
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (position-lo)*(values[hi]-values[lo])


def evaluate(inputs: list[dict], references: dict, labels: dict) -> tuple[list[dict], list[dict]]:
    results, predictions = [], []
    for item in inputs:
        cid = item["case_id"]
        ids, k = item["scc_order"], item["matched_k"]
        cores = {"full":references[cid]["core"]}
        cores.update({arm:select(ids,item["statistics"],k,arm) for arm in ARMS[1:]})
        # Freeze predictions first. Metric-only labels enter strictly below.
        predictions.append({"case_id":cid, "cores":cores})
        risk = set(labels[cid]["risk_endpoints"])
        root_top3 = labels[cid]["root"] in references[cid]["frozen_root_ranking"][:3]
        if not risk or not risk.issubset(ids):
            raise AssertionError("Invalid metric endpoint labels")
        for arm,nodes in cores.items():
            chosen = set(nodes)
            if len(nodes) != k or len(chosen) != k or not chosen.issubset(ids):
                raise AssertionError("Exact per-case matched size failed")
            results.append({"case_id":cid,"source_id":item["source_id"],"domain":item["domain"],
                            "template":item["template"],"arm":arm,"valid":True,"scc_size":len(ids),
                            "k":k,"compression":1-k/len(ids),"risk_any":bool(chosen & risk),
                            "risk_all":risk.issubset(chosen),"risk_coverage":len(chosen & risk)/len(risk),
                            "root_at_3":root_top3,"selected_nodes":"|".join(nodes)})
    return results,predictions


def analyse_group(rows: list[dict], seed: int, replicates: int) -> dict:
    sources = sorted({r["source_id"] for r in rows})
    clusters = {source:{arm:[r for r in rows if r["source_id"]==source and r["arm"]==arm] for arm in ARMS} for source in sources}
    point_vectors = {f"{arm}/{metric}":[statistics.mean(float(r[metric]) for r in clusters[source][arm]) for source in sources]
                     for arm in ARMS for metric in METRICS}
    for arm in ARMS[1:]:
        for metric in METRICS:
            point_vectors[f"full-minus-{arm}/{metric}"] = [a-b for a,b in zip(point_vectors[f"full/{metric}"],point_vectors[f"{arm}/{metric}"])]
    rng = random.Random(seed)
    draws = [[rng.randrange(len(sources)) for _ in sources] for _ in range(replicates)]
    estimates = {}
    for key,values in point_vectors.items():
        means = [sum(values[j] for j in indices)/len(sources) for indices in draws]
        estimates[key] = {"mean":statistics.mean(values),"ci95":[quantile(means,.025),quantile(means,.975)],
                          "source_means":dict(zip(sources,values))}
    by_case = defaultdict(dict)
    for row in rows:
        by_case[row["case_id"]][row["arm"]] = row
    discordance = {}
    for arm in ARMS[1:]:
        discordance[arm] = {metric:{"full_only":sum(v["full"][metric] and not v[arm][metric] for v in by_case.values()),
                                            "control_only":sum(v[arm][metric] and not v["full"][metric] for v in by_case.values()),
                                            "both":sum(v["full"][metric] and v[arm][metric] for v in by_case.values()),
                                            "neither":sum(not v["full"][metric] and not v[arm][metric] for v in by_case.values())}
                               for metric in ("risk_all","risk_any")}
    return {"cases":len(by_case),"sources":len(sources),"estimates":estimates,"discordance":discordance}


def analyse(rows: list[dict], protocol: dict) -> dict:
    settings = protocol["bootstrap"]
    groups = {"overall":rows}
    groups.update({domain:[r for r in rows if r["domain"]==domain] for domain in sorted({r["domain"] for r in rows})})
    return {"version":"offline-selector-control-v1","primary_contrast":"full-minus-lea-score-matched-k/risk_all",
            "bootstrap":settings,"groups":{g:analyse_group(v,settings["seed"],settings["replicates"]) for g,v in groups.items()}}


def report(out: Path, summary: dict, rows: list[dict]) -> None:
    overall = summary["groups"]["overall"]
    e = overall["estimates"]
    def pct(key): return 100*e[key]["mean"]
    def interval(key): return [100*x for x in e[key]["ci95"]]
    contrast = "full-minus-lea-score-matched-k/risk_all"
    lo,hi = interval(contrast)
    if lo > 0:
        conclusion = "The paired interval favors the Full selector on these fixed trajectories."
    elif hi < 0:
        conclusion = "The paired interval favors simple LEA-score aggregation on these fixed trajectories."
    else:
        conclusion = "The paired interval does not establish an advantage for either selector on these fixed trajectories."
    paragraph = (
        "To isolate final evidence selection, we replayed the frozen GPT-4o trajectories for 80 injected variants from 20 source SCCs. "
        "The control applies LEA's existing aggregation score to the same recorded local outputs and selects exactly as many nodes as the Full core in each case. "
        f"Full and the LEA-score control achieve Risk-all of {pct('full/risk_all'):.2f}\\% and {pct('lea-score-matched-k/risk_all'):.2f}\\%, respectively "
        f"(Full minus control: {pct(contrast):+.2f} percentage points; 95\\% paired source-SCC bootstrap interval [{lo:.2f}, {hi:.2f}]). "
        f"Both retain {e['full/k']['mean']:.2f} nodes on average, with {pct('full/compression'):.2f}\\% compression. "
        f"{conclusion} The comparison conditions on evidence acquired by Full and does not isolate search-policy effects or online replacement benefits; it requires no new model calls."
    )
    write_json(out/"summary.json",summary)
    flattened=[]
    for group,data in summary["groups"].items():
        for key,value in data["estimates"].items():
            arm,metric=key.split("/")
            flattened.append({"group":group,"cases":data["cases"],"sources":data["sources"],
                              "arm_or_contrast":arm,"metric":metric,"mean":value["mean"],
                              "ci95_low":value["ci95"][0],"ci95_high":value["ci95"][1]})
    write_csv(out/"source_equal_summary.csv",flattened)
    write_csv(out/"case_metrics.csv",rows)
    (out/"manuscript_paragraph.tex").write_text(paragraph+"\n")
    table=[r"\begin{table}[t]",r"\centering",r"\small",
           r"\caption{Offline output selection on the same 80 GPT-4o traces (20 source SCCs), matching Full's actual core size in every case. Rates are percentages; no new model calls.}",
           r"\label{tab:offline_selector_control}",r"\begin{tabular}{lrrr}",r"\toprule",
           r"Selector & Risk-any & Risk-all & Comp. \\",r"\midrule"]
    for arm,label in [("full","Full"),("lea-score-matched-k","LEA-score control"),("mean-risk-matched-k","Mean-risk (diagnostic)")]:
        table.append(f"{label} & {pct(arm+'/risk_any'):.2f} & {pct(arm+'/risk_all'):.2f} & {pct(arm+'/compression'):.2f} \\\\")
    table += [r"\bottomrule",r"\end{tabular}",r"\end{table}"]
    (out/"manuscript_table.tex").write_text("\n".join(table)+"\n")
    lines=["# Offline selector control", "", paragraph.replace("\\%","%"), "",
           "| Selector | Risk-any | Risk-all | Endpoint coverage | Mean k | Compression |", "|---|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        lines.append(f"| {arm} | {pct(arm+'/risk_any'):.2f}% | {pct(arm+'/risk_all'):.2f}% | {pct(arm+'/risk_coverage'):.2f}% | {e[arm+'/k']['mean']:.2f} | {pct(arm+'/compression'):.2f}% |")
    lines += ["", "The frozen root ranking is unchanged across output selectors; Root@3 is " + f"{pct('full/root_at_3'):.2f}%.", "",
              "| Domain | Sources | Cases | Full Risk-all | LEA-score Risk-all | Difference (points) | Paired 95% interval |",
              "|---|---:|---:|---:|---:|---:|---|"]
    for domain,data in summary["groups"].items():
        if domain=="overall": continue
        x=data["estimates"]; delta=x[contrast]; ci=[100*v for v in delta["ci95"]]
        lines.append(f"| {domain} | {data['sources']} | {data['cases']} | {100*x['full/risk_all']['mean']:.2f}% | {100*x['lea-score-matched-k/risk_all']['mean']:.2f}% | {100*delta['mean']:+.2f} | [{ci[0]:.2f}, {ci[1]:.2f}] |")
    lines += ["", "Domain intervals are exploratory, with only 2–10 source clusters per domain. The primary analysis uses equal source weights; each source has four variants, so the overall variant average is identical.",
              "", "Full/control discordance for Risk-all: " + json.dumps(overall['discordance']['lea-score-matched-k']['risk_all']) + ".",
              "", "Selection uses the existing LEA score, including its observed-only median and SCC-order tie break. The control includes every recorded rollout entry, including cache reuse, and uses only node scores, local risk sets, repair entries and accepted local conflict-edge endpoints. It never reads OC, pair-ledger scores, Full composite evidence scores or injected labels.",
              "", "The per-case k comes from Full solely to control output size. This is a conditional analysis, not a deployable rule for choosing k. Both controls inherit Full's acquired evidence. These results must not be described as a token-matched comparison between independently run search policies.",
              "", "Files: protocol.json records the fixed analysis protocol; minimal_traces.jsonl and selection_inputs.jsonl contain anonymous text-free selection inputs; metric_labels.jsonl is used only for scoring; full_reference_outputs.jsonl stores the frozen Full outputs; identity_and_parity_audit.jsonl records 80 case checks; source_provenance.json and MANIFEST.sha256 support audit.",
              "", "Standalone reproduction: `python run_offline_selector_control_20261002.py --reproduce .` (Python standard library only). It verifies the manifest, reaggregates the sanitized traces, reruns both selectors, recomputes all paired intervals, and compares the saved results without rewriting them."]
    (out/"REPORT_EN.md").write_text("\n".join(lines)+"\n")


def reproduce(bundle: Path) -> None:
    for line in (bundle/"MANIFEST.sha256").read_text().splitlines():
        expected,name=line.split("  ",1)
        if sha_bytes((bundle/name).read_bytes())!=expected:
            raise AssertionError(f"Manifest mismatch: {name}")
    protocol=json.loads((bundle/"protocol.json").read_text())
    inputs=read_jsonl(bundle/"selection_inputs.jsonl")
    traces={r["case_id"]:r["events"] for r in read_jsonl(bundle/"minimal_traces.jsonl")}
    references={r["case_id"]:r for r in read_jsonl(bundle/"full_reference_outputs.jsonl")}
    labels={r["case_id"]:r for r in read_jsonl(bundle/"metric_labels.jsonl")}
    for row in inputs:
        if aggregate(row["scc_order"],traces[row["case_id"]])!=row["statistics"]:
            raise AssertionError("Sanitized trace/statistics mismatch")
    correctness_checks()
    results,predictions=evaluate(inputs,references,labels)
    if predictions!=read_jsonl(bundle/"predictions.jsonl"):
        raise AssertionError("Prediction reproduction failed")
    saved=read_jsonl(bundle/"case_metrics.jsonl")
    if results!=saved:
        raise AssertionError("Case metrics reproduction failed")
    summary=analyse(results,protocol)
    if summary!=json.loads((bundle/"summary.json").read_text()):
        raise AssertionError("Bootstrap/summary reproduction failed")
    print(json.dumps({"standalone_reproduction":"passed","cases":len(inputs),
                      "source_sccs":len({r['source_id'] for r in inputs}),"new_llm_calls":0}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reproduce",type=Path)
    args=parser.parse_args()
    if args.reproduce:
        with forbid_network() as attempts:
            reproduce(args.reproduce.resolve())
            assert not attempts
        return
    root=find_repo(); out=root/DEFAULT_REL
    protocol_path=out/"protocol.json"
    if (out/"summary.json").exists():
        raise RuntimeError("Results already exist; use --reproduce instead of overwriting")
    protocol_hash=sha_bytes(protocol_path.read_bytes())
    protocol=json.loads(protocol_path.read_text())
    write_json(out/"protocol_lock.json",{"protocol_sha256":protocol_hash,
               "analysis_started_utc":datetime.now(timezone.utc).isoformat(),
               "script_sha256":sha_bytes(Path(__file__).read_bytes()),
               "new_selector_results_exist_at_lock":False})
    with forbid_network() as attempts:
        checks=extract(root,out,protocol)
        inputs=read_jsonl(out/"selection_inputs.jsonl")
        references={r["case_id"]:r for r in read_jsonl(out/"full_reference_outputs.jsonl")}
        labels={r["case_id"]:r for r in read_jsonl(out/"metric_labels.jsonl")}
        rows,predictions=evaluate(inputs,references,labels)
        write_jsonl(out/"predictions.jsonl",predictions)
        write_jsonl(out/"case_metrics.jsonl",rows)
        summary=analyse(rows,protocol)
        report(out,summary,rows)
        checks.update({"matched_k_passes":80,"network_connection_attempts":len(attempts),
                       "selection_inputs_exclude_ground_truth":True,
                       "protocol_unchanged":sha_bytes(protocol_path.read_bytes())==protocol_hash,
                       "finished_utc":datetime.now(timezone.utc).isoformat()})
        assert checks["protocol_unchanged"] and not attempts
        write_json(out/"checks.json",checks)
    shutil.copy2(Path(__file__),out/Path(__file__).name)
    files=sorted(p for p in out.iterdir() if p.is_file() and p.name!="MANIFEST.sha256")
    (out/"MANIFEST.sha256").write_text("".join(f"{sha_bytes(p.read_bytes())}  {p.name}\n" for p in files))
    print(json.dumps({"status":"complete","primary":summary["groups"]["overall"]["estimates"][summary["primary_contrast"]],
                      "output":str(DEFAULT_REL)},indent=2))


if __name__=="__main__":
    main()

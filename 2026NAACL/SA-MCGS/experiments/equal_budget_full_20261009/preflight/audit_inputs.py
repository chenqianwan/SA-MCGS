#!/usr/bin/env python3
"""Offline identity, frozen-source, injected-input and workload audit.

Writes only this preflight directory. Network connections and dotenv loading are
disabled before importing the historical scientific modules. No LLM is created.
"""
from __future__ import annotations
import argparse
import collections
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import socket
import statistics
import sys
import types


HERE = Path(__file__).resolve().parent
EXPERIMENTS = HERE.parents[1]
MAIN_ROOT = EXPERIMENTS.parents[2]
OLD = EXPERIMENTS / "kimi_qwen35_three_methods_20260924"
SCIENCE_DIR = OLD / "runner"
BUNDLE = SCIENCE_DIR / "repo"
HISTORY = {
    "llama-3.1-8b": EXPERIMENTS / "llama8b_three_methods_20260924/downloaded_final",
    "kimi-vl-a3b-instruct": OLD / "downloaded_final/kimi",
    "qwen3.5-9b": OLD / "downloaded_final/qwen35",
}
IDENTITY_FIELDS = (
    "case_uid", "stable_case_uid", "physical_scc_uid", "planned_case_identity",
    "planned_scc_clause_ids", "planned_injection_identity", "source_result_sha256",
    "source_sa_record_sha256", "main_case_order", "domain", "scc_size", "template",
    "planned_scc_fingerprint",
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def write(name, value):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def blocked_network(*args, **kwargs):
    raise RuntimeError("This preflight forbids all network connections")


def load_offline_science():
    sys.dont_write_bytecode = True
    socket.create_connection = blocked_network
    socket.socket.connect = blocked_network
    socket.socket.connect_ex = blocked_network
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: False
    sys.modules["dotenv"] = dotenv
    # SDK imports are irrelevant to graph restoration and configuration checks.
    # Fail-closed constructor stubs avoid requiring either SDK in this local audit.
    for module_name, constructor in (("openai", "AsyncOpenAI"), ("anthropic", "AsyncAnthropic")):
        module = types.ModuleType(module_name)
        setattr(module, constructor, blocked_network)
        sys.modules[module_name] = module
    spec = importlib.util.spec_from_file_location("frozen_preflight_base", SCIENCE_DIR / "base_launcher.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    manifest = launcher.verify_bundle()
    cost = launcher.import_science()
    # Any accidental model construction or client factory use also fails closed.
    cost.make_llm = blocked_network
    return launcher, cost, manifest


def visible(graph, scc):
    ids = set(scc.clause_ids)
    return {
        "nodes": [{"id": node, "title": graph.clauses[node].title,
                   "text": graph.clauses[node].content} for node in scc.clause_ids],
        "edges": [{"source": edge.source, "target": edge.target,
                   "type": str(getattr(edge.dependency_type, "value", edge.dependency_type)),
                   "weight": float(edge.weight)}
                  for edge in graph.edges if edge.source in ids and edge.target in ids],
    }


def historical_workload():
    rows = []
    field_audit = {}
    for model, folder in HISTORY.items():
        equality_n = 0
        for method in ("sa-mcgs", "lea", "naive-single"):
            files = sorted((folder / "results").glob(f"*__{method}.json"))
            check(len(files) == 80, f"Historical result count mismatch: {model} {method}")
            results = [read(path) for path in files]
            usage = [item["llm_usage_summary"] for item in results]
            tokens = sorted(item["total_tokens"] for item in usage)
            if method == "sa-mcgs":
                for item in results:
                    if item["completion_status"] == "complete":
                        check(item["core_evidence_risk_subgraph_nodes"] == item["evidence_risk_subgraph_nodes"],
                              "Historical core_evidence differs from deployable evidence H")
                        equality_n += 1
            rows.append({
                "model": model, "method": method, "n": len(results), "usage_n": len(usage),
                "states": dict(collections.Counter(item["completion_status"] for item in results)),
                "prompt_tokens": sum(item["prompt_tokens"] for item in usage),
                "completion_tokens": sum(item["completion_tokens"] for item in usage),
                "total_tokens": sum(tokens), "mean_tokens": statistics.mean(tokens),
                "min_tokens": min(tokens), "p95_tokens": tokens[math.ceil(.95 * len(tokens)) - 1],
                "max_tokens": max(tokens),
                "api_calls": sum(item["recorded_api_calls"] for item in usage),
                "api_runtime_hours_sum": sum(item.get("api_runtime_sec_sum", 0) for item in usage) / 3600,
            })
        field_audit[model] = {"valid_sa_checked": equality_n, "native_and_core_equal": True}
    sa_sum = sum(row["total_tokens"] for row in rows if row["method"] == "sa-mcgs")
    return {"rows": rows, "historical_sa_total_tokens": sa_sum,
            "three_arm_ceiling_if_new_B_matched_historical_tokens": 3 * sa_sum,
            "warning": "Historical workload scale only; new sequential scheduling/parser can change realized B. Runtime sums overlap and are not GPU-wall-clock forecasts.",
            "native_h_field_audit": field_audit}


def main():
    global SCIENCE_DIR, BUNDLE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--science-dir", type=Path, default=SCIENCE_DIR,
                        help="Directory containing frozen base_launcher.py and repo/")
    arguments = parser.parse_args()
    SCIENCE_DIR = arguments.science_dir.resolve()
    BUNDLE = SCIENCE_DIR / "repo"
    manifest = read(BUNDLE / "bundle_manifest.json")
    canonical_path = BUNDLE / "portable_data/qwen80_case_plan.json"
    canonical = read(canonical_path)
    check(len(canonical) == 80 and len({item["case_uid"] for item in canonical}) == 80,
          "Expected 80 unique canonical variants")
    by_uid = {item["case_uid"]: item for item in canonical}
    comparisons, protocols = {}, {}
    for model, folder in HISTORY.items():
        plan, protocol = read(folder / "case_plan.json"), read(folder / "frozen_protocol.json")
        check(len(plan) == 80 and {item["case_uid"] for item in plan} == set(by_uid), "Case UID set differs")
        for item in plan:
            for field in IDENTITY_FIELDS:
                check(item.get(field) == by_uid[item["case_uid"]].get(field), f"Identity differs: {model} {field}")
        comparisons[model] = {"n": len(plan), "identity_fields_equal": list(IDENTITY_FIELDS),
                              "plan_sha256": sha(folder / "case_plan.json"),
                              "protocol_sha256": sha(folder / "frozen_protocol.json")}
        protocols[model] = protocol
    configurations = [value["sa_mcgs_config"] for value in protocols.values()]
    check(all(value == configurations[0] for value in configurations), "Historical SA configurations differ")
    proposed = copy.deepcopy(configurations[0])
    check(proposed["alphago_mcgs"]["concurrency"] == 8, "Unexpected old concurrency")
    proposed["alphago_mcgs"]["concurrency"] = 1
    code_checks = {}
    for relative, expected in manifest["unchanged_code_sha256"].items():
        check(sha(BUNDLE / relative) == expected, f"Frozen source mismatch: {relative}")
        current = MAIN_ROOT / relative
        code_checks[relative] = {"frozen_sha256": expected,
                                 "main_sha256": sha(current) if current.exists() else None}
    physical = collections.defaultdict(list)
    for case in canonical:
        physical[digest({"domain": case["domain"], "ids": sorted(case["planned_scc_clause_ids"])})].append(case)
    check(len(physical) == 20 and all(len(group) == 4 for group in physical.values()),
          "Expected 20 sources with 4 variants each")
    check(all(len({case["template"] for case in group}) == 4 for group in physical.values()),
          "Missing injection family in a physical source")
    launcher, cost, checked_manifest = load_offline_science()
    graphs = launcher.restore_graphs(cost, checked_manifest)
    plan = copy.deepcopy(canonical)
    for case in plan:
        case["source_result_file"] = str(BUNDLE / case["source_result_repo_relpath"])
    validated = cost.validate_case_plan(plan, graphs)
    actual = []
    for case in plan:
        graph, scc, root, labels = cost.prepare_injected_case(case, graphs)
        check(scc.clause_ids == case["planned_scc_clause_ids"], "Injected input order changed")
        check(root == case["planned_injection_identity"]["root_node"], "Injected root changed")
        payload = visible(graph, scc)
        item = {"case_uid": case["case_uid"], "main_case_order": case["main_case_order"],
                "domain": case["domain"], "template": case["template"], "scc_size": scc.size,
                "visible_input_sha256": digest(payload), "source_result_sha256": case["source_result_sha256"],
                "planned_fingerprint": case["planned_scc_fingerprint"],
                "risk_nodes_n": len(case["planned_injection_identity"]["risk_nodes"]),
                "evidence_nodes_n": len(case["planned_injection_identity"]["evidence_nodes"])}
        actual.append(item)
        write(f"visible_inputs/{case['main_case_order']:03d}.json", payload)
    args = argparse.Namespace(budget=60, window_size=4, internal_concurrency=1, compression_profile="current")
    check(cost.make_mcgs_config(args) == proposed, "New concurrency-1 config differs beyond intended change")
    workload = historical_workload()
    report = {
        "status": "passed", "n_cases": 80, "n_physical_sources": 20,
        "domain_variants": dict(collections.Counter(case["domain"] for case in canonical)),
        "template_variants": dict(collections.Counter(case["template"] for case in canonical)),
        "cross_model_identity": comparisons, "actual_injected_inputs_checked": len(actual),
        "canonical_plan_sha256": sha(canonical_path), "bundle_manifest_sha256": sha(BUNDLE / "bundle_manifest.json"),
        "science_dir": str(SCIENCE_DIR),
        "source_code_checks": code_checks,
        "main_source_differences": [path for path, value in code_checks.items()
                                    if value["main_sha256"] != value["frozen_sha256"]],
        "scientific_preflight": validated,
        "historical_parser": {"attempts": 3, "exhaustion_fallback": {}, "sdk_retries": 0},
        "proposed_sa_change": {"concurrency": {"old": 8, "new": 1},
                               "all_other_sa_config_equal": True,
                               "adaptive_trajectory_may_change": True},
        "historical_workload": workload,
        "not_checked": ["new runner/client implementation", "model/tokenizer runtime", "actual judge prompt budget", "cluster deployment"],
        "network_calls": 0, "model_calls": 0, "dotenv_loading_disabled": True,
    }
    write("proposed_sa_config.json", proposed)
    write("case_input_manifest.json", actual)
    write("historical_workload.json", workload)
    write("input_audit.json", report)
    print(json.dumps({"status": "passed", "cases": len(actual), "physical_sources": len(physical),
                      "source_code_differences": report["main_source_differences"],
                      "historical_sa_tokens": workload["historical_sa_total_tokens"],
                      "historical_three_arm_ceiling": workload["three_arm_ceiling_if_new_B_matched_historical_tokens"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

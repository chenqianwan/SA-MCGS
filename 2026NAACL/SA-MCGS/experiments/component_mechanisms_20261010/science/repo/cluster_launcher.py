#!/usr/bin/env python3
"""Portable Qwen80 LEA adapter. Only explicit smoke/run modes use localhost.

Scientific source files remain byte-identical. The adapter resolves copied
source artifacts, restores full graph snapshots, and sets a separate local
zero-rate route. Preflight and tokenizer validation never construct API calls.
"""
from __future__ import annotations
import argparse
import asyncio
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "2026NAACL/SA-MCGS/experiments/lea_full320_completion_20260923/run_completion.py"
MODEL = "qwen2.5-72b"
CHECKPOINT = "Qwen/Qwen2.5-72B-Instruct-AWQ"
REVISION = "698703eae6604af048a3d2f509995dc302088217"
sys.path.insert(0, str(ROOT))


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_bundle():
    manifest = read(ROOT / "bundle_manifest.json")
    checks = dict(manifest["unchanged_code_sha256"])
    checks.update({name: value["sha256"] for name, value in manifest["source_results"].items()})
    checks.update({value["path"]: value["sha256"] for value in manifest["graphs"].values()})
    checks.update({"portable_data/qwen80_case_plan.json": manifest["case_plan_sha256"],
                   "portable_data/original_prompt_capture.json.gz": manifest["original_capture_sha256"],
                   "portable_data/historical_provider_confirmation.json": manifest["historical_provider_confirmation_sha256"],
                   "portable_capture.py": manifest["portable_capture_sha256"]})
    for relative, expected in checks.items():
        if sha(ROOT / relative) != expected:
            raise RuntimeError(f"Bundle file hash mismatch: {relative}")
    return manifest


def import_runner():
    spec = importlib.util.spec_from_file_location("portable_frozen_runner", RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def restore_graph_loaders(runner, manifest):
    from src.models.graph import DependencyGraph
    graph_cache = {}
    for domain, info in manifest["graphs"].items():
        graph = DependencyGraph.model_validate_json(gzip.decompress((ROOT / info["path"]).read_bytes()))
        graph.metadata.pop(runner.cost._DATASET_REVISION_CACHE_KEY, None)
        revision = runner.cost.graph_dataset_revision(graph, domain)
        if revision != info["dataset_revision"]:
            raise RuntimeError(f"Restored full graph content revision mismatch: {domain}")
        graph_cache[domain] = graph
    for domain, function in {"debian": "load_debian_graph", "sec_ex21": "load_sec_graph",
                             "bgb": "load_bgb_graph", "cuad": "load_cuad_graph"}.items():
        setattr(runner.cost.battle, function, lambda domain=domain: graph_cache[domain])
    return graph_cache


def prepare_runtime(args, runner, manifest):
    parsed = urlparse(args.base_url)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path.rstrip("/") != "/v1"
            or not parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise RuntimeError("Only the same-node http://127.0.0.1:<port>/v1 endpoint is allowed")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plan = read(ROOT / "portable_data/qwen80_case_plan.json")
    for case in plan:
        case["source_result_file"] = str((ROOT / case["source_result_file"]).resolve())
    if len(plan) != 80 or any(case["model"] != MODEL for case in plan):
        raise RuntimeError("Expected exactly the frozen Qwen80 cases")
    pricing = {
        # The reused runner requires a positive cap <=50. Every accepted route
        # is localhost and both token rates are exactly zero; external spend=0.
        "budget_usd": 50.0, "external_api_spending_allowed_usd": 0.0,
        "scope": "Independent cluster-local Qwen80; GPU allocation cost is not API spend",
        "models": {MODEL: {"base_url": args.base_url, "model_id": "qwen2.5-72b-instruct",
            "api_key_env": "LOCAL_VLLM_API_KEY", "input_usd_per_million": 0.0,
            "output_usd_per_million": 0.0, "pricing_source": "self_hosted_same_node_vllm",
            "checkpoint_repository": CHECKPOINT, "checkpoint_revision": REVISION,
            "quantization": "awq", "activation_dtype": "float16", "tensor_parallel_size": 1,
            "backend_differs_from_historical_hosted_qwen": True}},
    }
    provenance = {"bundle_manifest_sha256": sha(ROOT / "bundle_manifest.json"),
                  "launcher_sha256": sha(Path(__file__)), "graph_adapter": "full_content_verified_gzip_json",
                  "source_artifacts": "unchanged_original_bytes", "scientific_code": "unchanged_original_bytes",
                  "checkpoint_repository": CHECKPOINT, "checkpoint_revision": REVISION,
                  "quantization": "awq", "activation_dtype": "float16",
                  "backend_differs_from_historical_hosted_qwen": True,
                  "historical_provider_confirmation": read(ROOT / "portable_data/historical_provider_confirmation.json"),
                  "note": "Current deployment settings are recorded here. The user confirmed with XHub that the historical endpoint also used AWQ; this record does not establish a precision change."}
    with runner.locked(args.output_dir / "locks/portable_init.lock"):
        for name, payload in (("portable_case_plan.json", plan), ("frozen_pricing.json", pricing),
                              ("deployment_provenance.json", provenance)):
            path = args.output_dir / name
            if path.exists() and read(path) != payload:
                raise RuntimeError(f"Portable runtime configuration changed: {name}")
            if not path.exists():
                write(path, payload)
    os.environ["LOCAL_VLLM_API_KEY"] = "local-vllm-no-external-billing"
    return plan


async def validate_portability(args, runner, manifest, plan):
    from portable_capture import capture_case
    expected = json.loads(gzip.decompress((ROOT / "portable_data/original_prompt_capture.json.gz").read_bytes()))
    graphs = runner.cost.load_graphs(plan)
    report = runner.cost.validate_case_plan(plan, graphs)
    expected_by_id = {item["case_id"]: item for item in expected}
    requests = 0
    windows = 0
    for case in plan:
        actual = await capture_case(runner.cost, case, graphs)
        if actual != expected_by_id[case["case_id"]]:
            raise RuntimeError(f"Original vs portable prompt/window mismatch: {case['case_id']}")
        requests += len(actual["actual_requests"])
        windows += len(actual["deterministic_windows"])
    report.update({"passed": True, "api_calls": 0, "cases": len(plan), "request_count": requests,
                   "deterministic_window_count": windows, "original_and_portable_requests_identical": True,
                   "bundle_manifest_sha256": sha(ROOT / "bundle_manifest.json"),
                   "scientific_code_unchanged": True, "full_graph_dataset_revisions_verified": True})
    runner.cost.persist_case_plan(args.output_dir, plan)
    write(args.output_dir / "portable_preflight.json", report)
    return expected


def tokenize(args, captures):
    if not args.tokenizer_path:
        raise RuntimeError("--tokenizer-path is required for offline tokenize mode")
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer_path), local_files_only=True, trust_remote_code=False)
    rows = []
    for case in captures:
        for request in case["actual_requests"]:
            tokens = tokenizer.apply_chat_template(request["messages"], tokenize=True, add_generation_prompt=True)
            # Recent transformers returns BatchEncoding by default for some
            # tokenizers; preserve the exact IDs without retokenizing text.
            if isinstance(tokens, dict) or hasattr(tokens, "keys"):
                tokens = tokens["input_ids"]
            if len(tokens) and isinstance(tokens[0], (list, tuple)):
                tokens = tokens[0]
            token_n = len(tokens)
            rows.append({"case_id": case["case_id"], "call_index": request["call_index"],
                         "request_sha256": request["request_sha256"], "prompt_tokens": token_n,
                         "max_output_tokens": request["max_tokens"], "total_reserved_context": token_n+request["max_tokens"]})
    overflow = [row for row in rows if row["total_reserved_context"] > args.max_model_len]
    report = {"passed": not overflow, "api_calls": 0, "cases": len(captures), "requests": len(rows),
              "max_model_len": args.max_model_len, "max_output_tokens": args.max_output_tokens,
              "max_prompt_tokens": max(row["prompt_tokens"] for row in rows),
              "max_prompt_plus_output_tokens": max(row["total_reserved_context"] for row in rows),
              "overflow_count": len(overflow), "overflow": overflow,
              "bundle_manifest_sha256": sha(ROOT / "bundle_manifest.json"),
              "tokenizer_path": str(args.tokenizer_path),
              "tokenizer_files_sha256": {name: sha(args.tokenizer_path / name) for name in (
                  "tokenizer.json", "tokenizer_config.json", "config.json", "chat_template.jinja") if (args.tokenizer_path / name).is_file()},
              "rows": rows}
    write(args.output_dir / "tokenization_report.json", report)
    if overflow:
        raise RuntimeError(f"Context overflow in {len(overflow)} frozen requests; no API calls made")
    return report


async def main(args):
    manifest = verify_bundle()
    runner = import_runner()
    restore_graph_loaders(runner, manifest)
    plan = prepare_runtime(args, runner, manifest)
    if args.mode in {"preflight", "tokenize"}:
        captures = await validate_portability(args, runner, manifest, plan)
        report = tokenize(args, captures) if args.mode == "tokenize" else read(args.output_dir / "portable_preflight.json")
        print(json.dumps({key: value for key, value in report.items() if key not in {"case_uids", "rows", "tokenizer_files_sha256"}}, indent=2))
        return 0
    for name in ("portable_preflight.json", "tokenization_report.json"):
        path = args.output_dir / name
        if not path.exists() or not read(path).get("passed") or read(path).get("bundle_manifest_sha256") != sha(ROOT / "bundle_manifest.json"):
            raise RuntimeError(f"A successful current-bundle {name} is required before local model calls")
    token_report = read(args.output_dir / "tokenization_report.json")
    if token_report["max_model_len"] != args.max_model_len or token_report["max_output_tokens"] != 2048:
        raise RuntimeError("Tokenization context differs from the frozen served context")
    run_args = argparse.Namespace(output_dir=args.output_dir,
        case_csv=args.output_dir / "unused_case_csv.csv", case_plan=args.output_dir / "portable_case_plan.json",
        pricing=args.output_dir / "frozen_pricing.json", models=[MODEL], mode=args.mode,
        shard_count=args.shard_count, shard_index=args.shard_index, llm_timeout=args.llm_timeout,
        smoke_case_order=args.smoke_case_order, resume_provider_failures=args.resume_provider_failures)
    await runner.run(run_args)
    selected = [case for case in plan if case["main_case_order"] == args.smoke_case_order] if args.mode == "smoke" else [case for index, case in enumerate(plan) if index % args.shard_count == args.shard_index]
    statuses = {}
    for case in selected:
        path = args.output_dir / "results" / f"{case['case_id']}__lea.json"
        statuses[case["case_id"]] = read(path).get("completion_status") if path.exists() else "missing"
    incomplete = [case for case, state in statuses.items() if state not in {"complete", "strict_experiment_failure"}]
    if args.mode == "smoke":
        incomplete = [case for case, state in statuses.items() if state != "complete"]
    print(json.dumps({"mode": args.mode, "expected": len(selected), "terminal": len(selected)-len(incomplete),
                      "incomplete_cases": incomplete, "external_api_cost_usd": 0.0}, indent=2))
    return 2 if incomplete else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "tokenize", "smoke", "run"), default="preflight")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18072/v1")
    parser.add_argument("--tokenizer-path", type=Path)
    parser.add_argument("--max-model-len", type=int, default=16384)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--smoke-case-order", type=int, default=20)
    parser.add_argument("--llm-timeout", type=float, default=600)
    parser.add_argument("--resume-provider-failures", action="store_true")
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    if args.tokenizer_path:
        args.tokenizer_path = args.tokenizer_path.resolve()
    if args.max_output_tokens != 2048 or args.max_model_len != 16384 or args.smoke_case_order != 20:
        parser.error("Frozen protocol requires context16384, output2048 and smoke_case_order20")
    if not 0 <= args.shard_index < args.shard_count or (args.mode == "smoke" and (args.shard_count != 1 or args.shard_index != 0)):
        parser.error("Invalid sharding or sharded smoke")
    raise SystemExit(asyncio.run(main(args)))

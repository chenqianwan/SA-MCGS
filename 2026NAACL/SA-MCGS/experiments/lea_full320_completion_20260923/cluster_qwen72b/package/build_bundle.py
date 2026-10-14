#!/Users/chenlong/.pyenv/versions/3.11.0/bin/python
"""Export frozen Qwen80 inputs and unchanged scientific code, without API calls."""
from __future__ import annotations
import asyncio
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
MAIN = HERE.parents[1]
DEST = HERE / "repo"
sys.path.insert(0, str(ROOT))
from emnlp2026_discussion import run_cost_audit_clean as cost


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


async def main():
    DEST.mkdir(parents=True, exist_ok=True)
    copies = list((ROOT / "src").rglob("*.py"))
    copies += [ROOT / p for p in (
        "emnlp2026_discussion/run_cost_audit_clean.py", "emnlp2026_discussion/run_lea_full_baseline.py",
        "experiments/cross_domain/run_cross_domain.py", "experiments/cross_domain/run_cross_domain_battle.py",
        "experiments/cross_domain/inject_defect.py", "experiments/perturbation.py",
    )]
    copies.append(MAIN / "run_completion.py")
    for optional in (ROOT / "experiments/__init__.py", ROOT / "experiments/cross_domain/__init__.py", ROOT / "emnlp2026_discussion/__init__.py"):
        if optional.exists():
            copies.append(optional)
    code_hashes = {}
    for source in copies:
        relative = source.relative_to(ROOT)
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        assert sha(source) == sha(target)
        code_hashes[str(relative)] = sha(source)
    plan = [copy.deepcopy(c) for c in json.loads((MAIN / "preflight/case_plan.json").read_text()) if c["model"] == "qwen2.5-72b"]
    assert len(plan) == 80
    sources = {}
    for case in plan:
        source = Path(case["source_result_file"])
        target = DEST / "experiments/cross_domain/results" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        assert "sha256:" + sha(target) == case["source_result_sha256"]
        sources[str(target.relative_to(DEST))] = {"sha256": sha(target), "bytes": target.stat().st_size}
    graphs = cost.load_graphs(plan)
    graph_info = {}
    for domain, graph in graphs.items():
        expected_revision = cost.graph_dataset_revision(graph, domain)
        graph.metadata.pop(cost._DATASET_REVISION_CACHE_KEY, None)
        data = graph.model_dump_json().encode()
        target = DEST / "portable_data" / f"{domain}.graph.json.gz"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            with gzip.GzipFile(fileobj=handle, mode="wb", mtime=0, compresslevel=6) as stream:
                stream.write(data)
        graph_info[domain] = {"path": str(target.relative_to(DEST)), "sha256": sha(target),
                              "bytes": target.stat().st_size, "json_bytes": len(data),
                              "dataset_revision": expected_revision, "clauses": len(graph.clauses),
                              "edges": len(graph.edges), "sccs": len(graph.sccs)}
        print(json.dumps({"exported_graph": domain, **graph_info[domain]}), flush=True)
    template = copy.deepcopy(plan)
    for case in template:
        case["source_result_file_original"] = case["source_result_file"]
        case["source_result_file"] = "experiments/cross_domain/results/" + Path(case["source_result_file"]).name
    write_json(DEST / "portable_data/qwen80_case_plan.json", template)
    shutil.copyfile(HERE.parent / "historical_provider_confirmation.json", DEST / "portable_data/historical_provider_confirmation.json")
    helper_spec = importlib.util.spec_from_file_location("portable_capture", DEST / "portable_capture.py")
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    captures = []
    for index, case in enumerate(plan, 1):
        captures.append(await helper.capture_case(cost, case, graphs))
        if index % 10 == 0:
            print(json.dumps({"captured_cases": index}), flush=True)
    target = DEST / "portable_data/original_prompt_capture.json.gz"
    with target.open("wb") as handle:
        with gzip.GzipFile(fileobj=handle, mode="wb", mtime=0, compresslevel=6) as stream:
            stream.write(json.dumps(captures, ensure_ascii=False, separators=(",", ":")).encode())
    manifest = {"version": "qwen80_portable_v1", "model": "qwen2.5-72b", "cases": 80,
                "api_calls_during_export": 0, "graphs": graph_info, "source_results": sources,
                "unchanged_code_sha256": code_hashes,
                "case_plan_sha256": sha(DEST / "portable_data/qwen80_case_plan.json"),
                "original_capture_sha256": sha(target),
                "original_capture_cases": len(captures),
                "portable_capture_sha256": sha(DEST / "portable_capture.py"),
                "historical_provider_confirmation_sha256": sha(DEST / "portable_data/historical_provider_confirmation.json"),
                "source_bytes": sum(s["bytes"] for s in sources.values()),
                "graph_gzip_bytes": sum(s["bytes"] for s in graph_info.values()),
                "graph_loading_only_adapter": True}
    write_json(DEST / "bundle_manifest.json", manifest)
    print(json.dumps({k: v for k, v in manifest.items() if k not in {"graphs", "source_results", "unchanged_code_sha256"}}, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())

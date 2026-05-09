"""Incremental experiment runner with DAG evaluation caching.

Key optimization: the baseline SA-MCGS pipeline is run ONCE on the unperturbed
graph.  All DAG evaluation results are cached.  Each perturbation job only
re-evaluates the *affected* nodes (the perturbed target and its downstream
dependents), reusing cached results for everything else.

With DeepSeek cloud API (20 concurrent calls), this brings per-job time from
~18 min down to ~30-60 seconds.

Results:  experiments/results/live_results.json
Status:   experiments/results/live_status.json
Graph:    experiments/results/live_graph.json
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import networkx as nx
import typer
import yaml
from loguru import logger

RESULTS_FILE = Path("experiments/results/live_results.json")
STATUS_FILE = Path("experiments/results/live_status.json")
GRAPH_FILE = Path("experiments/results/live_graph.json")

app = typer.Typer()

# ── helpers ──────────────────────────────────────────────────────────

def _load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _create_llm_client(config: dict):
    from src.llm import LocalClient, OpenAIClient, AnthropicClient
    provider = config.get("llm", {}).get("provider", "openai")
    if provider == "local":
        return LocalClient(config["llm"])
    elif provider == "openai":
        return OpenAIClient(config["llm"])
    elif provider == "anthropic":
        return AnthropicClient(config["llm"])
    raise ValueError(f"Unknown provider: {provider}")


def _load_json(path: Path) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, ValueError):
            return [] if "results" in path.name else {}
    return [] if "results" in path.name else {}


def _save_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    tmp.replace(path)


def _update_status(phase: str, detail: str, progress: dict | None = None):
    status = {
        "phase": phase,
        "detail": detail,
        "updated_at": datetime.now().isoformat(),
        "total_results": len(_load_json(RESULTS_FILE)),
    }
    if progress:
        status.update(progress)
    _save_json(STATUS_FILE, status)


# ── graph setup ──────────────────────────────────────────────────────

def _setup_graph(data_dir: str, config: dict):
    import gzip, pickle

    graph_path = Path(data_dir) / "de" / "4_crossreference_graph" / "bgb_focus.gpickle.gz"
    if not graph_path.exists():
        raise FileNotFoundError(f"Focus graph not found: {graph_path}")

    targets_path = Path("experiments/data/experiment_targets.json")
    if not targets_path.exists():
        with gzip.open(graph_path, "rb") as f:
            G = pickle.load(f)
        targets = _select_targets(G)
        targets_path.parent.mkdir(parents=True, exist_ok=True)
        targets_path.write_text(json.dumps(targets, indent=2, ensure_ascii=False))
    else:
        targets = json.loads(targets_path.read_text())

    from src.data.loader import QuantLawLoader
    loader = QuantLawLoader(data_dir, config)
    pair = loader.load_single(str(graph_path))
    graph_id, graph = pair

    scc_ids = set()
    for scc in nx.strongly_connected_components(
        nx.DiGraph([(e.source, e.target) for e in graph.edges])
    ):
        if len(scc) > 1:
            scc_ids |= scc

    nodes = []
    for cid, clause in graph.clauses.items():
        nodes.append({
            "id": cid,
            "heading": getattr(clause, "title", cid) or cid,
            "text": (getattr(clause, "content", "") or "")[:200],
            "type": "scc" if cid in scc_ids else "dag",
        })
    edges_list = [{"source": e.source, "target": e.target} for e in graph.edges]
    _save_json(GRAPH_FILE, {"graph_id": graph_id, "nodes": nodes, "edges": edges_list})

    return graph_id, graph, targets


def _select_targets(G: nx.DiGraph) -> dict:
    import random
    random.seed(42)

    sccs = sorted(
        [s for s in nx.strongly_connected_components(G) if len(s) > 1],
        key=len, reverse=True,
    )
    dag_nodes = []
    for scc_set in nx.strongly_connected_components(G):
        if len(scc_set) == 1:
            node = next(iter(scc_set))
            if not G.has_edge(node, node) and len(G.nodes[node].get("text", "")) > 50:
                dag_nodes.append(str(node))

    random.shuffle(dag_nodes)
    dag_targets = [
        {"id": nid, "heading": G.nodes[nid].get("heading", nid)}
        for nid in dag_nodes[:3]
    ]

    scc_targets = []
    for i, scc_nodes in enumerate(sccs[:2]):
        scc_list = sorted(str(n) for n in scc_nodes)
        scc_targets.append({
            "scc_id": f"scc_{i}",
            "size": len(scc_list),
            "node_ids": scc_list,
            "nodes": [{"id": n, "heading": G.nodes[n].get("heading", n)} for n in scc_list],
            "internal_edges": [
                {"source": str(u), "target": str(v)}
                for u, v in G.edges()
                if str(u) in set(scc_list) and str(v) in set(scc_list)
            ],
        })

    return {"dag_targets": dag_targets, "scc_targets": scc_targets}


# ── baseline computation ─────────────────────────────────────────────

async def compute_baseline(pipeline, graph, graph_id: str):
    """Run full SA-MCGS pipeline on unperturbed graph. Returns the result.
    Caches the result to experiments/results/baseline_{graph_id}.json
    """
    from experiments.perturbation import _deep_copy_graph
    from src.models.evaluation import ContractFinalResult
    
    cache_file = Path(f"experiments/results/baseline_{graph_id}.json")
    if cache_file.exists():
        logger.info(f"Loading cached baseline from {cache_file}")
        try:
            data = json.loads(cache_file.read_text())
            return ContractFinalResult(**data)
        except Exception as e:
            logger.warning(f"Failed to load baseline cache: {e}. Recomputing...")

    _update_status("baseline", "Computing baseline SA-MCGS evaluation...")
    logger.info("Computing baseline on original graph...")

    async def on_progress(current, total, detail):
        _update_status("baseline", detail, {"current": current, "total": total})
        logger.debug(f"Progress update: {current}/{total} - {detail}")

    g = _deep_copy_graph(graph)
    result = await pipeline.run_from_graph(g, graph_id=f"{graph_id}_baseline", on_progress=on_progress)

    logger.info(
        f"Baseline complete: overall_risk={result.overall_risk_score:.4f}, "
        f"high_risk={result.high_risk_clauses}"
    )
    
    # Save to cache
    _save_json(cache_file, result.dict())
    return result


def _extract_clause_metric(result, clause_id: str) -> dict[str, Any]:
    """Extract per-clause metrics from a pipeline result."""
    from experiments.runner import _extract_clause_metrics
    return _extract_clause_metrics(result, clause_id)


# ── perturbation job runner ──────────────────────────────────────────

async def _run_perturbation_job(
    job: dict,
    config: dict,
    llm_client,
    graph,
    graph_id: str,
    baseline_result,
) -> dict:
    """Run a single perturbation job.

    The full pipeline is re-run on the perturbed graph.  With DeepSeek's
    high concurrency the DAG evaluation phase finishes quickly.
    """
    from experiments.runner import _run_direct_llm, _extract_clause_metrics, _extract_search_stats, ExperimentResult
    from experiments.perturbation import perturb_type_a, perturb_type_b, perturb_type_c, _ensure_clause_text
    from src.pipeline import SaMCGSPipeline

    target_id = job["target_id"]
    ptype = job["perturbation_type"]
    cfg_name = job["config_name"]

    baseline_metrics = _extract_clause_metric(baseline_result, target_id)

    if ptype == "type_a":
        perturbed_g = perturb_type_a(graph, target_id)
    elif ptype == "type_b":
        perturbed_g = perturb_type_b(graph, job["scc_node_ids"], target_id, job["clause_y_id"])
    elif ptype == "type_c":
        perturbed_g = perturb_type_c(graph, job["scc_node_ids"], target_id)
    else:
        raise ValueError(f"Unknown perturbation: {ptype}")

    pipeline = SaMCGSPipeline(config, llm_client)

    if cfg_name == "direct_llm":
        clause = perturbed_g.clauses.get(target_id)
        text = _ensure_clause_text(clause, perturbed_g) if clause else ""
        score, detected, elapsed = await _run_direct_llm(llm_client, text, target_id)
        return {
            "graph_id": graph_id, "target_clause_id": target_id,
            "node_type": job["node_type"], "perturbation_type": ptype,
            "config_name": cfg_name, "risk_score": score,
            "high_risk_detected": detected, "time_seconds": elapsed,
            "delta_mcgs_risk": score - baseline_metrics.get("risk_score", 0.5),
            "run_id": job["run_id"], "round": job["round"],
        }

    t0 = time.monotonic()
    result = await pipeline.run_from_graph(perturbed_g, graph_id=f"{graph_id}_{ptype}")
    mcgs_time = time.monotonic() - t0

    metrics = _extract_clause_metrics(result, target_id)
    stats = _extract_search_stats(result)

    clause = perturbed_g.clauses.get(target_id)
    text = _ensure_clause_text(clause, perturbed_g) if clause else ""
    llm_score, llm_detected, llm_time = await _run_direct_llm(llm_client, text, target_id)

    exp = ExperimentResult(
        graph_id=graph_id, target_clause_id=target_id,
        node_type=job["node_type"], perturbation_type=ptype,
        mcgs_risk_score=metrics["risk_score"],
        mcgs_max_risk=metrics["max_risk"], mcgs_std=metrics["std"],
        mcgs_high_risk_detected=metrics["high_risk"],
        mcgs_uncertain_detected=metrics["uncertain"],
        direct_llm_risk_score=llm_score, direct_llm_detected=llm_detected,
        mcgs_time_seconds=mcgs_time, direct_llm_time_seconds=llm_time,
        delta_mcgs_risk=metrics["risk_score"] - baseline_metrics.get("risk_score", 0.5),
        delta_direct_llm_risk=llm_score - baseline_metrics.get("risk_score", 0.5),
    )
    res_dict = exp.to_dict()
    res_dict.update({"run_id": job["run_id"], "round": job["round"], "config_name": cfg_name})
    return res_dict


# ── main ─────────────────────────────────────────────────────────────

@app.command()
def main(
    config_path: str = typer.Option("config/deepseek.yaml"),
    repeats: int = typer.Option(5),
    concurrency: int = typer.Option(4, help="Max concurrent perturbation jobs"),
):
    config = _load_config(config_path)
    llm_client = _create_llm_client(config)
    graph_id, graph, targets = _setup_graph("data/quantlaw", config)

    jobs = []
    for r in range(1, repeats + 1):
        for t in targets["dag_targets"]:
            jobs.append({
                "round": "R2_DAG", "target_id": t["id"], "node_type": "dag",
                "perturbation_type": "type_a", "config_name": "experiment", "run_id": r,
            })
        for s in targets["scc_targets"]:
            for pt in ["type_a", "type_b", "type_c"]:
                jobs.append({
                    "round": "R3_SCC", "target_id": s["node_ids"][0],
                    "node_type": "scc", "perturbation_type": pt,
                    "scc_node_ids": s["node_ids"],
                    "clause_y_id": s["node_ids"][1] if len(s["node_ids"]) > 1 else None,
                    "config_name": "experiment", "run_id": r,
                })
        if r == 1:
            dag0 = targets["dag_targets"][0]["id"]
            for cfg in ["full", "no_graph_pruning", "no_mcgs", "direct_llm"]:
                jobs.append({
                    "round": "R4_ABLATION", "target_id": dag0,
                    "node_type": "dag", "perturbation_type": "type_a",
                    "config_name": cfg, "run_id": 1,
                })

    existing = _load_json(RESULTS_FILE)
    done_keys = {
        f"{j['graph_id']}|{j['target_clause_id']}|{j['perturbation_type']}|{j['config_name']}|{j['run_id']}"
        for j in existing if not j.get("error")
    }
    remaining = [
        j for j in jobs
        if f"{graph_id}|{j['target_id']}|{j['perturbation_type']}|{j['config_name']}|{j['run_id']}" not in done_keys
    ]

    logger.info(f"Total jobs: {len(jobs)}, Done: {len(done_keys)}, Remaining: {len(remaining)}")

    async def _run_all():
        t_start = time.monotonic()

        baseline_result = await compute_baseline(
            SaMCGSPipeline(config, llm_client), graph, graph_id
        )

        sem = asyncio.Semaphore(concurrency)
        completed = 0

        async def _run_one(i: int, job: dict):
            nonlocal completed
            async with sem:
                label = (
                    f"[{i+1}/{len(remaining)}] Run#{job['run_id']} "
                    f"{job['round']} {job['config_name']}:{job['perturbation_type']} "
                    f"on {job['target_id']}"
                )
                _update_status(
                    job["round"], label,
                    {"current": completed + 1, "total": len(remaining),
                     "elapsed": round(time.monotonic() - t_start)},
                )
                try:
                    res = await _run_perturbation_job(
                        job, config, llm_client, graph, graph_id, baseline_result,
                    )
                    existing.append(res)
                    _save_json(RESULTS_FILE, existing)
                    completed += 1
                    logger.info(f"  Done ({completed}/{len(remaining)}): {label}")
                except Exception as e:
                    logger.error(f"  Failed: {label} | {e}")
                    existing.append({"error": str(e), **job, "graph_id": graph_id})
                    _save_json(RESULTS_FILE, existing)

        await asyncio.gather(*[_run_one(i, j) for i, j in enumerate(remaining)])

        elapsed = time.monotonic() - t_start
        _update_status("done", f"All {len(remaining)} experiments complete in {elapsed:.0f}s")
        logger.info(f"All done in {elapsed:.0f}s ({elapsed/60:.1f} min)")

    from src.pipeline import SaMCGSPipeline
    asyncio.run(_run_all())


if __name__ == "__main__":
    app()

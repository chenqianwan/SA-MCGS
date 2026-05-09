"""FastAPI server with WebSocket for real-time pipeline visualization."""
from __future__ import annotations

import asyncio
import json
import time
import traceback
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from .llm.base import BaseLLMClient
from .models.clause import Clause, ClauseEvaluation
from .models.evaluation import ContractFinalResult
from .models.graph import DependencyGraph
from .models.search_tree import SearchTree
from .modules.aggregator import Aggregator
from .modules.dag_evaluator import DAGEvaluator
from .modules.graph_builder import GraphBuilder
from .modules.mcgs import MCGS
from .modules.parser import ClauseParser
from .modules.pruning import DominancePruner, InfluencePruner, VariancePruner
from .modules.scc_sampler import SCCSampler
from .modules.tarjan import TarjanSCCDetector

app = FastAPI(title="SA-MCGS Dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if RESULTS_DIR.exists():
    app.mount(
        "/experiments/results",
        StaticFiles(directory=str(RESULTS_DIR)),
        name="results",
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/demo", response_class=HTMLResponse)
async def demo():
    html_path = STATIC_DIR / "demo.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


def _create_llm_client(llm_config: dict) -> BaseLLMClient:
    from .llm import AnthropicClient, LocalClient, OpenAIClient

    provider = llm_config.get("provider", "openai")
    if provider == "openai":
        return OpenAIClient(llm_config)
    elif provider == "anthropic":
        return AnthropicClient(llm_config)
    elif provider == "local":
        return LocalClient(llm_config)
    raise ValueError(f"Unknown LLM provider: {provider}")


def _load_config() -> dict:
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "default.yaml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "llm": {"provider": "openai", "model": "gpt-4o", "api_key_env": "OPENAI_API_KEY"},
        "parsing": {"max_clause_length": 2000},
        "graph": {"max_clauses_per_batch": 20, "min_dependency_weight": 0.3},
        "scc": {"num_samples": 5, "temperature": 0.7},
        "pruning": {"variance_threshold": 0.01, "influence_threshold": 0.2},
        "mcgs": {"num_rollouts": 100, "ucb_exploration_weight": 1.414},
        "aggregation": {"high_risk_threshold": 0.7, "high_uncertainty_threshold": 0.15},
        "logging": {"level": "INFO"},
    }


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _graph_to_vis(graph: DependencyGraph) -> dict:
    scc_map: dict[str, str] = {}
    for scc in graph.sccs:
        for cid in scc.clause_ids:
            scc_map[cid] = scc.id

    nodes = []
    for cid, clause in graph.clauses.items():
        nodes.append({
            "id": cid,
            "title": clause.title,
            "scc": scc_map.get(cid),
            "is_dag": cid in graph.dag_nodes,
        })

    edges = []
    for e in graph.edges:
        edges.append({
            "source": e.source,
            "target": e.target,
            "type": e.dependency_type.value,
            "weight": e.weight,
        })

    return {"nodes": nodes, "edges": edges}


def _search_tree_to_vis(tree: SearchTree) -> dict:
    nodes = []
    for scc_id, node in tree.nodes.items():
        branches = []
        for b in node.branches:
            branches.append({
                "id": b.branch_id,
                "is_pruned": b.is_pruned,
                "pruned_by": b.pruned_by,
                "visit_count": b.visit_count,
                "avg_reward": round(b.avg_reward, 4),
                "avg_risk": round(
                    sum(e.overall_risk_score for e in b.evaluation.values()) / max(len(b.evaluation), 1), 3
                ),
            })
        nodes.append({
            "scc_id": scc_id,
            "depth": node.depth,
            "visit_count": node.visit_count,
            "branches": branches,
        })
    return {"nodes": nodes, "topo_order": tree.scc_topological_order}


def _result_to_vis(result: ContractFinalResult) -> dict:
    clauses = []
    for cid, cr in result.clause_results.items():
        clauses.append({
            "id": cid,
            "mean": round(cr.mean_risk_score, 4),
            "median": round(cr.median_risk_score, 4),
            "max": round(cr.max_risk_score, 4),
            "std": round(cr.std_risk_score, 4),
            "confidence": round(cr.confidence, 4),
            "samples": cr.num_samples,
            "source": cr.source,
            "dimensions": {k: round(v, 4) for k, v in cr.dimension_scores.items()},
        })
    return {
        "contract_id": result.contract_id,
        "overall_risk": round(result.overall_risk_score, 4),
        "high_risk": result.high_risk_clauses,
        "uncertain": result.uncertain_clauses,
        "clauses": clauses,
        "scc_stats": result.scc_statistics,
        "search_stats": result.search_statistics,
    }


# ---------------------------------------------------------------------------
# WebSocket pipeline runner
# ---------------------------------------------------------------------------

@app.websocket("/ws/run")
async def ws_run(ws: WebSocket):
    await ws.accept()

    async def send(event: str, data: Any = None):
        await ws.send_json({"event": event, "data": data, "ts": time.time()})

    try:
        msg = await ws.receive_json()
        raw_text: str = msg.get("text", "")
        config_overrides: dict = msg.get("config", {})

        if not raw_text.strip():
            await send("error", {"message": "Empty contract text"})
            return

        config = _load_config()
        if config_overrides:
            for section, values in config_overrides.items():
                if section in config and isinstance(values, dict):
                    config[section].update(values)
                else:
                    config[section] = values

        llm_client = _create_llm_client(config["llm"])

        parser = ClauseParser(llm_client, config)
        graph_builder = GraphBuilder(llm_client, config)
        tarjan = TarjanSCCDetector()
        dag_evaluator = DAGEvaluator(llm_client, config)
        scc_sampler = SCCSampler(llm_client, config)
        variance_pruner = VariancePruner(config)
        dominance_pruner = DominancePruner(config)
        influence_pruner = InfluencePruner(config)
        mcgs = MCGS(config)
        aggregator = Aggregator(config)

        await send("phase", {"phase": 1, "step": "parse", "label": "条款分割..."})
        clauses = await parser.parse(raw_text)
        await send("clauses", {
            "count": len(clauses),
            "items": [{"id": c.id, "title": c.title, "length": len(c.content)} for c in clauses],
        })

        await send("phase", {"phase": 1, "step": "graph", "label": "依赖图构建..."})
        graph = await graph_builder.build(clauses)
        await send("phase", {"phase": 1, "step": "tarjan", "label": "Tarjan SCC 检测..."})
        graph = tarjan.detect(graph)
        await send("graph", _graph_to_vis(graph))
        await send("scc_info", {
            "num_sccs": len(graph.sccs),
            "scc_sizes": [s.size for s in graph.sccs],
            "dag_node_count": len(graph.dag_nodes),
            "dag_ratio": round(graph.metadata.get("dag_ratio", 0), 4),
            "sccs": [{"id": s.id, "clause_ids": s.clause_ids, "size": s.size} for s in graph.sccs],
        })

        await send("phase", {"phase": 2, "step": "dag_eval", "label": "DAG 确定性评估..."})
        dag_results = await dag_evaluator.evaluate(graph)
        dag_vis = {
            cid: {"score": round(ev.overall_risk_score, 4), "reasoning": ev.reasoning}
            for cid, ev in dag_results.items()
            if cid in graph.dag_nodes
        }
        await send("dag_results", dag_vis)

        scc_samples: dict = {}
        if graph.sccs:
            await send("phase", {"phase": 2, "step": "scc_sample", "label": "SCC 多次采样..."})
            scc_samples = await scc_sampler.sample_all_sccs(graph, dag_results)
            scc_variance = {
                s.id: {"variance": round(s.variance, 6), "size": s.size, "num_samples": len(s.samples)}
                for s in graph.sccs
            }
            await send("scc_samples", scc_variance)

        await send("phase", {"phase": 3, "step": "variance_prune", "label": "方差剪枝..."})
        vp_stats = variance_pruner.prune(graph)
        await send("pruning", {"type": "variance", **vp_stats})

        search_tree = scc_sampler.build_search_tree(graph, scc_samples)

        await send("phase", {"phase": 3, "step": "dominance_prune", "label": "支配剪枝..."})
        dp_stats = dominance_pruner.prune(search_tree)
        await send("pruning", {"type": "dominance", **dp_stats})

        await send("phase", {"phase": 3, "step": "influence_prune", "label": "影响力剪枝..."})
        ip_stats = influence_pruner.prune(search_tree, graph)
        await send("pruning", {"type": "influence", **ip_stats})

        await send("search_tree", _search_tree_to_vis(search_tree))

        active_nodes = {sid: n for sid, n in search_tree.nodes.items() if n.active_branches}
        total_active = sum(len(n.active_branches) for n in active_nodes.values())

        rollout_results: list[dict] = []
        if active_nodes and total_active > len(active_nodes):
            await send("phase", {"phase": 4, "step": "mcgs", "label": f"MCGS 搜索 ({mcgs.num_rollouts} rollouts)..."})
            rollout_results = mcgs.search(search_tree, dag_results, graph)
            rewards = [r["reward"] for r in rollout_results]
            await send("mcgs_progress", {
                "total_rollouts": len(rollout_results),
                "rewards": [round(r, 4) for r in rewards],
                "avg_reward": round(sum(rewards) / len(rewards), 4) if rewards else 0,
            })
        else:
            await send("phase", {"phase": 4, "step": "mcgs_skip", "label": "剪枝已解决所有 SCC，跳过搜索"})

        await send("phase", {"phase": 5, "step": "aggregate", "label": "统计聚合..."})
        collapsed_results: dict = {}
        for scc in graph.sccs:
            if scc.is_collapsed and scc.collapsed_value:
                collapsed_results.update(scc.collapsed_value)

        result = aggregator.aggregate(rollout_results, dag_results, collapsed_results, graph)
        result.contract_id = "contract"
        await send("result", _result_to_vis(result))
        await send("done", None)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.error(f"Pipeline error: {exc}\n{traceback.format_exc()}")
        try:
            await send("error", {"message": str(exc)})
        except Exception:
            pass

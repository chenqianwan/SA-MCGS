"""Main experiment orchestration script.

Runs the complete counterfactual perturbation experiment:
  Phase 3 Round 1: Smoke test (1 DAG + 1 SCC, Type A only)
  Phase 3 Round 2: DAG control group (5-10 DAG nodes, Type A)
  Phase 3 Round 3: SCC experiment group (2-3 SCCs, Type A/B/C)
  Phase 4: Ablation study (4 configs)
  Phase 5: Visualization

Usage:
    python -m experiments.run_experiment --round 1 --config config/default.yaml
    python -m experiments.run_experiment --round all
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
import yaml
from loguru import logger

app = typer.Typer()


def _load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _create_llm_client(config: dict):
    from src.llm import AnthropicClient, LocalClient, OpenAIClient
    provider = config.get("llm", {}).get("provider", "openai")
    if provider == "openai":
        return OpenAIClient(config["llm"])
    elif provider == "anthropic":
        return AnthropicClient(config["llm"])
    elif provider == "local":
        return LocalClient(config["llm"])
    raise ValueError(f"Unknown provider: {provider}")


def _load_graph(data_dir: str, config: dict, max_nodes: int = 0):
    """Load the 2019 DE graph via QuantLawLoader.

    If max_nodes > 0, extract a subgraph containing target nodes and their
    k-hop neighborhood, capped at max_nodes.
    """
    from src.data.loader import QuantLawLoader
    loader = QuantLawLoader(data_dir, config)

    gpickle = Path(data_dir) / "de" / "4_crossreference_graph" / "2019.gpickle.gz"
    if gpickle.exists():
        pair = loader.load_single(str(gpickle))
        if pair:
            return pair

    all_graphs = loader.load()
    de_graphs = [(gid, g) for gid, g in all_graphs if gid.startswith("de_")]
    if de_graphs:
        return de_graphs[-1]
    if all_graphs:
        return all_graphs[-1]

    raise FileNotFoundError(f"No graphs found in {data_dir}")


def _extract_subgraph(graph, target_ids: list[str], max_nodes: int = 500):
    """Extract a subgraph around target nodes for faster experiments."""
    import networkx as nx
    from src.models.graph import DependencyGraph

    G = nx.DiGraph()
    for e in graph.edges:
        G.add_edge(e.source, e.target)

    keep = set()
    for tid in target_ids:
        if tid not in G:
            continue
        # 2-hop neighborhood
        for hop1 in list(G.predecessors(tid)) + list(G.successors(tid)) + [tid]:
            keep.add(hop1)
            for hop2 in list(G.predecessors(hop1)) + list(G.successors(hop1)):
                keep.add(hop2)
                if len(keep) >= max_nodes:
                    break
            if len(keep) >= max_nodes:
                break

    # Also include all nodes from the same SCCs as target nodes
    # (will be computed after Tarjan, so just add connected components)
    for tid in target_ids:
        if tid in G:
            try:
                scc = nx.descendants(G, tid) & nx.ancestors(G, tid)
                scc.add(tid)
                keep.update(scc)
            except nx.NetworkXError:
                pass

    keep = keep & set(graph.clauses.keys())
    new_clauses = {k: v for k, v in graph.clauses.items() if k in keep}
    new_edges = [e for e in graph.edges if e.source in keep and e.target in keep]

    return DependencyGraph(
        clauses=new_clauses,
        edges=new_edges,
        metadata={**graph.metadata, "subgraph": True, "original_size": len(graph.clauses)},
    )


def _load_targets(targets_path: str = "experiments/data/experiment_targets.json") -> dict:
    return json.loads(Path(targets_path).read_text(encoding="utf-8"))


async def run_round1(config: dict, llm_client, graph, graph_id: str, targets: dict):
    """Phase 3 Round 1: Smoke test."""
    from .runner import ExperimentRunner

    runner = ExperimentRunner(config, llm_client)

    # 1a: One DAG node, Type A
    dag_target = targets["dag_targets"][0]["id"]
    logger.info(f"Round 1a: DAG smoke test on {dag_target}")
    exp_dag = await runner.run_single(
        graph, graph_id, dag_target,
        node_type="dag", perturbation_type="type_a",
    )
    if exp_dag.delta_mcgs_risk > 0:
        logger.info(f"  DAG smoke test PASSED: delta={exp_dag.delta_mcgs_risk:+.4f}")
    else:
        logger.warning(f"  DAG smoke test: delta={exp_dag.delta_mcgs_risk:+.4f} (expected > 0)")

    # 1b: One SCC node, Type A
    scc_target = targets["scc_targets"][0]
    scc_clause_id = scc_target["node_ids"][0]
    logger.info(f"Round 1b: SCC smoke test on {scc_clause_id}")
    exp_scc = await runner.run_single(
        graph, graph_id, scc_clause_id,
        node_type="scc", perturbation_type="type_a",
        scc_node_ids=scc_target["node_ids"],
    )
    logger.info(f"  SCC smoke test: delta={exp_scc.delta_mcgs_risk:+.4f}")

    runner.save_results("round1_smoke_results.json")
    return runner.results


async def run_round2(config: dict, llm_client, graph, graph_id: str, targets: dict):
    """Phase 3 Round 2: DAG control group."""
    from .runner import ExperimentRunner

    runner = ExperimentRunner(config, llm_client)
    dag_ids = [t["id"] for t in targets["dag_targets"]]
    results = await runner.run_dag_group(graph, graph_id, dag_ids)

    runner.save_results("round2_dag_results.json")

    summary = runner.compute_detection_rates()
    logger.info(f"Round 2 summary: {json.dumps(summary, indent=2)}")
    return results


async def run_round3(config: dict, llm_client, graph, graph_id: str, targets: dict):
    """Phase 3 Round 3: SCC experiment group."""
    from .runner import ExperimentRunner

    runner = ExperimentRunner(config, llm_client)
    results = await runner.run_scc_group(
        graph, graph_id, targets["scc_targets"],
        perturbation_types=["type_a", "type_b", "type_c"],
    )

    runner.save_results("round3_scc_results.json")

    summary = runner.compute_detection_rates()
    logger.info(f"Round 3 summary: {json.dumps(summary, indent=2)}")
    return results


async def run_ablation(config: dict, llm_client, graph, graph_id: str, targets: dict):
    """Phase 4: Ablation study."""
    from .ablation import AblationRunner
    from .perturbation import perturb_type_a, perturb_type_b

    ablation = AblationRunner(config, llm_client)

    # Ablation on one DAG + one SCC perturbation
    dag_target = targets["dag_targets"][0]["id"]
    dag_perturbed = perturb_type_a(graph, dag_target)
    await ablation.run_all_configs(
        dag_perturbed, graph_id, dag_target,
        node_type="dag", perturbation_type="type_a",
    )

    scc_target = targets["scc_targets"][0]
    scc_ids = scc_target["node_ids"]
    if len(scc_ids) >= 2:
        scc_perturbed = perturb_type_b(graph, scc_ids, scc_ids[0], scc_ids[1])
        await ablation.run_all_configs(
            scc_perturbed, graph_id, scc_ids[0],
            node_type="scc", perturbation_type="type_b",
        )

    ablation.save_results()

    summary = ablation.compute_detection_rates()
    logger.info(f"Ablation summary: {json.dumps(summary, indent=2)}")
    return ablation.results


def run_visualization():
    """Phase 5: Generate figures."""
    from .visualize import generate_all_figures

    # Merge all round results for comprehensive visualization
    all_results = []
    for fname in ["round1_smoke_results.json", "round2_dag_results.json", "round3_scc_results.json"]:
        path = Path("experiments/results") / fname
        if path.exists():
            all_results.extend(json.loads(path.read_text(encoding="utf-8")))

    if all_results:
        merged_path = Path("experiments/results/experiment_results.json")
        merged_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False, default=str))
        logger.info(f"Merged {len(all_results)} results into {merged_path}")

    generate_all_figures()


@app.command()
def main(
    round: str = typer.Option("all", help="Which round to run: 1, 2, 3, ablation, viz, all"),
    config_path: str = typer.Option("config/default.yaml", help="Config file"),
    data_dir: str = typer.Option("data/quantlaw", help="QuantLaw data root"),
    targets_path: str = typer.Option("experiments/data/experiment_targets.json", help="Targets JSON"),
):
    """Run counterfactual perturbation experiment rounds."""
    config = _load_config(config_path)

    if round == "viz":
        run_visualization()
        return

    llm_client = _create_llm_client(config)
    graph_id, full_graph = _load_graph(data_dir, config)
    targets = _load_targets(targets_path)

    # Extract subgraph around experiment targets for faster execution
    all_target_ids = [t["id"] for t in targets["dag_targets"]]
    for scc in targets["scc_targets"]:
        all_target_ids.extend(scc["node_ids"])
    graph = _extract_subgraph(full_graph, all_target_ids, max_nodes=600)

    logger.info(f"Graph: {graph_id} (full={len(full_graph.clauses)}, subgraph={len(graph.clauses)} nodes, {len(graph.edges)} edges)")
    logger.info(f"DAG targets: {len(targets['dag_targets'])}, SCC targets: {len(targets['scc_targets'])}")

    async def _run():
        if round in ("1", "all"):
            logger.info("=" * 60)
            logger.info("Phase 3 Round 1: Smoke Test")
            logger.info("=" * 60)
            await run_round1(config, llm_client, graph, graph_id, targets)

        if round in ("2", "all"):
            logger.info("=" * 60)
            logger.info("Phase 3 Round 2: DAG Control Group")
            logger.info("=" * 60)
            await run_round2(config, llm_client, graph, graph_id, targets)

        if round in ("3", "all"):
            logger.info("=" * 60)
            logger.info("Phase 3 Round 3: SCC Experiment Group")
            logger.info("=" * 60)
            await run_round3(config, llm_client, graph, graph_id, targets)

        if round in ("ablation", "all"):
            logger.info("=" * 60)
            logger.info("Phase 4: Ablation Study")
            logger.info("=" * 60)
            await run_ablation(config, llm_client, graph, graph_id, targets)

        if round == "all":
            logger.info("=" * 60)
            logger.info("Phase 5: Visualization")
            logger.info("=" * 60)
            run_visualization()

    asyncio.run(_run())


if __name__ == "__main__":
    app()

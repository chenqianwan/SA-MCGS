"""Local LLM smoke test — end-to-end with Ollama llama3.1.

Generates a small synthetic graph (30 nodes), selects targets,
runs Phase 3 Round 1 (1 DAG + 1 SCC, Type A perturbation),
and prints detailed results.

Usage:
    python -m experiments.smoke_local
"""
from __future__ import annotations

import asyncio
import gzip
import json
import pickle
import random
import time
from pathlib import Path

import networkx as nx
import yaml
from loguru import logger


def generate_small_graph(n_dag: int = 20, scc_sizes: tuple = (3, 4)) -> nx.DiGraph:
    """Build a small graph with realistic negatable legal text for smoke testing."""
    rng = random.Random(42)
    G = nx.DiGraph()

    sections = [
        ("Vertragspflichten",
         "The seller shall deliver all goods within 30 days of the contract date. "
         "The buyer is entitled to inspect goods upon delivery and reject defective items."),
        ("Zahlungsbedingungen",
         "Payment shall be made within 14 days of invoice receipt. "
         "Late payment is permitted only with prior written approval from the creditor."),
        ("Gewährleistung",
         "The manufacturer shall warrant all products for a period of 24 months. "
         "The warranty is valid for manufacturing defects reported within the warranty period."),
        ("Haftungsbeschränkung",
         "Liability shall not exceed the total contract value. "
         "Each party has the right to claim damages for proven losses under this section."),
        ("Kündigungsrecht",
         "Either party shall have the right to terminate this agreement with 90 days notice. "
         "Termination is permitted only after completion of all outstanding obligations."),
        ("Geheimhaltung",
         "All parties shall maintain strict confidentiality of proprietary information. "
         "Disclosure is permitted only with express written consent of the disclosing party."),
        ("Wettbewerbsverbot",
         "The employee shall not engage in competing business activities for 12 months. "
         "This restriction applies to all markets where the employer currently operates."),
        ("Schadensersatz",
         "Damages shall be compensable for direct losses caused by breach of contract. "
         "The injured party is entitled to full compensation including lost profits."),
        ("Streitbeilegung",
         "Disputes shall be resolved through binding arbitration in Frankfurt. "
         "Each party has the right to seek injunctive relief in competent courts."),
        ("Schlussbestimmungen",
         "Amendments to this agreement shall require written consent of all parties. "
         "This contract is valid and applies to all transactions between the parties."),
    ]

    for i in range(n_dag):
        heading, text = sections[i % len(sections)]
        G.add_node(f"d{i}", heading=f"§{i+1} {heading}", key=f"BGB_§{i+1}",
                   text=text, document_type="section")

    for i in range(1, n_dag):
        if rng.random() < 0.6:
            target = rng.randint(0, i - 1)
            G.add_edge(f"d{i}", f"d{target}", edge_type="reference")

    scc_texts = [
        ("Gegenseitige Leistungspflicht",
         "The debtor shall perform all obligations as specified in the corresponding provisions. "
         "Performance is required within the timeframe established by the related sections."),
        ("Rücktrittsrecht bei Nichterfüllung",
         "Either party shall have the right to withdraw if the other party fails to perform. "
         "Withdrawal is permitted only after a reasonable grace period has expired."),
        ("Nacherfüllungsanspruch",
         "The buyer is entitled to demand supplementary performance before exercising other remedies. "
         "The seller shall bear all costs of supplementary performance."),
        ("Minderung des Kaufpreises",
         "The buyer has the right to reduce the purchase price proportionally to the defect. "
         "Price reduction shall be calculated based on the diminished value of the goods."),
        ("Schadenersatz statt der Leistung",
         "The creditor is entitled to claim damages in lieu of performance after failed cure. "
         "This right applies to all foreseeable losses arising from the breach."),
        ("Aufwendungsersatz",
         "The aggrieved party shall be reimbursed for all reasonable expenses incurred. "
         "Reimbursement is permitted for expenses made in reliance on the contract."),
        ("Unmöglichkeit der Leistung",
         "The obligor shall be released from performance if it becomes objectively impossible. "
         "The obligation to pay damages applies to cases of attributable impossibility."),
    ]

    node_idx = n_dag
    for sz in scc_sizes:
        nodes = []
        for j in range(sz):
            nid = f"s{node_idx}"
            heading, text = scc_texts[(node_idx - n_dag) % len(scc_texts)]
            G.add_node(nid,
                       heading=f"§{node_idx+1} {heading}",
                       key=f"BGB_§{node_idx+1}",
                       text=text,
                       document_type="section")
            nodes.append(nid)
            node_idx += 1
        for j in range(sz):
            G.add_edge(nodes[j], nodes[(j + 1) % sz], edge_type="reference")
        if sz > 2:
            G.add_edge(nodes[0], nodes[2], edge_type="reference")
        G.add_edge(f"d{rng.randint(0, n_dag-1)}", nodes[0], edge_type="reference")

    return G


def save_graph(G: nx.DiGraph, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as f:
        pickle.dump(G, f)
    logger.info(f"Saved graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges → {path}")


def select_targets(G: nx.DiGraph) -> dict:
    """Quick target selection for smoke test."""
    sccs = [s for s in nx.strongly_connected_components(G) if len(s) > 1]
    dag_nodes = []
    for scc_set in nx.strongly_connected_components(G):
        if len(scc_set) == 1:
            node = next(iter(scc_set))
            if not G.has_edge(node, node):
                dag_nodes.append(str(node))

    dag_targets = [{"id": nid, "heading": G.nodes[nid].get("heading", nid)} for nid in dag_nodes[:3]]

    scc_targets = []
    for i, scc_nodes in enumerate(sorted(sccs, key=len, reverse=True)[:2]):
        scc_list = sorted(str(n) for n in scc_nodes)
        scc_targets.append({
            "scc_id": f"scc_{i}",
            "size": len(scc_list),
            "node_ids": scc_list,
            "nodes": [{"id": n, "heading": G.nodes[n].get("heading", n)} for n in scc_list],
            "internal_edges": [{"source": str(u), "target": str(v)}
                               for u, v in G.edges() if str(u) in set(scc_list) and str(v) in set(scc_list)],
        })

    return {"dag_targets": dag_targets, "scc_targets": scc_targets}


async def run_smoke_test():
    t_total = time.monotonic()

    # --- Step 1: Generate small graph ---
    logger.info("=" * 60)
    logger.info("Phase 0: Generating small synthetic graph")
    logger.info("=" * 60)

    G = generate_small_graph(n_dag=10, scc_sizes=(3, 4))
    graph_path = Path("data/quantlaw/de/4_crossreference_graph/2019.gpickle.gz")
    save_graph(G, graph_path)

    sccs = [s for s in nx.strongly_connected_components(G) if len(s) > 1]
    logger.info(f"  Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}, SCCs: {len(sccs)}")

    targets = select_targets(G)
    targets_dir = Path("experiments/data")
    targets_dir.mkdir(parents=True, exist_ok=True)
    (targets_dir / "experiment_targets.json").write_text(
        json.dumps(targets, indent=2, ensure_ascii=False))
    logger.info(f"  DAG targets: {[t['id'] for t in targets['dag_targets']]}")
    logger.info(f"  SCC targets: {[t['scc_id'] for t in targets['scc_targets']]}")

    # --- Step 2: Load config and create LLM client ---
    logger.info("=" * 60)
    logger.info("Loading config and LLM client (Ollama llama3.1)")
    logger.info("=" * 60)

    config = yaml.safe_load(Path("config/local_smoke.yaml").read_text())
    from src.llm.local_client import LocalClient
    llm_client = LocalClient(config["llm"])

    # Quick connectivity test
    logger.info("Testing LLM connectivity...")
    t0 = time.monotonic()
    test_resp = await llm_client.call_json(
        'Rate this legal clause risk from 0.0-1.0. '
        'Clause: "All parties shall comply." '
        'Output JSON: {"overall_risk_score": 0.0, "reasoning": "..."}',
        temperature=0.0,
    )
    logger.info(f"  LLM responded in {time.monotonic()-t0:.1f}s: {test_resp}")

    # --- Step 3: Load graph through pipeline ---
    logger.info("=" * 60)
    logger.info("Phase 3 Round 1: Smoke Test (1 DAG + 1 SCC, Type A)")
    logger.info("=" * 60)

    from src.data.loader import QuantLawLoader
    loader = QuantLawLoader("data/quantlaw", config)
    pair = loader.load_single(str(graph_path))
    if not pair:
        raise RuntimeError("Failed to load graph")
    graph_id, graph = pair
    logger.info(f"  Loaded: {graph_id} ({len(graph.clauses)} clauses, {len(graph.edges)} edges)")

    # --- Step 4: Run experiment ---
    from experiments.runner import ExperimentRunner

    results_dir = Path("experiments/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    runner = ExperimentRunner(config, llm_client, output_dir=str(results_dir))

    # Round 1a: DAG node, Type A
    dag_target = targets["dag_targets"][0]["id"]
    logger.info(f"\n--- Round 1a: DAG Type A on {dag_target} ---")

    # Diagnostic: show baseline vs perturbed text
    from experiments.perturbation import perturb_type_a, _ensure_clause_text
    baseline_text = _ensure_clause_text(graph.clauses[dag_target], graph)
    perturbed_g = perturb_type_a(graph, dag_target)
    perturbed_text = perturbed_g.clauses[dag_target].content
    logger.info(f"  Baseline text: {baseline_text[:120]}...")
    logger.info(f"  Perturbed text: {perturbed_text[:120]}...")

    t0 = time.monotonic()
    exp_dag = await runner.run_single(
        graph, graph_id, dag_target,
        node_type="dag", perturbation_type="type_a",
    )
    dag_time = time.monotonic() - t0
    logger.info(f"  DAG result ({dag_time:.1f}s):")
    logger.info(f"    MCGS risk:  {exp_dag.mcgs_risk_score:.4f} (delta={exp_dag.delta_mcgs_risk:+.4f})")
    logger.info(f"    MCGS max:   {exp_dag.mcgs_max_risk:.4f}")
    logger.info(f"    Direct LLM: {exp_dag.direct_llm_risk_score:.4f} (delta={exp_dag.delta_direct_llm_risk:+.4f})")
    logger.info(f"    MCGS detected: {exp_dag.mcgs_high_risk_detected or exp_dag.mcgs_uncertain_detected}")
    logger.info(f"    LLM detected:  {exp_dag.direct_llm_detected}")

    # Round 1b: SCC node, Type A
    scc_target = targets["scc_targets"][0]
    scc_clause = scc_target["node_ids"][0]
    logger.info(f"\n--- Round 1b: SCC Type A on {scc_clause} ---")

    # Diagnostic
    scc_baseline_text = _ensure_clause_text(graph.clauses[scc_clause], graph)
    scc_perturbed_g = perturb_type_a(graph, scc_clause)
    scc_perturbed_text = scc_perturbed_g.clauses[scc_clause].content
    logger.info(f"  Baseline text: {scc_baseline_text[:120]}...")
    logger.info(f"  Perturbed text: {scc_perturbed_text[:120]}...")

    t0 = time.monotonic()
    exp_scc = await runner.run_single(
        graph, graph_id, scc_clause,
        node_type="scc", perturbation_type="type_a",
        scc_node_ids=scc_target["node_ids"],
    )
    scc_time = time.monotonic() - t0
    logger.info(f"  SCC result ({scc_time:.1f}s):")
    logger.info(f"    MCGS risk:  {exp_scc.mcgs_risk_score:.4f} (delta={exp_scc.delta_mcgs_risk:+.4f})")
    logger.info(f"    MCGS max:   {exp_scc.mcgs_max_risk:.4f}")
    logger.info(f"    Direct LLM: {exp_scc.direct_llm_risk_score:.4f} (delta={exp_scc.delta_direct_llm_risk:+.4f})")
    logger.info(f"    MCGS detected: {exp_scc.mcgs_high_risk_detected or exp_scc.mcgs_uncertain_detected}")
    logger.info(f"    LLM detected:  {exp_scc.direct_llm_detected}")

    # Save results
    out_path = runner.save_results("smoke_local_results.json")

    total_time = time.monotonic() - t_total

    # --- Summary ---
    logger.info("\n" + "=" * 60)
    logger.info("SMOKE TEST SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Model:        {config['llm']['model']} (Ollama local)")
    logger.info(f"  Graph:        {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(sccs)} SCCs")
    logger.info(f"  Total time:   {total_time:.1f}s")
    logger.info(f"  DAG time:     {dag_time:.1f}s")
    logger.info(f"  SCC time:     {scc_time:.1f}s")
    logger.info(f"  LLM calls:    {llm_client._call_count if hasattr(llm_client, '_call_count') else 'N/A'}")
    logger.info(f"")
    logger.info(f"  DAG Type A:   delta_mcgs={exp_dag.delta_mcgs_risk:+.4f}  delta_llm={exp_dag.delta_direct_llm_risk:+.4f}")
    logger.info(f"  SCC Type A:   delta_mcgs={exp_scc.delta_mcgs_risk:+.4f}  delta_llm={exp_scc.delta_direct_llm_risk:+.4f}")
    logger.info(f"")
    dag_pass = exp_dag.delta_mcgs_risk > 0
    scc_pass = exp_scc.delta_mcgs_risk > 0
    logger.info(f"  DAG smoke:    {'PASS ✓' if dag_pass else 'FAIL ✗'}")
    logger.info(f"  SCC smoke:    {'PASS ✓' if scc_pass else 'FAIL ✗'}")
    logger.info(f"  Results:      {out_path}")
    logger.info("=" * 60)

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(run_smoke_test())

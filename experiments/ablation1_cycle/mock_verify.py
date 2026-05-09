"""Quick mock verification: confirm TreeMCTS fails on 10-node cycle.

Expected behavior:
  1. Tree node count >> graph node count (explosion due to cycle re-expansion)
  2. Avg rollout steps near max_depth (trapped in cycle)
  3. Q-value oscillation high (inconsistent backprop from cycle-averaged rollouts)

Usage:
    python -m experiments.ablation1_cycle.mock_verify
"""
from __future__ import annotations

import random
from experiments.ablation1_cycle.graph_generator import generate_dag, generate_simple_cycle
from experiments.ablation1_cycle.mock_llm import MockEvaluator
from experiments.ablation1_cycle.search_methods import TreeMCTS, SA_MCGS


def run_mock_verify():
    random.seed(42)
    print("=" * 70)
    print("MOCK VERIFICATION: TreeMCTS on Cycle-10 vs DAG-10")
    print("=" * 70)

    # --- Cycle-10 graph ---
    cycle_graph = generate_simple_cycle(cycle_size=10, dag_prefix=0, dag_suffix=0)
    print(f"\nCycle-10 graph: {len(cycle_graph.nodes)} nodes, "
          f"{len(cycle_graph.edges)} edges, "
          f"anomaly={cycle_graph.anomaly_nodes}")

    evaluator_cycle = MockEvaluator(cycle_graph, noise_std=0.12, context_influence=0.25)

    # Run TreeMCTS on cycle
    random.seed(42)
    tree_mcts_cycle = TreeMCTS(
        graph=cycle_graph,
        evaluator=evaluator_cycle,
        max_iterations=100,
        rollout_max_depth=30,
        exploration_c=1.414,
    )
    result_tree_cycle = tree_mcts_cycle.run()

    # Run SA-MCGS on same cycle
    random.seed(42)
    sa_mcgs_cycle = SA_MCGS(
        graph=cycle_graph,
        evaluator=evaluator_cycle,
        max_iterations=100,
        window_size=4,
        exploration_c=1.414,
    )
    result_sa_cycle = sa_mcgs_cycle.run()

    # --- DAG-10 graph ---
    random.seed(42)
    dag_graph = generate_dag(n=10)
    evaluator_dag = MockEvaluator(dag_graph, noise_std=0.12, context_influence=0.25)

    random.seed(42)
    tree_mcts_dag = TreeMCTS(
        graph=dag_graph,
        evaluator=evaluator_dag,
        max_iterations=100,
        rollout_max_depth=30,
        exploration_c=1.414,
    )
    result_tree_dag = tree_mcts_dag.run()

    # === Print Results ===
    print("\n" + "-" * 70)
    print("FAILURE MODE 1: SEARCH TREE EXPLOSION")
    print("-" * 70)
    print(f"  TreeMCTS on DAG-10:    {result_tree_dag.tree_node_count} tree nodes "
          f"(graph has {len(dag_graph.nodes)} nodes)")
    print(f"  TreeMCTS on Cycle-10:  {result_tree_cycle.tree_node_count} tree nodes "
          f"(graph has {len(cycle_graph.nodes)} nodes)")
    ratio = result_tree_cycle.tree_node_count / max(1, result_tree_dag.tree_node_count)
    print(f"  Explosion ratio:       {ratio:.1f}x")
    if result_tree_cycle.tree_node_count > len(cycle_graph.nodes) * 2:
        print(f"  >>> CONFIRMED: Tree explodes (tree nodes >> graph nodes)")
    else:
        print(f"  !!! NOT confirmed: tree size is not much larger than graph size")

    print("\n" + "-" * 70)
    print("FAILURE MODE 2: ROLLOUT WASTE (trapped in cycle)")
    print("-" * 70)
    print(f"  TreeMCTS on DAG-10:    avg {result_tree_dag.avg_rollout_steps:.1f} steps/rollout "
          f"(max_depth=30)")
    print(f"  TreeMCTS on Cycle-10:  avg {result_tree_cycle.avg_rollout_steps:.1f} steps/rollout "
          f"(max_depth=30)")
    print(f"  Cycle hit rate:        {result_tree_cycle.rollout_hit_cycle_rate:.0%} of rollouts "
          f"entered a cycle")
    if result_tree_cycle.avg_rollout_steps > result_tree_dag.avg_rollout_steps * 1.5:
        print(f"  >>> CONFIRMED: Rollouts trapped in cycle (longer avg steps)")
    else:
        print(f"  !!! NOT confirmed: rollout lengths similar")

    print("\n" + "-" * 70)
    print("FAILURE MODE 3: Q-VALUE DILUTION (all nodes → same average)")
    print("-" * 70)
    print(f"  TreeMCTS on DAG-10:    Q-spread = {result_tree_dag.q_spread:.4f}")
    print(f"  TreeMCTS on Cycle-10:  Q-spread = {result_tree_cycle.q_spread:.4f}")
    print(f"  SA-MCGS on Cycle-10:   Q-spread = {result_sa_cycle.q_spread:.4f}")
    print(f"  (Q-oscillation: DAG={result_tree_dag.q_oscillation:.4f}, "
          f"Cycle={result_tree_cycle.q_oscillation:.4f}, "
          f"SA-MCGS={result_sa_cycle.q_oscillation:.4f})")
    if result_tree_cycle.q_spread < result_tree_dag.q_spread * 0.5:
        print(f"  >>> CONFIRMED: Cycle dilutes Q-values (spread {result_tree_cycle.q_spread:.4f} "
              f"<< DAG spread {result_tree_dag.q_spread:.4f})")
    elif result_sa_cycle.q_spread > result_tree_cycle.q_spread * 1.5:
        print(f"  >>> CONFIRMED: SA-MCGS maintains spread while TreeMCTS loses it")
    else:
        print(f"  !!! NOT confirmed: Q-spread similar")

    print("\n" + "-" * 70)
    print("DETECTION ACCURACY")
    print("-" * 70)
    print(f"  TreeMCTS on DAG-10:    target rank = {result_tree_dag.target_rank}, "
          f"hit@3 = {result_tree_dag.hit_top3}")
    print(f"  TreeMCTS on Cycle-10:  target rank = {result_tree_cycle.target_rank}, "
          f"hit@3 = {result_tree_cycle.hit_top3}")
    print(f"  SA-MCGS on Cycle-10:   target rank = {result_sa_cycle.target_rank}, "
          f"hit@3 = {result_sa_cycle.hit_top3}")

    # Q-value progression for anomaly node
    if cycle_graph.anomaly_nodes:
        anom = cycle_graph.anomaly_nodes[0]
        print(f"\n" + "-" * 70)
        print(f"Q-VALUE TRACE for anomaly node '{anom}' (TreeMCTS on Cycle):")
        print("-" * 70)
        trace = [r.q_values.get(anom, 0.0) for r in result_tree_cycle.history]
        for i in range(0, len(trace), 10):
            chunk = trace[i:i+10]
            vals = " ".join(f"{v:.3f}" for v in chunk)
            print(f"  iter {i:3d}-{i+len(chunk)-1:3d}: {vals}")

    # Visit distribution comparison
    print(f"\n" + "-" * 70)
    print("VISIT DISTRIBUTION (TreeMCTS on Cycle-10)")
    print("-" * 70)
    sorted_visits = sorted(
        result_tree_cycle.final_visit_counts.items(),
        key=lambda x: -x[1]
    )
    for nid, v in sorted_visits:
        bar = "#" * min(50, v)
        is_anom = "(ANOMALY)" if nid in cycle_graph.anomaly_nodes else ""
        print(f"  {nid:4s}: {v:4d} visits | {bar} {is_anom}")

    print(f"\n  Visit entropy (TreeMCTS/Cycle): {result_tree_cycle.visit_entropy:.2f}")
    print(f"  Visit entropy (SA-MCGS/Cycle):  {result_sa_cycle.visit_entropy:.2f}")
    print(f"  Visit entropy (TreeMCTS/DAG):   {result_tree_dag.visit_entropy:.2f}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    failures_confirmed = 0
    if result_tree_cycle.tree_node_count > len(cycle_graph.nodes) * 2:
        failures_confirmed += 1
    if result_tree_cycle.avg_rollout_steps > result_tree_dag.avg_rollout_steps * 1.5:
        failures_confirmed += 1
    if (result_tree_cycle.q_spread < result_tree_dag.q_spread * 0.5 or
            result_sa_cycle.q_spread > result_tree_cycle.q_spread * 1.5):
        failures_confirmed += 1
    print(f"  Failure modes confirmed: {failures_confirmed}/3")
    if failures_confirmed >= 2:
        print(f"  VERDICT: Mock verification PASSED - proceed with full experiment")
    else:
        print(f"  VERDICT: Mock verification INSUFFICIENT - need parameter tuning")


if __name__ == "__main__":
    run_mock_verify()

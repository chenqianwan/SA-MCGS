"""Ablation 1b: Real LLM experiment on actual CUAD contract graphs with cycles.

Uses DeepSeek-Chat to evaluate clause risk, comparing:
  - TreeMCTS: standard tree search directly on the cyclic contract graph
  - SA-MCGS: SCC-aware windowed evaluation with transposition table

Usage:
    python -m experiments.ablation1_cycle.run_real_llm
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
from openai import AsyncOpenAI


# ─── Configuration ───────────────────────────────────────────────────
# xhub proxy API — supports deepseek-chat, gpt-4o, etc.
XHUB_BASE_URL = "https://api3.xhub.chat/v1"
DEFAULT_MODEL = "deepseek-chat"

MAX_ITERATIONS = 50
ROLLOUT_MAX_DEPTH = 20
WINDOW_SIZE = 4
EXPLORATION_C = 1.414

# Deal packages to test (cross-contract merged graphs with real SCCs)
DEAL_PACKAGES_TO_TEST = [
    "AzulSa (2xMaintenance)",
    "NETGEAR (Distributor+2Amend)",
]


# ─── Graph Loading ───────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

@dataclass
class ContractGraph:
    contract_id: str
    nodes: dict[str, dict]  # id -> {title, content, node_type}
    adjacency: dict[str, list[str]]
    scc_nodes: set[str]
    scc_sizes: list[int]
    total_edges: int

    @property
    def node_ids(self) -> list[str]:
        return list(self.nodes.keys())


def load_deal_package_graph(pkg_name: str) -> ContractGraph | None:
    """Load and merge a cross-contract deal package, detecting SCCs."""
    from src.data.cuad_loader import CUADLoader
    from src.modules.tarjan import TarjanSCCDetector
    from scripts.analyze_deal_packages import (
        merge_graphs, add_cross_contract_edges, FG_DIR, DEAL_PACKAGES,
    )
    from experiments.run_clause_battle import add_medium_implicit_edges

    if pkg_name not in DEAL_PACKAGES:
        print(f"  [ERROR] Unknown package: {pkg_name}")
        return None

    loader = CUADLoader(str(FG_DIR.parent), config={"cuad": {"clause_only": False}})
    files = DEAL_PACKAGES[pkg_name]
    graphs = []
    for fname in files:
        fpath = FG_DIR / fname
        result = loader.load_single_graph(fpath)
        if result:
            graphs.append(result)

    if len(graphs) < 2:
        print(f"  [ERROR] Only {len(graphs)} graphs found for {pkg_name}")
        return None

    merged = merge_graphs(graphs)
    cross = add_cross_contract_edges(merged)
    merged.edges.extend(cross)
    merged = add_medium_implicit_edges(merged)
    merged = TarjanSCCDetector().detect(merged)

    # Convert DependencyGraph to ContractGraph format
    nodes = {}
    for cid, clause in merged.clauses.items():
        nodes[cid] = {
            "title": clause.title,
            "content": clause.content,
            "node_type": clause.metadata.get("node_type", "CLAUSE"),
        }

    adjacency: dict[str, list[str]] = {nid: [] for nid in nodes}
    for edge in merged.edges:
        if edge.source in nodes and edge.target in nodes:
            adjacency[edge.source].append(edge.target)

    scc_nodes = set()
    for scc in merged.sccs:
        scc_nodes.update(scc.clause_ids)

    return ContractGraph(
        contract_id=pkg_name,
        nodes=nodes,
        adjacency=adjacency,
        scc_nodes=scc_nodes,
        scc_sizes=sorted([s.size for s in merged.sccs], reverse=True),
        total_edges=len(merged.edges),
    )


# ─── LLM Evaluator ──────────────────────────────────────────────────

def _get_api_key() -> str:
    key = os.environ.get("XHUB_API_KEY", "")
    if not key:
        raise RuntimeError("XHUB_API_KEY environment variable not set")
    return key


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM output, handling markdown fences."""
    import re
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Find first { ... } block
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    return {}


class RealLLMEvaluator:
    """Evaluate clause risk using LLM API (auto-selects provider)."""

    SYSTEM_PROMPT = (
        "You are a legal risk assessment expert. "
        "Given one or more contract clauses, rate each clause's risk level "
        "from 0.0 (no risk) to 1.0 (extreme risk). Consider: financial exposure, "
        "liability scope, termination risk, compliance burden, and ambiguity. "
        "Respond in JSON format: {\"clause_id\": risk_score, ...}"
    )

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        api_key = _get_api_key()
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=XHUB_BASE_URL,
            timeout=180,
        )
        self.call_count = 0
        self.total_tokens = 0
        self.cache: dict[frozenset[str], dict[str, float]] = {}
        self._consecutive_errors = 0
        self.provider_name = "xhub"
        print(f"  [LLM] Using xhub / {self.model}")

    async def evaluate_window(
        self, graph: ContractGraph, window: list[str]
    ) -> dict[str, float]:
        """Evaluate a window of clauses. Uses cache (transposition table)."""
        key = frozenset(window)
        if key in self.cache:
            return self.cache[key]

        prompt_parts = []
        for nid in window:
            info = graph.nodes.get(nid, {})
            title = info.get("title") or nid
            content = info.get("content") or ""
            text = f"[{nid}] {title}"
            if content:
                text += f"\n{content[:500]}"
            prompt_parts.append(text)

        prompt = (
            "Evaluate the legal risk of each clause below (0.0-1.0).\n"
            "Return ONLY valid JSON: {\"clause_id\": risk_score}\n\n"
            + "\n---\n".join(prompt_parts)
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            self.call_count += 1
            if response.usage:
                self.total_tokens += (response.usage.prompt_tokens +
                                      response.usage.completion_tokens)

            content = response.choices[0].message.content or "{}"
            scores = _extract_json(content)
            self._consecutive_errors = 0
            result = {}
            for nid in window:
                val = scores.get(nid, scores.get(str(nid), 0.5))
                try:
                    result[nid] = float(val) if isinstance(val, (int, float, str)) else 0.5
                except (ValueError, TypeError):
                    result[nid] = 0.5
            self.cache[key] = result
            return result

        except Exception as e:
            self._consecutive_errors = getattr(self, '_consecutive_errors', 0) + 1
            if self._consecutive_errors <= 3:
                print(f"  [LLM ERROR] {e}")
            elif self._consecutive_errors == 4:
                print(f"  [LLM ERROR] Suppressing further errors ({e})")
            if self._consecutive_errors >= 10:
                raise RuntimeError(
                    f"LLM API failed {self._consecutive_errors} consecutive times. "
                    f"Last error: {e}"
                )
            return {nid: 0.5 for nid in window}

    async def close(self):
        await self.client.close()


# ─── TreeMCTS (Real LLM version) ────────────────────────────────────

@dataclass
class TreeNode:
    graph_node_id: str
    parent: TreeNode | None = None
    children: dict[str, TreeNode] = field(default_factory=dict)
    visit_count: int = 0
    total_value: float = 0.0
    is_expanded: bool = False


async def run_tree_mcts(
    graph: ContractGraph,
    evaluator: RealLLMEvaluator,
    max_iterations: int = MAX_ITERATIONS,
) -> dict:
    """Run true tree-based MCTS on contract graph using real LLM."""
    root_id = graph.node_ids[0]
    root = TreeNode(graph_node_id=root_id)
    tree_node_count = 1

    graph_visits: dict[str, int] = defaultdict(int)
    graph_total: dict[str, float] = defaultdict(float)
    rollout_steps_list: list[int] = []
    cycle_hits = 0

    for it in range(max_iterations):
        # Selection
        node = root
        path = [node]
        depth = 0
        while node.is_expanded and node.children and depth < 80:
            best = None
            best_ucb = -math.inf
            total = node.visit_count + 1
            for child in node.children.values():
                if child.visit_count == 0:
                    best = child
                    break
                exploit = child.total_value / child.visit_count
                explore = EXPLORATION_C * math.sqrt(math.log(total) / child.visit_count)
                ucb = exploit + explore
                if ucb > best_ucb:
                    best_ucb = ucb
                    best = child
            if best is None:
                break
            node = best
            path.append(node)
            depth += 1

        # Expansion
        gid = node.graph_node_id
        neighbors = graph.adjacency.get(gid, [])
        if neighbors and not node.is_expanded:
            for nbr in neighbors:
                if nbr not in node.children:
                    child = TreeNode(graph_node_id=nbr, parent=node)
                    node.children[nbr] = child
                    tree_node_count += 1
            node.is_expanded = True
            unvisited = [c for c in node.children.values() if c.visit_count == 0]
            chosen = random.choice(unvisited) if unvisited else random.choice(list(node.children.values()))
            path.append(chosen)
        else:
            chosen = node

        # Rollout: random walk collecting nodes, then evaluate
        current = chosen.graph_node_id
        rollout_path = [current]
        visited_in_rollout = {current}
        hit_cycle = False
        for _ in range(ROLLOUT_MAX_DEPTH):
            nbrs = graph.adjacency.get(current, [])
            if not nbrs:
                break
            nxt = random.choice(nbrs)
            if nxt in visited_in_rollout:
                hit_cycle = True
            visited_in_rollout.add(nxt)
            rollout_path.append(nxt)
            current = nxt

        rollout_steps_list.append(len(rollout_path))
        if hit_cycle:
            cycle_hits += 1

        # Evaluate rollout endpoint window using LLM
        eval_window = list(set(rollout_path[-WINDOW_SIZE:]))
        scores = await evaluator.evaluate_window(graph, eval_window)
        avg_value = sum(scores.values()) / len(scores) if scores else 0.5

        # Backpropagation
        for n in reversed(path):
            n.visit_count += 1
            n.total_value += avg_value
            graph_visits[n.graph_node_id] += 1
            graph_total[n.graph_node_id] += avg_value

        if (it + 1) % 10 == 0:
            print(f"    TreeMCTS iter {it+1}/{max_iterations}: "
                  f"tree={tree_node_count}, LLM calls={evaluator.call_count}")

    # Build final Q-values
    q_values = {}
    for nid in graph.node_ids:
        v = graph_visits[nid]
        q_values[nid] = graph_total[nid] / v if v > 0 else 0.0

    return {
        "method": "tree_mcts",
        "q_values": q_values,
        "visit_counts": dict(graph_visits),
        "tree_node_count": tree_node_count,
        "avg_rollout_steps": sum(rollout_steps_list) / len(rollout_steps_list) if rollout_steps_list else 0,
        "cycle_hit_rate": cycle_hits / max_iterations,
        "llm_calls": evaluator.call_count,
    }


# ─── SA-MCGS (Real LLM version) ─────────────────────────────────────

async def run_sa_mcgs(
    graph: ContractGraph,
    evaluator: RealLLMEvaluator,
    max_iterations: int = MAX_ITERATIONS,
) -> dict:
    """Run SA-MCGS windowed search on contract graph using real LLM."""
    visit_count: dict[str, int] = {nid: 0 for nid in graph.node_ids}
    total_risk: dict[str, float] = {nid: 0.0 for nid in graph.node_ids}

    # Reverse adjacency for window building
    rev_adj: dict[str, list[str]] = defaultdict(list)
    for src, targets in graph.adjacency.items():
        for tgt in targets:
            rev_adj[tgt].append(src)

    scc_list = list(graph.scc_nodes)

    for it in range(max_iterations):
        # UCB selection, focusing on SCC nodes
        if scc_list and random.random() < 0.8:
            seed = _ucb_select(scc_list, visit_count, total_risk)
        else:
            seed = _ucb_select(graph.node_ids, visit_count, total_risk)

        # Build window around seed
        window = [seed]
        window_set = {seed}
        for _ in range(WINDOW_SIZE - 1):
            candidates = []
            for n in window:
                for nbr in graph.adjacency.get(n, []):
                    if nbr not in window_set:
                        candidates.append(nbr)
                for nbr in rev_adj.get(n, []):
                    if nbr not in window_set:
                        candidates.append(nbr)
            if not candidates:
                break
            chosen = random.choice(candidates)
            window.append(chosen)
            window_set.add(chosen)

        # Evaluate with LLM (cache = transposition table)
        scores = await evaluator.evaluate_window(graph, window)

        for nid in window:
            score = scores.get(nid, 0.5)
            visit_count[nid] += 1
            total_risk[nid] += score

        if (it + 1) % 10 == 0:
            tt_size = len(evaluator.cache)
            print(f"    SA-MCGS iter {it+1}/{max_iterations}: "
                  f"LLM calls={evaluator.call_count}, TT size={tt_size}")

    q_values = {}
    for nid in graph.node_ids:
        v = visit_count[nid]
        q_values[nid] = total_risk[nid] / v if v > 0 else 0.0

    return {
        "method": "sa_mcgs",
        "q_values": q_values,
        "visit_counts": visit_count,
        "tree_node_count": 0,
        "avg_rollout_steps": 0,
        "cycle_hit_rate": 0,
        "llm_calls": evaluator.call_count,
    }


def _ucb_select(
    candidates: list[str],
    visit_count: dict[str, int],
    total_risk: dict[str, float],
) -> str:
    total = sum(visit_count.get(c, 0) for c in candidates) + 1
    best = None
    best_ucb = -math.inf
    for nid in candidates:
        n = visit_count.get(nid, 0)
        if n == 0:
            return nid
        exploit = total_risk[nid] / n
        explore = EXPLORATION_C * math.sqrt(math.log(total) / n)
        ucb = exploit + explore
        if ucb > best_ucb:
            best_ucb = ucb
            best = nid
    return best


# ─── Main ────────────────────────────────────────────────────────────

async def run_single_contract_graph(graph: ContractGraph) -> dict:
    """Run both methods on a contract graph and compare."""
    print(f"\n{'='*70}")
    print(f"Contract: {graph.contract_id}")
    print(f"  Nodes: {len(graph.nodes)}, Edges: {graph.total_edges}")
    print(f"  SCCs: {len(graph.scc_sizes)} (sizes: {graph.scc_sizes[:5]})")
    print(f"  SCC nodes: {len(graph.scc_nodes)}/{len(graph.nodes)} "
          f"({len(graph.scc_nodes)/len(graph.nodes):.0%})")

    if not graph.scc_nodes:
        print("  [SKIP] No SCCs in this contract")
        return {"contract": graph.contract_id, "skipped": True, "reason": "no_scc"}

    # Run TreeMCTS
    print(f"\n  --- TreeMCTS ({MAX_ITERATIONS} iterations) ---")
    evaluator_tree = RealLLMEvaluator()
    random.seed(42)
    t0 = time.monotonic()
    result_tree = await run_tree_mcts(graph, evaluator_tree)
    tree_time = time.monotonic() - t0
    await evaluator_tree.close()

    # Run SA-MCGS (fresh evaluator to track separate call count)
    print(f"\n  --- SA-MCGS ({MAX_ITERATIONS} iterations) ---")
    evaluator_sa = RealLLMEvaluator()
    random.seed(42)
    t0 = time.monotonic()
    result_sa = await run_sa_mcgs(graph, evaluator_sa)
    sa_time = time.monotonic() - t0
    await evaluator_sa.close()

    # Analyze results
    print(f"\n{'─'*70}")
    print("RESULTS COMPARISON")
    print(f"{'─'*70}")

    # Q-value spread
    tree_qvals = [v for v in result_tree["q_values"].values() if v > 0]
    sa_qvals = [v for v in result_sa["q_values"].values() if v > 0]
    tree_spread = (max(tree_qvals) - min(tree_qvals)) if len(tree_qvals) >= 2 else 0
    sa_spread = (max(sa_qvals) - min(sa_qvals)) if len(sa_qvals) >= 2 else 0

    print(f"\n  Q-Spread:       TreeMCTS={tree_spread:.4f}  SA-MCGS={sa_spread:.4f}")
    print(f"  Tree size:      {result_tree['tree_node_count']} nodes")
    print(f"  Avg rollout:    {result_tree['avg_rollout_steps']:.1f} steps")
    print(f"  Cycle hit rate: {result_tree['cycle_hit_rate']:.0%}")
    print(f"  LLM calls:      TreeMCTS={result_tree['llm_calls']}  "
          f"SA-MCGS={result_sa['llm_calls']} (TT saved {max(0, MAX_ITERATIONS - result_sa['llm_calls'])} calls)")
    print(f"  Time:           TreeMCTS={tree_time:.1f}s  SA-MCGS={sa_time:.1f}s")

    # Top-5 risk nodes comparison
    tree_top5 = sorted(result_tree["q_values"].items(), key=lambda x: -x[1])[:5]
    sa_top5 = sorted(result_sa["q_values"].items(), key=lambda x: -x[1])[:5]

    print(f"\n  Top-5 Risk (TreeMCTS):")
    for rank, (nid, q) in enumerate(tree_top5, 1):
        in_scc = "SCC" if nid in graph.scc_nodes else "DAG"
        title = (graph.nodes[nid].get("title") or nid)[:50] if nid in graph.nodes else nid
        print(f"    #{rank}: [{in_scc}] {nid} (Q={q:.3f}) - {title}")

    print(f"\n  Top-5 Risk (SA-MCGS):")
    for rank, (nid, q) in enumerate(sa_top5, 1):
        in_scc = "SCC" if nid in graph.scc_nodes else "DAG"
        title = (graph.nodes[nid].get("title") or nid)[:50] if nid in graph.nodes else nid
        print(f"    #{rank}: [{in_scc}] {nid} (Q={q:.3f}) - {title}")

    # SCC-specific analysis
    scc_tree_qs = [result_tree["q_values"].get(n, 0) for n in graph.scc_nodes]
    scc_sa_qs = [result_sa["q_values"].get(n, 0) for n in graph.scc_nodes]
    non_scc = [n for n in graph.node_ids if n not in graph.scc_nodes]
    nonscc_tree_qs = [result_tree["q_values"].get(n, 0) for n in non_scc]
    nonscc_sa_qs = [result_sa["q_values"].get(n, 0) for n in non_scc]

    print(f"\n  SCC vs non-SCC Q-value analysis:")
    if scc_tree_qs:
        print(f"    TreeMCTS SCC avg: {sum(scc_tree_qs)/len(scc_tree_qs):.3f}  "
              f"std: {_std(scc_tree_qs):.4f}")
    if nonscc_tree_qs:
        print(f"    TreeMCTS DAG avg: {sum(nonscc_tree_qs)/len(nonscc_tree_qs):.3f}  "
              f"std: {_std(nonscc_tree_qs):.4f}")
    if scc_sa_qs:
        print(f"    SA-MCGS  SCC avg: {sum(scc_sa_qs)/len(scc_sa_qs):.3f}  "
              f"std: {_std(scc_sa_qs):.4f}")
    if nonscc_sa_qs:
        print(f"    SA-MCGS  DAG avg: {sum(nonscc_sa_qs)/len(nonscc_sa_qs):.3f}  "
              f"std: {_std(nonscc_sa_qs):.4f}")

    return {
        "contract": graph.contract_id,
        "graph_nodes": len(graph.nodes),
        "graph_edges": graph.total_edges,
        "scc_count": len(graph.scc_sizes),
        "scc_sizes": graph.scc_sizes,
        "scc_node_ratio": len(graph.scc_nodes) / len(graph.nodes),
        "tree_mcts": {
            "tree_size": result_tree["tree_node_count"],
            "avg_rollout_steps": result_tree["avg_rollout_steps"],
            "cycle_hit_rate": result_tree["cycle_hit_rate"],
            "q_spread": tree_spread,
            "llm_calls": result_tree["llm_calls"],
            "time_sec": tree_time,
            "top5": tree_top5,
        },
        "sa_mcgs": {
            "q_spread": sa_spread,
            "llm_calls": result_sa["llm_calls"],
            "time_sec": sa_time,
            "top5": sa_top5,
        },
    }


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))


async def main():
    print("=" * 70)
    print(f"ABLATION 1b: Real LLM ({DEFAULT_MODEL}) on Cross-Contract Deal Packages")
    print("=" * 70)
    print(f"Config: {MAX_ITERATIONS} iterations, rollout_depth={ROLLOUT_MAX_DEPTH}, "
          f"window={WINDOW_SIZE}, API=xhub")

    results = []
    for pkg_name in DEAL_PACKAGES_TO_TEST:
        graph = load_deal_package_graph(pkg_name)
        if graph is None:
            continue
        result = await run_single_contract_graph(graph)
        results.append(result)

    # Save results
    output_path = Path(__file__).parent.parent / "results" / "ablation1_real_llm.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n\nResults saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

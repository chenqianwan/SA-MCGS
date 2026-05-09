"""Cross-domain SA-MCGS experiment with SIMULATED LLM rollouts.

Uses graph-structure-based heuristic scoring instead of real LLM calls
to validate the SA-MCGS pipeline works across all three domains.
When DeepSeek balance is recharged, swap SimulatedLLM -> OpenAIClient.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import math
import os
import random
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.clause import Clause, ClauseType
from src.models.graph import DependencyGraph, DependencyType, Edge, SCCInfo
from src.modules.tarjan import TarjanSCCDetector
from src.modules.alphago_mcgs import AlphaGoMCGS
from src.llm.base import BaseLLMClient, LLMResponse

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ─── Simulated LLM Client (graph-heuristic scoring) ─────────────────

class SimulatedLLMClient(BaseLLMClient):
    """Scores nodes by graph-structural features instead of LLM inference.
    
    Heuristics used:
    - In-degree / out-degree ratio (asymmetric nodes are suspicious)
    - Betweenness-like centrality (hub nodes propagate risk)
    - Random perturbation (simulates LLM stochasticity)
    """

    def __init__(self, graph: DependencyGraph, domain: str):
        super().__init__({"model": f"simulated-{domain}"})
        self.domain = domain
        self._adj: dict[str, list[str]] = defaultdict(list)
        self._rev: dict[str, list[str]] = defaultdict(list)
        for e in graph.edges:
            self._adj[e.source].append(e.target)
            self._rev[e.target].append(e.source)
        self._nodes = set(graph.clauses.keys())
        avg_degree = sum(len(v) for v in self._adj.values()) / max(1, len(self._nodes))
        self._avg_degree = avg_degree

    async def call(self, prompt: str, **kwargs) -> LLMResponse:
        return LLMResponse(content="{}", model=self.model)

    async def call_json(self, prompt: str, **kwargs) -> dict:
        clause_ids = re.findall(r'"([^"]+)":\s*\{"risk_score"', prompt)
        if not clause_ids:
            clause_ids = re.findall(r'### (?:Package|Category|Company): ([^\n]+)', prompt)
            clause_ids = [c.strip() for c in clause_ids]

        evaluations = {}
        conflicts = []

        for cid in clause_ids:
            out_deg = len(self._adj.get(cid, []))
            in_deg = len(self._rev.get(cid, []))
            total_deg = out_deg + in_deg

            asymmetry = abs(out_deg - in_deg) / max(1, total_deg)
            hub_score = min(1.0, total_deg / max(1, self._avg_degree * 3))
            noise = random.gauss(0, 0.1)

            if self.domain == "debian":
                risk = 0.3 + 0.3 * hub_score + 0.2 * asymmetry + noise
            elif self.domain == "wikipedia":
                risk = 0.4 + 0.25 * asymmetry + 0.2 * hub_score + noise
            elif self.domain == "sec":
                risk = 0.35 + 0.3 * asymmetry + 0.2 * hub_score + noise
            else:
                risk = 0.5 + noise

            risk = max(0.05, min(0.95, risk))
            evaluations[cid] = {
                "risk_score": round(risk, 3),
                "reasoning": f"degree={total_deg}, asymmetry={asymmetry:.2f}",
            }

        for i in range(len(clause_ids)):
            for j in range(i + 1, len(clause_ids)):
                a, b = clause_ids[i], clause_ids[j]
                if (a in self._adj and b in self._adj.get(a, []) or
                    b in self._adj and a in self._adj.get(b, [])):
                    if random.random() < 0.4:
                        conflicts.append({
                            "clause_a": a, "clause_b": b,
                            "description": f"circular dependency between {a} and {b}",
                        })

        return {"clause_evaluations": evaluations, "conflicts": conflicts}

    async def close(self):
        pass


# ─── Data loaders (same as run_cross_domain.py) ─────────────────────

def load_debian_graph() -> DependencyGraph:
    deps_file = Path(__file__).parent / "20241027.cards.debian_pkgs" / "20241027.debian_pkgs.deps.gz"
    if not deps_file.exists():
        raise FileNotFoundError(f"Debian CARDS data not found at {deps_file}")

    print(f"  [Debian] Loading from CARDS deps.gz...")
    clauses: dict[str, Clause] = {}
    edges: list[Edge] = []
    all_pkgs = set()

    with gzip.open(deps_file, 'rt', errors='replace') as f:
        for line in f:
            tokens = line.strip().split()
            if len(tokens) < 2:
                continue
            pkg = tokens[0]
            deps = tokens[1:]
            all_pkgs.add(pkg)
            all_pkgs.update(deps)
            for dep in deps:
                if dep != pkg:
                    edges.append(Edge(
                        source=pkg, target=dep,
                        dependency_type=DependencyType.REFERENCES, weight=0.8,
                    ))

    for pkg in all_pkgs:
        clauses[pkg] = Clause(
            id=pkg, title=pkg,
            content=f"Debian package: {pkg}. Software package in the Debian Bookworm distribution.",
            clause_type=ClauseType.OTHER,
        )

    valid_edges = [e for e in edges if e.source in clauses and e.target in clauses]
    print(f"  [Debian] {len(clauses)} packages, {len(valid_edges)} edges")
    return DependencyGraph(clauses=clauses, edges=valid_edges)


def load_wikipedia_graph() -> DependencyGraph:
    print("  [Wikipedia] Fetching category cycles from Wikipedia API...")
    all_cycles = []
    for page_num in range(1, 5):
        url = (
            f"https://en.wikipedia.org/w/api.php?action=parse"
            f"&page=User:SDZeroBot/Category%20cycles/{page_num}"
            f"&prop=wikitext&format=json"
        )
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'SA-MCGS/1.0'})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode())
            wt = data.get('parse', {}).get('wikitext', {}).get('*', '')
            for line in wt.strip().split('\n'):
                cats = re.findall(r'Category:([^|\]]+)', line.strip())
                if len(cats) >= 2:
                    all_cycles.append(cats)
            time.sleep(0.5)
        except Exception as e:
            print(f"    Page {page_num}: {e}")

    target = [c for c in all_cycles if 5 <= len(c) <= 12]
    selected = target[:8]
    print(f"  [Wikipedia] {len(all_cycles)} total cycles, selected {len(selected)}")

    clauses: dict[str, Clause] = {}
    edges: list[Edge] = []
    for cycle in selected:
        for i, cat in enumerate(cycle):
            cid = cat.replace(' ', '_')
            if cid not in clauses:
                clauses[cid] = Clause(
                    id=cid, title=cat,
                    content=f"Wikipedia category: {cat}. Part of the category hierarchy.",
                    clause_type=ClauseType.OTHER,
                )
            nxt = cycle[(i + 1) % len(cycle)].replace(' ', '_')
            edges.append(Edge(
                source=cid, target=nxt,
                dependency_type=DependencyType.REFERENCES, weight=0.8,
                reasoning=f"{cat} → {cycle[(i+1)%len(cycle)]}",
            ))

    print(f"  [Wikipedia] {len(clauses)} categories, {len(edges)} edges")
    return DependencyGraph(clauses=clauses, edges=edges)


def load_sec_graph() -> DependencyGraph:
    actual_file = Path(__file__).parent / "finance_blockchain" / "corpwatch" / "entities.ftm.json.gz"
    print(f"  [SEC EX-21] Loading from {actual_file.name}...")

    companies: dict[str, dict] = {}
    ownership_edges: list[tuple[str, str]] = []

    with open(actual_file, 'r') as f:
        for line in f:
            try:
                ent = json.loads(line.strip())
                schema = ent.get('schema')
                if schema == 'Company':
                    companies[ent['id']] = {
                        'name': ent.get('caption', ent['id']),
                        'country': ent.get('properties', {}).get('country', ['unknown'])[0],
                    }
                elif schema == 'Ownership':
                    props = ent.get('properties', {})
                    for owner in props.get('owner', []):
                        for asset in props.get('asset', []):
                            if owner != asset:
                                ownership_edges.append((owner, asset))
            except:
                continue

    graph_adj = defaultdict(set)
    all_nodes = set()
    for src, dst in ownership_edges:
        graph_adj[src].add(dst)
        all_nodes.add(src)
        all_nodes.add(dst)

    # Fast Tarjan to select SCCs
    idx_c = [0]; stack = []; on_s = set(); idx_m = {}; low_m = {}; sccs_raw = []
    for start in all_nodes:
        if start in idx_m: continue
        wk = [(start, iter(graph_adj.get(start, set())), True)]
        idx_m[start] = low_m[start] = idx_c[0]; idx_c[0] += 1
        stack.append(start); on_s.add(start)
        while wk:
            v, nb, _ = wk[-1]; found = False
            for w in nb:
                if w not in idx_m:
                    idx_m[w] = low_m[w] = idx_c[0]; idx_c[0] += 1
                    stack.append(w); on_s.add(w)
                    wk.append((w, iter(graph_adj.get(w, set())), True)); found = True; break
                elif w in on_s:
                    low_m[v] = min(low_m[v], idx_m[w])
            if not found:
                if low_m[v] == idx_m[v]:
                    scc = []
                    while True:
                        w = stack.pop(); on_s.discard(w); scc.append(w)
                        if w == v: break
                    sccs_raw.append(scc)
                wk.pop()
                if wk: low_m[wk[-1][0]] = min(low_m[wk[-1][0]], low_m[v])

    target_sccs = sorted([s for s in sccs_raw if 5 <= len(s) <= 12], key=len)[:6]
    print(f"  [SEC EX-21] Selected {len(target_sccs)} SCCs (size 5-12)")

    needed = set()
    for scc in target_sccs:
        needed.update(scc)

    clauses: dict[str, Clause] = {}
    edges: list[Edge] = []
    for nid in needed:
        info = companies.get(nid, {'name': nid, 'country': 'unknown'})
        clauses[nid] = Clause(
            id=nid, title=info['name'],
            content=f"Company: {info['name']}. Country: {info['country']}. SEC 10-K Exhibit 21.",
            clause_type=ClauseType.OTHER,
        )
    for src, dst in ownership_edges:
        if src in needed and dst in needed:
            edges.append(Edge(
                source=src, target=dst,
                dependency_type=DependencyType.REFERENCES, weight=0.8,
            ))

    print(f"  [SEC EX-21] Graph: {len(clauses)} companies, {len(edges)} edges")
    return DependencyGraph(clauses=clauses, edges=edges)


# ─── Run ─────────────────────────────────────────────────────────────

async def run_domain(name: str, domain_key: str, graph: DependencyGraph, max_sccs=3) -> dict:
    print(f"\n{'='*60}\n  Domain: {name}\n{'='*60}")

    detector = TarjanSCCDetector()
    graph = detector.detect(graph)

    target = sorted(
        [s for s in graph.sccs if 5 <= s.size <= 12],
        key=lambda s: s.size,
    )[:max_sccs]
    if not target:
        target = sorted(
            [s for s in graph.sccs if s.size >= 3],
            key=lambda s: s.size,
        )[:max_sccs]

    print(f"  All SCCs: {len(graph.sccs)}, sizes: {sorted([s.size for s in graph.sccs], reverse=True)[:15]}")
    print(f"  Target SCCs: {len(target)}, sizes: {[s.size for s in target]}")

    llm = SimulatedLLMClient(graph, domain_key)
    config = {
        "alphago_mcgs": {
            "budget": 40, "window_size": 4, "concurrency": 4,
            "ucb_exploration_weight": 1.414, "ucb_exploration_init": 2.5,
            "temperature": 0.3, "max_tokens": 2048, "tt_max_reuse": 2,
        },
        "detection": {"alpha": 0.1, "min_rollouts": 5},
    }

    results = {"domain": name, "domain_key": domain_key, "sccs": [], "summary": {}}

    for scc in target:
        print(f"\n  --- SCC {scc.id} ({scc.size} nodes) ---")
        node_names = {cid: graph.clauses[cid].title for cid in scc.clause_ids if cid in graph.clauses}
        for cid in scc.clause_ids[:6]:
            print(f"    {node_names.get(cid, cid)}")
        if scc.size > 6:
            print(f"    ... (+{scc.size - 6} more)")

        mcgs = AlphaGoMCGS(llm_client=llm, config=config)

        scc_result = await mcgs.search(graph, scc)
        scc_result["scc_id"] = scc.id
        scc_result["scc_size"] = scc.size
        scc_result["node_names"] = node_names

        print(f"\n  Results for SCC {scc.id}:")
        print(f"    Iterations: {scc_result['total_iterations']}")
        print(f"    LLM calls (simulated): {scc_result['llm_calls']}")
        print(f"    TT hit rate: {scc_result['tt_hit_rate']:.1%}")
        print(f"    OC detected anomalies: {scc_result['oc_count']}")
        if scc_result['oc_detected_clauses']:
            print(f"      Detected: {[node_names.get(c, c) for c in scc_result['oc_detected_clauses']]}")

        print(f"    Risk ranking (top 5):")
        for cid, score in scc_result['ranking_by_risk'][:5]:
            print(f"      {node_names.get(cid, cid):45s}  risk={score:.3f}")

        print(f"    Conflict ranking (top 5):")
        for cid, rate in scc_result['ranking_by_conflict_rate'][:5]:
            print(f"      {node_names.get(cid, cid):45s}  conflict_rate={rate:.3f}")

        if scc_result.get('edge_details'):
            top_edges = sorted(
                scc_result['edge_details'].values(),
                key=lambda x: -x['avg_conflict']
            )[:3]
            print(f"    Top conflict edges:")
            for ed in top_edges:
                s_name = node_names.get(ed['source'], ed['source'])
                t_name = node_names.get(ed['target'], ed['target'])
                print(f"      {s_name} → {t_name}: conflict={ed['avg_conflict']:.3f}")

        results["sccs"].append(scc_result)

    total_detected = sum(r.get('oc_count', 0) for r in results['sccs'] if isinstance(r, dict))
    total_nodes = sum(r.get('scc_size', 0) for r in results['sccs'] if isinstance(r, dict))
    results["summary"] = {
        "total_sccs_analyzed": len(target),
        "total_nodes": total_nodes,
        "total_oc_detected": total_detected,
        "detection_rate": total_detected / max(1, total_nodes),
    }

    return results


async def main():
    print("=" * 60)
    print("  SA-MCGS Cross-Domain Experiment (Simulated LLM)")
    print("  Validates: Graph Build → SCC Detect → MCGS Navigate → OC Detect")
    print("=" * 60)

    all_results = {}
    t0 = time.time()

    # Domain 1: Debian
    try:
        print("\n[1/3] Loading Debian package data...")
        g = load_debian_graph()
        all_results["debian"] = await run_domain("Debian Package Dependencies", "debian", g)
    except Exception as e:
        print(f"  Debian FAILED: {e}")
        import traceback; traceback.print_exc()
        all_results["debian"] = {"error": str(e)}

    # Domain 2: Wikipedia
    try:
        print("\n[2/3] Loading Wikipedia category data...")
        g = load_wikipedia_graph()
        all_results["wikipedia"] = await run_domain("Wikipedia Category Hierarchy", "wikipedia", g)
    except Exception as e:
        print(f"  Wikipedia FAILED: {e}")
        import traceback; traceback.print_exc()
        all_results["wikipedia"] = {"error": str(e)}

    # Domain 3: SEC EX-21
    try:
        print("\n[3/3] Loading SEC EX-21 corporate ownership data...")
        g = load_sec_graph()
        all_results["sec_ex21"] = await run_domain("SEC EX-21 Corporate Ownership", "sec", g)
    except Exception as e:
        print(f"  SEC EX-21 FAILED: {e}")
        import traceback; traceback.print_exc()
        all_results["sec_ex21"] = {"error": str(e)}

    elapsed = time.time() - t0

    # Save
    out_file = RESULTS_DIR / f"cross_domain_sim_{int(time.time())}.json"
    with open(out_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    # Final Summary
    print(f"\n\n{'='*60}")
    print(f"  FINAL SUMMARY  (total time: {elapsed:.1f}s)")
    print(f"{'='*60}")

    for dk, res in all_results.items():
        if "error" in res:
            print(f"\n  [{dk}] ERROR: {res['error']}")
            continue
        s = res.get("summary", {})
        print(f"\n  [{dk}] {res.get('domain', dk)}")
        print(f"    SCCs analyzed: {s.get('total_sccs_analyzed', 0)}")
        print(f"    Total nodes:   {s.get('total_nodes', 0)}")
        print(f"    OC detected:   {s.get('total_oc_detected', 0)}")
        print(f"    Detection rate: {s.get('detection_rate', 0):.1%}")

        for scc_r in res.get("sccs", []):
            if not isinstance(scc_r, dict) or "error" in scc_r:
                continue
            names = scc_r.get("node_names", {})
            detected = scc_r.get("oc_detected_clauses", [])
            top3 = scc_r.get("ranking_by_risk", [])[:3]
            print(f"    SCC {scc_r['scc_id']} ({scc_r['scc_size']} nodes):")
            if detected:
                print(f"      ⚠ Anomalies: {[names.get(c,c) for c in detected]}")
            print(f"      Top risk: {[(names.get(c,c), f'{s:.3f}') for c,s in top3]}")

    print(f"\n  Results saved: {out_file}")
    print(f"  NOTE: Using simulated LLM. Recharge DeepSeek for real LLM results.")


if __name__ == "__main__":
    asyncio.run(main())

"""Cross-domain Battle: Naive Prompting vs SA-MCGS

Runs face-to-face comparison using the SAME LLM models on the SAME SCCs:
  1. Naive Prompting — feed entire SCC to LLM in one shot (baseline paper approach)
  2. SA-MCGS — iterative structured search with windowed evaluation

Prompt formats adapted from baseline papers:
  - Debian: adapted from DI-BENCH (ACL 2025) dependency analysis methodology
  - Wikipedia: adapted from TaxoGlimpse (VLDB 2024) taxonomy classification
  - SEC EX-21: adapted from Fin-RATE (2026) cross-entity reasoning format

Ground truth for binary evaluation:
  - Debian: packages with known CVEs (ruby3.1 ~48 CVE, mono ~52 CVE)
  - Wikipedia: injected semantic contradictions (literature-backed)
  - SEC: circular ownership anomaly detection (expert labels TBD)

IMPORTANT: This script does NOT modify any existing results or configs.
Results are saved with "battle_v2_" prefix.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.clause import Clause, ClauseType
from src.models.graph import DependencyGraph, Edge, SCCInfo
from src.modules.tarjan import TarjanSCCDetector
from src.modules.alphago_mcgs import AlphaGoMCGS
from src.llm.openai_client import OpenAIClient

from run_cross_domain import (
    load_debian_graph,
    load_wikipedia_graph,
    load_sec_graph,
)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

XHUB_BASE_URL = "https://api3.xhub.chat/v1"

# ─── Models to test (all via XHub) ────────────────────────────────────
BATTLE_MODELS = [
    {"name": "gpt-4o",        "model_id": "gpt-4o"},
    {"name": "deepseek-v3",   "model_id": "deepseek-chat"},
]

# ─── SA-MCGS configs per domain ──────────────────────────────────────
MCGS_DEFAULT = {
    "alphago_mcgs": {
        "budget": 30, "window_size": 4, "concurrency": 4,
        "ucb_exploration_weight": 1.414, "ucb_exploration_init": 2.5,
        "temperature": 0.4, "max_tokens": 2048, "tt_max_reuse": 3,
    },
    "detection": {"alpha": 0.1, "min_rollouts": 6},
}

MCGS_WIKI = {
    "alphago_mcgs": {**MCGS_DEFAULT["alphago_mcgs"], "budget": 60},
    "detection": {"alpha": 0.1, "min_rollouts": 6},
}

# ─── Ground Truth: known defective nodes per domain ──────────────────
# Keys are substrings — if any GT key is a substring of a node ID, it's a
# known defect. Values describe the evidence source.
GROUND_TRUTH = {
    "debian": {
        "ruby3.1":  "~48 CVEs (NVD/CVE database)",
        "ruby":     "ruby ecosystem CVE propagation",
        "mono":     "~52 CVEs (NVD/CVE database)",
        "libmono":  "mono framework component, inherits mono CVE exposure",
    },
    "wikipedia": {},
    "sec_ex21": {},
}


def is_ground_truth_node(node_id: str, domain: str) -> bool:
    """Check if a node matches any ground truth defect pattern."""
    gt = GROUND_TRUTH.get(domain, {})
    node_lower = node_id.lower()
    return any(pattern.lower() in node_lower for pattern in gt)


def get_gt_evidence(node_id: str, domain: str) -> str:
    """Get the evidence string for a ground truth match."""
    gt = GROUND_TRUTH.get(domain, {})
    node_lower = node_id.lower()
    for pattern, evidence in gt.items():
        if pattern.lower() in node_lower:
            return evidence
    return ""


# ═══════════════════════════════════════════════════════════════════════
#  NAIVE PROMPTS — adapted from baseline paper methodologies
# ═══════════════════════════════════════════════════════════════════════

def build_naive_prompt_debian(
    clauses: dict[str, Clause],
    edges: list[Edge],
    scc_ids: list[str],
) -> str:
    """Naive one-shot prompt for Debian, adapted from DI-BENCH methodology.

    DI-BENCH (ACL 2025) feeds complete dependency context to LLM in one pass.
    We adapt: give full SCC package list + all dependency links, ask to rank
    security risk.
    """
    all_edges = [e for e in edges if e.source in set(scc_ids) and e.target in set(scc_ids)]

    pkg_section = "\n".join(
        f"- {clauses[cid].title}: {clauses[cid].content}"
        for cid in scc_ids if cid in clauses
    )
    dep_section = "\n".join(
        f"- {e.source} depends on {e.target}"
        for e in all_edges
    ) or "No direct dependencies listed."

    return (
        "You are a software supply chain security analyst.\n\n"
        "The following packages form a CIRCULAR DEPENDENCY in the Debian ecosystem. "
        "Circular dependencies increase the risk of CVE propagation, version conflicts, "
        "and cascading failures.\n\n"
        f"## All Packages in This Cycle ({len(scc_ids)} packages)\n{pkg_section}\n\n"
        f"## All Dependency Links\n{dep_section}\n\n"
        "## Task\n"
        "Analyze the ENTIRE circular dependency structure. For each package, assign a "
        "risk_score from 0.0 (safe) to 1.0 (critical security risk). Consider:\n"
        "- Known CVE history and vulnerability exposure\n"
        "- Degree of coupling (how many other packages depend on it)\n"
        "- Potential for cascading failures\n"
        "- Whether the package is a common attack surface\n\n"
        "Output STRICTLY as JSON:\n"
        '{"clause_evaluations": {\n'
        + ",\n".join(
            f'  "{cid}": {{"risk_score": 0.0, "reasoning": "brief explanation"}}'
            for cid in scc_ids
        )
        + '\n},\n"conflicts": [\n'
        '  {"clause_a": "pkg_id", "clause_b": "pkg_id", "description": "specific issue"}\n'
        "]}"
    )


def build_naive_prompt_wikipedia(
    clauses: dict[str, Clause],
    edges: list[Edge],
    scc_ids: list[str],
) -> str:
    """Naive one-shot prompt for Wikipedia, adapted from TaxoGlimpse methodology.

    TaxoGlimpse (VLDB 2024) tests taxonomy relationships as "Is A a subcategory of B?"
    We adapt: present all subcategory links in the cycle, ask to identify incorrect ones.
    """
    all_edges = [e for e in edges if e.source in set(scc_ids) and e.target in set(scc_ids)]

    cat_section = "\n".join(
        f"- {clauses[cid].title}"
        for cid in scc_ids if cid in clauses
    )
    link_section = "\n".join(
        f"- \"{clauses.get(e.source, Clause(id=e.source, title=e.source, content='')).title}\" "
        f"is a subcategory of "
        f"\"{clauses.get(e.target, Clause(id=e.target, title=e.target, content='')).title}\""
        for e in all_edges
    )

    return (
        "You are a taxonomy expert reviewing Wikipedia's category hierarchy.\n\n"
        "The following categories form a CYCLE in the subcategory relationships. "
        "A well-formed taxonomy should be a DAG (directed acyclic graph), so at least "
        "one subcategory link in this cycle must be incorrect.\n\n"
        f"## Categories in This Cycle ({len(scc_ids)} categories)\n{cat_section}\n\n"
        f"## Subcategory Relationships\n{link_section}\n\n"
        "## Task\n"
        "For each category, assess whether it is correctly placed in the hierarchy. "
        "Assign a risk_score from 0.0 (correctly placed) to 1.0 (clearly misplaced / "
        "causing the cycle). Identify which specific subcategory link(s) should be removed "
        "to break the cycle.\n\n"
        "Output STRICTLY as JSON:\n"
        '{"clause_evaluations": {\n'
        + ",\n".join(
            f'  "{cid}": {{"risk_score": 0.0, "reasoning": "brief explanation"}}'
            for cid in scc_ids
        )
        + '\n},\n"conflicts": [\n'
        '  {"clause_a": "cat_id", "clause_b": "cat_id", "description": "why this link is wrong"}\n'
        "]}"
    )


def build_naive_prompt_sec(
    clauses: dict[str, Clause],
    edges: list[Edge],
    scc_ids: list[str],
) -> str:
    """Naive one-shot prompt for SEC, adapted from Fin-RATE methodology.

    Fin-RATE (2026) tests cross-entity reasoning on SEC filings. We adapt:
    present full circular ownership structure, ask to identify erroneous links.
    """
    all_edges = [e for e in edges if e.source in set(scc_ids) and e.target in set(scc_ids)]

    comp_section = "\n".join(
        f"- {clauses[cid].title}: {clauses[cid].content}"
        for cid in scc_ids if cid in clauses
    )
    own_section = "\n".join(
        f"- \"{clauses.get(e.source, Clause(id=e.source, title=e.source, content='')).title}\" "
        f"owns/controls "
        f"\"{clauses.get(e.target, Clause(id=e.target, title=e.target, content='')).title}\""
        for e in all_edges
    )

    return (
        "You are a corporate governance analyst reviewing SEC 10-K Exhibit 21 filings.\n\n"
        "The following companies form a CIRCULAR OWNERSHIP structure. Circular ownership "
        "(A owns B, B owns C, C owns A) is anomalous and may indicate filing errors, "
        "complex tax avoidance structures, or regulatory violations.\n\n"
        f"## Companies in This Cycle ({len(scc_ids)} entities)\n{comp_section}\n\n"
        f"## Ownership Links\n{own_section}\n\n"
        "## Task\n"
        "Analyze the entire ownership structure. For each company, assign an "
        "anomaly_risk_score from 0.0 (normal subsidiary) to 1.0 (clearly anomalous / "
        "likely filing error). Consider:\n"
        "- Whether the ownership direction makes business sense\n"
        "- Tax haven jurisdictions\n"
        "- Shell company indicators\n"
        "- Cross-border ownership complexity\n\n"
        "Output STRICTLY as JSON:\n"
        '{"clause_evaluations": {\n'
        + ",\n".join(
            f'  "{cid}": {{"risk_score": 0.0, "reasoning": "brief explanation"}}'
            for cid in scc_ids
        )
        + '\n},\n"conflicts": [\n'
        '  {"clause_a": "company_id", "clause_b": "company_id", "description": "specific concern"}\n'
        "]}'
    )


# ═══════════════════════════════════════════════════════════════════════
#  SA-MCGS PROMPTS — windowed versions (reused from run_cross_domain.py)
# ═══════════════════════════════════════════════════════════════════════

def _mcgs_debian_prompt(self, window: list[str]) -> str:
    clauses_fmt = "\n\n".join(
        f"### Package: {self._clauses[cid].title}\n{self._clauses[cid].content}"
        for cid in window if cid in self._clauses
    )
    window_set = set(window)
    relevant_edges = [
        e for e in self._internal_edges
        if e.source in window_set and e.target in window_set
    ]
    deps_fmt = "\n".join(
        f"- {e.source} depends on {e.target} ({e.dependency_type.value})"
        for e in relevant_edges
    ) or "No direct dependencies between these packages."

    return (
        "You are a software supply chain security analyst examining a SUBSET of "
        "packages from a circular dependency cluster in the Debian ecosystem.\n\n"
        f"## Packages Under Analysis ({len(window)} of {len(self._scc_ids)} in this cycle)\n"
        f"{clauses_fmt}\n\n"
        f"## Dependency Links\n{deps_fmt}\n\n"
        "## Task\n"
        "Analyze whether these packages contain any security risk, version conflict, "
        "unnecessary tight coupling, or CVE propagation risk when considered together.\n"
        "For each package, assess its risk_score (0.0=safe, 1.0=critical) IN CONTEXT "
        "of the other packages. Identify specific conflicts between package pairs.\n\n"
        "Output STRICTLY as JSON:\n"
        '{"clause_evaluations": {\n'
        + ",\n".join(
            f'  "{cid}": {{"risk_score": 0.0, "reasoning": "brief"}}'
            for cid in window
        )
        + '\n},\n"conflicts": [\n'
        '  {"clause_a": "pkg_id", "clause_b": "pkg_id", "description": "..."}\n'
        "]}"
    )


def _mcgs_wikipedia_prompt(self, window: list[str]) -> str:
    clauses_fmt = "\n\n".join(
        f"### Category: {self._clauses[cid].title}\n{self._clauses[cid].content}"
        for cid in window if cid in self._clauses
    )
    window_set = set(window)
    relevant_edges = [
        e for e in self._internal_edges
        if e.source in window_set and e.target in window_set
    ]
    deps_fmt = "\n".join(
        f"- \"{e.source}\" is a subcategory of \"{e.target}\""
        for e in relevant_edges
    ) or "No direct subcategory links between these categories."

    return (
        "You are a Wikipedia taxonomy expert examining a SUBSET of categories from "
        "a CYCLIC subcategory chain. These categories form a loop which is an error — "
        "the category hierarchy should be a DAG (directed acyclic graph).\n\n"
        f"## Categories Under Analysis ({len(window)} of {len(self._scc_ids)} in this cycle)\n"
        f"{clauses_fmt}\n\n"
        f"## Subcategory Links\n{deps_fmt}\n\n"
        "## Task\n"
        "Determine which subcategory link(s) are INCORRECT and cause the cycle. "
        "For each category, assess its error_risk_score (0.0=correctly placed, "
        "1.0=clearly misplaced/causing the cycle). Be DECISIVE — give at least one "
        "category a score above 0.7 if you believe it is misplaced.\n\n"
        "Output STRICTLY as JSON:\n"
        '{"clause_evaluations": {\n'
        + ",\n".join(
            f'  "{cid}": {{"risk_score": 0.0, "reasoning": "brief"}}'
            for cid in window
        )
        + '\n},\n"conflicts": [\n'
        '  {"clause_a": "cat_id", "clause_b": "cat_id", "description": "..."}\n'
        "]}"
    )


def _mcgs_sec_prompt(self, window: list[str]) -> str:
    clauses_fmt = "\n\n".join(
        f"### Company: {self._clauses[cid].title}\n{self._clauses[cid].content}"
        for cid in window if cid in self._clauses
    )
    window_set = set(window)
    relevant_edges = [
        e for e in self._internal_edges
        if e.source in window_set and e.target in window_set
    ]
    deps_fmt = "\n".join(
        f"- \"{e.source}\" owns/controls \"{e.target}\""
        for e in relevant_edges
    ) or "No direct ownership links between these companies."

    return (
        "You are a corporate governance analyst examining a SUBSET of companies "
        "from a CIRCULAR OWNERSHIP structure found in SEC 10-K Exhibit 21 filings. "
        "Circular ownership (A owns B owns C owns A) is anomalous and indicates "
        "filing errors, complex tax structures, or regulatory concerns.\n\n"
        f"## Companies Under Analysis ({len(window)} of {len(self._scc_ids)} in this cycle)\n"
        f"{clauses_fmt}\n\n"
        f"## Ownership Links\n{deps_fmt}\n\n"
        "## Task\n"
        "Determine which ownership link(s) are most likely ERRONEOUS or problematic. "
        "For each company, assess its anomaly_risk_score (0.0=normal subsidiary, "
        "1.0=clearly anomalous/causing circular ownership). Identify specific "
        "suspicious ownership links.\n\n"
        "Output STRICTLY as JSON:\n"
        '{"clause_evaluations": {\n'
        + ",\n".join(
            f'  "{cid}": {{"risk_score": 0.0, "reasoning": "brief"}}'
            for cid in window
        )
        + '\n},\n"conflicts": [\n'
        '  {"clause_a": "company_id", "clause_b": "company_id", "description": "..."}\n'
        "]}"
    )


DOMAIN_MCGS_PROMPTS = {
    "debian": _mcgs_debian_prompt,
    "wikipedia": _mcgs_wikipedia_prompt,
    "sec_ex21": _mcgs_sec_prompt,
}

DOMAIN_NAIVE_PROMPTS = {
    "debian": build_naive_prompt_debian,
    "wikipedia": build_naive_prompt_wikipedia,
    "sec_ex21": build_naive_prompt_sec,
}


# ═══════════════════════════════════════════════════════════════════════
#  EXPERIMENT RUNNERS
# ═══════════════════════════════════════════════════════════════════════

async def run_naive(
    llm: OpenAIClient,
    model_name: str,
    domain: str,
    graph: DependencyGraph,
    scc: SCCInfo,
) -> dict:
    """Run Naive one-shot prompting on a single SCC."""
    t0 = time.time()

    prompt_fn = DOMAIN_NAIVE_PROMPTS[domain]
    scc_set = set(scc.clause_ids)
    scc_edges = [e for e in graph.edges if e.source in scc_set and e.target in scc_set]

    prompt = prompt_fn(graph.clauses, scc_edges, scc.clause_ids)

    parsed = await llm.call_json(prompt, temperature=0.0, max_tokens=4096, retries=2)

    elapsed = time.time() - t0

    evals = parsed.get("clause_evaluations", {})
    conflicts = parsed.get("conflicts", [])

    scores = {}
    reasonings = {}
    for cid in scc.clause_ids:
        info = evals.get(cid, {})
        scores[cid] = float(info.get("risk_score", 0.0))
        reasonings[cid] = info.get("reasoning", "")

    ranking = sorted(scores.items(), key=lambda x: -x[1])
    score_vals = list(scores.values())
    s_spread = max(score_vals) - min(score_vals) if score_vals else 0

    gt_nodes = [cid for cid in scc.clause_ids if is_ground_truth_node(cid, domain)]
    top1_hit = ranking[0][0] in gt_nodes if (ranking and gt_nodes) else None
    top3_ids = {r[0] for r in ranking[:3]}
    top3_hit = bool(top3_ids & set(gt_nodes)) if gt_nodes else None

    node_names = {
        cid: graph.clauses[cid].title
        for cid in scc.clause_ids if cid in graph.clauses
    }

    return {
        "method": "naive",
        "method_source": f"adapted from baseline paper ({domain})",
        "model": model_name,
        "domain": domain,
        "scc_size": scc.size,
        "scc_id": scc.id,
        "scc_clause_ids": scc.clause_ids,
        "llm_calls": 1,
        "time": elapsed,
        "scores": scores,
        "reasonings": reasonings,
        "ranking": ranking,
        "conflicts": conflicts,
        "score_spread": s_spread,
        "score_mean": sum(score_vals) / max(1, len(score_vals)),
        "score_max": max(score_vals) if score_vals else 0,
        "node_names": node_names,
        "ground_truth_nodes": gt_nodes,
        "gt_evidence": {n: get_gt_evidence(n, domain) for n in gt_nodes},
        "top1_hit": top1_hit,
        "top3_hit": top3_hit,
    }


async def run_sa_mcgs(
    llm: OpenAIClient,
    model_name: str,
    domain: str,
    graph: DependencyGraph,
    scc: SCCInfo,
    mcgs_config: dict,
) -> dict:
    """Run SA-MCGS on a single SCC."""
    t0 = time.time()

    prompt_fn = DOMAIN_MCGS_PROMPTS[domain]
    mcgs = AlphaGoMCGS(llm_client=llm, config=mcgs_config)
    mcgs._build_focused_prompt = lambda w, _self=mcgs: prompt_fn(_self, w)

    scc_result = await mcgs.search(graph, scc)

    elapsed = time.time() - t0

    scores = {}
    for cid, score in scc_result.get("ranking_by_risk", []):
        scores[cid] = score

    ranking = scc_result.get("ranking_by_risk", [])
    score_vals = list(scores.values())
    s_spread = max(score_vals) - min(score_vals) if score_vals else 0

    gt_nodes = [cid for cid in scc.clause_ids if is_ground_truth_node(cid, domain)]
    top1_hit = ranking[0][0] in gt_nodes if (ranking and gt_nodes) else None
    top3_ids = {r[0] for r in ranking[:3]}
    top3_hit = bool(top3_ids & set(gt_nodes)) if gt_nodes else None

    node_names = {
        cid: graph.clauses[cid].title
        for cid in scc.clause_ids if cid in graph.clauses
    }

    return {
        "method": "sa-mcgs",
        "model": model_name,
        "domain": domain,
        "scc_size": scc.size,
        "scc_id": scc.id,
        "scc_clause_ids": scc.clause_ids,
        "budget": mcgs_config["alphago_mcgs"]["budget"],
        "llm_calls": scc_result.get("llm_calls", 0),
        "tt_hits": scc_result.get("tt_hits", 0),
        "tt_hit_rate": scc_result.get("tt_hit_rate", 0),
        "time": elapsed,
        "scores": scores,
        "ranking": ranking,
        "oc_detected": scc_result.get("oc_detected_clauses", []),
        "oc_count": scc_result.get("oc_count", 0),
        "score_spread": s_spread,
        "score_mean": sum(score_vals) / max(1, len(score_vals)),
        "score_max": max(score_vals) if score_vals else 0,
        "node_names": node_names,
        "clause_details": scc_result.get("clause_details", {}),
        "ground_truth_nodes": gt_nodes,
        "gt_evidence": {n: get_gt_evidence(n, domain) for n in gt_nodes},
        "top1_hit": top1_hit,
        "top3_hit": top3_hit,
    }


# ═══════════════════════════════════════════════════════════════════════
#  MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════

def select_sccs(
    graph: DependencyGraph,
    min_size: int = 5,
    max_size: int = 15,
    max_count: int = 2,
) -> list[SCCInfo]:
    """Select representative SCCs: prefer one small (5-6) and one larger (7+)."""
    detector = TarjanSCCDetector()
    graph = detector.detect(graph)

    candidates = sorted(
        [s for s in graph.sccs if min_size <= s.size <= max_size],
        key=lambda s: s.size,
    )

    if len(candidates) <= max_count:
        return candidates

    small = [s for s in candidates if s.size <= 6]
    large = [s for s in candidates if s.size >= 7]

    selected = []
    if small:
        selected.append(small[0])
    if large:
        selected.append(large[-1])

    while len(selected) < max_count and candidates:
        for c in candidates:
            if c not in selected:
                selected.append(c)
                break
        else:
            break

    return sorted(selected, key=lambda s: s.size)


async def main():
    api_key = os.environ.get("XHUB_API_KEY", "")
    if not api_key:
        api_key = input("Enter XHUB API key: ").strip()
        os.environ["XHUB_API_KEY"] = api_key
    if not api_key:
        raise RuntimeError("XHUB_API_KEY is required")

    print("=" * 70)
    print("  SA-MCGS BATTLE: Naive Prompting vs SA-MCGS")
    print("  Models: " + ", ".join(m["name"] for m in BATTLE_MODELS))
    print("  Domains: Debian, Wikipedia, SEC EX-21")
    print("  Evaluation: Binary detection (Top-1/Top-3 hit on ground truth)")
    print("=" * 70)

    # ── Load all domain graphs ──
    print("\n[LOAD] Loading domain data...")
    graphs = {}

    print("  Loading Debian...")
    graphs["debian"] = load_debian_graph()

    print("  Loading Wikipedia...")
    graphs["wikipedia"] = load_wikipedia_graph()

    print("  Loading SEC EX-21...")
    graphs["sec_ex21"] = load_sec_graph()

    # ── Select SCCs per domain ──
    domain_sccs: dict[str, list[SCCInfo]] = {}
    for domain, graph in graphs.items():
        sccs = select_sccs(graph, min_size=5, max_size=15, max_count=2)
        domain_sccs[domain] = sccs
        print(f"  [{domain}] Selected {len(sccs)} SCCs: sizes {[s.size for s in sccs]}")

    # ── Run all experiments ──
    all_results = []
    total_exps = sum(
        len(sccs) * len(BATTLE_MODELS) * 2
        for sccs in domain_sccs.values()
    )
    exp_idx = 0

    for domain, sccs in domain_sccs.items():
        graph = graphs[domain]
        mcgs_cfg = MCGS_WIKI if domain == "wikipedia" else MCGS_DEFAULT

        for scc in sccs:
            gt_nodes = [cid for cid in scc.clause_ids if is_ground_truth_node(cid, domain)]
            gt_names = [graph.clauses[n].title for n in gt_nodes if n in graph.clauses]

            print(f"\n{'─'*70}")
            print(f"  [{domain}] SCC {scc.id} ({scc.size} nodes)")
            print(f"  Ground truth defects: {gt_names or '(none defined)'}")
            print(f"{'─'*70}")

            for model_info in BATTLE_MODELS:
                model_name = model_info["name"]
                model_id = model_info["model_id"]

                llm_config = {
                    "provider": "openai",
                    "model": model_id,
                    "base_url": XHUB_BASE_URL,
                    "api_key_env": "XHUB_API_KEY",
                    "timeout": 300,
                }
                llm = OpenAIClient(llm_config)

                # ── Naive ──
                exp_idx += 1
                print(f"\n  [{exp_idx}/{total_exps}] {model_name} + Naive on {domain} {scc.size}n...")
                try:
                    naive_result = await run_naive(llm, model_name, domain, graph, scc)
                    top3 = naive_result["ranking"][:3]
                    print(f"    Top-3: {[(graph.clauses.get(c, Clause(id=c, title=c, content='')).title, f'{s:.2f}') for c, s in top3]}")
                    print(f"    Score spread: {naive_result['score_spread']:.3f}")
                    print(f"    Top-1 GT hit: {naive_result['top1_hit']}, Top-3 GT hit: {naive_result['top3_hit']}")
                    all_results.append(naive_result)
                except Exception as e:
                    print(f"    ERROR: {e}")
                    all_results.append({
                        "method": "naive", "model": model_name, "domain": domain,
                        "scc_id": scc.id, "scc_size": scc.size, "error": str(e),
                    })

                # ── SA-MCGS ──
                exp_idx += 1
                print(f"\n  [{exp_idx}/{total_exps}] {model_name} + SA-MCGS on {domain} {scc.size}n...")
                try:
                    mcgs_result = await run_sa_mcgs(llm, model_name, domain, graph, scc, mcgs_cfg)
                    top3 = mcgs_result["ranking"][:3]
                    print(f"    Top-3: {[(graph.clauses.get(c, Clause(id=c, title=c, content='')).title, f'{s:.3f}') for c, s in top3]}")
                    print(f"    Score spread: {mcgs_result['score_spread']:.3f}, OC: {mcgs_result['oc_count']}")
                    print(f"    Top-1 GT hit: {mcgs_result['top1_hit']}, Top-3 GT hit: {mcgs_result['top3_hit']}")
                    all_results.append(mcgs_result)
                except Exception as e:
                    print(f"    ERROR: {e}")
                    all_results.append({
                        "method": "sa-mcgs", "model": model_name, "domain": domain,
                        "scc_id": scc.id, "scc_size": scc.size, "error": str(e),
                    })

                await llm.close()

    # ── Save Results ──
    out_file = RESULTS_DIR / f"battle_v2_{int(time.time())}.json"
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n{'='*70}")
    print(f"  Results saved: {out_file}")

    # ── Summary Table ──
    print(f"\n{'='*70}")
    print(f"  BATTLE SUMMARY")
    print(f"{'='*70}")
    print(f"{'Model':<16} {'Domain':<12} {'SCC':<8} {'Method':<10} {'Spread':>8} {'Top1-GT':>8} {'Top3-GT':>8} {'OC':>4}")
    print("─" * 80)

    for r in all_results:
        if "error" in r:
            print(f"{r.get('model','?'):<16} {r.get('domain','?'):<12} {r.get('scc_size','?'):<8} {r.get('method','?'):<10} {'ERROR':>8}")
            continue
        oc = r.get("oc_count", "-") if r["method"] == "sa-mcgs" else "-"
        t1 = "Y" if r.get("top1_hit") else ("N" if r.get("top1_hit") is False else "-")
        t3 = "Y" if r.get("top3_hit") else ("N" if r.get("top3_hit") is False else "-")
        print(
            f"{r['model']:<16} {r['domain']:<12} {r['scc_size']:<8} {r['method']:<10} "
            f"{r['score_spread']:>8.3f} {t1:>8} {t3:>8} {str(oc):>4}"
        )

    # ── Detection Rate Summary ──
    print(f"\n{'='*70}")
    print(f"  DETECTION RATE (where ground truth exists)")
    print(f"{'='*70}")

    for model_info in BATTLE_MODELS:
        mn = model_info["name"]
        for method in ["naive", "sa-mcgs"]:
            relevant = [
                r for r in all_results
                if r.get("model") == mn and r.get("method") == method
                and r.get("top3_hit") is not None and "error" not in r
            ]
            if not relevant:
                continue
            hits = sum(1 for r in relevant if r["top3_hit"])
            total = len(relevant)
            rate = hits / total if total else 0
            print(f"  {mn:<16} {method:<10} Top-3 Detection: {hits}/{total} = {rate:.0%}")

    print(f"\n  Done! Total experiments: {len(all_results)}")


if __name__ == "__main__":
    asyncio.run(main())

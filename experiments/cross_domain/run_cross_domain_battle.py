"""Cross-domain Battle: Naive Prompting vs SA-MCGS

Runs face-to-face comparison using the SAME LLM models on the SAME SCCs:
  1. Naive Prompting — feed entire SCC to LLM in one shot (baseline paper approach)
  2. SA-MCGS — iterative structured search with windowed evaluation

Prompting policy:
  - Formal injected runs use a generic directed-graph consistency/risk prompt
    for both Naive and SA-MCGS.
  - Domain names and domain-specific error types are kept out of the task prompt
    so the methods remain general.

Ground truth for binary evaluation:
  - Debian: packages with known CVEs (ruby3.1 ~48 CVE, mono ~52 CVE)
  - Wikipedia: injected semantic contradictions (literature-backed)
  - SEC: circular ownership anomaly detection (expert labels TBD)

IMPORTANT: This script does NOT modify any existing results or configs.
Results are saved with "battle_v2_" or "battle_inject_" prefixes.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import gzip
import json
import math
import os
import pickle
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from src.models.clause import Clause, ClauseType
from src.models.graph import DependencyGraph, DependencyType, Edge, SCCInfo
from src.modules.tarjan import TarjanSCCDetector
from src.modules.alphago_mcgs import AlphaGoMCGS
from src.llm.openai_client import OpenAIClient

try:
    from run_cross_domain import (
        load_debian_graph,
        load_wikipedia_graph,
        load_sec_graph,
    )
except ImportError:
    from experiments.cross_domain.run_cross_domain import (
        load_debian_graph,
        load_wikipedia_graph,
        load_sec_graph,
    )

try:
    try:
        from inject_defect import (
            DEFAULT_MEMORY_CONFLICT_TEMPLATE,
            DEFAULT_MEMORY_CONFLICT_SEVERITY,
            DOMAIN_INJECT_TYPE,
            SUPPORTED_INJECT_PROFILES,
            SUPPORTED_MEMORY_CONFLICT_SEVERITIES,
            SUPPORTED_MEMORY_CONFLICT_TEMPLATES,
            get_injected_node,
            inject_defect,
        )
    except ImportError:
        from experiments.cross_domain.inject_defect import (
            DEFAULT_MEMORY_CONFLICT_TEMPLATE,
            DEFAULT_MEMORY_CONFLICT_SEVERITY,
            DOMAIN_INJECT_TYPE,
            SUPPORTED_INJECT_PROFILES,
            SUPPORTED_MEMORY_CONFLICT_SEVERITIES,
            SUPPORTED_MEMORY_CONFLICT_TEMPLATES,
            get_injected_node,
            inject_defect,
        )
    _INJECT_AVAILABLE = True
except ImportError:
    DEFAULT_MEMORY_CONFLICT_TEMPLATE = "handoff_invariant"
    DEFAULT_MEMORY_CONFLICT_SEVERITY = "standard"
    DOMAIN_INJECT_TYPE = {}
    SUPPORTED_INJECT_PROFILES = {"explicit"}
    SUPPORTED_MEMORY_CONFLICT_SEVERITIES = {"standard"}
    SUPPORTED_MEMORY_CONFLICT_TEMPLATES = {"handoff_invariant"}
    _INJECT_AVAILABLE = False

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
REPO_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_REPO_ROOT = Path(os.environ.get("MCGS_LAW_DATA_ROOT", "/Users/chenlong/WorkSpace/MCGS_Law"))
BGB_XML_PATH = REPO_ROOT / "data" / "bgb_raw" / "BJNR001950896.xml"
BGB_QUANTLAW_PATH = EXTERNAL_REPO_ROOT / "data" / "quantlaw" / "de" / "4_crossreference_graph" / "2019.gpickle.gz"
CUAD_DATA_DIR = REPO_ROOT / "data" / "cuad"
CUAD_EXTERNAL_DATA_DIR = EXTERNAL_REPO_ROOT / "data" / "cuad"
CUAD_FULLGRAPH_DIR = CUAD_EXTERNAL_DATA_DIR / "grpo_lex_replicated" / "fullgraphs"

XHUB_BASE_URL = "https://api3.xhub.chat/v1"

# ─── Models to test (all via XHub) ────────────────────────────────────
BATTLE_MODELS = [
    {"name": "gpt-4o",        "model_id": "gpt-4o"},
    {"name": "deepseek-v3",   "model_id": "deepseek-chat"},
    {"name": "claude-3-5-sonnet", "model_id": "claude-3-5-sonnet-20241022"},
    {"name": "qwen2.5-72b",       "model_id": "qwen2.5-72b-instruct"},
    {"name": "gemini-2.5-flash",  "model_id": "gemini-2.5-flash"},
    {"name": "gemini-2.5-pro",    "model_id": "gemini-2.5-pro"},
]

# ─── SA-MCGS configs per domain ──────────────────────────────────────
MCGS_DEFAULT = {
    "alphago_mcgs": {
        "budget": 30, "window_size": 4, "concurrency": 4,
        "ucb_exploration_weight": 1.414, "ucb_exploration_init": 2.5,
        "temperature": 0.4, "max_tokens": 2048, "tt_max_reuse": 3,
        "evidence": {
            "relation_first": True,
            "relation_prior_weight": 0.85,
            "relation_prior_decay": 0.35,
            "probe_fraction": 0.30,
            "probe_min_rollouts": 4,
            "probe_min_score": 1.0,
            "subgraph_max_ratio": 0.45,
            "subgraph_min_nodes": 4,
            "core_min_nodes": 2,
            "core_min_relative_score": 0.52,
            "core_stop_gap": 0.14,
            "core_min_score": 0.10,
            "pair_memory_max_ratio": 0.65,
            "pair_memory_min_score": 0.42,
            "pair_closure_min_score": 0.35,
            "critical_pair_ledger": True,
            "critical_pair_enter_threshold": 0.66,
            "critical_pair_exit_threshold": 0.48,
            "critical_pair_lock_support": 2,
            "critical_pair_revisit_fraction": 0.45,
            "critical_pair_frontier_max_pairs": 8,
            "critical_pair_core_min_score": 0.62,
        },
    },
    "detection": {"alpha": 0.1, "min_rollouts": 6},
}

MCGS_WIKI = {
    "alphago_mcgs": {**MCGS_DEFAULT["alphago_mcgs"], "budget": 60},
    "detection": {"alpha": 0.1, "min_rollouts": 6},
}

NAIVE_PROFILES = {"basic", "ranked", "direct_subgraph"}


def _model_json_max_tokens(model_name: str, requested: int) -> int:
    """Respect provider-specific JSON output caps while keeping defaults unchanged."""
    normalized = (model_name or "").lower()
    if "qwen" in normalized:
        return min(requested, 8192)
    return requested

MCGS_COMPRESSION_PROFILES = {
    "current": {},
    "conservative": {
        "subgraph_max_ratio": 0.40,
        "subgraph_min_nodes": 4,
        "core_min_relative_score": 0.56,
        "core_tail_relative_score": 0.32,
        "core_stop_gap": 0.12,
        "core_min_score": 0.12,
        "critical_pair_core_min_score": 0.68,
        "critical_pair_core_max_edge_ratio": 0.75,
    },
    "balanced": {
        "subgraph_max_ratio": 0.35,
        "subgraph_min_nodes": 3,
        "core_min_relative_score": 0.58,
        "core_tail_relative_score": 0.38,
        "core_stop_gap": 0.10,
        "core_min_score": 0.14,
        "critical_pair_core_min_score": 0.72,
        "critical_pair_core_max_edge_ratio": 0.50,
    },
    "aggressive": {
        "subgraph_max_ratio": 0.25,
        "subgraph_min_nodes": 2,
        "core_min_relative_score": 0.66,
        "core_tail_relative_score": 0.48,
        "core_stop_gap": 0.08,
        "core_min_score": 0.18,
        "critical_pair_core_min_score": 0.78,
        "critical_pair_core_max_edge_ratio": 0.30,
    },
}


def save_results(path: Path, results: list[dict]) -> None:
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)


def parse_domain_size_ranges(specs: list[str] | None) -> dict[str, tuple[int, int]]:
    """Parse CLI specs like 'cuad:12-26 wikipedia:34 bgb:11-25'."""
    ranges: dict[str, tuple[int, int]] = {}
    for spec in specs or []:
        if ":" not in spec:
            raise ValueError(f"Invalid --domain-size-ranges entry: {spec}")
        domain, raw_range = spec.split(":", 1)
        domain = domain.strip()
        raw_range = raw_range.strip()
        if "-" in raw_range:
            left, right = raw_range.split("-", 1)
            min_size, max_size = int(left), int(right)
        else:
            min_size = max_size = int(raw_range)
        if min_size <= 0 or max_size < min_size:
            raise ValueError(f"Invalid SCC size range for {domain}: {raw_range}")
        ranges[domain] = (min_size, max_size)
    return ranges


def runtime_mcgs_config(domain: str, args: argparse.Namespace) -> dict:
    cfg = copy.deepcopy(MCGS_WIKI if domain == "wikipedia" else MCGS_DEFAULT)
    evidence_cfg = cfg["alphago_mcgs"].setdefault("evidence", {})
    if getattr(args, "mcgs_concurrency", None):
        cfg["alphago_mcgs"]["concurrency"] = args.mcgs_concurrency
    if getattr(args, "mcgs_budget", None):
        cfg["alphago_mcgs"]["budget"] = args.mcgs_budget
    if domain == "wikipedia" and getattr(args, "wiki_mcgs_budget", None):
        cfg["alphago_mcgs"]["budget"] = args.wiki_mcgs_budget
    if getattr(args, "mcgs_trace", False):
        cfg["alphago_mcgs"]["trace"] = True
    evidence_mode = getattr(args, "mcgs_evidence_mode", "relation_first")
    if evidence_mode == "off":
        evidence_cfg["relation_first"] = False
        evidence_cfg["pair_memory_min_score"] = 999.0
        evidence_cfg["pair_closure_min_score"] = 999.0
        evidence_cfg["probe_fraction"] = 0.0
    elif evidence_mode == "pair_memory":
        evidence_cfg["relation_first"] = False
        evidence_cfg["probe_fraction"] = 0.0
    else:
        evidence_cfg["relation_first"] = True
    compression_profile = getattr(args, "mcgs_compression_profile", "current")
    evidence_cfg["compression_profile"] = compression_profile
    evidence_cfg.update(MCGS_COMPRESSION_PROFILES.get(compression_profile, {}))
    compression_overrides = {
        "subgraph_max_ratio": getattr(args, "mcgs_subgraph_max_ratio", None),
        "subgraph_min_nodes": getattr(args, "mcgs_subgraph_min_nodes", None),
        "core_min_relative_score": getattr(args, "mcgs_core_min_relative_score", None),
        "core_tail_relative_score": getattr(args, "mcgs_core_tail_relative_score", None),
        "core_stop_gap": getattr(args, "mcgs_core_stop_gap", None),
        "core_min_score": getattr(args, "mcgs_core_min_score", None),
        "critical_pair_core_min_score": getattr(args, "mcgs_critical_pair_core_min_score", None),
        "critical_pair_core_max_edge_ratio": getattr(args, "mcgs_critical_pair_core_max_edge_ratio", None),
        "critical_pair_core_max_edges": getattr(args, "mcgs_critical_pair_core_max_edges", None),
    }
    for key, value in compression_overrides.items():
        if value is not None:
            evidence_cfg[key] = value
    return cfg


def _legal_ref_numbers(text: str) -> list[str]:
    """Extract simple section-number references from statute text."""
    refs = re.findall(r"§{1,2}\s*(\d+[a-z]?)", text, flags=re.IGNORECASE)
    refs.extend(re.findall(r"section\s+(\d+(?:\.\d+)*)", text, flags=re.IGNORECASE))
    return list(dict.fromkeys(refs))


def load_bgb_graph() -> DependencyGraph:
    """Load a real BGB cross-reference graph from local XML.

    This is a dependency-free fallback for the QuantLaw graph builder: it uses
    original gesetze-im-internet XML text and a conservative section-reference
    regex, so formal runs still use real node content.
    """
    if BGB_QUANTLAW_PATH.exists():
        with gzip.open(BGB_QUANTLAW_PATH, "rb") as fh:
            graph_obj = pickle.load(fh)
        graph = _nx_to_dependency_graph(
            graph_obj,
            graph_id="bgb_quantlaw_2019",
            source="bgb_quantlaw_gpickle",
        )
        graph.metadata.update({
            "source": "bgb_quantlaw_gpickle",
            "graph_id": "bgb_quantlaw_2019",
            "data_path": str(BGB_QUANTLAW_PATH),
        })
        return graph

    if not BGB_XML_PATH.exists():
        raise FileNotFoundError(f"BGB XML not found: {BGB_XML_PATH}")

    section_re = re.compile(r"§\s*(\d+\w*)")
    root = ET.parse(BGB_XML_PATH).getroot()
    raw_sections: dict[str, dict[str, str]] = {}

    for norm in root.findall("norm"):
        meta = norm.find("metadaten")
        if meta is None:
            continue
        enbez = (meta.findtext("enbez") or "").strip()
        match = section_re.match(enbez)
        if not match:
            continue
        sec_num = match.group(1)
        text_elem = norm.find(".//textdaten/text")
        if text_elem is None:
            continue
        text = ET.tostring(text_elem, encoding="unicode", method="text").strip()
        if not text or text == "(weggefallen)":
            continue
        title = (meta.findtext("titel") or "").strip()
        raw_sections[sec_num] = {
            "title": title,
            "content": text,
            "doknr": norm.attrib.get("doknr", ""),
        }

    valid = set(raw_sections)
    clauses: dict[str, Clause] = {}
    edges: list[Edge] = []

    for sec_num, data in raw_sections.items():
        node_id = f"bgb_{sec_num}"
        clauses[node_id] = Clause(
            id=node_id,
            title=f"§{sec_num} {data['title']}".strip(),
            content=data["content"],
            clause_type=ClauseType.OTHER,
            metadata={
                "source": "bgb_xml_regex",
                "original_record": True,
                "section_number": sec_num,
                "doknr": data["doknr"],
            },
        )

    seen_edges: set[tuple[str, str]] = set()
    for sec_num, data in raw_sections.items():
        source = f"bgb_{sec_num}"
        for ref_num in _legal_ref_numbers(data["content"]):
            if ref_num not in valid or ref_num == sec_num:
                continue
            target = f"bgb_{ref_num}"
            key = (source, target)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append(Edge(
                source=source,
                target=target,
                dependency_type=DependencyType.REFERENCES,
                weight=0.8,
                reasoning="regex_section_reference",
            ))

    return DependencyGraph(
        clauses=clauses,
        edges=edges,
        metadata={"source": "bgb_xml_regex", "graph_id": "bgb_local_xml"},
    )


def _nx_to_dependency_graph(
    g_obj: Any,
    graph_id: str,
    prefix: str = "",
    source: str = "cuad_processed_gpickle",
) -> DependencyGraph:
    clauses: dict[str, Clause] = {}
    edges: list[Edge] = []
    for node, data in g_obj.nodes(data=True):
        raw_id = str(node)
        node_id = f"{prefix}{raw_id}"
        clauses[node_id] = Clause(
            id=node_id,
            title=str(data.get("heading") or data.get("title") or data.get("label") or raw_id),
            content=str(data.get("text") or data.get("content") or data.get("heading") or raw_id),
            clause_type=ClauseType.OTHER,
            metadata={
                "source": source,
                "original_record": True,
                "raw_node_id": raw_id,
                **{
                    str(k): str(v)
                    for k, v in data.items()
                    if k not in {"heading", "title", "label", "text", "content"}
                },
            },
        )
    for src, tgt, data in g_obj.edges(data=True):
        source = f"{prefix}{src}"
        target = f"{prefix}{tgt}"
        if source not in clauses or target not in clauses:
            continue
        edges.append(Edge(
            source=source,
            target=target,
            dependency_type=DependencyType.REFERENCES,
            weight=max(0.0, min(1.0, float(data.get("weight", 0.7)))),
            reasoning=str(data.get("reasoning") or data.get("edge_type") or "reference"),
        ))
    return DependencyGraph(
        clauses=clauses,
        edges=edges,
        metadata={"source": source, "graph_id": graph_id},
    )


def _safe_graph_prefix(graph_id: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", graph_id).strip("_")[:36]
    digest = hashlib.sha1(graph_id.encode("utf-8")).hexdigest()[:8]
    return f"{stem}_{digest}"


def _add_cuad_edge(
    edges: list[Edge],
    seen: set[tuple[str, str, str]],
    source: str,
    target: str,
    reasoning: str,
    weight: float,
) -> None:
    if source == target:
        return
    key = (source, target, reasoning)
    if key in seen:
        return
    seen.add(key)
    edges.append(Edge(
        source=source,
        target=target,
        dependency_type=DependencyType.REFERENCES,
        weight=max(0.0, min(1.0, weight)),
        reasoning=reasoning,
    ))


def _cuad_fullgraph_to_dependency_graph(json_path: Path) -> DependencyGraph:
    """Convert one CUAD fullgraph into a clause-only graph with full implicit edges."""
    with open(json_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    graph_id = json_path.stem.replace("_fullgraph", "")
    prefix = f"cuad_{_safe_graph_prefix(graph_id)}__"
    raw_nodes = data.get("nodes", [])
    raw_edges = data.get("edges", [])

    clause_raw_ids = {
        str(node.get("id", ""))
        for node in raw_nodes
        if node.get("node_type", node.get("type")) == "CLAUSE"
    }
    id_map = {raw_id: f"{prefix}{raw_id}" for raw_id in clause_raw_ids}

    clauses: dict[str, Clause] = {}
    for node in raw_nodes:
        raw_id = str(node.get("id", ""))
        node_type = node.get("node_type", node.get("type", "CLAUSE"))
        if raw_id not in clause_raw_ids:
            continue
        node_id = id_map[raw_id]
        title = node.get("title") or node.get("name") or node.get("label") or raw_id
        content = node.get("text") or node.get("content") or title
        clauses[node_id] = Clause(
            id=node_id,
            title=str(title),
            content=str(content),
            clause_type=ClauseType.OTHER,
            metadata={
                "source": "cuad_fullgraph_full_implicit",
                "original_record": True,
                "graph_id": graph_id,
                "raw_node_id": raw_id,
                "node_type": node_type,
            },
        )

    edges: list[Edge] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in raw_edges:
        src = str(edge.get("src", edge.get("source", "")))
        tgt = str(edge.get("tgt", edge.get("target", "")))
        edge_type = str(edge.get("type", edge.get("edge_type", "REFERENCES")))
        if edge_type in {"REFERENCES", "IS_PART_OF"} and src in id_map and tgt in id_map:
            _add_cuad_edge(edges, seen, id_map[src], id_map[tgt], edge_type, 1.0)

    term_to_definers: dict[str, set[str]] = defaultdict(set)
    term_to_users: dict[str, set[str]] = defaultdict(set)
    term_to_clauses: dict[str, set[str]] = defaultdict(set)
    full_term_to_clauses: dict[str, set[str]] = defaultdict(set)
    term_definers_canonical: dict[str, set[str]] = defaultdict(set)
    stop_terms = {
        "term:agreement", "term:party", "term:parties", "term:company",
        "term:effective date", "term:section", "term:affiliate",
        "term:affiliates", "term:license",
    }

    for edge in raw_edges:
        edge_type = str(edge.get("type", edge.get("edge_type", "")))
        src = str(edge.get("src", edge.get("source", "")))
        tgt = str(edge.get("tgt", edge.get("target", "")))
        if src not in clause_raw_ids or not tgt.startswith("term:"):
            continue
        canonical = tgt.lower().strip()
        if edge_type == "DEFINES":
            term_to_definers[tgt].add(src)
            term_definers_canonical[canonical].add(src)
        if edge_type == "USES":
            term_to_users[tgt].add(src)
        if edge_type in {"USES", "DEFINES"} and canonical not in stop_terms:
            term_to_clauses[canonical].add(src)
        if edge_type in {"USES", "DEFINES"}:
            full_term_to_clauses[canonical].add(src)

    for term, definers in term_to_definers.items():
        for user in term_to_users.get(term, set()):
            for definer in definers:
                if user in id_map and definer in id_map and user != definer:
                    _add_cuad_edge(
                        edges, seen, id_map[user], id_map[definer],
                        "CUAD_STRONG_IMPLICIT_TERM", 0.7,
                    )

    for term, linked_clauses in full_term_to_clauses.items():
        if len(linked_clauses) < 2 or len(linked_clauses) > 5:
            continue
        definers = term_definers_canonical.get(term, set())
        clause_list = sorted(linked_clauses)
        if definers:
            definer = sorted(definers)[0]
            for clause_id in clause_list:
                if clause_id == definer:
                    continue
                _add_cuad_edge(
                    edges, seen, id_map[clause_id], id_map[definer],
                    "CUAD_MEDIUM_IMPLICIT_TERM", 0.5,
                )
                if len(linked_clauses) == 2:
                    _add_cuad_edge(
                        edges, seen, id_map[definer], id_map[clause_id],
                        "CUAD_MEDIUM_IMPLICIT_TERM_BACKLINK", 0.4,
                    )
        else:
            anchor = clause_list[0]
            for clause_id in clause_list[1:]:
                _add_cuad_edge(
                    edges, seen, id_map[clause_id], id_map[anchor],
                    "CUAD_MEDIUM_IMPLICIT_TERM_ANCHOR", 0.4,
                )

    high_freq_threshold = max(3, len(clause_raw_ids) * 0.3)
    for term, linked_clauses in term_to_clauses.items():
        if len(linked_clauses) < 2 or len(linked_clauses) > high_freq_threshold:
            continue
        clause_list = sorted(linked_clauses)
        for i, left in enumerate(clause_list):
            for right in clause_list[i + 1:]:
                _add_cuad_edge(
                    edges, seen, id_map[left], id_map[right],
                    "CUAD_FULL_IMPLICIT_TERM_COUSAGE", 0.35,
                )
                _add_cuad_edge(
                    edges, seen, id_map[right], id_map[left],
                    "CUAD_FULL_IMPLICIT_TERM_COUSAGE", 0.35,
                )

    return DependencyGraph(
        clauses=clauses,
        edges=edges,
        metadata={
            "source": "cuad_fullgraph_full_implicit",
            "graph_id": graph_id,
            "data_path": str(json_path),
        },
    )


def _combine_graphs(graphs: list[tuple[str, DependencyGraph]]) -> DependencyGraph:
    clauses: dict[str, Clause] = {}
    edges: list[Edge] = []
    for graph_id, graph in graphs:
        safe_prefix = re.sub(r"[^A-Za-z0-9]+", "_", graph_id).strip("_")[:40]
        prefix = f"cuad_{safe_prefix}__"
        for cid, clause in graph.clauses.items():
            node_id = f"{prefix}{cid}"
            metadata = {
                **(clause.metadata or {}),
                "source": (clause.metadata or {}).get("source", "cuad"),
                "original_record": True,
                "graph_id": graph_id,
                "raw_node_id": cid,
            }
            copied = clause.model_copy(
                update={"id": node_id, "metadata": metadata},
                deep=True,
            )
            clauses[node_id] = copied
        for edge in graph.edges:
            source = f"{prefix}{edge.source}"
            target = f"{prefix}{edge.target}"
            if source in clauses and target in clauses:
                edges.append(edge.model_copy(update={"source": source, "target": target}))
    return DependencyGraph(
        clauses=clauses,
        edges=edges,
        metadata={"source": "cuad_combined", "graph_count": len(graphs)},
    )


def load_cuad_graph() -> DependencyGraph:
    """Load CUAD if local data exists; otherwise raise a clear skip error."""
    if CUAD_FULLGRAPH_DIR.exists():
        graphs = [
            (path.stem.replace("_fullgraph", ""), _cuad_fullgraph_to_dependency_graph(path))
            for path in sorted(CUAD_FULLGRAPH_DIR.glob("*_fullgraph.json"))
        ]
        if graphs:
            return _combine_graphs(graphs)

    if not CUAD_DATA_DIR.exists():
        raise FileNotFoundError(
            f"CUAD data directory not found: {CUAD_DATA_DIR}. "
            "Skipping CUAD; Debian/SEC/BGB can still run."
        )

    processed = CUAD_DATA_DIR / "processed" / "gpickle"
    if processed.exists():
        graphs = []
        for idx, path in enumerate(sorted(processed.glob("*.gpickle.gz"))[:50]):
            with gzip.open(path, "rb") as fh:
                graphs.append((path.stem.replace(".gpickle", ""), _nx_to_dependency_graph(
                    pickle.load(fh), path.stem.replace(".gpickle", "")
                )))
        if graphs:
            return _combine_graphs(graphs)

    try:
        from src.data.cuad_loader import CUADLoader
    except Exception as exc:
        raise RuntimeError(f"CUADLoader unavailable: {exc}") from exc

    loader = CUADLoader(str(CUAD_DATA_DIR))
    loaded = loader.load()
    if not loaded:
        raise FileNotFoundError(
            f"No CUAD graphs/text found under {CUAD_DATA_DIR}. "
            "Expected processed gpickle files or CUAD_v1 full_contract_txt."
        )
    return _combine_graphs(loaded[:50])

# ─── Ground Truth: known defective nodes per domain ──────────────────
# EXACT_MATCH_KEYS use exact equality (case-insensitive), not substring.
# Others use substring. This prevents "ruby" from matching "libruby".
GROUND_TRUTH = {
    "debian": {
        "ruby-sdbm": "structural propagation hub (Debian Bug #1055352): orphaned C ext creates version lock, makes entire SCC unresolvable",
        "ruby3.1": "~48 CVEs (NVD), primary CVE carrier in ruby SCC (Debian Bug #1055352)",
        "libmono-system-core4.0-cil": "mono .NET core runtime, base dependency for all libmono CVE propagation (Debian Bug #775878)",
    },
    "wikipedia": {},
    "sec_ex21": {
        "Baker Hughes EHO": "special-purpose entity causing circular ownership (4/4 model consensus across gpt-4o+deepseek-v3)",
    },
}

_GT_EXACT_MATCH = {
    "ruby-sdbm",
    "ruby3.1",
    "libmono-system-core4.0-cil",
}


def is_ground_truth_node(node_id: str, domain: str) -> bool:
    """Check if a node matches any ground truth defect pattern."""
    gt = GROUND_TRUTH.get(domain, {})
    node_lower = node_id.lower()
    for pattern in gt:
        p_lower = pattern.lower()
        if p_lower in _GT_EXACT_MATCH:
            if p_lower == node_lower:
                return True
        elif p_lower in node_lower:
            return True
    return False


def get_gt_evidence(node_id: str, domain: str) -> str:
    """Get the evidence string for a ground truth match."""
    gt = GROUND_TRUTH.get(domain, {})
    node_lower = node_id.lower()
    for pattern, evidence in gt.items():
        p_lower = pattern.lower()
        if p_lower in _GT_EXACT_MATCH and p_lower == node_lower:
            return evidence
        if p_lower not in _GT_EXACT_MATCH and p_lower in node_lower:
            return evidence
    return ""


# ═══════════════════════════════════════════════════════════════════════
#  SHARED RISK RUBRIC + METHOD ADAPTERS
# ═══════════════════════════════════════════════════════════════════════

SHARED_RISK_RUBRIC_VERSION = "shared_graph_risk_rubric_v1"


def build_shared_risk_rubric() -> str:
    """Canonical audit summary of the legacy domain-agnostic prompt wording.

    This text is intentionally not injected as an extra prompt block. The formal
    experiments already used the generic graph-risk wording below inside each
    method-specific prompt; keeping the runtime prompt unchanged preserves
    compatibility with completed runs.
    """
    return (
        "## Shared Risk Rubric\n"
        "You are analyzing a directed graph of interdependent records. Each node "
        "contains a record. Each directed edge indicates that one record depends "
        "on, constrains, references, modifies, or otherwise affects another "
        "record.\n\n"
        "A record or relation is risky if it is structurally inconsistent, "
        "mutually incompatible, underspecified, or high-impact under the visible "
        "graph context. For each visible record, assign a risk_score from 0.0 "
        "(no meaningful structural concern) to 1.0 (severe structural concern). "
        "Use only the visible node text and visible directed edges. Explain "
        "concrete conflicts using exact record IDs and evidence from the input. "
        "Do not assume domain-specific error types.\n"
    )


def shared_risk_rubric_hash() -> str:
    """Stable short hash for auditing the shared semantic risk criterion."""
    return hashlib.sha256(
        build_shared_risk_rubric().encode("utf-8")
    ).hexdigest()[:16]


def build_risk_rubric_audit(adapter_type: str, input_scope: str) -> dict[str, str]:
    return {
        "prompt_semantic_audit_version": SHARED_RISK_RUBRIC_VERSION,
        "prompt_semantic_audit_hash": shared_risk_rubric_hash(),
        "prompt_compatibility": "legacy_formal_prompt_no_extra_rubric_block",
        "prompt_adapter_type": adapter_type,
        "prompt_input_scope": input_scope,
    }


# ═══════════════════════════════════════════════════════════════════════
#  NAIVE PROMPTS — adapted from baseline paper methodologies
# ═══════════════════════════════════════════════════════════════════════

def _basic_naive_output_spec(scc_ids: list[str], id_label: str, issue_label: str) -> str:
    return (
        "Output STRICTLY as JSON:\n"
        '{"clause_evaluations": {\n'
        + ",\n".join(
            f'  "{cid}": {{"risk_score": 0.0, "reasoning": "brief explanation"}}'
            for cid in scc_ids
        )
        + f'\n}},\n"conflicts": [\n'
        f'  {{"clause_a": "{id_label}", "clause_b": "{id_label}", "description": "{issue_label}"}}\n'
        "]}"
    )


def _ranked_naive_output_spec(
    scc_ids: list[str],
    id_label: str = "record_id",
    issue_label: str = "specific concern",
) -> str:
    return (
        "## Ranking Requirements\n"
        "You must produce a complete global risk ordering, not just independent scores. "
        "The ranking is the primary output used for evaluation.\n\n"
        "First identify the major risk factors and assign their relative importance. "
        "The importance_weight values should sum to approximately 1.0. "
        "Infer the factors only from the record texts and directed edges; do not assume "
        "a pre-defined error type.\n\n"
        "Then rank every node from most risky to least risky. If several nodes have "
        "similar numeric scores, you must still break ties using evidence strength, "
        "specificity, graph position, and incident severity. Do not leave a large tied "
        "block as the final answer.\n\n"
        "Use the exact ID field from the node list for every clause_id. "
        "Do not use titles, natural-language names, or invented IDs.\n\n"
        "Output STRICTLY as JSON with these top-level fields:\n"
        "{\n"
        '  "risk_factor_distribution": [\n'
        '    {"factor": "factor name", "importance_weight": 0.0, "description": "what this factor captures"}\n'
        "  ],\n"
        '  "global_ranking": [\n'
        '    {"rank": 1, "clause_id": "node id from the cycle", "risk_score": 0.0, '
        '"risk_factors": ["factor name"], "reasoning": "why this node has this rank"}\n'
        "  ],\n"
        '  "clause_evaluations": {\n'
        '    "node id from the cycle": {"risk_score": 0.0, "reasoning": "brief explanation"}\n'
        "  },\n"
        '  "conflicts": [\n'
        f'    {{"clause_a": "{id_label}", "clause_b": "{id_label}", "description": "{issue_label}"}}\n'
        "  ]\n"
        "}\n\n"
        f"Rules: global_ranking MUST contain exactly {len(scc_ids)} entries, one for "
        "each listed node id, with ranks 1..N and no duplicate node ids. "
        "Do not copy the input order unless the evidence supports that ordering."
    )


def _direct_subgraph_naive_output_spec(
    scc_ids: list[str],
    id_label: str = "record_id",
    issue_label: str = "specific concern",
) -> str:
    return (
        "## Direct Risk-Subgraph Requirements\n"
        "You must directly output the smallest subgraph that you believe preserves "
        "the structurally inconsistent, mutually incompatible, or high-risk region. "
        "This is not a request to merely list the top-scoring records. Include a "
        "node only when its text or graph position is needed to explain, localize, "
        "or repair the risk. It is acceptable for the subgraph to contain one node "
        "when one record is clearly sufficient, or several nodes when the risk is "
        "distributed across records.\n\n"
        "Also produce a complete global risk ordering so the subgraph can be compared "
        "with rank-based baselines. If several nodes have similar scores, still break "
        "ties using evidence strength, specificity, graph position, and incident "
        "severity.\n\n"
        "Use exact node IDs from the input. Do not use titles, natural-language names, "
        "or invented IDs.\n\n"
        "Output STRICTLY as JSON with these top-level fields:\n"
        "{\n"
        '  "risk_factor_distribution": [\n'
        '    {"factor": "factor name", "importance_weight": 0.0, "description": "what this factor captures"}\n'
        "  ],\n"
        '  "global_ranking": [\n'
        '    {"rank": 1, "clause_id": "node id from the cycle", "risk_score": 0.0, '
        '"risk_factors": ["factor name"], "reasoning": "why this node has this rank"}\n'
        "  ],\n"
        '  "risk_subgraph_nodes": [\n'
        '    "node id from the cycle"\n'
        "  ],\n"
        '  "risk_subgraph_rationale": "why this exact set is sufficient and minimal",\n'
        '  "risk_subgraph_edges": [\n'
        '    {"source": "node id from the cycle", "target": "node id from the cycle", '
        '"reason": "why this edge matters"}\n'
        "  ],\n"
        '  "clause_evaluations": {\n'
        '    "node id from the cycle": {"risk_score": 0.0, "reasoning": "brief explanation"}\n'
        "  },\n"
        '  "conflicts": [\n'
        f'    {{"clause_a": "{id_label}", "clause_b": "{id_label}", "description": "{issue_label}"}}\n'
        "  ]\n"
        "}\n\n"
        f"Rules: global_ranking MUST contain exactly {len(scc_ids)} entries, one for "
        "each listed node id, with ranks 1..N and no duplicate node ids. "
        "risk_subgraph_nodes MUST contain only exact listed node ids, no duplicates, "
        "and should be smaller than the full graph unless the whole graph is truly "
        "needed. Do not copy the input order unless the evidence supports that ordering."
    )


def _format_record_section(
    clauses: dict[str, Clause],
    scc_ids: list[str],
) -> str:
    return "\n".join(
        f"- ID: {cid}\n  Title: {clauses[cid].title}\n  Content: {clauses[cid].content}"
        for cid in scc_ids if cid in clauses
    )


def _format_edge_section(
    clauses: dict[str, Clause],
    edges: list[Edge],
    scc_ids: list[str],
) -> str:
    scc_set = set(scc_ids)
    all_edges = [e for e in edges if e.source in scc_set and e.target in scc_set]
    return "\n".join(
        f"- {e.source} ({clauses.get(e.source, Clause(id=e.source, title=e.source, content='')).title}) "
        f"-> {e.target} ({clauses.get(e.target, Clause(id=e.target, title=e.target, content='')).title}); "
        f"relation={e.dependency_type.value}"
        for e in all_edges
    ) or "No directed edges listed."


def _build_generic_naive_prompt(
    clauses: dict[str, Clause],
    edges: list[Edge],
    scc_ids: list[str],
    ranked: bool = False,
    direct_subgraph: bool = False,
) -> str:
    record_section = _format_record_section(clauses, scc_ids)
    edge_section = _format_edge_section(clauses, edges, scc_ids)
    return (
        "You are analyzing a directed graph of interdependent records.\n\n"
        "Each node contains a record. Each directed edge indicates that one record "
        "depends on, constrains, references, modifies, or otherwise affects another "
        "record. Your task is to reason over both the record text and the graph "
        "structure.\n\n"
        f"## Records ({len(scc_ids)} nodes)\n{record_section}\n\n"
        f"## Directed Edges\n{edge_section}\n\n"
        "## Task\n"
        "Identify structurally inconsistent, mutually incompatible, underspecified, "
        "or high-impact records. For each record, assign a risk_score from 0.0 "
        "(no meaningful structural concern) to 1.0 (severe structural concern). "
        "Explain any concrete conflict using record IDs and evidence from the input.\n\n"
        + (
            _direct_subgraph_naive_output_spec(scc_ids)
            if direct_subgraph else
            _ranked_naive_output_spec(scc_ids)
            if ranked else
            _basic_naive_output_spec(scc_ids, "record_id", "specific concern")
        )
    )


def build_naive_prompt_debian(
    clauses: dict[str, Clause],
    edges: list[Edge],
    scc_ids: list[str],
    ranked: bool = False,
    direct_subgraph: bool = False,
) -> str:
    """Naive one-shot prompt for Debian using the generic graph-risk task."""
    return _build_generic_naive_prompt(
        clauses, edges, scc_ids, ranked=ranked, direct_subgraph=direct_subgraph
    )


def build_naive_prompt_wikipedia(
    clauses: dict[str, Clause],
    edges: list[Edge],
    scc_ids: list[str],
    ranked: bool = False,
    direct_subgraph: bool = False,
) -> str:
    """Naive one-shot prompt for Wikipedia using the generic graph-risk task."""
    return _build_generic_naive_prompt(
        clauses, edges, scc_ids, ranked=ranked, direct_subgraph=direct_subgraph
    )


def build_naive_prompt_sec(
    clauses: dict[str, Clause],
    edges: list[Edge],
    scc_ids: list[str],
    ranked: bool = False,
    direct_subgraph: bool = False,
) -> str:
    """Naive one-shot prompt for SEC using the generic graph-risk task."""
    return _build_generic_naive_prompt(
        clauses, edges, scc_ids, ranked=ranked, direct_subgraph=direct_subgraph
    )


# ═══════════════════════════════════════════════════════════════════════
#  SA-MCGS PROMPTS — windowed versions (reused from run_cross_domain.py)
# ═══════════════════════════════════════════════════════════════════════

def _mcgs_generic_prompt(self, window: list[str]) -> str:
    clauses_fmt = "\n\n".join(
        f"### ID: {cid}\nTitle: {self._clauses[cid].title}\nContent: {self._clauses[cid].content}"
        for cid in window if cid in self._clauses
    )
    window_set = set(window)
    relevant_edges = [
        e for e in self._internal_edges
        if e.source in window_set and e.target in window_set
    ]
    deps_fmt = "\n".join(
        f"- {e.source} -> {e.target}; relation={e.dependency_type.value}"
        for e in relevant_edges
    ) or "No directed edges between these records."

    return (
        "You are analyzing a subset of records from a directed graph of "
        "interdependent records.\n\n"
        "Each node contains a record. Each directed edge indicates that one record "
        "depends on, constrains, references, modifies, or otherwise affects another "
        "record. Reason over both the record text and the local graph structure.\n\n"
        f"## Records Under Analysis ({len(window)} of {len(self._scc_ids)} total)\n"
        f"{clauses_fmt}\n\n"
        f"## Directed Edges Within This Subset\n{deps_fmt}\n\n"
        "## Task\n"
        "Identify structurally inconsistent, mutually incompatible, underspecified, "
        "or high-impact records in this subset. For each record, assess its "
        "risk_score (0.0=no meaningful structural concern, 1.0=severe structural "
        "concern) in context of the other records. Identify concrete conflicts "
        "between record pairs when evidence supports them. If a pair forms a severe "
        "same-path incompatibility with no obvious fallback, list it under "
        "critical_pairs as well. Do not invent a critical pair unless both endpoints "
        "and the relation are visible in this window.\n\n"
        "Output STRICTLY as JSON:\n"
        "{\n"
        '"clause_evaluations": {\n'
        + ",\n".join(
            f'  "{cid}": {{"risk_score": 0.0, "reasoning": "brief"}}'
            for cid in window
        )
        + '\n},\n'
        '"local_risk_subgraph_nodes": [\n'
        '  "record_id"\n'
        "],\n"
        '"local_conflict_edges": [\n'
        '  {"source": "record_id", "target": "record_id", "reason": "why this local relation matters"}\n'
        "],\n"
        '"critical_pairs": [\n'
        '  {"source": "record_id", "target": "record_id", "reason": "same-path severe incompatibility", '
        '"same_path_score": 0.0, "mutual_incompatibility_score": 0.0, '
        '"severity_score": 0.0, "no_fallback": false}\n'
        "],\n"
        '"repair_entry_nodes": [\n'
        '  "record_id"\n'
        "],\n"
        '"conflicts": [\n'
        '  {"clause_a": "record_id", "clause_b": "record_id", "description": "..."}\n'
        "]\n"
        "}\n\n"
        "Rules: local_risk_subgraph_nodes should be the smallest node set inside "
        "this window that preserves the local risk or inconsistency. "
        "repair_entry_nodes are records a reviewer could inspect or edit first. "
        "Use only exact IDs from this window."
    )


def _mcgs_debian_prompt(self, window: list[str]) -> str:
    return _mcgs_generic_prompt(self, window)


def _mcgs_wikipedia_prompt(self, window: list[str]) -> str:
    return _mcgs_generic_prompt(self, window)


def _mcgs_sec_prompt(self, window: list[str]) -> str:
    return _mcgs_generic_prompt(self, window)


DOMAIN_MCGS_PROMPTS = {
    "debian": _mcgs_debian_prompt,
    "wikipedia": _mcgs_wikipedia_prompt,
    "sec_ex21": _mcgs_sec_prompt,
    "bgb": _mcgs_generic_prompt,
    "cuad": _mcgs_generic_prompt,
}

DOMAIN_NAIVE_PROMPTS = {
    "debian": build_naive_prompt_debian,
    "wikipedia": build_naive_prompt_wikipedia,
    "sec_ex21": build_naive_prompt_sec,
    "bgb": _build_generic_naive_prompt,
    "cuad": _build_generic_naive_prompt,
}


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _score_tie_diagnostics(scores: dict[str, float]) -> dict:
    groups: dict[float, list[str]] = {}
    for cid, score in scores.items():
        groups.setdefault(score, []).append(cid)
    tied_groups = [
        {"score": score, "count": len(ids), "nodes": ids}
        for score, ids in sorted(groups.items(), key=lambda item: (-len(item[1]), -item[0]))
        if len(ids) > 1
    ]
    return {
        "distinct_score_count": len(groups),
        "largest_tie_count": max((len(ids) for ids in groups.values()), default=0),
        "tied_score_groups": tied_groups,
    }


def _extract_ranked_node_id(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return None
    for key in ("clause_id", "node_id", "id", "package_id", "category_id", "company_id"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _normalize_node_alias(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _build_node_alias_map(
    clauses: dict[str, Clause],
    scc_ids: list[str],
) -> dict[str, str]:
    """Map unambiguous IDs/titles back to canonical SCC IDs."""
    alias_sets: dict[str, set[str]] = {}
    for cid in scc_ids:
        candidates = {cid, cid.replace("_", " ")}
        clause = clauses.get(cid)
        if clause:
            candidates.add(clause.title)
        for candidate in candidates:
            if candidate:
                alias_sets.setdefault(_normalize_node_alias(candidate), set()).add(cid)
    return {
        alias: next(iter(ids))
        for alias, ids in alias_sets.items()
        if len(ids) == 1
    }


def _explicit_naive_ranking(
    parsed: dict,
    scc_ids: list[str],
    scores: dict[str, float],
    alias_map: dict[str, str] | None = None,
) -> tuple[list[tuple[str, float]], dict]:
    """Use the model's explicit global ranking when available.

    Score-only sorting is kept as a fallback, but it is order-sensitive when many
    nodes tie. The ranked Naive baseline asks the model to break those ties itself.
    """
    raw_ranking = parsed.get("global_ranking", [])
    if not isinstance(raw_ranking, list) or not raw_ranking:
        return sorted(scores.items(), key=lambda x: -x[1]), {
            "ranking_source": "score_sort",
            "ranking_complete": False,
            "ranking_missing": list(scc_ids),
            "ranking_duplicates": [],
            "ranking_invalid": [],
            "ranking_alias_resolutions": [],
        }

    scc_set = set(scc_ids)
    seen: set[str] = set()
    duplicates: list[str] = []
    invalid: list[str] = []
    alias_resolutions: list[dict[str, str]] = []
    entries: list[tuple[int, int, str, float]] = []

    for position, item in enumerate(raw_ranking):
        raw_cid = _extract_ranked_node_id(item)
        cid = raw_cid
        if cid not in scc_set and alias_map and cid:
            resolved = alias_map.get(_normalize_node_alias(cid))
            if resolved:
                cid = resolved
                if raw_cid != resolved:
                    alias_resolutions.append({"raw": raw_cid, "canonical": resolved})
        if not cid or cid not in scc_set:
            if raw_cid:
                invalid.append(raw_cid)
            continue
        if cid in seen:
            duplicates.append(cid)
            continue
        seen.add(cid)
        if isinstance(item, dict):
            rank = int(_coerce_float(item.get("rank"), position + 1))
            score = _coerce_float(item.get("risk_score", item.get("score")), scores.get(cid, 0.0))
        else:
            rank = position + 1
            score = scores.get(cid, 0.0)
        entries.append((rank, position, cid, score))

    entries.sort(key=lambda x: (x[0], x[1]))
    ordered = [(cid, score) for _, _, cid, score in entries]

    missing = [cid for cid in scc_ids if cid not in seen]
    if missing:
        missing_ranked = sorted(
            ((cid, scores.get(cid, 0.0)) for cid in missing),
            key=lambda item: (-item[1], scc_ids.index(item[0])),
        )
        ordered.extend(missing_ranked)

    return ordered, {
        "ranking_source": "global_ranking",
        "ranking_complete": not missing and not duplicates and not invalid,
        "ranking_missing": missing,
        "ranking_duplicates": duplicates,
        "ranking_invalid": invalid,
        "ranking_alias_resolutions": alias_resolutions,
    }


def _normalize_direct_subgraph_nodes(
    parsed: dict,
    scc_ids: list[str],
    alias_map: dict[str, str] | None = None,
) -> tuple[list[str], dict]:
    """Normalize a one-shot LLM's declared risk-subgraph node list."""
    raw_nodes = parsed.get("risk_subgraph_nodes")
    raw_subgraph = parsed.get("risk_subgraph")
    if raw_nodes is None and isinstance(raw_subgraph, dict):
        raw_nodes = (
            raw_subgraph.get("nodes")
            or raw_subgraph.get("node_ids")
            or raw_subgraph.get("clause_ids")
        )
    elif raw_nodes is None and isinstance(raw_subgraph, list):
        raw_nodes = raw_subgraph

    if raw_nodes is None:
        raw_nodes = []
    if isinstance(raw_nodes, str):
        raw_nodes = [piece.strip() for piece in re.split(r"[,;\n]+", raw_nodes) if piece.strip()]
    if not isinstance(raw_nodes, list):
        raw_nodes = []

    scc_set = set(scc_ids)
    nodes: list[str] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    invalid: list[str] = []
    alias_resolutions: list[dict[str, str]] = []

    for item in raw_nodes:
        raw_cid = _extract_ranked_node_id(item)
        cid = raw_cid
        if cid not in scc_set and alias_map and cid:
            resolved = alias_map.get(_normalize_node_alias(cid))
            if resolved:
                cid = resolved
                if raw_cid != resolved:
                    alias_resolutions.append({"raw": raw_cid, "canonical": resolved})
        if not cid or cid not in scc_set:
            if raw_cid:
                invalid.append(raw_cid)
            continue
        if cid in seen:
            duplicates.append(cid)
            continue
        seen.add(cid)
        nodes.append(cid)

    return nodes, {
        "direct_subgraph_raw": raw_nodes,
        "direct_subgraph_invalid": invalid,
        "direct_subgraph_duplicates": duplicates,
        "direct_subgraph_alias_resolutions": alias_resolutions,
        "direct_subgraph_complete_parse": bool(nodes) and not invalid and not duplicates,
    }


def _word_ratio_before(text: str, char_idx: int) -> float | None:
    if char_idx < 0:
        return None
    total = len(re.findall(r"\S+", text))
    if total == 0:
        return None
    before = len(re.findall(r"\S+", text[:char_idx]))
    return before / total


def build_prompt_audit(
    prompt: str,
    clauses: dict[str, Clause],
    injected_id: str | None,
) -> dict:
    """Record prompt-level leakage/parity diagnostics for injected experiments."""
    if not injected_id or injected_id not in clauses:
        return {}

    clause = clauses[injected_id]
    title = clause.title or injected_id
    content = clause.content or ""

    title_positions = [m.start() for m in re.finditer(re.escape(title), prompt)]
    id_positions = [m.start() for m in re.finditer(re.escape(injected_id), prompt)]

    content_idx = prompt.find(content) if content else -1
    if content_idx < 0 and content:
        probe = content[: min(len(content), 120)]
        content_idx = prompt.find(probe)

    return {
        "prompt_word_count": len(re.findall(r"\S+", prompt)),
        "injected_title_occurrences_in_prompt": len(title_positions),
        "injected_id_occurrences_in_prompt": len(id_positions),
        "injected_title_first_word_ratio": (
            _word_ratio_before(prompt, title_positions[0]) if title_positions else None
        ),
        "injected_content_in_prompt": content_idx >= 0,
        "injected_content_first_word_ratio": _word_ratio_before(prompt, content_idx),
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
    naive_profile: str = "ranked",
    injected_id: str | None = None,
) -> dict:
    """Run Naive one-shot prompting on a single SCC."""
    t0 = time.time()

    prompt_fn = DOMAIN_NAIVE_PROMPTS[domain]
    scc_set = set(scc.clause_ids)
    scc_edges = [e for e in graph.edges if e.source in scc_set and e.target in scc_set]

    ranked_naive = naive_profile in {"ranked", "direct_subgraph"}
    direct_subgraph_naive = naive_profile == "direct_subgraph"
    prompt = prompt_fn(
        graph.clauses,
        scc_edges,
        scc.clause_ids,
        ranked=ranked_naive,
        direct_subgraph=direct_subgraph_naive,
    )
    prompt_audit = build_prompt_audit(prompt, graph.clauses, injected_id)

    parsed = await llm.call_json(
        prompt,
        temperature=0.0,
        max_tokens=_model_json_max_tokens(
            model_name,
            12000 if direct_subgraph_naive else (8192 if ranked_naive else 4096),
        ),
        retries=4 if "gemini" in (model_name or "").lower() else 2,
    )
    if not parsed:
        raise ValueError("LLM returned no parseable JSON")

    elapsed = time.time() - t0

    evals = parsed.get("clause_evaluations", {})
    conflicts = parsed.get("conflicts", [])

    scores = {}
    reasonings = {}
    for cid in scc.clause_ids:
        info = evals.get(cid, {})
        scores[cid] = _coerce_float(info.get("risk_score"), 0.0)
        reasonings[cid] = info.get("reasoning", "")

    alias_map = _build_node_alias_map(graph.clauses, scc.clause_ids)
    ranking, ranking_diagnostics = (
        _explicit_naive_ranking(
            parsed,
            scc.clause_ids,
            scores,
            alias_map=alias_map,
        )
        if ranked_naive else
        (
            sorted(scores.items(), key=lambda x: -x[1]),
            {
                "ranking_source": "score_sort",
                "ranking_complete": False,
                "ranking_missing": [],
                "ranking_duplicates": [],
                "ranking_invalid": [],
                "ranking_alias_resolutions": [],
            },
        )
    )
    if ranked_naive and (
        ranking_diagnostics.get("ranking_source") != "global_ranking"
        or not ranking_diagnostics.get("ranking_complete")
    ):
        raise ValueError(
            "Ranked Naive returned an incomplete or invalid global_ranking: "
            f"missing={ranking_diagnostics.get('ranking_missing')}, "
            f"duplicates={ranking_diagnostics.get('ranking_duplicates')}, "
            f"invalid={ranking_diagnostics.get('ranking_invalid')}"
        )
    direct_subgraph_nodes: list[str] = []
    direct_subgraph_diagnostics: dict = {}
    direct_subgraph_rationale = None
    direct_subgraph_edges = []
    if direct_subgraph_naive:
        direct_subgraph_nodes, direct_subgraph_diagnostics = _normalize_direct_subgraph_nodes(
            parsed,
            scc.clause_ids,
            alias_map=alias_map,
        )
        raw_subgraph = parsed.get("risk_subgraph")
        if isinstance(raw_subgraph, dict):
            direct_subgraph_rationale = (
                parsed.get("risk_subgraph_rationale")
                or raw_subgraph.get("rationale")
                or raw_subgraph.get("reasoning")
            )
            direct_subgraph_edges = (
                parsed.get("risk_subgraph_edges")
                or raw_subgraph.get("edges")
                or []
            )
        else:
            direct_subgraph_rationale = parsed.get("risk_subgraph_rationale")
            direct_subgraph_edges = parsed.get("risk_subgraph_edges", [])
        if not direct_subgraph_nodes:
            raise ValueError(
                "Direct-subgraph Naive returned no valid risk_subgraph_nodes: "
                f"invalid={direct_subgraph_diagnostics.get('direct_subgraph_invalid')}"
            )
    score_vals = list(scores.values())
    s_spread = max(score_vals) - min(score_vals) if score_vals else 0
    ranking_score_vals = [score for _, score in ranking]
    ranking_spread = (
        max(ranking_score_vals) - min(ranking_score_vals)
        if ranking_score_vals else 0
    )
    tie_diagnostics = _score_tie_diagnostics(scores)
    risk_factor_distribution = parsed.get("risk_factor_distribution", [])
    risk_factor_weight_sum = sum(
        _coerce_float(item.get("importance_weight"), 0.0)
        for item in risk_factor_distribution
        if isinstance(item, dict)
    )

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
        "method_source": f"adapted from baseline paper ({domain}); naive_profile={naive_profile}",
        "naive_profile": naive_profile,
        **build_risk_rubric_audit(
            adapter_type=(
                "whole_scc_direct_subgraph"
                if direct_subgraph_naive else
                "whole_scc_global_ranking"
                if ranked_naive else
                "whole_scc_basic_scoring"
            ),
            input_scope="full_scc",
        ),
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
        "global_ranking_raw": parsed.get("global_ranking", []),
        "risk_factor_distribution": risk_factor_distribution,
        "risk_factor_weight_sum": risk_factor_weight_sum,
        "direct_risk_subgraph_nodes": direct_subgraph_nodes,
        "direct_risk_subgraph_size": len(direct_subgraph_nodes),
        "direct_compression_ratio": (
            1 - (len(direct_subgraph_nodes) / max(1, scc.size))
            if direct_subgraph_naive else None
        ),
        "direct_subgraph_type": (
            "llm_declared_minimal_risk_subgraph" if direct_subgraph_naive else None
        ),
        "direct_subgraph_policy": (
            "LLM directly declares risk_subgraph_nodes from whole-SCC one-shot prompt"
            if direct_subgraph_naive else None
        ),
        "direct_risk_subgraph_rationale": direct_subgraph_rationale,
        "direct_risk_subgraph_edges": direct_subgraph_edges,
        **direct_subgraph_diagnostics,
        **ranking_diagnostics,
        **tie_diagnostics,
        "conflicts": conflicts,
        "score_spread": s_spread,
        "ranking_score_spread": ranking_spread,
        "score_mean": sum(score_vals) / max(1, len(score_vals)),
        "score_max": max(score_vals) if score_vals else 0,
        "node_names": node_names,
        "ground_truth_nodes": gt_nodes,
        "gt_evidence": {n: get_gt_evidence(n, domain) for n in gt_nodes},
        "top1_hit": top1_hit,
        "top3_hit": top3_hit,
        **prompt_audit,
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
        **build_risk_rubric_audit(
            adapter_type="local_window_evidence_for_search",
            input_scope="local_scc_window",
        ),
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
        "local_risk_subgraph_counts": scc_result.get("local_risk_subgraph_counts", {}),
        "repair_entry_counts": scc_result.get("repair_entry_counts", {}),
        "local_conflict_edges": scc_result.get("local_conflict_edges", []),
        "local_subgraph_signal": scc_result.get("local_subgraph_signal", {}),
        "local_subgraph_candidate_nodes": scc_result.get("local_subgraph_candidate_nodes", []),
        "ranking_by_local_subgraph": scc_result.get("ranking_by_local_subgraph", []),
        "amaf_node_evidence": scc_result.get("amaf_node_evidence", {}),
        "amaf_edge_evidence": scc_result.get("amaf_edge_evidence", {}),
        "path_fragment_evidence": scc_result.get("path_fragment_evidence", {}),
        "relation_node_raw_scores": scc_result.get("relation_node_raw_scores", {}),
        "relation_probe_history": scc_result.get("relation_probe_history", []),
        "relation_probe_count": scc_result.get("relation_probe_count", 0),
        "selection_events": scc_result.get("selection_events", []),
        "relation_first_enabled": scc_result.get("relation_first_enabled", False),
        "relation_evidence_policy": scc_result.get("relation_evidence_policy"),
        "evidence_node_scores": scc_result.get("evidence_node_scores", {}),
        "evidence_component_names": scc_result.get("evidence_component_names", []),
        "evidence_component_policy": scc_result.get("evidence_component_policy"),
        "ranking_by_evidence": scc_result.get("ranking_by_evidence", []),
        "conflict_probability_matrix": scc_result.get("conflict_probability_matrix", []),
        "evidence_pair_memory_nodes": scc_result.get("evidence_pair_memory_nodes", []),
        "evidence_pair_memory_edges": scc_result.get("evidence_pair_memory_edges", []),
        "critical_pair_ledger_rows": scc_result.get("critical_pair_ledger_rows", []),
        "critical_pair_locked_edges": scc_result.get("critical_pair_locked_edges", []),
        "critical_pair_candidate_edges": scc_result.get("critical_pair_candidate_edges", []),
        "critical_pair_revisit_history": scc_result.get("critical_pair_revisit_history", []),
        "critical_pair_policy": scc_result.get("critical_pair_policy"),
        "mcgs_compression_profile": (
            mcgs_config.get("alphago_mcgs", {})
            .get("evidence", {})
            .get("compression_profile", "current")
        ),
        "mcgs_compression_params": {
            key: value
            for key, value in (
                mcgs_config.get("alphago_mcgs", {})
                .get("evidence", {})
                .items()
            )
            if key.startswith("core_")
            or key.startswith("subgraph_")
            or key.startswith("critical_pair_core_")
        },
        "evidence_risk_subgraph_nodes": scc_result.get("evidence_risk_subgraph_nodes", []),
        "evidence_risk_subgraph_size": scc_result.get("evidence_risk_subgraph_size", 0),
        "evidence_compression_ratio": scc_result.get("evidence_compression_ratio", 0),
        "context_evidence_risk_subgraph_nodes": scc_result.get("context_evidence_risk_subgraph_nodes", []),
        "context_evidence_risk_subgraph_size": scc_result.get("context_evidence_risk_subgraph_size", 0),
        "context_evidence_compression_ratio": scc_result.get("context_evidence_compression_ratio", 0),
        "dynamic_core_priority_rows": scc_result.get("dynamic_core_priority_rows", []),
        "dynamic_core_hit_cap": scc_result.get("dynamic_core_hit_cap", False),
        "evidence_subgraph_policy": scc_result.get("evidence_subgraph_policy"),
        "evidence_subgraph_cap": scc_result.get("evidence_subgraph_cap"),
        "trace_events": scc_result.get("trace_events", []),
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
    gt_patterns: Optional[list[str]] = None,
) -> list[SCCInfo]:
    """Select representative SCCs: prefer one small (5-6) and one larger (7+).

    If gt_patterns is provided, prioritize SCCs containing nodes matching any
    pattern (case-insensitive substring match). Falls back to size-based
    selection when not enough GT-containing SCCs exist.
    """
    detector = TarjanSCCDetector()
    graph = detector.detect(graph)

    candidates = sorted(
        [s for s in graph.sccs if min_size <= s.size <= max_size],
        key=lambda s: s.size,
    )

    def has_gt(scc: SCCInfo) -> bool:
        if not gt_patterns:
            return False
        pats = [p.lower() for p in gt_patterns]
        return any(any(p in cid.lower() for p in pats) for cid in scc.clause_ids)

    if gt_patterns:
        gt_candidates = [s for s in candidates if has_gt(s)]
        non_gt = [s for s in candidates if not has_gt(s)]
        candidates = gt_candidates + non_gt

    if len(candidates) <= max_count:
        return candidates

    small = [s for s in candidates if s.size <= 6]
    large = [s for s in candidates if s.size >= 7]

    selected = []
    if small:
        selected.append(small[0])
    if large:
        selected.append(large[0] if gt_patterns else large[-1])

    while len(selected) < max_count and candidates:
        for c in candidates:
            if c not in selected:
                selected.append(c)
                break
        else:
            break

    return sorted(selected, key=lambda s: s.size)


def _synthetic_content(domain: str, node_id: str, idx: int, size: int) -> str:
    """Plain baseline text for synthetic long-cycle nodes before injection."""
    if domain == "debian":
        return (
            f"Debian package: {node_id}. Synthetic long-cycle package {idx + 1}/{size}. "
            "It participates in a controlled dependency stress test with ordinary "
            "release notes, rebuild constraints, and medium-priority maintenance noise."
        )
    if domain == "wikipedia":
        return (
            f"Wikipedia category: {node_id}. Synthetic category {idx + 1}/{size}. "
            "It represents a controlled taxonomy cycle used to test whether a model "
            "can retain a problematic hierarchy note across a long category chain."
        )
    return (
        f"SEC Exhibit 21 entity: {node_id}. Synthetic subsidiary {idx + 1}/{size}. "
        "It belongs to a controlled ownership cycle with routine consolidation notes "
        "and medium-priority audit follow-up items."
    )


def add_synthetic_cycle(graph: DependencyGraph, domain: str, size: int) -> SCCInfo:
    """Append a controlled synthetic cycle to a domain graph and return its SCCInfo."""
    prefix = f"synthetic_{domain}_{size}"
    node_ids = [f"{prefix}_node_{i + 1:02d}" for i in range(size)]
    for idx, node_id in enumerate(node_ids):
        graph.clauses[node_id] = Clause(
            id=node_id,
            title=node_id.replace("_", " "),
            content=_synthetic_content(domain, node_id, idx, size),
            clause_type=ClauseType.OTHER,
            metadata={
                "source": "synthetic_diagnostic_cycle",
                "original_record": False,
                "diagnostic_only": True,
            },
        )

    internal_edges = []
    for idx, src in enumerate(node_ids):
        dst = node_ids[(idx + 1) % size]
        edge = Edge(
            source=src,
            target=dst,
            dependency_type=DependencyType.REFERENCES,
            weight=0.8,
            reasoning=f"synthetic long-cycle edge {src} -> {dst}",
        )
        graph.edges.append(edge)
        internal_edges.append(edge)

    return SCCInfo(id=prefix, clause_ids=node_ids, internal_edges=internal_edges, size=size)


def assert_original_scc_content(graph: DependencyGraph, scc: SCCInfo, domain: str) -> None:
    """Formal memory-stress runs must not silently use placeholder node text."""
    bad_nodes = []
    for cid in scc.clause_ids:
        clause = graph.clauses.get(cid)
        if not clause or not (clause.content or "").strip():
            bad_nodes.append(f"{cid}: empty/missing content")
            continue
        metadata = clause.metadata or {}
        if metadata.get("diagnostic_only") or metadata.get("original_record") is not True:
            bad_nodes.append(f"{cid}: source={metadata.get('source', 'unknown')}")
    if bad_nodes:
        preview = "; ".join(bad_nodes[:5])
        raise RuntimeError(
            f"{domain} SCC {scc.id} does not have audited original node content "
            f"for all nodes ({preview}). Formal runs must use original records; "
            "synthetic/placeholder content is diagnostic only."
        )


def select_memory_real_sccs(
    sccs: list[SCCInfo],
    min_size: int,
    max_size: int,
    max_count: int,
) -> list[SCCInfo]:
    """Pick real SCCs with size diversity while respecting the formal size cap."""
    candidates = sorted(
        [s for s in sccs if min_size <= s.size <= max_size],
        key=lambda s: (s.size, sorted(s.clause_ids)),
    )
    if len(candidates) <= max_count:
        return candidates

    anchors = [5, 8, 12, 16, 24]
    selected: list[SCCInfo] = []
    for anchor in anchors:
        eligible = [s for s in candidates if s not in selected]
        if not eligible or len(selected) >= max_count:
            break
        best = min(
            eligible,
            key=lambda s: (abs(s.size - anchor), -s.size, sorted(s.clause_ids)),
        )
        selected.append(best)

    for scc in sorted(candidates, key=lambda s: (-s.size, sorted(s.clause_ids))):
        if len(selected) >= max_count:
            break
        if scc not in selected:
            selected.append(scc)
    return sorted(selected, key=lambda s: (s.size, sorted(s.clause_ids)))


def reorder_scc_for_memory_stress(scc: SCCInfo, injected_id: str) -> SCCInfo:
    """Move the GT node into the later third of one-shot prompt order."""
    ids = [cid for cid in scc.clause_ids if cid != injected_id]
    insert_at = max(0, min(len(ids), (len(scc.clause_ids) * 2) // 3))
    reordered = ids[:insert_at] + [injected_id] + ids[insert_at:]
    return scc.model_copy(update={"clause_ids": reordered, "size": len(reordered)})


def build_risk_subgraph_summary(
    graph: DependencyGraph,
    scc: SCCInfo,
    result: dict,
    injected_id: str | None,
    evidence_ids: list[str] | None = None,
    risk_ids: list[str] | None = None,
    affected_ids: list[str] | None = None,
    top_k: int = 3,
) -> dict:
    """Summarize compact risk subgraphs retained by SA-MCGS evidence.

    The legacy risk_subgraph_* fields are explicitly post-hoc because they use
    injected_id as an anchor. The blind_risk_subgraph_* fields do not use GT.
    """
    scc_ids = set(scc.clause_ids)
    ordered_cycle = [cid for cid in scc.clause_ids if cid in scc_ids]

    def with_cycle_neighbors(nodes: set[str], anchors: set[str]) -> set[str]:
        expanded = set(nodes)
        for anchor in anchors:
            if anchor not in ordered_cycle:
                continue
            idx = ordered_cycle.index(anchor)
            expanded.add(ordered_cycle[(idx - 1) % len(ordered_cycle)])
            expanded.add(ordered_cycle[(idx + 1) % len(ordered_cycle)])
        return expanded

    evidence_nodes = set(result.get("oc_detected", []))
    evidence_nodes.update(cid for cid, _ in result.get("ranking", [])[:top_k])

    blind_anchors = set(result.get("oc_detected", []))
    if not blind_anchors and result.get("ranking"):
        blind_anchors.add(result["ranking"][0][0])
    blind_nodes = with_cycle_neighbors(evidence_nodes, blind_anchors)
    blind_ordered_nodes = [cid for cid in scc.clause_ids if cid in blind_nodes]
    if not blind_ordered_nodes and result.get("ranking"):
        blind_ordered_nodes = [result["ranking"][0][0]]

    nodes = set(blind_ordered_nodes)
    posthoc_anchors = set(blind_anchors)
    if injected_id:
        nodes.add(injected_id)
        posthoc_anchors.add(injected_id)
    nodes = with_cycle_neighbors(nodes, posthoc_anchors)

    ordered_nodes = [cid for cid in scc.clause_ids if cid in nodes]
    if not ordered_nodes and result.get("ranking"):
        ordered_nodes = [result["ranking"][0][0]]

    evidence_ids = list(dict.fromkeys(evidence_ids or ([injected_id] if injected_id else [])))
    evidence_set = set(evidence_ids)
    risk_ids = list(dict.fromkeys(risk_ids or ([injected_id] if injected_id else [])))
    risk_set = set(risk_ids)
    affected_ids = list(dict.fromkeys(affected_ids or []))
    affected_set = set(affected_ids)
    blind_evidence_retained = [cid for cid in evidence_ids if cid in blind_ordered_nodes]
    posthoc_evidence_retained = [cid for cid in evidence_ids if cid in ordered_nodes]

    size = len(ordered_nodes)
    total = max(1, scc.size)
    return {
        "risk_subgraph_nodes": ordered_nodes,
        "risk_subgraph_size": size,
        "compression_ratio": 1 - (size / total),
        "contains_injected_node": bool(injected_id and injected_id in ordered_nodes),
        "contains_any_evidence_node": bool(evidence_set.intersection(ordered_nodes)),
        "contains_all_evidence_nodes": bool(evidence_ids and all(cid in ordered_nodes for cid in evidence_ids)),
        "evidence_nodes_retained": posthoc_evidence_retained,
        "contains_any_risk_node": bool(risk_set.intersection(ordered_nodes)),
        "contains_all_risk_nodes": bool(risk_ids and all(cid in ordered_nodes for cid in risk_ids)),
        "contains_any_affected_node": bool(affected_set.intersection(ordered_nodes)),
        "subgraph_type": "posthoc_gt_anchored",
        "subgraph_policy": f"oc_nodes + top_{top_k}_risk + ordered-cycle neighbors of OC/GT anchors",
        "blind_risk_subgraph_nodes": blind_ordered_nodes,
        "blind_risk_subgraph_size": len(blind_ordered_nodes),
        "blind_compression_ratio": 1 - (len(blind_ordered_nodes) / total),
        "blind_contains_injected_node": bool(injected_id and injected_id in blind_ordered_nodes),
        "blind_contains_any_evidence_node": bool(evidence_set.intersection(blind_ordered_nodes)),
        "blind_contains_all_evidence_nodes": bool(evidence_ids and all(cid in blind_ordered_nodes for cid in evidence_ids)),
        "blind_evidence_nodes_retained": blind_evidence_retained,
        "blind_contains_any_risk_node": bool(risk_set.intersection(blind_ordered_nodes)),
        "blind_contains_all_risk_nodes": bool(risk_ids and all(cid in blind_ordered_nodes for cid in risk_ids)),
        "blind_contains_any_affected_node": bool(affected_set.intersection(blind_ordered_nodes)),
        "blind_subgraph_policy": f"oc_nodes + top_{top_k}_risk + ordered-cycle neighbors of OC anchors only",
    }


def build_local_declared_subgraph_summary(
    scc: SCCInfo,
    result: dict,
    evidence_ids: list[str] | None = None,
    risk_ids: list[str] | None = None,
    affected_ids: list[str] | None = None,
    max_ratio: float = 0.45,
    min_nodes: int = 4,
) -> dict:
    """Build a blind SA-MCGS subgraph from LLM-declared local window subgraphs."""
    scc_ids = list(scc.clause_ids)
    scc_set = set(scc_ids)
    signal = {
        cid: _coerce_float(score, 0.0)
        for cid, score in (result.get("local_subgraph_signal") or {}).items()
        if cid in scc_set
    }
    oc_nodes = [cid for cid in result.get("oc_detected", []) if cid in scc_set]
    repair_counts = {
        cid: int(_coerce_float(count, 0.0))
        for cid, count in (result.get("repair_entry_counts") or {}).items()
        if cid in scc_set
    }

    ranked_candidates: list[tuple[str, float]] = []
    raw_ranking = result.get("ranking_by_local_subgraph") or []
    if isinstance(raw_ranking, list):
        for item in raw_ranking:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                cid = item[0]
                score = _coerce_float(item[1], signal.get(cid, 0.0))
            elif isinstance(item, dict):
                cid = item.get("clause_id") or item.get("node_id") or item.get("id")
                score = _coerce_float(item.get("score"), signal.get(cid, 0.0))
            else:
                continue
            if isinstance(cid, str) and cid in scc_set and score > 0:
                ranked_candidates.append((cid, score))

    if not ranked_candidates:
        ranked_candidates = [
            (cid, score) for cid, score in signal.items() if score > 0
        ]
    if not ranked_candidates:
        ranked_candidates = [
            (cid, score)
            for cid, score in result.get("ranking", [])[:min_nodes]
            if cid in scc_set
        ]

    max_signal = max([score for _, score in ranked_candidates] or [0.0])
    candidate_scores = {
        cid: score
        for cid, score in ranked_candidates
    }
    for cid in oc_nodes:
        candidate_scores[cid] = candidate_scores.get(cid, 0.0) + max(1.0, max_signal * 0.25)
    for cid, count in repair_counts.items():
        if count > 0:
            candidate_scores[cid] = candidate_scores.get(cid, 0.0) + 0.5 * count

    cap = min(len(scc_ids), max(min_nodes, math.ceil(len(scc_ids) * max_ratio)))
    selected: set[str] = set(oc_nodes)
    for cid, _score in sorted(candidate_scores.items(), key=lambda item: (-item[1], scc_ids.index(item[0]))):
        if len(selected) >= cap:
            break
        selected.add(cid)

    if not selected and result.get("ranking"):
        selected.add(result["ranking"][0][0])

    ordered_nodes = [cid for cid in scc_ids if cid in selected]
    total = max(1, len(scc_ids))

    evidence_ids = list(dict.fromkeys(evidence_ids or []))
    risk_ids = list(dict.fromkeys(risk_ids or []))
    affected_ids = list(dict.fromkeys(affected_ids or []))
    valuable_ids = list(dict.fromkeys([*risk_ids, *affected_ids]))

    def retained(ids: list[str]) -> list[str]:
        node_set = set(ordered_nodes)
        return [cid for cid in ids if cid in node_set]

    def coverage(ids: list[str]) -> float | None:
        if not ids:
            return None
        return len(retained(ids)) / len(ids)

    node_set = set(ordered_nodes)
    return {
        "local_declared_risk_subgraph_nodes": ordered_nodes,
        "local_declared_risk_subgraph_size": len(ordered_nodes),
        "local_declared_compression_ratio": 1 - (len(ordered_nodes) / total),
        "local_declared_subgraph_policy": (
            "aggregate LLM-declared local_risk_subgraph_nodes, repair_entry_nodes, "
            "local conflict endpoints, and OC nodes; cap by SCC size"
        ),
        "local_declared_contains_any_risk_node": bool(set(risk_ids) & node_set),
        "local_declared_contains_all_risk_nodes": bool(
            risk_ids and all(cid in node_set for cid in risk_ids)
        ),
        "local_declared_risk_nodes_retained": retained(risk_ids),
        "local_declared_risk_coverage": coverage(risk_ids),
        "local_declared_contains_any_evidence_node": bool(set(evidence_ids) & node_set),
        "local_declared_contains_all_evidence_nodes": bool(
            evidence_ids and all(cid in node_set for cid in evidence_ids)
        ),
        "local_declared_evidence_nodes_retained": retained(evidence_ids),
        "local_declared_evidence_coverage": coverage(evidence_ids),
        "local_declared_contains_any_affected_node": bool(set(affected_ids) & node_set),
        "local_declared_contains_all_affected_nodes": bool(
            affected_ids and all(cid in node_set for cid in affected_ids)
        ),
        "local_declared_affected_nodes_retained": retained(affected_ids),
        "local_declared_contains_any_valuable_node": bool(set(valuable_ids) & node_set),
        "local_declared_contains_all_valuable_nodes": bool(
            valuable_ids and all(cid in node_set for cid in valuable_ids)
        ),
        "local_declared_valuable_nodes_retained": retained(valuable_ids),
        "local_declared_valuable_coverage": coverage(valuable_ids),
    }


def build_core_evidence_subgraph_summary(
    scc: SCCInfo,
    result: dict,
    evidence_ids: list[str] | None = None,
    risk_ids: list[str] | None = None,
    affected_ids: list[str] | None = None,
) -> dict:
    """Evaluate SA-MCGS's built-in evidence_risk_subgraph output.

    Unlike legacy post-hoc summaries, this consumes the subgraph emitted by
    AlphaGoMCGS itself from its rollout evidence accumulator.
    """
    scc_set = set(scc.clause_ids)
    nodes = [
        cid for cid in (result.get("evidence_risk_subgraph_nodes") or [])
        if cid in scc_set
    ]
    context_nodes = [
        cid for cid in (result.get("context_evidence_risk_subgraph_nodes") or [])
        if cid in scc_set
    ]
    node_set = set(nodes)
    context_node_set = set(context_nodes)
    total = max(1, len(scc.clause_ids))
    evidence_ids = list(dict.fromkeys(evidence_ids or []))
    risk_ids = list(dict.fromkeys(risk_ids or []))
    affected_ids = list(dict.fromkeys(affected_ids or []))
    valuable_ids = list(dict.fromkeys([*risk_ids, *affected_ids]))

    def retained(ids: list[str]) -> list[str]:
        return [cid for cid in ids if cid in node_set]

    def coverage(ids: list[str]) -> float | None:
        if not ids:
            return None
        return len(retained(ids)) / len(ids)

    return {
        "core_evidence_risk_subgraph_nodes": nodes,
        "core_evidence_risk_subgraph_size": len(nodes),
        "core_evidence_compression_ratio": 1 - (len(nodes) / total),
        "core_evidence_hit_cap": bool(result.get("dynamic_core_hit_cap")),
        "context_evidence_risk_subgraph_nodes": context_nodes,
        "context_evidence_risk_subgraph_size": len(context_nodes),
        "context_evidence_compression_ratio": 1 - (len(context_nodes) / total),
        "core_evidence_contains_any_risk_node": bool(set(risk_ids) & node_set),
        "core_evidence_contains_all_risk_nodes": bool(
            risk_ids and all(cid in node_set for cid in risk_ids)
        ),
        "core_evidence_risk_nodes_retained": retained(risk_ids),
        "core_evidence_risk_coverage": coverage(risk_ids),
        "core_evidence_contains_any_evidence_node": bool(set(evidence_ids) & node_set),
        "core_evidence_contains_all_evidence_nodes": bool(
            evidence_ids and all(cid in node_set for cid in evidence_ids)
        ),
        "core_evidence_evidence_nodes_retained": retained(evidence_ids),
        "core_evidence_evidence_coverage": coverage(evidence_ids),
        "core_evidence_contains_any_affected_node": bool(set(affected_ids) & node_set),
        "core_evidence_contains_all_affected_nodes": bool(
            affected_ids and all(cid in node_set for cid in affected_ids)
        ),
        "core_evidence_affected_nodes_retained": retained(affected_ids),
        "core_evidence_contains_any_valuable_node": bool(set(valuable_ids) & node_set),
        "core_evidence_contains_all_valuable_nodes": bool(
            valuable_ids and all(cid in node_set for cid in valuable_ids)
        ),
        "core_evidence_valuable_nodes_retained": retained(valuable_ids),
        "core_evidence_valuable_coverage": coverage(valuable_ids),
        "context_evidence_contains_any_risk_node": bool(set(risk_ids) & context_node_set),
        "context_evidence_contains_all_risk_nodes": bool(
            risk_ids and all(cid in context_node_set for cid in risk_ids)
        ),
    }


def build_trace_convergence_summary(
    scc: SCCInfo,
    result: dict,
    evidence_ids: list[str] | None = None,
    risk_ids: list[str] | None = None,
    affected_ids: list[str] | None = None,
    max_ratio: float = 0.45,
    min_nodes: int = 4,
) -> dict:
    """Compute rollout-prefix convergence metrics from SA-MCGS trace events."""
    events = list(result.get("trace_events") or [])
    if not events:
        return {}

    scc_ids = list(scc.clause_ids)
    scc_set = set(scc_ids)
    cap = min(len(scc_ids), max(min_nodes, math.ceil(len(scc_ids) * max_ratio)))
    risk_ids = list(dict.fromkeys(risk_ids or []))
    evidence_ids = list(dict.fromkeys(evidence_ids or []))
    affected_ids = list(dict.fromkeys(affected_ids or []))
    valuable_ids = list(dict.fromkeys([*risk_ids, *affected_ids]))

    local_counts: dict[str, int] = defaultdict(int)
    repair_counts: dict[str, int] = defaultdict(int)
    endpoint_counts: dict[str, int] = defaultdict(int)
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    explicit_pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    pair_reasons: dict[tuple[str, str], list[str]] = defaultdict(list)
    total_risk: dict[str, float] = defaultdict(float)
    visit_counts: dict[str, int] = defaultdict(int)
    oc_nodes: set[str] = set()
    prev_selected: set[str] = set()
    rows: list[dict] = []
    cumulative_llm_calls = 0

    first_subgraph_any = None
    first_subgraph_all = None
    first_local_any = None
    first_local_all = None
    first_window_any = None
    first_window_all = None
    first_effective_oc = None

    def retained(nodes: set[str], ids: list[str]) -> list[str]:
        return [cid for cid in ids if cid in nodes]

    def coverage(nodes: set[str], ids: list[str]) -> float | None:
        if not ids:
            return None
        return len(retained(nodes, ids)) / len(ids)

    def any_hit(nodes: set[str], ids: list[str]) -> bool:
        return bool(set(ids) & nodes)

    def all_hit(nodes: set[str], ids: list[str]) -> bool:
        return bool(ids and all(cid in nodes for cid in ids))

    def pair_key(source: str | None, target: str | None) -> tuple[str, str] | None:
        if source in scc_set and target in scc_set and source != target:
            return tuple(sorted((source, target)))
        return None

    def select_nodes() -> dict:
        avg_risk = {
            cid: total_risk[cid] / visit_counts[cid]
            for cid in scc_ids
            if visit_counts.get(cid, 0) > 0
        }
        risk_values = list(avg_risk.values())
        if risk_values:
            ordered_risk = sorted(risk_values)
            mid = len(ordered_risk) // 2
            risk_baseline = (
                ordered_risk[mid]
                if len(ordered_risk) % 2
                else (ordered_risk[mid - 1] + ordered_risk[mid]) / 2
            )
        else:
            risk_baseline = 0.0
        signal = {
            cid: local_counts.get(cid, 0)
            + repair_counts.get(cid, 0)
            + endpoint_counts.get(cid, 0)
            + max(0.0, avg_risk.get(cid, 0.0) - risk_baseline)
            for cid in scc_ids
        }
        max_signal = max(signal.values() or [0])
        scores: dict[str, float] = {
            cid: float(score)
            for cid, score in signal.items()
            if score > 0
        }
        for cid in oc_nodes:
            scores[cid] = scores.get(cid, 0.0) + max(1.0, max_signal * 0.25)
        for cid, count in repair_counts.items():
            if count > 0:
                scores[cid] = scores.get(cid, 0.0) + 0.5 * count
        selected: set[str] = set(oc_nodes)
        pair_memory_nodes: set[str] = set()
        pair_memory_node_scores: dict[str, float] = {}

        max_pair_count = max(pair_counts.values() or [0])
        max_explicit_count = max(explicit_pair_counts.values() or [0])
        pair_rows = []
        for (source, target), count in pair_counts.items():
            reasons = pair_reasons.get((source, target), [])
            semantic_strength = AlphaGoMCGS._semantic_conflict_strength(reasons)
            count_score = math.log1p(count) / math.log1p(max(1, max_pair_count))
            explicit_count = explicit_pair_counts.get((source, target), 0)
            explicit_score = (
                math.log1p(explicit_count) / math.log1p(max_explicit_count)
                if max_explicit_count > 0 and explicit_count > 0 else 0.0
            )
            endpoint_score = (
                scores.get(source, 0.0) + scores.get(target, 0.0)
            ) / max(1.0, 2 * max(scores.values() or [1.0]))
            pair_score = (
                0.45 * semantic_strength
                + 0.20 * explicit_score
                + 0.20 * count_score
                + 0.15 * endpoint_score
            )
            pair_rows.append({
                "source": source,
                "target": target,
                "count": count,
                "explicit_count": explicit_count,
                "semantic_strength": semantic_strength,
                "pair_score": pair_score,
            })
        pair_rows.sort(
            key=lambda edge: (
                -edge["pair_score"],
                -edge["semantic_strength"],
                -edge["explicit_count"],
                -edge["count"],
                edge["source"],
                edge["target"],
            )
        )

        pair_node_soft_cap = min(cap, max(2, math.ceil(cap * 0.65)))
        for edge in pair_rows:
            if len(selected) >= cap:
                break
            if edge["pair_score"] < 0.42 and edge["semantic_strength"] < 0.8:
                continue
            endpoints = [edge["source"], edge["target"]]
            new_nodes = [cid for cid in endpoints if cid not in selected]
            if not new_nodes:
                continue
            within_soft_cap = len(selected) + len(new_nodes) <= pair_node_soft_cap
            one_endpoint_selected = any(cid in selected for cid in endpoints)
            strong_pair = edge["semantic_strength"] >= 0.8
            if not (within_soft_cap or one_endpoint_selected or strong_pair):
                continue
            for cid in endpoints:
                if len(selected) >= cap:
                    break
                selected.add(cid)
                pair_memory_nodes.add(cid)
                pair_memory_node_scores[cid] = max(
                    pair_memory_node_scores.get(cid, 0.0),
                    float(edge["pair_score"]),
                )

        sorted_scores = sorted(
            scores.items(),
            key=lambda item: (-item[1], scc_ids.index(item[0])),
        )
        for cid, _score in sorted_scores:
            if len(selected) >= cap:
                break
            selected.add(cid)

        for edge in pair_rows:
            if edge["pair_score"] < 0.35 and edge["semantic_strength"] < 0.65:
                continue
            source = edge["source"]
            target = edge["target"]
            if (source in selected) == (target in selected):
                continue
            counterpart = target if source in selected else source
            if len(selected) < cap:
                selected.add(counterpart)
                pair_memory_nodes.add(counterpart)
                pair_memory_node_scores[counterpart] = max(
                    pair_memory_node_scores.get(counterpart, 0.0),
                    float(edge["pair_score"]),
                )
                continue
            replaceable = [
                cid for cid in selected
                if cid not in oc_nodes
                and cid not in {source, target}
            ]
            if not replaceable:
                continue
            weakest = min(
                replaceable,
                key=lambda cid: (
                    pair_memory_node_scores.get(cid, 0.0),
                    scores.get(cid, 0.0),
                    -scc_ids.index(cid),
                ),
            )
            weakest_pair_score = pair_memory_node_scores.get(weakest, 0.0)
            weakest_score = scores.get(weakest, 0.0) / max(1.0, max(scores.values() or [1.0]))
            if edge["pair_score"] >= max(0.35, weakest_pair_score * 1.05, weakest_score * 0.85):
                selected.remove(weakest)
                selected.add(counterpart)
                pair_memory_nodes.add(counterpart)
                pair_memory_node_scores[counterpart] = max(
                    pair_memory_node_scores.get(counterpart, 0.0),
                    float(edge["pair_score"]),
                )
        legacy_context_selected = set(selected)

        pair_endpoint_scores: dict[str, float] = defaultdict(float)
        pair_endpoint_counts: dict[str, int] = defaultdict(int)
        strong_edges = []
        for edge in pair_rows:
            pair_score = float(edge.get("pair_score", 0.0))
            semantic_strength = float(edge.get("semantic_strength", 0.0))
            explicit_count = int(edge.get("explicit_count", 0))
            if (
                pair_score >= 0.42
                or semantic_strength >= 0.65
                or explicit_count > 0
            ):
                strong_edges.append(edge)
                for cid in (edge["source"], edge["target"]):
                    pair_endpoint_scores[cid] = max(pair_endpoint_scores[cid], pair_score)
                    pair_endpoint_counts[cid] += 1

        core_candidate_universe = {
            cid for cid, score in scores.items()
            if cid in scc_set and score > 0
        }
        core_candidate_universe.update(cid for cid in oc_nodes if cid in scc_set)
        for edge in strong_edges:
            for cid in (edge["source"], edge["target"]):
                if cid in scc_set:
                    core_candidate_universe.add(cid)
        if not core_candidate_universe:
            core_candidate_universe = set(legacy_context_selected)

        max_score = max(scores.values() or [1.0])
        priority_rows = []
        for cid in core_candidate_universe:
            score = scores.get(cid, 0.0) / max(1.0, max_score)
            pair_score = pair_endpoint_scores.get(cid, 0.0)
            oc_bonus = 0.16 if cid in oc_nodes else 0.0
            priority = score + 0.24 * pair_score + oc_bonus
            if priority <= 0:
                continue
            priority_rows.append({
                "clause_id": cid,
                "priority": priority,
                "score": score,
                "pair_score": pair_score,
                "pair_endpoint_count": pair_endpoint_counts.get(cid, 0),
                "oc": cid in oc_nodes,
            })
        priority_rows.sort(
            key=lambda row: (
                -row["priority"],
                -row["pair_endpoint_count"],
                scc_ids.index(row["clause_id"]),
            )
        )
        if not priority_rows:
            context_nodes = [cid for cid in scc_ids if cid in legacy_context_selected]
            return {
                "core_nodes": context_nodes[:1],
                "context_nodes": context_nodes,
                "core_hit_cap": len(context_nodes[:1]) >= cap,
                "stop_reason": "fallback",
            }

        top_priority = max(priority_rows[0]["priority"], 1e-9)
        core_min_nodes = min(cap, 2)
        core_selected: set[str] = set()
        prev_priority = priority_rows[0]["priority"]
        stop_reason = "exhausted_candidates"

        if strong_edges:
            top_pair_score = max(float(edge.get("pair_score", 0.0)) for edge in strong_edges)
            relation_seed_node_cap = min(cap, core_min_nodes)
            relation_seed_min_score = max(0.42, top_pair_score * 0.90)
            for edge in strong_edges:
                if len(core_selected) >= relation_seed_node_cap:
                    break
                pair_score = float(edge.get("pair_score", 0.0))
                semantic_strength = float(edge.get("semantic_strength", 0.0))
                if pair_score < relation_seed_min_score and semantic_strength < 0.9:
                    continue
                endpoints = [
                    cid for cid in (edge["source"], edge["target"])
                    if cid in core_candidate_universe
                ]
                if len(endpoints) < 2:
                    continue
                if len(core_selected.union(endpoints)) > relation_seed_node_cap:
                    continue
                core_selected.update(endpoints)

        for row in priority_rows:
            if len(core_selected) >= cap:
                stop_reason = "hit_cap"
                break
            priority = float(row["priority"])
            relative = priority / top_priority
            gap = max(0.0, (prev_priority - priority) / top_priority)
            if row["clause_id"] in core_selected:
                prev_priority = priority
                continue
            must_keep = row["oc"]
            if len(core_selected) >= core_min_nodes and not must_keep:
                if priority < 0.10:
                    stop_reason = "below_absolute_score"
                    break
                if gap >= 0.14:
                    stop_reason = "score_gap"
                    break
                if relative < 0.28:
                    stop_reason = "below_tail_relative_score"
                    break
                if relative < 0.52:
                    stop_reason = "below_relative_score"
                    break
            core_selected.add(row["clause_id"])
            prev_priority = priority

        closure_top_pair_score = max(
            [float(edge.get("pair_score", 0.0)) for edge in strong_edges] or [0.0]
        )
        for edge in strong_edges:
            if len(core_selected) >= cap:
                break
            source = edge["source"]
            target = edge["target"]
            if source not in core_candidate_universe or target not in core_candidate_universe:
                continue
            if (source in core_selected) == (target in core_selected):
                continue
            counterpart = target if source in core_selected else source
            pair_score = float(edge.get("pair_score", 0.0))
            semantic_strength = float(edge.get("semantic_strength", 0.0))
            counterpart_priority = next(
                (
                    float(row["priority"])
                    for row in priority_rows
                    if row["clause_id"] == counterpart
                ),
                0.0,
            )
            if (
                pair_score >= max(0.35, closure_top_pair_score * 0.90)
                and (
                    semantic_strength >= 0.9
                    or counterpart_priority / top_priority >= 0.35
                )
            ):
                core_selected.add(counterpart)

        core_nodes = [cid for cid in scc_ids if cid in core_selected]
        context_selected = set(core_selected)
        for cid in scc_ids:
            if len(context_selected) >= cap:
                break
            if cid in legacy_context_selected:
                context_selected.add(cid)
        for cid, _score in sorted_scores:
            if len(context_selected) >= cap:
                break
            context_selected.add(cid)
        context_nodes = [cid for cid in scc_ids if cid in context_selected]
        return {
            "core_nodes": core_nodes,
            "context_nodes": context_nodes,
            "core_hit_cap": len(core_nodes) >= cap,
            "stop_reason": stop_reason,
        }

    for event in sorted(events, key=lambda e: e.get("completion_index", e.get("iteration", 0))):
        rollout = int(event.get("completion_index") or len(rows) + 1)
        if not event.get("is_tt_hit"):
            cumulative_llm_calls += 1

        window_nodes = {
            cid for cid in event.get("window", [])
            if cid in scc_set
        }
        local_nodes = {
            cid for cid in event.get("local_risk_subgraph_nodes", [])
            if cid in scc_set
        }
        repair_nodes = {
            cid for cid in event.get("repair_entry_nodes", [])
            if cid in scc_set
        }
        oc_nodes.update(
            cid for cid in event.get("oc_detected_so_far", [])
            if cid in scc_set
        )
        for cid, score in (event.get("scores") or {}).items():
            if cid in scc_set:
                visit_counts[cid] += 1
                total_risk[cid] += float(score)

        for cid in local_nodes:
            local_counts[cid] += 1
        for cid in repair_nodes:
            repair_counts[cid] += 1
        counted_pairs: set[tuple[str, str]] = set()
        for conflict in event.get("conflicts", []):
            if not isinstance(conflict, dict):
                continue
            key = pair_key(conflict.get("clause_a"), conflict.get("clause_b"))
            if not key:
                continue
            pair_counts[key] += 1
            explicit_pair_counts[key] += 1
            counted_pairs.add(key)
            endpoint_counts[key[0]] += 1
            endpoint_counts[key[1]] += 1
            reason = str(conflict.get("description") or "")[:300]
            if reason and len(pair_reasons[key]) < 3:
                pair_reasons[key].append(reason)
        for edge in event.get("local_conflict_edges", []):
            if not isinstance(edge, dict):
                continue
            source = edge.get("source")
            target = edge.get("target")
            key = pair_key(source, target)
            if not key:
                continue
            if key not in counted_pairs:
                pair_counts[key] += 1
                endpoint_counts[key[0]] += 1
                endpoint_counts[key[1]] += 1
            reason = str(edge.get("reason") or "")[:300]
            if reason and len(pair_reasons[key]) < 3:
                pair_reasons[key].append(reason)

        selection = select_nodes()
        selected_nodes = selection["core_nodes"]
        context_nodes = selection["context_nodes"]
        selected = set(selected_nodes)
        if risk_ids:
            if first_window_any is None and any_hit(window_nodes, risk_ids):
                first_window_any = rollout
            if first_window_all is None and all_hit(window_nodes, risk_ids):
                first_window_all = rollout
            if first_local_any is None and any_hit(local_nodes, risk_ids):
                first_local_any = rollout
            if first_local_all is None and all_hit(local_nodes, risk_ids):
                first_local_all = rollout
            if first_subgraph_any is None and any_hit(selected, risk_ids):
                first_subgraph_any = rollout
            if first_subgraph_all is None and all_hit(selected, risk_ids):
                first_subgraph_all = rollout
            if first_effective_oc is None and any_hit(oc_nodes, risk_ids + affected_ids):
                first_effective_oc = rollout

        union = selected | prev_selected
        jaccard = (
            len(selected & prev_selected) / len(union)
            if union else None
        )
        prev_selected = selected
        rows.append({
            "rollout": rollout,
            "llm_calls": cumulative_llm_calls,
            "window_risk_any": any_hit(window_nodes, risk_ids),
            "window_risk_all": all_hit(window_nodes, risk_ids),
            "local_risk_any": any_hit(local_nodes, risk_ids),
            "local_risk_all": all_hit(local_nodes, risk_ids),
            "subgraph_nodes": selected_nodes,
            "subgraph_size": len(selected_nodes),
            "compression_ratio": 1 - (len(selected_nodes) / max(1, len(scc_ids))),
            "context_subgraph_nodes": context_nodes,
            "context_subgraph_size": len(context_nodes),
            "context_compression_ratio": 1 - (len(context_nodes) / max(1, len(scc_ids))),
            "core_hit_cap": selection.get("core_hit_cap"),
            "core_stop_reason": selection.get("stop_reason"),
            "risk_coverage": coverage(selected, risk_ids),
            "evidence_coverage": coverage(selected, evidence_ids),
            "valuable_coverage": coverage(selected, valuable_ids),
            "risk_any": any_hit(selected, risk_ids),
            "risk_all": all_hit(selected, risk_ids),
            "evidence_all": all_hit(selected, evidence_ids),
            "effective_oc": any_hit(oc_nodes, risk_ids + affected_ids),
            "jaccard_prev": jaccard,
        })

    probe_points = [1, 2, 4, 8, 16, 30, 60, 100]
    convergence_points = {}
    max_rollout_seen = rows[-1]["rollout"] if rows else 0
    for point in probe_points:
        if point > max_rollout_seen:
            continue
        candidates = [row for row in rows if row["rollout"] <= point]
        if candidates:
            convergence_points[str(point)] = candidates[-1]

    risk_cov_values = [
        row["risk_coverage"]
        for row in rows
        if row.get("risk_coverage") is not None
    ]
    stability_values = [
        row["jaccard_prev"]
        for row in rows[1:]
        if row.get("jaccard_prev") is not None
    ]
    final = rows[-1]
    return {
        "convergence_trace": rows,
        "convergence_points": convergence_points,
        "convergence_auc_risk_coverage": (
            sum(risk_cov_values) / len(risk_cov_values)
            if risk_cov_values else None
        ),
        "convergence_mean_stability": (
            sum(stability_values) / len(stability_values)
            if stability_values else None
        ),
        "convergence_final_risk_coverage": final.get("risk_coverage"),
        "convergence_final_evidence_coverage": final.get("evidence_coverage"),
        "convergence_final_valuable_coverage": final.get("valuable_coverage"),
        "convergence_final_subgraph_size": final.get("subgraph_size"),
        "convergence_final_compression_ratio": final.get("compression_ratio"),
        "convergence_final_context_subgraph_size": final.get("context_subgraph_size"),
        "convergence_final_context_compression_ratio": final.get("context_compression_ratio"),
        "convergence_final_core_hit_cap": final.get("core_hit_cap"),
        "convergence_final_core_stop_reason": final.get("core_stop_reason"),
        "first_window_risk_any_rollout": first_window_any,
        "first_window_risk_all_rollout": first_window_all,
        "first_local_risk_any_rollout": first_local_any,
        "first_local_risk_all_rollout": first_local_all,
        "first_subgraph_risk_any_rollout": first_subgraph_any,
        "first_subgraph_risk_all_rollout": first_subgraph_all,
        "first_effective_oc_rollout": first_effective_oc,
    }


def add_rank_metrics(result: dict, injected_id: str | None) -> None:
    """Attach rank and margin metrics for the injected GT node."""
    ranking = result.get("ranking", [])
    if injected_id:
        ranks = [idx + 1 for idx, (cid, _) in enumerate(ranking) if cid == injected_id]
        result["injected_rank"] = ranks[0] if ranks else None
    if len(ranking) >= 2:
        result["top1_margin"] = ranking[0][1] - ranking[1][1]
    else:
        result["top1_margin"] = None


def get_injection_metadata(graph: DependencyGraph, injected_id: str | None) -> dict:
    """Extract injected root/witness metadata into result records."""
    if not injected_id or injected_id not in graph.clauses:
        return {}
    metadata = graph.clauses[injected_id].metadata
    evidence_nodes = metadata.get("_inject_evidence_nodes") or [injected_id]
    return {
        "inject_profile_version": metadata.get("_inject_profile_version"),
        "injected_witness_node": metadata.get("_inject_witness_node"),
        "injected_witness_distance": metadata.get("_inject_witness_distance"),
        "injected_bridge_node": metadata.get("_inject_bridge_node"),
        "injected_bridge_distance": metadata.get("_inject_bridge_distance"),
        "injected_risk_nodes": list(metadata.get("_inject_risk_nodes") or [injected_id]),
        "injected_evidence_nodes": list(evidence_nodes),
        "injected_affected_nodes": list(metadata.get("_inject_affected_nodes") or []),
        "injected_conflict_family": metadata.get("_inject_conflict_family"),
        "injected_conflict_difficulty": metadata.get("_inject_conflict_difficulty"),
        "injected_conflict_severity": metadata.get("_inject_conflict_severity"),
        "injected_conflict_severity_label": metadata.get("_inject_conflict_severity_label"),
        "injected_conflict_template": metadata.get("_inject_conflict_template"),
    }


def _add_node_set_rank_metrics(result: dict, prefix: str, node_ids: list[str] | None) -> None:
    node_ids = list(dict.fromkeys(node_ids or []))
    if not node_ids:
        return
    ranking = result.get("ranking", [])
    ranked_ids = [cid for cid, _ in ranking]
    ranks = {
        cid: ranked_ids.index(cid) + 1
        for cid in node_ids
        if cid in ranked_ids
    }
    top1 = ranked_ids[:1]
    top3 = ranked_ids[:3]
    top5 = ranked_ids[:5]
    result[f"{prefix}_node_ranks"] = ranks
    result[f"{prefix}_best_rank"] = min(ranks.values()) if ranks else None
    result[f"{prefix}_worst_rank"] = max(ranks.values()) if len(ranks) == len(node_ids) else None
    result[f"{prefix}_top1_hit"] = bool(top1 and top1[0] in node_ids)
    result[f"{prefix}_top3_hit"] = any(cid in node_ids for cid in top3)
    result[f"{prefix}_top5_hit"] = any(cid in node_ids for cid in top5)
    result[f"{prefix}_all_top3_hit"] = bool(node_ids and all(cid in top3 for cid in node_ids))
    result[f"{prefix}_all_top5_hit"] = bool(node_ids and all(cid in top5 for cid in node_ids))


def add_structural_rank_metrics(result: dict, injection_metadata: dict) -> None:
    """Attach ranking metrics for risk, evidence, and affected node sets."""
    risk_ids = injection_metadata.get("injected_risk_nodes") or []
    evidence_ids = injection_metadata.get("injected_evidence_nodes") or []
    affected_ids = injection_metadata.get("injected_affected_nodes") or []
    valuable_ids = list(dict.fromkeys([*risk_ids, *affected_ids]))
    _add_node_set_rank_metrics(result, "risk", risk_ids)
    _add_node_set_rank_metrics(result, "evidence", evidence_ids)
    _add_node_set_rank_metrics(result, "affected", affected_ids)
    _add_node_set_rank_metrics(result, "valuable", valuable_ids)
    result["root_rank"] = result.get("injected_rank")
    result["root_top1_hit"] = result.get("top1_hit")
    result["root_top3_hit"] = result.get("top3_hit")


def add_direct_subgraph_retention_metrics(result: dict, injection_metadata: dict) -> None:
    """Attach retention metrics for a Naive LLM-declared risk subgraph."""
    if result.get("naive_profile") != "direct_subgraph":
        return
    nodes = list(dict.fromkeys(result.get("direct_risk_subgraph_nodes") or []))
    node_set = set(nodes)
    risk_ids = list(dict.fromkeys(injection_metadata.get("injected_risk_nodes") or []))
    evidence_ids = list(dict.fromkeys(injection_metadata.get("injected_evidence_nodes") or []))
    affected_ids = list(dict.fromkeys(injection_metadata.get("injected_affected_nodes") or []))
    valuable_ids = list(dict.fromkeys([*risk_ids, *affected_ids]))

    def retained(ids: list[str]) -> list[str]:
        return [cid for cid in ids if cid in node_set]

    result["direct_subgraph_nodes_retained"] = nodes
    result["direct_contains_injected_node"] = bool(
        result.get("injected_node") and result["injected_node"] in node_set
    )
    result["direct_contains_any_risk_node"] = bool(set(risk_ids) & node_set)
    result["direct_contains_all_risk_nodes"] = bool(
        risk_ids and all(cid in node_set for cid in risk_ids)
    )
    result["direct_risk_nodes_retained"] = retained(risk_ids)
    result["direct_contains_any_evidence_node"] = bool(set(evidence_ids) & node_set)
    result["direct_contains_all_evidence_nodes"] = bool(
        evidence_ids and all(cid in node_set for cid in evidence_ids)
    )
    result["direct_evidence_nodes_retained"] = retained(evidence_ids)
    result["direct_contains_any_affected_node"] = bool(set(affected_ids) & node_set)
    result["direct_contains_all_affected_nodes"] = bool(
        affected_ids and all(cid in node_set for cid in affected_ids)
    )
    result["direct_affected_nodes_retained"] = retained(affected_ids)
    result["direct_contains_any_valuable_node"] = bool(set(valuable_ids) & node_set)
    result["direct_contains_all_valuable_nodes"] = bool(
        valuable_ids and all(cid in node_set for cid in valuable_ids)
    )
    result["direct_valuable_nodes_retained"] = retained(valuable_ids)


async def main(args: argparse.Namespace):
    api_key = os.environ.get("XHUB_API_KEY", "")
    if not api_key:
        api_key = input("Enter XHUB API key: ").strip()
        os.environ["XHUB_API_KEY"] = api_key
    if not api_key:
        raise RuntimeError("XHUB_API_KEY is required")

    inject_mode = bool(getattr(args, "inject", False))
    if inject_mode and not _INJECT_AVAILABLE:
        raise RuntimeError("Inject mode requested, but inject_defect.py could not be imported")
    inject_profile = getattr(args, "inject_profile", "explicit")
    if inject_profile not in SUPPORTED_INJECT_PROFILES:
        raise RuntimeError(f"Unknown inject profile: {inject_profile}")
    cycle_source = getattr(args, "cycle_source", "real_long")
    real_min_size = getattr(args, "real_min_size", 5)
    real_max_size = getattr(args, "real_max_size", 24)
    domain_size_ranges = parse_domain_size_ranges(getattr(args, "domain_size_ranges", None))
    allow_synthetic_diagnostic = bool(getattr(args, "allow_synthetic_diagnostic", False))
    if (
        inject_mode
        and inject_profile == "memory_stress"
        and cycle_source in {"synthetic_long", "both"}
        and not allow_synthetic_diagnostic
    ):
        raise RuntimeError(
            "synthetic_long/both are diagnostic-only for memory_stress. Formal runs "
            "must use --cycle-source real_long with original node content, or pass "
            "--allow-synthetic-diagnostic to make the diagnostic status explicit."
        )
    synthetic_sizes = getattr(args, "synthetic_sizes", [16, 24])
    conflict_template = getattr(args, "conflict_template", DEFAULT_MEMORY_CONFLICT_TEMPLATE)
    if conflict_template not in SUPPORTED_MEMORY_CONFLICT_TEMPLATES:
        raise RuntimeError(f"Unknown conflict template: {conflict_template}")
    conflict_severity = getattr(args, "conflict_severity", DEFAULT_MEMORY_CONFLICT_SEVERITY)
    if conflict_severity not in SUPPORTED_MEMORY_CONFLICT_SEVERITIES:
        raise RuntimeError(f"Unknown conflict severity: {conflict_severity}")
    include_subgraph_summary = bool(getattr(args, "include_subgraph_summary", False))
    naive_profile = getattr(args, "naive_profile", "ranked")
    if naive_profile not in NAIVE_PROFILES:
        raise RuntimeError(f"Unknown naive profile: {naive_profile}")
    evidence_mode = getattr(args, "mcgs_evidence_mode", "relation_first")
    methods_to_run = getattr(args, "methods", ["naive", "sa-mcgs"])
    methods_to_run = list(dict.fromkeys(methods_to_run))
    run_naive_method = "naive" in methods_to_run
    run_mcgs_method = "sa-mcgs" in methods_to_run
    if not run_naive_method and not run_mcgs_method:
        raise RuntimeError("At least one method must be selected")

    # ── Resolve filters (smoke mode is just preset filters) ──
    if args.smoke:
        domains_to_run = ["debian"]
        models_to_run = [m for m in BATTLE_MODELS if m["name"] == "deepseek-v3"]
        max_sccs = 1
        out_prefix = f"battle_inject_{inject_profile}_smoke" if inject_mode else "battle_smoke"
    else:
        domains_to_run = args.domains or (
            ["debian", "sec_ex21", "bgb", "cuad"]
            if inject_mode else
            ["debian", "wikipedia", "sec_ex21", "bgb"]
        )
        models_to_run = (
            [m for m in BATTLE_MODELS if m["name"] in args.models]
            if args.models else BATTLE_MODELS
        )
        max_sccs = args.max_sccs
        out_prefix = f"battle_inject_{inject_profile}" if inject_mode else "battle_v2"
    if inject_mode and inject_profile == "memory_stress":
        out_prefix = f"{out_prefix}_{conflict_template}"
        if conflict_severity != DEFAULT_MEMORY_CONFLICT_SEVERITY:
            out_prefix = f"{out_prefix}_{conflict_severity}"
    if naive_profile == "ranked":
        out_prefix = f"{out_prefix}_rankednaive"
    elif naive_profile == "direct_subgraph":
        out_prefix = f"{out_prefix}_directsubgraphnaive"
    if methods_to_run != ["naive", "sa-mcgs"]:
        out_prefix = f"{out_prefix}_{'_'.join(methods_to_run).replace('-', '')}only"
    if run_mcgs_method:
        out_prefix = f"{out_prefix}_{evidence_mode}"
    run_tag = getattr(args, "run_tag", None)
    if run_tag:
        safe_tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_tag).strip("_")
        out_prefix = f"{out_prefix}_{safe_tag}"

    print("=" * 70)
    print("  SA-MCGS BATTLE: Naive Prompting vs SA-MCGS")
    if args.smoke:
        print("  [SMOKE MODE] 1 domain x 1 SCC x 1 model — quick validation")
    if inject_mode:
        print("  [INJECT MODE] UDIP synthetic defect injection enabled")
        print(f"  Inject profile: {inject_profile}; cycle source: {cycle_source}")
        if inject_profile == "memory_stress":
            print(f"  Conflict template: {conflict_template}; severity: {conflict_severity}")
        if cycle_source in {"synthetic_long", "both"}:
            print("  [DIAGNOSTIC ONLY] Synthetic sizes: " + ", ".join(str(s) for s in synthetic_sizes))
    print("  Models: " + ", ".join(m["name"] for m in models_to_run))
    print("  Methods: " + ", ".join(methods_to_run))
    print(f"  Naive profile: {naive_profile}")
    if run_mcgs_method:
        print(f"  SA-MCGS evidence mode: {evidence_mode}")
    print("  Domains: " + ", ".join(domains_to_run))
    print("  Evaluation: Binary detection (Top-1/Top-3 hit on ground truth)")
    print("=" * 70)

    # ── Load only the domain graphs we need ──
    print("\n[LOAD] Loading domain data...")
    loaders = {
        "debian": load_debian_graph,
        "wikipedia": load_wikipedia_graph,
        "sec_ex21": load_sec_graph,
        "bgb": load_bgb_graph,
        "cuad": load_cuad_graph,
    }
    graphs = {}
    skipped_domains: dict[str, str] = {}
    for d in domains_to_run:
        if inject_mode and inject_profile == "memory_stress" and cycle_source == "synthetic_long":
            print(f"  Loading {d}... synthetic-only empty graph")
            graphs[d] = DependencyGraph()
        else:
            print(f"  Loading {d}...")
            try:
                graphs[d] = loaders[d]()
            except Exception as exc:
                skipped_domains[d] = str(exc)
                print(f"  [{d}] SKIP: {exc}")
    if skipped_domains:
        domains_to_run = [d for d in domains_to_run if d in graphs]
    if not graphs:
        raise RuntimeError(f"No domains could be loaded: {skipped_domains}")

    # ── Select SCCs per domain ──
    domain_sccs: dict[str, list[SCCInfo]] = {}
    if inject_mode:
        inject_scc_patterns = [
            ["libnode108", "node-acorn", "nodejs"],
            ["ocaml", "ocaml-compiler-libs", "ocaml-interp"],
            ["nova-compute"],
            ["node-babel7", "node-babel"],
        ]
        for domain, graph in graphs.items():
            detector = TarjanSCCDetector()
            detected = detector.detect(graph)
            selected = []

            if inject_profile == "memory_stress" and cycle_source in {"real_long", "both"}:
                domain_min_size, domain_max_size = domain_size_ranges.get(
                    domain,
                    (real_min_size, real_max_size),
                )
                selected.extend(
                    select_memory_real_sccs(
                        detected.sccs,
                        min_size=domain_min_size,
                        max_size=domain_max_size,
                        max_count=max_sccs,
                    )
                )
            elif domain == "debian":
                for pattern_group in inject_scc_patterns:
                    pats = [p.lower() for p in pattern_group]
                    for scc in detected.sccs:
                        if any(any(p in cid.lower() for p in pats) for cid in scc.clause_ids):
                            if scc not in selected:
                                selected.append(scc)
                            break

            if inject_profile == "memory_stress" and cycle_source in {"synthetic_long", "both"}:
                for size in synthetic_sizes:
                    selected.append(add_synthetic_cycle(graph, domain, size))

            if not selected:
                used_patterns = {"ruby", "libmono"}
                selected = [
                    s for s in sorted(detected.sccs, key=lambda x: x.size)
                    if 3 <= s.size <= 7
                    and not any(p in cid.lower() for p in used_patterns for cid in s.clause_ids)
                ][:max_sccs]

            domain_sccs[domain] = selected[:max_sccs]
            print(
                f"  [{domain}] Inject mode: selected {len(domain_sccs[domain])} SCCs: "
                f"sizes {[s.size for s in domain_sccs[domain]]}, "
                f"nodes {[sorted(s.clause_ids) for s in domain_sccs[domain]]}"
            )
    else:
        for domain, graph in graphs.items():
            gt_pats = list(GROUND_TRUTH.get(domain, {}).keys()) or None
            sccs = select_sccs(
                graph, min_size=5, max_size=15,
                max_count=max_sccs, gt_patterns=gt_pats,
            )
            domain_sccs[domain] = sccs
            print(f"  [{domain}] Selected {len(sccs)} SCCs: sizes {[s.size for s in sccs]}")

    # ── Run all experiments ──
    all_results = [
        {
            "method": "domain_load",
            "domain": domain,
            "error": reason,
            "skipped": True,
        }
        for domain, reason in skipped_domains.items()
    ]
    out_file = RESULTS_DIR / f"{out_prefix}_{int(time.time())}.json"
    checkpoint_file = out_file.with_name(f"{out_file.stem}.partial.json")
    if all_results:
        save_results(checkpoint_file, all_results)
    total_exps = sum(
        len(sccs) * len(models_to_run) * len(methods_to_run)
        for sccs in domain_sccs.values()
    )
    exp_idx = 0

    for domain, sccs in domain_sccs.items():
        graph = graphs[domain]
        mcgs_cfg = runtime_mcgs_config(domain, args)

        for scc in sccs:
            injected_id = None
            injection_metadata = {}
            evidence_nodes = []
            if inject_mode:
                if inject_profile == "memory_stress" and not allow_synthetic_diagnostic:
                    assert_original_scc_content(graph, scc, domain)
                graph_to_use, injected_id = inject_defect(
                    graph, scc, domain, seed=42, profile=inject_profile,
                    conflict_template=conflict_template,
                    conflict_severity=conflict_severity,
                )
                if inject_profile == "memory_stress":
                    scc = reorder_scc_for_memory_stress(scc, injected_id)
                injected_scan = get_injected_node(graph_to_use, scc)
                if injected_scan != injected_id:
                    raise RuntimeError(
                        f"Injected node scan mismatch: expected {injected_id}, got {injected_scan}"
                    )
                gt_nodes = [injected_id]
                gt_names = [
                    graph_to_use.clauses[injected_id].title
                    if injected_id in graph_to_use.clauses else injected_id
                ]
                injection_metadata = get_injection_metadata(graph_to_use, injected_id)
                evidence_nodes = injection_metadata.get("injected_evidence_nodes", [injected_id])
            else:
                graph_to_use = graph
                gt_nodes = [cid for cid in scc.clause_ids if is_ground_truth_node(cid, domain)]
                gt_names = [graph.clauses[n].title for n in gt_nodes if n in graph.clauses]

            print(f"\n{'─'*70}")
            print(f"  [{domain}] SCC {scc.id} ({scc.size} nodes)")
            print(f"  Ground truth defects: {gt_names or '(none defined)'}")
            if injected_id:
                print(f"  Injected defect node: {injected_id}")
            print(f"{'─'*70}")

            if inject_mode and injected_id:
                orig_gt = GROUND_TRUTH.get(domain, {}).copy()
                orig_exact_gt = set(_GT_EXACT_MATCH)
                GROUND_TRUTH[domain] = {
                    injected_id: f"injected {inject_profile} defect (seed=42)"
                }
                _GT_EXACT_MATCH.add(injected_id.lower())
            else:
                orig_gt = None
                orig_exact_gt = None

            try:
                for model_info in models_to_run:
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
                    if run_naive_method:
                        exp_idx += 1
                        print(f"\n  [{exp_idx}/{total_exps}] {model_name} + Naive on {domain} {scc.size}n...")
                        try:
                            naive_result = await run_naive(
                                llm,
                                model_name,
                                domain,
                                graph_to_use,
                                scc,
                                naive_profile=naive_profile,
                                injected_id=injected_id,
                            )
                            if inject_mode:
                                naive_result["inject_mode"] = True
                                naive_result["injected_node"] = injected_id
                                naive_result["inject_type"] = DOMAIN_INJECT_TYPE.get(domain)
                                naive_result["inject_profile"] = inject_profile
                                naive_result["cycle_source"] = cycle_source
                                naive_result.update(injection_metadata)
                                add_rank_metrics(naive_result, injected_id)
                                add_structural_rank_metrics(naive_result, injection_metadata)
                                add_direct_subgraph_retention_metrics(naive_result, injection_metadata)
                            top3 = naive_result["ranking"][:3]
                            print(f"    Top-3: {[(graph_to_use.clauses.get(c, Clause(id=c, title=c, content='')).title, f'{s:.2f}') for c, s in top3]}")
                            print(f"    Score spread: {naive_result['score_spread']:.3f}")
                            if naive_result.get("ranking_source"):
                                print(
                                    f"    Ranking source: {naive_result['ranking_source']} "
                                    f"(complete={naive_result.get('ranking_complete')})"
                                )
                            if naive_result.get("largest_tie_count", 0) > 1:
                                print(f"    Largest score tie: {naive_result['largest_tie_count']}")
                            if naive_result.get("naive_profile") == "direct_subgraph":
                                print(
                                    f"    Direct subgraph: {naive_result.get('direct_risk_subgraph_size')}/{scc.size} "
                                    f"(compression={naive_result.get('direct_compression_ratio', 0):.0%}, "
                                    f"risk-any={naive_result.get('direct_contains_any_risk_node')})"
                                )
                            print(f"    Top-1 GT hit: {naive_result['top1_hit']}, Top-3 GT hit: {naive_result['top3_hit']}")
                            all_results.append(naive_result)
                            save_results(checkpoint_file, all_results)
                        except Exception as e:
                            print(f"    ERROR: {e}")
                            err_result = {
                                "method": "naive", "model": model_name, "domain": domain,
                                "scc_id": scc.id, "scc_size": scc.size, "error": str(e),
                                "naive_profile": naive_profile,
                            }
                            if inject_mode:
                                err_result.update({"inject_mode": True, "injected_node": injected_id})
                                err_result.update(injection_metadata)
                            all_results.append(err_result)
                            save_results(checkpoint_file, all_results)

                    # ── SA-MCGS ──
                    if run_mcgs_method:
                        exp_idx += 1
                        print(f"\n  [{exp_idx}/{total_exps}] {model_name} + SA-MCGS on {domain} {scc.size}n...")
                        try:
                            mcgs_result = await run_sa_mcgs(llm, model_name, domain, graph_to_use, scc, mcgs_cfg)
                            if inject_mode:
                                mcgs_result["inject_mode"] = True
                                mcgs_result["injected_node"] = injected_id
                                mcgs_result["inject_type"] = DOMAIN_INJECT_TYPE.get(domain)
                                mcgs_result["inject_profile"] = inject_profile
                                mcgs_result["cycle_source"] = cycle_source
                                mcgs_result.update(injection_metadata)
                                add_rank_metrics(mcgs_result, injected_id)
                                add_structural_rank_metrics(mcgs_result, injection_metadata)
                                if include_subgraph_summary:
                                    mcgs_result.update(
                                        build_risk_subgraph_summary(
                                            graph_to_use,
                                            scc,
                                            mcgs_result,
                                            injected_id,
                                            evidence_nodes,
                                            injection_metadata.get("injected_risk_nodes"),
                                            injection_metadata.get("injected_affected_nodes"),
                                        )
                                    )
                                    mcgs_result.update(
                                        build_local_declared_subgraph_summary(
                                            scc,
                                            mcgs_result,
                                            evidence_nodes,
                                            injection_metadata.get("injected_risk_nodes"),
                                            injection_metadata.get("injected_affected_nodes"),
                                        )
                                    )
                                    mcgs_result.update(
                                        build_core_evidence_subgraph_summary(
                                            scc,
                                            mcgs_result,
                                            evidence_nodes,
                                            injection_metadata.get("injected_risk_nodes"),
                                            injection_metadata.get("injected_affected_nodes"),
                                        )
                                    )
                                    mcgs_result.update(
                                        build_trace_convergence_summary(
                                            scc,
                                            mcgs_result,
                                            evidence_nodes,
                                            injection_metadata.get("injected_risk_nodes"),
                                            injection_metadata.get("injected_affected_nodes"),
                                        )
                                    )
                            top3 = mcgs_result["ranking"][:3]
                            print(f"    Top-3: {[(graph_to_use.clauses.get(c, Clause(id=c, title=c, content='')).title, f'{s:.3f}') for c, s in top3]}")
                            print(f"    Score spread: {mcgs_result['score_spread']:.3f}, OC: {mcgs_result['oc_count']}")
                            if include_subgraph_summary and "risk_subgraph_size" in mcgs_result:
                                print(
                                    f"    Risk subgraph: {mcgs_result['risk_subgraph_size']}/{scc.size} "
                                    f"(compression={mcgs_result['compression_ratio']:.0%}, "
                                    f"GT={mcgs_result['contains_injected_node']})"
                                )
                            if include_subgraph_summary and "local_declared_risk_subgraph_size" in mcgs_result:
                                print(
                                    f"    Local-declared subgraph: "
                                    f"{mcgs_result['local_declared_risk_subgraph_size']}/{scc.size} "
                                    f"(compression={mcgs_result['local_declared_compression_ratio']:.0%}, "
                                    f"risk-any={mcgs_result['local_declared_contains_any_risk_node']})"
                                )
                            if include_subgraph_summary and "core_evidence_risk_subgraph_size" in mcgs_result:
                                print(
                                    f"    Core evidence subgraph: "
                                    f"{mcgs_result['core_evidence_risk_subgraph_size']}/{scc.size} "
                                    f"(compression={mcgs_result['core_evidence_compression_ratio']:.0%}, "
                                    f"risk-any={mcgs_result['core_evidence_contains_any_risk_node']})"
                                )
                            if include_subgraph_summary and mcgs_result.get("convergence_trace"):
                                print(
                                    f"    Convergence: first-any="
                                    f"{mcgs_result.get('first_subgraph_risk_any_rollout')}, "
                                    f"first-all={mcgs_result.get('first_subgraph_risk_all_rollout')}, "
                                    f"final-cov={mcgs_result.get('convergence_final_risk_coverage')}"
                                )
                            print(f"    Top-1 GT hit: {mcgs_result['top1_hit']}, Top-3 GT hit: {mcgs_result['top3_hit']}")
                            all_results.append(mcgs_result)
                            save_results(checkpoint_file, all_results)
                        except Exception as e:
                            print(f"    ERROR: {e}")
                            err_result = {
                                "method": "sa-mcgs", "model": model_name, "domain": domain,
                                "scc_id": scc.id, "scc_size": scc.size, "error": str(e),
                            }
                            if inject_mode:
                                err_result.update({"inject_mode": True, "injected_node": injected_id})
                                err_result.update(injection_metadata)
                            all_results.append(err_result)
                            save_results(checkpoint_file, all_results)

                    await llm.close()
            finally:
                if orig_gt is not None:
                    GROUND_TRUTH[domain] = orig_gt
                if orig_exact_gt is not None:
                    _GT_EXACT_MATCH.clear()
                    _GT_EXACT_MATCH.update(orig_exact_gt)

    # ── Save Results ──
    save_results(out_file, all_results)
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

    for model_info in models_to_run:
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
    parser = argparse.ArgumentParser(description="SA-MCGS Battle: Naive vs SA-MCGS")
    parser.add_argument(
        "--smoke", action="store_true",
        help="Smoke mode: 1 domain (debian) x 1 SCC x 1 model (deepseek-v3)",
    )
    parser.add_argument(
        "--domains", nargs="+", choices=["debian", "wikipedia", "sec_ex21", "bgb", "cuad"],
        help="Subset of domains to run (default: all 3)",
    )
    parser.add_argument(
        "--models", nargs="+",
        help="Subset of model names to run (e.g. deepseek-v3 gpt-4o)",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=["naive", "sa-mcgs"],
        default=["naive", "sa-mcgs"],
        help="Methods to run. Use '--methods naive' to rerun only the one-shot baseline.",
    )
    parser.add_argument(
        "--max-sccs", type=int, default=2,
        help="Max SCCs per domain (default: 2)",
    )
    parser.add_argument(
        "--inject", action="store_true",
        help=(
            "Injection mode: inject a synthetic defect into one node per SCC "
            "and use that node as ground truth. Results saved as battle_inject_*."
        ),
    )
    parser.add_argument(
        "--inject-profile",
        choices=sorted(SUPPORTED_INJECT_PROFILES),
        default="explicit",
        help=(
            "Injection profile. explicit preserves the original UDIP sanity check; "
            "memory_stress injects a simple structural conflict into existing SCC nodes."
        ),
    )
    parser.add_argument(
        "--cycle-source",
        choices=["real_long", "synthetic_long", "both"],
        default="real_long",
        help="SCC source for memory-stress injection.",
    )
    parser.add_argument(
        "--real-min-size",
        type=int,
        default=5,
        help="Minimum real SCC size for memory_stress formal runs.",
    )
    parser.add_argument(
        "--real-max-size",
        type=int,
        default=24,
        help="Maximum real SCC size for memory_stress formal runs.",
    )
    parser.add_argument(
        "--domain-size-ranges",
        nargs="*",
        default=[],
        help=(
            "Optional per-domain SCC ranges, e.g. "
            "'cuad:12-26 wikipedia:34 bgb:11-25'. Overrides --real-min/max "
            "for listed domains."
        ),
    )
    parser.add_argument(
        "--allow-synthetic-diagnostic",
        action="store_true",
        help=(
            "Allow synthetic_long/both memory_stress runs. These are diagnostic only "
            "and must not be reported as formal results."
        ),
    )
    parser.add_argument(
        "--conflict-template",
        choices=sorted(SUPPORTED_MEMORY_CONFLICT_TEMPLATES),
        default=DEFAULT_MEMORY_CONFLICT_TEMPLATE,
        help=(
            "Structural conflict family for memory_stress injection. "
            "Use direct_mutex as the obvious baseline; later templates require "
            "multi-node evidence."
        ),
    )
    parser.add_argument(
        "--conflict-severity",
        choices=sorted(SUPPORTED_MEMORY_CONFLICT_SEVERITIES),
        default=DEFAULT_MEMORY_CONFLICT_SEVERITY,
        help="Consequence severity for memory_stress structural injections.",
    )
    parser.add_argument(
        "--synthetic-sizes",
        nargs="+",
        type=int,
        default=[16, 24],
        help="Synthetic long-cycle sizes to append when --cycle-source uses synthetic cycles.",
    )
    parser.add_argument(
        "--include-subgraph-summary",
        action="store_true",
        help="Record SA-MCGS compact risk-subgraph metrics.",
    )
    parser.add_argument(
        "--mcgs-concurrency",
        type=int,
        help="Override SA-MCGS internal LLM concurrency for this run.",
    )
    parser.add_argument(
        "--mcgs-budget",
        type=int,
        help="Override SA-MCGS rollout budget for all domains.",
    )
    parser.add_argument(
        "--mcgs-trace",
        action="store_true",
        help="Record per-rollout SA-MCGS trace and prefix convergence metrics.",
    )
    parser.add_argument(
        "--mcgs-evidence-mode",
        choices=["relation_first", "pair_memory", "off"],
        default="relation_first",
        help=(
            "SA-MCGS evidence mode. relation_first uses AMAF/RAVE-style "
            "relation/path evidence to bias future rollouts; pair_memory keeps "
            "the older final-subgraph pair memory only; off disables both "
            "relation-first probes and pair-memory closure for ablation."
        ),
    )
    parser.add_argument(
        "--mcgs-compression-profile",
        choices=sorted(MCGS_COMPRESSION_PROFILES),
        default="current",
        help=(
            "Final SA-MCGS core compression profile. current preserves existing "
            "settings; conservative/balanced/aggressive tighten the blind core "
            "subgraph while keeping the wider context_evidence_* explanation."
        ),
    )
    parser.add_argument("--mcgs-subgraph-max-ratio", type=float)
    parser.add_argument("--mcgs-subgraph-min-nodes", type=int)
    parser.add_argument("--mcgs-core-min-relative-score", type=float)
    parser.add_argument("--mcgs-core-tail-relative-score", type=float)
    parser.add_argument("--mcgs-core-stop-gap", type=float)
    parser.add_argument("--mcgs-core-min-score", type=float)
    parser.add_argument("--mcgs-critical-pair-core-min-score", type=float)
    parser.add_argument("--mcgs-critical-pair-core-max-edge-ratio", type=float)
    parser.add_argument("--mcgs-critical-pair-core-max-edges", type=int)
    parser.add_argument(
        "--wiki-mcgs-budget",
        type=int,
        help="Override SA-MCGS rollout budget for Wikipedia only.",
    )
    parser.add_argument(
        "--naive-profile",
        choices=sorted(NAIVE_PROFILES),
        default="ranked",
        help=(
            "Naive one-shot baseline profile. ranked asks the model for risk-factor "
            "distribution plus a complete no-tie global ranking; direct_subgraph asks "
            "the model to directly declare a minimal risk subgraph as well; basic "
            "preserves the old score-only baseline."
        ),
    )
    parser.add_argument(
        "--run-tag",
        help="Optional safe tag appended to result filenames for parallel grid runs.",
    )
    args = parser.parse_args()

    asyncio.run(main(args))

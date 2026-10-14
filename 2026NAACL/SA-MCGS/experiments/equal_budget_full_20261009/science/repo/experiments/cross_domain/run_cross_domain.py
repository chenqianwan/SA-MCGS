"""Cross-domain SA-MCGS experiment: Debian + Wikipedia + SEC EX-21

Runs AlphaGoMCGS on 2-3 SCCs per domain using DeepSeek-chat via xhub proxy.
Each domain has a custom prompt builder and pluggable pruning strategy.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import os
import random
import re
import sys
import time
import urllib.request
import urllib.parse
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.clause import Clause, ClauseType
from src.models.graph import DependencyGraph, DependencyType, Edge, SCCInfo
from src.modules.tarjan import TarjanSCCDetector
from src.modules.alphago_mcgs import AlphaGoMCGS
from src.llm.openai_client import OpenAIClient

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

XHUB_BASE_URL = "https://api3.xhub.chat/v1"
DEBIAN_DATA_DIR = Path(__file__).parent / "20241027.cards.debian_pkgs"
DEBIAN_DEPS_FILE = DEBIAN_DATA_DIR / "20241027.debian_pkgs.deps.gz"
DEBIAN_PACKAGES_FILE = DEBIAN_DATA_DIR / "20241027.debian_pkgs.packages.txt.gz"
WIKIPEDIA_MAX_CYCLES = int(os.environ.get("SA_MCGS_WIKIPEDIA_MAX_CYCLES", "48"))
WIKIPEDIA_MIN_CYCLE_LEN = int(os.environ.get("SA_MCGS_WIKIPEDIA_MIN_CYCLE_LEN", "5"))
WIKIPEDIA_MAX_CYCLE_LEN = int(os.environ.get("SA_MCGS_WIKIPEDIA_MAX_CYCLE_LEN", "60"))

LLM_CONFIG = {
    "provider": "openai",
    "model": "deepseek-chat",
    "base_url": XHUB_BASE_URL,
    "api_key_env": "XHUB_API_KEY",
    "timeout": 300,
}

MCGS_CONFIG = {
    "alphago_mcgs": {
        "budget": 30,
        "window_size": 4,
        "concurrency": 4,
        "ucb_exploration_weight": 1.414,
        "ucb_exploration_init": 2.5,
        "temperature": 0.4,
        "max_tokens": 2048,
        "tt_max_reuse": 3,
    },
    "detection": {"alpha": 0.1, "min_rollouts": 6},
}

# ─── Domain-specific prompt builders (monkey-patched) ─────────────────

def _debian_prompt(self, window: list[str]) -> str:
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


def _wikipedia_prompt(self, window: list[str]) -> str:
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
        "1.0=clearly misplaced/causing the cycle). Identify the specific "
        "problematic subcategory links.\n\n"
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


def _sec_prompt(self, window: list[str]) -> str:
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


# ─── Data loaders ────────────────────────────────────────────────────

def _read_debian_package_records(packages_file: Path) -> dict[str, dict[str, str]]:
    """Read original Debian Packages.gz stanzas keyed by package name."""
    if not packages_file.exists():
        raise FileNotFoundError(
            f"Original Debian Packages.gz-derived file not found: {packages_file}. "
            "Run experiments/cross_domain/20241027.cards.debian_pkgs/build_dataset.fish "
            "or place 20241027.debian_pkgs.packages.txt.gz there before formal runs."
        )

    records: dict[str, dict[str, str]] = {}
    current: dict[str, str] = {}
    current_key: str | None = None

    def flush() -> None:
        if current.get("Package"):
            records[current["Package"]] = dict(current)

    with gzip.open(packages_file, "rt", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            if not line:
                flush()
                current = {}
                current_key = None
                continue
            if line.startswith(" ") and current_key:
                continuation = line[1:]
                current[current_key] = current.get(current_key, "") + "\n" + continuation
                continue
            if ": " not in line:
                continue
            key, val = line.split(": ", 1)
            current[key] = val
            current_key = key
    flush()
    return records


def _debian_record_content(record: dict[str, str]) -> str:
    fields = [
        "Package", "Version", "Architecture", "Source", "Depends", "Pre-Depends",
        "Breaks", "Conflicts", "Replaces", "Provides", "Description",
    ]
    return "\n".join(f"{field}: {record[field]}" for field in fields if record.get(field))

def load_debian_graph() -> DependencyGraph:
    """Build DependencyGraph from Debian CARDS .deps.gz file."""
    deps_file = DEBIAN_DEPS_FILE
    if not deps_file.exists():
        raise FileNotFoundError(f"Debian CARDS data not found at {deps_file}")
    package_records = _read_debian_package_records(DEBIAN_PACKAGES_FILE)

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
                        dependency_type=DependencyType.REFERENCES,
                        weight=0.8,
                    ))

    missing_records = 0
    for pkg in sorted(all_pkgs):
        record = package_records.get(pkg)
        if not record:
            missing_records += 1
            continue
        clauses[pkg] = Clause(
            id=pkg, title=pkg,
            content=_debian_record_content(record),
            clause_type=ClauseType.OTHER,
            metadata={"source": "debian_packages_gz", "original_record": True},
        )

    valid_edges = [e for e in edges if e.source in clauses and e.target in clauses]
    print(
        f"  [Debian] {len(clauses)} packages with original stanzas, "
        f"{len(valid_edges)} edges; skipped {missing_records} nodes without original records"
    )
    return DependencyGraph(clauses=clauses, edges=valid_edges)


def _extract_revision_wikitext(page: dict) -> str:
    revisions = page.get("revisions") or []
    if not revisions:
        return ""
    revision = revisions[0]
    slots = revision.get("slots")
    if isinstance(slots, dict):
        main = slots.get("main", {})
        if isinstance(main, dict):
            return (main.get("*") or main.get("content") or "").strip()
    return (revision.get("*") or revision.get("content") or "").strip()


def _fetch_wikipedia_category_texts(categories: list[str]) -> dict[str, str]:
    """Fetch original Category page raw wikitext from MediaWiki."""
    texts: dict[str, str] = {}
    titles = [f"Category:{cat}" for cat in categories]
    for i in range(0, len(titles), 40):
        batch = titles[i:i + 40]
        query = urllib.parse.urlencode({
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "format": "json",
            "redirects": "1",
            "titles": "|".join(batch),
        })
        url = f"https://en.wikipedia.org/w/api.php?{query}"
        req = urllib.request.Request(url, headers={'User-Agent': 'SA-MCGS-Research/1.0'})
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read().decode())
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title", "")
            if not title.startswith("Category:"):
                continue
            cat = title.removeprefix("Category:")
            wikitext = _extract_revision_wikitext(page)
            if wikitext:
                texts[cat] = wikitext
        time.sleep(0.2)
    return texts


def _select_wikipedia_cycles(cycles: list[list[str]], max_select: int) -> list[list[str]]:
    """Choose a size-diverse subset of real category cycles."""
    if len(cycles) <= max_select:
        return cycles

    selected: list[list[str]] = []
    anchors = [5, 8, 12, 16, 20, 24]
    for anchor in anchors:
        if len(selected) >= max_select:
            break
        eligible = [c for c in cycles if c not in selected]
        if not eligible:
            break
        selected.append(min(eligible, key=lambda c: (abs(len(c) - anchor), -len(c), c)))

    for cycle in sorted(cycles, key=lambda c: (-len(c), c)):
        if len(selected) >= max_select:
            break
        if cycle not in selected:
            selected.append(cycle)

    return selected


def load_wikipedia_graph() -> DependencyGraph:
    """Build DependencyGraph from Wikipedia category cycle data via API."""
    print("  [Wikipedia] Fetching category cycles from Wikipedia API...")

    all_cycles = []
    for page_num in range(1, 5):
        url = (
            f"https://en.wikipedia.org/w/api.php?action=parse"
            f"&page=User:SDZeroBot/Category%20cycles/{page_num}"
            f"&prop=wikitext&format=json"
        )
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'SA-MCGS-Research/1.0'})
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

    target_cycles = [
        c for c in all_cycles
        if WIKIPEDIA_MIN_CYCLE_LEN <= len(c) <= WIKIPEDIA_MAX_CYCLE_LEN
    ]
    if not target_cycles:
        target_cycles = [c for c in all_cycles if len(c) >= 3]

    selected = _select_wikipedia_cycles(target_cycles, WIKIPEDIA_MAX_CYCLES)
    print(f"  [Wikipedia] {len(all_cycles)} total cycles, selected {len(selected)} for experiment")
    category_names = sorted({cat for cycle in selected for cat in cycle})
    category_texts = _fetch_wikipedia_category_texts(category_names)
    missing_texts = sorted(set(category_names) - set(category_texts))
    if missing_texts:
        print(
            f"  [Wikipedia] WARNING: {len(missing_texts)} category pages have no "
            "raw wikitext; edges touching them will be skipped"
        )

    clauses: dict[str, Clause] = {}
    edges: list[Edge] = []

    for cycle in selected:
        for cat in cycle:
            cid = cat.replace(' ', '_')
            if cid in clauses:
                continue
            page_text = category_texts.get(cat)
            if not page_text:
                continue
            clauses[cid] = Clause(
                id=cid, title=cat,
                content=page_text,
                clause_type=ClauseType.OTHER,
                metadata={
                    "source": "wikipedia_category_raw_wikitext",
                    "original_record": True,
                    "page_title": f"Category:{cat}",
                },
            )

    for cycle in selected:
        for i, cat in enumerate(cycle):
            cid = cat.replace(' ', '_')
            next_cat = cycle[(i + 1) % len(cycle)].replace(' ', '_')
            if cid in clauses and next_cat in clauses:
                edges.append(Edge(
                    source=cid, target=next_cat,
                    dependency_type=DependencyType.REFERENCES,
                    weight=0.8,
                    reasoning=f"{cat} is subcategory of {cycle[(i+1) % len(cycle)]}",
                ))

    print(f"  [Wikipedia] {len(clauses)} categories with raw wikitext, {len(edges)} edges")
    return DependencyGraph(clauses=clauses, edges=edges)


def load_sec_graph() -> DependencyGraph:
    """Build DependencyGraph from OpenSanctions SEC EX-21 ownership data."""
    data_file = Path(__file__).parent / "finance_blockchain" / "corpwatch" / "entities.ftm.json.gz"
    if not data_file.exists():
        data_file = Path(__file__).parent / "finance_blockchain" / "corpwatch" / "entities.ftm.json"
    if not data_file.exists():
        raise FileNotFoundError(
            "SEC EX-21 source entity file not found. Formal runs require the original "
            f"OpenSanctions/CorpWatch source at {data_file} or the .json.gz variant."
        )
    actual_file = data_file

    print(f"  [SEC EX-21] Loading from {actual_file.name}...")

    companies: dict[str, dict] = {}
    ownership_edges: list[tuple[str, str]] = []

    with open(actual_file, "rb") as probe:
        is_gzip = probe.read(2) == b"\x1f\x8b"
    opener = gzip.open if is_gzip else open
    with opener(actual_file, 'rt', encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                ent = json.loads(line.strip())
                schema = ent.get('schema')
                if schema == 'Company':
                    companies[ent['id']] = {
                        'name': ent.get('caption', ent['id']),
                        'country': ent.get('properties', {}).get('country', ['unknown'])[0],
                        'properties': ent.get('properties', {}),
                    }
                elif schema == 'Ownership':
                    props = ent.get('properties', {})
                    for owner in props.get('owner', []):
                        for asset in props.get('asset', []):
                            if owner != asset:
                                ownership_edges.append((owner, asset))
            except:
                continue

    print(f"  [SEC EX-21] {len(companies)} companies, {len(ownership_edges)} ownership edges")

    graph_adj = defaultdict(set)
    all_nodes = set()
    for src, dst in ownership_edges:
        graph_adj[src].add(dst)
        all_nodes.add(src)
        all_nodes.add(dst)

    # Tarjan for SCC detection (fast, to select SCCs)
    random.seed(42)
    idx_counter = [0]
    stack = []
    on_stack = set()
    idx_map = {}
    low_map = {}
    sccs_raw = []

    for start in sorted(all_nodes):
        if start in idx_map:
            continue
        work = [(start, iter(sorted(graph_adj.get(start, set()))), True)]
        idx_map[start] = low_map[start] = idx_counter[0]
        idx_counter[0] += 1
        stack.append(start)
        on_stack.add(start)

        while work:
            v, nbrs, _ = work[-1]
            found = False
            for w in nbrs:
                if w not in idx_map:
                    idx_map[w] = low_map[w] = idx_counter[0]
                    idx_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(sorted(graph_adj.get(w, set()))), True))
                    found = True
                    break
                elif w in on_stack:
                    low_map[v] = min(low_map[v], idx_map[w])
            if not found:
                if low_map[v] == idx_map[v]:
                    scc = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        scc.append(w)
                        if w == v:
                            break
                    sccs_raw.append(scc)
                work.pop()
                if work:
                    low_map[work[-1][0]] = min(low_map[work[-1][0]], low_map[v])

    target_sccs = sorted(
        [s for s in sccs_raw if 5 <= len(s) <= 24],
        key=lambda s: (-len(s), sorted(s)),
    )
    if len(target_sccs) > 8:
        target_sccs = target_sccs[:8]

    print(f"  [SEC EX-21] Selected {len(target_sccs)} SCCs (size 5-24)")

    clauses: dict[str, Clause] = {}
    edges: list[Edge] = []
    needed_nodes = set()
    for scc in target_sccs:
        needed_nodes.update(scc)

    missing_records = 0
    for node_id in needed_nodes:
        info = companies.get(node_id, {'name': node_id, 'country': 'unknown'})
        if node_id not in companies:
            missing_records += 1
            continue
        properties = info.get("properties", {})
        source_fields = []
        for key in sorted(properties):
            values = properties.get(key)
            if isinstance(values, list) and values:
                source_fields.append(f"{key}: {'; '.join(str(v) for v in values)}")
        if not source_fields:
            source_fields = [
                f"name: {info['name']}",
                f"country: {info['country']}",
            ]
        clauses[node_id] = Clause(
            id=node_id, title=info['name'],
            content="\n".join(source_fields),
            clause_type=ClauseType.OTHER,
            metadata={"source": "opensanctions_entity_properties", "original_record": True},
        )

    for src, dst in ownership_edges:
        if src in needed_nodes and dst in needed_nodes:
            edges.append(Edge(
                source=src, target=dst,
                dependency_type=DependencyType.REFERENCES,
                weight=0.8,
                reasoning=f"{companies.get(src, {}).get('name', src)} owns {companies.get(dst, {}).get('name', dst)}",
            ))

    print(
        f"  [SEC EX-21] Graph: {len(clauses)} companies with source properties, "
        f"{len(edges)} edges; skipped {missing_records} nodes without company records"
    )
    return DependencyGraph(clauses=clauses, edges=edges)


# ─── Main experiment runner ──────────────────────────────────────────

async def run_domain_experiment(
    domain_name: str,
    graph: DependencyGraph,
    prompt_fn,
    max_sccs: int = 3,
) -> dict:
    """Run AlphaGoMCGS on SCCs from a domain graph."""
    print(f"\n{'='*60}")
    print(f"  Domain: {domain_name}")
    print(f"{'='*60}")

    detector = TarjanSCCDetector()
    graph = detector.detect(graph)

    print(f"  SCCs found: {len(graph.sccs)}")
    scc_sizes = sorted([s.size for s in graph.sccs], reverse=True)
    print(f"  SCC sizes (top 20): {scc_sizes[:20]}")
    print(f"  DAG nodes: {len(graph.dag_nodes)}")

    target_sccs = [s for s in graph.sccs if 5 <= s.size <= 15]
    if not target_sccs:
        target_sccs = [s for s in graph.sccs if s.size >= 3]
    target_sccs = sorted(target_sccs, key=lambda s: s.size)[:max_sccs]

    if not target_sccs:
        print(f"  WARNING: No suitable SCCs found for {domain_name}")
        return {"domain": domain_name, "error": "no_suitable_sccs"}

    print(f"  Running MCGS on {len(target_sccs)} SCCs: sizes {[s.size for s in target_sccs]}")

    llm = OpenAIClient(LLM_CONFIG)
    results = {"domain": domain_name, "llm": LLM_CONFIG["model"], "api": "xhub", "sccs": []}

    for scc in target_sccs:
        print(f"\n  --- SCC {scc.id} ({scc.size} nodes) ---")
        print(f"  Nodes: {scc.clause_ids[:8]}{'...' if scc.size > 8 else ''}")

        mcgs = AlphaGoMCGS(llm_client=llm, config=MCGS_CONFIG)
        mcgs._build_focused_prompt = lambda w, _self=mcgs: prompt_fn(_self, w)

        try:
            scc_result = await mcgs.search(graph, scc)
            scc_result["scc_id"] = scc.id
            scc_result["scc_size"] = scc.size
            scc_result["scc_clause_ids"] = scc.clause_ids
            scc_result["node_names"] = {
                cid: graph.clauses[cid].title
                for cid in scc.clause_ids if cid in graph.clauses
            }

            print(f"  Results:")
            print(f"    LLM calls: {scc_result['llm_calls']}")
            print(f"    TT hits: {scc_result['tt_hits']}")
            print(f"    OC detected: {scc_result['oc_detected_clauses']}")
            print(f"    Top 3 by risk:")
            for cid, score in scc_result['ranking_by_risk'][:3]:
                name = graph.clauses.get(cid, Clause(id=cid, title=cid, content="")).title
                print(f"      {name}: {score:.3f}")

            results["sccs"].append(scc_result)

        except Exception as e:
            print(f"  ERROR on SCC {scc.id}: {e}")
            import traceback
            traceback.print_exc()
            results["sccs"].append({"scc_id": scc.id, "error": str(e)})

    await llm.close()
    return results


async def main():
    api_key = os.environ.get("XHUB_API_KEY", "")
    if not api_key:
        api_key = input("Enter XHUB API key: ").strip()
        os.environ["XHUB_API_KEY"] = api_key
    if not api_key:
        raise RuntimeError("XHUB_API_KEY is required")

    print("=" * 60)
    print("  SA-MCGS Cross-Domain Preliminary Experiment (First Run)")
    print(f"  LLM: {LLM_CONFIG['model']} via xhub | Budget=30 | 3 Domains")
    print("=" * 60)

    all_results = {}

    # ── Domain 1: Debian ──
    try:
        print("\n[1/3] Loading Debian package data...")
        debian_graph = load_debian_graph()
        debian_results = await run_domain_experiment(
            "Debian Package Dependencies", debian_graph, _debian_prompt, max_sccs=3
        )
        all_results["debian"] = debian_results
    except Exception as e:
        print(f"  Debian FAILED: {e}")
        import traceback; traceback.print_exc()
        all_results["debian"] = {"error": str(e)}

    # ── Domain 2: Wikipedia ──
    try:
        print("\n[2/3] Loading Wikipedia category data...")
        wiki_graph = load_wikipedia_graph()
        wiki_results = await run_domain_experiment(
            "Wikipedia Category Hierarchy", wiki_graph, _wikipedia_prompt, max_sccs=3
        )
        all_results["wikipedia"] = wiki_results
    except Exception as e:
        print(f"  Wikipedia FAILED: {e}")
        import traceback; traceback.print_exc()
        all_results["wikipedia"] = {"error": str(e)}

    # ── Domain 3: SEC EX-21 ──
    try:
        print("\n[3/3] Loading SEC EX-21 corporate ownership data...")
        sec_graph = load_sec_graph()
        sec_results = await run_domain_experiment(
            "SEC EX-21 Corporate Ownership", sec_graph, _sec_prompt, max_sccs=3
        )
        all_results["sec_ex21"] = sec_results
    except Exception as e:
        print(f"  SEC EX-21 FAILED: {e}")
        import traceback; traceback.print_exc()
        all_results["sec_ex21"] = {"error": str(e)}

    # ── Save Results ──
    output_file = RESULTS_DIR / f"cross_domain_preliminary_{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n{'='*60}")
    print(f"  Results saved to: {output_file}")
    print(f"{'='*60}")

    # ── Print Summary ──
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for domain, res in all_results.items():
        if "error" in res and isinstance(res.get("error"), str):
            print(f"\n  [{domain}] ERROR: {res['error']}")
            continue
        sccs = res.get("sccs", [])
        print(f"\n  [{domain}] {len(sccs)} SCCs analyzed")
        for scc_res in sccs:
            if "error" in scc_res:
                print(f"    SCC {scc_res.get('scc_id','?')}: ERROR {scc_res['error']}")
                continue
            scc_id = scc_res.get("scc_id", "?")
            n = scc_res.get("scc_size", "?")
            detected = scc_res.get("oc_detected_clauses", [])
            top_risk = scc_res.get("ranking_by_risk", [])[:3]
            names = scc_res.get("node_names", {})
            print(f"    SCC {scc_id} ({n} nodes):")
            print(f"      OC detected: {len(detected)} nodes — {[names.get(d, d) for d in detected]}")
            print(f"      Top risk:")
            for cid, score in top_risk:
                print(f"        {names.get(cid, cid)}: {score:.3f}")


if __name__ == "__main__":
    asyncio.run(main())

"""Replicate graph-grpo-lex pipeline on CUAD contracts.

Faithfully reproduces the clause-to-minigraph extraction pipeline from
Dechtiar et al. (IEEE ICDM Workshop 2025), using the exact V4 prompt
template and identical API call structure.

Usage:
    python scripts/replicate_grpo_lex.py --num-contracts 5 --model gpt-4o
    python scripts/replicate_grpo_lex.py --skip-llm  # re-run assembly only
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

import networkx as nx
import typer
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.data.cuad_loader import CUADLoader  # noqa: E402
from src.models.graph import DependencyType, Edge, SCCInfo  # noqa: E402

app = typer.Typer(pretty_exceptions_enable=False)

# ── V4 Prompt (exact copy from graph-grpo-lex) ──────────────────────────────

SYSTEM_PROMPT = (
    "You will receive the full details of ONE clause: {id, text, title, level}."
)

PROMPT_INSTRUCTION = """\
Your task is to act as a legal graph extractor. From this single clause, create a self-contained set of nodes and edges that are explicitly supported by the text. Follow the reasoning process, rules, and clarifications below.

Output ONLY a single, strict JSON object with this structure:

{
 "contract_id": "...",
 "nodes": [ ... ],
 "edges": [ ... ]
}

──────────────────────────
REASONING PROCESS
──────────────────────────
1.  **Isolate Core Text:** First, mentally separate the core contractual prose from any 'noise' like Tables of Contents, redaction headers, or formatting artifacts. Your analysis should ONLY focus on the contractual prose.
2.  **Create Primary Node:** Create the `CLAUSE` node for the clause you were given.
3.  **Infer and Create Parent Node:** Analyze the clause `id` to infer the parent clause ID. Create the parent `CLAUSE` node and the IS_PART_OF edge to it.
4.  **Scan and Create Nodes:** Read the core text to identify all other entities (Referenced Clauses, Defined Terms, Parties, Values) and create their corresponding nodes according to the rules below.
5.  **Create Edges:** Link the primary clause node to all other created nodes using the appropriate edge types.

──────────────────────────
NODE RULES
──────────────────────────
- CLAUSE:
  { "id": "<clause-id>", "node_type": "CLAUSE", "title": "<title>", "level": <int> }
  Rule: Create a node for the input clause, its inferred parent, and any clauses it explicitly references.

- DEFINED_TERM:
  { "id": "term:<Canonical Term>", "node_type": "DEFINED_TERM", "name": "<Canonical Term>" }
  Rule: Create for terms with special meaning (quoted, ALL CAPS, or explicitly defined). Canonicalize the name (e.g., "this Agreement" becomes "Agreement"; use Title Case).

- PARTY:
  { "id": "party:<Party Name>", "node_type": "PARTY", "name": "<Party Name>" }
  Rule: Only for legal entities or defined roles (e.g., "Licensor", "the Supplier"). Canonicalize by removing articles ("the", "a").

- VALUE:
  { "id": "value:<literal text>", "node_type": "VALUE", "unit": "Currency|Percentage|Days|Months|Years", "text": "<literal text>" }
  Rule: Extract specific amounts, durations, etc.

──────────────────────────
EDGE RULES
──────────────────────────
Format: { "src":"<id>", "tgt":"<id>", "type":"<EDGE_TYPE>" }

- IS_PART_OF: CLAUSE → parent CLAUSE
  Rule: Infer parent from child's ID. Numeric: "3.4" → "3"; "14.2" → "ARTICLE 14". Non-numeric: For an ID like "(h)", look for context in the text like "Section 3.2(h)" to infer the parent is "3.2".

- DEFINES: CLAUSE → DEFINED_TERM
  Rule: Use when the clause introduces a definition ("X shall mean...", "(the 'X')").

- USES: CLAUSE → DEFINED_TERM
  Rule: Use when a defined term is mentioned but not defined in this clause. Be thorough and include all capitalized, multi-word legal concepts (e.g., "Material Change", "Product Prices").

- REFERENCES: CLAUSE → CLAUSE
  Rule: Use for explicit cross-references like "Section 3.2" or "Article 10".

- MENTIONS_PARTY: CLAUSE → PARTY
  Rule: Create an edge for every mentioned party.

- CONTAINS: CLAUSE → VALUE
  Rule: Create an edge for every extracted value.

──────────────────────────
CRITICAL CLARIFICATIONS
──────────────────────────
1.  **Reference Typing is Key:** Any cross-reference to another part of the document (e.g., "Article 5", "Exhibit B") MUST be created as a `CLAUSE` node. It is NEVER a `DEFINED_TERM`.
2.  **No Duplicates:** Output each unique node and edge only once. If no nodes or edges can be created, output empty arrays.
3.  **Sort for Consistency:** Sort nodes by ID and edges by `src`, `type`, then `tgt`."""

# ── Default contracts (same 5 used by graph-grpo-lex) ───────────────────────

DEFAULT_CONTRACTS = [
    "NETGEAR,INC_04_21_2003-EX-10.16-DISTRIBUTOR AGREEMENT.txt",
    "ScansourceInc_20190822_10-K_EX-10.38_11793958_EX-10.38_Distributor Agreement2.txt",
    "StaarSurgicalCompany_20180801_10-Q_EX-10.37_11289449_EX-10.37_Distributor Agreement.txt",
    "WORLDWIDESTRATEGIESINC_11_02_2005-EX-10-RESELLER AGREEMENT.txt",
    "BELLICUMPHARMACEUTICALS,INC_05_07_2019-EX-10.1-Supply Agreement.txt",
    "Array BioPharma Inc. - LICENSE, DEVELOPMENT AND COMMERCIALIZATION AGREEMENT.txt",
    "BELLRINGBRANDS,INC_02_07_2020-EX-10.18-MASTER SUPPLY AGREEMENT.txt",
    "CytodynInc_20200109_10-Q_EX-10.5_11941634_EX-10.5_License Agreement.txt",
    "Apollo Endosurgery - Manufacturing and Supply Agreement.txt",
    "ArconicRolledProductsCorp_20191217_10-12B_EX-2.7_11923804_EX-2.7_Trademark License Agreement.txt",
    "ArtaraTherapeuticsInc_20200110_8-K_EX-10.5_11943350_EX-10.5_License Agreement.txt",
    "CHANGEPOINTCORP_03_08_2000-EX-10.6-LICENSE AND HOSTING AGREEMENT.txt",
    "ChinaRealEstateInformationCorp_20090929_F-1_EX-10.32_4771615_EX-10.32_Content License Agreement.txt",
    "AimmuneTherapeuticsInc_20200205_8-K_EX-10.3_11967170_EX-10.3_Development Agreement.txt",
    "CoherusBiosciencesInc_20200227_10-K_EX-10.29_12021376_EX-10.29_Development Agreement.txt",
    "MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING AGREEMENT.txt",
    "CERES,INC_01_25_2012-EX-10.20-Collaboration Agreement.txt",
    "GOOSEHEADINSURANCE,INC_04_02_2018-EX-10.6-Franchise Agreement.txt",
    "PhasebioPharmaceuticalsInc_20200330_10-K_EX-10.21_12086810_EX-10.21_Development Agreement.txt",
    "VerizonAbsLlc_20200123_8-K_EX-10.4_11952335_EX-10.4_Service Agreement.txt",
    "RevolutionMedicinesInc_20200117_S-1_EX-10.1_11948417_EX-10.1_Development Agreement.txt",
    "MRSFIELDSORIGINALCOOKIESINC_01_29_1998-EX-10-FRANCHISE AGREEMENT.txt",
    "HarpoonTherapeuticsInc_20200312_10-K_EX-10.18_12051356_EX-10.18_Development Agreement.txt",
    "AzulSa_20170303_F-1A_EX-10.3_9943903_EX-10.3_Maintenance Agreement1.txt",
    "UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement.txt",
    "Monsanto Company - SECOND A_R EXCLUSIVE AGENCY AND MARKETING AGREEMENT .txt",
    "BERKELEYLIGHTS,INC_06_26_2020-EX-10.12-COLLABORATION AGREEMENT.txt",
    "INNOVIVA,INC_08_07_2014-EX-10.1-COLLABORATION AGREEMENT.txt",
    "Microgenics Corporation - Collaborative Development and Commercialization Agreement.txt",
    "FOUNDATIONMEDICINE,INC_02_02_2015-EX-10.2-Collaboration Agreement.txt",
    # ── Deal Package contracts (cross-contract analysis) ──
    "NETGEAR,INC_04_21_2003-EX-10.16-AMENDMENT TO THE DISTRIBUTOR AGREEMENT BETWEEN INGRAM MICRO AND NETGEAR.txt",
    "NETGEAR,INC_04_21_2003-EX-10.16- AMENDMENT #2 TO THE DISTRIBUTION AGREEMENT.txt",
    "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
    "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.8_11951679_EX-10.8_Service Agreement.txt",
    "ReynoldsConsumerProductsInc_20191115_S-1_EX-10.18_11896469_EX-10.18_Supply Agreement.txt",
    "ReynoldsConsumerProductsInc_20200121_S-1A_EX-10.22_11948918_EX-10.22_Service Agreement.txt",
    "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing Agreement1.txt",
    "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing Agreement2.txt",
    "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing Agreement3.txt",
    "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing Agreement4.txt",
    "BIOAMBERINC_04_10_2013-EX-10.34-DEVELOPMENT AGREEMENT (1).txt",
    "BIOAMBERINC_04_10_2013-EX-10.34-DEVELOPMENT AGREEMENT - First Amendment.txt",
    "AzulSa_20170303_F-1A_EX-10.3_9943903_EX-10.3_Maintenance Agreement2.txt",
]

# ── Helpers ──────────────────────────────────────────────────────────────────


def safe_name(s: str, maxlen: int = 120) -> str:
    s = re.sub(r"[^A-Za-z0-9._\-]+", "_", str(s))
    s = re.sub(r"_{3,}", "__", s).strip("._-")
    return s[:maxlen] or "untitled"


def _maybe_unfence(s: str) -> str:
    if not isinstance(s, str):
        return s
    t = s.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t.strip("`")
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3].rstrip()
    return t


def build_input_object(contract_id: str, clause: dict) -> dict:
    return {
        "contract_id": contract_id,
        "clause": {
            "id": clause.get("id"),
            "title": clause.get("title"),
            "text": clause.get("text"),
        },
    }


def dedup_edges(edge_list: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out = []
    for e in edge_list or []:
        src, tgt, et = e.get("src"), e.get("tgt"), e.get("type")
        if not src or not tgt or not et:
            continue
        key = (src, tgt, et)
        if key not in seen:
            seen.add(key)
            out.append({"src": src, "tgt": tgt, "type": et})
    return out


def dedup_nodes(node_list: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out = []
    for n in node_list or []:
        nid = n.get("id", "")
        ntype = n.get("node_type", "")
        key = (nid, ntype)
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out


# ── RPM Limiter (matching graph-grpo-lex) ────────────────────────────────────


class AsyncRPMLimiter:
    def __init__(self, rpm: int):
        self.rpm = max(1, rpm)
        self.window = 60.0
        self._lock = asyncio.Lock()
        self._timestamps: list[float] = []

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            self._timestamps = [
                t for t in self._timestamps if now - t < self.window
            ]
            if len(self._timestamps) >= self.rpm:
                sleep_for = self.window - (now - self._timestamps[0]) + 0.1
                print(f"  [RPM] rate limit reached, sleeping {sleep_for:.1f}s")
                await asyncio.sleep(sleep_for)
            self._timestamps.append(time.monotonic())


# ── Graph Metrics ────────────────────────────────────────────────────────────


def graph_metrics(node_ids: set[str], edge_list: list[dict]) -> dict:
    for e in edge_list or []:
        node_ids.add(e["src"])
        node_ids.add(e["tgt"])

    G_undir = nx.Graph()
    G_undir.add_nodes_from(node_ids)
    for e in edge_list:
        if e["src"] != e["tgt"]:
            G_undir.add_edge(e["src"], e["tgt"])

    G_dir = nx.DiGraph()
    G_dir.add_nodes_from(node_ids)
    for e in edge_list:
        if e["src"] != e["tgt"]:
            G_dir.add_edge(e["src"], e["tgt"], type=e.get("type", ""))

    n = G_undir.number_of_nodes()
    density = nx.density(G_undir) if n > 1 else 0.0
    deg = dict(G_undir.degree())
    orphans = [u for u, d in deg.items() if d == 0]
    leaves = [u for u, d in deg.items() if d == 1]

    art_points = list(nx.articulation_points(G_undir)) if n > 2 else []

    dep_depth = 0
    if n > 1:
        for comp in nx.connected_components(G_undir):
            sg = G_undir.subgraph(comp)
            if sg.number_of_nodes() > 1:
                try:
                    d = nx.diameter(sg)
                    dep_depth = max(dep_depth, d)
                except nx.NetworkXError:
                    pass

    core_nums = nx.core_number(G_undir) if n > 0 else {}
    k_core_k = max(core_nums.values()) if core_nums else 0

    sccs = list(nx.strongly_connected_components(G_dir))
    non_trivial_sccs = [s for s in sccs if len(s) > 1]

    return {
        "nodes": n,
        "edges_directed_typed": len(dedup_edges(edge_list)),
        "edges_undirected": G_undir.number_of_edges(),
        "density": round(density, 6),
        "orphans": len(orphans),
        "leaves": len(leaves),
        "orphan_ratio": round(len(orphans) / n, 4) if n else 0,
        "leaf_ratio": round(len(leaves) / n, 4) if n else 0,
        "articulation_points": len(art_points),
        "dependency_depth": dep_depth,
        "k_core_k": k_core_k,
        "scc_count": len(non_trivial_sccs),
        "largest_scc_size": max((len(s) for s in non_trivial_sccs), default=0),
    }


# ── Core Pipeline ────────────────────────────────────────────────────────────


async def extract_minigraph(
    client: AsyncOpenAI,
    model: str,
    input_obj: dict,
    temperature: float,
    max_tokens: int,
) -> tuple[dict, dict, dict]:
    """Call LLM with V4 prompt. Returns (completion_obj, raw_resp, usage)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": PROMPT_INSTRUCTION + "\nReturn ONLY a JSON object",
        },
        {
            "role": "user",
            "content": "INPUT:\n" + json.dumps(input_obj, ensure_ascii=False),
        },
    ]
    kwargs = dict(
        model=model,
        temperature=temperature,
        messages=messages,
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
    )

    resp = await client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or ""
    usage = resp.usage
    usage_dict = {
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }

    content_clean = _maybe_unfence(content)
    try:
        obj = json.loads(content_clean)
        return obj, {"content": content}, usage_dict
    except json.JSONDecodeError:
        pass

    # Retry once (matching graph-grpo-lex behavior)
    print("  [RETRY] JSON parse failed, retrying...")
    resp2 = await client.chat.completions.create(**kwargs)
    content2 = resp2.choices[0].message.content or ""
    usage2 = resp2.usage
    usage_dict2 = {
        "prompt_tokens": usage2.prompt_tokens if usage2 else 0,
        "completion_tokens": usage2.completion_tokens if usage2 else 0,
        "total_tokens": usage2.total_tokens if usage2 else 0,
    }
    content2_clean = _maybe_unfence(content2)
    obj2 = json.loads(content2_clean)
    return obj2, {"content": content2}, usage_dict2


async def process_clause(
    client: AsyncOpenAI,
    model: str,
    temperature: float,
    max_tokens: int,
    sem: asyncio.Semaphore,
    rpm_limiter: AsyncRPMLimiter,
    contract_id: str,
    clause: dict,
    pairs_dir: Path,
    debug_dir: Path,
    error_dir: Path,
) -> bool:
    clause_id = clause.get("id", "unknown")
    stub = safe_name(f"{contract_id}__{clause_id}")
    out_path = pairs_dir / f"{stub}.json"

    if out_path.exists():
        print(f"  [SKIP] {out_path.name}")
        return True

    inp = build_input_object(contract_id, clause)
    text_len = len(clause.get("text", ""))

    async with sem:
        await rpm_limiter.acquire()
        print(
            f"  [CALL] contract='{contract_id}' clause='{clause_id}' "
            f"text_chars={text_len}"
        )

        try:
            completion_obj, raw_resp, usage = await extract_minigraph(
                client, model, inp, temperature, max_tokens
            )
            pt = usage.get("prompt_tokens", 0)
            ct = usage.get("completion_tokens", 0)
            tt = usage.get("total_tokens", 0)
            print(
                f"  [USAGE] prompt={pt} completion={ct} total={tt}"
            )
        except Exception as e:
            err_path = error_dir / f"{stub}.err.txt"
            err_path.write_text(
                f"{traceback.format_exc()}\nINPUT:\n"
                + json.dumps(inp, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"  [ERROR] {clause_id}: {e}")
            completion_obj = {"nodes": [], "edges": []}
            raw_resp = {"error": str(e)}
            usage = {}

        raw_path = debug_dir / f"{stub}.raw.json"
        raw_path.write_text(
            json.dumps(raw_resp, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        sft_pair = {
            "prompt": {"instruction": PROMPT_INSTRUCTION, "input": inp},
            "completion": completion_obj,
        }
        out_path.write_text(
            json.dumps(sft_pair, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        n_nodes = len(completion_obj.get("nodes", []))
        n_edges = len(completion_obj.get("edges", []))
        print(f"  [RESULT] nodes={n_nodes} edges={n_edges} -> {out_path.name}")
        return True


async def run_pipeline(
    txt_dir: str,
    output_dir: str,
    model: str,
    temperature: float,
    max_tokens: int,
    concurrency: int,
    rpm_limit: int,
    num_contracts: int,
    skip_llm: bool,
    api_key: str,
    base_url: str,
):
    out = Path(output_dir)
    parsed_dir = out / "parsed"
    pairs_dir = out / "pairs"
    debug_dir = out / "debug"
    error_dir = out / "errors"
    fullgraph_dir = out / "fullgraphs"
    gpickle_dir = out / "gpickle"
    reports_dir = out / "reports"

    for d in [parsed_dir, pairs_dir, debug_dir, error_dir,
              fullgraph_dir, gpickle_dir, reports_dir]:
        d.mkdir(parents=True, exist_ok=True)

    txt_path = Path(txt_dir)
    loader = CUADLoader(str(txt_path.parent.parent.parent))

    # ── Step 1: Select and segment contracts ────────────────────────────
    print("=" * 60)
    print("Step 1: Clause Segmentation / 条款切分")
    print("=" * 60)

    contract_files = []
    for name in DEFAULT_CONTRACTS[:num_contracts]:
        fp = txt_path / name
        if fp.exists():
            contract_files.append(fp)
        else:
            print(f"  [WARN] Not found: {name}")

    if not contract_files:
        all_txt = sorted(txt_path.glob("*.txt"))
        contract_files = all_txt[:num_contracts]

    parsed_contracts: list[tuple[str, list[dict]]] = []
    for fp in contract_files:
        contract_id = fp.stem
        text = fp.read_text(encoding="utf-8", errors="replace")
        clauses_dict, _ = loader._segment_and_link(text, contract_id)

        clauses_list = []
        for cid, clause in sorted(clauses_dict.items()):
            clauses_list.append({
                "id": cid,
                "title": clause.title,
                "text": clause.content,
            })

        parsed_data = {"contract_id": contract_id, "clauses": clauses_list}
        parsed_path = parsed_dir / f"{safe_name(contract_id)}_parsed.json"
        parsed_path.write_text(
            json.dumps(parsed_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        parsed_contracts.append((contract_id, clauses_list))
        print(f"  {contract_id}: {len(clauses_list)} clauses")

    total_clauses = sum(len(c) for _, c in parsed_contracts)
    print(f"\nTotal: {len(parsed_contracts)} contracts, {total_clauses} clauses")

    # ── Step 2: LLM Minigraph Extraction ────────────────────────────────
    if not skip_llm:
        print("\n" + "=" * 60)
        print("Step 2: LLM Minigraph Extraction / LLM 小图提取")
        print(f"  Model: {model} | Temp: {temperature} | MaxTokens: {max_tokens}")
        print(f"  Concurrency: {concurrency} | RPM: {rpm_limit}")
        print("=" * 60)

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        sem = asyncio.Semaphore(concurrency)
        rpm = AsyncRPMLimiter(rpm_limit)

        total_done = 0
        for contract_id, clauses in parsed_contracts:
            print(f"\n── Contract: {contract_id} ({len(clauses)} clauses) ──")
            tasks = [
                process_clause(
                    client, model, temperature, max_tokens,
                    sem, rpm, contract_id, clause,
                    pairs_dir, debug_dir, error_dir,
                )
                for clause in clauses
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            done = sum(1 for r in results if r is True)
            errors = sum(1 for r in results if isinstance(r, Exception))
            total_done += done
            print(f"  Done: {done}/{len(clauses)} (errors: {errors})")

        await client.close()
        print(f"\nStep 2 complete: {total_done}/{total_clauses} clauses processed")
    else:
        print("\n[SKIP LLM] Using existing pair files")

    # ── Step 3: Graph Assembly ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 3: Graph Assembly / 图组装")
    print("=" * 60)

    all_metrics = []
    for contract_id, _ in parsed_contracts:
        prefix = safe_name(contract_id) + "__"
        pair_files = sorted(pairs_dir.glob(f"{prefix}*.json"))
        if not pair_files:
            print(f"  [WARN] No pair files for {contract_id}")
            continue

        all_nodes: list[dict] = []
        all_edges: list[dict] = []
        for pf in pair_files:
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                comp = data.get("completion", {})
                all_nodes.extend(comp.get("nodes", []))
                all_edges.extend(comp.get("edges", []))
            except Exception as e:
                print(f"  [WARN] Failed to read {pf.name}: {e}")

        node_map = dedup_nodes(all_nodes)
        edges = dedup_edges(all_edges)

        full_graph = {
            "contract_id": contract_id,
            "nodes": node_map,
            "node_map": node_map,
            "edges": edges,
        }
        fg_path = fullgraph_dir / f"{safe_name(contract_id)}_fullgraph.json"
        fg_path.write_text(
            json.dumps(full_graph, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        node_ids = {n.get("id") for n in node_map if n.get("id")}
        m = graph_metrics(node_ids, edges)
        m["contract_id"] = contract_id
        m["pair_files"] = len(pair_files)
        all_metrics.append(m)

        print(
            f"  {contract_id}: nodes={m['nodes']} edges={m['edges_directed_typed']} "
            f"density={m['density']} SCCs={m['scc_count']} "
            f"largest_SCC={m['largest_scc_size']}"
        )

    # ── Step 4: Convert to SA-MCGS format ───────────────────────────────
    print("\n" + "=" * 60)
    print("Step 4: Convert to SA-MCGS DependencyGraph / 转换为 SA-MCGS 格式")
    print("=" * 60)

    loader_all = CUADLoader(str(txt_path.parent.parent.parent),
                            config={"cuad": {"clause_only": False}})
    for fg_file in sorted(fullgraph_dir.glob("*_fullgraph.json")):
        graph = loader_all._json_to_dependency_graph(
            fg_file, fg_file.stem.replace("_fullgraph", "")
        )
        if not graph:
            continue

        G = nx.DiGraph()
        for cid, clause in graph.clauses.items():
            G.add_node(cid, heading=clause.title, text=clause.content[:200],
                       key=cid, clause_type=clause.clause_type.value)
        for edge in graph.edges:
            G.add_edge(edge.source, edge.target,
                       edge_type=edge.dependency_type.value,
                       weight=edge.weight, reasoning=edge.reasoning)

        gpickle_path = gpickle_dir / f"{fg_file.stem.replace('_fullgraph', '')}.gpickle.gz"
        import gzip
        import pickle
        with gzip.open(gpickle_path, "wb") as f:
            pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

        sccs = list(nx.strongly_connected_components(G))
        non_trivial = [s for s in sccs if len(s) > 1]

        print(
            f"  {fg_file.stem}: clauses={len(graph.clauses)} "
            f"edges={len(graph.edges)} SCCs={len(non_trivial)} "
            f"-> {gpickle_path.name}"
        )

        if non_trivial:
            for i, scc in enumerate(sorted(non_trivial, key=len, reverse=True)[:3]):
                print(f"    SCC-{i}: size={len(scc)} nodes={sorted(scc)[:5]}...")

    # ── Save reports ────────────────────────────────────────────────────
    if all_metrics:
        metrics_path = reports_dir / "fullgraphs_metrics.json"
        metrics_path.write_text(
            json.dumps(all_metrics, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        try:
            import csv
            csv_path = reports_dir / "fullgraphs_metrics.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=all_metrics[0].keys())
                writer.writeheader()
                writer.writerows(all_metrics)
            print(f"\nMetrics saved to {csv_path}")
        except Exception:
            pass

    summary = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "contracts": len(parsed_contracts),
        "total_clauses": total_clauses,
        "metrics": all_metrics,
    }
    summary_path = reports_dir / "processing_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Summary saved to {summary_path}")
    print("\nDone!")


# ── CLI ──────────────────────────────────────────────────────────────────────


@app.command()
def main(
    num_contracts: int = typer.Option(5, help="Number of contracts to process"),
    model: str = typer.Option("gpt-4o", help="OpenAI model name"),
    temperature: float = typer.Option(0.0, help="Sampling temperature"),
    max_tokens: int = typer.Option(4096, help="Max completion tokens"),
    concurrency: int = typer.Option(3, help="Max concurrent API calls"),
    rpm_limit: int = typer.Option(30, help="Requests per minute limit"),
    output_dir: str = typer.Option(
        "data/cuad/grpo_lex_replicated", help="Output directory"
    ),
    txt_dir: str = typer.Option(
        "data/cuad/CUAD_v1/CUAD_v1/full_contract_txt",
        help="CUAD contract text directory",
    ),
    skip_llm: bool = typer.Option(False, help="Skip LLM calls, re-run assembly only"),
    api_key: str = typer.Option(
        None, envvar="OPENAI_API_KEY", help="API key (or set OPENAI_API_KEY)"
    ),
    base_url: str = typer.Option(
        None, envvar="OPENAI_BASE_URL", help="API base URL"
    ),
):
    """Replicate graph-grpo-lex pipeline on CUAD contracts."""
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        typer.echo("ERROR: No API key. Set --api-key or OPENAI_API_KEY env var.")
        raise typer.Exit(1)

    asyncio.run(
        run_pipeline(
            txt_dir=txt_dir,
            output_dir=output_dir,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            concurrency=concurrency,
            rpm_limit=rpm_limit,
            num_contracts=num_contracts,
            skip_llm=skip_llm,
            api_key=api_key,
            base_url=base_url,
        )
    )


if __name__ == "__main__":
    app()

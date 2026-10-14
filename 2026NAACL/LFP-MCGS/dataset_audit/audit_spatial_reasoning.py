#!/usr/bin/env python3
"""Recompute the frozen spatial-reasoning audit from ignored raw data.

The script is intentionally offline.  It reads only files below
``dataset_audit/raw/logic`` and records their hashes in the generated JSON.
Expected hashes and headline counts are assertions, never substitutes for
computing the metrics from the source records.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import statistics
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RAW_ROOT = SCRIPT_DIR / "raw" / "logic"
DEFAULT_OUTPUT = SCRIPT_DIR / "spatial_reasoning_audit.json"

FROZEN_FILES = {
    "spartun/train.json": {
        "sha256": "d650144e0e47eca5075ec3d04d27aebeac9b83ac0ee560021aaa5fd585759b0f",
        "url": "https://www.cse.msu.edu/~kordjams/data/SPARTUN.zip",
    },
    "spartun/dev.json": {
        "sha256": "7446cfb121de07c094a492c5a28caea268c421eb79bd7ca6fe3bd7d191cb7a45",
        "url": "https://www.cse.msu.edu/~kordjams/data/SPARTUN.zip",
    },
    "spartun/test.json": {
        "sha256": "52614b1719ae82317ae8d033aaf6df8d690003f38a5a2fa66d402e172c021db4",
        "url": "https://www.cse.msu.edu/~kordjams/data/SPARTUN.zip",
    },
    "sparp/train.parquet": {
        "sha256": "d30694cadd55278d03fb77e6209d7b66b75f6760085a9132954d9e9317431492",
        "url": "https://huggingface.co/datasets/UKPLab/sparp/resolve/refs%2Fconvert%2Fparquet/SpaRP-PS1%20(SpaRTUN)/train/0000.parquet",
    },
    "sparp/validation.parquet": {
        "sha256": "65d5bb03c90a3b06dfa66b6fae1e1c4b6d58e8242dcb23b8f107d7ace81317da",
        "url": "https://huggingface.co/datasets/UKPLab/sparp/resolve/refs%2Fconvert%2Fparquet/SpaRP-PS1%20(SpaRTUN)/validation/0000.parquet",
    },
    "sparp/test.parquet": {
        "sha256": "317908a3bf36a54a2a2711fa30d1909f220a386d8a26c703af0248e72433595e",
        "url": "https://huggingface.co/datasets/UKPLab/sparp/resolve/refs%2Fconvert%2Fparquet/SpaRP-PS1%20(SpaRTUN)/test/0000.parquet",
    },
    "stepgame/test.jsonl": {
        "sha256": "8fd1a61d36257322752f39e412d7aff1a187a555a30414a10c1bae66acd112bc",
        "url": "https://raw.githubusercontent.com/ShiZhengyan/StepGame/5e6aff1563a6d7f46ee1f1aeff98b94e68c29005/Dataset/TrainVersion/test.jsonl",
    },
    "stepgame/repo/Code/template.py": {
        "sha256": "c9ff684b7674a2c8c11af6d584619c24786d704d6eaa031d28d50e3983db0c02",
        "url": "https://raw.githubusercontent.com/ShiZhengyan/StepGame/5e6aff1563a6d7f46ee1f1aeff98b94e68c29005/Code/template.py",
    },
    "stepgame/repo/Code/parameterized_step_game_8relation.py": {
        "sha256": "5144f62caf6adcca80ae282c02693a49b842e6150487aed50c624f2239a244c5",
        "url": "https://raw.githubusercontent.com/ShiZhengyan/StepGame/5e6aff1563a6d7f46ee1f1aeff98b94e68c29005/Code/parameterized_step_game_8relation.py",
    },
}

EXPECTED_METRICS = {
    "spartun.questions": 48246,
    "spartun.multihop_questions": 25112,
    "spartun.chain_cycles": 0,
    "spartun.goal_chain_cycles": 0,
    "sparp.rows": 21163,
    "sparp.two_hop_rows": 7161,
    "sparp.ground_cycles": 0,
    "stepgame.full_test_examples": 100000,
    "stepgame.k10_examples": 10000,
    "stepgame.k10_fully_canonical": 6725,
    "stepgame.k10_bad_examples": 602,
    "stepgame.k10_bad_sentences": 624,
    "stepgame.k10_zero_but_for": 1235,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def frozen_inventory(raw_root: Path) -> dict[str, dict]:
    inventory: dict[str, dict] = {}
    missing: list[str] = []
    for relative, expected in FROZEN_FILES.items():
        path = raw_root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        actual_hash = sha256_file(path)
        if actual_hash != expected["sha256"]:
            raise AssertionError(
                f"Frozen input hash mismatch for {relative}: "
                f"expected {expected['sha256']}, got {actual_hash}"
            )
        inventory[relative] = {
            "bytes": path.stat().st_size,
            "sha256": actual_hash,
            "source_url": expected["url"],
        }
    if missing:
        joined = "\n  - ".join(missing)
        raise FileNotFoundError(
            f"Cannot reproduce the audit; frozen raw files are missing:\n  - {joined}"
        )
    return inventory


def assert_metric(name: str, actual: int) -> None:
    expected = EXPECTED_METRICS[name]
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected}, recomputed {actual}")


def counter_json(counter: Counter) -> dict[str, int]:
    return {str(key): counter[key] for key in sorted(counter)}


def describe(values: Sequence[int | float]) -> dict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": min(values),
        "median": float(statistics.median(values)),
        "mean": round(statistics.fmean(values), 6),
        "max": max(values),
    }


def has_directed_cycle(edges: Iterable[tuple[str, str]]) -> bool:
    unique_edges = set(edges)
    nodes = {node for edge in unique_edges for node in edge}
    adjacency: dict[str, list[str]] = {node: [] for node in nodes}
    indegree = {node: 0 for node in nodes}
    for source, target in unique_edges:
        if source == target:
            return True
        adjacency[source].append(target)
        indegree[target] += 1
    queue = deque(node for node in nodes if indegree[node] == 0)
    processed = 0
    while queue:
        current = queue.popleft()
        processed += 1
        for neighbor in adjacency[current]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)
    return processed != len(nodes)


def audit_spartun(raw_root: Path) -> dict:
    split_counts: dict[str, dict[str, int]] = {}
    stories = 0
    questions = 0
    multihop = 0
    chain_cycles = 0
    goal_chain_cycles = 0
    self_loops = 0
    question_types: Counter = Counter()
    chain_lengths: Counter = Counter()
    reasoning_steps: Counter = Counter()
    candidate_pairs: list[int] = []
    support_pairs: list[int] = []

    for split in ("train", "dev", "test"):
        path = raw_root / "spartun" / f"{split}.json"
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        records = payload["data"]
        split_questions = sum(len(record["questions"]) for record in records)
        split_counts[split] = {
            "stories": len(records),
            "questions": split_questions,
        }
        stories += len(records)
        for record in records:
            story_pair_count = len(record["story_triplets"])
            for question in record["questions"]:
                questions += 1
                question_types[question["q_type"]] += 1
                info = question["question_info"]
                chain = info.get("chain") or []
                goal_chain = info.get("goal_chain") or []
                chain_lengths[len(chain)] += 1
                reasoning_steps[info["reasoning_steps"]] += 1
                multihop += len(chain) >= 2
                candidate_pairs.append(story_pair_count)
                support_pairs.append(len(chain))

                chain_edges = [(step[0][0], step[0][1]) for step in chain]
                goal_edges = [(step[0], step[1]) for step in goal_chain]
                chain_cycles += has_directed_cycle(chain_edges)
                goal_chain_cycles += has_directed_cycle(goal_edges)
                self_loops += sum(a == b for a, b in chain_edges)
                self_loops += sum(a == b for a, b in goal_edges)

    assert_metric("spartun.questions", questions)
    assert_metric("spartun.multihop_questions", multihop)
    assert_metric("spartun.chain_cycles", chain_cycles)
    assert_metric("spartun.goal_chain_cycles", goal_chain_cycles)

    return {
        "source": {
            "paper": "https://aclanthology.org/2022.emnlp-main.413/",
            "repository": "https://github.com/HLR/SpaRTUN",
            "repository_revision_audited": "ab924d2324ac28955cc1b72b7edf1bbd5b35e811",
            "official_archive": "https://www.cse.msu.edu/~kordjams/data/SPARTUN.zip",
            "license_evidence": "MIT in the official repository; the data archive has no separate license file.",
        },
        "measured": {
            "split_counts": split_counts,
            "stories": stories,
            "questions": questions,
            "multihop_questions_chain_length_ge_2": multihop,
            "question_type_distribution": counter_json(question_types),
            "gold_chain_length_distribution": counter_json(chain_lengths),
            "reasoning_steps_distribution": counter_json(reasoning_steps),
            "candidate_story_triplet_pairs": describe(candidate_pairs),
            "gold_chain_support_pairs": describe(support_pairs),
            "directed_ground_cycles": {
                "chain": chain_cycles,
                "goal_chain": goal_chain_cycles,
                "self_loops_across_both": self_loops,
            },
        },
        "semantics": {
            "instance_natural_language": "facts only",
            "rules": "known global spatial algebra, not latent per-instance natural-language rules",
            "certificate": "chain and goal_chain provide one gold support path",
            "cycle_audit_scope": "released gold chain/goal_chain only; not the complete story/source graph",
            "source_deletion_gold": False,
            "ground_scc_evidence": False,
        },
        "verdict": "P1 confirmatory transfer corpus; not evidence for SCC-specific MCGS.",
    }


def decode_json_field(value):
    return json.loads(value) if isinstance(value, str) else value


def audit_sparp(raw_root: Path) -> dict:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:  # pragma: no cover - environment diagnostic
        raise RuntimeError(
            "SpaRP frozen inputs are Parquet; install pyarrow to reproduce this audit."
        ) from exc

    split_rows: dict[str, int] = {}
    rows: list[dict] = []
    for split in ("train", "validation", "test"):
        path = raw_root / "sparp" / f"{split}.parquet"
        table = parquet.read_table(
            path,
            columns=[
                "context_id",
                "question_id",
                "num_hop",
                "symbolic_context",
                "symbolic_reasoning",
            ],
        )
        split_rows[split] = table.num_rows
        rows.extend(table.to_pylist())

    hop_distribution: Counter = Counter()
    proof_step_distribution: Counter = Counter()
    unique_contexts: set[str] = set()
    context_pairs: list[int] = []
    context_minus_hop: list[int] = []
    parse_failures = 0
    ground_cycles = 0
    ground_self_loops = 0

    for row in rows:
        hop = int(row["num_hop"])
        hop_distribution[hop] += 1
        unique_contexts.add(row["context_id"])
        try:
            context = decode_json_field(row["symbolic_context"])
            proof = decode_json_field(row["symbolic_reasoning"])
        except (TypeError, ValueError, json.JSONDecodeError):
            parse_failures += 1
            continue
        context_pairs.append(len(context))
        context_minus_hop.append(len(context) - hop)
        proof_step_distribution[len(proof)] += 1
        proof_edges = [(step["head"], step["tail"]) for step in proof]
        ground_cycles += has_directed_cycle(proof_edges)
        ground_self_loops += sum(source == target for source, target in proof_edges)

    row_count = len(rows)
    two_hop_rows = hop_distribution[2]
    assert_metric("sparp.rows", row_count)
    assert_metric("sparp.two_hop_rows", two_hop_rows)
    assert_metric("sparp.ground_cycles", ground_cycles)
    if parse_failures:
        raise AssertionError(f"SpaRP symbolic JSON parse failures: {parse_failures}")

    return {
        "source": {
            "paper": "https://aclanthology.org/2024.acl-long.261/",
            "dataset": "https://huggingface.co/datasets/UKPLab/sparp",
            "dataset_revision": "2706ed464416758c67a09716ed0262c880ee6bdd",
            "repository": "https://github.com/UKPLab/acl2024-sparc-and-sparp",
            "license": "CC-BY-SA-4.0",
            "configuration": "SpaRP-PS1 (SpaRTUN)",
        },
        "measured": {
            "split_rows": split_rows,
            "rows": row_count,
            "unique_context_ids": len(unique_contexts),
            "two_hop_rows": two_hop_rows,
            "multihop_rows_num_hop_ge_2": sum(
                count for hop, count in hop_distribution.items() if hop >= 2
            ),
            "num_hop_distribution": counter_json(hop_distribution),
            "symbolic_reasoning_step_distribution": counter_json(
                proof_step_distribution
            ),
            "symbolic_context_relation_pairs": describe(context_pairs),
            "symbolic_context_pairs_minus_num_hop": describe(context_minus_hop),
            "symbolic_json_parse_failures": parse_failures,
            "directed_ground_cycles": ground_cycles,
            "directed_ground_self_loops": ground_self_loops,
        },
        "semantics": {
            "instance_natural_language": "facts plus question",
            "rules": "known global spatial algebra",
            "certificate": "verbalized and machine-readable symbolic reasoning path",
            "cycle_audit_scope": "released symbolic_reasoning proof path only; not the complete symbolic_context graph",
            "native_executable_program": False,
            "source_deletion_gold": False,
            "ground_scc_evidence": False,
        },
        "verdict": "Best proof-supervised spatial transfer option, but P1 only because all audited ground proof graphs are acyclic.",
    }


# StepGame's generator has eight qualitative directions.  The template parser
# is compiled from the frozen official template.py rather than a hand-written
# sentence parser.
FUNCTION_VECTORS = {
    "object1_left_object2": (-1, 0),
    "object1_right_object2": (1, 0),
    "object1_over_object2": (0, 1),
    "object1_below_object2": (0, -1),
    "object1_lowerleft_object2": (-1, -1),
    "object1_upright_object2": (1, 1),
    "object1_lowerright_object2": (1, -1),
    "object1_upleft_object2": (-1, 1),
}

AA_IS_OBJECT1 = {
    "object1_left_object2",
    "object1_over_object2",
    "object1_lowerleft_object2",
    "object1_lowerright_object2",
}

QUESTION_RE = re.compile(
    r"^What is the relation of the agent (?P<source>[A-Z]) "
    r"to the agent (?P<target>[A-Z])\?$"
)

Constraint = tuple[str, str, int, int]


def normalize_constraint(
    source: str, target: str, dx: int, dy: int
) -> Constraint:
    if source < target:
        return source, target, dx, dy
    return target, source, -dx, -dy


@dataclass(frozen=True)
class CompiledTemplate:
    pattern: re.Pattern[str]
    function: str
    index: int
    vector: tuple[int, int]
    fields: frozenset[str]


@dataclass(frozen=True)
class SentenceParse:
    status: str
    constraints: tuple[Constraint, ...]
    signatures: tuple[str, ...]


class OfficialStepGameParser:
    def __init__(self, template_path: Path) -> None:
        tree = ast.parse(template_path.read_text(encoding="utf-8"))
        compiled: list[CompiledTemplate] = []
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name not in FUNCTION_VECTORS:
                continue
            candidates: list[str] = []
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if any(
                    isinstance(target, ast.Name)
                    and target.id == "template_candidates"
                    for target in statement.targets
                ):
                    candidates = ast.literal_eval(statement.value)
                    break
            bindings = (
                {"AA": "source", "BB": "target"}
                if node.name in AA_IS_OBJECT1
                else {"BB": "source", "AA": "target"}
            )
            for index, template in enumerate(candidates):
                fields: set[str] = set()
                pattern = ""
                for part in re.split(r"(AA|BB)", template):
                    if part not in bindings:
                        pattern += re.escape(part)
                        continue
                    field = bindings[part]
                    if field in fields:
                        pattern += f"(?P={field})"
                    else:
                        pattern += f"(?P<{field}>[A-Z])"
                        fields.add(field)
                compiled.append(
                    CompiledTemplate(
                        pattern=re.compile(f"^{pattern}$"),
                        function=node.name,
                        index=index,
                        vector=FUNCTION_VECTORS[node.name],
                        fields=frozenset(fields),
                    )
                )
        self.templates = compiled

    def parse(self, sentence: str) -> SentenceParse:
        complete: set[Constraint] = set()
        signatures: set[str] = set()
        incomplete = False
        for template in self.templates:
            match = template.pattern.fullmatch(sentence)
            if match is None:
                continue
            signatures.add(f"{template.function}[{template.index}]")
            if not {"source", "target"}.issubset(template.fields):
                incomplete = True
                continue
            dx, dy = template.vector
            complete.add(
                normalize_constraint(
                    match.group("source"), match.group("target"), dx, dy
                )
            )
        constraints = tuple(sorted(complete))
        if len(constraints) == 1:
            status = "canonical"
        elif len(constraints) > 1:
            status = "ambiguous"
        elif incomplete:
            status = "incomplete_template"
        else:
            status = "unmatched"
        return SentenceParse(status, constraints, tuple(sorted(signatures)))


def undirected_adjacency(
    constraints: Sequence[Constraint],
) -> dict[str, list[tuple[str, int]]]:
    graph: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for edge_id, (source, target, _dx, _dy) in enumerate(constraints):
        graph[source].append((target, edge_id))
        graph[target].append((source, edge_id))
    return graph


def shortest_source_distance(
    constraints: Sequence[Constraint], source: str, target: str
) -> int | None:
    graph = undirected_adjacency(constraints)
    queue = deque([(source, 0)])
    seen = {source}
    while queue:
        current, distance = queue.popleft()
        if current == target:
            return distance
        for neighbor, _edge_id in graph.get(current, []):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, distance + 1))
    return None


def connected_without_edge(
    graph: dict[str, list[tuple[str, int]]],
    source: str,
    target: str,
    skipped_edge: int,
) -> bool:
    stack = [source]
    seen = {source}
    while stack:
        current = stack.pop()
        if current == target:
            return True
        for neighbor, edge_id in graph.get(current, []):
            if edge_id == skipped_edge or neighbor in seen:
                continue
            seen.add(neighbor)
            stack.append(neighbor)
    return False


def undirected_cycle_rank(constraints: Sequence[Constraint]) -> int:
    graph = undirected_adjacency(constraints)
    seen: set[str] = set()
    components = 0
    for root in graph:
        if root in seen:
            continue
        components += 1
        stack = [root]
        seen.add(root)
        while stack:
            current = stack.pop()
            for neighbor, _edge_id in graph[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
    return len(constraints) - len(graph) + components


def audit_stepgame(raw_root: Path) -> dict:
    test_path = raw_root / "stepgame" / "test.jsonl"
    template_path = raw_root / "stepgame" / "repo" / "Code" / "template.py"
    parser = OfficialStepGameParser(template_path)

    full_examples = 0
    k10_examples = 0
    fully_canonical = 0
    bad_examples = 0
    bad_sentences = 0
    zero_but_for = 0
    stories_with_undirected_cycle = 0
    support_lengths: list[int] = []
    story_lengths: list[int] = []
    nominal_noise: list[int] = []
    parse_status: Counter = Counter()

    with test_path.open(encoding="utf-8") as handle:
        for line in handle:
            example = json.loads(line)
            full_examples += 1
            if int(example["k_hop"]) != 10:
                continue
            k10_examples += 1
            story = example["story"]
            story_lengths.append(len(story))
            nominal_noise.append(len(story) - 10)
            parses = [parser.parse(sentence) for sentence in story]
            parse_status.update(item.status for item in parses)
            incomplete_count = sum(
                item.status == "incomplete_template" for item in parses
            )
            bad_sentences += incomplete_count
            bad_examples += incomplete_count > 0

            if not all(item.status == "canonical" for item in parses):
                continue
            fully_canonical += 1
            question_match = QUESTION_RE.fullmatch(example["question"])
            if question_match is None:
                raise AssertionError(
                    f"Unparseable canonical StepGame question: {example['question']}"
                )
            source = question_match.group("source")
            target = question_match.group("target")
            constraints = [item.constraints[0] for item in parses]
            distance = shortest_source_distance(constraints, source, target)
            if distance is None:
                raise AssertionError("Canonical StepGame story does not connect query")
            support_lengths.append(distance)
            graph = undirected_adjacency(constraints)
            critical = sum(
                not connected_without_edge(graph, source, target, edge_id)
                for edge_id in range(len(constraints))
            )
            zero_but_for += critical == 0
            stories_with_undirected_cycle += undirected_cycle_rank(constraints) > 0

    assert_metric("stepgame.full_test_examples", full_examples)
    assert_metric("stepgame.k10_examples", k10_examples)
    assert_metric("stepgame.k10_fully_canonical", fully_canonical)
    assert_metric("stepgame.k10_bad_examples", bad_examples)
    assert_metric("stepgame.k10_bad_sentences", bad_sentences)
    assert_metric("stepgame.k10_zero_but_for", zero_but_for)

    return {
        "source": {
            "paper": "https://ojs.aaai.org/index.php/AAAI/article/view/21383",
            "repository": "https://github.com/ShiZhengyan/StepGame",
            "repository_revision": "5e6aff1563a6d7f46ee1f1aeff98b94e68c29005",
            "license": "MIT",
        },
        "measured": {
            "full_noisy_test_examples": full_examples,
            "k10_examples": k10_examples,
            "k10_story_sentences": describe(story_lengths),
            "k10_nominal_noise_sentences": describe(nominal_noise),
            "k10_parse_status": counter_json(parse_status),
            "k10_fully_canonical_examples": fully_canonical,
            "k10_minimum_support_sources": describe(support_lengths),
            "k10_redundancy": {
                "fully_canonical_stories_with_zero_but_for_sources": zero_but_for,
                "rate_within_fully_canonical": round(
                    zero_but_for / fully_canonical, 6
                ),
            },
            "k10_undirected_source_cycles": {
                "stories": stories_with_undirected_cycle,
                "rate_within_fully_canonical": round(
                    stories_with_undirected_cycle / fully_canonical, 6
                ),
            },
            "k10_bad_apparent_self_references": {
                "affected_examples": bad_examples,
                "sentence_occurrences": bad_sentences,
                "cause": "Official object1_upleft_object2 template index 11 drops the second entity and repeats the first placeholder; these are malformed surface forms, not valid semantic self-loop facts.",
            },
        },
        "semantics": {
            "instance_natural_language": "facts only",
            "rules": "known global inverse and vector-composition rules",
            "gold_proof": False,
            "cycle_audit_scope": "undirected source redundancy only; not a grounded directed SCC",
            "source_deletion_gold": False,
            "ground_scc_evidence": False,
        },
        "verdict": "P1 redundancy/noise stress test after strict template filtering; not a controlled grounded-SCC corpus.",
    }


def build_audit(raw_root: Path) -> dict:
    inventory = frozen_inventory(raw_root)
    return {
        "schema_version": 2,
        "audit_as_of": "2026-08-18",
        "generated_by": Path(__file__).name,
        "raw_root": (
            "raw/logic (relative to audit_spatial_reasoning.py)"
            if raw_root.resolve() == DEFAULT_RAW_ROOT.resolve()
            else str(raw_root.resolve())
        ),
        "method": "All counts are recomputed from frozen raw records. Hard-coded values are used only as hash and regression assertions.",
        "frozen_input_inventory": inventory,
        "datasets": {
            "SpaRTUN": audit_spartun(raw_root),
            "SpaRP_PS1_SpaRTUN": audit_sparp(raw_root),
            "StepGame": audit_stepgame(raw_root),
        },
        "cross_dataset_verdict": {
            "use_for_main_scc_claim": False,
            "recommended_use": "Use one filtered spatial corpus as a P1 domain-transfer experiment after the main logic corpus.",
            "shared_limitation": "Instance text supplies facts under globally known rules; audited gold chains have no directed ground cycles.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    result = build_audit(args.raw_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote reproducible spatial audit to {args.output}")


if __name__ == "__main__":
    main()

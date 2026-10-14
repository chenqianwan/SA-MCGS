#!/usr/bin/env python3
"""Blind root-action local-LLM -> Horn KB -> LFP -> MCGS integration smoke.

This is deliberately an integration test, not a benchmark result.  Search may
read raw source text and the current committed closure, but it cannot inspect a
source's symbolic parse until it executes that source as a charged root action.
Hypothetical TreeMCTS/MCGS rollouts contain no atoms or rules.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCRIPT_PATH = Path(__file__).resolve()
EXPERIMENT_ROOT = SCRIPT_PATH.parent
NAACL_ROOT = SCRIPT_PATH.parents[2]
AUDIT_PATH = NAACL_ROOT / "dataset_audit" / "audit_productive_recursion.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pw = load_module("v2_smoke_pw", AUDIT_PATH)


SYSTEM_PROMPT = """You are a deterministic semantic parser for one controlled-English positive Horn statement.
Return exactly one JSON object and no explanation:
{"kind":"fact|rule","head":{"predicate":"string","arguments":["string"]},"body":[{"predicate":"string","arguments":["string"]}]}

Rules:
1. Parse only the supplied sentence. Never answer a query, infer a new fact, or combine sources.
2. For a fact, body is []. For a rule, body contains every premise and exactly one head.
3. Use adjective predicates without an is_ prefix: "Bob is kind" uses "kind".
4. Use relation verbs in their surface third-person form: "sees", "likes", "visits".
5. Lowercase entities; join multiword entities with underscores; drop leading the/a/an.
6. Preserve someone and something as variables; map their pronouns consistently.
7. Named animals or people introduced with "the" are constants, not variables.
8. Do not invent predicates, facts, premises, negation, IDs, spans, or explanations.

Examples:
Bob is kind. => {"kind":"fact","head":{"predicate":"kind","arguments":["bob"]},"body":[]}
The mouse sees the tiger. => {"kind":"fact","head":{"predicate":"sees","arguments":["mouse","tiger"]},"body":[]}
If someone is red then they are nice. => {"kind":"rule","head":{"predicate":"nice","arguments":["someone"]},"body":[{"predicate":"red","arguments":["someone"]}]}
If something sees the cat then it visits the dog. => {"kind":"rule","head":{"predicate":"visits","arguments":["something","dog"]},"body":[{"predicate":"sees","arguments":["something","cat"]}]}
Big people are round. => {"kind":"rule","head":{"predicate":"round","arguments":["someone"]},"body":[{"predicate":"big","arguments":["someone"]}]}
If someone eats the rabbit and they eat the cat then they visit the dog. => {"kind":"rule","head":{"predicate":"visits","arguments":["someone","dog"]},"body":[{"predicate":"eats","arguments":["someone","rabbit"]},{"predicate":"eats","arguments":["someone","cat"]}]}
"""


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "does", "if", "in",
    "is", "it", "of", "or", "something", "someone", "that", "the", "then",
    "they", "them", "to", "what", "when", "with",
    "all", "thing", "things", "person", "people",
}


RELATION_FORMS = {
    "see": "sees", "sees": "sees",
    "eat": "eats", "eats": "eats",
    "like": "likes", "likes": "likes",
    "need": "needs", "needs": "needs",
    "visit": "visits", "visits": "visits",
    "chase": "chases", "chases": "chases",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_unit(*parts: Any) -> float:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / 2**64


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def write_jsonl_atomic(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def surface_tokens(text: str) -> frozenset[str]:
    return frozenset(
        token for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1 and token not in STOPWORDS
    )


def atom_sort_key(atom: Any) -> tuple:
    return atom.predicate, atom.arguments


def atom_text(atom: Any) -> str:
    return f"{atom.predicate}({','.join(atom.arguments)})"


def atom_tokens(atom: Any) -> set[str]:
    predicate = atom.predicate.rsplit("::", 1)[0]
    tokens = set(predicate.replace("_", " ").split())
    for argument in atom.arguments:
        if argument not in pw.VARIABLES:
            tokens.update(argument.replace("_", " ").split())
    return {token.lower() for token in tokens if token}


def normalize_predicate(value: str, arity: int | None = None) -> str:
    predicate = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    for prefix in ("is_", "are_"):
        if predicate.startswith(prefix):
            predicate = predicate[len(prefix):]
    if not predicate or predicate.startswith("not_"):
        raise ValueError(f"Invalid positive predicate: {value!r}")
    if arity == 2:
        predicate = RELATION_FORMS.get(predicate, predicate)
    return f"{predicate}::+"


def normalize_argument(value: str) -> str:
    argument = re.sub(r"[^a-z0-9?]+", "_", value.strip().lower()).strip("_")
    while argument.startswith(("the_", "a_", "an_")):
        argument = argument.split("_", 1)[1]
    aliases = {
        "?x": "someone", "x": "someone", "they": "someone", "them": "someone",
        "person": "someone", "?y": "something", "y": "something", "it": "something",
    }
    argument = aliases.get(argument, argument.lstrip("?"))
    if not argument:
        raise ValueError("Empty argument")
    return argument


def parse_atom_json(raw: Any) -> Any:
    if not isinstance(raw, dict) or set(raw) - {"predicate", "arguments", "args"}:
        raise ValueError("Atom is not a strict predicate/arguments object")
    predicate = raw.get("predicate")
    arguments = raw.get("arguments", raw.get("args"))
    if not isinstance(predicate, str) or not isinstance(arguments, list):
        raise ValueError("Atom requires predicate and arguments")
    if not 1 <= len(arguments) <= 2 or not all(isinstance(item, str) for item in arguments):
        raise ValueError("Only unary/binary atoms are supported")
    return pw.Atom(normalize_predicate(predicate, len(arguments)), tuple(normalize_argument(item) for item in arguments))


@dataclass(frozen=True)
class ParsedStatement:
    kind: str
    head: Any
    body: tuple[Any, ...]

    @property
    def signature(self) -> str:
        if self.kind == "fact":
            return f"fact:{atom_text(self.head)}"
        return f"rule:{'&'.join(atom_text(atom) for atom in self.body)}->{atom_text(self.head)}"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "head": {"predicate": self.head.predicate, "arguments": list(self.head.arguments)},
            "body": [
                {"predicate": atom.predicate, "arguments": list(atom.arguments)}
                for atom in self.body
            ],
        }


def validate_statement(raw: Any, source_text: str) -> ParsedStatement:
    if not isinstance(raw, dict) or set(raw) != {"kind", "head", "body"}:
        raise ValueError("Top-level schema must be exactly kind/head/body")
    kind = str(raw["kind"]).strip().lower()
    if kind not in {"fact", "rule"}:
        raise ValueError(f"Unknown kind: {kind!r}")
    head = parse_atom_json(raw["head"])
    if not isinstance(raw["body"], list):
        raise ValueError("body must be a list")
    body_unsorted = tuple(parse_atom_json(item) for item in raw["body"])
    if kind == "fact" and body_unsorted:
        raise ValueError("fact has a non-empty body")
    if kind == "rule" and not body_unsorted:
        raise ValueError("rule has an empty body")
    if len(set(body_unsorted)) != len(body_unsorted):
        raise ValueError("duplicate rule premise")
    body = tuple(sorted(body_unsorted, key=atom_sort_key))
    head_variables = {item for item in head.arguments if item in pw.VARIABLES}
    body_variables = {item for atom in body for item in atom.arguments if item in pw.VARIABLES}
    if not head_variables <= body_variables:
        raise ValueError("unsafe rule: head variable is not bound in body")

    visible = surface_tokens(source_text)
    for atom in (head, *body):
        predicate_name = atom.predicate.rsplit("::", 1)[0]
        predicate_forms = {predicate_name}
        if predicate_name in RELATION_FORMS.values():
            predicate_forms.update(key for key, canonical in RELATION_FORMS.items() if canonical == predicate_name)
        if not any(set(form.split("_")) <= visible for form in predicate_forms):
            raise ValueError(f"predicate not grounded in source: {atom.predicate}")
        for argument in atom.arguments:
            if argument in pw.VARIABLES:
                continue
            if not set(argument.split("_")) <= visible:
                raise ValueError(f"constant not grounded in source: {argument}")
    return ParsedStatement(kind, head, body)


def extract_json(text: str) -> dict:
    value = text.strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", value, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    start = value.find("{")
    if start < 0:
        raise ValueError("No JSON object in model response")
    depth = 0
    for index, character in enumerate(value[start:], start=start):
        depth += character == "{"
        depth -= character == "}"
        if depth == 0:
            return json.loads(value[start:index + 1])
    raise ValueError("Unclosed JSON object")


class FrozenLocalParser:
    """Fail-closed local parser. Cache access is mediated by the provider."""

    def __init__(self, config: dict, cache_path: Path, refresh: bool = False):
        self.config = config
        self.cache_path = cache_path
        self.prompt_hash = sha256_bytes(SYSTEM_PROMPT.encode("utf-8"))
        self.rows: dict[str, dict] = {}
        self.new_llm_attempts = 0
        self.new_prompt_tokens = 0
        self.new_completion_tokens = 0
        self.new_latency_seconds = 0.0
        if cache_path.exists() and not refresh:
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row["cache_key"]] = row

    def _cache_key(self, text: str) -> str:
        return sha256_bytes(canonical_json({
            "model": self.config["model"],
            "prompt_version": self.config["prompt_version"],
            "prompt_hash": self.prompt_hash,
            "model_digest": self.config.get("model_digest"),
            "validator_version": self.config.get("validator_version"),
            "temperature": self.config["temperature"],
            "max_tokens": self.config["max_tokens"],
            "text": text,
        }).encode("utf-8"))

    def _persist(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in sorted(self.rows.values(), key=lambda item: item["cache_key"])
        )
        temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.cache_path)

    def _call(self, text: str, repair: str | None) -> tuple[str, dict, float]:
        user_text = f"Statement: {text}"
        if repair:
            user_text += f"\nPrevious output was invalid because: {repair}. Return corrected JSON only."
        payload = {
            "model": self.config["model"],
            "temperature": self.config["temperature"],
            "max_tokens": self.config["max_tokens"],
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
        }
        request = urllib.request.Request(
            f"{self.config['base_url'].rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.config["timeout_seconds"]) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Local LLM request failed: {exc}") from exc
        latency = time.perf_counter() - started
        return raw["choices"][0]["message"]["content"], raw.get("usage", {}), latency

    def parse(self, access_id: str, text: str) -> tuple[ParsedStatement | None, dict, bool]:
        cache_key = self._cache_key(text)
        if cache_key in self.rows:
            row = self.rows[cache_key]
            parsed = validate_statement(row["parsed"], text) if row.get("valid") else None
            return parsed, row, True

        attempts = []
        error = None
        parsed = None
        for attempt in range(2):
            content, usage, latency = self._call(text, error if attempt else None)
            self.new_llm_attempts += 1
            self.new_prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
            self.new_completion_tokens += int(usage.get("completion_tokens", 0) or 0)
            self.new_latency_seconds += latency
            try:
                parsed = validate_statement(extract_json(content), text)
                error = None
            except (ValueError, json.JSONDecodeError) as exc:
                error = str(exc)
            attempts.append({
                "attempt": attempt + 1,
                "response": content,
                "usage": usage,
                "latency_seconds": latency,
                "error": error,
            })
            if parsed is not None:
                break
        row = {
            "cache_key": cache_key,
            "first_access_id": access_id,
            "text": text,
            "model": self.config["model"],
            "prompt_version": self.config["prompt_version"],
            "prompt_hash": self.prompt_hash,
            "valid": parsed is not None,
            "parsed": parsed.as_dict() if parsed else None,
            "attempts": attempts,
        }
        self.rows[cache_key] = row
        self._persist()
        return parsed, row, False


@dataclass(frozen=True)
class PublicSource:
    source_id: str
    text: str


@dataclass(frozen=True)
class PublicCase:
    case_id: str
    question_text: str
    query: Any
    sources: tuple[PublicSource, ...]

    @property
    def source_map(self) -> dict[str, PublicSource]:
        return {source.source_id: source for source in self.sources}

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(source.source_id for source in self.sources)


@dataclass(frozen=True)
class GoldSidecar:
    answer: bool | str
    query: Any
    source_statements: Mapping[str, ParsedStatement]
    minimum_source_cover: int | None


def normalize_gold_atom(atom: Any) -> Any:
    predicate, polarity = atom.predicate.rsplit("::", 1)
    canonical = normalize_predicate(predicate, len(atom.arguments)).rsplit("::", 1)[0]
    return pw.Atom(f"{canonical}::{polarity}", tuple(normalize_argument(item) for item in atom.arguments))


def gold_statement(kind: str, source_id: str, representation: str) -> ParsedStatement:
    if kind == "fact":
        return ParsedStatement("fact", normalize_gold_atom(pw.parse_fact(representation)), tuple())
    rule = pw.parse_rule(source_id, representation)
    body = tuple(sorted((normalize_gold_atom(atom) for atom in rule.body), key=atom_sort_key))
    return ParsedStatement("rule", normalize_gold_atom(rule.head), body)


def load_cases(config: dict, parser: FrozenLocalParser, input_path: Path) -> tuple[list[PublicCase], dict[str, GoldSidecar], list[dict]]:
    case_ids = [item["case_id"] for item in config["dataset"]["cases"]]
    wanted = {case_id.split("::", 1)[0] for case_id in case_ids}
    theories = {}
    with input_path.open(encoding="utf-8") as handle:
        for line in handle:
            theory = json.loads(line)
            if theory["id"] in wanted:
                theories[theory["id"]] = theory
    if set(theories) != wanted:
        raise KeyError(f"Missing theories: {sorted(wanted - set(theories))}")

    public_cases = []
    gold_sidecars = {}
    query_rows = []
    for case_id in case_ids:
        theory_id, question_id = case_id.split("::", 1)
        theory = theories[theory_id]
        question = theory["questions"][question_id]
        query_parse, query_row, cache_hit = parser.parse(f"{case_id}::query", question["question"])
        query_rows.append({**query_row, "access_id": f"{case_id}::query", "cache_hit": cache_hit})
        if query_parse is None or query_parse.kind != "fact":
            raise ValueError(f"Query parser failed for {case_id}")
        sources = []
        gold_sources = {}
        for kind, records in (("fact", theory["triples"]), ("rule", theory["rules"])):
            for source_id, record in records.items():
                sources.append(PublicSource(source_id, record["text"]))
                gold_sources[source_id] = gold_statement(kind, source_id, record["representation"])
        covers = pw.source_ids_for_proof(question, theory.get("mappings"))
        public_cases.append(PublicCase(case_id, question["question"], query_parse.head, tuple(sources)))
        gold_sidecars[case_id] = GoldSidecar(
            answer=question["answer"],
            query=normalize_gold_atom(pw.parse_fact(question["representation"])),
            source_statements=gold_sources,
            minimum_source_cover=min((len(cover) for cover in covers), default=None),
        )
    return public_cases, gold_sidecars, query_rows


class HiddenOutcomeProvider:
    """The only object allowed to turn an unexecuted source into symbols."""

    def __init__(self, parser: FrozenLocalParser):
        self.parser = parser
        self.materialize_count = 0
        self.cache_hits = 0
        self.events: list[dict] = []

    def materialize(self, case_id: str, source: PublicSource) -> ParsedStatement | None:
        self.materialize_count += 1
        parsed, row, cache_hit = self.parser.parse(f"{case_id}::{source.source_id}", source.text)
        self.cache_hits += int(cache_hit)
        self.events.append({
            "case_id": case_id,
            "source_id": source.source_id,
            "cache_key": row["cache_key"],
            "cache_hit": cache_hit,
            "valid": parsed is not None,
            "signature": parsed.signature if parsed else None,
        })
        return parsed


@dataclass(frozen=True)
class RealState:
    selected: frozenset[str]
    committed_signatures: tuple[str, ...]
    facts: frozenset[Any]
    schemas: tuple[Any, ...]
    ground_rules: tuple[Any, ...]
    closure: frozenset[Any]
    proof_sources: Mapping[Any, frozenset[str]]
    frontier: tuple[Any, ...]
    status: str
    endpoint: Any | None
    endpoint_sources: tuple[str, ...]
    source_set_proof_verified: bool

    @property
    def key(self) -> tuple:
        return (
            tuple(sorted(self.selected)),
            self.committed_signatures,
            tuple(sorted(atom_text(atom) for atom in self.closure)),
        )


def recursive_frontier(targets: Iterable[Any], closure: set[Any], rules: Sequence[Any]) -> tuple[Any, ...]:
    producers: dict[Any, list[Any]] = defaultdict(list)
    for rule in rules:
        producers[rule.head].append(rule)
    frontier = set()
    pending = list(targets)
    visited = set()
    while pending:
        atom = pending.pop()
        if atom in closure or atom in visited:
            continue
        visited.add(atom)
        candidate_rules = producers.get(atom, [])
        if not candidate_rules:
            frontier.add(atom)
            continue
        missing_found = False
        for rule in candidate_rules:
            missing = [premise for premise in rule.body if premise not in closure]
            if missing:
                pending.extend(missing)
                missing_found = True
        if not missing_found:
            frontier.add(atom)
    return tuple(sorted(frontier, key=atom_sort_key))


def program_parts(committed: Mapping[str, ParsedStatement | None], query: Any) -> tuple[set[Any], list[Any], list[Any], tuple[str, ...]]:
    facts = set()
    schemas = []
    signatures = []
    constants = {arg for arg in query.arguments if arg not in pw.VARIABLES}
    for source_id in sorted(committed):
        statement = committed[source_id]
        if statement is None:
            signatures.append(f"{source_id}:invalid")
            continue
        signatures.append(f"{source_id}:{statement.signature}")
        if statement.kind == "fact":
            facts.add(statement.head)
        else:
            schemas.append(pw.Rule(source_id, statement.body, statement.head))
        for atom in (statement.head, *statement.body):
            constants.update(arg for arg in atom.arguments if arg not in pw.VARIABLES)
    ground = pw.ground_rules(schemas, sorted(constants))
    return facts, schemas, ground, tuple(signatures)


def provenance_closure(facts: set[Any], ground_rules: Sequence[Any]) -> tuple[set[Any], dict[Any, frozenset[str]]]:
    closure = set(facts)
    proof_sources: dict[Any, frozenset[str]] = {}
    return closure, proof_sources


def build_real_state(case: PublicCase, committed: Mapping[str, ParsedStatement | None]) -> RealState:
    facts, schemas, ground_rules, signatures = program_parts(committed, case.query)
    closure = set(facts)
    fact_supports: dict[Any, list[str]] = defaultdict(list)
    for source_id, statement in committed.items():
        if statement is not None and statement.kind == "fact":
            fact_supports[statement.head].append(source_id)
    proof_sources: dict[Any, frozenset[str]] = {
        atom: frozenset({min(source_ids)})
        for atom, source_ids in fact_supports.items()
    }
    changed = True
    while changed:
        changed = False
        for rule in ground_rules:
            if not all(premise in closure for premise in rule.body):
                continue
            candidate = frozenset({rule.rule_id}).union(*(proof_sources[premise] for premise in rule.body))
            old = proof_sources.get(rule.head)
            if rule.head not in closure:
                closure.add(rule.head)
                proof_sources[rule.head] = candidate
                changed = True
            elif old is None or (len(candidate), sorted(candidate)) < (len(old), sorted(old)):
                proof_sources[rule.head] = candidate
                changed = True

    independent = pw.saturate(facts, ground_rules)[0]
    if closure != independent:
        raise AssertionError("provenance closure differs from independent reference LFP")
    opposite = pw.complement(case.query)
    has_query = case.query in closure
    has_opposite = opposite in closure
    if has_query and has_opposite:
        status, endpoint = "Both", case.query
    elif has_query:
        status, endpoint = "Entailed", case.query
    elif has_opposite:
        status, endpoint = "Contradicted", opposite
    elif len(committed) == len(case.sources):
        status, endpoint = "PR-Unknown", None
    else:
        status, endpoint = "Unresolved", None
    endpoint_sources = tuple(sorted(proof_sources.get(endpoint, frozenset()))) if endpoint else tuple()
    source_set_proof_verified = False
    if endpoint is not None:
        proof_program = {source_id: committed[source_id] for source_id in endpoint_sources}
        subset_facts, _subset_schemas, subset_ground, _ = program_parts(proof_program, case.query)
        source_set_proof_verified = endpoint in pw.saturate(subset_facts, subset_ground)[0]
        if not source_set_proof_verified:
            raise AssertionError("source-linked proof failed independent verifier")
    frontier = recursive_frontier((case.query, opposite), closure, ground_rules)
    return RealState(
        selected=frozenset(committed),
        committed_signatures=signatures,
        facts=frozenset(facts),
        schemas=tuple(schemas),
        ground_rules=tuple(ground_rules),
        closure=frozenset(closure),
        proof_sources=proof_sources,
        frontier=frontier,
        status=status,
        endpoint=endpoint,
        endpoint_sources=endpoint_sources,
        source_set_proof_verified=source_set_proof_verified,
    )


@dataclass(frozen=True)
class SurfaceClause:
    kind: str
    head_predicates: frozenset[str]
    body_predicates: frozenset[str]
    generic: bool


def canonical_surface_predicate(token: str) -> str:
    token = re.sub(r"[^a-z]", "", token.lower())
    return RELATION_FORMS.get(token, token)


def literal_predicates(text: str) -> frozenset[str]:
    """Cheap directional sketch from public text; never returns atoms/bindings."""
    lowered = text.lower().strip(" .")
    found = {
        canonical_surface_predicate(token)
        for token in re.findall(r"\b(?:see|sees|eat|eats|like|likes|need|needs|visit|visits|chase|chases)\b", lowered)
    }
    copular = re.search(r"\b(?:is|are)\s+(.+)$", lowered)
    if copular and not found:
        tail = copular.group(1)
        found.update(
            canonical_surface_predicate(token)
            for token in re.findall(r"[a-z]+", tail)
            if token not in STOPWORDS and token not in {"not"}
        )
    if not found:
        bare = [token for token in re.findall(r"[a-z]+", lowered) if token not in STOPWORDS]
        if len(bare) == 1:
            found.add(canonical_surface_predicate(bare[0]))
    return frozenset(token for token in found if token)


def surface_clause(text: str) -> SurfaceClause:
    lowered = text.lower().strip(" .")
    generic = bool(re.search(r"\b(?:someone|something|people|things|they|them|it)\b", lowered))
    if lowered.startswith("if ") and " then " in lowered:
        body_text, head_text = lowered[3:].rsplit(" then ", 1)
        body_parts = re.split(r"\s+and\s+|,\s*", body_text)
        body = set().union(*(literal_predicates(part) for part in body_parts))
        return SurfaceClause("rule", literal_predicates(head_text), frozenset(body), generic)
    class_rule = re.match(r"(?:all\s+)?(.+?)\s+(?:people|things)\s+are\s+(.+)$", lowered)
    if class_rule:
        body = {
            canonical_surface_predicate(token)
            for token in re.findall(r"[a-z]+", class_rule.group(1))
            if token not in STOPWORDS
        }
        head = literal_predicates(f"something is {class_rule.group(2)}")
        return SurfaceClause("rule", head, frozenset(body), True)
    return SurfaceClause("fact", literal_predicates(lowered), frozenset(), False)


def predicate_name(atom: Any) -> str:
    return atom.predicate.rsplit("::", 1)[0]


@dataclass(frozen=True)
class SketchState:
    selected: frozenset[str]
    available_predicates: frozenset[str]
    obligation_predicates: frozenset[str]
    remaining_steps: int
    value: float

    @property
    def key(self) -> tuple:
        return (
            tuple(sorted(self.selected)),
            tuple(sorted(self.available_predicates)),
            tuple(sorted(self.obligation_predicates)),
            self.remaining_steps,
        )


class SketchSimulator:
    """Predicate-direction sketch from public text; never emits atoms/rules."""

    def __init__(self, case: PublicCase, real_state: RealState, remaining_budget: int):
        self.case = case
        self.real_state = real_state
        self.remaining_budget = remaining_budget
        self.base_selected = real_state.selected
        self.source_tokens = {source.source_id: surface_tokens(source.text) for source in case.sources}
        self.clauses = {source.source_id: surface_clause(source.text) for source in case.sources}
        counts = Counter(token for tokens in self.source_tokens.values() for token in tokens)
        total = len(self.source_tokens)
        self.idf = {token: math.log((total + 1) / (count + 1)) + 1 for token, count in counts.items()}
        self.base_available = frozenset(predicate_name(atom) for atom in real_state.closure)
        self.base_obligations = frozenset(predicate_name(atom) for atom in real_state.frontier)
        self.frontier_entities = frozenset(
            token
            for atom in real_state.frontier
            for argument in atom.arguments
            if argument not in pw.VARIABLES
            for token in argument.split("_")
        )
        self.goal_predicates = frozenset({predicate_name(case.query)})
        relevant_predicates = set(self.base_obligations or self.goal_predicates)
        relevant_sources = set()
        changed = True
        while changed:
            changed = False
            for source_id, clause in self.clauses.items():
                if clause.head_predicates & relevant_predicates and source_id not in relevant_sources:
                    relevant_sources.add(source_id)
                    before = len(relevant_predicates)
                    relevant_predicates.update(clause.body_predicates)
                    changed = changed or len(relevant_predicates) != before
        self.relevant_sources = frozenset(relevant_sources)
        self.transitions = 0

    def _summarize(self, selected: frozenset[str], remaining_steps: int) -> SketchState:
        hypothetical = selected - self.base_selected
        available = set(self.base_available)
        for source_id in hypothetical:
            clause = self.clauses[source_id]
            if clause.kind == "fact":
                available.update(clause.head_predicates)
        changed = True
        while changed:
            changed = False
            for source_id in hypothetical:
                clause = self.clauses[source_id]
                if clause.kind == "rule" and clause.body_predicates <= available:
                    before = len(available)
                    available.update(clause.head_predicates)
                    changed = changed or len(available) != before

        selected_rules = [self.clauses[source_id] for source_id in hypothetical if self.clauses[source_id].kind == "rule"]

        def unresolved(predicate: str, visiting: frozenset[str]) -> frozenset[str]:
            if predicate in available:
                return frozenset()
            if predicate in visiting:
                return frozenset({predicate})
            candidates = [clause for clause in selected_rules if predicate in clause.head_predicates]
            if not candidates:
                return frozenset({predicate})
            alternatives = []
            for clause in candidates:
                missing = frozenset().union(
                    *(unresolved(item, visiting | {predicate}) for item in clause.body_predicates)
                ) if clause.body_predicates else frozenset()
                alternatives.append(missing)
            return min(alternatives, key=lambda item: (len(item), tuple(sorted(item))))

        starting_obligations = self.base_obligations or self.goal_predicates
        obligations = frozenset().union(*(unresolved(item, frozenset()) for item in starting_obligations))
        query_ready = float(bool(self.goal_predicates & available))
        relevant_selected = len(hypothetical & self.relevant_sources)
        relevant_coverage = relevant_selected / max(1, min(len(self.relevant_sources), self.remaining_budget))
        useful_ratio = relevant_selected / max(1, len(hypothetical))
        obligation_progress = 1.0 / (1.0 + len(obligations))
        value = 0.48 * query_ready + 0.28 * obligation_progress + 0.16 * relevant_coverage + 0.08 * useful_ratio
        return SketchState(selected, frozenset(available), obligations, remaining_steps, value)

    def root(self) -> SketchState:
        return self._summarize(self.real_state.selected, self.remaining_budget)

    def remaining_actions(self, state: SketchState) -> tuple[str, ...]:
        return tuple(source_id for source_id in self.case.source_ids if source_id not in state.selected)

    def prior(self, state: SketchState, source_id: str) -> float:
        clause = self.clauses[source_id]
        source = self.source_tokens[source_id]
        head_hit = len(clause.head_predicates & state.obligation_predicates)
        body_ready = (
            len(clause.body_predicates & state.available_predicates) / max(1, len(clause.body_predicates))
            if clause.kind == "rule" else 1.0
        )
        if clause.generic or not self.frontier_entities:
            entity_compatibility = 1.0
        else:
            entity_compatibility = 1.0 if source & self.frontier_entities else 0.05
        relevant = float(source_id in self.relevant_sources)
        lexical = sum(self.idf.get(token, 1.0) for token in source & surface_tokens(self.case.question_text))
        return (
            0.05
            + 6.0 * head_hit * entity_compatibility
            + 3.5 * head_hit * body_ready * entity_compatibility
            + 1.5 * relevant
            + 0.10 * lexical
        )

    def transition(self, state: SketchState, source_id: str) -> SketchState:
        if source_id in state.selected or state.remaining_steps <= 0:
            raise ValueError("invalid sketch transition")
        self.transitions += 1
        return self._summarize(state.selected | {source_id}, state.remaining_steps - 1)


@dataclass
class EdgeStats:
    child_id: str
    visits: int = 0
    value_sum: float = 0.0

    @property
    def q(self) -> float:
        return self.value_sum / self.visits if self.visits else 0.0


@dataclass
class SearchNode:
    node_id: str
    state: SketchState
    visits: int = 0
    value_sum: float = 0.0
    edges: dict[str, EdgeStats] = field(default_factory=dict)


class MonteCarloPlanner:
    """Paired TreeMCTS/MCGS planner over the same non-symbolic simulator."""

    def __init__(self, simulator: SketchSimulator, config: dict, seed: int, merge_states: bool, decision_step: int):
        self.sim = simulator
        self.config = config
        self.seed = seed
        self.merge_states = merge_states
        self.decision_step = decision_step
        self.nodes: dict[str, SearchNode] = {}
        self.graph_index: dict[tuple, str] = {}
        self.next_node = 0
        self.transposition_hits = 0
        self.validated_merges = 0
        self.expansions = 0
        self.max_depth = 0
        self.backprop_updates = 0

    def _node(self, state: SketchState, history: tuple[str, ...]) -> SearchNode:
        if self.merge_states and state.key in self.graph_index:
            existing = self.nodes[self.graph_index[state.key]]
            if existing.state != state or self.sim.remaining_actions(existing.state) != self.sim.remaining_actions(state):
                raise AssertionError("non-equivalent transposition")
            self.transposition_hits += 1
            self.validated_merges += 1
            return existing
        node_id = f"n{self.next_node}"
        self.next_node += 1
        node = SearchNode(node_id, state)
        self.nodes[node_id] = node
        if self.merge_states:
            self.graph_index[state.key] = node_id
        return node

    def _jitter(self, simulation: int, depth: int, state: SketchState, action: str) -> float:
        return stable_unit(self.seed, self.decision_step, simulation, depth, state.key, action)

    def _expand(self, node: SearchNode, action: str, history: tuple[str, ...]) -> SearchNode:
        child_state = self.sim.transition(node.state, action)
        child = self._node(child_state, history + (action,))
        node.edges[action] = EdgeStats(child.node_id)
        self.expansions += 1
        return child

    def _rollout(self, state: SketchState, simulation: int, depth: int) -> SketchState:
        current = state
        while depth < self.config["rollout_depth"] and current.remaining_steps > 0:
            actions = self.sim.remaining_actions(current)
            if not actions:
                break
            action = max(
                actions,
                key=lambda item: (self.sim.prior(current, item), self._jitter(simulation, depth, current, item)),
            )
            current = self.sim.transition(current, action)
            depth += 1
            self.max_depth = max(self.max_depth, depth)
        return current

    def choose(self) -> tuple[str, dict]:
        root_state = self.sim.root()
        root = self._node(root_state, tuple())
        horizon = min(self.config["rollout_depth"], root_state.remaining_steps)
        if horizon <= 0:
            raise RuntimeError("No sketch budget remains")
        for simulation in range(self.config["simulations_per_decision"]):
            node = root
            path_nodes = [root]
            path_edges: list[tuple[SearchNode, str]] = []
            history: tuple[str, ...] = tuple()
            depth = 0
            expanded = False
            while depth < horizon and node.state.remaining_steps > 0:
                actions = self.sim.remaining_actions(node.state)
                if not actions:
                    break
                unexpanded = [action for action in actions if action not in node.edges]
                if unexpanded:
                    action = max(
                        unexpanded,
                        key=lambda item: (self.sim.prior(node.state, item), self._jitter(simulation, depth, node.state, item)),
                    )
                    child = self._expand(node, action, history)
                    path_edges.append((node, action))
                    history += (action,)
                    node = child
                    path_nodes.append(node)
                    depth += 1
                    expanded = True
                    self.max_depth = max(self.max_depth, depth)
                    break
                log_parent = math.log(max(2, node.visits + 1))
                action = max(
                    actions,
                    key=lambda item: (
                        node.edges[item].q
                        + self.config["exploration_constant"]
                        * self.sim.prior(node.state, item)
                        / (1 + self.sim.prior(node.state, item))
                        * math.sqrt(log_parent / (1 + node.edges[item].visits)),
                        self._jitter(simulation, depth, node.state, item),
                    ),
                )
                path_edges.append((node, action))
                history += (action,)
                node = self.nodes[node.edges[action].child_id]
                path_nodes.append(node)
                depth += 1
                self.max_depth = max(self.max_depth, depth)
            final = self._rollout(node.state, simulation, depth) if expanded else node.state
            reward = final.value
            for visited in path_nodes:
                visited.visits += 1
                visited.value_sum += reward
                self.backprop_updates += 1
            for parent, action in path_edges:
                parent.edges[action].visits += 1
                parent.edges[action].value_sum += reward
        if not root.edges:
            raise RuntimeError("Planner failed to expand a root action")
        action = max(
            root.edges,
            key=lambda item: (
                root.edges[item].visits,
                root.edges[item].q,
                self.sim.prior(root.state, item),
                stable_unit(self.seed, self.decision_step, "root", item),
            ),
        )
        return action, {
            "root_visits": root.visits,
            "root_children": {
                item: {"visits": edge.visits, "q": edge.q}
                for item, edge in sorted(root.edges.items())
            },
            "nodes": len(self.nodes),
            "expansions": self.expansions,
            "transposition_hits": self.transposition_hits,
            "validated_merges": self.validated_merges,
            "max_depth": self.max_depth,
            "backprop_updates": self.backprop_updates,
            "simulator_transitions": self.sim.transitions,
        }


def choose_non_monte_carlo(policy: str, simulator: SketchSimulator, seed: int, step: int) -> tuple[str, dict]:
    root = simulator.root()
    actions = simulator.remaining_actions(root)
    if not actions:
        raise RuntimeError("No source remains")
    if policy == "random":
        action = max(actions, key=lambda item: stable_unit(seed, step, root.key, item))
    elif policy == "surface_obligation_greedy":
        action = max(actions, key=lambda item: (simulator.prior(root, item), stable_unit(seed, step, item)))
    elif policy == "sketch_greedy":
        action = max(
            actions,
            key=lambda item: (
                simulator.transition(root, item).value,
                simulator.prior(root, item),
                stable_unit(seed, step, item),
            ),
        )
    else:
        raise ValueError(policy)
    return action, {"simulator_transitions": simulator.transitions}


def run_policy(case: PublicCase, policy: str, search: dict, seed: int, provider: HiddenOutcomeProvider) -> dict:
    source_map = case.source_map
    committed: dict[str, ParsedStatement | None] = {}
    state = build_real_state(case, committed)
    trace = []
    aggregate = Counter()
    budget = min(int(search["real_action_budget"]), len(case.sources))
    started = time.perf_counter()
    for step in range(budget):
        simulator = SketchSimulator(case, state, budget - step)
        before_materialize = provider.materialize_count
        if policy in {"tree_mcts_sketch", "lfp_mcgs_sketch"}:
            planner = MonteCarloPlanner(
                simulator,
                search,
                seed,
                merge_states=policy == "lfp_mcgs_sketch",
                decision_step=step,
            )
            action, search_stats = planner.choose()
        else:
            action, search_stats = choose_non_monte_carlo(policy, simulator, seed, step)
        if provider.materialize_count != before_materialize:
            raise AssertionError("planner accessed hidden parse before root action")
        previous_closure = set(state.closure)
        previous_frontier = set(state.frontier)
        parsed = provider.materialize(case.case_id, source_map[action])
        committed[action] = parsed
        state = build_real_state(case, committed)
        for key, value in search_stats.items():
            if isinstance(value, (int, float)):
                aggregate[key] += value
        trace.append({
            "step": step + 1,
            "action": action,
            "source_text": source_map[action].text,
            "parse_valid": parsed is not None,
            "parse_signature": parsed.signature if parsed else None,
            "new_closure_atoms": sorted(atom_text(atom) for atom in set(state.closure) - previous_closure),
            "closed_frontier_atoms": sorted(atom_text(atom) for atom in previous_frontier - set(state.frontier)),
            "closure_size": len(state.closure),
            "frontier": [atom_text(atom) for atom in state.frontier],
            "status": state.status,
            "search": search_stats,
        })
        if state.endpoint is not None:
            break
    return {
        "case_id": case.case_id,
        "policy": policy,
        "seed": seed,
        "real_action_budget": budget,
        "actions_used": len(committed),
        "sequence": list(committed),
        "status": state.status,
        "endpoint": atom_text(state.endpoint) if state.endpoint else None,
        "source_set_proof_verified": state.source_set_proof_verified,
        "proof_sources": list(state.endpoint_sources),
        "proof_source_count": len(state.endpoint_sources),
        "final_closure_size": len(state.closure),
        "final_frontier": [atom_text(atom) for atom in state.frontier],
        "search_totals": dict(aggregate),
        "runtime_seconds": time.perf_counter() - started,
        "trace": trace,
    }


def run_invariant_tests(case: PublicCase, search: dict, provider: HiddenOutcomeProvider) -> dict:
    atom_a = pw.Atom("a::+", ("c",))
    atom_b = pw.Atom("b::+", ("c",))
    schemas = [
        pw.Rule("r1", (pw.Atom("a::+", ("someone",)),), pw.Atom("b::+", ("someone",))),
        pw.Rule("r2", (pw.Atom("b::+", ("someone",)),), pw.Atom("a::+", ("someone",))),
    ]
    unseeded = pw.saturate(set(), pw.ground_rules(schemas, ["c"]))[0]
    if unseeded:
        raise AssertionError("unseeded positive cycle self-supported")

    fact = ParsedStatement("fact", atom_a, tuple())
    rule = ParsedStatement("rule", atom_b, (atom_a,))
    toy_case = PublicCase("toy", "B holds.", atom_b, (PublicSource("f", "A holds."), PublicSource("r", "If A holds then B holds.")))
    state_f = build_real_state(toy_case, {"f": fact})
    state_r = build_real_state(toy_case, {"r": rule})
    if atom_b in state_f.closure or atom_a in state_r.closure:
        raise AssertionError("branch-local state contamination")
    state_fr = build_real_state(toy_case, {"f": fact, "r": rule})
    state_rf = build_real_state(toy_case, {"r": rule, "f": fact})
    if state_fr.key != state_rf.key or atom_b not in state_fr.closure:
        raise AssertionError("order-equivalent real states failed canonical merge test")

    real = build_real_state(case, {})
    simulator = SketchSimulator(case, real, min(4, len(case.sources)))
    planner = MonteCarloPlanner(simulator, search, 991, True, 0)
    before = provider.materialize_count
    _action, stats = planner.choose()
    if provider.materialize_count != before:
        raise AssertionError("hidden provider accessed by planner sentinel")
    if stats["max_depth"] < 2 or stats["backprop_updates"] <= stats["root_visits"]:
        raise AssertionError("planner did not execute multi-step backpropagation")
    if stats["transposition_hits"] <= 0:
        raise AssertionError("MCGS did not encounter an abstract transposition")
    return {
        "unseeded_cycle_empty": True,
        "branch_isolation": True,
        "order_equivalent_real_key": True,
        "hidden_access_sentinel": True,
        "planner_depth": stats["max_depth"],
        "planner_backprop_updates": stats["backprop_updates"],
        "abstract_transposition_hits": stats["transposition_hits"],
    }


def score_trials(trials: Sequence[dict], gold: Mapping[str, GoldSidecar]) -> tuple[list[dict], dict]:
    scored = []
    for trial in trials:
        sidecar = gold[trial["case_id"]]
        expected = "PR-Unknown" if sidecar.answer == "Unknown" else ("Entailed" if sidecar.answer is True else "Contradicted")
        row = dict(trial)
        row["gold_answer_offline"] = sidecar.answer
        row["gold_minimum_source_cover_offline"] = sidecar.minimum_source_cover
        row["expected_status_offline"] = expected
        row["proof_recovered"] = trial["source_set_proof_verified"] and trial["status"] == expected
        row["unknown_false_entailment"] = sidecar.answer == "Unknown" and trial["status"] in {"Entailed", "Contradicted", "Both"}
        scored.append(row)
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in scored:
        grouped[row["policy"]][row["case_id"]].append(row)
    policy_summary = {}
    for policy, case_rows in sorted(grouped.items()):
        flat = [row for rows in case_rows.values() for row in rows]
        productive = [row for row in flat if gold[row["case_id"]].answer != "Unknown"]
        unknown = [row for row in flat if gold[row["case_id"]].answer == "Unknown"]
        policy_summary[policy] = {
            "trials": len(flat),
            "productive_trials": len(productive),
            "proof_recovery_rate": sum(row["proof_recovered"] for row in productive) / max(1, len(productive)),
            "unique_productive_cases_with_proof": len({row["case_id"] for row in productive if row["proof_recovered"]}),
            "source_set_verified_proofs": sum(row["source_set_proof_verified"] for row in productive),
            "unknown_trials": len(unknown),
            "unknown_false_entailments": sum(row["unknown_false_entailment"] for row in unknown),
            "mean_actions_used": sum(row["actions_used"] for row in flat) / max(1, len(flat)),
            "mcgs_transposition_hits": sum(row["search_totals"].get("transposition_hits", 0) for row in flat),
            "search_nodes": sum(row["search_totals"].get("nodes", 0) for row in flat),
        }
    return scored, policy_summary


def audit_all_sources(cases: Sequence[PublicCase], parser: FrozenLocalParser) -> list[dict]:
    rows = []
    for case in cases:
        for source in case.sources:
            parsed, cache_row, cache_hit = parser.parse(f"audit::{case.case_id}::{source.source_id}", source.text)
            rows.append({
                "case_id": case.case_id,
                "source_id": source.source_id,
                "text": source.text,
                "cache_key": cache_row["cache_key"],
                "cache_hit": cache_hit,
                "valid": parsed is not None,
                "signature": parsed.signature if parsed else None,
                "parsed": parsed.as_dict() if parsed else None,
            })
    return rows


def extract_all_diagnostic(
    cases: Sequence[PublicCase],
    audit_rows: Sequence[dict],
    gold: Mapping[str, GoldSidecar],
) -> dict[str, dict]:
    by_case: dict[str, dict[str, ParsedStatement | None]] = defaultdict(dict)
    for row in audit_rows:
        by_case[row["case_id"]][row["source_id"]] = (
            validate_statement(row["parsed"], row["text"]) if row["valid"] else None
        )
    output = {}
    for case in cases:
        state = build_real_state(case, by_case[case.case_id])
        expected = "PR-Unknown" if gold[case.case_id].answer == "Unknown" else (
            "Entailed" if gold[case.case_id].answer is True else "Contradicted"
        )
        output[case.case_id] = {
            "status": state.status,
            "expected_status_offline": expected,
            "recovered": state.status == expected and (
                expected == "PR-Unknown" or state.source_set_proof_verified
            ),
            "source_set_proof_verified": state.source_set_proof_verified,
            "proof_sources": list(state.endpoint_sources),
        }
    return output


def parser_diagnostics(
    provider: HiddenOutcomeProvider,
    query_rows: Sequence[dict],
    source_audit_rows: Sequence[dict],
    gold: Mapping[str, GoldSidecar],
) -> dict:
    query_exact = 0
    for row in query_rows:
        case_id = row["access_id"].split("::query", 1)[0]
        parsed = validate_statement(row["parsed"], row["text"]) if row.get("valid") else None
        query_exact += int(parsed is not None and parsed.kind == "fact" and parsed.head == gold[case_id].query)
    exact = 0
    valid = 0
    for row in source_audit_rows:
        valid += int(row["valid"])
        if row["valid"]:
            expected = gold[row["case_id"]].source_statements[row["source_id"]].signature
            exact += int(row["signature"] == expected)
    total = len(source_audit_rows)
    return {
        "query_total": len(query_rows),
        "query_exact": query_exact,
        "query_exact_rate": query_exact / max(1, len(query_rows)),
        "audited_source_instances": total,
        "audited_source_coverage": 1.0,
        "source_valid": valid,
        "source_valid_rate": valid / max(1, total),
        "source_semantic_exact": exact,
        "source_semantic_exact_rate": exact / max(1, total),
        "logical_materializations": provider.materialize_count,
        "parse_cache_hits": provider.cache_hits,
        "new_llm_attempts": provider.parser.new_llm_attempts,
        "new_prompt_tokens": provider.parser.new_prompt_tokens,
        "new_completion_tokens": provider.parser.new_completion_tokens,
        "new_latency_seconds": provider.parser.new_latency_seconds,
    }


def smoke_gates(
    config: dict,
    scored: Sequence[dict],
    summaries: Mapping[str, dict],
    parser_stats: dict,
    invariants: dict,
    extract_all: Mapping[str, dict],
) -> dict:
    gates = config["smoke_gates"]
    mcgs_rows = [row for row in scored if row["policy"] == "lfp_mcgs_sketch"]
    productive_proofs = [row for row in scored if row["proof_recovered"]]
    results = {
        "source_parse_valid_rate": parser_stats["source_valid_rate"] >= gates["minimum_valid_parse_rate"],
        "source_parse_exact_rate_diagnostic": parser_stats["source_semantic_exact_rate"] >= gates["minimum_semantic_exact_parse_rate"],
        "query_parse_exact": parser_stats["query_exact"] == parser_stats["query_total"],
        "extract_all_productive_ceiling": sum(
            row["recovered"] for case_id, row in extract_all.items()
            if row["expected_status_offline"] != "PR-Unknown"
        ) >= gates["minimum_extract_all_productive_cases"],
        "extract_all_unknown_sanity": all(
            row["status"] == "PR-Unknown"
            for row in extract_all.values()
            if row["expected_status_offline"] == "PR-Unknown"
        ),
        "minimum_verified_proofs": len(productive_proofs) >= gates["minimum_verified_proofs"],
        "mcgs_unique_cases": len({row["case_id"] for row in mcgs_rows if row["proof_recovered"]}) >= gates["minimum_mcgs_unique_cases"],
        "mcgs_multisource_proof": (not gates["require_multisource_proof"]) or any(
            row["proof_recovered"] and row["proof_source_count"] >= 2 for row in mcgs_rows
        ),
        "zero_unknown_false_entailment": not any(row["unknown_false_entailment"] for row in scored),
        "mcgs_transposition_hit": (not gates["require_mcgs_transposition_hit"]) or summaries["lfp_mcgs_sketch"]["mcgs_transposition_hits"] > 0,
        "tree_and_graph_executed": (not gates["require_tree_and_graph_execution"]) or all(
            name in summaries and summaries[name]["search_nodes"] > 0
            for name in ("tree_mcts_sketch", "lfp_mcgs_sketch")
        ),
        "core_invariants": all(value is True or isinstance(value, int) and value > 0 for value in invariants.values()),
    }
    return {"passed": all(results.values()), "checks": results}


def git_metadata() -> dict:
    def run(*args: str) -> str:
        return subprocess.run(args, cwd=NAACL_ROOT.parent, text=True, capture_output=True, check=False).stdout.strip()
    return {
        "commit": run("git", "rev-parse", "HEAD"),
        "branch": run("git", "branch", "--show-current"),
        "workspace_dirty": bool(run("git", "status", "--porcelain")),
    }


def model_metadata(config: dict) -> dict:
    try:
        base = config["base_url"].split("/v1", 1)[0]
        with urllib.request.urlopen(f"{base}/api/tags", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        match = next((item for item in payload.get("models", []) if item.get("name") == config["model"]), None)
        return match or {"name": config["model"], "available": False}
    except Exception as exc:  # metadata failure must not disguise experiment output
        return {"name": config["model"], "metadata_error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=EXPERIMENT_ROOT / "config.json")
    parser.add_argument("--refresh-parser", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    input_path = NAACL_ROOT / config["dataset"]["path"]
    results_dir = EXPERIMENT_ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    local_parser = FrozenLocalParser(config["parser"], results_dir / "parser_cache.jsonl", args.refresh_parser)

    started = time.time()
    public_cases, gold, query_rows = load_cases(config, local_parser, input_path)
    provider = HiddenOutcomeProvider(local_parser)
    invariants = run_invariant_tests(public_cases[0], config["search"], provider)
    trials = []
    for case in public_cases:
        for policy in config["search"]["policies"]:
            for seed in config["search"]["seeds"]:
                row = run_policy(case, policy, config["search"], seed, provider)
                trials.append(row)
                print(
                    f"[{len(trials):03d}] {case.case_id} {policy} seed={seed} "
                    f"status={row['status']} actions={row['actions_used']} proof={row['source_set_proof_verified']}",
                    flush=True,
                )

    source_audit_rows = audit_all_sources(public_cases, local_parser)
    extract_all = extract_all_diagnostic(public_cases, source_audit_rows, gold)
    scored, policy_summary = score_trials(trials, gold)
    parser_stats = parser_diagnostics(provider, query_rows, source_audit_rows, gold)
    gates = smoke_gates(config, scored, policy_summary, parser_stats, invariants, extract_all)
    results = {
        "schema_version": 2,
        "run_id": config["run_id"],
        "run_status": "complete",
        "evidence_status": config["evidence_status"],
        "claim_boundary": config["claim_boundary"],
        "access_model": {
            "free": "query text, raw source text, surface/entity index, current committed program-relative closure/frontier",
            "charged_root_action": "one source materialization through local LLM (or its frozen cache), validator, commit, exact LFP",
            "forbidden_in_rollout": "answer, MAC, proofs, gold representations, unexecuted parser outcomes, hypothetical atoms/rules",
        },
        "cases": [case.case_id for case in public_cases],
        "case_roles": {
            case.case_id: "unknown_cycle_control" if gold[case.case_id].answer == "Unknown" else "productive_proof"
            for case in public_cases
        },
        "parser": parser_stats,
        "extract_all_local_lfp": extract_all,
        "policy_summary": policy_summary,
        "invariants": invariants,
        "smoke_gates": gates,
        "duration_seconds": time.time() - started,
        "limitations": [
            "Six curated ProofWriter dev cases are an integration smoke, not a performance estimate.",
            "The rollout simulator is a hand-built surface/obligation sketch, not a learned p_phi.",
            "MCGS transpositions are abstract acquisition-state merges; real-program merge benefit is not established.",
            "The verifier checks source-set sufficiency under the committed program; it does not yet emit a stepwise proof DAG.",
            "Unknown controls remain Unresolved under partial coverage and do not certify global non-entailment.",
            "No matched SCC-vs-DAG causal result, revision transition, external domain, or LLM-family generalization is tested.",
        ],
    }
    trials_path = results_dir / "experiment_v2_trials.jsonl"
    parser_audit_path = results_dir / "experiment_v2_parser_audit.jsonl"
    results_path = results_dir / "experiment_v2_results.json"
    cache_path = results_dir / "parser_cache.jsonl"
    write_jsonl_atomic(trials_path, scored)
    write_jsonl_atomic(parser_audit_path, source_audit_rows)
    write_json_atomic(results_path, results)
    manifest = {
        "run_id": config["run_id"],
        "created_unix": time.time(),
        "inputs": {
            "config": {"path": str(args.config), "sha256": sha256_file(args.config)},
            "runner": {"path": str(SCRIPT_PATH), "sha256": sha256_file(SCRIPT_PATH)},
            "audit_engine": {"path": str(AUDIT_PATH), "sha256": sha256_file(AUDIT_PATH)},
            "dataset": {"path": str(input_path), "sha256": sha256_file(input_path)},
            "parser_cache": {"path": str(cache_path), "sha256": sha256_file(cache_path)},
        },
        "outputs": {
            "trials": {"path": str(trials_path), "sha256": sha256_file(trials_path)},
            "parser_audit": {"path": str(parser_audit_path), "sha256": sha256_file(parser_audit_path)},
            "results": {"path": str(results_path), "sha256": sha256_file(results_path)},
        },
        "parser_prompt_hash": local_parser.prompt_hash,
        "parser_validator_version": config["parser"].get("validator_version"),
        "simulator_kind": config["search"]["simulator_kind"],
        "model": model_metadata(config["parser"]),
        "python": {"version": platform.python_version(), "platform": platform.platform()},
        "git": git_metadata(),
    }
    write_json_atomic(results_dir / "experiment_v2_manifest.json", manifest)
    print(json.dumps({
        "passed": gates["passed"],
        "parser": parser_stats,
        "policy_summary": policy_summary,
        "results": str(results_dir / "experiment_v2_results.json"),
    }, indent=2, ensure_ascii=False))
    return 0 if gates["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Check whether BoardgameQA's rule graph contains grounded recursion.

BoardgameQA is an attractive-looking candidate because it has natural language,
proofs, conflicts, and executable rules.  Its generator, however, intentionally
avoids loops.  This script independently verifies that property on the released
Main depth-1/2/3 configurations and also shows why predicate-only SCC counts can
be misleading: repeated relation names can form a predicate cycle even when the
ground rule-instance graph is acyclic.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

import networkx as nx


ATOM_RE = re.compile(r"~?\([^()]+\)")


def predicate(atom: str) -> str:
    negative = atom.startswith("~")
    fields = [field.strip() for field in atom.lstrip("~(").rstrip(")").split(",")]
    relation = fields[1] if len(fields) > 1 else atom
    return ("~" if negative else "") + relation


def has_cycle(graph: nx.DiGraph) -> bool:
    return any(
        len(component) > 1 or any(graph.has_edge(node, node) for node in component)
        for component in nx.strongly_connected_components(graph)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    files = []
    for directory in glob.glob(str(args.root / "BoardgameQA-Main-depth*")):
        files.extend(glob.glob(str(Path(directory) / "*.json")))

    result = {
        "files": sorted(files),
        "theories": 0,
        "ground_rule_graph_with_cycle": 0,
        "predicate_graph_with_cycle": 0,
        "maximum_rules": 0,
    }
    for path in files:
        with open(path, encoding="utf-8") as handle:
            examples = json.load(handle)
        for example in examples:
            result["theories"] += 1
            ground_graph = nx.DiGraph()
            predicate_graph = nx.DiGraph()
            in_rules = False
            rule_count = 0
            for line in example["theory"].splitlines():
                if line == "Rules:":
                    in_rules = True
                    continue
                if line == "Preferences:":
                    in_rules = False
                    continue
                if not in_rules or "=>" not in line:
                    continue
                rule_count += 1
                _, rule_text = line.split(":", 1)
                body_text, head_text = rule_text.split("=>", 1)
                body = ATOM_RE.findall(body_text)
                heads = ATOM_RE.findall(head_text)
                if not heads:
                    raise ValueError(f"Could not parse rule: {line}")
                head = heads[-1].strip()
                for premise in body:
                    premise = premise.strip()
                    ground_graph.add_edge(premise, head)
                    predicate_graph.add_edge(predicate(premise), predicate(head))
            result["maximum_rules"] = max(result["maximum_rules"], rule_count)
            result["ground_rule_graph_with_cycle"] += has_cycle(ground_graph)
            result["predicate_graph_with_cycle"] += has_cycle(predicate_graph)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

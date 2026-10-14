# BGB SCC controlled-intervention smoke

This is the isolated V4 data-construction batch for the Phase 1–5 smoke. It
freezes real strongly connected components (SCCs) from the repository's 2019
BGB cross-reference graph, appends auditable symbolic notes, and produces an
exact least-fixed-point (LFP) oracle. It does **not** modify the BGB graph, the
raw XML, or the archived V1–V3 experiments.

## What is built

The builder recomputes SCCs from
`data/quantlaw/de/4_crossreference_graph/2019.gpickle.gz` and selects the
lexicographically first native SCC at each exact size:

- smoke: 3, 5, 7, 9 nodes;
- pressure-only: 11 and 25 nodes;
- not fabricated: the graph has no native SCC of size 12, 16, or 20.

Each carrier has five conditions:

- `Productive`: seed fact + bridge rule + witness rule entail the query. All
  three injected sources are necessary.
- `Decoy`: the same three roles form a complete proof for a visibly separate
  parallel dossier, so the target query remains `PR-Unknown`.
- `Broken`: seed and witness are present, while the bridge patch is an audited
  no-op. No original text is deleted.
- `Clean`: no injection.
- `Matched-DAG`: the Productive program on a separately hashed, cycle-removed
  topology. Its frozen root is the seed source. A seed-rooted DFS visits the
  native seed→bridge→witness shortest path before side branches, then retains
  every forward edge. This preserves an acyclic root→all acquisition route.
  Removed edges are fully recorded; it is not claimed to have the same
  physical topology as the SCC.

`Productive`, `Decoy`, `Broken`, and `Clean` share identical native nodes,
edges, and original-window hashes. Every non-empty intervention is appended at
the end of one existing window between frozen delimiters:

```text
[CONTROLLED-LFP-NOTE]
...
[/CONTROLLED-LFP-NOTE]
```

## Outputs and leakage boundary

- `data/public_cases.jsonl`: query, topology, and source windows; no expected
  answer, formal program, proof, or oracle.
- `data/gold_sidecar.jsonl`: evaluator-only labels, append/no-op patch log,
  formal fragments, provenance, minimum source covers, and gates.
- `data/cases.jsonl`: paired records for local smoke runners. A model must see
  only `public_case`; never pass `evaluator_sidecar` to a model.
- `data/manifest.json`: input/output hashes, SCC inventory, carrier identities,
  topology deltas, counts, limitations, and aggregate gate status.

The `condition` metadata is for controlled analysis and must likewise be
removed from the actual model prompt. The model prompt should contain only the
query and materialized source content.

## Rebuild and test

```bash
python 2026NAACL/LFP-MCGS/experiments/v4_bgb_smoke/build_cases.py
python 2026NAACL/LFP-MCGS/experiments/v4_bgb_smoke/test_case_builder.py
```

The complete smoke can be reproduced with:

```bash
python 2026NAACL/LFP-MCGS/experiments/v4_bgb_smoke/run_phase2.py --mode both --baselines both
python 2026NAACL/LFP-MCGS/experiments/v4_bgb_smoke/run_phase3.py
python 2026NAACL/LFP-MCGS/experiments/v4_bgb_smoke/run_phase35.py
python 2026NAACL/LFP-MCGS/experiments/v4_bgb_smoke/run_phase4_baselines.py \
  --provider xhub --model qwen-turbo --sizes 3,5,7,9,11,25 \
  --conditions Productive,Clean --methods direct,cot,lea \
  --results-dir 2026NAACL/LFP-MCGS/experiments/v4_bgb_smoke/results/phase4_xhub_productive_clean
/opt/homebrew/anaconda3/bin/python \
  2026NAACL/LFP-MCGS/experiments/v4_bgb_smoke/run_phase5_graphpuct_xhub.py --refresh-cache
```

Phase 4 is XHub-only: the runner safely loads `XHUB_API_KEY` from the ignored
repository `.env`, records only the variable name, and has no Ollama fallback.
Its caches and outputs are isolated from the earlier local-Qwen diagnostics.
`qwen-turbo` is an API alias without a frozen upstream revision, so this smoke
records the requested and observed model IDs but does not claim weight-level
reproducibility.

The builder runs two independent positive-Horn LFP executors (naive full scan
and indexed agenda propagation). Gates require:

1. both closures agree;
2. Productive and Matched-DAG entail the query;
3. Decoy, Broken, and Clean remain `PR-Unknown`;
4. Productive loses entailment when any one injected source is removed;
5. the proof has no fact-free cyclic self-support;
6. P/D/B/C topology and original-window hashes match;
7. the DAG control is acyclic and separately hashed.
8. the frozen root reaches every source (and therefore every required proof
   source), the native reference route survives, its move/read cost fits the
   default budget, and exact LFP over only root-reachable sources still matches
   the expected label.

## Observed smoke results

These are exploratory mechanism checks, not confirmatory paper results.

- **Phase 2, controlled local parser:** Qwen 2.5 14B parses 120/120 source
  instances exactly and recovers 20/20 labels. The runner first isolates the
  explicit `CONTROLLED-LFP-NOTE` and sends only that note to the model; this is
  not raw German-window parsing. It used 24 unique cached calls, 15,542 tokens,
  and 170.6 seconds.
- **Phase 2, whole-window baselines:** Direct answers 14/20 labels correctly,
  but only 11/20 satisfy the strict answer-plus-citation contract. CoT answers
  16/20 labels correctly, but only 4/20 satisfy that strict contract. Longer
  output therefore did not automatically produce a reliable source proof.
- **Phase 3:** across sizes 3/5/7/9, Beam recovers 8/8 positive cases;
  GraphPUCT, TreePUCT, and Greedy recover 7/8. GraphPUCT records 191 strict TT
  hits and allocates 26.1% fewer nodes than TreePUCT, but has the same proof
  recovery and charged transitions. Merge mechanics work; an algorithmic
  advantage is not established.
- **Phase 3.5:** the frozen 2,160-cell grid covers sizes 3/5/7/9/11/25, two
  real-action budgets, three search intensities, three tie seeds, five
  conditions, and four methods. In the single size-9 Productive carrier under
  the standard budget, the PUCT family recovers 2/3, 3/3, and 3/3 proofs from
  low to high intensity, versus 1/3 at every intensity for Beam and Greedy.
  However, PUCT spends substantially more reads; Graph and Tree tie on all 180
  paired proof-recovery slices; and the size-9 Matched-DAG reverses direction at
  mid/high intensity (Beam 3/3, PUCT 0/3). This is a controller–topology
  interaction candidate, not an MCGS or SCC causal advantage.
- **Phase 4, Pure Baseline smoke** *(backend: XHub `qwen-turbo`)*: on the six Productive carriers,
  Full-SCC Direct and CoT both produce 0/6 correct labels and 0/6 strict
  answer-plus-verifiable-proof results. The rebuttal-lineage LEA-LFP full-cover
  baseline produces 6/6 strict results. LEA is deliberately fixed rather than
  adaptive: deterministic width-4 graph windows, unordered-set cache reuse,
  independent raw-window extraction, transparent validated union, and one
  end-only exact LFP. It costs 54 calls / 192,201 tokens, versus 6 calls /
  38,663 tokens for Direct and 6 / 39,369 for CoT. On the six Clean carriers,
  all three methods correctly remain `PR-Unknown`; LEA has 0/6 false
  entailments. This is evidence that the full structured local aggregation
  pipeline is promising, not a compute-matched PUCT advantage or an isolated
  LFP effect.
- **Phase 5, real GraphPUCT + XHub + online LFP:** on the fixed 9-node
  Productive and Clean carriers, both cases pass the strict answer/proof gate.
  The Productive run performs 7 real XHub calls / 27,313 tokens and commits two
  root windows: the first contributes witness/bridge rules and exposes
  `bridge_ready` plus `seed_ready` obligations; the second contributes the seed,
  after which exact LFP derives the bridge and query with the exact three-source
  minimum proof. Clean uses 6 calls / 21,572 tokens, commits three windows, and
  remains `PR-Unknown`. Across both cases, 40 logical window evaluations reuse
  13 unique real model observations (48,885 tokens total). This establishes the
  real end-to-end mechanism, not a general or compute-matched advantage.

Compact audited outputs are in `results/phase2_summary.json`,
`results/phase3_summary.json`, and `results/phase35_summary.json`. The first
Phase 3 run with an unreachable Matched-DAG root is retained under
`results/pre_fix_matched_dag_reachability/` as a failed diagnostic and is not
included in the headline results.

Phase 4 artifacts are isolated under `results/phase4_xhub_productive/`,
`results/phase4_xhub_clean/`, and `results/phase4_xhub_productive_clean/`.
They should not be numerically pooled with Phase 3/3.5: Phase 4 uses real XHub
`qwen-turbo` outputs, while the Phase 3/3.5 search smokes reveal frozen formal
outcomes only after charged reads.

Phase 5 artifacts are isolated under
`results/phase5_graphpuct_xhub_smoke/`. Unlike Phase 3/3.5, the XHub parser is
called inside GraphPUCT simulation; parsed fragments are branch-local, exact
LFP feedback enters value/prior/backup, and only the selected root action is
persisted. The Productive run has zero TT hits, so this smoke does not establish
an MCGS/state-sharing advantage. Its public-text prior can also match the
explicit controlled predicates; later confirmation needs no-feedback and
weaker-index controls.

The compact result directories are sufficient to recompute the headline
answer/proof and cost aggregates. A full replay of every window extraction
still depends on the private raw-response cache; that cache is intentionally
not published and is not yet hashed by the compact manifest. A confirmatory
release must freeze a redacted outcome tape or write validated fragment
signatures into each trial.

## Scope

This batch demonstrates a controlled mechanism. It does not estimate how often
the same proof pattern occurs naturally in legal corpora, and it does not turn
the original German statute prose into a gold symbolic program. Those claims
require later natural-data validation. Each size currently has one carrier,
the root is the injected seed, and every positive proof still uses exactly
three sources and two acyclic Horn rules. The current grid therefore probes
document navigation and controller behavior, not recursive-LFP scaling.

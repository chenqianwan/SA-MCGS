# Historical mock diagnostic audit

Audit date: 2026-10-02. This is an offline audit of saved results, with zero new model calls and zero simulation reruns. The original experiment files and manuscript are unchanged.

## Inputs and evidence level

The primary input is `experiments/results/ablation1_cycle.json`: 90 saved run records, comprising two methods, three topology families, three scales, and five repetitions. The exact input bytes are frozen as `source_frozen_runs.json`. File hashes and current source-code snapshots are listed in `source_manifest.json`. The secondary `ablation1_mcts_cycle.json` is a rounded narrative summary, not an independent experiment; only its mock portion is copied here.

Each run stores its seed, graph size, SCC sizes, final anomaly rank/Hit@3, node-Q range, allocated tree-node count, cycle-revisit fraction, and 100-entry histories for tree size, rollout length, and the anomalous node's Q. It does **not** store the complete final node-Q vector, every realized graph, per-rollout terminal flags, evaluator-call counts, the historical Python hash seed, or a code/runtime execution manifest. The source code in this audit is the current on-disk implementation; its identity with the historical executed version cannot be independently certified.

Therefore:

- Allocated-tree ratios and depth-cap-reached fractions can be recomputed directly from the saved scalars/histories.
- Saved Q-range and Hit@3 can be reaggregated, and Hit@3 can be checked against the saved anomaly rank. The underlying range/rank cannot be recalculated from all node values because those values were not retained.
- This bundle reproduces the **audit and saved-run aggregation**, not the complete historical simulation. It must not be described as complete independent reproduction of the original execution.

## Current-code protocol, with historical limitations

`runner.py:39–46,57–86` specifies 100 iterations per run, a random-walk transition cap of 30 for TreeMCTS, local proxy windows of 3/4/5 nodes, mock noise standard deviation 0.12, and context influence 0.25. The stored records agree with the 100-iteration design and graph-size layout:

| Topology | Small physical nodes | Medium | Large | Nontrivial SCC sizes |
|---|---:|---:|---:|---|
| DAG | 10 | 25 | 60 | none |
| Simple cycle with prefix/suffix | 10 | 17 | 30 | 5 / 12 / 25 |
| Compound cycles with bridges | 9 | 21 | 34 | [3,4] / [5,7,5] / [10,12,8] |

These are synthetic numeric-risk graphs, not document graphs or annotated repair packets. The generator places one anomaly per graph with a default base risk of 0.6. Other base risks are sampled from the ranges defined in `graph_generator.py`, generally 0.25–0.40 inside cycles/DAGs, with lower prefix/suffix/bridge ranges. The mock evaluator adds a context shift toward the other nodes' mean base risk, deterministic window-dependent hash noise, and Gaussian noise, then clips the score to [0,1] (`mock_llm.py:47–75`). It has direct access to the generator's risk values by construction; it is a simulator, not an LLM evaluator.

The historical `sa_mcgs` label refers to the simplified class in `search_methods.py:331–527`: SCC-biased seed selection, local graph windows, per-node score averages, and a window transposition cache. It has no random-walk rollout and does not implement the full paper's relation-first evidence memory, critical-pair/core policy, or LLM interface. The corrected table calls it **SCC-window proxy**.

## Pairing and budget

All 45 corresponding topology/scale/repetition cells use different recorded seeds between methods. The runner constructs seeds from Python's `hash((method_name, topology, scale, repeat))` (`runner.py:141`), and then samples graph risks/edges after setting that seed. Current code also converts sets to lists in search/evaluation. Identical realized graphs, deterministic historical reruns, and paired statistical tests are not established. The defensible description is **the same topology/scale families and 100 iteration slots**, not matched document components or matched rollout/evaluator/token budgets. The proxy reuses cached windows, whereas TreeMCTS evaluates random-walk node sets; evaluator counts and work per call are not equalized.

## Metric dictionary

| Published shorthand | What the saved data/code actually measure | Audit output |
|---|---|---|
| Expansion | Final allocated tree-node count, including the root and created children, divided by total physical graph nodes. It is not the number of expansion operations, unique visited nodes, or SCC-only nodes. | Mean of per-run `tree_node_count / graph_size`. A separate ratio-of-means is retained in JSON for transparency. |
| Truncation | The archive stores rollout path-node counts. The routine starts with one node and permits 30 transitions; a length of 31 means the transition cap was reached. No final terminal flag is saved. | `depth_cap_reached_count / 100`; named **depth cap reached**, not exact terminal-conditioned truncation. |
| Cycle hit | Whether any physical node was revisited during a rollout, aggregated over rollouts. | Logged separately; never substituted for depth-cap reaching. |
| Q-spread | `max(Q_v) - min(Q_v)` over physical graph nodes with strictly positive final Q (`search_methods.py:284–287,498–499`). | Mean **saved positive-node Q range**. It is neither standard deviation nor the range of root action values. |
| Hit@3 | Whether the single synthetic anomalous node has saved rank ≤3 (`search_methods.py:266–273,312–313,482–487,518–519`). | Count and percentage out of 15 runs per method/topology. Not expert repair-endpoint recall. |

TreeMCTS's node Q aggregates path-backpropagated **window-mean** rollout values; the proxy's Q aggregates **node-specific** evaluator scores (`search_methods.py:225–239,417–421`). Their Q ranges thus do not represent the same estimator, and a larger proxy range does not by itself isolate improved convergence or calibration. Zero Q values are excluded from the range. The unrelated `q_oscillation` field uses a tail standard deviation; it is not the Q-spread in the paper.

The proxy allocates per-physical-node statistics by implementation, but has no tree and no random-walk truncation outcome. Its corresponding table cells are **N/A**, not a measured 1.0× tree expansion or 0% truncation result.

## Cohort and summary rules

Each corrected row contains exactly 15 runs from one method and one topology: five repetitions at each of three scales. All row metrics use these same 15 runs. Because each run has 100 iterations, per-run and pooled-iteration means coincide for depth-cap reaching. The audit also provides 18 method/topology/scale rows (n=5 each). The simple-plus-compound aggregate is retained only in JSON for tracing the legacy values, not mixed into a compound-only row. No paired confidence interval or significance test is produced.

The old paper's 0.044 / 30% and 0.371 / 90% are reproducible as **simple-plus-compound pooled** saved metrics (n=30 each). Its 100% depth-cap statistic pertains to **compound** TreeMCTS only (n=15). The 6.4× ratio is in the secondary narrative summary, derived from its approximate 127/20 figures, and cannot be reproduced as either the primary compound mean of ratios (7.4549) or its ratio of means (5.7281). The DAG primary mean ratio is 2.2331, not an exact 2.3; its depth-cap-reaching fraction is 4/1500=0.2667%, not exactly zero.

## What this diagnostic can support

The saved runs illustrate path-state duplication and frequent cap-reaching for one deliberately simple TreeMCTS implementation on synthetic cyclic topologies. They do not establish a general failure of MCTS/UCT on cycles, loss of a theoretical convergence guarantee, the superiority of production SA-MCGS at matched cost, or natural-document risk detection. TreeMCTS Hit@3 is also poor on the DAG control (1/15), so the anomaly-ranking difference cannot be attributed exclusively to cycles. Heterogeneous graph sizes, independently generated instances, different value targets, and distinct evaluator use remain confounds.

## Rebuild and verification

Run `python3 rebuild_audit.py` in this directory, followed by `python3 rebuild_audit.py --verify`. Both use only the standard library and frozen inputs. The verification checks 90 unique complete runs, 18 balanced cells, 100-entry histories, monotonic tree allocation, scalar/history agreement, and saved rank/Hit@3 consistency. `per_run_sanitized.csv` contains only synthetic run identifiers, method/configuration labels and numeric statistics; it contains no expert identifiers, document text, account credentials or local absolute paths.

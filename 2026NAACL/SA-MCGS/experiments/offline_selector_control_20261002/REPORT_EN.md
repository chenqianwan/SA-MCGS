# Offline selector control

To isolate final evidence selection, we replayed the frozen GPT-4o trajectories for 80 injected variants from 20 source SCCs. The control applies LEA's existing aggregation score to the same recorded local outputs and selects exactly as many nodes as the Full core in each case. Full and the LEA-score control achieve Risk-all of 75.00% and 72.50%, respectively (Full minus control: +2.50 percentage points; 95% paired source-SCC bootstrap interval [-16.25, 20.00]). Both retain 8.10 nodes on average, with 51.26% compression. The paired interval does not establish an advantage for either selector on these fixed trajectories. The comparison conditions on evidence acquired by Full and does not isolate search-policy effects or online replacement benefits; it requires no new model calls.

| Selector | Risk-any | Risk-all | Endpoint coverage | Mean k | Compression |
|---|---:|---:|---:|---:|---:|
| full | 100.00% | 75.00% | 87.50% | 8.10 | 51.26% |
| lea-score-matched-k | 98.75% | 72.50% | 85.62% | 8.10 | 51.26% |
| mean-risk-matched-k | 100.00% | 93.75% | 96.88% | 8.10 | 51.26% |

The frozen root ranking is unchanged across output selectors; Root@3 is 86.25%.

| Domain | Sources | Cases | Full Risk-all | LEA-score Risk-all | Difference (points) | Paired 95% interval |
|---|---:|---:|---:|---:|---:|---|
| bgb | 3 | 12 | 58.33% | 33.33% | +25.00 | [-50.00, 75.00] |
| cuad | 10 | 40 | 72.50% | 67.50% | +5.00 | [-15.00, 27.50] |
| debian | 2 | 8 | 100.00% | 100.00% | +0.00 | [0.00, 0.00] |
| sec_ex21 | 5 | 20 | 80.00% | 95.00% | -15.00 | [-60.00, 15.00] |

Domain intervals are exploratory, with only 2–10 source clusters per domain. The primary analysis uses equal source weights; each source has four variants, so the overall variant average is identical.

Full/control discordance for Risk-all: {"full_only": 12, "control_only": 10, "both": 48, "neither": 10}.

Selection uses the existing LEA score, including its observed-only median and SCC-order tie break. The control includes every recorded rollout entry, including cache reuse, and uses only node scores, local risk sets, repair entries and accepted local conflict-edge endpoints. It never reads OC, pair-ledger scores, Full composite evidence scores or injected labels.

The per-case k comes from Full solely to control output size. This is a conditional analysis, not a deployable rule for choosing k. Both controls inherit Full's acquired evidence. These results must not be described as a token-matched comparison between independently run search policies.

Files: protocol.json records the fixed analysis protocol; minimal_traces.jsonl and selection_inputs.jsonl contain anonymous text-free selection inputs; metric_labels.jsonl is used only for scoring; full_reference_outputs.jsonl stores the frozen Full outputs; identity_and_parity_audit.jsonl records 80 case checks; source_provenance.json and MANIFEST.sha256 support audit.

Standalone reproduction: `python run_offline_selector_control_20261002.py --reproduce .` (Python standard library only). It verifies the manifest, reaggregates the sanitized traces, reruns both selectors, recomputes all paired intervals, and compares the saved results without rewriting them.

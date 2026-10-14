# Expert audit: offline analysis, 22 September 2026

The current audit contains 18 unmodified originals and 24 newly annotated injected variants; two experts rated all 42 presentations and a third independently reviewed 14 selected presentations (9 pre, 5 post). There are 98 actual judgments. All 18 originals are finally absent/sufficient and all 24 injected variants present/sufficient. These are expert labels, not model accuracies.

New post: 24 variants from 14 source SCCs. Pre: 18 originals from 18 source SCCs. The historical 12-case audit remains a separate stratum; its worksheets were not reopened or merged in this analysis.

## Original inter-annotator agreement

Agreement is computed before adjudication. The third expert's targeted subset is reported separately and is not a random three-rater sample. Cohen's kappa is undefined when both marginal distributions contain only one category. Empty/empty set Jaccard is 1; post-only set agreement avoids the empty negative-evidence inflation.

| Pair | Scope | N | Target agreement | Target kappa | Sufficiency agreement | Sufficiency kappa | Joint agreement | Minimal Jaccard | Repair Jaccard |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| expert_1/expert_2 | all | 42 | 39/42 | 0.842 | 37/42 | 0.222 | 35/42 | 0.700 | 0.630 |
| expert_1/expert_2 | pre | 18 | 15/18 | 0.471 | 13/18 | 0.118 | 11/18 | 0.741 | 0.505 |
| expert_1/expert_2 | post | 24 | 24/24 | undefined | 24/24 | undefined | 24/24 | 0.670 | 0.723 |
| expert_1/expert_3 | all | 14 | 10/14 | 0.472 | 10/14 | 0.000 | 6/14 | 0.462 | 0.490 |
| expert_1/expert_3 | pre | 9 | 5/9 | 0.000 | 5/9 | 0.000 | 1/9 | 0.556 | 0.442 |
| expert_1/expert_3 | post | 5 | 5/5 | undefined | 5/5 | undefined | 5/5 | 0.294 | 0.577 |
| expert_2/expert_3 | all | 14 | 11/14 | 0.588 | 11/14 | 0.000 | 10/14 | 0.629 | 0.610 |
| expert_2/expert_3 | pre | 9 | 6/9 | 0.000 | 6/9 | 0.000 | 5/9 | 0.667 | 0.531 |
| expert_2/expert_3 | post | 5 | 5/5 | undefined | 5/5 | undefined | 5/5 | 0.560 | 0.753 |

## Post evidence quality

For the five adjudicated post cases, all reference fields come from the third expert's complete answer. For the other 19 post cases, each prediction is scored separately against the two original references and the two metric values are averaged within the case; no union or intersection of expert gold sets is used. Minimal recall = |returned intersect minimal|/|minimal|; repair coverage = |returned intersect repair|/|repair|; repair precision = |returned intersect repair|/|returned|. Repair packets already permit explanation and supporting material. The bridge-aware sensitivity allows the independently frozen injection bridge in addition to each individual repair reference. Outside-reference nodes are not established to be irrelevant.

SA uses the deployable core_evidence_risk_subgraph_nodes field, LEA uses lea_risk_subgraph_nodes, and One-shot uses direct_risk_subgraph_nodes. LEA/SA selections were checked against the frozen hint export. The historical SA risk_subgraph_nodes field can be anchored on injected ground truth and is excluded from this expert comparison. This output-field distinction must also be stated if historical benchmark metrics using a different field appear nearby. Valid outputs were checked against exact clause/injection identities; invalid One-shot outcomes retain the identity established in the frozen coverage audit. Failed or empty outputs retain their cases: recall, coverage, precision, density, and excess are zero by the existing analysis convention; therefore precision plus excess need not equal 100% in an aggregate containing such cases. Report validity beside these measures.

The main estimates average variants within each source SCC, then weight source SCCs equally. Brackets are percentile 95% intervals from 20,000 source-SCC bootstrap draws (seed 20260922). Descriptive variant means are reported separately. These small selected-sample intervals do not support population prevalence claims.

| Model | Method | Valid / 24 | Minimal recall % [CI] | Repair coverage % [CI] | Repair precision % [CI] | Outside repair % [CI] | Bridge-aware precision % [CI] |
|---|---|---:|---:|---:|---:|---:|---:|
| gpt-4o | one-shot | 20/24 | 40.5 [23.7, 58.3] | 34.1 [21.7, 47.2] | 59.9 [40.0, 78.5] | 15.1 [6.7, 24.3] | 60.3 [40.2, 78.9] |
| gpt-4o | lea | 24/24 | 65.4 [55.8, 75.4] | 56.1 [53.3, 58.7] | 66.5 [60.2, 73.0] | 33.5 [27.0, 39.8] | 66.7 [60.4, 73.2] |
| gpt-4o | sa-mcgs | 24/24 | 90.8 [86.8, 94.7] | 73.1 [68.7, 77.6] | 85.0 [80.9, 88.8] | 15.0 [11.2, 19.1] | 85.0 [80.9, 88.8] |
| gemini-2.5-pro | one-shot | 24/24 | 69.6 [59.9, 78.6] | 37.0 [31.4, 42.9] | 91.5 [83.6, 97.7] | 8.5 [2.3, 16.4] | 91.5 [83.6, 97.7] |
| gemini-2.5-pro | lea | 24/24 | 86.3 [78.4, 93.6] | 61.3 [55.7, 66.7] | 71.8 [64.6, 79.3] | 28.2 [20.7, 35.4] | 72.2 [64.8, 79.9] |
| gemini-2.5-pro | sa-mcgs | 24/24 | 88.5 [81.2, 94.6] | 68.3 [59.6, 75.5] | 88.4 [80.5, 95.0] | 11.6 [5.0, 19.5] | 88.4 [80.5, 95.0] |

Variant-weighted descriptive means (same 24-case denominator):

| Model | Method | Minimal recall % | Repair coverage % | Repair precision % | Outside repair % |
|---|---|---:|---:|---:|---:|
| gpt-4o | one-shot | 38.2 | 36.4 | 64.9 | 18.5 |
| gpt-4o | lea | 61.1 | 56.3 | 69.5 | 30.5 |
| gpt-4o | sa-mcgs | 88.4 | 71.6 | 86.8 | 13.2 |
| gemini-2.5-pro | one-shot | 67.0 | 37.2 | 93.0 | 7.0 |
| gemini-2.5-pro | lea | 84.3 | 61.6 | 75.4 | 24.6 |
| gemini-2.5-pro | sa-mcgs | 86.9 | 69.0 | 90.3 | 9.7 |

Paired source-SCC contrasts (percentage points; positive means higher for SA):

| Model | Contrast | Minimal recall difference [CI] | Repair coverage difference [CI] | Repair precision difference [CI] |
|---|---|---:|---:|---:|
| gpt-4o | sa-mcgs minus one-shot | 50.3 [33.0, 66.4] | 39.1 [24.2, 53.3] | 25.2 [6.3, 46.0] |
| gpt-4o | sa-mcgs minus lea | 25.5 [15.3, 35.1] | 17.0 [11.7, 22.3] | 18.6 [13.1, 23.6] |
| gemini-2.5-pro | sa-mcgs minus one-shot | 18.8 [9.4, 29.1] | 31.3 [22.0, 39.5] | -3.1 [-9.7, 2.7] |
| gemini-2.5-pro | sa-mcgs minus lea | 2.2 [-7.4, 12.0] | 6.9 [-3.0, 15.8] | 16.6 [8.5, 24.4] |

## Pre negative-case audit

The stored decision rule asserts a target conflict only when a raw conflict record (a rollout conflict for SA) has two distinct exact SCC IDs and a nonempty reason. A valid output with no accepted pair is operational abstention; it is not a separately elicited negative judgment. Nonempty selected subgraphs are not used to infer assertions. An invalid output is never treated as a correct abstention. Since all 18 expert labels are negative, each stored valid assertion is a false positive under this operational rule. Natural-positive recall is not estimable (N = 0).

First means the original complete run, including its within-run schema retries. SA recovery permits exactly one additional complete run on each original strict failure (10 GPT and 14 Gemini); the original SA result files remain preserved. GPT LEA also reran its two original failures on 29 August: CUAD25 recovered and CUAD34 remained invalid. That runner overwrote the two original result JSONs, so their first-run invalid status is reconstructed only from the append-only call log, with exact line provenance; unavailable original output text and selections are not reconstructed. Gemini LEA and One-shot have no additional complete-run recovery here. Recovery is a reliability/cost sensitivity, not an equal-opportunity single-run comparison. The SA retry report accounts for 1,140 additional retry calls, 5,011,988 tokens and estimated $26.766918; GPT LEA recovery adds 63 calls and 261,389 tokens (153,448 input + 107,941 output). First-run costs are additional.

| Model | Method | Protocol | Valid / 18 | False positive / 18 | Abstain / 18 | Invalid / 18 | False positive % [CI] | FP among valid % |
|---|---|---|---:|---:|---:|---:|---:|---:|
| gpt-4o | one-shot | first | 12/18 | 12/18 | 0/18 | 6/18 | 66.7 [44.4, 88.9] | 100.0 |
| gpt-4o | lea | first | 16/18 | 16/18 | 0/18 | 2/18 | 88.9 [72.2, 100.0] | 100.0 |
| gpt-4o | lea | recovery | 17/18 | 17/18 | 0/18 | 1/18 | 94.4 [83.3, 100.0] | 100.0 |
| gpt-4o | sa-mcgs | first | 8/18 | 8/18 | 0/18 | 10/18 | 44.4 [22.2, 66.7] | 100.0 |
| gpt-4o | sa-mcgs | recovery | 15/18 | 15/18 | 0/18 | 3/18 | 83.3 [66.7, 100.0] | 100.0 |
| gemini-2.5-pro | one-shot | first | 18/18 | 18/18 | 0/18 | 0/18 | 100.0 [100.0, 100.0] | 100.0 |
| gemini-2.5-pro | lea | first | 18/18 | 17/18 | 1/18 | 0/18 | 94.4 [83.3, 100.0] | 94.4 |
| gemini-2.5-pro | sa-mcgs | first | 4/18 | 4/18 | 0/18 | 14/18 | 22.2 [5.6, 44.4] | 100.0 |
| gemini-2.5-pro | sa-mcgs | recovery | 18/18 | 18/18 | 0/18 | 0/18 | 100.0 [100.0, 100.0] | 100.0 |

Provenance reconciliation: the historical 16/18 GPT LEA figure is the original pass; the current result JSONs, batch summary CSV, and frozen hint packs reflect 17/18 after recovery. The append-only log records initial CUAD25 and CUAD34 failures at lines 144 and 162, second-run starts at lines 305 and 306, and the repeated CUAD34 failure at line 381. These are different protocols, not a numerical error in the original first-run count. A 100% bootstrap interval degenerates when every observed source is positive and should not be interpreted as certainty about unseen sources.

## Provenance and limits

The frozen adjudication hash, public manifest hash, case/source identity, section mappings, positive-reference denominators, raw method output identity and hint-selection agreement were checked. Machine-readable outputs preserve every separate expert reference and every first/recovery system record; source_manifest.json lists SHA-256 digests for all read artifacts and preserved original workbook provenance. No new model calls were made. Reproduce with `python3 analyze.py` from this directory.

The 14-case adjudication rule was author-designated after receiving the third expert's results, not preregistered. No full 42-case unique evidence gold is claimed. Expert qualifications, consent, compensation, and ethics statements must be supplied from real author records. The original historical 12-case summary may be cited separately; no missing old-case labels were reconstructed. The analysis measures output-set agreement and an explicit assertion protocol, not legal advice quality or natural-positive detection.

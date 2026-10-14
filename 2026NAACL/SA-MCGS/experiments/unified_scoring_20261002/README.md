# Unified strict five-model reanalysis

This directory contains a retrospective, offline reanalysis of 1,200 archived
outputs: 20 physical source SCCs × 4 injected variants × 5 models × 3 methods.
The protocol was frozen before this reanalysis aggregated results, after the
historical outcomes were already known. It is not a prospective preregistration.
No new model calls were made and no original output was changed.

The raw-input audit rechecks source-file hashes, method/model identity, SCC node
membership, root/risk identities, terminal validity, rankings, and selected-node
sets. All 1,200 recomputed strict scores match their archived strict analyses.
Historical parser decisions and local fallback behavior remain fixed. The audit
does not reinterpret an invalid output as a successful partial answer.

## Primary estimands and denominators

- Root@3, Risk-any and Risk-all include all 80 planned variants per model-method;
  a strict-invalid terminal output contributes zero to all three.
- Compression is conditional on a defined valid output. Its denominator is
  explicit in every aggregate. All three binary denominators remain 80.
- The main pooled binary comparison first averages the 20 paired differences
  within each source (four variants × five fixed models), then averages sources.
  Models are fixed rather than treated as independent clusters.
- Paired bootstrap intervals use 20,000 resamples of the physical source SCCs,
  seed 8229, and percentile intervals with linear interpolation. These intervals
  measure selected-source heterogeneity, not repeated-run seed variation.
- Compression confidence intervals are a separate complete-pair, source-equal
  conditional analysis. They are not intervals for the difference of the main
  valid-only marginal means. Their sample and source counts must accompany them.
- `overall_method.csv` distinguishes pooled defined-output compression from
  equal-model conditional compression. The manuscript's 55.70% mean SA-MCGS
  compression uses the latter; its five model-specific denominators are
  80/80/80/78/80, not a single denominator of 400.

## Main effects of this correction

Only the Qwen3.5-9B One-shot row changes relative to the previous mixed-policy
main table. Its strict scores are Root@3 12.50%, Risk-any 53.75%, Risk-all 12.50%,
and compression 62.70% over 67 valid outputs. The previous metricwise values
15.00/60.00/13.75/64.73 (compression n=80) remain separately available as a
sensitivity analysis of the same archived responses.

Across the five fixed models, SA-MCGS minus LEA is +6.75 points for Root@3
(95% source interval −0.25 to 14.00), and +15.25 for Risk-all (2.00 to 27.75).
SA-MCGS minus One-shot is now +46.50 for Root@3 (37.75 to 55.25), and +39.00 for
Risk-all (29.00 to 49.25). All SA-MCGS and LEA values remain unchanged.

`impact_summary.json` lists affected figure/table families. The GPT-4o budget
curve, expert audit and component experiments are not reanalysed or modified.

## Files for manuscript integration

- `canonical_case_metrics.csv`: anonymous per-output strict metrics with stable
  source/case identities, validity, and source SHA; no prompts or local paths.
- `model_method.csv`, `domain_method.csv`, `scale_method.csv`,
  `model_domain_method.csv`, `model_scale_method.csv`: strict aggregates.
- `paired_source_cluster_ci.csv` and `.tex`: SA-minus-LEA and SA-minus-One-shot
  intervals for all three binary metrics, pooled and model-specific.
- `validity_denominators.tex`: planned, valid, invalid and compression counts.
- `five_model_main_rows.tex`, domain/scale row snippets: main-result table rows.
- `qwen_scoring_sensitivity.csv` and `.tex`: strict vs metricwise sensitivity.
- `scoring_protocol_paragraph.tex`: short English methods/scope wording.
- `compatible_assets/canonical_case_metrics.json` and `aggregates.json`: the
  existing plotting schema with all numeric values replaced by strict outputs.
  Optional node metadata is inherited from the prior validated asset table;
  it does not determine the new scores. Source paths are repository-relative.
- `source_record_audit.csv`, `input_manifest.json`, and `validation.json`:
  extraction and provenance checks.

## Verified configuration and remaining gaps

`verified_config_observations.csv` reports only allowlisted fields from the
actual result records and frozen Llama/Qwen3.5 protocols. No credentials,
endpoints, raw prompts or private absolute paths are included.
`verified_model_method_configuration.csv` summarizes those observations.

The local Llama 3.1-8B and Qwen3.5-9B frozen protocols identify the exact
checkpoints and use One-shot temperature 0.0/max_tokens 12000, LEA and SA-MCGS
temperature 0.4/max_tokens 2048. They record Python RNG and hash seeds of 42;
these are not evidence of an API/model sampling seed or repeated independent
runs. Qwen3.5 is recorded with thinking disabled.

The audited historical GPT-4o, Gemini 2.5 Pro and Qwen2.5-72B result artifacts
do not completely record decoding settings or pinned model snapshots. Their
missing values are explicitly marked, not reconstructed from current defaults.
In particular, the Qwen2.5-72B LEA records specify
`Qwen/Qwen2.5-72B-Instruct-AWQ`, revision
`698703eae6604af048a3d2f509995dc302088217`. The corresponding historical One-shot
and SA-MCGS records do not establish the same checkpoint or quantization, so
this is not a verified identical-backend three-method comparison.

The dataset and five models are selected, executions span historical batches,
and the study does not estimate natural-positive recall or establish equal-token
superiority. Statistical intervals do not remove those design limitations.

## Rebuild

The full raw-input audit requires the archived repository data:

```sh
python3 experiments/main_experiment/build_unified_scoring_20261002.py
```

The `anonymous_reproduction` subdirectory contains only the sanitized canonical
inputs, fixed protocol and a standard-library script. It reproduces statistical
tables and LaTeX snippets without raw model responses, network access, or any
external packages. From that subdirectory:

```sh
python3 rebuild_statistics.py --from-canonical canonical_case_metrics.csv --sensitivity-cases qwen_metricwise_sensitivity_cases.csv --protocol protocol.json --output-dir rebuilt
```

This second mode reproduces statistics from the supplied scores; it does not
claim to rerun the original models or independently reconstruct their raw
parsing decisions. `anonymous_rebuild_validation.json` records an actual
rebuild and numerical-artifact equivalence check.

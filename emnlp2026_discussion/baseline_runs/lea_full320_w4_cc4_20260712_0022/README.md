# LEA Full-320 Attempt: Paused

Started: 2026-07-12 00:29 +0800

Scope intended: all 320 rows from `emnlp2026_discussion/case_composition.csv`, using the GraphRAG-style Local Evidence Aggregation baseline.

Status: paused manually after provider-side failures.

## What happened

- `gpt-4o` calls completed normally for the first few cases.
- `deepseek-v3` returned repeated provider errors: `403 user quota is not enough`.
- `qwen2.5-72b` was tested separately and its first call timed out / failed with `APIConnectionError` after about 318 seconds.

Because LEA's underlying local evaluation can continue with fallback entries after individual LLM failures, these failed-provider cases must not be mixed into the baseline table. The runner has been patched so any case with failed API calls is marked invalid.

## Data handling

- Valid early `gpt-4o` results remain in `results/`.
- The early `deepseek-v3` JSON files generated during the quota failure were moved to `quarantine_insufficient_quota/`.
- This run should not be used as a final table. It is only a record of the interrupted full-320 attempt.

## Follow-up

Continue full coverage after provider availability is restored. In the meantime, the available-model run is:

`/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/baseline_runs/lea_available160_gpt4o_gemini_w4_cc4_20260712_0048`

# EMNLP 2026 Discussion Experiment Record: GraphRAG-style LEA Baseline

Created: 2026-07-12

This directory freezes the current clean run of the graph-aware decomposed baseline, tentatively named GraphRAG-style Local Evidence Aggregation (LEA).

## Source Run

- Source: `/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/baseline_runs/lea_available160_gpt4o_gemini_w4_cc4_20260712_0048`
- Scope: 160 cases, covering `gpt-4o` and `gemini-2.5-pro` only.
- Status: 160/160 completed, 0 failed, 0 invalid.
- Method: deterministic local graph-window retrieval with the same local evidence schema as SA-MCGS, but without relation-first memory, critical-pair revisiting, OC/core signals, or dynamic-core replacement.

This is a clean available-model run, not the final intended full-320 table. `deepseek-v3` was blocked by provider quota, and `qwen2.5-72b` showed connection/timeout instability during smoke testing.

## Frozen Files

- `summary_lea_full_breakdown.md` / `summary_lea_full_breakdown.csv`: LEA-only results by model, domain, SCC size, and template.
- `summary_method_cases.csv`: per-case LEA rows.
- `matched_lea_vs_full_sa_mcgs_summary.md` / `matched_lea_vs_full_sa_mcgs_summary.csv`: matched LEA vs locked Full SA-MCGS comparison.
- `matched_lea_vs_full_sa_mcgs.csv`: per-case matched comparison.
- `case_plan.csv`, `run_config.json`, `status.json`: execution metadata.

## LEA-Only Summary

Overall on 160 available-model cases:

- Root@3: 0.838
- Risk-any: 0.963
- Risk-all: 0.662
- Compression: 0.516
- Calls / case: 15.688
- Total tokens / case: 78,888
- Runtime / case: 311.3s

By model:

- `gemini-2.5-pro`: Root@3 0.887, Risk-any 1.000, Risk-all 0.887.
- `gpt-4o`: Root@3 0.787, Risk-any 0.925, Risk-all 0.438.

## Matched LEA vs Full SA-MCGS

On the same 160 cases:

| Method | Root@3 | Risk-any | Risk-all | Compression | Calls / case |
|---|---:|---:|---:|---:|---:|
| LEA | 0.838 | 0.963 | 0.662 | 0.516 | 15.7 |
| Full SA-MCGS | 0.869 | 0.988 | 0.794 | 0.536 | 55.7 |
| SA-MCGS - LEA | +0.031 | +0.025 | +0.131 | +0.020 | +40.1 |

Paired counts:

- Root@3: SA-MCGS better on 15 cases, tied on 135, LEA better on 10.
- Risk-any: SA-MCGS better on 6 cases, tied on 152, LEA better on 2.
- Risk-all: SA-MCGS better on 34 cases, tied on 113, LEA better on 13.

## Interpretation

The new decomposed graph-aware baseline is competitive, especially under Gemini 2.5 Pro. This is useful for the discussion because it directly controls for local decomposition and output-schema burden. Full SA-MCGS still gives a clear overall endpoint-completeness gain, mainly in Risk-all, but the result should be described as non-uniform across models rather than universal dominance.

# EMNLP 2026 Discussion Experiment Record: Stage 2 Dynamic Component Ablation

Created: 2026-07-11

This directory freezes the discussion-facing Stage 2 component ablation evidence. It supersedes the earlier static core-only replay record, which should remain an internal sanity check only.

## Source Run

- Dynamic Stage 2 source: `/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/component_ablation_runs/stage2_dynamic_gpt4o_b60_ic4_cc4_20260711_main40`
- Scope: 40 matched gpt-4o cases, 4 variants, 160/160 completed, 0 failed.
- Full SA-MCGS rows are copied from locked main results. The ablated variants are dynamically re-run with the same local evidence schema and rollout budget.

## Frozen Files

- `component_ablation_table.md` / `component_ablation_table.csv`: main Stage 2 table.
- `summary_component_cases.csv`: per-case rows for paired analysis.
- `case_plan.csv`: selected case identities.
- `run_config.json` and `status.json`: execution metadata.

## Main Results

| Variant | N | Root@3 | Risk-any | Risk-all | Compression | Avg core size |
|---|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | 40 | 0.850 | 1.000 | 0.700 | 0.521 | 9.975 |
| No OC/core signal | 40 | 0.850 | 1.000 | 0.600 | 0.522 | 9.725 |
| Monotone core | 40 | 0.775 | 0.875 | 0.450 | 0.761 | 4.750 |
| No pair closure in final core | 40 | 0.800 | 0.950 | 0.675 | 0.530 | 9.450 |

## Paired Interpretation

- Monotone core is the clearest degradation. Relative to Full SA-MCGS, Risk-all drops by 25 points and Risk-any drops by 12.5 points; compression rises from 0.521 to 0.761, and average core size drops from 9.975 to 4.750. In paired case comparison, 38/40 cases produce a smaller core and 11/40 lose Risk-all, while only 1 gains Risk-all.
- No OC/core signal mainly affects endpoint completeness rather than basic risk discovery. Risk-any stays at 1.000, while Risk-all drops from 0.700 to 0.600. Paired comparison gives 7 Risk-all losses and 3 gains, so this should be described as a moderate endpoint-completeness signal, not a uniformly decisive component.
- No pair closure in final core has a smaller and mixed effect in this 40-case sample. Risk-all changes from 0.700 to 0.675, with 7 paired losses and 6 paired gains. It is best treated as a light robustness safeguard rather than the main Stage 2 contribution.

## Reviewer-Facing Takeaway

The strongest Stage 2 evidence is for dynamic/replacement core construction: a simple monotone accumulation baseline tends to over-compress and lose repair-relevant endpoints, especially in larger SCCs. OC/core signals can be reported as helping endpoint completeness on average, while final pair closure should be framed cautiously as an auxiliary protection mechanism.

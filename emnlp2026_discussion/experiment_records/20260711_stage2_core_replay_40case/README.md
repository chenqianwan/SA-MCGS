# Deprecated: Stage 2 Core-Only Replay Record

Created: 2026-07-11

Status: deprecated. Do not use this static replay as discussion evidence unless explicitly revisited. The analysis holds rollout evidence fixed and only recomputes the final core, so it does not represent a dynamic trajectory-level component ablation. The current discussion-facing Stage 2 is the dynamic run at `/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/component_ablation_runs/stage2_dynamic_gpt4o_b60_ic4_cc4_20260711_main40`.

Source run: `/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/component_ablation_runs/stage2_core_replay_main40_20260711`

Scope: 40 matched Full SA-MCGS cases from the Stage 1 full-80 summary. This is a replay-only experiment from saved Full SA-MCGS results; it does not make new LLM calls.

## Files

- `stage2_core_replay_report.md`: consolidated report.
- `stage2_core_replay_table.md` / `stage2_core_replay_table.csv`: main 40-case table.
- `stage2_core_replay_by_scc_bin.md` / `stage2_core_replay_by_scc_bin.csv`: SCC-size-bin breakdown.
- `summary_stage2_core_replay_cases.csv`: per-case rows.
- `case_plan.csv`: selected case identities.
- `run_config.json` and `status.json`: execution metadata.

## Main Results

- Full SA-MCGS: Risk-any 1.000, Risk-all 0.700, Compression 0.521.
- No OC/core signal: identical to Full on this 40-case replay, suggesting OC/core bonus is not the binding final-core factor in this subset.
- Monotone core: Risk-any 0.975, Risk-all 0.600, Compression 0.771. This is the clearest Stage 2 degradation and supports dynamic/replacement core construction.
- No pair closure in final core: Risk-any 1.000, Risk-all 0.675, Compression 0.523. This is a smaller but directionally consistent endpoint-retention drop.

## Historical Note

This replay should be treated only as an internal sanity check. It should not be cited in reviewer-facing comments because SA-MCGS is a trajectory-dependent algorithm: OC signals, pair evidence, and core policies can affect later rollout paths and therefore need dynamic re-runs for component-level ablation.

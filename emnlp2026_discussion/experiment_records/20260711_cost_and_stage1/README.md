# EMNLP 2026 Discussion Experiment Record: Cost Audit and Stage 1 Component Ablation

Created: 2026-07-11

This directory freezes the current reviewer-facing experimental evidence before Stage 2 core-only replay. It keeps copied tables and plots from the live run directories so later edits to runners or dashboards do not obscure the numbers used during discussion.

## Source Runs

- Cost audit source: `/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/cost_audit_runs/clean_gpt4o_b50_20260711_013007`
- Stage 1 component ablation source: `/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/component_ablation_runs/stage1_full80_by_scc_size`

## Cost Audit Files

- `summary_cost_table_merged.md` / `summary_cost_table_merged.csv`: main cost, reliability, and performance table.
- `cost_summary_method_cases.csv`: per-method case-level cost/performance rows.
- `cost_reliability_overview.png`: visual overview for cost/reliability/performance.

Main cost-audit scope: 20 matched cases, comparing Full-SCC Naive, GraphRAG-style LEA, and SA-MCGS. The table reports input/output/total tokens, API calls, runtime, validity, Root@3, Risk-any, Risk-all, and Compression, with SCC-size breakdowns.

## Stage 1 Component Ablation Files

- `component_ablation_full80_report.md`: consolidated Stage 1 report.
- `component_ablation_table_full80.md` / `component_ablation_table_full80.csv`: full 80-case component ablation table.
- `component_ablation_by_scc_bin_compact.md` / `component_ablation_by_scc_bin_compact.csv`: compact SCC-size-bin table.
- `component_ablation_by_subset.md`: main20 / long20 / midshort40 split.
- `component_ablation_full80_metrics.png`: full 80 metric plot.
- `delta_risk_all_by_scc_bin.png`: SCC-size-bin delta plot.

Stage 1 scope: all 80 gpt-4o case configurations from locked main results. Full SA-MCGS rows are copied from locked main results; no relation-first memory, no critical-pair ledger/revisit, and random local-window selection are re-run under B=60, window=4, case concurrency=4, internal concurrency=4.

## Key Stage 1 Takeaways

- No critical-pair ledger/revisit is the strongest component-level degradation: Risk-all drops from 0.750 to 0.537 overall, and from 0.583 to 0.167 on large SCCs.
- Random local-window selection reduces Risk-all from 0.750 to 0.637 overall, supporting graph-guided window selection beyond repeated local prompting.
- No relation-first memory is close to Full SA-MCGS in this gpt-4o sample; we should describe it as heterogeneous / diagnostic rather than a uniformly harmful ablation.
- SCC-size bins are assigned from matched Full/plan metadata, not from per-variant payload fields.


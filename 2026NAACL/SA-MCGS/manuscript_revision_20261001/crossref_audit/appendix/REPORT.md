# Appendix cross-reference audit — before fixes, 2026-10-01

Scope: active clean-view source after `\\appendix` in `paper/latex/acl_latex.tex`, plus `revision_expert_appendix.tex`, `revision_experiments.tex`, and imported `five_model_appendix_breakdowns.tex`. Read-only: no manuscript changes by this auditor. Baseline PDF: 24-page `acl_latex_clean.pdf` modified 2026-10-01 22:00. Line numbers below are pre-fix source lines.

## Findings

**All 35 active appendix reference commands (26 unique targets) resolve to the intended numbered object/section/equation. No clean-view numerical cross-reference, figure panel, method legend, or relocated-figure caption mismatch was found.** Source and actual rendered PDF were both checked. However, there is substantial appendix float drift, and two bare panel mentions should be linked explicitly.

### 1. Floats escape their owning appendices

| Owning appendix | Text position before fixes | Figure/table/algorithm positions before fixes | Impact |
|---|---|---|---|
| B expert audit | starts p11, ends p14 | Tables 5–10: pp13,13,14,14,15,16 | Tables9–10 appear after Appendix C/D/E begin |
| C long-SCC example | p14 | Figure4 p15 | Case figure appears just above Appendix E, after Appendix D text |
| D algorithms | p14 | Algorithms2–5: pp16,16,16,17 | Algorithms are visually mixed into Appendix E/F/G text |
| F prior coefficients | begins p16 | Table11 p18 | Table appears among Appendix I dataset material |
| I datasets | pp17–18 | Tables12–13 p19 | Source-associated tables precede J on p19; less serious but adding a boundary makes ownership robust |
| J additional experiments | p19 | Table14 p20; Figures5–7 pp21,22,23 | Size and budget figures appear in K.2–K.4, two to four pages after their callouts |

Recommended minimal boundary set: appendix-only `\\FloatBarrier` before `\\section{Representative Long-\\scc{} Case Study}` (old `acl_latex.tex:535`), before Core Algorithm Details (:547), before Formula Details (:639), before Shared Risk Rubric (:735), before Additional Experimental Details (:829), and before `\\input{revision_experiments}` (:882). This clears each preceding appendix's floats without affecting main-text pagination. Use fresh compilation to assess appendix whitespace/page count and float order; do not assume `FloatBarrier` is cost-free.

### 2. Ambiguous panel pointers

- `paper/latex/revision_experiments.tex:85`: “Panel B extends ...” follows a Table16 cost callout, but B belongs to **Table15 Stage-1 ablations**. Replace the opening with `Table~\\ref{tab:revision_stage1}, panel B, extends ...` or `Panel B of Table~\\ref{tab:revision_stage1} extends ...`.
- `paper/latex/revision_experiments.tex:108`: “whereas Stage-1 Panel B includes ...” is semantically clear but unlinked. Prefer `whereas Table~\\ref{tab:revision_stage1}, panel B, includes ...`.

### 3. Optional navigation improvements, not numerical errors

Appendix D / Algorithms2–5, Table6 (expert instructions), Table13 (injection templates), and Table18 (complete cost results) have labels but no direct numbered callout in active manuscript text. Their context makes their purpose clear, so this is not evidence of a broken reference. If adding callouts, keep them short and appendix-local to preserve the main text's page budget.

`acl_latex.tex:766` points to all of Appendix K for LEA's window construction; the more precise destination is `app:revision_lea` (K.1), but the current link is valid.

`acl_latex.tex:848` states “Absolute results appear in Figure6 and Table14.” Figure6 provides per-model × size results; Table14 provides separate aggregate breakdowns by model/domain/size. These are both absolute results, so this is not a contradiction, but the table must not be described elsewhere as giving every model × size numerical cell.

## Figure content and panel checks

| Label / clean number | Source asset | Visual validation |
|---|---|---|
| `fig:case` / Figure4 p15 | `fig06_representative_scc_three_methods.pdf` | Panels a/b/c = One-shot/LEA/SA-MCGS. 25 BGB records, root §505, witness §491. Retained3/12/9, compression88/52/64, One-shot root absent. Caption and prose at :541/:545 match. |
| `fig:main_metrics` / Figure5 p21 | `fig02_scale_gain_heatmaps.pdf` | a Root@3, b Risk-all; five model rows; n36/24/20 size columns; blue gains/orange losses. GPT4o Risk-all medium+37.50 and Qwen2.5+62.50 match :848. Llama Root@3 positive in all groups. |
| `fig:absolute_size_breakdowns` / Figure6 p22 | `fig02_main_results_five_models.pdf` | Five model columns; a Root@3/b Risk-all rows. Gray circle One-shot, orange square LEA, blue triangle SA-MCGS. Same size groups as Figure5; caption :862 matches. |
| `fig:convergence` / Figure7 p23 | `fig04_budget_prefix_three_methods.pdf` | a complete risk evidence/b compression, SA blue solid; One-shot gray dotted and LEA orange dashed horizontal baselines. Final75.00/51.26 matches Table2 GPT4o. Caption :877 and prose :872 match. |

Asset paths use `graphicspath` at `acl_latex.tex:26`; filenames' historical fig02/fig04/fig06 prefixes are internal asset names, not stale printed Figure numbers. `revasset` always selects its second/current argument.

## Clean appendix object inventory

| Object | Label | Clean number | Page before fixes |
|---|---|---|---|
| Original expert audit | tab:expert_audit_results | Table5 | 13 |
| Expert instructions | tab:expert_protocol | Table6 | 13 |
| Original expert example | tab:expert_example | Table7 | 14 |
| Expanded audit agreement | tab:expert_new_agreement | Table8 | 14 |
| Expanded evidence quality | tab:expert_new_quality | Table9 | 15 |
| Natural-negative audit | tab:expert_pre_negative | Table10 | 16 |
| Long-SCC example | fig:case | Figure4 | 15 |
| SCC search | alg:appendix_scc_localized | Algorithm2 | 16 |
| Rollout | alg:appendix_rollout | Algorithm3 | 16 |
| Memory | alg:appendix_relation_memory | Algorithm4 | 16 |
| Dynamic core | alg:appendix_dynamic_core | Algorithm5 | 17 |
| Prior coefficients | tab:prior_coefficients | Table11 | 18 |
| Datasets/coverage (two aliases) | tab:dataset_processing; tab:domains | Table12 | 19 |
| Injection templates | tab:injection_templates | Table13 | 19 |
| Complete breakdowns | tab:appendix_breakdowns | Table14 | 20 |
| Size gains | fig:main_metrics | Figure5 | 21 |
| Absolute size results | fig:absolute_size_breakdowns | Figure6 | 22 |
| Prefix results | fig:convergence | Figure7 | 23 |
| Stage1 | tab:revision_stage1 | Table15 | 22 |
| Stage1 cost | tab:revision_stage1_cost | Table16 | 22 |
| Stage2 | tab:revision_stage2 | Table17 | 22 |
| Complete cost | tab:revision_cost_full | Table18 | 23 |
| Prior sensitivity | tab:revision_prior | Table19 | 24 |

## Marked-view behavior

Retired tables/figure in `revision_retired_controls.tex` are wrapped by `revdeletedtable` and absent from the clean PDF; they deliberately remain in the marked PDF with deletion markings. They consume counters only in the marked view, so marked and clean Figure/Table numbers differ. This is expected, not a clean-source alignment error. Current `tab:appendix_breakdowns` and retired `tab:appendix_breakdowns:previous` are distinct labels (via `revoldlabel`), so the five-model active callout goes to the current table, not the historical four-model table.

The retained historical captions inside soft deletion still describe the old figures, whereas revised captions describe current assets. No inactive historical reference should be counted as an active scientific claim. Float barriers should be validated in both views, but only the clean view has submission page-limit significance.

## Complete reference coverage

The table below lists every active command in this appendix scope. Repeated entries on a line are intentional separate references. All were checked against target content and clean-PDF position.

| Source file:line | Target key | Printed target | Page | Check |
|---|---|---|---|---|
| paper/latex/acl_latex.tex:422 | `tab:mcts_scc` | Table1 | 3 | Motivation diagnostic/control matches A definitions |
| paper/latex/acl_latex.tex:427 | `tab:mcts_scc` | Table1 | 3 | Motivation diagnostic/control matches A definitions |
| paper/latex/acl_latex.tex:440 | `app:expert_extension` | B.2 | 12 | Expanded paired expert audit |
| paper/latex/acl_latex.tex:466 | `tab:expert_audit_results` | Table5 | 13 | Original 12-case results |
| paper/latex/acl_latex.tex:531 | `tab:expert_example` | Table7 | 14 | Paired SEC entity example |
| paper/latex/acl_latex.tex:545 | `fig:case` | Figure4 | 15 | Current three-method25-record BGB figure |
| paper/latex/acl_latex.tex:642 | `sec:method` | §3 | 2 | Method equations expanded by AppendixE |
| paper/latex/acl_latex.tex:663 | `eq:relation-prior` | Eq5 | 4 | Shared prior formula |
| paper/latex/acl_latex.tex:682 | `eq:priority` | Eq7 | 4 | Priority with OC bonus |
| paper/latex/acl_latex.tex:685 | `eq:core` | Eq8 | 5 | Dynamic-core objective |
| paper/latex/acl_latex.tex:695 | `tab:prior_coefficients` | Table11 | 18 | Node/edge/pair fixed coefficients |
| paper/latex/acl_latex.tex:704 | `eq:relation-prior` | Eq5 | 4 | Shared prior formula |
| paper/latex/acl_latex.tex:713 | `eq:relation-prior` | Eq5 | 4 | Shared prior formula |
| paper/latex/acl_latex.tex:722 | `eq:critical-pair` | Eq11 | 16 | Critical-pair ledger weights |
| paper/latex/acl_latex.tex:766 | `app:revision_experiments` | K | 19 | Additional baseline/ablation/cost methods |
| paper/latex/acl_latex.tex:781 | `tab:dataset_processing` | Table12 | 19 | Four domains and graph conversion |
| paper/latex/acl_latex.tex:834 | `app:revision_experiments` | K | 19 | Additional baseline/ablation/cost methods |
| paper/latex/acl_latex.tex:834 | `tab:appendix_breakdowns` | Table14 | 20 | Five-model/domain/size aggregate results |
| paper/latex/acl_latex.tex:848 | `fig:main_metrics` | Figure5 | 21 | SA–LEA size gain heatmap |
| paper/latex/acl_latex.tex:848 | `fig:absolute_size_breakdowns` | Figure6 | 22 | Three-method absolute model×size results |
| paper/latex/acl_latex.tex:848 | `tab:appendix_breakdowns` | Table14 | 20 | Five-model/domain/size aggregate results |
| paper/latex/acl_latex.tex:853 | `fig:absolute_size_breakdowns` | Figure6 | 22 | Three-method absolute model×size results |
| paper/latex/acl_latex.tex:857 | `fig:absolute_size_breakdowns` | Figure6 | 22 | Three-method absolute model×size results |
| paper/latex/acl_latex.tex:857 | `fig:main_metrics` | Figure5 | 21 | SA–LEA size gain heatmap |
| paper/latex/acl_latex.tex:872 | `fig:convergence` | Figure7 | 23 | GPT4o prefix retention/compression |
| paper/latex/acl_latex.tex:872 | `tab:matched_main` | Table2 | 7 | GPT4o final75/51.26 matches |
| paper/latex/revision_experiments.tex:38 | `tab:revision_stage1` | Table15 | 22 | Stage1 full/subset breakdown |
| paper/latex/revision_experiments.tex:65 | `tab:revision_stage1_cost` | Table16 | 22 | Stage1 calls/tokens |
| paper/latex/revision_experiments.tex:108 | `tab:revision_stage2` | Table17 | 22 | Dynamic/locked paired replay |
| paper/latex/revision_experiments.tex:161 | `eq:revision_parallel_time` | Eq16 | 23 | Parallel walltime approximation |
| paper/latex/revision_experiments.tex:166 | `tab:prior_coefficients` | Table11 | 18 | Node/edge/pair fixed coefficients |
| paper/latex/revision_experiments.tex:186 | `tab:revision_prior` | Table19 | 24 | Prior multiplier sensitivity |
| paper/latex/revision_expert_appendix.tex:39 | `tab:expert_new_agreement` | Table8 | 14 | Pre-adjudication judgments |
| paper/latex/revision_expert_appendix.tex:68 | `tab:expert_new_quality` | Table9 | 15 | Unaugmented expert repair references |
| paper/latex/revision_expert_appendix.tex:98 | `tab:expert_pre_negative` | Table10 | 16 | False-positive/abstention/invalid counts |

Machine-readable full source contexts and all 50 labels are saved in `active_inventory.json`; pre-fix PDF page text/images in this same scratch directory.

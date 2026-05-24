# Paper Figure and Table Plan

本文档只记录论文需要放的图表，避免写作时混用旧实验、诊断图或临时 dashboard。

## 主文图表 / Main Paper

| ID | Type | Title / Purpose | Placement | Source / Status | Priority |
|---|---|---|---|---|---|
| Figure 1 | Diagram | **SA-MCGS Pipeline**: document graph -> Tarjan SCC -> SCC-aware rollout -> evidence memory -> dynamic core -> collapsed risk subgraph | Method opening | Final: `paper_assets/figures/fig01_sa_mcgs_framework_architecture.pdf/png` | P0 |
| Table 1 | Table | **Why Standard MCTS Fails on SCCs**: TreeMCTS DAG vs TreeMCTS Cycle vs SA-MCGS Cycle, with Expansion / Truncation / Q-spread / Hit@3 | End of Introduction or Method motivation | Values already in `PAPER_FRAMEWORK.md`; need LaTeX table | P0 |
| Table 2 | Table | **Domain Coverage and Authority**: Debian / SEC EX-21 / BGB / CUAD, source authority, graph source, noise level, paper role | Experimental Setup | Values already in `PAPER_FRAMEWORK.md`; need LaTeX table | P0 |
| Table 3 | Table | **Main Strict Results**: Root@3, Risk-any, Risk-all, Compression, unavailable structured outputs for Naive vs SA-MCGS | Main Results | `experiments/main_experiment/MANIFEST.json` and `supplements/tables/E0_matched_valid_only.csv` | P0 |
| Figure 2 | Composite bar chart | **Main Metrics Strict**: strict headline, matched usable-output robustness, and output-availability accounting | Main Results, near Table 3 | Final: `paper_assets/figures/fig02_main_metrics_strict.pdf/png` | P0 |
| Figure 3 | Composite size chart | **Metrics by SCC Size**: whether gains change with longer SCCs, including coverage and compression | Main Results or Analysis | Final: `paper_assets/figures/fig03_main_by_scc_size.pdf/png` | P0 |
| Figure 4 | Line chart | **Rollout Convergence**: Risk-any / Risk-all / Root@3 / coverage / compression over budget prefixes | Analysis | Final: `paper_assets/figures/fig04_budget_prefix_convergence.pdf/png` | P0 |
| Figure 5 | Trade-off chart | **Compression Profile Ablation**: current/default vs balanced; shows why stronger compression hurts Risk-all | Analysis | Final: `paper_assets/figures/fig05_compression_profile_tradeoff.pdf/png` | P1 |
| Figure 6 | Case diagram | **Representative SCC Collapse Case**: root/witness/affected/core nodes before and after SA-MCGS | Case Study | Final: `paper_assets/figures/fig06_representative_scc_collapse.pdf/png` | P1 |

## Appendix / Supplement 图表

| ID | Type | Title / Purpose | Placement | Source / Status | Priority |
|---|---|---|---|---|---|
| Table A1 | Table | **Strict vs Valid-only vs Matched usable-output**: shows unavailable outputs are counted, not hidden | Appendix / output-availability analysis | Existing: `supplements/tables/E0_matched_valid_only.csv`; figure `E0_strict_vs_matched.pdf` | P0 |
| Table A2 | Table | **Naive Output-burden Control**: full direct-subgraph vs lite Naive on CUAD long SCCs | Appendix / Baseline fairness | Existing: `supplements/tables/E1_naive_output_burden_control.csv` | P0 |
| Figure A2 | Bar chart | **Naive Output-burden Control**: shows that shortening Naive output improves output availability but does not close the SA-MCGS retention gap | Appendix / Baseline fairness | Final: `paper_assets/figures/figA2_naive_output_burden.pdf/png` | P1 |
| Table A3 | Table | **Prompt/Rubric Parity**: shared risk semantics between Naive and SA-MCGS | Appendix / Fairness | Existing: `supplements/tables/E5_prompt_rubric_parity.csv`; narrative in `E5_PROMPT_RUBRIC_PARITY.md` | P0 |
| Table A4 | Table | **Model-level Breakdown**: gpt-4o / deepseek-v3 / qwen2.5-72b / gemini-2.5-pro | Appendix or compressed main table if space allows | Need derive from main result JSON/tables | P1 |
| Table A5 | Table | **Domain-level Breakdown**: Debian / SEC EX-21 / BGB / CUAD | Appendix; maybe main if reviewer concern is high | Need derive from main result JSON/tables | P1 |

## 图表口径规则

- 主实验只用 `current/default + structural_simple_v2 + critical + 80 SCC blocks/model + 4 models`。
- 不把 `balanced`、旧 `memory_stress`、Wikipedia exploratory、Gemini Flash、smoke/diagnostic runs 放进主文主表。
- `Effective OC` 只能写成 cumulative discovery / convergence support，不作为主指标图。
- `Risk-all` 是 critical 风险下的核心完整性指标，不能弱化成 appendix-only。
- Compression 要和 Risk-all 一起解释：压缩率下降不是失败，而是为了保留更多 critical endpoints。

## 还需要制作的图表

当前主文图表已经生成并接入 `paper/latex/acl_latex.tex`。后续只需要在写作压缩时决定 Figure 5 / Figure 6 是否留在主文，或移到 appendix。

# Paper Figure and Table Plan

本文档只记录论文需要放的图表，避免写作时混用旧实验、诊断图或临时 dashboard。

## 主文图表 / Main Paper

| ID | Type | Title / Purpose | Placement | Source / Status | Priority |
|---|---|---|---|---|---|
| Figure 1 | Diagram | **SA-MCGS Pipeline**: document graph -> Tarjan SCC -> SCC-aware rollout -> evidence memory -> dynamic core -> collapsed risk subgraph | Method opening | Need draw clean vector/PDF from current framework | P0 |
| Table 1 | Table | **Why Standard MCTS Fails on SCCs**: TreeMCTS DAG vs TreeMCTS Cycle vs SA-MCGS Cycle, with Expansion / Truncation / Q-spread / Hit@3 | End of Introduction or Method motivation | Values already in `PAPER_FRAMEWORK.md`; need LaTeX table | P0 |
| Table 2 | Table | **Domain Coverage and Authority**: Debian / SEC EX-21 / BGB / CUAD, source authority, graph source, noise level, paper role | Experimental Setup | Values already in `PAPER_FRAMEWORK.md`; need LaTeX table | P0 |
| Table 3 | Table | **Main Strict Results**: Root@3, Risk-any, Risk-all, Compression, Errors for Naive vs SA-MCGS | Main Results | `experiments/main_experiment/MANIFEST.json` and `supplements/tables/E0_matched_valid_only.csv` | P0 |
| Figure 2 | Bar chart | **Main Metrics Strict**: visual version of Root@3 / Risk-any / Risk-all / Compression | Main Results, near Table 3 | Existing: `supplements/figures/main_metrics_strict.pdf` | P0 |
| Figure 3 | Line/bar chart | **Metrics by SCC Size**: whether gains change with longer SCCs | Main Results or Analysis | Existing: `supplements/figures/main_by_scc_size.pdf` | P0 |
| Figure 4 | Line chart | **Rollout Convergence**: Risk-any / Risk-all / coverage / compression over budget prefixes | Analysis | Existing: `supplements/figures/E2_budget_prefix_convergence.pdf` | P0 |
| Figure 5 | Trade-off chart | **Compression Profile Ablation**: current/default vs balanced; shows why stronger compression hurts Risk-all | Analysis | Existing: `supplements/figures/E3_profile_tradeoff.pdf` | P1 |
| Figure 6 | Case diagram | **Representative SCC Collapse Case**: root/witness/affected/core nodes before and after SA-MCGS | Case Study | Need generate from one BGB clean long-SCC case or CUAD noisy case | P1 |

## Appendix / Supplement 图表

| ID | Type | Title / Purpose | Placement | Source / Status | Priority |
|---|---|---|---|---|---|
| Table A1 | Table | **Strict vs Valid-only vs Matched-no-error**: shows errors are counted, not hidden | Appendix / Error analysis | Existing: `supplements/tables/E0_matched_valid_only.csv`; figure `E0_strict_vs_matched.pdf` | P0 |
| Figure A1 | Bar chart | **E0 Error Handling Visual** | Appendix | Existing: `supplements/figures/E0_strict_vs_matched.pdf` | P1 |
| Table A2 | Table | **Naive Output-burden Control**: full direct-subgraph vs lite Naive on CUAD long SCCs | Appendix / Baseline fairness | Existing: `supplements/tables/E1_naive_output_burden_control.csv` | P0 |
| Figure A2 | Bar chart | **E1 Naive Output-burden Visual** | Appendix | Existing: `supplements/figures/E1_naive_output_burden.pdf` | P1 |
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

1. **Figure 1 pipeline vector**：从前端框架图重画为 ACL 友好的 PDF，控制在单栏或双栏都清晰。
2. **Table 1 MCTS failure table**：直接用 framework 数字，放在 Introduction/Method motivation。
3. **Table 2 domain authority table**：写明四个数据集的权威性和泛化角色。
4. **Figure 6 case diagram**：选 1 个 BGB clean case 或 CUAD noisy case，展示 SCC -> risk subgraph collapse。
5. **Table A4/A5 breakdown**：按 model/domain 生成，防止 reviewer 问“是不是某个模型或某个域撑起来的”。


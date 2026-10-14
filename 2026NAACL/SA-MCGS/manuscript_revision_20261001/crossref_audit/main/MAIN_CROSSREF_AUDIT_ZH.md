# 主文交叉引用核对（只读）

当前净稿：24 页，正文结束于第 8 页。共核对 **33 处活跃交叉引用、24 个不同目标**。检查采用当前修订宏的净稿语义，排除了软删除历史文字。未发现主文的失效引用、错误图号/表号、图与说明错配或活跃旧分面引用。

## 覆盖明细

| 来源 | 引用目标 | 目标净稿页 | 核对内容 |
|---|---|---:|---|
| `paper/latex/acl_latex.tex:84` | Figure 1 (`fig:pipeline`) | 3 | SA-MCGS framework: SCC localization, local rollouts, evidence memory, dynamic core；对应正确 |
| `paper/latex/acl_latex.tex:117` | Appendix A (`app:diagnostics`) | 11 | Effective compression/OC plus TreeMCTS Expansion, Truncation, Q-spread, Hit@3 definitions；对应正确 |
| `paper/latex/acl_latex.tex:133` | Figure 2 (`fig:mcts_failure`) | 3 | TreeMCTS cyclic-path duplication diagnostic and SA-MCGS comparison；对应正确 |
| `paper/latex/acl_latex.tex:133` | Table 1 (`tab:mcts_scc`) | 3 | DAG vs SCC TreeMCTS and SCC SA-MCGS motivating ablation；对应正确 |
| `paper/latex/acl_latex.tex:133` | Appendix A (`app:diagnostics`) | 11 | Effective compression/OC plus TreeMCTS Expansion, Truncation, Q-spread, Hit@3 definitions；对应正确 |
| `paper/latex/acl_latex.tex:200` | Appendix F (`app:priors`) | 16 | Fixed search-prior coefficients; corresponding Table 11 on page 18；对应正确 |
| `paper/latex/acl_latex.tex:200` | Equation 4 (`eq:ucb`) | 4 | Shared UCB selection template with visit-decayed prior；对应正确 |
| `paper/latex/acl_latex.tex:208` | Appendix E (`sec:appendix_formula_details`) | 15 | Exact node/relation updates and OC threshold definition; continues page 16；对应正确 |
| `paper/latex/acl_latex.tex:222` | Appendix E (`sec:appendix_formula_details`) | 15 | Exact node/relation updates and OC threshold definition; continues page 16；对应正确 |
| `paper/latex/acl_latex.tex:222` | Equation 7 (`eq:priority`) | 4 | Core priority includes OC bonus gamma*o_t(v)；对应正确 |
| `paper/latex/acl_latex.tex:239` | Section 6.2 (`sec:component_tests`) | 6 | Stage-1 ablations and Stage-2 same-trace core replacement replay；对应正确 |
| `paper/latex/acl_latex.tex:249` | Equation 4 (`eq:ucb`) | 4 | Shared UCB selection template with visit-decayed prior；对应正确 |
| `paper/latex/acl_latex.tex:254` | Equation 8 (`eq:core`) | 5 | Bounded dynamic-core selection objective；对应正确 |
| `paper/latex/acl_latex.tex:272` | Appendix J.2 (`app:budget_prefix`) | 19 | Budget-prefix convergence analysis; Figure 7 on page 23；对应正确 |
| `paper/latex/acl_latex.tex:273` | Section 6.3 (`sec:cost_analysis`) | 7 | Inference cost and prior sensitivity, corresponding Table 4 page 7；对应正确 |
| `paper/latex/acl_latex.tex:280` | Appendix I (`sec:appendix_datasets`) | 17 | Domain formatter/graph construction and injection templates; Tables 12 and 13 page 19；对应正确 |
| `paper/latex/acl_latex.tex:313` | Appendix I (`sec:appendix_datasets`) | 17 | Domain formatter/graph construction and injection templates; Tables 12 and 13 page 19；对应正确 |
| `paper/latex/acl_latex.tex:317` | Appendix I (`sec:appendix_datasets`) | 17 | Domain formatter/graph construction and injection templates; Tables 12 and 13 page 19；对应正确 |
| `paper/latex/acl_latex.tex:317` | Appendix J (`sec:appendix_experiments`) | 19 | Run-configuration overview that forwards actual method protocol to Appendix K；对应正确 |
| `paper/latex/acl_latex.tex:335` | Figure 3 (`fig:paired_case_outcomes`) | 8 | Paired Risk-all outcomes; panel a One-shot, panel b LEA；对应正确 |
| `paper/latex/acl_latex.tex:351` | Table 14 (`tab:appendix_breakdowns`) | 20 | Five-model results; A models, B domains, C SCC sizes；对应正确 |
| `paper/latex/acl_latex.tex:352` | Appendix C (`sec:appendix_case`) | 14 | Same 25-record BGB/Gemini case comparison; Figure 4 page 15；对应正确 |
| `paper/latex/acl_latex.tex:354` | Appendix J.1 (`app:size_breakdowns`) | 19 | Per-model SCC size analysis; Figure 5 heatmap page 21 and Figure 6 absolute values page 22；对应正确 |
| `paper/latex/acl_latex.tex:367` | Appendix J.2 (`app:budget_prefix`) | 19 | Budget-prefix convergence analysis; Figure 7 on page 23；对应正确 |
| `paper/latex/revision_baselines.tex:6` | Appendix K.1 (`app:revision_lea`) | 19 | Four-node window construction, aggregation, caches, same input/model protocol；对应正确 |
| `paper/latex/revision_main_results.tex:40` | Table 2 (`tab:matched_main`) | 7 | Main 5-model, 3-method, 80-case Root@3/Risk-any/Risk-all/compression comparison；对应正确 |
| `paper/latex/revision_main_analysis.tex:5` | Table 3 (`tab:component_main`) | 7 | Contemporaneous 17-variant Stage-1 and 80-variant Stage-2 summary；对应正确 |
| `paper/latex/revision_main_analysis.tex:5` | Appendix K (`app:revision_experiments`) | 19 | K.2 Stage-1 and cost, K.3 paired core replay, K.4 cost/recovery/time, K.5 prior sensitivity；对应正确 |
| `paper/latex/revision_main_analysis.tex:49` | Table 4 (`tab:cost_main`) | 7 | 12-source/two-model/three-method cost and strict Risk-all summary；对应正确 |
| `paper/latex/revision_main_analysis.tex:49` | Appendix K (`app:revision_experiments`) | 19 | K.2 Stage-1 and cost, K.3 paired core replay, K.4 cost/recovery/time, K.5 prior sensitivity；对应正确 |
| `paper/latex/revision_main_analysis.tex:51` | Appendix K (`app:revision_experiments`) | 19 | K.2 Stage-1 and cost, K.3 paired core replay, K.4 cost/recovery/time, K.5 prior sensitivity；对应正确 |
| `paper/latex/revision_expert_main.tex:5` | Appendix B.2 (`app:expert_extension`) | 12 | 42-presentation annotation, agreement, quality, negative source and recovery outcomes; Tables 8-10 pp14-16；对应正确 |
| `paper/latex/revision_expert_main.tex:9` | Appendix B.2 (`app:expert_extension`) | 12 | 42-presentation annotation, agreement, quality, negative source and recovery outcomes; Tables 8-10 pp14-16；对应正确 |

## 可选的定位精确化（不是编号错乱）

- `paper/latex/acl_latex.tex:317`：Appendix J only forwards configuration to Appendix K. The reference resolves, but makes the reader follow a second link. 最小修改：`Appendix~\ref{app:revision_lea} specifies the method protocol.`。
- `paper/latex/acl_latex.tex:335`：Sentence discusses only SA-MCGS versus LEA; this is specifically panel (b). Both caption and figure are already correct. 最小修改：`Figure~\ref{fig:paired_case_outcomes}b`。
- `paper/latex/acl_latex.tex:351`：Domain values are in panel B of the 3-part table. Current general table reference is valid. 最小修改：`Table~\ref{tab:appendix_breakdowns}B`。
- `paper/latex/revision_main_analysis.tex:49`：Parallel-time/recovery details are specifically K.4. Broad K reference is valid. 最小修改：`Appendix~\ref{app:revision_cost}`。
- `paper/latex/revision_main_analysis.tex:51`：Prior-sensitivity details are specifically K.5. Broad K reference is valid. 最小修改：`Appendix~\ref{app:revision_prior}`。

## 改稿后最需要核对的迁移项

- 主文配对结果图是 **Figure 3，第 8 页**；净稿 §5 已正确引用 Figure 3。该图的 LEA 比较确实是右侧 panel b，GPT-4o 的 SA-only 32 与 LEA-only 7 匹配正文。
- SCC 尺度分析已在 **Appendix J.1（第 19 页）**，正文不再以旧主文图号指向它。尺度增益热力图是 **Figure 5（第 21 页）**；绝对值图为 **Figure 6（第 22 页）**。
- 预算曲线位于 **Appendix J.2**，实际 **Figure 7（第 23 页）**；主文两处均正确转指 J.2。
- 领域覆盖表已移至 **Appendix I**，主文指向 Appendix I，数据源表与旧 domains 标签共同映射 Table 12 是兼容别名，不是重复表。
- 域分解数据位于 **Table 14（第 20 页）panel B**；正文 BGB 26.67→51.67、CUAD 53.00→69.00 与表一致。
- 核心伪代码 **Algorithm 1 第 5 页**内部指向 Equation 4 / 8 正确。没有正文句子明确叫出 Algorithm 1，但这属于写作可选增强，不是错误引用。
- 图表排版有正常浮动：主文第 6 页提及主表/配对图，实际分别在第 7/8 页。没有错误的 above/below 方位断言；无需为了页序移动资产。

## 图像核验

已读取净稿第 3、8 页渲染，确认 Figure 1 框架、Figure 2 动机、Figure 3 双面配对图与当前图注及正文语义一致。渲染位于同目录 `render_page_03.png`、`render_page_08.png`。本子任务没有修改论文文件。

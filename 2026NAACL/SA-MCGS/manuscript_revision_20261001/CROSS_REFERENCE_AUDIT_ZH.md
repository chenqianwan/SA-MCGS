# 图表、算法与附录交叉引用核对清单

更新：2026-10-01。本文件记录本轮核对后的实际净稿；历史修改清单中的旧页码不再作为当前定位依据。

**7 张图、19 张表、5 个算法已逐项对应实际内容、图注、标签、编号和 PDF 位置。初核没有发现净稿指向错误图表或编号失效；发现并修复了图注残留、指引不够精确，以及附录浮动图表进入后续无关章节的问题。**

最终净稿正文仍在第 8 页结束，Limitations 从第 9 页开始。附录重新排布后，净稿全文 **26 页**（原 24 页），修订稿 **31 页**（原 29 页）。主文所有图表的所在页保持不变。字体、页边距、图表内容、数据、公式和算法正文未改。

## 1. 发现与实际处理

| 项目 | 原来的问题 | 本次处理 |
|---|---|---|
| 专家案例表图注（净稿 Table 7） | 仍称“左列的角色名”，实际左列只有实体 A/B 和 case-level decision | 原黑字软删除；红字改为准确的匿名展示说明，不再声称有角色名 |
| §4.3 实验配置指引 | 指到 J，而 J 再转指 K | 直接指向 K.1；附录 H、J 的相同 LEA／配置指引也直接到 K.1 |
| 主文组件、成本、敏感性细节 | 均笼统指到附录 K | 分别指到 K.2/K.3、K.4、K.5 |
| LEA 配对收益与领域分解 | 只给图／表总编号 | 指到 Figure 3b 与 Table 14 的 panel B |
| 跨批次 Stage-1 解释 | “Panel B”前面刚引用过另一张成本表，容易误认 | 两处都明确写出 Table 15, panel B，并提供链接 |
| 少数独立图表／算法缺编号指引 | 标注任务表、注入模板表、完整成本表及算法只有标题／泛指 | 在附录原有说明处补 Table 6、13、18 和 Algorithms 2–5 / Algorithm 1 的指引 |
| 附录 B/C/D 的浮动内容 | 专家表、案例图和算法延迟排入后续附录 | 在相关附录边界清理待排浮动对象；附录 D 的四个算法按源文顺序就地排布 |
| 附录 F/I/J 的浮动内容 | 系数表、数据表和规模／预算图进入后续附录，尤其 J 的图出现在 K 中 | 增加局部浮动边界；J 的所有图表现在结束于第 22 页，K 从第 23 页开始 |
| 浮动约束带来的空白 | 试排时系数介绍与宽表分成两页，K 标题间距被拉大 | 调整宽表入队顺序，使 Table 11 与 F 的说明同在第 18 页；附录采用自然段底对齐，避免拉伸空白 |

新增／改写文字沿用红色。旧黑字修改采用软删除。此次没有改变图表编号；变化的是部分附录页码和指引精度。

## 2. 全部图的位置

以下数字均为**当前净稿**。最后一列给出修订稿的编号／页码，便于交叉查看。修订稿保留已删除的旧图表，因此两版后续编号可以不同；两版各自的引用均已检查。

| 图 | 内容 | 归属 | 原净稿页 → 当前净稿页 | 修订稿编号／页 |
|---|---|---|---|---|
| Figure 1 | SA-MCGS 框架 | 主文 Introduction | 3 → **3** | Figure 1／p. 3 |
| Figure 2 | TreeMCTS 循环搜索动机 | 主文 §3.1 | 3 → **3** | Figure 2／p. 5 |
| Figure 3 | 逐案例配对收益：a One-shot，b LEA | 主文 §5 | 8 → **8** | Figure 3／p. 10 |
| Figure 4 | 同一 BGB 案例的三方法子图 | 附录 C | 15 → **16** | Figure 4／p. 18 |
| Figure 5 | 规模分组收益热图：a Root@3，b Risk-all | 附录 J.1 | 21 → **21** | Figure 6／p. 24 |
| Figure 6 | 规模分组三方法绝对值 | 附录 J.1 | 22 → **22** | Figure 7／p. 26 |
| Figure 7 | 预算前缀：a Risk-all，b Compression | 附录 J.2 | 23 → **22** | Figure 8／p. 27 |

## 3. 全部表的位置

| 表 | 内容 | 归属 | 原净稿页 → 当前净稿页 | 修订稿编号／页 |
|---|---|---|---|---|
| Table 1 | TreeMCTS / SA-MCGS 诊断 | 主文 §3.1 | 3 → **3** | Table 1／p. 4 |
| Table 2 | 五模型 × 三方法主结果 | 主文 §5 | 7 → **7** | Table 3／p. 9 |
| Table 3 | Stage-1 / Stage-2 组件结果 | 主文 §6.2 | 7 → **7** | Table 4／p. 9 |
| Table 4 | 成本与效果摘要 | 主文 §6.3 | 7 → **7** | Table 5／p. 10 |
| Table 5 | 原 12-case 专家结果 | 附录 B.1 | 13 → **13** | Table 6／p. 15 |
| Table 6 | 原专家标注任务 | 附录 B.1 | 13 → **13** | Table 7／p. 16 |
| Table 7 | 专家审计示例 | 附录 B.1 | 14 → **14** | Table 8／p. 16 |
| Table 8 | 裁决前标注一致性 | 附录 B.2 | 14 → **14** | Table 9／p. 16 |
| Table 9 | 专家参考证据质量 | 附录 B.2 | 15 → **15** | Table 10／p. 17 |
| Table 10 | 未修改原文的负例审计 | 附录 B.2 | 16 → **15** | Table 11／p. 17 |
| Table 11 | 固定先验系数 | 附录 F | 18 → **18** | Table 12／p. 21 |
| Table 12 | 领域覆盖、数据构建与用途 | 附录 I | 19 → **20** | Table 13／p. 23 |
| Table 13 | 四类结构性注入模板 | 附录 I | 19 → **20** | Table 14／p. 23 |
| Table 14 | A 模型 / B 领域 / C 规模分解 | 附录 J | 20 → **21** | Table 18／p. 26 |
| Table 15 | Stage-1：A 同期 / B 跨批次描述 | 附录 K.2 | 22 → **25** | Table 19／p. 30 |
| Table 16 | 同期 Stage-1 的成本 | 附录 K.2 | 22 → **25** | Table 20／p. 30 |
| Table 17 | Stage-2 配对核心回放 | 附录 K.3 | 22 → **25** | Table 21／p. 30 |
| Table 18 | 分模型完整成本与可靠性 | 附录 K.4 | 23 → **26** | Table 22／p. 31 |
| Table 19 | 先验敏感性 | 附录 K.5 | 24 → **26** | Table 23／p. 31 |

`tab:domains` 与 `tab:dataset_processing` 是合并后同一张 Table 12 的两个兼容标签，不是重复表或冲突编号。当前五模型分解表使用 `tab:appendix_breakdowns`；修订稿内被删除的旧分解表使用独立的 `:previous` 标签，不会把净稿引用引向旧结果。

## 4. 全部算法的位置

| 算法 | 内容 | 归属 | 原净稿页 → 当前净稿页 | 修订稿编号／页 |
|---|---|---|---|---|
| Algorithm 1 | 单 SCC 的高层流程 | 主文 §3.6 | 5 → **5** | Algorithm 1／p. 6 |
| Algorithm 2 | SCC-localized search | 附录 D | 16 → **16** | Algorithm 2／p. 18 |
| Algorithm 3 | 局部 rollout | 附录 D | 16 → **16** | Algorithm 3／p. 19 |
| Algorithm 4 | Relation-first evidence memory | 附录 D | 16 → **17** | Algorithm 4／p. 19 |
| Algorithm 5 | Dynamic core compression | 附录 D | 17 → **17** | Algorithm 5／p. 19 |

Algorithms 2–5 在附录 D 的引导句中作为一个编号范围引用，包含中间的 Algorithms 3、4。高层 Algorithm 1 保持在正文；本次只补指引，没有移动它。

## 5. 编号与内容双重核查结果

- 初始净稿有 **68 处有效交叉引用、43 个不同目标**；补充精确指引后为 **77 处、51 个不同目标**，包括图、表、算法、章节与公式。
- 两次均无未定义标签、重复标签或引用编号未解析的问题。不存在用手写旧 Figure / Table 数字替代现有自动引用的活跃错指。
- 重新读取实际 PDF 链接：净稿 **238 个**内部命名链接、修订稿 **271 个**，全部可解析；所有标签的页码与 PDF 跳转目标页相符。这一链接总数也包含文献引用等，并不等于图表引用数量。
- Figure 3 的两组比较、十条分组计数及净差与主表一致；Table 2 与 Table 14A 的 15 行、四项指标逐数一致。
- Figure 4 的案例节点／方法／指标、Figure 5 的差值与色标、Figure 6 的绝对值和图例、Figure 7 的预算前缀和基线方向均核对通过。
- 所有 `tabular` 表格内容、`equation` 公式、`algorithmic` 算法正文与 `includegraphics` 命令保持原样；文献库和 ACL 样式未变。
- 净稿未产生 overfull 警告；修订稿仅保留原先 Introduction 软删除区域的 overfull 提示，没有新增此类问题。

图表有时位于同页顶部、先于引用它的小节标题，属于双栏浮动的正常排法。例如 Table 11 位于第 18 页顶部，F 的标题和说明紧随其后。它不再夹在数据构建等无关附录中。本次没有强求所有图表都出现在第一次引用之后，也没有以缩小图中文字来压页数。

旧黑字的删除历史不按现行科学叙述重新改写。例如已删除的旧分面说明在修订稿中仍可见，但不进入净稿；核查时将它们与有效正文分开。

## 6. 当前 77 处交叉引用逐项定位

此表由最终源码的净稿投影与新编译的 `.aux`、实际 PDF 目标共同生成。正文和附录都包含；已删除文字及退休图表不计入。完整上下文另存于机器清单。

| 序号 | 引用所在文件／行 | 引用目标 | 当前编号 | 净稿目标页 |
|---|---|---|---|---|
| 1 | [acl_latex.tex:85](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:85) | `fig:pipeline` | 1 | 3 |
| 2 | [acl_latex.tex:118](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:118) | `app:diagnostics` | A | 11 |
| 3 | [acl_latex.tex:134](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:134) | `fig:mcts_failure` | 2 | 3 |
| 4 | [acl_latex.tex:134](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:134) | `tab:mcts_scc` | 1 | 3 |
| 5 | [acl_latex.tex:134](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:134) | `app:diagnostics` | A | 11 |
| 6 | [acl_latex.tex:201](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:201) | `app:priors` | F | 18 |
| 7 | [acl_latex.tex:201](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:201) | `eq:ucb` | 4 | 4 |
| 8 | [acl_latex.tex:209](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:209) | `sec:appendix_formula_details` | E | 17 |
| 9 | [acl_latex.tex:223](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:223) | `sec:appendix_formula_details` | E | 17 |
| 10 | [acl_latex.tex:223](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:223) | `eq:priority` | 7 | 4 |
| 11 | [acl_latex.tex:240](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:240) | `sec:component_tests` | 6.2 | 6 |
| 12 | [acl_latex.tex:250](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:250) | `eq:ucb` | 4 | 4 |
| 13 | [acl_latex.tex:255](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:255) | `eq:core` | 8 | 5 |
| 14 | [acl_latex.tex:273](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:273) | `app:budget_prefix` | J.2 | 20 |
| 15 | [acl_latex.tex:274](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:274) | `sec:cost_analysis` | 6.3 | 7 |
| 16 | [acl_latex.tex:281](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:281) | `sec:appendix_datasets` | I | 19 |
| 17 | [acl_latex.tex:314](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:314) | `sec:appendix_datasets` | I | 19 |
| 18 | [acl_latex.tex:318](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:318) | `sec:appendix_datasets` | I | 19 |
| 19 | [acl_latex.tex:318](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:318) | `app:revision_lea` | K.1 | 23 |
| 20 | [acl_latex.tex:336](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:336) | `fig:paired_case_outcomes` | 3 | 8 |
| 21 | [acl_latex.tex:352](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:352) | `tab:appendix_breakdowns` | 14 | 21 |
| 22 | [acl_latex.tex:353](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:353) | `sec:appendix_case` | C | 15 |
| 23 | [acl_latex.tex:355](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:355) | `app:size_breakdowns` | J.1 | 20 |
| 24 | [acl_latex.tex:368](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:368) | `app:budget_prefix` | J.2 | 20 |
| 25 | [acl_latex.tex:425](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:425) | `tab:mcts_scc` | 1 | 3 |
| 26 | [acl_latex.tex:430](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:430) | `tab:mcts_scc` | 1 | 3 |
| 27 | [acl_latex.tex:443](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:443) | `app:expert_extension` | B.2 | 12 |
| 28 | [acl_latex.tex:448](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:448) | `tab:expert_protocol` | 6 | 13 |
| 29 | [acl_latex.tex:469](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:469) | `tab:expert_audit_results` | 5 | 13 |
| 30 | [acl_latex.tex:534](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:534) | `tab:expert_example` | 7 | 14 |
| 31 | [acl_latex.tex:550](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:550) | `fig:case` | 4 | 16 |
| 32 | [acl_latex.tex:556](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:556) | `alg:appendix_scc_localized` | 2 | 16 |
| 33 | [acl_latex.tex:556](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:556) | `alg:appendix_dynamic_core` | 5 | 17 |
| 34 | [acl_latex.tex:556](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:556) | `alg:samcgs` | 1 | 5 |
| 35 | [acl_latex.tex:649](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:649) | `sec:method` | 3 | 2 |
| 36 | [acl_latex.tex:670](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:670) | `eq:relation-prior` | 5 | 4 |
| 37 | [acl_latex.tex:689](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:689) | `eq:priority` | 7 | 4 |
| 38 | [acl_latex.tex:692](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:692) | `eq:core` | 8 | 5 |
| 39 | [acl_latex.tex:707](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:707) | `eq:relation-prior` | 5 | 4 |
| 40 | [acl_latex.tex:716](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:716) | `eq:relation-prior` | 5 | 4 |
| 41 | [acl_latex.tex:725](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:725) | `eq:critical-pair` | 11 | 17 |
| 42 | [acl_latex.tex:741](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:741) | `tab:prior_coefficients` | 11 | 18 |
| 43 | [acl_latex.tex:776](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:776) | `app:revision_lea` | K.1 | 23 |
| 44 | [acl_latex.tex:791](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:791) | `tab:dataset_processing` | 12 | 20 |
| 45 | [acl_latex.tex:816](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:816) | `tab:injection_templates` | 13 | 20 |
| 46 | [acl_latex.tex:845](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:845) | `app:revision_lea` | K.1 | 23 |
| 47 | [acl_latex.tex:845](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:845) | `tab:appendix_breakdowns` | 14 | 21 |
| 48 | [acl_latex.tex:859](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:859) | `fig:main_metrics` | 5 | 21 |
| 49 | [acl_latex.tex:859](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:859) | `fig:absolute_size_breakdowns` | 6 | 22 |
| 50 | [acl_latex.tex:859](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:859) | `tab:appendix_breakdowns` | 14 | 21 |
| 51 | [acl_latex.tex:864](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:864) | `fig:absolute_size_breakdowns` | 6 | 22 |
| 52 | [acl_latex.tex:868](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:868) | `fig:absolute_size_breakdowns` | 6 | 22 |
| 53 | [acl_latex.tex:868](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:868) | `fig:main_metrics` | 5 | 21 |
| 54 | [acl_latex.tex:883](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:883) | `fig:convergence` | 7 | 22 |
| 55 | [acl_latex.tex:883](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:883) | `tab:matched_main` | 2 | 7 |
| 56 | [revision_baselines.tex:6](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_baselines.tex:6) | `app:revision_lea` | K.1 | 23 |
| 57 | [revision_main_results.tex:40](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_results.tex:40) | `tab:matched_main` | 2 | 7 |
| 58 | [revision_main_analysis.tex:5](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:5) | `tab:component_main` | 3 | 7 |
| 59 | [revision_main_analysis.tex:5](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:5) | `app:revision_stage1` | K.2 | 23 |
| 60 | [revision_main_analysis.tex:5](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:5) | `app:revision_stage2` | K.3 | 24 |
| 61 | [revision_main_analysis.tex:49](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:49) | `tab:cost_main` | 4 | 7 |
| 62 | [revision_main_analysis.tex:49](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:49) | `app:revision_cost` | K.4 | 24 |
| 63 | [revision_main_analysis.tex:51](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:51) | `app:revision_prior` | K.5 | 25 |
| 64 | [revision_expert_main.tex:5](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_main.tex:5) | `app:expert_extension` | B.2 | 12 |
| 65 | [revision_expert_main.tex:9](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_main.tex:9) | `app:expert_extension` | B.2 | 12 |
| 66 | [revision_expert_appendix.tex:39](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:39) | `tab:expert_new_agreement` | 8 | 14 |
| 67 | [revision_expert_appendix.tex:68](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:68) | `tab:expert_new_quality` | 9 | 15 |
| 68 | [revision_expert_appendix.tex:98](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:98) | `tab:expert_pre_negative` | 10 | 15 |
| 69 | [revision_experiments.tex:38](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:38) | `tab:revision_stage1` | 15 | 25 |
| 70 | [revision_experiments.tex:65](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:65) | `tab:revision_stage1_cost` | 16 | 25 |
| 71 | [revision_experiments.tex:85](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:85) | `tab:revision_stage1` | 15 | 25 |
| 72 | [revision_experiments.tex:108](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:108) | `tab:revision_stage2` | 17 | 25 |
| 73 | [revision_experiments.tex:108](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:108) | `tab:revision_stage1` | 15 | 25 |
| 74 | [revision_experiments.tex:113](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:113) | `tab:revision_cost_full` | 18 | 26 |
| 75 | [revision_experiments.tex:161](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:161) | `eq:revision_parallel_time` | 16 | 24 |
| 76 | [revision_experiments.tex:166](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:166) | `tab:prior_coefficients` | 11 | 18 |
| 77 | [revision_experiments.tex:186](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:186) | `tab:revision_prior` | 19 | 26 |

## 7. 可复核记录

- [逐条引用、标签和实际跳转检查](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/crossref_audit/final_crossref_checks.json)
- [全部源码改动](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/crossref_audit/changes.diff)
- [数据、公式、算法与图资产保留检查](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/crossref_audit/final_preservation_checks.json)
- [主文独立核对](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/crossref_audit/main/MAIN_CROSSREF_AUDIT_ZH.md)
- [附录独立核对](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/crossref_audit/appendix/REPORT.md)
- [最终附录位置与视觉检查](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/crossref_audit/appendix/FINAL_PLACEMENT_QA.md)
- [图表内容与资产逐项核对](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/crossref_audit/assets/ASSET_AUDIT_ZH.md)

子审计的初始清单保留修改前位置；本文件与 `final_crossref_checks.json` 为本轮最终结果。

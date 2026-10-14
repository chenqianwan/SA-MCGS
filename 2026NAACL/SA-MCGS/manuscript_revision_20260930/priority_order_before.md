# 论文篇幅调整清单：主文去重与附录迁移

日期：2026-09-30。**本轮仅执行已确认的 M2、M4；M1、M3、M6 暂缓，M5 不执行。C1–C14 尚未执行。**

调整前的净稿全文 25 页，结论在第 10 页，属于主文的 Figure 5 又浮动到了第 11 页。主文确实超页；不能只按结论位置计算，也不能把全文 25 页都算成主文。

M2、M4 落实后，[净稿](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex_clean.pdf)仍为 25 页；结论和最后一张主文图均在第 10 页，参考文献由第 11 页提前到第 10 页。领域合并表在附录第 21 页，预算图在附录第 23 页。**本轮已减少主文占用，但尚未达到 8 页。**

ARR 长文正文上限为 **8 页**；结论后的 Limitations、可选伦理声明和参考文献另计，主文图表仍计入正文篇幅。规则核对：[ARR Call for Papers](https://aclrollingreview.org/cfp)。本轮以净稿为验收对象，目标是主文及其全部图表在第 8 页内结束。

沿用[此前逐项修改清单](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20260922/CHANGE_LIST_ZH.md)的科学内容；本清单调整内容位置与重复叙述。以下 M／C 项中的图表编号、章节和行号均指**本轮调整前版本**，便于对照原建议；论文内编号已自动更新。

## 1. 按本轮决定，主文保留什么

主线：**问题与方法 → 五模型三方法比较 → 逐案例收益 → 组件、成本与专家证据。**

| 主文保留 | 用途 |
|---|---|
| Figure 1：框架图 | 解释完整方法。 |
| Figure 2：TreeMCTS 动机示意；Table 1：诊断表 | 按本轮决定保留在主文，M1 暂缓。 |
| Figure 3：SCC 规模分解 | 按本轮决定保留在主文，M3 暂缓。 |
| 当前 Figure 4：已选定的 D 配对结果图 | 展示改善发生在哪些案例；保留你已经选定的设计。 |
| 五模型 × 三方法主表（净稿现为 Table 2） | 保留全部 15 行及四项指标。 |
| 组件消融表（净稿现为 Table 3） | 同时保留正式 Stage-1 与 Stage-2 结果。 |
| 成本—效果表（净稿现为 Table 4） | 保留三方法成本、效果及该实验的样本范围。 |
| Algorithm 1；prior 与 OC 细节 | 高层伪代码继续留主文，M5 不执行；M6 暂缓。 |
| 专家审计简短正文 | 保留主要质量结果和原文负例发现，详细协议与完整表放附录。 |

目前主文保留 **4 张图、4 张表和 Algorithm 1**。原来的“2 图、3 表”是整体压缩建议，本轮不执行该配置。

## 2. 附录迁移建议与本轮决定

| 编号 | 本轮状态 |
|---|---|
| M1 | 暂缓，动机示意和诊断表保留主文。 |
| M2 | **已完成**：原领域表并入附录 I，净稿为 Table 12；原黑字在修订版保留删除线。 |
| M3 | 暂缓，规模分解图保留主文。 |
| M4 | **已完成**：预算图和完整数值移入附录 J.1，净稿为 Figure 6；正文保留一句过程观察和指引。 |
| M5 | 不执行，Algorithm 1 保留主文。 |
| M6 | 暂缓，prior／OC 细节保留主文。 |

原建议内容保留如下供后续对照，不代表其余项目已获执行确认：

| 编号 | 当前位置 | 具体调整 | 正文留下什么／附录落点 |
|---|---|---|---|
| M1 | §3.1；Figure 2；Table 1 | 将 TreeMCTS 动机示意、诊断表及 path-copy 展开细节集中移入附录。保留已经优化好的图，不删除资产。 | 正文保留一个短段解释循环中状态复制、预算分散及诊断观察；完整内容合入附录 A `app:diagnostics`，去掉与原附录重复的解释。 |
| M2 | §4.1；Table 2 | 将领域覆盖表与附录已有数据来源表合并，不再保留两张近似表。 | 正文保留四个领域及选择动机；合入附录 I `sec:appendix_datasets` 的 `tab:dataset_processing`，保全两表独有信息。 |
| M3 | Figure 3；§6.1 | 将五模型、两指标的 SCC 规模分解图及分组数值移入附录。 | 正文用一句概括 GPT-4o、Qwen2.5 在三个规模组的 Risk-all 收益；图与分解表放附录 J `sec:appendix_experiments`，新增 `app:size_breakdowns`。 |
| M4 | Figure 5；§6.2 | 将预算前缀曲线及逐预算数值移入附录。 | 正文保留一句过程观察及指引；附录 J 新增 `app:budget_prefix`，说明曲线来自已有轨迹的前缀重建。 |
| M5 | §3.6 后的 Algorithm 1 | 将高层伪代码移到附录算法部分开头，与已有四个详细算法形成总览—展开结构。 | 主文保留框架图、关键公式、步骤衔接及算法引用；附录 D `sec:appendix_algorithm` 承接。若最终主文有足够余量，优先考虑把总览伪代码放回。 |
| M6 | §3.3、§3.5：prior 特征与 OC 校准细节 | 将节点／边特征枚举、系数解释、校准展开与附录现有内容合并。 | 正文保留 prior 构造原则、必要公式和 OC 如何影响选点；详情放附录 E `sec:appendix_formula_details`、F `app:priors`。 |

定位：M1 `[主文件:126]`；M2 `[主文件:282]`；M3 `[主文件:324]`；M4 `[主文件:358]`；M5 `[主文件:240]`；M6 `[主文件:199、221]`。文件链接见第 5 节。

## 3. 按正文顺序删除重复、压缩叙述

**本节 C1–C14 均未执行，等待后续选择。**

| 编号 | 位置 | 对应修改 |
|---|---|---|
| C1 | Introduction：背景、方法概述、贡献列表 | 合并反复出现的“循环导致树搜索困难”。背景只留一个具体例子；方法概述与贡献列表不要各列一遍完整流水线。领域来源留到设置部分介绍。 |
| C2 | §2 Task Formulation 与 §4.3 | 图、root、witness 和输出在任务定义处讲清；注入过程与样本数量集中到设置部分。保留一处完整的 20 个源 SCC → 80 variants → 五模型 400 model-cases 说明，删去各处展开复述。 |
| C3 | §3.1 动机段 | 配合 M1，将“图展示什么”“表验证什么”“为什么会重复访问”的多段解释合成一个短段，直接引出方法。 |
| C4 | §3.4 Relation-first evidence memory | 删除段首与段末重复的关系证据直觉。保留 memory 更新规则、priority 公式，以及 max 聚合如何限制 degree bias。 |
| C5 | §3.5–3.6：OC 与 dynamic core | 每节保留定义、操作和作用各一层；删去再次阐述“关系证据重要、干扰节点应丢弃”的句子。core replacement 的具体机制留正文。 |
| C6 | §3.7 Computational feasibility | 压为一个短段，保留关键复杂度与固定预算。删去重复的 path-copy 对比；并发说明集中在成本节，详细推导合入附录 D／K.4。 |
| C7 | §4.2 Domain formatting | 不再逐域解释 record 格式；序列化展开移入附录 I。正文保留统一输入、共享风险语义和不泄露目标标签的关键设置。 |
| C8 | §4.4 Baselines and models | 保留三方法定义、LEA 与 SA 的关键区别及五模型完整引用。相同案例／协议只说明一次；压缩模型引出句与名单中重复的 proprietary／open-weight 分类。 |
| C9 | §5 主结果与 D 图解释 | 主表负责全部数值，正文集中说明总体提升及模型间表现，D 图段只解释配对收益。删除同一模型的前后分数、差值、SA-only／baseline-only／net 被连续报三遍的写法；保留有代表性的数值。 |
| C10 | §5.1、§6.1–6.3 | 将领域、规模、预算的简短结论合成一个紧凑的补充分析段，指向附录。删除只有预告作用的 “Robustness checks” 小节；案例指引并入相关段末。 |
| C11 | Component ablations | 保留正式 Stage-1 表及结果概括、Stage-2 同轨迹同容量比较。80-case 跨批次描述性结果的逐项数字集中到 K.2；主文保留 Stage-2 的 +37.5 pp、同 8.1 节点及置信区间。 |
| C12 | Inference cost and prior sensitivity | 成本段只解释额外开销及效果回报，不重报整张表。保留约 3.2× LEA tokens；完整分模型统计、恢复和并行时间解释放 K.4。prior 敏感性细节放 K.5，正文一处指引即可。 |
| C13 | Expert evidence | 正文保留新样本范围、盲审方式、主要证据质量结果和原文负例发现。标注分工、一致性、裁决及评分规则集中到现有 B.2 `app:expert_extension`，不在两处逐项展开。 |
| C14 | Related Work；Conclusion | Related Work 保留文献定位，删除再次定义 LEA 的协议段。结论压为约三句：任务贡献、主要结果、方法带来的证据组织价值；不再复述全部模块和实验列表。 |

压缩后的主文仍保留正式组件结果、计算代价和原文负例的简短结论；主要结果及统计口径沿用已确认版本。

## 4. 执行顺序与验收

1. **本轮完成**：执行 M2、M4，合并已有数据表、移动预算曲线，更新相关交叉引用。
2. **后续待选择**：M1／M3／M6 暂缓，M5 不执行；C1–C14 未执行，不自动扩大修改范围。
3. **整体篇幅目标**：下面的 7.7 页是原整体方案的参考预算，需结合保留图表的决定重新评估；本轮没有实现该目标。

| 内容块（含所属图表） | 目标页数 |
|---|---:|
| 标题、摘要、Introduction、Task Formulation | 1.7 |
| Method 与框架图 | 2.0 |
| Experimental Setup | 0.8 |
| Main Results、Analysis 与主表／D 图／消融／成本／专家结果 | 2.5 |
| Related Work、Conclusion | 0.7 |
| **合计** | **7.7** |

以下为整体目标及本轮检查状态：

- [ ] 主文、结论及全部主文图表在第 8 页内结束；没有主文浮动体落到 Limitations 或 References 区域。
- [x] Limitations 保留在结论之后；迁入附录的图表有清晰标题、范围及正文引用。
- [x] 五模型、三方法、15 行主表和已确认数值保持一致；迁移不改变实验与失败统计口径。
- [x] 本轮保留主文原有变量定义、关键公式及方法步骤。
- [x] 图表编号自动更新，相关标签唯一，交叉引用有效。
- [x] 新改写用绿色；原黑字按原约定软删除；迁移内容在净稿中只出现一次。
- [x] 本轮保持 ACL 模板字号、页边距与图表尺寸。

## 5. 执行文件

| 清单范围 | 源文件与主要定位 |
|---|---|
| M1–M6；C1–C7、C10、C14 | [主文件](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex)：Introduction 64；Task 104；Method 123；Setup 275；Analysis 351；Related Work 376；Conclusion 392；附录 A 406、D 539、E 631、F 684、I 760、J 810。 |
| C8 | [基线定义](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_baselines.tex:1)；模型段位于主文件 317。 |
| C9 | [主结果](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_results.tex:37)；配对图解释位于主文件 332。 |
| C11–C12 | [消融与成本正文](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:1)；[实验附录 K](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:35)。 |
| C13 | [专家正文](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_main.tex:5)；[专家附录 B.2](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:5)。 |

分页核查记录：[pagination.json](/Users/chenlong/WorkSpace/MCGS_Law/tmp/pdfs/page_budget_audit_20260930/pagination.json)。

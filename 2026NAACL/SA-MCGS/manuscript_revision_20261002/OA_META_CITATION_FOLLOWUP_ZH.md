# 对照 OA 与 Meta 的文献补充建议

日期：2026-10-02。**本清单七篇已全部实施，当前 References 为 54 条。** [实际加入位置与编译核验](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261002/citation_expansion_54/CITATION_EXPANSION_54_ZH.md)。以下保留本轮在 47 条版本基础上的选择理由与评审来源。

**本轮已补 7 篇：其中 5 篇来自评审明确点名的遗漏，另外 2 篇补足子图搜索和证据评价的研究定位。**

## 1. 原始意见依据

已读取[完整 OpenReview 原件](</Users/chenlong/Downloads/Risk Subgraph Extraction in Cyclic Document Graphs with Structure-Aware Monte Carlo Search _ OpenReview.pdf>)第 3–4 页的 Area Chair TxMU meta-review，以及三位 reviewer 的原始意见。没有把内部 OA3.5/Meta3.5 目标计划当作评审。

- **Meta 的自然风险建议**明确列出 CUAD、MAUD、ContractNLI、LEDGAR、CLAUDETTE/UNFAIR-ToS。CUAD、ContractNLI 已有引用，后三项缺原始来源。见[原文抽取第 205 行](/Users/chenlong/WorkSpace/MCGS_Law/tmp/pdfs/openreview.txt:205)。
- **wWUk 的图推理基线建议**点名 Dechtiar et al. (2025)、Chen et al. (2026)、de Martim (2025)。Dechtiar 已有；后两者缺失。见[review 第 22 行](/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/reviews/reviewer_wWUk.md:22)。Meta 本身没有点名后两篇。
- **iMEC**认为技术贡献偏向现有方法的集成，建议更清楚地分离图搜索／子图压缩的贡献；**rxvy**要求 subgraph precision／irrelevant-node rate，指出单靠压缩率不足以评价输出证据。这两点分别对应下表 SubgraphX 和 ERASER 的补充理由；两篇是本次核对提出的建议，并非评审指定。
- Meta 另要求成本、局部输出 schema 公平性和组件消融。这些问题主要由实验回答，文献的作用是说明研究定位和已有路线。

## 2. 建议补充的 7 篇

| 顺序 | 文献及正式出处 | 对应意见 | 建议位置及加入理由 |
|---|---|---|---|
| 1 | **LegalGraphRAG: Multi-Agent Graph Retrieval-Augmented Generation for Reliable Legal Reasoning**，Zerui Chen et al., ACL 2026。[ACL 原始来源](https://aclanthology.org/2026.acl-long.1738/) | wWUk 点名 Chen et al. (2026)，要求覆盖代表性法律图推理 | §7 图检索段。介绍层级法律图及检索—证据核验—裁决流程，再说明本文集中在 SCC 内风险端点和紧凑子图输出。它比增加一篇泛用 RAG 综述更贴近评审关切。 |
| 2 | **An Ontology-Driven Graph RAG for Legal Norms: A Hierarchical, Temporal, and Deterministic Approach**，Hudson de Martim, JURIX 2025。[出版方全文](https://journals.sagepub.com/doi/pdf/10.3233/FAIA251598) | wWUk 点名 de Martim (2025) | 与上一条合并一句，说明 SAT-Graph RAG 利用法律层级、版本与来源追踪做时间相关检索。补全法律图表示及确定性检索这条路线。 |
| 3 | **CLAUDETTE: an automated detector of potentially unfair clauses in online terms of service**，Lippi et al., Artificial Intelligence and Law 2019。[正式出版页](https://link.springer.com/article/10.1007/s10506-019-09243-2) | Meta 与 wWUk 明确提及 CLAUDETTE/UNFAIR-ToS | §7 法律任务背景。三篇数据集中最接近风险检测：以句子级潜在不公平检测为参照，交代本文研究跨记录关系风险与证据子图。 |
| 4 | **MAUD: An Expert-Annotated Legal NLP Dataset for Merger Agreement Understanding**，Wang et al., EMNLP 2023。[ACL 原始来源](https://aclanthology.org/2023.emnlp-main.1019/) | Meta 与 wWUk 点名 MAUD | 与 CUAD、ContractNLI 合并介绍专家标注合同理解和并购条款阅读理解，说明本文任务与这些现有标注的关系。 |
| 5 | **LEDGAR: A Large-Scale Multilabel Corpus for Text Classification of Legal Provisions in Contracts**，Tuggener et al., LREC 2020。[ACL 原始来源](https://aclanthology.org/2020.lrec-1.155/) | Meta 与 wWUk 点名 LEDGAR | 与 MAUD／CLAUDETTE 放在同一段，用于真实合同条款分类背景；不另写一段数据集综述。 |
| 6 | **On Explainability of Graph Neural Networks via Subgraph Explorations（SubgraphX）**，Yuan et al., ICML 2021。[PMLR 原始来源](https://proceedings.mlr.press/v139/yuan21c.html) | 对应 iMEC 的技术定位意见；本次提出 | §7 Monte Carlo search on graphs 或图证据段。该工作已经用 MCTS 搜索解释 GNN 预测的子图，并以 Shapley 值评价重要性。“MCTS＋子图选择”已有直接先例，值得明确引用，再落到本文的文档 SCC、在线关系证据和风险端点目标。 |
| 7 | **ERASER: A Benchmark to Evaluate Rationalized NLP Models**，DeYoung et al., ACL 2020。[ACL 原始来源](https://aclanthology.org/2020.acl-main.408/) | 对应 rxvy 的证据精度／无关节点意见；本次提出 | 优先放附录 B.2 Expert-reference scoring，与人类证据标注的一致性评价相连；正文专家分析如有合适位置可短引。为“输出是否保留有用证据”补充 NLP 评价脉络，避免只谈图的尺寸和端点命中。 |

## 3. 各类文献怎样发挥作用

**法律数据集三篇**应合并成一到两句，按任务组织：合同跨度／推断、并购条款理解、条款类别、不公平条款检测。它们说明现有真实法律材料和标签覆盖到哪里；没有提供本文所需的 SCC 冲突端点和修复子图标注。引用时不能把 MAUD／LEDGAR 写成本文已经运行过的自然风险实验。

**法律 GraphRAG 两篇**应与现有 GraphRAG、ToG-2、G-Retriever 接在一起，补足法律领域的专门路线。可交代各自的图结构和证据流程，再集中陈述 SA-MCGS 的具体目标；LEA 仍按本文的局部窗口聚合协议描述，不改称为完整复现这两个系统。

**SubgraphX**说明重要技术先例，有助于更准确地界定贡献。它解释已训练 GNN 的预测；本文搜索文档关系中的风险证据。应比较任务、状态、评价信号和输出目标，不作“以前没有图搜索”的笼统断言。

**ERASER**区分与人类依据的一致性和对模型预测的忠实性。本文现有专家 precision／recall 对应前者，不应因为引用 ERASER 就把这些指标改称为 faithfulness 或套用尚未执行的 sufficiency／comprehensiveness 实验。

上述是引用与论述调整；自然正例、外部系统对比等实验是否充分，仍应依据实际实验评价。

## 4. 可选但暂不列入本轮 7 篇

[Scaling LLM Test-Time Compute Optimally Can be More Effective than Scaling Parameters for Reasoning](https://proceedings.iclr.cc/paper_files/paper/2025/hash/1b623663fd9b874366f3ce019fdfdd44-Abstract-Conference.html)，Snell et al., ICLR 2025：与评审关心的推理成本／效果权衡有关，可放成本讨论。但研究主要围绕数学推理、搜索／修订和按难度分配预算；相较前七篇，它对当前稿件的增量较小。若之后加强 test-time compute 定位再加，届时为 55 篇；无需仅为整数目标加入。

## 5. 已核实的版本细节

- LegalGraphRAG 正式 DOI 为 `10.18653/v1/2026.acl-long.1738`，ACL 2026，37455–37484。其 2026 年 5 月预印本早于 7 月评审；作者、主题及作者回复草稿均支持将其高置信对应到 reviewer 的 Chen et al. (2026)。
- de Martim 正式 DOI 为 `10.3233/FAIA251598`。JURIX 版题名使用 **Hierarchical**；[arXiv 后期版本](https://arxiv.org/abs/2505.00039)使用 **Structural**。引用时应将正式题名与正式 DOI 配套，不混用。
- MAUD 为 **EMNLP 2023**，DOI `10.18653/v1/2023.emnlp-main.1019`；完整作者应按 PDF 首页，特别注意 Steven H. Wang／Dimitry Levkin 与元数据缩写或拼写差异。
- LEDGAR 为 **LREC 2020，1235–1241**；官方记录未给 DOI，使用 ACL URL。
- CLAUDETTE 引 **2019 正式期刊版**，27:117–139，DOI `10.1007/s10506-019-09243-2`，不与 2018 预印本年份拼接。
- SubgraphX 为 ICML 2021，PMLR 139:12241–12252；ERASER 为 ACL 2020，4443–4458，DOI `10.18653/v1/2020.acl-main.408`。

当前论文为 54 篇。七篇均已落地，沿用红色新增／原黑字软删除；两版 PDF 已重新编译，净稿正文仍在第 8 页内结束。可选的 Snell et al. 未纳入本轮。

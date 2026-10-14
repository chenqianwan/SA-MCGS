# 参考文献补充完成清单：41 → 47

更新：2026-10-02。已落实本轮确认的六篇文献，原有 41 篇全部保留。新增／改写文字及新进入 References 的书目标红，被替换的原黑字保留删除线。

## 1. 六篇文献、加入位置与作用

| 文献与核对来源 | 位置 | 本次加入的内容与作用 |
|---|---|---|
| [Language Agent Tree Search Unifies Reasoning, Acting, and Planning in Language Models](https://proceedings.mlr.press/v235/zhou24r.html)，Zhou et al., ICML 2024 | Introduction 搜索动机；§7 Search-augmented LLMs | 补足从经典 MCTS 到 LLM 搜索的衔接；介绍 LATS 的价值估计、反思及环境反馈。 |
| [ReKG-MCTS: Reinforcing LLM Reasoning on Knowledge Graphs via Training-Free Monte Carlo Tree Search](https://aclanthology.org/2025.findings-acl.484/)，Song et al., Findings of ACL 2025 | Introduction 搜索动机；§7 Monte Carlo search on graphs | 纳入知识图谱上的 LLM／MCTS 近邻工作，使搜索动机和方法定位更完整。 |
| [Monte Carlo Tree Search for Graph Reasoning in Large Language Model Agents](https://doi.org/10.1145/3746252.3760854)，Lihui Liu, CIKM 2025 | §7 Monte Carlo search on graphs | 与 ReKG-MCTS 一起说明外部图知识上的 MCTS 推理，避免把“使用外部图”本身作为区别。 |
| [From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://arxiv.org/abs/2404.16130v1)，Edge et al., 2024 | §7 Graph retrieval and evidence selection | 介绍实体图与社区摘要路线，补上图组织和文档汇总的相关背景。沿用已核实的 2024 v1 记录。 |
| [Think-on-Graph 2.0: Deep and Faithful Large Language Model Reasoning with Knowledge-guided Retrieval Augmented Generation](https://proceedings.iclr.cc/paper_files/paper/2025/hash/830b1abc6d2da85f23d41169fa44d185-Abstract-Conference.html)，Ma et al., ICLR 2025 | §7 Graph retrieval and evidence selection | 介绍知识图遍历与文档检索的结合，与本文 SCC 内关系证据累计及风险端点保留的任务目标对应。 |
| [G-Retriever: Retrieval-Augmented Generation for Textual Graph Understanding and Question Answering](https://proceedings.neurips.cc/paper_files/paper/2024/hash/efaf1c9726648c8ba363a5c927440529-Abstract-Conference.html)，He et al., NeurIPS 2024 | §7 Graph retrieval and evidence selection | 补充通过 prize-collecting Steiner tree 优化选择查询相关子图的近邻方法，明确本文最终输出紧凑风险子图的目标。 |

## 2. 正文实际改动

| 位置 | 改动 |
|---|---|
| Introduction 第三段开头 | 将单独的 AlphaGo-style search 引出句改为 MCTS 在游戏与 LLM 推理中的应用，接入 LATS、ReKG-MCTS。后续普通 MCTS、循环路径副本和 SCC 动机解释保持原样。 |
| §7 第一段 | 合并重复的长上下文／图推理背景；将原末段的法律网络分析和合同图抽取引用归入文档图背景。 |
| §7 第二段 | 保留 ToT／GoT／reasoning-as-planning，并加入 LATS 的具体搜索机制。 |
| §7 第三段 | 保留 transposition sharing 与 loop uncertainty；加入 ReKG-MCTS／Graph-MCTS。删除原来重复的 AlphaGo 背景和笼统的 remaining gap 表述。 |
| §7 第四段 | 改为图检索与证据选择，加入 GraphRAG／ToG-2／G-Retriever，并以 SCC 内关系证据积累和紧凑风险输出收束。校准机制及其两条引用仍完整保留在方法部分。 |

没有新增实验、调整结果、修改图表或压缩字体。Related Work 仍为四个段落。

## 3. 引用与编译核对

- 实际净稿 References：**47 条**；修订版同为 47 个正式条目，另显示已有书目删除痕迹。
- 原有 41 条引用全部保留；此次新增 5 条 BibTeX，启用 1 条已有 GraphRAG 记录。文献库共 54 条，未引用库存 7 条。
- 新记录的题名、完整作者顺序、年份、正式出处及可用 DOI／URL 均经核对。LATS、ToG-2 的官方条目未提供 DOI，未自行填入。
- Graph-MCTS 的算法概括依据出版商摘要；正式作者与卷页另以 Crossref 注册记录交叉核对。正文只写已核实的外部图知识推理范围。
- 净稿 **26 页，正文及结论仍在第 8 页内结束**；Limitations 从第 8 页开始，References 位于第 9–11 页。
- 修订版 33 页。新正文及新引文已检查红色标记；原黑字软删除正常。
- 77 处有效交叉引用全部解析成功；7 张图、19 张表和 5 个算法的标签有效，无损坏的内部链接或未定义引用。
- 净稿无 overfull 警告；修订版保留原有 Introduction 删除文字的一处 5.22 pt overfull，本轮未新增。实际新增位置及书目页已渲染检查。

## 4. 文件

- [净稿 PDF](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex_clean.pdf)
- [红字修订版 PDF](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.pdf)
- [主稿源文件](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:70)
- [参考文献库](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/custom.bib)
- [本次程序核验记录](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261002/citation_expansion_47/verification.json)
- [两版交叉引用核验](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261002/citation_expansion_47/final_crossref_checks.json)
- [搜索文献核验依据](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261002/citation_expansion_47/search_additions_verification.json)
- [图检索文献核验依据](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261002/citation_expansion_47/retrieval_verification.json)
- [本次源文件差异](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261002/citation_expansion_47/citation_expansion.patch)

本清单记录此次增补；此前 41 条参考文献的完整核对历史仍保留于 [全文引用核对报告](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/FULL_CITATION_AUDIT_ZH.md)。

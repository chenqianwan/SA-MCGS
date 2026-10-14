# OA / Meta 相关文献补充：54 条完成记录

日期：2026-10-02。按作者确认的七篇清单实施，正式 References 从 **47 条增至 54 条**，原 47 条全部保留。新增／改写文字和七篇新增书目均标红，原黑字软删除记录保留。

## 1. 实际加入位置与作用

| 文献 | 实际位置 | 加入方式与作用 |
|---|---|---|
| Chen et al., 2026，LegalGraphRAG | §7 Related Work，图检索段 | 介绍层级法律图、证据检索及核验，补入 wWUk 点名的法律图推理路线。 |
| de Martim, 2025，SAT-Graph RAG | §7，同上 | 与 LegalGraphRAG 合并介绍法律层级、时间版本和来源追踪，补入 wWUk 点名的另一条路线。 |
| Lippi et al., 2019，CLAUDETTE | §7，法律任务背景段 | 将潜在不公平条款检测纳入法律任务背景；回应 Meta / wWUk 点名的数据集出处。 |
| Wang et al., 2023，MAUD | §7，同上 | 与既有 CUAD、ContractNLI 连贯介绍并购协议理解。 |
| Tuggener et al., 2020，LEDGAR | §7，同上 | 补足合同条款分类背景；与其他数据集按任务合并说明。 |
| Yuan et al., 2021，SubgraphX | §7，Monte Carlo graph search 段 | 明确已有 MCTS 子图搜索用于解释 GNN 预测的先例，完善技术定位。 |
| DeYoung et al., 2020，ERASER | 附录 B.2，Expert-reference scoring | 说明现有专家指标衡量与标注证据的一致性，区分这一概念与预测忠实性。 |

前五篇对应评审明确点名的遗漏；后两篇由本轮核对提出，分别补充子图搜索和证据评价的学术背景。引用不改变实验定义，也不新增外部系统的实验结果。

## 2. 正式来源与元数据核验

| 文献 | 核实后的出版信息 | 来源 |
|---|---|---|
| LegalGraphRAG | ACL 2026，37455–37484；DOI 10.18653/v1/2026.acl-long.1738 | [ACL Anthology](https://aclanthology.org/2026.acl-long.1738/) |
| An Ontology-Driven Graph RAG for Legal Norms: A Hierarchical, Temporal, and Deterministic Approach | JURIX 2025，Legal Knowledge and Information Systems，282–287；DOI 10.3233/FAIA251598 | [出版方全文](https://journals.sagepub.com/doi/pdf/10.3233/FAIA251598) |
| CLAUDETTE | Artificial Intelligence and Law 27(2)，117–139，2019；DOI 10.1007/s10506-019-09243-2 | [正式出版页](https://link.springer.com/article/10.1007/s10506-019-09243-2) |
| MAUD | EMNLP 2023，16369–16382；DOI 10.18653/v1/2023.emnlp-main.1019 | [ACL Anthology](https://aclanthology.org/2023.emnlp-main.1019/) |
| LEDGAR | LREC 2020，1235–1241；官方未提供 DOI，保留正式 URL | [ACL Anthology](https://aclanthology.org/2020.lrec-1.155/) |
| SubgraphX | ICML 2021，PMLR 139，12241–12252；保留正式 URL | [PMLR](https://proceedings.mlr.press/v139/yuan21c.html) |
| ERASER | ACL 2020，4443–4458；DOI 10.18653/v1/2020.acl-main.408 | [ACL Anthology](https://aclanthology.org/2020.acl-main.408/) |

版本细节：de Martim 使用正式 JURIX 题名中的 Hierarchical，并按出版方 PDF 核实页码；MAUD 的 Steven H. Wang / Dimitry Levkin 和 LEDGAR 题名中的 Multilabel 按论文 PDF 首页记录。作者列表完整，未为没有官方 DOI 的条目编造 DOI。

## 3. 编译与版面核验

- 净稿 **27 页**；正文结论仍在 **第 8 页内结束**，Limitations 从第 9 页开始，References 位于第 9–11 页。
- 修订版 **34 页**，包括原黑字删除记录及彩色新增；新增七篇书目均标红。
- 两版均实际输出 **54 条参考文献**；原 47 条全部保留，无未解析 citation。
- **77 处交叉引用**全部可解析，覆盖 7 张图、19 张表和 5 个算法；已有编号全部不变，PDF 内部链接与目标页一致。
- 净稿无 overfull 警告；修订版只有原引言删除文字已有的 5.22 pt overfull，本轮未新增。
- 已逐页检查改动所在的相关工作、参考文献和专家评分页面，无新增遮挡或截断。
- 本轮主文件只改 §7 的三段新增文字；另在附录 B.2 加入 ERASER 说明。引言、结果数值、图表资产、公式和实验协议不变。

## 4. 文件与核验记录

- [主文相关工作](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:383)
- [专家参考评分](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:42)
- [BibTeX 文献库](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/custom.bib)
- [相对 47 条版本的源文件差异](SOURCE_CHANGES.patch)
- [自动核验记录](verification.json)与[交叉引用记录](final_crossref_checks.json)

文献库目前有 61 个条目，其中 54 个被当前论文引用；其余为既有未引用库存。正式文献数量以编译后的 References 为准。

# 2026 NAACL：LFP-MCGS

本目录用于第二篇论文项目：在有限、function-free、positive Horn 自然语言规则上研究 SCC 内的 least-fixed-point evidence recovery，并以 SA-MCGS 的图搜索骨架调度有限预算下的局部语义解析。

## 文档索引

- [`LFP_MCGS_RESEARCH_PLAN_ZH.md`](./LFP_MCGS_RESEARCH_PLAN_ZH.md)：完整研究方案、算法图、实验和八周计划。
- [`LFP_MCGS_LITERATURE_REVIEW.md`](./LFP_MCGS_LITERATURE_REVIEW.md)：MCGS × SCC × least-fixed-point 的新颖性检索与相关文献。
- [`LFP_MCGS_DATASET_ANALYSIS.md`](./LFP_MCGS_DATASET_ANALYSIS.md)：权威真实数据源、现有 SA-MCGS 数据复用和推荐数据方案。

## 当前范围

- 语义：least-Herbrand-model / least-fixed-point；
- 规则：finite、function-free、positive Horn；
- 输入：自然语言 facts / rules、candidate dependency graph 与 query；
- 输出：answer、query-relevant closure、source-linked proof certificate；
- MCGS 作用：选择下一处需要昂贵语义解析的文本窗口；
- deterministic LFP engine 作用：对已验证程序做 rule firing、closure 和 proof verification。

## 当前调研结论

- 未检索到把自然语言规则、SCC-aware MCGS、Datalog LFP closure 与可验证 proof recovery 同时结合的既有系统；但 cyclic MCGS、MCTS + SCC、SCC-wise Datalog evaluation 均已有工作，claim 必须限定在四者交集。
- 数据采用三层组合：RuleTaker / ProofWriter recursive-SCC diagnostic、Debian `botch` / `dose` 真实主数据，以及 Wikidata ontology violations 跨域外测。
- Paper 1 的 BGB / CUAD / SEC 数据可做真实文本与图迁移，但其 injected risk labels 不再承担 Paper 2 的主要量化结论。
- 正式方法名采用 **LFP-MCGS**；不使用容易被理解为 greatest fixed point 的 `GFP` 简称。

## 分支

项目分支：`2026NAACL`

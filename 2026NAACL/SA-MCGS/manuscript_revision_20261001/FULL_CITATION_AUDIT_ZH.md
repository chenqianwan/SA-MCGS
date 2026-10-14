# 全文参考文献核对：完整 citation list

**后续更新（2026-10-02）：**本报告记录原 41 条文献的审计。经作者确认，现已补入六篇相关文献，实际 References 为 **47 条**；新增位置、来源及最终编译结果见[47 条增补完成清单](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261002/citation_expansion_47/CITATION_EXPANSION_47_ZH.md)。下文 41 条审计结论作为原批次历史保留。

核对日期：2026-10-01；2026-10-02 追加提交前复核。对象为本轮修订后的实际净稿，而不只限于新加的模型引用。

**10 月 2 日补核：**RULER 已补为核实后的 COLM 2024 正式会议引文，保留论文实际署名的 8 位作者。两份 PDF 已重编译；净稿仍为 26 页，主文在第 8 页结束，41 条参考文献，无未定义引用或损坏内部链接。10 月 1 日 `final_verification.json` 为当时的存档；当前版本的校验记录见 `full_citation_audit/readiness_20261002/verification.json`。

**结论：原参考文献列表并非全部正确。当前正式列表的 41 条均已核对，其中 12 条存在需要修正的书目信息、作者记录或版本归属问题，17 条主要补齐可验证的出版字段／定位信息，12 条保留原条目。未发现整条凭空捏造的文献，但发现了错误作者、无效 DOI、错误会议归属和预印本／正式版信息拼接。已把确认的修正落实到稿件。**

另检查 `.bib` 中 8 条未引用条目：它们不进入当前论文参考文献表。本次修复了其中的作者记录、专著类型，并补全定位信息，没有为了保留它们而增加正文引用。

## 1. 优先看这些实际问题

| 文献 | 原问题 | 已落实 |
|---|---|---|
| Measuring Law Over Time | 作者名单混入 Boulet、Music，漏 Beckedorf，首作者错误 | 按出版商全文改为 Coupette、Beckedorf 等五人；正文作者—年份引用自动同步 |
| SARA：A Dataset for Statutory Reasoning… | 错标 ACL 出版；所填 ACL DOI 不存在 | 改为 CEUR Workshop Proceedings 2645，31–38 页，链接正式 PDF |
| The Second Type of Uncertainty in MCTS | 所填 IJCAI 2020 和 2388–2394 页不属于该文 | 恢复可核实的 arXiv:2005.09645 身份，不虚构正式会议 |
| Czech et al. 2021 | 将预印本标题拼接到 ICAPS 正式记录 | 正式标题改为 Improving AlphaZero Using Monte-Carlo Graph Search |
| Tree of Thoughts | NeurIPS 36 的年份误写为 2024 | 改为 2023；补齐正式卷页和 DOI |
| Battaglia / Silver 2016 / LegalBench | 手写 `and others` 被 ACL 样式计为一个作者，省略人数错误 | 分别存全 27／20／40 位作者，让官方样式自行截断 |
| 两条 Debian Policy 引文 | 作者字段填成书名；动态网页版本已偏离声明的 4.7.2.0 | 按该版本文档实际署名修改作者，固定到官方 4.7.2.0 Git 标签；保留 2025 |
| Berger–Shor 1990 | `10.5555/320176.320203` 经 DOI 与 Handle 查询均未注册 | 删除无效 DOI 字段，保留 ACM 目录 URL；不换成题名不同的 1997 期刊版 |
| Nemhauser et al. 1978 | 完整题名漏了结尾的 Part I | 补回 “—I”，其他书目字段保留 |

以上按条目计为 12 条；一个条目同时有多个问题仍只计一次。补页码或加链接不计为“错引”。完整作者由正式 PDF 和作者顺序核实，未机械照搬存在拆名、缩名或漏名的导出文件。

## 2. 两处引用语境的最小修正

### §3.6：经典次模保证与本文启发式实现

原句：

> Core compression is cast as budgeted subset selection, for which greedy selection is a standard approximation strategy under monotone submodular objectives with cardinality constraints.

改为：

> Classical greedy guarantees apply to monotone submodular objectives under cardinality constraints. We use greedy replacement as a heuristic for the relation-aware utility below.

保留 Nemhauser 引文。原文献确实证明了特定条件下的贪心近似界；但本文目标中的正向成对关系奖励具有互补性，不能直接继承该保证。例如，将 v 加入空集合和加入已有 u 的集合，后者多得到 ηm(u,v) 的边奖励，与次模边际递减相反。此次仅把引用范围写清楚，没有改公式、实现或结果。[原论文及其条件](https://link.springer.com/article/10.1007/BF01588971)。

### 附录 A：循环与 rollout 截断

把 “which is common in loops” 改为 “loops can prevent termination”，保留 Moerland 引文。论文 §4.2 直接讨论循环妨碍终止；原句对“常见”程度的概括没有必要。原黑字在修订版中软删除，新句标红。

## 3. 正式参考文献列表：41 条逐条总表

顺序遵循修正后净稿的 References；key 保留原名以避免无关改动，因此内部 `yao2024tree`／`boulet2021measuring` 不代表最终显示的年份／首作者。

| # | 文献 | 结论 | 处理与依据 |
|---|---|---|---|
| 1 | LongBench: A Bilingual, Multitask Benchmark for Long Context Understanding (2024) | 核心信息正确；已补全 | 补全或规范：DOI、页码、来源链接 [核对来源](https://aclanthology.org/2024.acl-long.172/) |
| 2 | Relational Inductive Biases, Deep Learning, and Graph Networks (2018) | 已修正 | 作者手工截断为10名加and others；实际27名，ACL模板会把others计为1名，造成“1 others”及作者遗漏。 [核对来源](https://arxiv.org/abs/1806.01261) |
| 3 | Approximation Algorithms for the Maximum Acyclic Subgraph Problem (1990) | 已修正 | 所填 DOI 不可解析：doi.org 返回404，Handle 注册查询 responseCode=100。不能把 ACM 目录标识当作已注册 DOI。 [核对来源](https://dl.acm.org/doi/10.5555/320176.320203) |
| 4 | Graph of Thoughts: Solving Elaborate Problems with Large Language Models (2024) | 核心信息正确；已补全 | 补全或规范：DOI、页码、来源链接 [核对来源](https://ojs.aaai.org/index.php/AAAI/article/view/29720) |
| 5 | A Survey of Monte Carlo Tree Search Methods (2012) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://repository.essex.ac.uk/4117/) |
| 6 | LexGLUE: A Benchmark Dataset for Legal Language Understanding in English (2022) | 核心信息正确；已补全 | 补全或规范：DOI、来源链接、题名 [核对来源](https://aclanthology.org/2022.acl-long.297/) |
| 7 | Progressive Strategies for Monte-Carlo Tree Search (2008) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://cris.maastrichtuniversity.nl/en/publications/progressive-strategies-for-monte-carlo-tree-search/) |
| 8 | Transpositions and Move Groups in Monte Carlo Tree Search (2008) | 核心信息正确；已补全 | 补全或规范：DOI [核对来源](https://ieeexplore.ieee.org/document/5035667/) |
| 9 | Measuring Law Over Time: A Network Analytical Framework with an Application to Statutes and Regulations in the United States and Germany (2021) | 已修正 | 原作者列表混入 Romain Boulet、Pierre Music，并漏掉实际第二作者 Janis Beckedorf；实际第一作者为 Corinna Coupette。；对应正文作者年引用应由 Boulet et al. (2021) 自动变为 Coupette et al. (2021)。 [核对来源](https://www.frontiersin.org/journals/physics/articles/10.3389/fphy.2021.658463/full) |
| 10 | Improving AlphaZero Using Monte-Carlo Graph Search (2021) | 已修正 | 混用了 arXiv 2020 预印本题名 Monte-Carlo Graph Search for AlphaZero 与 ICAPS 2021 卷页；正式 ICAPS 论文题名为 Improving AlphaZero Using Monte-Carlo Graph Search。 [核对来源](https://ojs.aaai.org/index.php/ICAPS/article/view/15952) |
| 11 | GRAPH-GRPO-LEX: Contract Graph Modeling and Reinforcement Learning with Group Relative Policy Optimization (2025) | 核心信息正确；已补全 | 补全或规范：DOI、来源链接 [核对来源](https://arxiv.org/abs/2511.06618) |
| 12 | A Fast and Effective Heuristic for the Feedback Arc Set Problem (1993) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://www.sciencedirect.com/science/article/pii/002001909390079O) |
| 13 | Talk Like a Graph: Encoding Graphs for Large Language Models (2024) | 核心信息正确；已补全 | 补全或规范：来源链接 [核对来源](https://proceedings.iclr.cc/paper_files/paper/2024/hash/bf72f65f30eedf5d48da6980ee02b589-Abstract-Conference.html) |
| 14 | Combining Online and Offline Knowledge in UCT (2007) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://dl.acm.org/doi/10.1145/1273496.1273531) |
| 15 | Gemini 2.5: Pushing the Frontier with Advanced Reasoning, Multimodality, Long Context, and Next Generation Agentic Capabilities (2025) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://arxiv.org/html/2507.06261v6) |
| 16 | Adaptive Conformal Inference Under Distribution Shift (2021) | 核心信息正确；已补全 | 补全或规范：来源链接、出版方 [核对来源](https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html) |
| 17 | LegalBench: A Collaboratively Built Benchmark for Measuring Legal Reasoning in Large Language Models (2023) | 已修正 | 仅写三名作者 + and others 导致 ACL 样式把剩余作者误计为 1；应记录全体 40 名作者。 [核对来源](https://proceedings.neurips.cc/paper_files/paper/2023/hash/89e44582fd28ddfea1ea4dcb0ebbf4b0-Abstract-Datasets_and_Benchmarks.html) |
| 18 | Reasoning with Language Model is Planning with World Model (2023) | 核心信息正确；已补全 | 补全或规范：DOI、来源链接 [核对来源](https://aclanthology.org/2023.emnlp-main.507/) |
| 19 | CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review (2021) | 核心信息正确；已补全 | 补全或规范：来源链接、卷号 [核对来源](https://datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/6ea9ab1baa0efb9e19094440c317e21b-Abstract-round1.html) |
| 20 | A Dataset for Statutory Reasoning in Tax Law Entailment and Question Answering (2020) | 已修正 | 原 publisher=Association for Computational Linguistics 错误，正式会议集是 CEUR Workshop Proceedings Vol.2645 的 NLLP@KDD 2020。；原 DOI 10.18653/v1/2020.nllp-1.4 不存在；doi.org 实测 HTTP 404，且不是该文的出版入口。 [核对来源](https://ceur-ws.org/Vol-2645/) |
| 21 | RULER: What's the Real Context Size of Your Long-Context Language Models? (2024) | 核心信息正确；已补全 | 10 月 2 日补为 COLM 2024 正式会议引文；作者按论文首页保留 8 人 [核对来源](https://colmweb.org/2024/AcceptedPapers.html) |
| 22 | A General Solution to the Graph History Interaction Problem (2004) | 核心信息正确；已补全 | 补全或规范：来源链接 [核对来源](https://s.aaai.org/Papers/AAAI/2004/AAAI04-102.pdf) |
| 23 | Bandit Based Monte-Carlo Planning (2006) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://link.springer.com/chapter/10.1007/11871842_29) |
| 24 | ContractNLI: A Dataset for Document-level Natural Language Inference for Contracts (2021) | 核心信息正确；已补全 | 补全或规范：来源链接 [核对来源](https://aclanthology.org/2021.findings-emnlp.164/) |
| 25 | Lost in the Middle: How Language Models Use Long Contexts (2024) | 核心信息正确；已补全 | 补全或规范：来源链接 [核对来源](https://aclanthology.org/2024.tacl-1.9/) |
| 26 | The Llama 3 Herd of Models (2024) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://arxiv.org/abs/2407.21783v3) |
| 27 | The Second Type of Uncertainty in Monte Carlo Tree Search (2020) | 已修正 | IJCAI 2020、2388–2394 不属于本篇。已核实来源为 arXiv:2005.09645（2020）；合著者出版列表仍标 Submitted/arXiv，不能称 IJCAI 已发表。 [核对来源](https://arxiv.org/abs/2005.09645) |
| 28 | An Analysis of Approximations for Maximizing Submodular Set Functions—I (1978) | 已修正 | 标题漏了末尾的 Part I（—I）。 [核对来源](https://link.springer.com/article/10.1007/BF01588971) |
| 29 | GPT-4o System Card (2024) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://cdn.openai.com/gpt-4o-system-card.pdf) |
| 30 | Qwen2.5 Technical Report (2024) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://arxiv.org/abs/2412.15115v1) |
| 31 | Qwen3.5-9B (2026) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md) |
| 32 | UCD: Upper Confidence Bound for Rooted Directed Acyclic Graphs (2012) | 核心信息正确；已补全 | 补全或规范：DOI [核对来源](https://www.sciencedirect.com/science/article/abs/pii/S0950705111002504) |
| 33 | Mastering the game of Go with deep neural networks and tree search (2016) | 已修正 | 作者仅存前 10 人及手工 others；该论文实际有 20 位作者，ACL 样式把占位符错误计作 1 others。 [核对来源](https://www.nature.com/articles/nature16961) |
| 34 | Depth-First Search and Linear Graph Algorithms (1972) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://epubs.siam.org/doi/10.1137/0201010) |
| 35 | Debian Policy Manual: Declaring relationships between packages (2025) | 已修正 | 原可变网页现在显示 v4.7.4.1，与参考文献声明的版本 4.7.2.0 不一致；固定到官方 Git 中的 debian/4.7.2.0 标签。；原作者 Debian Policy Manual 是书名；固定版本的 conf.py.in 明确 author/latex_documents 为 The Debian Policy Mailing List。 [核对来源](https://browse.dgit.debian.org/debian-policy.git/plain/policy/ch-relationships.rst?h=debian/4.7.2.0) |
| 36 | Debian Policy Manual: Shared libraries (2025) | 已修正 | 原可变网页现在显示 v4.7.4.1，与参考文献声明的版本 4.7.2.0 不一致；固定到官方 Git 中的 debian/4.7.2.0 标签。；原作者 Debian Policy Manual 是书名；固定版本的 conf.py.in 明确 author/latex_documents 为 The Debian Policy Mailing List。 [核对来源](https://browse.dgit.debian.org/debian-policy.git/plain/policy/ch-sharedlibs.rst?h=debian/4.7.2.0) |
| 37 | Algorithmic Learning in a Random World (2005) | 通过；保留 | 作者、标题、年、出处及标识相符。 [核对来源](https://link.springer.com/book/10.1007/b106715) |
| 38 | Can Language Models Solve Graph Problems in Natural Language? (2023) | 核心信息正确；已补全 | 补全或规范：文献类型、DOI、正式会议名称、页码、来源链接、出版方、卷号 [核对来源](https://proceedings.neurips.cc/paper_files/paper/2023/hash/622afc4edf2824a1b6aaf5afe153fa93-Abstract-Conference.html) |
| 39 | Chain-of-Thought Prompting Elicits Reasoning in Large Language Models (2022) | 核心信息正确；已补全 | 补全或规范：DOI、页码、来源链接、出版方 [核对来源](https://proceedings.neurips.cc/paper_files/paper/2022/hash/9d5609613524ecf4f15af0f7b31abca4-Abstract-Conference.html) |
| 40 | Tree of Thoughts: Deliberate Problem Solving with Large Language Models (2023) | 已修正 | 会议年份误写2024；NeurIPS36官方卷次/元数据/论文页脚均为2023。 [核对来源](https://proceedings.neurips.cc/paper_files/paper/2023/hash/271db9922b8d1f4dd7aaef84ed5ac703-Abstract-Conference.html) |
| 41 | Using Anytime Algorithms in Intelligent Systems (1996) | 核心信息正确；已补全 | 补全或规范：DOI [核对来源](https://ojs.aaai.org/aimagazine/index.php/aimagazine/article/view/1232) |

## 4. 逐条字段、正文用途和来源记录

每条均核对作者及顺序、完整题名、年份、发表类型／渠道、适用的卷期页码、DOI／URL，以及在当前正文中的用途。没有 DOI 的材料使用可验证的正式出处，不猜填标识。

### 01. LongBench: A Bilingual, Multitask Benchmark for Long Context Understanding

引用键：`bai2024longbench`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Yushi Bai and Xin Lv and Jiajie Zhang and Hongchang Lyu and Jiankai Tang and Zhidian Huang and Zhengxiao Du and Xiao Liu and Aohan Zeng and Lei Hou and Yuxiao Dong and Jie Tang and Juanzi Li |
| 年份／类型 | 2024；`inproceedings` |
| 会议 | Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers) |
| 出版方 | Association for Computational Linguistics |
| 页码／文章号 | 3119–3137 |
| DOI | 10.18653/v1/2024.acl-long.172 |
| 最终链接 | https://aclanthology.org/2024.acl-long.172/ |

**正文支持性：**支持Intro/Related Work长上下文理解不足及跨文档证据整合；包含21数据集6任务族并报告更长上下文困难。

**本次处理：**补全或规范：DOI、页码、来源链接

13名作者、题名、ACL2024卷册正确；补3119–3137页、DOI及ACL链接。

引用位置（审计开始时源文件行号）：`acl_latex.tex:67`、`acl_latex.tex:383`。

核对依据：[来源 1](https://aclanthology.org/2024.acl-long.172/)。

### 02. Relational Inductive Biases, Deep Learning, and Graph Networks

引用键：`battaglia2018relational`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Battaglia, Peter W. and Hamrick, Jessica B. and Bapst, Victor and Sanchez-Gonzalez, Alvaro and Zambaldi, Vinicius and Malinowski, Mateusz and Tacchetti, Andrea and Raposo, David and Santoro, Adam and Faulkner, Ryan and Gulcehre, Caglar and Song, Francis and Ballard, Andrew and Gilmer, Justin and Dahl, George and Vaswani, Ashish and Allen, Kelsey and Nash, Charles and Langston, Victoria and Dyer, Chris and Heess, Nicolas and Wierstra, Daan and Kohli, Pushmeet and Botvinick, Matt and Vinyals, Oriol and Li, Yujia and Pascanu, Razvan |
| 年份／类型 | 2018；`article` |
| 期刊／存档 | arXiv preprint arXiv:1806.01261 |
| DOI | 10.48550/arXiv.1806.01261 |
| 最终链接 | https://arxiv.org/abs/1806.01261 |

**正文支持性：**支持§3.4实体及关系层面的relational inductive bias这一设计动机；并非用该综述证明本稿memory公式的理论保证，当前表述可成立。

**本次处理：**作者手工截断为10名加and others；实际27名，ACL模板会把others计为1名，造成“1 others”及作者遗漏。

恢复arXiv列出的全部27名作者；原题名、2018及arXivID正确；补DOI与链接。

引用位置（审计开始时源文件行号）：`acl_latex.tex:205`。

核对依据：[来源 1](https://arxiv.org/abs/1806.01261)。

### 03. Approximation Algorithms for the Maximum Acyclic Subgraph Problem

引用键：`berger1990approximation`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Bonnie Berger and Peter W. Shor |
| 年份／类型 | 1990；`inproceedings` |
| 会议 | Proceedings of the First Annual ACM-SIAM Symposium on Discrete Algorithms |
| 出版方 | Society for Industrial and Applied Mathematics |
| 页码／文章号 | 236–243 |
| 最终链接 | https://dl.acm.org/citation.cfm?id=320176.320203 |

**正文支持性：**书目存在且最大无环子图主题与上下文匹配。ACM 原页面访问受限，未声称阅读全文；Eades 原文摘要明确说明 Berger–Shor 方法与反馈边的关系。 Shor 本人的 MIT 出版列表 Other Technical Papers #7 明确记录1990会议前身及页码；作者另一篇SIAM论文参考文献也给出完整题录。

**本次处理：**所填 DOI 不可解析：doi.org 返回404，Handle 注册查询 responseCode=100。不能把 ACM 目录标识当作已注册 DOI。

保留作者、题名、SODA1990及236–243页；以 ACM 目录 URL 定位，不再生成一个无效 doi.org 链接。ACM托管的会议目录可交叉核题录，但它是DBLP镜像，报告明确其性质。

引用位置（审计开始时源文件行号）：`acl_latex.tex:83`。

核对依据：[来源 1](https://dl.acm.org/doi/10.5555/320176.320203)、[来源 2](https://doi.org/10.5555/320176.320203)、[来源 3](https://hdl.handle.net/api/handles/10.5555/320176.320203)、[来源 4](https://sigmod.org/publications/dblp/db/conf/soda/soda90.html)、[来源 5](https://math.mit.edu/~shor/pubs.html)、[来源 6](https://epubs.siam.org/doi/10.1137/S0097539792240005)。

### 04. Graph of Thoughts: Solving Elaborate Problems with Large Language Models

引用键：`besta2024graph`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Maciej Besta and Nils Blach and Ales Kubicek and Robert Gerstenberger and Michal Podstawski and Lukas Gianinazzi and Joanna Gajda and Tomasz Lehmann and Hubert Niewiadomski and Piotr Nyczyk and Torsten Hoefler |
| 年份／类型 | 2024；`inproceedings` |
| 会议 | Proceedings of the AAAI Conference on Artificial Intelligence |
| 卷号 | 38 |
| 页码／文章号 | 17682–17690 |
| DOI | 10.1609/aaai.v38i16.29720 |
| 最终链接 | https://ojs.aaai.org/index.php/AAAI/article/view/29720 |

**正文支持性：**支持Related Work关于图式thought搜索/聚合可改善推理；原文图表示的是生成的思维，不是外部文档图，本稿紧接着明确此区别，语境适当。

**本次处理：**补全或规范：DOI、页码、来源链接

11名作者、题名、AAAI38及2024均正确；补16期、17682–17690页、DOI及链接。

引用位置（审计开始时源文件行号）：`acl_latex.tex:386`。

核对依据：[来源 1](https://ojs.aaai.org/index.php/AAAI/article/view/29720)、[来源 2](https://ojs.aaai.org/index.php/AAAI/article/download/29720/31236)。

### 05. A Survey of Monte Carlo Tree Search Methods

引用键：`browne2012survey`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Cameron B. Browne and Edward Powley and Daniel Whitehouse and Simon M. Lucas and Peter I. Cowling and Philipp Rohlfshagen and Stephen Tavener and Diego Perez and Spyridon Samothrakis and Simon Colton |
| 年份／类型 | 2012；`article` |
| 期刊／存档 | IEEE Transactions on Computational Intelligence and AI in Games |
| 卷号 | 4 |
| 期号 | 1 |
| 页码／文章号 | 1–43 |
| DOI | 10.1109/TCIAIG.2012.2186810 |

**正文支持性：**原文综述确认四阶段 MCTS 流程、UCT、progressive bias、AMAF/RAVE 等；现有作者形式与出版商登记一致，无须按 DBLP 的后期姓名扩写另改。

**本次处理：**作者、标题、年、出处及标识相符。

引用位置（审计开始时源文件行号）：`acl_latex.tex:70`、`acl_latex.tex:127`、`acl_latex.tex:201`、`acl_latex.tex:389`、`acl_latex.tex:741`。

核对依据：[来源 1](https://repository.essex.ac.uk/4117/)、[来源 2](https://repository.essex.ac.uk/4117/1/MCTS-Survey.pdf)、[来源 3](https://api.crossref.org/works/10.1109/TCIAIG.2012.2186810)。

### 06. LexGLUE: A Benchmark Dataset for Legal Language Understanding in English

引用键：`chalkidis2022lexglue`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Ilias Chalkidis and Abhik Jana and Dirk Hartung and Michael Bommarito and Ion Androutsopoulos and Daniel Martin Katz and Nikolaos Aletras |
| 年份／类型 | 2022；`inproceedings` |
| 会议 | Proceedings of the 60th Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers) |
| 出版方 | Association for Computational Linguistics |
| 页码／文章号 | 4310–4330 |
| DOI | 10.18653/v1/2022.acl-long.297 |
| 最终链接 | https://aclanthology.org/2022.acl-long.297/ |

**正文支持性：**支持 Related Work 法律语言理解/文档推理基准的概述；本文未据此宣称它是循环图风险子图基准。

**本次处理：**补全或规范：DOI、来源链接、题名

补 DOI 和 URL；保留 Daniel Martin Katz：论文 PDF 首页包含 Martin，网站导出省略它，不应据导出删改。

引用位置（审计开始时源文件行号）：`acl_latex.tex:383`。

核对依据：[来源 1](https://aclanthology.org/2022.acl-long.297/)、[来源 2](https://aclanthology.org/2022.acl-long.297.pdf)。

### 07. Progressive Strategies for Monte-Carlo Tree Search

引用键：`chaslot2008progressive`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Guillaume M. J.-B. Chaslot and Mark H. M. Winands and H. Jaap van den Herik and Jos W. H. M. Uiterwijk and Bruno Bouzy |
| 年份／类型 | 2008；`article` |
| 期刊／存档 | New Mathematics and Natural Computation |
| 卷号 | 4 |
| 期号 | 3 |
| 页码／文章号 | 343–357 |
| DOI | 10.1142/S1793005708001094 |

**正文支持性：**原文 Section 3.1 为 progressive bias，访问增多后启发式影响衰减，与正文类比吻合。期刊出版年 2008 正确；2011 是网上上线日期，不应改年份。5 作者顺序与期刊稿一致，不能采用 2007 同题会议版的作者顺序。

**本次处理：**作者、标题、年、出处及标识相符。

引用位置（审计开始时源文件行号）：`acl_latex.tex:201`、`acl_latex.tex:741`。

核对依据：[来源 1](https://cris.maastrichtuniversity.nl/en/publications/progressive-strategies-for-monte-carlo-tree-search/)、[来源 2](https://project.dke.maastrichtuniversity.nl/games/files/articles/pMCTS.pdf)、[来源 3](https://api.crossref.org/works/10.1142/S1793005708001094)。

### 08. Transpositions and Move Groups in Monte Carlo Tree Search

引用键：`childs2008transpositions`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Benjamin E. Childs and James H. Brodeur and Levente Kocsis |
| 年份／类型 | 2008；`inproceedings` |
| 会议 | 2008 IEEE Symposium On Computational Intelligence and Games |
| 出版方 | IEEE |
| 页码／文章号 | 389–395 |
| DOI | 10.1109/CIG.2008.5035667 |

**正文支持性：**论文原文第一页直接讨论 transpositions、cycles 和一个状态在同次模拟中多次出现，支持本文重复状态/图统计复用相关论述。IEEE 当前网页机器人拦截，但出版商登记和原论文可核。

**本次处理：**补全或规范：DOI

补 DOI 10.1109/CIG.2008.5035667。

引用位置（审计开始时源文件行号）：`acl_latex.tex:73`、`acl_latex.tex:127`、`acl_latex.tex:389`、`acl_latex.tex:741`。

核对依据：[来源 1](https://ieeexplore.ieee.org/document/5035667/)、[来源 2](https://api.crossref.org/works/10.1109/CIG.2008.5035667)、[来源 3](https://citeseerx.ist.psu.edu/document?doi=e7443565e965aae469d993e2fad6d0b202266213&repid=rep1&type=pdf)。

### 09. Measuring Law Over Time: A Network Analytical Framework with an Application to Statutes and Regulations in the United States and Germany

引用键：`boulet2021measuring`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Corinna Coupette and Janis Beckedorf and Dirk Hartung and Michael Bommarito and Daniel Martin Katz |
| 年份／类型 | 2021；`article` |
| 期刊／存档 | Frontiers in Physics |
| 卷号 | 9 |
| 页码／文章号 | 658463 |
| DOI | 10.3389/fphy.2021.658463 |
| 最终链接 | https://www.frontiersin.org/journals/physics/articles/10.3389/fphy.2021.658463/full |

**正文支持性：**原文 §2.1–2.2 将法规和法条建模为带 hierarchy/sequence/reference 的网络，并明确研究跨文档引用；支持正文 statutory cross-references/network analysis 的论述。

**本次处理：**原作者列表混入 Romain Boulet、Pierre Music，并漏掉实际第二作者 Janis Beckedorf；实际第一作者为 Corinna Coupette。；对应正文作者年引用应由 Boulet et al. (2021) 自动变为 Coupette et al. (2021)。

保留内部 key 避免无关重命名；标题、年、期刊、卷、文章号和 DOI 原来正确。

引用位置（审计开始时源文件行号）：`acl_latex.tex:65`、`acl_latex.tex:392`。

核对依据：[来源 1](https://www.frontiersin.org/journals/physics/articles/10.3389/fphy.2021.658463/full)、[来源 2](https://pure.mpg.de/view/item_3330143_2)。

### 10. Improving AlphaZero Using Monte-Carlo Graph Search

引用键：`czech2021monte`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Johannes Czech and Patrick Korus and Kristian Kersting |
| 年份／类型 | 2021；`inproceedings` |
| 会议 | Proceedings of the International Conference on Automated Planning and Scheduling |
| 卷号 | 31 |
| 页码／文章号 | 103–111 |
| DOI | 10.1609/icaps.v31i1.15952 |

**正文支持性：**正式论文摘要明确将树推广为 directed acyclic graph，使不同子树共享信息，正文关于 acyclic search graph/transposition sharing 的表述得到直接支持。

**本次处理：**混用了 arXiv 2020 预印本题名 Monte-Carlo Graph Search for AlphaZero 与 ICAPS 2021 卷页；正式 ICAPS 论文题名为 Improving AlphaZero Using Monte-Carlo Graph Search。

补 DOI 10.1609/icaps.v31i1.15952。

引用位置（审计开始时源文件行号）：`acl_latex.tex:83`、`acl_latex.tex:201`、`acl_latex.tex:389`、`acl_latex.tex:741`。

核对依据：[来源 1](https://ojs.aaai.org/index.php/ICAPS/article/view/15952)、[来源 2](https://ojs.aaai.org/index.php/ICAPS/article/download/15952/15763/19445)、[来源 3](https://arxiv.org/abs/2012.11045)。

### 11. GRAPH-GRPO-LEX: Contract Graph Modeling and Reinforcement Learning with Group Relative Policy Optimization

引用键：`dechtiar2025graphgrpolex`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Moriya Dechtiar and Daniel Martin Katz and Mari Sundaresan and Sylvain Jaume and Hongming Wang |
| 年份／类型 | 2025；`article` |
| 期刊／存档 | arXiv preprint arXiv:2511.06618 |
| DOI | 10.48550/arXiv.2511.06618 |
| 最终链接 | https://arxiv.org/abs/2511.06618v1 |

**正文支持性：**摘要明确提出将合同转换为语义图、抽取实体/关系和显隐式条款依赖。支持正文 contract graph extraction is active，未用于声称 SA-MCGS 的性能或证据保持保证。

**本次处理：**补全或规范：DOI、来源链接

补 arXiv 官方 DOI 和版本化链接；原有五名作者、标题和年份均准确；该条保持预印本身份，不伪造会议发表。

引用位置（审计开始时源文件行号）：`acl_latex.tex:392`。

核对依据：[来源 1](https://arxiv.org/abs/2511.06618)。

### 12. A Fast and Effective Heuristic for the Feedback Arc Set Problem

引用键：`eades1993fast`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Peter Eades and Xuemin Lin and W. F. Smyth |
| 年份／类型 | 1993；`article` |
| 期刊／存档 | Information Processing Letters |
| 卷号 | 47 |
| 期号 | 6 |
| 页码／文章号 | 319–323 |
| DOI | 10.1016/0020-0190(93)90079-O |

**正文支持性：**摘要直接定义反转反馈边获得无环图，支持正文删除/重定向反馈边的对比；本文对风险证据损失的分析是自身动机而非归给该文的实验结论。

**本次处理：**作者、标题、年、出处及标识相符。

三作者、47(6)、319–323、1993、DOI 与出版商页面和登记一致。

引用位置（审计开始时源文件行号）：`acl_latex.tex:83`。

核对依据：[来源 1](https://www.sciencedirect.com/science/article/pii/002001909390079O)。

### 13. Talk Like a Graph: Encoding Graphs for Large Language Models

引用键：`fatemi2024talk`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Bahare Fatemi and Jonathan Halcrow and Bryan Perozzi |
| 年份／类型 | 2024；`inproceedings` |
| 会议 | The Twelfth International Conference on Learning Representations |
| 最终链接 | https://proceedings.iclr.cc/paper_files/paper/2024/hash/bf72f65f30eedf5d48da6980ee02b589-Abstract-Conference.html |

**正文支持性：**直接支持Related Work graph encoding/task formulation敏感性；原文比较编码方法、任务、图结构三层因素。

**本次处理：**补全或规范：来源链接

3名作者、题名、ICLR2024正确；通过ICLR官方proceedings核实，补官方链接（OpenReview有访问验证）。

引用位置（审计开始时源文件行号）：`acl_latex.tex:383`。

核对依据：[来源 1](https://proceedings.iclr.cc/paper_files/paper/2024/hash/bf72f65f30eedf5d48da6980ee02b589-Abstract-Conference.html)。

### 14. Combining Online and Offline Knowledge in UCT

引用键：`gelly2007combining`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Sylvain Gelly and David Silver |
| 年份／类型 | 2007；`inproceedings` |
| 会议 | Proceedings of the 24th International Conference on Machine Learning |
| 出版方 | ACM |
| 页码／文章号 | 273–280 |
| DOI | 10.1145/1273496.1273531 |

**正文支持性：**作者原文介绍快速在线动作价值估计与离线先验用于 UCT，支持正文 RAVE-style reuse 的类比。ACM HTML 受限，但作者原文在浏览索引中可读并与出版商元数据交叉核实。

**本次处理：**作者、标题、年、出处及标识相符。

引用位置（审计开始时源文件行号）：`acl_latex.tex:201`、`acl_latex.tex:741`。

核对依据：[来源 1](https://dl.acm.org/doi/10.1145/1273496.1273531)、[来源 2](https://www.davidsilver.uk/wp-content/uploads/2020/03/combining_uct.pdf)、[来源 3](https://api.crossref.org/works/10.1145/1273496.1273531)。

### 15. Gemini 2.5: Pushing the Frontier with Advanced Reasoning, Multimodality, Long Context, and Next Generation Agentic Capabilities

引用键：`comanici2025gemini25`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Gemini Team |
| 年份／类型 | 2025；`article` |
| 期刊／存档 | arXiv preprint arXiv:2507.06261 |
| DOI | 10.48550/arXiv.2507.06261 |
| 最终链接 | https://arxiv.org/abs/2507.06261v6 |

**正文支持性：**支持§4.4模型身份和出处，不用于证明本文实验收益。

**本次处理：**作者、标题、年、出处及标识相符。

Gemini Team 首页团体署名；§3.1 Table2 对应 Gemini2.5Pro。 复用同日已完成的逐项审计和存档证据，并确认条目此后未改；本轮无需再次修改。

引用位置（审计开始时源文件行号）：`acl_latex.tex:325`。

核对依据：[来源 1](https://arxiv.org/html/2507.06261v6)。

### 16. Adaptive Conformal Inference Under Distribution Shift

引用键：`gibbs2021adaptive`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Isaac Gibbs and Emmanuel Candès |
| 年份／类型 | 2021；`inproceedings` |
| 会议 | Advances in Neural Information Processing Systems |
| 出版方 | Curran Associates, Inc. |
| 卷号 | 34 |
| 页码／文章号 | 1660–1672 |
| 最终链接 | https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html |

**正文支持性：**支持在线分布变化下自适应校准的动机。本文明确只取 calibration-inspired signal，不声称继承覆盖保证；适配。

**本次处理：**补全或规范：来源链接、出版方

官方 BibTeX 核对两作者、2021、NeurIPS 34、1660–1672；保留 Candès 的重音。

引用位置（审计开始时源文件行号）：`acl_latex.tex:223`、`acl_latex.tex:392`。

核对依据：[来源 1](https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html)。

### 17. LegalBench: A Collaboratively Built Benchmark for Measuring Legal Reasoning in Large Language Models

引用键：`guha2023legalbench`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Neel Guha and Julian Nyarko and Daniel E. Ho and Christopher Ré and Adam Chilton and Aditya Narayana and Alex Chohlas-Wood and Austin Peters and Brandon Waldon and Daniel N. Rockmore and Diego Zambrano and Dmitry Talisman and Enam Hoque and Faiz Surani and Frank Fagan and Galit Sarfaty and Gregory M. Dickinson and Haggai Porat and Jason Hegland and Jessica Wu and Joe Nudell and Joel Niklaus and John Nay and Jonathan H. Choi and Kevin Tobia and Margaret Hagan and Megan Ma and Michael Livermore and Nikon Rasumov-Rahe and Nils Holzenberger and Noam Kolt and Peter Henderson and Sean Rehaag and Sharad Goel and Shang Gao and Spencer Williams and Sunny Gandhi and Tom Zur and Varun Iyer and Zehua Li |
| 年份／类型 | 2023；`inproceedings` |
| 会议 | Advances in Neural Information Processing Systems |
| 出版方 | Curran Associates, Inc. |
| 卷号 | 36 |
| 页码／文章号 | 44123–44279 |
| DOI | 10.52202/075280-1915 |
| 最终链接 | https://proceedings.neurips.cc/paper_files/paper/2023/hash/89e44582fd28ddfea1ea4dcb0ebbf4b0-Abstract-Datasets_and_Benchmarks.html |

**正文支持性：**支持法律推理 benchmark 概述：162 个任务、六类法律推理。正文无归给该文的具体实验数值或循环图专属结论。

**本次处理：**仅写三名作者 + and others 导致 ACL 样式把剩余作者误计为 1；应记录全体 40 名作者。

用已正式发表的 NeurIPS 2023 Datasets and Benchmarks 版本代替同年 arXiv；补卷号、正式页码、DOI/URL。 完整作者按正式 PDF 首页核对，不能机械复制官方 BibTeX 的 Aditya K；PDF 署名为 Aditya Narayana。同理保留 Daniel E. Ho、Daniel N. Rockmore、Gregory M. Dickinson、Jonathan H. Choi 的中间字母。

引用位置（审计开始时源文件行号）：`acl_latex.tex:383`。

核对依据：[来源 1](https://proceedings.neurips.cc/paper_files/paper/2023/hash/89e44582fd28ddfea1ea4dcb0ebbf4b0-Abstract-Datasets_and_Benchmarks.html)、[来源 2](https://proceedings.neurips.cc/paper_files/paper/2023/file/89e44582fd28ddfea1ea4dcb0ebbf4b0-Paper-Datasets_and_Benchmarks.pdf)、[来源 3](https://proceedings.neurips.cc/paper_files/paper/19664-/bibtex)。

### 18. Reasoning with Language Model is Planning with World Model

引用键：`hao2023reasoning`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Shibo Hao and Yi Gu and Haodi Ma and Joshua Jiahua Hong and Zhen Wang and Daisy Zhe Wang and Zhiting Hu |
| 年份／类型 | 2023；`inproceedings` |
| 会议 | Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing |
| 出版方 | Association for Computational Linguistics |
| 页码／文章号 | 8154–8173 |
| DOI | 10.18653/v1/2023.emnlp-main.507 |
| 最终链接 | https://aclanthology.org/2023.emnlp-main.507/ |

**正文支持性：**支持Related Work关于规划式LLM搜索；原文RAP以LLM作为world model并结合MCTS，测试规划、数学、逻辑任务。

**本次处理：**补全或规范：DOI、来源链接

7名作者/题名/EMNLP2023/8154–8173页正确；补DOI及链接。ACL网页导出缩写Joshua Hong/Daisy Wang，而最终PDF首页明确Joshua Jiahua Hong/Daisy Zhe Wang，现有全名正确，不误改。

引用位置（审计开始时源文件行号）：`acl_latex.tex:386`。

核对依据：[来源 1](https://aclanthology.org/2023.emnlp-main.507/)、[来源 2](https://aclanthology.org/2023.emnlp-main.507.pdf)。

### 19. CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review

引用键：`hendrycks2021cuad`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Dan Hendrycks and Collin Burns and Anya Chen and Spencer Ball |
| 年份／类型 | 2021；`inproceedings` |
| 会议 | Proceedings of the Neural Information Processing Systems Track on Datasets and Benchmarks |
| 卷号 | 1 |
| 最终链接 | https://datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/6ea9ab1baa0efb9e19094440c317e21b-Abstract-round1.html |

**正文支持性：**支持法律合同审查背景及 Related Work 的法律 NLP 基准概述。它本身是合同条款标注/提取数据集，不是本文循环图方法的证据；正文开场的 graph problems 是本文的问题建模，与同时引用的法条网络研究共同提供动机。

**本次处理：**补全或规范：来源链接、卷号

补官方卷号 1 和永久论文页面；官方 BibTeX pages 为空，不猜造页码/DOI。

引用位置（审计开始时源文件行号）：`acl_latex.tex:65`、`acl_latex.tex:383`。

核对依据：[来源 1](https://datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/6ea9ab1baa0efb9e19094440c317e21b-Abstract-round1.html)。

### 20. A Dataset for Statutory Reasoning in Tax Law Entailment and Question Answering

引用键：`holzenberger2020sara`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Nils Holzenberger and Andrew Blair-Stanek and Benjamin Van Durme |
| 年份／类型 | 2020；`inproceedings` |
| 会议 | Proceedings of the Natural Legal Language Processing Workshop 2020 |
| 出版方 | CEUR-WS.org |
| 系列 | CEUR Workshop Proceedings |
| 卷号 | 2645 |
| 页码／文章号 | 31–38 |
| 最终链接 | https://ceur-ws.org/Vol-2645/paper5.pdf |

**正文支持性：**支持法条交叉引用与例外条件的动机。原文 §2.2 明确分别讨论 Exceptions and substitutions、Cross-references，并给出同节和跨节、显式和隐式引用数量。无需修改当前正文论述。

**本次处理：**原 publisher=Association for Computational Linguistics 错误，正式会议集是 CEUR Workshop Proceedings Vol.2645 的 NLLP@KDD 2020。；原 DOI 10.18653/v1/2020.nllp-1.4 不存在；doi.org 实测 HTTP 404，且不是该文的出版入口。

保留正确的作者、标题、2020 年和页码 31–38；补 CEUR 卷号/系列/正式 PDF URL。

引用位置（审计开始时源文件行号）：`acl_latex.tex:65`。

核对依据：[来源 1](https://ceur-ws.org/Vol-2645/)、[来源 2](https://ceur-ws.org/Vol-2645/paper5.pdf)、[来源 3](https://nlp.jhu.edu/law/sara/)。

### 21. RULER: What's the Real Context Size of Your Long-Context Language Models?

引用键：`hsieh2024ruler`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Cheng-Ping Hsieh and Simeng Sun and Samuel Kriman and Shantanu Acharya and Dima Rekesh and Fei Jia and Yang Zhang and Boris Ginsburg |
| 年份／类型 | 2024；`inproceedings` |
| 会议 | First Conference on Language Modeling |
| 最终链接 | https://openreview.net/forum?id=kIoBbc76Sy |

**正文支持性：**直接支持Intro及Related Work的retrieval/multi-hop tracing/aggregation局限；原文明确扩展NIAH到后两任务且性能随长度下降。

**本次处理：**10 月 2 日补齐正式发表身份和 OpenReview 链接；不猜填页码或会议 DOI。

原 arXiv 引文真实有效。10 月 2 日已用 COLM 2024 官方录用列表确认正式会议身份及 OpenReview ID kIoBbc76Sy，按 ARR 对已正式发表版本的引用要求补齐出处。会议网页作者列表漏 Yang Zhang，而正式 PDF 的搜索索引首页、arXiv v3 原文及作者 NVIDIA 仓库均为 8 人；因此保留论文的完整署名。OpenReview 直接访问及 API 仍遇验证／403，本次没有声称读取成功。

引用位置（审计开始时源文件行号）：`acl_latex.tex:67`、`acl_latex.tex:383`。

核对依据：[COLM 官方录用列表](https://colmweb.org/2024/AcceptedPapers.html)、[正式论文入口](https://openreview.net/forum?id=kIoBbc76Sy)、[正式 PDF 的索引来源](https://openreview.net/pdf?id=kIoBbc76Sy)、[arXiv v3](https://arxiv.org/abs/2404.06654v3)、[作者仓库](https://github.com/NVIDIA/RULER)。

### 22. A General Solution to the Graph History Interaction Problem

引用键：`kishimoto2004general`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Akihiro Kishimoto and Martin Müller |
| 年份／类型 | 2004；`inproceedings` |
| 会议 | Proceedings of the Nineteenth National Conference on Artificial Intelligence |
| 页码／文章号 | 644–649 |
| 最终链接 | https://s.aaai.org/Papers/AAAI/2004/AAAI04-102.pdf |

**正文支持性：**原文直接讨论在含环状态空间使用 transposition table 时的路径历史依赖及错误；现有正文将其列作 graph-history 问题来源，适合。AAAI 网页目录抬头误写 Eighteenth，但作者正式出版列表确认 Nineteenth/AAAI 2004，当前 booktitle 不需改。

**本次处理：**补全或规范：来源链接

补 AAAI 原文稳定 URL。

引用位置（审计开始时源文件行号）：`acl_latex.tex:73`。

核对依据：[来源 1](https://s.aaai.org/Papers/AAAI/2004/AAAI04-102.pdf)、[来源 2](https://webdocs.cs.ualberta.ca/~mmueller/ghi.html)。

### 23. Bandit Based Monte-Carlo Planning

引用键：`kocsis2006bandit`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Levente Kocsis and Csaba Szepesvári |
| 年份／类型 | 2006；`inproceedings` |
| 会议 | Machine Learning: ECML 2006 |
| 出版方 | Springer |
| 系列 | LNCS |
| 卷号 | 4212 |
| 页码／文章号 | 282–293 |
| DOI | 10.1007/11871842_29 |

**正文支持性：**正式 ECML 2006 论文提出 UCT 并在有限时域/折扣 MDP 下给出一致性和有限样本结果；正文仅以 UCB intuition/UCT-style selection 引用，未将其理论保证直接转给本文新策略，使用恰当。

**本次处理：**作者、标题、年、出处及标识相符。

引用位置（审计开始时源文件行号）：`acl_latex.tex:70`、`acl_latex.tex:183`、`acl_latex.tex:389`、`acl_latex.tex:436`、`acl_latex.tex:741`。

核对依据：[来源 1](https://link.springer.com/chapter/10.1007/11871842_29)、[来源 2](https://api.crossref.org/works/10.1007/11871842_29)。

### 24. ContractNLI: A Dataset for Document-level Natural Language Inference for Contracts

引用键：`koreeda2021contractnli`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Yuta Koreeda and Christopher D. Manning |
| 年份／类型 | 2021；`inproceedings` |
| 会议 | Findings of the Association for Computational Linguistics: EMNLP 2021 |
| 出版方 | Association for Computational Linguistics |
| 页码／文章号 | 1907–1919 |
| DOI | 10.18653/v1/2021.findings-emnlp.164 |
| 最终链接 | https://aclanthology.org/2021.findings-emnlp.164/ |

**正文支持性：**支持 document-level reasoning、evidence identification 和跨条款/非局部 exception 的背景。原文 §7 专门分析 non-local negation by exception；本文 Related Work 的概括不超出这一范围。

**本次处理：**补全或规范：来源链接

补官方 URL。保留 Christopher D. Manning：论文 PDF 首页有中间首字母 D.，ACL 导出元数据省略 D. 不应照抄。

引用位置（审计开始时源文件行号）：`acl_latex.tex:65`、`acl_latex.tex:383`。

核对依据：[来源 1](https://aclanthology.org/2021.findings-emnlp.164/)、[来源 2](https://aclanthology.org/2021.findings-emnlp.164.pdf)。

### 25. Lost in the Middle: How Language Models Use Long Contexts

引用键：`liu2024lost`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Nelson F. Liu and Kevin Lin and John Hewitt and Ashwin Paranjape and Michele Bevilacqua and Fabio Petroni and Percy Liang |
| 年份／类型 | 2024；`article` |
| 期刊／存档 | Transactions of the Association for Computational Linguistics |
| 卷号 | 12 |
| 页码／文章号 | 157–173 |
| DOI | 10.1162/tacl_a_00638 |
| 最终链接 | https://aclanthology.org/2024.tacl-1.9/ |

**正文支持性：**支持当前Intro/Related Work关于长上下文检索随证据位置恶化的论述；该文具体测试多文档问答及键值检索。文中的多跳/聚合概括由同组RULER/LongBench共同支撑，未把三类任务都错误归于Lost in the Middle。

**本次处理：**补全或规范：来源链接

作者、题名、2024年、TACL12卷、157–173页及DOI完全匹配；补ACL永久链接。

引用位置（审计开始时源文件行号）：`acl_latex.tex:67`、`acl_latex.tex:383`。

核对依据：[来源 1](https://aclanthology.org/2024.tacl-1.9/)。

### 26. The Llama 3 Herd of Models

引用键：`grattafiori2024llama3`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Llama Team |
| 年份／类型 | 2024；`article` |
| 期刊／存档 | arXiv preprint arXiv:2407.21783 |
| DOI | 10.48550/arXiv.2407.21783 |
| 最终链接 | https://arxiv.org/abs/2407.21783v3 |

**正文支持性：**支持§4.4模型身份和出处，不用于证明本文实验收益。

**本次处理：**作者、标题、年、出处及标识相符。

Llama Team团体署名对应报告首页，涵盖3.1及8B。 复用同日已完成的逐项审计和存档证据，并确认条目此后未改；本轮无需再次修改。

引用位置（审计开始时源文件行号）：`acl_latex.tex:325`。

核对依据：[来源 1](https://arxiv.org/abs/2407.21783v3)。

### 27. The Second Type of Uncertainty in Monte Carlo Tree Search

引用键：`moerland2020mcts`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Thomas M. Moerland and Joost Broekens and Aske Plaat and Catholijn M. Jonker |
| 年份／类型 | 2020；`article` |
| 期刊／存档 | arXiv preprint arXiv:2005.09645 |
| DOI | 10.48550/arXiv.2005.09645 |
| 最终链接 | https://arxiv.org/abs/2005.09645 |

**正文支持性：**正文关于 loop difficulty、重复状态与 subtree uncertainty 的引用成立：原文 Section 4/4.2 明确讨论循环、重复展开和不终止。附录把 depth-limit truncation 说成 common in loops 稍超来源；建议将该短句改为 loops can prevent termination，保留引用。

**本次处理：**IJCAI 2020、2388–2394 不属于本篇。已核实来源为 arXiv:2005.09645（2020）；合著者出版列表仍标 Submitted/arXiv，不能称 IJCAI 已发表。

改为预印本条目并补 arXiv DOI/URL。

引用位置（审计开始时源文件行号）：`acl_latex.tex:73`、`acl_latex.tex:389`、`acl_latex.tex:434`。

核对依据：[来源 1](https://arxiv.org/abs/2005.09645)、[来源 2](https://arxiv.org/pdf/2005.09645)、[来源 3](https://liacs.leidenuniv.nl/~plaata1/pubs.html)、[来源 4](https://www.ijcai.org/proceedings/2020/330)。

### 28. An Analysis of Approximations for Maximizing Submodular Set Functions—I

引用键：`nemhauser1978analysis`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | George L. Nemhauser and Laurence A. Wolsey and Marshall L. Fisher |
| 年份／类型 | 1978；`article` |
| 期刊／存档 | Mathematical Programming |
| 卷号 | 14 |
| 期号 | 1 |
| 页码／文章号 | 265–294 |
| DOI | 10.1007/BF01588971 |

**正文支持性：**文献证明的是单调次模目标在基数约束下的贪心近似界。本文正向成对关系奖励不满足一般次模性；只能支持方法动机，不能给本文效用函数提供该近似保证。

**本次处理：**标题漏了末尾的 Part I（—I）。

作者、1978、14(1):265–294、DOI正确。正文仅作最小范围澄清，明确本文采用启发式 replacement；不改变公式或算法。

引用位置（审计开始时源文件行号）：`acl_latex.tex:228`。

核对依据：[来源 1](https://link.springer.com/article/10.1007/BF01588971)。

### 29. GPT-4o System Card

引用键：`openai2024gpt4o`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | OpenAI |
| 年份／类型 | 2024；`article` |
| 期刊／存档 | arXiv preprint arXiv:2410.21276 |
| DOI | 10.48550/arXiv.2410.21276 |
| 最终链接 | https://arxiv.org/abs/2410.21276 |

**正文支持性：**支持§4.4模型身份和出处，不用于证明本文实验收益。

**本次处理：**作者、标题、年、出处及标识相符。

官方 system card 明确要求署名 OpenAI (2024)。 复用同日已完成的逐项审计和存档证据，并确认条目此后未改；本轮无需再次修改。

引用位置（审计开始时源文件行号）：`acl_latex.tex:325`。

核对依据：[来源 1](https://cdn.openai.com/gpt-4o-system-card.pdf)。

### 30. Qwen2.5 Technical Report

引用键：`qwen2024qwen25`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Qwen Team |
| 年份／类型 | 2024；`article` |
| 期刊／存档 | arXiv preprint arXiv:2412.15115 |
| DOI | 10.48550/arXiv.2412.15115 |
| 最终链接 | https://arxiv.org/abs/2412.15115v1 |

**正文支持性：**支持§4.4模型身份和出处，不用于证明本文实验收益。

**本次处理：**作者、标题、年、出处及标识相符。

2024年v1的 Qwen Team 署名及Qwen2.5系列/72B模型对应准确。 复用同日已完成的逐项审计和存档证据，并确认条目此后未改；本轮无需再次修改。

引用位置（审计开始时源文件行号）：`acl_latex.tex:325`。

核对依据：[来源 1](https://arxiv.org/abs/2412.15115v1)。

### 31. Qwen3.5-9B

引用键：`qwen2026qwen35nine`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Qwen Team |
| 年份／类型 | 2026；`misc` |
| 最终链接 | https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md |
| 版本说明 | Official model card, revision c202236. Accessed October 1, 2026 |

**正文支持性：**支持§4.4模型身份和出处，不用于证明本文实验收益。

**本次处理：**作者、标题、年、出处及标识相符。

官方Qwen3.5-9B固定模型卡版本对应实际实验。 复用同日已完成的逐项审计和存档证据，并确认条目此后未改；本轮无需再次修改。

引用位置（审计开始时源文件行号）：`acl_latex.tex:325`。

核对依据：[来源 1](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md)。

### 32. UCD: Upper Confidence Bound for Rooted Directed Acyclic Graphs

引用键：`saffidine2012ucd`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Abdallah Saffidine and Tristan Cazenave and Jean Méhat |
| 年份／类型 | 2012；`article` |
| 期刊／存档 | Knowledge-Based Systems |
| 卷号 | 34 |
| 页码／文章号 | 26–33 |
| DOI | 10.1016/j.knosys.2011.11.014 |

**正文支持性：**论文明确为 rooted DAG 中的 transposition-aware MCTS，Sections 2–3 讨论多个路径分散统计以及在边上聚合；适合当前引用。其 2011 预印本日期不改变 2012 正式期刊年。

**本次处理：**补全或规范：DOI

补 DOI 10.1016/j.knosys.2011.11.014。

引用位置（审计开始时源文件行号）：`acl_latex.tex:73`。

核对依据：[来源 1](https://www.sciencedirect.com/science/article/abs/pii/S0950705111002504)、[来源 2](https://www.lamsade.dauphine.fr/~cazenave/papers/kbs.pdf)、[来源 3](https://api.crossref.org/works/10.1016/j.knosys.2011.11.014)。

### 33. Mastering the game of Go with deep neural networks and tree search

引用键：`silver2016mastering`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | David Silver and Aja Huang and Chris J. Maddison and Arthur Guez and Laurent Sifre and George van den Driessche and Julian Schrittwieser and Ioannis Antonoglou and Veda Panneershelvam and Marc Lanctot and Sander Dieleman and Dominik Grewe and John Nham and Nal Kalchbrenner and Ilya Sutskever and Timothy Lillicrap and Madeleine Leach and Koray Kavukcuoglu and Thore Graepel and Demis Hassabis |
| 年份／类型 | 2016；`article` |
| 期刊／存档 | Nature |
| 卷号 | 529 |
| 期号 | 7587 |
| 页码／文章号 | 484–489 |
| DOI | 10.1038/nature16961 |

**正文支持性：**支持 AlphaGo 将策略/价值网络与 Monte Carlo 搜索结合的论述；没有将其结果误写为本文实验。Nature 直连抓取存在访问跳转，题录以出版商 Crossref 登记及原文首页交叉确认。

**本次处理：**作者仅存前 10 人及手工 others；该论文实际有 20 位作者，ACL 样式把占位符错误计作 1 others。

引用位置（审计开始时源文件行号）：`acl_latex.tex:70`、`acl_latex.tex:389`。

核对依据：[来源 1](https://www.nature.com/articles/nature16961)、[来源 2](https://api.crossref.org/works/10.1038/nature16961)、[来源 3](https://www.cs.cmu.edu/afs/cs.cmu.edu/academic/class/15780-s16/www/AlphaGo.nature16961.pdf)。

### 34. Depth-First Search and Linear Graph Algorithms

引用键：`tarjan1972depth`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Robert Tarjan |
| 年份／类型 | 1972；`article` |
| 期刊／存档 | SIAM Journal on Computing |
| 卷号 | 1 |
| 期号 | 2 |
| 页码／文章号 | 146–160 |
| DOI | 10.1137/0201010 |

**正文支持性：**原文摘要直接给出有向图 SCC 算法及 k1 V+k2 E+k3 的空间/时间上界；支持正文线性 SCC 预处理。

**本次处理：**作者、标题、年、出处及标识相符。

SIAM 原刊：1972年6月，1(2):146–160；2006 是网站上线日期，不能替代出版年。

引用位置（审计开始时源文件行号）：`acl_latex.tex:105`、`acl_latex.tex:177`。

核对依据：[来源 1](https://epubs.siam.org/doi/10.1137/0201010)。

### 35. Debian Policy Manual: Declaring relationships between packages

引用键：`debianPolicyRelationships`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | The Debian Policy Mailing List |
| 年份／类型 | 2025；`manual` |
| 最终链接 | https://browse.dgit.debian.org/debian-policy.git/plain/policy/ch-relationships.rst?h=debian/4.7.2.0 |
| 版本说明 | Version 4.7.2.0, chapter 7 |

**正文支持性：**固定版本 §7.2 明确配置顺序、循环依赖、Pre-Depends 所需先行安装/配置；支持正文依赖条件。

**本次处理：**原可变网页现在显示 v4.7.4.1，与参考文献声明的版本 4.7.2.0 不一致；固定到官方 Git 中的 debian/4.7.2.0 标签。；原作者 Debian Policy Manual 是书名；固定版本的 conf.py.in 明确 author/latex_documents 为 The Debian Policy Mailing List。

保留真实的历史版本 4.7.2.0 和 2025 年；不把实验来源暗中升级到最新版。

引用位置（审计开始时源文件行号）：`acl_latex.tex:65`。

核对依据：[来源 1](https://browse.dgit.debian.org/debian-policy.git/plain/policy/ch-relationships.rst?h=debian/4.7.2.0)、[来源 2](https://browse.dgit.debian.org/debian-policy.git/plain/policy/conf.py.in?h=debian/4.7.2.0)、[来源 3](https://lists.debian.org/debian-devel-announce/2025/02/msg00005.html)、[来源 4](https://www.debian.org/doc/debian-policy/ch-relationships.html)。

### 36. Debian Policy Manual: Shared libraries

引用键：`debianPolicySharedLibraries`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | The Debian Policy Mailing List |
| 年份／类型 | 2025；`manual` |
| 最终链接 | https://browse.dgit.debian.org/debian-policy.git/plain/policy/ch-sharedlibs.rst?h=debian/4.7.2.0 |
| 版本说明 | Version 4.7.2.0, chapter 8 |

**正文支持性：**固定版本 §8.1 明确共享库新旧 ABI 的共同安装、旧程序兼容与新接口最低版本依赖；支持正文 old interfaces/newer dependencies 例子。

**本次处理：**原可变网页现在显示 v4.7.4.1，与参考文献声明的版本 4.7.2.0 不一致；固定到官方 Git 中的 debian/4.7.2.0 标签。；原作者 Debian Policy Manual 是书名；固定版本的 conf.py.in 明确 author/latex_documents 为 The Debian Policy Mailing List。

保留真实的历史版本 4.7.2.0 和 2025 年；不把实验来源暗中升级到最新版。

引用位置（审计开始时源文件行号）：`acl_latex.tex:65`。

核对依据：[来源 1](https://browse.dgit.debian.org/debian-policy.git/plain/policy/ch-sharedlibs.rst?h=debian/4.7.2.0)、[来源 2](https://browse.dgit.debian.org/debian-policy.git/plain/policy/conf.py.in?h=debian/4.7.2.0)、[来源 3](https://lists.debian.org/debian-devel-announce/2025/02/msg00005.html)、[来源 4](https://www.debian.org/doc/debian-policy/ch-sharedlibs.html)。

### 37. Algorithmic Learning in a Random World

引用键：`vovk2005algorithmic`。结论：**通过；保留**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Vladimir Vovk and Alexander Gammerman and Glenn Shafer |
| 年份／类型 | 2005；`book` |
| 出版方 | Springer |
| DOI | 10.1007/b106715 |

**正文支持性：**书中第2章介绍 conformal prediction，支持校准动机；本文没有把该书交换性条件下的结论直接套到自适应搜索。

**本次处理：**作者、标题、年、出处及标识相符。

Springer 第一版页面确认三作者、书名、2005、出版社及 DOI；不因第二版存在而改动经典第一版。

引用位置（审计开始时源文件行号）：`acl_latex.tex:223`、`acl_latex.tex:392`。

核对依据：[来源 1](https://link.springer.com/book/10.1007/b106715)。

### 38. Can Language Models Solve Graph Problems in Natural Language?

引用键：`wang2023can`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Heng Wang and Shangbin Feng and Tianxing He and Zhaoxuan Tan and Xiaochuang Han and Yulia Tsvetkov |
| 年份／类型 | 2023；`inproceedings` |
| 会议 | Advances in Neural Information Processing Systems |
| 出版方 | Curran Associates, Inc. |
| 卷号 | 36 |
| 页码／文章号 | 30840–30861 |
| DOI | 10.52202/075280-1345 |
| 最终链接 | https://proceedings.neurips.cc/paper_files/paper/2023/hash/622afc4edf2824a1b6aaf5afe153fa93-Abstract-Conference.html |

**正文支持性：**支持Related Work图任务/提示形式及虚假相关的敏感性；NLGraph覆盖8类图任务，比较prompting。

**本次处理：**补全或规范：文献类型、DOI、正式会议名称、页码、来源链接、出版方、卷号

现有2023预印本本身有效；已有NeurIPS36正式版本，同6名作者同年，建议用正式版本并补30840–30861页、DOI、链接。这属于发表信息更新，不是虚假文献。

引用位置（审计开始时源文件行号）：`acl_latex.tex:383`。

核对依据：[来源 1](https://proceedings.neurips.cc/paper_files/paper/2023/hash/622afc4edf2824a1b6aaf5afe153fa93-Abstract-Conference.html)。

### 39. Chain-of-Thought Prompting Elicits Reasoning in Large Language Models

引用键：`wei2022chain`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Jason Wei and Xuezhi Wang and Dale Schuurmans and Maarten Bosma and Brian Ichter and Fei Xia and Ed Chi and Quoc V. Le and Denny Zhou |
| 年份／类型 | 2022；`inproceedings` |
| 会议 | Advances in Neural Information Processing Systems |
| 出版方 | Curran Associates, Inc. |
| 卷号 | 35 |
| 页码／文章号 | 24824–24837 |
| DOI | 10.52202/068431-1800 |
| 最终链接 | https://proceedings.neurips.cc/paper_files/paper/2022/hash/9d5609613524ecf4f15af0f7b31abca4-Abstract-Conference.html |

**正文支持性：**支持Related Work关于CoT改善逐步推理的概括，原文在算术、常识和符号推理任务验证；本稿未声称CoT对所有模型任务统一有效。

**本次处理：**补全或规范：DOI、页码、来源链接、出版方

9名作者与NeurIPS2022官方记录一致；补24824–24837页、官方DOI及链接。网页将brian ichter小写属于元数据大小写，不把现有规范大小写误报为错误。

引用位置（审计开始时源文件行号）：`acl_latex.tex:383`。

核对依据：[来源 1](https://proceedings.neurips.cc/paper_files/paper/2022/hash/9d5609613524ecf4f15af0f7b31abca4-Abstract-Conference.html)。

### 40. Tree of Thoughts: Deliberate Problem Solving with Large Language Models

引用键：`yao2024tree`。结论：**已修正**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Shunyu Yao and Dian Yu and Jeffrey Zhao and Izhak Shafran and Tom Griffiths and Yuan Cao and Karthik Narasimhan |
| 年份／类型 | 2023；`inproceedings` |
| 会议 | Advances in Neural Information Processing Systems |
| 出版方 | Curran Associates, Inc. |
| 卷号 | 36 |
| 页码／文章号 | 11809–11822 |
| DOI | 10.52202/075280-0517 |
| 最终链接 | https://proceedings.neurips.cc/paper_files/paper/2023/hash/271db9922b8d1f4dd7aaef84ed5ac703-Abstract-Conference.html |

**正文支持性：**支持Related Work关于显式搜索改善LLM推理；原文以生成/评价thoughts及BFS/DFS开展搜索，对Game24、写作、填字作实验。

**本次处理：**会议年份误写2024；NeurIPS36官方卷次/元数据/论文页脚均为2023。

修正2024→2023；补11809–11822页、DOI、链接。Tom Griffiths为官方BibTeX署名，PDF作Thomas L.Griffiths，均是同一作者，保留现有官方BibTeX写法；内部key可不改。

引用位置（审计开始时源文件行号）：`acl_latex.tex:386`。

核对依据：[来源 1](https://proceedings.neurips.cc/paper_files/paper/2023/hash/271db9922b8d1f4dd7aaef84ed5ac703-Abstract-Conference.html)。

### 41. Using Anytime Algorithms in Intelligent Systems

引用键：`zilberstein1996anytime`。结论：**核心信息正确；已补全**。

| 字段 | 核对后的记录 |
|---|---|
| 作者（完整、按顺序） | Shlomo Zilberstein |
| 年份／类型 | 1996；`article` |
| 期刊／存档 | AI Magazine |
| 卷号 | 17 |
| 期号 | 3 |
| 页码／文章号 | 73–83 |
| DOI | 10.1609/aimag.v17i3.1232 |

**正文支持性：**摘要讨论 anytime 算法在计算时间和解质量间的权衡，符合正文固定预算/可中断计算的背景引用。

**本次处理：**补全或规范：DOI

作者、题名、1996、AI Magazine17(3):73–83均正确；补官方DOI。

引用位置（审计开始时源文件行号）：`acl_latex.tex:264`。

核对依据：[来源 1](https://ojs.aaai.org/aimagazine/index.php/aimagazine/article/view/1232)、[来源 2](https://onlinelibrary.wiley.com/doi/10.1609/aimag.v17i3.1232)。

## 5. 未进入论文的 8 条库存文献

这些条目不增加当前 PDF 的参考文献数量，也不承担当前正文的证据作用。

| 引用键 | 文献 | 核对结果／处理 | 依据 |
|---|---|---|---|
| `chalkidis2020legalbert` | LEGAL-BERT: The Muppets Straight Out of Law School (2020) | 作者、标题、年、出处及标识相符。  | [来源 1](https://aclanthology.org/2020.findings-emnlp.261/) |
| `devlin2019bert` | BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding (2019) | 补全或规范：正式会议名称、来源链接 未引用库存条目4作者、题名、2019、页码、DOI正确；booktitle补官方完整卷册名，补ACL链接。 | [来源 1](https://aclanthology.org/N19-1423/) |
| `edge2024graphrag` | From Local to Global: A Graph RAG Approach to Query-Focused Summarization (2024) | 补全或规范：DOI、来源链接 未引用库存条目8作者对应2024arXivv1，完全正确；v2在2025新增2名作者，不能据v2倒推v1漏作者。补DOI并明确链接v1，不混合版本。 | [来源 1](https://arxiv.org/abs/2404.16130v1) |
| `hansen1996monitoring` | Monitoring the Progress of Anytime Problem-Solving (1996) | 补全或规范：来源链接  | [来源 1](https://cdn.aaai.org/AAAI/1996/AAAI96-182.pdf)、[来源 2](https://www.aiinternational.org/Library/AAAI/1996/aaai96-182.php) |
| `kahneman2011thinking` | Thinking, Fast and Slow (2011) | 该条是专著，原 @article 类型错误。 出版社页面确认 Daniel Kahneman、书名、Farrar Straus Giroux、2011年10月25日；修复库存类型，不引入正文。 | [来源 1](https://us.macmillan.com/books/9781429969352/thinkingfastandslow/) |
| `li2022alphacode` | Competition-Level Code Generation with AlphaCode (2022) | 未引用库存条目作者手工截断为10名加and others；Science登记完整26名，若引用将产生错误的“1 others”。 未引用库存条目卷378期6624页1092–1097年2022、DOI正确；从Science提交Crossref的完整记录恢复26位作者（同时与作者arXiv一致）。 | [来源 1](https://doi.org/10.1126/science.abq1158)、[来源 2](https://api.crossref.org/works/10.1126/science.abq1158)、[来源 3](https://arxiv.org/abs/2203.07814) |
| `silver2017mastering` | Mastering Chess and Shogi by Self-Play with a General Reinforcement Learning Algorithm (2017) | 未引用库存条目的实际 13 作者被截成前 10 人加 others。  | [来源 1](https://arxiv.org/abs/1712.01815)、[来源 2](https://arxiv.org/pdf/1712.01815) |
| `tolpin2012simple` | MCTS Based on Simple Regret (2012) | 补全或规范：DOI、number、页码、卷号  | [来源 1](https://ojs.aaai.org/index.php/AAAI/article/view/8126)、[来源 2](https://ojs.aaai.org/index.php/AAAI/article/download/8126/7984) |

## 6. 没有误改的几个细节

- **RAP**：Joshua Jiahua Hong、Daisy Zhe Wang 的完整姓名见正式 PDF；不因网页缩名而删去中间名。
- **ContractNLI／LexGLUE**：保留正式 PDF 的 Christopher D. Manning、Daniel Martin Katz。
- **RULER**：已核实原 arXiv 2024 版本的 8 位作者并补齐链接；不根据署名不一致、访问受限的会议元数据强行换版本。原引用本身成立。
- **GraphRAG（库存）**：8 位作者对应 2024 v1，链接固定到 v1；不拼接后来 10 位作者的版本。
- **Tarjan／Chaslot／Tolpin**：保留原论文出版年，网站迁移或后补上网的日期不充当论文年份。
- **五条模型出处**：复用同日已完成的原始报告／模型卡审计，确认条目之后没有变化；本轮保留。[此前完整报告](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/NEW_CITATION_AUDIT_ZH.md)。
- **ACL 作者截断**：未改官方 `.bst`。Battaglia 显示 19 名＋8 others，LegalBench 显示 19 名＋21 others；Silver 2016 共20人，最终 PDF 完整列出20人。清除的是手工占位导致的错误计数，不自行改写官方样式。
- **AAAI／ICAPS 卷期**：已核实原刊 issue；ACL 的 `inproceedings` 样式不接受 volume 与 number 同时输出，最终保留卷号与页码，避免模板警告。完整核实记录保存在 JSON。

## 7. 访问边界与链接实测

对 41 条在用文献逐一测试最终 DOI 或 URL。27 条在本次请求直接返回 HTTP 200；其余14条出现出版商反爬、代理／TLS连接限制或 IEEE 的202响应，不能把这些情况写成“文献不存在”。已结合出版商登记、官方正文、作者原文或版本化源文件核对。两处真正无效的 DOI（SARA、Berger）均已移除。

Berger 1990 的 ACM 页面本轮仍受限；其论文存在、会议和页码由作者 Shor 的 MIT 发表列表及 Berger 本人另一篇 SIAM 论文中的题录交叉核实。这里明确区分“题录和引用用途可核”与“已经读到原篇全文”，不把前者包装成后者。

完整 HTTP 状态和最终跳转地址见 [链接检查记录](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/full_citation_audit/link_checks.json)。完整49条逐字段记录、正文引用上下文见 [机器可读审计清单](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/full_citation_audit/full_audit.json)。

## 8. 编译与交付核验

- 净稿 **26 页**；Conclusion 在第 **8 页**结束，主文仍在8页内。Limitations 现从第8页开始并延至第9页，References 从第9页开始。
- 修订版 **33 页**，包含正文修订痕迹和旧书目软删除；净稿不显示这些历史内容。
- 两版都只有 **41 个正式 bibliography item**，与正文／附录的 **70 次有效 citation 出现、41 个不同引用键**对应；8条库存未误入列表。
- 无未定义 citation／reference、无重复 label、无损坏内部链接。原77处图表／章节交叉引用仍可解析，净稿图表及算法编号不变。
- 净稿无 overfull 排版警告；修订版只保留此前贡献列表的约5.2pt提示，本轮新增书目无溢出。已视觉检查参考文献各页及正文末页。
- 29 条调整后的在用书目标红；18 条可见文字发生变化的旧书目在修订版黑色软删除。仅增加链接而未改变可见文字的条目不重复打印相同旧句。原有模型引用颜色保留。
- 实验数值、算法公式、模型集合、图表资产与官方 ACL bibliography 样式保持不变。

修改文件：[custom.bib](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/custom.bib)、[正文](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex)、[修订标记](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_markup.tex)、[书目旧文保留](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_bibliography_audit.tex)。

完整构建核验：[final_verification.json](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/full_citation_audit/final_verification.json)。修改前文件与原始来源证据一并存档于 `full_citation_audit/`。

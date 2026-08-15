# LFP-MCGS 文献检索与新颖性边界

> 检索日期：2026-08-16
> 研究问题：是否已有工作将 MCGS、SCC 与 least-fixed-point（LFP）结合，用于自然语言递归规则的选择性解析与可验证闭包？
> 结论性质：这是面向立项的系统性检索，不是正式 systematic review。负检索只能说明“在下列来源和关键词中未发现”，不能证明绝对不存在。

## 1. 结论先行

截至检索日，我们**没有找到名称或机制都与 LFP-MCGS 等价的已发表工作**。在外部 archival primary sources 中，也未找到一篇明确称为 MCGS、同时以 SCC decomposition 做 recursive-Datalog LFP recovery 的论文。尤其没有找到一个系统同时具备以下四点：

1. 对自然语言 facts / rules 做局部、按需的语义解析；
2. 用 SCC 与 MCGS 分配有限的 LLM 调用预算；
3. 对已验证的 positive-Horn program 做确定性 least-fixed-point saturation；
4. 用 missing-premise obligations 反向驱动重访，并返回 source-linked proof / coverage certificate。

但是，不能据此写成“第一个 MCGS + SCC”“第一个处理环的 MCGS”或“第一个 fixed-point MCGS”，因为：

- Paper 1 的 [SA-MCGS](https://github.com/chenqianwan/SA-MCGS) 本身已经公开组合 MCGS、Tarjan SCC 与 transposition table；
- **MCGS 中的环与数值 fixed point**；
- **Monte Carlo search 与 SCC decomposition**；
- **Datalog 的 SCC-wise least-fixed-point evaluation**；
- **自然语言规则到符号程序、外部记忆和证明搜索**。

因此，新颖性不是任何单个组件，而是以下交集：

> **在昂贵且不可靠的自然语言规则解析前提下，用 SCC-aware MCGS 调度“下一段读什么”，并让确定性 LFP 内核负责单调闭包与可验证证明。**

最稳妥的表述是：

> We introduce an SCC-aware MCGS scheduler for selective semantic interpretation toward verified least-fixed-point closure of recursive natural-language rule programs.

在完成最终 Scholar / Semantic Scholar / DBLP 前向与反向引文核查之前，正文应优先使用 “we found no prior system that jointly ...”，而不是绝对的 “the first”。

---

## 2. 检索范围与关键词

本轮检索覆盖 ACL Anthology、PMLR、AAAI / ICAPS、AAMAS proceedings、Springer、IJCAI、KR、OpenReview、arXiv，以及论文和项目的官方页面。使用的关键词组合包括：

```text
"LFP-MCGS"
"least fixed point" "Monte Carlo graph search"
"fixed-point MCGS" / "fixed point MCGS"
"SCC-MCGS" / "MCGS" "strongly connected component"
"SCC" "Monte Carlo tree search"
"recursive Datalog" MCTS / MCGS
"cyclic rules" LLM reasoning
"least fixed point" natural language reasoning
"symbolic working memory" recursive rules
```

精确词 `LFP-MCGS`、`SCC-MCGS` 和 `recursive Datalog + MCGS/MCTS` 未产生对应方法命中。不过存在数个必须在 related work 中正面讨论的近邻。

---

## 3. 最直接的近邻

| 工作 | 已经覆盖什么 | 与 LFP-MCGS 的关键差异 | 对 claim 的约束 |
|---|---|---|---|
| [SA-MCGS](https://github.com/chenqianwan/SA-MCGS), Paper 1 / public repository | AlphaGo-style MCGS、Tarjan SCC、TT 与循环文档风险核 | 风险证据搜索，而不是 verified partial program 的 LFP saturation | Paper 2 不能再次 claim first MCGS + SCC；必须把它写成 state/semantics/task 的演化 |
| [Monte-Carlo Graph Search: the Value of Merging Similar States](https://proceedings.mlr.press/v129/leurent20a.html), ACML 2020 | 正式提出 MCGS；搜索图可有 loop；用 fixed-point iteration 计算 Bellman bounds | 数值 MDP planning；不是 Datalog LFP；无 SCC、自然语言规则和证明证书 | 不能说 first fixed-point MCGS 或 first MCGS with loops |
| [ANN-CMCGS](https://imrclab.github.io/assets/pdf/2026-ann-cmcgs-grc.pdf), AAMAS 2026 extended abstract | 明确支持 arbitrary directed graphs with cycles，并阻止单次 playout 内无限循环 | 连续机器人规划；无 SCC、规则闭包、LFP 或证据验证；论文也未解决 cyclic convergence/completeness | 不能说 first cyclic / non-DAG MCGS |
| [Guessing Winning Policies in LTL Synthesis by Semantic Learning](https://link.springer.com/chapter/10.1007/978-3-031-37706-8_20), CAV 2023 | MCTS + SCC decomposition；按 SCC 逆拓扑求解 parity game | 是 MCTS 而非 state-merging MCGS；目标是 LTL synthesis，不是自然语言规则的 LFP closure | 不能说 first Monte Carlo search with SCCs |
| [Parsel](https://papers.neurips.cc/paper_files/paper/2023/hash/6445dd88ebb9a6a3afa0b126ad87fe41-Abstract-Conference.html), NeurIPS 2023 | 将函数依赖图分成 SCC，联合合成 mutually recursive functions，并用 tests 验证 | 无 MCTS/MCGS；目标是程序合成而非语义闭包 | 不能把 SCC-aware LLM reasoning/synthesis 写成全新方向 |
| [A Monte-Carlo Tree Search in Argumentation](https://www.mit.edu/~irahwan/argmas/argmas14/w12-07.pdf), ArgMAS 2014 | MCTS reward 使用 Dung grounded extension；后者由 LFP 定义 | tree search 主动消除环，TT 仅 future work；不是 Datalog rule interpretation | 不能说 first Monte Carlo search involving LFP semantics |
| [On Fast Large-Scale Program Analysis in Datalog](https://www.souffle-lang.com/pdf/cc.pdf) | Soufflé 对互递归关系做 SCC 分解、semi-naive evaluation 与 fixed-point computation | 规则已经是精确 Datalog；不存在昂贵/随机的 NL 解析和搜索预算问题 | 不能把 SCC + LFP evaluator 当算法 novelty |
| [Symbolic Working Memory](https://aclanthology.org/2024.emnlp-main.974/), EMNLP 2024 | 将事实/规则保存在外部工作记忆中，迭代 grounding，并由 LLM 实现局部规则 | 倾向先装入全部输入；没有以 SCC 拓扑控制的 MCGS scheduler、verified monotone commit 或 coverage-aware stopping | 必须作为最近的 NLP 方法邻居比较 |

### 3.1 原始 MCGS 已经涉及 loop 与 fixed point

[Leurent and Maillard (ACML 2020)](https://proceedings.mlr.press/v129/leurent20a.html) 的贡献是合并相似或转置状态，从 tree 变为 graph。其主文讨论 graph loop，补充材料使用 fixed-point iteration 求 Bellman-style bounds。

这里的 “fixed point” 与我们计划中的 LFP 不同：

- ACML 2020：折扣 MDP 上的**数值 Bellman fixed point**；
- LFP-MCGS：finite positive-Horn program 上 immediate-consequence operator 的**最小 Herbrand fixed point**。

这一区分必须写在论文开头。否则 reviewer 很容易认为只是把已有 MCGS 的 fixed-point 术语换到规则推理。

### 3.2 Cyclic MCGS 已经存在

[ANN-CMCGS](https://imrclab.github.io/assets/pdf/2026-ann-cmcgs-grc.pdf) 直接宣称支持带环任意有向图。它通过记录当前 playout 路径，避免再次选择路径中已有节点，从而阻止无限 selection / backpropagation。该工作面向连续 motion planning，没有 SCC saturation、逻辑闭包或证明来源；但足以否定 “MCGS 第一次支持 cycle” 的 claim。

[Improving AlphaZero Using Monte-Carlo Graph Search](https://ojs.aaai.org/index.php/ICAPS/article/view/15952)（ICAPS 2021）也应引用，但该版本将图限制为 DAG；它有助于说明 transposition graph 这条 MCGS 主线如何发展。

### 3.3 Monte Carlo search + SCC 也不是空白

[Křetínský et al. (CAV 2023)](https://link.springer.com/chapter/10.1007/978-3-031-37706-8_20) 在 LTL synthesis 中明确组合 MCTS 与 SCC decomposition：按 SCC 逆拓扑处理 parity game，并缓存已经求解区域的出边值。

它与我们最像的地方，是“用 SCC 划分循环逻辑结构，并让 Monte Carlo search 在其上工作”。真正的差异必须落在：

- MCTS vs. state-sharing MCGS；
- game policy/value vs. monotone fact closure；
- 已形式化 parity game vs. 尚未被完整语义解析的自然语言规则；
- winning policy vs. source-linked entailment proof / coverage certificate。

### 3.4 SCC-wise LFP 本身是经典求值技术

[Soufflé](https://www.souffle-lang.com/pdf/cc.pdf) 等 Datalog 系统将 predicate precedence graph 的 SCC 视为互递归规则区，并在 SCC 内迭代到 fixed point；semi-naive evaluation 只传播新增 facts。这与我们计划的 `ΔK_t` 十分接近，但它是应当复用的 deterministic kernel，而不是论文的新算法。

因此论文应明确：

> LFP-MCGS does not replace semi-naive Datalog evaluation. It decides which expensive natural-language regions should be interpreted next; the symbolic engine only saturates the currently verified partial program.

### 3.5 SCC-aware LLM reasoning 已有相邻占位

[Parsel](https://papers.neurips.cc/paper_files/paper/2023/hash/6445dd88ebb9a6a3afa0b126ad87fe41-Abstract-Conference.html) 将 LLM 或人工产生的函数依赖图分解为 SCC，对相互递归的函数联合采样，并用 tests 验证。它不是 MCGS，也不计算事实闭包；但会阻止我们把贡献泛化成“首次让 LLM 在 SCC 上推理”。

同样，[A Monte-Carlo Tree Search in Argumentation](https://www.mit.edu/~irahwan/argmas/argmas14/w12-07.pdf) 已经让 MCTS 使用由 least fixed point 定义的 grounded extension 计算 reward。它没有构造 MCGS transposition graph，并且主动去除搜索环；然而它足以说明“Monte Carlo search 与 LFP semantics 从未结合”也是不安全的说法。

---

## 4. 自然语言符号推理近邻

### 4.1 NL → formal program → solver

- [Logic-LM](https://aclanthology.org/2023.findings-emnlp.248/)（Findings of EMNLP 2023）将自然语言问题翻译为符号形式，再调用相应求解器，并利用 solver error 做自修正。
- [LINC](https://aclanthology.org/2023.emnlp-main.313/)（EMNLP 2023）同样强调用符号逻辑承担推断、用语言模型承担转换。

它们会成为最危险的强基线：`full input → NL-to-Datalog once → solver`。如果这个 baseline 在长循环图上已经便宜、稳定且准确，MCGS 调度就没有存在必要。

我们的潜在差异不是“使用 solver”，而是：

1. 输入过长或含大量 query-irrelevant rule，无法一次可靠解析；
2. 局部解析结果被 validation gate 后单调提交；
3. 新 closure 与 missing premises 会动态改变下一窗口的价值；
4. 在预算耗尽时输出 verified entailment 或 `UNKNOWN`，而非把未找到证明误判为否定。

### 4.2 外部记忆与逐步规则应用

[Symbolic Working Memory](https://aclanthology.org/2024.emnlp-main.974/) 是最需要认真区分的方法：它也维护事实、规则和 grounding 状态，也将符号操作与 LLM 结合。LFP-MCGS 必须通过以下实验性差异站住：

- 长文本中只选择性解析部分规则，而不是预先可靠装载全部符号记忆；
- SCC / fixed-point rounds 是显式、可控的难度变量；
- proof obligation 能显著改善 query-relevant closure recovery；
- 在相同 LLM token / call budget 下优于 exhaustive、random、deterministic cycle-basis 选择。

[Bi-Chainer](https://aclanthology.org/2024.findings-acl.507/)（Findings of ACL 2024）用动态双向 chaining 提高推理效率，是 missing-premise backward search 的直接近邻。区别应是它优化 proof-chain search，而我们的困难来自 query-relevant recursive SCC 的饱和、闭包共享和 circular self-support。

### 4.3 Search-augmented reasoning

- [RAP](https://aclanthology.org/2023.emnlp-main.507/) 将语言模型推理建模为 MCTS；
- [LATS](https://proceedings.mlr.press/v235/zhou24r.html) 将语言模型、环境反馈和 tree search 结合；
- [Graph of Thoughts](https://doi.org/10.1609/aaai.v38i16.29720) 支持图状中间思维；
- [ReKG-MCTS](https://aclanthology.org/2025.findings-acl.484/) 在知识图谱上做 MCTS 推理。

这些工作说明“LLM + search / graph”本身不构成 novelty。LFP-MCGS 必须强调 verified monotone closure，而非自由文本 thought graph。

### 4.4 形式推理与 provenance

- [ProofWriter](https://aclanthology.org/2021.findings-acl.317/) 提供 Datalog-style rules、entailment labels 和 proofs；
- [RuleTaker](https://www.ijcai.org/Proceedings/2020/537) 提供自然语言规则推理及受控深度；
- [FaiRR](https://aclanthology.org/2022.acl-long.77/) 将规则选择与规则应用解耦，强调忠实推理；
- [ASPBench](https://proceedings.kr.org/2025/60/) 覆盖 Answer Set Programming 中的 entailment、verification 和 computation，并暴露模型对循环/非单调语义的困难；
- [Causality and Minimal Supports in Recursive Datalog](https://arxiv.org/abs/2607.16443) 研究递归 Datalog 的支持与 provenance，并提示 minimal supports 可能指数爆炸。

最后一项意味着我们不应随意承诺“枚举所有最小证明”。两个月版本应只保证：返回**一条可验证证明**，以及可选的紧凑 proof core；最小性只作为可计算时的分析指标。

---

## 5. Benchmark 空位应如何准确描述

不能笼统写“现有 benchmark 都避开 cycle”。RuleTaker / ProofWriter 的语义来自 Datalog 风格系统，RuleTaker 生成器也可能出现 self-loop；ASPBench 更明确包含循环程序。

较安全的观察是：

> 主流自然语言 entailment benchmark 很少把 **productive SCC、是否存在外部 seed、达到固定点所需 rounds、以及 query-relevant closure coverage** 同时作为受控变量；多数仍主要监督最终 label 或有限 proof depth，而不是 SCC 内完整闭包的恢复与证书。

[ReEfBench](https://aclanthology.org/2026.acl-long.931/) 的生成设置显式避免 cyclic reasoning，可作为“部分新 benchmark 仍主动排除环”的例证，但不能外推为整个领域都如此。另一个相邻工作 [t-BEN](https://openreview.net/pdf?id=XkzGgKJAA2) 已含 symbolic + natural-language DatalogMTL 的 Recursive level；截至检索日它是 non-archival OpenReview submission，引用时必须标明状态。

建议新 benchmark 至少包含 matched pairs：

- 同一 SCC topology；
- seeded productive cycle vs. unseeded circular self-support；
- query-relevant seed vs. distractor seed；
- 相同表层文本与 proof length，只改变一处 ground fact；
- 控制 SCC size、fixed-point rounds、irrelevant-rule ratio 与 paraphrase split。

---

## 6. 三张图必须分清

LFP-MCGS 容易出现概念混淆。论文应明确区分：

```mermaid
flowchart LR
  G1["规则依赖图\n可能有 SCC"] -->|"SCC decomposition"| S["递归规则区域"]
  S -->|"选择性解析并 commit"| G2["事实闭包格\nK0 ⊆ K1 ⊆ ... ⊆ K*"]
  G2 -->|"等价 partial state 合并"| G3["MCGS transposition graph"]
```

1. **Rule / predicate dependency graph**：规则的 head-body 依赖；可能有 SCC；SCC 在这里定义。
2. **Closure-state lattice**：每个状态是已经验证的 fact set；在 positive Horn 下单调增长，因此沿执行轨迹不回退。
3. **MCGS transposition graph**：不同窗口访问顺序可能到达同一 canonical closure state，因此可以合并。

这也解释了为什么方法不是简单“在一个 SCC 里跑原始 MCGS”：Paper 2 的 state、transition、reward 和 stopping condition 都发生了改变。

---

## 7. Claim 红线与推荐写法

### 7.1 不安全的 claim

- First fixed-point MCGS.
- First MCGS + SCC.
- First MCGS that handles cycles / non-DAG graphs.
- First Monte Carlo search using SCC decomposition.
- First MCGS for logical or formal reasoning.
- First proof / provenance method for recursive Datalog.
- Exact LFP recovery under a fixed LLM-call budget.

### 7.2 可以防守的 claim

在最终检索无新冲突的前提下：

> To our knowledge, LFP-MCGS is the first LLM-guided, SCC-aware MCGS architecture designed for verified least-fixed-point closure of recursive natural-language rule programs.

更保守的版本：

> We found no prior system that jointly performs SCC-aware Monte Carlo graph scheduling, selective natural-language rule interpretation, monotone least-fixed-point saturation, and source-linked proof recovery.

方法贡献可拆为：

1. 一个 selective semantic interpretation 问题，而不是新的 Datalog evaluator；
2. closure-aware transposition state 与 proof-obligation-driven search；
3. 对 circular self-support 的 one-sided soundness：有证书才能报 entailment；
4. 一个以 SCC size / seed / fixed-point rounds 为控制轴的诊断 benchmark；
5. 在真实 solver-certified graph 上的外部验证。

### 7.3 理论边界

第一版只在以下范围内声称性质：

- finite、grounded / function-free；
- positive Horn rules；
- least-Herbrand-model semantics；
- committed facts / rules 单调增长；
- LLM 解析错误由验证门约束，但端到端 soundness 仍相对于已提交程序；
- 预算耗尽且未找到 proof 时输出 `UNKNOWN`；只有 relevant source coverage 完成时才允许 certified negative。

若加入 negation-as-failure、exceptions、fact deletion、existential rules 或 function symbols，需要重新定义语义和终止保证，不属于 2026 年 10 月版本。

---

## 8. 最危险基线与可证伪条件

这篇论文应主动设置能否定自身必要性的基线：

1. **Full-context direct LLM**；
2. **Full NL → Datalog once + symbolic solver**（Logic-LM 风格）；
3. **Extract-all local windows + semi-naive LFP**；
4. **Deterministic SCC / cycle-basis window order**；
5. **Bi-directional chaining**；
6. **Random / LEA / 原始 SA-MCGS scheduler**；
7. **LFP-MCGS 去掉 obligation revisit、transposition sharing、validation gate 的消融**。

如果 `extract-all once + solver` 在 hard split 上以更低成本达到同等 proof-valid accuracy，或者 deterministic SCC order 与 MCGS 的差异小于 5 个百分点，就不应把 MCGS 作为主贡献继续扩展。

---

## 9. 建议正文 Related Work 结构

1. **From SA-MCGS to closure-state search**：明确 Paper 1 是 self-prior，而非需要匿名隐藏的空白；
2. **Monte Carlo Graph Search and cyclic search graphs**：ACML 2020、ICAPS 2021、ANN-CMCGS；
3. **SCC decomposition and recursive fixed-point evaluation**：CAV 2023、Parsel、Soufflé / Datalog；
4. **Neuro-symbolic natural-language reasoning**：Logic-LM、LINC、Symbolic Working Memory、Bi-Chainer；
5. **Search-augmented LLM reasoning**：RAP、LATS、ReKG-MCTS、argumentation MCTS；
6. **Recursive reasoning benchmarks and proof faithfulness**：RuleTaker、ProofWriter、FaiRR、ASPBench、ReEfBench、t-BEN。

这一结构会让 reviewer 清楚看到：我们了解每个组件的历史，并把 novelty 放在一个可验证的新问题交叉点上，而不是“把 MCGS、SCC 和 solver 拼起来”。

---

## 10. 投稿前必须补做的检索

- 在 Google Scholar、Semantic Scholar、DBLP 对 `MCGS + SCC/LFP/Datalog/recursive rules` 做最终检索；
- 对 ACML 2020 MCGS、ANN-CMCGS、Symbolic Working Memory、CAV 2023 做前向引用扫描；
- 检查 2026 年 8 月之后的 ARR / ACL / EMNLP / NeurIPS / ICLR 新稿；
- 核对所有 preprint 的最终发表状态，related work 中区分 peer-reviewed paper 与 preprint；
- 用一段明确文字区分 Bellman fixed point、least fixed point 与 greatest fixed point；
- 方法正式命名使用 **LFP-MCGS**，避免 `GFP` 被理解为 greatest fixed point。

## 11. 立项判断

**建议进入两周 pilot，但不建议直接宣称 broad novelty。** 当前文献格局支持一个窄而清晰的研究问题：

> 当规则文本很长、局部语义解析昂贵且可能出错时，能否用 SCC-aware MCGS 选择解析位置，并以 verified LFP closure 给出比一次性形式化更好的 accuracy–cost Pareto？

只要 pilot 能证明 MCGS scheduler 相对 `extract-all + solver` 与 deterministic SCC traversal 的实际优势，这个切入具有独立于 Paper 1 的顶会故事；否则应将其降为 SA-MCGS 的系统扩展，而不是第二篇主论文。

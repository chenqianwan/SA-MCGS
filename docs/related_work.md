# Related Work

> 本文档收录与 SA-MCGS 系统相关的文献，按主题分类。每篇文献包含：核心方法概述、与我们工作的关系、可复用的数据/指标。

---

## 1. Contract Graph Construction & Analysis

### 1.1 GRAPH-GRPO-LEX (Dechtiar et al., 2025)

**完整标题**: GRAPH-GRPO-LEX: Contract Graph Modeling and Reinforcement Learning with Group Relative Policy Optimization

**来源**: arXiv:2511.06618 (Nov 2025)

**作者**: Moriya Dechtiar, Daniel Martin Katz, Mari Sundaresan, Sylvain Jaume, Hongming Wang

**机构**: Harvard, Illinois Tech, Georgetown, MIT, Stanford CodeX

**代码**: https://github.com/moriyadechtiar/graph-grpo-lex/

#### 核心方法

将合同转化为结构化语义图（semantic graph），使用 GRPO 强化学习训练 LLM 自动提取节点和边。

- **图本体 (Ontology)**:
  - 节点类型: `CLAUSE`, `PARTY`, `DEFINED_TERM`, `VALUE`
  - 边类型: `IS_PART_OF`, `REFERENCES`, `USES`, `MENTIONS_PARTY`, `DEFINES`, `CONTAINS`
  - 同时建模结构依赖（IS_PART_OF）和语义依赖（REFERENCES, USES 等）
- **Pipeline**: 合同分割（NuPunkt/CharBoundary）→ clause-level minigraph extraction → minigraph assembly → 去重合并为完整合同图
- **训练**: SFT baseline → Gated GRPO（分阶段引入 reward signal：结构合法性 → F1 → 语义相似度 → 图编辑距离）
- **Contract Linter**: 将图指标映射为法律风险信号（density, depth, centrality, k-core, orphan/leaf ratio, articulation points, **cycle detection**）

#### CUAD 图结构指标（关键数据）

论文使用 CUAD 的 Distribution & Channel Sales 合同子集（43 份合同，约 1600 个条款），以 Zogenix Inc. 经销商协议为详细 case study：

| 指标 | 值 | 法律含义 |
|------|------|----------|
| 节点数 | 257 | 合同含大量实体（条款+术语+方+值） |
| 边数 | 916 | 高连通性 |
| 图密度 | 0.014 | 层级文档中的正常稀疏度 |
| 最长依赖路径 | 6 | 认知负荷深度 — 理解需要 6 步递归追踪 |
| 孤立节点 (Orphan) | 131 | 未被引用的定义项 → glossary bloat |
| 叶子节点 (Leaf) | 97 | 终端节点 — 支付义务、终止权等最终后果 |
| 孤立比 (Orphan Ratio) | ~0.50 | 接近一半节点未被引用 |
| 叶子比 (Leaf Ratio) | 0.377 | 近 40% 节点为叶子 |
| 连接关键点 (Articulation Points) | 11 | "单点故障" — 修改将断裂合同逻辑 |

**环检测相关**:
- 论文明确提及 **Cycle Detection** 是关键图算法之一
- 他们将环定义为 "logical flaws and ambiguity"（如"术语 A 引用 B，B 又引用 A"的循环定义）
- **但论文仅将环视为缺陷信号，未利用 SCC 结构做风险量化或搜索**

#### 关键性能数据

| 指标 | SFT Baseline | Gated GRPO |
|------|:---:|:---:|
| strict_micro_precision | 0.539 | **0.806** |
| strict_micro_recall | 0.854 | 0.790 |
| strict_micro_f1 | 0.661 | **0.798** |
| fuzzy_micro_f1 | 0.693 | **0.809** |
| invalid_json_rate | 0.0 | 0.02 |

Gated GRPO 相比 non-gated GRPO F1 提升 6 倍。

#### 与 SA-MCGS 的关系

| 方面 | GRAPH-GRPO-LEX | SA-MCGS (Ours) |
|------|---------------|----------------|
| **图构建** | GRPO 训练 LLM 自动提取 | LLM prompt-based 提取 + 权重过滤 |
| **节点粒度** | 多类型 (Clause, Party, Term, Value) | Clause-only（聚焦条款间依赖） |
| **依赖类型** | 6 种 (IS_PART_OF, REFERENCES...) | 5 种 (defines, constrains, triggers, modifies, references) |
| **SCC 处理** | 仅检测环 → 标记为 "逻辑缺陷" | **核心贡献**: Tarjan SCC → 多采样 → 三层剪枝 → MCGS 搜索 |
| **风险评估** | 图指标间接推断（density, depth...） | 每条款直接评分（5 维度 × mean/max/std/confidence） |
| **搜索策略** | 无 | UCB1 + rollout + 反向传播 |
| **输出** | 合同图 + linter 指标 | 条款级风险评分 + 高风险/高不确定性标记 |

**核心定位差异**: GRAPH-GRPO-LEX 解决的是 *graph construction*（如何从合同文本构建准确的图）；SA-MCGS 假设图已构建，解决的是 *risk evaluation on graph*（如何在图上高效搜索风险评估路径）。两者互补：他们的 GRPO 图构建可以作为我们 Module 2 (GraphBuilder) 的增强替代。

#### 可复用数据

- **CUAD 子集**: 43 份 Distribution & Channel Sales 合同，~1600 条款 — 可作为我们的实验数据源
- **CUAD 图结构基线**: density=0.014, depth=6, orphan_ratio=0.5 等指标可作为 SA-MCGS Section 3（实证分析）的 baseline 参考
- **环存在性验证**: 他们的 cycle detection 结果佐证了合同中确实存在环状依赖，证明 SCC-based 方法的必要性

### 1.2 Measuring Law Over Time (Boulet et al., 2021)

**完整标题**: Measuring Law Over Time: A Network Analytical Framework with an Application to Statutes and Regulations in the United States and Germany

**来源**: Frontiers in Physics, 9:658463 (2021)

**作者**: Romain Boulet, Pierre Music, Corinna Coupette, Dirk Hartung, Michael Bommarito, Daniel Martin Katz

**数据**: QuantLaw — https://doi.org/10.5281/zenodo.4660133

#### 核心方法

对 US Code 和德国联邦法律（BGB/StGB 等）的 section-level 交叉引用图做时间序列分析，借鉴 Web 图研究中的 bowtie 分解框架，追踪 SCC、in-only 分量、out-only 分量、tendrils 和 tubes 中节点比例随时间的变化。

- **数据范围**: US Code (1926–2019), German federal law (1950–2019), US Code of Federal Regulations
- **图构建**: 每年一张有向图，节点 = 法律条款 (section)，边 = 交叉引用
- **分析方法**: 最大连通分量 → bowtie 分解 (SCC / in-component / out-component / tendrils / tubes)

#### SCC 核心发现（关键数据）

| 指标 | US Code (2019) | German Federal Law (2019) |
|------|:-:|:-:|
| SCC 占全部 sections 比例 | ~15% | ~15% |
| Out-only 分量占比 | ~7% | ~12% |
| In-component 相对 SCC 大小 | SCC 的 ~3 倍 | SCC 的 ~2 倍 |

**结构形态**:
- 法律系统**不**呈现生物网络中常见的 bowtie 结构（小 SCC + 较大 in/out 分量）
- 也**不**像早期万维网 bowtie（各分量大小相近，SCC 略大）
- 而是类似 **"火箭"结构** — in-only 分量是基座，tendrils/tubes 是尾翼，SCC 是箭体，out-component 是箭头
- 两个法域结构高度相似，暗示法律体系的共性结构规律

#### 论文做了什么 vs 没做什么

**做了**:
- Giant SCC 的比例及其随时间的演化趋势
- Bowtie 各分量的相对大小对比（跨法域）
- 网络增长的宏观统计（节点数、边数、密度的时序变化）

**没做（= 我们的 contribution 空间）**:
- **SCC 大小分布**: 只报告了 giant SCC，未给出所有非平凡 SCC 的完整分布 — 有多少 size=2 小环？多少 size≥10 中等环？
- **SCC 内部结构分析**: giant SCC 里 ~15% 的条款具体属于哪些法律领域？（税法？刑法？跨领域？）
- **SCC 时序演化细粒度**: bowtie 比例趋势图给了，但 SCC 是在增长还是碎片化？
- **SCC 上的风险量化/搜索**: 完全没有 — 他们的目标是测度学 (measurement)，不是风险评估
- **跨法域 SCC 内部组成对比**: 美国 ~15% vs 德国 ~15%，但内部有什么区别？

#### 与 SA-MCGS 的关系

| 方面 | Measuring Law Over Time | SA-MCGS (Ours) |
|------|------------------------|----------------|
| **目标** | 法律网络的宏观测度与演化 | SCC 上的风险评估与搜索 |
| **图粒度** | Section-level（法律条款） | Clause-level（合同条款） |
| **SCC 用途** | Bowtie 分解的一个分量 → 报告占比 | **核心对象**: SCC → 多采样 → 剪枝 → MCGS 搜索 |
| **SCC 分析深度** | Giant SCC 比例 | 完整分布 + 内部结构 + 时序碎片化 + 风险量化 |
| **数据** | US Code + 德国联邦法 (statute/regulation) | 合同 (CUAD) + 可扩展至 QuantLaw |
| **方法** | 描述性网络统计 | 算法框架 (Tarjan → pruning → MCGS) |

**核心定位差异**: "Measuring Law Over Time" 证明了法律文本中 SCC 的**存在性和规模**（~15%），但只是把 SCC 当作 bowtie 的一个组成部分来测度。SA-MCGS 则将 SCC 作为**核心计算对象**，在其上构建搜索和风险评估算法。他们的数据验证了我们方法的前提假设，他们未做的 SCC 分布/内部结构分析正是我们的 novel contribution。

#### 可复用数据

- **QuantLaw 数据集**: 完整的 US Code / 德国法 / US CFR 交叉引用图（`.gpickle.gz`），可直接加载到我们的 pipeline（已实现 `QuantLawLoader`）
- **SCC 比例基线**: Giant SCC ~15% — 可作为我们 Section 3 实证分析的 ground truth / 参照值
- **时序基线**: 1926–2019 年的 bowtie 演化趋势 — 可与我们的 SCC 细粒度分析做对比
- **"火箭"结构模型**: 可在论文中引用作为法律网络的宏观结构参照

---

## 2. Legal NLP & Contract Understanding

*(预留位置)*

### 2.1 CUAD (Hendrycks et al., 2021)

> TODO: CUAD 数据集原始论文

### 2.2 ContractNLI (Koreeda & Manning, 2021)

> TODO: 607 NDA 合同的文档级自然语言推理数据集

### 2.3 LAW: Legal Agentic Workflows (Watson et al., 2025)

> TODO: 多 Agent 合同分析框架

---

## 3. Graph-Based Risk Analysis

*(预留位置)*

### 3.1 Knowledge Graph for Contract Risk (Zheng et al., 2025)

> TODO: NCKG — Nested Contract Knowledge Graph，construction contract 领域

### 3.2 Construction Contract Risk via Knowledge-Augmented LM (Wong et al., 2024)

> TODO: knowledge-augmented LM 做合同风险识别

---

## 4. Monte Carlo Tree/Graph Search

### 4.1 UCT 收敛性与有限路径假设 (Kocsis & Szepesvári, 2006)

**完整标题**: Bandit based Monte-Carlo Planning

**来源**: ECML 2006 (Machine Learning: ECML 2006, LNCS 4212, pp. 282–293)

**作者**: Levente Kocsis, Csaba Szepesvári

**机构**: MTA SZTAKI, Hungarian Academy of Sciences

#### 核心方法

提出 UCT (Upper Confidence bounds applied to Trees) 算法，将 multi-armed bandit 的 UCB1 策略递归应用于搜索树的每一层，实现 exploration-exploitation 平衡。

- **收敛性定理 (Theorem 5)**: UCT 在 finite-horizon MDP 上，搜索树深度有限（D < ∞）时，bias of the estimated value converges to zero at a rate of O(log(n)/n)
- **关键假设**: 搜索路径长度有限（bounded depth D），rewards bounded in [0,1]
- **对于 discounted MDP**: 基于 Kearns et al. (2002) 的结论，fixed-size trees with depth proportional to 1/(1−γ) · log(1/(ε(1−γ))) 足以找到 near-optimal actions

#### 与 SA-MCGS 的关系

| 方面 | UCT | SA-MCGS (Ours) |
|------|-----|----------------|
| **图结构** | 搜索树 (tree, acyclic by definition) | 有向图（含 SCC 环路） |
| **路径长度** | 有限 (finite horizon D) | SCC 中路径可无限循环 |
| **收敛保证** | Theorem 5: O(log n / n) bias | 需要 SCC 处理后才能继承 UCT 收敛性 |
| **环处理** | **不涉及**（树不含环） | Tarjan SCC → 联合评估 → 坍缩为 DAG |

**核心定位差异**: UCT 的收敛性证明从根本上假设了搜索空间是树/有限深度结构。当存在 SCC（路径长度无上界）时，Theorem 5 的前提被违反，Q-value 收敛不再有保证。**SA-MCGS 通过 SCC 坍缩将有环图转化为 DAG，重新满足 UCT 收敛条件。**

#### 可引用论点

- "UCT convergence requires finite-horizon assumption (bounded search depth D)"
- "Cycles in directed graphs create potentially infinite paths, violating the fundamental assumption of UCT's convergence proof"
- 引用格式: Kocsis, L. and Szepesvári, C. (2006). Bandit based Monte-Carlo Planning. In ECML 2006, LNCS 4212, pp. 282–293.

---

### 4.2 Monte-Carlo Graph Search for AlphaZero (Czech et al., 2020)

**完整标题**: Monte-Carlo Graph Search for AlphaZero

**来源**: ICAPS 2021 (Proceedings of the International Conference on Automated Planning and Scheduling, Vol. 31, pp. 103–111)

**作者**: Johannes Czech, Patrick Korus, Kristian Kersting

**机构**: Technical University of Darmstadt, hessian.AI

**代码**: CrazyAra engine

**arXiv**: 2012.11045 (Dec 2020)

#### 核心方法

将 AlphaZero 的 MCTS 搜索树推广为 **Directed Acyclic Graph (DAG)**，利用 transposition（不同路径到达同一状态）共享信息，减少重复评估。

- **关键创新**:
  - 搜索结构从 tree → DAG（允许节点有多个 parent）
  - Modified backpropagation：DAG 中需要处理多条 backprop 路径
  - Transposition nodes：不同 trajectory 到达相同 board position 时共享节点
  - ε-greedy exploration：帮助 UCT 跳出 local optima
  - Terminal solver：对已知结果的子图做精确推理

- **明确限定**: 论文标题和全文多次强调 **"Directed Acyclic Graph"**，不处理环

- **性能提升**: 在 chess 和 crazyhouse 上，MCGS 在 fixed time 和 fixed evaluations 两种条件下都显著优于 MCTS

#### 关于环 (Cycles) 的处理

论文明确只处理 **transpositions**（同一状态经不同路径到达），这在棋类游戏中是 DAG 结构（因为游戏规则如 50-move rule 保证有限性）。论文 **不涉及** 真正的 SCC / 强连通分量。

> "We generalize the search tree to a Directed Acyclic Graph (DAG)." — 论文 Abstract

> "Nodes with more than one parent, so called transposition nodes, allow to share information between different subtrees." — Section 1

#### 与 SA-MCGS 的关系

| 方面 | MCGS (Czech et al.) | SA-MCGS (Ours) |
|------|---------------------|----------------|
| **搜索结构** | DAG（允许 transposition） | 有向图 → SCC 坍缩 → DAG |
| **环处理** | **不处理**（游戏天然 acyclic） | **核心贡献**: Tarjan → SCC 评估 → 坍缩 |
| **Backpropagation** | DAG 上的 multi-parent backprop | SCC 内：Conflict Probability Matrix；DAG 上：同 MCGS |
| **Transposition Table** | 用于合并相同 game state | 用于 SCC 内重复窗口的缓存 + DAG 上 state 合并 |
| **应用域** | Chess, Crazyhouse (零和博弈) | 法律文档风险评估 (单人优化) |
| **评估函数** | 神经网络 (value + policy head) | LLM rollout (risk score) |

**核心定位差异**: Czech et al. 解决了 MCTS → DAG 的推广（处理 transposition），但**明确不处理环**。SA-MCGS 在此基础上更进一步，解决了 **有环有向图 → DAG** 的转化问题（通过 SCC 检测与坍缩），使得 MCGS 的 DAG 假设得到满足。两者是递进关系：Czech et al. 证明了 DAG 搜索的有效性，我们证明了如何将有环图**安全转化为**DAG。

#### 可引用论点

- "State-of-the-art Monte-Carlo Graph Search explicitly requires DAG structure"
- "Even the latest MCGS extensions handle only transpositions (DAG), not cycles (SCC)"
- "Our SCC-collapse step is a necessary prerequisite for applying MCGS to cyclic document graphs"
- 引用格式: Czech, J., Korus, P., and Kersting, K. (2021). Monte-Carlo Graph Search for AlphaZero. In ICAPS, Vol. 31, pp. 103–111.

---

### 4.3 MCTS 在环结构上的指数爆炸 (Moerland et al., 2020)

**完整标题**: The Second Type of Uncertainty in Monte Carlo Tree Search

**来源**: IJCAI 2020 (Proceedings of the 29th International Joint Conference on Artificial Intelligence)

**作者**: Thomas M. Moerland, Joost Broekens, Aske Plaat, Catholijn M. Jonker

**机构**: Delft University of Technology, Leiden University (LIACS)

**代码**: https://github.com/tmoer/mcts-t

#### 核心方法

揭示 MCTS 的一个根本性缺陷：UCB 公式只依赖 local visit counts（第一类不确定性），完全忽略了 subtree size（第二类不确定性），导致在有环/深度不对称的环境中性能灾难性崩溃。

- **关键发现**:
  - 在 Chain domain（稀疏奖励长链）中，MCTS 复杂度为 **O(2^N)**（指数级），而最优算法仅需 O(N)
  - 原因：MCTS 在根节点两侧获得相同 return (0)，无法判断哪边更深，导致 traces 指数级扩散
  - **Loops (环)** 是 subtree depth variation 的特殊情况：环使得搜索树在展开时出现无限重复

- **环的影响 (Section 4)**:
  - Loop = 同一状态在单条 trace 中重复出现
  - 当环存在时，搜索树展开会产生大量重复状态的分支
  - 对于 γ=1 的无限时域问题，环内累积奖励 S° 导致 value estimate → ±∞（Eq. 13）
  - "Standard MCTS cannot detect this problem, and will therefore repeatedly expand the tree in all directions"

- **解决方案 MCTS-T+**:
  - 估计每个 action 下方 subtree size (σ_τ)
  - 检测到 loop 时设 σ_τ = 0，**完全移除该方向的 exploration pressure**
  - 本质上是在 single trace 内做 loop blocking

#### 与 SA-MCGS 的关系

| 方面 | MCTS-T+ (Moerland et al.) | SA-MCGS (Ours) |
|------|---------------------------|----------------|
| **问题识别** | Loops = 单条 trace 内状态重复 | SCC = 图拓扑结构中的强连通分量 |
| **处理粒度** | Single state loop detection | **Multi-node SCC 整体处理**（Tarjan 算法） |
| **处理方式** | Block loop (σ_τ=0), 截断不展开 | SCC 内联合评估 → 坍缩为超级节点 |
| **信息保留** | 丢弃环内所有信息 | **保留 SCC 内风险评估结果**（Conflict Matrix） |
| **应用场景** | RL navigation tasks (grid world) | 法律文档依赖图 |
| **理论贡献** | 证明环导致 MCTS O(2^N) 复杂度 | 提出 SCC 坍缩使 MCTS 在有环图上可行 |

**核心定位差异**: Moerland et al. 在 RL 环境中发现了环对 MCTS 的灾难性影响，并提出了 trace-level 的 loop blocking 解决方案。但他们的方法是**消极的**（检测到环就截断，丢弃环内信息）。SA-MCGS 的 SCC 处理是**积极的**——不仅检测环，还在环内做联合评估、提取风险信息，然后以保留信息的方式坍缩。Moerland 的 MCTS-T+ 可视为我们方法的退化特例（SCC 大小=1 时的 loop blocking）。

#### 可引用的关键数据

| 数据点 | 值 | 用途 |
|--------|------|------|
| MCTS 在 Chain(N) 的复杂度 | O(2^N) 指数级 | 证明环导致 MCTS 失效 |
| MCTS-T+ 的改进 | Chain(100) 从不收敛 → 可收敛 | loop handling 的必要性 |
| 环的 value 估计问题 | γ=1 时 V → ±∞ (Eq. 13) | 环导致值估计发散的数学证明 |

#### 可引用论点

- "MCTS has exponential complexity O(2^N) on tasks with loops" (Section 3.2, Figure 3)
- "Standard MCTS cannot detect [loops], and will therefore repeatedly expand the tree in all directions" (Section 4)
- "For infinite-horizon problems with γ=1, the value estimate of a loop state diverges to ±∞" (Eq. 13)
- 引用格式: Moerland, T.M., Broekens, J., Plaat, A., and Jonker, C.M. (2020). The Second Type of Uncertainty in Monte Carlo Tree Search. In IJCAI-20, pp. 2388–2394.

---

### 4.4 AlphaGo / AlphaZero (Silver et al., 2016/2017)

> TODO: MCTS 经典方法

### 4.5 MCTS for NLP / LLM Reasoning (RAP, etc.)

> TODO: MCTS 在 NLP 推理中的应用 (Hao et al., 2023 - RAP)

---

## 5. Reinforcement Learning for LLM

*(预留位置)*

### 5.1 DeepSeek-R1 & GRPO (Shao et al., 2024; Guo et al., 2025)

> TODO: GRPO 方法原始论文

### 5.2 Self-RAG (Asai et al., 2024)

> TODO: 自反思检索增强生成

---

## 6. Graph Pruning & Information Bottleneck

*(预留位置)*

### 6.1 Graph Information Bottleneck

> TODO: 图信息瓶颈理论

### 6.2 Dominance-based Pruning in Multi-Objective Optimization

> TODO: Pareto 支配剪枝理论基础

---

## 附录: 论文中可引用的关键数据汇总

| 来源 | 数据点 | 值 | 用途 |
|------|--------|------|------|
| GRAPH-GRPO-LEX | CUAD 合同子集大小 | 43 contracts, ~1600 clauses | Section 3 实证分析 |
| GRAPH-GRPO-LEX | 单合同图规模 | 257 nodes, 916 edges | 图规模 baseline |
| GRAPH-GRPO-LEX | 图密度 | 0.014 | 稀疏性 baseline |
| GRAPH-GRPO-LEX | 最长依赖路径 | 6 | 认知深度 baseline |
| GRAPH-GRPO-LEX | 孤立比 / 叶子比 | 0.50 / 0.377 | 图结构特征 |
| GRAPH-GRPO-LEX | 连接关键点 | 11 | articulation points |
| GRAPH-GRPO-LEX | GRPO F1 | 0.798 (strict), 0.809 (fuzzy) | 图构建精度 baseline |
| GRAPH-GRPO-LEX | 环检测 | 确认存在 | SCC 方法必要性论证 |
| Measuring Law Over Time | SCC 占全部节点比例 | ~15% (US & DE) | SCC 规模 baseline / 前提验证 |
| Measuring Law Over Time | Out-only 分量占比 | US ~7%, DE ~12% | Bowtie 结构参照 |
| Measuring Law Over Time | In-component / SCC 比 | US ~3x, DE ~2x | 法律网络"火箭"结构 |
| Measuring Law Over Time | 数据时间跨度 | 1926–2019 (US), 1950–2019 (DE) | 时序分析覆盖范围 |
| Measuring Law Over Time | 数据集 | QuantLaw (Zenodo 4660133) | 可直接加载的 `.gpickle.gz` 图 |

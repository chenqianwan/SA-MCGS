# LFP-MCGS 文献检索与新颖性边界

> 更新日期：2026-08-16
>
> 检索目标：分别判断“普通 seeded LFP + MCGS”和“SCC-aware LFP-MCGS”是否已有直接先例。
>
> 结论性质：面向立项的系统性检索，不是穷尽式 systematic review；“未发现”不等于“不存在”。

## 1. 最终判断

| 问题 | 检索结论 | 可否作为 novelty |
|---|---|---|
| 是否存在名称为 LFP-MCGS 的方法？ | 未检到 | 只能说明名称未被占用 |
| 是否存在与我们完整机制相同的方法？ | 未检到 | 可以谨慎描述交集空位 |
| 普通 seed + LFP + Monte Carlo search 是否为空白？ | **不是**。已有 MCTS + LFP、MCTS + recursive logic closure、Datalog/GDL + UCT 等先例 | **不能 claim first** |
| MCGS 是否首次进入形式推理？ | 不是；Aristotle 已在 Lean proof states 上使用 MCGS | 不能作为 claim |
| MCGS + SCC 是否首次出现？ | 不是；SA-MCGS 已经这样做，MCTS + SCC 也有外部先例 | 不能作为 claim |
| 预算化自然语言规则获取 + partial-program LFP + MCGS 精确状态合并是否已有直接同类？ | 本轮未发现 | 当前最可守的普通版交集 |
| productive recursive SCC + 上述机制是否已有直接同类？ | 本轮未发现 | **更清晰、更有科学问题的主线** |

若把两个术语都卡得很严——MCGS 必须是 Leurent-style state-merging graph search，LFP 必须是 positive-Horn least-Herbrand fixed point——本轮**没有找到直接命中**。但投稿时不能依靠这一字面空位：reviewer 很可能把 MCTS→MCGS 的状态合并视为增量变化，并同时引用已有的 MCTS+LFP 与 MCGS+formal-proof 工作。

一句话结论：

> **普通 seed 本身没有新颖性，LFP 与 Monte Carlo search 的宽泛组合也不是空白。**
>
> 普通版能守住的，只是“对尚未完全获得的自然语言程序做预算化获取，并在 provenance-aware partial LFP states 上做 MCGS”；加入 productive SCC 后，才有一个适合构造成受控 NLP failure 的核心现象：外部 seed 可以驱动反馈传播，而无 seed 的循环不能自我证明。该语义本身是经典 LFP 性质，新意在于 noisy NL acquisition 下的诊断与调度。

因此建议：

- 方法可以在完整图上运行，不必把输入限制为一个 SCC；
- **论文主问题保留 SCC / productive recursion**；
- DAG 与普通 seeded chain 作为 matched control 和 generality 证据；
- 只有实验表明 DAG 与 SCC 都有稳定收益时，才把标题上升为一般的 budgeted program acquisition。

---

## 2. “普通 seed + LFP”到底是什么

在 finite、function-free、positive-Horn 程序中，给定初始事实 F₀ 和规则 R：

<div align="center">

T_{R,F₀}(K) = F₀ ∪ K ∪ { head(r) | body(r) ⊆ K }

K* = lfp(T_{R,F₀}) = ⋃_{t≥0} T_{R,F₀}ᵗ(∅)

</div>

- **seed**：初始 extensional facts，即 F₀；
- **LFP**：从 seed 出发反复应用规则，直到不再产生新事实；
- **SCC**：任何有向图都可定义 SCC；本文所说的 semantic/recursive SCC 特指 predicate dependency graph 上的 SCC，不是 LFP-MCGS 名字里的某个字母；
- **MCGS**：若规则已完整符号化，它不负责求 LFP；它只可能负责决定下一份昂贵文本或规则源该不该读取。

### 2.1 三种情形

| 情形 | 语义行为 | MCGS 的必要性 |
|---|---|---|
| 已知符号程序 + DAG | 拓扑序或 semi-naive 一次传播即可 | 基本没有 |
| 未知/昂贵 NL 程序 + DAG | 主要是 query-directed acquisition / parsing | 可能有，但近邻很多 |
| 未知/昂贵 NL 程序 + productive recursive SCC | 新事实会跨反馈边产生更多新事实，需要多轮 saturation；还必须阻止 circular self-support | 最有理由 |

### 2.2 productive seed 与 circular self-support

~~~mermaid
flowchart LR
  F["Seed facts<br/>edge(a,b), edge(b,c)"] --> R0["r0: edge(x,y) → reach(x,y)"]
  R0 --> K1["new: reach(a,b), reach(b,c)"]
  K1 --> R1["r1: reach(x,y) ∧ edge(y,z) → reach(x,z)"]
  R1 --> K2["new: reach(a,c)"]
  K2 --> Q["query proved"]
  R1 -. "predicate feedback<br/>reach → reach" .-> R1
~~~

这里的递归规则实例真正产生了新 atom；删除 r1 后，query 不再成立。它是 **productive feedback**。

相反，若只有 <code>p(x)→q(x)</code> 与 <code>q(x)→p(x)</code>，但没有 p/q seed，LFP 中不会凭空出现 p 或 q。这是 **circular self-support**，也是我们比一般 proof search 更有辨识度的科学问题。

---

## 3. 检索协议

### 3.1 来源

优先检查论文原文与官方出版页面：ACL Anthology、PMLR、AAAI/ICAPS、AAMAS、NeurIPS、IEEE、Springer、KR、DBLP、arXiv 及作者项目页。

### 3.2 查询族

~~~text
"LFP-MCGS"
"least fixed point" "Monte Carlo graph search"
"least Herbrand model" MCTS / MCGS
"recursive Datalog" MCTS / MCGS
"recursive logic program" "Monte Carlo tree search"
"deductive closure" MCTS
"Datalog" UCT "transposition table"
"MCTS" theorem proving / proof search
"budgeted oracle calls" MCTS
"active information gathering" MCTS
"value of computation" MCTS
"query-directed Datalog" Magic Sets tabling
"selective rule interpretation" LLM
"SCC" MCTS / MCGS
~~~

### 3.3 排除的假阳性

- 数据库文献中的 MCG 常指 **minimal complete generalization**，不是 Monte Carlo Graph Search；
- MDP 文献中的 fixed point 多为 Bellman/value fixed point，不是 least-Herbrand LFP；
- greatest fixed point、coinduction、stable-model semantics 不能与 positive-Horn LFP 混用；
- “recursive algorithm”不等于 recursive logic semantics；
- GDL 是 Datalog variant，因此 GDL + UCT 是真实技术近邻，不能当作同名误报排除。

---

## 4. 普通 seed + LFP + Monte Carlo：已有的强先例

### 4.1 最危险的四篇

| 工作 | 已经做了什么 | 与我们不同 | 它否定的 claim |
|---|---|---|---|
| [A Monte-Carlo Tree Search in Argumentation](https://www.mit.edu/~irahwan/argmas/argmas14/w12-07.pdf), ArgMAS 2014 | 将 Dung grounded extension 明确定义为 characteristic function 的 **least fixed point**；MCTS 搜 argumentation，LFP 用于 reward | 完整 argument graph 已知；非 positive-Horn closure；attack 不可撤销且已走 attack 不可重复，因此 search trajectory 不成环；transposition 仅列为 future work | first LFP + MCTS；first grounded reasoning + Monte Carlo search |
| [Synthesizing Recursive Logic Programs by Inverting General Resolution](https://ieeexplore.ieee.org/document/11027907), IEEE Access 2025 | modified MCTS 搜候选 recursive logic-program hypotheses，并以 literal compression/cost 为目标；候选压缩时穷举 general-resolution sentence closure；实验学习 <code>scc(A,B)</code> 关系 | 输入已形式化；不是 MCGS；<code>scc/2</code> 是数据图关系学习 benchmark，不是 predicate-SCC decomposition 或 productive-SCC diagnosis；不做预算化 NL acquisition | first MCTS for recursive logic-program synthesis；first MCTS + deductive closure；first Monte Carlo recursive graph-rule learning |
| [Combining UCT and Nested Monte-Carlo Search for Single-Player General Game Playing](https://www.lamsade.dauphine.fr/~cazenave/papers/ggp2009.pdf), IEEE TCIAIG 2010 | 在 GDL 游戏上使用 UCT 与 transposition table；[GDL 是支持 recursion 等特性的 Datalog variant](https://doi.org/10.1007/s10994-019-05843-w) | 完整 game rules 已知；该实现将 GDL 转为 Prolog，由 Prolog 计算 terminal/legal/next/goal，UCT 搜动作轨迹；并非所有 GGP 实例都使用 recursion | first Datalog/Horn + Monte Carlo search；first transposition-aware Monte Carlo on logic-defined dynamics |
| [Monte Carlo Tree Search for Verifying Reachability in Markov Decision Processes](https://arxiv.org/abs/1809.03299), ISoLA 2018 | MCTS-guided value iteration 做 partial exploration；其 reachability computation 可数学解释为数值 Bellman fixed-point problem，并需构造 MEC quotient 保证收敛 | 不是 least-Herbrand semantics；无 NL、规则获取或 provenance proof | first MCTS-guided numeric fixed-point computation；first Monte Carlo + cyclic Bellman setting |

其中，Qiu & Ichise 2025 是此次补检最重要的新命中。它没有直接覆盖我们的任务，但已经把 modified MCTS、递归逻辑程序、general-resolution deductive closure 与 <code>scc/2</code> 关系学习 benchmark 放在同一篇论文中。它不是 positive-Horn least-Herbrand LFP，也没有做 SCC decomposition；但足以否定宽泛的 “first MCTS for recursive logic programs” 或 “first Monte Carlo reasoning over recursive rules”。

### 4.2 为什么精确的 MCGS 仍可能有空位

本轮仍未找到一个系统同时满足：

1. facts/rules 藏在尚未完整解析的自然语言窗口中；
2. 每次真实 action 都要付出 LLM/semantic parsing 成本；
3. 搜索状态包含已提交程序、program-relative LFP、provenance、coverage 与 remaining budget；
4. 不同读取顺序到达 decision-equivalent state 时才合并；
5. 输出 source-linked proof，并区分 PR-Unknown 与 Unresolved。

这个交集比“LFP + MCGS”窄得多，也更安全。但它的 novelty 来自 **budgeted latent-program acquisition**，不是 seed 或 LFP。

---

## 5. 普通版本周围已经很拥挤

### 5.1 MCGS、状态合并与形式证明

| 工作 | 相关性 | 边界 |
|---|---|---|
| [Monte-Carlo Graph Search: the Value of Merging Similar States](https://proceedings.mlr.press/v129/leurent20a.html), ACML 2020 | 原始 MCGS；合并转置/相似状态；讨论 loop 与 Bellman fixed-point iteration | 不能 claim first fixed-point MCGS 或 first MCGS with loops |
| [Improving AlphaZero Using Monte-Carlo Graph Search](https://ojs.aaai.org/index.php/ICAPS/article/view/15952), ICAPS 2021 | DAG transpositions 与共享 search statistics | 不能把 state sharing 本身当新贡献 |
| [Partially Observable Monte-Carlo Graph Search](https://ojs.aaai.org/index.php/ICAPS/article/view/36129/38283), ICAPS 2025 | 在 belief state 上构造 compact policy graph，处理部分可观测与连续 POMDP | 我们必须严格定义 belief/state key、合法 merge 与 hidden outcome 访问权 |
| [Aristotle: IMO-level Automated Theorem Proving](https://arxiv.org/abs/2510.01346), 2025 technical report | highly parallel MCGS 合并等价 Lean proof states/actions，Lean 验证最终证明 | 不能 claim first MCGS for formal reasoning、first verifier-backed/proof-producing MCGS |
| [HyperTree Proof Search](https://proceedings.neurips.cc/paper_files/paper/2022/hash/a8901c5e85fb8e1823bbf0f755053672-Abstract-Conference.html), NeurIPS 2022 | 在 proof hypertree 上做 neural theorem-proving search，是 Aristotle 的直接 formal-search 前身 | graph/hypertree proof search 本身不是新方向 |
| [Machine Learning Guidance for Connection Tableaux](https://link.springer.com/article/10.1007/s10817-020-09576-7), JAR 2021 | MCTS 搜一阶 theorem-proving derivations | 不能把 Monte Carlo proof search 写成新方向 |
| [LEMUR](https://doi.org/10.1007/s10994-015-5510-3), Machine Learning 2015 | UCT 搜 probabilistic logic-program clause structure | 不是 positive-Horn LFP 或 NL acquisition；但 Monte Carlo logic-program induction 不是新方向 |
| [Provenance-Guided Synthesis of Datalog Programs](https://doi.org/10.1145/3371130), POPL 2020 | why/why-not provenance 驱动 CEGIS 搜 Datalog program | 无 MCTS 或 NL acquisition；但 provenance-guided Datalog program search 已有直接先例 |

### 5.2 有限预算的信息获取

| 工作 | 相关性 | 对我们的要求 |
|---|---|---|
| [TreeSample](https://proceedings.mlr.press/v108/buesing20a.html), AISTATS 2020 | 在昂贵 density-oracle call 有限时，用 MCTS 决定下一次查询，并缓存历史结果 | “预算化昂贵查询 + MCTS”不是 novelty；必须证明 partial-program/provenance/LFP 改变了问题 |
| [Static and Dynamic Values of Computation in MCTS](https://proceedings.mlr.press/v124/sezener20a.html), UAI 2020 | 直接估计一次额外 computation 对最终决策的价值 | 必须加入同等信息与 compute 权限的 one-step/greedy/beam controls |
| [MCTS-RAG](https://aclanthology.org/2025.findings-emnlp.672/), Findings of EMNLP 2025 | MCTS 动态交织 retrieval、decomposition、summary 与 reasoning | 不能把“MC search 决定下一段知识”作为 headline novelty |
| [ReKG-MCTS](https://aclanthology.org/2025.findings-acl.484/), Findings of ACL 2025 | UCB 在 KG 上扩展路径，LLM rollout/value/backprop | “LLM + MCTS + graph reasoning”不是 novelty |

### 5.3 自然语言符号控制

| 工作 | 相关性 | 对我们的要求 |
|---|---|---|
| [SymBa](https://aclanthology.org/2025.naacl-long.124/), NAACL 2025 | symbolic SLD controller 管理 proof process；只有缺信息时才调用 LLM | **最危险的 NLP comparator**；必须比较 official 与 cycle-safe adapted 版本 |
| [Symbolic Working Memory](https://aclanthology.org/2024.emnlp-main.974/), EMNLP 2024 | 外部 symbolic memory、grounding 与逐步 rule implementation | 临时知识库/符号记忆不是 novelty |
| [Logic-LM](https://aclanthology.org/2023.findings-emnlp.248/) 与 [LINC](https://aclanthology.org/2023.emnlp-main.313/), EMNLP 2023 | NL→formal program→solver | Full-Formalize+LFP 是必须击败的最危险全局基线 |
| [FaiRR](https://aclanthology.org/2022.acl-long.77/) 与 [Bi-Chainer](https://aclanthology.org/2024.findings-acl.507/) | faithful rule selection/application、动态双向 chaining | obligation-driven selection 不能只和 Direct/CoT 比 |

普通版若不带 SCC，reviewer 很容易把它概括成：

> TreeSample/MCTS-RAG 式 acquisition policy + SymBa/SWM 式 symbolic controller + 标准 Datalog executor。

所以，单靠模块组合并不足以形成强论文。

---

## 6. SCC 相关先例与真正可守的差异

| 工作 | 已有内容 | 不能声称 | 仍可区分之处 |
|---|---|---|---|
| [SA-MCGS](https://github.com/chenqianwan/SA-MCGS), Paper 1 | AlphaGo-style MCGS、Tarjan SCC、TT、循环文档风险证据搜索 | first MCGS + SCC | Paper 2 改变 state、transition、semantics、output 与 scientific question |
| [Guessing Winning Policies in LTL Synthesis by Semantic Learning](https://link.springer.com/chapter/10.1007/978-3-031-37706-8_20), CAV 2023 | MCTS + SCC decomposition，逆拓扑求解 parity-game regions | first Monte Carlo search with SCCs | 已形式化 game vs. latent NL rules；policy/value vs. grounded closure/proof |
| [Parsel](https://papers.neurips.cc/paper_files/paper/2023/hash/6445dd88ebb9a6a3afa0b126ad87fe41-Abstract-Conference.html), NeurIPS 2023 | SCC-aware mutually recursive function synthesis + tests | first SCC-aware LLM reasoning | 无 MCTS/MCGS、LFP closure 或 provenance |
| [Soufflé Datalog](https://www.souffle-lang.com/pdf/cc.pdf) | predicate SCC、semi-naive delta、fixed-point evaluation；[Magic Sets](https://souffle-lang.github.io/magicset) 做 query-directed rewrite | SCC-wise LFP 不是新算法 | 我们只调度昂贵 NL acquisition；symbolic kernel复用经典方法 |
| [ANN-CMCGS](https://imrclab.github.io/assets/pdf/2026-ann-cmcgs-grc.pdf), AAMAS 2026 extended abstract | MCGS 支持 arbitrary directed graphs with cycles | first cyclic MCGS | motion planning，无逻辑 closure/SCC diagnosis |

### 6.1 SCC 的价值不是“圈出一块图”

SCC 应提供一个独立的、可检验的 interaction：

<div align="center">

Δcycle = (Ours − Baseline)SCC − (Ours − Baseline)DAG

</div>

主正例不能只满足“predicate graph 有环”。必须同时满足：

1. recursive predicate SCC 中存在 grounded feedback-rule instance；
2. 该 instance 产生此前未知的 ground atom；
3. 删除它会减少 query-relevant closure 或改变 query label；
4. matched DAG 控制尽量保持 rule/fact 数、proof depth、fan-in/out、词频与表面长度；
5. unseeded SCC 用来测 circular self-support FPR。

这使 SCC 从工程技巧变为科学变量。

### 6.2 Benchmark 空位的安全表述

不能写“现有自然语言规则 benchmark 都避开 cycle”。[RuleTaker](https://www.ijcai.org/Proceedings/2020/537) / [ProofWriter](https://aclanthology.org/2021.findings-acl.317/) 的 Datalog-style 生成过程允许递归结构；non-archival OpenReview 稿 [t-BEN](https://openreview.net/pdf?id=XkzGgKJAA2) 已设 Recursive DatalogMTL level；[SLR-Bench](https://aclanthology.org/2026.acl-long.16/) 也讨论 recursive complexity，但当前数据主要面向规则归纳，不等于 productive multi-rule LFP recovery。另一方面，[ReEfBench](https://aclanthology.org/2026.acl-long.931/) 的生成器明确避开 cyclic reasoning。

较安全的 gap 是：现有数据很少同时控制 **grounded feedback contribution、外部 seed、minimum saturation rounds、circular self-support、source-linked proof 与 acquisition cost**。我们的贡献不是发现 seeded/unseeded LFP 语义，而是把它变成 noisy NL acquisition 下可配对、可证伪的 failure condition。

---

## 7. 机制交集矩阵

图例：✓ = 核心机制；△ = 部分覆盖或不同语义；— = 不覆盖。

| 工作 | Monte Carlo | 状态合并 | latent NL rule acquisition | positive-Horn LFP recovery | source-linked NL proof | productive SCC diagnosis |
|---|---:|---:|---:|---:|---:|---:|
| Argumentation MCTS 2014 | ✓ | — | — | △ | — | — |
| GDL + UCT/TT 2010 | ✓ | ✓ | — | △ | — | — |
| Qiu & Ichise 2025 | ✓ | — | — | — | — | — |
| TreeSample 2020 | ✓ | — | — | — | — | — |
| SymBa 2025 | — | — | ✓ | △ | ✓ | — |
| Aristotle 2025 | ✓ | ✓ | — | — | — | — |
| SA-MCGS | ✓ | ✓ | △ | — | △ | △ |
| **普通 LFP-MCGS 设想** | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| **SCC-aware LFP-MCGS 主线** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

矩阵说明：我们没有找到完全同列覆盖的已有系统，但每个单列以及多个两两组合都已有成熟先例。因此论文必须用实验说明“交集为何产生了新能力”，不能只靠架构图声称 novelty。

---

## 8. 四张图必须分开

~~~mermaid
flowchart LR
  G0["G₀^ret: text-window retrieval graph<br/>非语义，只定义候选 action"] --> A["MCGS chooses a costly read"]
  A --> P["committed partial program<br/>facts + rules + provenance"]
  P --> C["fixed-program LFP chain<br/>K₀ → K₁ → ... → K*"]
  P --> D["predicate dependency graph<br/>SCC 在这里定义"]
  C --> O["proof obligations / PR status"]
  O --> A
  P -. "不同 action 顺序形成" .-> S["partial-program state poset<br/>仅 decision-equivalent states 可合并"]
~~~

必须避免四种混淆：

1. <code>G₀^ret</code> 的 reference/entity/retrieval edge 不是 formal rule edge，不能在其上声称 semantic SCC；
2. 固定程序的 LFP 是唯一单调链，不是分叉的 closure lattice；
3. 跨读取 action 形成的是 partial-program state poset；
4. 只有 committed F/R/K、belief <code>b_t</code>、ledger、coverage、sample/retry history、可用 actions、provenance、remaining cost 与 outcome-sketch <code>p_φ</code> version 都满足 decision-equivalence 时，MCGS statistics 才能共享。

---

## 9. Claim 边界

### 9.1 明确禁止

- first LFP + MCTS/MCGS；
- first fixed-point MCGS；
- first MCTS for recursive logic programs；
- first Datalog/Horn + Monte Carlo search；
- first MCGS for logical/formal reasoning；
- first verifier-backed or proof-producing MCGS；
- first MCGS + SCC / first cyclic MCGS；
- first Monte Carlo search using SCC decomposition。

### 9.2 正确性红线

即使没有 prior-art 冲突，也不能声称 fixed LLM budget 下的 exact end-to-end LFP recovery，或把 formal proof validity 写成自然语言解析 soundness。所有结论必须带 program-relative 限定。

### 9.3 普通版安全写法

> Prior work has combined Monte Carlo search with grounded argumentation, Datalog-encoded games, recursive logic-program synthesis, expensive oracle allocation, and formal proof search. We found no prior work that uses Monte Carlo graph search to allocate a limited acquisition budget over latent natural-language facts and rules while maintaining a provenance-carrying, program-relative positive-Horn least fixed point.

这句话仍需保留 “we found no prior work”，不能改成无条件 “the first”。

### 9.4 SCC 主线推荐写法

> We study budgeted semantic interpretation for grounded productive recursion: MCGS schedules costly natural-language rule acquisition, while a deterministic provenance-carrying LFP kernel propagates external evidence without allowing a cycle to support itself.

若最终检索与实验均通过，可以再加：

> To our knowledge, this is the first SCC-aware MCGS architecture designed for budgeted recovery of program-relative positive-Horn LFP closure from partially interpreted natural-language rules, with productive predicate-dependency SCCs as a controlled reasoning regime.

这里的限定词不能删：**SCC-aware、budgeted、program-relative、positive-Horn、partially interpreted natural-language rules、productive predicate-dependency SCCs**。

### 9.5 输出语义

- <code>PR-Entailed</code>：相对于 committed program 有 verifier-valid proof；
- <code>PR-Contradicted</code>：相对于 committed program 可推出显式 complement；
- <code>PR-Unknown</code>：当前 committed program 已饱和且预注册 coverage protocol 完成；
- <code>Unresolved</code>：预算或覆盖不足。

只有 gold-parse/oracle track 才能把前三者称为对 gold program 的 certified 结论。End-to-end track 不能排除 parser false negative 或 validator false reject。

---

## 10. 文献检索直接导出的 baseline 要求

### 10.1 普通版本的最低合格线

1. Gold semi-naive / Soufflé 与 Magic Sets；
2. Full-Formalize+LFP；
3. Extract-All-Local+LFP；
4. official SymBa；
5. authors’ cycle-safe Tabled-SymBa；
6. Static/Demand、Greedy、outcome-sketch Greedy 与 Beam；
7. TreeMCTS-LFP；
8. LFP-MCGS；
9. Aristotle 只作 related-work 边界，不要求任务不兼容的硬复现。

内部 scheduler controls 必须共享同一 retrieval graph、local parser、schema、validator、LFP、cache 与 proof assembler；使用 outcome-sketch 的方法还必须共享同一个模型与 compute cap。

### 10.2 决策门槛

| 结果 | 论文定位 |
|---|---|
| DAG 与 SCC 都有效，且 Δcycle 显著为正 | 一般 budgeted program acquisition；SCC 为核心 stress test |
| 只有 SCC 有效 | 直接以 grounded productive recursion 为主问题；当前最推荐 |
| DAG 有效，但没有 SCC-specific interaction | 删除 cycle headline，改成 selective semantic interpretation |
| Greedy/Beam/SymBa 与 MCGS 持平 | 删除 MCGS 主贡献，采用更简单的 symbolic scheduler |
| 完整程序已知时仍把 MCGS 当 LFP evaluator | 研究问题设定错误；改用 semi-naive/Magic Sets |
| 所有设置都无显著 accuracy–cost 优势 | NO-GO |

---

## 11. Related Work 建议结构

1. **Exact LFP and query-directed Datalog**：semi-naive、SCC-wise evaluation、Magic Sets、tabling；
2. **Monte Carlo search with logic/fixed-point semantics**：argumentation MCTS、GDL/GGP、Qiu & Ichise、MDP reachability；
3. **MCGS and formal search**：original MCGS、AlphaZero MCGS、POMCGS、Aristotle；
4. **Budgeted information acquisition**：TreeSample、value of computation、MCTS-RAG；
5. **Neuro-symbolic natural-language controllers**：Logic-LM、LINC、SWM、SymBa、FaiRR、Bi-Chainer；
6. **SCC-aware reasoning/search**：SA-MCGS、CAV 2023、Parsel、Soufflé；
7. **Productive recursion benchmark gap**：seed、feedback contribution、saturation rounds、circular self-support。

---

## 12. 立项结论

### 普通 seeded LFP-MCGS

**可以做，但不能靠“LFP + MCGS”本身投稿。** 精确同构工作尚未找到；然而它位于 MCTS acquisition、neuro-symbolic controller、formal proof search 与标准 Datalog evaluation 的拥挤交叉处。若没有 SCC-specific failure 或非常强的 accuracy–cost Pareto，它容易被评价为工程拼装。

### SCC-aware LFP-MCGS

**建议保留为主线。** 它不是简单“再给 SA-MCGS 加一个 SCC 模块”，而是利用 SCC 定义新的语义失效：

- 外部 seed 进入 recursive region 后，证据会通过 feedback 多轮传播；
- 没有 seed 的循环不能自我产生事实；
- noisy local parsing 容易同时造成 propagation miss 与 circular-support false positive；
- MCGS 的价值可由 SCC-vs-DAG interaction、merge rate、proof validity 与 token Pareto 证伪。

最终定位应是：

> **方法面向全图，科学问题聚焦 productive recursive SCC。**
>
> 普通 seed/DAG 证明 generality；SCC 证明为什么需要 LFP-aware MCGS。

---

## 13. 投稿前最后复核

- 对 Qiu & Ichise 2025、Riveret et al. 2014、Aristotle 2025、SymBa 2025 做前向/反向引文扫描；
- 检查 2026 年 8 月之后的 ARR、ACL、EMNLP、NeurIPS、ICLR 新稿；
- 继续检索 GDL/GGP、probabilistic logic-program induction、argumentation 与 theorem-proving 社区，而不只检索 ACL；
- 在正文中区分 Bellman fixed point、grounded-extension LFP 与 least-Herbrand LFP；
- 最终 claim 使用 “to our knowledge / no prior work we found”，并保留全部任务限定；
- 方法名称固定为 **LFP-MCGS**，避免 GFP 被理解为 greatest fixed point。

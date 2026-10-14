# LFP-MCGS：文献、新颖性与受控注入依据

> 更新：2026-08-19<br>
> 口径：检索概念等价工作，不以 “LFP-MCGS” 名称是否被占用判断 novelty。

## 0. 结论

尚未检索到完整同构系统同时做到：

```text
真实 cyclic document graph
+ local-window LLM acquisition
+ SA-MCGS / PUCT 与严格状态合并
+ source-validated partial Horn KB
+ predicate-SCC incremental least-Herbrand LFP
+ closure/provenance obligations 反馈下一轮搜索
```

但其中任何单项都不是新的。安全的新颖性口径只能是**这条闭环的特定耦合**，并且必须由交互消融证明，不是把几个已有组件并列起来。

数据方面，沿用 SA-MCGS 的受控注入是合理的：真实 document SCC 作为冻结载体，现有窗口中做最小、可解释、成对的语义干预，再用独立 LFP 引擎给出 exact gold。文献支持它作为 capability-focused stress test，但不支持把它写成自然分布估计。

---

## 1. 方法新颖性边界

| 近邻 | 已覆盖的能力 | 与本文的硬区别 | 不能 claim |
|---|---|---|---|
| [SA-MCGS](https://github.com/chenqianwan/SA-MCGS) | 真实循环文档、local windows、PUCT/MCGS、结构注入风险 | 无 committed Horn program、exact LFP、closure provenance | SCC-aware MCGS 本身是新的 |
| [Self-Correcting RAG](https://aclanthology.org/2026.findings-acl.1052/) | MCTS/PUCT 中继续生成或检索，用 NLI evidence feedback 修正 | tree state 是文本答案/文档；无 SCC、Horn KB、exact closure 与 state merge | 首次 evidence-guided PUCT 或在线 retrieval |
| [MCTS-RAG](https://aclanthology.org/2025.findings-emnlp.672/) | MCTS 动态交织分解、检索与回答 | 自然语言轨迹树；没有 committed program 和 LFP | 首次 Monte Carlo retrieval-reasoning |
| [PRISM-MCTS](https://aclanthology.org/2026.findings-acl.807/) | 在 MCTS 分支间共享启发式/失败文本记忆 | 仍是 tree；不合并决策等价知识状态，不执行 closure | 首次跨 rollout 信息共享 |
| [SymBa](https://aclanthology.org/2025.naacl-long.124/) | SLD solver 按 proof obligation 让 LLM 从原文补事实/规则 | 全文可见、top-down SLD；无收费窗口、document SCC、MCGS merge | 首次 solver-guided LLM acquisition |
| [Symbolic Working Memory](https://aclanthology.org/2024.emnlp-main.974/) | 持久 facts/rules 与迭代 symbolic memory | 没有 SCC-local exact LFP 和 Monte Carlo graph planning | 首次 persistent symbolic memory |
| [Soufflé](https://www.souffle-lang.com/pdf/cc.pdf) / [BigDatalog](https://doi.org/10.1145/2882903.2915229) | 已知 Datalog 程序的 SCC-wise semi-naive fixed point | 程序完整给定，不做自然语言证据获取 | LFP 执行本身或 SCC 优化是新的 |
| [Qiu & Ichise 2025](https://doi.org/10.1109/ACCESS.2025.3577238) | PUCT 搜 recursive logic program，并算 deductive closure | 搜 formal program hypothesis，不读 source windows；不是严格 MCGS | 首次 Monte Carlo + recursive closure |
| [ProSynth](https://popl20.sigplan.org/details/POPL-2020-Research-Papers/47/Provenance-Guided-Synthesis-of-Datalog-Programs) | why/why-not provenance 反馈程序搜索 | CEGIS/SAT 程序合成；无 NL、SCC document search 或 LLM | 首次 provenance-guided search |

安全表述：

> To our knowledge, prior work has not coupled cyclic-document SA-MCGS with source-validated partial Horn programs, online predicate-SCC least-Herbrand closure, and provenance-aware closure obligations under decision-equivalent graph-state sharing.

这句话也必须由 `online vs end-only LFP`、`memory-only`、`TreeMCTS`、`Greedy/Beam` 与强 retrieval/search agent 实验支撑。

---

## 2. 为什么人工注入有文献基础

### 2.1 最相关 primary literature

| 工作 | 原文给出的原则 | 对本项目的具体启发 | 它不能替我们证明什么 |
|---|---|---|---|
| [Contrast Sets](https://aclanthology.org/2020.findings-emnlp.117/) | 对原测试例做小而有意义、通常改变标签的人工扰动，观察局部决策边界 | 同一真实 SCC 生成 productive 与近邻 controls；除目标变量外尽量保持不变 | 不能说明扰动在自然分布中的频率 |
| [Counterfactually-Augmented Data](https://openreview.net/forum?id=Sklgs0NFvr) | 改到目标标签、保持内部连贯、避免不必要修改 | 注入必须是最小、可读且由领域模板约束，不重写整份文档 | 不能自动排除新的词面 shortcut |
| [CAD limitation](https://aclanthology.org/2022.acl-long.256/) | 缺少干预多样性会漏学稳健特征，甚至强化原有伪相关 | seed/bridge/witness 的位置、实体、模板和措辞必须轮换；按模板 family 做 held-out split | 少量固定模板不能支持 OOD 泛化 claim |
| [RobustLR](https://aclanthology.org/2022.emnlp-main.653/) | 用最小逻辑编辑和逻辑等价条件诊断推理稳健性 | decoy seed、broken bridge、等价 paraphrase 与 polarity/guard edits 必须成套出现 | RobustLR 自身不是 cyclic document search |
| [WIQA](https://aclanthology.org/D19-1629/) | 在过程影响图上构造 what-if intervention，并区分相关与无关影响 | productive、inactive 与外部/无关干预应分开；gold 由结构化影响规则复核 | 影响图不等于 Horn document SCC |
| [MuSiQue](https://aclanthology.org/2022.tacl-1.31/) | 组合多步问题，同时过滤能靠 disconnected reasoning 解出的样本 | 必须做单窗口不足、leave-one-source-out 与最小来源覆盖检查 | 多跳组合本身不证明 recursion 或 MCGS 必要 |
| [ProofWriter](https://aclanthology.org/2021.findings-acl.317/) | 自然语言规则、可执行 implication 与显式 proof | 用独立 executor 生成 closure、逐轮 proof 与 Unknown controls | 模板逻辑数据不能代替真实文本自然性 |

这些工作共同支持的是：

> **在真实载体附近做最小、成对、能力导向的结构语义干预，并由独立形式系统验证标签。**

它们不支持“人工注入就等于真实法律风险”。

### 2.2 为什么要保留 SA-MCGS 风格

SA-MCGS 已形成一套可解释的受控协议：从真实 SCC 选择相距较远的 root、bridge、witness，在现有记录上追加少量领域化内容，保留真实拓扑和大部分原文。Paper 2 应继承这套原则，而不是重新生成一张 canonical cycle。

对应关系：

| SA-MCGS 注入 | Paper 2 注入 |
|---|---|
| root 风险线索 | grounded seed fact |
| bridge | 中间 Horn rule / guard |
| distant witness | query-critical rule 或 fact |
| critical-pair revisit | proof-obligation revisit |
| 风险端点 gold | exact closure + source-linked proof gold |

Paper 2 更强的地方是：每个结论、每轮 closure、每个必要来源都能由 executor 重算，而不是只标一个风险端点。

### 2.3 DOMINANT / CoLA 的位置

[DOMINANT](https://doi.org/10.1137/1.9781611975673.67)、[CoLA](https://doi.org/10.1109/TNNLS.2021.3068344) 等图异常工作可以作为 Paper 1 使用过的**历史结构注入依据**：它们说明在真实图上受控构造异常是常见评测手段。但它们不处理自然语言证据、最小语义编辑、多来源 sufficiency、LFP 或 proof provenance。

因此 Paper 2 的注入正当性不能主要靠 DOMINANT/CoLA；主引用应是 Contrast Sets、CAD、RobustLR、WIQA、MuSiQue 与 ProofWriter。

---

## 3. 文献导出的数据协议

### 3.1 冻结载体，最小改变语义

```text
真实 SCC：节点、边、source ID、原文主体冻结
干预窗口：seed + 1..k bridges + witness
其他窗口：保持原样，或只加入成对且不影响 gold 的 no-op paraphrase
```

不能让注入创建 SCC；论文写成“在既有 SCC 中注入 distributed proof obligation”。

### 3.2 每个 family 的必要条件

1. `Productive`：所有指定来源联合后 query 可证；
2. `Decoy`：最小 seed/guard 编辑后不可证；
3. `Broken/Inactive`：缺桥或环与 query 无关；
4. `Clean`：原始 SCC，无注入；
5. `Matched-DAG`：匹配长度、规则数、深度、标签与表面统计，只移除反馈结构。

### 3.3 防 shortcut

- seed、bridge、witness 位置随机轮换；
- 实体、谓词、模板按 family 切分；
- 正负条件使用相同提示词、句长和标点分布；
- 训练/开发/测试不共享模板骨架与 SCC topology hash；
- 做 injection-only classifier：只给单窗口或只给新增 span，性能应接近机会水平；
- 做盲审：标注者不知道 condition，检查可读性、领域一致性和单窗口可解性；
- clean SCC 与 no-op paraphrase 单列误报率。

### 3.4 Exact oracle

每个 case 发布：

- initial facts、rules 和 query；
- 完整 LFP 与 saturation rounds；
- 每个 atom 的 proof parents 与 source spans；
- minimum acquisition cover；
- 删除任一必要 source 后的 closure/query 变化；
- case family、carrier SCC、所有注入 span、模板与随机种子。

被测 LLM 不参与 gold 生成；形式 gold 与语言自然性由不同流程验证。

---

## 4. 从 AC/SAC 视角看的 claim

### 可以写

- 一个在真实 document SCC 上受控测试 distributed proof recovery 的 benchmark；
- LFP closure 作为跨局部读取的知识状态与后续 PUCT 反馈；
- 相比 matched-compute 通用 LLM 和现有 search agents，在长 SCC 上更好的 proof-valid accuracy–cost Pareto；
- 对 committed program 可验证、对原文有 source spans 的 proof；
- 人工注入与真实无注入外测分层报告。

### 不要写

- 首次 MCTS/MCGS + RAG；
- 首次跨 rollout memory；
- 首次 solver-guided LLM acquisition；
- 首次 Monte Carlo + fixed point；
- 人工注入代表自然法律风险分布；
- citation cycle 天然等于 semantic recursion；
- positive-Horn closure 能撤销既有事实；
- 只因 TreeMCTS 在大图崩溃就证明本文方法优越。

---

## 5. 最终判断

这条路线有 NAACL/ACL 价值，但论文成色由四个问题决定：

1. 强通用 LLM 在 `7–20` 节点 SCC 上是否真的出现 proof-recovery gap；
2. online closure feedback 是否胜过 end-only LFP 与 memory-only；
3. SCC 上的收益是否显著大于 carefully matched DAG；
4. held-out templates、clean SCC 和少量真实无注入案例是否排除了注入 shortcut。

若四项都成立，论文不是“SA-MCGS 加一个 solver”，而是一种被受控实验验证的 source-grounded slow-thinking architecture。若只在固定模板上胜 TreeMCTS，则最多是 synthetic mechanism result，不能支撑主会故事。

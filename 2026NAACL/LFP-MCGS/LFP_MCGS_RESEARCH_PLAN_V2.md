# LFP-MCGS 研究计划 V2

> 工作标题：**Closing the Loop: Source-Grounded Slow Reasoning over Cyclic Documents**<br>
> 状态：决策版 V2.2（2026-08-19）。本文是唯一当前执行口径；旧初稿与 V1–V3 只作历史诊断。<br>
> 目标：2026 年 10 月 ARR；venue 与日期以 [ARR 官方页面](https://aclrollingreview.org/dates) 为准。

---

## 0. 一页结论

**继续做，先走与 SA-MCGS 一致的人工注入版本。**

Paper 2 继承 SA-MCGS 已验证的三项基础：

1. 真实 document SCC，而不是为了实验临时生成一张图；
2. LLM 每次只看一个局部窗口，由 PUCT/MCGS 决定下一步读哪里；
3. 用更多 test-time compute 换取长循环中的慢思考。

新的部分是把 SA-MCGS 的局部风险窗口替换为可执行的知识状态：

```text
真实 document SCC
  → PUCT 选择一个局部窗口
  → 通用 LLM 提出 fact / Horn rule + source span
  → validator 决定是否提交
  → committed KB 上增量 LFP
  → Δclosure / provenance / proof obligation
  → 反馈下一轮 PUCT
  → answer + source-linked proof
```

核心机制集采用 **topology-controlled SCC intervention**：冻结真实 SCC 的节点、边和绝大多数原文，只在现有窗口中最小注入 `seed / bridge / witness`，使任一窗口单独都不足，跨窗口组合后才由 LFP 推出查询。

本文不把贡献写成“用 MCGS 加速 LFP”。已知程序上的 LFP 很便宜；困难是**程序碎片藏在长循环文档中，而且读取昂贵、局部、可能出错**。

### 0.1 论文主问题

> 在真实循环文档图中，相比一次性或通用慢思考 LLM，能否用 SCC-aware PUCT 逐步读取局部证据，并让 source-grounded LFP closure 改变后续搜索，从而以更少成本恢复可验证证明？

### 0.2 只承诺什么

| 承诺 | 不承诺 |
|---|---|
| finite、function-free、positive-Horn LFP | 任意法律逻辑、缺省逻辑、时态与例外 |
| 相对于 committed program 的 exact closure / proof | LLM 对原文抽取天然全局 sound |
| 受控注入下的机制因果证据 | 人工注入代表自然风险分布 |
| 真实 SCC 上的 local-window slow reasoning | “有环就一定需要 MCGS” |
| matched-compute 下与强通用 LLM 比较 | 只打败一个弱 prompt 就宣称成功 |

Positive Horn 的知识只会增加，不能撤回已经成立的事实。因此主任务是 `Unresolved → Entailed/Unknown` 的证据恢复；如需研究冲突，只能让显式 `q` 与 `not_q` 都被推出并标为 `Conflict`，不能称作 LFP “强撤回”了旧结论。

---

## 1. 与 SA-MCGS 保持一致，但不是重复 Paper 1

### 1.1 继承关系

| 维度 | SA-MCGS | LFP-MCGS |
|---|---|---|
| 载体 | 真实循环文档图 | 同类真实循环文档图 |
| 读取 | LLM 局部窗口 | LLM 局部窗口 |
| 调度 | SCC-aware PUCT / MCGS | 同一搜索骨架，value 加入 closure progress |
| 跨轮记忆 | 局部风险、critical pair | committed facts/rules、closure、provenance、obligations |
| 重新访问 | 风险对与动态 core | 新 atom、缺失前提和 proof frontier |
| 输出 | 风险子图 | 答案、query-relevant closure、source-linked proof |

一句话：

> **SA-MCGS 在真实 SCC 中注入“远处信息合起来才形成风险”；Paper 2 在真实 SCC 中注入“远处证明碎片合起来，经过 LFP 才形成证明”。**

Paper 1 的具体注入代码已经采用 root / bridge / witness 位置和真实窗口追加文本；Paper 2 沿用其“真实载体 + 最小结构语义干预 + 可解释 gold”的原则，但把 gold 从风险端点升级为可执行闭包与逐步 provenance。

### 1.2 必须是新的部分

- source-span anchored candidate ledger 与 fail-closed commit；
- committed partial Horn program；
- SCC-local incremental LFP 与逐轮 provenance；
- closure delta / missing premise 对下一轮 PUCT 的反馈；
- 按完整知识状态做 decision-equivalent merge；
- proof-valid answer、coverage-aware Unknown 与预算不足时的 `Unresolved`。

如果真实 `Δclosure` 没有进入后续选择，方法只是“最后跑一次 solver”；如果 exact merge 没有命中或关闭后无差异，就不把 MCGS 写成核心贡献。

---

## 2. 方法边界

### 2.1 LFP 内核

给定已验证事实 `F̂` 与 positive-Horn rules `R̂`：

\[
K_0=\hat F,\qquad K_{i+1}=K_i\cup T_{\hat R}(K_i),\qquad
K^*=\operatorname{lfp}_{\hat R}(\hat F).
\]

每个查询状态至少包含：

```text
S_t = {
  committed facts / rules,
  exact closure and provenance,
  missing proof obligations,
  read windows and remaining actions,
  token/call/time budget,
  MCGS visit/value statistics
}
```

三张图不能混写：

| 图 | 含义 |
|---|---|
| document graph | 真实文档引用、依赖或关系边；它的 SCC 定义读取空间 |
| predicate dependency graph | 已提交 Horn rules 的语义依赖；LFP 在其递归分量内饱和 |
| search-state graph | 不同读取顺序到达同一决策等价状态后共享统计 |

### 2.2 一次安全迭代

1. PUCT 在当前 document SCC 的未读窗口中选择 action；
2. LLM 只读取该窗口和允许的局部上下文，提出 facts/rules 与逐条 source span；
3. validator 检查 schema、实体绑定、方向、span 支持与重复冲突；
4. 只有真实执行且验证通过的结果进入 committed KB；
5. incremental LFP 只处理新提交造成的 delta，并保存每个 atom 的来源链；
6. 新 atom、关闭/打开的 obligation 与 query progress 更新下一轮 prior/value；
7. 达到可验证 proof 后停止；覆盖不足或预算耗尽则返回 `Unresolved`。

安全线：simulation 可以读取 committed-state snapshot 并保留 branch-local 假设，但不能把 speculative parse 或 speculative closure 写入全局 KB。若 outcome model 在 simulation 中读取尚未真实执行的窗口，其 calls、tokens 与 latency 同样计入预算，并向所有 control 开放同等权限；只有 root action 的真实结果可以 commit。共享状态至少要同时匹配 committed program、closure、coverage/action mask 和剩余预算；只按 closure 合并是不安全的。

### 2.3 最小不变量

- `F̂_t ⊆ F̂_{t+1}`、`R̂_t ⊆ R̂_{t+1}`、`K_t ⊆ K_{t+1}`；
- 每次 commit 后 `K_t = lfp_{R̂_t}(F̂_t)`；
- 每个派生 atom 都能回溯到输入窗口中的有限 source spans；
- 无 seed 的 `a→b, b→a` 不推出任何新 atom；
- 未读窗口的 parse、gold 与 answer 对 policy 不可见；
- 预算耗尽但必要 source 未覆盖时只能返回 `Unresolved`。

---

## 3. 核心机制集：Topology-Controlled SCC Intervention

### 3.1 生成原则

每个案例先从真实 document graph 选择一个 SCC，再做以下受控处理：

1. **冻结拓扑：**不新增、删除或重连节点与边；保留原始窗口和来源标识；
2. **最小注入：**只在现有窗口中追加领域化短句，分别承担 seed、一个或多个 bridge、distant witness；
3. **分散必要性：**任一单窗口、任一单次 acquisition 都不能直接推出 query；
4. **闭包必要性：**只有合并多个窗口后，LFP 才产生 query-critical atom；若注入程序本身含 predicate recursion，另行记录其 predicate-SCC 与饱和轮数，绝不把 document SCC 当作 semantic SCC；
5. **可执行 gold：**独立 LFP 引擎生成逐轮 closure、proof DAG、最小来源集和 leave-one-source-out 结果；
6. **表面自然性：**模板由领域术语与原窗口实体实例化，并做盲审；不让被测 LLM 生成标签。

注入位置不能永远固定在“末尾”或某个度数区间；seed、bridge、witness 的位置、实体和表达模板必须在 family 层轮换，避免位置和词面 shortcut。

### 3.2 每个 SCC 的五联组

| 条件 | 只改变什么 | Gold 作用 |
|---|---|---|
| `Productive` | 正确 seed + bridges + witness | LFP 可推出 query；所有指定来源联合必要 |
| `Decoy` | seed 的实体、guard 或极性做最小替换 | 环存在但不能启动目标 closure |
| `Broken / Inactive` | 缺一条必要 bridge，或环与 query 无关 | 测 false positive 与盲目循环追踪 |
| `Clean` | 不做语义注入，保持原始 SCC | 测注入痕迹、自然噪声与误报 |
| `Matched-DAG` | 另行构造物理 document-topology 对照；保持窗口、事实/规则、proof depth 与标签一致，只打断 document feedback edge | 隔离 document-SCC effect；它不属于前四个“冻结 SCC 拓扑”的语义干预 |

成对样本必须留在同一 split；统计单位是 `SCC family`，不是把同一 family 的多个 query 当独立样本。

### 3.3 长度与难度轴

主规模固定为：

```text
SCC nodes = 3 / 5 / 7 / 9 / 12 / 16 / 20
```

节点数与 proof-carrying window 数分开报告。小环 `3–5` 用于调通；`7–9` 开始检验普通 LLM 全局扫描是否退化；`12–20` 检验慢思考的成本—准确率曲线。还要分别控制：

- 最小来源覆盖数；
- LFP saturation rounds；
- distractor ratio；
- witness 与 seed 的 document distance；
- SCC density 与重复路径数；
- 表面长度和实体频率。

### 3.4 人工注入的 claim 边界

它可以证明：

- 多个局部读取是否必须组合；
- online closure feedback 是否帮助找齐远端证据；
- 无 seed 的环是否会被错误自证；
- 优势是否随 SCC 长度、证据距离和预算增长。

它不能证明：

- 这种模式在真实法律/合同中的自然发生频率；
- 注入文本与自然风险分布等价；
- 对任意非单调法律推理都有效。

因此主文必须称 **controlled structural stress test**。另设不注入的真实 SCC 外测，二者分表，不混成一个总体准确率。

---

## 4. 数据证据栈

| 层 | 数据角色 | 回答的问题 |
|---|---|---|
| P0 · 核心机制 | SA-MCGS 管线中的真实 BGB/QuantLaw、Debian、SEC/CUAD document SCC，经审计后做五联组干预 | 长 SCC 中分散证明、closure feedback 与慢思考是否成立 |
| P1 · 真实无注入 | 法律真实 SCC 子集、AOP-Wiki/SIGNOR 等有来源 feedback case；以可审计样本为准 | 方法能否离开模板；不估计自然总体分布 |
| P1 · symbolic safety | ProofWriter strict-positive、RobustLR-style logical edits | LFP、provenance、seeded/unseeded invariant 是否正确 |
| P2 · 无环组合控制 | MuSiQue、ProofWriter/CLUTRR/StepGame 中的 matched DAG 或多跳切片 | 收益是否只是普通多跳证据组合 |

Paper 1 的真实 SCC 是核心载体；旧 injected-risk label 不直接复用为 Paper 2 gold。Paper 2 为同一载体建立新的 proof-level intervention 和 exact oracle。

现有第三轮审计仍有价值：ProofWriter strict-positive 已确认 `2,778` 个 ground-instance-causal theories / `24,169` 个 queries，CLUTRR、StepGame 与 SpaRTUN/SpaRP 可作 closure/executor sanity；但这些数字不再定义主实验方向。

---

## 5. Baseline：主问题是慢思考，不是 Tree 对 Graph 的表演赛

### 5.1 主 baseline

所有内部对照优先共享同一 base LLM，并按实际 input/output tokens、calls、wall time 与并行度做 matched compute：

1. `Direct / one-shot audit`：把允许的完整输入一次交给通用 LLM；
2. `CoT / strong reasoning setting`：同模型的主流长思考设置；
3. `Self-Consistency / Best-of-N`：把同等额外计算只用于重复采样；
4. `ReAct / search-agent baseline`：允许按相同次数读取局部窗口，但没有 structured LFP state；
5. `Self-Correcting RAG` 或等价强在线检索—修正方法；
6. `SA-MCGS memory-only`：沿用 Paper 1 搜索，但不提交 Horn KB；
7. `Extract-All + exact LFP`：读取所有窗口后一次性求解，给出高成本上界。

这个梯子直接回答：相较第一代“一次扫完”和现有通用慢思考，把时间花在 SCC-aware、closure-guided search 上是否更值。

### 5.2 机制控制

| 控制 | 唯一差别 | 说明 |
|---|---|---|
| Greedy / Beam | 不做 Monte Carlo rollout | 检验复杂规划是否必要 |
| end-only LFP | closure 不反馈下一步 | 检验 LFP 是否只是后处理 |
| memory-only | 记文本摘要，不执行规则 | 检验收益是否来自任意跨轮记忆 |
| TreeMCTS | 关闭 exact state merge | **只做 merge 消融，不是主 baseline** |
| matched-DAG | 单独打断物理 document feedback edge，保持同一程序与 proof | 检验 document-SCC-specific interaction；不冒充 predicate-recursion 消融 |
| gold parser / gold graph | oracle diagnostic | 定位 parser、retrieval 和 search 各自瓶颈 |

SymBa、PRISM-MCTS、MCTS-RAG / Self-Correcting RAG 是必须正面讨论的近邻；对齐不了输入/输出接口时单列 method-native 结果，不能用不公平 adapter 机械记错。

---

## 6. 实验与指标

### 6.1 四组主实验

| 实验 | 核心问题 | 主要比较 |
|---|---|---|
| E0 · Oracle safety | 数据和 LFP gold 是否完全正确 | 两个独立 executor、leave-one-source-out、unseeded controls |
| E1 · Strong-LLM gap | 长 SCC 是否真的需要 structured slow thinking | Direct/CoT/Best-of-N/ReAct vs LFP-MCGS，按 size 与 budget 分层 |
| E2 · Mechanism | 哪个组件带来收益 | online vs end-only LFP、memory-only、Greedy/Beam、TreeMCTS、matched-DAG |
| E3 · External validity | 模板外是否保留方向一致的收益 | clean SCC、真实无注入 case、held-out templates/entities/domains |

### 6.2 主指标

- Proof-Verified Answer Accuracy；
- query-relevant closure precision / recall / F1；
- source-set sufficiency 与 minimum acquisition cover；
- leave-one-required-source-out failure rate；
- circular self-support false-positive rate；
- tokens、calls、wall time、unique windows 与 time-to-first-valid-proof；
- accuracy–cost Pareto；
- `method × SCC-size`、`method × topology`、`method × model` interaction。

主图应直接显示从 `3 → 20` 节点时：通用 LLM 是否先退化、LFP-MCGS 是否用更多时间保住 proof-valid accuracy。不要只报一个总体平均数。

### 6.3 必做消融

- `– committed symbolic KB`；
- `online LFP → end-only LFP`；
- `– provenance / source anchor`；
- `– closure-delta feedback`；
- `– proof-obligation priority`；
- `– SCC-aware prior`；
- `– exact state merging`（即 TreeMCTS）；
- rollout depth 与预算敏感性。

---

## 7. 历史实验：保留数字，但不当作当前方法证据

| 历史阶段 | 已观察结果 | 当前解释 |
|---|---|---|
| SA-MCGS 消融 | 去 critical-pair revisit `−21.3`；random local window `−11.3`；去 OC/core `−10.0`；monotone core `−25.0`；去 final pair closure `−2.5`；去 relation memory 反而 `+5.0` | 说明 revisit、结构窗口和动态 core 值得继承；relation-first memory 不应照搬 |
| V1 gold replay | @`2×MAC`：ProofWriter dynamic frontier `15.0%`，StepGame `96.7%`；closure-signature compression `83.6%` | 证明数据/closure 管线有信号；未运行 LLM 或 MCTS/MCGS |
| V2 local-LLM smoke | LFP-MCGS 与 TreeMCTS 都是 `11/12`；MCGS 节点少 `22.7%` | 只证明集成与 abstract merge；没有算法准确率优势，也不是当前 persistent-KB 架构 |
| V3 synthetic scaling | canonical Tree/MCGS recovery 相同；overlay 节点约省 `17%`，但 recovery AUC 略低 | 证明压力存在、优势未成立；synthetic graph 不能代表真实 document SCC |

这些数字保留用于解释为什么路线转向真实 SCC + strong-LLM gap + controlled intervention。不得把它们放进摘要或主结果表。

---

## 8. Go / No-Go

### GO

- 五联组经独立 executor 100% 通过，任何必要 source 删除后 query 不再可证；
- 在至少两个强模型上，LFP-MCGS 的 proof-valid accuracy–cost Pareto 优于 Direct/CoT/Best-of-N 与强 search agent；
- 优势从 `7–9` 节点开始随 SCC size 或 evidence distance 显著放大；
- online LFP 明显优于 end-only LFP，说明 closure 真正反馈了搜索；
- clean/decoy/inactive controls 的 circular-support FPR 足够低；
- 至少一个无注入真实子集方向一致，但只作 external validity。

### 简化或停止 MCGS headline

- 强通用 LLM 一次全局扫描在 `9–20` 节点仍稳定秒解；
- Greedy/Beam 与 LFP-MCGS 同成本持平；
- online LFP 与 end-only LFP 无差别；
- TreeMCTS 与 MCGS 持平且 exact merge 极少；
- 收益只来自固定模板、位置词或 oracle 图；
- 自然 clean SCC 上误报高；
- positive-Horn 任务被错误包装成非单调“强推翻”。

---

## 9. 六周执行顺序

| 周 | 交付 |
|---|---|
| W1 | 从 SA-MCGS 图提取 SCC size `3/5/7/9/12/16/20`；冻结 carrier、source window 和 split |
| W2 | 实现五联组 intervention、双 executor、provenance 与 leave-one-source-out 验证；人工盲审模板 |
| W3 | 接入 SA-MCGS local-window PUCT；实现 committed KB、incremental LFP 和安全 branch/root commit |
| W4 | 跑强 LLM baseline 与 Greedy/Beam/end-only/Tree 消融；先做 `3–9` 节点 Gate |
| W5 | 扩到 `12–20`、两个模型、三个 seeds；冻结主结果和成本账本 |
| W6 | clean/真实无注入外测、错误分析、人审与从零复现 |

先完成 injection smoke，再扩大真实数据集。若 W4 看不到 clear slow-thinking gap，不用更多 API 预算掩盖问题。

---

## 10. 投稿前清单

- [ ] 主文明确真实 SCC 是载体，人工干预只改现有窗口；
- [ ] 每例有 `Productive / Decoy / Broken-or-Inactive / Clean / Matched-DAG`；
- [ ] 节点、边、原始窗口、注入 span、模板、实体和随机种子全部可追溯；
- [ ] exact LFP、逐轮 provenance、最小来源集和 deletion oracle 由独立程序复核；
- [ ] 主 baseline 是 matched-compute 强通用 LLM；TreeMCTS 只做 merge 消融；
- [ ] internal methods 共享相同 base LLM、窗口访问权和总成本核算；
- [ ] simulation 不污染共享 committed KB；
- [ ] controlled、clean 与 natural external results 分表；
- [ ] 不声称人工注入代表自然分布；
- [ ] 不把 positive Horn 写成撤回式 strong overturn；
- [ ] 所有历史 V1–V3 数字标成 exploratory diagnostic；
- [ ] 发布 split manifest、构建脚本、oracle、prompt、raw outputs、cost ledger 与 license 记录。

---

## 11. 最终 Pitch

> Existing LLMs can scan a short document once, but long cyclic documents require repeated local decisions about what to read and which fragments jointly support a conclusion. LFP-MCGS retains SA-MCGS's cyclic local-window search, commits only source-validated Horn fragments, and feeds exact least-fixed-point progress back into subsequent PUCT. A topology-controlled intervention benchmark tests this mechanism on real document SCCs without allowing a cycle to prove itself.

最重要的一句话：

> **我们不是让 LFP 替 LLM 算一个已知程序；我们让 LFP 把 LLM 多次局部读取获得的证明碎片变成下一步慢思考的知识状态。**

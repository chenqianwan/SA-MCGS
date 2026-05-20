# SA-MCGS Paper Framework

> 工作方式：这个文件是论文写作的总框架。先在这里把主线、章节、图表、实验口径和 reviewer 风险改顺，再同步到 `paper/latex/acl_latex.tex`。

## 0. 一张框架图

```text
Problem
  One-shot LLMs can inspect long records, but cyclic structures make risk evidence
  diffuse, revisitable, and easy to lose.

  Standard MCTS is not a clean escape hatch: in SCCs, rollout paths can revisit
  the same records indefinitely, so the search tree expands path copies instead
  of concentrating evidence.

        long interdependent records
                  |
                  v
        directed dependency graph
                  |
                  v
        SCC detection: find cyclic reasoning bottlenecks
                  |
       +----------+--------------------------+
       |                                     |
       v                                     v
  DAG region                           SCC bottleneck
  normal MCTS path                     SA-MCGS path
                                            |
                                            v
  +----------------------------------------------------------------+
  | SA-MCGS                                                        |
  |                                                                |
  |  C1. SCC-aware search engine                                   |
  |      local window rollout + transposition memory + SCC-UCB      |
  |  C2. Online conformal evaluator                                |
  |      OC / structural evidence calibration                       |
  |  C3. Pluggable domain adapters                                 |
  |      domain rubric + pruning / saliency hooks                   |
  |  Dynamic core risk-subgraph compression                         |
  +----------------------------------------------------------------+
                  |
                  v
        collapsed risk subgraph / evaluation point
                  |
                  v
Claim
  SA-MCGS turns a cyclic document region into a compact, interpretable,
  high-recall risk subgraph more reliably than full-SCC one-shot prompting.
```

## 1. 当前论文主张

**一句话主张：**  
SA-MCGS 不是简单让 LLM “多想几次”，而是把长环 SCC 这种会阻断 MCTS/LLM 推理的结构瓶颈，转化为可搜索、可收敛、可压缩的风险子图。

**更正式的 claim：**

1. 复杂文档中的结构性风险往往不是单节点文本异常，而是跨节点约束在 SCC 中互相作用后产生。
2. Full-SCC one-shot baseline 能看到部分风险，但在长合同、长环、输出负担和多证据保留上不稳定。
3. 直接在完整合同或完整 SCC 上跑普通 MCTS 会被环结构膨胀：搜索树复制路径、rollout 被截断、Q 值被稀释。
4. SA-MCGS 通过 SCC-aware 搜索、conformal 评价和可插拔领域适配器，把 SCC 压缩成更可靠的风险子图/评估点。
5. 论文主指标不是单点 Top-1，而是 `Root@3 + Risk-any + Risk-all + Compression`。

## 2. 三项核心贡献

这三项贡献要在 Introduction 和 Method 中反复保持一致，避免 paper 看起来像一组临时工程技巧。

| Contribution | 中文定位 | 要解决的问题 | 论文中怎么写 |
|---|---|---|---|
| C1: SCC-aware Monte Carlo Graph Search | SCC 感知搜索引擎 | 普通 MCTS 在 SCC 中路径无界、树膨胀、Q 值稀释 | 用 Tarjan 找 SCC，对 SCC 内部做局部窗口 rollout、转置记忆、SCC-aware selection，并把 SCC 输出为风险子图节点 |
| C2: Online conformal evaluator | 在线 conformal 评价 | 局部窗口风险分数不稳定，单次判断容易受噪声影响 | 把 OC 作为结构证据发现信号和 rollout 收敛分析，不把 Effective OC 当主指标 |
| C3: Pluggable domain adapters | 可插拔领域适配器 | 不同领域的 record/edge/风险语义不同，但主算法不能写死领域规则 | 领域适配器只提供通用风险 rubric、edge saliency、剪枝/格式化 hooks；主搜索逻辑保持领域无关 |

**贡献 3 的最新说法：**  
不要再写成固定的“剪枝策略”。现在更准确的是 **pluggable domain adapters**：领域相关的信息通过 adapter 注入，但 Naive 和 SA-MCGS 共享同类风险语义，差异来自搜索/压缩机制。

## 3. 关键消融：为什么不能直接在完整合同上跑 MCTS

这组消融是 Introduction / Method motivation 的核心，不只是 appendix 小实验。

**逻辑链：**

1. AlphaGo/MCTS 风格搜索适合探索结构化推理空间。
2. 但真实文档图中存在 SCC；SCC 使 rollout path length unbounded。
3. 普通 TreeMCTS 在 SCC 中会复制同一物理节点的不同路径分身，导致搜索树膨胀。
4. 因此不能把完整合同直接交给 MCTS；必须先定位 SCC，再把 SCC 作为一个 bottleneck 单元处理。
5. SA-MCGS 的作用就是把 SCC 内部探索压缩成一个 risk subgraph / evaluation point，使上层图搜索可以继续。

**旧 demo 中可转化为论文表格的 ablation 数字：**

| Setting | Topology | Expansion | Truncation | Q-spread | Hit@3 |
|---|---|---:|---:|---:|---:|
| TreeMCTS | DAG | 2.3x | 0% | 0.077 | 7% |
| TreeMCTS | Cycle | 6.4x | 100% | 0.044 | 30% |
| SA-MCGS | Cycle | 1.0x | N/A | 0.371 | 90% |

真实 CUAD AzulSa 13-node SCC 中，TreeMCTS 的 Q-spread 只有 `0.058`，SA-MCGS 为 `0.800`。这说明环上普通 MCTS 不是“多跑一点就好”，而是会把风险信号平均掉。

## 4. 泛化领域：为什么选择这四个数据集

这部分需要在 Experiments 前后都出现一次：Introduction 中用一句话说明覆盖面，Experimental Setup 中用表格解释权威性和结构差异。

**一句话版本：**  
我们选择 Debian、SEC EX-21、BGB 和 CUAD，不是为了堆数据集数量，而是为了覆盖四类真实结构风险场景：软件依赖、监管披露、成文法引用、商业合同条款；它们分别代表不同的文本噪声、图结构来源和领域权威性。

| Domain | 权威来源 | 为什么适合结构风险 | 泛化价值 |
|---|---|---|---|
| Debian | Debian Policy / official package metadata | Debian 明确定义 `Depends`、`Pre-Depends`、`Conflicts`、`Breaks` 等包关系，是大规模真实依赖图 | 非法律技术域；验证 SA-MCGS 不是只对法律文本有效 |
| SEC EX-21 | SEC EDGAR / Regulation S-K Item 601(b)(21) | EX-21 要求上市公司披露 subsidiaries、jurisdiction、business names，是真实公司实体/控制关系图 | 监管披露域；结构风险来自 ownership / consolidation / subsidiary chains |
| BGB | German Civil Code, official Federal Ministry of Justice / Gesetze im Internet | BGB 是权威成文法，条文之间存在稳定引用和条件依赖，噪声低 | 干净法律域；适合证明方法在高权威、低噪声法条图上有效 |
| CUAD | Contract Understanding Atticus Dataset, NeurIPS Datasets & Benchmarks 2021 | 510 commercial contracts、13,000+ expert labels、41 clause types，文本长且噪声高 | 商业合同域；最贴近真实合同审查，测试 one-shot 输出负担和长文本鲁棒性 |

**覆盖矩阵：**

| 维度 | Debian | SEC EX-21 | BGB | CUAD |
|---|---|---|---|---|
| Legal / non-legal | non-legal | regulatory/legal | statutory legal | private contract legal |
| Text noise | low-medium | medium | low | high |
| Graph source | package metadata | public filings | statute references | contract cross-references |
| Authority | official project policy/data | SEC filings/rules | official law | expert benchmark |
| Role in paper | cross-domain generality | entity/control graph | clean legal control | hardest long-contract stress |

**写作重点：**

- Debian 是“出圈”泛化：证明算法处理的是结构风险，不是法律关键词。
- SEC EX-21 是监管实体图：证明方法能处理 ownership / subsidiary 这类公司结构。
- BGB 是干净权威法条图：如果这里也有效，说明方法不是只在噪声里找异常。
- CUAD 是高噪声长合同：最能说明 Naive full-SCC one-shot 的输出负担和风险端点保留问题。

**可引用来源：**

- Debian Policy Manual, Section 7: declaring relationships between packages.
- SEC FAST Act final rule / Regulation S-K Item 601(b)(21): subsidiaries of registrant.
- German Civil Code BGB, official English translation hosted by Gesetze im Internet / Federal Ministry of Justice.
- The Atticus Project CUAD page and CUAD paper: 510 contracts, 13,000+ labels, 41 clause types, NeurIPS Datasets and Benchmarks.

## 5. 论文结构草案

### Abstract

需要包含：

- 问题：LLM 在长循环依赖结构中丢失或稀释风险证据。
- 方法：SCC detection + SCC-aware rollout + conformal evidence + pluggable domain adapters + dynamic risk core。
- 数据：4 authority-backed domains、4 models、80 critical SCC blocks per model。
- 结果：SA-MCGS strict `Root@3 81% / Risk-any 98% / Risk-all 78%`，Naive 为 `48% / 72% / 47%`；代价是 compression 从 `67%` 降到 `53%`。
- 解释：更高风险保留率以较小压缩率牺牲换来。

### 1. Introduction

目标：把故事讲清楚，不要一上来堆算法。

建议段落：

1. **Motivating Problem**  
   长合同、法规、依赖链、公司结构不是线性文本，而是互相引用/约束的图。风险常常来自两个或多个看似合理节点的组合。

2. **Why Standard MCTS Is Not Enough**  
   直接把完整合同交给 MCTS 会在 SCC 里膨胀：路径可无限重复，树节点是物理节点的路径复制，Q 值被稀释。

3. **Why One-shot LLM Is Not Enough**  
   One-shot 可以识别明显高风险点，但在 SCC 中会遇到长上下文记忆、风险扩散、输出负担和多端点保留不稳定。

4. **Our Solution**  
   SA-MCGS 先定位 SCC，然后在 SCC 内做局部 rollout，把风险证据持续写入 relation-first memory，最后用 dynamic core 把 SCC 坍缩为风险子图/评估点。

5. **Contributions**
   - 提出结构性风险子图任务，而不是单点异常检测。
   - 提出 SA-MCGS 的三项组件：SCC-aware search engine、online conformal evaluator、pluggable domain adapters。
   - 构造 structural critical stress benchmark，覆盖软件依赖、监管披露、成文法和商业合同四类权威数据源。
   - 在 4 models × 4 domains × 80 cases 上验证，包含 fairness、error handling、compression trade-off、rollout convergence。

### 2. Structural Risk Subgraph Extraction

需要明确 reviewer 最可能问的问题：

- 什么是 record graph？
- 什么是 SCC？
- 什么是 structural risk？
- root / witness / affected 分别是什么意思？
- 为什么 risk-all 重要？

建议定义：

- `G = (V, E)`：records and directed dependencies。
- `S ⊆ V`：一个 SCC。
- `R = {root, witness, affected...}`：注入后形成风险的 evidence set。
- 输出：`H ⊆ S`，一个 risk subgraph。

指标：

- `Root@3`：GT/root 是否进入 top-3。
- `Risk-any`：子图是否包含至少一个可修复风险入口。
- `Risk-all`：子图是否完整保留核心风险端点。
- `Compression`：`1 - |H| / |S|`。
- `Effective OC`：只作为发现/收敛辅助，不作为主指标。

### 3. Method: SA-MCGS

建议结构：

1. **Graph Construction and SCC Localization**  
   先把文档/依赖关系变成图，再用 Tarjan 找 SCC。DAG 区域可以继续作为普通上层搜索对象；SCC 区域进入 SA-MCGS。

2. **C1: SCC-aware Local Rollout Search**  
   每次只看一个局部窗口，用统一 risk rubric 评价风险，并用转置记忆/SCC-aware selection 避免环上重复路径膨胀。

3. **Relation-first Evidence Memory**  
   不是只记“某个节点天然危险”，而是记“某个节点在已有证据关系下变得危险”。

4. **C2: OC / Conformal Signal**  
   OC 不是最终指标，而是结构性证据触发器，用来提示某个局部窗口发现了互相不兼容或高风险关系。

5. **Dynamic Core Risk Subgraph**  
   风险子图不是只增不减，而是随着 rollout 替换、收敛、压缩。

6. **C3: Pluggable Domain Adapters**  
   Debian、SEC、BGB、CUAD 的文本格式和边语义不同；adapter 负责 record formatting、risk rubric hooks、edge saliency/pruning hints，但不改变主搜索算法。

7. **Complexity / Cost Discussion**  
   SA-MCGS 调用更多 LLM，但每次窗口更小、输出更短，且稳定性更高。

### 4. Experimental Setup

主实验必须只写这个口径：

```text
profile: current/default
inject profile version: structural_simple_v2
severity: critical
domains: Debian, SEC EX-21, BGB, CUAD
models: gpt-4o, deepseek-v3, qwen2.5-72b, gemini-2.5-pro
cases: 80 SCC blocks per model
methods: Naive direct-subgraph vs SA-MCGS
SA budget: 60 rollouts
```

Baseline fairness 要写：

- Naive 不是弱 baseline：它直接看完整 SCC，并直接输出 risk subgraph。
- SA-MCGS 和 Naive 使用同一类通用风险语义，不使用领域专用找错 prompt。
- 报错计入 strict denominator。

### 5. Main Results

主表：

| Metric | Naive | SA-MCGS |
|---|---:|---:|
| Root@3 | 48% | 81% |
| Risk-any | 72% | 98% |
| Risk-all | 47% | 78% |
| Compression | 67% | 53% |
| Errors | 59/320 | 0/320 |

核心解释：

- SA-MCGS 在三个识别指标上都明显更好。
- Compression 较低不是失败，而是用更大的 core 换取更完整的风险保留。
- Risk-all 提升最关键，因为 critical structural risk 需要同时保留多个端点。

### 6. Analysis

建议分成四个短小但有力的小节：

1. **By SCC Size**  
   重点写长环趋势：long `>=24` 中 SA 仍保持优势，但 Risk-all 更难。

2. **Convergence with Rollouts**  
   用 E2 图说明 rollout 增加带来 risk coverage / risk-all 上升。  
   注意：`effective_oc_discovered` 是 cumulative discovery，不要当主指标。

3. **Error Handling and Output Burden**  
   用 E0/E1：Naive 报错不是被忽略；轻量版能降错，但仍不能追上 SA 的完整风险保留。

4. **Compression Trade-off**  
   用 E3：balanced 更压缩，但 Risk-all 掉；current/default 是主实验，因为 critical 风险下保留更重要。

### 7. Case Study

至少两个 case：

1. BGB 长环：法规文本更干净，适合展示 SA 如何收敛到 root+witness。
2. CUAD 长合同：原生噪声高，适合展示 one-shot 输出负担和 SA 的局部搜索稳定性。

每个 case 需要：

- SCC size。
- root/witness/affected。
- Naive 输出。
- SA-MCGS core。
- 为什么 SA 的 core 更可解释。

### 8. Limitations

需要主动写，不要躲：

- SA-MCGS 成本更高。
- Risk-all 很严格，在高噪声合同中仍可能失败。
- 注入式 benchmark 不是自然发生的全部风险。
- 当前 graph construction 质量会影响 SCC 和搜索质量。
- Human audit E4 需要作为最终补充。

### 9. Conclusion

收束到一句：

SA-MCGS 把“长环结构中的风险识别”从 one-shot 文本判断，转化为 SCC 内的可搜索、可收敛、可压缩的风险子图抽取问题。

## 6. 图表清单

主文建议放：

1. **Figure 1: SA-MCGS pipeline**  
   Document graph → Tarjan SCC → SCC-aware rollout → evidence memory → dynamic core → collapsed risk subgraph。

2. **Table 1: Why standard MCTS fails on SCCs**  
   TreeMCTS DAG vs TreeMCTS cycle vs SA-MCGS cycle：Expansion / Truncation / Q-spread / Hit@3。

3. **Table 2: Domain coverage and authority**  
   Debian / SEC EX-21 / BGB / CUAD 的来源、结构类型、噪声水平、泛化角色。

4. **Table 3: Main results**  
   Root@3 / Risk-any / Risk-all / Compression / Errors。

5. **Figure 2: Metrics by SCC size**  
   使用 `main_by_scc_size`。

6. **Figure 3: Rollout convergence**  
   使用 E2 convergence 图。

7. **Table 4: Error and valid-only analysis**  
   使用 E0，可能放 appendix 也可以。

8. **Table/Figure: Naive output-burden control**  
   使用 E1，建议 appendix 或 analysis 小表。

9. **Figure: Compression profile trade-off**  
   使用 E3，证明 current/default 选择不是 cherry-pick。

## 7. Reviewer 风险清单

### Q1. Baseline 是否太弱？

答法：

- Naive 不是只输出单点 rank，而是 direct-subgraph baseline。
- Naive 看完整 SCC，信息量上反而更强。
- E1 说明即使减轻输出 schema，Naive 在 CUAD 长 SCC 上仍有明显限制。

### Q2. Prompt 是否公平？

答法：

- 使用通用 risk rubric。
- 不使用领域专门找错词。
- 差异是 full-SCC one-shot vs local rollout search，不是评价标准不同。

### Q3. 数据是不是 cherry-pick？

答法：

- 主实验文件级锁定：`current/default + critical + 80 cases x 4 models`。
- 所有报错计入 strict denominator。
- balanced / diagnostic / smoke 都标为补充或探索，不混入主表。

### Q3b. 四个数据集是否足够泛化？

答法：

- 四个域按结构来源选择，不按结果好坏选择。
- Debian 是非法律软件依赖图，SEC 是监管实体披露图，BGB 是权威成文法图，CUAD 是专家标注商业合同图。
- 这覆盖了 clean vs noisy、legal vs non-legal、statutory vs private contract、structured metadata vs long natural language。

### Q4. Compression 变低是否说明 SA 不够好？

答法：

- critical risk 里完整保留风险端点优先级高于极致压缩。
- SA 以约 14pt compression 代价，换来 Risk-all 31pt 提升。
- E3 表明过强压缩会伤 Risk-all。

### Q5. 为什么不用 Effective OC 做主指标？

答法：

- Effective OC 是 cumulative discovery signal，适合说明 rollout 探索过程。
- 主指标仍是最终子图是否保留风险：Risk-any / Risk-all / Compression。

## 8. 下一步写作顺序

1. 先改 Abstract + Introduction。
2. 写 MCTS-on-SCC failure 消融和动机，把“为什么不直接全合同 MCTS”说清楚。
3. 写 domain generalization / dataset authority 表，解释为什么是四个域。
4. 再写 Structural Risk Subgraph Extraction，把指标定义钉死。
5. 写 Method，按 C1/C2/C3 三项贡献组织。
6. 写 Experiments + Main Results。
7. 写 Analysis 和 Limitations。
8. 最后同步到 LaTeX，并插入图表。

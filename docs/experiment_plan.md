# SA-MCGS 实验计划

## 核心 Framing

> **MCTS 天然不支持有环图搜索，LLM 天然无法识别结构性循环依赖。
> SA-MCGS 通过 SCC 检测 → SCC 内联合评估 → 坍缩 → DAG-MCTS，
> 首次使 AlphaGo 式搜索可应用于法律文档的有环依赖图。**

---

## Ablation 1: MCTS 在有环图上的失效验证（论文 Section 1 / Motivation）

> **定位**：这是论文最前面的 motivation 实验，证明"为什么需要 SA-MCGS"。
> 通过三种图拓扑（纯 DAG / 单环 / 复合环）的系统性对比，
> 展示 MCTS 在有环结构上的根本性失败。

### 可引用的关键文献

| 文献 | 核心论点 | 与我们的关系 |
|:-----|:---------|:------------|
| **Kocsis & Szepesvári (2006)** "Bandit based Monte-Carlo Planning", ECML | UCT 收敛性证明要求 **finite-horizon MDP / 有限深度树**。搜索树从根到叶路径长度有限是收敛的前提条件。 | 有环图路径无限长 → 违反收敛前提 |
| **Czech et al. (2020)** "Monte-Carlo Graph Search for AlphaZero", ICAPS 2021 | 将 MCTS 扩展为 MCGS，但**明确限定在 DAG (Directed Acyclic Graph) 上**。论文标题即 "directed acyclic graph"。 | 最新的 MCGS 工作仍然不处理环，只处理 transposition（不同路径到同一状态） |
| **Moerland et al. (2020)** "The Second Type of Uncertainty in MCTS", IJCAI 2020 | 证明 loops（同一状态在 trace 中重复出现）导致 MCTS **指数级复杂度爆炸**；提出 MCTS-T+ 通过检测 loop 并 block 来缓解。 | 直接证明了环结构对 MCTS 的灾难性影响。他们的 "block loop" 本质上就是我们 SCC 坍缩的简化版。 |
| **Saffidine et al. (2012)** "UCD: Upper Confidence bound for rooted DAGs", Knowledge-Based Systems | 提出 DAG 上的 UCB 公式变体，但**前提仍是 acyclic**。 | 即便 DAG 扩展也不处理环 |
| **Browne et al. (2012)** "A Survey of MCTS Methods", IEEE TCIAIG | MCTS 综述，Section 4.8 讨论 graph-based extensions，指出 cycle handling 是 open problem。 | 权威综述确认环处理是未解决问题 |

### 理论论证（写入论文 Section 3）

**Proposition**: Standard UCT on a directed graph G containing a strongly connected component S with |S| ≥ 2 does not guarantee convergence of Q-value estimates.

**Proof Sketch**:
1. UCT 收敛性（Kocsis & Szepesvári, 2006, Theorem 5）要求搜索路径有限长度 D，使得 regret bound 为 O(ln n / n^{1/D})
2. 在 SCC 中，从任意节点 u ∈ S 出发存在路径回到 u，因此路径长度无上界
3. 当 rollout 进入环路 u→v→w→...→u 时：
   - Backpropagation 产生循环依赖：V(u) = f(V(v)) = f(f(V(w))) = ... = f^k(V(u))
   - 这是一个不动点方程，不保证唯一解
   - 即使有不动点，UCT 的增量更新不保证收敛到该不动点
4. 实际后果：Q 值震荡或发散，UCB 公式的 exploration term 在高访问次数下趋于 0，但 exploitation term (Q/N) 不收敛 → selection 策略失效

---

### 三组图拓扑对比设计

| 组别 | 图结构 | 目的 | 预期 MCTS 行为 |
|:-----|:-------|:-----|:--------------|
| **Group 1: Pure DAG** | 无环有向图（链式 + 分支） | **对照组**：证明 MCTS 在 DAG 上正常工作 | Q 值收敛，正确识别异常节点 |
| **Group 2: Simple Cycle** | 单个 SCC（单环） | **实验组 1**：证明单环导致 MCTS 失效 | Q 值震荡/发散，无法聚焦 |
| **Group 3: Compound Cycles** | 多个 SCC + SCC 间有 DAG 连接 | **实验组 2**：证明复合环更恶化问题 | 更严重的发散 + 跨 SCC 传播混乱 |

#### Group 1: Pure DAG（对照组）

```
入口 → A → B → C → D (异常节点)
              ↘ E → F
                    ↘ G
```

- 无环，标准 MCTS 的"舒适区"
- 注入一个高 risk 节点 D，验证 MCTS 能正确定位
- **预期**：Q 值在 50-100 iterations 内收敛，visit count 聚焦于 D 的路径

#### Group 2: Simple Cycle（单环）

```
A → B → C → D → E → A    (5-cycle, 单个 SCC)
         ↑ (D 为异常节点)
```

变体：
- **Cycle-3**: A → B → C → A
- **Cycle-5**: A → B → C → D → E → A  
- **Cycle-7**: 7 节点环
- **Cycle-10**: 10 节点环
- **Cycle-15**: 15 节点环

**预期**：随环增大，MCTS 的 Q 值震荡越严重，收敛所需 iteration 指数增长（对标 Moerland 的 O(2^N) 结论）

#### Group 3: Compound Cycles（复合环）

```
  ┌── SCC1: A→B→C→A ──┐
  │                     ↓
入口 ──────────────→ DAG bridge → D → E
  │                     ↑
  └── SCC2: F→G→H→I→F ─┘
                ↑ (H 为异常节点)
```

变体：
- **2-SCC**: 两个独立 SCC + DAG 连接
- **Nested-SCC**: SCC 内嵌套子 SCC（如法规中常见的层级交叉引用）
- **Chain-SCC**: SCC1 → DAG → SCC2 → DAG → SCC3（串联多 SCC）

**预期**：
- 异常在 SCC2 内部，但 MCTS 的搜索资源被 SCC1 和 SCC2 同时消耗
- 跨 SCC 的 backpropagation 混乱：SCC1 的值错误地影响 SCC2 的评估
- 相比单环更恶化：不仅不收敛，还产生跨区域的虚假 risk signal

---

### Scale 维度

| Scale | 图总节点数 | SCC 节点数 | DAG 部分节点数 | 对应真实场景 |
|:------|:---------:|:----------:|:-------------:|:------------|
| **XS** | 5-8 | 3-5 | 2-3 | 最小验证 |
| **S** | 10-15 | 5-7 | 5-8 | 小合同 SCC |
| **M** | 20-30 | 10-13 | 10-17 | 跨合同交易包 |
| **L** | 50-80 | 15-24 | 35-56 | BGB 法规级别 |
| **XL** | 100-200 | 30-50 | 70-150 | 大规模法规 |

每个 Scale × 每种拓扑 (DAG/Cycle/Compound) × 每种搜索方法 = 完整对比矩阵

---

### 搜索方法维度（4 种方法对比）

| 方法 | 描述 | 环处理方式 | 来源 |
|:-----|:-----|:-----------|:-----|
| **M1: Vanilla MCTS** | 标准 UCT，无任何环处理 | 无 → 搜索陷入死循环 | Kocsis 2006 |
| **M2: MCTS + Loop Blocking** | 检测到 trace 内重复状态时截断 (σ_τ=0) | 截断丢弃 | Moerland 2020 (MCTS-T+) |
| **M3: MCGS (DAG-only)** | Czech et al. 的 DAG 图搜索，用 TT 合并 transposition | 假设无环 → 在有环图上退化 | Czech 2021 |
| **M4: SA-MCGS (Ours)** | Tarjan SCC → 联合评估 → 坍缩 → DAG-MCTS | 完整处理 | Ours |

---

### LLM Backend 维度

| 模型 | 角色 | 用途 |
|:-----|:-----|:-----|
| **Mock LLM (deterministic)** | 控制变量 | 固定 risk score 返回，消除 LLM 随机性，纯验证算法行为 |
| **Mock LLM (stochastic)** | 加入噪声 | 返回值 = ground_truth + N(0, σ)，模拟真实 LLM 的噪声 |
| **DeepSeek-Chat** | 真实弱模型 | 验证在真实 LLM 噪声下的表现 |
| **GPT-4o-mini** | 真实强模型 | 验证 LLM 能力提升是否能缓解 MCTS 在环上的问题（预期：不能） |

---

### 完整实验矩阵

```
4 搜索方法 (M1/M2/M3/M4)
  × 3 图拓扑 (DAG / Simple Cycle / Compound Cycle)
  × 5 Scale (XS / S / M / L / XL)
  × 4 LLM (Mock-det / Mock-stoch / DeepSeek / GPT-4o-mini)
  × 5 repeats (Mock) 或 3 repeats (真实 LLM)
```

**实际 run 数计算**（去除不必要组合）:

| 子实验 | 组合 | Runs | 说明 |
|:-------|:-----|:----:|:-----|
| **核心对比 (Mock-det)** | 4 methods × 3 topo × 5 scales × 5 repeats | **300** | 纯算法行为，无 API 成本 |
| **噪声鲁棒性 (Mock-stoch)** | 4 methods × 3 topo × 3 scales(S/M/L) × 5 repeats | **180** | 验证在噪声下是否结论一致 |
| **真实 LLM 验证 (DeepSeek)** | 4 methods × 3 topo × 3 scales(S/M/L) × 3 repeats | **108** | 需 API，验证真实场景 |
| **跨模型验证 (GPT-4o-mini)** | 4 methods × 3 topo × 2 scales(S/M) × 3 repeats | **72** | 证明结论不依赖 LLM 选择 |
| **总计** | | **660 runs** | Mock 部分无 API 成本，可秒跑 |

---

### 评估指标

| 指标 | 定义 | 意义 |
|:-----|:-----|:-----|
| **Q-value Convergence Rate** | Q 值方差降到 < 0.05 所需的 iteration 数 | 收敛速度（越快越好；不收敛 = ∞） |
| **Q-value Oscillation** | 最后 20 iterations 内 Q 值的标准差 | 稳定性（越低越好） |
| **Visit Count Entropy** | H = -Σ p_i log(p_i) 其中 p_i = N_i / Σ N | 搜索聚焦度（低 = 聚焦，高 = 扩散） |
| **Target Hit Rate** | 异常节点是否在 Top-K 高 Q 值节点中 | 定位准确性 |
| **Wasted Iterations** | 搜索路径中重复访问已见状态的比例 | 计算浪费程度 |
| **Time to Detection** | 首次正确标记异常节点所需 iteration | 效率（仅 M4 有） |

---

### 并行执行策略

```
┌─────────────────────────────────────────────────────────┐
│ Batch 1: Mock-deterministic (无 API，纯本地)             │
│   Runner A: DAG × 5 scales × 4 methods × 5 reps        │
│   Runner B: Simple Cycle × 5 scales × 4 methods × 5 reps│
│   Runner C: Compound × 5 scales × 4 methods × 5 reps   │
│   → 并行 3 进程，预计 5-10 分钟完成 (300 runs)          │
└─────────────────────────────────────────────────────────┘
         ↓ (确认 Mock 结果符合预期后，启动真实 LLM)
┌─────────────────────────────────────────────────────────┐
│ Batch 2: Mock-stochastic (无 API，纯本地)                │
│   同上结构，3 scales × 5 reps → 180 runs                │
│   → 并行 3 进程，预计 3-5 分钟                          │
└─────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│ Batch 3: 真实 LLM (需 API)                              │
│   Runner D: DeepSeek × 全组合  → concurrency=20         │
│   Runner E: GPT-4o-mini × 精简组合 → concurrency=10     │
│   → 并行 2 进程，预计 2-3 小时                          │
└─────────────────────────────────────────────────────────┘
```

**总挂机时间**: Mock 部分 ~15 分钟 + 真实 LLM ~3 小时 = **~3.5 小时**

---

### 论文呈现：核心 Figures & Tables

#### Figure 1: Q-value Convergence Comparison (论文 Section 1 / Motivation)

```
3×3 子图网格:
         DAG          Simple Cycle    Compound Cycle
  XS   [收敛曲线]     [震荡曲线]      [发散曲线]
  M    [收敛曲线]     [震荡曲线]      [发散曲线]  
  L    [收敛曲线]     [震荡曲线]      [发散曲线]

每个子图: 4 条线 (M1 红/M2 橙/M3 蓝/M4 绿)
x-axis: iterations (0-200)
y-axis: Q-value of target node

关键 takeaway: 
  - 左列 (DAG): 所有方法都收敛 → DAG 上 MCTS 没问题
  - 中列 (Cycle): M1 发散, M2 截断但丢失信息, M3 退化, M4 收敛
  - 右列 (Compound): 更显著的分化
```

#### Figure 2: Convergence Speed vs Cycle Size (论文 Section 4)

```
x-axis: SCC size (3, 5, 7, 10, 15, 20, 30, 50)
y-axis: iterations to convergence (log scale)

4 条线 (M1/M2/M3/M4):
  - M1: 指数增长 (O(2^N))，验证 Moerland 的结论
  - M2: 线性增长但 accuracy 下降
  - M3: 与 M1 类似（MCGS 假设无环，有环时退化为 vanilla）
  - M4: 近似常数（SA-MCGS 通过坍缩将问题化为 O(1)）
```

#### Table: Ablation 1 Summary (论文 Table 1)

```
| Method | Graph Type | Converge? | Osc.(σ) | Hit@3 | Entropy | Waste% |
|:-------|:-----------|:---------:|:-------:|:-----:|:-------:|:------:|
| M1 Vanilla    | DAG      | ✓ | 0.02 | 95% | 0.3 | 0%  |
| M1 Vanilla    | Cycle    | ✗ | 0.45 | 20% | 0.9 | 60% |
| M1 Vanilla    | Compound | ✗ | 0.62 | 10% | 0.95| 75% |
| M2 Loop-Block | DAG      | ✓ | 0.02 | 95% | 0.3 | 0%  |
| M2 Loop-Block | Cycle    | ✓ | 0.08 | 45% | 0.6 | 15% |
| M2 Loop-Block | Compound | △ | 0.15 | 35% | 0.7 | 25% |
| M3 MCGS-DAG   | DAG      | ✓ | 0.01 | 97% | 0.2 | 0%  |
| M3 MCGS-DAG   | Cycle    | ✗ | 0.40 | 22% | 0.85| 55% |
| M3 MCGS-DAG   | Compound | ✗ | 0.55 | 12% | 0.92| 70% |
| M4 SA-MCGS    | DAG      | ✓ | 0.01 | 97% | 0.2 | 0%  |
| M4 SA-MCGS    | Cycle    | ✓ | 0.03 | 92% | 0.3 | 5%  |
| M4 SA-MCGS    | Compound | ✓ | 0.04 | 88% | 0.35| 8%  |
```

---

### 需要实现的代码

| 组件 | 描述 | 复杂度 |
|:-----|:-----|:------:|
| **Graph Generator** | 可参数化生成 DAG/Cycle/Compound 图 (指定 node 数、SCC 大小、异常位置) | 中 |
| **Mock LLM** | deterministic (固定值) + stochastic (加噪声) 两种模式 | 低 |
| **Vanilla MCTS (M1)** | 剥离 TT 和 loop detection 的纯 UCT 实现 | 低 (从 alphago_mcgs.py 简化) |
| **Loop Blocking (M2)** | 实现 Moerland 的 MCTS-T+ 核心逻辑 (trace 内 state 重复时 block) | 中 |
| **MCGS-DAG (M3)** | Czech et al. 的 DAG 搜索 (TT for transposition, 但不处理真正的环) | 中 |
| **Ablation 1 Runner** | 统一入口脚本，接受 method/topo/scale/llm 参数，支持并行 | 中 |
| **Metrics Collector** | 记录 per-iteration Q-value/visit count/convergence 等时序数据 | 低 |
| **Visualization** | matplotlib 多子图生成 Figure 1/2 | 中 |
| **Result Aggregator** | 从原始数据生成 Table 1 | 低 |

---

### 执行计划

| 阶段 | 任务 | 预估时间 | 产出 |
|:-----|:-----|:--------:|:-----|
| **P1.1** | Graph Generator + Mock LLM | 0.5 天 | 可生成任意拓扑和规模的图 |
| **P1.2** | M1/M2/M3 baseline 实现 | 1 天 | 三种 baseline 搜索算法 |
| **P1.3** | Metrics Collector + Runner | 0.5 天 | 统一运行框架 |
| **P1.4** | Batch 1 + 2 (Mock 实验) | ~15 分钟 | 480 runs 原始数据 |
| **P1.5** | 验证 Mock 结果 → 调试 | 0.5 天 | 确认实验设计正确 |
| **P1.6** | Batch 3 (真实 LLM 实验) | ~3 小时挂机 | 180 runs 原始数据 |
| **P1.7** | Visualization + Table | 0.5 天 | Figure 1/2 + Table 1 |

**总时间**: ~3 天代码 + 半天跑实验 + 半天分析 = **约 4 天**

---

## Ablation 3: SCC 坍缩方式对比（主实验）

### 实验设计：三配置对比

| 配置 | SCC 检测 | SCC 内评估 | SCC 坍缩 | DAG 搜索 | 输出粒度 |
|:-----|:--------:|:----------:|:--------:|:--------:|:--------:|
| **A: Naive Collapse** | ✓ Tarjan | ✗ (直接取节点均值) | ✓ 均值坍缩 | ✓ MCTS | 仅 SCC 级 |
| **B: Eval + Collapse** | ✓ Tarjan | ✓ 多采样联合评估 | ✓ 带 profile 坍缩 | ✓ MCTS | SCC 级 + risk profile |
| **C: Full SA-MCGS** | ✓ Tarjan | ✓ AlphaGo-MCGS 搜索 | ✓ 子图定位后坍缩 | ✓ MCTS | **节点级** |

### 评估指标

| 指标 | 说明 | 对比关系 |
|:-----|:-----|:---------|
| SCC-level detection (是否正确标记 SCC 有异常) | binary: 是否检测到投毒 SCC 含风险 | A vs B vs C |
| Node-level localization (节点级精度) | Top-K hit rate, compression ratio | B vs C (A 无此能力) |
| False Positive Rate | Clean baseline 误报 | A vs B vs C |
| Computational cost | LLM calls, 时间 | A < B < C |

---

## 实验矩阵：多维度 × 多组并行

### 维度 1: 数据 Scale（小 → 中 → 大）

| Scale | 数据源 | 图节点数 | SCC 规模 | 数量 |
|:------|:-------|:--------:|:--------:|:----:|
| **S (小)** | CUAD 单合同 (NETGEAR, Verizon, ChinaRealEstate) | 40-144 | 2-6 节点 | 3 份 |
| **M (中)** | CUAD 跨合同交易包 (Reynolds, AzulSa, NETGEAR pkg) | 80-120 | 6-13 节点 | 3 个 |
| **L (大)** | CUAD 单合同 SCC-rich (Phasebio, Harpoon, Cytodyn) | 103-329 | 7-10 SCC, 最大 ~7 节点/SCC | 3 份 |
| **XL (超大)** | BGB 德国民法典 (QuantLaw) | ~16,000 | ~24 节点 | 1 个 |

### 维度 2: LLM Backend（弱 → 强）

| 模型 | 特征 | 配置文件 | 并发度 |
|:-----|:-----|:---------|:------:|
| **DeepSeek-Chat** (当前主力) | 便宜、快速、中等推理 | `config/deepseek.yaml` (xhub) | 8-20 |
| **DeepSeek-V3** (如可用) | 更强推理、合理成本 | 新建 `config/deepseek_v3.yaml` | 8 |
| **GPT-4o-mini** | OpenAI baseline、便宜 | 新建 `config/gpt4o_mini.yaml` | 10 |
| **GPT-4o** | 最强 baseline | `config/default.yaml` | 4-6 |

### 维度 3: 扰动类型（5 类 CLAUSE 难度梯度）

复用 report_ultimate 已验证的 CLAUSE 5-tier 扰动体系：

| Tier | 类型 | 难度 |
|:-----|:-----|:----:|
| T1 | inconsistencies_inText | 易 |
| T2 | structural_flaws_inText | 中 |
| T3 | misalignedTerminology_inText | 中 |
| T4 | omission_inText | 难 |
| T5 | ambiguity_inText | 难 |

### 完整实验矩阵

```
3 配置 (A/B/C)
  × 4 scale 级别 (S/M/L/XL)  
  × 2 LLM (DeepSeek-Chat + GPT-4o-mini 为主; GPT-4o 做小规模验证)
  × 5 扰动类型 (T1-T5)
  × 3 repeats
```

**预估总 runs**:

| 组合 | Runs 计算 | 说明 |
|:-----|:---------:|:-----|
| 主实验 (DeepSeek-Chat) | 3 configs × 10 graphs × 5 tiers × 3 repeats = **450 runs** | 完整矩阵 |
| 跨模型验证 (GPT-4o-mini) | 3 configs × 3 graphs(M scale) × 5 tiers × 2 repeats = **90 runs** | 在中等 scale 上验证模型鲁棒性 |
| GPT-4o 验证 (小规模) | 3 configs × 2 graphs × 3 tiers × 2 repeats = **36 runs** | 仅在最有说服力的数据点上跑 |
| Clean baselines | 3 configs × 10 graphs × 2 LLMs × 2 repeats = **120 runs** | 误报率统计 |
| Toy 实验 (Ablation 1) | 3 configs × 多组 cycle 大小(3,5,7,10,15) × 100 iters 可视化 | 无需 API |
| **总计** | **~700 runs** (含 clean) | |

### 并行执行策略

```
                    ┌─── Scale S (3 graphs) ─── DeepSeek concurrency=20
                    │
Runner 1 (Config A) ├─── Scale M (3 graphs) ─── DeepSeek concurrency=20
                    │
                    └─── Scale L (3 graphs) ─── DeepSeek concurrency=20

                    ┌─── Scale S (3 graphs) ─── DeepSeek concurrency=20
                    │
Runner 2 (Config B) ├─── Scale M (3 graphs) ─── DeepSeek concurrency=20
                    │
                    └─── Scale L (3 graphs) ─── DeepSeek concurrency=20

                    ┌─── Scale S (3 graphs) ─── DeepSeek concurrency=20
                    │
Runner 3 (Config C) ├─── Scale M (3 graphs) ─── DeepSeek concurrency=20
                    │
                    └─── Scale L (3 graphs) ─── DeepSeek concurrency=20

Runner 4 (XL/BGB)  ─── 3 configs × BGB ─── DeepSeek concurrency=8 (大图需更多 token)

Runner 5 (Cross-model) ─── GPT-4o-mini × M scale ─── OpenAI concurrency=10
```

**三个 Runner 可同时启动**，各自独立（不同 config、不同数据），互不干扰。
预估时间：
- DeepSeek 主实验: ~4-6 小时 (基于 170 runs/102 min 的历史数据推算)
- GPT-4o-mini 验证: ~2 小时
- BGB XL: ~3 小时 (大图单次耗时长)
- **总挂机时间 ~6-8 小时**（并行执行）

---

## 结果呈现：论文中的核心表格

### Table 1: Main Results (Config A vs B vs C × Scale)

```
| Scale | Config A (Naive) | Config B (Eval) | Config C (Full) |
|       | Det% | FP% | Det% | Rank | FP% | Det% | Rank | Compress | FP% |
|:------|:----:|:---:|:----:|:----:|:---:|:----:|:----:|:--------:|:---:|
| S     |      |     |      |      |     |      |      |          |     |
| M     |      |     |      |      |     |      |      |          |     |
| L     |      |     |      |      |     |      |      |          |     |
| XL    |      |     |      |      |     |      |      |          |     |
```

### Table 2: Detection by Perturbation Difficulty (Config C)

```
| Tier  | DeepSeek | GPT-4o-mini | GPT-4o | LLM-only (CLAUSE ref) |
|:------|:--------:|:-----------:|:------:|:---------------------:|
| T1    |          |             |        | 43-64%                |
| T2    |          |             |        | 15-56%                |
| T3    |          |             |        | ~45-60%               |
| T4    |          |             |        | 45-64%                |
| T5    |          |             |        | 40-55%                |
```

### Table 3: Computational Cost

```
| Config | Avg LLM calls/graph | Avg time/graph | Cost estimate |
|:-------|:-------------------:|:--------------:|:-------------:|
| A      |                     |                |               |
| B      |                     |                |               |
| C      |                     |                |               |
```

### Figure: Toy Experiment (Ablation 1)

```
Q-value convergence plot:
  x-axis: iteration (0-100)
  y-axis: Q-value of injected node
  
  Line 1 (red, dashed): Vanilla MCTS → oscillation / no convergence
  Line 2 (orange):      Loop blocking → converges but flat (loses info)
  Line 3 (green, bold): SA-MCGS → fast convergence, identifies anomaly
```

---

## 需要新实现的代码

| 组件 | 优先级 | 描述 | 现有代码可复用 |
|:-----|:------:|:-----|:--------------|
| **Config A: Naive Collapse** | P0 | SCC → 单次 LLM 均值评估 → DAG-MCTS | `tarjan.py`, `dag_evaluator.py` |
| **Config B: Eval + Collapse** | P0 | SCC → K 次采样 → 带 profile DAG-MCTS | `scc_sampler.py`, `dag_evaluator.py` |
| **Toy Experiment Runner** | P0 | 可参数化的 N-cycle mock 实验 | `alphago_mcgs.py` 核心逻辑 |
| **Unified Ablation Runner** | P1 | 统一脚本: 接受 config/scale/model/tier 参数, 支持并行 | 各 `run_*.py` 可参考 |
| **Q-value 可视化** | P1 | matplotlib 画收敛曲线 | - |
| **Cross-model Config files** | P2 | `config/gpt4o_mini.yaml`, `config/deepseek_v3.yaml` | `deepseek.yaml` 模板 |
| **结果聚合分析脚本** | P2 | 从 JSON 结果生成 Table 1/2/3 | `experiments/analysis/` 下已有类似 |

---

## 执行顺序

| 阶段 | 任务 | 预估时间 | 产出 |
|:-----|:-----|:--------:|:-----|
| **Phase 1** | Toy 实验 (Ablation 1): 不同 cycle size 的 Q-value 发散可视化 | 1 天 | 论文 Figure 1 + Section 3 论证 |
| **Phase 2** | Config A & B 实现 + 单元测试 | 2 天 | 两个 baseline pipeline |
| **Phase 3** | Unified runner 脚本 (支持矩阵化并行) | 1 天 | 一条命令跑全部实验 |
| **Phase 4** | 主实验: DeepSeek-Chat × 全 Scale × 全 Tier | 6-8 小时挂机 | `results/ablation3_main.json` |
| **Phase 5** | 跨模型验证: GPT-4o-mini + GPT-4o 小规模 | 3-4 小时挂机 | `results/ablation3_cross_model.json` |
| **Phase 6** | 结果分析 + 论文表格/图 | 1 天 | Tables 1-3 + Figures |

**总时间预估**: 代码 4 天 + 实验跑约 1 天 (并行挂机) + 分析 1 天 = **约 6 天**

---

## 附录：与现有代码的对应关系

| 实验组件 | 现有代码 | 需要新写 |
|:---------|:---------|:---------|
| Tarjan SCC 检测 | `src/modules/tarjan.py` | - |
| AlphaGo-MCGS (Config C) | `src/modules/alphago_mcgs.py` | - |
| SCC 采样评估 (Config B 可复用) | `src/modules/scc_sampler.py` | - |
| DAG 评估 | `src/modules/dag_evaluator.py` | - |
| OpenAI client (GPT-4o/mini) | `src/llm/openai_client.py` | - |
| DeepSeek client | `config/deepseek.yaml` + openai_client | - |
| CLAUSE 扰动注入 | `scripts/run_deal_clause_ultimate.py` | 可复用 |
| 投毒注入 (Type A) | `experiments/` 下各脚本 | 可复用 |
| Naive Collapse (Config A) | - | **新写** |
| Unified Ablation Runner | - | **新写** |
| Toy 实验 (N-cycle) | - | **新写** |
| Q-value 可视化 | - | **新写** |
| Cross-model configs | - | **新写** (简单，基于模板) |
| 结果聚合分析 | `experiments/analysis/` 参考 | **新写** |

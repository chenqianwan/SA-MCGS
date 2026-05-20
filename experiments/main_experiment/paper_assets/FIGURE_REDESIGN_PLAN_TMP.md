# Temporary Figure Redesign Plan

这个文件只记录图表重设计方案，暂时不改现有图。目标是把 `paper_assets/figures/` 从“实验截图/基础统计图”升级成 ARR/EMNLP 主文可用的论文级图表。

## 总体原则

1. **Figure 1 固定使用 `demo.html` 前端架构图。**  
   这张图已经完整表达：有向有环图输入、Tarjan SCC、三大贡献、可插拔领域适配器。后续只需要导出成更清晰的 SVG/PDF/PNG，不再使用简化 pipeline 图。

2. **主文图必须有叙事密度。**  
   单纯 4 个 bar 的图太薄。主文图应同时回答 reviewer 会问的问题：效果提升来自哪里、是否受 error 影响、是否随 SCC 变长仍成立、rollout 是否真的收敛。

3. **Appendix 图要少而硬。**  
   如果图不能支撑 reviewer rebuttal，就不要放图，最多保留表格。

4. **Risk-all 是主指标，不弱化。**  
   Critical setting 下 risk-all 很重要。图表要解释：SA-MCGS 为了保住 root/witness/affected 端点，合理牺牲了一部分 compression。

---

## Figure 1: Framework Architecture

**当前问题**  
之前的 `fig01_sa_mcgs_pipeline` 是临时简图，信息量不足。

**新方案**  
直接用 `static/demo.html` 里的架构图：

- 输入：四类有环依赖图。
- Tarjan SCC 检测。
- DAG path vs SCC path。
- Contribution 1: SCC-aware search。
- Contribution 2: conformal evaluation。
- Contribution 3: pluggable pruning/domain adapter。
- 输出：ranked anomalies / collapsed risk subgraph。

**输出文件建议**

- `fig01_sa_mcgs_framework_architecture.svg`
- `fig01_sa_mcgs_framework_architecture.pdf`
- `fig01_sa_mcgs_framework_architecture.png`

**论文位置**  
Method 开头，作为整体方法图。

---

## Figure 2: Main Results Composite

**当前问题**  
现在只是 `Root@3 / Risk-any / Risk-all / Compression` 四个 bar，内容太少，而且 compression 低看起来像负面，没有解释“为什么这是必要 trade-off”。

**新方案：做成 3-panel 复合图。**

### Panel A: Strict Main Metrics

仍保留四大指标：

- Root@3
- Risk-any
- Risk-all
- Compression

但每个 bar 上标：

- `x/320`
- error count
- delta，例如 `+33 pts`

重点突出：

- Root@3: Naive 48% -> SA 81%
- Risk-any: 72% -> 98%
- Risk-all: 47% -> 78%
- Compression: 67% -> 53%

### Panel B: Reliability / Error Burden

单独画 error rate：

- Naive: 59/320 errors
- SA-MCGS: 0/320 errors

作用：回应 reviewer 对 “Naive 是不是被 JSON 解析拖垮” 的质疑。

### Panel C: Utility Frontier

做一个二维 trade-off：

- x-axis: Compression loss / subgraph size cost
- y-axis: Risk-all or Root@3 gain

要表达：SA-MCGS 不是“压缩更差”，而是用很小的子图扩张换来 critical endpoints retention。

**论文信息点**  
这张图变成主结果核心图，标题可以是：

> SA-MCGS improves critical risk localization while paying a controlled compression cost.

---

## Figure 3: SCC Size Composite

**当前问题**  
现在的 size bucket 图太普通，不能直观看出“长环是否更体现优势”。

**新方案：做成 2x2 或 1x3 复合图。**

### Panel A: Metric Gap by SCC Size

按 SCC size bucket：

- short `<=12`
- mid `14-20`
- long `>=24`

画 SA - Naive 的 delta：

- Root@3 delta
- Risk-any delta
- Risk-all delta

比直接画两组 bar 更抓眼球。

### Panel B: Absolute Risk-all by SCC Size

保留 Naive vs SA 的 risk-all 对比，因为 risk-all 是 critical 主指标。

### Panel C: Compression by SCC Size

显示不同长度下 compression 是否牺牲过大。

### 可选 Panel D: Error Rate by SCC Size

如果 Naive error 在长 SCC 明显变多，这个 panel 很有价值；如果没有明显趋势，就不放。

**论文信息点**

> As SCCs grow, SA-MCGS retains a stronger localization advantage, especially on complete critical endpoint retention.

---

## Figure 4: Rollout Convergence Composite

**当前问题**

现在的收敛图缺少 Root@3 / Rank@3 线。并且 Effective OC 是 cumulative discovery 指标，单独看容易误解为“必然单调上升所以没意义”。

**新方案：Figure 4 做成 convergence + final utility 的复合图。**

### Panel A: Rollout Convergence Curves

曲线包括：

- Root@3 / Rank@3
- Risk-any
- Risk-all
- Compression

不要把 Effective OC 作为主线。Effective OC 可以用浅色虚线或小注释，说明它是 discovery support，不是主指标。

### Panel B: Marginal Gain by Budget

显示 rollout budget 从：

- 5
- 10
- 20
- 30
- 60

带来的增量，例如：

- Risk-all gain
- Root@3 gain

作用：说明 SA-MCGS 的 rollout 不是纯堆调用量，而是在 early/mid budget 仍有实质收益。

### Panel C: Long-SCC Subset

单独看 `long >=24` 的收敛。  
如果长环上到 60 仍有上升趋势，这个 panel 很重要。

**论文信息点**

> Rollout increases do not merely accumulate evidence; they stabilize the dynamic core and improve complete critical endpoint retention.

---

## Figure 5: Compression Profile / Trade-off

**当前问题**

现在的 Figure 5 对比不明显，看起来像普通 ablation，价值不高。

**两个选择**

### Option A: 重做成 Pareto Frontier

把不同 compression profile 放到同一张二维图：

- x-axis: Compression
- y-axis: Risk-all
- point size: Root@3
- color: profile 或 method

这样能表达：

> Current/default is chosen because it is near the best risk-retention frontier, not because it maximizes compression.

### Option B: 不进主文，只留 appendix/table

如果 profile sweep 的样本量或对比不够强，Figure 5 从主文删除，只保留：

- `E3_compression_profile_ablation.csv`
- appendix table
- 一句话解释当前 profile 为什么固定

**我的建议**

先尝试 Option A。  
如果 Pareto frontier 不漂亮，就不要强行放主文，避免 reviewer 觉得我们在拿弱图凑数。

---

## Figure 6: Case Study Redesign

**当前问题**

现在的 Figure 6 是机械圆环，太乱，不像顶会图；也没有讲清楚“为什么 SA-MCGS 找到的是可修复风险子图”。

**新方案：做成 case narrative 图，而不是机械 network plot。**

### 推荐结构：三栏故事图

#### Left: Full SCC Context

只画抽象长环：

- 灰色节点表示 background SCC。
- root / witness / affected 高亮。
- 不需要把所有节点名字都挤进去。

#### Middle: Evidence Accumulation

画 rollout timeline：

- root first seen
- witness first seen
- affected first seen
- critical pair locked
- final core stabilized

这个比圆环图更能体现 SA-MCGS 的算法过程。

#### Right: Collapsed Risk Subgraph

画最终 core：

- root
- witness
- affected
- OC / repair entry

旁边给出：

- core size
- compression
- risk-all retained yes/no
- one-sentence diagnosis

**选择 case**

优先选 BGB-25 的 clean case。  
原因：BGB 噪声低，法律规则权威性强，更适合展示“结构冲突确实存在，而且被压缩成可解释子图”。

**论文信息点**

> The output is not a single suspicious node; it is a repair-oriented subgraph that preserves the critical endpoints of a structural contradiction.

---

## Figure A1: Remove

**当前用途**

Strict vs matched no-error 对比。

**问题**

这张图容易让主线变散，而且 bar chart 形式不够重要。

**处理**

删除 Figure A1。  
保留 `E0` 表格即可，用于 appendix 或 footnote：

- strict rate
- valid-only rate
- matched no-error rate
- error count

Reviewer 质疑错误处理时，表格比图更清楚。

---

## Figure A2: Naive Output-burden Control

**它是什么意思**

Figure A2 对应 E1：Naive baseline 有一个潜在不公平点：

- 主实验 Naive 要一次性读完整 SCC；
- 还要输出完整 ranking；
- 还要输出 risk subgraph；
- 还要输出 clause-level evaluation；
- 在 CUAD 长合同上，这会造成 JSON/输出负担。

E1 做了一个轻量 Naive：

- 输入仍是完整 SCC；
- 但输出 schema 简化；
- 只要求 top-risk nodes 和 risk subgraph。

它回答的问题是：

> Naive 的失败是不是因为输出格式太重，而不是因为 one-shot full-SCC reasoning 本身弱？

**当前问题**

作为图可能不够直观，而且会分散主线。

**处理建议**

不要作为主文图。  
保留为 appendix 表格 + 简短解释：

- 如果 lite Naive error 下降：说明 full-SCC one-shot 输出负担确实存在；
- 如果 lite Naive risk-all 仍不如 SA-MCGS：说明 SA 的优势不只是 JSON/schema 稳定性。

如果一定要画图，A2 应改名为：

> Appendix Figure: Naive Output Burden Control

并在 caption 中明确它是 fairness control，不是主结果。

---

## 新图表优先级

### P0 必做

1. Figure 1 使用 `demo.html` 架构图。
2. Figure 2 改成 main result 3-panel composite。
3. Figure 3 改成 SCC-size gap composite。
4. Figure 4 加 Root@3 / Rank@3，并区分主收敛指标和 cumulative Effective OC。
5. Figure 6 重做成 case narrative，而不是机械圆环。

### P1 视效果决定

1. Figure 5 尝试 Pareto frontier；不漂亮就降级为 appendix table。
2. A2 降级为 appendix fairness-control table。

### 删除 / 不推荐

1. Figure A1 删除。
2. 当前机械版 Figure 6 删除。
3. 当前单 bar Figure 2 删除。

---

## 最终推荐图表布局

### Main Paper

| Figure/Table | Purpose |
|---|---|
| Figure 1 | Framework architecture from demo.html |
| Table 1 | Why MCTS fails on SCC / why SCC collapse is needed |
| Table 2 | Dataset authority and coverage |
| Figure 2 | Main strict results composite |
| Figure 3 | SCC-size effect composite |
| Figure 4 | Rollout convergence composite |
| Figure 6 | BGB-25 case narrative |
| Table 3 | Main strict numeric table |

### Appendix

| Figure/Table | Purpose |
|---|---|
| E0 table | strict / valid-only / matched no-error |
| E1 table | Naive output-burden control |
| E3 table or Pareto figure | compression profile trade-off |
| E5 table | prompt/rubric parity |
| Human annotation pack | expert validation material |


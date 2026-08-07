# EMNLP 2026 Discussion: SA-MCGS 组件级消融实验设计

用途：回应 reviewers 关于 “component-level ablations for SA-MCGS itself are insufficient” 的意见。目标不是重复证明 full SA-MCGS 有效，而是更清楚地隔离 relation memory、critical-pair evidence、search policy、OC/core signal 和 dynamic core construction 的贡献。

## 1. 总体原则

- 组件消融的目标是验证 SA-MCGS 各模块对正确率和 evidence retention 的贡献，不再服务于推理成本估计。因此不采用低并发 cost-audit 设置。
- 使用论文主实验的 locked setting：`gpt-4o`、rollout budget `60`、window size `4`、SA-MCGS 内部并发 `4`。如果 runner 需要显式参数，默认设为 `--budget 60 --internal-concurrency 4`。
- case 外层可以适当并发，建议先用 `case_concurrency=4`；若 smoke run 稳定，再提高到 `6`。这里并发只用于加速，不作为实验变量。
- 每个 `case x variant` 单独 JSON 落盘；runner 可恢复，挂掉不影响已完成 case。
- 主表尽量使用同一批 case，避免不同 variant 的 case composition 不一致。
- 消融分成两类：
  - LLM-dependent search ablations：改变 rollout 选择或跨 rollout 记忆，会改变实际调用窗口，必须补跑。
  - Trace-replay / core-only ablations：只改变最终 core construction 或 evidence aggregation，可以从 full trace 重放，更干净地隔离 final-core 模块。

## 2. Case 设计

### 主消融集

主表建议沿用上一轮已经整理出的同一批 20 个 `direct_mutex` case identities，但所有 component variants 重新按主实验设置运行：

- 覆盖 4 个 domain：CUAD、BGB、Debian、SEC EX-21。
- 覆盖 SCC size：large / medium / small。
- 与已经完成的 LEA / Naive 诊断使用同一批 case identities，便于后续叙事对齐。
- Full SA-MCGS 不需要重跑，直接复用 locked 320-case main experiment；如果 component ablation 主表只使用 subset，则从 locked main results 中抽取同一 subset 的 Full SA-MCGS rows 作为 matched 对照。注意不要复用低并发诊断结果作为 Full 对照。
- case 顺序仍按 SCC size 从大到小，便于优先得到大 SCC 上的信号。

### 稳健性补充集

为了避免 reviewer 觉得消融只在 `direct_mutex` template 上成立，建议增加一个小型 template robustness subset：

- 从主消融集中选 8 个代表性 SCC：
  - large CUAD 2 个；
  - medium CUAD 2 个；
  - BGB 1-2 个；
  - Debian 1 个；
  - SEC EX-21 1-2 个。
- 对这些 SCC 跑 4 个 templates：`direct_mutex`、`condition_trigger`、`temporal_gate`、`handoff_invariant`。
- 该 subset 不一定进入主表；可作为 appendix-style robustness note，报告 “the component trends are similar across conflict templates”。

优先保证主 20-case 消融；template subset 作为第二阶段，用来增强结论稳健性。

## 3. Variant 设计

### A. 主表 variants

| Variant | 需要 LLM 重跑 | 改动 | 回答的问题 |
|---|---:|---|---|
| Full SA-MCGS | 否 | 复用 locked 320-case main results；若主表使用 subset，则抽取 matched Full rows | 主方法对照 |
| No relation-first memory | 是 | 关闭 relation-first progressive bias / relation probe / relation-first compression seeding | relation memory 是否贡献 search 与 endpoint retention |
| No critical-pair ledger/revisit | 是 | 保留普通 relation evidence，但关闭 persistent critical-pair ledger 与 revisit | persistent pair evidence 是否帮助保留冲突两端 |
| Random local-window selection | 是 | 保留同样 local-window prompt/schema/budget，但随机选窗口 | SA-MCGS 是否优于简单 repeated local prompting |
| No OC/core signal | 否，优先 trace replay | final core priority 中去掉 OC/core alarm contribution | OC/core signal 是否影响 root/core selection |
| Monotone core | 否，优先 trace replay | core 只累积高分节点，不做 dynamic replacement / pair-closure replacement | dynamic replacement core 是否优于单调累积 |

### B. 可选更细 variants

如果主表结果显示某个模块贡献不明显，可以补充更细粒度诊断，而不是一开始就把表做得太宽：

| Variant | 用途 |
|---|---|
| UCB without relation prior | 保留 UCB 和局部 graph expansion，只去掉 relation progressive bias，隔离 relation-prior 对 selection 的影响 |
| No pair closure in final core | 保留 critical-pair ledger，但 final core 不为强 pair 自动补 counterpart，隔离 final-core pair closure |
| Deterministic local-window repeated prompting / LEA | 已完成，作为 local decomposition baseline 引用，不必塞入 component table |

## 4. 指标

主表列：

| Metric | 说明 |
|---|---|
| `N` | attempted cases |
| `Invalid` | invalid output rate |
| `Root@3` | injected root 是否进入 top 3 |
| `Risk-any` | final/core subgraph 是否包含任一 injected risk endpoint |
| `Risk-all` | final/core subgraph 是否包含全部 injected risk endpoints |
| `Compression` | final/core subgraph compression ratio |
| `Avg core size` | 平均 core 节点数，帮助解释 compression |
| `Delta vs Full` | 相对 Full SA-MCGS 的主要指标下降，用来突出模块贡献 |

token / call / runtime 可以继续在 JSON 中记录，便于内部排查，但不作为 component ablation 主表重点。

辅助诊断列，可放在附表：

- `First risk-any rollout`
- `First risk-all rollout`
- `Relation probe count`
- `Critical-pair locked/candidate edges`
- `TT hits`
- `Core hit cap rate`

## 5. 推荐运行顺序

### Stage 0: sanity smoke

先选 3 个 cases：large CUAD、medium CUAD、small SEC/BGB，各跑所有 LLM-dependent variants。目的只是验证 runner、开关和 summary 没问题。

建议 smoke 设置：

- `case_concurrency=3`
- `internal_concurrency=4`
- `budget=60`

### Stage 1: 主 20-case 消融

按以下顺序跑：

1. 从 locked main results 抽取 Full SA-MCGS matched rows
2. `No relation-first memory`
3. `No critical-pair ledger/revisit`
4. `Random local-window selection`

No OC/core signal 和 Monotone core 先从 full traces replay。

建议主跑设置：

- `case_concurrency=4` 起步；如果 API 稳定，可提高到 `6`。
- `internal_concurrency=4`，与论文主设置一致。
- 不把 wall-clock time 作为结论依据。

### Stage 2: core-only replay

从 full SA-MCGS 的 trace/result 重放：

1. `No OC/core signal`
2. `Monotone core`
3. 可选 `No pair closure in final core`

这个阶段不产生新 LLM 调用，适合快速迭代表格。

### Stage 3: template robustness subset

如果 Stage 1 结果足够清楚，再跑 8 SCC x 4 templates 的 subset。优先 variants：

1. Full SA-MCGS
2. No relation-first memory
3. No critical-pair ledger/revisit
4. Random local-window selection

## 6. 运行规模

| Variant | Cases | 执行方式 |
|---|---:|---|
| Full SA-MCGS | 20 或 320 | 复用 locked main results；按主表 case scope 抽取 matched rows |
| No relation-first memory | 20 | 按主实验设置跑 |
| No critical-pair ledger/revisit | 20 | 按主实验设置跑 |
| Random local-window selection | 20 | 按主实验设置跑 |
| No OC/core signal | 20 | 从 Full traces replay |
| Monotone core | 20 | 从 Full traces replay |

template robustness subset 如果跑 8 SCC x 4 templates x 4 variants，大约是 128 method-cases；建议作为第二阶段任务，不和主 20-case 主表混在同一张表里。

## 7. Reviewer-facing 口径

后续 discussion 可写：

> We add a component-level ablation on the same stratified case identities used for the discussion diagnostics, but run the ablation under the paper's main SA-MCGS setting. Starting from full SA-MCGS, we disable relation-first memory, critical-pair revisiting, graph-guided local-window selection, OC/core signals, and dynamic core replacement one at a time. The search ablations are re-run under the same local evidence schema and rollout budget; the core-only ablations are replayed from full SA-MCGS traces, which isolates the final-core construction effect without introducing additional sampling noise. This table separates the roles of persistent relation evidence, pair-level evidence, search policy, calibrated core signals, and dynamic core construction.

中文口径：

> 我们在同一批分层 case identities 上补充组件级消融，但消融本身使用论文主实验的 SA-MCGS 设置。从 full SA-MCGS 出发，分别关闭 relation-first memory、critical-pair revisiting、graph-guided local-window selection、OC/core signals 和 dynamic core replacement。会改变 rollout 轨迹的消融重新运行 LLM；只影响 final core construction 的消融从 full trace 重放，以便隔离最终压缩模块本身的作用。这张表用于展示 persistent relation evidence、pair-level evidence、search policy、calibrated core signals 和 dynamic core construction 各自的增量贡献。

## 8. 最终产物

- `component_ablation_runs/<run_id>/results/*.json`
- `component_ablation_runs/<run_id>/summary_component_cases.csv`
- `component_ablation_runs/<run_id>/component_ablation_table.csv`
- `component_ablation_runs/<run_id>/component_ablation_table.md`
- 可选图：`component_ablation_overview.png`

# Experiment V3 · Historical Synthetic Scaling Diagnostic

> **Current-position notice (2026-08-19).** 本文件保留 V3 的冻结技术记录，
> 不再代表 Paper 2 的当前主路线。当前框架已回到 SA-MCGS 的真实循环文档、
> local-window LLM reads、committed symbolic KB 与 online incremental LFP feedback；
> 普通通用 LLM 是主 baseline，TreeMCTS 仅是 exact-state-sharing 消融。

## 先看结论

这轮把递归规模固定为 `3 / 5 / 7 / 9 / 12 / 16 / 20`，共生成并验证
`140 families / 420 cases`，再做 TreeMCTS 与严格状态合并 MCGS 的配对实验。

当前结论是：

- **Synthetic search-budget sensitivity 可复现。** 在 canonical productive cases 上，把 search-transition cap 从 1,024 提高到
  4,096，size 12 / 16 / 20 的恢复率分别从 `48.3 / 26.7 / 16.7%`
  上升到 `80.0 / 55.0 / 43.3%`。
- **Unseeded oracle invariant 通过。** 全部 unseeded controls 均未从循环中自我推出 query；这不是端到端 LFP 安全性结论。
- **MCGS 优势尚未成立。** Canonical 图上 Tree 与 MCGS 的 recovery 完全一致；
  合成多路径 overlay 虽节省约 17% 搜索节点，但 proof-recovery AUC 略低于 Tree。
- **SCC 因果尚未成立。** Matched DAG 也随长度和预算呈相近变化；本结果不能解释为 LLM 慢思考或当前 LFP-MCGS 方法的优势。

## 数据三联组

每个 family 含：

1. `productive_seeded_scc`：seed 进入 predicate SCC，最后一条 feedback rule
   返回同一 predicate 的新 grounding，并推出 query。
2. `unseeded_scc`：规则与 SCC 保持不变，相关 seed 换成 decoy；query 为 Unknown。
3. `matched_dag`：规则、事实、来源数、干扰项和最小推导深度匹配，但 predicate graph
   被切成 DAG。

全部语义是 finite ground positive Horn；生成器保存闭包、逐轮 provenance、最小证明源和
删除因果检查。它是**合成机制诊断**，不是自然语料或 LLM 结果。

## A0 · 一次性 oracle-structure search

- 420 cases × 3 seeds × 2 methods × 2 navigation variants = `5,040` trials / cap。
- 完整预算网格：`1,024 / 2,048 / 4,096` transitions。
- Canonical strict TT hit rate 仅 `0.047%`；判定为 sparse-transposition NO-GO。
- Synthetic overlay 的 node-saving AUC：productive `17.11%`，DAG `17.46%`。
- Proof-recovery AUC：

| Navigation | Condition | Tree | MCGS | MCGS − Tree |
|---|---|---:|---:|---:|
| Canonical | Productive SCC | 74.82% | 74.82% | 0.00 pp |
| Canonical | Matched DAG | 70.77% | 70.77% | 0.00 pp |
| Synthetic overlay | Productive SCC | 74.40% | 73.75% | −0.65 pp |
| Synthetic overlay | Matched DAG | 75.42% | 75.24% | −0.18 pp |

## A1 · 在线 root action → LFP → replan

代表性 scaling 运行了 `252` trials：每轮规划后执行一个付费 root action，获取来源后更新
exact LFP，再从新的 closure/obligations 继续规划。

- 126 个 Tree/MCGS 配对中，proof recovery 改变 `0` 次。
- Root action sequence 只改变 `1` 次，最终结果仍相同。
- Overlay 出现 `469` 次 TT hit 和 `147` 次跨 root 严格复用；canonical 全为 `0`。
- 这说明在线闭环和严格复用已经能运行，但当前 value/prior 尚未把复用转化为更好决策。

## 当前数据设计缺口

`source_adjacency` 由 predicate producer/consumer overlap 导出，因此物理导航 SCC 与逻辑
predicate SCC 被耦合。特别是 unseeded case 的 decoy seed 会让入口在 canonical 图上断开，
使该控制条件过于容易。该结果保留为失败证据，不进入论文主张。

当时提出的两轴设计保留为历史诊断建议，不再是当前论文主路线：

```text
physical document topology: SCC / DAG
semantic dependency:          productive SCC / matched DAG
```

当前确认实验改为直接测试真实 cyclic local-window search、source-grounded committed KB、
online LFP feedback 与 matched-compute general-LLM baselines；TreeMCTS 只关闭 exact state sharing。

## 复现入口

```bash
python3 generate_benchmark.py --check-only
pytest -q test_v3_scc_scaling.py
python3 run_a0_scc_scaling.py --quiet
python3 run_a1_online_scaling.py
```

主要冻结产物位于 `results/`：A0 主结果、三预算 sensitivity、A1 在线 scaling，以及各自
manifest。不要把 overlay、oracle reward 或模板 NL 当作正式端到端证据。

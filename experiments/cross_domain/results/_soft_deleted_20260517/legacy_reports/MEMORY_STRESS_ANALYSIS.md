# Long-Cycle Memory Stress: Legacy Diagnostic Notice

最后更新：2026-05-13  
当前状态：**Legacy diagnostic only；不可作为论文主结果**

这份文件原本包含旧版 `memory_stress` 的 28-case 分析、Wikipedia gap、旧图表和旧 TODO。由于后续审计确认旧结果混入了 prompt parity 问题、score-only/ranked baseline 口径问题，以及过于显性的注入文本，这些内容已经从主分析中移除。

正式分析文件已切换到：

[STRUCTURAL_SIMPLE_ANALYSIS.md](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/STRUCTURAL_SIMPLE_ANALYSIS.md)

## 旧结果如何使用

| 旧口径 | 当前用途 | 不再用于 |
|---|---|---|
| old score-only Naive | Appendix 方法警示 | 主表、摘要、核心 claim |
| old `memory_stress` | 设计演进记录 | 正式实验结果 |
| old Wikipedia gap | confound 复盘 | memory-loss 证据 |
| old risk subgraph with GT anchor | post-hoc 解释示例 | blind retrieval 指标 |

## 正式口径

正式实验从 `structural_simple_v1` 开始重新计数：

- 不新增节点，只修改原 SCC 中已有节点。
- 一个 GT/root 节点标记 `_perturbed`。
- 一个远距离 witness 节点只改文本，不标记 `_perturbed`。
- Naive 和 SA-MCGS 都使用通用 directed-graph consistency/risk prompt。
- 正式结果必须来自新 rerun 文件。


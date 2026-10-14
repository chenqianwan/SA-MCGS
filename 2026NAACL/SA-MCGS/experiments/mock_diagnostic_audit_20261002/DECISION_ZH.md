# TreeMCTS mock 诊断核验与采用建议

2026-10-02。本目录只重算已有数据，不调用 LLM、不重跑模拟，不改论文。

**结论：旧表不能原样保留。最稳妥方案是把这个诊断移到附录，明确写为 synthetic mock，用本目录六行同分组表替换；正文只留结构动机，不让 mock 承担生产 SA-MCGS 优势的核心证据。**

已完成：90 条原始 run 找回；逐条核验100次迭代、历史长度、tree size末值、rollout均值与Hit@3/rank一致；按 topology × method 重算；每行15条，按规模另输出18行。重建与 `--verify` 均通过。输出包含协议、脱敏逐例CSV、完整JSON、LaTeX片段及英文方法。

实质修正：

1. 旧表混用了 compound-only 的100%与 pooled cycles 的0.044/30%、0.371/90%。新表严格分开 DAG/simple/compound。
2. 6.4×不能由原始compound cohort复算；逐例比值均值为7.45×，ratio-of-means为5.73×。原二级summary使用约数127/20，不应成为正式数据源。
3. Q-spread 是最终**物理节点正值Q的极差**；不是标准差，也不是root action values。Tree与proxy的Q估计目标亦不同，不能靠极差宣布收敛更好。
4. Hit@3 是合成异常节点的top3命中，不是人工确认的repair endpoint。
5. 实际只记录路径长度。31个路径节点意味着达到30步transition cap；没有terminal flag，统一改称depth-cap reached。DAG为0.27%，simple为11.73%，compound为100%。
6. SA mock没有随机游走与树结构，应显示N/A，不将源码零占位当实测0%失败；每个物理节点一份统计是设计属性，不能当1.0×测得的tree expansion。
7. 两方法所有45个对应单元seed均不同，不能写matched same graph。100 iteration slots不等于等调用/等token。
8. 该proxy只有SCC偏置窗口与TT，不具备生产版relation-first memory和core policy，需更名SCC-window proxy或明确“simplified SA-style proxy”。

可选择的论文呈现：

- **推荐：附录六行表。** 使用 `table_same_cohort.tex` 与 `methods_en.md`；正文删除6.4×/100%/0.044→0.371的混合强陈述，仅说明路径状态复制的动机。DAG代理对照也应保留，不能隐藏TreeMCTS在DAG上同样很低的Hit@3。
- **更保守：仅保留结构表。** 只展示TreeMCTS三种拓扑的allocated-state ratio、path长度、depth-cap reached；Qrange与Hit@3列移除，减少“只剩保存摘要”的复核依赖。全部运行同样进入附录，以免择优展示。
- **不推荐：强行修成旧三行表。** 即使把SCC行改成compound-only，也无法恢复matched graphs、root-action Q、生产算法归因与等compute。更换几个数字不足以修复定义问题。

不能恢复的部分已经明确标为不支持：完整最终Q向量、按全部节点独立复算rank/Qrange、每步terminal flags、历史hash seed/运行版本、完整realized graphs、独立同图对照和准确等调用预算。不得以当前源码新跑替代原始数据并称原实验复现。

参考原始源码：`search_methods.py:172–195`（allocated states）、`:197–229`（path lengths）、`:258–287`（rank与Qrange）、`:398–425`（proxy更新）；原始runner `:141`（依赖method的hash seed）。本目录保留对应当前源码及hash。

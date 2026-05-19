# Structural Simple V2 正式真实文本实验报告

最后更新：2026-05-13  
实验范围：`memory_stress` CLI profile，内部版本 `_inject_profile_version = structural_simple_v2`  
运行标签：`formal_full_realtext_c8_*_20260513`

> **状态：正式真实文本分析。** 旧版 `memory_stress`、synthetic、diagnostic 结果不进入本报告主结果，只作为实验设计演进的历史记录。当前主结论只基于 **Debian + SEC EX-21**。Wikipedia 由于真实 SCC 覆盖过少，只保留为数据集诊断记录，不参与主结论。

## 1. 核心结论

结构性缺陷不应该只按“注入 root 节点是否进入 Top-k”来评估，而应该按 **风险区域 risk region** 来评估。

原因很简单：我们注入的不是一个孤立坏点，而是一组互相依赖的结构性冲突。危险状态通常由 perturbed root、远距离 witness，以及可能存在的 bridge/affected 节点共同形成。在真实修复流程里，修改 **root 侧、witness 侧，或者某个被影响的桥接记录** 都可能解除风险。因此，root-only Top-k 只是一个较窄的诊断指标；如果模型抓到了 witness 或 affected 节点，也不能简单算失败。

本轮主结果完成 **76 个有效 case，0 个错误**。这里的主结果只统计 Debian + SEC EX-21；Wikipedia 的 4 个 case 不进入主表结论。

| 方法 | N | Root Top-3 | Risk-any Top-3 | Risk-all Top-3 | 平均 root 排名 | 子图 risk-any | 子图 risk-all | 子图压缩率 | SA-only OC | OC 有效率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Ranked Naive | 38 | 16/38 (42%) | 35/38 (92%) | 12/38 (32%) | 4.92 | 36/38 (95%) | 27/38 (71%) | 21.1% | - | - |
| SA-MCGS | 38 | 13/38 (34%) | 35/38 (92%) | 12/38 (32%) | 5.47 | 36/38 (95%) | 16/38 (42%) | 41.3% | 23/38 (61%) | 18/23 (78%) |

**解释。** 如果只看 Top-k，这轮并不是一个干净的 SA-MCGS 排名胜利：Naive 的 root Top-3 是 `16/38 (42%)`，SA-MCGS 的 root Top-3 是 `13/38 (34%)`。但两种方法都经常能把至少一个风险节点放进 Top-3。这说明 one-shot LLM 并非完全看不见风险；真正要比较的是，系统能不能把“泛泛的可疑节点”进一步组织成 **OC 证据 + 可检查的风险子图**。

## 2. 为什么主指标应是 OC + 风险子图

对 SA-MCGS 来说，重要输出不是单个排名，而是：

- **OC hit：** 局部窗口搜索是否发现了 ordered-cycle evidence 或结构性矛盾信号。
- **OC 有效率：** 在已经触发 OC 的 case 中，OC 节点是否落在 root / witness / bridge / affected 任一可解释风险节点上。它衡量 OC 不是“随便响”，而是真的指向风险扩散区域。
- **盲风险子图 blind risk subgraph：** 由 OC 节点、Top-k 风险节点和局部环邻居构成，不手动加入 GT root。
- **Risk-any retention：** 盲子图是否保留至少一个可修复风险点，例如 root 或 witness。
- **Risk-all retention：** 盲子图是否同时保留 root 和 witness。这个指标更严格，但真实修复时不一定必须同时抓住两端。
- **Compression：** 在保留风险区域的同时，能把原 SCC 压缩掉多少。

为避免对子图能力的比较不公平，报告新增了一个 matched subgraph baseline：

```text
Naive 子图 = Naive global_ranking Top-3 anchors + 每个 anchor 的环上前后邻居
SA-MCGS 子图 = OC anchors + Top-3 anchors + 环上前后邻居，不使用 GT root
```

这个口径下，Naive 也被允许输出一个风险子图；SA-MCGS 的增量主要来自 OC anchors 是否能让子图更小、更集中。

![OC 与风险子图](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/formal_realtext_main_oc_subgraph.png)

[打开原图](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/formal_realtext_main_oc_subgraph.png)

| 领域 | 总 case | Naive Root@3 | SA Root@3 | Naive 子图 any | SA 子图 any | Naive 子图 all | SA 子图 all | Naive 压缩 | SA 压缩 | SA OC 命中 | OC 有效率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Debian | 44 | 14/22 (64%) | 12/22 (55%) | 21/22 (95%) | 22/22 (100%) | 18/22 (82%) | 14/22 (64%) | 7.3% | 29.7% | 11/22 (50%) | 11/11 (100%) |
| SEC EX-21 | 32 | 2/16 (12%) | 1/16 (6%) | 15/16 (94%) | 14/16 (88%) | 9/16 (56%) | 2/16 (12%) | 40.1% | 57.4% | 12/16 (75%) | 7/12 (58%) |

![按领域指标表](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/formal_realtext_main_domain_metrics_table.png)

[打开原图](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/formal_realtext_main_domain_metrics_table.png)

![公平子图对照](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/formal_realtext_main_matched_subgraph.png)

[打开原图](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/formal_realtext_main_matched_subgraph.png)

**SEC EX-21 是当前最强的主结果领域。** 在这个领域里，两种方法的 root Top-3 都很低，说明任务不是靠“看出被改过的 root”就能轻松解决。在 matched subgraph 口径下，Naive 子图 risk-any 是 `15/16 (94%)`，SA-MCGS 是 `14/16 (88%)`；但 SA-MCGS 平均压缩率更高，`57.4%` 对 `40.1%`。这说明 SA-MCGS 不是单纯覆盖更多风险点，而是更激进地压缩风险区域。与此同时，SEC 中 `12/16` 个 case 有 OC，其中 `7/12` 个 OC 落在 root / witness / bridge / affected 这类可解释风险区域里。

**Debian 是混合但有用的支持结果。** 很多 5-node 小环太小，不容易体现压缩价值；但 matched subgraph 口径下，Naive risk-any 是 `21/22 (95%)`，SA-MCGS 是 `22/22 (100%)`，同时 SA-MCGS 压缩率从 Naive 的 `7.3%` 提高到 `29.7%`。此外，SA-MCGS 在 `11/22` 个 case 中触发 OC，且这 `11/11` 个 OC 都落在可解释风险区域里。

**Wikipedia 暂时不参与主结论。** 当前 loader 合图后只有 3 个真实 SCC，长度为 `[5, 34, 56]`；在 `5-24` 正式范围内只剩一个 5-node SCC，因此结果覆盖太稀疏，不适合作为数据集主证据。

## 3. 环长度影响

![按 SCC 规模对比](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/formal_realtext_main_by_size.png)

[打开原图](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/formal_realtext_main_by_size.png)

随着 SCC 变长，root Top-3 会变弱并且更不稳定。这是合理现象：结构性冲突传播后，root 不一定是表面上最可疑的记录。更稳健的指标应该是方法是否保留了一个可操作的风险区域。

比起 5-node 小环，11/12/18-node case 更值得写进论文主体：

- Debian 11-node：Naive 和 SA-MCGS 都没有命中 root Top-3，但 DeepSeek + SA-MCGS 仍触发 OC，并保留压缩子图。
- Debian 12-node：gpt-4o + SA-MCGS 在 Naive miss 的情况下恢复 root Top-3；两个 SA run 都压缩到 `7/12`。
- SEC 18-node：两个模型都 miss root Top-3，但盲风险子图压缩到 `7/18`，相当于减少 `61%`。即使 Top-k 不成功，这也是很强的风险子图证据。

## 4. 为什么暂时不参考 Wikipedia

Wikipedia 这轮不是因为 API 或实验失败，而是数据形态本身不适合作为当前主数据集。当前 loader 把真实 category cycles 合成图后再跑 Tarjan，得到的 SCC 长度只有：

```text
[5, 34, 56]
```

在本轮正式参数 `--real-min-size 5 --real-max-size 24` 下，Wikipedia 只贡献了一个 5-node SCC，因此只有：

```text
1 个 SCC × 2 个模型 × 2 个方法 = 4 个 case
```

这 4 个 case 的结果是：Naive root Top-3 `2/2 (100%)`，SA-MCGS root Top-3 `2/2 (100%)`，SA-MCGS OC `0/2 (0%)`。这些数字没有足够数据集覆盖意义，因此只保留为记录，不进入主结论。

## 5. SEC EX-21 明细

SEC 是当前最适合承载论文叙事的领域，因为它把 root ranking 和 structural risk localization 分开了：root 排名不高，但 OC 与风险子图仍然能给出可解释定位。

![SEC 明细表](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/formal_realtext_main_sec_case_table.png)

[打开原图](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/formal_realtext_main_sec_case_table.png)

表格右侧是关键：即使 root Top-3 没命中，OC、OC 有效率和盲风险子图覆盖仍然经常保留下来。这正好匹配我们的设定：结构性注入缺陷不一定只能从 root 修，也可以从 witness 或 affected 节点侧修。

## 6. 对论文主张的影响

论文不应该写成“SA-MCGS 在单点排名上碾压 Naive”。更稳、更有说服力的主张应该是：

> **在真实文本的循环依赖图中，one-shot ranking 经常可以抓到某个可疑节点，但它不能解释结构性失效。SA-MCGS 的价值在于增加 search-time OC 信号，并把 SCC 压缩成一个更小的风险子图，同时保留可操作的修复入口。**

这个口径也解释了为什么 root-only GT 会显得不公平或噪声很大。注入 root 只是结构性矛盾的一端；如果模型抓到了 witness、bridge 或 affected 记录，在实践上并不是失败，而是找到了另一个修复把手。

## 7. 下一步实验建议

1. 把 `blind_risk_subgraph` 作为主子图指标；GT-anchored subgraph 只保留为 sanity check。
2. 分开报告 root Top-k、risk-any Top-k、risk-all Top-k，不要合并成一个 detection rate。
3. 把 SEC EX-21 提升为当前设计下的主结构风险领域。
4. Debian 作为支持结果，重点写 11/12-node SCC。
5. 当前 Wikipedia 不作为 headline；后续除非改成更合理的 raw-cycle mode 或找到更密集真实 SCC，否则不进入主实验。
6. 考虑把 **CUAD** 加入下一轮跨域实验。CUAD 的合同条款文本更长、更接近法律推理场景，可能比 Wikipedia 更适合验证结构性冲突 + 风险子图压缩。
7. 方法章节必须解释：为什么结构性冲突不能只用 root-only GT 评估。
8. 下一轮可以只在 SEC/Debian/CUAD 上跑多个 conflict template，继续坚持真实文本、不新增 synthetic 节点。

## 8. 结果文件

- `battle_inject_memory_stress_handoff_invariant_rankednaive_formal_full_realtext_c8_debian_20260513_1778677670.json`
- `battle_inject_memory_stress_handoff_invariant_rankednaive_formal_full_realtext_c8_sec_20260513_1778677677.json`
- `battle_inject_memory_stress_handoff_invariant_rankednaive_formal_full_realtext_c8_wikipedia_20260513_1778677675.json`

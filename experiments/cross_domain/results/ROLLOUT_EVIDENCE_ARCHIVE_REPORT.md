# Rollout Evidence Archive 诊断报告

最后更新：2026-05-14  
输入结果：`battle_inject_memory_stress_handoff_invariant_rankednaive_samcgsonly_convergence_long_real_gpt4o_b100_20260514_1778724052.json`  
对照 baseline：Debian/SEC 的 `Naive direct subgraph` 结果  

> **状态：离线后处理诊断。** 本报告没有重新调用 API，也没有修改 SA-MCGS rollout 搜索算法。它只重放已有 trace，验证一个问题：SA-MCGS 是否已经发现过风险证据，但最终压缩子图没有稳定保留。

## 1. 结论先说

当前证据支持我们的判断：

**SA-MCGS 的搜索过程已经比末态结果更强；问题主要在 evidence retention，而不是单纯搜索不到。**

在 12 个较长真实 SCC 上：

| 范围 | N | Naive 平均覆盖 | Naive risk-all | SA final 平均覆盖 | SA final risk-all | Archive 平均覆盖 | Archive risk-all | Best-so-far 平均覆盖 | Best-so-far risk-all | Archive 压缩率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Overall | 12 | 54.2% | 2/12 (17%) | 75.0% | 7/12 (58%) | 83.3% | 8/12 (67%) | 87.5% | 9/12 (75%) | 49.9% |
| Debian | 4 | 62.5% | 2/4 (50%) | 75.0% | 3/4 (75%) | 87.5% | 3/4 (75%) | 87.5% | 3/4 (75%) | 47.6% |
| SEC EX-21 | 8 | 50.0% | 0/8 (0%) | 75.0% | 4/8 (50%) | 81.2% | 5/8 (62%) | 87.5% | 6/8 (75%) | 51.0% |

解释口径：

- **SA final**：当前实验脚本最后一轮留下的风险子图。
- **Evidence archive**：不使用 GT 标签，只根据 trace 中的 local risk、repair、conflict endpoint、OC、prefix-selected history 构造的盲子图。
- **Best-so-far diagnostic**：使用 GT 做诊断的 oracle 指标，只说明“搜索过程曾经达到过哪里”，不能作为部署算法。

最重要的变化是：

```text
Naive risk-all:        2/12 (17%)
SA final risk-all:     7/12 (58%)
Evidence archive:      8/12 (67%)
Best-so-far diagnostic:9/12 (75%)
```

也就是说，archive 没有把所有 best-so-far 都追回来，但已经把 final 的一部分末态丢失修复掉了。

![Evidence archive summary](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/rollout_evidence_archive_summary.png)

## 2. 这个结果说明什么

这不是“rollout 越多自然越好”。更准确地说：

1. 早期 8-30 rollout 内发现的风险证据，比较容易进入后续统计。
2. 21 轮之后才出现的 pair，当前 final 子图经常留不住。
3. Evidence archive 的价值是把“曾经形成过紧凑风险子图”的节点留下记忆，而不是只看最后累计分数。

所以我们现在看到的是一个很好的算法诊断：

> MCGS 的搜索已经有能力发现结构风险，但现有末态聚合会遗忘 late evidence。正式算法应该加入 evidence-aware retention。

## 3. 逐 case 明细

![Evidence archive cases](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/rollout_evidence_archive_cases.png)

| Domain | Size | SCC | Naive cov | SA final | Archive | Best diag | 首次同窗 | 首次 final 收齐 | best rollout | Archive nodes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| debian | 7 | scc_49 | 1.0 | 1.0 | 1.0 | 1.0 | 3 | 3 | 3 | pcscd, libasedrive-usb, libifd-cyberjack6, libasedrive-serial |
| debian | 7 | scc_15 | 0.0 | 0.0 | 0.5 | 0.5 | 9 | None | 1 | ruby-sdbm, libruby3.1, ruby, rake |
| debian | 11 | scc_23 | 1.0 | 1.0 | 1.0 | 1.0 | None | 7 | 7 | node-deep-equal, node-es-abstract, node-tape, node-parse-json, node-istanbul |
| debian | 12 | scc_8 | 0.5 | 1.0 | 1.0 | 1.0 | 8 | 8 | 8 | libecore-input1, libevas1, libecore-evas1, libevas1-engines-wayland, libecore-x1, libevas1-engines-fb |
| SEC EX-21 | 9 | scc_6 | 0.5 | 1.0 | 1.0 | 1.0 | 6 | 6 | 6 | us-cw-3682811, us-cw-617657, us-cw-3682213, us-cw-3682212, us-cw-3684902 |
| SEC EX-21 | 10 | scc_0 | 0.5 | 0.5 | 0.5 | 1.0 | None | 3 | 3 | us-cw-1020294, us-cw-749750, us-cw-749751, us-cw-1011764, us-cw-749749 |
| SEC EX-21 | 11 | scc_2 | 0.5 | 0.5 | 0.5 | 0.5 | 21 | None | 6 | us-cw-1843, us-cw-74755, us-cw-74745, us-cw-489773, us-cw-423245 |
| SEC EX-21 | 11 | scc_7 | 0.5 | 1.0 | 1.0 | 1.0 | 9 | 6 | 6 | us-cw-1073489, us-cw-570230, us-cw-491198, us-cw-491194, us-cw-1073529 |
| SEC EX-21 | 11 | scc_1 | 0.5 | 0.5 | 1.0 | 1.0 | 9 | 18 | 18 | us-cw-19363, us-cw-145, us-cw-21081, us-cw-406, us-cw-23183 |
| SEC EX-21 | 12 | scc_3 | 0.5 | 1.0 | 1.0 | 1.0 | 5 | 5 | 5 | us-cw-7565, us-cw-502062, us-cw-502091, us-cw-708556, us-cw-705648, us-cw-748274 |
| SEC EX-21 | 12 | scc_4 | 0.5 | 1.0 | 1.0 | 1.0 | None | 3 | 3 | us-cw-133693, us-cw-470271, us-cw-133699, us-cw-470337, us-cw-133694, us-cw-133698 |
| SEC EX-21 | 18 | scc_5 | 0.5 | 0.5 | 0.5 | 0.5 | 21 | None | 4 | us-cw-1196, us-cw-42654, us-cw-130, us-cw-1280, us-cw-1180, us-cw-822, us-cw-118216, us-cw-3379182, us-cw-590085 |

几个关键观察：

- `SEC scc_1`：SA final 只保留 0.5，但 archive 恢复到 1.0。这是典型的“曾经找到，最后被挤掉”。
- `Debian ruby3.1`：archive 从 0.0 提升到 0.5，但仍然没有收齐。这说明不是所有失败都能靠后处理修复。
- `SEC 18-node`：best diag 也只有 0.5，说明当前 rollout 虽然看到过 root+witness 同窗，但没有形成可稳定选出的完整风险对。

## 4. 当前 archive 策略

Archive 子图是 blind 的，不看 GT：

```text
score(node) =
  2.0 * local_risk_subgraph_count
  + 1.0 * repair_entry_count
  + 2.0 * conflict_endpoint_count
  + 5.0 * one_time_OC_bonus
  + 1.0 * prefix_selected_count
  + 8.0 * early_prefix_selected_count(rollout <= 30)
```

然后保留 `ceil(0.45 * SCC_size)` 个节点，最少 4 个。

这个策略刻意没有强行保护 conflict pair，因为当前 traces 里 pair edge 噪声偏多，强制保护 pair 反而会把子图塞满。pair 信息现在只作为解释性 evidence 输出。

## 5. 下一步建议

1. 先把 Evidence archive 作为报告指标加入正式实验口径，但明确标注为 **post-hoc blind retention**。
2. 暂时不要改 SA-MCGS 搜索主循环。
3. 下一步再做一个小型消融：
   - no prefix memory
   - prefix memory only
   - OC bonus only
   - pair-protected archive
4. 如果消融确认 prefix memory 是主要收益，再把它转成 SA-MCGS 的稳定子图输出。
5. 真正改搜索时，再考虑 risk-aware seed boost 和 pair-seeking expansion。

## 6. 输出文件

- Enriched JSON: `rollout_evidence_archive_b100_long_real_gpt4o_20260514.json`
- Summary figure: `rollout_evidence_archive_summary.png`
- Case figure: `rollout_evidence_archive_cases.png`

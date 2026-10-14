# Experiment V1 · Gold-replay 冒烟

> **Exploratory · Gold replay · Not LFP-MCGS**  
> 这轮只验证数据管线、source acquisition 压力、动态 frontier 的简单可用性，以及 state transposition 是否值得进入 V2。它没有调用 LLM，也没有运行 MCTS/MCGS。

## 冻结设置

| 数据 | 样本 | 作用 |
|---|---:|---|
| ProofWriter OWA D5 dev | 60 | curated hard slice：positive-Horn、predicate-SCC、ground-instance deletion-causal query |
| StepGame test 冻结子集 | 60 | curated hard slice：从 NL spatial facts 获取证据并做 exact recursive closure |
| CLUTRR clean | 12 | 独立 executor sanity；没有 selection pressure，不进入 policy 比较 |

主预算为 `MAC`、`2×MAC`、`min(N, 3×MAC)`。MAC 是 gold minimum source cover，只用于筛样本、归一化预算和 lower bound，不参与可部署策略选 action。

比较项：

- `source_order`：原始记录顺序；
- `random`：5 个固定种子；
- `static_surface`：只按 query 与未读原文的表面词项/实体相关性固定排序；
- `dynamic_frontier`：ProofWriter 用已读 program 的 proof obligations；StepGame 用已读 facts 的 entity components。二者都只借助免费原文 / cheap lexical-entity index 重排，未读取 source 的 formal outcome 不可见；
- `gold_minimum_proof_lower_bound`：泄漏 gold proof 的成本下界，不是方法。

## 初步结果

Verified Answer Recovery @ `2×MAC`：

| 数据 | Random | Static surface | Dynamic frontier | Gold lower bound |
|---|---:|---:|---:|---:|
| ProofWriter D5 | 3.0% | 1.7% | **15.0%** | 100% |
| StepGame | 8.0% | 16.7% | **96.7%** | 100% |

在这个 oracle executor / free-text-and-entity-index 的 V1 access model 下，动态 frontier 出现了正向描述性信号；ProofWriter 仍远未解决，恰好说明“找到局部线索”与“组合完整递归证明”之间还有较大距离。StepGame 的动态策略本质是 acquired-graph connectivity frontier，不是 closure-feedback 证据。CLUTRR 12/12 query 被独立 closure executor 恢复，median query round 为 3，但 clean release 没有可用于调度比较的 distractor pressure。

12 cases / dataset、depth≤4 的 state census 给出约 95% 的 combinatorial acquisition-order duplication 上界；它由 N/depth/顺序可交换性决定，不是实际 TT hit rate，更不是 MCGS 已取得 accuracy/cost 收益。ProofWriter 中 closure-signature compression 为 83.6%；同一 closure 对应不同 coverage/action mask，因此 V2 **不能只按 closure 合并状态**。

## 现在能说 / 不能说

能说：

- 三类 released/oracle symbolic artifact 能稳定经过 exact executor / closure verification；
- 两个冻结切片都有预算化 source selection 压力；
- 不窥视未读 formal outcome 的 dynamic frontier 值得进入 V2；ProofWriter 是 dual-polarity proof-obligation/closure-aware lexical frontier，StepGame 是 entity-connectivity frontier；
- order-duplication 理论上界足够大，值得实现严格 state-sharing 对照。

不能说：

- LFP-MCGS 已经优于 Greedy / Beam / TreeMCTS；
- LLM 能可靠抽取这些 facts / rules；
- state merging 已带来真实收益；
- SCC topology 的因果优势已被证明；
- D3 或论文 GO gate 已关闭。

## 复现

```bash
python3 2026NAACL/LFP-MCGS/experiments/v1_smoke/run_experiment_v1.py
```

产物：

- `config.json`：运行前冻结的设置；
- `results/experiment_v1_results.json`：机器可读结果与 frozen case IDs；
- `results/experiment_v1_trials.jsonl`：1,080 条 per-case / per-seed 序列和指标；
- `results/experiment_v1_manifest.json`：输入、脚本、配置和结果 SHA-256。

同一输入连续运行两次得到相同 result SHA-256：

```text
（以 `experiment_v1_manifest.json` 中的当前 result SHA-256 为准）
```

历史后续是 V2/V3；当前确认路线已改为：在 SA-MCGS 的真实循环文档与 local windows 上，
比较同一个通用 LLM 在 matched test-time compute 下的 Direct / CoT / agent、Greedy / Beam
与 committed-KB + online-LFP feedback 方法。TreeMCTS 只作为关闭 exact state sharing 的内部消融。

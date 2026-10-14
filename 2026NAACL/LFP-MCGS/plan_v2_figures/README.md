# Research Plan V2 figures

> **历史图归档：**这些图对应 2026-08-18 的 ProofWriter-first / matched-simulator 计划，其中 `pφ`、TreeMCTS 主对比与旧 generality stack 已不再是当前口径。当前方案见 [`../LFP_MCGS_RESEARCH_PLAN_V2.md`](../LFP_MCGS_RESEARCH_PLAN_V2.md)：真实 document SCC + local-window PUCT + committed KB + online LFP feedback；核心数据改为 topology-controlled SCC intervention，主 baseline 改为 matched-compute 强通用 LLM。旧图只用于追溯，不进入论文。

| Figure | Purpose |
|---|---|
| `01_claim_evidence_chain` | 五个核心 claim 与决定性实验、主指标和否决门槛 |
| `02_algorithm_and_search_graph` | 区分 predicate recursion、grounded productive trace、fixed-program LFP chain 与 exact transposition graph，并定义无泄漏 sketch rollout |
| `03_generality_evidence_stack` | task-aligned topology/language/model 泛化、错误隔离与外域 interface 证据分层 |
| `04_baseline_and_ablation` | matched-simulator scheduler controls / method-native systems 两层公平性、双 endpoint、预算协议与六项原子消融 |

重新生成：

```bash
NODE_PATH=/path/to/node_modules node generate_plan_v2_figures.mjs
```

脚本同时输出 SVG 和 PNG；Markdown 默认引用 PNG，SVG 用于论文或后续编辑。

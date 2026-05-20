# E1. Naive Output-burden Control

目的：控制 Naive 的输出 schema 负担。输入仍是完整 CUAD 长 SCC；区别只是轻量版不再要求完整 `global_ranking` 和逐节点 `clause_evaluations`，只输出 `top_risk_nodes` 与 `risk_subgraph_nodes`。

- Status summary: `{'done': 16}`.
- Matched full-vs-lite records: `32`.
- 解释口径：E1 只回答 Naive 的 JSON/输出负担问题，不替换主实验的 Naive direct-subgraph baseline。

| Scope | N | Errors | Root@3 | Risk-any | Risk-all | Compression | Avg subgraph | Avg prompt words | Avg time sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lite_all_records | 32 | 8 | 22% | 47% | 12% | 83% | 4.50 | 13241 | 342.4 |
| matched_main_full_direct_subgraph | 32 | 28 | 6% | 9% | 0% | 84% | 4.50 | 10641 | 46.3 |
| matched_lite_direct_subgraph | 32 | 8 | 22% | 47% | 12% | 83% | 4.50 | 13241 | 342.4 |

## Reviewer-facing Takeaway

- 如果轻量 Naive 的报错显著下降，说明 CUAD 长合同的一部分失败来自 whole-SCC one-shot 的输出格式压力。
- 如果轻量 Naive 的 Risk-all 仍明显低于 SA-MCGS，则说明差距不只是 JSON/schema，而是长环结构搜索与证据保留问题。
- 这组结果应放 appendix / robustness，不进入主表。

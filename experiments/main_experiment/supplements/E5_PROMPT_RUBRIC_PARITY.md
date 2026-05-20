# E5. Prompt / Rubric Parity

- Shared semantic audit version: `shared_graph_risk_rubric_v1`
- Shared semantic hash: `345549c32f20ec3a`
- 兼容性：没有在已完成实验后新增 prompt block；这是对已有通用 wording 的抽象记录。

## Shared Risk Rubric

```text
## Shared Risk Rubric
You are analyzing a directed graph of interdependent records. Each node contains a record. Each directed edge indicates that one record depends on, constrains, references, modifies, or otherwise affects another record.

A record or relation is risky if it is structurally inconsistent, mutually incompatible, underspecified, or high-impact under the visible graph context. For each visible record, assign a risk_score from 0.0 (no meaningful structural concern) to 1.0 (severe structural concern). Use only the visible node text and visible directed edges. Explain concrete conflicts using exact record IDs and evidence from the input. Do not assume domain-specific error types.
```

## Common Terms Audit

| Term | Naive prompt | SA window prompt |
|---|---:|---:|
| `directed graph of interdependent records` | yes | no |
| `depends on, constrains, references, modifies` | yes | yes |
| `structurally inconsistent` | yes | yes |
| `mutually incompatible` | yes | yes |
| `underspecified` | yes | yes |
| `high-impact` | yes | yes |
| `risk_score` | yes | yes |
| `record IDs` | yes | no |

## Adapter Difference

- Naive adapter: one-shot full SCC, requires a whole-SCC ranking and a direct risk subgraph.
- SA-MCGS adapter: repeated local windows, same risk semantics, plus local evidence fields for search aggregation.
- 公平性结论：风险判断标准一致；差异来自输入范围和搜索/聚合机制，而不是领域专用找错提示。

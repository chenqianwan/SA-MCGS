# Stage-1 formal 硬门禁

结论：**PASS**；matrix 68/68，valid cells 68/68。

| Arm | Cells valid | Network fail/calls | Logical first-fail | Recovered | Exhausted | Est. USD |
|---|---:|---:|---:|---:|---:|---:|
| full-sa-mcgs-rerun | 17/17 | 1/995 | 1 | 1 | 0 | $9.6111 |
| no-relation-first-memory | 17/17 | 1/979 | 1 | 1 | 0 | $9.2426 |
| no-critical-pair-ledger-revisit | 17/17 | 1/993 | 2 | 2 | 0 | $9.6081 |
| random-local-window-selection | 17/17 | 0/967 | 2 | 2 | 0 | $8.9997 |

- Exhausted rollout 保留在原 arm 的 strict denominator，不整 cell 重跑。
- 本 phase 本地调用账本：$34.948035。
- XHub 账户同期总扣减：$64.891886（并行任务污染，仅交叉核验）。

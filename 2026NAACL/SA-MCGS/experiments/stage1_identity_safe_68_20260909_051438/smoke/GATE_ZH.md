# Stage-1 smoke 硬门禁

结论：**PASS**；matrix 12/12，valid cells 12/12。

| Arm | Cells valid | Network fail/calls | Logical first-fail | Recovered | Exhausted | Est. USD |
|---|---:|---:|---:|---:|---:|---:|
| full-sa-mcgs-rerun | 3/3 | 0/181 | 6 | 5 | 1 | $3.0338 |
| no-relation-first-memory | 3/3 | 1/184 | 4 | 4 | 0 | $2.9803 |
| no-critical-pair-ledger-revisit | 3/3 | 0/184 | 10 | 10 | 0 | $3.1601 |
| random-local-window-selection | 3/3 | 2/195 | 13 | 11 | 2 | $3.2589 |

- Exhausted rollout 保留在原 arm 的 strict denominator，不整 cell 重跑。
- 本 phase 本地调用账本：$12.433140。
- XHub 账户同期总扣减：$32.767688（并行任务污染，仅交叉核验）。
- formal 68 cells 保守经验包络：$48.664278。
- 非选择性复用 order-8 四格后，新付费 64 cells 包络：$46.150830。
- smoke + 新付费64总包络：$58.583970 / $60.00，余量 $1.416030。

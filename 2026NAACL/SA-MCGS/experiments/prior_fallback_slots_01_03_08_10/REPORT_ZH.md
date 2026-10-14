# Relation-prior 冻结 fallback 报告

生成时间：2026-09-09T22:48:26+0800。输出隔离目录：`prior_fallback_slots_01_03_08_10`。

该 fallback 只使用结果盲选并预冻结的 slots 01/03/08/10。执行顺序严格来自 fallback manifest 的 16 cells；8 个 nominal cells 仅引用 parent cost 结果，不复制、不重跑。invalid 保留在每个 model/profile 的固定 4-case strict denominator 内，且不换 case、不自动重试。

## 当前门禁

Parent cost 72/72：True；nominal parity：8/8；fallback 新 cells：attempted=16、valid=16、invalid=0、missing=0。

## Strict table

| Model | Profile | Planned | Attempted | Valid | Invalid | Missing | Root@3 strict | Risk-any strict | Risk-all strict |
|---|---|---|---|---|---|---|---|---|---|
| gpt-4o | minus20 | 4 | 4 | 4 | 0 | 0 | 0.7500 | 1.0000 | 1.0000 |
| gpt-4o | nominal | 4 | 4 | 4 | 0 | 0 | 1.0000 | 1.0000 | 0.7500 |
| gpt-4o | plus20 | 4 | 4 | 4 | 0 | 0 | 0.7500 | 1.0000 | 1.0000 |
| gemini-2.5-pro | minus20 | 4 | 4 | 4 | 0 | 0 | 1.0000 | 1.0000 | 0.7500 |
| gemini-2.5-pro | nominal | 4 | 4 | 4 | 0 | 0 | 0.7500 | 1.0000 | 0.7500 |
| gemini-2.5-pro | plus20 | 4 | 4 | 4 | 0 | 0 | 1.0000 | 1.0000 | 0.7500 |

## 成本与审计

Fallback 新 cells 的 provider-token × 冻结 XHub list-rate 累计为 $17.810895。当前缺失尾部保守投影为 $0.000000，另需启动参数传入且不少于 $10 的 closeout reserve。共享账户余额不用于本线归因。

完整身份、配置、prompt/schema、价格、预算、nominal 引用与执行状态审计位于 `preflight/`；逐 cell append-only 账本为 `budget_ledger.jsonl`。

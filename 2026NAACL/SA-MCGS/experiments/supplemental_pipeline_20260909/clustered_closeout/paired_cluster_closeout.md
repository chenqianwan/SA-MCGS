# SCC 等权配对统计收尾

生成时间：2026-09-10T10:13:33+0800。两条输入实验均已通过 terminal、identity、hash、ledger 与 strict-denominator 门禁。Bootstrap 固定为 20,000 次、seed 8229，cluster unit 为 physical SCC。

## Cost / reliability：三方法严格性能

| Model | Method | Metric | Success / 12 | Strict rate | 95% cluster-bootstrap CI | Invalid cells |
|---|---|---|---:|---:|---:|---:|
| gpt-4o | One-shot | root@3 | 4/12 | 33.3% | [8.3%, 58.3%] | 3 |
| gpt-4o | One-shot | risk_any | 7/12 | 58.3% | [33.3%, 83.3%] | 3 |
| gpt-4o | One-shot | risk_all | 3/12 | 25.0% | [0.0%, 50.0%] | 3 |
| gpt-4o | LEA | root@3 | 10/12 | 83.3% | [58.3%, 100.0%] | 0 |
| gpt-4o | LEA | risk_any | 11/12 | 91.7% | [75.0%, 100.0%] | 0 |
| gpt-4o | LEA | risk_all | 5/12 | 41.7% | [16.7%, 66.7%] | 0 |
| gpt-4o | SA-MCGS | root@3 | 11/12 | 91.7% | [75.0%, 100.0%] | 0 |
| gpt-4o | SA-MCGS | risk_any | 12/12 | 100.0% | [100.0%, 100.0%] | 0 |
| gpt-4o | SA-MCGS | risk_all | 10/12 | 83.3% | [58.3%, 100.0%] | 0 |
| gemini-2.5-pro | One-shot | root@3 | 12/12 | 100.0% | [100.0%, 100.0%] | 0 |
| gemini-2.5-pro | One-shot | risk_any | 12/12 | 100.0% | [100.0%, 100.0%] | 0 |
| gemini-2.5-pro | One-shot | risk_all | 12/12 | 100.0% | [100.0%, 100.0%] | 0 |
| gemini-2.5-pro | LEA | root@3 | 9/12 | 75.0% | [50.0%, 100.0%] | 0 |
| gemini-2.5-pro | LEA | risk_any | 12/12 | 100.0% | [100.0%, 100.0%] | 0 |
| gemini-2.5-pro | LEA | risk_all | 10/12 | 83.3% | [58.3%, 100.0%] | 0 |
| gemini-2.5-pro | SA-MCGS | root@3 | 11/12 | 91.7% | [75.0%, 100.0%] | 0 |
| gemini-2.5-pro | SA-MCGS | risk_any | 12/12 | 100.0% | [100.0%, 100.0%] | 0 |
| gemini-2.5-pro | SA-MCGS | risk_all | 11/12 | 91.7% | [75.0%, 100.0%] | 0 |

## Cost / reliability：SA-MCGS − LEA 配对差值

| Model | Metric | Delta | 95% paired CI | Better / tied / worse |
|---|---|---:|---:|---:|
| gpt-4o | root@3 | 8.3% | [0.0%, 25.0%] | 1 / 11 / 0 |
| gpt-4o | risk_any | 8.3% | [0.0%, 25.0%] | 1 / 11 / 0 |
| gpt-4o | risk_all | 41.7% | [8.3%, 75.0%] | 6 / 5 / 1 |
| gemini-2.5-pro | root@3 | 16.7% | [0.0%, 41.7%] | 2 / 10 / 0 |
| gemini-2.5-pro | risk_any | 0.0% | [0.0%, 0.0%] | 0 / 12 / 0 |
| gemini-2.5-pro | risk_all | 8.3% | [-16.7%, 33.3%] | 2 / 9 / 1 |

## Relation-prior：扰动 − nominal 配对差值

| Model | Profile | Metric | Delta | 95% paired CI | Better / tied / worse |
|---|---|---|---:|---:|---:|
| gpt-4o | minus20 | root@3 | -25.0% | [-75.0%, 0.0%] | 0 / 3 / 1 |
| gpt-4o | minus20 | risk_any | 0.0% | [0.0%, 0.0%] | 0 / 4 / 0 |
| gpt-4o | minus20 | risk_all | 25.0% | [0.0%, 75.0%] | 1 / 3 / 0 |
| gpt-4o | plus20 | root@3 | -25.0% | [-75.0%, 0.0%] | 0 / 3 / 1 |
| gpt-4o | plus20 | risk_any | 0.0% | [0.0%, 0.0%] | 0 / 4 / 0 |
| gpt-4o | plus20 | risk_all | 25.0% | [0.0%, 75.0%] | 1 / 3 / 0 |
| gemini-2.5-pro | minus20 | root@3 | 25.0% | [0.0%, 75.0%] | 1 / 3 / 0 |
| gemini-2.5-pro | minus20 | risk_any | 0.0% | [0.0%, 0.0%] | 0 / 4 / 0 |
| gemini-2.5-pro | minus20 | risk_all | 0.0% | [0.0%, 0.0%] | 0 / 4 / 0 |
| gemini-2.5-pro | plus20 | root@3 | 25.0% | [0.0%, 75.0%] | 1 / 3 / 0 |
| gemini-2.5-pro | plus20 | risk_any | 0.0% | [0.0%, 0.0%] | 0 / 4 / 0 |
| gemini-2.5-pro | plus20 | risk_all | 0.0% | [0.0%, 0.0%] | 0 / 4 / 0 |

Relation-prior 区间仅基于预冻结的 4 个不同 SCC，属于探索性敏感度描述；不据此宣称统计显著或无差异。所有 invalid/未定义布尔值均按严格分母计 0，未做 valid-only 删除。

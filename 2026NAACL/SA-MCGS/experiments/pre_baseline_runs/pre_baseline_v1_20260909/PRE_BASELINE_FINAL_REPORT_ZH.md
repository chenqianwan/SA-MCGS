# Pre 公平基线最终报告

状态：**冻结范围已完成**。本轮完成 two-model one-shot 36 个正式 cell，并对原始 pre SA-MCGS 的 GPT-4o 10 个、Gemini 2.5 Pro 14 个 strict-invalid 各执行一次 exact retry。原始 invalid 未覆盖，post 与 pre LEA 未重跑。

## 严格结果

| 方法/分母 | 模型 | attempted | valid | invalid | assert | abstain |
|---|---|---:|---:|---:|---:|---:|
| one-shot 正式首试 | GPT-4o | 18 | 12 | 6 | 12 | 0 |
| one-shot 正式首试 | Gemini 2.5 Pro | 18 | 18 | 0 | 18 | 0 |
| **one-shot 正式首试合计** |  | **36** | **30** | **6** | **30** | **0** |
| SA 原始首试（reliability） | GPT-4o | 18 | 8 | 10 | 8 | 0 |
| SA 原始首试（reliability） | Gemini 2.5 Pro | 18 | 4 | 14 | 4 | 0 |
| **SA 原始首试合计** |  | **36** | **12** | **24** | **12** | **0** |
| SA exact retry | GPT-4o | 10 | 7 | 3 | 7 | 0 |
| SA exact retry | Gemini 2.5 Pro | 14 | 14 | 0 | 14 | 0 |
| **SA exact retry 合计** |  | **24** | **21** | **3** | **21** | **0** |

SA 合并唯一-cell 可用性为 33/36：GPT-4o 18 个中 15 个可用，Gemini 18 个中 18 个可用。首试 reliability 分母仍是 36 attempted / 24 invalid；retry 成功不会回写首试成功率。GPT retry 后余下 3 个 strict-invalid 已保留，不再选择性重试。

## 成本

| 批次 | calls | tokens | estimated USD |
|---|---:|---:|---:|
| 2-cell paid smoke | 2 | 11,170 | $0.088029 |
| one-shot 正式 36 | 60 | 2,138,785 | $7.779534 |
| SA GPT retry 10 | 527 | 2,053,394 | $11.478373 |
| SA Gemini retry 14 | 613 | 2,958,594 | $15.288545 |
| **全线** | **1,202** | **7,161,943** | **$34.634480** |

全线低于 $55 硬上限，余量 $20.365520。1,202/1,202 API calls transport-success；最长单调用 379.50 秒，低于 900 秒冻结超时。XHub 最终账户快照 $819.228642；账户由并发任务共享，因此本线归因以独立 call/token ledger 为准。

## 完整性

- 18 个冻结 pre source 均为恰好一个 Tarjan SCC；source manifest SHA-256 为 `5872e4c255e5b099a1f3af68a8e4c396ec0bb1a2d8ddaf5da6b41af563777035`。
- one-shot protocol fingerprint：`sha256:2d9aba5aeec944b33cac56599ec787d6b03b4b89b21e86eae96716b9b12c9cf8`。
- SA 原始与 retry protocol fingerprint：`sha256:873882b0f28e64bd6abef9fc99d122b8334e45144c75dfdc90fa516862674bd9`。
- 原始 invalid、retry plan、retry result 的 ID 集在两个模型上均完全相等；36 个 one-shot case UID 全部唯一。
- 所有新结果均为 `condition=pre`、`inject_mode=false`、`unmodified=true`，嵌套 identity 与顶层指纹一致。
- 机器可读汇总见 `summary.json`；逐项 digest 见 `integrity_audit.json`；完整 calls/tokens 见 `budget_ledger.json`。

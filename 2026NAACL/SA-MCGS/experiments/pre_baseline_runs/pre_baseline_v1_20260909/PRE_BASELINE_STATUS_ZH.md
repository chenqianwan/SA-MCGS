# Pre 公平基线闭环状态（2026-09-09）

## 结论

本轮已完成冻结范围内的全部新增调用：two-model pre one-shot `18 × 2 = 36` 个正式 cell，以及对原始 pre SA-MCGS strict-invalid 的精确重试（GPT-4o 10 个、Gemini 2.5 Pro 14 个）。没有重跑 post，也没有重跑 pre LEA。

- one-shot 正式首试：36/36 已尝试，30 strict-valid，6 strict-invalid；GPT-4o 为 12/18 valid，Gemini 2.5 Pro 为 18/18 valid。
- SA-MCGS 原始首试保持原样：GPT-4o 8/18 valid、10/18 invalid；Gemini 2.5 Pro 4/18 valid、14/18 invalid。
- SA-MCGS exact retry：GPT-4o 7/10 valid、3/10 invalid；Gemini 2.5 Pro 14/14 valid、0 invalid。
- 合并“原始有效结果 + 一次精确重试有效结果”后，SA-MCGS 可分析的唯一 cell 为 33/36：GPT-4o 18 个中 15 个可用，Gemini 18 个中 18 个可用。GPT 剩余 3 个 strict-invalid 不再选择性重试。
- 全线新增调用（含通过门禁的 2-cell paid smoke）共 1,202 calls、7,161,943 tokens，按冻结 XHub pricing 估算为 **$34.634480**；低于本线 $55 硬上限，余量 $20.365520。

## 严格分母

| 方法/视图 | 模型 | attempted | valid | invalid | assert | abstain | strict-valid rate |
|---|---|---:|---:|---:|---:|---:|---:|
| one-shot 正式首试 | GPT-4o | 18 | 12 | 6 | 12 | 0 | 66.67% |
| one-shot 正式首试 | Gemini 2.5 Pro | 18 | 18 | 0 | 18 | 0 | 100.00% |
| one-shot 正式首试 | 合计 | 36 | 30 | 6 | 30 | 0 | 83.33% |
| SA 原始首试（reliability denominator） | GPT-4o | 18 | 8 | 10 | 8 | 0 | 44.44% |
| SA 原始首试（reliability denominator） | Gemini 2.5 Pro | 18 | 4 | 14 | 4 | 0 | 22.22% |
| SA 原始首试（reliability denominator） | 合计 | 36 | 12 | 24 | 12 | 0 | 33.33% |
| SA exact retry（单独分母） | GPT-4o | 10 | 7 | 3 | 7 | 0 | 70.00% |
| SA exact retry（单独分母） | Gemini 2.5 Pro | 14 | 14 | 0 | 14 | 0 | 100.00% |
| SA exact retry（单独分母） | 合计 | 24 | 21 | 3 | 21 | 0 | 87.50% |
| SA 合并唯一-cell 可用性 | GPT-4o | 18 | 15 | 3 unresolved | 15 | 0 | 83.33% |
| SA 合并唯一-cell 可用性 | Gemini 2.5 Pro | 18 | 18 | 0 unresolved | 18 | 0 | 100.00% |
| SA 合并唯一-cell 可用性 | 合计 | 36 | 33 | 3 unresolved | 33 | 0 | 91.67% |

原始首试的 24 个 invalid 始终保留在首试 reliability denominator 中。retry 只作为单独的恢复尝试报告；不能用 retry 的 21 个成功结果回填并改写“首试成功率”。若审计所有 API 尝试，则 SA 为 60 次尝试、33 valid、27 invalid；该口径包含重复 cell，只用于 reliability audit，不用于唯一-cell 方法效果比较。

## Invalid 说明

- one-shot 的 6 个 invalid 均发生在 GPT-4o：模型在冻结 schema 重试后仍缺少至少一个 exact clause ID 的评价。API/transport 均成功，原始输出及 terminal validation event 已保留。
- GPT SA retry 的 3 个 invalid 分别为一个缺失 exact clause evaluation、两个非 JSON object。API/transport 均成功，未再次选择性重跑。
- Gemini SA retry 的 14 个结果全部通过 strict schema。

## 身份与协议门禁

- 冻结源：18 个 pre source SCC；领域分布 BGB 3、CUAD 10、SEC-Ex21 5；每个 source 都验证为恰好一个 Tarjan SCC。
- source manifest SHA-256：`sha256:5872e4c255e5b099a1f3af68a8e4c396ec0bb1a2d8ddaf5da6b41af563777035`。
- one-shot plan fingerprint：`sha256:c8b19a8b76845ea24f86bd0969e72098253e09038597f835c57e561d6ff203f4`。
- one-shot protocol fingerprint：`sha256:2d9aba5aeec944b33cac56599ec787d6b03b4b89b21e86eae96716b9b12c9cf8`。
- SA protocol fingerprint：`sha256:873882b0f28e64bd6abef9fc99d122b8334e45144c75dfdc90fa516862674bd9`；原始首试与两组 retry 完全一致。
- 36 个 one-shot 结果有 36 个唯一 case UID；所有结果均为 `condition=pre`、`inject_mode=false`、`unmodified=true`，且嵌套 identity 与顶层内容指纹一致。
- GPT/Gemini 原始 invalid ID 集、retry plan ID 集和 retry result ID 集分别逐项相等；哈希见 `integrity_audit.json`。
- 原始 first-attempt 文件保留在 `experiments/sa_runs/`，retry 写入独立目录。原始结果最新 mtime 仍为 2026-08-29。

## 成本账本

| 批次 | cells | calls | prompt tokens | completion tokens | total tokens | estimated USD |
|---|---:|---:|---:|---:|---:|---:|
| one-shot smoke v1（pre-API parser 诊断） | 2 | 0 | 0 | 0 | 0 | $0.000000 |
| one-shot smoke v2（门禁通过） | 2 | 2 | 2,900 | 8,270 | 11,170 | $0.088029 |
| one-shot 正式 36 | 36 | 60 | 1,694,027 | 444,758 | 2,138,785 | $7.779534 |
| SA GPT exact retry 10 | 10 | 527 | 1,207,409 | 845,985 | 2,053,394 | $11.478373 |
| SA Gemini exact retry 14 | 14 | 613 | 1,633,988 | 1,324,606 | 2,958,594 | $15.288545 |
| **全线新增调用（含 paid smoke）** | 62 paid attempts | **1,202** | **4,538,324** | **2,623,619** | **7,161,943** | **$34.634480** |

正式批次、不计 paid smoke 的估算为 $34.546451。全程 1,202/1,202 API calls transport-success，最大单调用耗时 379.50 秒，低于冻结的 900 秒超时。

XHub 账户最终快照为 $819.228642。相对全局起点 $907.078988 的账户差是 $87.850346；相对本线开始前快照 $905.006092 的账户差是 $85.777450。由于 Stage-1/cost 等任务共享同一账户并发运行，这两个账户差只能交叉核验，不能归因成本；本线归因以独立 call/token ledger 的 $34.634480 为准。

## 产物

- `one_shot_full/`：正式 36-cell one-shot 结果、identity preflight、case plan、call log 和汇总 CSV。
- `sa_retry_gpt10/`：GPT 原始 10 个 invalid 的一次精确 retry。
- `sa_retry_gemini14/`：Gemini 原始 14 个 invalid 的一次精确 retry。
- `pre_baseline_results.csv`：模型 × 方法 × denominator 结果表。
- `budget_ledger.json`：calls、tokens、估算美元与共享账户交叉快照。
- `integrity_audit.json`：身份、协议、ID 集及原始结果保留校验。

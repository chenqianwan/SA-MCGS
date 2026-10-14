# LEA 更新状态（2026-08-29）

当前论文模型恢复为 **GPT-4o + Gemini 2.5 Pro**。

| 部分 | 状态 | 结果 |
|---|---|---|
| GPT-4o post | 完成 | 补跑 12 个 identity-repair cases；合并旧结果后 36/36 exact、0 invalid。 |
| Gemini post | 完成 | 补跑 11 个 identity-repair cases；另 1 个 SEC case 直接复用旧 exact 结果；合并后 36/36 exact、0 invalid。 |
| GPT-4o pre | 完成 | 18/18 跑完：16 个有效 assertion、2 个 CUAD strict-invalid。 |
| Gemini pre | 完成 | 18/18 跑完：17 个 assertion、1 个 abstention、0 invalid；280/280 API calls 成功。 |
| Post coverage audit | 完成 | one-shot、LEA、SA-MCGS 在两个模型上均无缺失或 identity mismatch；`rerun_scope.csv` 为 0 行。 |
| 专家打标页面 | 无需更新 | 页面不展示模型输出，36 个 post variants 与待标文本没有变化。 |

## 36 个 post variants 上的 LEA

| 模型 | Root@3 | Risk-any | Risk-all | 平均压缩率 |
|---|---:|---:|---:|---:|
| GPT-4o | 27/36（75.0%） | 34/36（94.4%） | 10/36（27.8%） | 51.0% |
| Gemini 2.5 Pro | 32/36（88.9%） | 36/36（100%） | 30/36（83.3%） | 51.0% |

这是冻结的 36-case 专家审计子集，不替代 rebuttal 的 matched-160 统计。

## 18 个 pre originals 上的 LEA 诊断

| 模型 | 完成 | assertion | abstention | strict-invalid |
|---|---:|---:|---:|---:|
| GPT-4o | 18/18 | 16 | 0 | 2 |
| Gemini 2.5 Pro | 18/18 | 17 | 1 | 0 |

固定口径：pre 不存在注入 ground truth，因此不计算 Root@3、Risk-any 或 Risk-all；上表只是系统输出分布，必须等专家标签冻结后才能计算自然冲突识别、over-reporting 与 abstention 指标。API/JSON/schema 失败计 strict-invalid，不能计作 abstention。

主要结果目录：

- `../lea_runs/lea_post_gpt12_20260829/`
- `../lea_runs/lea_post_gemini_smoke_20260829/`
- `../lea_runs/lea_post_gemini_remaining10_20260829/`
- `../lea_runs/lea_pre_gpt18_20260829/`
- `../lea_runs/lea_pre_gemini18_20260829/`

此前 Qwen 目标的 scope、preflight 与 provider-failure 日志保留为历史审计材料，但已 superseded，不进入当前论文模型对。

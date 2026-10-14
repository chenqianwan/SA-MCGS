# LEA 补跑汇总

数据状态：**PARTIAL（未完成）**；稳定身份核验通过的 LEA 结果 **240/320**。
历史复用 147/147，新增完成 93/173。

| 模型 | 已有/目标 | 严格无效 | 待完成 | 全80指标可用 |
|---|---:|---:|---:|---|
| gpt-4o | 80/80 | 0 | 0 | 是 |
| gemini-2.5-pro | 80/80 | 0 | 0 | 是 |
| qwen2.5-72b | 0/80 | 0 | 80 | 否 |
| deepseek-v3 | 80/80 | 0 | 0 | 是 |

以下指标仅包含已完成全部80案例的模型；严格无效结果保留在检测指标分母中。

| 模型 | Root@3 | Risk-any | Risk-all | Compression（有效输出） |
|---|---:|---:|---:|---:|
| gpt-4o | 78.8% | 96.2% | 43.8% | 51.3% |
| gemini-2.5-pro | 87.5% | 100.0% | 83.8% | 51.3% |
| deepseek-v3 | 78.8% | 100.0% | 76.2% | 51.3% |

未完成分组的完整范围均值留空；不能把当前已完成子集的均值当作80案例结果。
已生成三方法共同集合：**240 个模型×案例对，720 条方法记录**；这是当前可用共同子集。
三方法输出分别使用 One-shot 的 direct_risk_subgraph_nodes、LEA 的 lea_risk_subgraph_nodes、SA 的 core_evidence_risk_subgraph_nodes。严格无效的 Root@3/Risk-any/Risk-all 记0，Compression 留空，仅对有效输出平均。

补跑账本：已结算或保守记账 **$6.4458**，未结算预留 **$0.0000**，合计承诺上界 **$6.4458 / $50**。
历史 LEA token 用量按冻结单价换算的成本单独列出，不代表历史账单，也不计入本次50美元增量额度。原始 One-shot/SA 无 token 记录时保留空值。

身份/配置异常：0；缓存指标与按最终输出重算差异：0。
明细见 full320_case_metrics.csv、full320_breakdown.csv、matched_3method_case_metrics.csv、matched_3method_summary.csv 和 verification.json。

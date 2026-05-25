# Boosted Naive Baseline Report

状态：boosted Naive 补充实验报告；当前 main baseline 使用 `oracle_risk_top3`，`self_top3` 和 `oracle_compression_top3` 作为附录/diagnostic controls。

- Raw attempts: `3200`
- Top-k aggregation: `Top-3`
- Errors recorded in denominator: `800`
- Observed tokens: prompt `39,972,656`, completion `11,659,377`, total `51,632,033`

## Aggregate

| Selector | N | Root@3 | Risk-any | Risk-all | Compression | Mean valid attempts | Avg selected tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| self_top3 | 320 | 52.1% | 74.5% | 51.6% | 59.6% | 7.50 | 20,112 |
| oracle_risk_top3 | 320 | 58.4% | 79.4% | 62.2% | 60.0% | 7.50 | 20,051 |
| oracle_compression_top3 | 320 | 53.3% | 74.7% | 47.4% | 63.5% | 7.50 | 19,988 |

## Notes

- `self_top3` 不看 GT，只按 JSON 完整性、模型自报风险强度、证据一致性和子图合理性选择样本。
- `oracle_risk_top3` 枚举所有 Top-3 组合，优先最大化 Root@3 / Risk-any / Risk-all 三个风险指标的均衡下限，其次最大化三者均值，compression 只作 tie-break。
- `oracle_compression_top3` 枚举所有 Top-3 组合，优先最大化 compression，风险均衡只作 tie-break。
- Oracle selectors 使用真实评估指标进行选择；`oracle_risk_top3` 作为当前 main oracle-risk baseline，`self_top3` 保留为非 oracle selector。
- 如果某个 model-case 没有任何有效输出，则该 case 记为失败。

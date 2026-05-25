# Boosted Naive Baseline Report

状态：独立补充实验报告；不更新 paper / LaTeX / paper figures。

- Raw attempts: `780`
- Top-k aggregation: `Top-3`
- Errors recorded in denominator: `26`
- Observed tokens: prompt `3,533,207`, completion `2,687,762`, total `6,220,969`

## Aggregate

| Selector | N | Root@3 | Risk-any | Risk-all | Compression | Mean valid attempts | Avg selected tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| self_top3 | 156 | 53.3% | 91.9% | 59.7% | 60.6% | 4.83 | 8,477 |
| oracle_top3 | 156 | 58.0% | 95.3% | 68.5% | 59.8% | 4.83 | 8,463 |

## Notes

- `self_top3` 不看 GT，只按 JSON 完整性、模型自报风险强度、证据一致性和子图合理性选择样本。
- `oracle_top3` 看真实指标，只作为 boosted Naive 的上界，不应作为默认论文主结果。
- 如果某个 model-case 没有任何有效输出，则该 case 记为失败。

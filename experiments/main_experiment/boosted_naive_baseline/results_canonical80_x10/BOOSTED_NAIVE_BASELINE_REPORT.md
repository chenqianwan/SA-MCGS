# Boosted Naive Baseline Report

状态：独立补充实验报告；不更新 paper / LaTeX / paper figures。

- Raw attempts: `3162`
- Top-k aggregation: `Top-3`
- Errors recorded in denominator: `777`
- Observed tokens: prompt `39,159,372`, completion `11,520,584`, total `50,679,956`

## Aggregate

| Selector | N | Root@3 | Risk-any | Risk-all | Compression | Mean valid attempts | Avg selected tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| self_top3 | 320 | 52.1% | 74.5% | 51.6% | 59.6% | 7.45 | 20,109 |
| oracle_risk_top3 | 320 | 58.3% | 79.4% | 62.1% | 60.0% | 7.45 | 20,047 |
| oracle_compression_top3 | 320 | 53.2% | 74.7% | 47.3% | 63.5% | 7.45 | 19,987 |

## Notes

- `self_top3` 不看 GT，只按 JSON 完整性、模型自报风险强度、证据一致性和子图合理性选择样本。
- `oracle_risk_top3` 枚举所有 Top-3 组合，优先最大化 Root@3 / Risk-any / Risk-all 三个风险指标的均衡下限，其次最大化三者均值，compression 只作 tie-break。
- `oracle_compression_top3` 枚举所有 Top-3 组合，优先最大化 compression，风险均衡只作 tie-break。
- Oracle selectors 看真实指标，只作为 boosted Naive 的上界，不应作为默认论文主结果。
- 如果某个 model-case 没有任何有效输出，则该 case 记为失败。

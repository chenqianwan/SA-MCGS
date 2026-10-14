# Stage-1 identity-safe 四臂配对消融

状态：smoke 诊断完成。

历史 frozen Full 缺少原始 prompt/config hash，因此本批次将 Full 与三个消融全部 contemporaneous 重跑。
所有指标使用 strict all-case denominator；invalid 保留并按未命中计。置信区间以 physical source SCC 聚类 bootstrap。

| Variant | Attempted | Valid | Invalid | Root@3 | Risk-any | Risk-all | API calls | Tokens | Est. USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS (contemporaneous rerun) | 3 | 3 | 0 | 100.0% | 100.0% | 100.0% | 181 | 576015 | $3.0338 |
| No relation-first memory | 3 | 3 | 0 | 100.0% | 100.0% | 66.7% | 184 | 562223 | $2.9803 |
| No critical-pair ledger/revisit | 3 | 3 | 0 | 100.0% | 66.7% | 66.7% | 184 | 595270 | $3.1601 |
| Random local-window selection | 3 | 3 | 0 | 100.0% | 100.0% | 66.7% | 195 | 600108 | $3.2589 |

- physical source SCC clusters：3
- case-level 首轮失败/重试：0/0
- rollout 首次 JSON/transport 失败：33
- 显式 JSON/transport retry attempts：42
- 本 phase 估算成本：$12.433140
- smoke + formal 累计估算成本：$12.433140 / $60.00

详细逐 case 结果、聚类区间与哈希索引分别见 `stage1_case_results_strict.csv`、
`stage1_clustered_uncertainty.json` 与 `results_manifest.json`。

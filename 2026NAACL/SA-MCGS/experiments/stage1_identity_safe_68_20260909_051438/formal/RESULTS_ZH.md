# Stage-1 identity-safe 四臂配对消融

状态：正式批次完成。

历史 frozen Full 缺少原始 prompt/config hash，因此本批次将 Full 与三个消融全部 contemporaneous 重跑。
所有指标使用 strict all-case denominator；invalid 保留并按未命中计。置信区间以 physical source SCC 聚类 bootstrap。

| Variant | Attempted | Valid | Invalid | Root@3 | Risk-any | Risk-all | API calls | Tokens | Est. USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS (contemporaneous rerun) | 17 | 17 | 0 | 100.0% | 100.0% | 88.2% | 995 | 1637548 | $9.6111 |
| No relation-first memory | 17 | 17 | 0 | 100.0% | 100.0% | 100.0% | 979 | 1575503 | $9.2426 |
| No critical-pair ledger/revisit | 17 | 17 | 0 | 100.0% | 100.0% | 100.0% | 993 | 1640748 | $9.6081 |
| Random local-window selection | 17 | 17 | 0 | 100.0% | 100.0% | 82.4% | 967 | 1531561 | $8.9997 |

- physical source SCC clusters：5
- case-level 首轮失败/重试：0/0
- rollout 首次 JSON/transport 失败：5
- 显式 JSON/transport retry attempts：5
- 本 phase 估算成本：$34.948035
- smoke + formal 累计估算成本：$47.381175 / $60.00

详细逐 case 结果、聚类区间与哈希索引分别见 `stage1_case_results_strict.csv`、
`stage1_clustered_uncertainty.json` 与 `results_manifest.json`。

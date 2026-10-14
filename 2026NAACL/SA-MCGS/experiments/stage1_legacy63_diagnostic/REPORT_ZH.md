# Stage-1 legacy 63-case 零 API 诊断附录

## 边界

本附录固定排除 identity-safe 重跑覆盖的 17 个 order：
`8,14,17,18,20,39,40,44,60,69,70,71,72,73,74,79,80`。剩余 63 个历史 case 仅作为独立 legacy 证据保存；
不能与本次同期修复的 17 个 SEC case 拼接成新的 80-case headline。全程只读历史 raw JSON，
没有调用模型或任何付费 API。

历史 Full raw 没有 prompt/config hash，且三个 shard 的 `run_config.json` 只列出三条
同期 ablation arm、未列出 Full。因此，即便四臂 raw case/injection/source-SCC 身份逐格一致，
任何 `vs Full` 差值仍只属于 diagnostic，不是严格同期 paired control 结论。

## 描述结果

每臂均为 63/63 有效 case、17 个 physical/source SCC。`case` 为 63-case 普通均值；
`SCC-eq` 为先在 SCC 内平均、再对 17 个 source SCC 等权平均。

| arm | Root@3 case / SCC-eq | Risk-any case / SCC-eq | Risk-all case / SCC-eq |
|---|---:|---:|---:|
| full-sa-mcgs-locked | 82.5% / 83.8% | 100.0% / 100.0% | 74.6% / 76.5% |
| no-relation-first-memory | 85.7% / 86.8% | 98.4% / 98.5% | 79.4% / 80.9% |
| no-critical-pair-ledger-revisit | 79.4% / 80.9% | 85.7% / 86.8% | 44.4% / 48.5% |
| random-local-window-selection | 87.3% / 88.2% | 95.2% / 95.6% | 68.3% / 70.6% |

source-SCC case 数分布：1 个 SCC×1 cases，1 个 SCC×2 cases，15 个 SCC×4 cases。这里不计算 CI 或显著性检验。

## 可复跑与审计

```bash
cd /Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS
python3 experiments/stage1_legacy63_diagnostic/build_legacy63_diagnostic.py
```

`legacy63_case_metrics.csv` 的每一行都携带 raw 文件路径和 SHA-256；三项数值分别直接读取
raw 的 `root_top3_hit`、`core_evidence_contains_any_risk_node` 和
`core_evidence_contains_all_risk_nodes`。旧 summary 只消费 case/order/arm/result path/subset
五个 locator 字段，旧 summary 的 metric/aggregate 列没有参与估计。输入锁、identity 检查、
配置检查与限制见 `legacy63_summary.json` 和 `frozen_protocol.json`。

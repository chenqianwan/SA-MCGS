# Qwen3.5-9B 三方法实验结果

模型：Qwen/Qwen3.5-9B，官方 BF16，非 thinking，固定版本 c202236235762e1c871ad0ccb60c8ee5ba337b9a。

80 个注入案例 × 3 方法，共 240 个科学终态；其中 227 个有效结果、13 个严格失败、0 个运行故障、0 个缺失。严格失败按既定规则纳入检测分母并记 0，不重跑；压缩率只统计有效结果。80 个案例来自 20 个物理 SCC，本报告仅作描述性比较。

GPU 作业 395518 于 2026-09-25 02:39:06（香港时间）完成实验；Slurm sacct 确认 COMPLETED、退出码 0:0，已释放 GPU。仅使用节点本地推理，外部 API 支出 $0（不含集群资源成本）。

| 方法 | Root@3 | Risk-any | Risk-all | 压缩率（有效 n） | 有效 | 严格失败 | 运行故障 | 缺失 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| One-shot | 12.50% (10/80) | 53.75% (43/80) | 12.50% (10/80) | 62.70% (n=67) | 67 | 13 | 0 | 0 |
| LEA | 56.25% (45/80) | 91.25% (73/80) | 63.75% (51/80) | 51.26% (n=80) | 80 | 0 | 0 | 0 |
| SA-MCGS | 62.50% (50/80) | 86.25% (69/80) | 63.75% (51/80) | 67.25% (n=80) | 80 | 0 | 0 | 0 |

压缩率定义为 1 − 保留节点数 / 原 SCC 节点数。三方法的检测实际可评估分母均为 80，也等于计划分母；压缩率分母分别为 67、80、80。

SA-MCGS 相对 LEA：Root@3 提高 6.25 个百分点，Risk-any 降低 5.00 个百分点，Risk-all 持平，平均压缩率提高 15.99 个百分点。该结果体现检测与压缩之间的取舍，不能概括为所有指标均改善。

按冻结规则保留 JSON 解析耗尽后的原有回退：LEA 有 12 个案例涉及 13 个窗口，SA-MCGS 有 21 个案例涉及 48 个窗口。这些窗口不是端点故障，也未据此重跑或筛除案例。

结果来源与核验：下载清单中的 245 个文件均已逐一验证 SHA-256；冻结分析器从原始输出与80案例计划独立重算，身份/版本/案例/覆盖计数核验通过。分析器不重新加载原图或重复推理。另一路未导入分析器函数的独立复核也已通过，指标与计数一致。

- [原始结果与下载清单](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/downloaded_final/qwen35/download_manifest.json)
- [逐案例指标](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/final_analysis/qwen35/qwen3_5-9b_case_metrics.json)
- [完整分析与输入 SHA](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/final_analysis/qwen35/qwen3_5-9b_analysis.json)

Kimi 实验尚未完成，仍由原作业 395516 持续运行。本文件仅交付已完成的 Qwen 结果；全部 480 格实验尚未齐全。

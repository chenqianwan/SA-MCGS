# Kimi 与 Qwen3.5 三方法实验最终结果

两模型均已完成，每模型 80 个案例 × 3 种方法，共 480 个科学终态：422 个有效结果、58 个严格失败、0 个运行故障、0 个缺失。原始结果均已下载并逐文件验证 SHA-256，冻结分析器已独立重算全部指标；另一路未导入分析器函数的独立复核也已通过。

Kimi GPU 作业 395516 于 2026-09-25 08:16:19 结束，Qwen GPU 作业 395518 于 02:39:07 结束（香港时间）。Slurm 确认两者 COMPLETED、退出码 0:0，活动队列为空，GPU 分配已释放。各模型均仅启动服务一次，没有端点恢复或作业重提。外部 API 支出 $0，未折算集群资源成本。

## 指标与统计口径

严格失败按既定规则纳入检测分母并记 0，压缩率缺失。运行故障独立统计，不作为模型严格失败。本次所有方法的实际可评估分母均为 80，与计划分母一致。压缩率 = 1 − 保留节点数 / 原 SCC 节点数，取有效结果的案例均值；表中 n 为压缩率实际分母。

| 模型 | 方法 | Root@3 | Risk-any | Risk-all | 压缩率（n） | 严格失败 | 运行故障 |
|---|---|---:|---:|---:|---:|---:|---:|
| Kimi-VL-A3B-Instruct | One-shot | 6.25% (5/80) | 42.50% (34/80) | 37.50% (30/80) | 9.24% (n=35) | 45 | 0 |
| Kimi-VL-A3B-Instruct | LEA | 5.00% (4/80) | 90.00% (72/80) | 18.75% (15/80) | 51.26% (n=80) | 0 | 0 |
| Kimi-VL-A3B-Instruct | SA-MCGS | 5.00% (4/80) | 87.50% (70/80) | 32.50% (26/80) | 51.85% (n=80) | 0 | 0 |
| Qwen3.5-9B | One-shot | 12.50% (10/80) | 53.75% (43/80) | 12.50% (10/80) | 62.70% (n=67) | 13 | 0 |
| Qwen3.5-9B | LEA | 56.25% (45/80) | 91.25% (73/80) | 63.75% (51/80) | 51.26% (n=80) | 0 | 0 |
| Qwen3.5-9B | SA-MCGS | 62.50% (50/80) | 86.25% (69/80) | 63.75% (51/80) | 67.25% (n=80) | 0 | 0 |

## SA-MCGS 相对 LEA

| 模型 | Root@3 变化 | Risk-any 变化 | Risk-all 变化 | 压缩率变化 |
|---|---:|---:|---:|---:|
| Kimi-VL-A3B-Instruct | 0.00 个百分点 | −2.50 个百分点 | +13.75 个百分点 | +0.59 个百分点 |
| Qwen3.5-9B | +6.25 个百分点 | −5.00 个百分点 | 0.00 个百分点 | +15.99 个百分点 |

Qwen 的 SA-MCGS 提高了根因定位和压缩率，完整风险覆盖持平，但至少一项风险覆盖下降。Kimi 的完整风险覆盖提高，根因定位仍为 5%，压缩率接近 LEA，至少一项风险覆盖略降。两个模型均不能概括为所有指标全面改善。

Kimi One-shot 的 Risk-all 高于窗口方法，但其有效输出平均压缩率仅 9.24%，保留了更多节点，且 45/80 案例严格失败。比较时应同时呈现覆盖、压缩与失败率。

80 个注入案例共享 20 个物理 SCC；这些是描述性结果，不能把 80 个案例视作 80 个独立图来作显著性或普适性结论。

## 保留的解析回退与严格失败

下表为按冻结流程执行最多 3 次 JSON 解析后仍耗尽的案例/窗口记录。窗口耗尽采用原有回退，属于保留的科学执行路径，不是端点运行故障，也未据此重跑。窗口回退可以发生在整体有效结果内，不能与严格失败数量相加。

| 模型 | 方法 | 涉及案例 | 耗尽窗口 | 严格失败 |
|---|---|---:|---:|---:|
| Kimi-VL-A3B-Instruct | One-shot | 13 | 13 | 45 |
| Kimi-VL-A3B-Instruct | LEA | 40 | 179 | 0 |
| Kimi-VL-A3B-Instruct | SA-MCGS | 40 | 457 | 0 |
| Qwen3.5-9B | One-shot | 0 | 0 | 13 |
| Qwen3.5-9B | LEA | 12 | 13 | 0 |
| Qwen3.5-9B | SA-MCGS | 21 | 48 | 0 |

两模型严格失败均仅出现在 One-shot，记录的错误类型均为 ValueError。原始结果、失败原因和缓存按原协议保留，未按分数重跑。

## 冻结协议与核验文件

- Kimi：moonshotai/Kimi-VL-A3B-Instruct，版本 398eede0903cd983a2bfa0cc634e9ac1d843f375；Qwen：Qwen/Qwen3.5-9B，版本 c202236235762e1c871ad0ccb60c8ee5ba337b9a。均为官方 BF16，纯文本，单 H800 同节点运行服务与脚本；Qwen 非 thinking。
- One-shot 输出上限 12000、温度 0；LEA 窗口 4、输出 2048、温度 0.4；SA budget 60、窗口 4、输出 2048、温度 0.4、内部并发 8。成功和严格失败均未重跑，冻结科学代码未改变。
- 490 个下载文件均通过 SHA-256 校验。分析核对冻结 80 案例身份、模型与协议、节点成员及结果计数；不重新加载原图或重复推理。

- [联合分析 JSON](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/final_analysis/combined_analysis.json)
- [Kimi 下载清单](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/downloaded_final/kimi/download_manifest.json)
- [Qwen 下载清单](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/downloaded_final/qwen35/download_manifest.json)
- [Kimi 逐案例指标](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/final_analysis/kimi-vl-a3b-instruct_case_metrics.json)
- [Qwen 逐案例指标](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/final_analysis/qwen3_5-9b_case_metrics.json)
- [Kimi 独立复核](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/deployment_audit/kimi_final_secondary_audit.json)
- [Qwen 独立复核](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/deployment_audit/qwen35_final_secondary_audit.json)
- [两 GPU 释放证据](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/deployment_audit/final_gpu_release.json)

两模型收集与复核完成后，定时检查 kimi-qwen3-5 已暂停。

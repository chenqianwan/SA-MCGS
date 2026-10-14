# Kimi / Qwen3.5：严格失败案例按指标补入后的结果

按用户于 2026-09-25 指定的新口径：只重新解析 58 个原严格失败案例；其余 422 个成功案例直接沿用已有指标，数值未变。全部案例均纳入统计，能计算的指标照常计入，缺失或不能确定的指标记 0。每个模型、每种方法、每项指标（包括压缩率）的分母统一为 80。

本次仅离线处理现有缓存，新增模型调用 0 次、API 支出 $0。原始响应和原始运行诊断保留；原“严格失败”标记不再屏蔽整例指标。

| 模型 | 方法 | Root@3 | Risk-any | Risk-all | 平均压缩率 | 分母 |
|---|---|---:|---:|---:|---:|---:|
| Kimi-VL-A3B-Instruct | One-shot | 11.25% (9/80) | 90.00% (72/80) | 70.00% (56/80) | 16.38% | 80 |
| Kimi-VL-A3B-Instruct | LEA | 5.00% (4/80) | 90.00% (72/80) | 18.75% (15/80) | 51.26% | 80 |
| Kimi-VL-A3B-Instruct | SA-MCGS | 5.00% (4/80) | 87.50% (70/80) | 32.50% (26/80) | 51.85% | 80 |
| Qwen3.5-9B | One-shot | 15.00% (12/80) | 60.00% (48/80) | 13.75% (11/80) | 64.73% | 80 |
| Qwen3.5-9B | LEA | 56.25% (45/80) | 91.25% (73/80) | 63.75% (51/80) | 51.26% | 80 |
| Qwen3.5-9B | SA-MCGS | 62.50% (50/80) | 86.25% (69/80) | 63.75% (51/80) | 67.25% | 80 |

## 仅对原严格失败案例的补入情况

| 模型 | 处理案例 | 有可用排名 | 有可用风险节点 | 可计算压缩率 | 新增 Root@3 / Risk-any / Risk-all 命中 |
|---|---:|---:|---:|---:|---|
| Kimi-VL-A3B-Instruct | 45 | 45 | 44 | 44 | 4 / 38 / 26 |
| Qwen3.5-9B | 13 | 13 | 13 | 13 | 2 / 5 / 1 |

## 固定的取值规则

- 每例固定使用原流程最后一次缓存响应；不从多次响应中挑选分数较好的结果。
- 排名只取完整输出的条目，沿用原唯一节点别名映射，非法 ID 排除，重复 ID 保留首次；按显式 rank、原始位置排序，取实际可用的前 3 项。缺失节点不补入，缺失排名不通过 risk_score 猜测。
- 风险指标使用已完整输出的节点 ID，规范化后去重。已输出节点能够证明命中则记 1，否则记 0；整个字段缺失同样记 0。
- 压缩率仅在风险列表完整闭合且有有效节点时计算为 1 − 保留节点数 / SCC 节点数；列表截断、缺失或无法解析时记 0。所有案例都参与平均。
- 使用字符串和转义感知的 JSON 前缀解析。唯一的错层字段、唯一且明确的数组内字段标签可以确定性提取；重复键或有歧义的字段不猜测。
- 本次改变了失败处理口径和压缩率分母，属于用户指定的新版评估；原严格版报告保留作对照，不将两种口径混用。LEA / SA-MCGS 因没有整例严格失败，指标不变。

## 复核与文件

- [逐例指标、58 例解析证据及汇总](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/parsing_recovery_audit_20260925/metricwise_results.json)
- [可复现的离线重算脚本](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/parsing_recovery_audit_20260925/rescore_strict_failures.py)
- [原始严格口径报告](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/final_analysis/FINAL_RESULTS_ZH.md)
- [独立复算记录](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/parsing_recovery_audit_20260925/metricwise_independent_review.json)

读取的原始文件均记录 SHA-256，并在结束时确认未变；422 个原成功案例逐行相等检查通过。解析与指标取值的19项测试通过，独立复算的461项检查通过。

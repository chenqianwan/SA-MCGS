# SA-MCGS：XHub 恢复后两天的全部补充实验简报

范围：本轮 XHub 恢复后启动的新跑、补跑及离线复核。付费运行集中在 **9 月 9 日完成，9 月 10 日完成最终统计收尾**；不是只汇总最后的 Cost/Prior。累计观测 token 按冻结 XHub 单价估算 **$136.60 / $200**，含预跑检查与中断恢复的已记录消耗，不是共享账户精确实扣。

**总判断：完成五项新跑/补跑，补齐四项离线统计与诊断，并准备好专家后处理。成本—完整性取舍和动态核心证据更清楚；搜索组件的贡献存在样本差异，不能概括成所有模块都必不可少。**

## 1. 这两天实际新跑、补跑了什么

Risk-all 指找全基准定义风险端点的比例；“有效”只表示输出通过格式/协议校验，不等于专家认定判断正确。

| 实验 | 本轮执行范围 | 结果与结论 |
|---|---|---|
| Stage-1 同期组件消融 | 17 个 SEC variants / 5 个源 SCC × 4 臂＝68 项，全部有效 | 完整算法 / 去关系记忆 / 去关键对重访 / 随机窗口的 Risk-all＝88.2 / 100 / 100 / 82.4%。这个小子集未支持前两个组件的正向贡献 |
| Pre One-shot 基线 | 18 个未注入源 SCC × 2 模型＝36 项新运行 | 30 有效、6 无效；自然原文基线已补齐，正确率与误报仍待专家标签 |
| Pre SA 失败项补跑 | 对原有 24 个无效项各重试一次 | 21 项重试成功，3 项仍无效；结合旧首试，36 项中可用输出从 12 增至 33。不能把 33/36 写成首次成功率 |
| Cost / reliability | 12 个源 SCC × 2 模型 × 3 方法＝72 项 | 69 有效、3 无效；补齐公平成本比较，效果与代价见下表 |
| Prior 先验敏感性 | 4 个预冻结源 SCC × 2 模型 × ±20%＝16 项新运行，复用 8 个默认值结果 | 全部有效。扰动后 GPT-4o Risk-all 75%→100%，Gemini 保持 75%；Risk-any 均为 100%。端点完整性未下降，但 Root@3 有波动，仅作小样本探索 |

另完成预跑检查：Stage-1 12 项中 4 项验收后纳入上述 68 项，另 8 项仅诊断；Pre 另 2 项。费用均已计入，不重复扩大正式样本数。

## 2. 公平成本比较：更完整，但不是免费提升

相同 12 个源 SCC × 2 个模型 × 3 种方法，共 72 项。Risk-all 指是否找全基准定义的风险端点，越高越好；不是专家判定的法律风险准确率。

| 方法 | GPT-4o Risk-all ↑ | Gemini 2.5 Pro Risk-all ↑ | 平均 token / 项 ↓ |
|---|---:|---:|---:|
| One-shot（整段直接问一次） | 25.0% | 100.0% | 23,488 |
| LEA（局部证据聚合基线） | 41.7% | 83.3% | 63,702 |
| SA-MCGS | 83.3% | 91.7% | 203,364 |

每个模型/方法分母均为 12；token 列对两个模型等权平均。72 项中 69 有效、3 无效，3 个无效均为 GPT-4o One-shot，保留在性能与成本分母中。

结论：SA 的 token 约为 LEA 的 **3.2 倍**。GPT-4o 相对 LEA 提高 **41.7 个百分点**，SCC 配对 95% 区间为 [8.3, 75.0]；Gemini 仅提高 8.3 个百分点，区间 [−16.7, 33.3]，且 One-shot 最好。因此支持有条件的成本—效果取舍，不支持跨模型全面优越。

## 3. 同期补做的离线分析（零模型调用）

| 分析 | 关键结果 | 能支持的结论 |
|---|---|---|
| 新 Stage-1 的 SCC 等权统计 | 先在同源 variants 内平均，四臂 Risk-all＝88.3 / 100 / 100 / 85.0%；相对完整算法的区间均含 0 | 避免同一 SCC 多个注入版本被当成独立样本；组件贡献仍不确定 |
| 旧 63-case 消融复核 | 63 variants / 17 源 SCC，四臂 Risk-all＝74.6 / 79.4 / 44.4 / 68.3%（顺序同上） | 旧样本保留关键对重访的正向信号；但旧 Full 缺 prompt/config hash，只能作诊断，不能和新 17 个拼成严格 80-case 主表 |
| Stage-2 新增 SCC 配对区间 | 复用旧 80 variants / 20 源 SCC 回放：动态替换 75.0%，锁定不替换 37.5%；差值 +37.5 个百分点，95% 区间 [12.5, 60.0] | 支持动态核心改善最终证据完整性。本轮新增的是统计分析，不是重新跑 Stage-2，也不证明搜索轨迹改善 |
| Cost/Prior 最终配对统计 | 完成按源 SCC 的 20,000 次 bootstrap 与身份、账本、结果哈希核验 | GPT-4o 的 SA−LEA 完整性优势有支持；Gemini 差值不确定；Prior 仅 4 个 SCC，不外推普遍稳健性 |

上述两个 Stage-1 版本分别报告 variant 级与 SCC 等权比例，不混用分母。旧失败及重试记录均保留。Cost 另有 1 项 SA 经中断恢复才完成，恢复前后已观测 token 均计入成本；最终有效率不能冒充首次成功率。Prior 外层改为最多 4 任务并行、内部搜索仍为 1，耗时不能直接与串行默认值比较。

## 4. 专家准备、未完成项与最终口径

- **这两天新增的准备：** 专家导出合并、一致性统计、分歧裁决、标签冻结、证据质量与 SCC 聚类工具已完成，33 项合成测试通过。对应 42 个新增标注项（18 pre＋24 post），旧 12 项独立核验复用；测试数字不是专家结果。
- **仍未完成：** 真实标签与裁决，以及依赖标签的自然原文误报/弃答、证据召回、多余节点指标；之后再整合进论文。没有新增独立的 core-threshold sensitivity 批次。
- **此前结果仅复用：** 原 320 model-case 主实验、Post 36-case 基线、Pre LEA、Pre SA 首次结果、Stage-2 原回放；不算这两天新跑。
- **论文结论：** 以动态核心的证据完整性、模型相关的成本—效果取舍为主；关键对重访的历史信号与新子集差异如实并列，不再统一声称所有搜索组件都已被证明必要。

核验来源：[成本表](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/cost_prior_12case_gpt4o_gemini25pro_b60_v1/REPORT_ZH.md)（仅引用 Cost 部分；其中旧 48 项 Prior 计划已由 16 项子集替代）、[Cost/Prior 最终统计](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/supplemental_pipeline_20260909/clustered_closeout/paired_cluster_closeout.md)、[Stage-1](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage1_identity_safe_68_20260909_051438/formal/FINAL_REPORT_ZH.md)、[Pre](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/pre_baseline_runs/pre_baseline_v1_20260909/PRE_BASELINE_FINAL_REPORT_ZH.md)、[Stage-2](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage2_paired_replay_80case_identity_v1_final/stage2_paired_core_report.md)。

新增离线来源：[Stage-1 等权统计](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage1_identity_safe_68_20260909_051438/formal/SCC_EQUAL_INFERENCE_ZH.md)、[历史 63-case 复核](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage1_legacy63_diagnostic/REPORT_ZH.md)、[Stage-2 配对区间](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage2_paired_replay_80case_identity_v1_final/stage2_clustered_paired_inference.md)、[专家后处理审计](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/annotation_prep/analysis_v1/AUDIT_ZH.md)。

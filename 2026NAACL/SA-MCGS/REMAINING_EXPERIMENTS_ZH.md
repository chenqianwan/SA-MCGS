# SA-MCGS：ARR Oct 2026 剩余实验

> 目标 venue：NAACL 2027。状态核对日期：2026-09-10。  
> 本文件只记录尚未闭环的实验；旧 rebuttal 中身份不稳定的 LEA、Stage-1 和 cost 数字不得直接入稿。

**当前：Stage-1、Stage-2、pre 基线、Cost/Prior 付费与离线统计已完成；专家结果等作者标签。** 本轮观测列表价估算 US$136.60 / US$200；不整体重跑旧主实验。最终报告与执行限制见 `experiments/supplemental_pipeline_20260909/clustered_closeout/`。

## 已完成，不再重跑

- Stable identity：physical-SCC fingerprint 与严格 node-set 校验。
- Stage-2：80-case replacement core vs. locked no-replacement paired replay。
- Post 审计子集：36 cases × 2 models 的 one-shot、LEA、SA-MCGS coverage 已对齐。
- Pre：18 个 unmodified source SCC × 2 models 的 LEA 已完成。
- Stage-1：同期 Full + 三消融，68/68 valid；仅覆盖 17 个错配 SEC cases / 5 个 source SCC。
- Pre：one-shot 36 次与 SA 36 次首次运行、24 次预定 SA 重试已完成。
- 专家离线后处理：33 项合成测试通过；Stage-2 SCC 等权配对 CI 已生成，零 API。

## P0：投稿前必须完成

### 1. Stage-1 配对消融

- [x] 完成 `17 cases × 4 arms = 68 jobs`；旧 Full 缺少可核验 prompt/config hash，因此使用同期 Full。
- [x] identity、干预开关、逐 case evaluator 与 strict denominator 核验通过；68 valid、0 invalid。
- [x] 已有原 case-level 表及 SCC 等权离线补充，不混淆两个统计目标。

**结果口径：** Full / no-relation / no-critical / random 的 Risk-all 为 88.2 / 100 / 100 / 82.4%。这个 SEC 修复子集不支持前两组件的正向贡献，不能代表全部旧 80 cases；不沿用旧 −21.3/−11.3 pp。报告见 `experiments/stage1_identity_safe_68_20260909_051438/formal/`。

### 2. Cost / reliability 修复

- [x] 新冻结的 12 SCC × GPT-4o/Gemini 2.5 Pro × one-shot/LEA/SA = 72 cells 已完成：69 valid、3 invalid。当前批次单独成表，不混合旧 cost；旧 6 个不可验证 Naive cells 不进入新表。
- [x] 正式模型、预算、并发、重试与身份协议已经冻结，执行目录为 `experiments/cost_prior_12case_gpt4o_gemini25pro_b60_v1/`。
- [x] 已生成 calls、input/output tokens、strict performance、invalid rate；runtime 只作次要参考。
- [x] 执行说明区分总推理成本、并行耗时和中断恢复；恢复成功不当作首次成功。仍需整合入论文。

**入稿口径：** SA-MCGS 是以更多调用和 token 换取 endpoint completeness 的 cost-performance trade-off，不声称免费提升。

### 3. Pre 公平基线补齐

- [x] one-shot 36/36 已尝试，30 valid、6 invalid。
- [x] SA 首次 12/36 valid；预定 24 次重试已完成，最终输出可用 33/36，仍有 3 invalid。
- [x] 首次结果与重试账本分别保留；不能把 33/36 当作首次成功率。
- [ ] 标签冻结后，在固定 SCC/模型与预声明方法协议下计算专家指标。

**入稿口径：** Pre 不计算注入式 Risk-all；只在专家标签冻结后报告自然冲突识别、over-reporting、abstention 和证据定位。

### 4. 盲法专家审计

- [ ] 冻结不显示 pre/post 条件、LEA/SA-MCGS 输出或方法提示的正式 blind build；当前显示提示的页面仅作辅助复核。
- [ ] 核验旧 12 个 post cases 的逐 case 原始标注导出；能核验才直接复用。
- [ ] 标注 18 个 pre originals + 24 个新增 post variants：每位专家 42 项，三位专家共 126 份判断。
- [ ] 若旧 12-case 原始导出无法核验，则将其加入重新标注范围。
- [ ] 完成 adjudication、inter-annotator agreement、最终 label freeze 与 label hash。

固定字段：`target conflict / no target conflict / insufficient context`、minimal evidence、repair packet、confidence。

**入稿口径：** 18 个 pre SCC 用于 selected unmodified cases 上的自然冲突与 clean-negative 审计，不外推总体自然风险率；36 个 post variants 用于 endpoint recovery 的配对分析。

## P1：低成本但应完成

### 5. Subgraph cleanliness

- [x] 专家导入、IAA、裁决、freeze、cleanliness、bridge-aware 与 SCC 聚类工具及 33 项回归测试完成。
- [ ] 收到真实标签并冻结后，在固定输出上计算 expert-evidence recall、repair-packet coverage、excess-node rate 与 endpoint density。
- [ ] 同时报告 one-shot、LEA、SA-MCGS；桥接节点按预先定义的 bridge-aware 规则处理。

**入稿口径：** Compression 不等于 evidence precision；cleanliness 指标只证明返回子图的证据负担和覆盖程度。

### 6. Prior sensitivity

- [x] 已比较 relation-prior `nominal / -20% / +20%`：16/16 新 cells valid，复用 8 个 nominal。
- 使用预先按结构冻结的 slots 1/3/8/10 四域 fallback；不是完整 12-SCC / 48 新 cells 的版本。
- [x] identity、模型、预算及其余算法参数核验通过；外层并行变更单独留档，不比较并行 prior 与串行 nominal 的 runtime。

**入稿口径：** 该 4-SCC 子集的 Risk-any 未变、Risk-all 持平或提高，Root@3 有模型相关变化；只作探索性敏感度描述，不宣称普遍不敏感。

### 7. 聚类统计与统一验收

- [x] Stage-1/Stage-2 已提供先在 source SCC 内汇总的等权统计；Stage-2 Risk-all 差值 +37.5 pp，95% CI [12.5, 60.0] pp。
- [x] Cost/Prior 的 SCC 配对 bootstrap 区间已生成（20,000 次，seed 8229），完整性门禁通过。
- [ ] 真实专家结果待标签冻结后补齐同口径区间；三位专家不作为三个独立样本。
- [ ] 所有表同时保留 attempted、valid、invalid 和 strict all-case denominator。
- [ ] 冻结 manifest、prompt/config hash、聚合脚本和最终结果索引。

## 公平基线范围决策

当前 identity-safe 的公平比较覆盖冻结的 36-post、2-model 子集；旧 rebuttal matched-160 aggregate 不可使用。投稿前二选一：

1. **最小方案：** 保留 36-case 比较，并把公平性结论明确限制在该预定专家审计子集与两个模型；原 320-case oracle-risk 结果只作 non-deployable diagnostic。
2. **增强方案：** 重新完成 identity-safe matched-160 LEA，以支撑更广的公平基线结论。

不选择增强方案时，不得在摘要或结论中声称 SA-MCGS 跨四模型统一优于公平 graph-aware baseline。

## 推荐执行顺序

`冻结协议、候选集与 blind build → 专家盲标并冻结 label → 解盲方法结果 → cleanliness/prior sensitivity → clustered aggregation → 修改正文`

Stage-1、cost 和 pre one-shot/SA 可在盲标期间并行运行，但专家不得在 label freeze 前看到这些方法输出或汇总结果。

## 完成门槛

以下条件同时满足，才可把补充实验标为完成：

- Stage-1、cost、pre baseline 均有 identity-safe 的正式结果和 strict denominator；
- 专家标签来自冻结的 blind build，并完成 agreement/adjudication；
- cleanliness、prior sensitivity 和 source-SCC clustered uncertainty 均有可复现输出；
- 不使用旧错配数字，不隐藏不利模型或 invalid outputs，所有 claim 与实际实验范围一致。

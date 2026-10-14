# SA-MCGS 专家集增量计划

## 1. 固定原则

旧 12-case 专家审计及其论文结果全部保留：不重标、不重算、不替换原表，也不修改原来的 recognizability claim。新增工作只补 reviewer 要求的 pre-injection、clean/negative 和 naturally occurring cases。

固定中心口径：

> 旧 audit 说明注入的结构冲突对专家可识别；新增 audit 独立检查未经注入 SCC 上的过度报告、abstention 和自然冲突证据。两部分互补，但不合并成一个总分。

旧 12 cases 在原表中仍按 12 cases 报告。新增分析涉及 physical-SCC 统计时，对其中共享相同 SCC 的 variants 只聚类一次；这不改变旧结果，只避免在新增统计中重复计数。

## 2. 增量样本

| 部分 | 数量 | 是否重标 | 用途 |
|---|---:|---|---|
| 原有 injected expert audit | 12 cases | 否，直接沿用 | 注入风险 recognizability 与旧 endpoint 结果 |
| 对应 pre-哦哦好的injection originals | 7 个唯一 physical SCC | 是 | 相同原始 SCC 上的 conflict/over-reporting 对照 |
| Probability-sampled untouched | 24 个唯一 physical SCC | 是 | clean/negative、abstention 和 false-positive pilot |
| Independently enriched natural candidates | 12 个唯一 physical SCC | 是 | 提高找到自然正例的概率，验证自然 evidence localization |

本轮新增 **43 cases、129 份专家判断**。加入旧 12 cases 后，完整专家证据包包含 55 个 case presentations；按 physical SCC 去重后为 43 个独立 SCC。

核心仍覆盖 SEC EX-21、BGB、CUAD。Debian 只有在能找到软件依赖专家时单独追加，不与法律/合同专家结果混合。

## 3. 抽样与身份冻结

- Pre-injection track 只标旧 12 cases 对应的 7 个唯一原始 SCC，不重复展示相同原文。
- 每个 pre-injection case 回到 source graph 核验原始节点文本、typed edges 和 source hash。
- Track 主键使用稳定的 physical-SCC identity，不使用会随遍历顺序变化的 Tarjan `scc_id`。
- Untouched track 从冻结的 eligible SCC frame 中，按 domain × SCC size 分层随机抽取三域各 8 个；记录 seed、source revision 和排除项。
- Natural-candidate track 三域各 4 个，由模型无关结构规则、外部元数据或不参加最终标注的独立 scout 筛选。
- 不使用 SA-MCGS、LEA 或 Naive 的分数、core、ranking 和输出挑选自然案例。
- Untouched 不预先称为 clean；是否为正例、负例或上下文不足由专家决定。
- Random 与 enriched tracks 分表报告，不按标注结果替换样本，也不用于估计真实 prevalence。

## 4. 新增标注协议

旧标注材料与旧结果不动。新增 43 cases 使用与旧 audit 可对齐的字段：

1. **Case label**：存在结构冲突 / 未观察到目标冲突 / 上下文不足；置信度 1–5。
2. **Node label**：`clear issue / possibly relevant / no issue observed / uncertain`。
3. **Minimal evidence**：正例选择使冲突成立的最小节点集合和关键关系。
4. **Repair packet**：选择足以让审阅者理解和修复冲突的节点集合。
5. **Context**：是否需要 SCC 外材料，以及简短理由。

新增界面只展示完整 SCC 原始文本、中性段落 ID 和 typed directed edges，不展示任何方法输出。所有新增 cases 使用同一套说明和字段，确保正负例可直接比较。

“未观察到目标冲突”只表示没有识别到本文定义的结构冲突，不表示文档不存在任何其他法律、合规或技术风险。

## 5. 专家与质控

- 每个新增 case 仍由 3 位专家独立标注；优先邀请原三位专家，以保持判断尺度一致，缺位时使用同等领域资历的替代者。
- 正式开始前用 6 个不进入分析的 calibration cases 做一次短 pilot。
- 每次 session 控制在约 60–90 分钟，记录逐例耗时，减少长 CUAD cases 的疲劳影响。
- 保留全部原始判断；2/3 形成 provisional label。无多数、低置信度或 `insufficient context` case 再做 domain adjudication。
- 在运行或查看新增系统结果前，冻结新增 labels、minimal-evidence sets、repair packets 和 annotation bundle hash。
- 报告专家资历、招募/报酬、语言能力、agreement、adjudication rate 和 uncertain rate。

## 6. 指标与统计

| Case 类型 | 主要报告 |
|---|---|
| 旧 injected cases | 完全沿用旧 audit 数字与解释 |
| Pre-injection originals | expert conflict rate、no-conflict rate、context-needed rate；系统 abstention/over-reporting |
| Untouched expert positives | case sensitivity、expert-evidence recall、repair-packet coverage、excess-node rate |
| Untouched expert negatives | abstention/non-abstention、retained-node burden；只有冻结 no-risk rule 后才称 case-level FPR |
| Enriched natural positives | 发现数量、case sensitivity、expert-evidence recall 和典型案例 |

- 新增 case-level agreement 报 raw agreement 与 Krippendorff's alpha 或 Gwet's AC1；evidence sets 报 pairwise Jaccard。
- 统计单位为 physical SCC/document，不把 3 位专家的 129 份判断当成 129 个独立实验样本。
- Pre-injection 与旧 injected 结果只作对应 SCC 的描述性对照，不重新估计或改写旧 audit 数字。
- Probability-sampled 与 enriched tracks 始终分开；不产生 old + new pooled headline。
- 自然正例的 evidence set 称为 `expert-adjudicated evidence`，不沿用 injected benchmark 的 root/witness 或 `Risk-all` 命名。

## 7. 新增系统实验

标签冻结后，在新增的 43 cases 上比较 one-shot、LEA、SA-MCGS，覆盖两个代表模型，统一输入、输出 schema、context budget 和 abstention rule。

最小新增量为：

`43 cases × 3 methods × 2 models = 258 method-case runs`。

旧 injected 320-case benchmark 和旧 12-case expert audit 均不需要重跑。

## 8. 论文落位

- 原有 expert-audit 表及数字不修改。
- 主文新增一个紧凑的 `Natural and negative-case validation` 表，只放 pre-injection/untouched/natural 的 case-level 结果、abstention 和 evidence quality。
- 完整 sampling、逐领域结果、agreement、repair-packet overlap 和案例放附录。
- 旧 injected、随机 untouched、富集 natural 三类证据分别解释，不增加统一 accuracy 或统一 Risk-all。

建议新增口径：

> Building on the original injected-risk recognizability audit, we add expert-annotated pre-injection controls and untouched cyclic SCCs. These incremental evaluations measure over-reporting, abstention, and evidence localization on expert-adjudicated natural positives and negatives, without re-estimating the original audit or claiming population-level risk prevalence.

## 9. 工作量与完成标准

新增 `43 × 3 = 129` 份专家判断。按每例 15–20 分钟估计，标注约 32–43 expert-hours；培训、adjudication 和质控另需约 6–10 小时。系统侧新增约 258 runs。

进入主文的条件：

- 43 个新增 cases 的身份、source hash 和抽样来源均可追溯；
- labels 在系统运行/解盲前冻结；
- random 与 enriched tracks 没有样本或选择规则泄漏；
- 正负结果完整报告；
- 若自然正例太少，则 natural track 降为案例型 pilot，但旧 audit 与新增 negative-control 结果仍正常保留。

后续产物统一放入 `2026NAACL/SA-MCGS/expert_set/`。执行顺序：

`恢复 7 个唯一 pre-injection originals → 冻结 random/enriched sampling → 生成新增标注包 → 6-case pilot → 43-case 正式标注 → adjudication/label freeze → 258 runs → 分轨统计 → 增量入稿`。

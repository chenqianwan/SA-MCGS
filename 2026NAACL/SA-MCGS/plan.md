# SA-MCGS：ARR Oct 2026 修订计划（精简版）

> 执行状态更新：2026-09-22。本轮付费实验及 Cost/Prior 离线统计已完成，观测 token 按冻结单价估算 **US$136.60 / US$200**。三份专家标注（42 / 42 / 14）均已按作者确认的盲评过程和第三位裁决规则完成离线统计。正文、附录增补稿已写入；本轮新增 API 调用为 0。当前待作者核对、压页与投稿材料准备。

详细写作与最新数值以 [总修订方案](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/ARR_OCT2026_MASTER_REVISION_PLAN_ZH.md) 为准；保留原稿故事线，主结果升级为 full-SCC＋LEA 双基线比较，并整合消融、成本和专家结果；本次不新增付费实验。

修订标记：正文和附录的新增/改写用蓝色；被删除或替换的旧文保留并加删除线，未改动内容保持原样。以 `backups/latex_2026-09-22/` 为基准，LaTeX 标记开关可切换为无痕投稿版。

付费实验历史状态与报告见 `experiments/supplemental_pipeline_20260909/README.md`、`execution_status.json` 及 `clustered_closeout/`；本轮专家及写作状态以本计划开头和总方案为准。

本轮专家统计见 [报告](manuscript_revision_20260922/expert_analysis/REPORT_EN.md)：新 24 post 来自 14 sources，旧 12 原汇总分层保留。GPT 的 SA−LEA 最小证据召回提高 25.5 pp，Gemini 为 2.2 pp 且区间含零；自然原文 18 负例上各方法有效输出几乎均误报。首试和恢复后结果分开；GPT pre-LEA 首试 16/18 valid，恢复后 17/18，不能混写。

## 1. 项目与论文口径

- 工作分支：`2026NAACL/SA-MCGS`；本项目产物只写入 `2026NAACL/SA-MCGS/`，不进入 `2026NAACL/LFP-MCGS/`。
- 中心结论：SA-MCGS 在 cyclic-SCC structural-risk stress test 中，以更多 calls/tokens 换取更完整的 endpoint recovery；收益依赖模型与案例难度，定位为 decision support。
- 并发效率口径保留：更多 calls/tokens 不意味着等待时间同比例增加；内部 rollout 并发可缓解时间开销，沿用 rebuttal 的近似并行时间公式。不把外层批量并发写成单案例实测提速，不追加加速实验。
- 比较框架：full-SCC 基线＋结构化强基线 LEA，与 SA-MCGS 并列进入主要比较。保留原数据，不要求旧单基线主表原样保留；One-shot 与 GT-selected oracle 分开标明，消融仍相对 Full SA。
- Dynamic-core 沿用修正口径：`dynamic/replacement core` 相比 `locked-no-replacement core` 提高 endpoint completeness，不声称改变 rollout trajectory。
- 本文件取代旧的四轨专家集方案，后续只执行统一的 one-to-many pre/post audit：36 个 post variants 对应 18 个去重后的 pre originals。

## 2. Rebuttal 修复

| 项目 | 状态/动作 |
|---|---|
| Stable identity | 已完成；使用 physical-SCC fingerprint，Tarjan `scc_id` 仅作诊断 |
| Stage-2 core | 已完成 80-case paired replay；Risk-all 75.0% vs. 37.5%，SCC 聚类差值 CI 为 [12.5, 60.0] pp |
| Stage-1 | 同期 17 cases × 4 arms = 68/68 valid（5 个 SEC source SCC）；另已重算旧 63＋新 17 的描述性 80-case，不等于统一同期重跑 |
| LEA | 固定 GPT-4o + Gemini 2.5 Pro；post identity 修复与 18-pre LEA 均已完成，post 审计 0 rerun |
| Cost | 已完成 72/72：69 valid、3 invalid；calls/tokens、strict performance 及 SCC 配对区间已生成；中断恢复与首次有效性分开 |
| Pre 基线 | one-shot 36/36 已尝试，30 valid；SA 初次 12/36 valid，冻结的 24 次重试后可用 33/36；LEA 已完成 |
| Prior sensitivity | 冻结 4-SCC 子集的 16/16 扰动均 valid，复用 8 nominal；配对区间已生成，仅为探索性敏感度分析 |

Stage-1 本批 case-level Risk-all：Full 88.2%、no-relation 100%、no-critical-pair 100%、random-window 82.4%。这批结果不支持前两组件的正向独立贡献；旧 −21.3/−11.3 pp 不直接沿用。原始 case-level 表保留，另提供先在 SCC 内平均的等权统计。

旧 63 个身份一致案例另作零 API 诊断：Full / no-relation / no-critical / random 的 Risk-all 为 74.6 / 79.4 / 44.4 / 68.3%。历史 Full 缺 prompt/config hash，因此保留该信号，但不与新 17 cases 拼成严格 80-case 主表；见 `experiments/stage1_legacy63_diagnostic/REPORT_ZH.md`。

最新描述性 80-case 四臂 Risk-all 为 **77.50 / 83.75 / 56.25 / 71.25%**；完整 Root@3、Risk-any、压缩率见总方案第 4.4 节。Stage-2 的 Full 75.0% 使用原冻结轨迹，来源不同，不与此处的 Full 77.5% 混用。

关系记忆消融保留：正文简述“未显示一致独立收益，移除后 Risk-all 提高”，完整结果和成本放附录。移除后 Risk-any 仅少 1/80，压缩率不变；同期 17-case tokens/估算费用反而约少 3.8%，不硬解释为成本换收益。旧 rebuttal 已报告移除后 +5 pp，当前不是方向反转。

重投说明简洁交代数值更新的原因、范围和结论影响，区分修正与扩样，不统称“优化”；旧 rebuttal 原样保留。参见总方案第 9.3 节。

旧 320 model-case 主实验数据与旧 12-case expert-audit 汇总结果保留，不整体重跑；主比较表格及文字按双基线重组。LEA 当前已对齐 36 post × 2 模型，另有 12-SCC × 2 模型同期三方法对照，不等于已覆盖全 320。若需全 320 三方法网格，先核对 LEA 缺口，补跑范围与预算另定。

## 3. 统一的 one-to-many pre/post 审计

### 样本

- Post：已从主实验冻结 36 个 variants，其中包含旧 expert audit 的 12 个 cases；新增 24 个不依据方法输赢选择。最终 SEC、BGB、CUAD 各 12 个，四种 template 各 9 个。
- Pre：用 stable fingerprint 映射并去重后得到 18 个未注入 source SCC，覆盖主实验全部法律 source SCC。
- 每个 post 必须能映射到一个 pre；同一个 pre 可以对应多个 injection templates，因此 pre/post 数量不要求相等。

### 专家标注

- 完整审计集合为 18 个 pre originals + 36 个 post variants。
- 旧 audit 的 12 个 post cases 已定位，对应 7 个唯一 source SCC；旧论文汇总保留。两份旧原始导出已找到，待逐 case 核验后按可比字段复用，不推断或补造旧标签。
- 本轮新增集合为 18 个 pre + 24 个 post。前两位各完成 42 项；第三位已完成 14 个高分歧/不确定案例独立盲标（9 pre + 5 post，共 264 段），合计实际 98 份判断，不写成三人均全量标注。
- 使用相同二选一字段：冲突存在/不存在、判断充分/不充分，加 minimal evidence、repair packet、confidence。第三位页面不含前两位答案或筛选理由；按作者要求加入同源算法提示、案例注入状态及真实注入段落标记，顶部可一并隐藏全部提示。正式盲评需在专家阅读前隐藏并记录实际操作，旧答案不追溯改写。
- 筛选并集：存在性不同、任一不充分、任一信心 ≤2/5，或至少一位给出“存在且充分”且任一材料集合的 Jaccard <0.5。恰好 0.5 不纳入；不按模型输赢筛选。规则及独立页面见 [第三专家定向复核](annotation_prep/third_expert_review/README.md)。
- 三位实际全盲评已经作者明确确认，原始导出字段与文件保留。按作者收到结果后的明确指定，14 个复核项整体采用第三位完整答案：9 pre 为充分负例、5 post 为充分正例；不称三位一致或事前预注册裁决。未送审的 28 项保留双专家记录，不填造第三票或擅自合并不同证据集合。IAA 始终基于原始独立标注，双专家全量与第三位定向子集分开报告。见 [裁决记录](annotation_prep/third_expert_review/internal/adjudication_20260920/README_ZH.md)。
- 专家判断不当作独立数据样本；Natural 分析的样本量是 18，Post 计划 case 数是 36（本次新标 24）。统计先在每个 source SCC 内汇总多个 post variants，再进行比较，并按 fingerprint 聚类。

### 系统实验

- 比较 one-shot、LEA、SA-MCGS，固定使用 GPT-4o 与 Gemini 2.5 Pro，并统一 prompt、schema、context budget 与 abstention rule。
- Pre：$18 \times 3$ methods $\times 2$ models $=108$ 个主网格已全部尝试；另完成预定的 24 次 SA 重试。初次可靠性与重试后输出可用率分开报告，不覆盖首次失败。
- Post：36 个 cases 的 one-shot/SA-MCGS 主实验结果直接复用；LEA identity-mismatched cells（GPT-4o 12 个、Gemini 11 个）已补齐，不新增其他 post-SCC 主实验。

## 4. 指标与论文呈现

主结果采用 full-SCC＋LEA＋SA-MCGS 的比较框架；原 320 覆盖结果与已对齐三方法子集按组/panel 区分，LEA 不是仅放在末尾的补充表。Baseline 定义、主结果分析、摘要和结论同步更新。

专家审计表展示 one-to-many pre/post audit：Pre 在 18 个 unmodified source SCC 上报告自然冲突、expert-negative over-reporting 与 abstention；Post 在 36 个 injected variants 上报告 endpoint completeness、expert-evidence recall、repair-packet coverage、excess-node rate 及 call/token cost。one-shot、LEA、SA-MCGS 使用相同的 expert-grounded 指标。

原主实验的 benchmark-defined `Risk-all` 单独保留。Pre/post 比较不把 18 与 36 个原始行直接相减：主分析先对每个 source SCC 的 post variants 求均值，再进行 SCC-level matched comparison；模板级结果作为次分析。自然风险率只描述这 18 个 selected source SCC，不外推为整个领域的总体发生率；另报告排除旧 12 cases 的敏感性分析。

固定表述：

> We audit 36 injected variants derived from 18 distinct, unmodified source SCCs. Multiple conflict variants may originate from the same physical SCC; all uncertainty estimates are therefore clustered by source-SCC identity. The originals measure natural-case over-reporting, while the injected variants support matched analysis of endpoint recovery across conflict templates.

## 5. 执行顺序

`Cost/Prior 已完成；专家 42 / 42 / 14 已收齐，14 项第三位裁决已记录 → 按实际覆盖范围适配指标，并核验旧 12 原始导出 → expert-grounded 指标与聚类区间 → 修改正文与附录`。

原三专家全量分析工具见 `annotation_prep/analysis_v1/README.md`；当前为 binary 字段、两人全量加第三人定向复核，正式合并需适配实际覆盖范围，不能直接通过填充缺失标签套用旧三专家全量流程。14 项完整裁决标签已有可追溯记录；其余 28 项保留双专家证据集合，不声称全量唯一集合 gold 已冻结。

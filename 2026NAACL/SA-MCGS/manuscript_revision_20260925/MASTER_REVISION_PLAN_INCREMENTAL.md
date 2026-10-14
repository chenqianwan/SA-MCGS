# SA-MCGS：ARR October 总修订方案

更新：2026-09-28。目标：OA 3.5 / Meta 3.5。修订原则：保留原稿框架与故事线，按 rebuttal 增量补齐证据。正文与附录增补稿、专家离线统计已完成；旧 12 例保留原汇总，新 24 例单列，不补造旧标签。五模型主表与分析图已接入论文；本次按作者选择，将 Figure 4 替换为 D 逐案例配对收益图，并同步图注、结果文字和修改清单。

修订标记：以 `backups/latex_2026-09-22/` 为原稿基准，本轮论文新增及改写用绿色，旧蓝字可直接删除，原黑字采用删除线；方案和清单的新增改动继续标蓝，未改动内容保持原样。正文和附录采用同一规则。LaTeX 使用 `\revadd{新文}`、`\revdel{旧文}`、`\revreplace{旧文}{新文}`；`paper/latex/revision_markup.tex` 中的开关可导出无标记的投稿版。

本方案以 9 月 22 日修改 MD 为底稿，保留原有结构和未改文字；本次新增或替换的内容在[蓝字对照版](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20260925/output/pdf/MASTER_REVISION_PLAN_BLUE.pdf)中标蓝，原文保持黑色。

## 0. 先看结论

**本轮不改变原稿故事线，也不重构章节和贡献框架。以原投稿稿为基础，把 rebuttal 及后续修复实验补到对应位置，逐项回应评审短板。** 原评审已经认可问题、动机和系统完整性；这次重点补公平基线、组件消融、成本、敏感性和专家审计。

保留原有主线：

> 循环文档图中的相互依赖给普通树式推理带来困难 → SA-MCGS 通过 SCC 局部化、结构感知 Monte Carlo 搜索、关系证据记忆和动态 core 提取风险子图 → 四域五模型实验验证方法表现。

新增实验是这条主线的补充验证，不另起一个以 dynamic core 或成本为中心的故事。标题、问题设定、方法流程和主要章节顺序保留；已确认的五模型结果作为本轮主比较，原实验记录保留；**主结果改为双 baseline 框架：One-shot full-SCC 基线＋结构化强基线 LEA，SA-MCGS 同时与二者比较**。保留故事线不等于保留旧表版式；主要比较表、图注和相关结论按双基线重组，不再仅在旧单基线主表后追加 LEA。

| 补充内容 | 当前状态 | 怎样加入原稿 |
|---|---|---|
| 五模型主实验 | 每模型 80 案例、三方法结果已确认 | 用第 4.2 节完整主表更新结果，图表任务见第 7.3 节 |
| LEA 强基线 | 五模型 LEA 已补齐并纳入主表；同期 12-SCC 三方法比较已完成 | 与 full-SCC 基线并列进入主要结果、成本及专家方法对照，不只是补充验证 |
| Stage-1 / Stage-2 消融 | 同期 Stage-1 17-case 与 Stage-2 80-variant 回放已完成；另有 Stage-1 80-case 描述性汇总 | 区分实验范围；关系记忆正文简述、完整结果放附录，不更换全文贡献中心 |
| Cost / Prior | 已完成 | 在实验分析中增加紧凑成本表；Prior 简述及完整附录表 |
| 专家审计 | 两位各 42 项、第三位复核 14 项；裁决及离线指标完成 | 已加入正文和专家附录：18 pre 负例审计、新 24 post 的证据质量、原始一致性和恢复口径，详见第 8 节 |

面向双 3.5，本轮的完成标准是：**原稿认可的优点保留，reviewer 提出的短板有对应证据，新增结果与文字口径一致。** 不以重构论文作为进入下一轮的前提。模型和组件的结果差异仍如实呈现，但只在相关实验段落解释，不改成新的故事线。

**准备工作进度：付费补充实验、专家标注收集、14 项裁决、专家离线统计及正文/附录增补已完成。** 旧 12 项沿用原论文汇总并与新轮分层，不强行合并异构标签。剩余主要是五模型主表与分析图更新、对应文字修改、作者核对、压页、真实专家伦理/资格说明及重投修改说明；不新增付费实验或重标。

官方 OA 3.5 对应 Borderline Conference，是本项目的质量目标，不是自动录用线。[ARR 评分表](https://aclrollingreview.org/reviewform)

### 阅读顺序

- 想核对审稿是否逐项回应：看第 2、3、5 节。
- 想看已经做完什么、哪些数字能用：看第 4 节。
- 想开始改 LaTeX：看第 6、7、9 节。
- 专家部分：看第 8 节，区分专家标签、方法证据质量、负例误报和首试/恢复结果。

## 1. 修改基础

以已确认与 EMNLP 投递稿对应的本地 LaTeX 为起点，原稿保存在 `backups/latex_2026-09-22/`；[当前修订源](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex) 已整合 9 月 22 日方案的正文与附录增补，并保留修订痕迹。

评审依据为 [完整 OpenReview 记录](</Users/chenlong/Downloads/Risk Subgraph Extraction in Cyclic Document Graphs with Structure-Aware Monte Carlo Search _ OpenReview.pdf>)，包含 1 条 meta、3 条 review 和 9 条作者评论。下文评审页码指这份 17 页 PDF；实验结论采用后续修复后的最终结果。

## 2. 整个 ARR review：原始评价与修改责任

### 2.1 分数与已经得到的认可

| 评审者 | OA | Soundness | Excitement | Confidence | 主要态度 |
|---|---:|---:|---:|---:|---|
| iMEC | 2.5 | 3 | 3 | 3 | 问题清楚，但方法像整合，归因和成本不足 |
| rxvy | 2.5 | 2.5 | 3.5 | 4 | 认可任务价值；最关注公平性、有效性及外推 |
| wWUk | 3 | 3.5 | 3 | 3 | 肯定动机、系统和复现；要求自然风险、强基线、成本 |
| Meta / TxMU | 3 | — | — | — | Findings 级评价，汇总上述主要修订点 |

OA 均值约 **2.67**。wWUk 的 3.5 是 Soundness，不是 OA。定位：meta pp.3–4；iMEC pp.4–5；rxvy pp.8–10；wWUk pp.13–14；[本地 review 索引](/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/reviews/review_index.md)。

可以继续作为文章基础的优点：循环依赖是实际而研究不足的问题；按路径复制状态会浪费有限预算的动机易理解；输出可检查的多端点子图比单一风险标签更有价值；系统设计 coherent；原稿具备跨域、跨模型、规模和预算等覆盖。新稿无需推倒任务定义，但需要把这些优点与可靠证据接起来。

### 2.2 全部实质性意见—回复—新稿动作

编号用于后续逐条 revision notes，不表示某条意见必须新增一套大型实验。

| 编号 / 提出者 | 审稿意见，用直白的话说 | 当时实际回复或承诺 | 现在要怎样改 |
|---|---|---|---|
| R1 创新性：iMEC | 这些模块组合起来合理，但独立技术价值是什么？ | 用组件消融说明关键对重访、窗口和动态 core 的作用 | 保留原方法与贡献框架，在消融段说明各设计获得了什么支持；Stage-1 与 Stage-2 结果一起报告，不另设新的核心贡献 |
| R2 组件归因：iMEC / rxvy / meta | TreeMCTS 诊断不能证明 memory、OC、critical pairs、core、窗口各自有效 | 提交六项 Risk-all 消融 | 区分 Stage-1 同期 17-case、描述性 80-case 与 Stage-2 回放；数值按第 4 节更新，保留 memory 非一致收益；OC、closure 不借 Stage-2 一并宣布已验证 |
| R3 输出任务不公平：rxvy / meta / iMEC | Naive 一次写全局排名与子图，SA 只写局部证据，提升可能来自更容易输出 | 承诺局部同 schema、matched-valid / lite-Naive 等控制，提交 LEA | 正文采用五模型各 80 案例的 One-shot / LEA / SA-MCGS 对照；方法部分说明 schema、聚合与预算，主表采用第 4.2 节结果 |
| R4 基线范围：wWUk | 除了 full-SCC prompting，还应有真正利用图结构的基线 | 提交 GraphRAG-style LEA，借鉴图推理中可迁移的局部聚合设计 | LEA 作为与 full-SCC 并列的结构化强基线进入主要比较；说明其 task-aligned 自建设计，不冒称完整复现所有 GraphRAG 系统；等 token 的搜索归因仍未被此实验完全回答 |
| R5 模型差异：iMEC / rxvy / meta | Gemini Pro 等模型的旧 baseline 很强；平均数掩盖了谁真正受益 | 承认非统一占优，报告 Pro 的 LEA 更好 | 以五模型主表呈现比较，围绕根因定位、完整风险证据与紧凑子图组织正向结果；领域和规模分解放附录 |
| R6 自然风险：rxvy / wWUk / meta | 人工注入冲突可识别，不等于真实文档天然风险能识别 | 明确讨论期不新增完整自然风险主实验，承诺 stress-test 定位和后续审计 | 18 个同源未修改 pre 最终均被判为充分负例，可用于自然原文误报审计；未观察到自然正例，不能声称已验证自然正例检出或总体风险率 |
| R7 负例与误报：rxvy | 没有冲突时，是否仍然过度报告风险？ | 7/11 明确承诺 clean/non-risk false-positive / over-reporting | 已统计并入稿：18 个充分负例上有效输出几乎均误报，首试和恢复后分开；invalid 不当作正确弃答 |
| R8 子图干净程度：rxvy | 删掉一半节点，不代表剩下的一半都是有用证据 | 承诺 endpoint precision / irrelevant-node rate | 已按裁决/双参考规则计算专家证据召回、修复材料覆盖、precision 与 outside-reference fraction；与 benchmark endpoint density 分开，不自动把参考集外节点认定为无关 |
| R9 先验敏感性：rxvy | 固定权重是否碰巧调到当前数据上？ | 承诺 prior coefficient sensitivity | 报告已完成的 4-SCC、单 relation-prior 系数 ±20% 探索；不扩大成所有系数/core threshold 均稳健 |
| R10 成本：三位 / meta | 提高了多少质量，花了多少调用、token 和时间？ | 三方法成本表、规模分析及并行时间公式 | 以新 72-job Cost 替换旧表；失败留在分母，恢复消耗入账；报告 calls/tokens/performance，并保留“内部 rollout 并发可缓解等待时间”的解释与公式，不写未经实测的加速倍数 |
| R11 oracle 定义：rxvy / iMEC | 读者可能把用标准答案挑出来的结果误当可部署方法 | 承诺明确由 ground-truth risk metrics 选择的 boosted full-SCC baseline | 按论文协议完整定义 Top-3-from-10；与 One-shot、LEA 分开。十次诊断的成本不能当单次部署成本 |
| R12 使用边界：rxvy | 误报增加人工负担、漏报可能危险，还依赖图是否建对 | 承诺 decision support，而非自动风险裁决 | 摘要、结论、Limitations 统一：保留证据供人工复核，不提供自动法律正确性保证；讨论图缺边、上下文不足和过信 |
| R13 文字 / 复现：iMEC 等 | 附录编号错误、协议与资产应可执行复现 | 承诺 Appendix 9→J 等修正 | 使用自动交叉引用；冻结数据身份、prompt/config、解析器、输出失败与重试规则；检查匿名复现包 |

定位补充：R1–5 主要见 iMEC p.5、rxvy p.9、meta p.4、wWUk p.14；R6 见 rxvy p.9、wWUk p.13、meta p.4；R7–9、R11 见 rxvy p.9；R12 见 rxvy p.10。

两个容易误读的地方：

- **CUAD 并非没进主实验。** Reviewer 要的是自然风险评测；使用 CUAD 来源再注入风险，不自动回答这条意见。CUAD 的原生条款类别标签也不等于 SCC 冲突与最小证据标签。新稿直接澄清任务差异，无需将此写成 reviewer 看错。
- **Meta 不是完全没看到 rebuttal。** Meta p.4 明确提到作者在 discussion 提供了成本结果；但仍要求正式修订，不等于已经认可全部统计口径。

## 3. 我们的 rebuttal：提交史、旧数字与替换关系

### 3.1 实际提交了什么

| 时间 | 给谁 | 内容 | 本次如何使用 |
|---|---|---|---|
| 7/11 | 三位 reviewer 各一条 | 承诺公平 LEA、组件消融、成本、模型级讨论；rxvy 回复另明确承诺负例、子图质量和 prior | 作为必须逐项闭环的责任清单 |
| 7/13 | 三位各一条 | 同一套 T1 LEA、T2 消融、T3 Cost，加上定位与局限解释 | 作为已提交历史证据；数值是否入稿由后续审计决定 |
| 7/16 | 三位各一条 | 询问是否还有意见的 check-in | 没有新增数据；不能算第三轮实质实验补充 |
| EMNLP commitment | Response to Metareview 截图 | 再次汇总三类证据并承诺整合与降调 | 单独记录；不是新的独立实验 |

附件未见 reviewer 对上述追加评论作回复。因此事实是“每人收到三次作者评论”，不是“三轮有来有回并认可结果”。

[comment.md](/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/comment.md) 与 7/13 正式文本相符；[v2 双语草稿](/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/round2_response_draft_bilingual_v2.md) 中更详细的样本数和 valid-only 分母说明，不能视作全部已经正式披露。

### 3.2 T1：历史 LEA 表，不作为新版主表

以下均为当时提交的百分比，保留是为了说明修订来源，**不是当前有效结果**。

| 历史分组 | LEA Root@3 / Risk-all | SA Root@3 / Risk-all | Δ Risk-all |
|---|---:|---:|---:|
| Matched overall | 83.8 / 66.2 | 86.9 / 79.4 | +13.1 pp |
| Gemini 2.5 Pro | 88.8 / 88.8 | 87.5 / 83.8 | −5.0 pp |
| GPT-4o | 78.8 / 43.8 | 86.2 / 75.0 | +31.2 pp |
| Gemini 2.5 Flash | 82.5 / 65.0 | 92.5 / 95.0 | +30.0 pp |

旧原始 matched-160 的 exact identity 审计为 124 一致 / 36 错配；8 月补好其中 23 项后为 147 / 160，仍有 13 项未对齐。最早“33/160”只是 size 不一致的下界，并不矛盾。Flash 是额外切片，不并入这 160。

**替换方式：** LEA 补充已完成，主结果统一采用第 4.2 节的五模型、每模型 80 案例三方法表；36-post 与 12-SCC 对照保留为专家及成本专题证据。

### 3.3 T2：历史消融表，逐项标注有效性

| 当时消融 | Full→消融 Risk-all | 旧解释 | 新稿处理 |
|---|---:|---|---|
| 去 critical-pair revisit | 75.0→53.8，−21.3 pp | 关键对重访重要 | 最新描述性 80-case 为 −21.25 pp，方向/幅度接近；同期 17-case 单列，不将二者当同一确认性证据 |
| 随机局部窗口 | 75.0→63.7，−11.3 pp | 图引导窗口重要 | 最新描述性 80-case 为 −6.25 pp，下降幅度缩小；同期 17-case 区间含 0 |
| 去 relation memory | 75.0→80.0，+5.0 pp | 效果 mixed | 最新描述性 80-case 为 +6.25 pp；延续旧观察，不是新出现的反转。保留结果、降低独立收益主张 |
| 去 OC/core signal | 70.0→60.0，−10.0 pp | OC/core 有贡献 | 没有对应修正后独立证据，暂不作确认性主张 |
| Monotone core | 70.0→45.0，−25.0 pp | 动态 core 很重要 | 旧实现不是真正 no-replacement，弃用旧数；替换为修正 80-case paired replay |
| 去 final pair closure | 70.0→67.5，−2.5 pp | 末尾闭合贡献较小 | 没有对应修正后独立消融；不能借新 Stage-2 宣称已经验证 |

### 3.4 T3：历史成本表，不直接搬入新稿

| 历史模型 / 方法 | Invalid | Calls | Tokens | Time | Risk-all |
|---|---:|---:|---:|---:|---:|
| GPT-4o Naive | 15% | 1.0 | 18.2K | 17.7s | 29.4% |
| GPT-4o LEA | 0 | 16.7 | 58.8K | 162.7s | 42.5% |
| GPT-4o SA | 0 | 48.9 | 163.6K | 498.1s | 77.5% |
| Flash Naive | 0 | 1.0 | 26.6K | 9.4s | 57.5% |
| Flash LEA | 0 | 15.6 | 53.2K | 54.9s | 65.0% |
| Flash SA | 0 | 45.9 | 148.2K | 164.5s | 95.0% |

问题不是“格式不够完美”：旧实验有 identity 错配，而且 GPT Naive 的性能使用 valid-only 分母，表里的 invalid 却以全部尝试为分母。不能把这种混合口径当公平三方法比较，也不能只改一个百分比就宣布修好全部实验。

保留 rebuttal 的并行时间公式及其论点：更多 calls/tokens 不意味着等待时间必须同比例增加，提高有效 rollout 并发可以缩短可并行调用的等待部分。它是执行层面的解释，不是已测得的加速倍数；具体写法见第 4.6 节。新 Cost 与旧表还存在模型、样本及预算差异（新 SA B60），不把两表差值当算法升级收益。

## 4. 后续全部补做工作的证据总账

状态定义：**正式**＝可在注明实验范围后入稿；**诊断**＝不承担主要确认性主张；**废弃**＝保留历史但不再引用其效果结论。专家指标已按实际标注覆盖完成统计，见第 8 节及离线报告。

### 4.1 样本单位先统一

| 证据集合 | 样本含义 | 正确计数 / 边界 |
|---|---|---|
| 原主实验 | 20 个 source SCC，经 4 种注入生成 80 variants，运行 4 模型 | 320 model-cases，不是 320 独立 SCC；源 SCC：Debian 2、SEC 5、BGB 3、CUAD 10 |
| 本轮主比较 | 同一 80 variants，运行 GPT-4o、Gemini 2.5 Pro、Qwen2.5-72B、Llama 3.1-8B-Instruct、Qwen3.5-9B | 400 model-cases；每模型 One-shot、LEA、SA-MCGS 三方法，共 1,200 个方法结果 |
| 专家 / post 对照 | 从主实验法律池选择 36 post variants | 对应 18 去重 source SCC；SEC/BGB/CUAD 各 12 variants，四模板各 9 |
| Pre | 上述 36 variants 的未修改来源 | 18 个 originals；同一 pre 对应多个 post 是预期设计 |
| 本轮实际专家标注 | 18 pre＋24 新 post＝42 个展示项；旧 12 post 另行衔接 | 专家覆盖 42 / 42 / 14，共 98 份判断；不是 98 个独立案例或三人全量标注 |
| 新 Stage-1 | 修复子集的同期四臂 | 17 SEC variants / 5 source SCC × 4＝68 格，不是全域 80 |
| Stage-1 更新汇总 | 四臂均取旧身份一致 63＋新同期 17 | 80 variants / 20 source SCC；跨批次描述性汇总，不是全量同期重跑 |
| Stage-2 | 同轨迹改变最终 core policy | 80 variants / 20 source SCC；不是新增 160 个独立案例 |
| 新 Cost | 四域中 12 个不同 source SCC，各选一个 variant | 12 × 2 模型 × 3 方法＝72 格 |
| 新 Prior | Cost 的预冻结 4-SCC 子集 | 16 个扰动新运行，复用 8 个默认值；只有 4 个独立 source 簇 |

方法比较同 case 配对；同源 variants 和同 source 的多个模型不能当完全独立样本。主文明确 cluster 数；涉及多个 variants 时同时区分 variant 平均与 source-SCC 等权平均。不同样本表不能直接拼成一个更大的 N。

### 4.2 主实验呈现：保留原数据，改为双 baseline 比较

**新版主比较采用 One-shot＋LEA＋SA-MCGS，覆盖五个模型、每模型同一 80 案例。** 以下四项指标均以百分比显示，作为本轮主表、图表与文字的固定采用版本。

| 模型 | 方法 | Root@3 | Risk-any | Risk-all | Compression |
|---|---|---:|---:|---:|---:|
| GPT-4o | One-shot | 26.25 | 55.00 | 15.00 | 67.89 |
| GPT-4o | LEA | 78.75 | 96.25 | 43.75 | 51.26 |
| GPT-4o | SA-MCGS | 86.25 | 100.00 | 75.00 | 51.26 |
| Gemini 2.5 Pro | One-shot | 90.00 | 97.50 | 85.00 | 74.98 |
| Gemini 2.5 Pro | LEA | 87.50 | 100.00 | 83.75 | 51.26 |
| Gemini 2.5 Pro | SA-MCGS | 87.50 | 97.50 | 83.75 | 55.86 |
| Qwen2.5-72B | One-shot | 2.50 | 46.25 | 13.75 | 42.69 |
| Qwen2.5-72B | LEA | 67.50 | 97.50 | 43.75 | 51.26 |
| Qwen2.5-72B | SA-MCGS | 70.00 | 97.50 | 75.00 | 52.82 |
| Llama 3.1-8B-Instruct | One-shot | 3.75 | 47.50 | 25.00 | 30.27 |
| Llama 3.1-8B-Instruct | LEA | 43.75 | 92.50 | 35.00 | 51.26 |
| Llama 3.1-8B-Instruct | SA-MCGS | 61.25 | 95.00 | 48.75 | 51.30 |
| Qwen3.5-9B | One-shot | 15.00 | 60.00 | 13.75 | 64.73 |
| Qwen3.5-9B | LEA | 56.25 | 91.25 | 63.75 | 51.26 |
| Qwen3.5-9B | SA-MCGS | 62.50 | 86.25 | 63.75 | 67.25 |

主表按模型分组，每组固定三行；保留两位小数。SA-MCGS 方法名突出，数值加粗仅用于组内对应指标的最佳值，相同最佳值同时标粗。

**结果叙述以正向提升为主线：根因定位、完整风险证据与紧凑子图。** 先以 GPT-4o、Qwen2.5-72B 和两个较小模型相对 One-shot 的结果建立总体效果，再说明搜索相对 LEA 的进一步提升。GPT-4o 与 Qwen2.5-72B 的 Risk-all 均由 43.75% 提高至 75.00%，提高 31.25 个百分点；Llama 3.1-8B 的 Root@3 由 43.75% 提高至 61.25%，Risk-all 由 35.00% 提高至 48.75%。

Qwen3.5-9B 的 Root@3 从 56.25% 提高至 62.50%，在 Risk-all 保持 63.75% 的同时，Compression 从 51.26% 提高至 67.25%；这一结果衔接定位与证据压缩的共同作用。Gemini 2.5 Pro 的基线已处于较高水平，三方法的 Risk-all 为 83.75%–85.00%，用相邻短句交代即可。正文选取代表值，完整数值由主表承担。

本轮主表的数据来源：[GPT-4o、Gemini 2.5 Pro 与 Qwen2.5-72B 结果](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/lea_full320_completion_20260923/RESULTS_ANALYSIS.json)、[Llama 3.1-8B 结果](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/llama8b_three_methods_20260924/final_analysis.json)、[Qwen3.5-9B 已确认结果](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/parsing_recovery_audit_20260925/metricwise_results.json)。图表离线读取对应逐例数据，完整修改清单见第 7.3 节。

### 4.3 专家配套比较：保留已对齐的 36-post 子集

8 月补齐 GPT-4o 12 项与 Gemini Pro 11 项，共 23 项；当前 36 post × 2 模型 LEA **72/72 exact identity、0 invalid**。One-shot 和 SA 使用原主实验对应的冻结逐例结果，因此此表不是三方法全部同期重跑。

| 模型 | 方法 | Root@3 | Risk-any | Risk-all | Invalid |
|---|---|---:|---:|---:|---:|
| GPT-4o | One-shot | 8/36＝22.2% | 21/36＝58.3% | 4/36＝11.1% | 7/36 |
| GPT-4o | LEA | 27/36＝75.0% | 34/36＝94.4% | 10/36＝27.8% | 0/36 |
| GPT-4o | SA-MCGS | 30/36＝83.3% | 36/36＝100% | 26/36＝72.2% | 0/36 |
| Gemini 2.5 Pro | One-shot | 32/36＝88.9% | 35/36＝97.2% | 29/36＝80.6% | 0/36 |
| Gemini 2.5 Pro | LEA | 32/36＝88.9% | 36/36＝100% | 30/36＝83.3% | 0/36 |
| Gemini 2.5 Pro | SA-MCGS | 32/36＝88.9% | 34/36＝94.4% | 29/36＝80.6% | 0/36 |

此表保留为专家配套子集的历史对照，与后文专家分析衔接；当前主结果统一采用第 4.2 节的完整 80 案例五模型表。

来源：[候选与采样规则](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/annotation_prep/candidates/README.md)、[identity 覆盖明细](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/annotation_prep/baseline_audit/baseline_coverage.csv)、[LEA 修复状态](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/lea_update/LEA_UPDATE_STATUS_ZH.md)。

### 4.4 Stage-1：同期消融、80-case 更新汇总与关系记忆口径

新四臂：GPT-4o，B60，window 4，内部并发 3，17 variants / 5 SEC source SCC；含同期 Full，68/68 valid。身份、源码、配置、schema、toggle 和集合指标重算通过。

| 方法 | Variant 级 Risk-all | Source-SCC 等权 Risk-all | 对新版主张的含义 |
|---|---:|---:|---|
| Full | 88.2% | 88.3% | 不是四臂最优 |
| 去 relation-first memory | 100% | 100% | 未证明该组件在这批数据有正向独立收益 |
| 去 critical-pair ledger/revisit | 100% | 100% | 未复现旧全体大幅下降 |
| 随机 local window | 82.4% | 85.0% | 点估计下降，但不能作确定组件结论 |

四臂 Root@3 / Risk-any 均为 100%；Risk-all 差值区间均包含 0。Full / no-memory / random 的平均压缩率均为 50.09%，no-critical 为 65.34%。Full 的两个失败 case 是排名已覆盖端点、最终 core 漏掉一个端点，不是可以靠“改 evaluator”消去的错误。

旧 identity 一致的 63 variants / 17 source SCC 另行离线复核：Full / no-memory / no-critical / random 的 variant 级 Risk-all＝74.6 / 79.4 / 44.4 / 68.3%。存在 critical-pair 的历史正向信号，但旧 Full 缺 prompt/config hash，只能作诊断。**不能把旧 63＋新 17 合成严格 80-case 主表。**

**80-case 更新汇总（描述性，不替代上面的同期实验）：** 四臂各取上述旧 63＋新 17，逐例核对输入身份，并由原始结果重算。下面的 Full 也替换了对应 17 项，不以旧 Full 搭配新消融。

| 方法 | Root@3 | Risk-any | Risk-all | 平均压缩率 | 平均 core 节点数 |
|---|---:|---:|---:|---:|---:|
| Full | 86.25% | 100.00% | 77.50% | 51.26% | 8.10 |
| 去 relation-first memory | 88.75% | 98.75% | 83.75% | 51.26% | 8.10 |
| 去 critical-pair ledger/revisit | 83.75% | 88.75% | 56.25% | 71.29% | 4.30 |
| 随机 local window | 90.00% | 96.25% | 71.25% | 51.26% | 8.10 |

相对 Full 的 Risk-all 差值为：去 critical-pair **−21.25 pp**、随机窗口 **−6.25 pp**、去记忆 **+6.25 pp**。前两项保留总体下降方向，但窗口降幅小于旧 rebuttal；去记忆的改善方向原 rebuttal 已报告。此表用于补充整体描述与新旧变化说明，放附录并注明跨批次来源；不能据此宣称“统一重跑 80 cases 后严格确认组件贡献”。

**关系记忆的写法已确定：保留消融，不单独展开为正文重点。** [rxvy 明确要求过 no relation memory](/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/reviews/reviewer_rxvy.md:22)。正文简述“关系记忆未显示一致的独立收益，移除后 Risk-all 反而提高”，并指向附录完整表；不删掉不利结果，也不把它列为已验证的主要增益来源。该结论限制组件必要性，不等于否定完整方法的主实验表现，不要求改算法或故事线。

- 80-case 汇总中，移除记忆仅在 Risk-any 上下降 1.25 pp（80/80→79/80）；Risk-all 净多成功 5/80，压缩率相同。这不足以强调明确的可靠性优势。
- 可比的同期 17-case 中，Full→no-memory：调用 995→979、tokens 1,637,548→1,575,503、账本估算总费用 $9.6111→$9.2426，后两者均约减少 3.8%。没有“移除后靠更多计算换取收益”的证据；这些成本只代表该 17-case 批次，不能外推为完整 80-case 成本。
- 平均单例时间 185.7→187.1 秒，但中位数 165.8→163.1 秒；不将这种小幅、方向不一致的波动解释成稳定速度代价。完整成本放附录，不额外增加正文成本表。

整体解释：历史全域诊断存在 critical-pair 的正向信号；同期小型 SEC 子集未支持 memory 与 critical-pair 的必要性。分别报告适用范围，不把局部结果推广到全部域，也不声称所有组件都独立必需。

来源：[新 Stage-1 最终报告](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage1_identity_safe_68_20260909_051438/formal/FINAL_REPORT_ZH.md)、[SCC 等权统计](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage1_identity_safe_68_20260909_051438/formal/SCC_EQUAL_INFERENCE_ZH.md)、[旧 63 诊断](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage1_legacy63_diagnostic/REPORT_ZH.md)、[同期 17-case 成本汇总](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage1_identity_safe_68_20260909_051438/formal/final_summary.json)。80-case 表由旧 63 的 raw manifest 与新 17 的 `formal/results/` 四臂逐项汇总，不改写历史报告。

### 4.5 Stage-2：补充原 dynamic-core 设计的消融证据

80 variants / 20 source SCC；两臂共用冻结搜索轨迹，仅改变最终 core 的 replacement policy。原回放此前完成，9 月新增 source-SCC 配对统计，零模型调用。

Stage-2 的 Full＝75.0% 来自全套原冻结轨迹；Stage-1 更新汇总的 Full＝77.5% 包含新跑的 17 项。两者运行来源不同，不能互换作对照，也不是同一实验前后矛盾。

| 指标 | Dynamic / replacement | Locked no-replacement | 差值及 source-SCC 95% CI |
|---|---:|---:|---:|
| Risk-all | 75.0% | 37.5% | +37.5 pp [12.5, 60.0] |
| Risk-any | 100% | 86.25% | +13.75 pp [5.0, 22.5] |
| 平均 core 节点数 | 8.1 | 8.1 | 同规模 |
| Compression | 51.3% | 51.3% | 同压缩水平 |

可说：在共享已观测证据与相同 core 规模下，允许替换比早期锁定更能保留 benchmark 端点。这比“输出更大所以包含更多端点”更有针对性。

不可说：Root@3 由 core replacement 提升；改变了搜索轨迹；对所有模型都验证过；独立证明 OC 或 final closure 的效果；是一项端到端重新搜索对照。旧 40-case 修正值 70→42.5 仅作修复历史，新稿优先 80 版；旧 −25 pp 不再用。

来源：[正式回放](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage2_paired_replay_80case_identity_v1_final/stage2_paired_core_report.md)、[配对区间](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage2_paired_replay_80case_identity_v1_final/stage2_clustered_paired_inference.md)。

### 4.6 Cost：已完成，可以承担正文的成本—效果论证

同一批 12 不同 source SCC、GPT-4o 与 Gemini 2.5 Pro、三方法，同期 72 格；69 valid、3 invalid，失败全部为 GPT One-shot，保留在性能与成本分母。SA B60、window 4、内部并发 1；四域样本数为 2 / 3 / 3 / 4。

| 方法 | GPT Risk-all（n=12） | Gemini Risk-all（n=12） | 平均记录 calls / 项 | 平均 tokens / 项 |
|---|---:|---:|---:|---:|
| One-shot | 25.0% | 100% | 1.0 | 23,488 |
| LEA | 41.7% | 83.3% | 16.9 | 63,702 |
| SA-MCGS | 83.3% | 91.7% | 56.5 | 203,364 |

calls/tokens 列对两个模型等权平均。SA token 约为 LEA 的 **3.2 倍**；GPT SA−LEA Risk-all 为 +41.7 pp，95% CI [8.3, 75.0]；Gemini 为 +8.3 pp，区间 [−16.7, 33.3]，且 Gemini One-shot 最好。

正文必须同时说清两个结论：**部分模型值得花额外计算保留更多端点；强模型的一次完整阅读也可能已经足够好。** 尚未验证按难度自动路由的策略，不把“简单先 One-shot、困难再 SA”写成已验证系统。

一项 Gemini SA 中断恢复，累计 17＋56＝73 次有记录调用。成本包含已观察的恢复消耗；无法观察的在途收费不假定为零。终态有效不等于首次成功，跨批 runtime 不作公平加速结论。

**并发效率解释保留。** SA-MCGS 使用更多 calls/tokens，但可以通过内部 rollout 并发缓解等待时间，计算成本增加不意味着实际耗时必须同比例增加。沿用 rebuttal 的近似解释：`T_wall ≈ T_serial + Σ_g ceil(n_g / p_g) · t_g`，其中各组按依赖顺序执行，组内 `n_g` 次可并行调用以有效并行度 `p_g` 执行，`t_g` 为代表性调用延迟；有效并发受可并行任务、worker 和 API 限额约束。在固定调用工作量下，并发缩短等待，不自动降低调用数、token 或费用。这一解释与公式进入成本讨论；不把外层同时跑多个案例当作单案例 rollout 的实测提速，也不为保留该解释追加实验。

来源：[Cost 报告，仅 Cost 部分](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/cost_prior_12case_gpt4o_gemini25pro_b60_v1/REPORT_ZH.md)、[最终配对统计](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/supplemental_pipeline_20260909/clustered_closeout/paired_cluster_closeout.md)、[执行口径](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/supplemental_pipeline_20260909/clustered_closeout/EXECUTION_CAVEATS_ZH.md)。

### 4.7 Prior：完成的是小型扰动，不是原计划全部参数网格

预冻结 slots 01 / 03 / 08 / 10，共 4 source SCC；两模型，唯一改变 `relation_prior_weight`：默认 0.85，减 20% 为 0.68，加 20% 为 1.02。16 个新运行全部 valid，8 个默认结果复用 Cost。

| 模型 | Risk-all：默认 / −20% / +20% | Root@3：默认 / −20% / +20% |
|---|---|---|
| GPT-4o | 75 / 100 / 100% | 100 / 75 / 75% |
| Gemini Pro | 75 / 75 / 75% | 75 / 100 / 100% |

Risk-any 均为 100%。可说“这个小子集上最终端点完整性未下降，但根定位有变化”；不可说“所有先验都不敏感”“最佳系数已确定”或“core-threshold sensitivity 完成”。仅 4 簇，区间不支持强泛化。

旧 12-SCC / 48 新运行方案已经由预算门禁下预冻结的 4-SCC / 16 方案替代，不是还有 48 项待跑。后段增加的是外层任务并行，内部搜索仍为 1，不能与串行默认值比较算法加速。

来源：[Prior 最终报告](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/prior_fallback_slots_01_03_08_10/REPORT_ZH.md)、[范围冻结依据](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/validation/prior_budget_gate_v1/PRIOR_BUDGET_GATE_ZH.md)。

### 4.8 Pre 输出：运行完成不等于自然风险正确率已知

18 originals × 2 模型 × 3 方法＝108 个主网格均已尝试；LEA 和 SA 首次批次此前已有，本轮新增 One-shot 与 SA 指定失败项的一次重试。

| 方法 | GPT 有效输出 | Gemini 有效输出 | 解释 |
|---|---:|---:|---|
| LEA 首次 | 16/18 | 18/18 | 旧批次；其中 Gemini 有 1 个有效 abstention；首试以追加日志核验 |
| LEA 历史恢复后 | 17/18 | 18/18 | GPT 两项失败完整重跑，一项恢复；新增 63 calls / 261,389 tokens，不混成首试 |
| One-shot 首次 | 12/18 | 18/18 | 本轮 36 项已完成 |
| SA 首次 | 8/18 | 4/18 | 合计 12/36，不能从记录中删掉 |
| SA 按预定失败项重试后的累计可用 | 15/18 | 18/18 | 24 次重试成功 21；最终 33/36 可用，不是首试成功率 |

valid 只代表格式/协议可用；assertion 不等于真实冲突，invalid 不等于有意识弃答。这些 pre 无注入 gold，不能套用注入 Risk-all。专家标签与正式统计已完成：18 pre 最终均为“不存在且充分”，有效输出除 Gemini LEA 一次 operational abstention 外均触发显式冲突断言。自然正例数为 0，正例检出率/召回率不可估计，而不是 0 分。完整首试/恢复分表见第 8 节离线报告。

新稿应同时报告 first-attempt 与 recovery-aware 两层协议；若把重试后输出用于专家质量对比，所有方法的重试规则和累计成本必须清楚标注，不能把 SA 多次机会混写成单次公平比较。

来源：[Pre 最终运行报告](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/pre_baseline_runs/pre_baseline_v1_20260909/PRE_BASELINE_FINAL_REPORT_ZH.md)、[Pre LEA 状态](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/lea_update/LEA_UPDATE_STATUS_ZH.md)。

### 4.9 其他已做工作与实际开销

- Stable identity：使用 source revision、节点集合 fingerprint、source hash 与 variant 身份，Tarjan `scc_id` 仅作诊断。这是实验对应关系修复，不包装成算法创新。
- Stage-0、dry run、旧 Flash/Qwen 成本及 Qwen LEA 接口失败检查：流程诊断，不作为新主表证据。
- 新 Stage-1 smoke 12 格中 4 格按验收规则纳入正式 68，其他 8 格不增加正式 N；Pre 另 2 格 smoke。
- 9 月离线新增：Stage-1 SCC 等权、旧 63 诊断、Stage-2 SCC 区间、Cost/Prior 最终配对及账本审计。最终 bootstrap 为 20,000 次；9/10 汇总器修复失败结果方法名称兼容，不改原始结果，也没有新增付费调用。
- 专家后处理：本轮零 API 分析已适配二选一字段及 42 / 42 / 14 的实际覆盖，输出 IAA、双参考方法指标和 source-SCC 区间；原始判断与 14 项裁决未改写。新增验证见 `manuscript_revision_20260922/expert_analysis/VALIDATION.json`。

| 本轮账本 | 观测 token 按冻结单价估算 |
|---|---:|
| Pre（含 smoke 与指定重试） | $34.634480 |
| Stage-1（含实际 smoke 消耗） | $47.381175 |
| Cost | $36.77011125 |
| Prior | $17.810895 |
| 合计 | **$136.59666125，约 $136.60 / $200** |

这不是共享 XHub 账户精确实扣；旧实验与旧 LEA 修复费用不重复计为本轮新增。Cost 最早 6 条压力价字段已按规则转换，不能混合加总。执行记录中的 `paid_experiments_complete_labels_pending` 是历史阶段状态；专家正式统计与正文/附录增补现已完成，本轮写作及核验未新增模型调用。

## 5. 现在能否回答原 reviewer：完成度而非打分预测

| 问题 | 当前证据状态 | 剩余工作 | 对双 3.5 的重要性 |
|---|---|---|---|
| baseline 不公平 | 五模型各 80 案例的三方法结果已确认 | 更新五模型主表和三方法图；专家与同期 12-SCC 成本对照保留原用途 | 很高 |
| 方法只是模块拼装 | 部分回答 | 在原方法说明后用新消融解释各组件作用；保留 Stage-1 不确定性，不更换全文贡献中心 | 高 |
| 自然风险与 practical significance | 新 42 项标注及指标已完成；18 pre 充分负例，24 post 充分正例 | 核对已入稿结论；旧 12 原汇总、新 24 分层报告 | 很高；支持自然原文负例审计，不证明自然正例检出 |
| cost / reliability | 当前主要证据已完成 | 把 calls/tokens/strict performance 放正文；明确恢复协议 | 高，不需要默认再跑旧 40-case |
| 模型异质性 | 已充分显现 | 以根因定位、完整风险证据及紧凑输出组织结果，正文突出代表性提升，完整比较列入主表 | 高 |
| 负例 / 误报 / 子图质量 | 双参考、裁决和首试/恢复指标已完成并入稿 | 核对误报与证据质量并存的结论，不把 invalid 当正确弃答 | 高 |
| prior sensitivity | 部分回答 | 附录报告 4-SCC 探索与扰动范围 | 中；不再作为未跑项 |
| reproducibility | 资产较充分，但仍需投稿包验收 | 统一 canonical 表、协议、匿名说明与可执行入口 | 高 |

**总判断：按“原稿＋针对性补充”推进双 3.5，不改变整篇故事。** 新结果用于补足公平性、机制和成本说明；个别组件的效果不确定，就在消融段如实交代，并局部调整相关句子。保留方法框架与避免不受支持的强断言并不冲突。

## 6. 保留原稿，仅做必要的口径修正

### 6.1 主张—证据清单

| 主张 | 状态 | 推荐措辞 / 修改原则 |
|---|---|---|
| SCC 是适合局部证据推理的结构单元 | 保留 | SCC 不等于有风险；任务是在给定文档图内分析相互依赖证据 |
| SA 提升所有模型的风险识别 | 改写 | SA-MCGS 在多个模型上提高根因定位与完整风险证据提取，并将关键证据组织为紧凑子图；代表性结果见第 4.2 节 |
| Dynamic core 改善最终端点完整性 | 保留并强化 | 用 shared-trajectory replacement vs locked-no-replacement 回放；不要归因 Root@3 |
| Memory、critical-pair、OC、窗口均独立必需 | 删除统一断言 | 方法中描述其设计作用，实验中分别报告支持程度；新 Stage-1 不能隐去 |
| Risk-all 等于完整修复证据 / 法律正确率 | 改写 | 是 benchmark-defined root–witness endpoint completeness；expert evidence / repair packet 另测 |
| 自然案例审计证明总体自然风险分布 | 不采用 | 18 个 selected unmodified source SCC；只描述该样本，不估计领域总体风险率 |
| SA 免费提升或始终性价比最高 | 不采用 | SA 用更多 tokens/calls 换取某些模型上的完整性；12-SCC 不等于全预算 Pareto 曲线 |
| 已证明 priors 普遍稳健 | 不采用 | 4-SCC、一个系数 ±20% 的探索性结果 |
| 内部 rollout 并发可缓解等待时间 | 保留 | 计算成本与等待时间分开；保留并行时间公式，不把外层任务并发当作单案例实测加速，不写未经实测的倍数 |
| Collapse 改善更高层完整业务 pipeline | 降为接口动机 | 当前直接评测 SCC 内输出，不冒充已验证上层任务质量 |

### 6.2 贡献框架保持原样

保留原稿贡献条目的主题、顺序以及方法整体定位，不另写一套贡献列表。SCC 局部化、结构感知 Monte Carlo 搜索、关系证据记忆、动态 core 都继续在原方法中完整介绍，名称和流程不变。

LEA 升为与 full-SCC 并列的主要强基线，Stage-1 / Stage-2、Cost、Prior 和专家审计补齐原贡献的证据。方法贡献框架不变，但比较结论和摘要中的实验概括应覆盖双基线，而非只复述旧单基线提升。涉及具体效果时说明模型和样本范围；无需因此删掉模块、重新设计算法，或将 dynamic core 提升为唯一核心贡献。

## 7. 沿原章节增补，不重排全文

### 7.1 原位置的最小修改清单

沿原章节位置修改：方法部分以局部修订为主，比较相关段落和图表按双基线重新组织；不另起论文故事线。

| 原稿位置 | 保留什么 | 本轮只补 / 改什么 |
|---|---|---|
| 标题、Abstract、Introduction | 标题、问题动机和叙述顺序 | 实验概括同步为四域五模型三方法比较，突出定位、完整证据与压缩效果；不重写问题动机 |
| Contributions | 原条目主题与顺序 | 在已有评估贡献后简述补充验证；不替换贡献列表 |
| Task / metrics | 原任务、输入输出和符号框架 | 补 source SCC / variant / model-case 的区别 |
| Method 各模块 | SCC rollout、memory、OC、dynamic core 的结构和介绍顺序 | 补与消融对应的实现说明，不合并模块或改流程 |
| Algorithm / complexity | 原伪码与复杂度段 | 必要时补指向新 cost 表的引用，区分理论量级与实测调用/token |
| Domains / injection | 四域数据介绍与原数据表 | 加一句样本层级及注入风险范围；不改主实验集合 |
| Baselines | full-SCC 比较方法与原协议记录 | 改为 full-SCC 与 LEA 两类主要基线的并列介绍；交代 LEA 窗口、schema 和聚合，One-shot 与 GT-selected oracle 分开 |
| Main Results | 原 80 案例、章节位置与四域覆盖依据 | 采用第 4.2 节五模型三方法主表，保留规模图、预算图和案例图；Figure 4 已替换为 D 逐案例配对收益图，执行清单见第 7.3 节 |
| Ablation / Robustness 附近 | 原实验顺序 | 增加 Stage-1 / Stage-2 紧凑消融表及结论；如原无消融小节，局部新增一小节即可 |
| Cost / Prior | 不牵动原方法结构 | 成本—效果表并列 One-shot、LEA、SA-MCGS，保留内部并发缓解等待时间的解释与公式；Prior 给简短总结并指向附录 |
| 专家审计 | 原 12-case 结果和已有附录位置 | 加入两位全量＋第三位定向裁决的协议与已确认标签结论；沿用已完成的正式方法指标，旧 12 分层衔接 |
| Related Work | 原分类与结构 | 补 LEA / 图推理相关比较说明及必要引用，不重写文献综述 |
| Conclusion / Limitations | 原结论主题与位置 | 综合五模型比较与专家证据，围绕根因定位、完整风险证据和紧凑子图总结方法价值；保留原结论主题与位置 |
| 附录与交叉引用 | 原附录组织 | 放完整新增表、实验协议与专家细节；统一指标名称和 Appendix 编号 |

### 7.2 新增内容怎样控制篇幅

| 补充内容 | 正文最小呈现 | 完整细节放哪里 |
|---|---|---|
| 双基线主比较 | 五模型三方法完整主表，配规模对照及逐案例配对收益图；文字集中陈述代表性提升 | 五模型逐域、逐规模分解放附录；36-post 对照保留在专家配套位置 |
| 模型差异 | 与主比较同处呈现，以 GPT-4o、Qwen2.5-72B、Llama 和 Qwen3.5 的代表性提升串联结果 | 模型完整数值放主表；领域和规模分解沿用原附录位置 |
| Stage-1 / Stage-2 | 紧凑表区分同期 17-case 与 80-case 回放；正文交代关系记忆无一致收益、移除后 Risk-all 提高，不单独展开 | 完整 no-memory 结果与成本、描述性 80-case、旧 63 诊断、逐例及回放细节放附录 |
| Cost | calls/tokens 与性能同表，可与同期三方法比较合并；简述内部并发可缓解等待时间并保留近似公式 | 失败/恢复、逐域/规模与账本细节放附录；并行公式较长时放附录，正文保留结论与指引 |
| Prior | 一两句范围和结论 | 4-SCC 扰动全表放附录 |
| 专家审计 | 数据来源、实际覆盖、标签结论；沿用已完成的方法指标紧凑对照表 | 新旧协议、完整结果、裁决和敏感性分析放原专家附录 |

先按上述方式补入、编译，再判断是否超页。若确实需要腾空间，优先删重复句、压缩重复说明、合并同义表格；只有必要时才讨论个别图表移动。**不预先移走两张全宽图，不合并 Method 为新三段，不重新制定逐节页数配额。**

正文仍需让读者看见会改变结论的模型差异和消融结果；“完整表在附录”不等于只在附录承认这些差异。通过短段落说明即可，不需要重排整篇文章。

### 7.3 本次新增：第八页之后的图表更新清单

以下位置以 LaTeX 标签为准。Figure 4 已选定 D 并完成替换，数据取自现有冻结结果；主文仅采用这一备选图。

| 现有位置 / 标签 | 本轮具体修改 | 采用的数据与布局 | 正文承担的任务 |
|---|---|---|---|
| P8 Table 3，`tab:matched_main` | 用第 4.2 节的 15 行完整替换；删除旧 36-case 主表说明 | 五模型分组、三方法同序、四指标、两位小数 | 给出完整方法比较 |
| P8 Figure 3，`fig:main_metrics`；`fig02_main_results_composite.pdf` | 重画为五模型的三方法规模对照图，替换旧总体两方法柱图及旧规模面板 | 两行五列小面板：列为模型，行为 Root@3 / Risk-all；横轴为统一 SCC 规模组，三方法颜色固定 | 展示定位和完整性随 SCC 规模的变化，减少与主表的重复 |
| Figure 4，`fig:paired_case_outcomes`；`fig03_paired_case_outcomes_five_models.pdf` | 已用 D 逐案例配对收益图替换；从冻结逐例 Risk-all 结果统计，图注与相邻正文同步 | 左右两面板分别比较 One-shot、LEA；每模型同一 80 例，以四段横条显示 SA-only、Both、Baseline-only、Neither，右侧列 Risk-all 净提升（百分点） | 解释 SA-MCGS 多找回了多少案例的完整风险证据 |
| Figure 5，`fig:convergence`；`fig04_budget_prefix_convergence.pdf` | 重画 GPT-4o 的已有预算轨迹，改用 Risk-all 与 Compression 两面板，并加入同模型两基线终点参考线 | SA 横轴为 rollout budget；One-shot、LEA 用标明方法的水平参考线；从已保存快照读取节点集合 | 展示搜索如何积累并压缩证据 |
| Figure 6，`fig:case`；`fig06_representative_scc_collapse.pdf` | 改为同一固定 SCC 的 One-shot、LEA、SA-MCGS 三列图 | 固定案例身份、同一模型、共享节点位置与图例；保留节点着色，删去节点淡灰；列下给节点数和四指标 | 展示各方法如何组织同一组风险证据 |

预算图的旧生成代码把“根节点是否保留在子图中”标成了 Root@3。本轮预算图直接使用节点集合可确定的 Risk-all 与 Compression，并与主表区分排名和子图保留两类指标；主表数值保持不变。

预算图出图前逐例核对 budget 60 的 core 与主表采用的同 80 例最终 core。轨迹中的节点集合按同一 core 提取规则离线整理，末端与保存的最终输出对齐后，再生成曲线与参考线。

规模图从当前逐例结果沿用原稿的 SCC 规模分组，三方法共享分组与样本列表。先检查每个模型、每个规模组的结果覆盖，再出图。领域分析同样三方法并列，完整四指标放附录，正文用一小段承接总体结果；具体分组结论在离线图表生成后据图落笔。

Figure 4 采用已选定的 D：逐案例配对收益图，与 Table 3 和 Figure 3 分工：主表给出总体指标，规模图展示分组表现，配对图解释新增完整风险证据来自多少案例。正文突出相对 LEA 的净增案例数：GPT-4o 为 32−7＝25，Qwen2.5-72B 为 33−8＝25，Llama 3.1-8B 为 21−10＝11；对应 Risk-all 提升 31.25、31.25、13.75 个百分点。

**专题表与附录同步：**

| 图表 / 文件 | 更新动作 |
|---|---|
| Table 4，`tab:component_main` | 数值与配置保留，压缩表前后文字；Stage-1 和 Stage-2 分面显示 |
| Table 5，`tab:cost_main` | 三方法成本数值保留，统一名称，结果段衔接更充分证据搜索的计算开销 |
| 专家 Tables 6–11；Tables 6–8 位于 `acl_latex.tex`，Tables 9–11 位于 `revision_expert_appendix.tex` | 原统计保留；方法顺序与主表一致，正文突出证据召回与修复材料覆盖 |
| 数据构建、注入模板与固定 prior 表 | 保留设计内容；五模型、400 model-cases、1,200 方法结果的说明同步到适用位置 |
| 旧 Table 17，`tab:appendix_breakdowns` | 模型面板更新为五模型三方法；领域和规模面板离线重建，表头、方法名与主图统一 |
| Tables 18–22，`revision_experiments.tex` | 保留 GPT 组件、core replay、双模型成本与先验表；更新主文引用 |
| 旧 selector 表与输出负担图 | 从本轮效果论证链中移出，主结果位置由完整三方法比较接替；不继续用旧 pooled aggregate 支撑新结论 |

方法曲线沿用 One-shot 灰色、LEA 橙色、SA-MCGS 蓝色及不同点形。Figure 4 按配对结果编码：SA-only 深蓝、Both 浅蓝、Baseline-only 橙色、Neither 灰色；横轴为案例数，四段合计 80，净提升＝（SA-only−Baseline-only）÷80×100。模型顺序与 Table 3 一致。

后续绘图入口为 `experiments/main_experiment/build_paper_assets.py`。先建立五模型三方法的明确数据映射，再替换旧脚本中的两方法和 selector 硬编码；输出到 `experiments/main_experiment/paper_assets/`。正文与附录使用同一套资产，模型顺序与第 4.2 节一致。

## 8. 专家审计：标注、裁决及正式离线统计已完成

### 8.1 样本与实际完成量

冻结设计不变：**36 post variants → 18 个去重 pre originals**。Post 包含旧 12 和新增 24；完整设计为 54 个展示项，不是 54 个独立 SCC。本轮新标注范围为 **18 pre＋24 post＝42 项**。

| 标注批次 | 实际覆盖 | 当前状态 |
|---|---|---|
| 专家 1 | 新 42 项，648 段 | 已收齐 |
| 专家 2 | 同一新 42 项，648 段 | 已收齐 |
| 专家 3 | 定向复核 14 项：9 pre＋5 post，264 段 | 已收齐；按作者指定作为这 14 项的最终裁决 |
| 旧审计 | 12 post，来自 7 个源 SCC，包含在上述设计内 | 原论文汇总保留；逐例标签尚未合并 |

本轮共有 **98 份真实判断（42＋42＋14）**，不是三位各 42 项的 126 份，也不把第三位复核计成新增样本。

旧 12 的两份原始导出均已定位，文件仍在；剩余是逐例身份、来源及字段可比性核验，不是要求重新打标：

- [旧专家导出 1](</Users/chenlong/Documents/New project/合同标注2.0/structural_conflict_annotations_2026-05-23 (11).xlsx>)。
- [旧专家导出 2](</Users/chenlong/Documents/New project/human_annotation_pack(1)/structural_conflict_annotations_2026-05-24 (1).xlsx>)。

可比字段直接复用；缺失字段在对应指标中标缺失，不用模型补填。若协议不足以合并，保留旧 12 汇总、新 24 单列，不因此默认返工。

### 8.2 盲评、裁决与证据集合口径

- **三位实际均完全盲评，作者已明确确认算法提示和注入信息不可见。** 原 Excel 中的辅助页面模式/提示字段原样保存，另记录实际操作确认；不把文件名当作实际看见提示的证据，也不改写原导出。
- 论文描述为“**两位全量独立标注，第三位对选定分歧/不确定项独立标注并提供最终裁决**”，不写三位全量或三位一致。复核筛选依据专家分歧、充分性、低信心和证据集合差异，不依据模型输赢。
- 按作者 9 月 20 日收到结果后的指定，14 项整体采用第三位完整答案：存在性、充分性、信心、最小证据集及修复材料均来自同一位，不拼接答案。此规则不称事前预注册。
- 其余 28 项的存在性与充分性已获前两位一致判断；但最小证据集有 14 项不同，修复材料有 28 项不同。保留双参考集合，**不擅自求并集/交集或补造第三票，也不声称全部 42 项唯一证据 gold 已冻结**。
- IAA 使用裁决前原始判断；前两位的全量一致性与第三位的定向子集分开。不能用裁决后的统一答案计算“100% 专家一致率”。
- 中文译文用于阅读，涉及歧义时回到原文核对。专家资格、同意、补偿与适用伦理说明由作者按真实情况补齐，不补造记录。

可追溯来源：[第三专家复核说明](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/annotation_prep/third_expert_review/README.md)、[最终裁决记录](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/annotation_prep/third_expert_review/internal/adjudication_20260920/README_ZH.md)、[逐例记录与原始文件校验](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/annotation_prep/third_expert_review/internal/adjudication_20260920/adjudicated_records.json)。三份原始 Excel 和 98 份原始判断均保留，裁决另存，不覆盖原票。

### 8.3 已确认的结果与能支持的结论

下表的“最终判断”指 14 项采用第三位裁决，其余 28 项采用前两位一致的类别判断；不表示所有证据集合已合并。

| 项目 | 已确认结果 | 对论文的意义 |
|---|---|---|
| 18 个未修改 pre | 自然目标冲突正例 0、负例 18；全部判断充分 | 提供真实专家确认的负例，可检验是否过度报告风险；不等于算法误报为零 |
| 新 24 个注入 post | 24 项均为“存在且充分” | 支持所审计注入冲突的可识别性；不是算法取得 100% 正确率 |
| 第三位定向裁决 | 14/14 已处理：9 个充分负例、5 个充分正例 | 本批送审争议已有采用依据，不再列为等待裁决 |
| 前两位原始类别一致性 | 存在性 39/42、κ=0.842；充分性 37/42、κ=0.222；联合 35/42 | 均在裁决前计算；第三位定向子集另报 |
| 证据集合与方法质量 | 已统计；14 项用第三位完整参考，28 项保留双参考 | 新 24 post 来自 14 source SCC；未裁决正例逐参考评分后取平均，不构造并集 gold |

**最终结论：注入版本的目标冲突可被专家识别，SA 在新 post 的专家证据质量上优于 LEA 的若干指标，但各方法在自然原文负例上均有明显过度报告。** GPT 的 SA−LEA 最小证据召回差为 +25.5 pp [15.3,35.1]；Gemini 为 +2.2 pp [−7.4,12.0]。没有自然正例，不能据此声称自然正例检出能力已验证。

新 24 post / 14 source SCC 的主统计先在同 source 内平均、再 source 等权。下表为百分比；旧 12 原汇总另列，不混入此表。

| 模型 | 方法 | 最小证据召回 | 修复材料覆盖 | 修复参考 precision |
|---|---|---:|---:|---:|
| GPT-4o | One-shot | 40.5 | 34.1 | 59.9 |
| GPT-4o | LEA | 65.4 | 56.1 | 66.5 |
| GPT-4o | SA-MCGS | 90.8 | 73.1 | 85.0 |
| Gemini Pro | One-shot | 69.6 | 37.0 | 91.5 |
| Gemini Pro | LEA | 86.3 | 61.3 | 71.8 |
| Gemini Pro | SA-MCGS | 88.5 | 68.3 | 88.4 |

GPT One-shot 20/24 valid，其余 24/24；失败不移出分母。18 pre 的首试 FP/abstention/invalid 分别为：GPT One-shot 12/0/6、LEA 16/0/2、SA 8/0/10；Gemini One-shot 18/0/0、LEA 17/1/0、SA 4/0/14。恢复后的 GPT LEA 为 17/0/1，SA 为 GPT 15/0/3、Gemini 18/0/0。无效多导致 FP/all 看似低，不代表特异性更好。

完整区间、原始一致性、逐参考和逐例数据及可重建脚本见 [专家离线报告](manuscript_revision_20260922/expert_analysis/REPORT_EN.md)。20,000 次 source-SCC bootstrap，seed 20260922；258 次逐参考评分与独立实现一致，247 个来源哈希核验通过。

统计按 source SCC 聚类；同源 post 先在源内汇总，再作 pre/post 配对，不直接相减 18 与 36 个原始行。样本来自原主实验选定来源，可以称自然原文/未修改来源，不能把 0/18 外推为领域总体自然风险率。旧 12 与新 24 分层，并保留排除旧 12 的分析。

### 8.4 本轮落地与仍需作者确认的事项

1. **已完成离线统计。** 新脚本适配二选一字段及 42 / 42 / 14 覆盖；对未裁决证据集逐参考评分再平均，保留原始票，不补第三票。
2. **旧 12 分层保留。** 本轮沿用原稿真实汇总、新 24 独立呈现；不强行合并旧字段，也未重新打标。
3. **已写入正文与附录。** 主要结论、三方法专家指标、自然负例、原始一致性和裁决/恢复协议均已整合；作者尚需确认新一轮专家资格、同意、补偿及适用伦理信息，不由系统补造。

专家收集、裁决及本轮统计整合已结束；剩余为作者核对、压页与提交材料，不等待第三专家，也不重跑主实验。

## 9. 接下来怎么做：执行次序与验收

### 9.1 默认方案：先完成离线整合与写作，不重跑全 pipeline

| 优先级 | 工作包 | 具体交付 | 完成条件 |
|---|---|---|---|
| P0-1 | 统一可入稿数字 | 第 4.2 节五模型三方法共 60 个指标值固定；专家统计沿用原版本 | 主表、图表及段落采用同一结果版本，60 个主表数值逐一核对 |
| P0-2 | 双基线主比较与 rebuttal 证据整合 | 本方案先按旧版逐处更新并标蓝；随后完成第 7.3 节图表和第八页之后文字，导出同源修订版及净稿 | 保留原故事线、章节顺序与贡献框架；五模型结果和图表接入后逐段审阅及压页 |
| P0-3 | 专家正式统计与旧标签衔接 | 已完成 IAA、双参考指标、误报/弃答及聚类区间；旧 12 原汇总、新 24 分层保留 | 无新标注或模型调用；待作者核对专家资格、同意、补偿和伦理信息 |
| P0-4 | 写重投修改说明 | 逐 reviewer R1–R13 对应新稿章节/表格；附主要数值替换说明 | 正式提交承诺逐项有处理，不靠长篇“已经解释过” |
| P1-1 | 附录与复现包 | 全协议、采样、hash、runtime/retry 口径、历史诊断、匿名入口 | 能在不调用模型的情况下从 frozen results 重建主表 |
| P1-2 | 最终质量检查 | 编译、分页、图表可读性、引用与匿名/伦理清单 | 正文自足；无占位专家结果混进最终提交 |

9 月 22 日的核验、专家离线统计和正文/附录增补已经落地。本次新增的五模型主比较与图表按本方案继续接入论文。修订记录见 `manuscript_revision_20260922/WRITING_RECORD_ZH.md`。当前净稿约 25 页、正文约 10 页，页数以最终编译为准；后续需按投稿要求压页并准备重投说明，不把增补稿当作已验收投稿包。

### 9.2 额外实验只作备选，不纳入本轮默认修改

| 可选工作 | 什么时候值得做 | 精确边界 |
|---|---|---|
| 更有针对性的搜索机制对照 | 若仍要把“critical-pair/search 明确优于简单重复局部 prompting”作为核心贡献 | 预先选多域/多 source SCC，使用同期 Full、同 schema 与等预算局部对照；不得只挑有利域补到显著；数量/预算另定 |
| 独立 OC / final closure / core threshold | 只有将其列为必须证明的核心贡献时 | 当前没有修正后的独立证据；默认将其作为实现设计而非独立已验证贡献 |
| 更多自然案例 | 若真实标签显示当前 positive / negative 覆盖不足且文章仍需该能力主张 | 另行定义增量目标，不改旧 12、不用结果筛选制造自然发生率 |

先把已有 rebuttal 修复结果与专家审计接入原稿，不因追求额外完整性自动增加实验。本表只是未来确有必要时的备选，不作为本轮整合或投稿的默认前置条件；任何新增实验另行确认范围与费用。

LEA 补齐已完成，从待办中移除。本轮按已确认结果更新图表与文字。

### 9.3 重投修改说明怎样写

建议按五个主题组织：① baseline 与 oracle 定义；② Stage-1 / Stage-2 机制；③ cost、失败与 prior；④ 专家和自然原文；⑤模型差异、指标与适用边界。每条都给“旧意见→实际修改→新表/章节→仍未覆盖的边界”，最后附 R1–R13 对照。

**保留已提交 rebuttal 的历史记录，新稿使用核验后的结果；不为保持数字一致而沿用已知问题。** 修改说明只需一段或紧凑清单，交代“更新原因→涉及范围→新数值→对结论的影响”，不另加冗长版本核对章节，也不把内部 debugging 日志塞入正文。

区分新增/扩样与实验修正：Stage-1 说明案例对应关系复核及 17-case 同期补跑；Stage-2 说明 no-replacement 对照实现校正与 80-case 回放范围；Cost 说明身份和分母统一。不统称为“算法优化”，也不暗示完全同条件的重复。关系记忆移除后改善在旧 rebuttal 已存在，无需写成新发现的结论反转；critical-pair 的描述性降幅相近，窗口效应缩小，分别按第 4.4 节说明。

ARR 重投需要关联前次 submission，并提交新的逐点修改说明 PDF；不是把旧 rebuttal 原样作为新回复，但旧记录仍可追溯。官方允许改进方法、扩展实验与分析；Reviewer / AC 偏好由作者选择。[ARR 重投规则](https://aclrollingreview.org/cfp#resubmissions)。本轮以清楚、可核验的更新维护可信度，不预设更新数据必然加分，也不将其本身视为信誉问题。

### 9.4 双 3.5 内部验收清单

- [x] 原问题、故事线、方法流程、主要章节顺序与贡献框架保持不变；主结果更新为五模型各 80 案例、三方法比较。
- [ ] Reviewer 能用两句话复述我们的任务与方法价值，不需要先理解所有缩写。
- [ ] One-shot 与 LEA 作为两类主要基线贯穿五模型主表、规模图和案例图；模型与方法顺序一致。
- [ ] 主要可部署比较不依赖 oracle 选择；LEA 与 One-shot 的样本范围和计算差异清楚。
- [ ] 正文如实交代 Stage-1 不利结果与模型差异；no-memory 完整数字可放附录，但正文不保留其独立增益已获验证的暗示。
- [ ] Stage-1 描述性 80-case 不冒充统一同期重跑；与 Stage-2 的 Full 来源及样本范围标注清楚。
- [ ] Stage-2 的正向证据准确归因为 final-core retention，未延伸到搜索轨迹。
- [ ] Risk-all、evidence quality、compression、validity、abstention 不混用。
- [ ] 主表每个 N 都能解释成 source / variant / model-case，区间按 source 聚类。
- [x] 三份真实专家标注已收齐：42 / 42 / 14，共 98 份判断；作者已确认实际完全盲评。
- [x] 14 项第三位完整答案已按作者指定记录为裁决；原始判断保留。
- [x] 专家正式指标与区间完成；旧 12 原汇总、新 24 分层保留，双参考处理透明，不将裁决后一致当 IAA。
- [ ] 实际成本包括可观察失败与恢复；不把最终完成率当首试可靠性。
- [ ] 抽象、贡献、图注、主表、结论互相一致，没有“正文温和、图注夸大”。
- [ ] R1–R13 在 modification notes 各有落点；主要数值更新说明原因、范围和结论影响，旧 rebuttal 记录保留。
- [ ] 主表 15 行、60 个指标值与第 4.2 节一致，图表使用对应逐例结果。
- [ ] 三方法规模图、Figure 4 逐案例配对收益图、预算参考线和同案例三列图已完成；配对横条各合计 80，净收益与主表 Risk-all 差值一致。
- [ ] 新版 LaTeX 已编译和视觉检查，专家占位未被误作结果提交。

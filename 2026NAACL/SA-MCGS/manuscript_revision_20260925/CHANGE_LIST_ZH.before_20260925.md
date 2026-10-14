# 论文修改清单：按正文至附录顺序

日期：2026-09-23。对照 2026-09-22 备份原稿与当前 LaTeX。

以下按实际阅读顺序排列：摘要 → 正文 → 附录。只列已经修改的位置，未改章节略过；这些是已完成修改，不是后续计划。

## 一、正文

| 顺序 | 修改位置 | 改了什么 | 修改原因 |
|---|---|---|---|
| 1 | Abstract 摘要 | 保留原实验概括，加入 LEA 比较、模型差异、消融、成本和专家验证。 | 让摘要反映新增证据。 |
| 2 | Introduction：贡献列表最后一项 | 将实验贡献扩展为双基线、组件消融、成本及专家审计。 | 同步新版验证内容，不改变原贡献框架。 |
| 3 | §2 Task Formulation | 补充 source SCC、注入 variant、model-case 的区别；专家证据指标与 benchmark 指标分开。 | 解释样本数量及指标各自测什么。 |
| 4 | §3.6 Dynamic core compression | 局部调整机制作用的表述，加入 Stage-2 回放的指引。 | 将动态 core 的设计与实际验证对应起来。 |
| 5 | §3.7 Computational feasibility | 加入实测成本指引，以及内部并发可减少等待时间的说明。 | 接上成本实验，保留并行效率论点。 |
| 6 | §4.2 Domain formatting and shared risk semantics | 将共享风险定义的参与方法扩展为 One-shot、LEA、SA。 | 明确三种方法判断的是同一种风险任务。 |
| 7 | §4.3 Critical structural injection | 写明原实验 20 个源 SCC → 80 variants → 320 model-cases，以及匹配集的来源和数量。 | 交代不同实验集合之间的关系。 |
| 8 | §4.4 Baselines and models | 正式并列 full-SCC One-shot 与 LEA；介绍 LEA 的窗口和聚合；oracle 单列；说明实际覆盖和计算预算。 | 回应强基线、比较公平性和 oracle 定义问题。 |
| 9 | §5 Main Results | 新增 36 variants、两模型、三方法主表，包含质量、压缩率和失败数；调整原 320 结果图注与解释。 | 让双基线成为主要比较，同时保留原四域四模型证据。 |
| 10 | §5.1 Breakdown by model and domain | 明确 GPT/Qwen 的提升，以及 DeepSeek/Gemini 的不同表现。 | 回应平均数掩盖模型差异的问题。 |
| 11 | §6.4 Component ablations：Stage-1 | 加入同期 17-case 消融表，并说明更新后的描述性 80-case 结果。 | 回应 memory、critical-pair 和局部窗口的组件归因。 |
| 12 | §6.4 Component ablations：Stage-2 | 加入 80-case replacement／no-replacement 回放，报告相同 core 大小下的效果差异。 | 验证动态 core 对最终证据保留的贡献。 |
| 13 | §6.5 Inference cost and prior sensitivity：成本部分 | 加入 72 jobs 的三方法成本—效果表，以及并发说明。 | 回答提升效果需要多少 calls、tokens；解释如何缓解等待时间。 |
| 14 | §6.5：Prior 部分 | 简述 relation-prior 系数 ±20% 的测试结果。 | 回应固定权重的敏感性问题。 |
| 15 | §6.6 Expert evidence and unmodified originals | 依次加入盲评与裁决协议、专家证据质量、未注入原文的误报发现。 | 回答子图是否有用，以及没有冲突时是否仍报告风险。 |
| 16 | §7 Related Work | 补充 LEA 的定位及其与 SA 自适应搜索的区别。 | 解释新增强基线的设计来源与比较意义。 |
| 17 | §8 Conclusion | 更新为双基线、消融、成本和专家证据支持下的总结。 | 让结论与新版实验一致。 |
| 18 | Limitations | 补充模型和样本覆盖、自然负例、额外计算及人工复核边界。 | 交代新增实验实际覆盖了什么、尚未覆盖什么。 |

## 二、附录

| 顺序 | 修改位置 | 改了什么 | 修改原因 |
|---|---|---|---|
| 19 | 附录 B 开头、B.1 | 将原 12-case 专家审计明确标为原有批次，原结果保留。 | 区分新旧标注协议，直接沿用已有成果。 |
| 20 | B.2：样本、标注与裁决 | 加入 42 个展示项、两位全量＋第三位定向标注，以及裁决前一致性。 | 完整交代专家审计如何完成。 |
| 21 | B.2：专家参考评分 | 加入证据召回、修复材料覆盖、precision、双参考规则和完整方法表。 | 给正文的子图质量结论提供依据。 |
| 22 | B.2：未注入原文误报 | 加入判断规则，以及首试／恢复后的误报、弃答、失败统计。 | 完整回答负例与过度报告问题。 |
| 23 | 附录 G：Shared Risk Rubric Prompt | 将共享风险任务的描述同步为三方法框架。 | 与正文双基线设置一致。 |
| 24 | 附录 H：Prompt Templates | 明确 LEA 与 SA 使用同类局部输出接口，补充聚合协议指引。 | 解释公平比较具体如何实现。 |
| 25 | 附录 J：Additional Experimental Details | 修正样本单位称谓，同步 oracle 的角色说明；原数值保留。 | 避免附录仍沿用与正文不一致的旧描述。 |
| 26 | 新增附录 K.1：LEA Protocol | 补全 LEA 窗口、缓存、聚合、容量及 oracle 选择规则。 | 支持强基线复现。 |
| 27 | K.2：Stage-1 | 完整列出同期 17-case、描述性 80-case 和各臂成本。 | 展示全部指标及不同实验范围。 |
| 28 | K.3：Stage-2 | 补全回放策略、全部指标和统计区间。 | 支撑动态 core 消融结论。 |
| 29 | K.4：Cost and Reliability | 分模型报告完整成本、可靠性、恢复消耗及并行时间公式。 | 补足正文成本表的细节。 |
| 30 | K.5：Prior Sensitivity | 列出默认值和上下扰动的完整结果。 | 支撑正文的敏感性结论。 |
| 31 | K.6：Identity and Statistical Conventions | 说明样本身份、同源统计、失败分母及压缩率口径。 | 让新增实验能够核对和重算。 |

## 三、全文统一格式

新增／改写为蓝色，被替换旧文保留删除线；净稿开关隐藏修订痕迹，便于连续阅读。标题、原故事线、方法模块和章节主顺序保留。

## 对照源文件

- [主文及原附录的局部修改](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex)
- [双基线定义](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_baselines.tex)、[匹配主表与分析](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_results.tex)
- [消融、成本和 Prior 正文](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex)、[专家正文](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_main.tex)
- [专家附录 B.2](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex)、[实验附录 K](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex)

本次仅整理清单，没有再次修改论文内容或新增实验。

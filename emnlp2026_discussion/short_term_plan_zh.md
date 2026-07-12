# EMNLP 2026 Discussion 短期补充实验与回复计划

目标：第一轮作者回复先保持非常礼貌、感谢式的语气，明确接受 reviewer 的核心建议，并附上我们在 discussion 期间会补齐或整理的短期实验计划。回复策略不是强辩，而是让 reviewers 看到：他们指出的问题我们都认真接住了，而且有清晰、可交付的补充证据。

## 总体回复姿态

1. 先感谢三位 reviewer 对问题设定、技术动机和实验分析的认可。
2. 对主要不足不回避：component ablation、inference cost、baseline fairness、injected-risk limitation、negative cases、model-level non-uniformity 都明确承认需要补充。
3. 第一轮回复先给出“正在补齐的实验计划 + 已有可整理证据”，避免在没有结果前写死数字；对成本问题先说明后续回复会补充按 case scale 分层的 token/runtime 表和理论复杂度分析，并且成本表会覆盖 Naive、SA-MCGS 和新增的 graph-aware decomposed baseline。
4. 对高风险应用表述降调：强调 SA-MCGS 是 decision-support tool，不是 automated risk adjudicator。
5. 对不能短期完成的大型新增实验谨慎说明：例如完整 naturally occurring risk benchmark 或外部 GraphRAG 系统复现，不承诺在 discussion 阶段内完成，只承诺在论文中弱化 claim 并补充 limitation。

## Reviewer 关切合并

| 关切 | 提出 reviewer | 我们要补的内容 | 短期可行性 |
|---|---|---|---|
| SA-MCGS 组件级 ablation 不足 | iMEC, rxvy | relation memory、OC signal、critical-pair ledger、dynamic/replacement core、random/local-window selection 的消融 | 高，优先做 trace replay 或小规模补跑 |
| 推理成本分析不足 | iMEC, rxvy, wWUk | input/output tokens、LLM calls、runtime、cost-performance tradeoff、按 SCC size/case scale 分层的理论与实测成本；覆盖 Naive、SA-MCGS 和新增 GraphRAG-style baseline | 高，Naive 从已有日志补算；SA-MCGS 做低并发 token audit；新增 baseline 同步记录成本 |
| baseline fairness / prompt decomposition confound | iMEC, rxvy, wWUk | matched valid-only、轻量 Naive、同 rubric 说明、GraphRAG-style local evidence baseline | 中高，已有 E0/E1/E5，可再补一个 graph-aware decomposed baseline |
| 主要评估依赖 injected risks | rxvy, wWUk | 降低真实高风险场景 claim，补 human audit 解释；如时间允许加少量 naturally occurring/clean examples | 中，claim 修订高可行，完整 natural benchmark 低可行 |
| clean/non-risk SCC 与 over-reporting | rxvy | clean SCC negative-case evaluation，报告 false positive / over-report rate | 中高，可抽样补跑或复用旧 clean baseline |
| subgraph precision / irrelevant-node rate | rxvy | 除 compression 外增加 retained subgraph cleanliness 指标 | 高，可从已有输出和 ground-truth endpoint 集合直接计算 |
| prior coefficient sensitivity | rxvy | 对固定 prior 权重做小范围扰动或 profile sensitivity | 中，优先做 representative subset |
| SA-MCGS 对强模型不总是优于 Naive | iMEC, rxvy | 用 model-level breakdown 承认 Gemini 2.5 Pro / DeepSeek-V3 上 Naive 很强，并重写 headline claim | 高，已有 Table A4 |
| 技术贡献显著性 | iMEC | 更集中解释 cyclic SCC failure、relation-indexed memory、SCC-aware rollout control、dynamic risk core 的组合贡献 | 高，主要是回复与论文文字修订 |
| typo / 术语定义 | iMEC, rxvy | 修正 `Appendix 9 separates...` -> `Appendix J separates...`，明确定义 oracle-risk Naive 是 boosted, ground-truth-selected full-SCC baseline | 高，直接修 |

## P0：必须优先补齐的内容

### 1. 推理成本表

覆盖 reviewer：iMEC, rxvy, wWUk

要做：

- 从主实验日志中统计 Naive / boosted Naive 的 observed input tokens、output tokens、total tokens、LLM calls、runtime。
- 对 SA-MCGS 复做一个 stratified token audit：覆盖不同 domain 和 SCC size/case scale，记录 provider-observed input/output/total tokens。
- 对新增的 GraphRAG-style Local Evidence Aggregation (LEA) baseline 同步记录 observed input/output tokens、LLM calls、runtime、失败/不可用输出比例，并纳入同一张 cost-performance table。
- SA-MCGS token audit 使用低并发设置，避免把上游排队或限流造成的等待时间混入算法本身的 runtime 解释；成本表中记录 concurrency。
- 统计 LLM call 数量、平均每 case runtime、失败/不可用输出比例，并按 SCC size/case scale 分层。
- 把 cost 与 performance 放在一起：Root@3、Risk-any、Risk-all、Compression、tokens/case、calls/case、runtime/case、concurrency。表格列以方法为单位覆盖 oracle-risk/full-SCC Naive、SA-MCGS 和 LEA。
- 给出理论复杂度说明：Naive full-SCC prompting 的 prompt cost 随 SCC 文本规模增长；LEA 的成本主要来自固定 local-window evidence aggregation，可写成 `O(K * tokens(w))`，其中 `K` 是实际检索/评分窗口数；SA-MCGS 的成本主要是 `O(B * tokens(w))`，其中 `B` 是实际 local-window rollout LLM calls，`w` 是 local window size，且 transposition table 会使实际 calls 小于 rollout budget。

预期产出：

- `cost_accounting.csv`
- `cost_accounting.md`
- `cost_by_method_and_case_scale.csv`
- `cost_by_case_scale.csv`
- `cost_complexity_note.md`
- 内部执行口径：SA-MCGS token audit 采用 20 个代表性 case，覆盖全部 `domain x SCC-size` bucket；但对外回复只说 stratified by case scale，不说 small sample。
- discussion 中一句核心口径：SA-MCGS 确实增加调用次数和 wall-clock 成本，我们感谢 reviewer 指出这一点；后续回复会给出覆盖 oracle-risk/full-SCC Naive、SA-MCGS 和 GraphRAG-style LEA 的按 case scale 分层 provider-observed token/call/runtime 表，并在论文中加入理论复杂度和实测成本分析。

### 2. 组件级 ablation 小表

覆盖 reviewer：iMEC, rxvy

当前判断：

- 现有实验可以支持 TreeMCTS 在 SCC 中的 failure mode、rollout budget convergence、compression profile trade-off。
- 但现有实验不能充分回答 reviewer 提出的 “which SA-MCGS components are responsible for the gains”。
- 因此第一轮回复不应声称已有 ablation 已经足够，而应明确感谢并接受建议，说明我们会补充组件级消融。

第一轮回复口径：

> We agree that the current ablations mainly diagnose the SCC failure mode and analyze budget/compression behavior, but do not yet sufficiently isolate individual SA-MCGS modules. We are adding a component-level ablation table to separate the effects of relation-first memory, critical-pair revisiting, OC/core signals, and local-window selection.

优先级顺序：

1. Full SA-MCGS：主方法对照，使用当前 locked main setting。
2. no relation-first memory：关闭 relation-first evidence / relation prior，检验 relation memory 的贡献。
3. no critical-pair ledger / revisit：关闭 critical-pair ledger 或 revisit，检验 persistent pair evidence 的贡献。
4. random local-window selection：保留 local-window prompt 和 output schema，但不使用 graph-guided / UCB-style selection，检验 search policy 的贡献。
5. local-window repeated prompting without graph search：回应 reviewer 关于 decomposed/local-window baseline 的公平性问题。
6. no OC/core signal：去掉 OC 或 OC-like evidence 在 final core priority 中的作用，检验 OC/core signal 的贡献。
7. monotone core instead of replacement/dynamic core：如果时间允许，补充 dynamic replacement core 与 monotone accumulation 的对比。

执行策略：

- 能通过现有 trace replay 完成的先做 replay，不额外花 LLM 成本。
- 必须补跑 LLM 的项目先缩小到 stratified subset，覆盖不同 domain、SCC size 和 template；优先覆盖 CUAD 长 SCC、BGB/SEC 图结构清晰的 SCC，以及 reviewer 指出的强模型/弱模型差异。
- 不追求把所有 ablation 做成主表；discussion 期间需要的是足以回应“which components matter”的证据。
- 如果时间不足，最小可交付 ablation table 包含：Full、no relation-first memory、no critical-pair ledger/revisit、random local-window selection。

预期产出：

- 一张 compact ablation table：N、Root@3、Risk-any、Risk-all、Compression、Avg subgraph。
- `component_ablation.md`
- `component_ablation.csv`
- discussion 中承认现稿 ablation 主要诊断 TreeMCTS failure，不足以隔离 SA-MCGS modules；然后说明我们正在补充组件级消融，并会在后续回复中报告表格。

### 3. baseline fairness / schema burden 说明

覆盖 reviewer：iMEC, rxvy, wWUk

已有可用材料：

- `E0_MATCHED_VALID_ONLY.md`：strict、valid-only、matched usable-output 三种分母拆开。
- `E1_NAIVE_OUTPUT_BURDEN_CONTROL.md`：轻量 Naive 降低输出 schema 负担后的表现。
- `E5_PROMPT_RUBRIC_PARITY.md`：Naive 和 SA-MCGS 使用同一 risk rubric。
- `tabA4_model_breakdown.md`：model-level breakdown，显示强 full-SCC 模型上的非一致优势。

还要补的最小实验：

- 一个更公平的 graph-aware decomposed baseline，暂称 `GraphRAG-style Local Evidence Aggregation (LEA)`。
- 该 baseline 受 GraphRAG / LegalGraphRAG / legal KG-RAG / contract-graph 工作启发，但不声称复现外部系统，因为这些系统的任务、输入 graph schema 和输出目标与我们的 SCC risk-subgraph extraction 不完全相同。
- 与 reviewer3 明确提到的近期工作对应关系：
  - Dechtiar et al. (2025) 的 `GRAPH-GRPO-LEX` 证明 contract clause 可以显式建模为 graph nodes / relation edges，因此支持我们把 full-SCC one-shot prompt 替换为 graph-window retrieval。
  - Chen et al. (2026) 的 `LegalGraphRAG` 使用 hierarchical legal graph 和 Researcher/Auditor/Adjudicator 式 evidence retrieval、verification、synthesis，因此支持 LEA 的“局部 evidence 抽取 -> 透明聚合”结构。
  - de Martim (2025) 的 legal GraphRAG / SAT-Graph RAG 强调 hierarchy、cross-reference 和 deterministic retrieval，因此支持 LEA 采用固定图窗口与引用边检索，而不是随机或模型自由检索。
- LEA 使用与 SA-MCGS 相同的 SCC、node texts、directed edges、risk rubric 和 local-window evidence schema。
- LEA 先用 deterministic graph retrieval 生成 ego-window / edge-window，再独立抽取 local risk evidence，最后用透明的 score aggregation 输出 risk subgraph。
- LEA 不使用 SA-MCGS 的 UCB-style selection、relation-first memory、critical-pair revisit、OC/core signals 或 dynamic replacement core。
- 这样可以直接控制 prompt decomposition 和 output-schema burden；若 SA-MCGS 仍优于 LEA，则差距更能归因于 search policy、persistent relation evidence 和 dynamic core construction。
- 第一轮回复只承诺会补充这个 baseline，不提前固定 window size、window budget、LLM call 数或聚合系数；这些参数等实际实验跑完后在后续回复/表格中一起报告。
- LEA 的 provider-observed tokens、LLM calls 和 runtime 必须进入同一张 inference-cost / cost-performance 表，而不是只在 baseline 表中单独给性能。

预期产出：

- `graph_local_evidence_baseline.md`
- `graph_local_evidence_baseline.csv`
- discussion 中核心口径：我们同意 reviewer 指出 baseline comparison 可能混入 schema difficulty；因此会同时报告 matched valid-only、lite Naive 和一个 graph-aware decomposed baseline。该 baseline 会使用固定的图窗口检索和同一 local evidence schema；具体窗口预算、调用次数、聚合设置以及 tokens/calls/runtime 将在实验完成后随结果报告。

## P1：强烈建议补齐的内容

### 4. clean / non-risk SCC negative-case evaluation

覆盖 reviewer：rxvy，也能回应 wWUk 的 practical deployment concern

当前判断：

- 不能只靠最终 320 条 injected-risk 主实验直接得到，因为这些 case 都是 positive/stress cases，无法衡量 clean SCC 上的 false positive。
- 仓库里确实有旧版 clean baseline / no-injection ablation：
  - `control_24n.json`：BGB 24-node clean SCC 上，MCGS 仍标出大量 high-risk / OC 节点，说明早期协议下 over-reporting 明显。
  - `ablation_suite.json`：clean MCGS 在 9/9 条件下都有 OC，joint LLM clean FP 也很高；这组更像早期 delta-detection failure analysis。
  - `pruning_comparison.json` / `pruning_v2.json`：clean SCC 上 OC 数依 pruning/profile 变化很大，说明 pruning/profile 会影响 false-positive behavior。
  - 后续 `clause_battle.json` / `deal_package_mcgs.json` / `deal_clause_ultimate.json` 的 clean baseline 好一些，但任务、数据和协议不同。
- 因此第 4 项不是一个“已有数据可直接证明低误报”的加分项，而是一个 over-reporting audit。对 reviewer 的口径应是：感谢指出 negative-case 缺口，我们会补充或整理 clean-SCC audit，并如实报告 over-reporting/false-positive behavior，同时在 limitations 中强调 decision-support 而非自动裁定。
- 最稳妥做法是对当前主实验协议下的代表性 SCC 做 unmodified/clean counterpart 小规模补跑；这需要新增 LLM calls，但不需要重新构造 benchmark。

要做：

- 从四个 domain 中抽取没有 injected critical risk 的 clean SCC。
- 对 SA-MCGS 和简单 baseline 跑风险子图抽取。
- 报告 false positive rate、over-report rate、平均返回子图大小。
- 如果 clean SCC 标注不够完整，先做保守版本：只报告“是否产生 high-risk core / 是否过度返回大量节点”。

预期产出：

- `negative_clean_scc_eval.md`
- discussion 口径：感谢 reviewer 指出 current metrics 主要关注 injected endpoints；我们会补充或整理 clean SCC negative-case audit 来检查 over-reporting，并在论文中明确 false positives / review burden 的限制。
- 第一轮对外口径：我们同意 negative/non-risk SCC 是评估 deployment behavior 的必要补充；会在后续回复中补充 clean/non-risk SCC 上的 false-positive / over-reporting 数据，并报告返回子图大小等诊断指标。

### 5. subgraph cleanliness 指标

覆盖 reviewer：rxvy

当前判断：

- 可以从已有主实验结果直接计算，不需要新增 LLM 实验。
- 现有 JSON 已经包含方法返回的 subgraph nodes，以及 injected root / witness / evidence / affected nodes。
- 需要在论文/回复中说明：用 injected endpoints 定义的 precision / irrelevant-node rate 是保守指标，因为某些中间节点可能对 repair path 有帮助，但没有被 ground truth 标成 endpoint。

要做：

- 在已有主实验结果上计算 retained subgraph precision / irrelevant-node rate。
- 一个可行定义：
  - Relevant nodes = root + witness + affected nodes。
  - Subgraph precision = retained relevant nodes / retained subgraph nodes。
  - Irrelevant-node rate = retained non-relevant nodes / retained subgraph nodes。
- 和 compression 一起报告，说明“更小”不等于“更干净”，也不等于“保留了修复所需证据”。

预期产出：

- `subgraph_cleanliness_metrics.md`
- discussion 口径：我们同意 compression alone is insufficient，因此增加 cleanliness 指标。
- 第一轮对外口径：我们同意 compression alone 不能说明 retained subgraph 是否干净；会补充 endpoint-based subgraph precision / irrelevant-node rate，与 compression 和 endpoint retention 一起报告。

### 6. prior coefficient sensitivity

覆盖 reviewer：rxvy

当前判断：

- 不能完全靠已有主结果得到真正的 prior-coefficient sensitivity，因为 reviewer 关心的权重会影响 rollout selection；权重一变，后续访问的 local windows 和 LLM evidence 也会变。
- 现有 trace 可以做一部分 post-hoc replay，例如 final core construction / compression policy 对权重或 profile 的敏感性；已有 E3 也能说明 compression profile trade-off。
- 但如果要严谨回应 “fixed prior coefficients affect rollout selection and core construction”，最好还是做一个小规模扰动补跑。该项优先级低于 cost、component ablation、baseline fairness 和 cleanliness。

要做：

- 对 relation prior / OC / critical-pair 权重做小范围扰动。
- 推荐先做 3 个 profile：
  - default
  - lower-prior：关键 prior 权重乘 0.8
  - higher-prior：关键 prior 权重乘 1.2
- 如果完整 320 cases 太贵，先做 representative subset。

预期产出：

- `prior_sensitivity.md`
- discussion 口径：感谢 reviewer 指出固定系数可能影响 rollout selection 和 core construction；我们补充 sensitivity check。
- 第一轮对外口径：我们同意固定 prior / core-construction 系数需要稳定性检查；会在后续回复中补充 coefficient-sensitivity 数据，报告 key metrics 在合理扰动下是否稳定。

## P2：主要通过文字修订处理

### 7. injected risks 与 naturally occurring risks 的 claim 降调

覆盖 reviewer：rxvy, wWUk

要做：

- 明确当前 benchmark 是 controlled critical structural stress test，不声称已经覆盖 naturally occurring risk distribution。
- 强调 human audit 只证明 injected risks 对 qualified readers 是语义可见的，不证明真实风险分布完全匹配。
- 在 limitations 中加入 naturally occurring cases 需要后续人工审计。

不建议短期硬做：

- 不建议在 discussion 阶段内承诺完整 naturally occurring benchmark。
- 若要补，只做 small illustrative natural/clean cases，并明确是 preliminary evidence。

### 8. model-level non-uniformity 的边界讨论

覆盖 reviewer：iMEC, rxvy

已有结果：

- Gemini 2.5 Pro 的 oracle-risk Naive 很强：Root@3 99%、Risk-any 100%、Risk-all 97%。
- DeepSeek-V3 的 oracle-risk Naive 也很强：Root@3 87%、Risk-any 95%、Risk-all 87%。
- SA-MCGS 的优势主要在 long/noisy SCC、输出稳定性压力更高、endpoint retention 更困难的设置中更明显，尤其是 Qwen2.5-72B 和 CUAD。

要改的口径：

- 不写“uniformly superior across all models”。
- 改成“SA-MCGS improves robustness and endpoint retention under cyclic long-context pressure, while strong full-SCC models can perform competitively on some settings.”

### 9. 技术贡献表述强化

覆盖 reviewer：iMEC

要强调：

- 问题不是普通 graph search，而是 cyclic document SCC 中 path-copy explosion 和 state duplication。
- 贡献不是简单集成，而是把 SCC localization、relation-indexed evidence memory、critical-pair revisiting、OC evidence 和 dynamic risk core 放在同一个可评估框架中。
- 输出不是 binary label，而是 repair-relevant risk subgraph。

### 10. 社会影响与使用边界

覆盖 reviewer：rxvy

要加的句子：

- SA-MCGS should be used as a decision-support tool rather than an automated risk adjudicator.
- False positives may increase review burden; false negatives may hide contractual, compliance, financial, or dependency risks.
- Graph-construction errors and injected-benchmark performance may cause overtrust on naturally occurring cases.

## 第一轮回复中可以附上的短期计划摘要

建议把下面这组计划放在对三位 reviewer 的第一次统一回复中：

1. 我们会补充 inference-cost accounting，在后续回复中报告覆盖 oracle-risk/full-SCC Naive、SA-MCGS 和 GraphRAG-style LEA 的按 case scale 分层 provider-observed tokens、LLM calls 和 runtime，并加入理论复杂度说明。
2. 我们会补充 SA-MCGS component ablations；同时承认当前 ablations 主要诊断 SCC failure 和 budget/compression behavior，后续会隔离 relation-first memory、critical-pair revisiting、OC/core signals 和 local-window selection。
3. 我们会补充 baseline-fairness checks，包括 matched valid-only、lite Naive、prompt/rubric parity 和一个 GraphRAG-style graph-aware decomposed baseline；第一轮只说明设计目标和控制变量，具体窗口预算、调用次数、聚合参数以及对应成本等到实验完成后随结果报告。
4. 我们会补充或整理 clean/non-risk SCC negative-case audit，并如实报告 over-reporting 或 false-positive behavior。
5. 我们会增加 subgraph cleanliness 指标，例如 irrelevant-node rate / subgraph precision。
6. 我们会增加 fixed-prior sensitivity check。
7. 我们会修订论文措辞，弱化 naturally occurring high-stakes risk extraction 的泛化 claim，并明确 decision-support 使用边界。
8. 我们会更直接讨论 Gemini 2.5 Pro 和 DeepSeek-V3 上 oracle-risk Naive 很强的现象。

## 时间安排建议

| 时间 | 工作 | 产出 |
|---|---|---|
| Day 0 | 整理已有 E0/E1/E5/E3/Table A4 结果，生成 reviewer-facing 摘要 | baseline fairness 和 model-level discussion 草稿 |
| Day 1 | 补 Naive/SA-MCGS cost accounting、低并发 SA-MCGS token audit、subgraph cleanliness metrics | 初版 cost 表、case-scale token/runtime 表、complexity note、cleanliness 表 |
| Day 2 | 跑或 replay component ablations、prior sensitivity | ablation 表、sensitivity 表 |
| Day 3 | 补 clean SCC negative evaluation 和 GraphRAG-style local evidence baseline，并把新 baseline 的成本并入 cost table | negative-case 表、baseline 表、完整 cost-performance 表 |
| Day 4 | 写第一轮 author response，按 reviewer 分别感谢并引用补充计划 | 三个 reviewer 的礼貌回复草稿 |

## 当前最稳妥的优先级

如果时间很紧，优先顺序建议为：

1. Cost accounting
2. Component ablation subset
3. Matched valid-only / lite Naive / rubric parity 整理
4. GraphRAG-style local evidence baseline 及其 cost accounting
5. Subgraph cleanliness metrics
6. Model-level non-uniformity discussion
7. Clean SCC negative cases
8. Prior sensitivity

这样排的原因是：前四项直接对应三位 reviewer 的共同关切，尤其是 baseline fairness 与 cost-performance 必须使用同一套方法集合；第 5-8 项能明显显示我们接受了 rxvy 的细节建议。

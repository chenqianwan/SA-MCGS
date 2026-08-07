# EMNLP 2026 Discussion: Initial Reviewer Comments (Bilingual Draft)

用途：第一轮 author comment 草稿。中文版本用于内部确认语气和内容，英文版本更接近可直接提交到 OpenReview 的正式回复。核心口径：第一轮先真诚感谢并说明补充计划；相关实验表和数据会在 discussion 期间，也就是第一次回复之后，通过 follow-up comments 尽快提供，而不是只留到最终修订稿中处理。

## Reviewer iMEC

### 中文草稿

**感谢您抽出时间认真而具体地审阅我们的论文。** 您对本文核心问题的概括非常到位：在循环文档图中，tree-style search 会因为 SCC 内的重复访问和路径副本而出现预算稀释与 rollout 不稳定。您的评论也帮助我们把 discussion 的重点更清楚地放在贡献边界、组件作用、推理成本、baseline 公平性和强模型结果差异上。我们会在本次初始回复中先说明补充计划，并在 discussion 期间的后续回复中尽快提供相应表格和数据。

具体来说，我们会把后续证据集中补在三处：

1. 组件级消融表。现有消融主要解释 TreeMCTS 为什么会在 SCC 中失败，以及 rollout budget / compression profile 如何变化；它还没有充分拆开 SA-MCGS 内部模块各自的作用。我们正在准备 component-level ablation，至少覆盖 full SA-MCGS、no relation-first memory、no critical-pair ledger/revisit、random local-window selection，并在可行范围内加入 no OC/core signal 与 monotone core instead of dynamic replacement core。这张表的目的不是重复证明整体效果，而是更清楚地展示 relation memory、pair evidence、search policy 和 dynamic core construction 的增量贡献。
2. 成本与复杂度表。我们会按 case scale / SCC size 报告 provider-observed input/output tokens、LLM calls 和 runtime；方法上同时覆盖 oracle-risk/full-SCC Naive、SA-MCGS 和新增的 GraphRAG-style Local Evidence Aggregation baseline。我们也会给出理论复杂度说明，区分 full-SCC prompting、deterministic local-window evidence aggregation 和 SA-MCGS local-window rollout search 的成本结构，使 Root@3、Risk-any、Risk-all、Compression 与 tokens/calls/runtime 能够放在同一张 cost-performance 表中比较。
3. 更公平的 graph-aware decomposed baseline。您对 prompt decomposition 和 output-schema burden 的提醒很精准。除 matched valid-only、lite Naive 和 rubric parity 说明外，我们正在补充 GraphRAG-style Local Evidence Aggregation：它使用固定图窗口检索和与 SA-MCGS 相同的 local evidence schema，但不使用 relation-first memory、critical-pair revisiting、OC/core signals 或 dynamic core。我们会把它的性能和 tokens/calls/runtime 一起报告，用来区分“local decomposition 带来的收益”和“SA-MCGS 搜索与记忆机制带来的收益”。

您关于 model-level non-uniformity 的观察也会直接反映在修改中。Gemini 2.5 Pro 和 DeepSeek-V3 在 oracle-risk Naive 下已经很强，因此我们会避免把结论写成 SA-MCGS 在所有模型上均匀优越，而会改为强调：SA-MCGS 在 cyclic long-context pressure、输出可靠性压力和 endpoint retention 困难的设置中提升更明显；强 full-SCC models 在部分设置下仍然很有竞争力。另外，感谢您指出 “Appendix 9 separates...” 的 typo；我们会将其修正为 “Appendix J separates...”，并在 discussion 中明确 oracle-risk Naive 是使用 ground-truth risk selector boost 的 full-SCC baseline。

### English Draft

**Comment title:** Initial response: plan and forthcoming data.

**Thank you for taking the time to provide such a careful and concrete review.** We appreciate how clearly you identify the central failure mode studied in the paper: in cyclic document graphs, tree-style search can repeatedly revisit the same logical records through different path copies, leading to budget dilution and unstable rollouts. Your comments also help us focus the discussion on the right boundaries: technical contribution, component effects, inference cost, baseline fairness, and non-uniform gains on stronger models. In this initial response, we outline the analyses we are preparing; in follow-up comments during the discussion period, we will provide the corresponding tables and data as soon as they are ready.

We will organize the follow-up evidence around three items:

1. **Component-level ablations.** The current ablations mainly explain why TreeMCTS fails in SCCs and how rollout budget / compression profiles behave; they do not yet isolate the contribution of each SA-MCGS module. We are preparing an ablation table covering at least full SA-MCGS, no relation-first memory, no critical-pair ledger/revisit, and random local-window selection; when feasible, we will also include no OC/core signal and monotone core instead of dynamic replacement core. The goal is to make the roles of **relation memory, pair evidence, search policy, and dynamic-core construction** visible, rather than only reporting the full-system gain.
2. **Cost and complexity accounting.** We will report provider-observed input/output tokens, LLM calls, and runtime by case scale / SCC size. The table will cover oracle-risk/full-SCC Naive, SA-MCGS, and the new GraphRAG-style Local Evidence Aggregation baseline. We will also add a complexity note distinguishing full-SCC prompting, deterministic local-window evidence aggregation, and SA-MCGS local-window rollout search, so that Root@3, Risk-any, Risk-all, Compression, tokens, calls, and runtime can be compared in one cost-performance view.
3. **A fairer graph-aware decomposed baseline.** Your point about prompt decomposition and output-schema burden is well taken. In addition to matched valid-only, lite-Naive, and prompt/rubric parity checks, we are adding **GraphRAG-style Local Evidence Aggregation**. It uses deterministic graph-window retrieval and the same local evidence schema as SA-MCGS, but does not use relation-first memory, critical-pair revisiting, OC/core signals, or dynamic-core replacement. We will report both its performance and tokens/calls/runtime, so the comparison can separate the benefit of local decomposition from the benefit of SA-MCGS's search and memory mechanisms.

Your observation about model-level non-uniformity will also be reflected in the revision. Strong full-SCC models such as Gemini 2.5 Pro and DeepSeek-V3 can be highly competitive under the oracle-risk Naive baseline. We will therefore avoid presenting the result as uniform superiority across all models, and will instead state that **SA-MCGS improves robustness and endpoint retention under cyclic long-context pressure**, especially when full-SCC prompting faces output-reliability or endpoint-retention difficulties. Thank you also for pointing out the “Appendix 9 separates...” typo; we will correct it to “Appendix J separates...” and define oracle-risk Naive explicitly as a boosted full-SCC baseline selected using ground-truth risk metrics.

## Reviewer rxvy

### 中文草稿

**非常感谢您细致而深入的审阅。** 您的评论准确指出了本文最需要补强的几处：injected risks 与 naturally occurring risks 的距离、Naive baseline 的 schema burden、强模型上的非一致提升、SA-MCGS 组件级消融不足，以及 negative cases、subgraph cleanliness 和 coefficient sensitivity。我们认同这些建议，并会在 discussion 期间尽快补充相应数据。

关于 baseline fairness，您指出的 prompt decomposition 和 output-schema burden 正是现有 Naive 对比中需要进一步隔离的因素。当前 Naive 需要一次性读取完整 SCC 并输出 global ranking 与 risk subgraph，而 SA-MCGS 将任务分解为 local evidence extraction 和 algorithmic core construction；因此我们不会只做文字解释，而会补充一个任务对齐的 graph-aware decomposed baseline，暂称 GraphRAG-style Local Evidence Aggregation。我们会配套报告以下证据：

1. matched valid-only 结果，避免不可用输出影响结论；
2. lite Naive / output-burden control，降低 Naive 的输出 schema 负担；
3. GraphRAG-style Local Evidence Aggregation：使用固定图窗口检索和与 SA-MCGS 相同的 local evidence schema，但不使用 relation-first memory、critical-pair revisiting、OC/core signals 或 dynamic core，用来隔离 “local decomposition/schema simplification” 与 “SA-MCGS 搜索和记忆机制” 的贡献。这个新 baseline 也会和 Naive、SA-MCGS 一起进入 token/call/runtime accounting。

关于 model-level non-uniformity，我们会直接修订论文表述：Gemini 2.5 Pro 和 DeepSeek-V3 在 oracle-risk Naive 下已经很强，因此不应把 SA-MCGS 写成 across-model uniform superiority。我们会强调 SA-MCGS 的主要优势在 cyclic long-context pressure 下的鲁棒性、输出可靠性和 endpoint retention。关于组件级消融，我们也会补充 component-level ablation table，覆盖 relation-first memory、critical-pair ledger/revisit、OC/core signals、local-window selection 以及 dynamic/replacement core。

关于 injected risks 与 naturally occurring risks 的距离，我们会把它作为 scope 和 limitations 处理，而不是在 discussion 期间仓促新增 naturally occurring 主实验。具体修订包括：

1. 将当前 benchmark 定位为 controlled structural stress test；
2. 收窄 real high-stakes risk extraction 的泛化表述；
3. 说明 human audit 证明的是 injected risks 的语义可识别性，而不是真实风险分布等价；
4. 在 limitations / societal-impact 中强调 decision-support 使用边界。

最后，我们会补充 clean/non-risk SCC 的 false-positive / over-reporting 数据、endpoint-based subgraph precision / irrelevant-node rate，以及 fixed-prior / core-construction coefficient sensitivity；同时明确 oracle-risk Naive 是 ground-truth-selected boosted full-SCC baseline，并扩展 false positives、false negatives、graph-construction errors 和 overtrust 的社会影响讨论。

### English Draft

**Comment title:** Initial response: plan and forthcoming data.

**Thank you for the detailed and careful review.** Your comments identify several places where the paper should be more precise: the gap between injected and naturally occurring risks, the schema burden of the Naive baseline, non-uniform model-level results, insufficient component ablations, and the need for negative cases, subgraph cleanliness metrics, and coefficient sensitivity. We agree with these points and will provide follow-up data during the discussion period.

Your baseline-fairness concern is important, especially regarding prompt decomposition and output-schema burden. This is exactly the factor that the current Naive comparison does not fully isolate: Naive reads the full SCC and produces a global ranking plus a risk subgraph in one generation, whereas SA-MCGS decomposes the task into local evidence extraction and algorithmic core construction. We will therefore add a task-aligned graph-aware decomposed baseline, tentatively named GraphRAG-style Local Evidence Aggregation, while keeping it aligned with our SCC risk-subgraph extraction task. We will report:

1. **matched valid-only results**;
2. **lite-Naive / output-burden controls**;
3. **GraphRAG-style Local Evidence Aggregation**, using deterministic graph-window retrieval and the same local evidence schema as SA-MCGS, but without relation-first memory, critical-pair revisiting, OC/core signals, or dynamic core. This baseline is intended to separate the benefit of local decomposition / schema simplification from the benefit of SA-MCGS's search and memory mechanisms, and will be included in the same token/call/runtime accounting as Naive and SA-MCGS.

We will also revise the model-level discussion to emphasize where the method is strongest. Gemini 2.5 Pro and DeepSeek-V3 are already strong under oracle-risk Naive, while SA-MCGS shows its clearest value in **robustness, output reliability, and endpoint retention under cyclic long-context pressure**. For ablations, we are preparing a component-level table covering relation-first memory, critical-pair ledger/revisiting, OC/core signals, local-window selection, and dynamic/replacement core construction.

On injected versus naturally occurring risks, we will handle this as a scope and limitation revision rather than adding a naturally occurring main experiment during the discussion period. Specifically, we will:

1. describe the benchmark as a controlled structural stress test;
2. narrow the high-stakes real-world risk-extraction framing;
3. clarify that the expert audit supports semantic recognizability, not distributional equivalence;
4. state the decision-support usage boundary in limitations / societal impact.

Finally, we will provide **clean/non-risk SCC false-positive / over-reporting results**, endpoint-based subgraph precision and irrelevant-node rate, and coefficient-sensitivity results. We will also define oracle-risk Naive as a ground-truth-selected boosted full-SCC baseline and expand the discussion of false positives, false negatives, graph-construction errors, and possible overtrust.

## Reviewer wWUk

### 中文草稿

**感谢您专业而建设性的审阅，以及对本文问题设定、技术动机、框架整合和实证结果的积极评价。** 您指出 cyclic document structures 是法律、监管和依赖分析中现实存在但仍未充分探索的问题，这一点对我们非常重要；我们也感谢您对 reproducibility 的肯定。您的建议非常准确地集中在 naturally occurring risks、representative document-graph / GraphRAG-style baselines 和 cost-performance analysis 三个关键维度。我们会在 discussion 期间尽快补充相应 baseline、成本和诊断结果。

关于 naturally occurring risks，我们同意这是 practical significance 的重要方向。当前 benchmark 更准确地说是 controlled structural-risk stress test，可系统评估 root localization、endpoint retention 和 risk subgraph compression；但它不能等同于 naturally occurring risk distribution。由于“大 SCC、自然发生、严重风险、独立专家确认”同时满足的案例需要单独构建和审计，我们会在论文中明确这一边界，并将 naturally occurring risk distribution 作为重要后续方向，而不是在当前结论中作过度泛化。

针对 baseline 和 cost 两点，我们会补充以下结果：

1. GraphRAG-style Local Evidence Aggregation。您的 baseline 建议很好地指出了我们需要区分“利用结构化图表示”与“SA-MCGS 的 SCC-aware search / persistent memory”这两类收益。我们会补充一个 task-aligned graph-aware decomposed baseline，设计上吸收相关工作的可迁移思想：Dechtiar et al. 的 contract graph modeling 支持把合同条款作为显式节点和边来检索；Chen et al. 的 LegalGraphRAG 强调 candidate evidence retrieval、verification 和 synthesis；de Martim 的 legal GraphRAG 则强调 hierarchy/reference-aware deterministic retrieval。对应到我们的任务中，这个 baseline 使用 deterministic graph-window retrieval、与 SA-MCGS 相同的 local evidence schema 和透明聚合规则，但不使用 relation-first memory、critical-pair revisiting、OC/core signals 或 dynamic-core replacement。这样可以更直接地检验增益来自一般 structured graph representation / local decomposition，还是来自 SA-MCGS 的搜索和记忆机制。
2. Cost-performance accounting。我们会报告 provider-observed input/output tokens、LLM calls、runtime，并按 case scale / SCC size 分层。该成本表会同时覆盖 oracle-risk/full-SCC Naive、SA-MCGS 和 GraphRAG-style Local Evidence Aggregation，并与 Root@3、Risk-any、Risk-all、Compression 一起报告。我们也会加入理论复杂度说明，区分 full-SCC prompting、deterministic local-window evidence aggregation 与 local rollout search 的成本结构。

最后，我们会扩大 limitations / societal-impact discussion，明确 SA-MCGS 应作为辅助审查工具使用，而不是自动化风险裁定系统。再次感谢您提出这些专业而具体的建议，它们有助于让论文的贡献边界、实证证据和部署含义更加清晰。

### English Draft

**Comment title:** Initial response: plan and forthcoming data.

**Thank you for the thoughtful and constructive review.** We appreciate your careful assessment of the problem setting, technical motivation, framework integration, empirical improvements, and reproducibility. Your main suggestions accurately identify three key dimensions for strengthening the paper: naturally occurring risks, representative document-graph / GraphRAG-style baselines, and cost-performance analysis. During the discussion period, we will provide the corresponding baseline, cost, and diagnostic results as soon as they are ready.

On naturally occurring risks, we agree that this is an important direction for establishing practical significance. Our current benchmark is best viewed as a **controlled structural-risk stress test**: it supports systematic measurement of root localization, endpoint retention, and risk-subgraph compression, but should not be presented as a substitute for the naturally occurring risk distribution. Cases that simultaneously contain large SCCs, naturally occurring severe risks, and independent expert validation require separate data construction and audit. We will make this boundary explicit and frame naturally occurring risk distribution as an important direction for future expert-annotated evaluation.

For baselines and cost, we will add two concrete analyses:

1. **GraphRAG-style Local Evidence Aggregation.** Your baseline suggestion usefully points to the need to separate the benefit of structured graph representations from the benefit of SA-MCGS's SCC-aware search and persistent memory. We will add a task-aligned graph-aware decomposed baseline that borrows the transferable ideas from the cited line of work: Dechtiar et al.'s contract graph modeling motivates explicit clause-node and relation-edge retrieval; Chen et al.'s LegalGraphRAG motivates candidate-evidence retrieval, verification, and synthesis; and de Martim's legal GraphRAG motivates hierarchy/reference-aware deterministic retrieval. In our SCC risk-subgraph setting, the baseline will use deterministic graph-window retrieval, the same local evidence schema as SA-MCGS, and transparent aggregation, but will not use relation-first memory, critical-pair revisiting, OC/core signals, or dynamic-core replacement. This will help distinguish general benefits from structured graph representation / local decomposition from the specific benefits of SA-MCGS's search and memory mechanisms.
2. **Cost-performance accounting.** We will report provider-observed input/output tokens, LLM calls, and runtime, stratified by case scale / SCC size. The table will cover oracle-risk/full-SCC Naive, SA-MCGS, and GraphRAG-style Local Evidence Aggregation, and will be reported together with Root@3, Risk-any, Risk-all, and Compression. We will also add a complexity note distinguishing full-SCC prompting, deterministic local-window evidence aggregation, and local rollout-based search.

Finally, we will expand the limitations and societal-impact discussion to state that **SA-MCGS should be used as a decision-support tool**, not as an automated risk adjudication system. Thank you again for these concrete and expert suggestions; they will help make the contribution boundary, evidence, and deployment implications clearer.

---

# Round-2 Follow-up Response Draft

用途：第二轮 author follow-up comment 草稿。**建议作为统一回复发给三位 reviewer**，不要为不同 reviewer 改出三套不一致的说法。核心口径：我们在第一轮承诺补充三类证据，现在用同一套实验口径回应三类共同关切：**graph-aware decomposed baseline、component ablations、cost / reliability accounting**。英文版本更接近 OpenReview 可提交文本；中文版本用于内部核对。

## English Draft

**Comment title:** Follow-up evidence: strengthened graph-aware baseline, component ablations, and completed cost accounting

Thank you again for the careful and constructive reviews. Because the three reviews raise overlapping concerns, we use a single evidence frame in this follow-up response. This avoids giving different reviewers different versions of the claim. In our initial responses, we identified three gaps that needed additional evidence: **(i) component-level ablations**, **(ii) a fairer graph-aware decomposed baseline**, and **(iii) inference cost / reliability accounting**. We have now completed these follow-up analyses and will incorporate them into the revision.

The new results support a more targeted and stronger claim. **SA-MCGS shows substantial gains on gpt-4o and Gemini 2.5 Flash**, especially for strict endpoint completeness / Risk-all. On **Gemini 2.5 Pro**, both LEA and SA-MCGS operate at a high level, confirming that the strengthened graph-aware baseline is strong while SA-MCGS remains competitive. The component ablations show sizeable mechanism effects, and the cost audits show that rollout parallelism can substantially reduce wall-clock runtime while calls/tokens remain the accounting cost. Together, these results position SA-MCGS as an additional inference-time compute option for difficult cyclic SCCs requiring endpoint-complete risk-subgraph recovery.

## Shared Evidence Frame for All Reviewers

| Reviewer concern | New evidence | Consistent takeaway for revision |
|---|---|---|
| Baseline fairness / prompt-decomposition confound | Added a **GraphRAG-style Local Evidence Aggregation (LEA)** baseline. We also report **Gemini 2.5 Flash** as a model-sensitive diagnostic. | LEA is a strong graph-aware baseline. On Gemini 2.5 Pro the current cases are comparable; on gpt-4o and Gemini 2.5 Flash, SA-MCGS substantially improves strict endpoint completeness. |
| Component-level contribution | Added **Stage 1 search/memory ablations** and **Stage 2 dynamic-core ablations**. | The ablation effects are substantial; the strongest support is for **critical-pair ledger/revisit**, **graph-guided local-window selection**, and **dynamic/replacement core construction**. Relation memory and final pair closure should be framed cautiously. |
| Inference cost and reliability | Completed **low-rollout cost audits** on **gpt-4o** and **Gemini 2.5 Flash**, covering Naive / LEA / SA-MCGS with calls, input/output tokens, total tokens, runtime, invalid rate, and performance. | SA-MCGS costs more calls and tokens, but improves strict endpoint completeness. High-concurrency rollout can substantially reduce wall-clock time, while token/call consumption remains the unavoidable accounting cost. This gives an additional inference-time compute option for difficult cases. |
| Scope of the benchmark | We keep the current benchmark framing as a controlled evaluation setting. | The benchmark should be described as a **controlled structural-risk stress test**, not as a direct sample of naturally occurring high-stakes risk distributions. |

## 1. Graph-Aware Decomposed Baseline

To address the concern that the original Full-SCC Naive baseline may confound method quality with prompt decomposition and output-schema difficulty, we implemented a **GraphRAG-style Local Evidence Aggregation (LEA)** baseline.

LEA uses deterministic graph-window retrieval and the same local evidence schema as SA-MCGS, followed by transparent aggregation. It does **not** use relation-first memory, critical-pair revisiting, OC/core signals, rollout selection, or dynamic-core replacement. This makes it a stronger test of whether the gains come merely from local decomposition / graph-window prompting, or from the SCC-aware search and memory mechanisms in SA-MCGS.

| Group | LEA Root@3 | SA Root@3 | Delta | LEA Risk-all | SA Risk-all | Delta | LEA calls | SA calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Matched overall | 83.8% | **86.9%** | +3.1 | 66.2% | **79.4%** | **+13.1** | 15.7 | 55.7 |
| Gemini 2.5 Pro | **88.8%** | 87.5% | -1.2 | **88.8%** | 83.8% | -5.0 | 14.9 | 53.0 |
| gpt-4o | 78.8% | **86.2%** | **+7.5** | 43.8% | **75.0%** | **+31.2** | 16.5 | 58.5 |
| Gemini 2.5 Flash | 82.5% | **92.5%** | **+10.0** | 65.0% | **95.0%** | **+30.0** | 15.6 | 45.9 |
| Large SCCs | **85.0%** | 77.5% | -7.5 | 55.0% | **72.5%** | **+17.5** | 25.6 | 56.5 |
| Medium SCCs | 75.0% | **83.3%** | **+8.3** | 64.6% | **75.0%** | **+10.4** | 14.7 | 57.8 |
| Small SCCs | 88.9% | **94.4%** | **+5.6** | 73.6% | **86.1%** | **+12.5** | 10.8 | 54.0 |

- on **Gemini 2.5 Pro**, LEA and SA-MCGS are comparable in the current cases: LEA is slightly ahead on Risk-all, while Root@3 is nearly tied;
- on **gpt-4o**, SA-MCGS improves Risk-all by **31.2 points**;
- on **Gemini 2.5 Flash**, SA-MCGS improves Risk-all by **30.0 points**;
- overall, on the matched set, SA-MCGS improves Risk-all by **13.1 points**.

The consistent interpretation is that **SA-MCGS shows the clearest gains on gpt-4o and Gemini 2.5 Flash**, while Gemini 2.5 Pro keeps both LEA and SA-MCGS at a high level. LEA validates the reviewers' baseline-fairness concern by serving as a strong graph-aware comparator. The overall pattern suggests that SA-MCGS is most useful when the model benefits from repeated structured evidence accumulation and endpoint-complete subgraph construction.

## 2. Component-Level Ablations

We added component-level ablations to identify which modules are most responsible for the gains.

### Stage 1: Search / Memory Ablations

| Variant | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core |
|---|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | 86.2% | **100.0%** | **75.0%** | 51.3% | 0.0 | 8.1 |
| No relation-first memory | 88.8% | 98.8% | 80.0% | 51.8% | +5.0 | 8.0 |
| No critical-pair ledger/revisit | 83.8% | 88.8% | 53.8% | 72.0% | **-21.3** | 4.2 |
| Random local-window selection | **90.0%** | 96.2% | 63.7% | 51.8% | **-11.3** | 8.0 |

The clearest Stage-1 result is that removing the **critical-pair ledger/revisit** mechanism substantially reduces endpoint completeness: Risk-all drops from **75.0% to 53.8%**. Random local-window selection also lowers Risk-all from **75.0% to 63.7%**, suggesting that graph-guided selection matters beyond simply repeating local prompts.

The relation-first memory ablation is more nuanced: in this sample, removing it does not reduce aggregate Risk-all. We therefore will not overstate relation memory as an independently dominant module. Instead, we will frame it as part of the evidence organization mechanism whose effect can be model- and setting-dependent.

### Stage 2: Dynamic-Core Ablations

| Variant | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core |
|---|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | **85.0%** | **100.0%** | **70.0%** | 52.1% | 0.0 | 10.0 |
| No OC/core signal | **85.0%** | **100.0%** | 60.0% | 52.2% | **-10.0** | 9.7 |
| Monotone core | 77.5% | 87.5% | 45.0% | 76.1% | **-25.0** | 4.8 |
| No pair closure in final core | 80.0% | 95.0% | 67.5% | 53.0% | -2.5 | 9.4 |

The Stage-2 ablation shows that replacing the dynamic/replacement core with monotone accumulation strongly hurts endpoint completeness: Risk-all drops from **70.0% to 45.0%**. Removing OC/core signals reduces Risk-all by **10.0 points**. Final pair closure has a smaller effect in this sample and will be framed cautiously.

## 3. Completed Cost and Reliability Accounting

We agree with the reviewers that practical inference cost must be reported explicitly. We therefore ran completed low-rollout cost audits on **gpt-4o** and **Gemini 2.5 Flash**, measuring calls, input tokens, output tokens, total tokens, wall-clock runtime, invalid-output rate, and performance.

### gpt-4o audit

| Method | Invalid | Calls / case | Total tokens / case | Runtime / case | Root@3 | Risk-any | Risk-all |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full-SCC Naive | 15.0% | 1.0 | 18.2K on valid outputs | 17.7s on valid outputs | 29.4% | 73.5% | 29.4% |
| LEA | **0.0%** | 16.7 | 58.8K | 162.7s | 75.0% | 90.0% | 42.5% |
| SA-MCGS | **0.0%** | 48.9 | 163.6K | 498.1s | **87.5%** | **92.5%** | **77.5%** |

For gpt-4o Naive, some outputs were invalid; the displayed Naive performance is computed on valid outputs in the current summary. Treating invalid outputs as failures would only strengthen the reliability conclusion.

### Gemini 2.5 Flash audit

| Method | Invalid | Calls / case | Total tokens / case | Runtime / case | Root@3 | Risk-any | Risk-all |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full-SCC Naive | **0.0%** | 1.0 | 26.6K | 9.4s | 75.0% | 87.5% | 57.5% |
| LEA | **0.0%** | 15.6 | 53.2K | 54.9s | 82.5% | **100.0%** | 65.0% |
| SA-MCGS | **0.0%** | 45.9 | 148.2K | 164.5s | **92.5%** | **100.0%** | **95.0%** |

These results clarify the cost-performance tradeoff. **SA-MCGS is more expensive** than LEA and Naive in calls and tokens. However, it substantially improves strict endpoint completeness, especially on Risk-all. LEA is a strong lower-cost middle point: it uses roughly one third of the calls of SA-MCGS and is competitive on several metrics, but it does not preserve all endpoints as reliably on gpt-4o and Gemini 2.5 Flash.

Runtime should also be interpreted carefully. These audits use low rollout / low concurrency, so wall-clock time is conservative and not a fixed lower bound. Because many rollout calls are independent or weakly coupled, **large-scale concurrent rollout can substantially improve wall-clock efficiency**. The token and call counts, however, cannot be parallelized away; they remain the real accounting cost. We will therefore present SA-MCGS as a deliberate inference-time-compute option: it spends more tokens/calls to solve difficult cyclic cases more reliably, providing an alternative to relying only on a single long-context or single-pass "deep reasoning" generation.

We will add an explicit parallelizable-time discussion:

```text
T_wall(c_parallel) ~= T_serial + T_LLM / c_parallel
c_parallel = min(C_rollout, C_worker, C_api)
```

Increasing effective rollout concurrency can reduce the parallel LLM-call portion by multiples, subject to worker and API-rate limits. Token count and call count remain the accounting costs and should be reported alongside performance.

## 4. Scope and Societal-Impact Revisions

We also agree that the current benchmark should be framed more carefully. The benchmark is best described as a **controlled structural-risk stress test**, not as a direct sample of naturally occurring high-stakes risk distributions. The expert audit supports semantic recognizability of the injected structural risks, but it does not establish distributional equivalence with naturally occurring legal, regulatory, or software-dependency risks.

In the revision, we will:

- explicitly describe the benchmark as a controlled structural-risk stress test;
- weaken broad claims about direct high-stakes deployment;
- define oracle-risk Naive as a boosted full-SCC baseline selected using ground-truth risk metrics;
- add the LEA baseline and component ablations;
- report calls, tokens, runtime, invalid outputs, and performance together;
- describe SA-MCGS as a **decision-support tool**, not an automated risk adjudicator;
- discuss false positives, false negatives, graph-construction errors, and overtrust risks on naturally occurring cases.

## Revised Overall Claim

The new evidence supports a more focused strength claim:

> SA-MCGS shows substantial Risk-all gains on **gpt-4o by 31.2 points** and **Gemini 2.5 Flash by 30.0 points**, and improves the matched overall aggregate by **13.1 points**. On **Gemini 2.5 Pro**, both LEA and SA-MCGS are in a high-performance regime, showing that the strengthened graph-aware baseline is strong while SA-MCGS remains competitive. These gains come with more calls and tokens, but rollout parallelism can substantially reduce wall-clock runtime. Component ablations show sizeable effects, with critical-pair revisiting and dynamic/replacement core construction receiving the strongest support.

We appreciate the reviewers' suggestions; they led us to add stronger baselines, clearer ablations, and explicit cost accounting. We will incorporate these results and the more careful framing into the revised manuscript.

---

## 中文翻译

**评论标题：** 补充证据：强化后的图感知 baseline、组件级消融与完整成本核算

再次感谢各位审稿人的仔细和建设性意见。由于三位审稿人的关切高度重叠，我们在第二轮回复中使用同一套证据口径，避免给不同 reviewer 不同版本的主张。在第一轮回复中，我们指出有三类证据需要补充：**(i) 组件级消融**、**(ii) 更公平的图感知分解式 baseline**，以及 **(iii) 推理成本 / 可靠性核算**。现在这些补充分析已经完成，我们会把它们纳入修订稿。

新的结果支持一个更聚焦的优势结论：**SA-MCGS 在 gpt-4o 和 Gemini 2.5 Flash 上取得显著提升**，尤其体现在严格 endpoint completeness / Risk-all 上。在 **Gemini 2.5 Pro** 上，LEA 和 SA-MCGS 都表现出较高水平，说明强化后的 graph-aware baseline 本身很强，同时 SA-MCGS 仍保持竞争力。组件消融效果非常可观；成本审计也表明，提高 rollout 并发可以显著优化 wall-clock runtime，calls/tokens 则仍是实际成本核算口径。整体上，SA-MCGS 为需要 endpoint-complete risk-subgraph recovery 的困难 cyclic SCCs 提供了一种额外的 inference-time compute 选择。

## 三位 Reviewer 共用的证据口径

| 审稿人关切 | 新增证据 | 修订稿中的统一结论 |
|---|---|---|
| Baseline fairness / prompt decomposition 混杂 | 加入 **GraphRAG-style Local Evidence Aggregation (LEA)** baseline。另报告 **Gemini 2.5 Flash** 作为模型敏感性诊断。 | LEA 是强 graph-aware baseline。Gemini 2.5 Pro 当前样本中两者表现相当；gpt-4o 和 Gemini 2.5 Flash 上 SA-MCGS 对严格 endpoint completeness 的提升显著。 |
| 组件级贡献 | 加入 **Stage 1 搜索/记忆消融** 和 **Stage 2 dynamic-core 消融**。 | 组件消融效果非常可观；证据最强的是 **critical-pair ledger/revisit**、**graph-guided local-window selection** 和 **dynamic/replacement core construction**。Relation memory 和 final pair closure 需要谨慎表述。 |
| 推理成本和可靠性 | 在 **gpt-4o** 和 **Gemini 2.5 Flash** 上完成 **low-rollout cost audits**，覆盖 Naive / LEA / SA-MCGS，并记录 calls、input/output tokens、total tokens、runtime、invalid rate 和 performance。 | SA-MCGS 的 calls/tokens 成本更高，但严格 endpoint completeness 更好。高并发 rollout 可以显著缩短 wall-clock 时间，但 token/call 消耗是无法并行消除的实际成本。这为困难案例提供了一种额外的 inference-time compute 选择。 |
| Benchmark scope | 当前 benchmark 保持为 controlled evaluation setting。 | Benchmark 应描述为 **controlled structural-risk stress test**，而不是 naturally occurring high-stakes risk distribution 的直接样本。 |

## 1. 图感知分解式 Baseline

为回应审稿人关于 Full-SCC Naive baseline 可能混入 prompt decomposition 和 output-schema difficulty 的担忧，我们实现了一个 **GraphRAG-style Local Evidence Aggregation (LEA)** baseline。

LEA 使用 deterministic graph-window retrieval，并采用与 SA-MCGS 相同的 local evidence schema，然后通过透明 aggregation 汇总结果。它**不使用** relation-first memory、critical-pair revisiting、OC/core signals、rollout selection 或 dynamic-core replacement。因此，它能更直接地检验：增益究竟只是来自 local decomposition / graph-window prompting，还是来自 SA-MCGS 的 SCC-aware search 和 memory mechanisms。

| Group | LEA Root@3 | SA Root@3 | Delta | LEA Risk-all | SA Risk-all | Delta | LEA calls | SA calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Matched overall | 83.8% | **86.9%** | +3.1 | 66.2% | **79.4%** | **+13.1** | 15.7 | 55.7 |
| Gemini 2.5 Pro | **88.8%** | 87.5% | -1.2 | **88.8%** | 83.8% | -5.0 | 14.9 | 53.0 |
| gpt-4o | 78.8% | **86.2%** | **+7.5** | 43.8% | **75.0%** | **+31.2** | 16.5 | 58.5 |
| Gemini 2.5 Flash | 82.5% | **92.5%** | **+10.0** | 65.0% | **95.0%** | **+30.0** | 15.6 | 45.9 |
| Large SCCs | **85.0%** | 77.5% | -7.5 | 55.0% | **72.5%** | **+17.5** | 25.6 | 56.5 |
| Medium SCCs | 75.0% | **83.3%** | **+8.3** | 64.6% | **75.0%** | **+10.4** | 14.7 | 57.8 |
| Small SCCs | 88.9% | **94.4%** | **+5.6** | 73.6% | **86.1%** | **+12.5** | 10.8 | 54.0 |


- 在 **Gemini 2.5 Pro** 当前样本上，LEA 和 SA-MCGS 表现相当：LEA 的 Risk-all 略高，但 Root@3 基本接近；
- 在 **gpt-4o** 上，SA-MCGS 的 Risk-all 提升 **31.2 points**；
- 在**Gemini 2.5 Flash** 上，SA-MCGS 的 Risk-all 提升 **30.0 points**；
- 在 matched set 的总体结果上，SA-MCGS 的 Risk-all 提升 **13.1 points**。

统一解读是：**SA-MCGS 在 gpt-4o 和 Gemini 2.5 Flash 上提升最明显**，而 Gemini 2.5 Pro 上 LEA 和 SA-MCGS 都保持较高水平。LEA 作为强 graph-aware comparator，也回应了审稿人关于 baseline fairness 的关切。整体模式说明，SA-MCGS 的价值主要体现在模型需要反复结构化证据积累、并构造 endpoint-complete subgraph 的场景中。

## 2. 组件级消融

我们补充了组件级消融，用来识别哪些模块最主要地贡献了增益。

### Stage 1：搜索 / 记忆消融

| Variant | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core |
|---|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | 86.2% | **100.0%** | **75.0%** | 51.3% | 0.0 | 8.1 |
| No relation-first memory | 88.8% | 98.8% | 80.0% | 51.8% | +5.0 | 8.0 |
| No critical-pair ledger/revisit | 83.8% | 88.8% | 53.8% | 72.0% | **-21.3** | 4.2 |
| Random local-window selection | **90.0%** | 96.2% | 63.7% | 51.8% | **-11.3** | 8.0 |

Stage 1 最清楚的结果是：移除 **critical-pair ledger/revisit** 会显著降低 endpoint completeness，Risk-all 从 **75.0% 降到 53.8%**。随机 local-window selection 也会把 Risk-all 从 **75.0% 降到 63.7%**，说明 graph-guided selection 的作用不只是“重复 local prompts”。

Relation-first memory 的结果更复杂：在这个样本里，移除它并没有降低 aggregate Risk-all。因此我们不会把它写成单独主导模块，而会把 relation memory 表述为 evidence organization mechanism 的一部分，其效果可能与模型和设置有关。

### Stage 2：Dynamic-Core 消融

| Variant | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core |
|---|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | **85.0%** | **100.0%** | **70.0%** | 52.1% | 0.0 | 10.0 |
| No OC/core signal | **85.0%** | **100.0%** | 60.0% | 52.2% | **-10.0** | 9.7 |
| Monotone core | 77.5% | 87.5% | 45.0% | 76.1% | **-25.0** | 4.8 |
| No pair closure in final core | 80.0% | 95.0% | 67.5% | 53.0% | -2.5 | 9.4 |

Stage 2 消融显示，如果用 monotone accumulation 替代 dynamic/replacement core，endpoint completeness 会显著下降：Risk-all 从 **70.0% 降到 45.0%**。移除 OC/core signals 也会使 Risk-all 下降 **10.0 points**。Final pair closure 在该样本中的影响较小，因此需要谨慎表述。

## 3. 完整成本与可靠性核算

我们同意审稿人关于 practical inference cost 必须显式报告的意见。因此，我们在 **gpt-4o** 和 **Gemini 2.5 Flash** 上完成了 low-rollout cost audits，记录 calls、input tokens、output tokens、total tokens、wall-clock runtime、invalid-output rate 和 performance。

### gpt-4o audit

| Method | Invalid | Calls / case | Total tokens / case | Runtime / case | Root@3 | Risk-any | Risk-all |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full-SCC Naive | 15.0% | 1.0 | valid outputs 上 18.2K | valid outputs 上 17.7s | 29.4% | 73.5% | 29.4% |
| LEA | **0.0%** | 16.7 | 58.8K | 162.7s | 75.0% | 90.0% | 42.5% |
| SA-MCGS | **0.0%** | 48.9 | 163.6K | 498.1s | **87.5%** | **92.5%** | **77.5%** |

对 gpt-4o Naive 来说，部分输出为 invalid；表中 Naive 的 performance 是当前 summary 对 valid outputs 的计算结果。如果把 invalid outputs 直接视为失败，则可靠性方面的结论只会更强。

### Gemini 2.5 Flash audit

| Method | Invalid | Calls / case | Total tokens / case | Runtime / case | Root@3 | Risk-any | Risk-all |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full-SCC Naive | **0.0%** | 1.0 | 26.6K | 9.4s | 75.0% | 87.5% | 57.5% |
| LEA | **0.0%** | 15.6 | 53.2K | 54.9s | 82.5% | **100.0%** | 65.0% |
| SA-MCGS | **0.0%** | 45.9 | 148.2K | 164.5s | **92.5%** | **100.0%** | **95.0%** |

这些结果澄清了 cost-performance tradeoff。**SA-MCGS 的 calls 和 tokens 成本更高**。不过，它显著提升了严格的 endpoint completeness，尤其是 Risk-all。LEA 是一个强 lower-cost middle point：它的调用数大约是 SA-MCGS 的三分之一，并且在若干指标上很有竞争力；但在 gpt-4o 和 Gemini 2.5 Flash 上，它对完整 endpoints 的保留不如 SA-MCGS 稳定。

Runtime 也需要谨慎解释。这些 audit 使用 low rollout / low concurrency，因此 wall-clock time 是偏保守测量，不是固定下界。由于许多 rollout 调用彼此独立或弱耦合，**大规模高并发 rollout 可以显著提升 wall-clock 运行效率**。但是 token 和 call count 不会因为并行而消失，它们仍然是实际成本核算口径。因此我们会把 SA-MCGS 表述为一种 deliberate inference-time-compute 选择：它用更多 token/calls 换取困难循环案例上更可靠的 endpoint-complete 解，提供了不同于单次长上下文或单次“深度思考”生成的另一条路线。

我们会加入明确的并行时间讨论：

```text
T_wall(c_parallel) ~= T_serial + T_LLM / c_parallel
c_parallel = min(C_rollout, C_worker, C_api)
```

增大有效 rollout 并发可以在 worker 和 API-rate 限制内近似按倍数缩短可并行的 LLM-call 部分。Token count 和 call count 仍然是实际成本核算口径，需要和 performance 一起报告。

## 4. Scope 和 Societal Impact 修订

我们也同意当前 benchmark 的定位需要更谨慎。这个 benchmark 最准确的说法是 **controlled structural-risk stress test**，而不是 naturally occurring high-stakes risk distribution 的直接样本。Expert audit 支持 injected structural risks 在语义上可被专业读者识别，但不能证明其与真实法律、监管或软件依赖风险具有相同分布。

在修订稿中，我们会：

- 明确把 benchmark 描述为 controlled structural-risk stress test；
- 弱化直接 high-stakes deployment 的宽泛表述；
- 定义 oracle-risk Naive 为一个由 ground-truth risk metrics 选择的 boosted full-SCC baseline；
- 加入 LEA baseline 和组件级消融；
- 一起报告 calls、tokens、runtime、invalid outputs 和 performance；
- 把 SA-MCGS 描述为 **decision-support tool**，不是 automated risk adjudicator；
- 讨论 false positives、false negatives、graph-construction errors，以及在 naturally occurring cases 上的 overtrust 风险。

## 修订后的总体主张

新增证据支持一个更聚焦的优势主张：

> SA-MCGS 在 **gpt-4o Risk-all 上提升 31.2 points**，并在 **Gemini 2.5 Flash 上提升 30.0 points**，matched overall aggregate 提升 **13.1 points**。在 **Gemini 2.5 Pro** 上，LEA 和 SA-MCGS 都处于较高水平，说明强化后的 graph-aware baseline 本身很强，同时 SA-MCGS 仍保持竞争力。这些提升的代价是更多 calls 和 tokens，但 rollout 并发可以显著优化 wall-clock runtime。组件级消融显示出可观效果，其中 critical-pair revisiting 和 dynamic/replacement core construction 是证据最强的机制。

我们感谢审稿人的建议；这些建议促使我们加入更强 baseline、更清楚的消融和显式成本核算。我们会把这些结果和更谨慎的 framing 纳入修订稿。

---

---

# Round-2 Per-Reviewer Sendable Comments

用途：下面三条均为可直接发送的独立英文回复；每条英文正文都已经把三张表格计入字符数并控制在 5000 characters 以内。每条英文回复后都附上对应中文翻译，便于核对和进一步修改。

## To Reviewer iMEC

**Comment title:** Follow-up evidence on strengthened baseline, ablations, cost accounting, and model-level behavior

Thank you again for the careful and concrete review. In our first response, we said that the follow-up would focus on **(1) component-level ablations**, **(2) practical cost/complexity accounting**, and **(3) a fairer graph-aware decomposed baseline**. We have now completed these analyses. The strongest new signal is that SA-MCGS gives large Risk-all gains on **gpt-4o** and **Gemini 2.5 Flash**, supporting its value for cyclic SCCs that require repeated structure-aware evidence accumulation to recover endpoint-complete risk subgraphs. On **Gemini 2.5 Pro**, both LEA and SA-MCGS reach a high-performance regime, showing that the strengthened baseline is strong while SA-MCGS remains competitive. The component ablations also show substantial mechanism effects. The cost audit further shows a useful cost-performance route: SA-MCGS spends more calls/tokens, but wall-clock time can be substantially reduced by increasing rollout parallelism/concurrency, giving practitioners an additional inference-time compute option for hard cyclic cases.

Concretely, LEA is a strong graph-aware comparator rather than merely another full-SCC prompt variant. It decomposes each SCC into deterministic graph windows, applies the same local evidence schema as SA-MCGS, and aggregates root/endpoint evidence with fixed rules. The removed parts are exactly the SA-MCGS mechanisms under test: relation memory, critical-pair revisiting, OC/core signals, rollout selection, and dynamic/replacement core construction.

**Evidence tables included in this comment.** All performance entries are percentages.

**T1. Strengthened baseline: LEA vs. SA-MCGS**

|Slice|LEA R@3/All|SA R@3/All|Delta All|
|---|---:|---:|---:|
|Matched|83.8/66.2|86.9/**79.4**|**+13.1**|
|Gemini 2.5 Pro|88.8/**88.8**|87.5/83.8|-5.0|
|gpt-4o|78.8/43.8|86.2/**75.0**|**+31.2**|
|Gemini 2.5 Flash|82.5/65.0|92.5/**95.0**|**+30.0**|

**T2. Component ablations: Risk-all**

|Ablation|Full|Ablated|Delta|
|---|---:|---:|---:|
|No critical-pair revisit|75.0|53.8|**-21.3**|
|Random local window|75.0|63.7|**-11.3**|
|No relation memory|75.0|80.0|+5.0|
|No OC/core signal|70.0|60.0|**-10.0**|
|Monotone core|70.0|45.0|**-25.0**|
|No final pair closure|70.0|67.5|-2.5|

The ablations give mechanism-level evidence, not only aggregate deltas. Removing **critical-pair revisiting** costs 21.3 Risk-all points, showing that unresolved endpoint pairs must be revisited rather than treated as one-shot local judgments. Random local windows cost 11.3 points, supporting graph-guided selection. In Stage 2, **monotone core** loses 25.0 points and removing **OC/core signals** loses 10.0 points, showing that dynamic replacement and core signals are central to endpoint retention.

**T3. Completed cost audits**

|Run|Invalid|Calls|Tokens|Time|Risk-all|
|---|---:|---:|---:|---:|---:|
|gpt-4o Naive|15.0%|1.0|18.2K|17.7s|29.4|
|gpt-4o LEA|0|16.7|58.8K|162.7s|42.5|
|gpt-4o SA|0|48.9|163.6K|498.1s|**77.5**|
|Flash Naive|0|1.0|26.6K|9.4s|57.5|
|Flash LEA|0|15.6|53.2K|54.9s|65.0|
|Flash SA|0|45.9|148.2K|164.5s|**95.0**|

We will add the cost/time relation explicitly:

`T_wall(p) ~= T_serial + sum_g ceil(n_g / p_g) * t_g`, where `n_g` is the number of rollout calls in group `g`, `p_g` is effective parallelism, and `t_g` is per-call latency. Increasing `p_g` reduces wall-clock time, while total calls and tokens remain `sum_g n_g` and `sum(tokens)`.

The component ablations show substantial effect sizes: the best-supported mechanisms are **critical-pair revisiting**, **graph-guided local-window selection**, and **dynamic/replacement core construction**. We will be more cautious about relation memory and final pair closure, whose current ablations are mixed or small. The cost audits also clarify that SA-MCGS is an inference-time-compute option: higher rollout concurrency can substantially reduce wall-clock runtime, while calls/tokens remain the accounting cost. This gives practitioners another way to spend compute for difficult cyclic cases, beyond relying only on a single long-context or single deep-reasoning generation. We will also fix 'Appendix 9' to 'Appendix J' and define oracle-risk Naive as a boosted full-SCC baseline selected using ground-truth risk metrics.

### 中文翻译

**评论标题：** 关于强化 baseline、消融、成本核算和模型层面表现的补充证据

再次感谢您细致而具体的审阅。在第一轮回复中，我们说明后续证据会集中在 **(1) 组件级消融**、**(2) 实际成本/复杂度核算** 和 **(3) 更公平的 graph-aware decomposed baseline** 三处；现在这些分析已经完成。最强的新信号是：SA-MCGS 在 **gpt-4o** 和 **Gemini 2.5 Flash** 上带来显著 Risk-all 提升，支持其在 cyclic SCCs 需要反复结构感知证据积累、以恢复 endpoint-complete risk subgraphs 的场景中的价值。在 **Gemini 2.5 Pro** 上，LEA 和 SA-MCGS 都达到较高水平，说明强化后的 baseline 本身很强，同时 SA-MCGS 仍保持竞争力。组件消融也显示出非常可观的机制效应。成本审计进一步说明了一条有用的 cost-performance 路线：SA-MCGS 会使用更多 calls/tokens，但可以通过提高 rollout 并行度/并发度显著优化 wall-clock 时间，为困难 cyclic cases 提供一种额外的 inference-time compute 选择。

具体来说，LEA 是一个强 graph-aware comparator，而不只是另一个 full-SCC prompt variant。它把每个 SCC 分解成 deterministic graph windows，使用与 SA-MCGS 相同的 local evidence schema，并用固定规则聚合 root/endpoint evidence。被移除的正是 SA-MCGS 中待检验的机制：relation memory、critical-pair revisiting、OC/core signals、rollout selection 和 dynamic/replacement core construction。

**本评论包含的证据表。** 所有性能数值均为百分比。

**表 1. 强化后的 baseline：LEA vs. SA-MCGS**

|口径|LEA R@3/All|SA R@3/All|All 差值|
|---|---:|---:|---:|
|Matched 总体|83.8/66.2|86.9/**79.4**|**+13.1**|
|Gemini 2.5 Pro|88.8/**88.8**|87.5/83.8|-5.0|
|gpt-4o|78.8/43.8|86.2/**75.0**|**+31.2**|
|Gemini 2.5 Flash|82.5/65.0|92.5/**95.0**|**+30.0**|

**表 2. 组件级消融：Risk-all**

|消融项|完整方法|消融后|差值|
|---|---:|---:|---:|
|去掉 critical-pair revisit|75.0|53.8|**-21.3**|
|随机 local window|75.0|63.7|**-11.3**|
|去掉 relation memory|75.0|80.0|+5.0|
|去掉 OC/core signal|70.0|60.0|**-10.0**|
|Monotone core|70.0|45.0|**-25.0**|
|去掉 final pair closure|70.0|67.5|-2.5|

消融实验给出的不是单纯 aggregate delta，而是组件级机制证据。去掉 **critical-pair revisiting** 会损失 21.3 个 Risk-all points，说明未解决的 endpoint pairs 需要被反复 revisited，而不能只作为一次性 local judgment。随机 local windows 损失 11.3 points，支持 graph-guided selection 的作用。Stage 2 中，**monotone core** 损失 25.0 points，去掉 **OC/core signals** 损失 10.0 points，说明 dynamic replacement 和 core signals 对 endpoint retention 很关键。

**表 3. 已完成的成本审计**

|实验/方法|Invalid|调用数|Tokens|时间|Risk-all|
|---|---:|---:|---:|---:|---:|
|gpt-4o Naive|15.0%|1.0|18.2K|17.7s|29.4|
|gpt-4o LEA|0|16.7|58.8K|162.7s|42.5|
|gpt-4o SA|0|48.9|163.6K|498.1s|**77.5**|
|Flash Naive|0|1.0|26.6K|9.4s|57.5|
|Flash LEA|0|15.6|53.2K|54.9s|65.0|
|Flash SA|0|45.9|148.2K|164.5s|**95.0**|

我们会显式加入成本/时间关系式：

`T_wall(p) ~= T_serial + sum_g ceil(n_g / p_g) * t_g`，其中 `n_g` 是第 `g` 组 rollout 调用数，`p_g` 是有效并行度，`t_g` 是单次调用延迟。提高 `p_g` 可以缩短 wall-clock time，但总调用数和 token 总量仍是 `sum_g n_g` 和 `sum(tokens)`。

组件消融的效果非常可观：证据最强的是 **critical-pair revisiting**、**graph-guided local-window selection** 和 **dynamic/replacement core construction**。relation memory 与 final pair closure 当前消融结果混合或影响较小，我们会更谨慎表述。成本审计也说明，SA-MCGS 可以作为一种 inference-time-compute 选择：提高 rollout 并发可以显著优化 wall-clock runtime，calls/tokens 则仍是实际成本核算口径。这为困难 cyclic cases 提供了单次长上下文或单次 deep-reasoning generation 之外的额外选择。我们也会把 “Appendix 9” 修正为 “Appendix J”，并明确 oracle-risk Naive 是由 ground-truth risk metrics 选择的 boosted full-SCC baseline。

## To Reviewer rxvy

**Comment title:** Follow-up evidence on strengthened baseline fairness, benchmark scope, and responsible interpretation

Thank you again for the thoughtful review. We especially appreciated that your comments separated baseline fairness, model-level behavior, injected-risk scope, component attribution, and deployment risk. Following our first response, we now provide the promised evidence in the same structure: **(1) a stronger graph-aware decomposed comparator**, **(2) component-level ablations**, **(3) cost/reliability accounting with an explicit parallel-time formula**, and **(4) a narrower benchmark/deployment framing**. The resulting interpretation is more specific: **SA-MCGS gives substantial Risk-all gains on gpt-4o and Gemini 2.5 Flash, while Gemini 2.5 Pro puts both LEA and SA-MCGS in a high-performance regime**. This supports SA-MCGS most clearly when cyclic SCCs require repeated structure-aware evidence accumulation for endpoint-complete subgraphs. The component ablations show sizeable effects, making the mechanism story much more concrete. The cost audit also shows that increasing rollout parallelism/concurrency can substantially reduce SA-MCGS wall-clock time, while calls/tokens remain the accounting cost; this gives an additional inference-time compute choice for hard cases.

LEA directly addresses the baseline-fairness issue: it keeps deterministic graph-window retrieval and the same local evidence schema, then uses fixed aggregation, while excluding relation memory, critical-pair revisiting, OC/core signals, rollout selection, and dynamic/replacement core construction. Thus the comparison separates graph-aware decomposition from the additional SCC-aware search and memory mechanisms.

**Evidence tables included in this comment.** All performance entries are percentages.

**T1. Strengthened baseline: LEA vs. SA-MCGS**

|Slice|LEA R@3/All|SA R@3/All|Delta All|
|---|---:|---:|---:|
|Matched|83.8/66.2|86.9/**79.4**|**+13.1**|
|Gemini 2.5 Pro|88.8/**88.8**|87.5/83.8|-5.0|
|gpt-4o|78.8/43.8|86.2/**75.0**|**+31.2**|
|Gemini 2.5 Flash|82.5/65.0|92.5/**95.0**|**+30.0**|

**T2. Component ablations: Risk-all**

|Ablation|Full|Ablated|Delta|
|---|---:|---:|---:|
|No critical-pair revisit|75.0|53.8|**-21.3**|
|Random local window|75.0|63.7|**-11.3**|
|No relation memory|75.0|80.0|+5.0|
|No OC/core signal|70.0|60.0|**-10.0**|
|Monotone core|70.0|45.0|**-25.0**|
|No final pair closure|70.0|67.5|-2.5|

The ablations also sharpen component attribution. The largest drops are **monotone core** (-25.0) and **no critical-pair revisit** (-21.3), which supports the claim that endpoint-complete recovery requires both dynamic core replacement and repeated attention to unresolved critical pairs. The random-window drop (-11.3) supports graph-guided local-window selection, while the OC/core-signal drop (-10.0) shows that core construction benefits from explicit structural signals.

**T3. Completed cost audits**

|Run|Invalid|Calls|Tokens|Time|Risk-all|
|---|---:|---:|---:|---:|---:|
|gpt-4o Naive|15.0%|1.0|18.2K|17.7s|29.4|
|gpt-4o LEA|0|16.7|58.8K|162.7s|42.5|
|gpt-4o SA|0|48.9|163.6K|498.1s|**77.5**|
|Flash Naive|0|1.0|26.6K|9.4s|57.5|
|Flash LEA|0|15.6|53.2K|54.9s|65.0|
|Flash SA|0|45.9|148.2K|164.5s|**95.0**|

We will add the cost/time relation explicitly:

`T_wall(p) ~= T_serial + sum_g ceil(n_g / p_g) * t_g`, where `n_g` is the number of rollout calls in group `g`, `p_g` is effective parallelism, and `t_g` is per-call latency. Increasing `p_g` reduces wall-clock time, while total calls and tokens remain `sum_g n_g` and `sum(tokens)`.

The same evidence also narrows the benchmark claim. We will describe the benchmark as a **controlled structural-risk stress test**, not as a direct sample of naturally occurring high-stakes risk distributions. The expert audit supports recognizability and semantic plausibility of the injected risks, but not distributional equivalence. Deployment-wise, we will frame SA-MCGS as **decision support**, not automated risk adjudication. The cost audit provides an important additional choice: SA-MCGS spends more calls/tokens for higher strict endpoint completeness, but rollout parallelism can substantially reduce wall-clock runtime. The component ablations are also large enough to make the mechanism story more concrete, especially for critical-pair revisiting and dynamic/replacement core construction.

### 中文翻译

**评论标题：** 关于强化 baseline fairness、benchmark scope 和 responsible interpretation 的补充证据

再次感谢您深入的审阅。您的意见帮助我们区分 baseline fairness、model-level behavior、injected-risk scope、组件归因和部署风险。承接第一轮回复，我们现在按同一结构补充承诺过的证据：**(1) 更强的 graph-aware decomposed comparator**、**(2) 组件级消融**、**(3) 带并行时间公式的成本/可靠性核算**，以及 **(4) 更收窄的 benchmark/deployment framing**。新的解释更加聚焦：**SA-MCGS 在 gpt-4o 和 Gemini 2.5 Flash 上带来显著 Risk-all 提升；Gemini 2.5 Pro 上 LEA 和 SA-MCGS 都表现出较高水平**。这说明 SA-MCGS 的优势最清楚地体现在 cyclic SCCs 需要反复结构感知证据积累、以保留 endpoint-complete subgraphs 的场景中。组件消融显示出非常可观的效果，使机制解释更具体。成本审计也表明，提高 rollout 并行度/并发度可以显著优化 SA-MCGS 的 wall-clock 时间，而 calls/tokens 仍是实际成本核算口径；这为困难案例提供了一种额外的 inference-time compute 选择。

LEA 直接回应 baseline fairness 问题：它保留 deterministic graph-window retrieval 和相同的 local evidence schema，然后使用固定聚合规则；同时排除 relation memory、critical-pair revisiting、OC/core signals、rollout selection 和 dynamic/replacement core construction。因此，这个比较可以区分 graph-aware decomposition 的收益和额外 SCC-aware search/memory 机制的收益。

**本评论包含的证据表。** 所有性能数值均为百分比。

**表 1. 强化后的 baseline：LEA vs. SA-MCGS**

|口径|LEA R@3/All|SA R@3/All|All 差值|
|---|---:|---:|---:|
|Matched 总体|83.8/66.2|86.9/**79.4**|**+13.1**|
|Gemini 2.5 Pro|88.8/**88.8**|87.5/83.8|-5.0|
|gpt-4o|78.8/43.8|86.2/**75.0**|**+31.2**|
|Gemini 2.5 Flash|82.5/65.0|92.5/**95.0**|**+30.0**|

**表 2. 组件级消融：Risk-all**

|消融项|完整方法|消融后|差值|
|---|---:|---:|---:|
|去掉 critical-pair revisit|75.0|53.8|**-21.3**|
|随机 local window|75.0|63.7|**-11.3**|
|去掉 relation memory|75.0|80.0|+5.0|
|去掉 OC/core signal|70.0|60.0|**-10.0**|
|Monotone core|70.0|45.0|**-25.0**|
|去掉 final pair closure|70.0|67.5|-2.5|

消融也让组件归因更清楚。下降最大的是 **monotone core**（-25.0）和 **no critical-pair revisit**（-21.3），支持 endpoint-complete recovery 同时需要 dynamic core replacement 和对 unresolved critical pairs 的反复关注。Random-window 下降 11.3 points，支持 graph-guided local-window selection；OC/core-signal 下降 10.0 points，说明 core construction 受益于显式结构信号。

**表 3. 已完成的成本审计**

|实验/方法|Invalid|调用数|Tokens|时间|Risk-all|
|---|---:|---:|---:|---:|---:|
|gpt-4o Naive|15.0%|1.0|18.2K|17.7s|29.4|
|gpt-4o LEA|0|16.7|58.8K|162.7s|42.5|
|gpt-4o SA|0|48.9|163.6K|498.1s|**77.5**|
|Flash Naive|0|1.0|26.6K|9.4s|57.5|
|Flash LEA|0|15.6|53.2K|54.9s|65.0|
|Flash SA|0|45.9|148.2K|164.5s|**95.0**|

我们会显式加入成本/时间关系式：

`T_wall(p) ~= T_serial + sum_g ceil(n_g / p_g) * t_g`，其中 `n_g` 是第 `g` 组 rollout 调用数，`p_g` 是有效并行度，`t_g` 是单次调用延迟。提高 `p_g` 可以缩短 wall-clock time，但总调用数和 token 总量仍是 `sum_g n_g` 和 `sum(tokens)`。

同一组证据也会收窄 benchmark 的主张。我们会把 benchmark 描述为 **controlled structural-risk stress test**，而不是真实高风险分布的直接样本；expert audit 支持 injected risks 的可识别性和语义合理性，但不证明分布等价。部署上，SA-MCGS 会被定位为 **decision support**，不是 automated risk adjudication。成本审计提供了一个重要的额外选择：SA-MCGS 用更多 calls/tokens 换取更高的严格 endpoint completeness，但提高 rollout 并发可以显著优化 wall-clock runtime。组件消融的幅度也非常可观，使机制解释更具体，尤其是 critical-pair revisiting 和 dynamic/replacement core construction。

## To Reviewer wWUk

**Comment title:** Follow-up evidence on strengthened graph-aware baseline and cost-performance tradeoffs

Thank you again for the constructive review and for recognizing the motivation, cyclic-graph failure mode, framework integration, and reproducibility effort. Your first-round suggestions focused on representative graph-aware baselines and cost-performance analysis, so our follow-up is organized around those promised additions: **GraphRAG-style LEA**, component ablations, and cost accounting with an explicit parallel-time formula. LEA uses deterministic graph-window retrieval and the same local evidence schema as SA-MCGS, but without relation memory, critical-pair revisiting, OC/core signals, rollout selection, or dynamic-core replacement. The resulting pattern is clear: SA-MCGS gives large Risk-all gains on **gpt-4o** and **Gemini 2.5 Flash**, while **Gemini 2.5 Pro** keeps both LEA and SA-MCGS at a high level. The component ablations show substantial effects, and the cost audit shows that SA-MCGS wall-clock time can be improved by increasing rollout parallelism/concurrency, giving practitioners an additional inference-time compute choice.

Operationally, LEA retrieves deterministic local graph windows, asks the model to fill the same local evidence schema used by SA-MCGS, and aggregates root/endpoint evidence with fixed rules. It therefore represents a strengthened graph-aware baseline rather than another full-SCC prompting variant, while leaving out the search, memory, and dynamic-core components that distinguish SA-MCGS.

**Evidence tables included in this comment.** All performance entries are percentages.

**T1. Strengthened baseline: LEA vs. SA-MCGS**

|Slice|LEA R@3/All|SA R@3/All|Delta All|
|---|---:|---:|---:|
|Matched|83.8/66.2|86.9/**79.4**|**+13.1**|
|Gemini 2.5 Pro|88.8/**88.8**|87.5/83.8|-5.0|
|gpt-4o|78.8/43.8|86.2/**75.0**|**+31.2**|
|Gemini 2.5 Flash|82.5/65.0|92.5/**95.0**|**+30.0**|

**T2. Component ablations: Risk-all**

|Ablation|Full|Ablated|Delta|
|---|---:|---:|---:|
|No critical-pair revisit|75.0|53.8|**-21.3**|
|Random local window|75.0|63.7|**-11.3**|
|No relation memory|75.0|80.0|+5.0|
|No OC/core signal|70.0|60.0|**-10.0**|
|Monotone core|70.0|45.0|**-25.0**|
|No final pair closure|70.0|67.5|-2.5|

The ablation table further shows why the method is not just a larger prompt decomposition. **Critical-pair revisiting** and **dynamic/replacement core construction** have the largest measured effects (-21.3 and -25.0 Risk-all points when removed/flattened). Graph-guided window selection and OC/core signals also matter (-11.3 and -10.0). This supports a mechanism story centered on repeated pair resolution and adaptive core construction.

**T3. Completed cost audits**

|Run|Invalid|Calls|Tokens|Time|Risk-all|
|---|---:|---:|---:|---:|---:|
|gpt-4o Naive|15.0%|1.0|18.2K|17.7s|29.4|
|gpt-4o LEA|0|16.7|58.8K|162.7s|42.5|
|gpt-4o SA|0|48.9|163.6K|498.1s|**77.5**|
|Flash Naive|0|1.0|26.6K|9.4s|57.5|
|Flash LEA|0|15.6|53.2K|54.9s|65.0|
|Flash SA|0|45.9|148.2K|164.5s|**95.0**|

We will add the cost/time relation explicitly:

`T_wall(p) ~= T_serial + sum_g ceil(n_g / p_g) * t_g`, where `n_g` is the number of rollout calls in group `g`, `p_g` is effective parallelism, and `t_g` is per-call latency. Increasing `p_g` reduces wall-clock time, while total calls and tokens remain `sum_g n_g` and `sum(tokens)`.

The result identifies a strong target setting. SA-MCGS gives large Risk-all gains on gpt-4o and Gemini 2.5 Flash, while **Gemini 2.5 Pro keeps both LEA and SA-MCGS at a high level**. We will present SA-MCGS as a **cost-performance tradeoff**, not a free improvement: it uses more inference-time compute to solve difficult cyclic cases more reliably. At the same time, the cost audit shows that increasing rollout concurrency can substantially reduce wall-clock runtime, giving practitioners an additional inference-time compute choice. The ablation effects are also substantial and support critical-pair revisiting, graph-guided local windows, and dynamic/replacement core construction, while weaker components will be described cautiously.

### 中文翻译

**评论标题：** 关于强化后的 graph-aware baseline 和 cost-performance tradeoff 的补充证据

再次感谢您建设性的审阅，也感谢您认可本文的问题动机、cyclic-graph failure mode、框架整合和 reproducibility 工作。您第一轮建议重点集中在 representative graph-aware baselines 和 cost-performance analysis，因此我们这次 follow-up 也围绕这些承诺补充：**GraphRAG-style LEA**、组件消融，以及带并行时间公式的成本核算。LEA 使用 deterministic graph-window retrieval 和与 SA-MCGS 相同的 local evidence schema，但不使用 relation memory、critical-pair revisiting、OC/core signals、rollout selection 或 dynamic-core replacement。结果模式很清楚：SA-MCGS 在 **gpt-4o** 和 **Gemini 2.5 Flash** 上带来显著 Risk-all 提升；在 **Gemini 2.5 Pro** 上，LEA 和 SA-MCGS 都保持较高水平。组件消融显示出非常可观的效果；成本审计也表明，可以通过提高 rollout 并行度/并发度优化 SA-MCGS 的 wall-clock 时间，为实践者提供一种额外的 inference-time compute 选择。

操作上，LEA 会检索 deterministic local graph windows，让模型填写与 SA-MCGS 相同的 local evidence schema，并用固定规则聚合 root/endpoint evidence。因此它是一个强化后的 graph-aware baseline，而不是另一个 full-SCC prompting variant；同时它不包含 SA-MCGS 中用于区分方法贡献的 search、memory 和 dynamic-core components。

**本评论包含的证据表。** 所有性能数值均为百分比。

**表 1. 强化后的 baseline：LEA vs. SA-MCGS**

|口径|LEA R@3/All|SA R@3/All|All 差值|
|---|---:|---:|---:|
|Matched 总体|83.8/66.2|86.9/**79.4**|**+13.1**|
|Gemini 2.5 Pro|88.8/**88.8**|87.5/83.8|-5.0|
|gpt-4o|78.8/43.8|86.2/**75.0**|**+31.2**|
|Gemini 2.5 Flash|82.5/65.0|92.5/**95.0**|**+30.0**|

**表 2. 组件级消融：Risk-all**

|消融项|完整方法|消融后|差值|
|---|---:|---:|---:|
|去掉 critical-pair revisit|75.0|53.8|**-21.3**|
|随机 local window|75.0|63.7|**-11.3**|
|去掉 relation memory|75.0|80.0|+5.0|
|去掉 OC/core signal|70.0|60.0|**-10.0**|
|Monotone core|70.0|45.0|**-25.0**|
|去掉 final pair closure|70.0|67.5|-2.5|

消融表进一步说明，该方法并不只是更大的 prompt decomposition。**Critical-pair revisiting** 和 **dynamic/replacement core construction** 的测得作用最大，移除或压平成 monotone core 时分别损失 21.3 和 25.0 个 Risk-all points。Graph-guided window selection 与 OC/core signals 也有明显作用，分别损失 11.3 和 10.0 points。这支持以 repeated pair resolution 和 adaptive core construction 为中心的机制解释。

**表 3. 已完成的成本审计**

|实验/方法|Invalid|调用数|Tokens|时间|Risk-all|
|---|---:|---:|---:|---:|---:|
|gpt-4o Naive|15.0%|1.0|18.2K|17.7s|29.4|
|gpt-4o LEA|0|16.7|58.8K|162.7s|42.5|
|gpt-4o SA|0|48.9|163.6K|498.1s|**77.5**|
|Flash Naive|0|1.0|26.6K|9.4s|57.5|
|Flash LEA|0|15.6|53.2K|54.9s|65.0|
|Flash SA|0|45.9|148.2K|164.5s|**95.0**|

我们会显式加入成本/时间关系式：

`T_wall(p) ~= T_serial + sum_g ceil(n_g / p_g) * t_g`，其中 `n_g` 是第 `g` 组 rollout 调用数，`p_g` 是有效并行度，`t_g` 是单次调用延迟。提高 `p_g` 可以缩短 wall-clock time，但总调用数和 token 总量仍是 `sum_g n_g` 和 `sum(tokens)`。

结果给出了清晰的优势场景：SA-MCGS 在 gpt-4o 和 Gemini 2.5 Flash 上 Risk-all 提升显著；**Gemini 2.5 Pro 上 LEA 和 SA-MCGS 都保持较高水平**。我们会把 SA-MCGS 表述为 **cost-performance tradeoff**，而不是“免费提升”：它使用更多 inference-time compute 来更可靠地解决困难 cyclic cases。同时，成本审计表明，提高 rollout 并发可以显著优化 wall-clock runtime，为实践者提供一种额外的 inference-time compute 选择。组件消融的效果也非常可观，进一步支持 critical-pair revisiting、graph-guided local windows 和 dynamic/replacement core construction；证据较弱的组件会谨慎表述。

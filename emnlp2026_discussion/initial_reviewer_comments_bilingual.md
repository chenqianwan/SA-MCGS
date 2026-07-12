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

We will also revise the model-level discussion: Gemini 2.5 Pro and DeepSeek-V3 are already strong under oracle-risk Naive, so we will not frame SA-MCGS as uniformly superior across models. Instead, we will emphasize **robustness, output reliability, and endpoint retention under cyclic long-context pressure**. For ablations, we are preparing a component-level table covering relation-first memory, critical-pair ledger/revisiting, OC/core signals, local-window selection, and dynamic/replacement core construction.

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

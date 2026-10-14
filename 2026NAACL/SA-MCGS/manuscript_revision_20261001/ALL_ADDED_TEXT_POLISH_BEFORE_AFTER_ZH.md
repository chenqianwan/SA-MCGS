# 本次新增文字润色：完整逐项对照清单

2026-10-01。对照上一轮全面润色开始前的备份与当前稿，共 **90 处改动单元**。相邻的改写句合并为一项，因此不是 90 个单句。按论文阅读顺序排列，正文和附录均包含；这次只整理清单，没有继续改论文。

每项给出 **原文 → 改后 → 理由**，并链接到当前源码位置。两侧完全相同的段首、段尾句不重复抄录；夹在改写句之间的未改句保留作上下文。领域表只列发生修改的单元格。单纯修订颜色／LaTeX 包装变化不计入。

英文按排版后的文字展示，展开 SA-MCGS、Root@3 等宏，图表与章节交叉引用统一使用当前净稿编号，保留数学内容。理由会区分消除歧义、逻辑组织与可选换词；少数改变语气或解释重心的地方也如实注明。

原文基准：`tmp/pdfs/all_additions_polish_20261001/before/`；当前稿：`paper/latex/`。这与更早 ARR 初稿的累计差异不同。

## 索引

| 范围 | 条目 | 数量 |
|---|---:|---:|
| 摘要与引言 | 001–005 | 5 |
| 任务定义与方法 | 006–010 | 5 |
| 实验设置与基线 | 011–014 | 4 |
| 主结果与配对、领域分析 | 015–021 | 7 |
| 分析与正文专家评估 | 022–031 | 10 |
| 结论与局限 | 032–033 | 2 |
| 附录 A、B：诊断与专家审计 | 034–049 | 16 |
| 附录 C、G、H、I：案例、提示与领域接口 | 050–059 | 10 |
| 附录 J：规模与预算分析 | 060–066 | 7 |
| 附录 K：基线、消融、成本与统计协议 | 067–090 | 24 |

## 摘要与引言

### 001｜摘要：双基线收益与补充验证

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:58)。

**原文**

> Across five LLMs and 400 model-cases, SA-MCGS improves mean Root@3 and Risk-all by 6.75 and 15.25 percentage points over local evidence aggregation (LEA), and by 46.00 and 38.75 points over one-shot prompting. The returned subgraphs remove 55.70% of SCC nodes on average. Component ablations, measured inference costs, and a blinded expert audit further support its use for extracting compact, inspectable evidence from cyclic document graphs.

**改后**

> Across five LLMs and 400 model-cases, SA-MCGS raises mean Root@3 and Risk-all over local evidence aggregation (LEA) by 6.75 and 15.25 percentage points, respectively. The corresponding gains over one-shot prompting are 46.00 and 38.75 points. Returned subgraphs remove 55.70% of SCC nodes on average. Component ablations isolate the effect of core replacement, while cost measurements and a blinded expert audit assess computational efficiency and the quality of the extracted evidence.

**理由**：将 LEA 和 One-shot 的两组提升拆成两句，并加 respectively，使两项指标与两组数字的对应关系更清楚。将笼统的 further support its use 改成消融、成本和专家审计各自回答的问题，避免用一个泛泛的支持性结论概括不同证据；其余摘要背景未改。

### 002｜引言：循环依赖与完整证据保留

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:66)。

**原文**

> In strongly connected components (SCCs), following dependency paths can lead back to a previously visited record. One-shot prompting must rank risk sources and assemble their supporting evidence from the entire component in one generation. This makes complete evidence retention a distinct objective from locating a suspicious record.

**改后**

> Following dependencies within strongly connected components (SCCs) can revisit the same records. One-shot prompting must jointly rank risk sources and assemble supporting evidence from the entire component in one generation. Complete evidence retention is therefore a distinct objective from locating a suspicious record.

**理由**：把 can lead back to a previously visited record 简化为 revisit the same records，直接描述循环访问；加入 jointly，突出一次生成同时承担排序与证据组织。末句把 complete evidence retention 放在主语位置，用 therefore 明确接上前面的任务要求。

### 003｜引言：方法概述

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:84)。

**原文**

> We propose SA-MCGS, a structure-aware Monte Carlo graph search method that conducts local LLM rollouts within each SCC. A record's priority reflects how its constraints, exceptions, or handoffs interact with evidence already observed. Relation-first memory preserves this context across rollouts and guides further inspection of implicated records and relations. A dynamic core allows earlier selections to be replaced as evidence accumulates, yielding a compact risk subgraph for inspection (Figure 1).

**改后**

> We propose SA-MCGS, a structure-aware Monte Carlo graph search method that performs local LLM rollouts within each SCC. A record's priority depends on how its constraints, exceptions, or handoffs interact with accumulated evidence. Relation-first memory preserves this context across rollouts and guides exploration of implicated records and relations. Dynamic core replacement revises earlier selections as evidence accumulates, producing a compact risk subgraph for inspection (Figure 1).

**理由**：将 evidence already observed 统一为 accumulated evidence，并以 depends on 表明优先级与已观察证据的联系。把 A dynamic core allows…to be replaced 改成 Dynamic core replacement revises…，直接说明执行的操作；conducts→performs、inspection→exploration 是搭配与术语选择，并非原文语法错误。

### 004｜引言：第一项贡献

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:88)。

**原文**

> A formulation of structural risk subgraph extraction that requires compact subgraphs to retain repair-relevant evidence from cyclic document regions.

**改后**

> A formulation of structural risk subgraph extraction: retaining repair-relevant evidence in compact subgraphs of cyclic document regions.

**理由**：用冒号直接解释 structural risk subgraph extraction，替换较绕的 that requires…to retain 结构；保留名词短语起句，与贡献列表的形式一致。

### 005｜引言：第三项贡献

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:90)。

**原文**

> A frozen four-domain benchmark for comparing SA-MCGS with one-shot prompting and LEA across five LLMs, complemented by component ablations, measured inference costs, and expert auditing.

**改后**

> A fixed four-domain benchmark comparing SA-MCGS with one-shot prompting and LEA across five LLMs, with component ablations, inference-cost measurements, and expert evaluation.

**理由**：用 fixed 代替偏实验管理语气的 frozen，压缩 for comparing 和 complemented by。将 measured inference costs 改为 inference-cost measurements，使其与 component ablations、expert evaluation 构成并列的验证项目；fixed/frozen 和 evaluation/auditing 属于风格选择。


## 任务定义与方法

### 006｜任务定义：source、variant 与 model-case

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:118)。

**原文**

> We call an unmodified component a source SCC. Each controlled edit produces an injected variant, and each evaluation of a variant by a model counts as one model-case. Variants from the same source are not independent samples. We assess coverage of expert evidence and repair materials separately from the benchmark endpoint metrics.

**改后**

> An unmodified component is a source SCC; each controlled edit produces an injected variant. Evaluating one variant with one model constitutes a model-case. Variants from the same source are not independent samples. Expert evidence and repair-material coverage are evaluated separately from the benchmark endpoint metrics.

**理由**：按源组件、注入变体、模型评估的顺序直接下定义，减少 We call／We assess 的叙述性外壳。把每个模型—变体组合单列一句，便于理解计数单位；同源样本非独立及专家指标单独评估的含义保留。

### 007｜方法动机：TreeMCTS 诊断比较

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:133)。

**原文**

> In a matched-budget diagnostic, TreeMCTS expands 6.4 times as many states as physical nodes in the cyclic setting, with all rollouts truncated. SA-MCGS limits expansion to 1.0 times the component size and increases Q-spread from 0.044 to 0.371. Table 1 includes the acyclic control; Appendix A gives the setup and metric definitions.

**改后**

> With matched rollout budgets, TreeMCTS expands 6.4 times as many states as physical nodes in the cyclic setting, and all rollouts are truncated. SA-MCGS limits expansion to 1.0 times the component size and increases Q-spread from 0.044 to 0.371. Table 1 includes the acyclic control; Appendix A defines the diagnostic setup and metrics.

**理由**：将 matched-budget 具体写成 matched rollout budgets，说明匹配的是 rollout 预算；把 with all rollouts truncated 改成完整并列分句，突出截断是观察结果。附录指引使用 defines，明确其提供设置与指标定义。

### 008｜动态核心：共享轨迹回放指引

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:239)。

**原文**

> The paired replay in Section 6.2 isolates final-core replacement on shared search traces; it does not alter the rollouts themselves.

**改后**

> The paired replay in Section 6.2 isolates the effect of final-core replacement using identical search trajectories.

**理由**：把 isolates final-core replacement 改为 isolates the effect of final-core replacement，明确被隔离的是替换策略的影响。using identical search trajectories 已表达搜索轨迹不变，因此删去后半句重复的 does not alter the rollouts themselves；本段前面的原黑字说明未改。

### 009｜计算可行性：预算前缀分析指引

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:272)。

**原文**

> Budget-prefix behavior is analyzed in Appendix J.2.

**改后**

> Appendix J.2 analyzes performance across rollout-budget prefixes.

**理由**：将被动结构 is analyzed in 改为 Appendix…analyzes，并将含糊的 behavior 写成 performance across rollout-budget prefixes，说明读者在附录可以看到什么。

### 010｜计算可行性：调用量与并发

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:273)。

**原文**

> Measured calls and tokens are reported in Section 6.3; internal rollout concurrency can reduce waiting time without reducing the underlying inference workload.

**改后**

> Section 6.3 reports call and token counts; concurrent rollouts can reduce waiting time without reducing the inference workload.

**理由**：把 measured calls and tokens 改成 call and token counts，明确报告的是数量。用 concurrent rollouts 替代较重的 internal rollout concurrency，删去 underlying；减少等待不等于减少推理工作量的限定保留。


## 实验设置与基线

### 011｜实验设置：注入协议与样本计数

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:317)。

**原文**

> Each injected variant edits existing records in a real SCC without adding nodes. The 20 source SCCs each contribute four variants, giving the same 80 cases per model; five models and three methods yield 400 model-cases and 1,200 outputs. Inputs, injection identities, prompt schemas, and method settings are fixed across this comparison. Appendix I gives the templates, and Appendix J the run profile.

**改后**

> Each injected variant modifies existing records in a real SCC without adding nodes. The 20 source SCCs each contribute four variants, yielding the same 80 cases per model. Five models and three methods produce 400 model-cases and 1,200 outputs. Inputs, injection identities, prompt schemas, and method settings are fixed throughout. Appendix I provides the injection templates, and Appendix J specifies the run configuration.

**理由**：将 20→80 的数据构造与五模型／三方法的 400／1,200 计数拆成两句，避免一条长句连续切换统计单位。附录指引补全动词，并用 injection templates、run configuration 代替较笼统的 templates、run profile。

### 012｜基线说明：One-shot 的整体输入与输出

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_baselines.tex:2)。

**原文**

> This baseline processes the entire SCC in a single LLM call and directly produces a node ranking and a risk subgraph.

**改后**

> One-shot processes the entire SCC in a single LLM call, returning a node ranking and a risk subgraph.

**理由**：将泛指的 ‘This baseline’ 换为具体方法名 ‘One-shot’，使句子脱离小标题也能明确指代；把 ‘and directly produces’ 改为分词结构 ‘, returning’，压缩同一调用的输出描述。删除 ‘directly’ 属于可选的简洁化处理，整图输入、单次 LLM 调用以及两类输出均未改变。

### 013｜基线说明：LEA 窗口与比较条件

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_baselines.tex:6)。

**原文**

> LEA evaluates a four-record window anchored at every SCC node, using the same local evaluator schema as SA-MCGS. It averages node scores and aggregates evidence into a fixed-cap subgraph, without adaptive search, relation memory, critical-pair revisiting, or core replacement. Appendix K.1 specifies window construction, aggregation, and caching. SA-MCGS uses 60 rollouts and dynamic-core selection; the comparison controls the local output task rather than total computation.

**改后**

> LEA evaluates a four-record window anchored at each SCC node, using the same local evaluator schema as SA-MCGS. It averages node scores and aggregates evidence into a fixed-cap subgraph, without adaptive search, relation memory, critical-pair revisiting, or core replacement. Appendix K.1 details window construction, aggregation, and caching. SA-MCGS uses 60 rollouts and dynamic-core selection; the comparison fixes the local output task, but not total computation.

**理由**：‘every’→‘each’、‘specifies’→‘details’ 是可选的措辞调整，分别保留逐节点建窗和附录说明的原意；结尾将 ‘controls the local output task rather than total computation’ 改成 ‘fixes the local output task, but not total computation’，把比较中固定的任务与未固定的总计算量直接说清。窗口大小、聚合方式、禁用组件和 60 次 rollout 均保持原样。

### 014｜实验设置：五模型引出句

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:324)。

**原文**

> We assess SA-MCGS across five LLM backbones: the proprietary GPT-4o (OpenAI, 2024) and Gemini 2.5 Pro (Comanici et al., 2025), and the open-weight Qwen2.5-72B (Qwen, 2024), Llama 3.1-8B-Instruct (Grattafiori et al., 2024), and Qwen3.5-9B (Qwen Team, 2026).

**改后**

> We evaluate SA-MCGS with five LLM backbones: proprietary GPT-4o (OpenAI, 2024) and Gemini 2.5 Pro (Comanici et al., 2025), and open-weight Qwen2.5-72B (Qwen, 2024), Llama 3.1-8B-Instruct (Grattafiori et al., 2024), and Qwen3.5-9B (Qwen Team, 2026).

**理由**：evaluate…with 比 assess…across 更直接地表达用这些模型评估 SA-MCGS；去掉 proprietary 和 open-weight 前不必要的 the，使两类模型列表形式一致。这是轻量风格调整，没有增加跨规模或普适性主张。


## 主结果与配对、领域分析

### 015｜主结果表注：五模型比较与加粗规则

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_results.tex:7)。

**原文**

> Five-model comparison of One-shot, LEA, and SA-MCGS on the same 80 injected variants per model. All metrics are percentages. Bold values indicate the best result for each metric within a model, including ties.

**改后**

> Comparison of One-shot, LEA, and SA-MCGS across five models, each evaluated on the same 80 injected variants. All metrics are percentages. Bold marks the best value for each metric within a model, including ties.

**理由**：将前置的 ‘Five-model comparison … on the same 80 injected variants per model’ 改为 ‘Comparison … across five models, each evaluated on the same 80 injected variants’，用后接分句展开模型数与评估集的关系；‘Bold values indicate the best result’ 缩为 ‘Bold marks the best value’，保留逐模型、逐指标及并列最优的加粗规则。两处均以句式和长度调整为主，未改动模型数、样本数或百分比单位。

### 016｜主结果：四个模型的根节点指标提升

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_results.tex:40)。

**原文**

> SA-MCGS improves Root@3 over both One-shot and LEA for GPT-4o, Qwen2.5-72B, Llama 3.1-8B-Instruct, and Qwen3.5-9B (Table 2). The largest gain over LEA is 17.50 percentage points for Llama 3.1-8B-Instruct.

**改后**

> SA-MCGS achieves higher Root@3 than both One-shot and LEA on GPT-4o, Qwen2.5-72B, Llama 3.1-8B-Instruct, and Qwen3.5-9B (Table 2). The largest gain over LEA is 17.50 percentage points on Llama 3.1-8B-Instruct.

**理由**：‘improves … over both’ 改为 ‘achieves higher … than both’，把表述落在实测指标高于两项基线上；模型前的 ‘for’ 统一改为 ‘on’，属于可选的搭配调整。四个模型、比较对象和最大 17.50 个百分点的增益均未改变。

### 017｜主结果：完整风险证据保留率与 Gemini 表现

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_results.tex:42)。

**原文**

> Complete risk-evidence retention also improves: Risk-all rises over LEA by 31.25 points for both GPT-4o and Qwen2.5-72B, and by 13.75 points for Llama 3.1-8B-Instruct. Gemini 2.5 Pro starts from a high baseline, with Risk-all between 83.75% and 85.00% across the three methods.

**改后**

> Complete risk-evidence retention also improves: Risk-all increases by 31.25 percentage points over LEA on GPT-4o and Qwen2.5-72B, and by 13.75 on Llama 3.1-8B-Instruct. On Gemini 2.5 Pro, all three methods achieve Risk-all between 83.75% and 85.00%.

**理由**：将 ‘rises over LEA by … points’ 改为 ‘increases by … percentage points over LEA’，明确增益单位并调整信息顺序，第二处 ‘percentage points’ 用省略避免重复；模型前 ‘for’ 改为 ‘on’，并删除不必要的 ‘both’。Gemini 句由 ‘starts from a high baseline’ 改为直接陈述三种方法均处于 83.75%–85.00% 区间，去掉了对基线高低的评价性概括，但保留了相同数值与比较范围。

### 018｜主结果：Qwen3.5-9B 的压缩与证据保留

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_results.tex:44)。

**原文**

> Qwen3.5-9B combines higher Root@3 with more compact output: compression reaches 67.25% while Risk-all matches LEA at 63.75%.

**改后**

> On Qwen3.5-9B, SA-MCGS combines higher Root@3 with 67.25% compression, matching LEA's Risk-all of 63.75%.

**理由**：原句以 ‘Qwen3.5-9B’ 为主语，新句用 ‘On Qwen3.5-9B, …’ 交代模型，并让方法名成为主语，明确是谁取得这些结果；把 ‘more compact output: compression reaches … while … matches’ 合并为 ‘with … compression, matching …’，减少重复说明。删除 ‘more compact’ 后，句子保留 67.25% 压缩率这一直接证据，以及与 LEA 同为 63.75% 的风险证据保留率。

### 019｜主结果：逐案例配对比较

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:335)。

**原文**

> Figure 3 shows that SA-MCGS recovers more LEA failures than the reverse for GPT-4o, Qwen2.5-72B, and Llama 3.1-8B-Instruct.

**改后**

> Paired Risk-all outcomes favor SA-MCGS over LEA for GPT-4o, Qwen2.5-72B, and Llama 3.1-8B-Instruct (Figure 3).

**理由**：把 recovers more LEA failures than the reverse 改成 Paired Risk-all outcomes favor…，明确比较的是 Risk-all 配对结果，避免 reverse 指代不清或让人误解为重试恢复。32 对 7 的具体证据保留，图号改放句末。

### 020｜配对收益图：图注

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:344)。

**原文**

> Paired outcomes for complete risk-evidence retention against (a) One-shot and (b) LEA on the same 80 cases per model. Bars partition cases into SA-MCGS only (blue), both methods (light blue), baseline only (orange), and neither method (gray), according to Risk-all. Net $\Delta$ reports SA-MCGS minus baseline Risk-all in percentage points.

**改后**

> Paired Risk-all outcomes for SA-MCGS versus (a) One-shot and (b) LEA on the same 80 cases per model. Bars separate cases where complete evidence is retained by SA-MCGS only (blue), both methods (light blue), the baseline only (orange), or neither method (gray). Net $\Delta$ is the Risk-all difference between SA-MCGS and the baseline, in percentage points.

**理由**：首句直接交代 SA-MCGS 与哪两个基线比较、使用什么指标。将四种分组解释成‘哪些方法保留完整证据’，并将 Net Δ 定义为两方法 Risk-all 的差，使读者不必从正文反推条形和净提升的含义。

### 021｜领域分析：完整证据收益

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:351)。

**原文**

> The model-level gains also appear in the domain breakdowns in Table 14. Pooling the five models, SA-MCGS raises Risk-all over LEA from 26.67% to 51.67% on BGB and from 53.00% to 69.00% on CUAD. These comparisons extend the completeness gains to statutory cross-references and longer contract-clause graphs.

**改后**

> The domain breakdown also shows gains in complete evidence retention (Table 14). Pooling results across the five models, SA-MCGS raises Risk-all over LEA from 26.67% to 51.67% on BGB and from 53.00% to 69.00% on CUAD. These gains extend to statutory cross-references and longer contract-clause graphs.

**理由**：主题句由笼统的 model-level gains 改为 gains in complete evidence retention，明确这一段讨论的指标含义。Pooling results across the five models 表明被汇总的是结果；末句删除 comparisons extend the gains 的绕行表达。


## 分析与正文专家评估

### 022｜正文预算分析：前期收益与后期核心调整

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:367)。

**原文**

> For GPT-4o, most completeness gains emerge within the first 20 rollouts, with later rollouts refining the retained core (Appendix J.2).

**改后**

> For GPT-4o, most gains in evidence completeness occur within the first 20 rollouts; subsequent rollouts refine the retained core (Appendix J.2).

**理由**：将 completeness gains 展开为 gains in evidence completeness，避免脱离上下文后不清楚 completeness 指什么。用分号并列前 20 次与后续 rollout 的作用，替换 with 引出的附带结构；emerge→occur 属于轻量风格选择。

### 023｜消融分析：两阶段设置与不同样本范围

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:5)。

**原文**

> We separate search components (Stage-1) from final-core policy (Stage-2). Table 3 reports the contemporaneous Stage-1 subset and the full shared-trace core replay. The 17-variant SEC subset does not show a benefit from relation memory or critical-pair revisiting; random windows reduce Risk-all modestly. Across the wider, cross-batch 80-variant descriptive summary, removing critical-pair revisiting lowers Risk-all by 21.25 points, random windows by 6.25 points, and removing memory raises it by 6.25 points. These distinct scopes do not establish that every component is independently necessary. Full metrics and the memory-cost comparison appear in Appendix K.

**改后**

> The ablations separate search components (Stage-1) from final-core selection (Stage-2). Table 3 reports contemporaneous Stage-1 runs and Stage-2 replay on shared search traces. On the 17-variant SEC subset, neither relation memory nor critical-pair revisiting improves Risk-all; random windows reduce it modestly. In the cross-batch descriptive analysis of 80 variants, removing critical-pair revisiting lowers Risk-all by 21.25 percentage points and random windows by 6.25, whereas removing memory raises it by 6.25. These results do not establish that each component is independently necessary. Appendix K reports full metrics and memory costs.

**理由**：将 ‘We separate’ 改为 ‘The ablations separate’，‘final-core policy’ 改为 ‘final-core selection’，并用 ‘Stage-1 runs’ 和 ‘Stage-2 replay on shared search traces’ 更直接地描述两阶段操作；但新句删除了表格范围中的 ‘subset’ 与 ‘full’，这两项覆盖范围信息不再在该句明示。把宽泛的 ‘does not show a benefit’ 收窄为 ‘neither … improves’ 风险证据保留指标，将 80 变体结果写成去除组件后的方向性对照，并明确 ‘percentage points’ 后省略重复单位；这是对结论对象的限定，不能理解为已证明所有指标都无收益。末尾 ‘These distinct scopes’→‘These results’、‘every’→‘each’ 主要压缩表述，附录句改为主动结构，但 ‘memory-cost comparison’→‘memory costs’ 也省去了“比较”这一层描述。

### 024｜消融表注：阶段、样本与对照条件

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:10)。

**原文**

> Component tests with GPT-4o. Stage-1: 17 variants/5 SEC sources, contemporaneous runs. Stage-2: 80 variants/20 sources, shared-trace replay. Values are percentages; controls differ between stages.

**改后**

> GPT-4o component ablations. Stage-1 uses contemporaneous runs on 17 variants from 5 SEC sources; Stage-2 replays shared traces for 80 variants from 20 sources. Values are percentages; the stages use different controls.

**理由**：‘Component tests with GPT-4o’ 改为更具体的 ‘GPT-4o component ablations’，并将 ‘17 variants/5 SEC sources’、‘80 variants/20 sources’ 的速记形式展开为完整句，明确变体来自多少来源以及各阶段如何运行。‘controls differ between stages’ 改为主动式 ‘the stages use different controls’，保留样本规模、同期运行、共享轨迹回放和对照不同等条件。

### 025｜消融分析：替换策略与端点保留效果

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:27)。

**原文**

> Stage-2 replays the same observed evidence with replacement or locked no-replacement cores. Replacement improves Risk-all by 37.5 points (source-SCC bootstrap 95% CI: 12.5–60.0), with the same mean 8.1 retained nodes. This supports final-core endpoint retention rather than larger outputs or improved root ranking: the search trajectory is shared.

**改后**

> Stage-2 compares replacement and locked no-replacement cores using the same observed evidence. Replacement improves Risk-all by 37.5 percentage points (source-SCC bootstrap 95% CI: 12.5–60.0), with both cores retaining 8.1 nodes on average. The shared trajectory isolates gains in endpoint retention from changes in output size or root ranking.

**理由**：首句把 ‘replays … with’ 改为 ‘compares … using’，突出在相同证据上比较两种核心策略；‘points’ 明确为 ‘percentage points’，‘with the same mean 8.1 retained nodes’ 展开为两种核心平均都保留 8.1 个节点。结句从 ‘This supports …: the search trajectory is shared’ 改为 ‘The shared trajectory isolates gains …’，重排了论据与结论，但 ‘isolates’ 比 ‘supports’ 更强，且相同平均节点数并不等于各样本输出大小完全相同，因此这一处并非完全等义的语言润色。

### 026｜成本表注：评估规模、严格计分与恢复成本

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:35)。

**原文**

> Contemporaneous cost–performance comparison: 12 sources, two models, three methods (72 runs). Risk-all is strict; calls/tokens average both models and include observed recovery work.

**改后**

> Contemporaneous cost–performance comparison on 12 sources, two models, and three methods (72 runs). Risk-all uses strict scoring. Calls and tokens are averaged across models and include observed recovery work.

**理由**：将冒号后的规模清单连成 ‘comparison on …’，并把原先分号连接的两项口径拆为独立句；‘riskall is strict’ 展开为 ‘uses strict scoring’，‘calls/tokens average both models’ 改为 ‘Calls and tokens are averaged across models’，让计分和平均方式的语法更明确。12 个来源、两个模型、三种方法、72 次运行及计入实际恢复工作量的口径均未改变。

### 027｜成本分析：令牌开销、模型差异与并行时间

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:49)。

**原文**

> Table 4 shows the cost of stronger endpoint retention. SA-MCGS uses about 3.2 times LEA's tokens. Its Risk-all gain over LEA is 41.7 points for GPT-4o (95% CI: 8.3–75.0) and 8.3 for Gemini Pro ($-16.7$–33.3); One-shot is best on the latter model in this sample. Three GPT-4o One-shot outputs are invalid and remain in the denominator. Internal rollout concurrency can reduce waiting for independent calls without reducing token expenditure; Appendix K gives the parallel-time model and recovery accounting.

**改后**

> Table 4 reports inference costs and endpoint retention. SA-MCGS uses about 3.2 times as many tokens as LEA, with Risk-all gains of 41.7 percentage points on GPT-4o (95% CI: 8.3–75.0) and 8.3 on Gemini 2.5 Pro ($-16.7$–33.3). One-shot performs best on Gemini in this sample. Three invalid GPT-4o One-shot outputs remain in the denominator. Concurrent rollouts can reduce wall-clock time without reducing token use; Appendix K details the parallel-time model and recovery accounting.

**理由**：开头由 ‘shows the cost of stronger endpoint retention’ 改为并列报告 ‘inference costs and endpoint retention’，减少预先评价；‘3.2 times LEA’s tokens’ 展开为 ‘3.2 times as many tokens as LEA’，与后面的增益合成一句，并明确 ‘percentage points’、将 ‘Gemini Pro’ 补全为 ‘Gemini 2.5 Pro’。把 ‘the latter model’ 明写为 Gemini 并单独成句，压缩无效输出仍计入分母的说明，再将 ‘Internal rollout concurrency … waiting for independent calls’ 改成 ‘Concurrent rollouts … wall-clock time’、‘token expenditure’ 改为 ‘token use’，使时间与令牌开销的区别更直接，但新句也省略了“独立调用”这一原有限定。

### 028｜敏感性分析：单系数扰动及结论边界

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_main_analysis.tex:51)。

**原文**

> On four prespecified sources, perturbing the relation-prior bonus multiplier by $\pm20%$ does not reduce final Risk-all, but changes Root@3. This is a small, single-coefficient sensitivity check, not evidence that all priors or thresholds are insensitive (Appendix K).

**改后**

> On four prespecified sources, varying the relation-prior bonus multiplier by $\pm20%$ does not reduce final Risk-all but changes Root@3. This single-coefficient check does not establish robustness to other priors or thresholds (Appendix K).

**理由**：‘perturbing’ 换为更常用的 ‘varying’，并删除 ‘but’ 前的逗号；后句把 ‘This is a small, single-coefficient sensitivity check, not evidence that all … are insensitive’ 压缩为 ‘This single-coefficient check does not establish robustness to other …’，直接说明不能外推到其他先验或阈值。新句删去了 ‘small’，但前句仍保留四个预指定来源；‘all … are insensitive’ 与 ‘robustness to other …’ 的覆盖范围不完全相同，因此应视为限制性表述的重新组织，而非逐词同义替换。

### 029｜专家评估：盲审范围与正负样本确认

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_main.tex:5)。

**原文**

> The expanded blinded expert audit covers 24 new injected variants and 18 unmodified sources. Independent annotation and targeted third-expert review identify the new variants as supported positives and the originals as supported negatives.

**改后**

> A blinded expert audit covers 24 new injected variants and 18 unmodified sources. Independent annotation and targeted third-expert review confirm the variants as supported positives and the originals as supported negatives.

**理由**：‘The expanded blinded expert audit’ 改为 ‘A blinded expert audit’，去掉依赖修订过程的 ‘expanded’；后句 ‘the new variants’ 简化为 ‘the variants’，避免与首句的 ‘24 new injected variants’ 重复。‘identify … as’ 改为 ‘confirm … as’ 语气更强，带有对既有标签进行验证的意味，不能仅解释为完全等义的文风调整；样本量、独立标注、第三专家复核和附录引用未变。

### 030｜专家评估：召回、修复参考精确率与证据口径

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_main.tex:7)。

**原文**

> On the new 24 variants (14 source SCCs), source-equal minimal-evidence recall is 90.8% for GPT-4o SA-MCGS versus 65.4% for LEA, and 88.5% versus 86.3% for Gemini Pro. Repair-reference precision also improves over LEA, from 66.5% to 85.0% and from 71.8% to 88.4%, respectively. The Gemini recall difference is uncertain (95% paired CI: $-7.4$–12.0 points). These expert-set metrics assess different evidence than injected-endpoint Risk-all.

**改后**

> On the 24 variants (14 source SCCs), minimal-evidence recall with equal source weighting is 90.8% for GPT-4o SA-MCGS versus 65.4% for LEA, and 88.5% versus 86.3% for Gemini 2.5 Pro. Repair-reference precision rises from 66.5% to 85.0% and from 71.8% to 88.4%, respectively. The Gemini recall difference remains uncertain (95% paired CI: $-7.4$–12.0 points). These metrics assess expert-selected evidence, complementing injected-endpoint Risk-all.

**理由**：‘source-equal minimal-evidence recall’ 展开为 ‘minimal-evidence recall with equal source weighting’，让来源等权的计算口径更易读；删除重复的 ‘new’，补全 ‘Gemini 2.5 Pro’，并把 ‘also improves over LEA’ 缩为 ‘rises’，后者不再在该句显式点名 LEA，而由上下文承接。‘is uncertain’→‘remains uncertain’ 是语气调整；结句把 ‘assess different evidence than’ 改成 ‘assess expert-selected evidence, complementing’，更具体地交代证据来源，但 ‘complementing’ 也新增了互补性的解释，强于仅说证据不同，所有数值和区间保持不变。

### 031｜原始样本评估：误报限制与结果报告范围

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_main.tex:9)。

**原文**

> The unmodified originals expose a detection limitation: nearly all valid outputs assert a conflict under the explicit-pair decision rule, despite expert-negative labels. Invalid outputs are failures, not correct abstentions. Thus useful evidence selection on injected positives does not establish reliable absence detection. Appendix B.2 reports all three methods, original agreement, dual-reference scoring, and separate initial/recovery outcomes.

**改后**

> On the unmodified originals, nearly all valid outputs assert a conflict under the explicit-pair decision rule despite expert-negative labels; invalid outputs count as failures, not abstentions. Thus, improved evidence selection on injected positives does not imply reliable detection of conflict absence. Appendix B.2 reports all three methods, independent agreement, dual-reference scoring, and separate initial and recovery outcomes.

**理由**：用 ‘On the unmodified originals’ 直接引出观察结果，删去 ‘expose a detection limitation’，并将无效输出的处理合并进分号后的分句；‘does not establish reliable absence detection’ 改为 ‘does not imply reliable detection of conflict absence’，明确缺失的对象是冲突。‘useful’→‘improved’ 增加了比较意味，‘not correct abstentions’→‘not abstentions’ 去掉了 ‘correct’ 限定，而 ‘original agreement’→‘independent agreement’ 从原始一致性改成独立标注一致性，均不能一概视为等义润色；最后将 ‘initial/recovery’ 展开为 ‘initial and recovery’，保留分别报告的意思。


## 结论与局限

### 032｜结论：平均收益与输出价值

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:396)。

**原文**

> Across four domains and five LLMs, SA-MCGS improves Root@3 and Risk-all on average over one-shot prompting and LEA. The returned compact risk subgraphs organize cyclic dependencies into focused evidence for human inspection.

**改后**

> Across four domains and five LLMs, SA-MCGS achieves higher mean Root@3 and Risk-all than one-shot prompting and LEA. Its compact risk subgraphs consolidate cyclic dependencies into evidence for human inspection.

**理由**：higher mean Root@3 and Risk-all 将平均值限定放到指标前，避免 on average 修饰范围不清。将 returned…organize…into focused evidence 改成更直接的 Its…consolidate…into evidence，去掉泛化修饰词 focused；结论第一句未改。

### 033｜局限：负例审计、验证范围与人工复核

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:401)。

**原文**

> The 18 audited unmodified sources are expert-confirmed negatives; this tests over-reporting but provides no natural-positive recall estimate or domain-wide prevalence estimate. The strict Stage-1 experiment is a small SEC subset, and prior sensitivity varies one coefficient on four sources. Neither establishes uniform component necessity or equal-token superiority. Graph construction quality also matters, as missing or spurious edges can change the SCCs that the method receives. Finally, Risk-all remains difficult in noisy long-contract settings, so we report it explicitly without replacing it with the easier Risk-any metric. False alarms and omitted evidence both require human review; downstream whole-document decisions after collapse are not evaluated here.

**改后**

> The 18 audited unmodified sources are expert-confirmed negatives, allowing us to assess over-reporting but not recall on naturally occurring risks or domain-wide prevalence. Stage-1 covers a small SEC subset, and the sensitivity analysis varies one prior coefficient on four sources. These designs do not establish uniform component necessity or superiority at equal token budgets. Graph construction quality also matters, as missing or spurious edges can change the SCCs that the method receives. Finally, Risk-all remains difficult in noisy long-contract settings, so we report it explicitly without replacing it with the easier Risk-any metric. False positives and missing evidence require human review; downstream decisions over complete documents remain unevaluated.

**理由**：把 natural-positive recall estimate、equal-token superiority 等密集压缩词组展开为普通学术表达，并用 These designs 明确限制来自前述实验设计。False positives 与全文误报术语一致，missing evidence 比 omitted evidence 更直接；本条只解释这些新增句的改写，段内原黑字说明未动。


## 附录 A、B：诊断与专家审计

### 034｜附录 A：动机诊断的三种比较条件

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:422)。

**原文**

> We compare ordinary TreeMCTS on an acyclic dependency graph, ordinary TreeMCTS on an SCC, and SA-MCGS on the same SCC setting, using matched document-graph components, the same local risk task, and the same rollout budget. Table 1 reports state expansion, rollout truncation, Q-spread, and Hit@3; the diagnostic metrics are defined below.

**改后**

> We compare TreeMCTS on acyclic and strongly connected document graphs with SA-MCGS on the same SCC setting. The comparison uses matched components, the same local risk task, and equal rollout budgets. Table 1 reports state expansion, rollout truncation, Q-spread, and Hit@3, as defined below.

**理由**：把三种条件和共同控制拆开写，避免在同一长句中重复 ordinary TreeMCTS 并堆叠 using 修饰语。equal rollout budgets 明确控制条件，指标定义的指引用 as defined below 接到列表后。

### 035｜附录 B：两轮专家审计的关系

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:440)。

**原文**

> We report two annotation rounds separately: the original 12-case audit below and the new 42-presentation audit in Section B.2. Their label schemas and annotator coverage differ; original aggregate results are retained without imputing missing labels.

**改后**

> We report the original 12-case audit below and the new 42-presentation audit in Section B.2 separately because their annotation schemes and annotator coverage differ. The original aggregate results are retained without imputing missing labels.

**理由**：用 separately because 直接连接‘分开报告’与‘标注方案和覆盖不同’的原因。将保留原聚合结果单独成句；annotation schemes 比 label schemas 更适合这里的人工标注流程语境。

### 036｜扩展专家审计的样本与标注数量

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:9)。

**原文**

> The expanded design selects 36 injected variants from the locked legal-domain experiment, including the original 12 audited cases, and maps them to 18 distinct unmodified source SCCs. The new annotation round covers the remaining 24 injected variants (14 sources) and all 18 originals: 42 presentations and 648 paragraphs. Two experts annotated all 42 independently; the third annotated 14 selected cases (nine originals, five injected variants; 264 paragraphs). There are 98 judgments, not three full sets of 42. The original 12-case results above remain a separate annotation stratum rather than being pooled across different label schemes.

**改后**

> The expanded audit includes 36 injected variants from the locked legal-domain experiment, including the original 12 audited cases, and their 18 distinct unmodified source SCCs. The new annotation round covers the remaining 24 variants (14 sources) and all 18 originals, totaling 42 presentations and 648 paragraphs. Two experts independently annotated all 42 presentations; a third annotated 14 selected cases (nine originals, five injected variants; 264 paragraphs), yielding 98 case-level judgments. The original 12-case results are reported separately because they use a different annotation scheme.

**理由**：将“selects…maps them to”改为“includes…and their”，直接交代注入变体与源 SCC 的对应范围；把冒号后的数量说明并入“totaling”，并补全“42 presentations”和“case-level judgments”，使 42 次呈现、98 份案例级判断的计数单位更清楚。末句将“不合并不同标签体系”的表述压缩为“因标注方案不同而单独报告”，保留原 12 案例结果单列的理由，但删去了“并非三套完整的 42 例标注”这一显式提醒。

### 037｜标注问题、证据集合与盲法说明

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:11)。

**原文**

> Annotators answered two binary questions: whether a target conflict exists and whether the visible material is sufficient to make that judgment. They also selected a minimal evidence set $M$ and a broader repair-material set $R$, with confidence and optional notes. Repair material can include explanatory or bridging records that are not themselves conflicting. Chinese translations supported reading, with originals available for checking. Algorithm outputs and injection information were hidden during actual annotation, as confirmed by the authors; auxiliary-view metadata in archived exports were not rewritten.

**改后**

> Annotators answered two binary questions: whether a target conflict exists and whether the visible material suffices to make that judgment. They selected a minimal evidence set $M$ and a broader repair-material set $R$, and provided confidence scores and optional notes. Repair material may include explanatory or bridging records that are not themselves conflicting. Chinese translations supported reading, with the original text available for verification. The authors confirmed that algorithm outputs and injection information were hidden during annotation; auxiliary-view metadata in the archived exports remain unchanged.

**理由**：用“suffices”压缩“is sufficient”，并将笼统的“with confidence”展开为“provided confidence scores”，使证据集合选择、置信度及备注成为并列的标注操作；“original text”也更明确地指向供核查的原文。将“as confirmed by the authors”改为作者作主语的确认句，删去“actual”，并把归档元数据说明改为当前状态“remain unchanged”；“can”改为“may”属于措辞选择。

### 038｜第三位专家的转交标准与裁定范围

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:14)。

**原文**

> Third-expert selection used the union of disagreement on existence, any insufficient judgment, confidence at most two of five, or evidence-set Jaccard below 0.5 when at least one rater judged a sufficiently supported conflict. Selection did not depend on method performance. After the third expert's independent annotations were received, the authors adopted that expert's complete answer for all 14 reviewed cases; this was not a preregistered majority-vote rule. The remaining 28 cases retain the first two experts' agreed case categories and their separate evidence sets. This yields 18 sufficiently supported negatives and 24 sufficiently supported positives, without claiming that all 42 evidence sets are uniquely adjudicated.

**改后**

> Cases were referred to the third expert if any criterion held: disagreement on conflict existence, any judgment of insufficient evidence, confidence at most two of five, or evidence-set Jaccard below 0.5 when at least one rater judged the conflict sufficiently supported. Selection was independent of method performance. After receiving the third expert's independent annotations, the authors adopted that expert's complete answer for all 14 reviewed cases; this decision was not a preregistered majority-vote rule. The remaining 28 cases retain the first two experts' agreed categories and separate evidence sets. The resulting labels comprise 18 sufficiently supported negatives and 24 sufficiently supported positives; the 42 cases do not all have a single adjudicated evidence set.

**理由**：将抽象的“used the union of”改成“if any criterion held”，明确四项条件满足任一项即可转交，并把“insufficient judgment”展开为证据不足的判断。后半段用“this decision”明确未经预注册的是采用第三位专家完整答案的决定，再以独立分句说明并非全部 42 案例都有单一裁定证据集，避免把正负类别标签与证据集裁定混为一谈。

### 039｜裁定前标注者一致性表注

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:19)。

**原文**

> Agreement before adjudication. E1/E2 covers all 42 presentations; pairs involving E3 cover only the 14 selected cases.

**改后**

> Inter-annotator agreement before adjudication. E1/E2 covers all 42 presentations; E1/E3 and E2/E3 cover the 14 selected cases.

**理由**：在“Agreement”前补“Inter-annotator”，明确表格衡量的是标注者间一致性；把“pairs involving E3”展开为“E1/E3 and E2/E3”，让读者直接看到仅覆盖 14 个选定案例的两组配对。

### 040｜一致性结果及第三专家子集的解释

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:39)。

**原文**

> Table 8 uses original independent votes, not the post-adjudication labels. For E1/E2 on the 24 new positives, mean minimal-set Jaccard is 0.670 and repair-set Jaccard is 0.723. The selected third-expert subset is not representative of unrestricted three-rater agreement. On all 42 cases, existence agreement is high while sufficiency $\kappa$ is lower; the two fields are not interchangeable.

**改后**

> Table 8 reports independent judgments before adjudication. For E1/E2 on the 24 new positives, mean Jaccard similarity is 0.670 for minimal evidence sets and 0.723 for repair sets. Agreement involving E3 is conditional on the selected subset and does not estimate agreement among three raters over all cases. Across all 42 cases, E1/E2 agreement is high for conflict existence, while sufficiency has a lower $\kappa$, distinguishing the two annotation tasks.

**理由**：将“original independent votes”表述为“independent judgments before adjudication”，统一判断术语并直接说明统计时点；把两种 Jaccard 指标写成对称句式，标明各自对应最小证据集与修复集。对 E3 子集的限制由“not representative”改成“conditional on the selected subset”，并明确其不能估计全案例三人一致性；末句补明全 42 案例结果属于 E1/E2，将“两个字段不可互换”改为区分两项标注任务的解释。

### 041｜专家参考指标与案例内评分方式

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:42)。

**原文**

> The outside-reference fraction is $|H\setminus R|/|H|$; it describes disagreement with a repair reference, not proof that every other node is irrelevant. For the five adjudicated positives we use E3's complete reference. For the other 19, we compute each metric against E1 and E2 separately and average the two scores within the case; we do not manufacture a union or intersection gold set. No positive reference denominator is empty.

**改后**

> The outside-reference fraction, $|H\setminus R|/|H|$, measures disagreement with the repair reference; it does not establish that unreferenced nodes are irrelevant. We use E3's complete reference for the five adjudicated positives. For the other 19, we score against E1 and E2 separately and average their scores within each case, without merging their reference sets. All positive reference denominators are nonempty.

**理由**：将参考集外比例的公式并入主句，并把“not proof that every other node is irrelevant”改写为“does not establish that unreferenced nodes are irrelevant”，更直接说明该指标的解释边界。随后前置每组案例的评分动作，用“without merging their reference sets”概括原先不构造并集或交集金标准的规则，去掉带评价色彩的“manufacture”；末句将否定式改为“nonempty”的肯定式。

### 042｜实际系统输出与失败案例的计分约定

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:44)。

**原文**

> Predictions use the returned, deployable evidence core for SA-MCGS, the fixed-cap LEA output, and the direct One-shot subgraph. In the stored SA-MCGS records this is `core_evidence_risk_subgraph_nodes`; ground-truth-assisted diagnostic fields are not used for expert scoring. Cases remain in the denominator after failure. Recall, coverage, and precision are zero for invalid or empty outputs; the outside-reference fraction is also set to zero in that case and must be read alongside validity, not as successful filtering.

**改后**

> Predictions are the returned evidence core for SA-MCGS, the fixed-cap LEA output, and the direct One-shot subgraph. For SA-MCGS, we use `core_evidence_risk_subgraph_nodes`, which is available at inference time, and exclude diagnostic fields that use ground truth. Failed cases remain in the denominator. Invalid or empty outputs receive zero recall, coverage, and precision. Their outside-reference fraction is also zero by convention, so this metric must be interpreted alongside validity.

**理由**：把“deployable evidence core”具体解释为所用字段“available at inference time”，并将不使用依赖真值的诊断字段写成直接的排除规则。把失败保留在分母、无效或空输出的零分处理拆为短句，并为参考集外比例的零值补“by convention”，说明它是计分约定；原先“不能视为成功过滤”的提醒改由“须结合有效性解读”表达。

### 043｜专家参考证据质量表的汇总口径

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:49)。

**原文**

> Expert evidence quality on 24 newly annotated injected variants from 14 sources. Percentages first average variants within each source and then weight sources equally. Brackets are source-SCC bootstrap 95% intervals (20,000 draws, seed 20260922). Validity counts use 24 variants; all planned cases remain in metric denominators.

**改后**

> Expert-reference evidence quality on 24 newly annotated injected variants from 14 sources. Metrics are averaged within each source, then equally across sources, and reported as percentages. Brackets give source-SCC bootstrap 95% intervals (20,000 draws, seed 20260922). Validity counts are out of 24; all planned cases remain in metric denominators.

**理由**：将“Expert evidence quality”改为“Expert-reference evidence quality”，明确质量指标以专家参考集为依据。把原来由“Percentages”作主语的平均过程改为指标先在源内平均、再对源等权平均、最后以百分比报告，并用“out of 24”明确有效性计数的分母。

### 044｜相对 LEA 的差值与精度—覆盖率比较

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:66)。

**原文**

> SA-MCGS–LEA minimal-recall differences are 25.5 points for GPT-4o (95% paired interval 15.3–35.1) and 2.2 for Gemini ($-7.4$–12.0). Repair-precision differences are 18.6 (13.1–23.6) and 16.6 (8.5–24.4), respectively. One-shot's Gemini repair precision is 91.5%, higher than SA-MCGS's 88.4%, but its repair coverage is 37.0% versus 68.3%. This distinguishes compact selection from coverage of material needed for repair.

**改后**

> Relative to LEA, SA-MCGS improves minimal-evidence recall by 25.5 percentage points for GPT-4o (95% paired interval: 15.3–35.1) and 2.2 for Gemini 2.5 Pro ($-7.4$–12.0). The corresponding repair-reference precision gains are 18.6 (13.1–23.6) and 16.6 (8.5–24.4) points. For Gemini 2.5 Pro, One-shot achieves higher repair precision than SA-MCGS (91.5% versus 88.4%) but lower repair coverage (37.0% versus 68.3%), illustrating the trade-off between precise selection and repair-material coverage.

**理由**：将压缩的“方法间 differences”改成“Relative to LEA…improves”，明确比较方向，并将“points”首次写全为“percentage points”、统一“minimal-evidence recall”和“repair-reference precision”名称、补全 Gemini 2.5 Pro 型号。One-shot 的两组对比改为平行的“higher… but lower…”结构；末句从区分“紧凑选择与修复材料覆盖”改为解释“精确选择与覆盖率之间的权衡”，因此包含解释重心的调整，而非完全等义替换。

### 045｜参考集外比例、桥接记录敏感性与变体平均

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:68)。

**原文**

> Outside-reference fractions for One-shot/LEA/SA-MCGS are 15.1/33.5/15.0% with GPT-4o and 8.5/28.2/11.6% with Gemini. The GPT One-shot value includes failed outputs and must not be interpreted as evidence of cleanliness. Allowing the frozen injection bridge in addition to each expert's repair set changes precision by at most 0.4 percentage points; the main table uses expert repair sets without that augmentation. For comparison, variant-weighted minimal recall is 38.2/61.1/88.4% for GPT-4o and 67.0/84.3/86.9% for Gemini. These descriptive variant means are not additional independent samples.

**改后**

> Outside-reference fractions for One-shot/LEA/SA-MCGS are 15.1/33.5/15.0% with GPT-4o and 8.5/28.2/11.6% with Gemini 2.5 Pro. Failed outputs contribute zeros to GPT-4o One-shot's value, so a low fraction alone does not imply better evidence selection. Adding the frozen injection bridge to each expert's repair set changes precision by at most 0.4 percentage points; Table 9 uses the unaugmented expert repair sets. Variant-weighted minimal-evidence recall is 38.2/61.1/88.4% for GPT-4o and 67.0/84.3/86.9% for Gemini 2.5 Pro. These are descriptive averages over the same cases, not additional independent samples.

**理由**：将含糊的“includes failed outputs”展开为失败输出以零值计入，并把“cleanliness”换成“better evidence selection”，让低参考集外比例不能单独说明选择更好的原因更明确。用明确表号替代“main table”，以“unaugmented”说明主表未加入桥接记录，同时补全模型和召回率名称；末句增加“over the same cases”，交代变体平均并未提供额外独立样本。

### 046｜原始负例上的冲突判定与操作性弃权

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:71)。

**原文**

> The operational decision rule asserts a conflict only if the output contains a reasoned conflict record with two distinct exact SCC node IDs; for SA-MCGS, it inspects recorded rollout conflicts. A valid result with no accepted pair is operational abstention, not a separately elicited negative judgment. We do not infer a positive solely from a nonempty selected subgraph. Invalid API or schema outputs are a separate category.

**改后**

> A conflict assertion requires a reasoned conflict record containing two distinct, exact SCC node IDs; for SA-MCGS, this rule is applied to recorded rollout conflicts. A valid result with no accepted pair counts as operational abstention, although the model is not separately asked for a negative judgment. A nonempty selected subgraph alone does not count as a positive. Invalid API or schema outputs form a separate category.

**理由**：将“operational decision rule asserts”改为“conflict assertion requires”，直接写出两个不同且精确匹配的 SCC 节点 ID 这一判定条件，并明确该规则应用于所记录的 rollout 冲突。将“not a separately elicited negative judgment”展开为模型未被单独要求作负面判断，使操作性弃权与显式负例判断的区别更易理解；非空子图和无效输出的规则也改为直接的分类表述。

### 047｜负源审计表注与恢复结果

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:76)。

**原文**

> Negative-source audit: false-positive assertions (FP), operational abstentions (Abs.), and invalid outputs (Inv.), each out of 18. Initial and recovered runs are separate; no invalid output is a correct abstention.

**改后**

> Negative-source audit: false-positive assertions (FP), operational abstentions (Abs.), and invalid outputs (Inv.), each out of 18 sources. Initial and recovery outcomes are reported separately; invalid outputs do not count as abstentions.

**理由**：在“out of 18”后补“sources”，明确分母是 18 个源；“Initial and recovered runs”改为“Initial and recovery outcomes”，使分列对象落在结果而非运行过程上。将“no invalid output is a correct abstention”改为“invalid outputs do not count as abstentions”，直接陈述计数规则。

### 048｜重跑恢复、可靠性解释及额外成本

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:96)。

**原文**

> The initial GPT-4o LEA outcomes are reconstructed from preserved append-only logs: two cases failed and were subsequently rerun, with one recovered. Current result files therefore contain 17 valid outputs rather than the initial 16. SA-MCGS recovery adds one complete run for each of its 24 original failures; 21 recover, yielding 33/36 usable outputs across models. Recovery outcomes are a reliability sensitivity, not an equal-opportunity one-run comparison. Recorded additional work is 63 calls / 261,389 tokens for the two LEA reruns and 1,140 calls / 5,011,988 tokens for SA-MCGS recovery; initial-run costs are additional.

**改后**

> Preserved append-only logs reconstruct the initial GPT-4o LEA outcomes: two cases failed and were rerun, and one recovered. Current result files thus contain 17 valid outputs, compared with the initial 16. For SA-MCGS, one complete rerun per original failure recovers 21 of 24 cases, yielding 33/36 usable outputs across models. These recovery results assess reliability with additional attempts and are reported separately from the single-run comparison. The two LEA reruns require 63 calls and 261,389 tokens; SA-MCGS recovery requires 1,140 calls and 5,011,988 tokens, in addition to initial-run costs.

**理由**：将“are reconstructed from”改为日志作主语的主动句，并把恢复过程合成“每个失败案例完整重跑一次、24 例中恢复 21 例”，减少跨句追踪数量的负担。把“reliability sensitivity”和“equal-opportunity one-run comparison”展开为“额外尝试下的可靠性评估、与单次运行比较分别报告”；成本部分用“and”取代斜杠，并保留初始成本另计的范围说明。

### 049｜负例审计发现及总体推断的边界

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_expert_appendix.tex:98)。

**原文**

> Table 10 shows high over-reporting among valid outputs: all are positive assertions except one Gemini LEA abstention. Smaller all-case false-positive counts caused by more invalid outputs do not indicate better specificity. This sample contains no natural positive, so natural-positive recall is not estimable. The selected original sources support a paired negative audit, not an estimate of a domain's overall natural-conflict prevalence.

**改后**

> Table 10 shows frequent false positives: all valid outputs assert a conflict except one Gemini 2.5 Pro LEA abstention. Lower false-positive counts resulting from more invalid outputs do not indicate better specificity. Because the sample contains no natural positives, it cannot estimate natural-positive recall. The selected sources support a paired negative audit but do not estimate the prevalence of natural conflicts in the domain.

**理由**：将“high over-reporting”换成与本段指标一致的“frequent false positives”，并明确是有效输出作出冲突断言，同时补全 Gemini 型号。用“Because”连接无自然正例与无法估计自然正例召回率的因果关系；末句将抽象的“not an estimate of…prevalence”改为直接的“do not estimate”，保留所选源仅支持配对负例审计、不能估计领域自然冲突流行率的边界。


## 附录 C、G、H、I：案例、提示与领域接口

### 050｜附录 C：BGB 案例图注

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:541)。

**原文**

> Three methods on the same 25-record BGB case with Gemini 2.5 Pro. Node positions are shared across panels; filled markers denote retained records and open markers omitted records. Diamonds identify the root (§505) and witness (§491). The aligned rows below report the retained node count and the four evaluation metrics.

**改后**

> Comparison of three methods on the same 25-record BGB case with Gemini 2.5 Pro. Node positions are fixed across panels; filled markers indicate retained records and open markers indicate omitted records. Diamonds mark the root (§505) and witness (§491). The rows below report retained node counts and the four evaluation metrics.

**理由**：用 Comparison of three methods 明确图的比较功能，fixed across panels 明确节点位置固定。用平行的 filled/open markers indicate 解释保留与遗漏记录；删去 aligned 等不影响读图的修饰。这些主要是图注可读性调整。

### 051｜附录 C：三方法案例解释

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:545)。

**原文**

> Figure 4 compares three ways to organize evidence from the same cyclic region. One-shot retains three records but omits the root. LEA and SA-MCGS both retain all risk endpoints; SA-MCGS uses nine records rather than LEA's twelve, increasing compression from 52% to 64%. The shared layout makes the retained constraint and its distant witness directly comparable.

**改后**

> Figure 4 compares evidence selection within the same cyclic region. One-shot retains three records but omits the root. LEA and SA-MCGS retain all risk endpoints, but SA-MCGS uses nine records compared with twelve for LEA, increasing compression from 52% to 64%. The shared layout allows direct comparison of the retained constraint and its distant witness.

**理由**：将 three ways to organize evidence 收束为 evidence selection，直接对应图中保留哪些节点。把两方法均保留端点与 SA-MCGS 用更少节点放进同一比较句，突出在证据完整前提下的压缩差异；末句语序更直接。

### 052｜共享风险定义：三方法的工作方式

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:746)。

**原文**

> One-shot prompting, LEA, and SA-MCGS use this risk rubric. One-shot returns a global ranking and subgraph; LEA aggregates fixed local evaluations; SA-MCGS adaptively gathers local evidence before selecting its final core.

**改后**

> One-shot prompting, LEA, and SA-MCGS share this risk rubric. One-shot produces a global ranking and subgraph in one call; LEA aggregates fixed local evaluations; SA-MCGS adaptively acquires local evidence to construct its final core.

**理由**：用 share 强调共同 rubric，并补出 One-shot 的 in one call，使与局部评估方法的对照更明确。将 gathers…before selecting 改成 acquires…to construct，连接证据获取与最终核心；没有修改实际提示模板。

### 053｜提示接口：局部评估与算法聚合

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:766)。

**原文**

> One-shot prompting ranks the entire component and produces a final subgraph in one generation. LEA and SA-MCGS share the local evaluator interface, leaving global aggregation outside the LLM. LEA omits adaptive memory and search; its window construction and aggregation are specified in Appendix K.

**改后**

> One-shot prompting ranks the entire component and returns a final subgraph in one generation. LEA and SA-MCGS share a local evaluator interface and aggregate its outputs algorithmically. LEA uses fixed windows without adaptive search or memory; Appendix K specifies its window construction and aggregation.

**理由**：将 leaving global aggregation outside the LLM 改为 aggregate its outputs algorithmically，正面说明聚合由什么完成。LEA uses fixed windows 补回具体操作，再交代无自适应搜索或记忆，减少只有‘不做什么’的定义。

### 054｜附录 I：领域记录类型（公式前）

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:773)。

**原文**

> The four sources differ in surface form. A Debian record exposes package fields, a BGB record is a statutory section, an SEC EX-21 record is a subsidiary disclosure, and a CUAD record is a contract clause. We therefore use lightweight domain formatters

**改后**

> Record formats vary by domain: Debian records contain package fields, BGB records are statutory sections, SEC EX-21 records are subsidiary disclosures, and CUAD records are contract clauses. Lightweight domain formatters

**理由**：用 Record formats vary by domain 直接提出本段差异，并把四类记录统一为复数并列结构。与下一条连读，Lightweight domain formatters 在公式后直接接 serialize 等动词，替换 We therefore use…to 的外层结构；公式本身未改。

### 055｜附录 I：格式化与共享语义（公式后）

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:777)。

**原文**

> to serialize records, expose typed directed edges, and normalize model outputs. These formatters do not define the target risk type and do not reveal the injected endpoints. One-shot prompting, LEA, and SA-MCGS share the same risk rubric that is neutral across domains. Under this rubric, models flag structural inconsistency or mutual incompatibility, as well as risks that are underspecified or have high impact, using only visible node text and directed edges. The comparison varies how evidence is acquired and aggregated: global generation, fixed local aggregation, or adaptive SCC-aware search.

**改后**

> serialize records, expose typed directed edges, and normalize model outputs without specifying a target risk type or revealing injected endpoints. All three methods apply the same domain-neutral rubric to visible node text and directed edges, identifying structural inconsistency, mutual incompatibility, underspecification, and high-impact risks. They differ in how they acquire and aggregate evidence: global generation, fixed local aggregation, or adaptive SCC-aware search.

**理由**：把格式化的三个操作及不提供目标／端点信息合并在一句，避免连续 These formatters…do not…。用 All three methods 接回前文已定义的三方法，统一 structural inconsistency、mutual incompatibility、underspecification 和 high-impact risks 的并列形式；末句直接说明证据获取与聚合方式的区别。

### 056｜领域表：Debian 的评估作用

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:791)。

**原文**

> Tests software migration and dependency constraints beyond legal and financial language.

**改后**

> Evaluates software migration and dependency constraints beyond legal and financial text.

**理由**：Tests→Evaluates 与表内评估作用的表达保持一致，legal and financial text 比 language 更明确地指向输入文本类型。这里是可选的词语调整，原句没有实质性问题；表内其他单元格未改。

### 057｜领域表：SEC EX-21 的评估作用

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:792)。

**原文**

> Tests financial/legal entity reasoning through public disclosures, ownership-chain consistency, and consolidation paths.

**改后**

> Evaluates ownership and consolidation reasoning from public financial and legal disclosures.

**理由**：将 financial/legal entity reasoning 的宽泛标签具体化为 ownership and consolidation reasoning，并去掉 through 后对 public disclosures、ownership-chain consistency、consolidation paths 的并列堆叠。主要是压缩同类概念的重复，来源与建图说明保留。

### 058｜领域表：BGB 的评估作用

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:793)。

**原文**

> Provides a comparatively clean stress test of statutory cross-reference cycles using authoritative legal text.

**改后**

> Provides a relatively clean setting for statutory cross-reference cycles in authoritative legal text.

**理由**：将 comparatively clean stress test 换成 relatively clean setting，减少把数据特点写成额外压力测试结论的语气。statutory cross-reference cycles 和 authoritative legal text 保留；这是表述收束，不是新增实验判断。

### 059｜领域表：CUAD 的评估作用

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:794)。

**原文**

> Provides long, noisy contract components with ambiguity and diffuse evidence.

**改后**

> Tests long contract components with ambiguity and diffuse evidence.

**理由**：用 Tests 把句子改成评估作用，而不只是说数据‘提供’什么。删除 noisy，保留更具体的 ambiguity 和 diffuse evidence，避免几个近义描述叠加；并未调整数据处理或实验结果。


## 附录 J：规模与预算分析

### 060｜附录 J：五模型统一设置

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:834)。

**原文**

> All five models use the same 80 injected variants from 20 source SCCs. One-shot, LEA, and SA-MCGS follow the shared risk rubric and fixed method configurations described in Appendix K. Table 14 reports their model-, domain-, and size-level results.

**改后**

> All five models are evaluated on the same 80 injected variants from 20 source SCCs. One-shot, LEA, and SA-MCGS use the shared risk rubric and fixed method configurations specified in Appendix K. Table 14 groups results by model, domain, and SCC size.

**理由**：are evaluated on 明确同一批变体是评估输入，而不只是 models use。将 model-, domain-, and size-level results 改为 groups results by…，减少多重连字符结构，并说明 size 指 SCC 大小。

### 061｜附录 J.1：按 SCC 规模的收益

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:848)。

**原文**

> Figure 5 shows that SA-MCGS improves Risk-all over LEA in all three size groups for GPT-4o and Qwen2.5-72B. The largest gains for these models occur in medium components, at 37.50 and 62.50 percentage points, respectively. Llama 3.1-8B-Instruct also improves Root@3 in every size group. Figure 6 provides the absolute three-method curves; Table 14 reports the full breakdown.

**改后**

> SA-MCGS improves Risk-all over LEA in all three SCC-size groups for GPT-4o and Qwen2.5-72B (Figure 5). Their largest gains occur in medium components: 37.50 and 62.50 percentage points, respectively. For Llama 3.1-8B-Instruct, Root@3 also improves in every size group. Absolute results appear in Figure 6 and Table 14.

**理由**：将 SA-MCGS 的结果放在句首，图号作为证据指引；medium components 后用冒号直接给两模型数值。用 For Llama…明确提升的主体，合并末尾图和表的导航句，减少连续 provides／reports。

### 062｜规模热图：图注

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:853)。

**原文**

> Cells report percentage-point differences for each model and size group (36 small, 24 medium, and 20 large cases per model). Blue denotes gains and orange losses on a shared zero-centered scale. Figure 6 reports the absolute results for all three methods.

**改后**

> Cells show percentage-point differences for each model and size group (36 small, 24 medium, and 20 large cases per model). Blue indicates gains and orange indicates losses on a shared zero-centered scale. Figure 6 reports absolute performance for all three methods.

**理由**：用 show／indicates 描述单元格和颜色，更贴近读图动作；将 absolute results 改成 absolute performance，点明另一张图展示绝对性能。这主要是图注措辞统一，颜色、分组和样本数完全不变。

### 063｜绝对规模曲线：与热图的对应关系

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:857)。

**原文**

> Figure 6 reports Root@3 and Risk-all for One-shot, LEA, and SA-MCGS on all five models. The size groups and case denominators are identical to those used for the differences in Figure 5.

**改后**

> Figure 6 uses the same size groups and case counts as Figure 5, reporting Root@3 and Risk-all for all three methods and five models.

**理由**：把相同分组和案例数放到句首，先说明两张图可直接对应，再交代报告的指标和模型。两句合成一句，避免重复列出 One-shot、LEA、SA-MCGS 与 five models。

### 064｜绝对规模曲线：图注

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:862)。

**原文**

> Three-method comparison by SCC size. Columns show the five models; rows show (a) Root@3 and (b) Risk-all. All methods use the same small ($\leq12$ nodes), medium (14–20), and large ($\geq24$) case groups. Gray circles denote One-shot, orange squares LEA, and blue triangles SA-MCGS.

**改后**

> Performance by SCC size. Columns correspond to models and rows to (a) Root@3 and (b) Risk-all. All three methods use the same small ($\leq12$ nodes), medium (14–20), and large ($\geq24$) case groups. Gray circles, orange squares, and blue triangles denote One-shot, LEA, and SA-MCGS, respectively.

**理由**：用 Performance by SCC size 直接命名图的分析维度；列、行说明合并成平行句。最后把三个图形和三个方法写成 respectively 对应，减少逐个重复 denote；节点阈值和分组未改。

### 065｜附录 J.2：预算前缀趋势

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:872)。

**原文**

> Figure 7 shows that most completeness gains emerge within the first 20 rollouts: Risk-all rises from 25.00% at budget 5 to 76.25% at budget 20. Subsequent rollouts update the retained core, ending at 75.00% Risk-all and 51.26% compression at budget 60. The final points match the GPT-4o results in Table 2.

**改后**

> Most gains in evidence completeness occur within the first 20 rollouts (Figure 7): Risk-all rises from 25.00% at budget 5 to 76.25% at budget 20. Subsequent rollouts refine the core, reaching 75.00% Risk-all and 51.26% compression at budget 60, matching the GPT-4o results in Table 2.

**理由**：以‘前 20 次获得主要完整性收益’开头，图号后置；把最终数值与主表一致的说明并入同句，删去独立导航句。refine 替换 update 是描述核心逐步调整的风格选择，不表示各预算点单调上升，76.25%→75.00% 的数值保留。

### 066｜预算曲线：前缀重建图注

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:877)。

**原文**

> GPT-4o evidence retention and compression over 60 rollout prefixes on the same 80 cases. The solid curve shows SA-MCGS; horizontal reference lines show the final One-shot and LEA scores. Each prefix uses the saved search evidence and the final-core selection rule, with budget 60 aligned to the final outputs.

**改后**

> GPT-4o evidence retention and compression across 60 rollout prefixes on the same 80 cases. The solid curve represents SA-MCGS; horizontal lines indicate the final One-shot and LEA scores. Each prefix is reconstructed from stored search evidence using the final-core selection rule. Results at budget 60 match the final outputs.

**理由**：将 Each prefix uses…改为 is reconstructed from…using…，明确曲线来自已存轨迹的前缀重建。预算 60 与最终输出一致单列一句，避免 with budget 60 aligned…像含糊的绘图对齐说明；show→represent／indicate 属于图注措辞选择。


## 附录 K：基线、消融、成本与统计协议

### 067｜LEA 的窗口构造与共享评估器

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:21)。

**原文**

> Local Evidence Aggregation (LEA) is our task-aligned structured baseline. It uses graph-based local retrieval and evidence aggregation, rather than reproducing an external GraphRAG system in full. For each node in an SCC, LEA constructs a window containing that node and its incoming and outgoing neighbors, ordered by the fixed SCC node order. Windows contain four nodes; missing positions are filled by alternating forward and backward offsets in that order. LEA evaluates the resulting windows with the same local prompt builder, response schema, and parser as SA-MCGS, including node scores, local risk nodes, conflict relations, critical pairs, and repair entries. Repeated window evaluations can be served from the evaluator's cache. The number of windows follows the graph size; LEA does not run a fixed number of search rollouts.

**改后**

> Local Evidence Aggregation (LEA) provides a structured baseline based on local graph retrieval and evidence aggregation, without implementing a full external GraphRAG system. For each SCC node, LEA constructs a four-node window from the node and its incoming and outgoing neighbors, using the fixed SCC node order. Missing positions are filled by alternating forward and backward offsets in that order. Each window is evaluated with the same local prompt builder, response schema, and parser as SA-MCGS, producing node scores, local risk nodes, conflict relations, critical pairs, and repair entries. Repeated evaluations may use cached results. The number of windows depends on graph size rather than a fixed rollout budget.

**理由**：将开头两句关于 structured baseline 和 local retrieval 的介绍合并，并把 four-node 提前放入窗口定义，减少读者跨句拼接信息的需要；将 including 改为 producing，使节点分数、冲突关系等明确成为评估器的输出。缓存句压缩为 may use cached results，末句直接对照随图规模变化的窗口数与固定 rollout 预算；这些改动压缩表达，没有新增 LEA 的功能。

### 068｜LEA 计数变量与成员分数定义

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:23)。

**原文**

> Let $\bar q_v$ be the mean risk score over windows containing node $v$, and let $L_v$, $R_v$, and $E_v$ count its appearances in local risk sets, repair entries, and conflict-edge endpoints. LEA ranks roots by $\bar q_v$ and scores subgraph membership by

**改后**

> Let $\bar q_v$ denote the mean risk score over windows containing node $v$, and let $L_v$, $R_v$, and $E_v$ count its occurrences in local risk sets, repair entries, and conflict-edge endpoints, respectively. LEA ranks roots by $\bar q_v$ and assigns each node a subgraph membership score

**理由**：在三个计数变量及其对应对象后增加 respectively，明确 L、R、E 与局部风险集、修复条目、冲突边端点的顺序对应；把 scores subgraph membership by 改为 assigns each node a subgraph membership score，明确随后公式给每个节点赋分。be→denote、appearances→occurrences 属于措辞选择，并非原定义有误。

### 069｜LEA 的选择规则与比较边界

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:28)。

**原文**

> It returns the highest-scoring $k=\min\{|S|,\max(4,\lceil0.45|S|\rceil)\}$ nodes, using SCC order to break ties; when all membership scores are zero, it uses the mean-risk ranking. It does not use adaptive relation-memory selection, critical-pair revisiting, OC-guided core construction, or dynamic replacement. This control aligns local evidence production while retaining a simpler aggregation procedure. Computation is measured separately, so it is not an equal-token search comparison.

**改后**

> LEA returns the top $k=\min\{|S|,\max(4,\lceil0.45|S|\rceil)\}$ nodes, breaking ties by SCC order. If all membership scores are zero, it selects nodes by mean risk score. LEA uses no adaptive relation-memory selection, critical-pair revisiting, OC-guided core construction, or dynamic replacement. It therefore shares the local evidence evaluator with SA-MCGS but uses a simpler aggregation procedure. Computational cost is reported separately; token budgets are not matched.

**理由**：以 LEA 替代段首 It，并把零分时的回退选择拆为独立条件句，使 top-k、平分规则和回退规则更容易逐项核对。将 aligns local evidence production 具体写成 shares the local evidence evaluator，将 not an equal-token search comparison 直接写成 token budgets are not matched，分别明确共享的环节与未控制的成本条件。

### 070｜主实验规模、输入匹配与模型设置

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:30)。

**原文**

> The main comparison contains 80 injected variants from 20 source SCCs across Debian, SEC, BGB, and CUAD. GPT-4o, Gemini 2.5 Pro, Qwen2.5-72B, Llama 3.1-8B-Instruct, and Qwen3.5-9B each run One-shot, LEA, and SA-MCGS on these inputs, giving 400 model-cases and 1,200 method outputs. All three methods are matched by source content, SCC membership, and injection identity. The Qwen3.5-9B runs use `enable_thinking=false` for all three methods. The separate contemporaneous cost experiment below uses 12 source SCCs and 72 method jobs.

**改后**

> The main comparison comprises 80 injected variants from 20 source SCCs across Debian, SEC, BGB, and CUAD. GPT-4o, Gemini 2.5 Pro, Qwen2.5-72B, Llama 3.1-8B-Instruct, and Qwen3.5-9B each run One-shot, LEA, and SA-MCGS on the same inputs, yielding 400 model-cases and 1,200 method outputs. Inputs are matched across methods by source content, SCC membership, and injection identity. All Qwen3.5-9B runs use `enable_thinking=false`. The separate contemporaneous cost experiment uses 12 source SCCs and 72 method jobs.

**理由**：在运行输入处明确写 same inputs，并将 All three methods are matched 改成 Inputs are matched across methods，使内容、SCC 成员和注入身份这些匹配条件的对象更准确。把 Qwen3.5-9B 的统一设置压缩为 All Qwen3.5-9B runs，删除末句的 below；contains→comprises、giving→yielding 只是词语替换，样本数和运行数未变。

### 071｜Oracle Top-3-from-10 的选择与成本

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:33)。

**原文**

> The historical oracle-risk Top-3-from-10 reference selects among ten full-SCC attempts using ground-truth metrics. For every three-attempt subset of valid outputs, it computes mean Root@3, Risk-any, and Risk-all; selection maximizes their minimum, then their mean, then mean compression, in lexicographic order. With fewer than three valid attempts it uses all valid attempts; with none, binary metrics are zero. Reported metrics average the selected attempts, rather than evaluating a union of their nodes or subgraphs. This ground-truth-dependent selection is separate from deployable One-shot and LEA, and its ten-attempt computation is not a one-call cost.

**改后**

> The historical oracle-risk Top-3-from-10 reference uses ground-truth metrics to select among ten full-SCC attempts. For each three-attempt subset of valid outputs, it computes mean Root@3, Risk-any, and Risk-all. Selection lexicographically maximizes the minimum of these three metrics, their mean, and mean compression. With fewer than three valid attempts, it uses all valid attempts; with none, binary metrics are zero. Reported metrics average the selected attempts without pooling their nodes or subgraphs. This oracle selection requires ground truth, unlike deployable One-shot and LEA, and incurs the computation of ten attempts.

**理由**：将候选子集的指标计算与字典序选择拆成两句，并用 the minimum of these three metrics 明确最小值取自哪三个均值指标。将 rather than evaluating a union 改为 without pooling，简化“对被选尝试取平均、并不合并子图”的说明；末句直接说明选择依赖真值且包含十次尝试的计算量，保留其与可部署基线的区别。

### 072｜Stage-1 同期消融设置与指标对象

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:38)。

**原文**

> The contemporaneous comparison used GPT-4o, a budget of 60 rollouts, windows of four nodes, and internal concurrency three on 17 SEC variants from five source SCCs. All 68 outputs were valid. The four arms shared input identities, prompt builder, parser, and response schema. Removing relation-first memory disabled relation-biased selection and relation probes; removing the critical-pair ledger disabled its protection and revisiting; random-window selection replaced the local-window selector. Table 15 reports metrics on the returned core, not endpoint coverage in the root ranking.

**改后**

> The contemporaneous comparison used GPT-4o with 60 rollouts, four-node windows, and internal concurrency three on 17 SEC variants from five source SCCs. All 68 outputs were valid. The four ablation conditions shared input identities, prompt builder, parser, and response schema. Removing relation-first memory disabled relation-biased selection and relation probes; removing the critical-pair ledger disabled its protection and revisiting; random-window selection replaced the local-window selector. Table 15 measures endpoint coverage in the returned core, separately from root-ranking performance.

**理由**：把 a budget of 60 rollouts、windows of four nodes 分别压缩为 60 rollouts、four-node windows，并将 four arms 写成 four ablation conditions，降低实验设置句的阅读负担。末句改为先说明在返回核心中衡量端点覆盖，再说明其与根节点排序表现分开，突出这两类结果的评估对象不同。

### 073｜Stage-1 消融表图注

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:42)。

**原文**

> Root@3, Any (Risk-any), All (Risk-all), and compression (Comp.) are percentages; $|H|$ is the mean number of returned core nodes. Panel A is a contemporaneous four-arm comparison. Panel B combines 63 identity-matched historical variants with the 17 rerun variants in every arm and is descriptive across batches.

**改后**

> Root@3, Any (Risk-any), All (Risk-all), and compression (Comp.) are percentages; $|H|$ is mean core size. Panel A compares four conditions contemporaneously. Panel B combines 63 historical variants with verified input identities and the 17 rerun variants for each condition, providing a descriptive comparison across batches.

**理由**：将 mean number of returned core nodes 压缩为 mean core size，并把 four-arm comparison 改为 four conditions contemporaneously。将 identity-matched 展开为 verified input identities、every arm 改为 each condition，使历史样本的身份核验和各条件共用 17 个重跑样本更直观，同时保留 Panel B 仅作跨批次描述比较的限定。

### 074｜Stage-1 同期结果与无记忆条件成本

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:65)。

**原文**

> On the contemporaneous subset, source-SCC-equal Risk-all was 88.3%, 100%, 100%, and 85.0%, respectively. Relative to Full, the two removals each changed this estimate by $+11.7$ percentage points (95% paired interval $[0,25.0]$); random windows changed it by $-3.3$ points ($[-20.0,15.0]$). Thus this small subset did not establish a positive independent contribution of memory or critical-pair revisiting. Full's two Risk-all failures retained the endpoints in the ranking but omitted one from the final core. Table 16 also shows that removing memory did not buy its higher endpoint coverage through more calls or tokens.

**改后**

> On the contemporaneous subset, Risk-all averaged equally over source SCCs was 88.3%, 100%, 100%, and 85.0%, respectively. Relative to Full, each component removal changed this estimate by $+11.7$ percentage points (95% paired interval $[0,25.0]$), whereas random windows changed it by $-3.3$ points ($[-20.0,15.0]$). This subset therefore provides no clear evidence of an independent benefit from memory or critical-pair revisiting. In both Full Risk-all failures, the ranking retained the endpoints but the final core omitted one. Removing memory improved endpoint coverage with fewer calls and tokens (Table 16).

**理由**：将 source-SCC-equal 展开为 averaged equally over source SCCs，并用 whereas 连接组件移除与随机窗口的相反方向变化，使估计口径和对照关系更明确；将 did not establish a positive independent contribution 改为 provides no clear evidence of an independent benefit，仍然只陈述证据不足。失败案例句改成“排序保留端点、最终核心遗漏一个”的直接结构，成本句改为 fewer calls and tokens；后者比原来的“未靠更多调用或 token 换取”更具体，表中 No memory 的 979 次调用、1.576M tokens 均低于 Full 的 995 次、1.638M。

### 075｜Stage-1 成本表图注

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:69)。

**原文**

> Costs for the 17-case contemporaneous Stage-1 matrix. Calls, tokens, and estimated USD are totals per arm; time is mean seconds per case. Token costs use the frozen gateway-price snapshot.

**改后**

> Costs for the 17-case contemporaneous Stage-1 comparison. Calls, tokens, and estimated USD are totals for each condition; time is mean seconds per case. Token costs use the frozen gateway prices.

**理由**：将 matrix 改为 comparison、per arm 改为 for each condition，使图注沿用正文对实验条件的称呼。将 frozen gateway-price snapshot 压缩为 frozen gateway prices，保留价格固定这一计价前提；总调用量、总 token、总费用及平均每例时间的口径未变。

### 076｜Stage-1 跨批次描述结果的解释边界

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:85)。

**原文**

> For broader descriptive coverage, Panel B combines the 17 reruns with 63 historical variants whose input identities were independently verified. Full is updated on the same 17 variants as every ablation. The historical Full outputs lack complete prompt/configuration hashes, so this panel is not a contemporaneous 80-case attribution test. Relative to Full, Risk-all changed by $-21.25$ points without critical-pair revisiting, $-6.25$ with random windows, and $+6.25$ without memory. The broader critical-pair signal and the inconclusive contemporaneous subset therefore have different scopes; relation memory did not show a consistent independent gain.

**改后**

> Panel B extends the descriptive comparison to 80 variants by combining the 17 reruns with 63 historical variants whose input identities were independently verified. Full and all ablations are updated on the same 17 variants. Because the historical Full outputs lack complete prompt/configuration hashes, this panel supports a descriptive comparison across batches rather than contemporaneous attribution. Relative to Full, Risk-all changed by $-21.25$ points without critical-pair revisiting, $-6.25$ with random windows, and $+6.25$ without memory. The critical-pair gain in this broader sample does not resolve the inconclusive contemporaneous result; memory showed no consistent independent gain.

**理由**：开头直接交代 Panel B 扩展到 80 个变体，并明确 Full 和所有消融均更新同一组 17 个样本；将历史 Full 缺少完整哈希与只能作跨批次描述比较写成明确的因果关系。末句由“两组结果范围不同”改为“较大样本中的关键对收益不能消除同期结果的不确定性”，更直接提醒读者不要用跨批次结果替代同期归因结论。

### 077｜Stage-2 共享轨迹回放协议

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:90)。

**原文**

> We replayed the frozen GPT-4o Full trajectories for 80 variants from 20 source SCCs without new model calls. Both policies consumed the same selector proposal at each trajectory prefix. The dynamic policy allowed replacement; the locked policy admitted nodes until the cap and then retained them without eviction. OC signals, relation seeding, critical-pair protection, pair closure, thresholds, and the cap remained shared.

**改后**

> We replayed frozen GPT-4o Full trajectories for 80 variants from 20 source SCCs without new model calls. Both policies received the same selector proposal at each trajectory prefix. The dynamic policy allowed node replacement; the locked policy admitted nodes up to the cap and retained them without eviction. Both shared OC signals, relation seeding, critical-pair protection, pair closure, thresholds, and the cap.

**理由**：将策略 consumed 同一提案改为 received，给 replacement 补出 node，并把 admitted nodes until the cap 改为 admitted nodes up to the cap，明确策略接收的输入及其节点操作。将共享参数列表改为 Both shared，让两种策略成为明确主语；冻结轨迹、零新增模型调用及 80 对一致性检查均保持原意。

### 078｜Stage-2 表中 Root@3 的固定性

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:94)。

**原文**

> Root@3 is inherited from the common trajectory and is not a core-policy effect.

**改后**

> Root@3 is fixed by the shared trajectory and is unaffected by the core policy.

**理由**：将 Root@3 is inherited from the common trajectory and is not a core-policy effect 改为 is fixed by the shared trajectory and is unaffected by the core policy，直接说明该指标在共享轨迹回放中的固定来源与不受核心策略影响的原因。这里澄清的是本回放比较的解释范围，没有增加性能结论。

### 079｜Stage-2 回放可归因范围

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:108)。

**原文**

> This isolates final endpoint retention conditional on observed evidence; it does not test changed search trajectories or the independent effects of OC and closure.

**改后**

> The replay isolates endpoint retention given the observed evidence; search trajectories are fixed, and OC and closure are not ablated independently.

**理由**：将含糊的 This 换成 The replay，并把 conditional on observed evidence 写成 given the observed evidence，让端点保留效应的条件更易理解。原来“并未测试变化后的轨迹或 OC、closure 的独立效应”改为“轨迹固定，OC 和 closure 未分别消融”，直接用实验操作解释边界；提升幅度、区间及与 Stage-1 运行批次的差别未变。

### 080｜成本实验的样本构成与调用设置

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:113)。

**原文**

> The cost experiment selected one injected variant from each of 12 distinct source SCCs: Debian/SEC/BGB/CUAD contributed 2/3/3/4 SCCs, the four templates contributed three each, and small/medium/large SCCs numbered 6/3/3. GPT-4o and Gemini 2.5 Pro each ran One-shot, LEA, and SA-MCGS on these frozen inputs, yielding 72 method jobs. SA-MCGS used 60 rollouts, windows of four, and internal concurrency one. One-shot used one full-SCC direct-subgraph generation; it did not use oracle selection.

**改后**

> The cost experiment used one injected variant from each of 12 distinct source SCCs. Debian/SEC/BGB/CUAD contributed 2/3/3/4 SCCs; each of the four templates contributed three variants; and small/medium/large SCCs numbered 6/3/3. GPT-4o and Gemini 2.5 Pro each ran One-shot, LEA, and SA-MCGS on these frozen inputs, yielding 72 method jobs. SA-MCGS used 60 rollouts, four-node windows, and internal concurrency one. One-shot generated a subgraph directly from the full SCC in a single call, without oracle selection.

**理由**：将样本总述与各领域、模板、规模的配额拆句，并补明每个模板贡献 three variants，避免三个数值分组挤在同一句中。把 windows of four 写为 four-node windows，将 one full-SCC direct-subgraph generation 展开成从完整 SCC 在单次调用中直接生成子图，使窗口单位和 One-shot 的调用方式更清楚。

### 081｜成本、性能与可靠性表图注

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:117)。

**原文**

> Model-level cost, performance, and reliability on 12 source SCCs per model–method row. All binary rates use the strict denominator 12; invalid outputs count as failures. Comp. is valid-output mean compression, with its denominator shown in parentheses. Calls and token counts include recorded recovery use and are divided by 12. Token units are thousands. Time is recorded runtime per case, not a measured parallel-speedup result.

**改后**

> Cost, performance, and reliability on 12 source SCCs for each model–method pair. All binary rates use a denominator of 12, with invalid outputs counted as failures. Comp. is mean compression over valid outputs; parentheses give the denominator. Calls and tokens include recorded recovery usage and are divided by 12. Tokens are in thousands. Time is recorded runtime per case; parallel speedup was not measured.

**理由**：将 per model–method row 改为 for each model–method pair，并把有效输出压缩率及括号分母的说明拆开，使每行的评估单位和不同指标的分母更易核对。删除 strict 等不影响定义的修饰，把 token 单位写为 Tokens are in thousands，末句直接说明未测量并行加速；无效输出计失败、恢复调用计入成本等口径保留。

### 082｜无效输出、恢复执行与未知成本

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:151)。

**原文**

> There were 69 valid and three invalid final outputs; all invalid outputs were GPT-4o One-shot and remained in the cost and performance denominators. One Gemini SA-MCGS job was interrupted and restarted, contributing 17 pre-interruption and 56 recovery calls. Its final validity is distinct from first-attempt success. Recorded usage includes both executions; unreturned in-flight requests cannot be assigned zero cost. Its runtime records the recovery interval, with pre-interruption API time retained separately in the ledger.

**改后**

> Of the final outputs, 69 were valid and three were invalid. All invalid outputs came from GPT-4o One-shot and remained in the cost and performance denominators. One Gemini SA-MCGS job was interrupted and restarted, with 17 calls before interruption and 56 during recovery; its valid final output required more than one execution. Recorded usage includes both executions, although costs for unreturned in-flight requests are unknown. Runtime covers the recovery interval, with pre-interruption API time recorded separately.

**理由**：把有效与无效输出的数量和来源拆成两句，并将 pre-interruption/recovery calls 展开为中断前及恢复期间的调用，便于读者追踪这次重启。将“最终有效不同于首次成功”具体写为有效结果经历多次执行，将“未返回请求不能算作零成本”改为其成本未知，直接呈现记录边界；运行时间覆盖恢复阶段、先前 API 时间另记的限定仍在。

### 083｜成本收益在模型间的差异

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:153)。

**原文**

> Averaging models equally, SA-MCGS used 203.4K tokens per case versus 63.7K for LEA, approximately $3.2\times$ as many. Thus additional computation had model-dependent returns.

**改后**

> Averaged equally across models, SA-MCGS used 203.4K tokens per case, compared with 63.7K for LEA, or approximately $3.2\times$ as many. The performance gains from additional computation thus varied by model.

**理由**：将 Averaging models equally 改成 Averaged equally across models，并用 compared with 和 or approximately 衔接两组 token 数及约 3.2 倍的关系，使等权平均的对象与比较关系更清楚。末句把抽象的 model-dependent returns 写成 performance gains ... varied by model，明确这里说的是额外计算对应的性能收益；数值与区间未改。

### 084｜并行执行时间公式的引入

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:155)。

**原文**

> Internal rollout concurrency can reduce the waiting component of that computation. A simple execution approximation is

**改后**

> Internal rollout concurrency can reduce waiting time. A simple approximation to wall-clock time is

**理由**：将 reduce the waiting component of that computation 简化为 reduce waiting time，并将 execution approximation 明确为 approximation to wall-clock time。这样直接指出并发可能改变的是等待时间，以及随后公式近似的量是墙钟时间。

### 085｜并行时间变量与实测边界

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:161)。

**原文**

> where dependency-ordered group $g$ contains $n_g$ parallelizable calls, with effective parallelism $p_g$ and representative latency $t_g$. Available work, workers, and API limits constrain $p_g$. For fixed work, concurrency does not reduce calls, tokens, or fees. Equation 16 is an execution model, not an empirically measured speedup; running different cases concurrently does not measure within-case acceleration.

**改后**

> where each dependency-ordered group $g$ contains $n_g$ parallelizable calls, $p_g$ is effective parallelism, and $t_g$ is representative call latency. Available work, workers, and API limits constrain $p_g$. For fixed work, concurrency leaves calls, tokens, and fees unchanged. Equation 16 models execution time; no within-case speedup was measured, and concurrent execution of separate cases does not establish such a speedup.

**理由**：将组内调用数、有效并行度及延迟分别对应到 n、p、t，并为 latency 补出 call，使公式变量的指向明确；将 does not reduce 改成 leaves ... unchanged，承接固定工作量这一前提。末句不再泛称“不是实测加速”，而是明确没有测量单案例内部加速、不同案例同时运行也不能证明这种加速，从而突出与本实验相关的限制。

### 086｜关系先验敏感性实验的控制设置

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:166)。

**原文**

> We perturbed only the relation-prior bonus multiplier (configuration key `relation_prior_weight`), from its default 0.85 to 0.68 and 1.02 ($\pm20%$), on four source SCCs selected and frozen before observing the sensitivity results (cost slots 01/03/08/10). The node, edge, and pair feature weights in Table 11 remained fixed. The two models produced 16 new valid outputs, and eight identity/configuration-matched nominal outputs were reused from the cost experiment. Other settings, including the rollout budget and internal concurrency one, were fixed.

**改后**

> We varied the relation-prior bonus multiplier (`relation_prior_weight`) from its default 0.85 to 0.68 and 1.02 ($\pm20%$). The four source SCCs (cost slots 01/03/08/10) were selected and frozen before the sensitivity results were observed. Node, edge, and pair feature weights in Table 11 remained fixed. The two models produced 16 new valid outputs; eight nominal outputs with matching inputs and configurations were reused from the cost experiment. All other settings were fixed, including rollout budget and internal concurrency one.

**理由**：将系数扰动范围与四个源 SCC 的预先选定拆成两句，减少参数、样本及冻结时点集中在一个长句中的负担；将 identity/configuration-matched 展开为 matching inputs and configurations，让复用标称输出的条件更容易理解。末句改为 All other settings were fixed，并继续列出 rollout 预算与内部并发度，清楚保留只改变该系数的实验控制。

### 087｜关系先验敏感性表图注

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:170)。

**原文**

> Exploratory relation-prior sensitivity: four source SCCs per row.

**改后**

> Exploratory sensitivity to the relation-prior multiplier on four source SCCs per row.

**理由**：将笼统的 relation-prior sensitivity 改为 sensitivity to the relation-prior multiplier，准确指出被扰动的是关系先验乘数。四个源 SCC 的样本量、探索性定位及各指标单位均未改变。

### 088｜敏感性结果及其外推限制

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:186)。

**原文**

> Endpoint completeness did not decrease on this subset, while root ranking changed (Table 19). With only four source clusters, this is a local sensitivity check of one coefficient, not evidence that all priors or core thresholds are insensitive. Parallel submission of independent sensitivity jobs does not support a runtime comparison against the serial nominal runs.

**改后**

> Endpoint completeness did not decrease on this subset, although root rankings changed (Table 19). This four-cluster check characterizes local sensitivity to one coefficient; it does not establish robustness to other priors or core thresholds. The sensitivity jobs ran concurrently across cases, precluding a direct runtime comparison with the serial nominal runs.

**理由**：将 while 改成 although，更明确地对照端点完整性未下降与根排序发生变化；将“并非所有先验或阈值均不敏感的证据”改为“不足以确立对其他先验或阈值的稳健性”，突出本次仅检查一个系数的边界。末句把跨案例并发这一执行事实与不能直接对比串行标称运行时间连接起来，使不可比的原因更直接。

### 089｜实验身份匹配与批次保留

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:191)。

**原文**

> The frozen manifests distinguish physical source SCCs from injected variants and model–method outputs. Input matching uses source content, SCC node membership, and injection identity; an SCC's traversal index alone is not its identity. The experiment bundles retain raw outputs, result hashes, prompt/schema and configuration records, parser versions, and call-level usage. The 80-case descriptive Stage-1 table is rebuilt from its 63-case raw manifest and the 17-case formal results without overwriting either batch.

**改后**

> Frozen manifests distinguish physical source SCCs, injected variants, and model–method outputs. Inputs are matched by source content, SCC node membership, and injection identity, rather than traversal index alone. Experiment bundles retain raw outputs, result hashes, prompt/schema and configuration records, parser versions, and call-level usage. The descriptive 80-case Stage-1 table is reconstructed from the 63-case raw manifest and 17-case formal results, preserving both batches.

**理由**：将输入匹配方式与“仅凭遍历序号不足以识别 SCC”合并成一句，直接列出可靠匹配所用的内容、节点成员和注入身份。把末尾 without overwriting either batch 改为 preserving both batches，以正面表述说明重建 80 例表时保留两批原始记录；清单区分的实体层级及留存记录类型未变。

### 090｜统计分母、端点指标与聚类重采样

位置：[当前源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_experiments.tex:193)。

**原文**

> For the ablation and cost experiments, binary performance includes every planned output; invalid or undefined outcomes count as failures. Compression is $1-|H|/|S|$ and is computed only when an output is defined, with its denominator disclosed. Risk-any and Risk-all evaluate intersection and full inclusion of the injected endpoint set in $H$; they do not measure precision of every returned node. Paired intervals use 20,000 percentile-bootstrap replicates with seed 8229, resampling physical source SCCs jointly across methods. Source-equal estimates first average variants within each SCC; variant averages are explicitly identified. Models and variants from one source are not additional independent clusters. These intervals describe the selected source set and do not estimate natural-risk prevalence.

**改后**

> For the ablation and cost experiments, binary performance uses all planned outputs, counting invalid or undefined outcomes as failures. Compression is $1-|H|/|S|$ and is computed only for defined outputs, with the denominator reported. Risk-any and Risk-all measure intersection and full inclusion of the injected endpoint set in $H$, respectively, rather than node-level precision. Paired intervals use 20,000 percentile-bootstrap replicates with seed 8229, resampling physical source SCCs jointly across methods. Source-equal estimates average variants within each SCC before averaging SCCs; variant-level averages are labeled explicitly. Models and variants from the same source do not constitute independent clusters. The intervals characterize the selected source set, not natural-risk prevalence.

**理由**：将无效或未定义结果计失败并入二元指标的主句，并用 respectively 明确 Risk-any、Risk-all 分别对应交集与完全包含；将“不衡量所有返回节点的精确率”压缩为 rather than node-level precision。将 Source-equal 的步骤补写为先在 SCC 内平均变体、再平均 SCC，使等源加权口径完整显式化，同时将独立聚类和自然风险发生率的限制压缩为更直接的句子。

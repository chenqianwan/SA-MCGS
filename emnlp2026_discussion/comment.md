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

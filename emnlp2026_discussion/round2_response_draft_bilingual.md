# Round-2 Discussion Response Draft

Working draft for EMNLP 2026 discussion. The English version is written in a reviewer-facing style and can be adapted for OpenReview. The Chinese version follows as a faithful translation for internal checking.

---

## English Draft

**Comment title:** Follow-up evidence: component ablations, graph-aware baseline, and preliminary cost accounting

Thank you again for the concrete suggestions in the reviews. In our initial response, we acknowledged three main gaps that needed additional evidence: **component-level ablations**, **a fairer graph-aware decomposed baseline**, and **cost / reliability accounting**. We have now completed several additional analyses and summarize the main results below.

We will incorporate these results into the revision. We will also revise the paper's framing to avoid overclaiming uniform superiority across all models or direct coverage of naturally occurring high-stakes risks.

### Summary of New Evidence

| Reviewer concern | New evidence now available | Main takeaway for revision |
|---|---|---|
| Component-level contribution of SA-MCGS modules | Stage-1 ablations on **80 gpt-4o cases** and Stage-2 dynamic-core ablations on **40 cases** | The strongest evidence supports the importance of **critical-pair ledger/revisit** and **dynamic/replacement core construction**. Random window selection also hurts endpoint completeness. Relation-first memory is not uniformly worse when removed in this sample, so we will frame it cautiously. |
| Baseline fairness / prompt-decomposition confound | A **GraphRAG-style Local Evidence Aggregation (LEA)** baseline on **160 matched cases**, using graph-window retrieval and the same local evidence schema, but without SA-MCGS memory/search/core mechanisms | LEA is a strong baseline, especially on Gemini 2.5 Pro. However, SA-MCGS still improves endpoint completeness overall, especially on gpt-4o and Risk-all. This supports the value of SCC-aware search and core construction, while confirming model-level non-uniformity. |
| Inference cost and reliability | A preliminary **20-case low-concurrency cost audit** covering Full-SCC Naive, LEA, and SA-MCGS with calls, tokens, runtime, invalid rate, and performance metrics | SA-MCGS has higher cost, as reviewers correctly noted, but also removes invalid-output failures in this audit and improves Root@3 / Risk-all. LEA substantially reduces calls compared with SA-MCGS and should be reported as a cost-performance middle point. A larger cost audit is still running and will be used to update final numbers. |

### 1. Graph-Aware Decomposed Baseline

To address the concern that the original Full-SCC Naive comparison may confound method quality with prompt decomposition and output-schema difficulty, we implemented a **GraphRAG-style Local Evidence Aggregation (LEA)** baseline.

LEA uses deterministic graph-window retrieval and the same local evidence schema as SA-MCGS, followed by transparent aggregation. It does **not** use relation-first memory, critical-pair revisiting, OC/core signals, UCB-style rollout selection, or dynamic-core replacement. This makes it a more direct test of whether the gains come merely from local decomposition / graph-window prompting, or from the SCC-aware search and memory mechanisms in SA-MCGS.

| Group | N | LEA Root@3 | SA-MCGS Root@3 | Delta | LEA Risk-all | SA-MCGS Risk-all | Delta | LEA calls | SA-MCGS calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Overall | 160 | 83.8% | **86.9%** | +3.1 | 66.2% | **79.4%** | **+13.1** | 15.7 | 55.7 |
| Gemini 2.5 Pro | 80 | **88.8%** | 87.5% | -1.2 | **88.8%** | 83.8% | -5.0 | 14.9 | 53.0 |
| gpt-4o | 80 | 78.8% | **86.2%** | **+7.5** | 43.8% | **75.0%** | **+31.2** | 16.5 | 58.5 |
| Large SCCs | 40 | **85.0%** | 77.5% | -7.5 | 55.0% | **72.5%** | **+17.5** | 25.6 | 56.5 |
| Medium SCCs | 48 | 75.0% | **83.3%** | **+8.3** | 64.6% | **75.0%** | **+10.4** | 14.7 | 57.8 |
| Small SCCs | 72 | 88.9% | **94.4%** | **+5.6** | 73.6% | **86.1%** | **+12.5** | 10.8 | 54.0 |

These results sharpen the claim. LEA is indeed competitive, which confirms the reviewers' concern that **structured graph-window decomposition is a strong baseline and should not be dismissed**. At the same time, SA-MCGS improves **Risk-all**, our strict endpoint-completeness metric, by **13.1 points overall** and by **31.2 points on gpt-4o**. This suggests that the additional SA-MCGS mechanisms are most useful when the model benefits from repeated structured evidence accumulation rather than one-pass local aggregation.

We will revise the paper accordingly: instead of claiming uniform dominance, we will state that **SA-MCGS improves endpoint completeness and robustness under cyclic long-context pressure, while strong decomposed or full-SCC models can be competitive in some settings**.

### 2. Component-Level Ablations

We also added component-level ablations to isolate which modules drive the observed gains.

#### Stage 1: Search / Memory Ablations on 80 Cases

| Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core size |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | 80 | 86.2% | **100.0%** | **75.0%** | 51.3% | 0.0 | 8.1 |
| No relation-first memory | 80 | **88.8%** | 98.8% | 80.0% | 51.8% | +5.0 | 8.0 |
| No critical-pair ledger/revisit | 80 | 83.8% | 88.8% | 53.8% | 72.0% | **-21.3** | 4.2 |
| Random local-window selection | 80 | 90.0% | 96.2% | 63.7% | 51.8% | **-11.3** | 8.0 |

The clearest Stage-1 result is that removing the **critical-pair ledger/revisit** mechanism substantially reduces endpoint completeness: Risk-all drops from **75.0% to 53.8%**. Random local-window selection also lowers Risk-all from **75.0% to 63.7%**, suggesting that the graph-guided selection policy matters beyond simply repeating local prompts.

The relation-first-memory ablation is more nuanced: in this particular gpt-4o sample, removing it does not reduce aggregate Risk-all. We therefore will not overstate this module as independently dominant. Instead, we will describe it as part of the evidence organization mechanism whose role may be model- and setting-dependent.

The SCC-size breakdown reinforces the importance of critical-pair revisiting. On large SCCs, removing the critical-pair ledger/revisit reduces Risk-all from **58.3% to 16.7%**, a **41.7-point drop**.

#### Stage 2: Dynamic-Core Ablations on 40 Cases

| Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core size |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | 40 | **85.0%** | **100.0%** | **70.0%** | 52.1% | 0.0 | 10.0 |
| No OC/core signal | 40 | **85.0%** | **100.0%** | 60.0% | 52.2% | -10.0 | 9.7 |
| Monotone core | 40 | 77.5% | 87.5% | 45.0% | 76.1% | **-25.0** | 4.8 |
| No pair closure in final core | 40 | 80.0% | 95.0% | 67.5% | 53.0% | -2.5 | 9.4 |

The dynamic-core ablation shows that replacing the dynamic/replacement core with a monotone accumulation strategy strongly hurts endpoint completeness: Risk-all drops from **70.0% to 45.0%**. Removing OC/core signals also reduces Risk-all by **10.0 points**, while disabling final pair closure has a smaller effect in this sample.

We will revise the ablation section to emphasize the modules with the strongest direct support: **critical-pair ledger/revisit**, **graph-guided local-window selection**, and **dynamic/replacement core construction**.

### 3. Preliminary Cost and Reliability Accounting

We agree with the reviewers that practical inference cost must be reported explicitly. We therefore ran a low-concurrency cost audit with provider-observed input tokens, output tokens, total tokens, API calls, runtime, invalid-output rate, and performance.

The current frozen audit covers 20 cases and compares Full-SCC Naive, LEA, and SA-MCGS under the same accounting framework. We are also running a larger 40-case audit, which will update the final cost table.

| Method | Cases | Invalid | Calls / case | Total tokens / case | Runtime / case | Root@3 | Risk-any | Risk-all | Compression |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full-SCC Naive | 20 | 15.0% | 1.0 | 23.6K | 20.4s | 41.2% | 76.5% | 47.1% | 69.3% |
| GraphRAG-style LEA | 20 | **0.0%** | 17.4 | 58.4K | 175.6s | 75.0% | **90.0%** | 40.0% | 51.5% |
| SA-MCGS | 20 | **0.0%** | 50.5 | 161.2K | 524.6s | **85.0%** | 85.0% | **75.0%** | 51.5% |

This table clarifies the tradeoff:

- **SA-MCGS is more expensive** than both Full-SCC Naive and LEA. We will state this directly.
- Full-SCC Naive is cheap but had **15.0% invalid outputs** in this audit and much lower Root@3 / Risk-all.
- LEA is a strong middle point: it removes invalid outputs and uses far fewer calls than SA-MCGS, but in this preliminary audit it does not preserve all endpoints as reliably as SA-MCGS.
- SA-MCGS gives the highest Root@3 and Risk-all in this sample, but at the cost of more rollout calls and higher runtime.

We will add both empirical and theoretical cost discussion. Conceptually, Full-SCC Naive has one large full-SCC prompt; LEA has deterministic local-window extraction and aggregation; SA-MCGS has rollout-budgeted local-window search with persistent evidence memory and transposition-style reuse. Thus the relevant practical comparison is not just accuracy, but **accuracy / reliability / endpoint completeness per call and per token**.

### 4. Scope, Natural Risks, and Societal-Impact Revisions

We also agree that the current benchmark should be framed more carefully. The benchmark is best described as a **controlled structural-risk stress test**, not as a direct sample of naturally occurring high-stakes risk distributions. The expert audit supports semantic recognizability of the injected structural risks, but it does not establish distributional equivalence with naturally occurring legal, regulatory, or software-dependency risks.

In the revision, we will:

- explicitly call the benchmark a controlled structural-risk stress test;
- weaken broad claims about direct high-stakes deployment;
- define **oracle-risk Naive** as a boosted full-SCC baseline selected using ground-truth risk metrics;
- add the new LEA baseline and component ablations;
- report cost / reliability alongside performance;
- state that SA-MCGS is a **decision-support tool**, not an automated risk adjudicator;
- discuss false positives, false negatives, graph-construction errors, and overtrust on naturally occurring cases as deployment risks.

### Overall Revised Claim

The new evidence leads us to a more precise and, we think, stronger claim:

> SA-MCGS is not uniformly superior to all graph-aware or strong-model baselines. Instead, its value is clearest when cyclic document SCCs require repeated, structure-aware evidence accumulation and endpoint-complete risk-subgraph construction. Compared with a strong graph-aware decomposed LEA baseline, SA-MCGS improves overall Risk-all by **13.1 points** and gpt-4o Risk-all by **31.2 points**, at the cost of more LLM calls. Component ablations show that critical-pair revisiting and dynamic/replacement core construction are central to these gains.

We appreciate the reviewers' suggestions because they substantially improved the empirical clarity of the paper. We will incorporate these tables and the more careful framing into the revised manuscript.

---

## 中文翻译

**评论标题：** 后续证据：组件级消融、图感知 baseline 与初步成本核算

再次感谢各位审稿人提出具体而有帮助的建议。在第一轮回复中，我们承认了三类需要补充证据的问题：**组件级消融**、**更公平的图感知分解式 baseline**，以及 **成本 / 可靠性核算**。我们现在已经完成了几组补充分析，下面汇总主要结果。

我们会把这些结果纳入修订稿。同时，我们也会修改论文表述，避免把结果写成“所有模型上都一致优越”，也不会把当前 benchmark 直接等同于 naturally occurring high-stakes risks。

### 新增证据总览

| 审稿人关切 | 当前新增证据 | 修订稿中的核心结论 |
|---|---|---|
| SA-MCGS 各组件分别贡献多少 | Stage 1 在 **80 个 gpt-4o cases** 上做搜索/记忆模块消融；Stage 2 在 **40 个 cases** 上做 dynamic-core 消融 | 证据最强的是 **critical-pair ledger/revisit** 和 **dynamic/replacement core construction**。随机 local-window 选择也会伤害 endpoint completeness。relation-first memory 在这个样本里不是单独主导因素，因此需要谨慎表述。 |
| baseline fairness / prompt decomposition 混杂 | 在 **160 个 matched cases** 上加入 **GraphRAG-style Local Evidence Aggregation (LEA)** baseline。LEA 使用图窗口检索和相同 local evidence schema，但不使用 SA-MCGS 的 memory/search/core 机制 | LEA 是很强的 baseline，尤其在 Gemini 2.5 Pro 上很强。但 SA-MCGS 在 overall endpoint completeness，特别是 Risk-all 上仍有优势。这说明 SCC-aware search 和 dynamic core construction 有价值，同时也确认 model-level behavior 并不均匀。 |
| 推理成本和可靠性 | 初步 **20-case low-concurrency cost audit**，覆盖 Full-SCC Naive、LEA 和 SA-MCGS，并报告 calls、tokens、runtime、invalid rate 和 performance metrics | SA-MCGS 成本确实更高，这一点我们会直接承认。但在该 audit 中，SA-MCGS 消除了 invalid-output failures，并提升 Root@3 / Risk-all。LEA 的调用数显著少于 SA-MCGS，是 cost-performance 上的中间点。更大的 40-case cost audit 仍在运行，最终表格会用其更新。 |

### 1. 图感知分解式 Baseline

为回应审稿人关于 Full-SCC Naive 对比可能混入 prompt decomposition 和 output-schema difficulty 的担忧，我们实现了一个 **GraphRAG-style Local Evidence Aggregation (LEA)** baseline。

LEA 使用 deterministic graph-window retrieval，并采用与 SA-MCGS 相同的 local evidence schema，然后通过透明的 aggregation 规则汇总结果。它**不使用** relation-first memory、critical-pair revisiting、OC/core signals、UCB-style rollout selection 或 dynamic-core replacement。因此，它可以更直接地检验：性能增益到底只是来自 local decomposition / graph-window prompting，还是来自 SA-MCGS 的 SCC-aware search 和 memory mechanisms。

| Group | N | LEA Root@3 | SA-MCGS Root@3 | Delta | LEA Risk-all | SA-MCGS Risk-all | Delta | LEA calls | SA-MCGS calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Overall | 160 | 83.8% | **86.9%** | +3.1 | 66.2% | **79.4%** | **+13.1** | 15.7 | 55.7 |
| Gemini 2.5 Pro | 80 | **88.8%** | 87.5% | -1.2 | **88.8%** | 83.8% | -5.0 | 14.9 | 53.0 |
| gpt-4o | 80 | 78.8% | **86.2%** | **+7.5** | 43.8% | **75.0%** | **+31.2** | 16.5 | 58.5 |
| Large SCCs | 40 | **85.0%** | 77.5% | -7.5 | 55.0% | **72.5%** | **+17.5** | 25.6 | 56.5 |
| Medium SCCs | 48 | 75.0% | **83.3%** | **+8.3** | 64.6% | **75.0%** | **+10.4** | 14.7 | 57.8 |
| Small SCCs | 72 | 88.9% | **94.4%** | **+5.6** | 73.6% | **86.1%** | **+12.5** | 10.8 | 54.0 |

这些结果让我们的结论更精确。LEA 的确很有竞争力，这证明审稿人的担忧是合理的：**structured graph-window decomposition 本身就是一个强 baseline，不能被简单忽略**。同时，SA-MCGS 在 **Risk-all** 这个严格的 endpoint-completeness 指标上仍然整体提升 **13.1 points**，在 **gpt-4o** 上提升 **31.2 points**。这说明，当模型需要通过反复的结构化证据积累而不是一次性局部聚合来保留完整 endpoints 时，SA-MCGS 的额外机制更有价值。

因此，我们会修改论文表述：不再声称 SA-MCGS 在所有模型和设置上都统一占优，而是改为说明：**SA-MCGS 在 cyclic long-context pressure 下提升 endpoint completeness 和 robustness；同时，强 decomposed baseline 或强 full-SCC model 在某些设置下也可以非常有竞争力**。

### 2. 组件级消融

我们也补充了组件级消融，用来隔离各模块的实际作用。

#### Stage 1：80 cases 上的搜索 / 记忆模块消融

| Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core size |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | 80 | 86.2% | **100.0%** | **75.0%** | 51.3% | 0.0 | 8.1 |
| No relation-first memory | 80 | **88.8%** | 98.8% | 80.0% | 51.8% | +5.0 | 8.0 |
| No critical-pair ledger/revisit | 80 | 83.8% | 88.8% | 53.8% | 72.0% | **-21.3** | 4.2 |
| Random local-window selection | 80 | 90.0% | 96.2% | 63.7% | 51.8% | **-11.3** | 8.0 |

Stage 1 最清楚的结果是：移除 **critical-pair ledger/revisit** 后，endpoint completeness 明显下降，Risk-all 从 **75.0% 降到 53.8%**。随机 local-window selection 也会把 Risk-all 从 **75.0% 降到 63.7%**，说明 graph-guided selection policy 的作用不只是“重复 local prompting”。

relation-first memory 的结果更复杂：在这个 gpt-4o 样本中，移除该模块并没有降低 aggregate Risk-all。因此我们不会把它写成单独的主导模块，而会把它描述为 evidence organization mechanism 的一部分，其作用可能与模型和设置有关。

SCC-size breakdown 进一步支持 critical-pair revisiting 的重要性。在 large SCCs 中，移除 critical-pair ledger/revisit 后，Risk-all 从 **58.3% 降到 16.7%**，下降 **41.7 points**。

#### Stage 2：40 cases 上的 Dynamic-Core 消融

| Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core size |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | 40 | **85.0%** | **100.0%** | **70.0%** | 52.1% | 0.0 | 10.0 |
| No OC/core signal | 40 | **85.0%** | **100.0%** | 60.0% | 52.2% | -10.0 | 9.7 |
| Monotone core | 40 | 77.5% | 87.5% | 45.0% | 76.1% | **-25.0** | 4.8 |
| No pair closure in final core | 40 | 80.0% | 95.0% | 67.5% | 53.0% | -2.5 | 9.4 |

Dynamic-core 消融显示：如果用 monotone accumulation 替代 dynamic/replacement core，endpoint completeness 会显著下降，Risk-all 从 **70.0% 降到 45.0%**。移除 OC/core signals 也使 Risk-all 下降 **10.0 points**；而禁用 final pair closure 在这个样本中的影响较小。

因此，我们会在修订稿中重点强调证据最强的模块：**critical-pair ledger/revisit**、**graph-guided local-window selection** 和 **dynamic/replacement core construction**。

### 3. 初步成本与可靠性核算

我们同意审稿人关于 practical inference cost 必须显式报告的意见。因此，我们进行了一个 low-concurrency cost audit，记录 provider-observed input tokens、output tokens、total tokens、API calls、runtime、invalid-output rate 和 performance。

当前 frozen audit 覆盖 20 个 cases，并在同一套 accounting framework 下比较 Full-SCC Naive、LEA 和 SA-MCGS。我们也正在运行更大的 40-case audit，最终成本表会根据其结果更新。

| Method | Cases | Invalid | Calls / case | Total tokens / case | Runtime / case | Root@3 | Risk-any | Risk-all | Compression |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full-SCC Naive | 20 | 15.0% | 1.0 | 23.6K | 20.4s | 41.2% | 76.5% | 47.1% | 69.3% |
| GraphRAG-style LEA | 20 | **0.0%** | 17.4 | 58.4K | 175.6s | 75.0% | **90.0%** | 40.0% | 51.5% |
| SA-MCGS | 20 | **0.0%** | 50.5 | 161.2K | 524.6s | **85.0%** | 85.0% | **75.0%** | 51.5% |

这张表澄清了 tradeoff：

- **SA-MCGS 的成本确实更高**，高于 Full-SCC Naive 和 LEA；我们会直接承认这一点。
- Full-SCC Naive 成本最低，但在该 audit 中有 **15.0% invalid outputs**，并且 Root@3 / Risk-all 明显较低。
- LEA 是一个很强的中间点：它消除了 invalid outputs，调用次数也远少于 SA-MCGS；但在该初步 audit 中，它对完整 endpoints 的保留不如 SA-MCGS 稳定。
- SA-MCGS 在该样本中有最高的 Root@3 和 Risk-all，但代价是更多 rollout calls 和更高 runtime。

我们会加入实测成本和理论复杂度两部分讨论。概念上，Full-SCC Naive 是一次大的 full-SCC prompt；LEA 是 deterministic local-window extraction + aggregation；SA-MCGS 是带 rollout budget 的 local-window search，并带有 persistent evidence memory 和 transposition-style reuse。因此，真正有意义的实践对比不只是 accuracy，而是 **每次调用 / 每个 token 下的 accuracy、reliability 和 endpoint completeness**。

### 4. Scope、Naturally Occurring Risks 和 Societal Impact 的修订

我们也同意当前 benchmark 的定位需要更谨慎。这个 benchmark 最准确的说法是一个 **controlled structural-risk stress test**，而不是 naturally occurring high-stakes risk distribution 的直接样本。Expert audit 支持的是 injected structural risks 在语义上可被专业读者识别，但并不能证明它们与真实法律、监管或软件依赖风险具有相同分布。

在修订稿中，我们会：

- 明确把 benchmark 称为 controlled structural-risk stress test；
- 弱化关于直接 high-stakes deployment 的宽泛表述；
- 明确定义 **oracle-risk Naive** 是一个由 ground-truth risk metrics 选择的 boosted full-SCC baseline；
- 加入新的 LEA baseline 和组件级消融；
- 把 cost / reliability 与 performance 一起报告；
- 明确 SA-MCGS 是 **decision-support tool**，不是 automated risk adjudicator；
- 讨论 false positives、false negatives、graph-construction errors，以及用户可能因为 injected-benchmark performance 而对 naturally occurring cases 产生 overtrust 的风险。

### 修订后的总体结论

新增证据使我们的结论更精确，也更稳健：

> SA-MCGS 并不是在所有 graph-aware 或 strong-model baselines 上都统一优越。它的价值最清楚地体现在 cyclic document SCCs 需要反复的结构感知证据积累，以及需要构造 endpoint-complete risk subgraph 的场景中。与强 graph-aware decomposed LEA baseline 相比，SA-MCGS 在 overall Risk-all 上提升 **13.1 points**，在 gpt-4o Risk-all 上提升 **31.2 points**，代价是更多 LLM calls。组件级消融显示，critical-pair revisiting 和 dynamic/replacement core construction 是这些增益的核心来源。

我们感谢审稿人的建议，因为这些建议显著提升了论文实验证据的清晰度。我们会把这些表格和更谨慎的 framing 纳入修订稿。

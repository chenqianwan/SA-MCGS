# Round-2 Discussion Response Draft v2

Working draft for EMNLP 2026 discussion. This version incorporates the completed 40-case cost audit on **gpt-4o** and **Gemini 2.5 Flash**, the graph-aware LEA baseline, and the component ablations. The English draft is reviewer-facing; the Chinese translation follows for internal checking.

---

## English Draft

**Comment title:** Additional evidence: graph-aware baseline, component ablations, and completed cost accounting

Thank you again for the careful and constructive reviews. In our initial response, we identified three gaps that required additional evidence: **(i) component-level ablations**, **(ii) a fairer graph-aware decomposed baseline**, and **(iii) inference cost / reliability accounting**. We have now completed these follow-up analyses and will incorporate them into the revision.

The new results lead to a more precise claim. SA-MCGS is **not uniformly superior across every model and metric**. A strong graph-aware decomposed baseline is highly competitive, and on Gemini 2.5 Pro it is even stronger on Risk-all. However, SA-MCGS improves endpoint completeness overall and is especially helpful on gpt-4o and Gemini 2.5 Flash. We will revise the paper to emphasize this model-level non-uniformity rather than overclaiming uniform dominance.

### Summary of New Evidence

| Reviewer concern | New evidence | Revision takeaway |
|---|---|---|
| Baseline fairness / prompt-decomposition confound | Added a **GraphRAG-style Local Evidence Aggregation (LEA)** baseline on **160 matched cases**, plus an additional **40-case Gemini 2.5 Flash cost-audit slice** | LEA is a strong graph-aware baseline. SA-MCGS improves overall endpoint completeness, but behavior is model-dependent. |
| Component-level contribution | Added **Stage 1 ablations on 80 cases** and **Stage 2 dynamic-core ablations on 40 cases** | Strongest support is for **critical-pair ledger/revisit**, **graph-guided local-window selection**, and **dynamic/replacement core construction**. Relation memory and final pair closure should be framed cautiously. |
| Inference cost and reliability | Completed **40-case low-rollout cost audits** on gpt-4o and Gemini 2.5 Flash for Naive / LEA / SA-MCGS | SA-MCGS costs more calls/tokens, but improves strict endpoint completeness. LEA is an important lower-cost middle point. Runtime is measured at low rollout / low concurrency and can be parallelized. |

### 1. Graph-Aware Decomposed Baseline

To address the concern that the original Full-SCC Naive baseline may confound method quality with prompt decomposition and output-schema difficulty, we implemented a **GraphRAG-style Local Evidence Aggregation (LEA)** baseline.

LEA uses deterministic graph-window retrieval and the same local evidence schema as SA-MCGS, followed by transparent aggregation. It does **not** use relation-first memory, critical-pair revisiting, OC/core signals, rollout selection, or dynamic-core replacement. This makes it a stronger test of whether the gains come merely from local decomposition / graph-window prompting, or from the SCC-aware search and memory mechanisms in SA-MCGS.

| Group | N | LEA Root@3 | SA Root@3 | Delta | LEA Risk-all | SA Risk-all | Delta | LEA calls | SA calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Matched overall | 160 | 83.8% | **86.9%** | +3.1 | 66.2% | **79.4%** | **+13.1** | 15.7 | 55.7 |
| Gemini 2.5 Pro | 80 | **88.8%** | 87.5% | -1.2 | **88.8%** | 83.8% | -5.0 | 14.9 | 53.0 |
| gpt-4o | 80 | 78.8% | **86.2%** | **+7.5** | 43.8% | **75.0%** | **+31.2** | 16.5 | 58.5 |
| Gemini 2.5 Flash cost audit | 40 | 82.5% | **92.5%** | **+10.0** | 65.0% | **95.0%** | **+30.0** | 15.6 | 45.9 |
| Large SCCs | 40 | **85.0%** | 77.5% | -7.5 | 55.0% | **72.5%** | **+17.5** | 25.6 | 56.5 |
| Medium SCCs | 48 | 75.0% | **83.3%** | **+8.3** | 64.6% | **75.0%** | **+10.4** | 14.7 | 57.8 |
| Small SCCs | 72 | 88.9% | **94.4%** | **+5.6** | 73.6% | **86.1%** | **+12.5** | 10.8 | 54.0 |

The Gemini 2.5 Flash row is an additional **40-case cost-audit slice**, not part of the matched 160-case aggregate. We include it because the reviewer concern is model-dependent: on Gemini 2.5 Pro, LEA is slightly better on Risk-all, while on gpt-4o and Gemini 2.5 Flash, SA-MCGS improves Risk-all by **31.2** and **30.0** points, respectively.

Thus, the fairer conclusion is not "SA-MCGS always dominates." Rather, **LEA validates the reviewers' baseline-fairness concern**, and SA-MCGS is most useful when the model benefits from repeated structured evidence accumulation and endpoint-complete subgraph construction.

### 2. Component-Level Ablations

We added component-level ablations to identify which modules are most responsible for the gains.

#### Stage 1: Search / Memory Ablations on 80 Cases

| Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | 80 | 86.2% | **100.0%** | **75.0%** | 51.3% | 0.0 | 8.1 |
| No relation-first memory | 80 | 88.8% | 98.8% | 80.0% | 51.8% | +5.0 | 8.0 |
| No critical-pair ledger/revisit | 80 | 83.8% | 88.8% | 53.8% | 72.0% | **-21.3** | 4.2 |
| Random local-window selection | 80 | **90.0%** | 96.2% | 63.7% | 51.8% | **-11.3** | 8.0 |

The clearest Stage-1 result is that removing the **critical-pair ledger/revisit** mechanism substantially reduces endpoint completeness: Risk-all drops from **75.0% to 53.8%**. Random local-window selection also lowers Risk-all from **75.0% to 63.7%**, suggesting that graph-guided selection matters beyond simply repeating local prompts.

The relation-first memory ablation is more nuanced: in this sample, removing it does not reduce aggregate Risk-all. We therefore will not overstate it as independently dominant. Instead, we will frame relation memory as part of the evidence organization mechanism whose effect can be model- and setting-dependent.

#### Stage 2: Dynamic-Core Ablations on 40 Cases

| Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | 40 | **85.0%** | **100.0%** | **70.0%** | 52.1% | 0.0 | 10.0 |
| No OC/core signal | 40 | **85.0%** | **100.0%** | 60.0% | 52.2% | **-10.0** | 9.7 |
| Monotone core | 40 | 77.5% | 87.5% | 45.0% | 76.1% | **-25.0** | 4.8 |
| No pair closure in final core | 40 | 80.0% | 95.0% | 67.5% | 53.0% | -2.5 | 9.4 |

The Stage-2 ablation shows that replacing the dynamic/replacement core with monotone accumulation strongly hurts endpoint completeness: Risk-all drops from **70.0% to 45.0%**. Removing OC/core signals reduces Risk-all by **10.0** points. Final pair closure has a smaller effect in this sample and will be framed cautiously.

### 3. Completed Cost and Reliability Accounting

We agree with the reviewers that practical inference cost must be reported explicitly. We therefore ran completed 40-case low-rollout cost audits on **gpt-4o** and **Gemini 2.5 Flash**, measuring calls, input/output tokens, total tokens, wall-clock runtime, invalid-output rate, and performance.

#### gpt-4o 40-case audit

| Method | Cases | Invalid | Calls / case | Total tokens / case | Runtime / case | Root@3 | Risk-any | Risk-all |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Full-SCC Naive | 40 | 15.0% | 1.0 | 18.2K on valid outputs | 17.7s on valid outputs | 29.4% | 73.5% | 29.4% |
| LEA | 40 | **0.0%** | 16.7 | 58.8K | 162.7s | 75.0% | 90.0% | 42.5% |
| SA-MCGS | 40 | **0.0%** | 48.9 | 163.6K | 498.1s | **87.5%** | **92.5%** | **77.5%** |

For gpt-4o Naive, 6/40 outputs were invalid; the displayed Naive performance is computed on the 34 valid outputs in the current summary. Treating invalid outputs as failures would only strengthen the reliability conclusion.

#### Gemini 2.5 Flash 40-case audit

| Method | Cases | Invalid | Calls / case | Total tokens / case | Runtime / case | Root@3 | Risk-any | Risk-all |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Full-SCC Naive | 40 | **0.0%** | 1.0 | 26.6K | 9.4s | 75.0% | 87.5% | 57.5% |
| LEA | 40 | **0.0%** | 15.6 | 53.2K | 54.9s | 82.5% | **100.0%** | 65.0% |
| SA-MCGS | 40 | **0.0%** | 45.9 | 148.2K | 164.5s | **92.5%** | **100.0%** | **95.0%** |

These results clarify the cost-performance tradeoff. **SA-MCGS is more expensive** than LEA and Naive in calls and tokens. However, it substantially improves strict endpoint completeness, especially on Risk-all. LEA is a strong lower-cost middle point: it uses roughly one third of the calls of SA-MCGS and is competitive on several metrics, but it does not preserve all endpoints as reliably on gpt-4o and Gemini 2.5 Flash.

Runtime should also be interpreted carefully. These audits use low rollout / low concurrency, so wall-clock time is conservative and not a fixed lower bound. We will add an explicit parallelizable-time discussion:

```text
T_wall(c_parallel) ~= T_serial + T_LLM / c_parallel
c_parallel = min(C_rollout, C_worker, C_api)
```

Increasing effective rollout concurrency can reduce the parallel LLM-call portion by multiples, subject to worker and API-rate limits. Token count and call count remain the accounting costs.

### 4. Scope and Societal-Impact Revisions

We also agree that the current benchmark should be framed more carefully. The benchmark is best described as a **controlled structural-risk stress test**, not as a direct sample of naturally occurring high-stakes risk distributions. The expert audit supports semantic recognizability of the injected structural risks, but it does not establish distributional equivalence with naturally occurring legal, regulatory, or software-dependency risks.

In the revision, we will:

- explicitly describe the benchmark as a controlled structural-risk stress test;
- weaken broad claims about direct high-stakes deployment;
- define oracle-risk Naive as a boosted full-SCC baseline selected using ground-truth risk metrics;
- add the LEA baseline and component ablations;
- report calls, tokens, runtime, invalid outputs, and performance together;
- describe SA-MCGS as a **decision-support tool**, not an automated risk adjudicator;
- discuss false positives, false negatives, graph-construction errors, and overtrust risks on naturally occurring cases.

### Revised Overall Claim

The new evidence supports a narrower and stronger claim:

> SA-MCGS is not uniformly superior to all graph-aware or strong-model baselines. Its clearest value is in cyclic document SCCs where repeated structure-aware evidence accumulation is needed to preserve endpoint-complete risk subgraphs. Compared with a strong graph-aware decomposed LEA baseline, SA-MCGS improves matched overall Risk-all by **13.1 points**, gpt-4o Risk-all by **31.2 points**, and an additional Gemini 2.5 Flash cost-audit slice by **30.0 points**, while using more calls and tokens. Component ablations show that critical-pair revisiting and dynamic/replacement core construction are the best-supported mechanisms.

We appreciate the reviewers' suggestions; they led us to add stronger baselines, clearer ablations, and explicit cost accounting. We will incorporate these results and the more careful framing into the revised manuscript.

---

## 中文翻译

**评论标题：** 补充证据：图感知 baseline、组件级消融与完整成本核算

再次感谢各位审稿人的仔细和建设性意见。在第一轮回复中，我们指出有三类证据需要补充：**(i) 组件级消融**、**(ii) 更公平的图感知分解式 baseline**，以及 **(iii) 推理成本 / 可靠性核算**。现在这些补充分析已经完成，我们会把它们纳入修订稿。

新的结果让我们的主张更精确。SA-MCGS **并不是在每个模型和每个指标上都一致优越**。一个强的 graph-aware decomposed baseline 本身非常有竞争力，并且在 Gemini 2.5 Pro 上 Risk-all 甚至更高。不过，SA-MCGS 在 overall endpoint completeness 上仍有优势，并且在 gpt-4o 和 Gemini 2.5 Flash 上尤其明显。我们会在修订稿中强调这种 model-level non-uniformity，而不是过度声称统一优势。

### 新增证据总览

| 审稿人关切 | 新增证据 | 修订稿结论 |
|---|---|---|
| Baseline fairness / prompt decomposition 混杂 | 在 **160 个 matched cases** 上加入 **GraphRAG-style Local Evidence Aggregation (LEA)** baseline，并额外加入 **40-case Gemini 2.5 Flash cost-audit slice** | LEA 是强 graph-aware baseline。SA-MCGS 提升 overall endpoint completeness，但表现具有模型依赖性。 |
| 组件贡献 | **80 cases Stage 1 消融** 和 **40 cases Stage 2 dynamic-core 消融** | 证据最强的是 **critical-pair ledger/revisit**、**graph-guided local-window selection** 和 **dynamic/replacement core construction**。Relation memory 和 final pair closure 需要谨慎表述。 |
| 推理成本和可靠性 | 完成 gpt-4o 与 Gemini 2.5 Flash 上的 **40-case low-rollout cost audits**，比较 Naive / LEA / SA-MCGS | SA-MCGS 的 calls/tokens 成本更高，但严格 endpoint completeness 更好。LEA 是重要的低成本中间点。Runtime 来自低 rollout / 低并发设置，可通过并行优化。 |

### 1. 图感知分解式 Baseline

为回应审稿人关于 Full-SCC Naive baseline 可能混入 prompt decomposition 和 output-schema difficulty 的担忧，我们实现了一个 **GraphRAG-style Local Evidence Aggregation (LEA)** baseline。

LEA 使用 deterministic graph-window retrieval，并采用与 SA-MCGS 相同的 local evidence schema，然后通过透明 aggregation 汇总结果。它**不使用** relation-first memory、critical-pair revisiting、OC/core signals、rollout selection 或 dynamic-core replacement。因此，它能更直接地检验：增益究竟只是来自 local decomposition / graph-window prompting，还是来自 SA-MCGS 的 SCC-aware search 和 memory mechanisms。

| Group | N | LEA Root@3 | SA Root@3 | Delta | LEA Risk-all | SA Risk-all | Delta | LEA calls | SA calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Matched overall | 160 | 83.8% | **86.9%** | +3.1 | 66.2% | **79.4%** | **+13.1** | 15.7 | 55.7 |
| Gemini 2.5 Pro | 80 | **88.8%** | 87.5% | -1.2 | **88.8%** | 83.8% | -5.0 | 14.9 | 53.0 |
| gpt-4o | 80 | 78.8% | **86.2%** | **+7.5** | 43.8% | **75.0%** | **+31.2** | 16.5 | 58.5 |
| Gemini 2.5 Flash cost audit | 40 | 82.5% | **92.5%** | **+10.0** | 65.0% | **95.0%** | **+30.0** | 15.6 | 45.9 |
| Large SCCs | 40 | **85.0%** | 77.5% | -7.5 | 55.0% | **72.5%** | **+17.5** | 25.6 | 56.5 |
| Medium SCCs | 48 | 75.0% | **83.3%** | **+8.3** | 64.6% | **75.0%** | **+10.4** | 14.7 | 57.8 |
| Small SCCs | 72 | 88.9% | **94.4%** | **+5.6** | 73.6% | **86.1%** | **+12.5** | 10.8 | 54.0 |

Gemini 2.5 Flash 这一行是额外的 **40-case cost-audit slice**，不计入 matched 160-case aggregate。我们加入它，是因为 reviewer 关心的问题本身与模型强相关：在 Gemini 2.5 Pro 上 LEA 的 Risk-all 略高；但在 gpt-4o 和 Gemini 2.5 Flash 上，SA-MCGS 的 Risk-all 分别提升 **31.2** 和 **30.0** points。

因此，更公平的结论不是“SA-MCGS 总是胜出”。相反，**LEA 证明审稿人关于 baseline fairness 的担忧是成立的**；而 SA-MCGS 的价值主要体现在模型需要反复结构化证据积累、并构造 endpoint-complete subgraph 的场景中。

### 2. 组件级消融

我们补充了组件级消融，用来识别哪些模块最主要地贡献了增益。

#### Stage 1：80 cases 上的搜索 / 记忆消融

| Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | 80 | 86.2% | **100.0%** | **75.0%** | 51.3% | 0.0 | 8.1 |
| No relation-first memory | 80 | 88.8% | 98.8% | 80.0% | 51.8% | +5.0 | 8.0 |
| No critical-pair ledger/revisit | 80 | 83.8% | 88.8% | 53.8% | 72.0% | **-21.3** | 4.2 |
| Random local-window selection | 80 | **90.0%** | 96.2% | 63.7% | 51.8% | **-11.3** | 8.0 |

Stage 1 最清楚的结果是：移除 **critical-pair ledger/revisit** 会显著降低 endpoint completeness，Risk-all 从 **75.0% 降到 53.8%**。随机 local-window selection 也会把 Risk-all 从 **75.0% 降到 63.7%**，说明 graph-guided selection 的作用不只是“重复 local prompts”。

Relation-first memory 的结果更复杂：在这个样本里，移除它并没有降低 aggregate Risk-all。因此我们不会把它写成单独主导模块，而会把 relation memory 表述为 evidence organization mechanism 的一部分，其效果可能与模型和设置有关。

#### Stage 2：40 cases 上的 Dynamic-Core 消融

| Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Risk-all | Avg core |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full SA-MCGS | 40 | **85.0%** | **100.0%** | **70.0%** | 52.1% | 0.0 | 10.0 |
| No OC/core signal | 40 | **85.0%** | **100.0%** | 60.0% | 52.2% | **-10.0** | 9.7 |
| Monotone core | 40 | 77.5% | 87.5% | 45.0% | 76.1% | **-25.0** | 4.8 |
| No pair closure in final core | 40 | 80.0% | 95.0% | 67.5% | 53.0% | -2.5 | 9.4 |

Stage 2 消融显示，如果用 monotone accumulation 替代 dynamic/replacement core，endpoint completeness 会显著下降：Risk-all 从 **70.0% 降到 45.0%**。移除 OC/core signals 也会使 Risk-all 下降 **10.0** points。Final pair closure 在该样本中的影响较小，因此需要谨慎表述。

### 3. 完整成本与可靠性核算

我们同意审稿人关于 practical inference cost 必须显式报告的意见。因此，我们在 **gpt-4o** 和 **Gemini 2.5 Flash** 上完成了 40-case low-rollout cost audits，记录 calls、input/output tokens、total tokens、wall-clock runtime、invalid-output rate 和 performance。

#### gpt-4o 40-case audit

| Method | Cases | Invalid | Calls / case | Total tokens / case | Runtime / case | Root@3 | Risk-any | Risk-all |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Full-SCC Naive | 40 | 15.0% | 1.0 | valid outputs 上 18.2K | valid outputs 上 17.7s | 29.4% | 73.5% | 29.4% |
| LEA | 40 | **0.0%** | 16.7 | 58.8K | 162.7s | 75.0% | 90.0% | 42.5% |
| SA-MCGS | 40 | **0.0%** | 48.9 | 163.6K | 498.1s | **87.5%** | **92.5%** | **77.5%** |

对 gpt-4o Naive 来说，40 个输出中有 6 个 invalid；表中 Naive 的 performance 是当前 summary 对 34 个 valid outputs 的计算结果。如果把 invalid outputs 直接视为失败，则可靠性方面的结论只会更强。

#### Gemini 2.5 Flash 40-case audit

| Method | Cases | Invalid | Calls / case | Total tokens / case | Runtime / case | Root@3 | Risk-any | Risk-all |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Full-SCC Naive | 40 | **0.0%** | 1.0 | 26.6K | 9.4s | 75.0% | 87.5% | 57.5% |
| LEA | 40 | **0.0%** | 15.6 | 53.2K | 54.9s | 82.5% | **100.0%** | 65.0% |
| SA-MCGS | 40 | **0.0%** | 45.9 | 148.2K | 164.5s | **92.5%** | **100.0%** | **95.0%** |

这些结果澄清了 cost-performance tradeoff。**SA-MCGS 的 calls 和 tokens 成本更高**。不过，它显著提升了严格的 endpoint completeness，尤其是 Risk-all。LEA 是一个强 lower-cost middle point：它的调用数大约是 SA-MCGS 的三分之一，并且在若干指标上很有竞争力；但在 gpt-4o 和 Gemini 2.5 Flash 上，它对完整 endpoints 的保留不如 SA-MCGS 稳定。

Runtime 也需要谨慎解释。这些 audit 使用 low rollout / low concurrency，因此 wall-clock time 是偏保守测量，不是固定下界。我们会加入明确的并行时间讨论：

```text
T_wall(c_parallel) ~= T_serial + T_LLM / c_parallel
c_parallel = min(C_rollout, C_worker, C_api)
```

增大有效 rollout 并发可以在 worker 和 API-rate 限制内近似按倍数缩短可并行的 LLM-call 部分。Token count 和 call count 仍然是实际成本核算口径。

### 4. Scope 和 Societal Impact 修订

我们也同意当前 benchmark 的定位需要更谨慎。这个 benchmark 最准确的说法是 **controlled structural-risk stress test**，而不是 naturally occurring high-stakes risk distribution 的直接样本。Expert audit 支持 injected structural risks 在语义上可被专业读者识别，但不能证明其与真实法律、监管或软件依赖风险具有相同分布。

在修订稿中，我们会：

- 明确把 benchmark 描述为 controlled structural-risk stress test；
- 弱化直接 high-stakes deployment 的宽泛表述；
- 定义 oracle-risk Naive 为一个由 ground-truth risk metrics 选择的 boosted full-SCC baseline；
- 加入 LEA baseline 和组件级消融；
- 一起报告 calls、tokens、runtime、invalid outputs 和 performance；
- 把 SA-MCGS 描述为 **decision-support tool**，不是 automated risk adjudicator；
- 讨论 false positives、false negatives、graph-construction errors，以及在 naturally occurring cases 上的 overtrust 风险。

### 修订后的总体主张

新增证据支持一个更窄但更稳健的主张：

> SA-MCGS 并不是在所有 graph-aware 或 strong-model baselines 上都统一优越。它最清楚的价值在于 cyclic document SCCs 需要反复结构感知证据积累，以保留 endpoint-complete risk subgraphs 的场景。与强 graph-aware decomposed LEA baseline 相比，SA-MCGS 在 matched overall Risk-all 上提升 **13.1 points**，在 gpt-4o Risk-all 上提升 **31.2 points**，并在额外的 Gemini 2.5 Flash cost-audit slice 上提升 **30.0 points**，代价是更多 calls 和 tokens。组件级消融显示，critical-pair revisiting 和 dynamic/replacement core construction 是证据最强的机制。

我们感谢审稿人的建议；这些建议促使我们加入更强 baseline、更清楚的消融和显式成本核算。我们会把这些结果和更谨慎的 framing 纳入修订稿。

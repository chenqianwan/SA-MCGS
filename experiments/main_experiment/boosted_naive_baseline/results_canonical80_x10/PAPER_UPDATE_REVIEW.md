# Paper 更新逐项核对：oracle-risk Naive baseline

本文件用于逐项核对本轮 paper 更新。核心口径是：正文 baseline 从 one-shot Naive 切到 `boosted Naive oracle_risk_top3`，图例写作 `oracle-risk Naive`；`self_top3` 和 `oracle_compression_top3` 放附录。

## 0. 范围说明

- 论文源文件：[`paper/latex/acl_latex.tex`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex)
- 主图/表生成脚本：[`experiments/main_experiment/build_paper_assets.py`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/build_paper_assets.py)
- 论文 PDF：[`paper/latex/acl_latex.pdf`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.pdf)
- 本文件列出需要人工核对的论文落字、表格落字和图片资产。
- `boosted_naive_raw_attempts.jsonl`、`boosted_naive_top3_summary.csv`、`boosted_naive_round_robin_status.json` 是实验原始/汇总数据，不在这里逐行展开；下面只列论文会引用到的数字。
- `submission/` 是打包副本，不作为核对源文件；确认正文和图片后再决定是否重新打包。
- 当前 diff 里还包含 title 变化。它不属于 oracle-risk 口径核心，但我在第 2 节也列出来，方便你确认是否保留。

## 1. 新主口径

| 项 | 当前写法 |
|---|---|
| 正文 Naive baseline | `oracle-risk Naive` |
| 对应 selector | `oracle_risk_top3` |
| selector 含义 | 从 10 次 full-SCC Naive attempts 中，用 `Root@3 / Risk-any / Risk-all` 风险优先 oracle 选 Top-3 |
| 主 Figure 3 | 只画 `oracle-risk Naive` vs `SA-MCGS` |
| 附录 selector 表 | 保留 `one-shot Naive`、`single-attempt mean`、`self_top3`、`oracle_risk_top3`、`oracle_compression_top3`、`SA-MCGS` |
| 错误解释 | 长 full-SCC context 加完整 global ranking / risk subgraph 输出负担，导致 timeout 或 ranking 缺失、重复、非法等解析崩坏 |

主结果数字：

| Method | N | Root@3 | Risk-any | Risk-all | Compression |
|---|---:|---:|---:|---:|---:|
| oracle-risk Naive | 320 | 58% | 79% | 62% | 60% |
| SA-MCGS | 320 | 81% | 98% | 78% | 53% |

对应 gain：

| Metric | oracle-risk Naive | SA-MCGS | Gain |
|---|---:|---:|---:|
| Root@3 | 58% | 81% | +23 |
| Risk-any | 79% | 98% | +19 |
| Risk-all | 62% | 78% | +16 |
| Compression | 60% | 53% | SA-MCGS 更少压缩，作为 retention trade-off 解释 |

## 2. `acl_latex.tex` 正文与附录落字

### 2.1 Title

位置：[`acl_latex.tex:46`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:46)

```latex
\title{Risk Subgraph Extraction in Cyclic Document Graphs\\
with Structure-Aware Monte Carlo Search}
```

核对备注：这个 title 变化在当前 diff 里存在，但不是 oracle-risk baseline 更新的必要项。

### 2.2 Abstract

位置：[`acl_latex.tex:55`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:55)

```latex
Long documents such as contracts, statutes, software package metadata, and corporate filings often contain risks that emerge only across mutually dependent records.  LLM-guided Monte Carlo tree search (MCTS) can improve structured document reasoning, but standard tree rollouts become unstable on strongly connected components (SCCs), where the same logical record may be revisited indefinitely.  We propose \samcgs{}, a structure-aware Monte Carlo graph search method that localizes SCCs, performs local LLM rollouts with relation-first evidence memory, and collapses each cyclic region into an inspectable risk subgraph.  We evaluate a locked critical structural benchmark covering four authority-backed domains: Debian dependencies, SEC EX-21 subsidiary disclosures, German Civil Code cross-references, and CUAD contracts.  Across 320 model-case pairs and four LLMs, \samcgs{} improves \rootthree{} from 58\% to 81\%, \riskany{} from 79\% to 98\%, and \riskall{} from 62\% to 78\% over an oracle-risk Top-3 full-\scc{} \naive{} baseline selected from ten attempts.  The gains are larger under long-context pressure, and the returned subgraphs retain core evidence while removing more than half of the original SCC nodes.
```

### 2.3 Contribution bullet

位置：[`acl_latex.tex:87`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:87)

```latex
\item We build a frozen critical-stress benchmark from four authority-backed sources. Debian provides package-dependency graphs, SEC EX-21 provides subsidiary-disclosure graphs, the German Civil Code (BGB) provides statutory cross-reference graphs, and CUAD provides contract-clause graphs. The benchmark contains 320 model-case pairs evaluated with GPT-4o, DeepSeek-V3, Qwen2.5-72B, and Gemini 2.5 Pro. Across these settings, \samcgs{} improves \rootthree{}, \riskany{}, and \riskall{} over an oracle-risk full-\scc{} direct-subgraph baseline. It also makes the retention cost visible through an explicit compression metric.
```

### 2.4 Domain formatting / shared semantics

位置：[`acl_latex.tex:300`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:300)

```latex
to serialize records, expose typed directed edges, and normalize model outputs.  These formatters do not define the target risk type and do not reveal the injected endpoints.  Both \naive{} and \samcgs{} use the same risk rubric that is neutral across domains.  Under this rubric, models flag structural inconsistency or mutual incompatibility, as well as risks that are underspecified or have high impact, using only visible node text and directed edges.  The comparison is therefore computational, contrasting full-\scc{} direct-subgraph generation and Top-3 aggregation with \scc{}-aware rollout selection, relation-first memory, critical-pair revisiting, and dynamic-core compression.
```

### 2.5 Baselines and models

位置：[`acl_latex.tex:308`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:308)

```latex
We use oracle-risk \naive{} as the main baseline. It runs the full-\scc{} direct-subgraph prompt ten times. From these attempts, a risk-prioritized oracle chooses the reported Top-3 set using \rootthree{}, \riskany{}, and \riskall{}. Each \naive{} attempt sees the full \scc{} and emits a whole-\scc{} ranking plus a risk subgraph; Appendix~\ref{sec:appendix_experiments} reports non-oracle and compression-first variants. \samcgs{} instead sees smaller local windows over 60 rollouts and aggregates evidence into a dynamic core.
```

位置：[`acl_latex.tex:310`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:310)

```latex
We evaluate GPT-4o, DeepSeek-V3, Qwen2.5-72B-Instruct, and Gemini 2.5 Pro.  The main comparison contains 320 model-case pairs per method; oracle-risk \naive{} is selected from 3,200 raw full-\scc{} attempts.  This gives boosted \naive{} a total token budget comparable to \samcgs{}.
```

### 2.6 Figure 3 caption

位置：[`acl_latex.tex:318`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:318)

```latex
\caption{Main critical-\scc{} results on 320 model-case pairs per method.  Panel A compares \samcgs{} with oracle-risk \naive{}, an oracle-risk Top-3 selection over ten full-\scc{} attempts; Panel B gives a compact \scc{}-size breakdown of endpoint retention and compression.}
```

### 2.7 Main Results 段落

位置：[`acl_latex.tex:322`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:322)

```latex
Figure~\ref{fig:main_metrics} shows the core result.  Against oracle-risk \naive{}, \samcgs{} improves \rootthree{} by 23 points, \riskany{} by 19 points, and \riskall{} by 16 points.  The strongest claim is not that full-\scc{} prompting never finds risk, since the baseline is already selected from ten attempts with access to risk metrics.  Improvement from \samcgs{} is more reliable preservation of the repair-relevant evidence endpoints in the final subgraph.
```

位置：[`acl_latex.tex:324`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:324)

```latex
The compression axis should be read as a trade-off, not a loss.  Oracle-risk \naive{} is slightly more compressed on average, but still retains all critical endpoints less often.  \samcgs{} deliberately keeps a larger dynamic core when evidence persists across rollouts.
```

位置：[`acl_latex.tex:326`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:326)

```latex
Appendix~\ref{tab:reliability} separates one-shot output availability from boosted raw-attempt and model-case reliability.
```

### 2.8 Breakdown by model and domain

位置：[`acl_latex.tex:330`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:330)

```latex
The gains are not carried by a single model.  Gemini 2.5 Pro and DeepSeek-V3 are strong even under oracle-risk \naive{}, while GPT-4o and Qwen2.5-72B still lag in complete endpoint retention.  Domain-wise, CUAD is the hardest setting: long contract components create both context pressure and output-schema burden for full-\scc{} ranking and subgraph generation.
```

### 2.9 Effect of SCC size

位置：[`acl_latex.tex:337`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:337)

```latex
Figure~\ref{fig:main_metrics}B separates the results by \scc{} size.  In short components ($\leq 12$ nodes), \samcgs{} improves \riskall{} from 79\% to 83\%.  In mid-sized components (14--20 nodes), the improvement is 47\% to 80\%.  In long components ($\geq 24$ nodes), \riskall{} remains difficult, but \samcgs{} still improves 50\% to 65\%.  The pattern is consistent with the task. In longer cycles, plausible distractors are more numerous and native ambiguity is higher, especially in CUAD.
```

### 2.10 Robustness checks

位置：[`acl_latex.tex:352`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:352)

```latex
Appendix~\ref{sec:appendix_experiments} reports selector and reliability checks.  The non-oracle boosted selector reaches 52\% \riskall{}, while compression-first oracle selection raises compression but lowers \riskall{} to 47\%.  A CUAD lite-output control reduces formatting burden but still reaches only 12\% \riskall{} on long-contract SCCs, and a more compressed \samcgs{} profile lowers \riskall{} from 78\% to 71\%.
```

### 2.11 Shared Risk Rubric Prompt

位置：[`acl_latex.tex:703`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:703)

```latex
Reviewer fairness depends on separating the risk definition from the search mechanism.  The following excerpt gives the shared evaluator rubric used by both full-\scc{} \naive{} attempts and the \samcgs{} local-window evaluator.
```

位置：[`acl_latex.tex:711`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:711)

```latex
\naive{} and \samcgs{} use this same risk rubric.  The methods differ in input unit and search procedure.  Each \naive{} attempt reads the complete \scc{} and emits a global ranking plus a risk subgraph; the main baseline aggregates ten such attempts with oracle-risk Top-3 selection.  \samcgs{} reads local windows over multiple rollouts and aggregates evidence before emitting a final core.  The comparison holds the risk definition fixed and varies the computation.
```

位置：[`acl_latex.tex:731`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:731)

```latex
\naive{} requires each generation to rank the entire \scc{} and produce a final subgraph.  In contrast, \samcgs{} asks only for local evidence, leaving final subgraph construction to algorithmic memory and compression.
```

### 2.12 Appendix: Locked run configuration

位置：[`acl_latex.tex:786`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:786)

```latex
\paragraph{Locked run configuration.}
Unless otherwise stated, \samcgs{} uses the locked profile
\texttt{current/default + memory\_stress(structural\_simple\_v2) + critical}
with 80 \scc{} blocks per model and four models (GPT-4o, DeepSeek-V3, Qwen2.5-72B, and Gemini 2.5 Pro).  The main \naive{} baseline is oracle-risk Top-3 selection over ten full-\scc{} direct-subgraph attempts per model-case.  One-shot \naive{}, non-oracle boosted selection, and compression-first oracle selection are reported below as controls.
```

### 2.13 Appendix reliability table

位置：[`acl_latex.tex:791`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:791)

```latex
\begin{table*}[!t]
\centering
\small
\begin{tabular}{llrrr}
\toprule
Scope & Denominator & Usable & Unusable & Rate \\
\midrule
one-shot \naive{} & model-cases & 261/320 & 59/320 & 82\% \\
\samcgs{} & model-cases & 320/320 & 0/320 & 100\% \\
boosted \naive{} & raw attempts & 2400/3200 & 800/3200 & 75\% \\
boosted \naive{} & model-cases & 274/320 & 46/320 & 86\% \\
\bottomrule
\end{tabular}
\caption{Output reliability audit.  Boosted \naive{} has both a raw-attempt denominator and a model-case denominator; the latter counts cases with at least one valid full-\scc{} generation.}
\label{tab:reliability}
\end{table*}
```

### 2.14 Appendix boosted selector table

位置：[`acl_latex.tex:808`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:808)

```latex
\begin{table*}[!t]
\centering
\scriptsize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{p{.28\textwidth}rrrrrp{.20\textwidth}}
\toprule
Control & N & \rootthree{} & \riskany{} & \riskall{} & Comp. & Role \\
\midrule
one-shot \naive{} & 320 & 48\% & 72\% & 47\% & 67\% & original locked control \\
boosted \naive{} single-attempt mean & 3200 attempts & 47\% & 67\% & 48\% & 50\% & raw repeated-sampling mean \\
boosted \naive{} self Top-3 & 320 & 52\% & 75\% & 52\% & 60\% & non-oracle selector \\
boosted \naive{} oracle-risk Top-3 & 320 & 58\% & 79\% & 62\% & 60\% & main oracle-risk baseline \\
boosted \naive{} oracle-compression Top-3 & 320 & 53\% & 75\% & 47\% & 63\% & compression-first diagnostic \\
\samcgs{} & 320 & 81\% & 98\% & 78\% & 53\% & proposed method \\
\bottomrule
\end{tabular}
\caption{Boosted \naive{} selector comparison.  Oracle selectors use ground-truth evaluation metrics for selection; oracle-risk Top-3 is the main oracle-risk baseline, while self Top-3 is the non-oracle boosted selector.}
\label{tab:boosted_selectors}
\end{table*}
```

### 2.15 Appendix Figure A2 caption

位置：[`acl_latex.tex:831`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:831)

```latex
\caption{Naive output-burden control.  Reducing the output schema improves availability and recovers some risk signal, but it does not close the endpoint-retention gap on long CUAD components.}
```

### 2.16 Appendix combined table: selector summary

位置：[`acl_latex.tex:855`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:855)

```latex
\textbf{B. Selector summary}\\[0.4mm]
\begin{tabular}{@{}lrrr@{}}
\toprule
Control & N & \rootthree{} & \riskall{} \\
\midrule
one-shot \naive{} & 320 & 48\% & 47\% \\
self Top-3 & 320 & 52\% & 52\% \\
oracle-risk Top-3 & 320 & 58\% & 62\% \\
\samcgs{} & 320 & 81\% & 78\% \\
\bottomrule
\end{tabular}
```

### 2.17 Appendix combined table: model breakdown

位置：[`acl_latex.tex:869`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:869)

```latex
\textbf{C. Model-level breakdown}\\[0.4mm]
\begin{tabular}{@{}llrrrrrr@{}}
\toprule
Model & Method & N & Zero & \rootthree{} & \riskany{} & \riskall{} & Comp. \\
\midrule
GPT-4o & oracle-risk \naive{} & 80 & 6 & 37\% & 76\% & 37\% & 65\% \\
GPT-4o & \samcgs{} & 80 & 0 & 86\% & 100\% & 75\% & 51\% \\
DeepSeek-V3 & oracle-risk \naive{} & 80 & 0 & 87\% & 95\% & 87\% & 74\% \\
DeepSeek-V3 & \samcgs{} & 80 & 0 & 80\% & 95\% & 76\% & 51\% \\
Qwen2.5-72B & oracle-risk \naive{} & 80 & 40 & 11\% & 48\% & 28\% & 22\% \\
Qwen2.5-72B & \samcgs{} & 80 & 0 & 70\% & 98\% & 75\% & 53\% \\
Gemini 2.5 Pro & oracle-risk \naive{} & 80 & 0 & 99\% & 100\% & 97\% & 79\% \\
Gemini 2.5 Pro & \samcgs{} & 80 & 0 & 88\% & 98\% & 84\% & 56\% \\
\bottomrule
\end{tabular}
```

### 2.18 Appendix combined table: domain breakdown

位置：[`acl_latex.tex:889`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:889)

```latex
\textbf{D. Domain-level breakdown}\\[0.4mm]
\begin{tabular}{@{}llrrrrrr@{}}
\toprule
Domain & Method & N & Zero & \rootthree{} & \riskany{} & \riskall{} & Comp. \\
\midrule
Debian & oracle-risk \naive{} & 32 & 0 & 65\% & 100\% & 80\% & 61\% \\
Debian & \samcgs{} & 32 & 0 & 84\% & 100\% & 88\% & 53\% \\
SEC EX-21 & oracle-risk \naive{} & 80 & 0 & 74\% & 100\% & 85\% & 62\% \\
SEC EX-21 & \samcgs{} & 80 & 0 & 96\% & 100\% & 88\% & 50\% \\
BGB & oracle-risk \naive{} & 48 & 1 & 46\% & 89\% & 50\% & 61\% \\
BGB & \samcgs{} & 48 & 0 & 75\% & 98\% & 62\% & 52\% \\
CUAD & oracle-risk \naive{} & 160 & 45 & 53\% & 62\% & 51\% & 59\% \\
CUAD & \samcgs{} & 160 & 0 & 74\% & 96\% & 75\% & 54\% \\
\bottomrule
\end{tabular}
```

位置：[`acl_latex.tex:905`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:905)

```latex
\caption{Supplementary case and result breakdowns.  ``Zero'' counts boosted \naive{} model-cases with no valid full-\scc{} generation.  CUAD concentrates long-context and output-schema failures, where generations may time out or become unparseable through incomplete, duplicate, or invalid rankings.}
```

## 3. 生成出来的 Markdown 表格

这些是 `paper_assets/tables/` 下被更新或新增的 Markdown 表。

### 3.1 Main Results

源文件：[`tab03_main_results_strict.md`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/tables/tab03_main_results_strict.md)

| method | n | root_at_3 | risk_any | risk_all | compression |
|---|---:|---:|---:|---:|---:|
| oracle-risk Naive | 320 | 58% | 79% | 62% | 60% |
| sa-mcgs | 320 | 81% | 98% | 78% | 53% |

### 3.2 Output Reliability

源文件：[`tab03_reliability_strict.md`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/tables/tab03_reliability_strict.md)

| scope | method | denominator | usable | unusable | usable_rate |
|---|---|---|---|---|---:|
| locked one-shot | one-shot Naive | model-cases | 261/320 | 59/320 | 82% |
| locked main | sa-mcgs | model-cases | 320/320 | 0/320 | 100% |
| boosted Naive x10 | oracle-risk Naive | raw attempts | 2400/3200 | 800/3200 | 75% |
| boosted Naive x10 | oracle-risk Naive | model-cases | 274/320 | 46/320 | 86% |

### 3.3 Model-level Breakdown

源文件：[`tabA4_model_breakdown.md`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/tables/tabA4_model_breakdown.md)

| model | method | n | zero_valid_cases | root_at_3 | risk_any | risk_all | compression |
|---|---|---:|---:|---:|---:|---:|---:|
| gpt-4o | oracle-risk Naive | 80 | 6 | 37% | 76% | 37% | 65% |
| gpt-4o | sa-mcgs | 80 | 0 | 86% | 100% | 75% | 51% |
| deepseek-v3 | oracle-risk Naive | 80 | 0 | 87% | 95% | 87% | 74% |
| deepseek-v3 | sa-mcgs | 80 | 0 | 80% | 95% | 76% | 51% |
| qwen2.5-72b | oracle-risk Naive | 80 | 40 | 11% | 48% | 28% | 22% |
| qwen2.5-72b | sa-mcgs | 80 | 0 | 70% | 98% | 75% | 53% |
| gemini-2.5-pro | oracle-risk Naive | 80 | 0 | 99% | 100% | 97% | 79% |
| gemini-2.5-pro | sa-mcgs | 80 | 0 | 88% | 98% | 84% | 56% |

### 3.4 Domain-level Breakdown

源文件：[`tabA5_domain_breakdown.md`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/tables/tabA5_domain_breakdown.md)

| domain | method | n | zero_valid_cases | root_at_3 | risk_any | risk_all | compression |
|---|---|---:|---:|---:|---:|---:|---:|
| debian | oracle-risk Naive | 32 | 0 | 65% | 100% | 80% | 61% |
| debian | sa-mcgs | 32 | 0 | 84% | 100% | 88% | 53% |
| sec_ex21 | oracle-risk Naive | 80 | 0 | 74% | 100% | 85% | 62% |
| sec_ex21 | sa-mcgs | 80 | 0 | 96% | 100% | 88% | 50% |
| bgb | oracle-risk Naive | 48 | 1 | 46% | 89% | 50% | 61% |
| bgb | sa-mcgs | 48 | 0 | 75% | 98% | 62% | 52% |
| cuad | oracle-risk Naive | 160 | 45 | 53% | 62% | 51% | 59% |
| cuad | sa-mcgs | 160 | 0 | 74% | 96% | 75% | 54% |

### 3.5 Metrics by SCC Size

源文件：[`tabA6_by_scc_size.md`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/tables/tabA6_by_scc_size.md)

| scc_size | method | n | root_at_3 | risk_any | risk_all | compression |
|---|---|---:|---:|---:|---:|---:|
| 9 | oracle-risk Naive | 32 | 68% | 92% | 62% | 53% |
| 9 | sa-mcgs | 32 | 88% | 97% | 72% | 44% |
| 10 | oracle-risk Naive | 16 | 83% | 100% | 96% | 52% |
| 10 | sa-mcgs | 16 | 88% | 100% | 56% | 50% |
| 11 | oracle-risk Naive | 48 | 65% | 100% | 79% | 59% |
| 11 | sa-mcgs | 48 | 79% | 100% | 81% | 55% |
| 12 | oracle-risk Naive | 48 | 74% | 92% | 84% | 60% |
| 12 | sa-mcgs | 48 | 100% | 100% | 100% | 51% |
| 14 | oracle-risk Naive | 16 | 52% | 75% | 52% | 57% |
| 14 | sa-mcgs | 16 | 88% | 100% | 88% | 50% |
| 16 | oracle-risk Naive | 16 | 38% | 38% | 38% | 61% |
| 16 | sa-mcgs | 16 | 100% | 100% | 100% | 50% |
| 17 | oracle-risk Naive | 16 | 50% | 71% | 33% | 62% |
| 17 | sa-mcgs | 16 | 38% | 100% | 69% | 53% |
| 18 | oracle-risk Naive | 32 | 51% | 84% | 55% | 70% |
| 18 | sa-mcgs | 32 | 91% | 100% | 88% | 51% |
| 20 | oracle-risk Naive | 16 | 50% | 52% | 50% | 61% |
| 20 | sa-mcgs | 16 | 56% | 94% | 50% | 55% |
| 24 | oracle-risk Naive | 16 | 57% | 57% | 50% | 63% |
| 24 | sa-mcgs | 16 | 69% | 75% | 44% | 56% |
| 25 | oracle-risk Naive | 32 | 44% | 75% | 51% | 67% |
| 25 | sa-mcgs | 32 | 84% | 100% | 78% | 56% |
| 28 | oracle-risk Naive | 16 | 50% | 69% | 50% | 60% |
| 28 | sa-mcgs | 16 | 25% | 94% | 31% | 58% |
| 34 | oracle-risk Naive | 16 | 48% | 50% | 48% | 45% |
| 34 | sa-mcgs | 16 | 94% | 94% | 94% | 64% |

### 3.6 Boosted Naive Selector Comparison

源文件：[`tabA9_boosted_naive_selector_comparison.md`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/tables/tabA9_boosted_naive_selector_comparison.md)

| control | n | root_at_3 | risk_any | risk_all | compression | role |
|---|---|---:|---:|---:|---:|---|
| one-shot Naive | 320 | 48% | 72% | 47% | 67% | original locked control |
| boosted Naive single-attempt mean | 320 cases / 3200 attempts | 47% | 67% | 48% | 50% | raw repeated-sampling mean |
| boosted Naive self_top3 | 320 | 52% | 75% | 52% | 60% | non-oracle selector |
| boosted Naive oracle_risk_top3 | 320 | 58% | 79% | 62% | 60% | main oracle-risk baseline |
| boosted Naive oracle_compression_top3 | 320 | 53% | 75% | 47% | 63% | compression-first diagnostic |
| SA-MCGS | 320 | 81% | 98% | 78% | 53% | proposed method |

## 4. 图片与 PDF 资产

### 4.1 Figure 3: Main results composite

源文件：

- PNG：[`fig02_main_results_composite.png`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig02_main_results_composite.png)
- PDF：[`fig02_main_results_composite.pdf`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig02_main_results_composite.pdf)

核对点：

- Panel A 用 `oracle-risk Naive` vs `SA-MCGS`。
- Root@3：58 -> 81。
- Risk-any：79 -> 98。
- Risk-all：62 -> 78。
- Compression：60 vs 53。
- Panel B size breakdown 使用 oracle-risk Naive。
- 已修复你截图里指出的 legend / Root@3 遮挡：图例上方留了额外 band。

![Figure 3 main results composite](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig02_main_results_composite.png)

### 4.2 Main metrics strict 备用图

源文件：

- PNG：[`fig02_main_metrics_strict.png`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig02_main_metrics_strict.png)
- PDF：[`fig02_main_metrics_strict.pdf`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig02_main_metrics_strict.pdf)

核对点：

- 这个图也切到了 `oracle-risk Naive`。
- 当前 paper 主文用的是 composite Figure 3；这个更像备用/源图。

![Main metrics strict](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig02_main_metrics_strict.png)

### 4.3 SCC-size 备用图 / Appendix figure

源文件：

- PNG：[`fig03_main_by_scc_size.png`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig03_main_by_scc_size.png)
- PDF：[`fig03_main_by_scc_size.pdf`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig03_main_by_scc_size.pdf)

核对点：

- Naive 侧改为 oracle-risk Naive。
- 与 Figure 3 Panel B 的 size 口径一致。

![SCC size breakdown](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig03_main_by_scc_size.png)

### 4.4 Paper PDF

源文件：[`paper/latex/acl_latex.pdf`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.pdf)

核对点：

- 已重新编译。
- 编译无 LaTeX error；只有已有样式/排版 warning。
- Figure 3 使用更新后的 PDF 图。

## 5. README / catalog / report 文案变更

### 5.1 Main experiment README

源文件：[`experiments/main_experiment/README.md`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/README.md)

```md
口径提醒：主实验图表使用 `current/default + critical + structural_simple_v2 + 4 models + 80 SCC blocks/model`，其中 main Naive baseline 为 `oracle_risk_top3` over ten full-SCC Naive attempts。旧 diagnostic、smoke、balanced exploratory 不作为主结果。
```

### 5.2 Paper assets README

源文件：[`experiments/main_experiment/paper_assets/README.md`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/README.md)

新增：

```md
- Boosted Naive selector comparison: `tables/tabA9_boosted_naive_selector_comparison.md` / `.csv`
```

### 5.3 Figures README / figure catalog

源文件：

- [`figures/README.md`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/README.md)
- [`figure_catalog.md`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/tables/figure_catalog.md)

Figure 3 描述改为：

```md
Composite main-result figure: oracle-risk Naive versus SA-MCGS, plus SCC-size breakdown of endpoint retention and compression.
```

口径规则新增：

```md
- 主实验图使用 `current/default + critical + structural_simple_v2 + 4 models + 80 SCC blocks/model`。
- Figure 3 的 Naive baseline 是 `oracle_risk_top3` over ten full-SCC Naive attempts，图例写作 `oracle-risk Naive`。
```

### 5.4 Boosted Naive report

源文件：[`BOOSTED_NAIVE_BASELINE_REPORT.md`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/boosted_naive_baseline/results_canonical80_x10/BOOSTED_NAIVE_BASELINE_REPORT.md)

当前报告落字：

```md
# Boosted Naive Baseline Report

状态：boosted Naive 补充实验报告；当前 main baseline 使用 `oracle_risk_top3`，`self_top3` 和 `oracle_compression_top3` 作为附录/diagnostic controls。

- Raw attempts: `3200`
- Top-k aggregation: `Top-3`
- Errors recorded in denominator: `800`
- Observed tokens: prompt `39,972,656`, completion `11,659,377`, total `51,632,033`

| Selector | N | Root@3 | Risk-any | Risk-all | Compression | Mean valid attempts | Avg selected tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| self_top3 | 320 | 52.1% | 74.5% | 51.6% | 59.6% | 7.50 | 20,112 |
| oracle_risk_top3 | 320 | 58.4% | 79.4% | 62.2% | 60.0% | 7.50 | 20,051 |
| oracle_compression_top3 | 320 | 53.3% | 74.7% | 47.4% | 63.5% | 7.50 | 19,988 |
```

## 6. 生成脚本的口径变更

源文件：[`build_paper_assets.py`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/build_paper_assets.py)

需要核对的逻辑：

- 新增 boosted 数据源：
  - `BOOSTED_RESULTS_DIR`
  - `BOOSTED_SUMMARY_CSV`
  - `BOOSTED_RAW_JSONL`
- 新增主 baseline 常量：
  - `MAIN_NAIVE_SELECTOR = "oracle_risk_top3"`
  - `MAIN_NAIVE_LABEL = "oracle-risk Naive"`
- 主结果图、主结果表、model/domain/SCC-size 表都使用 `oracle_risk_top3` 的 boosted summary 作为 Naive 侧数据。
- Reliability 表拆成 one-shot、SA-MCGS、boosted raw attempts、boosted model-cases 四行。
- 新增 `tabA9_boosted_naive_selector_comparison.csv/md`。
- Figure 3 legend 防遮挡：Panel A 的 y-axis 上方增加空间，避免 `oracle-risk Naive` 标签压到 Root@3 点。

需要人工确认的脚本文案：

```python
MAIN_NAIVE_SELECTOR = "oracle_risk_top3"
MAIN_NAIVE_LABEL = "oracle-risk Naive"
```

```python
"role": "main oracle-risk baseline"
```

```python
"role": "non-oracle selector"
```

```python
"role": "compression-first diagnostic"
```

## 7. 原始数据 / 打包文件状态

这些文件有变化，但不建议逐行人工核对，除非你要审计实验日志：

| 文件 | 状态 |
|---|---|
| [`boosted_naive_round_robin_status.json`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/boosted_naive_baseline/results_canonical80_x10/boosted_naive_round_robin_status.json) | `status: done`, `completed_attempts: 3200`, `remaining_attempts: 0` |
| [`boosted_naive_raw_attempts.jsonl`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/boosted_naive_baseline/results_canonical80_x10/boosted_naive_raw_attempts.jsonl) | 3200 行 raw attempts |
| [`boosted_naive_top3_summary.csv`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/boosted_naive_baseline/results_canonical80_x10/boosted_naive_top3_summary.csv) | 961 行 summary，包含 320 cases x 3 selectors + header |
| [`submission/arr_submission_20260525_210437.zip`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/submission/arr_submission_20260525_210437.zip) | 当前生成的提交包副本，建议确认 paper 后重新打包 |

## 8. 我建议你优先核对的点

- [ ] Abstract 里 `58 / 79 / 62 -> 81 / 98 / 78` 是否接受。
- [ ] `oracle-risk Naive` 这个图例和正文称呼是否接受。
- [ ] 正文是否统一使用 `oracle-risk` baseline，而不是更弱的 `self_top3` baseline。
- [ ] Figure 3 Panel A legend 现在是否不遮挡。
- [ ] 主文不增加长度，只把 selector comparison 和 reliability 放附录，这个结构是否接受。
- [ ] Reliability 里 raw attempts `2400/3200` 和 model-cases `274/320` 两个分母是否清楚。
- [ ] CUAD 错误解释是否统一为 long-context / output-schema burden，而不是 quota 或网络错误。

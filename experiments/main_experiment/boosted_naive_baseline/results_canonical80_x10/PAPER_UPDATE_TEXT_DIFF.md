# Paper 更新文字核对：改前 / 改后精简版

本文件只列“文字从什么改成什么”。不贴 LaTeX 源码，不贴整段原文，只保留需要核对的改动句子或短语。

## 1. 正文文字改动

### 1.1 标题

改前：
Collapsing Strongly Connected Components into Risk Subgraphs with Structure-Aware Monte Carlo Graph Search

改后：
Risk Subgraph Extraction in Cyclic Document Graphs with Structure-Aware Monte Carlo Search

备注：标题变化不是 oracle-risk baseline 必需改动，需要确认是否保留。

### 1.2 Abstract 主结果句

改前：
Across 320 model-case pairs and four LLMs, SA-MCGS improves strict Root@3 from 48% to 81%, Risk-any from 72% to 98%, and Risk-all from 47% to 78%.

改后：
Across 320 model-case pairs and four LLMs, SA-MCGS improves Root@3 from 58% to 81%, Risk-any from 79% to 98%, and Risk-all from 62% to 78% over an oracle-risk Top-3 full-SCC Naive baseline selected from ten attempts.

### 1.3 Contribution 里的 baseline 描述

改前：
Across these settings, SA-MCGS improves strict Root@3, Risk-any, and Risk-all over a full-SCC direct-subgraph baseline.

改后：
Across these settings, SA-MCGS improves Root@3, Risk-any, and Risk-all over an oracle-risk full-SCC direct-subgraph baseline.

### 1.4 方法对比口径

改前：
The comparison is therefore computational, contrasting full-SCC one-shot generation with SCC-aware rollout selection, relation-first memory, critical-pair revisiting, and dynamic-core compression.

改后：
The comparison is therefore computational, contrasting full-SCC direct-subgraph generation and Top-3 aggregation with SCC-aware rollout selection, relation-first memory, critical-pair revisiting, and dynamic-core compression.

### 1.5 Baseline 定义

改前：
We compare against a full-context direct-subgraph baseline, where Naive sees the full SCC in one prompt and outputs both a whole-SCC risk ranking and a risk subgraph.

改后：
We use oracle-risk Naive as the main baseline. It runs the full-SCC direct-subgraph prompt ten times. From these attempts, a risk-prioritized oracle chooses the reported Top-3 set using Root@3, Risk-any, and Risk-all.

改前：
SA-MCGS instead sees smaller local windows over 60 rollouts and aggregates evidence into a dynamic core. This setup gives Naive more context per call but a heavier one-shot output burden. SA-MCGS trades that burden for iterative search and evidence retention.

改后：
Each Naive attempt sees the full SCC and emits a whole-SCC ranking plus a risk subgraph; the appendix reports non-oracle and compression-first variants. SA-MCGS instead sees smaller local windows over 60 rollouts and aggregates evidence into a dynamic core.

### 1.6 实验规模说明

改前：
The main data contain 320 model-case pairs and 640 method-level records.

改后：
The main comparison contains 320 model-case pairs per method; oracle-risk Naive is selected from 3,200 raw full-SCC attempts. This gives boosted Naive a total token budget comparable to SA-MCGS.

### 1.7 Figure 3 caption

改前：
Panel A reports strict headline metrics, and Panel B gives a compact SCC-size breakdown of endpoint retention and compression. Higher compression values indicate smaller subgraphs and show the cost of retaining more evidence.

改后：
Panel A compares SA-MCGS with oracle-risk Naive, an oracle-risk Top-3 selection over ten full-SCC attempts; Panel B gives a compact SCC-size breakdown of endpoint retention and compression.

### 1.8 Main Results 主结论

改前：
SA-MCGS improves Root@3 by 32 points, Risk-any by 26 points, and Risk-all by 31 points.

改后：
Against oracle-risk Naive, SA-MCGS improves Root@3 by 23 points, Risk-any by 19 points, and Risk-all by 16 points.

改前：
The strongest claim is not that one-shot LLMs never find risk, since Naive often finds at least one suspicious record.

改后：
The strongest claim is not that full-SCC prompting never finds risk, since the baseline is already selected from ten attempts with access to risk metrics.

### 1.9 Compression 解释

改前：
Although Naive returns smaller subgraphs on average, it often drops one side of a critical contradiction or produces an output that is too large, incomplete, or otherwise unavailable for scoring.

改后：
Oracle-risk Naive is slightly more compressed on average, but still retains all critical endpoints less often.

### 1.10 Reliability 说明

改前：
Strict rates keep unavailable structured outputs in the denominator; the appendix reports the output-availability audit.

改后：
The appendix separates one-shot output availability from boosted raw-attempt and model-case reliability.

### 1.11 Model / domain breakdown

改前：
GPT-4o and Qwen2.5-72B show large Risk-all gains, DeepSeek-V3 is already strong under Naive and still improves, and Gemini 2.5 Pro is competitive for both methods.

改后：
Gemini 2.5 Pro and DeepSeek-V3 are strong even under oracle-risk Naive, while GPT-4o and Qwen2.5-72B still lag in complete endpoint retention.

改前：
Domain-wise, CUAD is the hardest setting, as long contract text creates high output burden for full-SCC prompting. Debian and SEC are cleaner and still show endpoint-retention gains.

改后：
Domain-wise, CUAD is the hardest setting: long contract components create both context pressure and output-schema burden for full-SCC ranking and subgraph generation.

### 1.12 SCC-size breakdown

改前：
In short components, SA-MCGS improves Risk-all from 55% to 83%.

改后：
In short components, SA-MCGS improves Risk-all from 79% to 83%.

改前：
In mid-sized components, the improvement is 40% to 80%.

改后：
In mid-sized components, the improvement is 47% to 80%.

改前：
In long components, Risk-all remains difficult, but SA-MCGS still improves 41% to 65%.

改后：
In long components, Risk-all remains difficult, but SA-MCGS still improves 50% to 65%.

### 1.13 Robustness checks

改前：
The appendix reports two auxiliary checks.

改后：
The appendix reports selector and reliability checks.

改前：
First, a more compressed profile reduces the average retained core from 7.69 to 5.91 nodes, although Risk-all falls from 78% to 71%. For the main run, we therefore keep the profile that better preserves critical endpoints.

改后：
The non-oracle boosted selector reaches 52% Risk-all, while compression-first oracle selection raises compression but lowers Risk-all to 47%.

改前：
Second, strict rates do not hide unavailable Naive outputs. On 261 matched usable pairs, SA-MCGS remains higher in Root@3 (83% vs. 59%), Risk-any (98% vs. 88%), and Risk-all (77% vs. 57%). A CUAD lite-output control likewise reduces formatting burden but still reaches only 12% Risk-all on long-contract SCCs, indicating that full-SCC prompting is both an output and reasoning burden.

改后：
A CUAD lite-output control reduces formatting burden but still reaches only 12% Risk-all on long-contract SCCs, and a more compressed SA-MCGS profile lowers Risk-all from 78% to 71%.

## 2. 附录文字改动

### 2.1 Shared Risk Rubric 描述

改前：
The shared evaluator rubric is used by both the full-SCC Naive baseline and the SA-MCGS local-window evaluator.

改后：
The shared evaluator rubric is used by both full-SCC Naive attempts and the SA-MCGS local-window evaluator.

### 2.2 Shared semantics

改前：
Naive reads the complete SCC once and emits a global ranking plus a risk subgraph.

改后：
Each Naive attempt reads the complete SCC and emits a global ranking plus a risk subgraph; the main baseline aggregates ten such attempts with oracle-risk Top-3 selection.

改前：
The comparison holds the risk definition fixed and varies the computation, contrasting one-shot full-context evaluation with localized search and evidence compression.

改后：
The comparison holds the risk definition fixed and varies the computation.

### 2.3 Output contrast

改前：
Naive requires one generation to rank the entire SCC and produce a final subgraph.

改后：
Naive requires each generation to rank the entire SCC and produce a final subgraph.

### 2.4 Locked run configuration

改前：
Unless otherwise stated, the main tables use the locked profile.

改后：
Unless otherwise stated, SA-MCGS uses the locked profile.

改前：
For each model and profile, the same SCC block is evaluated by the full-SCC direct-subgraph Naive baseline and by SA-MCGS. Strict rates count unusable structured outputs in the denominator.

改后：
The main Naive baseline is oracle-risk Top-3 selection over ten full-SCC direct-subgraph attempts per model-case. One-shot Naive, non-oracle boosted selection, and compression-first oracle selection are reported below as controls.

### 2.5 Reliability table caption

改前：
Strict output reliability. Unavailable structured outputs remain in the denominator of Figure 3. The appendix placement reflects the role of output availability as an audit detail, not a headline metric.

改后：
Output reliability audit. Boosted Naive has both a raw-attempt denominator and a model-case denominator; the latter counts cases with at least one valid full-SCC generation.

### 2.6 New selector table caption

新增：
Boosted Naive selector comparison. Oracle selectors use ground-truth evaluation metrics for selection; oracle-risk Top-3 is the main oracle-risk baseline, while self Top-3 is the non-oracle boosted selector.

### 2.7 Naive output-burden figure caption

改前：
Reducing the output schema helps full-SCC prompting, although it does not close the endpoint-retention gap on long CUAD components.

改后：
Reducing the output schema improves availability and recovers some risk signal, but it does not close the endpoint-retention gap on long CUAD components.

### 2.8 Appendix combined table section title

改前：
B. Output availability

改后：
B. Selector summary

改前：
C. Model-level strict breakdown

改后：
C. Model-level breakdown

改前：
D. Domain-level strict breakdown

改后：
D. Domain-level breakdown

### 2.9 Appendix combined table caption

改前：
Supplementary case and result breakdowns. Representative cases illustrate why remediation often requires more than a single suspicious record. Strict rates count unusable structured outputs in the denominator. Matched usable-output rates show that the gap is not only output availability.

改后：
Supplementary case and result breakdowns. "Zero" counts boosted Naive model-cases with no valid full-SCC generation. CUAD concentrates long-context and output-schema failures, where generations may time out or become unparseable through incomplete, duplicate, or invalid rankings.

## 3. 表格内容口径改动

### 3.1 Main Results table

改前：
Naive: N 320, errors 59, Root@3 48%, Risk-any 72%, Risk-all 47%, Compression 67%, effective compression 66%, avg subgraph 4.44

改后：
oracle-risk Naive: N 320, Root@3 58%, Risk-any 79%, Risk-all 62%, Compression 60%

改前：
SA-MCGS: N 320, errors 0, Root@3 81%, Risk-any 98%, Risk-all 78%, Compression 53%, effective compression 53%, avg subgraph 7.69

改后：
SA-MCGS: N 320, Root@3 81%, Risk-any 98%, Risk-all 78%, Compression 53%

### 3.2 Reliability table

改前：
Naive: 261/320 usable, 59/320 unavailable, 82% usable-output rate

改后：
one-shot Naive: 261/320 usable, 59/320 unusable, 82% usable rate

改前：
SA-MCGS: 320/320 usable, 0/320 unavailable, 100% usable-output rate

改后：
SA-MCGS: 320/320 usable, 0/320 unusable, 100% usable rate

新增：
boosted Naive x10 raw attempts: 2400/3200 usable, 800/3200 unusable, 75% usable rate

新增：
boosted Naive x10 model-cases: 274/320 usable, 46/320 unusable, 86% usable rate

### 3.3 Selector comparison table

新增：
one-shot Naive: 48% Root@3, 72% Risk-any, 47% Risk-all, 67% compression

新增：
boosted Naive single-attempt mean: 47% Root@3, 67% Risk-any, 48% Risk-all, 50% compression

新增：
boosted Naive self_top3: 52% Root@3, 75% Risk-any, 52% Risk-all, 60% compression

新增：
boosted Naive oracle_risk_top3: 58% Root@3, 79% Risk-any, 62% Risk-all, 60% compression

新增：
boosted Naive oracle_compression_top3: 53% Root@3, 75% Risk-any, 47% Risk-all, 63% compression

新增：
SA-MCGS: 81% Root@3, 98% Risk-any, 78% Risk-all, 53% compression

### 3.4 Model breakdown table

改前：
Model table used one-shot Naive rows with an errors column.

改后：
Model table uses oracle-risk Naive rows with a zero-valid-cases column.

主要改后数字：

| Model | oracle-risk Naive Root@3 | Risk-any | Risk-all | Compression | Zero-valid cases |
|---|---:|---:|---:|---:|---:|
| GPT-4o | 37% | 76% | 37% | 65% | 6 |
| DeepSeek-V3 | 87% | 95% | 87% | 74% | 0 |
| Qwen2.5-72B | 11% | 48% | 28% | 22% | 40 |
| Gemini 2.5 Pro | 99% | 100% | 97% | 79% | 0 |

### 3.5 Domain breakdown table

改前：
Domain table used one-shot Naive rows with an errors column.

改后：
Domain table uses oracle-risk Naive rows with a zero-valid-cases column.

主要改后数字：

| Domain | oracle-risk Naive Root@3 | Risk-any | Risk-all | Compression | Zero-valid cases |
|---|---:|---:|---:|---:|---:|
| Debian | 65% | 100% | 80% | 61% | 0 |
| SEC EX-21 | 74% | 100% | 85% | 62% | 0 |
| BGB | 46% | 89% | 50% | 61% | 1 |
| CUAD | 53% | 62% | 51% | 59% | 45 |

## 4. 图片文字 / 图内数字改动

### 4.1 Figure 3

改前：
Legend: Naive vs SA-MCGS

改后：
Legend: oracle-risk Naive vs SA-MCGS

改前：
Panel A values used one-shot Naive: Root@3 48%, Risk-any 72%, Risk-all 47%, Compression 67%

改后：
Panel A values use oracle-risk Naive: Root@3 58%, Risk-any 79%, Risk-all 62%, Compression 60%

改前：
Panel B size breakdown used one-shot Naive.

改后：
Panel B size breakdown uses oracle-risk Naive.

视觉修复：
Legend band increased so "oracle-risk Naive" no longer overlaps the Root@3 row.

图片路径：
[`fig02_main_results_composite.png`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig02_main_results_composite.png)

### 4.2 Main metrics strict image

改前：
Naive label and values used one-shot Naive.

改后：
Naive label and values use oracle-risk Naive.

图片路径：
[`fig02_main_metrics_strict.png`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig02_main_metrics_strict.png)

### 4.3 SCC-size image

改前：
Naive side used one-shot Naive by SCC size.

改后：
Naive side uses oracle-risk Naive by SCC size.

图片路径：
[`fig03_main_by_scc_size.png`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/experiments/main_experiment/paper_assets/figures/fig03_main_by_scc_size.png)

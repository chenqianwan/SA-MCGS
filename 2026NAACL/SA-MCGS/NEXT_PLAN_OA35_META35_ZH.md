# SA-MCGS Next Plan：OA 3.5 / Meta 3.5

> 历史评估草案，保留用于追溯，不再作为当前实验规模、完成状态或组件贡献的依据。2026-09-09 的实际执行方案以 `plan.md`、`REMAINING_EXPERIMENTS_ZH.md` 和各批次结果为准；专家集已统一为 18 pre / 36 post，Stage-1 修复子集未复现旧 critical-pair 下降结论。

## 1. 目标判断

ARR 的 `3.5` 是 **Borderline Conference**，不只是“基本可发表”。Findings 与主会都要求 soundness/reproducibility；主会还需要在新意、影响或其他方面形成清楚的区分度，并且不能留下主要问题（[review form](https://aclrollingreview.org/reviewform)，[AC guidelines](https://aclrollingreview.org/acguidelines)）。

当前分数为 `2.5 / 2.5 / 3.0`，meta 为 `3.0`。因此：

- 修复 LEA、Stage-1 和 cost 只是恢复 rebuttal 证据可信度，属于 **3.0/Findings 底线**；
- 要较有把握达到 OA/meta `3.5`，还要关闭 clean/false-positive 边界，并形成一个真正有区分度的新信号；
- 最有升分价值的新信号是 **自然发生的 cyclic 正负例专家集**；若做不到，至少完成 clean-negative control，并彻底收窄外部有效性口径。

## 2. 固定中心口径

> 在 controlled cyclic-SCC structural-risk stress test 中，SA-MCGS 通过 repeated critical-pair resolution 和 replacement-based dynamic core，以更多 calls/tokens 换取困难案例上更完整的 benchmark-defined endpoint recovery；收益依赖模型与案例难度，系统定位为 human decision support，而非 automated risk adjudication。

固定术语：

- `Risk-all`：benchmark-defined endpoint completeness；
- `LEA`：matched graph-aware local aggregation control，不称为某个已发表 GraphRAG 系统的复现；
- `oracle-risk Naive`：使用 ground truth 选取结果的 non-deployable diagnostic baseline；
- dynamic core 只主张改善 final endpoint retention，不主张改变 frozen rollout trajectory。

## 3. Reviewer / Meta 升分门槛

| 对象 | 当前卡点 | 达到 3.5 所需的最小闭环 |
|---|---|---|
| iMEC（2.5） | 技术贡献像组件集成；缺公平基线、组件归因和成本 | corrected LEA；corrected Stage-1；已修复 Stage-2；统一 cost。正文只把 cluster-aware 结果支持的机制列为贡献 |
| rxvy（2.5） | injected-only、false positive、cleanliness、prior sensitivity、模型异质性 | clean/non-risk + frozen abstention；endpoint-density/excess-node；小规模 prior sensitivity；所有反向模型结果在正文可见 |
| wWUk（3.0） | 自然风险、graph-aware comparator、成本 | corrected LEA + cost；最好加入自然发生 cyclic 正负例。若无自然集，明确只评估 stress-test，不声称自然风险 recall |
| Meta（3.0） | 已看到 rebuttal，但公平性、成本、组件和现实意义仍未完全落稿 | P0 全部可信入稿；再增加 clean/natural 边界和清楚的 mechanism story，避免只是把 rebuttal 表格搬进正文 |

## 4. 实验优先级

### P0：投稿底线，先完成

1. **LEA**：补跑错配 `36/160`；最终 `160/160` fingerprint、schema、denominator 可核验。GPT-4o 与 Gemini 2.5 Pro 分别代表明显获益和强 full-context 区间，必须逐模型报告，不能只报 aggregate。
2. **Stage-1**：`17 cases × 3 variants = 51 jobs`。正文优先检验 critical-pair revisiting 与 guided-vs-random window；relation memory、OC、closure 若仍混合，只进附录或降为实现细节。
3. **Stage-2**：已完成，`0 API`。正式补 physical-SCC cluster interval 与 replacement-rescue 轨迹分析；旧 `-25` 永久弃用。
4. **Cost**：最小主表补 GPT/Flash `54 jobs`，并补 `6` 个不可验证 GPT Naive cells；strict all-case denominator，invalid 不剔除，不用跨批 runtime 做 headline。
5. **匿名复现包**：stable case manifest、prompt/config hash、aggregation script、结果索引和一键 README。

最小正式修复为 `147 jobs = 51 + 36 + 54 + 6`；加 `9` 个 smoke 为 `156`。若再做 Qwen cost `18 jobs`，与当前完整 manifest 一致为 `174`。Stage-2 不增加 API 成本。

### P1：真正抬分

旧 12-case expert audit 及其论文数字全部保留，不重标、不重算。专家集只做增量：新增 7 个唯一 pre-injection originals、24 个 probability-sampled untouched SCC，以及 12 个 independently enriched natural candidates，共 43 个新增 cases、129 份专家判断。完整冻结方案、工作量和 claim boundary 见 [EXPERT_SET_PLAN_ZH.md](EXPERT_SET_PLAN_ZH.md)。

标签冻结后，在 43 个新增 cases 上运行 `3` 个 deployable methods（one-shot、LEA、SA）× `2` 个代表模型，共约 `258` method-case runs；逐轨报告 expert-evidence recall、over-reporting/abstention、excess-node burden 和宽置信区间。旧 injected audit 与新增结果不 pooled，也不重新估计旧数字。若自然正例过少或没有冻结的 deployable abstention rule，则 natural 结果降为附录 pilot，并继续保持 controlled stress-test 口径。

另做两个低成本补充：

- 离线计算 endpoint density、excess-node rate 和 bridge-aware cleanliness；
- 在固定小子集上做 relation-prior `nominal / -20% / +20%` 的 contemporaneous pilot。若敏感，则明确写成 task-tuned heuristic。

### P2：预算充足再做

- 将 LEA 从当前两模型 `160` 扩到原始四模型 `320`；新增约 `160` jobs。若不扩，必须明确其为预定两能力区间诊断，不能支撑四模型统一结论。
- 只有存在 task-compatible 输出接口时，才适配一个已发表 document-graph/GraphRAG 系统；否则说明任务不兼容，不做名义上的伪公平比较。
- 并发 `p=1/2/4/8`、更多 size bins、convergence 和额外模型只进附录，不优先占用主预算。

## 5. 正文最短证据链

正文只保留四步：

1. **公平性**：one-shot / LEA / SA 的 matched comparison，含 model heterogeneity；
2. **机制**：critical-pair revisiting + replacement core；
3. **代价**：Risk-all–calls/tokens–invalid 的 cost-performance；
4. **边界**：natural/clean 结果与 decision-support scope。

Oracle-risk 320-case 结果降为 compact diagnostic；完整模型/领域 breakdown、弱或负组件消融、sensitivity、cleanliness、convergence 和完整成本放附录。主文通过移动 TreeMCTS 诊断图、domain table 和 convergence 图腾出版面，不在旧稿上继续追加。

## 6. Go / No-Go

**OA/meta 3.5 目标 GO：** P0 全部通过；clean-negative、cleanliness、sensitivity 和 physical-SCC cluster uncertainty 完成；正文形成公平 baseline → 两个核心机制 → 成本/异质性 → 现实边界的闭环。自然正负例专家集完成时，meta 3.5 的把握明显更高。

**Findings 口径 GO：** P0 通过但没有自然集；保留 controlled stress-test / model-dependent / decision-support 的窄口径，不把稿件包装成真实风险部署验证。

**NO-GO：** 仍使用旧 rebuttal 数字；LEA 或 ablation 身份不能 100% 核验；valid-only 与 all-case 混用；隐藏不利模型；没有 clean evidence 却继续声称 risk detection；或 SA 被 LEA 在性能与成本上同时 Pareto dominate 后仍保持“方法整体优越”表述。

执行顺序：`冻结 claim/stat protocol → 9-job smoke → Stage-1 与 LEA → cost → P0 editorial gate → natural/clean suite → 聚合与 cluster inference → 重写正文与 revision explanation`。

现有操作清单见 [plan.md](plan.md)，精确补跑范围见 [rerun_scope.json](manifests/rerun_scope.json)，已修复 Stage-2 见 [stage2 report](experiments/stage2_paired_replay_80case_identity_v1_final/stage2_paired_core_report.md)。

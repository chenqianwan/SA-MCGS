# SA-MCGS 十月 2026 ARR 回收与改稿计划

更新日期：2026-08-27

目标轮次：October 2026 ARR（官方截止 2026-10-12）

工作分支：`2026NAACL/SA-MCGS`

## 一、结论先行

这篇工作有明确的回收空间，但不应把 rebuttal 表格直接追加到旧稿。最合理的新版证据链是：

> 公平的 graph-aware baseline → 经过验证的机制归因 → 成本—性能权衡 → 模型异质性与适用边界。

建议将中心结论收窄为：

> 在 controlled structural-risk stress test 中，SA-MCGS 是一种额外的 inference-time graph-search 选项：它用更多 LLM calls/tokens 换取困难 cyclic SCC 上更完整的 benchmark-defined endpoint recovery；相对 matched local decomposition 的收益依赖模型和案例难度，并非跨模型一致。

在重跑完成前，不应把 rebuttal 中的 LEA、组件消融和成本数字写进摘要或正文。原因不是单纯缺少统计检验，而是新增实验 runner 存在 SCC case 身份匹配错误；其中所谓 `monotone-core` 消融也没有实现真正的 monotone accumulation。

## 二、材料边界

- `8229_Risk_Subgraph_Extraction_ (3).pdf` 是 rebuttal 前的 18 页论文：正文 8 页、参考文献和 Appendix A--J；不包含 reviewer reports、rebuttal、meta-review 或 EMNLP decision。
- EMNLP reject 决定没有提供新的技术意见。十月 ARR 应主要回应此前 ARR reviewers、meta-review，以及 rebuttal 中承诺但尚未可靠落稿的工作。
- 正式修改源是 `paper/latex/acl_latex.tex`。`submission/arr_submission_20260525_210437/` 是历史提交快照，应保持归档。
- `paper/PAPER_FRAMEWORK.md` 仍以旧的 one-shot Naive、relation-first memory 和 OC 为中心，且部分数字过时。应先重写 claim–evidence map，再改 LaTeX。

## 三、先冻结：当前 rebuttal 数字的证据状态

| 证据 | 当前状态 | ARR 中的处理 |
|---|---|---|
| 原稿 locked 320 model-case 结果 | 可保留；没有被本次 `find_scc` bug 直接牵连，但主要 comparator 是 ground-truth-selected oracle-risk baseline | 作为广覆盖 stress-test 结果；不再单独承担公平性主张，并把模型级异质性移入正文 |
| 12-case 专家审计 | 可保留，支持“注入冲突可被识别” | 不外推为自然风险分布；`Risk-all` 攵称 benchmark-defined endpoint completeness |
| LEA matched 160 | **暂不可入稿** | 修复稳定 case identity 后，在原始 320 cases / 4 models 上重跑或明确子集边界 |
| Stage-1 ablations | **暂不可入稿** | 与 contemporaneous Full control 成对重跑；优先验证 critical-pair revisiting |
| Stage-2 dynamic-core ablations | **暂不可入稿** | 先实现真正的 monotone/no-replacement policy，再重跑 |
| 40-case cost audit | **暂不可入稿** | 修复 case identity；统一 strict denominator；同时报告 one-shot、deployable LEA/SA 和 ten-attempt diagnostic 的成本 |
| clean/non-risk SCC、false positive | 缺失 | rebuttal 承诺过，至少完成一个冻结负例集与 abstention 规则 |
| subgraph precision / irrelevant-node rate | 缺失 | 加入 excess-node / endpoint-density 等保守诊断，说明 bridge/context nodes 不一定是无关节点 |
| coefficient sensitivity | 缺失 | 对主要 prior/core 参数做冻结的小规模扰动实验 |
| naturally occurring risks | 缺失 | 资源允许时增加小型独立专家标注正负集；否则显著收窄外部有效性表述 |

### 3.1 P0：SCC 身份匹配错误

`emnlp2026_discussion/run_cost_audit_clean.py` 当前通过 `scc_id` 匹配 SCC，并在 size 不同后仍回退到同 id：

```python
for scc in graph.sccs:
    if scc.id == case["scc_id"] and scc.size == case["scc_size"]:
        return scc
matches = [scc for scc in graph.sccs if scc.id == case["scc_id"]]
if matches:
    return matches[0]
```

Tarjan 遍历产生的 SCC id 不是跨进程稳定身份，SEC EX-21 尤其容易变化。已能直接观察到的 size mismatch 包括：

| 结果集 | 明显错配 |
|---|---:|
| LEA matched 160 | 33 / 160 |
| Stage-1 每个 rerun variant | 16 / 80 |
| Stage-2 每个 rerun variant | 5 / 40 |
| GPT-4o cost audit | 8 / 40 |
| Gemini 2.5 Flash cost audit | 9 / 40 |
| Qwen cost audit | 9 / 40 |

仅过滤 size mismatch 仍不安全：两个 SCC 可能大小相同但节点集合不同。因此所有依赖该 loader 的新增数字均按 provisional 处理，不能从“看起来匹配”的行中挑结果入稿。

#### 修复规范

1. 为每个 case 生成不可变 `case_uid`：`domain + source_document_id + sorted(node_ids) + sorted(internal_edge_signature)` 的哈希。
2. case manifest 保存 `expected_node_ids`、`expected_size`、`expected_edge_signature`、root/witness/affected IDs 和 injection template/version。
3. loader 只允许 exact node-set/signature match；找不到或多匹配时 fail closed，禁止按 `scc_id` fallback。
4. 注入前后分别 assert：原 SCC fingerprint、注入节点、root/witness/affected IDs、node count 和 edge count。
5. 每条结果记录 expected/actual fingerprint、代码 commit、prompt hash、model snapshot、seed、temperature、token/call/runtime denominator。
6. 增加 regression test：同一数据在不同进程、不同迭代顺序下必须解析到同一物理 SCC。

可复用 `experiments/main_experiment/boosted_naive_baseline/run_boosted_naive_round_robin.py` 中按保存的 `scc_clause_ids` 重建 SCC 的思路。canonical case manifest 应复制到仓库内并版本化，不能继续依赖其他 worktree 的路径。

### 3.2 P0：`monotone-core` 名称与实现不符

`run_component_ablation_stage0.py` 的 `monotone-core` 分支只是关闭 protected critical-pair seeding 和 final pair closure；它仍从当前 evidence 重新计算最终集合，没有维护 `H_t \supseteq H_{t-1}`，因而不能支持“dynamic replacement 优于 monotone accumulation”的主张。

需要实现一个真正对照：

- `monotone-union`: `H_t = H_{t-1} \cup \Delta_t`，达到预算后不替换；或
- `locked-no-replacement`: 节点首次进入 core 后不可被移出，在相同 cap 下运行。

两者必须与同批 cases、同模型、同 prompt/config、同时间窗口内重跑的 Full 配对。原来的 `-25` 只可作为 debugging signal，不可作为论文结果。

### 3.3 现有消融已经提示应收缩机制主张

即使暂不把数值当作最终证据，方向性诊断也很明确：

- critical-pair revisiting 值得作为第一核心机制继续验证；
- removal of relation-first memory 没有造成下降，当前不能声称它独立驱动性能；
- random-window、OC/core signal、final pair closure 的效果在诊断统计中不稳定；
- 因此新版贡献应优先围绕 `critical-pair revisiting + replacement-based dynamic core`，其余模块降为实现细节或 setting-dependent components，除非重跑改变结论。

## 四、统一重跑协议

### 4.1 最小可提交版本（P0）

1. **LEA 公平基线**
   - 复用原始 frozen 80 structural cases，覆盖与主稿一致的四个模型，共 320 model-case pairs。
   - LEA 使用与 SA-MCGS 相同的 local evidence schema；固定窗口检索和透明聚合；不使用 rollout selection、critical-pair memory、OC/core signals 或 replacement core。
   - 同时报告 LEA 的自然调用预算和 equal-call/equal-token control，画出 Risk-all–calls/tokens Pareto curve，避免把收益简单归因于更多调用。
   - 将 Gemini 2.5 Flash 明确标记为独立 cost/model-sensitivity diagnostic，而不是混入原始四模型 aggregate。

2. **机制消融**
   - 第一优先级：`no critical-pair revisit`、真正的 `no replacement/monotone`。
   - 第二优先级：guided vs random window。
   - 第三优先级：relation memory、OC signal、final pair closure；若资源不足，完整结果进附录，不把它们列为独立贡献。
   - 每个 variant 都必须同时重跑 Full；禁止把旧 locked Full 与后来 API run 横向比较。
   - 至少覆盖一个明显获益模型和一个强 full-context / 弱获益模型，以检验 interaction，而不是只在 GPT-4o 上归因。

3. **成本—性能**
   - deployable main comparison：one-shot full-SCC、LEA、SA-MCGS。
   - diagnostic comparison：self Top-3、oracle-risk Top-3，明确后者使用 ground truth，不能部署。
   - 同表报告 strict all-case Root@3/Risk-any/Risk-all、invalid rate、calls、input/output/total tokens、serial runtime、实际 concurrency。
   - 若声称并行降低 wall-clock time，至少做 `p = 1, 2, 4, 8` 的小规模实测；理论公式不能替代实测，而且 memory/UCB 更新存在顺序依赖。
   - 区分 algorithmic/logical calls 与 provider-recorded API calls（含 retries），并把 invalid requests 已消耗的 tokens/runtime 计入成本。

当前 GPT-4o cost 表还有一个独立的 denominator 问题：Naive 的性能与成本只在 34 个 valid outputs 上平均，但表中同时写了 40 cases 和 15% invalid。若按全部 40 planned cases 进行 strict 汇总，诊断重算约为 Root@3 25.0%、Risk-any 62.5%、Risk-all 25.0%、23.76K tokens/case 和 39.2s/case；这些数字同样受 SCC bug 影响，只用于说明为何正式表必须统一 denominator，不能入稿。

4. **统计协议**
   - binary paired metrics 报绝对百分点差和 paired interval；可补 McNemar exact test。
   - 主 CI 按 underlying structural case / SCC 做 cluster bootstrap，避免把同一 case 在多个模型上的重复当作独立样本。
   - 明确 unavailable/invalid output 的 strict denominator；禁止 valid-only baseline 与 all-case SA/LEA 直接并列。
   - 报模型级结果和 interaction；aggregate 不能掩盖 Gemini Pro/DeepSeek 等强模型上的反向结果。
   - 多个 ablations/comparisons 做 Holm correction；连续型成本与 compression 报 median/IQR 和 paired bootstrap CI。
   - “long-context pressure” 应按实际 serialized tokens/characters 建模，并控制 domain/model；旧的 short/mid/long Risk-all 增益并不单调，不能仅凭 node-count bins 写成增益随长度增加。

### 4.2 reviewer 尚未真正解决的实验（P1）

1. **clean/non-risk set**：冻结真实 SCC，不注入风险；先定义 `abstain/no-risk` 机制，再报告 false-positive / over-reporting。
2. **subgraph cleanliness**：报告 endpoint density、excess-node rate、bridge-node-aware precision；不要把所有非 endpoint 节点都自动视为错误。
3. **prior/core sensitivity**：对主要阈值和权重做 ±10%/±20% 或预注册网格，报告性能与 core size 的稳定性。
4. **natural cases**：最高价值的扩展是一个小型、独立专家标注、同时含正负例的 naturally occurring cyclic set。它同时回应外部有效性、假阳性、现实意义和 decision-support 四项关切。
5. **release package**：匿名代码、case manifest、prompt/config hash、结果聚合脚本和 README；确保所有表可由 frozen artifacts 一键复现。
6. **prompt parity**：将同一个 literal core risk-rubric block 原样嵌入所有 adapter，并保存 hash；已有 E5 只是 post-hoc semantic abstraction，不能写成 exact prompt parity。
7. **single source of truth**：更新 `experiments/main_experiment/MANIFEST.json`；它目前仍记录 one-shot `48/72/47`，与现稿 boosted `58/79/62` 主表不一致。

## 五、论文主线怎么改

### 5.1 摘要与贡献

修改 `paper/latex/acl_latex.tex:54-55` 与 `:81-88`：

- 首句就说明是 controlled structural-risk stress test；
- 主 headline 应优先使用验证后的 matched LEA，而不是只对 oracle-risk Naive；
- 明写 model-dependent 和 additional inference cost；
- 不再把 relation-first memory 写成已被独立消融支持的核心贡献；
- 将 decision-support 边界放进摘要末句或引言贡献边界。

在重跑前可先使用不带数字的占位结论：

> Compared with a matched graph-aware local aggregation baseline, SA-MCGS improves endpoint-complete recovery in difficult cyclic components for some models, while offering little or no gain for already-strong full-context models. The improvement comes with substantially more calls and tokens.

### 5.2 Method

- `:195-213` relation-first memory：保留为 evidence representation，但不声称它独立贡献显著；若 factorial ablation 仍不支持，则压缩篇幅。
- `:215-217` OC：统一改称 `online quantile conflict signal` 或 `calibration-inspired conflict signal`；不要暗示 conformal coverage guarantee。
- `:219-230` dynamic core：删除 Nemhauser approximation 暗示。当前正的 induced-edge pair term 通常体现互补性，不能直接套 monotone submodular greedy guarantee。建议改为：

> Core construction is a budgeted heuristic over node and relation evidence. We use greedy replacement for computational efficiency and do not claim an approximation guarantee for monotone submodular maximization.

- `:255` computational feasibility：用实测 calls/tokens/runtime 替代理论性“可比 token budget”主张。

### 5.3 Experimental setup 与 baselines

修改 `:302-310`：

- 首次完整定义 one-shot Naive、self Top-3、oracle-risk Top-3 和 LEA；
- 明确 oracle-risk 是 ground-truth-selected、non-deployable diagnostic；
- LEA 称为 `a graph-aware decomposed baseline`，除非严格复现某项 GraphRAG 方法，否则不要写成 “GraphRAG baseline”；
- 统一 SCC size bins，避免旧主实验、LEA、ablation 三套 small/mid/long 阈值混在一张表中。

### 5.4 Main results 与 Analysis

修改 `:312-353`：

- 保留原 320-case Figure 3，定位为 broad stress-test comparison；
- 新增一个紧凑的 matched LEA 主表，放 overall + model-level heterogeneity；
- 删除 `:330` 的 “The gains are not carried by a single model.”，改为直接承认模型依赖；
- `:326` 的交叉引用当前渲染为 “Appendix 9”，改为 `Table~\ref{tab:reliability}` 或正确 appendix section 引用；
- 将 rollout-convergence Figure 4 移入附录；正文版面改放经过验证的 component attribution 和 cost–performance；
- 组件表只突出通过统一 protocol 支持的机制，负结果也必须保留。

### 5.5 Conclusion、Limitations 与伦理边界

修改 `:370-378`：

- 结论不再声称跨四模型普遍优于 baseline；
- 明确 injected stress test 不估计自然风险 prevalence 或部署性能；
- 系统是 evidence prioritization / human decision support，不是 automated legal、financial、regulatory 或 software-risk adjudication；
- 补充 false positives、false negatives、graph-construction error 和 overtrust；
- 人类审计只能支持样本中的 semantic recognizability，不能证明自然分布等价。

## 六、正文 8 页的空间重新分配

当前正文已经占满 8 页，但可以通过“替换”而非“追加”腾出空间：

| 动作 | 预计收益 | 用途 |
|---|---:|---|
| 将全宽 rollout-convergence Figure 4 移附录 | 约 0.5--0.8 页 | matched LEA + cost/ablation 核心证据 |
| domain table 只保留压缩版，详细 processing 放附录 | 约 0.2--0.3 页 | model heterogeneity |
| 合并 Intro、Why TreeMCTS、Related Work 中重复的 cycle 动机 | 约 80--120 词 | scope 与 claim boundary |
| 主文只留 overview algorithm，四个实现伪代码留附录 | 约 0.2--0.4 页 | 组件消融解释 |
| 合并重复 selector/reliability tables | 至少一个 float | 一张统一 cost–performance table |
| Conclusion 压到 45--60 词 | 约 30--45 词 | 留给局限性过渡 |

建议正文最终只保留：

1. 方法 overview 图；
2. 320-case broad result；
3. 一个包含 LEA 与 model heterogeneity 的主表；
4. 一个紧凑的 validated ablation / cost–performance 组合表或三面板图。

完整 calls/tokens/runtime 分布、全部 ablations、concurrency、clean cases、sensitivity、convergence 和 prompts 均进附录。

## 七、建议的新 claim–evidence ledger

| Claim | 正文所需证据 | 边界 |
|---|---|---|
| SA-MCGS 在困难 cyclic SCC 上改善 endpoint completeness | exact-matched LEA + paired uncertainty | 只按 model/size 支持，不写 uniform superiority |
| 收益不只是 local decomposition/schema simplification | LEA 使用相同 local schema | 需要确认 aggregation budget 与窗口覆盖公平 |
| critical-pair revisiting 有独立作用 | contemporaneous paired ablation | 不从单次 API run 外推所有模型 |
| replacement core 优于 no-replacement accumulation | 正确实现的 monotone/no-replacement ablation | 不再使用当前 mislabeled result |
| 额外 compute 换取更完整结果 | 同 denominator cost–performance | 不把 ideal parallelism 当成实测 |
| 输出适合人类审查 | expert audit + clean/natural positive/negative sample | 不等同安全部署或自动裁决 |

## 八、六周执行表

| 日期 | 交付物 | Go/No-Go gate |
|---|---|---|
| 8/27--9/2 | stable case manifest、exact matcher、regression tests；修正 monotone ablation；冻结统计协议 | 任一 runner 仍依赖 numeric `scc_id` fallback 则不得开正式跑 |
| 9/3--9/14 | 320-case LEA；关键机制的 paired Full/ablation；统一 cost audit | exact fingerprints 100% 匹配，表可由原始 JSON 一键重建 |
| 9/15--9/23 | clean/non-risk、cleanliness、sensitivity；可行时补 natural expert set | 至少完成 clean negatives + abstention，否则必须在稿中声明未评估 FPR |
| 9/24--10/2 | 重写 PAPER_FRAMEWORK、Abstract/Intro/Setup/Results/Discussion；生成新主图表 | 每个摘要数字都有 frozen artifact 和脚本来源 |
| 10/3--10/7 | 全文压缩、复现实验、匿名 release、统计复核 | 主文 ≤8 页；模型级反向结果在正文可见 |
| 10/8--10/11 | explanation of revisions、逐 reviewer matrix、格式与匿名审计 | previous submission link、逐点回复、section/line references 齐全 |
| 10/12 | October ARR submission | 最终 PDF、supplement、revision explanation、checklist 同步冻结 |

## 九、ARR resubmission package

ARR resubmission 不是只上传新版 PDF。需要同时准备：

1. previous submission link；
2. overview of changes；
3. 对 meta-review 和三位 reviewer 每条 weakness/suggestion 的 point-by-point response；
4. 每项修改对应的新 section/line number；
5. 未采纳建议的理由与论文中新增的 limitation；
6. 匿名代码与数据 supplement；
7. reviewer-registration / Responsible NLP checklist 等提交项。

建议 revision explanation 用以下四组标题组织，而不是按 rebuttal 时间线堆砌：

- Fair baselines and output-schema controls
- Component attribution and corrected protocol
- Cost, reliability, and statistical uncertainty
- Scope, natural validity, and decision-support boundaries

## 十、最终 Go/No-Go 标准

满足以下条件才把 rebuttal 结果写进正文：

- 100% exact SCC fingerprint match；
- Full 与 variant 是 contemporaneous paired runs；
- `monotone/no-replacement` 名实相符；
- performance 和 cost 使用同一 case denominator；
- 至少一个公平 LEA 主比较和模型级 breakdown；
- 反向或无增益结果不被 aggregate 掩盖；
- 摘要数字均能追溯到 frozen artifact + aggregation script；
- clean negative / false-positive 证据完成，或在正文明确承认仍未评估。

若到 9 月下旬仍无法完成稳定重跑，宁可提交一个更窄、只使用可靠 locked evidence 的版本，也不要把有 case-identity 风险的 rebuttal 数字写入论文。

## 十一、Git 状态说明

- `main` 已通过 merge commit 吸收原本的本地 `2026NAACL`。
- 因为 Git 不能同时保留 `refs/heads/2026NAACL` 和 `refs/heads/2026NAACL/SA-MCGS`，旧本地分支已改名为 `archive/2026NAACL`。
- 当前分支为用户指定的 `2026NAACL/SA-MCGS`。
- 原工作区的 tracked/untracked 改动均已恢复，未被纳入本次 merge commit。
- 尚未 push。远端仍有 `origin/2026NAACL`；它与远端层级名 `2026NAACL/SA-MCGS` 存在同样的 ref 冲突。推送新分支前需先决定是否删除或重命名远端旧分支。

## 十二、官方时间与格式依据

- ARR dates: <https://aclrollingreview.org/dates>
- ARR CFP / resubmission policy: <https://aclrollingreview.org/cfp>

官方页面列出 October 2026 ARR 截止日为 2026-10-12、cycle end 为 2026-12-20，并对应 NAACL 2027 / COLING 2027。Long paper 主文上限为 8 页；Limitations 和结论后的 Ethical Considerations 不计入该 8 页。Resubmission 必须提交 previous-submission link 与逐点 revision explanation，忽略已有评审意见可能导致 desk rejection。

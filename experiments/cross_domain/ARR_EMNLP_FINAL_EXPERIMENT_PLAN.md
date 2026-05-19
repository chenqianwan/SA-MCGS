# ARR/EMNLP Final Experiment Plan

最后更新：2026-05-17  
状态：主计划文件 / single source of truth  
目标会议：ARR -> EMNLP

> 后续所有实验决策、补跑任务、打标任务和论文实验叙事，都以本文为准。旧窗口里的口头计划、旧 `memory_stress` 结果、旧 diagnostic 报告只作为背景，不作为论文主结果口径。

---

## 0. 一句话主叙事

我们用 AlphaGo/MCTS 风格搜索处理结构性问题；但真实依赖图里会出现 SCC，导致普通搜索无法稳定推进。SA-MCGS 的核心贡献是：先定位 SCC，再通过多轮 rollout、OC 证据和风险子图压缩，把循环结构坍缩成一个可解释的评估点 / risk subgraph。

论文主张不是“LLM 更会找异常”，而是：

> SA-MCGS turns cyclic structural risk into a compact, evidence-backed risk subgraph, improving risk localization and auditability under long-range SCC dependencies.

---

## 1. 当前实验状态

### 1.1 可以作为主结果基础的内容

- `critical_paper_v3_b60`：目前最接近正式主结果的 critical run。
  - 覆盖：Debian、SEC EX-21、BGB、CUAD。
  - 模型：`gpt-4o`、`deepseek-v3`。
  - 方法：Naive direct subgraph vs SA-MCGS。
  - 用途：主结果基础，但需要用最终 frozen setting 重新固定一次口径。
- `compression_profile_sweep_b60_net`：用于说明 compression profile 的 trade-off。
  - 用途：参数选择 / ablation / appendix。
- `SEVERITY_GRID_ANALYSIS.md`：用于 severity 和 domain 差异分析。
  - 用途：辅助解释，不直接作为最终主表。
- `CRITICAL_FAILURE_CASE_AUDIT.md`：用于解释 risk-all / core retention 失败。
  - 用途：failure analysis / limitation / appendix。

### 1.2 不进入主结果的内容

- 旧 `explicit` / old `memory_stress` sanity-check。
- 旧 score-only Naive。
- 旧 Wikipedia gap / synthetic long-cycle 结果。
- fallback 到错误 SCC 长度的结果，例如 BGB requested 14 -> actual 3。

这些可以放 appendix 解释实验设计演进，但不能写成主证据。

---

## 2. Reviewer 风险与对应补实验

| Reviewer 可能质疑 | 风险 | 必须补的实验 |
|---|---|---|
| Baseline 不公平 | SA-MCGS 调用 LLM 更多，Naive 只 one-shot | Budget-matched Naive |
| 算法贡献不清楚 | SA-MCGS 看起来像 heuristic + prompt trick | SA-MCGS ablation |
| 模型覆盖不足 | 只在 GPT-4o / DeepSeek-V3 上成立 | Strong model robustness |
| 数据集不够可信 | 注入冲突是否自然、严重、真实 | Human validation |
| 指标口径不清楚 | Risk-any / Risk-all / compression 容易被误读 | 固定指标定义 + CI |
| SCC 长度不够强 | 中小环太容易，长环才体现价值 | Hard subset + long SCC focus |

---

## 3. 模型计划

### 3.1 主表模型

主表只用以下两个模型全量跑：

- `gpt-4o`
- `deepseek-v3`

理由：

- 和前置论文 / benchmark 口径对齐。
- 现有实验最完整。
- 成本可控。
- 主叙事最干净。

### 3.2 补充模型

补充模型只跑 hard subset，不跑全量。

XHub `/v1/models` probe 结果（2026-05-17）：

- `claude-3-5-sonnet-20241022`：可用。
- `qwen2.5-72b-instruct`：可用。
- `Llama-3.3-70B-Instruct`：未发现精确可用 ID。
- `Gemini 2.0 Flash`：未发现精确可用 ID；可用相近项为 `gemini-2.5-flash`、`gemini-2.5-flash-nothinking`、`gemini-2.5-pro`。

优先级：

1. `claude-3-5-sonnet-20241022`
   - 主流闭源强模型。
   - reviewer 熟悉。
   - 成本比 Opus 可控。
   - 建议必跑。
2. `qwen2.5-72b-instruct`
   - 主流 open-weight 70B 强模型。
   - 用于证明不是 closed-model 特例。
3. `gemini-2.5-flash-nothinking` 或 `gemini-2.5-flash`
   - 只作为 low-cost / fast-model appendix。
   - 不和 GPT-4o / DeepSeek-V3 放在同级主表里解释。
4. `gemini-2.5-pro`
   - 可用，但可能成本偏高。
   - 只有在额度宽松时作为 Gemini strong-model appendix。

暂不跑：

- `Llama-3.3-70B-Instruct`：XHub 当前模型列表没有精确 ID。
- `deepseek-r1-distill-llama-70b`：虽然是 Llama 70B distill，但不是标准 Llama-3.3-70B baseline，容易让模型覆盖叙事变脏。

最低可接受补充模型：

- `claude-3-5-sonnet-20241022`
- `qwen2.5-72b-instruct`

如果额度不足，只跑 Claude + Qwen。Gemini Flash 只能作为 low-cost appendix，不能替代 Claude/Qwen 的 robustness 角色。

### 3.3 模型 registry 更新要求

当前 `run_cross_domain_battle.py` 只注册了：

- `gpt-4o`
- `deepseek-v3`

正式跑补充模型前，把以下可用模型加入 `BATTLE_MODELS`，但默认不跑，必须通过 `--models` 显式指定：

- `claude-3-5-sonnet-20241022`
- `qwen2.5-72b-instruct`
- `gemini-2.5-flash-nothinking`
- `gemini-2.5-flash`
- `gemini-2.5-pro`

结果报告中使用“论文显示名 + 实际 model_id”双列记录，避免 reviewer 或复现实验时混淆模型版本。

---

## 4. 必补实验

### A. Main Critical Run

Run tag：`critical_balanced_b60_final`

配置：

- Domains：Debian、SEC EX-21、BGB、CUAD
- Models：`gpt-4o`、`deepseek-v3`
- Methods：Naive direct subgraph vs SA-MCGS balanced
- Severity：critical
- Budget：SA-MCGS 60 rollout
- Injection：`memory_stress` profile 内部版本 `structural_simple_v1`
- SCC source：real SCC only

为什么必须补：

- 这是论文主结果表。
- 当前已有结果来自多个阶段，混入过旧注入、不同 compression profile、不同报告口径。
- EMNLP reviewer 会非常在意 main table 是否来自同一套 frozen setting。

它回答的问题：

> 在严格 matched setting 下，SA-MCGS 是否比 one-shot direct subgraph 更稳定地定位结构性风险，并生成可解释风险子图？

主要指标：

- `Root@3`：是否更能找回风险源。
- `Risk-any`：是否至少保留一个可修复风险入口。
- `Risk-all`：critical 下是否能完整保留关键风险端点。
- `Compression`：风险子图是否比原 SCC 小。
- `Effective OC`：SA 是否真的找到了结构性证据，而不是随机猜测。
- `LLM calls / token cost`：成本。

验收标准：

- 无 API / JSON parse error。
- 每个 matched case 有 Naive 和 SA-MCGS 两条结果。
- 每个结果保存 root / witness / affected / final subgraph / OC evidence。
- 结果表报告 `x/y + 95% CI`，不只报告百分比。

---

### B. Budget-Matched Naive

Run tag：`budgetmatched_naive_b60_hard`

配置：

- Hard subset：
  - BGB-25
  - CUAD-25
  - CUAD-34
  - SEC-18
  - Debian-12
- Models：`gpt-4o`、`deepseek-v3`
- Baseline：Naive direct-subgraph self-consistency
- 做法：同一 SCC 多次 one-shot，随机 node order / edge order，聚合多个 direct subgraph 输出。

为什么必须补：

- SA-MCGS 调用 LLM 更多，reviewer 一定会问：

> 你是不是只是花了更多 token，所以赢了？

- 直接拿 one-shot Naive 对比 rollout-based SA，会被认为不公平。
- Budget-matched Naive 是最关键的防守实验。

它回答的问题：

> 如果给 Naive 类似的 LLM 调用预算，它能否通过多次采样和聚合达到 SA-MCGS 的效果？

主要指标：

- 同预算下 `Root@3`。
- 同预算下 `Risk-any` / `Risk-all`。
- Naive 聚合子图大小。
- Naive 聚合 compression。
- Naive 是否仍缺少 `Effective OC`。
- Cost-normalized gain：每单位 LLM call / token 的收益。

预期论文写法：

> Even under a matched inference budget, repeated one-shot prompting does not reliably recover the same compact, evidence-backed risk subgraph, indicating that the gain is not merely due to additional LLM calls.

---

### C. SA-MCGS Ablation

Run tag：`sa_ablation_b60_hard`

配置：

- Hard subset：
  - BGB-25
  - CUAD-25
  - CUAD-34
  - SEC-18
  - Debian-12
- Models：`gpt-4o`、`deepseek-v3`
- Budget：60 rollout

消融项：

- full SA-MCGS
- no relation-first memory
- no dynamic core replacement
- no critical-pair reinforcement

为什么必须补：

- Reviewer 不只会问“有没有提升”，还会问：

> 提升来自哪个算法组件？

- 如果没有 ablation，SA-MCGS 会看起来像一组 heuristic。
- Ablation 可以说明每个机制都服务于 SCC 风险坍缩。

它回答的问题：

> SA-MCGS 的收益是否来自 relation-first evidence accumulation、dynamic core retention 和 critical-pair reinforcement，而不是 prompt wording？

主要指标：

- 去掉 relation-first 后，`Root@3` 是否下降。
- 去掉 dynamic core 后，`Compression` 或 `Risk-any` 是否变差。
- 去掉 critical-pair reinforcement 后，`Risk-all` 是否下降。
- full model 是否在 `Risk-all + Compression` 上有最佳 trade-off。

预期论文写法：

> Relation-first memory improves long-range risk localization, dynamic core replacement controls subgraph size, and critical-pair reinforcement prevents high-severity endpoint evidence from being overwritten by later noisy observations.

---

### D. Supplementary Model Robustness

Run tag：`model_robustness_hard_b60`

配置：

- Hard subset：
  - BGB-25
  - CUAD-25
  - CUAD-34
  - SEC-18
  - Debian-12
- Methods：Naive direct subgraph vs SA-MCGS balanced
- Severity：critical
- Budget：60 rollout

模型优先级：

1. `claude-3-5-sonnet-20241022`
2. `qwen2.5-72b-instruct`
3. `gemini-2.5-flash-nothinking` 或 `gemini-2.5-flash` appendix only
4. `gemini-2.5-pro` optional strong appendix, only if budget allows

为什么需要补：

- EMNLP reviewer 可能会问：

> 这个方法是不是只对 GPT-4o / DeepSeek-V3 有效？

- 全量跑更多模型成本太高，也会让主表变乱。
- 只在 hard subset 上做 robustness，是成本和说服力的平衡。

它回答的问题：

> SA-MCGS 的趋势是否能迁移到其他主流模型族？

主要指标：

- Claude/Qwen 上是否保持同方向提升。
- open-weight 70B 模型上是否仍能看到 SA 的风险子图优势。
- Gemini Flash 如果跑，只报告 low-cost lower-bound，不与强模型同列主表比较。

预期论文写法：

> The main results use GPT-4o and DeepSeek-V3 following prior work; additional hard-subset experiments on Claude Sonnet and an open-weight 70B model show that the trend is not model-specific. Gemini Flash is reported only as a low-cost appendix setting.

---

### E. Rollout / Convergence Curve

Run tag：不必重跑，可从 60 rollout trace 截取。

配置：

- 截取 rollout：
  - 5
  - 10
  - 20
  - 40
  - 60
- 按 domain 和 SCC size 画曲线。

指标：

- Risk-any
- Risk-all
- Effective OC
- Compression
- Core size

为什么必须补：

- SA-MCGS 的核心不是一次性 prompt，而是持续搜索。
- 如果没有收敛曲线，很难支撑 “rollout 带来证据积累” 这条主张。
- 这也是和 MCTS / AlphaGo 叙事最直接连接的实验。

它回答的问题：

> 随着 rollout 增加，SA-MCGS 是否更稳定地收敛到风险区域，而不是随机波动？

主要观察：

- `Effective OC` 是否随 rollout 增长。
- `Risk-any` / `Risk-all` 是否在中后期稳定。
- `Compression` 是否保持在可解释范围。
- 长 SCC 是否比短 SCC 更体现 rollout 价值。

---

### F. Human Validation / Annotation

Run tag：人工标注，不需要 LLM run。

为什么必须补：

- 我们的缺陷是结构性注入，reviewer 可能质疑：

> 这些 injected conflicts 是否真实、自然、严重？

- 仅靠自动 GT 不够，尤其是 CUAD 和 BGB 这类法律文本。
- 人工标注可以证明实验不是自嗨构造。

它回答的问题：

> 注入的 critical conflict 是否真的成立？SA 输出的风险子图是否更适合人工审计？

---

## 5. 人工打标计划

### 5.1 需要提前通知标注的数据集

需要人工打标的是四个主数据集：

- Debian
- SEC EX-21
- BGB
- CUAD

Wikipedia 暂时不打标，不进主结果。

### 5.2 推荐打标量

论文级推荐：80 个 case。

- Debian：20
- SEC EX-21：20
- BGB：20
- CUAD：20

保底：48 个 case。

- 每个 domain 12 个。

### 5.3 优先打标 hard subset

优先发给标注者：

- BGB-25
- CUAD-25
- CUAD-34
- SEC-18
- Debian-12

这些样本直接对应主图、case study、模型鲁棒性和 budget-matched baseline。

### 5.4 每个 case 的标注字段

标注者需要判断：

- `conflict_valid`：结构冲突是否成立。
- `severity`：严重程度 1-5。
- `root_valid`：root 是否是风险源。
- `witness_valid`：witness 是否参与冲突。
- `affected_valid`：affected 是否是合理风险扩散点。
- `minimal_repair_nodes`：哪些节点改掉即可修复。
- `naturalness`：注入文本是否自然。
- `distractor_noise`：原始 SCC 是否有更强原生噪声。
- `better_subgraph`：Naive / SA-MCGS / Tie，哪个风险子图更适合人工审计。

### 5.5 标注输出

最终报告：

- conflict validity rate。
- average severity。
- naturalness score。
- inter-annotator agreement。
- better_subgraph preference。
- disagreement examples。

---

## 6. 论文主指标定义

主表固定报告：

- `Root@3`：GT/root 是否进入前三。
- `Risk-any`：风险子图是否包含任意有效修复入口。
- `Risk-all`：critical 场景下是否完整保留关键风险端点，保留为重要严格指标。
- `Effective OC`：SA 的 OC 是否落在真实风险区域。
- `Compression`：风险子图相对原 SCC 的压缩率。
- `Core size`：最终风险子图节点数。
- `LLM calls`：调用次数。
- `Cost-normalized gain`：每单位 LLM call / token 的收益。

写法原则：

- `Risk-all` 在 critical 中保留为重要严格指标。
- `Risk-any` 解释为至少找到一个可修复入口。
- `Compression` 要和 `Risk-all` 一起解释，不单独追求越高越好。
- `Effective OC` 是 SA-MCGS 区别于 one-shot baseline 的关键证据指标。

---

## 7. 最终论文图表清单

### 主文图表

1. Pipeline figure：
   - MCTS structural reasoning -> SCC blockage -> SCC detection -> SA-MCGS collapse。
2. Main result table：
   - Debian / SEC / BGB / CUAD。
   - Naive vs SA。
   - GPT-4o / DeepSeek-V3。
3. Hard subset comparison：
   - BGB-25、CUAD-25/34、SEC-18、Debian-12。
4. Budget-matched baseline figure：
   - same calls / same budget 下的 Naive vs SA。
5. Convergence curves：
   - rollout vs Risk-any / Risk-all / Effective OC / Compression。
6. Case study figure：
   - 至少一个 BGB-25，一个 CUAD-34。

### Appendix 图表

1. Supplementary model robustness。
2. Ablation table。
3. Human annotation agreement。
4. Failure case audit。
5. Old diagnostic result evolution。

---

## 8. 10 天排期

### Day 1

- Probe 补充模型。
- 加入 model registry。
- 冻结指标定义。
- 启动 `critical_balanced_b60_final`。

### Day 2

- 完成 main critical run。
- 检查 API / JSON parse error。
- 补跑失败 case。

### Day 3

- 跑 `budgetmatched_naive_b60_hard`。
- 同步生成成本统计。

### Day 4

- 跑 `sa_ablation_b60_hard`。

### Day 5

- 跑 Claude / Qwen robustness。
- Gemini 2.5 Flash 只有在额度和时间宽松时跑，作为 low-cost appendix。
- Llama-3.3-70B 当前不跑，除非后续 XHub 出现标准可用 ID。

### Day 6

- 整理人工标注包。
- 发给标注者。

### Day 7

- 生成主表、消融表、模型鲁棒性表。
- 生成收敛曲线、成本收益曲线。

### Day 8

- 回收标注。
- 计算 validity 和 agreement。

### Day 9

- 写 experiment section。
- 写 appendix。

### Day 10

- 全文 polish。
- 旧 diagnostic 结果移到 appendix。
- 检查所有图表路径、表格口径、run tag。

---

## 9. Acceptance Criteria

- 主表必须来自同一 frozen setting。
- 必须有 budget-matched naive。
- 必须有 SA-MCGS ablation。
- 至少完成 Claude + 一个 70B open-weight 模型 robustness。
- 人工标注至少 48 个 case，理想 80 个。
- `Risk-all` 在 critical 中保留为重要严格指标。
- 所有主结果必须使用 real SCC。
- 旧 explicit / synthetic / Wikipedia diagnostic 不进入主结果。
- 所有图表必须在 Markdown / HTML 中正常显示。
- 每个实验结果都记录 run tag、model id、seed、budget、domain、SCC size、template、severity。

---

## 10. Open TODO

- [ ] Probe XHub 可用模型名。
- [ ] 更新 `BATTLE_MODELS` model registry。
- [ ] 确认 hard subset 的真实 SCC size，避免 fallback。
- [ ] 启动 final main run。
- [ ] 实现 / 启动 budget-matched naive。
- [ ] 启动 SA-MCGS ablation。
- [ ] 启动 supplementary model robustness。
- [ ] 生成 annotation package。
- [ ] 生成最终报告和图表。
- [ ] 清理旧 diagnostic 结果引用。

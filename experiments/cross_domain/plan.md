# ARR/EMNLP Final Experiment Plan

## 一句话判断

当前数据**已经足够支撑一个 ARR/EMNLP 级别的核心实验主张**，但前提是论文 claim 要收窄：

> SA-MCGS 不是在所有情况下都“单点识别更强”，而是在循环依赖结构中，通过 rollout 搜索把结构性风险压缩成可解释的风险子图，并在多模型、多领域、不同 SCC 长度下更稳定地保留 root/risk evidence。

不要写成 “Naive 完全不行”。Naive direct-subgraph 在 Gemini/DeepSeek 上并不弱。更稳的主张是：**SA-MCGS 的优势来自结构搜索、OC/evidence trace、风险子图保留和长环稳定性**。

## 当前主结果够不够

**基本够。**

当前 `current/default + critical` 主实验是 `4 models × 80 cases = 320 method-level pairs`，覆盖 `Debian / SEC EX-21 / BGB / CUAD`，SCC 长度从 `9` 到 `34`。

主结果很有说服力：

| Metric | Naive | SA-MCGS |
|---|---:|---:|
| Root@3 | 48% | 81% |
| Risk-any | 72% | 98% |
| Risk-all | 47% | 78% |
| Compression | 67% | 53% |
| Method errors | 59/320 | 0/320 |

按长度看也成立：

| SCC bucket | Root@3 | Risk-any | Risk-all |
|---|---:|---:|---:|
| short <=12 | 54% → 89% | 88% → 99% | 55% → 83% |
| mid 14-20 | 43% → 77% | 59% → 99% | 40% → 80% |
| long >=24 | 45% → 71% | 56% → 92% | 41% → 65% |

这说明结果不是只靠短环 sanity 得来的。长环上 SA 仍然明显更稳，只是 `Risk-all` 会下降，这是合理 limitation。

## Reviewer 最可能质疑什么

1. **Baseline 公平性**
   - Naive full-SCC prompt 更长，报错更多，strict rate 会放大 SA 优势。
   - 必须同时报告 strict rate 和 valid-only / no-error subset。
   - 需要明确：Naive direct-subgraph 已经是强 baseline，不是弱 baseline。

2. **指标定义**
   - `Risk-any` 和 `Risk-all` 要解释清楚。
   - `Risk-all` 在 critical 下很重要，不能淡化；但也要说明结构风险可能有 root/witness/affected 多个修复入口。
   - `Effective OC` 不应作为单调累计主指标。更适合用：
     - First Effective OC
     - Final OC retention
     - OC persistence / AUC

3. **压缩率 tradeoff**
   - SA 的覆盖率提升是以更大子图为代价。
   - 当前 compression 从 Naive 67% 降到 SA 53%，代价存在但不夸张。
   - 论文里要直接写：这是 evidence retention vs compactness 的 tradeoff，不要回避。

4. **数据集可信度**
   - BGB 是最干净的法律文本补充，CUAD 噪声更大但真实合同更贴近实际。
   - Wikipedia 参考价值弱，不要作为主结论。
   - Debian/SEC 可以作为跨域泛化补充，不要过度承载主 claim。

5. **注入有效性**
   - critical 注入必须有 case audit。
   - 最少要人工检查一小批 root/witness/affected 是否真的构成结构性风险。

## 必补实验：针对 Reviewer 硬伤

下面这些不是为了“继续刷分”，而是为了堵住顶会 reviewer 几个不可避免的问题。优先级高于继续扩模型或继续调参。

### E0: Matched / Valid-only 重算表

**要解决的问题：** Naive 报错多，strict rate 是否人为放大了 SA-MCGS 优势？

**做法：**

- 不重新调用 LLM。
- 在同一批 `80 cases × 4 models` 上重算三套表：
  - `strict`: 报错计失败，作为主表。
  - `valid-only`: 只统计成功返回的 Naive/SA。
  - `matched-no-error`: 只统计 Naive 和 SA 都成功的配对 case。

**论文用途：**

- 主文用 strict。
- appendix 放 valid-only / matched-no-error。
- 如果 SA 在 matched-no-error 里仍有优势，baseline 公平性质疑会弱很多。

**优先级：P0。**

### E1: Naive 输出负担控制实验

**要解决的问题：** Naive 失败到底是因为 one-shot full-SCC 方法不行，还是因为我们要求它输出太复杂的 JSON？

**做法：**

- 只补 Naive，不重跑 SA。
- 选择 Naive 报错最集中的部分：`CUAD long SCC`，优先 `qwen2.5-72b` 和 `gpt-4o`。
- 新增一个 `naive-lite` / `naive-minimal-json` 口径：
  - 仍然一次性看完整 SCC。
  - 仍然输出 `risk_subgraph_nodes`。
  - 减少或取消逐节点 `clause_evaluations`、长解释、完整 ranking 细节。
- 规模建议：
  - 最小：CUAD 长环 20 到 40 calls。
  - 理想：CUAD 全 40 cases × 2 models = 80 calls。

**论文用途：**

- 如果 naive-lite 仍然差：说明问题确实来自 full-SCC one-shot 的长上下文结构压力。
- 如果 naive-lite 明显变好：主文仍可保留 strict 主表，但必须承认输出 schema 对 Naive 有影响，并把 naive-lite 作为强 baseline appendix。

**优先级：P0。** 这是 reviewer 最可能抓的硬伤之一。

### E2: Budget / Rollout 收敛实验

**要解决的问题：** SA-MCGS 调用更多 LLM，优势是不是只是“花更多钱硬搜”？

**做法：**

- 优先不重新跑，用现有 `convergence_trace` 做 prefix analysis。
- 汇报 budget = `5 / 10 / 20 / 30 / 60` 时的：
  - Root@3
  - Risk-any
  - Risk-all
  - Compression
  - First Effective OC / Final OC Retention / OC Persistence
- 按 SCC 长度段拆分：`<=12`, `14-20`, `>=24`。

**论文用途：**

- 证明 rollout 增加带来逐步收敛，而不是只看最终 60。
- 如果 30 已接近 60，可以说明成本可控。
- 如果长环 60 仍在增长，可以说明结构搜索在长环上确实有继续探索价值。

**优先级：P0。**

### E3: Compression Profile Ablation

**要解决的问题：** SA-MCGS 覆盖率提升是不是靠牺牲压缩率换来的？压缩率参数是不是 cherry-pick？

**做法：**

- 使用已有 `current/default` 和 `balanced` 结果。
- 不把 balanced 放进主结果，只做 ablation。
- 表格只看：
  - Risk-any
  - Risk-all
  - Compression
  - Avg subgraph size
- 如果某些 balanced row 缺失，只补最小缺口，不扩大规模。

**论文用途：**

- 解释 `current/default` 是 evidence-retention 优先。
- `balanced` 是更强压缩设置，展示 tradeoff。
- 主文一句话 + appendix 详细表即可。

**优先级：P1。**

### E4: 人工 Case Audit

**要解决的问题：** 注入是不是自嗨？root/witness/affected 是否真的构成结构性风险？

**做法：**

- 不做大规模人工评测。
- 做 20 到 30 个小样本审计：
  - BGB-25：8 到 12 个。
  - CUAD-25/34：8 到 12 个。
  - Debian/SEC：各 2 到 4 个。
- 标注字段：
  - root/witness 是否构成冲突。
  - affected 是否合理。
  - SA 子图是否包含可修复入口。
  - Naive 子图是否可操作。

**论文用途：**

- 主文放 1 到 2 个 case study。
- appendix 放 audit summary。

**优先级：P1。**

### E5: Prompt/Rubric Parity Check

**要解决的问题：** Naive 和 SA-MCGS 是否因为 prompt 不一致导致不公平？

**做法：**

- 不重新跑大实验。
- 抽取最终使用的 Naive prompt 和 SA window prompt。
- 写出 shared risk rubric：
  - structural inconsistency
  - mutually incompatible records
  - high-risk propagation
  - repairable risk subgraph
- 明确差异只在输入粒度：
  - Naive: full SCC one-shot。
  - SA: local window rollout + evidence aggregation。

**论文用途：**

- 放 method 或 appendix。
- 这是 fairness 文字说明，但必须有真实 prompt 截图/片段支撑。

**优先级：P1。**

## 最后 6 天优先级

### P0 / Day 1: 文件层级锁定主实验口径

- 主表只用 `current/default + critical + 80 cases × 4 models`。
- 文件入口统一到 `experiments/main_experiment/`：
  - `README.md`：主实验口径说明。
  - `MANIFEST.json`：唯一 canonical status files。
  - `STATUS.md`：剩余写作任务。
- 每个结果表同时给：
  - strict rate
  - valid-only rate
  - error count
  - compression
- Gemini 2.5 Flash 不进入主实验；Gemini 2.5 Pro 可以进入。
- 结果文件、dashboard、论文表格必须使用同一批 run，不再临时换 profile。

**重要性：最高。** 这是防止实验口径混乱的第一道防线。没有这个，后面所有分析都会被 reviewer 质疑 cherry-picking。

### P0 / Day 1-2: 跑/生成必补公平性实验

- 先做 `E0 matched / valid-only`，不需要 LLM 调用。
- 再做 `E1 Naive 输出负担控制实验`，只补 Naive，优先 CUAD long + qwen/gpt。
- 同步整理 `E5 Prompt/Rubric parity`。

**重要性：最高。** EMNLP reviewer 很容易攻击 baseline 不公平；这部分不能只靠文字，需要有对应补充实验或配对分析。

### P0 / Day 2: Budget / Rollout 收敛分析

- 做 `E2 Budget / Rollout` prefix analysis。
- 不把累计 `Effective OC` 当主指标。
- 收敛图改成支持：
  - First Effective OC。
  - Final OC Retention。
  - OC Persistence/AUC。
  - Risk-any/Risk-all 随 rollout 的变化。

**重要性：很高。** 这是解释 SA-MCGS 多轮 rollout 价值的核心补充实验。

### P0 / Day 2-3: 固化最终图表和主表

论文主图建议只保留最有杀伤力的 5 张：

1. Overall current/default bar chart。
2. By model bar chart。
3. By SCC length bucket chart。
4. Compression vs Risk-all tradeoff scatter。
5. SA convergence curve：First Effective OC / Risk-any / Risk-all / Compression。

主表必须包括：

- `N`
- `Errors`
- `Root@3`
- `Risk-any`
- `Risk-all`
- `Compression`
- `Valid-only` 或 appendix 指针

**重要性：很高。** 图表要服务 claim，不要展示所有探索历史。现在最怕图太多、口径太乱。

### P1 / Day 3: Compression ablation + 人工审计小样本

先做 `E3 Compression Profile Ablation`，再做人工 audit。

建议打标/人工检查，不要扩大：

- BGB-25：8 到 12 个 case。
- CUAD-25/34：8 到 12 个 case。
- Debian/SEC：各 2 到 4 个 case 即可。

标注内容只需要判断：

- root/witness 是否真的构成 structural conflict。
- affected 是否是合理风险扩散点。
- SA 子图是否包含可修复入口。
- Naive 子图是否给出可操作解释。

**重要性：高。** 这是防止“synthetic injection 自嗨”的关键证据。但不要做成大规模人工评测，时间不够。

### P1 / Day 3-4: 写两个 case study

- 一个 BGB 长环 case：强调干净法律文本、结构冲突、SA 子图解释性。
- 一个 CUAD 长环 case：强调真实合同噪声下仍能抓到可修复风险入口。
- 每个 case study 控制在半页以内：
  - graph/context 简述
  - root/witness/affected
  - Naive 输出
  - SA rollout evidence + final subgraph
  - 为什么这个子图可解释

**重要性：高。** Case study 是把“数字优势”转成“方法可信”的地方，尤其适合 rebut reviewer 对指标的怀疑。

### P2 / Day 4: 写 limitation

- Gemini Pro 的 Naive 很强，SA 不是所有模型上都大幅赢。
- CUAD 有原生噪声，Risk-all 更难。
- SA 调用更多 LLM，优势不是成本更低，而是结构搜索更稳。
- Compression 有代价，不是免费提升。

**重要性：中高。** 主动承认 limitation 会让论文更可信，尤其是 ARR 场景。

### P2 / Day 5: Appendix 和复现材料

- 放 valid-only 表。
- 放 per-domain / per-model 详细表。
- 放 prompt/rubric。
- 放注入模板说明。
- 放 error breakdown。

**重要性：中。** 主文放不下，但 appendix 能挡很多 reviewer 的细节追问。

### P3 / Day 6: 最终收口

- 不再新增模型。
- 不再改 SA-MCGS 算法。
- 不再改 injection profile。
- 只做：
  - 表格编号统一。
  - 数字核对。
  - claim 和图表一致性检查。
  - abstract/introduction/conclusion 的说法对齐。

**重要性：中，但必须留时间。** 最后一天不应该再跑实验，应该专门防止论文内部自相矛盾。

## 现在不要做

- 不要无目的扩 100+ case；只做上面 E0-E5 的 targeted supplement。
- 不要再加新模型。
- 不要再调 compression profile 当主结果。
- 不要再把 Wikipedia 写进主结论。
- 不要把累计 `Effective OC` 写成主指标。
- 不要试图证明 Naive 完全失败。

## 最终建议

**可以进入论文主体写作。**

现在不建议继续大规模扩实验。剩余时间更应该花在：

1. 固定主口径。
2. 完成 targeted supplement：E0/E1/E2。
3. 把 baseline 公平性和 error handling 写扎实。
4. 把指标定义写清楚。
5. 做少量人工 audit。
6. 用 case study 证明 SA-MCGS 的子图不是“多吐几个节点”，而是真的形成了结构证据。

如果以上 P0/P1 做完，当前实验强度对 ARR/EMNLP 是够用的；如果不做这些解释，reviewer 很可能会抓住 baseline error、OC 指标、compression tradeoff 和注入有效性来打分。

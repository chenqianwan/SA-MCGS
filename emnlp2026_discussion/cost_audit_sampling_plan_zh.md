# 成本统计复做小实验：case 组成与抽样建议

## 推理成本表实验设计（执行版）

目标是给 reviewer 一个最直观的 cost-performance 表：同一张表里同时看到 **tokens / calls / runtime** 和 **Root@3 / Risk-any / Risk-all / Compression**。口径上不把 cost 和 accuracy 拆成两段讨论，而是明确展示：SA-MCGS 增加了 LLM calls 和 wall-clock runtime，但每次调用是 local-window prompt；full-SCC Naive 调用次数少，但单次 prompt 更长且承担更重的 output schema；新增 LEA baseline 用来隔离 local decomposition / schema simplification 的收益。

### 最终给 reviewer 的主表模板

建议最终 follow-up comment 只放这一张主表。`Scale` 可以包含 `Overall`、`small`、`medium`、`large`；如果 OpenReview 空间紧张，保留 `Overall` 三到四行，把 scale-stratified 版本作为附表/后续补充。

| Method | Scale | Cases | Case conc. | Internal conc. | Calls / case | Input tok. / case | Output tok. / case | Total tok. / case | Runtime / case | Invalid output | Root@3 | Risk-any | Risk-all | Compression |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full-SCC Naive, single attempt | Overall | TBD | 1 | 1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Oracle-risk/full-SCC Naive, reported selector | Overall | TBD | 1 | 1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| GraphRAG-style LEA | Overall | TBD | 1 | 1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| SA-MCGS | Overall | TBD | 1 | 1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

表格脚注建议：

- `Input/output tokens` are provider-observed usage, summed over all LLM calls in a case.
- `Case conc.` is the number of cases run simultaneously; `Internal conc.` is the number of simultaneous LLM calls allowed inside one method/case. For the audit table, both are set to 1 unless explicitly noted.
- `Runtime` is measured wall-clock time under the recorded low-concurrency setting; token cost and queue/wall-clock cost are interpreted separately.
- `Oracle-risk/full-SCC Naive` uses the same boosted full-SCC selector setting as the reported baseline; the single-attempt row is included to make per-generation full-SCC cost transparent.
- LEA uses deterministic graph-window retrieval and the same local evidence schema as SA-MCGS, but without relation-first memory, critical-pair revisiting, OC/core signals, or dynamic-core replacement.

### 并发控制口径

这次 20-case cost audit 不沿用旧实验的大并发设置。所有方法默认按 `case_concurrency=1` 串行执行；SA-MCGS 和 LEA 的单 case 内部 LLM 并发也默认设为 `internal_concurrency=1`。如果为了节省时间临时使用 `internal_concurrency=2`，必须在表中显式标注，并且不与 `internal_concurrency=1` 的 runtime 混合平均。

旧实验的并发只作为背景，不作为本次 cost table 的 runtime 口径：

| Experiment script | Case/task-level concurrency | Internal LLM concurrency | 说明 |
|---|---:|---:|---|
| `run_cross_domain_battle.py` single process | 1 | SA-MCGS default 4, or `--mcgs-concurrency` override | 单个进程内按 model/method 顺序跑；SA-MCGS rollout 内部并发。 |
| `run_severity_grid.py` wrapper | default 6 | default 8 passed as `--mcgs-concurrency` | 多个 case/task 同时启动，理论峰值约为 `6 x 8 = 48` 个 SA-MCGS local-window LLM calls。 |
| `run_budget60_rerun.py` | 1 | 4 | targeted rerun 是 case 层级串行，但 SA-MCGS 单 case 内部仍并发 4。 |
| boosted Naive round-robin | default 16 attempts | 1 per attempt | 每轮最多 16 个 full-SCC attempts 并发；canonical run 是 80 blocks x 4 models x 10 attempts。 |

### 方法口径

| Method row | 成本计入口径 | 需要补什么 | 性能指标来源 | 备注 |
|---|---|---|---|---|
| Full-SCC Naive, single attempt | 1 次 full-SCC prompt 的 tokens/calls/runtime | 如果旧日志缺 runtime，则在选中 case 上低并发复跑计时 | selected cases 上对应 single attempt 输出，或从 raw attempts 抽取 | 用来说明 full-SCC prompt 的单次成本 |
| Oracle-risk/full-SCC Naive, reported selector | reported boosted selector 的全部 attempts 成本，calls/case 约等于 attempts 数 | runtime 若旧日志缺失，用 single-attempt runtime 乘 attempts 或复跑 selected cases | locked main result 过滤到 selected cases | 用来和论文主表 baseline 对齐 |
| GraphRAG-style LEA | 固定图窗口检索 + local evidence extraction + 透明聚合的全部 calls | 新跑，记录 tokens/calls/runtime/invalid output | 新跑 selected cases | 与 SA-MCGS 使用同一 local evidence schema，但无 search/memory/core 模块 |
| SA-MCGS | local-window rollout calls 的 provider-observed tokens/calls/runtime | 复做 selected cases 的 token audit；旧 trace 可补 calls/runtime | locked main result 过滤到 selected cases；token audit 只用于成本 | 低并发复跑，避免把 provider queueing 误读为算法成本 |

### 分层采样口径

内部执行采用 20 个代表性 case，覆盖全部 `domain x SCC-size` bucket；对外只说 stratified by case scale / SCC size，不强调 small sample。推荐先用一个主模型完成全 size 覆盖，必要时再补少量 cross-model hard cases。

| Domain | SCC sizes covered | Audit cases | Scale bins touched |
|---|---|---:|---|
| debian | 11, 12 | 2 | small |
| sec_ex21 | 9, 10, 11, 12, 18 | 5 | small, medium |
| bgb | 9, 11, 25 | 3 | small, large |
| cuad | 12, 14, 16, 17, 18, 20, 24, 25, 28, 34 | 10 | small, medium, large |
| **Total** | **20 domain-size buckets** | **20** | **all bins** |

建议 scale bin：

| Scale | SCC size range | 用途 |
|---|---|---|
| small | `n <= 12` | full-SCC prompt 尚可承受，观察 LEA/SA-MCGS 是否有额外调用成本 |
| medium | `13 <= n <= 20` | 观察 local-window 方法的 token 增长是否慢于 full-SCC prompt |
| large | `n >= 24` | 重点展示 full-SCC long-context / output schema pressure 与 local-window rollout 的 tradeoff |

### 记录字段

原始 call-level 日志至少保留：

| Field | 含义 |
|---|---|
| `case_id`, `domain`, `scc_size`, `template`, `model` | 对齐主实验 case 和分层统计 |
| `method`, `attempt_id`, `call_id` | 区分 Naive attempts、LEA windows、SA-MCGS rollouts |
| `window_nodes`, `window_edges`, `window_token_estimate` | 解释 local-window prompt 的真实规模 |
| `provider_prompt_tokens`, `provider_completion_tokens`, `provider_total_tokens` | 最关键的 provider-observed usage |
| `call_runtime_sec`, `case_runtime_sec`, `concurrency` | 区分 token 成本和 wall-clock 成本 |
| `parse_ok`, `schema_valid`, `invalid_reason` | 对齐 output reliability / invalid output rate |
| `root_at_3`, `risk_any`, `risk_all`, `compression` | 生成最终 cost-performance 表 |

### 理论复杂度说明

最终表格旁边配一段简短公式，不需要展开成新实验：

| Method | Cost expression | 解释 |
|---|---|---|
| Full-SCC Naive | `O(A * T_SCC)` | `A` 是 attempts 数；`T_SCC` 包含整个 SCC 文本、边、rubric 和输出 schema。single-attempt 时 `A=1`，reported oracle-risk selector 时 `A` 为 boosted attempts。 |
| GraphRAG-style LEA | `O(K * T_w)` | `K` 是 deterministic graph windows 数；`T_w` 是固定 local window 的文本、局部边和 local evidence schema。 |
| SA-MCGS | `O(U * T_w)` with `U <= B` | `B` 是 rollout budget，`U` 是实际触发 LLM 的 unique local-window calls；cache / repeated states 会让实际 calls 小于 naive rollout count。 |

推荐 discussion 表述：

> The resulting table reports provider-observed tokens, calls, and wall-clock runtime under a recorded low-concurrency setting, stratified by SCC/case scale. It also reports Root@3, Risk-any, Risk-all, and Compression in the same view, so that the tradeoff between cost and endpoint retention is visible rather than described only qualitatively.

## 当前 locked main experiment 组成

主实验是 `current/default + critical + structural_simple_v2 + budget=60`。

按方法看：

- 主表 method-level records：`640 = 320 Naive + 320 SA-MCGS`
- 每个方法的 model-case pairs：`320`
- boosted/oracle-risk Naive 的原始尝试：`3200 = 320 cases x 10 attempts`

按模型看，每个模型 `80` 个 case：

| Model | Cases |
|---|---:|
| gpt-4o | 80 |
| deepseek-v3 | 80 |
| qwen2.5-72b | 80 |
| gemini-2.5-pro | 80 |

按 domain 看，全体 `320` 个 SA-MCGS model-case pairs：

| Domain | Total cases | Per model |
|---|---:|---:|
| debian | 32 | 8 |
| sec_ex21 | 80 | 20 |
| bgb | 48 | 12 |
| cuad | 160 | 40 |

每个模型内部的 domain 组成一致：

| Model | Debian | SEC EX-21 | BGB | CUAD | Total |
|---|---:|---:|---:|---:|---:|
| each model | 8 | 20 | 12 | 40 | 80 |

按风险模板看，四类模板完全均衡：

| Template | Total cases |
|---|---:|
| direct_mutex | 80 |
| handoff_invariant | 80 |
| temporal_gate | 80 |
| condition_trigger | 80 |

每个 domain 内模板也均衡：

| Domain | direct_mutex | handoff_invariant | temporal_gate | condition_trigger |
|---|---:|---:|---:|---:|
| debian | 8 | 8 | 8 | 8 |
| sec_ex21 | 20 | 20 | 20 | 20 |
| bgb | 12 | 12 | 12 | 12 |
| cuad | 40 | 40 | 40 | 40 |

## SCC size 组成

每个 `domain x SCC-size` bucket 在全体 320 model-case pairs 中出现 `16` 次：`4 models x 4 templates`。

| Domain | SCC sizes | Count per size |
|---|---|---:|
| debian | 11, 12 | 16 each |
| sec_ex21 | 9, 10, 11, 12, 18 | 16 each |
| bgb | 9, 11, 25 | 16 each |
| cuad | 12, 14, 16, 17, 18, 20, 24, 25, 28, 34 | 16 each |

更完整的逐 case 列表已保存到：

- `case_composition.csv`

## 各方法还缺什么

Naive / boosted Naive 已经有 provider-observed token usage：

- raw attempts: `3200`
- total tokens: `51,632,033`
- prompt tokens: `39,972,656`
- completion tokens: `11,659,377`

Naive / boosted Naive 可能还缺：

- selected-case runtime；
- single-attempt full-SCC runtime；
- 与最终表格完全对齐的 selected-case aggregation。

SA-MCGS 当前已有：

- exact LLM calls
- exact runtime
- exact trace windows

但缺：

- provider-observed prompt tokens
- provider-observed completion tokens

GraphRAG-style LEA 是新增 baseline，需要完整记录：

- provider-observed prompt/completion/total tokens；
- LLM calls；
- runtime；
- invalid / unparsable output；
- Root@3、Risk-any、Risk-all、Compression。

因此成本复做由三部分组成：

1. Naive：优先从旧 raw attempts 汇总 token；若 runtime 缺失，在 selected cases 上低并发复跑或用 selected single-attempt timing 补齐。
2. SA-MCGS：复做 selected cases 的 token audit，在每次 local-window call 后记录 provider usage；性能指标仍优先引用 locked main result 的 selected-case 子集。
3. LEA：在同一批 selected cases 上新跑，并把性能和 tokens/calls/runtime 同步写入同一张 cost-performance 表。

## 关于 `max_tokens`

`max_tokens=2048` 只是每次 local-window completion 的上限，不等于实际消耗。

SA-MCGS 每次调用只看：

- 当前 window 的 4 个节点文本；
- 这 4 个节点之间的边；
- 固定 JSON schema。

所以不能按 `60 rollouts x 2048 max_tokens` 估算 completion 成本，也不能按 full-context 上限估算 input 成本。精确复做应该记录 provider 返回的真实 usage。

## 推荐复做方案

### 方案 A：当前采用的 stratified cost audit，20 cases

目的：覆盖所有 domain-size bucket，得到 SA-MCGS local-window token 的真实量级，同时给 LEA 和 Naive runtime 对齐同一批 selected cases。

组成：

- 选 1 个模型，建议先用 `gpt-4o` 或实际论文中最稳定的一个模型；
- 每个 `domain x SCC-size` bucket 选 1 个 case；
- 一共 `2 + 5 + 3 + 10 = 20` cases；
- 每个 case 跑 SA-MCGS token audit 和 LEA；Naive 只在旧日志缺 runtime 或需要 single-attempt timing 时复跑。
- 使用低并发设置：`case_concurrency=1`，并将 SA-MCGS 的 `alphago_mcgs.concurrency` 显式设为 `1`。如果为了节省时间使用 `2`，必须在表中标注，且不与 `1` 的 runtime 混算。
- 成本表必须同时记录 `case_concurrency` 和 `internal_concurrency`，并把 token cost 与 wall-clock time 分开解释。

优点：

- 覆盖所有 SCC size；
- 能证明 SA-MCGS 不是按满上下文消耗 token；
- 成本明显小于重跑主实验；
- 三个方法可以进入同一张 selected-case cost-performance 表。

缺点：

- completion token 只代表一个模型；
- 不能直接报告四个模型的 provider-observed average。

### 方案 B：模型敏感 token audit，32 cases

目的：看不同模型的 completion token 和 runtime 差异。

组成：

- 每个模型选 8 个 case；
- 每个模型覆盖：Debian small/medium、SEC short/long、BGB short/long、CUAD medium/long；
- 一共 `4 models x 8 = 32` cases；
- 优先用于 SA-MCGS token sensitivity；如果时间允许，LEA 同步跑同一批 case。

优点：

- 能得到四个模型的真实 provider-observed SA-MCGS token；
- 规模仍然远小于 320 cases。

缺点：

- 不能覆盖全部 20 个 domain-size bucket；
- 对 CUAD size 分布的覆盖弱于方案 A。

### 方案 C：推荐折中，40 cases

目的：既覆盖 size，又有一定模型差异。

组成：

- `20` 个 domain-size bucket 全部用一个主模型跑；
- 额外选 `5` 个代表性 hard/long cases，在另外 3 个模型上各跑一次；
- 总计 `20 + 5 x 3 = 35`，可补到 `40`。

推荐的 5 个 cross-model hard cases：

1. Debian size 12
2. SEC EX-21 size 18
3. BGB size 25
4. CUAD size 28
5. CUAD size 34

优点：

- 覆盖所有 size；
- 又能看到模型差异；
- 适合 discussion 期间报告为 stratified exact cost audit。

## 推荐回复口径

如果采用小型复做，可以在 discussion 中写：

> We thank the reviewers for asking for practical cost characterization. We re-ran a stratified cost audit on representative SCC/case scales, logging provider-observed prompt and completion tokens, LLM calls, runtime, and invalid-output behavior. For SA-MCGS, this audit records provider-side usage for every local-window rollout; for the new GraphRAG-style LEA baseline, it records the same fields under the same local evidence schema. This table makes clear that SA-MCGS does not consume the full context per rollout: each call uses a small local window plus local edges and a fixed JSON schema.

第一轮回复中更稳的预告口径：

> We agree that practical inference cost should be characterized more explicitly. We are adding a cost analysis stratified by SCC/case scale, reporting provider-observed input/output tokens, LLM calls, and runtime for oracle-risk/full-SCC Naive, SA-MCGS, and the GraphRAG-style LEA baseline, together with theoretical cost expressions for full-SCC prompting, deterministic local-window aggregation, and local-window rollout search. We will include the detailed table in a follow-up response and revise the paper accordingly.

中文理解：

- 不承认之前成本不可用；
- 只说原始 SA-MCGS 主实验没有保存每次 local rollout 的 provider token usage；
- 小实验是为 reviewer 补“工程成本可见性”；
- 强调 `max_tokens` 是上限，实际 token 是 provider-observed。
- 对外不说“只做 20 个 case”，只说按 SCC/case scale 分层；内部执行采用 20 个覆盖全部 domain-size bucket 的代表性 case，并让 LEA 与 SA-MCGS 使用同一批 selected cases。

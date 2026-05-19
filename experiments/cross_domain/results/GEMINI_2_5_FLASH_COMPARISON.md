# Gemini 2.5 Flash 对比分析

更新时间：2026-05-17  
对应结果文件：

- `critical_balanced_b60_supp_qwen_gemini_severity_grid_status.json`
- `critical_paper_v3_b60_severity_grid_status.json`

## 一句话结论

Gemini 2.5 Flash **不是一个整体很弱的模型**：官方定位是低成本、低延迟、可调 thinking budget 的 hybrid reasoning model。但在我们当前 SA-MCGS 实验里，它明显弱在两点：**复杂 JSON/结构化证据协议不稳定**，以及 **局部窗口内没有把风险对转化成高风险 conflict evidence**。因此它在 Naive whole-SCC 判断里还能命中一部分风险，但在 SA-MCGS 的 local evidence pipeline 里几乎完全失效。

## 1. 我们任务上的定量结果

### 1.1 Critical paper 主模型结果

| Model | Method | N | Root@3 | Risk-any | Risk-all | Avg compression |
|---|---:|---:|---:|---:|---:|---:|
| gpt-4o | Naive | 80 | 21/80 (26%) | 44/80 (55%) | 12/80 (15%) | 67.9% |
| gpt-4o | SA-MCGS | 80 | 69/80 (86%) | 80/80 (100%) | 60/80 (75%) | 51.3% |
| deepseek-v3 | Naive | 80 | 60/80 (75%) | 70/80 (88%) | 59/80 (74%) | 70.1% |
| deepseek-v3 | SA-MCGS | 80 | 64/80 (80%) | 76/80 (95%) | 61/80 (76%) | 51.3% |

### 1.2 Supplement 模型结果

| Model | Method | N | Root@3 | Risk-any | Risk-all | Avg compression |
|---|---:|---:|---:|---:|---:|---:|
| qwen2.5-72b | Naive | 80 | 6/80 (8%) | 38/80 (48%) | 15/80 (19%) | 43.6% |
| qwen2.5-72b | SA-MCGS | 80 | 53/80 (66%) | 75/80 (94%) | 48/80 (60%) | 63.6% |
| gemini-2.5-flash | Naive | 80 | 20/80 (25%) | 20/80 (25%) | 16/80 (20%) | 55.1% |
| gemini-2.5-flash | SA-MCGS | 80 | 0/80 (0%) | 0/80 (0%) | 0/80 (0%) | 93.1% |

### 1.3 Gemini SA-MCGS 为什么是 0

Gemini 的 SA-MCGS 不是 API 顶层失败；80 个 SA-MCGS 记录都有结果。但内部证据几乎全空：

| Evidence signal | gemini-2.5-flash SA | qwen2.5-72b SA |
|---|---:|---:|
| `oc_count > 0` | 0/80 | 62/80 |
| `local_conflict_edges` non-empty | 0/80 | 79/80 |
| `critical_pair_locked_edges` non-empty | 0/80 | 75/80 |
| `dynamic_core_priority_rows` non-empty | 0/80 | 79/80 |
| Average `score_spread` | 0.004 | 0.445 |
| Final core size distribution | 80/80 are size 1 | mostly 4--9 nodes |

解释：Gemini 在局部窗口里通常给出近乎均匀的风险分数，且不稳定地产生 `local_conflict_edges` / `critical_pairs`。于是 SA-MCGS 没有可累计的结构证据，最终 core selection 只能退化成 1 个 fallback node。这和 Naive 不矛盾：Naive 看到完整 SCC 后仍有一定语义识别能力，但 SA-MCGS 需要模型把局部风险转成可聚合的结构化证据。

## 2. 错误来源

在 supplement 模型的 Naive 侧，Gemini 的主要失败是 JSON 解析：

| Model | Method | Error type | Count |
|---|---|---:|---:|
| gemini-2.5-flash | Naive | no parseable JSON | 50 |
| gemini-2.5-flash | Naive | quota exhausted | 9 |
| gemini-2.5-flash | Naive | invalid/incomplete ranking | 1 |
| qwen2.5-72b | Naive | connection error | 27 |
| qwen2.5-72b | Naive | 502 gateway | 13 |
| qwen2.5-72b | Naive | quota exhausted | 1 |

所以 Gemini 的 Naive 结果被 JSON 失败强烈污染；Qwen 的 Naive 结果更多是服务/API 稳定性污染。SA-MCGS 顶层没有报错，但 Gemini 的局部证据字段为空，这是模型行为问题，不是请求失败。

## 3. 外部资料中的模型定位

### Gemini 2.5 Flash

Google 的 model card 把 Gemini 2.5 Flash 定位为 **hybrid reasoning + cost/latency tradeoff** 模型：它支持打开/关闭 thinking，并可以设置 thinking budget，在质量、成本和延迟之间取舍；支持 1M context 和 64K text output；架构是 sparse MoE。官方也明确列出一般 foundation model 限制，包括 hallucination、causal understanding、complex logical deduction、counterfactual reasoning 等。  
来源：[Google DeepMind Gemini 2.5 Flash Model Card](https://storage.googleapis.com/deepmind-media/Model-Cards/Gemini-2-5-Flash-Model-Card.pdf)

官方 benchmark 显示它并不差：例如 model card 中 Gemini 2.5 Flash GA thinking 在 GPQA Diamond 上为 82.8%，AIME 2025 为 72.0%，LiveCodeBench v5 为 63.9%，Global MMLU Lite 为 88.4%。但是这些指标不等价于我们这里的 **局部结构化证据抽取 + 多轮聚合**。

### Gemini JSON / structured output

Google 官方文档说明，如需稳定生成 JSON object，应在 generation config 中设置 structured output / JSON schema；structured output 会生成符合 schema 的 JSON 字符串，但只支持 JSON Schema 的一个子集。  
来源：[Gemini API Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output)

我们的 XHub/OpenAI-compatible 调用当前主要是 prompt-level JSON instruction，而不是 Gemini native `response_format` schema。因此 Gemini 的 `no parseable JSON` 不能简单解释成模型智力差，更像是 **provider 路由 + prompt JSON + 长输出 schema** 的组合问题。

### Qwen2.5-72B-Instruct

Qwen2.5 技术报告称，Qwen2.5-72B-Instruct 是 open-weight flagship，并且相对 5 倍大小的 Llama-3-405B-Instruct 仍有竞争力。它在我们实验里也表现为：Naive 不强，但 SA-MCGS 能把局部结构证据稳定产出并聚合起来。  
来源：[Qwen2.5 Technical Report](https://arxiv.org/abs/2412.15115)

### Claude 3.5 Sonnet

Anthropic 将 Claude 3.5 Sonnet 定位为 frontier intelligence，强调复杂指令、nuance、coding 和 multi-step workflow；2024-10-22 版本在 SWE-bench Verified 从 33.4% 提升到 49.0%。这类模型更适合作为后续补充模型，而不是低成本 Flash 对照。  
来源：[Claude 3.5 Sonnet](https://www.anthropic.com/news/claude-3-5-sonnet), [Claude 3.5 Sonnet 2024-10-22](https://www.anthropic.com/news/3-5-models-and-computer-use)

### DeepSeek-V3 / GPT-4o

DeepSeek-V3 技术报告定位为大规模 MoE 通用模型；GPT-4o system card 则覆盖文本、视觉和语音能力与安全评估。我们当前主结果里，DeepSeek-V3 和 GPT-4o 都比 Gemini Flash 更适合作为论文主模型。  
来源：[DeepSeek-V3 Technical Report](https://arxiv.org/abs/2412.19437), [GPT-4o System Card](https://openai.com/index/gpt-4o-system-card/)

## 4. 定性判断

Gemini 2.5 Flash 在我们的设置里不是“语义完全看不懂”，而是 **不适合当前 SA-MCGS local evidence 协议**：

1. 它在 whole-SCC Naive 中仍有 25% Root@3 / 25% Risk-any / 20% Risk-all，说明它有一定识别能力。
2. 它在 SA-MCGS 中 `score_spread` 接近 0，说明局部窗口打分几乎不区分风险和背景节点。
3. 它没有产生 conflict edge / critical pair，导致 MCGS 无法强化、无法 OC、无法动态 core 收敛。
4. 它的 Naive JSON parse failure 很高，说明 prompt-only strict JSON 对 Gemini Flash 不稳。

## 5. 论文写法建议

不要把 Gemini 2.5 Flash 写成主模型。建议写成 appendix / sensitivity analysis：

> Gemini 2.5 Flash is a cost- and latency-oriented hybrid reasoning model. In our critical SCC setting, it showed non-trivial one-shot semantic recognition but failed to reliably emit the structured local evidence required by SA-MCGS under prompt-only JSON constraints. We therefore treat Gemini Flash as a model-sensitivity case rather than a main result model.

主文建议保留：

- GPT-4o
- DeepSeek-V3
- Qwen2.5-72B-Instruct

Claude 3.5 Sonnet 可以作为更强但更贵的补充模型，优先跑小规模 hard subset。

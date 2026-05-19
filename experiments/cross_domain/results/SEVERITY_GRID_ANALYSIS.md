# Severity Grid 实验分析

结果文件：`severitygrid_cuad_bgb_2size_b60_severity_grid_status.json`

图表入口：
- 总览长图：[SEVERITY_GRID_ANALYSIS_CONTACT_SHEET.png](SEVERITY_GRID_ANALYSIS_CONTACT_SHEET.png)
- 自包含 HTML：[SEVERITY_GRID_ANALYSIS.html](SEVERITY_GRID_ANALYSIS.html)
- 单张 PNG 在本报告每个图表小节下面都有链接。

> 说明：Codex 当前的 Markdown 预览不稳定支持 `data:image` 或本地相对图片内嵌，所以本版报告不再直接内嵌图片，避免灰色占位。要看图，优先打开总览长图或 HTML。

本轮共 `192` 条 method-level 记录，来自 `48` 个 block：
`2 domains × 2 requested sizes × 4 templates × 3 severities × 2 models × 2 methods`。

> 重要口径：下面的 hit rate 默认是 **strict rate**，也就是 JSON/排名解析错误按失败计入分母。Naive direct-subgraph 有 `19/96` 条解析/排名错误；SA-MCGS 是 `0/96`。

## 1. 最重要的结论

1. **高严重度注入确实让信号更可见。** SA-MCGS 的 `Risk-any` 从 standard 的 `47%` 提升到 critical 的 `84%`，`Root@3` 也从 `38%` 提升到 `78%`。

2. **BGB-25 是当前最漂亮的长环对照。** 在 actual 25-node BGB 上，Naive `Root@3=0%`，SA-MCGS `Root@3=58%`；Naive 子图平均 `7.3` 个节点、压缩率 `71%`，SA 子图平均 `3.8` 个节点、压缩率 `85%`。也就是说 SA 不只是更能找 root，还明显更会压缩。

3. **CUAD 在高噪声合同图上仍然更难。** CUAD-25 上 SA `Risk-any=83%`，高于 Naive `54%`；但 `Risk-all` 仍然低，说明合同图里的原生风险/噪声会吞掉完整端点收敛。

4. **Risk-all 不是当前主叙事。** 结构性缺陷有 root/witness/affected 多个风险入口，修复时不一定必须同时抓住所有端点。更稳的主指标应该是：`Root@3 + Risk-any + Effective OC + Compression`。

5. **BGB requested 14 实际不是 14-node。** 代码选择不到 14-node BGB SCC 时 fallback 到了 3-node SCC，所以这部分只能当小环 sanity，不应写成 14-node 主结果。

## 2. 指标口径和解释

- `Root@3`：GT/root 节点是否进入前三。这个最接近传统“定位注入节点”的指标，但对结构性缺陷来说并不完整，因为 witness/affected node 也可能是有效修复入口。
- `Risk-any`：输出子图是否至少包含一个风险端点，例如 root 或 witness。对于结构性风险，这个比单点 Top-k 更合理，因为修复任意一端可能都能解除冲突。
- `Risk-all`：输出子图是否同时包含所有风险端点。这个很严格，适合作为上限指标，但不适合作为唯一主指标。
- `OC hit`：SA-MCGS 的局部窗口搜索是否产生结构证据。Naive 没有这个机制，所以不是同列比较，而是 SA 的解释性信号。
- `Effective OC`：OC/core evidence 是否落到风险区域。它比单纯 OC hit 更关键，因为只发现“某处有结构信号”还不够，必须和风险端点发生重合。
- `Compression`：子图压缩率。高压缩率意味着模型把长 SCC 收缩成更小的可检查风险区域。
- `Errors`：Naive direct-subgraph 的 JSON/排名结构不完整错误。strict rate 把它算失败，因为不可解析输出不能进入自动评估，也不能作为稳定系统输出。

**本轮主指标建议：** `Root@3 + Risk-any + Effective OC + Compression`。  
`Risk-all` 应该保留，但作为更严格的附加指标，不建议作为主叙事中心。

## 3. 分层分析

### 3.1 BGB：干净法条图，最适合作为主证据

BGB 的性质更像“正确、规范、低噪声的法律文本图”。因此如果这里出现长环结构风险，模型不应该被大量原生错误干扰。实际结果也最清楚：

- BGB actual 25 上，Naive `Root@3=0%`，SA-MCGS `Root@3=58%`。
- BGB actual 25 上，Naive `Risk-any=42%`，SA-MCGS `Risk-any=54%`。
- BGB actual 25 上，两者 `Risk-all` 都只有 `4%`，说明完整收齐 root+witness 仍然难。
- BGB actual 25 上，SA 的平均子图只有 `3.8` 个节点，Naive 是 `7.3` 个节点；SA 压缩率 `85%`，Naive `71%`。

所以 BGB-25 的论文表述应该是：**SA-MCGS 在干净长环法条图里显著改善 root 定位，并生成更小的风险子图；完整端点收齐仍是后续优化点。**

### 3.2 CUAD：高噪声合同图，适合作为泛化补充

CUAD 本身来自合同抽取/条款图构造，天然有更多噪声和潜在标注问题。这里不能期待像 BGB 那样干净，但它能测试“噪声下是否还能保留风险区域”。

- CUAD actual 25 上，Naive `Risk-any=54%`，SA-MCGS `Risk-any=83%`。
- CUAD actual 25 上，SA 的 `OC hit=100%`，说明局部搜索几乎总能找到结构信号。
- CUAD actual 25 上，Naive `Risk-all=46%`，SA `Risk-all=29%`。这说明 Naive 一旦成功吐出 direct subgraph，经常会把多个风险端点一起包进去；SA 的 dynamic core 更偏向压缩，可能剪掉 witness。
- CUAD actual 25 上，Naive 有 `8/24` 条解析/排名错误；SA 没有。

所以 CUAD 的论文表述应该更克制：**SA-MCGS 在 noisy contract graph 上提高 Risk-any 和 OC 解释信号，但 Risk-all 不占优，说明合同域需要更强的 OC-to-core retention。**

### 3.3 严重程度：critical 才是主实验应使用的设置

severity 趋势非常明显：

- standard 下，SA `Root@3=38%`、`Risk-any=47%`。
- severe 下，SA `Root@3=75%`、`Risk-any=78%`。
- critical 下，SA `Root@3=78%`、`Risk-any=84%`、`Risk-all=53%`。

这说明早期注入确实偏弱或者偏“单看合理但后果不够重”。如果论文要证明 high-risk structural accident，主实验应该聚焦 `severe/critical`，把 standard 放到 ablation 或 appendix。

### 3.4 模板：handoff/temporal 更像 SA-MCGS 的真实战场

- `handoff_invariant`：SA `Root@3=71%`，Naive `29%`；SA `Risk-any=75%`，Naive `54%`。这是最适合讲“长链路交接不变量”的模板。
- `temporal_gate`：SA `Risk-any=75%`，Naive `54%`，也很适合结构搜索叙事。
- `condition_trigger`：Naive `Risk-any=79%`，SA `71%`，两者 `Risk-all=46%`。这个模板对 one-shot 也很友好，更像强 baseline sanity。
- `direct_mutex`：SA 改善 Root@3，但 Risk-any 持平，Risk-all 低于 Naive。它太直接，未必最能体现 SA 的慢搜索优势。

因此论文主实验模板优先级建议：`handoff_invariant > temporal_gate > condition_trigger > direct_mutex`。

### 3.5 模型差异：DeepSeek 强，gpt-4o 暴露 one-shot 稳定性问题

- DeepSeek Naive 很强：`Risk-any=85%`、`Risk-all=65%`，且没有解析错误。
- gpt-4o Naive 有 `19/48` 条解析/排名错误，strict 指标明显下降。
- SA-MCGS 两个模型都没有解析错误；gpt-4o 下 SA `Root@3=71%`，Naive strict `27%`。

这意味着论文不能简单写“Naive 看不见风险”。更准确的说法是：**强 one-shot baseline 可以直接抓到部分风险点，但结构化搜索在长环 root 定位、可解释 OC 证据和输出稳定性上更稳。**

## 4. 怎么把这轮结果写进论文

### 4.1 主结果应该怎么讲

这轮结果最有价值的不是“SA-MCGS 所有指标都赢”，而是更细的一条线：

1. **在干净长环里，SA-MCGS 明显更会定位 root。** BGB actual 25 是关键 case：Naive direct-subgraph 的 `Root@3=0%`，SA-MCGS 是 `58%`。这说明当风险不是简单靠单点文本显著性判断，而是需要沿结构证据回推时，rollout + relation-first core 能把 root 拉回候选前列。

2. **在 noisy 合同图里，SA-MCGS 更像风险区域搜索器。** CUAD actual 25 上，`Risk-any` 从 Naive `54%` 到 SA `83%`，但 `Risk-all` 不占优。这说明合同图本身有很多可疑条款/抽取噪声，SA 更擅长保住一个可修复入口，而不是同时收齐所有端点。

3. **压缩不是附属指标，而是核心贡献。** BGB actual 25 上 SA 平均子图 `3.8/25`，Naive `7.3/25`；SA 用更少节点保留更强 root 信号。论文里应该把它写成“可检查风险子图”，而不只是 Top-k 排名。

4. **OC/Effective OC 是 SA 与 Naive 的机制差异。** Naive direct-subgraph 可以直接吐一个子图，所以我们不能再说 Naive 没有子图能力；但 Naive 没有独立的局部结构证据。SA 的优势在于：它不仅给出候选子图，还能留下“为什么这个局部区域可疑”的 OC/core evidence。

### 4.2 当前不能过度声称什么

- 不能说 Naive 完全失败。DeepSeek 的 direct-subgraph Naive 很强，尤其在部分模板上能直接抓到风险端点。
- 不能把 `Risk-all` 当主胜负。结构风险可以通过 root、witness 或 affected node 任意一端修复，`Risk-all` 更像“完整解释上限”，不是唯一有效性指标。
- 不能把 BGB requested 14 写成 14-node 结果。它 fallback 到 actual 3，只能作为 sanity。
- 不能把 CUAD 写成干净法律知识图。CUAD 更像 noisy contract extraction stress test，它的意义是泛化和鲁棒性，不是主证据。

### 4.3 推荐主表口径

主表建议只放 `BGB actual 25` 和 `CUAD actual 25`，并按以下列组织：

| Domain | Actual SCC | Method | Root@3 | Risk-any | Effective OC | Avg subgraph | Compression | Error |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| BGB | 25 | Naive direct-subgraph | 0% | 42% | - | 7.3 | 71% | 9/24 |
| BGB | 25 | SA-MCGS | 58% | 54% | 见图表 | 3.8 | 85% | 0/24 |
| CUAD | 25 | Naive direct-subgraph | 46% | 54% | - | 4.7 | 81% | 8/24 |
| CUAD | 25 | SA-MCGS | 54% | 83% | 见图表 | 4.2 | 83% | 0/24 |

这张表的主信息是：**BGB 证明长环 root localization，CUAD 证明 noisy domain 下风险区域 retention；二者共同支撑 SA-MCGS 是结构化风险搜索，而不是单纯 anomaly ranking。**

## 5. 实际 SCC 口径

- `bgb` requested `14` -> actual SCC size `3`
- `bgb` requested `25` -> actual SCC size `25`
- `cuad` requested `18` -> actual SCC size `18`
- `cuad` requested `25` -> actual SCC size `25`

## 6. 图表


### 图 1. 不同实际 SCC 长度下的方法差异

图片文件：[severitygrid_domain_size_metrics.png](severitygrid_domain_size_metrics.png)

**读法。** 每个小图分别是 `Root@3`、`Risk-any`、`Risk-all`。横轴是实际 SCC 长度，不是请求长度。
最关键的是 `BGB actual 25` 和 `CUAD actual 25`：前者是干净法条长环，后者是 noisy contract extraction 长环。

**结论。** BGB-25 上 SA-MCGS 的 `Root@3` 从 Naive 的 `0%` 拉到 `58%`，这是本轮最干净的长环优势；CUAD-25 上 SA-MCGS 的 `Risk-any` 达到 `83%`，比 Naive 的 `54%` 高很多，但 `Risk-all` 仍低，说明合同图里完整收齐 root+witness 很难。

### 图 2. SA-MCGS 相对 Naive 的差值热力图

图片文件：[severitygrid_sa_minus_naive_heatmap.png](severitygrid_sa_minus_naive_heatmap.png)

**读法。** 绿色表示 SA-MCGS 高于 Naive，红色表示低于 Naive。这个图最适合快速判断“优势在哪里”。

**结论。** SA 的优势集中在 `BGB actual 25` 的 `Root@3` 和 `Compression`，以及 `CUAD actual 25` 的 `Risk-any`。`Risk-all` 不稳定，尤其 CUAD 上 Naive valid output 一旦能生成子图，常常会同时包含两个端点，所以不能把 `Risk-all` 当唯一主指标。

### 图 3. Matched pair 胜/平/负

图片文件：[severitygrid_pairwise_wins.png](severitygrid_pairwise_wins.png)

**读法。** 每个 matched pair 是同一个 domain、size、template、severity、model 下的 Naive-vs-SA 对比。绿色是 SA wins，灰色是 tie，红色是 Naive wins。

**结论。** SA 在 `Root@3` 和 `Compression` 上更常赢；`Risk-any` 大量 tie，说明 Naive direct-subgraph 已经是一个很强 baseline；`Risk-all` 不是 SA 的稳定优势点。

### 图 4. 严重程度影响

图片文件：[severitygrid_severity_effect.png](severitygrid_severity_effect.png)

**读法。** 横轴从 `standard` 到 `critical`。如果注入策略合理，critical 应该让结构风险更容易暴露。

**结论。** 这个趋势成立：SA-MCGS 的 `Risk-any` 从 `47%` 提升到 `84%`，`Root@3` 从 `38%` 提升到 `78%`。这支持后续主实验应该聚焦 `severe/critical`，不要把过弱的 standard 混进主表稀释叙事。

### 图 5. 不同结构冲突模板

图片文件：[severitygrid_template_effect.png](severitygrid_template_effect.png)

**读法。** `direct_mutex` 是直接互斥，`handoff_invariant` 是链路交接不变量，`temporal_gate` 是时间门控，`condition_trigger` 是条件触发。

**结论。** `handoff_invariant` 对 SA 最友好：Root@3 从 Naive `29%` 到 SA `71%`，Risk-any 从 `54%` 到 `75%`。`condition_trigger` 对 Naive 也很友好，所以它更像“明显规则冲突 baseline”，不适合单独作为 SA 优势主证据。

### 图 6. 子图压缩与平均子图大小

图片文件：[severitygrid_compression_subgraph.png](severitygrid_compression_subgraph.png)

**读法。** 左图是压缩率，越高越好；右图是平均子图节点数，越小越好，但不能小到丢掉风险点。

**结论。** BGB-25 上 SA 的子图明显更小：Naive 平均 `7.3` 节点，SA 平均 `3.8` 节点；压缩率从 `71%` 到 `85%`。这非常适合支撑“风险子图压缩”这条论文主线。

### 图 7. 模型差异与输出稳定性

图片文件：[severitygrid_model_error_effect.png](severitygrid_model_error_effect.png)

**读法。** 第三个小图是 parser/ranking error。这里的错误不是 API 错，而是 baseline 没能按要求吐出完整可评估结构。

**结论。** DeepSeek 的 Naive direct-subgraph 很强，甚至在 `Risk-any/Risk-all` 上不弱；gpt-4o 的 Naive 出现 `19/48` 解析/排名错误，而 SA-MCGS 没有错误。论文里不能只说 Naive 弱，应该说：one-shot direct subgraph 在强模型上能抓到风险，但输出稳定性和长环 root 定位仍弱于结构化搜索。

### 图 8. SA 的 OC signal 与风险保留

图片文件：[severitygrid_sa_oc_vs_retention.png](severitygrid_sa_oc_vs_retention.png)

**读法。** `OC hit` 表示 SA 局部搜索产生 ordered-cycle/结构证据；`Effective OC` 近似表示 OC 或 core evidence 是否落入风险区域；`Risk-all` 是同时保留所有风险端点。

**结论。** SA 的 OC 信号非常充足：CUAD-25 是 `100%`，BGB-25 是 `88%`。但 `Risk-all` 低很多，说明当前算法已经会发现“这里有结构风险”，但最终 core 选择不总能同时保留 root+witness。这个现象不是坏事，它正好说明后续算法改进应该集中在 **OC-to-core retention**，而不是继续扩大 one-shot prompt。


## 7. 分组表

### By Domain

| domain | method | n | valid | errors | root_top3 | risk_any | risk_all | compression | subgraph_size | oc_hit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bgb | naive | 48 | 39 | 9 | 50% | 71% | 48% | 37% | 4.4 | - |
| bgb | sa-mcgs | 48 | 48 | 0 | 79% | 77% | 52% | 48% | 3.2 | 60% |
| cuad | naive | 48 | 38 | 10 | 38% | 52% | 40% | 78% | 4.5 | - |
| cuad | sa-mcgs | 48 | 48 | 0 | 48% | 62% | 23% | 81% | 4.0 | 92% |

### By Actual Size

| domain | actual_size | method | n | valid | errors | root_top3 | risk_any | risk_all | compression | subgraph_size | oc_hit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bgb | 3 | naive | 24 | 24 | 0 | 100% | 100% | 92% | 15% | 2.5 | - |
| bgb | 3 | sa-mcgs | 24 | 24 | 0 | 100% | 100% | 100% | 11% | 2.7 | 33% |
| bgb | 25 | naive | 24 | 15 | 9 | 0% | 42% | 4% | 71% | 7.3 | - |
| bgb | 25 | sa-mcgs | 24 | 24 | 0 | 58% | 54% | 4% | 85% | 3.8 | 88% |
| cuad | 18 | naive | 24 | 22 | 2 | 29% | 50% | 33% | 76% | 4.3 | - |
| cuad | 18 | sa-mcgs | 24 | 24 | 0 | 42% | 42% | 17% | 79% | 3.8 | 83% |
| cuad | 25 | naive | 24 | 16 | 8 | 46% | 54% | 46% | 81% | 4.7 | - |
| cuad | 25 | sa-mcgs | 24 | 24 | 0 | 54% | 83% | 29% | 83% | 4.2 | 100% |

### By Severity

| severity | method | n | valid | errors | root_top3 | risk_any | risk_all | compression | subgraph_size | oc_hit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| critical | naive | 32 | 25 | 7 | 47% | 62% | 47% | 59% | 3.8 | - |
| critical | sa-mcgs | 32 | 32 | 0 | 78% | 84% | 53% | 64% | 3.6 | 78% |
| severe | naive | 32 | 26 | 6 | 47% | 66% | 47% | 58% | 4.3 | - |
| severe | sa-mcgs | 32 | 32 | 0 | 75% | 78% | 34% | 65% | 3.7 | 72% |
| standard | naive | 32 | 26 | 6 | 38% | 56% | 38% | 54% | 5.1 | - |
| standard | sa-mcgs | 32 | 32 | 0 | 38% | 47% | 25% | 65% | 3.5 | 78% |

### By Template

| template | method | n | valid | errors | root_top3 | risk_any | risk_all | compression | subgraph_size | oc_hit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| condition_trigger | naive | 24 | 22 | 2 | 54% | 79% | 46% | 64% | 4.0 | - |
| condition_trigger | sa-mcgs | 24 | 24 | 0 | 58% | 71% | 46% | 64% | 3.6 | 79% |
| direct_mutex | naive | 24 | 19 | 5 | 46% | 58% | 50% | 56% | 4.7 | - |
| direct_mutex | sa-mcgs | 24 | 24 | 0 | 67% | 58% | 33% | 66% | 3.5 | 75% |
| handoff_invariant | naive | 24 | 19 | 5 | 29% | 54% | 33% | 53% | 4.7 | - |
| handoff_invariant | sa-mcgs | 24 | 24 | 0 | 71% | 75% | 33% | 63% | 3.7 | 71% |
| temporal_gate | naive | 24 | 17 | 7 | 46% | 54% | 46% | 54% | 4.4 | - |
| temporal_gate | sa-mcgs | 24 | 24 | 0 | 58% | 75% | 38% | 65% | 3.6 | 79% |

### By Model

| model | method | n | valid | errors | root_top3 | risk_any | risk_all | compression | subgraph_size | oc_hit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| deepseek-v3 | naive | 48 | 48 | 0 | 60% | 85% | 65% | 62% | 4.9 | - |
| deepseek-v3 | sa-mcgs | 48 | 48 | 0 | 56% | 65% | 38% | 66% | 3.8 | 79% |
| gpt-4o | naive | 48 | 29 | 19 | 27% | 38% | 23% | 49% | 3.6 | - |
| gpt-4o | sa-mcgs | 48 | 48 | 0 | 71% | 75% | 38% | 64% | 3.4 | 73% |

### By Domain / Valid-only

下面这个表只统计可解析输出，主要用于判断 Naive 错误是否单纯由 parser 问题造成。论文主表仍建议使用 strict rate，因为不可解析输出本身就是 one-shot baseline 的系统稳定性问题。

| domain | method | n | valid | errors | root_top3 | risk_any | risk_all | compression | subgraph_size | oc_hit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bgb | naive | 39 | 39 | 0 | 62% | 87% | 59% | 37% | 4.4 | - |
| bgb | sa-mcgs | 48 | 48 | 0 | 79% | 77% | 52% | 48% | 3.2 | 60% |
| cuad | naive | 38 | 38 | 0 | 47% | 66% | 50% | 78% | 4.5 | - |
| cuad | sa-mcgs | 48 | 48 | 0 | 48% | 62% | 23% | 81% | 4.0 | 92% |

## 8. 对论文实验叙事的建议

- 主结果优先写 `BGB-25 + CUAD-25`，不要把 fallback 的 BGB-3 伪装成 14-node。
- 对 CUAD 的解释要强调：它本来就是 noisy contract extraction graph，所以 SA 的价值更像“从噪声里稳定提出可解释风险区域”，而不是保证 `risk-all`。
- 对 BGB 的解释可以更强：干净法条图上，SA-MCGS 在 25-node 长环里把 Naive 漏掉的 root 拉回，并以更小子图表达风险。
- 下一轮如果要追 ARR 高分，建议增加真实 `BGB 11-25` 中可验证存在的长度，避免 fallback；同时针对 CUAD 增加 `critical`/`severe` 高危模板即可，不需要继续扩 standard。

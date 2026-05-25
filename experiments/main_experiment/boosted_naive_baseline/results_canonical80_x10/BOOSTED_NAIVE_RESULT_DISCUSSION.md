# Boosted Naive 新结果对 paper 的最小修改清单

目标：根据新的 boosted Naive 数据，列出 paper 中必须调整的口径和可能需要补的图表。原则是：不大改正文，不增加正文长度；正文只做必要的等长替换或澄清；新增材料尽量放附录。

## 新数据需要纳入的事实

Boosted Naive 已经完成完整 80-block 跑法：

| 对照 | N | Root@3 | Risk-any | Risk-all | Compression |
|---|---:|---:|---:|---:|---:|
| one-shot Naive，当前 paper 主实验 | 320 | 48% | 72% | 47% | 67% |
| boosted Naive，single-attempt mean | 320 | 47.4% | 67.0% | 48.0% | 49.7% |
| boosted Naive，self_top3 | 320 | 52.1% | 74.5% | 51.6% | 59.6% |
| boosted Naive，oracle_risk_top3 | 320 | 58.4% | 79.4% | 62.2% | 60.0% |
| boosted Naive，oracle_compression_top3 | 320 | 53.3% | 74.7% | 47.4% | 63.5% |
| SA-MCGS，当前 paper 主实验 | 320 | 81% | 98% | 78% | 53% |

Boosted run 的错误情况：

- raw attempts: 3200。
- raw errors: 800。
- 每个 model-case 平均有效输出：7.50 / 10。
- 46 / 320 个 model-case 没有任何有效 boosted 输出。
- 没有 quota stop 的迹象。
- paper 中的错误解释应统一写成：full-SCC one-shot 输入太长，同时要求完整 global ranking 和 risk subgraph，导致长 context 下的解析崩坏、ranking 缺失/重复/非法、或者超时。

## 推荐总体口径

保留当前 one-shot Naive 作为正文主 baseline。Boosted Naive 作为附录里的 robustness / budget-control 实验。

这样可以避免正文大改，也能保持当前 Figure 3 的主结果结构。新的证据主要表达：

> 即使让 full-SCC Naive 重复跑 10 次，并用非 oracle 的 self_top3 选择结果，提升也比较有限，仍明显低于 SA-MCGS。Oracle selector 说明 10 次采样中有时存在更好的 Naive 输出，但这需要用真实指标挑选，只能作为 diagnostic upper bound。

## 正文必须改的地方

这些地方建议只做短替换，不新增大段文字。

1. `paper/latex/acl_latex.tex:55` abstract

   建议不改主结果数字。当前 `48 / 72 / 47` 是 one-shot Naive 主实验，仍然成立。

   如果决定把 boosted Naive 提到主 baseline，才需要把 Naive 数字改成 boosted self_top3：

   - `48% / 72% / 47%`
   - 改为 `52% / 75% / 52%`

   但这会连带要求主图和主结果段落都引入 boosted Naive，不符合“不要大改正文”的目标。因此不推荐。

2. `paper/latex/acl_latex.tex:308` baseline 定义

   当前写的是 full-context direct-subgraph baseline。需要明确这是 one-shot baseline，避免之后附录出现 boosted Naive 时产生混淆。

   建议把：

   - `a full-context direct-subgraph baseline`

   改成：

   - `a one-shot full-context direct-subgraph baseline`

3. `paper/latex/acl_latex.tex:318` Figure 3 caption

   Figure 3 caption 需要说明主图里的 Naive 是 locked one-shot full-SCC Naive。

   目的：让主图和附录 boosted control 分清楚。

4. `paper/latex/acl_latex.tex:322` main result 句子

   当前写 `SA-MCGS improves ... by xx points`。数字可以不动，但要说明对比对象是 one-shot full-SCC Naive。

   建议方向：

   - `Against one-shot full-SCC Naive, ...`

5. `paper/latex/acl_latex.tex:324-326` unavailable output 解释

   当前已经写到输出可能太大、不完整、不可用。需要把原因解释得更贴近新 boosted run 的证据：

   - full-SCC context 太长；
   - 一次生成里同时要求完整 global ranking 和 risk subgraph；
   - 因此会出现解析崩坏、ranking 缺失/重复/非法、或者 timeout。

   不建议在正文里写 quota、provider failure 或 network error。

6. `paper/latex/acl_latex.tex:330` model/domain breakdown 段落

   这里仍然可以保留原主实验结论，但建议加上 one-shot 限定。

   原因：boosted Naive 下模型故事会变。Gemini 和 DeepSeek 在 repeated sampling 下很强，GPT-4o 有一定改善，Qwen 主要被 CUAD 长 context 崩坏拖累。

7. `paper/latex/acl_latex.tex:352` robustness checks 段落

   这是正文里最适合提 boosted Naive 的地方。建议等长替换，把原来的 robustness 句子改成“附录报告三个检查”：

   - compression-profile tradeoff；
   - matched usable-output / lite-output controls；
   - ten-sample boosted Naive control。

   如果正文只放一个 boosted 数字，建议写：

   - boosted self_top3 达到 `52% / 75% / 52%` 的 `Root@3 / Risk-any / Risk-all`，仍低于 SA-MCGS 的 `81% / 98% / 78%`。

## 附录必须增加的地方

这些可以增加长度。

1. 在 `paper/latex/acl_latex.tex:784` 附近的 experiment details 里增加一个小节。

   建议标题：

   - `Budgeted full-SCC Naive control`

   需要解释：

   - 每个 model-case 跑 10 次 full-SCC Naive。
   - `self_top3` 是唯一可部署、非 oracle 的 selector。
   - `oracle_risk_top3` 和 `oracle_compression_top3` 使用真实指标挑选，只能作为 diagnostic upper bound。
   - 失败输出作为 long-context unusable generations 计入。

2. 增加一张附录表。

   建议表格：

   | Method/control | Selector | N | Root@3 | Risk-any | Risk-all | Compression |
   |---|---|---:|---:|---:|---:|---:|
   | one-shot Naive | locked main | 320 | 48% | 72% | 47% | 67% |
   | boosted Naive | self_top3 | 320 | 52.1% | 74.5% | 51.6% | 59.6% |
   | boosted Naive | oracle_risk_top3 | 320 | 58.4% | 79.4% | 62.2% | 60.0% |
   | boosted Naive | oracle_compression_top3 | 320 | 53.3% | 74.7% | 47.4% | 63.5% |
   | SA-MCGS | locked main | 320 | 81% | 98% | 78% | 53% |

3. 增加 boosted run 的 reliability note。

   建议内容：

   - `3200` raw attempts；
   - `800` unusable attempts；
   - `46/320` model-case 没有任何有效 boosted 输出；
   - 错误来自 very long full-SCC context 加完整 global ranking / subgraph schema 的输出负担，表现为 timeout、解析崩坏、incomplete / duplicate / invalid ranking。

4. 可选：增加 boosted Naive 的 model/domain breakdown。

   这个有助于解释异质性：

   - Gemini 和 DeepSeek 在 boosted Naive 下很强；
   - GPT-4o 主要在 risk coverage 上有提升，但仍弱；
   - Qwen 被 CUAD 长 context 稳定性问题严重拖累；
   - CUAD 应该被解释成 long-context / output-burden stress，而不是普通 hard domain。

## 配图和表格怎么处理

推荐最小方案：

1. 主 Figure 3 不改数据、不加第三个方法。

   只改 caption 和正文说明：Figure 3 是 locked one-shot baseline。这样不会改变主文视觉结构。

2. 新 boosted 结果优先放附录表，不放主图。

   原因：boosted 结果有 selector 语义，尤其 oracle 上界不能和普通方法混画在主图里，否则会增加解释负担。

3. 如果需要图，放附录图。

   可做一个小的 appendix figure：

   - x-axis: one-shot Naive / boosted self_top3 / boosted oracle_risk_top3 / SA-MCGS；
   - bars: Root@3, Risk-any, Risk-all, Compression；
   - 不把 oracle_compression_top3 放主视觉也可以，只在表里保留。

   建议文件名：

   - `figA3_boosted_naive_control.pdf/png`

4. 只有当我们决定把 boosted Naive 升级为主 baseline 时，才重画 Figure 3。

   不推荐这么做，因为主图要加第三个方法，正文也必须解释 selector 和 oracle，会造成大改。

## 错误解释的推荐写法

可以用这种口径：

> We count unusable full-SCC generations in the denominator. In the boosted Naive control, failures arise from the long-context one-shot setting: the model must read the full SCC and emit a complete global ranking plus a risk subgraph in a single generation. Under this burden, outputs may time out or become unparseable through incomplete, duplicate, or invalid rankings.

中文理解就是：

> 我们把不可用的 full-SCC generation 计入分母。Boosted Naive 中的失败主要来自 long-context one-shot 设定：模型必须在一次生成中读取完整 SCC，并输出完整 global ranking 和 risk subgraph。在这个负担下，输出可能超时，或者因为 ranking 缺失、重复、非法而无法解析。

不要写成：

- quota failure；
- provider instability 是主因；
- generic network error；
- model refused。

## 不应该改的地方

- 不重写 method section。
- 不改变主 benchmark 定义。
- 不替换 SA-MCGS 主结果。
- 不把 oracle selector 写成可部署 baseline。
- 不在正文增加一大段 boosted Naive narrative。

## 当前附录的口径审查

当前附录整体没有严重口径错误，但如果要纳入 boosted Naive，需要补几处限定，否则读者会混淆 one-shot Naive、lite Naive、boosted Naive。

### 1. `Additional Experimental Details` 需要明确当前表是 one-shot 主实验

位置：`paper/latex/acl_latex.tex:786-789`

当前写法：

- main tables use locked profile；
- same SCC block is evaluated by full-SCC direct-subgraph Naive and SA-MCGS；
- strict rates count unusable structured outputs。

问题：

- 没有明确说这里的 Naive 是 one-shot。
- 加入 boosted Naive 后，`full-SCC direct-subgraph Naive` 这个名字会变得不够精确，因为 boosted Naive 也是 full-SCC direct-subgraph，只是重复跑 10 次再选 Top-3。

建议：

- 改成 `one-shot full-SCC direct-subgraph Naive`。
- 所有 appendix 表里的 `Naive` 行，如果涉及主实验，都默认解释为 one-shot locked main baseline。

### 2. Output reliability 表只能代表 one-shot 主实验，不能代表 boosted run

位置：`paper/latex/acl_latex.tex:791-805`

当前表：

- Naive usable structured outputs: `261/320`
- unavailable: `59/320`
- SA-MCGS: `320/320`

这个表对主实验没问题，但加入 boosted 后会有潜在混淆：

- boosted run 是 `3200` raw attempts，不是 `320` method records；
- boosted 有 `800` raw unusable attempts；
- 还有 `46/320` model-case 没有任何有效 boosted 输出；
- 这些不能混进当前 reliability 表。

建议：

- 当前表 caption 加 `one-shot main run` 或 `locked one-shot setting`。
- boosted 另起一张小表或一句 reliability note，不和 `59/320` 主实验表合并。

### 3. E1 / Figure A2 的口径基本对，但 caption 可以更精确

位置：`paper/latex/acl_latex.tex:808-812`

当前 caption：

> Reducing the output schema helps full-SCC prompting, although it does not close the endpoint-retention gap on long CUAD components.

问题：

- “helps full-SCC prompting” 有点泛。
- E1 具体说明的是：减少 schema 负担后，不可用输出下降，Risk-any/Root@3 有恢复，但 Risk-all 仍很低。
- 而且 lite 的平均耗时更长，不能让读者理解成全面更快/更稳定。

建议 caption 口径：

- `Reducing the output schema improves availability and recovers some risk signal, but it does not close the endpoint-retention gap on long CUAD components.`

中文意思：

- 轻量 schema 改善的是 availability 和部分 risk signal，不是证明 full-SCC prompting 已经被修好。

### 4. Appendix combined table B 需要标注 one-shot

位置：`paper/latex/acl_latex.tex:833-846`

当前 B 表：

- Strict Naive: 320, 48%, 47%
- Valid-only Naive: 261, 59%, 57%
- Matched Naive / SA-MCGS

问题：

- 加入 boosted Naive 后，`Strict Naive` 会不够明确。

建议：

- 表头或 row label 改成 `one-shot Naive`。
- 或 caption 里说：`Naive rows in this table refer to the locked one-shot full-SCC baseline.`

### 5. Model-level strict breakdown 和 boosted model story 会不同

位置：`paper/latex/acl_latex.tex:850-864`

当前 one-shot 表中：

- Qwen Naive 很差，SA-MCGS 大幅提升；
- Gemini Naive 已经很强；
- DeepSeek Naive 也强；
- GPT-4o Naive 很弱。

Boosted 后的 story：

- Gemini / DeepSeek 仍强；
- GPT-4o 有一些 oracle headroom，但 self_top3 仍弱；
- Qwen 在 CUAD 上几乎全崩，boosted self_top3 仍很弱；
- 所以 boosted model breakdown 不能直接套用这张表的叙述。

建议：

- 当前表保持 one-shot strict breakdown。
- 如果附录加入 boosted model/domain breakdown，必须单独命名为 `Boosted Naive control`，不要和现有 `Model-level strict breakdown` 合并。

### 6. Domain-level strict breakdown 对 CUAD 的解释需要和 boosted 错误口径一致

位置：`paper/latex/acl_latex.tex:870-886`

当前表显示：

- CUAD Naive errors: `57/160`
- CUAD Naive Risk-all: `42%`
- SA-MCGS Risk-all: `75%`

Boosted run 中：

- CUAD 是错误最集中的 domain；
- Qwen + CUAD 几乎全失败；
- GPT-4o + CUAD 也有明显不可用输出。

建议：

- 当前 domain 表不用改数字。
- 但如果正文或附录解释 CUAD，应写成 `long-context/output-burden stress`，不要只说 `hard domain`。
- 报错解释统一为：长 full-SCC context 下，模型需要一次性输出完整 global ranking 和 risk subgraph，导致 timeout 或解析崩坏。

### 7. `Matched usable-output rates show that the gap is not only output availability` 这句话仍成立，但要避免和 boosted 混用

位置：`paper/latex/acl_latex.tex:886`

当前 caption：

> Matched usable-output rates show that the gap is not only output availability.

这个对主 one-shot 实验成立：在 261 matched usable pairs 上 SA-MCGS 仍然更高。

问题：

- boosted Naive 是另外一个问题：它说明多次采样能找到更好的 full-SCC 输出，但 self selector 只带来有限提升。
- 不能用 matched usable-output 这句话直接解释 boosted Naive。

建议：

- 保留这句话，但加 one-shot 限定。
- boosted 另写：`Repeated full-SCC sampling provides only a modest non-oracle gain; oracle selectors are diagnostic upper bounds.`

## 附录新增 boosted Naive 时的推荐结构

最稳的结构是在 `Additional Experimental Details` 里按顺序放：

1. Locked one-shot run configuration。
2. One-shot output reliability 表，也就是现在的 `261/320` 表。
3. Naive output-burden control，也就是现在的 Figure A2。
4. 新增 `Budgeted full-SCC Naive control`。

新增 boosted 小节需要包含：

- 10 attempts per model-case；
- self_top3 是非 oracle selector；
- oracle_risk_top3 / oracle_compression_top3 是 diagnostic upper bounds；
- failures 计入 denominator；
- 错误解释为 long-context full-SCC generation burden，而不是 quota/provider/network headline。

建议不要把 boosted Naive 塞进现在的 combined Table A/B/C/D。那张表已经很挤，而且语义是 one-shot strict/matched breakdown；boosted 是另一个控制实验，单独放更清楚。

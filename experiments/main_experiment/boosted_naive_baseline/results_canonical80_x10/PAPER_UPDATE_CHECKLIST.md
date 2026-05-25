# Paper 更新确认清单：oracle_risk_top3 作为新 baseline

这份文件只列需要确认和修改的点，不直接修改 paper。当前决策：正文和 Figure 3 的 Naive baseline 使用 `oracle_risk_top3`；`self_top3` 和 `oracle_compression_top3` 放附录。

## 1. 新主口径

主文 baseline 从原来的 one-shot Naive 切换为：

- `boosted Naive oracle_risk_top3`：新的正文 baseline。
- `SA-MCGS`：保持原主实验结果不变。
- `boosted Naive self_top3`：放附录，作为非 oracle / deployable selector。
- `boosted Naive oracle_compression_top3`：放附录，作为 compression-first diagnostic。
- `one-shot Naive`：放附录，作为原始 locked one-shot control。

必须注意：

- `oracle_risk_top3` 使用真实评估指标在 10 次 full-SCC Naive 输出中挑选 risk-first Top-3，因此正文、图注、表名必须统一写成 `oracle-risk` baseline；机制解释可以写 `risk-prioritized oracle`。
- 不能把 `oracle_risk_top3` 写成普通可部署 selector。
- 新主文问题变成：即使用 oracle-risk 从 10 次 full-SCC Naive 中挑选，SA-MCGS 仍有更高 endpoint retention。

## 2. 主结果数字

旧 paper 主结果：

| Method | N | Root@3 | Risk-any | Risk-all | Compression |
|---|---:|---:|---:|---:|---:|
| one-shot Naive | 320 | 48% | 72% | 47% | 67% |
| SA-MCGS | 320 | 81% | 98% | 78% | 53% |

新主结果建议：

| Method | N | Root@3 | Risk-any | Risk-all | Compression |
|---|---:|---:|---:|---:|---:|
| boosted Naive oracle_risk_top3 | 320 | 58.4% | 79.4% | 62.2% | 60.0% |
| SA-MCGS | 320 | 81% | 98% | 78% | 53% |

主文可四舍五入写：

- Naive oracle-risk baseline: `58% / 79% / 62%`
- SA-MCGS: `81% / 98% / 78%`
- gains: `+23 Root@3`, `+19 Risk-any`, `+16 Risk-all`

Compression：

- oracle_risk_top3: `60%`
- SA-MCGS: `53%`
- 不能再用旧的 `67% vs 53%` 压缩差距。

## 3. Figure 3 必改

相关位置：

- LaTeX 引用：`paper/latex/acl_latex.tex` 中 `fig02_main_results_composite.pdf`
- 生成脚本：`experiments/main_experiment/build_paper_assets.py`
- 输出文件：`experiments/main_experiment/paper_assets/figures/fig02_main_results_composite.pdf/png`

必须改：

- Panel A 的 Naive 点改成 `boosted Naive oracle_risk_top3`。
- Panel B 的 SCC-size breakdown 也用 `oracle_risk_top3`。
- 图例建议用 `Oracle-risk Naive`，不要只写 `Naive`。
- Caption 需要说明：Naive baseline is selected by oracle-risk Top-3 over 10 full-SCC attempts。

不要做：

- 不要把 `self_top3` 放进主 Figure 3。
- 不要把 `oracle_compression_top3` 放进主 Figure 3。
- 不要把 one-shot Naive、self_top3、oracle_risk_top3、SA-MCGS 全塞进主图；这些对照放附录表。

## 4. Figure 3 size breakdown 新数字

按 `oracle_risk_top3`：

| SCC size bucket | N | Root@3 | Risk-any | Risk-all | Compression |
|---|---:|---:|---:|---:|---:|
| short <=12 | 144 | 70.4% | 95.4% | 78.9% | 57.6% |
| mid 14-20 | 96 | 48.6% | 67.4% | 47.2% | 63.5% |
| long >=24 | 80 | 48.5% | 65.2% | 50.0% | 60.3% |

SA-MCGS 的 size breakdown 保持当前主实验数字。

正文中原来的 size 句子需要改：

- 旧：short `55% -> 83%`
- 旧：mid `40% -> 80%`
- 旧：long `41% -> 65%`

新句子应按 oracle-risk baseline 改成大约：

- short: `79% -> 83%`
- mid: `47% -> 80%`
- long: `50% -> 65%`

最终落字前建议用脚本重算 SA-MCGS bucket，避免手工误差。

## 5. 主表必须改

相关文件：

- `experiments/main_experiment/paper_assets/tables/tab03_main_results_strict.csv`
- `experiments/main_experiment/paper_assets/tables/tab03_main_results_strict.md`
- LaTeX 中主结果文字和 Figure 3 caption

需要改：

- `naive` 行替换为 `boosted Naive oracle_risk_top3`。
- `errors` 不再用 one-shot `59`。
- oracle-risk baseline 的有效性来自 10 次 raw attempts，因此主表里的 error 列需要重新设计。

建议：

- 主表不放 `errors` 列，只放主指标。
- Reliability 单独放附录，因为 boosted baseline 有两个分母：
  - raw attempt 层级：`800/3200` unusable；
  - model-case 层级：`46/320` zero-valid。

如果主表必须保留 error：

- 不要写 `errors=800` 配 `N=320`，这会混淆分母。
- 可以写 `zero-valid cases = 46/320`，raw errors 放 caption 或附录 reliability。

## 6. Reliability 表必须拆开

旧 reliability：

| Method | Usable | Unavailable |
|---|---:|---:|
| one-shot Naive | 261/320 | 59/320 |
| SA-MCGS | 320/320 | 0/320 |

新 boosted reliability：

- raw attempts: `2400/3200` usable，`800/3200` unusable。
- model-cases with at least one valid output: `274/320`。
- zero-valid model-cases: `46/320`。
- mean valid attempts: `7.50/10`。

建议附录分两张表或一张分组表：

1. one-shot / SA-MCGS locked run reliability。
2. boosted Naive x10 reliability。

正文如果提 reliability，只写短句：

> Boosted Naive keeps unusable full-SCC generations in the denominator; failures concentrate under long-context ranking/subgraph generation.

## 7. Model-level breakdown 必须改

新主口径是 `oracle_risk_top3` vs SA-MCGS。

`oracle_risk_top3` model breakdown：

| Model | Root@3 | Risk-any | Risk-all | Compression | zero-valid cases |
|---|---:|---:|---:|---:|---:|
| GPT-4o | 36.9% | 75.6% | 37.1% | 65.4% | 6 |
| DeepSeek-V3 | 87.1% | 94.6% | 86.7% | 73.7% | 0 |
| Qwen2.5-72B | 10.8% | 47.5% | 28.3% | 21.9% | 40 |
| Gemini 2.5 Pro | 98.8% | 100.0% | 96.7% | 79.1% | 0 |

叙述需要更新：

- Gemini 和 DeepSeek 的 oracle-risk Naive 已经很强。
- SA-MCGS 的主要优势变成稳定性、非 oracle 搜索、以及在弱模型/长 context 下的 endpoint retention。
- Qwen 仍被 CUAD 长 context 崩坏严重拖累。
- GPT-4o 即使用 oracle-risk 选择，Risk-all 仍明显弱于 SA-MCGS。

## 8. Domain-level breakdown 必须改

新主口径是 `oracle_risk_top3` vs SA-MCGS。

`oracle_risk_top3` domain breakdown：

| Domain | Root@3 | Risk-any | Risk-all | Compression | zero-valid cases |
|---|---:|---:|---:|---:|---:|
| BGB | 45.8% | 88.9% | 50.0% | 61.3% | 1 |
| CUAD | 53.0% | 62.2% | 50.6% | 58.6% | 45 |
| Debian | 64.6% | 100.0% | 80.2% | 61.5% | 0 |
| SEC EX-21 | 74.2% | 100.0% | 85.4% | 61.6% | 0 |

CUAD 解释必须更新：

- 不能只说 “CUAD is hard”。
- 应写成：CUAD 是 long-context / output-burden stress；full-SCC boosted Naive 在 CUAD 上容易出现 timeout 或 ranking/subgraph 解析崩坏。

## 9. Abstract 必须改数字

旧句：

> improves strict Root@3 from 48% to 81%, Risk-any from 72% to 98%, and Risk-all from 47% to 78%.

新句建议：

> improves Root@3 from 58% to 81%, Risk-any from 79% to 98%, and Risk-all from 62% to 78% over an oracle-risk Top-3 full-SCC Naive baseline.

注意：

- 如果正文使用 `oracle_risk_top3`，abstract 不能再写旧 `48 / 72 / 47`。
- `strict` 这个词要谨慎，因为 oracle-risk baseline 是 Top-3 aggregate，不是 one-shot method record strict。
- 建议写 `oracle-risk Top-3 full-SCC Naive baseline`，避免读者误解。

## 10. Main Results 段落必须改

旧：

- gains: `+32 / +26 / +31`
- Naive often finds one suspicious record
- Naive returns smaller subgraphs on average

新：

- gains: `+23 / +19 / +16`
- oracle-risk Naive 已经是 10 次 full-SCC 输出中的 risk-first 上界；
- SA-MCGS 仍高于这个 baseline，说明优势不是只来自 Naive 单次采样坏运气；
- compression 差距变成 `60% vs 53%`。

推荐主文表达：

> Even against an oracle-risk Top-3 selection over ten full-SCC Naive attempts, SA-MCGS retains more complete repair endpoints.

## 11. Robustness / appendix checks 需要重排

新结构建议：

1. 主结果：`oracle_risk_top3` vs SA-MCGS。
2. 附录 selector comparison：
   - `self_top3`
   - `oracle_risk_top3`
   - `oracle_compression_top3`
3. 附录 one-shot control：
   - 原 one-shot Naive `48 / 72 / 47 / 67`
4. 附录 reliability：
   - one-shot unavailable；
   - boosted raw attempt errors；
   - zero-valid model-cases。
5. 附录 compression profile：
   - SA-MCGS current/default vs balanced。

## 12. 另外两个 selector 放附录

附录表建议：

| Control | N | Root@3 | Risk-any | Risk-all | Compression | Role |
|---|---:|---:|---:|---:|---:|---|
| one-shot Naive | 320 | 48% | 72% | 47% | 67% | original locked control |
| boosted Naive single-attempt mean | 320 | 47.4% | 67.0% | 48.0% | 49.7% | raw repeated-sampling mean |
| boosted Naive self_top3 | 320 | 52.1% | 74.5% | 51.6% | 59.6% | non-oracle selector |
| boosted Naive oracle_risk_top3 | 320 | 58.4% | 79.4% | 62.2% | 60.0% | main oracle-risk baseline |
| boosted Naive oracle_compression_top3 | 320 | 53.3% | 74.7% | 47.4% | 63.5% | compression-first diagnostic |
| SA-MCGS | 320 | 81% | 98% | 78% | 53% | proposed method |

解释：

- `oracle_risk_top3` 是正文 baseline。
- `self_top3` 说明不用真实指标时 boosted Naive 能达到多少。
- `oracle_compression_top3` 说明 compression-first 会伤 Risk-all。

## 13. 报错解释统一口径

推荐写法：

> Boosted Naive failures are counted as unusable full-SCC generations. They arise under long-context one-shot generation, where the model must read the complete SCC and emit a complete global ranking plus a risk subgraph in one response. Under this burden, outputs may time out or become unparseable through incomplete, duplicate, or invalid rankings.

中文口径：

> Boosted Naive 的失败计为不可用 full-SCC generation。失败来自 long-context one-shot 生成负担：模型需要一次读完整 SCC，并在同一次回复中输出完整 global ranking 和 risk subgraph。在这个负担下，输出可能超时，也可能因为 ranking 缺失、重复或非法而无法解析。

不要写：

- quota stop；
- provider failure 是主因；
- generic network error；
- API 不稳定作为主要解释。

## 14. 脚本需要改的地方

主要脚本：

- `experiments/main_experiment/build_paper_assets.py`

需要改：

1. 读取 `results_canonical80_x10/boosted_naive_top3_summary.csv`。
2. 构造 main `oracle_risk_top3` summary。
3. `create_main_results_composite_figure` 使用 `oracle_risk_top3` 替代 one-shot Naive。
4. `create_main_metrics_figure` 同样替换。
5. `create_scc_size_figure` 使用 `oracle_risk_top3` size buckets。
6. `create_main_tables` 输出新主表、model breakdown、domain breakdown、size breakdown。
7. 新增 appendix selector comparison 表。
8. 保留 one-shot Naive 表作为 control，不覆盖 raw source。

可能还要改：

- `experiments/main_experiment/generate_paper_supplements.py`，如果 E0/E1/E3 仍被复制成 appendix 表。
- `paper_assets/figures/README.md`
- `paper_assets/tables/figure_catalog.csv/md`
- `experiments/main_experiment/paper_assets/README.md`

## 15. LaTeX 需要改的地方

至少需要改：

- Abstract：主结果数字和 baseline 名称。
- Baseline definition：说明 main Naive 是 oracle-risk Top-3 over ten full-SCC Naive attempts。
- Figure 3 caption：说明 `oracle_risk_top3`。
- Main Results 数字和 gain。
- SCC-size analysis 数字。
- Model/domain breakdown 文字。
- Robustness checks：重排 oracle-risk baseline / self selector / compression selector / one-shot control / lite-output / compression profile 的关系。
- Appendix experiment details：新增 boosted Naive selector comparison。
- Appendix reliability：拆 raw-attempt reliability 和 model-case reliability。
- Appendix combined table：如果继续保留，需要更新成 oracle-risk baseline 或明确 one-shot control。

## 16. 已确认的关键决策

1. 主文 baseline 确定使用 `boosted Naive oracle_risk_top3`。
2. 主 Figure 3 只画 `oracle_risk_top3` vs `SA-MCGS`。
3. Figure 3 图例使用 `oracle-risk Naive`。
4. 主表移除旧 `errors` 列，把 reliability 放附录。
5. `self_top3` 和 `oracle_compression_top3` 只放附录 selector comparison 表。

后续实际修改 paper 时，所有正文、Figure 3、主表和附录表都按以上五条执行。

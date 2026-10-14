# Pilot 核心指标数据说明

本目录从已经完成的四源、单模型 GPT-4o pilot 离线派生指标。`build_metrics.py` 只使用 Python 标准库，不导入推理代码，不读密钥，不调用 API，不修改原实验文件。运行 `python3 build_metrics.py` 可重新生成三份指标数据。

- `metrics.json`：绘图入口，包含固定顺序的5组汇总、20条逐例记录、全流程资源消耗、输入文件哈希及定义。
- `metrics_by_case.csv`：逐例记录；每组内部按 Debian、SEC EX-21、BGB、CUAD 排列。
- `metrics_summary.csv`：SA、LEA首次、LEA最终、Full首次、Full最终5行汇总。

## 指标定义

| 指标 | 定义与范围 |
|---|---|
| Root@1 / Root@3 | 注入根节点在方法原始完整排名中位于前1/3位；固定以4例为分母。 |
| MRR | 每例根节点排名倒数的均值；排名从1开始，失败记0。 |
| Risk-any / Risk-all | 原生H是否保留至少一个/全部注入风险端点。每例有2个风险端点，含root。 |
| Endpoint recall | 每例 `H∩risk_nodes` 的节点数除以风险端点总数，再对4例求宏平均。 |
| Evidence-all | **本次新增离线诊断**：原生H是否保留全部 `planned_injection_identity.evidence_nodes`。 |
| Evidence recall | 每例 `H∩evidence_nodes` 的节点数除以证据节点总数，再对4例求宏平均。 |
| H / Compression | 原方法输出节点数；压缩率为 `1−|H|/|SCC|`，只对有效输出求宏平均。 |
| Elapsed | 本行请求最早reserve至最晚finish的ledger时间跨度，单位秒，包含间隔与重试。 |
| Tokens / Calls / Cost | 所属请求实际usage总和、API尝试数、按输入$2.50/M与输出$10.00/M估算的费用。 |

JSON里的比率均为0到1，图表显示百分比时乘100；tokens、calls、cost在汇总行中为4例总量，`mean_elapsed_sec`为每例平均。所有20条当前输出均有效；脚本仍按原报告的严格有效性与失败口径处理。

原生H分别读取 `evidence_risk_subgraph_nodes`、`lea_risk_subgraph_nodes`、`direct_risk_subgraph_nodes`，不使用旧的GT锚定输出，也不施加共同输出上限。首次诊断固定读取 `candidate_001.json`，不会改选第一个成功候选。最终输出来自 `final.json`，包含已选候选的原生H。

注入风险端点每例均为2个；Debian、SEC、BGB、CUAD的标记证据节点数依次为2、3、3、2。SEC和BGB各多一个bridge。**Risk-all不是Evidence-all**：SA本次保留全部8个风险端点，但未保留两个bridge，因此Risk-all为4/4，Evidence-all为2/4。证据节点齐全仍不证明边、关系方向或论证正确。

## 费用和耗时口径

首次行按照候选 `usage_before/after.accounted_tokens` 边界，从ledger中定位对应请求；它是最终流程的费用、tokens和耗时子集，不能再加到最终流程上。最终baseline行含全部候选与judge。脚本逐项核验原 `summary.json` 的Root@3、Risk-any/all、H、压缩率、usage与费用，并核验12个final；未知或未结束的ledger请求会阻止导出。

全局finance只汇总SA、LEA、Full三个实际arm，不重复计入首次行。本次397次请求均有usage，费用估值$5.9983475。各arm并发执行，全局墙钟时间取全部请求的首尾跨度，不能相加各arm耗时。首次候选没有独立程序计时器，因此所有行统一采用ledger跨度；该时间不能当作独立运行时的服务性能基准。

`candidate_count`指完成的有效候选数；本次与尝试数相同，SA对应null。`rollouts`只记录SA完成的轮数，baseline对应null。

## 解释限制

- 只有4个小源SCC、每源1个注入变体、1个模型；新增指标均为事后离线诊断，不支持显著性或跨域泛化结论。
- 每个arm每例共享160K token上限，实际消耗不同；LEA最多6候选、Full最多12候选。候选上限、保守整轮估值与评选预留都会导致提前停止。CUAD LEA实际仅1个候选、未调用judge，不能用于证明重复选择增益。预留额度不是实际消耗。
- 模型请求均使用同一渠道的`gpt-4o`别名，返回模型标签有多个值；这些标签保存在JSON来源信息中，不能据此确定真实快照是否相同。
- 注入gold之外的节点没有完整负标签，还可能是必要上下文，不能把H中的其他节点直接当作误报。这里不能估计自然风险识别的precision、F1或FPR。
- 共同cap诊断未改变本次任何H，因此不能视为等输出大小对照。原生H大小差异需与召回一起阅读。
- SA在Root@1上没有优势，MRR与Full接近；LEA最终的端点召回比首次下降，Full最终的SEC bridge丢失。应同时呈现这些结果，不能只选Root@3或端点Risk-all。

输入哈希和脚本哈希写入 `metrics.json` 的 `provenance`；重新生成前会检查输入与原报告的一致性，不会重新运行任何模型。

# LEA 补跑运行说明

运行目录：`/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/lea_full320_completion_20260923/`。

本批补齐同一套80个稳定案例在四个原模型上的LEA结果。已审定历史结果147条；补跑173条。用户授权本批新增API总开销上限为 **50美元**，所有模型、进程、失败调用和恢复运行共用同一账本与上限。

| 模型 | 历史可复用 | 本批任务 | 渠道与启动条件 |
|---|---:|---:|---|
| GPT-4o | 74 | 6 | XHub，先完成固定案例smoke，再跑剩余任务 |
| Gemini 2.5 Pro | 73 | 7 | XHub，先完成固定案例smoke，再跑剩余任务 |
| DeepSeek-V3 | 0 | 80 | XHub，先完成固定案例smoke，再跑剩余任务 |
| Qwen2.5-72B | 0 | 80 | OpenRouter；当前缺少 `OPENROUTER_API_KEY` 凭据，尚未启动 |
| 合计 | 147 | 173 | XHub可安排93条，Qwen等待凭据80条 |

这张表是冻结任务规模，不是动态完成数。三个XHub模型使用同一个固定原始案例（`main_case_order=20`）做smoke；成功且核验通过的smoke结果直接属于正式任务，恢复时复用已付费响应缓存。

## 刷新当前汇总

以下命令只读取本地结果并更新汇总，不调用API，不启动补跑：

```bash
/Users/chenlong/.pyenv/versions/3.11.0/bin/python /Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/lea_full320_completion_20260923/summarize_completion.py
```

刷新后先看 `SUMMARY_ZH.md` 和 `verification.json`。结果不齐时明确显示 **PARTIAL**；某模型不足80条时，该模型的完整范围均值留空。严格无效输出保留为正式结果，Root@3、Risk-any和Risk-all记0；Compression只对有效输出求均值。暂停、缺凭据、尚未完成的案例不视为严格无效，仍计入缺口。

已准备 `monitor_completion.py` 供后台只读监控：每10秒写入 `live_status.json`，每60秒或所有当前worker退出时刷新汇总。它只观察已经启动的进程，不启动或重试任何API任务；所有当前worker退出后写入 `finished` 或 `needs_attention` 并自动退出。Qwen未补齐时会保留缺凭据与剩余80条的说明。监控进程的启动由主任务处理。

仅获取一次快照并退出，可运行：

```bash
/Users/chenlong/.pyenv/versions/3.11.0/bin/python /Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/lea_full320_completion_20260923/monitor_completion.py --once
```

去掉 `--once` 会持续观察已记录的最新worker；同一模型按最新启动阶段与分片选取，旧smoke记录不计作当前活跃任务。`live_status.json` 中的 `observed_results` 是快速文件计数，正式科学覆盖以 `verified_coverage` 指向的最近一次完整身份核验为准。

## 进度与费用文件

| 文件或目录 | 含义 |
|---|---|
| `verification.json` | 总覆盖、逐模型覆盖、完整/部分状态、身份异常、账本费用快照 |
| `live_status.json` | 只读监控器的当前进程、快速结果计数、最近核验覆盖、费用及待处理原因 |
| `SUMMARY_ZH.md` | 可直接阅读的覆盖与费用汇总 |
| `worker_status/*.json` | 各模型/分片的当前案例、状态、进程号及最后更新时间；检查是否仍有活跃进程，不把旧状态文件当作实时心跳 |
| `case_attempts.jsonl` | 案例启动/结束事件，含模型、阶段、状态和worker |
| `case_status/*.json` | 每个尝试过的案例的最新状态；provider、budget或integrity暂停不计入科学结果覆盖 |
| `results/*__lea.json` | 正式完成或严格无效的终态结果；汇总逐条核验模型、稳定身份、来源与批准协议 |
| `budget_status.json` | 全批预算上限、已结算或保守计费、未结算预留、总承诺上界及余额 |
| `budget_ledger.jsonl` | 共享预算的完整reserve/settle事件；本批费用的权威来源，包含失败调用、重试和未完成案例 |
| `call_logs/llm_calls.jsonl` | 实际API调用及用量记录；从已保存缓存重放不算新付费调用 |
| `call_cache/<model>/<case_id>/responses.jsonl` | 已收到且付费的模型响应缓存，恢复时验证请求和批准协议后复用 |
| `protocol_amendments.json`、`amendments/` | 已审查的预算或适配器兼容修正及原协议、暂停记录、隔离结果的留档 |

`full320_case_metrics.csv` 固定保留320个目标格；`full320_breakdown.csv` 按模型、领域、SCC规模和模板分解。`matched_3method_case_metrics.csv` 与 `matched_3method_summary.csv` 仅包含当前三方法均有可用结果的共同集合，当前集合可能不足最终320个模型×案例对。SA比较字段固定使用可部署输出 `core_evidence_risk_subgraph_nodes`。

## 启动阶段记录

2026-09-23的启动检查发现两个适配问题：Gemini的用量含独立计费的thinking tokens，预算预留已按批准修正扩大；随后发现provider返回的嵌套usage元数据需要在进入旧evaluator前规范化。相应暂停保留了完整账本与响应缓存。受旧适配器fallback影响的两个smoke输出已归档隔离至 `amendments/20260923_usage_adapter/`，重算核验通过前不计入有效科学结果；恢复时从缓存重新解析。后续是否已恢复、已完成多少条，以刷新后的身份核验汇总及worker状态为准。

隔离后的核验快照为147/320（本批新增有效结果0），24次API调用均已结算，共 **$0.19760547**，未结算预留为0。24条响应缓存均已通过原JSON提取器的可解析性检查，正在进行适配器修正后的结果重建；同一已付费请求从缓存复用，尚未执行的后续请求仍按共享账本计费。旧适配器终态结果不因缓存兼容而恢复有效性，必须重新解析并通过新协议身份核验。

费用口径须区分：共享账本衡量本次50美元新增开销；历史结果按冻结单价换算的 `cost_usd_at_frozen_prices` 只是用量估价，不代表历史实际账单，也不占用本批新增额度。不要仅累加最终结果里的 `llm_usage_summary` 代替账本，因为它可能遗漏前次失败或额外预留。

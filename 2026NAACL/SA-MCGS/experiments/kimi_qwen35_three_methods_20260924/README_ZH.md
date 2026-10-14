# Kimi-VL 与 Qwen3.5 三方法实验

**2026-09-25 统计口径更新：按用户要求，仅对58个原严格失败案例补入可解析指标，其余422个成功案例指标不变；无法计算的值记0，全部指标（含压缩率）统一以每方法80例为分母。** 当前结果见 [按指标补入后的中文报告](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/parsing_recovery_audit_20260925/METRICWISE_RESULTS_ZH.md)。仅离线解析，没有新增推理调用。下方冻结协议及原始记录保留运行时口径。

**已于2026-09-25完成：两模型共480个科学终态（原运行诊断为422个有效、58个严格失败），运行故障和缺失均为0。原始结果已下载并验SHA，独立复核通过，两项GPU作业均已结束释放。** 原指标、实际分母、失败和解析回退记录见 [原始严格口径报告](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/final_analysis/FINAL_RESULTS_ZH.md)。

用户于2026-09-24授权两模型一条龙运行、夜间恢复端点、故障跳过并次日查看结果。原有模型和论文文件不变。本目录是独立实验；API推理全部使用各自Slurm节点的127.0.0.1，没有外部API支出，集群资源费用未折算。

## 模型与资源

| 标识 | 模型 | 固定版本 | 本地端口 |
|---|---|---|---|
| kimi | moonshotai/Kimi-VL-A3B-Instruct | 398eede0903cd983a2bfa0cc634e9ac1d843f375 | 18082 |
| qwen35 | Qwen/Qwen3.5-9B | c202236235762e1c871ad0ccb60c8ee5ba337b9a | 18083 |

两者均为官方BF16，TP=1，无量化，纯文本输入，服务上下文131072。Qwen客户端及服务默认均固定 `enable_thinking=false`。每模型单独一个单H800作业，16CPU/128G内存/最长5天；服务与全部实验脚本同节点。完成即释放GPU。CPU准备作业不占GPU：Kimi 395439，Qwen 395441。GPU作业使用对应afterok依赖，依赖失败则取消，不空等占卡。正式GPU作业已于23:22提交：Kimi **395516**，Qwen3.5 **395518**。详见各 `*_gpu_submission_receipt.json`。

远端根目录 `/aifs4su/hansirui_3rd/chenlong/kq35_20260924`。共享运行环境 `/aifs4su/hansirui/vllm-dsv4-venv` 只读；缓存、临时文件及模型权重都放本实验个人目录。使用既有SSH别名 Group3_slogin，登录暂时失败不代表集群作业停止。

## 冻结科学协议

同一80案例（20个物理SCC，各4种注入），每模型执行One-shot、LEA、SA-MCGS，合计480个计划格子。

- One-shot：原direct_subgraph提示，温度0，输出上限12000。
- LEA：窗口4、温度0.4、输出2048、内部并发1。
- SA-MCGS：budget60、窗口4、温度0.4、输出2048、内部并发8、current压缩配置。
- 每模型8个病例worker，vLLM最多32序列，8192分块预填充，显存利用率0.85。
- 全80长提示按各自tokenizer重新计数；每个真实动态请求也检查长度，绝不截断。
- 原科学代码和base_launcher按字节复用；新适配器单独冻结。Qwen3.5不继承历史托管Qwen按名称触发的8192上限，这一适配明确写入协议。
- 成功或模型输出严格失败均为不可变科学终态，不按分数好坏重跑。JSON最多3次解析，耗尽仍用原{}回退。
- 严格失败检测记0，压缩率缺失；SA采用core_evidence_risk_subgraph_nodes。

## 端点恢复与故障跳过

`supervisor.py`在Slurm节点自行维持服务与workers，不依赖本地电脑持续在线。每模型最多4次服务启动（初次+3次恢复），计数在 `recovery/MODEL.json` 持久保存，重启不清零；每个case-method最多4次执行尝试。

单请求失败但模型端点仍健康时，记录该格子的运行故障并继续。实际端点中断才退出75，由supervisor清理它自己启动的专用进程组、重启同一模型并按原请求及完成次序回放缓存。缓存不一致则记录故障，不能清掉缓存重新抽样。所有重试耗尽后，把未完成格子记为独立运行故障，不影响另一模型。源数据、版本或身份完整性错误停止该模型并保留证据。

模型输出问题存 `results/MODEL/results/`；运行故障存 `results/MODEL/infrastructure_failures/`。`terminal_results=240`只表示240格已结算；仅 `scientific_complete=true` 才表示240格都有科学终态。汇总同时给计划80分母保守率、实际可评估分母、有效压缩率及缺失/故障数量。绝不把服务故障当模型输出错误。

## 操作与交付

1. `cluster_snapshot.py`：只读读取本实验作业、下载、恢复记录、状态及有限日志，写 `cluster_live_status.json`。真实输出出现后可运行 `audit_runtime.py`，只读核对每方法首个实际请求的模型、预算、thinking配置及本地/服务端token计数；没有输出时不会误判通过。
2. `stage_and_submit_gpu.py --submit`：冻结源文件后幂等上传提交；durable intent出现但receipt缺失时，必须先查询精确作业身份，不再次sbatch。
3. `fetch_results.py --models kimi qwen35`：两者结算后下载原始结果到 `downloaded_final/` 并验SHA；也可仅传一个已结束模型。不会覆盖变化的已有结果。
4. `analyze_results.py --input-dir downloaded_final/kimi --input-dir downloaded_final/qwen35 --output-dir final_analysis --allow-incomplete`：独立只读重算指标，生成分析及逐案例JSON；依据这些结果另行整理 `final_analysis/FINAL_RESULTS_ZH.md`。缺失/故障明确列出。

夜间定时检查在当前任务跟进，仍正常运行时不重复提交，不频繁通知。仅处理本实验作业；不能更改共享环境、其它用户作业、旧模型结果、原论文，也不新增付费API。两模型均结束并完成本地收集分析后停止定时检查。若本地应用离线，集群supervisor仍持续运行和保存结果。

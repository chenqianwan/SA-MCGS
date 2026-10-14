# Cost / reliability 与 relation-prior sensitivity 报告

生成时间：2026-09-09T18:55:49+0800。协议：`cost_prior_12case_gpt4o_gemini25pro_b60_v1`。

## 冻结设计与身份验收

已冻结并验证 12 个不同 physical SCC；GPT-4o 与 Gemini 2.5 Pro 在每个 slot 的 source-SCC 与注入 fingerprint 完全一致。领域分布为 Debian/SEC/BGB/CUAD = 2/3/3/4，模板四类各 3 个，scale 为 small/medium/large = 6/3/3。Debian 在 locked benchmark 中只有 size 11 与 12 两个 eligible SCC，因此未通过重复注入伪造第三个独立 Debian SCC。

主成本表固定使用 `memory_stress / structural_simple_v2 / critical / current(default)`，SA-MCGS rollout budget=60，window=4，case concurrency=1、internal concurrency=1。One-shot 指一次 full-SCC direct-subgraph prompt。所有二元性能指标均按每个模型/方法 12 个冻结 cases 的严格分母汇总；invalid 与 missing 计为失败，不插补、不静默删除。

## Cost / reliability 主表

| Model | Method | Planned | Attempted | Valid | Invalid | Missing | Invalid rate / planned | Logical calls / planned | Recorded calls / planned | Input tok. / planned | Output tok. / planned | Total tok. / planned | Total tok. median attempted | Runtime / planned | Runtime median attempted | Root@3 strict | Risk-any strict | Risk-all strict | Compression mean valid-only | Compression n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-4o | One-shot (full-SCC, single attempt) | 12 | 12 | 9 | 3 | 0 | 0.250 | 0.8 | 1.0 | 16978.4 | 2941.3 | 19919.8 | 8022.0 | 20.967 | 22.141 | 0.333 | 0.583 | 0.250 | 0.672 | 9 |
| gpt-4o | GraphRAG-style LEA | 12 | 12 | 12 | 0 | 0 | 0.000 | 16.9 | 17.8 | 36304.1 | 22776.8 | 59080.8 | 32093.5 | 189.163 | 137.959 | 0.833 | 0.917 | 0.417 | 0.510 | 12 |
| gpt-4o | SA-MCGS | 12 | 12 | 12 | 0 | 0 | 0.000 | 57.2 | 59.6 | 112251.6 | 68418.4 | 180670.0 | 176320.0 | 570.897 | 574.744 | 0.917 | 1.000 | 0.833 | 0.510 | 12 |
| gemini-2.5-pro | One-shot (full-SCC, single attempt) | 12 | 12 | 12 | 0 | 0 | 0.000 | 1.0 | 1.0 | 19553.7 | 7502.3 | 27056.0 | 13848.5 | 85.885 | 66.774 | 1.000 | 1.000 | 1.000 | 0.693 | 12 |
| gemini-2.5-pro | GraphRAG-style LEA | 12 | 12 | 12 | 0 | 0 | 0.000 | 15.8 | 15.9 | 36594.3 | 31728.2 | 68322.5 | 53169.5 | 868.234 | 443.933 | 0.750 | 1.000 | 0.833 | 0.510 | 12 |
| gemini-2.5-pro | SA-MCGS | 12 | 12 | 12 | 0 | 0 | 0.000 | 51.4 | 53.5 | 115897.2 | 110161.4 | 226058.7 | 221469.5 | 1650.232 | 1413.088 | 0.917 | 1.000 | 0.917 | 0.574 | 12 |
| Both models | One-shot (full-SCC, single attempt) | 24 | 24 | 21 | 3 | 0 | 0.125 | 0.9 | 1.0 | 18266.0 | 5221.8 | 23487.9 | 12096.5 | 53.426 | 31.045 | 0.667 | 0.792 | 0.625 | 0.684 | 21 |
| Both models | GraphRAG-style LEA | 24 | 24 | 24 | 0 | 0 | 0.000 | 16.3 | 16.9 | 36449.2 | 27252.5 | 63701.7 | 45978.5 | 528.698 | 315.756 | 0.792 | 0.958 | 0.625 | 0.510 | 24 |
| Both models | SA-MCGS | 24 | 24 | 24 | 0 | 0 | 0.000 | 54.3 | 56.5 | 114074.4 | 89289.9 | 203364.3 | 205857.5 | 1110.565 | 908.860 | 0.917 | 1.000 | 0.875 | 0.542 | 24 |

`Compression mean valid-only` 只在有定义的有效输出上计算，并同时给出 `Compression n`；它没有被伪装成 strict all-case 指标。Calls/tokens 的 `/ planned` 分母包含所有冻结 cells，已发生的 invalid 调用仍计入成本。Runtime 是串行低并发实测，不能直接当作高并发 wall-clock 预测。

## Relation-prior sensitivity

仅扰动 `alphago_mcgs.evidence.relation_prior_weight`：0.68 / 0.85 / 1.02，其他参数、case identity、模型与预算不变。Nominal 0.85 必须通过配置与身份 parity 后逐字节引用 cost 主表的 SA-MCGS 结果，不重复付费运行。

| Model | Planned | Attempted | Valid | Invalid | Missing | Invalid rate / planned | Logical calls / planned | Recorded calls / planned | Input tok. / planned | Output tok. / planned | Total tok. / planned | Total tok. median attempted | Runtime / planned | Runtime median attempted | Root@3 strict | Risk-any strict | Risk-all strict | Compression mean valid-only | Compression n | Profile | Relation prior |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-4o | 12 | 0 | 0 | 0 | 12 | 0.000 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | NA | 0.000 | NA | 0.000 | 0.000 | 0.000 | NA | 0 | minus20 | 0.680 |
| gpt-4o | 12 | 12 | 12 | 0 | 0 | 0.000 | 57.2 | 59.6 | 112251.6 | 68418.4 | 180670.0 | 176320.0 | 570.897 | 574.744 | 0.917 | 1.000 | 0.833 | 0.510 | 12 | nominal | 0.850 |
| gpt-4o | 12 | 0 | 0 | 0 | 12 | 0.000 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | NA | 0.000 | NA | 0.000 | 0.000 | 0.000 | NA | 0 | plus20 | 1.020 |
| gemini-2.5-pro | 12 | 0 | 0 | 0 | 12 | 0.000 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | NA | 0.000 | NA | 0.000 | 0.000 | 0.000 | NA | 0 | minus20 | 0.680 |
| gemini-2.5-pro | 12 | 12 | 12 | 0 | 0 | 0.000 | 51.4 | 53.5 | 115897.2 | 110161.4 | 226058.7 | 221469.5 | 1650.232 | 1413.088 | 0.917 | 1.000 | 0.917 | 0.574 | 12 | nominal | 0.850 |
| gemini-2.5-pro | 12 | 0 | 0 | 0 | 12 | 0.000 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | NA | 0.000 | NA | 0.000 | 0.000 | 0.000 | NA | 0 | plus20 | 1.020 |

逐 case 方向统计见 `prior/paired_direction_table.csv`。只有两边均为有效布尔值的 cell 才进入 improved/tied/worsened；同时保留 strict 12-case rate delta，避免 invalid 被有效样本分母掩盖。

## 预算与可审计性

本线 XHub 公共 ratio 列表价估算累计为 **$36.7701**，2×压力估算为 **$73.5402**，硬上限 **$85.00**。价格快照与 pricing version 保存在 `xhub_pricing_snapshot.json`；账户余额差仍只作共享环境交叉核验。
本线开始后的账户全局余额变化为 **$116.9341**，最新过滤后余额快照为 **$783.9780**。由于同一 key 有并行实验，这一全局差值不能单独归因给本线。

Cost cells：{'attempted': 72, 'valid': 69, 'invalid': 3}。Prior 新付费 cells：{'missing': 48}；nominal 计划复用 24 cells。当前全协议投影：$167.7173（门禁内：False）。

原始结果、call-level usage、append-only budget ledger、冻结 case plans、配置 hash、结果 hash 与 nominal reuse index 均保留在本目录。未运行 Flash/Qwen 附录，也未对结果不利的 case 做替换。


## 执行中断与恢复（必须保留的口径）

Gemini slot 8 SA 首次执行在产生部分调用后被中断，原因未由日志确证；恢复时没有算法状态 checkpoint，因此同一冻结 cell 从头执行。这不是首次尝试成功。主表 valid 表示最终输出可用性，不等于首次成功率；首次尝试分析需将该 cell 记为 interrupted/未获得完整输出。其 token 与 recorded-call 成本包含中断前全部可观测用量及恢复用量；无 usage 返回的潜在在途请求无法精确归账，账户余额另作交叉检查。audit wall-clock 保留恢复执行区间，中断前 API 耗时单列，不能当成一次连续运行。详细记录：`/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/supplemental_pipeline_20260909/recovery/interruption_20260909_170050_586038.json`。

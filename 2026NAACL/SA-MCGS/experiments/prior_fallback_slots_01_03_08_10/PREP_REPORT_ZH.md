# Relation-prior fallback 运行准备报告

准备时间：2026-09-09 10:54 +0800。此阶段未查询 XHub，未构造 LLM client，未发起
任何模型或付费 API 调用。

## 结论

冻结 runner、断点续跑规则、identity/config/prompt/schema/pricing/预算门禁均已落地。
离线 preflight 验证了固定 slots 01/03/08/10、4 个不同 physical source SCC、两个
模型完全一致的 case UID / SCC / injection fingerprint / seed=42，以及 minus20/plus20
相对 nominal 的唯一科学配置差异确实只有 relation-prior profile、multiplier 和
`alphago_mcgs.evidence.relation_prior_weight`。

复审后又补齐了五类 fail-closed 完整性门禁：parent 72 格逐结果校验并绑定唯一 ledger
row；nominal 8 格绑定 parent ledger 的 canonical result hash；fallback resume 绑定同一
invocation 的 start/complete、launch receipt 与结果 hash；authoritative budget 自动
纳入固定的 pre、Stage-1、parent cost 三项上游账本与 fallback own ledger，而非信任
调用者选账本或自报 remaining；每个 model/profile 的完整 scientific config hash 由
frozen protocol 锁定。因此 outcome、usage、身份、配置或账本任一事后改动都会关闭
paid gate。

复审快照中的 paid gate 正确关闭：parent cost 为 50/72（47 valid、3 invalid、22
missing），8 个指定 nominal 中 7 个已完成，Gemini slot 08 尚缺；local fallback 为
0/16 attempted。该计数只记录复审时点，后续当前状态必须以新生成的离线 preflight
为准，不能以本文作为启动依据。

## 离线预算口径

加固后的 snapshot/固定账本门禁尚未在本文中声称完成新的 dry-run；旧 `dry_run.json`
如早于本次加固，只能视为历史材料，不能作为启动证据。此前按冻结 XHub list-rate 与
parent nominal usage 得到的 16 个缺失 cells 保守投影为 40.447020 USD，加 10 USD
closeout reserve 为 50.447020 USD；重新演练时仍须提供真实存在、hash 匹配、时效内且
`context_kind=synthetic` 的人工 snapshot 文件，并让 CLI remaining 与固定账本推导值
一致。synthetic context 无论算术是否通过都不具备正式启动资格。

正式启动必须同时满足：parent cost 72/72；指定 nominal 8/8 parity；所有 source 和
实现及 scientific-config hash 不漂移；exact execution order；时效内且 hash/scope
可验证的 `xhub_balance_snapshot.v1` artifact；`global_authorization_usd=200`。runner
必须自动纳入 pre `$34.634480`、Stage-1 `$47.381175`、动态 parent cost 与 fallback
自身 ledger，从 `$200` 推导 remaining；任意非空 `--upstream-ledger` 必须拒绝。CLI
`global_authorization_remaining_usd` 必须与推导值一致且不高于 snapshot balance，并
足以覆盖完整 missing tail 与不少于 10 USD 的 closeout reserve；最后仍需显式
`--execute-paid-cells`。snapshot 的 `captured_by` 必须精确为
`sa-mcgs-local-cost-fallback-pipeline`。

snapshot TTL 只在每次 invocation 启动时作严格 freshness 门禁。同一 invocation 的
per-cell gate 会继续校验已由 receipt 绑定的 artifact/hash/字段、固定账本、fallback
ledger 与 balance assertion；模型耗时导致 age 超过 TTL 本身不终止该 invocation。
一旦中断后 resume，则属于新 invocation，必须换用 TTL 内的新 snapshot。

## Terminal 与恢复语义

每个 order 在模型调用前写 append-only `cell_start`，结果落盘后写 `cell_complete`。
首次 invalid 与 valid 同样 terminal，继续计入 4-case strict denominator，不自动重跑、
不换 case。正常中断可从连续前缀后恢复；若出现 start 未闭合、result/ledger 不一致或
后序结果越过前序缺口，则 fail closed，要求人工审计而不是隐式重试。对已有结果的
恢复检查包括：start/complete 同一 invocation、唯一且 hash 匹配的 launch receipt、
frozen cell 身份与路径、结果文件 hash、usage、重算 estimated cost、valid/error 和
terminal policy。

## 离线对抗回归

`test_prior_fallback.py` 现覆盖五个复审复现：72 个任意 `{}` JSON 加伪 status/ledger；
nominal outcome bit 篡改；fallback result 与 `cell_complete.result_sha256` 脱钩；伪造
balance reference/高报 self-reported remaining；nominal 与 varied 同时加入额外
`max_depth` 的共同配置漂移。预算回归还断言 pre/Stage-1/parent 三个 role 无需 CLI 即
自动存在、fallback own 自动追加，且任意 caller-selected upstream ledger 被拒绝。
fixture 仅使用临时目录和 mock，不访问网络、不构造 LLM client、不发起付费调用。
完整离线 preflight 测试仍可能刷新 `preflight/*.json` 与 `execution_status.json` 的时间戳。

启动和完整审计文件说明见 `README.md`；历史 `dry_run.json` 不自动代表通过加固后的
门禁。最近一次 preflight 为 `preflight/gate.json`，16-cell 固定顺序为
`preflight/execution_plan.json`，nominal 逐格引用与 hashes 为
`preflight/nominal_reuse_readiness.json`。

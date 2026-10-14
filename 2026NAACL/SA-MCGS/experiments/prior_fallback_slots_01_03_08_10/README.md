# Relation-prior fallback（slots 01/03/08/10）

这是一个与 full-12 prior 完全隔离的冻结 fallback。它只执行
`validation/prior_budget_gate_v1/fallback_subset.json` 中预先声明的 16 个
paid cells，并按原文件的 `execution_order=1..16` 串行运行。4 个 slot 为
01/03/08/10；两个模型各复用 4 个 parent nominal SA-MCGS cells，复用结果只
做引用和 hash 绑定，不复制到本目录，也不重新运行。parent 的 72 个 cost 结果
不能只凭文件数和 status 计数通过：每格都必须通过 frozen identity/config/protocol
校验，并与唯一 parent ledger terminal row 的 result hash、valid/error、usage 和
cost 一致。8 个 nominal 引用沿用同一 ledger 绑定。

有效和无效的首次结果都属于固定 strict denominator，均为 terminal。runner
没有 retry-errors、换 case 或按结果重选子集的入口。若发现顺序跳跃、未闭合
的已启动 attempt、意外结果文件、source/config/prompt/schema/pricing/scientific-
config hash 漂移，会 fail closed。已完成 fallback 结果还必须与同一 invocation
的 `cell_start`/`cell_complete` 和 launch receipt 完整绑定；结果 hash、身份、usage、
重算 cost 或 terminal policy 任一不一致都拒绝恢复。

## 离线检查

以下命令不会构造 LLM client，不查询 XHub，也不会发起模型调用：

```bash
cd /Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS
/opt/homebrew/anaconda3/bin/python experiments/prior_fallback_slots_01_03_08_10/run_prior_fallback.py preflight
```

加固后的 synthetic dry-run 也必须引用一个真实存在、hash 匹配且时效内的人工
snapshot 文件；不能再用任意字符串代替。下面只是命令模板，不表示本报告已经执行过
这次演练。snapshot 内的 `context_kind` 应为 `synthetic`，其 balance、captured-at 和
ledger-derived remaining 必须分别与 CLI assertion 一致：

```bash
cd /Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS
/opt/homebrew/anaconda3/bin/python experiments/prior_fallback_slots_01_03_08_10/run_prior_fallback.py dry-run \
  --global-authorization-usd 200 \
  --global-authorization-remaining-usd "${FALLBACK_LEDGER_DERIVED_REMAINING_USD}" \
  --closeout-reserve-usd 10 \
  --accounting-context-kind synthetic \
  --fresh-xhub-balance-usd "${FALLBACK_SNAPSHOT_BALANCE_USD}" \
  --fresh-balance-captured-at "${FALLBACK_SNAPSHOT_CAPTURED_AT}" \
  --fresh-balance-snapshot /ABSOLUTE/PATH/TO/MANUALLY-CAPTURED-SYNTHETIC-SNAPSHOT.json \
  --fresh-balance-snapshot-sha256 "${FALLBACK_SNAPSHOT_SHA256}"
```

测试：

```bash
cd /Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS
/opt/homebrew/anaconda3/bin/python -m py_compile \
  experiments/prior_fallback_slots_01_03_08_10/run_prior_fallback.py \
  experiments/prior_fallback_slots_01_03_08_10/test_prior_fallback.py
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/anaconda3/bin/python \
  experiments/prior_fallback_slots_01_03_08_10/test_prior_fallback.py -v
```

测试中的篡改样本、ledger 和 balance snapshot 全部写入临时目录，不访问网络或付费
API。`test_full_offline_preflight_never_constructs_llm` 会运行真实离线 preflight，因而
可能刷新本目录 `preflight/*.json` 与 `execution_status.json` 的时间戳。

## 正式启动命令

只有 coordinator 在 parent cost 已达 72/72、8 个 nominal parity 全通过，且用
fresh XHub balance 与所有已完成 ledger 算出本轮剩余授权后，才运行：

```bash
cd /Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS
/opt/homebrew/anaconda3/bin/python experiments/prior_fallback_slots_01_03_08_10/run_prior_fallback.py run \
  --global-authorization-usd 200 \
  --global-authorization-remaining-usd "${FALLBACK_AUTH_REMAINING_USD}" \
  --closeout-reserve-usd 10 \
  --accounting-context-kind authoritative \
  --fresh-xhub-balance-usd "${FALLBACK_FRESH_XHUB_BALANCE_USD}" \
  --fresh-balance-captured-at "${FALLBACK_BALANCE_CAPTURED_AT}" \
  --fresh-balance-snapshot "${FALLBACK_BALANCE_SNAPSHOT_PATH}" \
  --fresh-balance-snapshot-sha256 "${FALLBACK_BALANCE_SNAPSHOT_SHA256}" \
  --execute-paid-cells
```

balance snapshot 必须是独立文件，schema 为 `xhub_balance_snapshot.v1`，包含
`context_kind/provider/source/captured_at/total_available_usd/captured_by/authorization_scope_id`；
其中 `captured_by` 必须精确为 `sa-mcgs-local-cost-fallback-pipeline`。其 hash、时效、
scope、CLI balance 和 captured-at assertion 必须全部一致；任意字符串不能充当
snapshot reference。

TTL 在每次新 invocation 启动时严格执行。invocation 启动并由 receipt 锁定该 snapshot
后，同一 invocation 的 per-cell gate 仍逐次复验 artifact、hash、字段、receipt、账本与
余额 assertion，但不会仅因模型运行耗时令 snapshot age 越过 TTL 而中止；任何 resume
都会创建新 invocation，因此必须重新提供 TTL 内的 fresh snapshot。

上游账本不是 CLI 可选范围。runner 按 frozen protocol 自动且完整地纳入三项：pre
aggregate（冻结支出 `$34.634480`）、Stage-1 aggregate（冻结支出 `$47.381175`）和
动态 parent cost ledger；若 fallback 自身 ledger 存在则自动追加。任何非空
`--upstream-ledger` 都会 fail closed，调用者既不能漏掉固定账本，也不能任意增加账本。
authoritative remaining 只能按
`200 - 34.634480 - 47.381175 - parent cost - fallback own` 推导；CLI 的
`--global-authorization-remaining-usd` 只是必须与推导值一致的 assertion，并且不能高于
可信 snapshot balance。每格启动前都会重新计算整个 missing tail 加 `$10` closeout
reserve。若需人工分段，可增加 `--max-new-cells N`；恢复时已存在的 valid/invalid cells
只有在 result/ledger/receipt 完整性复验后才会跳过。

## 审计产物

- `frozen_fallback_protocol.json`：冻结 scope、runtime、价格、输入、实现 hashes、每个
  model/profile 的完整 experiment/scientific config hashes、balance snapshot TTL 与
  authorization scope，以及 pre/Stage-1/parent 三个固定 accounting sources 的路径、
  hashes、字段和冻结金额。
- `preflight/source_hash_audit.json`：全部 source/implementation hash 验证。
- `preflight/case_and_config_parity.json`：case/seed/prompt/schema/config parity。
- `preflight/execution_plan.json`：唯一允许的 16-cell 顺序及每格 config hash。
- `preflight/nominal_reuse_readiness.json`：8 个 nominal 引用、parent-ledger result hash
  和 parity。
- `preflight/parent_cost_terminal.json`：parent 72/72 状态/磁盘/逐格 ledger-integrity 门禁。
- `preflight/pricing_and_budget_projection.json`：冻结价格、逐模型 reserve 与启动门禁；
  authoritative accounting 的 snapshot、固定 source roles/hashes/spend、fallback own
  ledger 和 derived remaining 会同时进入 preflight/receipt 审计链。
- `dry_run.json`：最近一次历史离线 dry-run receipt；若其 protocol/runner/accounting
  hashes 早于当前加固则不能作为当前门禁通过证据。
- `launch_receipts/*.json`：每次正式 invocation 的 authorization assertion、balance
  snapshot/hash、固定三项 source 加 fallback own 的 hashes、derived remaining、tail
  projection 与 headroom。
- `budget_ledger.jsonl`：append-only invocation/cell start/cell complete 账本；恢复时与
  launch receipt 和结果文件逐字段复验。
- `results/{minus20|plus20}/{model}/results/*.json`：只允许 16 个冻结新结果。

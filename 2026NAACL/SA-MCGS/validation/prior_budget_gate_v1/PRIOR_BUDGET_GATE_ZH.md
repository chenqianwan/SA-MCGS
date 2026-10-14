# Relation-prior sensitivity 预算门禁 v1

本目录只做离线预算与身份审计；没有启动 prior、没有网络调用，也没有修改正在运行的 cost 目录或顶层计划。

## 当前结论

截至 2026-09-09 09:10 +08:00，三个可归因 ledger 合计支出 $92.198360：pre $34.634480、Stage-1 $38.647540、cost $18.916340。按用户授权的全局 $200 计算，当前实际授权余量为 $107.801640。

当前不能启动 prior，原因有四个：cost 仅 41/72、Stage-1 仅 51/68、Gemini nominal SA 仅 1/12、尚未提供启动瞬间的新 XHub 余额快照。预算数字不能覆盖这些门禁。

| 方案 | 新 cases | 新 cells | 当前保守投影 | 加 $10 closeout reserve 的启动阈值 | 当前判断 |
|---|---:|---:|---:|---:|---|
| Full | 12 | 48 | $121.341060 | $131.341060 | 不安全；阈值已高于当前授权余量，且投影仍 provisional |
| Frozen fallback | 4 | 16 | $40.447020 | $50.447020 | 金额暂可容纳，但必须等待全部门禁后重算 |

Full 当前已经不安全：即使暂时忽略尚未完成的 Stage-1/cost 后续支出，$107.801640 也小于 $131.341060。最终决策只能在两个运行任务结束后，使用最终 ledger 重算。

## Full 48 投影方法审计

现有 runner 对每个模型使用“已观察 nominal SA-MCGS 单 cell 的 XHub 列表价最大值 × 1.5”，再乘剩余 cell 数。这个方法适合作为保守 hard gate，但有两个使用前提：

1. 每个模型的 12 个 nominal cost SA cells 必须全部落盘；否则最大值来自不完整样本，只能标记 provisional。
2. 必须比较用户的全局 $200 实际授权余量，而不是继续把 cost+prior 都塞进旧的本线 $85 cap。

当前 GPT nominal 12/12 已齐，最大列表价 $1.6552125/cell，对应 reserve $2.48281875。Gemini 仅 1/12，当前最大值 $1.7153725/cell，对应 provisional reserve $2.57305875。正式公式为：

```text
reserve_m = max($1.25, 1.5 × max_c nominal_cost(m,c))
P_full_guard = 24 × reserve_GPT + 24 × reserve_Gemini
P_fallback_guard = 8 × reserve_GPT + 8 × reserve_Gemini
```

不得用 valid-only 均值、方法效果或 prior outcome 调低投影。Invalid nominal cell 的实际 token 成本仍进入最大值与总 ledger。

## Outcome-blind fallback

从 frozen protocol 的 12 个 selectors 中枚举全部 4-case 组合，要求：四域各 1、四种 template 各 1、scale 为 small/medium/large = 2/1/1。共有三组可行解：`[1,3,8,10]`、`[2,3,8,9]`、`[2,5,7,12]`；按预先声明的 slot tuple 字典序选择第一组 `[1,3,8,10]`。选择过程不读取模型效果、validity 或 prior outcome。

| Slot | Domain | Template | Scale | SCC size |
|---:|---|---|---|---:|
| 1 | Debian | direct_mutex | small | 11 |
| 3 | SEC-Ex21 | temporal_gate | small | 9 |
| 8 | BGB | condition_trigger | large | 25 |
| 10 | CUAD | handoff_invariant | medium | 20 |

Fallback 的严格分母是每个 model × profile 4 cases。Nominal 0.85 只复用这 4×2=8 个 cost cells；minus20/plus20 共需 4×2×2=16 个新付费 cells。不能把 fallback 的 4-case 结果伪装成 full 12-case sensitivity。

执行顺序已完整冻结在 `fallback_subset.json`：同一 case/model 的 minus20 与 plus20 相邻，模型先后按 case 交替。若中断，只能按原顺序断点续跑；invalid 保留、禁止换 case。Full/fallback 的选择必须发生在第一笔 prior 调用前，之后不得按 outcome 升降档。

## 启动判据

必须同时满足：

- cost 72/72 terminal，且两模型各 12 个 nominal SA 结果均通过 case UID、physical SCC、injection fingerprint、budget、concurrency、config hash 与 nominal profile parity；
- Stage-1 terminal，最终 self-ledger 已冻结；
- prior 新付费结果仍为 0，防止看过 outcome 后再选 subset；
- pricing version 仍为 `a42d372ccf0b5dd13ecf71203521f9d2`；
- 启动瞬间重新查询 XHub 余额；
- 为旧 runner 建立仅改变 budget gate/slot scope 的版本化 amendment，并使用独立 fallback 结果目录。当前 `prior` 命令仍绑定 $85 cap 且不支持冻结的 4-slot scope，禁止直接调用。

实际剩余预算公式：

```text
R_actual = 200 - C_pre_final - C_stage1_final - C_cost_final - C_other_paid
```

所有成本取各任务 provider-token ledger；共享账户余额差只交叉核验。决策顺序固定为：

1. 若 `R_actual >= P_full_guard + $10` 且账户余额也满足，运行 Full 48；
2. 否则若 `R_actual >= P_fallback_guard + $10` 且账户余额也满足，运行 frozen fallback 16；
3. 否则不启动。

机器可读快照见 `prior_budget_gate.json`，冻结 subset 与 16-cell 顺序见 `fallback_subset.json`。运行 `build_prior_budget_gate.py --account-available-usd <fresh_balance>` 可在所有上游任务结束后离线重算最终判据；脚本本身不会查询网络或调用模型。

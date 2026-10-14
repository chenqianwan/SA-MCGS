# 本轮补充实验的本地衔接

这是已启动实验的执行衔接，不是定时任务，也不延迟六小时开跑。

**最终状态（2026-09-10）：付费实验与 Cost/Prior 离线统计已完成。** Cost 72/72（69 valid、3 invalid），Prior 16/16 valid；总观测列表价估算 $136.60 / $200。报告及执行限制见 `clustered_closeout/`，专家标签仍待作者提供。下文保留执行历史，不应重新启动已完成的付费入口。

2026-09-09 最后汇总因 one-shot 成功/失败结果的方法名称不同而拒绝；现仅修复离线读取校验，6 项测试与真实完整性门禁通过。原始结果、失败分母和冻结付费 runner 均未改变，未新增 API 调用。`parallel_prior_v1/recovery_required.json` 保留作历史事件记录，已无待恢复付费项。

1. 等待现有 cost 进程自然结束，且状态为 72/72 terminal；不再启动第二份 cost。
2. 使用 prior runner 核验全部 parent 结果、预算账本、8 个 nominal 引用与冻结配置。
3. 每格开始前读取 XHub 真实余额，运行预算 dry-run；通过后按固定顺序补一个 prior cell，直到 16 格完成。有效和无效结果都保留，不整格重试。
4. 生成 cost / prior 报告及按 source SCC 配对的离线 bootstrap 区间。专家标注、裁决及专家指标仍等待作者提供真实标签。

总授权 **US$200**，包含 pre、Stage-1、cost 和 prior；留出 $10 收尾余量。额外用账户余额 $707.078988 作保守交叉检查。任何门禁失败只记录并停止，不能扩大预算或换样本。

Prior 选用预先冻结的 slots **1/3/8/10**，四域各一；共 8 个 nominal 复用、16 个新扰动 cells。完整 48-cell prior 的既有保守预算已高于本轮剩余额度，不能为了跑完整规模超支。不得把四 SCC 的探索性敏感性分析写成 12 SCC。

执行（检查模式不联网、不调用模型）：

```bash
/opt/homebrew/anaconda3/bin/python 2026NAACL/SA-MCGS/experiments/supplemental_pipeline_20260909/continue_pipeline.py
```

已授权的实际衔接入口：

```bash
/opt/homebrew/anaconda3/bin/python 2026NAACL/SA-MCGS/experiments/supplemental_pipeline_20260909/continue_pipeline.py --execute --cost-pid 94022
```

`pipeline.lock` 防止同一编排器重复运行；`execution_status.json` 记录当前阶段，`runner.log` 保留子进程日志，`balance_snapshots/` 仅保存余额及来源，不含密钥。运行期间用 `caffeinate -i` 阻止系统因闲置休眠，不阻止手动休眠或关机；结束后释放。

若电脑关机、进程退出、预算/身份门禁失败，需检查停止原因后再恢复；脚本不会假装已经完成。`paid_experiments_complete_labels_pending` 只表示付费实验完成，不表示专家审计完成。

## 2026-09-09 中断恢复

15:43 确认旧 cost 进程退出，原因未由日志确证。保留 62 个终态（59 valid、3 invalid），只继续 10 个缺项。Gemini slot 8 SA 有 17 条已返回但未入整格账本的调用，观测用量估算 $0.21987125；没有算法状态 checkpoint，因此只将该未完成 cell 从头运行，不能称为首次成功。

恢复入口为 `resume_cost_after_interruption.py --execute`；先保存 `recovery/interruption_*.json` 的原始记录、哈希、余额及 62 个旧结果哈希，再运行同一冻结配置。该 cell 的唯一最终结果与账本会包含中断前及恢复后的全部可观测 API 用量；原始 call logs 不覆盖。首次中断、恢复后有效性须分开解释，audit wall-clock 仅为恢复执行区间；无返回的潜在在途扣费不可假定为零。若在其他 cell 再次中断，入口会拒绝未经审计的部分调用，不静默漏账。

最终 cost 报告和 clustered closeout 的论文汇总必须引用这份恢复记录；不能把最终 valid rate 写成首次成功率。旧 3 个 terminal invalid 不重试，实验样本、算法、prompt、预算和 prior 子集不改。

## Prior 四任务并行（用户要求加速）

新增入口 `parallel_prior.py --execute`，只接管原任务：旧 coordinator 暂停派发，已启动的 serial cell 自然完成并入账后，切至最多 **4 个独立进程**。每进程只跑一个 cell，内部搜索并发仍为 1，60-rollout、窗口、prompt、先验权重、模型与样本不改；冻结 runner 文件不改，已完成 cells 和 nominal 不重跑。

`parallel_prior_v1/amendment.json` 记录操作性变更；`events.jsonl`、`workers/` 的票据、实际时间与调用日志独立保存。中央按冻结前缀顺序提交正式结果/账本，提交顺序不代表实际串行执行。Prior 并行耗时不与串行 nominal 作公平耗时比较。

预算覆盖所有在途预留、已完成未提交费用、剩余尾部和至少 $10 收尾余量。新增调用级预算门禁若截断某项，该项是 `BudgetStop` strict invalid，须单列，不能把它归因为 prior 效应。发生调度/worker 异常时停止新增、等待其他已启动任务落盘并保存恢复清单，不自动重试。

并行前检查：调度、worker、恢复入口合计 53 项零网络测试通过；原 closeout 4 项合成测试通过，兼容 Counter 省略零 missing 字段。

验证：编排器 6 项合成测试（无网络）；与项目根测试合跑共 63 项通过。

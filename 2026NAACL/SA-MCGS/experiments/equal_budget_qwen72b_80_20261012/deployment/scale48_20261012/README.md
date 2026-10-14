# Qwen2.5-72B：48 并发测试

2026-10-12，集群任务 415747，节点 dgx-061。当前实验继续运行：4 个 TP2 副本使用 8 张 H800，每副本 12 个 worker，服务 `max_num_seqs=12`。只运行 Qwen2.5-72B 的 LEA / Full-SCC，SA 复用。冻结协议、提示、模型、预算和科学方法没有改变。

## 观察结果

约 12:32:46–12:37:46 HKT 采样五分钟，排除首分钟后，平均输出吞吐 672.76 token/s；此前 32 worker 窗口为 619.82 token/s，本次高 8.54%。最后一分钟为 617.44 token/s，已接近此前 32 worker 的水平。案例与缓存状态不同，这不是受控基准，也不能据此承诺持续提速 8.54%。

实际同时执行峰值 46；观察结束时 35 执行、13 排队。KV 缓存峰值 99.99%。本次观察未发现服务 error/abort 或 KV 抢占。48 worker 的进程、配置和账本核验通过，465 个旧调用仅结算一次，所有旧响应缓存与账本前缀保留。

维持已授权的 48 worker 实验运行，不进一步提高到 64；本次测试表明长输入及 KV 缓存容量限制了额外并发收益。

## 切换与恢复记录

原 32 worker 在调用结算后逐一暂停，全部冻结前缀通过两次离线回放，provider calls 为 0。32 条 TERM/CONT 均完成，全部旧进程正常按计划退出；退出检查发生 `/proc/.../environ` 的 PermissionError 竞态。原失败记录原样保留。

独立 CPU step 49 再次确认所有结果逐字节不变、旧进程退出、服务端口关闭和 160 个任务锁释放，形成 additive reconciliation 与首次 drained receipt，然后启动新 pipeline。当前服务 step 50、worker step 51；原 checkpoint/controller step 48 已退出。恢复未再次发送信号、未重复科学调用。

实际部署的 reconciliation 脚本 SHA256 为 `e1dc8969deb24e764ade0d6b993684df170959988dad64d90f550d994213b02e`。后续仅增加原脚本集合断言的本地强化版本未部署，已保存在 `local_before_sync_20261012/`。未采用的 boundary assistant 草稿没有部署或发送信号。

## 证据

- `performance_48.json`：原始 31 个采样及指标。
- `post_restart_audit_initial.json` / `post_restart_audit.json`：启动后与观察结束后的只读核验。
- `checkpoint_reconciliation.json` / `drained_receipt.json`：保留原错误的独立退出证明。
- `recovery_launch_receipt.json` / `restart_receipt.json`：来源指纹与重启记录。
- `test_summary.json`：本次测试结论。
- `local_sync_receipt.json`：同步到本地的部署快照指纹。

GPU 利用率的附加读取在无 GPU 权限的 CPU step 中不可用，未用于本次结论；该读取失败不属于模型或科学 worker 错误。全部 8 卡的分配由四个 TP2 服务命令及服务启动检查确认。

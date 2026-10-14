# 单节点并发升级

用户于 2026-09-24 要求提高并发、缩短实验时间。本次把病例 worker 从 2 增至 4，vLLM `max-num-seqs` 从 8 增至 16；仍限定 `dgx-100` 的 1 张 H800、16 CPU、128GB 内存，最长 5 天。

SA 内部并发仍为 8、预算 60、窗口 4；One-shot 输出上限仍为 12000，LEA/SA 为 2048。上下文 131072、BF16、模型 revision、采样设置以及所有科学源码均未改变。原 launcher SHA256 为 `97f6b3909746226a7237046c352944c2785e4b5b2887b79c4986fc361018e01f`。

病例并发和分片数不在原冻结科学协议中，离线核验确认旧、新调用的协议 SHA 完全相同：`88fca6211d93c02fa5d6d54821d33262c9d093a36a20742c7dc23dba3705f953`。结果会分别保留实际病例并发 2 或 4；这属于执行配置变化，不改写旧结果。

## 交接记录

1. 作业 `395039` 以 hold + afterany 原作业 `394926` 的方式先提交。
2. 向原 batch 协调器发送 USR1，触发其自身清理和退出；旧 Slurm 最终记录 FAILED 是本次主动交接的退出码，不代表原实验自然崩溃。
3. 原作业退出后封存 **43 项终态结果、90 个缓存文件、1320 条已返回回复**，校验请求签名、响应对应关系及文件 SHA，之后才释放新作业。
4. `395039` 在发送任何新推理请求前于端口 bind 预检退出，错误为 Address already in use。它保留了全部数据；GPU 空闲检查及旧结果复核已通过。
5. `port_reuse/` 单独保存最小端口预检修正：设置 `SO_REUSEADDR`，与 Uvicorn 的端口绑定方式一致。它仍拒绝真正存在的监听服务，未开启 `SO_REUSEPORT`。本地复现证明 TIME_WAIT 可令旧普通 bind 误判；没有把这项本地复现当作第一次退出原因已获节点实测证实。
6. 相同节点的接续作业 **395047** 于 19:48:41 提交。提交前再次确认两次旧 allocation 均已停止，43 项结果与全部缓存 SHA 完全未变。
7. 19:51:25 核验作业已恢复 `running`：四个 worker 同时处理四个案例，模型服务实际参数为 max-num-seqs=16；结果增至45项，原43项结果和90个缓存的已有字节前缀全部未变。证据见 `migration_runtime_verification.json`。

最新作业回执为 `retry_submission.json`（远端及状态快照中可取），查询使用父目录 `cluster_snapshot.py`。GPU 服务和四个 worker 始终属于同一个作业；没有两个 GPU 作业同时占资源。

## 验证证据

- `runner_compatibility_verification.json`：2→4 协议等价、80 例分片覆盖唯一、终态直接复用及原缓存重放。
- `handoff_snapshot.json`、`cache_verification.json`：停止后结果及请求缓存快照。
- `port_reuse/staging_manifest.json`：修正后的部署文件 SHA。
- `socket_preflight_audit.json`：本地 TIME_WAIT/真实监听区别的复现。
- 每次作业 `runs/<job>/execution_change.json` 记录实际执行配置；最终完成时再次核验切换前 43 项结果的 SHA。

四条最长 One-shot 的输入＋输出预算合计 283156 tokens，小于实际 KV 池 420096 tokens。此前生成吞吐在 Running=2 时约 195 tokens/s、Running=8 时约 609 tokens/s；这是描述性样本，不能作为提升后的实际加速倍数。

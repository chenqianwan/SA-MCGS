# 集群资源申请

- 作业号：**415747**；名称：`chenlong_mcgs_8g_1009`。
- 普通队列 / QoS：`llm`；账户：`hansirui`。
- 资源：单节点、8 GPU、128 CPU、1000G 内存。
- 时限：5 天，从实际开始运行时计时。
- 提交时间：2026-10-09 00:16:42（香港时间）。
- 核验状态：`PENDING`，原因 `Priority`；尚未分配节点。
- 当时预计开始：2026-10-13 21:47:38（香港时间），仅为调度器估计，会变化。
- 远程目录：`/aifs4su/hansirui_3rd/chenlong/mcgs_law/allocations/20261009_8gpu_5d`。

此作业保留申请的资源，等待后续工作负载。`submission.json` 保存提交回执，`verified_status.json` 保存提交后的调度状态。不要重复提交同一申请。

在 `Group3_slogin` 上查询：

```bash
export SLURM_CONF=/cm/shared/apps/slurm/var/etc/slurm/slurm.conf
/cm/shared/apps/slurm/current/bin/squeue -j 415747
```

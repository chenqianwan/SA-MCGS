# Qwen2.5-72B 集群可部署性检查

2026年9月23日实查结论：**硬件、权限、存储和下载网络均具备；当前主要限制是调度排队，模型尚未部署。**

- AI_Council 的 `Group3_slogin` 与 `Group3_dgx-127` 已成功连接。可用 `llm` 分区、`llm` QoS 和 `hansirui` account。
- `dgx-127` 实测 H800、每卡81,559 MiB。`llm` 共11节点、87张配置GPU；`dgx-081` 当时为IDLE、8卡。真正分配到的节点仍须在启动时核验卡型。
- 推荐单节点4卡、原BF16、TP4；Qwen2.5-72B-Instruct约72.7B参数，纯BF16权重约145.4GB。2卡80GB属于紧配置，需要上下文/并发实测；本轮优先不改量化精度。
- 已检查共享模型目录，未发现所需文本模型；发现的Qwen2.5-VL-72B属于另一模型，不能替代。Hugging Face与ModelScope的目标config下载都返回200。
- 共享文件系统约剩3.1T；共享账号配额余量约3910.92GiB，足以规划约145GB权重下载，但这些空间未被预留。
- 现有只读runtime：vLLM 0.20.0+cu129、PyTorch 2.11.0+cu128、Transformers 5.6.2。

## Slurm试算

全部为 `sbatch --test-only`，没有提交或占用GPU。

| GPU/CPU/内存 | 时限 | 当次预计启动（集群本地时间） |
|---|---|---|
| 4/32/256G | 4小时 | 9月24日21:46:44 |
| 4/32/256G | 1小时 | 9月25日08:42:05 |
| 4/32/256G | 2小时 | 9月25日08:42:05 |
| 2/16/192G | 4小时 | 9月25日08:42:05 |

预计时间在不同查询间变化，不能作为预约承诺；缩短时限或减至2卡并未获得更早的估计。节点IDLE不等于该账号可以立即获得分配。

部署草案见 `deploy.sbatch.template`。启动前需下载并固定文本Instruct checkpoint revision、用实际tokenizer验证全部LEA窗口长度，再完成服务与一例LEA核验。集群结果应记录与历史API不同的服务后端、精度和采样默认值；当前付费补跑的冻结账本和配置保持原样。

[Qwen官方模型](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct)；[Qwen官方显存/速度基准](https://qwen.readthedocs.io/en/v2.5/benchmark/speed_benchmark.html)。

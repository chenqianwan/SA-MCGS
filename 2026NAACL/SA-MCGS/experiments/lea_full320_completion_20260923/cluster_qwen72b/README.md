# Qwen2.5-72B-Instruct BF16 单节点部署草案

当前仅有本地模板，未连接集群、下载模型或提交任务。模型路径、不可变 checkpoint revision 和 config SHA256 留有明确占位符；未填实会停止。

主任务本次只读探测确认：`dgx127` 为 H800（81,559 MiB/卡）；这不能代替对候选 `dgx-081` 的型号核验。共享 runtime 为 vLLM `0.20.0+cu129`、PyTorch `2.11.0+cu128`、Transformers `5.6.2`。目前只找到 `Qwen2.5-VL-72B-Instruct`，它不能替代本实验的纯文本 `Qwen2.5-72B-Instruct`。

4 GPU、32 CPU、256 GB、4 小时的 `sbatch --test-only` 已通过，但当次预测启动为 2026-09-24 21:46:44（香港时间）；这是调度估计，并未提交作业。节点显示 idle 不代表可以立即获得分配。随后4卡1/2小时与2卡4小时的试算均预测为9月25日08:42:05，未获得更早启动时间；完整实查结果见 [ASSESSMENT_ZH.md](ASSESSMENT_ZH.md)。

草案基于 `AI_Council/deliverables/cluster-deployment/20260911-4b-service/4b_bf16.sbatch`。只读复用 `/aifs4su/hansirui/vllm-dsv4-venv` 与 CUDA 12.8；日志、缓存、编译产物、IPC 临时文件和运行记录全部放入新的 `/aifs4su/hansirui_3rd/chenlong/q72_20260923/`。

| 项目 | 草案设置 |
|---|---|
| Slurm | partition `llm`、QOS `llm`、account `hansirui` |
| 资源 | 1 节点、4 GPU、32 CPU、256 GB RAM、4 小时 |
| 模型 | `Qwen/Qwen2.5-72B-Instruct`，原始 BF16、TP=4 |
| 服务别名 | `qwen2.5-72b-instruct`，端口 18072 |
| 容量 | context 16,384，最多 8 个并发序列 |
| 请求 | 沿用客户端 `max_tokens=2048`，温度与原 LEA 请求一致 |
| 生成默认值 | `generation-config=vllm`；`top_k=-1`、`top_p=1.0`、`repetition_penalty=1.0` |

提交前需完成以下核验：

1. 确认本次 GPU 型号、单卡显存和调度资源。`dgx-081` 的暂时空闲信息不保证提交时仍有效，因此模板没有固定节点，也不覆盖 Slurm 的 GPU 分配。
2. 找到并验证 **Qwen2.5-72B-Instruct 原始 BF16** checkpoint，填入真实本地路径、不可变 revision、`config.json` SHA256。架构检查不能独自区分 base 与 instruct，需同时确认快照来源。模板不自动下载模型。
3. 用该快照 tokenizer 和实际 chat template 对全部 80 个案例的窗口输入计数，确认 `最大输入 tokens + 2048 ≤ 16384`。目前最大输入约 18,212 UTF-8 bytes，仅能用于初步规划，不能代替 tokenizer 计数。
4. 核对已测共享 vLLM runtime 的 CLI 参数支持，再在专用目录创建 `logs/` 后暂存脚本；Slurm 会在脚本执行前打开日志文件。检查点是只读源，不允许脚本向共享 runtime 或共享模型目录写入。
5. 服务就绪后先核验 `/v1/models` 别名及一例完整 LEA 请求，再单独记录本地端点/运行配置。当前正在运行的 runner、pricing、manifest 都没有修改。

Qwen2.5 此模板没有引入 Qwen3.5 的 reasoning parser、tool parser 或 thinking 开关。启动会记录 checkpoint revision、配置/tokenizer/index 的 SHA256、分片大小与时间、实际 runtime 版本、GPU 清单、完整启动参数及 endpoint；分片记录不等同于全量权重 SHA256。

模型架构字段依据 [Qwen 官方配置](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct/blob/main/config.json)。生成参数仍须以集群实际 vLLM 版本为准；[vLLM 官方服务文档](https://docs.vllm.ai/en/latest/serving/online_serving/)提供参考。

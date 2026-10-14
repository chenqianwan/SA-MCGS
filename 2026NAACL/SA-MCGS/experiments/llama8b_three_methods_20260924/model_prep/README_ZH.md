# Llama 3.1 8B Instruct 权重准备

目标为 Meta 原始 BF16 checkpoint，固定为 `meta-llama/Llama-3.1-8B-Instruct` 的 revision `0e9e39f249a16976918f6564b8830bc894c89659`，不做量化或权重修改。

远端目录：`/aifs4su/hansirui_3rd/chenlong/llama8b_20260924/models/llama-3.1-8b-instruct`。所有新增模型文件、缓存、临时文件、日志和准备脚本位于该任务个人目录，不修改共享模型目录或共享 Python 环境。

## 来源与内容核验

集群已配置的 Hugging Face 凭据未获该仓库 gated 访问授权（官方 config HEAD 返回 `403 GatedRepo`）。没有继续尝试该受限下载路径，没有代用户申请授权、接受条款或修改凭据。

使用独立公开再分发来源 [ModelScope LLM-Research/Meta-Llama-3.1-8B-Instruct](https://modelscope.cn/models/LLM-Research/Meta-Llama-3.1-8B-Instruct)。该来源提供原始 LICENSE 与 USE_POLICY。每个公开下载 URL 固定到来源文件的提交版本，下载请求不发送任何令牌。

内容身份以 Meta 官方固定 revision 的元数据为准，而不是仅依赖镜像名称：

- 四个 safetensors 分片逐个比对 Meta 官方 LFS SHA256。
- 配置、tokenizer、模型索引、说明及许可文件逐个比对 Meta 官方 Git blob SHA1，并保存实际 SHA256。
- 已有共享下载的第 3、4 分片先通过相同 SHA256 核验，再复制到个人目录。已有配置及 tokenizer 仅在内容核验通过后复用。
- 收集官方全部 14 个顶层文件，排除 `original/` 下另一格式的重复权重。

`official_files.json` 保存 Meta 官方元数据；`modelscope_files.json` 保存公开来源元数据；`source_assessment.json` 保存无凭据的来源检查结果。

## 作业范围

准备作业为 Slurm **394900**，于香港时间 2026-09-24 17:24:47 提交，17:24:48 在 `dgx-126` 启动。申请 `debug` 分区、4 CPU、16GB 内存、8 小时，**不申请 GPU**。权重就绪后退出，不承担正式实验。

正式服务与 One-shot、LEA、SA-MCGS 三方法实验由另一个同节点 GPU 作业管理，最长 5 天；本准备脚本不会提交 GPU 作业。

完成后远端生成 `model_download_complete.json`：`state=complete`、`verified=true`，记录模型身份、模型路径、各文件大小/SHA/核验依据与总字节数。正式 GPU 作业须检查该完成证据后加载模型。

## 本地最后核验状态

2026-09-24 17:40:13（香港时间）只读确认 **13/14 文件已核验**。最后第 2 权重分片正在下载，临时文件大小为 **2,675,965,952 / 4,999,802,720 字节**，修改时间距检查仅 1.37 秒。尚无完成 marker，也无 failure marker。此状态仅代表该时点，不应代替运行结束后的最终核验。

五个已核验的小文件已回传到 `../tokenizer_validation/model/`，再次核对 Meta 官方 Git blob 全部通过，证据为 `../tokenizer_validation/retrieval_verification.json`。

协调器随后报告正式 GPU 作业 **394926** 已提交，依赖 `afterok:394900`，最长 `5-00:00:00`。按主任务指示停止持续轮询；不取消或修改下载作业。下载成功退出后由 Slurm 处理依赖启动，正式协调器仍需检查完成 marker 与模型文件身份。

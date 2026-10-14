# Qwen2.5-72B-Instruct 单 H800 实验作业

## 最终运行状态（2026-09-24 16:38 核验）

续跑作业 **394534** 已成功结束：Slurm `COMPLETED`，退出码 `0:0`，续跑耗时 **6:17:57**。协调器在 **16:29:50** 确认 **80/80 complete、strict_failures=0**，随后关闭服务并释放 GPU。四个分片均 finished、incomplete_cases 为空，Slurm stderr 为空。证据：`cluster_live_status.json`。

Qwen 的外部 API 费用为 0；本机另外三个模型合计 240/240，API 账本保守费用 $6.445800866。四模型实验运行合计 320/320；Qwen 原始结果仍在集群共享目录，尚未回传并入本地统一科学汇总。

## 2026-09-24 续跑

原作业 394281 在 04:20 触发协调器时限，保留 **26/80** 完整结果及 **721** 条响应缓存后退出。26 个结果均为 complete，无严格失败；4 个中断案例没有失败状态文件，缓存连续、usage 可审计。4 条尚未结算的旧 reservation 均为 0 美元，原账本保留不改。

续跑作业 **394534** 于 **10:11:51（香港时间）** 提交，**10:11:58 已在 dgx-037 启动**。申请单 GPU、16 CPU、128 GB、**12 小时**，Slurm 截止 **22:11:58**，协调器预留 5 分钟退出。**10:16:49 已确认四分片正常续跑**：合计跳过原 26 个完整结果，4 个中断案例分别从原第 48、3、21、2 次调用继续，已返回新的响应，Slurm stderr 为空。远端证据：`resume_started_evidence_20260924.json`。提交回执：`resume_submission_receipt_20260924.txt`；实时状态由 `cluster_snapshot.py` 读取最新续跑作业并保存至 `cluster_live_status.json`。

运行入口为 `run_awq_lea_resume.sbatch` → `run_awq_lea_resume.py`。原 152 个部署文件、科学 protocol、pricing、launcher、模型与服务参数逐一验证未改；续跑跳过已完成案例，对未完成案例按原请求签名回放缓存，然后接着调用本地服务。未启用 provider failure 自动重试。仍使用 `results/lea_qwen80/`，本次日志位于 `runs/394534/`、`logs/lea-394534.out` 和 `logs/lea-394534.err`。

2026-09-24 00:25:02（香港时间）已提交 Slurm 作业 **394281**，00:25:03 已在 **dgx-037** 启动；实际核验为单张 **NVIDIA H800**（85,017,493,504 字节显存）。00:30:03 状态为 `smoke`：服务健康检查已通过，实验脚本已收到首个推理请求的 HTTP 200，正在完成固定案例 20。实际回执见 `gpu_submission_receipt.txt`，最新快照见 `cluster_live_status.json`。早先 `--test-only` 的预计时间已被本次实际启动状态取代。

模型准备作业 **394276** 于 00:17:36 成功完成（耗时 4 分 29 秒），21 个文件共 41,607,438,677 字节，其中 11 个权重分片均通过官方 LFS SHA256 核验。已完成作业的依赖引用被 Slurm 拒绝后，确认没有重复 GPU 作业，核验完成标记并直接提交；失败记录保留在 `gpu_failed_dependency_submission_receipt.txt`。

## 运行配置

| 项目 | 已提交配置 |
|---|---|
| Checkpoint | `Qwen/Qwen2.5-72B-Instruct-AWQ` |
| 不可变 revision | `698703eae6604af048a3d2f509995dc302088217` |
| GPU / TP | 单张 H800 80 GB，TP=1；实际分配后检查硬件 |
| CPU / 内存 / 时限 | 16 CPU、128 GB、4 小时 |
| 调度 | `llm` partition、`llm` QOS、`hansirui` account |
| 推理环境 | 只读共享 `/aifs4su/hansirui/vllm-dsv4-venv`，vLLM `0.20.0+cu129` |
| 节点内接口 | `http://127.0.0.1:18072/v1`，模型名 `qwen2.5-72b-instruct` |
| 推理参数 | AWQ、FP16 activation、16384 context、最多 4 个并发序列 |
| 科学参数 | 原始窗口、提示词、温度和 2048 输出上限保持一致 |
| 外部 API 费用 | 0；集群资源计费不属于 API 费用 |

`run_awq_lea.sbatch` 调用 `run_awq_lea.py`：校验权重和 GPU → 核验 80 例身份及提示词 → tokenizer 预检 → 启动 localhost vLLM → 固定案例 20 → 四分片完成 80 例 → 关闭本次服务并释放 GPU。失败与超时保留检查点；严格实验失败为终态，不通过自动重跑选择结果。

模型与实验脚本由同一个 Slurm 作业管理，Mac 断开不影响执行。所有输出位于个人目录：

- 部署根目录：`/aifs4su/hansirui_3rd/chenlong/q72awq_20260924`
- 实验结果：`results/lea_qwen80/`
- 作业状态和子进程日志：`runs/394281/`
- Slurm 日志：`logs/lea-394281.out`、`logs/lea-394281.err`

集群端环境与 tokenizer 预检通过：1184 个捕获请求的最大输入为 5308 tokens，加 2048 输出上限为 7356，低于 16384，溢出 0。独立 CPU 预检作业为 **394282**，未申请 GPU、未调用模型。

## 数据与后续汇总

152 个部署文件（含 150 个实验包文件）上传后逐个通过 SHA256 检查。原始 80 个 SA 源结果保留原字节；57 个代码文件与原仓库一致。完整图以 gzip JSON 迁移，并重新计算验证 dataset revision。本地离线验证 80 例稳定身份、1344 个窗口、1184 个无网络捕获请求均一致，证据见 `package/local_validation_final/portable_preflight.json`。

根据用户向 XHub 工作人员核实的信息，历史路由也是此 AWQ 版本。模型展示名保持原样；内部 provenance 保留真实 checkpoint、revision 与后端信息。

集群结果使用独立的零 API 费率配置，不改变正在运行的主实验 $50 预算及冻结文件。结果回传后须在汇总层显式核验集群 protocol、provenance 与 case identity；不能将它们直接混入要求原 API 路由的主结果目录。

# Qwen80 LEA 同节点运行包

将本包的 `repo/` 解压到 `/aifs4su/hansirui_3rd/chenlong/q72awq_20260924/repo/`。本包不含模型权重、凭据、`.env` 或其他模型的实验输出。

使用已安装的只读运行环境 `/aifs4su/hansirui/vllm-dsv4-venv/bin/python3`。所需依赖为 pydantic 2、networkx 3、openai 2、anthropic、aiohttp、loguru；python-dotenv为可选兼容依赖。tokenize检查另外使用本地transformers/tokenizers。该环境已由主任务核验具备这些依赖，不需修改共享环境。

入口为 `cluster_launcher.py`，输出目录由协调器指定，例如 `.../results/lea_qwen80/`。它原样复用冻结的 `run_completion.py` 与科学代码，只在进程内替换四个数据加载函数，从完整gzip JSON图快照恢复原图。加载时清除缓存revision，再以真实内容重算并核验全部图指纹。80个原始SA来源文件保留原字节及SHA，源路径在运行时重定位。

操作顺序：

1. `--mode preflight --output-dir OUTPUT`：离线核验80个稳定案例、原始来源、1344个固定窗口及1184个实际初始请求的逐字节prompt一致性；不调用模型。
2. `--mode tokenize --output-dir OUTPUT --tokenizer-path /aifs4su/hansirui_3rd/chenlong/q72awq_20260924/model --max-model-len 16384 --max-output-tokens 2048`：使用本地checkpoint的真实chat template逐请求计算上下文，超限立即失败；不调用模型。
3. 服务就绪后，`--mode smoke --output-dir OUTPUT --base-url http://127.0.0.1:18072/v1 --smoke-case-order 20`。
4. smoke核验通过后，用4个进程运行 `--mode run --output-dir OUTPUT --base-url http://127.0.0.1:18072/v1 --shard-count 4 --shard-index 0` 至 `3`。每个分片内部串行；smoke的结果与缓存直接复用。

preflight生成 `case_plan.json`、`portable_case_plan.json` 和 `portable_preflight.json`。tokenize生成 `tokenization_report.json`。结果在 `results/<case_id>__lea.json`；保留原case ID，便于回传与主清单按稳定身份对齐。smoke要求唯一固定case为complete；run对缺失/provider暂停非零退出，严格无效保留终态供后续审计。协调器最终核验80份结果和完成状态。

服务地址严格限定为同节点 `http://127.0.0.1:<port>/v1`，模型alias为 `qwen2.5-72b-instruct`。独立pricing的输入和输出单价均为0；外部API消费授权为0。原runner要求正预算上限，因此其内部保留50美元形式上限，所有本地调用以0美元计账；GPU资源费用由Slurm作业管理，不属于API额度。主机上的XHub账本、冻结输入和正在执行的DeepSeek任务均不修改。

实际checkpoint为 `Qwen/Qwen2.5-72B-Instruct-AWQ`，revision `698703eae6604af048a3d2f509995dc302088217`。用户已向XHub确认历史endpoint也是AWQ；原始确认记录位于 `portable_data/historical_provider_confirmation.json`。`deployment_provenance.json`记录此次自部署实际配置；论文显示模型名保持Qwen2.5-72B-Instruct。

本包不自动启动vLLM、不自动提交作业、不下载文件。由外部同节点协调器负责checkpoint校验、模型服务生命周期、smoke验证和分片进程管理。

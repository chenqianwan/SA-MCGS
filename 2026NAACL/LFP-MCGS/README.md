# 2026 NAACL：LFP-MCGS

本目录用于 Paper 2：继承 SA-MCGS 的**真实循环文档图、局部窗口读取和 PUCT/MCGS 搜索骨架**，把原来的局部风险记忆替换为 source-grounded symbolic KB 与 online least-fixed-point closure。论文研究的是：通用 LLM 能否用更多 test-time compute，在长 SCC 中逐步找齐、组合并验证分散证据。

## 文档索引

- [`LFP_MCGS_RESEARCH_PLAN_V2.md`](./LFP_MCGS_RESEARCH_PLAN_V2.md)：**唯一当前执行版**；方法、受控注入、baseline、实验和 Go/No-Go 均以此为准。
- [`LFP_MCGS_RESEARCH_PLAN_ZH.md`](./LFP_MCGS_RESEARCH_PLAN_ZH.md)：旧初稿的归档入口；不再保留第二套口径。
- [`LFP_MCGS_LITERATURE_REVIEW.md`](./LFP_MCGS_LITERATURE_REVIEW.md)：方法新颖性与 topology-controlled SCC intervention 的文献依据。
- [`LFP_MCGS_DATASET_ANALYSIS.md`](./LFP_MCGS_DATASET_ANALYSIS.md)：当前数据设计：真实 SCC 载体、最小注入、matched family 与 exact oracle。
- [`LFP_MCGS_DATASET_AUDIT.md`](./LFP_MCGS_DATASET_AUDIT.md)：现有数据实测、可复用资产和数据资格 Gate；历史数字均标为诊断证据。
- [`algorithm_figures/`](./algorithm_figures/)：早期算法视觉 walkthrough；当前 no-leak rollout、状态合并与停止语义以 V2 为准。
- [`plan_v2_figures/`](./plan_v2_figures/)：V2 的 claim-evidence、算法边界、generality 与 baseline/ablation 图及可复现生成脚本。

## 当前范围

- 载体：从 SA-MCGS 数据管线提取的真实 document SCC；节点、边和原始窗口冻结。
- 干预：只在现有窗口中做最小、领域化的 `seed / bridge / witness` 注入，不凭空生成整张图。
- 规模：SCC 节点数 `3 / 5 / 7 / 9 / 12 / 16 / 20`，同时单独记录真正承载证明的窗口数。
- 语义：finite、function-free、positive Horn 的 least-Herbrand / least-fixed-point；LFP 只增加结论，不承担“撤回已经成立事实”的强推翻。
- 方法：局部 LLM 读取提出 fact/rule，验证后写入 committed KB；增量 LFP 产生 `Δclosure / provenance / proof obligations`，再反馈下一轮 PUCT。
- 输出：答案、query-relevant closure、source-linked proof certificate 与完整成本账本。

## 当前调研结论

- 未检索到完整同构系统；新意只写成这条闭环的耦合：`cyclic local-window MCGS → source-validated partial Horn program → online SCC-local LFP → closure/provenance feedback → decision-equivalent state sharing`。
- 核心机制集采用 topology-controlled SCC intervention。每个正例与 `decoy / broken-or-inactive / clean / matched-DAG` 配对，并由独立 LFP 引擎复核 closure、逐轮 provenance 和 leave-one-source-out 必要性。
- 主 baseline 是同一通用 LLM 在 matched test-time compute 下的 Direct/CoT、Self-Consistency/Best-of-N 与强 search/retrieval agent；TreeMCTS 只用于关闭 exact state merging 的内部消融。
- 人工注入只能证明受控机制，不能证明自然分布。真实无注入 SCC 与外域数据单独做 external validation，不能与受控集混成一个总分。
- ProofWriter 等既有审计数字和 V1–V3 结果继续保留，但只作为 symbolic safety / 历史诊断，不再定义论文主线。

## 分支

项目分支：`2026NAACL`

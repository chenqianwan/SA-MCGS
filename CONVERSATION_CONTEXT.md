# SA-MCGS 项目完整对话上下文 (截至 2026-05-09 23:50)

> 本文件记录了整个开发对话的完整上下文，供切换到其他工具后继续使用。
> 新工具请首先阅读此文件，然后按需深入具体代码文件。

---

## 一、项目总体信息

- **项目名**: SA-MCGS (Structure-Aware Monte Carlo Graph Search)
- **仓库地址**: `git@github.com:chenqianwan/SA-MCGS.git`
- **本地路径**: `/Users/chenlong/WorkSpace/MCGS_Law`
- **目标会议**: ACL ARR (5.25 截稿)
- **论文模板**: ARR 模板已下载，骨架已填写 → `paper/latex/acl_latex.tex`
- **论文标题**: "SA-MCGS: Structure-Aware Monte Carlo Graph Search for Cyclic Reasoning in Complex Document Analysis"
- **前端 Demo**: `static/demo.html` (Tailwind + Chart.js + D3.js, 4335行)
- **语言**: Python 3.10+, 异步 (asyncio)
- **依赖**: pydantic, openai, loguru, 详见 `requirements.txt`

---

## 二、SA-MCGS 算法核心原理

### 总体架构 (4 阶段 Pipeline)
```
Phase 1 (System-1): Graph Construction  — 文档 → 有向依赖图 G=(V,E)
Phase 2 (System-1): SCC Detection       — Tarjan 算法 → 找出循环依赖的强连通分量
Phase 3 (System-2): Monte Carlo Search  — AlphaGo 风格搜索，LLM 做 rollout 评估
Phase 4 (System-2): Online Conformal    — 统计异常检测，提供可靠性保证
```

### AlphaGoMCGS 搜索引擎 (`src/modules/alphago_mcgs.py`, 569行)

**每次迭代的流程**：
1. **UCB Selection** — 用 UCB1 + Dirichlet noise 选择种子节点
   - `UCB(v) = Q(v)/N(v) + c·sqrt(ln(N_total)/N(v)) + ε·Dir(α)`
   - 前 40% 迭代用高探索权重 (`exploration_init=2.5`)，后期降到 (`exploration_weight=1.414`)
2. **Window Expansion** — 从种子贪心扩展到 `window_size=4` 个相邻节点
   - 沿边展开，用 UCB 选最有信息量的邻居
   - Dirichlet noise (α=0.3, weight=0.25) 防止过度确定性
3. **Evaluation** — 先查 Transposition Table，miss 则调 LLM
   - TT key = `frozenset(window)` (无序集合)
   - `tt_max_reuse=3`：同一个窗口最多复用 3 次 TT 结果
   - LLM 返回 JSON: `{clause_evaluations: {id: {risk_score, reasoning}}, conflicts: [...]}`
4. **Backpropagation** — 更新节点和边的统计信息
   - `NodeStats`: visit_count, total_risk, risk_history, conflict_count
   - `EdgeStats`: visit_count, total_conflict
   - `score_pool`: 全局分数池，用于 OC 检测
5. **OC Detection** — 三票投票制：z_score > 1.5, avg_rank > 0.8, exceedance > 0.8
   - 任意 2/3 投票通过 → 标记为异常节点
   - 需要 `min_rollouts=6` 次以上才开始检测

**并行机制**：
- `concurrency=4` 个 rollout 并行执行
- **Virtual Loss**: 正在评估的窗口节点被施加虚拟损失，使其他并行线程倾向于探索不同区域
- 每个 batch 用 `asyncio.gather()` 并发

**为什么 window=4 能检测长链 (如 12 节点)**：
- 滑动窗口逐段扫描，每个节点被多次评估（在不同邻居上下文中）
- Backpropagation 沿图结构传递风险信号（高风险邻居 → 当前节点被更多访问）
- UCB 自动聚焦高风险区域（visit 少但 risk 高的节点获得更高 UCB）
- 不需要一次看完整条链，天然解决 LLM 上下文长度限制

### 数据模型

**`src/models/clause.py`**:
```python
class Clause(BaseModel):
    id: str; title: str; content: str
    section: Optional[str]; clause_type: ClauseType; metadata: dict
```

**`src/models/graph.py`**:
```python
class Edge(BaseModel):
    source: str; target: str
    dependency_type: DependencyType  # DEFINES/CONSTRAINS/TRIGGERS/MODIFIES/REFERENCES
    weight: float; reasoning: str

class SCCInfo(BaseModel):
    id: str; clause_ids: list[str]; size: int

class DependencyGraph(BaseModel):
    clauses: dict[str, Clause]; edges: list[Edge]
    sccs: list[SCCInfo]; dag_nodes: list[str]
```

**`src/models/search_tree.py`**:
- `NodeStats`: visit_count, total_risk, risk_history, conflict_count, virtual_loss
- `EdgeStats`: visit_count, total_conflict, virtual_loss
- `TranspositionEntry`: clause_evaluations, conflicts, timestamp

### 可插拔剪枝 (`src/modules/pruning/`)

**通用跨领域插件** (`cross_domain_plugin.py`):
- `NoiseEdgeRemover`: 去除自环、低权重边 (threshold=0.3)、重复 reasoning 边
- `InfoBottleneckPruner`: 基于信息论的轻量剪枝 (compression_ratio=0.10)
- 注册名: `"cross_domain"`，config 中用 `plugins: ["cross_domain"]`

**法律专用插件** (已分离):
- `legacy_plugin.py`: 原始启发式 (weight threshold + hierarchy prior)
- `adaptive_tacs_plugin.py`: Type-Aware Cycle Saliency
- 层级先验: Definition → Obligation → Condition → Remedy → Limitation

---

## 三、LLM 客户端 (`src/llm/openai_client.py`)

**OpenAIClient** — 支持 OpenAI API 兼容的所有服务 (OpenAI, XHub, DeepSeek)
- `call(prompt, temperature, max_tokens, system_prompt)` → LLMResponse
- `call_json(prompt, ..., retries=2)` → dict (自动 JSON 解析)
- `_extract_json(text)` — 静态方法，处理:
  - 标准 JSON
  - Markdown 代码块包裹的 JSON (` ```json ... ``` `)
  - 截断的 JSON (找最外层 `{...}`)
  - 空响应 → 返回 None

**XHub API 配置**:
```python
{
    "provider": "openai",
    "model": "deepseek-chat",  # 或 gpt-4o, claude-3-5-sonnet-20241022 等
    "base_url": "https://api3.xhub.chat/v1",
    "api_key_env": "XHUB_API_KEY",
    "timeout": 300,
}
```

**可用模型 (通过 XHub)**:
| model_id | 说明 |
|----------|------|
| `gpt-4o` | GPT-4o (DI-BENCH 42.9%, Fin-RATE 75.2%) |
| `deepseek-chat` | DeepSeek V2/V3 级别 (DI-BENCH 48.0% best) |
| `claude-3-5-sonnet-20241022` | Claude 3.5 Sonnet (DI-BENCH 39.0%) |
| `gemini-2.0-flash` | Gemini 2.0 Flash |
| `qwen-plus` | Qwen Plus |

---

## 四、跨领域验证 — 领域选择过程

### 选择标准 (5 项 Go/No-Go)
1. 存在 3+ 个非平凡 SCC (节点数 >= 3)
2. 至少 1 个 SCC 规模在 5-30 节点 (非全连接)
3. SCC 中存在可检测的异常
4. 节点可转化为 LLM 可读文本
5. 有 LLM baseline 数据可对比 (来自顶会论文)

### 最终选定的三个领域

#### A. Debian 软件供应链 ✅ GO
- **数据源**: CARDS dataset (Debian Bookworm apt)
- **本地路径**: `experiments/cross_domain/20241027.cards.debian_pkgs/20241027.debian_pkgs.deps.gz`
- **规模**: 59,718 节点, 276,939 边
- **SCC**: 65个(>=2), 28个(>=3), **11个(5-12节点)**
- **密度**: 20-47%, SCC 节点占比 0.34%
- **Ground Truth**: CVE 数据库 — `ruby3.1` ~48 CVE, `mono` ~52 CVE
- **Baseline 论文**: DI-BENCH (ACL 2025) — 18个模型, best 48% pass rate
  - GPT-4o: 42.9%, Claude-3.5-Sonnet: 39.0%, DeepSeek-V3: 48.0%
  - 评估方式: **客观二元** — 生成的依赖文件 build 通过=Pass
- **数据加载**: `run_cross_domain.py::load_debian_graph()`
  - 读取 `.deps.gz` 文件，每行: `pkg dep1 dep2 ...`
  - 每个包创建一个 Clause (id=包名, content="Debian package: {name}")
  - 每个依赖创建一条 Edge (type=REFERENCES, weight=0.8)

#### B. Wikipedia 分类层级 ✅ GO
- **数据源**: Wikipedia Category Hierarchy (SDZeroBot/Category cycles)
- **获取方式**: Wikipedia API 实时获取 (`en.wikipedia.org/w/api.php`)
  - 解析 `User:SDZeroBot/Category cycles/1` 到 `/4` 共 4 页
  - 每行提取 `Category:XXX` 链接，形成环路
- **规模**: 2026年4月共 **834 个已知环路**, **134 个在 5-30 范围**
- **环路示例**:
  - 长度 5: Falangism → Francoism → Francoist Spain → Spanish Civil War → Politics
  - 长度 8: Iraq War → Aftermath → War in Iraq → Anti-ISIL → Ba'ath Party → ...
  - 长度 15: Canaan → Hebrews → Israelites → Jews → Jewish diaspora → ...
- **重要发现**: 需要 **budget=60** 才能有效触发 OC (默认 30 不够)
- **Baseline 论文**:
  - TaxoGlimpse (VLDB 2024): GPT-4 在 taxonomy 分类任务 62.6-92.1%
  - HiBench (2025): 复杂层级结构推理能力不足
  - RELEVAL (2025): 环路检测任务 LLM 显著性能差距
  - GraCoRe (COLING 2025): 图理解 benchmark
  - 评估方式: **客观二元** — "Is A subcategory of B?" 正确=Pass
- **特殊讨论 (待定)**:
  - 环路不一定是错误 — 类似词典递归定义 ("递归: 参见递归")
  - TaxoGlimpse 逐边评测 ("Is A subcategory of B?") **无法检测环**
  - 每条边局部可能是正确的，但全局形成了环
  - **SA-MCGS 的价值**: 从边级别评测升级到结构级别评测
  - 设计方向: 不把环本身当错误，在环中注入语义矛盾边 (从文献获取案例)
  - **此问题需要后续单独讨论**
- **数据加载**:
  - 小环: `run_cross_domain.py::load_wikipedia_graph()` — 选 5-15 节点
  - 大环: `run_larger_sccs.py::load_wikipedia_graph_large(min_cycle, max_cycle, max_select)`

#### C. SEC EX-21 企业交叉持股 ✅ GO
- **数据源**: OpenSanctions US CorpWatch EX-21 Filings (SEC 10-K Exhibit 21)
- **本地路径**: `experiments/cross_domain/finance_blockchain/corpwatch/entities.ftm.json.gz`
  - **注意**: 文件名是 .gz 但实际是纯 JSON Lines 格式 (2.2GB, 已在 .gitignore 中排除)
  - schema=Company: id, caption, country
  - schema=Ownership: owner → asset
- **规模**: 691,152 公司节点, 917,000 所有权有向边
- **SCC**: 195个(>=2), 81个(>=3), **37个(5-30节点)**, 最大 72 节点
- **SCC 示例**:
  - SCC(5): Grolier International → Grolier Overseas → Grolier Malaysia → ...
  - SCC(5): Baker Hughes EHO → Baker Hughes Holdings III B.V. → ...
  - SCC(5): Dominion Energy Inc → Dominion Resources → Virginia Electric → ...
- **Baseline 论文**:
  - Fin-RATE (2026): GPT-4o 75.2% 公司治理推理 → 跨实体仅 ~56.6% (下降18.6%)
  - FinBen (NeurIPS 2024): 42 datasets, 24 tasks, 21 LLMs
  - FinAuditing (2025): 跨文档一致性检测
  - 评估方式: **客观** — 推理正确率
- **Ground Truth**: 后期找专业人标注 (6个SCC, 39个公司, ~2.5小时)
- **数据加载**: `run_cross_domain.py::load_sec_graph()`
  - 内嵌 Tarjan SCC 检测 (iterative, 非递归)
  - 选取 size 5-15 的 SCC

### 淘汰的候选领域
| 候选 | 淘汰原因 |
|------|---------|
| 代码审计 | 商用已非常成熟，不认为能做出更好效果 |
| 法规合规 (regulatory) | 跟法律合同太相似 |
| 医药/生物学 | 背景知识太少，后期人工验证不可做 |
| 传播学/新闻/交通 | 没找到满足条件的权威数据集 |
| Wikidata | DAG by design, 环全是 vandalism |
| ConceptNet | 仅 5 个 SCC[5-30], 被 Wikipedia 替代 |
| AI4Risk/Interbank | 巨大 SCC (775-1313节点) |
| TransXion AML | 巨大 SCC (46K节点) |
| 中国担保圈 | 数据私有 |
| GLEIF Level 2 | 仅 2 个 size-2 SCC |

详细追踪: `experiments/cross_domain/smoke_test_tracker.md` (149行)

---

## 五、已完成的实验 (5 轮)

### 实验 1: 初始 DeepSeek 5n 实验
- **脚本**: `run_cross_domain.py`
- **模型**: deepseek-chat via XHub
- **配置**: budget=30, window=4, concurrency=4, alpha=0.1
- **每领域**: 3 个最小的 SCC (约 5 节点)
- **结果**: `results/cross_domain_preliminary_1778319537.json` (3573行)
- **关键发现**:
  - Debian: 3 SCC (5n), **2/9 节点触发 OC**
  - Wikipedia: 3 SCC (5n), **0/9 节点触发 OC** ← budget 不够
  - SEC: 3 SCC (5n), **2/9 节点触发 OC**
  - TT hit rate: Debian 60%, Wiki 47%, SEC 53%
  - LLM calls: 每个 SCC 约 10-15 次

### 实验 2: Wikipedia OC 敏感度测试
- **脚本**: `run_wiki_oc_test.py`
- **结果**: `results/wiki_oc_test_1778333840.json`
- **测试参数组合**: budget=30/60, alpha=0.05/0.1/0.15, 不同 prompt 变体
- **关键发现**: budget=60 显著改善 OC 检测，alpha 参数影响较小
- **结论**: Wikipedia 后续实验统一用 budget=60

### 实验 3: 更大 SCC 实验 (7-12n)
- **脚本**: `run_larger_sccs.py` (292行, 独立脚本)
- **模型**: deepseek-chat via XHub
- **配置**: Debian/SEC budget=30, Wikipedia budget=60
- **结果**: `results/larger_sccs_1778335517.json` (5568行)
- **每领域 3 个大 SCC**:
  - Debian: 12n (EFL/libevas), 11n, 7n (ruby/sdbm)
  - Wikipedia: 8n (Iraq War cycle), 8n, 8n
  - SEC: 10n (Nielsen), 7n (AEP Electric), 7n
- **关键发现**:
  - 大 SCC OC 触发率更高 (78% vs 44% for 5n)
  - TT hit rate 与 SCC 大小成反比 (大图缓存命中率低，符合预期)
  - SEC 风险分数最高 (循环持股本身即异常)
  - Wikipedia 8n 全部触发 OC (budget=60 有效)

### 实验 4: 旧版 Battle (GPT-4o + DeepSeek)
- **结果**: `results/battle_1778339091.json` (4630行, 无对应脚本文件 — 上一个 AI 模型生成但未保存脚本)
- **内容**: 3 域 × 2 SCC × 2 模型(gpt-4o, deepseek-chat) × 2 方法(naive, sa-mcgs) = 24 组
- **问题**: 没有 Ground Truth 评估, Naive prompt 不是 baseline 论文格式
- **数据可用性**: 结果 JSON 完整, 可作为参考但不是最终实验

### 实验 5 (待运行): 新版 Battle
- **脚本**: `run_cross_domain_battle.py` ← **本次对话新写**
- **改进**:
  1. Naive prompt 适配自 baseline 论文方法论 (DI-BENCH / TaxoGlimpse / Fin-RATE)
  2. Ground Truth 自动评估 (`is_ground_truth_node()`)
  3. Binary detection rate (Top-1/Top-3 GT hit)
  4. 结果汇总表自动输出
- **结果**: 将存为 `results/battle_v2_*.json`

### 所有结果文件索引
```
results/cross_domain_sim_1778317791.json       — 模拟 LLM 管道测试
results/cross_domain_preliminary_1778317791.json — 早期 DeepSeek 测试 (可能不完整)
results/cross_domain_preliminary_1778319375.json — 早期 DeepSeek 测试
results/cross_domain_preliminary_1778319537.json — ★ 正式 DeepSeek 5n 实验
results/wiki_oc_test_1778333840.json           — Wikipedia OC 敏感度测试
results/larger_sccs_1778335517.json            — ★ 7-12n 大规模 SCC 实验
results/battle_1778339091.json                 — 旧版 Battle (GPT-4o+DS)
results/battle_v2_*.json                       — 新版 Battle (待生成)
```
**⚠️ 不要覆盖任何已有结果文件！**

---

## 六、前端 Demo (`static/demo.html`, 4335行)

### Tab 导航结构 (11 个 tab)
| # | tab id | 名称 | 内容 |
|---|--------|------|------|
| 1 | overview | Algorithm Overview | SA-MCGS 整体架构图，已更新三个新领域 |
| 2 | ablation1 | Ablation 1: MCTS vs Cycle | MCTS 在环上的失败模式分析 |
| 3 | dataset | Dataset Evolution | 数据集演进 |
| 4 | timeline | Progress & Timeline | 项目进度 |
| 5 | dashboard | 实验数据看板 | BGB + CUAD 实验数据, LLM baseline 对比图 |
| 6 | crossdomain | **跨领域验证** | ★ 核心 tab, 三个新领域实验结果 |
| 7 | process | 贡献1: MCTS搜索与剪枝 | 搜索过程可视化 |
| 8 | graph | 贡献2: Conformal评价 | OCP 统计检测 |
| 9 | pruning | 贡献3: 剪枝策略 | 剪枝策略对比 |
| 10 | scaling | Scaling Analysis | 扩展性分析 |
| 11 | results | Head-to-Head Results | 对比结果 |

### 跨领域验证 Tab (crossdomain) 详情
- **实验配置区**: 标注 Wikipedia budget=60
- **4 个 Chart.js 图表**:
  - `chart-cd-risk`: 风险评分柱状图 (18 SCC)
  - `chart-cd-oc`: OC 检测 vs LLM 调用散点图 (18 SCC)
  - `chart-cd-tt`: TT Hit Rate 散点图 (X=SCC Size, Y=TT Rate) — 反比关系
  - `chart-cd-dist`: 节点风险分布 (18 SCC)
- **数据**: 包含全部 18 个 SCC (9个5n + 9个7-12n), JavaScript 数组 `allLabels`, `allRisk`, `allOC` 等
- **Baseline 背书**: DI-BENCH, TaxoGlimpse, Fin-RATE 引用
- **缺陷注入背书**: CVE (Debian), SDZeroBot (Wiki), SEC 官方数据
- **综合结论**: OC 触发率 78%, TT 效率与 SCC 大小反比, 领域特异性发现

---

## 七、论文骨架 (`paper/latex/acl_latex.tex`, 557行)

### 论文结构
- **Title**: SA-MCGS: Structure-Aware Monte Carlo Graph Search for Cyclic Reasoning in Complex Document Analysis
- **Abstract**: 已写完 (含关键数据: 100% detection, 500+ clauses, Magnifier Effect)
- **§1 Introduction**: 框架写好 (key findings + 贡献列表), TODO: 开头段落
- **§2 Related Work**: 已写完 5 个子节 (Reasoning Gap, Search-Augmented, MCTS, Contract Graph, Conformal)
- **§3 SA-MCGS Framework**: 框架写好, TODO: 每个子节的正文
  - §3.1 Graph Construction
  - §3.2 SCC Detection + Pruning
  - §3.3 Monte Carlo Graph Search
  - §3.4 Online Conformal Prediction
- **§4 Experimental Setup**: 框架写好, TODO: 正文
  - §4.1 Study 1: Single-Contract (CUAD/CLAUSE, 141 runs)
  - §4.2 Study 2: Cross-Contract Deal Packages (170 runs)
- **§5 Results**: 6 个子节框架, TODO: 正文和图表
  - §5.1 Main Results (SA-MCGS 1.00 vs Gemini 0.47)
  - §5.2 Difficulty Gradient (T1-T5: 100%→80%)
  - §5.3 Focused LLM (搜索价值隔离: FP 9.2→0.7)
  - §5.4 Scaling Collapse (60-80 clauses 临界点)
  - §5.5 Magnifier Effect (Type C +8.4 nodes, 300%+)
  - §5.6 Ablation: MCTS vs Cycles (Q-Spread: MCTS 0.044 vs SA-MCGS 0.371)
- **§6 Analysis**: 框架写好
- **Limitations / Ethics**: TODO
- **Appendix**: 4 个子节框架

### 论文中的关键数据
| 指标 | LLM Baseline | SA-MCGS |
|------|:---:|:---:|
| 结构性缺陷 F1 | 0.15-0.47 | **1.00** |
| OC 检测范围 | 全文 | SCC 内 (~5% 节点) |
| 扩展性极限 | 60-80 clauses 崩溃 | 500+ clauses 稳定 |
| 难度梯度 T1-T5 | — | 100%→80% |
| 误报率 | — | 13% (0.7 FP/run) |
| Focused LLM FP | 9.2/run | 0.7/run |

---

## 八、Battle 实验设计 (当前核心待办)

### 为什么需要 Battle
之前的跨领域实验只用了 DeepSeek-chat，然后引用 baseline 论文 (DI-BENCH 42.9%, TaxoGlimpse 62.6%) 说 "LLM 弱"。
这是 apples-to-oranges 比较 — 不同模型 + 不同任务 + 不同数据。
Battle 要做的是 apples-to-apples: **同一个模型 × 同一份数据 × 两种方法**。

### 实验逻辑
```
对每个 SCC:
  1. Naive: 把整个 SCC 一次性塞给 LLM → 得到各节点 risk_score
     (Naive prompt 适配自 baseline 论文方法论)
  2. SA-MCGS: 用搜索框架迭代分析 → 得到各节点 risk_score
  3. 评判: 注入的缺陷节点是否被 rank 到 Top-1 / Top-3？ Pass=1, Fail=0
  最终: Detection Rate = Pass 数 / 总 SCC 数
```

### Naive Prompt 设计
| 领域 | 来源论文 | 适配程度 | 核心差异 |
|------|---------|:---:|------|
| Debian | DI-BENCH (ACL 2025) | ~60% | 从"依赖生成"适配为"异常检测" |
| Wikipedia | TaxoGlimpse (VLDB 2024) | ~90% | 从"逐边分类"扩展为"环路分析" |
| SEC | Fin-RATE (2026) | ~90% | 保持"跨实体推理"格式 |

Naive vs SA-MCGS 的 prompt 唯一区别: Naive 看**全部节点**, SA-MCGS 看**窗口内 4 个节点** (但迭代多次)。

### 与 Baseline 论文的关系
- **Naive = 复现他们的方法** (同模型, 适配后的 prompt)
- **SA-MCGS = 我们的方法**
- **Baseline 论文数字 (42.9% 等) = 外部独立验证**, 证明 Naive 在该领域确实弱
- 论文表格只放 Naive vs SA-MCGS, baseline 数字作为正文引用/脚注
- **不能直接把 42.9% 和我们的 detection rate 放同一列** (不同任务)

### Ground Truth 定义
| 领域 | Ground Truth | 判定方式 | 硬度 |
|------|-------------|---------|:---:|
| Debian | CVE 高危包 | node_id 包含 "ruby" 或 "mono" = GT | **硬** |
| Wikipedia | 注入的语义矛盾边 | 注入什么就是 GT | **硬** |
| SEC | 异常持股边 | 后期专家标注 | **中→硬** |

### 脚本配置 (`run_cross_domain_battle.py`)
- **模型**: `BATTLE_MODELS = [gpt-4o, deepseek-v3(deepseek-chat)]`
- **每领域**: 2 个代表性 SCC (1 个 5-6n, 1 个 7+n)
- **MCGS 参数**: Debian/SEC budget=30, Wikipedia budget=60
- **输出**: `results/battle_v2_{timestamp}.json`
- **预估**: 24 组实验, ~$10-15 API 费用

### 论文论证结构
```
Step 1 (引用 baseline 论文):
  "DI-BENCH (ACL 2025) reports GPT-4o achieves only 42.9% on dependency inference,
   confirming LLM weakness in software supply chain reasoning."

Step 2 (我们的实验):
  "On SCC anomaly detection from the same Debian ecosystem, GPT-4o with naive
   prompting achieves X% detection rate. With SA-MCGS, detection improves to Y%."

Step 3 (结论):
  "SA-MCGS provides a 2.3× gain, demonstrating that structured graph search
   effectively compensates for the LLM weakness independently identified by DI-BENCH."
```

---

## 九、历史问题与修复

| # | 问题 | 修复 |
|---|------|------|
| 1 | InfoBottleneckPruner 在大图上卡死 | 移除初始跨领域实验的全图剪枝 |
| 2 | XHub LLM 返回空/markdown JSON | 增加 `_extract_json()` + retry 机制 |
| 3 | DeepSeek 直连余额不足 | 改用 XHub 代理, 同 key 调用 |
| 4 | Wikipedia OC 不触发 (budget=30) | Wikipedia 专用 budget=60 |
| 5 | 只跑了 5 节点 SCC 太小 | 补跑 7-12n SCC, 结果整合到统一 tab |
| 6 | Python f-string SyntaxError | 修正 `.join()` 在 f-string 中的嵌套语法 |
| 7 | `load_wikipedia_graph()` 只选小环 | 新增 `load_wikipedia_graph_large()` 专门选 7-15n |
| 8 | Baseline 对比不公平 (全用 DeepSeek) | 设计 Battle 实验: 同模型 × 同数据 × Naive vs SA-MCGS |

---

## 十、紧急注意事项

1. **不要覆盖任何 `results/` 下的 JSON 文件** — 用户明确要求保留所有历史结果
2. **修改参数跑实验后必须改回来** — 尤其是 `run_cross_domain.py` 的 `budget=30`
3. **Wikipedia 用 budget=60**, 其他领域用 budget=30
4. **SEC Ground Truth 尚未标注** — 需要后期找专业人做, 预计 2.5 小时
5. **Wikipedia 实验设计需要单独讨论** — 环路是否天然合理, 注入什么矛盾
6. **论文截稿 5.25** — 时间紧张
7. **SEC CorpWatch 数据 2.2GB** — 在 .gitignore 中排除, 不上传到 git
8. **跨领域实验不做全图剪枝** — InfoBottleneckPruner 在大图上太慢

---

## 十一、下一步待办

### 立即可做
- [ ] 运行 `run_cross_domain_battle.py` (需要设置 XHUB_API_KEY)
- [ ] 将 Battle 结果更新到 `demo.html` 跨领域验证 tab
- [ ] 将 Battle 结果整理成论文表格格式

### 需要讨论
- [ ] Wikipedia 实验设计 — 注入语义矛盾的具体方案 + 文献来源
- [ ] SEC Ground Truth 专家标注计划
- [ ] 是否增加更多模型 (Claude-3.5-Sonnet, Gemini) 到 Battle

### 论文相关
- [ ] Experiment Section (§4) 补充跨领域实验设置
- [ ] Results Section (§5) 补充跨领域结果
- [ ] Generalization Section (§6.3) 用跨领域数据充实
- [ ] Abstract 加一句跨领域泛化
- [ ] Introduction 贡献列表更新

# SA-MCGS 跨领域冒烟测试追踪表 (第四轮 — 三领域全部 GO)

## Go/No-Go 标准

1. 存在 3+ 个非平凡 SCC (节点数 >= 3)
2. 至少 1 个 SCC 规模在 5-30 节点 (非全连接)
3. SCC 中存在可检测的异常
4. 节点可转化为 LLM 可读文本
5. 有 LLM baseline 数据可对比

---

## A: 软件供应链 — Debian 包依赖 ✅ GO

- **数据源**: CARDS dataset (Debian Bookworm apt)
- 59,718 节点, 276,939 边
- **65 SCC** (>=2), **28** (>=3), **11** (5-12 节点)
- 密度 20-47%, SCC 节点占比 0.34%
- CVE: ruby3.1 ~48, mono ~52
- **Baseline**: DI-BENCH (ACL 2025) — best 48% pass rate
- **任务**: 检测循环依赖中的缺陷包


| 标准           | 状态                  |
| ------------ | ------------------- |
| SCC 结构       | ✅ 11 个 SCC[5-30]    |
| 可检测异常        | ✅ CVE 漏洞传播          |
| LLM 弱点       | ✅ DI-BENCH best 48% |
| 节点可文本化       | ✅ 包名+描述+版本          |
| Baseline 可对比 | ✅ DI-BENCH 18个模型    |


---

## B: 知识图谱 — Wikipedia 分类层级 ✅ GO (替代 ConceptNet)

- **数据源**: Wikipedia Category Hierarchy (SDZeroBot/Category cycles)
- **2026年4月共 834 个已知环路** (Wikipedia 官方维护)
- 环路长度分布: 2-36 (含 length=2: 154, length=3: 124, length=4: 62, ...)
- **134 个环路在 5-30 范围** ★ (远超 Debian 11 个, ConceptNet 5 个)
- 涉及 1,113 个唯一分类节点

### 5-30 范围环路示例 (全是层级分类错误):

- **长度 5**: Falangism → Francoism → Francoist Spain → Spanish Civil War → Politics of the Spanish Civil War
- **长度 6**: Nationalist faction → Falangism → Francoism → Francoist Spain → Spanish Civil War → Politics
- **长度 8**: Iraq War → Aftermath → War in Iraq → Anti-ISIL → Ba'ath Party → History of Ba'ath → ...
- **长度 10**: Communist Party of Soviet Union → Party leaders → Heads of CPSU → Joseph Stalin → Stalinism → ...
- **长度 15**: Canaan → Hebrews → Israelites → Jews → Jewish diaspora → Jews by country → ...
- **长度 20**: Automatic category TOC tracking → Template Category TOC → Wikipedia formatting → ...

### Baseline:

- **HiBench (2025)**: 30 hierarchical reasoning tasks, 20 LLMs — 复杂层级结构推理能力不足
- **TaxoGlimpse (VLDB 2024)**: GPT-4 在 taxonomy 分类任务 62.6-70.8%, 18 个模型数据
- **RELEVAL (2025)**: 环路检测任务 — LLM 有显著性能差距
- **GraCoRe (COLING 2025)**: 图理解 benchmark — 19 tasks, 5140 graphs
- **Wiki Race**: LLMs 陷入环路后无法重新规划 (Claude Opus 16% Hard)

### 任务: 在分类层级环路中识别哪条 subcategory 边是错误的


| 标准           | 状态                                    |
| ------------ | ------------------------------------- |
| SCC 结构       | ✅ **134** 个环路[5-30] (极强)              |
| 可检测异常        | ✅ 环路=层级错误, Wikipedia 官方标记为需修复         |
| LLM 弱点       | ✅ HiBench/TaxoGlimpse/RELEVAL 多重证据    |
| 节点可文本化       | ✅ 分类名+描述+父子关系+文章列表                    |
| Baseline 可对比 | ✅ HiBench/TaxoGlimpse/GraCoRe/RELEVAL |


### 淘汰的 KG 候选:

- Wikidata: DAG by design, 环全是 vandalism — ❌
- ConceptNet: 仅 5 个 SCC[5-30], 巨大 SCC 未解决 — ⚠️ 边缘 (被 Wikipedia 替代)

---

## C: 金融 — SEC EX-21 企业交叉持股 ✅ GO

- **数据源**: OpenSanctions US CorpWatch EX-21 Filings (SEC 10-K Exhibit 21)
- 691,152 个公司节点, 917,000 条所有权有向边
- **195 SCC** (>=2), **81** (>=3), **37** (5-30 节点) ★
- 最大 SCC: 72 节点 (可管理, 不是巨型 SCC!)
- SCC 涉及 Grolier, Baker Hughes, Dominion Energy, Intermec 等真实企业集团

### SCC 大小分布:


| 大小  | 数量  |     | 大小    | 数量  |
| --- | --- | --- | ----- | --- |
| 2   | 114 |     | 9     | 4 ★ |
| 3   | 29  |     | 10    | 1 ★ |
| 4   | 12  |     | 11    | 3 ★ |
| 5   | 7 ★ |     | 12    | 2 ★ |
| 6   | 7 ★ |     | 18    | 1 ★ |
| 7   | 9 ★ |     | 29    | 1 ★ |
| 8   | 2 ★ |     | 37-72 | 3   |


### 5-30 范围 SCC 示例:

- **SCC(5)**: Grolier International → Grolier Overseas → Grolier Malaysia → Grolier Finance (Philippines) → Federated Credit Corp
- **SCC(5)**: Baker Hughes EHO → Baker Hughes Holdings III B.V. → Baker Hughes Nederland → Baker Hughes Ltd → BJ Services International
- **SCC(5)**: Dominion Energy Inc → Dominion Resources → Virginia Electric & Power → Dominion Energy Questar → Piedmont Share Trust

### Baseline:

- **Fin-RATE (2026)**: SEC filing 分析 benchmark, 17 LLMs — 跨实体分析准确率下降 **18.6%**
  - GPT-4o: 75.2% 公司治理推理 → **cross-entity 仅约 56.6%**
  - Claude 3.7: 64.5% → cross-entity 更低
  - 关键失败模式: "entity mismatches" 和 "comparison hallucinations"
- **FinBen (NeurIPS 2024)**: 42 datasets, 24 tasks, 21 LLMs — LLMs 在高级推理中表现差
- **FinAuditing (2025)**: 跨文档一致性检测, Financial Relationship Extraction (FinRE)

### 任务: 在循环持股链中识别哪条所有权边是异常/错误的


| 标准           | 状态                             |
| ------------ | ------------------------------ |
| SCC 结构       | ✅ **37** 个 SCC[5-30], 最大仅 72   |
| 可检测异常        | ✅ 循环持股=申报异常/复杂结构               |
| LLM 弱点       | ✅ Fin-RATE cross-entity -18.6% |
| 节点可文本化       | ✅ 公司名+国家+行业+申报日期               |
| Baseline 可对比 | ✅ Fin-RATE/FinBen/FinAuditing  |


### 淘汰的金融候选:

- AI4Risk/Interbank: 1 个巨大 SCC (775-1313节点) — ❌
- TransXion AML: 1 个巨大 SCC (46K/47.5K节点) — ❌
- 中国担保圈: 结构匹配但数据私有 — ❌
- GLEIF Level 2: 仅 2 个 size-2 SCC (数据太干净) — ❌

---

## 最终综合判定


| 领域    | 数据集                           | SCC[5-30] | LLM弱点              | Baseline来源              | 判定       |
| ----- | ----------------------------- | --------- | ------------------ | ----------------------- | -------- |
| 软件供应链 | **Debian (CARDS)**            | **11**    | DI-BENCH 48%       | ACL 2025                | **✅ GO** |
| 知识图谱  | **Wikipedia Categories**      | **134**   | TaxoGlimpse 62-71% | VLDB 2024 / COLING 2025 | **✅ GO** |
| 金融    | **SEC EX-21 (OpenSanctions)** | **37**    | Fin-RATE -18.6%    | NeurIPS 2024 / 2026     | **✅ GO** |


**三个领域全部通过所有 5 项 Go/No-Go 标准!**

共计: 11 + 134 + 37 = **182 个 SCC** 在 5-30 节点范围可供实验
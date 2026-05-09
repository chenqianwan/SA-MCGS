# SA-MCGS Battle 实验上下文 (2026-05-09)

## 项目概述

SA-MCGS (Structure-Aware Monte Carlo Graph Search) 是一个利用 LLM 进行图结构异常检测的框架。
核心思想：在 SCC (强连通分量/循环依赖) 中，通过 MCTS 风格的迭代搜索 + 在线保角预测 (OCP)
来识别风险节点，而不是把整个图一次性扔给 LLM。

## 当前任务：Battle 实验

### 目标
在相同的 SCC 数据上，用相同的 LLM 模型，对比：
1. **Naive Prompting**（整个 SCC 一次性输入 LLM，baseline 论文的方法）
2. **SA-MCGS**（迭代搜索框架）

### 为什么需要这个实验
之前的实验只用了 DeepSeek-chat 跑 SA-MCGS，然后引用 baseline 论文的数字说"LLM 在这个领域弱"。
但这是 apples-to-oranges 比较。现在需要 apples-to-apples：同一个模型，同一份数据，两种方法。

### 实验脚本
`experiments/cross_domain/run_cross_domain_battle.py` — 已完成编写，待运行。

### 运行方式
```bash
cd /Users/chenlong/WorkSpace/MCGS_Law
export XHUB_API_KEY="your-key"
python experiments/cross_domain/run_cross_domain_battle.py
```

### 实验矩阵
- **模型**: GPT-4o, DeepSeek-V3 (通过 XHub API)
- **领域**: Debian, Wikipedia, SEC EX-21
- **每个领域**: 2 个代表性 SCC (1 个 5-6n, 1 个 7+n)
- **每个 SCC**: Naive × 2 models + SA-MCGS × 2 models
- **总计**: 3 domains × 2 SCCs × 2 models × 2 methods = 24 组实验
- **预估费用**: ~$10-15 (Naive 很便宜，SA-MCGS 每个 SCC 约 15-20 次 LLM call)

### 评估指标
1. **Score Spread** (区分度): max_score - min_score，越大越好
2. **Top-1 GT Hit**: 最高分节点是否是已知缺陷节点
3. **Top-3 GT Hit**: Top-3 节点中是否包含已知缺陷节点
4. **OC Detection**: SA-MCGS 独有的统计异常检测 (Naive 无此能力)
5. **Detection Rate**: 在有 Ground Truth 的 SCC 中，命中率 = hits/total

---

## Ground Truth

### Debian (硬 — CVE 数据库)
- `ruby3.1`: ~48 个 CVE (NVD/CVE database)
- `mono` / `libmono*`: ~52 个 CVE
- 判定：SCC 中含 ruby 或 mono 开头的包 → Ground Truth 缺陷节点
- 脚本中已实现 `is_ground_truth_node()` 函数

### Wikipedia (待补充)
- 当前 Ground Truth 为空 `{}`
- 设计方向：注入语义矛盾边（从文献获取案例）
- 环路本身是自然存在的（类似词典递归定义），不等于错误
- TaxoGlimpse 的边级别评测无法处理环结构 — 这是 SA-MCGS 的方法论贡献点
- **后续需要单独讨论 Wikipedia 的实验设计**

### SEC EX-21 (后期专家标注)
- 当前 Ground Truth 为空 `{}`
- 计划：找金融/法律专业人做人工标注
- 6 个 SCC，39 个公司，约 45 条持股边
- 工作量估算：1 位专家 ~2.5 小时，双标 ~6 小时
- 标注前可用 Score Spread 作为中间指标

---

## 三个 Baseline 论文的评估方式

### DI-BENCH (ACL 2025) — Debian
- **任务**: 给代码仓库，推断 requirements.txt
- **指标**: Pass Rate (build 通过 = 1)
- **性质**: 完全客观，机器判定
- **关键数据**: GPT-4o = 42.9%, Claude-3.5-Sonnet = 39.0%, DeepSeek-V3 = 48.0% (best)
- **我们的 Naive Prompt**: 适配自 DI-BENCH 方法论（完整依赖上下文 → 一次性分析）

### TaxoGlimpse (VLDB 2024) — Wikipedia
- **任务**: "Is A a subcategory of B?" 二元分类
- **指标**: Accuracy
- **性质**: 客观，有权威标准答案
- **关键数据**: GPT-4 = 62.6-92.1%
- **重要发现**: 逐边评测无法检测环 — SA-MCGS 的结构感知是核心优势

### Fin-RATE (2026) — SEC
- **任务**: SEC filing 跨实体推理
- **指标**: Accuracy
- **关键数据**: GPT-4o 跨实体推理下降 18.6% (75.2% → ~56.6%)

---

## 论文论证结构

```
Step 1 (引用): Baseline 论文独立证明 LLM 在该领域弱
  → DI-BENCH 42.9%, TaxoGlimpse 62.6%, Fin-RATE -18.6%

Step 2 (我们的实验): 在同源数据的 SCC 上
  → Naive GPT-4o 检测率 = X%  (预期跟 baseline 量级一致)
  → SA-MCGS GPT-4o 检测率 = Y%  (预期显著提升)

Step 3 (结论): SA-MCGS 结构化搜索有效克服了 LLM 的领域弱点
```

论文表格格式:
```
| Method          | Model       | Debian | Wiki | SEC |
| Naive Prompting | GPT-4o      | X%     | —    | —   |
| SA-MCGS         | GPT-4o      | Y%     | —    | —   |
| Naive Prompting | DeepSeek-V3 | X%     | —    | —   |
| SA-MCGS         | DeepSeek-V3 | Y%     | —    | —   |
```

Baseline 论文数字 (42.9% 等) 作为脚注/正文引用，不直接进入表中。

---

## 文件结构

### 核心代码
- `src/modules/alphago_mcgs.py` — SA-MCGS 搜索引擎
- `src/llm/openai_client.py` — LLM 客户端（支持 XHub 代理多模型）
- `src/modules/tarjan.py` — Tarjan SCC 检测
- `src/modules/pruning/cross_domain_plugin.py` — 跨领域通用剪枝插件

### 实验脚本
- `experiments/cross_domain/run_cross_domain.py` — 初始 DeepSeek 实验 (budget=30)
- `experiments/cross_domain/run_larger_sccs.py` — 更大 SCC 实验 (7-12n)
- `experiments/cross_domain/run_wiki_oc_test.py` — Wikipedia OC 敏感度测试
- `experiments/cross_domain/run_cross_domain_battle.py` — **Battle 脚本 (新)** ← 当前任务

### 实验结果 (不要覆盖!)
- `results/cross_domain_preliminary_1778319537.json` — 初始 DeepSeek 5n 实验
- `results/larger_sccs_1778335517.json` — DeepSeek 7-12n 实验
- `results/wiki_oc_test_1778333840.json` — Wikipedia OC 测试
- `results/battle_1778339091.json` — 旧版 Battle (GPT-4o + DeepSeek, 无 GT 评估)
- `results/battle_v2_*.json` — 新版 Battle (带 GT 评估) ← 待生成

### 数据文件
- `experiments/cross_domain/20241027.cards.debian_pkgs/` — Debian CARDS 数据
- `experiments/cross_domain/finance_blockchain/corpwatch/` — SEC EX-21 数据
- Wikipedia 数据通过 API 实时获取 (SDZeroBot/Category cycles)

### 前端
- `static/demo.html` — 包含"跨领域验证" tab，展示已有实验结果

---

## XHub API 配置

- **Base URL**: `https://api3.xhub.chat/v1`
- **API Key 环境变量**: `XHUB_API_KEY`
- **可用模型** (model_id):
  - `gpt-4o` — GPT-4o
  - `deepseek-chat` — DeepSeek (V2/V3 级别)
  - `claude-3-5-sonnet-20241022` — Claude 3.5 Sonnet
  - `gemini-2.0-flash` — Gemini 2.0 Flash
  - `qwen-plus` — Qwen Plus

### SA-MCGS 参数
- `budget`: 30 (默认) / 60 (Wikipedia)
- `window_size`: 4
- `concurrency`: 4
- `ucb_exploration_weight`: 1.414
- `temperature`: 0.4
- `tt_max_reuse`: 3

---

## 待办事项

### 立即可做
1. ✅ 运行 `run_cross_domain_battle.py` — Naive vs SA-MCGS Battle
2. 将 Battle 结果更新到 `demo.html` 跨领域验证 tab

### 后续讨论
3. Wikipedia 实验设计 — 需要单独讨论：
   - 环路是否天然合理（词典递归解释类比）
   - 注入什么样的语义矛盾
   - TaxoGlimpse 边级别评测 vs SA-MCGS 结构级别评测
4. SEC Ground Truth 专家标注
5. 论文 Experiment Section 撰写

### 技术注意事项
- **不要覆盖之前的 DeepSeek 结果** — 新 Battle 用 `battle_v2_` 前缀
- **如果修改了参数跑实验，跑完后必须改回来**
- Wikipedia 用 budget=60，其他用 budget=30
- `run_cross_domain.py` 中的参数必须保持 budget=30 不变

---

## 关键设计决策回顾

1. **为什么用 Naive 而不是直接引用 baseline 数字？**
   - baseline 论文的任务和我们的不完全一样（如 DI-BENCH 测的是依赖生成，我们测的是异常检测）
   - Naive 实验 = "他们的方法在我们的数据上的表现"
   - 两者结合：Naive 结果 + baseline 引用 = 双重证据

2. **为什么选 GPT-4o + DeepSeek-V3？**
   - GPT-4o: DI-BENCH (42.9%) 和 Fin-RATE 的核心测试模型
   - DeepSeek-V3: DI-BENCH 最强模型 (48.0%)
   - 两个模型覆盖三篇 baseline 论文的主要模型

3. **评估指标为什么用 binary detection 而不是连续分数？**
   - 跟 baseline 论文的 pass rate / accuracy 对齐
   - 简单、直观、可解释
   - "注入的缺陷点是否被划入风险子图" = 最硬的指标

# P0 里程碑计划

> 基于 MASTER (NAACL 2025) 对标分析，确定的最高优先级任务。  
> 完成这两个里程碑后，SA-MCGS 将具备顶级会议投稿所需的全部实验数据。

---

## 总览

| 里程碑 | 目标 | 核心产出 | 状态 |
|--------|------|---------|------|
| **M1** | [统一架构与管线集成](./M1_unified_architecture.md) | 统一的 MCGS 引擎策略模式、配置驱动的实验 Pipeline | 🔴 未开始 |
| **M2** | [权威 Evaluation (Benchmark & Baselines)](./M2_integrated_evaluation.md) | 基于 CLAUSE 的对标实验、F1 碾压数据、Spatial Precision 报告 | 🟡 数据就绪 |

**总计**: 约 10-14 天

---

## 🔥 重大进展 (2026-04-27)

### 已完成的关键突破

1. **CUAD 图构建 Pipeline 完成**: 复制 `graph-grpo-lex` (斯坦福) 的 V4 Prompt，完成 30 份 CUAD 合同图提取。
2. **隐性引用增强**: Medium 模式达到 SCC ratio ≈ 4.4%，完美对标 BGB (德国民法典) 的 ~5% 拓扑特性。
3. **CLAUSE Benchmark 闭环**: 成功集成 EACL 2026 最新 Benchmark，实现了“投毒数据 + 专家标注 + 权威 Baseline”三合一。
4. **降维打击验证**: 冒烟测试显示 67% 的 CLAUSE 投毒目标命中 SCC 节点，SA-MCGS 在结构性缺陷检测上具备天然优势。

---

## 依赖关系

```
M1: 统一架构 (Pipeline 稳定性保证)
 └──→ M2: 综合评估 (数据、检测、对标一站式完成)
```

---

## 完成后的产出物

1. **统一的 MCGS 引擎**: 支持 Classic / Conformal / CVaR / AlphaGo 四种策略。
2. **CLAUSE Battle 报告**: SA-MCGS vs. GPT-4o / Gemini-2.5 / LLaMA-3.3 的全维度 F1 对比。
3. **Spatial Specificity 验证**: 证明检测子图会随缺陷位置移动，支撑“结构化推理”的核心论点。
4. **论文就绪表格**: LaTeX 格式的 Main Results 表格。


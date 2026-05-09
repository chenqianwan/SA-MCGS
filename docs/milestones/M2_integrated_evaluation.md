# Milestone 2: 权威评价体系 (Integrated Evaluation)

> **目标**: 基于 EACL 2026 的 CLAUSE Benchmark 构建全流程评估，实现对主流 LLM 的“降维打击”对比。  
> **预计工时**: 5-7 天  
> **优先级**: P0 — 论文的核心说服力  
> **状态**: 🟡 数据就绪，待运行实验  
> **前置依赖**: M1 (统一架构) 基本完成

---

## 1. 现状与优势

通过引入 **CLAUSE (EACL 2026 Findings)**，我们将 Evaluation 提升到了顶会水平：

| 维度 | 传统方法 | SA-MCGS + CLAUSE |
|------|---------|-----------------|
| **数据源** | 内部 QuantLaw (BGB) 数据 | **CUAD (公开权威)** |
| **投毒质量** | 简单规则替换 | **ASU 法学院专家验证的投毒 (98.6% 准确率)** |
| **对比对象** | 零星的 Direct LLM | **GPT-4o, Gemini-2.5, LLaMA-3.3 (全系列 Baseline)** |
| **评估指标** | 自定义 Delta 指标 | **标准 F1 / Precision / Recall / ROUGE** |

---

## 2. 评估矩阵设计 (Battle Matrix)

我们将 SA-MCGS 放入 CLAUSE 的三级评估框架中进行 Battle：

### 2.1 Task 1: 缺陷检出率 (F1 对标)
直接对比 CLAUSE 论文中各模型的 F1 成绩。
- **目标**: 在 **Structural Flaws** 和 **Omission** 类别上显著超越现有 SOTA (Gemini-2.5)。
- **核心论点**: 图结构能捕捉到跨条款的逻辑断裂，这是 Flat-text LLM 的盲区。

### 2.2 Task 2: 缺陷定位精度 (Spatial Specificity)
利用 CLAUSE 的 `location` 和 `contradicted_location` 标注。
- **指标**: 我们的搜索子图与 Ground Truth 标注的重合度。
- **对比**: 对标论文中的 `location_alignment` (ROUGE 分数)。

### 2.3 Task 3: 效率与成本
- **指标**: 定位一个缺陷所需的 Token 数 vs. 直接读全文的 Token 数。

---

## 3. 实施步骤

### Step 1: 原始/投毒图库构建 (Day 1-2)
- [ ] 批量处理 30+ 份 CUAD 核心合同。
- [ ] 对每一份合同：构建 Original Graph 和 10+ 份对应的 Perturbed Graphs (从 CLAUSE 提取)。
- [ ] 确保 `grpo-lex` Pipeline 在投毒文本上运行稳定。

### Step 2: 运行 SA-MCGS 检索 (Day 2-4)
- [ ] 在统一架构 (M1) 下，运行全量搜索。
- [ ] 自动提取高风险子图路径。
- [ ] 记录检测到的 `Section Number`。

### Step 3: 数据对标与分析 (Day 4-5)
- [ ] 编写 `clause_battle_analyzer.py`。
- [ ] 计算 SA-MCGS 的 F1 Score。
- [ ] 绘制对比图表：SA-MCGS vs. GPT-4o-mini vs. Gemini-2.5。

---

## 4. 预期对比结果 (Mockup)

| 方法 | Structural Flaws (F1) | Omission (F1) | 法律引用准确率 |
|-----|----------------------|---------------|--------------|
| GPT-4o-mini | 37.9% | 41.8% | < 10% |
| Gemini-2.5 | 64.2% | 63.8% | 13.8% |
| **SA-MCGS (Ours)** | **Expected 80%+** | **Expected 75%+** | **N/A (图定位)** |

---

## 5. 验收标准

- [ ] 完成 30 份合同的全量投毒对比测试。
- [ ] 生成全自动化的评估报告。
- [ ] 证明 SA-MCGS 在 **Structural Flaws** 类别上是全班第一。
- [ ] 导出 LaTeX 格式的 Main Results 表格。

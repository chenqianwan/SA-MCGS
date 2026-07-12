# Baseline Fairness / Schema Burden：升级版图推理 baseline 方案

## 目标

Reviewer 的核心担心不是“Naive 太弱”这么简单，而是：

1. 当前 Naive 需要一次性读完整 SCC，并在一个 generation 里产出 global ranking + risk subgraph，schema burden 很重。
2. SA-MCGS 则把任务拆成 local-window scoring/evidence，再 algorithmically construct final core。
3. 因此主结果可能混入了 prompt decomposition / output-schema difficulty，而不只是 SCC-aware Monte Carlo graph search 的贡献。
4. wWUk 还建议与近期 document-graph reasoning / legal GraphRAG 系统比较。

所以我们需要增加一个更公平的 graph-aware baseline，而不是只继续解释 oracle-risk Naive。

## 文献与外部系统调研结论

| Work | 可迁移到 LEA baseline 的部分 | DOI / 标识 |
|------|------------------------------|------------|
| Dechtiar et al. (2025), `GRAPH-GRPO-LEX` | contract clauses as graph nodes, typed relation edges, graph-window evidence extraction | `10.1109/ICDMW69685.2025.00092`；preprint: `arXiv:2511.06618` / `10.48550/arXiv.2511.06618` |
| Chen et al. (2026), `LegalGraphRAG` | hierarchical legal graph, multi-agent evidence retrieval / verification / synthesis | `10.18653/v1/2026.acl-long.1738`；preprint: `arXiv:2605.28120` / `10.48550/arXiv.2605.28120` |
| de Martim et al. (2025), legal GraphRAG / SAT-Graph RAG | hierarchy-aware and reference-aware deterministic retrieval over legal text units | `10.3233/FAIA251598`；preprint: `arXiv:2505.00039` / `10.48550/arXiv.2505.00039` |

对外口径：LEA 是 task-aligned GraphRAG-style baseline，吸收这些工作的 graph-grounded retrieval / evidence aggregation 思路，但不声称直接复现任何一个外部系统。

### 1. Microsoft GraphRAG / Edge et al. 2024

来源：From Local to Global: A Graph RAG Approach to Query-Focused Summarization  
链接：https://arxiv.org/abs/2404.16130

关键思想：

- 先构建 graph-based text index；
- 基于图社区或局部结构生成 partial responses；
- 再把 partial responses 合成为 final response。

对我们的启发：

- 可将 SCC 切成 graph-grounded local windows；
- 每个 window 先产生局部 risk evidence；
- 最后聚合为全局 risk subgraph。

不适合直接复现的原因：

- 原任务是 query-focused summarization / QA，不是 risk-subgraph extraction；
- graph community summaries 对我们的单个 SCC 小图不一定合适；
- 但“local graph evidence -> global synthesis”的结构非常适合作为 baseline 设计。

### 2. LegalGraphRAG / Chen et al. 2026

来源：LegalGraphRAG: Multi-Agent Graph Retrieval-Augmented Generation for Reliable Legal Reasoning  
链接：https://arxiv.org/abs/2605.28120  
DOI：`10.18653/v1/2026.acl-long.1738`；preprint DOI：`10.48550/arXiv.2605.28120`  
代码：https://github.com/XMUDeepLIT/LegalGraphRAG

关键思想：

- 构建 hierarchical legal graph，区分 fact/rule/ontology 等不同层级；
- 使用 Researcher / Auditor / Adjudicator 多 agent 流程；
- 先检索候选 evidence，再验证 evidence，最后综合出 legal judgment。

对我们的启发：

- 可以设计一个 Researcher-Auditor-Adjudicator 风格的 baseline：
  - Researcher：在固定 local windows 中提取候选风险节点和冲突边；
  - Auditor：验证候选 conflict pair 是否真的由可见边和文本支持；
  - Adjudicator：汇总 verified evidence，输出 risk_subgraph_nodes。

不适合直接复现的原因：

- LegalGraphRAG 的公开实现面向 CAIL/CMDL legal judgment prediction；
- 它的 graph schema 依赖法条、案件事实、司法解释等层级；
- 我们的四个 domain 包括 Debian、SEC、BGB、CUAD，任务是 SCC 内 structural risk subgraph extraction。

因此更合理的是实现一个 “LegalGraphRAG-inspired graph evidence baseline”，而不是声称复现 LegalGraphRAG。

### 3. Graph RAG for Legal Norms / de Martim 2025

来源：An Ontology-Driven Graph RAG for Legal Norms: A Hierarchical, Temporal, and Deterministic Approach  
链接：https://arxiv.org/abs/2505.00039  
DOI：`10.3233/FAIA251598`；preprint DOI：`10.48550/arXiv.2505.00039`

关键思想：

- 法律文本有层级结构、引用网络和时间演化；
- GraphRAG 可以把结构化节点和上下文丰富的 text units 结合起来；
- 强调 decision support，而不是自动裁判。

对我们的启发：

- BGB/SEC/CUAD 的 SCC 可以被看作 graph-grounded text units；
- baseline 应该显式利用 directed edges 和局部路径，而不是只做 flat prompt；
- 但 temporal/hierarchical law norm modeling 不是我们当前 benchmark 的必要部分。

### 4. Portuguese Legal KG-RAG / Oliveira et al. 2026

来源：Retrieval-Augmented Generation and Knowledge Graphs in Portuguese-Language Legal Documents  
链接：https://aclanthology.org/2026.propor-1.1/

关键思想：

- 用 nodes 表示 Articles / Paragraphs / Items 等结构单元；
- edges 表示 normative relationships；
- retrieval 时重建 evidence paths，并进行 semantic re-ranking。

对我们的启发：

- 可增加 path-aware / k-hop evidence aggregation baseline；
- baseline 输出可以包含 risk path / evidence path，而不只是孤立 top nodes。

### 5. Contract Graph / Dechtiar et al. 2025-2026

相关来源：

- GRAPH-GRPO-LEX: https://arxiv.org/abs/2511.06618
- DOI：`10.1109/ICDMW69685.2025.00092`；preprint DOI：`10.48550/arXiv.2511.06618`
- ContractGraphEval: https://github.com/moriyadechtiar/ensemble-graph-eval

关键思想：

- 合同可以建模为 clause-level graph / minigraph；
- graph extraction 和 graph quality 可通过 multi-judge / uncertainty-aware refinement 来评估；
- 代表了 legal contract graph modeling 方向。

对我们的启发：

- 对 CUAD 这类合同 SCC，graph-aware baseline 是合理且必要的；
- 但 Dechtiar 系列更偏 graph construction / graph extraction evaluation，不是直接做 SCC risk-subgraph search；
- 因此它适合作为 “why graph-aware baseline is appropriate” 的相关工作依据，而不是直接复现实验对象。

## 推荐新增 baseline：GraphRAG-style Local Evidence Aggregation

暂定命名：

- `GraphRAG-Lite`
- 或 `Decomposed GraphRAG Baseline`
- 或 `Local Evidence Aggregation (LEA)`

建议论文/回复中称为：

> a graph-aware decomposed baseline inspired by recent GraphRAG-style document reasoning systems

不要称为：

> LegalGraphRAG reproduction

因为我们不是复现 Chen et al. 的 CAIL/CMDL legal judgment framework。

## Baseline 设计

### 输入

与 SA-MCGS 完全一致：

- 同一个 SCC；
- 同一批 node texts；
- 同一批 directed edges；
- 同一个 shared risk rubric；
- 不使用 injected labels；
- 不使用 ground-truth endpoints。

### Stage 1：Graph-grounded window retrieval

生成固定 local windows，不使用 Monte Carlo search：

1. 对每个节点生成 ego-window：seed node + incoming/outgoing neighbors，最多 `w=4` 个节点。
2. 对每条边生成 edge-window：source + target + source/target 的高 degree 邻居，最多 `w=4` 个节点。
3. 去重 windows。
4. 若 windows 超过预算，则按 deterministic graph heuristic 排序：
   - edge endpoint degree；
   - bridge / articulation-like centrality；
   - source-target local connectivity；
   - SCC traversal order。

这一步对应 GraphRAG 的 graph retrieval / evidence path reconstruction，但不使用 SA-MCGS 的 UCB、relation memory、OC 或 critical-pair revisit。

### Stage 2：Local evidence extraction

对每个 selected local window 调用同一个 local-window prompt schema：

- `clause_evaluations`
- `local_risk_subgraph_nodes`
- `local_conflict_edges`
- `critical_pairs`
- `repair_entry_nodes`
- `conflicts`

注意：这里可以复用 SA-MCGS 的 local prompt，以保证 schema burden 公平。

区别：

- 不做 MCTS selection；
- 不做 relation-first memory；
- 不做 OC 更新；
- 不做 dynamic replacement core；
- 每个 window 独立处理。

### Stage 3：Evidence aggregation

使用固定、透明的 aggregation rule：

```text
node_score(v)
  = max_local_risk_score(v)
  + alpha * local_risk_subgraph_count(v)
  + beta  * repair_entry_count(v)
  + gamma * conflict_endpoint_count(v)
  + delta * incident_verified_edge_count(v)
```

候选 conflict edge score：

```text
edge_score(u, v)
  = count_reported_conflict(u, v)
  + count_critical_pair(u, v)
  + mean_pair_severity(u, v)
```

然后选取 top nodes，cap 与 SA-MCGS 的 compression profile 对齐，例如：

```text
cap = max(4, ceil(0.45 * |SCC|))
```

输出：

- `risk_subgraph_nodes`
- `risk_subgraph_edges`
- `top_risk_nodes`
- aggregation diagnostics

### 可选 Stage 4：Auditor / Adjudicator

如果时间允许，可以加一个更像 LegalGraphRAG 的二阶段版本：

1. `Researcher`：Stage 1-2 得到 candidate nodes / conflict pairs。
2. `Auditor`：只检查 candidate pairs 是否由文本和 visible edge 支持。
3. `Adjudicator`：在 verified evidence 上输出 final risk subgraph。

但是 discussion 期间不一定需要上这个版本。原因：

- 多 agent 版本成本更高；
- 更难保证输出稳定；
- reviewer 最主要担心的是 decomposed/schema fairness，用 Stage 1-3 已经能直接回应。

## 和现有 baseline 的关系

| Baseline | 作用 | 局限 |
|---|---|---|
| oracle-risk Naive | 强 full-SCC one-shot baseline；用 ground-truth selector boost | schema burden 重，不是 deployable baseline |
| lite Naive | 控制 global ranking / full schema burden | 仍然是 whole-SCC one-shot |
| matched valid-only | 控制 unusable output 分母 | 不是新方法 |
| GraphRAG-Lite / LEA | 控制 prompt decomposition；代表 graph-aware document reasoning baseline | 没有 MCTS / relation memory / dynamic core |
| SA-MCGS | 我们的方法 | 成本更高，需要 cost table |

## 推荐实验规模

短期 discussion 不建议全量重跑 320 x 4 methods。

建议先做两层：

### 最小可交付

- 20 cases，覆盖所有 `domain x SCC-size` bucket；
- 与成本 token audit 的 20 cases 对齐；
- 模型先选 `gpt-4o` 或一个稳定模型；
- methods：Naive existing、GraphRAG-Lite、SA-MCGS existing/复做。

### 更强版本

- 40 cases；
- 包含所有 20 个 size buckets；
- 对 CUAD 28/34、BGB 25、SEC 18、Debian 12 等 hard/long cases 做跨模型补充。

对外回复时不要强调 small sample；说：

> We are adding a graph-aware decomposed baseline on a stratified set covering different SCC scales and domains.

## 评估指标

与主实验一致：

- Root@3
- Risk-any
- Risk-all
- Compression
- Avg subgraph size
- Unavailable outputs

额外加入：

- LLM calls
- token/case
- runtime/case
- subgraph precision / irrelevant-node rate

## Discussion 口径草稿

第一轮回复：

> We agree that the comparison should separate SCC-aware search from prompt decomposition and output-schema difficulty. In addition to the matched valid-only and lite-Naive checks, we are adding a graph-aware decomposed baseline inspired by recent GraphRAG-style document reasoning systems. This baseline retrieves deterministic local graph windows, applies the same local risk-evidence schema as SA-MCGS, and aggregates local evidence into a risk subgraph without relation-first memory, OC signals, critical-pair revisiting, or dynamic-core replacement. We will report this comparison together with token/call/runtime costs in a follow-up response.

后续有结果后：

> This baseline directly controls for local-window prompting and structured schema difficulty. Therefore, any remaining gap is less attributable to one-shot output burden and more specifically to search policy, persistent relation evidence, and dynamic core construction.

## 结论

可以做升级版 baseline，而且比直接复现 LegalGraphRAG 更合适。

最推荐的 baseline 是：

> GraphRAG-style Local Evidence Aggregation：固定图窗口检索 + 同 schema 局部 evidence extraction + 简单透明聚合

它能同时回应：

1. rxvy 的 decomposed/local-window baseline 要求；
2. iMEC 的 simpler graph-aware baseline 要求；
3. wWUk 的 document-graph reasoning / GraphRAG 比较要求；
4. baseline fairness / schema burden 的核心质疑。

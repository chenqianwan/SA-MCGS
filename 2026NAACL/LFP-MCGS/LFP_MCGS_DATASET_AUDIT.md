# LFP-MCGS 数据资格审计

> 更新：2026-08-19<br>
> 当前 Gate：审计对象已从“哪个现成逻辑数据能当主集”改为“哪些真实 document SCC 能承载可解释的 topology-controlled intervention”。旧 ProofWriter/CLUTRR/StepGame 数字保留为 symbolic asset audit，不再代表论文主轴。

## 0. 当前结论

| 问题 | 结论 |
|---|---|
| 主数据怎么来？ | 从 SA-MCGS 已有真实 document graphs 重新提取 SCC，冻结节点/边/窗口，在现有窗口中做最小 `seed / bridge / witness` 注入。 |
| Paper 1 的注入能否直接复用？ | **原则可复用，标签不能直接复用。** Paper 1 注入风险端点；Paper 2 必须重新生成可执行 Horn program、LFP、provenance 与 deletion oracle。 |
| 为什么不只用 ProofWriter？ | 它能验证 symbolic safety，但没有真实 cyclic-document local-window search pressure。 |
| TreeMCTS 是主要比较对象吗？ | **不是。** 主比较是 matched-compute 强通用 LLM；TreeMCTS 只用于关闭 exact state merging。 |
| 人工数据能证明什么？ | 只能证明受控机制与 failure mode，不能证明自然分布或现实风险发生率。 |
| positive Horn 能做强推翻吗？ | **不能。** 它单调增加事实；显式冲突可以检测，但已成立事实不会被 retract。 |

---

## 1. 六道数据资格 Gate

| Gate | 必须回答的问题 | 通过标准 |
|---|---|---|
| G0 · 真实载体 | SCC 是否来自真实文档/记录图？ | source、node、edge、snapshot 可追溯；不是临时生成 canonical cycle |
| G1 · 拓扑冻结 | SCC 内语义干预是否偷改了搜索难度？ | Productive/Decoy/Broken-or-Inactive/Clean 的节点、边、window boundary 全部不变；Matched-DAG 是单独物理拓扑 control |
| G2 · 最小语义干预 | 是否只改变目标能力？ | seed/bridge/witness 短、领域一致、单窗口不足；有 clean/no-op controls |
| G3 · Exact gold | 标签和 proof 能否独立重算？ | 两个 LFP evaluator 一致；逐轮 provenance 与 deletion oracle 完整 |
| G4 · Paired causality | 是否排除了词面、长度和普通多跳混杂？ | Productive/Decoy/Broken-or-Inactive/Clean/Matched-DAG 五联组 |
| G5 · 外部有效性 | 是否离开固定模板仍有信号？ | held-out template/entity/topology + 至少一个真实无注入 block；分表报告 |

主实验只有通过 G0–G4 才能开始；G5 决定 claim ceiling。

---

## 2. SA-MCGS 资产审计

现有 Paper 1 管线包含 Debian、SEC EX-21、BGB 与 CUAD 四个领域。可复用的是：

- 真实记录与 source IDs；
- document graph 与 Tarjan SCC；
- local-window materialization；
- SCC sampling、PUCT/UCB、virtual loss 和运行日志；
- root / bridge / witness 式远端联合注入经验。

不能直接复用的是：

- `direct_mutex`、`handoff_invariant`、`temporal_gate`、`condition_trigger` 等 risk label；
- 只有 root 带 `_perturbed` 标记，bridge/witness 的文本改动未完整进入 manifest，也没有逐条 Horn provenance gold；
- Paper 1 的 OC、risk prompt、relation-first memory 与 dynamic risk core。

Paper 1 注入实现可作为 protocol 参考：[`inject_defect.py`](../experiments/cross_domain/inject_defect.py)。Paper 2 必须额外记录所有被修改窗口；不能只给 root 标注 `_perturbed`，也不能把 root 永久放在固定拓扑区间。

### 2.1 Carrier 优先级

| 优先级 | Carrier | 当前决定 |
|---|---|---|
| P0 | BGB / QuantLaw 法条引用 SCC | 优先做法律核心；先复核 source、长度档与许可 |
| P0/P1 | Debian dependency SCC | 做结构差异大的第二 carrier；先正确处理 alternatives/version semantics |
| P1 | SEC EX-21 | 重新审计实体解析后再决定；伪环不得进入核心 |
| P1 | CUAD / contract graph | 只使用图边和引用语义可解释的 SCC；否则降为 source-grounding 外测 |

`3 / 5 / 7 / 9 / 12 / 16 / 20` 是目标采样网格，不是强制每个域都有每个档。缺失的长档可作跨域 pooled stress，但统计仍按 carrier family 聚类。

---

## 3. Intervention 审计表

每个 case 构建时必须自动验证：

- [ ] Productive/Decoy/Broken-or-Inactive/Clean 的 topology hash 与 clean carrier 完全一致；Matched-DAG 单独记录 edge delta、pair mapping 与自身 hash；
- [ ] 原始窗口 hash 可恢复；
- [ ] 每个新增 span 有 window/source、模板、实体和随机种子；
- [ ] Productive query 在 full LFP 中可证；
- [ ] 任一指定必要 source 删除后 query 不可证；
- [ ] Decoy 与 Broken/Inactive 不可由循环自启动；
- [ ] Clean 不含注入答案词或 proof shortcut；
- [ ] Matched-DAG 匹配窗口数、tokens、事实/规则数、proof depth 和 label，但明确不满足“同 topology hash”；
- [ ] 单窗口与 injected-span-only 模型不能稳定解题；
- [ ] 五联组位于同一 split；
- [ ] 被测 LLM 未参与 gold 构造。

人审另查：领域自然性、实体一致性、语义方向、单窗口泄露与注入可识别度。形式 oracle 不能代替语言审计。

---

## 4. Symbolic safety 资产：历史数字继续保留

### 4.1 ProofWriter

[ProofWriter](https://aclanthology.org/2021.findings-acl.317/) strict-positive 的历史 grounded audit：

| 切片 | causal theories | causal queries | MAC `≥3` |
|---|---:|---:|---:|
| OWA D5 | **2,778** | **24,169** | 21,350（88.3%） |
| ParaRules | **1,679** | **8,723** | 6,749（77.4%） |

独立 Horn engine 对 eligible 官方标签 mismatch 为 `0`。这些数据继续用于：

- LFP/executor regression tests；
- seeded/unseeded cycle invariant；
- proof/provenance serialization；
- minimal logical edit 与 parser sanity。

它不承担真实 document SCC、自然性或 MCGS 主优势。

### 4.2 其他已实测资产

| 数据 | 历史实测 | 当前角色 |
|---|---:|---|
| CLUTRR | 3,977/3,977 query 被独立 closure 重算 | 关系组合 sanity；无复杂 document SCC |
| StepGame | 100k noisy test；78,777 fully canonical；57.45% 需要多跳 | fact acquisition 与 noise control |
| SpaRTUN/SpaRP | 48,246 questions；25,112 gold-chain length≥2；21,163 machine-readable proof rows | proof-certificate / matched-DAG control |
| BoardgameQA | 7,500 theories；predicate cycles 792，但 grounded rule graph cycles 0 | 负面审计：predicate SCC 不等于 productive grounded cycle |

这些结果证明既有 loader/oracle 可用，不再用它们决定当前论文标题。

---

## 5. 真实无注入与外部控制

| 数据 | 可回答的问题 | 限制 |
|---|---|---|
| AOP-Wiki / SIGNOR | 有 source/evidence 的真实 feedback case 能否通过相同 interface | 没有原生 LFP QA/proof；预注册语义不等于 biological truth |
| ContractNLI / CUAD | 真实法律/合同 source grounding | 无权威 recursive program；不能承担 SCC-LFP claim |
| MuSiQue | 分散证据是否必须组合，是否存在 disconnected shortcut | 多跳不等于 SCC 或 recursive closure |
| Debian `dose/botch` | 图与 solver certificate sanity | 完整 installability 超出 positive Horn |

真实无注入 block 的任务可以与核心机制集不同，但必须分表、分指标、分 claim。不能把不同 semantic profiles 做一个 macro average。

---

## 6. Split、统计与发布

- split 单位：carrier SCC family；同一 family 的五个条件不拆开；
- held-out：template family、entity family、topology hash 与 source family；
- 主统计：按 SCC family clustered bootstrap / mixed model；多个 query 不是 IID；
- 报告：每个 size、model、condition、budget 单独显示，不只给 pooled score；
- 发布：carrier IDs、原文 hash、构建脚本、注入 spans、exact oracle、reject reasons、prompt、raw outputs 与 cost ledger；
- 原始数据不可重分发时只发布 index、patch manifest 与 reconstruction script；
- clean 与 natural external 数据永远与 intervention 分表。

关键冻结资产继续保留在 [`dataset_audit/`](./dataset_audit/)；旧资格矩阵图片仅是第三轮候选审计快照，不再作为当前决策图。

---

## 7. 当前数据 Gate

下一步不是继续扩大候选池，而是完成一个小型、完整、可否定的 injection smoke：

1. 从至少两个 carrier 域各取 `3 / 5 / 7 / 9` 节点 SCC；
2. 每个 SCC 生成五联组；
3. 双 executor + deletion oracle 100% 通过；
4. 做 injection-only shortcut 与 30–50 例盲审；
5. 用同一强 LLM 跑 Direct/CoT 与 local-window LFP-MCGS；
6. 只有出现随 size 放大的 proof-valid gap，才扩到 `12 / 16 / 20`。

一句话口径：

> **核心数据证明机制，clean 数据测误报，真实无注入数据限制外推；三者互补，但绝不能互相冒充。**

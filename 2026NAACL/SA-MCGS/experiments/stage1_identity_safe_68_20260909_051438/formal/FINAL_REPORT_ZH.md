# Stage-1 identity-safe 四臂配对消融：最终报告

状态：**完成并通过最终审计（68/68 valid，0 invalid）**。旧 frozen Full 因缺 raw prompt/config hash，未作为严格对照；本批次使用同期 Full。

## 可入稿结果

| Arm | Root@3 [cluster 95% CI] | Risk-any [cluster 95% CI] | Risk-all [cluster 95% CI] | Δ Risk-all vs Full [cluster 95% CI] | Risk-all discordance (+/−) |
|---|---:|---:|---:|---:|---:|
| Full SA-MCGS (contemporaneous rerun) | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 88.2% [75.0%, 100.0%] | reference | — |
| No relation-first memory | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 11.8% [0.0%, 25.0%] | 2/0 |
| No critical-pair ledger/revisit | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 11.8% [0.0%, 25.0%] | 2/0 |
| Random local-window selection | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 82.4% [64.7%, 100.0%] | -5.9% [-22.2%, 14.3%] | 2/3 |

这里的 +/− 分别表示相对 Full 从失败变成功、从成功变失败的配对 case 数。Root@3 与 Risk-any 四臂均饱和；所有非零 Risk-all 配对区间均覆盖 0。

## 结论与旧归因的关系

本批次**不支持**旧 rebuttal 中“relation-first memory 或 critical-pair ledger 提升 Risk-all”的组件归因。两个消融均为 17/17，Full 为 15/17；二者相对 Full 均 +2/17（+11.8 pp，clustered 95% CI [0, 25.0 pp]）。这不是显著正向证据：只有 5 个 physical source-SCC clusters，区间包含 0。

Random local-window 为 14/17，相对 Full −1/17（−5.9 pp，clustered 95% CI [−22.2, 14.3 pp]；discordance 2/3），同样不能作确定性组件结论。最稳妥的入稿表述是：在这一小型 identity-safe 子集上，Root@3/Risk-any 无差异，Risk-all 的组件贡献不确定，且两个结构组件的移除没有造成退化。

## 两处 Full-only Risk-all 失败与 trace 根因

### Case 20: `20_sec_ex219_scc_5_direct_mutex`

注入 risk nodes 为 `us-cw-3682212, us-cw-3682811`。Full 的风险排名仍覆盖全部 risk nodes（Risk-all@top3=True），但最终 dynamic evidence core 漏掉 `us-cw-3682212`，因此预冻结的 final-core Risk-all=False。

| Arm | Final-core Risk-all | Missing risk node(s) | Selection modes |
|---|---:|---|---|
| Full SA-MCGS (contemporaneous rerun) | False | us-cw-3682212 | critical_pair_revisit:10, relation_probe:9, ucb_relation_bias:41 |
| No relation-first memory | True | none | ucb:60 |
| No critical-pair ledger/revisit | True | none | relation_probe:19, ucb_relation_bias:41 |
| Random local-window selection | True | none | random_local_window:60 |

四臂完整输出和末次 trace/convergence 摘要已固化在 `negative_control_audit.json`；Full 原始结果：`/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage1_identity_safe_68_20260909_051438/formal/results/20_sec_ex219_scc_5_direct_mutex__full-sa-mcgs-rerun.json`。

### Case 73: `73_sec_ex2110_scc_2_temporal_gate`

注入 risk nodes 为 `us-cw-1020294, us-cw-515909`。Full 的风险排名仍覆盖全部 risk nodes（Risk-all@top3=True），但最终 dynamic evidence core 漏掉 `us-cw-515909`，因此预冻结的 final-core Risk-all=False。

| Arm | Final-core Risk-all | Missing risk node(s) | Selection modes |
|---|---:|---|---|
| Full SA-MCGS (contemporaneous rerun) | False | us-cw-515909 | critical_pair_revisit:10, relation_probe:9, ucb_relation_bias:41 |
| No relation-first memory | True | none | ucb:60 |
| No critical-pair ledger/revisit | True | none | relation_probe:19, ucb_relation_bias:41 |
| Random local-window selection | True | none | random_local_window:60 |

四臂完整输出和末次 trace/convergence 摘要已固化在 `negative_control_audit.json`；Full 原始结果：`/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/experiments/stage1_identity_safe_68_20260909_051438/formal/results/73_sec_ex2110_scc_2_temporal_gate__full-sa-mcgs-rerun.json`。

## 独立负控与 evaluator 核验

- 17 个 quartet 的 case_uid、physical SCC fingerprint、source hash、注入身份与 seed=42 完全一致；model=gpt-4o、budget=60、window=4、internal concurrency=3 一致。
- prompt builder hash=`sha256:ea6e30590d7eeb3d4514027936ea9220f54c3fb9255b59baa8fdc65ef7160001`；parser hash=`sha256:ce5f8791744d212f035522932159cbc89df6ebcda912bb6ad9b202eeebcaace1`；response schema 冻结一致。精确 request prompt 会因各臂选择不同窗口/轨迹而不同，这是干预本身，不是 parity 错误。
- Full/no-relation/no-critical 的 base config hash 已从冻结源码独立重算并逐一匹配。Random 臂按设计与 Full 共用 base config hash，但其 runtime selector 的 17×60 events 均为 `random_local_window`，seed 规则为 `8229 + case_order×1009`；组合后的四个 effective intervention hashes 全部不同。
- no-relation：17/17 均 `relation_first_enabled=False`、relation probes=0，且无 relation-biased selection；no-critical：17/17 ledger/locked/candidate/revisit 全空；Full 使用原生 relation-first；random：每 case 60/60 random events。
- Risk-any/Risk-all 已对 68 格从集合关系独立重算，并与结果 JSON、strict CSV 三方逐格一致。Risk-all 定义为 `injected_risk_nodes ⊆ final core_evidence_risk_subgraph_nodes`，不是 top-3 ranking coverage。每臂 denominator=17；0 invalid；不存在 evaluator 或 denominator 错误。
- protocol/code/result/artifact SHA256 全部复算匹配；order 8 的四格 smoke promotion 29/29 checks 通过，非结果选择性复用。

## 五层可靠性与成本

正式 68-cell 矩阵：3934 network calls（3931 success / 3 fail）；3928 logical rollouts；6 个 first-parse/transport fail，6 recovered，0 exhausted；68 case-level valid，0 invalid，0 case retry。按臂明细见 `gate.json`。

正式矩阵本身（order 8 只计一次）为 6,385,360 tokens、$37.461483。实际唯一付费账本为 smoke 12 格 + formal 新跑 64 格：4437 calls、8,266,395 tokens、$47.381175；低于 $60 硬上限，余量 $12.618825。

共享账户在 formal checkpoint 间从 $866.179282 到 $801.287396，但期间有并行实验，因此该差额仅作交叉核验；本线 token ledger 才是可归因成本。

## 产物

- `stage1_paired_publication_table.csv`：可入稿四臂点估计、cluster CI、paired delta 与 discordance。
- `final_summary.json`：最终机器可读汇总。
- `negative_control_audit.json`：逐 case parity/toggle/evaluator、Full failure trace 与 hash 证据。
- `stage1_case_results_strict.csv`：68 格 strict 明细。
- `stage1_clustered_uncertainty.json`：20,000 次 source-SCC clustered bootstrap。
- `gate.json` / `GATE_ZH.md`：五层正式 gate。

未修改顶层 `plan.md` / `REMAINING_EXPERIMENTS_ZH.md`，未提交或推送 Git。

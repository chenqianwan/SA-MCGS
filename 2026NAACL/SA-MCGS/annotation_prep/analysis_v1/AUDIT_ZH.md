# annotation_prep 后处理工具审计（离线）

审计日期：2026-09-09。审计范围为 `2026NAACL/SA-MCGS/annotation_prep/`，并额外检索了仓库中的 IAA、adjudication、label freeze、cleanliness 与 clustered bootstrap 实现。审计没有读取任何真实专家导出或真实专家标签，也没有调用 API；测试只读取明确标记的合成导出。

## 结论

此前没有完整的专家标注后处理闭环。现有工具覆盖“候选集/私有 codebook → 盲标网页”的上游构建和页面安全校验，但不覆盖三专家结果合并、结果 schema 校验、IAA、裁决、label freeze 或 expert-grounded cleanliness。

| 能力 | 审计前已有内容 | 是否可直接复用 | 本目录补充 |
|---|---|---:|---|
| JSON/XLSX 专家导出 | `frontend/blind_app.js` 负责导出 | 只有前端，没有离线导入门禁 | 读取 `blind_annotation.export.v2` 与当前三张 XLSX 表 |
| 三专家合并/schema | 页面只检查浏览器本地状态 | 否 | 精确三 slot、三 reviewer、hash/order/case/section bijection 校验 |
| IAA | 无 | 否 | raw agreement、pairwise Cohen kappa、Krippendorff nominal alpha、fixed-universe Gwet AC1、全体与 eligible-conditional set Jaccard |
| adjudication | 计划文档只有原则 | 否 | outcome-blind 固定选入规则和空白 decision template |
| final label freeze | 无 | 否 | 强制 adjudication、legacy 显式输入、freeze attestation 与 SHA-256 |
| cleanliness | 无 | 否 | evidence recall、repair coverage、excess-node rate、bridge-aware precision/excess、available-layer endpoint density |
| source-SCC clustered CI | Stage-1 runner 有任务专用函数 | 不能处理专家冻结标签 | 分层、确定性 cluster bootstrap；专家不作独立样本 |

## 正式使用前复审与修复

两轮独立复审发现下列 identity、派生数据与统计口径风险。以下门禁已经落入 `annotation_analysis.py`，每项均有合成回归测试；这里的“通过”只表示工具门禁通过，不表示正式 legacy 标签已经具备。

| 级别 | 风险 | 修复后的 fail-closed 行为 | 回归测试 |
|---|---|---|---|
| P0 | manifest/codebook/translation 与 variant 身份未贯穿 merge→freeze | 除正文 hash 外，wrapper 必须绑定唯一 master case，section→node 必须一一覆盖 canonical nodes；post fingerprint 从 canonical 正文重算，endpoint/bridge 绑定 outcome-blind catalog | `test_wrapper_is_bound_to_its_exact_master_case`、`test_section_to_node_mapping_must_be_one_to_one`、`test_post_fingerprint_is_recomputed_from_canonical_node_text` |
| P0 | merged 内 provisional/IAA/queue 可被重封后篡改 | freeze 强制显式提供与 merged 绑定相同的三份源导出，并重新生成 annotations、provisional、IAA、queue；派生 hash 必须一致 | `test_freeze_recomputes_merged_from_all_three_bound_exports`、`test_freeze_records_recomputed_iaa_queue_and_source_exports` |
| P0 | 裁决可添加/删除 case 或篡改队列元数据 | freeze 要求 exact case-set，并逐例核对 `stratum/domain/reasons/allowed sections/provisional`；outcome-blind attestation 必须具名带时间且为真 | `test_adjudication_case_set_must_be_exact`、`test_adjudication_metadata_is_recomputed_not_trusted`、`test_adjudication_requires_outcome_blind_attestation` |
| P0 | legacy sibling variant 或任意“来源文件”可伪绑定 | source artifact 只接受正式 record schema；每个 locator 必须解析且 normalized/source 全字段相等；post fingerprint 与 canonical 正文、endpoint 与 injection identity 均精确相等 | `test_legacy_case_must_bind_post_content_fingerprint`、`test_legacy_source_schema_locator_and_record_are_verified` |
| P0 | complete grid 从输入自推断或评分时换轴 | models/methods/strata 在 label freeze 内固化；score 只读冻结轴并验证精确笛卡尔积，runtime axes 只能做相等性复核 | `test_complete_grid_uses_frozen_dimensions` |
| P0 | 正例空 repair packet 令 cleanliness 静默掉分母 | positive+sufficient freeze 必须有非空 minimal evidence 与 repair packet；eligible positive 的空 returned set 明确计 0，invalid 仍留在严格分母 | `test_positive_sufficient_final_label_requires_repair_packet`、`test_full_synthetic_closure_and_zero_preserving_cleanliness` |
| P0 | 工作区缺正式 legacy12 标签 | 缺 artifact 时给出明确 `Formal legacy12 label gate BLOCKED`；工具绝不生成或推断旧标签 | `test_missing_formal_legacy_artifact_is_an_explicit_gate` |
| P1 | SCC 多 variant 获得更高权重 | 先在 SCC 内求均值，再对 SCC 等权 bootstrap；仍同时报告 presentation 数与 SCC 数 | `test_cluster_bootstrap_is_scc_equal_weighted_and_deterministic` |
| P1 | 系统行可缺 SCC/stratum | 两字段均为必填，且必须与 frozen label 精确一致 | `test_system_source_scc_uid_and_stratum_are_required` |
| P1 | XLSX section reviewer 未核对、孤儿行被忽略 | section/case/metadata reviewer 一致；section sheet 的 case 集必须与 case sheet 精确相等，后续仍做逐 case section bijection | `test_xlsx_rejects_wrong_section_reviewer_and_orphan_rows` |
| P1 | 三份导出可共同声明伪 translation hash | 每份 export 必须等于已经验真的正式 translation pack hash | `test_expert_export_must_match_verified_translation_pack` |
| P1 | legacy source hash/provenance 只检查非空 | 要求合法 SHA-256、真实存在且不同于 normalized labels 的来源文件、实算 hash 相等、唯一 locator、非空 provenance、具名带时间转录认证 | `test_legacy_source_artifact_and_provenance_are_fail_closed` |
| P1 | current/legacy ID 可能碰撞并覆盖 | current、legacy 的 primary IDs 必须 disjoint；所有可接受 alias 全局唯一 | `test_current_and_legacy_case_ids_must_be_globally_disjoint` |
| P1 | system row 可用 alias 命中错误 variant | 除 SCC/stratum 外强制 exact `case_uid`；post 层还强制 exact canonical `post_content_fingerprint`，pre 层须显式 null | `test_system_output_requires_exact_case_uid_and_post_fingerprint` |
| P1 | AC1 用观测类别数导致数值漂移 | 每个字段使用固定完整类别全集；未观测类别保留零计数，并以已知数值 oracle 回归 | `test_gwet_ac1_uses_fixed_category_universe_numeric_oracle` |
| P1 | minimal evidence 可落在 repair packet 外 | expert export、adjudicated final 与 legacy source 三条路径全部强制 `minimal ⊆ repair` | `test_minimal_evidence_must_be_subset_of_repair` |
| P1 | bridge 被误计为冗余；endpoint scope 被硬编码 | freeze 固化 canonical bridge 及 `repair ∪ bridge` cleanliness 规则；endpoint 只报告整层真实具备 endpoint 的 strata，并把 scope 固化在 score protocol | `test_bridge_aware_cleanliness_uses_frozen_canonical_bridge`、`test_endpoint_metrics_follow_frozen_actual_availability` |
| P1 | empty-empty Jaccard 抬高 set IAA | 保留预声明全 case 口径，同时报告排除 empty-empty pair/case 的 eligible-conditional Jaccard 与分母 | `test_set_jaccard_reports_eligible_conditional_value` |

复审后的测试命令与结果：

```bash
cd 2026NAACL/SA-MCGS/annotation_prep/analysis_v1
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_annotation_analysis.py
```

结果：`Ran 33 tests ... OK`。

## 当前真实布局（只含元数据）

- `frontend/data/manifest.json`：42 个当前盲标 presentation。
- `internal/private_codebook.json`：42 个当前 presentation 的私有映射，以及 12 个只复用旧标签的记录。
- 当前 42 精确分为 18 个 `pre18` 与 24 个 `post_new24`；旧 12 使用 `post_legacy12`，不进入本轮 IAA，也不与新 post 合并成 headline。
- source cluster 使用 `source_physical_fingerprint`，而非不稳定的数值 Tarjan `scc_id`。
- 当前静态页面 JSON schema 是 `blind_annotation.export.v2`；XLSX 表名是 `样本整体标注`、`逐段标注`、`版本信息`。

机器可读的无标签审计快照为 `current_layout_audit.json`。

## 边界

- `analysis_v1` 不含任何真实专家标签或由真实材料推导的标签。
- `fixtures/` 全部显式标记 `synthetic_fixture: true`，仅覆盖代码路径；其数字不得进入论文。
- 旧 12 的标签不会被重建、投票或猜测；正式 freeze 必须同时提供人工核对后的 `annotation_analysis.legacy_labels.v1` 与逐 locator 可解析的 `annotation_analysis.legacy_source_records.v1`。
- 截至本次审计，仓库仍不存在通过上述来源、指纹和 provenance 门禁的正式 legacy12 标签 artifact；因此正式 freeze 是“工具就绪、输入阻塞”，不能用合成 fixture 绕过。
- 系统输出只有在 label bundle 已冻结并用 hash 绑定后才能评分。

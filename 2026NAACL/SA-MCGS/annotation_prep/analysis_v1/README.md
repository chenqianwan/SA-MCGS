# SA-MCGS 专家标注离线分析 v2

这是一个零 API、fail-closed 的后处理入口。正式链兼容原独立盲标页面的 v2 JSON/XLSX 导出，并固定保持 `18 pre / 24 new post / 12 legacy post` 三层口径。带算法提示的辅助复核导出不进入正式盲标链。

唯一脚本为 `annotation_analysis.py`，仅依赖 Python 3.11 标准库；读取 `.xlsx` 时额外需要 `openpyxl>=3.1`。脚本不会调用模型或网络。

## 简化二选一表单协议

新表单使用 `annotation_protocol: binary_judgment_v1`，可开始收集数据；与原 v2 的问题含义不同，不能直接导入原正式合并／裁决／冻结链。

| 字段 | 值与含义 |
|---|---|
| `target_conflict` | `present / absent`，专家原始存在性判断，始终原样保留 |
| `judgment_sufficient` | `yes / no`，材料是否足以支持上述判断；不复用原 `evidence_sufficient` |
| `confidence` | 1–5；保留 |
| `sections.*.minimal_evidence / repair_packet` | 明确布尔值；强制最小证据集包含于修复材料集 |
| `sets_reviewed` | 必须为 `true`；由“确认并保存”动作记录，不增加一道专家问题 |
| `role / need_more_context / evidence_sufficient` | 不再要求填写；若旧记录存在则保留，不补造、不转为本轮专家评分 |

独立工具函数（只校验或算单例，不写正式论文结果）：

- `validate_binary_annotation(record, section_ids)`：校验新协议、完整段落覆盖、集合确认及充分正例的非空最小证据；不修改输入记录。
- `binary_metric_applicability(record, section_ids)`：保留原始判断，另给 `scoring_status = positive / negative / insufficient`。材料“不充分”无论原始判断为何，都不进入确定正例、负例或误报率分母，留待裁决。
- `binary_case_metrics(record, section_ids, returned_section_ids, prediction=..., output_valid=..., bridge_section_ids=...)`：按明确两集合计算单例 evidence recall、repair coverage、excess、bridge-aware excess/precision；ID 必须是同一样本内的 section ID。桥接节点需事先独立固定，不能按系统输出反推。充分正例的空返回／invalid 保留分母，recall、coverage、density、precision、excess 均按既有约定记 0；负例与不充分例不计算集合质量指标。无效系统输出单列，不当作正确负例。
- `binary_categorical_iaa(cases, field)`：只对本轮确实询问的 `target_conflict / judgment_sufficient` 使用固定二类别全集；缺失专家不填默认值，报告排除数量。角色／上下文等旧字段即使留存也不贡献本轮评分人数。

这些函数不是三专家共识、裁决或冻结后的 gold。未来正式分析需独立声明新协议的合并／裁决／冻结流程和实际是否看过算法提示；不能把辅助复核包装成独立盲标。旧 `partial / not_applicable` 不自动变成二选一，新旧标签不静默混用。JSON 与 XLSX 对辅助模式及新协议都有显式门禁；不含新字段的原 v2 导出继续兼容。

## 正式执行顺序

以下变量只为缩短示例；所有输出应写到新的、权限受控的结果目录，不要放进专家分发包。

```bash
ANALYSIS=2026NAACL/SA-MCGS/annotation_prep/analysis_v1/annotation_analysis.py
MANIFEST=2026NAACL/SA-MCGS/annotation_prep/frontend/data/manifest.json
CODEBOOK=2026NAACL/SA-MCGS/annotation_prep/internal/private_codebook.json
TRANSLATIONS=2026NAACL/SA-MCGS/annotation_prep/frontend/data/translations_zh.json
RESULTS=/path/to/private/expert_analysis_results
```

1. 无标签布局门禁：

```bash
python3 "$ANALYSIS" layout \
  --manifest "$MANIFEST" \
  --codebook "$CODEBOOK" \
  --translations "$TRANSLATIONS" \
  --out "$RESULTS/layout_audit.json"
```

这一步会重算 manifest 与 translation-pack 正文 hash，逐段核对翻译源文本，逐 wrapper 绑定其唯一 source-master case，并要求 section→node 是覆盖 canonical nodes 的一一映射。所有 post fingerprint 都由有序 canonical node 正文按生成端同一公式重算；endpoint/bridge 则绑定 outcome-blind post identity catalog。上述文件 hash 和 identity-map hash 会写入后续产物。

2. 合并三位专家的独立导出，同时生成 IAA 和裁决模板。三个文件可分别是页面导出的 `.json` 或 `.xlsx`，顺序不限；slot 必须恰为 `expert_1/2/3`：

```bash
python3 "$ANALYSIS" merge \
  --manifest "$MANIFEST" \
  --codebook "$CODEBOOK" \
  --translations "$TRANSLATIONS" \
  --exports /private/e1.json /private/e2.xlsx /private/e3.json \
  --out-dir "$RESULTS/merge"
```

产物是：

- `merged_bundle.json`：保留三份原始判断的规范化副本、身份映射和预声明 2/3 provisional 值；
- `iaa.json`：只给 `pre18`、`post_new24` 各自的 IAA；旧 12 不重算，且不产生跨层汇总；
- `adjudication_template.json`：只纳入预先规定的疑难例，decision 初始为 `null`。

必须先复制裁决模板，再由领域裁决者填写 `decision` 与 `outcome_blind_attestation`，并重新生成该文件的 `artifact_sha256`。不得查看系统输出后再决定哪些 case 进入裁决。freeze 会从显式传入且与 merged 绑定一致的三份原始导出重新生成 normalized annotations、provisional、IAA 与裁决队列，而不信任 merged 内的派生值。裁决 case 集合以及每例 `stratum/domain/reasons/allowed sections/provisional` 必须与重算模板逐字段一致；额外裁决、漏裁决或 `system_outcomes_unseen` 非真都会被拒绝。

3. 人工准备旧 12 的逐字复用输入。normalized schema 为 `annotation_analysis.legacy_labels.v1`；其 source artifact 必须使用受支持的 `annotation_analysis.legacy_source_records.v1`，不能指向任意文件。每个唯一 locator 必须实际解析到一条 source record，normalized 的身份、标签、node sets、endpoint 与 provenance 必须逐字段相等；endpoint 还必须等于 canonical injection identity。脚本不会替你生成、猜测或推断旧标签。字段示意见合成 fixtures，不得复制其中的合成值。

当前仓库没有可验证的正式 legacy12 标签 artifact，因此正式 54-case freeze 处于明确的 `BLOCKED_UNTIL_EXPLICIT_VERIFIED_LEGACY_LABEL_ARTIFACT` 门禁；合成 fixture 只用于测试。

4. 在解盲任何系统结果之前 freeze：

```bash
python3 "$ANALYSIS" freeze \
  --merged "$RESULTS/merge/merged_bundle.json" \
  --adjudication "$RESULTS/adjudication_filled.json" \
  --manifest "$MANIFEST" \
  --codebook "$CODEBOOK" \
  --translations "$TRANSLATIONS" \
  --legacy-labels "$RESULTS/legacy12_verified.json" \
  --exports /private/e1.json /private/e2.xlsx /private/e3.json \
  --protocol-id sa-mcgs-expert-freeze-v2 \
  --frozen-by ANON_FREEZER_ID \
  --frozen-at 2026-09-09T12:00:00+08:00 \
  --confirm-outcome-blind-freeze \
  --score-models gpt-4o gemini-2.5-pro \
  --score-methods one-shot lea sa-mcgs \
  --score-strata pre18 post_new24 post_legacy12 \
  --out "$RESULTS/frozen_labels.json"
```

`label_bundle_sha256` 绑定三份源导出及其重算派生物、裁决文件、legacy source records、canonical endpoint/bridge、最终 node sets 与完整评分网格。任何后改都会使校验失败。

5. 将每个系统结果规范化为 `annotation_analysis.system_outputs.v1`，并写入上一步的 `label_bundle_sha256`。每个 record 至少含：

```json
{
  "case_id": "presentation_id、original_case_id 或 case_uid",
  "case_uid": "与 frozen label 完全一致的精确 case_uid",
  "post_content_fingerprint": "post 层为精确 sha256；pre18 必须显式为 null",
  "source_scc_uid": "与 frozen label 完全一致的 SCC 身份",
  "stratum": "pre18|post_new24|post_legacy12",
  "model": "model-id",
  "method": "one-shot|lea|sa-mcgs",
  "output_valid": true,
  "prediction": "present|absent|insufficient|abstain",
  "returned_node_ids": ["原始 node ID"]
}
```

Strict invalid 必须写 `output_valid:false`、`prediction:"invalid"`、空 returned set；禁止丢行或换 case。

6. 计算 cleanliness 和 source-SCC clustered CI：

```bash
python3 "$ANALYSIS" score \
  --labels "$RESULTS/frozen_labels.json" \
  --system-outputs "$RESULTS/system_outputs.json" \
  --bootstrap-samples 20000 \
  --seed 20260909 \
  --require-complete-grid \
  --expected-models gpt-4o gemini-2.5-pro \
  --expected-methods one-shot lea sa-mcgs \
  --expected-strata pre18 post_new24 post_legacy12 \
  --out-dir "$RESULTS/scored"
```

完整网格轴只取自 `frozen_labels.json.score_protocol`，不会从 system outputs 自推断；score 阶段的三个 `--expected-*` 若提供，只作为必须与冻结轴逐项相等的复核。输出 `cleanliness_records.json` 与 `clustered_summary.json`。bootstrap 在每个 `stratum × model × method` 内先求每个 `source_scc_uid` 的均值，再等权采样 SCC；不会把专家或同 SCC variants 当作独立 cluster，也不会跨层 pooling。

## 指标固定定义

- `expert_evidence_recall = |returned ∩ frozen minimal evidence| / |frozen minimal evidence|`。
- `repair_packet_coverage = |returned ∩ frozen repair packet| / |frozen repair packet|`。
- `excess_node_rate = |returned − frozen repair packet| / |returned|`；eligible positive 的 returned 为空时按预声明约定记 0，而不是从分母静默删除。
- `bridge_aware_excess_node_rate` 的允许集合固定为 `repair packet ∪ canonical bridge nodes`；对应 precision 同时输出，规则写入冻结 score protocol。
- endpoint 只在某 stratum 每个 case 都有 canonical non-empty endpoint 时报告；真实可用层由 freeze 计算并固化，不再硬编码或外推。
- eligible positive 的 invalid 在 hit/recall/coverage 上记 0；原始 invalid 状态和 strict denominator 保留。
- positive 且 evidence sufficiency 为 `yes/partial` 的最终标签必须同时有非空 minimal-evidence 与 repair-packet；否则 freeze/score 拒绝。
- 每份原始标注、裁决结果和 legacy source record 都强制 `minimal evidence ⊆ repair packet`。

这些指标刻画覆盖与审阅负担，不等同 evidence precision、安全性或真实风险 prevalence。

## IAA 约定

- case categorical：unanimous rate、平均 pairwise raw agreement、pairwise Cohen kappa、Krippendorff nominal alpha、Gwet AC1；AC1 使用各字段预先固定的完整类别全集，未观测类别保留零计数；
- section role：把 `case × section` 作为 unit，三专家作为 rater；
- minimal evidence / repair packet：同时报告全 case Jaccard（双方空集按 1）和 eligible-conditional Jaccard（排除 union 为空的 pair/case），并给出各自分母；
- IAA 只针对本轮独立盲标 42，不把复用旧 12 混入。

## 测试

```bash
cd 2026NAACL/SA-MCGS/annotation_prep/analysis_v1
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_annotation_analysis.py
```

测试 fixture 中所有内容均为合成数据，见 `fixtures/SYNTHETIC_NOTICE.md`。43 个测试覆盖原有 33 项 source-bound／裁决／冻结闭环，以及新二选一协议的分母、集合约束、单例质量指标、缺省角色处理和 JSON/XLSX 模式门禁。测试只在临时目录或内存中操作合成标签，不输出论文结果。

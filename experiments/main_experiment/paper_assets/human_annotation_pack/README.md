# Human Annotation Pack / 人工标注包

目的：让领域专家快速审阅少量精选 critical SCC case，判断结构性风险和风险子图是否合理。

包含文件：

- `annotation_interface.html`：专家使用的主入口。可切换中英文、弹窗查看节点文本、直接填写标注并导出 Excel。
- `human_annotation_cases.csv`：专家小样本 manifest。
- `materials/*.md` / `materials/*.json`：每个入选 case 的备查素材。
- `vendor/xlsx.full.min.js`：本地 Excel 导出依赖，已打进 zip，打开 HTML 不需要联网。
- `full_candidate_manifest_not_for_experts.csv`：完整候选清单，只供内部追溯，不建议发给专家。

专家需要填写：

- `label_is_structural_conflict`：是否确实存在结构性风险。
- `label_relevant_risk_nodes`：专家认为应纳入风险子图的节点。
- `label_core_is_sufficient_for_repair`：SA core 是否足够作为修复入口。
- `label_confidence_1_to_5`：标注信心。
- `label_comments`：自由说明或缺失节点。

当前专家包包含 `12` 个精选 case，每个领域约 `3` 个；不是全量 80-case 主实验。

注意：当前包使用主实验锁定口径生成，不包含旧 diagnostic / smoke / balanced exploratory 数据。

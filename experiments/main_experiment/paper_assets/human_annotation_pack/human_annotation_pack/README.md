# Human Annotation Pack / 人工标注包

目的：让领域专家快速审阅 critical SCC case，判断结构性风险和风险子图是否合理。

包含文件：

- `human_annotation_cases.csv`：可直接发给标注者或导入表格工具。
- `annotation_interface.html`：双语切换的本地前端标注浏览页面。
- `materials/*.md`：每个 case 的可读卡片。
- `materials/*.json`：每个 case 的结构化素材。

建议标注列：

- `label_is_structural_conflict`：是否确实存在结构性风险。
- `label_relevant_risk_nodes`：专家认为应纳入风险子图的节点。
- `label_core_is_sufficient_for_repair`：SA core 是否足够作为修复入口。
- `label_comments`：自由说明。

注意：当前包使用主实验锁定口径生成，不包含旧 diagnostic / smoke / balanced exploratory 数据。

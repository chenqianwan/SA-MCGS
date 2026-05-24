# Human Annotation Pack / 人工标注包

目的：让领域专家像阅读长合同、公司披露或法条材料一样，逐段判断哪些文本存在冲突、哪些文本应保留给后续修复。

包含文件：

- `annotation_interface.html`：专家使用的主入口。打开后直接看到完整长文本，可在每段旁边打标，并一键导出 Excel。
- `expert_case_index.csv`：专家可读的小样本清单，只包含文本类型、段落数和冲突类型。
- `vendor/xlsx.full.min.js`：本地 Excel 导出依赖，已打进 zip，打开 HTML 不需要联网。
- `human_annotation_cases.csv`、`materials/` 和 `full_candidate_manifest_not_for_experts.csv`：只保留在本地目录供内部追溯，不打进专家 zip。

专家需要填写：

- 每一段文字：有明显问题 / 可能有关 / 没看出问题 / 不确定。
- 每一段文字：是否应放进最终修复材料。
- 整组文字：是否存在真实冲突、勾选材料是否足够修复、是否需要更多上下文、标注信心和备注。

当前专家包包含 `12` 个精选 case：SEC EX-21、BGB、CUAD 各 4 个。Debian 软件依赖样本不放入专家包，由项目内部单独标注。

页面内置 `专家 1/2/3` 三个独立标注槽位。每个样本需要三位专家分别标一次；导出 Excel 时会按专家展开。

注意：当前包使用主实验锁定口径生成，不包含旧 diagnostic / smoke / balanced exploratory 数据。

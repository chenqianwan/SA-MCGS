# 36-Post 候选集冻结说明

## 结果

- 从 locked 80-case 主实验中只取法律领域的 72 个 post variants；不读取任何方法得分或输赢字段。
- 最终冻结 36 个 post cases：SEC EX-21、BGB、CUAD 各 12 个；四种 template 各 9 个；每个 domain × template 单元格均为 3 个。
- 保留旧 expert audit 的全部 12 个 post cases；其余 24 个由预先声明的结构约束和固定 SHA-256 tie seed 选出。
- 36 个 post 映射到 **U=18** 个 unmodified pre source SCC；覆盖 locked 法律池的全部 18 个 source physical SCC，因此 source breadth 已达可实现上限。
- Size bins（9–11 / 12–19 / 20+ nodes）为 **13 / 12 / 11**。在“保留旧 12 + 全覆盖 18 sources + domain/template 精确平衡”约束下，本选择最小化了相对 12/12/12 的平方偏差。

## 身份口径

`source_physical_fingerprint` 只哈希 `domain + dataset_revision + sorted source clause IDs + typed internal edges`，明确排除 injection metadata、Tarjan `scc_id` 和注入后文本。它将 72 个法律 post variants 正确折叠为 18 个 source SCC，并将旧 12 个 cases 折叠为 7 个 source SCC。

`pre_sources_18.json` 是从原始 SEC/BGB/CUAD graph loader 重新读取的未注入文本和内部边。生成时逐个验证其 clause set 和 internal-edge signature 与 locked plan 一致；`pre_content_fingerprint` 再对实际原文内容进行固定。

## 文件

- `selected_post_36.csv`：便于人工核对的冻结清单。
- `selected_post_36.json`：前端/实验脚本使用的完整 post manifest。
- `pre_sources_18.csv`：18 个 source pre SCC 的概要映射。
- `pre_sources_18.json`：未注入 pre 文本、节点和内部边。
- `post_materials_36_internal.json`：按冻结注入规则重建的 36 个 post 纯文本材料；旧 12 个逐节点文本已与旧专家包精确核对。
- `master_manifest.json`：前端消费入口；本轮只筛选 `annotation_action=new_annotation`，内部 pre/post 映射与复用状态保留在该文件中。
- `selection_validation.json`：平衡、复用、U、hash 与验证证明。
- `select_candidates.py`：可复现生成脚本。

复现：在仓库根目录执行 `python 2026NAACL/SA-MCGS/annotation_prep/candidates/select_candidates.py`。

# 专家评估表格数据（2026-10-13）

按当前最终存在性标签：18例＝15有风险＋3无风险；充分性不作本表准入筛选。旧post Table 9不变。

## Table 10 最少字段

| 模型 | 方法／协议 | TP | TN | FP | FN | Invalid | 正确/18 | Accuracy |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| gpt-4o | One-shot, initial | 11 | 0 | 1 | 0 | 6 | 11/18 | 61.11% |
| gpt-4o | LEA, initial | 15 | 0 | 1 | 0 | 2 | 15/18 | 83.33% |
| gpt-4o | LEA, recovered | 15 | 0 | 2 | 0 | 1 | 15/18 | 83.33% |
| gpt-4o | SA-MCGS, initial | 8 | 0 | 0 | 0 | 10 | 8/18 | 44.44% |
| gpt-4o | SA-MCGS, recovered | 15 | 0 | 0 | 0 | 3 | 15/18 | 83.33% |
| gemini-2.5-pro | One-shot, initial | 15 | 0 | 3 | 0 | 0 | 15/18 | 83.33% |
| gemini-2.5-pro | LEA, initial | 14 | 0 | 3 | 1 | 0 | 14/18 | 77.78% |
| gemini-2.5-pro | SA-MCGS, initial | 4 | 0 | 0 | 0 | 14 | 4/18 | 22.22% |
| gemini-2.5-pro | SA-MCGS, recovered | 15 | 0 | 3 | 0 | 0 | 15/18 | 83.33% |
| gpt-4o | SA-MCGS, final verified | 15 | 3 | 0 | 0 | 0 | 18/18 | 100.00% |
| gemini-2.5-pro | SA-MCGS, final verified | 15 | 0 | 3 | 0 | 0 | 15/18 | 83.33% |

Accuracy=(TP+TN)/18；invalid计为错误，但单列，不能改记TN或FN。

最后两行与历史初始／恢复行分组。GPT final verified的3个TN（PRE-09/11/16）来自已核实的SA无风险判定；原模型文件仍为invalid，无新API调用。Gemini final verified与历史恢复判定相同。

最终SA-MCGS结果：GPT-4o总错误率0.00%、无风险子集虚警率0/3＝0.00%；Gemini 2.5 Pro总错误率3/18＝16.67%、无风险子集虚警率3/3＝100.00%。

## 当前原始投票IAA

| Pair | Scope | N | Existence agree | κ | Sufficiency agree | κ | Joint agree |
|---|---|---:|---:|---:|---:|---:|---:|
| expert_1/expert_2 | pre | 18 | 15/18 | 0.620 | 13/18 | 0.118 | 11/18 |
| expert_1/expert_2 | post | 24 | 24/24 | undefined | 24/24 | undefined | 24/24 |
| expert_1/expert_2 | all | 42 | 39/42 | 0.690 | 37/42 | 0.222 | 35/42 |
| expert_1/expert_3 | pre | 5 | 4/5 | 0.000 | 5/5 | 1.000 | 4/5 |
| expert_1/expert_3 | post | 5 | 5/5 | undefined | 5/5 | undefined | 5/5 |
| expert_1/expert_3 | all | 10 | 9/10 | 0.000 | 10/10 | 1.000 | 9/10 |
| expert_2/expert_3 | pre | 5 | 3/5 | 0.286 | 4/5 | 0.000 | 3/5 |
| expert_2/expert_3 | post | 5 | 5/5 | undefined | 5/5 | undefined | 5/5 |
| expert_2/expert_3 | all | 10 | 8/10 | 0.412 | 9/10 | 0.000 | 8/10 |

E1/E2新pre各18票＋旧post各24票；E3新pre5票＋旧post5票，共94份完整原票。E3只代表定向子集，all混合两个标注轮次，正文优先分层报告。

IAA由当前source_exports和integrated_annotations中的原始投票计算，专家最终标签由current_expert_final_decisions提供。PRE-05/18的最终存在性裁决不增加完整原票或改变证据集。转审阈值为confidence<3；旧post既有裁决及选样来源保持不变。

所有9组历史结果和2组final verified结果均由逐例记录重算。当前源文件SHA已核验，模型预测及日志SHA与此前一致；逐例分类、原始投票IAA、来源SHA和旧post表9冻结SHA保存在同名JSON中。
JSON schema：pre18_manuscript_tables.v1；主要字段final_existence_labels、third_review_policy、table10（historical_rows/final_verified_sa_rows及逐例明细）、agreement、unchanged_post_table9、provenance。

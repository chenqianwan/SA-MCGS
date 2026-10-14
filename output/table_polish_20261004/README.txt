SA-MCGS 表格统一润色版 | 2026-10-04 | ACL 重点表格浅蓝强调版

本包是独立审阅副本，基于 2026-10-02 的修订包；没有覆盖主线程的论文。
结合 nature-writing / nature-figure 的清晰表达和信息层次原则，保留 ARR/ACL 模板；本轮保留白底，并参考顶会论文中对方法行的克制强调方式，仅为重要比较表增加浅蓝底色。

本次完成
- 正文与附录全部 19 张表：白底表头、统一三线表与分组间距。
- Table 2、4、9、14、18：共 24 条 SA-MCGS 行使用浅蓝底色 #EDF4FA，并加粗方法名称。其余表保持白底。
- 底色只标识方法，不表示最佳或显著性；各表表题已有说明。非领先指标和较高成本仍同等着色。
- 表头和分组标题保持白底；用横线、留白、加粗分组标题区分模型或实验组。
- 所有表题及其标签均置于表格下方，遵循 ACL 的表题位置规范。
- 可比较结果：最佳粗体、次佳下划线。并列同等标记；次佳指第二个不同数值。
- 准确率/覆盖率越高越好；成本越低越好；只在同一模型或同一实验组内比较。
- 主结果与分组结果保留压缩率的高值标记，明确高压缩仅表示核心更小；消融和成本明细的压缩率、核心大小作为描述量。
- 参数、标注协议、专家一致性、负样本审计表不强行排名。专家参考质量表只标点估计，不标置信区间端点。
- 附录汇总表从 7.5 pt 左右并排改成 9 pt 上下三个面板。
- 所有数据、置信区间、样本量与表外正文均保留。修改限于表格版式、表头/图例说明和精简表题。

阅读与编译
- SA_MCGS_tables_polished.pdf：统一表格后的完整清稿。
- source/main.tex：Overleaf 主文件，选择 XeLaTeX。所有图、参考文献和样式均已打包。
- source/table_style.tex：浅蓝强调色、粗体、下划线及文本列的公共定义。
- marked.tex 保留已有正文修订显示入口；本次表格样式不是逐字红线稿。
- tables_only.patch：仅本次表格相关差异，供后续合并审阅；尚未应用至主稿。

验证
- 19 张表、846 个数据单元格、356 个参与排名的数值已核对；文字与数值保持一致。
- 已重新编译并目视检查本轮变化的第 7、8、16、22、27 页；其余表格沿用上一版检查结果。无表格溢出、未定义引用或过大浮动体。
- 清稿共 28 页，含参考文献与附录；Conclusion 的最后一句完整位于第 8 页。
- 未改变正文的字号、页边距或官方 ACL 样式文件。

表格页码
Table 1: page 3 (tab:mcts_scc)
Table 2: page 7 (tab:matched_main)
Table 3: page 7 (tab:component_main)
Table 4: page 7 (tab:cost_main)
Table 5: page 13 (tab:expert_audit_results)
Table 6: page 14 (tab:expert_protocol)
Table 7: page 14 (tab:expert_example)
Table 8: page 14 (tab:expert_new_agreement)
Table 9: page 16 (tab:expert_new_quality)
Table 10: page 16 (tab:expert_pre_negative)
Table 11: page 18 (tab:prior_coefficients)
Table 12: page 21 (tab:dataset_processing)
Table 13: page 21 (tab:injection_templates)
Table 14: page 22 (tab:appendix_breakdowns)
Table 15: page 26 (tab:revision_stage1)
Table 16: page 26 (tab:revision_stage1_cost)
Table 17: page 26 (tab:revision_stage2)
Table 18: page 27 (tab:revision_cost_full)
Table 19: page 27 (tab:revision_prior)

本轮参考
- ACL 官方格式（表题位于下方，颜色需兼顾灰度阅读）：https://acl-org.github.io/ACLPUB/formatting.html#figures-and-tables
- ACL 2025 Taming LLMs with Gradient Grouping（以浅蓝强调方法行的已发表实例）：https://aclanthology.org/2025.acl-long.164.pdf
颜色强调是排版选择，不是顶会统一强制要求。

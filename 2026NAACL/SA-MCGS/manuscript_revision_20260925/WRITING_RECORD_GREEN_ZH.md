# 论文绿色修订记录（2026-09-25）

已按最新逐项清单完成论文更新。主表使用已确认的五模型 × 三方法结果，正文、摘要、结论及附录同步采用根因定位、完整风险证据与子图压缩的主线。

- 本轮新增、改写内容使用绿色；被替换的旧蓝字直接移除；原黑字使用删除线保留。未改动的旧蓝字继续保留。
- 更新主表与模型／领域／规模附表；更新四张图：五模型规模分析、覆盖率与压缩率对比、预算曲线、同一案例的三方法比较。
- 主表 60 个指标值与已确认列表一致；原始黑字还原后的规范化文本完全一致。
- 预算图依据已保存的轨迹离线重建，80/80 个最终 core 与主结果一致；本轮没有新模型调用。
- 修订版 27 页，净稿 24 页；检查了全部页面，未发现越界、未解析引用或重复标签。简洁清单同步标记完成，共 3 页。

## 文件

- [论文源码](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex)
- [绿色修订版](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.pdf)
- [净稿](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex_clean.pdf)
- [逐项清单](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20260922/CHANGE_LIST_ZH.md)
- [简洁清单 PDF](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20260925/output/pdf/CHANGE_LIST_BLUE.pdf)
- [最终验证记录](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20260925/green_manuscript_completion.json)
- [本轮修改前备份清单](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20260925/latex_before_green_manifest.json)

## 编译与检查

在 `paper/latex` 目录分别运行 `tectonic --only-cached --keep-logs acl_latex.tex` 和 `tectonic --only-cached --keep-logs acl_latex_clean.tex`。绿色修订核验脚本为同目录记录区的 `audit_green_revision.py`；图表数据与来源校验保存在 `experiments/main_experiment/paper_assets`。

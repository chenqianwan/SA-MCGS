from pathlib import Path
import json, hashlib, re, math
base=Path('/Users/chenlong/WorkSpace/MCGS_Law'); out=base/'tmp/crossref_audit_20261001/assets'; F='paper/latex/acl_latex.tex'
figs=[
(1,'fig:pipeline',3,F,93,'fig01_sa_mcgs_framework_architecture_figma.png','正文 §1','流水线四阶段与当前图一致；图中文字 Relation-aware memory 与正文 Relation-first evidence memory 用词不完全统一，属于术语层面的旧资产残留，并非引用错位。'),
(2,'fig:mcts_failure',3,F,135,'fig02_vanilla_mcts_scc_failure_figma.png','正文 §3.1','三面板拓扑示意；6.4×/100%/0.044 与 1.0×/0.371/90% 和 Table 1 一致。'),
(3,'fig:paired_case_outcomes',8,F,341,'fig03_paired_case_outcomes_five_models.pdf','正文 §5','a=One-shot、b=LEA，四类颜色与 caption 完全相符；5×2 个条形均合计 80；每个净增益与 Table 2 相符。'),
(4,'fig:case',15,F,538,'fig06_representative_scc_three_methods.pdf','附录 C','固定 25 节点；root §505、witness §491；保留 3/12/9，压缩 88/52/64，caption 与正文一致。'),
(5,'fig:main_metrics',21,F,850,'fig02_scale_gain_heatmaps.pdf','附录 J.1','a=Root@3、b=Risk-all；每模型 36/24/20；蓝正橙负、±65 共享色标；正文 37.50/62.50 pp 对应 medium 的正确单元格。'),
(6,'fig:absolute_size_breakdowns',22,F,859,'fig02_main_results_five_models.pdf','附录 J.1','5 列模型、2 行指标 a/b；灰圆/橙方/蓝三角与 caption 相符；36/24/20 案例组对应 Figure 5。'),
(7,'fig:convergence',23,F,874,'fig04_budget_prefix_three_methods.pdf','附录 J.2','a=Risk-all、b=Compression；曲线与水平基线语义相符；终点 75.00/51.26 与 Table 2 一致。')]
tables=[
(1,'tab:mcts_scc',3,F,145,'正文 §3.1','DAG/SCC 对照；caption 与表内容一致。'),
(2,'tab:matched_main',7,'paper/latex/revision_main_results.tex',4,'正文 §5','5 模型 × 3 方法，四百分数指标；加粗最大值含并列准确。'),
(3,'tab:component_main',7,'paper/latex/revision_main_analysis.tex',7,'正文 §6.3','17 例 Stage-1 与 80 例 Stage-2 明确分开；与附录 Tables 15/17 对应。'),
(4,'tab:cost_main',7,'paper/latex/revision_main_analysis.tex',32,'正文 §6.4','12 来源 ×2 模型 ×3 方法；Calls/Tokens 与 Table 18 汇总一致。'),
(5,'tab:expert_audit_results',13,F,470,'附录 B.1','原始 12 例、36 判断、24 endpoints；表文一致。'),
(6,'tab:expert_protocol',13,F,497,'附录 B.1','三类标注任务与 caption 一致；无显式文本 callout。'),
(7,'tab:expert_example',14,F,514,'附录 B.1','caption 中 Role names in the left column 与实际 A/B/Case-level 左列不符，应修正。'),
(8,'tab:expert_new_agreement',14,'paper/latex/revision_expert_appendix.tex',16,'附录 B.2','E1/E2 n42、第三标注员配对 n14，分母和判断列相符。'),
(9,'tab:expert_new_quality',15,'paper/latex/revision_expert_appendix.tex',46,'附录 B.2','24 例/14 来源；6 模型-方法行、有效计数和区间与说明一致。'),
(10,'tab:expert_pre_negative',16,'paper/latex/revision_expert_appendix.tex',73,'附录 B.2','所有行 FP+Abs+Inv=18；initial/recovered 清楚对应。'),
(11,'tab:prior_coefficients',18,F,697,'附录 F','node/edge/pair 三组权重与 caption 一致；内含 Eq. 引用待 equation 审核员核对。'),
(12,'tab:dataset_processing / tab:domains',19,F,783,'附录 I','4 域 Why selected/Graph construction/Role 与新合并 caption 一致；两个标签同指一表是有意保留 alias。'),
(13,'tab:injection_templates',19,F,808,'附录 I','4 注入模板，root/witness/风险列对应；无显式文本 callout。'),
(14,'tab:appendix_breakdowns',20,'experiments/main_experiment/paper_assets/tables/five_model_appendix_breakdowns.tex',1,'附录 J','A 模型 / B 域 / C 大小，N 与表内汇总相符；A 与 Table 2 数值完全相同。'),
(15,'tab:revision_stage1',22,'paper/latex/revision_experiments.tex',40,'附录 K.2','A 当批 17/5；B 描述性跨批 80/20；caption 正确区分。'),
(16,'tab:revision_stage1_cost',22,'paper/latex/revision_experiments.tex',67,'附录 K.2','Calls/Tokens/USD 总数，time 每例均值；caption 与表头一致。'),
(17,'tab:revision_stage2',22,'paper/latex/revision_experiments.tex',92,'附录 K.3','Dynamic/Locked，同 Root@3、同核心大小，caption 正确。'),
(18,'tab:revision_cost_full',23,'paper/latex/revision_experiments.tex',115,'附录 K.4','上下两部分结果与用量；单元格分母/单位与 caption 对应。'),
(19,'tab:revision_prior',24,'paper/latex/revision_experiments.tex',168,'附录 K.5','两模型两指标、0.68/0.85/1.02 三条件；caption 与表相符。')]
algs=[(1,'alg:samcgs',5,241,'正文 §3.6'),(2,'alg:appendix_scc_localized',16,552,'附录 D'),(3,'alg:appendix_rollout',16,573,'附录 D'),(4,'alg:appendix_relation_memory',16,592,'附录 D'),(5,'alg:appendix_dynamic_core',17,615,'附录 D')]
pairedA=[[49,11,1,19],[11,56,12,1],[51,9,2,18],[29,10,10,31],[42,9,2,27]]
pairedB=[[32,28,7,13],[8,59,8,5],[33,27,8,12],[21,18,10,31],[12,39,12,17]]
mainSA=[75,83.75,75,48.75,63.75]; mainOne=[15,85,13.75,25,13.75]; mainLEA=[43.75,83.75,43.75,35,63.75]
for rows,baseMetrics in [(pairedA,mainOne),(pairedB,mainLEA)]:
 for row,sa,bl in zip(rows,mainSA,baseMetrics):
  assert sum(row)==80
  assert math.isclose((row[0]+row[1])/80*100,sa)
  assert math.isclose((row[1]+row[2])/80*100,bl)
  assert math.isclose((row[0]-row[2])/80*100,sa-bl)
main=(base/'paper/latex/revision_main_results.tex').read_text().split('\\end{table*}')[0]
app=(base/'experiments/main_experiment/paper_assets/tables/five_model_appendix_breakdowns.tex').read_text().split('\\textbf{B. Domains}')[0]
num=lambda s:[[float(x) for x in re.findall(r'(?<![A-Za-z])\b\d+\.\d+\b',l.split('&',2)[-1])] for l in s.splitlines() if '&' in l and re.search(r'\d+\.\d+',l)]
assert num(main)==num(app)
obj={'pdf_sha256':hashlib.sha256((base/'paper/latex/acl_latex_clean.pdf').read_bytes()).hexdigest(),'figures':figs,'tables':tables,'algorithms':algs,'checks':{'paired_case_totals_and_main_scores':'PASS, 10 bars','main_vs_appendix_model_rows':'PASS, 15 rows'},'findings':[{'severity':'fix','file':F,'line':527,'issue':'Table 7 caption claims role names in left column, but no such role names are displayed.','suggestion':'Representative expert-audit example. Annotators saw paragraph text and identifiers, without hidden root/witness labels or system suggestions.'},{'severity':'navigation','file':F,'line':511,'issue':'Table 6 has no explicit in-text reference.'},{'severity':'navigation','file':F,'line':823,'issue':'Table 13 has no explicit in-text reference.'},{'severity':'navigation','file':F,'line':244,'issue':'Algorithms 1–5 have no explicit in-text references.'},{'severity':'terminology_asset','file':'experiments/main_experiment/paper_assets/figures/fig01_sa_mcgs_framework_architecture_figma.png','line':None,'issue':'Figure 1 says Relation-aware memory; manuscript and Figure 2 say relation-first evidence memory. Same module, not cross-reference wrong target.'}]}
(out/'inventory.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
lines=['# 图、表、算法与实际资产核对（只读独立复核）','','核对对象：2026-10-01 当前净稿，24 页；7 图、19 表、5 算法。以下页码是本次核对时 PDF 的实际页码，逻辑归属按源文件环境所在章节。后续主代理修复可能改变分页。','','## 明确发现','','1. **Table 7 caption 残留旧描述**：`paper/latex/acl_latex.tex:527` 说左列为解释加入 role names，但实际左列只有 SEC EX-21 entity record A、B 和 Case-level decision。建议保留匿名化标注说明，删除不实的“role names in the left column”。','2. **导航缺失**：Table 6、Table 13 和 Algorithms 1–5 均已有正确编号与 label，但没有显式文本引用；并非指向错误，可在相关段落补短 callout。','3. **非引用错位，仅术语提醒**：Figure 1 图内仍写 Relation-aware memory，caption、正文和 Figure 2 写 Relation-first evidence memory。两者指同一模块；不建议借此次 cross-reference 审核擅自改已确认示意图。','','## 图清单','','| 图 | 标签 | 实际页 | 逻辑位置 | 源位置 | 核对 |','|---|---|---:|---|---|---|']
for n,label,p,f,line,asset,section,result in figs:lines.append(f'| Figure {n} | `{label}` | {p} | {section} | `{f}:{line}` | {result} |')
lines+=['','## 表清单','','| 表 | 标签 | 实际页 | 逻辑位置 | 源位置 | 核对 |','|---|---|---:|---|---|---|']
for n,label,p,f,line,section,result in tables:lines.append(f'| Table {n} | `{label}` | {p} | {section} | `{f}:{line}` | {result} |')
lines+=['','## 算法清单','','| 算法 | 标签 | 实际页 | 源位置 | 状态 |','|---|---|---:|---|---|']
for n,label,p,line,section in algs:lines.append(f'| Algorithm {n} | `{label}` | {p} | `{F}:{line}` | {section}；标题与伪代码功能一致，缺显式 callout |')
lines+=['','## 数值与资产一致性复核','','- Figure 3 的 10 个条形四类计数均合计 80；SA-only + both 恢复对应 SA-MCGS Risk-all；baseline-only + both 恢复对应基线 Risk-all；净增益均与 Table 2 一致。','- Figure 4 的 3/25、12/25、9/25 与 88%、52%、64% 压缩率对应；两个 diamond 确为 §505 和 §491。','- Figure 5 的大小组样本数与 Figure 6、Table 14 相容；GPT-4o 和 Qwen2.5 medium Risk-all 增益 37.50 和 62.50 pp 与文字相符。','- Figure 7 的最终 75.00% Risk-all、51.26% compression 与 Table 2 相同；此图已位于附录 J.2 的源环境，实际因 LaTeX 浮动出现在第 23 页。','- Table 2 和 Table 14 Panel A 的全部 15 行四指标逐行数字比较通过。','- Figure 1/2 PNG 及 Figure 3–7 PDF 均打开检查；所有图中面板字母、方法、符号和 caption 相符。','- 文件名的 fig02/fig03/fig04 不是论文编号；论文通过 label/ref 自动编号，旧资产文件名前缀不构成错误。','- 软删除段落中的历史 Figure 5B / old oracle controls 不是净稿有效表述，不能据此误判现行 figure 引用。','','## 物理浮动位置','','Figure 5、6、7 的逻辑章节为附录 J.1、J.1、J.2，实际落在第 21、22、23 页，其中正文流已经进入 K。Labels 正确、编号解析正确；这是浮动排版，不是移错章节。若最终要追求严格章节内视觉归属，可单独调整 appendix float barriers，但不应当作为错误编号修复。','']
(out/'ASSET_AUDIT_ZH.md').write_text('\n'.join(lines))
print('saved',out/'ASSET_AUDIT_ZH.md')

from pathlib import Path
import json,re,unicodedata
from collections import Counter

P=Path(__file__).resolve().parent;ROOT=P.parents[1]
DEST=ROOT/'2026NAACL/SA-MCGS/manuscript_revision_20261001'
data=json.loads((P/'full_audit.json').read_text())
qa=json.loads((P/'final_verification.json').read_text())
links=json.loads((P/'link_checks.json').read_text())
bbl=(P/'clean_build/acl_latex_clean.bbl').read_text()
order=re.findall(r'\\bibitem\[.*?\]\{([^}]+)\}',bbl,re.S)
unused=sorted(k for k,x in data.items() if not x['cited_in_pdf'])

def clean(t):
    s=str(t).replace('{','').replace('}','').replace('---','—').replace('--','–')
    accents={"'":'\u0301','`':'\u0300','\"':'\u0308','^':'\u0302','~':'\u0303'}
    return re.sub(r"\\([\"'`^~])([A-Za-z])",lambda m:unicodedata.normalize('NFC',m[2]+accents[m[1]]),s)
def status(x):
    if x.get('errors'):return '已修正'
    if x['field_changes'] or x['type_change']:return '核心信息正确；已补全'
    return '通过；保留'
def reason(x):
    if x.get('errors'):return '；'.join(x['errors'])
    if x['field_changes'] or x['type_change']:
        names={'url':'来源链接','doi':'DOI','pages':'页码','volume':'卷号','publisher':'出版方','booktitle':'正式会议名称','journal':'文献类型','year':'年份','author':'作者','title':'题名'}
        return '补全或规范：'+ '、'.join(names.get(k,k) for k in x['field_changes'])
    return '作者、标题、年、出处及标识相符。'
def source_links(x):
    return '、'.join(f'[来源 {i+1}]({u})' for i,u in enumerate(x['primary_urls']))

out=['# 全文参考文献核对：完整 citation list', '',
'核对日期：2026-10-01。对象为本轮修订后的实际净稿，而不只限于新加的模型引用。', '',
'**结论：原参考文献列表并非全部正确。当前正式列表的 41 条均已核对，其中 12 条存在需要修正的书目信息、作者记录或版本归属问题，17 条主要补齐可验证的出版字段／定位信息，12 条保留原条目。未发现整条凭空捏造的文献，但发现了错误作者、无效 DOI、错误会议归属和预印本／正式版信息拼接。已把确认的修正落实到稿件。**', '',
'另检查 `.bib` 中 8 条未引用条目：它们不进入当前论文参考文献表。本次修复了其中的作者记录、专著类型，并补全定位信息，没有为了保留它们而增加正文引用。', '',
'## 1. 优先看这些实际问题', '',
'| 文献 | 原问题 | 已落实 |', '|---|---|---|',
'| Measuring Law Over Time | 作者名单混入 Boulet、Music，漏 Beckedorf，首作者错误 | 按出版商全文改为 Coupette、Beckedorf 等五人；正文作者—年份引用自动同步 |',
'| SARA：A Dataset for Statutory Reasoning… | 错标 ACL 出版；所填 ACL DOI 不存在 | 改为 CEUR Workshop Proceedings 2645，31–38 页，链接正式 PDF |',
'| The Second Type of Uncertainty in MCTS | 所填 IJCAI 2020 和 2388–2394 页不属于该文 | 恢复可核实的 arXiv:2005.09645 身份，不虚构正式会议 |',
'| Czech et al. 2021 | 将预印本标题拼接到 ICAPS 正式记录 | 正式标题改为 Improving AlphaZero Using Monte-Carlo Graph Search |',
'| Tree of Thoughts | NeurIPS 36 的年份误写为 2024 | 改为 2023；补齐正式卷页和 DOI |',
'| Battaglia / Silver 2016 / LegalBench | 手写 `and others` 被 ACL 样式计为一个作者，省略人数错误 | 分别存全 27／20／40 位作者，让官方样式自行截断 |',
'| 两条 Debian Policy 引文 | 作者字段填成书名；动态网页版本已偏离声明的 4.7.2.0 | 按该版本文档实际署名修改作者，固定到官方 4.7.2.0 Git 标签；保留 2025 |',
'| Berger–Shor 1990 | `10.5555/320176.320203` 经 DOI 与 Handle 查询均未注册 | 删除无效 DOI 字段，保留 ACM 目录 URL；不换成题名不同的 1997 期刊版 |',
'| Nemhauser et al. 1978 | 完整题名漏了结尾的 Part I | 补回 “—I”，其他书目字段保留 |', '',
'以上按条目计为 12 条；一个条目同时有多个问题仍只计一次。补页码或加链接不计为“错引”。完整作者由正式 PDF 和作者顺序核实，未机械照搬存在拆名、缩名或漏名的导出文件。', '',
'## 2. 两处引用语境的最小修正', '',
'### §3.6：经典次模保证与本文启发式实现', '',
'原句：', '',
'> Core compression is cast as budgeted subset selection, for which greedy selection is a standard approximation strategy under monotone submodular objectives with cardinality constraints.', '',
'改为：', '',
'> Classical greedy guarantees apply to monotone submodular objectives under cardinality constraints. We use greedy replacement as a heuristic for the relation-aware utility below.', '',
'保留 Nemhauser 引文。原文献确实证明了特定条件下的贪心近似界；但本文目标中的正向成对关系奖励具有互补性，不能直接继承该保证。例如，将 v 加入空集合和加入已有 u 的集合，后者多得到 ηm(u,v) 的边奖励，与次模边际递减相反。此次仅把引用范围写清楚，没有改公式、实现或结果。[原论文及其条件](https://link.springer.com/article/10.1007/BF01588971)。', '',
'### 附录 A：循环与 rollout 截断', '',
'把 “which is common in loops” 改为 “loops can prevent termination”，保留 Moerland 引文。论文 §4.2 直接讨论循环妨碍终止；原句对“常见”程度的概括没有必要。原黑字在修订版中软删除，新句标红。', '',
'## 3. 正式参考文献列表：41 条逐条总表', '',
'顺序遵循修正后净稿的 References；key 保留原名以避免无关改动，因此内部 `yao2024tree`／`boulet2021measuring` 不代表最终显示的年份／首作者。', '',
'| # | 文献 | 结论 | 处理与依据 |', '|---|---|---|---|']
for i,k in enumerate(order,1):
    x=data[k];f=x['final_metadata']
    out.append(f'| {i} | {clean(f["title"])} ({f["year"]}) | {status(x)} | {reason(x)} [核对来源]({x["primary_urls"][0]}) |')
out+=['','## 4. 逐条字段、正文用途和来源记录','',
'每条均核对作者及顺序、完整题名、年份、发表类型／渠道、适用的卷期页码、DOI／URL，以及在当前正文中的用途。没有 DOI 的材料使用可验证的正式出处，不猜填标识。', '']
for i,k in enumerate(order,1):
    x=data[k];f=x['final_metadata']
    out += [f'### {i:02d}. {clean(f["title"])}','', f'引用键：`{k}`。结论：**{status(x)}**。','',
            '| 字段 | 核对后的记录 |','|---|---|',f'| 作者（完整、按顺序） | {clean(f["author"])} |',
            f'| 年份／类型 | {f["year"]}；`{x["final_entry_type"]}` |']
    for field,label in [('booktitle','会议'),('journal','期刊／存档'),('publisher','出版方'),('series','系列'),('volume','卷号'),('number','期号'),('pages','页码／文章号'),('doi','DOI'),('url','最终链接'),('note','版本说明')]:
        if field in f:out.append(f'| {label} | {clean(f[field])} |')
    out+=['', '**正文支持性：**'+x['support'], '', '**本次处理：**'+reason(x)]
    if x.get('metadata_notes'):out+=['',x['metadata_notes']]
    if x.get('enhancements'):out+=['',' '.join(x['enhancements'])]
    loc=list(dict.fromkeys(Path(c['file']).name+':'+str(c['line']) for c in x['contexts']))
    out+=['','引用位置（审计开始时源文件行号）：'+ '、'.join('`'+v+'`' for v in loc)+'。', '',
          '核对依据：'+source_links(x)+'。','']
out+=['## 5. 未进入论文的 8 条库存文献','','这些条目不增加当前 PDF 的参考文献数量，也不承担当前正文的证据作用。','',
      '| 引用键 | 文献 | 核对结果／处理 | 依据 |','|---|---|---|---|']
for k in unused:
    x=data[k];f=x['final_metadata']
    out.append(f'| `{k}` | {clean(f["title"])} ({f["year"]}) | {reason(x)} {x.get("metadata_notes","")} | {source_links(x)} |')
out+=['','## 6. 没有误改的几个细节','',
'- **RAP**：Joshua Jiahua Hong、Daisy Zhe Wang 的完整姓名见正式 PDF；不因网页缩名而删去中间名。',
'- **ContractNLI／LexGLUE**：保留正式 PDF 的 Christopher D. Manning、Daniel Martin Katz。',
'- **RULER**：已核实原 arXiv 2024 版本的 8 位作者并补齐链接；不根据署名不一致、访问受限的会议元数据强行换版本。原引用本身成立。',
'- **GraphRAG（库存）**：8 位作者对应 2024 v1，链接固定到 v1；不拼接后来 10 位作者的版本。',
'- **Tarjan／Chaslot／Tolpin**：保留原论文出版年，网站迁移或后补上网的日期不充当论文年份。',
'- **五条模型出处**：复用同日已完成的原始报告／模型卡审计，确认条目之后没有变化；本轮保留。[此前完整报告](NEW_CITATION_AUDIT_ZH.md)。',
'- **ACL 作者截断**：未改官方 `.bst`。Battaglia 显示 19 名＋8 others，LegalBench 显示 19 名＋21 others；Silver 2016 共20人，最终 PDF 完整列出20人。清除的是手工占位导致的错误计数，不自行改写官方样式。',
'- **AAAI／ICAPS 卷期**：已核实原刊 issue；ACL 的 `inproceedings` 样式不接受 volume 与 number 同时输出，最终保留卷号与页码，避免模板警告。完整核实记录保存在 JSON。', '',
'## 7. 访问边界与链接实测','',
'对 41 条在用文献逐一测试最终 DOI 或 URL。27 条在本次请求直接返回 HTTP 200；其余14条出现出版商反爬、代理／TLS连接限制或 IEEE 的202响应，不能把这些情况写成“文献不存在”。已结合出版商登记、官方正文、作者原文或版本化源文件核对。两处真正无效的 DOI（SARA、Berger）均已移除。', '',
'Berger 1990 的 ACM 页面本轮仍受限；其论文存在、会议和页码由作者 Shor 的 MIT 发表列表及 Berger 本人另一篇 SIAM 论文中的题录交叉核实。这里明确区分“题录和引用用途可核”与“已经读到原篇全文”，不把前者包装成后者。', '',
'完整 HTTP 状态和最终跳转地址见 [链接检查记录](full_citation_audit/link_checks.json)。完整49条逐字段记录、正文引用上下文见 [机器可读审计清单](full_citation_audit/full_audit.json)。', '',
'## 8. 编译与交付核验','',
f'- 净稿 **{qa["clean"]["pages"]} 页**；Conclusion 在第 **{qa["clean"]["conclusion_page"]} 页**结束，主文仍在8页内。Limitations 现从第8页开始并延至第9页，References 从第9页开始。',
f'- 修订版 **{qa["marked"]["pages"]} 页**，包含正文修订痕迹和旧书目软删除；净稿不显示这些历史内容。',
'- 两版都只有 **41 个正式 bibliography item**，与正文／附录的 **70 次有效 citation 出现、41 个不同引用键**对应；8条库存未误入列表。',
'- 无未定义 citation／reference、无重复 label、无损坏内部链接。原77处图表／章节交叉引用仍可解析，净稿图表及算法编号不变。',
'- 净稿无 overfull 排版警告；修订版只保留此前贡献列表的约5.2pt提示，本轮新增书目无溢出。已视觉检查参考文献各页及正文末页。',
'- 29 条调整后的在用书目标红；18 条可见文字发生变化的旧书目在修订版黑色软删除。仅增加链接而未改变可见文字的条目不重复打印相同旧句。原有模型引用颜色保留。',
'- 实验数值、算法公式、模型集合、图表资产与官方 ACL bibliography 样式保持不变。', '',
'修改文件：[custom.bib](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/custom.bib)、[正文](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex)、[修订标记](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_markup.tex)、[书目旧文保留](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/revision_bibliography_audit.tex)。', '',
'完整构建核验：[final_verification.json](full_citation_audit/final_verification.json)。修改前文件与原始来源证据一并存档于 `full_citation_audit/`。','']
DEST.mkdir(parents=True,exist_ok=True)
report='\n'.join(out)
report=report.replace('](full_citation_audit/',']('+str(DEST/'full_citation_audit')+'/').replace('](NEW_CITATION_AUDIT_ZH.md)',']('+str(DEST/'NEW_CITATION_AUDIT_ZH.md')+')')
(DEST/'FULL_CITATION_AUDIT_ZH.md').write_text(report)
print(DEST/'FULL_CITATION_AUDIT_ZH.md')

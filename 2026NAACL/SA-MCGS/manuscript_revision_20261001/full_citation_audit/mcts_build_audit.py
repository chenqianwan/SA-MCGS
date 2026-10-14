from pathlib import Path
import json,re
root=Path('tmp/full_citation_audit_20261001'); original=Path('paper/latex/custom.bib').read_text()
blocks={m.group(2):m.group(0) for m in re.finditer(r'(?ms)^@(\w+)\{([^,]+),.*?^\}',original)}
keys=['silver2016mastering','kocsis2006bandit','browne2012survey','gelly2007combining','chaslot2008progressive','childs2008transpositions','kishimoto2004general','saffidine2012ucd','czech2021monte','moerland2020mcts','silver2017mastering','tolpin2012simple','hansen1996monitoring']
rows={}
for k in keys:
 fields={m.group(1):m.group(2) for m in re.finditer(r'(?m)^\s*(\w+)\s*=\s*\{(.*)\},?\s*$',blocks[k])}
 rows[k]={'key':k,'printed_in_current_pdf':k not in ['silver2017mastering','tolpin2012simple','hansen1996monitoring'],'status':'verified','errors':[],'completion':[],'primary_urls':[],'verified_metadata':fields,'support':'','checked_fields':['authors and order','title','year','venue/type','volume/issue if applicable','pages if applicable','DOI/URL'],'original_bib':blocks[k]}
def setrow(k,**kw):rows[k].update(kw)
def fields(k,**kw):rows[k]['verified_metadata'].update(kw)
setrow('silver2016mastering',status='correct_author_list',errors=['作者仅存前 10 人及手工 others；该论文实际有 20 位作者，ACL 样式把占位符错误计作 1 others。'],primary_urls=['https://www.nature.com/articles/nature16961','https://api.crossref.org/works/10.1038/nature16961','https://www.cs.cmu.edu/afs/cs.cmu.edu/academic/class/15780-s16/www/AlphaGo.nature16961.pdf'],support='支持 AlphaGo 将策略/价值网络与 Monte Carlo 搜索结合的论述；没有将其结果误写为本文实验。Nature 直连抓取存在访问跳转，题录以出版商 Crossref 登记及原文首页交叉确认。')
silver=json.loads((root/'mcts_sources/10.1038_nature16961.json').read_text())
fields('silver2016mastering',author=' and '.join(a['given']+' '+a['family'] for a in silver['author']))
setrow('kocsis2006bandit',primary_urls=['https://link.springer.com/chapter/10.1007/11871842_29','https://api.crossref.org/works/10.1007/11871842_29'],support='正式 ECML 2006 论文提出 UCT 并在有限时域/折扣 MDP 下给出一致性和有限样本结果；正文仅以 UCB intuition/UCT-style selection 引用，未将其理论保证直接转给本文新策略，使用恰当。')
setrow('browne2012survey',primary_urls=['https://repository.essex.ac.uk/4117/','https://repository.essex.ac.uk/4117/1/MCTS-Survey.pdf','https://api.crossref.org/works/10.1109/TCIAIG.2012.2186810'],support='原文综述确认四阶段 MCTS 流程、UCT、progressive bias、AMAF/RAVE 等；现有作者形式与出版商登记一致，无须按 DBLP 的后期姓名扩写另改。')
setrow('gelly2007combining',primary_urls=['https://dl.acm.org/doi/10.1145/1273496.1273531','https://www.davidsilver.uk/wp-content/uploads/2020/03/combining_uct.pdf','https://api.crossref.org/works/10.1145/1273496.1273531'],support='作者原文介绍快速在线动作价值估计与离线先验用于 UCT，支持正文 RAVE-style reuse 的类比。ACM HTML 受限，但作者原文在浏览索引中可读并与出版商元数据交叉核实。')
setrow('chaslot2008progressive',primary_urls=['https://cris.maastrichtuniversity.nl/en/publications/progressive-strategies-for-monte-carlo-tree-search/','https://project.dke.maastrichtuniversity.nl/games/files/articles/pMCTS.pdf','https://api.crossref.org/works/10.1142/S1793005708001094'],support='原文 Section 3.1 为 progressive bias，访问增多后启发式影响衰减，与正文类比吻合。期刊出版年 2008 正确；2011 是网上上线日期，不应改年份。5 作者顺序与期刊稿一致，不能采用 2007 同题会议版的作者顺序。')
setrow('childs2008transpositions',status='complete_identifier',completion=['补 DOI 10.1109/CIG.2008.5035667。'],primary_urls=['https://ieeexplore.ieee.org/document/5035667/','https://api.crossref.org/works/10.1109/CIG.2008.5035667','https://citeseerx.ist.psu.edu/document?doi=e7443565e965aae469d993e2fad6d0b202266213&repid=rep1&type=pdf'],support='论文原文第一页直接讨论 transpositions、cycles 和一个状态在同次模拟中多次出现，支持本文重复状态/图统计复用相关论述。IEEE 当前网页机器人拦截，但出版商登记和原论文可核。')
fields('childs2008transpositions',doi='10.1109/CIG.2008.5035667')
setrow('kishimoto2004general',status='complete_identifier',completion=['补 AAAI 原文稳定 URL。'],primary_urls=['https://s.aaai.org/Papers/AAAI/2004/AAAI04-102.pdf','https://webdocs.cs.ualberta.ca/~mmueller/ghi.html'],support='原文直接讨论在含环状态空间使用 transposition table 时的路径历史依赖及错误；现有正文将其列作 graph-history 问题来源，适合。AAAI 网页目录抬头误写 Eighteenth，但作者正式出版列表确认 Nineteenth/AAAI 2004，当前 booktitle 不需改。')
fields('kishimoto2004general',url='https://s.aaai.org/Papers/AAAI/2004/AAAI04-102.pdf')
setrow('saffidine2012ucd',status='complete_identifier',completion=['补 DOI 10.1016/j.knosys.2011.11.014。'],primary_urls=['https://www.sciencedirect.com/science/article/abs/pii/S0950705111002504','https://www.lamsade.dauphine.fr/~cazenave/papers/kbs.pdf','https://api.crossref.org/works/10.1016/j.knosys.2011.11.014'],support='论文明确为 rooted DAG 中的 transposition-aware MCTS，Sections 2–3 讨论多个路径分散统计以及在边上聚合；适合当前引用。其 2011 预印本日期不改变 2012 正式期刊年。')
fields('saffidine2012ucd',doi='10.1016/j.knosys.2011.11.014')
setrow('czech2021monte',status='correct_title_version',errors=['混用了 arXiv 2020 预印本题名 Monte-Carlo Graph Search for AlphaZero 与 ICAPS 2021 卷页；正式 ICAPS 论文题名为 Improving AlphaZero Using Monte-Carlo Graph Search。'],completion=['补 DOI 10.1609/icaps.v31i1.15952。'],primary_urls=['https://ojs.aaai.org/index.php/ICAPS/article/view/15952','https://ojs.aaai.org/index.php/ICAPS/article/download/15952/15763/19445','https://arxiv.org/abs/2012.11045'],support='正式论文摘要明确将树推广为 directed acyclic graph，使不同子树共享信息，正文关于 acyclic search graph/transposition sharing 的表述得到直接支持。')
fields('czech2021monte',title='Improving {AlphaZero} Using {Monte-Carlo} Graph Search',doi='10.1609/icaps.v31i1.15952',number='1')
setrow('moerland2020mcts',status='correct_false_venue',errors=['IJCAI 2020、2388–2394 不属于本篇。已核实来源为 arXiv:2005.09645（2020）；合著者出版列表仍标 Submitted/arXiv，不能称 IJCAI 已发表。'],completion=['改为预印本条目并补 arXiv DOI/URL。'],primary_urls=['https://arxiv.org/abs/2005.09645','https://arxiv.org/pdf/2005.09645','https://liacs.leidenuniv.nl/~plaata1/pubs.html','https://www.ijcai.org/proceedings/2020/330'],support='正文关于 loop difficulty、重复状态与 subtree uncertainty 的引用成立：原文 Section 4/4.2 明确讨论循环、重复展开和不终止。附录把 depth-limit truncation 说成 common in loops 稍超来源；建议将该短句改为 loops can prevent termination，保留引用。',prose_issue={'file':'paper/latex/acl_latex.tex','approx_line':433,'before':'by the depth limit before a terminal state, which is common in loops \\citep{moerland2020mcts}.','after':'by the depth limit before a terminal state; loops can prevent termination \\citep{moerland2020mcts}.','reason':'Section 4.2 directly demonstrates failure to terminate; the paper does not estimate the general frequency of depth-limit truncation.'})
f=rows['moerland2020mcts']['verified_metadata'];f.pop('booktitle');f.pop('pages');f.update(journal='arXiv preprint arXiv:2005.09645',doi='10.48550/arXiv.2005.09645',url='https://arxiv.org/abs/2005.09645')
rows['moerland2020mcts']['verified_entry_type']='article'
setrow('silver2017mastering',status='correct_author_list_unused',errors=['未引用库存条目的实际 13 作者被截成前 10 人加 others。'],completion=['补全 13 作者及 DOI/URL；维持已有 arXiv 2017 版本，不擅自替换成 2018 Science 另一题名。'],primary_urls=['https://arxiv.org/abs/1712.01815','https://arxiv.org/pdf/1712.01815'],support='当前 PDF 未引用；仅核题录，不作为现有正文证据。')
fields('silver2017mastering',author='David Silver and Thomas Hubert and Julian Schrittwieser and Ioannis Antonoglou and Matthew Lai and Arthur Guez and Marc Lanctot and Laurent Sifre and Dharshan Kumaran and Thore Graepel and Timothy Lillicrap and Karen Simonyan and Demis Hassabis',doi='10.48550/arXiv.1712.01815',url='https://arxiv.org/abs/1712.01815')
setrow('tolpin2012simple',status='complete_identifier_unused',completion=['补正式 AAAI 26(1):570–576、DOI；保留 2012，勿把迁站上传日期 2021 错当发表年。'],primary_urls=['https://ojs.aaai.org/index.php/AAAI/article/view/8126','https://ojs.aaai.org/index.php/AAAI/article/download/8126/7984'],support='当前 PDF 未引用；正式原文第一页确认完整姓名 Solomon Eyal Shimony。另有 SoCS 同题版本 pp193–199，不能与当前 AAAI 条目混用。')
fields('tolpin2012simple',volume='26',number='1',pages='570--576',doi='10.1609/aaai.v26i1.8126')
setrow('hansen1996monitoring',status='complete_identifier_unused',completion=['补 AAAI 原文 URL。'],primary_urls=['https://cdn.aaai.org/AAAI/1996/AAAI96-182.pdf','https://www.aiinternational.org/Library/AAAI/1996/aaai96-182.php'],support='当前 PDF 未引用；原文 6 页，页码 1229–1234、作者题目均吻合。')
fields('hansen1996monitoring',url='https://cdn.aaai.org/AAAI/1996/AAAI96-182.pdf')
proposed=[]
for k,r in rows.items():
 typ=r.get('verified_entry_type',re.match(r'@(\w+)',blocks[k]).group(1));r['verified_entry_type']=typ
 if r['status']!='verified':
  b='@'+typ+'{'+k+',\n'+''.join('    '+f+' = {'+v+'},\n' for f,v in r['verified_metadata'].items())+'}'
  r['proposed_bib']=b;proposed.append(b)
(root/'mcts_audit.json').write_text(json.dumps({'audit_date':'2026-10-01','scope':'10 printed entries + 3 unused stored entries','entries':rows},ensure_ascii=False,indent=2))
(root/'mcts_proposed.bib').write_text('\n\n'.join(proposed)+'\n')
print('Wrote',len(rows),'audits;',len(proposed),'replacement entries (3 active metadata/author corrections, 3 active identifier completions, 3 unused inventory improvements).')

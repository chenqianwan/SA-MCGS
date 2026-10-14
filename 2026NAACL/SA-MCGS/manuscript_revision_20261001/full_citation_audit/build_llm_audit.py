from pathlib import Path
import json,re
root=Path('tmp/full_citation_audit_20261001'); src=root/'llm_sources'; meta=json.loads((src/'metadata.json').read_text()); original=Path('paper/latex/custom.bib').read_text()
keys=['liu2024lost','wei2022chain','yao2024tree','besta2024graph','hao2023reasoning','battaglia2018relational','hsieh2024ruler','bai2024longbench','wang2023can','fatemi2024talk','edge2024graphrag','devlin2019bert','li2022alphacode']
def extract(key):
 m=re.search(r'@(\w+)\{'+re.escape(key)+r',',original); i=m.end(); depth=1
 while depth:
  if original[i]=='{' and original[i-1]!='\\':depth+=1
  elif original[i]=='}' and original[i-1]!='\\':depth-=1
  i+=1
 return original[m.start():i]
def fields(s):
 out={};pos=s.find(',')+1
 while True:
  m=re.search(r'(\w+)\s*=\s*\{',s[pos:])
  if not m:break
  start=pos+m.end();i=start;d=1
  while d:
   if s[i]=='{' and s[i-1]!='\\':d+=1
   elif s[i]=='}' and s[i-1]!='\\':d-=1
   i+=1
  out[m.group(1)]=s[start:i-1];pos=i
 return out
D={k:fields(extract(k)) for k in keys}; kinds={k:re.match(r'@(\w+)',extract(k)).group(1) for k in keys}
D['liu2024lost']['url']='https://aclanthology.org/2024.tacl-1.9/'
for key,short in [('wei2022chain','wei'),('yao2024tree','yao'),('wang2023can','wang')]:
 v=meta[short]['meta'];D[key].update(booktitle='Advances in Neural Information Processing Systems',volume=v['citation_volume'][0],pages=v['citation_firstpage'][0]+'--'+v['citation_lastpage'][0],year=v['citation_publication_date'][0][:4],doi=v['citation_doi'][0],url=meta[short]['url'],publisher='Curran Associates, Inc.');D[key].pop('journal',None);kinds[key]='inproceedings'
D['besta2024graph'].update(number='16',pages='17682--17690',doi='10.1609/aaai.v38i16.29720',url='https://ojs.aaai.org/index.php/AAAI/article/view/29720')
D['hao2023reasoning'].update(doi='10.18653/v1/2023.emnlp-main.507',url='https://aclanthology.org/2023.emnlp-main.507/')
D['battaglia2018relational'].update(author=' and '.join(meta['battaglia']['meta']['citation_author']),doi='10.48550/arXiv.1806.01261',url='https://arxiv.org/abs/1806.01261')
D['hsieh2024ruler'].update(doi='10.48550/arXiv.2404.06654',url='https://arxiv.org/abs/2404.06654v3')
D['bai2024longbench'].update(pages='3119--3137',doi='10.18653/v1/2024.acl-long.172',url='https://aclanthology.org/2024.acl-long.172/')
D['fatemi2024talk']['url']='https://proceedings.iclr.cc/paper_files/paper/2024/hash/bf72f65f30eedf5d48da6980ee02b589-Abstract-Conference.html'
D['edge2024graphrag'].update(doi='10.48550/arXiv.2404.16130',url='https://arxiv.org/abs/2404.16130v1')
D['devlin2019bert'].update(booktitle=meta['devlin']['meta']['citation_conference_title'][0],url='https://aclanthology.org/N19-1423/')
li=json.loads((src/'li.html').read_text())['message'];author=[]
for a in li['author']:
 family=a['family'].replace('’',"'"); given=a['given'].replace('é',"{\\'e}")
 author.append(family+', '+given)
D['li2022alphacode'].update(author=' and '.join(author),url='https://doi.org/10.1126/science.abq1158')
errors={'yao2024tree':['会议年份误写2024；NeurIPS36官方卷次/元数据/论文页脚均为2023。'], 'battaglia2018relational':['作者手工截断为10名加and others；实际27名，ACL模板会把others计为1名，造成“1 others”及作者遗漏。'],'li2022alphacode':['未引用库存条目作者手工截断为10名加and others；Science登记完整26名，若引用将产生错误的“1 others”。']}
notes={
'liu2024lost':'作者、题名、2024年、TACL12卷、157–173页及DOI完全匹配；补ACL永久链接。',
'wei2022chain':'9名作者与NeurIPS2022官方记录一致；补24824–24837页、官方DOI及链接。网页将brian ichter小写属于元数据大小写，不把现有规范大小写误报为错误。',
'yao2024tree':'修正2024→2023；补11809–11822页、DOI、链接。Tom Griffiths为官方BibTeX署名，PDF作Thomas L.Griffiths，均是同一作者，保留现有官方BibTeX写法；内部key可不改。',
'besta2024graph':'11名作者、题名、AAAI38及2024均正确；补16期、17682–17690页、DOI及链接。',
'hao2023reasoning':'7名作者/题名/EMNLP2023/8154–8173页正确；补DOI及链接。ACL网页导出缩写Joshua Hong/Daisy Wang，而最终PDF首页明确Joshua Jiahua Hong/Daisy Zhe Wang，现有全名正确，不误改。',
'battaglia2018relational':'恢复arXiv列出的全部27名作者；原题名、2018及arXivID正确；补DOI与链接。',
'hsieh2024ruler':'现有arXiv2024引文8名作者与arXivv3、作者NVIDIA仓库完全一致，属有效引文。原文标注COLM2024，但OpenReview访问受限且其被转引元数据常漏Yang Zhang，因此本轮保留已核实的arXiv版本，补DOI和v3链接；不擅自把8作者改成7作者。',
'bai2024longbench':'13名作者、题名、ACL2024卷册正确；补3119–3137页、DOI及ACL链接。',
'wang2023can':'现有2023预印本本身有效；已有NeurIPS36正式版本，同6名作者同年，建议用正式版本并补30840–30861页、DOI、链接。这属于发表信息更新，不是虚假文献。',
'fatemi2024talk':'3名作者、题名、ICLR2024正确；通过ICLR官方proceedings核实，补官方链接（OpenReview有访问验证）。',
'edge2024graphrag':'未引用库存条目8作者对应2024arXivv1，完全正确；v2在2025新增2名作者，不能据v2倒推v1漏作者。补DOI并明确链接v1，不混合版本。',
'devlin2019bert':'未引用库存条目4作者、题名、2019、页码、DOI正确；booktitle补官方完整卷册名，补ACL链接。',
'li2022alphacode':'未引用库存条目卷378期6624页1092–1097年2022、DOI正确；从Science提交Crossref的完整记录恢复26位作者（同时与作者arXiv一致）。'}
support={
'liu2024lost': '支持当前Intro/Related Work关于长上下文检索随证据位置恶化的论述；该文具体测试多文档问答及键值检索。文中的多跳/聚合概括由同组RULER/LongBench共同支撑，未把三类任务都错误归于Lost in the Middle。',
'wei2022chain':'支持Related Work关于CoT改善逐步推理的概括，原文在算术、常识和符号推理任务验证；本稿未声称CoT对所有模型任务统一有效。',
'yao2024tree':'支持Related Work关于显式搜索改善LLM推理；原文以生成/评价thoughts及BFS/DFS开展搜索，对Game24、写作、填字作实验。',
'besta2024graph':'支持Related Work关于图式thought搜索/聚合可改善推理；原文图表示的是生成的思维，不是外部文档图，本稿紧接着明确此区别，语境适当。',
'hao2023reasoning':'支持Related Work关于规划式LLM搜索；原文RAP以LLM作为world model并结合MCTS，测试规划、数学、逻辑任务。',
'battaglia2018relational':'支持§3.4实体及关系层面的relational inductive bias这一设计动机；并非用该综述证明本稿memory公式的理论保证，当前表述可成立。',
'hsieh2024ruler':'直接支持Intro及Related Work的retrieval/multi-hop tracing/aggregation局限；原文明确扩展NIAH到后两任务且性能随长度下降。',
'bai2024longbench':'支持Intro/Related Work长上下文理解不足及跨文档证据整合；包含21数据集6任务族并报告更长上下文困难。',
'wang2023can':'支持Related Work图任务/提示形式及虚假相关的敏感性；NLGraph覆盖8类图任务，比较prompting。',
'fatemi2024talk':'直接支持Related Work graph encoding/task formulation敏感性；原文比较编码方法、任务、图结构三层因素。',
'edge2024graphrag':'未出现在本次PDF参考文献列表，无当前正文支撑关系可核对。',
'devlin2019bert':'未出现在本次PDF参考文献列表，无当前正文支撑关系可核对。',
'li2022alphacode':'未出现在本次PDF参考文献列表，无当前正文支撑关系可核对。'}
urls={k:[D[k]['url']] for k in keys};urls['besta2024graph'].append('https://ojs.aaai.org/index.php/AAAI/article/download/29720/31236');urls['hao2023reasoning'].append('https://aclanthology.org/2023.emnlp-main.507.pdf');urls['hsieh2024ruler']+=['https://github.com/NVIDIA/RULER','https://arxiv.org/abs/2404.06654'];urls['li2022alphacode']+=['https://api.crossref.org/works/10.1126/science.abq1158','https://arxiv.org/abs/2203.07814']
audit={}
for k in keys:
 old=fields(extract(k));changed={f:{'old':old.get(f),'new':v} for f,v in D[k].items() if old.get(f)!=v}
 if kinds[k]!=re.match(r'@(\w+)',extract(k)).group(1):changed['entry_type']={'old':'article','new':kinds[k]}
 audit[k]={'status':'verified_correction' if k in errors else 'verified_metadata_completion','cited_in_pdf':k not in ['edge2024graphrag','devlin2019bert','li2022alphacode'],'errors':errors.get(k,[]),'metadata_notes':notes[k],'primary_urls':urls[k],'support':support[k],'support_verdict':'supported' if k not in ['edge2024graphrag','devlin2019bert','li2022alphacode'] else 'not_cited','verified_metadata':{'entry_type':kinds[k],**D[k]},'proposed_changes':changed}
(root/'llm_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
texts=[]
for k in keys:
 texts.append('@'+kinds[k]+'{'+k+',\n'+''.join('    '+f+' = {'+v+'},\n' for f,v in D[k].items())+'}')
(root/'llm_proposed.bib').write_text('\n\n'.join(texts)+'\n')
print(json.dumps({'audited':len(keys),'active':10,'unused':3,'real_errors':list(errors),'proposed_file':str(root/'llm_proposed.bib')},ensure_ascii=False,indent=2))

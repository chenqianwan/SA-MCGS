from pathlib import Path
import json, re

P = Path(__file__).resolve().parent
inventory = json.loads((P/'inventory.json').read_text())

def fields(raw):
    result = {}
    for m in re.finditer(r'^\s*(\w+)\s*=\s*\{', raw, re.M):
        start = m.end(); i = start; depth = 1
        while depth:
            if raw[i] == '\\': i += 2; continue
            if raw[i] == '{': depth += 1
            elif raw[i] == '}': depth -= 1
            i += 1
        result[m[1]] = raw[start:i-1]
    return result

audit = {}
def add(key, urls, support, errors=(), updates=None, remove=(), entry_type=None, notes=''):
    original = inventory[key]
    f = fields(original['original_bib'])
    for k in remove: f.pop(k, None)
    f.update(updates or {})
    typ = entry_type or original['type']
    changed = f != fields(original['original_bib']) or typ != original['type']
    audit[key] = dict(status='verified_correction' if errors else ('verified_metadata_completion' if changed else 'verified'),
                      cited_in_pdf=original['cited_in_clean'], errors=list(errors), primary_urls=urls,
                      support=support, metadata_notes=notes, verified_entry_type=typ, verified_metadata=f)
    if changed:
        audit[key]['proposed_bib'] = '@'+typ+'{'+key+',\n'+''.join('    '+k+' = {'+v+'},\n' for k,v in f.items())+'}'

add('gibbs2021adaptive', ['https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html'],
    '支持在线分布变化下自适应校准的动机。本文明确只取 calibration-inspired signal，不声称继承覆盖保证；适配。',
    updates={'url':'https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html', 'publisher':'Curran Associates, Inc.'},
    notes='官方 BibTeX 核对两作者、2021、NeurIPS 34、1660–1672；保留 Candès 的重音。')
add('vovk2005algorithmic', ['https://link.springer.com/book/10.1007/b106715'],
    '书中第2章介绍 conformal prediction，支持校准动机；本文没有把该书交换性条件下的结论直接套到自适应搜索。',
    notes='Springer 第一版页面确认三作者、书名、2005、出版社及 DOI；不因第二版存在而改动经典第一版。')
add('tarjan1972depth', ['https://epubs.siam.org/doi/10.1137/0201010'],
    '原文摘要直接给出有向图 SCC 算法及 k1 V+k2 E+k3 的空间/时间上界；支持正文线性 SCC 预处理。',
    notes='SIAM 原刊：1972年6月，1(2):146–160；2006 是网站上线日期，不能替代出版年。')
add('eades1993fast', ['https://www.sciencedirect.com/science/article/pii/002001909390079O'],
    '摘要直接定义反转反馈边获得无环图，支持正文删除/重定向反馈边的对比；本文对风险证据损失的分析是自身动机而非归给该文的实验结论。',
    notes='三作者、47(6)、319–323、1993、DOI 与出版商页面和登记一致。')
add('berger1990approximation', ['https://dl.acm.org/doi/10.5555/320176.320203',
    'https://doi.org/10.5555/320176.320203', 'https://hdl.handle.net/api/handles/10.5555/320176.320203',
    'https://sigmod.org/publications/dblp/db/conf/soda/soda90.html'],
    '书目存在且最大无环子图主题与上下文匹配。ACM 原页面访问受限，未声称阅读全文；Eades 原文摘要明确说明 Berger–Shor 方法与反馈边的关系。',
    errors=['所填 DOI 不可解析：doi.org 返回404，Handle 注册查询 responseCode=100。不能把 ACM 目录标识当作已注册 DOI。'],
    updates={'url':'https://dl.acm.org/doi/10.5555/320176.320203'}, remove=('doi',),
    notes='保留作者、题名、SODA1990及236–243页；以 ACM 目录 URL 定位，不再生成一个无效 doi.org 链接。ACM托管的会议目录可交叉核题录，但它是DBLP镜像，报告明确其性质。')
add('nemhauser1978analysis', ['https://link.springer.com/article/10.1007/BF01588971'],
    '文献证明的是单调次模目标在基数约束下的贪心近似界。本文正向成对关系奖励不满足一般次模性；只能支持方法动机，不能给本文效用函数提供该近似保证。',
    errors=['标题漏了末尾的 Part I（—I）。'],
    updates={'title':'An Analysis of Approximations for Maximizing Submodular Set Functions---{I}'},
    notes='作者、1978、14(1):265–294、DOI正确。正文仅作最小范围澄清，明确本文采用启发式 replacement；不改变公式或算法。')
add('zilberstein1996anytime', ['https://ojs.aaai.org/aimagazine/index.php/aimagazine/article/view/1232',
    'https://onlinelibrary.wiley.com/doi/10.1609/aimag.v17i3.1232'],
    '摘要讨论 anytime 算法在计算时间和解质量间的权衡，符合正文固定预算/可中断计算的背景引用。',
    updates={'doi':'10.1609/aimag.v17i3.1232'},
    notes='作者、题名、1996、AI Magazine17(3):73–83均正确；补官方DOI。')
add('kahneman2011thinking', ['https://us.macmillan.com/books/9781429969352/thinkingfastandslow/'],
    '未被当前净稿引用，不产生正文证据需求。', errors=['该条是专著，原 @article 类型错误。'],
    updates={'url':'https://us.macmillan.com/books/9781429969352/thinkingfastandslow/'},remove=('note',),entry_type='book',
    notes='出版社页面确认 Daniel Kahneman、书名、Farrar Straus Giroux、2011年10月25日；修复库存类型，不引入正文。')

models = {
 'openai2024gpt4o': ('https://cdn.openai.com/gpt-4o-system-card.pdf','官方 system card 明确要求署名 OpenAI (2024)。'),
 'comanici2025gemini25': ('https://arxiv.org/html/2507.06261v6','Gemini Team 首页团体署名；§3.1 Table2 对应 Gemini2.5Pro。'),
 'qwen2024qwen25': ('https://arxiv.org/abs/2412.15115v1','2024年v1的 Qwen Team 署名及Qwen2.5系列/72B模型对应准确。'),
 'grattafiori2024llama3': ('https://arxiv.org/abs/2407.21783v3','Llama Team团体署名对应报告首页，涵盖3.1及8B。'),
 'qwen2026qwen35nine': ('https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md','官方Qwen3.5-9B固定模型卡版本对应实际实验。')
}
for k,(url,note) in models.items():
    add(k,[url], '支持§4.4模型身份和出处，不用于证明本文实验收益。',notes=note+' 复用同日已完成的逐项审计和存档证据，并确认条目此后未改；本轮无需再次修改。')

(P/'root_audit.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n')
(P/'root_proposed.bib').write_text('\n\n'.join(a['proposed_bib'] for a in audit.values() if 'proposed_bib' in a)+'\n')
print('Root checked',len(audit),'entries')

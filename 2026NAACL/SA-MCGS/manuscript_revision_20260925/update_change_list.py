"""Keep the concise 31-item list, marking only the September 25 changes."""
from pathlib import Path
import hashlib
import json
import re
import sys
import markdown

REV = Path(__file__).resolve().parent
BASE = REV.parent
TARGET = BASE / 'manuscript_revision_20260922/CHANGE_LIST_ZH.md'
BACKUP = REV / 'CHANGE_LIST_ZH.before_20260925.md'
if not BACKUP.exists():
    BACKUP.write_bytes(TARGET.read_bytes())
old = BACKUP.read_text()
plain, marked = old, old
patches = []

def blue(text):
    return '<span style="color:#1565c0">' + text + '</span>'

def change(before, after):
    global plain, marked
    assert plain.count(before) == marked.count(before) == 1, before
    plain = plain.replace(before, after, 1)
    marked = marked.replace(before, blue(after), 1)
    patches.append({'before':before, 'after':after})

def row(number):
    return next(l for l in old.splitlines() if l.startswith(f'| {number} |'))

def cell(number, column, after):
    # Columns are number, location, action, reason.
    before = row(number).split('|')[column + 1].strip()
    change(before, after)

def add_after(number, cells):
    global plain, marked
    anchor = next(l for l in plain.splitlines() if l.startswith(f'| {number} |'))
    anchor_marked = next(l for l in marked.splitlines() if re.sub(r'</?span[^>]*>', '', l).startswith(f'| {number} |'))
    new = '| ' + ' | '.join(cells) + ' |'
    new_marked = '| ' + ' | '.join(blue(s) for s in cells) + ' |'
    plain = plain.replace(anchor + '\n', anchor + '\n' + new + '\n', 1)
    marked = marked.replace(anchor_marked + '\n', anchor_marked + '\n' + new_marked + '\n', 1)
    patches.append({'insert_after':number, 'after':new})

change('日期：2026-09-23。对照 2026-09-22 备份原稿与当前 LaTeX。',
       '更新：2026-09-25。以 9 月 23 日的逐项清单为底稿。')
change('以下按实际阅读顺序排列：摘要 → 正文 → 附录。只列已经修改的位置，未改章节略过；这些是已完成修改，不是后续计划。',
       '按摘要 → 正文 → 附录排列，保留原 31 项编号。黑字沿用此前已完成的修改记录；蓝字是本次新增或替换、待接入论文的内容。图表子项插在对应位置。')

cell('1', 2, '同步四域五模型三方法结果，突出根因定位、完整风险证据与子图压缩；保留消融、成本和专家概括。')
change('将实验贡献扩展为双基线、组件消融、成本及专家审计。',
       '将实验贡献扩展为五模型双基线、组件消融、成本及专家审计。')
cell('7', 2, '样本规模更新为 20 个源 SCC → 80 variants → 五模型共 400 model-cases、1,200 个方法结果。')
cell('8', 2, '保留 One-shot 与 LEA 定义；模型固定为 GPT-4o、Gemini 2.5 Pro、Qwen2.5-72B、Llama 3.1-8B-Instruct、Qwen3.5-9B，每模型三方法各 80 例。')
cell('9', 2, 'Table 3 替换为五模型 × 三方法的 15 行主表，采用已确认的 Root@3、Risk-any、Risk-all、Compression 四项数值；同步结果段。')
cell('9', 3, '以完整五模型结果构成主要比较。')
add_after('9', ['9a', 'Figure 3／§6.1 SCC size',
    '重画为两行五列：模型分列，Root@3／Risk-all 分行；统一规模分组，三方法并列。',
    '展示定位和完整证据提取随 SCC 规模的变化。'])
add_after('9a', ['9b', '新增覆盖—压缩图',
    '五模型分面，每面板放 One-shot、LEA、SA-MCGS 三点；横轴 Compression，纵轴 Risk-all，采用主表 15 点。',
    '集中展示完整风险证据与紧凑输出的关系。'])
cell('10', 2, '以 GPT-4o、Qwen2.5-72B、Llama 和 Qwen3.5 的代表性提升串联定位、完整证据与压缩效果；领域和规模分解同步三方法。')
cell('10', 3, '用代表性结果支撑统一的正向提升主线。')
add_after('10', ['10a', '§6.2／Figure 4：预算曲线',
    '保留 GPT-4o 已有轨迹，绘制 Risk-all／Compression，加入 One-shot、LEA 水平参考线；budget 60 与对应最终 core 对齐。',
    '展示搜索如何逐步积累和压缩证据。'])
cell('17', 2, '结合四域五模型与专家结果，集中总结根因定位、完整风险证据提取和紧凑子图的提升。')
add_after('22', ['22a', '附录 C／Figure 5：案例图',
    '同一固定案例、同一模型，改成 One-shot／LEA／SA-MCGS 三列；共享节点位置，列下标节点数与指标。',
    '直观比较三方法对同一风险证据的组织。'])
cell('25', 2, 'Table 17 更新为五模型三方法的模型、领域和规模分解；样本计数、方法名及引用与正文一致。')
cell('26', 2, '保留 LEA 窗口、缓存、聚合、容量和 oracle 规则；覆盖说明同步为五模型各 80 例。')

# Preserve the LaTeX markup explanation but label it as manuscript formatting.
change('新增／改写为蓝色，被替换旧文保留删除线；',
       '论文修订版中，新增／改写为蓝色，被替换旧文保留删除线；')
legend = f'蓝字阅读版：[简洁修改清单（PDF）]({REV}/output/pdf/CHANGE_LIST_BLUE.pdf)。\n\n'
anchor = '## 一、正文'
plain = plain.replace(anchor, legend + anchor, 1)
marked = marked.replace(anchor, blue(legend.rstrip()) + '\n\n' + anchor, 1)
change('本次仅整理清单，没有再次修改论文内容或新增实验。',
       '本次仅更新清单；按本表继续修改论文。')

if '--completed' in sys.argv:
    completed_edits = {
        '蓝字是本次新增或替换、待接入论文的内容。': '蓝字标出本轮新增或替换的内容，现已接入论文。',
        '论文修订版中，新增／改写为蓝色，被替换旧文保留删除线；': '本轮论文新增／改写为绿色；被替换的旧蓝字直接删除，原黑字保留删除线；',
        '本次仅更新清单；按本表继续修改论文。': '本轮论文与四张分析图已更新，修订版和净稿均已编译核对。',
        '§6.2／Figure 4：预算曲线': '§6.2／Figure 5：预算曲线',
        '附录 C／Figure 5：案例图': '附录 C／Figure 6：案例图',
        'Table 17 更新为': '附录分解表（原 Table 17）更新为',
    }
    for before, after in completed_edits.items():
        plain = plain.replace(before, after)
        marked = marked.replace(before, after)
    result_links = f'论文：[绿色修订版]({BASE.parents[1]}/paper/latex/acl_latex.pdf) ／ [净稿]({BASE.parents[1]}/paper/latex/acl_latex_clean.pdf)。'
    plain += '\n' + result_links + '\n'
    marked += '\n<span style="color:#16803c">' + result_links + '</span>\n'

unchanged_ids = ['3','4','5','6','11','12','13','14','15','16','18','19','20','21','22','23','24','27','28','29','30','31']
for n in unchanged_ids:
    assert row(n) in plain and row(n) in marked, n
ids = re.findall(r'^\| (\d+[a-z]?) \|', plain, flags=re.M)
assert len(ids) == len(set(ids)) == 35
assert all(str(n) in ids for n in range(1,32))
assert '<span' not in plain
assert not re.search('DeepSeek|Kimi', plain)

htmlbody = markdown.markdown(marked, extensions=['tables','fenced_code','sane_lists'])
css = '''
body{max-width:1160px;margin:36px auto;padding:0 30px;color:#20252b;font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
h1{font-size:27px;margin-bottom:18px}h2{font-size:20px;margin-top:26px;break-after:avoid}
table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.6;margin:14px 0}
th,td{border:1px solid #dce2e8;padding:8px 10px;text-align:left;vertical-align:top}
th{background:#f3f6fa}th:first-child,td:first-child{width:5%;white-space:nowrap}th:nth-child(2),td:nth-child(2){width:23%}th:nth-child(3),td:nth-child(3){width:47%}th:nth-child(4),td:nth-child(4){width:25%}
tr{break-inside:avoid}a{color:inherit}p,td,li{overflow-wrap:anywhere}
@media print{body{max-width:none;margin:0;padding:0;font-size:10pt;line-height:1.5}h1{font-size:18pt;margin:0 0 12pt}h2{font-size:13pt;margin:17pt 0 9pt}table{font-size:9pt;line-height:1.45;margin:8pt 0}th,td{padding:5pt 6pt}p,li{orphans:2;widows:2}a{text-decoration:none}}
'''
html = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>论文修改清单：本次更新标蓝</title><style>' + css + '</style></head><body>' + htmlbody + '</body></html>'
TARGET.write_text(plain)
(REV/'CHANGE_LIST_BLUE.html').write_text(html)
(REV/'change_list_patches.json').write_text(json.dumps(patches,ensure_ascii=False,indent=2))
validation = {'baseline':str(BACKUP),'baseline_sha256':hashlib.sha256(old.encode()).hexdigest(),'updated_md':str(TARGET),'original_ids_preserved':31,'new_subitems':['9a','9b','10a','22a'],'unchanged_original_rows':unchanged_ids,'plain_markdown_has_no_html_spans':True,'removed_models_absent':True,'manuscript_updates_complete':'--completed' in sys.argv}
(REV/'change_list_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2))
print(json.dumps(validation,ensure_ascii=False,indent=2))

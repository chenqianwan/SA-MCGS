"""Update the existing plans incrementally for the author's selected Figure 4 D."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import markdown

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REV = BASE / 'manuscript_revision_20260925'
ROOT = BASE.parents[1]
BACKUP = HERE / 'before_plans'
LIST = BASE / 'manuscript_revision_20260922/CHANGE_LIST_ZH.md'
MASTER = BASE / 'ARR_OCT2026_MASTER_REVISION_PLAN_ZH.md'
INCREMENTAL = REV / 'MASTER_REVISION_PLAN_INCREMENTAL.md'
CLEAN = REV / 'MASTER_REVISION_PLAN_20260925_CLEAN.md'
LHTML = REV / 'CHANGE_LIST_BLUE.html'
MHTML = REV / 'MASTER_REVISION_PLAN_BLUE.html'
FILES = [LIST, MASTER, INCREMENTAL, CLEAN, LHTML, MHTML,
         REV / 'output/pdf/CHANGE_LIST_BLUE.pdf',
         REV / 'output/pdf/MASTER_REVISION_PLAN_BLUE.pdf', REV / 'blue_preview_top.png']
for path in FILES:
    destination = BACKUP / path.relative_to(BASE)
    if path.exists() and not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

def prior(path):
    return (BACKUP / path.relative_to(BASE)).read_text()

def inline(text):
    rendered = markdown.markdown(text, extensions=['tables', 'fenced_code', 'sane_lists'])
    assert rendered.startswith('<p>') and rendered.endswith('</p>'), rendered
    return rendered[3:-4]

def apply(plain, html, edits, key):
    for old, new in edits:
        assert plain.count(old) == 1, (key, plain.count(old), old)
        plain = plain.replace(old, new, 1)
        if html is not None:
            old_html = inline(old)
            assert html.count(old_html) == 1, (key, html.count(old_html), old_html)
            html = html.replace(old_html, '<span style="color:#1565c0">' + inline(new) + '</span>', 1)
    return plain, html

list_edits = [
    ('更新：2026-09-25。以 9 月 23 日的逐项清单为底稿。',
     '更新：2026-09-28。沿用原逐项清单；本次将 Figure 4 替换为已选定的 D：逐案例配对收益图。'),
    ('新增覆盖—压缩图', 'Figure 4／逐案例配对收益（已替换为 D）'),
    ('五模型分面，每面板放 One-shot、LEA、SA-MCGS 三点；横轴 Compression，纵轴 Risk-all，采用主表 15 点。',
     '采用 D：左右分别与 One-shot、LEA 配对；每模型 80 例分为 SA-only、Both、Baseline-only、Neither，并列净提升。相对 LEA，GPT-4o、Qwen2.5、Llama 分别净增 25、25、11 例；图注和正文同步更新。'),
    ('集中展示完整风险证据与紧凑输出的关系。',
     '把总体 Risk-all 提升解释为具体案例收益，与主表和规模图互补。'),
]
list_plain, list_html = apply(prior(LIST), prior(LHTML), list_edits, 'list')

new_layout = '左右两面板分别比较 One-shot、LEA；每模型同一 80 例，以四段横条显示 SA-only、Both、Baseline-only、Neither，右侧列 Risk-all 净提升（百分点）'
new_interpretation = 'Figure 4 采用已选定的 D：逐案例配对收益图，与 Table 3 和 Figure 3 分工：主表给出总体指标，规模图展示分组表现，配对图解释新增完整风险证据来自多少案例。正文突出相对 LEA 的净增案例数：GPT-4o 为 32−7＝25，Qwen2.5-72B 为 33−8＝25，Llama 3.1-8B 为 21−10＝11；对应 Risk-all 提升 31.25、31.25、13.75 个百分点。'
common_edits = [
    ('新增覆盖—压缩图，拟用 `fig:coverage_compression`',
     'Figure 4，`fig:paired_case_outcomes`；`fig03_paired_case_outcomes_five_models.pdf`'),
    ('用当前 15 个方法点作散点图；One-shot、LEA、SA-MCGS 均保留',
     '已用 D 逐案例配对收益图替换；从冻结逐例 Risk-all 结果统计，图注与相邻正文同步'),
    ('五模型分面，每面板三点；横轴 Compression，纵轴 Risk-all；共享 0–100% 坐标', new_layout),
    ('直观看见完整证据与紧凑输出的关系', '解释 SA-MCGS 多找回了多少案例的完整风险证据'),
    ('P9 Figure 4，`fig:convergence`', 'Figure 5，`fig:convergence`'),
    ('P18 Figure 5，`fig:case`', 'Figure 6，`fig:case`'),
    ('Figure 4 的旧生成代码', '预算图的旧生成代码'),
    ('覆盖—压缩图放在主结果与规模分析附近，与 Table 3 合作：表提供完整数值，图突出两项指标的共同变化。它替换原复合图中重复总体百分比的面板；排版时保留清晰的模型分面与图例，不再另加一张重复的总体柱状图。', new_interpretation),
    ('所有方法效果图使用同一图例：One-shot 灰色、LEA 橙色、SA-MCGS 蓝色，同时用不同点形区分。模型顺序与 Table 3 一致；坐标、百分号、小数精度和字体在图之间统一。折线仅连接同一方法的实际分组或搜索快照，静态基线以参考线呈现。',
     '方法曲线沿用 One-shot 灰色、LEA 橙色、SA-MCGS 蓝色及不同点形。Figure 4 按配对结果编码：SA-only 深蓝、Both 浅蓝、Baseline-only 橙色、Neither 灰色；横轴为案例数，四段合计 80，净提升＝（SA-only−Baseline-only）÷80×100。模型顺序与 Table 3 一致。'),
]
master_edits = [
    ('更新：2026-09-25。', '更新：2026-09-28。'),
    ('当前先根据已确认的五模型结果更新本方案，再修改第八页及之后的结果、分析和图表。',
     '五模型主表与分析图已接入论文；本次按作者选择，将 Figure 4 替换为 D 逐案例配对收益图，并同步图注、结果文字和修改清单。'),
    ('新增及改写后的文字用蓝色；被删除或被替换的旧文字保留并加删除线，未改动内容保持原样。',
     '本轮论文新增及改写用绿色，旧蓝字可直接删除，原黑字采用删除线；方案和清单的新增改动继续标蓝，未改动内容保持原样。'),
    ('采用第 4.2 节五模型三方法主表，更新规模图、预算图和案例图，新增覆盖—压缩图；执行清单见第 7.3 节',
     '采用第 4.2 节五模型三方法主表，保留规模图、预算图和案例图；Figure 4 已替换为 D 逐案例配对收益图，执行清单见第 7.3 节'),
    ('五模型三方法完整主表，配规模对照及覆盖—压缩图；文字集中陈述代表性提升',
     '五模型三方法完整主表，配规模对照及逐案例配对收益图；文字集中陈述代表性提升'),
    ('以下页码按当前修订 PDF 定位，实际修改以 LaTeX 标签为准。先完成本方案，再从既有结果离线生成图表，接入论文。',
     '以下位置以 LaTeX 标签为准。Figure 4 已选定 D 并完成替换，数据取自现有冻结结果；主文仅采用这一备选图。'),
] + common_edits + [
    ('三方法规模图、覆盖—压缩图、预算参考线和同案例三列图已完成；预算 60 端点与对应最终 core 对齐。',
     '三方法规模图、Figure 4 逐案例配对收益图、预算参考线和同案例三列图已完成；配对横条各合计 80，净收益与主表 Risk-all 差值一致。'),
]
master_plain, master_html = apply(prior(MASTER), prior(MHTML), master_edits, 'master')
assert prior(MASTER) == prior(INCREMENTAL)
# Keep the short table lead-in with its following table after the longer D row.
table_lead = '<p><span style="color: #1565c0;"><strong>专题表与附录同步：</strong></span></p>'
assert master_html.count(table_lead) == 1
master_html = master_html.replace(table_lead, table_lead.replace('<p>', '<p style="break-after:avoid">'))

clean_edits = [
    ('更新：2026-09-25。当前任务：依据已确认的五模型结果，更新论文第八页及之后的结果、分析、图表和结论。本文是后续改稿的执行方案；主实验数值采用本方案第 4.2 节的完整列表。',
     '更新：2026-09-28。五模型结果与分析图已接入论文；本次按作者选择将 Figure 4 替换为 D 逐案例配对收益图，同步图注、结果文字和修改清单。主实验数值沿用第 4.2 节的完整列表。'),
    ('更新蓝色修订方案；随后按方案修改第八页及之后的论文和图表', 'Figure 4 已替换为 D；论文新增文字用绿色，修改方案与清单的更新用蓝色'),
    ('当前修订标记版为 26 页：第 8 页包含主结果 Table 3、Figure 3 和规模分析；第 9 页包含预算 Figure 4、组件 Table 4 和成本 Table 5；第 10 页接成本、专家与 Related Work；第 11 页为结论。后续按章节标签定位，图表增删后的最终页码由编译决定。',
     '主结果由 Table 3、规模 Figure 3 和逐案例配对 Figure 4 构成；预算图为 Figure 5，案例图为 Figure 6。正文按章节标签定位，修订版和净稿页码以最终编译为准。'),
    ('结合覆盖—压缩图，说明方法能够将关键证据组织成更紧凑的输出。', '结合主表的压缩率，说明方法能够将关键证据组织成更紧凑的输出。'),
    ('正文将这一结果与覆盖—压缩图连接，说明证据选择和替换的价值。', '正文将这一结果与主表和逐案例配对收益连接，说明证据选择和替换的价值。'),
    ('风险覆盖与紧凑子图之间的关系', '完整风险证据提升对应的案例收益'),
    ('新覆盖—压缩图', 'Figure 4 逐案例配对收益图'),
    ('展示证据选择质量', '展示新增完整风险证据的案例数'),
    ('预算 Figure 4、组件 Table 4', '预算 Figure 5、组件 Table 4'),
] + common_edits + [
    ('规模三方法图、覆盖—压缩图、预算图、三列案例图 | 待执行',
     '规模三方法图、D 逐案例配对收益图、预算图、三列案例图 | 已完成；本次替换 Figure 4'),
]
clean_plain, _ = apply(prior(CLEAN), None, clean_edits, 'clean')

# The accepted main table is copied byte-for-byte; only figure planning changes.
def main_table(text):
    start = text.index('| 模型 | 方法 | Root@3 | Risk-any | Risk-all | Compression |')
    return text[start:text.index('\n\n', start)]
assert main_table(master_plain) == main_table(prior(MASTER))
assert main_table(clean_plain) == main_table(prior(CLEAN))
for content in [list_plain, master_plain, clean_plain]:
    assert '<span' not in content
    assert '覆盖—压缩图' not in content
    assert 'fig:coverage_compression' not in content
assert len(re.findall(r'^\| (\d+[a-z]?) \|', list_plain, re.M)) == 35
assert all(re.search(r'^\| ' + str(i) + r' \|', list_plain, re.M) for i in range(1, 32))

for path, content in [(LIST, list_plain), (LHTML, list_html), (MASTER, master_plain),
                      (INCREMENTAL, master_plain), (MHTML, master_html), (CLEAN, clean_plain)]:
    path.write_text(content)

report = {'updated': '2026-09-28', 'selected': 'D', 'main_figure_label': 'fig:paired_case_outcomes',
          'changed_files': [str(p) for p in [LIST, MASTER, INCREMENTAL, CLEAN, LHTML, MHTML]],
          'backups': str(BACKUP), 'original_31_items_and_4_subitems_preserved': True,
          'accepted_main_tables_byte_identical': True,
          'plain_markdown_has_no_html': True, 'old_scatter_plan_absent': True,
          'prior_html_markup_preserved_new_replacements_blue': True,
          'patches': {'list': list_edits, 'master': master_edits, 'clean': clean_edits}}
(HERE / 'plan_update_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps({k: v for k, v in report.items() if k != 'patches'}, ensure_ascii=False, indent=2))

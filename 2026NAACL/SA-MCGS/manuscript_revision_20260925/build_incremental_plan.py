"""Apply the September 25 additions to the preserved September 22 plan."""
from pathlib import Path
import hashlib
import json
import re
import markdown

REV = Path(__file__).resolve().parent
BASE = REV.parent
ORIGINAL = REV / 'ARR_OCT2026_MASTER_REVISION_PLAN_ZH.before_20260925.md'
baseline = ORIGINAL.read_text()
plain = baseline
marked = baseline
changes = []

def blue(text):
    return '<span style="color: #1565c0;">' + text + '</span>' if text else ''

def blue_block(text):
    lines = []
    for line in text.splitlines(keepends=True):
        end = '\n' if line.endswith('\n') else ''
        line = line.rstrip('\n')
        if not line.strip() or re.fullmatch(r'[| :\-]+', line):
            lines.append(line + end)
        elif line.startswith('|'):
            cells = line.split('|')
            lines.append('|' + '|'.join(' ' + blue(c.strip()) + ' ' for c in cells[1:-1]) + '|' + end)
        else:
            m = re.match(r'^(#{1,6} |[-*] (?:\[[ x]\] )?|> )(.*)$', line)
            lines.append((m[1] + blue(m[2]) if m else blue(line)) + end)
    return ''.join(lines)

def replace(old, new, block=False):
    global plain, marked
    assert plain.count(old) == 1, (plain.count(old), old[:150])
    assert marked.count(old) == 1, (marked.count(old), old[:150])
    plain = plain.replace(old, new, 1)
    marked = marked.replace(old, blue_block(new) if block else blue(new), 1)
    changes.append({'before': old, 'after': new})

def insert_before(anchor, new):
    global plain, marked
    assert plain.count(anchor) == marked.count(anchor) == 1
    plain = plain.replace(anchor, new + anchor, 1)
    marked = marked.replace(anchor, blue_block(new) + anchor, 1)
    changes.append({'before': '', 'after': new, 'before_anchor': anchor})

# Update only current status and the model comparison; keep the old plan as the base.
replace('更新：2026-09-22。', '更新：2026-09-25。')
replace('当前进入作者逐段核对及篇幅压缩阶段，尚非最终投稿包。',
        '当前先根据已确认的五模型结果更新本方案，再修改第八页及之后的结果、分析和图表。')
insert_before('## 0. 先看结论',
    '本方案以 9 月 22 日修改 MD 为底稿，保留原有结构和未改文字；本次新增或替换的内容在[蓝字对照版](manuscript_revision_20260925/output/pdf/MASTER_REVISION_PLAN_BLUE.pdf)中标蓝，原文保持黑色。\n\n')
replace('四域四模型实验验证方法表现。', '四域五模型实验验证方法表现。')
replace('原 320 model-case 数据保留、不整体重跑，但',
        '已确认的五模型结果作为本轮主比较，原实验记录保留；')
replace('full-SCC 基线＋结构化强基线 LEA，SA-MCGS 同时与二者比较',
        'One-shot full-SCC 基线＋结构化强基线 LEA，SA-MCGS 同时与二者比较')
replace('| 原 320 model-case 主实验 | 冻结数据与覆盖价值保留，不整体重跑 | 主结果表按双基线重组；明确各组覆盖，不要求旧表原样保留 |',
        '| 五模型主实验 | 每模型 80 案例、三方法结果已确认 | 用第 4.2 节完整主表更新结果，图表任务见第 7.3 节 |', block=True)
replace('36-post 已对齐；同期 12-SCC 三方法比较已完成',
        '五模型 LEA 已补齐并纳入主表；同期 12-SCC 三方法比较已完成')
replace('剩余主要是作者核对、压页、真实专家伦理/资格说明及重投修改说明；',
        '剩余主要是五模型主表与分析图更新、对应文字修改、作者核对、压页、真实专家伦理/资格说明及重投修改说明；')
replace('已整合本方案的正文与附录增补', '已整合 9 月 22 日方案的正文与附录增补')

# Only current-action cells change in the review history.
replace('正文加入 One-shot / LEA / SA 同样本 strict 对照；说明各自 schema、聚合、预算；oracle 单列，不用 valid-only 隐去失败',
        '正文采用五模型各 80 案例的 One-shot / LEA / SA-MCGS 对照；方法部分说明 schema、聚合与预算，主表采用第 4.2 节结果')
replace('Gemini Pro、DeepSeek 的旧 baseline 很强', 'Gemini Pro 等模型的旧 baseline 很强')
replace('在双基线主结果和相邻讨论中展示模型差异，按实际覆盖报告；完整分解放附录，不将差异改成新的故事线',
        '以五模型主表呈现比较，围绕根因定位、完整风险证据与紧凑子图组织正向结果；领域和规模分解放附录')
replace('**替换方式：** 新稿默认使用已对齐的 36-post 与新的 12-SCC 同期三方法比较；若以后希望恢复完整 matched-160，单独补齐剩余 13 项并重算，而非继续使用旧 aggregate。',
        '**替换方式：** LEA 补充已完成，主结果统一采用第 4.2 节的五模型、每模型 80 案例三方法表；36-post 与 12-SCC 对照保留为专家及成本专题证据。')
insert_before('| 专家 / post 对照 |',
        '| 本轮主比较 | 同一 80 variants，运行 GPT-4o、Gemini 2.5 Pro、Qwen2.5-72B、Llama 3.1-8B-Instruct、Qwen3.5-9B | 400 model-cases；每模型 One-shot、LEA、SA-MCGS 三方法，共 1,200 个方法结果 |\n')

# Replace the obsolete active comparison, leaving all historical/specialist tables intact.
donor = (REV / 'MASTER_REVISION_PLAN_20260925_CLEAN.md').read_text()
table_start = donor.index('| 模型 | 方法 | Root@3 | Risk-any | Risk-all | Compression |')
table_end = donor.index('\n\n', table_start)
main_table = donor[table_start:table_end]
old_start = plain.index('**新版主比较采用')
old_end = plain.index('### 4.3 ', old_start)
new_main = '''**新版主比较采用 One-shot＋LEA＋SA-MCGS，覆盖五个模型、每模型同一 80 案例。** 以下四项指标均以百分比显示，作为本轮主表、图表与文字的固定采用版本。

''' + main_table + '''

主表按模型分组，每组固定三行；保留两位小数。SA-MCGS 方法名突出，数值加粗仅用于组内对应指标的最佳值，相同最佳值同时标粗。

**结果叙述以正向提升为主线：根因定位、完整风险证据与紧凑子图。** 先以 GPT-4o、Qwen2.5-72B 和两个较小模型相对 One-shot 的结果建立总体效果，再说明搜索相对 LEA 的进一步提升。GPT-4o 与 Qwen2.5-72B 的 Risk-all 均由 43.75% 提高至 75.00%，提高 31.25 个百分点；Llama 3.1-8B 的 Root@3 由 43.75% 提高至 61.25%，Risk-all 由 35.00% 提高至 48.75%。

Qwen3.5-9B 的 Root@3 从 56.25% 提高至 62.50%，在 Risk-all 保持 63.75% 的同时，Compression 从 51.26% 提高至 67.25%；这一结果衔接定位与证据压缩的共同作用。Gemini 2.5 Pro 的基线已处于较高水平，三方法的 Risk-all 为 83.75%–85.00%，用相邻短句交代即可。正文选取代表值，完整数值由主表承担。

本轮主表的数据来源：[GPT-4o、Gemini 2.5 Pro 与 Qwen2.5-72B 结果](experiments/lea_full320_completion_20260923/RESULTS_ANALYSIS.json)、[Llama 3.1-8B 结果](experiments/llama8b_three_methods_20260924/final_analysis.json)、[Qwen3.5-9B 已确认结果](experiments/kimi_qwen35_three_methods_20260924/parsing_recovery_audit_20260925/metricwise_results.json)。图表离线读取对应逐例数据，完整修改清单见第 7.3 节。

'''
replace(plain[old_start:old_end], new_main, block=True)
replace('### 4.3 LEA 强基线主比较：已对齐的 36-post 子集',
        '### 4.3 专家配套比较：保留已对齐的 36-post 子集', block=True)
replace('可说：GPT 的端点完整性改善明显；Gemini 上 LEA 略高。不可说：跨模型统一胜出、36 个独立源 SCC、旧 160 全部修好了。One-shot 是单次 direct-subgraph，不是 oracle Top-3。',
        '此表保留为专家配套子集的历史对照，与后文专家分析衔接；当前主结果统一采用第 4.2 节的完整 80 案例五模型表。')

replace('已有匹配三方法结果，覆盖范围明确', '五模型各 80 案例的三方法结果已确认')
replace('以 full-SCC＋LEA 双基线重组主结果；保留 36-post 与同期 12-SCC 的范围区别',
        '更新五模型主表和三方法图；专家与同期 12-SCC 成本对照保留原用途')
replace('把 Gemini、DeepSeek 的边界放正文，而非只在附录承认',
        '以根因定位、完整风险证据及紧凑输出组织结果，正文突出代表性提升，完整比较列入主表')
replace('提升依赖模型、样本与成本；强 full-SCC / LEA 也可能更好',
        'SA-MCGS 在多个模型上提高根因定位与完整风险证据提取，并将关键证据组织为紧凑子图；代表性结果见第 4.2 节')

# Preserve section 7 and append concrete figure/table work, not a replacement outline.
replace('实验概括同步为双基线比较，突出 LEA 强基线验证及模型差异；不重写问题动机',
        '实验概括同步为四域五模型三方法比较，突出定位、完整证据与压缩效果；不重写问题动机')
replace('原主实验数据、章节位置与四域四模型覆盖依据',
        '原 80 案例、章节位置与四域覆盖依据')
replace('主表/图及分析按双基线重组，LEA 与 full-SCC 并列；不同覆盖范围分组/panel 展示，不要求旧表原样保留',
        '采用第 4.2 节五模型三方法主表，更新规模图、预算图和案例图，新增覆盖—压缩图；执行清单见第 7.3 节')
replace('总结相对两类基线的表现及模型差异、成本和自然风险边界；不另写一套结论',
        '综合五模型比较与专家证据，围绕根因定位、完整风险证据和紧凑子图总结方法价值；保留原结论主题与位置')
replace('主结果按 full-SCC＋LEA＋SA-MCGS 重组；不同覆盖范围分组/panel，替代单纯“旧表后追加 LEA”的安排',
        '五模型三方法完整主表，配规模对照及覆盖—压缩图；文字集中陈述代表性提升')
replace('36-post 的完整分解、采样与协议放附录；原 320 结果保留且与匹配子集分开',
        '五模型逐域、逐规模分解放附录；36-post 对照保留在专家配套位置')
replace('与主比较同处呈现，说明各模型面对 full-SCC / LEA 的实际表现',
        '与主比较同处呈现，以 GPT-4o、Qwen2.5-72B、Llama 和 Qwen3.5 的代表性提升串联结果')
replace('完整模型表可保留原附录位置；无 LEA 的模型不补造比较',
        '模型完整数值放主表；领域和规模分解沿用原附录位置')
replace('正式方法指标计算后补入', '沿用已完成的正式方法指标')
replace('方法指标完成后给紧凑对照表', '沿用已完成的方法指标紧凑对照表')

fig_start = donor.index('| 现有位置 / 标签 |')
fig_end = donor.index('\n### 7.3 文字与资产的执行对应', fig_start)
figures = donor[fig_start:fig_end].replace('### 7.2 保留并同步的专题表与附录', '**专题表与附录同步：**')
figure_section = '''### 7.3 本次新增：第八页之后的图表更新清单

以下页码按当前修订 PDF 定位，实际修改以 LaTeX 标签为准。先完成本方案，再从既有结果离线生成图表，接入论文。

''' + figures + '''
后续绘图入口为 `experiments/main_experiment/build_paper_assets.py`。先建立五模型三方法的明确数据映射，再替换旧脚本中的两方法和 selector 硬编码；输出到 `experiments/main_experiment/paper_assets/`。正文与附录使用同一套资产，模型顺序与第 4.2 节一致。

'''
insert_before('## 8. 专家审计：', figure_section)

replace('已对照冻结结果核对；专家统计附逐例来源、哈希、脚本和验证记录',
        '第 4.2 节五模型三方法共 60 个指标值固定；专家统计沿用原版本')
replace('作者核对版本，同期、跨批次描述和回放范围不混淆',
        '主表、图表及段落采用同一结果版本，60 个主表数值逐一核对')
replace('已写入当前 LaTeX，新增蓝色、旧文删除线；提供同源修订版和净稿',
        '本方案先按旧版逐处更新并标蓝；随后完成第 7.3 节图表和第八页之后文字，导出同源修订版及净稿')
replace('原故事线、章节顺序、贡献框架与冻结数据保留；待逐段审阅及压页',
        '保留原故事线、章节顺序与贡献框架；五模型结果和图表接入后逐段审阅及压页')
replace('这轮核验、离线统计和正文/附录增补已经落地，没有再跑原主实验。',
        '9 月 22 日的核验、专家离线统计和正文/附录增补已经落地。本次新增的五模型主比较与图表按本方案继续接入论文。')
replace('| 修完整旧 matched-160 剩余 13 项 LEA | 希望保留更广的两模型全基准公平比较时 | 先冻结剩余 identity 清单，再补对应 LEA 并重算；不是再跑 160，更不是重跑主 320；历史 SA 批次限制仍披露 |\n', '', block=True)
insert_before('### 9.3 重投修改说明怎样写',
        'LEA 补齐已完成，从待办中移除。本轮按已确认结果更新图表与文字。\n\n')
replace('原 320 数据保留，主结果按双基线重组。',
        '主结果更新为五模型各 80 案例、三方法比较。')
replace('full-SCC 与 LEA 作为两类主要基线贯穿核心比较；One-shot 与 oracle 分开，不把 LEA 子集写成全 320 覆盖。',
        'One-shot 与 LEA 作为两类主要基线贯穿五模型主表、规模图和案例图；模型与方法顺序一致。')
insert_before('- [ ] 新版 LaTeX 已编译和视觉检查，',
        '- [ ] 主表 15 行、60 个指标值与第 4.2 节一致，图表使用对应逐例结果。\n- [ ] 三方法规模图、覆盖—压缩图、预算参考线和同案例三列图已完成；预算 60 端点与对应最终 core 对齐。\n')

# All newly added relative references become usable absolute file links.
def absolutize(m):
    target = m[1]
    new_targets = {
        'manuscript_revision_20260925/output/pdf/MASTER_REVISION_PLAN_BLUE.pdf',
        'experiments/lea_full320_completion_20260923/RESULTS_ANALYSIS.json',
        'experiments/llama8b_three_methods_20260924/final_analysis.json',
        'experiments/kimi_qwen35_three_methods_20260924/parsing_recovery_audit_20260925/metricwise_results.json',
    }
    if target not in new_targets:
        return m[0]
    return '](' + str(BASE / target) + ')'
plain = re.sub(r'\]\(([^)]+)\)', absolutize, plain)
marked = re.sub(r'\]\(([^)]+)\)', absolutize, marked)

assert '<span' not in plain
assert not re.search(r'DeepSeek|Kimi|kimi(?!_)', plain)
assert main_table in plain
def section(text, start, end):
    return text[text.index(start):text.index(end)]
preserved = [
    ('### 2.1 ', '### 2.2 '),
    ('### 3.1 ', '### 3.2 '),
    ('### 3.3 ', '## 4.'),
    ('### 4.4 ', '## 5.'),
    ('## 8.', '## 9.'),
]
for start, end in preserved:
    assert section(baseline, start, end) == section(plain, start, end), start
    assert '<span' not in section(marked, start, end), start

css = '''
body{font:16px/1.75 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;max-width:1220px;margin:45px auto;padding:0 32px;color:#20252b}
h1{font-size:29px} h2{font-size:23px;margin-top:40px} h3{font-size:19px;margin-top:28px}
table{border-collapse:collapse;width:100%;font-size:14px;margin:18px 0;line-height:1.6}
th,td{border:1px solid #dce2e8;padding:9px 11px;text-align:left;vertical-align:top}th{background:#f3f6fa}
code{background:#f1f3f5;padding:1px 4px;border-radius:3px;font-size:13px;overflow-wrap:anywhere}
a{color:inherit;text-decoration:underline}blockquote{margin-left:0;padding:8px 18px;border-left:4px solid #90b7e7;background:#f5f9ff}
p,li{overflow-wrap:anywhere}
@media print{
body{font-size:10.5pt;line-height:1.55;margin:0;padding:0;max-width:none}
h1{font-size:21pt;margin:0 0 18pt}h2{font-size:15pt;margin-top:22pt;break-after:avoid}h3{font-size:12pt;margin-top:16pt;break-after:avoid}
p,li{orphans:3;widows:3}table{font-size:8.3pt;line-height:1.4;margin:12pt 0;break-inside:avoid}
table.review-table{break-inside:auto}table.review-table tr{break-inside:avoid}
th,td{padding:5pt 6pt}code{font-size:8.2pt}blockquote{padding:6pt 10pt}a{text-decoration:none}}
'''
body = markdown.markdown(marked, extensions=['tables', 'fenced_code', 'sane_lists'])
body = body.replace('<table>\n<thead>\n<tr>\n<th>编号 / 提出者</th>', '<table class="review-table">\n<thead>\n<tr>\n<th>编号 / 提出者</th>')
html = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>SA-MCGS：旧方案增量蓝字对照</title><style>' + css + '</style></head><body>' + body + '</body></html>'
(BASE / 'ARR_OCT2026_MASTER_REVISION_PLAN_ZH.md').write_text(plain)
(REV / 'MASTER_REVISION_PLAN_INCREMENTAL.md').write_text(plain)
(REV / 'MASTER_REVISION_PLAN_BLUE.html').write_text(html)
(REV / 'incremental_plan_changes.json').write_text(json.dumps(changes, ensure_ascii=False, indent=2))
validation = {
    'baseline': str(ORIGINAL),
    'baseline_sha256': hashlib.sha256(baseline.encode()).hexdigest(),
    'targeted_changes': len(changes),
    'unchanged_sections': preserved,
    'main_result_values_preserved': True,
    'plain_markdown_has_no_html_spans': True,
    'removed_models_not_in_discussion': True,
    'html_blue_spans': html.count('<span style="color: #1565c0;">'),
}
(REV / 'incremental_plan_validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2))
print(json.dumps(validation, ensure_ascii=False, indent=2))

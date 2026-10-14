"""Style the portable snapshot only; preserve data and all non-table prose."""
from pathlib import Path
from zipfile import ZipFile
from decimal import Decimal
import json
import re

OUT = Path(__file__).resolve().parent
SRC = OUT / 'source'
BASE = OUT.parent / 'arr_revision_20261002/SA_MCGS_Overleaf_revision.zip'
TABLE = re.compile(r'\\begin\{table\*?\}.*?\\end\{table\*?\}', re.S)
NUM = re.compile(r'(?<![A-Za-z])\d+(?:\.\d+)?')
FILES = ['acl_latex.tex', 'revision_main_results.tex', 'revision_main_analysis.tex',
         'revision_expert_appendix.tex', 'revision_breakdowns.tex', 'revision_experiments.tex']
AUDIT = []

STYLE = r'''% Shared table typography. All results remain the frozen manuscript values.
% ACL edition: white headers, selective method-row tint, captions below tables.
\usepackage{colortbl}
\definecolor{TableFocus}{HTML}{EDF4FA}
\newcommand{\tblbest}[1]{\textbf{#1}}
\newcommand{\tblsecond}[1]{\underline{#1}}
\newcolumntype{L}[1]{>{\raggedright\arraybackslash}p{#1}}
\newcolumntype{R}[1]{>{\raggedleft\arraybackslash}p{#1}}
'''

FOCUS_TABLES = {
    'tab:matched_main': 5,
    'tab:cost_main': 1,
    'tab:expert_new_quality': 2,
    'tab:appendix_breakdowns': 12,
    'tab:revision_cost_full': 4,
}


def focus_method_rows(block, label):
    """One pale tint identifies the method, independently of metric rankings."""
    if label not in FOCUS_TABLES:
        return block
    lines = block.splitlines()
    highlighted = 0
    for idx, cells in rows(block):
        if any(cell in [r'\samcgs{}', r'\textbf{\samcgs{}}', 'SA-MCGS', r'\textbf{SA-MCGS}'] for cell in cells):
            highlighted += 1
            for c, cell in enumerate(cells):
                if cell == r'\samcgs{}':
                    cells[c] = r'\textbf{\samcgs{}}'
                elif cell == 'SA-MCGS':
                    cells[c] = r'\textbf{SA-MCGS}'
            lines[idx] = r'\rowcolor{TableFocus}' + '\n' + ' & '.join(cells) + r' \\'
    assert highlighted == FOCUS_TABLES[label], (label, highlighted)
    return '\n'.join(lines)


def caption(block, new=None, suffix=None):
    start = block.index(r'\caption{') + len(r'\caption{')
    pos, depth = start, 1
    while depth:
        if block[pos] == '{' and block[pos - 1] != '\\': depth += 1
        if block[pos] == '}' and block[pos - 1] != '\\': depth -= 1
        pos += 1
    old = block[start:pos - 1]
    return block[:start] + (new if new is not None else old + ' ' + suffix) + block[pos - 1:]


def rows(block):
    """Data rows, excluding headers, section bands, and text outside tabulars."""
    result = []
    data = False
    for idx, line in enumerate(block.splitlines()):
        if r'\begin{tabular' in line: data = False
        if r'\midrule' in line: data = True
        if r'\bottomrule' in line or r'\end{tabular' in line: data = False
        if data and '&' in line and r'\\' in line and not line.lstrip().startswith(r'\multicolumn'):
            cells = [c.strip() for c in line.split(r'\\', 1)[0].split('&')]
            result.append((idx, cells))
    return result


def clean_num(cell):
    return re.sub(r'\\(?:textbf|tblbest|tblsecond)\{(\d+(?:\.\d+)?)\}', r'\1', cell)


def value(cell):
    m = NUM.search(clean_num(cell))
    assert m, cell
    return Decimal(m[0])


def rank(block, label, groups, columns, direction='max', across=False):
    lines = block.splitlines()
    data = rows(block)
    for group in groups:
        for col in columns:
            coords = [(r, col) for r in group] if not across else [(group[0], c) for c in columns]
            vals = [value(data[r][1][c]) for r, c in coords]
            ordered = sorted(set(vals), reverse=direction == 'max')
            for (r, c), val in zip(coords, vals):
                cell = clean_num(data[r][1][c])
                rank_no = ordered.index(val) + 1
                if rank_no <= 2:
                    macro = 'tblbest' if rank_no == 1 else 'tblsecond'
                    cell = NUM.sub(lambda m: '\\' + macro + '{' + m[0] + '}', cell, count=1)
                data[r][1][c] = cell
                AUDIT.append({'table': label, 'row': r, 'column': c, 'value': str(val),
                              'direction': direction, 'rank': rank_no, 'group': list(group),
                              'axis': 'row' if across else 'column'})
            if across: break
    for line_no, cells in data:
        lines[line_no] = ' & '.join(cells) + r' \\'
    return '\n'.join(lines)


def headers_and_groups(block, label):
    lines = block.splitlines()
    inside = head = False
    for idx, line in enumerate(lines):
        if r'\begin{tabular' in line: inside, head = True, True
        if r'\midrule' in line: head = False
        if r'\end{tabular' in line: inside, head = False, False
        if inside and head and '&' in line and r'\\' in line:
            cells = line.split(r'\\', 1)[0].split('&')
            for c, text in enumerate(cells):
                text = text.strip()
                if not text: continue
                if text.startswith(r'\multicolumn'):
                    text = re.sub(r'(\\multicolumn\{\d+\}\{[^}]+\}\{)', r'\1\\bfseries ', text)
                else:
                    text = r'\bfseries ' + text
                cells[c] = text
            lines[idx] = ' & '.join(cells) + r' \\'
        elif inside and not head and line.lstrip().startswith(r'\multicolumn'):
            line = re.sub(r'(\\multicolumn\{\d+\}\{[^}]+\}\{)', r'\1\\bfseries ', line)
            lines[idx] = line
    return '\n'.join(lines)


def caption_below(block):
    cap = block.index(r'\caption{')
    if cap > block.rindex(r'\end{tabular'): return block
    pos, depth = cap + len(r'\caption{'), 1
    while depth:
        if block[pos] == '{' and block[pos - 1] != '\\': depth += 1
        if block[pos] == '}' and block[pos - 1] != '\\': depth -= 1
        pos += 1
    labels = re.match(r'(?:\s*\\label\{[^}]+\})+', block[pos:])
    assert labels, 'Caption must move together with its labels'
    pos += labels.end()
    tail = block[cap:pos]
    block = block[:cap] + block[pos:]
    end = block.rindex(r'\end{table')
    return block[:end].rstrip() + '\n' + tail + '\n' + block[end:]


def style(block):
    original = block
    label = re.search(r'\\label\{(tab:[^}]+)\}', block)[1]
    n = len(rows(block))
    primary = label in ['tab:mcts_scc', 'tab:matched_main', 'tab:component_main', 'tab:cost_main']
    block = block.replace(r'\centering', r'\centering' + '\n' +
                          r'\renewcommand{\arraystretch}{' + ('1.02' if primary else '1.10') + '}', 1)
    # Every comparison has an explicit scope and direction in its caption.
    if label == 'tab:mcts_scc':
        block = block.replace(r'\scriptsize', r'\scriptsize' + '\n' + r'\setlength{\tabcolsep}{3pt}')
        block = rank(block, label, [[1, 2]], [2], 'min')
        block = rank(block, label, [[1, 2]], [5])
        block = caption(block, new=r'Cyclic-search ablation. Within SCC rows, bold and underlining mark best and second-best expansion ($\downarrow$) and Hit@3 ($\uparrow$); DAG is an acyclic reference.')
    elif label == 'tab:matched_main':
        block = rank(block, label, [list(range(i, i + 3)) for i in range(0, n, 3)], [2, 3, 4, 5])
        block = block.replace(r'\renewcommand{\arraystretch}{1.06}', '')
        # Fixed label widths keep models and methods aligned across groups.
        block = block.replace(r'@{\extracolsep{\fill}}llrrrr@{}', r'@{}L{.28\textwidth}L{.15\textwidth}rrrr@{}')
        block = block.replace(r'\begin{tabular*}{\textwidth}', r'\begin{tabular}').replace(r'\end{tabular*}', r'\end{tabular}')
        block = caption(block, new=r'Results on 80 matched injected variants per model (\%). Bold/underline: highest/second-highest within each model, including ties. Shading identifies \samcgs{}; higher compression means a smaller core.')
    elif label == 'tab:component_main':
        block = rank(block, label, [[0, 1, 2, 3], [4, 5]], [1])
        block = caption(block, new=r'GPT-4o ablations (\%). Stage-1: 17 variants/5 SEC sources; Stage-2: shared-trace replay on 80 variants/20 sources, with different controls. Bold/underline: best/next \riskall{} within each stage.')
    elif label == 'tab:cost_main':
        block = rank(block, label, [[0, 1, 2]], [1, 2])
        block = rank(block, label, [[0, 1, 2]], [3, 4], 'min')
        block = block.replace('GPT-4o & Pro &', 'GPT-4o & Gemini &')
        block = caption(block, new=r'Cost--performance: 12 sources, 72 runs, GPT-4o/Gemini 2.5 Pro. Strict \riskall{} ($\uparrow$); model-averaged calls/tokens ($\downarrow$) include recovery. Bold/underline: best/next per column. Shading: \samcgs{}.')
    elif label == 'tab:expert_new_quality':
        block = rank(block, label, [[0, 1, 2], [3, 4, 5]], [3, 4, 5])
        block = block.replace('Gemini Pro &', r'\midrule' + '\n' + 'Gemini Pro &')
        block = re.sub(r'\[(\d+\.\d+),(\d+\.\d+)\]', r'[\1,\,\2]', block)
        block = caption(block, suffix=r'Bold/underline: best/next point estimate within each model ($\uparrow$), not statistical significance.')
    elif label == 'tab:appendix_breakdowns':
        block = rank(block, label, [list(range(i, i + 3)) for i in range(0, n, 3)], [3, 4, 5, 6])
        # Stack all panels at readable size instead of squeezing two into half-width.
        block = block.replace(r'\fontsize{7.5}{9}\selectfont', r'\fontsize{9}{10}\selectfont')
        block = block.replace(r'\setlength{\tabcolsep}{2pt}', r'\setlength{\tabcolsep}{5pt}')
        block = block.replace(r'\renewcommand{\arraystretch}{1.08}', r'\renewcommand{\arraystretch}{1.02}')
        block = re.sub(r'\\begin\{minipage\}\[t\]\{\.49\\textwidth\}\s*\\centering', '', block)
        block = block.replace(r'\end{minipage}\hfill', r'\par\medskip').replace(r'\end{minipage}', '')
        block = block.replace(r'\begin{tabular}{@{}llrrrrr@{}}', r'\begin{tabular}{L{.25\textwidth}L{.12\textwidth}R{.05\textwidth}*{4}{R{.09\textwidth}}}')
        block = caption(block, new=r'Five-model results by model, domain, and original SCC size. Metrics are percentages; domain and size summaries pool the same five models. Bold/underline mark highest/next distinct values within each group, including ties. Higher compression means a smaller core.')
    elif label == 'tab:revision_stage1':
        block = rank(block, label, [list(range(4)), list(range(4, 8))], [1, 2, 3])
        block = block.replace(r'\setlength{\tabcolsep}{8pt}', r'\setlength{\tabcolsep}{6pt}')
        block = caption(block, suffix=r'Bold/underline: best/next endpoint metric within each panel, including ties; core size and compression are descriptive.')
    elif label == 'tab:revision_stage1_cost':
        block = rank(block, label, [list(range(4))], [1, 2, 3, 4], 'min')
        block = caption(block, suffix=r'Bold/underline: lowest/next distinct cost per column.')
    elif label == 'tab:revision_stage2':
        block = block.replace(r'\setlength{\tabcolsep}{3pt}', r'\setlength{\tabcolsep}{4pt}')
        block = rank(block, label, [[0, 1]], [1, 2, 3])
        block = caption(block, suffix=r'Bold/underline: best/next endpoint metric ($\uparrow$), including ties.')
    elif label == 'tab:revision_cost_full':
        block = rank(block, label, [[0, 1, 2], [3, 4, 5]], [4, 5, 6])
        block = rank(block, label, [[6, 7, 8], [9, 10, 11]], [2, 3, 4, 5, 6, 7], 'min')
        block = block.replace('Gemini 2.5 Pro &', r'\midrule' + '\n' + 'Gemini 2.5 Pro &')
        block = caption(block, suffix=r'Within each model, bold/underline mark best/next endpoint rates ($\uparrow$, upper panel) or costs ($\downarrow$, lower panel); compression and validity are descriptive.')
    elif label == 'tab:revision_prior':
        block = rank(block, label, [[i] for i in range(4)], [2, 3, 4], across=True)
        block = block.replace('Gemini Pro &', r'\midrule' + '\n' + 'Gemini Pro &')
        block = caption(block, suffix=r'Bold/underline: highest/next distinct value across settings in each row, including ties.')
    elif label == 'tab:expert_new_agreement':
        for pair in ['E1/E3', 'E2/E3']:
            block = block.replace(pair + ' &', r'\midrule' + '\n' + pair + ' &')
    elif label == 'tab:expert_pre_negative':
        block = block.replace('Gemini Pro &', r'\midrule' + '\n' + 'Gemini Pro &')
    # Text tables: flush-left prose, bold headers, consistent type hierarchy.
    prose_tables = ['tab:expert_audit_results', 'tab:expert_protocol', 'tab:expert_example',
                   'tab:prior_coefficients', 'tab:dataset_processing', 'tab:injection_templates']
    if label in prose_tables:
        block = re.sub(r'p\{(\.\d+\\textwidth)\}', r'L{\1}', block)
        if label == 'tab:prior_coefficients':
            block = block.replace(r'L{.10\textwidth}', r'R{.10\textwidth}')
        else:
            lines = block.splitlines()
            for idx, cells in rows(block):
                cells[0] = r'\textbf{' + cells[0] + '}'
                lines[idx] = ' & '.join(cells) + r' \\'
            block = '\n'.join(lines)
        if label in ['tab:dataset_processing', 'tab:injection_templates']:
            block = block.replace(r'\scriptsize', r'\footnotesize')
        if label == 'tab:injection_templates':
            block = block.replace(r'\_', r'\_\allowbreak ')
        lines = block.splitlines()
        for idx, _ in rows(block)[:-1]:
            lines[idx] += '\n' + r'\addlinespace[1.5pt]'
        block = '\n'.join(lines)
    # Retain consistent outer cell padding inside the booktabs rules.
    block = block.replace('@{}', '')
    # Use one caption convention for first and second distinct ranks.
    block = block.replace('best/next', 'best/second-best').replace('highest/next', 'highest/second-highest').replace('lowest/next', 'lowest/second-lowest')
    block = headers_and_groups(block, label)
    if label in FOCUS_TABLES and label not in ['tab:matched_main', 'tab:cost_main']:
        block = caption(block, suffix=r'Shading identifies \samcgs{}.')
    block = focus_method_rows(block, label)
    block = caption_below(block)
    # Exact numeric tokens per data cell, including all interval bounds and counts.
    before, after = rows(original), rows(block)
    assert len(before) == len(after), label
    for (_, aa), (_, bb) in zip(before, after):
        assert len(aa) == len(bb), label
        for a, b in zip(aa, bb):
            assert NUM.findall(a) == NUM.findall(b), (label, a, b)
    return block


def main():
    stats = []
    with ZipFile(BASE) as z:
        for name in FILES:
            old = z.read(name).decode()
            new = TABLE.sub(lambda m: style(m[0]), old)
            assert TABLE.sub('', old) == TABLE.sub('', new), name
            if name == 'acl_latex.tex':
                new = new.replace(r'\usepackage{placeins}', r'\usepackage{placeins}' + '\n' + r'\input{table_style}')
            (SRC / name).write_text(new)
            stats.extend({'file': name, 'label': re.search(r'\\label\{(tab:[^}]+)\}', t)[1],
                          'rows': len(rows(t))} for t in TABLE.findall(old))
    assert len(stats) == 19
    (SRC / 'table_style.tex').write_text(STYLE)
    (OUT / 'qa/table_inventory.json').write_text(json.dumps(stats, indent=2))
    (OUT / 'qa/ranking_audit.json').write_text(json.dumps(AUDIT, indent=2))
    print(json.dumps({'tables':len(stats), 'ranked_cells': len(AUDIT),
                      'data_cells_unchanged':True, 'non_table_prose_unchanged':True}))


if __name__ == '__main__':
    main()

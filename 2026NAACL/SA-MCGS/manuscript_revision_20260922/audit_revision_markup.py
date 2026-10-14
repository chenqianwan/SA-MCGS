"""Read-only source QA; counts are approximate prose/caption/table words, not TeXcount."""
from pathlib import Path
import difflib
import re

ROOT = Path(__file__).resolve().parents[3]
CURRENT = ROOT / 'paper/latex'
BASE = ROOT / '2026NAACL/SA-MCGS/backups/latex_2026-09-22'

def uncomment(s):
    return re.sub(r'(?<!\\)%[^\n]*', '', s)

def arg(s, p):
    while s[p].isspace(): p += 1
    assert s[p] == '{', (p, s[p:p+60])
    start = p + 1
    depth = 1
    p += 1
    while depth:
        if s[p] == '\\':
            p += 2
            continue
        if s[p] == '{': depth += 1
        elif s[p] == '}': depth -= 1
        p += 1
    return s[start:p-1], p

def view(s, mode, directory):
    s = uncomment(s)
    out = []
    p = 0
    pattern = re.compile(r'\\(revadd|revdel|revreplace|input)\b|\\begin\{revadded\}')
    while m := pattern.search(s, p):
        out.append(s[p:m.start()])
        if m.group(0) == r'\begin{revadded}':
            end = s.index(r'\end{revadded}', m.end())
            content = s[m.end():end]
            if mode == 'clean': out.append(view(content, mode, directory))
            p = end + len(r'\end{revadded}')
            continue
        kind = m.group(1)
        a, p = arg(s, m.end())
        if kind == 'revreplace':
            b, p = arg(s, p)
            out.append(view(a if mode == 'old' else b, mode, directory))
        elif kind == 'revadd':
            if mode == 'clean': out.append(view(a, mode, directory))
        elif kind == 'revdel':
            if mode == 'old': out.append(view(a, mode, directory))
        else:
            if a == 'revision_markup': continue
            path = directory / (a if a.endswith('.tex') else a + '.tex')
            out.append(view(path.read_text(), mode, directory))
    out.append(s[p:])
    return ''.join(out)

def body(s):
    return s.split(r'\begin{document}', 1)[1].split(r'\end{document}', 1)[0]

def normalize(s):
    # A newly added subsection leaves an empty structural command only in old view.
    s = re.sub(r'\\(?:sub)*section\*?\{\s*\}', '', s)
    return re.findall(r'\\[A-Za-z]+|\\.|[^\s]', s)

def prose(s):
    for macro, text in {'samcgs':'SA-MCGS', 'scc':'SCC', 'naive':'Naive', 'rootthree':'Root@3', 'riskany':'Risk-any', 'riskall':'Risk-all', 'oc':'OC'}.items():
        s = re.sub(r'\\' + macro + r'\b\{\}', text, s)
    s = re.sub(r'\\begin\{(equation\*?|align\*?|algorithm|tabular)\}.*?\\end\{\1\}', '', s, flags=re.S)
    s = re.sub(r'\$[^$]*\$', '', s)
    s = re.sub(r'\\(?:label|ref|eqref|cite\w*|bibliography|includegraphics|begin|end)(?:\[[^\]]*\])?\{[^{}]*\}', '', s)
    s = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?', ' ', s)
    return re.findall(r"[A-Za-z]+(?:[-'][A-Za-z0-9]+)*|\d+(?:\.\d+)?", s)

def counts(s):
    headings = list(re.finditer(r'\\section(\*)?\{', s))
    result = {'Abstract': len(prose(s[:headings[0].start()]))}
    for i, m in enumerate(headings):
        name, start = arg(s, m.end()-1)
        end = headings[i+1].start() if i+1 < len(headings) else len(s)
        result[name] = len(prose(s[start:end]))
    return result

baseline = body(uncomment((BASE/'acl_latex.tex').read_text()))
source = body((CURRENT/'acl_latex.tex').read_text())
old = view(source, 'old', CURRENT)
clean = view(source, 'clean', CURRENT)
before, recovered = normalize(baseline), normalize(old)
print('Old-view normalized source exact match:', before == recovered)
if before != recovered:
    for tag, a, b, c, d in difflib.SequenceMatcher(None, before, recovered, autojunk=False).get_opcodes():
        if tag != 'equal': print(tag, 'BASE:', ''.join(before[a:b])[:1000], 'RECOVERED:', ''.join(recovered[c:d])[:1000])
print('Clean unresolved revision/input commands:', re.findall(r'\\(?:revadd|revdel|revreplace|input)\b', clean))
print('Clean empty headings:', re.findall(r'\\(?:sub)*section\*?\{\s*\}', clean))
for path in sorted(CURRENT.glob('revision_*.tex')):
    if path.name == 'revision_markup.tex': continue
    remainder = view(path.read_text(), 'old', CURRENT).strip()
    print('Unmarked new-file remainder:', path.name, repr(remainder[:500]))
old_counts, new_counts = counts(baseline), counts(clean)
print('Approximate per-section counts (exclude display equations, algorithms, tabular; retain captions):')
for key in dict.fromkeys([*old_counts, *new_counts]):
    print(f'{key}: {old_counts.get(key, 0)} -> {new_counts.get(key, 0)}')
print('TOTAL:', sum(old_counts.values()), '->', sum(new_counts.values()))

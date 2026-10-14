"""Assemble the current manuscript's portable source dependencies only."""
from pathlib import Path
import hashlib
import json
import re
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PAPER = ROOT / 'paper/latex'
DEST = HERE / 'SA_MCGS_Overleaf'
DEST.mkdir(exist_ok=True)

def uncomment(text):
    return re.sub(r'(?<!\\)%[^\n]*', '', text)

sources = set()
figures = set()
pending = ['acl_latex.tex']
while pending:
    name = pending.pop()
    if name in sources:
        continue
    source = PAPER / name
    assert source.is_file(), source
    sources.add(name)
    text = uncomment(source.read_text())
    for dep in re.findall(r'\\(?:input|include)\{([^}]+)\}', text):
        assert '#' not in dep and '\\' not in dep, dep
        pending.append(dep if dep.endswith('.tex') else dep + '.tex')
    figures.update(x for x in re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}', text) if '#' not in x)
    for old, new in re.findall(r'\\revfigure\{([^}]+)\}\{([^}]+)\}', text):
        figures.update([old, new])

files = sources | figures | {'acl.sty', 'acl_natbib.bst', 'custom.bib'}
manifest = {}
for name in sorted(files):
    source = PAPER / name
    assert source.is_file(), source
    target = DEST / name
    assert target.resolve().is_relative_to(DEST.resolve()), name
    target.parent.mkdir(parents=True, exist_ok=True)
    if name == 'acl_latex.tex':
        text = source.read_text()
        old = r'\graphicspath{{../../experiments/main_experiment/paper_assets/figures/}}'
        assert text.count(old) == 1
        target.write_text(text.replace(old, r'\graphicspath{{./}}'))
    else:
        shutil.copy2(source, target)
    manifest[name] = {
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'packaged_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
    }

(DEST / 'main.tex').write_text('% Clean manuscript. Compile with XeLaTeX and BibTeX.\n\\def\\CleanRevisionVersion{1}\n\\input{acl_latex.tex}\n')
(DEST / 'marked.tex').write_text('% Optional view with revision marks.\n\\input{acl_latex.tex}\n')
(DEST / 'README.txt').write_text('SA-MCGS — Overleaf source, 2026-10-13\n\n'
    '本文件夹包含当前论文、最新五模型预算对比、新增的五篇参考文献及附录排版优化。\n'
    '将文件夹内的全部文件和子文件夹上传到 Overleaf，并保留目录结构。\n'
    '主文件选择 main.tex，编译器选择 XeLaTeX。\n'
    '如需显示修订标记，主文件改选 marked.tex。\n'
    '参考文献使用 BibTeX；Overleaf 会自动处理。\n\n'
    'Main document: main.tex. Compiler: XeLaTeX. Bibliography: BibTeX.\n'
    'Optional marked view: marked.tex. No Python execution is required.\n')
(HERE / 'source_manifest.json').write_text(json.dumps({
    'source': str(PAPER), 'destination': str(DEST),
    'source_tex_files': len(sources), 'figure_files': len(figures),
    'files': manifest,
    'only_manuscript_transformation': 'Replace the repository-relative graphics search path with ./.'
}, indent=2) + '\n')
print(json.dumps({'folder': str(DEST), 'tex_sources': len(sources), 'figures': len(figures),
                  'total_files': sum(p.is_file() for p in DEST.rglob('*'))}, indent=2))

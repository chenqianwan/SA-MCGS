"""Make a portable clean-paper copy highlighting only this data update."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PAPER = ROOT / 'paper/latex'
PORTABLE = ROOT / 'output/overleaf_release_20261013/SA_MCGS_Overleaf'
SOURCE = HERE / 'blue_review_source'
BUILD = HERE / 'build_blue_review'
FINAL = ROOT / 'output/pdf/SA_MCGS_natural_case_update_blue.pdf'
BIN = Path('/private/tmp/samcgs_texlive_20261009/TinyTeX/bin/universal-darwin')
for p in (SOURCE, BUILD, FINAL.parent):
    p.mkdir(parents=True, exist_ok=True)
shutil.copytree(PORTABLE, SOURCE, dirs_exist_ok=True)
manifest = {
    'canonical_source': str(PAPER),
    'canonical_clean_pdf_sha256': hashlib.sha256((PAPER / 'acl_latex_clean.pdf').read_bytes()).hexdigest(),
    'canonical_sources': {}, 'highlights': []
}
for path in PORTABLE.rglob('*'):
    if not path.is_file() or path.name in ('main.tex', 'marked.tex', 'README.txt'):
        continue
    relative = path.relative_to(PORTABLE)
    canonical = PAPER / relative
    assert canonical.is_file(), relative
    data = canonical.read_bytes()
    expected = data
    if path.name == 'acl_latex.tex':
        expected = data.replace(b'\\graphicspath{{../../experiments/main_experiment/paper_assets/figures/}}', b'\\graphicspath{{./}}')
    assert expected == path.read_bytes(), f'Portable source out of sync: {relative}'
    manifest['canonical_sources'][str(relative)] = hashlib.sha256(data).hexdigest()

def blue(text):
    return '\\caseupdateblue{' + text + '}'

def highlight(path, text):
    original = path.read_text()
    assert original.count(text) == 1, (path.name, text)
    path.write_text(original.replace(text, blue(text)))
    manifest['highlights'].append({'file': path.name, 'text': text})

highlight(SOURCE / 'revision_expert_main.tex',
    r'Among the unmodified sources, experts identify 15 risk and three no-risk cases. \samcgs{} flags all 15 risk cases with both models, matching expert judgments on 18/18 (100.0\%) with GPT-4o and 15/18 (83.3\%) with Gemini 2.5 Pro.')
appendix = SOURCE / 'revision_expert_appendix.tex'
highlight(appendix, 'The final unmodified-source labels contain 15 risk cases and three no-risk cases.')
highlight(appendix, r'Table~\ref{tab:expert_pre_negative} evaluates case-level risk judgments against the 15 risk and three no-risk expert labels.')
highlight(appendix,
    r'Both SA-MCGS backbones flag all 15 expert-identified risk cases. GPT-4o also correctly identifies all three no-risk cases, yielding 18/18 agreement and no false alarms; Gemini 2.5 Pro yields 15/18 agreement and three false alarms. Overall error rates are 0.0\% and 16.7\%, respectively. False-positive rates among the three no-risk cases are 0.0\% and 100.0\%.')

# Color changed numeric cells in risk agreement and model outcomes.
current = (PAPER / 'revision_expert_appendix.tex').read_text().splitlines()
before = (HERE / 'before/revision_expert_appendix.tex').read_text().splitlines()
assert len(current) == len(before)
cell_count = 0
for line_index, (old, new) in enumerate(zip(before, current)):
    if old == new or ' & ' not in new:
        continue
    assert new.endswith(r' \\') and old.endswith(r' \\'), new
    old_cells = old[:-3].split(' & ')
    new_cells = new[:-3].split(' & ')
    assert len(old_cells) == len(new_cells) and len(new_cells) in (4, 7)
    changed = []
    for i, (previous, value) in enumerate(zip(old_cells, new_cells)):
        if previous != value:
            assert i in ((2, 3) if len(new_cells) == 4 else (3, 5, 6)), (i, previous, value)
            new_cells[i] = blue(value)
            changed.append(i)
            cell_count += 1
    marked = ' & '.join(new_cells) + r' \\'
    lines = appendix.read_text().splitlines(keepends=True)
    assert lines[line_index].rstrip('\n') == new
    lines[line_index] = marked + '\n'
    appendix.write_text(''.join(lines))
    manifest['highlights'].append({'file': appendix.name, 'row': new, 'columns_zero_based': changed})
assert cell_count == 37, cell_count

markup = SOURCE / 'revision_markup.tex'
markup.write_text(markup.read_text() + '\n\\DeclareRobustCommand{\\caseupdateblue}[1]{\\leavevmode{\\color{blue}#1}}\n')
(SOURCE / 'main.tex').write_text('\\def\\CleanRevisionVersion{1}\n\\input{acl_latex.tex}\n')
(SOURCE / 'README.txt').write_text(
    'Current manuscript review copy. Main document: main.tex. Compiler: XeLaTeX.\n'
    'Blue identifies the natural-case result changes; all other revision markup is disabled.\n'
    'The canonical manuscript remains in paper/latex.\n')

env = os.environ.copy()
env['PATH'] = str(BIN) + os.pathsep + env['PATH']
env['BIBINPUTS'] = str(SOURCE) + os.pathsep
env['BSTINPUTS'] = str(SOURCE) + os.pathsep
stem = 'SA_MCGS_natural_case_update_blue'
command = [str(BIN / 'xelatex'), '-interaction=nonstopmode', '-halt-on-error',
    '-file-line-error', '-jobname=' + stem, '-output-directory=' + str(BUILD), 'main.tex']
steps = [('pass1', command, SOURCE), ('bibtex', [str(BIN / 'bibtex'), stem], BUILD)]
steps += [(f'pass{i}', command, SOURCE) for i in (2, 3, 4)]
for name, cmd, cwd in steps:
    with (BUILD / (name + '.stdout')).open('w') as stream:
        result = subprocess.run(cmd, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print((BUILD / (name + '.stdout')).read_text()[-6000:], flush=True)
        raise RuntimeError(f'{name} failed')
    print(name + ': OK', flush=True)
log = (BUILD / (stem + '.log')).read_text()
assert not re.search(r'Overfull \\[hv]box|LaTeX Warning: .*undefined|There were undefined references', log)
shutil.copy2(BUILD / (stem + '.pdf'), FINAL)
manifest['output'] = str(FINAL)
manifest['output_sha256'] = hashlib.sha256(FINAL.read_bytes()).hexdigest()
(HERE / 'blue_review_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(str(FINAL), flush=True)

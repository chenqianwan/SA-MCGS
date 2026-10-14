"""Check the focused revision and render its changed manuscript pages."""
from pathlib import Path
import hashlib
import json
import re
from pypdf import PdfReader
import pypdfium2 as pdfium

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PAPER = ROOT / 'paper/latex'
BEFORE = HERE / 'before'
QA = HERE / 'qa'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
names = ['revision_equal_budget_main.tex', 'revision_equal_budget_table.tex',
         'revision_equal_budget_appendix.tex', 'revision_experiments.tex']
for name in names[:3]:
    text = (PAPER / name).read_text()
    assert not re.search(r'(?i)fail\w*|invalid|valid output|three.run|three runs|three complete|sample SD|standard deviation|503|recovery|retr(?:y|ies)|tab:equal_budget_three_wave|\\pm', text), name
for name in ['acl_latex.tex', 'acl_latex_clean.tex']:
    assert sha(PAPER / name) == sha(BEFORE / name), name
old = (BEFORE / 'revision_experiments.tex').read_text().splitlines()
new = (PAPER / 'revision_experiments.tex').read_text().splitlines()
assert len(old) == len(new)
assert [i+1 for i, (a, b) in enumerate(zip(old, new)) if a != b] == [28]
rows = json.loads((PAPER / 'figures_equal_budget_20261012/figure_source_data.json').read_text())
assert len(rows) == 15
table = (PAPER / 'revision_equal_budget_table.tex').read_text()
data_lines = [s for s in table.splitlines() if re.search(r' & (?:LEA|Full-SCC|\\textbf)', s)]
assert len(data_lines) == 15
models = ['gpt4o', 'qwen25', 'llama', 'qwen35', 'kimi']
methods = ['lea', 'full-scc', 'sa-mcgs']
metrics = ['root_at_3_percent', 'risk_any_percent', 'risk_all_percent', 'compression_percent']
lookup = {(r['model'], r['method']): r for r in rows}
for line, (model, method) in zip(data_lines, [(m, n) for m in models for n in methods]):
    cells = line.split(' & ')[2:]
    actual = [re.search(r'\d+\.\d+', cell).group() for cell in cells]
    assert actual == [f'{lookup[(model, method)][key]:.2f}' for key in metrics]
report = {'changed_source_files': names, 'source_hashes': {n: sha(PAPER/n) for n in names},
          'metric_values_verified': 60, 'unrelated_source_preserved': True, 'builds': {}}
for view, stem in [('clean', 'acl_latex_clean'), ('marked', 'acl_latex')]:
    dest = HERE / ('build_' + view)
    log = (dest / (stem + '.log')).read_text(errors='replace')
    issues = [s for s in log.splitlines() if any(w in s for w in ['Overfull', 'undefined', 'too large', 'multiply defined'])]
    assert not issues, (view, issues)
    labels = {k: (n, int(pg)) for k, n, pg in re.findall(r'\\newlabel\{([^}]+)\}\{\{([^}]*)\}\{(\d+)\}', (dest / (stem + '.aux')).read_text())}
    pdf = PdfReader(dest / (stem + '.pdf'))
    texts = [p.extract_text() for p in pdf.pages]
    pages = sorted({labels[n][1] for n in ['fig:equal_budget_tradeoff', 'tab:equal_budget_five_models', 'app:equal_budget', 'sec:conclusion']} | ({6, 8} if view == 'clean' else set()))
    document = pdfium.PdfDocument(str(dest / (stem + '.pdf')))
    for number in pages:
        page = document[number-1]
        bitmap = page.render(scale=1.6)
        bitmap.to_pil().save(QA / f'{view}_page_{number:02d}.png')
        page.close()
    document.close()
    assert all(len(t.strip()) > 80 for t in texts), 'Unexpected empty page'
    report['builds'][view] = {'pages': len(pdf.pages), 'warnings': issues,
                             'sha256': sha(dest / (stem + '.pdf')), 'rendered_pages': pages,
                             'labels': {k: labels[k] for k in ['fig:equal_budget_tradeoff', 'tab:equal_budget_five_models', 'sec:conclusion', 'sec:limitations', 'app:equal_budget']}}
(QA / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

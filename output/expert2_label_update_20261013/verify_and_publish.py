from pathlib import Path
from pypdf import PdfReader
import json, shutil, hashlib, subprocess

ROOT = Path('/Users/chenlong/WorkSpace/MCGS_Law')
OUT = Path(__file__).resolve().parent
ANALYSIS = ROOT / '2026NAACL/SA-MCGS/manuscript_revision_20261010/pre_reannotation_analysis'
checks = {}
for view, stem, final in [('clean', 'acl_latex_clean', 'SA_MCGS_clean'),
                          ('marked', 'acl_latex', 'SA_MCGS_marked')]:
    new = OUT / f'build_{view}' / (stem + '.pdf')
    old = OUT / 'before' / (stem + '.pdf')
    log = (new.parent / (stem + '.log')).read_text()
    bad = [s for s in log.splitlines() if any(t in s for t in
           ['Overfull', 'undefined', 'multiply defined', 'Float too large'])]
    assert not bad, bad
    x, y = PdfReader(old), PdfReader(new)
    assert len(x.pages) == len(y.pages)
    norm = lambda p: ''.join(p.extract_text().split())
    changed = [i+1 for i, (p, q) in enumerate(zip(x.pages, y.pages)) if norm(p) != norm(q)]
    expected = 15 if view == 'clean' else 18
    assert changed == [expected], (view, changed)
    before, after = norm(x.pages[expected-1]), norm(y.pages[expected-1])
    before = before.replace('Existence13/180.444', 'Existence15/180.620')
    before = before.replace('Existence37/420.557', 'Existence39/420.690')
    assert before == after, (view, 'Unexpected text change')
    shutil.copy2(new, ROOT / 'paper/latex' / (stem + '.pdf'))
    shutil.copy2(new, OUT / (final + '.pdf'))
    checks[view] = {'pages': len(y.pages), 'changed_pages': changed,
                    'only_table8_risk_agreement_values_changed': True,
                    'no_overfull_or_reference_errors': True}
(OUT / 'pdf_checks.json').write_text(json.dumps(checks, indent=2) + '\n')
sync = json.loads((ANALYSIS / 'manuscript_data_sync.json').read_text())
for entry in sync['manuscript_sources'] + sync['pdf_outputs']:
    entry['sha256'] = hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()
sync['agreement_source'] = {'path': str(ANALYSIS / 'agreement.json'),
    'sha256': hashlib.sha256((ANALYSIS / 'agreement.json').read_bytes()).hexdigest()}
sync['pdf_checks'] = str(OUT / 'pdf_checks.json')
sync['e1_e2_risk_agreement'] = {'pre': {'agree': 15, 'n': 18, 'kappa_rounded': .620},
                              'all': {'agree': 39, 'n': 42, 'kappa_rounded': .690}}
(ANALYSIS / 'manuscript_data_sync.json').write_text(json.dumps(sync, indent=2) + '\n')
subprocess.run(['python3', str(ANALYSIS / 'refresh_current_decisions.py')], check=True,
               stdout=subprocess.DEVNULL)
subprocess.run(['python3', str(ROOT / 'output/overleaf_release_20261013/prepare_folder.py')], check=True)
print(json.dumps(checks, indent=2))

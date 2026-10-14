"""Build both portable entry points and compare them to the approved PDFs."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
import subprocess
import pypdfium2 as pdfium
from pypdf import PdfReader
from PIL import ImageChops, ImageStat

HERE = Path(__file__).resolve().parent
PACKAGE = HERE / 'SA_MCGS_Overleaf'
ROOT = HERE.parents[1]
REFERENCE = ROOT / 'output/expert2_label_update_20261013'
BIN = Path('/private/tmp/samcgs_texlive_20261009/TinyTeX/bin/universal-darwin')
env = os.environ.copy()
env['PATH'] = str(BIN) + os.pathsep + env['PATH']
env['TEXINPUTS'] = str(PACKAGE) + os.pathsep
env['BIBINPUTS'] = str(PACKAGE) + os.pathsep
env['BSTINPUTS'] = str(PACKAGE) + os.pathsep

def build(stem):
    dest = HERE / ('build_' + stem)
    dest.mkdir(exist_ok=True)
    cmd = [str(BIN / 'xelatex'), '-interaction=nonstopmode', '-halt-on-error',
           '-file-line-error', '-recorder', '-output-directory=' + str(dest), stem + '.tex']
    steps = [('pass1', cmd), ('bibtex', [str(BIN / 'bibtex'), stem]),
             ('pass2', cmd), ('pass3', cmd)]
    for name, args in steps:
        with (dest / (name + '.stdout')).open('w') as stream:
            result = subprocess.run(args, cwd=dest if name == 'bibtex' else PACKAGE,
                                    env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError((dest / (name + '.stdout')).read_text()[-5000:])
    log = (dest / (stem + '.log')).read_text()
    # Use explicit line checks; TeX can wrap long warning messages.
    bad = [line for line in log.splitlines() if any(s in line for s in
           ['Overfull', 'undefined', 'multiply defined', 'Float too large'])]
    assert not bad, bad
    forbidden_inputs = [line for line in (dest / (stem + '.fls')).read_text().splitlines()
                        if line.startswith('INPUT ') and '/WorkSpace/MCGS_Law/paper/' in line]
    assert not forbidden_inputs, forbidden_inputs
    print(stem + ': compilation passed', flush=True)
    return dest / (stem + '.pdf')

with ThreadPoolExecutor(max_workers=2) as pool:
    results = dict(zip(['main', 'marked'], pool.map(build, ['main', 'marked'])))

checks = {}
for stem, output in results.items():
    old = REFERENCE / ('SA_MCGS_clean.pdf' if stem == 'main' else 'SA_MCGS_marked.pdf')
    readers = [PdfReader(p) for p in [old, output]]
    assert len(readers[0].pages) == len(readers[1].pages)
    normalize = lambda page: re.sub(r'\s+', '', page.extract_text())
    assert [normalize(p) for p in readers[0].pages] == [normalize(p) for p in readers[1].pages]
    docs = [pdfium.PdfDocument(str(p)) for p in [old, output]]
    pixel_error_by_page = []
    qa = HERE / 'qa'
    qa.mkdir(exist_ok=True)
    for i in range(len(docs[0])):
        bitmaps = [d[i].render(scale=1).to_pil().convert('RGB') for d in docs]
        assert bitmaps[0].size == bitmaps[1].size
        # Recompiling under a new job name changes PDF coordinate rounding slightly.
        # Require matching page content plus negligible full-page rendered error.
        error = max(ImageStat.Stat(ImageChops.difference(*bitmaps)).mean)
        pixel_error_by_page.append(error)
        assert error < 0.25, (stem, i + 1, error)
        if (stem == 'main' and i + 1 in [7, 8, 29]) or (stem == 'marked' and i + 1 in [10, 35]):
            docs[1][i].render(scale=1.5).to_pil().save(qa / f'{stem}_page_{i+1}.png')
    for d in docs:
        d.close()
    checks[stem] = {'pages': len(readers[1].pages), 'text_matches_current_pdf_ignoring_whitespace': True,
                    'maximum_page_mean_pixel_error_0_to_255': max(pixel_error_by_page),
                    'render_comparison_passed': True,
                    'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
    print(stem + ': all pages match the current manuscript', flush=True)

assert not any(p.suffix in ['.aux', '.log', '.out', '.bbl', '.blg', '.zip'] for p in PACKAGE.rglob('*'))
(HERE / 'verification.json').write_text(json.dumps(checks, indent=2) + '\n')
print(json.dumps(checks, indent=2), flush=True)

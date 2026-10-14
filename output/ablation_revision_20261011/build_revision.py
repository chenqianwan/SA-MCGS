"""Compile this multi-file manuscript using its existing local TeX runtime."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
SOURCE = ROOT / 'paper/latex'
BIN = Path('/private/tmp/samcgs_texlive_20261009/TinyTeX/bin/universal-darwin')
VIEWS = {
    'blue': ('acl_latex_ablation_blue.tex', 'SA_MCGS_ablation_blue'),
    'clean': ('acl_latex_clean.tex', 'SA_MCGS_clean'),
    'marked': ('acl_latex.tex', 'SA_MCGS_marked'),
}


def build(view):
    source, job = VIEWS[view]
    dest = OUT / ('build_' + view)
    dest.mkdir(exist_ok=True)
    env = os.environ.copy()
    env['PATH'] = str(BIN) + os.pathsep + env['PATH']
    env['BIBINPUTS'] = str(SOURCE) + os.pathsep
    env['BSTINPUTS'] = str(SOURCE) + os.pathsep
    cmd = [str(BIN / 'xelatex'), '-interaction=nonstopmode', '-halt-on-error',
           '-file-line-error', '-recorder', '-output-directory=' + str(dest),
           '-jobname=' + job, source]
    sequence = [('pass1', cmd, SOURCE),
                ('bibtex', [str(BIN / 'bibtex'), job], dest)]
    sequence += [(f'pass{i}', cmd, SOURCE) for i in (2, 3, 4)]
    steps = []
    for label, command, cwd in sequence:
        start = time.monotonic()
        with (dest / (label + '.stdout')).open('w') as log:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=log,
                                    stderr=subprocess.STDOUT)
        steps.append({'step': label, 'returncode': result.returncode,
                      'seconds': round(time.monotonic() - start, 2)})
        if result.returncode:
            print((dest / (label + '.stdout')).read_text()[-5000:], flush=True)
            raise RuntimeError(f'{view}: {label}')
    pdf = dest / (job + '.pdf')
    final = OUT / (job + '.pdf')
    final.write_bytes(pdf.read_bytes())
    report = {'view': view, 'steps': steps, 'pdf': str(final),
              'sha256': hashlib.sha256(final.read_bytes()).hexdigest()}
    (dest / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    views = sys.argv[1:] or ['blue', 'clean']
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(views)) as pool:
        list(pool.map(build, views))

"""Compile clean and marked manuscript views without changing unrelated sources."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PAPER = ROOT / 'paper/latex'
BIN = Path('/private/tmp/samcgs_texlive_20261009/TinyTeX/bin/universal-darwin')
env = os.environ.copy()
env['PATH'] = str(BIN) + os.pathsep + env['PATH']
env['BIBINPUTS'] = str(PAPER) + os.pathsep
env['BSTINPUTS'] = str(PAPER) + os.pathsep

def build(view):
    stem = 'acl_latex_clean' if view == 'clean' else 'acl_latex'
    dest = HERE / ('build_' + view)
    dest.mkdir(exist_ok=True)
    tex = [str(BIN / 'xelatex'), '-interaction=nonstopmode', '-halt-on-error',
           '-file-line-error', '-output-directory=' + str(dest), stem + '.tex']
    sequence = [('pass1', tex), ('bibtex', [str(BIN / 'bibtex'), stem])]
    sequence += [(f'pass{i}', tex) for i in (2, 3)]
    steps = []
    for name, command in sequence:
        with (dest / (name + '.stdout')).open('w') as stream:
            proc = subprocess.run(command, cwd=dest if name == 'bibtex' else PAPER, env=env,
                                  stdout=stream, stderr=subprocess.STDOUT)
        steps.append({'step': name, 'returncode': proc.returncode})
        if proc.returncode:
            print((dest / (name + '.stdout')).read_text()[-6000:], flush=True)
            raise RuntimeError(f'{view}: {name} failed')
    (dest / 'build.json').write_text(json.dumps(steps, indent=2) + '\n')
    print(f'{view}: compiled {dest / (stem + ".pdf")}', flush=True)

with ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(build, ['clean', 'marked']))

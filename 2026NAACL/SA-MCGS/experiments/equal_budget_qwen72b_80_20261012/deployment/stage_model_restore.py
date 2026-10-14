#!/usr/bin/env python3
"""Stage audited restoration scripts, optionally dispatch exactly once."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
HOST = 'Group3_slogin'
REMOTE = '/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012/deployment'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15', HOST]


def ssh(code):
    return subprocess.run(SSH + ['/usr/bin/python3 -B -c ' + shlex.quote(code)],
                          text=True, capture_output=True, check=True, timeout=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    names = ['restore_model.py', 'start_model_restore_once.py', 'official_model_metadata.json',
             'restore_staging_manifest.json']
    manifest = json.loads((HERE / 'restore_staging_manifest.json').read_text())
    for name, value in manifest['files'].items():
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != value['sha256']:
            raise RuntimeError('Local staged artifact changed')
    # A launched restore can only be inspected, never overwritten by this tool.
    result = ssh('from pathlib import Path\n'
                 f'p=Path({REMOTE!r})\n'
                 "if (p/'model_restore_launch_receipt.json').exists(): raise RuntimeError('Restore dispatched; staging disabled')\n"
                 "p.mkdir(parents=True,exist_ok=True,mode=0o700)\n"
                 "assert p.resolve()==p\n")
    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                    *[str(HERE / name) for name in names], f'{HOST}:{REMOTE}/'], check=True, timeout=120)
    code = ('from pathlib import Path\nimport hashlib,json\n'
            f'p=Path({REMOTE!r})\n'
            "m=json.loads((p/'restore_staging_manifest.json').read_text())\n"
            "for n,v in m['files'].items(): assert hashlib.sha256((p/n).read_bytes()).hexdigest()==v['sha256']\n"
            "print(json.dumps({'staged':str(p),'verified_files':len(m['files']),'inference_calls':0}))\n")
    checked = ssh(code)
    (HERE / 'restore_staging_receipt.json').write_text(checked.stdout)
    print(checked.stdout, end='')
    if args.launch:
        launched = subprocess.run(SSH + ['/usr/bin/python3 -B ' + shlex.quote(REMOTE + '/start_model_restore_once.py')],
                                  text=True, capture_output=True, check=True, timeout=90)
        (HERE / 'model_restore_launch_receipt.json').write_text(launched.stdout)
        print(launched.stdout, end='')


if __name__ == '__main__':
    main()

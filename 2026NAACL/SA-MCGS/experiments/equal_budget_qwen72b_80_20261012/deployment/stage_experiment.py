#!/usr/bin/env python3
"""Stage a checksummed source snapshot; never launch compute or overwrite results."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
REMOTE = '/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15', 'Group3_slogin']


def main():
    files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py', '.json', '.sh', '.md')]
    files += [p for p in (ROOT/'sources').rglob('*') if p.is_file()]
    files += [p for p in (ROOT/'deployment/tokenizer_preflight').iterdir() if p.is_file()]
    files += [p for p in (ROOT/'deployment').iterdir() if p.is_file() and p.suffix in ('.py', '.md')]
    files += [ROOT/'deployment/official_model_metadata.json']
    # Runtime files are never included, even if this script is invoked after deployment.
    excluded = {'endpoints.json', 'protocol.json', 'execution_status.json'}
    files = sorted({p for p in files if p.name not in excluded})
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest = ROOT/'deployment/services_staging_manifest.json'
    manifest.write_text(json.dumps({'files': hashes}, indent=2)+'\n')
    files.append(manifest)
    archive = ROOT/'deployment/source_staging.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        for path in files:
            stream.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    remote_archive = REMOTE+'/deployment/source_staging_'+archive_hash[:16]+'.tar.gz'
    subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                    '-o', 'ConnectTimeout=15', str(archive), 'Group3_slogin:'+remote_archive], check=True)
    program = r'''
import hashlib, io, json, os, pathlib, tarfile
root = pathlib.Path(ROOT_VALUE)
archive = pathlib.Path(ARCHIVE_VALUE)
assert os.getuid() == 1083 and root.resolve() == root
assert hashlib.sha256(archive.read_bytes()).hexdigest() == HASH_VALUE
assert not (root/'protocol.json').exists(), 'Refusing source replacement after scientific launch'
with tarfile.open(archive) as stream:
    entries = stream.getmembers()
    assert len({m.name for m in entries}) == len(entries)
    for item in entries:
        name = pathlib.PurePosixPath(item.name)
        assert item.isfile() and not name.is_absolute() and '..' not in name.parts
    manifest = json.load(stream.extractfile('deployment/services_staging_manifest.json'))
    for item in entries:
        data = stream.extractfile(item).read()
        if item.name != 'deployment/services_staging_manifest.json':
            assert hashlib.sha256(data).hexdigest() == manifest['files'][item.name]
        target = root/item.name
        assert target.resolve() == target
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() == data:
            continue
        temporary = target.with_name('.'+target.name+'.stage.tmp')
        temporary.write_bytes(data)
        temporary.replace(target)
for name, expected in manifest['files'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == expected
print(json.dumps({'status':'staged_and_verified','files':len(manifest['files']),'root':str(root),'archive_sha256':HASH_VALUE}))
'''
    program = program.replace('ROOT_VALUE', repr(REMOTE)).replace('ARCHIVE_VALUE', repr(remote_archive)).replace('HASH_VALUE', repr(archive_hash))
    checked = subprocess.run(SSH+['python3 -'], input=program, text=True, capture_output=True, timeout=90, check=True)
    print(checked.stdout.strip())
    (ROOT/'deployment/source_staging_receipt.json').write_text(checked.stdout)


if __name__ == '__main__':
    main()

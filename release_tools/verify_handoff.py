"""Portable handoff file inventory. This is NOT the official task fingerprint."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'handoff/FILE_MANIFEST.json'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8<<20),b''):h.update(chunk)
    return h.hexdigest()


def files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and not {'.git','__pycache__'}.intersection(p.relative_to(ROOT).parts) and p.suffix not in ('.pyc','.pyo') and p!=MANIFEST and 'handoff/verification/' not in str(p.relative_to(ROOT)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--restore-empty-dirs',action='store_true')
    args=parser.parse_args()
    if args.write:
        payload={'purpose':'handoff-integrity-only-not-official-task-binding','files':{str(p.relative_to(ROOT)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in files()},'empty_directories':[str(p.relative_to(ROOT)) for p in sorted(ROOT.rglob('*')) if p.is_dir() and '.git' not in p.relative_to(ROOT).parts and not any(p.iterdir())]}
        MANIFEST.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    expected=json.loads(MANIFEST.read_text())
    if args.restore_empty_dirs:
        for name in expected['empty_directories']:
            p=(ROOT/name).resolve()
            if not p.is_relative_to(ROOT): raise SystemExit('Unsafe manifest path')
            p.mkdir(parents=True,exist_ok=True)
    failures=[]
    for name,identity in expected['files'].items():
        p=ROOT/name
        if p.is_symlink() or not p.is_file() or sha(p)!=identity['sha256']:failures.append(name)
    extra={str(p.relative_to(ROOT)) for p in files()}-set(expected['files'])
    if failures or extra:raise SystemExit(json.dumps({'status':'FAILED','changed_or_missing':failures,'extra':sorted(extra)}))
    missing=[name for name in expected['empty_directories'] if not (ROOT/name).is_dir()]
    if missing:raise SystemExit('Missing empty directories; rerun with --restore-empty-dirs')
    print(json.dumps({'status':'PASS_HANDOFF_INTEGRITY','files':len(expected['files']),'empty_directories':len(expected['empty_directories']),'official_task_fingerprint':False}))


if __name__=='__main__':main()

"""Build a complete, unreviewed submission ZIP; do not grant QA PASS."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(); root=args.package_root.resolve(); out=args.output.resolve()
    for name in ('workspace','expert_evidence','optimization_evidence'):
        if not (root/name).is_dir():raise SystemExit('Missing required package directory: '+name)
    if out.is_relative_to(root):raise SystemExit('ZIP output must be outside package inputs')
    if out.exists():raise SystemExit('Refusing to overwrite an existing ZIP')
    paths=sorted(root.rglob('*'))
    for p in paths:
        if p.is_symlink() or not (p.is_file() or p.is_dir()):raise SystemExit('Unsafe package file type')
        if p.name in ('.env','id_rsa','id_ed25519','.git-credentials') or '.git' in p.relative_to(root).parts:raise SystemExit('Forbidden credential or repository metadata')
        if p.suffix in ('.pyc','.pyo') or '__pycache__' in p.parts:raise SystemExit('Remove generated Python caches before packaging/fingerprinting')
    out.parent.mkdir(parents=True,exist_ok=True)
    temp=out.with_name(out.name+'.tmp')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for p in paths:
            name=str(p.relative_to(root))+('/' if p.is_dir() else '')
            info=zipfile.ZipInfo(name,date_time=(2026,10,21,0,0,0))
            info.create_system=3; info.external_attr=p.stat().st_mode<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,b'' if p.is_dir() else p.read_bytes())
    with zipfile.ZipFile(temp) as archive:
        if archive.testzip() is not None:raise SystemExit('ZIP integrity error')
    temp.rename(out); h=hashlib.sha256()
    with out.open('rb') as f:
        for chunk in iter(lambda:f.read(8<<20),b''):h.update(chunk)
    checksum=out.with_suffix(out.suffix+'.sha256'); checksum.write_text(h.hexdigest()+'  '+out.name+'\n')
    print(json.dumps({'status':'PACKAGED_UNREVIEWED','sha256':h.hexdigest(),'bytes':out.stat().st_size,'QA_PASS':False}))


if __name__=='__main__':main()

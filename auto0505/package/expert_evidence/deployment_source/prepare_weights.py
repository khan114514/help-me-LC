"""Copy only the frozen model assets into the trusted image build context."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''): h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--destination', type=Path, default=Path(__file__).parent/'runtime-image'/'weights')
    args = parser.parse_args()
    source = args.source.resolve()
    manifest = json.loads((Path(__file__).parent/'runtime-image'/'weight_manifest.json').read_text())['files']
    verified = []
    for name, expected in manifest.items():
        path = source/name
        if not path.is_file() or not path.resolve().is_relative_to(source) or sha(path) != expected:
            raise SystemExit('Missing or mismatched frozen model asset: '+name)
        verified.append((name,path,path.stat().st_size,expected))
    args.destination.mkdir(parents=True, exist_ok=True)
    for name, path, size, expected in verified:
        target = args.destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and sha(target) != expected:
            raise SystemExit('Refusing to overwrite a different asset: '+name)
        if not target.exists(): shutil.copy2(path,target)
        if sha(target) != expected: raise SystemExit('Copy verification failed: '+name)
    receipt = {'status':'VERIFIED_COPY','files':len(verified),'bytes':sum(row[2] for row in verified),
               'sha256':{row[0]:row[3] for row in verified}}
    (args.destination.parent/'asset-copy-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':receipt['status'],'files':receipt['files'],'bytes':receipt['bytes']}))


if __name__ == '__main__': main()

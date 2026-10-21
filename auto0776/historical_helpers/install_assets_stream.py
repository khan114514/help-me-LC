"""Build-only streamed import; final image has no download dependency."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import urllib.request


class HashedReader(io.RawIOBase):
    def __init__(self, response):
        self.response = response
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def read(self, size=-1):
        value = self.response.read(size)
        self.digest.update(value)
        return value


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    url, expected_archive, expected_manifest = sys.argv[1:]
    target = Path('/opt/onedc/weights')
    target.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(target).free < 9881600505 + (2 << 30):
        raise RuntimeError('Insufficient build storage for model import with reserve')
    with urllib.request.urlopen(url, timeout=30) as response:
        stream = HashedReader(response)
        members = set()
        with tarfile.open(fileobj=stream, mode='r|gz') as archive:
            for member in archive:
                relative = PurePosixPath(member.name)
                if relative.is_absolute() or '..' in relative.parts or '\\' in member.name or len(members) > 100:
                    raise RuntimeError('Invalid whitelisted model archive path')
                path = target / relative
                if member.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                elif member.isfile() and member.size <= 4_000_000_000:
                    key = relative.as_posix()
                    if key in members:
                        raise RuntimeError('Repeated model archive file')
                    members.add(key)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, path.open('xb') as out:
                        shutil.copyfileobj(source, out, 1 << 20)
                    path.chmod(0o644)
                else:
                    raise RuntimeError('Model archive contains a link or unsupported type')
        while stream.read(1 << 20):
            pass
        if stream.digest.hexdigest() != expected_archive:
            raise RuntimeError('Model transport archive hash mismatch')
    manifest = target / 'asset_manifest.json'
    if digest(manifest) != expected_manifest:
        raise RuntimeError('Model manifest hash mismatch')
    assets = json.loads(manifest.read_text())['files']
    if members != set(assets) | {'asset_manifest.json'}:
        raise RuntimeError('Model archive differs from the exact file whitelist')
    for relative, value in assets.items():
        path = target / relative
        if path.stat().st_size != value['size'] or digest(path) != value['sha256']:
            raise RuntimeError('Baked model asset fingerprint mismatch')
    print(json.dumps({'offline_model_files': len(assets), 'bytes': sum(v['size'] for v in assets.values()),
                      'archive_sha256': expected_archive, 'manifest_sha256': expected_manifest}))


if __name__ == '__main__':
    main()

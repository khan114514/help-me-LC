"""Whitelist, hash and normalize offline model assets; no credential files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

GROUPS = [
    ('checkpoints/lambda4.6', 'lambda4.6'),
    ('.cache/huggingface/hub/models--madebyollin--taesd', 'hf/hub/models--madebyollin--taesd'),
    ('.cache/huggingface/hub/models--runwayml--stable-diffusion-v1-5', 'hf/hub/models--runwayml--stable-diffusion-v1-5'),
    ('.cache/huggingface/hub/models--stabilityai--stable-diffusion-2-1', 'hf/hub/models--stabilityai--stable-diffusion-2-1'),
    ('.cache/torch/hub/checkpoints/alexnet-owt-7be5be79.pth', 'torch/hub/checkpoints/alexnet-owt-7be5be79.pth'),
    ('.cache/torch/hub/checkpoints/vgg16-397923af.pth', 'torch/hub/checkpoints/vgg16-397923af.pth'),
]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def manifest(raw):
    files, links = {}, {}
    for source, destination in GROUPS:
        group = raw / source
        if not group.exists():
            raise RuntimeError('Required model asset group is missing: ' + source)
        members = sorted(group.rglob('*')) if group.is_dir() else [group]
        for path in members:
            key = destination if path == group else destination + '/' + path.relative_to(group).as_posix()
            if path.is_symlink():
                if os.path.isabs(os.readlink(path)) or not path.resolve().is_relative_to(group.resolve()):
                    raise RuntimeError('Model asset symlink escapes its whitelisted group')
                links[key] = os.readlink(path)
            if path.is_file():
                files[key] = {'size': path.stat().st_size, 'sha256': sha(path)}
            elif not path.is_dir():
                raise RuntimeError('Unsupported model asset type')
    return {'schema_version': 'onedc-offline-assets.v1', 'files': files, 'symlinks': links,
            'source_fidelity': 'Transport hashes verified separately. Cache revision labels alone do not authenticate upstream provenance.'}


def copy_or_link(source, target):
    try:
        os.link(source, target)
        return target
    except OSError:
        return shutil.copy2(source, target)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--raw', required=True, type=Path)
    p.add_argument('--manifest', required=True, type=Path)
    p.add_argument('--normalize', type=Path)
    p.add_argument('--expected', type=Path)
    args = p.parse_args()
    observed = manifest(args.raw)
    if args.expected and observed != json.loads(args.expected.read_text()):
        raise RuntimeError('Transferred assets differ from the source manifest')
    args.manifest.write_text(json.dumps(observed, indent=2, sort_keys=True) + '\n')
    if args.normalize:
        args.normalize.mkdir(parents=True, exist_ok=False)
        for source, destination in GROUPS:
            path, target = args.raw / source, args.normalize / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.is_dir():
                shutil.copytree(path, target, symlinks=True, copy_function=copy_or_link)
            else:
                copy_or_link(path, target)
        for relative, value in observed['files'].items():
            path = args.normalize / relative
            if path.stat().st_size != value['size'] or sha(path) != value['sha256']:
                raise RuntimeError('Normalized asset fingerprint mismatch')
        (args.normalize / 'asset_manifest.json').write_text(args.manifest.read_text())
    print(json.dumps({'files': len(observed['files']), 'links': len(observed['symlinks']),
                      'bytes': sum(v['size'] for v in observed['files'].values()),
                      'manifest_sha256': sha(args.manifest)}))


if __name__ == '__main__':
    main()

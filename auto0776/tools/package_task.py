#!/usr/bin/env python3
"""Package a repaired three-directory task; this is not official QA or fingerprint."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import sys
import zipfile

TOPS = ['workspace', 'expert_evidence', 'optimization_evidence']
FIELDS = {'round', 'policy_name', 'method_summary', 'status', 'score', 'failure_reason', 'retained_best', 'time'}


def validate(root):
    required = ['workspace/harbor_task/instruction.md', 'workspace/harbor_task/task.toml', 'workspace/harbor_task/tests/test.sh', 'expert_evidence/expert_annotation.json', 'expert_evidence/run_summary.json', 'expert_evidence/trajectory_codex.json', 'expert_evidence/trajectory_seed.json', 'optimization_evidence/comparison_summary.json']
    for rel in required:
        if not (root / rel).is_file():
            raise ValueError('missing:' + rel)
    best = root / 'expert_evidence/best_method'
    if not best.is_dir() or not any(p.is_file() for p in best.rglob('*')):
        raise ValueError('missing final best_method')
    for name in ['trajectory_codex.json', 'trajectory_seed.json']:
        data = json.loads((root / 'expert_evidence' / name).read_text())
        rounds = data['rounds']
        if not rounds:
            raise ValueError('empty trajectory:' + name)
        previous = 0
        for row in rounds:
            if set(row) != FIELDS or type(row['round']) is not int or row['round'] <= previous:
                raise ValueError('invalid fields/order:' + name)
            previous = row['round']
            if type(row['retained_best']) is not bool or not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', row['time']):
                raise ValueError('invalid best/time:' + name)
            if row['score'] is not None and (type(row['score']) not in (int, float) or not math.isfinite(row['score'])):
                raise ValueError('nonfinite score:' + name)
            if row['status'] == 'ok' and (row['score'] is None or row['failure_reason'] is not None):
                raise ValueError('invalid ok:' + name)
    for top in TOPS:
        if not (root / top).is_dir():
            raise ValueError('missing directory:' + top)
        for p in (root / top).rglob('*'):
            if p.is_symlink():
                raise ValueError('symlink requires approved explicit delivery handling')
            if p.is_file() and p.suffix == '.json':
                json.loads(p.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out.resolve()
    if output.exists():
        raise ValueError('refuse to overwrite existing candidate')
    if output.is_relative_to(root):
        raise ValueError('put output outside source tree')
    validate(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for top in TOPS:
            for p in [root / top, *sorted((root / top).rglob('*'))]:
                name = p.relative_to(root).as_posix() + ('/' if p.is_dir() else '')
                info = zipfile.ZipInfo(name, (2026, 10, 21, 0, 0, 0))
                info.create_system = 3
                info.external_attr = ((stat.S_IFDIR if p.is_dir() else stat.S_IFREG) | stat.S_IMODE(p.stat().st_mode)) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, b'' if p.is_dir() else p.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + '.sha256').write_text(digest + '  ' + output.name + '\n')
    print(json.dumps({'status': 'PACKAGED_NOT_QA_APPROVED', 'file': output.name, 'sha256': digest, 'task_release_ready': False, 'official_fingerprint_generated': False, 'next': 'Run actual official checks and independent dual AI QA on these exact bytes.'}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'NOT_PACKAGED', 'reason': str(exc)}))
        sys.exit(1)

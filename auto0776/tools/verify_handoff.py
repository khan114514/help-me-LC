#!/usr/bin/env python3
"""Check author handoff integrity, never execute candidate code or claim task QA."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def check():
    errors, checks, runs = [], [], []

    def require(condition, label):
        (checks if condition else errors).append(label)

    def files_from(manifest, prefix):
        for row in manifest:
            path = prefix / row['path']
            require(path.is_file() and not path.is_symlink(), 'file:' + row['path'])
            if not path.is_file() or path.is_symlink():
                continue
            require(sha(path) == row['sha256'], 'sha:' + row['path'])
            if 'bytes' in row:
                require(path.stat().st_size == row['bytes'], 'size:' + row['path'])

    src = ROOT / 'source/onedc_v9'
    baseline = load(ROOT / 'manifests/source_v9.json')
    files_from(baseline['files'], src)
    actual = {p.relative_to(src).as_posix() for p in src.rglob('*') if p.is_file()}
    require(actual == {r['path'] for r in baseline['files']}, 'historical_source_member_set')

    skills = load(ROOT / 'manifests/skills_provenance.json')['files']
    for row in skills:
        p = ROOT / row['path']
        require(p.is_file() and sha(p) == row['published_sha256'], 'skill:' + row['path'])

    release = ROOT / 'skills/autoresearch-manager/assets/qa-release.json'
    for rel, expected in load(release)['files'].items():
        p = release.parent / 'qa-skills' / rel
        require(p.is_file() and sha(p) == expected, 'fixed_legacy_qa:' + rel)

    prov = load(src / 'optimization_evidence/native_calibration_v8/original_records/PROVENANCE.json')
    index = {x['member']: x for x in prov['records']}
    for role, label in [('baseline_runs', 'B'), ('reference_runs', 'R')]:
        for repeat in (1, 2, 3):
            root = src / 'optimization_evidence' / role / f'seed_eval_replicate_{repeat}'
            raw = src / 'optimization_evidence/native_calibration_v8/original_records/raw' / f'{label}_{repeat}'
            execution = load(raw / 'execution.json')
            metrics = load(raw / 'out/metrics.json')
            result = load(root / 'result.json')
            log = raw / 'run.log'
            log_bytes = log.read_bytes()
            p = index[log.relative_to(src).as_posix()]
            run_id = f'{label}_{repeat}'
            require(sha(log) == p['original_sha256'] == p['delivered_sha256'], run_id + ':original_log_sha')
            require(log_bytes == (root / 'run.log').read_bytes(), run_id + ':formal_raw_log_identical')
            require(len(re.findall(rb'\[run_eval\] kodim\d+:', log_bytes)) == 24, run_id + ':24_images_in_stdout')
            require(execution['exit_code'] == 0 and execution['seed'] == 0, run_id + ':exit_and_real_seed')
            require(execution['method_sha256'] == metrics['method_sha256'] == result['method']['source_sha256'], run_id + ':method_binding')
            require(metrics['valid'] is True, run_id + ':valid')
            require(metrics['dists'] == result['metrics']['dists'], run_id + ':result_binding')
            require([r['split'] for r in metrics['per_image']] == ['public'] * 16 + ['hidden'] * 8, run_id + ':split_order')
            require(len({r['image'] for r in metrics['per_image']}) == 24, run_id + ':24_unique_images')
            for split in ['public', 'hidden']:
                require(metrics[split]['bpp_mean'] <= metrics['bpp_cap'][split], run_id + ':' + split + '_rate_gate')
            runs.append({'run': run_id, 'seed': 0, 'images': 24, 'log_lines': len(log_bytes.splitlines()), 'log_sha256': sha(log), 'exit_code': execution['exit_code'], 'dists': metrics['dists']})

    records = list((ROOT / 'evidence/original_clock_records').glob('*/private-rounds/*/*.json'))
    require(len(records) == 118, '59_original_audit_and_start_pairs')
    for p in records:
        load(p)
    best = src / 'expert_evidence/final_native_replays/gpt/method.py'
    require(sha(best) == 'db57c37907109775875e3f1e1146acedc026e003b0d8bcf6bb480c39f4fe9acb', 'historical_gpt_candidate_sha')

    final_manifest = ROOT / 'manifests/files.json'
    if final_manifest.exists():
        files_from(load(final_manifest)['files'], ROOT)
    else:
        errors.append('missing_final_handoff_file_manifest')
    return {'status': 'PASS_HANDOFF_INTEGRITY_ONLY' if not errors else 'FAIL_HANDOFF_INTEGRITY', 'task_release_ready': False, 'official_0310_qa_performed': False, 'scope': 'Read-only file hashes, historical six raw score logs and actual skill snapshots. No candidate import, GPU, model, official fingerprint, NOP or QA execution.', 'checks': len(checks), 'errors': errors, 'source_files': len(baseline['files']), 'skill_files': len(skills), 'clock_files': len(records), 'runs': runs}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    try:
        report = check()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = {'status': 'FAIL_HANDOFF_INTEGRITY', 'task_release_ready': False, 'error_type': type(exc).__name__}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report['status'] == 'PASS_HANDOFF_INTEGRITY_ONLY' else 1)

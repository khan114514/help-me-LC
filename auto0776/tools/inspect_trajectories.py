#!/usr/bin/env python3
"""Read old trajectories and receipts; report conflicts without editing evidence."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'round', 'policy_name', 'method_summary', 'status', 'score', 'failure_reason', 'retained_best', 'time'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path)
    args = p.parse_args()
    result = {'scope': 'author review candidates, not automatic score correction or research-time decision', 'tracks': []}
    for track, filename in [('gpt', 'trajectory_codex.json'), ('seed', 'trajectory_seed.json')]:
        trajectory = json.loads((ROOT / 'source/onedc_v9/expert_evidence' / filename).read_text())['rounds']
        old_path = ROOT / 'source/onedc_v9/expert_evidence/final_research_history' / track / 'original-controller-trajectory.jsonl'
        old = {r['round']: r for line in old_path.read_text().splitlines() if line.strip() for r in [json.loads(line)]}
        rows = []
        for row in trajectory:
            audit_path = ROOT / 'evidence/original_clock_records' / track / 'private-rounds' / f"{row['round']:05d}" / 'audit.json'
            audit = json.loads(audit_path.read_text()) if audit_path.exists() else {}
            candidate = row.get('candidate_method_sha256', audit.get('candidate_sha256'))
            receipts = audit.get('new_public_receipts', [])
            rows.append({'original_round': row['round'], 'current_status': row['status'], 'current_score': row['score'], 'original_status': old.get(row['round'], {}).get('status'), 'original_score': old.get(row['round'], {}).get('score'), 'candidate_sha256': candidate, 'cli_exit': audit.get('cli_exit'), 'extra_fields': sorted(set(row) - FIELDS), 'new_receipts_count': len(receipts), 'same_candidate_receipts': [{k: r.get(k) for k in ['run_id', 'method_sha256', 'split', 'status', 'valid', 'dists', 'score', 'exit_code', 'bpp_mean', 'bpp_cap']} for r in receipts if r.get('method_sha256') == candidate], 'audit_path': audit_path.relative_to(ROOT).as_posix() if audit_path.exists() else None, 'decision': 'REQUIRES_REVIEW_OF_PROTOCOL_AND_ORDER'})
        ids = {r['round'] for r in trajectory}
        result['tracks'].append({'track': track, 'rows': len(rows), 'missing_original_attempt_numbers': sorted(set(range(1, max(ids) + 1)) - ids), 'rounds': rows})
    output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
        print(json.dumps({'report': str(args.out), 'tracks': [{k: v for k, v in t.items() if k != 'rounds'} for t in result['tracks']]}, ensure_ascii=False))
    else:
        print(output, end='')


if __name__ == '__main__':
    main()

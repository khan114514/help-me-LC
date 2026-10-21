#!/usr/bin/env python3
"""Arithmetic only for manually evidenced intervals, not automatic eligibility."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ALLOWED = {'method_design', 'analysis', 'evaluation', 'normal_training', 'method_failure'}
EXCLUDED = {'setup', 'install', 'queue', 'infrastructure_failure', 'api_block', 'paused', 'post_pause_qa', 'final_recheck'}


def parse_time(value):
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('timezone required')
    return d.timestamp()


def merge(values):
    result = []
    for start, end in sorted(values):
        if not result or start > result[-1][1]:
            result.append([start, end])
        else:
            result[-1][1] = max(result[-1][1], end)
    return result


def intervals(rows, categories):
    out = []
    for row in rows:
        if row.get('category') not in categories or not row.get('evidence') or not row.get('rationale'):
            raise ValueError('category, evidence and rationale required')
        start, end = parse_time(row['start']), parse_time(row['end'])
        if end <= start:
            raise ValueError('nonpositive interval')
        out.append((start, end))
    return merge(out)


def duration(values):
    return sum(end - start for start, end in values)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('ledger', type=Path)
    p.add_argument('--out', type=Path)
    args = p.parse_args()
    data = json.loads(args.ledger.read_text())
    target = data['required_seconds_per_track']
    if not isinstance(target, (int, float)) or target <= 0:
        raise ValueError('positive target required')
    results = []
    for row in data['tracks']:
        eligible = intervals(row['research_intervals'], ALLOWED)
        excluded = intervals(row['excluded_intervals'], EXCLUDED)
        overlap = sum(max(0, min(b, d) - max(a, c)) for a, b in eligible for c, d in excluded)
        actual = max(0, duration(eligible) - overlap)
        reviewed = row.get('review_complete') is True
        results.append({'track': row['track'], 'review_complete': reviewed, 'research_union_seconds': duration(eligible), 'exclusion_overlap_seconds': overlap, 'effective_seconds': actual if reviewed else None, 'arithmetic_unreviewed_seconds': actual, 'required_seconds': target, 'deficit_seconds': max(0, target - actual) if reviewed else None, 'target_met': reviewed and actual >= target})
    if {r['track'] for r in results} != {'gpt', 'seed'} or len(results) != 2:
        raise ValueError('exactly two known tracks required')
    ready = all(r['review_complete'] and r['target_met'] for r in results)
    result = {'status': 'ARITHMETIC_TARGET_MET_REQUIRES_EVIDENCE_REVIEW' if ready else 'INCOMPLETE', 'task_release_ready': False, 'tracks': results, 'scope': 'Union/subtraction of author-reviewed evidence intervals only; does not authenticate evidence or accept 7h exceptions.'}
    output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
    print(output, end='')
    return 0 if ready else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'INVALID_LEDGER', 'error_type': type(exc).__name__}))
        sys.exit(1)

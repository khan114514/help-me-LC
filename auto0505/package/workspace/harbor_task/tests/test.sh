#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
exec timeout --signal=TERM --kill-after=10s 3590s python3 -I -B /tests/evaluate_candidate.py --method /workspace/solution/method.py --out /logs/verifier --formal

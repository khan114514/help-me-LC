#!/bin/bash
set -euo pipefail
exec timeout --signal=TERM --kill-after=10s 3590s python3 -I -B /opt/rfsteps/public/evaluate_candidate.py --method "${1:-/workspace/solution/method.py}" --out "${2:-/workspace/agent-output/dev}"

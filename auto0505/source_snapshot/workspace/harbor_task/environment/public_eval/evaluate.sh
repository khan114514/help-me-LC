#!/bin/bash
set -euo pipefail
exec python3 /workspace/environment/public_eval/evaluate_candidate.py --method "${1:-/workspace/solution/method.py}" --out "${2:-/workspace/agent-output/dev}" --worker /workspace/environment/public_eval/candidate_worker.py --worker-python /usr/bin/python3

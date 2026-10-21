#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
exec python3 /tests/evaluate_candidate.py --method /workspace/solution/method.py --out /logs/verifier --formal --worker /usr/local/lib/rfsteps/candidate_worker.py --worker-python /usr/bin/python3

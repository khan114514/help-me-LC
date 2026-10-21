#!/bin/bash
set -euo pipefail
if [ -f /workspace/environment/starter/method.py ]; then
  mkdir -p /workspace/solution /workspace/agent-output
  cp /workspace/environment/starter/method.py /workspace/solution/method.py
  cp /workspace/environment/public_eval/solve.sh /workspace/solution/solve.sh
fi
exec "$@"

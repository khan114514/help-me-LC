#!/bin/bash
set -euo pipefail
mkdir -p /workspace/solution /workspace/agent-output
if [ ! -e /workspace/solution/method.py ]; then
  cp /workspace/starter/method.py /workspace/solution/method.py
  cp /workspace/starter/solve.sh /workspace/solution/solve.sh
fi
exec "$@"

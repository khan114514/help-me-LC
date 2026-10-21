#!/bin/bash
set -euo pipefail
exec bash /workspace/environment/public_eval/evaluate.sh /workspace/solution/method.py /workspace/agent-output/dev

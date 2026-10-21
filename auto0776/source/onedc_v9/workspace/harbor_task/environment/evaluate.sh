#!/bin/bash
set -euo pipefail
exec python3 /opt/onedc/grader/public_eval_client.py "$@"

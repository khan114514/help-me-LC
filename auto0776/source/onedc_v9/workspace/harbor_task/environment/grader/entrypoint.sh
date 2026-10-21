#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
python3 /opt/onedc/grader/public_eval_server.py >/tmp/onedc-public-service.log 2>&1 &
service_pid=$!
for attempt in $(seq 1 40); do
    kill -0 "$service_pid"
    if test -f /workspace/public-results/service-ready.json; then
        exec "$@"
    fi
    sleep .1
done
exit 3

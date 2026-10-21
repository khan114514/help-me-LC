#!/bin/bash
# Agent can read public task assets; the tensor worker cannot read images,
# model files, evaluator code or public score history.
set -euo pipefail
for directory in /workspace/repo /workspace/public_assets /opt/onedc/weights /opt/onedc/metric_weights /opt/onedc/grader /workspace/public-results; do
    chown root:onedc-agent "$directory"
    chmod 750 "$directory"
done
chmod 750 /opt/onedc/grader/entrypoint.sh /opt/onedc/grader/public_eval.py
chmod 700 /home/onedc-agent
mkdir -p /workspace/.aws
chown root:root /workspace/.aws
chmod 755 /workspace/.aws /workspace
chmod 1770 /workspace/eval-requests

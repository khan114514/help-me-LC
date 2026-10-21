#!/bin/bash
set -euo pipefail
chown -R 0:0 /tests /logs/verifier
chmod 700 /tests /logs/verifier
mkdir /tests/eval
ln -s /workspace/public_assets/eval_public /tests/eval/public
ln -s /tests/hidden_assets /tests/eval/hidden
export ONEDC_EVAL=/tests/eval ONEDC_HIDDEN_MANIFEST=/tests/hidden_assets/manifest.json
export ONEDC_ANCHORS=/tests/anchors.json ONEDC_LOCK=/opt/onedc/locks/gpu.lock
export HF_HOME=/opt/onedc/weights/hf TORCH_HOME=/opt/onedc/weights/torch
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1
python3 /tests/calibration_bundle_verifier.py

#!/bin/bash
# Formal verification requires the complete externally injected hidden split.
set -euo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS=/logs/verifier
mkdir -p "$LOGS"
chown -R 0:0 "$LOGS" "$TESTS_DIR"
chmod 700 "$LOGS" "$TESTS_DIR"
rm -f "$LOGS/reward.json" "$LOGS/reward.txt"
rm -rf "$LOGS/out"
CANDIDATE="${1:-/logs/artifacts/solution/method.py}"
PRIVATE="$(mktemp -d /tmp/onedc-verifier.XXXXXX)"
trap 'rm -rf "$PRIVATE"' EXIT
mkdir "$PRIVATE/eval"
ln -s /workspace/public_assets/eval_public "$PRIVATE/eval/public"
ln -s "$TESTS_DIR/hidden_assets" "$PRIVATE/eval/hidden"
export ONEDC_EVAL="$PRIVATE/eval"
export ONEDC_HIDDEN_MANIFEST="$TESTS_DIR/hidden_assets/manifest.json"
export ONEDC_REPO_SRC=/workspace/repo/onedc/src
export ONEDC_CHECKPOINT=/opt/onedc/weights/lambda4.6
export ONEDC_ANCHORS="$TESTS_DIR/anchors.json"
export ONEDC_FROZEN_HASHES=/opt/onedc/grader/frozen_hashes.txt
export ONEDC_LOCK=/opt/onedc/locks/gpu.lock
export HF_HOME=/opt/onedc/weights/hf
export TORCH_HOME=/opt/onedc/weights/torch
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1
set +e
python3 /opt/onedc/grader/solution_guard.py "$(dirname "$CANDIDATE")" /opt/onedc/grader/solution_contract.json
RC=$?
if [ "$RC" -eq 0 ]; then
    timeout 7300 python3 /opt/onedc/grader/lease_exec.py --timeout 3600 -- python3 /opt/onedc/grader/run_eval.py --method "$CANDIDATE" --out "$LOGS/out" --split full
    RC=$?
elif [ "$RC" -eq 65 ]; then
    mkdir -p "$LOGS/out"
    python3 - "$LOGS/out/metrics.json" <<'EOF'
import json, sys
with open(sys.argv[1], "w") as f:
    json.dump({"status": "hard_gate", "failure_type": "hard_gate", "valid": False,
               "score": -1.0, "violation": "Submitted solution violates its frozen file contract"}, f)
EOF
    RC=0
fi
set -e
python3 - "$LOGS/out/metrics.json" "$RC" "$LOGS/reward.json" <<'EOF'
import json, math, os, sys
metrics_path, rc, reward_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
if os.path.isfile(metrics_path):
    with open(metrics_path) as f:
        metrics = json.load(f)
else:
    metrics = {"status": "timeout" if rc == 124 else "infrastructure_error", "score": None, "valid": False}
if rc != 0 or metrics.get("score") is None:
    print(json.dumps({"failure_type": metrics.get("status"), "exit_code": rc}))
    raise SystemExit(rc or 3)
score = float(metrics["score"])
if not math.isfinite(score):
    raise SystemExit("Nonfinite reward")
temporary = reward_path + ".tmp"
with open(temporary, "w") as f:
    json.dump({"reward": score}, f)
    f.flush()
    os.fsync(f.fileno())
os.replace(temporary, reward_path)
print(json.dumps({"reward": score, "valid": metrics.get("valid"), "status": metrics.get("status")}))
EOF
exit "$RC"

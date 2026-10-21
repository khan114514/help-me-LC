#!/usr/bin/env python3
"""Fixed root service helper: callers cannot select a scorer or split."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from solution_guard import ScopeViolation, validate_solution


def main():
    if os.geteuid() != 0 or len(sys.argv) != 1:
        raise SystemExit("Use /workspace/evaluate.sh without arguments")
    method = Path("/workspace/solution/method.py")
    root = Path("/opt/onedc/grader")
    receipts = Path("/workspace/public-results")
    if receipts.is_symlink() or receipts.stat().st_uid != 0:
        raise SystemExit("Trusted public result directory was altered")
    run_id = uuid.uuid4().hex
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1",
           "TRANSFORMERS_OFFLINE": "1", "HF_HOME": "/opt/onedc/weights/hf",
           "TORCH_HOME": "/opt/onedc/weights/torch", "ONEDC_REPO_SRC": "/workspace/repo/onedc/src",
           "ONEDC_CHECKPOINT": "/opt/onedc/weights/lambda4.6",
           "ONEDC_ANCHORS": str(root / "public_anchors.json"),
           "ONEDC_FROZEN_HASHES": str(root / "frozen_hashes.txt"),
           "ONEDC_LOCK": "/opt/onedc/locks/gpu.lock"}
    for key in ("LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES"):
        if key in os.environ:
            env[key] = os.environ[key]
    with tempfile.TemporaryDirectory(prefix="onedc-public-") as private:
        private = Path(private)
        eval_root = private / "eval"
        eval_root.mkdir()
        (eval_root / "public").symlink_to("/workspace/public_assets/eval_public")
        out = private / "out"
        snapshot = private / "method.py"
        env["ONEDC_EVAL"] = str(eval_root)
        command = [sys.executable, str(root / "lease_exec.py"), "--timeout", "3600", "--",
                   sys.executable, str(root / "run_eval.py"), "--method", str(snapshot), "--out", str(out), "--split", "public"]
        log_path = receipts / (run_id + ".log")
        with log_path.open("xb") as log:
            try:
                validate_solution(method.parent, root / "solution_contract.json")
                shutil.copyfile(method, snapshot)
                snapshot.chmod(0o400)
                result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=7300)
                rc = result.returncode
            except ScopeViolation as exc:
                out.mkdir()
                (out / "metrics.json").write_text(json.dumps({"status": "hard_gate", "failure_type": "hard_gate",
                    "valid": False, "score": -1.0, "violation": str(exc)}))
                rc = 0
            except subprocess.TimeoutExpired:
                rc = 124
        if (out / "metrics.json").is_file():
            metrics = json.loads((out / "metrics.json").read_text())
        else:
            metrics = {"status": "timeout" if rc == 124 else "infrastructure_error",
                       "failure_type": "timeout" if rc == 124 else "infrastructure_error",
                       "valid": False, "score": None}
        if rc != 0:
            if metrics.get('status') in ('success', 'valid') or metrics.get('valid'):
                metrics['status'] = metrics['failure_type'] = 'infrastructure_error'
            metrics['valid'] = False
            metrics['score'] = None
        metrics['exit_code'] = rc
        metrics["run_id"] = run_id
        path = receipts / (run_id + ".json")
        with path.open("x") as f:
            json.dump(metrics, f, indent=2)
        path.chmod(0o444)
        log_path.chmod(0o444)
        print(json.dumps({"metrics_path": str(path), "log_path": str(log_path), "exit_code": rc,
                          "status": metrics["status"], "valid": metrics["valid"], "dists": metrics.get("dists"),
                          "bpp_mean": metrics.get("bpp_mean"), "score": metrics.get("score")}))
        return rc


if __name__ == "__main__":
    raise SystemExit(main())

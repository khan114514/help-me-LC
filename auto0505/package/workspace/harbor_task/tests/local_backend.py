"""Trusted numeric execution on this sandbox's allocated GPU."""
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_files(root, expected):
    root = Path(root).resolve()
    for name, wanted in expected.items():
        path = root / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise RuntimeError("required_frozen_asset_missing_or_unsafe:" + name)
        if digest(path) != wanted:
            raise RuntimeError("frozen_asset_hash_mismatch:" + name)


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def evaluate(nodes, formal, out, method_digest, runtime):
    started = time.monotonic()
    runtime, out = Path(runtime).resolve(), Path(out).resolve()
    if formal and (runtime != Path("/tests") or os.geteuid() != 0):
        raise RuntimeError("formal_requires_independent_verifier_root")
    manifest = json.loads((runtime / "asset_manifest.json").read_text())
    if manifest["role"] != ("formal" if formal else "public"):
        raise RuntimeError("scoring_role_mismatch")
    verify_files(runtime, manifest["runtime_files"])
    verify_files("/opt/rfsteps/worker", manifest["worker_files"])
    verify_files(runtime / "assets", manifest["images"])
    actual_images = {str(p.relative_to(runtime / "assets")) for p in (runtime / "assets").rglob("*.png")}
    if actual_images != set(manifest["images"]):
        raise RuntimeError("unexpected_evaluation_images")
    verify_files("/opt/rfsteps/repo", manifest["repo_files"])
    verify_files("/opt/rfsteps/weights", manifest["weight_files"])
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/tmp",
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "PYTHONNOUSERSITE": "1",
        "OMP_NUM_THREADS": "8", "OPENBLAS_NUM_THREADS": "8",
        "RFSTEPS_REPO_SRC": "/opt/rfsteps/repo/RF-Solver-Edit/FLUX_Image_Edit/src",
        "RFSTEPS_WEIGHTS": "/opt/rfsteps/weights", "RFSTEPS_EVAL": str(runtime / "assets"),
        "RFSTEPS_ANCHORS": str(runtime / "anchors.json"),
        "RFSTEPS_LOCK": "/tmp/rfsteps-local-gpu.lock",
    }
    # Preserve only allocation selectors supplied by the container runtime.
    for key in ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES"):
        if key in os.environ:
            environment[key] = os.environ[key]
    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             env=environment, check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("allocated_gpu_inventory_failed") from exc
    rows = [row.rsplit(",", 1) for row in gpu.splitlines() if row.strip()]
    if len(rows) != 1 or not any(card in rows[0][0] for card in ("A100", "H20", "L20")) or int(rows[0][1]) < 38000:
        raise RuntimeError("allocated_gpu_type_or_memory_mismatch")
    # The scorer imports only this trusted numeric bridge, never candidate code.
    with tempfile.TemporaryDirectory(prefix="rfsteps_numeric_") as temp:
        temp = Path(temp)
        bridge = temp / "validated_schedule.py"
        bridge.write_text("def get_timesteps(num_steps, image_seq_len):\n    return " + json.dumps(nodes, allow_nan=False) + "\n")
        bridge.chmod(0o444)
        scoring_out = temp / "score"
        command = [str(Path(sys.executable).resolve()), "-I", "-B", str(runtime / "run_eval.py"),
                   "--method", str(bridge), "--out", str(scoring_out), "--split", "full" if formal else "public"]
        receipt = {"schema_version": 1, "execution": "allocated_gpu_in_same_single_container",
                   "role": manifest["role"], "gpu": gpu, "method_sha256": method_digest,
                   "nodes_sha256": hashlib.sha256(json.dumps(nodes, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
                   "scorer_sha256": digest(runtime / "run_eval.py"), "assets_verified": True,
                   "started_at_unix": time.time(), "command": command, "exit_code": None}
        atomic_json(out / "gpu_receipt.json", receipt)
        with (out / "scorer-stdout.txt").open("wb") as stdout, (out / "scorer-stderr.txt").open("wb") as stderr:
            proc = subprocess.Popen(command, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                                    env=environment, start_new_session=True)
            timed_out = False
            try:
                proc.wait(timeout=max(1, 3500 - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
        receipt.update(exit_code=proc.returncode, total_seconds=time.monotonic() - started,
                       stdout_sha256=digest(out / "scorer-stdout.txt"), stderr_sha256=digest(out / "scorer-stderr.txt"))
        atomic_json(out / "gpu_receipt.json", receipt)
        if timed_out:
            raise TimeoutError("local_scorer_timeout")
        if proc.returncode != 0:
            raise RuntimeError("local_scorer_exit_nonzero")
        metrics = json.loads((scoring_out / "metrics.json").read_text())
        count = 16 if formal else 12
        if (metrics["overall"]["n"] != count or len(metrics["per_image"]) != count
                or metrics["nfe_per_image"] != 100 or metrics["num_steps"] != 25):
            raise RuntimeError("scorer_protocol_mismatch")
        if formal:
            if metrics["public"]["n"] != 12 or metrics["hidden"]["n"] != 4:
                raise RuntimeError("formal_split_mismatch")
        elif any(row["split"] != "public" for row in metrics["per_image"]):
            raise RuntimeError("public_split_mismatch")
        if metrics["method_sha256"] != digest(bridge):
            raise RuntimeError("numeric_bridge_identity_mismatch")
        anchors = json.loads((runtime / "anchors.json").read_text())
        split = "full" if formal else "public"
        baseline = anchors["baseline"][split]["psnr"]
        upper = anchors["upper_bound"][split]["psnr"]
        expected = (metrics["overall"]["psnr"] - baseline) / (upper - baseline)
        if not math.isfinite(expected) or abs(expected - metrics["score"]) > 1e-10:
            raise RuntimeError("normalization_mismatch")
        for row in metrics["per_image"]:
            if not all(math.isfinite(float(row[key])) for key in ("psnr", "ssim", "pixel_mse", "latent_mse")):
                raise RuntimeError("nonfinite_per_image_metric")
        atomic_json(out / "numeric_metrics.json", metrics)
        metrics["schedule_bridge_sha256"] = metrics["method_sha256"]
        metrics["method_sha256"] = method_digest
        return metrics, receipt

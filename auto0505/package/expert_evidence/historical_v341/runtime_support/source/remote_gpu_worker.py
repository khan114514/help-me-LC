#!/usr/bin/env python3
"""Trusted SSH worker: finite nodes in, frozen GPU evaluation out.

Only this file runs on the GPU host. Candidate source never crosses this boundary.
The role and optional control task checksum come from trusted process argv, never
from the request. This numerical cache is not claimed to be a v3.4 Harbor task.
"""
import argparse
import ctypes
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import struct
import subprocess
import sys
import time
import uuid

REQUEST_LIMIT = 16384
RESPONSE_LIMIT = 2 << 20
TOTAL_TIMEOUT_SEC = 3500
QUEUE_TIMEOUT_SEC = 600
SCORER_SHA256 = "23993adad6641121c03950e777089cb702a14e3c7a9f4cb0e9e55685542afaf9"
REPO_SHA256 = "af8bec543dba11eb1f9c8697577461c1b68b585b7ae89753e202068c60d3c623"
ANCHOR_SHA256 = {
    "public": "f0c7c9d1b184ef2f0a364bd153b58cf74a3874f40098d089babf2adcfbfe1ab5",
    "formal": "50076621400ca5bfd087acf5434f4d0e241926ffa84dbd9fa3e04eadef8a983f",
}
PUBLIC_FILES = {
    "coco_000000000139.png": "410abbaa2b30b9386fb1d53aefc21af172d292026fbb81f61c23c9301a88ead8",
    "coco_000000000285.png": "3acce04c32eccd56472e4269a7e57ea1ac8f2ede5ff7216d34b399e8a2276f6b",
    "coco_000000000632.png": "f19d159764fa3aeb612c0a090aa27d82934fab43675e6bf05b218c3a4dd7f729",
    "coco_000000001000.png": "837ede6bcebcc4465c1555c48d85130d5bf9829469b052bdbe5718649b4132fa",
    "coco_000000001268.png": "3876caece29c6b1a681b061e6e1577828839c14394abb68372b252cb92c59e95",
    "coco_000000001425.png": "26830a640e3974480e1b8c734c46af479c74d6e273ad4f52dbd106b954e5b049",
    "coco_000000001490.png": "be0522e9c34479fa5da9f4a433454affd8a468a8cbab897ad75c6d7f24f6e104",
    "coco_000000039769.png": "fd6f28d91862d2dd0b8265afb1da553b3a3f9bc91841c1040a8598042b4324e5",
    "repo_art.png": "95e0d7bfa351fa3b00f90d667e7ab7ca5da261e44fcf4473de50bde6eed5e9ea",
    "repo_boy.png": "b7c9e147c4635e10953fb14cdad472ff1bfaa54ae6147ae096c24133b019697a",
    "repo_horse.png": "dceef30c01ae1814a274ac264823c851145c5623dd268bff715b5e339855f952",
    "repo_nobel.png": "1496a92a885c211c5de07dc23dd346047079f76982754639c40e18021ded60d5",
}
HIDDEN_FILES = {
    "coco_000000000802.png": "642688ad84d6c9c3f64d1e9f66c388e5857da157e7ea9e5a9be8c0132b768be7",
    "coco_000000001296.png": "00dba577e9dcb25f07b4d06f50f05ddfaae8c46826bc59d44c48fe7a548c0d93",
    "repo_cartoon.png": "6ed0bb12d07ecf772e868c2f33f88bbe782882d4ac3a6dbc36597928a3182bda",
    "repo_hiking.png": "13c42ee741a032e7caba387654becfe5a366f897557d72b8b4ac7b3d478f8966",
}
WEIGHTS = {
    "flux-dev/flux1-dev.safetensors": "4610115bb0c89560703c892c59ac2742fa821e60ef5871b33493ba544683abd7",
    "flux-schnell/ae.safetensors": "afc8e28272cd15db3919bacdb6918ce9c1ed22e96cb12c4d5ed0fba823529e38",
    "t5-encoder-bf16/model.safetensors": "565cb2487351282e8e4dbeb88e63f4ad28217ce0439f5a8e6525a924807d2d9b",
    "clip-vit-l14/model.safetensors": "a2bf730a0c7debf160f7a6b50b3aaf3703e7e88ac73de7a314903141db026dcb",
}
MESSAGES = {
    "INVALID_REQUEST": "Request must contain only a canonical UUID job_id and 26 legal finite timesteps.",
    "BUSY": "The GPU or RPC execution lease is unavailable; no score was accepted.",
    "INFRASTRUCTURE_ERROR": "Required frozen runtime or assets failed verification; inspect the organizer-side receipt.",
    "SCORER_TIMEOUT": "The scoring process exceeded the bounded job deadline; no score was accepted.",
    "SCORER_ERROR": "The frozen scorer did not complete a valid full numerical evaluation.",
}


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def reject_constant(_):
    raise ValueError("nonfinite JSON constant")


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def decode_json(raw):
    if len(raw) > REQUEST_LIMIT:
        raise ValueError("request too large")
    return json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)


def validate_request(data):
    if not isinstance(data, dict) or set(data) != {"job_id", "timesteps"}:
        raise ValueError("unexpected request fields")
    job_id = data["job_id"]
    if not isinstance(job_id, str) or str(uuid.UUID(job_id)) != job_id:
        raise ValueError("noncanonical UUID")
    values = data["timesteps"]
    if not isinstance(values, list) or len(values) != 26:
        raise ValueError("wrong timestep count")
    if any(type(v) not in (int, float) for v in values):
        raise ValueError("timesteps must be numbers")
    values = [float(v) for v in values]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("nonfinite timesteps")
    # The same numerical tolerances as the frozen scorer and v3.3 CPU guard.
    if abs(values[0] - 1.0) > 1e-6 or abs(values[-1]) > 1e-6:
        raise ValueError("invalid endpoints")
    if any(v < -1e-9 or v > 1 + 1e-9 for v in values):
        raise ValueError("timesteps out of bounds")
    if any(a < b - 1e-12 for a, b in zip(values, values[1:])):
        raise ValueError("increasing timesteps")
    return {"job_id": job_id, "timesteps": values}


def nodes_sha256(values):
    # Shared wrapper/controller contract: convert to floats before compact JSON.
    canonical = json.dumps([float(v) for v in values], separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, path)


def response(status, role, job_id, receipt=None, metrics=None):
    return {
        "schema_version": 1,
        "status": status,
        "evaluation_completed": status == "COMPLETE",
        "role": role,
        "job_id": job_id,
        "metrics": metrics if status == "COMPLETE" else None,
        "receipt": receipt or {},
        "record_infra_error": None if status == "COMPLETE" else {
            "code": status, "message": MESSAGES[status],
        },
    }


class JobError(Exception):
    def __init__(self, status, reason_code):
        self.status, self.reason_code = status, reason_code


def require(condition, reason):
    if not condition:
        raise JobError("INFRASTRUCTURE_ERROR", reason)


def verify_images(directory, expected):
    directory = Path(directory)
    actual = {p.name: p for p in directory.iterdir() if p.is_file() and p.suffix == ".png"}
    require(set(actual) == set(expected), "image_file_set_mismatch")
    result = {}
    for name, expected_hash in sorted(expected.items()):
        path = actual[name]
        require(not path.is_symlink(), "asset_symlink_rejected")
        with path.open("rb") as stream:
            header = stream.read(24)
        require(header[:8] == b"\x89PNG\r\n\x1a\n" and len(header) == 24,
                "image_png_header_invalid")
        require(struct.unpack("!II", header[16:24]) == (512, 512), "image_dimensions_mismatch")
        result[name] = sha256_file(path)
        require(result[name] == expected_hash, "image_hash_mismatch")
    return result


def repo_sha256(root):
    records = []
    for path in sorted(Path(root).rglob("*")):
        if path.is_file() and (path.suffix == ".py" or path.name == "LICENSE"):
            require(not path.is_symlink(), "runtime_symlink_rejected")
            records.append(str(path.relative_to(root)) + " " + sha256_file(path) + "\n")
    return hashlib.sha256("".join(records).encode()).hexdigest()


def gpu_snapshot():
    try:
        p = subprocess.run([
            "nvidia-smi", "--query-gpu=index,name,uuid,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ], capture_output=True, text=True, timeout=10)
        q = subprocess.run([
            "nvidia-smi", "--query-compute-apps=pid,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ], capture_output=True, text=True, timeout=10)
        require(p.returncode == 0 and q.returncode == 0, "gpu_query_failed")
        lines = p.stdout.strip().splitlines()
        require(len(lines) == 1, "expected_one_gpu")
        index, name, gpu_uuid, total, used, util = [v.strip() for v in lines[0].split(",")]
        require(("A100" in name or "H100" in name) and int(total) >= 38000,
                "gpu_type_or_memory_mismatch")
        processes = []
        for line in q.stdout.strip().splitlines():
            pid, memory = [v.strip() for v in line.split(",")]
            processes.append({"pid": int(pid), "used_memory_mib": int(memory)})
        return {"observed_at": utc_now(), "index": int(index), "name": name,
                "uuid": gpu_uuid, "total_memory_mib": int(total),
                "used_memory_mib": int(used), "utilization_percent": int(util),
                "compute_processes": processes}
    except (ValueError, OSError, subprocess.SubprocessError):
        raise JobError("INFRASTRUCTURE_ERROR", "gpu_query_unavailable") from None


def require_gpu_idle(snapshot):
    if (snapshot["used_memory_mib"] > 512 or snapshot["utilization_percent"] > 5
            or snapshot["compute_processes"]):
        raise JobError("BUSY", "gpu_not_idle")


def kill_own_process(process):
    # This process group was created by this worker, never obtained from GPU pids.
    if process is not None and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=15)


def verify_metrics(metrics, role, bridge_hash, anchors):
    split = "public" if role == "public" else "full"
    expected_files = [("public", name[:-4]) for name in PUBLIC_FILES]
    if role == "formal":
        expected_files += [("hidden", name[:-4]) for name in HIDDEN_FILES]
    require(isinstance(metrics, dict), "metrics_not_object")
    require(metrics.get("split") == split and metrics.get("num_steps") == 25
            and metrics.get("nfe_per_image") == 100
            and metrics.get("method_sha256") == bridge_hash, "metrics_protocol_mismatch")
    rows = metrics.get("per_image")
    require(isinstance(rows, list) and len(rows) == len(expected_files), "metrics_count_mismatch")
    require({(r.get("split"), r.get("image")) for r in rows} == set(expected_files),
            "metrics_image_set_mismatch")
    for row in rows:
        for name in ("psnr", "ssim", "pixel_mse", "latent_mse"):
            value = row.get(name)
            require(type(value) in (int, float) and math.isfinite(value), "nonfinite_image_metric")
    overall = metrics.get("overall", {})
    require(overall.get("n") == len(expected_files), "aggregate_count_mismatch")
    for name in ("psnr", "ssim", "pixel_mse", "latent_mse"):
        value = overall.get(name)
        require(type(value) in (int, float) and math.isfinite(value), "nonfinite_aggregate_metric")
        mean = sum(r[name] for r in rows) / len(rows)
        require(math.isclose(value, mean, rel_tol=1e-10, abs_tol=1e-10), "aggregate_mean_mismatch")
    b = anchors["baseline"][split]["psnr"]
    u = anchors["upper_bound"][split]["psnr"]
    expected_score = (overall["psnr"] - b) / (u - b)
    require(type(metrics.get("score")) in (int, float)
            and math.isfinite(metrics["score"])
            and math.isclose(metrics["score"], expected_score, rel_tol=1e-10, abs_tol=1e-10),
            "normalized_score_mismatch")
    require(metrics.get("anchors") == {"baseline_psnr": b, "upper_bound_psnr": u},
            "metric_anchor_mismatch")


def run_job(request, role, base, weights_root, task_checksum):
    base, weights_root = Path(base), Path(weights_root)
    task = base / "harbor_task"
    scorer = task / "tests/run_eval.py"
    repo = task / "tests/repo/RF-Solver-Edit/FLUX_Image_Edit"
    public = task / "environment/public_assets/eval_public"
    hidden = base / "private_hidden_assets"
    anchors_path = (task / "environment/public_eval/anchors.json" if role == "public"
                    else task / "tests/anchors.json")
    python = base / "venv/bin/python3"
    jobs_root = base / "rpc_jobs"
    jobs_root.mkdir(mode=0o700, exist_ok=True)
    require(not jobs_root.is_symlink(), "job_root_symlink_rejected")
    jobs_root.chmod(0o700)
    job = jobs_root / request["job_id"]
    try:
        job.mkdir(mode=0o700)
    except FileExistsError:
        return response("INFRASTRUCTURE_ERROR", role, request["job_id"],
                        {"failure_code": "job_id_already_exists", "control_task_checksum": task_checksum})
    receipt = {
        "control_task_checksum": task_checksum,
        "numerical_runtime_profile": "frozen-v3.3-numerics-over-role-bound-GPU-RPC",
        "worker_sha256": sha256_file(__file__),
        "nodes_sha256": nodes_sha256(request["timesteps"]),
        "received_at": utc_now(), "queue_started_at": utc_now(),
        "queue_finished_at": None, "queue_seconds": None,
        "scoring_started_at": None, "scoring_finished_at": None,
        "scoring_seconds": None, "exit_code": None,
        "protocol": {"num_steps": 25, "nfe_per_image": 100, "image_size": [512, 512],
                     "model": "flux-dev", "dtype": "bf16", "prompt": "", "guidance": 1,
                     "inject_step": 0, "split": "public" if role == "public" else "full"},
    }
    started = time.monotonic()
    deadline = started + TOTAL_TIMEOUT_SEC
    lock = None
    process = None
    log_path = job / "scorer-stdout.txt"
    previous_signals = {}
    def controller_cancelled(*_):
        raise JobError("SCORER_TIMEOUT", "trusted_controller_connection_terminated")
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        previous_signals[signum] = signal.signal(signum, controller_cancelled)
    try:
        atomic_json(job / "request.json", request)
        lock = (base / "rpc_gpu.lock").open("a")
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - started >= QUEUE_TIMEOUT_SEC:
                    raise JobError("BUSY", "execution_lease_queue_timeout")
                time.sleep(0.2)
        receipt["queue_finished_at"] = utc_now()
        receipt["queue_seconds"] = time.monotonic() - started
        receipt["gpu_before"] = gpu_snapshot()
        require_gpu_idle(receipt["gpu_before"])
        receipt["scorer_sha256"] = sha256_file(scorer)
        require(receipt["scorer_sha256"] == SCORER_SHA256, "scorer_hash_mismatch")
        receipt["repo_sha256"] = repo_sha256(repo)
        require(receipt["repo_sha256"] == REPO_SHA256, "runtime_hash_mismatch")
        receipt["anchors_sha256"] = sha256_file(anchors_path)
        require(receipt["anchors_sha256"] == ANCHOR_SHA256[role], "anchor_hash_mismatch")
        receipt["asset_sha256"] = {"public": verify_images(public, PUBLIC_FILES)}
        if role == "formal":
            receipt["asset_sha256"]["hidden"] = verify_images(hidden, HIDDEN_FILES)
        # Execute fresh byte-identical Python files, excluding inherited pyc
        # caches. Hashing source alone is not proof that an old cache was unused.
        frozen = job / "frozen"
        frozen.mkdir(mode=0o700)
        execution_scorer = frozen / "run_eval.py"
        execution_anchors = frozen / "anchors.json"
        execution_repo = frozen / "repo"
        execution_repo.mkdir(mode=0o700)
        shutil.copyfile(scorer, execution_scorer)
        shutil.copyfile(anchors_path, execution_anchors)
        for source in sorted(repo.rglob("*")):
            if source.is_file() and (source.suffix == ".py" or source.name == "LICENSE"):
                target = execution_repo / source.relative_to(repo)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        require(sha256_file(execution_scorer) == SCORER_SHA256
                and repo_sha256(execution_repo) == REPO_SHA256
                and sha256_file(execution_anchors) == ANCHOR_SHA256[role], "fresh_runtime_copy_mismatch")
        receipt["runtime_execution"] = "fresh byte-identical source copy; no inherited Python caches"
        receipt["weights_sha256"] = {}
        for name, expected in WEIGHTS.items():
            path = weights_root / name
            require(path.is_file() and not path.is_symlink(), "weight_missing_or_symlink")
            value = sha256_file(path)
            require(value == expected, "weight_hash_mismatch")
            receipt["weights_sha256"][name] = value
        receipt["weight_support_sha256"] = {
            str(p.relative_to(weights_root)): sha256_file(p)
            for dirname in ("t5-encoder-bf16", "clip-vit-l14")
            for p in sorted((weights_root / dirname).iterdir())
            if p.is_file() and p.suffix != ".safetensors"
        }
        require(python.is_file() and os.access(python, os.X_OK), "python_runtime_missing")
        eval_root = job / "eval"
        eval_root.mkdir(mode=0o700)
        (eval_root / "public").symlink_to(public, target_is_directory=True)
        if role == "formal":
            (eval_root / "hidden").symlink_to(hidden, target_is_directory=True)
        bridge = job / "literal_schedule.py"
        bridge.write_text("def get_timesteps(num_steps, image_seq_len):\n    return "
                          + repr(request["timesteps"]) + "\n")
        bridge.chmod(0o600)
        receipt["bridge_sha256"] = sha256_file(bridge)
        output = job / "output"
        output.mkdir(mode=0o700)
        home = job / "home"
        home.mkdir(mode=0o700)
        env = {"PATH": "/opt/conda/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": str(home),
               "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
               "OMP_NUM_THREADS": "8", "MKL_NUM_THREADS": "8",
               "OPENBLAS_NUM_THREADS": "8", "TOKENIZERS_PARALLELISM": "false",
               "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HOME": str(home / "hf"),
               "RFSTEPS_REPO_SRC": str(execution_repo / "src"), "RFSTEPS_WEIGHTS": str(weights_root),
               "RFSTEPS_EVAL": str(eval_root), "RFSTEPS_ANCHORS": str(execution_anchors),
               "RFSTEPS_LOCK": str(base / "rpc_frozen_scorer.lock"),
               "CUDA_VISIBLE_DEVICES": str(receipt["gpu_before"]["index"])}
        metadata_code = (
            "import json,sys,importlib.metadata as m,torch; "
            "names=['torch','numpy','einops','pillow','scikit-image','transformers',"
            "'huggingface-hub','safetensors','sentencepiece','invisible-watermark','requests']; "
            "print(json.dumps({'python':sys.version,'packages':{n:m.version(n) for n in names},"
            "'imported_torch':torch.__version__,'cuda_runtime':torch.version.cuda,"
            "'cuda_available':torch.cuda.is_available()}))"
        )
        metadata = subprocess.run([str(python), "-c", metadata_code], env=env,
                                  capture_output=True, text=True, timeout=45)
        require(metadata.returncode == 0, "runtime_metadata_probe_failed")
        receipt["environment"] = json.loads(metadata.stdout)
        require(receipt["environment"]["cuda_available"], "cuda_unavailable")
        receipt["gpu_at_scoring_start"] = gpu_snapshot()
        require_gpu_idle(receipt["gpu_at_scoring_start"])
        affinity = sorted(os.sched_getaffinity(0))[:8] if hasattr(os, "sched_getaffinity") else None
        receipt["cpu_affinity"] = affinity
        worker_parent_pid = os.getpid()

        def child_limits():
            if sys.platform == "linux":
                libc = ctypes.CDLL(None, use_errno=True)
                # The scorer dies if this worker disappears abruptly, including
                # SIGKILL. No host GPU pid or unrelated process is ever targeted.
                if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
                    raise OSError(ctypes.get_errno(), "PR_SET_PDEATHSIG failed")
                if os.getppid() != worker_parent_pid:
                    os.kill(os.getpid(), signal.SIGKILL)
            if affinity is not None:
                os.sched_setaffinity(0, affinity)
            resource.setrlimit(resource.RLIMIT_FSIZE, (256 << 20, 256 << 20))

        command = [str(python), str(execution_scorer), "--method", str(bridge), "--out", str(output),
                   "--split", receipt["protocol"]["split"]]
        atomic_json(job / "command.json", {"argv": command, "environment": env})
        if time.monotonic() >= deadline:
            raise JobError("SCORER_TIMEOUT", "preflight_exhausted_job_deadline")
        receipt["scoring_started_at"] = utc_now()
        scoring_start = time.monotonic()
        next_sample = scoring_start
        peak_rss = 0
        with log_path.open("x") as log, (job / "gpu-observations.jsonl").open("x") as telemetry:
            process = subprocess.Popen(command, env=env, cwd=job, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True,
                                       preexec_fn=child_limits)
            receipt["scorer_process_pid"] = process.pid
            try:
                while process.poll() is None:
                    now = time.monotonic()
                    if now >= deadline:
                        raise JobError("SCORER_TIMEOUT", "total_job_deadline")
                    if now >= next_sample:
                        snapshot = gpu_snapshot()
                        try:
                            for line in Path("/proc/%d/status" % process.pid).read_text().splitlines():
                                if line.startswith("VmRSS:"):
                                    snapshot["scorer_rss_bytes"] = int(line.split()[1]) * 1024
                                    peak_rss = max(peak_rss, snapshot["scorer_rss_bytes"])
                                    break
                        except (OSError, ValueError):
                            snapshot["scorer_rss_bytes"] = None
                        telemetry.write(json.dumps(snapshot) + "\n")
                        telemetry.flush()
                        # A single fresh scorer is the only RPC GPU process. Host
                        # vs container pid namespaces may differ, so preserve pids
                        # rather than pretend nvidia-smi pids equal local pids.
                        if len(snapshot["compute_processes"]) > 1:
                            raise JobError("BUSY", "concurrent_gpu_process_detected")
                        next_sample = now + 1
                    time.sleep(0.1)
            finally:
                kill_own_process(process)
                receipt["exit_code"] = process.returncode
                receipt["scoring_finished_at"] = utc_now()
                receipt["scoring_seconds"] = time.monotonic() - scoring_start
                receipt["scorer_peak_rss_observed_bytes"] = peak_rss
        receipt["gpu_after"] = gpu_snapshot()
        require(process.returncode == 0, "scorer_nonzero_exit")
        metrics_path = output / "metrics.json"
        require(metrics_path.is_file() and metrics_path.stat().st_size <= RESPONSE_LIMIT,
                "metrics_missing_or_oversized")
        metrics = json.loads(metrics_path.read_text(), parse_constant=reject_constant)
        anchors = json.loads(anchors_path.read_text())
        verify_metrics(metrics, role, receipt["bridge_sha256"], anchors)
        schedule_path = output / "schedule.json"
        schedule = json.loads(schedule_path.read_text())
        require(schedule.get("num_steps") == 25 and schedule.get("timesteps") == request["timesteps"],
                "scored_schedule_does_not_match_request")
        receipt["schedule_sha256"] = sha256_file(schedule_path)
        require(sha256_file(scorer) == SCORER_SHA256 and repo_sha256(repo) == REPO_SHA256,
                "runtime_changed_during_evaluation")
        require(sha256_file(execution_scorer) == SCORER_SHA256 and repo_sha256(execution_repo) == REPO_SHA256,
                "execution_source_changed_during_evaluation")
        require(sha256_file(anchors_path) == ANCHOR_SHA256[role], "anchors_changed_during_evaluation")
        require(verify_images(public, PUBLIC_FILES) == receipt["asset_sha256"]["public"],
                "public_changed_during_evaluation")
        if role == "formal":
            require(verify_images(hidden, HIDDEN_FILES) == receipt["asset_sha256"]["hidden"],
                    "hidden_changed_during_evaluation")
        receipt["metrics_sha256"] = sha256_file(metrics_path)
        receipt["png_sha256"] = {p.name: sha256_file(p) for p in sorted(output.glob("*.png"))}
        expected_recon = {"recon_" + name for name in PUBLIC_FILES}
        if role == "formal":
            expected_recon.update("recon_" + name for name in HIDDEN_FILES)
        require(set(receipt["png_sha256"]) == expected_recon,
                "reconstruction_png_count_mismatch")
        receipt["exclusivity_evidence"] = "serialized RPC lease; GPU idle before launch; sampled compute-process inventory"
        result = response("COMPLETE", role, request["job_id"], receipt, metrics)
    except JobError as exc:
        receipt["failure_code"] = exc.reason_code
        status = exc.status
        if exc.reason_code == "scorer_nonzero_exit":
            status = "SCORER_ERROR"
        result = response(status, role, request["job_id"], receipt)
    except (OSError, ValueError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
        receipt["failure_code"] = "trusted_runtime_operation_failed"
        result = response("INFRASTRUCTURE_ERROR", role, request["job_id"], receipt)
    finally:
        kill_own_process(process)
        if lock is not None:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
        for signum, previous in previous_signals.items():
            signal.signal(signum, previous)
    receipt["finished_at"] = utc_now()
    receipt["total_seconds"] = time.monotonic() - started
    if receipt["queue_finished_at"] is None:
        receipt["queue_finished_at"] = receipt["finished_at"]
        receipt["queue_seconds"] = receipt["total_seconds"]
    if log_path.exists():
        receipt["scorer_log_sha256"] = sha256_file(log_path)
    gpu_log = job / "gpu-observations.jsonl"
    if gpu_log.exists():
        receipt["gpu_observations_sha256"] = sha256_file(gpu_log)
    if not result["evaluation_completed"]:
        # Keep rejected raw diagnostics private, never in the accepted output
        # location or structured metrics field. No reward is written by worker.
        for name in ("metrics.json", "reward.json", "reward.txt"):
            rejected = job / "output" / name
            if rejected.exists():
                quarantine = job / "rejected-diagnostics"
                quarantine.mkdir(mode=0o700, exist_ok=True)
                receipt.setdefault("rejected_output_sha256", {})[name] = sha256_file(rejected)
                rejected.rename(quarantine / name)
    atomic_json(job / "receipt.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("public", "formal"), required=True)
    parser.add_argument("--base", default=('' + ('/' + 'root/') + 'rfsteps-v33-numeric-check-20261004'),
                        help="trusted deployment configuration, never supplied by a candidate")
    parser.add_argument("--weights-root", default=('' + ('/' + 'root/') + 'rivermind-data/weights'))
    parser.add_argument("--task-checksum", help="trusted current Harbor task directory SHA-256")
    args = parser.parse_args()
    os.umask(0o077)
    if args.task_checksum is not None and not re.fullmatch(r"[0-9a-f]{64}", args.task_checksum):
        result = response("INFRASTRUCTURE_ERROR", args.role, None,
                          {"failure_code": "invalid_control_task_checksum"})
    else:
        try:
            request = validate_request(decode_json(sys.stdin.buffer.read(REQUEST_LIMIT + 1)))
        except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
            result = response("INVALID_REQUEST", args.role, None)
        else:
            try:
                result = run_job(request, args.role, args.base, args.weights_root, args.task_checksum)
            except (OSError, JobError, ValueError):
                result = response("INFRASTRUCTURE_ERROR", args.role, request["job_id"],
                                  {"failure_code": "job_storage_unavailable",
                                   "control_task_checksum": args.task_checksum})
    encoded = json.dumps(result, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode()) > RESPONSE_LIMIT:
        encoded = json.dumps(response("INFRASTRUCTURE_ERROR", args.role, result.get("job_id"),
                                      {"failure_code": "receipt_size_limit"}))
    # Sole stdout event. Scorer stdout/stderr stay in the private job directory.
    print(encoded, flush=True)
    return 0 if result["evaluation_completed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

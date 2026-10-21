"""Separate untrusted schedule execution from the frozen numerical scorer."""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import socket
import uuid
import subprocess
import sys
import tempfile
import time
import stat
import errno


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, path)


CPU_LIMIT_SECONDS = 30
WALL_LIMIT_SECONDS = 35
AS_LIMIT_BYTES = 512 << 20
SOURCE_LIMIT_BYTES = 1 << 20
WORKER_EXIT_STATUS = {42: "FORMAT_ERROR", 43: "HARD_GATE_INVALID", 44: "RESOURCE_EXCEEDED"}


class CandidateFailure(Exception):
    def __init__(self, status, reason_code, evidence=None, rpc_result=None):
        self.status = status
        self.reason_code = reason_code
        self.evidence = evidence or {}
        self.rpc_result = rpc_result
        super().__init__(reason_code)


def record_failure(out, status, message, *, evidence=None, invalid_candidate=False):
    # Only an explicitly classified non-cheating Hard Gate invalidity gets -1.
    # The legacy keyword is retained for call compatibility, not status coercion.
    out = Path(out)
    for name in ("reward.json", "reward.txt", "metrics.json"):
        (out / name).unlink(missing_ok=True)
    actions = {
        "FORMAT_ERROR": "Provide syntactically valid method.py and a callable get_timesteps returning 26 numeric values.",
        "HARD_GATE_INVALID": "Meet the frozen finite/domain/endpoint/order, stdlib-origin and no-subprocess gates.",
        "TIMEOUT": "Reduce candidate CPU work or blocking; stay below CPU30s and wall35s.",
        "RESOURCE_EXCEEDED": "Reduce source/address-space/output/process usage to the declared limits.",
        "INFRASTRUCTURE_ERROR": "Ask the expert to repair the trusted runtime; do not treat this as a score.",
    }
    atomic_json(out / "evaluation_status.json", {
        "schema_version": 1, "status": status, "evaluation_completed": False,
        "reason_code": message, "reason": message, "action": actions.get(status, "Inspect the expert-side failure record."),
        "execution_evidence": evidence or {}, "psnr": None, "score": None,
    })
    if status == "HARD_GATE_INVALID":
        atomic_json(out / "reward.json", {"reward": -1.0})
    print("[evaluation]", status + ":", message, flush=True)


def validate_schedule(values):
    if len(values) != 26:
        raise CandidateFailure("FORMAT_ERROR", "schedule_shape_requires_26")
    if not all(math.isfinite(v) for v in values):
        raise CandidateFailure("HARD_GATE_INVALID", "schedule_nonfinite")
    if abs(values[0] - 1.0) > 1e-6 or abs(values[-1]) > 1e-6:
        raise CandidateFailure("HARD_GATE_INVALID", "schedule_endpoints")
    if any(v < -1e-9 or v > 1 + 1e-9 for v in values):
        raise CandidateFailure("HARD_GATE_INVALID", "schedule_domain")
    if any(a < b - 1e-12 for a, b in zip(values, values[1:])):
        raise CandidateFailure("HARD_GATE_INVALID", "schedule_order")
    return values


def restrict_candidate():
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_SECONDS, CPU_LIMIT_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT_BYTES, AS_LIMIT_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))
    # Prevent privilege restoration through setuid executables.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS failed")
    if os.geteuid() == 0:
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)


def kill_owned_candidate(process):
    """Signal only this unreaped Popen session, with its actual dropped UID.

    The trusted CLI is single threaded. The saved parent UID remains root;
    SETUID is already required for candidate privilege dropping. CAP_KILL is
    deliberately absent from the frozen container, so match the candidate's
    UID for this one signal and restore it before any other parent operation.
    An unreaped child PID cannot be recycled before this exact wait4 boundary.
    """
    parent_euid = os.geteuid()
    signal_euid = 65534 if parent_euid == 0 else parent_euid
    try:
        if signal_euid != parent_euid:
            os.seteuid(signal_euid)
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    finally:
        if os.geteuid() != parent_euid:
            os.seteuid(parent_euid)
    return {"owned_worker_pid": process.pid, "signal_euid": signal_euid,
            "parent_euid_restored": os.geteuid() == parent_euid}


def extract_schedule(method, worker, scratch, worker_python=None):
    if not Path(worker).is_file() or Path(worker).is_symlink():
        raise CandidateFailure("INFRASTRUCTURE_ERROR", "trusted_worker_missing_or_unsafe")
    method = Path(method)
    try:
        if not stat.S_ISREG(method.lstat().st_mode) or method.is_symlink():
            raise CandidateFailure("FORMAT_ERROR", "method_source_must_be_regular")
        with method.open("rb") as stream:
            source = stream.read(SOURCE_LIMIT_BYTES + 1)
    except FileNotFoundError:
        raise CandidateFailure("FORMAT_ERROR", "method_source_missing") from None
    if len(source) > SOURCE_LIMIT_BYTES:
        raise CandidateFailure("RESOURCE_EXCEEDED", "method_source_size")
    scratch = Path(scratch)
    scratch.chmod(0o755)
    copy = scratch / "candidate.py"
    copy.write_bytes(source)
    copy.chmod(0o644)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                [worker_python or str(Path(sys.executable).resolve()), "-I", "-B", str(worker), str(copy)],
                cwd=scratch, stdout=stdout, stderr=stderr,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
                     "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
                start_new_session=True, preexec_fn=restrict_candidate,
            )
        except (OSError, subprocess.SubprocessError):
            raise CandidateFailure("INFRASTRUCTURE_ERROR", "trusted_worker_start_failed") from None
        started = time.monotonic()
        usage = None
        wall_timeout = False
        cleanup_evidence = {}
        try:
            while True:
                pid, wait_status, usage = os.wait4(process.pid, os.WNOHANG)
                if pid:
                    process.returncode = os.waitstatus_to_exitcode(wait_status)
                    break
                if time.monotonic() - started >= WALL_LIMIT_SECONDS:
                    wall_timeout = True
                    cleanup_evidence = kill_owned_candidate(process)
                    _, wait_status, usage = os.wait4(process.pid, 0)
                    process.returncode = os.waitstatus_to_exitcode(wait_status)
                    break
                time.sleep(0.01)
        finally:
            if process.returncode is None:
                kill_owned_candidate(process)
                process.wait()
        evidence = {"exit_code": process.returncode, "wall_seconds": time.monotonic() - started,
                    "cpu_seconds": usage.ru_utime + usage.ru_stime,
                    "max_rss_kib": usage.ru_maxrss,
                    "cpu_limit_seconds": CPU_LIMIT_SECONDS, "wall_limit_seconds": WALL_LIMIT_SECONDS,
                    "address_space_limit_bytes": AS_LIMIT_BYTES,
                    "owned_signal_cleanup": cleanup_evidence}
        if wall_timeout:
            raise CandidateFailure("TIMEOUT", "candidate_wall_timeout", evidence)
        if process.returncode in (-signal.SIGXCPU, -signal.SIGKILL) and evidence["cpu_seconds"] >= CPU_LIMIT_SECONDS - 0.1:
            raise CandidateFailure("TIMEOUT", "candidate_cpu_timeout", evidence)
        if process.returncode == -signal.SIGXFSZ:
            raise CandidateFailure("RESOURCE_EXCEEDED", "candidate_output_file_limit", evidence)
        if process.returncode < 0:
            # Unknown external signals must not be invented as CPU/memory facts.
            raise CandidateFailure("INFRASTRUCTURE_ERROR", "worker_signal_termination_unattributed", evidence)
        stdout.seek(0)
        try:
            raw = stdout.read((1 << 20) + 1)
            if len(raw) > 1 << 20:
                raise ValueError()
            data = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError):
            raise CandidateFailure("FORMAT_ERROR", "candidate_worker_output_invalid", evidence) from None
        expected = WORKER_EXIT_STATUS.get(process.returncode)
        if expected:
            if (not isinstance(data, dict) or set(data) != {"schema_version", "status", "reason_code"}
                    or data.get("schema_version") != 1 or data.get("status") != expected
                    or not isinstance(data.get("reason_code"), str)):
                raise CandidateFailure("INFRASTRUCTURE_ERROR", "trusted_worker_failure_protocol", evidence)
            raise CandidateFailure(expected, data["reason_code"], evidence)
        if process.returncode != 0:
            raise CandidateFailure("FORMAT_ERROR", "candidate_abnormal_exit", evidence)
        if (not isinstance(data, dict) or set(data) != {"schema_version", "status", "timesteps"}
                or data.get("schema_version") != 1 or data.get("status") != "NODES_READY"):
            raise CandidateFailure("FORMAT_ERROR", "candidate_worker_success_protocol", evidence)
        try:
            values = [float(value) for value in data["timesteps"]]
        except (ValueError, KeyError, TypeError):
            raise CandidateFailure("FORMAT_ERROR", "candidate_return_value_format", evidence) from None
    try:
        values = validate_schedule(values)
    except CandidateFailure as failure:
        failure.evidence = evidence
        raise
    return values, hashlib.sha256(source).hexdigest()


def rpc_evaluate(nodes, formal):
    job_id = str(uuid.uuid4())
    path = "/run/rfsteps/formal.sock" if formal else "/run/rfsteps/public.sock"
    request = json.dumps({"job_id": job_id, "timesteps": nodes}, allow_nan=False).encode() + b"\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(3720)
        connection.connect(path)
        connection.sendall(request)
        connection.shutdown(socket.SHUT_WR)
        chunks = []
        size = 0
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > 2 << 20:
                raise ValueError("trusted GPU receipt exceeded its limit")
            chunks.append(chunk)
    result = json.loads(b"".join(chunks))
    if not isinstance(result, dict):
        raise ValueError("trusted GPU receipt is not an object")
    expected_role = "formal" if formal else "public"
    if result.get("job_id") != job_id or result.get("role") != expected_role:
        raise ValueError("trusted GPU receipt binding mismatch")
    if result.get("status") == "SCORER_TIMEOUT":
        # A timeout is trusted only after the own job/role binding above and
        # a coherent failed response. Contradictory or malformed receipts are
        # infrastructure failures, never normal scores or candidate -1.
        if (result.get("evaluation_completed") is not False
                or result.get("metrics") is not None
                or not isinstance(result.get("receipt"), dict)
                or not isinstance(result.get("record_infra_error"), dict)):
            raise ValueError("trusted GPU timeout receipt is inconsistent")
        raise CandidateFailure("TIMEOUT", "remote_scorer_timeout",
            {"job_id": job_id, "role": expected_role, "rpc_status": "SCORER_TIMEOUT"},
            rpc_result=result)
    if not result.get("evaluation_completed") or result.get("status") != "COMPLETE":
        reason = result.get("record_infra_error") or "remote scorer did not complete"
        raise RuntimeError(str(result.get("status", "INFRASTRUCTURE_ERROR")) + ": " + str(reason))
    metrics = result["metrics"]
    count = 16 if formal else 12
    if metrics["overall"]["n"] != count or len(metrics["per_image"]) != count:
        raise ValueError("trusted GPU result has the wrong image count")
    if metrics["nfe_per_image"] != 100 or metrics["num_steps"] != 25:
        raise ValueError("trusted GPU result has the wrong budget")
    if not formal and ((metrics.get("hidden") or {}).get("n", 0) != 0 or any(x["split"] != "public" for x in metrics["per_image"])):
        raise ValueError("public endpoint returned unexpected material")
    receipt = result["receipt"]
    expected_nodes = hashlib.sha256(json.dumps(nodes, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if receipt.get("nodes_sha256") != expected_nodes or receipt.get("scorer_sha256") != "23993adad6641121c03950e777089cb702a14e3c7a9f4cb0e9e55685542afaf9":
        raise ValueError("trusted GPU input identity mismatch")
    return metrics, result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method")
    parser.add_argument("--out", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--worker-python", default="/usr/bin/python3")
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--record-infrastructure-error")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)
    for name in ("reward.json", "reward.txt", "metrics.json", "evaluation_status.json", "gpu_receipt.json", "remote_metrics.json"):
        (out / name).unlink(missing_ok=True)
    if args.record_infrastructure_error:
        record_failure(out, "INFRASTRUCTURE_ERROR", args.record_infrastructure_error)
        return 2
    if args.formal and os.geteuid() != 0:
        record_failure(out, "INFRASTRUCTURE_ERROR", "formal scoring requires the isolated verifier")
        return 2
    if not args.method or not Path(args.method).is_file():
        record_failure(out, "FORMAT_ERROR", "submitted_method_missing")
        return 1
    with tempfile.TemporaryDirectory(prefix="rfsteps_candidate_") as scratch:
        try:
            values, method_digest = extract_schedule(args.method, args.worker, scratch, args.worker_python)
        except CandidateFailure as exc:
            record_failure(out, exc.status, exc.reason_code, evidence=exc.evidence)
            return {"FORMAT_ERROR": 1, "HARD_GATE_INVALID": 1, "TIMEOUT": 3,
                    "RESOURCE_EXCEEDED": 4, "INFRASTRUCTURE_ERROR": 2}[exc.status]
        except (OSError, subprocess.SubprocessError) as exc:
            record_failure(out, "INFRASTRUCTURE_ERROR", str(exc))
            return 2
    try:
        metrics, raw = rpc_evaluate(values, args.formal)
        atomic_json(out / "gpu_receipt.json", raw)
        atomic_json(out / "remote_metrics.json", metrics)
        metrics = dict(metrics)
        metrics["schedule_bridge_sha256"] = metrics["method_sha256"]
        metrics["method_sha256"] = method_digest
        reward = {"reward": float(metrics["score"]), "psnr": float(metrics["overall"]["psnr"]), "ssim": float(metrics["overall"]["ssim"]), "nfe_per_image": float(metrics["nfe_per_image"])}
        if not all(math.isfinite(x) for x in reward.values()):
            raise ValueError("nonfinite metric")
        atomic_json(out / "metrics.json", metrics)
        atomic_json(out / "evaluation_status.json", {"status": "COMPLETE", "evaluation_completed": True, "split": "full" if args.formal else "public", "method_sha256": method_digest, "psnr": reward["psnr"], "score": reward["reward"], "gpu_job_id": raw["job_id"]})
        atomic_json(out / "reward.json", reward)
    except CandidateFailure as exc:
        if exc.rpc_result is not None:
            atomic_json(out / "gpu_receipt.json", exc.rpc_result)
        record_failure(out, exc.status, exc.reason_code, evidence=exc.evidence)
        return {"TIMEOUT": 3, "INFRASTRUCTURE_ERROR": 2}.get(exc.status, 2)
    except TimeoutError:
        # socket.timeout is TimeoutError too. No completed response exists;
        # retain its distinct transport deadline without inventing a receipt.
        record_failure(out, "TIMEOUT", "score_transport_timeout")
        return 3
    except (OSError, KeyError, ValueError, TypeError, RuntimeError) as exc:
        record_failure(out, "INFRASTRUCTURE_ERROR", str(exc))
        return 2
    print("[evaluation] COMPLETE reward:", json.dumps(reward), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

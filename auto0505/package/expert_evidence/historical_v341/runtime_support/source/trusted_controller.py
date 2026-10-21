#!/usr/bin/env python3
"""Private controller for the role-bound numerical RPC.

Credentials are generated in memory and sent to the host gateway through stdin.
Only validated numeric nodes can cross the SSH boundary. This process is owned
by the organizer and is never mounted into either task container.
"""
import argparse
import datetime as dt
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import shlex
import signal
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rpc_contract", HERE / "socket_gateway.py")
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


class Controller(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, args, tokens, log):
        self.args, self.tokens, self.log = args, tokens, log
        self.log_lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(2)
        self.jobs_lock = threading.Lock()
        self.jobs = set()
        super().__init__(("127.0.0.1", 0), Handler)

    def record(self, item):
        with self.log_lock:
            self.log.write(json.dumps({"time": now(), **item}, allow_nan=False) + "\n")
            self.log.flush()

    def mirror_result(self, request, result):
        """Seal worker output outside every Agent mount before replying to it."""
        raw = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
        name = request["job_id"] + ".json"
        local = Path(self.args.evidence_dir) / "trusted-receipts"
        local.mkdir(mode=0o700, exist_ok=True)
        with (local / name).open("xb") as file:
            file.write(raw); file.flush(); os.fsync(file.fileno())
        # Static trusted program, validated UUID and organizer-only /root path.
        code = (
            "import os,stat,sys,uuid; from pathlib import Path; "
            f"root=Path({self.args.trusted_receipts_root!r}); "
            "root.mkdir(mode=0o700,exist_ok=True); s=root.lstat(); "
            "assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700; "
            f"target=root/{name!r}; data=sys.stdin.buffer.read({contract.RESPONSE_LIMIT + 1}); "
            f"assert 0<len(data)<={contract.RESPONSE_LIMIT}; "
            "temp=root/('.receipt-'+uuid.uuid4().hex); "
            "fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); "
            "f=os.fdopen(fd,'wb'); f.write(data); f.flush(); os.fsync(f.fileno()); f.close(); "
            "os.link(temp,target); temp.unlink(); "
            "fd=os.open(root,os.O_RDONLY); os.fsync(fd); os.close(fd)"
        )
        transfer = subprocess.run([
            "ssh", "-o", "BatchMode=yes", "-o", "ClearAllForwardings=yes", "-o",
            "ConnectTimeout=10", self.args.control_host, shlex.join(["python3", "-c", code])],
            input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
        if transfer.returncode != 0:
            raise RuntimeError("trusted receipt mirror failed")
        self.record({"event": "trusted_receipt_sealed", "job_id": request["job_id"],
                     "role": result["role"], "response_sha256": hashlib.sha256(raw).hexdigest(),
                     "trusted_receipts_root": self.args.trusted_receipts_root})


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *_):
        pass

    def send_json(self, status, body):
        raw = json.dumps(body, separators=(",", ":"), allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (OSError, BrokenPipeError):
            pass

    def do_POST(self):
        server = self.server
        role, request = None, None
        self.connection.settimeout(5)
        try:
            length = self.headers.get("Content-Length")
            if (self.path != "/evaluate" or self.headers.get("Transfer-Encoding")
                    or length is None or not length.isdecimal()
                    or not 0 < int(length) <= contract.REQUEST_LIMIT):
                raise ValueError("invalid HTTP framing")
            body = contract.decode_json(self.rfile.read(int(length)))
            if not isinstance(body, dict) or set(body) != {"role", "request"}:
                raise ValueError("invalid envelope")
            role = body["role"]
            if role not in ("public", "formal"):
                raise ValueError("invalid role")
            expected = "Bearer " + server.tokens[role]
            if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
                self.send_json(401, {"error": "unauthorized"})
                return
            request = contract.validate_request(body["request"])
            with server.jobs_lock:
                if request["job_id"] in server.jobs or len(server.jobs) >= 8192:
                    raise ValueError("job replay or job limit")
                server.jobs.add(request["job_id"])
        except (OSError, ValueError, TypeError, KeyError, OverflowError, UnicodeError):
            self.send_json(400, {"error": "invalid request"})
            return
        if not server.slots.acquire(blocking=False):
            self.send_json(200, contract.failure("BUSY", role, request["job_id"], "controller_job_limit"))
            return
        started = time.monotonic()
        result = contract.failure("INFRASTRUCTURE_ERROR", role, request["job_id"], "trusted_ssh_failure")
        try:
            argv = [server.args.gpu_python, server.args.gpu_worker,
                    "--base", server.args.gpu_base, "--role", role,
                    "--task-checksum", server.args.task_checksum]
            command = ["ssh", "-o", "BatchMode=yes", "-o", "ClearAllForwardings=yes", "-o", "ConnectTimeout=10",
                       "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
                       server.args.gpu_host, shlex.join(argv)]
            process = subprocess.run(command, input=json.dumps(request, allow_nan=False).encode(),
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3530)
            if len(process.stdout) <= contract.RESPONSE_LIMIT:
                parsed = contract.decode_json(process.stdout, contract.RESPONSE_LIMIT)
                parsed = contract.validate_response(parsed, role, request["job_id"])
                if parsed["evaluation_completed"] and process.returncode != 0:
                    raise ValueError("completed payload with nonzero worker exit")
                if parsed["receipt"].get("control_task_checksum") != server.args.task_checksum:
                    raise ValueError("unbound control task")
                result = parsed
            server.record({"event": "worker_exit", "job_id": request["job_id"], "role": role,
                           "exit_code": process.returncode, "stdout_bytes": len(process.stdout),
                           "stderr_sha256": hashlib.sha256(process.stderr).hexdigest()})
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
            pass
        finally:
            server.slots.release()
        server.record({"event": "job_finished", "job_id": request["job_id"], "role": role,
                       "status": result["status"], "elapsed_seconds": time.monotonic() - started,
                       "response_sha256": hashlib.sha256(json.dumps(result, sort_keys=True,
                                                                   allow_nan=False).encode()).hexdigest()})
        try:
            server.mirror_result(request, result)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            server.record({"event": "trusted_receipt_mirror_failed", "job_id": request["job_id"],
                           "role": role})
            result = contract.failure("INFRASTRUCTURE_ERROR", role, request["job_id"],
                                      "trusted_receipt_mirror_failed")
        self.connection.settimeout(5)
        self.send_json(200, result)


def stop_child(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def stop_owned_gateway(args, ready):
    if not ready or type(ready.get("pid")) is not int or type(ready.get("start_ticks")) is not int:
        return
    # A trusted startup receipt binds PID plus start time and exact command.
    code = ("from pathlib import Path; import os,signal; "
            f"p=Path('/proc/{ready['pid']}'); "
            "s=(p/'stat').read_text(); ticks=int(s[s.rfind(')')+2:].split()[19]); "
            f"assert ticks=={ready['start_ticks']}; "
            f"assert (p/'cmdline').read_bytes().split(b'\\0')[:2]==[b'python3',{args.gateway.encode()!r}]; "
            f"os.kill({ready['pid']},signal.SIGTERM)")
    try:
        subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                        args.control_host, shlex.join(["python3", "-c", code])],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-host", default="root@118.195.251.134")
    parser.add_argument("--gpu-host", required=True)
    parser.add_argument("--gpu-python", required=True)
    parser.add_argument("--gpu-base", required=True)
    parser.add_argument("--gpu-worker", required=True)
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--socket-root", required=True)
    parser.add_argument("--remote-port", type=int, required=True)
    parser.add_argument("--task-checksum", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--trusted-receipts-root", required=True)
    parser.add_argument("--gateway-identity", required=True)
    parser.add_argument("--gateway-lifecycle-log", required=True)
    parser.add_argument("--recovery-max-attempts", type=int, default=6)
    parser.add_argument("--recovery-max-outage-seconds", type=float, default=300)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{64}", args.task_checksum):
        parser.error("task checksum must be a SHA-256")
    receipt_root = Path(args.trusted_receipts_root)
    if receipt_root.parent != Path("/root") or not re.fullmatch(r"rfsteps-[a-zA-Z0-9-]+", receipt_root.name):
        parser.error(('trusted receipt root must be a dedicated direct ' + ('/' + 'root/') + 'rfsteps-* directory'))
    from detached_gateway_lifecycle import (BoundedSSHProcess, ReverseForwardRecovery,
        launch_detached_ssh, cleanup_detached_ssh, reverse_ssh_argv, safe_record)
    for name in ("gateway", "socket_root", "gateway_identity", "gateway_lifecycle_log"):
        if not Path(getattr(args, name)).is_absolute():
            parser.error("remote source and metadata paths must be absolute")
    if not 1024 <= args.remote_port <= 65535:
        parser.error("invalid reverse port")
    os.umask(0o077)
    evidence = Path(args.evidence_dir)
    evidence.mkdir(parents=True, exist_ok=False)
    tokens = {role: secrets.token_urlsafe(48) for role in ("public", "formal")}
    recovery = server = ready = None
    owner = str(uuid.uuid4())
    halt = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: halt.set())
    try:
        with (evidence / "controller-events.jsonl").open("x") as log:
            server = Controller(args, tokens, log)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            local_port = server.server_address[1]
            recovery = ReverseForwardRecovery(
                lambda: BoundedSSHProcess(reverse_ssh_argv(args.control_host, args.remote_port, local_port)),
                server.record, max_attempts=args.recovery_max_attempts,
                max_outage_seconds=args.recovery_max_outage_seconds)
            recovery.start()
            while recovery.tick() != "UP":
                if halt.wait(0.1) or recovery.state == "EXHAUSTED_WAIT_OPERATOR":
                    raise RuntimeError("initial_reverse_forward_not_ready")
            config = {"upstream_url": f"http://127.0.0.1:{args.remote_port}/evaluate",
                      "public_token": tokens["public"], "formal_token": tokens["formal"],
                      "socket_root": args.socket_root}
            try:
                ready = launch_detached_ssh(args.control_host, args.gateway, config,
                    identity_path=args.gateway_identity, diagnostics_path=args.gateway_lifecycle_log,
                    owner_id=owner)
            finally:
                config.clear()
            expected_sha = hashlib.sha256((HERE / "socket_gateway.py").read_bytes()).hexdigest()
            if ready.get("ready") is not True or ready.get("source_sha256") != expected_sha:
                raise RuntimeError("detached_gateway_source_mismatch")
            metadata = {"ready": True, "pid": os.getpid(), "started_at": now(),
                "task_checksum": args.task_checksum, "socket_root": args.socket_root,
                "reverse_forward_port": args.remote_port, "gateway_owner_id": owner,
                "gateway_pid": ready["pid"], "gateway_start_ticks": ready["start_ticks"],
                "gateway_identity": args.gateway_identity, "detached_gateway": True,
                "controller_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "gateway_sha256": expected_sha,
                "lifecycle_sha256": hashlib.sha256((HERE / "detached_gateway_lifecycle.py").read_bytes()).hexdigest(),
                "gpu_worker_sha256": hashlib.sha256((HERE / "remote_gpu_worker.py").read_bytes()).hexdigest(),
                "trusted_receipts_root": args.trusted_receipts_root,
                "credentials": "RAM only; gateway receives role tokens once through stdin",
                "research_credit_seconds": 0}
            (evidence / "readiness.json").write_text(json.dumps(metadata, indent=2) + "\n")
            print(json.dumps(metadata), flush=True)
            server.record({"event": "ready", "task_checksum": args.task_checksum,
                           "research_credit_seconds": 0})
            while not halt.wait(0.25):
                recovery.tick()  # Only owned reverse-forward process; never replay HTTP jobs.
            server.record({"event": "shutdown_requested", "research_credit_seconds": 0})
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("[controller] service failed; no score accepted", flush=True)
        return 2
    finally:
        if recovery is not None:
            recovery.close()
        if ready is not None:
            result = cleanup_detached_ssh(args.control_host, ready,
                        str(Path(args.gateway).parent / "detached_gateway_lifecycle.py"))
            safe_record(evidence / "lifecycle-cleanup.jsonl", "owned_cleanup", status=result.get("cleanup"))
        if server is not None:
            server.shutdown()
            server.server_close()
        tokens.clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

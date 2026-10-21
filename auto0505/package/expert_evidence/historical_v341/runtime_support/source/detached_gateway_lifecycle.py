"""Private draft: RAM-only detached gateways and bounded reverse-SSH recovery.

No model, evaluation, or HTTP request is retried by this module. Diagnostics
contain fixed codes and process identity only, never startup config or payload.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading
import time
import uuid

MAX_READY_BYTES = 8192


def linux_identity(pid: int) -> dict:
    if type(pid) is not int or pid <= 1:
        raise ValueError("invalid_pid")
    base = Path("/proc") / str(pid)
    raw = (base / "stat").read_text().rsplit(")", 1)[1].split()
    command = (base / "cmdline").read_bytes().split(b"\0")
    return {"pid": pid, "start_ticks": int(raw[19]), "state": raw[0],
            "command": command}


def safe_record(path: Path, event: str, **fields) -> None:
    allowed = {"pid", "start_ticks", "owner_id", "source_sha256", "status",
               "error_type", "return_code", "attempt", "outage_seconds",
               "stderr_bytes", "stderr_sha256", "diagnostic_codes"}
    if not set(fields) <= allowed:
        raise ValueError("unsafe_diagnostic_fields")
    record = {"event": event, "utc_ns": time.time_ns(),
              "research_credit_seconds": 0, **fields}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, (json.dumps(record, separators=(",", ":")) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def detach_and_run(config: dict, serve, *, source_path: str, identity_path: str,
                   diagnostics_path: str, owner_id: str, timeout_seconds=20) -> int:
    """Fork exactly once; the child owns RAM config, stdio and its own metadata.

    serve(config, announce) must announce only after its own sockets exist. It
    must do normal exact-inode cleanup in finally. Linux proc identity is a
    hard condition; no simulated identity is permitted in this implementation.
    """
    source = Path(source_path).resolve(strict=True)
    identity = Path(identity_path)
    diagnostics = Path(diagnostics_path)
    if (not identity.is_absolute() or not diagnostics.is_absolute()
            or identity == diagnostics or identity.exists()
            or not identity.parent.is_dir() or not diagnostics.parent.is_dir()
            or not isinstance(owner_id, str) or str(uuid.UUID(owner_id)) != owner_id):
        raise ValueError("invalid_detached_paths_or_owner")
    linux_identity(os.getpid())  # Reject unsupported OS before fork.
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child:
        os.close(write_fd)
        # The parent must not keep an extra RAM copy after this one startup.
        config.clear()
        raw = bytearray()
        end = time.monotonic() + timeout_seconds
        try:
            while b"\n" not in raw:
                remain = end - time.monotonic()
                if remain <= 0 or not select.select([read_fd], [], [], remain)[0]:
                    raise TimeoutError("detached_readiness_timeout")
                part = os.read(read_fd, min(4096, MAX_READY_BYTES + 1 - len(raw)))
                if not part:
                    raise ValueError("detached_child_no_readiness")
                raw.extend(part)
                if len(raw) > MAX_READY_BYTES:
                    raise ValueError("detached_readiness_too_large")
            value = json.loads(bytes(raw).split(b"\n", 1)[0])
            if value.get("detached") is not True or value.get("pid") != child:
                raise ValueError("detached_child_not_ready")
            # Bounded metadata only. Normal startup SSH returns 0 afterward.
            print(json.dumps(value, separators=(",", ":")), flush=True)
            return 0
        except (OSError, ValueError, TimeoutError):
            # No blind second fork. A lost readiness may have a live daemon;
            # its nonsecret owner metadata makes expert recovery possible.
            safe_record(diagnostics, "startup_handshake_failed", error_type="readiness_failed")
            return 2
        finally:
            os.close(read_fd)
    os.close(read_fd)
    exit_code = 2
    identity_inode = None
    announced = False
    try:
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        for target in (0, 1, 2):
            os.dup2(devnull, target)
        if devnull > 2:
            os.close(devnull)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        source_sha = hashlib.sha256(source.read_bytes()).hexdigest()

        def announce(value):
            nonlocal announced, identity_inode
            if announced:
                raise ValueError("duplicate_detached_readiness")
            actual = linux_identity(os.getpid())
            document = {"schema_version": 1, "pid": actual["pid"],
                        "start_ticks": actual["start_ticks"], "owner_id": owner_id,
                        "source_path": str(source), "source_sha256": source_sha}
            fd = os.open(identity, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.write(fd, (json.dumps(document, separators=(",", ":")) + "\n").encode())
                os.fsync(fd)
                info = os.fstat(fd)
                identity_inode = (info.st_dev, info.st_ino)
            finally:
                os.close(fd)
            metadata = {**value, **document, "detached": True}
            encoded = (json.dumps(metadata, separators=(",", ":")) + "\n").encode()
            if len(encoded) > MAX_READY_BYTES:
                raise ValueError("detached_readiness_too_large")
            os.write(write_fd, encoded)
            os.close(write_fd)
            announced = True
            safe_record(diagnostics, "daemon_ready", pid=actual["pid"],
                        start_ticks=actual["start_ticks"], owner_id=owner_id,
                        source_sha256=source_sha)

        exit_code = int(serve(config, announce) or 0)
    except BaseException as error:
        safe_record(diagnostics, "daemon_failed", error_type=type(error).__name__)
    finally:
        config.clear()
        if not announced:
            try:
                os.close(write_fd)
            except OSError:
                pass
        if identity_inode is not None:
            try:
                info = identity.lstat()
                if (info.st_dev, info.st_ino) == identity_inode:
                    identity.unlink()
            except FileNotFoundError:
                pass
        safe_record(diagnostics, "daemon_stopped", status=exit_code)
        os._exit(exit_code)


def cleanup_exact_linux(document: dict, *, timeout_seconds=10) -> dict:
    """SIGTERM only the supplied exact Linux PID/birth/script/owner tuple."""
    try:
        pid, ticks = document["pid"], document["start_ticks"]
        source, owner = document["source_path"], document["owner_id"]
        actual = linux_identity(pid)
        command = actual["command"]
        source_bytes, owner_bytes = source.encode(), owner.encode()
        if (type(ticks) is not int or actual["start_ticks"] != ticks
                or len(command) < 2 or command[1] != source_bytes
                or b"--owner-id" not in command
                or command[command.index(b"--owner-id") + 1] != owner_bytes):
            return {"cleanup": "identity_mismatch", "signal_sent": False}
        if actual["state"] == "Z":
            return {"cleanup": "already_stopped", "signal_sent": False}
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                current = linux_identity(pid)
                if current["start_ticks"] != ticks or current["state"] == "Z":
                    return {"cleanup": "stopped", "signal_sent": True}
            except FileNotFoundError:
                return {"cleanup": "stopped", "signal_sent": True}
            time.sleep(0.05)
        return {"cleanup": "not_confirmed", "signal_sent": True}
    except (KeyError, TypeError, ValueError, OSError, IndexError):
        return {"cleanup": "not_confirmed", "signal_sent": False}


class BoundedSSHProcess:
    """Drain child stderr continuously; keep hashes/fixed codes, never raw text."""
    def __init__(self, argv):
        self.process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.stderr_bytes = 0
        self.stderr_hash = hashlib.sha256()
        self.codes = set()
        self._forward_confirmed = False
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self):
        tail = b""
        while True:
            part = self.process.stderr.read1(4096)
            if not part:
                return
            with self._lock:
                self.stderr_bytes += len(part)
                self.stderr_hash.update(part)
                text = (tail + part).lower()
                if b"remote forward success for:" in text:
                    self._forward_confirmed = True
                for pattern, code in ((b"broken pipe", "ssh_broken_pipe"),
                                      (b"connection refused", "ssh_connection_refused"),
                                      (b"timed out", "ssh_timeout"),
                                      (b"permission denied", "ssh_auth_failed"),
                                      (b"remote port forwarding failed", "ssh_forward_failed")):
                    if pattern in text:
                        self.codes.add(code)
                tail = text[-80:]

    def poll(self):
        return self.process.poll()

    def ready(self):
        with self._lock:
            return self._forward_confirmed

    def diagnostics(self):
        with self._lock:
            return {"stderr_bytes": self.stderr_bytes,
                    "stderr_sha256": self.stderr_hash.hexdigest(),
                    "diagnostic_codes": sorted(self.codes)}

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self._thread.join(timeout=1)
        if not self._thread.is_alive():
            self.process.stderr.close()


class ReverseForwardRecovery:
    """Bounded process reconnection, never HTTP/evaluation/model replay.

    Only a failed reverse-forward SSH child is replaced. The same gateway,
    credentials, remote port and UDS stay fixed. Retry budget is lifetime-wide,
    including brief flapping connections. Budget exhaustion stays alive
    in EXHAUSTED_WAIT_OPERATOR with no more attempts until explicit shutdown.
    """
    def __init__(self, spawn, record, *, clock=time.monotonic,
                 max_attempts=6, max_outage_seconds=300, backoff=(2, 5, 10, 20, 30, 60),
                 startup_grace_seconds=0.5):
        if (type(max_attempts) is not int or max_attempts < 1
                or max_outage_seconds <= 0 or not backoff
                or any(v < 0 for v in backoff) or startup_grace_seconds < 0):
            raise ValueError("invalid_recovery_budget")
        self.spawn, self.record, self.clock = spawn, record, clock
        self.max_attempts, self.max_outage_seconds = max_attempts, max_outage_seconds
        self.backoff, self.grace = tuple(backoff), startup_grace_seconds
        self.current = None
        self.state = "NOT_STARTED"
        self.outage_started = None
        self.attempts = 0
        self.next_try = None
        self.candidate_started = None

    def _record(self, event, **fields):
        self.record({"event": event, "research_credit_seconds": 0, **fields})

    def start(self):
        if self.state != "NOT_STARTED":
            raise ValueError("reverse_reentry_forbidden")
        self.current = self.spawn()
        self.candidate_started = self.clock()
        self.state = "STARTING"

    def tick(self):
        now = self.clock()
        if self.state in ("EXHAUSTED_WAIT_OPERATOR", "CLOSED"):
            return self.state
        if self.current is not None:
            code = self.current.poll()
            if code is None and self.state in ("STARTING", "RECOVERING"):
                if now - self.candidate_started >= self.grace and self.current.ready():
                    self.state = "UP"
                    self._record("reverse_forward_up", attempt=self.attempts,
                                 outage_seconds=0 if self.outage_started is None else now-self.outage_started)
                    self.outage_started = None
                elif now-self.candidate_started >= self.max_outage_seconds:
                    self.current.stop()
                    self.current = None
                    self.state = "EXHAUSTED_WAIT_OPERATOR"
                    self._record("reverse_forward_readiness_exhausted", attempt=self.attempts,
                                 outage_seconds=now-self.candidate_started)
                return self.state
            if code is None:
                return self.state
            diag = self.current.diagnostics()
            self.current.stop()
            self.current = None
            if self.outage_started is None:
                self.outage_started = now
                self._record("reverse_forward_outage", return_code=code, **diag)
            else:
                self._record("reverse_forward_retry_failed", return_code=code,
                             attempt=self.attempts, **diag)
            self.state = "DOWN"
            self.next_try = now + self.backoff[min(self.attempts, len(self.backoff)-1)]
        if self.outage_started is not None:
            if self.attempts >= self.max_attempts or now-self.outage_started >= self.max_outage_seconds:
                self.state = "EXHAUSTED_WAIT_OPERATOR"
                self._record("reverse_forward_recovery_exhausted", attempt=self.attempts,
                             outage_seconds=now-self.outage_started)
            elif now >= self.next_try:
                self.attempts += 1
                self._record("reverse_forward_retry", attempt=self.attempts,
                             outage_seconds=now-self.outage_started)
                self.current = self.spawn()
                self.candidate_started = now
                self.state = "RECOVERING"
        return self.state

    def close(self):
        if self.current is not None:
            self.current.stop()
            self.current = None
        self.state = "CLOSED"


def launch_detached_ssh(host, gateway_path, config, *, identity_path,
                        diagnostics_path, owner_id, startup_timeout=25):
    """One startup stdin write only; stdout readiness is bounded and drained."""
    import shlex
    argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ClearAllForwardings=yes",
            "-o", "ControlMaster=no", "-o", "ControlPath=none",
            "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3", host,
            shlex.join(["python3", gateway_path, "--detach", "--identity-path", identity_path,
                        "--lifecycle-log", diagnostics_path, "--owner-id", owner_id])]
    # Consume stderr continuously without retaining raw diagnostics. Only this
    # startup writes config; timeout/lost readiness must never start another daemon.
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    stderr_reader = threading.Thread(target=lambda: _discard(process.stderr), daemon=True)
    stderr_reader.start()
    raw = bytearray()
    deadline = time.monotonic() + startup_timeout
    try:
        encoded = json.dumps(config, allow_nan=False).encode()
        if len(encoded) > 4096:
            raise ValueError("startup_config_too_large")
        process.stdin.write(encoded)
        process.stdin.close()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                raise TimeoutError("detached_startup_timeout_no_retry")
            part = os.read(process.stdout.fileno(), 4096)
            if not part:
                break
            raw.extend(part)
            if len(raw) > MAX_READY_BYTES:
                raise ValueError("detached_startup_output_too_large")
        code = process.wait(timeout=max(0.01, deadline-time.monotonic()))
        if code != 0:
            raise ValueError("detached_startup_failed_no_retry")
        ready = json.loads(raw)
        if (ready.get("detached") is not True or type(ready.get("pid")) is not int
                or type(ready.get("start_ticks")) is not int or ready.get("owner_id") != owner_id
                or ready.get("source_path") != gateway_path):
            raise ValueError("detached_startup_identity_failed")
        return ready
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        stderr_reader.join(timeout=1)
        process.stdout.close()
        process.stderr.close()


def cleanup_detached_ssh(host, ready, helper_path):
    """No credentials cross this cleanup call; remote verifier fails closed."""
    import shlex
    code = ("import json,sys;sys.path.insert(0," + repr(str(Path(helper_path).parent)) + ");"
            "from detached_gateway_lifecycle import cleanup_exact_linux;"
            "print(json.dumps(cleanup_exact_linux(json.load(sys.stdin))))")
    argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ClearAllForwardings=yes",
            "-o", "ControlMaster=no", "-o", "ControlPath=none", host,
            shlex.join(["python3", "-B", "-c", code])]
    try:
        data = {k:ready[k] for k in ("pid", "start_ticks", "source_path", "owner_id")}
        result = subprocess.run(argv, input=json.dumps(data).encode(), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=15)
        if result.returncode == 0 and len(result.stdout) < 4096:
            return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        pass
    return {"cleanup": "not_confirmed", "signal_sent": False}


def _discard(stream):
    while stream.read(4096):
        pass


def reverse_ssh_argv(host, remote_port, local_port):
    if (type(remote_port) is not int or type(local_port) is not int
            or not 1024 <= remote_port <= 65535 or not 1 <= local_port <= 65535):
        raise ValueError("invalid_forward_ports")
    # -F /dev/null excludes inherited LocalForward/RemoteForward configuration.
    # ClearAllForwardings=yes would also suppress our explicit authorized -R.
    return ["ssh", "-v", "-F", "/dev/null", "-N", "-T", "-o", "BatchMode=yes", "-o",
            "ControlMaster=no", "-o", "ControlPath=none", "-o", "ConnectTimeout=10",
            "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30", "-o",
            "ServerAliveCountMax=3", "-R", f"127.0.0.1:{remote_port}:127.0.0.1:{local_port}", host]

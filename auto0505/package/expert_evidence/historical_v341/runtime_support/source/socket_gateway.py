#!/usr/bin/env python3
"""Role-bound UDS gateway; startup credentials are consumed from stdin only.

Mount public.sock alone into the Agent, formal.sock alone into the Verifier.
A read-only socket mount still permits RPC: role enforcement happens here and at
the authenticated host controller, not through the bind mount's read-only flag.
"""
import argparse
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import socketserver
import stat
import sys
import threading
import time
from urllib.parse import urlsplit
import uuid

REQUEST_LIMIT = 16384
RESPONSE_LIMIT = 2 << 20
REQUEST_READ_TIMEOUT = 5
UPSTREAM_TIMEOUT = 3540
MAX_TRACK_JOBS = 4096
STATUSES = {"COMPLETE", "INVALID_REQUEST", "BUSY", "INFRASTRUCTURE_ERROR", "SCORER_TIMEOUT", "SCORER_ERROR"}


def parse_proc_start_ticks(raw, expected_pid):
    # /proc stat field 2 (comm) may itself contain spaces and parentheses.
    prefix, separator, remaining = raw.rpartition(")")
    pid_text = prefix.partition("(")[0].strip()
    fields = remaining.split()
    if (not separator or pid_text != str(expected_pid) or len(fields) < 20
            or not fields[19].isdecimal() or int(fields[19]) <= 0):
        raise ValueError("process identity unavailable")
    return int(fields[19])  # field 22; remaining begins at field 3.


def readiness_identity():
    pid = os.getpid()
    ticks = None
    if sys.platform == "linux":
        ticks = parse_proc_start_ticks(Path("/proc/self/stat").read_text(), pid)
    return {"pid": pid, "start_ticks": ticks}


def reject_constant(_):
    raise ValueError("nonfinite JSON constant")


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def decode_json(raw, limit=REQUEST_LIMIT):
    if len(raw) > limit:
        raise ValueError("message size limit")
    return json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)


def validate_request(data):
    if not isinstance(data, dict) or set(data) != {"job_id", "timesteps"}:
        raise ValueError("unexpected request fields")
    job_id = data["job_id"]
    if not isinstance(job_id, str) or str(uuid.UUID(job_id)) != job_id:
        raise ValueError("noncanonical UUID")
    values = data["timesteps"]
    if not isinstance(values, list) or len(values) != 26 or any(type(v) not in (int, float) for v in values):
        raise ValueError("invalid timesteps")
    values = [float(v) for v in values]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("nonfinite timesteps")
    if abs(values[0] - 1.0) > 1e-6 or abs(values[-1]) > 1e-6:
        raise ValueError("invalid endpoints")
    if any(v < -1e-9 or v > 1 + 1e-9 for v in values):
        raise ValueError("out-of-range timesteps")
    if any(a < b - 1e-12 for a, b in zip(values, values[1:])):
        raise ValueError("increasing timesteps")
    return {"job_id": job_id, "timesteps": values}


def validate_startup(data):
    if not isinstance(data, dict) or set(data) != {"upstream_url", "public_token", "formal_token", "socket_root"}:
        raise ValueError("invalid startup configuration")
    url = urlsplit(data["upstream_url"])
    if (url.scheme != "http" or url.hostname != "127.0.0.1" or url.username is not None
            or url.password is not None or url.path != "/evaluate" or url.query or url.fragment
            or url.port is None or not 1 <= url.port <= 65535):
        raise ValueError("upstream must be a fixed loopback HTTP evaluate endpoint")
    tokens = [data["public_token"], data["formal_token"]]
    if any(not isinstance(t, str) or re.fullmatch(r"[A-Za-z0-9_-]{32,256}", t) is None for t in tokens):
        raise ValueError("invalid role credentials")
    if tokens[0] == tokens[1]:
        raise ValueError("role credentials must differ")
    root = data["socket_root"]
    if not isinstance(root, str) or not Path(root).is_absolute() or "\x00" in root:
        raise ValueError("socket root must be an absolute trusted path")
    if len(os.fsencode(str(Path(root) / "formal.sock"))) >= 104:
        raise ValueError("Unix socket path too long")
    return {**data, "upstream_host": url.hostname, "upstream_port": url.port}


def failure(status, role, job_id=None, code=None):
    return {"schema_version": 1, "status": status, "evaluation_completed": False,
            "role": role, "job_id": job_id, "metrics": None,
            "receipt": {"failure_code": code or status.lower(), "transport": "role-bound-uds-to-loopback-http"},
            "record_infra_error": {"code": code or status,
                                   "message": "No evaluation score was accepted; check the organizer-side RPC service."}}


def validate_response(data, role, job_id):
    def finite_json(value, depth=0):
        if depth > 32:
            raise ValueError("response nesting limit")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("nonfinite upstream JSON number")
        if isinstance(value, dict):
            for item in value.values():
                finite_json(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                finite_json(item, depth + 1)
    finite_json(data)
    expected = {"schema_version", "status", "evaluation_completed", "role", "job_id",
                "metrics", "receipt", "record_infra_error"}
    if not isinstance(data, dict) or set(data) != expected:
        raise ValueError("upstream response schema mismatch")
    if data["schema_version"] != 1 or data["role"] != role or data["job_id"] != job_id:
        raise ValueError("upstream response binding mismatch")
    if data["status"] not in STATUSES or type(data["evaluation_completed"]) is not bool:
        raise ValueError("upstream status mismatch")
    if data["evaluation_completed"] != (data["status"] == "COMPLETE"):
        raise ValueError("upstream completion mismatch")
    if not isinstance(data["receipt"], dict):
        raise ValueError("upstream receipt mismatch")
    if data["evaluation_completed"]:
        m = data["metrics"]
        split, count = ("public", 12) if role == "public" else ("full", 16)
        if (not isinstance(m, dict) or m.get("split") != split or m.get("num_steps") != 25
                or m.get("nfe_per_image") != 100 or m.get("overall", {}).get("n") != count
                or not isinstance(m.get("per_image"), list) or len(m["per_image"]) != count
                or type(m.get("score")) not in (int, float) or not math.isfinite(m["score"])
                or data["record_infra_error"] is not None):
            raise ValueError("upstream metrics protocol mismatch")
        expected_splits = {"public"} if role == "public" else {"public", "hidden"}
        if {r.get("split") for r in m["per_image"]} != expected_splits:
            raise ValueError("upstream split escalation")
        if role == "public" and (m.get("hidden") is not None or "hidden" in data["receipt"].get("asset_sha256", {})):
            raise ValueError("upstream private information in public response")
    elif data["metrics"] is not None or not isinstance(data["record_infra_error"], dict):
        raise ValueError("upstream failure carried a score")
    return data


def post_upstream(config, role, request):
    connection = http.client.HTTPConnection(config["upstream_host"], config["upstream_port"],
                                           timeout=UPSTREAM_TIMEOUT)
    deadline = time.monotonic() + UPSTREAM_TIMEOUT
    try:
        body = json.dumps({"role": role, "request": request}, allow_nan=False, separators=(",", ":")).encode()
        lease_cookie = config[role + "_token"]
        connection.request("POST", "/evaluate", body=body,
                           headers={"Authorization": "Bearer " + lease_cookie,
                                    "Content-Type": "application/json", "Connection": "close"})
        result = connection.getresponse()
        if result.status != 200:
            raise ValueError("upstream returned non-200 status")
        length = result.getheader("Content-Length")
        if length is None or not length.isdecimal() or int(length) > RESPONSE_LIMIT:
            raise ValueError("upstream response size or framing invalid")
        if result.getheader("Transfer-Encoding"):
            raise ValueError("upstream chunked response rejected")
        remaining = int(length)
        parts = []
        while remaining:
            budget = deadline - time.monotonic()
            if budget <= 0:
                raise TimeoutError("upstream deadline")
            if connection.sock is not None:
                connection.sock.settimeout(budget)
            part = result.read1(min(65536, remaining))
            if not part:
                raise ValueError("upstream truncated response")
            parts.append(part)
            remaining -= len(part)
        data = validate_response(decode_json(b"".join(parts), RESPONSE_LIMIT), role, request["job_id"])
        if data["evaluation_completed"]:
            canonical = json.dumps(request["timesteps"], separators=(",", ":"), allow_nan=False).encode()
            if data["receipt"].get("nodes_sha256") != hashlib.sha256(canonical).hexdigest():
                raise ValueError("upstream scored nodes do not match request")
        return data
    finally:
        connection.close()


class RoleHandler(socketserver.BaseRequestHandler):
    def handle(self):
        server = self.server
        request = None
        try:
            self.request.settimeout(REQUEST_READ_TIMEOUT)
            # Exactly one newline-delimited JSON request, no second command.
            raw = bytearray()
            deadline = time.monotonic() + REQUEST_READ_TIMEOUT
            while b"\n" not in raw:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("request deadline")
                self.request.settimeout(remaining)
                block = self.request.recv(min(4096, REQUEST_LIMIT + 1 - len(raw)))
                if not block:
                    raise ValueError("missing newline-delimited request")
                raw.extend(block)
                if len(raw) > REQUEST_LIMIT:
                    raise ValueError("request size limit")
            line, trailing = bytes(raw).split(b"\n", 1)
            if trailing.strip():
                raise ValueError("multiple requests are not allowed")
            request = validate_request(decode_json(line))
            with server.state_lock:
                if request["job_id"] in server.used_jobs or len(server.used_jobs) >= MAX_TRACK_JOBS:
                    raise ValueError("job id reuse or job limit")
                server.used_jobs.add(request["job_id"])
            if not server.active_job.acquire(blocking=False):
                result = failure("BUSY", server.role, request["job_id"], "role_job_already_running")
            else:
                try:
                    result = post_upstream(server.config, server.role, request)
                except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError,
                        http.client.HTTPException):
                    result = failure("INFRASTRUCTURE_ERROR", server.role, request["job_id"],
                                     "upstream_unavailable_or_unbound")
                finally:
                    server.active_job.release()
        except (OSError, ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
            result = failure("INVALID_REQUEST", server.role,
                             request["job_id"] if request else None, "request_rejected")
        encoded = json.dumps(result, allow_nan=False, separators=(",", ":")).encode() + b"\n"
        if len(encoded) > RESPONSE_LIMIT:
            encoded = json.dumps(failure("INFRASTRUCTURE_ERROR", server.role,
                                         request["job_id"] if request else None,
                                         "response_size_limit")).encode() + b"\n"
        try:
            self.request.settimeout(5)
            self.request.sendall(encoded)
        except OSError:
            pass


class RoleServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 2

    def __init__(self, path, role, config):
        self.role, self.config = role, config
        self.thread_slots = threading.BoundedSemaphore(2)
        self.active_job = threading.BoundedSemaphore(1)
        self.state_lock = threading.Lock()
        self.used_jobs = set()
        super().__init__(str(path), RoleHandler)

    def process_request(self, request, client_address):
        if not self.thread_slots.acquire(blocking=False):
            try:
                request.settimeout(0.2)
                request.sendall(json.dumps(failure("BUSY", self.role, code="connection_limit")).encode() + b"\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.thread_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.thread_slots.release()

    def handle_error(self, request, client_address):
        # Do not print tracebacks, configuration values, HTTP headers or bodies.
        print("[gateway] request handling failed; no score returned", file=sys.stderr, flush=True)


def serve(config, announce=None, *, detached=False):
    os.umask(0o077)
    root = Path(config["socket_root"])
    servers, started_servers, paths, inode_ids = [], [], [], {}
    stop = threading.Event()
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink() or not root.is_dir() or any(root.iterdir()):
            raise ValueError("socket root must be a fresh empty directory")
        root.chmod(0o700)
        for role in ("public", "formal"):
            path = root / (role + ".sock")
            server = RoleServer(path, role, config)
            path.chmod(0o666 if role == "public" else 0o600)
            inode_ids[path] = path.stat().st_ino
            paths.append(path)
            servers.append(server)
        def request_stop(*_):
            stop.set()
        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        if not detached:
            signal.signal(signal.SIGHUP, request_stop)
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            started_servers.append(server)
        ready = {"ready": True, "protocol": "rfsteps-role-bound-rpc-v1",
                 "public_socket": str(paths[0]), "formal_socket": str(paths[1]),
                 **readiness_identity()}
        if announce is None:
            print(json.dumps(ready), flush=True)
        else:
            announce(ready)
        stop.wait()
    except (OSError, ValueError):
        print("[gateway] startup or socket operation failed", file=sys.stderr, flush=True)
        return 2
    finally:
        for server in started_servers:
            server.shutdown()
        for server in servers:
            server.server_close()
        for path in paths:
            try:
                mode = path.lstat()
                if stat.S_ISSOCK(mode.st_mode) and mode.st_ino == inode_ids[path]:
                    path.unlink()
            except FileNotFoundError:
                pass
        # Tokens never enter argv, files, logs or client-visible responses.
        config.clear()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private draft RAM-only numerical gateway")
    parser.add_argument("--detach", action="store_true")
    parser.add_argument("--identity-path")
    parser.add_argument("--lifecycle-log")
    parser.add_argument("--owner-id")
    args = parser.parse_args(argv)
    try:
        config = validate_startup(decode_json(sys.stdin.buffer.read(REQUEST_LIMIT + 1)))
        if args.detach:
            if not all((args.identity_path, args.lifecycle_log, args.owner_id)):
                raise ValueError("detached metadata paths required")
            from detached_gateway_lifecycle import detach_and_run
            return detach_and_run(config, lambda c, a: serve(c, a, detached=True),
                source_path=__file__, identity_path=args.identity_path,
                diagnostics_path=args.lifecycle_log, owner_id=args.owner_id)
        return serve(config)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        print("[gateway] startup failed", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

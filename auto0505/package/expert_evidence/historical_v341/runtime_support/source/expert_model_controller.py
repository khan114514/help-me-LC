#!/usr/bin/env python3
"""Organizer-only Responses proxy; real credentials remain in process memory."""
from __future__ import annotations
import argparse
import ast
import datetime as dt
import hashlib
import hmac
import http.client
import http.server
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import shlex
import signal
import ssl
import subprocess
import sys
import threading
import time
import uuid

from model_transport import (BoundedThreadingMixIn, Deadline, DeadlineExpired, MAX_REQUEST_BYTES,
                             RejectedRequest, RestrictedHandler, read_request,
                             strict_json)
from model_socket_gateway import ROLE_CONTRACT, validate_role_body


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def read_authorized_gpt_key(path):
    # Parse only one known literal assignment. Never source the legacy script.
    try:
        text = Path(path).read_text()
    except Exception:
        raise RuntimeError("authorized_key_source_unavailable") from None
    matches = re.findall(r'^\s*export\s+AUTORESEARCH_CUSTOM_API_KEY=(.*)$', text, re.M)
    if len(matches) != 1:
        raise RuntimeError("authorized_key_assignment_unavailable")
    try:
        value = ast.literal_eval(matches[0])
    except Exception:
        # SyntaxError.text contains the assignment, including the credential.
        # Neither its message, traceback source nor chained context may escape.
        raise RuntimeError("authorized_key_assignment_invalid") from None
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_.~+/=-]{24,4096}", value) is None:
        raise RuntimeError("authorized_key_assignment_invalid")
    return value


class CredentialLookupTimeout(TimeoutError):
    pass


def read_profile_key(args, deadline=None):
    argv = ["/opt/conda/bin/arkcli", "profile", "apikey", "get", "--plain",
            "--profile", "platform_cn-beijing_accountwide"]
    timeout = min(25, deadline.remaining()) if deadline is not None else 25
    try:
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ClearAllForwardings=yes",
                            "-o", "ConnectTimeout=8", args.profile_host, shlex.join(argv)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        # TimeoutExpired may retain partial stdout/stderr containing a key.
        raise CredentialLookupTimeout("official_profile_lookup_timeout") from None
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("official_profile_key_unavailable") from None
    try:
        if len(p.stdout) > 4096:
            raise ValueError
        value = p.stdout.decode("ascii").strip()
    except (UnicodeError, ValueError):
        raise RuntimeError("official_profile_key_unavailable") from None
    if p.returncode != 0 or re.fullmatch(r"[A-Za-z0-9_.=-]{24,512}", value) is None:
        raise RuntimeError("official_profile_key_unavailable")
    return value


def credential_patterns(values):
    patterns = set()
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        patterns.add(value.encode())
        # Recognize common fully escaped JSON credential representations too.
        patterns.add("".join("\\u%04x" % ord(char) for char in value).encode())
        patterns.add("".join("\\u%04X" % ord(char) for char in value).encode())
    return sorted(patterns, key=lambda item: (-len(item), item))


class StreamingRedactor:
    """Hold only a raw suffix that can still become a credential match."""
    def __init__(self, patterns):
        self.patterns = sorted(set(p for p in patterns if p), key=lambda item: (-len(item), item))
        self.pending = b""
        self.redactions = 0

    def feed(self, data):
        pending = self.pending + bytes(data)
        output = []
        while pending:
            matches = [(pending.find(pattern), -len(pattern), pattern) for pattern in self.patterns]
            matches = [match for match in matches if match[0] >= 0]
            if not matches:
                break
            index, _length, pattern = min(matches)
            output.extend((pending[:index], b"[REDACTED]"))
            pending = pending[index + len(pattern):]
            self.redactions += 1
        keep = 0
        for pattern in self.patterns:
            tail = pending[-min(len(pending), len(pattern) - 1):] if len(pattern) > 1 else b""
            index = tail.find(pattern[:1])
            while index >= 0:
                candidate = tail[index:]
                if pattern.startswith(candidate):
                    keep = max(keep, len(candidate))
                    break
                index = tail.find(pattern[:1], index + 1)
        output.append(pending[:-keep] if keep else pending)
        self.pending = pending[-keep:] if keep else b""
        return b"".join(output)

    def finish(self, *, aborted=False):
        pending, self.pending = self.pending, b""
        if pending and aborted:
            self.redactions += 1
            return b"[REDACTED-PARTIAL]"
        return pending


def redact(raw, key):
    redactor = StreamingRedactor(credential_patterns([key]))
    return redactor.feed(raw) + redactor.finish()


def _safe_usage(value):
    if not isinstance(value, dict):
        return None
    result = {}
    for name in ("input_tokens", "output_tokens", "total_tokens"):
        count = value.get(name)
        if type(count) is int and 0 <= count <= (1 << 63) - 1:
            result[name] = count
    for name, keys in (("input_tokens_details", ("cached_tokens",)),
                       ("output_tokens_details", ("reasoning_tokens",))):
        details = value.get(name)
        if isinstance(details, dict):
            clean = {key: details[key] for key in keys if type(details.get(key)) is int
                     and 0 <= details[key] <= (1 << 63) - 1}
            if clean:
                result[name] = clean
    return result or None


def _safe_identifier(value, secret_values, *, limit=256):
    if (not isinstance(value, str) or len(value) > limit
            or re.fullmatch(r"[A-Za-z0-9_.:/-]+", value) is None
            or any(secret and secret in value for secret in secret_values)):
        return None
    return value


def response_summary(raw, content_type, *, expected_model=None, expected_effort=None,
                     secret_values=(), http_status=200):
    objects = []
    try:
        if content_type.split(";", 1)[0].strip().lower() == "text/event-stream":
            normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            # An unterminated final event is not dispatched by SSE semantics.
            for frame in normalized.split(b"\n\n")[:-1]:
                data, event_name = [], None
                for line in frame.split(b"\n"):
                    field, separator, value = line.partition(b":")
                    if value.startswith(b" "):
                        value = value[1:]
                    if field == b"data":
                        data.append(value if separator else b"")
                    elif field == b"event":
                        event_name = value.decode("utf-8", errors="replace")
                payload = b"\n".join(data)
                if payload and payload != b"[DONE]":
                    try:
                        objects.append((strict_json(payload), event_name))
                    except RejectedRequest:
                        pass
        else:
            objects.append((strict_json(raw), None))
    except (ValueError, UnicodeError, RejectedRequest, RecursionError):
        pass
    terminal, final, event_types = None, {}, set()
    completed_observed, conflict = False, False
    terminals = {"response.completed": "completed", "response.failed": "failed",
                 "response.incomplete": "incomplete", "response.cancelled": "cancelled",
                 "response.error": "error", "error": "error"}
    for obj, named_event in objects:
        if not isinstance(obj, dict):
            continue
        kind = obj.get("type") if isinstance(obj.get("type"), str) else named_event
        safe_kind = _safe_identifier(kind, secret_values)
        if safe_kind and len(event_types) < 128:
            event_types.add(safe_kind)
        if named_event and obj.get("type") and named_event != obj.get("type"):
            conflict = True
            terminal = "event_type_conflict"
            continue
        nested = obj.get("response")
        candidate = nested if isinstance(nested, dict) else obj
        status = candidate.get("status")
        state = terminals.get(kind)
        if state is None and status in ("completed", "failed", "incomplete", "cancelled"):
            state = status
        if state is not None:
            terminal, final = state, candidate
            if state == "completed":
                completed_observed = True
                valid_object = isinstance(nested, dict) and bool(nested) or status == "completed"
                if not valid_object or status not in (None, "completed"):
                    terminal = "invalid_completion"
    model = _safe_identifier(final.get("model"), secret_values)
    reasoning = final.get("reasoning")
    effort = reasoning.get("effort") if isinstance(reasoning, dict) else None
    if effort not in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
        effort = None
    return {"completed": terminal == "completed" and 200 <= http_status <= 299 and not conflict,
            "completion_event_observed": completed_observed, "terminal_state": terminal,
            "event_type_conflict": conflict,
            "response_id": _safe_identifier(final.get("id"), secret_values),
            "served_model": model, "accepted_effort": effort,
            "served_model_matches_request": model == expected_model if model is not None and expected_model is not None else None,
            "accepted_effort_matches_request": effort == expected_effort if effort is not None and expected_effort is not None else None,
            "usage": _safe_usage(final.get("usage")), "event_types": sorted(event_types)}


class ModelServer(BoundedThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = False

    def __init__(self, args, tokens, key, events):
        self.args, self.tokens, self.gpt_key, self.events = args, tokens, key, events
        self.role = "expert_model_controller"
        self.log_lock = threading.Lock()
        super().__init__(("127.0.0.1", 0), ModelHandler, deadline_seconds=1200,
                         max_request_threads=2)

    def record(self, item):
        with self.log_lock:
            self.events.write(json.dumps({"time": now(), **item}, allow_nan=False) + "\n")
            self.events.flush()


class ModelHandler(RestrictedHandler):
    def do_POST(self):
        self.close_connection = True
        role = next((r for r in ROLE_CONTRACT if self.path == ROLE_CONTRACT[r][2]), None)
        if role is None:
            self.reject(404, "path_not_allowed")
            return
        headers = self.headers.get_all("Authorization", [])
        if len(headers) != 1 or not hmac.compare_digest(headers[0].encode("utf-8"),
                                                       ("Bearer " + self.server.tokens[role]).encode("utf-8")):
            self.reject(401, "unauthorized")
            return
        deadline = Deadline(self.server.deadline_seconds)
        deadline.expires = self._request_started + self.server.deadline_seconds
        request_id = str(uuid.uuid4())
        started = time.monotonic()
        metadata = {"event": "model_request", "request_id": request_id, "role": role,
                    "task_checksum": self.server.args.task_checksum, "started_at": now(),
                    "requested_model": ROLE_CONTRACT[role][0], "requested_effort": ROLE_CONTRACT[role][1],
                    "completed": False, "outcome": "request_not_completed", "request_phase": "request_validation"}
        connection = response = None
        key = None
        raw_response = bytearray()
        content_type = "application/octet-stream"
        transport_complete = False
        known_secrets = [self.server.gpt_key, *self.server.tokens.values()]
        try:
            self.path = "/v1/responses"
            body = read_request(self, deadline)
            validate_role_body(role, body)
            request = strict_json(body)
            if request.get("store") is not None and request.get("store") is not False:
                raise RejectedRequest(403, "store_true_not_allowed")
            transforms = []
            if request.get("store") is None:
                request["store"] = False
                transforms.append("explicit_store_false")
            if role == "seed":
                if request.get("thinking") not in (None, {"type": "enabled"}):
                    raise RejectedRequest(403, "thinking_disabled_not_allowed")
                if request.get("thinking") is None:
                    request["thinking"] = {"type": "enabled"}
                    transforms.append("official_ark_thinking_enabled")
            try:
                sent = json.dumps(request, allow_nan=False, separators=(",", ":")).encode()
            except (ValueError, RecursionError):
                raise RejectedRequest(400, "invalid_json_numeric_value") from None
            metadata.update({"incoming_body_sha256": hashlib.sha256(body).hexdigest(),
                             "forwarded_body_sha256": hashlib.sha256(sent).hexdigest(),
                             "declared_adapter_transformations": transforms})
            credential_start = time.monotonic()
            metadata["request_phase"] = "credential_lookup"
            metadata["credential_lookup_started_at"] = now()
            try:
                key = self.server.gpt_key if role == "gpt" else read_profile_key(self.server.args, deadline)
                metadata["credential_lookup_outcome"] = "ok"
            except (CredentialLookupTimeout, DeadlineExpired, TimeoutError):
                metadata["credential_lookup_outcome"] = "timeout"
                raise
            except Exception:
                metadata["credential_lookup_outcome"] = "failed"
                raise
            finally:
                metadata["credential_lookup_seconds_excluded"] = time.monotonic() - credential_start
                metadata["credential_lookup_finished_at"] = now()
            known_secrets.append(key)
            metadata["request_phase"] = "upstream_connect"
            context = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
            if role == "gpt":
                connection = http.client.HTTPSConnection("127.0.0.1", 7892, context=context,
                                                        timeout=deadline.remaining())
                connection.set_tunnel("modcon.top", 443)
                path = "/v1/responses"
                metadata["provider_route"] = "authorized ModCon Responses through local proxy"
            else:
                connection = http.client.HTTPSConnection("ark.cn-beijing.volces.com", context=context,
                                                        timeout=deadline.remaining())
                path = "/api/v3/responses"
                metadata["provider_route"] = "official arkcli platform profile; authorized published-model Responses"
            upstream_headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
                                "Accept": "text/event-stream", "Accept-Encoding": "identity"}
            if role == "gpt":
                upstream_headers["x-openai-actor-authorization"] = "local-image-extension"
            metadata["upstream_started_at"] = now()
            self.server.record({**metadata, "event": "upstream_started"})
            connection.connect()
            self._upstream_socket = connection.sock
            deadline.apply(connection.sock)
            metadata["request_phase"] = "upstream_send"
            connection.request("POST", path, body=sent, headers=upstream_headers)
            deadline.apply(connection.sock)
            metadata["request_phase"] = "upstream_headers"
            response = connection.getresponse()
            self._upstream_socket = connection.sock or getattr(getattr(response.fp, "raw", None), "_sock", None)
            metadata["http_status"] = response.status
            metadata["upstream_http_status"] = response.status
            content_type = response.getheader("Content-Type") or "application/octet-stream"
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise RuntimeError("unexpected_upstream_encoding")
            if not 200 <= response.status <= 599:
                raise RuntimeError("unexpected_upstream_status")
            transfer = response.getheader("Transfer-Encoding")
            lengths = response.headers.get_all("Content-Length", [])
            if (transfer and transfer.lower() != "chunked") or (transfer and lengths):
                raise RuntimeError("invalid_upstream_framing")
            if lengths and (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()):
                raise RuntimeError("invalid_upstream_framing")
            deadline.apply(self.connection)
            self.send_response_only(response.status)
            self.send_header("Content-Type", content_type)
            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self._response_started = True
            self._wire_status = response.status
            redactor = StreamingRedactor(credential_patterns(known_secrets))
            metadata["request_phase"] = "upstream_stream"
            while True:
                deadline.apply(connection.sock or getattr(getattr(response.fp, "raw", None), "_sock", None))
                part = response.read1(65536)
                if not part:
                    if response.length not in (None, 0):
                        raise RuntimeError("truncated_upstream_response")
                    break
                if not raw_response:
                    metadata["first_response_byte_at"] = now()
                if len(raw_response) + len(part) > MAX_REQUEST_BYTES:
                    raise RuntimeError("response_size_limit")
                raw_response.extend(part)
                piece = redactor.feed(part)
                if piece:
                    deadline.apply(self.connection)
                    self.wfile.write(piece)
                    self.wfile.flush()
                    self._relayed_bytes += len(piece)
            tail = redactor.finish()
            metadata["request_phase"] = "downstream_flush"
            deadline.apply(self.connection)
            self.wfile.write(tail)
            self.wfile.flush()
            self._relayed_bytes += len(tail)
            transport_complete = True
            metadata["stream_redactions"] = redactor.redactions
            metadata["outcome"] = "provider_response_received"
        except RejectedRequest as e:
            metadata.update({"outcome": e.code, "http_status": e.status, "completed": False})
            self.reject(e.status, e.code)
        except (DeadlineExpired, CredentialLookupTimeout, TimeoutError) as error:
            metadata.update({"outcome": "provider_deadline_exceeded" if time.monotonic() >= deadline.expires
                             or isinstance(error, DeadlineExpired) else "credential_lookup_timeout"
                             if metadata["request_phase"] == "credential_lookup" else "provider_transport_timeout",
                             "failure_kind": "timeout", "http_status": self._wire_status or 504, "completed": False})
            self.reject(504, "provider_deadline_exceeded")
        except (OSError, ValueError, RuntimeError, http.client.HTTPException, subprocess.SubprocessError):
            expired = time.monotonic() >= deadline.expires
            metadata.update({"outcome": "provider_deadline_exceeded" if expired else "trusted_provider_transport_failed",
                             "failure_kind": "timeout" if expired else "credential_unavailable"
                             if metadata["request_phase"] == "credential_lookup" else "transport_failure",
                             "http_status": self._wire_status or (504 if expired else 502), "completed": False})
            self.reject(504 if expired else 502, "provider_deadline_exceeded" if expired else "provider_transport_failed")
        finally:
            if response is not None:
                try:
                    response.close()
                except OSError:
                    pass
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            metadata["transport_complete"] = transport_complete
            metadata["delivered_response_bytes"] = self._relayed_bytes
            if response is not None or raw_response:
                captured = StreamingRedactor(credential_patterns(known_secrets))
                safe_response = captured.feed(raw_response) + captured.finish(aborted=not transport_complete)
                summary = response_summary(safe_response, content_type,
                    expected_model=ROLE_CONTRACT[role][0], expected_effort=ROLE_CONTRACT[role][1],
                    secret_values=known_secrets, http_status=metadata.get("upstream_http_status", 0))
                if not transport_complete:
                    summary["completed"] = False
                metadata.update(summary)
                metadata["raw_response_sha256"] = hashlib.sha256(raw_response).hexdigest()
                metadata["redacted_response_sha256"] = hashlib.sha256(safe_response).hexdigest()
                metadata["captured_response_bytes"] = len(raw_response)
                metadata["response_capture_status"] = "complete" if transport_complete else "partial"
                try:
                    (Path(self.server.args.evidence_dir) / (request_id + ".response")).write_bytes(safe_response)
                except OSError:
                    metadata["response_capture_status"] = "write_failed"
                    metadata["completed"] = False
            metadata.update({"finished_at": now(), "elapsed_seconds": time.monotonic() - started})
            if "upstream_started_at" in metadata:
                metadata["upstream_finished_at"] = metadata["finished_at"]
            self.server.record(metadata)


def stop_process(p):
    if p is not None and p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-host", default="root@118.195.251.134")
    parser.add_argument("--profile-host", default="gpuhome-a100")
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--socket-root", required=True)
    parser.add_argument("--remote-port", type=int, required=True)
    parser.add_argument("--gpt-key-source", required=True)
    parser.add_argument("--task-checksum", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--gateway-identity", required=True)
    parser.add_argument("--gateway-lifecycle-log", required=True)
    parser.add_argument("--recovery-max-attempts", type=int, default=6)
    parser.add_argument("--recovery-max-outage-seconds", type=float, default=300)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{64}", args.task_checksum) is None:
        parser.error("invalid task checksum")
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
    tokens = {r: secrets.token_urlsafe(48) for r in ROLE_CONTRACT}
    halt = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: halt.set())
    server = recovery = ready = None
    owner = str(uuid.uuid4())
    try:
        key = read_authorized_gpt_key(args.gpt_key_source)
        with (evidence / "model-events.jsonl").open("x") as events:
            server = ModelServer(args, tokens, key, events)
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
            config = {"upstream_url": f"http://127.0.0.1:{args.remote_port}",
                      "gpt_token": tokens["gpt"], "seed_token": tokens["seed"],
                      "socket_root": args.socket_root}
            try:
                ready = launch_detached_ssh(args.control_host, args.gateway, config,
                    identity_path=args.gateway_identity, diagnostics_path=args.gateway_lifecycle_log,
                    owner_id=owner)
            finally:
                config.clear()
            expected_sha = hashlib.sha256((Path(__file__).parent / "model_socket_gateway.py").read_bytes()).hexdigest()
            if ready.get("event") != "ready" or ready.get("source_sha256") != expected_sha:
                raise RuntimeError("detached_gateway_source_mismatch")
            state = {"ready": True, "pid": os.getpid(), "started_at": now(),
                "task_checksum": args.task_checksum, "socket_root": args.socket_root,
                "reverse_forward_port": args.remote_port, "gateway_owner_id": owner,
                "gateway_pid": ready["pid"], "gateway_start_ticks": ready["start_ticks"],
                "gateway_identity": args.gateway_identity, "detached_gateway": True,
                "controller_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "gateway_sha256": expected_sha,
                "lifecycle_sha256": hashlib.sha256((Path(__file__).parent / "detached_gateway_lifecycle.py").read_bytes()).hexdigest(),
                "credentials": "expert RAM only; gateway receives independent role tokens once through stdin",
                "formal_research_time_started": False, "research_credit_seconds": 0}
            (evidence / "readiness.json").write_text(json.dumps(state, indent=2) + "\n")
            print(json.dumps(state), flush=True)
            while not halt.wait(0.25):
                recovery.tick()  # No model request/stream replay on transport reconnection.
    except (OSError, ValueError, RuntimeError, RejectedRequest, subprocess.SubprocessError):
        print("[model-controller] startup or service failed; no completed model claim", flush=True)
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

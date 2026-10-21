#!/usr/bin/env python3
"""Bounded HTTP transport helpers. No provider credentials or payload logging."""
from __future__ import annotations

import http.client
import http.server
import json
import os
import socket
import socketserver
import sys
import threading
import time

MAX_REQUEST_BYTES = 20 * 1024 * 1024
DEFAULT_DEADLINE_SECONDS = 1200.0
ROUTING_HEADERS = frozenset({"x-base-url", "x-api-base", "x-provider", "x-model-provider", "x-forwarded-host", "forwarded"})


class RejectedRequest(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code


class DeadlineExpired(Exception):
    pass


class TransportFailure(Exception):
    pass


class Deadline:
    def __init__(self, seconds: float):
        self.started = time.monotonic()
        self.expires = self.started + seconds

    def remaining(self) -> float:
        remaining = self.expires - time.monotonic()
        if remaining <= 0:
            raise DeadlineExpired
        return remaining

    def apply(self, sock: socket.socket | None) -> None:
        remaining = self.remaining()
        if sock is not None:
            sock.settimeout(remaining)


def safe_log(event: str, *, role: str, status: int | None = None,
             outcome: str | None = None, body_bytes: int | None = None) -> None:
    """Callers pass only fixed event/outcome codes, never exception text or input."""
    record = {"event": event, "role": role}
    for key, value in (("status", status), ("outcome", outcome), ("body_bytes", body_bytes)):
        if value is not None:
            record[key] = value
    try:
        print(json.dumps(record, separators=(",", ":")), file=sys.stderr, flush=True)
    except OSError:
        pass  # A closed supervisor log pipe must not dump a traceback/payload.


def process_identity() -> dict:
    result = {"pid": os.getpid(), "start_ticks": None}
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/stat", "r", encoding="ascii") as stream:
                # Fields after the final ')' begin at field 3; starttime is 22.
                result["start_ticks"] = int(stream.read().rsplit(") ", 1)[1].split()[19])
        except (OSError, IndexError, ValueError):
            result["start_ticks_unavailable"] = "proc_stat_unavailable"
    else:
        result["start_ticks_unavailable"] = "non_linux"
    return result


def strict_json(data: bytes) -> object:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("non_json_constant")

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError):
        raise RejectedRequest(400, "invalid_json") from None


def read_request(handler: http.server.BaseHTTPRequestHandler, deadline: Deadline) -> bytes:
    if handler.path != "/v1/responses":
        raise RejectedRequest(404, "path_not_allowed")
    if handler.headers.get("Transfer-Encoding") is not None:
        raise RejectedRequest(400, "request_transfer_encoding_not_allowed")
    lengths = handler.headers.get_all("Content-Length", [])
    if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
        raise RejectedRequest(400, "one_content_length_required")
    if len(lengths[0]) > 8:
        raise RejectedRequest(413, "request_too_large")
    length = int(lengths[0])
    if length > MAX_REQUEST_BYTES:
        raise RejectedRequest(413, "request_too_large")
    if (len(handler.headers.get_all("Content-Type", [])) != 1
            or handler.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json"):
        raise RejectedRequest(415, "json_content_type_required")
    if handler.headers.get("Content-Encoding", "identity").lower() != "identity":
        raise RejectedRequest(415, "request_content_encoding_not_allowed")
    for name in handler.headers.keys():
        name = name.lower()
        if name in ROUTING_HEADERS or name.startswith("x-upstream-"):
            raise RejectedRequest(403, "client_routing_not_allowed")
    parts = []
    unread = length
    while unread:
        deadline.apply(handler.connection)
        piece = handler.rfile.read1(min(65536, unread))
        if not piece:
            raise RejectedRequest(400, "truncated_request")
        parts.append(piece)
        unread -= len(piece)
    return b"".join(parts)


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str, *, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.socket_path)
        except BaseException:
            sock.close()
            raise
        self.sock = sock


def _response_socket(response, connection):
    if connection.sock is not None:
        return connection.sock
    raw = getattr(response.fp, "raw", None)
    return getattr(raw, "_sock", None)


def relay_response(handler, connection, path: str, body: bytes,
                   headers: dict[str, str], deadline: Deadline) -> tuple[int, int]:
    """Decode HTTP framing only; never decode, parse or manufacture SSE payloads."""
    response = None
    sent = 0
    try:
        connection.connect()
        handler._upstream_socket = connection.sock
        deadline.apply(connection.sock)
        connection.request("POST", path, body=body, headers=headers)
        deadline.apply(connection.sock)
        response = connection.getresponse()
        handler._upstream_socket = _response_socket(response, connection)
        if not 200 <= response.status <= 599:
            raise TransportFailure
        transfer = response.getheader("Transfer-Encoding")
        lengths = response.headers.get_all("Content-Length", [])
        if (transfer and transfer.lower() != "chunked") or (transfer and lengths):
            raise TransportFailure
        if lengths and (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()):
            raise TransportFailure
        deadline.apply(handler.connection)
        handler.send_response_only(response.status)
        handler.send_header("Content-Type", response.getheader("Content-Type") or "application/octet-stream")
        if response.getheader("Content-Encoding"):
            handler.send_header("Content-Encoding", response.getheader("Content-Encoding"))
        # Deliberately use connection-close framing after dechunking. A premature
        # upstream EOF must not leave a false Content-Length or fabricated event.
        handler.send_header("Connection", "close")
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler._response_started = True
        handler._wire_status = response.status
        while True:
            deadline.apply(_response_socket(response, connection))
            piece = response.read1(65536)
            if not piece:
                if response.length not in (None, 0):
                    raise TransportFailure
                break
            deadline.apply(handler.connection)
            handler.wfile.write(piece)
            handler.wfile.flush()
            sent += len(piece)
            handler._relayed_bytes = sent
        return response.status, sent
    finally:
        if response is not None:
            response.close()
        connection.close()


class RestrictedHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "RFStepsTransport"
    sys_version = ""

    def setup(self):
        # Bounds initial request-line/header reads before do_POST is reached.
        self.request.settimeout(self.server.deadline_seconds)
        super().setup()
        self._response_started = False
        self._upstream_socket = None
        self._wire_status = None
        self._relayed_bytes = 0

    def log_message(self, _format, *_args):
        pass

    def send_error(self, code, message=None, explain=None):
        # Base parser errors must not echo untrusted request text.
        self.reject(code, "http_parse_rejected")

    def reject(self, status: int, code: str):
        self.close_connection = True
        if self._response_started:
            return
        body = json.dumps({"error": {"code": code}}, separators=(",", ":")).encode()
        try:
            self.send_response_only(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            if getattr(self, "command", None) != "HEAD":
                self.wfile.write(body)
        except (OSError, ValueError):
            pass

    def handle_expect_100(self):
        self.reject(417, "expect_not_allowed")
        return False

    def not_allowed(self):
        self.reject(405, "method_not_allowed")

    do_GET = do_HEAD = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_CONNECT = not_allowed

    def do_POST(self):
        self.close_connection = True
        deadline = Deadline(self.server.deadline_seconds)
        # Include setup/header time in the absolute per-request deadline.
        deadline.expires = self._request_started + self.server.deadline_seconds
        status, count, outcome = None, 0, "transport_failure"
        try:
            body = read_request(self, deadline)
            connection, path, headers = self.route(body, deadline)
            status, count = relay_response(self, connection, path, body, headers, deadline)
            outcome = "transport_complete"
        except RejectedRequest as error:
            status, outcome = error.status, error.code
            self.reject(status, outcome)
        except (DeadlineExpired, TimeoutError):
            status, outcome = 504, "deadline_exceeded"
            self.reject(status, outcome)
        except (OSError, http.client.HTTPException, TransportFailure, ValueError):
            if time.monotonic() >= deadline.expires:
                status, outcome = 504, "deadline_exceeded"
            else:
                status, outcome = 502, "transport_failure"
            self.reject(status, outcome)
        finally:
            if self._response_started:
                status, count = self._wire_status, self._relayed_bytes
            safe_log("request_end", role=self.server.role, status=status,
                     outcome=outcome, body_bytes=count)

    def handle_one_request(self):
        self._request_started = time.monotonic()
        # socket timeouts alone are idle limits and reset during slow trickles.
        # An absolute watchdog also interrupts header parsing and chunk framing.
        def expire():
            for sock in (self._upstream_socket, self.connection):
                if sock is not None:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
        watchdog = threading.Timer(self.server.deadline_seconds, expire)
        watchdog.daemon = True
        watchdog.start()
        try:
            super().handle_one_request()
        except (OSError, ValueError):
            self.close_connection = True
        finally:
            watchdog.cancel()


class BoundedThreadingMixIn(socketserver.ThreadingMixIn):
    daemon_threads = True
    block_on_close = False

    def __init__(self, *args, deadline_seconds=DEFAULT_DEADLINE_SECONDS,
                 max_request_threads=8, **kwargs):
        self.deadline_seconds = float(deadline_seconds)
        self._request_slots = threading.BoundedSemaphore(max_request_threads)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            try:
                request.settimeout(1.0)
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()

    def handle_error(self, request, client_address):
        # Never dump request-associated tracebacks or inputs.
        safe_log("handler_error", role=self.role, outcome="internal_error")

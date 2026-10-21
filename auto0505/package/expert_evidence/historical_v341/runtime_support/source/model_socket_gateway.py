#!/usr/bin/env python3
"""Role-fixed UDS -> expert loopback HTTP. Read four-field RAM config from stdin."""
from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import select
import signal
import socketserver
import stat
import sys
import threading
import urllib.parse

from model_transport import (BoundedThreadingMixIn, DEFAULT_DEADLINE_SECONDS,
                             RejectedRequest, RestrictedHandler, process_identity, strict_json)

ROLE_CONTRACT = {
    "gpt": ("gpt-6.1-sol", "xhigh", "/model/gpt/responses"),
    "seed": ("doubao-seed-2-1-turbo-260628", "high", "/model/seed/responses"),
}
ROUTING_FIELDS = frozenset({"upstream_url", "base_url", "api_base", "api_base_url",
                            "endpoint", "url", "proxy_url", "provider", "model_provider"})


def parse_startup_config(data: bytes) -> dict:
    if len(data) > 65536:
        raise ValueError("startup_config_too_large")
    try:
        config = strict_json(data)
    except RejectedRequest:
        raise ValueError("invalid_startup_config") from None
    if not isinstance(config, dict) or set(config) != {"upstream_url", "gpt_token", "seed_token", "socket_root"}:
        raise ValueError("four_startup_fields_required")
    if not all(isinstance(value, str) for value in config.values()):
        raise ValueError("startup_strings_required")
    for name in ("gpt_token", "seed_token"):
        if not re.fullmatch(r"[A-Za-z0-9._~+/=-]{32,4096}", config[name]):
            raise ValueError("invalid_role_token")
    if config["gpt_token"] == config["seed_token"]:
        raise ValueError("distinct_role_tokens_required")
    parsed = urllib.parse.urlsplit(config["upstream_url"])
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
    except ValueError:
        raise ValueError("literal_loopback_upstream_required") from None
    if (parsed.scheme != "http" or not address.is_loopback or port is None or not 1 <= port <= 65535
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("literal_loopback_upstream_required")
    if not os.path.isabs(config["socket_root"]):
        raise ValueError("absolute_socket_root_required")
    config["upstream_host"], config["upstream_port"] = str(address), port
    return config


def validate_role_body(role: str, body: bytes) -> None:
    request = strict_json(body)
    if not isinstance(request, dict):
        raise RejectedRequest(400, "json_object_required")
    if ROUTING_FIELDS.intersection(request):
        raise RejectedRequest(403, "client_routing_not_allowed")
    model, effort, _path = ROLE_CONTRACT[role]
    if request.get("model") != model:
        raise RejectedRequest(403, "model_not_allowed")
    reasoning = request.get("reasoning")
    if not isinstance(reasoning, dict) or reasoning.get("effort") != effort:
        raise RejectedRequest(403, "effort_not_allowed")


class GatewayHandler(RestrictedHandler):
    def route(self, body, deadline):
        validate_role_body(self.server.role, body)
        connection = http.client.HTTPConnection(self.server.upstream_host, self.server.upstream_port,
                                                timeout=deadline.remaining())
        return connection, ROLE_CONTRACT[self.server.role][2], {
            "Content-Type": "application/json", "Accept": "text/event-stream",
            "Authorization": "Bearer " + self.server.role_token,
        }


class GatewayServer(BoundedThreadingMixIn, socketserver.UnixStreamServer):
    def __init__(self, socket_path: str, role: str, config: dict, *, deadline_seconds=DEFAULT_DEADLINE_SECONDS):
        if role not in ROLE_CONTRACT or len(os.fsencode(socket_path)) > 100:
            raise ValueError("invalid_socket_role_or_path")
        if os.path.lexists(socket_path):
            raise ValueError("existing_socket_path_refused")
        self.role = role
        self.role_token = config[role + "_token"]
        self.upstream_host = config["upstream_host"]
        self.upstream_port = config["upstream_port"]
        self._owned_socket_identity = None
        try:
            super().__init__(socket_path, GatewayHandler, deadline_seconds=deadline_seconds)
            inode = os.lstat(socket_path)
            self._owned_socket_identity = (inode.st_dev, inode.st_ino)
            os.chmod(socket_path, 0o600)
        except BaseException:
            self.server_close()
            raise

    def server_close(self):
        super().server_close()
        try:
            current = os.lstat(self.server_address)
            if stat.S_ISSOCK(current.st_mode) and (current.st_dev, current.st_ino) == self._owned_socket_identity:
                os.unlink(self.server_address)
        except (FileNotFoundError, AttributeError):
            pass


def create_gateways(config: dict, *, deadline_seconds=DEFAULT_DEADLINE_SECONDS) -> list[GatewayServer]:
    root = Path(config["socket_root"])
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise ValueError("safe_owned_socket_directory_required")
    servers = []
    try:
        for role in ROLE_CONTRACT:
            servers.append(GatewayServer(str(root / (role + ".sock")), role, config,
                                         deadline_seconds=deadline_seconds))
        return servers
    except BaseException:
        for server in servers:
            server.server_close()
        raise


def read_startup_stdin(stop: threading.Event) -> bytes:
    """Require EOF but remain responsive to cleanup signals during startup."""
    parts, length = [], 0
    while not stop.is_set():
        readable, _, _ = select.select([sys.stdin.buffer], [], [], 0.1)
        if not readable:
            continue
        piece = os.read(sys.stdin.fileno(), 65537 - length)
        if not piece:
            return b"".join(parts)
        parts.append(piece)
        length += len(piece)
        if length > 65536:
            raise ValueError("startup_config_too_large")
    raise InterruptedError


def serve(config, deadline_seconds, announce=None, *, detached=False):
    servers = []
    stop = threading.Event()
    for name in (("SIGINT", "SIGTERM") if detached else ("SIGINT", "SIGTERM", "SIGHUP")):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda _sig, _frame: stop.set())
    try:
        servers = create_gateways(config, deadline_seconds=deadline_seconds)
        for server in servers:
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
        ready = {"event": "ready", "service": "model_socket_gateway",
                 "roles": ["gpt", "seed"], **process_identity()}
        if announce is None:
            print(json.dumps(ready, separators=(",", ":")), flush=True)
        else:
            announce(ready)
        stop.wait()
        return 0
    except InterruptedError:
        return 0
    except (OSError, ValueError):
        print('{"event":"startup_failed","service":"model_socket_gateway"}', flush=True)
        return 1
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private draft RAM-only model gateway")
    parser.add_argument("--deadline-seconds", type=float, default=DEFAULT_DEADLINE_SECONDS)
    parser.add_argument("--detach", action="store_true")
    parser.add_argument("--identity-path")
    parser.add_argument("--lifecycle-log")
    parser.add_argument("--owner-id")
    args = parser.parse_args(argv)
    if not 0 < args.deadline_seconds <= 86400:
        parser.error("invalid deadline")
    try:
        config = parse_startup_config(read_startup_stdin(threading.Event()))
        if args.detach:
            if not all((args.identity_path, args.lifecycle_log, args.owner_id)):
                raise ValueError("detached metadata paths required")
            from detached_gateway_lifecycle import detach_and_run
            return detach_and_run(config,
                lambda c, a: serve(c, args.deadline_seconds, a, detached=True),
                source_path=__file__, identity_path=args.identity_path,
                diagnostics_path=args.lifecycle_log, owner_id=args.owner_id)
        return serve(config, args.deadline_seconds)
    except (OSError, ValueError, InterruptedError):
        print('{"event":"startup_failed","service":"model_socket_gateway"}', flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

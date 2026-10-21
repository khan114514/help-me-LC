#!/usr/bin/env python3
"""Agent loopback HTTP -> its sole mounted model UDS. No upstream credentials."""
from __future__ import annotations

import argparse
import http.server
import json
import os
import signal
import stat
import threading

from model_transport import (BoundedThreadingMixIn, DEFAULT_DEADLINE_SECONDS,
                             RestrictedHandler, UnixHTTPConnection, process_identity)


class BridgeHandler(RestrictedHandler):
    def route(self, body, deadline):
        return (UnixHTTPConnection(self.server.socket_path, timeout=deadline.remaining()),
                "/v1/responses", {"Content-Type": "application/json", "Accept": "text/event-stream"})


class BridgeServer(BoundedThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True

    def __init__(self, socket_path, port, *, deadline_seconds=DEFAULT_DEADLINE_SECONDS):
        if not os.path.isabs(socket_path) or not stat.S_ISSOCK(os.lstat(socket_path).st_mode):
            raise ValueError("socket_required")
        self.socket_path = socket_path
        self.role = os.path.basename(socket_path).removesuffix(".sock")
        if self.role not in ("gpt", "seed"):
            self.role = "bridge"
        super().__init__(("127.0.0.1", port), BridgeHandler, deadline_seconds=deadline_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--deadline-seconds", type=float, default=DEFAULT_DEADLINE_SECONDS)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 0 < args.deadline_seconds <= 86400:
        parser.error("invalid port or deadline")
    server = None
    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda _sig, _frame: stop.set())
    try:
        server = BridgeServer(args.socket, args.port, deadline_seconds=args.deadline_seconds)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        print(json.dumps({"event": "ready", "service": "model_http_bridge",
                          "bind": "127.0.0.1", "port": server.server_port,
                          **process_identity()}, separators=(",", ":")), flush=True)
        stop.wait()
        return 0
    except (OSError, ValueError):
        print('{"event":"startup_failed","service":"model_http_bridge"}', flush=True)
        return 1
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())

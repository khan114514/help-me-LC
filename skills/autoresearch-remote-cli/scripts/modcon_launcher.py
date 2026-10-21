#!/usr/bin/env python3
"""Start remote Codex with a transient ModCon key and the forwarded proxy."""

import getpass
import os
import socket
import sys


def main():
    env = os.environ.copy()
    if not env.get("AUTORESEARCH_CUSTOM_API_KEY"):
        if not sys.stdin.isatty():
            print("Missing runtime ModCon key; run codex-modcon in an interactive terminal.", file=sys.stderr)
            return 1
        key = getpass.getpass("ModCon API key (hidden, this process only): ")
        if not key.strip():
            print("ModCon key is empty.", file=sys.stderr)
            return 1
        env["AUTORESEARCH_CUSTOM_API_KEY"] = key.strip()
    try:
        with socket.create_connection(("127.0.0.1", 17892), timeout=2):
            pass
    except OSError:
        print("Remote proxy 127.0.0.1:17892 is unavailable. Reconnect the authorized local SSH proxy tunnel.",
              file=sys.stderr)
        return 1
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env[name] = "http://127.0.0.1:17892"
    os.execve("/opt/conda/bin/codex", ["/opt/conda/bin/codex", *sys.argv[1:]], env)


if __name__ == "__main__":
    raise SystemExit(main())

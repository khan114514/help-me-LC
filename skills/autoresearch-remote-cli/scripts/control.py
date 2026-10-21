#!/usr/bin/env python3
"""Forward an in-memory job to the CLIs running on an SSH server."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


def read_request():
    if not sys.stdin.isatty():
        return json.load(sys.stdin)
    import termios

    old = termios.tcgetattr(sys.stdin)
    quiet = termios.tcgetattr(sys.stdin)
    quiet[3] &= ~(termios.ECHO | termios.ICANON)
    quiet[6][termios.VMIN] = 1
    quiet[6][termios.VTIME] = 0
    termios.tcsetattr(sys.stdin, termios.TCSANOW, quiet)
    try:
        print("REQUEST_INPUT_READY", file=sys.stderr, flush=True)
        return json.loads(sys.stdin.readline())
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSANOW, old)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["doctor", "ark", "ark-profile", "codex-seed", "codex-seed-profile", "codex-openai", "codex-custom"])
    parser.add_argument("--host", default="gpuhome-a100")
    parser.add_argument("--control-path")
    parser.add_argument("--worker", default=('' + ('/' + 'root/') + 'rivermind-data/autoresearch_tools/remote_worker.py'))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--request-stdin", action="store_true")
    group.add_argument("--request-file", type=Path)
    args = parser.parse_args()
    try:
        request = read_request() if args.request_stdin else {}
        if args.request_file:
            request = json.loads(args.request_file.read_text())
            if "credentials" in request:
                raise ValueError("Credentials are forbidden in request files; use stdin or transient environment.")
        if not isinstance(request, dict):
            raise ValueError("Request must be a JSON object.")
        request["operation"] = args.operation
        credentials = request.setdefault("credentials", {})
        if not isinstance(credentials, dict):
            raise ValueError("credentials must be an object.")
        for name, env in [("ark_ak", "VOLC_ACCESSKEY"), ("ark_sk", "VOLC_SECRETKEY"),
                          ("openai_api_key", "OPENAI_API_KEY"),
                          ("custom_api_key", "AUTORESEARCH_CUSTOM_API_KEY")]:
            if name not in credentials and os.environ.get(env):
                credentials[name] = os.environ[env]
        command = ["ssh", "-o", "ConnectTimeout=15"]
        if args.control_path:
            command += ["-o", "ControlPath=" + args.control_path]
        command += [args.host, shlex.join(["python", args.worker])]
        result = subprocess.run(command, input=json.dumps(request), text=True,
                                capture_output=True, timeout=550)
        stdout, stderr = result.stdout, result.stderr
        for value in credentials.values():
            if isinstance(value, str) and value:
                stdout, stderr = stdout.replace(value, "[REDACTED]"), stderr.replace(value, "[REDACTED]")
        sys.stdout.write(stdout)
        sys.stderr.write(stderr)
        return result.returncode
    except (ValueError, OSError, subprocess.TimeoutExpired):
        print(json.dumps({"status": "transport_error", "message": "Invalid request, SSH failure, or transport timeout; credentials suppressed."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

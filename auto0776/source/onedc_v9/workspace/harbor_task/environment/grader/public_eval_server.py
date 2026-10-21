#!/usr/bin/env python3
"""Root service accepts one operation, never caller commands, paths or scores."""
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

REQUESTS = Path('/workspace/eval-requests')
RECEIPTS = Path('/workspace/public-results')
GRADER = Path('/opt/onedc/grader')
PATTERN = re.compile(r'([0-9a-f]{32})\.request\.json')


def atomic_result(path, value):
    pending = path.with_suffix('.pending')
    descriptor = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as f:
        json.dump(value, f)
        f.flush()
        os.fsync(f.fileno())
    pending.chmod(0o444)
    pending.rename(path)


def read_request(path, identifier):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 25000 or info.st_nlink != 1 or info.st_size > 1024:
            raise ValueError('Invalid public request metadata')
        request = json.loads(f.read(1025))
    if request != {'op': 'public_evaluate', 'request_id': identifier}:
        raise ValueError('Unsupported public request')


def remove_request(path):
    try:
        path.unlink(missing_ok=True)
    except (IsADirectoryError, PermissionError):
        pass


def main():
    if os.getuid() != 0 or len(sys.argv) != 1:
        raise SystemExit('The image entrypoint must start the trusted public service')
    for directory in [REQUESTS, RECEIPTS]:
        if directory.is_symlink() or directory.stat().st_uid != 0:
            raise SystemExit('Trusted public transport directory ownership mismatch')
    atomic_result(RECEIPTS / 'service-ready.json', {'service': 'onedc-public-v1', 'pid': os.getpid()})
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
           'LC_ALL': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'}
    for key in ['LD_LIBRARY_PATH', 'CUDA_VISIBLE_DEVICES', 'NVIDIA_VISIBLE_DEVICES', 'NVIDIA_DRIVER_CAPABILITIES']:
        if key in os.environ:
            env[key] = os.environ[key]
    while True:
        for path in sorted(REQUESTS.glob('*.request.json'))[:100]:
            match = PATTERN.fullmatch(path.name)
            if not match:
                continue
            identifier = match[1]
            response = RECEIPTS / (identifier + '.response.json')
            if response.exists():
                remove_request(path)
                continue
            started = time.monotonic()
            try:
                read_request(path, identifier)
                result = subprocess.run([sys.executable, str(GRADER / 'public_eval.py')],
                                        cwd=str(GRADER), env=env, stdin=subprocess.DEVNULL,
                                        capture_output=True, text=True, timeout=7300)
                if len(result.stdout) > 16384:
                    raise RuntimeError('Trusted public helper output exceeded budget')
                summary = json.loads(result.stdout)
                if not isinstance(summary, dict) or summary.get('exit_code') != result.returncode:
                    raise RuntimeError('Trusted public helper result mismatch')
            except Exception as exc:
                # No request body, exception message or helper stderr is exposed.
                summary = {'exit_code': 3, 'status': 'evaluation_service_error',
                           'valid': False, 'score': None, 'failure_class': type(exc).__name__}
            summary.update(request_id=identifier, service_elapsed_sec=time.monotonic() - started)
            atomic_result(response, summary)
            remove_request(path)
        time.sleep(.25)


if __name__ == '__main__':
    main()

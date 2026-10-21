#!/usr/bin/env python3
"""Unprivileged, file-only client for the fixed public evaluation service."""
import json
import os
from pathlib import Path
import sys
import time
import uuid


def main():
    if os.getuid() != 25000 or len(sys.argv) != 1:
        raise SystemExit("Run /workspace/evaluate.sh as the agent without arguments")
    identifier = uuid.uuid4().hex
    requests = Path('/workspace/eval-requests')
    receipts = Path('/workspace/public-results')
    if requests.is_symlink() or receipts.is_symlink():
        raise SystemExit("Public evaluation transport was altered")
    request = requests / (identifier + '.request.json')
    pending = requests / (identifier + '.pending')
    with pending.open('x') as f:
        os.fchmod(f.fileno(), 0o644)
        json.dump({'op': 'public_evaluate', 'request_id': identifier}, f)
        f.flush()
        os.fsync(f.fileno())
    pending.rename(request)
    response = receipts / (identifier + '.response.json')
    start = time.monotonic()
    print('Public evaluation requested; waiting for trusted result ' + identifier, flush=True)
    while time.monotonic() - start < 7200:
        if response.is_file() and not response.is_symlink():
            result = json.loads(response.read_text())
            if result.get('request_id') != identifier:
                raise SystemExit('Trusted public response identity mismatch')
            print(json.dumps(result), flush=True)
            return int(result['exit_code'])
        time.sleep(.5)
    print(json.dumps({'status': 'transport_timeout', 'score': None, 'valid': False,
                      'request_id': identifier}), flush=True)
    return 124


if __name__ == '__main__':
    raise SystemExit(main())

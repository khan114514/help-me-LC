"""Keep the trusted GPU lease until the entire evaluator process has exited."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import stat
import subprocess
import time


def live_group(group):
    members = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == group and fields[0] not in ('Z', 'X'):
                members.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return members


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--timeout', type=float, default=3600)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == '--':
        command = command[1:]
    if os.geteuid() != 0 or not command or not 0 < args.timeout <= 3600:
        raise RuntimeError('Trusted lease supervisor requires root and a bounded command')
    path = Path(os.environ.get('ONEDC_LOCK', '/opt/onedc/locks/gpu.lock'))
    descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise RuntimeError('GPU lease must be a private root-owned regular file')
    process = None

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        started = time.monotonic()
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - started >= 3600:
                    return 124
                time.sleep(.1)
        queue = time.monotonic() - started
        if os.pread(descriptor, 1024, 0):
            raise RuntimeError('GPU lease is blocked after an unresolved evaluator cleanup')
        env = dict(os.environ)
        env['ONEDC_LEASE_FD'] = str(descriptor)
        env['ONEDC_LEASE_QUEUE_SEC'] = repr(queue)
        process = subprocess.Popen(command, env=env, pass_fds=(descriptor,), start_new_session=True)
        deadline = time.monotonic() + args.timeout
        while True:
            # Leave the direct child unreaped until group cleanup. This reserves
            # its PID/PGID and prevents signaling a subsequently reused PID.
            result = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if result is not None:
                return result.si_status if result.si_code == os.CLD_EXITED else 128 + result.si_status
            if time.monotonic() >= deadline:
                return 124
            time.sleep(.05)
    finally:
        if process is not None:
            # KILL covers any still-live worker in the evaluator's process group,
            # including one whose parent has already failed. Root alone has this
            # capability; the candidate UID and the agent UID have no capabilities.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 15
            while live_group(process.pid):
                if time.monotonic() >= deadline:
                    os.pwrite(descriptor, b'blocked: evaluator process group did not terminate\n', 0)
                    os.fsync(descriptor)
                    raise RuntimeError('Evaluator cleanup failed; the shared GPU lease is now blocked')
                time.sleep(.05)
            process.wait(timeout=15)
        os.close(descriptor)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

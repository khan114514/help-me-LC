"""Detached, locked job wrapper with durable process observations."""
import argparse
import fcntl
import os
import signal
import subprocess
import time
from pathlib import Path
from common import clean_env, read, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True, type=Path)
    args = parser.parse_args()
    job = args.job.resolve()
    lock = (job / 'worker.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    if (job / 'exit.json').exists():
        return 0
    spec = read(job / 'execution.json')
    started = time.time()
    write(job / 'started.json', {'pid': os.getpid(), 'epoch': started, 'job_id': job.name})
    try:
        with (job / 'stdout.log').open('wb') as out, (job / 'stderr.log').open('wb') as err:
            proc = subprocess.Popen(spec['argv'], cwd=job, env=clean_env(), stdout=out,
                                    stderr=err, stdin=subprocess.DEVNULL, start_new_session=True)
            write(job / 'child.json', {'pid': proc.pid, 'epoch': time.time()})
            timed_out = False
            while proc.poll() is None:
                write(job / 'heartbeat.json', {'pid': os.getpid(), 'child_pid': proc.pid,
                                              'epoch': time.time()})
                if time.time() - started > spec['timeout_seconds']:
                    timed_out = True
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                    break
                time.sleep(0.2)
            code = proc.wait()
        result = {'exit_code': code, 'started_epoch': started, 'ended_epoch': time.time(),
                  'timed_out': timed_out}
    except Exception as exc:
        result = {'exit_code': -1, 'started_epoch': started, 'ended_epoch': time.time(),
                  'timed_out': False, 'error_type': type(exc).__name__}
    write(job / 'exit.json', result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

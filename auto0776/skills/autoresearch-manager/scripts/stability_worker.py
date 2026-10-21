#!/usr/bin/env python3
"""Observe a real dedicated container continuously; no synthetic uptime credit."""
import argparse
import json
import subprocess
import time
from pathlib import Path
from common import clean_env, public_inspect, read, receipt, write


def inspect(container):
    return json.loads(subprocess.check_output(['docker', 'inspect', container], env=clean_env()))[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', required=True, type=Path)
    p.add_argument('--container', required=True)
    p.add_argument('--interval', type=float, default=30)
    p.add_argument('--health-argv-json')
    args = p.parse_args()
    if not 0 < args.interval <= 60:
        p.error('interval must be in (0,60]')
    request = read(args.request)
    job = args.request.resolve().parent
    health = json.loads(args.health_argv_json) if args.health_argv_json else None
    if health is not None and (not isinstance(health, list) or not health or not all(isinstance(x, str) for x in health)):
        p.error('health argv must be a nonempty string array')
    duration = request['contract'].get('stability_seconds', 43200)
    first = inspect(args.container)
    container_id = first['Id']
    write(job / 'initial-inspect.json', public_inspect(first))
    observation = {'status': 'RUNNING', 'container_id': container_id, 'interval_seconds': args.interval,
                   'contract_sha256': request['contract_sha256'], 'samples': []}
    start = time.monotonic()
    while True:
        row = inspect(container_id)
        state = row['State']
        healthy = state.get('Health', {}).get('Status') == 'healthy'
        if health:
            healthy = subprocess.run(health, env=clean_env(), stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, timeout=min(60, args.interval)).returncode == 0
        sample = {'epoch': time.time(), 'container_id': row['Id'], 'started_at': state['StartedAt'],
                  'restart_count': row['RestartCount'], 'running': state['Running'], 'healthy': healthy}
        observation['samples'].append(sample)
        elapsed = time.monotonic() - start
        if not healthy or not sample['running'] or sample['restart_count'] != 0 or sample['started_at'] != first['State']['StartedAt']:
            observation['status'] = 'FAIL'
        elif elapsed >= duration:
            observation['status'] = 'PASS'
        write(job / 'observation.json', observation)
        if observation['status'] != 'RUNNING':
            receipt(request, observation['status'], ['initial-inspect.json', 'observation.json'],
                    {'observation': 'observation.json'})
            return 0
        time.sleep(min(args.interval, max(0.01, duration - elapsed)))


if __name__ == '__main__':
    raise SystemExit(main())

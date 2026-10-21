#!/usr/bin/env python3
"""Independent QA in a fresh credential-free container with exactly one ZIP."""
import argparse
import json
import shutil
import signal
import subprocess
from pathlib import Path
from common import clean_env, digest, public_inspect, read, receipt, write

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', required=True, type=Path)
    p.add_argument('--image', required=True)
    p.add_argument('--network', required=True)
    p.add_argument('--gateway-url', required=True)
    p.add_argument('--reasoning-effort', default='high')
    args = p.parse_args()
    request = read(args.request)
    if request['stage'] not in ('qa_a', 'qa_b'):
        p.error('only independent QA stages are allowed')
    job = args.request.resolve().parent
    artifact = request['artifact']
    if digest(artifact['path']) != artifact['sha256']:
        raise ValueError('immutable ZIP changed')
    input_dir, output_dir = job / 'input', job / 'out'
    input_dir.mkdir()
    output_dir.mkdir()
    shutil.copyfile(artifact['path'], input_dir / 'submission.zip')
    shutil.copyfile(HERE / 'qa_entry.py', output_dir / 'entry.py')
    write(output_dir / 'reviewer.json', {'reviewer': request['reviewer'], 'session_id': request['session_id'],
          'reasoning_effort': args.reasoning_effort, 'gateway_url': args.gateway_url})
    skills = HERE.parent / 'assets/qa-skills'
    name = 'ar-qa-' + request['session_id']
    command = ['docker', 'create', '--name', name, '--network', args.network,
               '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--tmpfs', '/tmp:rw,nosuid,nodev,size=2g',
               '--mount', f'type=bind,source={input_dir},target=/input,readonly',
               '--mount', f'type=bind,source={skills},target=/skills,readonly',
               '--mount', f'type=bind,source={output_dir},target=/out',
               args.image, 'python3', '/out/entry.py']
    created = subprocess.run(command, env=clean_env(), capture_output=True, check=True)
    container_id = created.stdout.decode().strip()
    def stop_owned_container(signum, frame):
        # Killing the docker CLI alone would leave its daemon-owned model process
        # running. Stop only this job's recorded container on wrapper timeout.
        subprocess.run(['docker', 'kill', container_id], env=clean_env(), capture_output=True, timeout=5)
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, stop_owned_container)
    signal.signal(signal.SIGINT, stop_owned_container)
    inspect = json.loads(subprocess.check_output(['docker', 'inspect', container_id], env=clean_env()))[0]
    # Persist real launch config; no credentials were supplied in env or argv.
    write(job / 'container-inspect.json', public_inspect(inspect))
    write(job / 'launch.json', {'session_id': request['session_id'], 'fresh_session': True,
          'artifact_sha256': artifact['sha256'], 'reviewer': request['reviewer'],
          'container_id': container_id, 'image_id': inspect['Image'], 'network': args.network,
          'gateway_url': args.gateway_url, 'argv': command})
    names = [x.split('=', 1)[0].upper() for x in inspect.get('Config', {}).get('Env', [])]
    if any(any(word in name for word in ('API_KEY', 'ACCESS_KEY', 'SECRET', 'TOKEN', 'CREDENTIAL')) for name in names):
        receipt(request, 'NEEDS_INPUT', ['launch.json', 'container-inspect.json'],
                {'reason': 'QA image contains credential environment fields; use a clean image.'})
        subprocess.run(['docker', 'rm', container_id], env=clean_env(), capture_output=True)
        return 0
    with (job / 'container.log').open('wb') as log:
        result = subprocess.run(['docker', 'start', '-a', container_id], env=clean_env(), stdout=log,
                                stderr=subprocess.STDOUT)
    final = json.loads(subprocess.check_output(['docker', 'inspect', container_id], env=clean_env()))[0]
    write(job / 'container-final.json', public_inspect(final))
    report = output_dir / 'report/report.json'
    runtime_path = output_dir / 'runtime.json'
    runtime = read(runtime_path) if runtime_path.exists() else {}
    if result.returncode != 0 or final['State']['ExitCode'] != 0 or not report.exists() or len(runtime.get('thread_ids', [])) != 1:
        receipt(request, 'RETRY', ['launch.json'], {'reason': 'QA container/model did not produce one completed fresh session.'})
        return 0
    launch = read(job / 'launch.json')
    launch['codex_thread_id'] = runtime['thread_ids'][0]
    write(job / 'launch.json', launch)
    evidence = ['launch.json', 'container-inspect.json', 'container-final.json',
                'out/runtime.json', 'out/events.jsonl', 'out/report/report.json']
    # Adapter process succeeded even when the honest QA report decision is FAIL.
    receipt(request, 'PASS', evidence, {'report': 'out/report/report.json', 'session_evidence': 'launch.json'})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

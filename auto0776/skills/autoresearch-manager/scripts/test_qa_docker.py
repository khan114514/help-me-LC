"""Opt-in real Docker isolation test with a fake Codex executable (no model calls)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import zipfile
from pathlib import Path
from common import digest, object_digest, read, write

HERE = Path(__file__).resolve().parent

MOCK_CODEX = r'''#!/usr/local/bin/python3
import json,os,sys,uuid
from pathlib import Path
assert sorted(p.name for p in Path('/input').iterdir()) == ['submission.zip']
assert not any(k.endswith('_API_KEY') or k.endswith('_TOKEN') for k in os.environ)
settings=json.loads(Path('/out/reviewer.json').read_text())
if settings['reviewer']['model']=='SIMULATED-WAIT':
    __import__('time').sleep(300)
sid=str(uuid.uuid4())
print(json.dumps({'type':'thread.started','thread_id':sid}),flush=True)
report={'source':{'kind':'zip','sha256':__import__('hashlib').sha256(Path('/input/submission.zip').read_bytes()).hexdigest()},
        'summary':{'decision':'PASS'},
        'qa_run':{'skill':{'name':'autoresearch-qa-skills','version':'0.3.4'},'input_kind':'zip',
                  'clean_context':True,'reviewer':{**settings['reviewer'],'session_id':settings['session_id']}},
        'checks':[{'id':f'QA{i:02}','status':'pass'} for i in range(1,22)],
        'content_gates':{'checks':[{'id':f'G{i:02}','status':'pass'} for i in range(1,4)]},
        'harbor':{'checks':[{'id':f'H{i:02}','status':'pass'} for i in range(1,7)]},
        'test_only':'SIMULATED MODEL OUTPUT; NOT FORMAL QA'}
report['qa_run']['artifact_sha256']=report['source']['sha256']
Path('/out/report').mkdir()
Path('/out/report/report.json').write_text(json.dumps(report))
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':0,'output_tokens':0}}),flush=True)
'''


@unittest.skipUnless(os.environ.get('AUTORESEARCH_MANAGER_DOCKER_TEST') == '1', 'opt-in actual Docker test')
class DockerIsolationTests(unittest.TestCase):
    def test_two_fresh_containers_only_mount_zip_skills_and_own_output(self):
        with tempfile.TemporaryDirectory(prefix='ar-manager-docker-') as temporary:
            root = Path(temporary)
            (root / 'codex').write_text(MOCK_CODEX)
            (root / 'Dockerfile').write_text('FROM python:3.12-slim\nCOPY codex /usr/local/bin/codex\nRUN chmod 755 /usr/local/bin/codex\n')
            image = 'ar-manager-test-only:' + uuid.uuid4().hex
            subprocess.run(['docker', 'build', '--network', 'none', '-t', image, str(root)],
                           check=True, capture_output=True)
            containers = []
            try:
                archive = root / 'input.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr('TEST-ONLY.txt', 'Not a formal research task.')
                launches = []
                for lane in ('a', 'b'):
                    job = root / lane
                    job.mkdir()
                    session = uuid.uuid4().hex
                    request = {'job_id': session, 'session_id': session, 'stage': 'qa_' + lane,
                               'revision': 1, 'contract_sha256': object_digest({'test': True}),
                               'reviewer': {'provider': 'SIMULATED', 'model': 'SIMULATED-' + lane, 'version': 'test'},
                               'artifact': {'path': str(archive), 'sha256': digest(archive), 'revision': 1},
                               'receipt_path': str(job / 'receipt.json')}
                    write(job / 'request.json', request)
                    result = subprocess.run([sys.executable, str(HERE / 'qa_container.py'), '--request', str(job / 'request.json'),
                             '--image', image, '--network', 'none', '--gateway-url', 'http://no-model-provider.invalid/v1'],
                             capture_output=True)
                    containers.append('ar-qa-' + session)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                    self.assertEqual(read(job / 'receipt.json')['status'], 'PASS')
                    inspect = read(job / 'container-inspect.json')
                    self.assertEqual({m['Destination'] for m in inspect['Mounts']}, {'/input', '/skills', '/out'})
                    self.assertTrue(inspect['HostConfig']['ReadonlyRootfs'])
                    self.assertEqual(inspect['HostConfig']['NetworkMode'], 'none')
                    self.assertTrue(all(not m['RW'] for m in inspect['Mounts'] if m['Destination'] in ('/input', '/skills')))
                    self.assertTrue(all(str(root) != m['Source'] for m in inspect['Mounts']))
                    launches.append(read(job / 'launch.json'))
                self.assertNotEqual(launches[0]['container_id'], launches[1]['container_id'])
                self.assertNotEqual(launches[0]['codex_thread_id'], launches[1]['codex_thread_id'])
                self.assertEqual(launches[0]['artifact_sha256'], launches[1]['artifact_sha256'])
                # A detached Docker container must also stop when its owned driver
                # is terminated; stopping only `docker start -a` would orphan it.
                job = root / 'timeout'
                job.mkdir()
                session = uuid.uuid4().hex
                request = {'job_id': session, 'session_id': session, 'stage': 'qa_a', 'revision': 1,
                           'contract_sha256': object_digest({'test': True}),
                           'reviewer': {'provider': 'SIMULATED', 'model': 'SIMULATED-WAIT', 'version': 'test'},
                           'artifact': {'path': str(archive), 'sha256': digest(archive), 'revision': 1},
                           'receipt_path': str(job / 'receipt.json')}
                write(job / 'request.json', request)
                containers.append('ar-qa-' + session)
                proc = subprocess.Popen([sys.executable, str(HERE / 'qa_container.py'), '--request', str(job / 'request.json'),
                        '--image', image, '--network', 'none', '--gateway-url', 'http://no-model-provider.invalid/v1'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    end = time.monotonic() + 10
                    while not (job / 'launch.json').exists() and time.monotonic() < end:
                        time.sleep(0.05)
                    self.assertTrue((job / 'launch.json').exists())
                    container_id = read(job / 'launch.json')['container_id']
                    running = False
                    while time.monotonic() < end:
                        row = json.loads(subprocess.check_output(['docker', 'inspect', container_id]))[0]
                        running = row['State']['Running']
                        if running:
                            break
                        time.sleep(0.05)
                    self.assertTrue(running)
                    proc.terminate()
                    proc.wait(timeout=10)
                    row = json.loads(subprocess.check_output(['docker', 'inspect', container_id]))[0]
                    self.assertFalse(row['State']['Running'])
                finally:
                    if proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=10)
            finally:
                for container in containers:
                    subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
                subprocess.run(['docker', 'image', 'rm', image], capture_output=True)


if __name__ == '__main__':
    unittest.main()

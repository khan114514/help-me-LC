"""TEST ONLY: simulated research/QA outputs, never formal acceptance evidence."""
import argparse
import json
import time
import zipfile
from pathlib import Path
from common import digest, read, receipt, write


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--request', required=True, type=Path)
    p.add_argument('--delay', type=float, default=0.02)
    args = p.parse_args()
    request = read(args.request)
    job, stage = args.request.parent, request['stage']
    start = time.time()
    time.sleep(args.delay)
    write(job / 'simulated.json', {'warning': 'SIMULATED UNIT TEST; NOT RESEARCH EVIDENCE', 'stage': stage})
    evidence, details = ['simulated.json'], {}
    if stage.startswith('dual_'):
        end = time.time()
        write(job / 'duration.json', {'effective_seconds': end - start,
              'intervals': [{'start_epoch': start, 'end_epoch': end, 'kind': 'research'}]})
        evidence += ['duration.json']
        details = {'effective_seconds': end - start, 'duration_evidence': 'duration.json'}
    elif stage in ('nop', 'preflight_nop'):
        kinds = {'config': 'config.json', 'result': 'result.json', 'reward': 'reward.txt', 'log': 'trial.log'}
        for path in kinds.values():
            (job / path).write_text('SIMULATED TEST\n')
        evidence += list(kinds.values())
        details = {'trial_evidence': kinds}
    elif stage == 'finalize':
        validations = {}
        for lane in ('a', 'b'):
            row = {'status': 'PASS', 'method_sha256': lane * 64,
                   'contract_sha256': request['contract_sha256']}
            write(job / (lane + '.json'), row)
            validations[lane] = {**row, 'evidence': lane + '.json'}
            evidence.append(lane + '.json')
        details = {'final_validations': validations}
    elif stage == 'stability':
        samples = []
        for _ in range(3):
            samples.append({'epoch': time.time(), 'container_id': 'SIMULATED', 'started_at': 'SIMULATED',
                            'restart_count': 0, 'running': True, 'healthy': True})
            time.sleep(0.02)
        write(job / 'observation.json', {'status': 'PASS', 'container_id': 'SIMULATED',
              'interval_seconds': 0.02, 'samples': samples})
        evidence.append('observation.json')
        details = {'observation': 'observation.json'}
    elif stage == 'package':
        with zipfile.ZipFile(job / 'submission.zip', 'w') as z:
            z.writestr('TEST-ONLY.txt', 'Simulated framework test, not a research submission.')
            z.writestr('revision.txt', str(request['revision']))
        evidence.append('submission.zip')
        details = {'artifact': 'submission.zip'}
    elif stage.startswith('qa_'):
        failing = request['revision'] == 1 and stage == 'qa_a'
        report = {'source': {'kind': 'zip', 'sha256': request['artifact']['sha256']},
                  'summary': {'decision': 'NOT READY' if failing else 'PASS'},
                  'qa_run': {'skill': {'name': 'autoresearch-qa-skills', 'version': '0.3.4'},
                  'artifact_sha256': request['artifact']['sha256'], 'input_kind': 'zip', 'clean_context': True,
                  'reviewer': {**request['reviewer'], 'session_id': request['session_id']}},
                  'checks': [{'id': f'QA{i:02}', 'status': 'fail' if failing and i == 1 else 'pass'} for i in range(1, 22)],
                  'content_gates': {'checks': [{'id': f'G{i:02}', 'status': 'pass'} for i in range(1, 4)]},
                  'harbor': {'checks': [{'id': f'H{i:02}', 'status': 'pass'} for i in range(1, 7)]}}
        write(job / 'report.json', report)
        write(job / 'launch.json', {'session_id': request['session_id'], 'fresh_session': True,
              'artifact_sha256': request['artifact']['sha256'], 'reviewer': request['reviewer']})
        evidence += ['report.json', 'launch.json']
        details = {'report': 'report.json', 'session_evidence': 'launch.json'}
    elif stage == 'repair':
        Path(request['task_root'], 'fix.txt').write_text('Simulated repair for integration test.\n')
    receipt(request, 'PASS', evidence, details)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

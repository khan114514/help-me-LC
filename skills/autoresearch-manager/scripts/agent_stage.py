#!/usr/bin/env python3
"""Fresh expert-side Codex turn; never used as the isolated QA runner."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from common import clean_env, read, write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', required=True, type=Path)
    p.add_argument('--model', required=True)
    p.add_argument('--gateway-url')
    p.add_argument('--reasoning-effort', default='xhigh')
    args = p.parse_args()
    request = read(args.request)
    if request['stage'].startswith('qa_') or request['stage'].startswith('dual_'):
        p.error('use isolated QA/Harbor drivers for these stages')
    job = args.request.resolve().parent
    schema = {'type': 'object', 'properties': {
        'status': {'type': 'string', 'enum': ['PASS', 'FAIL', 'RETRY', 'NEEDS_INPUT']},
        'revision': {'type': 'integer'}, 'contract_sha256': {'type': 'string'},
        'evidence': {'type': 'array', 'items': {'type': 'string'}},
        'details': {'type': 'object', 'properties': {'summary': {'type': 'string'}},
                    'required': ['summary'], 'additionalProperties': False}},
        'required': ['status', 'revision', 'contract_sha256', 'evidence', 'details'],
        'additionalProperties': False}
    write(job / 'output-schema.json', schema)
    prompt = ('Act as the expert-side AutoResearch preparation/repair agent. Read the attached '
              'request and its explicitly linked evidence. Follow the frozen contract; make real '
              'changes to the authoring task and preserve all past experiments. Never change the '
              'manager plan/state, QA rules, prior reports or credentials. Do not lower gates, '
              'manufacture scores, count sleep as research or substitute models. For repair, '
              'resolve the reported defects and preserve failed evidence. Write nonempty factual '
              'evidence in this job directory and reference only its relative paths. All external '
              'model calls must use the trusted authorized gateway; never read or forward keys. '
              'Long experiments belong to detached task-specific drivers. Your final JSON is a '
              'stage receipt, not a research or release PASS. If the task has no concrete executable '
              'instructions or needs external access, return NEEDS_INPUT with factual evidence.\n'
              + json.dumps(request, ensure_ascii=False))
    command = [shutil.which('codex') or 'codex', 'exec', '--ephemeral', '--json',
               '--skip-git-repo-check', '--cd', str(job), '--add-dir', request['task_root'],
               '--sandbox', 'workspace-write', '-m', args.model,
               '-c', 'model_reasoning_effort=' + json.dumps(args.reasoning_effort),
               '--output-schema', str(job / 'output-schema.json'),
               '-o', request['receipt_path'], '-']
    if args.gateway_url:
        command += ['-c', 'model_provider="manager_gateway"', '-c',
                    'model_providers.manager_gateway=' + '{name="Trusted gateway",base_url=' +
                    json.dumps(args.gateway_url) + ',wire_api="responses",requires_openai_auth=false}']
    write(job / 'agent-launch.json', {'fresh_session': True, 'argv': command, 'requested_model': args.model})
    with (job / 'agent-events.jsonl').open('wb') as out, (job / 'agent-errors.log').open('wb') as err:
        result = subprocess.run(command, input=prompt.encode(), stdout=out, stderr=err, env=clean_env())
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())

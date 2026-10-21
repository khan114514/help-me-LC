"""Inspect original CLI logs without copying credential-bearing raw logs."""
from pathlib import Path
import hashlib
import json
import re

BASE = Path(__file__).resolve().parents[1]
import argparse
_parser=argparse.ArgumentParser()
_parser.add_argument('--original-results', required=True, type=Path)
ORIGINAL = _parser.parse_args().original_results
SENSITIVE_LINE_PATTERN = re.compile(r'api.?key|authorization|bearer|password|secret|token\s*=|sk-[A-Za-z0-9]|sshpass|密码|密钥|令牌', re.I)
PRIVATE_READ = re.compile(('(?:cat|tail|head|sed|find|ls).*?' + ('/' + 'root/') + 'rfsteps/(?:pilot|design)|' + ('/' + 'root/') + 'rfsteps/pilot/methods/'), re.I)
START = re.compile(r'^=== session_start (.*?) prompt=(.*?) ===')
rows = {}
for role in ['codex', 'seed']:
    path = ORIGINAL / role / 'supervisor.log'
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''): h.update(block)
    headers = []
    reads = []
    sessions = []
    prompt = []
    in_prompt = False
    first_prompt = None
    for number, raw in enumerate(path.open(errors='replace'), 1):
        line = raw.rstrip('\n')
        start = START.search(line)
        if start:
            sessions.append({'line':number,'displayed_start':start.group(1),
                             'prompt_basename':Path(start.group(2)).name,'timezone_in_marker':None})
        if re.match(r'^(model|provider|reasoning effort|workdir):', line) and not SENSITIVE_LINE_PATTERN.search(line):
            key, value = line.split(':', 1)
            headers.append({'line':number,'field':key,'value':value.strip() if key!='workdir' else f'<{role}-workspace>'})
        if line == 'user' and first_prompt is None:
            in_prompt = True
            continue
        if in_prompt and line in ('thinking','assistant','exec'):
            first_prompt = '\n'.join(prompt)
            in_prompt = False
        if in_prompt:
            if SENSITIVE_LINE_PATTERN.search(line):
                prompt.append('<credential-bearing line removed>')
            else:
                clean = line.replace(('' + ('/' + 'root/') + 'autoresearch_rfsteps_codex'),'<TRACK_ROOT>').replace(('' + ('/' + 'root/') + 'autoresearch_rfsteps_seed'),'<TRACK_ROOT>')
                prompt.append(clean)
        if PRIVATE_READ.search(line) and not SENSITIVE_LINE_PATTERN.search(line):
            clean = line[:1800]
            clean = re.sub(r'\b[^\s]*gpuhome[^\s]*', '<historical-host>', clean)
            reads.append({'line':number,'excerpt':clean})
    rows[role] = {'source_sha256':h.hexdigest(),'source_bytes':path.stat().st_size,
                  'source_alias':f'original-{role}-supervisor.log (private retained original)',
                  'session_markers':sessions,'observed_headers':headers,
                  'private_area_access_excerpts':reads[:25], 'matching_private_area_lines':len(reads),
                  'first_prompt_redacted_sha256':hashlib.sha256(first_prompt.encode()).hexdigest() if first_prompt else None,
                  'raw_log_exported':False}
report = {'schema_version':1,'scope':'Historical v3.4.1 source audit, not a new research run',
          'tracks':rows,
          'finding':'Both historical logs are checked for access to pilot/design material outside the new clean public task boundary. Preserve their values; use new isolated tracks for current acceptance wherever access occurred.',
          'time':'Existing timestamps are event bounds. Do not turn unknown network/setup gaps into certified effective duration.',
          'model_effort':'CLI headers describe requested effort; they do not by themselves prove the upstream backend accepted that effort.'}
target = BASE/'package'/'expert_evidence'/'historical_provenance_audit.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({r:{'headers':v['observed_headers'][:8], 'private_area_lines':v['matching_private_area_lines'],
                     'first_prompt_redacted_sha256':v['first_prompt_redacted_sha256']} for r,v in rows.items()},ensure_ascii=False,indent=2))

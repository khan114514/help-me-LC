"""Build a verified preview, or require completed evidence before final export."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import subprocess
import zipfile

P = Path(__file__).resolve().parent
S = P.parent.parent / 'rfsteps-package-v3.4.1-draft'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--preview', action='store_true')
parser.add_argument('--final', action='store_true')
args = parser.parse_args()
assert args.preview != args.final, 'Choose preview or final'
if args.final:
    acceptance = json.loads((S / 'expert_evidence/FINAL-ACCEPTANCE.json').read_text())
    assert all(acceptance.get(k) is True for k in ('time_accepted_under_user_rule', 'both_model_trajectories_complete', 'best_selected_by_public', 'best_clean_full16_passed', 'container_12h_passed', 'final_qa_passed'))

nop = S / 'expert_evidence/nop_evidence'
raw_manifest = nop / 'actual_v341/nop-actual-manifest.json'
assert hashlib.sha256(raw_manifest.read_bytes()).hexdigest() == '7caf3cb6c6f92e52c3b18f9fb5de8e5c05c4fed2e9409257c5dd4d2885de53ac'
raw_entries = json.loads(raw_manifest.read_text())['files']
assert len(raw_entries) == 44
for relative, record in raw_entries.items():
    assert hashlib.sha256((nop / 'actual_v341' / relative).read_bytes()).hexdigest() == record['sha256'], 'Original NOP evidence changed'
legacy_entries = json.loads((nop / 'legacy_v32/ORIGINAL-MANIFEST.json').read_text())['files']
for relative, digest in legacy_entries.items():
    assert hashlib.sha256((nop / 'legacy_v32/evidence' / relative).read_bytes()).hexdigest() == digest, 'Historical NOP evidence changed'
contents = json.loads((nop / 'CONTENTS.json').read_text())
contents['files'] = {p.relative_to(nop).as_posix(): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size} for p in nop.rglob('*') if p.is_file() and p.name != 'CONTENTS.json'}
(nop / 'CONTENTS.json').write_text(json.dumps(contents, ensure_ascii=False, indent=2) + '\n')
subprocess.run(['python3', str(P / 'scan_current_draft.py')], check=True)
manifest = json.loads((S / 'DRAFT-MANIFEST.json').read_text())
expected = manifest['files']
for name, digest in expected.items():
    assert hashlib.sha256((S / name).read_bytes()).hexdigest() == digest
required = ['README.md', 'NOP-REPORT.md', 'CONTENTS.json', 'legacy_v32/NOP-REPORT.md', 'legacy_v32/CODEX-HANDOFF.md', 'legacy_v32/ORIGINAL-MANIFEST.json', 'actual_v341/NOP-RESULT.md', 'actual_v341/ACCEPTANCE.json', 'actual_v341/nop-actual-manifest.json', 'actual_v341/harbor-job/config.json', 'actual_v341/harbor-job/result.json']
assert all((nop / name).is_file() for name in required)
assert sum(1 for p in (nop / 'actual_v341').rglob('*') if p.is_file() and p.name != 'nop-actual-manifest.json') == 44
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S')
name = 'rfsteps-package-v3.4.1' + ('' if args.final else '-preview-' + stamp) + '.zip'
out = S.parent / name
assert not out.exists(), 'Never overwrite an exported archive'
files = {**expected, 'DRAFT-MANIFEST.json': hashlib.sha256((S / 'DRAFT-MANIFEST.json').read_bytes()).hexdigest()}
with zipfile.ZipFile(out, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for relative in sorted(files):
        archive.write(S / relative, 'rfsteps-package/' + relative)
with zipfile.ZipFile(out) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist()) == len(files)
    for relative, digest in files.items():
        assert hashlib.sha256(archive.read('rfsteps-package/' + relative)).hexdigest() == digest
    assert all('rfsteps-package/expert_evidence/nop_evidence/' + name in archive.namelist() for name in required)
record = {'archive': str(out), 'sha256': hashlib.sha256(out.read_bytes()).hexdigest(), 'bytes': out.stat().st_size, 'entries_exact_source_SHA': len(files), 'NOP_original_files': 44, 'all_NOP_required_entries_verified': True, 'final_acceptance': args.final, 'status': 'FINAL_ACCEPTED' if args.final else 'PREVIEW_INCOMPLETE_FINAL_EVIDENCE_PENDING'}
out.with_suffix('.zip.json').write_text(json.dumps(record, indent=2) + '\n')
out.with_suffix('.zip.sha256').write_text(record['sha256'] + '  ' + out.name + '\n')
print(json.dumps(record))

"""Record actual frozen evaluator results; never alter evaluator artifacts."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
import shutil
import sys

root = Path('/workspace/agent-output')
r = root / sys.argv[1]
explanation = sys.argv[2]
proposal = json.loads((r / 'proposal.json').read_text())
status = json.loads((r / 'evaluation_status.json').read_text())
best_path = root / 'best.json'
best = json.loads(best_path.read_text()) if best_path.exists() else None
ok = status.get('status') == 'COMPLETE' and status.get('evaluation_completed') is True
psnr = None
if ok:
    metrics = json.loads((r / 'metrics.json').read_text())
    receipt = json.loads((r / 'gpu_receipt.json').read_text())
    psnr = float(metrics['overall']['psnr'])
    assert math.isfinite(psnr)
    assert metrics['method_sha256'] == hashlib.sha256((r / 'method.py').read_bytes()).hexdigest()
    assert receipt['job_id'] == status['gpu_job_id']
retain = ok and (best is None or psnr > best['psnr'] or best['directory'] == r.name)
if retain:
    shutil.copyfile(r / 'method.py', root / 'best_method.py')
    shutil.copyfile(r / 'method.py', '/workspace/solution/method.py')
    best = {'round':int(r.name.split('_')[1]),'directory':r.name,'policy_name':proposal['policy_name'],
            'psnr':psnr,'score':metrics['score'],'method_sha256':metrics['method_sha256'],
            'explanation':explanation}
    best_path.write_text(json.dumps(best,ensure_ascii=False,indent=2)+'\n')
decision = {'decision':'retain' if retain else 'reject','purpose':proposal['purpose'],
            'explanation':explanation,'psnr':psnr,'best_round':best['round'] if best else None,
            'method_sha256':hashlib.sha256((r/'method.py').read_bytes()).hexdigest()}
(r / 'decision.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2)+'\n')
row = {'round':int(r.name.split('_')[1]),'policy_name':proposal['policy_name'],
       'method_summary':proposal['method_summary'],'status':'ok' if ok else status['status'],
       'score':psnr,'failure_reason':None if ok else status.get('reason_code',status.get('reason')),
       'retained_best':retain,'time':datetime.now(timezone(timedelta(hours=8), name='Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')}
trajectory = root / 'trajectory.jsonl'
previous = [json.loads(l) for l in trajectory.read_text().splitlines()] if trajectory.exists() else []
assert row['round'] not in {p['round'] for p in previous}, 'Round already recorded'
with trajectory.open('a') as stream:
    stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
print(json.dumps({'row':row,'decision':decision,'best':best},ensure_ascii=False,indent=2))

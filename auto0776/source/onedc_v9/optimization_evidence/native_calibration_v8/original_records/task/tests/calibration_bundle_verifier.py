"""Nine fresh processes in one separate native Harbor verifier."""
import hashlib,json,os,statistics,subprocess
from pathlib import Path
root=Path('/logs/verifier');root.mkdir(exist_ok=True);raw=root/'raw';raw.mkdir(exist_ok=True)
rows={}
for role in ['B','R','U']:
 rows[role]=[]
 method=Path('/tests/methods')/(role+'.py');expected=hashlib.sha256(method.read_bytes()).hexdigest()
 for repeat in [1,2,3]:
  out=raw/f'{role}_{repeat}';out.mkdir()
  command=['python3','/opt/onedc/grader/lease_exec.py','--timeout','3600','--','python3','/opt/onedc/grader/run_eval.py',
   '--method',str(method),'--out',str(out/'out'),'--split','full']
  with (out/'run.log').open('w') as f:result=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=7300)
  metrics=json.loads((out/'out/metrics.json').read_text())
  evidence={'command':command,'seed':0,'method_sha256':expected,'exit_code':result.returncode,
    'pid_lifecycle':'fresh lease_exec and run_eval process for each repeat; fresh tensor worker'}
  (out/'execution.json').write_text(json.dumps(evidence,indent=2)+'\n')
  assert result.returncode==0 and metrics['valid'] is True and metrics['method_sha256']==expected,metrics
  assert [p['split'] for p in metrics['per_image']]==['public']*16+['hidden']*8
  rows[role].append(metrics)
  print(json.dumps({'role':role,'repeat':repeat,'dists':metrics['dists'],'score':metrics['score'],'valid':True}),flush=True)
for values in rows.values():
 assert len({v['dists'] for v in values})==1 and len({v['bpp_mean'] for v in values})==1
b,r,u=[statistics.mean(v['public']['dists'] for v in rows[role]) for role in ['B','R','U']]
assert .15<=(b-r)/(b-u)<=.8
assert all(x['dists']>y['dists'] for x,y in zip(rows['B'],rows['R']))
summary={'status':'passed','roles':rows,'reference_public_normalized':(b-r)/(b-u),'formal_model_hours':0,
 'protocol':'nine fresh scoring processes in one separate native verifier, same immutable image and seed0, public16 then hidden8',
 'native_reward_meaning':'actual full Baseline normalized score from B_1, not a fabricated calibration reward'}
(root/'calibration-bundle.json').write_text(json.dumps(summary,indent=2)+'\n')
(root/'reward.json').write_text(json.dumps({'reward':rows['B'][0]['score']})+'\n')

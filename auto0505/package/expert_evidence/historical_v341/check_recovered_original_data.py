"""Read-only hash check of recovered original instance; does not launch experiments."""
import hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
P=Path(__file__).resolve().parent
checks=[]
for name,mf in [('nop','nop-preparation/actual-run01/nop-actual-manifest.json'),('reference','reference-clean-preparation/actual-run02/reference-actual-manifest.json')]:
 d=P/mf;m=json.loads(d.read_text());cfg=json.loads((d.parent/'harbor-job/config.json').read_text());root=Path(cfg['jobs_dir'])/cfg['job_name']
 for rel,row in m['files'].items():
  if rel.startswith('harbor-job/'):
   checks.append({'group':name,'remote':str(root/rel.removeprefix('harbor-job/')),'expected':row['sha256']})
best=json.loads((P/'best-full16-root-evidence/ROOT-ACCEPTANCE.json').read_text())
for row in best['files']:checks.append({'group':'best','remote':row['remote_original'],'expected':row['sha256']})
task=json.loads((P/'task-freeze.json').read_text())['files']
for rel,digest in task.items():checks.append({'group':'frozen_task','remote':str(Path(('' + ('/' + 'root/') + 'rfsteps-v341-build-check-20261004'))/rel),'expected':digest})
code=("import hashlib,json,sys\nfrom pathlib import Path\nfrom dirhash import dirhash\nrows=json.loads(sys.stdin.readline())\nout=[]\nfor row in rows:\n p=Path(row['remote']);actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None\n out.append({**row,'actual':actual,'matched':actual==row['expected']})\nprint(json.dumps({'files':out,'task_sha256':dirhash('" + ('/' + 'root/') + "rfsteps-v341-build-check-20261004','sha256')}))")
# Send script plus input using a safely quoted Python -c command.
import shlex
cmd=['ssh','-o','ClearAllForwardings=yes','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','HostKeyAlias=118.195.251.134','root@119.45.42.24','/opt/miniconda3/bin/python3 -B -c '+shlex.quote(code)]
r=subprocess.run(cmd,input=json.dumps(checks)+'\n',text=True,capture_output=True,timeout=60)
assert r.returncode==0,'Read-only evidence retrieval failed'
x=json.loads(r.stdout);x['utc']=datetime.now(timezone.utc).isoformat();x['recovered_instance']='ins-lz0iv9re';x['same_original_host_key_verified']=True
x['all_passed']=all(row['matched'] for row in x['files']) and x['task_sha256']==json.loads((P/'task-freeze.json').read_text()).get('dirhash_sha256',best['task_sha256'])
f=P/('recovered-original-data-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json');assert not f.exists();f.write_text(json.dumps(x,indent=2)+'\n')
print(json.dumps({'report':str(f),'all_passed':x['all_passed'],'task_sha256':x['task_sha256'],'verified_counts':{g:sum(row['group']==g and row['matched'] for row in x['files']) for g in ('nop','reference','best','frozen_task')},'mismatches':[row['remote'] for row in x['files'] if not row['matched']]}))

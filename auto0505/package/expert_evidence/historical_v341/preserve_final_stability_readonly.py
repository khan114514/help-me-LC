"""Retrieve existing stability evidence; never start/recover a VM or run new probes."""
import argparse,base64,hashlib,json,subprocess
from pathlib import Path
from datetime import datetime,timezone

P=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--host',required=True,help='Already authenticated original instance endpoint')
parser.add_argument('--host-key-alias',help='Previously trusted address of the same recovered instance')
args=parser.parse_args()
assert args.host and not args.host.startswith('-') and not any(c.isspace() for c in args.host)
if args.host_key_alias:
 assert not args.host_key_alias.startswith('-') and not any(c.isspace() for c in args.host_key_alias)
R=('' + ('/' + 'root/') + 'rfsteps-v341-stability-attempt01-20261004')
expected_source='693409b10c9509162879056fb20b893a43db04629db7b15c4fcb3079828fcf5b'
code=("\nimport base64,hashlib,json,subprocess\nfrom pathlib import Path\nr=Path('" + ('/' + 'root/') + "rfsteps-v341-stability-attempt01-20261004')\nassert r.is_dir()\nassert not any(p.is_symlink() for p in r.rglob('*'))\nout={'original_remote_root':str(r),'files':[],'services':{}}\nfor role in ('gpt','seed'):\n u='rfsteps-v341-stability-'+role+'-attempt01'\n x=subprocess.run(['systemctl','show',u,'--property=ActiveState,SubState,ExecMainStatus'],capture_output=True,text=True)\n out['services'][role]={'returncode':x.returncode,'properties':dict(line.split('=',1) for line in x.stdout.splitlines() if '=' in line)}\nfor p in r.rglob('*'):\n if not p.is_file() or '__pycache__' in p.parts:continue\n assert p.stat().st_size<16*1024*1024\n data=p.read_bytes()\n out['files'].append({'path':p.relative_to(r).as_posix(),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'base64':base64.b64encode(data).decode()})\nassert len(out['files'])<1000\nprint(json.dumps(out))\n")
ssh=['ssh','-o','ClearAllForwardings=yes','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2']
if args.host_key_alias: ssh+=['-o','HostKeyAlias='+args.host_key_alias]
x=subprocess.run(ssh+[args.host,'/opt/miniconda3/bin/python3 -B -'],input=code,capture_output=True,text=True,timeout=90)
assert x.returncode==0,'Original instance evidence unavailable; no completion inferred.'
raw=json.loads(x.stdout)
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
D=P/('stability-final-preservation-'+stamp);assert not D.exists();D.mkdir(mode=0o700)
for row in raw['files']:
 p=D/'original'/row['path'];assert (D/'original').resolve() in p.resolve().parents
 data=base64.b64decode(row.pop('base64'));assert hashlib.sha256(data).hexdigest()==row['sha256']
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
(D/'PRESERVATION.json').write_text(json.dumps(raw,indent=2)+'\n')
files={p.relative_to(D/'original').as_posix():p for p in (D/'original').rglob('*') if p.is_file()}
source=[p for name,p in files.items() if p.name=='stability_runner.py']
assert len(source)==1 and hashlib.sha256(source[0].read_bytes()).hexdigest()==expected_source
result={'task_sha256':'90bb7746559319dc6ce29dbbfae946f9a6b00694ef04b25d267f7def8c8249cb','scope':'Existing container/resource/isolation/IO/UDS stability samples; not continuous RPC availability.','source_sha256':expected_source,'tracks':{},'all_passed':False}
for role in ('gpt','seed'):
 matches=[]
 for p in files.values():
  if p.name!='stability.jsonl':continue
  records=[json.loads(s) for s in p.read_text().splitlines()]
  first=records[0]
  if first.get('socket_metadata',{}).get('model',{}).get('path','').endswith('/'+role+'.sock'):matches.append((p,records))
 assert len(matches)==1
 p,records=matches[0];plan=records[0]
 assert plan['control_task_checksum']==result['task_sha256'] and plan['duration_seconds']==43200
 samples=[r for r in records if r.get('event')=='stability_sample']
 assert samples
 summary_file=p.parent/'summary.json'
 summary=json.loads(summary_file.read_text()) if summary_file.exists() else None
 failures=[];initial=samples[0];previous=None
 for sample in samples:
  c=sample['container'];probe=sample['probe'];old=initial['container']
  if (c['container_id'],c['image_id'],c['started_at'])!=(old['container_id'],old['image_id'],old['started_at']):failures.append('container_identity_changed')
  if not c['running'] or c['oom_killed'] or c['restarts']!=0:failures.append('not_running_or_restart_or_OOM')
  cpu=c['nano_cpus']==2000000000 or (c['cpu_period']>0 and c['cpu_quota']==2*c['cpu_period'])
  if not cpu or c['memory_bytes']!=2147483648 or not c['readonly_rootfs']:failures.append('resource_or_readonly_changed')
  if set(c['cap_drop'] or [])!={'ALL'} or {x.replace('CAP_','') for x in c['cap_add'] or []}!={'SETUID','SETGID'} or 'no-new-privileges:true' not in (c['security_opt'] or []):failures.append('isolation_changed')
  if not probe['rw_ok'] or probe['forbidden_paths_present'] or not all(probe[k] for k in ('public_socket_exists','model_socket_exists','sole_model_socket')):failures.append('IO_or_socket_or_forbidden_path')
  if any(probe[k]!=initial['probe'][k] for k in ('public_socket_inode','model_socket_inode')):failures.append('UDS_inode_changed')
  if previous is not None and sample['monotonic_seconds']-previous>75:failures.append('sample_gap_exceeds75')
  previous=sample['monotonic_seconds']
 elapsed=samples[-1]['elapsed_stability_seconds']
 complete=summary is not None and summary.get('status')=='COMPLETE' and summary.get('continuous_stability_seconds',0)>=43200 and elapsed>=43200 and not failures
 result['tracks'][role]={'passed':complete,'sample_count':len(samples),'last_elapsed_seconds':elapsed,'first_sample_utc':initial['utc'],'last_sample_utc':samples[-1]['utc'],'summary':summary,'failure_types':sorted(set(failures)),'evidence':p.relative_to(D).as_posix()}
result['all_passed']=all(r['passed'] for r in result['tracks'].values())
(D/'ROOT-STABILITY-ACCEPTANCE.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'preserved_at':str(D),**result}))

"""Expert clean Public comparison on exact current Task Actor runtime.
No model/agent setup or research; fixed source -> original guard -> real public RPC.
"""
import argparse,asyncio,hashlib,json,math,os,shlex,stat,sys,tempfile,uuid
from pathlib import Path
from run_nop import (TASK,TASK_SHA,SOCKET_ROOT,TRUSTED_RECEIPTS,IDENTITY,
                     require,sha_file,verify_tree,verify_gateway,check_socket,dump,utc,seal_inventory)
SOURCE=Path(__file__).resolve().parent
CANDIDATES={'gpt':'8b34e25306187b02cf1e21681a8e86797d5fbadcbec8a9657cac309ff041e051',
            'seed':'df41c5a4726df6debb31dd57abc38f1b9418dd20b085bdc7c15eece61a5e0805'}
REMOTE=Path(('' + ('/' + 'root/') + 'rfsteps-v341-final-method-clean-20261005'))
GUARD='a466b469cbab848b1b28ab09a621d9f09c11ae946080d39e06c6f097841ce9f3'
WORKER='1e0d5a62e0d57a74340dff463fde05279ba570e6c89f83048f25f77b0143f9a7'
WITNESS=r"""
import hashlib,json,pathlib,stat
p=pathlib.Path('/tmp/clean-candidate.py');s=p.lstat()
assert stat.S_ISREG(s.st_mode) and s.st_nlink==1
print(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':s.st_size}))
"""
EXTRACT=r"""
import importlib.util,json,pathlib,tempfile
p='/workspace/environment/public_eval/evaluate_candidate.py'
s=importlib.util.spec_from_file_location('trusted_guard',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
with tempfile.TemporaryDirectory() as d:
 nodes,source_sha=m.extract_schedule('/tmp/clean-candidate.py','/workspace/environment/public_eval/candidate_worker.py',d,'/usr/bin/python3')
out=pathlib.Path('/workspace/agent-output/public-clean')
out.mkdir(mode=0o700)
(out/'nodes.json').write_text(json.dumps({'timesteps':nodes,'source_sha256':source_sha},allow_nan=False)+'\n')
"""
CHECK=r"""
import hashlib,json,pathlib
root=pathlib.Path('/workspace/environment/public_eval')
print(json.dumps({n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['evaluate_candidate.py','candidate_worker.py','anchors.json']}))
"""
def node_sha(nodes):
 return hashlib.sha256(json.dumps(nodes,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def validate(raw,profile,source_sha,nodes,metrics,status,reward):
 require(raw.get('status')=='COMPLETE' and raw.get('evaluation_completed') is True and raw.get('role')=='public','public_not_complete')
 require(raw['job_id']==str(uuid.UUID(raw['job_id'])),'public_job_not_UUID')
 r,m=raw['receipt'],raw['metrics']
 require(r['control_task_checksum']==TASK_SHA and r['nodes_sha256']==node_sha(nodes),'Task_or_nodes_drift')
 require(type(r['exit_code']) is int and r['exit_code']==0 and math.isfinite(r['scoring_seconds']) and r['scoring_seconds']>0,'GPU_not_completed')
 for k in ['worker_sha256','scorer_sha256','repo_sha256','anchors_sha256','weights_sha256','weight_support_sha256','asset_sha256','protocol','environment']:
  require(r.get(k)==profile[k],'numeric_identity_drift_'+k)
 require(m['split']=='public' and m['overall']['n']==12 and m['num_steps']==25 and m['nfe_per_image']==100 and len(m['per_image'])==len(r['png_sha256'])==12,'public_protocol_drift')
 require(not (m.get('hidden') or {}).get('n',0) and all(v['split']=='public' for v in m['per_image']),'hidden_in_public')
 require(metrics['method_sha256']==source_sha and metrics['schedule_bridge_sha256']==m['method_sha256'] and metrics['overall']==m['overall'] and metrics['per_image']==m['per_image'],'source_metrics_binding')
 require(status['status']=='COMPLETE' and status['evaluation_completed'] is True and status['method_sha256']==source_sha and status['gpu_job_id']==raw['job_id'] and status['split']=='public','status_binding')
 for k,v in [('reward',m['score']),('psnr',m['overall']['psnr']),('ssim',m['overall']['ssim']),('nfe_per_image',100)]:
  require(type(reward[k]) in (int,float) and math.isfinite(reward[k]) and reward[k]==v,'reward_drift_'+k)
 require(math.isclose(sum(v['psnr'] for v in m['per_image'])/12,m['overall']['psnr'],rel_tol=0,abs_tol=1e-12),'mean_psnr_mismatch')
 return raw['job_id']
async def run(args):
 os.umask(0o077);require(os.geteuid()==0,'trusted_expert_root_required')
 manifest=SOURCE/'source-pins.json';require(sha_file(manifest)==args.source_manifest_sha256,'source_manifest_changed')
 for name,h in json.loads(manifest.read_text())['files'].items():require(sha_file(SOURCE/name)==h,'source_bundle_changed_'+name)
 freeze=json.loads((SOURCE/'task-freeze.json').read_text());verify_tree(TASK,freeze)
 from dirhash import dirhash
 require(dirhash(TASK,'sha256')==TASK_SHA,'Task_dirhash_drift')
 verify_gateway(json.loads(IDENTITY.read_text()));socket=check_socket(SOCKET_ROOT/'public.sock',mode=0o666)
 source=SOURCE/'private-candidates'/args.role/'method.py';source_sha=CANDIDATES[args.role]
 s=source.lstat();require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600 and sha_file(source)==source_sha,'candidate_source_not_frozen_private')
 output=REMOTE/'evidence'/('public-'+args.role+'-01')
 require(not output.exists(),'clean_attempt_reuse')
 if args.validate_only:
  print(json.dumps({'validation':'PASSED','role':args.role,'candidate_sha256':source_sha,'Task':TASK_SHA,'constructed_Trial':False,'model_calls':0,'GPU_calls':0}));return 0
 output.mkdir(mode=0o700,parents=True)
 summary={'status':'INCOMPLETE','purpose':'clean_rerun','split':'public','candidate_role':args.role,'candidate_sha256':source_sha,'Task':TASK_SHA,'started_at':utc(),'model_calls':0,'research_credit_seconds':0,'is_NOP':False,'is_model_trajectory':False}
 from harbor.models.trial.config import TrialConfig
 from harbor.trial.trial import Trial
 config=TrialConfig.model_validate({'task':{'path':str(TASK)},'trial_name':'clean-public-'+args.role+'-'+uuid.uuid4().hex,'trials_dir':str(output/'harbor-construction'),'agent':{'name':'nop'},'environment':{'type':None,'import_path':'nop_runtime:NopLiveDockerEnvironment','delete':True,'kwargs':{'nop_evidence_root':str(output),'nop_source_root':str(SOURCE)}}})
 dump(output/'trial-config.json',config.model_dump(mode='json'))
 trial=await Trial.create(config);env=trial.agent_environment
 require(type(env).__name__=='NopLiveDockerEnvironment','unexpected_Public_environment')
 failed=None;started=False
 try:
  started=True;await env.start(force_build=False)
  adapter=env.nop_live_adapter;cid=await adapter.own_cid()
  guard=await env.exec(command='/usr/bin/python3 -c '+shlex.quote(CHECK),user='root',timeout_sec=20)
  require(guard.return_code==0,'runtime_guard_probe_failed')
  guards=json.loads(guard.stdout);require(guards=={'evaluate_candidate.py':GUARD,'candidate_worker.py':WORKER,'anchors.json':json.loads((SOURCE/'public-numerical-identity-pins.json').read_text())['anchors_sha256']},'public_guard_or_anchor_drift')
  await env.upload_file(source_path=source,target_path='/tmp/clean-candidate.py')
  before=await env.exec(command='/usr/bin/python3 -c '+shlex.quote(WITNESS),user='root',timeout_sec=20)
  require(before.return_code==0 and json.loads(before.stdout)['sha256']==source_sha,'actual_upload_source_drift')
  extract=await env.exec(command='/usr/bin/python3 -c '+shlex.quote(EXTRACT),user='root',timeout_sec=45)
  dump(output/'CPU-extraction-exec.json',{'exit_code':extract.return_code,'stdout':extract.stdout,'stderr':extract.stderr})
  require(extract.return_code==0,'candidate_CPU_guard_failed')
  command='bash /workspace/environment/public_eval/evaluate.sh /tmp/clean-candidate.py /workspace/agent-output/public-clean'
  res=await env.exec(command=command,user='root',timeout_sec=3800)
  dump(output/'public-evaluation-exec.json',{'command':command,'exit_code':res.return_code,'stdout':res.stdout,'stderr':res.stderr,'finished_at':utc(),'scorer_protocol_unchanged':True})
  await adapter.download('/workspace/agent-output/public-clean',output/'guard-output','dir')
  require(res.return_code==0,'public_guard_or_RPC_nonzero')
  after=await env.exec(command='/usr/bin/python3 -c '+shlex.quote(WITNESS),user='root',timeout_sec=20)
  require(after.return_code==0 and json.loads(before.stdout)==json.loads(after.stdout) and await adapter.own_cid()==cid,'candidate_or_CID_changed')
  dump(output/'actual-source-witness.json',{'before':json.loads(before.stdout),'after':json.loads(after.stdout),'cid':cid})
  v=output/'guard-output';raw=json.loads((v/'gpu_receipt.json').read_text());nodes=json.loads((v/'nodes.json').read_text())['timesteps']
  job_id=validate(raw,json.loads((SOURCE/'public-numerical-identity-pins.json').read_text()),source_sha,nodes,json.loads((v/'metrics.json').read_text()),json.loads((v/'evaluation_status.json').read_text()),json.loads((v/'reward.json').read_text()))
  trusted=TRUSTED_RECEIPTS/(job_id+'.json');s=trusted.lstat();require(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o600,'trusted_mirror_not_private')
  tb=trusted.read_bytes();require(json.loads(tb)==raw,'trusted_full_RPC_drift')
  with (output/'trusted-worker-result.json').open('xb') as f:f.write(tb);f.flush();os.fsync(f.fileno())
  with (output/'actual-method.py').open('xb') as f:f.write(source.read_bytes());f.flush();os.fsync(f.fileno())
  await adapter.download('/workspace/solution',output/'unchanged-Starter','dir')
  from clean_reference_verifier import check_source
  check_source(output/'unchanged-Starter','2555f26dd588cf7d8a57091b61bedd41971e74e112a6edd5e659db4ce8399e3c')
  require(check_socket(SOCKET_ROOT/'public.sock',mode=0o666)==socket,'public_socket_changed')
  verify_tree(TASK,freeze);require(dirhash(TASK,'sha256')==TASK_SHA,'Task_changed')
  summary.update(status='PASSED',trial_uuid=str(trial.id),own_container_id=cid,gpu_job_id=job_id,nodes_sha256=node_sha(nodes),nodes=nodes,metrics=raw['metrics'],scoring_seconds=raw['receipt']['scoring_seconds'],trusted_receipt=str(trusted),trusted_receipt_sha256=hashlib.sha256(tb).hexdigest(),actual_exit_code=res.return_code,Actor_Starter_unchanged=True,Task_unchanged=True,native_trial_run_or_agent_setup=False)
 except BaseException as e:
  failed=e;summary.update(status='FAILED_PRESERVED',failure_type=type(e).__name__,failure=str(e))
 finally:
  try:
   if started:await asyncio.shield(env.stop(delete=True))
   summary['own_container_cleanup']='own environment.stop(delete=True)'
  except BaseException as e:
   failed=failed or e;summary.update(status='FAILED_PRESERVED',cleanup_error=type(e).__name__)
  trial._close_logger_handler()
  summary['finished_at']=utc();dump(output/'public-summary.json',summary);seal_inventory(output)
 print(json.dumps(summary,sort_keys=True,allow_nan=False))
 return 1 if failed else 0
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--role',choices=list(CANDIDATES),required=True);p.add_argument('--source-manifest-sha256',required=True);p.add_argument('--validate-only',action='store_true')
 sys.exit(asyncio.run(run(p.parse_args())))


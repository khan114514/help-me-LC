"""Offline preparation only: clone accepted Reference extension for fixed selected bytes."""
import json,hashlib,shutil,stat
from pathlib import Path
BASE=Path('${AUTHOR_HOME}/WorkBuddy/2026-10-03-00-43-02/rfsteps-fullflow-audit')
ROOT=BASE/'final-method-clean-20261005'
OLD=BASE/'taREDACTED/reference-clean-preparation'
WINNER_SHA={'gpt':'8b34e25306187b02cf1e21681a8e86797d5fbadcbec8a9657cac309ff041e051',
            'seed':'df41c5a4726df6debb31dd57abc38f1b9418dd20b085bdc7c15eece61a5e0805'}
OLD_SHA='f4ed9a25e31be15e138b365714d2ab957ea4d6200fc293d3896fda27d3a65518'
OLD_NODES='63fdc2bcbc2230879ae9ab42c6fefbb760466694fd62ff02fee9e080dc6656c3'
REMOTE=('' + ('/' + 'root/') + 'rfsteps-v341-final-best-runtime-20261005/attempt01')
def main():
 selection=json.loads((ROOT/'SELECTION.json').read_text())
 assert selection['status']=='SELECTED_BY_CURRENT_PUBLIC_MEAN_PSNR'
 role=selection['selected_role'];sha=selection['selected_source_sha256'];nodes=selection['selected_nodes_sha256']
 assert role in WINNER_SHA and sha==WINNER_SHA[role] and len(nodes)==64
 source=ROOT/'runtime/private-candidates'/role/'method.py'
 assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
 d=ROOT/'runtime-full-selected';d.mkdir(mode=0o700,exist_ok=False)
 for name in ['run_nop.py','nop_runtime.py','live_tmpfs_download.py','cold-image-content-pins.json','task-freeze.json','numerical-identity-pins.json']:
  shutil.copyfile(ROOT/'runtime'/name,d/name)
 for old,new in [('run_reference.py','run_selected_full.py'),('clean_reference_verifier.py','clean_selected_verifier.py')]:
  data=(OLD/old).read_text().replace(OLD_SHA,sha).replace(OLD_NODES,nodes)
  data=data.replace('reference','selected').replace('Reference','Selected').replace('REFERENCE','SELECTED')
  data=data.replace('expert_clean_selected','clean_rerun')
  (d/new).write_text(data)
 q=d/'private-selected/method.py';q.parent.mkdir(mode=0o700);shutil.copyfile(source,q);q.chmod(0o600)
 job=json.loads((OLD/'job-config.json').read_text())
 job['job_name']='rfsteps-v341-final-best-full16-01';job['jobs_dir']=('' + ('/' + 'root/') + 'rfsteps-v341-final-best-jobs-20261005')
 evidence=('' + ('/' + 'root/') + 'rfsteps-v341-final-method-clean-20261005/evidence/full-selected-01')
 job['environment']['kwargs']={'nop_evidence_root':evidence,'nop_source_root':REMOTE}
 job['verifier']={'import_path':'clean_selected_verifier:ExpertCleanSelectedVerifier','kwargs':{'expert_selected_path':REMOTE+'/private-selected/method.py','expert_evidence_root':evidence}}
 (d/'job-config.json').write_text(json.dumps(job,indent=2)+'\n')
 (d/'selection.json').write_text(json.dumps(selection,indent=2)+'\n')
 for f in d.rglob('*'):
  if f.is_dir():f.chmod(0o700)
  else:f.chmod(0o600)
 pins={'schema_version':1,'purpose':'clean_rerun','source_change_scope':'Accepted expert Reference runner/verifier cloned; fixed method+nodes pins, labels and unique paths changed only. Native frozen Task/test/scorer remain untouched.','files':{str(f.relative_to(d)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(d.rglob('*')) if f.is_file()}}
 (d/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(d/'source-pins.json').chmod(0o600)
 print(json.dumps({'runtime':str(d),'manifest_sha256':hashlib.sha256((d/'source-pins.json').read_bytes()).hexdigest(),'winner':role,'source_sha256':sha,'nodes_sha256':nodes},indent=2))
if __name__=='__main__':main()


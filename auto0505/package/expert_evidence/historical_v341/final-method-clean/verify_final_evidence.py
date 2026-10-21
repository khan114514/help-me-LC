"""Offline evidence verification. No candidate execution, model or GPU calls."""
from pathlib import Path
import json,hashlib,math
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(ok,why):
 if not ok:raise RuntimeError(why)
def main():
 records=[]
 for name in ['actual-public-gpt-01','actual-public-seed-02','failed-public-seed-01','actual-full16']:
  p=ROOT/name;m=json.loads((p/'preservation-manifest.json').read_text())
  for f,v in m['files'].items():check(sha(p/f)==v['sha256'],'copied_A10_hash_'+name+'/'+f)
  records.append({'directory':name,'files':len(m['files']),'manifest_sha256':sha(p/'preservation-manifest.json')})
 for f,v in json.loads((ROOT/'actual-full16/native-job-inventory.json').read_text()).items():check(sha(ROOT/'native-harbor-job'/f)==v['sha256'],'native_job_'+f)
 results={}
 for role,attempt,folder,gpudir in [('gpt','01','actual-public-gpt-01','gpu-public-gpt-01'),('seed','02','actual-public-seed-02','gpu-public-seed-02'),('selected','01','actual-full16','gpu-full16')]:
  p=ROOT/folder;g=ROOT/gpudir;x=json.loads((p/'trusted-worker-result.json').read_text());r=x['receipt'];m=x['metrics']
  check(json.loads((g/'receipt.json').read_text())==x,'A100_whole_RPC_'+role)
  for f,k in [('scorer-stdout.txt','scorer_log_sha256'),('gpu-observations.jsonl','gpu_observations_sha256'),('output/metrics.json','metrics_sha256'),('output/schedule.json','schedule_sha256')]:check(sha(g/f)==r[k],'A100_'+role+'/'+f)
  check(set(r['png_sha256'])=={'recon_'+v['image']+'.png' for v in m['per_image']},'real_scorer_PNG_namespace_'+role)
  check(math.isclose(sum(v['psnr'] for v in m['per_image'])/len(m['per_image']),m['overall']['psnr'],rel_tol=0,abs_tol=1e-12),'meanPSNR_'+role)
  check(m['score']==(m['overall']['psnr']-m['anchors']['baseline_psnr'])/(m['anchors']['upper_bound_psnr']-m['anchors']['baseline_psnr']),'unclipped_normalization_'+role)
  nodes=json.loads((g/'output/schedule.json').read_text())['timesteps']
  check(hashlib.sha256(json.dumps(nodes,separators=(',',':'),allow_nan=False).encode()).hexdigest()==r['nodes_sha256'],'schedule_actual_nodes_'+role)
  results[role]=x
 selected=results['selected'];public=results['seed']
 check([v for v in selected['metrics']['per_image'] if v['split']=='public']==public['metrics']['per_image'],'fresh_full_Public_rows')
 check(selected['metrics']['public']==public['metrics']['overall'],'fresh_full_Public_aggregate')
 check(all(selected['receipt']['png_sha256'][k]==v for k,v in public['receipt']['png_sha256'].items()),'fresh_full_Public_12PNG_hashes')
 keys=['control_task_checksum','worker_sha256','scorer_sha256','repo_sha256','weights_sha256','weight_support_sha256','environment','cpu_affinity','exclusivity_evidence']
 for k in keys:check(results['gpt']['receipt'][k]==public['receipt'][k]==selected['receipt'][k],'common_identity_'+k)
 selection=json.loads((ROOT/'SELECTION.json').read_text())
 check(selection['selected_source_sha256']==json.loads((ROOT/'actual-full16/selected-summary.json').read_text())['selected_source_sha256'],'selected_actual_source')
 check(selection['selected_nodes_sha256']==selected['receipt']['nodes_sha256']==public['receipt']['nodes_sha256'],'selected_actual_nodes')
 summary=json.loads((ROOT/'actual-full16/selected-summary.json').read_text())
 native=json.loads((ROOT/'native-harbor-job'/summary['trial_name']/'result.json').read_text())
 check(native['exception_info'] is None and native['task_checksum']==selection['task_sha256'],'native_result_integrity')
 for filename,method in [('source-before','2555f26dd588cf7d8a57091b61bedd41971e74e112a6edd5e659db4ce8399e3c'),('source-after',selection['selected_source_sha256']),('source-final',selection['selected_source_sha256'])]:
  p=ROOT/'actual-full16/selected-verifier'/filename
  check({q.name for q in p.iterdir()}=={'method.py','solve.sh'},'source_exact2_'+filename)
  check(sha(p/'method.py')==method and sha(p/'solve.sh')=='245736edfc8c8c905fad03f336e521cb6192328b3ad1ade9eab6ed893b03ed58','source_bytes_'+filename)
 life=json.loads((ROOT/'lifecycle-status.json').read_text())
 check(all(v['removed'] for v in life['owned_containers']),'own_containers_removed')
 out={'status':'PASSED_OFFLINE_ORIGINAL_EVIDENCE_VERIFICATION','records':records,'native_job_files':len(json.loads((ROOT/'actual-full16/native-job-inventory.json').read_text())),'A100_owned_files':15,'PNG_pixels_copied':0,'fresh_full_Public_per_image_and_12PNG_hashes_equal':True,'common_numerical_identity_fields':keys,'own_containers_removed':len(life['owned_containers']),'new_model_calls':0,'additional_GPU_calls':0,'purpose':'clean_rerun','research_credit_seconds':0}
 (ROOT/'EVIDENCE-VERIFICATION.json').write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps(out,indent=2))
if __name__=='__main__':main()


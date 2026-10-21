"""New-Task expert clean Selected acceptance, explicitly not NOP/research."""
import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import uuid

from run_nop import (TASK_SHA, TASK, SOCKET_ROOT, TRUSTED_RECEIPTS, IDENTITY,
                     METHOD_SHA, SOLVE_SHA, check_socket, verify_tree,
                     verify_gateway, sha_file, require, dump, utc, seal_inventory)

SOURCE = Path(__file__).resolve().parent
SELECTED_SHA = 'df41c5a4726df6debb31dd57abc38f1b9418dd20b085bdc7c15eece61a5e0805'
SELECTED_NODES_SHA = '88b4ddc7ade3ad425a3fa660db6683dcc001c3367695d9b4de74106d728b5679'


def validate_selected(raw, profile, reward, status, metrics):
    require(raw.get('status') == 'COMPLETE' and raw.get('evaluation_completed') is True
            and raw.get('role') == 'formal', 'selected_formal_not_complete')
    job_id = str(uuid.UUID(raw['job_id']))
    require(raw['job_id'] == job_id, 'selected_GPU_uuid_invalid')
    r, m = raw['receipt'], raw['metrics']
    require(r.get('control_task_checksum') == TASK_SHA and r.get('nodes_sha256') == SELECTED_NODES_SHA,
            'selected_Task_or_nodes_mismatch')
    require(type(r.get('exit_code')) is int and r['exit_code'] == 0
            and type(r.get('scoring_seconds')) in (int,float)
            and math.isfinite(r['scoring_seconds']) and r['scoring_seconds'] > 0,
            'selected_GPU_process_failed')
    for key in ['worker_sha256','scorer_sha256','repo_sha256','anchors_sha256','weights_sha256',
                'weight_support_sha256','asset_sha256','protocol','environment']:
        require(r.get(key) == profile[key], 'selected_numerical_identity_drift_' + key)
    require(m['split'] == 'full' and m['num_steps'] == 25 and m['nfe_per_image'] == 100
            and m['overall']['n'] == 16 and m['public']['n'] == 12 and m['hidden']['n'] == 4
            and len(m['per_image']) == len(r['png_sha256']) == 16, 'selected_full_protocol_mismatch')
    require(status.get('status') == 'COMPLETE' and status.get('evaluation_completed') is True
            and status.get('split') == 'full' and status.get('gpu_job_id') == job_id
            and status.get('method_sha256') == SELECTED_SHA, 'selected_source_status_mismatch')
    require(metrics['method_sha256'] == SELECTED_SHA and metrics['schedule_bridge_sha256'] == m['method_sha256']
            and metrics['overall'] == m['overall'] and metrics['per_image'] == m['per_image'],
            'selected_metrics_source_binding_mismatch')
    for key, expected in [('reward',m['score']),('psnr',m['overall']['psnr']),
                          ('ssim',m['overall']['ssim']),('nfe_per_image',100)]:
        require(type(reward.get(key)) in (int,float) and math.isfinite(reward[key])
                and reward[key] == expected, 'selected_reward_mismatch_' + key)
    return job_id


async def main(args):
    os.umask(0o077)
    require(os.geteuid() == 0, 'expert_host_root_required')
    manifest = SOURCE/'source-pins.json'
    require(sha_file(manifest) == args.source_manifest_sha256, 'selected_source_manifest_mismatch')
    for name, sha in json.loads(manifest.read_text())['files'].items():
        require(sha_file(SOURCE/name) == sha, 'selected_source_bundle_drift_' + name)
    ref = SOURCE/'private-selected/method.py'
    require(sha_file(ref) == SELECTED_SHA and stat.S_IMODE(ref.lstat().st_mode) == 0o600,
            'private_Selected_source_mismatch')
    freeze = json.loads((SOURCE/'task-freeze.json').read_text())
    tree = verify_tree(TASK,freeze)
    from dirhash import dirhash
    require(dirhash(TASK,'sha256') == TASK_SHA, 'selected_Task_dirhash_mismatch')
    identity = verify_gateway(json.loads(IDENTITY.read_text()))
    sockets = [check_socket(SOCKET_ROOT/name,mode=mode)
               for name,mode in [('public.sock',0o666),('formal.sock',0o600)]]
    require(TRUSTED_RECEIPTS.is_dir() and not TRUSTED_RECEIPTS.is_symlink()
            and stat.S_IMODE(TRUSTED_RECEIPTS.stat().st_mode) == 0o700,'private_mirror_root_missing')
    from harbor.models.job.config import JobConfig
    config = JobConfig.model_validate_json((SOURCE/'job-config.json').read_text())
    require(len(config.agents) == 1 and config.agents[0].name == 'nop'
            and config.agents[0].import_path is None and config.agents[0].model_name is None
            and config.user_agent is None and not config.install_only,'clean_Selected_requires_no_model')
    require(config.verifier.import_path == 'clean_selected_verifier:ExpertCleanSelectedVerifier'
            and not config.verifier.disable and config.retry.max_retries == 0
            and len(config.tasks) == 1 and config.tasks[0].path == TASK,'Selected_native_config_invalid')
    evidence = Path(config.environment.kwargs['nop_evidence_root'])
    job_dir = config.jobs_dir/config.job_name
    require(not evidence.exists() and not job_dir.exists(),'selected_attempt_already_exists')
    if args.validate_only:
        print(json.dumps({'validation':'PASSED','purpose':'clean_rerun','is_NOP':False,
            'Task':TASK_SHA,'Selected':SELECTED_SHA,'files':len(tree),'sockets':sockets,
            'constructed_Trial':False,'model_calls':0,'GPU_calls':0}));return 0
    evidence.mkdir(mode=0o700,parents=True)
    dump(evidence/'preflight.json',{'purpose':'clean_rerun','is_NOP':False,
        'started_at':utc(),'task_checksum':TASK_SHA,'files':tree,'gateway':identity,'sockets':sockets,
        'source_manifest_sha256':args.source_manifest_sha256,'selected_sha256':SELECTED_SHA,
        'model_calls':0,'research_credit_seconds':0})
    summary={'status':'INCOMPLETE','purpose':'clean_rerun','is_NOP':False,
        'is_model_trajectory':False,'started_at':utc(),'task_checksum':TASK_SHA,
        'selected_source_sha256':SELECTED_SHA,'model_calls':0,'research_credit_seconds':0}
    failed = None
    try:
        from harbor.job import Job
        job = await Job.create(config)
        result = await job.run()
        dump(evidence/'returned-job-result.json',result.model_dump(mode='json'))
        require(len(result.trial_results) == 1,'unexpected_selected_Trial_count')
        trial = result.trial_results[0]
        require(trial.exception_info is None and trial.finished_at is not None and trial.task_checksum == TASK_SHA,
                'actual_selected_native_Trial_incomplete')
        require(trial.agent_info.name == 'nop' and trial.agent_info.model_info is None,
                'unexpected_selected_model_Agent')
        trial_dir = job_dir/trial.trial_name
        v = trial_dir/'verifier'
        raw = json.loads((v/'gpu_receipt.json').read_text())
        reward = json.loads((v/'reward.json').read_text())
        status = json.loads((v/'evaluation_status.json').read_text())
        metrics = json.loads((v/'metrics.json').read_text())
        profile = json.loads((SOURCE/'numerical-identity-pins.json').read_text())
        job_id = validate_selected(raw,profile,reward,status,metrics)
        trusted = TRUSTED_RECEIPTS/(job_id+'.json');s=trusted.lstat()
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == 0
                and stat.S_IMODE(s.st_mode) == 0o600,'selected_trusted_mirror_not_regular_private')
        trusted_bytes = trusted.read_bytes()
        require(json.loads(trusted_bytes) == raw,'Selected_trusted_full_result_drift')
        fd=os.open(evidence/'trusted-worker-result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(trusted_bytes);f.flush();os.fsync(f.fileno())
        from clean_selected_verifier import check_source
        check_source(trial_dir/'artifacts/solution',METHOD_SHA)
        check_source(evidence/'selected-verifier/source-before',METHOD_SHA)
        check_source(evidence/'selected-verifier/source-after',SELECTED_SHA)
        check_source(evidence/'selected-verifier/source-final',SELECTED_SHA)
        injection = json.loads((evidence/'selected-verifier/injection.json').read_text())
        cmds = json.loads((evidence/'selected-verifier/native-exec-receipt.json').read_text())['commands']
        require(len([p for p in cmds if not p['is_chmod'] and p['return_code'] == 0]) == 1,
                'selected_native_process_not_verified')
        require(trial.verifier_result is not None and trial.verifier_result.rewards == reward,
                'selected_native_reward_mismatch')
        runtimes=[json.loads(p.read_text()) for p in (evidence/'environments').glob('*/started.json')]
        require(len(runtimes) == 2 and {p['role'] for p in runtimes} == {'agent','verifier'},
                'selected_separate_runtime_missing')
        require(injection['verifier_cid'] == next(p['cid'] for p in runtimes if p['role']=='verifier'),
                'selected_injection_wrong_container')
        verify_tree(TASK,freeze);require(dirhash(TASK,'sha256') == TASK_SHA,'Task_changed_during_Selected')
        summary.update(status='PASSED',job_id=str(result.id),trial_uuid=str(trial.id),
            trial_name=trial.trial_name,trial_dir=str(trial_dir),job_dir=str(job_dir),gpu_job_id=job_id,
            trusted_receipt=str(trusted),trusted_receipt_sha256=hashlib.sha256(trusted_bytes).hexdigest(),
            reward=reward,scoring_seconds=raw['receipt']['scoring_seconds'],native_exception=None,
            actor_unchanged_Starter=True,Task_unchanged=True,full_images=16,nfe_per_image=100,
            injection=injection,runtimes=runtimes)
    except BaseException as exc:
        failed=exc;summary.update(status='FAILED_PRESERVED',failure_type=type(exc).__name__,
                                 failure=str(exc),job_dir=str(job_dir))
    finally:
        summary['finished_at']=utc();dump(evidence/'selected-summary.json',summary)
        if job_dir.exists():
            inv={p.relative_to(job_dir).as_posix():{'sha256':sha_file(p),'bytes':p.stat().st_size}
                 for p in sorted(job_dir.rglob('*')) if p.is_file() and not p.is_symlink()}
            dump(evidence/'native-job-inventory.json',inv)
        seal_inventory(evidence)
    print(json.dumps(summary,sort_keys=True,allow_nan=False))
    return 1 if failed else 0


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-manifest-sha256',required=True)
    p.add_argument('--validate-only',action='store_true')
    sys.exit(asyncio.run(main(p.parse_args())))

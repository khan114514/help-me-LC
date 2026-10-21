"""Expert-only fresh Harbor NOP. Validation does not construct a Trial/container."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import uuid

TASK_SHA = '90bb7746559319dc6ce29dbbfae946f9a6b00694ef04b25d267f7def8c8249cb'
TASK = Path(('' + ('/' + 'root/') + 'rfsteps-v341-build-check-20261004'))
SOCKET_ROOT = Path(('' + ('/' + 'root/') + 'rfsteps-v341-rpc-20261004/sockets'))
TRUSTED_RECEIPTS = Path(('' + ('/' + 'root/') + 'rfsteps-v341-trusted-rpc-receipts-20261004'))
IDENTITY = Path(('' + ('/' + 'root/') + 'rfsteps-v341-rpc-20261004/gateway-identity.json'))
GATEWAY_SHA = '79532001e77d0e680ec8dad75421c3e2ef251227e250fc15338f241e94ee7928'
NODE_SHA = 'a2a74cba18f963bf00245edde3452535627888905664e63007434076828ff427'
METHOD_SHA = '2555f26dd588cf7d8a57091b61bedd41971e74e112a6edd5e659db4ce8399e3c'
SOLVE_SHA = '245736edfc8c8c905fad03f336e521cb6192328b3ad1ade9eab6ed893b03ed58'
SOURCE = Path(__file__).resolve().parent


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def check_socket(path, owner=0, mode=0o600):
    path = Path(path)
    for ancestor in [path.parent, *path.parent.parents]:
        require(not ancestor.is_symlink(), 'socket_ancestor_symlink')
    s = path.lstat()
    require(stat.S_ISSOCK(s.st_mode), 'socket_source_is_not_UDS')
    require(s.st_uid == owner and stat.S_IMODE(s.st_mode) == mode, 'socket_owner_or_mode_invalid')
    return {'path': str(path), 'inode': s.st_ino, 'device': s.st_dev,
            'uid': s.st_uid, 'mode': stat.S_IMODE(s.st_mode)}


def verify_tree(task, freeze):
    actual = {}
    for p in sorted(Path(task).rglob('*')):
        require(not p.is_symlink(), 'task_symlink_rejected')
        if p.is_file():
            actual[p.relative_to(task).as_posix()] = sha_file(p)
        else:
            require(p.is_dir(), 'task_nonregular_rejected')
    require(freeze['task_sha256'] == TASK_SHA and freeze['file_count'] == 63,
            'freeze_identity_invalid')
    require(actual == freeze['files'], 'frozen_Task_file_set_or_bytes_differ')
    return actual


def verify_gateway(identity):
    require(identity.get('schema_version') == 1 and identity.get('source_sha256') == GATEWAY_SHA,
            'gateway_identity_source_invalid')
    uuid.UUID(identity['owner_id'])
    require(sha_file(identity['source_path']) == GATEWAY_SHA, 'gateway_source_bytes_drift')
    pid = identity['pid']
    require(type(pid) is int and pid > 1, 'gateway_pid_invalid')
    tokens = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    require(int(tokens[19]) == identity['start_ticks'], 'gateway_process_birth_changed')
    return identity


def validate_result(raw, profile, reward, status, metrics):
    require(raw.get('status') == 'COMPLETE' and raw.get('evaluation_completed') is True
            and raw.get('role') == 'formal', 'formal_worker_not_complete')
    job_id = str(uuid.UUID(raw['job_id']))
    require(raw['job_id'] == job_id, 'GPU_job_id_not_canonical')
    r, m = raw['receipt'], raw['metrics']
    require(r.get('control_task_checksum') == TASK_SHA and r.get('nodes_sha256') == NODE_SHA,
            'formal_Task_or_Starter_nodes_mismatch')
    require(type(r.get('exit_code')) is int and r['exit_code'] == 0
            and type(r.get('scoring_seconds')) in (int, float)
            and math.isfinite(r['scoring_seconds']) and r['scoring_seconds'] > 0,
            'GPU_process_not_completed')
    for key in ['worker_sha256', 'scorer_sha256', 'repo_sha256', 'anchors_sha256',
                'weights_sha256', 'weight_support_sha256', 'asset_sha256', 'protocol']:
        require(r.get(key) == profile[key], 'numeric_identity_mismatch_' + key)
    # Package versions/actual CUDA availability are independently recorded by the worker.
    require(r.get('environment') == profile['environment'], 'numerical_environment_drift')
    require(m.get('split') == 'full' and m.get('num_steps') == 25 and m.get('nfe_per_image') == 100,
            'full_scoring_protocol_mismatch')
    require(m['overall']['n'] == 16 and m['public']['n'] == 12 and m['hidden']['n'] == 4
            and len(m['per_image']) == 16 and len(r['png_sha256']) == 16, 'full_image_count_mismatch')
    require(status.get('status') == 'COMPLETE' and status.get('evaluation_completed') is True
            and status.get('split') == 'full' and status.get('gpu_job_id') == job_id
            and status.get('method_sha256') == METHOD_SHA, 'Verifier_status_binding_mismatch')
    require(metrics['method_sha256'] == METHOD_SHA and metrics['schedule_bridge_sha256'] == m['method_sha256'],
            'actual_Starter_source_binding_mismatch')
    require(metrics['overall'] == m['overall'] and metrics['per_image'] == m['per_image'],
            'Verifier_metrics_differ_from_GPU_receipt')
    for key, expected in [('reward', m['score']), ('psnr', m['overall']['psnr']),
                          ('ssim', m['overall']['ssim']), ('nfe_per_image', 100)]:
        require(type(reward.get(key)) in (int, float) and math.isfinite(reward[key])
                and reward[key] == expected, 'Verifier_reward_drift_' + key)
    return job_id


def seal_inventory(root):
    files = {}
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name != 'preservation-manifest.json':
            require(not p.is_symlink(), 'evidence_symlink')
            p.chmod(0o600)
            files[p.relative_to(root).as_posix()] = {'sha256': sha_file(p), 'bytes': p.stat().st_size}
        elif p.is_dir():
            p.chmod(0o700)
    dump(root / 'preservation-manifest.json', {'schema_version': 1, 'files': files,
        'research_credit_seconds': 0, 'model_calls': 0})


async def main_async(args):
    os.umask(0o077)
    require(os.geteuid() == 0, 'expert_host_root_required')
    manifest = SOURCE / 'source-pins.json'
    require(sha_file(manifest) == args.source_manifest_sha256, 'source_manifest_pin_mismatch')
    source_pins = json.loads(manifest.read_text())
    for name, expected in source_pins['files'].items():
        require(sha_file(SOURCE / name) == expected, 'expert_runtime_source_drift_' + name)
    config_raw = json.loads((SOURCE / 'job-config.json').read_text())
    freeze = json.loads((SOURCE / 'task-freeze.json').read_text())
    profile = json.loads((SOURCE / 'numerical-identity-pins.json').read_text())
    tree = verify_tree(TASK, freeze)
    from dirhash import dirhash
    require(dirhash(TASK, 'sha256') == TASK_SHA, 'Harbor_Task_dirhash_mismatch')
    identity = verify_gateway(json.loads(IDENTITY.read_text()))
    sockets = [check_socket(SOCKET_ROOT / name, mode=mode)
               for name, mode in [('public.sock', 0o666), ('formal.sock', 0o600)]]
    require(TRUSTED_RECEIPTS.is_dir() and not TRUSTED_RECEIPTS.is_symlink()
            and stat.S_IMODE(TRUSTED_RECEIPTS.stat().st_mode) == 0o700,
            'trusted_receipt_root_not_private')
    from harbor.models.job.config import JobConfig
    config = JobConfig.model_validate(config_raw)
    require(len(config.agents) == 1 and config.agents[0].name == 'nop'
            and not config.agents[0].import_path and not config.agents[0].model_name
            and config.user_agent is None and not config.install_only,
            'native_NOP_config_required')
    require(config.retry.max_retries == 0 and len(config.tasks) == 1
            and config.tasks[0].path == TASK and not config.verifier.disable,
            'fresh_single_native_verifier_trial_required')
    evidence = Path(config_raw['environment']['kwargs']['nop_evidence_root'])
    job_dir = config.jobs_dir / config.job_name
    require(not job_dir.exists() and not evidence.exists(), 'attempt_or_job_already_exists')
    if args.validate_only:
        print(json.dumps({'validation': 'PASSED', 'Task': TASK_SHA, 'files': len(tree),
                          'sockets': sockets, 'gateway': identity, 'constructed_Trial': False,
                          'model_calls': 0, 'GPU_calls': 0}, sort_keys=True))
        return 0
    evidence.mkdir(parents=True, mode=0o700)
    started = utc()
    dump(evidence / 'preflight.json', {'started_at': started, 'task_checksum': TASK_SHA,
        'files': tree, 'sockets': sockets, 'gateway': identity,
        'source_manifest_sha256': args.source_manifest_sha256, 'research_credit_seconds': 0})
    failure = None
    summary = {'status': 'INCOMPLETE', 'task_checksum': TASK_SHA, 'started_at': started,
               'native_agent': 'nop', 'model_calls': 0, 'research_credit_seconds': 0}
    try:
        from harbor.job import Job
        job = await Job.create(config)
        result = await job.run()
        dump(evidence / 'returned-job-result.json', result.model_dump(mode='json'))
        require(len(result.trial_results) == 1, 'unexpected_trial_count')
        trial = result.trial_results[0]
        require(trial.exception_info is None and trial.finished_at is not None,
                'actual_Harbor_Trial_exception_or_incomplete')
        require(trial.agent_info.name == 'nop' and trial.agent_info.model_info is None,
                'actual_agent_is_not_native_NOP')
        trial_dir = job_dir / trial.trial_name
        v = trial_dir / 'verifier'
        raw = json.loads((v / 'gpu_receipt.json').read_text())
        reward = json.loads((v / 'reward.json').read_text())
        status = json.loads((v / 'evaluation_status.json').read_text())
        metrics = json.loads((v / 'metrics.json').read_text())
        job_id = validate_result(raw, profile, reward, status, metrics)
        trusted = TRUSTED_RECEIPTS / (job_id + '.json')
        require(stat.S_IMODE(trusted.lstat().st_mode) == 0o600 and not trusted.is_symlink(),
                'trusted_result_not_regular_private')
        trusted_bytes = trusted.read_bytes()
        require(json.loads(trusted_bytes) == raw, 'trusted_mirror_not_full_object_equal')
        fd = os.open(evidence / 'trusted-worker-result.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(trusted_bytes); stream.flush(); os.fsync(stream.fileno())
        solution = trial_dir / 'artifacts' / 'solution'
        require({p.name for p in solution.iterdir()} == {'method.py', 'solve.sh'}, 'native_artifact_not_exact_two')
        require(sha_file(solution / 'method.py') == METHOD_SHA and sha_file(solution / 'solve.sh') == SOLVE_SHA,
                'native_artifact_not_actual_Starter')
        reports = [json.loads(p.read_text()) for p in (evidence / 'environments').rglob('*.json')]
        runtime = [p for p in reports if p.get('native_nop') is True]
        require(len(runtime) == 2 and {p['role'] for p in runtime} == {'agent', 'verifier'},
                'separate_actual_runtime_records_missing')
        transfers = [p for p in reports if p.get('source') == '/workspace/solution' and p.get('kind') == 'dir']
        require(len(transfers) >= 1 and all(p.get('status') == 'COMPLETE'
                and p['live_before_inventory_sha256'] == p['live_after_inventory_sha256']
                == p['host_inventory_sha256'] and p['regular_files'] == 2 for p in transfers),
                'native_final_live_transfer_not_proven')
        require(trial.verifier_result is not None and trial.verifier_result.rewards == reward,
                'Harbor_reward_not_exact_Verifier_reward')
        verify_tree(TASK, freeze)
        require(dirhash(TASK, 'sha256') == TASK_SHA, 'Task_changed_during_NOP')
        summary.update(status='PASSED', job_id=str(result.id), job_dir=str(job_dir),
                       trial_uuid=str(trial.id), trial_name=trial.trial_name, trial_dir=str(trial_dir),
                       gpu_job_id=job_id, reward=reward, scoring_seconds=raw['receipt']['scoring_seconds'],
                       trusted_receipt=str(trusted), trusted_receipt_sha256=hashlib.sha256(trusted_bytes).hexdigest(),
                       actual_exception=None, runtimes=runtime,
                       full_count=16, nfe_per_image=100, solution_source_sha256=METHOD_SHA,
                       solver_sha256=SOLVE_SHA, transfer_report_count=len(transfers))
    except BaseException as exc:
        failure = exc
        summary.update(status='FAILED_PRESERVED', failure_type=type(exc).__name__, failure=str(exc),
                       job_dir=str(job_dir))
    finally:
        summary['finished_at'] = utc()
        dump(evidence / 'nop-summary.json', summary)
        # Preserve native Job separately; no modification of native logs or results.
        if job_dir.exists():
            native_inventory = {p.relative_to(job_dir).as_posix(): {'sha256': sha_file(p), 'bytes': p.stat().st_size}
                                for p in sorted(job_dir.rglob('*')) if p.is_file() and not p.is_symlink()}
            dump(evidence / 'native-job-inventory.json', native_inventory)
        seal_inventory(evidence)
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return 0 if failure is None else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-manifest-sha256', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args)))

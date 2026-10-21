#!/usr/bin/env python3
"""Durable AutoResearch repair-until-consensus orchestrator (standard library)."""
import argparse
import datetime as dt
import fcntl
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path
from common import clean_env, detach, digest, evidence_path, object_digest, read, reap, tree_digest, write

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
PHASES = ['prepare', 'br', 'preflight_nop', 'dual', 'finalize', 'nop', 'stability', 'package', 'qa']
DRIVERS = ['prepare', 'br', 'preflight_nop', 'dual_a', 'dual_b', 'finalize', 'nop', 'stability',
           'package', 'qa_a', 'qa_b', 'repair']


def verify_assets():
    manifest = read(SKILL / 'assets/qa-release.json')
    for relative, expected in manifest['files'].items():
        if digest(SKILL / 'assets/qa-skills' / relative) != expected:
            raise ValueError('pinned QA asset changed')


def validate_plan(plan, directory):
    if plan.get('schema_version') != 1:
        raise ValueError('unsupported plan schema')
    root = Path(plan['task_root'])
    if not root.is_absolute() or not root.is_dir():
        raise ValueError('task_root must be an existing absolute directory')
    directory = Path(directory).resolve()
    if root.resolve() == directory or root.resolve() in directory.parents or directory in root.resolve().parents:
        raise ValueError('task and private management directories must be disjoint')
    contract = plan['contract']
    if contract.get('qa_version') != '0.3.4':
        raise ValueError('this manager pins QA 0.3.4')
    seconds = contract.get('effective_seconds_per_track', 36000)
    exception = contract.get('seven_hour_exception', {})
    minimum = 25200 if all(exception.get(k) is True for k in
                           ('nontraining', 'short_iterations', 'continuing_directions')) else 36000
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not math.isfinite(seconds) or seconds < minimum:
        raise ValueError('invalid effective research threshold')
    stability = contract.get('stability_seconds', 43200)
    if isinstance(stability, bool) or not isinstance(stability, (int, float)) or not math.isfinite(stability) or stability < 43200:
        raise ValueError('stability must be at least 12h')
    identities = []
    for row in plan['reviewers']:
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in ('provider', 'model', 'version')):
            raise ValueError('reviewer identity is incomplete')
        identities.append(tuple(row[k] for k in ('provider', 'model', 'version')))
    if len(identities) != 2 or len(set(identities)) != 2:
        raise ValueError('exactly two different reviewer identities are required')
    for key in DRIVERS:
        argv = plan['drivers'].get(key)
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            raise ValueError('missing executable driver: ' + key)
        if not shutil.which(argv[0]):
            raise ValueError('driver executable does not exist: ' + key)
    for field, default in [('retry_seconds', 60), ('job_timeout_seconds', 172800)]:
        value = plan.get(field, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('invalid ' + field)


def event(directory, kind, **data):
    with (directory / 'events.jsonl').open('a') as f:
        f.write(__import__('json').dumps({'epoch': time.time(), 'kind': kind, **data}, ensure_ascii=False) + '\n')


def save(directory, state):
    state['updated_epoch'] = time.time()
    write(directory / 'state.json', state)
    write(directory / 'handoff.json', {k: state[k] for k in
          ('status', 'phase', 'revision', 'jobs', 'completed', 'failures', 'artifact', 'updated_epoch')})


def spawn(directory, plan, state, stage):
    identifier = uuid.uuid4().hex
    job = directory / 'jobs' / identifier
    job.mkdir(parents=True)
    request = {'job_id': identifier, 'stage': stage, 'revision': state['revision'],
               'task_root': plan['task_root'], 'task_sha256': state['task_sha256'],
               'contract': plan['contract'], 'contract_sha256': state['contract_sha256'],
               'goal': plan.get('goal', 'Complete the authorized AutoResearch task under the frozen contract.'),
               'receipt_path': str(job / 'receipt.json')}
    if stage.startswith('qa_'):
        # Neither reviewer receives task roots, author goals, research contract prose or history.
        for field in ('task_root', 'task_sha256', 'goal', 'contract'):
            request.pop(field, None)
        request['artifact'] = state['artifact']
        request['reviewer'] = plan['reviewers'][0 if stage == 'qa_a' else 1]
        request['session_id'] = identifier
    else:
        request['upstream'] = state['completed']
        request['failures'] = state['failures'] if stage == 'repair' else []
        if stage == 'repair':
            request['repair_before_sha256'] = tree_digest(plan['task_root'])
    write(job / 'request.json', request)
    write(job / 'execution.json', {'argv': plan['drivers'][stage] + ['--request', str(job / 'request.json')],
                                  'timeout_seconds': plan.get('job_timeout_seconds', 172800)})
    state['jobs'][stage] = {'id': identifier, 'directory': str(job), 'created_epoch': time.time()}
    save(directory, state)  # Persist intent before launching; workers deduplicate on their lock.
    detach([sys.executable, str(HERE / 'job_worker.py'), '--job', str(job)])
    event(directory, 'job_dispatched', stage=stage, job_id=identifier, revision=state['revision'])


def validate_duration(data, actual):
    intervals = data['intervals']
    total, end = 0.0, -float('inf')
    for row in sorted(intervals, key=lambda x: x['start_epoch']):
        a, b = row['start_epoch'], row['end_epoch']
        if not all(isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) for x in (a, b)):
            raise ValueError('nonfinite research interval')
        if b < a or a < end or a < actual['started_epoch'] - 1 or b > actual['ended_epoch'] + 1:
            raise ValueError('invalid/overlapping/out-of-run research intervals')
        end = b
        if row['kind'] == 'research':
            total += b - a
    if abs(total - data['effective_seconds']) > 1:
        raise ValueError('effective time does not match observed intervals')
    return total


def validate_receipt(plan, state, stage, job):
    directory = Path(job['directory'])
    actual = read(directory / 'exit.json')
    r = read(directory / 'receipt.json')
    if r.get('revision') != state['revision'] or r.get('contract_sha256') != state['contract_sha256']:
        raise ValueError('receipt belongs to another revision/contract')
    status = r.get('status')
    if status not in ('PASS', 'FAIL', 'RETRY', 'NEEDS_INPUT'):
        raise ValueError('invalid receipt status')
    if status != 'PASS':
        return status, {'job': str(directory), 'stage': stage, 'receipt': str(directory / 'receipt.json')}
    if actual['exit_code'] != 0 or actual['timed_out']:
        raise ValueError('process failure cannot pass')
    if not isinstance(r.get('evidence'), list) or not r['evidence']:
        raise ValueError('PASS requires actual evidence')
    files = {relative: evidence_path(directory, relative) for relative in r['evidence']}
    d = r.get('details', {})
    def checked(relative):
        if relative not in files:
            raise ValueError('stage evidence missing from evidence list')
        return files[relative]
    if stage.startswith('dual_'):
        seconds = validate_duration(read(checked(d['duration_evidence'])), actual)
        if abs(seconds - d['effective_seconds']) > 1 or seconds < plan['contract'].get('effective_seconds_per_track', 36000):
            raise ValueError('insufficient or conflicting effective research time')
    elif stage in ('nop', 'preflight_nop'):
        if set(d['trial_evidence']) != {'config', 'result', 'reward', 'log'}:
            raise ValueError('NOP requires config, result, reward and log')
        for p in d['trial_evidence'].values():
            checked(p)
    elif stage == 'finalize':
        validations = d['final_validations']
        if set(validations) != {'a', 'b'} or validations['a']['evidence'] == validations['b']['evidence']:
            raise ValueError('each final lane requires an independent validation')
        for row in validations.values():
            original = read(checked(row['evidence']))
            if len(row['method_sha256']) != 64 or row['contract_sha256'] != state['contract_sha256']:
                raise ValueError('invalid final method binding')
            if any(original.get(k) != row[k] for k in ('method_sha256', 'contract_sha256')) or original.get('status') != 'PASS':
                raise ValueError('final validation evidence mismatch')
    elif stage == 'stability':
        obs = read(checked(d['observation']))
        samples = obs['samples']
        if len(samples) < 2 or obs['status'] != 'PASS' or not obs.get('container_id'):
            raise ValueError('missing actual container observations')
        interval = obs['interval_seconds']
        if not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0 or interval > 60:
            raise ValueError('invalid stability observation interval')
        required = plan['contract'].get('stability_seconds', 43200)
        if samples[-1]['epoch'] - samples[0]['epoch'] < required:
            raise ValueError('stability interval is shorter than contract')
        for previous, sample in zip(samples, samples[1:]):
            if not 0 < sample['epoch'] - previous['epoch'] <= max(5, 3 * interval):
                raise ValueError('stability has an observation gap')
        for sample in samples:
            if sample.get('healthy') is not True or sample.get('running') is not True or sample.get('restart_count') != 0:
                raise ValueError('container health/stability failure')
            if sample.get('started_at') != samples[0]['started_at'] or sample.get('container_id') != obs['container_id']:
                raise ValueError('container restarted or changed')
            if not actual['started_epoch'] - 1 <= sample['epoch'] <= actual['ended_epoch'] + 1:
                raise ValueError('stability evidence lies outside this job')
    elif stage == 'package':
        artifact = checked(d['artifact'])
        if not zipfile.is_zipfile(artifact):
            raise ValueError('package is not a ZIP')
        with zipfile.ZipFile(artifact) as z:
            if not z.namelist() or z.testzip() is not None:
                raise ValueError('package is empty or corrupt')
        release = directory / 'frozen-submission.zip'
        if not release.exists():
            shutil.copyfile(artifact, release)
            release.chmod(0o400)
        if digest(release) != digest(artifact):
            raise ValueError('immutable submission mismatch')
        state['artifact'] = {'path': str(release), 'sha256': digest(release), 'revision': state['revision']}
    elif stage.startswith('qa_'):
        report = checked(d['report'])
        session = read(checked(d['session_evidence']))
        identity = plan['reviewers'][0 if stage == 'qa_a' else 1]
        if session.get('session_id') != job['id'] or session.get('fresh_session') is not True:
            raise ValueError('missing new-session launch provenance')
        if session.get('artifact_sha256') != state['artifact']['sha256'] or session.get('reviewer') != identity:
            raise ValueError('QA launch identity/artifact mismatch')
        r['report_path'] = str(report)
        # Report FAIL is meaningful QA output, not a driver infrastructure failure.
    elif stage == 'repair':
        request = read(directory / 'request.json')
        if tree_digest(plan['task_root']) == request['repair_before_sha256']:
            raise ValueError('repair produced no authoring artifact change')
    r['observed'] = actual
    r['evidence_sha256s'] = {p: digest(f) for p, f in files.items()}
    r['job_directory'] = str(directory)
    return 'PASS', r


def verify_report(report, identity, session, artifact):
    qa_run = report['qa_run']
    if report['source']['sha256'] != artifact['sha256'] or qa_run['artifact_sha256'] != artifact['sha256']:
        raise ValueError('QA report is not for the current immutable ZIP')
    if qa_run['reviewer'] != {**identity, 'session_id': session}:
        raise ValueError('QA report reviewer does not match the actual dispatch')
    required = [('checks', {f'QA{i:02}' for i in range(1, 22)}),
                ('content_gates', {f'G{i:02}' for i in range(1, 4)}),
                ('harbor', {f'H{i:02}' for i in range(1, 7)})]
    for section, ids in required:
        rows = report[section] if section == 'checks' else report[section]['checks']
        if len(rows) != len(ids) or {x['id'] for x in rows} != ids:
            raise ValueError('QA report missing/duplicating required checks')
        if report['summary']['decision'] == 'PASS' and any(x['status'] not in ('pass', 'not_applicable') for x in rows):
            raise ValueError('PASS report contains nonpassing checks')


def consensus(directory, state, plan):
    artifact = state['artifact']
    if not artifact or digest(artifact['path']) != artifact['sha256']:
        raise ValueError('current ZIP changed after freeze')
    paths = []
    for index, key in enumerate(('qa_a', 'qa_b')):
        entry = state['completed'][key]
        path = Path(entry['report_path'])
        rel = str(path.relative_to(entry['job_directory']))
        if digest(path) != entry['evidence_sha256s'][rel]:
            raise ValueError('QA report changed after completion')
        request = read(Path(entry['job_directory']) / 'request.json')
        verify_report(read(path), plan['reviewers'][index], request['job_id'], artifact)
        paths.append(path)
    qa_scripts = SKILL / 'assets/qa-skills/autoresearch-task-qa/scripts'
    sys.path.insert(0, str(qa_scripts))
    from qa_consensus import aggregate
    result, passed = aggregate(paths)
    output = directory / 'consensus' / (f"r{state['revision']:06}-" + uuid.uuid4().hex + '.json')
    write(output, result)
    state['consensus'] = str(output)
    return passed


def fail(directory, state, stage, details, retry_seconds):
    state['failures'].append({'revision': state['revision'], 'stage': stage, **details})
    state['jobs'] = {}
    state['phase'] = 'repair'
    state['next_dispatch_epoch'] = time.time() + retry_seconds
    event(directory, 'repair_required', revision=state['revision'], stage=stage)


def tick(directory):
    reap()
    directory = Path(directory).resolve()
    with (directory / 'manager.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state, plan = read(directory / 'state.json'), read(directory / 'plan.json')
        if state['status'] != 'RUNNING':
            return state
        try:
            verify_assets()
        except (OSError, ValueError):
            state['status'] = 'NEEDS_INPUT'
            state['input_reason'] = 'Pinned independent QA rules changed or disappeared; restore the approved release.'
            save(directory, state)
            return state
        if object_digest(plan) != state['plan_sha256']:
            state['status'] = 'NEEDS_INPUT'
            state['input_reason'] = 'Frozen plan changed; restore it or establish a new run.'
            save(directory, state)
            return state
        deadline = plan.get('deadline_utc')
        if deadline and dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(deadline.replace('Z', '+00:00')):
            state['status'], state['input_reason'] = 'NEEDS_INPUT', 'Authorized deadline reached.'
            save(directory, state)
            return state
        if time.time() < state.get('next_dispatch_epoch', 0):
            return state
        phase = state['phase']
        stages = ['dual_a', 'dual_b'] if phase == 'dual' else ['qa_a', 'qa_b'] if phase == 'qa' else [phase]
        # Wait for all concurrent jobs before handling failures. Never orphan a peer lane.
        for stage in stages:
            if stage not in state['jobs']:
                spawn(directory, plan, state, stage)
        exits = [Path(state['jobs'][s]['directory']) / 'exit.json' for s in stages]
        if not all(p.exists() for p in exits):
            for stage, path in zip(stages, exits):
                if path.exists():
                    continue
                job = state['jobs'][stage]
                folder = Path(job['directory'])
                heartbeat = folder / 'heartbeat.json'
                last = read(heartbeat)['epoch'] if heartbeat.exists() else job['created_epoch']
                if time.time() - last > 60:
                    started = folder / 'started.json'
                    if not started.exists():
                        # Replay persisted intent. The worker's unique job lock makes this
                        # safe even if an earlier launch is delayed rather than absent.
                        detach([sys.executable, str(HERE / 'job_worker.py'), '--job', str(folder)])
                        job['created_epoch'] = time.time()
                        event(directory, 'unstarted_job_replayed', job_id=job['id'])
                        save(directory, state)
                        continue
                    pid = read(started)['pid']
                    try:
                        os.kill(pid, 0)
                        # A live wrapper may have been suspended with the machine.
                        continue
                    except ProcessLookupError:
                        child = folder / 'child.json'
                        if child.exists():
                            try:
                                os.kill(read(child)['pid'], 0)
                                continue  # Preserve in-flight local child; never duplicate.
                            except ProcessLookupError:
                                pass
                        write(path, {'exit_code': -1, 'started_epoch': read(started)['epoch'],
                              'ended_epoch': time.time(), 'timed_out': False,
                              'error_type': 'LostWorkerAndChild'})
                        event(directory, 'lost_job_closed_as_failure', job_id=job['id'])
                        continue
                    except PermissionError:
                        pass
                    # Fail closed on ambiguous lost wrappers: do not duplicate remote workloads.
                    state['status'] = 'NEEDS_INPUT'
                    state['input_reason'] = 'Worker heartbeat lost; inspect existing child/remote job before resuming.'
                    event(directory, 'worker_lost', job_id=job['id'])
                    save(directory, state)
                    return state
            return state
        outcomes = []
        for stage in stages:
            try:
                status, data = validate_receipt(plan, state, stage, state['jobs'][stage])
            except Exception as exc:
                status, data = 'FAIL', {'job': state['jobs'][stage]['directory'], 'error_type': type(exc).__name__}
            outcomes.append((stage, status, data))
        for stage, status, data in outcomes:
            if status == 'NEEDS_INPUT':
                state['status'], state['input_reason'] = 'NEEDS_INPUT', 'Driver requires external input; see private receipt.'
                save(directory, state)
                return state
        for stage, status, data in outcomes:
            if status == 'RETRY':
                state['jobs'] = {}
                state['next_dispatch_epoch'] = time.time() + plan.get('retry_seconds', 60)
                event(directory, 'retry', stage=stage)
                save(directory, state)
                return state
            if status != 'PASS':
                fail(directory, state, stage, data, plan.get('retry_seconds', 60))
                save(directory, state)
                return state
        if phase not in ('prepare', 'repair') and tree_digest(plan['task_root']) != state['task_sha256']:
            fail(directory, state, phase, {'error_type': 'TaskChangedOutsideRepair'}, plan.get('retry_seconds', 60))
            save(directory, state)
            return state
        # repair intentionally replaces a rejected revision; its invalid historical
        # evidence remains archived, but must not prevent a new revision being born.
        if phase != 'repair':
            for previous_stage, previous in state['completed'].items():
                for relative, expected in previous['evidence_sha256s'].items():
                    try:
                        valid = digest(evidence_path(previous['job_directory'], relative)) == expected
                    except (OSError, ValueError):
                        valid = False
                    if not valid:
                        fail(directory, state, previous_stage, {'error_type': 'PriorEvidenceChanged'}, plan.get('retry_seconds', 60))
                        save(directory, state)
                        return state
        for stage, _, data in outcomes:
            state['completed'][stage] = data
        state['jobs'] = {}
        if phase == 'repair':
            state['revision'] += 1
            state['completed'], state['artifact'], state['consensus'] = {}, None, None
            state['phase'] = 'prepare'
            state['task_sha256'] = tree_digest(plan['task_root'])
            event(directory, 'revision_created', revision=state['revision'])
        elif phase == 'qa':
            try:
                passed = consensus(directory, state, plan)
            except Exception as exc:
                passed = False
                state['failures'].append({'revision': state['revision'], 'stage': 'consensus',
                                          'error_type': type(exc).__name__})
            if passed:
                state['status'] = 'DONE'
                event(directory, 'two_passes', revision=state['revision'], sha256=state['artifact']['sha256'])
            else:
                fail(directory, state, 'qa', {'reports': [state['completed'][s]['report_path'] for s in stages],
                                             'consensus': state.get('consensus')}, plan.get('retry_seconds', 60))
        else:
            if phase == 'prepare':
                state['task_sha256'] = tree_digest(plan['task_root'])
            state['phase'] = PHASES[PHASES.index(phase) + 1]
        save(directory, state)
        return state


def run(directory, poll):
    directory = Path(directory).resolve()
    with (directory / 'daemon.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        write(directory / 'daemon.json', {'pid': os.getpid(), 'epoch': time.time()})
        while True:
            try:
                state = tick(directory)
            except Exception as exc:
                with (directory / 'manager.lock').open('a') as state_lock:
                    fcntl.flock(state_lock, fcntl.LOCK_EX)
                    state = read(directory / 'state.json')
                    state['status'] = 'NEEDS_INPUT'
                    state['input_reason'] = 'Supervisor error (' + type(exc).__name__ + '); original state and jobs preserved.'
                    save(directory, state)
                    event(directory, 'supervisor_error', error_type=type(exc).__name__)
            if state['status'] in ('DONE', 'NEEDS_INPUT'):
                return 0 if state['status'] == 'DONE' else 2
            time.sleep(poll)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'doctor', 'start', 'run', 'tick', 'status', 'pause', 'resume'])
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--poll-seconds', type=float, default=5)
    args = parser.parse_args()
    directory = args.run_dir.resolve()
    if not 0 < args.poll_seconds <= 60:
        parser.error('poll interval must be in (0,60]')
    if args.command == 'init':
        if directory.exists() and any(directory.iterdir()):
            parser.error('run directory must be new/empty')
        plan = read(args.plan)
        validate_plan(plan, directory)
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
        write(directory / 'plan.json', plan)
        state = {'status': 'RUNNING', 'phase': 'prepare', 'revision': 1, 'jobs': {}, 'completed': {},
                 'failures': [], 'artifact': None, 'consensus': None, 'plan_sha256': object_digest(plan),
                 'contract_sha256': object_digest(plan['contract']), 'task_sha256': tree_digest(plan['task_root'])}
        save(directory, state)
        event(directory, 'initialized', revision=1)
    elif args.command == 'doctor':
        validate_plan(read(directory / 'plan.json'), directory)
        verify_assets()
        print('{"configuration":"PASS","runtime":"NOT_YET_VERIFIED"}')
        return 0
    elif args.command == 'run':
        return run(directory, args.poll_seconds)
    elif args.command == 'start':
        detach([sys.executable, str(HERE / 'manager.py'), 'run', '--run-dir', str(directory),
                '--poll-seconds', str(args.poll_seconds)])
    elif args.command == 'tick':
        tick(directory)
    elif args.command in ('pause', 'resume'):
        with (directory / 'manager.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = read(directory / 'state.json')
            if state['status'] != 'DONE':
                if args.command == 'resume' and state['status'] == 'NEEDS_INPUT':
                    # Completed NEEDS_INPUT receipts cannot become successful just
                    # because credentials were restored. Dispatch a fresh attempt.
                    if state['jobs'] and all((Path(j['directory']) / 'exit.json').exists() for j in state['jobs'].values()):
                        event(directory, 'input_resolved_reattempt', job_ids=[j['id'] for j in state['jobs'].values()])
                        state['jobs'] = {}
                    state.pop('input_reason', None)
                state['status'] = 'PAUSED' if args.command == 'pause' else 'RUNNING'
                save(directory, state)
                event(directory, args.command)
        if args.command == 'resume' and state['status'] == 'RUNNING':
            detach([sys.executable, str(HERE / 'manager.py'), 'run', '--run-dir', str(directory),
                    '--poll-seconds', str(args.poll_seconds)])
    state = read(directory / 'state.json')
    print(__import__('json').dumps({k: state.get(k) for k in ('status', 'phase', 'revision', 'artifact', 'consensus', 'input_reason')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

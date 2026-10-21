"""Behavioral tests use simulated actors and reduced test-only clocks in fixtures.

No production CLI accepts the reduced contracts used by make_run().
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
import manager
from common import clean_env, digest, evidence_path, object_digest, read, tree_digest, write

HERE = Path(__file__).resolve().parent


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.task = self.root / 'task'
        self.task.mkdir()
        (self.task / 'task.txt').write_text('simulation\n')
        self.run_dir = self.root / 'private'
        self.run_dir.mkdir()

    def plan(self):
        return {'schema_version': 1, 'task_root': str(self.task), 'goal': 'SIMULATED FRAMEWORK TEST',
                'contract': {'qa_version': '0.3.4', 'effective_seconds_per_track': 36000, 'stability_seconds': 43200},
                'reviewers': [{'provider': 'TEST-A', 'model': 'SIMULATED-A', 'version': 'test'},
                              {'provider': 'TEST-B', 'model': 'SIMULATED-B', 'version': 'test'}],
                'drivers': {s: [sys.executable, str(HERE / 'fixture_driver.py')] for s in manager.DRIVERS},
                'retry_seconds': 0.01, 'job_timeout_seconds': 20}

    def make_run(self, delay=0.02):
        plan = self.plan()
        # Test fixture explicitly bypasses CLI initialization to compress clocks.
        plan['contract']['effective_seconds_per_track'] = 0.01
        plan['contract']['stability_seconds'] = 0.03
        for argv in plan['drivers'].values():
            argv += ['--delay', str(delay)]
        state = {'status': 'RUNNING', 'phase': 'prepare', 'revision': 1, 'jobs': {}, 'completed': {},
                 'failures': [], 'artifact': None, 'consensus': None,
                 'plan_sha256': object_digest(plan), 'contract_sha256': object_digest(plan['contract']),
                 'task_sha256': tree_digest(self.task)}
        write(self.run_dir / 'plan.json', plan)
        manager.save(self.run_dir, state)
        return plan

    def until(self, condition, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            state = manager.tick(self.run_dir)
            if condition(state):
                return state
            if state['status'] == 'NEEDS_INPUT':
                self.fail(json.dumps(state))
            time.sleep(0.03)
        self.fail('condition timed out: ' + json.dumps(read(self.run_dir / 'state.json')))

    def test_failed_qa_is_repaired_and_both_reviews_are_new(self):
        self.make_run()
        final = self.until(lambda s: s['status'] == 'DONE')
        self.assertEqual(final['revision'], 2)
        self.assertTrue((self.task / 'fix.txt').exists())
        consensus = read(final['consensus'])
        self.assertEqual(consensus['status'], 'PASS')
        self.assertFalse(consensus['unresolved_disagreements'])
        sessions, report_versions, inputs = [], [], []
        for p in (self.run_dir / 'jobs').glob('*/request.json'):
            request = read(p)
            if request['stage'].startswith('qa_'):
                sessions.append(request['session_id'])
                report_versions.append(request['revision'])
                inputs.append(request)
                self.assertNotIn('failures', request)
                self.assertNotIn('upstream', request)
                self.assertNotIn('task_root', request)
        self.assertEqual(len(sessions), 4)
        self.assertEqual(len(set(sessions)), 4)
        self.assertEqual(sorted(report_versions), [1, 1, 2, 2])
        hashes = {r: {x['artifact']['sha256'] for x in inputs if x['revision'] == r} for r in (1, 2)}
        self.assertEqual(len(hashes[1]), 1)
        self.assertEqual(len(hashes[2]), 1)
        self.assertNotEqual(hashes[1], hashes[2])
        self.assertEqual(len(list((self.run_dir / 'jobs').glob('*/report.json'))), 4)

    def test_production_plan_rejects_compressed_times_and_same_models(self):
        plan = self.plan()
        manager.validate_plan(plan, self.run_dir)
        plan['contract']['effective_seconds_per_track'] = 60
        with self.assertRaises(ValueError):
            manager.validate_plan(plan, self.run_dir)
        plan = self.plan()
        plan['reviewers'][1] = dict(plan['reviewers'][0])
        with self.assertRaises(ValueError):
            manager.validate_plan(plan, self.run_dir)

    def test_nonfinite_stability_is_rejected(self):
        plan = self.plan()
        plan['contract']['stability_seconds'] = float('nan')
        with self.assertRaises(ValueError):
            manager.validate_plan(plan, self.run_dir)

    def test_finalize_cannot_change_frozen_task_after_dual(self):
        self.make_run()
        state = self.until(lambda s: s['phase'] == 'finalize')
        state = manager.tick(self.run_dir)
        job = Path(state['jobs']['finalize']['directory'])
        end = time.monotonic() + 5
        while not (job / 'exit.json').exists() and time.monotonic() < end:
            time.sleep(0.03)
        (self.task / 'task.txt').write_text('unexpected protocol change')
        state = manager.tick(self.run_dir)
        self.assertEqual(state['phase'], 'repair')

    def test_noop_repair_is_not_a_new_revision(self):
        self.make_run()
        state = read(self.run_dir / 'state.json')
        state['phase'] = 'repair'
        manager.save(self.run_dir, state)
        state = manager.tick(self.run_dir)
        job = Path(state['jobs']['repair']['directory'])
        end = time.monotonic() + 5
        while not (job / 'exit.json').exists() and time.monotonic() < end:
            time.sleep(0.03)
        (self.task / 'fix.txt').unlink()
        state = manager.tick(self.run_dir)
        self.assertEqual(state['revision'], 1)
        self.assertEqual(state['phase'], 'repair')

    def test_crash_between_intent_and_launch_is_replayed_once(self):
        from unittest.mock import patch
        self.make_run()
        with patch.object(manager, 'detach'):
            state = manager.tick(self.run_dir)
        job = state['jobs']['prepare']
        self.assertFalse((Path(job['directory']) / 'started.json').exists())
        job['created_epoch'] -= 70
        manager.save(self.run_dir, state)
        self.until(lambda s: s['phase'] == 'br')
        self.assertEqual(len(list((self.run_dir / 'jobs').iterdir())), 1)

    def test_pause_keeps_running_job_and_resume_does_not_duplicate(self):
        self.make_run(delay=0.4)
        state = manager.tick(self.run_dir)
        identifier = state['jobs']['prepare']['id']
        state['status'] = 'PAUSED'
        manager.save(self.run_dir, state)
        exit_path = Path(state['jobs']['prepare']['directory']) / 'exit.json'
        end = time.monotonic() + 5
        while not exit_path.exists() and time.monotonic() < end:
            time.sleep(0.03)
        self.assertTrue(exit_path.exists())
        paused = manager.tick(self.run_dir)
        self.assertEqual(paused['status'], 'PAUSED')
        self.assertEqual(paused['jobs']['prepare']['id'], identifier)
        self.assertEqual(len(list((self.run_dir / 'jobs').iterdir())), 1)
        paused['status'] = 'RUNNING'
        manager.save(self.run_dir, paused)
        resumed = manager.tick(self.run_dir)
        self.assertEqual(resumed['phase'], 'br')
        self.assertEqual(len(list((self.run_dir / 'jobs').iterdir())), 1)

    def test_supervisor_process_exit_does_not_kill_worker(self):
        self.make_run(delay=0.3)
        command = [sys.executable, str(HERE / 'manager.py'), 'tick', '--run-dir', str(self.run_dir)]
        result = subprocess.run(command, capture_output=True, check=True)
        state = read(self.run_dir / 'state.json')
        self.assertEqual(result.returncode, 0)
        job = Path(state['jobs']['prepare']['directory'])
        end = time.monotonic() + 5
        while not (job / 'exit.json').exists() and time.monotonic() < end:
            time.sleep(0.03)
        self.assertEqual(read(job / 'exit.json')['exit_code'], 0)
        self.assertEqual(manager.tick(self.run_dir)['phase'], 'br')

    def test_resolved_driver_input_starts_a_fresh_attempt(self):
        self.make_run()
        state = manager.tick(self.run_dir)
        old = state['jobs']['prepare']['id']
        job = Path(state['jobs']['prepare']['directory'])
        end = time.monotonic() + 5
        while not (job / 'exit.json').exists() and time.monotonic() < end:
            time.sleep(0.03)
        r = read(job / 'receipt.json')
        r['status'] = 'NEEDS_INPUT'
        write(job / 'receipt.json', r)
        self.assertEqual(manager.tick(self.run_dir)['status'], 'NEEDS_INPUT')
        subprocess.run([sys.executable, str(HERE / 'manager.py'), 'resume', '--run-dir', str(self.run_dir),
                        '--poll-seconds', '0.03'], check=True, capture_output=True)
        final = self.until(lambda s: s['status'] == 'DONE')
        prepares = [read(p) for p in (self.run_dir / 'jobs').glob('*/request.json') if read(p)['stage'] == 'prepare']
        self.assertGreaterEqual(len(prepares), 3)
        self.assertNotEqual(prepares[-1]['job_id'], old)
        self.assertEqual(final['revision'], 2)
        time.sleep(0.1)  # Allow the detached fixture supervisor to observe DONE before cleanup.

    def test_different_zip_or_changed_report_cannot_consensus(self):
        self.make_run()
        final = self.until(lambda s: s['status'] == 'DONE')
        artifact = Path(final['artifact']['path'])
        artifact.chmod(0o600)
        with artifact.open('ab') as f:
            f.write(b'changed')
        with self.assertRaises(ValueError):
            manager.consensus(self.run_dir, final, read(self.run_dir / 'plan.json'))

    def test_sparse_report_cannot_pass(self):
        identity = self.plan()['reviewers'][0]
        report = {'source': {'sha256': 'a' * 64}, 'qa_run': {'artifact_sha256': 'a' * 64,
                  'reviewer': {**identity, 'session_id': 'new'}}, 'summary': {'decision': 'PASS'},
                  'checks': [], 'content_gates': {'checks': []}, 'harbor': {'checks': []}}
        with self.assertRaises(ValueError):
            manager.verify_report(report, identity, 'new', {'sha256': 'a' * 64})

    def test_old_trajectory_evidence_cannot_change_before_release(self):
        self.make_run()
        state = self.until(lambda s: s['phase'] == 'finalize')
        entry = state['completed']['dual_a']
        (Path(entry['job_directory']) / 'duration.json').write_text('{"changed":true}')
        state = self.until(lambda s: s['phase'] == 'repair')
        self.assertEqual(state['status'], 'RUNNING')
        self.assertTrue(any(x.get('error_type') == 'PriorEvidenceChanged' for x in state['failures']))

    def test_deleted_old_evidence_enters_repair_and_can_complete_new_revision(self):
        self.make_run()
        state = self.until(lambda s: s['phase'] == 'finalize')
        (Path(state['completed']['dual_a']['job_directory']) / 'duration.json').unlink()
        state = self.until(lambda s: s['phase'] == 'repair')
        state = self.until(lambda s: s['status'] == 'DONE')
        self.assertEqual(state['revision'], 2)

    def test_fake_effective_duration_rejected(self):
        actual = {'started_epoch': 10, 'ended_epoch': 20}
        with self.assertRaises(ValueError):
            manager.validate_duration({'effective_seconds': 36000, 'intervals':
                [{'start_epoch': 10, 'end_epoch': 20, 'kind': 'research'}]}, actual)
        with self.assertRaises(ValueError):
            manager.validate_duration({'effective_seconds': 10, 'intervals':
                [{'start_epoch': 10, 'end_epoch': 20, 'kind': 'queue'}]}, actual)

    def test_path_escape_and_secret_environment_are_rejected(self):
        secret_file_path = self.root / 'secret'
        secret_file_path.write_text('TEST SENTINEL')
        (self.run_dir / 'link').symlink_to(secret_file_path)
        with self.assertRaises(ValueError):
            evidence_path(self.run_dir, 'link')
        with self.assertRaises(ValueError):
            evidence_path(self.run_dir, '../secret')
        old = os.environ.get('ARK_API_KEY')
        os.environ['ARK_API_KEY'] = 'TEST_SENTINEL_NOT_A_REAL_KEY'
        try:
            self.assertNotIn('ARK_API_KEY', clean_env())
        finally:
            if old is None:
                os.environ.pop('ARK_API_KEY')
            else:
                os.environ['ARK_API_KEY'] = old


if __name__ == '__main__':
    unittest.main()

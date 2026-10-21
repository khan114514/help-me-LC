"""Expert clean Reference; never a NOP or model trajectory result.

Native ArtifactHandler first hands over Starter. Only after Actor shutdown,
this official Verifier extension replaces this own Verifier's method.py.
"""
import hashlib
import os
from pathlib import Path
import stat
import types

from harbor.verifier.verifier import Verifier
from harbor.environments.docker.docker import DockerEnvironment
from run_nop import dump, require, sha_file, utc, TASK, METHOD_SHA, SOLVE_SHA

REFERENCE_SHA = 'f4ed9a25e31be15e138b365714d2ab957ea4d6200fc293d3896fda27d3a65518'
REFERENCE_NODES_SHA = '63fdc2bcbc2230879ae9ab42c6fefbb760466694fd62ff02fee9e080dc6656c3'


def check_source(path, method_sha):
    entries = list(Path(path).iterdir())
    require({p.name for p in entries} == {'method.py', 'solve.sh'}, 'reference_requires_exact_two_files')
    for p in entries:
        s = p.lstat()
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'reference_source_nonregular_or_link')
    require((Path(path)/'method.py').stat().st_size <= 1024*1024, 'reference_source_over_limit')
    require(sha_file(Path(path)/'method.py') == method_sha and sha_file(Path(path)/'solve.sh') == SOLVE_SHA,
            'reference_method_or_frozen_solve_mismatch')
    return {'method.py': method_sha, 'solve.sh': SOLVE_SHA}


class ExpertCleanReferenceVerifier(Verifier):
    def __init__(self, *args, expert_reference_path, expert_evidence_root,
                 skip_tests_upload=True, **kwargs):
        self.expert_reference = Path(expert_reference_path)
        self.expert_root = Path(expert_evidence_root)/'reference-verifier'
        # Harbor 0.23's custom-verifier factory drops its separate-mode flag.
        # This task's exact cold Verifier already has frozen /tests baked in.
        require(skip_tests_upload is True, 'Reference_requires_baked_frozen_tests')
        super().__init__(*args, skip_tests_upload=True, **kwargs)

    async def verify(self):
        env = self.environment
        require(isinstance(env, DockerEnvironment) and env.environment_dir.resolve() == TASK/'tests',
                'reference_requires_exact_own_Task_verifier')
        source = self.expert_reference
        s = source.lstat()
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == 0
                and stat.S_IMODE(s.st_mode) == 0o600 and s.st_size <= 1024*1024,
                'expert_Reference_not_private_regular')
        require(not any(p.is_symlink() for p in [source.parent,*source.parent.parents]),
                'expert_Reference_parent_link')
        require(sha_file(source) == REFERENCE_SHA, 'expert_Reference_source_pin_mismatch')
        adapter = getattr(env, '_rfsteps_live_tmpfs_download', None)
        require(adapter is not None and adapter.environment is env, 'own_live_reader_not_installed')
        self.expert_root.mkdir(mode=0o700, parents=True, exist_ok=False)
        cid = await adapter.own_cid()
        before = self.expert_root/'source-before'
        await adapter.download('/workspace/solution', before, 'dir')
        check_source(before, METHOD_SHA)
        # Upload only to this own isolated Verifier. Actor/Task/collected Starter stay unchanged.
        await env.upload_file(source_path=source, target_path='/workspace/solution/method.py')
        after = self.expert_root/'source-after'
        await adapter.download('/workspace/solution', after, 'dir')
        check_source(after, REFERENCE_SHA)
        require(await adapter.own_cid() == cid, 'reference_verifier_CID_changed')
        inventory_sha = adapter.pin_final_submission(after)
        dump(self.expert_root/'injection.json', {
            'purpose': 'expert_clean_reference', 'is_NOP': False, 'model_trajectory': False,
            'verifier_cid': cid, 'injected_at': utc(), 'source_before': str(before),
            'source_after': str(after), 'original_method_sha256': METHOD_SHA,
            'reference_method_sha256': REFERENCE_SHA, 'frozen_solve_sha256': SOLVE_SHA,
            'live_source_inventory_sha256': inventory_sha,
            'Actor_artifact_not_modified': True, 'Task_not_modified': True,
            'research_credit_seconds': 0,
        })
        original_exec = env.exec
        commands = []
        async def witnessed_exec(bound, *args, **kwargs):
            require(bound is env, 'reference_exec_instance_changed')
            result = await original_exec(*args, **kwargs)
            command = kwargs.get('command', args[0] if args else None)
            require(isinstance(command, str), 'native_verifier_command_not_string')
            commands.append({'command_sha256': hashlib.sha256(command.encode()).hexdigest(),
                             'return_code': result.return_code, 'finished_at': utc(),
                             'is_chmod': command.startswith('chmod +x ')})
            return result
        env.exec = types.MethodType(witnessed_exec, env)
        try:
            result = await super().verify()
            tests = [p for p in commands if not p['is_chmod']]
            require(len(tests) == 1 and tests[0]['return_code'] == 0,
                    'native_Reference_test_process_not_exit_zero')
            final = self.expert_root/'source-final'
            await adapter.download('/workspace/solution', final, 'dir')
            check_source(final, REFERENCE_SHA)
            require(await adapter.own_cid() == cid and sha_file(source) == REFERENCE_SHA,
                    'reference_source_or_instance_changed')
            return result
        finally:
            env.exec = original_exec
            dump(self.expert_root/'native-exec-receipt.json', {'commands': commands,
                'unchanged_native_commands': True, 'research_credit_seconds': 0})

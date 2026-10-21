"""Task-local live transfer for a genuine Harbor built-in NopAgent Job.

Only this Job's DockerEnvironment instances are extended; no model setup occurs.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from harbor.environments.docker.docker import DockerEnvironment
from live_tmpfs_download import install_live_downloads

TASK = Path(('' + ('/' + 'root/') + 'rfsteps-v341-build-check-20261004'))
SOCKET_ROOT = Path(('' + ('/' + 'root/') + 'rfsteps-v341-rpc-20261004/sockets'))
TASK_SHA = '90bb7746559319dc6ce29dbbfae946f9a6b00694ef04b25d267f7def8c8249cb'
ADAPTER_SHA = 'aec60c3a09e95841cf1bc421f4ceba899c32fb44950095ef136785eb11a939c2'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def check_socket(path, owner=0, mode=0o600):
    path = Path(path)
    for ancestor in [path.parent, *path.parent.parents]:
        require(not ancestor.is_symlink(), 'socket_ancestor_symlink')
    s = path.lstat()
    require(stat.S_ISSOCK(s.st_mode), 'socket_source_is_not_UDS')
    require(s.st_uid == owner and stat.S_IMODE(s.st_mode) == mode, 'socket_owner_or_mode_invalid')
    return {'path': str(path), 'inode': s.st_ino, 'device': s.st_dev,
            'uid': s.st_uid, 'mode': stat.S_IMODE(s.st_mode)}


def image_content(image):
    config = dict(image['Config'])
    config.pop('Labels', None)
    return {k: image[k] for k in ('Architecture', 'Os', 'RootFS')} | {'Config': config}


def safe_write(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, allow_nan=False).encode() + b'\n'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


async def engine_json(env, *args):
    command = type(env)._engine_cmd(*args)
    process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError('own_engine_inspect_timeout') from None
    require(process.returncode == 0 and len(stdout) <= 4 * 1024 * 1024, 'own_engine_inspect_failed')
    return json.loads(stdout)


class NopLiveDockerEnvironment(DockerEnvironment):
    def __init__(self, *args, nop_evidence_root, nop_source_root, **kwargs):
        self.nop_source_root = Path(nop_source_root)
        self.nop_evidence_root = Path(nop_evidence_root)
        env_dir = Path(kwargs['environment_dir']).resolve()
        require(env_dir in (TASK / 'environment', TASK / 'tests'), 'NOP_environment_outside_frozen_task')
        self.nop_role = 'agent' if env_dir.name == 'environment' else 'verifier'
        require(re.fullmatch(r'[A-Za-z0-9_.-]+', kwargs['session_id']) is not None, 'unsafe_session_id')
        self.nop_session = kwargs['session_id']
        self.nop_report = self.nop_evidence_root / 'environments' / self.nop_session
        super().__init__(*args, **kwargs)

    async def start(self, force_build):
        # Recheck right before native Compose. Missing paths must never be auto-created.
        socket_path = SOCKET_ROOT / ('public.sock' if self.nop_role == 'agent' else 'formal.sock')
        socket_mode = 0o666 if self.nop_role == 'agent' else 0o600
        before = check_socket(socket_path, mode=socket_mode)
        require(digest((self.nop_source_root / 'live_tmpfs_download.py').read_bytes()) == ADAPTER_SHA,
                'live_adapter_source_pin_mismatch')
        await super().start(force_build)
        adapter = install_live_downloads(self, self.nop_report / 'live-transfer')
        cid = await adapter.own_cid()
        actual = (await engine_json(self, 'inspect', cid))[0]
        image_id = actual['Image']
        pins = json.loads((self.nop_source_root / 'cold-image-content-pins.json').read_text())[self.nop_role]
        current_image = (await engine_json(self, 'image', 'inspect', image_id))[0]
        cold_image = (await engine_json(self, 'image', 'inspect', pins['image_id']))[0]
        direct_equal = image_content(current_image) == image_content(cold_image)
        content_sha = digest(canonical(image_content(current_image)))
        require(direct_equal and content_sha == pins['content_sha256'], 'actual_image_content_drift')
        host = actual['HostConfig']
        cpu = host.get('NanoCpus') == 2_000_000_000 or (
            host.get('CpuPeriod', 0) > 0 and host.get('CpuQuota') == 2 * host['CpuPeriod'])
        caps = sorted(x.removeprefix('CAP_') for x in (host.get('CapAdd') or []))
        require(cpu and host['Memory'] == 2 * 1024**3 and host['ReadonlyRootfs'] is True,
                'actual_resource_or_readonly_mismatch')
        require(not host.get('DeviceRequests') and not host.get('Devices'), 'unexpected_GPU_or_device')
        require(caps == ['SETGID', 'SETUID'] and 'ALL' in (host.get('CapDrop') or []), 'actual_capabilities_mismatch')
        mounts = [{'source': m['Source'], 'destination': m['Destination'], 'rw': m['RW'], 'type': m['Type']}
                  for m in actual.get('Mounts', [])]
        targets = [m for m in mounts if m['destination'].startswith('/run/rfsteps/')]
        require(targets == [{'source': str(socket_path), 'destination': '/run/rfsteps/' + socket_path.name,
                             'rw': False, 'type': 'bind'}], 'actual_score_socket_mount_mismatch')
        require(not any('/model' in m['destination'] or 'trusted-rpc-receipts' in m['source']
                        or 'private_hidden' in m['source'] for m in mounts), 'forbidden_mount')
        after = check_socket(socket_path, mode=socket_mode)
        require(before == after, 'score_socket_changed_while_starting')
        if self.nop_role == 'agent':
            # Bind the native final artifact collection to the actual unchanged Starter.
            adapter.pin_final_submission(TASK / 'solution')
        self.nop_live_adapter = adapter
        safe_write(self.nop_report / 'started.json', {
            'role': self.nop_role, 'session_id': self.nop_session, 'cid': cid,
            'image_id': image_id, 'cold_image_id': pins['image_id'], 'content_sha256': content_sha,
            'direct_image_content_equal': direct_equal, 'image_recipe': 'Architecture/Os/RootFS/Config except Labels; sorted compact JSON SHA256',
            'socket': after, 'mounts': mounts, 'cpus': 2, 'memory_bytes': host['Memory'],
            'readonly_rootfs': host['ReadonlyRootfs'], 'cap_add': caps,
            'task_checksum': TASK_SHA, 'live_adapter_sha256': ADAPTER_SHA,
            'native_nop': True, 'model_calls': 0, 'research_credit_seconds': 0,
        })

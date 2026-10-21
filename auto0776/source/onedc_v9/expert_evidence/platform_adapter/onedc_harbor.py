"""Harbor 0.23 Docker adapter for NVIDIA devices and a trusted shared lease.

Install on the organizer host, outside every candidate build context. Both agent
and separate-verifier environments use this same import_path and kwargs.
"""
import json
import os
from pathlib import Path
import re
import tempfile

from harbor.environments.docker.docker import DockerEnvironment


class OneDCDockerEnvironment(DockerEnvironment):
    @property
    def capabilities(self):
        return super().capabilities.model_copy(update={"gpus": True})

    def __init__(self, *args, gpu_lock_path="/var/lib/onedc/gpu.lock", gpu_device_id="0",
                 seccomp_profile_path="/var/lib/onedc/security/onedc-namespaces.json",
                 apparmor_profile_name="onedc-codex-v1", **kwargs):
        lease = Path(gpu_lock_path)
        if lease.is_symlink() or not lease.is_file():
            raise RuntimeError("Organizer must provision a regular shared GPU lease file")
        if lease.stat().st_uid != 0 or lease.stat().st_mode & 0o077:
            raise RuntimeError("GPU lease must be root-owned and private")
        if not str(gpu_device_id).isdigit():
            raise ValueError("GPU device must be a numeric NVIDIA device index")
        policy = Path(seccomp_profile_path)
        if policy.is_symlink() or not policy.is_file() or policy.stat().st_uid != 0 or policy.stat().st_mode & 0o022:
            raise RuntimeError("Organizer must provide a root-owned, non-writable seccomp policy")
        json.loads(policy.read_text())
        if not re.fullmatch(r"onedc-[a-zA-Z0-9-]+", apparmor_profile_name):
            raise ValueError("Expected a task-scoped OneDC AppArmor profile")
        loaded = Path("/sys/kernel/security/apparmor/profiles").read_text().splitlines()
        if apparmor_profile_name + " (enforce)" not in loaded:
            raise RuntimeError("OneDC AppArmor profile is not loaded in enforce mode")
        self._onedc_overlay = tempfile.TemporaryDirectory(prefix="onedc-harbor-")
        overlay = Path(self._onedc_overlay.name) / "runtime.json"
        main = {"pids_limit": 512, "shm_size": "512m", "ipc": "private",
                "tmpfs": ["/tmp:rw,nosuid,size=512m,mode=1777"],
                "security_opt": ["seccomp=" + str(policy.resolve()), "apparmor=" + apparmor_profile_name],
                "cap_drop": ["ALL"], "cap_add": ["SETUID", "SETGID", "CHOWN", "FOWNER", "KILL"],
                "labels": {"onedc.managed": "true"},
                "volumes": [{"type": "bind", "source": str(lease.resolve()),
                             "target": "/opt/onedc/locks/gpu.lock", "read_only": False}]}
        # Base construction checks capabilities before resolving compose paths.
        extras = list(kwargs.pop("extra_docker_compose", None) or [])
        kwargs["extra_docker_compose"] = extras + [str(overlay)]
        # This preliminary file is used during base validation.
        overlay.write_text(json.dumps({"services": {"main": main}}))
        super().__init__(*args, **kwargs)
        if self._effective_gpus not in (0, 1):
            raise RuntimeError("This adapter supports exactly one NVIDIA GPU or CPU preflight")
        if self._effective_gpus == 1:
            main["deploy"] = {"resources": {"reservations": {"devices": [
                {"driver": "nvidia", "device_ids": [str(gpu_device_id)], "capabilities": ["gpu"]}
            ]}}}
        overlay.write_text(json.dumps({"services": {"main": main}}, indent=2))

    async def stop(self, delete=False):
        try:
            return await super().stop(delete=delete)
        finally:
            if delete:
                self._onedc_overlay.cleanup()

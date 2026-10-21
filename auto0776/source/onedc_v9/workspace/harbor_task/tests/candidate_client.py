"""Bounded tensor-only IPC to a credential-free, unprivileged worker."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import pwd
import resource
import shutil
import socket
import struct
import subprocess
import sys
import tempfile

import numpy as np
import torch

from candidate_worker import MAX_BYTES, receive, send


class CandidateError(ValueError):
    pass


class CandidateClient:
    def __init__(self, method, device="cuda", timeout=60):
        if os.geteuid() != 0:
            raise RuntimeError("Trusted grading must run as root to isolate candidate code")
        account = pwd.getpwnam("onedc-worker")
        self.worker_uid, self.worker_gid = account.pw_uid, account.pw_gid
        self.stage = Path(tempfile.mkdtemp(prefix="onedc-method-"))
        self.stage.chmod(0o755)
        staged_method = self.stage / "method.py"
        shutil.copyfile(method, staged_method)
        staged_method.chmod(0o444)
        staged_worker = self.stage / "worker.py"
        shutil.copyfile(Path(__file__).with_name("candidate_worker.py"), staged_worker)
        staged_worker.chmod(0o444)
        self.method_sha256 = hashlib.sha256(staged_method.read_bytes()).hexdigest()
        self.scratch = Path(tempfile.mkdtemp(prefix="onedc-worker-"))
        os.chown(self.scratch, account.pw_uid, account.pw_gid)
        self.scratch.chmod(0o700)
        self.sock, child = socket.socketpair()
        self.sock.settimeout(timeout)

        def drop_privileges():
            os.setgroups([])
            os.setgid(account.pw_gid)
            os.setuid(account.pw_uid)
            os.chdir(self.scratch)
            if ctypes.CDLL(None, use_errno=True).prctl(38, 1, 0, 0, 0) != 0:
                raise OSError(ctypes.get_errno(), "Could not enable no_new_privs")
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_FSIZE, (16 << 20, 16 << 20))
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            resource.setrlimit(resource.RLIMIT_CPU, (1800, 1800))

        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
               "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
               "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "ONEDC_WORKER_DEVICE": device}
        for key in ("LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES"):
            if key in os.environ:
                env[key] = os.environ[key]
        self.process = subprocess.Popen(
            [sys.executable, str(staged_worker), str(child.fileno()), str(staged_method)],
            pass_fds=(child.fileno(),), preexec_fn=drop_privileges, env=env, cwd=self.stage,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        child.close()
        try:
            ready, payload = receive(self.sock)
            if ready != {"op": "isolated", "ok": True, "nbytes": 0} or payload:
                raise RuntimeError("Worker isolation preflight did not succeed")
        except BaseException:
            self.close()
            raise RuntimeError("Worker isolation or device initialization failed")

    def __call__(self, y_res, scales, ctx):
        try:
            y = y_res.detach().cpu().contiguous()
            s = scales.detach().cpu().contiguous()
            if tuple(s.shape) != tuple(y.shape):
                raise CandidateError("Entropy scales must have the residual shape")
            payload = y.view(torch.uint8).numpy().tobytes() + s.view(torch.uint8).numpy().tobytes()
            if len(payload) > MAX_BYTES:
                raise CandidateError("Candidate tensor exceeds the IPC budget")
            send(self.sock, {"op": "quantize", "dtype": str(y.dtype), "scales_dtype": str(s.dtype), "shape": list(y.shape)}, payload)
            header, payload = receive(self.sock)
            if not header.get("ok") or header.get("dtype") != "float32" or header.get("shape") != list(y.shape) or len(payload) != y.numel() * 4:
                raise CandidateError("Invalid worker tensor response")
            array = np.frombuffer(payload, dtype=np.float32).copy().reshape(y.shape)
            return torch.from_numpy(array).to(device=y_res.device, dtype=y_res.dtype)
        except socket.timeout as exc:
            raise TimeoutError("Candidate quantization call exceeded its deadline") from exc
        except (OSError, EOFError, ValueError, KeyError, TypeError, AttributeError, struct.error) as exc:
            raise CandidateError("Candidate failed or returned an invalid tensor response") from exc

    def close(self):
        try:
            send(self.sock, {"op": "close"})
        except OSError:
            pass
        self.sock.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        shutil.rmtree(self.stage)
        # The grader intentionally lacks DAC_OVERRIDE. Clean a worker-owned
        # directory as that same user after the entire worker has exited.
        subprocess.run(
            [sys.executable, "-I", "-c", "import shutil,sys; shutil.rmtree(sys.argv[1])", str(self.scratch)],
            user=self.worker_uid, group=self.worker_gid, extra_groups=[],
            cwd="/", env={"PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=15, check=True,
        )

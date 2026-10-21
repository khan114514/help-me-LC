"""Unprivileged quantization worker; never imports a candidate in the grader."""
import ctypes
import ctypes.util
import errno
import importlib.util
import json
import os
import socket
import struct
import sys

import numpy as np
import torch

MAX_BYTES = 64 * 1024 * 1024


def receive_exact(sock, size):
    if size < 0 or size > MAX_BYTES:
        raise ValueError("Message exceeds tensor size limit")
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise EOFError("Worker connection closed")
        data.extend(chunk)
    return data


def receive(sock):
    length = struct.unpack("!I", receive_exact(sock, 4))[0]
    if length > 65536:
        raise ValueError("Invalid tensor header")
    header = json.loads(receive_exact(sock, length))
    return header, receive_exact(sock, int(header.get("nbytes", 0)))


def send(sock, header, payload=b""):
    header = dict(header, nbytes=len(payload))
    data = json.dumps(header).encode()
    sock.sendall(struct.pack("!I", len(data)) + data + payload)


def restrict_syscalls():
    """Fail closed if the kernel cannot enforce the worker's syscall policy."""
    lib = ctypes.CDLL(ctypes.util.find_library("seccomp") or "libseccomp.so.2")
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    class ArgComparison(ctypes.Structure):
        _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int),
                    ("datum_a", ctypes.c_uint64), ("datum_b", ctypes.c_uint64)]
    lib.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                         ctypes.c_uint, ctypes.POINTER(ArgComparison)]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_attr_set.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = lib.seccomp_init(0x7FFF0000)
    if not ctx:
        raise RuntimeError("Cannot create worker syscall filter")
    try:
        if lib.seccomp_attr_set(ctx, 4, 1) != 0:  # SCMP_FLTATR_CTL_TSYNC
            raise RuntimeError("Cannot synchronize worker syscall restrictions across threads")
        blocked = ("socket", "connect", "bind", "listen", "accept", "accept4", "socketpair",
                   "fork", "vfork", "execve", "execveat", "unshare", "setns", "mount", "setsid", "setpgid",
                   "ptrace", "process_vm_readv", "process_vm_writev", "bpf", "open_by_handle_at")
        for name in blocked:
            call = lib.seccomp_syscall_resolve_name(name.encode())
            if call >= 0 and lib.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM, call, 0) != 0:
                raise RuntimeError("Cannot configure worker syscall filter")
        # Permit library threads, but never a new independent process. clone3
        # flags live behind a pointer; ENOSYS lets pthreads use checked clone.
        clone = lib.seccomp_syscall_resolve_name(b"clone")
        without_thread = ArgComparison(0, 7, 0x10000, 0)  # MASKED_EQ, CLONE_THREAD
        if clone < 0 or lib.seccomp_rule_add_array(ctx, 0x00050000 | errno.EPERM,
                                                 clone, 1, ctypes.byref(without_thread)) != 0:
            raise RuntimeError("Cannot restrict worker process cloning")
        clone3 = lib.seccomp_syscall_resolve_name(b"clone3")
        if clone3 >= 0 and lib.seccomp_rule_add(ctx, 0x00050000 | errno.ENOSYS, clone3, 0) != 0:
            raise RuntimeError("Cannot restrict worker clone3")
        if lib.seccomp_load(ctx) != 0:
            raise RuntimeError("Cannot enable worker syscall filter")
    finally:
        lib.seccomp_release(ctx)


def main():
    sock = socket.socket(fileno=int(sys.argv[1]))
    method_path = sys.argv[2]
    torch.set_num_threads(1)
    # Initialize CUDA before restricting syscall creation by candidate code.
    if os.environ.get("ONEDC_WORKER_DEVICE") == "cuda":
        torch.empty(1, device="cuda")
    restrict_syscalls()
    send(sock, {"op": "isolated", "ok": True})
    spec = importlib.util.spec_from_file_location("candidate_method", method_path)
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    fn = getattr(candidate, "quantize", None)
    if not callable(fn):
        raise ValueError("method.py must export quantize(y_res, scales, ctx)")
    while True:
        header, data = receive(sock)
        if header.get("op") == "close":
            break
        types = {"torch.float16": (np.dtype("float16"), torch.float16),
                 "torch.bfloat16": (np.dtype("uint16"), torch.bfloat16),
                 "torch.float32": (np.dtype("float32"), torch.float32),
                 "torch.float64": (np.dtype("float64"), torch.float64)}
        if header["dtype"] not in types or header["scales_dtype"] not in types:
            raise ValueError("Invalid tensor dtype")
        dtype, y_type = types[header["dtype"]]
        s_dtype, s_type = types[header["scales_dtype"]]
        shape = tuple(int(x) for x in header["shape"])
        count = int(np.prod(shape))
        size = count * dtype.itemsize
        s_size = count * s_dtype.itemsize
        if count <= 0 or len(shape) != 4 or len(data) != size + s_size:
            raise ValueError("Invalid tensor shape or length")
        device = "cuda" if os.environ.get("ONEDC_WORKER_DEVICE") == "cuda" else "cpu"
        y = torch.from_numpy(np.frombuffer(data[:size], dtype=dtype).copy().reshape(shape)).view(y_type).to(device)
        scales = torch.from_numpy(np.frombuffer(data[size:], dtype=s_dtype).copy().reshape(shape)).view(s_type).to(device)
        ctx = {"shape": shape, "device": str(y.device), "dtype": str(y.dtype)}
        with torch.no_grad():
            out = torch.as_tensor(fn(y, scales, ctx))
        if tuple(out.shape) != shape or not torch.isfinite(out).all() or not torch.equal(out, torch.round(out)):
            raise ValueError("Candidate must return finite integer values with the input shape")
        array = out.detach().float().cpu().numpy().astype(np.float32, copy=False)
        send(sock, {"ok": True, "shape": shape, "dtype": "float32"}, array.tobytes())


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        # Candidate exceptions cannot write metrics or reward files.
        print("candidate worker failed: " + type(exc).__name__ + ": " + str(exc)[:400], file=sys.stderr)
        raise SystemExit(2)

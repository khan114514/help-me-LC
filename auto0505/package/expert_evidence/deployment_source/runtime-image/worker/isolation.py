"""Fail-closed Linux filesystem and syscall confinement for schedule code.

This applies to the candidate subprocess only. No container network setting,
host mount, daemon, extra container, or privileged namespace is required.
"""
import ctypes
import errno
import os
from pathlib import Path
import platform
import sys
import sysconfig


class IsolationUnavailable(RuntimeError):
    pass


class Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathRule(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def install(candidate):
    if sys.platform != "linux" or platform.machine() not in ("x86_64", "aarch64"):
        raise IsolationUnavailable("linux_landlock_seccomp_required")
    # Load trusted native support before constraining filesystem access.
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        sec = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    except OSError as exc:
        raise IsolationUnavailable("libseccomp_unavailable") from exc
    libc.syscall.restype = ctypes.c_long
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise IsolationUnavailable("no_new_privileges_failed")
    # These syscall IDs are shared by Linux x86_64 and arm64. Unsupported
    # kernels fail before any candidate source is executed.
    abi = libc.syscall(444, ctypes.c_void_p(), ctypes.c_size_t(0), ctypes.c_uint(1))
    if abi < 3:
        raise IsolationUnavailable("landlock_abi3_required")
    ruleset = Ruleset((1 << 15) - 1)
    ruleset_fd = libc.syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0)
    if ruleset_fd < 0:
        raise IsolationUnavailable("landlock_ruleset_create_failed")
    read_file, read_dir = 1 << 2, 1 << 3
    roots = {Path(sysconfig.get_path(k)).resolve() for k in ("stdlib", "platstdlib")}
    # Native dependencies needed by standard-library extension modules.
    multiarch = sysconfig.get_config_var("MULTIARCH")
    if multiarch:
        roots.update(Path(p).resolve() for p in (f"/lib/{multiarch}", f"/usr/lib/{multiarch}") if Path(p).exists())
    files = {Path(candidate).resolve()}
    files.update(Path(p).resolve() for p in sys.path if p.endswith(".zip") and Path(p).is_file())
    if Path("/etc/ld.so.cache").is_file():
        files.add(Path("/etc/ld.so.cache"))
    try:
        for path in sorted(roots | files):
            fd = os.open(path, getattr(os, "O_PATH", 0x200000) | os.O_CLOEXEC)
            try:
                allowed = read_file | read_dir if path.is_dir() else read_file
                rule = PathRule(allowed, fd)
                if libc.syscall(445, ruleset_fd, 1, ctypes.byref(rule), 0) != 0:
                    raise IsolationUnavailable("landlock_path_rule_failed")
            finally:
                os.close(fd)
        if libc.syscall(446, ruleset_fd, 0) != 0:
            raise IsolationUnavailable("landlock_restrict_failed")
    finally:
        os.close(ruleset_fd)

    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    sec.seccomp_syscall_resolve_name.restype = ctypes.c_int
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sec.seccomp_rule_add.restype = ctypes.c_int
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    sec.seccomp_load.restype = ctypes.c_int
    sec.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = sec.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not ctx:
        raise IsolationUnavailable("seccomp_create_failed")
    denied = (
        "socket", "socketpair", "connect", "bind", "listen", "accept", "accept4",
        "sendto", "sendmsg", "sendmmsg", "recvfrom", "recvmsg", "recvmmsg",
        "fork", "vfork", "clone", "clone3", "execve", "execveat",
        "ptrace", "process_vm_readv", "process_vm_writev", "pidfd_getfd",
        "kill", "tkill", "tgkill", "pidfd_send_signal",
        "mount", "umount2", "pivot_root", "chroot", "setns", "unshare",
        "open_by_handle_at", "name_to_handle_at", "bpf", "userfaultfd", "io_uring_setup",
    )
    try:
        for name in denied:
            number = sec.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and sec.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM, number, 0) != 0:
                raise IsolationUnavailable("seccomp_rule_failed")
        if sec.seccomp_load(ctx) != 0:
            raise IsolationUnavailable("seccomp_load_failed")
    finally:
        sec.seccomp_release(ctx)
    os.umask(0o077)
    return {"landlock_abi": int(abi), "filesystem_read_only": True,
            "network_syscalls_denied": True, "process_creation_denied": True}

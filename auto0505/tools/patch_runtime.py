"""Apply the single-container change to preserved, reviewed runtime sources."""
from pathlib import Path

root = Path(__file__).resolve().parent / "runtime"
original = Path(__file__).resolve().parents[1] / "source_snapshot" / "workspace" / "harbor_task" / "tests"
worker = root / "candidate_worker.py"
text = (original / "candidate_worker.py").read_text()
old = 'def main():\n    emergency_reserve = bytearray(128 * 1024)'
new = '''def main():
    try:
        guard_spec = importlib.util.spec_from_file_location("trusted_isolation", Path(__file__).with_name("isolation.py"))
        guard = importlib.util.module_from_spec(guard_spec)
        guard_spec.loader.exec_module(guard)
        guard.install(sys.argv[1])
    except Exception:
        return emit({"schema_version": 1, "status": "INFRASTRUCTURE_ERROR", "reason_code": "candidate_kernel_isolation_unavailable"}, 45)
    emergency_reserve = bytearray(128 * 1024)'''
if old in text:
    text = text.replace(old, new)
    worker.write_text(text)
elif 'candidate_kernel_isolation_unavailable' not in text:
    raise RuntimeError('worker source mismatch')

path = root / "evaluate_candidate.py"
text = (original / "evaluate_candidate.py").read_text()
text = text.replace('import socket\n', '').replace('import uuid\n', '')
text = text.replace('import argparse\n', 'import argparse\nimport importlib.util\n')
text = text.replace('''        if not stat.S_ISREG(method.lstat().st_mode) or method.is_symlink():
            raise CandidateFailure("FORMAT_ERROR", "method_source_must_be_regular")
        with method.open("rb") as stream:
            source = stream.read(SOURCE_LIMIT_BYTES + 1)''', '''        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(method, flags)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise CandidateFailure("FORMAT_ERROR", "method_source_must_be_regular")
            source = stream.read(SOURCE_LIMIT_BYTES + 1)''')
text = text.replace('''    except FileNotFoundError:
        raise CandidateFailure("FORMAT_ERROR", "method_source_missing") from None''', '''    except FileNotFoundError:
        raise CandidateFailure("FORMAT_ERROR", "method_source_missing") from None
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EISDIR, errno.ENXIO):
            raise CandidateFailure("FORMAT_ERROR", "method_source_must_be_regular") from None
        raise''')
text = text.replace('WORKER_EXIT_STATUS = {42: "FORMAT_ERROR", 43: "HARD_GATE_INVALID", 44: "RESOURCE_EXCEEDED"}',
                    'WORKER_EXIT_STATUS = {42: "FORMAT_ERROR", 43: "HARD_GATE_INVALID", 44: "RESOURCE_EXCEEDED", 45: "INFRASTRUCTURE_ERROR"}')
text = text.replace('resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))',
                    'resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))\n    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))')
text = text.replace('cwd=scratch, stdout=stdout, stderr=stderr,',
                    'cwd=scratch, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,')
text = text.replace('def restrict_candidate():', 'def restrict_candidate(worker):')
text = text.replace('''        os.setuid(65534)
''', '''        os.setuid(65534)
    if not os.access(worker, os.R_OK):
        raise OSError(errno.EACCES, "trusted_worker_unreadable_after_uid_drop")
''')
text = text.replace('preexec_fn=restrict_candidate,', 'preexec_fn=lambda: restrict_candidate(str(worker)),')
text = text.replace('        stdout.seek(0)\n',
                    '        if max(os.fstat(stdout.fileno()).st_size, os.fstat(stderr.fileno()).st_size) >= 1 << 20:\n            raise CandidateFailure("RESOURCE_EXCEEDED", "candidate_output_file_limit", evidence)\n        stdout.seek(0)\n')
if 'def rpc_evaluate(' in text:
    begin = text.index('def rpc_evaluate(')
    end = text.index('\ndef main():', begin)
    text = text[:begin] + text[end + 1:]
text = text.replace('    parser.add_argument("--worker", required=True)',
                    '    parser.add_argument("--worker", default="/opt/rfsteps/worker/candidate_worker.py")')
text = text.replace('    for name in ("reward.json", "reward.txt", "metrics.json", "evaluation_status.json", "gpu_receipt.json", "remote_metrics.json"):',
                    '    for name in ("reward.json", "reward.txt", "metrics.json", "evaluation_status.json", "gpu_receipt.json", "numeric_metrics.json"):')
old = '''        metrics, raw = rpc_evaluate(values, args.formal)
        atomic_json(out / "gpu_receipt.json", raw)
        atomic_json(out / "remote_metrics.json", metrics)
        metrics = dict(metrics)
        metrics["schedule_bridge_sha256"] = metrics["method_sha256"]
        metrics["method_sha256"] = method_digest'''
new = '''        backend_spec = importlib.util.spec_from_file_location("trusted_local_backend", Path(__file__).with_name("local_backend.py"))
        backend = importlib.util.module_from_spec(backend_spec)
        backend_spec.loader.exec_module(backend)
        metrics, raw = backend.evaluate(values, args.formal, out, method_digest, Path(__file__).parent)'''
if old in text:
    text = text.replace(old, new)
text = text.replace('"gpu_job_id": raw["job_id"]', '"execution": raw["execution"]')
text = text.replace('"score_transport_timeout"', '"local_scoring_timeout"')
text = text.replace('''        # socket.timeout is TimeoutError too. No completed response exists;
        # retain its distinct transport deadline without inventing a receipt.''', '''        # The local backend retains a receipt when its numeric subprocess
        # reaches the deadline; no normal score is written.''')
text = text.replace('''    except (OSError, KeyError, ValueError, TypeError, RuntimeError) as exc:''', '''    except (OSError, KeyError, ValueError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:''')
path.write_text(text)
print('Patched candidate confinement and direct numeric execution; numerical scorer unchanged.')

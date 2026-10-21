"""Real Linux boundary tests; no model scoring or research time credit."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

RUNTIME = Path(os.environ.get("RFSTEPS_TEST_RUNTIME", "/runtime"))
spec = importlib.util.spec_from_file_location("trusted_evaluator", RUNTIME / "evaluate_candidate.py")
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


class CandidateBoundary(unittest.TestCase):
    def extract(self, source):
        with tempfile.TemporaryDirectory() as tmp:
            method = Path(tmp) / "method.py"
            method.write_text(source)
            scratch = Path(tmp) / "scratch"
            scratch.mkdir()
            # The copied method is readable by the worker after UID dropping.
            Path(tmp).chmod(0o755)
            return evaluator.extract_schedule(method, RUNTIME / "candidate_worker.py", scratch, "/usr/bin/python3")

    def test_valid_math_schedule(self):
        nodes, digest = self.extract("import math\ndef get_timesteps(n,s):\n return [math.cos(i*math.pi/(2*n)) for i in range(n+1)]\n")
        self.assertEqual(len(nodes), 26)
        self.assertEqual(len(digest), 64)

    def test_native_open_cannot_read_outside_input(self):
        canary = Path("/private-canary/readable-secret")
        self.assertTrue(canary.is_file())
        nodes, _ = self.extract('import ctypes\ndef get_timesteps(n,s):\n lib=ctypes.CDLL(None)\n fd=lib.open(b"/private-canary/readable-secret",0)\n if fd>=0:\n  lib.close(fd)\n  return [1-(i/n)**2 for i in range(n+1)]\n return [1-i/n for i in range(n+1)]\n')
        self.assertEqual(nodes, [1-i/25 for i in range(26)])

    def test_native_socket_denied(self):
        nodes, _ = self.extract('import ctypes\ndef get_timesteps(n,s):\n lib=ctypes.CDLL(None)\n fd=lib.socket(2,1,0)\n if fd>=0:\n  lib.close(fd)\n  return [1-(i/n)**2 for i in range(n+1)]\n return [1-i/n for i in range(n+1)]\n')
        self.assertEqual(nodes, [1-i/25 for i in range(26)])

    def test_nonfinite_is_invalid(self):
        with self.assertRaises(evaluator.CandidateFailure) as result:
            self.extract('def get_timesteps(n,s):\n return [float("nan")]*26\n')
        self.assertEqual(result.exception.status, "HARD_GATE_INVALID")

    def test_symlink_method_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "target").write_text("def get_timesteps(n,s): return [1-i/n for i in range(n+1)]")
            (root / "method.py").symlink_to(root / "target")
            (root / "scratch").mkdir()
            with self.assertRaises(evaluator.CandidateFailure) as result:
                evaluator.extract_schedule(root / "method.py", RUNTIME / "candidate_worker.py", root / "scratch", "/usr/bin/python3")
            self.assertEqual(result.exception.status, "FORMAT_ERROR")

    def test_unbounded_stdout_is_resource_failure(self):
        with self.assertRaises(evaluator.CandidateFailure) as result:
            self.extract('import os\ndef get_timesteps(n,s):\n while True: os.write(1,b"x"*65536)\n')
        self.assertEqual(result.exception.status, "RESOURCE_EXCEEDED")

    def test_fifo_source_rejected_without_waiting_for_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.mkfifo(root / "method.py")
            (root / "scratch").mkdir()
            with self.assertRaises(evaluator.CandidateFailure) as result:
                evaluator.extract_schedule(root / "method.py", RUNTIME / "candidate_worker.py", root / "scratch", "/usr/bin/python3")
            self.assertEqual(result.exception.status, "FORMAT_ERROR")

    def test_wall_timeout_reaps_worker(self):
        with self.assertRaises(evaluator.CandidateFailure) as result:
            self.extract('import time\ndef get_timesteps(n,s):\n time.sleep(100)\n return [1-i/n for i in range(n+1)]\n')
        self.assertEqual(result.exception.status, "TIMEOUT")
        self.assertGreaterEqual(result.exception.evidence["wall_seconds"], 35)
        self.assertLess(result.exception.evidence["wall_seconds"], 40)
        self.assertTrue(result.exception.evidence["owned_signal_cleanup"]["parent_euid_restored"])

    def test_missing_isolation_fails_before_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o755)
            shutil.copy2(RUNTIME / "candidate_worker.py", root / "worker.py")
            (root / "worker.py").chmod(0o644)
            (root / "method.py").write_text("raise ValueError('candidate_must_not_run')")
            (root / "scratch").mkdir()
            with self.assertRaises(evaluator.CandidateFailure) as result:
                evaluator.extract_schedule(root / "method.py", root / "worker.py", root / "scratch", "/usr/bin/python3")
            self.assertEqual(result.exception.status, "INFRASTRUCTURE_ERROR")
            self.assertEqual(result.exception.reason_code, "candidate_kernel_isolation_unavailable")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Exercise production image file/UID boundaries with a CPU-only base fixture."""
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile

formal = sys.argv[1] == "formal"
runtime = Path("/tests" if formal else "/opt/rfsteps/public")
assert os.geteuid() == (0 if formal else 1000)
assert Path("/opt/rfsteps/worker/candidate_worker.py").stat().st_mode & stat.S_IROTH
if formal:
    assert stat.S_IMODE(Path("/tests").stat().st_mode) == 0o700
    (runtime / "private-canary").write_text("synthetic-private-canary")
else:
    assert len(list((runtime / "assets/public").glob("*.png"))) == 12
    assert not (runtime / "assets/hidden").exists()
    assert os.access("/workspace/environment/public_eval/evaluate.sh", os.X_OK)
    assert os.access("/workspace/solution", os.W_OK)
    assert not os.access(runtime / "evaluate_candidate.py", os.W_OK)
spec = importlib.util.spec_from_file_location("trusted_evaluator", runtime / "evaluate_candidate.py")
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    root.chmod(0o755)
    method = root / "method.py"
    method.write_text('import ctypes\ndef get_timesteps(n,s):\n lib=ctypes.CDLL(None)\n fd=lib.open(b"/tests/private-canary",0)\n if fd>=0:\n  lib.close(fd)\n  return [1-(i/n)**2 for i in range(n+1)]\n return [1-i/n for i in range(n+1)]\n')
    method.chmod(0o644)
    scratch = root / "scratch"
    scratch.mkdir()
    nodes, digest = evaluator.extract_schedule(method, "/opt/rfsteps/worker/candidate_worker.py", scratch, "/usr/bin/python3")
    assert nodes == [1-i/25 for i in range(26)]
    assert len(digest) == 64
print("PASS", "formal-root-private-boundary" if formal else "public-user-runtime-permissions", "CPU_FIXTURE_NO_GPU_SCORE")

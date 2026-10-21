"""Protocol regression tests with a synthetic scorer and mocked GPU inventory.

These exercise the trusted wrapper only; they are not GPU/FLUX results.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

RUNTIME = Path(os.environ.get("RFSTEPS_TEST_RUNTIME", "/runtime"))
spec = importlib.util.spec_from_file_location("trusted_backend", RUNTIME / "local_backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

SCORER = '''import argparse, hashlib, json, os
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--method'); p.add_argument('--out'); p.add_argument('--split')
a=p.parse_args(); out=Path(a.out); out.mkdir()
m={'overall':{'n':12,'psnr':21.0,'ssim':0.8}, 'per_image':[{'split':'public','psnr':21.0,'ssim':0.8,'pixel_mse':0.1,'latent_mse':0.2} for _ in range(12)], 'nfe_per_image':100,'num_steps':25,'method_sha256':hashlib.sha256(Path(a.method).read_bytes()).hexdigest(),'score':0.5}
{mutation}
(out/'metrics.json').write_text(json.dumps(m))
print('SYNTHETIC_SCORER_NO_GPU')
'''


class BackendProtocol(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.out = self.root / "output"
        self.out.mkdir()
        (self.runtime / "assets/public").mkdir(parents=True)
        (self.runtime / "assets/public/fixture.png").write_bytes(b"synthetic-fixture")
        self.gpu_mock = patch.object(backend.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "NVIDIA A100-PCIE-40GB, 40960\n", ""))
        self.gpu = self.gpu_mock.start()
        self.addCleanup(self.gpu_mock.stop)
        original_verify = backend.verify_files

        def fixture_verify(root, expected):
            # Production paths deliberately remain fixed. Only these two large
            # asset roots are mocked; scorer/image/anchor hashes are checked.
            if str(root) in ("/opt/rfsteps/repo", "/opt/rfsteps/weights", "/opt/rfsteps/worker"):
                return
            original_verify(root, expected)

        self.verify_mock = patch.object(backend, "verify_files", side_effect=fixture_verify)
        self.verify_mock.start()
        self.addCleanup(self.verify_mock.stop)

    def prepare(self, mutation=""):
        (self.runtime / "run_eval.py").write_text(SCORER.replace("{mutation}", mutation))
        (self.runtime / "anchors.json").write_text(json.dumps({"baseline":{"public":{"psnr":20.0}},"upper_bound":{"public":{"psnr":22.0}}}))
        manifest={"role":"public", "runtime_files":{name:backend.digest(self.runtime/name) for name in ("run_eval.py","anchors.json")},"images":{"public/fixture.png":backend.digest(self.runtime/"assets/public/fixture.png")},"repo_files":{},"weight_files":{},"worker_files":{}}
        (self.runtime / "asset_manifest.json").write_text(json.dumps(manifest))

    def evaluate(self):
        return backend.evaluate([1-i/25 for i in range(26)], False, self.out, "a"*64, self.runtime)

    def test_numeric_bridge_identity_and_atomic_receipt(self):
        self.prepare()
        metrics, receipt = self.evaluate()
        raw = json.loads((self.out / "numeric_metrics.json").read_text())
        self.assertEqual(metrics["method_sha256"], "a"*64)
        self.assertEqual(metrics["schedule_bridge_sha256"], raw["method_sha256"])
        self.assertNotEqual(raw["method_sha256"], "a"*64)
        self.assertEqual(metrics["score"], 0.5)
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(receipt["stdout_sha256"], backend.digest(self.out / "scorer-stdout.txt"))

    def test_invalid_nfe_rejected(self):
        self.prepare("m['nfe_per_image']=99")
        with self.assertRaisesRegex(RuntimeError, "scorer_protocol_mismatch"):
            self.evaluate()

    def test_changed_normalization_rejected(self):
        self.prepare("m['score']=0.7")
        with self.assertRaisesRegex(RuntimeError, "normalization_mismatch"):
            self.evaluate()

    def test_wrong_candidate_identity_rejected(self):
        self.prepare("m['method_sha256']='0'*64")
        with self.assertRaisesRegex(RuntimeError, "numeric_bridge_identity_mismatch"):
            self.evaluate()

    def test_asset_corruption_stops_before_gpu(self):
        self.prepare()
        (self.runtime / "assets/public/fixture.png").write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "frozen_asset_hash_mismatch"):
            self.evaluate()
        self.gpu.assert_not_called()

    def test_gpu_inventory_failure_is_classified(self):
        self.prepare()
        self.gpu.side_effect = subprocess.CalledProcessError(1, ["nvidia-smi"])
        with self.assertRaisesRegex(RuntimeError, "allocated_gpu_inventory_failed"):
            self.evaluate()

    def test_gpu_inventory_timeout_is_infrastructure_failure(self):
        self.prepare()
        self.gpu.side_effect = subprocess.TimeoutExpired(["nvidia-smi"], 10)
        with self.assertRaisesRegex(RuntimeError, "allocated_gpu_inventory_failed"):
            self.evaluate()

    def test_nonzero_scorer_retains_failure_receipt(self):
        self.prepare("raise SystemExit(7)")
        with self.assertRaisesRegex(RuntimeError, "local_scorer_exit_nonzero"):
            self.evaluate()
        self.assertEqual(json.loads((self.out / "gpu_receipt.json").read_text())["exit_code"], 7)
        self.assertFalse((self.out / "numeric_metrics.json").exists())

    def test_nonfinite_per_image_rejected(self):
        self.prepare("m['per_image'][0]['latent_mse']=float('nan')")
        with self.assertRaisesRegex(RuntimeError, "nonfinite_per_image_metric"):
            self.evaluate()


if __name__ == "__main__":
    unittest.main(verbosity=2)

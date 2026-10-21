"""Validate imported model assets and freeze every runtime source/data asset."""
from pathlib import Path
import hashlib
import json


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


weights = Path("/opt/onedc/weights")
metric_weights = Path("/opt/onedc/metric_weights")
metric_manifest = Path("/opt/onedc/grader/metric_assets.json")
for relative, value in json.loads(metric_manifest.read_text())["files"].items():
    path = metric_weights / relative
    if path.stat().st_size != value["size"] or digest(path) != value["sha256"]:
        raise SystemExit("Metric asset integrity failure: " + relative)
expected = json.loads((weights / "asset_manifest.json").read_text())
for relative, value in expected["files"].items():
    path = weights / relative
    if digest(path) != value["sha256"] or path.stat().st_size != value["size"]:
        raise SystemExit("Model asset integrity failure: " + relative)
paths = list(Path("/workspace/repo").rglob("*.py")) + list(Path("/workspace/repo").rglob("*.yaml"))
paths += list(Path("/workspace/repo").rglob("*.so")) + list(Path("/opt/onedc/grader").glob("*.py"))
paths += [Path("/opt/onedc/grader/public_anchors.json"), Path("/opt/onedc/grader/data_manifest.json")]
paths += [weights / relative for relative in expected["files"]]
paths += list(Path("/workspace/public_assets").rglob("*.png"))
paths += [Path("/workspace/evaluate.sh"), Path("/workspace/solution/solve.sh"),
          Path("/workspace/instruction.md"), Path("/opt/onedc/grader/solution_contract.json"),
          Path("/usr/local/bin/codex")]
paths += [Path("/usr/local/bin/codex-code-mode-host")]
paths += [metric_manifest, metric_weights / "dists.pt", Path("/usr/weights.pt")]
paths += list(Path('/opt/onedc/grader').glob('*.sh'))
manifest = Path("/opt/onedc/grader/frozen_hashes.txt")
manifest.write_text("".join(digest(p) + "  " + str(p) + "\n" for p in sorted(set(paths))))
print("Frozen runtime assets:", len(set(paths)))

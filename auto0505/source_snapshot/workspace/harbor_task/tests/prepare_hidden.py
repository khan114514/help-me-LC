"""Check the externally injected, frozen private split before formal scoring."""
import argparse
import hashlib
import json
from pathlib import Path


def verify_hidden(directory, manifest):
    expected = json.loads(Path(manifest).read_text())["files"]
    actual = {p.name for p in Path(directory).glob("*.png")}
    if actual != set(expected):
        raise ValueError("private split is missing or does not match the frozen manifest")
    for name, digest in expected.items():
        if hashlib.sha256((Path(directory) / name).read_bytes()).hexdigest() != digest:
            raise ValueError("private split fingerprint mismatch")
    return len(expected)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="/tests/hidden_assets")
    parser.add_argument("--manifest", default="/tests/hidden_manifest.json")
    args = parser.parse_args()
    print("[preflight] frozen private split verified:", verify_hidden(args.directory, args.manifest), "images")

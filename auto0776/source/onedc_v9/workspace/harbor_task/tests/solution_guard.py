"""Check the complete collected solution without executing candidate content."""
import hashlib
import json
from pathlib import Path


class ScopeViolation(ValueError):
    pass


def validate_solution(directory, contract_path):
    directory = Path(directory)
    contract = json.loads(Path(contract_path).read_text())
    if directory.is_symlink() or not directory.is_dir():
        raise ScopeViolation("Solution directory must be an ordinary directory")
    if {p.name for p in directory.iterdir()} != {"method.py", "solve.sh"}:
        raise ScopeViolation("Solution must contain exactly method.py and frozen solve.sh")
    for name in ("method.py", "solve.sh"):
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            raise ScopeViolation("Solution contains a symlink, non-file, or oversized file")
    if hashlib.sha256((directory / "solve.sh").read_bytes()).hexdigest() != contract["solve_sha256"]:
        raise ScopeViolation("Frozen solve.sh was modified")


if __name__ == "__main__":
    import sys
    try:
        validate_solution(sys.argv[1], sys.argv[2])
    except ScopeViolation as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(65)

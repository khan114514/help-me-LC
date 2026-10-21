"""Private orchestration utilities; no model credentials are persisted."""
import hashlib
import json
import os
import tempfile
import subprocess
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.atomic-')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def object_digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def tree_digest(root):
    root = Path(root).resolve()
    h = hashlib.sha256()
    for p in sorted(root.rglob('*')):
        if '.git' in p.relative_to(root).parts or '__pycache__' in p.relative_to(root).parts:
            continue
        if p.is_symlink():
            raise ValueError('task contains symlink; materialize frozen inputs first')
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + b'\0')
            h.update(bytes.fromhex(digest(p)))
    return h.hexdigest()


def evidence_path(directory, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError('evidence must be a relative file path')
    directory = Path(directory).resolve()
    p = (directory / relative).resolve()
    if directory not in p.parents or not p.is_file() or p.stat().st_size == 0:
        raise ValueError('missing, empty, or escaping evidence')
    return p


def clean_env():
    # Deliberate allowlist: no API keys, auth tokens, proxy credentials or actor secrets.
    names = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT', 'USER', 'LOGNAME')
    return {k: os.environ[k] for k in names if k in os.environ}


_CHILDREN = []


def detach(argv):
    """Keep Popen handles until reaped; children outlive the launching conversation."""
    reap()
    proc = subprocess.Popen(argv, env=clean_env(), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                            start_new_session=True)
    _CHILDREN.append(proc)
    return proc.pid


def reap():
    _CHILDREN[:] = [p for p in _CHILDREN if p.poll() is None]


def receipt(request, status, evidence, details=None):
    write(request['receipt_path'], {'status': status, 'revision': request['revision'],
          'contract_sha256': request['contract_sha256'], 'evidence': evidence,
          'details': details or {}})


def public_inspect(row):
    """Keep runtime facts without recording baked-in environment values."""
    result = {k: row[k] for k in ('Id', 'Image', 'Mounts', 'HostConfig', 'State', 'RestartCount') if k in row}
    config = row.get('Config', {})
    result['Config'] = {k: config.get(k) for k in ('Image', 'WorkingDir', 'User')}
    result['Config']['EnvironmentNames'] = [x.split('=', 1)[0] for x in config.get('Env', [])]
    return result

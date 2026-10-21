"""Organizer-only complete-line JSONL mirror; no model/API calls or credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import threading
from datetime import datetime, timezone

LIMIT = 64 * 1024 * 1024
REMOTE_ROOT = ('' + ('/' + 'root/') + 'rfsteps-v341-trusted-model-events-20261004')

def complete_snapshot(path):
    data = Path(path).read_bytes()
    if len(data) > LIMIT:
        raise ValueError("expert event log too large")
    # A concurrent append may end between bytes; never mirror partial JSON.
    data = data[:data.rfind(b"\n")+1]
    for line in data.splitlines():
        value = json.loads(line)
        if value.get("event") not in ("upstream_started", "model_request", "owned_transport_exited", "reverse_forward_up", "reverse_forward_outage", "reverse_forward_retry", "reverse_forward_retry_failed", "reverse_forward_recovery_exhausted", "reverse_forward_readiness_exhausted"):
            raise ValueError("unrecognized expert event")
    return data

def transfer(data, host):
    code = (
        "import os,stat,sys,uuid; from pathlib import Path; "
        f"root=Path({REMOTE_ROOT!r}); root.mkdir(mode=0o700,exist_ok=True); s=root.lstat(); "
        "assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700; "
        f"data=sys.stdin.buffer.read({LIMIT+1}); assert len(data)<={LIMIT}; "
        "p=root/('.events-'+uuid.uuid4().hex); fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); "
        "f=os.fdopen(fd,'wb'); f.write(data); f.flush(); os.fsync(f.fileno()); f.close(); "
        "os.replace(p,root/'model-events.jsonl'); fd=os.open(root,os.O_RDONLY); os.fsync(fd); os.close(fd)"
    )
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ClearAllForwardings=yes",
        "-o", "ConnectTimeout=10", host, shlex.join(["python3", "-c", code])],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
    if result.returncode != 0:
        raise RuntimeError("expert event transfer failed")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--control-host", default="root@118.195.251.134")
    args = parser.parse_args()
    os.umask(0o077); root=Path(args.evidence_dir); root.mkdir(parents=True,exist_ok=False)
    halt=threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):signal.signal(sig,lambda *_:halt.set())
    previous=None; failures=0
    def emit(record):
        record={"utc":datetime.now(timezone.utc).isoformat(),**record}
        with (root/"mirror-events.jsonl").open("a") as f:
            f.write(json.dumps(record)+"\n"); f.flush(); os.fsync(f.fileno())
    while not halt.is_set():
        try:
            data=complete_snapshot(args.source); digest=hashlib.sha256(data).hexdigest()
            if digest!=previous:
                transfer(data,args.control_host)
                emit({"event":"snapshot_mirrored","bytes":len(data),"sha256":digest,
                      "remote_root":REMOTE_ROOT,"source":args.source,"research_time_credit":0})
                if previous is None:print(json.dumps({"ready":True,"remote_root":REMOTE_ROOT,"pid":os.getpid()}),flush=True)
                previous=digest
            failures=0
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            failures+=1; emit({"event":"mirror_failure","error_type":type(error).__name__,"consecutive":failures})
            if failures>=3:return 2
        halt.wait(2)
    emit({"event":"shutdown_requested"});return 0

if __name__=="__main__":raise SystemExit(main())

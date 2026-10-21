"""Independent 12h Docker stability evidence. Never research/model/GPU time.

This implementation is not a completed stability check. Invoke only after review.
Uses the actual Harbor Trial construction for frozen task/mount/network semantics,
then DockerEnvironment.start/exec/stop without agent setup/run or verification.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shlex
import stat
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

TASK_CHECKSUM = "90bb7746559319dc6ce29dbbfae946f9a6b00694ef04b25d267f7def8c8249cb"
PERIOD_SECONDS = 60
DURATION_SECONDS = 43200
MAX_SAMPLE_GAP_SECONDS = 75

PROBE = ("\nimport json,os,pathlib,stat,sys,time\nc=json.loads(sys.argv[1]); token=c['token']; role=c['role']\np=pathlib.Path('/workspace/agent-output')/('.stability-'+token)\ndata=('rfsteps-stability:'+token).encode()\nfd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)\ntry:\n os.write(fd,data);os.fsync(fd)\nfinally: os.close(fd)\ntry:\n if p.read_bytes()!=data: raise RuntimeError('small read/write mismatch')\nfinally: p.unlink()\nforbidden=['/tests','/solution','" + ('/' + 'root/') + "private_hidden_assets',\n '/run/rfsteps/formal.sock','/run/rfsteps-model/'+('seed' if role=='gpt' else 'gpt')+'.sock',\n '/var/run/docker.sock','" + ('/' + 'root/') + ".codex/auth.json']\nfound=[x for x in forbidden if os.path.lexists(x)]\npublic=pathlib.Path('/run/rfsteps/public.sock').lstat()\nown=pathlib.Path('/run/rfsteps-model')/(role+'.sock'); model=own.lstat()\nok_public=stat.S_ISSOCK(public.st_mode)\nok_model=stat.S_ISSOCK(model.st_mode) and model.st_uid==0 and stat.S_IMODE(model.st_mode)==0o600\nsole_model=sorted(x.name for x in own.parent.iterdir())==[role+'.sock']\nresult={'container_monotonic_ns':time.monotonic_ns(),'rw_ok':True,\n 'forbidden_paths_present':found,'public_socket_exists':ok_public,\n 'public_socket_inode':public.st_ino,'model_socket_exists':ok_model,\n 'model_socket_inode':model.st_ino,'sole_model_socket':sole_model}\nprint(json.dumps(result))\nif found or not ok_public or not ok_model or not sole_model: sys.exit(2)\n")

INSPECT_TEMPLATE = (
    '{"container_id":{{json .Id}},"image_id":{{json .Image}},'
    '"restarts":{{json .RestartCount}},"running":{{json .State.Running}},'
    '"oom_killed":{{json .State.OOMKilled}},"started_at":{{json .State.StartedAt}},'
    '"nano_cpus":{{json .HostConfig.NanoCpus}},"cpu_quota":{{json .HostConfig.CpuQuota}},'
    '"cpu_period":{{json .HostConfig.CpuPeriod}},"memory_bytes":{{json .HostConfig.Memory}},'
    '"readonly_rootfs":{{json .HostConfig.ReadonlyRootfs}},'
    '"cap_drop":{{json .HostConfig.CapDrop}},"cap_add":{{json .HostConfig.CapAdd}},'
    '"security_opt":{{json .HostConfig.SecurityOpt}},'
    '"network_mode":{{json .HostConfig.NetworkMode}},"mounts":{{json .Mounts}}}'
)


def check_host_socket(path: Path, *, role: str | None):
    s = path.lstat()
    if not stat.S_ISSOCK(s.st_mode) or s.st_uid != 0:
        raise ValueError("socket must be a root-owned actual UDS")
    if role is not None and (path.name != role + ".sock" or stat.S_IMODE(s.st_mode) != 0o600):
        raise ValueError("own model socket must be role.sock mode 0600")
    return {"path": str(path), "inode": s.st_ino, "uid": s.st_uid,
            "mode": oct(stat.S_IMODE(s.st_mode))}


def validate_sample(sample: dict, first: dict | None):
    if not sample["running"] or sample["oom_killed"] or sample["restarts"] != 0:
        raise RuntimeError("container stopped, restarted or OOM-killed")
    if first and (sample["container_id"], sample["image_id"], sample["started_at"]) != (
            first["container_id"], first["image_id"], first["started_at"]):
        raise RuntimeError("container/image/start identity changed")
    cpu_ok = sample["nano_cpus"] == 2_000_000_000 or (
        sample["cpu_period"] > 0 and sample["cpu_quota"] == 2 * sample["cpu_period"])
    if not cpu_ok or sample["memory_bytes"] != 2048 * 1024 * 1024:
        raise RuntimeError("frozen 2CPU/2048MB limits are not enforced")
    if not sample["readonly_rootfs"] or set(sample["cap_drop"] or []) != {"ALL"}:
        raise RuntimeError("frozen read-only/capability isolation changed")
    # Docker 29 inspect returns CAP_SETUID/CAP_SETGID for Compose SETUID/SETGID.
    if {c.removeprefix("CAP_") for c in (sample["cap_add"] or [])} != {"SETUID", "SETGID"}:
        raise RuntimeError("frozen capability allowance changed")
    if "no-new-privileges:true" not in (sample["security_opt"] or []):
        raise RuntimeError("no-new-privileges not enforced")


async def inspect_container(environment):
    # Exact own Compose project/service, never a global container search.
    result = await environment._run_docker_compose_command(["ps", "-q", "main"], timeout_sec=15)
    cid = (result.stdout or "").strip()
    if not re.fullmatch(r"[0-9a-f]{12,64}", cid):
        raise RuntimeError("own compose main container identity unavailable")
    process = await asyncio.create_subprocess_exec(
        "docker", "inspect", "--format", INSPECT_TEMPLATE, cid,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), 15)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    if process.returncode != 0 or len(output) > 256 * 1024:
        raise RuntimeError("bounded own-container inspection failed")
    return json.loads(output)


async def observe(environment, emit, role: str, *, duration=DURATION_SECONDS,
                  period=PERIOD_SECONDS, max_gap=MAX_SAMPLE_GAP_SECONDS,
                  monotonic=time.monotonic, sleep=asyncio.sleep, verify_host_sources=None):
    """Injectable clock only for CPU fixture; CLI always fixes 43200s/60s."""
    start = monotonic(); previous = None; first = None; count = 0
    while True:
        current = monotonic()
        if previous is not None and current - previous > max_gap:
            raise RuntimeError("stability heartbeat gap exceeds evidence bound")
        if verify_host_sources is not None:
            verify_host_sources()
        inspect = await inspect_container(environment)
        validate_sample(inspect, first)
        result = await environment.exec(
            command="python3 -c " + shlex.quote(PROBE) + " " +
                    shlex.quote(json.dumps({"role": role, "token": uuid.uuid4().hex})),
            user="root", timeout_sec=15)
        if result.return_code != 0:
            raise RuntimeError("small read/write or forbidden/socket probe failed")
        probe = json.loads(result.stdout or "")
        # Assert even a malformed/incorrectly-successful exec cannot produce success.
        if (not probe.get("rw_ok") or probe.get("forbidden_paths_present") or
                not all(probe.get(k) for k in (
                    "public_socket_exists", "model_socket_exists", "sole_model_socket"))):
            raise RuntimeError("probe receipt failed its positive/negative contract")
        if first is None:
            first = inspect
        count += 1
        emit({"event": "stability_sample", "sample_index": count,
              "monotonic_seconds": current, "elapsed_stability_seconds": current-start,
              "research_effective_seconds": 0, "container": inspect, "probe": probe})
        previous = current
        elapsed = monotonic() - start
        if elapsed >= duration:
            return {"continuous_stability_seconds": elapsed, "sample_count": count,
                    "research_effective_seconds": 0, "status": "COMPLETE"}
        next_due = start + count * period
        await sleep(max(0, min(next_due, start+duration)-monotonic()))


async def run(args):
    from dirhash import dirhash
    from harbor.environments.docker.docker import DockerEnvironment
    from harbor.models.trial.config import TrialConfig
    from harbor.trial.trial import Trial

    task = Path(args.task_dir).resolve()
    output = Path(args.output_dir).resolve()
    if output == task or task in output.parents:
        raise ValueError("stability records must be outside the frozen task")
    if dirhash(task, "sha256") != TASK_CHECKSUM:
        raise ValueError("frozen task checksum mismatch")
    public_root = Path(args.public_socket_root).resolve()
    own_model = Path(args.model_socket).absolute()
    sockets = {"public": check_host_socket(public_root/"public.sock", role=None),
               "model": check_host_socket(own_model, role=args.role)}
    output.mkdir(parents=True, exist_ok=False)
    os.environ["RFSTEPS_SOCKET_ROOT"] = str(public_root)
    config = TrialConfig.model_validate({
        "task": {"path": str(task)}, "trial_name": "stability-"+args.role+"-"+uuid.uuid4().hex,
        "trials_dir": str(output/"harbor-construction"), "agent": {"name": "nop"},
        "environment": {"type": "docker", "delete": False,
            "kwargs": {"keep_containers": False}, "mounts": [{"type": "bind",
                "source": str(own_model), "target": "/run/rfsteps-model/"+args.role+".sock",
                "read_only": True}]},
    })
    trial = await Trial.create(config)
    environment = trial.agent_environment
    if not isinstance(environment, DockerEnvironment):
        raise RuntimeError("stability runner requires the actual DockerEnvironment")
    env_cfg = trial.task.config.environment
    if (env_cfg.cpus, env_cfg.memory_mb, env_cfg.storage_mb, env_cfg.gpus) != (2, 2048, 8192, 0):
        raise RuntimeError("frozen task resources mismatch")
    if environment.network_policy.network_mode.value != "public":
        raise RuntimeError("frozen agent network policy mismatch")
    def emit(record):
        record = {"utc": datetime.now(timezone.utc).isoformat(), **record}
        with (output/"stability.jsonl").open("a") as file:
            file.write(json.dumps(record, separators=(",", ":"), allow_nan=False)+"\n")
            file.flush(); os.fsync(file.fileno())
    emit({"event": "stability_plan", "control_task_checksum": TASK_CHECKSUM,
          "duration_seconds": DURATION_SECONDS, "period_seconds": PERIOD_SECONDS,
          "separate_from_research": True, "research_effective_seconds": 0,
          "scope": "container continuity, resources, isolation, file IO and unchanged UDS identity; does not prove continuous RPC availability",
          "socket_metadata": sockets, "trial_id": str(trial.id),
          "task_resources": {"cpus": 2, "memory_mb": 2048, "storage_mb": 8192, "gpus": 0},
          "network_policy": "public", "environment_class": type(environment).__name__,
          "agent_setup_run_or_verification": False})
    summary = {"status": "INFRA_ERROR", "research_effective_seconds": 0}
    def verify_host_sources():
        actual = {"public": check_host_socket(public_root/"public.sock", role=None),
                  "model": check_host_socket(own_model, role=args.role)}
        if actual != sockets:
            raise RuntimeError("host socket source disappeared or changed inode")
    try:
        await environment.start(force_build=False)
        summary = await observe(environment, emit, args.role, verify_host_sources=verify_host_sources)
    except BaseException as exc:
        summary["error_type"] = type(exc).__name__
        raise
    finally:
        emit({"event": "stability_end", **summary})
        try:
            await asyncio.shield(environment.stop(delete=False))
            emit({"event": "own_environment_stopped", "delete": False,
                  "keep_containers": False, "semantics": "compose down"})
        finally:
            (output/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
            trial._close_logger_handler()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--public-socket-root", required=True)
    parser.add_argument("--model-socket", required=True)
    parser.add_argument("--role", choices=("gpt", "seed"), required=True)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()

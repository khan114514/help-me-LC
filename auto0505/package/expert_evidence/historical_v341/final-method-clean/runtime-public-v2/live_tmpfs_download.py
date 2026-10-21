"""Exact-instance Harbor Docker live tmpfs reads. No model/GPU/research work."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import shutil
import stat
import struct
import tarfile
import tempfile
import time
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOTS = ("/workspace/solution", "/workspace/agent-output")
MAX_ENTRIES = 4096
MAX_BYTES = 128 * 1024 * 1024
MAX_HEADER = 8 * 1024 * 1024
MAX_ARCHIVE = MAX_BYTES + MAX_ENTRIES * 2048 + 10240
MAX_WIRE = MAX_HEADER + MAX_ARCHIVE + 64
TIMEOUT_SECONDS = 45
MAGIC = b"RFSTEPS-LIVE-TAR1\n"

# Fixed trusted stdlib reader only. It never imports or executes submitted code.
# Every container read is under an allowed root via O_NOFOLLOW directory FDs.
READER = r'''
import hashlib,io,json,os,stat,struct,sys,tarfile
ROOTS=('/workspace/solution','/workspace/agent-output');LIMIT=128*1024*1024;COUNT=4096
source,kind=sys.argv[1:];source=source[:-1] if source.endswith('/') else source
if kind not in ('file','dir') or not any(source==r or source.startswith(r+'/') for r in ROOTS):raise RuntimeError('source_not_allowed')
parts=source.split('/')[1:]
if any(not p or p in ('.','..') or '\\' in p or any(ord(c)<32 for c in p) for p in parts):raise RuntimeError('source_invalid')
def cname(p):
 if not p or p in ('.','..') or '\\' in p or any(ord(c)<32 for c in p):raise RuntimeError('entry_invalid')
def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(value):return hashlib.sha256(value).hexdigest()
def open_source():
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
 try:
  for index,p in enumerate(parts):
   flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
   if index<len(parts)-1 or kind=='dir':flags|=os.O_DIRECTORY
   new=os.open(p,flags,dir_fd=fd);os.close(fd);fd=new
  return fd
 except BaseException:os.close(fd);raise
def collect(retain):
 entries=[];payload={};total=0
 def add(entry):
  if len(entry['path'])>1024:raise RuntimeError('entry_path_too_long')
  entries.append(entry)
  if len(entries)>COUNT:raise RuntimeError('entry_limit')
 def regular(fd,path):
  nonlocal total
  before=os.fstat(fd)
  if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1:raise RuntimeError('regular_single_link_required')
  if before.st_size>LIMIT-total:raise RuntimeError('byte_limit')
  digest=hashlib.sha256();chunks=[];size=0
  while True:
   chunk=os.read(fd,65536)
   if not chunk:break
   size+=len(chunk)
   if size>LIMIT-total:raise RuntimeError('byte_limit')
   digest.update(chunk)
   if retain:chunks.append(chunk)
  after=os.fstat(fd)
  fields=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  if size!=before.st_size or fields(before)!=fields(after):raise RuntimeError('file_changed_during_read')
  total+=size;add({'path':path,'type':'file','bytes':size,'sha256':digest.hexdigest()})
  if retain:payload[path]=b''.join(chunks)
 def directory(fd,prefix):
  for name in sorted(os.listdir(fd)):
   cname(name);path=prefix+name;s=os.stat(name,dir_fd=fd,follow_symlinks=False)
   if stat.S_ISDIR(s.st_mode):
    add({'path':path,'type':'dir'});child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
    try:directory(child,path+'/')
    finally:os.close(child)
   elif stat.S_ISREG(s.st_mode):
    child=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    try:regular(child,path)
    finally:os.close(child)
   else:raise RuntimeError('special_or_link_entry_rejected')
 fd=open_source()
 try:
  if kind=='dir':directory(fd,'')
  else:regular(fd,parts[-1])
 finally:os.close(fd)
 if not any(e['type']=='file' for e in entries):raise RuntimeError('empty_regular_file_inventory')
 return sorted(entries,key=lambda e:e['path']),payload,total
before,_,total=collect(False);entries,payload,total2=collect(True)
if before!=entries or total!=total2:raise RuntimeError('source_changed_before_tar')
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w',format=tarfile.PAX_FORMAT) as archive:
 for entry in entries:
  info=tarfile.TarInfo(entry['path']);info.uid=info.gid=0;info.mtime=0
  if entry['type']=='dir':info.type=tarfile.DIRTYPE;info.mode=0o700;archive.addfile(info)
  else:info.type=tarfile.REGTYPE;info.mode=0o600;info.size=entry['bytes'];archive.addfile(info,io.BytesIO(payload[entry['path']]))
after,_,total3=collect(False)
if after!=before or total3!=total:raise RuntimeError('source_changed_after_tar')
data=buffer.getvalue()
if len(data)>LIMIT+COUNT*2048+10240:raise RuntimeError('archive_limit')
header={'schema_version':1,'source':source,'kind':kind,'entries':entries,'total_bytes':total,
 'live_before_inventory_sha256':sha(canon(before)),'live_after_inventory_sha256':sha(canon(after)),
 'archive_sha256':sha(data),'regular_files':sum(e['type']=='file' for e in entries)}
encoded=canon(header)
if len(encoded)>8*1024*1024:raise RuntimeError('header_limit')
out=sys.stdout.buffer;out.write(b'RFSTEPS-LIVE-TAR1\n'+struct.pack('!Q',len(encoded))+encoded+data);out.flush()
'''


class DownloadRejected(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def selected_source(source):
    if not isinstance(source, str):
        raise DownloadRejected("source_type")
    value = source[:-1] if source.endswith("/") else source
    if not any(value == root or value.startswith(root+"/") for root in ROOTS):
        return None
    parts = value.split("/")[1:]
    if any(not p or p in (".", "..") or "\\" in p or any(ord(c) < 32 for c in p) for p in parts):
        raise DownloadRejected("source_path_invalid")
    return value


def entry_path(value):
    if (not isinstance(value, str) or not value or len(value) > 1024 or value.startswith("/")
            or "\\" in value or any(ord(c) < 32 for c in value)
            or any(p in ("", ".", "..") for p in value.split("/"))):
        raise DownloadRejected("archive_path_invalid")
    return value


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise DownloadRejected("duplicate_json_key")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(DownloadRejected("nonfinite_json")))


def decode_wire(data, source, kind):
    if len(data) > MAX_WIRE or not data.startswith(MAGIC) or len(data) < len(MAGIC)+8:
        raise DownloadRejected("wire_frame_invalid")
    size = struct.unpack("!Q", data[len(MAGIC):len(MAGIC)+8])[0]
    if size <= 0 or size > MAX_HEADER or len(data) < len(MAGIC)+8+size:
        raise DownloadRejected("wire_header_limit")
    header = strict_json(data[len(MAGIC)+8:len(MAGIC)+8+size])
    archive = data[len(MAGIC)+8+size:]
    if (not isinstance(header, dict) or set(header) != {"schema_version", "source", "kind", "entries", "total_bytes",
            "live_before_inventory_sha256", "live_after_inventory_sha256", "archive_sha256", "regular_files"}
            or type(header.get("schema_version")) is not int or header.get("schema_version") != 1
            or type(header.get("total_bytes")) is not int or type(header.get("regular_files")) is not int
            or header.get("source") != source
            or header.get("kind") != kind or len(archive) > MAX_ARCHIVE
            or sha(archive) != header.get("archive_sha256")):
        raise DownloadRejected("wire_identity_or_archive_hash")
    entries = header.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ENTRIES:
        raise DownloadRejected("inventory_entry_limit")
    seen = set(); total = 0; files = 0
    for entry in entries:
        name = entry_path(entry.get("path"))
        if name in seen:
            raise DownloadRejected("inventory_duplicate")
        seen.add(name)
        if entry.get("type") == "dir" and set(entry) == {"path", "type"}:
            continue
        if (set(entry) != {"path", "type", "bytes", "sha256"} or entry.get("type") != "file"
                or type(entry["bytes"]) is not int or entry["bytes"] < 0
                or not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
            raise DownloadRejected("inventory_regular_entry_invalid")
        total += entry["bytes"]; files += 1
    inventory_sha = sha(canonical(entries))
    if (entries != sorted(entries, key=lambda e: e["path"]) or not files or total > MAX_BYTES
            or total != header.get("total_bytes") or files != header.get("regular_files")
            or inventory_sha != header.get("live_before_inventory_sha256")
            or inventory_sha != header.get("live_after_inventory_sha256")):
        raise DownloadRejected("inventory_size_or_source_hash")
    if kind == "file" and (files != 1 or len(entries) != 1 or entries[0]["path"] != PurePosixPath(source).name):
        raise DownloadRejected("file_inventory_mismatch")
    return header, archive


def host_inventory(root):
    root = Path(root); entries = []
    for path in sorted(root.rglob("*")):
        mode = path.lstat()
        name = path.relative_to(root).as_posix(); entry_path(name)
        if stat.S_ISDIR(mode.st_mode):
            entries.append({"path": name, "type": "dir"})
        elif stat.S_ISREG(mode.st_mode) and mode.st_nlink == 1:
            entries.append({"path": name, "type": "file", "bytes": mode.st_size, "sha256": sha(path.read_bytes())})
        else:
            raise DownloadRejected("host_special_or_link_entry")
    return sorted(entries, key=lambda e: e["path"])


def check_host_ancestry(path):
    for component in [Path(path), *Path(path).parents]:
        if component.is_symlink():
            raise DownloadRejected("host_symlink_path")


def extract_verified(header, data, target):
    target = Path(os.path.abspath(target)); check_host_ancestry(target)
    if header["kind"] == "file" and target.is_dir():
        target = target/PurePosixPath(header["source"]).name
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True); check_host_ancestry(target)
    if header["kind"] == "dir" and target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise DownloadRejected("host_directory_target_not_empty")
    if header["kind"] == "file" and target.exists() and not target.is_file():
        raise DownloadRejected("host_file_target_not_regular")
    staging = Path(tempfile.mkdtemp(prefix=".rfsteps-live-", dir=target.parent)); staging.chmod(0o700)
    unpack = staging/"data"; unpack.mkdir(mode=0o700)
    expected = {entry["path"]: entry for entry in header["entries"]}; seen = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            for item in archive:
                name = entry_path(item.name)
                if name in seen or name not in expected or len(seen) >= MAX_ENTRIES:
                    raise DownloadRejected("tar_extra_or_duplicate_entry")
                seen.add(name); entry = expected[name]; path = unpack/name
                check_host_ancestry(path)
                if item.isdir() and entry["type"] == "dir" and item.size == 0:
                    path.mkdir(mode=0o700, parents=True, exist_ok=True)
                elif item.isreg() and not item.issparse() and entry["type"] == "file" and item.size == entry["bytes"]:
                    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True); check_host_ancestry(path)
                    stream = archive.extractfile(item)
                    if stream is None:
                        raise DownloadRejected("tar_regular_bytes_missing")
                    digest = hashlib.sha256(); size = 0
                    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, "wb") as output:
                        while chunk := stream.read(65536):
                            size += len(chunk)
                            if size > entry["bytes"]:
                                raise DownloadRejected("tar_file_size_overflow")
                            digest.update(chunk); output.write(chunk)
                        output.flush(); os.fsync(output.fileno())
                    if size != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
                        raise DownloadRejected("tar_regular_hash_mismatch")
                else:
                    raise DownloadRejected("tar_link_or_special_entry")
        if seen != set(expected) or host_inventory(unpack) != header["entries"]:
            raise DownloadRejected("host_staged_inventory_mismatch")
        if header["kind"] == "dir":
            os.replace(unpack, target)
            inventory = host_inventory(target)
        else:
            name = header["entries"][0]["path"]
            os.replace(unpack/name, target)
            inventory = [{"path": name, "type": "file", "bytes": target.stat().st_size,
                          "sha256": sha(target.read_bytes())}]
        if inventory != header["entries"]:
            raise DownloadRejected("host_published_inventory_mismatch")
        return target, sha(canonical(inventory))
    finally:
        shutil.rmtree(staging)


class LiveTmpfsDownload:
    def __init__(self, environment, report_root):
        self.environment = environment
        self.original_download_file = environment.download_file
        self.original_download_dir = environment.download_dir
        self.report_root = Path(os.path.abspath(report_root)); check_host_ancestry(self.report_root)
        self.report_root.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.container_id = None
        self.final_submission_inventory = None
        self.lock = asyncio.Lock()
        self.source_sha256 = sha(Path(__file__).read_bytes())

    def pin_final_submission(self, source):
        inventory = host_inventory(source)
        if (len(inventory) != 2 or {entry["path"] for entry in inventory} != {"method.py", "solve.sh"}
                or any(entry["type"] != "file" for entry in inventory)):
            raise DownloadRejected("final_submission_inventory_invalid")
        if self.final_submission_inventory is not None and self.final_submission_inventory != inventory:
            raise DownloadRejected("final_submission_pin_changed")
        self.final_submission_inventory = inventory
        return sha(canonical(inventory))

    def check_final_submission(self, source, kind, header):
        if self.final_submission_inventory is None or not (source == ROOTS[0] or source.startswith(ROOTS[0]+"/")):
            return
        if source == ROOTS[0] and kind == "dir":
            expected = self.final_submission_inventory
        else:
            relative = source[len(ROOTS[0])+1:]
            expected = [entry for entry in self.final_submission_inventory if entry["path"] == relative]
            if kind != "file" or len(expected) != 1:
                raise DownloadRejected("final_submission_source_not_bound")
        if header["entries"] != expected:
            raise DownloadRejected("final_submission_live_bytes_changed")

    async def own_cid(self):
        result = await self.environment._run_docker_compose_command(["ps", "-q", "main"], timeout_sec=15)
        value = (result.stdout or "").strip()
        if result.return_code != 0 or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise DownloadRejected("own_compose_container_id_invalid")
        if self.container_id is not None and value != self.container_id:
            raise DownloadRejected("own_container_identity_changed")
        self.container_id = value
        return value

    async def capture(self, cid, source, kind):
        command = type(self.environment)._engine_cmd("exec", "-u", "root", cid,
            "/usr/bin/python3", "-I", "-c", READER, source, kind)
        process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        async def bounded(stream, limit):
            buffer = bytearray()
            while chunk := await stream.read(65536):
                buffer.extend(chunk)
                if len(buffer) > limit:
                    raise DownloadRejected("live_reader_output_limit")
            return bytes(buffer)
        try:
            output, _ = await asyncio.gather(bounded(process.stdout, MAX_WIRE), bounded(process.stderr, 65536))
            await process.wait()
            if process.returncode != 0:
                raise DownloadRejected("live_reader_failed")
            return output
        finally:
            if process.returncode is None:
                # Only the child created by this exact invocation, never PID search.
                process.kill(); await process.wait()

    def record(self, record):
        path = self.report_root/(uuid.uuid4().hex+".json")
        data = canonical({"schema_version": 1, "utc": datetime.now(timezone.utc).isoformat(),
             "adapter_source_sha256": self.source_sha256, "research_credit_seconds": 0, **record})+b"\n"
        fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(data); output.flush(); os.fsync(output.fileno())

    async def download(self, source, target, kind):
        normalized = selected_source(source)
        if normalized is None:
            original = self.original_download_file if kind == "file" else self.original_download_dir
            return await original(source, target)
        started = time.monotonic()
        try:
            async with asyncio.timeout(TIMEOUT_SECONDS):
                async with self.lock:
                    cid = await self.own_cid()
                    output = await self.capture(cid, normalized, kind)
                    header, archive = decode_wire(output, normalized, kind)
                    self.check_final_submission(normalized, kind, header)
                    if await self.own_cid() != cid:
                        raise DownloadRejected("own_container_identity_changed")
                    target, host_sha = extract_verified(header, archive, target)
                    if time.monotonic()-started > TIMEOUT_SECONDS:
                        raise DownloadRejected("live_download_deadline")
                    self.record({"status": "COMPLETE", "source": normalized, "kind": kind,
                        "container_id": cid, "target": str(target), "live_inventory": header["entries"],
                        "live_before_inventory_sha256": header["live_before_inventory_sha256"],
                        "live_after_inventory_sha256": header["live_after_inventory_sha256"],
                        "host_inventory_sha256": host_sha, "total_bytes": header["total_bytes"],
                        "final_submission_inventory_sha256": sha(canonical(self.final_submission_inventory)) if self.final_submission_inventory is not None else None,
                        "regular_files": header["regular_files"], "archive_sha256": header["archive_sha256"]})
        except BaseException as error:
            self.record({"status": "FAILED", "source": normalized, "kind": kind,
                         "container_id": self.container_id, "reason": str(error) if isinstance(error, DownloadRejected) else type(error).__name__})
            raise


def install_live_downloads(environment, report_root):
    from harbor.environments.docker.docker import DockerEnvironment
    if not isinstance(environment, DockerEnvironment):
        raise DownloadRejected("exact_owned_docker_environment_required")
    previous = getattr(environment, "_rfsteps_live_tmpfs_download", None)
    if previous is not None:
        if previous.environment is not environment or previous.report_root != Path(os.path.abspath(report_root)):
            raise DownloadRejected("instance_adapter_binding_mismatch")
        return previous
    adapter = LiveTmpfsDownload(environment, report_root)
    async def download_file(bound, source_path, target_path):
        if bound is not adapter.environment:
            raise DownloadRejected("instance_identity_mismatch")
        return await adapter.download(source_path, target_path, "file")
    async def download_dir(bound, source_dir, target_dir):
        if bound is not adapter.environment:
            raise DownloadRejected("instance_identity_mismatch")
        return await adapter.download(source_dir, target_dir, "dir")
    environment.download_file = types.MethodType(download_file, environment)
    environment.download_dir = types.MethodType(download_dir, environment)
    environment._rfsteps_live_tmpfs_download = adapter
    return adapter

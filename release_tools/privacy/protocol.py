"""Local strict privacy protocol extension; provenance.json records its source.

No official upstream protocol.py was available. This extension implements the
published privacy contract and keeps upstream classifications without waivers.
Matched content and absolute input locations never appear in diagnostics.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
import re
import stat
import sys
sys.dont_write_bytecode = True
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import privacy_scan_upstream as upstream

MAX_FILE_BYTES=256*1024*1024
MAX_MEMBER_BYTES=32*1024*1024
MAX_ARCHIVE_BYTES=256*1024*1024
MAX_ARCHIVE_MEMBERS=10000
MAX_ARCHIVE_DEPTH=2
MAX_TOTAL_BYTES=1024*1024*1024
MAX_TOTAL_FILES=20000
UNSUPPORTED={'.tar','.gz','.bz2','.xz','.7z','.rar','.tgz'}
EXTRA_PATTERNS={
    'ROOT_HOME':re.compile(r'/'+r'root/'),
    'SSH_ENDPOINT':re.compile(r'(?:ssh|scp|sftp)://[^\s<>"\x27]+|\b[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+:(?:/|~)',re.I),
    'INTERNAL_DOMAIN':re.compile(r'\b[A-Za-z0-9_.-]+\.(?:internal|intranet|corp|lan|local)(?::\d+)?\b',re.I),
    'ABSOLUTE_REPORT_ROOT':re.compile(r'(?i)["\x27]?(?:source\.path|workspace_root|inspected_root|submission_root)["\x27]?\s*[:=]\s*["\x27]?(?:/|[A-Z]:\\)'),
    'COOKIE_VALUE':re.compile(r'(?i)\b(?:cookie|set-cookie)\s*:\s*(?![<$\[{])[^\s]+=[^\s;]+'),
}


def explicit_placeholder(value):
    value=value.strip().strip('"\x27')
    if not value:return True
    if value.upper() in {'REDACTED','YOUR_API_KEY','YOUR-API-KEY'}:return True
    return bool(re.fullmatch(r'(?:\$\{[A-Za-z0-9_]+\}|\$[A-Za-z_][A-Za-z0-9_]*|<[A-Za-z0-9_. -]+>|\{\{[A-Za-z0-9_. ]+\}\})',value))


# Tighten upstream example exceptions to explicit, unusable placeholders.
# No broad substring such as "redacted" or "your_" exempts a real value.
upstream._is_placeholder=explicit_placeholder
upstream.CREDENTIAL_ASSIGNMENT=re.compile(upstream.CREDENTIAL_ASSIGNMENT.pattern.replace(';}', ';'))
upstream.CAPABILITY_KEYS.update({'api_key','apikey','file_token','download_token','x-amz-security-token','x-goog-security-token'})


@dataclass(frozen=True)
class Finding:
    code:str
    path:str
    line:int=0


class Scan:
    def __init__(self):
        self.findings=set();self.bytes=0;self.files=0;self.manifest=[]

    def add(self,code,path,line=0):self.findings.add(Finding(code,path,line))

    def text(self,text,path):
        for f in upstream._scan_text(text,Path('artifact')):self.add(f.code,path,f.line)
        for number,line in enumerate(text.splitlines(),1):
            for code,pattern in EXTRA_PATTERNS.items():
                if pattern.search(line):self.add(code,path,number)
            # URL authority carrying a username can also be a capability.
            for match in upstream.URL_PATTERN.finditer(line):
                try:v=upstream.urlsplit(match.group(0).rstrip('.,;:)'))
                except ValueError:continue
                if v.username and not upstream._is_placeholder(v.username):self.add('URL_AUTHORITY_CREDENTIAL',path,number)

    def name(self,name,path,archive=False):
        for f in upstream._scan_name(name,Path('artifact'),'member' if archive else None):self.add(f.code,path,f.line)
        # Windows absolute and drive-prefixed archive paths are unsafe too.
        if archive and re.match(r'^(?:[A-Za-z]:|\\|/)',name):self.add('UNSAFE_ARCHIVE_PATH',path)
        self.text(name,path)

    def payload(self,data,name,path,depth=0):
        self.files+=1;self.bytes+=len(data)
        if self.files>MAX_TOTAL_FILES:self.add('TOTAL_FILE_LIMIT',path);return
        if self.bytes>MAX_TOTAL_BYTES:self.add('TOTAL_SCAN_SIZE_LIMIT',path);return
        self.manifest.append({'path':self.locator(path),'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data)})
        suffix=Path(name).suffix.lower()
        archive=suffix in upstream.ARCHIVE_SUFFIXES or data.startswith((b'PK\x03\x04',b'PK\x05\x06',b'PK\x07\x08'))
        if archive:
            if depth>MAX_ARCHIVE_DEPTH:self.add('ARCHIVE_DEPTH_LIMIT',path);return
            self.archive(data,path,depth);return
        if suffix in UNSUPPORTED or data.startswith((b'\x1f\x8b',b'7z\xbc\xaf\x27\x1c',b'Rar!')):
            self.add('UNSUPPORTED_RELEASE_CONTAINER',path);return
        decoded=upstream._decode_text(data,suffix)
        if decoded is not None:self.text(decoded,path)
        # Always inspect ASCII and both UTF-16 byte orders, even when a file
        # happens to decode as UTF-8. Printable metadata cannot evade by suffix.
        fragments=[m.group(0).decode('ascii') for m in upstream.ASCII_STRING.finditer(data)] if decoded is None else []
        fragments.extend(m.group(0).decode('utf-16-le') for m in upstream.UTF16_LE_STRING.finditer(data))
        fragments.extend(m.group(0).decode('utf-16-be') for m in upstream.UTF16_BE_STRING.finditer(data))
        self.text('\n'.join(fragments),path)

    def archive(self,data,path,depth):
        try:z=zipfile.ZipFile(io.BytesIO(data))
        except (OSError,ValueError,zipfile.BadZipFile):self.add('ARCHIVE_UNREADABLE',path);return
        with z:
            infos=z.infolist()
            if len(infos)>MAX_ARCHIVE_MEMBERS:self.add('ARCHIVE_MEMBER_LIMIT',path);return
            if sum(i.file_size for i in infos)>MAX_ARCHIVE_BYTES:self.add('ARCHIVE_SIZE_LIMIT',path);return
            self.metadata(z.comment,path+'!@archive-comment')
            seen=set()
            for info in infos:
                child=path+'!'+info.filename
                self.name(info.filename,child,True)
                if info.filename in seen:self.add('ARCHIVE_DUPLICATE_MEMBER',child)
                seen.add(info.filename)
                self.metadata(info.comment+info.extra,child+'!@metadata')
                mode=(info.external_attr>>16)&0o170000
                if mode==stat.S_IFLNK:self.add('ARCHIVE_SYMLINK',child);continue
                if mode not in (0,stat.S_IFREG,stat.S_IFDIR):self.add('ARCHIVE_SPECIAL_FILE',child);continue
                if info.flag_bits&1:self.add('ARCHIVE_ENCRYPTED',child);continue
                if info.is_dir():continue
                if info.file_size>MAX_MEMBER_BYTES:self.add('ARCHIVE_MEMBER_SIZE_LIMIT',child);continue
                try:
                    with z.open(info) as stream:body=stream.read(MAX_MEMBER_BYTES+1)
                    if len(body)>MAX_MEMBER_BYTES:self.add('ARCHIVE_MEMBER_SIZE_LIMIT',child);continue
                    if len(body)!=info.file_size:self.add('ARCHIVE_MEMBER_LENGTH_MISMATCH',child);continue
                except (OSError,ValueError,RuntimeError,NotImplementedError,zipfile.BadZipFile):
                    self.add('ARCHIVE_MEMBER_UNREADABLE',child);continue
                self.payload(body,info.filename,child,depth+1)
                if self.files>MAX_TOTAL_FILES or self.bytes>MAX_TOTAL_BYTES:break

    def metadata(self,data,path):
        # ZIP comments and extra fields are data, not recursively executable.
        for pattern,encoding in [(upstream.ASCII_STRING,'ascii'),(upstream.UTF16_LE_STRING,'utf-16-le'),(upstream.UTF16_BE_STRING,'utf-16-be')]:
            self.text('\n'.join(m.group(0).decode(encoding) for m in pattern.finditer(data)),path)

    def disk(self,path,logical):
        try:info=path.lstat()
        except OSError:self.add('FILE_UNREADABLE',logical);return
        self.name(logical,logical)
        if stat.S_ISLNK(info.st_mode):self.add('SYMLINK',logical);return
        if stat.S_ISDIR(info.st_mode):
            if not info.st_mode&0o444 or not info.st_mode&0o111:self.add('DIRECTORY_UNREADABLE',logical);return
            try:children=sorted(path.iterdir(),key=lambda p:p.name)
            except OSError:self.add('DIRECTORY_UNREADABLE',logical);return
            for child in children:
                self.disk(child,child.name if logical=='.' else logical+'/'+child.name)
                if self.files>MAX_TOTAL_FILES or self.bytes>MAX_TOTAL_BYTES:break
            return
        if not stat.S_ISREG(info.st_mode):self.add('SPECIAL_FILE',logical);return
        if not info.st_mode&0o444:self.add('FILE_UNREADABLE',logical);return
        if info.st_size>MAX_FILE_BYTES:self.add('FILE_SIZE_LIMIT',logical);return
        fd=None
        try:
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            opened=os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode):self.add('SPECIAL_FILE',logical);return
            if (opened.st_dev,opened.st_ino)!=(info.st_dev,info.st_ino):self.add('FILE_CHANGED_DURING_SCAN',logical);return
            with os.fdopen(fd,'rb') as stream:
                fd=None;body=stream.read(MAX_FILE_BYTES+1)
                final=os.fstat(stream.fileno())
            if len(body)>MAX_FILE_BYTES:self.add('FILE_SIZE_LIMIT',logical);return
            if len(body)!=opened.st_size or (opened.st_mtime_ns,opened.st_size)!=(final.st_mtime_ns,final.st_size):self.add('FILE_CHANGED_DURING_SCAN',logical);return
        except OSError:self.add('FILE_UNREADABLE',logical);return
        finally:
            if fd is not None:os.close(fd)
        self.payload(body,path.name,logical)

    def locator(self,path):
        pieces=[]
        for part in path.split('!'):
            sensitive=upstream._location_is_sensitive(part) or any(p.search(part) for p in EXTRA_PATTERNS.values())
            if sensitive or any(ord(c)<32 or ord(c)>126 for c in part):
                part='<redacted-'+hashlib.sha256(part.encode('utf-8',errors='replace')).hexdigest()[:12]+'>'
            pieces.append(part)
        return '!'.join(pieces)

    def run(self,path):
        # Do not resolve symlinks before testing the input itself.
        try:isdir=stat.S_ISDIR(path.lstat().st_mode)
        except OSError:isdir=False
        self.disk(path,'.' if isdir else path.name)
        if not self.files and not self.findings:self.add('EMPTY_ARTIFACT','.')
        findings=[{'code':f.code,'path':self.locator(f.path),'line':f.line} for f in sorted(self.findings,key=lambda f:(f.path,f.line,f.code))]
        manifest=sorted(self.manifest,key=lambda r:r['path'])
        return {'status':'NOT_READY' if findings else 'PASS','strict':True,
                'implementation':'local-strict-protocol-extension/1','official_upstream_protocol':False,
                'findings':findings,'scanned_payloads':self.files,'scanned_bytes_including_nested':self.bytes,
                'content_manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
                'content_manifest':manifest}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    check=sub.add_parser('privacy-check');check.add_argument('--strict',action='store_true',required=True)
    check.add_argument('artifact',type=Path)
    args=parser.parse_args()
    try:result=Scan().run(args.artifact)
    except Exception:
        result={'status':'NOT_READY','strict':True,'implementation':'local-strict-protocol-extension/1',
                'official_upstream_protocol':False,'findings':[{'code':'INTERNAL_SCAN_ERROR','path':'<artifact>','line':0}]}
    print(json.dumps(result,sort_keys=True))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())

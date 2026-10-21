"""Read primary public indexes without downloading model assets or wheels."""
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import json
from pathlib import Path
import re
import urllib.request

BASE = Path(__file__).resolve().parents[1]
requirements = [line.split('==', 1) for line in (BASE/'deployment/runtime-image/requirements.lock').read_text().splitlines() if line]


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'auto0505-dependency-source-check'}), timeout=30) as response:
        body = response.read(12 << 20)
        return body


def check(requirement):
    name, version = requirement
    url = f'https://pypi.org/pypi/{name}/{version}/json'
    try:
        raw = fetch(url)
        record = json.loads(raw)
        wheels = [item for item in record['urls'] if item['packagetype']=='bdist_wheel']
        # This is source availability, not a dependency resolver or install test.
        relevant = [item for item in wheels if item['filename'].endswith('none-any.whl') or
                    ('cp312' in item['filename'] and 'x86_64' in item['filename'] and 'manylinux' in item['filename']) or
                    ('abi3' in item['filename'] and 'x86_64' in item['filename'] and 'manylinux' in item['filename'])]
        return {'package':name,'version':version,'source':url,'metadata_sha256':hashlib.sha256(raw).hexdigest(),
                'status':'WHEEL_SOURCE_FOUND' if relevant else 'NEEDS_PLATFORM_RESOLUTION',
                'candidate_wheels':[{'filename':item['filename'],'sha256':item['digests']['sha256']} for item in relevant]}
    except Exception as exc:
        return {'package':name,'version':version,'source':url,'status':'SOURCE_PROBE_FAILED','error_type':type(exc).__name__}


with ThreadPoolExecutor(max_workers=5) as executor:
    records=list(executor.map(check, requirements))
torch_url='https://download.pytorch.org/whl/cu130/torch/'
try:
    raw=fetch(torch_url)
    names=re.findall(r'torch-2\.12\.1(?:%2B|\+)cu130-cp312-cp312-manylinux[^\s"<>]*x86_64\.whl',raw.decode())
    torch={'package':'torch','version':'2.12.1+cu130','source':torch_url,'metadata_sha256':hashlib.sha256(raw).hexdigest(),
           'status':'WHEEL_SOURCE_FOUND' if names else 'SOURCE_PROBE_NO_MATCH','candidate_wheels':sorted(set(names))}
except Exception as exc:
    torch={'package':'torch','source':torch_url,'status':'SOURCE_PROBE_FAILED','error_type':type(exc).__name__}
records.append(torch)
report={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope':'Public primary-index metadata only. No install, dependency resolution, CUDA compatibility or GPU execution claimed.',
        'packages':records}
output=BASE/'validation/dependency-source-probe.json'
output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'report':str(output),'statuses':{record['package']:record['status'] for record in records}},indent=2))

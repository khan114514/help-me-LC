from pathlib import Path
import hashlib,json,tomllib,importlib.metadata
from dirhash import dirhash
from harbor.models.task.config import TaskConfig
root=Path(('' + ('/' + 'root/') + 'rfsteps-v341-build-check-20261004'))
files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}
links=[str(p.relative_to(root)) for p in root.rglob('*') if p.is_symlink()]
config=TaskConfig.model_validate(tomllib.loads((root/'task.toml').read_text()))
result={'files':files,'file_count':len(files),'symlinks':links,'dirhash_sha256':dirhash(root,'sha256'),'harbor_version':importlib.metadata.version('harbor'),'native_schema':{'environment':{k:getattr(config.environment,k) for k in ('cpus','memory_mb','storage_mb','gpus','gpu_types')},'verifier_environment':{k:getattr(config.verifier.environment,k) for k in ('cpus','memory_mb','storage_mb','gpus','gpu_types')},'verifier_mode':config.verifier.environment_mode,'verifier_timeout_sec':config.verifier.timeout_sec,'agent_timeout_sec':config.agent.timeout_sec}}
print(json.dumps(result,sort_keys=True,default=str))

"""Assemble a new task from preserved source and the repaired shared runtime."""
from pathlib import Path
import hashlib
import json
import shutil

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / "source_snapshot"
PACKAGE = BASE / "package"
TASK = PACKAGE / "workspace" / "harbor_task"
OLD = SOURCE / "workspace" / "harbor_task"
RUNTIME = BASE / "tools" / "runtime"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


if not (PACKAGE / "expert_evidence" / "historical_v341").exists():
    prior = PACKAGE / "expert_evidence"
    prior.rename(BASE / "historical_expert_staging")
    prior.mkdir()
    (BASE / "historical_expert_staging").rename(prior / "historical_v341")
if TASK.exists():
    shutil.rmtree(TASK)
TASK.mkdir(parents=True)
agent = TASK / "environment"
tests = TASK / "tests"
agent.mkdir(); tests.mkdir()
shutil.copytree(OLD / "environment" / "starter", agent / "starter")
shutil.copytree(OLD / "environment" / "public_assets", agent / "public_assets")
shutil.copytree(OLD / "solution", TASK / "solution")
shutil.copy2(OLD / "tests" / "anchors.json", tests / "anchors.json")

baseline_receipt = json.loads((SOURCE / "optimization_evidence" / "baseline_runs" / "actual_v341" / "gpu-owned-job" / "receipt.json").read_text())["receipt"]
weight_files = dict(baseline_receipt["weights_sha256"])
weight_files.update(baseline_receipt["weight_support_sha256"])
repo_source = OLD / "tests" / "repo"
repo_files = {str(p.relative_to(repo_source)): digest(p) for p in repo_source.rglob("*") if p.is_file()}
runtime_files = {p.name: digest(p) for p in RUNTIME.iterdir() if p.suffix == ".py"}
hidden_root = SOURCE / 'private_inputs' / 'hidden'
hidden_manifest = json.loads((OLD / "tests" / "hidden_manifest.json").read_text())["files"]

for directory, formal in [(agent / "public_eval", False), (tests, True)]:
    directory.mkdir(exist_ok=True)
    for name in runtime_files:
        shutil.copy2(RUNTIME / name, directory / name)
    shutil.copy2(OLD / ("tests" if formal else "environment/public_eval") / "anchors.json", directory / "anchors.json")
    shutil.copytree(agent / "public_assets" / "eval_public", directory / "assets" / "public")
    if formal:
        (directory / "assets" / "hidden").mkdir()
        for name, expected in hidden_manifest.items():
            matches = [p for p in hidden_root.rglob(name) if p.is_file()]
            if len(matches) != 1 or digest(matches[0]) != expected:
                raise RuntimeError("Hidden input absent or mismatched")
            shutil.copy2(matches[0], directory / "assets" / "hidden" / name)
    images = {str(p.relative_to(directory / "assets")): digest(p) for p in (directory / "assets").rglob("*.png")}
    manifest = {"schema_version": 1, "role": "formal" if formal else "public", "images": images,
                "runtime_files": dict(runtime_files, **{"anchors.json": digest(directory / "anchors.json")}),
                "worker_files": {name:runtime_files[name] for name in ("candidate_worker.py", "isolation.py")},
                "repo_files": repo_files, "weight_files": weight_files}
    write_json(directory / "asset_manifest.json", manifest)

task_toml = '''schema_version = "1.3"
artifacts = ["/workspace/solution"]

[task]
name = "autoresearch/rfsteps"
version = "3.5.0-a100-repair"
description = "Deterministic timestep allocation under fixed numerical model and NFE budget."

[verifier]
timeout_sec = 3600.0
environment_mode = "separate"

[verifier.environment]
cpus = 8
memory_mb = 65536
gpus = 1
gpu_types = ["A100"]

[agent]
timeout_sec = 43200.0

[environment]
os = "linux"
cpus = 8
memory_mb = 65536
gpus = 1
gpu_types = ["A100"]
build_timeout_sec = 7200.0
'''
(TASK / "task.toml").write_text(task_toml)

instruction = (OLD / "instruction.md").read_text()
instruction = instruction.replace('候选编写和节点生成在独立 CPU 容器内完成，模型推理通过受控接口在外部 A100 执行；任务不训练模型。',
    '候选编写、公开开发评分在同一个单容器 sandbox 内完成，直接使用该 sandbox 分配的一张 GPU；任务不训练模型。节点函数在受限 CPU 子进程执行，可信数值评分器只接收已验证的节点。')
instruction = instruction.replace('这些限制由独立降权工作进程执行。',
    '这些限制由独立工作进程、Linux Landlock 文件访问规则、seccomp 系统调用规则及资源限额执行。候选不得联网、创建子进程或读取函数源码和标准库以外的业务材料；不依赖平台整体断网。内核不支持必要隔离时停止评分并报告基础设施错误。')
instruction = instruction.replace('受控服务只接受验证过的节点，公开端点固定公开集；候选不能请求其他数据、其他作业或服务器文件。GPU评分串行执行，每次只发出一个请求；排队由服务记录。单次评分最多3600秒，基础设施故障不产生有效分数。',
    '公开入口固定使用公开集；正式评分在独立 Verifier sandbox 内完成，私有材料不移交给 Agent。每个 sandbox 只使用自己的 GPU，不调用外部计算服务或额外容器。评分串行执行，节点提取有35秒墙钟上限，数值执行有3500秒上限，入口整体有3590秒上限。基础设施故障不产生有效分数。')
instruction = instruction.replace('验证节点后送入可信模型执行', '验证节点后在当前 sandbox 的可信模型进程执行')
(TASK / "instruction.md").write_text(instruction)
(agent / "instruction.md").write_text(instruction)

bootstrap = '''#!/bin/bash
set -euo pipefail
mkdir -p /workspace/solution /workspace/agent-output
if [ ! -e /workspace/solution/method.py ]; then
  cp /workspace/starter/method.py /workspace/solution/method.py
  cp /workspace/starter/solve.sh /workspace/solution/solve.sh
fi
exec "$@"
'''
(agent / "bootstrap.sh").write_text(bootstrap)
shutil.copy2(OLD / "solution" / "solve.sh", agent / "starter" / "solve.sh")
public_entry = '''#!/bin/bash
set -euo pipefail
exec timeout --signal=TERM --kill-after=10s 3590s python3 -I -B /opt/rfsteps/public/evaluate_candidate.py --method "${1:-/workspace/solution/method.py}" --out "${2:-/workspace/agent-output/dev}"
'''
(agent / "public_eval" / "evaluate.sh").write_text(public_entry)
verifier_entry = '''#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
exec timeout --signal=TERM --kill-after=10s 3590s python3 -I -B /tests/evaluate_candidate.py --method /workspace/solution/method.py --out /logs/verifier --formal
'''
(tests / "test.sh").write_text(verifier_entry)
docker_agent = '''ARG RFSTEPS_RUNTIME_IMAGE=rfsteps-numerical:3.5.0-a100
FROM ${RFSTEPS_RUNTIME_IMAGE}
USER root
COPY starter /workspace/starter
COPY instruction.md /workspace/instruction.md
COPY public_assets /workspace/environment/public_assets
COPY public_eval /opt/rfsteps/public
COPY public_eval/evaluate.sh /workspace/environment/public_eval/evaluate.sh
COPY bootstrap.sh /usr/local/bin/rfsteps-bootstrap
RUN useradd --uid 1000 --create-home solver \\
    && mkdir -p /workspace/solution /workspace/agent-output \\
    && cp /workspace/starter/method.py /workspace/solution/method.py \\
    && cp /workspace/starter/solve.sh /workspace/solution/solve.sh \\
    && chown -R 1000:1000 /workspace/solution /workspace/agent-output \\
    && chmod -R a+rX /workspace/starter /workspace/environment /opt/rfsteps/public /opt/rfsteps/repo /opt/rfsteps/weights \\
    && chmod -R a-w /workspace/starter /workspace/environment/public_assets /opt/rfsteps/public /opt/rfsteps/repo /opt/rfsteps/weights \\
    && chmod 755 /usr/local/bin/rfsteps-bootstrap /workspace/environment/public_eval/evaluate.sh
USER 1000
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/rfsteps-bootstrap"]
CMD ["/bin/bash"]
'''
(agent / "Dockerfile").write_text(docker_agent)
docker_verifier = '''ARG RFSTEPS_RUNTIME_IMAGE=rfsteps-numerical:3.5.0-a100
FROM ${RFSTEPS_RUNTIME_IMAGE}
USER root
COPY . /tests/
RUN chmod -R go-rwx /tests && chmod 755 /tests/test.sh
WORKDIR /workspace
CMD ["/bin/bash"]
'''
(tests / "Dockerfile").write_text(docker_verifier)
for p in [agent / 'bootstrap.sh', agent / 'public_eval/evaluate.sh', tests / 'test.sh']:
    p.chmod(0o755)

deployment = BASE / 'deployment' / 'runtime-image'
deployment.mkdir(parents=True, exist_ok=True)
if not (deployment / 'repo').exists():
    shutil.copytree(repo_source, deployment / 'repo')
write_json(deployment / 'weight_manifest.json', {'files': weight_files})
worker_dir = deployment / 'worker'
worker_dir.mkdir(exist_ok=True)
for name in ('candidate_worker.py', 'isolation.py'):
    shutil.copy2(RUNTIME/name, worker_dir/name)
    (worker_dir/name).chmod(0o644)
requirements = '\n'.join(f'{name}=={version}' for name, version in baseline_receipt['environment']['packages'].items() if name != 'torch') + '\n'
(deployment / 'requirements.lock').write_text(requirements)
(deployment / 'Dockerfile').write_text('''FROM node:22.16.0-bookworm-slim AS node_runtime
FROM python:3.12.13-slim-bookworm
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \\
    && apt-get -o Acquire::Retries=3 update \\
    && apt-get install -y --no-install-recommends python3 libseccomp2 libgomp1 libgl1 libglib2.0-0 ca-certificates git ripgrep coreutils \\
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node_runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN node /usr/local/lib/node_modules/npm/bin/npm-cli.js install -g @openai/codex@0.160.0
RUN pip install --no-cache-dir torch==2.12.1+cu130 --index-url https://download.pytorch.org/whl/cu130 \\
    && pip install --no-cache-dir -r /tmp/requirements.lock
COPY repo /opt/rfsteps/repo/
COPY weights /opt/rfsteps/weights/
COPY worker /opt/rfsteps/worker/
RUN chmod 755 /opt/rfsteps/worker && chmod 644 /opt/rfsteps/worker/*.py
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
''')
write_json(BASE / 'repair_state.json', {'task_id':'auto0505', 'status':'CODE_REPAIR_IN_PROGRESS',
    'source_zip_sha256':'bc995b80eeb1a361d4a17d88f1f9e8e04172cf1361b945d766219ea045153a6e',
    'new_task_version':'3.5.0-a100-repair', 'hardware':'A100 user override; H20/L20 deferred',
    'runtime_validation':'pending A100 connection', 'official_v4_tools':'missing',
    'historical_scores':'preserved; not relabeled as v3.5.0 results'})
print('Assembled', TASK)

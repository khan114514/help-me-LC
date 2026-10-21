# rfsteps NOP Trial 实测报告（v1.0，2026-10-04）

## 一句话结论

NOP Trial 在官方 harbor v0.23.0 上**全链路实际执行**：构建 → nop agent → tests 注入 → test.sh → run_eval.py → reward.json 原子写入 → harness 收集，**结构证据完整（H05/H06 有同一 Trial 的 config/result/reward/日志）**；同时实测发现并已修复提交包的 3 个真实依赖缺陷（v3.2）。最终 reward=0.0 系 **A10(22.06GiB) 物理容量小于 flux-dev 加载需求（22.2GiB）导致的 verifier 提前退出**，属纯基础设施障碍——任务声明的 gpu_types 为 A100/H100（40G+），A10 不在其列，不构成题目实现缺陷。

## 运行环境

| 项 | 值 |
|---|---|
| Harness | harbor 0.23.0（PyPI 官方，Python 3.14.7/Miniconda） |
| 机器 | 腾讯云 GPU 计算型 PNV4，NVIDIA A10 22.06GiB，Ubuntu 22.04.5，driver 580.126.20 |
| Docker | 29.8.2 + compose v5 + nvidia-container-toolkit 1.20.1（`--gpus all` 验证通过） |
| 权重 | /opt/rfsteps/weights（33G，与提交包 anchors.json 记录同构），bind 只读挂载 |
| 任务包 | rfsteps-package/workspace/harbor_task（v3.2 修复后版本；task.toml 逐字节同提交版） |

## Run-side 适配（不改被测对象，全部记录在 Trial config.json）

| 适配 | 原因 |
|---|---|
| 自定义环境类 `gpu_docker_env:GpuDockerEnvironment`（声明 gpus 能力） | 官方本地 docker provider capabilities.gpus=False，task 声明 gpus=1 会被拒 |
| compose overlay `gpu-overlay.yaml`（构建上下文=任务根 + nvidia device reservation） | 官方 provider 默认 environment/ 上下文（与本任务 teaching-task-root-v1 布局不兼容）且不注入 GPU |
| `--mounts` bind 权重；`--ve PYTORCH_CUDA_ALLOC_CONF`；`--verifier-timeout-multiplier 2` | 运行时挂载约定；A10 显存碎片与速度余量 |
| VM 侧 Dockerfile 副本加 `ENV PIP_INDEX_URL=清华镜像` | 仅构建加速（同包同版本不同源）；提交版 Dockerfile 不含此行 |

## 五轮 Trial 与实测发现

| 轮次 | Job | 结果 | 发现/处置 |
|---|---|---|---|
| 1 | 10-17/10-18 | ValueError: no-network 不支持 | harbor 内核探测镜像（alpine 摘要锁定）30s 内拉取超时误判；预拉后通过（基础设施） |
| 3 | 2026-10-04__10-26-12 | reward=0.0，20s 早退 | **缺陷①**：requirements.txt 缺 `invisible-watermark`（上游 flux/util.py `import imwatermark`）→ v3.2 修复 |
| 4 | 2026-10-04__10-51-51 | reward=0.0，早退 | **缺陷②**：opencv-python 需系统库 libxcb.so.1 → v3.2 修复（Dockerfile apt 增 libgl1/libglib2.0-0/libxcb1）；另补 `requests`（上游直接 import） |
| 5 | 2026-10-04__11-06-57 | **链路完整执行**，reward=0.0 | verifier 走完 tests 注入→test.sh→run_eval.py→模型加载；**flux-dev 加载 OOM**（A10 22.06GiB < 22.2GiB）。exception_info=null，finished_at 完整，verifier_result.rewards 与 reward.json 一致 |

## H05/H06 结构核对（run5，trial harbor_task__KZSk6k2）

- config.json：agent.name=nop、verifier 未禁用、verifier_timeout_multiplier=2.0、import_path/mounts/overlay 全记录 ✓
- result.json：exception_info=null、finished_at 存在、verifier_environment_mode="shared"（task.toml 未声明 environment_mode，官方默认 shared，tests 由 harbor 上传 /tests）、verifier_result.rewards={"reward":0.0} ✓
- verifier/reward.json `{"reward": 0.0}` 与 result 一致 ✓；verifier/test-stdout.txt 记录 OOM 栈 ✓
- task_checksum 记录于 result.json（与 v3.2 后任务目录对应）✓
- 结论：同一 Trial 证据完整一致；0 分原因为 GPU 容量基础设施障碍（A10∉{A100,H100}），非题目实现缺陷，非 harness 接入错误。

## v3.2 修复清单（已进提交包）

1. `environment/requirements.txt`：+`invisible-watermark`、`requests`（附 NOP 实测注释）
2. `environment/Dockerfile`：apt 增 `libgl1 libglib2.0-0 libxcb1`（附 NOP 实测注释）

## 残余边界

- 完整评分（真实 PSNR 产出）未验证：需 A100/H100 环境；task.toml gpu_types 声明与之匹配，平台侧不受影响。
- verifier no-network 由 egress sidecar 执行，未逐包审计；NOP 未触发网络访问需求。
- 若后续在 A100 环境补跑，预期 verifier 走完约 30-60 分钟评测并产出非零 reward（Baseline schedule 的 PSNR≈锚点 B）。

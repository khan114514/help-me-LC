# A100 返修版运行准备

本版由用户于2026-10-21指定先使用A100。H20/L20验收仍待后续迁移，本目录不声称已通过目标内场验收。

每个Agent/Verifier sandbox只运行一个容器，直接使用自己分配的GPU。没有Compose、宿主Docker socket、外部GPU服务或额外评分容器。最后的独立Verifier由Harbor创建；公开Dev保留在Agent镜像中。

## 冻结资产与镜像

在有NVIDIA容器运行能力的A100 Linux主机上，用原权重目录运行：

```bash
python3 deployment/prepare_weights.py --source /path/to/original/weights
docker build -t rfsteps-numerical:3.5.0-a100 deployment/runtime-image
docker build -t rfsteps-agent:3.5.0-a100 package/workspace/harbor_task/environment
docker build -t rfsteps-verifier:3.5.0-a100 package/workspace/harbor_task/tests
```

权重逐项匹配旧正式回执，不修改权重或锚点凑结果。基础镜像和依赖版本的真实可获取性、NVIDIA驱动兼容性由该次构建核验。若精确版本不可获取，记录失败后决定迁移方案，并复核受影响B/R/U；不能把其他版本称作已冻结原环境。

`weights/`含大模型资产，只在可信镜像构建context中准备。模型权重不通过候选目录移交。最终需记录实际镜像ID/digest和发布到平台认可仓库的入口；本地tag尚不等于内场可拉取镜像。

公开命令保持：

```bash
bash /workspace/environment/public_eval/evaluate.sh /workspace/solution/method.py /workspace/agent-output/dev
```

正式入口为`bash /tests/test.sh`。`task.toml`只移交`/workspace/solution`，Verifier使用新的sandbox及预置的`/tests`。正式候选不会作为高权限Python模块导入；降权、Landlock、seccomp、CPU/内存/输出限额检查后，只把26个数值节点交给可信数值评分器。

两种镜像共用`/opt/rfsteps/worker`内只读的公共候选入口，保证UID65534可以加载该入口；该目录不包含Hidden、锚点或参考实现。`/tests`仍为root私有，Agent公开运行代码和标准材料设置为可读不可写。实际Dockerfile已经用CPU测试基础镜像构建并验证以上权限；这不代表完整CUDA镜像构建通过。

## 实跑记录

先核对实际Harbor版本与配置解析，再运行A100公开Dev、同协议Baseline/Reference及必要U复核、最终方法公开复验和独立Verifier评分、新版本NOP。每次保留原始stdout/stderr、真实起止与退出码、方法/镜像/数据身份和结果。旧A100记录单独作为历史证据，不能改标为本版运行。

硬件和内核前检必须确认：单个分配GPU至少38GiB、Linux Landlock ABI≥3、libseccomp可用，且不需要privileged容器。若候选隔离不可用则返回基础设施错误，不降级执行候选。

单次节点提取35秒墙钟、数值链3500秒、入口3590秒、Verifier阶段3600秒，外层会终止子进程组。Agent时限43200秒、build/setup7200秒；有效研究时长仍需扣除安装/排队/故障等区间，不能以总时限替代。

## 尚待完成

当前保存的A100地址连接被拒绝，需要当前SSH入口。官方0.3.10发布包及`task_fingerprint.py`尚未取得。本地编译/容器边界测试不替代GPU评分、Harbor移交/NOP、正式指纹、双轨有效研究或12小时容器稳定性。

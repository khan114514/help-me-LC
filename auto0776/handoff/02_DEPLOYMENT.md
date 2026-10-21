# 单容器、目标卡与版本迁移

> 当前优先读[五项非阻断口径](00_CURRENT_REVIEW_POLICY.md)。本文件涉及指纹/哈希、换卡补证和H06/NOP的旧硬门槛由该口径覆盖，不因此强制补跑/判退；其他核心检查保留。旧工具结果原样保留，另列用户口径结论。

## 先记录目标真实能力

当前旧证据 Harbor 0.23.0 + 作者自定义 adapter，仅供追溯。先拿到目标平台实际 Harbor 版本/schema、GPU 分配方法、镜像仓库和候选受限执行能力；按它实装，不套未知字段、宿主功能或旧主机地址。用户新服务器需实测 `nvidia-smi`、CPU/RAM/文件系统和容器能力。普通无 Docker 的 GPU 实例可以做方法开发/Public 评分，但不能声称完成完整 Harbor/NOP 自验。

## 实现修改地图

| 位置（相对 source/onedc_v9） | 现状 | 需实现的结果 |
|---|---|---|
| workspace/harbor_task/task.toml | storage_mb、no-network、无目标卡；artifacts 只传 public-results、collect 另拷 solution | 使用目标支持配置；Agent 与 Verifier 分别明确 H20 或 L20；直接移交候选 solution；分别声明阶段时限 |
| expert_evidence/platform_adapter/onedc_harbor.py 与 offline adapter | 宿主 lease、seccomp 文件/AppArmor profile、extra_docker_compose | 正式路径不用这些作者专属宿主准备；平台每 sandbox 单容器，直接使用自身 GPU |
| environment/grader/public_eval.py、entrypoint.sh、lease_exec.py、run_eval.py | 请求服务/共享锁与旧路径可能耦合 | Public 在 Agent 本 sandbox 内可调用；只用正常进程/子进程；无额外 GPU 服务或容器 |
| tests/test.sh、tests/lease_exec.py | 老路径和超时嵌套，候选位置依旧 collect | 直接对框架移交的候选评分，清理超时进程，及时返回；可信侧写 reward |
| tests/candidate_client.py、candidate_worker.py（及 environment 对应副本） | 独立 tensor worker 与权限策略 | 按目标实际支持保留/重建候选边界：候选不可读 Hidden 标签/Reference，不可改 tests、固定参照、reward |
| environment/Dockerfile、tests/Dockerfile | 模型/工具命名 context，旧镜像/注入依赖 | Agent context=environment；独立 Verifier 可复用 Solver 镜像或 tests context 专用镜像；依赖预装、资产固定、不可越界 COPY |

先读实际调用链后改，不能仅凭表格删文件。移除外部调度依赖不意味着删除候选安全边界。若平台权限/namespace/用户切换能力不足，记录具体失败并寻找平台支持机制，不把关闭保护当验证通过。

## 目标结果

- Agent、Verifier 两个不同 sandbox，各一个容器，GPU 各自直接分配。最终 Verifier 在 Agent 退出和候选移交后执行，不启动第二个研究 Agent。
- 建议统一 artifacts=`/workspace/solution`；如用等价路径，题面/配置/入口/构建/实际移交一致。只传方法、必要配置和合同所需模型；不传 logs/reward/评分器/整个工作区。
- 不声明平台不支持的 storage_mb、禁网/白名单。根据实际联网条件写题面与评分边界；模型冻结、输入哈希、私有不可见、评分不可改仍须落实。离线缓存可以作为复现方式，不能虚称平台禁网。
- 分别记录 Agent 总时限、Verifier 阶段时限、候选单次时限、build/setup 时限。完整方法→必要重载→评分一轮 ≤7200s、≤8张H20/L20、≤64核；超时须能实际打断并清理。

## 资源估算与卡间桥接

旧说明称 A100 显存<12GB、推理几十秒，但这属于历史估计/实测范围，不能直接写成 H20/L20 资源已验证。用冻结 B/R/候选测目标卡峰值显存、GPU/CPU内存、完整时间、模型加载与熵编码；根据结果申请资源并写依据，不机械套固定8CPU/32GB。

锁定模型/codec/熵模型、数据顺序、seed0、精度、torch/CUDA/指标版本、rANS 和允许方法接口；先做 Public 桥接。逐图对比实际 bitstream 长度/bpp、DISTS、码率 cap 余量及重复运行数值差异。预先说明容差；若方法使用GPU浮点运算，不能从“整数熵编码”推出全链路跨卡确定。

目标正式协议所需的受影响 B/R 运行、锚点和质量门重新验证，保留 A10 标签和旧输入版本。若数值变化影响 B/U/cap，按统一协议和合理依据重标定并版本化；不得为使 R 落入目标区间而任意调 U。R Public 归一化需 [0.15,0.8]；候选超过U可>1，不截断。

## 正式验证顺序

1. 源码/配置静态改造，运行真实官方格式与GPU前检，修 ERROR、处理 CHECK。
2. 目标环境构建、Public 评分可用、候选隔离与移交验证；正式模型路径做真实 coding tool preflight。
3. 受影响 B/R/U 及资源/码率/确定性桥接，冻结新研究输入版本。
4. 补足合法研究、恢复每轨 Public best、选唯一最终方法并干净 Public 复验。
5. 最终 task 四项输入冻结后计算真实官方指纹，在该同版本 separate 模式跑 NOP。收同一 Trial 的 config/result/reward/log；0分本身不失败。
6. 目标环境12h稳定性单列，实际持续健康记录；旧 A10 12h不能证明新容器/配置12h，也不能当研究时间。

构建、评分器、候选移交或运行依赖在 NOP 后变化，按影响重做 NOP。只改专家说明、不改变四项任务输入时不无故重复 GPU 校准。不可为旧日志缺字段无条件重跑全部研究。

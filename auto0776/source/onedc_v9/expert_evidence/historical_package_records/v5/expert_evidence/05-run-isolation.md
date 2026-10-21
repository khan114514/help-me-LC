# 05 · 运行隔离与有效时长记录

旧两轨存在物理隔离缺陷，已停止并完整备份；219 轮的结果只作探索证据。用户在 2026-10-04 明确了时间口径：环境配置、构建、smoke、NOP、探索、正式跑分、排队、失败、调试和恢复都属于有效工作，只扣除有审计证据的未建立 HTTP 连接或未收到响应区间。HTTP 429 和不完整 HTTP 200 说明已经连上服务，因此计时。共享前置工作从首条任务记录 06:53:11 起同时计入两轨；旧隔离缺陷影响结果资格，不抹掉实际投入时间。完整计算见 `time-accounting.json` 和 `effective-time-user-policy.json`。

截至 2026-10-04 21:04:57 CST，总工作跨度为 14:11:46。GPT 有 00:21:27 的确认未连接区间，主口径有效时间为 13:50:19；Seed 有 00:00:15 的确认未连接区间，主口径有效时间为 14:11:31。两轨均已超过各自 10 小时要求。旧的语义闭环时钟仍保留为补充审计值（GPT 4817.37 秒、Seed 0 秒），不再用于完成判断。

修复版 final-v8 正式双轨于 2026-10-04 15:54:09 CST 首次并行启动，仍采用每轨 10 个有效小时，未采用 7 小时例外。Seed 第 1 轮为完全未改方法的 no-op，正式有效时长为 0，随后暴露可信控制器的恢复顺序错误：容器正确移除了 `DAC_OVERRIDE`，但控制器在使用 `CAP_CHOWN` 前尝试以 root 写入 UID 25000 的 0644 文件。最小同权限复现确认根因；修复为先转交单文件属主、写入、再还原 UID/权限。失败目录和异常结果完整保存在 `formal/failed-attempts`。为保证两轨使用相同修复版，Seed 于 16:01:33 从同一 Starter 重启；旧 GPT 回合未闭合，计时为 0。GPT 随后一次 17 秒重启因 Docker 复用尚未在启动前清理的旧 peer IP，在 agent 执行前退出并归档；清理顺序修正后，GPT 于 16:03:16 启动当前合格容器。

首次正式启动前可观测的全流程下界从首条旧轨迹记录到 15:54:09 为 9:00:58；按用户口径，该总投入中的配置、等待、构建、smoke、NOP、失败调试和修复全部计时。final-v8 pilot 的 GPT 完成 1 个闭环（268.03 秒），Seed pilot 未闭合一轮；二者实际耗时同样纳入主口径。

修复版使用原生 Harbor、任务专用 Docker/containerd 存储及原平台内核探针。Task 和独立 verifier 使用冻结离线镜像；唯一组织者 host bind 为 root 私有 GPU lease，无 Docker socket、host PID namespace、作者源码/模型目录或专家证据挂载。容器 drop ALL capabilities；可信父进程仅保留必要的 UID 切换、归属调整及 worker 清理能力；optimizer 和 tensor worker 有效 capabilities 均为空。

Optimizer UID 25000，仅 method.py 可在保护的工作区原地写入。Reference、隐藏输入、私有轨迹和同伴历史不进入其环境。隐藏数据只进入新建 verifier。Tensor worker UID 25001 与 optimizer 分离；对抗探针验证它不能读取公开输入、模型、评分器或 reward 历史，不能创建网络、执行子进程或逃离进程组；挂起 worker 可被可信父进程终止。

Codex workspace-write 沙箱和 no_new_privs 保持启用。真实工具探针验证 method 编辑及恢复成功，其他工作区写入、外部自有文件写入、verifier 私有读取及工具层直连网关被拒绝。早期探针错误地只接受 PermissionError，误判 EROFS；修正为检查明确拒绝 errno 后实测通过，未放宽边界。另一轮因 Docker cp 不能读取 tmpfs 日志失败，改为 Root exec 读取；模型口头声明不作为成功证据。

容器 peer 身份固定上游：GPT 为 gpt-6.1-sol/xhigh/Responses；Seed 为 doubao-seed-2-1-turbo-260628/high/thinking enabled/Responses。凭据仅在组织者独立进程内存，不进镜像、optimizer 环境或 argv。请求固定 store=false，拒绝重定向；这证明请求参数，不声称上游存储行为或返回 model 名称的密码学真实性。

外发为公开题面、允许的源码工具结果、自己轨迹公开指标及方法代码；不提供隐藏输入、Reference、同伴历史或组织者文件。正式控制器禁用图片查看和子 agent，网关拒绝结构化图片/音频/文件/视频输入。组织者保留脱敏原始请求、实际转发请求和返回流，目录/文件权限 0700/0600；不含 Authorization header，不进入公开交付。公开审计只留模型、状态、时间和内容哈希。

两个模型从同一 Starter、题面和资源规格启动，独立保留最佳方法。真实 CLI turn 结束后，可信公开 receipt 绑定方法 SHA，再保留或恢复。主时间口径按完整工作跨度计算，配置、smoke、NOP、未闭合 turn、失败或未完成请求、GPU 排队、构建、故障处理和恢复均计入；仅扣除确认没有 HTTP 状态或响应的区间。每轨分别检查 10 小时门槛。语义变化、有效评分和决策闭合仍用于评价实验质量，但不再决定时间是否有效。

12 小时容器稳定性另计：检查 image、StartedAt、RestartCount、Running 和 OOMKilled；重启/OOM 不算连续稳定。有效时长达到后重新评分最佳方法，保持同容器至少 12 小时，再由独立 verifier full 验证；稳定性等待不增加有效研究时长。

final-v8 镜像本地备份流在正式启动前开始，并与双轨旁路并行；16:08:37 CST 完成 gzip 完整性和 SHA256 核验。私有压缩包 15,121,763,292 bytes，SHA256 `8470df4b64f402bc52037df280bbe2b90ba3c20b2ea8be40a0d7f52fc7da037e`，元数据位于 `private-recovery/onedc-env-v8.backup.json`，不进入公开任务包。组织者磁盘余量至少 5 GiB，否则停止自己的轨迹。其他任务不被暂停或终止。

专用运行时初次配置曾误占系统 containerd endpoint；已停止专用进程并恢复系统 endpoint。默认 Docker daemon 未重启，前后默认容器列表为空；事件另有记录，不能声称 endpoint 从未受影响。

CPU 探针的 0.25 reward 仅为集成 fixture，非 OneDC 分数或正式轨迹指标。正式双轨已运行，用户口径的两轨 10 小时时间门已通过；两轨自身冻结 best 的独立原生全24图复验已经完成：GPT valid/reward1.1955827260919034，Seed 真实 hard_gate/reward-1。完整原生日志在 final_native_replays/native_execution_records。12小时真实连续稳定、原研究阶段诚实收尾和最终双AI质检仍待完成。

当前关联以 final_native_replays/PHASE-ASSOCIATION.json、time_authority/ 的直接人类授权与原始暂停回执为准。镜像、挂载及 UID25000 可见性实际清点见 platform_adapter/retained-exposure-inventory.json；该清点和健康探测不冒充完整12小时验收。
公开专家指标包含 Hidden 每图标识和分数及聚合，但不含 Hidden 原始像素；这些结果仅属于可信专家证据，不进入 Agent 上下文，也不用于后续调优。


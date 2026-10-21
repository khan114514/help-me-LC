# 接手执行约定

1. 本次任务是 auto0505（图像反演与重建时间步分配）的返修。用户授权继续完成其余问题，先用 A100，暂缓 H20；不要转做第二题 auto0776。七题目录和第二题反馈仅供上下文。
2. 先读 `handoff/START_HERE.md`、`handoff/REPAIR_MATRIX.md`、`handoff/SKILL_VERSIONS.md`，再读 `skills/autoresearch-task-qa/SKILL.md` 和其 V4、G01/G02/G03、21项、Harbor、提交格式与隐私参考。任务修复用 autoresearch/manager/remote-cli，独立审查用 QA/baseline-quality。
3. 当前优先执行用户2026-10-21五项放宽，详见 `handoff/CURRENT_REVIEW_POLICY.md` 和五个Skill的V4合同第5行起。QA21指纹/哈希差异、G02/G03换卡影响补证、QA15换卡耗时、QA17/H06 NOP、QA03/QA13换卡重算可记非阻断待补/待核，不单独判退、强制补跑或进入返修循环。其余核心检查继续保留。
4. 持续修复核心问题，直至同一个最终ZIP的两个不同AI、两个独立新会话按适用用户口径均通过，核心共识无未闭环分歧；可写“通过（含放宽待补项）”。旧工具原始fail/manual/NOT_READY和原版共识保留原样，另列用户口径结论；不要求为这五项把旧工具强制改成PASS。不得擅自再放宽、删错误证据、改锚点或伪造记录。核心硬失败或决定性缺证仍阻断。
5. 本地V4规则整合及用户放宽不是官方0.3.10发行包变更；旧辅助工具身份见版本说明。工具未核验就如实记未核验，不能把用户口径结论称为官方自检或平台验收。不得猜指纹算法；相关指纹缺证可后补。
6. 保留原始旧成绩及设备标签。历史 Seed 已明确访问过 pilot 日志与参考源码，不能作为干净轨迹；GPT 搜索无命中不等于证明完全干净。同 Prompt/起点一致性未证实，建议新建两条干净轨迹。
7. 每条有效研究默认至少10小时；7小时例外必须满足 V4 全部非训练快迭代条件。安装/排队/API失联/故障/最终QA等扣除，重叠不重复计。每轮恰八字段，不虚构轮次。12h容器稳定性另行实测。
8. 每 sandbox 单容器直接用自己的 GPU，separate Verifier，候选只移交 `/workspace/solution`。不启 Compose、不挂宿主 Docker socket、不调用外部 GPU RPC。Operator 可以构建镜像及做专家成对验证；解题 Agent 不部署额外工作容器。
9. 不把整个仓库、`source_snapshot/`、Reference、Hidden、专家说明、另一轨或旧 pilot 交给解题 Agent。两轨分别空输出起步；Harbor 在 Agent 结束后才移交候选并运行独立 Verifier。
10. 所有 Doubao/Ark/Seed 调用只走 `https://ark.cn-beijing.volces.com/api/coding/v3/chat/completions`。可信主控从 `ARK_CONFIG_FILE` 指定的受保护配置读取凭据；原用户环境使用 `~/.config/ark/current.json`、权限0600。不把 key 放仓库、日志、通知、请求文件或 Actor 环境。不回退按量接口。不静默替换指定模型。
11. 历史登记模型为 GPT `gpt-6.1-sol/xhigh` 与 Seed `doubao-seed-2-1-turbo-260628/high`；日志中 Seed CLI 也出现过 xhigh 请求，这不是上游实收证明。新调用前核验真实模型/推理能力和无凭据 Coding Agent 网关。套餐不支持则报告；普通聊天不是轨迹。不要调用旧 helper 的 Ark/profile/密钥注入操作。
12. 当前 A100 用户偏好不等于平台已豁免 QA15。官方审查若仍要求 H20/L20，保持明确待确认，取得平台真实接受证据或经用户决定迁移；不能把 A100 写成 H20，也不能自改最终规则。
13. 除用户已授权本仓库上传外，不自动填写平台验收表或向专家/群聊发消息。完成后交付实际最终 ZIP、SHA256、双独立报告及共识、修改说明和真实残余限制。

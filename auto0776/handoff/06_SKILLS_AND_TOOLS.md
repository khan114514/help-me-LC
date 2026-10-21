# 最终技能快照与工具缺口

## 这次交接的“最终skill”是什么

以下是本机 2026-10-21 更新后的实际技能树及其参考/脚本，不是凭空制作的官方新版包：

- [autoresearch](../skills/autoresearch/SKILL.md)：工作流入口和V4合同。
- [autoresearch-manager](../skills/autoresearch-manager/SKILL.md)：持续修复、执行调度、独立QA/收口。
- [autoresearch-remote-cli](../skills/autoresearch-remote-cli/SKILL.md)：授权远端操作、Coding Plan和旧helper禁用边界。
- [autoresearch-task-qa](../skills/autoresearch-task-qa/SKILL.md)：只读内容审查、G01–03/QA01–21/Harbor接口。
- [autoresearch-baseline-quality](../skills/autoresearch-baseline-quality/SKILL.md)：τ选择、预算、公平性专项。

规则统一先读 `autoresearch/references/phase3-v4-contract.md`。用户本轮返修意见优先于旧状态与参考示例。

## 真实工具版本，不能混称

| 材料 | 实际情况 | 允许声明 |
|---|---|---|
| V4合同 | 对用户2026-10-21教程的本地整合；教程对应审阅Skill0.3.10 | 已纳入当前规则 |
| 顶层autoresearch-task-qa脚本 | 实际旧v0.3.2 | 辅助清点/只读审查，不能叫0.3.10通过 |
| manager/assets/qa-skills | 固定旧v0.3.4；qa-release.json保存原文件SHA | 仅按其实际冻结版本使用；旧双PASS不代表V4新版全部验收 |
| 官方0.3.10发布包 | 本机和交接均未取得 | 待取得真实包并记录版本/SHA |
| check_submission.py、独立GPU前检、task_fingerprint.py | 本机和交接均缺失 | 待补，不能自写兼容算法后称官方通过 |
| 本仓库tools/ | 作者新写辅助工具 | 只说明各自校验范围，不是官方QA |

manager的旧调度器默认全量失效重跑，是旧实现行为，不是本次用户要求。使用前适配本题阶段与版本依赖；保留无关旧证据，只补受影响部分。当前主任务没有自动开长实验或恢复旧暂停状态。

## 可移植性与完整性

skills快照剔除了解释器缓存。作者home路径替换为 `${LOCAL_HOME}`，历史SSH主机替换为保留域/通用名称；remote技能旧作者root路径替换为 `${TRUSTED_RUNTIME_ROOT}`。这些是公开交接的可移植投影，不改变规则。旧remote helper不能直接照默认路径执行，需按当前合同显式配置，旧Ark操作仍禁用。逐文件源SHA、发布SHA和变更标记见 manifests/skills_provenance.json。manager的固定QA资产未作这种改写，qa-release.json逐文件哈希应仍匹配；verify_handoff.py会核验。

原始source/onedc_v9保持842文件字节不变；source_v9.json记录每个源文件SHA、模式和原始ZIP SHA。它不是官方任务指纹；重新打包不应宣称重现原始ZIP二进制。

不要向~/.codex/skills盲覆盖当前其他任务的skill。可让接手Agent在此仓库相对路径读取，或在确认来源和当前全局版本后安装。独立QA会话只提供固定QA技能和同一task ZIP，不能提供作者仓库/返修结论。

# Skill 与工具身份

随仓库提供的最终本地规则入口为 `skills/autoresearch-task-qa/SKILL.md`。它和 autoresearch/manager/remote-cli 的 V4 合同已整合用户2026-10-21教程；**它不是官方0.3.10发布包**。

已同步用户2026-10-21的[五项非阻断优先级调整](CURRENT_REVIEW_POLICY.md)，五个主Skill及各自V4合同、执行/报告参考共20份文档更新。旧冻结QA脚本和旧结果未修改。旧工具fail/manual/NOT_READY与本次用户口径结论分列；可以“通过（含放宽待补项）”，不因仅有这五项而强制NOP、返修或补跑。

| 组件 | 实际身份 / 用途 |
|---|---|
| autoresearch-task-qa 主技能 | 本地V4语义规则；随附辅助脚本仍为实际0.3.2 |
| autoresearch-manager | 持续执行及失败修复编排说明；随附QA资产实际0.3.4，不能冒充0.3.10 |
| autoresearch-baseline-quality | 正式Baseline只读合理性专项 |
| autoresearch / remote-cli | 返修工作流、独立研究、Coding Plan安全路由与远程执行边界 |
| systematic-debugging | 复现、定位根因再修复 |
| release_tools/privacy | 既有本地严格协议扩展/1与其upstream扫描器；`official_upstream_protocol=false`，不是官方0.3.10检查 |
| release_tools/verify_handoff.py | 本交接文件SHA256与空目录恢复；不是官方四项任务指纹 |
| release_tools/pack_submission.py | 完整ZIP打包、校验与SHA256；不会授予PASS |

完整Skill目录已复制，含相对引用文档和现有辅助代码；不存在的其他研究技能不因名称出现在路由表中就被视为已安装。接手直接从仓库读取即可，不需要先安装全局。需要安装时把所需技能目录复制到自己的 `$CODEX_HOME/skills`，已有同名技能先留存，别覆盖唯一原件。

为交接做了明确的隐私与可移植性转换：作者home路径改为占位，历史文本容器路径用逻辑别名；Python中必要容器root字符串以等价字符串拼接表示，避免将运行时位置误当作者目录。当前评分运行时未改变数值评分器。`handoff/export_provenance.json` 保存导出前后身份；后续手册/便携补丁以最终仓库文件清单为准。旧版本包身份字段仍保留其真实历史含义，不表示转换后的副本仍是未修改官方发行物。

不要直接用manager旧执行器的冻结循环强制落实这五项；保留其原始状态和结果，按用户口径另列结论。真实官方工具取得后按真实schema适配，不改冻结工具制造PASS。旧remote helper的Ark/Ark-profile/Seed-profile使用旧接口和子进程密钥注入，当前明确禁止。不得在此次明确授权之外自行继续放宽核心门槛。

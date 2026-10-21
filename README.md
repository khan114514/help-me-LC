# auto0505 返修交接

接手入口：**[handoff/START_HERE.md](handoff/START_HERE.md)**。把 [接手 Prompt](handoff/TAKEOVER_PROMPT.txt) 交给执行者，并让其先读根目录 [AGENTS.md](AGENTS.md)。

目标：完成第一题 auto0505 的返修、真实 A100 验证、独立双轨、同版本 Harbor/NOP、正式工具检查和最终完整 ZIP。最终同一 ZIP 获得两种 AI 的独立 PASS、共识无分歧后，再把 ZIP、SHA256、报告交给用户。

当前已完成代码与配置修复、本地 29 次测试执行；**尚未完成 A100 实跑及最终质检，不能直接把本仓库当作已通过的提交包。**

- [修改及验收矩阵](handoff/REPAIR_MATRIX.md)
- [当前阻塞及外部资产](handoff/BLOCKERS_AND_ASSETS.md)
- [历史质检原文快照与七题目录](handoff/table_review_snapshot.json)
- [当前返修包](auto0505/package/)
- [便携重建脚本](auto0505/tools/) / [镜像构建准备](auto0505/deployment/)
- [本地验证记录](auto0505/validation/local_validation_summary.json)
- [最终本地质检 Skill](skills/autoresearch-task-qa/SKILL.md) / [V4 合同](skills/autoresearch-task-qa/references/phase3-v4-contract.md)
- [Skill 版本说明](handoff/SKILL_VERSIONS.md)

本仓库包含 Hidden、Reference 和专家历史证据，是**可信操作者交接目录**。解题 Agent 仅接收 `environment/` 构建的公开环境，不能挂载整个仓库、接收交接文档或查询本仓库的专家材料。用户已知仓库公开并明确授权直接上传。

先使用 A100，H20/L20 暂缓，是用户对当前工作的明确决定。它不自动改变平台 V4 的卡型要求；最终平台 QA15 是否接受 A100 需要真实豁免或后续目标卡证据，不能修改审查规则制造 PASS。

无 API 密钥、密码、登录配置或大型 FLUX 权重。所需 19 个模型文件的准确哈希已附；基础设施、资产、官方工具缺口全部写在交接中。


## 第二题 auto0776 / OneDC 的独立交接

用户另行交接的 auto0776 请从 **[auto0776/README.md](auto0776/README.md)** 和 **[auto0776/START_HERE.md](auto0776/START_HERE.md)** 接手。包含842个原始源码/证据文件、六次B/R原始评分日志、59轮原audit/started、完整修改方案、网盘恢复清单、五个当前技能目录和交付验收门槛。

本题有独立的 [auto0776/AGENTS.md](auto0776/AGENTS.md)。上面的auto0505/A100约定不自动套用于auto0776；按用户当前选择的题目和对应子目录合同执行。交接完整性核验不等于目标卡/平台/正式QA已通过。

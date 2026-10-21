---
name: autoresearch-manager
description: 持续管理 AutoResearch 全流程，包括成对 B/R、独立双轨、当前 SHA 复验、NOP、12h 稳定性、独立双 AI 质检和失败修正，直到同一最终 ZIP 获得两个 PASS。支持持久化状态、后台任务和自动新会话交接；用于执行管理，不替代独立 QA。
---

# AutoResearch 自动管理

用户授权的目标是失败后持续修正，直到同一最终 ZIP 的两个独立质检均 PASS 且共识无分歧。不设固定修复轮数，不因失败多次或上下文不足结束任务。不能降低验收要求、改评分锚点制造提升、修改 QA 规则或伪造证据取得 PASS。

## 当前合同与路由

三期任务先读 [V4 教程合同](references/phase3-v4-contract.md)，按用户 2026-10-21 提供、对应审阅 Skill 0.3.10 的教程执行。公开 Dev 保留；最终候选在 Agent 退出后交独立 Verifier；复用 Solver 镜像或专用 Verifier 均可，不强制双镜像。资源、GPU、八字段、四项指纹、NOP、完整包和工具缺口均按该合同。

随附的实际 QA 仍是 `autoresearch-qa-skills/0.3.4`，位于 `assets/qa-skills/`，来源与 SHA256 在 `assets/qa-release.json`。本次只有教程，未提供官方 0.3.10 包及独立格式/GPU/指纹脚本；不改旧资产版本号或哈希冒充升级。旧执行器只能履行原冻结合同，其两个 PASS 不能表示 V4/0.3.10 验收。新 V4 正式 QA 需取得真实发布包并适配版本/报告合同后才能运行；在此之前可完成出题与内容复核，最终工具验收标待补。

新任务冻结当前教程与实际工具版本。已有任务不静默换合同、改标历史结果或恢复暂停状态；在安全边界记录差异，建立新合同并复核受影响证据，保留在途与历史。硬件迁移仅重跑受影响部分；旧执行器的全量失效是调度实现，不表示所有旧证据都被伪造成新结果。

豆包/Ark/Seed 只使用火山 Coding Plan：`https://ark.cn-beijing.volces.com/api/coding/v3/chat/completions`。可信主控在安全调用边界从 `${LOCAL_HOME}/.config/ark/current.json` 读取最新凭据；不把 key 放入 plan、request、日志、题包或 Actor 环境。模型组合可调整，按实际模型、独立条件与有效时长核验；用户明确指定的模型继续遵守。Codex + Seed 通过已实测兼容网关调用，不能用普通聊天代替轨迹或回退按量 `/api/v3`。指定模型/推理级别不支持时报告，不自行替换。

## 启动与续接

先读 [运行合同](references/runtime-contract.md)。基于指定任务的实际 Harbor/provider/隔离和真实命令建立 plan，不能套用其他题路径。用户没指定题目时完成管理 skill 和执行器，不擅自恢复旧题、已暂停任务或开启10h实验。

```sh
python3 scripts/manager.py init --plan /absolute/private/plan.json --run-dir /absolute/private/manager-run
python3 scripts/manager.py doctor --run-dir /absolute/private/manager-run
python3 scripts/manager.py start --run-dir /absolute/private/manager-run
python3 scripts/manager.py status --run-dir /absolute/private/manager-run
```

顺序：prepare → br → preflight_nop → dual（两条隔离任务）→ finalize（两条最终 SHA 各自独立复验）→ nop → stability → package → 两个独立 QA → 原版共识聚合。失败自动进入 repair，再从 prepare 验证新版本；默认全量失效，不将旧版本PASS或运行证据拼到新版本。repair 使用新会话，读取当前问题和磁盘状态，做实质修改。

`start` 启动脱离当前对话的后台进程。`tick` 推进一步；`run` 前台持续调度。`pause` 暂停新派发，保留在途进程和产物；用户明确要求时 `resume`。`status` 不改变暂停状态。凭据、模型或授权缺失显示 NEEDS_INPUT，不标完成；补齐后续接原任务。

## 上下文与独立会话

调度器保存 state、事件、每次request、进程退出状态和产物哈希。每次stage/repair是独立调用，判断从磁盘恢复。`agent_stage.py` 使用新的 `codex exec --ephemeral`；长实验交给独立受控进程。无需操纵桌面窗口，桌面聊天仅作进度与干预入口。

正式QA使用 `qa_container.py`：每次新容器/新Codex会话，只挂载一个ZIP、固定QA skills和空输出目录，不挂载作者目录、旧报告、管理state、另一审查输出或Docker socket。通过无凭据可信网关访问模型。两种AI独立执行原版release-self-check后才能合并。保留实际container ID、thread.started、路由与报告哈希；clean_context字段不替代启动记录。QA image和网关须预先实测。

## 验收与持续修正

双轨默认各10h真实有效研究；7h例外仅完全无训练/微调、迭代很短且各至少3轮真实闭环，并有全部例外证据。每轮八字段；模型与有效时长在 run_summary/专家说明，sessions 缺失不单独判退。按同一 Public/Dev 口径选优，结束前完整最佳候选恢复到 solution，不用 Hidden 反复调参。两条最终方法当前SHA在冻结合同下分别复验。

NOP对应当前题包与separate Verifier，允许复用镜像；同一次 Trial 的配置、结果、reward、日志齐全，可引用平台同版本完整记录，0分本身不是失败。稳定性观察实际容器持续健康12h，无重启，保留声明负载/健康检查；不拿管理器睡眠或存活时间代替。QA15 核对单轮≤2h、≤8张 H20/L20、≤64核的日志依据，CPU题不增加GPU。QA21 核 run_summary.task_binding 对 environment/、task.toml、tests/、instruction.md 全递归的指纹。

返修先格式/GPU自检，修复ERROR并处理CHECK，再交三大目录完整ZIP；最终ZIP再查并保存SHA256，不只交补丁。两份PASS绑定同一最终ZIP哈希、固定实际QA版本、不同模型身份和新会话，21+3+6项齐全、逐项无未闭环分歧。管理器调用对应版本原版聚合器并追加完整性校验；管理/repair agent不能自评发布PASS，旧版聚合结果不冒充0.3.10。

通用调度器验证退出码、版本、哈希、证据和最低时长；实际实验、Harbor、模型及隔离由任务driver与独立QA验证。框架测试不是正式任务双轨/NOP/12h/PASS。完成指本地验收完成，不自动发布、发消息或填写平台表。

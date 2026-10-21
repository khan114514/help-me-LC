# 模型路由与独立执行

> 当前优先读[五项非阻断口径](00_CURRENT_REVIEW_POLICY.md)。本文件涉及指纹/哈希、换卡补证和H06/NOP的旧硬门槛由该口径覆盖，不因此强制补跑/判退；其他核心检查保留。旧工具结果原样保留，另列用户口径结论。

## 指定模型

| 轨 | 模型 | 推理档 |
|---|---|---|
| GPT | gpt-6.1-sol | xhigh |
| Seed | doubao-seed-2-1-turbo-260628 | high |

这些是该题已有的实际配置，不是其他题的默认值。用户未更换前不自行替换；套餐不支持指定模型/档位时报告，不用“差不多”的模型顶替。请求模型与可观察实际返回模型分开记录，服务版本不可观察则null。

## Seed/Ark统一Coding Plan

Base URL：`https://ark.cn-beijing.volces.com/api/coding/v3`；Chat Completions 路径：`/chat/completions`。

可信主控在安全调用边界读取用户本机 `~/.config/ark/current.json`（权限0600）的最新授权配置。仓库、Actor、候选容器、请求落盘文件和日志都不能包含密钥。无需在交接时复制配置；新主控未能读取时让用户在可信侧配置，不把key粘进聊天或命令行。

禁止自动回退按量 `/api/v3`；历史原模型网关使用过时 `/api/v3/responses` 和旧私有端点，不得原样恢复。repo中的remote技能也明确禁止其legacy worker的ark/ark-profile/codex-seed系列动作；旧helper测试成功不代表当前可用。

Codex使用的Responses/tool流与Coding Plan Chat Completions是不同接口，需要经过真实验证的可信协议适配网关。仅改URL不够。接手需复用已批准并可核验的新网关，或实现并验证适配、流式工具调用、错误/超时和实际coding tool事件。先小型真实工具闭环，确认工具确实执行再开长轨迹。纯文本回复、CLI退出0但所有shell工具失败，均不是合法研究闭环。

本交接没有启动模型请求，没有验证套餐当前是否支持上述模型，也没有把旧主机网关复制为可执行新方案。

## 三类隔离

1. **研究两轨**：同题面、Public、资源、提示和协议；各空输出目录/独立状态，若续接只加入自身合法Public历史。不见另一轨、Reference或最终Hidden。
2. **研究与最终评分**：Agent只有Public/Dev；结束后仅候选solution进入另一个Verifier sandbox。可信评分可以读私有资产，候选工作进程不能读私有标签/参考，也不能改评分器和reward。
3. **最终独立QA**：两种AI各新会话/隔离输出，只收到同一完整ZIP和固定QA技能；没有作者交接、旧报告、另一QA结论。独立首轮完成后再合并分歧；有硬失败继续修复，重新冻结完整ZIP供两边复核。

主控看本仓库不等于Actor可以看。模型凭据属于主控，不以“远端运行需要”为理由注入Actor环境。不得把真实final Hidden结果作为下一轮Public反馈。

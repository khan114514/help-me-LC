# auto0776：OneDC 返修完整交接

**最新用户口径优先：**2026-10-21的[五项非阻断待补/待核](handoff/00_CURRENT_REVIEW_POLICY.md)优先于本文和旧参考中的冲突门槛。指纹/哈希差异、换卡影响/耗时/重算补证、H06/NOP不单独判退或强制补跑；其他核心要求保留。旧工具原始结果不改，另列用户口径结论，可为“通过（含放宽待补项）”。

题目：**One-Step Diffusion-Based Image Compression with Semantic Distillation**。本目录是专家侧材料，目标是完成本次返修、真实复验和独立质检，最后交回完整压缩包。

**当前不是已通过的最终题包。** 旧文件中的 passed、target_met、14.6/14.9h和旧版QA结论只是历史记录，不能作为当前V4验收结论。不要把整个仓库打包或交给研究Actor。

## 从这里接手

1. 阅读 [AGENTS.md](AGENTS.md)、[完整接手提示词](START_HERE.md)、[返修计划](handoff/01_REPAIR_PLAN.md)。
2. 阅读 [部署修改](handoff/02_DEPLOYMENT.md)、[轨迹与时间](handoff/03_TRAJECTORIES_AND_TIME.md)、[模型隔离](handoff/04_MODEL_AND_ISOLATION.md)、[验收交付](handoff/05_ACCEPTANCE_AND_DELIVERY.md)。
3. 阅读 [最终技能版本说明](handoff/06_SKILLS_AND_TOOLS.md) 和 [V4合同](skills/autoresearch/references/phase3-v4-contract.md)。
4. 从本目录运行 `python3 tools/verify_handoff.py`，确认下载完整。它只校验交接文件/历史证据，不是任务QA。
5. 复制 `source/onedc_v9/` 到新的作者工作目录，按方案修复，保留原件。外部大文件按 [恢复清单](assets/RECOVERY.md) 获取，准确元数据见 [archives.json](assets/archives.json)。
6. 最终按同一候选ZIP取得两种AI独立PASS和无分歧共识，交回完整三目录task ZIP及报告、SHA；不只交补丁。

## 已经备齐的材料

| 路径 | 内容 |
|---|---|
| `source/onedc_v9/` | 842个历史候选文件，原字节保留：任务源码、Starter/Reference、B/R/U、原日志、逐轮方法/结果、已有NOP/A10复验与稳定性材料 |
| `evidence/original_clock_records/` | GPT48轮、Seed11轮的原audit/started，共118文件；可追溯分数和时间，没有模型请求正文或凭据 |
| `evidence/missing_attempts/` | GPT23、Seed3/7的真实缺号说明 |
| `skills/` | 当前AutoResearch主技能、manager、remote、QA、Baseline技能及参考/脚本；本机V4整合与真实旧工具版本明确区分 |
| `assets/` | 网盘位置、精确已知哈希/大小、权重成员深审计；多GB文件留在用户网盘 |
| `historical_helpers/` | 两个历史资产处理实现，使用前适配，不含旧过时模型网关 |
| `tools/` | 只读完整性/轨迹检查、人工区间账本算术、完整三目录压缩；均不是官方0.3.10 |
| `manifests/` | 交接文件SHA、原v9来源、技能逐文件来源/可移植投影；不是官方四项指纹 |
| `handoff/STATE.json` | 当前待办与真实状态，不把未做的工作填true |

B/R六份原始stdout/stderr合流日志已找到，43–47行、24图、退出0；本次逐份与原始校准归档成员核SHA一致，两个split码率门均通过。旧A10六次不为“找日志”无条件重跑。各次都是固定seed0的fresh-process评分，不是跨seed或跨硬件稳定性证明。

formal墙钟上界仅GPT约5:08、Seed约5:14，扣除无效区间后还会更短。旧主时钟的14.6/14.9h不能用于本次验收；应审定合法区间并仅续做不足部分。

## 外部前提和真实性

运行仍需用户授权的网盘下载、新H20/L20服务器SSH、目标平台/镜像/隔离能力、可信模型主控配置，以及真实官方0.3.10发布包和独立格式/GPU/指纹脚本。不能从仓库制造这些依赖或声称已取得。缺某项时继续独立可做工作，最终必需验收项保持待补。

原模型为 `gpt-6.1-sol/xhigh` 与 `doubao-seed-2-1-turbo-260628/high`；未经用户指令不换。Ark/Seed只用Coding Plan，密钥只在可信主控读取。交接整理未启动GPU/模型实验，旧暂停/结束状态保持。

同仓库的auto0505是另一题，遵守它自己的用户指令；本目录的H20/L20与时间合同不推广到另一题，也不继承另一题的A100例外。

# 交给接手执行者的提示词

**最新用户口径优先：**2026-10-21的[五项非阻断待补/待核](handoff/00_CURRENT_REVIEW_POLICY.md)优先于本文和旧参考中的冲突门槛。指纹/哈希差异、换卡影响/耗时/重算补证、H06/NOP不单独判退或强制补跑；其他核心要求保留。旧工具原始结果不改，另列用户口径结论，可为“通过（含放宽待补项）”。

请接手本仓库的 auto0776（One-Step Diffusion-Based Image Compression with Semantic Distillation）返修，按 AGENTS.md 和 handoff/ 执行，完成后给用户完整压缩包。

先运行 `python3 tools/verify_handoff.py`，阅读 handoff/01–06 和 skills/autoresearch/references/phase3-v4-contract.md。将 source/onedc_v9 复制到新的作者工作目录，保护原始证据。先整理已经找回的六份原始评分日志和 τ=0.6 的既有扫描证据，再完成目标平台单容器与 H20/L20 适配、Public 评分、受影响成对验证及同版本 NOP。随后逐轮修复轨迹、按真实区间核算各轨有效时间，继续不足部分的合法研究，最终选择唯一 best 并干净公开复验。没有要求无条件重跑全部历史研究。

已有材料不等于全部验收完成：旧 14.6/14.9h 包含非研究时段；formal 墙钟上界仅约 5:08/5:14；旧轨迹虽部分改为 null，但有些轮次存在同候选 Public 回执，不能全清成“未出分”。正式每轮仅八字段，审计字段迁旁表；缺号以真实未闭合记录解释，不补造。

沿用 gpt-6.1-sol/xhigh 和 doubao-seed-2-1-turbo-260628/high，分别独立上下文；只给每轨自己的 Public 历史，不给本交接、Reference、Hidden 或另一轨。主控能看专家材料，但不得传给研究 Actor。Seed/Ark 只走 Coding Plan，凭据只在可信主控读取，不回退按量路径。旧 runtime gateway 使用过时路由，禁止直接恢复执行。

用户会提供新卡 SSH；网盘里的 onedc-assets.tar.gz 和 onedc-env-v8.tar.gz 的路径/哈希见 assets/RECOVERY.md。大文件、登录态、SSH、模型凭据和真实官方 0.3.10 工具是外部依赖，不能从仓库生成或伪造。遇到需要用户补充的依赖时说明具体缺口，同时继续独立可做工作。

最终补齐 expert_annotation.json、唯一 best_method、最终代码哈希、与研究版本对应的四项官方指纹、原始 B/R 评分、逐轮轨迹、研究时间账本、目标环境资源/码率/确定性/锚点比较及当前 NOP。完整 ZIP 接受两种 AI 独立质检；任何硬失败或分歧都返回修复，直到同一候选 SHA 两份真实 PASS、共识无分歧。不能用旧版 PASS 冒充 V4/0.3.10，通过结论由证据支撑。

交付用户：完整候选 task ZIP（根目录 workspace/、expert_evidence/、optimization_evidence/）、QA 两份报告和共识、ZIP SHA-256、简洁修改与验证说明。可另包一个 delivery ZIP 放这些文件，但须保留被审 task ZIP 的原始字节。

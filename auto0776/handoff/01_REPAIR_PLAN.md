# 返修任务、已核实证据与最小动作

> 当前优先读[五项非阻断口径](00_CURRENT_REVIEW_POLICY.md)。本文件涉及指纹/哈希、换卡补证和H06/NOP的旧硬门槛由该口径覆盖，不因此强制补跑/判退；其他核心检查保留。旧工具结果原样保留，另列用户口径结论。

本文是作者交接，不是独立 QA 结论。日期 2026-10-21，时区 Asia/Shanghai。

## 0. 用户的原始六项意见

1. 补 B/R 各三次正式评分的原始 stdout/stderr，关联 result/metrics、冻结方法和镜像；核模型加载、24 图、独立进程、退出与两个 split 码率门。
2. 改为平台支持的单容器；移除动态 Compose、宿主 lease/AppArmor 等依赖；处理不支持的存储/断网配置；Agent/Verifier 各自明确 H20/L20；保留 A10 标签，补资源估算/比较及同版本 NOP。
3. GPT 第 1 轮未测试却为 ok；27 个 failed 轮次沿用旧分数。未出分 null；已评分后 CLI 失败给同轮回执；缺号说明真实尝试。
4. 补 expert_annotation、唯一 best_method、最终代码哈希、干净 Public 复验、同步轨迹/汇总、与对应研究版本绑定的四项指纹。不得用当前包哈希倒填历史。
5. 扣除 setup、排队、安装、故障和暂停后 QA 后重算，每轨默认 10h；仅全部满足无训练/短迭代/三完整闭环/后续方向/best 干净复验等条件才考虑 7h 例外。
6. 补 τ=0.6 的既有扫描、真实选择集及双方预算；固定 seed 重复评分只证明该协议重复性。

建议先日志，再处理环境/GPU，最后轨迹、有效时长和版本绑定；未要求无条件重跑全部历史研究。当前交接仅 auto0776；“统一处理两题”的另一题未在本聊天定义，不擅自修改另一题。

## 1. 原始六日志：已找到，先纠正交付版本/入口

正式路径：`source/onedc_v9/optimization_evidence/{baseline_runs,reference_runs}/seed_eval_replicate_{1,2,3}/run.log`。

原始路径：`source/onedc_v9/optimization_evidence/native_calibration_v8/original_records/raw/{B,R}_{1,2,3}/`，含 run.log、execution.json、out/metrics.json 和逐图结果。PROVENANCE.json 记录原始归档成员与 SHA；正式日志与 raw 日志字节相同。原 wrapper `original_records/task/tests/calibration_bundle_verifier.py` 每次独立 subprocess.run，stdout 文件、stderr=STDOUT。这种合流日志保留原始输出，不另外伪造 stderr。

本次已逐份对比原 `final-calibration-evidence.tgz` 成员 SHA，六次全相同；日志均有 24 条逐图编码记录、模型加载和末尾输出；execution 退出均 0、seed 均 0、方法 SHA 与 result/metrics 相同；public/hidden 码率门均通过。

缺失的数值 PID、每次绝对启动时间原本未记录，不反推补造。独立进程的依据是原始 wrapper 调用与执行回执，限于该证据强度。归档整体 SHA 为 `2b799f7251c7724163f1d32ead30d404d7d88b28634f35ee859e6e60fbfdddb1`，146075097 字节，516 文件；它未全部放入 Git（超过单文件限制，且含不应公开到 Agent 的资产），可公开原始评分部分已在本仓库。

历史 A10/最终 v8 镜像 ID：`sha256:40875d7a85a1923dbd2041239f7d1ffa367e20e95e1aa31546cfe2dffa08a2c5`。这不是新平台实测。

| 角色 | 全 24 图 DISTS（每次相同） | Public bpp | Hidden bpp |
|---|---:|---:|---:|
| B ×3 | 0.11711087326208751 | 0.020015716552734375 | 0.02144622802734375 |
| R ×3 | 0.11463754375775655 | 0.02001317342122396 | 0.021352132161458336 |

旧 cap：Public `0.020115795135498046`，Hidden `0.021553459167480468`；各等于对应 B bpp×1.005。full 的 U=0.11314917107423146，R 归一化=0.6243098009518612。Public B=0.12342559173703194、R=0.12056996300816536、U=0.118447195738554，R 归一化=0.5736041748666919。实际从对应 metrics/anchors 复算，勿交叉混用 split。

**验收动作：**确认被审核原 ZIP 的 SHA；将现有原始文件放到规范主证据入口，补逐文件关联表和说明；旧七行/八行摘要另标 historical。已找到的旧 A10 六次不用为“补日志”重复执行。新目标卡影响另在新版本验证。

## 2. 部署：需要真实改造

旧 task.toml 尚有 storage_mb/no-network、未明确目标卡、候选移交依赖 collect；platform_adapter/onedc_harbor.py 仍硬依赖宿主 lease、AppArmor 和动态 Compose。完整修改方案见 02_DEPLOYMENT.md；仅改 GPU 字符串不能完成返修。

## 3. 轨迹：v9 只是部分纠正

v9 已把 GPT 第 1 轮变成 not_run/null；失败行已普遍清数值，但每轮仍带额外审计字段。有些 Seed 轮次实际上存在同候选评分回执，必须逐轮判断。`tools/inspect_trajectories.py` 可只读列出原始与衍生记录、同 SHA 新回执及额外字段。

原始行号：GPT 48 行、最大49，缺23；Seed 11行、最大13，缺3/7。缺号对应未闭合尝试，见 evidence/missing_attempts。不能插入虚构成功/失败方法轮；保留原始 attempt_id 映射，并依真实发布格式决定连续 round 与 attempt_id 的旁表关系，说明旧号与整理号映射，不伪造实验。

## 4. 唯一方法与注释：尚待最终收口

v9 没有标准 expert_annotation.json/best_method。现有 `expert_evidence/final_native_replays/gpt/method.py` 是可追溯历史候选，SHA `db57c37907109775875e3f1e1146acedc026e003b0d8bcf6bb480c39f4fe9acb`，Public DISTS=0.11724298819899559。它有旧 A10 full24 干净评分记录，不替代新目标环境 Public 干净复验。研究续做后可能出现更优合法候选，最终依据 Public 选，而非事先冻结这个文件为最终答案。

## 5. 时间：需要区间账本和续做

旧主计时把 setup/构建/队列/故障/暂停后 QA 算入；当前用户要求扣除。不得把旧“已达标”状态移植到新包。也不得机械用旧严格闭环算法中的零有效时间抹掉所有合法方法分析。见 03_TRAJECTORIES_AND_TIME.md。

## 6. τ=0.6：目前仅有汇总，不足证明完整既有扫描

`expert_evidence/02-optimization-surface.md` 是早期 A100/Kodak24 表，列 τ=0.6/0.7/0.8，并声称按0.05粒度扫描；该表不能替代完整原始扫描、选择集、尝试次数和双方成本账本。

先搜索旧专家材料和原始记录；写清真实历史选择集是全24还是 Public、当时何时划分、双方候选和预算，不能把全24扫描改称 Public 选择。不得以“两个参数数值步长差不多”代替实际公平搜索机会。找不到历史原始记录就写缺失；新做合理性/敏感性检查单列当前日期与版本，不能包装成旧扫描。

固定 seed0 三次 fresh-process 一致，只支持该设备、镜像、数据、精度和协议下可重复；不声称跨 seed/跨硬件稳定，也不造训练曲线或独立训练。

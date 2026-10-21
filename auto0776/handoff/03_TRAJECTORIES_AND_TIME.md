# 轨迹、回执、合法研究时间与续接

> 当前优先读[五项非阻断口径](00_CURRENT_REVIEW_POLICY.md)。本文件涉及指纹/哈希、换卡补证和H06/NOP的旧硬门槛由该口径覆盖，不因此强制补跑/判退；其他核心检查保留。旧工具结果原样保留，另列用户口径结论。

## 原始记录在哪里

- v9正式投影：source/onedc_v9/expert_evidence/trajectory_codex.json 与 trajectory_seed.json。
- 原controller轨迹：expert_evidence/final_research_history/{gpt,seed}/original-controller-trajectory.jsonl。
- 每轮代码、Public metrics、审计投影：同目录 rounds/；其中代码快照的 SHA 是核对分数是否属于本轮的依据之一。
- 原audit与started：evidence/original_clock_records/{gpt,seed}/private-rounds/。这118份文件保留原字节；gateway_records只含请求/响应元数据与内容哈希，没有请求正文、凭据或另一轨上下文。
- 缺号：evidence/missing_attempts/ 与 v9 expert_evidence/unclosed_attempts/。

先跑 `python3 tools/inspect_trajectories.py --out /tmp/auto0776-trajectory-review.json`。输出只是待人工核对清单，不能自动将所有匹配回执当该轮最终选择。

## 正式八字段

每轮只保留 round、policy_name、method_summary、status、score、failure_reason、retained_best、time。time 为 Asia/Shanghai 的 YYYY-MM-DD HH:mm:ss；模型、协议、有效时长放 run_summary，审计扩展字段/旧attempt号/方法哈希/命令/回执路径放旁表。

| 实际情况 | 正式记录 | 附证据 |
|---|---|---|
| 未实际测试，如GPT第1轮 | not_run 或真实失败类型，score=null，retained_best=false | 原事件、无同轮评分的说明 |
| CLI失败且本轮没生成新分数 | 失败类型，score=null | CLI状态；旧分数只能在历史栏，不能沿用 |
| 已评分，之后CLI失败 | 如实失败状态；score填写已声明Public指标真实值；failure_reason解释 | 同方法SHA、run_id、协议、时间顺序的评分回执，不用另一候选结果顶替 |
| 方法触发实际码率hard gate | 按评分器实际-1无效协议记录；旁表可保留DISTS/bpp，正常排序不使用 | 原回执；不伪装成基础设施失败或普通0分 |
| CLI结束但评分对象与最终文件SHA不同 | 不把该分数绑定最后候选 | 分开列评过的中间方法与最后文件，必要时新版本干净公开复验 |

同方法SHA相同只是必要线索，不足以证明旧分数是新评分；检查new_public_receipts、run_id和顺序。v9曾将失败轮全部清null，需纠正其中确有分数的情况。已见Seed第1/5轮有同SHA有效回执，第11–13轮有同SHA硬门回执；第2/4/6/8/10等可能评分的是中间候选，不能套给最终代码。保留原所有回执、差结果和失败。

注意指标映射：旧v9轨迹声明score是Public DISTS（越低越好），原评分回执的`score`却是归一化奖励；纠正有效数值时应取回执`dists`，不要将例如0.232的归一化奖励混进约0.12的DISTS轨迹。归一化值与质量门另在审计旁表保留；无效-1的标记须与所采用的公开协议/汇总定义一致，并且不参与普通方法排序。续做新版本若统一改用归一化口径，必须明确分段和映射，不能静默混用。

GPT源序号1–49缺23；Seed1–13缺3/7。当前V4要求round递增；若真实格式检查要求连续号，把已存在的真实研究记录连续编号，旧attempt号移旁表，提供一一映射。不能为了补号创造未发生的方法/分数/时间。

## 当前时间事实

| 轨 | formal 开始（上海） | 暂停 | 该段墙钟上界 | 即使不扣除，距10h仍至少 |
|---|---|---|---|---|
| GPT | 2026-10-04 16:03:16 | 21:11:43.022668 | 18507.022668s，约5:08:27 | 17492.977332s，约4:51:33 |
| Seed | 2026-10-04 16:01:33 | 21:15:34.694233 | 18841.694233s，约5:14:02 | 17158.305767s，约4:45:58 |

这些是上界，**不是审定有效研究时长**。开始与暂停来自旧time-accounting/transition记录。其间还需扣明确无效区间；若还有其他合法、独立且可追溯研究段，可审定后另列，不能把已知隔离有缺陷的早期探索或共同setup信用自动加给两轨。

旧主时钟14.59h/14.94h使用宽口径，把setup、构建、队列、故障、HTTP连上但阻塞及暂停后QA计入；本轮用户要求扣除。旧strict时钟又只计特定成功闭环，对正常方法设计/分析/真实方法失败可能过严，不能机械当当前V4真实值。

## 重算方式

1. 基于 started/audit、真实Public回执、CLI/工具事件、gateway元数据构建每轨独立区间。timestamp的单位/时区按原值核对，不从文件mtime猜实验时间。
2. 每段明确分类：method_design、analysis、evaluation、normal_training（此题通常不适用）、method_failure；以及setup、install、queue、infrastructure_failure、api_block、paused、post_pause_qa、final_recheck。
3. 只计可证明的合法研究区间；扣除无效重叠部分，区间并集计算，重叠不重复计。对一次API调用不能仅凭HTTP200/429认定整段都是有效分析，也不能仅凭CLI非零否定之前完整方法闭环。
4. `templates/time_ledger.json` 故意为空且未审定。人工填可定位的区间、证据与理由，再用 `tools/time_accounting.py` 算术复核；工具不会替你决定区间是否合法。
5. 复验、NOP、12h稳定性、打包和QA另列。正常方法失败保留；环境故障排除。等待、重复调用同一评分器和空转不补研究时长。

## 合法续接

默认每轨10h。当前还没有充分7h例外证据，不预先选例外。仅当无训练/微调、迭代确短、每轨至少3个完整方法→Public评分→决策闭环、持续演进及下一方向、best干净复验等全部具备时，才按真实合同说明例外。

旧控制器已暂停/结束，本仓库不恢复旧主机。接手收到用户新卡和执行授权后，在新冻结输入版本上续接，保留实际原模型和每轨自己的Public历史。不能把专家的Reference/Hidden/本交接或另一轨发给Actor。若旧Actor已看过Hidden/Reference，不能复用受污染上下文。

环境迁移若只改运行依赖，仍需有Public桥接/冻结面一致依据；评分协议、数据、方法边界实质变化时分段绑定版本，说明旧段为何可继承，无法证明的段不强行累加。不为新包倒填历史hash。

后续方向由各轨根据自身Public结果独立提出；交接主控不把另一轨或专家Reference算法当研究提示。最终每轨恢复其Public最佳候选，再按同协议选唯一最终方法；Hidden结束后一次正式评分，不反复指导续做。

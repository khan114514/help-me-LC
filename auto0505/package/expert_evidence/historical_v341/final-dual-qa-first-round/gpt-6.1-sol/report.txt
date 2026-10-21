# 优化面介绍

冻结FLUX与RF二阶积分器，开放时间步节点生成完整算法，CPU候选仅输出26节点给受控GPU服务。

可修改：/workspace/solution/method.py:get_timesteps全部节点生成策略。

固定面：FLUX权重/二阶积分公式；25步每方向，100NFE/图；512×512、空提示、guidance1/inject0、公开12+私有4图。

指标与质量门：最大化full16平均PSNR，连续未裁剪(B,U)归一化；节点数/端点/有限性/范围/单调与资源、来源门禁。

# Baseline 与 Reference 跑分

Baseline 方法：未经修改官方FLUX time_shift：序列长1024决定mu≈0.63，对均匀t作logit shift；冻结预训练模型推理，无训练。正式B是当前NOP/Starter full16。

Reference 方法：正弦t=sin(s*pi/2)，均匀s从1到0，高噪声端密集；保持同FLUX模型、二阶公式及100NFE；当前独立正式full16。

主指标：mean image PSNR (dB)（越高越好）。

| training_seed | Baseline | Reference | 配对改善 | 有效性 |
|---|---:|---:|---:|---|
| deterministic_full16 | 19.5288824095 | 20.4573492842 | 0.928466874721 | B:是 / R:是 |

汇总：Baseline 均值 19.5288824095，样本标准差 -；Reference 均值 20.4573492842，样本标准差 -。

改善结论：全正式配对1次：改善0.928466874721483dB；归一化0.462674017825915。无训练seed；固定确定性评测，不把16张图当16次随机重训。

质量门：两侧full16、100NFE、相同冻结协议/资产/权重，正常退出；全部逐图Reference优于Baseline。

# 前置内容门槛

| 门槛 | 结论 | 原因 |
|---|---|---|
| G01 方法级优化空间 | 通过 | get_timesteps可执行任意确定性节点算法；guard限制来源/资源及输出，不限制固定字面量参数搜索。 |
| G02 Baseline 合理性 | 通过 | 在已提供材料范围内合理：官方time_shift Starter绑定正式B；非训练冻结模型同协议full16正常执行，原始receipt/metrics/log一致，未见故障弱化或选择偏差。 |
| G03 Reference 提升充分性 | 通过 | 当前正式确定性full16配对改善0.928466874721483dB，归一化0.462674在[0.15,0.8]；U来自独立已测上限，质量门及预算一致。 |

G03 复算：Δ=0.928466874721；σ_B（样本标准差）=待确认；U=21.535623309；归一化分数=0.462674017826。

# 两条轨迹迭代概况

| Agent 轨迹 | 状态 | 打包轮数 | 声明有效轮数 | 时长 | 概况与最终结果 |
|---|---|---:|---:|---:|---|
| Codex + GPT-6.1 Sol xhigh | 完整 | 102 | - | - | 独立方法探索含密度、幂律、误差模型/网格策略；原失败和协议范围保留。精确生命周期净时长未知；当前协议Public复测GPT21.21974298189495 / Seed21.66197823479546；按Public选择Seed后full16 reward0.8703690797499839。 |
| Seed 2.1 Turbo (High资格未独立确认) | 完整 | 47 | - | - | 独立方法探索含密度、幂律、误差模型/网格策略；原失败和协议范围保留。精确生命周期净时长未知；当前协议Public复测GPT21.21974298189495 / Seed21.66197823479546；按Public选择Seed后full16 reward0.8703690797499839。 |

# 格式对齐建议

三目录职责存在。非训练正式记录采用actual_v341而非seed_*，语义等价；训练证据说明/comparison_summary文件名未提供，但方法说明及原始运行覆盖内容。历史大量附件建议按版本索引，额外内容不单独扣错。

- `DRAFT-MANIFEST.json`（可保留的额外项）：规范外附加材料；多交不构成格式失败。
- `FINAL-ZIP-CONTENTS.md`（可保留的额外项）：规范外附加材料；多交不构成格式失败。
- `optimization_evidence/baseline_runs/actual_v341`（可保留的额外项）：规范外附加材料；多交不构成格式失败。
- `optimization_evidence/reference_runs/actual_v341`（可保留的额外项）：规范外附加材料；多交不构成格式失败。
- `README.md`（可保留的额外项）：规范外附加材料；多交不构成格式失败。
- `rfsteps-package/optimization_evidence/`（可合并）：增加非训练协议与成对指标的轻量索引，明确deterministic_run而非伪造seed；保留原件。
- `rfsteps-package/expert_evidence/nop_evidence/legacy_v32`（可保留的额外项）：标记旧版历史记录不可用于3.4.1结论；当前记录已有独立索引。
- `rfsteps-package/expert_evidence/time-reconciliation`（可合并）：为实际活动与断网原始记录提供包内相对路径索引及计时区间，不引用本机绝对路径替代证据。
- 格式缺口：baseline_runs/ 中没有 seed_<真实seed>/ 运行目录。
- 格式缺口：optimization_evidence 必须包含 comparison_summary.json。
- 格式缺口：reference_runs/ 中没有 seed_<真实seed>/ 运行目录。
- 格式缺口：optimization_evidence 缺少中文训练证据说明.md。
- 格式缺口：最终轨迹 JSON 必须包含 rounds 数组。
- 格式缺口：rounds[17].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。
- 格式缺口：rounds[101].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。
- 格式缺口：rounds 为空，长程轨迹尚未完成或缺少证据；不能用虚构轮次补齐。

说明：额外材料仅作精简或归位建议，不因多交而单独判错。

# 质检结论：未完成检查

产物：rfsteps-package-v3.4.1-preview-20261005T015301.zip｜通过 15 项｜不通过 0 项｜未完成 3 项｜跳过/不适用 3 项

前置三门：通过 3 项｜不通过 0 项｜待核验 0 项；全部复核完成：否。

口径：只读实现情况检查；QA07/08 仅查 instruction，QA15 跳过，QA16 默认要求两条轨迹各至少 10h 有效迭代；仅完全不涉及训练或微调且单轮迭代很短的任务，才可凭资格与闭环等证据采用每条至少 7h 的例外。排队、安装与故障不计。未执行提交代码、未独立复跑参考解或反序列化模型。

Harbor 格式/接口：通过；已有 NOP 自检记录支持当前版本构建与运行可用，未独立复跑或鉴定真伪。

| 检查项 | 是否通过 | 原因 |
|---|---|---|
| QA01 八章节与题面信息泄露 | 通过 | 八章节齐全；题面未含论文、arXiv、仓库线索或参考方法答案。 |
| QA02 评分公式与 0/1 锚点 | 通过 | 实际主分数为(PSNR-B)/(U-B)，U>B，连续单调且未裁剪；score_clipped仅展示未传作reward。 |
| QA03 参考解分数与复现材料 | 通过 | Reference正弦方法有实际full16入口、非空原始日志和指标；归一化0.462674；非训练无checkpoint要求。 |
| QA04 波动指标的 3σ 可分辨性 | 不适用 | 确定性冻结推理；AE返回mean，评分路径无随机采样；包内重复基线与Seed多次复测一致，不以固定seed代替确定性。 |
| QA05 约束执行实现 | 通过 | 降权进程实现CPU/AS/源码上限、来源与子进程门禁，验证26节点和固定100NFE；可信RPC校验数据与预算。 |
| QA06 Verifier 入口、分数与错误处理 | 通过 | test.sh单命令调用正式评分，成功写有限数值reward.json；失败分类并清除旧reward，硬门非法写-1。 |
| QA07 instruction 中的 Hidden 信息泄露 | 通过 | 仅题面检查：没有Hidden样本、标签或可恢复答案；提及独立正式评测不构成泄露。 |
| QA08 instruction 中的参考解信息泄露 | 通过 | 仅题面检查：没有参考实现、具体参考配置或参考分数。 |
| QA09 结果清理与原子写入 | 通过 | main启动清除旧指标/reward；atomic_json临时写后os.replace，失败分支同样清理。 |
| QA10 冻结面保护或恢复实现 | 通过 | Compose只读rootfs；Verifier/tests权限限制；候选降权；GPU worker验证冻结评分器、repo、资产、权重并用新鲜源码副本执行。 |
| QA11 instruction 八项内容 | 通过 | 目标、环境、公式、范围、禁令、提交、迭代及完成条件均有实质内容。 |
| QA12 Git 清理 | 通过 | ZIP清点无.git目录，未发现Git远程或历史答案仓库泄漏。 |
| QA13 Baseline 与参考解提升 | 通过 | 正式非训练full16 B/R均正常完成；同资产/模型/预算/评分器，逐图均改善；不冒充多seed训练。 |
| QA14 合法改进空间 | 通过 | 完整算法接口开放，网格投影及局部预算交换是合法未直接提示方向；Reference score0.462674未饱和。 |
| QA15 资源限制（不检查） | 跳过 | 按用户要求不检查资源与单次迭代限制。 |
| QA16 轨迹实际迭代时长 | 未完成检查 | Codex + GPT-6.1 Sol xhigh缺少 collector 生成的 duration_evidence，手填 effective_seconds 不能单独作为时长证据；Codex + GPT-6.1 Sol xhigh缺少有效时长或排除排队/安装/故障的核算证据；Seed 2.1 Turbo (High资格未独立确认)缺少 collector 生成的 duration_evidence，手填 effective_seconds 不能单独作为时长证据；Seed 2.1 Turbo (High资格未独立确认)缺少有效时长或排除排队/安装/故障的核算证据 |
| QA17 Harbor Harness 兼容性 | 通过 | Harbor 格式/接口：通过；已有 NOP 自检记录支持当前版本构建与运行可用，未独立复跑或鉴定真伪。 |
| QA18 轨迹、日志与分析 | 未完成检查 | 两条轨迹的八字段证据未通过：rounds[101].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。 |
| QA19 seed 与有效提升阈值 | 不适用 | 确定性评估，无随机训练/随机评价seed阈值要求；确定性依据同QA04。 |
| QA20 修改范围、网络与工具策略 | 通过 | 题面给定method.py可改范围、公开文件/文献网络许可与单命令受控评分工具策略。 |
| QA21 三个 JSON 的填写内容 | 未完成检查 | 两条轨迹的八字段证据未通过：rounds[101].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。 |

风险提示（不额外计入清单结论）：12h稳定性未完成：run_summary/stability记录约19080秒，目标43200；不伪称压力测试；外部RPC/权重/Hidden与adapter实际部署必需；ZIP本身未验证任意平台task_id部署；历史时间网络标记无边界/时区，不能把事件凸包当已证明连续有效时长。

# 退回专家说明

QA16 轨迹实际迭代时长（待补充核验）：Codex + GPT-6.1 Sol xhigh缺少 collector 生成的 duration_evidence，手填 effective_seconds 不能单独作为时长证据；Codex + GPT-6.1 Sol xhigh缺少有效时长或排除排队/安装/故障的核算证据；Seed 2.1 Turbo (High资格未独立确认)缺少 collector 生成的 duration_evidence，手填 effective_seconds 不能单独作为时长证据；Seed 2.1 Turbo (High资格未独立确认)缺少有效时长或排除排队/安装/故障的核算证据
证据：rfsteps-package/expert_evidence/time-reconciliation/TIME-RECONCILIATION.json；rfsteps-package/expert_evidence/TIME-ACCOUNTING-AMENDMENT.json
请修改/补充：针对上述轨迹补齐有效时段核算，每条达到 10h；仅在完全不涉及训练或微调且单轮迭代很短时，才可凭资格依据采用至少 7h 的例外，并提交具体理由、每条至少 3 个有效方法闭环、后续方向及最优方法复验。
复检验收材料：两条轨迹各自的起止/有效时段日志、被排除时段及理由；如申请 7h 例外，附无训练/微调的实现证据、典型单轮耗时及原始日志、方法闭环与最优方法复验记录。

QA18 轨迹、日志与分析（待补充核验）：两条轨迹的八字段证据未通过：rounds[101].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。
证据：rfsteps-package/expert_evidence/trajectory_codex.json；rfsteps-package/expert_evidence/trajectory_seed.json；rfsteps-package/expert_evidence/trajectory-source-map.json；rfsteps-package/expert_evidence/run_summary.json
请修改/补充：补齐两条真实轨迹，每轮八字段须完整有效；保留失败原因，不补造分数、时间或轮次。自定义状态需说明其语义。
复检验收材料：overview.source_path 指向两份可读取轨迹，轮次及八字段符合教程，并与运行摘要和最佳方法记录一致。

QA21 三个 JSON 的填写内容（待补充核验）：两条轨迹的八字段证据未通过：rounds[101].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。
证据：rfsteps-package/expert_evidence/trajectory_codex.json；rfsteps-package/expert_evidence/trajectory_seed.json；rfsteps-package/expert_evidence/expert_annotation.json；rfsteps-package/expert_evidence/run_summary.json；rfsteps-package/expert_evidence/METHOD-EXPLANATION.md
请修改/补充：补齐两条真实轨迹，每轮八字段须完整有效；保留失败原因，不补造分数、时间或轮次。自定义状态需说明其语义。
复检验收材料：overview.source_path 指向两份可读取轨迹，轮次及八字段符合教程，并与运行摘要和最佳方法记录一致。

待质检员核实的格式观察（等价材料可以认可，不直接作为专家整改结论）：
- expert_evidence/trajectory-source-map.json：最终轨迹 JSON 必须包含 rounds 数组。
- expert_evidence/trajectory_codex-formal04-original.json：rounds[17].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。
- expert_evidence/trajectory_codex.json：rounds[101].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。
- expert_evidence/trajectory_seed-formal04-original.json：rounds 为空，长程轨迹尚未完成或缺少证据；不能用虚构轮次补齐。
- optimization_evidence/baseline_runs：baseline_runs/ 中没有 seed_<真实seed>/ 运行目录。
- optimization_evidence/comparison_summary.json：optimization_evidence 必须包含 comparison_summary.json。
- optimization_evidence/reference_runs：reference_runs/ 中没有 seed_<真实seed>/ 运行目录。
- optimization_evidence/训练证据说明.md：optimization_evidence 缺少中文训练证据说明.md。

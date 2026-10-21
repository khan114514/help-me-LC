# 优化面介绍

冻结RF-Solver二阶公式/模型/100NFE，开放get_timesteps算法返回26个共享节点；实际正弦Reference改变分配函数。

可修改：/workspace/solution/method.py内的确定性节点生成算法。

固定面：FLUX权重和二阶更新；25步/方向、100NFE/图；512x512和冻结公开/私有评测。

指标与质量门：full16平均PSNR越高越好；输出26节点有限、[0,1]、首尾1/0、单调不增。

# Baseline 与 Reference 跑分

Baseline 方法：未改Starter用官方flux-dev time_shift：序列长度1024计算mu≈0.63，对均匀s施logit偏移生成26节点；不训练模型，NOP保留Starter。

Reference 方法：独立Reference用t_i=sin((1-i/25)π/2)生成26节点，高t端更密；不训练模型，以同样100NFE评估。

主指标：full16 mean PSNR dB（越高越好）。

| training_seed | Baseline | Reference | 配对改善 | 有效性 |
|---|---:|---:|---:|---|
| full16-fixed | 19.5288824095 | 20.4573492842 | 0.928466874721 | B:是 / R:是 |

汇总：Baseline 均值 19.5288824095，样本标准差 -；Reference 均值 20.4573492842，样本标准差 -。

改善结论：Reference +0.928466874721483 dB；归一化0.46267401782591483。

质量门：两个独立Trial均16图、NFE100、同任务哈希，reward有限且无异常；静态复核，未独立复跑。

# 前置内容门槛

| 门槛 | 结论 | 原因 |
|---|---|---|
| G01 方法级优化空间 | 通过 | 方法函数可实现任意确定性节点生成算法；guard审的是输出及安全边界，并非固定字面量搜索。 |
| G02 Baseline 合理性 | 通过 | 正式B为未经修改的官方FLUX time_shift Starter；固定数据/预算，当前NOP同版本运行完整，未见截断训练或挑seed。 |
| G03 Reference 提升充分性 | 通过 | 当前full16单一确定性配对Δ=0.928466875dB，U=21.535623309，归一化0.462674；正式结果通过质量门。 |

G03 复算：Δ=0.928466874721；σ_B（样本标准差）=待确认；U=21.535623309；归一化分数=0.462674017826。

# 两条轨迹迭代概况

| Agent 轨迹 | 状态 | 打包轮数 | 声明有效轮数 | 时长 | 概况与最终结果 |
|---|---|---:|---:|---:|---|
| Codex GPT | 完整 | 102 | - | - | 102轮含历史及formal04；原轮分数保留，现版本最佳方法另作独立清洁复测；历史最优与当前公开选择分开；本轨不是最终选中Seed方法。 |
| Seed 2.1 Turbo High | 完整 | 47 | - | - | 47轮均历史记录；当前公开方法清洁复测并选为最终最佳；所选幂律方法独立full16 PSNR21.27548764；研究净时长未知。 |

# 格式对齐建议

三主目录均有实质材料；collector按旧seed目录/训练文件命名提示缺口与本非训练确定性单pair布局不等价。需补机器可解析时间证据和当前比较汇总索引；历史辅助文件建议归档。

- `DRAFT-MANIFEST.json`（可保留的额外项）：规范外附加材料；多交不构成格式失败。
- `FINAL-ZIP-CONTENTS.md`（可保留的额外项）：规范外附加材料；多交不构成格式失败。
- `optimization_evidence/baseline_runs/actual_v341`（可保留的额外项）：规范外附加材料；多交不构成格式失败。
- `optimization_evidence/reference_runs/actual_v341`（可保留的额外项）：规范外附加材料；多交不构成格式失败。
- `README.md`（可保留的额外项）：规范外附加材料；多交不构成格式失败。
- `rfsteps-package/expert_evidence/nop_evidence/legacy_v32`（旧布局/打包杂项）：旧版本NOP材料单独标明历史用途，当前版本入口指向actual_v341。
- `rfsteps-package/expert_evidence/trajectory-source-map.json`（可保留的额外项）：这是来源映射而非第三条轨迹，保留但标明角色。
- `rfsteps-package/optimization_evidence`（可合并）：提供同版本单pair comparison_summary，便于核对正式PSNR与锚点。
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

产物：rfsteps-package-v3.4.1-preview-20261005T015301.zip｜通过 14 项｜不通过 0 项｜未完成 4 项｜跳过/不适用 3 项

前置三门：通过 3 项｜不通过 0 项｜待核验 0 项；全部复核完成：否。

口径：只读实现情况检查；QA07/08 仅查 instruction，QA15 跳过，QA16 默认要求两条轨迹各至少 10h 有效迭代；仅完全不涉及训练或微调且单轮迭代很短的任务，才可凭资格与闭环等证据采用每条至少 7h 的例外。排队、安装与故障不计。未执行提交代码、未独立复跑参考解或反序列化模型。

Harbor 格式/接口：未完成；已提交 NOP 的运行或任务版本关联待核实。

| 检查项 | 是否通过 | 原因 |
|---|---|---|
| QA01 八章节与题面信息泄露 | 通过 | 题面八部分齐全，未直接写参考正弦方法或论文身份。 |
| QA02 评分公式与 0/1 锚点 | 通过 | 完整评分用未裁剪(PSNR-B)/(U-B)，B=0、U=1锚点方向正确；clipped仅展示。 |
| QA03 参考解分数与复现材料 | 通过 | 独立参考method与当前v3.4.1正式Trial/非空日志和reward齐全，0.462674在目标区间。 |
| QA04 波动指标的 3σ 可分辨性 | 不适用 | 冻结图像、固定节点/权重评估；Baseline重复运行数值完全相同，当前证据按确定性评估。 |
| QA05 约束执行实现 | 通过 | 独立候选worker及受控RPC检查节点、标准库、源码、预算、角色及公开/正式分流。 |
| QA06 Verifier 入口、分数与错误处理 | 通过 | test.sh单命令调用评分，清理旧输出并按失败类别写结果；正常reward.json有限标量。 |
| QA07 instruction 中的 Hidden 信息泄露 | 通过 | instruction仅描述Hidden存在与边界，未给私有样本或标签。 |
| QA08 instruction 中的参考解信息泄露 | 通过 | instruction未披露Reference正弦节点或结果数值。 |
| QA09 结果清理与原子写入 | 通过 | 评分入口预先unlink旧reward并通过同目录临时文件os.replace写结果。 |
| QA10 冻结面保护或恢复实现 | 通过 | 评分执行在受控GPU worker的冻结任务副本，校验冻结资源哈希并隔离候选方法。 |
| QA11 instruction 八项内容 | 通过 | 目标、环境、指标、范围、边界、提交、迭代、完成条件均有实质内容。 |
| QA12 Git 清理 | 通过 | ZIP清点未见.git目录；已检查归档成员。 |
| QA13 Baseline 与参考解提升 | 通过 | 当前任务NOP与Reference同任务哈希、full16及NFE100，PSNR 19.528882→20.457349，正式结果有效。 |
| QA14 合法改进空间 | 通过 | get_timesteps允许新节点生成算法；轨迹包含密度/交换等方向，Reference未饱和。 |
| QA15 资源限制（不检查） | 跳过 | 按用户要求不检查资源与单次迭代限制。 |
| QA16 轨迹实际迭代时长 | 未完成检查 | Codex GPT缺少 collector 生成的 duration_evidence，手填 effective_seconds 不能单独作为时长证据；Codex GPT缺少有效时长或排除排队/安装/故障的核算证据；Seed 2.1 Turbo High缺少 collector 生成的 duration_evidence，手填 effective_seconds 不能单独作为时长证据；Seed 2.1 Turbo High缺少有效时长或排除排队/安装/故障的核算证据 |
| QA17 Harbor Harness 兼容性 | 未完成检查 | Harbor 子项未通过：H02 版本与配置；H03 环境与运行路径；H06 NOP 自检记录；详细原因与证据保留在 report.json。 |
| QA18 轨迹、日志与分析 | 未完成检查 | 两条轨迹的八字段证据未通过：rounds[101].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。 |
| QA19 seed 与有效提升阈值 | 不适用 | 正式评估按固定图像与模型确定性口径；随机seed与3σ题面规则不适用。 |
| QA20 修改范围、网络与工具策略 | 通过 | 题面规定唯一可改文件、网络公开规则与工具调用/开发评分命令。 |
| QA21 三个 JSON 的填写内容 | 未完成检查 | 两条轨迹的八字段证据未通过：rounds[101].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。 |

风险提示（不额外计入清单结论）：两轨精确净时长均为null，时区/断网扣除与collector候选不闭环；collector H06身份检查遗漏[task].name，当前NOP被误判异名；不代表Trial实际失败；12小时稳定性仅约5.3小时样本，且外部GPU/Hidden部署不可移植性待核验。

# 退回专家说明

QA16 轨迹实际迭代时长（待补充核验）：Codex GPT缺少 collector 生成的 duration_evidence，手填 effective_seconds 不能单独作为时长证据；Codex GPT缺少有效时长或排除排队/安装/故障的核算证据；Seed 2.1 Turbo High缺少 collector 生成的 duration_evidence，手填 effective_seconds 不能单独作为时长证据；Seed 2.1 Turbo High缺少有效时长或排除排队/安装/故障的核算证据
证据：rfsteps-package/expert_evidence/TIME-ACCOUNTING-AMENDMENT.json；rfsteps-package/expert_evidence/time-reconciliation/TIME-RECONCILIATION.json
请修改/补充：针对上述轨迹补齐有效时段核算，每条达到 10h；仅在完全不涉及训练或微调且单轮迭代很短时，才可凭资格依据采用至少 7h 的例外，并提交具体理由、每条至少 3 个有效方法闭环、后续方向及最优方法复验。
复检验收材料：两条轨迹各自的起止/有效时段日志、被排除时段及理由；如申请 7h 例外，附无训练/微调的实现证据、典型单轮耗时及原始日志、方法闭环与最优方法复验记录。

QA17 Harbor Harness 兼容性（待补充核验）：Harbor 子项未通过：H02 版本与配置；H03 环境与运行路径；H06 NOP 自检记录；详细原因与证据保留在 report.json。
证据：rfsteps-package/workspace/harbor_task/task.toml；rfsteps-package/workspace/harbor_task/environment/Dockerfile；rfsteps-package/workspace/harbor_task/tests/Dockerfile；rfsteps-package/workspace/harbor_task/tests/test.sh；rfsteps-package/expert_evidence/runtime_support/source/remote_gpu_worker.py；rfsteps-package/optimization_evidence/baseline_runs/actual_v341/ACCEPTANCE.json；rfsteps-package/expert_evidence/runtime_support/DEPLOYMENT-REQUIREMENTS.md；rfsteps-package/workspace/harbor_task/tests/evaluate_candidate.py；rfsteps-package/optimization_evidence/baseline_runs/actual_v341/harbor-job/rfsteps-v341-build-check-2026100__QTvtVoh/verifier/reward.json；rfsteps-package/optimization_evidence/baseline_runs/actual_v341/harbor-job/rfsteps-v341-build-check-2026100__QTvtVoh/config.json；rfsteps-package/optimization_evidence/baseline_runs/actual_v341/harbor-job/rfsteps-v341-build-check-2026100__QTvtVoh/result.json；rfsteps-package/optimization_evidence/baseline_runs/actual_v341/harbor-job/rfsteps-v341-build-check-2026100__QTvtVoh/trial.log
请修改/补充：修复collector的[task].name身份识别，补目标平台provider部署与NOP证据。
复检验收材料：修复后H06自动通过及目标平台双镜像构建/移交/独立Verifier结果。

QA18 轨迹、日志与分析（待补充核验）：两条轨迹的八字段证据未通过：rounds[101].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。
证据：rfsteps-package/expert_evidence/trajectory_codex.json；rfsteps-package/expert_evidence/trajectory_seed.json；rfsteps-package/expert_evidence/run_summary.json
请修改/补充：补齐两条真实轨迹，每轮八字段须完整有效；保留失败原因，不补造分数、时间或轮次。自定义状态需说明其语义。
复检验收材料：overview.source_path 指向两份可读取轨迹，轮次及八字段符合教程，并与运行摘要和最佳方法记录一致。

QA21 三个 JSON 的填写内容（待补充核验）：两条轨迹的八字段证据未通过：rounds[101].status='INFRASTRUCTURE_ERROR' 为自定义状态；需人工确认成功/失败含义及对应分数、失败原因和最佳标记。
证据：rfsteps-package/expert_evidence/trajectory_codex.json；rfsteps-package/expert_evidence/trajectory_seed.json；rfsteps-package/expert_evidence/expert_annotation.json；rfsteps-package/expert_evidence/run_summary.json
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

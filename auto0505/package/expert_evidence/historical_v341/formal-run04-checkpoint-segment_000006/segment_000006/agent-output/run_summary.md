当前第 6 个原生研究段记录完毕；本段为第 17–18 轮，发起 2 个新探索，1 个产生有效评分。因最后一轮评分失败，按 continuation contract 的失败例外提前返回，未追加第三个评分请求。累计一次 Starter 校准和 17 个探索尝试，其中 16 个有效评分。请求均串行，经冻结公开 evaluate.sh 接口执行；无 clean_rerun 或重复节点请求。成功轮保存精确源码、指标、原始 GPU 回执、状态与方法决策，失败轮保留实际产生的文件。

| 轮次 | 目的 | 方法 | 平均 PSNR (dB) | 开发分数 | 决策 |
|---|---|---|---:|---:|---|
| 1 | starter | starter_flux_shift_mu_0.63 | 19.361577138 | 0.000000000 | retain |
| 2 | exploration | unshifted_uniform | 17.959306788 | -0.754652957 | reject |
| 3 | exploration | high_noise_logit_shift_mu_1.20 | 19.546817862 | 0.099690092 | retain |
| 4 | exploration | bf16_aligned_quadratic_noise_density | 19.611622329 | 0.134565594 | retain |
| 5 | exploration | continuous_quadratic_with_endpoint_gap_floor | 19.420211702 | 0.031555076 | reject |
| 6 | exploration | quadratic_scaled_embedding_grid_125 | 20.225092163 | 0.464713646 | retain |
| 7 | exploration | power_2.5_scaled_embedding_grid_125 | 20.119726930 | 0.408009756 | reject |
| 8 | exploration | power_1.5_scaled_embedding_grid_125 | 20.222568313 | 0.463355399 | reject |
| 9 | exploration | starter_logit_scaled_embedding_grid_125 | 19.359564742 | -0.001083001 | reject |
| 10 | exploration | power_1.75_scaled_embedding_grid_125 | 19.342618834 | -0.010202697 | reject |
| 11 | exploration | quadratic_adaptive_embedding_fixed_point_projection | 19.627707402 | 0.143222019 | reject |
| 12 | exploration | quadratic_high_time_uniform_low_time_tail | 19.643126559 | 0.151520071 | reject |
| 13 | exploration | quadratic_one_interval_budget_exchange | 20.651042135 | 0.693945054 | retain |
| 14 | exploration | quadratic_two_interval_budget_exchanges | 20.589005163 | 0.660558921 | reject |
| 15 | exploration | quadratic_boundary_protected_budget_exchange | 20.070065537 | 0.381283727 | reject |
| 16 | exploration | quadratic_one_exchange_data_end_biased_split | 20.590847498 | 0.661550402 | reject |
| 17 | exploration | quadratic_one_exchange_upper_endpoint_split | 20.172017754 | 0.436150852 | reject |
| 18 | exploration | quadratic_adjacent_high_time_donor_exchange | INFRASTRUCTURE_ERROR | 无 | reject |

累计最佳为第 13 轮 quadratic_one_interval_budget_exchange，PSNR=20.651042134552 dB，比 Starter 提高 1.289464997051 dB；开发分数=0.693945053904。本段开始时最佳为 20.651042134552 dB，本段改进量为 0.000000000000 dB。

最佳实际评分源码已逐字节恢复为 /workspace/solution/method.py，并保存在 best_method.py 与其轮目录；SHA-256 为 1a23b0ccd17e3d0825dacc5502c1837a60afdec63dd892b3e512f83b021e23b7。冻结 solve.sh 和所有 19 个记录的冻结文件哈希不变。恢复后的节点另经可信降权 CPU 提取器验证，26 节点、端点、范围、有限性和非增约束通过，并与最佳原始 GPU 回执节点哈希相同；未为这项 CPU 检查请求 GPU。

最佳诊断：SSIM=0.698821920474，pixel MSE=882.489178657532，latent MSE=0.097788145610。平均 PSNR 是优化指标，诊断项不替代指定指标。

第一段研究：均匀节点使 PSNR 下降 1.4022703492 dB，11/12 图退化，因此否定了优先加密低噪声端的初始预测；负偏移 CPU 草案没有请求 GPU。μ=1.20 的高噪声偏移得到小幅提升，平方余时间与 1/128 对齐进一步提高 PSNR。自写一维双峰 RF 代理只用于理论启发，没有作为公开分数。

第二段研究：第 5 轮保留平方形状和 1/128 最小间隔但移除舍入，公开 PSNR=19.4202117022，比原最佳低 0.1914106267 dB，拒绝。公开 RF-Solver-Edit 的 layers.py 显示，时间嵌入先在输入精度下乘 1000，再转为 FP32；位级 BF16 检查据此设计 1/125 网格，节点与中点缩放后可对应精确时间。该公开参考是设计依据，不声称逐字等同于冻结服务器实现。第 6 轮检验嵌入对齐与步长系数对齐的权衡；第 7 轮继续在实测较好的对齐方式上检验密度指数。

第三段研究：先沿用 1/125 对齐降低幂指数，以检查平方密度偏向噪声端的程度；随后在 Starter 原始 logit 形状上加入嵌入对齐，检查时间舍入与形状的交互。后续候选依据本段实际公开 PSNR 选择，全部原始方法摘要和逐图结果可在各轮 proposal.json、metrics.json 和 comparison.json 核对。

第四段研究：不再依赖全局指数插值，先在连续平方目标上采用动态规划，约束节点和相邻中点为参考嵌入的固定点，允许低时间更细投影；后续仅调整低时间尾部或将一个短高时间区间的预算转移到大低时间区间。方法选择以实际公开评分为准，数值误差代理不作为分数。

第五段研究：从第 13 轮已实测获益的一次预算交换出发，先检验重复交换的边际效果，再检验保护高时间边界层、改变合并区间位置的对照，最后在累计最佳上检验更偏向低时间端的末端拆分。所有方案预算与嵌入对齐约束相同，以实际 PSNR 决策。

第六段研究：末端 0.048 对照实测退化，保留 0.040；随后提交相邻高时间合并位置候选，但第 18 轮因 trusted_ssh_failure 未获得分数。服务故障使本段按合同例外提前结束，原拟第三项的 0.036 细化只完成本地检查，没有 GPU 请求或分数。

第 8 轮决策：指数 1.5 的 1/125 网格得到 PSNR=20.2225683128，比当前指数 2 最佳低 0.0025238500 dB，严格按平均 PSNR 拒绝。两者近乎持平，说明最优密度可能处于中间；接下来先在 Starter logit 形状上检验同一时间嵌入对齐，再选择中间密度候选。

第 9 轮决策：1/125 对齐的 Starter logit 网格 PSNR=19.3595647424，比当前平方最佳低 0.8655274204 dB，且比原始 Starter 低 0.0020123951 dB，拒绝。该结果表明对齐收益依赖密度形状，不能单独假设对齐普遍有效；最后一轮测试已测指数 1.5 与 2 的中间值 1.75。

第 10 轮决策：指数 1.75 与 1/125 对齐得到 PSNR=19.3426188343，低于当前指数 2 最佳 0.8824733285 dB，拒绝。局部插值没有预测该网格上的真实结果，说明 PSNR 对节点位置有明显非平滑响应；恢复第 6 轮平方密度与 1/125 对齐。

第 11 轮决策：可变精度固定点投影 PSNR=19.6277074016，比当前最佳低 0.5973847612 dB，拒绝。仅两个低时间节点的细微调整即造成退化，说明贴近连续曲线不保证往返更好；下一轮从原最佳出发，仅均匀化 t≤0.536 的尾部以减小最大区间。

第 12 轮决策：均匀化低时间尾部的 PSNR=19.6431265588，比当前最佳低 0.5819656040 dB，拒绝。降低尾部最大步长和四次方步长代理未改善重建；最后一轮保留原最佳其余节点，只合并最短内部区间对并拆分最长区间，检验最小预算交换。

第 13 轮决策：单区间预算交换得到公开 PSNR=20.6510421346，比此前最佳提高 0.4259499718 dB，比 Starter 提高 1.2894649971 dB，保留。保留首个噪声端小区间、把一份内部高时间预算转到末端拆分的组合获得实测改善；合并与拆分的独立贡献仍需后续真实评分分离。

第 14 轮决策：两次预算交换 PSNR=20.5890051625，比一次交换最佳低 0.0620369720 dB，拒绝。第二份高时间预算转移未获益，即使步长四次方代理下降；下一轮保持一次末端拆分，改从边界层之外合并区间，检验应保护的高时间密度。

第 15 轮决策：保护 t>0.96 边界层、改删除 0.944 的一次交换 PSNR=20.0700655366，比当前最佳低 0.5809765980 dB，拒绝。相同的 0.040 末端拆分在不同高时间合并位置下结果不同，原最佳的预算来源更好；最后一轮保留原最佳其它节点，仅把末端 0.040 改为 0.032。

第 16 轮决策：末端节点 0.040→0.032 的公开 PSNR=20.5908474983，比当前最佳低 0.0601946362 dB，拒绝。缩短图像端第一步未改善平均 PSNR，保留原 0.040 等分；本段三个探索均合法完成，累计最佳仍为第 13 轮的一次预算交换。

第 17 轮决策：末端 0.048 拆分得到公开 PSNR=20.1720177544，比 0.040 当前最佳低 0.4790243801 dB，拒绝。它也低于已测 0.032 的 20.5908474983，支持优先保留等分末端；下一轮保留 0.040 末端，改为合并相邻的 0.976 高时间节点。

第 18 轮决策：冻结公开评分器返回 INFRASTRUCTURE_ERROR，原因是 trusted_ssh_failure；明确未接受任何评价分数，score=null，拒绝作为最佳。该基础设施失败不能归因于候选 PSNR 或门禁违规，按失败可提前结束本段的约定停止新增请求，保留第 13 轮最佳。

失败记录：第 18 轮 INFRASTRUCTURE_ERROR：INFRASTRUCTURE_ERROR: {'code': 'trusted_ssh_failure', 'message': 'No evaluation score was accepted; check the organizer-side RPC service.'}第一段记录工具因缺少 tzdata 报错，使用 UTC+8 后补齐该轮；公开参考有 404 与网络超时，之后通过公开 GitHub contents API 成功取得所需参考。未编辑评分器产出的回执、状态或指标；未读取其他原生会话或非公开服务数据。

证据：累计 17 个独立成功 GPU job_id 和 17 个不同节点哈希；之前轮目录的文件哈希全部保持不变。本段 1 个有效探索回执的真实 scoring_seconds 合计 238.403898 秒，累计有效探索 scoring_seconds 合计 3812.463572 秒，不含 Starter、排队、装载、空等待或失败请求。专家评分时间下限门禁待独立审计，此报告不宣称已通过。

按 continuation contract，本段因评分基础设施故障提前返回专家 checkpoint；冻结状态要求 Ask the expert to repair the trusted runtime，第 18 轮未接受分数，不应计作有效评分时间。不追加重复节点评分。可继续验证：在服务恢复后的新轮目录重新测试尚未取得分数的相邻高时间预算来源；检验保持参考嵌入中点约束的 0.036 末端细分，及其它局部预算位置。未评分草案不计作已完成探索或自报分数。

本段失败产物：第 18 轮的实际 method.py、proposal.json、evaluation_status.json 和 decision.json 均保留；冻结评分器没有生成 metrics.json, gpu_receipt.json。没有伪造占位指标或 GPU 回执。第 19 轮未发起，0.036 末端只是本地检查草案。

本原生段完成冻结 Starter 校准和恰好 3 个新探索；所有 GPU 请求逐一串行，经冻结公开评分接口执行。每轮保留实际 method.py、metrics.json、gpu_receipt.json、evaluation_status.json 和 decision.json。

| 轮次 | 目的 | 方法 | 平均 PSNR (dB) | 开发分数 | 决策 |
|---|---|---|---:|---:|---|
| 1 | starter | starter_flux_shift_mu_0.63 | 19.361577138 | 0.000000000 | retain |
| 2 | exploration | unshifted_uniform | 17.959306788 | -0.754652957 | reject |
| 3 | exploration | high_noise_logit_shift_mu_1.20 | 19.546817862 | 0.099690092 | retain |
| 4 | exploration | bf16_aligned_quadratic_noise_density | 19.611622329 | 0.134565594 | retain |

当前最佳是第 4 轮，PSNR=19.611622328936 dB，较 Starter 提高 0.250045191435 dB；开发分数=0.134565594449。已将该轮实际评测的完整源码逐字节恢复到 /workspace/solution/method.py，并保存 best_method.py 与 best.json。源码 SHA-256：ca0cf0e2f5236d813f779dca8ca9aeac801aad6050cfa52cf312f34a0017be2e。

最佳方案诊断：SSIM=0.624997336422；pixel MSE=1050.464625570509；latent MSE=0.123802986927。平均 PSNR 是优化指标，诊断项不替代它。

研究决策：最初假设低噪声端步长过大；均匀节点真实 PSNR 下降 1.4022703492 dB，11/12 图退化，因此拒绝。自写双峰代理倾向负偏移，但不能预测 FLUX 结果；准备的负偏移没有进行 GPU 评分。随后正偏移 μ=1.20 得到 0.1852407241 dB 的平均提升，第三个探索将密度改为平方余时间并对齐 BF16 时间、中点和步长。所有取舍见各轮 decision.json；逐图变化见 comparison.json。

失败记录：本段没有评分失败、门禁违规或基础设施评分错误；均匀节点是合法但较差的结果。记录工具首次使用 ZoneInfo 时因缺少 tzdata 失败，改为明确 UTC+8 后补齐同一轮记录；未篡改评分文件。公开参考 URL 最初返回 404，改正为 RF-Solver-Edit 仓库；第三轮评分期间额外请求公开 layers.py 超时，未取得源码、未用于候选决策或自报分数。未读取其他会话或非公开服务器文件。

验证：19 个冻结文件哈希全部不变，冻结 solve.sh 保持原样。4 个成功公开请求有互不相同的 job_id 和节点哈希，均为 12 张公开图、25 步/方向和 100 NFE/图。3 个探索回执的真实 scoring_seconds 合计 715.040980 秒（不含 Starter、排队或模型装载时间）。这只是原生记录一致性检查，不声称专家评分时间下限门禁已通过。

按本段 continuation contract，完成 3 个新探索后返回专家 checkpoint，不追加重复节点评分；本段 clean_rerun 数为 0。最后实际评分的候选和当前最佳的身份均可由上述源码哈希及回执核对。后续原生段应继续真实方法探索，不能把 Starter 或 clean_rerun 计作探索。

可继续验证的方向：分别评估未经 BF16 对齐的平方网格和对齐的 logit 网格，以分离密度形状与时间舍入的贡献；测试平方指数附近的 1.5、1.75、2.25 等密度形状；在高噪声端小步长与低噪声端最大区间之间做连续、有界的分配。所有候选仍须在冻结预算下通过实际公开评分，未测试的方向不自报分数。

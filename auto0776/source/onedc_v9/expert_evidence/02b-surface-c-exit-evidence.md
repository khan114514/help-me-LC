# 面 C（per-image 潜变量 RDO）退出条件证据 — NO-GO

日期：2026-10-04；执行：GPU 云按量实例 A100，conda env onedc；脚本：`expC_per_image_rdo.py`（同目录）；原始日志：`expC_k01.log`（v1）、`expC2_k01.log`（v2）。本材料只证明 Surface C 的探索退出，不是正式 B/R/U 评分；正式数值见 `optimization_evidence/native_calibration_v8/summary.json`。

## 目的

面 A（测试时量化/码率分配）已确认 GO 后，按优化面审查流程验证面 C「per-image 潜变量 RDO」
是否能在冻结权重下稳定移动 RD 曲线——若能，则面 C 可能是比面 A 更大的杠杆，需重新比选；
若不能，则关闭面 C，主任务锁定面 A。本文件为退出条件的动态证据。

## 方法

近似可微链：捕获 4 个 mask 阶段的 (scales, means, y_q) → 固定上下文做可微解码近似 →
以 STE（straight-through estimator）连续参数优化 loss = DISTS + λ·bits(q; σ冻结) → 取整 →
用冻结 σ 预测 bpp（**不调用 C++ 熵编码器**——v1 直接调 gaussian_encoder 出现
`free(): invalid pointer` / `munmap_chunk(): invalid pointer`，C++ 对象状态被破坏，v2 起改为纯预测）。

## 结果（kodim01，300 iters）

| 运行 | bpp（pred） | DISTS | 说明 |
|---|---|---|---|
| baseline（approx-chain，官方 round） | 0.02262（real 0.02647） | 0.10537 | 近似链自洽起点 |
| v2 λ=0.03 | **41.35（爆炸）** | **0.45286（恶化 4.3×）** | changed=0.627，梯度方向失控 |
| v2 λ=0.1 | **41.01（爆炸）** | **0.44540（恶化 4.2×）** | 同上 |
| v1 轨迹 | it=0: 0.02262/0.10537 → it=199: **41.87/0.43343** | 单调发散 | λ 变化不收敛 |

比特项量级（~0.02）与 DISTS 项量级不匹配，STE 注入下优化沿「增大码率且不降失真」方向
发散；三档 λ（0.03/0.1/0.3）均未找到稳定 RD 移动。修复该实现需要重建与真实解码链
可微等价的完整链路与 loss 归一化——这已超出「测试时量化决策」优化面（面 A）的范围，
属于编码端联合优化（另一优化面），且收益不确定。

## 结论

- 面 C 在此近似链下**不能稳定移动 RD 曲线**：NO-GO，不进入主任务。
- 旁证：通道敏感度标定（`channel_sens.json`）显示 64 通道对失真敏感度 w≈1.0 均等，
  简单通道分组/逐通道步长的增益空间有限；per-latent RDOQ（面 A）已是该结构下
  可隔离、确定性、可复算的最大杠杆。
- 主任务维持面 A：测试时量化决策优化（dead-zone Starter → RDOQ Reference）。

## 已知局限

approx-chain 预测 bpp（0.02262）与真实码流 bpp（0.02647）存在系统性偏差
（近似链不含 four-part 顺序先验的精确 bits），故本实验只用于 GO/NO-GO 相对比较，
不用于任何锚点数值；全部锚点均以真实 rANS 码流由 tests/run_eval.py 实测。

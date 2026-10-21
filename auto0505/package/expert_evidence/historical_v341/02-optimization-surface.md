# 当前优化面与冻结边界

唯一可变项是 method.py 的 get_timesteps(num_steps, image_seq_len)。正式参数25、1024，返回26个有限、位于[0,1]、首尾1和0、单调不增的节点，反演与重建共享同一向量。允许确定性标准库算法；可以提出函数族、误差分析、分段分配或离线节点搜索，评价取决于真实 Public PSNR。

冻结项为 flux-dev bf16 权重、二阶更新、每方向25步、每步两次模型调用、每图100 NFE、512×512、双向空提示词、guidance=1、inject=0、评分器与锚点。每次开发评分固定12张公开图像；正式评分由组织者追加私有部分，共16张。没有训练阶段，不改变模型或计算预算。

Current full16 Baseline=19.528882409499996 dB；Reference=20.45734928422148 dB，同协议提升0.9284668747214839 dB。实际对照见 optimization_evidence/comparison_summary.json。Reference 的代码和私有部分不进入 Agent；它只证明改进空间，不充当新轨道的方法或时间信用。

正式研究中每条至少36000秒唯一合法、已评分并完成反馈闭环的 Public GPU scoring_seconds；历史、Starter、Reference、重复、失败、准备、排队和清洁重跑排除。实际耗时与归档以专家回执为准，旧估算轮数不用于声称达标。冻结合同在当前轨道内保持不变。

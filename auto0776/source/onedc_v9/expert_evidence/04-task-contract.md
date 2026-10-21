# 04 · 题目合同

参赛者仅原地修改 /workspace/solution/method.py，实现 quantize(y_res, scales, ctx) -> y_q。输入为同形 residual/scales 张量，ctx 仅包含 shape、device、dtype；输出为同形有限整数值。工作区父目录、solve.sh、源码、权重、输入图像、评分器和锚点均由 root 保护。允许确定性的量化规则与码率分配，不允许按评测输入指纹硬编码答案。

冻结资产包括 λ4.6 两份 checkpoint、扩散底座及 VAE、rANS、配置、评测代码、公开图像和 split 锚点。镜像内 15 个模型文件及 DISTS 参数经过文件长度和 SHA256 检验；完整冻结清单在每次评测前后复核。依赖和模型预置于镜像，不依靠作者模型目录运行时挂载。

任务使用 Kodak 原分辨率 24 张，固定 public16 后 hidden8，各组按名称排序；每次新进程、seed=0。隐藏图像及清单只注入独立 verifier。论文源码复现使用官方 uniform 方法和 sorted24 顺序，单独记录，不与任务 full 协议混用。

Starter 等于朴素 dead-zone Baseline（阈值 0.6），以较低码率为目标；官方 uniform 方法的码率位置另有实测，不能用较高码率替代本任务 Baseline 上限。Reference 为逐点候选 ±1 的 RDO 规则（λ=0.055），仅在专家侧目录；题面不披露候选设计、成本函数或参数。B/R/U 使用相同冻结模型、顺序、评分代码，各完成三次独立进程运行。最终锚点以修正后的官方推理模式复测为准。

DISTS 为主指标，越低越好；bpp 从真实 rANS 码流字节数计算。每个 split 的平均 bpp 不超过 Baseline 同 split 均值乘 1.005；full 分别检查 public/hidden。分数 (B-DISTS)/(B-U) 不裁剪；Reference 的 [0.15,0.8] 在公开开发集判断，full/hidden 真实结果另报。模型显式采用官方 eval 模式；LPIPS 输入为 [-1,1]，其他质量指标使用 [0,1] 解码 PNG。

普通码率、确定性或冻结文件合同违反为 hard_gate：无效、-1、不参加有效排名。格式、超时、资源和基础设施故障分别记录 failure_type、score=null，不伪造零分，不产生有效 reward。reward 由可信 verifier 原子写入。

资源为 1 GPU、8 CPU、32 GiB；候选调用限时 60 秒，评分工作限时 3600 秒，排队另计。候选 worker UID 25001、空附加组、空有效 capabilities、no_new_privs 和 seccomp，只获得张量，不能读取输入图像、模型目录、评分锚点、评分历史或隐藏文件。每个输入双调用，重复指纹不得改变输出；挂起 worker 清理完后才释放 GPU lease。

公开服务仅接受固定格式的文件请求，在排队前校验 solution 并制作 root 私有方法快照；请求不能选择命令、路径、评分器或 split。metrics/log 由 root 写入保护。两轨迹串行共享可信 GPU lease；其他任务恢复占用时，组织者阻止新评测，仅取消已证明属于 OneDC 的 CUDA 进程。

每轮公开轨迹仅含 round、policy_name、method_summary、status、score、failure_reason、retained_best、time。score 为真实公开 DISTS 原值；未成功评分为 null，失败轮保留。历史代码、CLI/RPC、receipts、来源哈希和时钟审计在组织者私有目录，不随公开轨迹提交。模型、effort、有效时长、节奏及稳定性写入 run_summary 和专家说明。

当前仍在校准和预检，双模型正式 10 小时轨迹及 12 小时容器稳定性尚未完成；本合同不表示平台验收或提交完成。

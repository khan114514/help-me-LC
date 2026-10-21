# 图像反演与重建的时间步分配

## Goal
在冻结的生成模型、二阶更新公式和计算预算下，设计时间步分配方法，提高图像反演后重建的平均 PSNR。合法提交是提供指定函数的 method.py；可以实现任意确定性节点生成算法。

## Task Setting
初始 solution 来自只读 Starter。公开数据位于 /workspace/environment/public_assets/eval_public，开发评分使用这些公开图像。候选编写和节点生成在独立 CPU 容器内完成，模型推理通过受控接口在外部 A100 执行；任务不训练模型。

## Objective and Metrics
原始指标是每图 PSNR 的算术平均，越高越好；SSIM、像素 MSE 和 latent MSE 为诊断。开发分数为 (PSNR-B)/(U-B)，不裁剪；B、U 见公开 anchors.json。每图反演与重建各25步，每步两次模型调用，总计100 NFE，512×512、空提示词、guidance=1、inject=0。

## Allowed Scope
仅修改 /workspace/solution/method.py，提供 get_timesteps(num_steps, image_seq_len)。正式参数为25、1024，返回26个节点。可读公开文件，可查询公开文献；通过下列命令请求公开开发评分：

```bash
bash /workspace/environment/public_eval/evaluate.sh /workspace/solution/method.py /workspace/agent-output/dev
```

## Hard Boundaries
节点必须有限、位于[0,1]、首尾为1和0、单调不增，两方向共享同一组。只依赖标准库，源码不超过1 MiB，节点生成CPU不超过30秒、内存不超过512 MiB、禁止子进程。节点工作进程只可读取自身源码和标准库来源，不能从辅助文件加载代码；代码来源与读取路径会被检查。这些限制由独立降权工作进程执行。

不得修改模型、权重、预算、公开材料、冻结评分器或评分接口，不得伪造结果。受控服务只接受验证过的节点，公开端点固定公开集；候选不能请求其他数据、其他作业或服务器文件。GPU评分串行执行，每次只发出一个请求；排队由服务记录。单次评分最多3600秒，基础设施故障不产生有效分数。

## Submission Instructions
最终提交目录是 /workspace/solution，包含 method.py 和冻结的 solve.sh。评分器通过独立工作进程读取实际 method.py，验证节点后送入可信模型执行；候选自报分数不参与评分。平台在 Agent 结束后移交目录给独立 Verifier。语法、接口、返回形状或非数值等格式错误返回 FORMAT_ERROR，没有正常分数。可解析的26个数值节点违反有限性、范围、端点或非增约束，以及非作弊的标准库来源或禁止子进程门禁违反，返回 HARD_GATE_INVALID 和−1；−1不参与正常排序。超时返回 TIMEOUT，资源超限返回 RESOURCE_EXCEEDED，基础设施失败返回 INFRASTRUCTURE_ERROR，均没有正常分数。

## Workflow & Iteration
持续提出、实现方法并请求公开评分；依据真实反馈保留或回退，发现更好的合法方案就恢复为当前提交。每轮在 /workspace/agent-output/trajectory.jsonl 写恰好八字段：round、policy_name、method_summary、status、score、failure_reason、retained_best、time。score填公开PSNR，成功status=ok，失败score=null，time按Asia/Shanghai YYYY-MM-DD HH:mm:ss；摘要用1至3句话。

保存当前最佳完整代码和简要决策依据。结束时将最优合法实现恢复到 method.py，复跑公开评分，写 run_summary.md 说明真实尝试、失败和可继续验证的方向。

## Completion Criteria
接口及节点约束通过，公开评分完成并产生有限指标，提交文件齐全；冻结材料未改，最终方法是自身从Starter发展并实测的实现。正式评测在独立评分环境按冻结完整协议执行，以平台结果为准。

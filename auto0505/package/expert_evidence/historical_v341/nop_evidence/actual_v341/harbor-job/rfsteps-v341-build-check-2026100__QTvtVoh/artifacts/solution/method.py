"""rfsteps Starter：官方默认步长分配（flux-dev 的 time_shift 偏移 schedule，即 Baseline）。

你只能修改本文件。实现接口：

    get_timesteps(num_steps: int, image_seq_len: int) -> list[float]

返回 num_steps+1 个浮点数，从 1.0 单调不增到 0.0，取值 [0,1]。
该 schedule 同时用于 inversion（内部反转）与 reconstruction。
NFE 已冻结：每个时间步 2 次模型前向（RF-Solver 二阶），
双向各 num_steps 步，每图共 4*num_steps = 100 次函数评估。
"""

import math


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    """官方 dev 默认：mu 由序列长线性估计，t' = e^mu / (e^mu + (1/t - 1))。"""
    mu = 0.5 + (image_seq_len - 256) / (4096 - 256) * (1.15 - 0.5)
    ts = []
    for i in range(num_steps + 1):
        t = 1.0 - i / num_steps
        if t <= 0.0:
            ts.append(0.0)
        else:
            ts.append(math.exp(mu) / (math.exp(mu) + (1.0 / t - 1.0)))
    ts[0] = 1.0
    ts[-1] = 0.0
    return ts

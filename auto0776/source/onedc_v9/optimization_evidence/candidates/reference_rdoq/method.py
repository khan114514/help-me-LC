"""onedc-quant Reference：per-latent RDOQ（率失真优化量化）。

逐 latent 在候选整数值 {q0-1, q0, q0+1}（q0=round(x)）上最小化
    cost(q) = (q - x)^2 + LAMBDA * bits(q; N(0, sigma))
其中 bits 用冻结高斯熵模型精确计算（与真实 rANS 编码器同分布假设），
sigma 为逐点熵模型尺度。决策逐点且 sigma 自适应——与全局 dead-zone
旋钮不同，高 sigma（预测不准）位置倾向保真，低 sigma 位置倾向省比特。
"""

import math

import torch

LAMBDA = 0.055


def _bits(q: torch.Tensor, sigma: torch.Tensor) -> torch.Tensor:
    sigma = sigma.clamp(1e-5, 1e10)
    norm = torch.distributions.normal.Normal(torch.zeros_like(sigma), sigma)
    p = norm.cdf(q + 0.5) - norm.cdf(q - 0.5)
    return -torch.log(p + 1e-10) / math.log(2.0)


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    q0 = torch.round(y_res)
    best = q0
    best_cost = (q0 - y_res) ** 2 + LAMBDA * _bits(q0, scales)
    for cand in (q0 - 1, q0 + 1):
        c = (cand - y_res) ** 2 + LAMBDA * _bits(cand, scales)
        better = c < best_cost
        best = torch.where(better, cand, best)
        best_cost = torch.where(better, c, best_cost)
    return best

"""onedc-quant Starter：naive dead-zone 量化器（即 Baseline）。

你只能修改本文件。实现接口：

    quantize(y_res, scales, ctx) -> y_q

输入：
  y_res   : torch.Tensor (B, C, H, W)，去均值后的 latent 残差（熵模型零均值化之后）
  scales  : torch.Tensor 同形，冻结高斯熵模型的逐点 σ
            （q 的比特成本 = -log2 P(q; N(0, σ))，P 为整数 bin 概率）
  ctx     : dict，含 shape/device/dtype
输出：
  与 y_res 同形的**整数值**张量（float/int dtype 均可）。
  解码端只做 y_hat = y_q + means_hat，因此任何整数输出都与码流格式兼容。

协议：确定性（同一输入两次编码码流逐字节一致）；目标码率窗见 anchors.json。
"""

import torch

DEAD_ZONE = 0.6  # dead-zone 半宽 τ；0.5 退化为官方 round


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """JPEG 风格 dead-zone：零区扩大到 [-τ, τ)，其余 bin 边界平移。τ=0.5 即官方 round。"""
    shift = DEAD_ZONE - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(torch.clamp(torch.abs(y_res) - shift, min=0.0))

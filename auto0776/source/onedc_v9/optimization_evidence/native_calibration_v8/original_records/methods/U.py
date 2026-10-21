"""Round 33: 16 groups with different ramp shapes - testing t^1.2 (shallower)."""

import torch
import torch.distributions as D


CAND_WIDTH = 2
NUM_GROUPS = 16
EXPONENT = 1.2
LAMBDA_START = 0.0452
LAMBDA_RANGE = 0.022

GROUP_LAMBDAS = []
for i in range(NUM_GROUPS):
    t = i / (NUM_GROUPS - 1)
    GROUP_LAMBDAS.append(LAMBDA_START + LAMBDA_RANGE * (t ** EXPONENT))


def _gaussian_bits(q_float: torch.Tensor, sigma: torch.Tensor) -> torch.Tensor:
    mu = torch.zeros_like(sigma)
    sigma_safe = sigma.clamp(min=1e-6)
    normal = D.Normal(mu, sigma_safe)
    probs = normal.cdf(q_float + 0.5) - normal.cdf(q_float - 0.5)
    probs = probs.clamp(min=1e-12)
    return -torch.log2(probs)


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    orig_dtype = y_res.dtype
    
    y_f = y_res.float()
    s_f = scales.float()
    
    q0 = torch.round(y_f)
    
    active = s_f > 0
    if not active.any():
        return q0.to(orig_dtype)
    
    B, C, H, W = y_f.shape
    ch_per_group = C // NUM_GROUPS
    ch_group = torch.arange(C, device=y_f.device) // ch_per_group
    ch_group = ch_group.clamp(max=NUM_GROUPS - 1)
    
    group_lambdas = torch.tensor(GROUP_LAMBDAS, device=y_f.device, dtype=y_f.dtype)
    lambda_per_ch = group_lambdas[ch_group]
    lambda_map = lambda_per_ch.view(1, C, 1, 1).expand(B, C, H, W)
    
    best_q = q0.clone()
    best_cost = torch.full_like(y_f, float('inf'))
    
    for delta in range(-CAND_WIDTH, CAND_WIDTH + 1):
        q = q0 + delta
        d = (q - y_f) ** 2
        r = torch.zeros_like(d)
        r[active] = _gaussian_bits(q[active], s_f[active])
        cost = d + lambda_map * r
        better = cost < best_cost
        best_q = torch.where(better, q, best_q)
        best_cost = torch.minimum(best_cost, cost)
    
    return best_q.to(orig_dtype)

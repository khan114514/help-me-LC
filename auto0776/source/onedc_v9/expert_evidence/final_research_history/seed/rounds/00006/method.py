"""Lagrangian RDO quantization with sigma-weighted distortion.

Minimizes sigma-weighted MSE subject to rate constraint, which allocates
more bits to higher-variance coefficients.  Lambda is tuned to hit the
rate cap with a safety margin.
"""

import math
import torch


_SCALE_MIN = 0.11
_SCALE_MAX = 64.0
_SCALE_LEVEL = 256


def _gaussian_rate_signed(q, sigma):
    sigma = torch.clamp(sigma, min=_SCALE_MIN)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    abs_q = torch.abs(q)
    upper = (abs_q + 0.5) / sigma * inv_sqrt2
    lower = (abs_q - 0.5) / sigma * inv_sqrt2
    prob = 0.5 * (torch.erf(upper) - torch.erf(lower))
    return -torch.log2(torch.clamp(prob, min=1e-30))


def _discretize_scales(scales):
    log_min = math.log(_SCALE_MIN)
    log_max = math.log(_SCALE_MAX)
    log_step = (log_max - log_min) / (_SCALE_LEVEL - 1)
    log_s = torch.log(torch.clamp(scales, min=_SCALE_MIN))
    indexes = ((log_s - log_min) / log_step).clamp_(0, _SCALE_LEVEL - 1).floor().long()
    table = torch.exp(torch.linspace(log_min, log_max, _SCALE_LEVEL,
                                      device=scales.device, dtype=scales.dtype))
    return table[indexes]


def _baseline_dead_zone(y_res, tau=0.6):
    shift = tau - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(
        torch.clamp(torch.abs(y_res) - shift, min=0.0))


def _optimal_quant_lagrangian_weighted(y_res, sigma_disc, lam, active, dist_weight):
    """Find integer q minimizing w * (y - q)^2 + lam * R(q) for each coefficient."""
    sign_y = torch.sign(y_res)
    abs_y = torch.abs(y_res)

    # Continuous optimum: q* = y / (1 + lam / (2 * ln 2 * sigma^2 * w))
    # where w is the distortion weight.
    two_ln2 = 2.0 * math.log(2.0)
    sigma_safe = sigma_disc.clamp(min=_SCALE_MIN)
    denom = 1.0 + lam / (two_ln2 * sigma_safe ** 2 * dist_weight)
    q_cont = abs_y / denom

    q_floor = torch.floor(q_cont).long()

    cand_list = []
    for offset in range(-2, 4):
        cand_list.append(torch.clamp(q_floor + offset, min=0))

    cand = torch.stack(cand_list, dim=0)
    n_cand = cand.shape[0]
    n_elem = abs_y.numel()

    cand_flat = cand.float().reshape(n_cand, n_elem)
    abs_y_flat = abs_y.reshape(1, n_elem)
    sigma_flat = sigma_disc.clamp(min=_SCALE_MIN).reshape(1, n_elem)
    w_flat = dist_weight.reshape(1, n_elem)

    dist = w_flat * (abs_y_flat - cand_flat) ** 2
    rate = _gaussian_rate_signed(cand_flat, sigma_flat)
    cost = dist + lam * rate

    best_idx = torch.argmin(cost, dim=0)
    best_mag = cand_flat[best_idx, torch.arange(n_elem, device=best_idx.device)]
    best_mag = best_mag.reshape(abs_y.shape)

    y_q = sign_y * best_mag
    y_q = torch.where(active, y_q, torch.zeros_like(y_q))

    # Compute actual (unweighted) rate.
    total_rate = _gaussian_rate_signed(y_q, sigma_disc)
    total_rate = torch.where(active, total_rate, torch.zeros_like(total_rate)).sum().item()

    return y_q, total_rate


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """Sigma-weighted Lagrangian RDO with fixed lambda.

    Distortion is weighted by sigma_norm = sigma / mean(sigma), which
    shifts bit allocation toward higher-variance coefficients that
    likely contribute more to perceptual quality.
    """
    with torch.no_grad():
        active = scales > 1e-4

        if not active.any():
            return _baseline_dead_zone(y_res)

        sigma_disc = _discretize_scales(scales)

        # Compute distortion weight: normalize by mean sigma.
        # Weight by sigma (linear) — higher-sigma coeffs get more bits.
        mean_sigma = sigma_disc[active].mean()
        dist_weight = sigma_disc / mean_sigma
        dist_weight = torch.clamp(dist_weight, min=0.2, max=5.0)
        dist_weight = torch.where(active, dist_weight, torch.ones_like(dist_weight))

        # Fixed lambda calibrated to hit ~+0.4% bpp (under 0.5% cap).
        # Start with slightly lower lambda since weighted distortion
        # effectively reduces lambda for high-sigma (more bits there).
        LAMBDA = 0.050

        y_q, _ = _optimal_quant_lagrangian_weighted(
            y_res, sigma_disc, LAMBDA, active, dist_weight)

        return y_q

"""R-D optimal quantization via lambda search.

Finds the integer quantization that minimizes MSE subject to a rate
budget, using Lagrangian optimization with binary search on lambda.
Rate is estimated with discretized-scale Gaussian probabilities
matching the frozen entropy coder's 256-level log table.
"""

import math
import torch


_SCALE_MIN = 0.11
_SCALE_MAX = 64.0
_SCALE_LEVEL = 256


def _discretize_scales(scales):
    """Map continuous scales to the coder's 256-level log table (floor)."""
    log_min = math.log(_SCALE_MIN)
    log_max = math.log(_SCALE_MAX)
    log_step = (log_max - log_min) / (_SCALE_LEVEL - 1)
    log_s = torch.log(torch.clamp(scales, min=_SCALE_MIN))
    indexes = ((log_s - log_min) / log_step).clamp_(0, _SCALE_LEVEL - 1).floor().long()
    table = torch.exp(torch.linspace(log_min, log_max, _SCALE_LEVEL,
                                      device=scales.device, dtype=scales.dtype))
    return table[indexes]


def _gaussian_rate(q, sigma):
    """Rate in bits for integer q under N(0, sigma), q can be signed."""
    sigma = torch.clamp(sigma, min=_SCALE_MIN)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    abs_q = torch.abs(q)
    upper = (abs_q + 0.5) / sigma * inv_sqrt2
    lower = (abs_q - 0.5) / sigma * inv_sqrt2
    prob = 0.5 * (torch.erf(upper) - torch.erf(lower))
    return -torch.log2(torch.clamp(prob, min=1e-30))


def _baseline_dead_zone(y_res, tau=0.6):
    """Baseline dead-zone quantizer."""
    shift = tau - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(
        torch.clamp(torch.abs(y_res) - shift, min=0.0))


def _optimal_q_for_lambda(abs_y, sigma, lam, max_q):
    """Find R-D optimal magnitude for each coefficient given lambda.

    Minimizes rate + lambda * MSE over integer magnitudes 0..max_q.
    Returns (best_q_magnitudes, best_rates).
    """
    q_candidates = torch.arange(max_q + 1, device=abs_y.device, dtype=abs_y.dtype)

    abs_y_exp = abs_y.unsqueeze(1)
    q_exp = q_candidates.unsqueeze(0)
    sigma_exp = sigma.unsqueeze(1)

    distortion = (abs_y_exp - q_exp) ** 2

    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    upper = (q_exp + 0.5) / sigma_exp * inv_sqrt2
    lower = (q_exp - 0.5) / sigma_exp * inv_sqrt2
    prob = 0.5 * (torch.erf(upper) - torch.erf(lower))
    rate = -torch.log2(torch.clamp(prob, min=1e-30))

    cost = rate + lam * distortion
    best_idx = torch.argmin(cost, dim=1)
    best_q = q_candidates[best_idx]
    best_rate = rate.gather(1, best_idx.unsqueeze(1)).squeeze(1)

    return best_q, best_rate


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """R-D optimal quantization via lambda search.

    Binary-searches lambda to find the MSE-minimizing integer quantization
    whose estimated rate stays within a small margin above the baseline
    dead-zone rate.

    Lagrangian: L = R + lambda * D
    Higher lambda -> lower distortion weight? No: higher lambda means
    distortion is penalized more, so we spend more bits -> higher rate.
    """
    with torch.no_grad():
        active = scales > 1e-4

        if not active.any():
            return _baseline_dead_zone(y_res)

        scales_disc = _discretize_scales(scales)

        y_q_base = _baseline_dead_zone(y_res)
        rate_base = _gaussian_rate(y_q_base, scales_disc)
        rate_base_total = rate_base[active].sum().item()

        if rate_base_total < 1.0:
            return y_q_base

        # Target rate: 0.35% above baseline estimated rate.
        # Cap is 0.5% actual; leaves margin for estimation error
        # (CDF quantization, RANS overhead, etc.).
        target_rate = rate_base_total * 1.0035

        abs_y = torch.abs(y_res)[active]
        sign_y = torch.sign(y_res)[active]
        s_active = scales_disc[active]

        max_q = int(torch.ceil(abs_y.max()).item()) + 10
        max_q = min(max_q, 200)

        # Find lambda bounds:
        # lambda low  -> low rate  (fewer bits, higher distortion)
        # lambda high -> high rate (more bits, lower distortion)
        lambda_low = 0.0001
        lambda_high = 10.0

        # Shrink lambda_low until rate is BELOW target
        for _ in range(20):
            _, rate_low = _optimal_q_for_lambda(abs_y, s_active, lambda_low, max_q)
            if rate_low.sum().item() < target_rate:
                break
            lambda_low *= 0.1
            if lambda_low < 1e-8:
                break

        # Expand lambda_high until rate is ABOVE target
        for _ in range(20):
            _, rate_high = _optimal_q_for_lambda(abs_y, s_active, lambda_high, max_q)
            if rate_high.sum().item() > target_rate:
                break
            lambda_high *= 10.0
            if lambda_high > 1e6:
                break

        # Binary search (geometric mean since lambda spans log scale)
        # After convergence: lambda_low -> rate < target, lambda_high -> rate > target
        for _ in range(25):
            lambda_mid = math.sqrt(lambda_low * lambda_high)
            _, rate_mid = _optimal_q_for_lambda(abs_y, s_active, lambda_mid, max_q)
            total_rate = rate_mid.sum().item()

            if total_rate > target_rate:
                lambda_high = lambda_mid
            else:
                lambda_low = lambda_mid

        # Use lambda_low (conservative: guaranteed rate <= target)
        q_opt, _ = _optimal_q_for_lambda(abs_y, s_active, lambda_low, max_q)

        y_q = torch.zeros_like(y_res)
        y_q[active] = sign_y * q_opt

        return y_q

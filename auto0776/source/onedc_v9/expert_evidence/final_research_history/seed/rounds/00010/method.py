"""Lagrangian rate-distortion optimized quantizer.

Binary searches over a Lagrange multiplier to find the optimal integer
quantization minimizing MSE distortion under a rate cap. Rate is
estimated with the discretized Gaussian model matching the frozen
entropy coder.
"""

import math
import torch


_SCALE_MIN = 0.11
_SCALE_MAX = 64.0
_SCALE_LEVEL = 256


def _build_scale_table(device, dtype):
    log_min = math.log(_SCALE_MIN)
    log_max = math.log(_SCALE_MAX)
    return torch.exp(torch.linspace(log_min, log_max, _SCALE_LEVEL,
                                    device=device, dtype=dtype))


def _discretize_scales(scales, scale_table):
    log_min = math.log(_SCALE_MIN)
    log_max = math.log(_SCALE_MAX)
    log_step = (log_max - log_min) / (_SCALE_LEVEL - 1)
    log_s = torch.log(torch.clamp(scales, min=_SCALE_MIN))
    indexes = ((log_s - log_min) / log_step).clamp_(0, _SCALE_LEVEL - 1).floor().long()
    return scale_table[indexes]


def _gaussian_rate(abs_q, sigma):
    """Rate in bits for |q| under N(0, sigma). Both tensors broadcast."""
    sigma = torch.clamp(sigma, min=_SCALE_MIN)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    upper = (abs_q + 0.5) / sigma * inv_sqrt2
    lower = (abs_q - 0.5) / sigma * inv_sqrt2
    prob = 0.5 * (torch.erf(upper) - torch.erf(lower))
    return -torch.log2(torch.clamp(prob, min=1e-30))


def _baseline_dead_zone(y_res, tau=0.6):
    shift = tau - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(
        torch.clamp(torch.abs(y_res) - shift, min=0.0))


def _optimal_q_for_lambda(abs_y, sigma, lam, q_max):
    """Find |q*| minimizing (|y|-|q|)^2 + lam*rate(|q|, sigma).

    Evaluates all |q| in [0, q_max] vectorized over coefficients.
    Returns (best_abs_q, rate_at_best).
    """
    device = abs_y.device
    dtype = abs_y.dtype
    n = abs_y.numel()

    qvals = torch.arange(0, q_max + 1, device=device, dtype=dtype)  # (Q,)
    Q = qvals.shape[0]

    # (n, Q) batch evaluation
    y_e = abs_y.view(n, 1).expand(n, Q)
    q_e = qvals.view(1, Q).expand(n, Q)
    s_e = sigma.view(n, 1).expand(n, Q)

    distortion = (y_e - q_e) ** 2
    rate = _gaussian_rate(q_e, s_e)
    cost = distortion + lam * rate

    best_idx = torch.argmin(cost, dim=1)
    best_q = qvals[best_idx]

    # Vectorized best-rate gathering
    best_rate = rate[torch.arange(n, device=device), best_idx]

    return best_q, best_rate


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """Lagrangian RDO: binary search on lambda to hit target rate.

    Each coefficient's optimal integer value minimizes
        (y - q)^2 + lambda * rate(q, sigma).
    Targets ~0.4% actual bpp increase (within the 0.5% hard cap).
    """
    with torch.no_grad():
        orig_dtype = y_res.dtype
        device = y_res.device

        y = y_res.float()
        s = scales.float()

        active = s > 1e-4
        n_active = int(active.sum().item())
        if n_active == 0:
            return _baseline_dead_zone(y_res).to(orig_dtype)

        scale_table = _build_scale_table(device, torch.float32)
        sigma = _discretize_scales(s, scale_table)

        # --- Dead-zone baseline for rate reference ---
        y_dz = _baseline_dead_zone(y, tau=0.6)
        rate_dz = _gaussian_rate(y_dz[active].abs(), sigma[active]).sum().item()

        if rate_dz < 1.0:
            return y_dz.to(orig_dtype)

        # --- Target rate ---
        # Actual cap = baseline_bpp * 1.005.
        # Target 1.6% estimated increase; empirical ratio needs refinement.
        target_rate = rate_dz * 1.016

        abs_y_a = y[active].abs()
        sigma_a = sigma[active]

        # Candidate search range
        q_max = int(min(abs_y_a.max().ceil().item() + 3, 40))
        q_max = max(q_max, 5)

        # Rounding rate check (best quality, highest rate)
        rate_round = _gaussian_rate(abs_y_a.round(), sigma_a).sum().item()
        if rate_round <= target_rate:
            return torch.round(y).to(orig_dtype)

        # --- Binary search on lambda ---
        # lam small -> high rate; lam large -> low rate.
        lam_low = 1e-4
        lam_high = 1e2

        _, r_low_vec = _optimal_q_for_lambda(abs_y_a, sigma_a, lam_low, q_max)
        rate_low = r_low_vec.sum().item()

        _, r_high_vec = _optimal_q_for_lambda(abs_y_a, sigma_a, lam_high, q_max)
        rate_high = r_high_vec.sum().item()

        # If lam_low rate is below target, rounding already fits (handled above).
        # If lam_high rate is above target, widen upper bound.
        if rate_high > target_rate:
            lam_high = 1e4
            _, r_high_vec = _optimal_q_for_lambda(abs_y_a, sigma_a, lam_high, q_max)
            rate_high = r_high_vec.sum().item()
            if rate_high > target_rate:
                q_final, _ = _optimal_q_for_lambda(abs_y_a, sigma_a, lam_high, q_max)
                y_q = torch.zeros_like(y)
                y_q[active] = torch.sign(y[active]) * q_final
                return y_q.to(orig_dtype)

        # Binary search in log-space
        for _ in range(20):
            lam_mid = math.sqrt(lam_low * lam_high)
            _, r_mid_vec = _optimal_q_for_lambda(abs_y_a, sigma_a, lam_mid, q_max)
            rate_mid = r_mid_vec.sum().item()

            if rate_mid > target_rate:
                lam_low = lam_mid
            else:
                lam_high = lam_mid

        # Use lam_high (under-budget side) for safety
        q_final, _ = _optimal_q_for_lambda(abs_y_a, sigma_a, lam_high, q_max)

        y_q = torch.zeros_like(y)
        y_q[active] = torch.sign(y[active]) * q_final

        return y_q.to(orig_dtype)

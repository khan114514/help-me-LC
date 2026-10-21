"""Lagrangian rate-distortion optimization with conservative rate calibration.

For each coefficient, finds the integer quantization level minimizing
MSE + lambda * rate, where rate is estimated from the discretized-scale
Gaussian entropy model.  Lambda is binary-searched to hit a target rate
increase above the dead-zone baseline that is calibrated to safely fit
within the 0.5% actual total-bpp cap.
"""

import math
import torch


_SCALE_MIN = 0.11
_SCALE_MAX = 64.0
_SCALE_LEVEL = 256
_MAX_LEVEL = 31  # max absolute value to consider per coefficient


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


def _gaussian_rate_signed(q_abs, sigma):
    """Rate in bits for |q|=q_abs (magnitude) of a signed integer under N(0, sigma).

    For q=0: rate = -log2 P(|x| < 0.5)
    For q=k>0: rate = -log2 P(k-0.5 < x < k+0.5)  = rate of signed value +k (or -k)
    """
    sigma = torch.clamp(sigma, min=_SCALE_MIN)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    upper = (q_abs + 0.5) / sigma * inv_sqrt2
    lower = (q_abs - 0.5) / sigma * inv_sqrt2
    prob = 0.5 * (torch.erf(upper) - torch.erf(lower))
    return -torch.log2(torch.clamp(prob, min=1e-30))


def _baseline_dead_zone(y_res, tau=0.6):
    """Baseline dead-zone quantizer (tau=0.6 matches frozen codec baseline)."""
    shift = tau - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(
        torch.clamp(torch.abs(y_res) - shift, min=0.0))


def _compute_rates_for_levels(sigma_disc, max_level):
    """Pre-compute rate for magnitudes 0..max_level for each coefficient.

    Returns tensor of shape [max_level+1, *sigma_disc.shape] with rate in bits.
    """
    levels = torch.arange(max_level + 1, device=sigma_disc.device, dtype=sigma_disc.dtype)
    # Reshape levels to broadcast with sigma_disc
    levels_expanded = levels.view(-1, *([1] * sigma_disc.ndim))
    sigma_expanded = sigma_disc.unsqueeze(0)
    return _gaussian_rate_signed(levels_expanded, sigma_expanded)


def _lagrangian_minimizer(abs_y, rate_table, lam):
    """Find magnitude minimizing | |y| - q |^2 + lam * rate(q) for each coefficient.

    rate_table: [L, ...]  rates for magnitudes 0..L-1
    abs_y: [...]          absolute residual values
    lam: scalar Lagrange multiplier

    Returns:
        q_opt: [...] optimal integer magnitudes
        total_rate: scalar total estimated rate
    """
    L = rate_table.shape[0]
    # Compute distortion for each level
    levels = torch.arange(L, device=abs_y.device, dtype=abs_y.dtype)
    levels_expanded = levels.view(-1, *([1] * abs_y.ndim))
    distortion = (abs_y.unsqueeze(0) - levels_expanded) ** 2  # [L, ...]

    # Lagrangian cost
    cost = distortion + lam * rate_table  # [L, ...]

    # Find argmin over level dimension
    q_opt = torch.argmin(cost, dim=0).to(abs_y.dtype)  # [...]

    # Gather rate at optimal level
    total_rate = rate_table.gather(0, q_opt.unsqueeze(0).long()).squeeze(0).sum()

    return q_opt, total_rate


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """Lagrangian RDO with binary search over lambda.

    Minimizes MSE + lambda * rate subject to estimated-rate budget calibrated
    to stay within the 0.5% actual-bpp cap with safety margin.
    """
    with torch.no_grad():
        device = y_res.device
        dtype = y_res.dtype

        active = scales > 1e-4
        if not active.any():
            return _baseline_dead_zone(y_res)

        sigma_disc = _discretize_scales(scales)

        sign = torch.sign(y_res)
        abs_y = torch.abs(y_res)

        # Baseline dead-zone quantization and its rate
        y_q_base = _baseline_dead_zone(y_res)
        rate_base = _gaussian_rate_signed(torch.abs(y_q_base), sigma_disc)
        rate_base_total = rate_base[active].sum().item()

        if rate_base_total < 1.0:
            return y_q_base

        # Target estimated y-rate increase: 0.9% above baseline.
        # Calibration: y-bits are ~54% of total bpp, so 0.9% y-rate increase
        # translates to ~0.49% total bpp increase — just under the 0.5% cap.
        target_total = rate_base_total * 1.008

        # Determine max level to evaluate
        max_abs = int(torch.ceil(abs_y[active].max()).item()) + 2
        max_level = min(max(max_abs, _MAX_LEVEL), 30)

        # Precompute rate table for all levels [0, max_level]
        rate_table = _compute_rates_for_levels(sigma_disc, max_level)  # [L, ...]

        # Binary search for lambda.
        # lam=0 -> minimize distortion (highest rate, ~round(y_res))
        # lam large -> minimize rate (lowest rate, all zeros)
        lam_lo = 0.0
        lam_hi = 1.0

        # Find an upper bound where rate <= target
        q_hi, rate_hi = _lagrangian_minimizer(abs_y, rate_table, lam_hi)
        for _ in range(20):
            if rate_hi.item() <= target_total:
                break
            lam_hi *= 2.0
            q_hi, rate_hi = _lagrangian_minimizer(abs_y, rate_table, lam_hi)

        if rate_hi.item() > target_total:
            # Even very high lambda can't reduce rate enough — return baseline
            return y_q_base

        # Check lower bound: lam=0 gives highest rate
        q_lo, rate_lo = _lagrangian_minimizer(abs_y, rate_table, lam_lo)
        if rate_lo.item() <= target_total:
            # lam=0 already fits budget — use minimum-distortion solution
            y_q = sign * q_lo
            return torch.round(y_q)

        # Binary search
        for _ in range(24):
            lam_mid = (lam_lo + lam_hi) * 0.5
            q_mid, rate_mid = _lagrangian_minimizer(abs_y, rate_table, lam_mid)
            if rate_mid.item() > target_total:
                # Need larger lambda to reduce rate
                lam_lo = lam_mid
                q_lo = q_mid
                rate_lo = rate_mid
            else:
                lam_hi = lam_mid
                q_hi = q_mid
                rate_hi = rate_mid

        # Use the solution with rate <= target (lam_hi side)
        q_opt = q_hi

        # Apply sign
        y_q = sign * q_opt

        # Ensure integer values
        y_q = torch.round(y_q)

        return y_q

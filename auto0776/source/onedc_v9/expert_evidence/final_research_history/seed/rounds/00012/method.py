"""Lagrangian rate-distortion optimization with discretized scale rates.

Per-coefficient RDO minimizes MSE + lambda * rate, with rate computed from
the Gaussian model using the coder's 256-level discretized scale table.
Binary-searches lambda to hit a target estimated-rate increase above the
dead-zone baseline.  A conservative target keeps us within the 0.5 %
actual-rate cap.
"""

import math
import torch


_SCALE_MIN = 0.11
_SCALE_MAX = 64.0
_SCALE_LEVEL = 256


def _discretize_scales(scales):
    log_min = math.log(_SCALE_MIN)
    log_step = (math.log(_SCALE_MAX) - log_min) / (_SCALE_LEVEL - 1)
    log_s = torch.log(torch.clamp(scales, min=_SCALE_MIN))
    indexes = ((log_s - log_min) / log_step).clamp_(0, _SCALE_LEVEL - 1).floor().long()
    table = torch.exp(torch.linspace(log_min, math.log(_SCALE_MAX), _SCALE_LEVEL,
                                      device=scales.device, dtype=scales.dtype))
    return table[indexes]


def _gaussian_rate(q, sigma):
    """Rate in bits for integer q under N(0, sigma) — signed formulation."""
    sigma = torch.clamp(sigma, min=_SCALE_MIN)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    abs_q = torch.abs(q)
    upper = (abs_q + 0.5) / sigma * inv_sqrt2
    lower = (abs_q - 0.5) / sigma * inv_sqrt2
    prob = 0.5 * (torch.erf(upper) - torch.erf(lower))
    return -torch.log2(torch.clamp(prob, min=1e-30))


def _dead_zone(y_res, tau=0.6):
    shift = tau - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(
        torch.clamp(torch.abs(y_res) - shift, min=0.0))


def _rdo_quantize(y_res, sigma_disc, lam, active):
    """Per-coefficient Lagrangian RDO.

    Evaluates candidate magnitudes for each active coefficient and picks
    the level minimizing (y_res - q)^2 + lam * rate(q).
    Candidates are 0..ceil(max(|y_res|)+3), capped at 24.
    """
    sign_y = torch.sign(y_res)
    abs_y = torch.abs(y_res)

    abs_y_active = abs_y[active]
    sigma_active = sigma_disc[active]

    max_val = abs_y_active.max().item()
    max_cand = min(int(math.ceil(max_val)) + 3, 24)

    device = y_res.device
    dtype = y_res.dtype

    candidates = torch.arange(max_cand + 1, device=device, dtype=dtype)

    abs_y_exp = abs_y_active.unsqueeze(-1)
    sigma_exp = sigma_active.unsqueeze(-1)
    cand_exp = candidates.unsqueeze(0)

    dist = (abs_y_exp - cand_exp) ** 2
    rate = _gaussian_rate(cand_exp, sigma_exp)

    cost = dist + lam * rate

    best_idx = torch.argmin(cost, dim=-1)
    best_mag = candidates[best_idx]

    result = torch.zeros_like(y_res)
    result[active] = sign_y[active] * best_mag
    return result


def _compute_total_rate(y_q, sigma_disc, active):
    rate = _gaussian_rate(y_q, sigma_disc)
    return rate[active].sum().item()


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """Lagrangian RDO with binary lambda search.

    Binary-searches lambda so that the estimated total rate equals
    (1 + target_increase) times the baseline dead-zone rate.
    """
    with torch.no_grad():
        active = scales > 1e-4
        n_active = active.sum().item()
        if n_active == 0:
            return _dead_zone(y_res)

        sigma_disc = _discretize_scales(scales)

        y_baseline = _dead_zone(y_res)
        rate_base = _compute_total_rate(y_baseline, sigma_disc, active)

        if rate_base < 1.0:
            return y_baseline

        # Target: 0.35 % estimated-rate increase above dead-zone baseline.
        # Conservative target ensures we stay under the 0.5 % actual-rate cap.
        target_increase = 0.0035
        target_rate = rate_base * (1.0 + target_increase)

        # lam=0 gives round() (maximum rate, minimum distortion).
        # Higher lambda gives lower rate / higher distortion.
        lam_lo = 0.0
        lam_hi = 2.0

        y_lo = _rdo_quantize(y_res, sigma_disc, lam_lo, active)
        rate_lo = _compute_total_rate(y_lo, sigma_disc, active)

        if rate_lo <= target_rate:
            return y_lo

        y_hi = _rdo_quantize(y_res, sigma_disc, lam_hi, active)
        rate_hi = _compute_total_rate(y_hi, sigma_disc, active)

        while rate_hi > target_rate and lam_hi < 64.0:
            lam_hi *= 2.0
            y_hi = _rdo_quantize(y_res, sigma_disc, lam_hi, active)
            rate_hi = _compute_total_rate(y_hi, sigma_disc, active)

        if rate_hi > target_rate:
            return y_hi

        # Binary search: find lam where rate ~ target_rate, preferring
        # the lower-rate side (higher lambda) for safety.
        for _ in range(14):
            lam_mid = (lam_lo + lam_hi) * 0.5
            y_mid = _rdo_quantize(y_res, sigma_disc, lam_mid, active)
            rate_mid = _compute_total_rate(y_mid, sigma_disc, active)

            if rate_mid > target_rate:
                lam_lo = lam_mid
                y_lo = y_mid
                rate_lo = rate_mid
            else:
                lam_hi = lam_mid
                y_hi = y_mid
                rate_hi = rate_mid

        return y_hi

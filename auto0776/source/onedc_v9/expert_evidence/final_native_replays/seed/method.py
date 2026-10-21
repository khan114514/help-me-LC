"""Greedy rate-distortion optimization.

Starts from baseline dead-zone (tau=0.6) and greedily upgrades coefficient
magnitudes by one level, prioritized by MSE distortion reduction per
estimated bit. Uses scale-discretized Gaussian rate estimates.
"""

import math
import torch


_SCALE_MIN = 0.11
_SCALE_MAX = 64.0
_SCALE_LEVEL = 256


def _gaussian_rate_signed(q, sigma):
    """Rate in bits for signed integer q under N(0, sigma)."""
    sigma = torch.clamp(sigma, min=_SCALE_MIN)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    abs_q = torch.abs(q)
    upper = (abs_q + 0.5) / sigma * inv_sqrt2
    lower = (abs_q - 0.5) / sigma * inv_sqrt2
    prob = 0.5 * (torch.erf(upper) - torch.erf(lower))
    return -torch.log2(torch.clamp(prob, min=1e-30))


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


def _baseline_dead_zone(y_res, tau=0.6):
    """Baseline dead-zone quantizer."""
    shift = tau - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(
        torch.clamp(torch.abs(y_res) - shift, min=0.0))


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """Greedy R-D upgrades from baseline dead-zone.

    Iteratively upgrades magnitudes by +1 level, sorted by MSE distortion
    reduction per estimated bit.  Budget calibrated to stay within the
    0.5 % actual-rate cap with a small safety margin.
    """
    with torch.no_grad():
        active = scales > 1e-4

        if not active.any():
            return _baseline_dead_zone(y_res)

        scales_disc = _discretize_scales(scales)

        y_q = _baseline_dead_zone(y_res)
        sign_y = torch.sign(y_res)
        abs_y = torch.abs(y_res)

        # Baseline rate
        rate_base = _gaussian_rate_signed(y_q, scales_disc)
        rate_base_total = rate_base[active].sum().item()

        if rate_base_total < 1.0:
            return y_q

        # 0.82% estimated -> ~0.44% actual based on calibration
        # Actual cap: 0.50%; leaves ~0.06% safety margin.
        target_increase = rate_base_total * 0.0082

        remaining = target_increase

        for _pass in range(8):
            if remaining <= 0:
                break

            abs_q = torch.abs(y_q)

            delta_d = 2.0 * (abs_y - abs_q) - 1.0
            delta_d = torch.clamp(delta_d, min=0.0)

            valid = active & (delta_d > 1e-6)
            if not valid.any():
                break

            rate_curr = _gaussian_rate_signed(abs_q, scales_disc)
            rate_next = _gaussian_rate_signed(abs_q + 1.0, scales_disc)
            delta_r = rate_next - rate_curr

            valid = valid & (delta_r > 1e-6)
            if not valid.any():
                break

            gain = delta_d[valid] / delta_r[valid]

            sorted_idx = torch.argsort(gain, descending=True)
            sorted_dr = delta_r[valid][sorted_idx]

            cum_r = torch.cumsum(sorted_dr, dim=0)
            n_upgrade = torch.searchsorted(cum_r, remaining).item()
            n_upgrade = min(n_upgrade, len(sorted_dr))

            if n_upgrade == 0:
                break

            threshold_gain = gain[sorted_idx[n_upgrade - 1]]

            upgrade = torch.zeros_like(y_q, dtype=torch.bool)
            upgrade[valid] = gain >= threshold_gain * 0.999999

            actual_inc = delta_r[upgrade].sum().item()
            if actual_inc > remaining * 1.005:
                n_upgrade = max(1, n_upgrade - 1)
                threshold_gain = gain[sorted_idx[n_upgrade - 1]]
                upgrade = torch.zeros_like(y_q, dtype=torch.bool)
                upgrade[valid] = gain > threshold_gain
                actual_inc = delta_r[upgrade].sum().item()

            y_q = torch.where(upgrade, sign_y * (abs_q + 1.0), y_q)
            remaining -= actual_inc

            if remaining <= 0:
                break

        return y_q

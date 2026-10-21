"""Refined greedy RDO quantizer.

Starts from dead-zone baseline and greedily upgrades coefficient magnitudes,
prioritized by MSE distortion reduction per estimated bit.  Uses a conservative
rate budget calibrated to stay well under the 0.5 % actual-bitrate cap.
"""

import math
import torch


_SCALE_MIN = 0.11
_SCALE_MAX = 64.0
_SCALE_LEVEL = 256


def _gaussian_rate(q, sigma):
    """Rate in bits for integer q under N(0, sigma), q can be signed."""
    sigma = torch.clamp(sigma, min=_SCALE_MIN)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    abs_q = torch.abs(q.float())
    upper = (abs_q + 0.5) / sigma * inv_sqrt2
    lower = (abs_q - 0.5) / sigma * inv_sqrt2
    prob = 0.5 * (torch.erf(upper) - torch.erf(lower))
    return -torch.log2(torch.clamp(prob, min=1e-30))


def _discretize_scales(scales):
    """Map continuous scales to the coder's 256-level log table."""
    log_min = math.log(_SCALE_MIN)
    log_max = math.log(_SCALE_MAX)
    log_step = (log_max - log_min) / (_SCALE_LEVEL - 1)
    log_s = torch.log(torch.clamp(scales, min=_SCALE_MIN))
    idx = ((log_s - log_min) / log_step).clamp_(0, _SCALE_LEVEL - 1).floor().long()
    table = torch.exp(torch.linspace(log_min, log_max, _SCALE_LEVEL,
                                      device=scales.device, dtype=scales.dtype))
    return table[idx]


def _dead_zone(y_res, tau=0.6):
    """Dead-zone quantizer with half-width tau."""
    shift = tau - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(
        torch.clamp(torch.abs(y_res) - shift, min=0.0))


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """Greedy RDO: upgrade coefficients by gain = delta_MSE / delta_rate."""
    with torch.no_grad():
        scales_disc = _discretize_scales(scales)
        y_q = _dead_zone(y_res, tau=0.6)

        sign_y = torch.sign(y_res)
        abs_y = torch.abs(y_res)
        abs_q = torch.abs(y_q)

        # Baseline estimated rate
        base_rate = _gaussian_rate(y_q, scales_disc).sum().item()

        if base_rate < 1.0:
            return y_q

        # Budget: 0.35 % above baseline estimated rate
        # Leaves safety margin under the 0.5 % actual-bpp cap.
        budget = base_rate * 0.0035
        remaining = budget

        for _pass in range(6):
            if remaining <= 0:
                break

            # MSE reduction from upgrading magnitude by 1:
            # delta_d = (|y| - |q|)^2 - (|y| - (|q|+1))^2
            #        = 2*|y| - 2*|q| - 1
            delta_d = 2.0 * (abs_y - abs_q) - 1.0
            delta_d = torch.clamp(delta_d, min=0.0)

            # Only consider coefficients where upgrading helps
            active = delta_d > 1e-6

            if not active.any():
                break

            # Rate increase from upgrading
            r_curr = _gaussian_rate(abs_q, scales_disc)
            r_next = _gaussian_rate(abs_q + 1.0, scales_disc)
            delta_r = r_next - r_curr

            valid = active & (delta_r > 1e-8)
            if not valid.any():
                break

            gain = delta_d[valid] / delta_r[valid]

            # Sort by gain descending
            sort_idx = torch.argsort(gain, descending=True)
            sorted_dr = delta_r[valid][sort_idx]

            cum_r = torch.cumsum(sorted_dr, dim=0)
            n_upgrade = int(torch.searchsorted(cum_r, remaining).item())
            n_upgrade = min(n_upgrade, len(sorted_dr))

            if n_upgrade == 0:
                break

            n_upgrade = max(1, min(n_upgrade, len(sorted_dr)))
            threshold_gain = gain[sort_idx[n_upgrade - 1]]

            upgrade = torch.zeros_like(y_q, dtype=torch.bool)
            upgrade[valid] = gain >= threshold_gain * 0.99999

            actual_inc = delta_r[upgrade].sum().item()

            # If we overshoot, use one fewer
            if actual_inc > remaining * 1.002:
                n_upgrade = max(1, n_upgrade - 1)
                threshold_gain = gain[sort_idx[n_upgrade - 1]]
                upgrade = torch.zeros_like(y_q, dtype=torch.bool)
                upgrade[valid] = gain > threshold_gain
                actual_inc = delta_r[upgrade].sum().item()

            abs_q = torch.where(upgrade, abs_q + 1.0, abs_q)
            remaining -= actual_inc

            if remaining <= 0:
                break

        return sign_y * abs_q

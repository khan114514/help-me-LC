"""Per-coefficient Lagrangian RDO with calibrated discretized-scale rate model.

Minimizes MSE + lambda * rate over integer quantization levels, using a
rate model that matches the actual entropy coder's 256-level log-discretized
scales. Lambda is found by binary search to target a small rate increase
above the dead-zone baseline with a conservative safety margin.
"""

import math
import torch


_SCALE_MIN = 0.11
_SCALE_MAX = 64.0
_SCALE_LEVEL = 256


def _build_scale_table(device, dtype):
    """256 log-spaced scale levels matching GaussianEncoder."""
    log_min = math.log(_SCALE_MIN)
    log_max = math.log(_SCALE_MAX)
    return torch.exp(torch.linspace(log_min, log_max, _SCALE_LEVEL,
                                    device=device, dtype=dtype))


def _discretize_scales(scales, table):
    """Floor scales to nearest log-table level (matching build_indexes.int())."""
    log_min = math.log(_SCALE_MIN)
    log_step = (math.log(_SCALE_MAX) - log_min) / (_SCALE_LEVEL - 1)
    log_s = torch.log(torch.clamp(scales, min=_SCALE_MIN))
    indexes = ((log_s - log_min) / log_step).clamp_(0, _SCALE_LEVEL - 1).floor().long()
    return table[indexes]


def _gaussian_pmf_abs(q, sigma):
    """P(|X| in [q-0.5, q+0.5]) for X ~ N(0, sigma). For q=0: P(|X| < 0.5).
    
    Uses the same erf formulation as GaussianEncoder.get_gaussian_prob.
    """
    sigma = torch.clamp(sigma, min=_SCALE_MIN)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    abs_q = torch.abs(q)
    upper = (abs_q + 0.5) / sigma * inv_sqrt2
    lower = (abs_q - 0.5) / sigma * inv_sqrt2
    prob = 0.5 * (torch.erf(upper) - torch.erf(lower))
    return torch.clamp(prob, min=1e-30)


def _rate_signed(q, sigma_disc):
    """Rate in bits for signed integer q under discretized-scale Gaussian."""
    pmf = _gaussian_pmf_abs(q, sigma_disc)
    return -torch.log2(pmf)


def _baseline_dead_zone(y_res, tau=0.6):
    """Baseline dead-zone quantizer."""
    shift = tau - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(
        torch.clamp(torch.abs(y_res) - shift, min=0.0))


def _quantize_lagrangian(y_res, sigma_disc, lam, max_level=8):
    """Find integer q minimizing |y - q|^2 + lambda * rate(q).
    
    Vectorized: evaluates all candidate levels 0..max_level simultaneously.
    """
    abs_y = torch.abs(y_res)
    sign_y = torch.sign(y_res)
    
    # Candidate levels: 0, 1, ..., max_level
    levels = torch.arange(max_level + 1, device=y_res.device, dtype=y_res.dtype)
    # Shape: (1, ..., 1, max_level+1) for broadcasting
    shape = [1] * (abs_y.dim() + 1)
    shape[-1] = -1
    levels = levels.view(*shape)
    
    # Expand abs_y and sigma_disc to have a trailing level dim
    abs_y_e = abs_y.unsqueeze(-1)
    sigma_e = sigma_disc.unsqueeze(-1)
    
    # MSE distortion for each level
    distortion = (abs_y_e - levels) ** 2
    
    # Rate for each level
    rate = _rate_signed(levels, sigma_e)
    
    # Lagrangian cost
    cost = distortion + lam * rate
    
    # Find best level per coefficient
    best_level = cost.argmin(dim=-1).float()
    
    return sign_y * best_level


def _total_rate_estimate(q, sigma_disc, active_mask):
    """Total estimated bits for signed integer quantization."""
    rate = _rate_signed(q, sigma_disc)
    return rate[active_mask].sum().item()


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """Lagrangian RDO with discretized-scale rate model and binary search over lambda.
    
    Targets a conservative rate increase above baseline dead-zone to stay
    well within the 0.5% actual-rate cap.
    """
    with torch.no_grad():
        active = scales > 1e-4
        if not active.any():
            return _baseline_dead_zone(y_res)
        
        device = y_res.device
        dtype = y_res.dtype
        
        # Build discretized scale table and quantize scales (floor to table)
        scale_table = _build_scale_table(device, dtype)
        sigma_disc = _discretize_scales(scales, scale_table)
        
        # Baseline dead-zone quantization
        y_base = _baseline_dead_zone(y_res)
        rate_base = _total_rate_estimate(y_base, sigma_disc, active)
        
        if rate_base < 1.0:
            return y_base
        
        # Target: 0.25% estimated rate increase with discretized scales.
        # Conservative: previous Lagrangian with continuous scales had ~20x
        # actual/estimated ratio, but discretized scales should give much
        # better calibration. We target well under the 0.5% cap.
        target_increase_ratio = 0.0025
        target_rate = rate_base * (1.0 + target_increase_ratio)
        
        # Binary search over lambda
        lam_low = 0.0
        lam_high = 200.0
        
        # Evaluate at high lambda first (should give rate <= baseline)
        q_high = _quantize_lagrangian(y_res, sigma_disc, lam_high)
        rate_high = _total_rate_estimate(q_high, sigma_disc, active)
        
        # If even high lambda gives too high rate, return baseline
        if rate_high > target_rate:
            return y_base
        
        q_low = _quantize_lagrangian(y_res, sigma_disc, lam_low)
        rate_low = _total_rate_estimate(q_low, sigma_disc, active)
        
        # If zero lambda is already within budget, use it
        if rate_low <= target_rate:
            return torch.round(q_low)
        
        # Binary search for lambda that hits target rate
        for _ in range(12):
            lam_mid = 0.5 * (lam_low + lam_high)
            q_mid = _quantize_lagrangian(y_res, sigma_disc, lam_mid)
            rate_mid = _total_rate_estimate(q_mid, sigma_disc, active)
            
            if rate_mid > target_rate:
                lam_low = lam_mid
                rate_low = rate_mid
            else:
                lam_high = lam_mid
                rate_high = rate_mid
                q_high = q_mid
        
        # Return the solution at lam_high (which is within budget)
        result = q_high
        
        # Ensure integer values
        result = torch.round(result)
        
        # Safety clamp: ensure no extreme values
        result = torch.clamp(result, min=-32, max=32)
        
        return result

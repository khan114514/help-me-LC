"""Lagrangian optimal quantization with scale-dependent perceptual penalty.

Accurate rate tables match the frozen 256-level Gaussian rANS coder.
Distortion objective includes a per-coefficient non-zero penalty that
scales inversely with sigma: high-frequency (small-sigma) coefficients
are zeroed more aggressively, consistent with perceptual masking.

Binary-searches lambda to hit a target just under the 1.005x rate cap.
"""

import math
import torch

_SCALE_MIN = 0.11
_SCALE_MAX = 64.0
_SCALE_LEVEL = 256
_inv_sqrt2 = 1.0 / math.sqrt(2.0)

_rate_table = None
_scale_table_tensor = None
_table_device = None
_log_scale_min = math.log(_SCALE_MIN)
_log_scale_step = (math.log(_SCALE_MAX) - _log_scale_min) / (_SCALE_LEVEL - 1)


def _ensure_tables(device):
    global _rate_table, _scale_table_tensor, _table_device
    if _rate_table is not None and _table_device == device:
        return

    scale_table = torch.exp(torch.linspace(
        _log_scale_min, math.log(_SCALE_MAX), _SCALE_LEVEL))

    pmf_center = torch.full((_SCALE_LEVEL,), 50, dtype=torch.int32)
    for i in range(50, 1, -1):
        z = i / scale_table * _inv_sqrt2
        cdf_i = 0.5 * (1.0 + torch.erf(z))
        pmf_center = torch.where(cdf_i > 0.9999,
                                 torch.tensor(i, dtype=torch.int32), pmf_center)

    max_pmf = int(pmf_center.max().item())
    max_k = max_pmf + 10

    k_vals = torch.arange(max_k + 1, dtype=torch.float32)
    upper = (k_vals.view(1, -1) + 0.5) / scale_table.view(-1, 1) * _inv_sqrt2
    lower = (k_vals.view(1, -1) - 0.5) / scale_table.view(-1, 1) * _inv_sqrt2
    pmf_signed = 0.5 * (torch.erf(upper) - torch.erf(lower))

    rate_table = -torch.log2(torch.clamp(pmf_signed, min=1e-30))

    tail_z = (-(pmf_center.float() + 0.5)) / scale_table * _inv_sqrt2
    tail_mass = torch.clamp(1.0 + torch.erf(tail_z), min=1e-30)
    tail_rate = -torch.log2(tail_mass)

    for s in range(_SCALE_LEVEL):
        pc = int(pmf_center[s].item())
        tr = tail_rate[s].item()
        for k in range(pc + 1, max_k + 1):
            raw_val = 2 * (k - pc - 1)
            if raw_val == 0:
                bypass_bits = 2.0
            else:
                n_bypass = math.ceil(math.log2(raw_val + 1) / 2)
                n_groups = n_bypass // 3 + 1
                bypass_bits = 2.0 * (n_groups + n_bypass)
            rate_table[s, k] = tr + bypass_bits

    _rate_table = rate_table.to(device)
    _scale_table_tensor = scale_table.to(device)
    _table_device = device


@torch.no_grad()
def _scale_index(scales: torch.Tensor) -> torch.Tensor:
    log_s = torch.log(torch.clamp(scales, min=_SCALE_MIN))
    idx = torch.floor((log_s - _log_scale_min) / _log_scale_step)
    idx = idx.clamp_(0, _SCALE_LEVEL - 1)
    return idx.to(torch.int64)


@torch.no_grad()
def _lookup_rate(q_signed: torch.Tensor, scale_idx: torch.Tensor) -> torch.Tensor:
    abs_q = torch.abs(q_signed).to(torch.int64)
    max_k = _rate_table.size(1) - 1
    return _rate_table[scale_idx, abs_q.clamp(0, max_k)]


@torch.no_grad()
def _lagrangian_cost(q_signed: torch.Tensor, y: torch.Tensor,
                     scale_idx: torch.Tensor, lam: float,
                     nz_penalty_base: float) -> torch.Tensor:
    """Cost = (y-q)^2 + lam*R(q) + (nz_penalty_base/sigma) * I(q != 0).

    Non-zero penalty scales with 1/sigma: small-sigma (high-frequency)
    coefficients get larger penalty, zeroing them more aggressively.
    """
    sigma = _scale_table_tensor[scale_idx]
    distortion = (y - q_signed) ** 2
    rate = _lookup_rate(q_signed, scale_idx)
    nz_penalty = nz_penalty_base / sigma * (torch.abs(q_signed) > 0.5).float()
    return distortion + lam * rate + nz_penalty


@torch.no_grad()
def _optimal_q(y: torch.Tensor, scale_idx: torch.Tensor,
               lam: float, nz_penalty_base: float) -> torch.Tensor:
    sigma = _scale_table_tensor[scale_idx]
    two_s2_ln2 = 2.0 * sigma ** 2 * math.log(2.0)
    q_cont = y / (1.0 + lam / two_s2_ln2)
    q_int = torch.round(q_cont).to(torch.int64)

    for _ in range(30):
        cost_curr = _lagrangian_cost(q_int.float(), y, scale_idx, lam, nz_penalty_base)
        cost_minus = _lagrangian_cost((q_int - 1).float(), y, scale_idx, lam, nz_penalty_base)
        cost_plus = _lagrangian_cost((q_int + 1).float(), y, scale_idx, lam, nz_penalty_base)

        better_minus = cost_minus < cost_curr
        better_plus = cost_plus < cost_curr

        if not (better_minus | better_plus).any():
            break

        move_left = better_minus & (~better_plus | (cost_minus <= cost_plus))
        move_right = better_plus & (~better_minus | (cost_plus < cost_minus))

        q_int = torch.where(move_left, q_int - 1, q_int)
        q_int = torch.where(move_right, q_int + 1, q_int)

    return q_int.float()


def _baseline_dead_zone(y_res: torch.Tensor, tau: float = 0.6) -> torch.Tensor:
    shift = tau - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(torch.clamp(torch.abs(y_res) - shift, min=0.0))


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """Lagrangian quantizer with scale-dependent perceptual penalty."""
    with torch.no_grad():
        device = y_res.device
        _ensure_tables(device)

        active = scales > 1e-4
        if not active.any():
            return _baseline_dead_zone(y_res)

        scale_idx = _scale_index(scales)

        y_q_base = _baseline_dead_zone(y_res)
        rate_base = _lookup_rate(y_q_base, scale_idx)
        rate_base_total = rate_base[active].sum().item()

        if rate_base_total < 1.0:
            return y_q_base

        # Perceptual non-zero penalty base (scaled by 1/sigma per coeff)
        nz_penalty_base = 0.03

        # Target: use most of the 0.5% margin
        target_rate = rate_base_total * 1.0035

        lam_low = 0.0
        lam_high = 10.0

        for _ in range(10):
            y_q_high = _optimal_q(y_res, scale_idx, lam_high, nz_penalty_base)
            rate_high = _lookup_rate(y_q_high, scale_idx)
            rate_high_total = rate_high[active].sum().item()
            if rate_high_total < target_rate:
                break
            lam_high *= 4.0
        else:
            return y_q_base

        for _ in range(25):
            lam_mid = (lam_low + lam_high) * 0.5
            y_q_mid = _optimal_q(y_res, scale_idx, lam_mid, nz_penalty_base)
            rate_mid = _lookup_rate(y_q_mid, scale_idx)
            rate_mid_total = rate_mid[active].sum().item()

            if rate_mid_total > target_rate:
                lam_low = lam_mid
            else:
                lam_high = lam_mid

        y_q_opt = _optimal_q(y_res, scale_idx, lam_high, nz_penalty_base)
        return y_q_opt

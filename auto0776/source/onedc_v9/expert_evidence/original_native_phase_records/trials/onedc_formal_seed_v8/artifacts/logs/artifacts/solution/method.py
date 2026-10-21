"""Incremental greedy rate-distortion improvement over baseline dead-zone.

Starting from the baseline dead-zone quantizer (tau=0.6), we consider
increasing the magnitude of each quantized value by 1 level (e.g., 0->1,
1->2, -1->-2, etc.). Each candidate upgrade is scored by its distortion
reduction per estimated bit cost. We apply the best candidates in order
until a conservative fraction of the rate budget is used.

Since we only make small incremental changes from baseline, the ratio
between estimated and actual bitrate should remain approximately
constant, making rate targeting reliable.
"""

import math
import torch


def gaussian_rate_abs(q_abs: torch.Tensor, sigma: torch.Tensor) -> torch.Tensor:
    """Rate in bits = -log2(P(|q|=q_abs)) for non-negative q_abs under N(0, sigma).

    Uses the same lower bound on sigma (0.11) as the frozen GaussianEncoder.
    For q_abs=0 this gives P(0); for q_abs>0 this gives 2*P(q) which is the
    total probability of either sign (we account for sign separately).
    """
    sigma = torch.clamp(sigma, min=0.11)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    upper = (q_abs + 0.5) / sigma * inv_sqrt2
    lower = (q_abs - 0.5) / sigma * inv_sqrt2
    prob = 0.5 * (torch.erf(upper) - torch.erf(lower))
    return -torch.log2(torch.clamp(prob, min=1e-30))


def baseline_dead_zone(y_res: torch.Tensor, tau: float = 0.6) -> torch.Tensor:
    """Baseline JPEG-style dead-zone quantizer (frozen Baseline)."""
    shift = tau - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(torch.clamp(torch.abs(y_res) - shift, min=0.0))


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """Greedy R-D improvement: incrementally upgrade magnitudes from baseline.

    1. Start with baseline dead-zone (tau=0.6).
    2. For each position, compute gain of upgrading magnitude by +1.
    3. Sort all candidates by (distortion reduction) / (rate increase).
    4. Apply best upgrades until 0.42% more estimated rate (conservative).
    5. Iterate: recompute gains and apply next level of upgrades.
    """
    with torch.no_grad():
        # Active positions: non-zero scales
        active = scales > 1e-4

        if not active.any():
            return baseline_dead_zone(y_res)

        # Step 1: baseline
        y_q = baseline_dead_zone(y_res)
        abs_q = torch.abs(y_q)
        sign_q = torch.sign(y_res)

        # Baseline estimated rate (using magnitude-based rate + 1 bit for sign when q != 0)
        # Actually, for Gaussian with zero mean, P(q) = P(-q), so rate of |q| includes both signs.
        # The actual coder codes q directly (signed), so rate(q) = rate_gaussian(q, sigma)
        # which is -log2(P(q)) for the specific signed value.
        # For q=0: rate = -log2(P(0))
        # For q!=0: rate = -log2(P(|q|)/2) = rate_abs(|q|) + 1  (approximately, not exact for small sigma)
        # Let's just compute rate directly for signed values using the same formula.

        def rate_signed(q_val, s_val):
            """Rate for signed integer q_val with scale s_val."""
            return gaussian_rate_abs(torch.abs(q_val), s_val)

        rate_base = rate_signed(y_q, scales)
        rate_base_total = rate_base[active].sum().item()

        if rate_base_total < 1.0:
            return y_q

        # Conservative target: 0.42% more estimated bits than baseline
        # Actual cap is 0.5% above baseline actual rate
        target_rate_increase = rate_base_total * 0.0042

        # Multiple passes: in each pass we upgrade magnitudes by 1
        remaining_budget = target_rate_increase

        for _pass in range(4):  # up to 4 levels of upgrades
            if remaining_budget <= 0:
                break

            abs_q = torch.abs(y_q)

            # Candidates for upgrade: all active positions
            # Upgrading from k to k+1 (in magnitude)
            # Distortion reduction: (|y_res| - k)^2 - (|y_res| - (k+1))^2 = 2*(|y_res| - k) - 1
            # Rate increase: rate(k+1) - rate(k)  (using signed rate)

            abs_y = torch.abs(y_res)

            # Distortion reduction from upgrading magnitude by 1
            delta_d = 2.0 * (abs_y - abs_q) - 1.0
            delta_d = torch.clamp(delta_d, min=0.0)

            # Only consider where distortion reduction is positive
            # (i.e., |y_res| - k > 0.5, meaning the next integer is closer)
            # But actually we want to consider ALL upgrades that reduce distortion
            # delta_d > 0 means |y_res| - abs_q > 0.5, which means abs_q + 1 is closer
            valid_upgrade = active & (delta_d > 1e-6)

            if not valid_upgrade.any():
                break

            # Rate increase: rate(k+1) - rate(k)
            rate_curr = rate_signed(abs_q, scales)
            rate_next = rate_signed(abs_q + 1.0, scales)
            delta_r = rate_next - rate_curr

            # Only consider positive rate increase
            valid_upgrade = valid_upgrade & (delta_r > 1e-6)

            if not valid_upgrade.any():
                break

            # Gain = distortion reduction per bit
            gain = delta_d[valid_upgrade] / delta_r[valid_upgrade]

            # Sort by gain (highest first)
            sorted_indices = torch.argsort(gain, descending=True)
            sorted_delta_r = delta_r[valid_upgrade][sorted_indices]

            # Cumulative rate
            cum_r = torch.cumsum(sorted_delta_r, dim=0)
            num_upgrades = torch.searchsorted(cum_r, remaining_budget).item()
            num_upgrades = min(num_upgrades, len(sorted_delta_r))

            if num_upgrades == 0:
                break

            # Find the threshold gain
            threshold_gain = gain[sorted_indices[num_upgrades - 1]]

            # Apply upgrades where gain >= threshold
            upgrade_mask = torch.zeros_like(y_q, dtype=torch.bool)
            upgrade_mask[valid_upgrade] = gain >= threshold_gain * 0.999999

            # Handle ties: ensure we don't exceed budget
            actual_increase = delta_r[upgrade_mask].sum().item()
            if actual_increase > remaining_budget * 1.005:
                # Too many from ties - reduce
                num_upgrades = max(1, num_upgrades - 1)
                threshold_gain = gain[sorted_indices[num_upgrades - 1]]
                upgrade_mask = torch.zeros_like(y_q, dtype=torch.bool)
                upgrade_mask[valid_upgrade] = gain > threshold_gain
                actual_increase = delta_r[upgrade_mask].sum().item()

            # Apply upgrades: increase magnitude by 1
            y_q = torch.where(upgrade_mask, sign_q * (abs_q + 1.0), y_q)

            remaining_budget -= actual_increase

            if remaining_budget <= 0:
                break

    return y_q

"""Greedy rate-distortion improvement starting from baseline dead-zone.

Starting from the baseline dead-zone quantizer (tau=0.6), we consider flipping
zero values to ±1 for positions where y_res is close to the dead-zone boundary.
Flips are ordered by distortion-reduction per estimated-bit, and we apply the
best ones until a conservative fraction of the rate budget is used.

Since we only make small changes from the baseline, the rate estimation error
factor should be approximately preserved, making the rate ratio reliable.
"""

import math
import torch


def gaussian_rate(k: torch.Tensor, sigma: torch.Tensor) -> torch.Tensor:
    """Compute -log2(P(k)) for integer k under N(0, sigma)."""
    sigma = torch.clamp(sigma, min=1e-6)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    upper = (k + 0.5) / sigma * inv_sqrt2
    lower = (k - 0.5) / sigma * inv_sqrt2
    prob = 0.5 * (torch.erf(upper) - torch.erf(lower))
    return -torch.log2(torch.clamp(prob, min=1e-30))


def baseline_dead_zone(y_res: torch.Tensor, tau: float = 0.6) -> torch.Tensor:
    """Baseline JPEG-style dead-zone quantizer."""
    shift = tau - 0.5
    if shift <= 0:
        return torch.round(y_res)
    return torch.sign(y_res) * torch.round(torch.clamp(torch.abs(y_res) - shift, min=0.0))


def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    """Greedy R-D improvement over baseline dead-zone.

    1. Start with baseline dead-zone (tau=0.6).
    2. For zero-valued positions near the boundary, consider flipping to ±1.
    3. Sort by (distortion reduction) / (rate increase).
    4. Apply best flips until 0.3% more estimated rate (conservative budget).
    """
    with torch.no_grad():
        # Step 1: baseline
        y_q = baseline_dead_zone(y_res)

        # Baseline estimated rate
        rate_base = gaussian_rate(y_q, scales).sum()

        if rate_base < 1.0:
            return y_q

        # Conservative rate budget: 0.3% more estimated bits
        # Actual cap is 0.5% above baseline actual rate
        # Small changes -> similar error factor -> ratio is approximately correct
        target_rate_increase = rate_base * 0.003

        # Step 2: identify candidates for 0 -> ±1 flips
        # Candidates: currently zero, but |y_res| is reasonably large
        is_zero = (y_q == 0.0)
        abs_y = torch.abs(y_res)

        # Only consider positions where flipping makes sense:
        # |y_res| > 0.3 (meaningful distortion reduction) and scales are reasonable
        candidate = is_zero & (abs_y > 0.3) & (scales > 1e-4)

        if not candidate.any():
            return y_q

        # For each candidate, compute:
        # ΔD = y_res² - (y_res - sign(y))² = 2*|y_res| - 1  (distortion reduction)
        # ΔR = rate(1) - rate(0)  (rate increase)
        abs_y_cand = abs_y[candidate]
        scales_cand = scales[candidate]
        sign_cand = torch.sign(y_res[candidate])

        # Distortion reduction from flipping 0 -> ±1
        # Original distortion: y_res^2, new distortion: (y_res - sign)^2 = (|y|-1)^2
        delta_d = abs_y_cand ** 2 - (abs_y_cand - 1.0) ** 2
        delta_d = torch.clamp(delta_d, min=0.0)

        # Rate increase from 0 to 1
        rate_0 = gaussian_rate(torch.zeros_like(scales_cand), scales_cand)
        rate_1 = gaussian_rate(torch.ones_like(scales_cand), scales_cand)
        delta_r = rate_1 - rate_0

        # Only consider flips with positive rate increase and positive distortion gain
        valid = (delta_r > 0) & (delta_d > 0)
        if not valid.any():
            return y_q

        delta_d = delta_d[valid]
        delta_r = delta_r[valid]
        sign_cand_valid = sign_cand[valid]

        # Gain = distortion reduction per bit
        gain = delta_d / delta_r

        # Step 3: sort by gain (highest first) and apply until budget exhausted
        sorted_indices = torch.argsort(gain, descending=True)
        sorted_delta_r = delta_r[sorted_indices]
        sorted_sign = sign_cand_valid[sorted_indices]

        # Cumulative rate
        cum_r = torch.cumsum(sorted_delta_r, dim=0)
        num_flips = torch.searchsorted(cum_r, target_rate_increase).item()
        num_flips = min(num_flips, len(sorted_delta_r))

        if num_flips == 0:
            return y_q

        # Step 4: apply flips
        # We need to map back to the original tensor positions
        # This is tricky with vectorized operations; let's use a different approach
        
        # Get the threshold gain
        threshold_gain = gain[sorted_indices[num_flips - 1]]
        
        # Apply flips where gain >= threshold (approximately num_flips elements)
        flip_mask = torch.zeros_like(y_q, dtype=torch.bool)
        
        # Build a mask of valid candidates with gain >= threshold
        # We need to put gain values back into original tensor shape
        gain_full = torch.zeros_like(y_q)
        sign_full = torch.zeros_like(y_q)
        
        # Map valid candidate indices back
        cand_flat = candidate.view(-1)
        valid_flat = torch.zeros_like(cand_flat)
        # valid is a subset of candidate
        # Let me do this more carefully...
        
        # Actually, let's use a simpler approach: just threshold by gain
        # Compute gain for all candidate positions
        all_delta_d = torch.zeros_like(y_q)
        all_delta_r = torch.zeros_like(y_q)
        
        all_delta_d[candidate] = abs_y[candidate] ** 2 - (abs_y[candidate] - 1.0) ** 2
        all_delta_d = torch.clamp(all_delta_d, min=0.0)
        
        all_rate_0 = gaussian_rate(torch.zeros_like(scales), scales)
        all_rate_1 = gaussian_rate(torch.ones_like(scales), scales)
        all_delta_r = all_rate_1 - all_rate_0
        
        all_gain = torch.where(candidate & (all_delta_r > 0) & (all_delta_d > 0),
                               all_delta_d / torch.clamp(all_delta_r, min=1e-10),
                               torch.zeros_like(y_q))
        
        # Find the gain threshold that uses ~target_rate_increase bits
        # Sort all valid gains
        valid_gain = all_gain[candidate & (all_delta_r > 0) & (all_delta_d > 0)]
        valid_dr = all_delta_r[candidate & (all_delta_r > 0) & (all_delta_d > 0)]
        
        if len(valid_gain) == 0:
            return y_q
        
        sorted_idx = torch.argsort(valid_gain, descending=True)
        sorted_dr = valid_dr[sorted_idx]
        cum_dr = torch.cumsum(sorted_dr, dim=0)
        n_flip = torch.searchsorted(cum_dr, target_rate_increase).item()
        n_flip = min(n_flip, len(sorted_dr))
        
        if n_flip == 0:
            return y_q
        
        # Get threshold gain
        threshold = valid_gain[sorted_idx[n_flip - 1]]
        
        # Apply flips
        flip = candidate & (all_gain >= threshold) & (all_delta_r > 0) & (all_delta_d > 0)
        
        # Make sure we don't exceed budget by too much (handle ties)
        flip_rate = all_delta_r[flip].sum()
        if flip_rate > target_rate_increase * 1.1:
            # Too many from ties - reduce threshold
            n_flip = max(1, n_flip - 1)
            threshold = valid_gain[sorted_idx[n_flip - 1]]
            flip = candidate & (all_gain > threshold) & (all_delta_r > 0) & (all_delta_d > 0)
        
        y_q = torch.where(flip, torch.sign(y_res), y_q)

    return y_q

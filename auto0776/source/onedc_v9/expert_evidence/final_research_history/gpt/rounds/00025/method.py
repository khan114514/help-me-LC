"""Deterministic entropy allocation with channel-normalized distortion.

The frozen Gaussian CDF construction is reproduced from its public source;
no codec, image, file, or evaluation state is accessed at quantization time.
"""

import math
import torch


_TABLES = None


def _make_tables():
    # Match the codec's 256 logarithmic scales and its 16-bit CDF rounding.
    scale_table = torch.exp(torch.linspace(math.log(0.11), math.log(64.0), 256))
    centers = torch.full((256,), 50, dtype=torch.int64)
    for k in range(50, 1, -1):
        cdf = 0.5 * (1.0 + torch.erf(k / scale_table / math.sqrt(2.0)))
        centers = torch.where(cdf > 0.9999, k, centers)
    samples = torch.arange(101, dtype=torch.float32)[None, :] - centers[:, None]
    upper = 0.5 * (1.0 + torch.erf((samples + 0.5) / scale_table[:, None] / math.sqrt(2.0)))
    lower = 0.5 * (1.0 + torch.erf((samples - 0.5) / scale_table[:, None] / math.sqrt(2.0)))
    pmf = upper - lower
    tail = 2.0 * lower[:, 0]
    costs = torch.zeros((256, 102), dtype=torch.float32)
    for row in range(256):
        length = 2 * int(centers[row]) + 1
        probabilities = pmf[row, :length].tolist() + [float(tail[row])]
        frequencies = [int(math.floor(p * 65536.0 + 0.5)) for p in probabilities]
        total = sum(frequencies)
        frequencies = [(65536 * f) // total for f in frequencies]
        frequencies[-1] += 65536 - sum(frequencies)
        # The C++ implementation steals from the first smallest frequency > 1.
        for i in range(len(frequencies)):
            if frequencies[i] == 0:
                donor = min((f, j) for j, f in enumerate(frequencies) if f > 1)[1]
                frequencies[donor] -= 1
                frequencies[i] = 1
        costs[row, :length + 1] = torch.tensor(
            [16.0 - math.log2(f) for f in frequencies], dtype=torch.float32
        )
    return costs, centers


def _symbol_bits(q, indexes, centers, costs):
    value = q.to(torch.int64) + centers
    sentinel = 2 * centers + 1
    outside = (value < 0) | (value >= sentinel)
    column = torch.where(outside, sentinel, value).clamp(0, 101)
    bits = costs[indexes, column]
    # Out-of-support values use the coder's tail symbol and four-bit bypasses.
    raw = torch.where(value < 0, -2 * value - 1, 2 * (value - sentinel)).clamp_min(0)
    bypasses = torch.ceil(torch.log2(raw.to(torch.float32) + 1.0) / 4.0)
    return bits + torch.where(outside, 4.0 * (1.0 + bypasses), 0.0)


@torch.no_grad()
def quantize(y_res: torch.Tensor, scales: torch.Tensor, ctx: dict) -> torch.Tensor:
    global _TABLES
    if _TABLES is None:
        _TABLES = _make_tables()
    costs, center_table = _TABLES
    costs = costs.to(device=y_res.device)
    center_table = center_table.to(device=y_res.device)

    # Preserve the original dead-zone computation as the rate reference.
    baseline = torch.sign(y_res) * torch.round((y_res.abs() - 0.1).clamp_min(0.0))
    residual = y_res.float()
    sign = torch.sign(residual)
    magnitude = baseline.abs().float()
    candidates = torch.stack((
        sign * (magnitude - 1.0).clamp_min(0.0),
        baseline.float(),
        sign * (magnitude + 1.0).clamp_max(30000.0),
    ), dim=0)

    log_min = math.log(0.11)
    log_step = (math.log(64.0) - log_min) / 255.0
    indexes = ((torch.log(scales.float().clamp_min(1e-5)) - log_min) / log_step)
    indexes = indexes.clamp(0, 255).to(torch.int64)
    centers = center_table[indexes]
    active = (y_res != 0) | (scales != 0)
    rates = _symbol_bits(candidates, indexes, centers, costs) * active.float()
    # DISTS compares normalized feature statistics. Approximate that invariance
    # in latent space by sharing the bit budget according to each channel's
    # relative reconstruction error, rather than its arbitrary activation gain.
    # Masked prior positions must not dilute the channel variance estimates.
    mask = active.float()
    count = mask.sum(dim=(-2, -1), keepdim=True).clamp_min(1.0)
    mean = (residual * mask).sum(dim=(-2, -1), keepdim=True) / count
    variance = ((residual - mean).square() * mask).sum(
        dim=(-2, -1), keepdim=True
    ) / count
    reference_variance = variance.median(dim=1, keepdim=True).values
    # A half-bin variance floor and bounded weights keep quiet channels from
    # consuming the budget, and limit departures from the tested MSE allocator.
    weights = ((reference_variance + 0.25) / (variance + 0.25)).clamp(0.5, 2.0)
    errors = (candidates - residual).square() * weights.unsqueeze(0)

    # Allocate each batch element independently; retain a small rate reserve
    # for arithmetic coder rounding and the subsequent spatial-prior stages.
    result = baseline.float().clone()
    for b in range(y_res.shape[0]):
        rb = rates[:, b].reshape(3, -1)
        eb = errors[:, b].reshape(3, -1)
        budget = float(rb[1].double().sum()) * 0.99
        minimum_rate = float(rb.min(dim=0).values.double().sum())
        if minimum_rate > budget:
            continue

        def choose(multiplier):
            selected = (eb + multiplier * rb).argmin(dim=0)
            used = float(rb.gather(0, selected[None, :]).double().sum())
            return selected, used

        selected, used = choose(0.0)
        if used > budget:
            lo, hi = 0.0, 1.0
            selected, used = choose(hi)
            for _ in range(24):
                if used <= budget:
                    break
                hi *= 2.0
                selected, used = choose(hi)
            if used > budget:
                continue
            # Keep the feasible side of the search, with deterministic ties.
            for _ in range(26):
                mid = (lo + hi) * 0.5
                trial, used = choose(mid)
                if used <= budget:
                    hi, selected = mid, trial
                else:
                    lo = mid
        cb = candidates[:, b].reshape(3, -1)
        result[b] = cb.gather(0, selected[None, :]).reshape_as(result[b])
    return result.to(dtype=y_res.dtype)

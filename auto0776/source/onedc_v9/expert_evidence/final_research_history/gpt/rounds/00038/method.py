"""Deterministic entropy allocation with signed covariance error shaping.

The frozen Gaussian CDF construction is reproduced from its public source;
no codec, image, file, or evaluation state is accessed at quantization time.
"""

import math
import torch
import torch.nn.functional as F


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


def _allocate(rates, errors, budget):
    """Select a feasible side of the deterministic Lagrange search."""
    def choose(multiplier):
        selected = (errors + multiplier * rates).argmin(dim=0)
        used = float(rates.gather(0, selected[None, :]).double().sum())
        return selected, used

    selected, used = choose(0.0)
    if used <= budget:
        return selected
    lo, hi = 0.0, 1.0
    selected, used = choose(hi)
    for _ in range(24):
        if used <= budget:
            break
        hi *= 2.0
        selected, used = choose(hi)
    if used > budget:
        return None
    for _ in range(26):
        mid = (lo + hi) * 0.5
        trial, used = choose(mid)
        if used <= budget:
            hi, selected = mid, trial
        else:
            lo = mid
    return selected


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
        # Coupled distortion need not favor the residual's sign: a small
        # opposite-sign symbol can cancel error in correlated channels.
        # Append it only at zero baseline symbols; elsewhere reuse baseline
        # so the previously tested candidate set and tie order are preserved.
        torch.where(magnitude == 0.0, -sign, baseline.float()),
    ), dim=0)
    candidate_count = candidates.shape[0]

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
        rb = rates[:, b].reshape(candidate_count, -1)
        eb = errors[:, b].reshape(candidate_count, -1)
        budget = float(rb[1].double().sum()) * 0.99
        minimum_rate = float(rb.min(dim=0).values.double().sum())
        if minimum_rate > budget:
            continue
        selected = _allocate(rb, eb, budget)
        if selected is None:
            continue
        cb = candidates[:, b].reshape(candidate_count, -1)
        current = cb.gather(0, selected[None, :]).reshape_as(result[b])

        # Pointwise error alone can spend the rate budget by shrinking a
        # channel's contrast or shifting its mean. Add the spatial statistics
        # that DISTS uses, with a half-bin floor for nearly constant channels.
        mb, nb, wb = mask[b], count[b], weights[b]
        source_mean = mean[b]
        source_std = torch.sqrt(variance[b] + 0.25)
        channels = current.shape[0]
        covariance_scale = source_std * torch.sqrt(nb)

        def pack_features(q, qmean):
            # The four-part prior places one active sample per channel in
            # each 2x2 cell, at channel-dependent offsets. Sum each cell to
            # align nearby samples across all channels, including phases
            # whose products would otherwise be identically zero.
            normalized = (q - qmean) * mb / covariance_scale
            return F.avg_pool2d(
                normalized.unsqueeze(0), 2, stride=2,
                ceil_mode=True, divisor_override=1,
            ).reshape(channels, -1)

        source_features = pack_features(residual[b], source_mean)
        source_covariance = source_features @ source_features.t()
        off_diagonal = 1.0 - torch.eye(channels, device=current.device)
        phases = mb[:, :2, :2].reshape(channels, -1)
        same_phase = ((phases @ phases.t()) > 0).float()
        # Keep the established same-phase term and give the additional
        # neighboring-phase correlations a smaller, conservative weight.
        covariance_pair_weights = same_phase + 0.25 * (1.0 - same_phase)
        covariance_weight = (
            0.25 * float(nb.mean())
            * float(reference_variance[b].reshape(-1)[0] + 0.25)
            / max(channels // 4, 1)
        )

        # Estimate which channel combinations naturally carry source energy.
        # A ridge and bounded inverse eigenvalues prevent small sample modes
        # from dominating. Trace normalization preserves the average MSE weight.
        # This metric penalizes error across correlated channels, in addition
        # to the existing penalty on changes in their reconstructed covariance.
        eigenvalues, eigenvectors = torch.linalg.eigh(
            source_covariance * covariance_pair_weights
        )
        inverse_eigenvalues = (eigenvalues.clamp_min(0.0) + 0.5).reciprocal()
        inverse_eigenvalues = inverse_eigenvalues.clamp(0.5, 2.0)
        inverse_eigenvalues = inverse_eigenvalues / inverse_eigenvalues.mean()
        precision_correction = (
            (eigenvectors * inverse_eigenvalues.unsqueeze(0)) @ eigenvectors.t()
            - torch.eye(channels, device=current.device)
        )
        whitening_weight = 0.25
        error_scale = wb.sqrt() * mb
        whitening_diagonal = (
            whitening_weight * precision_correction.diagonal()
        ).reshape(channels, 1, 1) * wb * mb

        def pack_error(q):
            return F.avg_pool2d(
                ((q - residual[b]) * error_scale).unsqueeze(0),
                2, stride=2, ceil_mode=True, divisor_override=1,
            ).reshape(channels, -1)

        def moments(q):
            qmean = (q * mb).sum(dim=(-2, -1), keepdim=True) / nb
            qvar = ((q - qmean).square() * mb).sum(
                dim=(-2, -1), keepdim=True
            ) / nb
            return qmean, torch.sqrt(qvar + 0.25)

        def covariance(q, qmean):
            features = pack_features(q, qmean)
            difference = (
                features @ features.t() - source_covariance
            ) * off_diagonal
            return features, difference

        def refinement_errors(q, qmean, qstd):
            mean_bias = qmean - source_mean
            contrast = (0.5 * (1.0 - source_std / qstd)).clamp(-0.5, 0.5)
            moment_errors = wb.unsqueeze(0) * mb.unsqueeze(0) * (
                2.0 * mean_bias.unsqueeze(0) * candidates[:, b]
                + contrast.unsqueeze(0)
                * (candidates[:, b] - qmean.unsqueeze(0)).square()
            )
            # Match covariance of channel mixtures on the compacted lattice.
            features, difference = covariance(q, qmean)
            packed_gradient = (
                4.0 * covariance_weight
                * ((difference * covariance_pair_weights) @ features)
            ).reshape(channels, (q.shape[-2] + 1) // 2,
                      (q.shape[-1] + 1) // 2)
            # Adjoint of the cell sum, then adjoint of masked centering.
            gradient = packed_gradient.repeat_interleave(
                2, dim=-2
            ).repeat_interleave(2, dim=-1)
            gradient = gradient[:, :q.shape[-2], :q.shape[-1]]
            gradient = gradient * mb / covariance_scale
            gradient = gradient - (
                (gradient * mb).sum(dim=(-2, -1), keepdim=True) / nb
            ) * mb
            packed_error_gradient = (
                2.0 * whitening_weight * (precision_correction @ pack_error(q))
            ).reshape(channels, (q.shape[-2] + 1) // 2,
                      (q.shape[-1] + 1) // 2)
            error_gradient = packed_error_gradient.repeat_interleave(
                2, dim=-2
            ).repeat_interleave(2, dim=-1)
            error_gradient = (
                error_gradient[:, :q.shape[-2], :q.shape[-1]] * error_scale
            )
            changes = candidates[:, b] - q.unsqueeze(0)
            # Include the exact diagonal quadratic term for each integer move;
            # the acceptance test accounts for simultaneous coupled moves.
            whitening_errors = (
                error_gradient.unsqueeze(0) * changes
                + whitening_diagonal.unsqueeze(0) * changes.square()
            )
            return (
                moment_errors + gradient.unsqueeze(0) * candidates[:, b]
                + whitening_errors
            )

        def objective(q):
            qmean, qstd = moments(q)
            pointwise = ((q - residual[b]).square() * mb * wb).sum()
            statistics = (nb * wb * (
                (qmean - source_mean).square()
                + 0.5 * (qstd - source_std).square()
            )).sum()
            _, covariance_difference = covariance(q, qmean)
            covariance_error = (
                covariance_weight * (
                    covariance_difference.square() * covariance_pair_weights
                ).sum()
            )
            packed_error = pack_error(q)
            whitening_error = whitening_weight * (
                packed_error * (precision_correction @ packed_error)
            ).sum()
            return float((
                pointwise + statistics + covariance_error + whitening_error
            ).double())

        best_objective = objective(current)
        for _ in range(3):
            qmean, qstd = moments(current)
            # Quadratic local model of the channel-statistic penalties.
            # Reallocate all symbols jointly, then accept only a decrease in
            # the complete nonlinear objective under the same bit budget.
            moment_errors = refinement_errors(current, qmean, qstd)
            trial_selected = _allocate(
                rb, eb + moment_errors.reshape(candidate_count, -1), budget
            )
            if trial_selected is None:
                break
            trial = cb.gather(0, trial_selected[None, :]).reshape_as(current)
            trial_objective = objective(trial)
            if trial_objective >= best_objective:
                break
            current, best_objective = trial, trial_objective
            selected = trial_selected

        # A full parallel update can overshoot: all pixels in a channel use
        # the same mean/contrast correction before any statistics are updated.
        # Refine four interleaved subsets of the active 2x2 prior lattice in
        # sequence, recomputing the correction after each accepted subset.
        # Reserve exactly the rate already occupied by the other subsets.
        height, width = current.shape[-2:]
        rows = torch.arange(height, device=current.device)[:, None] // 2
        columns = torch.arange(width, device=current.device)[None, :] // 2
        lattice_groups = (rows.remainder(2) + 2 * columns.remainder(2))
        group_indices = [
            ((lattice_groups == group).unsqueeze(0) & mb.bool())
            .reshape(-1).nonzero(as_tuple=False).flatten()
            for group in range(4)
        ]
        used_rate = float(rb.gather(0, selected[None, :]).double().sum())
        for _ in range(3):
            improved = False
            for positions in group_indices:
                if positions.numel() == 0:
                    continue
                qmean, qstd = moments(current)
                moment_errors = refinement_errors(current, qmean, qstd)
                group_rates = rb[:, positions]
                group_errors = (
                    eb + moment_errors.reshape(candidate_count, -1)
                )[:, positions]
                group_selected = selected[positions]
                group_used = float(group_rates.gather(
                    0, group_selected[None, :]
                ).double().sum())
                group_budget = budget - used_rate + group_used
                trial_selected = _allocate(group_rates, group_errors, group_budget)
                if trial_selected is None:
                    continue
                trial = current.clone()
                trial.reshape(-1)[positions] = cb[:, positions].gather(
                    0, trial_selected[None, :]
                ).flatten()
                trial_objective = objective(trial)
                if trial_objective >= best_objective:
                    continue
                trial_rate = float(group_rates.gather(
                    0, trial_selected[None, :]
                ).double().sum())
                used_rate += trial_rate - group_used
                selected[positions] = trial_selected
                current, best_objective = trial, trial_objective
                improved = True
            if not improved:
                break
        result[b] = current
    return result.to(dtype=y_res.dtype)

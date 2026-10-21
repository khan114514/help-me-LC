"""Deterministic entropy allocation with multiscale local moment refinement.

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
        selected = _allocate(rb, eb, budget)
        if selected is None:
            continue
        cb = candidates[:, b].reshape(3, -1)
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
        spatial_error_weight = 0.10
        error_scale = wb.sqrt() * mb
        whitening_diagonal = (
            whitening_weight * precision_correction.diagonal()
        ).reshape(channels, 1, 1) * wb * mb

        def pack_error(q):
            return F.avg_pool2d(
                ((q - residual[b]) * error_scale).unsqueeze(0),
                2, stride=2, ceil_mode=True, divisor_override=1,
            ).reshape(channels, -1)

        def compact_error(q):
            return pack_error(q).reshape(
                channels, (q.shape[-2] + 1) // 2,
                (q.shape[-1] + 1) // 2,
            )

        def spatial_error_terms(q):
            packed = compact_error(q)
            gradient = torch.zeros_like(packed)
            degree = torch.zeros_like(packed)
            horizontal = packed[:, :, :-1] + packed[:, :, 1:]
            vertical = packed[:, :-1, :] + packed[:, 1:, :]
            gradient[:, :, :-1] += spatial_error_weight * horizontal
            gradient[:, :, 1:] += spatial_error_weight * horizontal
            gradient[:, :-1, :] += spatial_error_weight * vertical
            gradient[:, 1:, :] += spatial_error_weight * vertical
            degree[:, :, :-1] += 1.0
            degree[:, :, 1:] += 1.0
            degree[:, :-1, :] += 1.0
            degree[:, 1:, :] += 1.0
            energy = 0.5 * spatial_error_weight * (
                horizontal.square().sum() + vertical.square().sum()
            )
            return gradient, degree, energy

        def moments(q):
            qmean = (q * mb).sum(dim=(-2, -1), keepdim=True) / nb
            qvar = ((q - qmean).square() * mb).sum(
                dim=(-2, -1), keepdim=True
            ) / nb
            return qmean, torch.sqrt(qvar + 0.25)

        # Global feature statistics can hide local loss of texture contrast.
        # A 4x4 / 8x8 patch in the masked tensor contains 2x2 / 4x4
        # samples on each channel's compact prior lattice. Preserve their
        # local means and standard deviations as well as the global moments.
        def patch_sum(values, kernel):
            return F.avg_pool2d(
                values.unsqueeze(0), kernel, stride=kernel,
                ceil_mode=True, divisor_override=1,
            ).squeeze(0)

        def patch_moments(q, kernel, samples):
            qmean = patch_sum(q * mb, kernel) / samples
            qvar = (
                patch_sum(q.square() * mb, kernel) / samples
                - qmean.square()
            ).clamp_min(0.0)
            return qmean, qvar

        local_targets = []
        for kernel, strength in ((4, 0.20), (8, 0.10)):
            samples = patch_sum(mb, kernel).clamp_min(1.0)
            target_mean, target_var = patch_moments(
                residual[b], kernel, samples
            )
            local_targets.append((
                kernel, strength, samples, target_mean,
                torch.sqrt(target_var + 0.25),
            ))

        def local_moment_errors(q):
            changes = candidates[:, b] - q.unsqueeze(0)
            error = torch.zeros_like(changes)
            for kernel, strength, samples, target_mean, target_std in local_targets:
                qmean, qvar = patch_moments(q, kernel, samples)

                def expand(values):
                    return values.repeat_interleave(
                        kernel, dim=-2
                    ).repeat_interleave(kernel, dim=-1)[
                        :, :q.shape[-2], :q.shape[-1]
                    ].unsqueeze(0)

                n = expand(samples)
                mean_here, var_here = expand(qmean), expand(qvar)
                mean_bias = mean_here - expand(target_mean)
                target_std_here = expand(target_std)
                # Exact finite-step change in one patch's mean and variance
                # for each integer candidate, including the centering term.
                trial_var = (
                    var_here + (
                        2.0 * changes * (q.unsqueeze(0) - mean_here)
                        + changes.square() * (1.0 - n.reciprocal())
                    ) / n
                ).clamp_min(0.0)
                mean_delta = changes / n
                contrast_delta = (
                    (torch.sqrt(trial_var + 0.25) - target_std_here).square()
                    - (torch.sqrt(var_here + 0.25) - target_std_here).square()
                )
                error += strength * n * wb.unsqueeze(0) * mb.unsqueeze(0) * (
                    2.0 * mean_bias * mean_delta + mean_delta.square()
                    + 0.5 * contrast_delta
                )
            return error

        def local_moment_objective(q):
            energy = torch.zeros((), device=q.device)
            for kernel, strength, samples, target_mean, target_std in local_targets:
                qmean, qvar = patch_moments(q, kernel, samples)
                energy += strength * (samples * wb * (
                    (qmean - target_mean).square()
                    + 0.5 * (torch.sqrt(qvar + 0.25) - target_std).square()
                )).sum()
            return energy

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
            # A single integer change alters each off-diagonal covariance
            # linearly. Its squared discrepancy therefore has an exact
            # quadratic term, omitted by the first-order covariance model.
            # Centering contributes no extra term here: every other channel's
            # packed features sum to zero on the complete prior lattice.
            covariance_curvature = (
                2.0 * covariance_weight
                * ((covariance_pair_weights * off_diagonal) @ features.square())
            ).reshape(channels, (q.shape[-2] + 1) // 2,
                      (q.shape[-1] + 1) // 2)
            covariance_curvature = covariance_curvature.repeat_interleave(
                2, dim=-2
            ).repeat_interleave(2, dim=-1)[:, :q.shape[-2], :q.shape[-1]]
            covariance_curvature = (
                covariance_curvature * mb / covariance_scale.square()
            )
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
            spatial_gradient, spatial_degree, _ = spatial_error_terms(q)
            spatial_gradient = spatial_gradient.repeat_interleave(
                2, dim=-2
            ).repeat_interleave(2, dim=-1)[:, :q.shape[-2], :q.shape[-1]]
            spatial_gradient = spatial_gradient * error_scale
            spatial_diagonal = (
                0.5 * spatial_error_weight * spatial_degree
            ).repeat_interleave(2, dim=-2).repeat_interleave(
                2, dim=-1
            )[:, :q.shape[-2], :q.shape[-1]] * error_scale.square()
            changes = candidates[:, b] - q.unsqueeze(0)
            # Include the exact diagonal quadratic term for each integer move;
            # the acceptance test accounts for simultaneous coupled moves.
            whitening_errors = (
                error_gradient.unsqueeze(0) * changes
                + whitening_diagonal.unsqueeze(0) * changes.square()
            )
            spatial_errors = (
                spatial_gradient.unsqueeze(0) * changes
                + spatial_diagonal.unsqueeze(0) * changes.square()
            )
            return (
                moment_errors + gradient.unsqueeze(0) * candidates[:, b]
                + covariance_curvature.unsqueeze(0) * changes.square()
                + whitening_errors + spatial_errors
                + local_moment_errors(q)
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
            _, _, spatial_error = spatial_error_terms(q)
            return float((
                pointwise + statistics + covariance_error + whitening_error
                + spatial_error + local_moment_objective(q)
            ).double())

        best_objective = objective(current)
        for _ in range(3):
            qmean, qstd = moments(current)
            # Quadratic local model of the channel-statistic penalties.
            # Reallocate all symbols jointly, then accept only a decrease in
            # the complete nonlinear objective under the same bit budget.
            moment_errors = refinement_errors(current, qmean, qstd)
            trial_selected = _allocate(
                rb, eb + moment_errors.reshape(3, -1), budget
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
                group_errors = (eb + moment_errors.reshape(3, -1))[:, positions]
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

        # The precision metric couples errors at the same compact lattice
        # location. Independent symbol allocation misses moves where two
        # correlated channels jointly improve, although neither does alone.
        # Match channels by precision coupling, then search all nine pairs
        # of their existing integer candidates under the same rate budget.
        cell_counts = F.avg_pool2d(
            mb.unsqueeze(0), 2, stride=2, ceil_mode=True,
            divisor_override=1,
        ).squeeze(0)
        if channels % 2 == 0 and bool((cell_counts == 1).all()):
            coupling = (
                precision_correction.abs()
                * wb.reshape(channels).sqrt()[:, None]
                * wb.reshape(channels).sqrt()[None, :]
            ).cpu().tolist()
            edges = sorted(
                (-coupling[i][j], i, j)
                for i in range(channels) for j in range(i + 1, channels)
            )
            paired = set()
            first_channels, second_channels = [], []
            for _, i, j in edges:
                if i in paired or j in paired:
                    continue
                first_channels.append(i)
                second_channels.append(j)
                paired.add(i)
                paired.add(j)
                if len(paired) == channels:
                    break
            first = torch.tensor(first_channels, device=current.device)
            second = torch.tensor(second_channels, device=current.device)
            first_option = torch.arange(9, device=current.device) // 3
            second_option = torch.arange(9, device=current.device) % 3

            def pack_cells(values):
                return F.avg_pool2d(
                    values, 2, stride=2, ceil_mode=True,
                    divisor_override=1,
                )

            packed_candidates = pack_cells(candidates[:, b])
            packed_rates = pack_cells(rates[:, b])
            pair_rates = (
                packed_rates[:, first].index_select(0, first_option)
                + packed_rates[:, second].index_select(0, second_option)
            ).reshape(9, -1)
            pair_first_values = packed_candidates[:, first].index_select(
                0, first_option
            )
            pair_second_values = packed_candidates[:, second].index_select(
                0, second_option
            )
            packed_selected = pack_cells(
                (selected.reshape_as(current).float() * mb).unsqueeze(0)
            ).squeeze(0).to(torch.int64)
            pair_selected = (
                3 * packed_selected[first] + packed_selected[second]
            ).reshape(-1)
            pair_shape = pair_first_values.shape[1:]
            pair_height, pair_width = pair_shape[-2:]
            pair_rows = torch.arange(pair_height, device=current.device)[:, None]
            pair_columns = torch.arange(pair_width, device=current.device)[None, :]
            pair_groups = pair_rows.remainder(2) + 2 * pair_columns.remainder(2)
            pair_positions = [
                (pair_groups == group).expand(pair_shape).reshape(-1)
                .nonzero(as_tuple=False).flatten()
                for group in range(4)
            ]
            cross_weight = (
                2.0 * whitening_weight * precision_correction[first, second]
                * (wb[first] * wb[second]).sqrt().reshape(-1)
            ).reshape(1, -1, 1, 1)
            pair_covariance_weight = (
                2.0 * covariance_weight * covariance_pair_weights[first, second]
            ).reshape(1, -1, 1, 1)
            first_covariance_scale = covariance_scale[first].unsqueeze(0)
            second_covariance_scale = covariance_scale[second].unsqueeze(0)
            centered_impulse_norm = (
                1.0 - nb[first].reciprocal()
            ).unsqueeze(0)

            for _ in range(2):
                improved = False
                for positions in pair_positions:
                    if positions.numel() == 0:
                        continue
                    qmean, qstd = moments(current)
                    local_errors = pack_cells(
                        errors[:, b] + refinement_errors(current, qmean, qstd)
                    )
                    packed_current = pack_cells(current.unsqueeze(0)).squeeze(0)
                    first_change = (
                        pair_first_values - packed_current[first].unsqueeze(0)
                    )
                    second_change = (
                        pair_second_values - packed_current[second].unsqueeze(0)
                    )
                    pair_features, pair_difference = covariance(current, qmean)
                    pair_features = pair_features.reshape(channels, pair_height, pair_width)
                    normalized_first_change = first_change / first_covariance_scale
                    normalized_second_change = second_change / second_covariance_scale
                    first_linear_change = (
                        normalized_first_change * pair_features[second].unsqueeze(0)
                    )
                    second_linear_change = (
                        normalized_second_change * pair_features[first].unsqueeze(0)
                    )
                    # Two changes share one centered spatial impulse. Their
                    # covariance acquires a bilinear increment in addition to
                    # the individual linear increments. Include the complete
                    # finite-step pair correction (through fourth order),
                    # subtracting the diagonal terms already in local_errors.
                    joint_covariance_change = (
                        normalized_first_change * normalized_second_change
                        * centered_impulse_norm
                    )
                    pair_covariance_correction = pair_covariance_weight * (
                        2.0 * first_linear_change * second_linear_change
                        + 2.0 * (first_linear_change + second_linear_change)
                        * joint_covariance_change
                        + joint_covariance_change.square()
                        + 2.0 * pair_difference[first, second].reshape(1, -1, 1, 1)
                        * joint_covariance_change
                    )
                    # The individual local models already contain the exact
                    # precision diagonal; add the missing pair cross term.
                    pair_errors = (
                        local_errors[:, first].index_select(0, first_option)
                        + local_errors[:, second].index_select(0, second_option)
                        + cross_weight * first_change * second_change
                        + pair_covariance_correction
                    ).reshape(9, -1)
                    group_rates = pair_rates[:, positions]
                    group_used = float(group_rates.gather(
                        0, pair_selected[positions].unsqueeze(0)
                    ).double().sum())
                    trial_selected = _allocate(
                        group_rates, pair_errors[:, positions],
                        budget - used_rate + group_used,
                    )
                    if trial_selected is None:
                        continue
                    trial_packed = packed_current.clone()
                    first_values = trial_packed[first].clone()
                    second_values = trial_packed[second].clone()
                    first_values.reshape(-1)[positions] = (
                        pair_first_values.reshape(9, -1)[:, positions].gather(
                            0, trial_selected.unsqueeze(0)
                        ).flatten()
                    )
                    second_values.reshape(-1)[positions] = (
                        pair_second_values.reshape(9, -1)[:, positions].gather(
                            0, trial_selected.unsqueeze(0)
                        ).flatten()
                    )
                    trial_packed[first] = first_values
                    trial_packed[second] = second_values
                    trial = trial_packed.repeat_interleave(
                        2, dim=-2
                    ).repeat_interleave(2, dim=-1)[:, :height, :width] * mb
                    trial_objective = objective(trial)
                    if trial_objective >= best_objective:
                        continue
                    trial_rate = float(group_rates.gather(
                        0, trial_selected.unsqueeze(0)
                    ).double().sum())
                    used_rate += trial_rate - group_used
                    pair_selected[positions] = trial_selected
                    current, best_objective = trial, trial_objective
                    improved = True
                if not improved:
                    break
        result[b] = current
    return result.to(dtype=y_res.dtype)

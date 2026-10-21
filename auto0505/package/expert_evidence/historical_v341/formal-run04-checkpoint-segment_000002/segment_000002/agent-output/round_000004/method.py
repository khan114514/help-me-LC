"""High-noise error-density grid with exact BF16 midpoint coefficients.

The continuous grid t=1-s**2 allocates density proportional to (1-t)**(-1/2).
Projection onto multiples of 1/128 makes nodes and midpoints exactly BF16
representable.  Minimum one-bin intervals prevent collapsed endpoint steps.
"""


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    if num_steps < 1:
        raise ValueError('num_steps must be positive')
    raw = [1.0 - (i / num_steps) ** 2 for i in range(num_steps + 1)]
    if num_steps <= 128:
        bins = [128]
        for i in range(1, num_steps):
            target = round(128 * raw[i])
            # Keep room for every remaining interval and ensure strict descent.
            target = max(num_steps - i, min(bins[-1] - 1, target))
            bins.append(target)
        bins.append(0)
        nodes = [k / 128.0 for k in bins]
    else:
        nodes = raw
    nodes[0], nodes[-1] = 1.0, 0.0
    return nodes

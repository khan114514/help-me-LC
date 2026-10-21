"""Quadratic noise density aligned to FLUX's scaled time embedding.

The reference time embedding multiplies a BF16 time by 1000 before FP32
conversion.  Nodes on a 1/125 grid and their 1/250 midpoints survive that
scaled conversion exactly.  Enforce one grid cell per interval.
"""


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    if num_steps < 1:
        raise ValueError("num_steps must be positive")
    raw = [1.0 - (i / num_steps) ** 2 for i in range(num_steps + 1)]
    resolution = 125
    if num_steps <= resolution:
        bins = [resolution]
        for i in range(1, num_steps):
            target = round(resolution * raw[i])
            target = max(num_steps - i, min(bins[-1] - 1, target))
            bins.append(target)
        bins.append(0)
        nodes = [k / resolution for k in bins]
    else:
        nodes = raw
    nodes[0], nodes[-1] = 1.0, 0.0
    return nodes

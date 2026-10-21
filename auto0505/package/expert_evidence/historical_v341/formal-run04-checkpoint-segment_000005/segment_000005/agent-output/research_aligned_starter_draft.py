"""Starter logit density with scaled time-embedding alignment.

Keep the original sequence-length shift but align all nodes and midpoints to
the effective time scale.  This separates schedule shape from alignment.
"""

import math


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    if num_steps < 1:
        raise ValueError("num_steps must be positive")
    mu = 0.5 + (image_seq_len - 256) / (4096 - 256) * (1.15 - 0.5)
    scale = math.exp(mu)
    raw = []
    for i in range(num_steps + 1):
        u = 1.0 - i / num_steps
        raw.append(scale * u / (1.0 + (scale - 1.0) * u))
    resolution = 125
    if num_steps <= resolution:
        bins = [resolution]
        for i in range(1, num_steps):
            target = round(resolution * raw[i])
            bins.append(max(num_steps - i, min(bins[-1] - 1, target)))
        bins.append(0)
        nodes = [k / resolution for k in bins]
    else:
        nodes = raw
    nodes[0], nodes[-1] = 1.0, 0.0
    return nodes

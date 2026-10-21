"""Low-noise-focused rational schedule, developed from the Starter logit warp.

The negative shift reverses the official high-time preference.  Both directions
share the returned nodes; there are no model calls or external data reads.
"""

import math


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    if num_steps < 1:
        raise ValueError("num_steps must be positive")
    scale = math.exp(-0.63)
    nodes = []
    for i in range(num_steps + 1):
        u = 1.0 - i / num_steps
        nodes.append(scale * u / (1.0 + (scale - 1.0) * u))
    nodes[0], nodes[-1] = 1.0, 0.0
    return nodes

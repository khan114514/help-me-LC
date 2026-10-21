"""High-noise-focused rational schedule developed from the Starter time shift.

Uniform nodes lost public reconstruction PSNR, so this candidate strengthens
the official preference for smaller steps near t=1.
"""

import math


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    if num_steps < 1:
        raise ValueError("num_steps must be positive")
    scale = math.exp(1.20)
    nodes = []
    for i in range(num_steps + 1):
        u = 1.0 - i / num_steps
        nodes.append(scale * u / (1.0 + (scale - 1.0) * u))
    nodes[0], nodes[-1] = 1.0, 0.0
    return nodes

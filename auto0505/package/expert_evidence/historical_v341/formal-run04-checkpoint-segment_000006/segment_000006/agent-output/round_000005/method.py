"""Continuous quadratic noise density with the same minimum gap as round 4.

This removes integer-grid rounding while keeping the endpoint gap floor, so
the public comparison tests time quantization rather than collapsed steps.
"""


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    if num_steps < 1:
        raise ValueError("num_steps must be positive")
    raw = [1.0 - (i / num_steps) ** 2 for i in range(num_steps + 1)]
    if num_steps <= 128:
        nodes = [1.0]
        for i in range(1, num_steps):
            target = max((num_steps - i) / 128.0,
                         min(nodes[-1] - 1.0 / 128.0, raw[i]))
            nodes.append(target)
        nodes.append(0.0)
    else:
        nodes = raw
    nodes[0], nodes[-1] = 1.0, 0.0
    return nodes

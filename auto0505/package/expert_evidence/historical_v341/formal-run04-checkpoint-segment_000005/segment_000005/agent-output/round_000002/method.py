"""Unshift the Starter schedule to balance forward and reverse midpoint steps."""


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    if num_steps < 1:
        raise ValueError("num_steps must be positive")
    nodes = [1.0 - i / num_steps for i in range(num_steps + 1)]
    nodes[0], nodes[-1] = 1.0, 0.0
    return nodes

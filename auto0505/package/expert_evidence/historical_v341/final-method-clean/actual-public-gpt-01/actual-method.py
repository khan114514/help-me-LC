"""Sine projection considering bf16 time-embedding quantization."""

import math


def _bf16(value: float) -> float:
    if value == 0.0:
        return 0.0
    quantum = math.ldexp(1.0, math.frexp(value)[1] - 8)
    return round(value / quantum) * quantum


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    if num_steps < 1:
        raise ValueError("num_steps must be positive")
    grid = 1 << (max(128, num_steps) - 1).bit_length()
    max_step = max(12, 1 << (((grid + num_steps - 1) // num_steps) - 1).bit_length())
    choices = range(1, max_step + 1)
    errors = []
    for index in range(2 * grid + 1):
        time = index / (2 * grid)
        errors.append((_bf16(1000.0 * _bf16(time)) - 1000.0 * time) ** 2)
    edge_cost = {}
    for position in range(grid):
        for step in choices:
            end = position + step
            if end <= grid:
                edge_cost[position, step] = errors[2 * (grid - position)] + errors[2 * (grid - end)] + 2 * errors[2 * grid - position - end]
    scale = sum(edge_cost.values()) / len(edge_cost) or 1.0
    targets = [grid * (1.0 - math.sin(0.5 * math.pi * (1.0 - i / num_steps)))
               for i in range(num_steps + 1)]
    states = {0: (0.0, ())}
    for i in range(1, num_steps + 1):
        remaining = num_steps - i
        following = {}
        for position, (cost, path) in states.items():
            for step in choices:
                end = position + step
                if end + remaining > grid or end + remaining * max_step < grid:
                    continue
                candidate = cost + (end - targets[i]) ** 2 + 0.5 * bool(step & (step - 1)) + 4 * edge_cost[position, step] / scale
                if end not in following or candidate < following[end][0]:
                    following[end] = (candidate, path + (step,))
        states = following
    timesteps = [1.0]
    position = 0
    for step in states[grid][1]:
        position += step
        timesteps.append(1.0 - position / grid)
    return timesteps

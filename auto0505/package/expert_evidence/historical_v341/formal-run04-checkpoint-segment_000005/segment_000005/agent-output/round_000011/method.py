"""Quadratic schedule projected onto variable-precision embedding fixed points.

A deterministic shortest path preserves exact effective embedding times for
both nodes and midpoints while approximating a continuous quadratic mesh.
"""

import struct


def _bf16(value):
    bits = struct.unpack('>I', struct.pack('>f', value))[0]
    bits = (bits + 0x7fff + ((bits >> 16) & 1)) & 0xffff0000
    return struct.unpack('>f', struct.pack('>I', bits))[0]


def _fixed(value):
    effective = _bf16(1000.0 * _bf16(value)) / 1000.0
    return abs(value - effective) < 1e-12


def get_timesteps(num_steps: int, image_seq_len: int) -> list[float]:
    if num_steps < 1:
        raise ValueError('num_steps must be positive')
    raw = [1.0 - (i / num_steps) ** 2 for i in range(num_steps + 1)]
    if num_steps > 125:
        raw[0], raw[-1] = 1.0, 0.0
        return raw
    continuous = [1.0]
    for i in range(1, num_steps):
        continuous.append(max((num_steps - i) / 125.0,
                              min(continuous[-1] - 1.0 / 125.0, raw[i])))
    continuous.append(0.0)
    fixed_nodes = [k for k in range(1001) if _fixed(k / 1000.0)]
    fixed_midpoints = {k for k in range(2001) if _fixed(k / 2000.0)}
    states = {1000: 0.0}
    parents = []
    for i in range(1, num_steps + 1):
        target = 1000.0 * continuous[i]
        if i == num_steps:
            candidates = [0]
        else:
            candidates = [k for k in fixed_nodes
                          if 8 * (num_steps - i) <= k <= 1000 - 8 * i
                          and abs(k - target) <= 16.0]
        next_states = {}
        step_parents = {}
        for k in candidates:
            best = None
            for previous, cost in states.items():
                if previous - k < 8 or previous + k not in fixed_midpoints:
                    continue
                entry = (cost + (k - target) ** 2, previous)
                if best is None or entry < best:
                    best = entry
            if best is not None:
                next_states[k] = best[0]
                step_parents[k] = best[1]
        if not next_states:
            # The coarse mesh provides an exact, feasible fallback.
            bins = [125]
            for j in range(1, num_steps):
                bins.append(max(num_steps - j,
                                min(bins[-1] - 1, round(125.0 * raw[j]))))
            bins.append(0)
            return [k / 125.0 for k in bins]
        states = next_states
        parents.append(step_parents)
    path = [0]
    for level in range(num_steps - 1, -1, -1):
        path.append(parents[level][path[-1]])
    nodes = [k / 1000.0 for k in reversed(path)]
    nodes[0], nodes[-1] = 1.0, 0.0
    return nodes
